# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""CardSource abstraction — lets BuildFigureScreen / BattleShopScreen work
with either a duel Game or a kingdom CollectionCard pool."""

from config import settings


class CardSource:
    """Abstract interface for providing cards to build/shop screens."""

    def get_cards(self):
        """Return (main_cards, side_cards) available for use."""
        raise NotImplementedError

    def get_figures(self, families, is_opponent=False):
        """Return figures already built in this context."""
        raise NotImplementedError


class GameCardSource(CardSource):
    """Wraps an existing duel Game — delegates to Game.get_hand / get_figures."""

    def __init__(self, game):
        self.game = game

    def get_cards(self):
        return self.game.get_hand()

    def get_figures(self, families, is_opponent=False):
        return self.game.get_figures(families, is_opponent)


class CollectionCardSource(CardSource):
    """For conquer/defence configs — uses the player's card collection.

    Parameters
    ----------
    collection_cards : list[Card]
        Full collection as Card objects.
    config_figures : list
        Already-built LandConfigFigure-like objects for the config.
    locked_card_ids : set[int]
        Card IDs already in use (locked) in this config.
    """

    def __init__(self, collection_cards, config_figures, locked_card_ids):
        self._cards = collection_cards
        self._figures = config_figures
        self._locked = set(locked_card_ids)

    def get_cards(self):
        free = [c for c in self._cards if c.id not in self._locked]
        main = [c for c in free if c.rank in settings.RANKS_MAIN_CARDS]
        side = [c for c in free if c.rank in settings.RANKS_SIDE_CARDS]
        return main, side

    def get_figures(self, families, is_opponent=False):
        return self._figures
