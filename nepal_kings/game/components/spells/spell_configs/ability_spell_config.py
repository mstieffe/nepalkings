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


POISON_CONFIG = {
    "name": "Poison",
    "type": "enchantment",
    "description": "Poison a figure to reduce its power by 6 for the next battle.",
    "suits": SUITS_BLACK,
    "icon_img": "poisson_portion.png",
    "icon_gray_img": "poisson_portion.png",
    "frame_img": "red.png",
    "frame_closed_img": "red.png",
    "frame_hidden_img": "red.png",
    "glow_img": "red.png",
    "spells": lambda family, suit: [
        Spell(
            name=f"Poison",
            family=family,
            cards=[Card('3', suit, 3), Card('3', suit, 3)],
            suit=suit,
            key_cards=[Card('3', suit, 3), Card('3', suit, 3)],
            requires_target=True,
            counterable=False,
        )
    ],  
}

BOOST_CONFIG = {
    "name": "Health Boost",
    "type": "enchantment",
    "description": "Boosts a figure to increase its power by 6 for the next battle.",
    "suits": SUITS_RED,
    "icon_img": "health_portion.png",
    "icon_gray_img": "health_portion.png",
    "frame_img": "red.png",
    "frame_closed_img": "red.png",
    "frame_hidden_img": "red.png",
    "glow_img": "red.png",
    "spells": lambda family, suit: [
        Spell(
            name=f"Health Boost",
            family=family,
            cards=[Card('3', suit, 3), Card('3', suit, 3)],
            suit=suit,
            key_cards=[Card('3', suit, 3), Card('3', suit, 3)],
            requires_target=True,
            counterable=False,
        )
    ],  
}


EXPLOSION_CONFIG = {
    "name": "Explosion",
    "type": "enchantment",
    "description": "Selected figure will be destroyed.",
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
    "suits": SUITS_RED+SUITS_BLACK,
    "icon_img": "eye.png",
    "icon_gray_img": "eye.png",
    "frame_img": "red.png",
    "frame_closed_img": "red.png",
    "frame_hidden_img": "red.png",
    "glow_img": "red.png",
    "spells": lambda family, suit: [
        Spell(
            name=f"All Seeing Eye",
            family=family,
            cards=[Card('9', suit, 9), Card('9', suit, 9)],
            suit=suit,
            key_cards=[Card('9', suit, 9), Card('9', suit, 9)],
            requires_target=False,
            counterable=False,
        )
    ],  
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