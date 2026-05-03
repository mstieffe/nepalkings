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


class TestCollectKingdomProduction:

    def _enable_booster_skills(self, db, kingdom, *, main_level=1, side_level=1):
        from kingdom_service import kingdom_skill_allocations
        allocations = kingdom_skill_allocations(kingdom.id)
        allocations['main_booster_production'].level = main_level
        allocations['side_booster_production'].level = side_level
        db.session.commit()

    def test_collect_production_transfers_gold_and_boosters(self, client, db,
                                                            two_users,
                                                            auth_headers_user1):
        u1, _ = two_users
        u1.gold = 100
        u1.booster_packs = 0
        u1.booster_packs_side = 0
        db.session.commit()
        _add_land(db, u1.id, 0, 0, gold_rate=6.0)
        k = _kingdom_for(u1.id)
        self._enable_booster_skills(db, k)
        now = datetime(2026, 4, 17, 12, 0, 0)
        k.last_gold_collection_at = now - timedelta(hours=1)
        k.last_main_booster_collection_at = now - timedelta(hours=96)
        k.last_side_booster_collection_at = now - timedelta(hours=96)
        db.session.commit()

        with patch('routes.kingdom._utcnow', return_value=now):
            rv = client.post(f'/kingdom/{k.id}/collect_production',
                             headers=auth_headers_user1)

        assert rv.status_code == 200
        data = rv.get_json()
        assert data['collected_gold'] == 6
        assert data['collected'] == 6  # legacy alias remains gold-only
        assert data['collected_main_boosters'] == 1
        assert data['collected_side_boosters'] == 1
        assert data['gold'] == 106
        assert data['booster_packs'] == 1
        assert data['booster_packs_side'] == 1
        assert data['production']['main_booster']['pending'] == 0
        assert data['production']['side_booster']['pending'] == 0

    def test_booster_capacity_is_one_without_carryover(self, client, db,
                                                       two_users,
                                                       auth_headers_user1):
        u1, _ = two_users
        _add_land(db, u1.id, 0, 0, gold_rate=0.0)
        k = _kingdom_for(u1.id)
        self._enable_booster_skills(db, k, side_level=0)
        now = datetime(2026, 4, 17, 12, 0, 0)
        k.last_main_booster_collection_at = now - timedelta(hours=200)
        db.session.commit()

        with patch('routes.kingdom._utcnow', return_value=now):
            rv = client.post(f'/kingdom/{k.id}/collect_production',
                             headers=auth_headers_user1)
        assert rv.get_json()['collected_main_boosters'] == 1
        db.session.refresh(k)
        assert k.pending_main_boosters == 0
        assert k.last_main_booster_collection_at == now

        with patch('routes.kingdom._utcnow', return_value=now + timedelta(hours=1)):
            rv = client.post(f'/kingdom/{k.id}/collect_production',
                             headers=auth_headers_user1)
        assert rv.get_json()['collected_main_boosters'] == 0

    def test_collect_specific_item_leaves_other_production_pending(self, client, db,
                                                                   two_users,
                                                                   auth_headers_user1):
        u1, _ = two_users
        u1.gold = 100
        u1.booster_packs = 0
        db.session.commit()
        _add_land(db, u1.id, 0, 0, gold_rate=6.0)
        k = _kingdom_for(u1.id)
        self._enable_booster_skills(db, k, side_level=0)
        now = datetime(2026, 4, 17, 12, 0, 0)
        k.last_gold_collection_at = now - timedelta(hours=1)
        k.last_main_booster_collection_at = now - timedelta(hours=96)
        db.session.commit()

        with patch('routes.kingdom._utcnow', return_value=now):
            rv = client.post(
                f'/kingdom/{k.id}/collect_production',
                headers=auth_headers_user1,
                json={'item_key': 'main_booster'},
            )

        assert rv.status_code == 200
        data = rv.get_json()
        assert data['collected_gold'] == 0
        assert data['collected_main_boosters'] == 1
        assert data['gold'] == 100
        assert data['booster_packs'] == 1
        assert data['pending_gold'] == 6.0
        assert data['pending_main_boosters'] == 0
        db.session.refresh(k)
        assert k.pending_gold == 6.0
        assert k.pending_main_boosters == 0

    def test_collect_specific_item_rejects_unknown_key(self, client, db, two_users,
                                                        auth_headers_user1):
        u1, _ = two_users
        _add_land(db, u1.id, 0, 0, gold_rate=0.0)
        k = _kingdom_for(u1.id)

        rv = client.post(
            f'/kingdom/{k.id}/collect_production',
            headers=auth_headers_user1,
            json={'item_key': 'not_real'},
        )

        assert rv.status_code == 400
        assert rv.get_json()['success'] is False

    def test_collect_all_aggregates_booster_totals(self, client, db, two_users,
                                                  auth_headers_user1):
        from kingdom_service import reconcile_user_kingdoms
        u1, _ = two_users
        _add_land(db, u1.id, 0, 0, gold_rate=0.0)
        _add_land(db, u1.id, 5, 5, gold_rate=0.0)
        reconcile_user_kingdoms(u1.id, commit=True)
        now = datetime(2026, 4, 17, 12, 0, 0)
        kingdoms = Kingdom.query.filter_by(owner_user_id=u1.id).all()
        for k in kingdoms:
            self._enable_booster_skills(db, k, side_level=0)
            k.last_main_booster_collection_at = now - timedelta(hours=96)
        db.session.commit()

        with patch('routes.kingdom._utcnow', return_value=now):
            rv = client.post('/kingdom/collect_production_all',
                             headers=auth_headers_user1)

        data = rv.get_json()
        assert data['success'] is True
        assert data['collected_main_boosters_total'] == 2
        assert data['booster_packs'] == 2
        assert sorted(k['collected_main_boosters'] for k in data['kingdoms']) == [1, 1]


class TestKingdomMergeBoosterOverflow:
    """Booster packs that would be lost on auto-merge are credited to the
    owning user's balance instead of being silently destroyed."""

    def _make_two_kingdoms(self, db, owner_id):
        from kingdom_service import create_kingdom
        k1 = create_kingdom(owner_id)
        k2 = create_kingdom(owner_id)
        db.session.commit()
        return k1, k2

    def test_overflow_pack_credits_user_balance(self, db, two_users):
        from kingdom_service import _merge_source_kingdom_into_target
        u1, _ = two_users
        u1.booster_packs = 0
        u1.booster_packs_side = 0
        db.session.commit()
        target, source = self._make_two_kingdoms(db, u1.id)
        target.pending_main_boosters = 1
        source.pending_main_boosters = 1
        target.pending_side_boosters = 0
        source.pending_side_boosters = 0
        db.session.commit()

        _merge_source_kingdom_into_target(source, target)
        db.session.commit()

        assert target.pending_main_boosters == 1  # capacity-clamped
        assert source.pending_main_boosters == 0
        assert u1.booster_packs == 1  # overflow credited to user
        assert u1.booster_packs_side == 0  # no overflow on the side track

    def test_no_overflow_when_only_source_ready(self, db, two_users):
        from kingdom_service import _merge_source_kingdom_into_target
        u1, _ = two_users
        u1.booster_packs = 0
        db.session.commit()
        target, source = self._make_two_kingdoms(db, u1.id)
        target.pending_main_boosters = 0
        source.pending_main_boosters = 1
        db.session.commit()

        _merge_source_kingdom_into_target(source, target)
        db.session.commit()

        assert target.pending_main_boosters == 1
        assert source.pending_main_boosters == 0
        assert u1.booster_packs == 0  # nothing to overflow
