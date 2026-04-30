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


def _make_figure_object(figure_id, *, field='castle', cannot_attack=False,
                       cannot_defend=False):
    """Stub for `DefenceScreen._figure_objects` entries.

    `_battle_figure_block_reason` only inspects ``cannot_attack``,
    ``cannot_defend``, and ``family.field`` on the figure, so a thin
    namespace is enough for readiness/selection tests.
    """
    return SimpleNamespace(
        id=figure_id,
        cannot_attack=cannot_attack,
        cannot_defend=cannot_defend,
        family=SimpleNamespace(field=field),
    )


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
        'draft_dirty': False,
    }
    cfg.update(overrides)
    return cfg


def _make_checkmate_family():
    description = (
        'Supports three village slots and two military slots. '
        'Triggers checkmate when defeated.'
    )
    matched = SimpleNamespace(
        suit='Spades',
        name='Himalaya Maharaja',
        sub_name='Spades',
        key_cards=[],
        number_card=None,
        upgrade_card=None,
    )
    family = SimpleNamespace(
        name='Himalaya Maharaja',
        description=description,
        figures=[matched],
    )
    return family, description


class TestDefenceScreenInit:

    def test_initial_state(self):
        from game.screens.defence_screen import DefenceScreen
        state = _make_state()
        screen = DefenceScreen(state)
        assert screen._land_id is None
        assert screen._config is None
        assert screen._loading is False

    def test_tiny_font_initialized(self):
        from game.screens.defence_screen import DefenceScreen
        state = _make_state()
        screen = DefenceScreen(state)
        assert hasattr(screen, '_tiny_font')

    def test_draw_land_header_handles_kingdom_effects(self):
        from game.screens.defence_screen import DefenceScreen
        state = _make_state()
        screen = DefenceScreen(state)
        land = {
            'tier': 2,
            'gold_rate': 5,
            'suit_bonus_suit': 'Hearts',
            'suit_bonus_value': 3,
            'kingdom_name': 'Valley Crown',
            'kingdom_skill_effects': ['+1 Shield', '+5 Gold Rate'],
        }
        # Regression guard: this path used to crash with AttributeError
        # when _tiny_font was not initialized.
        screen._draw_land_header(land)

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
        screen._figure_objects = [_make_figure_object(1)]
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


class TestDefenceDraftFlow:

    def test_load_opens_draft_config(self):
        from game.screens.defence_screen import DefenceScreen
        state = _make_state()
        screen = DefenceScreen(state)
        screen._land_id = 7

        class _Resp:
            status_code = 200
            headers = {'content-type': 'application/json'}

            def json(self):
                return {
                    'success': True,
                    'config': _make_config(draft_dirty=True),
                    'land': {'id': 7},
                }

        with patch('game.screens.defence_screen.requests.post', return_value=_Resp()) as mock_post, \
                patch.object(screen, '_refresh_collection'):
            screen._load_config()

        assert '/kingdom/defence/draft/open' in mock_post.call_args.args[0]
        assert mock_post.call_args.kwargs['json'] == {'land_id': 7}
        assert screen._draft_dirty is True

    def test_leave_clean_draft_does_not_reset_active(self):
        from game.screens.defence_screen import DefenceScreen
        state = _make_state()
        screen = DefenceScreen(state)
        screen._land_id = 7
        screen._config = _make_config(draft_dirty=False)

        with patch('game.screens.defence_screen.requests.post') as mock_post:
            screen._try_leave_screen()

        assert state.screen == 'kingdom'
        mock_post.assert_not_called()

    def test_leave_dirty_draft_offers_save_discard_stay(self):
        from game.screens.defence_screen import DefenceScreen
        state = _make_state()
        screen = DefenceScreen(state)
        screen._land_id = 7
        screen._config = _make_config(draft_dirty=True)
        screen._draft_dirty = True

        screen._try_leave_screen()

        assert screen._pending_leave_confirm is True
        assert screen.dialogue_box.actions == ['Save & Leave', 'Discard Changes', 'Stay']
        assert state.screen == 'defence'

    def test_discard_changes_discards_draft_only_and_navigates(self):
        from game.screens.defence_screen import DefenceScreen
        state = _make_state()
        screen = DefenceScreen(state)
        state.action = {'status': 'discard changes'}
        screen._pending_leave_confirm = True
        screen._pending_nav = 'game_menu'

        with patch.object(screen, '_server_discard_draft', return_value=True) as mock_discard:
            screen.handle_events([])

        mock_discard.assert_called_once()
        assert state.screen == 'game_menu'

    def test_save_confirm_saves_draft_and_navigates(self):
        from game.screens.defence_screen import DefenceScreen
        state = _make_state()
        screen = DefenceScreen(state)
        state.action = {'status': 'confirm'}
        screen._pending_save_confirm = True

        with patch.object(screen, '_server_save_draft', return_value=True) as mock_save:
            screen.handle_events([])

        mock_save.assert_called_once()
        assert state.screen == 'kingdom'

    def test_home_icon_cannot_bypass_dirty_draft_prompt(self):
        from game.screens.defence_screen import DefenceScreen
        import pygame
        state = _make_state()
        screen = DefenceScreen(state)
        screen._config = _make_config(draft_dirty=True)
        screen._draft_dirty = True
        screen._icon_home.collide = MagicMock(return_value=True)
        screen._icon_settings.collide = MagicMock(return_value=False)
        screen._icon_logout.collide = MagicMock(return_value=False)

        event = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(0, 0))
        handled = screen._handle_icon_events(event)

        assert handled is True
        assert state.screen == 'defence'
        assert screen._pending_nav == 'game_menu'
        assert screen._pending_leave_confirm is True


