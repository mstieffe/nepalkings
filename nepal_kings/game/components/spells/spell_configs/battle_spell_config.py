"""
Example spell configuration template.

This file demonstrates how to create spell configurations.
Each spell family needs:
- name: Display name
- type: 'greed', 'enchantment', or 'tactics'
- description: What the spell does
- suits: List of suits this spell is available in
- icon_img: Filename for colored icon
- icon_gray_img: Filename for grayscale icon
- frame_img: Filename for normal frame
- frame_closed_img: Filename for greyscale frame
- frame_hidden_img: Filename for hidden frame
- glow_img: Filename for glow effect (e.g., 'yellow.png', 'blue.png')
- spells: Function that generates spell instances
  Battle/tactics spells should have counterable=True
"""

from game.components.spells.spell import Spell
from game.components.cards.card import Card
from config import settings
from config.settings import SUITS_BLACK, SUITS_RED
from itertools import combinations_with_replacement, product


def generate_same_color_spell_variants(family, color_group, ranks, spell_name, **spell_kwargs):
    """
    Generate all spell variants for cards within the same color group.
    
    Args:
        family: The spell family
        color_group: 'red' or 'black'
        ranks: List of card ranks (e.g., ['5', '5'] for two 5s, or ['7', '8', '9'] for a sequence)
        spell_name: Name of the spell
        **spell_kwargs: Additional keyword arguments for Spell constructor (requires_target, counterable, etc.)
    
    Returns:
        List of Spell objects with all valid same-color combinations
    """
    suits = ['Hearts', 'Diamonds'] if color_group == 'red' else ['Spades', 'Clubs']
    spells = []
    
    # Use product to get all suit assignments (2^n combinations for n cards),
    # then deduplicate for cases where ranks repeat (e.g., two 5s where order
    # doesn't matter: 5♥5♦ == 5♦5♥)
    seen = set()
    for suit_combo in product(suits, repeat=len(ranks)):
        # Canonical key: sorted (rank, suit) pairs to detect duplicates
        card_key = tuple(sorted(zip(ranks, suit_combo)))
        if card_key in seen:
            continue
        seen.add(card_key)
        
        cards = [Card(rank, suit, get_card_value(rank)) for rank, suit in zip(ranks, suit_combo)]
        # Use the first suit as the primary suit for the spell
        primary_suit = suit_combo[0]
        
        spells.append(Spell(
            name=spell_name,
            family=family,
            cards=cards,
            suit=primary_suit,
            key_cards=cards,
            **spell_kwargs
        ))
    
    return spells


def get_card_value(rank):
    """Get the numeric value for a card rank."""
    value_map = {
        'J': 1, 'Q': 2, 'K': 4, 'A': 3,
        '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10
    }
    return value_map.get(rank, int(rank) if rank.isdigit() else 0)

CIVIL_WAR_CONFIG = {
    "name": "Civil War",
    "type": "tactics",
    "description": "The upcoming battle is a civil war, where each player may choose two villagers of the same color to fight for them.",
    "suits": ["Hearts", "Spades"],  # Represents red and black suit groups
    "icon_img": "civil_war.png",
    "icon_gray_img": "civil_war.png",
    "frame_img": "gold.png",
    "frame_closed_img": "gold.png",
    "frame_hidden_img": "gold.png",
    "glow_img": "yellow.png",
    "spells": lambda family, suit: generate_same_color_spell_variants(
        family=family,
        color_group='red' if suit == 'Hearts' else 'black',
        ranks=['5', '5'],
        spell_name="Civil War",
        requires_target=False,
        counterable=True,
        possible_during_ceasefire=False
    ),
}



PEASANT_WAR_CONFIG = {
    "name": "Peasant War",
    "type": "tactics",
    "description": "The upcoming battle is a peasant war, where only villagers can be selected for the battle.",
    "suits": ["Hearts", "Spades"],  # Represents red and black suit groups
    "icon_img": "peasant_war.png",
    "icon_gray_img": "peasant_war.png",
    "frame_img": "gold.png",
    "frame_closed_img": "gold.png",
    "frame_hidden_img": "gold.png",
    "glow_img": "yellow.png",
    "spells": lambda family, suit: generate_same_color_spell_variants(
        family=family,
        color_group='red' if suit == 'Hearts' else 'black',
        ranks=['J', 'J'],
        spell_name="Peasant War",
        requires_target=False,
        counterable=True,
        possible_during_ceasefire=False
    ),
}


BLITZKRIEG_CONFIG = {
    "name": "Blitzkrieg",
    "type": "tactics",
    "description": "The upcoming battle is a blitzkrieg, where the opponents battle figure is selected by you.",
    "suits": ["Hearts", "Spades"],  # Represents red and black suit groups
    "icon_img": "blitzkrieg.png",
    "icon_gray_img": "blitzkrieg.png",
    "frame_img": "gold.png",
    "frame_closed_img": "gold.png",
    "frame_hidden_img": "gold.png",
    "glow_img": "yellow.png",
    "spells": lambda family, suit: generate_same_color_spell_variants(
        family=family,
        color_group='red' if suit == 'Hearts' else 'black',
        ranks=['Q', 'Q'],
        spell_name="Blitzkrieg",
        requires_target=False,
        counterable=True,
        possible_during_ceasefire=False
    ),
}

INVADER_SWAP_CONFIG = {
    "name": "Invader Swap",
    "type": "tactics",
    "description": "The role of invader and defender will be swapped for the upcoming battle.",
    "suits": ["Hearts", "Spades"],  # Represents red and black suit groups
    "icon_img": "invader_swap.png",
    "icon_gray_img": "invader_swap.png",
    "frame_img": "gold.png",
    "frame_closed_img": "gold.png",
    "frame_hidden_img": "gold.png",
    "glow_img": "yellow.png",
    "spells": lambda family, suit: generate_same_color_spell_variants(
        family=family,
        color_group='red' if suit == 'Hearts' else 'black',
        ranks=['A', 'A'],
        spell_name="Invader Swap",
        requires_target=False,
        counterable=True,
        possible_during_ceasefire=False
    ),
}

CEASEFIRE_CONFIG = {
    "name": "Ceasefire",
    "type": "tactics",
    "description": "Both players gain 3 additional turns without battle. Ceasefire period starts anew.",
    "suits": ["Hearts", "Spades"],  # Represents red and black suit groups
    "icon_img": "ceasefire.png",
    "icon_gray_img": "ceasefire.png",
    "frame_img": "gold.png",
    "frame_closed_img": "gold.png",
    "frame_hidden_img": "gold.png",
    "glow_img": "yellow.png",
    "spells": lambda family, suit: (
        generate_same_color_spell_variants(
            family=family,
            color_group='red' if suit == 'Hearts' else 'black',
            ranks=['7', '8', '9'],
            spell_name="Ceasefire",
            requires_target=False,
            counterable=True,
            possible_during_ceasefire=False
        ) +
        generate_same_color_spell_variants(
            family=family,
            color_group='red' if suit == 'Hearts' else 'black',
            ranks=['8', '9', '10'],
            spell_name="Ceasefire",
            requires_target=False,
            counterable=True,
            possible_during_ceasefire=False
        )
    ),
}


ALL_BATTLE_CONFIGS = [
    CEASEFIRE_CONFIG,
    PEASANT_WAR_CONFIG,
    CIVIL_WAR_CONFIG,
    INVADER_SWAP_CONFIG,
    BLITZKRIEG_CONFIG,
]