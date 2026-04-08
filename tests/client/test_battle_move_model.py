# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Unit tests for the client-side BattleMove model."""
import pytest
import unittest.mock as mock


def _make_card(rank, suit, value):
    from game.components.cards.card import Card
    return Card(rank, suit, value, id=1, type='main')


def _make_family(name='Call Villager'):
    from game.components.battle_moves.battle_move import BattleMoveFamily
    stub = object.__new__(BattleMoveFamily)
    stub.name = name
    stub.description = ''
    stub.required_rank = 'J'
    stub.icon_img = mock.MagicMock()
    stub.icon_gray_img = mock.MagicMock()
    stub.frame_img = mock.MagicMock()
    stub.frame_gray_img = mock.MagicMock()
    stub.glow_green_img = mock.MagicMock()
    stub.glow_blue_img = mock.MagicMock()
    stub.moves = []
    return stub


def _make_move(rank='J', suit='Clubs', value=1, family_name='Call Villager'):
    from game.components.battle_moves.battle_move import BattleMove
    card = _make_card(rank, suit, value)
    family = _make_family(family_name)
    return BattleMove(name=f'{family_name} {suit}', family=family, card=card, suit=suit)


class TestBattleMove:
    def test_battle_move_value_equals_card_value(self):
        move = _make_move(rank='J', suit='Clubs', value=1)
        assert move.value == 1

    def test_battle_move_rank_equals_card_rank(self):
        move = _make_move(rank='Q', suit='Hearts', value=2)
        assert move.rank == 'Q'

    def test_battle_move_serialize(self):
        move = _make_move(rank='A', suit='Spades', value=3)
        s = move.serialize()
        assert s['family_name'] == move.family.name
        assert s['suit'] == 'Spades'
        assert s['rank'] == 'A'
        assert s['value'] == 3

    def test_battle_move_from_server_data_sets_id(self):
        move = _make_move()
        move.id = 42
        assert move.id == 42

    def test_battle_move_family_get_moves_for_suit(self):
        from game.components.battle_moves.battle_move import BattleMove
        family = _make_family('Call Villager')
        m_clubs = BattleMove('CV Clubs', family, _make_card('J', 'Clubs', 1), 'Clubs')
        m_hearts = BattleMove('CV Hearts', family, _make_card('J', 'Hearts', 1), 'Hearts')
        family.moves = [m_clubs, m_hearts]
        result = family.get_moves_for_suit('Clubs')
        assert len(result) == 1
        assert result[0].suit == 'Clubs'