class TestDefenceConfirmData:

    def test_save_confirmation_separates_locked_figures_from_deferred_consumed_cards(self):
        from game.screens.defence_screen import DefenceScreen
        import pygame
        state = _make_state()
        screen = DefenceScreen(state)
        screen._config = _make_config(
            figures=[{
                'id': 1,
                'name': 'Guard',
                'card_details': [{'suit': 'Hearts', 'rank': '7'}],
            }],
            battle_moves=[{
                'id': 2,
                'card_id': 20,
                'round_index': 0,
                'suit': 'Spades',
                'rank': 'Q',
            }],
            prelude_spell_name='Health Boost',
            prelude_spell_card_details=[{'suit': 'Clubs', 'rank': '3'}],
            counter_spell_name='Poison',
            counter_spell_card_details=[{'suit': 'Diamonds', 'rank': '8'}],
        )

        class _FakeCardImg:
            def __init__(self, window, suit, rank):
                self.front_img = pygame.Surface((70, 100), pygame.SRCALPHA)

        with patch('game.components.cards.card_img.CardImg', _FakeCardImg):
            msg, image_groups, after_msg = screen._build_confirm_data()

        assert 'saving this defence' in msg
        assert [group['key'] for group in image_groups] == ['consumed_if_lost', 'locked']
        consumed_if_lost, locked = image_groups
        assert consumed_if_lost['icon'] == 'remove'
        assert consumed_if_lost['badge_icon'] == 'remove'
        assert len(consumed_if_lost['items']) == 3
        assert locked['icon'] == 'lock'
        assert locked['badge_icon'] == 'lock'
        assert len(locked['items']) == 1
        assert 'loot' in after_msg
        assert 'while the land is still yours' in after_msg


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
        assert screen._btn_auto_gamble.top - screen._move_slots_rect.bottom >= 10
        assert screen._battle_plan_rect.bottom - screen._btn_auto_gamble.bottom >= 6

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

    def test_config_subscreen_rect_is_centered_below_top_chrome(self):
        from config import settings
        from game.screens.defence_screen import DefenceScreen
        state = _make_state()
        screen = DefenceScreen(state)

        rect = screen._config_subscreen_rect()

        assert rect.y > settings.SUB_SCREEN_Y
        assert abs(rect.centerx - settings.SCREEN_WIDTH // 2) <= 1
        assert abs(rect.centery - settings.SCREEN_HEIGHT // 2) <= 1

    def test_config_figures_hide_duel_only_checkmate_text(self):
        from game.screens.defence_screen import DefenceScreen
        state = _make_state()
        screen = DefenceScreen(state)
        family, description = _make_checkmate_family()

        fig = screen._config_fig_to_figure({
            'id': 10,
            'family_name': 'Himalaya Maharaja',
            'name': 'Himalaya Maharaja',
            'suit': 'Spades',
            'description': description,
            'checkmate': True,
        }, {'Himalaya Maharaja': family})

        assert fig.checkmate is False
        assert 'checkmate' not in fig.description.lower()
        assert 'checkmate' not in fig.family.description.lower()

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

    def test_selection_prompt_sits_below_header(self):
        from game.screens.defence_screen import DefenceScreen
        state = _make_state()
        screen = DefenceScreen(state)
        screen._land_id = 7
        screen._config = _make_config()
        screen._build_layout()

        header_bottom = (
            screen._field_title_pos[1]
            + screen._label_font.get_height()
            + screen._res_font.get_height()
        )
        prompt_rect = screen._draw_selection_prompt(
            'Click a figure',
            'Cancel',
            (255, 220, 80),
        )

        assert prompt_rect.top >= header_bottom

    def test_right_panel_info_buttons_exist_inside_sections(self):
        from game.screens.defence_screen import DefenceScreen
        state = _make_state()
        screen = DefenceScreen(state)
        screen._land_id = 7
        screen._config = _make_config()
        screen._build_layout()

        assert set(screen._info_button_rects) == {
            'battle_plan', 'prelude_spell', 'defender_response'
        }
        assert screen._battle_plan_rect.contains(screen._info_button_rects['battle_plan'])
        assert screen._prelude_panel_rect.contains(screen._info_button_rects['prelude_spell'])
        assert screen._counter_panel_rect.contains(screen._info_button_rects['defender_response'])

    def test_info_button_click_opens_section_info(self):
        from game.screens.defence_screen import DefenceScreen
        import pygame
        state = _make_state()
        screen = DefenceScreen(state)
        screen._land_id = 7
        screen._config = _make_config()
        screen._build_layout()

        event = pygame.event.Event(
            pygame.MOUSEBUTTONUP,
            button=1,
            pos=screen._info_button_rects['battle_plan'].center,
        )
        with patch.object(screen, '_open_battle_shop') as mock_open:
            screen.handle_events([event])

        assert screen._active_info_key == 'battle_plan'
        mock_open.assert_not_called()


class TestRemoveClickPriority:

    def test_figure_remove_click_does_not_open_detail_box(self):
        from game.screens.defence_screen import DefenceScreen
        import pygame
        state = _make_state()
        screen = DefenceScreen(state)
        screen._land_id = 7
        screen._config = _make_config()
        screen._build_layout()
        field_rect = screen._field_rects['castle']
        remove_rect = pygame.Rect(field_rect.right - 24, field_rect.top + 4, 20, 20)
        screen._config = _make_config(
            figures=[{'id': 10, 'has_deficit': False, 'field': 'castle', '_remove_rect': remove_rect}],
        )
        screen._figure_icons = {
            10: SimpleNamespace(hovered=True, figure=SimpleNamespace(id=10)),
        }

        with patch.object(screen, '_server_remove_figure') as mock_remove, \
                patch('game.screens.defence_screen.FigureDetailBox') as mock_detail:
            event = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=remove_rect.center)
            screen.handle_events([event])

            mock_remove.assert_called_once_with(10)
            mock_detail.assert_not_called()

    def test_battle_move_remove_click_does_not_open_detail_box(self):
        from game.screens.defence_screen import DefenceScreen
        import pygame
        state = _make_state()
        screen = DefenceScreen(state)
        screen._land_id = 7
        screen._config = _make_config(
            battle_moves=[{'id': 20, 'round_index': 1, 'family_name': 'Attack', 'suit': 'Hearts', 'value': 8}],
        )
        screen._build_layout()
        remove_rect = pygame.Rect(
            screen._move_slots_rect.centerx, screen._move_slots_rect.centery, 20, 20)
        screen._move_remove_rects = {1: remove_rect}
        screen._hovered_slot = 1

        with patch.object(screen, '_server_return_move') as mock_return, \
                patch('game.screens.defence_screen.BattleMoveDetailBox') as mock_detail:
            event = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=remove_rect.center)
            screen.handle_events([event])

            mock_return.assert_called_once_with(20)
            mock_detail.assert_not_called()


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
        screen._figure_objects = [
            _make_figure_object(10, field='castle'),
            _make_figure_object(11, field='village'),
        ]
        screen._build_layout()

        # Clicking the empty battle_figure slot should enter selection mode
        pos = screen._battle_figure_rect.center
        event = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos)
        screen.handle_events([event])
        assert screen._selecting_battle_fig is True

    def test_health_boost_target_selection_ignores_duel_only_checkmate(self):
        from game.screens.defence_screen import DefenceScreen
        import pygame
        state = _make_state()
        state.action = {}
        screen = DefenceScreen(state)
        screen._config = _make_config(figures=[{'id': 10, 'checkmate': True}])
        screen._selecting_spell_target = 'prelude'
        screen._figure_icons = {
            10: SimpleNamespace(hovered=True, figure=SimpleNamespace(id=10)),
        }

        event = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(0, 0))
        with patch.object(screen, '_server_set_prelude_spell') as mock_set:
            screen.handle_events([event])

        mock_set.assert_called_once_with('Health Boost', target_figure_id=10)
        state.set_msg.assert_not_called()
        assert screen._selecting_spell_target is None


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
