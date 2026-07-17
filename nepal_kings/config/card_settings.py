# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
from config.screen_settings import SCREEN_WIDTH, SCREEN_HEIGHT, _UI_SCALE, _IS_MOBILE

CARD_IMG_PATH = 'img/cards/'
RED_CROSS_IMG_PATH = 'img/cards/red_cross.png'

ALPHA_OVERLAY = 40
ALPHA_MISSING_OVERLAY = 60

CARD_WIDTH = int(0.06 * SCREEN_WIDTH)
CARD_HEIGHT = int(0.15 * SCREEN_HEIGHT)

RED_CROSS_WIDTH = int(0.02 * SCREEN_WIDTH)
RED_CROSS_HEIGHT = int(0.02 * SCREEN_WIDTH)

# Vertical nudge for the "X/Y cards" text below each hand (negative = up)
HAND_CARD_COUNT_Y_NUDGE = int(-0.016 * SCREEN_HEIGHT) if _IS_MOBILE else int(-0.008 * SCREEN_HEIGHT)

#CARD_HEIGHT = CARD_WIDTH * test_card.get_height() / test_card.get_width()

BRIGHTNESS_FACTOR = 100

CARD_SPACER = int(0.023 * SCREEN_WIDTH)

CARD_SLOT_BORDER_WIDTH = int(0.005 * SCREEN_WIDTH)

SUITS = ['Hearts', 'Diamonds', 'Clubs', 'Spades']
SUITS_BLACK = ['Clubs', 'Spades']
SUITS_RED = ['Hearts', 'Diamonds']

COLORS = ['offensive', 'defensive']

RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10','J', 'Q', 'K', 'A']
RANKS_WITH_ZK = ['2', '3', '4', '5', '6', '7', '8', '9', '10','J', 'Q', 'K', 'A', 'K', 'ZK']
RANKS_ZK = ['3', '6', '7', '8', '9', '10']
RANKS_MAIN_CARDS = ['7', '8', '9', '10', 'J', 'Q', 'K', 'A']
RANKS_SIDE_CARDS = ['2', '3', '4', '5', '6']

# Recipe roles. Keep these separate from ``NUMBER_CARDS``: that legacy list is
# the set of main-card number variants used by figure generation, while these
# constants describe how both pack families are taught and grouped.
MAIN_KEY_CARD_RANKS = ('J', 'Q', 'A', 'K')
MAIN_NUMBER_CARD_RANKS = ('7', '8', '9', '10')
SIDE_KEY_CARD_RANKS = ('2', '4', '5')
SIDE_NUMBER_CARD_RANKS = ('3', '6')

# Maharaja: a crafted king-flavour card. Not part of the regular rank pools
# (no booster drops, no sell/convert); crafted in the collection by trading
# one copy of every rank of a suit. Builds Maharaja castle figures in
# conquer/defence configs.
RANK_MAHARAJA = 'MK'
MAHARAJA_CRAFT_RANKS = RANKS  # one of each rank of the suit is consumed

NUMBER_CARDS = ['7', '8', '9', '10']

# Loot bucket classification by rank.  Used by the conquer loot system to
# bucket every captured card into either "key" or "number" pools.  All ranks
# are covered, so any card with a rank belongs to exactly one bucket.
LOOT_NUMBER_RANKS = frozenset({'3', '6', '7', '8', '9', '10'})
LOOT_KEY_RANKS = frozenset({'2', '4', '5', 'J', 'Q', 'K', 'A', RANK_MAHARAJA})

RANK_TO_IMG_PATH = {
    'MK': '14_maharaja',
    'A': '14',
    'K': '13',
    'Q': '12',
    'J': '11',
    '10': '10',
    '9': '09',
    '8': '08',
    '7': '07',
    '6': '06',
    '5': '05',
    '4': '04',
    '3': '03',
    '2': '02',
    'ZK': '00',
}

RANK_TO_VALUE = {
    'MK': 4,
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

RANK_TO_SORT = {
    'MK': 0,
    'A': 2,
    'K': 1,
    'Q': 3,
    'J': 4,
    '10': 5,
    '9': 6,
    '8': 7,
    '7': 8,
    '6': 9,
    '5': 10,
    '4': 11,
    '3': 12,
    '2': 13,
}

SUIT_TO_IMG_PATH = {
    'Spades': 's',
    'Hearts': 'h',
    'Diamonds': 'd',
    'Clubs': 'c',
}

SUIT_TO_COLOR = {
    'spades': 'defensive',
    'hearts': 'offensive',
    'diamonds': 'offensive',
    'clubs': 'defensive',
}

COLOR_TO_SUITS = {
    'offensive': ['Hearts', 'Diamonds'],
    'defensive': ['Spades', 'Clubs'],
}
