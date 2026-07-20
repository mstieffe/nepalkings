# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Dedicated AI and maintenance worker for hosted deployments."""

from __future__ import annotations

import hashlib
import logging
import os
import signal
import threading
import time
from pathlib import Path

from sqlalchemy import or_, text

import server_settings as settings


logger = logging.getLogger('nepalkings.background_worker')
_POSTGRES_WORKER_LOCK_NAMESPACE = 20044


def _candidate_game_ids(app):
    """Return unfinished Conquer games and duels containing an AI user."""
    with app.app_context():
        from models import Game, Player, User, db

        ai_game_ids = (
            db.session.query(Player.game_id)
            .join(User, User.id == Player.user_id)
            .filter(User.is_ai.is_(True))
        )
        rows = (
            db.session.query(Game.id)
            .filter(Game.state.in_(('open', 'active')))
            .filter(or_(
                Game.mode == 'conquer',
                Game.id.in_(ai_game_ids),
            ))
            .order_by(Game.id)
            .limit(500)
            .all()
        )
        return [game_id for (game_id,) in rows]


def run_worker_iteration(app, *, run_sweeper=False):
    """Trigger pending AI work and optionally run the stuck-game sweep."""
    from ai.ai_worker import trigger_ai_if_needed

    game_ids = _candidate_game_ids(app)
    if settings.AI_JOBS_ENABLED:
        for game_id in game_ids:
            with app.app_context():
                trigger_ai_if_needed(game_id, app=app)

    swept = 0
    if run_sweeper:
        with app.app_context():
            from sweepers import sweep_stuck_conquer_games

            swept = sweep_stuck_conquer_games()
    return {
        'candidate_games': len(game_ids),
        'ai_jobs_enabled': bool(settings.AI_JOBS_ENABLED),
        'swept_games': swept,
    }


class _WorkerLeadership:
    """Lifetime leadership handle for one always-on worker."""

    def __init__(
        self,
        *,
        file_handle=None,
        connection=None,
        environment_key=None,
    ):
        self.file_handle = file_handle
        self.connection = connection
        self.environment_key = environment_key

    def close(self):
        connection = self.connection
        self.connection = None
        if connection is not None:
            try:
                connection.execute(
                    text(
                        'SELECT pg_advisory_unlock('
                        ':namespace, :environment_key)'
                    ),
                    {
                        'namespace': _POSTGRES_WORKER_LOCK_NAMESPACE,
                        'environment_key': self.environment_key,
                    },
                )
                connection.commit()
            except Exception:
                logger.exception(
                    'Failed to explicitly release background-worker '
                    'leadership; closing the connection will release it'
                )
            finally:
                connection.close()

        handle = self.file_handle
        self.file_handle = None
        if handle is not None:
            try:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()


def _environment_lock_key():
    digest = hashlib.sha256(
        settings.APP_ENVIRONMENT.encode('utf-8'),
    ).digest()
    return int.from_bytes(digest[:4], 'big') & 0x7fffffff


def acquire_worker_leadership(app):
    """Acquire environment leadership without blocking.

    PostgreSQL uses a session advisory lock, so leadership is released
    automatically if the task crashes or loses its database connection.
    SQLite development uses a local file lock.
    """
    with app.app_context():
        from models import db

        if db.engine.dialect.name == 'postgresql':
            connection = db.engine.connect()
            environment_key = _environment_lock_key()
            try:
                acquired = bool(connection.execute(
                    text(
                        'SELECT pg_try_advisory_lock('
                        ':namespace, :environment_key)'
                    ),
                    {
                        'namespace': _POSTGRES_WORKER_LOCK_NAMESPACE,
                        'environment_key': environment_key,
                    },
                ).scalar_one())
                connection.commit()
            except Exception:
                connection.close()
                raise
            if not acquired:
                connection.close()
                return None
            return _WorkerLeadership(
                connection=connection,
                environment_key=environment_key,
            )

    import fcntl

    configured = os.getenv('BACKGROUND_WORKER_LOCK_PATH', '').strip()
    path = Path(configured or (
        f'/tmp/nepalkings-{settings.APP_ENVIRONMENT}-background-worker.lock'
    )).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open('a+', encoding='utf-8')
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    return _WorkerLeadership(file_handle=handle)


def run_forever(app, *, stop_event=None):
    """Run the single always-on task until SIGTERM/SIGINT."""
    if not settings.AI_ENABLED:
        raise RuntimeError(
            'The background worker requires AI_ENABLED=True'
        )

    leadership = acquire_worker_leadership(app)
    if leadership is None:
        raise RuntimeError(
            'Another background worker already owns this environment'
        )

    if stop_event is None:
        stop_event = threading.Event()

    def _stop(signum, _frame):
        logger.info('Background worker received signal %s', signum)
        stop_event.set()

    previous_handlers = {}
    for signum in (signal.SIGTERM, signal.SIGINT):
        previous_handlers[signum] = signal.signal(signum, _stop)

    poll_seconds = max(
        0.25,
        float(os.getenv('BACKGROUND_WORKER_POLL_SECONDS', '2')),
    )
    sweep_seconds = max(
        5.0,
        float(settings.STUCK_CONQUER_SWEEP_INTERVAL_SECONDS),
    )

    try:
        with app.app_context():
            from ai import init_ai_users

            init_ai_users()

        logger.info(
            'Background worker started environment=%s poll=%ss sweep=%ss',
            settings.APP_ENVIRONMENT,
            poll_seconds,
            sweep_seconds,
        )
        last_sweep = 0.0
        while not stop_event.is_set():
            now = time.monotonic()
            run_sweeper = now - last_sweep >= sweep_seconds
            result = run_worker_iteration(
                app,
                run_sweeper=run_sweeper,
            )
            if run_sweeper:
                last_sweep = now
                logger.info(
                    'Worker sweep complete candidates=%s resolved=%s',
                    result['candidate_games'],
                    result['swept_games'],
                )
            stop_event.wait(poll_seconds)
    finally:
        leadership.close()
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
        with app.app_context():
            from models import db

            db.session.remove()
            db.engine.dispose()
        logger.info('Background worker stopped')
