# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Unit tests for ConquerScreen logic (Phase 11)."""
import pygame
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


def _make_power_figure(figure_id, *, field='village', suit='Hearts', value=10,
                       cannot_be_targeted=False):
    return SimpleNamespace(
        id=figure_id,
        suit=suit,
        family=SimpleNamespace(field=field),
        cannot_be_targeted=cannot_be_targeted,
        get_value=lambda value=value: value,
    )


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

    def test_update_starts_background_config_load(self):
        from game.screens.conquer_screen import ConquerScreen
        state = _make_state()
        screen = ConquerScreen(state)
        with patch.object(screen, '_load_config') as sync_load, \
                patch.object(screen, '_start_config_load') as async_load:
            screen.update([])
        assert screen._land_id == 42
        sync_load.assert_not_called()
        async_load.assert_called_once()


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


class TestConquerBattleMovePower:

    def test_call_tactic_power_uses_bound_field_figure_and_healer_bonus(self):
        from game.screens.conquer_screen import ConquerScreen

        screen = object.__new__(ConquerScreen)
        farm = _make_power_figure(2, field='village', suit='Hearts', value=13)
        screen._figure_objects = [farm]
        screen._figure_icons = {
            2: SimpleNamespace(has_deficit=False, buffs_allies_bonus=4),
        }
        move = {
            'family_name': 'Call Villager',
            'suit': 'Hearts',
            'value': 1,
            'call_figure_id': 2,
        }

        assert ConquerScreen._battle_move_display_power(screen, move) == 18

    def test_unbound_call_tactic_previews_best_eligible_field_figure(self):
        from game.screens.conquer_screen import ConquerScreen

        screen = object.__new__(ConquerScreen)
        weak = _make_power_figure(1, field='castle', suit='Spades', value=6)
        strong = _make_power_figure(2, field='castle', suit='Clubs', value=11)
        deficit = _make_power_figure(3, field='castle', suit='Spades', value=20)
        screen._figure_objects = [weak, strong, deficit]
        screen._figure_icons = {
            1: SimpleNamespace(has_deficit=False, buffs_allies_bonus=0),
            2: SimpleNamespace(has_deficit=False, buffs_allies_bonus=0),
            3: SimpleNamespace(has_deficit=True, buffs_allies_bonus=0),
        }
        move = {
            'family_name': 'Call King',
            'suit': 'Clubs',
            'value': 4,
            'call_figure_id': None,
        }

        assert ConquerScreen._battle_move_display_power(screen, move) == 15


