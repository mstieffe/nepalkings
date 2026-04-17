# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Unit tests for DefenceScreen logic (Phase 12)."""
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def _make_state():
    state = SimpleNamespace()
    state.screen = 'defence'
    state.defence_land_id = 7
    state.game = MagicMock()
    return state


def _make_config(**overrides):
    cfg = {
        'figures': [],
        'battle_moves': [],
        'battle_modifier': None,
        'battle_figure_id': None,
        'battle_figure_id_2': None,
        'spell_name': None,
        'spell_card_ids': None,
        'spell_target_figure_id': None,
        'auto_gamble': False,
    }
    cfg.update(overrides)
    return cfg


class TestDefenceScreenInit:

    def test_initial_state(self):
        from game.screens.defence_screen import DefenceScreen
        state = _make_state()
        screen = DefenceScreen(state)
        assert screen._land_id is None
        assert screen._config is None
        assert screen._loading is False

    def test_picks_up_land_id_from_state(self):
        from game.screens.defence_screen import DefenceScreen
        state = _make_state()
        screen = DefenceScreen(state)
        screen.update([])
        assert screen._land_id == 7


class TestDefenceReadiness:

    def _screen_with_config(self, **kw):
        from game.screens.defence_screen import DefenceScreen
        state = _make_state()
        screen = DefenceScreen(state)
        screen._config = _make_config(**kw)
        return screen

    def test_not_ready_when_empty(self):
        screen = self._screen_with_config()
        assert screen._is_defence_ready() is False

    def test_not_ready_without_moves(self):
        figs = [{'id': 1, 'has_deficit': False, 'field': 'castle'}]
        screen = self._screen_with_config(figures=figs, battle_figure_id=1)
        assert screen._is_defence_ready() is False

    def test_not_ready_without_figures(self):
        moves = [{'id': i, 'round_index': i} for i in range(3)]
        screen = self._screen_with_config(battle_moves=moves, auto_gamble=True)
        assert screen._is_defence_ready() is False

    def test_not_ready_without_strategy(self):
        """Has figures + moves but no battle fig, spell, or auto-gamble."""
        figs = [{'id': 1, 'has_deficit': False, 'field': 'castle'}]
        moves = [{'id': i, 'round_index': i} for i in range(3)]
        screen = self._screen_with_config(figures=figs, battle_moves=moves)
        assert screen._is_defence_ready() is False

    def test_ready_with_battle_figure(self):
        figs = [{'id': 1, 'has_deficit': False, 'field': 'castle'}]
        moves = [{'id': i, 'round_index': i} for i in range(3)]
        screen = self._screen_with_config(
            figures=figs, battle_moves=moves, battle_figure_id=1)
        assert screen._is_defence_ready() is True

    def test_ready_with_spell(self):
        figs = [{'id': 1, 'has_deficit': False, 'field': 'castle'}]
        moves = [{'id': i, 'round_index': i} for i in range(3)]
        screen = self._screen_with_config(
            figures=figs, battle_moves=moves, spell_name='poison')
        assert screen._is_defence_ready() is True

    def test_ready_with_auto_gamble(self):
        figs = [{'id': 1, 'has_deficit': False, 'field': 'castle'}]
        moves = [{'id': i, 'round_index': i} for i in range(3)]
        screen = self._screen_with_config(
            figures=figs, battle_moves=moves, auto_gamble=True)
        assert screen._is_defence_ready() is True

    def test_not_ready_with_only_deficit_figures(self):
        figs = [{'id': 1, 'has_deficit': True, 'field': 'castle'}]
        moves = [{'id': i, 'round_index': i} for i in range(3)]
        screen = self._screen_with_config(
            figures=figs, battle_moves=moves, auto_gamble=True)
        assert screen._is_defence_ready() is False

    def test_not_ready_with_no_config(self):
        from game.screens.defence_screen import DefenceScreen
        state = _make_state()
        screen = DefenceScreen(state)
        screen._config = None
        assert screen._is_defence_ready() is False


class TestDefenceScreenNavigation:

    def test_back_returns_to_kingdom(self):
        from game.screens.defence_screen import DefenceScreen
        import pygame
        state = _make_state()
        screen = DefenceScreen(state)
        screen._build_layout()

        event = pygame.event.Event(
            pygame.MOUSEBUTTONUP, button=1, pos=screen._btn_back.center)
        screen.handle_events([event])
        assert state.screen == 'kingdom'

    def test_escape_returns_to_kingdom(self):
        from game.screens.defence_screen import DefenceScreen
        import pygame
        state = _make_state()
        screen = DefenceScreen(state)

        event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)
        screen.handle_events([event])
        assert state.screen == 'kingdom'


