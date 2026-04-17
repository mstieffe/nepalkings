# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Kingdom / hex-map visual settings."""

import math
from config.screen_settings import SCREEN_WIDTH, SCREEN_HEIGHT, _FS, _UI_SCALE
from config.font_settings import FS_TITLE, FS_SUBTITLE, FS_HEADING, FS_BODY, FS_SMALL, FS_TINY

# ── Hex geometry ────────────────────────────────────────────────────
HEX_SIZE            = int(0.055 * SCREEN_HEIGHT)      # "radius" of flat-top hex
HEX_WIDTH           = HEX_SIZE * 2
HEX_HEIGHT          = int(HEX_SIZE * math.sqrt(3))
HEX_BORDER_W        = max(2, int(0.002 * SCREEN_HEIGHT))

# ── Hex colours (by tier) ──────────────────────────────────────────
HEX_TIER_FILL = {
    1: (110, 140, 90),        # green — common
    2: (140, 130, 80),        # gold-ish — uncommon
    3: (130, 85, 110),        # purple-ish — rare
}
HEX_TIER_BORDER = {
    1: (75, 100, 60),
    2: (105, 95, 55),
    3: (95, 55, 80),
}
HEX_EMPTY_BORDER    = (90, 90, 90)         # unclaimed border
HEX_MINE_BORDER     = (250, 221, 0)        # gold border for own lands
HEX_HOVER_BRIGHTEN  = 35                   # added to each RGB channel on hover
HEX_SELECT_BORDER   = (255, 255, 255)      # white border for selected hex

# ── Owner colouring ────────────────────────────────────────────────
HEX_OWNER_ALPHA     = 110                  # overlay alpha for owner tint

# ── Camera / viewport ──────────────────────────────────────────────
HEX_MAP_ZOOM_MIN    = 0.5
HEX_MAP_ZOOM_MAX    = 3.0
HEX_MAP_ZOOM_STEP   = 0.15
HEX_MAP_DRAG_THRESHOLD = 5                 # px before drag starts

# ── Minimap ─────────────────────────────────────────────────────────
MINIMAP_W           = int(0.12 * SCREEN_WIDTH)
MINIMAP_H           = int(0.11 * SCREEN_HEIGHT)
MINIMAP_MARGIN      = int(0.015 * SCREEN_HEIGHT)
MINIMAP_BG_CLR      = (20, 20, 20, 180)
MINIMAP_BORDER_CLR  = (180, 160, 130)
MINIMAP_BORDER_W    = 1
MINIMAP_VIEWPORT_CLR = (255, 255, 255, 120)

# ── Info panel (top of screen) ──────────────────────────────────────
KINGDOM_INFO_FONT_SIZE  = FS_BODY
KINGDOM_INFO_CLR        = (250, 221, 0)
KINGDOM_INFO_BG_CLR     = (20, 20, 20, 140)
KINGDOM_INFO_PAD_X      = int(0.012 * SCREEN_WIDTH)
KINGDOM_INFO_PAD_Y      = int(0.008 * SCREEN_HEIGHT)

# ── Hex labels ──────────────────────────────────────────────────────
HEX_LABEL_FONT_SIZE     = FS_TINY
HEX_ICON_SIZE           = int(0.022 * SCREEN_HEIGHT)

# ── Land detail box ────────────────────────────────────────────────
LAND_DETAIL_W           = int(0.28 * SCREEN_WIDTH)
LAND_DETAIL_PAD         = int(0.018 * SCREEN_HEIGHT)
LAND_DETAIL_BG_CLR      = (30, 25, 20, 230)
LAND_DETAIL_BORDER_CLR  = (180, 160, 130)
LAND_DETAIL_BORDER_W    = 2
LAND_DETAIL_CORNER_R    = int(0.008 * SCREEN_HEIGHT)
LAND_DETAIL_TITLE_FONT  = FS_SUBTITLE
LAND_DETAIL_BODY_FONT   = FS_BODY
LAND_DETAIL_SMALL_FONT  = FS_SMALL
LAND_DETAIL_TITLE_CLR   = (250, 221, 0)
LAND_DETAIL_TEXT_CLR     = (220, 210, 195)
LAND_DETAIL_DIM_CLR      = (140, 130, 120)
LAND_DETAIL_BTN_W       = int(0.18 * SCREEN_WIDTH)
LAND_DETAIL_BTN_H       = int(0.045 * SCREEN_HEIGHT)

# ── Suit icon paths (reused from card settings) ────────────────────
SUIT_ICON_PATHS = {
    'Hearts':   'img/suits/hearts.png',
    'Diamonds': 'img/suits/diamonds.png',
    'Clubs':    'img/suits/clubs.png',
    'Spades':   'img/suits/spades.png',
}

# ── Tier star labels ────────────────────────────────────────────────
TIER_LABELS = {1: '\u2605', 2: '\u2605\u2605', 3: '\u2605\u2605\u2605'}

# ── Navigation buttons ─────────────────────────────────────────────
NAV_BTN_SIZE        = int(0.04 * SCREEN_HEIGHT)
NAV_BTN_MARGIN      = int(0.012 * SCREEN_HEIGHT)
NAV_BTN_BG_CLR      = (40, 35, 30, 200)
NAV_BTN_BORDER_CLR  = (160, 140, 110)
NAV_BTN_TEXT_CLR    = (220, 210, 195)
NAV_BTN_HOVER_CLR   = (250, 221, 0)
