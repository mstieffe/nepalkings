# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Regression tests for the dedicated conquer battle screen shell."""

from types import SimpleNamespace

import pygame


def _conquer_screen_class():
    from game.screens.conquer_game_screen import ConquerGameScreen

    return ConquerGameScreen


def _game_screen_class():
    from game.screens.game_screen import GameScreen

    return GameScreen


def _base_conquer_screen(game=None):
    ConquerGameScreen = _conquer_screen_class()
    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen.state = SimpleNamespace(
        screen='conquer_game',
        subscreen='field',
        game=game or SimpleNamespace(mode='conquer'),
        pending_conquer_prelude_target=None,
    )
    screen.subscreens = {
        'field': SimpleNamespace(conquer_own_defender_mode=False),
        'battle_shop': SimpleNamespace(bought_moves=[]),
        'battle': SimpleNamespace(),
    }
    screen._last_conquer_auto_route_key = None
    screen._conquer_auto_ready_attempt_key = None
    return ConquerGameScreen, screen


class TestGameplayScreenRouting:
    def test_conquer_games_route_to_conquer_game_screen(self):
        from game.core.screen_routing import gameplay_screen_for

        assert gameplay_screen_for(SimpleNamespace(mode='conquer')) == 'conquer_game'

    def test_duel_games_route_to_duel_game_screen(self):
        from game.core.screen_routing import gameplay_screen_for

        assert gameplay_screen_for(SimpleNamespace(mode='duel')) == 'game'
        assert gameplay_screen_for(SimpleNamespace()) == 'game'

    def test_duel_game_screen_redirects_accidental_conquer_game(self):
        GameScreen = _game_screen_class()
        screen = GameScreen.__new__(GameScreen)
        screen.state = SimpleNamespace(
            screen='game',
            game=SimpleNamespace(mode='conquer'),
        )

        assert GameScreen._ensure_duel_screen_game(screen) is False
        assert screen.state.screen == 'conquer_game'

    def test_conquer_game_screen_redirects_accidental_duel_game(self):
        ConquerGameScreen, screen = _base_conquer_screen(
            SimpleNamespace(mode='duel'))

        assert ConquerGameScreen._ensure_conquer_screen_game(screen) is False
        assert screen.state.screen == 'game'

    def test_game_screens_set_active_parent_on_enter(self):
        GameScreen = _game_screen_class()
        duel = GameScreen.__new__(GameScreen)
        duel.state = SimpleNamespace(
            screen='game',
            game=SimpleNamespace(mode='duel'),
        )

        GameScreen.on_enter(duel)
        assert duel.state.parent_screen is duel

        ConquerGameScreen, conquer = _base_conquer_screen(
            SimpleNamespace(mode='conquer'))
        ConquerGameScreen.on_enter(conquer)

        assert conquer.state.parent_screen is conquer
        assert conquer.state.subscreen == 'field'


