# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Pure layout helper for the unified conquer battlefield screen.

All dimensions are expressed as percentages of screen width (W) and screen
height (H).  The helper has no pygame dependency so it can be unit-tested
in isolation, and is the single source of truth for every named zone on
the conquer screen (header, content canvas, battlefield, field columns,
duel lane, support strips, tactics rail subzones, round ledger cards,
total resolve circle).

The layout has three modes:

* ``"pre_battle"`` — full timeline header (h=20% H), tactics rail on the
  left, battlefield on the right, round ledger across the bottom.
* ``"battle"`` — header collapses to a thin status strip (~5% H) plus a
  round narration log (~6% H); rail/battlefield grow taller; ledger
  unchanged.
* ``"result"`` — same as ``battle`` (status strip stays); ledger total
  card morphs into the resolve/result control.

Mobile/narrow rendering swaps the columns into a stacked single-column
layout (timeline → battlefield → tactics → ledger).  All asserts live in
:func:`_validate` so that any zone with a negative size or any neighbor
overlap fails fast at construction time.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple


Rect = Tuple[int, int, int, int]  # (x, y, w, h) in pixels (post-snap)


# ── Layout percentages (single source of truth) ─────────────────────
# All values are fractions of the screen width (W) or height (H).

# Outer canvas margins
_MARGIN_X_PCT = 0.025
_MARGIN_BOTTOM_PCT = 0.0333

# Header modes
_HEADER_PRE_BATTLE_H_PCT = 0.20
_STATUS_STRIP_H_PCT = 0.05
_LOG_STRIP_H_PCT = 0.06

# Vertical layout
_HEADER_TO_CONTENT_GAP_H_PCT = 0.0185   # gap between header and content
_CONTENT_TO_LEDGER_GAP_H_PCT = 0.0167
_LEDGER_H_PCT = 0.1685                  # ledger band height (pre+battle modes)

# Tactics rail (LEFT) — battlefield (RIGHT)
_RAIL_X_PCT = 0.025
_RAIL_W_PCT = 0.225
_RAIL_TO_FIELD_GAP_W_PCT = 0.0125
_FIELD_X_PCT = _RAIL_X_PCT + _RAIL_W_PCT + _RAIL_TO_FIELD_GAP_W_PCT
_FIELD_W_PCT = 1.0 - _FIELD_X_PCT - _MARGIN_X_PCT

# Battlefield inner padding
_FIELD_INNER_PAD_X_PCT = 0.00833
_FIELD_INNER_PAD_Y_PCT = 0.024

# Battlefield columns + duel lane
_FIELD_COL_W_PCT = 0.0813
_FIELD_LANE_W_PCT = 0.1458

# Tactics rail inner layout
_RAIL_INNER_PAD_X_PCT = 0.00833
_RAIL_INNER_PAD_Y_PCT = 0.015
_RAIL_TOP_STRIP_H_PCT = 0.059
_RAIL_DETAIL_H_PCT = 0.107
_RAIL_ACTION_TRAY_H_PCT = 0.063
_RAIL_CELL_H_PCT = 0.12
_RAIL_CELLS_VISIBLE = 5

# Ledger inner layout
_LEDGER_INNER_PAD_X_PCT = 0.00833
_LEDGER_INNER_PAD_Y_PCT = 0.0185
_LEDGER_ROUND_CARD_W_PCT = 0.254
_LEDGER_TOTAL_CARD_W_PCT = 0.146
_LEDGER_CARD_GAP_W_PCT = 0.005

# Duel lane bands (fractions of lane height, with gaps absorbed)
_LANE_FIGHTER_BAND_H_FRAC = 0.36
_LANE_DIFF_BAND_H_FRAC = 0.24
_LANE_BAND_GAP_H_FRAC = 0.04

# Support strip widths (inside the duel lane)
_SUPPORT_BADGE_RAIL_W_PCT = 0.035
_SUPPORT_CHIP_RAIL_W_PCT = 0.015

# Narrow / mobile breakpoint (W/H aspect ratio)
_NARROW_ASPECT_RATIO = 1.30


