# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Unit tests for ConquerScreen logic (Phase 11)."""
import os
from pathlib import Path
import pygame
import pytest
import subprocess
import sys
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

    def test_on_enter_clears_web_start_battle_requests(self):
        from game.screens.conquer_screen import ConquerScreen
        state = _make_state()
        screen = ConquerScreen(state)
        screen._start_battle_rid = 'start-rid'
        screen._start_battle_fetch_game_rid = 'fetch-rid'
        screen._start_battle_fetch_game_id = 99

        screen.on_enter()

        assert screen._start_battle_rid is None
        assert screen._start_battle_fetch_game_rid is None
        assert screen._start_battle_fetch_game_id is None


class TestConquerConfigLoading:

    class _Response:
        status_code = 200

        def __init__(self, payload):
            self._payload = payload

        def json(self):
            return self._payload

    def test_async_transform_uses_embedded_collection(self):
        from game.screens.conquer_screen import ConquerScreen

        embedded = {'cards': [{'suit': 'Hearts', 'rank': 'K', 'free': 1}]}
        result = ConquerScreen._transform_config_bundle_async({
            'config': self._Response({
                'success': True,
                'config': {},
                'collection': embedded,
            }),
        })

        assert result['collection_data'] == embedded

    def test_threaded_fetch_skips_second_request_when_collection_embedded(self):
        from game.screens import conquer_screen as module

        screen = object.__new__(module.ConquerScreen)
        embedded = {'cards': [{'suit': 'Spades', 'rank': '7', 'free': 2}]}
        response = self._Response({
            'success': True,
            'config': {},
            'collection': embedded,
        })

        with patch.object(module.requests, 'get', return_value=response), \
                patch.object(
                    module.collection_service,
                    'fetch_collection_cards',
                    side_effect=AssertionError('second collection request'),
                ):
            result = screen._fetch_config_bundle(42)

        assert result['collection_data'] == embedded

    def test_web_loader_requests_only_combined_config_endpoint(self):
        from game.screens import conquer_screen as module

        class Poller:
            busy = False

            def poll(self, args=None):
                self.args = args

        screen = module.ConquerScreen(_make_state())
        screen._land_id = 42
        with patch.object(module, 'BackgroundPoller', return_value=Poller()) as factory:
            screen._start_config_load()

        specs = factory.call_args.kwargs['async_requests']
        assert [spec['key'] for spec in specs] == ['config']
        assert specs[0]['url'].endswith('/kingdom/conquer/config')


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

    def test_royal_decree_requires_advanceable_castle_figure(self):
        figures = [
            {
                'id': 1,
                'has_deficit': False,
                'cannot_attack': False,
                'field': 'village',
            },
        ]
        moves = [
            {'id': 1, 'round_index': 0},
            {'id': 2, 'round_index': 1},
            {'id': 3, 'round_index': 2},
        ]
        screen = self._screen_with_config(figures, moves)
        screen._config['prelude_spell_name'] = 'Royal Decree'

        assert screen._is_battle_ready() is False
        assert any(
            'castle figure' in problem.lower()
            for problem in screen._get_battle_problems()
        )

        screen._config['figures'].append({
            'id': 2,
            'has_deficit': False,
            'cannot_attack': False,
            'field': 'castle',
        })
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
        assert 'We prepared your first attack' in step['body']
        assert '3 figures on the field' in step['body']
        assert '3 tactic moves to steer the battle' in step['body']
        assert 'prelude spell' in step['body']
        assert 'only looted cards' not in step['body']
        assert step['button_label'] == 'Start Battle'


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
        # Removals are free draft edits — the spell clears immediately,
        # without a confirmation dialog.
        with patch.object(screen, '_server_clear_prelude_spell') as mock_clear:
            screen.handle_events([event])
            mock_clear.assert_called_once()
        assert screen.dialogue_box is None


