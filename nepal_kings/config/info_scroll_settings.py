from config.screen_settings import SCREEN_WIDTH, SCREEN_HEIGHT, _FS, _UI_SCALE

INFO_SCROLL_WIDTH = int(0.105 * SCREEN_WIDTH)
INFO_SCROLL_X = int(0.011 * SCREEN_WIDTH)   
INFO_SCROLL_Y = int(0.36 * SCREEN_HEIGHT)

INFO_SCROLL_HEIGHT = int(0.24 * SCREEN_HEIGHT)
INFO_SCROLL_BG_IMG_PATH = 'img/background/paper4.png'  # legacy, no longer used
GLOW_RECT_IMG_PATH = 'img/glow/rect/'

INFO_SCROLL_FONT_SIZE = int(0.02 * _FS)
INFO_SCROLL_Y_TITLE_MARGIN = int(0.015 * SCREEN_HEIGHT)
INFO_SCROLL_TITLE_SPACING = int(0.025 * SCREEN_HEIGHT)
INFO_SCROLL_LINE_SPACING = int(0.035 * SCREEN_HEIGHT)
INFO_SCROLL_TEXT_COLOR = (220, 215, 200)        # warm off-white for body text
INFO_SCROLL_TITLE_COLOR = (250, 221, 0)         # gold for title
INFO_SCROLL_SCORE_COLOR = (200, 200, 200)
INFO_SCROLL_TEXT_MARGIN = int(0.005 * SCREEN_WIDTH)
INFO_SCROLL_TEXT_PADDING = int(0.002 * SCREEN_WIDTH)

INFO_SCROLL_ICON_SIZE = int(0.019 * SCREEN_WIDTH)
INFO_SCROLL_ICON_MARGIN = int(0.006 * SCREEN_WIDTH)
INFO_SCROLL_ICON_SPACING = int(0.004 * SCREEN_WIDTH)

# Dark-theme panel for info scroll
INFO_SCROLL_BG_CLR = (35, 30, 25, 200)          # warm dark semi-transparent
INFO_SCROLL_BORDER_CLR = (140, 130, 110)         # muted warm border
INFO_SCROLL_BORDER_WIDTH = 1
INFO_SCROLL_CORNER_R = int(0.008 * SCREEN_HEIGHT)

# Resource value pill colours (muted, dark-theme friendly)
INFO_SCROLL_RED_PILL_CLR = (45, 90, 45)          # muted green for djungle/red suits
INFO_SCROLL_BLACK_PILL_CLR = (35, 60, 110)       # muted blue for himalaya/black suits
INFO_SCROLL_DEFICIT_BORDER_CLR = (200, 50, 50)   # red border for deficit



RESOURCE_ICON_IMG_PATH_DICT = {
    'rice': 'img/resource_icons/rice.png',
    'wood': 'img/resource_icons/wood.png',
    'stone': 'img/resource_icons/stone.png',
    'sword': 'img/resource_icons/sword.png',
    'shield': 'img/resource_icons/shield.png',
    'meat': 'img/resource_icons/meat.png',
    'rice_meat': 'img/resource_icons/rice_meat.png',
    'wood_stone': 'img/resource_icons/wood_stone.png',
    'sword_shield': 'img/resource_icons/sword_shield.png',
    'warrior_red': 'img/resource_icons/warrior_red.png',
    'warrior_black': 'img/resource_icons/warrior_black.png',
    'warrior_red_black': 'img/resource_icons/warrior_red_black.png',
    'villager_red': 'img/resource_icons/villager_red.png',
    'villager_black': 'img/resource_icons/villager_black.png',
    'villager_red_black': 'img/resource_icons/villager_red_black.png',
}

SLOT_ICON_IMG_PATH_DICT = {
    'castle': 'img/slot_icons/castle.png',
    'village': 'img/slot_icons/village.png',
    'military': 'img/slot_icons/military.png',
}