# ── Public dataclasses ────────────────────────────────────────────────


@dataclass(frozen=True)
class HeaderLayout:
    """Header zone(s) above the content canvas."""

    mode: str  # 'pre_battle' | 'battle' | 'result'
    full_rect: Rect                # entire header band (y=0)
    timeline_rect: Optional[Rect]  # full timeline panel (pre-battle only)
    status_strip_rect: Optional[Rect]
    log_strip_rect: Optional[Rect]


@dataclass(frozen=True)
class FieldColumns:
    you_castle: Rect
    you_village: Rect
    you_military: Rect
    opp_military: Rect
    opp_village: Rect
    opp_castle: Rect


@dataclass(frozen=True)
class DuelLane:
    rect: Rect
    you_fighter_band: Rect
    diff_band: Rect
    opp_fighter_band: Rect
    you_support_badge_rail: Rect
    you_support_chip_rail: Rect
    opp_support_badge_rail: Rect
    opp_support_chip_rail: Rect


@dataclass(frozen=True)
class BattlefieldLayout:
    rect: Rect            # outer battlefield panel
    inner_rect: Rect      # padded interior (where columns/lane render)
    columns: FieldColumns
    duel_lane: DuelLane


@dataclass(frozen=True)
class TacticsRailLayout:
    rect: Rect
    inner_rect: Rect
    top_strip_rect: Rect
    selected_detail_rect: Rect
    hand_list_rect: Rect      # scroll viewport
    action_tray_rect: Rect
    cell_height: int          # px per visible hand cell
    cells_visible: int


@dataclass(frozen=True)
class RoundLedgerLayout:
    rect: Rect
    inner_rect: Rect
    round_card_rects: Tuple[Rect, Rect, Rect]  # round 1, 2, 3
    total_card_rect: Rect
    total_circle_rect: Rect    # bounding square for the resolve circle


@dataclass(frozen=True)
class ConquerLayout:
    """Top-level layout result for the unified conquer screen."""

    screen_size: Tuple[int, int]
    mode: str                  # 'pre_battle' | 'battle' | 'result'
    narrow: bool               # stacked / mobile layout
    header: HeaderLayout
    content_rect: Rect         # union of battlefield + tactics rail
    battlefield: BattlefieldLayout
    tactics_rail: TacticsRailLayout
    round_ledger: RoundLedgerLayout

    def as_dict(self) -> Dict:
        """Convenience for tests: nested dict of all rects."""
        return asdict(self)


# ── Computation helpers ───────────────────────────────────────────────


def _r(w: float, h_or_x=None, ww=None, hh=None) -> Rect:
    """Snap (x, y, w, h) floats to integer pixels."""
    # Allow either _r((x, y, w, h)) or _r(x, y, w, h)
    if isinstance(w, tuple):
        x, y, ww2, hh2 = w
        return (int(round(x)), int(round(y)),
                max(0, int(round(ww2))), max(0, int(round(hh2))))
    return (int(round(w)), int(round(h_or_x)),
            max(0, int(round(ww))), max(0, int(round(hh))))


def _is_narrow(screen_w: int, screen_h: int, narrow: Optional[bool]) -> bool:
    if narrow is not None:
        return bool(narrow)
    if screen_h <= 0:
        return False
    return (screen_w / screen_h) < _NARROW_ASPECT_RATIO


def _compute_header(W: int, H: int, mode: str) -> HeaderLayout:
    if mode == 'pre_battle':
        h = int(round(_HEADER_PRE_BATTLE_H_PCT * H))
        full = _r(0, 0, W, h)
        return HeaderLayout(
            mode=mode,
            full_rect=full,
            timeline_rect=full,
            status_strip_rect=None,
            log_strip_rect=None,
        )
    # battle / result share collapsed status + log strips
    status_h = int(round(_STATUS_STRIP_H_PCT * H))
    log_h = int(round(_LOG_STRIP_H_PCT * H))
    status = _r(0, 0, W, status_h)
    log = _r(0, status_h, W, log_h)
    full = _r(0, 0, W, status_h + log_h)
    return HeaderLayout(
        mode=mode,
        full_rect=full,
        timeline_rect=None,
        status_strip_rect=status,
        log_strip_rect=log,
    )


