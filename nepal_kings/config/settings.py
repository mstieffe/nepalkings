
# settings.py

from config.screen_settings import *
from config.build_screen_settings import *
from config.game_settings import *
from config.server_settings import *
from config.card_settings import *
from config.figure_settings import *
from config.font_settings import *
from config.button_settings import *
from config.colour_settings import *
from config.info_scroll_settings import *
from config.dialogue_box_settings import *
from config.state_buttons_settings import *
from config.msg_settings import *
from config.field_screen_settings import *

def get_x(relative_position):
    return SCREEN_WIDTH * relative_position

def get_y(relative_position):
    return SCREEN_HEIGHT * relative_position