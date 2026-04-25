# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Worker-level tests for AI orchestration and execution helpers."""

import pytest
from types import SimpleNamespace

from ai import ai_worker


@pytest.fixture(autouse=True)
def reset_ai_worker_state():
    with ai_worker._active_games_lock:
        ai_worker._active_games.clear()
        ai_worker._pending_retrigger.clear()
    with ai_worker._ai_player_user_ids_lock:
        ai_worker._ai_player_user_ids.clear()
    with ai_worker._internal_service_tokens_lock:
        ai_worker._internal_service_tokens.clear()
    with ai_worker._ai_watchdog_lock:
        ai_worker._ai_watchdog_retries.clear()
    with ai_worker._game_strategies_lock:
        ai_worker._game_strategies.clear()
    with ai_worker._planner_events_lock:
        ai_worker._planner_events.clear()
    with ai_worker._ai_chat_lock:
        ai_worker._ai_chat_states.clear()
        ai_worker._ai_explain_states.clear()

    yield

    with ai_worker._active_games_lock:
        ai_worker._active_games.clear()
        ai_worker._pending_retrigger.clear()
    with ai_worker._ai_player_user_ids_lock:
        ai_worker._ai_player_user_ids.clear()
    with ai_worker._internal_service_tokens_lock:
        ai_worker._internal_service_tokens.clear()
    with ai_worker._ai_watchdog_lock:
        ai_worker._ai_watchdog_retries.clear()
    with ai_worker._game_strategies_lock:
        ai_worker._game_strategies.clear()
    with ai_worker._planner_events_lock:
        ai_worker._planner_events.clear()
    with ai_worker._ai_chat_lock:
        ai_worker._ai_chat_states.clear()
        ai_worker._ai_explain_states.clear()


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


def test_ai_headers_falls_back_to_internal_service_token(monkeypatch):
    with ai_worker._ai_player_user_ids_lock:
        ai_worker._ai_player_user_ids[77] = 555

    monkeypatch.setattr(
        ai_worker,
        'get_ai_auth_headers',
        lambda _uid: {},
    )

    monkeypatch.setattr(ai_worker, '_generate_internal_service_token', lambda user_id: f'internal-{user_id}')

    headers = ai_worker._ai_headers(77)

    assert headers['Authorization'] == 'Bearer internal-555'


def test_normalize_conquer_auto_gamble_threshold_clamps_and_defaults():
    assert ai_worker._normalize_conquer_auto_gamble_threshold(None) == 10
    assert ai_worker._normalize_conquer_auto_gamble_threshold('bad') == 10
    assert ai_worker._normalize_conquer_auto_gamble_threshold(-3) == 1
    assert ai_worker._normalize_conquer_auto_gamble_threshold(99) == 20
    assert ai_worker._normalize_conquer_auto_gamble_threshold(13) == 13


def test_conquer_choose_gamble_target_prefers_lowest_below_threshold():
    low = {'move': SimpleNamespace(id=1, family_name='Dagger', value=7), 'effective_value': 7}
    mid = {'move': SimpleNamespace(id=2, family_name='Dagger', value=9), 'effective_value': 9}
    block = {'move': SimpleNamespace(id=3, family_name='Block', value=0), 'effective_value': 0}

    chosen = ai_worker._conquer_choose_gamble_target([mid, block, low], threshold=10)
    assert chosen['move'].id == 1


def test_conquer_choose_best_dagger_pair_uses_highest_combined_value():
    moves = [
        SimpleNamespace(id=1, family_name='Dagger', suit='Hearts', value=7),
        SimpleNamespace(id=2, family_name='Dagger', suit='Diamonds', value=9),
        SimpleNamespace(id=3, family_name='Dagger', suit='Spades', value=8),
        SimpleNamespace(id=4, family_name='Dagger', suit='Clubs', value=10),
    ]

    pair = ai_worker._conquer_choose_best_dagger_pair(moves)
    assert pair == (3, 4)


def test_conquer_choose_play_move_prefers_block_when_strongest_not_improving():
    block_info = {
        'move': SimpleNamespace(id=10, family_name='Block', value=2),
        'effective_value': 0,
    }
    strongest_info = {
        'move': SimpleNamespace(id=11, family_name='Dagger', value=8),
        'effective_value': 8,
    }

    chosen = ai_worker._conquer_choose_play_move(
        [strongest_info, block_info],
        opponent_round_value=9,
    )
    assert chosen['move'].id == 10


