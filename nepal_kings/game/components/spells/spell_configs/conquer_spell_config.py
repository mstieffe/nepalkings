# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Conquer-only prelude spell families.

These families are selectable as conquer/defence prelude spells only.
``conquer_only: True`` keeps them out of the duel spell book while their
icons and recipes still load for the prelude pickers, timeline, and
animations.
"""

from game.components.spells.spell_configs.battle_spell_config import (
    generate_same_color_spell_variants,
)


ROYAL_DECREE_CONFIG = {
    "name": "Royal Decree",
    "type": "tactics",
    "description": (
        "The kings command the battle: only castle figures may advance or "
        "defend. Both players dump their hands and draw fresh cards."
    ),
    "suits": ["Hearts", "Spades"],  # Represents red and black suit groups
    "icon_img": "kings_war.png",
    "icon_gray_img": "kings_war.png",
    "frame_img": "gold.png",
    "frame_closed_img": "gold.png",
    "frame_hidden_img": "gold.png",
    "glow_img": "yellow.png",
    "conquer_only": True,
    "spells": lambda family, suit: generate_same_color_spell_variants(
        family=family,
        color_group='red' if suit == 'Hearts' else 'black',
        ranks=['K', 'K'],
        spell_name="Royal Decree",
        requires_target=False,
        counterable=False,
    ),
}


COPY_FIGURE_CONFIG = {
    "name": "Copy Figure",
    "type": "enchantment",
    "description": (
        "Copy one enemy figure at battle start: a full-power clone joins "
        "your side for this battle. The target stays hidden while you "
        "choose; the copy is never a checkmate figure."
    ),
    "suits": ["Hearts", "Spades"],  # Represents red and black suit groups
    "icon_img": "copy.png",
    "icon_gray_img": "copy.png",
    "frame_img": "red.png",
    "frame_closed_img": "red.png",
    "frame_hidden_img": "red.png",
    "glow_img": "red.png",
    "conquer_only": True,
    "spells": lambda family, suit: generate_same_color_spell_variants(
        family=family,
        color_group='red' if suit == 'Hearts' else 'black',
        ranks=['10', '10'],
        spell_name="Copy Figure",
        requires_target=False,
        counterable=False,
    ),
}


LANDSLIDE_CONFIG = {
    "name": "Landslide",
    "type": "enchantment",
    "description": (
        "A landslide buries the land's blessing: the land bonus is inverted "
        "for this battle — figures matching the land suit lose it instead "
        "of gaining it (both sides)."
    ),
    "suits": ["Hearts", "Spades"],  # Represents red and black suit groups
    "icon_img": "landslide.png",
    "icon_gray_img": "landslide.png",
    "frame_img": "red.png",
    "frame_closed_img": "red.png",
    "frame_hidden_img": "red.png",
    "glow_img": "red.png",
    "conquer_only": True,
    "spells": lambda family, suit: generate_same_color_spell_variants(
        family=family,
        color_group='red' if suit == 'Hearts' else 'black',
        ranks=['2', '2'],
        spell_name="Landslide",
        requires_target=False,
        counterable=False,
    ),
}


DRAW_4_MAIN_CARDS_CONFIG = {
    "name": "Draw 4 MainCards",
    "type": "greed",
    "description": "Draw 4 additional main cards from your deck.",
    "suits": ["Hearts", "Spades"],  # Represents red and black suit groups
    "icon_img": "draw_four_main.png",
    "icon_gray_img": "draw_four_main.png",
    "frame_img": "blue.png",
    "frame_closed_img": "blue.png",
    "frame_hidden_img": "blue.png",
    "glow_img": "blue.png",
    "conquer_only": True,
    "spells": lambda family, suit: generate_same_color_spell_variants(
        family=family,
        color_group='red' if suit == 'Hearts' else 'black',
        ranks=['8', '8'],
        spell_name="Draw 4 MainCards",
        requires_target=False,
        counterable=False,
    ),
}


ALL_CONQUER_CONFIGS = [
    DRAW_4_MAIN_CARDS_CONFIG,
    COPY_FIGURE_CONFIG,
    ROYAL_DECREE_CONFIG,
    LANDSLIDE_CONFIG,
]
