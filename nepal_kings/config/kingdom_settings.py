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

# ── Hex colours ────────────────────────────────────────────────────
HEX_TIER_FILL = {
    1: (110, 140, 90),        # green — common
    2: (140, 130, 80),        # gold-ish — uncommon
    3: (130, 85, 110),        # purple-ish — rare
    4: (170, 60, 70),         # crimson — apex
}
HEX_TIER_BORDER = {
    1: (75, 100, 60),
    2: (105, 95, 55),
    3: (95, 55, 80),
    4: (120, 36, 44),
}
HEX_EMPTY_BORDER    = (90, 90, 90)         # unclaimed border
HEX_MINE_BORDER     = (250, 221, 0)        # gold border for own lands
HEX_HOVER_BRIGHTEN  = 35                   # added to each RGB channel on hover
HEX_SELECT_BORDER   = (255, 255, 255)      # white border for selected hex

# Suit-bonus semantic colours.  Hearts/Diamonds are green; Spades/Clubs are
# blue; neutral lands (no suit bonus) are grey.  Tier controls shade: light
# for tier 1, darker for the apex tier.
HEX_SUIT_TIER_FILL = {
    'green': {
        1: (112, 178, 118),
        2: (64, 135, 78),
        3: (28, 88, 46),
        4: (12, 60, 28),
    },
    'blue': {
        1: (104, 162, 206),
        2: (56, 116, 162),
        3: (24, 72, 116),
        4: (12, 46, 80),
    },
    'neutral': {
        1: (165, 165, 165),
        2: (130, 130, 130),
        3: (95, 95, 95),
    },
}
HEX_SUIT_TIER_BORDER = {
    'green': {
        1: (76, 124, 80),
        2: (42, 94, 54),
        3: (18, 58, 32),
        4: (8, 38, 18),
    },
    'blue': {
        1: (72, 112, 146),
        2: (36, 78, 112),
        3: (16, 46, 78),
        4: (8, 28, 52),
    },
    'neutral': {
        1: (110, 110, 110),
        2: (85, 85, 85),
        3: (60, 60, 60),
    },
}
HEX_STAR_FILL       = (255, 222, 78)
HEX_STAR_BORDER     = (100, 70, 20)
HEX_MINE_GLOW_CLR   = (255, 223, 80, 90)
HEX_MINE_GLOW_SOFT_CLR = (255, 210, 70, 45)
HEX_MINE_BADGE_BG   = (80, 55, 10, 220)
HEX_MINE_BADGE_CLR  = (255, 238, 150)
HEX_MINE_BORDER_OUTER = (112, 78, 20)
HEX_MINE_BORDER_HIGHLIGHT = (255, 246, 196)

# ── Kingdom cosmetic render presets ───────────────────────────────
HEX_DEFAULT_OWNER_STYLE = {
    'flag_key': 'flag_plain',
    'border_key': 'border_simple_gold',
    'surface_key': 'surface_plain',
}

HEX_FLAG_STYLES = {
    'flag_plain': {
        'pole': (150, 120, 72),
        'fill': (230, 214, 158),
        'accent': (116, 86, 46),
        'shape': 'pennant',
    },
    'flag_crimson': {
        'pole': (178, 136, 74),
        'fill': (176, 42, 48),
        'accent': (255, 224, 128),
        'shape': 'banner',
    },
    'flag_sun': {
        'pole': (200, 150, 70),
        'fill': (245, 181, 46),
        'accent': (110, 55, 18),
        'shape': 'swallowtail',
    },
    'flag_raven': {
        'pole': (142, 132, 122),
        'fill': (34, 36, 46),
        'accent': (176, 188, 210),
        'shape': 'banner',
    },
    'flag_lotus': {
        'pole': (184, 126, 92),
        'fill': (232, 104, 164),
        'accent': (255, 228, 242),
        'shape': 'pennant',
    },
    'flag_mountain': {
        'pole': (156, 120, 78),
        'fill': (80, 120, 154),
        'accent': (240, 246, 255),
        'shape': 'swallowtail',
    },
}