class TestConquerCoachCopy:

    def test_final_conquer_coach_step_uses_new_battle_handoff_copy(self):
        from game.screens.conquer_screen import ConquerScreen

        screen = ConquerScreen.__new__(ConquerScreen)
        screen.state = SimpleNamespace(user_dict={'onboarding': {'menu_hints_seen': []}})
        screen._menu_coach_allowed_common = lambda: True
        screen._conquer_coach_ready = lambda: True
        screen._loading = False
        screen._error = None
        screen._config = {'figures': [], 'battle_moves': []}
        screen._layout_built = True
        screen._active_subscreen = None
        screen._figure_detail_box = None
        screen._move_detail_box = None
        screen._active_info_key = None
        screen._menu_coach_seen = lambda: set()
        screen._conquer_field_coach_rect = lambda: pygame.Rect(0, 0, 0, 0)
        screen._conquer_combined_rect = lambda *rects: None
        screen._battle_plan_rect = None
        screen._btn_buy_move = None
        screen._prelude_panel_rect = None
        screen._btn_prelude_edit = None
        screen._prelude_spell_rect = None
        screen._btn_build = None
        screen._btn_battle = pygame.Rect(100, 100, 120, 48)

        step = ConquerScreen._current_conquer_coach_step(screen)

        # The pre-assembled first attack is now taught by a single window that
        # orients the player and hands off to Start Battle.
        assert step['id'] == 'conquer_config_to_battle'
        assert step['title'] == 'Your Attack Is Ready'
        assert 'guided tour ends here' not in step['body']
        assert 'pre-built this attack' in step['body']
        assert 'prelude draws cards' in step['body']
        assert 'only looted cards are gone' in step['body']
        assert step['button_label'] == 'Got it'


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

    def test_battle_confirmation_lists_all_committed_cards_as_loot_risk(self):
        from game.screens.conquer_screen import ConquerScreen
        import pygame
        state = _make_state()
        screen = ConquerScreen(state)
        screen._land = {
            'tier': 2,
            'kingdom_bonuses': {'loot_chance': 0.10},
        }
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

        assert 'committed to this conquer battle' in msg
        assert [group['key'] for group in image_groups] == ['loot_risk']
        group = image_groups[0]
        assert group['icon'] == 'lock'
        assert group['badge_icon'] == 'lock'
        assert len(group['items']) == 4
        assert 'Locked now:' in group['description']
        assert 'Loot risk:' in group['description']
        assert 'defender loots 3 of these 4 cards' in group['description']
        assert 'Tier 2 quota' in group['description']
        assert 'Defensive Looting adds a 10% extra roll' in group['description']
        assert 'does not consume cards by itself' in after_msg

    def test_battle_button_label_shows_cooldown_and_map(self, monkeypatch):
        from game.screens.conquer_screen import ConquerScreen
        state = _make_state()
        screen = ConquerScreen(state)
        screen._config = {
            'figures': [{'id': 1, 'has_deficit': False}],
            'battle_moves': [{'id': 1}, {'id': 2}, {'id': 3}],
        }
        screen._cooldown_remaining = 125
        screen._cooldown_synced_at_ms = 1000
        screen._maps_available = 2
        monkeypatch.setattr('pygame.time.get_ticks', lambda: 1000)

        assert screen._battle_button_label() == 'Cooldown 2m 05s'

    def test_cooldown_click_offers_map_before_battle_confirm(self, monkeypatch):
        from game.screens.conquer_screen import ConquerScreen
        state = _make_state()
        screen = ConquerScreen(state)
        screen._config = {
            'figures': [{'id': 1, 'has_deficit': False}],
            'battle_moves': [{'id': 1}, {'id': 2}, {'id': 3}],
        }
        screen._cooldown_remaining = 65
        screen._cooldown_synced_at_ms = 1000
        screen._maps_available = 1
        monkeypatch.setattr('pygame.time.get_ticks', lambda: 1000)

        screen._on_battle_click()

        assert screen._pending_map_confirm is True
        assert screen._pending_battle_confirm is False

    def test_use_map_response_opens_battle_confirm(self):
        from game.screens.conquer_screen import ConquerScreen
        state = _make_state()
        screen = ConquerScreen(state)
        state.action = {'status': 'use map'}
        screen._pending_map_confirm = True

        with patch.object(screen, '_open_battle_confirm') as mock_confirm, \
                patch.object(screen, '_start_battle') as mock_start:
            screen.handle_events([])

        mock_confirm.assert_called_once_with(use_map=True)
        mock_start.assert_not_called()

    def test_web_start_battle_uses_async_handoff(self, monkeypatch):
        from game.screens import conquer_screen as module

        state = _make_state()
        state.user_dict = {'maps': 2}
        screen = module.ConquerScreen(state)
        screen._land_id = 1942
        screen._cooldown_remaining = 0
        screen._cooldown_synced_at_ms = 1000
        monkeypatch.setattr(module._sys, 'platform', 'emscripten')
        monkeypatch.setattr(module.pygame.time, 'get_ticks', lambda: 1000)

        posted = {}

        def _fake_start_post_json(url, payload):
            posted['url'] = url
            posted['payload'] = payload
            return 7

        def _unexpected_sync_post(*_args, **_kwargs):
            raise AssertionError('web start battle must not use sync POST')

        monkeypatch.setattr(
            module.requests, 'start_async_post_json', _fake_start_post_json,
            raising=False)
        monkeypatch.setattr(module.requests, 'post', _unexpected_sync_post)

        screen._start_battle(use_map=True)

        assert posted['url'].endswith('/kingdom/conquer/start_battle')
        assert posted['payload'] == {'land_id': 1942, 'use_map': True}
        assert screen._start_battle_rid == 7
        assert screen._loading is True
        assert screen._loading_message == 'Starting conquer battle...'

    def test_web_start_battle_fetches_game_before_transition(self, monkeypatch):
        from game.screens import conquer_screen as module

        state = _make_state()
        state.user_dict = {'maps': 2}
        screen = module.ConquerScreen(state)
        screen._land_id = 1942
        screen._start_battle_rid = 7
        screen._loading = True
        monkeypatch.setattr(module._sys, 'platform', 'emscripten')

        class _Response:
            def __init__(self, status_code, data):
                self.status_code = status_code
                self._data = data
                self.text = ''

            def json(self):
                return self._data

        def _fake_check_async(rid):
            if rid == 7:
                return _Response(200, {
                    'game_id': 84,
                    'map_consumed': True,
                    'maps': 1,
                })
            if rid == 8:
                return _Response(200, {
                    'game': {'game_id': 84, 'mode': 'conquer'},
                })
            raise AssertionError(f'unexpected async rid {rid}')

        fetched = {}

        def _fake_start_get(url, params):
            fetched['url'] = url
            fetched['params'] = params
            return 8

        monkeypatch.setattr(module.requests, 'check_async', _fake_check_async,
                            raising=False)
        monkeypatch.setattr(module.requests, 'start_async_get', _fake_start_get,
                            raising=False)

        created = {}

        def _fake_game(game_dict, user_dict, lightweight=False):
            created['lightweight'] = lightweight
            return SimpleNamespace(
                game_id=game_dict['game_id'], mode=game_dict['mode'])

        monkeypatch.setattr(
            module, 'Game',
            _fake_game)

        screen._drain_start_battle_web()

        assert state.game_id == 84
        assert state.user_dict['maps'] == 1
        assert screen._maps_available == 1
        assert fetched == {
            'url': module.settings.SERVER_URL + '/games/get_game',
            'params': {'game_id': 84},
        }
        assert screen._start_battle_fetch_game_rid == 8
        assert screen._loading_message == 'Loading conquer battle...'

        screen._drain_start_battle_web()

        assert state.game.game_id == 84
        assert created['lightweight'] is True
        assert state.screen == 'conquer_game'
        assert screen._loading is False


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

    def test_config_figures_hide_instant_advance_in_conquer(self):
        from game.screens.conquer_screen import ConquerScreen
        state = _make_state()
        screen = ConquerScreen(state)
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

    def test_castle_cap_indicator_draws_when_castle_full(self, monkeypatch):
        from config import settings
        from game.screens import conquer_screen as module
        import pygame

        screen = module.ConquerScreen.__new__(module.ConquerScreen)
        screen.window = pygame.Surface((240, 180))
        screen._field_rects = {'castle': pygame.Rect(20, 20, 150, 120)}
        screen._land = {'tier': 2}
        screen._config = {
            'figures': [{'field': 'castle'}, {'field': 'castle'}],
        }
        screen._res_font = settings.get_font(settings.FS_TINY)
        calls = []

        def capture(window, rect, count, cap, font=None):
            calls.append((window, pygame.Rect(rect), count, cap, font))
            return pygame.Rect(rect)

        monkeypatch.setattr(module, 'draw_castle_cap_indicator', capture)

        result = module.ConquerScreen._draw_castle_cap_indicator(screen)

        assert result is not None
        assert calls
        assert calls[0][2:4] == (2, 2)


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
