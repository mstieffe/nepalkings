# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for AI observability/debug access routes."""

import pytest

import ai.ai_worker as ai_worker


@pytest.fixture(autouse=True)
def reset_ai_debug_state():
    with ai_worker._game_strategies_lock:
        ai_worker._game_strategies.clear()
    with ai_worker._planner_events_lock:
        ai_worker._planner_events.clear()

    yield

    with ai_worker._game_strategies_lock:
        ai_worker._game_strategies.clear()
    with ai_worker._planner_events_lock:
        ai_worker._planner_events.clear()


def _create_users_and_game(db):
    from models import User, Game, Player
    from werkzeug.security import generate_password_hash

    ai_user = User(
        username='[AI] ObserverBot',
        password_hash=generate_password_hash('x'),
        is_ai=True,
        gold=9999,
    )
    human_user = User(
        username='observer_human',
        password_hash=generate_password_hash('x'),
        is_ai=False,
        gold=9999,
    )
    outsider_user = User(
        username='observer_outsider',
        password_hash=generate_password_hash('x'),
        is_ai=False,
        gold=9999,
    )
    db.session.add_all([ai_user, human_user, outsider_user])
    db.session.commit()

    game = Game(current_round=1, stake=35, state='open')
    db.session.add(game)
    db.session.commit()

    ai_player = Player(user_id=ai_user.id, game_id=game.id, turns_left=2, points=0)
    human_player = Player(user_id=human_user.id, game_id=game.id, turns_left=2, points=0)
    db.session.add_all([ai_player, human_player])
    db.session.commit()

    return game, ai_user, human_user, outsider_user, ai_player, human_player


def _auth_headers_for_user(user_id):
    from routes.auth import generate_token

    return {'Authorization': f'Bearer {generate_token(user_id)}'}


def test_get_ai_debug_requires_token(client):
    resp = client.get('/games/get_ai_debug', query_string={'game_id': 1})

    assert resp.status_code == 401


def test_get_ai_debug_forbidden_for_non_participant(client, db):
    game, _ai_user, _human_user, outsider_user, _ai_player, _human_player = _create_users_and_game(db)

    resp = client.get(
        '/games/get_ai_debug',
        query_string={'game_id': game.id},
        headers=_auth_headers_for_user(outsider_user.id),
    )

    assert resp.status_code == 403


def test_get_ai_debug_returns_reasoning_and_planner_events_for_participant(client, db):
    game, _ai_user, human_user, _outsider_user, ai_player, _human_player = _create_users_and_game(db)

    with ai_worker._game_strategies_lock:
        ai_worker._game_strategies[game.id] = [
            'normal_turn: chose change_cards',
            'normal_turn: chose advance_figure | PLAN: seed=2',
        ]
    with ai_worker._planner_events_lock:
        ai_worker._planner_events[game.id] = [
            {'type': 'planner_generated', 'plans': 5},
            {'type': 'planner_shadow_comparison', 'match': False},
        ]

    resp = client.get(
        '/games/get_ai_debug',
        query_string={'game_id': game.id, 'max_notes': 1, 'max_events': 1},
        headers=_auth_headers_for_user(human_user.id),
    )

    assert resp.status_code == 200

    payload = resp.get_json()
    assert payload['success'] is True
    assert payload['game_id'] == game.id
    assert payload['ai_player_id'] == ai_player.id

    ai_debug = payload['ai_debug']
    assert len(ai_debug['strategy_notes']) == 1
    assert ai_debug['strategy_notes'][0].startswith('normal_turn: chose advance_figure')
    assert len(ai_debug['planner_events']) == 1
    assert ai_debug['planner_events'][0]['type'] == 'planner_shadow_comparison'
