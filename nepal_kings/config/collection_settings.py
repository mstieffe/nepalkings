# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
from config.screen_settings import SCREEN_WIDTH, SCREEN_HEIGHT, _UI_SCALE, _IS_MOBILE
from config.font_settings import FS_BODY, FS_HEADING, FS_SUBTITLE

# ── Card grid layout ────────────────────────────────────────────────
COLLECTION_CARD_W         = int(0.05 * SCREEN_WIDTH)
COLLECTION_CARD_H         = int((0.113 if _IS_MOBILE else 0.120) * SCREEN_HEIGHT)
COLLECTION_CARD_GAP_X     = int(0.007 * SCREEN_WIDTH)
COLLECTION_CARD_GAP_Y     = int((0.006 if _IS_MOBILE else 0.010) * SCREEN_HEIGHT)

# ── Grid panel ──────────────────────────────────────────────────────
COLLECTION_PANEL_X        = int(0.04 * SCREEN_WIDTH)
COLLECTION_PANEL_Y        = int(0.13 * SCREEN_HEIGHT)
COLLECTION_PANEL_W        = int(0.88 * SCREEN_WIDTH)
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
COLLECTION_LOCK_BADGE_CLR  = (255, 240, 205)
COLLECTION_LOCK_BADGE_BG_CLR = (126, 82, 28, 225)
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

# ── Booster / rarity tiers ─────────────────────────────────────────
COLLECTION_TIER_LABELS = {
    1: 'Common',
    2: 'Uncommon',
    3: 'Rare',
}
# Keep these in sync with server BOOSTER_TIER_RANKS / BOOSTER_SIDE_TIER_RANKS.
COLLECTION_TIER_MAIN_RANKS = {
    1: ('7', '8', '9'),
    2: ('J', '10', 'A'),
    3: ('K', 'Q'),
}
COLLECTION_TIER_SIDE_RANKS = {
    1: ('2', '3'),
    2: ('4', '5'),
    3: ('6',),
}
COLLECTION_MAIN_RANK_TO_TIER = {
    rank: tier
    for tier, ranks in COLLECTION_TIER_MAIN_RANKS.items()
    for rank in ranks
}
COLLECTION_SIDE_RANK_TO_TIER = {
    rank: tier
    for tier, ranks in COLLECTION_TIER_SIDE_RANKS.items()
    for rank in ranks
}
COLLECTION_TIER_COLORS = {
    1: (190, 190, 190),
    2: (255, 173, 78),
    3: (252, 224, 82),
}
COLLECTION_TIER_BORDER_COLORS = {
    1: (180, 180, 180, 130),
    2: (255, 156, 64, 175),
    3: (252, 224, 82, 215),
}
COLLECTION_TIER_GLOW_TINTS = {
    1: (210, 210, 210, 245),
    2: (255, 150, 55, 250),
    3: (255, 232, 74, 255),
}

# ── Collection summary / pack panels ───────────────────────────────
COLLECTION_STATS_STRIP_H = int(0.046 * SCREEN_HEIGHT)
COLLECTION_STATS_FONT_SIZE = int(FS_BODY * 0.82)
COLLECTION_STATS_BG_CLR = (24, 24, 30, 185)
COLLECTION_STATS_BORDER_CLR = (118, 105, 78, 185)
COLLECTION_STATS_TEXT_CLR = (225, 214, 184)
COLLECTION_STATS_VALUE_CLR = (250, 221, 0)

