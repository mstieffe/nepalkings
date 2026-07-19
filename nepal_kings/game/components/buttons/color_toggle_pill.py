# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Figure-colour toggle pill widget."""

import pygame

from config import settings
from game.core.input_state import get_pressed as _get_pressed
from utils import haptics
from utils import sound


class ColorTogglePill:
    """A programmatic pill-shaped toggle button (no image assets).

    Compatible with the SubScreenButton interface used by SubScreen
    (draw, update, collide, .active, .text, .hovered, .clicked).
    """

    # Small colour dot per label (faction hint)
    _DOT_COLOR_MAP = {
        'Djungle':  (80, 180, 80),   # green
        'Himalaya': (80, 130, 210),   # blue
    }

    def __init__(self, window, x, y, text, display_text=None):
        self.window = window
        self.x = x
        self.y = y
        self.text = text
        self.display_text = display_text or text
        self.font = settings.get_font(settings.COLOR_TOGGLE_FONT_SIZE, bold=True)

        self.rect = pygame.Rect(x, y, settings.COLOR_TOGGLE_W, settings.COLOR_TOGGLE_H)
        self.corner_r = settings.COLOR_TOGGLE_CORNER_R

        # Optional faction-colour dot
        self._dot_clr = self._DOT_COLOR_MAP.get(text, None)
        self._dot_r = max(3, int(0.006 * settings.SCREEN_HEIGHT))

        self.hovered = False
        self.clicked = False
        self.active = False

    # ---- interface -----
    def collide(self):
        # Mobile: pad the hit area vertically only — toggle pills sit in
        # a tight horizontal pair, so widening would overlap neighbours.
        pad = settings.TOUCH_HIT_PAD
        hit = self.rect.inflate(0, 2 * pad) if pad else self.rect
        return hit.collidepoint(pygame.mouse.get_pos())

    def update(self):
        self.hovered = self.collide()
        self.clicked = self.hovered and _get_pressed()[0]
        haptics.tap_edge(self)
        sound.tap_edge(self)

    def draw(self):
        r = self.corner_r
        w, h = self.rect.size

        # Pick colours (gold for active, warm cream for inactive)
        if self.active:
            bg = settings.COLOR_TOGGLE_BG_ACTIVE_CLR
            border = settings.COLOR_TOGGLE_BORDER_ACTIVE_CLR
            txt_clr = settings.COLOR_TOGGLE_TEXT_ACTIVE_CLR
        elif self.hovered:
            bg = settings.COLOR_TOGGLE_BG_HOVER_CLR
            border = settings.COLOR_TOGGLE_BORDER_CLR
            txt_clr = settings.COLOR_TOGGLE_TEXT_CLR
        else:
            bg = settings.COLOR_TOGGLE_BG_CLR
            border = settings.COLOR_TOGGLE_BORDER_CLR
            txt_clr = settings.COLOR_TOGGLE_TEXT_CLR

        # Surface with per-pixel alpha for semi-transparent bg
        pill = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(pill, bg, (0, 0, w, h), border_radius=r)
        pygame.draw.rect(pill, border, (0, 0, w, h), 2, border_radius=r)
        self.window.blit(pill, self.rect.topleft)

        # Text centred. The shrink-to-fit stops at a mobile legibility floor
        # (the callers pass short labels there instead).
        min_h = 13 if settings.TOUCH_TARGET_MIN > 0 else 8
        font = self.font
        while (font.size(self.display_text)[0] > max(1, w - 12)
               and font.get_height() > min_h):
            font = settings.get_font(font.get_height() - 1, bold=True)
        txt_surf = font.render(self.display_text, True, txt_clr)
        txt_rect = txt_surf.get_rect(center=self.rect.center)
        self.window.blit(txt_surf, txt_rect)

        # Faction colour dot to the left of the text
        if self._dot_clr is not None:
            dot_x = txt_rect.left - self._dot_r - 4
            # Clamp so the dot never bleeds outside the button
            dot_x = max(dot_x, self.rect.left + self._dot_r + 2)
            dot_y = self.rect.centery
            pygame.draw.circle(self.window, self._dot_clr, (dot_x, dot_y), self._dot_r)


# Preserve legacy runtime metadata for repr/pickle compatibility while
# ``utils.utils`` remains the supported public import path.
ColorTogglePill.__module__ = 'utils.utils'