class TestConquerLootRiskTutorial:

    def test_start_battle_shows_one_time_loot_tutorial_before_start(self):
        from game.screens.conquer_screen import ConquerScreen
        import pygame
        state = _make_state()
        # Second conquest (first battle already finished): the loot lesson shows.
        state.user_dict = {'onboarding': {
            'menu_hints_seen': [],
            'completed_steps': ['finish_first_conquer_battle'],
        }}
        screen = ConquerScreen(state)
        screen._land_id = 42
        screen._config = {
            'figures': [{'id': 1, 'has_deficit': False}],
            'battle_moves': [{'id': 1}, {'id': 2}, {'id': 3}],
        }
        screen._cooldown_remaining = 0
        screen._cooldown_synced_at_ms = 1000
        seen = []
        screen._mark_menu_coach_seen = seen.append

        with patch.object(screen, '_start_battle') as mock_start:
            screen._on_battle_click()
            assert screen._loot_risk_tutorial_dialogue is not None
            mock_start.assert_not_called()

            win = screen._loot_risk_tutorial_dialogue
            win._created_at = pygame.time.get_ticks() - 1000
            event = pygame.event.Event(
                pygame.MOUSEBUTTONUP, button=1, pos=win._btn_next.rect.center)
            screen.handle_events([event])

        assert seen == ['loot_risk_intro']
        mock_start.assert_called_once_with(use_map=False)
        assert screen._loot_risk_tutorial_dialogue is None

    def test_first_tutorial_conquest_defers_loot_tutorial(self):
        # First guided conquest (no land won yet): the battle is risk-free, so
        # the loot lesson is deferred — Start Battle runs immediately.
        from game.screens.conquer_screen import ConquerScreen
        state = _make_state()
        state.user_dict = {'onboarding': {
            'menu_hints_seen': [],
            'completed_steps': [],
        }}
        screen = ConquerScreen(state)
        screen._land_id = 42
        screen._config = {
            'figures': [{'id': 1, 'has_deficit': False}],
            'battle_moves': [{'id': 1}, {'id': 2}, {'id': 3}],
        }
        screen._cooldown_remaining = 0
        screen._cooldown_synced_at_ms = 1000

        with patch.object(screen, '_start_battle') as mock_start:
            screen._on_battle_click()

        assert screen._loot_risk_tutorial_dialogue is None
        mock_start.assert_called_once_with(use_map=False)

    def test_start_battle_skips_loot_tutorial_once_seen(self):
        from game.screens.conquer_screen import ConquerScreen
        state = _make_state()
        state.user_dict = {'onboarding': {'menu_hints_seen': ['loot_risk_intro']}}
        screen = ConquerScreen(state)
        screen._land_id = 42
        screen._config = {
            'figures': [{'id': 1, 'has_deficit': False}],
            'battle_moves': [{'id': 1}, {'id': 2}, {'id': 3}],
        }
        screen._cooldown_remaining = 0
        screen._cooldown_synced_at_ms = 1000

        with patch.object(screen, '_start_battle') as mock_start:
            screen._on_battle_click()

        assert screen._loot_risk_tutorial_dialogue is None
        mock_start.assert_called_once_with(use_map=False)

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

    def test_cooldown_click_offers_map_before_starting_battle(self, monkeypatch):
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

    def test_use_map_response_starts_battle_without_old_confirm(self):
        from game.screens.conquer_screen import ConquerScreen
        state = _make_state()
        screen = ConquerScreen(state)
        state.action = {'status': 'use map'}
        screen._pending_map_confirm = True

        with patch.object(screen, '_start_battle') as mock_start:
            screen.handle_events([])

        mock_start.assert_called_once_with(use_map=True)

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

    def test_config_figures_show_live_conquer_checkmate_rule(self):
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

        assert fig.checkmate is True
        assert 'checkmate' in fig.description.lower()
        assert 'checkmate' in fig.family.description.lower()

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

    def test_mobile_right_panel_controls_do_not_overlap_on_iphone_se(self):
        _run_mobile_geometry_check(r'''
from types import SimpleNamespace
from unittest.mock import MagicMock
import pygame
pygame.mouse.set_cursor = lambda *args, **kwargs: None
pygame.init()
pygame.display.set_mode((854, 480))
from config import settings
from game.screens.conquer_screen import ConquerScreen

state = SimpleNamespace(
    screen='conquer',
    conquer_land_id=42,
    game=MagicMock(),
    set_msg=MagicMock(),
    action={},
)
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

for panel, child in (
    (screen._battle_plan_rect, screen._move_slots_rect),
    (screen._prelude_panel_rect, screen._prelude_spell_rect),
):
    assert panel.contains(child), (tuple(panel), tuple(child))

for control in (
    screen._btn_buy_move,
    screen._info_button_rects['battle_plan'],
):
    assert not control.colliderect(screen._move_slots_rect), (
        tuple(control), tuple(screen._move_slots_rect))

caption_x = screen._prelude_spell_rect.right + int(0.012 * settings.SCREEN_WIDTH)
caption_right = screen._prelude_panel_rect.right - int(0.010 * settings.SCREEN_WIDTH)
caption_w = max(0, caption_right - caption_x)
assert screen._res_font.size('No prelude spell')[0] <= caption_w

records = []
screen._draw_section_panel = (
    lambda rect, title, *, description=None, icon_rect=None, title_pos=None:
        records.append((title, description))
)
screen._draw_info_buttons = lambda: None
screen._draw_right_panels()
assert records == [('Battle Plan', None), ('Prelude Spell', None)]
pygame.quit()
''')

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


