# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
from config.screen_settings import SCREEN_WIDTH, SCREEN_HEIGHT, _FS, _UI_SCALE, _IS_MOBILE
from config.font_settings import FS_SMALL, FS_CONQUER_LABEL

# PATHS
FIGURE_ICON_IMG_DIR = 'img/figures/icons/'
FIGURE_ICON_GREYSCALE_IMG_DIR = 'img/figures/icons_greyscale/'
FIGURE_ICON_SMALL_IMG_DIR = 'img/figures/icons_small/'
FIGURE_ICON_SMALL_GREYSCALE_IMG_DIR = 'img/figures/icons_small_greyscale/'
FIGURE_FRAME_IMG_DIR = 'img/figures/frames/'
FIGURE_FRAME_GREYSCALE_IMG_DIR = 'img/figures/frames_greyscale/'
FIGURE_FRAME_HIDDEN_IMG_DIR = 'img/figures/frames_hidden/'
FIGURE_FRAME_HIDDEN_GREYSCALE_IMG_DIR = 'img/figures/frames_hidden_greyscale/'
FIGURE_GLOW_IMG_DIR = 'img/game_button/glow_rect/'
    

FIGURE_WIDTH = int(0.1 * SCREEN_WIDTH)
FIGURE_HEIGHT = int(0.1 * SCREEN_WIDTH)


# FIGURE ICON
# Mobile field columns are narrow after the web canvas is scaled into a phone
# viewport.  Keep the visual footprint compact there and rely on inflated hit
# areas for touch comfort.
FIGURE_ICON_BIG_SCALE = 1.15 if _IS_MOBILE else 1.2
FRAME_FIGURE_SCALE = 1.24 if _IS_MOBILE else 1.4

FIGURE_NAME_BG_COLOR = (235, 210, 170)          # warm parchment
FIGURE_NAME_INFO_BG_COLOR = (200, 172, 132)       # slightly darker parchment for info section
FIGURE_NAME_FRAME_COLOR = (120, 72, 36)           # rich warm brown border
FIGURE_NAME_SEP_COLOR = (170, 140, 100)           # soft separator
FIGURE_NAME_SHADOW_COLOR = (40, 30, 18, 90)       # subtle drop shadow
FIGURE_NAME_PADDING = int(0.005 * SCREEN_WIDTH)
# Compress name-label vertical padding separately from the info-row padding
FIGURE_NAME_TEXT_PADDING_SCALE = 0.35
# Compress info-row vertical padding to minimise box height on all devices
FIGURE_NAME_INFO_PADDING_SCALE = 0.2
FIGURE_NAME_CORNER_R = int(0.005 * SCREEN_HEIGHT)
FIGURE_NAME_SHADOW_OFFSET = max(2, int(0.003 * SCREEN_HEIGHT))

_FIGURE_ICON_MASK_PCT = 0.064 if _IS_MOBILE else 0.08
_FIGURE_ICON_MASK_BIG_PCT = 0.058 if _IS_MOBILE else 0.066
FIGURE_ICON_MASK_WIDTH = int(_FIGURE_ICON_MASK_PCT * SCREEN_WIDTH)
FIGURE_ICON_MASK_HEIGHT = int(_FIGURE_ICON_MASK_PCT * SCREEN_WIDTH)
FIGURE_ICON_MASK_BIG_WIDTH = int(_FIGURE_ICON_MASK_BIG_PCT * SCREEN_WIDTH)
FIGURE_ICON_MASK_BIG_HEIGHT = int(_FIGURE_ICON_MASK_BIG_PCT * SCREEN_WIDTH)
FIGURE_ICON_WIDTH = FIGURE_ICON_MASK_WIDTH*0.9
FIGURE_ICON_HEIGHT = FIGURE_ICON_MASK_HEIGHT*0.9
FIGURE_ICON_BIG_WIDTH = FIGURE_ICON_MASK_BIG_WIDTH*0.9
FIGURE_ICON_BIG_HEIGHT = FIGURE_ICON_MASK_BIG_HEIGHT*0.9
FIGURE_ICON_GLOW_WIDTH = int((0.074 if _IS_MOBILE else 0.09) * SCREEN_WIDTH)
FIGURE_ICON_GLOW_BIG_WIDTH = int((0.095 if _IS_MOBILE else 0.12) * SCREEN_WIDTH)
FIGURE_ICON_DELTA_X = int(0.08 * SCREEN_WIDTH)

FIGURE_ICON_SIN_AMPL = int(0.005 * SCREEN_HEIGHT)

FIGURE_ICON_CAPTION_COLOR = (95, 42, 22)

# The figure label plate (name + power + bonus row) is a primary reading
# surface. The old mobile shrink (0.82x) landed at ~12 CSS px after the
# phone downscale; floor it just under the LABEL tier — full LABEL forces
# too much name ellipsis in the narrow field columns.
FIGURE_ICON_FONT_CAPTION_FONT_SIZE     = (max(FS_CONQUER_LABEL, FS_SMALL)
                                          if _IS_MOBILE else FS_SMALL)
FIGURE_ICON_FONT_CAPTION_BIG_FONT_SIZE = int(FIGURE_ICON_FONT_CAPTION_FONT_SIZE * 1.18 if _IS_MOBILE else FS_SMALL * 1.25)


# SUIT ICON
SUIT_ICON_IMG_PATH = 'img/suits/'
SUIT_ICON_DARKWHITE_IMG_PATH = 'img/suits/darkwhite/'

SUIT_ICON_WIDTH = int(0.03 * SCREEN_WIDTH)
SUIT_ICON_HEIGHT = int(0.03 * SCREEN_WIDTH)

SUIT_ICON_BIG_WIDTH = int(0.037 * SCREEN_WIDTH)
SUIT_ICON_BIG_HEIGHT = int(0.037 * SCREEN_WIDTH)
SUIT_ICON_GLOW_WIDTH = int(0.06 * SCREEN_WIDTH)
SUIT_ICON_GLOW_BIG_WIDTH = int(0.06 * SCREEN_WIDTH)
