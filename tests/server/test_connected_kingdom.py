# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for connected kingdom components and persistent kingdom bonuses."""

from datetime import datetime, timedelta
from unittest.mock import patch

from models import Land
import server_settings as config
from kingdom_service import (compute_owned_land_components, effective_gold_rate_for_lands,
                             conquer_cooldown_seconds_for_target)


def _add_land(db, col, row, owner_id=None, gold_rate=10.0):
    land = Land(
        col=col,
        row=row,
        tier=1,
        gold_rate=gold_rate,
        suit_bonus_suit='Hearts',
        suit_bonus_value=1,
        owner_user_id=owner_id,
    )
    db.session.add(land)
    db.session.commit()
    return land


class TestConnectedKingdomComponents:

    def test_components_group_only_adjacent_same_owner_lands(self, db, two_users):
        u1, u2 = two_users
        a = _add_land(db, 0, 0, owner_id=u1.id)
        b = _add_land(db, 1, 0, owner_id=u1.id)
        isolated = _add_land(db, 6, 6, owner_id=u1.id)
        rival = _add_land(db, 0, 1, owner_id=u2.id)

        info_by_land, components_by_user = compute_owned_land_components([a, b, isolated, rival])

        assert info_by_land[a.id]['kingdom_component_size'] == 2
        assert info_by_land[b.id]['kingdom_component_id'] == info_by_land[a.id]['kingdom_component_id']
        assert info_by_land[isolated.id]['kingdom_component_size'] == 1
        assert info_by_land[rival.id]['kingdom_component_size'] == 1
        assert [component['size'] for component in components_by_user[u1.id]] == [2, 1]

    def test_components_expose_no_legacy_size_bonuses(self, db, two_users):
        u1, _ = two_users
        a = _add_land(db, 0, 0, owner_id=u1.id, gold_rate=50.0)
        b = _add_land(db, 1, 0, owner_id=u1.id, gold_rate=50.0)

        info_by_land, _ = compute_owned_land_components([a, b])

        assert info_by_land[a.id]['kingdom_level'] == 0
        assert info_by_land[a.id]['kingdom_bonuses'] == {}
        # Without a persistent kingdom row, effective rate equals raw rate.
        assert info_by_land[a.id]['kingdom_effective_gold_rate'] == 100.0

    def test_effective_gold_rate_returns_raw_without_persistent_kingdom(self, db, two_users):
        u1, _ = two_users
        lands = [
            _add_land(db, 0, 0, owner_id=u1.id, gold_rate=50.0),
            _add_land(db, 1, 0, owner_id=u1.id, gold_rate=50.0),
        ]

        assert effective_gold_rate_for_lands(lands) == 100.0

    def test_conquer_cooldown_uses_only_base_seconds(self, db, two_users):
        u1, _ = two_users
        _add_land(db, 0, 0, owner_id=u1.id)
        _add_land(db, 1, 0, owner_id=u1.id)
        target = _add_land(db, 0, 1, owner_id=None)

        with patch.object(config, 'CONQUER_COOLDOWN_SECONDS', 100):
            cooldown = conquer_cooldown_seconds_for_target(u1.id, target)

        assert cooldown == 100


class TestConnectedKingdomRoutes:

    def test_map_exposes_component_data_and_no_legacy_bonuses(self, client, db, two_users,
                                                              auth_headers_user1):
        u1, _ = two_users
        _add_land(db, 0, 0, owner_id=u1.id, gold_rate=50.0)
        _add_land(db, 1, 0, owner_id=u1.id, gold_rate=50.0)

        rv = client.get('/kingdom/map', headers=auth_headers_user1)

        assert rv.status_code == 200
        data = rv.get_json()
        assert data['my_total_gold_rate'] == 100.0
        # No persistent kingdom skills allocated → effective == raw.
        assert data['my_effective_gold_rate'] == 100.0
        assert data['my_kingdom']['largest_component_size'] == 2
        lands = data['lands']
        assert lands[0]['kingdom_component_size'] == 2
        assert lands[0]['kingdom_level'] == 0
        assert lands[0]['kingdom_bonuses'] == {}

    def test_collect_gold_all_uses_raw_rate_without_persistent_skills(self, client, db,
                                                                       two_users,
                                                                       auth_headers_user1):
        from kingdom_service import reconcile_user_kingdoms
        from models import Kingdom
        u1, _ = two_users
        now = datetime(2026, 4, 26, 12, 0, 0)
        u1.gold = 0
        db.session.commit()
        _add_land(db, 0, 0, owner_id=u1.id, gold_rate=50.0)
        _add_land(db, 1, 0, owner_id=u1.id, gold_rate=50.0)
        reconcile_user_kingdoms(u1.id, commit=True)
        for k in Kingdom.query.filter_by(owner_user_id=u1.id).all():
            k.last_gold_collection_at = now - timedelta(hours=1)
        db.session.commit()

        with patch('routes.kingdom._utcnow', return_value=now):
            rv = client.post('/kingdom/collect_gold_all', headers=auth_headers_user1)

        assert rv.status_code == 200
        data = rv.get_json()
        # 1 connected kingdom of 2 lands @ 50 gph each = 100 gph; cap at 50/hr default vault.
        # Vault cap is config.KINGDOM_VAULT_DEFAULT_CAP and accrual is 1 hour.
        import server_settings as cfg
        expected = min(100, int(cfg.KINGDOM_VAULT_DEFAULT_CAP))
        assert data['collected_total'] == expected
        assert data['total_gold'] == expected
