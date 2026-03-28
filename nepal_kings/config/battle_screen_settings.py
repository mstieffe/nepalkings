# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Layout settings for the Battle Screen."""

from config.screen_settings import SCREEN_WIDTH, SCREEN_HEIGHT, _FS, _UI_SCALE, _IS_MOBILE
from config.font_settings import FS_DISPLAY, FS_SUBTITLE, FS_HEADING, FS_BODY, FS_SMALL, FS_TINY

# ─────────────────────────── general ───────────────────────────
BATTLE_SCREEN_FILL_COLOR = (106, 58, 24)
BATTLE_SCREEN_BORDER_COLOR = (25, 10, 4)
BATTLE_SCREEN_BORDER_WIDTH = 3
BATTLE_SCREEN_FILL_ALPHA = 200
BATTLE_SCREEN_PANEL_BG_COLOR = (80, 42, 18)
BATTLE_SCREEN_PANEL_BORDER_COLOR = (25, 10, 4)
BATTLE_SCREEN_PANEL_BORDER_WIDTH = 2

# ─────────────────── (1) BATTLE MOVES PANEL (left) ────────────
BATTLE_PANEL_X = int(0.18 * SCREEN_WIDTH)
BATTLE_PANEL_Y = int(0.07 * SCREEN_HEIGHT)
BATTLE_PANEL_W = int(0.10 * SCREEN_WIDTH)
BATTLE_PANEL_H = int(0.62 * SCREEN_HEIGHT)

# Icons inside the panel (3 stacked vertically)
_BPIM = 1.15 if _IS_MOBILE else 1.0   # enlarge battle-panel move icons on mobile
BATTLE_PANEL_ICON_SIZE = int(0.055 * SCREEN_WIDTH * _BPIM)
BATTLE_PANEL_ICON_FRAME_SCALE = 1.3
BATTLE_PANEL_ICON_GLOW_SIZE = int(0.08 * SCREEN_WIDTH * _BPIM)

# Advance overlay icon — slightly bigger on mobile so the charge arrow is visible
ADVANCE_ICON_SCALE = 0.35 if _IS_MOBILE else 0.25
BATTLE_PANEL_ICON_START_Y = int(0.17 * SCREEN_HEIGHT)
BATTLE_PANEL_ICON_DELTA_Y = int(0.14 * SCREEN_HEIGHT)

# Action buttons beside/below each icon
BATTLE_PANEL_BTN_W = int(0.075 * SCREEN_WIDTH)
BATTLE_PANEL_BTN_H = int(0.028 * SCREEN_HEIGHT)
BATTLE_PANEL_BTN_OFFSET_Y = int(0.065 * SCREEN_HEIGHT)  # below icon centre
BATTLE_PANEL_BTN_DELTA_Y = int(0.032 * SCREEN_HEIGHT)   # between buttons

# ─────────────── (2) FIGURES PANEL (centre-left) ──────────────
FIGURES_PANEL_X = int(0.30 * SCREEN_WIDTH)
FIGURES_PANEL_Y = int(0.07 * SCREEN_HEIGHT)
FIGURES_PANEL_W = int(0.14 * SCREEN_WIDTH)
FIGURES_PANEL_H = int(0.62 * SCREEN_HEIGHT)

# Player figure (top half)
FIGURES_PLAYER_Y = int(0.08 * SCREEN_HEIGHT)
# Opponent figure (bottom half)
FIGURES_OPPONENT_Y = int(0.44 * SCREEN_HEIGHT)
# Power difference box (middle)
FIGURES_DIFF_Y = int(0.355 * SCREEN_HEIGHT)
FIGURES_DIFF_W = int(0.08 * SCREEN_WIDTH)
FIGURES_DIFF_H = int(0.045 * SCREEN_HEIGHT)

# ─────────────────── (3) ROUNDS PANEL (centre) ────────────────
ROUNDS_PANEL_X = int(0.46 * SCREEN_WIDTH)
ROUNDS_PANEL_Y = int(0.07 * SCREEN_HEIGHT)
ROUNDS_PANEL_W = int(0.30 * SCREEN_WIDTH)
ROUNDS_PANEL_H = int(0.62 * SCREEN_HEIGHT)

# Round labels ("Round 1", "Round 2", "Round 3")
ROUNDS_LABEL_Y = int(0.09 * SCREEN_HEIGHT)
ROUNDS_LABEL_FONT_SIZE = FS_BODY                        # was int(0.022 * _FS)
ROUNDS_LABEL_COLOR = (220, 200, 180)
ROUNDS_LABEL_ACTIVE_COLOR = (250, 221, 0)

# Slot dimensions (diamond shaped, same as battle shop slots)
ROUNDS_SLOT_SIZE = int(0.06 * SCREEN_WIDTH)
ROUNDS_SLOT_GLOW_SIZE = int(0.09 * SCREEN_WIDTH)
ROUNDS_SLOT_FRAME_SCALE = 1.3

# Player move slots (top row) — 3 slots horizontally
ROUNDS_PLAYER_SLOT_Y = int(0.17 * SCREEN_HEIGHT)
# Difference boxes (middle row)
ROUNDS_DIFF_Y = int(0.355 * SCREEN_HEIGHT)
ROUNDS_DIFF_W = int(0.06 * SCREEN_WIDTH)
ROUNDS_DIFF_H = int(0.04 * SCREEN_HEIGHT)
# Opponent move slots (bottom row)
ROUNDS_OPPONENT_SLOT_Y = int(0.48 * SCREEN_HEIGHT)

# Horizontal spacing for the 3 round columns
ROUNDS_COL_DELTA_X = int(0.095 * SCREEN_WIDTH)

