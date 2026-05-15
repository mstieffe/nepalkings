# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Reusable rising-and-fading text overlay (e.g. ``+12g`` collect feedback)."""

import random

import pygame


class FloatingText:
    """A short-lived `+amount` style label that rises and fades.

    The instance owns its own lifetime: call :meth:`update` every frame with
    the elapsed milliseconds; when it returns ``False`` the caller should drop
    the reference. Drawing is independent of update so it can be batched in a
    layer.
    """

    def __init__(self, text, start_pos, *, color, duration_ms, rise_px, font,
                 jitter_px=4, delay_ms=0):
        self._text = str(text)
        self._x0, self._y0 = int(start_pos[0]), int(start_pos[1])
        self._color = tuple(color)[:3]
        self._duration_ms = max(1, int(duration_ms))
        self._rise_px = int(rise_px)
        self._font = font
        # Tiny per-instance horizontal jitter so stacked floaters spread out.
        self._jitter = random.randint(-int(jitter_px), int(jitter_px)) if jitter_px else 0
        self._delay_ms = max(0, int(delay_ms))
        self._elapsed_ms = 0
        # Pre-rendered surface — re-used every frame; only alpha varies.
        self._surface = self._font.render(self._text, True, self._color)
        self._surface = self._surface.convert_alpha()
        self._finished = False

    @property
    def finished(self):
        return self._finished

    def update(self, dt_ms):
        """Advance the animation by ``dt_ms`` and return ``False`` when done."""
        if self._finished:
            return False
        self._elapsed_ms += int(dt_ms)
        # Honour startup delay (used to stagger a burst of floaters).
        if self._elapsed_ms < self._delay_ms:
            return True
        if self._elapsed_ms - self._delay_ms >= self._duration_ms:
            self._finished = True
            return False
        return True

    def draw(self, surface):
        if self._finished:
            return
        active_ms = self._elapsed_ms - self._delay_ms
        if active_ms < 0:
            return
        t = active_ms / float(self._duration_ms)
        if t < 0 or t > 1:
            return
        # Linear rise.
        dy = int(self._rise_px * t)
        # Mild ease-out alpha: stays opaque longer, fades sharply at the end.
        alpha = max(0, min(255, int(255 * (1.0 - t) ** 1.4)))
        # ``set_alpha`` on a per-pixel-alpha surface doesn't work; blit a copy.
        frame = self._surface.copy()
        frame.fill((255, 255, 255, alpha), special_flags=pygame.BLEND_RGBA_MULT)
        rect = frame.get_rect(center=(self._x0 + self._jitter, self._y0 - dy))
        surface.blit(frame, rect.topleft)


class FloatingTextLayer:
    """Manage a list of :class:`FloatingText` instances."""

    def __init__(self):
        self._items = []

    def __len__(self):
        return len(self._items)

    def add(self, floater):
        self._items.append(floater)

    def clear(self):
        self._items.clear()

    def update(self, dt_ms):
        if not self._items:
            return
        self._items = [f for f in self._items if f.update(dt_ms)]

    def draw(self, surface):
        for f in self._items:
            f.draw(surface)
