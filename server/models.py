# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy_utils import ChoiceType
import enum
from datetime import datetime, timezone
import server_settings as server_config

db = SQLAlchemy()


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class ChallengeStatus(enum.Enum):
  OPEN = "open"
  ACCEPTED = "accepted"
  REJECTED = "rejected"

class Challenge(db.Model):
  id = db.Column(db.Integer, primary_key=True)
  challenger_id = db.Column(db.Integer, db.ForeignKey('user.id'))
  challenged_id = db.Column(db.Integer, db.ForeignKey('user.id'))
  status = db.Column(ChoiceType(ChallengeStatus, impl=db.String()), nullable=False, default=ChallengeStatus.OPEN)
  stake = db.Column(db.Integer, nullable=False, default=45)  # Gold stake / point threshold to win
  turn_time_limit = db.Column(db.Integer, nullable=True, default=None)  # Seconds per turn (None = no limit)
  game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=True)  # Set when challenge is accepted
  date = db.Column(db.DateTime, default=_utcnow)

  def serialize(self):
    return {
      'id': self.id,
      'challenger_id': self.challenger_id,
      'challenged_id': self.challenged_id,
      'challenger_name': self.challenger.username if self.challenger else None,
      'challenged_name': self.challenged.username if self.challenged else None,
      'status': self.status.value if hasattr(self.status, 'value') else str(self.status),
      'stake': self.stake,
      'turn_time_limit': self.turn_time_limit,
      'game_id': self.game_id,
      'date': self.date.isoformat() if self.date else None
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
    gold = db.Column(db.Integer, nullable=False, default=server_config.INITIAL_GOLD)  # Starting gold
    last_active = db.Column(db.DateTime, nullable=True)  # Heartbeat timestamp
    is_ai = db.Column(db.Boolean, nullable=False, default=False)  # AI opponent flag
    # Email verification fields (all optional for backward compatibility)
    email = db.Column(db.String(255), nullable=True, unique=True)
    email_verified = db.Column(db.Boolean, nullable=False, default=False)
    email_verification_token = db.Column(db.String(128), nullable=True)
    email_verification_sent_at = db.Column(db.DateTime, nullable=True)
    # v2.0: Collection & Kingdom
    booster_packs = db.Column(db.Integer, nullable=False, default=0)
    booster_packs_side = db.Column(db.Integer, nullable=False, default=0)
    last_gold_collection = db.Column(db.DateTime, nullable=True)
    last_conquer_at = db.Column(db.DateTime, nullable=True)
    challenges_issued = db.relationship('Challenge', backref='challenger', lazy=True,
                                        foreign_keys='Challenge.challenger_id')
    challenges_received = db.relationship('Challenge', backref='challenged', lazy=True,
                                          foreign_keys='Challenge.challenged_id')

    def serialize(self):
        is_online = self.is_ai  # AI users are always "online"
        if not is_online and self.last_active:
            is_online = (_utcnow() - self.last_active).total_seconds() < 60
        return {
            'id': self.id,
            'username': self.username,
            'gold': self.gold,
            'is_online': is_online,
            'is_ai': self.is_ai,
            'email_verified': self.email_verified,
            'booster_packs': self.booster_packs,
            'booster_packs_side': self.booster_packs_side,
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
    state = db.Column(db.String(20), nullable=False, default='open')  # 'open' | 'finished'
    mode = db.Column(db.String(10), nullable=False, default='duel')  # 'duel' | 'conquer'
    land_id = db.Column(db.Integer, db.ForeignKey('land.id'), nullable=True)  # conquer mode only
    conquer_config_id = db.Column(db.Integer, db.ForeignKey('land_config.id',
                                  use_alter=True, name='fk_game_conquer_config'),
                                  nullable=True)
    defence_config_id = db.Column(db.Integer, db.ForeignKey('land_config.id',
                                  use_alter=True, name='fk_game_defence_config'),
                                  nullable=True)
    date = db.Column(db.DateTime, default=_utcnow)
    stake = db.Column(db.Integer, nullable=False, default=45)  # Gold stake / point threshold to win
    turn_time_limit = db.Column(db.Integer, nullable=True, default=None)  # Seconds per turn (None = no limit)
    winner_player_id = db.Column(db.Integer, nullable=True)  # Player who won the game
    finished_at = db.Column(db.DateTime, nullable=True)  # When the game ended
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

    # Persisted battle result so the second client can retrieve it after cleanup
    # {winner_player_id, loser_player_id, winner_name, loser_name,
    #  points_awarded, destroyed_figure_name, destroyed_figure_family}
    last_battle_result = db.Column(db.JSON, nullable=True)

    # Reason for auto-loss/fold so the waiting player knows WHY they won/lost
    # e.g. 'no_figures_to_advance', 'no_defender_figures', 'resource_deficit', 'fold'
    auto_loss_reason = db.Column(db.String(50), nullable=True)
    auto_loss_detail = db.Column(db.String(200), nullable=True)  # e.g. figure name for deficit

    # Figures currently resting (rest_after_attack skill — cannot act for one round after battle)
    resting_figure_ids = db.Column(db.JSON, nullable=True)  # list of figure IDs

    # Battle shop gamble tracking — {str(player_id): count}
    battle_gamble_counts = db.Column(db.JSON, nullable=True)

    land = db.relationship('Land', foreign_keys=[land_id], lazy=True)
    log_entries = db.relationship('LogEntry', backref='game', lazy=True)
    chat_messages = db.relationship('ChatMessage', backref='game', lazy=True)
    active_spells = db.relationship('ActiveSpell', backref='game', lazy=True, foreign_keys='ActiveSpell.game_id')
    battle_moves = db.relationship('BattleMove', backref='game', lazy=True, foreign_keys='BattleMove.game_id')


    def serialize(self):
        return {
            'id': self.id,
            'state': self.state,
            'mode': self.mode,
            'land_id': self.land_id,
            'land_tier': self.land.tier if self.land else None,
            'land_gold_rate': self.land.gold_rate if self.land else None,
            'land_suit_bonus_suit': self.land.suit_bonus_suit if self.land else None,
            'land_suit_bonus_value': self.land.suit_bonus_value if self.land else None,
            'date': self.date.isoformat() if self.date else None,
            'stake': self.stake,
            'turn_time_limit': self.turn_time_limit,
            'winner_player_id': self.winner_player_id,
            'finished_at': self.finished_at.isoformat() if self.finished_at else None,
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
            'auto_loss_reason': self.auto_loss_reason,
            'auto_loss_detail': self.auto_loss_detail,
            'battle_round': self.battle_round,
            'battle_turn_player_id': self.battle_turn_player_id,
            'battle_skipped_rounds': self.battle_skipped_rounds,
            'post_battle_drawn_cards': self.post_battle_drawn_cards,
            'last_battle_result': self.last_battle_result,
            'resting_figure_ids': self.resting_figure_ids or [],
            'battle_gamble_counts': self.battle_gamble_counts or {},
            'players': [player.serialize() for player in self.players],
            'main_cards': [card.serialize() for card in self.main_cards],
            'side_cards': [card.serialize() for card in self.side_cards],
            'log_entries': [entry.serialize() for entry in self.log_entries],
            'chat_messages': [message.serialize() for message in self.chat_messages],
            'battle_moves': [move.serialize() for move in self.battle_moves],
            'active_spells': [spell.serialize() for spell in self.active_spells],
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
        user = db.session.get(User, self.user_id)
        username = user.username if user else None
        is_online = False
        if user and user.last_active:
            is_online = (_utcnow() - user.last_active).total_seconds() < 60

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
            'username': username,
            'is_online': is_online
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
            card = db.session.get(MainCard, self.card_id)
        elif self.card_type == 'side':
            card = db.session.get(SideCard, self.card_id)
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
    checkmate = db.Column(db.Boolean, default=False, nullable=False)  # If destroyed, owner loses
    cannot_be_blocked = db.Column(db.Boolean, default=False, nullable=False)  # Cannot be counter-advanced when advancing
    rest_after_attack = db.Column(db.Boolean, default=False, nullable=False)  # Must rest one round after battle
    cards = db.relationship('CardToFigure', backref='figure', lazy=True)
    date_created = db.Column(db.DateTime, default=_utcnow)

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
            'checkmate': self.checkmate,
            'cannot_be_blocked': self.cannot_be_blocked,
            'rest_after_attack': self.rest_after_attack,
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
    timestamp = db.Column(db.DateTime, default=_utcnow)  # When the event occurred

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
    timestamp = db.Column(db.DateTime, default=_utcnow)  # When the message was sent

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
    created_at = db.Column(db.DateTime, default=_utcnow)
    
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
    created_at = db.Column(db.DateTime, default=_utcnow)

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


class GameResult(db.Model):
    """Persisted record of a finished game for statistics and ranking."""
    id = db.Column(db.Integer, primary_key=True)
    game_id = db.Column(db.Integer, db.ForeignKey('game.id'), nullable=False)
    winner_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    loser_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    winner_username = db.Column(db.String(80), nullable=False)
    loser_username = db.Column(db.String(80), nullable=False)
    winner_score = db.Column(db.Integer, nullable=False)
    loser_score = db.Column(db.Integer, nullable=False)
    stake = db.Column(db.Integer, nullable=False)  # The gold stake / point threshold
    gold_awarded = db.Column(db.Integer, nullable=False)  # Gold given to winner (2 × stake)
    rounds_played = db.Column(db.Integer, nullable=False)
    finished_at = db.Column(db.DateTime, default=_utcnow)

    def serialize(self):
        return {
            'id': self.id,
            'game_id': self.game_id,
            'winner_user_id': self.winner_user_id,
            'loser_user_id': self.loser_user_id,
            'winner_username': self.winner_username,
            'loser_username': self.loser_username,
            'winner_score': self.winner_score,
            'loser_score': self.loser_score,
            'stake': self.stake,
            'gold_awarded': self.gold_awarded,
            'rounds_played': self.rounds_played,
            'finished_at': self.finished_at.isoformat() if self.finished_at else None,
        }


# ──────────────────────────────────────────────────────────────────────────────
# v2.0 Models: Collection, Kingdom, Lands
# ──────────────────────────────────────────────────────────────────────────────

class CollectionCard(db.Model):
    """A single card copy in a user's persistent card collection."""
    __tablename__ = 'collection_card'

    id        = db.Column(db.Integer, primary_key=True)
    user_id   = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    suit      = db.Column(db.String(10), nullable=False)   # Hearts/Diamonds/Clubs/Spades
    rank      = db.Column(db.String(5),  nullable=False)   # '7'..'A'
    value     = db.Column(db.Integer,    nullable=False)
    locked    = db.Column(db.Boolean,    nullable=False, default=False)
    lock_type = db.Column(db.String(30), nullable=True)    # e.g. 'conquer_figure', 'defence_move'
    lock_ref_id = db.Column(db.Integer,  nullable=True)    # FK to config element using this card

    user = db.relationship('User', backref=db.backref('collection_cards', lazy='dynamic'))

    __table_args__ = (
        db.Index('ix_collection_card_user_suit_rank', 'user_id', 'suit', 'rank'),
    )

    def serialize(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'suit': self.suit,
            'rank': self.rank,
            'value': self.value,
            'locked': self.locked,
            'lock_type': self.lock_type,
            'lock_ref_id': self.lock_ref_id,
        }


class Land(db.Model):
    """A single hex tile on the kingdom map."""
    __tablename__ = 'land'

    id               = db.Column(db.Integer, primary_key=True)
    col              = db.Column(db.Integer, nullable=False)
    row              = db.Column(db.Integer, nullable=False)
    tier             = db.Column(db.Integer, nullable=False)   # 1-3
    gold_rate        = db.Column(db.Float,   nullable=False)   # gold per hour
    suit_bonus_suit  = db.Column(db.String(10), nullable=False)
    suit_bonus_value = db.Column(db.Integer, nullable=False)
    owner_user_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True, index=True)
    owned_since      = db.Column(db.DateTime, nullable=True)
    defence_config_id = db.Column(db.Integer, db.ForeignKey('land_config.id',
                                  use_alter=True, name='fk_land_defence_config'),
                                  nullable=True)
    ai_template_index = db.Column(db.Integer, nullable=True)

    __table_args__ = (
        db.UniqueConstraint('col', 'row', name='uq_land_col_row'),
    )

    owner = db.relationship('User', backref=db.backref('owned_lands', lazy='dynamic'),
                            foreign_keys=[owner_user_id])

    def serialize(self):
        owner_data = None
        if self.owner_user_id:
            owner_data = {
                'user_id': self.owner_user_id,
                'username': self.owner.username if self.owner else None,
                'owned_since': self.owned_since.isoformat() if self.owned_since else None,
            }
        # Resolve AI name from template when land is unowned
        ai_name = None
        if not self.owner_user_id and self.ai_template_index is not None:
            from server_settings import AI_DEFENCE_TEMPLATES
            templates = AI_DEFENCE_TEMPLATES.get(self.tier, [])
            if 0 <= self.ai_template_index < len(templates):
                ai_name = templates[self.ai_template_index].get('ai_name')
        return {
            'id': self.id,
            'col': self.col,
            'row': self.row,
            'tier': self.tier,
            'gold_rate': self.gold_rate,
            'suit_bonus_suit': self.suit_bonus_suit,
            'suit_bonus_value': self.suit_bonus_value,
            'owner': owner_data,
            'ai_name': ai_name,
            'defence_config_id': self.defence_config_id,
            'ai_template_index': self.ai_template_index,
        }


class LandConfig(db.Model):
    """A conquer or defence configuration (figures, moves, modifiers, spells)."""
    __tablename__ = 'land_config'

    id            = db.Column(db.Integer, primary_key=True)
    user_id       = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, index=True)
    config_type   = db.Column(db.String(10), nullable=False)  # 'conquer' | 'defence'
    land_id       = db.Column(db.Integer, db.ForeignKey('land.id',
                              use_alter=True, name='fk_land_config_land'),
                              nullable=True)  # defence → which land; conquer → NULL
    # Battle modifier (JSON): {'type': 'Blitzkrieg'|'Peasant War'|'Civil War'}
    battle_modifier      = db.Column(db.JSON, nullable=True)
    modifier_card_ids    = db.Column(db.JSON, nullable=True)  # [collection_card.id, ...]
    # Battle figure(s) — defence only
    battle_figure_id     = db.Column(db.Integer,
                                     db.ForeignKey('land_config_figure.id',
                                                   use_alter=True,
                                                   name='fk_lc_battle_fig'),
                                     nullable=True)
    battle_figure_id_2   = db.Column(db.Integer,
                                     db.ForeignKey('land_config_figure.id',
                                                   use_alter=True,
                                                   name='fk_lc_battle_fig2'),
                                     nullable=True)  # civil war
    # Spell — defence only (alternative to battle figure)
    spell_name           = db.Column(db.String(50), nullable=True)   # 'health_boost'|'poison'
    spell_target_figure_id = db.Column(db.Integer, nullable=True)    # health boost target
    spell_card_ids       = db.Column(db.JSON, nullable=True)         # [collection_card.id, ...]
    # Auto-gambling — defence only
    auto_gamble          = db.Column(db.Boolean, nullable=False, default=False)
    created_at           = db.Column(db.DateTime, default=_utcnow)

    user = db.relationship('User', backref=db.backref('land_configs', lazy='dynamic'))
    figures = db.relationship('LandConfigFigure',
                              backref='config',
                              lazy=True,
                              foreign_keys='LandConfigFigure.config_id')
    battle_moves = db.relationship('LandConfigBattleMove',
                                   backref='config',
                                   lazy=True,
                                   foreign_keys='LandConfigBattleMove.config_id')

    def serialize(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'config_type': self.config_type,
            'land_id': self.land_id,
            'battle_modifier': self.battle_modifier,
            'modifier_card_ids': self.modifier_card_ids,
            'battle_figure_id': self.battle_figure_id,
            'battle_figure_id_2': self.battle_figure_id_2,
            'spell_name': self.spell_name,
            'spell_target_figure_id': self.spell_target_figure_id,
            'spell_card_ids': self.spell_card_ids,
            'auto_gamble': self.auto_gamble,
            'figures': [f.serialize() for f in self.figures],
            'battle_moves': [m.serialize() for m in self.battle_moves],
        }


class LandConfigFigure(db.Model):
    """A figure built in a conquer or defence configuration."""
    __tablename__ = 'land_config_figure'

    id          = db.Column(db.Integer, primary_key=True)
    config_id   = db.Column(db.Integer, db.ForeignKey('land_config.id'), nullable=False, index=True)
    family_name = db.Column(db.String(50), nullable=False)
    name        = db.Column(db.String(50), nullable=False)
    suit        = db.Column(db.String(10), nullable=False)
    color       = db.Column(db.String(10), nullable=False)   # 'offensive'|'defensive'
    field       = db.Column(db.String(10), nullable=False)   # 'castle'|'village'|'military'
    card_ids    = db.Column(db.JSON, nullable=False)          # [collection_card.id, ...]
    card_roles  = db.Column(db.JSON, nullable=False)          # ['key','key','number'] etc.
    produces    = db.Column(db.JSON, nullable=True)           # Resources produced (same as Figure)
    requires    = db.Column(db.JSON, nullable=True)           # Resources required (same as Figure)
    description         = db.Column(db.String(255), nullable=True)
    upgrade_family_name = db.Column(db.String(50), nullable=True)
    checkmate           = db.Column(db.Boolean, default=False, nullable=False)
    cannot_be_blocked   = db.Column(db.Boolean, default=False, nullable=False)
    rest_after_attack   = db.Column(db.Boolean, default=False, nullable=False)

    def serialize(self):
        return {
            'id': self.id,
            'config_id': self.config_id,
            'family_name': self.family_name,
            'name': self.name,
            'suit': self.suit,
            'color': self.color,
            'field': self.field,
            'card_ids': self.card_ids,
            'card_roles': self.card_roles,
            'produces': self.produces or {},
            'requires': self.requires or {},
            'description': self.description or '',
            'upgrade_family_name': self.upgrade_family_name,
            'checkmate': self.checkmate,
            'cannot_be_blocked': self.cannot_be_blocked,
            'rest_after_attack': self.rest_after_attack,
        }


class LandConfigBattleMove(db.Model):
    """A battle move purchased in a conquer or defence configuration."""
    __tablename__ = 'land_config_battle_move'

    id           = db.Column(db.Integer, primary_key=True)
    config_id    = db.Column(db.Integer, db.ForeignKey('land_config.id'), nullable=False, index=True)
    family_name  = db.Column(db.String(50), nullable=False)
    card_id      = db.Column(db.Integer, nullable=False)      # collection_card.id
    suit         = db.Column(db.String(10), nullable=False)
    rank         = db.Column(db.String(5),  nullable=False)
    value        = db.Column(db.Integer, nullable=False)
    round_index  = db.Column(db.Integer, nullable=False)      # 0, 1, 2
    call_figure_id = db.Column(db.Integer,
                               db.ForeignKey('land_config_figure.id'), nullable=True)

    def serialize(self):
        return {
            'id': self.id,
            'config_id': self.config_id,
            'family_name': self.family_name,
            'card_id': self.card_id,
            'suit': self.suit,
            'rank': self.rank,
            'value': self.value,
            'round_index': self.round_index,
            'call_figure_id': self.call_figure_id,
        }


class LandAttackLog(db.Model):
    """History of land conquer battles."""
    __tablename__ = 'land_attack_log'

    id               = db.Column(db.Integer, primary_key=True)
    land_id          = db.Column(db.Integer, db.ForeignKey('land.id'), nullable=False)
    attacker_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    defender_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # NULL for AI
    result           = db.Column(db.String(15), nullable=False)  # 'attacker_won'|'defender_won'
    card_won_suit    = db.Column(db.String(10), nullable=True)
    card_won_rank    = db.Column(db.String(5),  nullable=True)
    card_lost_suit   = db.Column(db.String(10), nullable=True)
    card_lost_rank   = db.Column(db.String(5),  nullable=True)
    seen_by_defender = db.Column(db.Boolean, nullable=False, default=False)
    timestamp        = db.Column(db.DateTime, default=_utcnow)

    land = db.relationship('Land', backref=db.backref('attack_logs', lazy='dynamic'))

    def serialize(self):
        return {
            'id': self.id,
            'land_id': self.land_id,
            'attacker_user_id': self.attacker_user_id,
            'defender_user_id': self.defender_user_id,
            'result': self.result,
            'card_won_suit': self.card_won_suit,
            'card_won_rank': self.card_won_rank,
            'card_lost_suit': self.card_lost_suit,
            'card_lost_rank': self.card_lost_rank,
            'seen_by_defender': self.seen_by_defender,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
        }