HEX_BORDER_SKINS = {
    'border_simple_gold': {
        'outer': (112, 78, 20),
        'main': (250, 221, 0),
        'highlight': (255, 246, 196),
        'width_bonus': 0,
    },
    'border_royal_blue': {
        'outer': (18, 46, 100),
        'main': (84, 150, 255),
        'highlight': (210, 232, 255),
        'width_bonus': 1,
    },
    'border_emerald_carved': {
        'outer': (10, 66, 42),
        'main': (58, 220, 128),
        'highlight': (212, 255, 225),
        'width_bonus': 1,
    },
    'border_obsidian': {
        'outer': (8, 8, 12),
        'main': (52, 54, 68),
        'highlight': (176, 176, 194),
        'width_bonus': 1,
    },
    'border_ruby': {
        'outer': (80, 8, 18),
        'main': (224, 46, 70),
        'highlight': (255, 205, 215),
        'width_bonus': 2,
    },
    'border_silver': {
        'outer': (86, 92, 100),
        'main': (206, 216, 226),
        'highlight': (255, 255, 255),
        'width_bonus': 0,
    },
}

HEX_SURFACE_SKINS = {
    'surface_plain': {
        'overlay': None,
        'pattern': None,
    },
    'surface_parchment': {
        'overlay': (255, 231, 175, 34),
        'pattern': 'speckles',
        'pattern_clr': (95, 70, 35, 44),
    },
    'surface_stone': {
        'overlay': (215, 218, 210, 30),
        'pattern': 'stone_lines',
        'pattern_clr': (25, 28, 30, 46),
    },
    'surface_snow': {
        'overlay': (232, 244, 255, 38),
        'pattern': 'speckles',
        'pattern_clr': (210, 230, 250, 62),
    },
    'surface_forest': {
        'overlay': (56, 130, 76, 38),
        'pattern': 'speckles',
        'pattern_clr': (18, 72, 38, 58),
    },
    'surface_dusk': {
        'overlay': (86, 64, 130, 42),
        'pattern': 'stone_lines',
        'pattern_clr': (18, 12, 38, 58),
    },
}

# ── Owner colouring ────────────────────────────────────────────────
HEX_OWNER_ALPHA     = 110                  # overlay alpha for owner tint

# ── Camera / viewport ──────────────────────────────────────────────
HEX_MAP_ZOOM_MIN    = 0.25
HEX_MAP_ZOOM_MAX    = 4.0
HEX_MAP_ZOOM_STEP   = 0.50
HEX_MAP_DRAG_THRESHOLD = 5                 # px before drag starts
# Hide tier stars / gold / suit bonus at full zoom-out; show after one zoom-in.
HEX_MAP_LAND_INFO_MIN_ZOOM = 2.0

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

# ── Kingdom map frame / activity panel ─────────────────────────────
KINGDOM_PANEL_GAP       = int(0.014 * SCREEN_WIDTH)
KINGDOM_HEADER_H        = int(0.105 * SCREEN_HEIGHT)
KINGDOM_ACTIVITY_W      = int(0.215 * SCREEN_WIDTH)
KINGDOM_MAP_FRAME_PAD   = int(0.010 * SCREEN_HEIGHT)
KINGDOM_MAP_FRAME_BG    = (18, 16, 13, 135)
KINGDOM_MAP_FRAME_BORDER = (166, 142, 96)
KINGDOM_MAP_FRAME_BORDER_W = 2
KINGDOM_ACTIVITY_BG     = (22, 20, 28, 205)
KINGDOM_ACTIVITY_BORDER = (160, 150, 180)
KINGDOM_ACTIVITY_TAB_BG = (46, 43, 58, 220)
KINGDOM_ACTIVITY_TAB_ACTIVE_BG = (80, 72, 102, 235)
KINGDOM_ACTIVITY_ROW_BG = (36, 34, 45, 175)
KINGDOM_ACTIVITY_ROW_H  = int(0.072 * SCREEN_HEIGHT)
KINGDOM_ACTIVITY_TEXT_CLR = (222, 218, 205)
KINGDOM_ACTIVITY_DIM_CLR = (155, 148, 135)
KINGDOM_ACTIVITY_GOOD_CLR = (130, 215, 135)
KINGDOM_ACTIVITY_BAD_CLR = (230, 120, 105)

# ── Kingdom config / skills icons ─────────────────────────────────
# These are deliberately client-configured so future custom artwork can be
# swapped in without changing the kingdom skill logic.
KINGDOM_SHIELD_ICON_PATH = 'img/battle/icons/block.png'
KINGDOM_SKILL_ICON_PATHS = {
    'gold_production': 'img/dialogue_box/icons/gold.png',
    'gold_vault': 'img/dialogue_box/icons/coins.png',
    'shield_cost_reduction': 'img/resource_icons/shield.png',
    'core_protection': 'img/battle/icons/block.png',
}

