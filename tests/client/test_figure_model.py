# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Unit tests for the client-side Figure model (pure logic, no server needed)."""
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_card(rank, suit, value):
    from game.components.cards.card import Card
    return Card(rank, suit, value)


def _make_stub_family(name='TestFamily', color='defensive', field='village'):
    """Minimal FigureFamily stub without pygame surfaces."""
    from game.components.figures.figure import FigureFamily
    import unittest.mock as mock
    stub = object.__new__(FigureFamily)
    stub.name = name
    stub.color = color
    stub.field = field
    stub.suits = ['Clubs', 'Spades']
    stub.figures = []
    stub.icon_img = mock.MagicMock()
    stub.icon_gray_img = mock.MagicMock()
    stub.icon_img_small = mock.MagicMock()
    stub.icon_gray_img_small = mock.MagicMock()
    stub.frame_img = mock.MagicMock()
    stub.frame_closed_img = mock.MagicMock()
    stub.frame_hidden_img = mock.MagicMock()
    stub.frame_hidden_greyscale_img = mock.MagicMock()
    stub.glow_img = mock.MagicMock()
    stub.build_position = None
    stub.description = ''
    return stub


def _make_village_figure(key_cards, number_card=None, upgrade_card=None,
                          upgrade_family_name=None, produces=None, requires=None):
    from game.components.figures.figure import VillageFigure
    family = _make_stub_family('Small Yack Farm', 'defensive', 'village')
    return VillageFigure(
        name='Small Yack Farm',
        sub_name='Clubs 7',
        suit='Clubs',
        family=family,
        key_cards=key_cards,
        number_card=number_card,
        upgrade_card=upgrade_card,
        upgrade_family_name=upgrade_family_name,
        produces=produces or {},
        requires=requires or {},
    )


def _make_castle_figure(name='Himalaya King', override_base_power=15,
                         produces=None, checkmate=False):
    from game.components.figures.figure import CastleFigure
    family = _make_stub_family(name, 'defensive', 'castle')
    return CastleFigure(
        name=name,
        sub_name='Clubs',
        suit='Clubs',
        family=family,
        key_cards=[_make_card('K', 'Clubs', 4)],
        override_base_power=override_base_power,
        produces=produces or {},
        checkmate=checkmate,
    )