def _compute_content_y_band(W: int, H: int, header: HeaderLayout) -> Tuple[int, int]:
    """Return (content_y, content_h) for the band between header and ledger."""
    header_bottom = header.full_rect[1] + header.full_rect[3]
    gap = int(round(_HEADER_TO_CONTENT_GAP_H_PCT * H))
    ledger_h = int(round(_LEDGER_H_PCT * H))
    bottom_margin = int(round(_MARGIN_BOTTOM_PCT * H))
    ledger_top = H - bottom_margin - ledger_h
    content_y = header_bottom + gap
    content_to_ledger_gap = int(round(_CONTENT_TO_LEDGER_GAP_H_PCT * H))
    content_h = max(0, ledger_top - content_y - content_to_ledger_gap)
    return content_y, content_h


def _compute_battlefield(W: int, H: int,
                         x_px: int, y_px: int,
                         w_px: int, h_px: int) -> BattlefieldLayout:
    """Battlefield outer rect + inner columns + duel lane."""
    rect = _r(x_px, y_px, w_px, h_px)
    pad_x = int(round(_FIELD_INNER_PAD_X_PCT * W))
    pad_y = int(round(_FIELD_INNER_PAD_Y_PCT * H))
    inner = _r(x_px + pad_x, y_px + pad_y,
               w_px - 2 * pad_x, h_px - 2 * pad_y)

    col_w = int(round(_FIELD_COL_W_PCT * W))
    lane_w = int(round(_FIELD_LANE_W_PCT * W))
    inner_x, inner_y, inner_w, inner_h = inner

    # Lane is centred between the two 3-column blocks, sharing inner_w.
    # Layout: [c][v][m]  [lane]  [m][v][c]
    block_w = 3 * col_w
    total = 2 * block_w + lane_w
    # If inner_w is wider than total, distribute the slack evenly as gutters.
    slack = max(0, inner_w - total)
    side_pad = slack // 2
    you_x0 = inner_x + side_pad

    cy = inner_y
    ch = inner_h
    columns = FieldColumns(
        you_castle=_r(you_x0 + 0 * col_w, cy, col_w, ch),
        you_village=_r(you_x0 + 1 * col_w, cy, col_w, ch),
        you_military=_r(you_x0 + 2 * col_w, cy, col_w, ch),
        opp_military=_r(you_x0 + 3 * col_w + lane_w, cy, col_w, ch),
        opp_village=_r(you_x0 + 4 * col_w + lane_w, cy, col_w, ch),
        opp_castle=_r(you_x0 + 5 * col_w + lane_w, cy, col_w, ch),
    )

    lane_x = you_x0 + block_w
    lane_rect = _r(lane_x, cy, lane_w, ch)

    # Lane vertical bands
    band_gap = max(1, int(round(_LANE_BAND_GAP_H_FRAC * ch)))
    fighter_h = int(round(_LANE_FIGHTER_BAND_H_FRAC * ch))
    diff_h = max(0, ch - 2 * fighter_h - 2 * band_gap)
    you_fighter = _r(lane_x, cy, lane_w, fighter_h)
    diff_band = _r(lane_x, cy + fighter_h + band_gap, lane_w, diff_h)
    opp_fighter = _r(lane_x, cy + fighter_h + band_gap + diff_h + band_gap,
                     lane_w, fighter_h)

    # Support strips: inside-left (player) and inside-right (opponent)
    badge_w = int(round(_SUPPORT_BADGE_RAIL_W_PCT * W))
    chip_w = int(round(_SUPPORT_CHIP_RAIL_W_PCT * W))
    # Player-side rails sit just inside the lane's left edge; opponent's
    # rails sit just inside the lane's right edge.
    you_chip = _r(lane_x, cy, chip_w, ch)
    you_badge = _r(lane_x + chip_w, cy, badge_w, ch)
    opp_badge = _r(lane_x + lane_w - chip_w - badge_w, cy, badge_w, ch)
    opp_chip = _r(lane_x + lane_w - chip_w, cy, chip_w, ch)

    duel = DuelLane(
        rect=lane_rect,
        you_fighter_band=you_fighter,
        diff_band=diff_band,
        opp_fighter_band=opp_fighter,
        you_support_badge_rail=you_badge,
        you_support_chip_rail=you_chip,
        opp_support_badge_rail=opp_badge,
        opp_support_chip_rail=opp_chip,
    )

    return BattlefieldLayout(
        rect=rect, inner_rect=inner, columns=columns, duel_lane=duel
    )


