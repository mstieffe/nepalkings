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

    # Ceasefire tracking
    ceasefire_active = db.Column(db.Boolean, nullable=False, default=True)  # Ceasefire starts active each round
    ceasefire_start_turn = db.Column(db.Integer, nullable=True)  # Turn count when ceasefire started

    # Spell-related fields
    pending_spell_id = db.Column(db.Integer, db.ForeignKey('active_spell.id'), nullable=True)  # Spell waiting for counter
    battle_modifier = db.Column(db.JSON, nullable=True)  # Active battle modifications from tactics spells
    waiting_for_counter_player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=True)  # Player who can counter

    # Advance/battle state tracking
    advancing_figure_id = db.Column(db.Integer, db.ForeignKey('figure.id'), nullable=True)  # Figure that advanced
    advancing_figure_id_2 = db.Column(db.Integer, db.ForeignKey('figure.id'), nullable=True)  # Second figure (Civil War)
    advancing_player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=True)  # Player who advanced
    defending_figure_id = db.Column(db.Integer, db.ForeignKey('figure.id'), nullable=True)  # Defender figure selected by opponent
    defending_figure_id_2 = db.Column(db.Integer, db.ForeignKey('figure.id'), nullable=True)  # Second defender (Civil War)

    # Battle decision tracking (fold/battle)
    battle_decisions = db.Column(db.JSON, nullable=True)  # {str(player_id): 'battle'|'fold'}
    battle_confirmed = db.Column(db.Boolean, nullable=False, default=False)  # True when both chose battle
    battle_moves_confirmed = db.Column(db.JSON, nullable=True)  # {str(player_id): True} — tracks who confirmed battle moves
    fold_outcome = db.Column(db.String(20), nullable=True)  # 'fold_win' | 'fold_draw' | None
    fold_winner_id = db.Column(db.Integer, nullable=True)  # Winner of fold (player_id)

    # 3-round battle phase tracking
    battle_round = db.Column(db.Integer, nullable=False, default=0)  # current battle round (0-2)
    battle_turn_player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=True)  # whose turn in battle
    battle_skipped_rounds = db.Column(db.JSON, nullable=True)  # {str(player_id): [round_indices]} — tracks skipped rounds

    # Post-battle side card draw — {str(player_id): [{suit, rank}, ...]}
    post_battle_drawn_cards = db.Column(db.JSON, nullable=True)

    log_entries = db.relationship('LogEntry', backref='game', lazy=True)
    chat_messages = db.relationship('ChatMessage', backref='game', lazy=True)
    active_spells = db.relationship('ActiveSpell', backref='game', lazy=True, foreign_keys='ActiveSpell.game_id')
    battle_moves = db.relationship('BattleMove', backref='game', lazy=True, foreign_keys='BattleMove.game_id')


    def serialize(self):
        return {
            'id': self.id,
            'state': self.state,
            'date': self.date,
            'current_round': self.current_round,
            'invader_player_id': self.invader_player_id,
            'turn_player_id': self.turn_player_id,
            'ceasefire_active': self.ceasefire_active,
            'ceasefire_start_turn': self.ceasefire_start_turn,
            'pending_spell_id': self.pending_spell_id,
            'battle_modifier': self.battle_modifier,
            'waiting_for_counter_player_id': self.waiting_for_counter_player_id,
            'advancing_figure_id': self.advancing_figure_id,
            'advancing_figure_id_2': self.advancing_figure_id_2,
            'advancing_player_id': self.advancing_player_id,
            'defending_figure_id': self.defending_figure_id,
            'defending_figure_id_2': self.defending_figure_id_2,
            'battle_decisions': self.battle_decisions,
            'battle_confirmed': self.battle_confirmed,
            'battle_moves_confirmed': self.battle_moves_confirmed,
            'fold_outcome': self.fold_outcome,
            'fold_winner_id': self.fold_winner_id,
            'battle_round': self.battle_round,
            'battle_turn_player_id': self.battle_turn_player_id,
            'battle_skipped_rounds': self.battle_skipped_rounds,
            'post_battle_drawn_cards': self.post_battle_drawn_cards,
            'players': [player.serialize() for player in self.players],
            'main_cards': [card.serialize() for card in self.main_cards],
            'side_cards': [card.serialize() for card in self.side_cards],
            'log_entries': [entry.serialize() for entry in self.log_entries],
            'chat_messages': [message.serialize() for message in self.chat_messages],
            'battle_moves': [move.serialize() for move in self.battle_moves]
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

        # Query cards directly to avoid SQLAlchemy relationship caching issues
        main_hand_cards = MainCard.query.filter_by(
            player_id=self.id,
            in_deck=False
        ).all()
        
        side_hand_cards = SideCard.query.filter_by(
            player_id=self.id,
            in_deck=False
        ).all()

        return {
            'id': self.id,
            'user_id': self.user_id,
            'game_id': self.game_id,
            'main_hand': [card.serialize() for card in main_hand_cards],
            'side_hand': [card.serialize() for card in side_hand_cards],
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
    part_of_battle_move = db.Column(db.Boolean, default=False)  # Is this card reserved for a battle move?

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
            'part_of_figure': self.part_of_figure,
            'part_of_battle_move': self.part_of_battle_move
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
    part_of_battle_move = db.Column(db.Boolean, default=False)  # Is this card reserved for a battle move?

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
            'part_of_figure': self.part_of_figure,
            'part_of_battle_move': self.part_of_battle_move
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
    field = db.Column(db.String(20), nullable=True)  # castle, village, or military
    color = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(50), nullable=False)
    suit = db.Column(db.String(20), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    upgrade_family_name = db.Column(db.String(50), nullable=True)
    produces = db.Column(db.JSON, nullable=True)  # Resources produced
    requires = db.Column(db.JSON, nullable=True)  # Resources required
    cards = db.relationship('CardToFigure', backref='figure', lazy=True)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)

    def serialize(self):
        return {
            'id': self.id,
            'player_id': self.player_id,
            'game_id': self.game_id,
            'family_name': self.family_name,
            'field': self.field,
            'color': self.color,
            'name': self.name,
            'suit': self.suit,
            'description': self.description,
            'upgrade_family_name': self.upgrade_family_name,
            'produces': self.produces or {},
            'requires': self.requires or {},
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


class ActiveSpell(db.Model):
    """Represents an active spell effect in the game."""
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)  # Player who cast the spell
    spell_name = db.Column(db.String(100), nullable=False)  # Name of the spell
    spell_type = db.Column(db.String(20), nullable=False)  # 'greed', 'enchantment', or 'tactics'
    spell_family_name = db.Column(db.String(100), nullable=False)  # Family name
    suit = db.Column(db.String(20), nullable=False)  # Suit of the spell
    target_figure_id = db.Column(db.Integer, db.ForeignKey('figure.id'), nullable=True)  # Target figure if applicable
    cast_round = db.Column(db.Integer, nullable=False)  # Round when spell was cast
    duration = db.Column(db.Integer, default=0)  # Duration in rounds (0 = instant)
    is_active = db.Column(db.Boolean, default=True)  # Whether spell effect is still active
    is_pending = db.Column(db.Boolean, default=False)  # True if waiting for counter
    counterable = db.Column(db.Boolean, default=False)  # Whether this spell can be countered
    effect_data = db.Column(db.JSON, nullable=True)  # JSON data for spell-specific effects
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship to player
    caster = db.relationship('Player', foreign_keys=[player_id], backref='cast_spells')
    target_figure = db.relationship('Figure', foreign_keys=[target_figure_id])

    def serialize(self):
        return {
            'id': self.id,
            'game_id': self.game_id,
            'player_id': self.player_id,
            'spell_name': self.spell_name,
            'spell_type': self.spell_type,
            'spell_family_name': self.spell_family_name,
            'suit': self.suit,
            'target_figure_id': self.target_figure_id,
            'cast_round': self.cast_round,
            'duration': self.duration,
            'is_active': self.is_active,
            'is_pending': self.is_pending,
            'counterable': self.counterable,
            'effect_data': self.effect_data,
            'created_at': self.created_at.isoformat(),
        }


class BattleMove(db.Model):
    """A purchased battle move for a player in a game."""
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey('player.id'), nullable=False)
    family_name = db.Column(db.String(50), nullable=False)  # e.g. 'Call Villager', 'Block', 'Dagger'
    card_id = db.Column(db.Integer, nullable=False)  # ID of the reserved card
    card_type = db.Column(db.String(10), nullable=False)  # 'main' or 'side'
    suit = db.Column(db.String(20), nullable=False)
    rank = db.Column(db.String(5), nullable=False)
    value = db.Column(db.Integer, nullable=False)    # Double Dagger: second card info (nullable for normal moves)
    card_id_b = db.Column(db.Integer, nullable=True)
    card_type_b = db.Column(db.String(10), nullable=True)
    suit_b = db.Column(db.String(20), nullable=True)
    value_a = db.Column(db.Integer, nullable=True)
    value_b = db.Column(db.Integer, nullable=True)
    played_round = db.Column(db.Integer, nullable=True)  # None=in hand, 0/1/2=played in that battle round
    call_figure_id = db.Column(db.Integer, db.ForeignKey('figure.id'), nullable=True)  # figure called
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    player = db.relationship('Player', backref='battle_moves', foreign_keys=[player_id])

    def serialize(self):
        data = {
            'id': self.id,
            'game_id': self.game_id,
            'player_id': self.player_id,
            'family_name': self.family_name,
            'card_id': self.card_id,
            'card_type': self.card_type,
            'suit': self.suit,
            'rank': self.rank,
            'value': self.value,
        }
        # Include Double Dagger extra fields when present
        if self.card_id_b is not None:
            data['card_id_b'] = self.card_id_b
            data['card_type_b'] = self.card_type_b
        if self.suit_b is not None:
            data['suit_b'] = self.suit_b
        if self.value_a is not None:
            data['value_a'] = self.value_a
        if self.value_b is not None:
            data['value_b'] = self.value_b
        if self.played_round is not None:
            data['played_round'] = self.played_round
        if self.call_figure_id is not None:
            data['call_figure_id'] = self.call_figure_id
        return data
