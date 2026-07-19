# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Characterization tests for figure-side colour mapping."""

import pickle

import pytest


def test_legacy_get_opp_color_import_reexports_canonical_function():
    from game.components.figures.figure_color import (
        get_opp_color as canonical_get_opp_color,
    )
    from utils.utils import get_opp_color as legacy_get_opp_color

    assert legacy_get_opp_color is canonical_get_opp_color
    assert canonical_get_opp_color.__module__ == "utils.utils"
    assert (
        pickle.loads(pickle.dumps(canonical_get_opp_color))
        is canonical_get_opp_color
    )


@pytest.mark.parametrize(
    ("color", "expected"),
    [
        ("offensive", "defensive"),
        ("defensive", "offensive"),
    ],
)
def test_get_opp_color_maps_known_figure_sides(color, expected):
    from utils.utils import get_opp_color

    assert get_opp_color(color) == expected


@pytest.mark.parametrize("color", [None, "", "Offensive", "unknown", 1])
def test_get_opp_color_returns_none_for_unknown_values(color):
    from utils.utils import get_opp_color

    assert get_opp_color(color) is None
