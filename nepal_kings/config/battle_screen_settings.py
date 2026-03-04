"""Layout settings for the Battle Screen."""

from config.screen_settings import SCREEN_WIDTH, SCREEN_HEIGHT

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
BATTLE_PANEL_ICON_SIZE = int(0.055 * SCREEN_WIDTH)
BATTLE_PANEL_ICON_FRAME_SCALE = 1.3
BATTLE_PANEL_ICON_GLOW_SIZE = int(0.08 * SCREEN_WIDTH)
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
ROUNDS_LABEL_FONT_SIZE = int(0.022 * SCREEN_HEIGHT)
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
TOTAL_CIRCLE_Y = int(0.34 * SCREEN_HEIGHT)
TOTAL_CIRCLE_RADIUS = int(0.045 * SCREEN_WIDTH)
TOTAL_CIRCLE_BORDER_W = 4

# Colors for the total circle
TOTAL_CIRCLE_POSITIVE_COLOR = (60, 180, 60)    # green
TOTAL_CIRCLE_NEGATIVE_COLOR = (200, 60, 60)    # red
TOTAL_CIRCLE_NEUTRAL_COLOR = (160, 160, 160)   # grey
TOTAL_CIRCLE_BG_COLOR = (50, 30, 15)
TOTAL_CIRCLE_BORDER_COLOR = (25, 10, 4)

# ────────────────── TURN INDICATOR ────────────────────────────
TURN_INDICATOR_FONT_SIZE = int(0.026 * SCREEN_HEIGHT)
TURN_INDICATOR_X = int(0.55 * SCREEN_WIDTH)
TURN_INDICATOR_Y = int(0.64 * SCREEN_HEIGHT)
TURN_YOUR_COLOR = (250, 221, 0)
TURN_OPPONENT_COLOR = (160, 140, 100)

# ────────────────── FONTS ─────────────────────────────────────
BATTLE_SCREEN_FONT_SIZE = int(0.022 * SCREEN_HEIGHT)
BATTLE_SCREEN_FONT_SIZE_SMALL = int(0.018 * SCREEN_HEIGHT)
BATTLE_SCREEN_VALUE_FONT_SIZE = int(0.032 * SCREEN_HEIGHT)
BATTLE_SCREEN_DIFF_FONT_SIZE = int(0.026 * SCREEN_HEIGHT)
BATTLE_SCREEN_TOTAL_FONT_SIZE = int(0.06 * SCREEN_HEIGHT)

# ─────────────── SLOT VISUAL SETTINGS ─────────────────────────
BATTLE_SLOT_BG_COLOR = (110, 70, 35)
BATTLE_SLOT_BORDER_COLOR = (140, 90, 45)
BATTLE_SLOT_HIGHLIGHT_COLOR = (250, 221, 0, 120)  # semi-transparent gold for current round

# ─────────────── POWER CIRCLES ────────────────────────────────
# Small circles showing per-element power values near figures & slots.
# Player circle sits below the element; opponent circle sits above.
POWER_CIRCLE_RADIUS = int(0.014 * SCREEN_WIDTH)          # circle radius
POWER_CIRCLE_BORDER_W = 2
POWER_CIRCLE_BG_COLOR = (50, 30, 15)
POWER_CIRCLE_BORDER_COLOR = (140, 120, 90)
POWER_CIRCLE_FONT_SIZE = int(0.017 * SCREEN_HEIGHT)
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
