# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for GET /kingdom/map endpoint."""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
from models import (db as _db, User, Land, Kingdom as KingdomModel,
                    KingdomSkillAllocation)
import server_settings as config


# ── Helpers ──────────────────────────────────────────────────────────────────

def _add_land(db, col, row, tier=1, gold_rate=5.0, owner_id=None,
              suit='Hearts', bonus=2):
    land = Land(
        col=col, row=row, tier=tier, gold_rate=gold_rate,
        suit_bonus_suit=suit, suit_bonus_value=bonus,
        owner_user_id=owner_id,
    )
    db.session.add(land)
    db.session.commit()
    return land


def _utcnow_fixed(dt):
    return patch('routes.kingdom._utcnow', return_value=dt)


# ═══════════════════════════════════════════════════════════════════
#  GET /kingdom/map
# ═══════════════════════════════════════════════════════════════════

class TestKingdomMap:

    def test_empty_map(self, client, db, auth_headers_user1):
        """No lands → empty list, zero stats."""
        db.session.query(Land).delete()
        db.session.commit()

        rv = client.get('/kingdom/map', headers=auth_headers_user1)
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['lands'] == []
        assert data['my_total_gold_rate'] == 0
        assert data['my_lands_count'] == 0
        assert data['conquer_cooldown_remaining'] == 0

    def test_returns_all_lands(self, client, db, two_users, auth_headers_user1):
        """All lands appear in response, ordered by row, col."""
        u1, u2 = two_users
        _add_land(db, 0, 0, tier=1, gold_rate=2.0, owner_id=u1.id)
        _add_land(db, 1, 0, tier=2, gold_rate=5.0, owner_id=u2.id)
        _add_land(db, 0, 1, tier=3, gold_rate=10.0)  # unclaimed

        rv = client.get('/kingdom/map', headers=auth_headers_user1)
        assert rv.status_code == 200
        data = rv.get_json()
        assert len(data['lands']) == 3

        # Check ordering (row 0 first, then row 1)
        assert data['lands'][0]['row'] == 0
        assert data['lands'][0]['col'] == 0
        assert data['lands'][1]['row'] == 0
        assert data['lands'][1]['col'] == 1
        assert data['lands'][2]['row'] == 1
        assert data['lands'][2]['col'] == 0

    def test_is_mine_flag(self, client, db, two_users, auth_headers_user1):
        """'is_mine' is True only for lands owned by requesting user."""
        u1, u2 = two_users
        _add_land(db, 0, 0, owner_id=u1.id)
        _add_land(db, 1, 0, owner_id=u2.id)
        _add_land(db, 2, 0)  # unclaimed

        rv = client.get('/kingdom/map', headers=auth_headers_user1)
        data = rv.get_json()
        lands = {(l['col'], l['row']): l for l in data['lands']}

        assert lands[(0, 0)]['is_mine'] is True
        assert lands[(1, 0)]['is_mine'] is False
        assert lands[(2, 0)]['is_mine'] is False

    def test_my_stats(self, client, db, two_users, auth_headers_user1):
        """my_total_gold_rate and my_lands_count reflect only user's lands."""
        u1, u2 = two_users
        _add_land(db, 0, 0, gold_rate=3.0, owner_id=u1.id)
        _add_land(db, 1, 0, gold_rate=7.0, owner_id=u1.id)
        _add_land(db, 2, 0, gold_rate=15.0, owner_id=u2.id)

        rv = client.get('/kingdom/map', headers=auth_headers_user1)
        data = rv.get_json()
        assert data['my_lands_count'] == 2
        assert data['my_total_gold_rate'] == 10.0

    def test_conquer_cooldown_active(self, client, db, two_users, auth_headers_user1):
        """When last_conquer_at is recent, cooldown_remaining > 0."""
        u1, _ = two_users
        now = datetime(2026, 4, 17, 12, 0, 0)
        u1.last_conquer_at = now - timedelta(hours=1)
        db.session.commit()

        with _utcnow_fixed(now):
            rv = client.get('/kingdom/map', headers=auth_headers_user1)

        data = rv.get_json()
        expected = max(0, int(getattr(config, 'CONQUER_COOLDOWN_SECONDS', 0)) - 3600)
        assert data['conquer_cooldown_remaining'] == expected

    def test_conquer_cooldown_expired(self, client, db, two_users, auth_headers_user1):
        """When enough time has passed, cooldown_remaining = 0."""
        u1, _ = two_users
        now = datetime(2026, 4, 17, 12, 0, 0)
        u1.last_conquer_at = now - timedelta(hours=7)
        db.session.commit()

        with _utcnow_fixed(now):
            rv = client.get('/kingdom/map', headers=auth_headers_user1)

        data = rv.get_json()
        expected = max(0, int(getattr(config, 'CONQUER_COOLDOWN_SECONDS', 0)) - 7 * 3600)
        assert data['conquer_cooldown_remaining'] == expected

    def test_conquer_cooldown_never_conquered(self, client, auth_headers_user1):
        """When last_conquer_at is None, cooldown_remaining = 0."""
        rv = client.get('/kingdom/map', headers=auth_headers_user1)
        data = rv.get_json()
        assert data['conquer_cooldown_remaining'] == 0

    def test_land_conquer_protection_remaining(self, client, db, two_users,
                                               auth_headers_user1):
        """Each land reports its own conquer protection countdown in seconds."""
        u1, _ = two_users
        now = datetime(2026, 4, 17, 12, 0, 0)

        protected = _add_land(db, 0, 0, owner_id=u1.id)
        protected.conquer_cooldown_until = now + timedelta(seconds=305)

        expired = _add_land(db, 1, 0)
        expired.conquer_cooldown_until = now - timedelta(seconds=1)
        db.session.commit()

        with _utcnow_fixed(now):
            rv = client.get('/kingdom/map', headers=auth_headers_user1)

        assert rv.status_code == 200
        data = rv.get_json()
        lands_by_id = {l['id']: l for l in data['lands']}
        assert lands_by_id[protected.id]['conquer_cooldown_remaining'] == 305
        assert lands_by_id[expired.id]['conquer_cooldown_remaining'] == 0

    def test_land_owner_data(self, client, db, two_users, auth_headers_user1):
        """Owned lands include owner username and owned_since."""
        u1, _ = two_users
        since = datetime(2026, 3, 15, 10, 0, 0)
        land = _add_land(db, 0, 0, owner_id=u1.id)
        land.owned_since = since
        db.session.commit()

        rv = client.get('/kingdom/map', headers=auth_headers_user1)
        data = rv.get_json()
        owner = data['lands'][0]['owner']
        assert owner['user_id'] == u1.id
        assert owner['username'] == 'player1'
        assert '2026-03-15' in owner['owned_since']

    def test_unclaimed_land_no_owner(self, client, db, two_users, auth_headers_user1):
        """Unclaimed lands have owner = None."""
        _add_land(db, 0, 0)

        rv = client.get('/kingdom/map', headers=auth_headers_user1)
        data = rv.get_json()
        assert data['lands'][0]['owner'] is None

    def test_land_serializes_tier_and_bonus(self, client, db, two_users,
                                            auth_headers_user1):
        """Verify tier, gold_rate, suit_bonus fields in response."""
        _add_land(db, 3, 2, tier=3, gold_rate=12.5, suit='Spades', bonus=8)

        rv = client.get('/kingdom/map', headers=auth_headers_user1)
        land = rv.get_json()['lands'][0]
        assert land['tier'] == 3
        assert land['gold_rate'] == 12.5
        assert land['suit_bonus_suit'] == 'Spades'
        assert land['suit_bonus_value'] == 8

    def test_opponent_land_includes_kingdom_name_and_owner_style(self, client, db,
                                                                  two_users,
                                                                  auth_headers_user1):
        """Map payload exposes opponent kingdom name/style for cross-player visibility."""
        _u1, u2 = two_users

        rival_kingdom = KingdomModel(
            owner_user_id=u2.id,
            name='Rival Realm',
            flag_key='flag_plain',
            border_key='border_simple_gold',
            surface_key='surface_plain',
        )
        db.session.add(rival_kingdom)
        db.session.commit()

        land = _add_land(db, 0, 0, owner_id=u2.id)
        land.kingdom_id = rival_kingdom.id
        db.session.commit()

        rv = client.get('/kingdom/map', headers=auth_headers_user1)
        assert rv.status_code == 200
        row = rv.get_json()['lands'][0]

        assert row['is_mine'] is False
        assert row['kingdom_name'] == 'Rival Realm'
        assert row['owner_style']['flag_key'] == 'flag_plain'
        assert row['owner_style']['border_key'] == 'border_simple_gold'
        assert row['owner_style']['surface_key'] == 'surface_plain'

    def test_core_protected_opponent_land_is_marked_shielded(self, client, db,
                                                             two_users,
                                                             auth_headers_user1):
        """Map payload must let the client disable Conquer before setup."""
        _u1, u2 = two_users
        kingdom = KingdomModel(
            owner_user_id=u2.id,
            name='Sanctuary',
            flag_key='flag_plain',
            border_key='border_simple_gold',
            surface_key='surface_plain',
        )
        db.session.add(kingdom)
        db.session.commit()
        land = _add_land(db, 0, 0, owner_id=u2.id)
        land.kingdom_id = kingdom.id
        db.session.add(KingdomSkillAllocation(
            kingdom_id=kingdom.id,
            skill_key='core_protection',
            level=1,
        ))
        db.session.commit()

        rv = client.get('/kingdom/map', headers=auth_headers_user1)
        assert rv.status_code == 200
        row = rv.get_json()['lands'][0]

        assert row['id'] == land.id
        assert row['kingdom_is_shielded'] is True
        assert row['kingdom_shield_reason'] == 'core_protection'
        assert row['kingdom_shield_remaining'] == -1

    def test_requires_auth(self, client):
        """Endpoint requires authentication."""
        rv = client.get('/kingdom/map')
        assert rv.status_code in (401, 403)
