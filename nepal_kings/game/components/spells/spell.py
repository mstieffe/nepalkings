from typing import List, Optional, Dict, Any
import pygame
from game.components.cards.card import Card
from config import settings


class SpellFamily:
    """Represents a family/category of spells with shared attributes."""
    
    def __init__(
        self,
        name: str,
        type: str,  # 'greed', 'enchantment', or 'tactics'
        description: str,
        icon_img: pygame.Surface,
        icon_gray_img: pygame.Surface,
        frame_img: pygame.Surface,
        frame_closed_img: pygame.Surface,
        frame_hidden_img: pygame.Surface,
        glow_img: pygame.Surface,
        spells: Optional[List['Spell']] = None,
    ):
        """
        Initialize a SpellFamily.
        
        :param name: Name of the spell family
        :param type: Type of spell ('greed', 'enchantment', or 'tactics')
        :param description: Description of what the spell does
        :param icon_img: Colored icon image
        :param icon_gray_img: Grayscale icon image
        :param frame_img: Normal frame image
        :param frame_closed_img: Greyscale frame image (for unbuildable)
        :param frame_hidden_img: Hidden frame image (for opponent spells)
        :param glow_img: Glow effect image for active state
        :param spells: List of spell instances in this family
        """
        self.name = name
        self.type = type
        self.description = description
        self.icon_img = icon_img
        self.icon_gray_img = icon_gray_img
        self.frame_img = frame_img
        self.frame_closed_img = frame_closed_img
        self.frame_hidden_img = frame_hidden_img
        self.glow_img = glow_img
        self.spells = spells or []
    
    def make_icon(self, window, game, x, y):
        """Creates a spell icon for this family."""
        from game.components.spells.spell_icon import CastSpellIcon
        return CastSpellIcon(window, game, self, x, y)
    
    def get_spells_by_suit(self, suit: str) -> List['Spell']:
        """Returns all spells of this family for a specific suit."""
        return [spell for spell in self.spells if spell.suit == suit]


class Spell:
    """Represents a specific spell instance with its cards and logic."""
    
    def __init__(
        self,
        name: str,
        family: SpellFamily,
        cards: List[Card],
        suit: str,
        key_cards: Optional[List[Card]] = None,
        number_card: Optional[Card] = None,
        upgrade_card: Optional[Card] = None,
        requires_target: bool = False,
        target_type: Optional[str] = None,  # 'own_figure', 'opponent_figure', 'any_figure', 'player'
        counterable: bool = False,
        possible_during_ceasefire: bool = True,
    ):
        """
        Initialize a Spell.
        
        :param name: Name of the spell instance
        :param family: The SpellFamily this spell belongs to
        :param cards: List of cards that compose this spell
        :param suit: The suit of this spell ('Diamonds', 'Hearts', 'Clubs', 'Spades')
        :param key_cards: Cards that define the core of the spell
        :param number_card: Card that determines spell power/duration
        :param upgrade_card: Card that upgrades the spell
        :param requires_target: Whether the spell needs a target (figure, player, etc.)
        :param target_type: Type of target required if requires_target is True
        :param counterable: Whether the opponent can counter this spell (True for battle spells)
        :param possible_during_ceasefire: Whether the spell can be cast during ceasefire (False for battle spells)
        """
        self.name = name
        self.family = family
        self.cards = cards
        self.suit = suit
        self.key_cards = key_cards or []
        self.number_card = number_card
        self.upgrade_card = upgrade_card
        self.requires_target = requires_target
        self.target_type = target_type
        self.counterable = counterable
        self.possible_during_ceasefire = possible_during_ceasefire
        
        # Runtime attributes (set when spell is cast/active)
        self.id = None  # Database ID when spell is cast
        self.player_id = None
        self.game_id = None
        self.target_figure_id = None
        self.is_active = False
        self.cast_round = None
        self.duration = 0  # Number of rounds the spell is active
    
    def to_tuple(self) -> tuple:
        """Returns a tuple representation of the spell's cards for matching."""
        return tuple(sorted((card.suit, card.rank) for card in self.cards))
    
    def execute(self, game, target=None) -> Dict[str, Any]:
        """
        Execute the spell's effect.
        This is a placeholder - each spell family should override this method.
        
        :param game: The game instance
        :param target: The target (figure, player, etc.) if required
        :return: Dictionary with execution result
        """
        return {
            'success': False,
            'message': f'Spell {self.name} execution not implemented'
        }
    
    def get_power(self) -> int:
        """Get the power/magnitude of the spell based on number_card."""
        if self.number_card:
            rank_values = {
                'A': 1, '2': 2, '3': 3, '4': 4, '5': 5, '6': 6,
                '7': 7, '8': 8, '9': 9, '10': 10, 'J': 11, 'Q': 12, 'K': 13
            }
            return rank_values.get(self.number_card.rank, 0)
        return 0
    
    def is_upgraded(self) -> bool:
        """Check if the spell has an upgrade card."""
        return self.upgrade_card is not None
    
    def serialize(self) -> Dict[str, Any]:
        """Serialize spell data for database storage."""
        return {
            'id': self.id,
            'name': self.name,
            'family_name': self.family.name,
            'type': self.family.type,
            'suit': self.suit,
            'cards': [{'rank': card.rank, 'suit': card.suit, 'value': card.value} for card in self.cards],
            'key_cards': [{'rank': card.rank, 'suit': card.suit, 'value': card.value} for card in self.key_cards],
            'number_card': {'rank': self.number_card.rank, 'suit': self.number_card.suit, 'value': self.number_card.value} if self.number_card else None,
            'upgrade_card': {'rank': self.upgrade_card.rank, 'suit': self.upgrade_card.suit, 'value': self.upgrade_card.value} if self.upgrade_card else None,
            'requires_target': self.requires_target,
            'target_type': self.target_type,
            'target_figure_id': self.target_figure_id,
            'is_active': self.is_active,
            'cast_round': self.cast_round,
            'duration': self.duration,
            'player_id': self.player_id,
            'game_id': self.game_id,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any], spell_family: SpellFamily) -> 'Spell':
        """Create a Spell instance from serialized data."""
        cards = [Card(c['rank'], c['suit'], c['value']) for c in data.get('cards', [])]
        key_cards = [Card(c['rank'], c['suit'], c['value']) for c in data.get('key_cards', [])]
        number_card = Card(data['number_card']['rank'], data['number_card']['suit'], data['number_card']['value']) if data.get('number_card') else None
        upgrade_card = Card(data['upgrade_card']['rank'], data['upgrade_card']['suit'], data['upgrade_card']['value']) if data.get('upgrade_card') else None
        
        spell = cls(
            name=data['name'],
            family=spell_family,
            cards=cards,
            suit=data['suit'],
            key_cards=key_cards,
            number_card=number_card,
            upgrade_card=upgrade_card,
            requires_target=data.get('requires_target', False),
            target_type=data.get('target_type'),
        )
        
        spell.id = data.get('id')
        spell.player_id = data.get('player_id')
        spell.game_id = data.get('game_id')
        spell.target_figure_id = data.get('target_figure_id')
        spell.is_active = data.get('is_active', False)
        spell.cast_round = data.get('cast_round')
        spell.duration = data.get('duration', 0)
        
        return spell
