# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Deterministic integration-style scenarios for AI worker game loop."""

from ai import ai_worker


class _InlineThread:
    """Thread shim that runs target immediately when start() is called."""

    def __init__(self, target=None, args=(), kwargs=None, **_ignored):
        self._target = target
        self._args = args
        self._kwargs = kwargs or {}

    def start(self):
        if self._target:
            self._target(*self._args, **self._kwargs)


def _sequence(values):
    state = {'idx': 0}

    def _next(*_args, **_kwargs):
        i = state['idx']
        state['idx'] += 1
        if i < len(values):
            return values[i]
        return None

    return _next


def _create_game_with_ai(db):
    from models import Game, Player, User
    from werkzeug.security import generate_password_hash

    ai_user = User(
        username='[AI] IntegrationBot',
        password_hash=generate_password_hash('x'),
        is_ai=True,
        gold=9999,
    )
    human_user = User(
        username='integration_human',
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


def _patch_common_loop_controls(monkeypatch):
    monkeypatch.setattr(ai_worker.settings, 'AI_ENABLED', True)
    monkeypatch.setattr(ai_worker.settings, 'AI_THINK_DELAY', 0)
    monkeypatch.setattr(ai_worker.time, 'sleep', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ai_worker.threading, 'Thread', _InlineThread)


def _reset_worker_state():
    with ai_worker._active_games_lock:
        ai_worker._active_games.clear()
        ai_worker._pending_retrigger.clear()
    with ai_worker._ai_player_user_ids_lock:
        ai_worker._ai_player_user_ids.clear()
    with ai_worker._ai_watchdog_lock:
        ai_worker._ai_watchdog_retries.clear()
        ai_worker._ai_watchdog_first_scheduled.clear()


def test_trigger_runs_normal_turn_flow_inline(app, db, monkeypatch):
    _reset_worker_state()
    game, ai_player = _create_game_with_ai(db)
    _patch_common_loop_controls(monkeypatch)

    # trigger check, loop start, post-start-turn, then exit.
    monkeypatch.setattr(
        ai_worker,
        'detect_phase',
        _sequence(['normal_turn', 'normal_turn', 'normal_turn', None, None]),
    )

    start_turn_calls = []
    monkeypatch.setattr(
        ai_worker,
        '_exec_start_turn',
        lambda *_args, **_kwargs: start_turn_calls.append(True) or True,
    )

    monkeypatch.setattr(
        ai_worker,
        'enumerate_actions',
        lambda *_args, **_kwargs: [
            {'id': 1, 'type': 'change_cards', 'description': 'swap', 'params': {}}
        ],
    )

    executed = []
    monkeypatch.setattr(
        ai_worker,
        '_execute_action',
        lambda _app, _gid, _pid, action: executed.append(action['type']) or True,
    )

    ai_worker.trigger_ai_if_needed(game.id, app=app)

    assert len(start_turn_calls) == 1
    assert executed == ['change_cards']
    with ai_worker._active_games_lock:
        assert game.id not in ai_worker._active_games


def test_trigger_uses_duel_strategy_when_multiple_actions(app, db, monkeypatch):
    _reset_worker_state()
    game, _ai_player = _create_game_with_ai(db)
    _patch_common_loop_controls(monkeypatch)

    monkeypatch.setattr(
        ai_worker,
        'detect_phase',
        _sequence(['battle_shop', 'battle_shop', None, None]),
    )

    choices = [
        {'id': 1, 'type': 'buy_battle_move', 'description': 'buy low', 'params': {'card_id': 1}},
        {'id': 2, 'type': 'confirm_battle_moves', 'description': 'confirm', 'params': {}},
    ]
    monkeypatch.setattr(ai_worker, 'enumerate_actions', lambda *_args, **_kwargs: choices)
    monkeypatch.setattr(
        ai_worker.duel_strategy,
        'choose_action',
        lambda *_args, **_kwargs: choices[1],
    )

    executed = []
    monkeypatch.setattr(
        ai_worker,
        '_execute_action',
        lambda _app, _gid, _pid, action: executed.append(action['id']) or True,
    )

    ai_worker.trigger_ai_if_needed(game.id, app=app)

    assert executed == [2]


def test_trigger_battle_shop_confirm_failure_falls_back_to_buy(app, db, monkeypatch):
    _reset_worker_state()
    game, _ai_player = _create_game_with_ai(db)
    _patch_common_loop_controls(monkeypatch)

    monkeypatch.setattr(
        ai_worker,
        'detect_phase',
        _sequence(['battle_shop', 'battle_shop', None, None]),
    )

    actions = [
        {'id': 1, 'type': 'buy_battle_move', 'description': 'buy', 'params': {'card_id': 7}},
        {'id': 2, 'type': 'confirm_battle_moves', 'description': 'confirm', 'params': {}},
    ]
    monkeypatch.setattr(ai_worker, 'enumerate_actions', lambda *_args, **_kwargs: actions)
    monkeypatch.setattr(
        ai_worker.duel_strategy,
        'choose_action',
        lambda *_args, **_kwargs: actions[1],
    )

    attempts = []

    def _exec(_app, _gid, _pid, action):
        attempts.append(action['type'])
        if action['type'] == 'confirm_battle_moves':
            return False
        return True

    monkeypatch.setattr(ai_worker, '_execute_action', _exec)

    ai_worker.trigger_ai_if_needed(game.id, app=app)

    assert attempts == ['confirm_battle_moves', 'buy_battle_move']


def test_trigger_post_battle_pick_phase_invokes_pick_handler(app, db, monkeypatch):
    _reset_worker_state()
    game, ai_player = _create_game_with_ai(db)
    _patch_common_loop_controls(monkeypatch)

    # Mark winner so detect_phase can map to post_battle_pick in our sequence.
    from models import db as model_db
    game.battle_confirmed = True
    game.fold_winner_id = ai_player.id
    model_db.session.commit()

    monkeypatch.setattr(
        ai_worker,
        'detect_phase',
        _sequence(['post_battle_pick', 'post_battle_pick']),
    )

    picked = []
    monkeypatch.setattr(
        ai_worker,
        '_handle_post_battle_pick',
        lambda _app, _gid, _pid: picked.append((_gid, _pid)),
    )

    ai_worker.trigger_ai_if_needed(game.id, app=app)

    assert picked == [(game.id, ai_player.id)]


def test_conquer_loop_battle_round_uses_tactics_hand_rows(app, db, monkeypatch):
    from models import ConquerTactic
    from tests.server.test_conquer_tactics_hand import (
        _force_active_battle,
        _start_player_owned_conquer,
    )

    _reset_worker_state()
    _client, _attacker, _defender, game, attacker_player, defender_player = (
        _start_player_owned_conquer(app, db)
    )
    _force_active_battle(db, game, attacker_player, defender_player)
    game.battle_round = 1
    game.battle_turn_player_id = defender_player.id
    db.session.commit()
    _patch_common_loop_controls(monkeypatch)

    monkeypatch.setattr(
        ai_worker,
        'detect_phase',
        _sequence(['battle_round', None, None]),
    )
    captured = {}

    def _capture_play(_base, game_id, player_id, params):
        captured['game_id'] = game_id
        captured['player_id'] = player_id
        captured['params'] = params
        return True

    def _fail_legacy(*_args, **_kwargs):
        raise AssertionError('tactics-hand conquer loop must use conquer tactic endpoint')

    monkeypatch.setattr(ai_worker, '_exec_play_conquer_tactic', _capture_play)
    monkeypatch.setattr(ai_worker, '_exec_play_battle_move', _fail_legacy)

    ai_worker._conquer_ai_loop(app, game.id, defender_player.id)

    defender_tactic_ids = {
        tactic.id
        for tactic in ConquerTactic.query.filter_by(
            game_id=game.id,
            player_id=defender_player.id,
            status='available',
        )
    }
    assert captured['game_id'] == game.id
    assert captured['player_id'] == defender_player.id
    assert captured['params']['battle_move_id'] in defender_tactic_ids


def test_conquer_loop_first_round_posts_real_tactics_for_both_sides(app, db, monkeypatch):
    from models import ConquerTactic, Player, User
    from tests.server.test_conquer_tactics_hand import (
        _force_active_battle,
        _start_player_owned_conquer,
    )
    from tests.server.test_land_battle import _auth_headers

    _reset_worker_state()
    client, _attacker, _defender, game, attacker_player, defender_player = (
        _start_player_owned_conquer(app, db)
    )
    _force_active_battle(db, game, attacker_player, defender_player)
    monkeypatch.setattr(ai_worker.settings, 'AI_ENABLED', True)
    monkeypatch.setattr(ai_worker.settings, 'AI_THINK_DELAY', 0)
    monkeypatch.setattr(ai_worker.time, 'sleep', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ai_worker, 'trigger_ai_if_needed', lambda *_args, **_kwargs: None)

    monkeypatch.setattr(
        ai_worker,
        'detect_phase',
        _sequence(['battle_round', None, None, 'battle_round', None, None]),
    )

    posted = []

    def _post_conquer_tactic(_base, game_id, player_id, params):
        player = db.session.get(Player, player_id)
        user = db.session.get(User, player.user_id)
        payload = {
            'game_id': game_id,
            'player_id': player_id,
            'tactic_id': params.get('tactic_id') or params.get('battle_move_id'),
        }
        if params.get('call_figure_id'):
            payload['call_figure_id'] = params['call_figure_id']
        resp = client.post(
            '/games/play_conquer_tactic',
            json=payload,
            headers=_auth_headers(app, user),
        )
        data = resp.get_json()
        posted.append((player_id, resp.status_code, data))
        return resp.status_code == 200 and data.get('success') is True

    def _fail_legacy(*_args, **_kwargs):
        raise AssertionError('tactics-hand conquer loop must not post legacy battle moves')

    monkeypatch.setattr(ai_worker, '_exec_play_conquer_tactic', _post_conquer_tactic)
    monkeypatch.setattr(ai_worker, '_exec_play_battle_move', _fail_legacy)

    ai_worker._conquer_ai_loop(app, game.id, attacker_player.id)
    db.session.refresh(game)
    assert game.battle_turn_player_id == defender_player.id
    assert ConquerTactic.query.filter_by(
        game_id=game.id,
        player_id=attacker_player.id,
        status='played',
        played_round=0,
    ).count() == 1

    ai_worker._conquer_ai_loop(app, game.id, defender_player.id)
    db.session.refresh(game)
    assert game.battle_round == 1
    assert game.battle_turn_player_id == game.invader_player_id
    assert ConquerTactic.query.filter_by(
        game_id=game.id,
        player_id=defender_player.id,
        status='played',
        played_round=0,
    ).count() == 1
    assert [item[0] for item in posted] == [attacker_player.id, defender_player.id]


def test_loop_failure_schedules_watchdog_retry_when_ai_still_owns_turn(app, db, monkeypatch):
    _reset_worker_state()
    game, ai_player = _create_game_with_ai(db)
    _patch_common_loop_controls(monkeypatch)

    # trigger check, loop iteration, final unsuccessful-exit phase check.
    monkeypatch.setattr(
        ai_worker,
        'detect_phase',
        _sequence(['battle_shop', 'battle_shop', 'battle_shop']),
    )

    monkeypatch.setattr(
        ai_worker,
        'enumerate_actions',
        lambda *_args, **_kwargs: [
            {'id': 1, 'type': 'unknown_action', 'description': 'force failure', 'params': {}}
        ],
    )
    monkeypatch.setattr(ai_worker, '_execute_action', lambda *_args, **_kwargs: False)

    scheduled = []
    monkeypatch.setattr(
        ai_worker,
        '_schedule_watchdog_retry',
        lambda _app, gid, pid, reason: scheduled.append((gid, pid, reason)),
    )

    ai_worker.trigger_ai_if_needed(game.id, app=app)

    assert scheduled == [(game.id, ai_player.id, 'loop_failure')]


def test_loop_failure_does_not_schedule_watchdog_when_no_actionable_phase(app, db, monkeypatch):
    _reset_worker_state()
    game, ai_player = _create_game_with_ai(db)
    _patch_common_loop_controls(monkeypatch)

    # trigger check, loop iteration, final unsuccessful-exit phase check -> None.
    monkeypatch.setattr(
        ai_worker,
        'detect_phase',
        _sequence(['battle_shop', 'battle_shop', None]),
    )

    monkeypatch.setattr(
        ai_worker,
        'enumerate_actions',
        lambda *_args, **_kwargs: [
            {'id': 1, 'type': 'unknown_action', 'description': 'force failure', 'params': {}}
        ],
    )
    monkeypatch.setattr(ai_worker, '_execute_action', lambda *_args, **_kwargs: False)

    scheduled = []
    monkeypatch.setattr(
        ai_worker,
        '_schedule_watchdog_retry',
        lambda _app, gid, pid, reason: scheduled.append((gid, pid, reason)),
    )

    ai_worker.trigger_ai_if_needed(game.id, app=app)

    assert scheduled == []