def _make_military_figure():
    from game.components.figures.figure import MilitaryFigure
    family = _make_stub_family('Test Military', 'defensive', 'military')
    return MilitaryFigure(
        name='Test Military',
        sub_name='Clubs',
        suit='Clubs',
        family=family,
        key_cards=[_make_card('A', 'Clubs', 3)],
        number_card=_make_card('7', 'Clubs', 7),
        requires={'warrior_black': 1},
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFigureValue:
    def test_figure_value_is_sum_of_card_values(self):
        key = _make_card('J', 'Clubs', 1)
        number = _make_card('7', 'Clubs', 7)
        fig = _make_village_figure([key], number_card=number)
        assert fig.value == 1 + 7

    def test_figure_value_uses_override_base_power_when_set(self):
        fig = _make_castle_figure(override_base_power=15)
        assert fig.value == 15

    def test_castle_maharaja_override_base_power_16(self):
        fig = _make_castle_figure(name='Himalaya Maharaja', override_base_power=16)
        assert fig.value == 16


class TestFigureBattleBonus:
    def test_figure_battle_bonus_military_is_zero(self):
        fig = _make_military_figure()
        assert fig.get_battle_bonus() == 0

    def test_figure_battle_bonus_maharaja_is_5(self):
        fig = _make_castle_figure(name='Himalaya Maharaja', override_base_power=16)
        assert fig.get_battle_bonus() == 5

    def test_figure_battle_bonus_king_is_4(self):
        fig = _make_castle_figure(name='Himalaya King', override_base_power=15)
        assert fig.get_battle_bonus() == 4

    def test_figure_battle_bonus_village_is_sum_of_key_cards(self):
        key1 = _make_card('J', 'Clubs', 1)
        key2 = _make_card('J', 'Spades', 1)
        fig = _make_village_figure([key1, key2])
        assert fig.get_battle_bonus() == 1 + 1


class TestFigureIsMatch:
    def test_figure_is_match_with_exact_cards(self):
        key = _make_card('J', 'Clubs', 1)
        number = _make_card('7', 'Clubs', 7)
        fig = _make_village_figure([key], number_card=number)
        assert fig.is_match([key, number]) is True

    def test_figure_is_match_with_superset_of_cards(self):
        key = _make_card('J', 'Clubs', 1)
        number = _make_card('7', 'Clubs', 7)
        extra = _make_card('Q', 'Clubs', 2)
        fig = _make_village_figure([key], number_card=number)
        assert fig.is_match([key, number, extra]) is True

    def test_figure_is_match_fails_with_missing_card(self):
        key = _make_card('J', 'Clubs', 1)
        number = _make_card('7', 'Clubs', 7)
        fig = _make_village_figure([key], number_card=number)
        assert fig.is_match([key]) is False


class TestFigureUpgrade:
    def test_figure_has_upgrade_returns_true_when_upgrade_family_set(self):
        key = _make_card('J', 'Clubs', 1)
        fig = _make_village_figure([key], upgrade_family_name='Large Yack Farm')
        assert fig.has_upgrade() is True

    def test_figure_has_upgrade_returns_false_when_not_set(self):
        key = _make_card('J', 'Clubs', 1)
        fig = _make_village_figure([key])
        assert fig.has_upgrade() is False


class TestFigureEnchantments:
    def test_figure_enchantment_add_and_get_modifier(self):
        fig = _make_village_figure([_make_card('J', 'Clubs', 1)])
        fig.add_enchantment('Poison', 'poison.png', -6)
        assert fig.get_total_enchantment_modifier() == -6

    def test_figure_enchantment_multiple_stacks(self):
        fig = _make_village_figure([_make_card('J', 'Clubs', 1)])
        fig.add_enchantment('Poison', 'poison.png', -6)
        fig.add_enchantment('Health Boost', 'boost.png', +6)
        assert fig.get_total_enchantment_modifier() == 0

    def test_figure_clear_enchantments(self):
        fig = _make_village_figure([_make_card('J', 'Clubs', 1)])
        fig.add_enchantment('Poison', 'poison.png', -6)
        fig.clear_enchantments()
        assert fig.get_total_enchantment_modifier() == 0
        assert fig.active_enchantments == []


class TestFigureResources:
    def test_figure_produces_dict_defaults_to_empty(self):
        from game.components.figures.figure import Figure
        family = _make_stub_family()
        fig = Figure(
            name='Test', sub_name='', suit='Clubs',
            family=family, key_cards=[],
        )
        assert fig.produces == {}

    def test_figure_requires_dict_defaults_to_empty(self):
        from game.components.figures.figure import Figure
        family = _make_stub_family()
        fig = Figure(
            name='Test', sub_name='', suit='Clubs',
            family=family, key_cards=[],
        )
        assert fig.requires == {}

    def test_figure_resources_alias_equals_produces(self):
        """The 'resources' attribute is an alias for 'produces' (backward compat)."""
        produces = {'villager_black': 2}
        from game.components.figures.figure import Figure
        family = _make_stub_family()
        fig = Figure(
            name='Test', sub_name='', suit='Clubs',
            family=family, key_cards=[],
            produces=produces,
        )
        assert fig.resources is fig.produces


class TestFigureSkills:
    def test_figure_active_skills_returns_correct_keys(self):
        from game.components.figures.figure import Figure
        family = _make_stub_family()
        fig = Figure(
            name='Test', sub_name='', suit='Clubs',
            family=family, key_cards=[],
            cannot_attack=True,
            rest_after_attack=True,
        )
        keys = fig.get_active_skill_keys()
        assert 'cannot_attack' in keys
        assert 'rest_after_attack' in keys
        assert 'distance_attack' not in keys


class TestFigureFamily:
    def test_figure_family_get_figures_by_suit(self):
        from game.components.figures.figure import FigureFamily, Figure
        import unittest.mock as mock

        family = _make_stub_family('Test', 'defensive', 'village')
        fig_clubs = Figure(
            name='F1', sub_name='', suit='Clubs',
            family=family, key_cards=[],
        )
        fig_hearts = Figure(
            name='F2', sub_name='', suit='Hearts',
            family=family, key_cards=[],
        )
        family.figures = [fig_clubs, fig_hearts]

        clubs_figs = family.get_figures_by_suit('Clubs')
        assert len(clubs_figs) == 1
        assert clubs_figs[0].suit == 'Clubs'
