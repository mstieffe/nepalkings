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
  Enchantment spells should have counterable=False
"""

from game.components.spells.spell import Spell
from game.components.cards.card import Card
from config import settings
from config.settings import SUITS_BLACK, SUITS_RED
from game.components.spells.spell_configs.battle_spell_config import generate_same_color_spell_variants


POISON_CONFIG = {
    "name": "Poison",
    "type": "enchantment",
    "description": "Poison a figure to reduce its power by 6 for the next battle.",
    "suits": ["Spades"],  # Represents black suit group
    "icon_img": "poisson_portion.png",
    "icon_gray_img": "poisson_portion.png",
    "frame_img": "red.png",
    "frame_closed_img": "red.png",
    "frame_hidden_img": "red.png",
    "glow_img": "red.png",
    "spells": lambda family, suit: generate_same_color_spell_variants(
        family=family,
        color_group='black',
        ranks=['3', '3'],
        spell_name="Poison",
        requires_target=True,
        counterable=False
    ),
}

BOOST_CONFIG = {
    "name": "Health Boost",
    "type": "enchantment",
    "description": "Boosts a figure to increase its power by 6 for the next battle.",
    "suits": ["Hearts"],  # Represents red suit group
    "icon_img": "health_portion.png",
    "icon_gray_img": "health_portion.png",
    "frame_img": "red.png",
    "frame_closed_img": "red.png",
    "frame_hidden_img": "red.png",
    "glow_img": "red.png",
    "spells": lambda family, suit: generate_same_color_spell_variants(
        family=family,
        color_group='red',
        ranks=['3', '3'],
        spell_name="Health Boost",
        requires_target=True,
        counterable=False
    ),
}


EXPLOSION_CONFIG = {
    "name": "Explosion",
    "type": "enchantment",
    "description": "Selected figure will be destroyed (does not apply to Maharajas).",
    "suits": ["Hearts", "Spades"],  # Represents the two combinations
    "icon_img": "bomb.png",
    "icon_gray_img": "bomb.png",
    "frame_img": "red.png",
    "frame_closed_img": "red.png",
    "frame_hidden_img": "red.png",
    "glow_img": "red.png",
    "spells": lambda family, suit: [
        Spell(
            name=f"Explosion",
            family=family,
            cards=[Card('6', 'Hearts', 6), Card('6', 'Hearts', 6), Card('6', 'Diamonds', 6), Card('6', 'Diamonds', 6)],
            suit='Hearts',  # Primary suit for this variant
            key_cards=[Card('6', 'Hearts', 6), Card('6', 'Hearts', 6), Card('6', 'Diamonds', 6), Card('6', 'Diamonds', 6)],
            requires_target=True,
            counterable=False,
        )
    ] if suit == "Hearts" else [
        Spell(
            name=f"Explosion",
            family=family,
            cards=[Card('6', 'Spades', 6), Card('6', 'Spades', 6), Card('6', 'Clubs', 6), Card('6', 'Clubs', 6)],
            suit='Spades',  # Primary suit for this variant
            key_cards=[Card('6', 'Spades', 6), Card('6', 'Spades', 6), Card('6', 'Clubs', 6), Card('6', 'Clubs', 6)],
            requires_target=True,
            counterable=False,
        )
    ],  
}


ALL_SEEING_EYE_CONFIG = {
    "name": "All Seeing Eye",
    "type": "enchantment",
    "description": "All cards + figures of the opponent become visible until the end of this round.",
    "suits": ["Hearts", "Spades"],  # Represents red and black suit groups
    "icon_img": "eye.png",
    "icon_gray_img": "eye.png",
    "frame_img": "red.png",
    "frame_closed_img": "red.png",
    "frame_hidden_img": "red.png",
    "glow_img": "red.png",
    "spells": lambda family, suit: generate_same_color_spell_variants(
        family=family,
        color_group='red' if suit == 'Hearts' else 'black',
        ranks=['9', '9'],
        spell_name="All Seeing Eye",
        requires_target=False,
        counterable=False
    ),
}


INIFINITE_HAMMER_CONFIG = {
    "name": "Infinite Hammer",
    "type": "enchantment",
    "description": "During this turn you can build/upgrade/pick-up as many figures as you want.",
    "suits": SUITS_BLACK + SUITS_RED,
    "icon_img": "infinite_hammer.png",
    "icon_gray_img": "infinite_hammer.png",
    "frame_img": "red.png",
    "frame_closed_img": "red.png",
    "frame_hidden_img": "red.png",
    "glow_img": "red.png",
    "spells": lambda family, suit: [
        Spell(
            name=f"Infinite Hammer",
            family=family,
            cards=[Card('K', suit, 4)],
            suit=suit,
            key_cards=[Card('K', suit, 4)],
            requires_target=False,
            counterable=False,
        )
    ],  
}

ALL_ABILITY_CONFIGS = [
    POISON_CONFIG,
    BOOST_CONFIG,
    ALL_SEEING_EYE_CONFIG,
    EXPLOSION_CONFIG,
    INIFINITE_HAMMER_CONFIG,
]