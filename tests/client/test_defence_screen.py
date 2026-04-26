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
    state.set_msg = MagicMock()
    state.action = {}
    return state


def _make_config(**overrides):
    cfg = {
        'figures': [],
        'battle_moves': [],
        'prelude_spell_name': None,
        'battle_figure_id': None,
        'battle_figure_id_2': None,
        'counter_spell_name': None,
        'counter_spell_card_ids': None,
        'counter_spell_target_figure_id': None,
        'auto_gamble': False,
        'auto_gamble_threshold': 10,
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
        """Has figures + moves but no battle figure or counter spell."""
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

    def test_ready_with_counter_spell(self):
        figs = [{'id': 1, 'has_deficit': False, 'field': 'castle'}]
        moves = [{'id': i, 'round_index': i} for i in range(3)]
        screen = self._screen_with_config(
            figures=figs, battle_moves=moves, counter_spell_name='Poison')
        assert screen._is_defence_ready() is True

    def test_not_ready_with_auto_gamble_only(self):
        figs = [{'id': 1, 'has_deficit': False, 'field': 'castle'}]
        moves = [{'id': i, 'round_index': i} for i in range(3)]
        screen = self._screen_with_config(
            figures=figs, battle_moves=moves, auto_gamble=True)
        assert screen._is_defence_ready() is False

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
            pygame.MOUSEBUTTONUP, button=1, pos=screen._btn_close_rect.center)
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


class TestPreludeSpellIcons:

    def test_edit_prelude_spell_opens_selection(self):
        from game.screens.defence_screen import DefenceScreen
        import pygame
        state = _make_state()
        state.action = {}
        screen = DefenceScreen(state)
        screen._land_id = 7
        screen._config = _make_config()
        screen._build_layout()
        screen._collection_cards = [
            {'suit': 'Hearts', 'rank': 'J', 'free': 2},
        ]

        pos = screen._btn_prelude_edit.center
        event = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos)
        with patch.object(screen, '_open_prelude_spell_screen') as mock_open:
            screen.handle_events([event])
            mock_open.assert_called_once()

    def test_clear_prelude_spell_via_x_button(self):
        from game.screens.defence_screen import DefenceScreen
        import pygame
        state = _make_state()
        state.action = {}
        screen = DefenceScreen(state)
        screen._land_id = 7
        screen._config = _make_config(prelude_spell_name='Peasant War')
        screen._build_layout()
        _xbs = screen._x_btn_sz
        rect = screen._prelude_spell_rect
        screen._prelude_x_rect = pygame.Rect(rect.right - _xbs - 2, rect.y + 2, _xbs, _xbs)

        event = pygame.event.Event(
            pygame.MOUSEBUTTONUP, button=1, pos=screen._prelude_x_rect.center)
        screen.handle_events([event])
        assert screen._pending_prelude_clear is True


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


