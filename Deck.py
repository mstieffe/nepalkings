from models import db, Game, Player, Card
import random
class Deck:
    def __init__(self, game):
        self.game = game
        self.cards = []

    def create(self):
        ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        suits = ['Hearts', 'Diamonds', 'Clubs', 'Spades']  # Hearts, Diamonds, Clubs, Spades

        for suit in suits:
            for rank in ranks:
                card = Card(game_id=self.game.id, rank=rank, suit=suit)
                self.cards.append(card)

        db.session.add_all(self.cards)
        db.session.commit()

    def shuffle(self):
        random.shuffle(self.cards)

    def deal_cards(self, players, num_cards=10):
        num_players = len(players)
        num_cards_to_deal = num_players * num_cards

        if num_cards_to_deal > len(self.cards):
            raise Exception("Not enough cards in the deck to deal.")

        for player in players:
            for _ in range(num_cards):
                card = self.cards.pop()
                card.player_id = player.id

        db.session.commit()

    def deal_card(self, player):
        card = self.cards.pop()
        card.player_id = player.id
        db.session.commit()

    def get_cards(self, player):
        cards = Card.query.filter_by(player_id=player.id)

        return cards