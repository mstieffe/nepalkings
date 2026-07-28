# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Pure layout solver for one field compartment (castle / village / military).

A compartment is a narrow vertical column that has to hold an unbounded number
of figures: ``CASTLE_FIGURE_LIMIT_BY_TIER`` allows six castle figures on a
tier-6 land, village and military are uncapped, and a tier-6 AI defence
routinely generates a dozen figures across the three columns.  At full icon
size only **two** fit, so this solver picks one of two presentations and, past
that, scrolls:

* ``"rich"`` — the established look (full icon plus the name/power info plate)
  while every figure fits without overlapping.
* ``"dense"`` — uniform rows with a smaller icon and no name plate, used as
  soon as the rich footprint would collide.  Dense rows drop the 1.2x castle
  bump so a castle column keeps the same row height as its neighbours.

The solver is pure (no pygame surfaces, no I/O) so it can be unit-tested
without a display, and it is the single source of truth for figure positions:
:mod:`field_screen`, :mod:`conquer_screen`, :mod:`defence_screen` and the
conquer spell-ghost fallback all read ``row_centers`` from here instead of
each re-deriving the same spacing formula.

Two measurements matter and were previously wrong:

* The footprint is derived from the **drawn** frame size
  (``FIELD_ICON_WIDTH * family * FIELD_FIGURE_ICON_SCALE * FRAME_FIGURE_SCALE``),
  not from the ``FIGURE_ICON_HEIGHT`` proxy the old formula used.  That proxy
  understated the real frame by roughly half, so icons began overlapping
  earlier than the spacing math predicted.
* ``icon_render_scale`` clamps the frame to the column width.  A mobile castle
  frame is 87 px inside a 69 px column, so castle icons used to bleed
  sideways into the duel lane and the neighbouring column.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

from config import settings


Rect = Tuple[int, int, int, int]  # (x, y, w, h) in pixels


# ── Tuning ────────────────────────────────────────────────────────────

# Dense icon size relative to a non-castle field icon.  0.70 is the point
# where four rows fit a mobile conquer column while the family artwork is
# still distinguishable at a glance.
_DENSE_ICON_SCALE = 0.70

# The info plate proxy the icon itself uses: its top sits at
# ``0.34 * FIGURE_ICON_HEIGHT`` below the icon centre (see
# ``FieldFigureIcon.draw_figure_info``'s ``base_offset = 0.68``) and it runs
# about ``2.6`` caption lines tall.
_INFO_TOP_OFFSET_FRAC = 0.34
_INFO_HEIGHT_LINES = 2.6

# Castle icons are built 1.2x larger than other fields
# (``FieldFigureIcon._initialize_images``).
_CASTLE_FAMILY_SCALE = 1.2


@dataclass(frozen=True)
class FieldColumnLayout:
    """Resolved geometry for one compartment."""

    mode: str                       # 'rich' | 'dense'
    column_rect: Rect
    header_rect: Rect               # tappable title strip (opens the expand sheet)
    content_rect: Rect              # clip target for the figure rows
    figure_count: int
    row_height: int
    row_above: int                  # drawn extent above a row's centre
    row_below: int                  # drawn extent below it (plate included)
    icon_render_scale: float        # multiplier on top of the icon's family scale
    frame_px: int                   # drawn frame size at icon_render_scale
    row_centers: Tuple[int, ...]    # absolute y centre per figure, scroll applied
    first_visible: int
    visible_count: int
    rows_visible: int               # capacity, independent of figure_count
    scroll_px: int
    max_scroll_px: int

    @property
    def overflow(self) -> bool:
        """True when the column cannot show every figure at once."""
        return self.max_scroll_px > 0

    @property
    def visible_slice(self) -> slice:
        return slice(self.first_visible, self.first_visible + self.visible_count)

    def is_row_fully_visible(self, index: int) -> bool:
        """True when row ``index`` is drawn whole inside ``content_rect``.

        Partially clipped rows are excluded so they never become hover or tap
        targets — a half-drawn icon that still answers clicks reads as a
        phantom hit.  A rich row is asymmetric about its centre (the info
        plate hangs below the icon), so the two extents are checked
        separately rather than as ``row_height / 2``.
        """
        if not 0 <= index < len(self.row_centers):
            return False
        _cx, cy, _cw, ch = self.content_rect
        centre = self.row_centers[index]
        return ((centre - self.row_above) >= cy - 1
                and (centre + self.row_below) <= cy + ch + 1)

    def row_rect(self, index: int) -> Optional[Rect]:
        """Full-width hit rect for row ``index``, or ``None`` if out of range."""
        if not 0 <= index < len(self.row_centers):
            return None
        cx, _cy, cw, _ch = self.content_rect
        centre = self.row_centers[index]
        return (cx, int(centre - self.row_above), cw,
                int(self.row_above + self.row_below))


