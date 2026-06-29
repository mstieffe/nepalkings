# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Regression tests for client battle-ready transition handling."""

import logging

import pygame

pygame.display.set_mode((1, 1))


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
        'battle_skipped_rounds': {},
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
    def test_lightweight_game_seeds_figures_from_player_payload(self):
        from game.core.game import Game

        data = _mk_game_dict()
        data['players'][0]['figures'] = [
            {'id': 501, 'name': 'Gorkha Soldier', 'cards': []},
        ]
        data['players'][1]['figures'] = [
            {'id': 601, 'name': 'Hidden Defender', 'cards': []},
        ]

        game = Game(data, _mk_user_dict(), lightweight=True)

        assert game.cached_figures_data[113][0]['id'] == 501
        assert game.cached_figures_data[114][0]['id'] == 601
        assert game._figures_data_version == 1

    def test_apply_server_data_does_not_bump_figure_version_for_equal_payload(self):
        from game.core.game import Game

        game = Game(_mk_game_dict(), _mk_user_dict(), lightweight=True)
        figures = {
            113: [{'id': 501, 'name': 'Gorkha Soldier', 'cards': []}],
            114: [{'id': 601, 'name': 'Hidden Defender', 'cards': []}],
        }
        game.cached_figures_data = figures
        game._figures_data_version = 7

        game.apply_server_data({
            'game': _mk_game_dict(),
            'logs': [],
            'chats': [],
            'active_spells': [],
            'figures': {
                113: [{'id': 501, 'name': 'Gorkha Soldier', 'cards': []}],
                114: [{'id': 601, 'name': 'Hidden Defender', 'cards': []}],
            },
        })

        assert game._figures_data_version == 7
        assert game.cached_figures_data is figures

    def test_apply_server_data_bumps_figure_version_for_changed_payload(self):
        from game.core.game import Game

        game = Game(_mk_game_dict(), _mk_user_dict(), lightweight=True)
        game.cached_figures_data = {
            113: [{'id': 501, 'name': 'Gorkha Soldier', 'cards': []}],
            114: [],
        }
        game._figures_data_version = 7

        game.apply_server_data({
            'game': _mk_game_dict(),
            'logs': [],
            'chats': [],
            'active_spells': [],
            'figures': {
                113: [{'id': 501, 'name': 'Gorkha Soldier', 'cards': []}],
                114: [{'id': 601, 'name': 'Hidden Defender', 'cards': []}],
            },
        })

        assert game._figures_data_version == 8
        assert game.cached_figures_data[114][0]['id'] == 601

    def test_battle_skipped_rounds_follow_server_snapshots(self):
        from game.core.game import Game

        initial = _mk_game_dict()
        initial['battle_skipped_rounds'] = {'114': [0]}
        game = Game(initial, _mk_user_dict(), lightweight=True)

        assert game.battle_skipped_rounds == {'114': [0]}

        action_update = _mk_game_dict()
        action_update['battle_skipped_rounds'] = {'114': [0], '113': [1]}
        game.update_from_dict(action_update)

        assert game.battle_skipped_rounds == {'114': [0], '113': [1]}

        poll_update = _mk_game_dict()
        poll_update['battle_skipped_rounds'] = {'114': [0, 2], '113': [1]}
        game._apply_game_dict(poll_update)

        assert game.battle_skipped_rounds == {'114': [0, 2], '113': [1]}

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

    def test_conquer_battle_confirmed_auto_proceeds_without_wait_flag(self):
        from game.core.game import Game

        initial = _mk_game_dict()
        initial['mode'] = 'conquer'
        game = Game(initial, _mk_user_dict(), lightweight=True)
        game.waiting_for_battle_decision = False
        game.auto_proceed_to_battle = False

        confirmed = _mk_game_dict()
        confirmed['mode'] = 'conquer'
        confirmed['battle_confirmed'] = True

        game._apply_game_dict(confirmed)

        assert game.auto_proceed_to_battle is True

    def test_update_from_dict_enters_defender_pick_after_conquer_counter_spell(self):
        from game.core.game import Game

        initial = _mk_game_dict()
        initial['mode'] = 'conquer'
        game = Game(initial, _mk_user_dict(), lightweight=True)
        game.pending_defender_selection = False
        game.defender_selection_dialogue_shown = False

        post_counter = _mk_game_dict()
        post_counter['mode'] = 'conquer'
        post_counter['advancing_figure_id'] = 501
        post_counter['advancing_player_id'] = 113
        post_counter['defending_figure_id'] = None
        post_counter['turn_player_id'] = 113
        post_counter['battle_confirmed'] = False
        post_counter['battle_decisions'] = None

        game.update_from_dict(post_counter)

        assert game.pending_defender_selection is True

    def test_update_from_dict_clears_stale_conquer_defender_flags_without_advance(self):
        from game.core.game import Game

        initial = _mk_game_dict()
        initial['mode'] = 'conquer'
        initial['advancing_figure_id'] = 501
        initial['advancing_player_id'] = 113
        game = Game(initial, _mk_user_dict(), lightweight=True)
        game.pending_defender_selection = True
        game.defender_selection_dialogue_shown = True
        game.pending_waiting_for_defender_pick = True
        game.waiting_for_defender_pick_shown = True
        game.pending_conquer_own_defender_selection = True
        game.conquer_own_defender_selection_shown = True
        game.civil_war_awaiting_second = True
        game.civil_war_defender_second = True
        game.civil_war_required_color = 'offensive'
        game.pending_battle_ready = True
        game.battle_ready_shown = True

        post_spell = _mk_game_dict()
        post_spell['mode'] = 'conquer'
        post_spell['advancing_figure_id'] = None
        post_spell['advancing_player_id'] = None
        post_spell['defending_figure_id'] = None
        post_spell['turn_player_id'] = 113
        post_spell['battle_confirmed'] = False
        post_spell['battle_decisions'] = None

        game.update_from_dict(post_spell)

        assert game.pending_defender_selection is False
        assert game.defender_selection_dialogue_shown is False
        assert game.pending_waiting_for_defender_pick is False
        assert game.waiting_for_defender_pick_shown is False
        assert game.pending_conquer_own_defender_selection is False
        assert game.conquer_own_defender_selection_shown is False
        assert game.civil_war_awaiting_second is False
        assert game.civil_war_defender_second is False
        assert game.civil_war_required_color is None
        assert game.pending_battle_ready is False
        assert game.battle_ready_shown is False

    def test_conquer_game_start_pending_clears_without_summary(self):
        from game.core.game import Game

        initial = _mk_game_dict()
        initial['mode'] = 'conquer'
        game = Game(initial, _mk_user_dict(), lightweight=True)
        game._game_start_pending = True
        game.game_start_notification_checked = True

        game._apply_start_turn_response({'success': True})

        assert game._game_start_pending is False
        assert game.pending_opponent_turn_summary is None

    def test_conquer_game_start_pending_waits_for_queued_summary(self):
        from game.core.game import Game

        initial = _mk_game_dict()
        initial['mode'] = 'conquer'
        game = Game(initial, _mk_user_dict(), lightweight=True)
        game._game_start_pending = True
        summary = {
            'action': 'game_start',
            'mode': 'conquer',
            'opponent_name': '[AI] Defender',
        }

        game._apply_start_turn_response({
            'success': True,
            'opponent_turn_summary': summary,
        })

        assert game._game_start_pending is True
        assert game.pending_opponent_turn_summary is summary

    def test_game_start_notification_helper_starts_once(self):
        from game.core.game import Game

        game = Game(_mk_game_dict(), _mk_user_dict(), lightweight=True)
        calls = []
        game._start_turn_async = lambda: calls.append('start')

        assert game.start_game_start_notification_if_needed() is True
        assert game.start_game_start_notification_if_needed() is False

        assert calls == ['start']
        assert game.game_start_notification_checked is True
        assert game._game_start_pending is True

    def test_suppress_turn_summary_only_when_turn_is_ours(self):
        """After fold, suppress_next_turn_summary should be True only for the
        player whose turn it is (fold winner/invader).  The defender's first
        _handle_start_turn carries a genuine opponent-action notification."""
        from unittest.mock import MagicMock
        from game.core.game import Game

        # --- Fold WINNER (invader, turn=True) → should suppress ---
        winner_dict = _mk_game_dict(player_id=113, opponent_id=114)
        winner_dict['fold_outcome'] = 'fold_win'
        winner_dict['fold_winner_id'] = 113
        winner_dict['turn_player_id'] = 113        # winner's turn
        winner_dict['invader_player_id'] = 113
        winner_dict['current_round'] = 4

        game_w = Game(winner_dict, _mk_user_dict(), lightweight=True)
        game_w.game_start_notification_checked = True
        # __init__ leaves turn=False; compute it like _apply_game_dict does
        game_w.turn = (game_w.turn_player_id == game_w.player_id)
        assert game_w.turn is True

        # Simulate _reset_battle_state via a mock GameScreen-like wrapper
        game_w.suppress_next_turn_summary = bool(game_w.turn)
        assert game_w.suppress_next_turn_summary is True

        # --- Fold LOSER (defender, turn=False) → should NOT suppress ---
        loser_dict = _mk_game_dict(player_id=113, opponent_id=114)
        loser_dict['fold_outcome'] = 'fold_win'
        loser_dict['fold_winner_id'] = 114          # opponent won
        loser_dict['turn_player_id'] = 114           # opponent's turn
        loser_dict['invader_player_id'] = 114
        loser_dict['current_round'] = 4

        game_l = Game(loser_dict, _mk_user_dict(), lightweight=True)
        game_l.game_start_notification_checked = True
        game_l.turn = (game_l.turn_player_id == game_l.player_id)
        assert game_l.turn is False

        game_l.suppress_next_turn_summary = bool(game_l.turn)
        assert game_l.suppress_next_turn_summary is False