def test_conquer_choose_play_move_prefers_strongest_when_advantage_positive():
    block_info = {
        'move': SimpleNamespace(id=10, family_name='Block', value=2),
        'effective_value': 0,
    }
    strongest_info = {
        'move': SimpleNamespace(id=11, family_name='Dagger', value=10),
        'effective_value': 10,
    }

    chosen = ai_worker._conquer_choose_play_move(
        [strongest_info, block_info],
        opponent_round_value=6,
    )
    assert chosen['move'].id == 11


def test_conquer_choose_weakest_play_move_picks_lowest_effective_value():
    weakest = {
        'move': SimpleNamespace(id=10, family_name='Dagger', value=7),
        'effective_value': 3,
    }
    mid = {
        'move': SimpleNamespace(id=11, family_name='Dagger', value=8),
        'effective_value': 5,
    }
    strongest = {
        'move': SimpleNamespace(id=12, family_name='Dagger', value=10),
        'effective_value': 9,
    }

    chosen = ai_worker._conquer_choose_weakest_play_move([strongest, weakest, mid])
    assert chosen['move'].id == 10


def test_conquer_play_battle_round_auto_gamble_plays_weakest_when_opponent_block(monkeypatch):
    game = SimpleNamespace(id=50, battle_round=1)

    weakest_move = SimpleNamespace(id=101, family_name='Dagger', value=7)
    strongest_move = SimpleNamespace(id=102, family_name='Dagger', value=10)
    move_infos = [
        {'move': strongest_move, 'effective_value': 10, 'call_figure_id': None},
        {'move': weakest_move, 'effective_value': 7, 'call_figure_id': None},
    ]

    monkeypatch.setattr(ai_worker, '_get_conquer_auto_gamble_settings', lambda *_args, **_kwargs: (True, 10))
    monkeypatch.setattr(ai_worker, '_conquer_collect_move_infos', lambda *_args, **_kwargs: (move_infos, []))
    monkeypatch.setattr(ai_worker, '_conquer_choose_gamble_target', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ai_worker, '_conquer_choose_best_dagger_pair', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ai_worker, '_conquer_opponent_move_value_for_round', lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(ai_worker, '_conquer_opponent_played_block_for_round', lambda *_args, **_kwargs: True)

    captured = {}

    def _capture_play(_base, _game_id, _player_id, params):
        captured['battle_move_id'] = params.get('battle_move_id')
        return True

    monkeypatch.setattr(ai_worker, '_exec_play_battle_move', _capture_play)

    ai_worker._conquer_play_battle_round('http://example.invalid', game, ai_player_id=999)

    assert captured['battle_move_id'] == 101


def test_conquer_play_battle_round_no_auto_gamble_keeps_existing_selector(monkeypatch):
    game = SimpleNamespace(id=51, battle_round=1)

    strongest_move = SimpleNamespace(id=202, family_name='Dagger', value=10)
    move_infos = [
        {'move': strongest_move, 'effective_value': 10, 'call_figure_id': None},
    ]

    monkeypatch.setattr(ai_worker, '_get_conquer_auto_gamble_settings', lambda *_args, **_kwargs: (False, 10))
    monkeypatch.setattr(ai_worker, '_conquer_collect_move_infos', lambda *_args, **_kwargs: (move_infos, []))
    monkeypatch.setattr(ai_worker, '_conquer_opponent_move_value_for_round', lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(ai_worker, '_conquer_opponent_played_block_for_round', lambda *_args, **_kwargs: True)
    monkeypatch.setattr(ai_worker, '_conquer_choose_play_move', lambda infos, _opp: infos[0])

    def _fail_if_called(_infos):
        raise AssertionError('weakest override must only apply when auto-gamble is enabled')

    monkeypatch.setattr(ai_worker, '_conquer_choose_weakest_play_move', _fail_if_called)

    captured = {}

    def _capture_play(_base, _game_id, _player_id, params):
        captured['battle_move_id'] = params.get('battle_move_id')
        return True

    monkeypatch.setattr(ai_worker, '_exec_play_battle_move', _capture_play)

    ai_worker._conquer_play_battle_round('http://example.invalid', game, ai_player_id=999)

    assert captured['battle_move_id'] == 202


def test_conquer_skip_battle_turn_with_fallback_plays_move_when_skip_rejected(monkeypatch):
    move = SimpleNamespace(id=404, family_name='Dagger', value=9)
    game = SimpleNamespace(id=71, battle_round=2)
    refreshed = SimpleNamespace(
        id=71,
        battle_round=2,
        serialize=lambda: {'id': 71},
    )

    monkeypatch.setattr(ai_worker, '_exec_skip_battle_turn', lambda *_args, **_kwargs: False)
    monkeypatch.setattr(ai_worker, '_reload_conquer_game', lambda _game_id: refreshed)
    monkeypatch.setattr(ai_worker, 'detect_phase', lambda *_args, **_kwargs: 'battle_round')
    monkeypatch.setattr(
        ai_worker,
        '_conquer_collect_move_infos',
        lambda *_args, **_kwargs: ([{'move': move, 'effective_value': 9, 'call_figure_id': None}], []),
    )
    monkeypatch.setattr(ai_worker, '_conquer_opponent_move_value_for_round', lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(ai_worker, '_conquer_opponent_played_block_for_round', lambda *_args, **_kwargs: False)

    captured = {}

    def _capture_play(_base, _game_id, _player_id, params):
        captured['battle_move_id'] = params.get('battle_move_id')
        return True

    monkeypatch.setattr(ai_worker, '_exec_play_battle_move', _capture_play)

    result = ai_worker._conquer_skip_battle_turn_with_fallback(
        'http://example.invalid', game, ai_player_id=999, auto_enabled=False)

    assert result is True
    assert captured['battle_move_id'] == 404


def test_conquer_confirm_battle_moves_with_fallback_executes_buy_action(monkeypatch):
    refreshed = SimpleNamespace(
        serialize=lambda: {'id': 72},
    )

    monkeypatch.setattr(ai_worker, '_exec_confirm_battle_moves', lambda *_args, **_kwargs: False)
    monkeypatch.setattr(ai_worker, '_reload_conquer_game', lambda _game_id: refreshed)
    monkeypatch.setattr(ai_worker, 'enrich_figures_with_skills', lambda d: d)
    monkeypatch.setattr(ai_worker, 'detect_phase', lambda *_args, **_kwargs: 'battle_shop')

    fallback_action = {
        'id': 1,
        'type': 'buy_battle_move',
        'description': 'buy fallback move',
        'params': {
            'card_id': 1,
            'family_name': 'Dagger',
            'card_type': 'main',
            'suit': 'Hearts',
            'rank': '7',
            'value': 7,
        },
    }
    monkeypatch.setattr(ai_worker, 'enumerate_actions', lambda *_args, **_kwargs: [fallback_action])

    captured = {}

    def _capture_execute(_app, _game_id, _ai_player_id, action):
        captured['type'] = action.get('type')
        return True

    monkeypatch.setattr(ai_worker, '_execute_action', _capture_execute)

    result = ai_worker._conquer_confirm_battle_moves_with_fallback(
        app=SimpleNamespace(),
        base='http://example.invalid',
        game_id=72,
        ai_player_id=999,
    )

    assert result is True
    assert captured['type'] == 'buy_battle_move'


def test_conquer_try_finish_battle_if_ready_posts_finish_request(monkeypatch):
    refreshed = SimpleNamespace(serialize=lambda: {'id': 73})

    monkeypatch.setattr(ai_worker, '_reload_conquer_game', lambda _game_id: refreshed)
    monkeypatch.setattr(ai_worker, 'detect_phase', lambda *_args, **_kwargs: 'finish_battle')

    calls = []

    def _fake_post(url, ai_player_id, **kwargs):
        calls.append((url, ai_player_id, kwargs.get('json')))

        class DummyResponse:
            def json(self):
                return {'success': True}

        return DummyResponse()

    monkeypatch.setattr(ai_worker, '_ai_post', _fake_post)

    result = ai_worker._conquer_try_finish_battle_if_ready(
        base='http://example.invalid',
        game_id=73,
        ai_player_id=999,
    )

    assert result is True
    assert calls
    assert calls[0][0].endswith('/games/finish_battle')
    assert calls[0][2]['game_id'] == 73


def test_conquer_ai_loop_processes_pending_retrigger_on_exit(app, db, monkeypatch):
    game, ai_player = _create_game_with_ai(db)
    game.mode = 'conquer'
    db.session.commit()

    monkeypatch.setattr(ai_worker.time, 'sleep', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ai_worker, 'detect_phase', lambda *_args, **_kwargs: None)

    trigger_calls = []
    monkeypatch.setattr(
        ai_worker,
        'trigger_ai_if_needed',
        lambda game_id, app=None: trigger_calls.append(game_id),
    )

    with ai_worker._active_games_lock:
        ai_worker._active_games.add(game.id)
        ai_worker._pending_retrigger.add(game.id)

    ai_worker._conquer_ai_loop(app, game.id, ai_player.id)

    assert trigger_calls == [game.id]
    with ai_worker._active_games_lock:
        assert game.id not in ai_worker._active_games
        assert game.id not in ai_worker._pending_retrigger


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


def test_ask_llm_for_action_uses_planner_recommendation_fallback(monkeypatch):
    class StubClient:
        def choose_action(self, _system_prompt, _user_prompt, temperature=0.4):
            return '{"action": 999}'

    monkeypatch.setattr(ai_worker, '_get_llm_client', lambda: StubClient())
    monkeypatch.setattr(ai_worker, 'serialize_game_for_llm', lambda *_args, **_kwargs: 'state')
    monkeypatch.setattr(ai_worker, 'format_actions_for_llm', lambda _actions: 'actions')
    monkeypatch.setattr(
        ai_worker,
        'generate_strategy_plans',
        lambda *_args, **_kwargs: [{'plan_id': 1, 'seed_action_id': 2, 'total_score': 5.0, 'turn_steps': ['a', 'b']}],
    )
    monkeypatch.setattr(ai_worker, 'format_strategy_plans_for_prompt', lambda _plans: 'PLANS')
    monkeypatch.setattr(ai_worker, 'recommended_action_id', lambda _plans: 2)

    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_ENABLED', True)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_USE_RECOMMENDATION_FALLBACK', True)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_MAX_PLANS', 5)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_MAX_MAIN_DRAWS_PER_TURN', 2)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_MAX_SIDE_DRAWS_PER_TURN', 1)

    actions = [
        {'id': 1, 'type': 'change_cards', 'description': 'swap low cards', 'params': {}},
        {'id': 2, 'type': 'advance_figure', 'description': 'advance strongest', 'params': {'figure_id': 7}},
    ]

    game_dict = {
        'id': 5,
        'players': [
            {'id': 1, 'turns_left': 2, 'main_hand': [], 'side_hand': [], 'figures': []},
            {'id': 2, 'turns_left': 2, 'main_hand': [], 'side_hand': [], 'figures': []},
        ],
    }
    chosen = ai_worker._ask_llm_for_action(game_dict, ai_player_id=1, phase='normal_turn', actions=actions)

    assert chosen['id'] == 2


def test_ask_llm_for_action_appends_strategy_plans_to_prompt(monkeypatch):
    captured = {'prompt': ''}

    class StubClient:
        def choose_action(self, _system_prompt, user_prompt, temperature=0.4):
            captured['prompt'] = user_prompt
            return '{"action": 1}'

    monkeypatch.setattr(ai_worker, '_get_llm_client', lambda: StubClient())
    monkeypatch.setattr(ai_worker, 'serialize_game_for_llm', lambda *_args, **_kwargs: 'state')
    monkeypatch.setattr(ai_worker, 'format_actions_for_llm', lambda _actions: 'actions')
    monkeypatch.setattr(
        ai_worker,
        'generate_strategy_plans',
        lambda *_args, **_kwargs: [{'plan_id': 1, 'seed_action_id': 1, 'total_score': 1.0, 'turn_steps': ['now']}],
    )
    monkeypatch.setattr(ai_worker, 'format_strategy_plans_for_prompt', lambda _plans: '\n=== STRATEGY PLAN CANDIDATES ===\nPLAN 1')

    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_ENABLED', True)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_USE_RECOMMENDATION_FALLBACK', True)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_MAX_PLANS', 5)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_MAX_MAIN_DRAWS_PER_TURN', 2)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_MAX_SIDE_DRAWS_PER_TURN', 1)

    actions = [
        {'id': 1, 'type': 'change_cards', 'description': 'swap low cards', 'params': {}},
    ]

    game_dict = {
        'id': 6,
        'players': [
            {'id': 1, 'turns_left': 2, 'main_hand': [], 'side_hand': [], 'figures': []},
            {'id': 2, 'turns_left': 2, 'main_hand': [], 'side_hand': [], 'figures': []},
        ],
    }
    ai_worker._ask_llm_for_action(game_dict, ai_player_id=1, phase='normal_turn', actions=actions)

    assert 'STRATEGY PLAN CANDIDATES' in captured['prompt']


