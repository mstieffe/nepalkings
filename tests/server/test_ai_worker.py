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
        ai_worker._ai_watchdog_first_scheduled.clear()
    with ai_worker._planner_events_lock:
        ai_worker._planner_events.clear()

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
        ai_worker._ai_watchdog_first_scheduled.clear()
    with ai_worker._planner_events_lock:
        ai_worker._planner_events.clear()


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


def test_conquer_play_battle_round_tactics_hand_uses_conquer_tactic_endpoint(monkeypatch):
    game = SimpleNamespace(id=52, battle_round=1, conquer_move_model='tactics_hand')
    tactic = SimpleNamespace(id=302, family_name='Call Villager', value=1)
    move_infos = [
        {'move': tactic, 'effective_value': 8, 'call_figure_id': 777},
    ]

    monkeypatch.setattr(ai_worker, '_get_conquer_auto_gamble_settings', lambda *_args, **_kwargs: (False, 10))
    monkeypatch.setattr(ai_worker, '_conquer_collect_move_infos', lambda *_args, **_kwargs: (move_infos, []))
    monkeypatch.setattr(ai_worker, '_conquer_opponent_move_value_for_round', lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(ai_worker, '_conquer_opponent_played_block_for_round', lambda *_args, **_kwargs: False)

    captured = {}

    def _capture_play(_base, _game_id, _player_id, params):
        captured.update(params)
        return True

    def _fail_legacy_play(*_args, **_kwargs):
        raise AssertionError('tactics-hand AI must not call the legacy battle move endpoint')

    monkeypatch.setattr(ai_worker, '_exec_play_conquer_tactic', _capture_play)
    monkeypatch.setattr(ai_worker, '_exec_play_battle_move', _fail_legacy_play)

    assert ai_worker._conquer_play_battle_round(
        'http://example.invalid', game, ai_player_id=999) is True
    assert captured == {'battle_move_id': 302, 'call_figure_id': 777}


def test_conquer_play_battle_round_tactics_hand_auto_gambles_conquer_tactic(monkeypatch):
    game = SimpleNamespace(id=53, battle_round=1, conquer_move_model='tactics_hand')
    weak_tactic = SimpleNamespace(id=401, family_name='Dagger', value=7, suit='Hearts')
    playable_tactic = SimpleNamespace(id=402, family_name='Dagger', value=10, suit='Clubs')
    collect_results = iter([
        ([{'move': weak_tactic, 'effective_value': 7, 'call_figure_id': None}], []),
        ([{'move': playable_tactic, 'effective_value': 10, 'call_figure_id': None}], []),
    ])

    monkeypatch.setattr(ai_worker, '_get_conquer_auto_gamble_settings', lambda *_args, **_kwargs: (True, 10))
    monkeypatch.setattr(ai_worker, '_conquer_collect_move_infos', lambda *_args, **_kwargs: next(collect_results))
    monkeypatch.setattr(ai_worker, '_reload_conquer_game', lambda _game_id: game)
    monkeypatch.setattr(ai_worker, '_conquer_opponent_move_value_for_round', lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(ai_worker, '_conquer_opponent_played_block_for_round', lambda *_args, **_kwargs: False)

    captured = {'gambled': None, 'played': None}

    def _capture_gamble(_base, _game_id, _player_id, params):
        captured['gambled'] = params
        return True

    def _capture_play(_base, _game_id, _player_id, params):
        captured['played'] = params
        return True

    def _fail_legacy(*_args, **_kwargs):
        raise AssertionError('tactics-hand AI must use conquer tactic endpoints')

    monkeypatch.setattr(ai_worker, '_exec_gamble_conquer_tactic', _capture_gamble)
    monkeypatch.setattr(ai_worker, '_exec_play_conquer_tactic', _capture_play)
    monkeypatch.setattr(ai_worker, '_exec_gamble_battle_move', _fail_legacy)
    monkeypatch.setattr(ai_worker, '_exec_play_battle_move', _fail_legacy)

    assert ai_worker._conquer_play_battle_round(
        'http://example.invalid', game, ai_player_id=999) is True
    assert captured['gambled'] == {'battle_move_id': 401, 'tactic_id': 401}
    assert captured['played'] == {'battle_move_id': 402}


def test_conquer_play_battle_round_tactics_hand_auto_combines_conquer_tactics(monkeypatch):
    game = SimpleNamespace(id=54, battle_round=1, conquer_move_model='tactics_hand')
    dagger_a = SimpleNamespace(id=501, family_name='Dagger', value=7, suit='Spades')
    dagger_b = SimpleNamespace(id=502, family_name='Dagger', value=8, suit='Clubs')
    combined = SimpleNamespace(id=599, family_name='Double Dagger', value=15, suit='Spades')
    collect_results = iter([
        ([
            {'move': dagger_a, 'effective_value': 7, 'call_figure_id': None},
            {'move': dagger_b, 'effective_value': 8, 'call_figure_id': None},
        ], []),
        ([{'move': combined, 'effective_value': 15, 'call_figure_id': None}], []),
    ])

    monkeypatch.setattr(ai_worker, '_get_conquer_auto_gamble_settings', lambda *_args, **_kwargs: (True, 1))
    monkeypatch.setattr(ai_worker, '_conquer_collect_move_infos', lambda *_args, **_kwargs: next(collect_results))
    monkeypatch.setattr(ai_worker, '_reload_conquer_game', lambda _game_id: game)
    monkeypatch.setattr(ai_worker, '_conquer_opponent_move_value_for_round', lambda *_args, **_kwargs: 0)
    monkeypatch.setattr(ai_worker, '_conquer_opponent_played_block_for_round', lambda *_args, **_kwargs: False)

    captured = {'combined': None, 'played': None}

    def _capture_combine(_base, _game_id, _player_id, params):
        captured['combined'] = params
        return True

    def _capture_play(_base, _game_id, _player_id, params):
        captured['played'] = params
        return True

    def _fail_legacy(*_args, **_kwargs):
        raise AssertionError('tactics-hand AI must use conquer tactic endpoints')

    monkeypatch.setattr(ai_worker, '_exec_combine_conquer_tactics', _capture_combine)
    monkeypatch.setattr(ai_worker, '_exec_play_conquer_tactic', _capture_play)
    monkeypatch.setattr(ai_worker, '_exec_combine_battle_moves', _fail_legacy)
    monkeypatch.setattr(ai_worker, '_exec_play_battle_move', _fail_legacy)

    assert ai_worker._conquer_play_battle_round(
        'http://example.invalid', game, ai_player_id=999) is True
    assert captured['combined'] == {'move_id_a': 501, 'move_id_b': 502}
    assert captured['played'] == {'battle_move_id': 599}


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


def test_conquer_skip_battle_turn_with_fallback_uses_conquer_tactic_endpoint(monkeypatch):
    move = SimpleNamespace(id=405, family_name='Dagger', value=9)
    game = SimpleNamespace(id=73, battle_round=2, conquer_move_model='tactics_hand')
    refreshed = SimpleNamespace(
        id=73,
        battle_round=2,
        conquer_move_model='tactics_hand',
        serialize=lambda: {'id': 73},
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

    def _fail_legacy_play(*_args, **_kwargs):
        raise AssertionError('tactics-hand fallback must not call legacy battle move endpoint')

    monkeypatch.setattr(ai_worker, '_exec_play_conquer_tactic', _capture_play)
    monkeypatch.setattr(ai_worker, '_exec_play_battle_move', _fail_legacy_play)

    result = ai_worker._conquer_skip_battle_turn_with_fallback(
        'http://example.invalid', game, ai_player_id=999, auto_enabled=False)

    assert result is True
    assert captured['battle_move_id'] == 405


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


def test_trigger_ai_if_needed_marks_pending_retrigger_when_game_already_active(app, db, monkeypatch):
    game, ai_player = _create_game_with_ai(db)

    monkeypatch.setattr(ai_worker.settings, 'AI_ENABLED', True)
    monkeypatch.setattr(ai_worker, 'detect_phase', lambda *_args, **_kwargs: 'normal_turn')

    with ai_worker._active_games_lock:
        ai_worker._active_games.add(game.id)

    ai_worker.trigger_ai_if_needed(game.id, app=app)

    with ai_worker._active_games_lock:
        assert game.id in ai_worker._pending_retrigger


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


def test_get_ai_debug_snapshot_returns_recent_planner_events():
    game_id = 321

    with ai_worker._planner_events_lock:
        ai_worker._planner_events[game_id] = [
            {'type': 'planner_generated', 'plans': 4},
            {'type': 'planner_runtime_warning', 'runtime_ms': 190.0},
            {'type': 'planner_failure', 'phase': 'normal_turn'},
        ]

    snapshot = ai_worker.get_ai_debug_snapshot(game_id, max_events=2)

    assert 'strategy_notes' not in snapshot
    assert len(snapshot['planner_events']) == 2
    assert snapshot['planner_events'][0]['type'] == 'planner_runtime_warning'
    assert snapshot['planner_events'][1]['type'] == 'planner_failure'