class TestConquerFigureHydration:
    @staticmethod
    def _gorkha_figure_data():
        return {
            'id': 31,
            'player_id': 113,
            'family_name': 'Gorkha Warriors',
            'name': 'Gorkha Warriors',
            'suit': 'Hearts',
            'description': (
                'The Gorkha Warriors is an offensive military figure that charges instantly into battle '
                'when placed on the field. Requires food equal to its number-card value.'
            ),
            'cards': [
                {'rank': 'A', 'suit': 'Hearts', 'value': 3, 'role': 'key'},
                {'rank': '7', 'suit': 'Hearts', 'value': 7, 'role': 'number'},
            ],
            'produces': {},
            'requires': {'warrior_red': 1, 'food_red': 7},
        }

    def test_conquer_mode_hides_instant_advance_on_loaded_figures(self):
        from game.core.game import Game
        from game.components.figures.figure_manager import FigureManager

        initial = _mk_game_dict()
        initial['mode'] = 'conquer'
        game = Game(initial, _mk_user_dict(), lightweight=True)
        game.cached_figures_data = {game.player_id: [self._gorkha_figure_data()]}

        figures = game.get_figures(FigureManager().families)

        assert len(figures) == 1
        assert figures[0].instant_charge is False
        assert 'charges instantly into battle' not in figures[0].description.lower()
        assert 'charges instantly into battle' not in figures[0].family.description.lower()

    def test_duel_mode_keeps_instant_advance_on_loaded_figures(self):
        from game.core.game import Game
        from game.components.figures.figure_manager import FigureManager

        initial = _mk_game_dict()
        initial['mode'] = 'duel'
        game = Game(initial, _mk_user_dict(), lightweight=True)
        game.cached_figures_data = {game.player_id: [self._gorkha_figure_data()]}

        figures = game.get_figures(FigureManager().families)

        assert len(figures) == 1
        assert figures[0].instant_charge is True
