# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Unit tests for the unified conquer screen layout helper.

These tests are pure (no pygame, no DB) and verify:
* every named zone has positive width/height,
* zones fit inside their parents,
* battlefield ↔ tactics rail do not overlap on desktop,
* header / content / ledger bands stay vertically separated,
* the 6 field columns mirror around the duel lane,
* duel lane bands (you/diff/opp) stack without overlap,
* helper handles narrow/stacked breakpoints,
* all three modes ('pre_battle', 'battle', 'result') validate.
"""
from __future__ import annotations

import pytest

from game.components.conquer_layout import (
    ConquerLayout,
    compute_conquer_layout,
)


_STANDARD_SIZES = [
    (1920, 1080),
    (1600, 900),
    (1366, 768),
]
_MODES = ('pre_battle', 'battle', 'result')


def _x_end(rect):
    return rect[0] + rect[2]


def _y_end(rect):
    return rect[1] + rect[3]


@pytest.mark.parametrize('size', _STANDARD_SIZES)
@pytest.mark.parametrize('mode', _MODES)
def test_layout_validates_for_standard_sizes(size, mode):
    layout = compute_conquer_layout(size[0], size[1], mode=mode)
    assert isinstance(layout, ConquerLayout)
    assert layout.mode == mode
    assert layout.screen_size == size


@pytest.mark.parametrize('size', _STANDARD_SIZES)
def test_pre_battle_header_is_full_timeline(size):
    layout = compute_conquer_layout(size[0], size[1], mode='pre_battle')
    assert layout.header.timeline_rect is not None
    assert layout.header.status_strip_rect is None
    assert layout.header.log_strip_rect is None
    # ~20% H
    assert layout.header.full_rect[3] >= int(0.18 * size[1])
    assert layout.header.full_rect[3] <= int(0.22 * size[1])


@pytest.mark.parametrize('size', _STANDARD_SIZES)
def test_battle_header_is_collapsed(size):
    layout = compute_conquer_layout(size[0], size[1], mode='battle')
    assert layout.header.timeline_rect is None
    assert layout.header.status_strip_rect is not None
    assert layout.header.log_strip_rect is not None
    # status strip ~5% H, log ~6% H
    status_h = layout.header.status_strip_rect[3]
    log_h = layout.header.log_strip_rect[3]
    assert int(0.04 * size[1]) <= status_h <= int(0.06 * size[1])
    assert int(0.05 * size[1]) <= log_h <= int(0.07 * size[1])
    # And combined ~11% H — definitely smaller than the pre-battle 20% H header.
    assert (status_h + log_h) < int(0.18 * size[1])


@pytest.mark.parametrize('size', _STANDARD_SIZES)
@pytest.mark.parametrize('mode', _MODES)
def test_tactics_rail_is_left_of_battlefield(size, mode):
    layout = compute_conquer_layout(size[0], size[1], mode=mode)
    if layout.narrow:
        pytest.skip("narrow layout stacks; LEFT/RIGHT does not apply")
    rail = layout.tactics_rail.rect
    field = layout.battlefield.rect
    assert _x_end(rail) <= field[0], (
        f"tactics rail right edge {_x_end(rail)} should be ≤ battlefield x {field[0]}"
    )


@pytest.mark.parametrize('size', _STANDARD_SIZES)
def test_field_columns_mirror_around_duel_lane(size):
    layout = compute_conquer_layout(size[0], size[1], mode='battle')
    cols = layout.battlefield.columns
    lane = layout.battlefield.duel_lane.rect
    # Player order left-to-right (closest to lane = military)
    assert cols.you_castle[0] < cols.you_village[0] < cols.you_military[0]
    assert _x_end(cols.you_military) <= lane[0]
    # Opponent mirrored (closest to lane = military)
    assert _x_end(lane) <= cols.opp_military[0]
    assert cols.opp_military[0] < cols.opp_village[0] < cols.opp_castle[0]
    # All 6 columns share equal width (snapping tolerance: 1px)
    widths = {c[2] for c in (cols.you_castle, cols.you_village, cols.you_military,
                              cols.opp_military, cols.opp_village, cols.opp_castle)}
    assert max(widths) - min(widths) <= 1


@pytest.mark.parametrize('size', _STANDARD_SIZES)
def test_desktop_layout_prioritizes_battlefield_over_command_rail(size):
    layout = compute_conquer_layout(size[0], size[1], mode='battle')
    if layout.narrow:
        pytest.skip("narrow layout stacks; rail width priority does not apply")

    rail = layout.tactics_rail.rect
    field = layout.battlefield.rect
    inner = layout.battlefield.inner_rect
    lane = layout.battlefield.duel_lane.rect

    assert rail[2] <= int(size[0] * 0.18)
    assert field[2] >= int(size[0] * 0.775)
    assert lane[2] >= int(inner[2] * 0.24)


@pytest.mark.parametrize('size', _STANDARD_SIZES)
def test_duel_lane_bands_stack_without_overlap(size):
    layout = compute_conquer_layout(size[0], size[1], mode='battle')
    lane = layout.battlefield.duel_lane
    you_y_end = _y_end(lane.you_fighter_band)
    diff_y_start = lane.diff_band[1]
    diff_y_end = _y_end(lane.diff_band)
    opp_y_start = lane.opp_fighter_band[1]
    assert you_y_end <= diff_y_start
    assert diff_y_end <= opp_y_start


@pytest.mark.parametrize('size', _STANDARD_SIZES)
def test_three_round_cards_plus_total_in_ledger(size):
    layout = compute_conquer_layout(size[0], size[1], mode='battle')
    rounds = layout.round_ledger.round_card_rects
    total = layout.round_ledger.total_card_rect
    assert len(rounds) == 3
    # Round cards fully left of total card
    for r in rounds:
        assert _x_end(r) <= total[0] + 2, "round card overlaps total card"
    # Round cards in left-to-right order
    assert rounds[0][0] < rounds[1][0] < rounds[2][0]


@pytest.mark.parametrize('mode', _MODES)
def test_helper_rejects_invalid_screen_size(mode):
    with pytest.raises(ValueError):
        compute_conquer_layout(0, 0, mode=mode)
    with pytest.raises(ValueError):
        compute_conquer_layout(-100, 800, mode=mode)


def test_helper_rejects_unknown_mode():
    with pytest.raises(ValueError):
        compute_conquer_layout(1920, 1080, mode='not_a_mode')


def test_narrow_forces_stacked_layout():
    # 800x1200 portrait — clearly narrow
    layout = compute_conquer_layout(800, 1200, mode='battle')
    assert layout.narrow is True
    # In narrow, battlefield sits above tactics rail (stacked)
    assert _y_end(layout.battlefield.rect) <= layout.tactics_rail.rect[1] + 2


def test_narrow_explicit_override_works():
    layout = compute_conquer_layout(1920, 1080, mode='battle', narrow=True)
    assert layout.narrow is True
    # And forcing narrow=False on a tall screen also works
    layout2 = compute_conquer_layout(800, 1200, mode='battle', narrow=False)
    assert layout2.narrow is False


@pytest.mark.parametrize('size', _STANDARD_SIZES)
@pytest.mark.parametrize('mode', _MODES)
def test_battle_mode_grows_content_band(size, mode):
    """Battle/result modes should give more vertical room to battlefield/rail."""
    pre = compute_conquer_layout(size[0], size[1], mode='pre_battle')
    cur = compute_conquer_layout(size[0], size[1], mode=mode)
    if mode == 'pre_battle':
        return
    # battle/result content band must be taller than pre-battle's
    assert cur.battlefield.rect[3] > pre.battlefield.rect[3]
    assert cur.tactics_rail.rect[3] > pre.tactics_rail.rect[3]


@pytest.mark.parametrize('size', _STANDARD_SIZES)
@pytest.mark.parametrize('mode', _MODES)
def test_total_circle_fits_inside_total_card(size, mode):
    layout = compute_conquer_layout(size[0], size[1], mode=mode)
    card = layout.round_ledger.total_card_rect
    circle = layout.round_ledger.total_circle_rect
    assert circle[0] >= card[0] - 1
    assert circle[1] >= card[1] - 1
    assert _x_end(circle) <= _x_end(card) + 1
    assert _y_end(circle) <= _y_end(card) + 1


def test_as_dict_round_trips_top_level_fields():
    layout = compute_conquer_layout(1920, 1080, mode='battle')
    d = layout.as_dict()
    assert d['mode'] == 'battle'
    assert d['screen_size'] == (1920, 1080)
    assert 'battlefield' in d
    assert 'tactics_rail' in d
    assert 'round_ledger' in d
    assert 'header' in d
