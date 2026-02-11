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

CIVIL_WAR_CONFIG = {
    "name": "Civil War",
    "type": "tactics",
    "description": "The upcoming battle is a civil war, where each player may choose two villagers of the same color to fight for them.",
    "suits": SUITS_RED + SUITS_BLACK,
    "icon_img": "civil_war.png",
    "icon_gray_img": "civil_war.png",
    "frame_img": "gold.png",
    "frame_closed_img": "gold.png",
    "frame_hidden_img": "gold.png",
    "glow_img": "yellow.png",
    "spells": lambda family, suit: [
        Spell(
            name=f"Civil War",
            family=family,
            cards=[Card('5', suit, 5), Card('5', suit, 5)],
            suit=suit,
            key_cards=[Card('5', suit, 5), Card('5', suit, 5)],
            requires_target=True,
            counterable=True,
        )
    ],  
}



PEASANT_WAR_CONFIG = {
    "name": "Peasant War",
    "type": "tactics",
    "description": "The upcoming battle is a peasant war, where only villagers can be selected for the battle.",
    "suits": SUITS_RED + SUITS_BLACK,
    "icon_img": "peasant_war.png",
    "icon_gray_img": "peasant_war.png",
    "frame_img": "gold.png",
    "frame_closed_img": "gold.png",
    "frame_hidden_img": "gold.png",
    "glow_img": "yellow.png",
    "spells": lambda family, suit: [
        Spell(
            name=f"Peasant War",
            family=family,
            cards=[Card('J', suit, 1), Card('J', suit, 1)],
            suit=suit,
            key_cards=[Card('J', suit, 1), Card('J', suit, 1)],
            requires_target=True,
            counterable=True,
        )
    ],  
}


BLITZKRIEG_CONFIG = {
    "name": "Blitzkrieg",
    "type": "tactics",
    "description": "The upcoming battle is a blitzkrieg, where the opponents battle figure is selected by you.",
    "suits": SUITS_RED + SUITS_BLACK,
    "icon_img": "blitzkrieg.png",
    "icon_gray_img": "blitzkrieg.png",
    "frame_img": "gold.png",
    "frame_closed_img": "gold.png",
    "frame_hidden_img": "gold.png",
    "glow_img": "yellow.png",
    "spells": lambda family, suit: [
        Spell(
            name=f"Blitzkrieg",
            family=family,
            cards=[Card('Q', suit, 2), Card('Q', suit, 2)],
            suit=suit,
            key_cards=[Card('Q', suit, 2), Card('Q', suit, 2)],
            requires_target=True,
            counterable=True,
        )
    ],  
}

INVADER_SWAP_CONFIG = {
    "name": "Invader Swap",
    "type": "tactics",
    "description": "The role of invader and defender will be swapped for the upcoming battle.",
    "suits": SUITS_RED + SUITS_BLACK,
    "icon_img": "invader_swap.png",
    "icon_gray_img": "invader_swap.png",
    "frame_img": "gold.png",
    "frame_closed_img": "gold.png",
    "frame_hidden_img": "gold.png",
    "glow_img": "yellow.png",
    "spells": lambda family, suit: [
        Spell(
            name=f"Invader Swap",
            family=family,
            cards=[Card('A', suit, 3), Card('A', suit, 3)],
            suit=suit,
            key_cards=[Card('A', suit, 3), Card('A', suit, 3)],
            requires_target=True,
            counterable=True,
        )
    ],  
}


ALL_BATTLE_CONFIGS = [
    PEASANT_WAR_CONFIG,
    CIVIL_WAR_CONFIG,
    INVADER_SWAP_CONFIG,
    BLITZKRIEG_CONFIG,
]