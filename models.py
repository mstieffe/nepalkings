from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    players = db.relationship('Player', backref='game', lazy=True)
    cards = db.relationship('Card', backref='game', lazy=True)

class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'))
    hand = db.relationship('Card', backref='player', lazy=True)
    # other player-related data...

class Card(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'))
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'))
    suit = db.Column(db.String(20))
    rank = db.Column(db.String(20))
    # other card-related data...

class Deck:
    def __init__(self, game):
        self.game = game
        self.cards = Card.query.filter_by(game_id=game.id, player_id=None)

    def shuffle(self):
        random.shuffle(self.cards)

    def deal(self, player, num_cards=1):
        for _ in range(num_cards):
            card = self.cards.pop()
            card.player_id = player.id
