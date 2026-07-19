# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Cross-worker coordination coverage."""

import threading

import pytest

import background_worker
from game_service.conquer_tactics_idempotency import (
    acquire_game_transaction_lock,
)
from models import db
from security_rate_limits import consume_rate_limit


def test_shared_security_rate_limit_is_database_backed(app):
    with app.app_context():
        first = consume_rate_limit(
            'test.login',
            '198.51.100.8',
            limit=2,
            window_seconds=60,
            now=1_000,
        )
        db.session.remove()
        second = consume_rate_limit(
            'test.login',
            '198.51.100.8',
            limit=2,
            window_seconds=60,
            now=1_001,
        )
        db.session.remove()
        third = consume_rate_limit(
            'test.login',
            '198.51.100.8',
            limit=2,
            window_seconds=60,
            now=1_002,
        )

    assert first[0] is True
    assert second[0] is True
    assert third[0] is False


def test_worker_iteration_triggers_candidates_and_sweeper(
        app,
        monkeypatch,
):
    import ai.ai_worker as ai_worker
    import sweepers

    triggered = []
    monkeypatch.setattr(
        background_worker,
        '_candidate_game_ids',
        lambda _app: [11, 22],
    )
    monkeypatch.setattr(
        ai_worker,
        'trigger_ai_if_needed',
        lambda game_id, app=None: triggered.append((game_id, app)),
    )
    monkeypatch.setattr(
        sweepers,
        'sweep_stuck_conquer_games',
        lambda: 3,
    )

    result = background_worker.run_worker_iteration(
        app,
        run_sweeper=True,
    )

    assert [game_id for game_id, _app in triggered] == [11, 22]
    assert all(worker_app is app for _game_id, worker_app in triggered)
    assert result == {
        'candidate_games': 2,
        'swept_games': 3,
    }


def test_worker_leadership_is_singleton(app, tmp_path, monkeypatch):
    """Only one always-on worker can lead an environment at a time."""
    monkeypatch.setenv(
        'BACKGROUND_WORKER_LOCK_PATH',
        str(tmp_path / 'background-worker.lock'),
    )
    first = background_worker.acquire_worker_leadership(app)
    assert first is not None
    try:
        second = background_worker.acquire_worker_leadership(app)
        assert second is None
    finally:
        first.close()

    replacement = background_worker.acquire_worker_leadership(app)
    assert replacement is not None
    replacement.close()


def test_postgres_game_transaction_lock_serializes_sessions(app):
    """Two independent PostgreSQL sessions cannot mutate one game together."""
    with app.app_context():
        if db.engine.dialect.name != 'postgresql':
            pytest.skip('PostgreSQL-only advisory lock assertion')

    first_acquired = threading.Event()
    second_attempted = threading.Event()
    second_acquired = threading.Event()
    release_first = threading.Event()
    failures = []

    def _first_worker():
        try:
            with app.app_context():
                acquire_game_transaction_lock(9876)
                first_acquired.set()
                assert release_first.wait(5)
                db.session.commit()
        except Exception as exc:  # pragma: no cover - surfaced below
            failures.append(exc)

    def _second_worker():
        try:
            assert first_acquired.wait(5)
            with app.app_context():
                second_attempted.set()
                acquire_game_transaction_lock(9876)
                second_acquired.set()
                db.session.commit()
        except Exception as exc:  # pragma: no cover - surfaced below
            failures.append(exc)

    first = threading.Thread(target=_first_worker)
    second = threading.Thread(target=_second_worker)
    first.start()
    second.start()
    assert second_attempted.wait(5)
    assert not second_acquired.wait(0.2)
    release_first.set()
    assert second_acquired.wait(5)
    first.join(timeout=5)
    second.join(timeout=5)

    assert not first.is_alive()
    assert not second.is_alive()
    assert failures == []
