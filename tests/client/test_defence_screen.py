# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Unit tests for DefenceScreen logic (Phase 12)."""
import os
from pathlib import Path
import subprocess
import sys
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


APP_DIR = Path(__file__).resolve().parents[2] / 'nepal_kings'


def _run_mobile_geometry_check(code):
    env = os.environ.copy()
    env.update({
        'SDL_VIDEODRIVER': 'dummy',
        'SDL_AUDIODRIVER': 'dummy',
        'NK_SCREEN_WIDTH': '854',
        'NK_SCREEN_HEIGHT': '480',
        'NK_IS_MOBILE': '1',
        'NK_UI_SCALE': '1.6',
    })
    result = subprocess.run(
        [sys.executable, '-c', code],
        cwd=APP_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


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


def _make_power_figure(figure_id, *, field='village', suit='Hearts', value=10,
                       cannot_be_targeted=False):
    return SimpleNamespace(
        id=figure_id,
        suit=suit,
        family=SimpleNamespace(field=field),
        cannot_be_targeted=cannot_be_targeted,
        get_value=lambda value=value: value,
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


def _make_instant_charge_family():
    description = (
        'The Gorkha Warriors is an offensive military figure that charges instantly into battle '
        'when placed on the field. Requires food equal to its number-card value.'
    )
    matched = SimpleNamespace(
        suit='Hearts',
        name='Gorkha Warriors',
        sub_name='Hearts 7',
        key_cards=[],
        number_card=None,
        upgrade_card=None,
        instant_charge=True,
    )
    family = SimpleNamespace(
        name='Gorkha Warriors',
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

    def test_update_starts_background_config_load(self):
        from game.screens.defence_screen import DefenceScreen
        state = _make_state()
        screen = DefenceScreen(state)
        with patch.object(screen, '_load_config') as sync_load, \
                patch.object(screen, '_start_config_load') as async_load:
            screen.update([])
        assert screen._land_id == 7
        sync_load.assert_not_called()
        async_load.assert_called_once()

    def test_field_slot_background_is_cached(self, monkeypatch):
        from game.screens import defence_screen as module
        from game.screens.defence_screen import DefenceScreen
        import pygame
        state = _make_state()
        screen = DefenceScreen(state)
        raw = pygame.Surface((12, 12), pygame.SRCALPHA)
        load_calls = []
        scale_calls = []

        def fake_load(path):
            load_calls.append(path)
            return raw

        def fake_smoothscale(source, size):
            scale_calls.append(size)
            return pygame.Surface(size, pygame.SRCALPHA)

        monkeypatch.setattr(module.pygame.image, 'load', fake_load)
        monkeypatch.setattr(module.pygame.transform, 'smoothscale', fake_smoothscale)
        rect = pygame.Rect(0, 0, 80, 90)
        first = screen._field_slot_background('castle', rect)
        second = screen._field_slot_background('castle', rect)
        assert first is second
        assert len(load_calls) == 1
        assert len(scale_calls) == 1

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


class TestDefenceBattleMovePower:

    def _screen(self):
        from game.screens.defence_screen import DefenceScreen

        screen = object.__new__(DefenceScreen)
        castle = _make_power_figure(7, field='castle', suit='Spades', value=12)
        screen._figure_objects = [castle]
        screen._figure_icons = {
            7: SimpleNamespace(has_deficit=False, buffs_allies_bonus=0),
        }
        return DefenceScreen, screen

    def test_call_tactic_power_uses_bound_field_figure(self):
        DefenceScreen, screen = self._screen()
        move = {
            'family_name': 'Call King',
            'suit': 'Spades',
            'value': 4,
            'call_figure_id': 7,
        }

        assert DefenceScreen._battle_move_display_power(screen, move) == 16

    def test_battle_move_slot_draws_effective_call_power(self):
        import pygame
        from config import settings

        DefenceScreen, screen = self._screen()
        window = pygame.display.get_surface() or pygame.display.set_mode((1, 1))
        screen.window = window
        screen._config = _make_config(battle_moves=[{
            'id': 20,
            'round_index': 0,
            'family_name': 'Call King',
            'suit': 'Spades',
            'value': 4,
            'call_figure_id': 7,
        }])
        screen._move_slots_rect = pygame.Rect(0, 0, 300, 100)
        screen._move_slot_size = 40
        screen._slot_glow_cache = {}
        screen._slot_icon_cache = {}
        screen._slot_frame_cache = {}
        screen._suit_icon_cache = {}
        screen._slot_font = settings.get_font(settings.FS_TINY)
        screen._small_font = settings.get_font(settings.FS_TINY)
        screen._slot_diamond = pygame.Surface((40, 40), pygame.SRCALPHA)
        screen._x_btn_sz = 12

        with patch('game.screens.defence_screen.draw_battle_move_icon') as draw_icon:
            DefenceScreen._draw_battle_move_slots(screen)

        assert draw_icon.call_args.args[5] == 16


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

    def test_save_ready_defence_saves_draft_and_navigates(self):
        from game.screens.defence_screen import DefenceScreen
        state = _make_state()
        screen = DefenceScreen(state)

        with patch.object(screen, '_server_save_draft', return_value=True) as mock_save:
            screen._save_ready_defence()

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


class TestVictoryReviewSkip:

    def test_skip_acks_victory_and_navigates_without_touching_draft(self):
        from game.screens.defence_screen import DefenceScreen
        state = _make_state()
        screen = DefenceScreen(state)
        screen._victory_review_mode = True
        screen._victory_review_game_id = 42
        screen._land_id = 7
        screen._config = _make_config(draft_dirty=True, figures=[])

        with patch.object(screen, '_server_acknowledge_victory_review',
                          return_value=True) as mock_ack, \
                patch.object(screen, '_server_save_draft') as mock_save, \
                patch.object(screen, '_server_discard_draft') as mock_discard, \
                patch.object(screen, '_server_clear_active_defence') as mock_clear:
            screen._on_skip_click()

        mock_ack.assert_called_once()
        mock_save.assert_not_called()
        mock_discard.assert_not_called()
        mock_clear.assert_not_called()
        assert screen._victory_review_mode is False
        assert screen._victory_review_game_id is None
        assert state.screen == 'kingdom'

    def test_skip_noop_outside_victory_review(self):
        from game.screens.defence_screen import DefenceScreen
        state = _make_state()
        screen = DefenceScreen(state)
        screen._victory_review_mode = False

        with patch.object(screen, '_server_acknowledge_victory_review') as mock_ack:
            screen._on_skip_click()

        mock_ack.assert_not_called()
        assert state.screen == 'defence'


class TestDefenceLootRiskTutorial:

    def test_save_defence_shows_one_time_loot_tutorial_before_save(self):
        from game.screens.defence_screen import DefenceScreen
        import pygame
        state = _make_state()
        state.user_dict = {'onboarding': {'menu_hints_seen': []}}
        screen = DefenceScreen(state)
        screen._is_defence_ready = lambda: True
        screen._server_validate_draft = lambda: {'success': True}
        seen = []
        screen._mark_menu_coach_seen = seen.append

        with patch.object(screen, '_server_save_draft', return_value=True) as mock_save:
            screen._on_save_click()
            assert screen._loot_risk_tutorial_dialogue is not None
            mock_save.assert_not_called()

            win = screen._loot_risk_tutorial_dialogue
            win._created_at = pygame.time.get_ticks() - 1000
            event = pygame.event.Event(
                pygame.MOUSEBUTTONUP, button=1, pos=win._btn_next.rect.center)
            screen.handle_events([event])

        assert seen == ['loot_risk_intro']
        mock_save.assert_called_once()
        assert state.screen == 'kingdom'
        assert screen._loot_risk_tutorial_dialogue is None

    def test_save_defence_skips_loot_tutorial_once_seen(self):
        from game.screens.defence_screen import DefenceScreen
        state = _make_state()
        state.user_dict = {'onboarding': {'menu_hints_seen': ['loot_risk_intro']}}
        screen = DefenceScreen(state)
        screen._is_defence_ready = lambda: True
        screen._server_validate_draft = lambda: {'success': True}

        with patch.object(screen, '_server_save_draft', return_value=True) as mock_save:
            screen._on_save_click()

        assert screen._loot_risk_tutorial_dialogue is None
        mock_save.assert_called_once()
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
        # Removals are free draft edits — the spell clears immediately,
        # without a confirmation dialog.
        with patch.object(screen, '_server_clear_prelude_spell') as mock_clear:
            screen.handle_events([event])
            mock_clear.assert_called_once()
        assert screen.dialogue_box is None


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

    def test_config_figures_show_live_defence_checkmate_rule(self):
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

        assert fig.checkmate is True
        assert 'checkmate' in fig.description.lower()
        assert 'checkmate' in fig.family.description.lower()

    def test_config_figures_hide_instant_advance_in_defence(self):
        from game.screens.defence_screen import DefenceScreen
        state = _make_state()
        screen = DefenceScreen(state)
        family, description = _make_instant_charge_family()

        fig = screen._config_fig_to_figure({
            'id': 11,
            'family_name': 'Gorkha Warriors',
            'name': 'Gorkha Warriors',
            'suit': 'Hearts',
            'description': description,
        }, {'Gorkha Warriors': family})

        assert fig.instant_charge is False
        assert 'charges instantly into battle' not in fig.description.lower()
        assert 'charges instantly into battle' not in fig.family.description.lower()

    def test_config_manufactories_do_not_set_cannot_attack(self):
        """Manufactories produce shields/swords but DO attack — the
        ``cannot_attack`` flag is intentionally NOT set on them."""
        from game.components.figures.family_configs.village_config import village_dict_list
        from game.screens.defence_screen import DefenceScreen
        state = _make_state()
        screen = DefenceScreen(state)
        by_name = {cfg['name']: cfg for cfg in village_dict_list}

        for family_name, suit in (
            ('Shield Manufactory', 'Clubs'),
            ('Sword Manufactory', 'Hearts'),
        ):
            cfg = by_name[family_name]
            family = SimpleNamespace(
                name=family_name,
                description=cfg['description'],
                field='village',
                figures=[],
            )
            family.figures = cfg['figures'](family, suit)

            fig = screen._config_fig_to_figure({
                'id': 11,
                'family_name': family_name,
                'name': family_name,
                'suit': suit,
                'description': cfg['description'],
            }, {family_name: family})

            assert fig.cannot_attack is False

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

    def test_mobile_right_panel_controls_do_not_overlap_on_iphone_se(self):
        _run_mobile_geometry_check(r'''
from types import SimpleNamespace
from unittest.mock import MagicMock
import pygame
pygame.mouse.set_cursor = lambda *args, **kwargs: None
pygame.init()
pygame.display.set_mode((854, 480))
from config import settings
from game.screens.defence_screen import DefenceScreen

state = SimpleNamespace(
    screen='defence',
    defence_land_id=7,
    game=MagicMock(),
    set_msg=MagicMock(),
    action={},
)
screen = DefenceScreen(state)
screen._land_id = 7
screen._config = {
    'figures': [],
    'battle_moves': [],
    'prelude_spell_name': None,
    'battle_figure_id': None,
    'battle_figure_id_2': None,
    'counter_spell_name': None,
    'counter_spell_card_ids': None,
    'counter_spell_target_figure_id': None,
    'auto_gamble': True,
    'auto_gamble_threshold': 8,
    'draft_dirty': False,
}
screen._build_layout()

assert screen._battle_plan_rect.bottom < screen._prelude_panel_rect.top
assert screen._prelude_panel_rect.bottom < screen._counter_panel_rect.top
assert screen._counter_panel_rect.bottom <= screen._btn_save.top

for child in (
    screen._move_slots_rect,
    screen._btn_auto_gamble,
    screen._btn_auto_gamble_dec,
    screen._auto_gamble_threshold_rect,
    screen._btn_auto_gamble_inc,
):
    assert screen._battle_plan_rect.contains(child), (
        tuple(screen._battle_plan_rect), tuple(child))

for child in (screen._prelude_spell_rect,):
    assert screen._prelude_panel_rect.contains(child), (
        tuple(screen._prelude_panel_rect), tuple(child))
for child in (screen._battle_figure_rect, screen._counter_spell_rect):
    assert screen._counter_panel_rect.contains(child), (
        tuple(screen._counter_panel_rect), tuple(child))

controls = [
    screen._btn_auto_gamble,
    screen._btn_auto_gamble_dec,
    screen._auto_gamble_threshold_rect,
    screen._btn_auto_gamble_inc,
]
for rect in controls:
    assert not rect.colliderect(screen._move_slots_rect), (
        tuple(rect), tuple(screen._move_slots_rect))
    assert rect.h >= settings.TOUCH_COMPACT_MIN
info = screen._info_button_rects['battle_plan']
assert not screen._btn_auto_gamble_inc.colliderect(info)
caption_x = screen._counter_spell_rect.right + int(0.012 * settings.SCREEN_WIDTH)
caption_right = screen._counter_panel_rect.right - int(0.010 * settings.SCREEN_WIDTH)
caption_w = max(0, caption_right - caption_x)
assert screen._res_font.size('No counter')[0] <= caption_w

records = []
screen._draw_section_panel = (
    lambda rect, title, *, description=None, icon_rect=None, title_pos=None:
        records.append((title, description))
)
screen._draw_info_buttons = lambda: None
screen._draw_right_panels()
assert records == [
    ('Battle Plan', None),
    ('Prelude Spell', None),
    ('Defender Response', None),
]
pygame.quit()
''')

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
            'battle_plan', 'prelude_spell', 'defender_response', 'auto_gamble'
        }
        assert screen._battle_plan_rect.contains(screen._info_button_rects['battle_plan'])
        assert screen._prelude_panel_rect.contains(screen._info_button_rects['prelude_spell'])
        assert screen._counter_panel_rect.contains(screen._info_button_rects['defender_response'])
        # The auto-gamble (i) sits in the Battle Plan panel next to the stepper.
        assert screen._battle_plan_rect.contains(screen._info_button_rects['auto_gamble'])

    def test_auto_gamble_info_button_opens_popup(self):
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
            pos=screen._info_button_rects['auto_gamble'].center,
        )
        screen.handle_events([event])
        assert screen._active_info_key == 'auto_gamble'

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

    def test_castle_cap_indicator_skips_until_castle_full(self, monkeypatch):
        from config import settings
        from game.screens import defence_screen as module
        import pygame

        screen = module.DefenceScreen.__new__(module.DefenceScreen)
        screen.window = pygame.Surface((240, 180))
        screen._field_rects = {'castle': pygame.Rect(20, 20, 150, 120)}
        screen._land = {'tier': 3}
        screen._config = {
            'figures': [{'field': 'castle'}, {'field': 'castle'}],
        }
        screen._res_font = settings.get_font(settings.FS_TINY)
        calls = []
        monkeypatch.setattr(
            module,
            'draw_castle_cap_indicator',
            lambda *args, **kwargs: calls.append(args) or pygame.Rect(0, 0, 1, 1),
        )

        result = module.DefenceScreen._draw_castle_cap_indicator(screen)

        assert result is None
        assert calls == []


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

    def test_civil_war_battle_figure_selection_sends_same_color_pair(self):
        from game.screens.defence_screen import DefenceScreen
        import pygame
        state = _make_state()
        state.action = {}
        screen = DefenceScreen(state)
        screen._land_id = 7
        screen._config = _make_config(
            prelude_spell_name='Civil War',
            figures=[
                {'id': 10, 'has_deficit': False, 'field': 'village',
                 'color': 'offensive'},
                {'id': 11, 'has_deficit': False, 'field': 'village',
                 'color': 'offensive'},
            ],
        )
        screen._figure_objects = [
            _make_figure_object(10, field='village'),
            _make_figure_object(11, field='village'),
        ]
        screen._figure_icons = {
            10: SimpleNamespace(hovered=True, figure=SimpleNamespace(id=10)),
            11: SimpleNamespace(hovered=False, figure=SimpleNamespace(id=11)),
        }
        screen._selecting_battle_fig = True

        first = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(0, 0))
        second = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(0, 0))
        with patch.object(screen, '_server_set_battle_figure') as mock_set:
            screen.handle_events([first])
            assert screen._selecting_battle_fig is True
            assert screen._pending_civil_war_battle_fig_1 == 10
            mock_set.assert_not_called()

            screen._figure_icons[10].hovered = False
            screen._figure_icons[11].hovered = True
            screen.handle_events([second])

        mock_set.assert_called_once_with(10, 11)
        assert screen._selecting_battle_fig is False
        assert screen._pending_civil_war_battle_fig_1 is None

    def test_civil_war_battle_figure_selection_rejects_wrong_color_second(self):
        from game.screens.defence_screen import DefenceScreen
        import pygame
        state = _make_state()
        state.action = {}
        screen = DefenceScreen(state)
        screen._land_id = 7
        screen._config = _make_config(
            prelude_spell_name='Civil War',
            figures=[
                {'id': 10, 'has_deficit': False, 'field': 'village',
                 'color': 'offensive'},
                {'id': 11, 'has_deficit': False, 'field': 'village',
                 'color': 'defensive'},
                {'id': 12, 'has_deficit': False, 'field': 'village',
                 'color': 'offensive'},
            ],
        )
        screen._figure_objects = [
            _make_figure_object(10, field='village'),
            _make_figure_object(11, field='village'),
            _make_figure_object(12, field='village'),
        ]
        screen._pending_civil_war_battle_fig_1 = 10
        screen._selecting_battle_fig = True
        screen._figure_icons = {
            11: SimpleNamespace(hovered=True, figure=SimpleNamespace(id=11)),
        }

        with patch.object(screen, '_server_set_battle_figure') as mock_set:
            event = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(0, 0))
            screen.handle_events([event])

        mock_set.assert_not_called()
        assert screen._selecting_battle_fig is True
        assert screen._pending_civil_war_battle_fig_1 == 10
        state.set_msg.assert_called_with(
            'Civil War requires two battle figures of the same color')

    def test_civil_war_second_pick_rejects_sword_manufactory(self):
        from game.screens.defence_screen import DefenceScreen
        import pygame
        state = _make_state()
        state.action = {}
        screen = DefenceScreen(state)
        screen._land_id = 7
        screen._config = _make_config(
            prelude_spell_name='Civil War',
            figures=[
                {'id': 10, 'has_deficit': False, 'field': 'village',
                 'color': 'offensive'},
                {'id': 11, 'has_deficit': False, 'field': 'village',
                 'family_name': 'Sword Manufactory', 'color': 'offensive'},
                {'id': 12, 'has_deficit': False, 'field': 'village',
                 'color': 'offensive'},
            ],
        )
        screen._figure_objects = [
            _make_figure_object(10, field='village'),
            _make_figure_object(11, field='village', cannot_attack=True),
            _make_figure_object(12, field='village'),
        ]
        screen._pending_civil_war_battle_fig_1 = 10
        screen._selecting_battle_fig = True
        screen._figure_icons = {
            11: SimpleNamespace(hovered=True, figure=SimpleNamespace(id=11)),
        }

        with patch.object(screen, '_server_set_battle_figure') as mock_set:
            event = pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(0, 0))
            screen.handle_events([event])

        mock_set.assert_not_called()
        assert screen._selecting_battle_fig is True
        assert screen._pending_civil_war_battle_fig_1 == 10
        state.set_msg.assert_called_with(
            'This figure cannot counter-advance because it cannot attack')

    def test_civil_war_readiness_requires_second_same_color_battle_figure(self):
        from game.screens.defence_screen import DefenceScreen
        state = _make_state()
        screen = DefenceScreen(state)
        screen._config = _make_config(
            prelude_spell_name='Civil War',
            figures=[
                {'id': 10, 'has_deficit': False, 'field': 'village',
                 'color': 'offensive'},
                {'id': 11, 'has_deficit': False, 'field': 'village',
                 'color': 'defensive'},
            ],
            battle_moves=[
                {'id': 1, 'round_index': 0},
                {'id': 2, 'round_index': 1},
                {'id': 3, 'round_index': 2},
            ],
            battle_figure_id=10,
            battle_figure_id_2=11,
        )
        screen._figure_objects = [
            _make_figure_object(10, field='village'),
            _make_figure_object(11, field='village'),
        ]

        assert screen._is_defence_ready() is False
        assert 'same color' in ' '.join(screen._get_defence_problems())

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
        # Removals are free draft edits — the spell clears immediately,
        # without a confirmation dialog.
        with patch.object(screen, '_server_clear_counter_spell') as mock_clear:
            screen.handle_events([event])
            mock_clear.assert_called_once()
        assert screen.dialogue_box is None