# ────────────── (4) TOTAL SUMMARY CIRCLE (right) ──────────────
TOTAL_CIRCLE_X = int(0.82 * SCREEN_WIDTH)
TOTAL_CIRCLE_Y = int(0.37 * SCREEN_HEIGHT)
TOTAL_CIRCLE_RADIUS = int(0.045 * SCREEN_WIDTH)
TOTAL_CIRCLE_BORDER_W = max(2, int(0.004 * SCREEN_HEIGHT))

# Colors for the total circle
TOTAL_CIRCLE_POSITIVE_COLOR = (60, 180, 60)    # green
TOTAL_CIRCLE_NEGATIVE_COLOR = (200, 60, 60)    # red
TOTAL_CIRCLE_NEUTRAL_COLOR = (160, 160, 160)   # grey
TOTAL_CIRCLE_BG_COLOR = (50, 30, 15)
TOTAL_CIRCLE_BORDER_COLOR = (25, 10, 4)

# ────────────────── TURN INDICATOR ────────────────────────────
TURN_INDICATOR_FONT_SIZE = FS_SMALL                     # was int(0.020 * _FS)
TURN_INDICATOR_X = BATTLE_PANEL_X + BATTLE_PANEL_W // 2
TURN_INDICATOR_Y = BATTLE_PANEL_Y + BATTLE_PANEL_H - int(0.03 * SCREEN_HEIGHT)
TURN_YOUR_COLOR = (250, 221, 0)
TURN_OPPONENT_COLOR = (160, 140, 100)

# ────────────────── FONTS ─────────────────────────────────────
BATTLE_SCREEN_FONT_SIZE = FS_BODY                          # was int(0.022 * _FS)
BATTLE_SCREEN_FONT_SIZE_SMALL = int(FS_SMALL * 0.9)        # was int(0.018 * _FS)  →  0.02 * 0.9 = 0.018
BATTLE_SCREEN_VALUE_FONT_SIZE = int(FS_SUBTITLE * 0.94)    # was int(0.032 * _FS)  →  0.034 * 0.94 ≈ 0.032
BATTLE_SCREEN_DIFF_FONT_SIZE = FS_HEADING                  # was int(0.026 * _FS)
# Total score font — smaller on mobile so it fits inside the circle
_TSM = 0.75 if _IS_MOBILE else 1.0
BATTLE_SCREEN_TOTAL_FONT_SIZE = int(FS_DISPLAY * _TSM)     # was int(0.06 * _FS * _TSM)

# Icon power-value font (the number on move icons) — larger on mobile
_BIM = 1.3 if _IS_MOBILE else 1.0
BATTLE_ICON_VALUE_FONT_SIZE = int(FS_SMALL * 0.9 * _BIM)   # was int(0.018 * _FS * _BIM)  →  0.02 * 0.9 = 0.018

# ─────────────── SLOT VISUAL SETTINGS ─────────────────────────
BATTLE_SLOT_BG_COLOR = (110, 70, 35)
BATTLE_SLOT_BORDER_COLOR = (140, 90, 45)
BATTLE_SLOT_HIGHLIGHT_COLOR = (250, 221, 0, 120)  # semi-transparent gold for current round

# ─────────────── POWER CIRCLES ────────────────────────────────
# Small circles showing per-element power values near figures & slots.
# Player circle sits below the element; opponent circle sits above.
# On mobile, enlarge power circles so values are readable
_PCM = 1.25 if _IS_MOBILE else 1.0
POWER_CIRCLE_RADIUS = int(0.014 * SCREEN_WIDTH * _PCM)    # circle radius
POWER_CIRCLE_BORDER_W = 2
POWER_CIRCLE_BG_COLOR = (50, 30, 15)
POWER_CIRCLE_BORDER_COLOR = (140, 120, 90)
POWER_CIRCLE_FONT_SIZE = int(FS_TINY * _PCM)               # was int(0.017 * _FS * _PCM)
POWER_CIRCLE_TEXT_COLOR = (255, 255, 255)
POWER_CIRCLE_EMPTY_TEXT = "—"                              # shown for unplayed slots
POWER_CIRCLE_EMPTY_COLOR = (120, 100, 80)
# Y positions  (same for figures panel and each round-slot column)
POWER_CIRCLE_PLAYER_Y = int(0.295 * SCREEN_HEIGHT)        # below player element
POWER_CIRCLE_OPPONENT_Y = int(0.455 * SCREEN_HEIGHT)      # above opponent element

# ─────────────── DIFF BOX COLORS ──────────────────────────────
DIFF_POSITIVE_COLOR = (60, 180, 60)
DIFF_NEGATIVE_COLOR = (200, 60, 60)
DIFF_NEUTRAL_COLOR = (160, 160, 160)
DIFF_BOX_BG_COLOR = (50, 30, 15)
DIFF_BOX_BORDER_COLOR = (80, 50, 25)

# ─────────────── FINISH BUTTON ────────────────────────────────
FINISH_BTN_X = int(0.83 * SCREEN_WIDTH)   # centre x
FINISH_BTN_Y = int(0.62 * SCREEN_HEIGHT)  # top y
FINISH_BTN_W = int(0.10 * SCREEN_WIDTH)
FINISH_BTN_H = int(0.045 * SCREEN_HEIGHT)
FINISH_BTN_COLOR = (180, 140, 40)
FINISH_BTN_HOVER_COLOR = (200, 170, 60)
FINISH_BTN_BORDER_COLOR = (250, 221, 0)
FINISH_BTN_TEXT_COLOR = (40, 20, 5)

# ─────────────── BATTLE FIGURE ICON SCALE ─────────────────────
# On mobile, enlarge the figure diamond icons (not the info box below them)
BATTLE_FIGURE_ICON_SCALE = 0.95 if _IS_MOBILE else 1.0
