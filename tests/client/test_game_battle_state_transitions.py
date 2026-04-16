# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Regression tests for client battle-ready transition handling."""

import logging


def _mk_game_dict(player_id=113, opponent_id=114):
    return {
        'id': 57,
        'state': 'open',
        'date': '2026-04-16T11:45:00',
        'players': [
            {
                'id': player_id,
                'user_id': 1,
                'username': 'Vader',
                'turns_left': 0,
                'points': 0,
                'is_online': True,
            },
            {
                'id': opponent_id,
                'user_id': 2,
                'username': '[AI] Strategos',
                'turns_left': 0,
                'points': 0,
                'is_online': True,
            },
        ],
        'main_cards': [],
        'side_cards': [],
        'current_round': 3,
        'invader_player_id': player_id,
        'turn_player_id': player_id,
        'ceasefire_active': False,
        'ceasefire_start_turn': None,
        'pending_spell_id': None,
        'battle_modifier': None,
        'waiting_for_counter_player_id': None,
        'advancing_figure_id': None,
        'advancing_figure_id_2': None,
        'advancing_player_id': None,
        'defending_figure_id': None,
        'defending_figure_id_2': None,
        'battle_decisions': None,
        'battle_confirmed': False,
        'battle_moves_confirmed': None,
        'fold_outcome': None,
        'fold_winner_id': None,
        'battle_round': 0,
        'battle_turn_player_id': None,
        'post_battle_drawn_cards': None,
        'last_battle_result': None,
        'winner_player_id': None,
        'finished_at': None,
        'auto_loss_reason': None,
        'auto_loss_detail': None,
        'resting_figure_ids': [],
    }


def _mk_user_dict():
    return {'id': 1, 'username': 'Vader'}


class TestGameBattleStateTransitions:
    def test_poll_transition_resets_battle_ready_after_update_from_dict_clear(self):
        """When update_from_dict clears advance first, the next poll must still reset battle-ready guards."""
        from game.core.game import Game

        game = Game(_mk_game_dict(), _mk_user_dict(), lightweight=True)
        game.game_start_notification_checked = True

        # Simulate prior finished battle state that intentionally blocks stale polls.
        game.battle_ready_shown = True
        game.pending_battle_ready = False

        # Simulate an old battle that was previously seen via polling.
        game._last_polled_advancing = 273

        cleared = _mk_game_dict()
        cleared['advancing_figure_id'] = None
        cleared['defending_figure_id'] = None
        game.update_from_dict(cleared)

        # update_from_dict should not clear battle_ready_shown by itself.
        assert game.battle_ready_shown is True

        # First poll after clear: must detect transition and reopen battle-ready checks.
        game._apply_game_dict(cleared)
        assert game.battle_ready_shown is False
        assert game.pending_battle_ready is False

        # Next poll with both figures set should trigger battle-ready again.
        battle_ready_state = _mk_game_dict()
        battle_ready_state['advancing_figure_id'] = 277
        battle_ready_state['advancing_player_id'] = 113
        battle_ready_state['defending_figure_id'] = 270
        battle_ready_state['turn_player_id'] = 113

        game._apply_game_dict(battle_ready_state)
        assert game.pending_battle_ready is True

    def test_logs_reason_when_battle_ready_is_blocked(self, caplog):
        from game.core.game import Game

        game = Game(_mk_game_dict(), _mk_user_dict(), lightweight=True)
        game.game_start_notification_checked = True

        game.battle_ready_shown = True
        game.pending_battle_ready = False
        game._last_polled_advancing = 277

        blocked = _mk_game_dict()
        blocked['advancing_figure_id'] = 277
        blocked['advancing_player_id'] = 113
        blocked['defending_figure_id'] = 270
        blocked['turn_player_id'] = 113

        with caplog.at_level(logging.WARNING, logger='nk.core.game'):
            game._apply_game_dict(blocked)

        messages = [rec.getMessage() for rec in caplog.records]
        assert any('[BATTLE_READY_BLOCKED]' in msg for msg in messages)
        assert any('battle_ready_shown' in msg for msg in messages)