def test_ask_llm_for_action_shadow_mode_does_not_append_strategy_plans_to_prompt(monkeypatch):
    captured = {'prompt': ''}

    class StubClient:
        def choose_action(self, _system_prompt, user_prompt, temperature=0.4):
            captured['prompt'] = user_prompt
            return '{"action": 1}'

    monkeypatch.setattr(ai_worker, '_get_llm_client', lambda: StubClient())
    monkeypatch.setattr(ai_worker, 'serialize_game_for_llm', lambda *_args, **_kwargs: 'state')
    monkeypatch.setattr(ai_worker, 'format_actions_for_llm', lambda _actions: 'actions')
    monkeypatch.setattr(
        ai_worker,
        'generate_strategy_plans',
        lambda *_args, **_kwargs: [{'plan_id': 1, 'seed_action_id': 1, 'total_score': 1.0, 'turn_steps': ['now']}],
    )
    monkeypatch.setattr(ai_worker, 'format_strategy_plans_for_prompt', lambda _plans: '\n=== STRATEGY PLAN CANDIDATES ===\nPLAN 1')

    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_ENABLED', True)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_SHADOW_MODE', True)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_USE_RECOMMENDATION_FALLBACK', True)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_MAX_PLANS', 5)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_MAX_MAIN_DRAWS_PER_TURN', 2)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_MAX_SIDE_DRAWS_PER_TURN', 1)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_RUNTIME_WARNING_MS', 9999.0)

    actions = [
        {'id': 1, 'type': 'change_cards', 'description': 'swap low cards', 'params': {}},
    ]

    game_dict = {
        'id': 7,
        'players': [
            {'id': 1, 'turns_left': 2, 'main_hand': [], 'side_hand': [], 'figures': []},
            {'id': 2, 'turns_left': 2, 'main_hand': [], 'side_hand': [], 'figures': []},
        ],
    }
    ai_worker._ask_llm_for_action(game_dict, ai_player_id=1, phase='normal_turn', actions=actions)

    assert 'STRATEGY PLAN CANDIDATES' not in captured['prompt']


