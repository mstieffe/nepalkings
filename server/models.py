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
    players = db.relationship(
        'Player',
        backref='game',
        lazy=True,
        foreign_keys='Player.game_id'  # Specify the foreign key explicitly
    )
    state = db.Column(db.String(20), nullable=False, default='open')
    date = db.Column(db.DateTime, default=datetime.utcnow)
    main_cards = db.relationship('MainCard', backref='game', lazy=True)
    side_cards = db.relationship('SideCard', backref='game', lazy=True)

    current_round = db.Column(db.Integer, nullable=False, default=1)  # New field
    invader_player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=True)  # New field
    turn_player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=True)  # New field

    log_entries = db.relationship('LogEntry', backref='game', lazy=True)
    chat_messages = db.relationship('ChatMessage', backref='game', lazy=True)


    def serialize(self):
        return {
            'id': self.id,
            'state': self.state,
            'date': self.date,
            'current_round': self.current_round,
            'invader_player_id': self.invader_player_id,
            'turn_player_id': self.turn_player_id,
            'players': [player.serialize() for player in self.players],
            'main_cards': [card.serialize() for card in self.main_cards],
            'side_cards': [card.serialize() for card in self.side_cards],
            'log_entries': [entry.serialize() for entry in self.log_entries],
            'chat_messages': [message.serialize() for message in self.chat_messages]
        }