def _compute_tactics_rail(W: int, H: int,
                          x_px: int, y_px: int,
                          w_px: int, h_px: int) -> TacticsRailLayout:
    rect = _r(x_px, y_px, w_px, h_px)
    pad_x = int(round(_RAIL_INNER_PAD_X_PCT * W))
    pad_y = int(round(_RAIL_INNER_PAD_Y_PCT * H))
    inner = _r(x_px + pad_x, y_px + pad_y,
               w_px - 2 * pad_x, h_px - 2 * pad_y)
    ix, iy, iw, ih = inner

    top_h = int(round(_RAIL_TOP_STRIP_H_PCT * H))
    detail_h = int(round(_RAIL_DETAIL_H_PCT * H))
    action_h = int(round(_RAIL_ACTION_TRAY_H_PCT * H))
    cell_h = int(round(_RAIL_CELL_H_PCT * H))

    # Hand list takes whatever is left between detail and action tray.
    list_y = iy + top_h + detail_h
    list_bottom = iy + ih - action_h
    list_h = max(0, list_bottom - list_y)

    return TacticsRailLayout(
        rect=rect,
        inner_rect=inner,
        top_strip_rect=_r(ix, iy, iw, top_h),
        selected_detail_rect=_r(ix, iy + top_h, iw, detail_h),
        hand_list_rect=_r(ix, list_y, iw, list_h),
        action_tray_rect=_r(ix, list_bottom, iw, action_h),
        cell_height=cell_h,
        cells_visible=_RAIL_CELLS_VISIBLE,
    )


