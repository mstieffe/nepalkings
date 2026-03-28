# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
from config.screen_settings import SCREEN_WIDTH, SCREEN_HEIGHT, SUB_SCREEN_X, SUB_SCREEN_Y, _FS, _UI_SCALE

# ── Colour palette (earthy/parchment theme) ─────────────────────────
GUIDE_SIDEBAR_BG            = (72, 52, 34, 200)       # warm dark brown, matches scroll panel
GUIDE_SIDEBAR_ITEM_HOVER    = (95, 68, 42, 170)       # lighter brown hover
GUIDE_SIDEBAR_ITEM_ACTIVE   = (120, 85, 48, 210)      # warm brown active
GUIDE_CONTENT_BG            = (62, 46, 30, 180)       # warm brown content bg (legible)
GUIDE_SECTION_TITLE_CLR     = (250, 221, 0)            # gold
GUIDE_BODY_TEXT_CLR         = (235, 225, 208)           # warm cream
GUIDE_HEADING_CLR           = (250, 210, 120)           # warm amber for sub-headings
GUIDE_BULLET_CLR            = (200, 170, 100)           # muted gold for bullets
GUIDE_SEPARATOR_CLR         = (130, 95, 50, 130)        # warm brown decorative rule
GUIDE_MENU_TEXT_CLR         = (220, 210, 190)
GUIDE_MENU_TEXT_ACTIVE      = (250, 221, 0)
GUIDE_SCROLLBAR_TRACK       = (95, 68, 42, 140)        # subtle warm brown track
GUIDE_SCROLLBAR_HANDLE_P    = (160, 125, 70)            # muted gold passive
GUIDE_SCROLLBAR_HANDLE_A    = (250, 221, 0)             # bright gold active / dragging
GUIDE_BORDER_CLR            = (120, 85, 42)             # warm brown border (echoes frame)

# ── Font sizes (relative to screen height) ──────────────────────────
GUIDE_SECTION_TITLE_FONT_SIZE = int(_FS * 0.032)
GUIDE_HEADING_FONT_SIZE       = int(_FS * 0.026)
GUIDE_BODY_FONT_SIZE          = int(_FS * 0.022)
GUIDE_MENU_FONT_SIZE          = int(_FS * 0.022)
GUIDE_MENU_FONT_ACTIVE_SIZE   = int(SCREEN_HEIGHT * 0.023)

# ── Layout geometry ─────────────────────────────────────────────────
GUIDE_PAD = int(0.022 * SCREEN_WIDTH)

# Sidebar
GUIDE_SIDEBAR_X     = SUB_SCREEN_X + GUIDE_PAD
GUIDE_SIDEBAR_Y     = SUB_SCREEN_Y + int(0.06 * SCREEN_HEIGHT)
GUIDE_SIDEBAR_W     = int(0.14 * SCREEN_WIDTH)
GUIDE_SIDEBAR_H     = int(0.62 * SCREEN_HEIGHT)
GUIDE_MENU_ITEM_H   = int(0.045 * SCREEN_HEIGHT)
GUIDE_MENU_ITEM_PAD = int(0.006 * SCREEN_HEIGHT)
GUIDE_MENU_TOP_PAD  = int(0.01 * SCREEN_HEIGHT)    # top padding inside sidebar
GUIDE_MENU_TEXT_X    = int(0.012 * SCREEN_WIDTH)   # text inset from item left edge

# Content area
GUIDE_CONTENT_GAP   = int(0.012 * SCREEN_WIDTH)
GUIDE_CONTENT_X     = GUIDE_SIDEBAR_X + GUIDE_SIDEBAR_W + GUIDE_CONTENT_GAP
GUIDE_CONTENT_Y     = GUIDE_SIDEBAR_Y
GUIDE_CONTENT_W     = int(0.58 * SCREEN_WIDTH)
GUIDE_CONTENT_H     = GUIDE_SIDEBAR_H

