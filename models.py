# models.py
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy_utils import ChoiceType
import enum
from datetime import datetime

db = SQLAlchemy()

class ChallengeStatus(enum.Enum):
  OPEN = "open"
  ACCEPTED = "accepted"
  REJECTED = "rejected"

class Challenge(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  challenger_id = db.Column(db.Integer, db.ForeignKey('user.id'))
  challenged_id = db.Column(db.Integer, db.ForeignKey('user.id'))
  status = db.Column(ChoiceType(ChallengeStatus, impl=db.String()), nullable=False, default='Open')
  date = db.Column(db.DateTime, default=datetime.utcnow)

  #challenger = db.relationship('User', foreign_keys=[challenger_id])
  #challenged = db.relationship('User', foreign_keys=[challenged_id])

  def serialize(self):
    return {
      'id': self.id,
      'challenger_id': self.challenger_id,
      'challenged_id': self.challenged_id,
      'status': self.status.value,
      'date': self.date
    }


class Suit(enum.Enum):
    HEARTS = "Hearts"
    DIAMONDS = "Diamonds"
    CLUBS = "Clubs"
    SPADES = "Spades"

class Rank(enum.Enum):
    TWO = '2'
    THREE = '3'
    FOUR = '4'
    FIVE = '5'
    SIX = '6'
    SEVEN = '7'
    EIGHT = '8'
    NINE = '9'
    TEN = '10'
    JACK = 'J'
    QUEEN = 'Q'
    KING = 'K'
    ACE = 'A'

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    challenges_issued = db.relationship('Challenge', backref='challenger', lazy=True,
                                        foreign_keys='Challenge.challenger_id')
    challenges_received = db.relationship('Challenge', backref='challenged', lazy=True,
                                          foreign_keys='Challenge.challenged_id')
    #email = db.Column(db.String(120), unique=True, nullable=False)

    def serialize(self):
        return {
            'id': self.id,
            'username': self.username,
            'challenges_issued': [challenge.serialize() for challenge in self.challenges_issued],
            'challenges_received': [challenge.serialize() for challenge in self.challenges_received]
        }

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Game(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    players = db.relationship('Player', backref='game', lazy=True)
    state = db.Column(db.String(20), nullable=False, default='open')
    date = db.Column(db.DateTime, default=datetime.utcnow)
    cards = db.relationship('Card', backref='game', lazy=True)

    def serialize(self):
        return {
            'id': self.id,
            'state': self.state,
            'date': self.date,
            'players': [player.serialize() for player in self.players],
            'cards': [card.serialize() for card in self.cards]
        }

class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'))
    hand = db.relationship('Card', backref='player', lazy=True)
    status = db.Column(db.String(20), nullable=False, default='active')

    def serialize(self):
        user = User.query.get(self.user_id)
        if user:
            username = user.username
        else:
            username = None

        return {
            'id': self.id,
            'user_id': self.user_id,
            'game_id': self.game_id,
            'hand': [card.serialize() for card in self.hand],
            'status': self.status,
            'username': username
        }

class Card(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'))
    suit = db.Column(ChoiceType(Suit, impl=db.String()))
    rank = db.Column(ChoiceType(Rank, impl=db.String()))
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'))

    def serialize(self):
        return {
            'id': self.id,
            'suit': self.suit.value,
            'rank': self.rank.value,
            'player_id': self.player_id,
            'game_id': self.game_id
        }

"""
class Deck:
    def __init__(self, game):
        self.game = game
        self.cards = Card.query.filter_by(player_id=None)

    def shuffle(self):
        random.shuffle(self.cards)

    def deal(self, player, num_cards=1):
        for _ in range(num_cards):
            card = self.cards.pop()
            card.player_id = player.id
"""
