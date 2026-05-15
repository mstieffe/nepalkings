# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Unit tests for the client-side Card model."""
import pytest


class TestCard:
    def test_card_to_tuple_returns_rank_suit_value(self):
        from game.components.cards.card import Card
        c = Card('K', 'Hearts', 4)
        assert c.to_tuple() == ('K', 'Hearts', 4)

    def test_card_value_is_integer(self):
        from game.components.cards.card import Card
        c = Card('7', 'Clubs', 7)
        assert isinstance(c.value, int)

    def test_card_value_stored_as_int_when_given_string(self):
        from game.components.cards.card import Card
        c = Card('A', 'Spades', '3')
        assert c.value == 3

    def test_card_type_main(self):
        from game.components.cards.card import Card
        c = Card('J', 'Diamonds', 1, type='main')
        assert c.type == 'main'

    def test_card_type_side(self):
        from game.components.cards.card import Card
        c = Card('3', 'Hearts', 3, type='side')
        assert c.type == 'side'

    def test_card_is_main_card_for_main_rank(self):
        """Cards with ranks 7-A are 'main' cards."""
        from game.components.cards.card import Card
        c = Card('K', 'Clubs', 4)
        assert c.is_main_card is True

    def test_card_not_main_for_side_rank(self):
        """Cards with ranks 2-6 are 'side' cards."""
        from game.components.cards.card import Card
        c = Card('3', 'Hearts', 3)
        assert c.is_main_card is False

    def test_card_serialize_contains_expected_keys(self):
        from game.components.cards.card import Card
        c = Card('Q', 'Diamonds', 2, id=5, game_id=1, player_id=2)
        s = c.serialize()
        for key in ('id', 'suit', 'rank', 'value', 'player_id', 'game_id'):
            assert key in s

    def test_card_equality_based_on_value(self):
        from game.components.cards.card import Card
        c1 = Card('K', 'Hearts', 4)
        c2 = Card('K', 'Spades', 4)
        assert c1 == c2

    def test_card_less_than_comparison(self):
        from game.components.cards.card import Card
        low = Card('7', 'Clubs', 7)
        high = Card('A', 'Hearts', 10)
        assert low < high

    def test_card_hash_based_on_rank_suit_value(self):
        from game.components.cards.card import Card
        c1 = Card('K', 'Hearts', 4)
        c2 = Card('K', 'Hearts', 4)
        assert hash(c1) == hash(c2)

    def test_card_in_set(self):
        from game.components.cards.card import Card
        c1 = Card('K', 'Hearts', 4)
        c2 = Card('K', 'Hearts', 4)
        s = {c1}
        assert c2 in s