class TestConquerGameShell:
    def test_initializes_only_three_conquer_tab_buttons(self):
        from config import settings

        ConquerGameScreen = _conquer_screen_class()
        screen = ConquerGameScreen.__new__(ConquerGameScreen)
        screen.window = pygame.Surface((1200, 800))
        screen.state = SimpleNamespace(game=SimpleNamespace(turn=True), subscreen='field')

        ConquerGameScreen.initialize_buttons(screen)

        names = [button.name for button in screen.game_buttons]
        # Battle-shop is no longer surfaced as a tab — the user is auto-routed
        # there during the moves phase by the timeline panel.
        assert names == [
            'conquer_view_field',
            'conquer_view_battle',
        ]
        assert all('build' not in name for name in names)
        assert all('spell' not in name for name in names)
        assert all('log' not in name for name in names)
        assert screen.battle_button.locked is False
        assert screen.field_button.x == screen.battle_button.x
        assert screen.field_button.y < screen.battle_button.y
        sub_x, _sub_y = ConquerGameScreen._conquer_subscreen_origin(screen)
        assert screen.field_button.x + settings.FIELD_BUTTON_WIDTH < sub_x

    def test_normalizes_hidden_duel_subscreen_to_field(self):
        ConquerGameScreen, screen = _base_conquer_screen()
        screen.state.subscreen = 'build_figure'

        ConquerGameScreen._normalize_conquer_subscreen(screen)

        assert screen.state.subscreen == 'field'

    def test_conquer_subscreen_origin_is_centered_below_header(self):
        from config import settings

        ConquerGameScreen, screen = _base_conquer_screen()

        x, y = ConquerGameScreen._conquer_subscreen_origin(screen)

        assert x == (settings.SCREEN_WIDTH - settings.SUB_SCREEN_BACKGROUND_IMG_WIDTH) // 2
        assert y > int(settings.SCREEN_HEIGHT * ConquerGameScreen.HEADER_H_FACTOR)
        assert y > settings.SUB_SCREEN_Y

    def test_auto_routes_to_field_once_for_required_field_action(self):
        game = SimpleNamespace(
            mode='conquer',
            pending_conquer_prelude_target=True,
            pending_spell_id=99,
        )
        ConquerGameScreen, screen = _base_conquer_screen(game)
        screen.state.subscreen = 'battle'

        ConquerGameScreen._auto_route_conquer_once(screen)
        assert screen.state.subscreen == 'field'

        screen.state.subscreen = 'battle'
        ConquerGameScreen._auto_route_conquer_once(screen)
        assert screen.state.subscreen == 'battle'

    def test_auto_routes_to_battle_shop_once_for_move_confirmation(self):
        # The auto_route helper itself does not move the user to the
        # battle_shop subscreen anymore — that is handled by
        # ``_enforce_battle_shop_during_moves`` so the user is forced there
        # during the moves phase.
        game = SimpleNamespace(
            mode='conquer',
            battle_moves_phase=True,
            battle_moves_ready=False,
            waiting_for_opponent_battle_moves=False,
            battle_confirmed=False,
        )
        ConquerGameScreen, screen = _base_conquer_screen(game)
        screen.battle_button = SimpleNamespace(locked=False)
        screen.state.subscreen = 'field'
        screen._conquer_left_battle_shop_at = 0
        screen.BATTLE_SHOP_SNAPBACK_MS = 0  # snap immediately for the test.

        ConquerGameScreen._enforce_battle_shop_during_moves(screen)
        # First call records the timestamp.  Second call snaps back.
        ConquerGameScreen._enforce_battle_shop_during_moves(screen)

        assert screen.state.subscreen == 'battle_shop'

    def test_auto_routes_to_battle_when_battle_has_started(self):
        game = SimpleNamespace(
            mode='conquer',
            battle_confirmed=True,
            battle_turn_player_id=20,
            battle_round=1,
        )
        ConquerGameScreen, screen = _base_conquer_screen(game)
        screen.state.subscreen = 'field'

        ConquerGameScreen._auto_route_conquer_once(screen)

        assert screen.state.subscreen == 'battle'

    def test_auto_routes_tactics_hand_battle_to_field(self):
        game = SimpleNamespace(
            mode='conquer',
            conquer_move_model='tactics_hand',
            battle_confirmed=True,
            battle_turn_player_id=42,
            battle_round=1,
            player_id=42,
        )
        ConquerGameScreen, screen = _base_conquer_screen(game)
        screen.state.subscreen = 'battle'

        ConquerGameScreen._auto_route_conquer_once(screen)

        assert screen.state.subscreen == 'field'

    def test_attention_counts_mark_required_tabs(self):
        game = SimpleNamespace(
            mode='conquer',
            pending_forced_advance=True,
            advancing_figure_id=None,
            battle_confirmed=True,
            battle_turn_player_id=20,
            pending_conquer_prelude_target=False,
            pending_defender_selection=False,
            pending_conquer_own_defender_selection=False,
            civil_war_awaiting_second=False,
            civil_war_defender_second=False,
        )
        ConquerGameScreen, screen = _base_conquer_screen(game)

        counts = ConquerGameScreen._conquer_attention_counts(screen)

        # battle_shop no longer has a dedicated tab — its attention is
        # surfaced via the timeline panel + auto-routing instead.
        assert counts == {'field': 1, 'battle': 1}

    def test_attention_counts_keep_tactics_hand_battle_on_field(self):
        game = SimpleNamespace(
            mode='conquer',
            conquer_move_model='tactics_hand',
            battle_confirmed=True,
            battle_turn_player_id=20,
            pending_conquer_prelude_target=False,
            pending_forced_advance=False,
            pending_defender_selection=False,
            pending_conquer_own_defender_selection=False,
            civil_war_awaiting_second=False,
            civil_war_defender_second=False,
        )
        ConquerGameScreen, screen = _base_conquer_screen(game)

        counts = ConquerGameScreen._conquer_attention_counts(screen)

        assert counts == {'field': 1, 'battle': 0}

    def test_confirming_figure_selection_acknowledges_selection_step(self):
        ConquerGameScreen, screen = _base_conquer_screen()
        screen._conquer_pending_confirmation = {'kind': 'advance'}
        screen._conquer_acknowledged_step_kinds = set()
        screen._conquer_timeline_step_started_at = {}
        screen.subscreens['field'] = SimpleNamespace(
            confirm_pending_advance=lambda: True)

        handled = ConquerGameScreen._handle_conquer_objective_action(
            screen, 'confirm')

        assert handled is True
        assert 'attacker' in screen._conquer_acknowledged_step_kinds

    def test_auto_confirms_conquer_moves_when_shop_has_no_changes(self, monkeypatch):
        game = SimpleNamespace(
            mode='conquer',
            game_id=12,
            player_id=3,
            battle_confirmed=True,
            battle_turn_player_id=None,
            battle_moves_phase=True,
            battle_moves_ready=False,
            waiting_for_opponent_battle_moves=False,
            both_battle_moves_ready=False,
            _game_data_version=1,
        )
        ConquerGameScreen, screen = _base_conquer_screen(game)
        screen.state.subscreen = 'field'
        screen.subscreens['battle_shop'] = SimpleNamespace(
            bought_moves=[{'id': 1}, {'id': 2}, {'id': 3}],
            card_source=None,
            game=game,
            _load_bought_moves=lambda: None,
            _can_ready_for_battle=lambda: True,
            has_available_battle_move_changes=lambda: False,
        )

        monkeypatch.setattr(
            'utils.battle_shop_service.confirm_battle_moves',
            lambda game_id, player_id: {'success': True, 'both_ready': True},
        )

        handled = ConquerGameScreen._auto_confirm_conquer_battle_moves_if_no_changes(screen)

        assert handled is True
        assert screen.state.subscreen == 'battle'
        assert game.battle_moves_phase is False
        assert game.both_battle_moves_ready is True

    def test_keeps_conquer_shop_when_move_changes_exist(self, monkeypatch):
        game = SimpleNamespace(
            mode='conquer',
            game_id=12,
            player_id=3,
            battle_confirmed=True,
            battle_turn_player_id=None,
            battle_moves_phase=True,
            battle_moves_ready=False,
            waiting_for_opponent_battle_moves=False,
            both_battle_moves_ready=False,
            _game_data_version=1,
        )
        ConquerGameScreen, screen = _base_conquer_screen(game)
        screen.battle_button = SimpleNamespace(locked=False)
        screen.subscreens['battle_shop'] = SimpleNamespace(
            bought_moves=[{'id': 1}, {'id': 2}, {'id': 3}],
            card_source=None,
            game=game,
            _load_bought_moves=lambda: None,
            _can_ready_for_battle=lambda: True,
            has_available_battle_move_changes=lambda: True,
        )
        called = []
        monkeypatch.setattr(
            'utils.battle_shop_service.confirm_battle_moves',
            lambda game_id, player_id: called.append((game_id, player_id)),
        )

        handled = ConquerGameScreen._auto_confirm_conquer_battle_moves_if_no_changes(screen)

        assert handled is False
        assert called == []

    def test_battle_shop_reloads_moves_when_game_data_version_changes(self):
        from game.screens.battle_shop_screen import BattleShopScreen

        game = SimpleNamespace(
            game_id=12,
            player_id=3,
            _game_data_version=2,
            battle_moves_phase=True,
            battle_confirmed=True,
        )
        screen = BattleShopScreen.__new__(BattleShopScreen)
        screen.game = game
        screen.mode = 'duel'
        screen.card_source = SimpleNamespace(game=game)
        screen.buttons = []
        screen.scroll_text_list_shifter = None
        screen._loaded_game_key = (12, 3)
        screen._loaded_bought_moves_key = (12, 3, 1)
        screen.bought_moves = [{'id': 1}, {'id': 2}, {'id': 3}]
        screen._battle_moves_confirmed = False
        screen._waiting_for_opponent = False
        screen.confirm_button = SimpleNamespace(disabled=True, update=lambda: None)
        screen.ready_button = SimpleNamespace(disabled=True, update=lambda: None)
        screen.move_family_buttons = []
        screen._can_ready_for_battle = lambda: True
        screen._update_icon_states = lambda: None
        figure_loads = []
        screen._load_player_figures = lambda: figure_loads.append('figures')
        move_loads = []

        def _reload_moves():
            move_loads.append('moves')
            screen.bought_moves = [{'id': 1}, {'id': 2}]
            screen._loaded_game_key = BattleShopScreen._game_identity_key(screen, game)
            screen._loaded_bought_moves_key = BattleShopScreen._bought_moves_cache_key(screen, game)

        screen._load_bought_moves = _reload_moves

        BattleShopScreen.update(screen, game)

        assert move_loads == ['moves']
        assert figure_loads == []
        assert screen.confirm_button.disabled is False

    def test_invader_swap_own_defender_mode_uses_own_selectable_update(self):
        game = SimpleNamespace(
            mode='conquer',
            player_id=1,
            invader=True,
            advancing_player_id=2,
            pending_defender_selection=False,
            defender_selection_dialogue_shown=False,
            pending_conquer_own_defender_selection=False,
            conquer_own_defender_selection_shown=False,
            civil_war_defender_second=True,
            cached_active_spells=[{
                'spell_name': 'Invader Swap',
                'effect_data': {
                    'conquer_invader_swap': True,
                    'old_invader_id': 1,
                },
            }],
        )
        ConquerGameScreen, screen = _base_conquer_screen(game)
        calls = []
        field = SimpleNamespace(
            defender_selection_mode=False,
            conquer_own_defender_mode=False,
            _update_defender_selectable=lambda: calls.append('opponent'),
            _update_conquer_own_defender_selectable=lambda: calls.append('own'),
            _reset_defender_selectable=lambda: calls.append('reset'),
        )
        screen.subscreens['field'] = field

        ConquerGameScreen._sync_conquer_action_modes(screen)

        assert field.conquer_own_defender_mode is True
        assert calls == ['own']

    def test_own_defender_selectability_excludes_first_civil_war_pick(self):
        from game.screens.field_screen import FieldScreen

        def figure(fig_id, *, player_id=1, color='offensive', field='village'):
            return SimpleNamespace(
                id=fig_id,
                player_id=player_id,
                name=f'Figure {fig_id}',
                family=SimpleNamespace(color=color, field=field),
            )

        first = figure(20)
        second = figure(21)
        wrong_color = figure(22, color='defensive')
        opponent = figure(23, player_id=2)
        icons = [
            SimpleNamespace(
                figure=f,
                has_deficit=False,
                defender_selectable=None,
                in_defender_selection_mode=False,
            )
            for f in (first, second, wrong_color, opponent)
        ]
        field = FieldScreen.__new__(FieldScreen)
        field.game = SimpleNamespace(
            player_id=1,
            battle_modifier=[{'type': 'Civil War'}],
            defending_figure_id=20,
            civil_war_defender_second=True,
            civil_war_required_color='offensive',
        )
        field.figure_icons = icons

        FieldScreen._update_conquer_own_defender_selectable(field)

        assert [icon.defender_selectable for icon in icons] == [False, True, False, False]

    def test_battle_result_attack_failed_is_shown_once(self):
        from game.screens.battle_screen import BattleScreen

        game = SimpleNamespace(
            player_id=1,
            invader=True,
            cached_active_spells=[],
            _conquer_result_dialogue_shown=False,
        )
        battle = BattleScreen.__new__(BattleScreen)
        battle.game = game
        battle.window = pygame.Surface((100, 100))
        shown = []

        def fake_dialogue(message, actions, icon, title, images=None):
            shown.append({
                'message': message,
                'actions': actions,
                'icon': icon,
                'title': title,
                'images': images,
            })

        battle.make_dialogue_box = fake_dialogue

        result = {
            'attacker_won': False,
            'conquer_result': 'defender_won',
            'conquer_attacker_player_id': 1,
        }

        BattleScreen._handle_conquer_end(battle, result)
        BattleScreen._handle_conquer_end(battle, result)

        assert len(shown) == 1
        assert shown[0]['title'] == 'Attack Failed'
        assert 'defender held their ground' not in shown[0]['message'].lower()
        assert game._conquer_result_dialogue_shown is True