def _base_frame_px(is_castle: bool) -> float:
    """Drawn frame edge length for a field icon at its natural scale."""
    family = _CASTLE_FAMILY_SCALE if is_castle else 1.0
    return (settings.FIELD_ICON_WIDTH
            * family
            * settings.FIELD_FIGURE_ICON_SCALE
            * settings.FRAME_FIGURE_SCALE)


def _info_plate_extent() -> Tuple[float, float]:
    """(top offset below centre, height) of the name/power plate."""
    caption_h = int(settings.FIGURE_ICON_FONT_CAPTION_FONT_SIZE * _INFO_HEIGHT_LINES)
    return _INFO_TOP_OFFSET_FRAC * settings.FIGURE_ICON_HEIGHT, caption_h


def _is_touch() -> bool:
    return bool(getattr(settings, 'TOUCH_TARGET_MIN', 0) > 0)


def rich_row_metrics(is_castle: bool = False) -> Tuple[int, int, int]:
    """``(frame_px, above, below)`` for a full-size icon with its info plate.

    Exposed so anything laying figures out at natural size — the expand
    sheet's grid, for instance — reserves the same space this module does
    instead of guessing at the plate's height again.
    """
    frame = _base_frame_px(is_castle)
    info_top, info_h = _info_plate_extent()
    return int(round(frame)), int(round(frame / 2.0)), int(round(info_top + info_h))


