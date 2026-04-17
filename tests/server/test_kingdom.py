# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for kingdom routes — gold production / collect_gold endpoint."""

import math
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from models import db as _db, User, Land


# ── Helpers ──────────────────────────────────────────────────────────────────

def _add_land(db, owner_id, col, row, tier=1, gold_rate=5.0):
    """Insert a Land hex owned by *owner_id*."""
    land = Land(
        col=col, row=row, tier=tier, gold_rate=gold_rate,
        suit_bonus_suit='Hearts', suit_bonus_value=1,
        owner_user_id=owner_id,
    )
    db.session.add(land)
    db.session.commit()
    return land


def _utcnow_fixed(dt):
    """Return a patcher that fixes _utcnow to *dt*."""
    return patch('routes.kingdom._utcnow', return_value=dt)


# ═══════════════════════════════════════════════════════════════════
#  POST /kingdom/collect_gold
# ═══════════════════════════════════════════════════════════════════

class TestCollectGold:

    # ── Basic cases ─────────────────────────────────────────────────

    def test_no_lands_returns_zero(self, client, auth_headers_user1):
        """User with no owned lands earns 0 gold."""
        rv = client.post('/kingdom/collect_gold', headers=auth_headers_user1)
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['gold_earned'] == 0
        assert data['total_production_rate'] == 0.0
        assert data['lands_owned'] == 0

    def test_first_collection_initialises_timestamp(self, client, db, two_users,
                                                     auth_headers_user1):
        """First call sets last_gold_collection but earns 0."""
        u1, _ = two_users
        _add_land(db, u1.id, 0, 0, gold_rate=10.0)

        rv = client.post('/kingdom/collect_gold', headers=auth_headers_user1)
        data = rv.get_json()
        assert data['gold_earned'] == 0
        assert data['total_production_rate'] == 10.0
        assert data['lands_owned'] == 1
        # Timestamp should now be set
        db.session.refresh(u1)
        assert u1.last_gold_collection is not None

    def test_collect_after_one_hour(self, client, db, two_users,
                                    auth_headers_user1):
        """After 1 hour with rate=10, user earns 10 gold."""
        u1, _ = two_users
        now = datetime(2026, 4, 17, 12, 0, 0)
        u1.last_gold_collection = now - timedelta(hours=1)
        u1.gold = 100
        db.session.commit()
        _add_land(db, u1.id, 0, 0, gold_rate=10.0)

        with _utcnow_fixed(now):
            rv = client.post('/kingdom/collect_gold', headers=auth_headers_user1)

        data = rv.get_json()
        assert data['gold_earned'] == 10
        assert data['total_gold'] == 110
        assert data['total_production_rate'] == 10.0

    def test_collect_multiple_lands(self, client, db, two_users,
                                    auth_headers_user1):
        """Gold rate sums across all owned lands."""
        u1, _ = two_users
        now = datetime(2026, 4, 17, 12, 0, 0)
        u1.last_gold_collection = now - timedelta(hours=2)
        u1.gold = 50
        db.session.commit()

        _add_land(db, u1.id, 0, 0, gold_rate=5.0)
        _add_land(db, u1.id, 1, 0, gold_rate=3.0)
        _add_land(db, u1.id, 2, 0, gold_rate=2.0)
        # total_rate = 10, 2 hours → 20

        with _utcnow_fixed(now):
            rv = client.post('/kingdom/collect_gold', headers=auth_headers_user1)

        data = rv.get_json()
        assert data['gold_earned'] == 20
        assert data['total_gold'] == 70
        assert data['total_production_rate'] == 10.0
        assert data['lands_owned'] == 3

    def test_fractional_hours_floored(self, client, db, two_users,
                                      auth_headers_user1):
        """Gold is floor'd — 1.5 hours at rate 3 = floor(4.5) = 4."""
        u1, _ = two_users
        now = datetime(2026, 4, 17, 12, 0, 0)
        u1.last_gold_collection = now - timedelta(hours=1, minutes=30)
        u1.gold = 0
        db.session.commit()
        _add_land(db, u1.id, 0, 0, gold_rate=3.0)

        with _utcnow_fixed(now):
            rv = client.post('/kingdom/collect_gold', headers=auth_headers_user1)

        data = rv.get_json()
        assert data['gold_earned'] == 4  # floor(3 * 1.5) = 4

    # ── Accumulation cap ────────────────────────────────────────────

    def test_accumulation_capped_at_max_hours(self, client, db, two_users,
                                               auth_headers_user1):
        """Elapsed time capped at GOLD_PRODUCTION_MAX_ACCUMULATION_HOURS."""
        u1, _ = two_users
        now = datetime(2026, 4, 17, 12, 0, 0)
        # 30 days ago — way beyond the 7-day cap
        u1.last_gold_collection = now - timedelta(days=30)
        u1.gold = 0
        db.session.commit()
        _add_land(db, u1.id, 0, 0, gold_rate=10.0)

        max_hours = 7 * 24  # 168
        expected = math.floor(10.0 * max_hours)

        with _utcnow_fixed(now):
            rv = client.post('/kingdom/collect_gold', headers=auth_headers_user1)

        data = rv.get_json()
        assert data['gold_earned'] == expected

    # ── Other users' lands not counted ──────────────────────────────

    def test_other_users_lands_not_included(self, client, db, two_users,
                                             auth_headers_user1):
        """Only the current user's owned lands contribute to gold rate."""
        u1, u2 = two_users
        now = datetime(2026, 4, 17, 12, 0, 0)
        u1.last_gold_collection = now - timedelta(hours=1)
        u1.gold = 0
        db.session.commit()

        _add_land(db, u1.id, 0, 0, gold_rate=5.0)
        _add_land(db, u2.id, 1, 0, gold_rate=100.0)  # u2's land

        with _utcnow_fixed(now):
            rv = client.post('/kingdom/collect_gold', headers=auth_headers_user1)

        data = rv.get_json()
        assert data['gold_earned'] == 5   # only u1's land
        assert data['lands_owned'] == 1

    # ── Timestamp updates ───────────────────────────────────────────

    def test_timestamp_updated_after_collection(self, client, db, two_users,
                                                 auth_headers_user1):
        """last_gold_collection should be updated to now after collecting."""
        u1, _ = two_users
        now = datetime(2026, 4, 17, 14, 0, 0)
        u1.last_gold_collection = datetime(2026, 4, 17, 12, 0, 0)
        db.session.commit()
        _add_land(db, u1.id, 0, 0, gold_rate=10.0)

        with _utcnow_fixed(now):
            client.post('/kingdom/collect_gold', headers=auth_headers_user1)

        db.session.refresh(u1)
        assert u1.last_gold_collection == now

    def test_consecutive_collections(self, client, db, two_users,
                                      auth_headers_user1):
        """Two rapid collections — second earns 0 since no time elapsed."""
        u1, _ = two_users
        now = datetime(2026, 4, 17, 12, 0, 0)
        u1.last_gold_collection = now - timedelta(hours=1)
        u1.gold = 0
        db.session.commit()
        _add_land(db, u1.id, 0, 0, gold_rate=10.0)

        with _utcnow_fixed(now):
            rv1 = client.post('/kingdom/collect_gold', headers=auth_headers_user1)
        assert rv1.get_json()['gold_earned'] == 10

        # Immediately collect again — same timestamp
        with _utcnow_fixed(now):
            rv2 = client.post('/kingdom/collect_gold', headers=auth_headers_user1)
        assert rv2.get_json()['gold_earned'] == 0

    # ── Auth ────────────────────────────────────────────────────────

    def test_unauthenticated_returns_401(self, client):
        """Request without token is rejected."""
        rv = client.post('/kingdom/collect_gold')
        assert rv.status_code in (401, 403)

    # ── Zero rate lands ─────────────────────────────────────────────

    def test_zero_rate_land_earns_nothing(self, client, db, two_users,
                                          auth_headers_user1):
        """Lands with gold_rate=0 don't produce gold."""
        u1, _ = two_users
        now = datetime(2026, 4, 17, 12, 0, 0)
        u1.last_gold_collection = now - timedelta(hours=10)
        u1.gold = 50
        db.session.commit()
        _add_land(db, u1.id, 0, 0, gold_rate=0.0)

        with _utcnow_fixed(now):
            rv = client.post('/kingdom/collect_gold', headers=auth_headers_user1)

        data = rv.get_json()
        assert data['gold_earned'] == 0
        assert data['total_gold'] == 50
