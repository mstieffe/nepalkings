from config.screen_settings import SCREEN_WIDTH, SCREEN_HEIGHT
import pygame

FONT_SIZE_DIALOGUE_BOX = int(0.03 * SCREEN_HEIGHT)
FONT_SIZE_TITLE_DIALOGUE_BOX = int(0.04 * SCREEN_HEIGHT)

TITLE_TEXT_COLOR = (200, 200, 200)

DIALOGUE_BOX_WIDTH = int(0.55 * SCREEN_WIDTH)
DIALOGUE_BOX_HEIGHT = int(0.2 * SCREEN_HEIGHT)
DIALOGUE_BOX_BORDER_WIDTH = 8
COLOR_DIALOGUE_BOX = (80, 80, 80)
COLOR_DIALOGUE_BOX_BORDER = (40, 40, 40)
DIALOGUE_BOX_IMG_HEIGHT = int(0.1 * SCREEN_HEIGHT)
DIALOGUE_BOX_TEXT_MARGIN_Y = int(0.05 * SCREEN_HEIGHT)
DIALOGUE_BOX_ICON_HEIGHT = int(0.05 * SCREEN_HEIGHT)
DIALOGUE_BOX_ICON_MARGIN_X = int(0.05 * SCREEN_WIDTH)
DIALOGUE_BOX_ICON_MARGIN_Y = int(0.05 * SCREEN_HEIGHT)

DIALOGUE_BOX_ICON_NAME_TO_IMG_DICT = {
    'info': pygame.image.load('img/dialogue_box/icons/exclamation_mark.png'),
    'warning': pygame.image.load('img/dialogue_box/icons/exclamation_mark.png'),
    'error': pygame.image.load('img/dialogue_box/icons/error.png'),
    'question': pygame.image.load('img/dialogue_box/icons/question_mark.png'),
    'success': pygame.image.load('img/dialogue_box/icons/success.png'),
    'victory': pygame.image.load('img/dialogue_box/icons/victory.png'),
    'loot': pygame.image.load('img/dialogue_box/icons/loot.png'),
}