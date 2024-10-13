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

class MainRank(enum.Enum):
    SEVEN = '7'
    EIGHT = '8'
    NINE = '9'
    TEN = '10'
    JACK = 'J'
    QUEEN = 'Q'
    KING = 'K'
    ACE = 'A'

class SideRank(enum.Enum):
    TWO = '2'
    THREE = '3'
    FOUR = '4'
    FIVE = '5'
    SIX = '6'

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    challenges_issued = db.relationship('Challenge', backref='challenger', lazy=True,
                                        foreign_keys='Challenge.challenger_id')
    challenges_received = db.relationship('Challenge', backref='challenged', lazy=True,
                                          foreign_keys='Challenge.challenged_id')

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
    main_cards = db.relationship('MainCard', backref='game', lazy=True)
    side_cards = db.relationship('SideCard', backref='game', lazy=True)

    def serialize(self):
        return {
            'id': self.id,
            'state': self.state,
            'date': self.date,
            'players': [player.serialize() for player in self.players],
            'main_cards': [card.serialize() for card in self.main_cards],
            'side_cards': [card.serialize() for card in self.side_cards]
        }

class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'))
    main_hand = db.relationship('MainCard', backref='player', lazy=True)
    side_hand = db.relationship('SideCard', backref='player', lazy=True)
    figures = db.relationship('Figure', backref='player', lazy=True)  # New relationship
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
            'main_hand': [card.serialize() for card in self.main_hand],
            'side_hand': [card.serialize() for card in self.side_hand],
            'figures': [figure.serialize() for figure in self.figures],  # Serialize figures
            'status': self.status,
            'username': username
        }
class MainCard(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=True)  # Null if in the deck
    suit = db.Column(ChoiceType(Suit, impl=db.String()))
    rank = db.Column(ChoiceType(MainRank, impl=db.String()))
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'))
    in_deck = db.Column(db.Boolean, default=True)  # Tracks if the card is still in the deck
    deck_position = db.Column(db.Integer, nullable=True)  # Optional: track deck order
    part_of_figure = db.Column(db.Boolean, default=False)  # New: Is this card part of a figure?

    def serialize(self):
        return {
            'id': self.id,
            'suit': self.suit.value,
            'rank': self.rank.value,
            'player_id': self.player_id,
            'game_id': self.game_id,
            'in_deck': self.in_deck,
            'deck_position': self.deck_position,
            'part_of_figure': self.part_of_figure
        }

class SideCard(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=True)
    suit = db.Column(ChoiceType(Suit, impl=db.String()))
    rank = db.Column(ChoiceType(SideRank, impl=db.String()))
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'))
    in_deck = db.Column(db.Boolean, default=True)
    deck_position = db.Column(db.Integer, nullable=True)
    part_of_figure = db.Column(db.Boolean, default=False)  # New: Is this card part of a figure?

    def serialize(self):
        return {
            'id': self.id,
            'suit': self.suit.value,
            'rank': self.rank.value,
            'player_id': self.player_id,
            'game_id': self.game_id,
            'in_deck': self.in_deck,
            'deck_position': self.deck_position,
            'part_of_figure': self.part_of_figure
        }


class Figure(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    cards = db.relationship('CardToFigure', backref='figure', lazy=True)
    figure_type = db.Column(db.String(50), nullable=False)  # Type of the figure, e.g., "Straight", "Flush", etc.
    date_created = db.Column(db.DateTime, default=datetime.utcnow)

    def serialize(self):
        return {
            'id': self.id,
            'player_id': self.player_id,
            'game_id': self.game_id,
            'cards': [card.serialize() for card in self.cards],
            'figure_type': self.figure_type,
            'date_created': self.date_created
        }
    

class CardToFigure(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    figure_id = db.Column(db.Integer, db.ForeignKey('figure.id'), nullable=False)
    card_id = db.Column(db.Integer, nullable=False)  # Store card IDs here
    card_type = db.Column(db.String(10), nullable=False)  # 'main' or 'side', to differentiate between MainCard and SideCard

    def serialize(self):
        return {
            'id': self.id,
            'figure_id': self.figure_id,
            'card_id': self.card_id,
            'card_type': self.card_type
        }