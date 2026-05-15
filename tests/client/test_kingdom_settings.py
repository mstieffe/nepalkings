# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for kingdom client configuration defaults."""

from pathlib import Path


def test_kingdom_skill_icon_defaults_exist():
    from config import settings

    client_root = Path(__file__).resolve().parents[2] / 'nepal_kings'
    assert (client_root / settings.KINGDOM_SHIELD_ICON_PATH).is_file()
    assert set(settings.KINGDOM_SKILL_ICON_PATHS) == {
        'gold_production',
        'gold_vault',
        'main_booster_production',
        'side_booster_production',
        'map_production',
        'atlas',
        'shield_cost_reduction',
        'core_protection',
        'loot_chance',
    }
    missing = [path for path in settings.KINGDOM_SKILL_ICON_PATHS.values()
               if not (client_root / path).is_file()]
    assert missing == []


def test_hex_gold_icon_default_exists():
    from config import settings

    client_root = Path(__file__).resolve().parents[2] / 'nepal_kings'
    assert (client_root / settings.HEX_GOLD_ICON_PATH).is_file()
