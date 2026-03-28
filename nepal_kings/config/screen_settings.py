# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
# Screen settings
import os as _os
SCREEN_WIDTH  = int(_os.environ.get('NK_SCREEN_WIDTH',  '1920'))
SCREEN_HEIGHT = int(_os.environ.get('NK_SCREEN_HEIGHT', '1080'))
SCREEN_CAPTION = 'Nepal Kings'

# Font-scale height: same as SCREEN_HEIGHT on desktop; inflated on mobile
# so that text stays readable when the canvas is CSS-scaled to a small screen.
_UI_SCALE = float(_os.environ.get('NK_UI_SCALE', '1.0'))
_FS = int(SCREEN_HEIGHT * _UI_SCALE)

# Sizes
CENTER_X = int(0.5 * SCREEN_WIDTH)
CENTER_Y = int(0.5 * SCREEN_HEIGHT)

CONTROL_BUTTON_WIDTH = int(0.15 * SCREEN_WIDTH)
CONTROL_BUTTON_HEIGHT = int(0.04 * SCREEN_HEIGHT)

MESSAGE_SPACING = int(0.04 * SCREEN_HEIGHT)

TINY_SPACER_X = int(0.01 * SCREEN_WIDTH)
TINY_SPACER_Y = int(0.01 * SCREEN_HEIGHT)

SMALL_SPACER_X = int(0.02 * SCREEN_WIDTH)
SMALL_SPACER_Y = int(0.02 * SCREEN_HEIGHT)

BIG_SPACER_X = int(0.1 * SCREEN_WIDTH)
BIG_SPACER_Y = int(0.1 * SCREEN_HEIGHT)

# Sub Screen settings
SUB_SCREEN_X = int(0.124 * SCREEN_WIDTH)
SUB_SCREEN_Y = int(0.01 * SCREEN_HEIGHT)


SUB_SCREEN_BACKGROUND_IMG_PATH = 'img/sub_screen/background_field.png'  # legacy fallback
SUB_BOX_BACKGROUND_IMG_PATH = 'img/sub_screen/background_dark.png'  # legacy fallback

# Programmatic sub-box background (replaces background_dark.png)
SUB_BOX_BG_CLR = (200, 142, 88, 235)               # warm orange-brown center
SUB_BOX_BG_INNER_CLR = (188, 128, 76, 215)         # slightly deeper for depth
SUB_BOX_BG_BORDER_CLR = (82, 50, 22)               # dark warm brown edge
SUB_BOX_BG_BORDER_W = 2
SUB_BOX_BG_CORNER_R = int(0.006 * SCREEN_HEIGHT)
SUB_BOX_BG_PAD = int(0.004 * SCREEN_HEIGHT)
SUB_BOX_BG_FRAME_W = int(0.007 * SCREEN_HEIGHT)    # dark frame band
SUB_BOX_BG_FRAME_CLR = (105, 62, 28, 240)          # warm dark brown frame
SUB_BOX_BG_FRAME_INNER_CLR = (92, 52, 22, 230)     # darker inner frame edge
SUB_SCREEN_BUTTON_IMG_PATH = 'img/sub_screen/button1.png'
SUB_BOX_SCROLL_BACKGROUND_IMG_PATH = 'img/sub_screen/scroll.png'
SUB_SCREEN_BACKGROUND_COLOR = (40, 40, 40)
SUB_SCREEN_BUTTON_TEXT_COLOR_ACTIVE = (248, 222, 0)  # Bright yellow for active state
SUB_SCREEN_BUTTON_TEXT_COLOR_PASSIVE = (60, 60, 60)  # Light cyan for dark turkis background
SUB_SCREEN_BUTTON_TEXT_COLOR_HOVERED = (255, 255, 255)  # White for hover state
SUB_SCREEN_BACKGROUND_TRANSPARENCY = 200
SUB_SCREEN_BACKGROUND_IMG_WIDTH = int(0.8 * SCREEN_WIDTH)
SUB_SCREEN_BACKGROUND_IMG_HEIGHT = int(0.73 * SCREEN_HEIGHT)

# Programmatic sub-screen background panel
SUB_SCREEN_BG_CLR = (232, 205, 168, 225)            # warm parchment, semi-transparent
SUB_SCREEN_BG_INNER_CLR = (222, 192, 155, 205)     # slightly deeper parchment for depth
SUB_SCREEN_BG_BORDER_CLR = (95, 62, 28)            # dark warm brown outer edge
SUB_SCREEN_BG_BORDER_W = 2
SUB_SCREEN_BG_CORNER_R = int(0.012 * SCREEN_HEIGHT)
SUB_SCREEN_BG_PAD = int(0.005 * SCREEN_HEIGHT)     # inner padding for depth rect
SUB_SCREEN_BG_FRAME_W = int(0.013 * SCREEN_HEIGHT) # decorative frame band
SUB_SCREEN_BG_FRAME_CLR = (148, 105, 56, 240)      # warm brown frame band
SUB_SCREEN_BG_FRAME_INNER_CLR = (125, 85, 42, 230) # slightly darker inner frame edge
SUB_SCREEN_BG_FRAME_EDGE_CLR = (92, 60, 28)        # dark edge line between frame and parchment
SUB_SCREEN_BUTTON_WIDTH = int(0.08 * SCREEN_WIDTH)
SUB_SCREEN_BUTTON_HEIGHT = int(0.035 * SCREEN_HEIGHT)
SUB_SCREEN_BUTTON_DELTA_X = int(0.09 * SCREEN_WIDTH)

SUB_SCREEN_TITLE_COLOR = (250, 221, 0)
SUB_SCREEN_TITLE_BG_COLOR = (62, 40, 22)
SUB_SCREEN_TITLE_BORDER_COLOR = (125, 90, 45)
SUB_SCREEN_TITLE_BORDER_WIDTH = 2
SUB_SCREEN_TITLE_PADDING = max(6, int(0.010 * SCREEN_HEIGHT))
SUB_SCREEN_TITLE_SHADOW_COLOR = (30, 20, 10)
SUB_SCREEN_TITLE_SHADOW_OFFSET = max(2, int(0.003 * SCREEN_HEIGHT))
SUB_SCREEN_TITLE_X = int(0.53 * SCREEN_WIDTH)
SUB_SCREEN_TITLE_Y = int(0.028 * SCREEN_HEIGHT)
SUB_SCREEN_TITLE_FONT_SIZE = int(0.034 * _FS)
SUB_SCREEN_TITLE_CORNER_R = int(0.006 * SCREEN_HEIGHT)


MINI_CARD_WIDTH = int(0.02 * SCREEN_WIDTH * _UI_SCALE)
MINI_CARD_HEIGHT = int(0.04 * SCREEN_HEIGHT * _UI_SCALE)