class TestConquerSubscreenLayout:
    def test_field_compartments_translate_with_conquer_subscreen_origin(self):
        from config import settings
        from game.screens.field_screen import FieldScreen

        ConquerGameScreen, conquer = _base_conquer_screen()
        sub_x, sub_y = ConquerGameScreen._conquer_subscreen_origin(conquer)

        field = FieldScreen.__new__(FieldScreen)
        field._layout_offset_x = sub_x - settings.SUB_SCREEN_X
        field._layout_offset_y = sub_y - settings.SUB_SCREEN_Y

        FieldScreen.init_field_compartments(field)

        assert field.compartments['self']['castle'].topleft == (
            settings.FIELD_SELF_X + field._layout_offset_x,
            settings.FIELD_Y + field._layout_offset_y,
        )

        bg_rect = pygame.Rect(
            sub_x, sub_y,
            settings.SUB_SCREEN_BACKGROUND_IMG_WIDTH,
            settings.SUB_SCREEN_BACKGROUND_IMG_HEIGHT,
        )
        all_compartments = [
            rect
            for player in field.compartments.values()
            for rect in player.values()
        ]
        layout_rect = all_compartments[0].unionall(all_compartments[1:])

        assert bg_rect.contains(layout_rect)

    def test_field_compartments_keep_duel_coordinates_at_default_origin(self):
        from config import settings
        from game.screens.field_screen import FieldScreen

        field = FieldScreen.__new__(FieldScreen)
        field._layout_offset_x = 0
        field._layout_offset_y = 0

        FieldScreen.init_field_compartments(field)

        assert field.compartments['self']['castle'].topleft == (
            settings.FIELD_SELF_X,
            settings.FIELD_Y,
        )

    def test_battle_panels_translate_with_conquer_subscreen_origin(self):
        from config import settings
        from game.screens.battle_screen import BattleScreen

        ConquerGameScreen, conquer = _base_conquer_screen()
        sub_x, sub_y = ConquerGameScreen._conquer_subscreen_origin(conquer)

        battle = BattleScreen.__new__(BattleScreen)
        battle._layout_offset_x = sub_x - settings.SUB_SCREEN_X
        battle._layout_offset_y = sub_y - settings.SUB_SCREEN_Y

        bg_rect = pygame.Rect(
            sub_x, sub_y,
            settings.SUB_SCREEN_BACKGROUND_IMG_WIDTH,
            settings.SUB_SCREEN_BACKGROUND_IMG_HEIGHT,
        )

        panel_rects = [
            BattleScreen._battle_panel_rect(battle),
            BattleScreen._figures_panel_rect(battle),
            BattleScreen._rounds_panel_rect(battle),
        ]
        for rect in panel_rects:
            assert bg_rect.contains(rect)

        total_radius = settings.TOTAL_CIRCLE_RADIUS
        total_rect = pygame.Rect(
            BattleScreen._sx(battle, settings.TOTAL_CIRCLE_X) - total_radius,
            BattleScreen._sy(battle, settings.TOTAL_CIRCLE_Y) - total_radius,
            total_radius * 2,
            total_radius * 2,
        )
        finish_rect = pygame.Rect(
            BattleScreen._sx(battle, settings.FINISH_BTN_X) - settings.FINISH_BTN_W // 2,
            BattleScreen._sy(battle, settings.FINISH_BTN_Y),
            settings.FINISH_BTN_W,
            settings.FINISH_BTN_H,
        )

        assert bg_rect.contains(total_rect)
        assert bg_rect.contains(finish_rect)

    def test_battle_panel_helpers_keep_duel_coordinates_at_default_origin(self):
        from config import settings
        from game.screens.battle_screen import BattleScreen

        battle = BattleScreen.__new__(BattleScreen)
        battle._layout_offset_x = 0
        battle._layout_offset_y = 0

        assert BattleScreen._battle_panel_rect(battle).topleft == (
            settings.BATTLE_PANEL_X,
            settings.BATTLE_PANEL_Y,
        )
        assert BattleScreen._battle_panel_icon_center(battle, 2) == (
            settings.BATTLE_PANEL_X + settings.BATTLE_PANEL_W // 2,
            settings.BATTLE_PANEL_ICON_START_Y + 2 * settings.BATTLE_PANEL_ICON_DELTA_Y,
        )