class TestDefenceConfigPolish:

    class _FakePoller:
        def __init__(self, result):
            self._result = result
            self.busy = False

        def has_result(self):
            return True

        @property
        def result(self):
            return self._result

    def _drain_with_config(self, screen, cfg):
        screen._config_poller = self._FakePoller({
            'config_data': {'config': cfg, 'land': {'tier': 1}},
            'collection_data': {'cards': []},
        })
        screen._config_poller_land_id = screen._land_id
        with patch.object(screen, '_rebuild_figure_objects'):
            screen._drain_config_poller()

    def test_load_does_not_force_spell_target_selection(self):
        """A fresh load with a target-less Health Boost must not hijack the
        player into the dim target-pick overlay (passive caption suffices)."""
        from game.screens.defence_screen import DefenceScreen
        state = _make_state()
        screen = DefenceScreen(state)
        screen._land_id = 7
        cfg = _make_config(
            prelude_spell_name='Health Boost',
            figures=[{'id': 1, 'field': 'castle'}],
        )
        self._drain_with_config(screen, cfg)
        assert screen._selecting_spell_target is None

    def test_reload_after_subscreen_prompts_spell_target(self):
        """Right after the player picked a spell in the subscreen, the reload
        does prompt for the missing Health Boost target."""
        from game.screens.defence_screen import DefenceScreen
        state = _make_state()
        screen = DefenceScreen(state)
        screen._land_id = 7
        screen._prompt_spell_target_on_next_load = True
        cfg = _make_config(
            prelude_spell_name='Health Boost',
            figures=[{'id': 1, 'field': 'castle'}],
        )
        self._drain_with_config(screen, cfg)
        assert screen._selecting_spell_target == 'prelude'
        assert screen._prompt_spell_target_on_next_load is False

    def test_close_subscreen_uses_async_loader_and_flags_prompt(self):
        from game.screens.defence_screen import DefenceScreen
        state = _make_state()
        screen = DefenceScreen(state)
        screen._land_id = 7
        screen._active_subscreen = 'prelude_spell'
        screen._subscreen_obj = MagicMock()

        with patch.object(screen, '_start_config_load') as async_load, \
                patch.object(screen, '_load_config') as sync_load:
            screen._close_subscreen()

        async_load.assert_called_once()
        sync_load.assert_not_called()
        assert screen._active_subscreen is None
        assert screen._prompt_spell_target_on_next_load is True

    def test_empty_move_slot_click_opens_battle_shop(self):
        from game.screens.defence_screen import DefenceScreen
        import pygame
        state = _make_state()
        screen = DefenceScreen(state)
        screen._land_id = 7
        screen._config = _make_config()
        screen._build_layout()
        screen._draw_battle_move_slots()
        assert set(screen._empty_move_slot_rects) == {0, 1, 2}

        event = pygame.event.Event(
            pygame.MOUSEBUTTONUP, button=1,
            pos=screen._empty_move_slot_rects[0].center)
        with patch.object(screen, '_open_battle_shop') as mock_open:
            screen.handle_events([event])
            mock_open.assert_called_once()

    def test_error_retry_click_reloads_config(self):
        from game.screens import defence_screen as module
        import pygame
        state = _make_state()
        screen = module.DefenceScreen(state)
        screen._land_id = 7
        screen._error = 'Connection error'
        sw = module.settings.SCREEN_WIDTH
        sh = module.settings.SCREEN_HEIGHT
        screen._btn_retry = pygame.Rect(sw // 2 - 40, sh // 2, 80, 40)

        event = pygame.event.Event(
            pygame.MOUSEBUTTONUP, button=1, pos=screen._btn_retry.center)
        with patch.object(screen, '_start_config_load') as mock_load:
            screen.handle_events([event])
        assert screen._error is None
        mock_load.assert_called_once()