# ── Kingdom level / XP / vault UI constants ───────────────────────
KINGDOM_LEVEL_HEADER_FONT_SIZE = FS_HEADING
KINGDOM_LEVEL_HEADER_CLR       = (242, 222, 156)
KINGDOM_XP_BAR_H               = max(8, int(0.011 * SCREEN_HEIGHT))
KINGDOM_XP_BAR_TRACK_CLR       = (52, 48, 60)
KINGDOM_XP_BAR_FILL_CLR        = (104, 196, 232)
KINGDOM_XP_BAR_BORDER_CLR      = (172, 152, 102)
KINGDOM_XP_BAR_TEXT_CLR        = (226, 218, 204)

KINGDOM_VAULT_BAR_H            = max(10, int(0.014 * SCREEN_HEIGHT))
KINGDOM_VAULT_BAR_TRACK_CLR    = (40, 36, 28)
KINGDOM_VAULT_BAR_FILL_CLR     = (240, 200, 80)
KINGDOM_VAULT_BAR_NEAR_CLR     = (236, 156, 60)   # ≥80%
KINGDOM_VAULT_BAR_FULL_CLR     = (224, 92, 76)    # at cap
KINGDOM_VAULT_BAR_BORDER_CLR   = (172, 152, 102)
KINGDOM_VAULT_NEAR_FULL_RATIO  = 0.80

# Floating "+amount" collect text
COLLECT_FLOAT_DURATION_MS      = 900
COLLECT_FLOAT_RISE_PX          = int(0.07 * SCREEN_HEIGHT)
COLLECT_FLOAT_FONT_SIZE        = FS_HEADING
COLLECT_FLOAT_GOLD_CLR         = (250, 224, 110)
COLLECT_FLOAT_XP_CLR           = (132, 210, 244)
COLLECT_FLOAT_LEVEL_CLR        = (250, 196, 92)
COLLECT_FLOAT_STAGGER_MS       = 80

# ── Kingdom config screen layout ──────────────────────────────────
KINGDOM_CONFIG_MARGIN = int(0.035 * SCREEN_WIDTH)
KINGDOM_CONFIG_TOP = int(0.105 * SCREEN_HEIGHT)
KINGDOM_CONFIG_PANEL_GAP = int(0.018 * SCREEN_WIDTH)
KINGDOM_CONFIG_LEFT_W = int(0.39 * SCREEN_WIDTH)
KINGDOM_CONFIG_CARD_H = int(0.155 * SCREEN_HEIGHT)
KINGDOM_CONFIG_SHIELD_H = int(0.17 * SCREEN_HEIGHT)
KINGDOM_CONFIG_SKILL_ROW_H = int(0.105 * SCREEN_HEIGHT)
KINGDOM_CONFIG_PANEL_BG = (24, 21, 28, 225)
KINGDOM_CONFIG_PANEL_BORDER = (176, 154, 108)
KINGDOM_CONFIG_CARD_BG = (38, 34, 46, 220)
KINGDOM_CONFIG_CARD_ACTIVE_BG = (62, 54, 76, 235)
KINGDOM_CONFIG_TEXT_CLR = (226, 218, 204)
KINGDOM_CONFIG_DIM_CLR = (156, 146, 132)
KINGDOM_CONFIG_HIGHLIGHT = (232, 190, 104)
KINGDOM_CONFIG_GOOD_CLR = (132, 220, 142)
KINGDOM_CONFIG_BAD_CLR = (226, 112, 96)

# ── Hex labels ──────────────────────────────────────────────────────
HEX_LABEL_FONT_SIZE     = FS_TINY
HEX_ICON_SIZE           = int(0.022 * SCREEN_HEIGHT)
HEX_GOLD_ICON_PATH      = 'img/dialogue_box/icons/coin.png'

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
TIER_LABELS = {
    1: '\u2605',
    2: '\u2605\u2605',
    3: '\u2605\u2605\u2605',
    4: '\u2605\u2605\u2605\u2605',
}

# ── Navigation buttons ─────────────────────────────────────────────
NAV_BTN_SIZE        = int(0.04 * SCREEN_HEIGHT)
NAV_BTN_MARGIN      = int(0.012 * SCREEN_HEIGHT)
NAV_BTN_BG_CLR      = (40, 35, 30, 200)
NAV_BTN_BORDER_CLR  = (160, 140, 110)
NAV_BTN_TEXT_CLR    = (220, 210, 195)
NAV_BTN_HOVER_CLR   = (250, 221, 0)
