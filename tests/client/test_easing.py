# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Unit tests for the shared easing module (pure math, no pygame)."""
import pytest

from game.components import easing


ENDPOINT_FUNCS = [
    easing.ease_out_quad,
    easing.ease_in_quad,
    easing.ease_in_out,
    easing.ease_out_cubic,
    easing.ease_in_out_cubic,
    easing.ease_out_back,
    easing.ease_in_out_back,
    easing.ease_out_elastic,
    easing.ease_out_bounce,
]


@pytest.mark.parametrize('func', ENDPOINT_FUNCS, ids=lambda f: f.__name__)
def test_easing_endpoints(func):
    assert func(0.0) == pytest.approx(0.0, abs=1e-9)
    assert func(1.0) == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize('func', ENDPOINT_FUNCS, ids=lambda f: f.__name__)
def test_easing_clamps_out_of_range_input(func):
    assert func(-3.0) == pytest.approx(func(0.0), abs=1e-9)
    assert func(4.5) == pytest.approx(func(1.0), abs=1e-9)


def test_ease_out_back_overshoots_past_one():
    # The overshoot family intentionally exceeds 1.0 mid-curve.
    assert easing.ease_out_back(0.7) > 1.0
    assert max(easing.ease_out_back(t / 100.0) for t in range(101)) > 1.05


def test_ease_out_elastic_rings_past_one():
    assert max(easing.ease_out_elastic(t / 100.0) for t in range(101)) > 1.0


def test_monotone_curves_stay_within_unit_interval():
    for func in (easing.ease_out_quad, easing.ease_in_quad, easing.ease_in_out,
                 easing.ease_out_cubic, easing.ease_in_out_cubic,
                 easing.ease_out_bounce):
        for t in range(101):
            v = func(t / 100.0)
            assert -1e-9 <= v <= 1.0 + 1e-9, (func.__name__, t, v)


def test_clamp01_and_lerp():
    assert easing.clamp01(-0.5) == 0.0
    assert easing.clamp01(1.5) == 1.0
    assert easing.clamp01(0.25) == 0.25
    assert easing.lerp(2.0, 4.0, 0.5) == pytest.approx(3.0)
    assert easing.lerp(2.0, 4.0, 0.0) == pytest.approx(2.0)
    # lerp is deliberately unclamped (overshoot easings rely on it).
    assert easing.lerp(0.0, 10.0, 1.2) == pytest.approx(12.0)


def test_conquer_effects_reexports_stay_compatible():
    """The historical import surface on conquer_effects must keep working."""
    from game.components.conquer_effects import (  # noqa: F401
        _clamp01, ease_in_out, ease_in_quad, ease_out_quad,
    )
    assert ease_out_quad(0.5) == pytest.approx(0.75)
    assert ease_in_quad(0.5) == pytest.approx(0.25)
    assert ease_in_out(0.5) == pytest.approx(0.5)
    assert _clamp01(2.0) == 1.0