def test_ask_llm_for_action_shadow_mode_invalid_action_uses_first_not_planner(monkeypatch):
    class StubClient:
        def choose_action(self, _system_prompt, _user_prompt, temperature=0.4):
            return '{"action": 999}'

    monkeypatch.setattr(ai_worker, '_get_llm_client', lambda: StubClient())
    monkeypatch.setattr(ai_worker, 'serialize_game_for_llm', lambda *_args, **_kwargs: 'state')
    monkeypatch.setattr(ai_worker, 'format_actions_for_llm', lambda _actions: 'actions')
    monkeypatch.setattr(
        ai_worker,
        'generate_strategy_plans',
        lambda *_args, **_kwargs: [{'plan_id': 1, 'seed_action_id': 2, 'total_score': 5.0, 'turn_steps': ['a', 'b']}],
    )
    monkeypatch.setattr(ai_worker, 'recommended_action_id', lambda _plans: 2)

    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_ENABLED', True)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_SHADOW_MODE', True)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_USE_RECOMMENDATION_FALLBACK', True)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_MAX_PLANS', 5)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_MAX_MAIN_DRAWS_PER_TURN', 2)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_MAX_SIDE_DRAWS_PER_TURN', 1)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_RUNTIME_WARNING_MS', 9999.0)

    actions = [
        {'id': 1, 'type': 'change_cards', 'description': 'swap low cards', 'params': {}},
        {'id': 2, 'type': 'advance_figure', 'description': 'advance strongest', 'params': {'figure_id': 7}},
    ]

    game_dict = {
        'id': 8,
        'players': [
            {'id': 1, 'turns_left': 2, 'main_hand': [], 'side_hand': [], 'figures': []},
            {'id': 2, 'turns_left': 2, 'main_hand': [], 'side_hand': [], 'figures': []},
        ],
    }
    chosen = ai_worker._ask_llm_for_action(game_dict, ai_player_id=1, phase='normal_turn', actions=actions)

    assert chosen['id'] == 1


