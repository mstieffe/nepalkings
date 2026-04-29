# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for per-kingdom gold collection routes (kingdom-levels rework)."""

from datetime import datetime, timedelta
from unittest.mock import patch

from models import Kingdom, Land


def _add_land(db, owner_id, col, row, *, tier=1, gold_rate=5.0):
    land = Land(col=col, row=row, tier=tier, gold_rate=gold_rate,
                suit_bonus_suit='Hearts', suit_bonus_value=1,
                owner_user_id=owner_id)
    db.session.add(land)
    db.session.commit()
    return land


def _kingdom_for(user_id):
    from kingdom_service import reconcile_user_kingdoms
    reconcile_user_kingdoms(user_id, commit=True)
    return Kingdom.query.filter_by(owner_user_id=user_id).first()


class TestCollectKingdomGold:

    def test_unauthenticated(self, client):
        rv = client.post('/kingdom/1/collect_gold')
        assert rv.status_code in (401, 403)

    def test_unknown_kingdom(self, client, auth_headers_user1):
        rv = client.post('/kingdom/9999/collect_gold', headers=auth_headers_user1)
        assert rv.status_code == 404

    def test_collect_advances_pending_and_credits_user(self, client, db,
                                                       two_users,
                                                       auth_headers_user1):
        u1, _ = two_users
        u1.gold = 100
        db.session.commit()
        _add_land(db, u1.id, 0, 0, gold_rate=6.0)
        k = _kingdom_for(u1.id)
        now = datetime(2026, 4, 17, 12, 0, 0)
        k.last_gold_collection_at = now - timedelta(hours=1)
        db.session.commit()
        kid = k.id

        with patch('routes.kingdom._utcnow', return_value=now):
            rv = client.post(f'/kingdom/{kid}/collect_gold',
                             headers=auth_headers_user1)
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['success'] is True
        assert data['collected'] == 6
        assert data['gold'] == 106
        assert data['total_gold'] == 106
        assert data['pending_gold'] == 0

    def test_collect_clamped_at_vault_cap(self, client, db, two_users,
                                          auth_headers_user1):
        import server_settings as config
        u1, _ = two_users
        u1.gold = 0
        db.session.commit()
        _add_land(db, u1.id, 0, 0, gold_rate=10.0)
        k = _kingdom_for(u1.id)
        now = datetime(2026, 4, 17, 12, 0, 0)
        k.last_gold_collection_at = now - timedelta(days=30)
        db.session.commit()
        kid = k.id

        with patch('routes.kingdom._utcnow', return_value=now):
            rv = client.post(f'/kingdom/{kid}/collect_gold',
                             headers=auth_headers_user1)
        data = rv.get_json()
        assert data['collected'] == int(config.KINGDOM_VAULT_DEFAULT_CAP)
        assert data['vault_cap'] == int(config.KINGDOM_VAULT_DEFAULT_CAP)


class TestCollectGoldAll:

    def test_collect_all_aggregates_breakdown(self, client, db, two_users,
                                              auth_headers_user1):
        from kingdom_service import reconcile_user_kingdoms
        u1, _ = two_users
        u1.gold = 0
        db.session.commit()
        _add_land(db, u1.id, 0, 0, gold_rate=4.0)
        _add_land(db, u1.id, 5, 5, gold_rate=2.0)
        reconcile_user_kingdoms(u1.id, commit=True)
        now = datetime(2026, 4, 17, 12, 0, 0)
        for k in Kingdom.query.filter_by(owner_user_id=u1.id).all():
            k.last_gold_collection_at = now - timedelta(hours=1)
        db.session.commit()

        with patch('routes.kingdom._utcnow', return_value=now):
            rv = client.post('/kingdom/collect_gold_all',
                             headers=auth_headers_user1)
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['success'] is True
        assert data['collected_total'] == 6
        assert data['gold'] == 6
        assert data['total_gold'] == 6
        assert len(data['kingdoms']) == 2
        assert sorted(k['collected'] for k in data['kingdoms']) == [2, 4]
