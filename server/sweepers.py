# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Background sweepers for stuck game state.

The stuck-conquer sweeper auto-resolves abandoned conquer battles.  A conquer
game is treated as abandoned when its ``state`` is still ``'active'`` (or
``'open'``) and its explicit ``last_activity_at`` timestamp is older
than :data:`server_settings.STUCK_CONQUER_TIMEOUT_SECONDS`.

The defender is treated as the winner: the attacker forfeits.  This calls
``_resolve_conquer_battle`` which is idempotent and writes a LandAttackLog
entry surfaced by the unified kingdom notification feed.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


def _utcnow():
    return datetime.now(timezone.utc)


def sweep_stuck_conquer_games(timeout_seconds=None):
    """Resolve stuck conquer games once.  Returns the number resolved.

    Safe to call from inside a Flask app context.  Does its own commits.
    """
    from models import db, Game, Player
    import server_settings as settings

    if timeout_seconds is None:
        timeout_seconds = settings.STUCK_CONQUER_TIMEOUT_SECONDS

    cutoff = _utcnow() - timedelta(seconds=timeout_seconds)
    # SQLite stores these model datetimes without timezone information. Keep
    # the SQL predicate in the same representation so the database can discard
    # recent/null games before the worker opens a transaction over them.
    cutoff_db = cutoff.replace(tzinfo=None)

    candidates = (
        Game.query
        .filter(Game.mode == 'conquer')
        .filter(Game.state.in_(['active', 'open']))
        .filter(Game.last_activity_at.isnot(None))
        .filter(Game.last_activity_at < cutoff_db)
        .all()
    )

    resolved = 0
    for game in candidates:
        # Require an explicit last_activity_at signal.  Games predating the
        # column (or never touched by an authenticated request) report
        # NULL and are left alone — better to leak a stuck row for one
        # player to revisit than to forfeit a possibly-active battle the
        # first time the sweeper runs after a deploy.
        last_active = game.last_activity_at
        if last_active is None:
            continue
        # Normalize to aware datetime for comparison
        if last_active.tzinfo is None:
            last_active = last_active.replace(tzinfo=timezone.utc)
        if last_active >= cutoff:
            continue

        # Determine the defender — they win on attacker abandonment.
        from routes.games import _conquer_attacker_player, _resolve_conquer_battle
        atk_player = _conquer_attacker_player(game)
        if atk_player is None and game.invader_player_id:
            atk_player = db.session.get(Player, game.invader_player_id)
        defender = None
        if atk_player is not None:
            defender = next(
                (p for p in game.players if p.id != atk_player.id),
                None,
            )
        if defender is None:
            logger.warning(
                "[STUCK_SWEEP] could not determine defender for game %s; skipping",
                game.id,
            )
            continue

        try:
            _resolve_conquer_battle(game, defender, defender)
            db.session.commit()
            resolved += 1
            logger.info(
                "[STUCK_SWEEP] auto-forfeited conquer game %s (land=%s, attacker=%s) — "
                "no activity since %s",
                game.id, game.land_id, atk_player.id if atk_player else None,
                last_active.isoformat(),
            )
        except Exception:
            db.session.rollback()
            logger.exception(
                "[STUCK_SWEEP] failed to auto-resolve game %s", game.id,
            )

    return resolved


def run_stuck_conquer_sweep_iteration(app):
    """Run one daemon iteration and always dispose its scoped DB session."""
    with app.app_context():
        from models import db
        try:
            return sweep_stuck_conquer_games()
        except Exception:
            db.session.rollback()
            raise
        finally:
            # The daemon owns a long-lived thread. Always release its scoped
            # session so no connection or SQLite transaction crosses the sleep
            # between iterations. Flask-SQLAlchemy's app-context teardown also
            # removes it; the explicit call keeps this invariant local/testable.
            db.session.remove()


class _SweeperLeadership:
    """Lifetime handle for the cross-process sweeper leadership lock."""

    def __init__(self, file_handle=None):
        self.file_handle = file_handle

    def release(self):
        handle = self.file_handle
        self.file_handle = None
        if handle is None:
            return
        try:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            handle.close()
        except Exception:
            pass


def _sweeper_lock_path(app):
    """Return one host-wide lock path shared by all WSGI worker processes."""
    import server_settings as settings

    configured = str(getattr(
        settings, 'STUCK_CONQUER_SWEEPER_LOCK_PATH', '') or '').strip()
    if configured:
        return os.path.abspath(os.path.expanduser(configured))

    with app.app_context():
        from models import db
        database = getattr(db.engine.url, 'database', None)
        if db.engine.dialect.name == 'sqlite' and database not in (None, ':memory:'):
            return os.path.abspath(database) + '.stuck-sweeper.lock'

    # Non-SQLite deployments on one host still benefit from one worker. A
    # future multi-host deployment should replace this with a scheduled job or
    # database advisory lock.
    return os.path.join('/tmp', 'nepalkings-stuck-conquer-sweeper.lock')


def acquire_stuck_conquer_sweeper_leadership(app):
    """Acquire non-blocking process leadership, or return ``None``."""
    try:
        import fcntl
    except ImportError:  # pragma: no cover - production is Linux
        logger.warning(
            '[STUCK_SWEEP] fcntl unavailable; process leadership is unsupported')
        return _SweeperLeadership()

    path = _sweeper_lock_path(app)
    handle = None
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        handle = open(path, 'a+', encoding='utf-8')
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        if handle is not None:
            handle.close()
        return None
    except Exception:
        logger.exception('[STUCK_SWEEP] failed to acquire leadership lock %s', path)
        if handle is not None:
            try:
                handle.close()
            except Exception:
                pass
        return None
    return _SweeperLeadership(handle)


def start_stuck_conquer_sweeper(app, interval_seconds=None):
    """Start the one process-leader daemon that periodically runs the sweep."""
    import server_settings as settings

    if interval_seconds is None:
        interval_seconds = settings.STUCK_CONQUER_SWEEP_INTERVAL_SECONDS

    if interval_seconds <= 0:
        logger.info("[STUCK_SWEEP] disabled (interval=%s)", interval_seconds)
        return None

    leadership = acquire_stuck_conquer_sweeper_leadership(app)
    if leadership is None:
        logger.info(
            '[STUCK_SWEEP] another worker owns leadership; this worker will '
            'remain a standby')

    def _loop():
        nonlocal leadership
        try:
            while True:
                if leadership is None:
                    # Standby workers retry so a rolling reload or worker crash
                    # cannot leave the deployment without a sweeper leader.
                    time.sleep(interval_seconds)
                    leadership = acquire_stuck_conquer_sweeper_leadership(app)
                    if leadership is None:
                        continue
                    logger.info('[STUCK_SWEEP] standby worker acquired leadership')
                try:
                    run_stuck_conquer_sweep_iteration(app)
                except Exception:
                    logger.exception("[STUCK_SWEEP] iteration failed")
                time.sleep(interval_seconds)
        finally:
            if leadership is not None:
                leadership.release()

    thread = threading.Thread(
        target=_loop, name='stuck-conquer-sweeper', daemon=True,
    )
    try:
        thread.start()
    except Exception:
        if leadership is not None:
            leadership.release()
        raise
    logger.info(
        "[STUCK_SWEEP] coordinator started (interval=%ss, timeout=%ss, leader=%s)",
        interval_seconds, settings.STUCK_CONQUER_TIMEOUT_SECONDS,
        leadership is not None,
    )
    return thread