class TestTacticsHandRouting:
    """Phase 9-10 redesign: tactics-hand games never visit ``battle_shop``."""

    def _make_screen(self, *, conquer_move_model='tactics_hand', battle_confirmed=False,
                     battle_moves_phase=False, battle_turn_player_id=None,
                     battle_round=0, last_battle_result=None):
        ConquerGameScreen, screen = _base_conquer_screen(SimpleNamespace(
            mode='conquer',
            conquer_move_model=conquer_move_model,
            battle_confirmed=battle_confirmed,
            battle_turn_player_id=battle_turn_player_id,
            battle_round=battle_round,
            battle_moves_phase=battle_moves_phase,
            battle_moves_ready=False,
            waiting_for_opponent_battle_moves=False,
            both_battle_moves_ready=False,
            pending_battle_ready=False,
            last_battle_result=last_battle_result,
            game_id=1,
            player_id=42,
            opponent_name='Defender',
            land_tier=2,
            land_suit_bonus_suit='Hearts',
            land_suit_bonus_value=2,
        ))
        screen._conquer_left_battle_shop_at = 0
        screen._conquer_timeline_overlay_until = 0
        screen._conquer_collapsed_header_rect = None
        return ConquerGameScreen, screen

    def test_is_tactics_hand_game_true_for_tactics_hand_marker(self):
        ConquerGameScreen, screen = self._make_screen(conquer_move_model='tactics_hand')
        assert ConquerGameScreen._is_tactics_hand_game(screen) is True

    def test_is_tactics_hand_game_false_for_legacy_battle_move_marker(self):
        ConquerGameScreen, screen = self._make_screen(conquer_move_model='battle_move')
        assert ConquerGameScreen._is_tactics_hand_game(screen) is False

    def test_required_tab_never_returns_battle_shop_for_tactics_hand(self):
        ConquerGameScreen, screen = self._make_screen(battle_moves_phase=True)
        tab, _key = ConquerGameScreen._conquer_required_tab(screen)
        assert tab != 'battle_shop'

    def test_required_tab_still_returns_battle_shop_for_legacy_games(self):
        ConquerGameScreen, screen = self._make_screen(
            conquer_move_model='battle_move', battle_moves_phase=True)
        tab, _key = ConquerGameScreen._conquer_required_tab(screen)
        assert tab == 'battle_shop'

    def test_enforce_battle_shop_during_moves_is_noop_for_tactics_hand(self):
        ConquerGameScreen, screen = self._make_screen(battle_moves_phase=True)
        screen.state.subscreen = 'field'
        ConquerGameScreen._enforce_battle_shop_during_moves(screen)
        # Must NOT yank the user onto the (gone) battle_shop subscreen.
        assert screen.state.subscreen == 'field'

    def test_header_uses_full_timeline_before_battle(self):
        ConquerGameScreen, screen = self._make_screen()

        assert ConquerGameScreen._conquer_layout_mode(screen) == 'pre_battle'
        assert ConquerGameScreen._should_use_collapsed_conquer_header(screen) is False

    def test_header_collapses_when_battle_turn_starts(self):
        ConquerGameScreen, screen = self._make_screen(
            battle_turn_player_id=42,
            battle_round=1,
        )

        assert ConquerGameScreen._conquer_layout_mode(screen) == 'battle'
        assert ConquerGameScreen._should_use_collapsed_conquer_header(screen) is True

    def test_header_stays_collapsed_for_result_mode(self):
        ConquerGameScreen, screen = self._make_screen(
            last_battle_result={'winner_name': 'Attacker', 'loser_name': 'Defender'},
        )

        assert ConquerGameScreen._conquer_layout_mode(screen) == 'result'
        assert ConquerGameScreen._should_use_collapsed_conquer_header(screen) is True

    def test_legacy_games_keep_full_timeline_header_during_battle(self):
        ConquerGameScreen, screen = self._make_screen(
            conquer_move_model='battle_move',
            battle_turn_player_id=42,
            battle_round=1,
        )

        assert ConquerGameScreen._conquer_layout_mode(screen) == 'battle'
        assert ConquerGameScreen._should_use_collapsed_conquer_header(screen) is False

    def test_clicking_collapsed_header_expands_timeline_overlay(self):
        ConquerGameScreen, screen = self._make_screen(
            battle_turn_player_id=42,
            battle_round=1,
        )

        handled = ConquerGameScreen._handle_collapsed_header_events(
            screen,
            [pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(8, 8))],
        )

        assert handled is True
        assert screen._conquer_timeline_overlay_until > pygame.time.get_ticks()

    def test_collapsed_header_clears_stale_actions_and_exposes_withdraw(self):
        from config import settings

        ConquerGameScreen, screen = self._make_screen(
            battle_turn_player_id=42,
            battle_round=1,
        )
        screen.window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        screen._conquer_header_font = settings.get_font(settings.FS_HEADING, bold=True)
        screen._conquer_hint_font = settings.get_font(settings.FS_SMALL)
        screen._conquer_badge_font = settings.get_font(settings.FS_TINY, bold=True)
        screen._conquer_objective_action_rects = {'next': pygame.Rect(1, 1, 10, 10)}
        screen._withdraw_dialogue_open = False
        screen._is_current_player_conquer_attacker = lambda: True

        ConquerGameScreen._draw_conquer_collapsed_header(screen)

        assert 'next' not in screen._conquer_objective_action_rects
        assert 'withdraw' in screen._conquer_objective_action_rects

    def test_tactics_hand_gamble_uses_conquer_tactic_endpoint(self, monkeypatch):
        from game.components.conquer_tactics_rail import ACTION_GAMBLE

        ConquerGameScreen, screen = self._make_screen()
        screen._tactics_rail = SimpleNamespace(reset_after_action=lambda: None)
        called = []
        monkeypatch.setattr(
            'utils.game_service.gamble_conquer_tactic',
            lambda game_id, player_id, tactic_id: called.append((game_id, player_id, tactic_id)),
        )
        monkeypatch.setattr(
            'utils.battle_shop_service.gamble_battle_move',
            lambda *_args: called.append(('legacy',)),
        )

        ConquerGameScreen._dispatch_tactics_rail_action(
            screen,
            {'action': ACTION_GAMBLE, 'move': {'id': 7}},
        )

        assert called == [(1, 42, 7)]

    def test_tactics_hand_dismantle_uses_conquer_tactic_endpoint(self, monkeypatch):
        from game.components.conquer_tactics_rail import ACTION_DISMANTLE

        ConquerGameScreen, screen = self._make_screen()
        screen._tactics_rail = SimpleNamespace(reset_after_action=lambda: None)
        called = []
        monkeypatch.setattr(
            'utils.game_service.dismantle_conquer_tactic',
            lambda game_id, player_id, tactic_id: called.append((game_id, player_id, tactic_id)),
        )
        monkeypatch.setattr(
            'utils.battle_shop_service.dismantle_battle_move',
            lambda *_args: called.append(('legacy',)),
        )

        ConquerGameScreen._dispatch_tactics_rail_action(
            screen,
            {'action': ACTION_DISMANTLE, 'move': {'id': 8}},
        )

        assert called == [(1, 42, 8)]

    def test_legacy_gamble_still_uses_battle_shop_endpoint(self, monkeypatch):
        from game.components.conquer_tactics_rail import ACTION_GAMBLE

        ConquerGameScreen, screen = self._make_screen(conquer_move_model='battle_move')
        screen._tactics_rail = SimpleNamespace(reset_after_action=lambda: None)
        called = []
        monkeypatch.setattr(
            'utils.game_service.gamble_conquer_tactic',
            lambda *_args: called.append(('tactics',)),
        )
        monkeypatch.setattr(
            'utils.battle_shop_service.gamble_battle_move',
            lambda game_id, player_id, move_id: called.append((game_id, player_id, move_id)),
        )

        ConquerGameScreen._dispatch_tactics_rail_action(
            screen,
            {'action': ACTION_GAMBLE, 'move': {'id': 9}},
        )

        assert called == [(1, 42, 9)]

    def test_legacy_dismantle_still_uses_battle_shop_endpoint(self, monkeypatch):
        from game.components.conquer_tactics_rail import ACTION_DISMANTLE

        ConquerGameScreen, screen = self._make_screen(conquer_move_model='battle_move')
        screen._tactics_rail = SimpleNamespace(reset_after_action=lambda: None)
        called = []
        monkeypatch.setattr(
            'utils.game_service.dismantle_conquer_tactic',
            lambda *_args: called.append(('tactics',)),
        )
        monkeypatch.setattr(
            'utils.battle_shop_service.dismantle_battle_move',
            lambda game_id, player_id, move_id: called.append((game_id, player_id, move_id)),
        )

        ConquerGameScreen._dispatch_tactics_rail_action(
            screen,
            {'action': ACTION_DISMANTLE, 'move': {'id': 10}},
        )

        assert called == [(1, 42, 10)]


