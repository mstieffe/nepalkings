# settings.py

# Screen settings
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
SCREEN_CAPTION = 'Nepal Kings'

# Font settings
FONT_PATH = None
FONT_SIZE = int(0.05 * SCREEN_HEIGHT)  # Adjust the font size based on screen height

# Sizes
CENTER_X = int(0.5 * SCREEN_WIDTH)
CENTER_Y = int(0.5 * SCREEN_HEIGHT)

BUTTON_WIDTH = int(0.2 * SCREEN_WIDTH)
BUTTON_HEIGHT = int(0.06 * SCREEN_HEIGHT)

SMALL_FIELD_WIDTH = int(0.375 * SCREEN_WIDTH)
SMALL_FIELD_HEIGHT = int(0.05 * SCREEN_HEIGHT)

TINY_SPACER_X = int(0.01 * SCREEN_WIDTH)
TINY_SPACER_Y = int(0.01 * SCREEN_HEIGHT)

SMALL_SPACER_X = int(0.02 * SCREEN_WIDTH)
SMALL_SPACER_Y = int(0.02 * SCREEN_HEIGHT)

# Color settings
COLOR_HEADER = (0, 0, 0)

BUTTON_COLOR_PASSIVE = (0, 0, 0)
BUTTON_COLOR_ACTIVE = (255, 0, 0)

FIELD_COLOR_PASSIVE = (50, 50, 50)
FIELD_COLOR_ACTIVE = (100, 100, 100)

TEXT_COLOR_PASSIVE = (255, 255, 255)
TEXT_COLOR_ACTIVE = (0, 0, 0)

BACKGROUND_COLOR = (255, 255, 255)

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)

# Server settings
SERVER_URL = 'http://localhost:5000'

def get_x(relative_position):
    return SCREEN_WIDTH*relative_position

def get_y(relative_position):
    return SCREEN_HEIGHT*relative_position