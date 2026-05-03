# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Data-driven AI defence generation configuration.

This module intentionally keeps AI land defence balancing out of
``server_settings.py``.  Rules here describe pools, ranges, and guarantees;
``ai/defence/generator.py`` turns them into concrete battle templates.
"""

AI_DEFENCE_GENERATOR_VERSION = 5

AI_DEFENCE_SUITS = ('Hearts', 'Diamonds', 'Clubs', 'Spades')
AI_DEFENCE_RED_SUITS = ('Hearts', 'Diamonds')
AI_DEFENCE_BLACK_SUITS = ('Clubs', 'Spades')

AI_DEFENCE_RANK_VALUES = {
    'A': 3,
    'K': 4,
    'Q': 2,
    'J': 1,
    '10': 10,
    '9': 9,
    '8': 8,
    '7': 7,
    '6': 6,
    '5': 5,
    '4': 4,
    '3': 3,
    '2': 2,
}

AI_DEFENCE_TIER_NAMES = {
    1: 'Border Watch',
    2: 'Mountain Warden',
    3: 'Suit Bastion',
    4: 'Apex Citadel',
}

# Figure keys are generated from role + suit-color and mapped to concrete
# family names. This catalog intentionally mirrors the active v2 runtime
# families from client family_configs + server ai.figure_recipes.
AI_DEFENCE_FIGURE_CATALOG = {
    'king': {
        'red': {
            'family_name': 'Djungle King',
            'name': 'Djungle King',
            'color': 'offensive',
            'field': 'castle',
            'produces': {'villager_red': 2, 'warrior_red': 1},
            'requires': {},
            'card_roles': ['key'],
            'key_cards': [{'rank': 'K', 'card_type': 'main'}],
        },
        'black': {
            'family_name': 'Himalaya King',
            'name': 'Himalaya King',
            'color': 'defensive',
            'field': 'castle',
            'produces': {'villager_black': 2, 'warrior_black': 1},
            'requires': {},
            'card_roles': ['key'],
            'key_cards': [{'rank': 'K', 'card_type': 'main'}],
        },
    },
    'maharaja': {
        'red': {
            'family_name': 'Djungle Maharaja',
            'name': 'Djungle Maharaja',
            'color': 'offensive',
            'field': 'castle',
            'produces': {'villager_red': 3, 'warrior_red': 2},
            'requires': {},
            'card_roles': ['key'],
            'key_cards': [{'rank': 'K', 'card_type': 'main'}],
            'checkmate': True,
        },
        'black': {
            'family_name': 'Himalaya Maharaja',
            'name': 'Himalaya Maharaja',
            'color': 'defensive',
            'field': 'castle',
            'produces': {'villager_black': 3, 'warrior_black': 2},
            'requires': {},
            'card_roles': ['key'],
            'key_cards': [{'rank': 'K', 'card_type': 'main'}],
            'checkmate': True,
        },
    },
    'farm_small': {
        'red': {
            'family_name': 'Small Rice Farm',
            'name': 'Small Rice Farm',
            'color': 'offensive',
            'field': 'village',
            'produces': {},
            'number_produces': {'food_red': 1},
            'requires': {'villager_red': 1},
            'card_roles': ['key', 'number'],
            'key_cards': [{'rank': 'J', 'card_type': 'main'}],
        },
        'black': {
            'family_name': 'Small Yack Farm',
            'name': 'Small Yack Farm',
            'color': 'defensive',
            'field': 'village',
            'produces': {},
            'number_produces': {'food_black': 1},
            'requires': {'villager_black': 1},
            'card_roles': ['key', 'number'],
            'key_cards': [{'rank': 'J', 'card_type': 'main'}],
        },
    },
    'farm_large': {
        'red': {
            'family_name': 'Large Rice Farm',
            'name': 'Large Rice Farm',
            'color': 'offensive',
            'field': 'village',
            'produces': {},
            'number_produces': {'food_red': 2},
            'requires': {'villager_red': 1},
            'card_roles': ['key', 'key', 'number'],
            'key_cards': [
                {'rank': 'J', 'card_type': 'main'},
                {'rank': 'Q', 'card_type': 'main'},
            ],
            'number_card_type': 'main',
        },
        'black': {
            'family_name': 'Large Yack Farm',
            'name': 'Large Yack Farm',
            'color': 'defensive',
            'field': 'village',
            'produces': {},
            'number_produces': {'food_black': 2},
            'requires': {'villager_black': 1},
            'card_roles': ['key', 'key', 'number'],
            'key_cards': [
                {'rank': 'J', 'card_type': 'main'},
                {'rank': 'Q', 'card_type': 'main'},
            ],
            'number_card_type': 'main',
        },
    },
    'temple': {
        'red': {
            'family_name': 'Djungle Temple',
            'name': 'Djungle Temple',
            'color': 'offensive',
            'field': 'village',
            'produces': {},
            'requires': {'villager_red': 1},
            'card_roles': ['key', 'key'],
            'key_cards': [
                {'rank': 'Q', 'card_type': 'main'},
                {'rank': 'Q', 'card_type': 'main'},
            ],
        },
        'black': {
            'family_name': 'Himalaya Temple',
            'name': 'Himalaya Temple',
            'color': 'defensive',
            'field': 'village',
            'produces': {},
            'requires': {'villager_black': 1},
            'card_roles': ['key', 'key'],
            'key_cards': [
                {'rank': 'Q', 'card_type': 'main'},
                {'rank': 'Q', 'card_type': 'main'},
            ],
        },
    },
    'manufactory': {
        'red': {
            'family_name': 'Sword Manufactory',
            'name': 'Sword Manufactory',
            'color': 'offensive',
            'field': 'village',
            'produces': {'armor_red': 7},
            'requires': {'villager_red': 1},
            'card_roles': ['key', 'key', 'number'],
            'key_cards': [
                {'rank': 'Q', 'card_type': 'main'},
                {'rank': 'Q', 'card_type': 'main'},
            ],
            'number_card_type': 'main',
            'number_rank_options': ['7'],
        },
        'black': {
            'family_name': 'Shield Manufactory',
            'name': 'Shield Manufactory',
            'color': 'defensive',
            'field': 'village',
            'produces': {'armor_black': 7},
            'requires': {'villager_black': 1},
            'card_roles': ['key', 'key', 'number'],
            'key_cards': [
                {'rank': 'Q', 'card_type': 'main'},
                {'rank': 'Q', 'card_type': 'main'},
            ],
            'number_card_type': 'main',
            'number_rank_options': ['7'],
        },
    },
    'healer': {
        'red': {
            'family_name': 'Djungle Healer',
            'name': 'Djungle Healer',
            'color': 'offensive',
            'field': 'village',
            'produces': {},
            'requires': {'villager_red': 1},
            'card_roles': ['key', 'key'],
            'key_cards': [
                {'rank': '2', 'card_type': 'side'},
                {'rank': '2', 'card_type': 'side'},
            ],
        },
        'black': {
            'family_name': 'Himalaya Healer',
            'name': 'Himalaya Healer',
            'color': 'defensive',
            'field': 'village',
            'produces': {},
            'requires': {'villager_black': 1},
            'card_roles': ['key', 'key'],
            'key_cards': [
                {'rank': '2', 'card_type': 'side'},
                {'rank': '2', 'card_type': 'side'},
            ],
        },
    },
    'material': {
        'red': {
            'family_name': 'Carpenter',
            'name': 'Carpenter',
            'color': 'offensive',
            'field': 'village',
            'produces': {},
            'number_produces': {'material_red': 1},
            'requires': {'villager_red': 1},
            'card_roles': ['key', 'number'],
            'key_cards': [{'rank': '2', 'card_type': 'side'}],
            'number_card_type': 'side',
            'number_rank_options': ['3', '6'],
        },
        'black': {
            'family_name': 'Stone Mason',
            'name': 'Stone Mason',
            'color': 'defensive',
            'field': 'village',
            'produces': {},
            'number_produces': {'material_black': 1},
            'requires': {'villager_black': 1},
            'card_roles': ['key', 'number'],
            'key_cards': [{'rank': '2', 'card_type': 'side'}],
            'number_card_type': 'side',
            'number_rank_options': ['3', '6'],
        },
    },
    'military_basic': {
        'red': {
            'family_name': 'Gorkha Warriors',
            'name': 'Gorkha Warriors',
            'color': 'offensive',
            'field': 'military',
            'produces': {},
            'requires': {'warrior_red': 1},
            'number_requires': {'food_red': 1},
            'card_roles': ['key', 'number'],
            'key_cards': [{'rank': 'A', 'card_type': 'main'}],
        },
        'black': {
            'family_name': 'Wooden Fortress',
            'name': 'Wooden Fortress',
            'color': 'defensive',
            'field': 'military',
            'produces': {},
            'requires': {'warrior_black': 1},
            'number_requires': {'food_black': 1},
            'card_roles': ['key', 'number'],
            'key_cards': [{'rank': 'A', 'card_type': 'main'}],
        },
    },
    'military_elite': {
        'red': {
            'family_name': 'Elite Gorkha Warriors',
            'name': 'Elite Gorkha Warriors',
            'color': 'offensive',
            'field': 'military',
            'produces': {},
            'requires': {'warrior_red': 1, 'armor_red': 7},
            'number_requires': {'food_red': 1},
            'card_roles': ['key', 'key', 'number'],
            'key_cards': [
                {'rank': 'A', 'card_type': 'main'},
                {'rank': '7', 'card_type': 'main'},
            ],
            'number_card_type': 'main',
        },
        'black': {
            'family_name': 'Stone Fortress',
            'name': 'Stone Fortress',
            'color': 'defensive',
            'field': 'military',
            'produces': {},
            'requires': {'warrior_black': 1, 'armor_black': 7},
            'number_requires': {'food_black': 1},
            'card_roles': ['key', 'key', 'number'],
            'key_cards': [
                {'rank': 'A', 'card_type': 'main'},
                {'rank': '7', 'card_type': 'main'},
            ],
            'number_card_type': 'main',
        },
    },
    'wall_cavalry': {
        'red': {
            'family_name': 'Cavalry',
            'name': 'Cavalry',
            'color': 'offensive',
            'field': 'military',
            'produces': {},
            'requires': {'warrior_red': 1},
            'number_requires': {'material_red': 1},
            'card_roles': ['key', 'key', 'number'],
            'key_cards': [
                {'rank': '4', 'card_type': 'side'},
                {'rank': '5', 'card_type': 'side'},
            ],
            'number_card_type': 'side',
            'number_rank_options': ['3', '6'],
            'cannot_be_blocked': True,
            'rest_after_attack': True,
        },
        'black': {
            'family_name': 'Wall',
            'name': 'Wall',
            'color': 'defensive',
            'field': 'military',
            'produces': {},
            'requires': {'warrior_black': 1},
            'number_requires': {'material_black': 1},
            'card_roles': ['key', 'key', 'number'],
            'key_cards': [
                {'rank': '4', 'card_type': 'side'},
                {'rank': '5', 'card_type': 'side'},
            ],
            'number_card_type': 'side',
            'number_rank_options': ['3', '6'],
        },
    },
    'archer': {
        'red': {
            'family_name': 'Djungle Archer',
            'name': 'Djungle Archer',
            'color': 'offensive',
            'field': 'military',
            'produces': {},
            'requires': {'warrior_red': 1},
            'number_requires': {'material_red': 1},
            'card_roles': ['key', 'number'],
            'key_cards': [{'rank': '4', 'card_type': 'side'}],
            'number_card_type': 'side',
            'number_rank_options': ['3', '6'],
        },
        'black': {
            'family_name': 'Himalya Archer',
            'name': 'Himalya Archer',
            'color': 'defensive',
            'field': 'military',
            'produces': {},
            'requires': {'warrior_black': 1},
            'number_requires': {'material_black': 1},
            'card_roles': ['key', 'number'],
            'key_cards': [{'rank': '4', 'card_type': 'side'}],
            'number_card_type': 'side',
            'number_rank_options': ['3', '6'],
        },
    },
}

# ---------------------------------------------------------------------------
# Tier generation rules (main tuning surface)
# ---------------------------------------------------------------------------
# Each tier entry controls how ``generator.generate_ai_defence_template_for_land``
# builds the final defence.  Key semantics:
#
# ``core_roles``
#   Guaranteed figures. One figure is created for each role listed here.
#   All core figures use the land's primary suit color unless suit fallback is
#   needed (for neutral/invalid suit inputs).
#
# ``optional_count_range``
#   Inclusive range ``(min, max)`` for extra figures after core_roles.
#   Larger values increase board complexity and the chance to include multiple
#   role synergies.
#
# ``optional_role_weights``
#   Weighted role pool for each optional slot, e.g. ``('warrior', 4)`` means
#   warrior is 4x as likely as a role with weight 1.  Roles must exist in
#   ``AI_DEFENCE_FIGURE_CATALOG``.
#
# ``number_ranks``
#   Default rank pool for number-card roles that do not define
#   ``number_rank_options`` at role level.
#
# ``battle_plan``
#   Selects deterministic move script template:
#   - ``border``: only dagger moves (lowest tactical complexity).
#   - ``sentinel``: ``Call King`` + ``Call Villager`` + high dagger.
#   - ``warden``: prefers ``Call King`` then daggers (requires castle field,
#     otherwise falls back to border pattern).
#   - ``bastion``: prefers ``Call Military`` then daggers (requires military
#     field, otherwise falls back to border pattern).
#   - ``apex``: ``Call King`` + ``Call Military`` + dagger (requires both
#     castle and military fields, otherwise falls back).
#   - ``overlord``: ``Block`` + ``Call Military`` + ``Call King``
#     (high denial + high burst).
#
# ``auto_gamble``
#   Enables conquer AI auto-gamble behavior for this tier.
#
# ``auto_gamble_threshold``
#   Effective-value floor used by the conquer AI: moves below threshold are
#   candidates for gambling. Runtime clamps to [1, 20].

# ``prelude_spell_weights`` / ``counter_spell_weights``
#   Weighted pools of scripted AI spells.  The seeded RNG picks one entry per
#   template, so each AI land draws an independent prelude / counter spell.
#   Use the literal value ``None`` (or ``'None'``) in a pool to give the
#   template a chance to roll "no spell" — this mirrors player defence
#   configs, where:
#     * Prelude is fully optional.
#     * Counter is optional too because AI templates always set
#       ``battle_figure_index`` (the counter-advance figure).
#   Available preludes: ``Dump Cards``, ``Forced Deal``, ``Poison``,
#   ``Health Boost``, ``Explosion``, ``Peasant War``, ``Civil War``.
#   Available counters: ``Dump Cards``, ``Forced Deal``, ``Poison``,
#   ``Health Boost``.
#   Targeted spells (``Poison``, ``Explosion``, ``Health Boost``) auto-resolve
#   their target at battle start (defender heuristic) so no extra data is
#   required in the template.  Battle-modifier preludes (``Peasant War``,
#   ``Civil War``) append to ``game.battle_modifier`` like player-cast spells.

# ``core_cross_color_chance`` / ``optional_suit_weights``
#   Controls suit-color variety. Core roles keep the first figure as a land-suit
#   anchor, then can occasionally use opposite-color variants. Optional figures
#   choose between primary suit, same-color alternate suit and opposite color.
#
# ``black_land_fortress_free_chance``
#   Chance that a black-suit land converts all generated Wooden/Stone Fortress
#   role picks to the red Gorkha equivalent instead.  This keeps fortress maps
#   common but no longer guaranteed on black lands.
#
# Practical tuning guidance:
# - If you increase expensive military/support frequencies, keep supporting
#   food/villager/material/armor production reachable so the repair loop does
#   not add too many emergency providers.
# - Tier >= 3 optional figures can include same-color alternate suits, so keep
#   battle plans compatible with mixed-suit lineups.
# - Keep ``number_ranks`` non-empty for every tier.
AI_DEFENCE_GENERATION_RULES = {
    # Tier 1: still beatable, but already "real" defence pressure.
    1: {
        'core_roles': ['king', 'farm_small', 'military_basic'],
        'optional_count_range': (0, 1),
        'optional_role_weights': [
            ('farm_small', 2),
            ('healer', 2),
            ('material', 1),
            ('archer', 1),
            ('military_basic', 2),
        ],
        'number_ranks': ['7', '8', '9'],
        'battle_plan': 'sentinel',
        'core_cross_color_chance': 0.38,
        'optional_suit_weights': {'primary': 6, 'same_color': 1, 'opposite_color': 3},
        'black_land_fortress_free_chance': 0.45,
        # T1: utility-leaning, with a real chance of "no spell".
        'prelude_spell_weights': [
            (None, 6),
            ('Dump Cards', 4),
            ('Forced Deal', 3),
            ('Poison', 2),
            ('Health Boost', 2),
            ('Peasant War', 2),
            ('Civil War', 1),
            ('Explosion', 1),
        ],
        'prelude_spell_data': {},
        'counter_spell_weights': [
            (None, 5),
            ('Dump Cards', 5),
            ('Forced Deal', 4),
            ('Poison', 3),
            ('Health Boost', 3),
        ],
        'counter_spell_data': {},
        'auto_gamble': True,
        'auto_gamble_threshold': 10,
    },
    # Tier 2: full call-based pressure with stronger support synergies.
    2: {
        'core_roles': ['king', 'farm_large', 'military_basic', 'healer', 'material'],
        'optional_count_range': (0, 3),
        'optional_role_weights': [
            ('temple', 2),
            ('archer', 2),
            ('manufactory', 2),
            ('military_elite', 1),
            ('wall_cavalry', 1),
            ('farm_large', 1),
        ],
        'number_ranks': ['9', '10'],
        'battle_plan': 'apex',
        'core_cross_color_chance': 0.32,
        'optional_suit_weights': {'primary': 5, 'same_color': 2, 'opposite_color': 3},
        'black_land_fortress_free_chance': 0.25,
        # T2: full pool, lower "no spell" chance.
        'prelude_spell_weights': [
            (None, 2),
            ('Dump Cards', 3),
            ('Forced Deal', 3),
            ('Poison', 4),
            ('Health Boost', 4),
            ('Peasant War', 3),
            ('Civil War', 3),
            ('Explosion', 2),
        ],
        'prelude_spell_data': {},
        'counter_spell_weights': [
            (None, 2),
            ('Dump Cards', 3),
            ('Forced Deal', 4),
            ('Poison', 5),
            ('Health Boost', 5),
        ],
        'counter_spell_data': {},
        'auto_gamble': True,
        'auto_gamble_threshold': 8,
    },
    # Tier 3: high-pressure fortress/elite economy with stacked support.
    3: {
        'core_roles': ['maharaja', 'farm_large', 'military_elite', 'manufactory', 'healer', 'material'],
        'optional_count_range': (3, 4),
        'optional_role_weights': [
            ('archer', 3),
            ('wall_cavalry', 3),
            ('temple', 2),
            ('military_elite', 2),
            ('farm_large', 1),
            ('maharaja', 1),
        ],
        'number_ranks': ['10'],
        'battle_plan': 'apex',
        'core_cross_color_chance': 0.28,
        'optional_suit_weights': {'primary': 5, 'same_color': 2, 'opposite_color': 3},
        'black_land_fortress_free_chance': 0.15,
        # T3: heavy pressure, small "no spell" chance for variety.
        'prelude_spell_weights': [
            (None, 1),
            ('Dump Cards', 2),
            ('Forced Deal', 2),
            ('Poison', 4),
            ('Health Boost', 4),
            ('Peasant War', 4),
            ('Civil War', 4),
            ('Explosion', 4),
        ],
        'prelude_spell_data': {},
        'counter_spell_weights': [
            (None, 1),
            ('Dump Cards', 2),
            ('Forced Deal', 4),
            ('Poison', 6),
            ('Health Boost', 6),
        ],
        'counter_spell_data': {},
        'auto_gamble': True,
        'auto_gamble_threshold': 7,
    },
    # Tier 4: almost unbeatable stack (deny + burst + high synergies).
    4: {
        'core_roles': [
            'maharaja',
            'farm_large',
            'military_elite',
            'wall_cavalry',
            'archer',
            'manufactory',
            'healer',
            'temple',
            'material',
        ],
        'optional_count_range': (4, 6),
        'optional_role_weights': [
            ('military_elite', 4),
            ('wall_cavalry', 4),
            ('archer', 4),
            ('manufactory', 3),
            ('healer', 3),
            ('temple', 3),
            ('farm_large', 2),
            ('material', 2),
            ('maharaja', 1),
            ('king', 1),
        ],
        'number_ranks': ['10'],
        'battle_plan': 'overlord',
        'core_cross_color_chance': 0.25,
        'optional_suit_weights': {'primary': 6, 'same_color': 2, 'opposite_color': 2},
        'black_land_fortress_free_chance': 0.08,
        # T4: always casts; weighted toward devastating choices.
        'prelude_spell_weights': [
            ('Dump Cards', 2),
            ('Forced Deal', 2),
            ('Poison', 4),
            ('Health Boost', 4),
            ('Peasant War', 4),
            ('Civil War', 4),
            ('Explosion', 5),
        ],
        'prelude_spell_data': {},
        'counter_spell_weights': [
            ('Dump Cards', 1),
            ('Forced Deal', 3),
            ('Poison', 6),
            ('Health Boost', 6),
        ],
        'counter_spell_data': {},
        'auto_gamble': True,
        'auto_gamble_threshold': 6,
    },
}

# Resource-deficit repair map.
# If generated figures require a resource that total production cannot satisfy,
# generator.py adds providers based on this mapping until the template is
# self-sufficient (or retry budget is exhausted).
AI_DEFENCE_RESOURCE_PROVIDERS = {
    'villager_red': ('king', 'red'),
    'warrior_red': ('king', 'red'),
    'food_red': ('farm_large', 'red'),
    'material_red': ('material', 'red'),
    'armor_red': ('manufactory', 'red'),
    'villager_black': ('king', 'black'),
    'warrior_black': ('king', 'black'),
    'food_black': ('farm_large', 'black'),
    'material_black': ('material', 'black'),
    'armor_black': ('manufactory', 'black'),
}

# Safe fallback templates are used when generation or validation fails.
# Keep these conservative and fully self-contained; they are the last line of
# defence against runtime template corruption.
AI_DEFENCE_SAFE_FALLBACKS = {
    1: {
        'ai_name': 'Fallback Border Watch',
        'figures': [
            {'family_name': 'Djungle King', 'name': 'Djungle King',
             'suit': 'Hearts', 'color': 'offensive', 'field': 'castle',
             'produces': {'villager_red': 2, 'warrior_red': 1}, 'requires': {},
             'card_ids': [], 'card_roles': ['key'],
             'cards': [{'rank': 'K', 'suit': 'Hearts', 'role': 'key'}]},
            {'family_name': 'Small Rice Farm', 'name': 'Small Rice Farm',
             'suit': 'Hearts', 'color': 'offensive', 'field': 'village',
             'produces': {'food_red': 10}, 'requires': {'villager_red': 1},
             'card_ids': [], 'card_roles': ['key', 'number'],
             'cards': [{'rank': 'J', 'suit': 'Hearts', 'role': 'key'},
                       {'rank': '7', 'suit': 'Hearts', 'role': 'number'}]},
        ],
        'battle_moves': [
            {'family_name': 'Dagger', 'rank': '7', 'suit': 'Hearts',
             'value': 7, 'round_index': 0, 'card_type': 'main'},
            {'family_name': 'Dagger', 'rank': '8', 'suit': 'Diamonds',
             'value': 8, 'round_index': 1, 'card_type': 'main'},
            {'family_name': 'Dagger', 'rank': '7', 'suit': 'Hearts',
             'value': 7, 'round_index': 2, 'card_type': 'main'},
        ],
        'battle_figure_index': 1,
        'battle_modifier': None,
        'spell': None,
        'prelude_spell_name': None,
        'prelude_spell_data': None,
        'counter_spell_name': None,
        'counter_spell_data': None,
        'auto_gamble': False,
        'auto_gamble_threshold': 10,
    },
}
