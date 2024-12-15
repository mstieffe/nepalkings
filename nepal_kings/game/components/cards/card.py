from game.components.cards.card_img import CardImg
from config import settings

class Card:
    def __init__(self, rank, suit, value, card_id=None, game_id=None, player_id=None, in_deck=None, deck_position=None, part_of_figure=None):
        """
        Initialize a Card instance.

        :param rank: The rank of the card (e.g., 'J', 'Q', 'K').
        :param suit: The suit of the card (e.g., 'Hearts', 'Diamonds').
        :param value: The numerical value of the card.
        :param card_id: (Optional) Unique identifier of the card in the database.
        :param game_id: (Optional) The game ID associated with the card.
        :param player_id: (Optional) The player ID holding the card.
        :param in_deck: (Optional) Boolean indicating if the card is in the deck.
        :param deck_position: (Optional) The position of the card in the deck.
        :param part_of_figure: (Optional) Boolean indicating if the card is part of a figure.
        """
        self.rank = rank
        self.suit = suit
        self.value = int(value)

        # Optional parameters for integration with the server
        self.card_id = card_id
        self.game_id = game_id
        self.player_id = player_id
        self.in_deck = in_deck
        self.deck_position = deck_position
        self.part_of_figure = part_of_figure

        # Derived properties
        self.is_ZK = True if self.rank in settings.RANKS_ZK else False
        self.is_main_card = True if self.rank in settings.RANKS_MAIN_CARDS else False

    def make_icon(self, window, game, x, y):
        return CardImg(window, self.suit, self.rank)

    def to_tuple(self):
        return self.rank, self.suit, self.value

    def serialize(self):
        """
        Serialize the Card instance into a dictionary format, ensuring consistency
        with the server's MainCard and SideCard serialization.
        """
        return {
            'id': self.card_id,
            'suit': self.suit,
            'rank': self.rank,
            'value': self.value,
            'player_id': self.player_id,
            'game_id': self.game_id,
            'in_deck': self.in_deck,
            'deck_position': self.deck_position,
            'part_of_figure': self.part_of_figure
        }

    def __str__(self):
        return f"{self.rank} of {self.suit}"

    def __repr__(self):
        return f"{self.rank} of {self.suit}"

    def __eq__(self, other):
        return self.value == other.value

    def __lt__(self, other):
        return self.value < other.value

    def __gt__(self, other):
        return self.value > other.value

    def __le__(self, other):
        return self.value <= other.value

    def __ge__(self, other):
        return self.value >= other.value

    def __ne__(self, other):
        return self.value != other.value

    def __hash__(self):
        return hash((self.rank, self.suit, self.value))