def test_ask_llm_for_action_logs_runtime_warning_when_planner_slow(monkeypatch, caplog):
    class StubClient:
        def choose_action(self, _system_prompt, _user_prompt, temperature=0.4):
            return '{"action": 1}'

    monkeypatch.setattr(ai_worker, '_get_llm_client', lambda: StubClient())
    monkeypatch.setattr(ai_worker, 'serialize_game_for_llm', lambda *_args, **_kwargs: 'state')
    monkeypatch.setattr(ai_worker, 'format_actions_for_llm', lambda _actions: 'actions')
    monkeypatch.setattr(
        ai_worker,
        'generate_strategy_plans',
        lambda *_args, **_kwargs: [{'plan_id': 1, 'seed_action_id': 1, 'total_score': 1.0, 'turn_steps': ['now']}],
    )
    monkeypatch.setattr(ai_worker, 'format_strategy_plans_for_prompt', lambda _plans: 'PLANS')

    perf_values = iter([100.0, 100.25])
    monkeypatch.setattr(ai_worker.time, 'perf_counter', lambda: next(perf_values))

    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_ENABLED', True)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_SHADOW_MODE', False)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_USE_RECOMMENDATION_FALLBACK', True)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_MAX_PLANS', 5)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_MAX_MAIN_DRAWS_PER_TURN', 2)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_MAX_SIDE_DRAWS_PER_TURN', 1)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_RUNTIME_WARNING_MS', 120.0)

    actions = [
        {'id': 1, 'type': 'change_cards', 'description': 'swap low cards', 'params': {}},
    ]

    game_dict = {
        'id': 9,
        'players': [
            {'id': 1, 'turns_left': 2, 'main_hand': [], 'side_hand': [], 'figures': []},
            {'id': 2, 'turns_left': 2, 'main_hand': [], 'side_hand': [], 'figures': []},
        ],
    }

    with caplog.at_level('WARNING'):
        ai_worker._ask_llm_for_action(game_dict, ai_player_id=1, phase='normal_turn', actions=actions)

    assert 'runtime exceeded warning threshold' in caplog.text


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


