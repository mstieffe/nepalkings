# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Scrolling, hit gating and the expand sheet for crowded field compartments.

A compartment that holds more figures than fit now clips and scrolls rather
than drawing them on top of each other.  That introduces three ways to get it
wrong, each pinned down here:

* a swipe that scrolls a column must not also select the figure it began on;
* a figure scrolled out of view must stop answering hovers and clicks, or it
  becomes a phantom hit target;
* a selection prompt whose only valid target is scrolled away must scroll it
  back, because a defender you cannot see is a defender you cannot pick.
"""
import os
import sys
from types import SimpleNamespace

import pygame
import pytest

APP_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'nepal_kings')


def _settings():
    from config import settings
    return settings


@pytest.fixture
def touch_mode(monkeypatch):
    """Simulate the mobile runtime: non-zero touch targets."""
    settings = _settings()
    monkeypatch.setattr(settings, 'TOUCH_TARGET_MIN', 58)
    monkeypatch.setattr(settings, 'TOUCH_COMPACT_MIN', 33)
    monkeypatch.setattr(settings, 'TOUCH_HIT_PAD', 8)


class _Icon:
    """Stand-in for FieldFigureIcon with just the surface the column uses."""

    def __init__(self, figure):
        self.figure = figure
        self.hovered = False
        self.clicked = False
        self.is_visible = True
        self.hit_rect = None
        self.hit_suppressed = False
        self.power_badge_only = False
        self.max_info_width = None
        self.render_scale = 1.0
        self.rect_frame = pygame.Rect(0, 0, 10, 10)

    def set_render_scale(self, scale):
        self.render_scale = scale

    def hit_area(self):
        if self.hit_suppressed:
            return None
        return pygame.Rect(self.hit_rect) if self.hit_rect else self.rect_frame


def _field(counts=None):
    """A FieldScreen carrying only what the column code touches."""
    from game.screens.field_screen import FieldScreen
    settings = _settings()

    counts = counts or {'castle': 12, 'village': 1, 'military': 1}
    screen = FieldScreen.__new__(FieldScreen)
    screen.window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    screen._column_scroll = {}
    screen._column_layouts = {}
    screen._icon_clip_rects = {}
    screen._column_drag = None
    screen._column_drag_moved = False
    screen._compartment_sheet = None
    screen._sheet_icon_ids = set()
    screen._last_selection_reveal_key = None
    screen.defender_selection_mode = False
    screen.conquer_own_defender_mode = False
    screen.icon_cache = {}
    screen.figure_icons = []

    col_w = int(0.115 * settings.SCREEN_WIDTH)
    col_h = int(0.52 * settings.SCREEN_HEIGHT)
    top = int(0.12 * settings.SCREEN_HEIGHT)
    left = int(0.18 * settings.SCREEN_WIDTH)
    screen.compartments = {'self': {}, 'opponent': {}}
    categorized = {'self': {}, 'opponent': {}}
    next_id = 1
    for player_index, player in enumerate(('self', 'opponent')):
        for field_index, field in enumerate(('castle', 'village', 'military')):
            x = left + (player_index * 3 + field_index) * col_w
            screen.compartments[player][field] = pygame.Rect(x, top, col_w, col_h)
            figures = []
            for _ in range(counts.get(field, 0) if player == 'self' else 1):
                figure = SimpleNamespace(
                    id=next_id, name=f'Figure {next_id}', player_id=1,
                    family=SimpleNamespace(field=field))
                next_id += 1
                figures.append(figure)
                icon = _Icon(figure)
                screen.icon_cache[figure.id] = icon
                screen.figure_icons.append(icon)
            categorized[player][field] = figures
    screen.categorized_figures = categorized
    screen._sync_column_layouts()
    return screen


def _press(screen, pos):
    return screen.handle_column_events(
        [pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos)])


def _motion(screen, pos):
    return screen.handle_column_events(
        [pygame.event.Event(pygame.MOUSEMOTION, pos=pos)])


def _release(screen, pos):
    return screen.handle_column_events(
        [pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=pos)])


# ── Layout wiring ───────────────────────────────────────────────────


def test_crowded_column_overflows_and_neighbours_do_not():
    screen = _field()
    crowded = screen._column_layouts[('self', 'castle')]
    quiet = screen._column_layouts[('self', 'village')]
    assert crowded.overflow and crowded.mode == 'dense'
    assert not quiet.overflow and quiet.mode == 'rich'


def test_row_hit_rects_are_disjoint_and_inside_the_column(touch_mode):
    """Adjacent rows may not overlap after the touch inflation.

    Inflating each row to the full touch target (as an isolated control
    would) makes neighbours overlap, and a tap near a boundary then selects
    the wrong figure.
    """
    screen = _field()
    screen._sync_column_layouts()
    layout = screen._column_layouts[('self', 'castle')]
    content = pygame.Rect(layout.content_rect)

    rects = [screen._column_row_hit_rect(layout, i)
             for i in range(layout.figure_count)
             if layout.is_row_fully_visible(i)]
    assert len(rects) >= 2
    for rect in rects:
        assert content.contains(rect)
        assert rect.height >= min(_settings().TOUCH_COMPACT_MIN,
                                  layout.row_height)
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            assert not rects[i].colliderect(rects[j]), (
                f'row hit rects {i} and {j} overlap')


# ── Scrolling ───────────────────────────────────────────────────────


def test_wheel_scrolls_the_column_under_the_cursor():
    screen = _field()
    key = ('self', 'castle')
    column = pygame.Rect(screen._column_layouts[key].column_rect)

    remaining = screen.handle_column_events([
        pygame.event.Event(pygame.MOUSEWHEEL, y=-1, pos=column.center)])
    assert screen._column_scroll[key] > 0
    assert remaining == [], 'a consumed wheel event must not fall through'


def test_wheel_over_a_column_that_fits_is_left_alone():
    screen = _field()
    key = ('self', 'village')
    column = pygame.Rect(screen._column_layouts[key].column_rect)
    remaining = screen.handle_column_events([
        pygame.event.Event(pygame.MOUSEWHEEL, y=-1, pos=column.center)])
    assert screen._column_scroll.get(key, 0) == 0
    assert len(remaining) == 1


def test_swipe_scrolls_and_swallows_the_release(touch_mode):
    """The instinctive scroll gesture must never select a figure."""
    screen = _field()
    key = ('self', 'castle')
    layout = screen._column_layouts[key]
    start = pygame.Rect(layout.content_rect).center

    _press(screen, start)
    _motion(screen, (start[0], start[1] - 40))
    assert screen._column_scroll[key] > 0, 'the drag did not scroll'

    remaining = _release(screen, (start[0], start[1] - 40))
    assert remaining == [], 'the release that ends a swipe must be swallowed'
    assert all(not icon.hovered for icon in screen.figure_icons)


def test_tap_without_movement_still_reaches_selection(touch_mode):
    screen = _field()
    key = ('self', 'castle')
    start = pygame.Rect(screen._column_layouts[key].content_rect).center

    _press(screen, start)
    remaining = _release(screen, start)
    assert screen._column_scroll[key] == 0
    assert len(remaining) == 1, 'a plain tap must pass through to the field'


def test_tiny_jitter_does_not_count_as_a_drag(touch_mode):
    """A couple of pixels of finger wobble is still a tap."""
    screen = _field()
    key = ('self', 'castle')
    start = pygame.Rect(screen._column_layouts[key].content_rect).center

    _press(screen, start)
    _motion(screen, (start[0], start[1] - 2))
    assert screen._column_scroll[key] == 0
    remaining = _release(screen, (start[0], start[1] - 2))
    assert len(remaining) == 1


def test_scroll_is_clamped_at_both_ends():
    screen = _field()
    key = ('self', 'castle')
    column = pygame.Rect(screen._column_layouts[key].column_rect)

    for _ in range(50):
        screen.handle_column_events([
            pygame.event.Event(pygame.MOUSEWHEEL, y=-1, pos=column.center)])
    screen._sync_column_layouts()
    assert screen._column_scroll[key] == screen._column_layouts[key].max_scroll_px

    for _ in range(50):
        screen.handle_column_events([
            pygame.event.Event(pygame.MOUSEWHEEL, y=1, pos=column.center)])
    assert screen._column_scroll[key] == 0


def test_stale_scroll_is_clamped_when_figures_leave():
    """Playing figures out of a compartment must not strand it mid-scroll."""
    screen = _field()
    key = ('self', 'castle')
    column = pygame.Rect(screen._column_layouts[key].column_rect)
    for _ in range(50):
        screen.handle_column_events([
            pygame.event.Event(pygame.MOUSEWHEEL, y=-1, pos=column.center)])
    assert screen._column_scroll[key] > 0

    screen.categorized_figures['self']['castle'] = \
        screen.categorized_figures['self']['castle'][:1]
    screen._sync_column_layouts()
    assert screen._column_scroll[key] == 0
    assert not screen._column_layouts[key].overflow


# ── Scroll into view ────────────────────────────────────────────────


def test_reveal_scrolls_a_hidden_figure_into_view():
    screen = _field()
    figures = screen.categorized_figures['self']['castle']
    last = figures[-1]
    layout = screen._column_layouts[('self', 'castle')]
    assert not layout.is_row_fully_visible(len(figures) - 1)

    assert screen._reveal_figure_in_column(last.id) is True
    screen._sync_column_layouts()
    assert screen._figure_row_visible(last.id)


def test_reveal_is_a_no_op_for_an_already_visible_figure():
    screen = _field()
    first = screen.categorized_figures['self']['castle'][0]
    assert screen._reveal_figure_in_column(first.id) is False
    assert screen._column_scroll[('self', 'castle')] == 0


def test_selection_prompt_reveals_its_only_valid_target():
    """A defender scrolled out of its column could not be picked at all."""
    screen = _field()
    figures = screen.categorized_figures['self']['castle']
    target = figures[-1]
    assert not screen._figure_row_visible(target.id)

    screen._is_conquer_selection_active = lambda: True
    screen._icon_is_selectable_for_current_mode = (
        lambda icon: icon.figure.id == target.id)
    screen._last_selection_reveal_key = None

    screen._sync_column_layouts()
    assert screen._figure_row_visible(target.id)


def test_selection_reveal_does_not_fight_manual_scrolling():
    """It is edge-triggered: re-running must not yank the view back."""
    screen = _field()
    figures = screen.categorized_figures['self']['castle']
    target = figures[-1]
    screen._is_conquer_selection_active = lambda: True
    screen._icon_is_selectable_for_current_mode = (
        lambda icon: icon.figure.id == target.id)
    screen._sync_column_layouts()

    key = ('self', 'castle')
    screen._column_scroll[key] = 0
    screen._sync_column_layouts()
    assert screen._column_scroll[key] == 0, 'reveal re-fired without an edge'


# ── Expand sheet ────────────────────────────────────────────────────


def test_header_tap_opens_the_expand_sheet(touch_mode):
    screen = _field()
    layout = screen._column_layouts[('self', 'castle')]
    header = pygame.Rect(layout.header_rect)

    remaining = _press(screen, header.center)
    assert screen._compartment_sheet is not None
    assert remaining == [], 'the header tap must not also hit a figure'
    assert len(screen._compartment_sheet.icons) == layout.figure_count


def test_header_of_a_column_that_fits_stays_inert():
    screen = _field()
    header = pygame.Rect(screen._column_layouts[('self', 'village')].header_rect)
    remaining = _press(screen, header.center)
    assert screen._compartment_sheet is None
    assert len(remaining) == 1


def test_open_sheet_consumes_every_event():
    """The sheet is modal; nothing underneath may act on the same batch."""
    screen = _field()
    header = pygame.Rect(screen._column_layouts[('self', 'castle')].header_rect)
    _press(screen, header.center)
    assert screen._compartment_sheet is not None

    remaining = screen.handle_column_events([
        pygame.event.Event(pygame.MOUSEMOTION, pos=(5, 5)),
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(5, 5)),
    ])
    assert remaining == []


def test_sheet_close_restores_the_borrowed_icons():
    """The sheet resizes shared icons; closing must put them back."""
    screen = _field()
    key = ('self', 'castle')
    screen._sync_column_layouts()
    dense_scale = screen._column_layouts[key].icon_render_scale
    for icon in screen.figure_icons:
        icon.set_render_scale(dense_scale)
        icon.power_badge_only = True

    header = pygame.Rect(screen._column_layouts[key].header_rect)
    _press(screen, header.center)
    sheet = screen._compartment_sheet
    assert sheet is not None

    sheet.close()
    for icon in sheet.icons:
        assert icon.render_scale == pytest.approx(dense_scale)
        assert icon.power_badge_only is True


def test_escape_closes_the_sheet():
    screen = _field()
    header = pygame.Rect(screen._column_layouts[('self', 'castle')].header_rect)
    _press(screen, header.center)
    assert screen._compartment_sheet is not None

    screen.handle_column_events([
        pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE)])
    assert screen._compartment_sheet is None
    assert screen._sheet_icon_ids == set()


# ── Hit gating ──────────────────────────────────────────────────────


class _ClipRecordingIcon(_Icon):
    """Records the clip that was in force while it drew."""

    def __init__(self, figure, window):
        super().__init__(figure)
        self.window = window
        self.clip_when_drawn = 'not drawn'

    def draw(self, x, y):
        self.clip_when_drawn = self.window.get_clip()

    def set_position(self, x, y):
        pass


def test_resting_icons_are_clipped_to_their_column():
    """Otherwise a scrolled row paints over the column above and below it."""
    screen = _field()
    layout = screen._column_layouts[('self', 'castle')]
    figure = screen.categorized_figures['self']['castle'][0]
    icon = _ClipRecordingIcon(figure, screen.window)
    screen._figure_entrance_anims = {}

    screen._draw_icon_with_entrance(icon, 100, 100)
    assert icon.clip_when_drawn == pygame.Rect(layout.content_rect)
    # The clip is restored afterwards, or everything drawn later is cut too.
    assert screen.window.get_clip() == screen.window.get_rect()


def test_a_popped_out_icon_is_not_clipped():
    """Hovering deliberately spills past the column so it reads whole."""
    screen = _field()
    figure = screen.categorized_figures['self']['castle'][0]
    icon = _ClipRecordingIcon(figure, screen.window)
    icon.hovered = True
    screen._figure_entrance_anims = {}

    screen._draw_icon_with_entrance(icon, 100, 100)
    assert icon.clip_when_drawn == screen.window.get_rect()


def test_icons_in_columns_that_fit_are_not_clipped():
    screen = _field()
    figure = screen.categorized_figures['self']['village'][0]
    icon = _ClipRecordingIcon(figure, screen.window)
    screen._figure_entrance_anims = {}

    screen._draw_icon_with_entrance(icon, 100, 100)
    assert icon.clip_when_drawn == screen.window.get_rect()


def test_hidden_icons_report_no_hit_area():
    icon = _Icon(SimpleNamespace(id=1, family=SimpleNamespace(field='castle')))
    icon.hit_rect = pygame.Rect(10, 10, 40, 40)
    assert icon.hit_area() is not None

    icon.hit_suppressed = True
    assert icon.hit_area() is None


def test_real_icon_hit_area_honours_the_gates():
    """The gate lives on FigureIcon itself, not just the test double."""
    from game.components.figures.figure_icon import FigureIcon

    icon = object.__new__(FigureIcon)
    icon.rect_frame = pygame.Rect(0, 0, 20, 20)
    icon.draw_name = False
    assert icon.hit_area() == pygame.Rect(0, 0, 20, 20)

    icon.hit_rect = pygame.Rect(5, 5, 60, 60)
    assert icon.hit_area() == pygame.Rect(5, 5, 60, 60)

    icon.hit_suppressed = True
    assert icon.hit_area() is None
    assert icon.collide() is False