# SKILL_ICON_IMG_PATH_DICT is now generated from SKILL_DEFINITIONS
# in game/components/figures/family_configs/skill_config.py  (imported via settings.py)

# SCOREBOARD SCROLL
SCOREBOARD_SCROLL_X = int(0.01 * SCREEN_WIDTH)
SCOREBOARD_SCROLL_Y = int(0.024 * SCREEN_HEIGHT)
SCOREBOARD_SCROLL_WIDTH = int(0.11 * SCREEN_WIDTH)
SCOREBOARD_SCROLL_HEIGHT = int(0.14 * SCREEN_HEIGHT)
SCOREBOARD_SCROLL_Y_TEXT_MARGIN = int(0.07 * SCREEN_HEIGHT)
SCOREBOARD_SCROLL_X_TEXT_MARGIN = int(0.02 * SCREEN_WIDTH)
SCOREBOARD_SCROLL_SPACER = int(0.01 * SCREEN_WIDTH)
SCOREBOARD_SCROLL_BG_IMG_PATH = 'img/background/paper3.png'

# On mobile, use smaller fonts so text fits the original-size panel
SCOREBOARD_SCROLL_FONT_SIZE = int(0.016 * _FS) if _UI_SCALE > 1.0 else int(0.02 * _FS)
SCOREBOARD_SCROLL_FONT_TITLE_SIZE = int(0.025 * SCREEN_HEIGHT)
SCOREBOARD_SCROLL_NUMBER_FONT_SIZE = int(0.028 * _FS) if _UI_SCALE > 1.0 else int(0.04 * _FS)
SCOREBOARD_SCROLL_LINE_SPACING = int(0.02 * SCREEN_HEIGHT)
SCOREBOARD_SCROLL_TEXT_COLOR = (20, 20, 20)

SCOREBOARD_CROSS_COLOR = (20, 20, 20)
SCOREBOARD_CROSS_ALPHA = 80
SCOREBOARD_CROSS_WIDTH = int(0.0015 * SCREEN_WIDTH)
SCOREBOARD_CROSS_SPACING = int(0.03 * SCREEN_WIDTH)
SCOREBOARD_CELL_TEXT_SPACING = int(0.002 * SCREEN_WIDTH)
SCOREBOARD_CELL_VALUE_OFFSET = int(0.006 * SCREEN_HEIGHT) if _UI_SCALE > 1.0 else int(0.010 * SCREEN_HEIGHT)
SCOREBOARD_CELL_SUBTITLE_SPACING = int(0.006 * SCREEN_HEIGHT) if _UI_SCALE > 1.0 else int(0.010 * SCREEN_HEIGHT)
SCOREBOARD_SUBTITLE_FONT_SIZE = int(0.009 * _FS) if _UI_SCALE > 1.0 else int(0.012 * _FS)
SCOREBOARD_LIMIT_SECTION_HEIGHT = int(0.03 * SCREEN_HEIGHT)

# Mobile scoreboard panel design (replaces paper background when _UI_SCALE > 1)
SCOREBOARD_USE_PANEL = (_UI_SCALE > 1.0)
SCOREBOARD_PANEL_BG_CLR        = (35, 30, 25, 200)       # warm dark semi-transparent
SCOREBOARD_PANEL_BORDER_CLR    = (140, 130, 110)          # muted warm border
SCOREBOARD_PANEL_BORDER_WIDTH  = 1
SCOREBOARD_PANEL_CORNER_R      = int(0.008 * SCREEN_HEIGHT)
SCOREBOARD_PANEL_TEXT_COLOR    = (220, 215, 200)          # warm off-white for labels
SCOREBOARD_PANEL_VALUE_COLOR   = (250, 245, 230)          # bright off-white for numbers
SCOREBOARD_PANEL_CROSS_COLOR   = (120, 110, 95)           # subtle warm divider
SCOREBOARD_PANEL_CROSS_ALPHA   = 120






