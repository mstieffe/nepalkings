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
  Greed spells should have counterable=False
"""

from game.components.spells.spell import Spell
from game.components.cards.card import Card
from config import settings
from config.settings import SUITS_BLACK, SUITS_RED


DRAW_2_SIDE_CARDS_CONFIG = {
    "name": "Draw 2 SideCards",
    "type": "greed",
    "description": "Draw 2 additional side cards from your deck",
    "suits": SUITS_BLACK + SUITS_RED,
    "icon_img": "draw_two_side.png",
    "icon_gray_img": "draw_two_side.png",
    "frame_img": "blue.png",
    "frame_closed_img": "blue.png",
    "frame_hidden_img": "blue.png",
    "glow_img": "blue.png",
    "spells": lambda family, suit: [
        Spell(
            name=f"Draw 2 SideCards",
            family=family,
            cards=[Card('2', suit, 2)],
            suit=suit,
            key_cards=[Card('2', suit, 2)],
            requires_target=False,
            counterable=False,
        )
    ],  
}


FORCED_DEAL_CONFIG = {
    "name": "Forced Deal",
    "type": "greed",
    "description": "Force a deal with an opponent: opponent and you exchange two cards at random from your main cards.",
    "suits": SUITS_RED + SUITS_BLACK,
    "icon_img": "forced_deal.png",
    "icon_gray_img": "forced_deal.png",
    "frame_img": "blue.png",
    "frame_closed_img": "blue.png",
    "frame_hidden_img": "blue.png",
    "glow_img": "blue.png",
    "spells": lambda family, suit: [
        Spell(
            name=f"Forced Deal",
            family=family,
            cards=[Card('4', suit, 4), Card('4', suit, 4)],
            suit=suit,
            key_cards=[Card('4', suit, 4), Card('4', suit, 4)],
            requires_target=False,
            counterable=False,
        )
    ],  
}


DUMP_CARDS_CONFIG = {
    "name": "Dump Cards",
    "type": "greed",
    "description": "Both players have to dump all their cards and refill 5 new main cards and 4 new side cards.",
    "suits": ["Hearts", "Spades"],  # Represents the two combinations
    "icon_img": "dump_cards.png",
    "icon_gray_img": "dump_cards.png",
    "frame_img": "blue.png",
    "frame_closed_img": "blue.png",
    "frame_hidden_img": "blue.png",
    "glow_img": "blue.png",
    "spells": lambda family, suit: [
        Spell(
            name=f"Dump Cards",
            family=family,
            cards=[Card('7', 'Hearts', 7), Card('7', 'Hearts', 7), Card('7', 'Diamonds', 7), Card('7', 'Diamonds', 7)],
            suit='Hearts',  # Primary suit for this variant
            key_cards=[Card('7', 'Hearts', 7), Card('7', 'Hearts', 7), Card('7', 'Diamonds', 7), Card('7', 'Diamonds', 7)],
            requires_target=False,
            counterable=False,
        )
    ] if suit == "Hearts" else [
        Spell(
            name=f"Dump Cards",
            family=family,
            cards=[Card('7', 'Spades', 7), Card('7', 'Spades', 7), Card('7', 'Clubs', 7), Card('7', 'Clubs', 7)],
            suit='Spades',  # Primary suit for this variant
            key_cards=[Card('7', 'Spades', 7), Card('7', 'Spades', 7), Card('7', 'Clubs', 7), Card('7', 'Clubs', 7)],
            requires_target=False,
            counterable=False,
        )
    ],  
}



DRAW_2_MAIN_CARDS_CONFIG = {
    "name": "Draw 2 MainCards",
    "type": "greed",
    "description": "Draw 2 additional main cards from your deck",
    "suits": SUITS_BLACK + SUITS_RED,
    "icon_img": "draw_two_main.png",
    "icon_gray_img": "draw_two_main.png",
    "frame_img": "blue.png",
    "frame_closed_img": "blue.png",
    "frame_hidden_img": "blue.png",
    "glow_img": "blue.png",
    "spells": lambda family, suit: [
        Spell(
            name=f"Draw 2 MainCards",
            family=family,
            cards=[Card('8', suit, 8)],
            suit=suit,
            key_cards=[Card('8', suit, 8)],
            requires_target=False,
            counterable=False,
        )
    ],  
}

FILL_10_CONFIG = {
    "name": "Fill up to 10",
    "type": "greed",
    "description": "Fill your main hand up to 10 cards.",
    "suits": SUITS_BLACK + SUITS_RED,
    "icon_img": "fill10.png",
    "icon_gray_img": "fill10.png",
    "frame_img": "blue.png",
    "frame_closed_img": "blue.png",
    "frame_hidden_img": "blue.png",
    "glow_img": "blue.png",
    "spells": lambda family, suit: [
        Spell(
            name=f"Fill up to 10",
            family=family,
            cards=[Card('10', suit, 10)],
            suit=suit,
            key_cards=[Card('10', suit, 10)],
            requires_target=False,
            counterable=False,
        )
    ],  
}



ALL_INSTANT_CONFIGS = [
    DRAW_2_SIDE_CARDS_CONFIG,
    DRAW_2_MAIN_CARDS_CONFIG,
    FILL_10_CONFIG,
    DUMP_CARDS_CONFIG,
    FORCED_DEAL_CONFIG,
]