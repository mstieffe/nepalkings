# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Shared easing / interpolation helpers for UI animation.

Pure-``math`` leaf module — deliberately imports nothing from ``pygame``,
``config``, or ``game.*`` so every animation-heavy module (effects layer,
reveal sequencer, round ledger, screens) can depend on it without any risk
of an import cycle.

All easing functions map ``t`` in [0, 1] → [0, 1] (clamping out-of-range
input) except the overshoot/elastic family, which intentionally exceeds
1.0 mid-curve before settling at ``f(1) == 1``.
"""
from __future__ import annotations

import math


def clamp01(x: float) -> float:
    """Clamp ``x`` to the closed interval [0, 1]."""
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation from ``a`` to ``b`` (``t`` unclamped by design)."""
    return a + (b - a) * t


# ---------------------------------------------------------------------------
# Quadratic / smoothstep (pre-existing curves — numerically identical to the
# originals that lived in conquer_effects.py)
# ---------------------------------------------------------------------------

def ease_out_quad(t: float) -> float:
    t = clamp01(t)
    return 1.0 - (1.0 - t) * (1.0 - t)


def ease_in_quad(t: float) -> float:
    t = clamp01(t)
    return t * t


def ease_in_out(t: float) -> float:
    """Smoothstep: gentle accelerate/decelerate."""
    t = clamp01(t)
    return t * t * (3.0 - 2.0 * t)


# ---------------------------------------------------------------------------
# Cubic
# ---------------------------------------------------------------------------

def ease_out_cubic(t: float) -> float:
    t = clamp01(t)
    inv = 1.0 - t
    return 1.0 - inv * inv * inv


def ease_in_out_cubic(t: float) -> float:
    t = clamp01(t)
    if t < 0.5:
        return 4.0 * t * t * t
    inv = -2.0 * t + 2.0
    return 1.0 - (inv * inv * inv) / 2.0


# ---------------------------------------------------------------------------
# Character curves: overshoot / elastic / bounce
# ---------------------------------------------------------------------------

def ease_out_back(t: float, s: float = 1.70158) -> float:
    """Decelerate past the target then settle back (overshoot ≈ 10%)."""
    t = clamp01(t)
    c3 = s + 1.0
    p = t - 1.0
    return 1.0 + c3 * p * p * p + s * p * p


def ease_in_out_back(t: float, s: float = 1.70158) -> float:
    """Symmetric anticipation + overshoot."""
    t = clamp01(t)
    c2 = s * 1.525
    if t < 0.5:
        return ((2.0 * t) ** 2 * ((c2 + 1.0) * 2.0 * t - c2)) / 2.0
    p = 2.0 * t - 2.0
    return (p * p * ((c2 + 1.0) * p + c2) + 2.0) / 2.0


def ease_out_elastic(t: float) -> float:
    """Springy settle: rings past the target a couple of times."""
    t = clamp01(t)
    if t == 0.0:
        return 0.0
    if t == 1.0:
        return 1.0
    c4 = math.tau / 3.0
    return math.pow(2.0, -10.0 * t) * math.sin((t * 10.0 - 0.75) * c4) + 1.0


def ease_out_bounce(t: float) -> float:
    """Ball-drop bounce toward the target."""
    t = clamp01(t)
    n1 = 7.5625
    d1 = 2.75
    if t < 1.0 / d1:
        return n1 * t * t
    if t < 2.0 / d1:
        t -= 1.5 / d1
        return n1 * t * t + 0.75
    if t < 2.5 / d1:
        t -= 2.25 / d1
        return n1 * t * t + 0.9375
    t -= 2.625 / d1
    return n1 * t * t + 0.984375
