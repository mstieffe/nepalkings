# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Cross-worker coordination coverage."""

import threading

import pytest

import background_worker
from game_service.conquer_tactics_idempotency import (
    acquire_game_transaction_lock,
)
from models import Figure, Game, LogEntry, Player, db
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


def test_postgres_concurrent_challenge_acceptance_creates_one_game(
    app,
    client,
    db,
    two_users,
    auth_headers_user1,
):
    """Concurrent accepts return one game and charge each user once."""
    from models import Challenge, Game, User

    with app.app_context():
        if db.engine.dialect.name != 'postgresql':
            pytest.skip('PostgreSQL-only challenge row-lock assertion')

    user1, user2 = two_users
    user1_id, user2_id = user1.id, user2.id
    original_gold = (user1.gold, user2.gold)
    challenge_response = client.post(
        '/challenges/create_challenge',
        data={
            'challenger': user1.username,
            'opponent': user2.username,
            'stake': '10',
        },
        headers=auth_headers_user1,
    )
    assert challenge_response.status_code == 200
    with app.app_context():
        challenge_id = Challenge.query.one().id

    start = threading.Barrier(3)
    responses = []
    failures = []

    def _accept():
        try:
            with app.test_client() as thread_client:
                start.wait(timeout=5)
                response = thread_client.post(
                    '/games/create_game',
                    data={'challenge_id': str(challenge_id)},
                    headers=auth_headers_user1,
                )
                responses.append((response.status_code, response.get_json()))
        except Exception as exc:  # pragma: no cover - surfaced below
            failures.append(exc)

    first = threading.Thread(target=_accept)
    second = threading.Thread(target=_accept)
    first.start()
    second.start()
    start.wait(timeout=5)
    first.join(timeout=15)
    second.join(timeout=15)

    assert not first.is_alive()
    assert not second.is_alive()
    assert failures == []
    assert len(responses) == 2
    assert {status for status, _payload in responses} == {200}
    assert all(payload['success'] is True for _status, payload in responses)
    assert len({
        payload['game']['id']
        for _status, payload in responses
    }) == 1

    with app.app_context():
        db.session.remove()
        challenge = db.session.get(Challenge, challenge_id)
        refreshed_user1 = db.session.get(User, user1_id)
        refreshed_user2 = db.session.get(User, user2_id)
        assert Game.query.count() == 1
        assert challenge.game_id == Game.query.one().id
        assert refreshed_user1.gold == original_gold[0] - challenge.stake
        assert refreshed_user2.gold == original_gold[1] - challenge.stake


def test_concurrent_conquer_advances_apply_exactly_one_action(
    app,
    two_users,
    auth_headers_user1,
):
    """Two requests cannot both advance against the same turn snapshot."""
    user1, user2 = two_users
    with app.app_context():
        game = Game(mode='conquer', state='open', ceasefire_active=False)
        db.session.add(game)
        db.session.flush()
        attacker = Player(
            game_id=game.id,
            user_id=user1.id,
            turns_left=1,
        )
        defender = Player(
            game_id=game.id,
            user_id=user2.id,
            turns_left=0,
        )
        db.session.add_all([attacker, defender])
        db.session.flush()
        figures = [
            Figure(
                game_id=game.id,
                player_id=attacker.id,
                family_name=f'Test Attacker {index}',
                field='military',
                color='offensive',
                name=f'Test Attacker {index}',
                suit='Hearts',
            )
            for index in (1, 2)
        ]
        defender_figure = Figure(
            game_id=game.id,
            player_id=defender.id,
            family_name='Test Defender',
            field='military',
            color='defensive',
            name='Test Defender',
            suit='Spades',
        )
        db.session.add_all([*figures, defender_figure])
        db.session.flush()
        game.turn_player_id = attacker.id
        game.invader_player_id = attacker.id
        db.session.commit()
        game_id = game.id
        attacker_id = attacker.id
        defender_id = defender.id
        figure_ids = [figure.id for figure in figures]

    start = threading.Barrier(3)
    responses = []
    failures = []

    def _advance(figure_id):
        try:
            with app.test_client() as thread_client:
                start.wait(timeout=5)
                response = thread_client.post(
                    '/games/advance_figure',
                    json={
                        'game_id': game_id,
                        'player_id': attacker_id,
                        'figure_id': figure_id,
                    },
                    headers=auth_headers_user1,
                )
                responses.append((response.status_code, response.get_json()))
        except Exception as exc:  # pragma: no cover - surfaced below
            failures.append(exc)

    first = threading.Thread(target=_advance, args=(figure_ids[0],))
    second = threading.Thread(target=_advance, args=(figure_ids[1],))
    first.start()
    second.start()
    start.wait(timeout=5)
    first.join(timeout=15)
    second.join(timeout=15)

    assert not first.is_alive()
    assert not second.is_alive()
    assert failures == []
    assert sorted(status for status, _payload in responses) == [200, 400], responses
    assert sum(
        payload.get('success') is True
        for _status, payload in responses
    ) == 1

    with app.app_context():
        db.session.remove()
        game = db.session.get(Game, game_id)
        attacker = db.session.get(Player, attacker_id)
        defender = db.session.get(Player, defender_id)
        assert game.advancing_figure_id in figure_ids
        assert game.turn_player_id == defender_id
        assert attacker.turns_left == 0
        assert defender.turns_left == 1
        assert LogEntry.query.filter_by(
            game_id=game_id,
            type='advance',
        ).count() == 1


def test_finished_game_rejects_new_advance(
    app,
    two_users,
    auth_headers_user1,
):
    """A stale client cannot mutate a Conquer game after another action ends it."""
    user1, user2 = two_users
    with app.app_context():
        game = Game(mode='conquer', state='finished')
        db.session.add(game)
        db.session.flush()
        attacker = Player(
            game_id=game.id,
            user_id=user1.id,
            turns_left=1,
        )
        defender = Player(
            game_id=game.id,
            user_id=user2.id,
            turns_left=0,
        )
        db.session.add_all([attacker, defender])
        db.session.flush()
        figure = Figure(
            game_id=game.id,
            player_id=attacker.id,
            family_name='Late Attacker',
            field='military',
            color='offensive',
            name='Late Attacker',
            suit='Hearts',
        )
        db.session.add(figure)
        db.session.flush()
        game.turn_player_id = attacker.id
        db.session.commit()
        payload = {
            'game_id': game.id,
            'player_id': attacker.id,
            'figure_id': figure.id,
        }

    response = app.test_client().post(
        '/games/advance_figure',
        json=payload,
        headers=auth_headers_user1,
    )

    assert response.status_code == 409
    assert response.get_json()['message'] == 'Game is already finished'
