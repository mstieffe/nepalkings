class Card:
    def __init__(self, rank, suit, value):
        self.rank = rank
        self.suit = suit
        self.value = int(value)

    def to_tuple(self):
        return self.rank, self.suit, self.value

    def __str__(self):
        return f"{self.name} of {self.suit}"

    def __repr__(self):
        return f"{self.name} of {self.suit}"

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
        return hash((self.name, self.suit, self.value))