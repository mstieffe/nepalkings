# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
from config.screen_settings import SCREEN_WIDTH, SCREEN_HEIGHT, _UI_SCALE
from config.font_settings import FS_BODY, FS_HEADING, FS_SUBTITLE

# ── Card grid layout ────────────────────────────────────────────────
COLLECTION_CARD_W         = int(0.052 * SCREEN_WIDTH)
COLLECTION_CARD_H         = int(0.13 * SCREEN_HEIGHT)
COLLECTION_CARD_GAP_X     = int(0.008 * SCREEN_WIDTH)
COLLECTION_CARD_GAP_Y     = int(0.012 * SCREEN_HEIGHT)

# ── Grid panel ──────────────────────────────────────────────────────
COLLECTION_PANEL_X        = int(0.04 * SCREEN_WIDTH)
COLLECTION_PANEL_Y        = int(0.13 * SCREEN_HEIGHT)
COLLECTION_PANEL_W        = int(0.92 * SCREEN_WIDTH)
COLLECTION_PANEL_BOTTOM   = int(0.82 * SCREEN_HEIGHT)
COLLECTION_PANEL_PAD_X    = int(0.015 * SCREEN_WIDTH)
COLLECTION_PANEL_PAD_Y    = int(0.012 * SCREEN_HEIGHT)

# ── Suit label ──────────────────────────────────────────────────────
COLLECTION_SUIT_LABEL_FONT_SIZE = FS_BODY
COLLECTION_SUIT_LABEL_CLR       = (220, 200, 140)
COLLECTION_SUIT_LABEL_W         = int(0.07 * SCREEN_WIDTH)

# ── Badge overlay ───────────────────────────────────────────────────
COLLECTION_BADGE_FONT_SIZE = int(FS_BODY * 0.75)
COLLECTION_BADGE_CLR       = (255, 255, 255)
COLLECTION_BADGE_BG_CLR    = (30, 100, 50, 200)
COLLECTION_BADGE_PAD_X     = int(0.004 * SCREEN_WIDTH)
COLLECTION_BADGE_PAD_Y     = int(0.002 * SCREEN_HEIGHT)

# ── Toggle buttons (Main / Side) ───────────────────────────────────
COLLECTION_TOGGLE_W       = int(0.12 * SCREEN_WIDTH)
COLLECTION_TOGGLE_H       = int(0.04 * SCREEN_HEIGHT)
COLLECTION_TOGGLE_GAP     = int(0.01 * SCREEN_WIDTH)
COLLECTION_TOGGLE_Y       = int(0.07 * SCREEN_HEIGHT)
COLLECTION_TOGGLE_ACTIVE_CLR   = (250, 221, 0)
COLLECTION_TOGGLE_INACTIVE_CLR = (150, 140, 120)
COLLECTION_TOGGLE_BG_CLR       = (40, 40, 45, 200)
COLLECTION_TOGGLE_ACTIVE_BG    = (60, 55, 35, 220)
COLLECTION_TOGGLE_BORDER_CLR   = (180, 160, 130)

# ── Bottom action buttons ──────────────────────────────────────────
COLLECTION_ACTION_BTN_W   = int(0.16 * SCREEN_WIDTH)
COLLECTION_ACTION_BTN_H   = int(0.05 * SCREEN_HEIGHT)
COLLECTION_ACTION_BTN_GAP = int(0.015 * SCREEN_WIDTH)
COLLECTION_ACTION_BTN_Y   = int(0.86 * SCREEN_HEIGHT)
COLLECTION_ACTION_BTN_FONT_SIZE = FS_BODY

# ── Greyed out card overlay ─────────────────────────────────────────
COLLECTION_GREY_ALPHA     = 160

# ── Title ───────────────────────────────────────────────────────────
COLLECTION_TITLE_FONT_SIZE = FS_SUBTITLE
COLLECTION_TITLE_CLR       = (250, 221, 0)
COLLECTION_TITLE_Y         = int(0.02 * SCREEN_HEIGHT)

# ── Sell dialogue ───────────────────────────────────────────────────
COLLECTION_SELL_FONT_SIZE  = FS_BODY

# ── Booster prices (mirror server values for UI display) ────────────
BOOSTER_PACK_PRICE       = 100
BOOSTER_PACK_SIDE_PRICE  = 100
