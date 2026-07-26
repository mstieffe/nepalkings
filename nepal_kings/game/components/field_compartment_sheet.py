# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Modal sheet showing one field compartment's figures at full size.

A compartment column is narrow enough that a tier-6 lineup has to render as a
scrolling list of compacted rows.  That is fine for keeping track of a battle,
but it is a poor way to actually read a dozen figures.  This sheet spreads the
same figures across the width of the screen in a grid at their natural size,
so the whole compartment can be taken in at a glance instead of scrolled
through a 69 px column.

The sheet reuses the caller's live ``FieldFigureIcon`` objects rather than
building its own: they already carry battle bonuses, enchantments, deficit and
selection state.  That is safe because the sheet is modal — the column behind
it is not drawing or hit-testing while it is open — but it does mean the sheet
must restore each icon's render scale and hit state when it closes.
"""
from __future__ import annotations

import pygame

from config import settings
from game.components.field_figure_layout import rich_row_metrics


_BACKDROP = (10, 8, 6, 214)
_PANEL_BG = (34, 28, 21, 250)
_PANEL_EDGE = (132, 108, 68, 235)
_TITLE_COLOR = (238, 222, 190)
_MUTED = (176, 154, 118)


class FieldCompartmentSheet:
    """Full-size grid of every figure in one compartment."""

    def __init__(self, window, field, icons, title=None):
        self.window = window
        self.field = field
        self.icons = list(icons)
        self.title = title or str(field).upper()

        self._scroll = 0.0
        self._max_scroll = 0.0
        self._dragging = False
        self._drag_last_y = 0
        self._drag_moved = False
        self._scrollbar_dragging = False
        self._scroll_track_rect = None

        self._cell_rects = []      # (icon, rect) for the current draw
        self._close_rect = None
        self._touch = bool(getattr(settings, 'TOUCH_TARGET_MIN', 0) > 0)

        # Icons are shared with the column behind us; remember what to put
        # back so closing the sheet does not leave them resized or inert.
        self._restore = [
            (icon, getattr(icon, 'render_scale', 1.0),
             getattr(icon, 'power_badge_only', False),
             getattr(icon, 'hit_rect', None),
             getattr(icon, 'hit_suppressed', False),
             getattr(icon, 'max_info_width', None))
            for icon in self.icons
        ]
        for icon in self.icons:
            icon.hovered = False

        self._layout()

    # ── Geometry ────────────────────────────────────────────────────

    def _layout(self):
        W, H = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT
        margin_x = int(0.03 * W)
        margin_y = int(0.06 * H)
        self.panel_rect = pygame.Rect(margin_x, margin_y,
                                      W - 2 * margin_x, H - 2 * margin_y)

        self._title_font = settings.get_font(
            max(11, int(settings.FS_BODY * 0.95)), bold=True, allow_small=True)
        self._label_font = settings.get_font(
            max(9, int(settings.FS_SMALL * 0.85)), allow_small=True)

        header_h = self._title_font.get_height() + max(8, int(0.014 * H))
        self.header_rect = pygame.Rect(self.panel_rect.x, self.panel_rect.y,
                                       self.panel_rect.width, header_h)
        self.content_rect = pygame.Rect(
            self.panel_rect.x + max(6, int(0.008 * W)),
            self.header_rect.bottom,
            self.panel_rect.width - 2 * max(6, int(0.008 * W)),
            self.panel_rect.height - header_h - max(6, int(0.010 * H)))

        close = max(int(0.030 * H), int(getattr(settings, 'TOUCH_TARGET_MIN', 0) or 0))
        close = max(close, 22)
        self._close_rect = pygame.Rect(0, 0, close, close)
        self._close_rect.topright = (self.header_rect.right - 6,
                                     self.header_rect.y + (header_h - close) // 2)

        # Each cell holds a full-size frame plus the icon's own name/power
        # plate, whose extents come from the same solver the columns use.
        frame, above, below = rich_row_metrics(str(self.field) == 'castle')
        self._frame_px = frame
        self._row_above = above
        # The plate is wider than the frame, so cells are sized by the plate
        # and the plate is capped to the cell — otherwise neighbouring names
        # run into each other.
        self._cell_w = int(max(frame * 1.6, frame + max(24, int(0.026 * W))))
        self._cell_h = int(above + below + max(8, int(0.016 * H)))
        self._columns = max(1, self.content_rect.width // max(1, self._cell_w))
        rows = (len(self.icons) + self._columns - 1) // max(1, self._columns)
        self._max_scroll = max(0.0, float(rows * self._cell_h
                                          - self.content_rect.height))

    # ── Events ──────────────────────────────────────────────────────

    def handle_events(self, events):
        """Return ``'close'``, ``('select', figure_id)`` or ``None``.

        Consumes the whole batch: the caller must not route these events to
        anything underneath.
        """
        from game.components.tutorial_window import _apply_wheel_drag_scroll

        _apply_wheel_drag_scroll(events, self.content_rect, self)

        for event in events:
            etype = getattr(event, 'type', None)
            if etype == pygame.KEYDOWN and getattr(event, 'key', None) == pygame.K_ESCAPE:
                self.close()
                return 'close'
            if etype != pygame.MOUSEBUTTONUP or getattr(event, 'button', 0) != 1:
                continue
            pos = getattr(event, 'pos', None) or pygame.mouse.get_pos()
            if self._drag_moved:
                # The release that ends a scroll drag must not also pick a
                # figure out of the grid.
                self._drag_moved = False
                continue
            if self._close_rect and self._close_rect.collidepoint(pos):
                self.close()
                return 'close'
            if not self.panel_rect.collidepoint(pos):
                self.close()
                return 'close'
            for icon, rect in self._cell_rects:
                if not rect.collidepoint(pos):
                    continue
                figure_id = getattr(getattr(icon, 'figure', None), 'id', None)
                if figure_id is not None:
                    self.close()
                    return ('select', figure_id)
        return None

    def close(self):
        """Restore the borrowed icons to how the column had them."""
        for icon, scale, badge, hit_rect, suppressed, info_w in self._restore:
            try:
                icon.set_render_scale(scale)
            except Exception:
                pass
            icon.power_badge_only = badge
            icon.hit_rect = hit_rect
            icon.hit_suppressed = suppressed
            icon.max_info_width = info_w
            icon.hovered = False

    # ── Drawing ─────────────────────────────────────────────────────

    def draw(self):
        from game.components.tutorial_window import _draw_vscrollbar

        backdrop = pygame.Surface(
            (settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT), pygame.SRCALPHA)
        backdrop.fill(_BACKDROP)
        self.window.blit(backdrop, (0, 0))

        panel = pygame.Surface(self.panel_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, _PANEL_BG, panel.get_rect(), border_radius=8)
        pygame.draw.rect(panel, _PANEL_EDGE, panel.get_rect(), 2, border_radius=8)
        self.window.blit(panel, self.panel_rect.topleft)

        heading = f"{self.title} — {len(self.icons)}"
        text = self._title_font.render(heading, True, _TITLE_COLOR)
        self.window.blit(text, (self.header_rect.x + max(8, int(0.010 * settings.SCREEN_WIDTH)),
                                self.header_rect.centery - text.get_height() // 2))
        self._draw_close_button()

        self._draw_cells()

        if self._max_scroll > 0:
            _draw_vscrollbar(
                self.window, self.panel_rect, self.content_rect.top,
                self.content_rect.height,
                self.content_rect.height + self._max_scroll,
                self._scroll, self._max_scroll, (188, 158, 96), obj=self)
        else:
            self._scroll_track_rect = None

    def _draw_close_button(self):
        rect = self._close_rect
        pygame.draw.rect(self.window, (58, 46, 34), rect, border_radius=4)
        pygame.draw.rect(self.window, _PANEL_EDGE, rect, 1, border_radius=4)
        inset = max(4, rect.width // 3)
        pygame.draw.line(self.window, _TITLE_COLOR,
                         (rect.left + inset, rect.top + inset),
                         (rect.right - inset, rect.bottom - inset), 2)
        pygame.draw.line(self.window, _TITLE_COLOR,
                         (rect.right - inset, rect.top + inset),
                         (rect.left + inset, rect.bottom - inset), 2)

    def _draw_cells(self):
        self._cell_rects = []
        previous_clip = self.window.get_clip()
        self.window.set_clip(self.content_rect)
        try:
            for index, icon in enumerate(self.icons):
                col = index % self._columns
                row = index // self._columns
                cell = pygame.Rect(
                    self.content_rect.x + col * self._cell_w,
                    int(self.content_rect.y + row * self._cell_h - self._scroll),
                    self._cell_w, self._cell_h)
                if not cell.colliderect(self.content_rect):
                    continue

                # Full size here — that is the whole point of the sheet.
                try:
                    icon.set_render_scale(1.0)
                except Exception:
                    pass
                icon.power_badge_only = False
                icon.max_info_width = self._cell_w - 6
                icon.hit_suppressed = False
                icon.hit_rect = cell

                # The icon paints its own name/power/suit plate, so the cell
                # adds no caption of its own.
                icon.draw(cell.centerx, cell.y + self._row_above + 2)
                self._cell_rects.append((icon, cell))
        finally:
            self.window.set_clip(previous_clip)
