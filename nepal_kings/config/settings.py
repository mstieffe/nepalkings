
# settings.py

from config.screen_settings import *
from config.game_settings import *
from config.server_settings import *
from config.card_settings import *
from config.figure_settings import *
from config.font_settings import *
from config.button_settings import *
from config.colour_settings import *

def get_x(relative_position):
    return SCREEN_WIDTH * relative_position

def get_y(relative_position):
    return SCREEN_HEIGHT * relative_position