def test_get_ai_debug_snapshot_returns_recent_notes_and_events():
    game_id = 321

    with ai_worker._game_strategies_lock:
        ai_worker._game_strategies[game_id] = ['n1', 'n2', 'n3']
    with ai_worker._planner_events_lock:
        ai_worker._planner_events[game_id] = [
            {'type': 'planner_generated', 'plans': 4},
            {'type': 'planner_shadow_comparison', 'match': True},
            {'type': 'planner_runtime_warning', 'runtime_ms': 190.0},
        ]

    snapshot = ai_worker.get_ai_debug_snapshot(game_id, max_notes=2, max_events=2)

    assert snapshot['strategy_notes'] == ['n2', 'n3']
    assert len(snapshot['planner_events']) == 2
    assert snapshot['planner_events'][0]['type'] == 'planner_shadow_comparison'
    assert snapshot['planner_events'][1]['type'] == 'planner_runtime_warning'


def test_ask_llm_for_action_records_shadow_comparison_event(monkeypatch):
    class StubClient:
        def choose_action(self, _system_prompt, _user_prompt, temperature=0.4):
            return '{"action": 1}'

    monkeypatch.setattr(ai_worker, '_get_llm_client', lambda: StubClient())
    monkeypatch.setattr(ai_worker, 'serialize_game_for_llm', lambda *_args, **_kwargs: 'state')
    monkeypatch.setattr(ai_worker, 'format_actions_for_llm', lambda _actions: 'actions')
    monkeypatch.setattr(
        ai_worker,
        'generate_strategy_plans',
        lambda *_args, **_kwargs: [{'plan_id': 1, 'seed_action_id': 2, 'total_score': 3.1, 'turn_steps': ['x', 'y']}],
    )
    monkeypatch.setattr(ai_worker, 'recommended_action_id', lambda _plans: 2)

    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_ENABLED', True)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_SHADOW_MODE', True)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_USE_RECOMMENDATION_FALLBACK', True)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_MAX_PLANS', 5)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_MAX_MAIN_DRAWS_PER_TURN', 2)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_MAX_SIDE_DRAWS_PER_TURN', 1)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_RUNTIME_WARNING_MS', 9999.0)

    actions = [
        {'id': 1, 'type': 'change_cards', 'description': 'swap low cards', 'params': {}},
        {'id': 2, 'type': 'advance_figure', 'description': 'advance strongest', 'params': {'figure_id': 7}},
    ]

    game_dict = {
        'id': 77,
        'players': [
            {'id': 1, 'turns_left': 2, 'main_hand': [], 'side_hand': [], 'figures': []},
            {'id': 2, 'turns_left': 2, 'main_hand': [], 'side_hand': [], 'figures': []},
        ],
    }
    ai_worker._ask_llm_for_action(game_dict, ai_player_id=1, phase='normal_turn', actions=actions)

    snapshot = ai_worker.get_ai_debug_snapshot(77, max_notes=5, max_events=20)
    event_types = [e.get('type') for e in snapshot['planner_events']]

    assert 'planner_generated' in event_types
    assert 'planner_shadow_comparison' in event_types


