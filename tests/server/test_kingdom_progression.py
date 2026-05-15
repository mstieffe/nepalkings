# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for kingdom XP progression tuning."""

import server_settings as config


def test_kingdom_xp_curve_uses_fast_growth():
    assert config.KINGDOM_LEVEL_XP_GROWTH == 1.25
    assert [
        config.kingdom_xp_required_for_level(level)
        for level in range(1, 6)
    ] == [5, 6, 8, 10, 12]
