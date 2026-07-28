# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Touch-path and worst-case coverage for the mobile conquer battle UI.

The hover-only explanations gained tap-to-pin parity (timeline steps,
support chips, ledger rounds) plus mobile-specific compact renderers.
These tests exercise the tap paths — previously only hover was tested —
and the worst-case content that used to truncate or collide.
"""

from types import SimpleNamespace

import pygame
import pytest


def _settings():
    from config import settings
    return settings


def _rect_has_non_background_pixel(surface, rect, background=(0, 0, 0)):
    bounds = pygame.Rect(rect).clip(surface.get_rect())
    step_x = max(1, bounds.width // 12)
    step_y = max(1, bounds.height // 12)
    for x in range(bounds.left, bounds.right, step_x):
        for y in range(bounds.top, bounds.bottom, step_y):
            if surface.get_at((x, y))[:3] != background:
                return True
    return False


@pytest.fixture
def touch_mode(monkeypatch):
    """Simulate the mobile runtime: non-zero touch targets."""
    settings = _settings()
    monkeypatch.setattr(settings, 'TOUCH_TARGET_MIN', 58)
    monkeypatch.setattr(settings, 'TOUCH_COMPACT_MIN', 33)
    monkeypatch.setattr(settings, 'TOUCH_HIT_PAD', 8)


def _step(kind='decision', title='Decide', headline='', body='',
          interactive=False, active=True, completed=False):
    from game.screens.conquer_flow import TimelineStep

    return TimelineStep(
        kind=kind,
        title=title,
        active=active,
        completed=completed,
        interactive=interactive,
        info_headline=headline,
        info_body=body,
    )


# ── Timeline tap-to-pin ──────────────────────────────────────────────


def _panel_with_tap_rects(steps_rects):
    from game.components.conquer_timeline_panel import ConquerTimelinePanel

    panel = ConquerTimelinePanel.__new__(ConquerTimelinePanel)
    panel._touch_pinned_step = None
    panel._step_hover = None
    panel._overflow_hover = None
    panel._tap_rects = [
        (panel._step_pin_key(step), pygame.Rect(rect), step)
        for step, rect in steps_rects
    ]
    return panel


def test_timeline_tap_pins_and_unpins_step(touch_mode):
    step = _step(title='Opponent Prelude')
    panel = _panel_with_tap_rects([(step, (100, 100, 40, 30))])

    assert panel.handle_tap((110, 110)) is True
    assert panel._touch_pinned_step == panel._step_pin_key(step)

    panel._apply_touch_pin_to_hover()
    assert panel._step_hover is not None
    assert panel._step_hover[0] is step

    # Tapping the same target again dismisses the pin.
    assert panel.handle_tap((110, 110)) is True
    assert panel._touch_pinned_step is None


def test_timeline_tap_uses_touch_inflation_and_nearest_center(touch_mode):
    near = _step(kind='a', title='near')
    far = _step(kind='b', title='far')
    panel = _panel_with_tap_rects([
        (near, (100, 100, 24, 24)),
        (far, (140, 100, 24, 24)),
    ])
    # 10px outside the near bubble — inside its inflated hit rect, and
    # closer to `near`'s centre than `far`'s.
    assert panel.handle_tap((94, 112)) is True
    assert panel._touch_pinned_step == panel._step_pin_key(near)


def test_timeline_unclaimed_tap_dismisses_but_is_not_consumed(touch_mode):
    step = _step()
    panel = _panel_with_tap_rects([(step, (100, 100, 40, 30))])
    panel._touch_pinned_step = panel._step_pin_key(step)

    assert panel.handle_tap((600, 400)) is False
    assert panel._touch_pinned_step is None


def test_timeline_tap_ignored_on_desktop():
    step = _step()
    panel = _panel_with_tap_rects([(step, (100, 100, 40, 30))])
    assert panel.handle_tap((110, 110)) is False
    assert panel._touch_pinned_step is None


# ── Screen-level single-pin coordination ─────────────────────────────


def _bare_screen():
    from game.screens.conquer_game_screen import ConquerGameScreen

    screen = ConquerGameScreen.__new__(ConquerGameScreen)
    screen._conquer_support_touch_pin = None
    return screen


def test_single_pin_rule_dismisses_other_surfaces():
    screen = _bare_screen()
    cleared = []
    screen._conquer_timeline_panel = SimpleNamespace(
        clear_touch_pin=lambda: cleared.append('timeline'))
    screen._round_ledger = SimpleNamespace(
        clear_touch_pin=lambda: cleared.append('ledger'))
    screen._conquer_support_touch_pin = ('badge', True, 'clash', 'x', '', '', ())

    screen._clear_conquer_touch_pins(except_for='support')
    assert cleared == ['timeline', 'ledger']
    assert screen._conquer_support_touch_pin is not None

    screen._clear_conquer_touch_pins()
    assert screen._conquer_support_touch_pin is None


def test_support_tap_target_inflates_and_picks_nearest(touch_mode, monkeypatch):
    settings = _settings()
    monkeypatch.setattr(settings, 'SCREEN_WIDTH', 854)
    monkeypatch.setattr(settings, 'SCREEN_HEIGHT', 480)
    screen = _bare_screen()
    near = {'rect': pygame.Rect(400, 100, 30, 30),
            'entry': {'kind': 'aggregate_support'}, 'is_player': True}
    far = {'rect': pygame.Rect(400, 150, 30, 30),
           'entry': {'kind': 'aggregate_ranged'}, 'is_player': True}
    screen._conquer_support_badge_rects = [near, far]
    screen._conquer_support_overflow_rects = []

    # Between the two chips but closer to `near`'s centre; only reachable
    # through touch inflation.
    kind, info = screen._conquer_support_tap_target((440, 120))
    assert kind == 'badge'
    assert info is near


def test_ledger_pin_clear_helper():
    from game.components.conquer_round_ledger import ConquerRoundLedger

    ledger = ConquerRoundLedger.__new__(ConquerRoundLedger)
    ledger._touch_round_idx = 2
    ledger.clear_touch_pin()
    assert ledger._touch_round_idx is None


# ── Support chip aggregation ─────────────────────────────────────────


def _summary(screen, entries):
    sections = {'clash': entries}
    return screen._conquer_support_chip_summary(sections)


def test_chip_summary_folds_support_and_land_and_keeps_ranged_separate():
    screen = _bare_screen()
    chips = _summary(screen, [
        {'kind': 'support_bonus', 'numeric_value': 4,
         'source_figure_ids': [1], 'source_entries': None},
        {'kind': 'land_bonus', 'numeric_value': 2,
         'source_figure_ids': [], 'source_entries': None},
        {'kind': 'distance_attack', 'numeric_value': 3,
         'source_figure_ids': [2], 'source_entries': None},
    ])
    by_kind = {c['kind']: c for c in chips}
    assert by_kind['aggregate_support']['value'] == '+6'
    assert by_kind['aggregate_support']['source_figure_ids'] == [1]
    assert by_kind['aggregate_ranged']['value'] == '-3'
    assert by_kind['aggregate_ranged']['source_figure_ids'] == [2]


def test_mobile_support_rail_title_describes_all_modifier_types():
    from game.screens.conquer_game_screen import ConquerGameScreen

    assert ConquerGameScreen.MOBILE_SUPPORT_RAIL_TITLE == 'MOD'


def test_chip_summary_uses_unblocked_value_for_blocked_support():
    screen = _bare_screen()
    chips = _summary(screen, [
        {'kind': 'support_bonus', 'numeric_value': 4, 'blocked_bonus': True,
         'unblocked_numeric_value': 1, 'source_figure_ids': [1]},
    ])
    assert chips[0]['value'] == '+1'


def test_chip_summary_landslide_lowers_support_sum():
    screen = _bare_screen()
    chips = _summary(screen, [
        {'kind': 'support_bonus', 'numeric_value': 4, 'source_figure_ids': [1]},
        {'kind': 'land_bonus', 'numeric_value': -2, 'source_figure_ids': []},
    ])
    by_kind = {c['kind']: c for c in chips}
    assert by_kind['aggregate_support']['value'] == '+2'
    assert 'aggregate_ranged' not in by_kind


def test_chip_summary_counts_blocks_and_passes_called_through():
    screen = _bare_screen()
    called = {'kind': 'called', 'move': {'family_name': 'Call Military'},
              'source_figure_ids': [9]}
    chips = _summary(screen, [
        {'kind': 'blocks_bonus', 'aggregate_count': 2, 'source_figure_ids': [3]},
        called,
    ])
    by_kind = {c['kind']: c for c in chips}
    assert by_kind['aggregate_block']['value'] == 'x2'
    assert chips[-1] is called


def test_chip_summary_pin_keys_are_stable_across_frames():
    screen = _bare_screen()
    entries = [
        {'kind': 'support_bonus', 'numeric_value': 4, 'source_figure_ids': [1]},
    ]
    chips_a = _summary(screen, entries)
    chips_b = _summary(screen, entries)
    key_a = screen._conquer_support_pin_key(
        {'entry': chips_a[0], 'is_player': True})
    key_b = screen._conquer_support_pin_key(
        {'entry': chips_b[0], 'is_player': True})
    assert key_a == key_b


# ── Pinned chip drives the hover pipeline ────────────────────────────


def test_pinned_chip_substitutes_for_hover_entry(touch_mode):
    screen = _bare_screen()
    entry = {'kind': 'aggregate_support', 'label': 'SUP', 'value': '+6',
             'section': 'aggregate', 'source_figure_ids': [1]}
    info = {'rect': pygame.Rect(0, 0, 30, 30), 'entry': entry,
            'is_player': True, 'source_figure_ids': [1], 'figure_id': None}
    screen._conquer_support_badge_rects = [info]
    screen._conquer_support_touch_pin = screen._conquer_support_pin_key(info)

    assert screen._current_conquer_support_hover_entry() is info

    # A stale pin (chips changed) yields no hover entry instead of a wrong one.
    screen._conquer_support_touch_pin = ('badge', True, 'aggregate', 'other',
                                         '', '', ())
    assert screen._current_conquer_support_hover_entry() is None


# ── Compact ledger (worst-case short band) ───────────────────────────


class _LedgerParent:
    def __init__(self, window, moves):
        self.window = window
        self.state = SimpleNamespace(game=SimpleNamespace(
            battle_round=1, last_battle_result=None))
        self.subscreens = {'battle': SimpleNamespace(opp_played=[])}
        self._moves = moves

    def _current_conquer_battle_moves(self):
        return list(self._moves)

    def _conquer_battle_move_icon_assets(self, icon_size):
        settings = _settings()
        return ({}, {}, {}, {}, settings.get_font(max(8, icon_size // 3), bold=True))


def _compact_ledger(window):
    from game.components.conquer_round_ledger import ConquerRoundLedger

    move = {'id': 1, 'family_name': 'Shield', 'suit': 'Clubs', 'rank': '9',
            'value': 3, 'played_round': 0, 'status': 'played'}
    parent = _LedgerParent(window, [move])
    ledger = ConquerRoundLedger.__new__(ConquerRoundLedger)
    ledger._parent = parent
    ledger.window = window
    ledger._round_reveal_animations = {}
    ledger._revealed_round_keys = {}
    ledger._tally_last_shown = None
    ledger._touch_round_idx = None
    return ledger, move


def test_compact_round_card_renders_chips_and_round_tag():
    window = pygame.Surface((854, 480))
    window.fill((0, 0, 0))
    ledger, move = _compact_ledger(window)

    rect = pygame.Rect(20, 420, 217, 44)  # compact: height < 64
    ledger._draw_round_card(rect, 0, move, None, 1)

    assert _rect_has_non_background_pixel(window, rect)
    # Chips span nearly the whole compact height (no title row reserved).
    chip_band = pygame.Rect(rect.left + 4, rect.top + 4,
                            int(rect.width * 0.30), rect.height - 8)
    assert _rect_has_non_background_pixel(window, chip_band)
    # Nothing bleeds outside the card's row.
    above = pygame.Rect(rect.left, rect.top - 12, rect.width, 10)
    assert not _rect_has_non_background_pixel(window, above)


def test_compact_round_chip_uses_icon_as_only_power_readout(
        touch_mode, monkeypatch):
    """The icon already owns the move-power label on mobile round cards."""
    window = pygame.Surface((854, 480))
    window.fill((0, 0, 0))
    ledger, move = _compact_ledger(window)
    rect = pygame.Rect(24, 424, 66, 36)
    icon_calls = []

    monkeypatch.setattr(
        ledger,
        '_draw_move_icon',
        lambda cx, cy, size, rendered_move, ghost=False: (
            icon_calls.append((cx, cy, size, rendered_move, ghost)) or True
        ),
    )

    def unexpected_text(*_args, **_kwargs):
        raise AssertionError(
            'compact tactic chip must not render a second power/name label')

    monkeypatch.setattr(_settings(), 'get_font', unexpected_text)

    ledger._draw_player_chip(rect, move, is_player_self=True)

    assert len(icon_calls) == 1
    assert icon_calls[0][:2] == rect.center
    assert icon_calls[0][2] == min(rect.height - 4, rect.width - 8)


def test_compact_total_card_keeps_circle_legible():
    window = pygame.Surface((854, 480))
    window.fill((0, 0, 0))
    ledger, _move = _compact_ledger(window)

    rect = pygame.Rect(700, 420, 125, 44)
    circle = pygame.Rect(729, 420, 44, 44)
    ledger._draw_total_card(rect, circle, [None, None, None], [None, None, None])

    assert ledger._total_circle_rect is not None
    # Side-by-side compact layout: the circle keeps ≥ 70% of the band height
    # instead of collapsing under a stacked caption.
    assert ledger._total_circle_rect.height >= int(rect.height * 0.7)
    assert _rect_has_non_background_pixel(window, rect)


# ── Worst-case timeline content (mobile compact info box) ────────────


def test_compact_info_box_wraps_long_headline_and_body(touch_mode):
    from game.components.conquer_timeline_panel import ConquerTimelinePanel

    window = pygame.Surface((854, 480))
    window.fill((0, 0, 0))
    settings = _settings()
    panel = ConquerTimelinePanel.__new__(ConquerTimelinePanel)
    panel.window = window
    panel.info_headline_font = settings.get_font(18, bold=True)
    panel.info_body_font = settings.get_font(14)
    panel.button_font = settings.get_font(13, bold=True)
    panel._tap_rects = []

    step = _step(
        kind='prelude_own',
        title='Prelude',
        headline='A very long prelude headline that can never fit on a '
                 'single compact mobile row without wrapping onto a second',
        body='An even longer body explaining exactly what the opponent '
             'did during the prelude and what the player should consider '
             'doing next, far beyond one line of compact row width.',
    )
    screen = SimpleNamespace(_conquer_pending_confirmation=None)

    rect = pygame.Rect(40, 60, 500, 110)
    panel._draw_compact_info_box(screen, rect, step, (255, 235, 170))

    headline_h = panel.info_headline_font.get_height()
    first_line = pygame.Rect(rect.left + 8, rect.top + 8, 200, headline_h)
    second_line = pygame.Rect(rect.left + 8, rect.top + 10 + headline_h,
                              200, headline_h)
    assert _rect_has_non_background_pixel(window, first_line)
    # The old renderer ellipsized to one line; the wrapped headline now
    # paints text into the second line band as well.
    assert _rect_has_non_background_pixel(window, second_line)


# ── Tactics rail: touch navigation ───────────────────────────────────


class _RailParent:
    """Minimal ``ConquerGameScreen`` stand-in for the tactics rail."""

    def __init__(self, window, game, moves):
        self.window = window
        self.state = SimpleNamespace(game=game)
        self.subscreens = {'battle': SimpleNamespace(opp_played=[])}
        self._moves = list(moves)

    def _current_conquer_battle_moves(self):
        return list(self._moves)

    def _conquer_battle_move_icon_assets(self, icon_size):
        settings = _settings()
        return ({}, {}, {}, {},
                settings.get_font(max(8, icon_size // 3), bold=True))


def _tactic(move_id, family='Dagger', suit='Hearts', rank='9', value=9,
            **extra):
    move = {
        'id': move_id,
        'family_name': family,
        'suit': suit,
        'rank': rank,
        'value': value,
        'status': 'available',
        'played_round': None,
    }
    move.update(extra)
    return move


def _touch_rail(moves):
    from config import settings
    from game.components.conquer_tactics_rail import ConquerTacticsRail

    window = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
    game = SimpleNamespace(
        mode='conquer', player_id=1, battle_round=1,
        battle_turn_player_id=1, battle_confirmed=True,
        battle_gamble_counts={}, last_battle_result=None,
    )
    rail = ConquerTacticsRail(_RailParent(window, game, moves))
    rail.draw()
    return rail


def _press(rail, pos):
    rail.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, button=1, pos=pos))


def _drag(rail, pos):
    rail.handle_event(pygame.event.Event(pygame.MOUSEMOTION, pos=pos))


def _release(rail, pos):
    rail.handle_event(pygame.event.Event(
        pygame.MOUSEBUTTONUP, button=1, pos=pos))


def test_tactics_rail_swipe_scrolls_instead_of_combining(touch_mode):
    """The instinctive scroll gesture must never merge two Daggers.

    Drag-to-combine fires an unconfirmed, destructive Combine, and touch
    input reaches the rail as mouse events — so a swipe down a hand full of
    same-colour Daggers used to consume two of them.
    """
    moves = [_tactic(i, suit='Hearts', rank=str(9 - i), value=9 - i)
             for i in range(6)]
    rail = _touch_rail(moves)
    assert len(rail._cell_rects) >= 2

    start = rail._cell_rects[0].center
    target = rail._cell_rects[1].center
    _press(rail, start)
    _drag(rail, (start[0], start[1] - 40))
    assert rail._scroll_px > 0             # the gesture scrolls the list
    # Finish the swipe over a second same-colour Dagger — the exact drop
    # that used to fire Combine.
    _drag(rail, target)
    _release(rail, target)
    rail.draw()

    assert rail.consume_pending_action() is None
    assert rail._selected_id is None       # the optimistic select was undone
    assert rail._drag_origin_id is None    # drag-to-combine never armed


def test_tactics_rail_tap_without_movement_still_selects(touch_mode):
    moves = [_tactic(i) for i in range(4)]
    rail = _touch_rail(moves)

    tap = rail._cell_rects[1].center
    _press(rail, tap)
    _release(rail, tap)

    assert rail._selected_id == rail._cell_move_ids[1]
    assert rail.consume_pending_action() is None


def test_tactics_rail_scroll_arrows_are_not_tap_targets_on_touch(touch_mode):
    """Arrows drawn over the first/last row swallowed taps meant for them."""
    moves = [_tactic(i) for i in range(12)]
    rail = _touch_rail(moves)

    assert len(rail._cell_rects) < len(moves)   # the list really does scroll
    assert rail._scroll_up_rect is None
    assert rail._scroll_down_rect is None

    # A tap in the bottom-right corner of the last row selects that row
    # rather than scrolling the list underneath the finger.
    last_rect = rail._cell_rects[-1]
    probe = (last_rect.right - 6, last_rect.bottom - 4)
    _press(rail, probe)
    _release(rail, probe)
    assert rail._selected_id == rail._cell_move_ids[-1]
    assert rail._scroll_px == 0


def test_tactics_rail_filter_chips_are_tappable_and_disjoint(touch_mode):
    settings = _settings()
    moves = [
        _tactic(1, family='Dagger', suit='Hearts', rank='9', value=9),
        _tactic(2, family='Dagger', suit='Spades', rank='8', value=8),
        _tactic(3, family='Block', suit='Clubs', rank='Q', value=0),
        _tactic(4, family='Call King', suit='Hearts', rank='K', value=5),
    ]
    rail = _touch_rail(moves)

    rects = [rect for _key, rect in rail._filter_chip_rects]
    assert len(rects) == 4                      # All + Dagger + Block + Call
    for rect in rects:
        assert rect.height >= settings.TOUCH_COMPACT_MIN - 4
    for first in range(len(rects)):
        for second in range(first + 1, len(rects)):
            overlap = rects[first].clip(rects[second])
            assert overlap.width <= 0 or overlap.height <= 0, (
                first, second, tuple(rects[first]), tuple(rects[second]))
    # Chips live above the list, never on top of a tactic row.
    for chip in rects:
        for row in rail._cell_rects:
            assert not chip.colliderect(row)


def test_tactics_rail_hand_viewport_does_not_move_while_playing(touch_mode):
    """Selecting a tactic or showing a banner must not resize the hand."""
    moves = [_tactic(i) for i in range(8)]
    rail = _touch_rail(moves)
    baseline = pygame.Rect(rail._dyn_hand_list_rect)
    rows = len(rail._cell_rects)

    tap = rail._cell_rects[-1].center
    _press(rail, tap)
    _release(rail, tap)
    rail.draw()
    assert rail._dyn_hand_list_rect == baseline
    assert len(rail._cell_rects) == rows
    assert rail._selected_id in rail._cell_move_ids   # still on screen

    rail.set_result_banner('Burn Dagger for 2 random tactics? Tap again.')
    rail.draw()
    assert rail._dyn_hand_list_rect == baseline
    assert len(rail._cell_rects) == rows