def _compute_round_ledger(W: int, H: int,
                          x_px: int, y_px: int,
                          w_px: int, h_px: int) -> RoundLedgerLayout:
    rect = _r(x_px, y_px, w_px, h_px)
    pad_x = int(round(_LEDGER_INNER_PAD_X_PCT * W))
    pad_y = int(round(_LEDGER_INNER_PAD_Y_PCT * H))
    inner = _r(x_px + pad_x, y_px + pad_y,
               w_px - 2 * pad_x, h_px - 2 * pad_y)
    ix, iy, iw, ih = inner

    round_w = int(round(_LEDGER_ROUND_CARD_W_PCT * W))
    total_w = int(round(_LEDGER_TOTAL_CARD_W_PCT * W))
    gap = int(round(_LEDGER_CARD_GAP_W_PCT * W))

    # Lay rounds left-to-right, total card anchored right.
    round_rects: List[Rect] = []
    for i in range(3):
        round_rects.append(_r(ix + i * (round_w + gap), iy, round_w, ih))
    total_x = ix + iw - total_w
    total_card = _r(total_x, iy, total_w, ih)

    # Total resolve circle: square centred in the total card, diameter
    # ≈ min(total_card_w, ih) (the plan calls out ~10.4% H).
    diameter = min(total_w, ih)
    cx = total_x + total_w // 2
    cy = iy + ih // 2
    total_circle = _r(cx - diameter // 2, cy - diameter // 2, diameter, diameter)

    return RoundLedgerLayout(
        rect=rect,
        inner_rect=inner,
        round_card_rects=tuple(round_rects),  # type: ignore[arg-type]
        total_card_rect=total_card,
        total_circle_rect=total_circle,
    )


# ── Public entry point ────────────────────────────────────────────────


def compute_conquer_layout(screen_w: int, screen_h: int,
                           mode: str = 'pre_battle',
                           narrow: Optional[bool] = None) -> ConquerLayout:
    """Compute every named rect for the unified conquer screen.

    Args:
        screen_w/screen_h: pixel dimensions of the target surface.
        mode: ``'pre_battle'`` (full timeline header), ``'battle'`` or
            ``'result'`` (collapsed status + log strips).
        narrow: force narrow/stacked layout; auto-detected from aspect
            ratio when ``None``.
    """
    if mode not in ('pre_battle', 'battle', 'result'):
        raise ValueError(f"Unknown conquer layout mode: {mode!r}")
    if screen_w <= 0 or screen_h <= 0:
        raise ValueError(f"Invalid screen size: {screen_w}x{screen_h}")

    W, H = int(screen_w), int(screen_h)
    is_narrow = _is_narrow(W, H, narrow)
    header = _compute_header(W, H, mode)
    content_y, content_h = _compute_content_y_band(W, H, header)
    margin_x = int(round(_MARGIN_X_PCT * W))
    bottom_margin = int(round(_MARGIN_BOTTOM_PCT * H))
    ledger_h = int(round(_LEDGER_H_PCT * H))
    ledger_y = H - bottom_margin - ledger_h
    ledger_x = margin_x
    ledger_w = W - 2 * margin_x

    if not is_narrow:
        rail_x = int(round(_RAIL_X_PCT * W))
        rail_w = int(round(_RAIL_W_PCT * W))
        field_x = int(round(_FIELD_X_PCT * W))
        field_w = int(round(_FIELD_W_PCT * W))
        # Snap rail_x_end + gap to field_x to avoid 1px overlaps from rounding.
        gap = int(round(_RAIL_TO_FIELD_GAP_W_PCT * W))
        if rail_x + rail_w + gap > field_x:
            rail_w = max(0, field_x - rail_x - gap)
        rail = _compute_tactics_rail(W, H, rail_x, content_y, rail_w, content_h)
        battlefield = _compute_battlefield(W, H, field_x, content_y, field_w, content_h)
    else:
        # Narrow / stacked: tactics rail above battlefield (full width, half each).
        full_x = margin_x
        full_w = W - 2 * margin_x
        half_h = max(0, content_h // 2 - int(round(0.01 * H)))
        # Plan stack order: timeline → battlefield → tactics → ledger
        battlefield = _compute_battlefield(
            W, H, full_x, content_y, full_w, half_h)
        rail_y = content_y + half_h + int(round(0.01 * H))
        rail_h = max(0, content_y + content_h - rail_y)
        rail = _compute_tactics_rail(W, H, full_x, rail_y, full_w, rail_h)

    ledger = _compute_round_ledger(W, H, ledger_x, ledger_y, ledger_w, ledger_h)

    content_rect = _r(
        min(rail.rect[0], battlefield.rect[0]),
        content_y,
        max(rail.rect[0] + rail.rect[2],
            battlefield.rect[0] + battlefield.rect[2]) - min(rail.rect[0], battlefield.rect[0]),
        content_h,
    )

    layout = ConquerLayout(
        screen_size=(W, H),
        mode=mode,
        narrow=is_narrow,
        header=header,
        content_rect=content_rect,
        battlefield=battlefield,
        tactics_rail=rail,
        round_ledger=ledger,
    )
    _validate(layout)
    return layout


# ── Validation ────────────────────────────────────────────────────────


def _intersects(a: Rect, b: Rect, tolerance: int = 1) -> bool:
    """Return True if rects ``a`` and ``b`` overlap by more than ``tolerance``."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    if aw <= 0 or ah <= 0 or bw <= 0 or bh <= 0:
        return False
    overlap_w = min(ax + aw, bx + bw) - max(ax, bx)
    overlap_h = min(ay + ah, by + bh) - max(ay, by)
    return overlap_w > tolerance and overlap_h > tolerance


def _contains(parent: Rect, child: Rect, tolerance: int = 1) -> bool:
    px, py, pw, ph = parent
    cx, cy, cw, ch = child
    return (cx + tolerance >= px
            and cy + tolerance >= py
            and cx + cw <= px + pw + tolerance
            and cy + ch <= py + ph + tolerance)


def _validate(layout: ConquerLayout) -> None:
    """Assert layout invariants. Raises ``AssertionError`` on violation."""
    W, H = layout.screen_size
    screen_rect: Rect = (0, 0, W, H)

    def positive(name: str, rect: Rect) -> None:
        x, y, w, h = rect
        assert w > 0 and h > 0, f"zone {name} has non-positive size: {rect}"

    # Every named zone must have positive size and fit inside the screen.
    zones: Dict[str, Rect] = {
        'header.full_rect': layout.header.full_rect,
        'content_rect': layout.content_rect,
        'battlefield': layout.battlefield.rect,
        'battlefield.inner': layout.battlefield.inner_rect,
        'tactics_rail': layout.tactics_rail.rect,
        'tactics_rail.inner': layout.tactics_rail.inner_rect,
        'tactics_rail.top_strip': layout.tactics_rail.top_strip_rect,
        'tactics_rail.selected_detail': layout.tactics_rail.selected_detail_rect,
        'tactics_rail.hand_list': layout.tactics_rail.hand_list_rect,
        'tactics_rail.action_tray': layout.tactics_rail.action_tray_rect,
        'round_ledger': layout.round_ledger.rect,
        'round_ledger.inner': layout.round_ledger.inner_rect,
        'round_ledger.total_card': layout.round_ledger.total_card_rect,
        'round_ledger.total_circle': layout.round_ledger.total_circle_rect,
        'duel_lane': layout.battlefield.duel_lane.rect,
        'duel_lane.diff_band': layout.battlefield.duel_lane.diff_band,
        'duel_lane.you_fighter': layout.battlefield.duel_lane.you_fighter_band,
        'duel_lane.opp_fighter': layout.battlefield.duel_lane.opp_fighter_band,
    }
    for name, rect in zones.items():
        positive(name, rect)
        assert _contains(screen_rect, rect), \
            f"zone {name} {rect} escapes screen {screen_rect}"

    # Field columns
    for name in ('you_castle', 'you_village', 'you_military',
                 'opp_military', 'opp_village', 'opp_castle'):
        rect = getattr(layout.battlefield.columns, name)
        positive(f'columns.{name}', rect)
        assert _contains(layout.battlefield.inner_rect, rect, tolerance=2), \
            f"column {name} {rect} escapes battlefield inner {layout.battlefield.inner_rect}"

    # Round cards
    for i, rect in enumerate(layout.round_ledger.round_card_rects):
        positive(f'round_card_{i}', rect)
        assert _contains(layout.round_ledger.inner_rect, rect, tolerance=2), \
            f"round_card_{i} {rect} escapes ledger inner"

    # Total circle inside total card
    assert _contains(layout.round_ledger.total_card_rect,
                     layout.round_ledger.total_circle_rect, tolerance=2), \
        "total_circle escapes total_card"

    # Battlefield + tactics rail must not overlap each other (desktop only)
    if not layout.narrow:
        assert not _intersects(layout.battlefield.rect, layout.tactics_rail.rect), \
            f"battlefield and tactics rail overlap"

    # Header must not overlap content or ledger
    assert not _intersects(layout.header.full_rect, layout.content_rect), \
        "header overlaps content"
    assert not _intersects(layout.header.full_rect, layout.round_ledger.rect), \
        "header overlaps ledger"
    assert not _intersects(layout.content_rect, layout.round_ledger.rect), \
        "content overlaps ledger"

    # Lane bands must not overlap each other
    lane = layout.battlefield.duel_lane
    bands = (lane.you_fighter_band, lane.diff_band, lane.opp_fighter_band)
    for i in range(len(bands)):
        for j in range(i + 1, len(bands)):
            assert not _intersects(bands[i], bands[j]), \
                f"lane bands {i} and {j} overlap"
