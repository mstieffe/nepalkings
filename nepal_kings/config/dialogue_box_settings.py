# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
from config.screen_settings import SCREEN_WIDTH, SCREEN_HEIGHT, _FS, _UI_SCALE
import pygame

FONT_SIZE_DIALOGUE_BOX = int(0.026 * _FS)
FONT_SIZE_TITLE_DIALOGUE_BOX = int(0.034 * _FS)

TITLE_TEXT_COLOR = (250, 221, 0)
DIALOGUE_BOX_MSG_TEXT_CLR = (220, 215, 200)

DIALOGUE_BOX_WIDTH = int(0.50 * SCREEN_WIDTH)
DIALOGUE_BOX_HEIGHT = int(0.2 * SCREEN_HEIGHT)
DIALOGUE_BOX_CORNER_R = int(0.010 * SCREEN_HEIGHT)
DIALOGUE_BOX_BORDER_WIDTH = 1
DIALOGUE_BOX_BG_CLR = (28, 28, 34, 210)
DIALOGUE_BOX_BORDER_CLR = (140, 130, 110)
DIALOGUE_BOX_SEP_CLR = (100, 95, 85)
DIALOGUE_BOX_OVERLAY_CLR = (0, 0, 0, 100)

# Legacy flat-color aliases (kept for reference, no longer primary)
COLOR_DIALOGUE_BOX = (80, 80, 80)
COLOR_DIALOGUE_BOX_BORDER = (40, 40, 40)

DIALOGUE_BOX_IMG_HEIGHT = int(0.16 * SCREEN_HEIGHT)
DIALOGUE_BOX_DRAWABLE_OBJECT_HEIGHT = int(0.19 * SCREEN_HEIGHT * _UI_SCALE)
DIALOGUE_BOX_TEXT_MARGIN_Y = int(0.040 * SCREEN_HEIGHT)
DIALOGUE_BOX_ICON_HEIGHT = int(0.055 * SCREEN_HEIGHT)
DIALOGUE_BOX_ICON_MARGIN_X = int(0.05 * SCREEN_WIDTH)
DIALOGUE_BOX_ICON_MARGIN_Y = int(0.05 * SCREEN_HEIGHT)

# Button styling for dialogue box
DIALOGUE_BOX_BTN_IMG_PATH = 'img/menu_button/menu_button2.png'
DIALOGUE_BOX_BTN_W = int(0.14 * SCREEN_WIDTH)
DIALOGUE_BOX_BTN_H = int(0.050 * SCREEN_HEIGHT)
DIALOGUE_BOX_BTN_GAP = int(0.015 * SCREEN_WIDTH)
DIALOGUE_BOX_BTN_MARGIN_BOTTOM = int(0.025 * SCREEN_HEIGHT)
DIALOGUE_BOX_BTN_FONT_SIZE = int(0.022 * _FS)
DIALOGUE_BOX_BTN_TEXT_CLR = (230, 225, 210)
DIALOGUE_BOX_BTN_TEXT_HOVER_CLR = (255, 245, 220)
DIALOGUE_BOX_GLOW_DIR = 'img/menu_button/glow/'

DIALOGUE_BOX_ICON_NAME_TO_IMG_DICT = {
    'info': pygame.image.load('img/dialogue_box/icons/exclamation_mark.png'),
    'warning': pygame.image.load('img/dialogue_box/icons/exclamation_mark.png'),
    'error': pygame.image.load('img/dialogue_box/icons/error.png'),
    'question': pygame.image.load('img/dialogue_box/icons/question_mark.png'),
    'success': pygame.image.load('img/dialogue_box/icons/success.png'),
    'victory': pygame.image.load('img/dialogue_box/icons/victory_small.png'),
    'defeat': pygame.image.load('img/dialogue_box/icons/defeat_small.png'),
    'draw': pygame.image.load('img/dialogue_box/icons/draw.png'),
    'loot': pygame.image.load('img/dialogue_box/icons/loot.png'),
    'figure': pygame.image.load('img/dialogue_box/icons/figure.png'),
    'magic': pygame.image.load('img/dialogue_box/icons/magic.png'),
    'ceasefire_passive': pygame.image.load('img/status_icons/ceasefire_passive.png'),
    'ceasefire_active': pygame.image.load('img/status_icons/ceasefire_active.png'),
    'dices': pygame.image.load('img/dialogue_box/icons/dices.png'),
    'gold': pygame.image.load('img/dialogue_box/icons/gold.png'),
    'gold_lost': pygame.image.load('img/dialogue_box/icons/gold_lost.png'),
    'welcome': pygame.image.load('img/dialogue_box/icons/welcome.png'),
}

# Large icons for dialogue box content display
DIALOGUE_BOX_LARGE_ICON_DICT = {
    'victory': pygame.image.load('img/dialogue_box/icons/victory.png'),
    'defeat': pygame.image.load('img/dialogue_box/icons/defeat.png'),
    'draw': pygame.image.load('img/dialogue_box/icons/draw.png'),
}