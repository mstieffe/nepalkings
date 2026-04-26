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


def _make_checkmate_family():
    description = (
        'Supports three village slots and two military slots. '
        'Triggers checkmate when defeated.'
    )
    matched = SimpleNamespace(
        suit='Hearts',
        name='Djungle Maharaja',
        sub_name='Hearts',
        key_cards=[],
        number_card=None,
        upgrade_card=None,
    )
    family = SimpleNamespace(
        name='Djungle Maharaja',
        description=description,
        figures=[matched],
    )
    return family, description


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
        with patch.object(screen, '_open_prelude_spell_screen') as mock_open:
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


class TestConquerConfirmData:

    def test_battle_confirmation_separates_consumed_and_locked_cards(self):
        from game.screens.conquer_screen import ConquerScreen
        import pygame
        state = _make_state()
        screen = ConquerScreen(state)
        screen._config = {
            'figures': [{
                'id': 1,
                'name': 'Attacker',
                'card_details': [{'suit': 'Hearts', 'rank': '7'}],
            }],
            'battle_moves': [{
                'id': 2,
                'card_id': 20,
                'round_index': 0,
                'suit': 'Spades',
                'rank': 'Q',
            }],
            'battle_modifier': {'type': 'Stronghold'},
            'modifier_card_details': [{'suit': 'Clubs', 'rank': '3'}],
            'prelude_spell_name': 'Poison',
            'prelude_spell_card_details': [{'suit': 'Diamonds', 'rank': '8'}],
        }

        class _FakeCardImg:
            def __init__(self, window, suit, rank):
                self.front_img = pygame.Surface((70, 100), pygame.SRCALPHA)

        with patch('game.components.cards.card_img.CardImg', _FakeCardImg):
            msg, image_groups, after_msg = screen._build_confirm_data()

        assert 'starting this conquer battle' in msg
        assert [group['key'] for group in image_groups] == ['consumed', 'locked']
        consumed, locked = image_groups
        assert consumed['icon'] == 'remove'
        assert consumed['badge_icon'] == 'remove'
        assert len(consumed['items']) == 3
        assert locked['icon'] == 'lock'
        assert locked['badge_icon'] == 'lock'
        assert len(locked['items']) == 1
        assert 'loot' in after_msg


class TestConquerScreenLayout:

    def test_config_subscreen_rect_is_centered_below_top_chrome(self):
        from config import settings
        from game.screens.conquer_screen import ConquerScreen
        state = _make_state()
        screen = ConquerScreen(state)

        rect = screen._config_subscreen_rect()

        assert rect.y > settings.SUB_SCREEN_Y
        assert abs(rect.centerx - settings.SCREEN_WIDTH // 2) <= 1
        assert abs(rect.centery - settings.SCREEN_HEIGHT // 2) <= 1

    def test_config_figures_hide_duel_only_checkmate_text(self):
        from game.screens.conquer_screen import ConquerScreen
        state = _make_state()
        screen = ConquerScreen(state)
        family, description = _make_checkmate_family()

        fig = screen._config_fig_to_figure({
            'id': 10,
            'family_name': 'Djungle Maharaja',
            'name': 'Djungle Maharaja',
            'suit': 'Hearts',
            'description': description,
            'checkmate': True,
        }, {'Djungle Maharaja': family})

        assert fig.checkmate is False
        assert 'checkmate' not in fig.description.lower()
        assert 'checkmate' not in fig.family.description.lower()

    def test_right_panels_stack_without_overlap(self):
        from game.screens.conquer_screen import ConquerScreen
        state = _make_state()
        state.action = {}
        screen = ConquerScreen(state)
        screen._land_id = 42
        screen._config = {
            'figures': [],
            'battle_moves': [],
            'prelude_spell_name': None,
        }
        screen._build_layout()

        assert screen._battle_plan_rect.bottom < screen._prelude_panel_rect.top
        assert screen._prelude_panel_rect.bottom <= screen._btn_battle.top

    def test_right_panel_controls_stay_inside_panels(self):
        from game.screens.conquer_screen import ConquerScreen
        state = _make_state()
        state.action = {}
        screen = ConquerScreen(state)
        screen._land_id = 42
        screen._config = {
            'figures': [],
            'battle_moves': [],
            'prelude_spell_name': None,
        }
        screen._build_layout()

        assert screen._battle_plan_rect.contains(screen._move_slots_rect)
        assert screen._prelude_panel_rect.contains(screen._prelude_spell_rect)

    def test_right_panel_info_buttons_exist_inside_sections(self):
        from game.screens.conquer_screen import ConquerScreen
        state = _make_state()
        state.action = {}
        screen = ConquerScreen(state)
        screen._land_id = 42
        screen._config = {
            'figures': [],
            'battle_moves': [],
            'prelude_spell_name': None,
        }
        screen._build_layout()

        assert set(screen._info_button_rects) == {'battle_plan', 'prelude_spell'}
        assert screen._battle_plan_rect.contains(screen._info_button_rects['battle_plan'])
        assert screen._prelude_panel_rect.contains(screen._info_button_rects['prelude_spell'])

    def test_info_button_click_opens_section_info(self):
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
        screen._build_layout()

        event = pygame.event.Event(
            pygame.MOUSEBUTTONUP,
            button=1,
            pos=screen._info_button_rects['prelude_spell'].center,
        )
        with patch.object(screen, '_open_prelude_spell_screen') as mock_open:
            screen.handle_events([event])

        assert screen._active_info_key == 'prelude_spell'
        mock_open.assert_not_called()


class TestConquerRemoveClickPriority:

    def test_figure_remove_click_does_not_open_detail_box(self):
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
        screen._build_layout()
        field_rect = screen._field_rects['castle']
        remove_rect = pygame.Rect(field_rect.right - 24, field_rect.top + 4, 20, 20)
        screen._config = {
            'figures': [{'id': 10, 'has_deficit': False, 'field': 'castle', '_remove_rect': remove_rect}],
            'battle_moves': [],
            'prelude_spell_name': None,
        }
        screen._figure_icons = {
            10: SimpleNamespace(hovered=True, figure=SimpleNamespace(id=10)),
        }

        with patch.object(screen, '_server_remove_figure') as mock_remove, \
                patch('game.screens.conquer_screen.FigureDetailBox') as mock_detail:
            event = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=remove_rect.center)
            screen.handle_events([event])

            mock_remove.assert_called_once_with(10)
            mock_detail.assert_not_called()

    def test_battle_move_remove_click_does_not_open_detail_box(self):
        from game.screens.conquer_screen import ConquerScreen
        import pygame
        state = _make_state()
        state.action = {}
        screen = ConquerScreen(state)
        screen._land_id = 42
        screen._config = {
            'figures': [],
            'battle_moves': [{'id': 20, 'round_index': 1, 'family_name': 'Attack', 'suit': 'Hearts', 'value': 8}],
            'prelude_spell_name': None,
        }
        screen._build_layout()
        remove_rect = pygame.Rect(
            screen._move_slots_rect.centerx, screen._move_slots_rect.centery, 20, 20)
        screen._move_remove_rects = {1: remove_rect}
        screen._hovered_slot = 1

        with patch.object(screen, '_server_return_move') as mock_return, \
                patch('game.screens.conquer_screen.BattleMoveDetailBox') as mock_detail:
            event = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=remove_rect.center)
            screen.handle_events([event])

            mock_return.assert_called_once_with(20)
            mock_detail.assert_not_called()
