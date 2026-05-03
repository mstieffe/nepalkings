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
        assert names == [
            'conquer_view_field',
            'conquer_view_battle_shop',
            'conquer_view_battle',
        ]
        assert all('build' not in name for name in names)
        assert all('spell' not in name for name in names)
        assert all('log' not in name for name in names)
        assert screen.battle_button.locked is False
        assert screen.field_button.x == screen.battle_shop_button.x == screen.battle_button.x
        assert screen.field_button.y < screen.battle_shop_button.y < screen.battle_button.y
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
        game = SimpleNamespace(
            mode='conquer',
            battle_moves_phase=True,
            battle_moves_ready=False,
            waiting_for_opponent_battle_moves=False,
        )
        ConquerGameScreen, screen = _base_conquer_screen(game)
        screen.state.subscreen = 'field'

        ConquerGameScreen._auto_route_conquer_once(screen)

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

    def test_attention_counts_mark_required_tabs(self):
        game = SimpleNamespace(
            mode='conquer',
            pending_forced_advance=True,
            advancing_figure_id=None,
            battle_moves_phase=True,
            battle_moves_ready=False,
            waiting_for_opponent_battle_moves=False,
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

        assert counts == {'field': 1, 'battle_shop': 1, 'battle': 1}


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
