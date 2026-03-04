"""Battle move model classes for the battle shop."""

import pygame
from config import settings


class BattleMoveFamily:
    """A family/type of battle move (e.g. 'Call Villager', 'Block', 'Dagger').

    Each family defines the icon, frame, and glow images, plus what kind of card
    is required. The family produces individual BattleMove instances for each
    matching card in the player's hand.
    """

    def __init__(self, name, description, required_rank, icon_img, icon_gray_img,
                 frame_img, frame_gray_img, glow_green_img, glow_blue_img):
        self.name = name
        self.description = description
        self.required_rank = required_rank  # e.g. 'J', 'Q', 'K', 'A', or 'number'
        self.icon_img = icon_img
        self.icon_gray_img = icon_gray_img
        self.frame_img = frame_img
        self.frame_gray_img = frame_gray_img
        self.glow_green_img = glow_green_img  # For red/offensive suits (Djungle)
        self.glow_blue_img = glow_blue_img    # For black/defensive suits (Himalaya)
        self.moves = []  # List of BattleMove instances

    def make_icon(self, window, game, x, y):
        """Create a BattleMoveIcon for this family."""
        from game.components.battle_moves.battle_move_icon import BattleMoveIcon
        return BattleMoveIcon(window, game, self, x, y)

    def get_moves_for_suit(self, suit):
        """Get all moves matching a specific suit."""
        return [m for m in self.moves if m.suit == suit]


class BattleMove:
    """A single battle move instance — one card from hand.

    Represents a purchasable battle action. Each move corresponds to exactly
    one card from the player's hand.
    """

    def __init__(self, name, family, card, suit):
        """
        :param name: Display name (e.g. 'Call Villager ♥')
        :param family: The BattleMoveFamily this belongs to
        :param card: The Card object from the player's hand
        :param suit: The suit of the card (e.g. 'Hearts')
        """
        self.name = name
        self.family = family
        self.card = card
        self.suit = suit
        self.id = None  # Set after purchase (server-assigned)

    @property
    def value(self):
        """The battle value of this move (= the card's value)."""
        return self.card.value if self.card else 0

    @property
    def rank(self):
        """The rank of the card."""
        return self.card.rank if self.card else ''

    def serialize(self):
        """Serialize for sending to the server."""
        return {
            'family_name': self.family.name,
            'card_id': self.card.id if self.card else None,
            'card_type': self.card.type if self.card else 'main_card',
            'suit': self.suit,
            'rank': self.rank,
            'value': self.value,
        }

    @staticmethod
    def from_server_data(data, families_by_name):
        """Reconstruct a BattleMove from server data (for display of bought moves)."""
        family = families_by_name.get(data.get('family_name'))
        if not family:
            return None

        # Create a minimal Card-like object for display
        from game.components.cards.card import Card
        card = Card(
            rank=data.get('rank', ''),
            suit=data.get('suit', ''),
            value=data.get('value', 0),
            id=data.get('card_id'),
            type=data.get('card_type', 'main_card')
        )

        move = BattleMove(
            name=f"{family.name}",
            family=family,
            card=card,
            suit=data.get('suit', '')
        )
        move.id = data.get('id')
        return move