# Scrollbar
GUIDE_SCROLLBAR_W   = int(0.006 * SCREEN_WIDTH)
GUIDE_SCROLLBAR_GAP = int(0.004 * SCREEN_WIDTH)
GUIDE_SCROLLBAR_X   = GUIDE_CONTENT_X + GUIDE_CONTENT_W + GUIDE_SCROLLBAR_GAP
GUIDE_SCROLLBAR_Y   = GUIDE_CONTENT_Y
GUIDE_SCROLLBAR_H   = GUIDE_CONTENT_H
GUIDE_SCROLLBAR_MIN_HANDLE = 20

# ── Content layout spacing ──────────────────────────────────────────
GUIDE_LINE_SPACING          = int(0.005 * SCREEN_HEIGHT)
GUIDE_PARAGRAPH_SPACING     = int(0.012 * SCREEN_HEIGHT)
GUIDE_HEADING_SPACING_ABOVE = int(0.014 * SCREEN_HEIGHT)
GUIDE_BULLET_INDENT         = int(0.022 * SCREEN_WIDTH)
GUIDE_BULLET_MARKER_GAP     = int(0.008 * SCREEN_WIDTH)
GUIDE_SEPARATOR_V_PAD       = int(0.004 * SCREEN_HEIGHT)
GUIDE_CONTENT_TEXT_X        = int(0.015 * SCREEN_WIDTH)  # text inset inside content area
GUIDE_CONTENT_MARGIN        = int(0.03 * SCREEN_WIDTH)   # left+right margin for wrapping
GUIDE_TITLE_TOP_PAD         = int(0.012 * SCREEN_HEIGHT)
GUIDE_TITLE_BOTTOM_PAD      = int(0.015 * SCREEN_HEIGHT)
GUIDE_BODY_BOTTOM_PAD       = int(0.008 * SCREEN_HEIGHT)

# ── Icon / image settings ──────────────────────────────────────────
GUIDE_ICON_SIZE             = int(0.034 * SCREEN_HEIGHT * _UI_SCALE)     # small inline icon (skills, suits, resources)
GUIDE_ICON_SIZE_LARGE       = int(0.070 * SCREEN_HEIGHT * _UI_SCALE)     # large inline icon (figures, spells, etc.)
GUIDE_ICON_TEXT_GAP         = int(0.010 * SCREEN_WIDTH)      # gap between icon and text
GUIDE_IMAGE_MAX_W           = int(0.50 * SCREEN_WIDTH * _UI_SCALE)       # max width for large images
GUIDE_IMAGE_V_PAD           = int(0.008 * SCREEN_HEIGHT)     # vertical padding around images

# ── Table settings ──────────────────────────────────────────────────
GUIDE_TABLE_ROW_H           = int(0.040 * SCREEN_HEIGHT * _UI_SCALE)     # row height (small icons)
GUIDE_TABLE_ROW_H_LARGE     = int(0.075 * SCREEN_HEIGHT * _UI_SCALE)     # row height (large icons)
GUIDE_TABLE_HEADER_CLR      = (250, 210, 120)                # warm amber header text
GUIDE_TABLE_CELL_CLR        = (235, 225, 208)                # warm cream cell text
GUIDE_TABLE_ROW_BG_ALT      = (255, 255, 255, 18)            # subtle zebra stripe
GUIDE_TABLE_BORDER_CLR      = (158, 81, 33, 80)              # faint table lines
GUIDE_TABLE_ICON_SIZE       = int(0.030 * SCREEN_HEIGHT * _UI_SCALE)     # small icons inside table cells
GUIDE_TABLE_ICON_SIZE_LARGE = int(0.060 * SCREEN_HEIGHT * _UI_SCALE)     # large icons inside table cells
GUIDE_TABLE_COL_PAD         = int(0.008 * SCREEN_WIDTH)      # padding between columns
GUIDE_TABLE_FONT_SIZE       = int(_FS * 0.020)     # slightly smaller for tables

# ── Scroll speed ────────────────────────────────────────────────────
GUIDE_SCROLL_SPEED = int(0.035 * SCREEN_HEIGHT)