class TestNativeStartBattleAsync:
    """The native 'To Battle!' flow must not block the main thread."""

    def test_native_start_battle_is_async(self, monkeypatch):
        from game.screens import conquer_screen as module

        state = _make_state()
        state.user_dict = {'maps': 2}
        screen = module.ConquerScreen(state)
        screen._land_id = 1942
        screen._cooldown_remaining = 0
        screen._cooldown_synced_at_ms = 1000

        def _unexpected_sync_post(*_args, **_kwargs):
            raise AssertionError('native start battle must not block the main thread')

        monkeypatch.setattr(module.requests, 'post', _unexpected_sync_post)

        started = {}

        class _FakePoller:
            def __init__(self, func, *args, **kwargs):
                started['func'] = func
                self.busy = False

            def poll(self, args=()):
                started['args'] = args

            def has_result(self):
                return False

        monkeypatch.setattr(module, 'BackgroundPoller', _FakePoller)

        screen._start_battle(use_map=True)

        assert started['func'] == screen._start_battle_task
        assert started['args'] == (1942, True)
        assert screen._loading is True
        assert screen._loading_message == 'Starting conquer battle...'

    def test_native_drain_transitions_on_game_id(self, monkeypatch):
        from game.screens import conquer_screen as module

        state = _make_state()
        state.user_dict = {'maps': 2}
        screen = module.ConquerScreen(state)
        screen._land_id = 1942
        screen._loading = True

        class _DonePoller:
            busy = False

            def has_result(self):
                return True

            @property
            def result(self):
                return {
                    'data': {'game_id': 84, 'map_consumed': True, 'maps': 1},
                    'game_dict': {'id': 84},
                }

        screen._start_battle_poller = _DonePoller()

        fake_game = MagicMock()
        monkeypatch.setattr(module, 'Game', lambda *a, **k: fake_game)
        monkeypatch.setattr(module, 'gameplay_screen_for', lambda game: 'conquer_game')

        screen._drain_start_battle_native()

        assert screen._loading is False
        assert state.game_id == 84
        assert state.user_dict['maps'] == 1
        assert state.game is fake_game
        assert state.screen == 'conquer_game'
        assert screen._start_battle_poller is None

    def test_native_drain_error_surfaces_error(self):
        from game.screens.conquer_screen import ConquerScreen

        state = _make_state()
        screen = ConquerScreen(state)
        screen._loading = True

        class _ErrPoller:
            busy = False

            def has_result(self):
                return True

            @property
            def result(self):
                return {'error': 'Connection error'}

        screen._start_battle_poller = _ErrPoller()
        screen._drain_start_battle_native()

        assert screen._loading is False
        assert screen._error == 'Connection error'


class TestConquerConfigPolish:

    def test_error_retry_click_reloads_config(self):
        from game.screens import conquer_screen as module
        import pygame
        state = _make_state()
        state.action = {}
        screen = module.ConquerScreen(state)
        screen._land_id = 42
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

    def test_empty_move_slot_click_opens_battle_shop(self):
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
        screen._draw_battle_move_slots()
        assert set(screen._empty_move_slot_rects) == {0, 1, 2}

        event = pygame.event.Event(
            pygame.MOUSEBUTTONUP, button=1,
            pos=screen._empty_move_slot_rects[0].center)
        with patch.object(screen, '_open_battle_shop') as mock_open:
            screen.handle_events([event])
            mock_open.assert_called_once()

    def test_close_subscreen_uses_async_loader(self):
        from game.screens.conquer_screen import ConquerScreen
        state = _make_state()
        screen = ConquerScreen(state)
        screen._land_id = 42
        screen._active_subscreen = 'battle_shop'
        screen._subscreen_obj = MagicMock()

        with patch.object(screen, '_start_config_load') as async_load, \
                patch.object(screen, '_load_config') as sync_load:
            screen._close_subscreen()

        async_load.assert_called_once()
        sync_load.assert_not_called()
        assert screen._active_subscreen is None


