# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Wheel / drag scrolling for a set of field compartments.

:mod:`field_figure_layout` decides *that* a compartment has to scroll; this
owns the offset it scrolls to and the gestures that move it.  It is shared by
every screen that draws figure columns so the attack and defence config
screens behave exactly like the battlefield: the wheel scrolls the column
under the cursor, a drag scrolls on touch, and the release that ends a drag
is swallowed so a swipe never doubles as a click on the figure it began on.
"""
from __future__ import annotations

import pygame

from config import settings


class FieldColumnScroller:
    """Scroll offsets for compartments, keyed by whatever the caller uses."""

    #: Pointer travel before a press becomes a scroll rather than a click.
    DRAG_START_PX = 6

    def __init__(self):
        self._scroll = {}
        self._layouts = {}
        self._drag = None
        self._drag_moved = False

    # ── State ───────────────────────────────────────────────────────

    def scroll_px(self, key) -> int:
        return int(self._scroll.get(key, 0))

    def sync(self, key, layout) -> None:
        """Record a freshly solved layout and clamp any stale offset.

        Figures leave compartments (played, picked up, destroyed); without
        this a column could stay scrolled past its own new end.
        """
        self._layouts[key] = layout
        self._scroll[key] = layout.scroll_px

    def reset(self) -> None:
        self._scroll.clear()
        self._layouts.clear()
        self._drag = None
        self._drag_moved = False

    def column_at(self, pos):
        for key, layout in self._layouts.items():
            if pygame.Rect(layout.column_rect).collidepoint(pos):
                return key
        return None

    def scroll_by(self, key, delta_px) -> bool:
        """Scroll one column; True when it actually moved."""
        layout = self._layouts.get(key)
        if layout is None or not layout.overflow:
            return False
        before = self._scroll.get(key, 0)
        after = max(0, min(before + delta_px, layout.max_scroll_px))
        self._scroll[key] = after
        return after != before

    # ── Events ──────────────────────────────────────────────────────

    def handle_events(self, events):
        """Consume scroll gestures; return the events the screen should keep."""
        if not self._layouts:
            return events

        remaining = []
        for event in events:
            etype = getattr(event, 'type', None)
            pos = getattr(event, 'pos', None)

            if etype == pygame.MOUSEWHEEL:
                key = self.column_at(pos or pygame.mouse.get_pos())
                step = max(24, int(0.045 * settings.SCREEN_HEIGHT))
                if key and self.scroll_by(key, -getattr(event, 'y', 0) * step):
                    continue

            elif (etype == pygame.MOUSEBUTTONDOWN
                    and getattr(event, 'button', 0) == 1 and pos):
                key = self.column_at(pos)
                layout = self._layouts.get(key)
                if key is not None and layout is not None and layout.overflow:
                    self._drag = {'key': key, 'y': pos[1]}
                    self._drag_moved = False

            elif etype == pygame.MOUSEMOTION and self._drag and pos:
                dy = pos[1] - self._drag['y']
                if not self._drag_moved:
                    if abs(dy) < self.DRAG_START_PX:
                        remaining.append(event)
                        continue
                    self._drag_moved = True
                self._drag['y'] = pos[1]
                self.scroll_by(self._drag['key'], -dy)
                continue

            elif etype == pygame.MOUSEBUTTONUP and getattr(event, 'button', 0) == 1:
                was_drag = self._drag is not None and self._drag_moved
                self._drag = None
                self._drag_moved = False
                if was_drag:
                    continue

            remaining.append(event)
        return remaining

    # ── Drawing ─────────────────────────────────────────────────────

    def draw_scrollbar(self, window, key) -> None:
        """Passive track + thumb on a column's inner edge.

        No clickable arrows: over a narrow column they land on the first or
        last row and swallow taps meant for that figure.
        """
        layout = self._layouts.get(key)
        if layout is None or not layout.overflow:
            return
        content = pygame.Rect(layout.content_rect)
        if content.height <= 8:
            return
        track_w = max(3, int(0.0025 * settings.SCREEN_WIDTH))
        track = pygame.Rect(content.right - track_w - 1, content.top + 2,
                            track_w, content.height - 4)
        pygame.draw.rect(window, (70, 58, 42), track, border_radius=2)
        span = max(1, layout.figure_count * layout.row_height)
        thumb_h = max(10, int(track.height * content.height / float(span)))
        travel = max(0, track.height - thumb_h)
        frac = (layout.scroll_px / float(layout.max_scroll_px)
                if layout.max_scroll_px else 0.0)
        thumb = pygame.Rect(track.x, track.y + int(travel * frac),
                            track_w, thumb_h)
        pygame.draw.rect(window, (188, 158, 96), thumb, border_radius=2)
