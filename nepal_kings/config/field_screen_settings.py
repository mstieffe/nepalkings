# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
from config.screen_settings import SCREEN_WIDTH, SCREEN_HEIGHT, _FS, _UI_SCALE, _IS_MOBILE
from config.font_settings import FS_BODY, FS_HEADING, FS_SMALL

FIELD_ICON_START_X = int(0.23 * SCREEN_WIDTH)
FIELD_ICON_START_Y = int(0.35 * SCREEN_HEIGHT)
FIELD_ICON_WIDTH = int(0.115 * SCREEN_WIDTH)
FIELD_ICON_PADDING_X = int(0.0 * SCREEN_WIDTH)
FIELD_ICON_PADDING_Y = int(0.02 * SCREEN_HEIGHT)

FIELD_FIGURE_CARD_MARGIN_Y_CASTLE = int(0.08 * SCREEN_HEIGHT)
FIELD_FIGURE_CARD_MARGIN_Y_VILLAGE = int(0.06 * SCREEN_HEIGHT)
FIELD_FIGURE_CARD_MARGIN_Y_MILITARY = int(0.06 * SCREEN_HEIGHT)


FIELD_FIGURE_CARD_DELTA_X = int(0.019 * SCREEN_WIDTH)
FIELD_FIGURE_CARD_WIDTH = int(0.015 * SCREEN_WIDTH * _UI_SCALE)
FIELD_FIGURE_CARD_HEIGHT = int(0.028 * SCREEN_HEIGHT * _UI_SCALE)

FIELD_SELF_X = int(0.17 * SCREEN_WIDTH)
FIELD_OPPONENT_X = int(0.54 * SCREEN_WIDTH)
FIELD_HEIGHT = int(0.6 * SCREEN_HEIGHT)
FIELD_Y = int(0.08 * SCREEN_HEIGHT)

FIELD_FILL_COLOR = (106, 58, 24) #(40, 40, 40)
FIELD_BORDER_COLOR = (25, 10, 4) #(100, 100, 100)
FIELD_BORDER_WIDTH = max(2, int(0.003 * SCREEN_HEIGHT))
FIELD_TRANSPARENCY = 200

# Field compartment titles
FIELD_TITLE_FONT_SIZE = int(FS_SMALL * 0.9) if _IS_MOBILE else FS_BODY  # was int(0.022 * _FS)
FIELD_TITLE_COLOR = (220, 200, 180)
FIELD_TITLE_PADDING = int(0.008 * SCREEN_HEIGHT)

# Board titles ("YOU" / "OPPONENT")
FIELD_BOARD_TITLE_FONT_SIZE = FS_HEADING if _IS_MOBILE else int(FS_HEADING * 1.08)  # was int(0.028 * _FS)  →  0.026 * 1.08 ≈ 0.028
FIELD_BOARD_TITLE_COLOR = FIELD_BORDER_COLOR  # Match border color
FIELD_BOARD_TITLE_Y_OFFSET = int(0.00 * SCREEN_HEIGHT)  # Offset above the field

# Slot icons for compartment backgrounds
SLOT_ICON_IMG_PATH_DICT = {
    'castle': 'img/slot_icons/castle.png',
    'village': 'img/slot_icons/village.png',
    'military': 'img/slot_icons/military.png',
}
SLOT_ICON_TRANSPARENCY = 50  # Alpha value for slot icon backgrounds (0-255)

# Scale factor for figure icon/frame on the field (relative to FIELD_ICON_WIDTH).
# Larger on mobile so figures are easier to tap.
FIELD_FIGURE_ICON_SCALE = 0.60 if _IS_MOBILE else 0.45