COLLECTION_PACK_PANEL_H = int(0.102 * SCREEN_HEIGHT)
COLLECTION_PACK_PANEL_GAP = int(0.020 * SCREEN_WIDTH)
COLLECTION_PACK_PANEL_PAD_X = int(0.010 * SCREEN_WIDTH)
COLLECTION_PACK_PANEL_PAD_Y = int(0.010 * SCREEN_HEIGHT)
COLLECTION_PACK_PANEL_BG_CLR = (24, 24, 30, 198)
COLLECTION_PACK_PANEL_BORDER_CLR = (132, 116, 83, 205)
COLLECTION_PACK_PANEL_TITLE_CLR = (250, 221, 0)
COLLECTION_PACK_PANEL_TEXT_CLR = (218, 205, 172)
COLLECTION_PACK_PANEL_MUTED_CLR = (150, 140, 118)
COLLECTION_PACK_PANEL_BTN_W = int(0.108 * SCREEN_WIDTH)
COLLECTION_PACK_PANEL_BTN_H = int(0.036 * SCREEN_HEIGHT)
COLLECTION_PACK_PANEL_BTN_GAP = int(0.010 * SCREEN_WIDTH)
COLLECTION_PACK_PANEL_TITLE_FONT_SIZE = FS_BODY
COLLECTION_PACK_PANEL_DETAIL_FONT_SIZE = int(FS_BODY * 0.72)

COLLECTION_PACK_PREVIEWS = {
    'main': {
        'title': 'Main Pack',
    },
    'side': {
        'title': 'Side Pack',
    },
}

# ── Card-details panel (3rd panel beside the booster panels) ───────
# Selling and conversion live inside the selected card profile, so ordinary
# collection browsing always remains the safe/default interaction.
COLLECTION_ACTIONS_PANEL_TITLE = 'Card Details'
COLLECTION_ACTIONS_PANEL_HINT = 'Tap a card to inspect'

# ── Card-to-card conversion (mirror server values) ──────────────────
COLLECTION_CONVERT_RATIO_SAME_COLOR = 2
COLLECTION_CONVERT_RATIO_DIFF_COLOR = 4
COLLECTION_RED_SUITS = ('Hearts', 'Diamonds')
COLLECTION_BLACK_SUITS = ('Clubs', 'Spades')

# ── Trade dialogue layout ───────────────────────────────────────────
COLLECTION_TRADE_TARGET_BTN_W = int(0.090 * SCREEN_WIDTH)
COLLECTION_TRADE_TARGET_BTN_H = int(0.044 * SCREEN_HEIGHT)
COLLECTION_TRADE_TARGET_GAP   = int(0.008 * SCREEN_WIDTH)
COLLECTION_TRADE_TARGET_FONT_SIZE = int(FS_BODY * 0.85)
COLLECTION_TRADE_RED_CLR   = (235, 96, 96)
COLLECTION_TRADE_BLACK_CLR = (190, 190, 200)

# ── Card profile dialogue ───────────────────────────────────────────
COLLECTION_PROFILE_GROUP_MAX_ITEMS = 12

# ── Sell quantity controls ─────────────────────────────────────────
COLLECTION_SELL_QTY_BTN_W = int(0.036 * SCREEN_WIDTH)
COLLECTION_SELL_QTY_BTN_H = int(0.032 * SCREEN_HEIGHT)
COLLECTION_SELL_QTY_MAX_W = int(0.054 * SCREEN_WIDTH)
COLLECTION_SELL_QTY_GAP = int(0.006 * SCREEN_WIDTH)

# ── Greyed out card overlay ─────────────────────────────────────────
COLLECTION_GREY_ALPHA     = 160

# ── Title ───────────────────────────────────────────────────────────
COLLECTION_TITLE_FONT_SIZE = FS_SUBTITLE
COLLECTION_TITLE_CLR       = (250, 221, 0)
COLLECTION_TITLE_Y         = int(0.02 * SCREEN_HEIGHT)

# ── Sell dialogue ───────────────────────────────────────────────────
COLLECTION_SELL_FONT_SIZE  = FS_BODY

# ── Booster reveal overlay ─────────────────────────────────────────
COLLECTION_REVEAL_FLIP_MS = 420
COLLECTION_REVEAL_RARE_PULSE_MS = 900
COLLECTION_REVEAL_TIER_LABEL_FONT_SIZE = int(FS_BODY * 0.82)
COLLECTION_RECENT_GAIN_HIGHLIGHT_MS = 1800

# ── Booster prices (mirror server values for UI display) ────────────
BOOSTER_PACK_PRICE       = 100
BOOSTER_PACK_SIDE_PRICE  = 100
