# settings.py
import pygame
from utils import scale

# GAME SETTINGS

NUM_MAIN_CARDS_START = 12
NUM_SIDE_CARDS_START = 4

# Screen settings
SCREEN_WIDTH = 1600
SCREEN_HEIGHT = 900
SCREEN_CAPTION = 'Nepal Kings'

# Font settings
FONT_PATH = None
FONT_SIZE = int(0.05 * SCREEN_HEIGHT)
FONT_SIZE_DETAIL = int(0.02 * SCREEN_HEIGHT)
LOGOUT_FONT_SIZE = int(0.03 * SCREEN_HEIGHT)

# Timings
MESSAGE_DURATION = 5000

# Sizes
CENTER_X = int(0.5 * SCREEN_WIDTH)
CENTER_Y = int(0.5 * SCREEN_HEIGHT)

BUTTON_WIDTH = int(0.2 * SCREEN_WIDTH)
BUTTON_HEIGHT = int(0.06 * SCREEN_HEIGHT)

CONTROL_BUTTON_WIDTH = int(0.15 * SCREEN_WIDTH)
CONTROL_BUTTON_HEIGHT = int(0.04 * SCREEN_HEIGHT)

SMALL_FIELD_WIDTH = int(0.375 * SCREEN_WIDTH)
SMALL_FIELD_HEIGHT = int(0.05 * SCREEN_HEIGHT)

MESSAGE_SPACING = int(0.04 * SCREEN_HEIGHT)

TINY_SPACER_X = int(0.01 * SCREEN_WIDTH)
TINY_SPACER_Y = int(0.01 * SCREEN_HEIGHT)

SMALL_SPACER_X = int(0.02 * SCREEN_WIDTH)
SMALL_SPACER_Y = int(0.02 * SCREEN_HEIGHT)

BIG_SPACER_X = int(0.1 * SCREEN_WIDTH)
BIG_SPACER_Y = int(0.1 * SCREEN_HEIGHT)

DIALOGUE_BOX_WIDTH = int(0.55 * SCREEN_WIDTH)
DIALOGUE_BOX_HEIGHT = int(0.2 * SCREEN_HEIGHT)

# Color settings
COLOR_HEADER = (0, 0, 0)

COLOR_DIALOGUE_BOX = (100, 100, 100)

BUTTON_COLOR_PASSIVE = (0, 0, 0)
BUTTON_COLOR_ACTIVE = (255, 0, 0)

FIELD_COLOR_PASSIVE = (50, 50, 50)
FIELD_COLOR_ACTIVE = (100, 100, 100)

TEXT_COLOR_PASSIVE = (255, 255, 255)
TEXT_COLOR_ACTIVE = (0, 0, 0)

CARD_SLOT_BORDER_COLOR = (0, 0, 0)
CARD_SLOT_COLOR = (100, 100, 100)
CARD_SLOT_COLOR_HOVERED = (150, 150, 150)

BACKGROUND_COLOR = (22, 55, 60)

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)

# BUTTONS
HAND_BUTTON_WIDTH = int(0.05 * SCREEN_WIDTH)
BUILD_BUTTON_WIDTH = int(0.1 * SCREEN_WIDTH)
ACTION_BUTTON_WIDTH = int(0.1 * SCREEN_WIDTH)

BUTTON_IMG_PATH = 'img/button/'

# GAME BUTTON
GAME_BUTTON_SYMBOL_IMG_PATH = 'img/game_button/symbol/'
GAME_BUTTON_GLOW_IMG_PATH = 'img/game_button/glow/'
GAME_BUTTON_STONE_IMG_PATH = 'img/game_button/stone/'

GAME_BUTTON_STONE_WIDTH = int(0.1 * SCREEN_WIDTH)
GAME_BUTTON_SYMBOL_WIDTH = int(0.1 * SCREEN_WIDTH)
GAME_BUTTON_GLOW_WIDTH = int(0.1 * SCREEN_WIDTH)

GAME_BUTTON_STONE_BIG_WIDTH = int(0.15 * SCREEN_WIDTH)
GAME_BUTTON_SYMBOL_BIG_WIDTH = int(0.12 * SCREEN_WIDTH)
GAME_BUTTON_GLOW_BIG_WIDTH = int(0.12 * SCREEN_WIDTH)

HAND_BUTTON_STONE_WIDTH = int(0.06 * SCREEN_WIDTH)
HAND_BUTTON_SYMBOL_WIDTH = int(0.03 * SCREEN_WIDTH)
HAND_BUTTON_GLOW_WIDTH = int(0.04 * SCREEN_WIDTH)

HAND_BUTTON_STONE_BIG_WIDTH = int(0.06 * SCREEN_WIDTH)
HAND_BUTTON_SYMBOL_BIG_WIDTH = int(0.04 * SCREEN_WIDTH)
HAND_BUTTON_GLOW_BIG_WIDTH = int(0.06 * SCREEN_WIDTH)

HAND_BUTTON_GLOW_SHIFT = int(0.00 * SCREEN_WIDTH)


# HAND BUTTON
MAIN_HAND_X = int(0.05 * SCREEN_WIDTH)
MAIN_HAND_Y = int(0.8 * SCREEN_HEIGHT)

SIDE_HAND_X = int(0.5 * SCREEN_WIDTH)
SIDE_HAND_Y = int(0.8 * SCREEN_HEIGHT)

BUILD_BUTTON_X = int(0.84 * SCREEN_WIDTH)
BUILD_BUTTON_Y = int(0.86 * SCREEN_HEIGHT)

ACTION_BUTTON_X = int(0.94 * SCREEN_WIDTH)
ACTION_BUTTON_Y = int(0.86 * SCREEN_HEIGHT)

# Server settings
SERVER_URL = 'http://localhost:5000'

DB_URL = 'sqlite:///test.db'

def get_x(relative_position):
    return SCREEN_WIDTH*relative_position

def get_y(relative_position):
    return SCREEN_HEIGHT*relative_position

# Card settings

MAX_MAIN_CARD_SLOTS = 14
MAX_SIDE_CARD_SLOTS = 8

CARD_IMG_PATH = 'img/new_cards/'

# Set the desired relative size as a percentage of the screen size
CARD_RELATIVE_WIDTH = 0.06
CARD_WIDTH = int(CARD_RELATIVE_WIDTH * SCREEN_WIDTH)
#test_card = pygame.image.load(CARD_IMG_PATH + 'back.png')
#CARD_RELATIVE_HEIGHT = CARD_RELATIVE_WIDTH * test_card.get_height() / test_card.get_width()
CARD_RELATIVE_HEIGHT = 0.15
CARD_HEIGHT = int(CARD_RELATIVE_HEIGHT * SCREEN_HEIGHT)

#CARD_HEIGHT = CARD_WIDTH * test_card.get_height() / test_card.get_width()

BRIGHTNESS_FACTOR = 50

CARD_SPACER = int(0.02 * SCREEN_WIDTH)

CARD_SLOT_BORDER_WIDTH = int(0.005 * SCREEN_WIDTH)

ALPHA_OVERLAY = 40

SUITS = ['Hearts', 'Diamonds', 'Clubs', 'Spades']
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10','J', 'Q', 'K', 'A']

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