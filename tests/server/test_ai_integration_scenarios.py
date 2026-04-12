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
    monkeypatch.setattr(ai_worker.settings, 'AI_OPENAI_API_KEY', 'test-key')
    monkeypatch.setattr(ai_worker.settings, 'AI_THINK_DELAY', 0)
    monkeypatch.setattr(ai_worker.time, 'sleep', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(ai_worker.threading, 'Thread', _InlineThread)
    monkeypatch.setattr(ai_worker, '_maybe_send_ai_chat', lambda *_args, **_kwargs: None)


def _reset_worker_state():
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


def test_trigger_uses_llm_choice_when_multiple_actions(app, db, monkeypatch):
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
    monkeypatch.setattr(ai_worker, '_ask_llm_for_action', lambda *_args, **_kwargs: choices[1])

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
    monkeypatch.setattr(ai_worker, '_ask_llm_for_action', lambda *_args, **_kwargs: actions[1])

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
