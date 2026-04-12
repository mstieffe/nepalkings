# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Worker-level tests for AI orchestration and execution helpers."""

import pytest

from ai import ai_worker


@pytest.fixture(autouse=True)
def reset_ai_worker_state():
    with ai_worker._active_games_lock:
        ai_worker._active_games.clear()
        ai_worker._pending_retrigger.clear()
    with ai_worker._ai_player_user_ids_lock:
        ai_worker._ai_player_user_ids.clear()
    with ai_worker._ai_watchdog_lock:
        ai_worker._ai_watchdog_retries.clear()
    with ai_worker._game_strategies_lock:
        ai_worker._game_strategies.clear()
    with ai_worker._ai_chat_lock:
        ai_worker._ai_chat_states.clear()

    yield

    with ai_worker._active_games_lock:
        ai_worker._active_games.clear()
        ai_worker._pending_retrigger.clear()
    with ai_worker._ai_player_user_ids_lock:
        ai_worker._ai_player_user_ids.clear()
    with ai_worker._ai_watchdog_lock:
        ai_worker._ai_watchdog_retries.clear()
    with ai_worker._game_strategies_lock:
        ai_worker._game_strategies.clear()
    with ai_worker._ai_chat_lock:
        ai_worker._ai_chat_states.clear()


def _create_game_with_ai(db):
    from models import Game, Player, User
    from werkzeug.security import generate_password_hash

    ai_user = User(
        username='[AI] WorkerBot',
        password_hash=generate_password_hash('x'),
        is_ai=True,
        gold=9999,
    )
    human_user = User(
        username='worker_human',
        password_hash=generate_password_hash('x'),
        is_ai=False,
        gold=9999,
    )
    db.session.add_all([ai_user, human_user])
    db.session.commit()

    game = Game(current_round=1, stake=35, state='open')
    db.session.add(game)
    db.session.commit()

    ai_player = Player(user_id=ai_user.id, game_id=game.id, turns_left=2, points=0)
    human_player = Player(user_id=human_user.id, game_id=game.id, turns_left=2, points=0)
    db.session.add_all([ai_player, human_player])
    db.session.commit()

    game.turn_player_id = ai_player.id
    game.invader_player_id = ai_player.id
    db.session.commit()

    return game, ai_player


def test_ai_post_injects_auth_and_internal_header(monkeypatch):
    with ai_worker._ai_player_user_ids_lock:
        ai_worker._ai_player_user_ids[42] = 100

    monkeypatch.setattr(
        ai_worker,
        'get_ai_auth_headers',
        lambda _uid: {'Authorization': 'Bearer token-123'},
    )

    captured = {}

    def fake_post(url, headers=None, **kwargs):
        captured['url'] = url
        captured['headers'] = headers or {}
        captured['kwargs'] = kwargs

        class DummyResponse:
            pass

        return DummyResponse()

    monkeypatch.setattr(ai_worker.http_requests, 'post', fake_post)

    ai_worker._ai_post('http://example.invalid/action', 42, json={'ok': True})

    assert captured['url'] == 'http://example.invalid/action'
    assert captured['headers']['Authorization'] == 'Bearer token-123'
    assert captured['headers']['X-NepalKings-AI-Internal'] == '1'
    assert captured['kwargs']['timeout'] == 15


def test_trigger_ai_if_needed_skips_without_api_key(app, monkeypatch):
    monkeypatch.setattr(ai_worker.settings, 'AI_ENABLED', True)
    monkeypatch.setattr(ai_worker.settings, 'AI_OPENAI_API_KEY', '')

    thread_created = {'value': False}

    class FakeThread:
        def __init__(self, *args, **kwargs):
            thread_created['value'] = True

        def start(self):
            thread_created['value'] = True

    monkeypatch.setattr(ai_worker.threading, 'Thread', FakeThread)

    ai_worker.trigger_ai_if_needed(999, app=app)

    assert thread_created['value'] is False