class TestAutoGambleThreshold:

    def test_threshold_controls_share_toggle_row_without_overlap(self):
        from game.screens.defence_screen import DefenceScreen
        state = _make_state()
        screen = DefenceScreen(state)
        screen._land_id = 7
        screen._config = _make_config(auto_gamble_threshold=10)
        screen._build_layout()

        assert screen._btn_auto_gamble.centery == screen._btn_auto_gamble_dec.centery
        assert screen._btn_auto_gamble.right < screen._btn_auto_gamble_dec.left
        assert screen._btn_auto_gamble_dec.right < screen._auto_gamble_threshold_rect.left
        assert screen._auto_gamble_threshold_rect.right < screen._btn_auto_gamble_inc.left
        assert screen._btn_auto_gamble_inc.right <= screen._battle_plan_rect.right

    def test_threshold_decrement(self):
        from game.screens.defence_screen import DefenceScreen
        import pygame
        state = _make_state()
        screen = DefenceScreen(state)
        screen._land_id = 7
        screen._config = _make_config(auto_gamble_threshold=10)
        screen._build_layout()

        with patch.object(screen, '_server_set_auto_gamble_threshold') as mock_set:
            event = pygame.event.Event(
                pygame.MOUSEBUTTONUP, button=1, pos=screen._btn_auto_gamble_dec.center)
            screen.handle_events([event])
            mock_set.assert_called_once_with(9)

    def test_threshold_decrement_updates_local_value_immediately(self):
        from game.screens.defence_screen import DefenceScreen
        import pygame
        state = _make_state()
        screen = DefenceScreen(state)
        screen._land_id = 7
        screen._config = _make_config(auto_gamble_threshold=10)
        screen._build_layout()

        with patch.object(screen, '_server_set_auto_gamble_threshold') as mock_set:
            event = pygame.event.Event(
                pygame.MOUSEBUTTONUP, button=1, pos=screen._btn_auto_gamble_dec.center)
            screen.handle_events([event])
            assert screen._config['auto_gamble_threshold'] == 9
            mock_set.assert_called_once_with(9)

    def test_threshold_increment(self):
        from game.screens.defence_screen import DefenceScreen
        import pygame
        state = _make_state()
        screen = DefenceScreen(state)
        screen._land_id = 7
        screen._config = _make_config(auto_gamble_threshold=10)
        screen._build_layout()

        with patch.object(screen, '_server_set_auto_gamble_threshold') as mock_set:
            event = pygame.event.Event(
                pygame.MOUSEBUTTONUP, button=1, pos=screen._btn_auto_gamble_inc.center)
            screen.handle_events([event])
            mock_set.assert_called_once_with(11)

    def test_threshold_click_priority_over_toggle_when_overlapping(self):
        from game.screens.defence_screen import DefenceScreen
        import pygame
        state = _make_state()
        screen = DefenceScreen(state)
        screen._land_id = 7
        screen._config = _make_config(auto_gamble=False, auto_gamble_threshold=10)
        screen._build_layout()

        # Simulate overlap to lock in expected click priority.
        screen._btn_auto_gamble_dec = screen._btn_auto_gamble.copy()

        with patch.object(screen, '_server_set_auto_gamble') as mock_toggle, \
                patch.object(screen, '_server_set_auto_gamble_threshold') as mock_set:
            event = pygame.event.Event(
                pygame.MOUSEBUTTONUP, button=1, pos=screen._btn_auto_gamble.center)
            screen.handle_events([event])
            mock_set.assert_called_once_with(9)
            mock_toggle.assert_not_called()

    def test_threshold_reverts_local_value_on_server_failure(self):
        from game.screens.defence_screen import DefenceScreen
        import pygame
        state = _make_state()
        screen = DefenceScreen(state)
        screen._land_id = 7
        screen._config = _make_config(auto_gamble_threshold=10)
        screen._build_layout()

        with patch.object(screen, '_server_set_auto_gamble_threshold', return_value=False):
            event = pygame.event.Event(
                pygame.MOUSEBUTTONUP, button=1, pos=screen._btn_auto_gamble_inc.center)
            screen.handle_events([event])
            assert screen._config['auto_gamble_threshold'] == 10

    def test_threshold_handles_non_json_response(self):
        from game.screens.defence_screen import DefenceScreen
        state = _make_state()
        screen = DefenceScreen(state)
        screen._land_id = 7
        screen._config = _make_config(auto_gamble_threshold=10)

        class _Resp:
            status_code = 500
            text = '<html>Internal Server Error</html>'

            def json(self):
                raise ValueError('Expecting value: line 1 column 1 (char 0)')

        with patch('game.screens.defence_screen.requests.post', return_value=_Resp()):
            ok = screen._server_set_auto_gamble_threshold(11)
            assert ok is False
            state.set_msg.assert_called_once_with('Could not update auto-gamble threshold')


