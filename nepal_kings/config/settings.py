
# settings.py

import os
import sys

# Base path for resource loading (handles PyInstaller bundles)
if getattr(sys, 'frozen', False):
    # Running as a PyInstaller bundle
    RESOURCE_BASE = sys._MEIPASS
else:
    # Running from source — nepal_kings/ directory
    RESOURCE_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from config.screen_settings import *
from config.build_screen_settings import *
from config.game_settings import *
from config.server_settings import *
from config.card_settings import *
from config.figure_settings import *
from config.spell_settings import *
from config.font_settings import *
from config.button_settings import *
from config.colour_settings import *
from config.info_scroll_settings import *
from game.components.figures.family_configs.skill_config import *
from config.dialogue_box_settings import *
from config.state_buttons_settings import *
from config.msg_settings import *
from config.field_screen_settings import *
from config.battle_shop_settings import *
from config.battle_screen_settings import *
from config.guide_book_settings import *
from config.game_menu_settings import *

def get_x(relative_position):
    return SCREEN_WIDTH * relative_position

def get_y(relative_position):
    return SCREEN_HEIGHT * relative_position