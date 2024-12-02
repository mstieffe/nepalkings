from config.screen_settings import SCREEN_WIDTH, SCREEN_HEIGHT

CARD_IMG_PATH = 'img/new_cards/'

ALPHA_OVERLAY = 40

CARD_WIDTH = int(0.06 * SCREEN_WIDTH)
CARD_HEIGHT = int(0.15 * SCREEN_HEIGHT)

#CARD_HEIGHT = CARD_WIDTH * test_card.get_height() / test_card.get_width()

BRIGHTNESS_FACTOR = 50

CARD_SPACER = int(0.02 * SCREEN_WIDTH)

CARD_SLOT_BORDER_WIDTH = int(0.005 * SCREEN_WIDTH)

SUITS = ['Hearts', 'Diamonds', 'Clubs', 'Spades']
SUITS_BLACK = ['Clubs', 'Spades']
SUITS_RED = ['Hearts', 'Diamonds']

COLORS = ['offensive', 'defensive']

RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10','J', 'Q', 'K', 'A']

NUMBER_CARDS = ['7', '8', '9', '10']

RANK_TO_IMG_PATH = {
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
}

RANK_TO_VALUE = {
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