def test_ask_llm_for_action_records_candidate_summaries_and_choice_event(monkeypatch):
    class StubClient:
        def choose_action(self, _system_prompt, _user_prompt, temperature=0.4):
            return '{"action": 2}'

    monkeypatch.setattr(ai_worker, '_get_llm_client', lambda: StubClient())
    monkeypatch.setattr(ai_worker, 'serialize_game_for_llm', lambda *_args, **_kwargs: 'state')
    monkeypatch.setattr(ai_worker, 'format_actions_for_llm', lambda _actions: 'actions')
    monkeypatch.setattr(
        ai_worker,
        'generate_strategy_plans',
        lambda *_args, **_kwargs: [
            {
                'plan_id': 1,
                'seed_action_id': 2,
                'strategy_name': 'Advance Line',
                'total_score': 4.2,
                'feasibility_probability': 0.8,
                'expected_power_diff': 2.0,
                'expected_battle_move_power': 11.0,
                'planned_battle_figure': {'name': 'Djungle Maharaja', 'field': 'castle', 'state': 'already_built', 'power_estimate': 15},
                'likely_opponent_figure': {'name': 'Himalaya Maharaja', 'power_estimate': 10, 'probability': 0.7},
                'planned_battle_moves': [{'rank': 'A', 'suit': 'Diamonds', 'value': 14}],
                'score_breakdown': {'feasibility': 0.8, 'offensive_value': 9.1},
                'turn_steps': ['execute now', 'pressure next'],
                'notes': ['good pressure line'],
            },
            {
                'plan_id': 2,
                'seed_action_id': 1,
                'strategy_name': 'Change Cards Line',
                'total_score': 1.1,
                'feasibility_probability': 0.5,
                'expected_power_diff': 0.2,
                'expected_battle_move_power': 6.0,
                'planned_battle_moves': [{'rank': '9', 'suit': 'Spades', 'value': 9}],
                'turn_steps': ['draw now'],
            },
        ],
    )
    monkeypatch.setattr(ai_worker, 'format_strategy_plans_for_prompt', lambda _plans: 'PLANS')
    monkeypatch.setattr(ai_worker, 'recommended_action_id', lambda _plans: 2)

    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_ENABLED', True)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_SHADOW_MODE', False)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_USE_RECOMMENDATION_FALLBACK', True)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_MAX_PLANS', 5)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_MAX_MAIN_DRAWS_PER_TURN', 2)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_MAX_SIDE_DRAWS_PER_TURN', 1)
    monkeypatch.setattr(ai_worker.settings, 'AI_STRATEGY_PLANNER_RUNTIME_WARNING_MS', 9999.0)

    actions = [
        {'id': 1, 'type': 'change_cards', 'description': 'swap low cards', 'params': {}},
        {'id': 2, 'type': 'advance_figure', 'description': 'advance strongest', 'params': {'figure_id': 7}},
    ]

    game_dict = {
        'id': 78,
        'players': [
            {'id': 1, 'turns_left': 2, 'main_hand': [], 'side_hand': [], 'figures': []},
            {'id': 2, 'turns_left': 2, 'main_hand': [], 'side_hand': [], 'figures': []},
        ],
    }
    chosen = ai_worker._ask_llm_for_action(game_dict, ai_player_id=1, phase='normal_turn', actions=actions)

    assert chosen['id'] == 2

    snapshot = ai_worker.get_ai_debug_snapshot(78, max_notes=5, max_events=20)
    planner_generated = next((e for e in snapshot['planner_events'] if e.get('type') == 'planner_generated'), None)
    planner_choice = next((e for e in snapshot['planner_events'] if e.get('type') == 'planner_choice'), None)

    assert planner_generated is not None
    assert planner_choice is not None
    assert len(planner_generated.get('candidates') or []) == 2
    assert planner_generated['candidates'][0]['seed_action_id'] == 2
    assert planner_generated['candidates'][0]['turn_steps'] == ['execute now', 'pressure next']
    assert planner_generated['candidates'][0]['planned_battle_moves'][0]['rank'] == 'A'
    assert planner_generated['candidates'][0]['planned_battle_figure']['name'] == 'Djungle Maharaja'
    assert planner_choice['recommended_action_id'] == 2
    assert planner_choice['chosen_action_id'] == 2
    assert planner_choice['chosen_matches_recommended'] is True


def test_handle_explain_chat_control_updates_mode_and_depth_without_manual():
    responses = ai_worker.handle_explain_chat_control(
        game_id=901,
        ai_player_id=22,
        human_player_id=11,
        message='explain mode turn depth extensive',
    )

    assert responses
    assert any('cadence=turn, depth=extensive' in msg for msg in responses)

    with ai_worker._ai_chat_lock:
        state = dict(ai_worker._ai_explain_states[901])

    assert state['mode'] == 'turn'
    assert state['depth'] == 'extensive'


