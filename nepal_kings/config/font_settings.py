# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
from config.screen_settings import SCREEN_HEIGHT, _FS, _IS_MOBILE

import pygame

# ── Font Size Groups ──────────────────────────────────────────────────────────
# Adjust these shared bases to scale whole categories of related text together.
# All font size constants across all config files derive from one of these groups.
FS_DISPLAY  = int(0.060 * _FS)  # Large decorative display  (e.g. battle total score circle)
FS_TITLE    = int(0.040 * _FS)  # Primary titles and large action/input buttons
FS_SUBTITLE = int(0.036 * _FS)  # Sub-screen/dialogue titles and section headlines
FS_HEADING  = int(0.034 * _FS)  # Column/section headings, scroll headers, guide headings
FS_BODY     = int(0.030 * _FS)  # Body text — labels, list items, messages, round labels
FS_BUTTON   = int(0.030 * _FS)  # Standard game/confirm/sub-screen button labels
FS_SMALL    = int(0.026 * _FS)  # Small text — icon captions, turn indicator, mini scroll
FS_TINY     = int(0.026 * _FS)  # Fine detail — tooltips, power circles, scoreboard sub-labels

# Legibility floor: the smallest canvas-px size that stays readable after the
# mobile canvas is CSS-downscaled (~0.78x on small phones — 15 canvas px is
# only ~12 CSS px there). Every conquer tier below floors on this instead of
# the old, always-dead max(7..10, ...) guards. Desktop keeps a lower floor;
# its formulas already exceed it.
FS_FLOOR    = max(15, int(0.016 * _FS)) if _IS_MOBILE else max(12, int(0.016 * _FS))

# ── Conquer battle semantic tiers ────────────────────────────────────────────
# The conquer screen previously derived ~40 ad-hoc sizes from FS_TINY with
# 0.50–0.95 multipliers, landing below legibility on the mobile canvas. All
# conquer battle text maps onto these four roles instead. The FS_FLOOR
# multiples carry mobile (where the 0.0xx*_FS terms are small); the
# percentage terms carry desktop unchanged.
FS_CONQUER_PRIMARY   = max(int(FS_FLOOR * 2.2), int(0.046 * _FS))     # fighter totals, diff value
FS_CONQUER_SECONDARY = max(int(FS_FLOOR * 1.6), int(0.030 * _FS))     # chip values, power numbers
FS_CONQUER_LABEL     = max(int(FS_FLOOR * 1.3), int(0.020 * _FS))     # names, captions, R#
FS_CONQUER_META      = FS_FLOOR                                       # sources, fine print

# ── Legacy aliases (keep existing constant names mapped to groups) ────────────
FONT_PATH               = None
FONT_SIZE               = FS_DISPLAY   # hero/large display font
FONT_SIZE_DETAIL        = FS_BUTTON    # detail text in cards, spell selector
FONT_SIZE_BUTTON        = FS_TITLE     # primary action buttons (login, register)
FONT_SIZE_SUBSCREEN_BUTTON = FS_BUTTON # sub-screen tab buttons
LOGOUT_FONT_SIZE        = FS_TITLE     # logout/navigation buttons

# ── Global font cache ──────────────────────────────────────────────
# pygame.font.Font() keeps an open file descriptor per instance.
# Caching by (path, size) reduces ~200 FDs to ~20 unique sizes.
_font_cache = {}

def get_font(size, bold=False):
    """Return a cached pygame.font.Font for FONT_PATH at the given size."""
    key = (FONT_PATH, size, bold)
    font = _font_cache.get(key)
    if font is None:
        font = pygame.font.Font(FONT_PATH, size)
        if bold:
            font.set_bold(True)
        _font_cache[key] = font
    return font

# Timings
MESSAGE_DURATION = 5000
