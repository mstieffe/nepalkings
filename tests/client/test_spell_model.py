# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Unit tests for the client-side Spell model."""
import pytest
import unittest.mock as mock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_card(rank, suit, value):
    from game.components.cards.card import Card
    return Card(rank, suit, value)


def _make_spell_family(name='Poison', spell_type='enchantment'):
    from game.components.spells.spell import SpellFamily
    stub = object.__new__(SpellFamily)
    stub.name = name
    stub.type = spell_type
    stub.description = ''
    stub.icon_img = mock.MagicMock()
    stub.icon_gray_img = mock.MagicMock()
    stub.frame_img = mock.MagicMock()
    stub.frame_closed_img = mock.MagicMock()
    stub.frame_hidden_img = mock.MagicMock()
    stub.glow_img = mock.MagicMock()
    stub.spells = []
    return stub


def _make_spell(name='Poison', suit='Clubs', spell_type='enchantment',
                key_cards=None, number_card=None, upgrade_card=None,
                counterable=False, requires_target=False):
    from game.components.spells.spell import Spell
    family = _make_spell_family(name, spell_type)
    kc = key_cards or [_make_card('J', suit, 1)]
    cards = kc[:]
    if number_card:
        cards.append(number_card)
    spell = Spell(
        name=name,
        family=family,
        cards=cards,
        suit=suit,
        key_cards=kc,
        number_card=number_card,
        upgrade_card=upgrade_card,
        requires_target=requires_target,
        counterable=counterable,
    )
    # Set runtime attributes that are normally set later
    spell.id = None
    spell.player_id = None
    spell.game_id = None
    spell.target_figure_id = None
    spell.is_active = False
    spell.cast_round = None
    spell.duration = 0
    return spell


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSpellBasics:
    def test_spell_is_upgraded_false_without_upgrade_card(self):
        spell = _make_spell()
        assert spell.is_upgraded() is False

    def test_spell_is_upgraded_true_with_upgrade_card(self):
        upgrade = _make_card('Q', 'Clubs', 2)
        spell = _make_spell(upgrade_card=upgrade)
        assert spell.is_upgraded() is True

    def test_spell_get_power_from_number_card(self):
        number = _make_card('7', 'Clubs', 7)
        spell = _make_spell(number_card=number)
        assert spell.get_power() == 7

    def test_spell_get_power_zero_without_number_card(self):
        spell = _make_spell()
        assert spell.get_power() == 0


class TestSpellSerialization:
    def test_spell_serialization_roundtrip(self):
        key = _make_card('J', 'Clubs', 1)
        number = _make_card('7', 'Clubs', 7)
        spell = _make_spell(key_cards=[key], number_card=number)
        data = spell.serialize()
        assert data['name'] == spell.name
        assert data['suit'] == spell.suit
        assert data['family_name'] == spell.family.name

    def test_spell_from_dict_creates_correct_spell(self):
        from game.components.spells.spell import Spell
        family = _make_spell_family('Poison', 'enchantment')
        data = {
            'name': 'Poison',
            'suit': 'Hearts',
            'cards': [{'rank': 'J', 'suit': 'Hearts', 'value': 1}],
            'key_cards': [{'rank': 'J', 'suit': 'Hearts', 'value': 1}],
            'number_card': None,
            'upgrade_card': None,
            'requires_target': True,
            'target_type': 'opponent_figure',
            'id': 42,
            'player_id': 1,
            'game_id': 1,
            'target_figure_id': None,
            'is_active': True,
            'cast_round': 2,
            'duration': 1,
        }
        spell = Spell.from_dict(data, family)
        assert spell.name == 'Poison'
        assert spell.suit == 'Hearts'
        assert spell.requires_target is True
        assert spell.is_active is True

    def test_spell_serialization_includes_number_card(self):
        number = _make_card('9', 'Clubs', 9)
        spell = _make_spell(number_card=number)
        data = spell.serialize()
        assert data['number_card'] is not None
        assert data['number_card']['rank'] == '9'


class TestSpellFamily:
    def test_spell_family_get_spells_by_suit(self):
        from game.components.spells.spell import SpellFamily, Spell
        family = _make_spell_family('Poison', 'enchantment')
        s1 = _make_spell(suit='Clubs')
        s2 = _make_spell(suit='Hearts')
        family.spells = [s1, s2]
        result = family.get_spells_by_suit('Clubs')
        assert len(result) == 1
        assert result[0].suit == 'Clubs'


class TestSpellProperties:
    def test_counterable_flag_set_correctly(self):
        spell = _make_spell(counterable=True)
        assert spell.counterable is True

    def test_non_counterable_flag(self):
        spell = _make_spell(counterable=False)
        assert spell.counterable is False

    def test_requires_target_set(self):
        spell = _make_spell(requires_target=True)
        assert spell.requires_target is True