class Player(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'))
    main_hand = db.relationship('MainCard', backref='player', lazy=True)
    side_hand = db.relationship('SideCard', backref='player', lazy=True)
    figures = db.relationship('Figure', backref='player', lazy=True)

    turns_left = db.Column(db.Integer, nullable=False, default=0)  # New field
    points = db.Column(db.Integer, nullable=False, default=0)  # New field
    status = db.Column(db.String(20), nullable=False, default='active')

    sent_messages = db.relationship('ChatMessage', foreign_keys='ChatMessage.sender_id', backref='sender', lazy=True)
    received_messages = db.relationship('ChatMessage', foreign_keys='ChatMessage.receiver_id', backref='receiver', lazy=True)

    def serialize(self):
        user = User.query.get(self.user_id)
        username = user.username if user else None

        return {
            'id': self.id,
            'user_id': self.user_id,
            'game_id': self.game_id,
            'main_hand': [card.serialize() for card in self.main_hand],
            'side_hand': [card.serialize() for card in self.side_hand],
            'figures': [figure.serialize() for figure in self.figures],
            'turns_left': self.turns_left,
            'points': self.points,
            'status': self.status,
            'username': username
        }


class MainCard(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=True)  # Null if in the deck
    suit = db.Column(ChoiceType(Suit, impl=db.String()))
    rank = db.Column(ChoiceType(MainRank, impl=db.String()))
    value = db.Column(db.Integer, nullable=False)  # New: Store the card value  
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'))
    in_deck = db.Column(db.Boolean, default=True)  # Tracks if the card is still in the deck
    deck_position = db.Column(db.Integer, nullable=True)  # Optional: track deck order
    part_of_figure = db.Column(db.Boolean, default=False)  # New: Is this card part of a figure?

    def serialize(self):
        """
        Serialize the MainCard instance into a dictionary with consistent field naming and order.
        """
        return {
            'id': self.id,
            'rank': self.rank.value,
            'suit': self.suit.value,
            'value': self.value,
            'game_id': self.game_id,
            'player_id': self.player_id,
            'in_deck': self.in_deck,
            'deck_position': self.deck_position,
            'part_of_figure': self.part_of_figure
        }


class SideCard(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=True)
    suit = db.Column(ChoiceType(Suit, impl=db.String()))
    rank = db.Column(ChoiceType(SideRank, impl=db.String()))
    value = db.Column(db.Integer, nullable=False)  # New: Store the card value
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'))
    in_deck = db.Column(db.Boolean, default=True)
    deck_position = db.Column(db.Integer, nullable=True)
    part_of_figure = db.Column(db.Boolean, default=False)  # New: Is this card part of a figure?

    def serialize(self):
        """
        Serialize the SideCard instance into a dictionary with consistent field naming and order.
        """
        return {
            'id': self.id,
            'rank': self.rank.value,
            'suit': self.suit.value,
            'value': self.value,
            'game_id': self.game_id,
            'player_id': self.player_id,
            'in_deck': self.in_deck,
            'deck_position': self.deck_position,
            'part_of_figure': self.part_of_figure
        }



class CardRole(enum.Enum):
    KEY = "key"
    UPGRADE = "upgrade"
    NUMBER = "number"


class CardToFigure(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    figure_id = db.Column(db.Integer, db.ForeignKey('figure.id'), nullable=False)
    card_id = db.Column(db.Integer, nullable=False)  # Store card IDs here
    card_type = db.Column(db.String(10), nullable=False)  # 'main' or 'side', to differentiate card decks
    role = db.Column(ChoiceType(CardRole, impl=db.String()), nullable=False)  # Role in the figure

    def serialize(self):
        # Base metadata
        card_data = {
            'id': self.id,
            'figure_id': self.figure_id,
            'card_id': self.card_id,
            'card_type': self.card_type,
            'role': self.role.value,
        }

        # Fetch card details based on card type
        if self.card_type == 'main':
            card = MainCard.query.get(self.card_id)
        elif self.card_type == 'side':
            card = SideCard.query.get(self.card_id)
        else:
            card = None

        if card:
            # Extend with card details
            card_data.update({
                'rank': card.rank.value,
                'suit': card.suit.value,
                'value': card.value,
                'player_id': card.player_id,
                'game_id': card.game_id,
                'in_deck': card.in_deck,
                'deck_position': card.deck_position,
                'part_of_figure': card.part_of_figure,
            })

        return card_data



class Figure(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    family_name = db.Column(db.String(50), nullable=False)
    color = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    suit = db.Column(db.String(20), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    upgrade_family_name = db.Column(db.String(50), nullable=True)
    cards = db.relationship('CardToFigure', backref='figure', lazy=True)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)

    def serialize(self):
        return {
            'id': self.id,
            'player_id': self.player_id,
            'game_id': self.game_id,
            'family_name': self.family_name,
            'color': self.color,
            'name': self.name,
            'suit': self.suit,
            'description': self.description,
            'upgrade_family_name': self.upgrade_family_name,
            'cards': [card.serialize() for card in self.cards],
            'date_created': self.date_created.isoformat(),
        }
    
class LogEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=True)  # Player associated with the event
    round_number = db.Column(db.Integer, nullable=False)  # The round during which the event occurred
    turn_number = db.Column(db.Integer, nullable=False)  # The turn within the round
    message = db.Column(db.String(500), nullable=False)  # Description of the event
    author = db.Column(db.String(80), nullable=False)  # Who logged the event (e.g., "system", "player_name")
    type = db.Column(db.String(50), nullable=False)  # Event type (e.g., "move", "draw", "figure", etc.)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)  # When the event occurred

    def serialize(self):
        return {
            'id': self.id,
            'game_id': self.game_id,
            'player_id': self.player_id,
            'round_number': self.round_number,
            'turn_number': self.turn_number,
            'message': self.message,
            'author': self.author,
            'type': self.type,
            'timestamp': self.timestamp.isoformat(),
        }


class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)  # Sender of the message
    receiver_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)  # Receiver of the message
    message = db.Column(db.String(1000), nullable=False)  # Content of the message
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)  # When the message was sent

    def serialize(self):
        return {
            'id': self.id,
            'game_id': self.game_id,
            'sender_id': self.sender_id,
            'receiver_id': self.receiver_id,
            'message': self.message,
            'timestamp': self.timestamp.isoformat(),
        }