class TestModifierCycle:

    def test_cycle_no_mod_to_peasant_war(self):
        from game.screens.defence_screen import DefenceScreen
        import pygame
        state = _make_state()
        screen = DefenceScreen(state)
        screen._land_id = 7
        screen._config = _make_config()
        screen._build_layout()

        with patch.object(screen, '_server_set_modifier') as mock_set:
            event = pygame.event.Event(
                pygame.MOUSEBUTTONUP, button=1, pos=screen._btn_modifier.center)
            screen.handle_events([event])
            mock_set.assert_called_once_with('Peasant War')

    def test_cycle_peasant_war_to_civil_war(self):
        from game.screens.defence_screen import DefenceScreen
        import pygame
        state = _make_state()
        screen = DefenceScreen(state)
        screen._land_id = 7
        screen._config = _make_config(battle_modifier={'type': 'Peasant War'})
        screen._build_layout()

        with patch.object(screen, '_server_set_modifier') as mock_set:
            event = pygame.event.Event(
                pygame.MOUSEBUTTONUP, button=1, pos=screen._btn_modifier.center)
            screen.handle_events([event])
            mock_set.assert_called_once_with('Civil War')

    def test_cycle_civil_war_to_none(self):
        from game.screens.defence_screen import DefenceScreen
        import pygame
        state = _make_state()
        screen = DefenceScreen(state)
        screen._land_id = 7
        screen._config = _make_config(battle_modifier={'type': 'Civil War'})
        screen._build_layout()

        with patch.object(screen, '_server_remove_modifier') as mock_rm:
            event = pygame.event.Event(
                pygame.MOUSEBUTTONUP, button=1, pos=screen._btn_modifier.center)
            screen.handle_events([event])
            mock_rm.assert_called_once()


class TestAutoGambleToggle:

    def test_toggle_on(self):
        from game.screens.defence_screen import DefenceScreen
        import pygame
        state = _make_state()
        screen = DefenceScreen(state)
        screen._land_id = 7
        screen._config = _make_config(auto_gamble=False)
        screen._build_layout()

        with patch.object(screen, '_server_set_auto_gamble') as mock_ag:
            event = pygame.event.Event(
                pygame.MOUSEBUTTONUP, button=1, pos=screen._btn_auto_gamble.center)
            screen.handle_events([event])
            mock_ag.assert_called_once_with(True)

    def test_toggle_off(self):
        from game.screens.defence_screen import DefenceScreen
        import pygame
        state = _make_state()
        screen = DefenceScreen(state)
        screen._land_id = 7
        screen._config = _make_config(auto_gamble=True)
        screen._build_layout()

        with patch.object(screen, '_server_set_auto_gamble') as mock_ag:
            event = pygame.event.Event(
                pygame.MOUSEBUTTONUP, button=1, pos=screen._btn_auto_gamble.center)
            screen.handle_events([event])
            mock_ag.assert_called_once_with(False)


class TestBattleFigureToggle:

    def test_clear_battle_figure(self):
        from game.screens.defence_screen import DefenceScreen
        import pygame
        state = _make_state()
        screen = DefenceScreen(state)
        screen._land_id = 7
        screen._config = _make_config(
            figures=[{'id': 10, 'has_deficit': False, 'field': 'castle', 'name': 'King'}],
            battle_figure_id=10,
        )
        screen._build_layout()

        with patch.object(screen, '_server_clear_battle_figure') as mock_cl:
            event = pygame.event.Event(
                pygame.MOUSEBUTTONUP, button=1, pos=screen._btn_battle_fig.center)
            screen.handle_events([event])
            mock_cl.assert_called_once()

    def test_auto_select_first_valid_figure(self):
        from game.screens.defence_screen import DefenceScreen
        import pygame
        state = _make_state()
        screen = DefenceScreen(state)
        screen._land_id = 7
        screen._config = _make_config(
            figures=[
                {'id': 10, 'has_deficit': True, 'field': 'castle'},
                {'id': 11, 'has_deficit': False, 'field': 'village'},
            ],
        )
        screen._build_layout()

        with patch.object(screen, '_server_set_battle_figure') as mock_sb:
            event = pygame.event.Event(
                pygame.MOUSEBUTTONUP, button=1, pos=screen._btn_battle_fig.center)
            screen.handle_events([event])
            mock_sb.assert_called_once_with(11)


class TestSpellToggle:

    def test_clear_spell(self):
        from game.screens.defence_screen import DefenceScreen
        import pygame
        state = _make_state()
        screen = DefenceScreen(state)
        screen._land_id = 7
        screen._config = _make_config(spell_name='poison')
        screen._build_layout()

        with patch.object(screen, '_server_clear_spell') as mock_cs:
            event = pygame.event.Event(
                pygame.MOUSEBUTTONUP, button=1, pos=screen._btn_spell.center)
            screen.handle_events([event])
            mock_cs.assert_called_once()
