# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
from config.screen_settings import SCREEN_HEIGHT, _FS

import pygame

# Font settings
FONT_PATH = None
FONT_SIZE = int(0.05 * _FS)
FONT_SIZE_DETAIL = int(0.02 * _FS)
FONT_SIZE_BUTTON = int(0.03 * _FS)
FONT_SIZE_SUBSCREEN_BUTTON = int(0.02 * _FS)
LOGOUT_FONT_SIZE = int(0.03 * _FS)

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
