# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
# ── Figure Skill Definitions ──────────────────────────────────
# Single source of truth for every figure skill in the game.
# Each entry maps a skill key → dict with display name, description,
# and icon path.  All UI/logic code should reference SKILL_DEFINITIONS
# instead of hard-coding skill names, labels, or icon paths.
#
# suit_advantage (bool):
#   When True the skill only affects the opponent figure whose suit
#   the owner has an advantage over.  The UI will display the
#   affected suit icon next to the skill icon.
#
# suit_self (bool):
#   When True the UI will display the figure's OWN suit icon in the
#   background of the skill icon (similar to suit_advantage but using
#   the owner's suit instead of the advantage suit).
#
# effects_battle (bool):
#   When True the skill affects battle power calculations, i.e. it
#   modifies the total power of battle figures or the power of
#   battle moves.

# ── Suit Advantage Cycle ──────────────────────────────────────
# Spades → Hearts → Clubs → Diamonds → Spades
# Each suit beats the suit it maps to.
SUIT_ADVANTAGE = {
    'Spades':   'Hearts',
    'Hearts':   'Clubs',
    'Clubs':    'Diamonds',
    'Diamonds': 'Spades',
}

# Reverse lookup: which suit beats me?
SUIT_DISADVANTAGE = {v: k for k, v in SUIT_ADVANTAGE.items()}


def get_advantage_suit(suit: str) -> str:
    """Return the suit that the given suit has an advantage over."""
    return SUIT_ADVANTAGE.get(suit)


def get_disadvantage_suit(suit: str) -> str:
    """Return the suit that has an advantage over the given suit."""
    return SUIT_DISADVANTAGE.get(suit)


SKILL_DEFINITIONS = {
    'cannot_attack': {
        'name': 'Cannot Attack',
        'description': 'This figure cannot initiate an advance.',
        'icon': 'img/figures/state_icons/cannot_attack.png',
        'suit_advantage': False,
        'suit_self': False,
        'effects_battle': False,
    },
    'must_be_attacked': {
        'name': 'Must Be Attacked',
        'description': 'Opponents must target this figure before others when choosing a defender.',
        'icon': 'img/figures/state_icons/must_be_attacked.png',
        'suit_advantage': False,
        'suit_self': False,
        'effects_battle': False,
    },
    'rest_after_attack': {
        'name': 'Rest After Attack',
        'description': 'After being used as battle figure, this figure needs to rest the upcoming round and can only be used in the round after again.',
        'icon': 'img/figures/state_icons/hourglass.png',
        'suit_advantage': False,
        'suit_self': False,
        'effects_battle': False,
    },
    'distance_attack': {
        'name': 'Distance Attack',
        'description': 'This figure reduces the power of an opponents figure whose suit it has an advantage over by the value of its number card, whenever such a figure is used during battle (both, battle figure and figures called in a battle move). This figure can only be used once per battle.',
        'icon': 'img/figures/state_icons/distance.png',
        'suit_advantage': True,
        'suit_self': False,
        'effects_battle': True,
    },
    'buffs_allies': {
        'name': 'Buffs Allies',
        'description': 'Increases the base power of all village figures with the same suit by +4.',
        'icon': 'img/figures/state_icons/buff.png',
        'suit_advantage': False,
        'suit_self': True,
        'effects_battle': True,
    },
    'buffs_allies_defence': {
        'name': 'Defence Buff',
        'description': 'Your battle figures gain additional power when defending that equals the value of the number card.',
        'icon': 'img/figures/state_icons/buff_defence.png',
        'suit_advantage': False,
        'suit_self': False,
        'effects_battle': True,
    },
    'blocks_bonus': {
        'name': 'Blocks Bonus',
        'description': 'Blocks the support bonus of the opponents battle figure whose suit this figure has an advantage over.',
        'icon': 'img/figures/state_icons/block.png',
        'suit_advantage': True,
        'suit_self': False,
        'effects_battle': True,
    },
    'cannot_defend': {
        'name': 'Cannot Defend',
        'description': 'This figure cannot be selected as a defender and cannot counter-advance when the opponent attacks.',
        'icon': 'img/figures/state_icons/cannot_defend.png',
        'suit_advantage': False,
        'suit_self': False,
        'effects_battle': False,
    },
    'instant_charge': {
        'name': 'Instant Advance',
        'description': 'This figure can advance immediately when placed on the field.',
        'icon': 'img/figures/state_icons/instant_charge.png',
        'suit_advantage': False,
        'suit_self': False,
        'effects_battle': False,
    },
    'cannot_be_blocked': {
        'name': 'Cannot Be Blocked',
        'description': 'When this figure advances, the opponent cannot counter-advance, i.e. you can select the opponents battle figure.',
        'icon': 'img/figures/state_icons/cannot_be_blocked2.png',
        'suit_advantage': False,
        'suit_self': False,
        'effects_battle': False,
    },
    'cannot_be_targeted': {
        'name': 'Cannot Be Targeted',
        'description': 'This figure cannot be selected as a target for battle or spells.',
        'icon': 'img/figures/state_icons/cannot_be_targeted.png',
        'suit_advantage': False,
        'suit_self': False,
        'effects_battle': False,
    },
    'checkmate': {
        'name': 'Checkmate',
        'description': 'If this figure dies you lose the game. This figure cannot be selected by the opponent for counter-advance. Immune to spells. This Figure is always visible to opponent. ',
        'icon': 'img/figures/state_icons/checkmate.png',
        'suit_advantage': False,
        'suit_self': False,
        'effects_battle': False,
    },
}

# Ordered list of all skill keys (controls display order)
SKILL_KEYS = list(SKILL_DEFINITIONS.keys())

# Convenience: icon path lookup (replaces the old SKILL_ICON_IMG_PATH_DICT)
SKILL_ICON_IMG_PATH_DICT = {
    key: defn['icon'] for key, defn in SKILL_DEFINITIONS.items()
}
