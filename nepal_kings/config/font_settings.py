# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
from config.screen_settings import SCREEN_HEIGHT, _FS, _IS_MOBILE

import pygame

# ── Font Size Groups ──────────────────────────────────────────────────────────
# Adjust these shared bases to scale whole categories of related text together.
# All font size constants across all config files derive from one of these groups.
#
# Mobile canvases are rendered larger than their CSS footprint.  The previous
# 1.6x UI scale kept headings readable, but 0.026-0.030 detail/body text still
# landed around 9-12 CSS px on smaller phones.  Give the text-heavy tiers a
# modest mobile-only lift while preserving the established desktop layout.
FS_DISPLAY  = int(0.060 * _FS)  # Large decorative display  (e.g. battle total score circle)
FS_TITLE    = int((0.043 if _IS_MOBILE else 0.040) * _FS)
FS_SUBTITLE = int((0.040 if _IS_MOBILE else 0.036) * _FS)
FS_HEADING  = int((0.037 if _IS_MOBILE else 0.034) * _FS)
FS_BODY     = int((0.034 if _IS_MOBILE else 0.030) * _FS)
FS_BUTTON   = int((0.034 if _IS_MOBILE else 0.030) * _FS)
FS_SMALL    = int((0.030 if _IS_MOBILE else 0.026) * _FS)
FS_TINY     = int((0.029 if _IS_MOBILE else 0.026) * _FS)

# Legibility floor: the smallest requested size accepted by ``get_font`` on
# mobile.  A number of older screens still derive fonts from raw
# ``SCREEN_HEIGHT`` (for example 0.016 * 480 = 7px), bypassing ``_UI_SCALE``.
# Clamping centrally makes those forgotten labels readable too.  Explicit
# semantic tiers above remain larger, so this is a safety net rather than the
# normal body-text size.
FS_FLOOR = max(18, int(0.023 * _FS)) if _IS_MOBILE else max(12, int(0.016 * _FS))

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

def mobile_font_size(size, minimum=None):
    """Return ``size`` with the shared mobile legibility floor applied."""
    size = max(1, int(size))
    if not _IS_MOBILE:
        return size
    floor = FS_FLOOR if minimum is None else max(FS_FLOOR, int(minimum))
    return max(size, floor)


def get_font(size, bold=False, allow_small=False):
    """Return a cached font, protecting mobile text from legacy tiny sizes.

    ``allow_small`` is reserved for decorative glyphs whose font size is part
    of a fixed icon drawing rather than player-facing text.
    """
    size = max(1, int(size))
    if _IS_MOBILE and not allow_small:
        size = mobile_font_size(size)
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