def test_trigger_ai_if_needed_marks_pending_retrigger_when_game_already_active(app, db, monkeypatch):
    game, ai_player = _create_game_with_ai(db)

    monkeypatch.setattr(ai_worker.settings, 'AI_ENABLED', True)
    monkeypatch.setattr(ai_worker.settings, 'AI_OPENAI_API_KEY', 'test-key')
    monkeypatch.setattr(ai_worker, 'detect_phase', lambda *_args, **_kwargs: 'normal_turn')

    with ai_worker._active_games_lock:
        ai_worker._active_games.add(game.id)

    ai_worker.trigger_ai_if_needed(game.id, app=app)

    with ai_worker._active_games_lock:
        assert game.id in ai_worker._pending_retrigger


def test_ask_llm_for_action_falls_back_to_first_on_invalid_action(monkeypatch):
    class StubClient:
        def choose_action(self, _system_prompt, _user_prompt, temperature=0.4):
            return '{"action": 999, "plan": "do something"}'

    monkeypatch.setattr(ai_worker, '_get_llm_client', lambda: StubClient())
    monkeypatch.setattr(ai_worker, 'serialize_game_for_llm', lambda *_args, **_kwargs: 'state')
    monkeypatch.setattr(ai_worker, 'format_actions_for_llm', lambda _actions: 'actions')

    actions = [
        {'id': 1, 'type': 'change_cards', 'description': 'swap low cards', 'params': {}},
        {'id': 2, 'type': 'advance_figure', 'description': 'advance strongest', 'params': {'figure_id': 7}},
    ]

    chosen = ai_worker._ask_llm_for_action({'id': 5}, ai_player_id=1, phase='normal_turn', actions=actions)
    assert chosen['id'] == 1


def test_handle_finish_battle_draw_picks_high_value_card(monkeypatch):
    calls = []

    def fake_ai_post(url, ai_player_id, **kwargs):
        calls.append((url, ai_player_id, kwargs.get('json')))

        class DummyResponse:
            def json(self):
                return {'success': True}

        return DummyResponse()

    monkeypatch.setattr(ai_worker, '_ai_post', fake_ai_post)

    ai_worker._handle_finish_battle_draw(
        base='http://server.local',
        game_id=11,
        ai_player_id=22,
        returnable_cards=[{'id': 7, 'value': 6, 'type': 'main'}],
    )

    assert calls
    url, ai_pid, payload = calls[-1]
    assert url.endswith('/games/finish_battle_draw')
    assert ai_pid == 22
    assert payload['choice'] == 'pick_card'
    assert payload['picked_card_id'] == 7
    assert payload['picked_card_type'] == 'main'


def test_handle_finish_battle_draw_defaults_to_destroy_when_cards_are_weak(monkeypatch):
    calls = []

    def fake_ai_post(url, ai_player_id, **kwargs):
        calls.append((url, ai_player_id, kwargs.get('json')))

        class DummyResponse:
            def json(self):
                return {'success': True}

        return DummyResponse()

    monkeypatch.setattr(ai_worker, '_ai_post', fake_ai_post)

    ai_worker._handle_finish_battle_draw(
        base='http://server.local',
        game_id=12,
        ai_player_id=23,
        returnable_cards=[{'id': 8, 'value': 4, 'type': 'side'}],
    )

    assert calls
    url, ai_pid, payload = calls[-1]
    assert url.endswith('/games/finish_battle_draw')
    assert ai_pid == 23
    assert payload['choice'] == 'destroy'


def test_sanitize_game_dict_for_prompt_removes_chat_messages_only():
    game_dict = {
        'id': 5,
        'current_round': 3,
        'chat_messages': [{'message': 'ignore me'}],
        'players': [{'id': 1}],
    }

    sanitized = ai_worker._sanitize_game_dict_for_prompt(game_dict)

    assert 'chat_messages' not in sanitized
    assert sanitized['id'] == 5
    assert sanitized['current_round'] == 3
    assert sanitized['players'] == [{'id': 1}]


def test_extract_ai_chat_line_normalizes_llm_output_format():
    raw = """```text
assistant: "Opponent, your line is cracked already."
```"""

    message = ai_worker._extract_ai_chat_line(raw)

    assert message == 'Opponent, your line is cracked already.'