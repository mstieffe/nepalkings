# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Regression tests for shared client-side figure buff helpers."""

from types import SimpleNamespace


class _Figure(SimpleNamespace):
    def get_value(self):
        return self.value


def _fig(fig_id, suit='Hearts', field='village', value=0, buffs_allies=False,
         requires=None):
    return _Figure(
        id=fig_id,
        suit=suit,
        value=value,
        buffs_allies=buffs_allies,
        requires=requires or {},
        family=SimpleNamespace(field=field),
    )


def test_apply_buffs_allies_sets_and_resets_icon_bonuses():
    from game.core.figure_buffs import apply_buffs_allies_to_icon_map

    healer = _fig(1, buffs_allies=True)
    farm = _fig(2, value=13)
    other_suit_farm = _fig(3, suit='Diamonds', value=13)
    military = _fig(4, field='military', value=8)
    icons = {
        1: SimpleNamespace(buffs_allies_bonus=99, has_deficit=False),
        2: SimpleNamespace(buffs_allies_bonus=99, has_deficit=False),
        3: SimpleNamespace(buffs_allies_bonus=99, has_deficit=False),
        4: SimpleNamespace(buffs_allies_bonus=99, has_deficit=False),
    }

    sources = apply_buffs_allies_to_icon_map(
        [healer, farm, other_suit_farm, military],
        icons,
        has_deficit=lambda fig: False,
    )

    assert sources == [healer]
    assert icons[1].buffs_allies_bonus == 4
    assert icons[2].buffs_allies_bonus == 4
    assert icons[3].buffs_allies_bonus == 0
    assert icons[4].buffs_allies_bonus == 0


def test_apply_buffs_allies_ignores_deficit_and_excluded_sources():
    from game.core.figure_buffs import apply_buffs_allies_to_icon_map

    healer = _fig(1, buffs_allies=True)
    farm = _fig(2, value=13)
    icons = {
        1: SimpleNamespace(buffs_allies_bonus=0, has_deficit=False),
        2: SimpleNamespace(buffs_allies_bonus=0, has_deficit=False),
    }

    apply_buffs_allies_to_icon_map(
        [healer, farm],
        icons,
        has_deficit=lambda fig: fig.id == 1,
    )
    assert icons[2].buffs_allies_bonus == 0

    apply_buffs_allies_to_icon_map(
        [healer, farm],
        icons,
        has_deficit=lambda fig: False,
        exclude_ids={1},
    )
    assert icons[2].buffs_allies_bonus == 0


def test_battle_shop_call_power_includes_healer_buff():
    from game.screens.battle_shop_screen import BattleShopScreen

    healer = _fig(1, value=4, buffs_allies=True)
    farm = _fig(2, value=13)
    screen = BattleShopScreen.__new__(BattleShopScreen)
    screen._player_figures = [healer, farm]
    screen._figures_loaded_game_key = (None, None, 0)
    screen._resources_data = {'produces': {}, 'requires': {}}
    screen.game = SimpleNamespace(
        game_id=None,
        player_id=None,
        _figures_data_version=0,
        advancing_figure_id=None,
        advancing_figure_id_2=None,
        defending_figure_id=None,
        defending_figure_id_2=None,
    )

    power = BattleShopScreen._get_display_power(
        screen,
        {'family_name': 'Call Villager', 'suit': 'Hearts', 'value': 1},
    )

    assert power == 18


def test_battle_shop_call_power_excludes_fighting_healer():
    from game.screens.battle_shop_screen import BattleShopScreen

    healer = _fig(1, value=4, buffs_allies=True)
    farm = _fig(2, value=13)
    screen = BattleShopScreen.__new__(BattleShopScreen)
    screen._player_figures = [healer, farm]
    screen._figures_loaded_game_key = (None, None, 0)
    screen._resources_data = {'produces': {}, 'requires': {}}
    screen.game = SimpleNamespace(
        game_id=None,
        player_id=None,
        _figures_data_version=0,
        advancing_figure_id=1,
        advancing_figure_id_2=None,
        defending_figure_id=None,
        defending_figure_id_2=None,
    )

    power = BattleShopScreen._get_display_power(
        screen,
        {'family_name': 'Call Villager', 'suit': 'Hearts', 'value': 1},
    )

    assert power == 14


def test_battle_screen_battle_figure_power_uses_shared_healer_buff():
    from game.screens.battle_screen import BattleScreen

    healer = _fig(1, value=4, buffs_allies=True)
    farm = _fig(2, value=13)
    farm_icon = SimpleNamespace(buffs_allies_bonus=0)

    screen = BattleScreen.__new__(BattleScreen)
    screen.player_figure = farm
    screen.player_figure_2 = None
    screen.opponent_figure = None
    screen.opponent_figure_2 = None
    screen.player_figure_icon = farm_icon
    screen.player_figure_icon_2 = None
    screen.opponent_figure_icon = None
    screen.opponent_figure_icon_2 = None
    screen._resources_data = {'produces': {}, 'requires': {}}
    screen._opponent_resources_data = {'produces': {}, 'requires': {}}

    BattleScreen._detect_buffs_allies(
        screen,
        player_figures=[healer, farm],
        opponent_figures=[],
    )

    assert screen.player_buffs_allies_figures == [healer]
    assert farm_icon.buffs_allies_bonus == 4


def test_call_move_detail_power_parts_include_healer_bonus():
    from game.components.battle_moves.battle_move_detail_box import BattleMoveDetailBox

    farm = _fig(2, value=13)
    box = BattleMoveDetailBox.__new__(BattleMoveDetailBox)
    box.bm = {'suit': 'Hearts'}
    box.display_power = 1
    box.figure_power_bonuses = {2: 4}

    assert BattleMoveDetailBox._get_call_power_parts(box, farm) == (17, 1)