class TestEntranceAnimations:
    """Draw-only slide-in animations for newly appearing config slots."""

    def _bare_screen(self):
        from game.screens.conquer_screen import ConquerScreen
        screen = object.__new__(ConquerScreen)
        screen._entrance_anims = {}
        screen._entrance_prev_sig = None
        screen._config = {
            'figures': [{'id': 7}],
            'battle_moves': [{'round_index': 0, 'family_name': 'Dagger'}],
            'prelude_spell_name': 'Poison',
        }
        return screen

    def test_new_config_registers_entrance_cascade(self, monkeypatch):
        monkeypatch.setattr('pygame.time.get_ticks', lambda: 5_000)
        screen = self._bare_screen()
        screen._sync_entrance_animations()
        assert ('fig', '7') in screen._entrance_anims
        assert ('move', 0) in screen._entrance_anims
        assert ('prelude',) in screen._entrance_anims
        # Cascade order: figures → moves → prelude.
        assert screen._entrance_anims[('fig', '7')]['index'] == 0
        assert screen._entrance_anims[('move', 0)]['index'] == 1
        assert screen._entrance_anims[('prelude',)]['index'] == 2
        # Same signature again: nothing new, nothing restarted.
        screen._entrance_anims.clear()
        screen._sync_entrance_animations()
        assert screen._entrance_anims == {}

    def test_config_change_animates_only_new_slot(self, monkeypatch):
        monkeypatch.setattr('pygame.time.get_ticks', lambda: 5_000)
        screen = self._bare_screen()
        screen._sync_entrance_animations()
        screen._entrance_anims.clear()
        screen._config['figures'].append({'id': 9})
        screen._sync_entrance_animations()
        assert list(screen._entrance_anims) == [('fig', '9')]

    def test_entrance_offset_lifecycle(self, monkeypatch):
        from game.screens.conquer_screen import ConquerScreen
        screen = self._bare_screen()
        screen._entrance_anims[('move', 0)] = {'started_at': 1_000, 'index': 1}
        stagger = ConquerScreen.ENTRANCE_STAGGER_MS
        slide = ConquerScreen.ENTRANCE_SLIDE_PX

        # Before this slot's staggered start: parked below its resting spot.
        monkeypatch.setattr('pygame.time.get_ticks', lambda: 1_000)
        assert screen._entrance_offset(('move', 0)) == (0, slide)

        # Mid-flight: partially risen (offset strictly between 0 and slide,
        # allowing the ease_out_back overshoot to dip slightly above rest).
        monkeypatch.setattr('pygame.time.get_ticks',
                            lambda: 1_000 + stagger + 95)
        dx, dy = screen._entrance_offset(('move', 0))
        assert dx == 0
        assert dy != 0
        assert dy < slide

        # Settled: no offset, record pruned.
        monkeypatch.setattr('pygame.time.get_ticks',
                            lambda: 1_000 + stagger + ConquerScreen.ENTRANCE_MS + 1)
        assert screen._entrance_offset(('move', 0)) == (0, 0)
        assert ('move', 0) not in screen._entrance_anims
        # Unknown keys are always settled.
        assert screen._entrance_offset(('move', 99)) == (0, 0)

    def test_icon_entrance_draw_restores_logical_position(self, monkeypatch):
        screen = self._bare_screen()
        screen._entrance_anims[('fig', '7')] = {'started_at': 1_000, 'index': 0}
        calls = []
        icon = SimpleNamespace(
            draw=lambda x, y: calls.append(('draw', x, y)),
            set_position=lambda x, y: calls.append(('set_position', x, y)))

        # Mid-entrance: the draw is offset but the logical position (used by
        # hover / detail-open hit tests) is restored to the resting spot.
        monkeypatch.setattr('pygame.time.get_ticks', lambda: 1_095)
        screen._draw_icon_with_entrance(icon, 100, 200, 7)
        assert calls[0][0] == 'draw'
        assert calls[0][2] != 200        # visually offset
        assert calls[-1] == ('set_position', 100, 200)

        # Settled: plain draw, no restore needed.
        calls.clear()
        monkeypatch.setattr('pygame.time.get_ticks', lambda: 60_000)
        screen._draw_icon_with_entrance(icon, 100, 200, 7)
        assert calls == [('draw', 100, 200)]

    def test_move_slot_x_button_suppressed_during_entrance(self, monkeypatch):
        import game.screens.conquer_screen as module
        state = _make_state()
        state.action = {}
        screen = module.ConquerScreen(state)
        screen._land_id = 42
        screen._config = {
            'figures': [],
            'battle_moves': [
                {'round_index': 0, 'family_name': 'Dagger',
                 'suit': 'Hearts', 'value': 3},
            ],
            'prelude_spell_name': None,
        }
        screen._build_layout()
        monkeypatch.setattr('pygame.time.get_ticks', lambda: 50_000)
        screen._sync_entrance_animations()
        assert ('move', 0) in screen._entrance_anims
        # Force the "always show X" (touch) branch so visibility is purely
        # driven by the entrance gate.
        monkeypatch.setattr(module.settings, 'TOUCH_TARGET_MIN', 48)

        screen._draw_battle_move_slots()          # mid-entrance
        assert 0 not in screen._move_remove_rects

        monkeypatch.setattr('pygame.time.get_ticks', lambda: 60_000)
        screen._draw_battle_move_slots()          # settled
        assert 0 in screen._move_remove_rects
