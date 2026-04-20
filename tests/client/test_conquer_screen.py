# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Unit tests for ConquerScreen logic (Phase 11)."""
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def _make_state():
    """Create a minimal state namespace."""
    state = SimpleNamespace()
    state.screen = 'conquer'
    state.conquer_land_id = 42
    state.game = MagicMock()
    return state


class TestConquerScreenInit:

    def test_initial_state(self):
        from game.screens.conquer_screen import ConquerScreen
        state = _make_state()
        screen = ConquerScreen(state)
        assert screen._land_id is None
        assert screen._config is None
        assert screen._loading is False

    def test_picks_up_land_id_from_state(self):
        from game.screens.conquer_screen import ConquerScreen
        state = _make_state()
        screen = ConquerScreen(state)
        # update() reads conquer_land_id from state
        screen.update([])
        assert screen._land_id == 42


class TestBattleReadiness:

    def _screen_with_config(self, figures, moves):
        from game.screens.conquer_screen import ConquerScreen
        state = _make_state()
        screen = ConquerScreen(state)
        screen._config = {
            'figures': figures,
            'battle_moves': moves,
            'prelude_spell_name': None,
        }
        return screen

    def test_not_ready_when_empty(self):
        screen = self._screen_with_config([], [])
        assert screen._is_battle_ready() is False

    def test_not_ready_without_moves(self):
        figs = [{'id': 1, 'has_deficit': False, 'field': 'castle'}]
        screen = self._screen_with_config(figs, [])
        assert screen._is_battle_ready() is False

    def test_not_ready_without_figures(self):
        moves = [
            {'id': 1, 'round_index': 0},
            {'id': 2, 'round_index': 1},
            {'id': 3, 'round_index': 2},
        ]
        screen = self._screen_with_config([], moves)
        assert screen._is_battle_ready() is False

    def test_not_ready_when_only_deficit_figures(self):
        figs = [{'id': 1, 'has_deficit': True, 'field': 'castle'}]
        moves = [
            {'id': 1, 'round_index': 0},
            {'id': 2, 'round_index': 1},
            {'id': 3, 'round_index': 2},
        ]
        screen = self._screen_with_config(figs, moves)
        assert screen._is_battle_ready() is False

    def test_ready_with_valid_figure_and_3_moves(self):
        figs = [{'id': 1, 'has_deficit': False, 'field': 'castle'}]
        moves = [
            {'id': 1, 'round_index': 0},
            {'id': 2, 'round_index': 1},
            {'id': 3, 'round_index': 2},
        ]
        screen = self._screen_with_config(figs, moves)
        assert screen._is_battle_ready() is True

    def test_ready_with_deficit_and_non_deficit_figures(self):
        figs = [
            {'id': 1, 'has_deficit': True, 'field': 'castle'},
            {'id': 2, 'has_deficit': False, 'field': 'village'},
        ]
        moves = [
            {'id': 1, 'round_index': 0},
            {'id': 2, 'round_index': 1},
            {'id': 3, 'round_index': 2},
        ]
        screen = self._screen_with_config(figs, moves)
        assert screen._is_battle_ready() is True

    def test_not_ready_with_only_2_moves(self):
        figs = [{'id': 1, 'has_deficit': False, 'field': 'castle'}]
        moves = [
            {'id': 1, 'round_index': 0},
            {'id': 2, 'round_index': 1},
        ]
        screen = self._screen_with_config(figs, moves)
        assert screen._is_battle_ready() is False

    def test_not_ready_with_no_config(self):
        from game.screens.conquer_screen import ConquerScreen
        state = _make_state()
        screen = ConquerScreen(state)
        screen._config = None
        assert screen._is_battle_ready() is False


class TestConquerScreenNavigation:

    def test_back_returns_to_kingdom(self):
        from game.screens.conquer_screen import ConquerScreen
        import pygame
        state = _make_state()
        screen = ConquerScreen(state)
        screen._build_layout()

        # Simulate click on X close button
        event = pygame.event.Event(
            pygame.MOUSEBUTTONUP,
            button=1,
            pos=screen._btn_close_rect.center,
        )
        screen.handle_events([event])
        assert state.screen == 'kingdom'

    def test_escape_returns_to_kingdom(self):
        from game.screens.conquer_screen import ConquerScreen
        import pygame
        state = _make_state()
        screen = ConquerScreen(state)

        event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)
        screen.handle_events([event])
        assert state.screen == 'kingdom'


class TestPreludeSpellToggle:

    def test_edit_prelude_spell_opens_selection(self):
        from game.screens.conquer_screen import ConquerScreen
        import pygame
        state = _make_state()
        state.action = {}
        screen = ConquerScreen(state)
        screen._land_id = 42
        screen._config = {
            'figures': [],
            'battle_moves': [],
            'prelude_spell_name': None,
        }
        screen._collection_cards = [
            {'suit': 'Hearts', 'rank': 'Q', 'free': 2, 'total': 2, 'locked': 0},
        ]
        screen._build_layout()

        # Click the edit button → should open prelude spell selection
        edit_rect = screen._btn_prelude_edit
        event = pygame.event.Event(
            pygame.MOUSEBUTTONUP,
            button=1,
            pos=edit_rect.center,
        )
        with patch.object(screen, '_open_prelude_spell_selection') as mock_open:
            screen.handle_events([event])
            mock_open.assert_called_once()

    def test_clear_prelude_spell_via_x_button(self):
        from game.screens.conquer_screen import ConquerScreen
        import pygame
        state = _make_state()
        state.action = {}
        screen = ConquerScreen(state)
        screen._land_id = 42
        screen._config = {
            'figures': [],
            'battle_moves': [],
            'prelude_spell_name': 'Blitzkrieg',
        }
        screen._build_layout()
        # Simulate X rect being set by draw
        _xbs = screen._x_btn_sz
        spell_rect = screen._prelude_spell_rect
        screen._prelude_x_rect = pygame.Rect(
            spell_rect.right - _xbs - 2, spell_rect.y + 2, _xbs, _xbs)

        event = pygame.event.Event(
            pygame.MOUSEBUTTONUP,
            button=1,
            pos=screen._prelude_x_rect.center,
        )
        screen.handle_events([event])
        assert screen._pending_prelude_clear is True