def compute_field_column(column_rect,
                         figure_count: int,
                         *,
                         title_space: int,
                         is_castle_column: bool = False,
                         scroll_px: int = 0,
                         force_mode: Optional[str] = None) -> FieldColumnLayout:
    """Resolve one compartment's rows.

    :param column_rect: the compartment rect, ``(x, y, w, h)`` or a
        ``pygame.Rect``-like object exposing ``x``/``y``/``width``/``height``.
    :param figure_count: how many figures the compartment holds.
    :param title_space: vertical space the compartment title needs.  Callers
        differ here (``FIELD_TITLE_FONT_SIZE + FIELD_TITLE_PADDING`` on the
        field screen, a flat ``24`` on the config screens), so it is an
        argument rather than a constant.
    :param is_castle_column: castle icons are built 1.2x larger.
    :param scroll_px: current scroll offset; clamped to ``[0, max_scroll_px]``.
    :param force_mode: pin the presentation instead of choosing by fit.  The
        expand sheet uses ``'rich'`` so it always renders at full size.
    """
    x, y, w, h = _as_rect(column_rect)
    count = max(0, int(figure_count))

    border = settings.FIELD_BORDER_WIDTH
    # A tappable header needs real height; on touch the bare title strip is
    # under the compact minimum, so reserve up to it. The cost is at most one
    # dense row and it buys a header that reliably opens the expand sheet.
    header_h = max(1, int(title_space))
    if _is_touch():
        header_h = max(header_h, int(settings.TOUCH_COMPACT_MIN))
    header_h = min(header_h, max(1, h - 1))
    header_rect: Rect = (x, y, w, header_h)

    content_y = y + header_h
    content_h = max(1, h - header_h - border)
    content_rect: Rect = (x + border, content_y, max(1, w - 2 * border), content_h)

    # Frames may never be wider than the column they live in.
    max_frame = max(8.0, float(w - 2 * border - 2))
    base_frame = _base_frame_px(is_castle_column)

    # Rich: natural size (clamped), icon above its info plate.
    rich_frame = min(base_frame, max_frame)
    info_top, info_h = _info_plate_extent()
    rich_above = rich_frame / 2.0
    rich_below = info_top + info_h
    rich_row = max(1, int(round(rich_above + rich_below)))

    # Dense: uniform rows, no plate, castle bump dropped so every column in a
    # board shares one row height.
    dense_frame = min(_base_frame_px(False) * _DENSE_ICON_SCALE, max_frame)
    # Kept tight on purpose: a larger gap costs a whole visible row on the
    # shortest canvas (854x480 fits four 54 px rows but only three 56 px ones).
    dense_gap = max(2, int(0.008 * settings.SCREEN_HEIGHT))
    dense_row = int(round(dense_frame)) + dense_gap
    if _is_touch():
        dense_row = max(dense_row, int(settings.TOUCH_COMPACT_MIN))

    fits_rich = count > 0 and count * rich_row <= content_h
    mode = force_mode or ('rich' if (count <= 1 or fits_rich) else 'dense')

    if mode == 'rich':
        row_height = rich_row
        frame_px = rich_frame
        above, below = rich_above, rich_below
    else:
        row_height = dense_row
        frame_px = dense_frame
        above = below = row_height / 2.0

    render_scale = (frame_px / base_frame) if base_frame > 0 else 1.0

    content_span = count * row_height
    max_scroll = max(0, content_span - content_h)
    scroll = int(max(0, min(int(scroll_px), max_scroll)))

    # With slack, centre the group the way the field screen always has.
    offset = ((content_h - content_span) / 2.0) if max_scroll == 0 else 0.0

    centers = tuple(
        int(round(content_y + offset + i * row_height + above - scroll))
        for i in range(count)
    )

    rows_visible = max(1, int(content_h // row_height)) if row_height > 0 else 1
    if max_scroll <= 0:
        first_visible, visible_count = 0, count
    else:
        first_visible = max(0, min(count - 1, int(scroll // row_height)))
        # +1 so a partially scrolled row is still drawn (clipped) rather than
        # popping in only once fully inside the viewport.
        visible_count = min(count - first_visible, rows_visible + 1)

    return FieldColumnLayout(
        mode=mode,
        column_rect=(x, y, w, h),
        header_rect=header_rect,
        content_rect=content_rect,
        figure_count=count,
        row_height=row_height,
        row_above=int(round(above)),
        row_below=int(round(below)),
        icon_render_scale=render_scale,
        frame_px=int(round(frame_px)),
        row_centers=centers,
        first_visible=first_visible,
        visible_count=max(0, visible_count),
        rows_visible=rows_visible,
        scroll_px=scroll,
        max_scroll_px=max_scroll,
    )


def scroll_to_reveal(layout: FieldColumnLayout, index: int) -> int:
    """Return the scroll offset that brings row ``index`` fully into view.

    A defender or spell target scrolled out of its column cannot be picked, so
    every selection prompt runs its valid target through this.
    """
    if layout.max_scroll_px <= 0 or not 0 <= index < layout.figure_count:
        return layout.scroll_px
    _cx, _cy, _cw, content_h = layout.content_rect
    row_top = index * layout.row_height
    row_bottom = row_top + layout.row_height
    scroll = layout.scroll_px
    if row_top < scroll:
        scroll = row_top
    elif row_bottom > scroll + content_h:
        scroll = row_bottom - content_h
    return int(max(0, min(scroll, layout.max_scroll_px)))


def _as_rect(rect) -> Rect:
    """Accept a 4-tuple or any pygame.Rect-like object."""
    if hasattr(rect, 'width') and hasattr(rect, 'height'):
        return int(rect.x), int(rect.y), int(rect.width), int(rect.height)
    x, y, w, h = rect
    return int(x), int(y), int(w), int(h)
