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
  Each spell should have counterable=True for battle/tactics spells, False for others
"""

from game.components.spells.spell import Spell
from game.components.cards.card import Card
from config import settings


def create_draw_cards_spells(family, suit):
    """
    Example: Draw Cards spell - Direct effect, draws extra cards.
    
    This spell consists of:
    - 2 cards of the same rank (key cards)
    - Number card determines how many cards to draw
    """
    spells = []
    
    # Create variants with different card combinations
    # Example: Pair of 5s = draw 2 cards, pair of 10s = draw 2 cards, etc.
    for rank in ['5', '6', '7', '8', '9', '10']:
        # Two cards of same rank
        value = int(rank) if rank.isdigit() else 10
        key_card_1 = Card(rank, suit, value)
        key_card_2 = Card(rank, suit, value)  # In real implementation, need different suits
        
        spell = Spell(
            name=f"Draw Cards ({rank}s)",
            family=family,
            cards=[key_card_1, key_card_2],
            suit=suit,
            key_cards=[key_card_1, key_card_2],
            number_card=key_card_1,  # The rank determines power
            requires_target=False,
            counterable=False,  # greed spells are not counterable
        )
        spells.append(spell)
    
    return spells


def create_strengthen_figure_spells(family, suit):
    """
    Example: Strengthen Figure spell - Figure attachment effect.
    
    This spell:
    - Requires target figure
    - Stays active for number of rounds based on number_card
    - Consists of 3 cards: 2 key cards + 1 number card
    """
    spells = []
    
    # Map face cards to values (J=11, Q=12, K=13)
    rank_values = {'J': 11, 'Q': 12, 'K': 13}
    
    for key_rank in ['J', 'Q', 'K']:
        for number_rank in ['2', '3', '4', '5']:
            key_value = rank_values[key_rank]
            number_value = int(number_rank)
            
            key_card_1 = Card(key_rank, suit, key_value)
            key_card_2 = Card(key_rank, suit, key_value)
            number_card = Card(number_rank, suit, number_value)
            
            spell = Spell(
                name=f"Strengthen {key_rank} for {number_rank} rounds",
                family=family,
                cards=[key_card_1, key_card_2, number_card],
                suit=suit,
                key_cards=[key_card_1, key_card_2],
                number_card=number_card,
                requires_target=True,
                target_type='own_figure',
                counterable=False,  # enchantment spells are not counterable
            )
            spells.append(spell)
    
    return spells


def create_change_battle_spells(family, suit):
    """
    Example: Change Battle Type spell - Battle modification effect.
    
    This spell:
    - Changes the battle type for current round
    - Single card casts (simple spell)
    """
    spells = []
    
    # Map ranks to values (A=14 or 1, number cards use their numeric value)
    rank_values = {'A': 14, '2': 2, '3': 3}
    
    for rank in ['A', '2', '3']:
        value = rank_values[rank]
        card = Card(rank, suit, value)
        
        spell = Spell(
            name=f"Change Battle ({rank})",
            family=family,
            cards=[card],
            suit=suit,
            key_cards=[card],
            requires_target=False,
            counterable=True,  # tactics spells are counterable
        )
        spells.append(spell)
    
    return spells


# Example spell family configurations
DRAW_CARDS_CONFIG = {
    "name": "Draw Cards",
    "type": "greed",
    "description": "Draw 2 additional cards from your deck",
    "suits": ["Diamonds", "Hearts", "Clubs", "Spades"],
    "icon_img": "draw_two_main.png",
    "icon_gray_img": "draw_two_main.png",
    "frame_img": "passive.png",
    "frame_closed_img": "passive.png",
    "frame_hidden_img": "passive.png",
    "glow_img": "yellow.png",
    "build_position": (
        settings.CAST_SPELL_ICON_START_X + 0 * settings.SPELL_ICON_DELTA_X,
        settings.CAST_SPELL_ICON_START_Y
    ),
    "spells": lambda family, suit: [
        Spell(
            name=f"Draw Cards (8s)",
            family=family,
            cards=[Card('8', suit, 8)],
            suit=suit,
            key_cards=[Card('8', suit, 8)],
            requires_target=False,
            counterable=False,  # greed spells are not counterable
        )
    ],  
}

STRENGTHEN_FIGURE_CONFIG = {
    "name": "Strengthen Figure",
    "type": "enchantment",
    "description": "Attach to a figure to increase its power",
    "suits": ["Diamonds", "Hearts"],
    "icon_img": "strengthen.png",
    "icon_gray_img": "strengthen.png",
    "frame_img": "spell_frame.png",
    "frame_closed_img": "spell_frame.png",
    "frame_hidden_img": "spell_frame.png",
    "glow_img": "yellow.png",
    "build_position": (
        settings.CAST_SPELL_ICON_START_X + 1 * settings.SPELL_ICON_DELTA_X,
        settings.CAST_SPELL_ICON_START_Y
    ),
    "spells": create_strengthen_figure_spells,
}

CHANGE_BATTLE_CONFIG = {
    "name": "Change Battle",
    "type": "tactics",
    "description": "Change the type of battle for this round",
    "suits": ["Clubs", "Spades"],
    "icon_img": "change_battle.png",
    "icon_gray_img": "change_battle.png",
    "frame_img": "spell_frame.png",
    "frame_closed_img": "spell_frame.png",
    "frame_hidden_img": "spell_frame.png",
    "glow_img": "yellow.png",
    "build_position": (
        settings.CAST_SPELL_ICON_START_X + 2 * settings.SPELL_ICON_DELTA_X,
        settings.CAST_SPELL_ICON_START_Y
    ),
    "spells": create_change_battle_spells,
}


# Export list of all spell configurations
# Add your spell configs to this list
EXAMPLE_SPELL_CONFIGS = [
    DRAW_CARDS_CONFIG,
    # STRENGTHEN_FIGURE_CONFIG,
    # CHANGE_BATTLE_CONFIG,
]
