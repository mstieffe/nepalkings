# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Geometry invariants for one field compartment.

The bug these pin down: a compartment used to distribute figure centres
evenly across whatever room it had, with no floor, so past the two figures
that actually fit the icons were simply drawn on top of each other.  A
tier-6 land allows six castle figures and village/military are uncapped, so
that is ordinary play rather than a corner case.

The solver is pure rect maths, so everything here runs without a display.
"""
import os
import subprocess
import sys

import pytest

APP_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'nepal_kings')


def _layout_module():
    from game.components import field_figure_layout
    return field_figure_layout


def _settings():
    from config import settings
    return settings


def _column(width=None, height=None):
    """A compartment rect roughly the size conquer gives one column."""
    settings = _settings()
    width = width or int(0.115 * settings.SCREEN_WIDTH)
    height = height or int(0.52 * settings.SCREEN_HEIGHT)
    return (int(0.2 * settings.SCREEN_WIDTH), int(0.12 * settings.SCREEN_HEIGHT),
            width, height)


def _title_space():
    settings = _settings()
    return settings.FIELD_TITLE_FONT_SIZE + settings.FIELD_TITLE_PADDING


COUNTS = [1, 2, 3, 4, 6, 9, 12, 16]


@pytest.mark.parametrize('count', COUNTS)
@pytest.mark.parametrize('is_castle', [False, True])
def test_rows_never_overlap(count, is_castle):
    """The whole point: no two figures may ever share vertical space."""
    mod = _layout_module()
    layout = mod.compute_field_column(
        _column(), count, title_space=_title_space(),
        is_castle_column=is_castle)

    for index in range(count - 1):
        this_bottom = layout.row_centers[index] + layout.row_below
        next_top = layout.row_centers[index + 1] - layout.row_above
        assert this_bottom <= next_top + 1, (
            f'rows {index}/{index + 1} overlap by '
            f'{this_bottom - next_top}px at count={count}')


@pytest.mark.parametrize('count', COUNTS)
def test_frame_never_exceeds_column_width(count):
    """A mobile castle frame is 87px inside a 69px column without clamping."""
    mod = _layout_module()
    settings = _settings()
    column = _column()
    layout = mod.compute_field_column(
        column, count, title_space=_title_space(), is_castle_column=True)
    usable = column[2] - 2 * settings.FIELD_BORDER_WIDTH
    assert layout.frame_px <= usable


@pytest.mark.parametrize('count', [1, 2, 12])
@pytest.mark.parametrize('is_castle', [False, True])
def test_narrow_column_clamps_the_frame(count, is_castle):
    """Rich mode has to clamp too, not just dense.

    A single figure stays rich at any width, so without the clamp its frame
    keeps its natural size and hangs out over the neighbouring column — the
    mobile castle case, where an 87px frame sits in a 69px column.
    """
    mod = _layout_module()
    settings = _settings()
    natural = mod.rich_row_metrics(is_castle)[0]
    # Deliberately narrower than the icon wants to be.
    column = (100, 100, int(natural * 0.6), int(0.52 * settings.SCREEN_HEIGHT))
    layout = mod.compute_field_column(
        column, count, title_space=_title_space(), is_castle_column=is_castle)
    usable = column[2] - 2 * settings.FIELD_BORDER_WIDTH
    assert layout.frame_px <= usable, (
        f'{layout.mode} frame {layout.frame_px} bleeds out of a '
        f'{column[2]}px column')
    assert layout.icon_render_scale < 1.0


@pytest.mark.parametrize('count', COUNTS)
def test_visible_rows_stay_inside_the_content_rect(count):
    mod = _layout_module()
    layout = mod.compute_field_column(
        _column(), count, title_space=_title_space())
    _cx, cy, _cw, ch = layout.content_rect
    for index in range(count):
        if not layout.is_row_fully_visible(index):
            continue
        assert layout.row_centers[index] - layout.row_above >= cy - 1
        assert layout.row_centers[index] + layout.row_below <= cy + ch + 1


@pytest.mark.parametrize('count', COUNTS)
def test_overflow_iff_content_does_not_fit(count):
    mod = _layout_module()
    layout = mod.compute_field_column(
        _column(), count, title_space=_title_space())
    span = count * layout.row_height
    fits = span <= layout.content_rect[3]
    assert layout.overflow is (not fits)
    if fits:
        assert layout.max_scroll_px == 0
        assert all(layout.is_row_fully_visible(i) for i in range(count))


def test_header_is_reserved_above_the_content():
    """The header opens the expand sheet, so it may not overlap row one."""
    mod = _layout_module()
    layout = mod.compute_field_column(
        _column(), 12, title_space=_title_space())
    hx, hy, hw, hh = layout.header_rect
    cx, cy, cw, ch = layout.content_rect
    assert hy + hh <= cy
    assert hh >= 1
    assert hw > 0 and cw > 0 and ch > 0


def test_small_counts_keep_the_rich_presentation():
    """A duel field with one or two figures must not change appearance."""
    mod = _layout_module()
    layout = mod.compute_field_column(
        _column(), 1, title_space=_title_space())
    assert layout.mode == 'rich'
    assert layout.icon_render_scale == pytest.approx(1.0, abs=0.30)


def test_crowded_counts_switch_to_dense_rows():
    mod = _layout_module()
    layout = mod.compute_field_column(
        _column(), 12, title_space=_title_space())
    assert layout.mode == 'dense'
    assert layout.overflow
    # Dense exists to show more at once than the rich layout could.
    rich = mod.compute_field_column(
        _column(), 1, title_space=_title_space())
    assert layout.row_height < rich.row_height


def test_dense_shows_at_least_four_rows_at_once():
    """Four visible rows is the density the layout is tuned for.

    Fewer would mean a dozen figures take four screens of scrolling; this
    guards the tuning (dense scale and row gap) against drift.
    """
    mod = _layout_module()
    layout = mod.compute_field_column(
        _column(), 12, title_space=_title_space())
    visible = sum(1 for i in range(12) if layout.is_row_fully_visible(i))
    assert visible >= 4


@pytest.mark.parametrize('count', [6, 12, 16])
def test_scroll_is_clamped_to_range(count):
    mod = _layout_module()
    layout = mod.compute_field_column(
        _column(), count, title_space=_title_space(), scroll_px=10 ** 6)
    assert layout.scroll_px == layout.max_scroll_px
    layout = mod.compute_field_column(
        _column(), count, title_space=_title_space(), scroll_px=-500)
    assert layout.scroll_px == 0


def test_scroll_to_reveal_brings_the_last_row_into_view():
    """A defender scrolled out of its column cannot be picked at all."""
    mod = _layout_module()
    layout = mod.compute_field_column(
        _column(), 12, title_space=_title_space())
    assert not layout.is_row_fully_visible(11)

    scroll = mod.scroll_to_reveal(layout, 11)
    revealed = mod.compute_field_column(
        _column(), 12, title_space=_title_space(), scroll_px=scroll)
    assert revealed.is_row_fully_visible(11)

    # And back to the first row again.
    back = mod.scroll_to_reveal(revealed, 0)
    first = mod.compute_field_column(
        _column(), 12, title_space=_title_space(), scroll_px=back)
    assert first.is_row_fully_visible(0)


def test_scroll_to_reveal_is_a_no_op_without_overflow():
    mod = _layout_module()
    layout = mod.compute_field_column(
        _column(), 1, title_space=_title_space())
    assert mod.scroll_to_reveal(layout, 0) == layout.scroll_px


def test_empty_compartment_is_harmless():
    mod = _layout_module()
    layout = mod.compute_field_column(
        _column(), 0, title_space=_title_space())
    assert layout.row_centers == ()
    assert layout.max_scroll_px == 0
    assert not layout.overflow


def test_row_rect_matches_the_row_extents():
    mod = _layout_module()
    layout = mod.compute_field_column(
        _column(), 6, title_space=_title_space())
    rect = layout.row_rect(0)
    assert rect is not None
    _x, y, _w, h = rect
    assert y == layout.row_centers[0] - layout.row_above
    assert h == layout.row_above + layout.row_below
    assert layout.row_rect(99) is None


def test_rich_row_metrics_match_a_rich_layout():
    """The expand sheet sizes its grid from these, so they must agree."""
    mod = _layout_module()
    frame, above, below = mod.rich_row_metrics(is_castle=False)
    # A very tall column keeps a single figure in rich mode unclamped.
    settings = _settings()
    tall = (0, 0, int(0.4 * settings.SCREEN_WIDTH),
            int(0.9 * settings.SCREEN_HEIGHT))
    layout = mod.compute_field_column(tall, 1, title_space=_title_space())
    assert layout.mode == 'rich'
    assert layout.row_above == above
    assert layout.row_below == below
    assert layout.frame_px == frame


# ── Touch geometry (needs the mobile settings baked in at import) ──


_TOUCH_ROWS_CHECK = """
import os, sys
sys.path.insert(0, os.getcwd())
from config import settings
from game.components.field_figure_layout import compute_field_column