class TestDefenceScreenLayout:

    def test_right_panels_stack_without_overlap(self):
        from game.screens.defence_screen import DefenceScreen
        state = _make_state()
        screen = DefenceScreen(state)
        screen._land_id = 7
        screen._config = _make_config()
        screen._build_layout()

        assert screen._battle_plan_rect.bottom < screen._prelude_panel_rect.top
        assert screen._prelude_panel_rect.bottom < screen._counter_panel_rect.top
        assert screen._counter_panel_rect.bottom <= screen._btn_save.top

    def test_right_panel_controls_stay_inside_panels(self):
        from game.screens.defence_screen import DefenceScreen
        state = _make_state()
        screen = DefenceScreen(state)
        screen._land_id = 7
        screen._config = _make_config()
        screen._build_layout()

        assert screen._battle_plan_rect.contains(screen._move_slots_rect)
        assert screen._battle_plan_rect.contains(screen._btn_auto_gamble)
        assert screen._battle_plan_rect.contains(screen._btn_auto_gamble_dec)
        assert screen._battle_plan_rect.contains(screen._auto_gamble_threshold_rect)
        assert screen._battle_plan_rect.contains(screen._btn_auto_gamble_inc)
        assert screen._prelude_panel_rect.contains(screen._prelude_spell_rect)
        assert screen._counter_panel_rect.contains(screen._battle_figure_rect)
        assert screen._counter_panel_rect.contains(screen._counter_spell_rect)

    def test_caption_text_fits_available_width(self):
        from game.screens.defence_screen import DefenceScreen
        state = _make_state()
        screen = DefenceScreen(state)

        fitted = screen._fit_text('Very Long Caption Text', screen._res_font, 30)

        assert screen._res_font.size(fitted)[0] <= 30


class TestBattleFigureToggle:

    def test_clear_battle_figure_via_x(self):
        from game.screens.defence_screen import DefenceScreen
        import pygame
        state = _make_state()
        state.action = {}
        screen = DefenceScreen(state)
        screen._land_id = 7
        screen._config = _make_config(
            figures=[{'id': 10, 'has_deficit': False, 'field': 'castle', 'name': 'King'}],
            battle_figure_id=10,
        )
        screen._build_layout()
        # Manually add X rect (normally set during draw)
        rect = screen._battle_figure_rect
        _xbs = screen._x_btn_sz
        screen._battle_figure_x_rect = pygame.Rect(rect.right - _xbs - 2, rect.y + 2, _xbs, _xbs)

        with patch.object(screen, '_server_clear_battle_figure') as mock_cl:
            event = pygame.event.Event(
                pygame.MOUSEBUTTONUP, button=1, pos=screen._battle_figure_x_rect.center)
            screen.handle_events([event])
            mock_cl.assert_called_once()

    def test_auto_select_first_valid_figure(self):
        from game.screens.defence_screen import DefenceScreen
        import pygame
        state = _make_state()
        state.action = {}
        screen = DefenceScreen(state)
        screen._land_id = 7
        screen._config = _make_config(
            figures=[
                {'id': 10, 'has_deficit': True, 'field': 'castle'},
                {'id': 11, 'has_deficit': False, 'field': 'village'},
            ],
        )
        screen._build_layout()

        # Clicking the empty battle_figure slot should enter selection mode
        pos = screen._battle_figure_rect.center
        event = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos)
        screen.handle_events([event])
        assert screen._selecting_battle_fig is True


class TestCounterSpellIcons:

    def test_edit_counter_spell_opens_selection(self):
        from game.screens.defence_screen import DefenceScreen
        import pygame
        state = _make_state()
        state.action = {}
        screen = DefenceScreen(state)
        screen._land_id = 7
        screen._config = _make_config()
        screen._build_layout()
        screen._collection_cards = [
            {'suit': 'Spades', 'rank': '3', 'free': 2},
        ]

        pos = screen._btn_counter_edit.center
        event = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos)
        with patch.object(screen, '_open_counter_spell_screen') as mock_open:
            screen.handle_events([event])
            mock_open.assert_called_once()

    def test_clear_counter_spell_via_x(self):
        from game.screens.defence_screen import DefenceScreen
        import pygame
        state = _make_state()
        state.action = {}
        screen = DefenceScreen(state)
        screen._land_id = 7
        screen._config = _make_config(counter_spell_name='Poison')
        screen._build_layout()
        _xbs = screen._x_btn_sz
        rect = screen._counter_spell_rect
        screen._counter_x_rect = pygame.Rect(rect.right - _xbs - 2, rect.y + 2, _xbs, _xbs)

        event = pygame.event.Event(
            pygame.MOUSEBUTTONUP, button=1, pos=screen._counter_x_rect.center)
        screen.handle_events([event])
        assert screen._pending_counter_clear is True
