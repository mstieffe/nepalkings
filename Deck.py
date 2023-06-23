from models import db, Game, Player, MainCard, SideCard
import random

class Deck:
    def __init__(self, game):
        self.game = game
        self.main_cards = []
        self.side_cards = []

    def create(self):
        main_ranks = ['7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        side_ranks = ['2', '3', '4', '5', '6']
        suits = ['Hearts', 'Diamonds', 'Clubs', 'Spades']

        for suit in suits:
            for rank in main_ranks:
                card = MainCard(game_id=self.game.id, rank=rank, suit=suit)
                self.main_cards.append(card)

            for rank in side_ranks:
                card = SideCard(game_id=self.game.id, rank=rank, suit=suit)
                self.side_cards.append(card)

        db.session.add_all(self.main_cards)
        db.session.add_all(self.side_cards)
        db.session.commit()

    def shuffle(self):
        random.shuffle(self.main_cards)
        random.shuffle(self.side_cards)
        db.session.commit()

    def deal_cards(self, players, num_main_cards=7, num_side_cards=3):
        num_players = len(players)

        for player in players:
            for _ in range(num_main_cards):
                card = self.main_cards.pop()
                card.player_id = player.id

            for _ in range(num_side_cards):
                card = self.side_cards.pop()
                card.player_id = player.id

        db.session.commit()

    def deal_card(self, player, card_type="main"):
        if card_type == "main":
            card = self.main_cards.pop()
        elif card_type == "side":
            card = self.side_cards.pop()
        else:
            raise ValueError("Invalid card_type. Must be 'main' or 'side'.")

        card.player_id = player.id
        db.session.commit()

    def get_cards(self, player):
        main_cards = MainCard.query.filter_by(player_id=player.id)
        side_cards = SideCard.query.filter_by(player_id=player.id)

        return main_cards, side_cards