column = (170, 134, 69, 257)
title_space = settings.FIELD_TITLE_FONT_SIZE + settings.FIELD_TITLE_PADDING
layout = compute_field_column(column, 12, title_space=title_space,
                              is_castle_column=True)

assert settings.TOUCH_COMPACT_MIN > 0, 'fixture is not in touch mode'
assert layout.mode == 'dense', layout.mode
# Rows must clear the compact touch minimum...
assert layout.row_height >= settings.TOUCH_COMPACT_MIN, layout.row_height
# ...and still leave four of them visible on the shortest canvas.
visible = sum(1 for i in range(12) if layout.is_row_fully_visible(i))
assert visible >= 4, visible
# Frames may not bleed out of a 69px column.
assert layout.frame_px <= 69 - 2 * settings.FIELD_BORDER_WIDTH, layout.frame_px
# Adjacent rows stay disjoint (a tap near a boundary must not hit two).
for i in range(11):
    assert layout.row_centers[i] + layout.row_below <= \
        layout.row_centers[i + 1] - layout.row_above + 1
print('ok')
"""


def test_touch_rows_are_tappable_and_disjoint():
    """Mobile geometry has to be checked in its own process.

    ``config.settings`` bakes resolution and touch constants in at import
    time, so the mobile canvas cannot be simulated by monkeypatching here.
    """
    env = os.environ.copy()
    env.update({
        'SDL_VIDEODRIVER': 'dummy', 'SDL_AUDIODRIVER': 'dummy',
        'NK_SCREEN_WIDTH': '854', 'NK_SCREEN_HEIGHT': '480',
        'NK_IS_MOBILE': '1', 'NK_UI_SCALE': '1.6',
    })
    result = subprocess.run(
        [sys.executable, '-c', _TOUCH_ROWS_CHECK], cwd=APP_DIR, env=env,
        capture_output=True, text=True, timeout=60, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
