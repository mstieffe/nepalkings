# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Unit tests for CardSource abstraction (Phase 10)."""
import pytest
from unittest.mock import MagicMock


def _card(rank, suit='Hearts', value=1, id=None, player_id=None):
    from game.components.cards.card import Card
    return Card(rank, suit, value, id=id, player_id=player_id)


# ---------------------------------------------------------------------------
# CardSource base class
# ---------------------------------------------------------------------------

class TestCardSourceBase:
    def test_get_cards_raises(self):
        from game.core.card_source import CardSource
        with pytest.raises(NotImplementedError):
            CardSource().get_cards()

    def test_get_figures_raises(self):
        from game.core.card_source import CardSource
        with pytest.raises(NotImplementedError):
            CardSource().get_figures([])


# ---------------------------------------------------------------------------
# GameCardSource
# ---------------------------------------------------------------------------

class TestGameCardSource:
    def test_get_cards_delegates_to_game(self):
        from game.core.card_source import GameCardSource
        game = MagicMock()
        main = [_card('K')]
        side = [_card('3')]
        game.get_hand.return_value = (main, side)

        src = GameCardSource(game)
        result = src.get_cards()

        game.get_hand.assert_called_once()
        assert result == (main, side)

    def test_get_figures_delegates_to_game(self):
        from game.core.card_source import GameCardSource
        game = MagicMock()
        figs = [MagicMock()]
        game.get_figures.return_value = figs

        src = GameCardSource(game)
        result = src.get_figures(['warrior'], is_opponent=True)

        game.get_figures.assert_called_once_with(['warrior'], True)
        assert result == figs

    def test_get_figures_default_is_opponent_false(self):
        from game.core.card_source import GameCardSource
        game = MagicMock()
        game.get_figures.return_value = []

        src = GameCardSource(game)
        src.get_figures(['mage'])

        game.get_figures.assert_called_once_with(['mage'], False)


# ---------------------------------------------------------------------------
# CollectionCardSource
# ---------------------------------------------------------------------------

class TestCollectionCardSource:
    def test_get_cards_splits_main_and_side(self):
        from game.core.card_source import CollectionCardSource
        cards = [
            _card('K', id=1),
            _card('A', id=2),
            _card('3', id=3),
            _card('5', id=4),
        ]
        src = CollectionCardSource(cards, config_figures=[], locked_card_ids=set())
        main, side = src.get_cards()

        assert len(main) == 2
        assert all(c.rank in ('K', 'A') for c in main)
        assert len(side) == 2
        assert all(c.rank in ('3', '5') for c in side)

    def test_get_cards_excludes_locked(self):
        from game.core.card_source import CollectionCardSource
        cards = [
            _card('K', id=1),
            _card('Q', id=2),
            _card('3', id=3),
        ]
        src = CollectionCardSource(cards, config_figures=[], locked_card_ids={1, 3})
        main, side = src.get_cards()

        assert len(main) == 1
        assert main[0].id == 2
        assert len(side) == 0

    def test_get_cards_empty_collection(self):
        from game.core.card_source import CollectionCardSource
        src = CollectionCardSource([], config_figures=[], locked_card_ids=set())
        main, side = src.get_cards()
        assert main == []
        assert side == []

    def test_get_cards_all_locked(self):
        from game.core.card_source import CollectionCardSource
        cards = [_card('K', id=1), _card('3', id=2)]
        src = CollectionCardSource(cards, config_figures=[], locked_card_ids={1, 2})
        main, side = src.get_cards()
        assert main == []
        assert side == []

    def test_get_figures_returns_config_figures(self):
        from game.core.card_source import CollectionCardSource
        figs = [MagicMock(), MagicMock()]
        src = CollectionCardSource([], config_figures=figs, locked_card_ids=set())
        assert src.get_figures(['warrior']) == figs

    def test_get_figures_ignores_families_and_is_opponent(self):
        """CollectionCardSource always returns all config_figures regardless of args."""
        from game.core.card_source import CollectionCardSource
        figs = [MagicMock()]
        src = CollectionCardSource([], config_figures=figs, locked_card_ids=set())
        assert src.get_figures([], is_opponent=True) == figs

    def test_locked_card_ids_accepts_list(self):
        """locked_card_ids should work even if passed as a list instead of set."""
        from game.core.card_source import CollectionCardSource
        cards = [_card('K', id=1), _card('Q', id=2)]
        src = CollectionCardSource(cards, config_figures=[], locked_card_ids=[1])
        main, side = src.get_cards()
        assert len(main) == 1
        assert main[0].id == 2

    def test_all_main_ranks_classified_correctly(self):
        from config import settings
        from game.core.card_source import CollectionCardSource
        cards = [_card(r, id=i) for i, r in enumerate(settings.RANKS_MAIN_CARDS)]
        src = CollectionCardSource(cards, config_figures=[], locked_card_ids=set())
        main, side = src.get_cards()
        assert len(main) == len(settings.RANKS_MAIN_CARDS)
        assert len(side) == 0

    def test_all_side_ranks_classified_correctly(self):
        from config import settings
        from game.core.card_source import CollectionCardSource
        cards = [_card(r, id=i) for i, r in enumerate(settings.RANKS_SIDE_CARDS)]
        src = CollectionCardSource(cards, config_figures=[], locked_card_ids=set())
        main, side = src.get_cards()
        assert len(main) == 0
        assert len(side) == len(settings.RANKS_SIDE_CARDS)
