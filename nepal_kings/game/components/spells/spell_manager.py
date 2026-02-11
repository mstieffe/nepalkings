from typing import List, Optional, Dict
import pygame
from collections import Counter
from game.components.spells.spell import Spell, SpellFamily
from game.components.cards.card import Card
from config import settings


class SpellManager:
    """Manages all spell families and spells in the game."""
    
    def __init__(self):
        """Initialize the SpellManager."""
        self.families: Dict[str, SpellFamily] = {}
        self.spells: List[Spell] = []
        self.spells_by_type: Dict[str, List[Spell]] = {
            'greed': [],
            'enchantment': [],
            'tactics': []
        }
        self.spells_by_suit: Dict[str, List[Spell]] = {
            'Diamonds': [],
            'Hearts': [],
            'Clubs': [],
            'Spades': []
        }
        self.spells_by_name: Dict[str, List[Spell]] = {}
        
        # Initialize spell families from configs
        self.initialize_spell_families()
    
    def add_spell_family(self, family: SpellFamily) -> None:
        """Add a spell family to the manager."""
        self.families[family.name] = family
    
    def add_spell(self, spell: Spell) -> None:
        """Add a spell to the manager and categorize it."""
        self.spells.append(spell)
        self.spells_by_type[spell.family.type].append(spell)
        self.spells_by_suit[spell.suit].append(spell)
        self.spells_by_name.setdefault(spell.name, []).append(spell)
    
    def load_image(self, path: str) -> pygame.Surface:
        """Load an image from the given path."""
        try:
            return pygame.image.load(path).convert_alpha()
        except pygame.error as e:
            print(f"Error loading image {path}: {e}")
            # Return a placeholder surface
            placeholder = pygame.Surface((100, 100))
            placeholder.fill((200, 200, 200))
            return placeholder
    
    def create_spell_family(
        self,
        name: str,
        type: str,
        description: str,
        icon_img: pygame.Surface,
        icon_gray_img: pygame.Surface,
        frame_img: pygame.Surface,
        frame_closed_img: pygame.Surface,
        frame_hidden_img: pygame.Surface,
        glow_img: pygame.Surface,
        spells: Optional[List[Spell]] = None,
    ) -> SpellFamily:
        """Create and add a SpellFamily."""
        family = SpellFamily(
            name=name,
            type=type,
            description=description,
            icon_img=icon_img,
            icon_gray_img=icon_gray_img,
            frame_img=frame_img,
            frame_closed_img=frame_closed_img,
            frame_hidden_img=frame_hidden_img,
            glow_img=glow_img,
            spells=spells,
        )
        self.add_spell_family(family)
        return family
    
    def initialize_spell_families(self) -> None:
        """
        Initialize all spell families from config files.
        Import and process all spell configs here.
        """
        try:
            from game.components.spells.spell_configs import SPELL_CONFIG_LIST
            
            for config in SPELL_CONFIG_LIST:
                family = self.create_spell_family(
                    name=config["name"],
                    type=config["type"],
                    description=config["description"],
                    icon_img=self.load_image(settings.SPELL_ICON_IMG_DIR + config["icon_img"]),
                    icon_gray_img=self.load_image(settings.SPELL_ICON_GREYSCALE_IMG_DIR + config["icon_gray_img"]),
                    frame_img=self.load_image(settings.SPELL_FRAME_IMG_DIR + config["frame_img"]),
                    frame_closed_img=self.load_image(settings.SPELL_FRAME_GREYSCALE_IMG_DIR + config["frame_closed_img"]),
                    frame_hidden_img=self.load_image(settings.SPELL_FRAME_HIDDEN_IMG_DIR + config["frame_hidden_img"]),
                    glow_img=self.load_image(settings.SPELL_GLOW_IMG_DIR + config["glow_img"]),
                )
                
                # Create spell instances for each suit
                family_spells = []
                for suit in config.get("suits", ['Diamonds', 'Hearts', 'Clubs', 'Spades']):
                    for spell in config["spells"](family, suit):
                        family_spells.append(spell)
                        self.add_spell(spell)
                
                family.spells = family_spells
                
        except ImportError:
            print("No spell configs found. Create spell_configs/__init__.py with SPELL_CONFIG_LIST")
    
    def match_spell(self, cards: List[Card]) -> Optional[Spell]:
        """
        Match a set of cards to a spell.
        
        :param cards: List of cards to match
        :return: Matching Spell or None
        """
        card_set = {(card.suit, card.rank) for card in cards}
        return next(
            (spell for spell in self.spells if {(card.suit, card.rank) for card in spell.cards} == card_set),
            None
        )
    
    def get_spells_by_type(self, type: str) -> List[Spell]:
        """Get all spells of a specific type."""
        return self.spells_by_type.get(type, [])
    
    def get_spells_by_suit(self, suit: str) -> List[Spell]:
        """Get all spells of a specific suit."""
        return self.spells_by_suit.get(suit, [])
    
    def get_family_by_name(self, name: str) -> Optional[SpellFamily]:
        """Get a spell family by name."""
        return self.families.get(name)
    
    def get_all_families(self) -> List[SpellFamily]:
        """Get all spell families."""
        return list(self.families.values())
    
    def find_castable_spells(self, hand: List[Card]) -> List[Spell]:
        """
        Find all spells that can be cast with the given hand.
        
        :param hand: Player's current hand of cards
        :return: List of castable spells
        """
        castable = []
        
        # Count available cards in hand - use (suit, rank) format
        hand_counter = Counter((card.suit, card.rank) for card in hand)
        
        for spell in self.spells:
            # Count required cards for spell - use (suit, rank) format
            spell_counter = Counter((card.suit, card.rank) for card in spell.cards)
            
            # Check if all spell cards are available in sufficient quantity
            can_cast = True
            for card_tuple, count in spell_counter.items():
                if hand_counter[card_tuple] < count:
                    can_cast = False
                    break
            
            if can_cast:
                castable.append(spell)
        
        return castable
    
    def get_families_with_castable_spells(self, hand: List[Card]) -> List[SpellFamily]:
        """
        Get all spell families that have at least one castable spell.
        
        :param hand: Player's current hand
        :return: List of spell families
        """
        castable_spells = self.find_castable_spells(hand)
        family_names = {spell.family.name for spell in castable_spells}
        return [self.families[name] for name in family_names]
