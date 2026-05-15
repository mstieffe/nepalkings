# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for shared menu chrome gold-gain floater bookkeeping."""

from types import SimpleNamespace


def _screen_with_gold(gold=100):
    from game.screens._menu_base import MenuScreenMixin
    screen = object.__new__(MenuScreenMixin)
    screen.state = SimpleNamespace(user_dict={'gold': gold})
    screen._last_seen_gold = gold
    calls = []
    screen._spawn_gold_gain_floater = lambda amount, pos: calls.append((amount, pos))
    return screen, calls


def test_gold_gain_spawns_top_bar_floater():
    screen, calls = _screen_with_gold(100)

    screen._maybe_spawn_gold_gain_floater(135, (42, 24))

    assert calls == [(35, (42, 24))]
    assert screen._last_seen_gold == 135


def test_gold_loss_resets_baseline_without_floater():
    screen, calls = _screen_with_gold(100)

    screen._maybe_spawn_gold_gain_floater(80, (42, 24))

    assert calls == []
    assert screen._last_seen_gold == 80


def test_missing_gold_position_suppresses_floater_but_keeps_baseline():
    screen, calls = _screen_with_gold(100)

    screen._maybe_spawn_gold_gain_floater(125, None)

    assert calls == []
    assert screen._last_seen_gold == 125


def test_suppress_next_gold_floater_skips_once_then_resumes():
    screen, calls = _screen_with_gold(100)

    screen._suppress_next_gold_floater()
    screen._maybe_spawn_gold_gain_floater(140, (42, 24))
    screen._maybe_spawn_gold_gain_floater(160, (42, 24))

    assert calls == [(20, (42, 24))]
    assert screen._last_seen_gold == 160


def test_override_next_gold_floater_position_uses_custom_anchor_once():
    screen, calls = _screen_with_gold(100)

    screen._set_next_gold_floater_pos((9, 11))
    screen._maybe_spawn_gold_gain_floater(130, (42, 24))
    screen._maybe_spawn_gold_gain_floater(150, (42, 24))

    assert calls == [(30, (9, 11)), (20, (42, 24))]
    assert screen._last_seen_gold == 150


def test_current_gold_amount_handles_missing_or_invalid_values():
    screen, _ = _screen_with_gold(100)

    screen.state.user_dict = {'gold': 'bad'}
    assert screen._current_gold_amount() == 0

    screen.state.user_dict = None
    assert screen._current_gold_amount() == 0
