# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""
Figure building recipes for the AI.

Server-side definition of what cards are needed to build each figure type.
This mirrors the client-side family_configs but in a data-only format
usable by the AI action enumerator.
"""

# Suit groupings
SUITS_BLACK = ['Clubs', 'Spades']
SUITS_RED = ['Hearts', 'Diamonds']
NUMBER_CARDS = ['7', '8', '9', '10']
SIDE_NUMBER_CARDS = ['3', '6']  # Used for Wall, Cavalry, Archers

# Each recipe: {
#   'name': display name,
#   'family_name': family identifier,
#   'field': 'castle'|'village'|'military',
#   'color': 'offensive'|'defensive',
#   'suits': list of valid suits,
#   'key_ranks': list of (rank, card_type) tuples needed as key cards,
#   'needs_number_card': True if needs a 7-10 number card of same suit,
#   'number_card_options': list of valid number ranks (default ['7','8','9','10']),
#   'upgrade_family_name': name of upgrade target (or None),
#   'produces_template': dict template (use {number} for number card value),
#   'requires': static resource requirements,
#   'instant_charge': bool,
#   'cannot_be_blocked': bool,
#   'rest_after_attack': bool,
#   'special_flags': dict of additional flags,
# }

FIGURE_RECIPES = [
    # ── CASTLE ──
    {
        'name': 'Himalaya King',
        'family_name': 'Himalaya King',
        'field': 'castle',
        'color': 'defensive',
        'suits': SUITS_BLACK,
        'key_ranks': [('K', 'main')],
        'needs_number_card': False,
        'produces_fn': lambda suit, num: {'villager_black': 2, 'warrior_black': 1},
        'requires': {},
    },
    {
        'name': 'Djungle King',
        'family_name': 'Djungle King',
        'field': 'castle',
        'color': 'offensive',
        'suits': SUITS_RED,
        'key_ranks': [('K', 'main')],
        'needs_number_card': False,
        'produces_fn': lambda suit, num: {'villager_red': 2, 'warrior_red': 1},
        'requires': {},
    },
    {
        'name': 'Himalaya Maharaja',
        'family_name': 'Himalaya Maharaja',
        'field': 'castle',
        'color': 'defensive',
        'suits': SUITS_BLACK,
        'key_ranks': [('MK', 'main')],
        'needs_number_card': False,
        'produces_fn': lambda suit, num: {'villager_black': 3, 'warrior_black': 2},
        'requires': {},
        'special_flags': {'checkmate': True},
    },
    {
        'name': 'Djungle Maharaja',
        'family_name': 'Djungle Maharaja',
        'field': 'castle',
        'color': 'offensive',
        'suits': SUITS_RED,
        'key_ranks': [('MK', 'main')],
        'needs_number_card': False,
        'produces_fn': lambda suit, num: {'villager_red': 3, 'warrior_red': 2},
        'requires': {},
        'special_flags': {'checkmate': True},
    },

    # ── VILLAGE — Farms ──
    {
        'name': 'Small Yack Farm',
        'family_name': 'Small Yack Farm',
        'field': 'village',
        'color': 'defensive',
        'suits': SUITS_BLACK,
        'key_ranks': [('J', 'main')],
        'needs_number_card': True,
        'number_card_options': NUMBER_CARDS,
        'upgrade_family_name': 'Large Yack Farm',
        'produces_fn': lambda suit, num: {'food_black': num} if suit in SUITS_BLACK else {'food_red': num},
        'requires': {'villager_black': 1},
    },
    {
        'name': 'Small Rice Farm',
        'family_name': 'Small Rice Farm',
        'field': 'village',
        'color': 'offensive',
        'suits': SUITS_RED,
        'key_ranks': [('J', 'main')],
        'needs_number_card': True,
        'number_card_options': NUMBER_CARDS,
        'upgrade_family_name': 'Large Rice Farm',
        'produces_fn': lambda suit, num: {'food_red': num} if suit in SUITS_RED else {'food_black': num},
        'requires': {'villager_red': 1},
    },

    # ── VILLAGE — Temples ──
    {
        'name': 'Himalaya Temple',
        'family_name': 'Himalaya Temple',
        'field': 'village',
        'color': 'defensive',
        'suits': SUITS_BLACK,
        'key_ranks': [('Q', 'main'), ('Q', 'main')],  # Needs 2 Queens
        'needs_number_card': False,
        'upgrade_family_name': 'Shield Manufactory',
        'produces_fn': lambda suit, num: {},
        'requires': {'villager_black': 1},
        'special_flags': {'cannot_attack': True, 'blocks_bonus': True},
    },
    {
        'name': 'Djungle Temple',
        'family_name': 'Djungle Temple',
        'field': 'village',
        'color': 'offensive',
        'suits': SUITS_RED,
        'key_ranks': [('Q', 'main'), ('Q', 'main')],
        'needs_number_card': False,
        'upgrade_family_name': 'Sword Manufactory',
        'produces_fn': lambda suit, num: {},
        'requires': {'villager_red': 1},
        'special_flags': {'cannot_attack': True, 'blocks_bonus': True},
    },

    # ── VILLAGE — Healers ──
    {
        'name': 'Himalaya Healer',
        'family_name': 'Himalaya Healer',
        'field': 'village',
        'color': 'defensive',
        'suits': SUITS_BLACK,
        'key_ranks': [('2', 'side'), ('2', 'side')],  # Needs 2 side-card 2s
        'needs_number_card': False,
        'upgrade_family_name': 'Stone Mason',
        'produces_fn': lambda suit, num: {},
        'requires': {'villager_black': 1},
        'special_flags': {'cannot_attack': True, 'buffs_allies': True},
    },
    {
        'name': 'Djungle Healer',
        'family_name': 'Djungle Healer',
        'field': 'village',
        'color': 'offensive',
        'suits': SUITS_RED,
        'key_ranks': [('2', 'side'), ('2', 'side')],
        'needs_number_card': False,
        'upgrade_family_name': 'Carpenter',
        'produces_fn': lambda suit, num: {},
        'requires': {'villager_red': 1},
        'special_flags': {'cannot_attack': True, 'buffs_allies': True},
    },

    # ── VILLAGE — Material Producers ──
    {
        'name': 'Carpenter',
        'family_name': 'Carpenter',
        'field': 'village',
        'color': 'offensive',
        'suits': SUITS_RED,
        'key_ranks': [('2', 'side')],
        'needs_number_card': True,
        'number_card_options': SIDE_NUMBER_CARDS,
        'number_card_type': 'side',
        'produces_fn': lambda suit, num: {'material_red': num} if suit in SUITS_RED else {'material_black': num},
        'requires': {'villager_red': 1},
    },
    {
        'name': 'Stone Mason',
        'family_name': 'Stone Mason',
        'field': 'village',
        'color': 'defensive',
        'suits': SUITS_BLACK,
        'key_ranks': [('2', 'side')],
        'needs_number_card': True,
        'number_card_options': SIDE_NUMBER_CARDS,
        'number_card_type': 'side',
        'produces_fn': lambda suit, num: {'material_black': num} if suit in SUITS_BLACK else {'material_red': num},
        'requires': {'villager_black': 1},
    },

    # ── MILITARY — Fortress ──
    {
        'name': 'Wooden Fortress',
        'family_name': 'Wooden Fortress',
        'field': 'military',
        'color': 'defensive',
        'suits': SUITS_BLACK,
        'key_ranks': [('A', 'main')],
        'needs_number_card': True,
        'number_card_options': NUMBER_CARDS,
        'upgrade_family_name': 'Stone Fortress',
        'produces_fn': lambda suit, num: {},
        'requires_fn': lambda suit, num: {'warrior_black': 1, 'food_black': num},
        'special_flags': {'cannot_attack': True, 'must_be_attacked': True},
    },

    # ── MILITARY — Warriors ──
    {
        'name': 'Gorkha Warriors',
        'family_name': 'Gorkha Warriors',
        'field': 'military',
        'color': 'offensive',
        'suits': SUITS_RED,
        'key_ranks': [('A', 'main')],
        'needs_number_card': True,
        'number_card_options': NUMBER_CARDS,
        'upgrade_family_name': 'Elite Gorkha Warriors',
        'produces_fn': lambda suit, num: {},
        'requires_fn': lambda suit, num: {'warrior_red': 1, 'food_red': num},
        'special_flags': {'instant_charge': True},
    },

    # ── MILITARY — Wall ──
    {
        'name': 'Wall',
        'family_name': 'Wall',
        'field': 'military',
        'color': 'defensive',
        'suits': SUITS_BLACK,
        'key_ranks': [('4', 'side'), ('5', 'side')],
        'needs_number_card': True,
        'number_card_options': SIDE_NUMBER_CARDS,
        'number_card_type': 'side',
        'produces_fn': lambda suit, num: {},
        'requires_fn': lambda suit, num: {'warrior_black': 1, 'material_black': num},
        'special_flags': {'cannot_attack': True, 'cannot_defend': True, 'buffs_allies_defence': True, 'cannot_be_targeted': True},
    },

    # ── MILITARY — Cavalry ──
    {
        'name': 'Cavalry',
        'family_name': 'Cavalry',
        'field': 'military',
        'color': 'offensive',
        'suits': SUITS_RED,
        'key_ranks': [('4', 'side'), ('5', 'side')],
        'needs_number_card': True,
        'number_card_options': SIDE_NUMBER_CARDS,
        'number_card_type': 'side',
        'produces_fn': lambda suit, num: {},
        'requires_fn': lambda suit, num: {'warrior_red': 1, 'material_red': num},
        'special_flags': {'instant_charge': True, 'cannot_be_blocked': True, 'rest_after_attack': True, 'cannot_defend': True},
    },

    # ── MILITARY — Archers ──
    {
        'name': 'Himalya Archer',
        'family_name': 'Himalya Archer',
        'field': 'military',
        'color': 'defensive',
        'suits': SUITS_BLACK,
        'key_ranks': [('4', 'side')],
        'needs_number_card': True,
        'number_card_options': SIDE_NUMBER_CARDS,
        'number_card_type': 'side',
        'produces_fn': lambda suit, num: {},
        'requires_fn': lambda suit, num: {'warrior_black': 1, 'material_black': num},
        'special_flags': {'distance_attack': True},
    },
    {
        'name': 'Djungle Archer',
        'family_name': 'Djungle Archer',
        'field': 'military',
        'color': 'offensive',
        'suits': SUITS_RED,
        'key_ranks': [('4', 'side')],
        'needs_number_card': True,
        'number_card_options': SIDE_NUMBER_CARDS,
        'number_card_type': 'side',
        'produces_fn': lambda suit, num: {},
        'requires_fn': lambda suit, num: {'warrior_red': 1, 'material_red': num},
        'special_flags': {'distance_attack': True},
    },
]

# ── Complete family_name → skill flags lookup ──
# Includes upgrade families not present in FIGURE_RECIPES.
# Auto-populated from recipes + manual upgrade entries.
FAMILY_SKILLS = {r['family_name']: dict(r.get('special_flags', {})) for r in FIGURE_RECIPES}
FAMILY_SKILLS.update({
    # Upgrade families (inherit parent skills)
    'Stone Fortress':        {'cannot_attack': True, 'must_be_attacked': True},
    'Elite Gorkha Warriors': {'instant_charge': True},
    'Shield Manufactory':    {'cannot_attack': True},
    'Sword Manufactory':     {'cannot_attack': True},
    # Castle upgrades
    'Himalaya Maharaja':     {'checkmate': True},
    'Djungle Maharaja':      {'checkmate': True},
    # Farms / material producers (no special flags, but ensure key exists)
    'Large Yack Farm':       {},
    'Large Rice Farm':       {},
})


def find_buildable_figures(main_hand, side_hand, existing_figures):
    """
    Given the AI's hand cards and existing figures, determine which figures can be built.
    
    Returns a list of dicts, each describing a buildable figure option:
    {
        'recipe': the recipe dict,
        'suit': the suit to use,
        'key_cards': list of card dicts (with id, type, role),
        'number_card': card dict or None,
        'name': full figure name,
        'produces': resource production dict,
        'requires': resource requirement dict,
    }
    """
    # Index available cards (not part of a figure or battle move)
    available_main = [c for c in main_hand if not c.get('part_of_figure') and not c.get('part_of_battle_move')]
    available_side = [c for c in side_hand if not c.get('part_of_figure') and not c.get('part_of_battle_move')]
    
    # Track existing figure family names to avoid duplicates where appropriate
    existing_names = {f.get('family_name') or f.get('name') for f in existing_figures}
    
    buildable = []
    
    for recipe in FIGURE_RECIPES:
        for suit in recipe['suits']:
            # Find matching key cards
            key_cards_needed = list(recipe['key_ranks'])  # copy
            matched_keys = []
            used_card_ids = set()
            
            success = True
            for rank, card_type in key_cards_needed:
                pool = available_main if card_type == 'main' else available_side
                found = None
                for c in pool:
                    if (c['id'] not in used_card_ids and 
                        c['rank'] == rank and 
                        c['suit'] == suit):
                        found = c
                        break
                if found:
                    matched_keys.append({
                        'id': found['id'],
                        'type': card_type,
                        'role': 'key',
                    })
                    used_card_ids.add(found['id'])
                else:
                    success = False
                    break
            
            if not success:
                continue
            
            # Find number card if needed
            if recipe.get('needs_number_card'):
                num_type = recipe.get('number_card_type', 'main')
                num_options = recipe.get('number_card_options', NUMBER_CARDS)
                pool = available_main if num_type == 'main' else available_side
                
                # Try each number option, prefer higher values
                for num_rank in sorted(num_options, key=lambda r: -int(r)):
                    num_card = None
                    for c in pool:
                        if (c['id'] not in used_card_ids and
                            c['rank'] == num_rank and
                            c['suit'] == suit):
                            num_card = c
                            break
                    if num_card:
                        num_value = int(num_rank)
                        produces = recipe['produces_fn'](suit, num_value)
                        
                        if 'requires_fn' in recipe:
                            requires = recipe['requires_fn'](suit, num_value)
                        else:
                            requires = dict(recipe.get('requires', {}))
                        
                        cards_list = matched_keys + [{
                            'id': num_card['id'],
                            'type': num_type,
                            'role': 'number',
                        }]
                        
                        fig_name = f"{recipe['name']}"
                        buildable.append({
                            'recipe': recipe,
                            'suit': suit,
                            'key_cards': list(matched_keys),
                            'number_card': num_card,
                            'number_value': num_value,
                            'cards': cards_list,
                            'name': fig_name,
                            'display_name': f"{fig_name} ({suit} {num_rank})",
                            'produces': produces,
                            'requires': requires,
                        })
                        break  # Only the best (highest) number card per suit
            else:
                # No number card needed
                produces = recipe['produces_fn'](suit, 0)
                requires = dict(recipe.get('requires', {}))
                
                fig_name = f"{recipe['name']}"
                buildable.append({
                    'recipe': recipe,
                    'suit': suit,
                    'key_cards': list(matched_keys),
                    'number_card': None,
                    'number_value': 0,
                    'cards': matched_keys,
                    'name': fig_name,
                    'display_name': f"{fig_name} ({suit})",
                    'produces': produces,
                    'requires': requires,
                })
    
    return buildable