class TestConquerObjectiveTacticsHand:
    """Objective derivation never aims at battle_shop for tactics-hand."""

    def test_moves_objective_targets_field_for_tactics_hand(self):
        from game.screens.conquer_flow import derive_conquer_objective

        game = SimpleNamespace(
            mode='conquer',
            conquer_move_model='tactics_hand',
            battle_moves_phase=True,
            battle_moves_ready=False,
            waiting_for_opponent_battle_moves=False,
            both_battle_moves_ready=False,
            battle_confirmed=False,
            pending_battle_ready=False,
            advancing_figure_id=None,
            defending_figure_id=None,
            pending_defender_selection=False,
            pending_conquer_own_defender_selection=False,
            pending_forced_advance=False,
            pending_conquer_prelude_target=False,
            pending_spell_id=None,
            current_round=1,
            game_over=False,
            game_state='active',
            state='active',
            mode_attribute=None,
            last_battle_result=None,
        )
        objective = derive_conquer_objective(
            game=game,
            field_screen=None,
            battle_shop_screen=None,
        )
        assert objective is not None
        assert objective.target_tab == 'field'
        assert objective.primary_action == 'play_tactic'

    def test_battle_objective_targets_field_for_tactics_hand(self):
        from game.screens.conquer_flow import derive_conquer_objective

        game = SimpleNamespace(
            mode='conquer',
            conquer_move_model='tactics_hand',
            battle_confirmed=True,
            battle_turn_player_id=42,
            battle_round=1,
            player_id=42,
            both_battle_moves_ready=False,
            game_over=False,
            pending_game_over=False,
            pending_conquer_prelude_target=False,
            pending_forced_advance=False,
            pending_defender_selection=False,
            pending_conquer_own_defender_selection=False,
            civil_war_awaiting_second=False,
            civil_war_defender_second=False,
        )
        objective = derive_conquer_objective(
            game=game,
            field_screen=None,
            battle_shop_screen=None,
        )

        assert objective.target_tab == 'field'
        assert objective.primary_action == 'play_tactic'

    def test_moves_objective_targets_battle_shop_for_legacy_games(self):
        from game.screens.conquer_flow import derive_conquer_objective

        game = SimpleNamespace(
            mode='conquer',
            conquer_move_model='battle_move',
            battle_moves_phase=True,
            battle_moves_ready=False,
            waiting_for_opponent_battle_moves=False,
            both_battle_moves_ready=False,
            battle_confirmed=False,
            pending_battle_ready=False,
            advancing_figure_id=None,
            defending_figure_id=None,
            pending_defender_selection=False,
            pending_conquer_own_defender_selection=False,
            pending_forced_advance=False,
            pending_conquer_prelude_target=False,
            pending_spell_id=None,
            current_round=1,
            game_over=False,
            game_state='active',
            state='active',
            mode_attribute=None,
            last_battle_result=None,
        )
        objective = derive_conquer_objective(
            game=game,
            field_screen=None,
            battle_shop_screen=SimpleNamespace(bought_moves=[]),
        )
        assert objective is not None
        assert objective.target_tab == 'battle_shop'