def test_handle_explain_chat_control_plain_help_returns_short_manual():
    responses = ai_worker.handle_explain_chat_control(
        game_id=900,
        ai_player_id=22,
        human_player_id=11,
        message='help',
    )

    assert len(responses) == 1
    assert 'AI explain help:' in responses[0]
    assert 'explain mode off/manual/turn/battle' in responses[0]


def test_handle_explain_chat_control_extensive_includes_candidate_sequences():
    with ai_worker._planner_events_lock:
        ai_worker._planner_events[902] = [
            {
                'type': 'planner_generated',
                'candidates': [
                    {
                        'seed_action_id': 3,
                        'action_description': 'advance strongest figure',
                        'total_score': 5.25,
                        'feasibility_probability': 0.81,
                        'expected_power_diff': 2.6,
                        'turn_steps': ['advance military', 'force defender', 'play high move'],
                        'planned_battle_figure': {
                            'name': 'Gorkha Warrior',
                            'field': 'military',
                            'state': 'build_possible_with_probability',
                            'power_estimate': 11,
                        },
                    },
                    {
                        'seed_action_id': 1,
                        'action_description': 'change low cards',
                        'total_score': 2.1,
                        'feasibility_probability': 0.58,
                        'expected_power_diff': 0.8,
                        'turn_steps': ['swap weak cards', 'prepare next turn'],
                    },
                ],
            },
            {
                'type': 'planner_choice',
                'recommended_action_id': 3,
                'chosen_action_id': 3,
                'chosen_matches_recommended': True,
            },
        ]

    responses = ai_worker.handle_explain_chat_control(
        game_id=902,
        ai_player_id=22,
        human_player_id=11,
        message='explain yourself depth extensive',
    )

    assert any('Tactical explain (manual, extensive)' in msg for msg in responses)
    assert any('Candidate 1:' in msg for msg in responses)
    assert any('Candidate 2:' in msg for msg in responses)


def test_maybe_send_ai_chat_turn_explain_mode_sends_once_per_marker(monkeypatch):
    monkeypatch.setattr(ai_worker.settings, 'AI_CHAT_ENABLED', True)
    monkeypatch.setattr(ai_worker.settings, 'AI_CHAT_CHANCE', 0.0)
    monkeypatch.setattr(ai_worker.settings, 'AI_CHAT_MAX_PER_GAME', 10)

    with ai_worker._ai_chat_lock:
        ai_worker._ai_explain_states[903] = {
            'mode': 'turn',
            'depth': 'brief',
            'last_marker': None,
        }

    with ai_worker._planner_events_lock:
        ai_worker._planner_events[903] = [
            {
                'type': 'planner_generated',
                'candidates': [
                    {
                        'seed_action_id': 2,
                        'action_description': 'advance strongest',
                        'total_score': 4.4,
                        'feasibility_probability': 0.77,
                        'expected_power_diff': 1.9,
                        'turn_steps': ['advance castle', 'pressure battle'],
                    }
                ],
            }
        ]

    sent_payloads = []

    class DummyResponse:
        status_code = 200

        def json(self):
            return {'success': True}

    def fake_ai_post(_url, _ai_player_id, **kwargs):
        sent_payloads.append(kwargs.get('json') or {})
        return DummyResponse()

    monkeypatch.setattr(ai_worker, '_ai_post', fake_ai_post)

    game_dict = {
        'id': 903,
        'current_round': 2,
        'turn_player_id': 1,
        'battle_round': 0,
        'players': [
            {'id': 1, 'username': '[AI] Strategos'},
            {'id': 2, 'username': 'human'},
        ],
    }

    ai_worker._maybe_send_ai_chat(
        game_id=903,
        ai_player_id=1,
        game_dict=game_dict,
        phase='normal_turn',
        action={'id': 2, 'type': 'advance_figure', 'description': 'advance strongest figure'},
    )
    first_count = len(sent_payloads)

    ai_worker._maybe_send_ai_chat(
        game_id=903,
        ai_player_id=1,
        game_dict=game_dict,
        phase='normal_turn',
        action={'id': 2, 'type': 'advance_figure', 'description': 'advance strongest figure'},
    )
    second_count = len(sent_payloads)

    assert first_count == 1
    assert second_count == 1
    assert sent_payloads[0]['sender_id'] == 1
    assert sent_payloads[0]['receiver_id'] == 2
    assert 'Tactical explain' in sent_payloads[0]['message']