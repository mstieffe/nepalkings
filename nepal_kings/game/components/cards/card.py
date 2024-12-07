from game.components.cards.card_img import CardImg
from config import settings

class Card:
    def __init__(self, rank, suit, value):
        self.rank = rank
        self.suit = suit
        self.value = int(value)

        self.is_ZK = True if self.rank in settings.RANKS_ZK else False
        self.is_main_card = True if self.rank in settings.RANKS_MAIN_CARDS else False

    def make_icon(self, window, game, x, y):
        return CardImg(window, self.suit, self.rank)

    def to_tuple(self):
        return self.rank, self.suit, self.value

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