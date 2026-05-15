# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for the map_production / atlas kingdom skills and map collection."""

from datetime import datetime, timedelta

import pytest

import server_settings as settings
from kingdom_progression import (
    booster_production_interval_hours,
    map_pending_capacity_for_atlas_level,
    skill_definition,
)


class TestMapProductionInterval:

    def test_level0_disabled(self):
        assert booster_production_interval_hours('map', 0) == 0

    def test_halving(self):
        base = settings.KINGDOM_MAP_PRODUCTION_BASE_HOURS
        assert booster_production_interval_hours('map', 1) == base
        assert booster_production_interval_hours('map', 2) == base * 0.5
        assert booster_production_interval_hours('map', 3) == base * 0.25

    def test_skill_defined(self):
        sdef = skill_definition('map_production')
        assert sdef is not None
        assert sdef.max_level == 5


class TestAtlasCapacity:

    def test_default_capacity_at_level_zero(self):
        assert map_pending_capacity_for_atlas_level(0) == settings.KINGDOM_ATLAS_DEFAULT_CAPACITY

    def test_grows_linearly(self):
        assert map_pending_capacity_for_atlas_level(1) == 2
        assert map_pending_capacity_for_atlas_level(5) == 6

    def test_atlas_skill_defined(self):
        sdef = skill_definition('atlas')
        assert sdef is not None
        assert sdef.max_level == 5


class TestCollectKingdomProductionMaps:

    def _own_kingdom(self, db, two_users):
        from models import Kingdom
        u1, _ = two_users
        from kingdom_service import create_kingdom, kingdom_skill_allocations
        k = create_kingdom(u1.id)
        db.session.flush()
        return u1, db.session.get(Kingdom, k.id)

    def _set_skill(self, kingdom, key, level):
        from kingdom_service import kingdom_skill_allocations
        allocs = kingdom_skill_allocations(kingdom.id)
        allocs[key].level = int(level)

    def test_collect_includes_pending_maps(self, app, db, two_users):
        from kingdom_service import collect_kingdom_production
        u1, kingdom = self._own_kingdom(db, two_users)
        self._set_skill(kingdom, 'map_production', 1)
        kingdom.pending_maps = 1
        u1.maps = 0
        db.session.flush()
        result = collect_kingdom_production(kingdom, u1)
        assert result.get('collected_maps') == 1
        assert u1.maps == 1
        assert kingdom.pending_maps == 0

    def test_atlas_caps_pending(self, app, db, two_users):
        from kingdom_service import _accrue_pending_booster
        u1, kingdom = self._own_kingdom(db, two_users)
        self._set_skill(kingdom, 'map_production', 5)
        self._set_skill(kingdom, 'atlas', 2)  # cap 3
        kingdom.pending_maps = 0
        kingdom.last_maps_collection_at = datetime.utcnow() - timedelta(days=30)
        db.session.flush()
        _accrue_pending_booster(kingdom, 'map')
        assert kingdom.pending_maps == 3
