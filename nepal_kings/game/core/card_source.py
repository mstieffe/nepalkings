# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""CardSource abstraction — lets BuildFigureScreen / BattleShopScreen work
with either a duel Game or a kingdom CollectionCard pool."""

from config import settings
from game.components.cards.card import Card
from game.components.figures.figure import Figure

import logging

logger = logging.getLogger('nk.core.card_source')


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
        if self.game is None:
            return [], []
        return self.game.get_hand()

    def get_figures(self, families, is_opponent=False):
        if self.game is None:
            return []
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
        figures = []
        for cfg_fig in self._figures:
            fig = self._config_fig_to_figure(cfg_fig, families)
            if fig is not None:
                figures.append(fig)
        return figures

    @staticmethod
    def _config_fig_to_figure(cfg_fig, families):
        """Convert a config figure dict to a real Figure object."""
        family_name = cfg_fig.get('family_name', '')
        family = families.get(family_name)
        if not family:
            return None

        suit = cfg_fig.get('suit', '')
        name = cfg_fig.get('name', family_name)

        matched = None
        for fam_fig in family.figures:
            if fam_fig.suit == suit and fam_fig.name == name:
                matched = fam_fig
                break
        if matched is None:
            for fam_fig in family.figures:
                if fam_fig.suit == suit:
                    matched = fam_fig
                    break

        card_specs = cfg_fig.get('card_specs') or []
        card_roles = cfg_fig.get('card_roles') or []
        key_cards = []
        number_card = None
        upgrade_card = None
        if card_specs:
            for spec, role in zip(card_specs, card_roles):
                if not spec:
                    continue
                card = Card(rank=spec['rank'], suit=spec['suit'], value=spec['value'])
                if role == 'key':
                    key_cards.append(card)
                elif role == 'number':
                    number_card = card
                elif role == 'upgrade':
                    upgrade_card = card
        if not key_cards and not number_card and not upgrade_card:
            key_cards = matched.key_cards if matched else []
            number_card = matched.number_card if matched else None
            upgrade_card = matched.upgrade_card if matched else None

        return Figure(
            name=name,
            sub_name=matched.sub_name if matched else '',
            suit=suit,
            family=family,
            key_cards=key_cards,
            number_card=number_card,
            upgrade_card=upgrade_card,
            upgrade_family_name=cfg_fig.get('upgrade_family_name'),
            produces=cfg_fig.get('produces', {}),
            requires=cfg_fig.get('requires', {}),
            description=cfg_fig.get('description', ''),
            id=cfg_fig.get('id'),
            cannot_attack=getattr(matched, 'cannot_attack', False) if matched else False,
            must_be_attacked=getattr(matched, 'must_be_attacked', False) if matched else False,
            rest_after_attack=cfg_fig.get('rest_after_attack', False),
            distance_attack=getattr(matched, 'distance_attack', False) if matched else False,
            buffs_allies=getattr(matched, 'buffs_allies', False) if matched else False,
            buffs_allies_defence=getattr(matched, 'buffs_allies_defence', False) if matched else False,
            blocks_bonus=getattr(matched, 'blocks_bonus', False) if matched else False,
            cannot_defend=getattr(matched, 'cannot_defend', False) if matched else False,
            instant_charge=getattr(matched, 'instant_charge', False) if matched else False,
            cannot_be_blocked=cfg_fig.get('cannot_be_blocked', False),
            cannot_be_targeted=getattr(matched, 'cannot_be_targeted', False) if matched else False,
            checkmate=cfg_fig.get('checkmate', False),
            override_base_power=getattr(matched, 'override_base_power', None) if matched else None,
        )
