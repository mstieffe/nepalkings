# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for persistent per-kingdom configuration."""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from models import (Game, Land, Kingdom, KingdomCosmeticUnlock, KingdomNotification,
                    KingdomSkillAllocation)
import server_settings as config
from kingdom_service import (effective_gold_rate_for_lands, reconcile_user_kingdoms,
                             serialize_kingdom_config)


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


class TestKingdomConfigRoutes:

    def test_config_route_reconciles_owned_lands_into_persistent_kingdom(self, client, db,
                                                                        two_users,
                                                                        auth_headers_user1):
        u1, _ = two_users
        land = _add_land(db, 0, 0, owner_id=u1.id, gold_rate=25.0)

        rv = client.get(f'/kingdom/config?land_id={land.id}', headers=auth_headers_user1)

        assert rv.status_code == 200
        data = rv.get_json()
        assert data['success'] is True
        assert len(data['kingdoms']) == 1
        kingdom = data['kingdoms'][0]
        assert kingdom['lands_count'] == 1
        # Fresh kingdoms start at level 1 with KINGDOM_SKILL_POINTS_PER_LEVEL SP.
        assert kingdom['level'] == 1
        assert kingdom['skill_points_total'] == config.KINGDOM_SKILL_POINTS_PER_LEVEL
        assert kingdom['raw_gold_rate'] == 25.0
        assert kingdom['effective_gold_rate'] == 25.0
        assert kingdom['style'] == config.KINGDOM_DEFAULT_STYLE
        assert data['rename_price_gold'] == config.KINGDOM_RENAME_PRICE_GOLD
        # Skill definitions exposed in the new shape (effect_values list).
        gp = kingdom['skills']['gold_production']
        assert gp['effect_values'][0] == 0.03
        assert gp['max_level'] == 5
        db.session.refresh(land)
        assert land.kingdom_id == kingdom['id']

    def test_skill_upgrade_is_permanent_and_costs_skill_points(self, client, db, two_users,
                                                               auth_headers_user1):
        u1, _ = two_users
        _add_land(db, 0, 0, owner_id=u1.id)
        kingdom = reconcile_user_kingdoms(u1.id, commit=True)[0]
        # Starter SP = KINGDOM_SKILL_POINTS_PER_LEVEL = 3.
        assert kingdom.skill_points_granted == config.KINGDOM_SKILL_POINTS_PER_LEVEL

        # First upgrade of gold_production costs 1 SP (cost_multiplier=1).
        rv = client.post(f'/kingdom/config/{kingdom.id}/skills/upgrade',
                         headers=auth_headers_user1,
                         json={'skill_key': 'gold_production'})
        assert rv.status_code == 200
        data = rv.get_json()['kingdom']
        assert data['skills']['gold_production']['level'] == 1
        assert data['skill_points_available'] == 2
        assert '+3% gold production' in data['skill_effects']

        # The reset endpoint has been removed: skills are permanent now.
        rv = client.post(f'/kingdom/config/{kingdom.id}/skills/reset',
                         headers=auth_headers_user1, json={})
        assert rv.status_code == 404

    def test_skill_upgrade_rejects_when_no_points_left(self, client, db, two_users,
                                                      auth_headers_user1):
        u1, _ = two_users
        _add_land(db, 0, 0, owner_id=u1.id)
        kingdom = reconcile_user_kingdoms(u1.id, commit=True)[0]
        # Drain all available SP.
        kingdom.skill_points_granted = 0
        db.session.commit()
        rv = client.post(f'/kingdom/config/{kingdom.id}/skills/upgrade',
                         headers=auth_headers_user1,
                         json={'skill_key': 'gold_production'})
        assert rv.status_code == 400
        assert rv.get_json()['message'] == 'Not enough skill points'

    def test_kingdom_rename_costs_gold(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        u1.gold = config.KINGDOM_RENAME_PRICE_GOLD + 25
        db.session.commit()
        _add_land(db, 0, 0, owner_id=u1.id)
        kingdom = reconcile_user_kingdoms(u1.id, commit=True)[0]

        rv = client.post(f'/kingdom/config/{kingdom.id}/rename',
                         headers=auth_headers_user1,
                         json={'name': 'High Garden'})

        assert rv.status_code == 200
        data = rv.get_json()
        assert data['kingdom']['name'] == 'High Garden'
        assert data['gold'] == 25
        db.session.refresh(kingdom)
        assert kingdom.name == 'High Garden'

    def test_cosmetic_purchase_unlocks_and_equips_skin(self, client, db, two_users,
                                                       auth_headers_user1):
        u1, _ = two_users
        u1.gold = config.KINGDOM_COSMETIC_CATALOG['surface_stone']['price_gold'] + 25
        db.session.commit()
        _add_land(db, 0, 0, owner_id=u1.id)
        kingdom = reconcile_user_kingdoms(u1.id, commit=True)[0]

        rv = client.post(f'/kingdom/config/{kingdom.id}/cosmetics/purchase',
                         headers=auth_headers_user1,
                         json={'cosmetic_key': 'surface_stone'})

        assert rv.status_code == 200
        data = rv.get_json()
        assert data['kingdom']['style']['surface_key'] == 'surface_stone'
        assert data['gold'] == 25
        db.session.refresh(kingdom)
        assert kingdom.surface_key == 'surface_stone'
        assert KingdomCosmeticUnlock.query.filter_by(
            kingdom_id=kingdom.id,
            cosmetic_key='surface_stone',
        ).one_or_none() is not None

    @pytest.mark.parametrize('cosmetic_key', [
        'surface_grass', 'surface_marble', 'surface_lava',
        'border_rope_braid', 'border_thorned',
    ])
    def test_new_cosmetics_can_be_purchased(self, client, db, two_users,
                                            auth_headers_user1, cosmetic_key):
        u1, _ = two_users
        entry = config.KINGDOM_COSMETIC_CATALOG[cosmetic_key]
        u1.gold = entry['price_gold'] + 10
        db.session.commit()
        _add_land(db, 0, 0, owner_id=u1.id)
        kingdom = reconcile_user_kingdoms(u1.id, commit=True)[0]

        rv = client.post(f'/kingdom/config/{kingdom.id}/cosmetics/purchase',
                         headers=auth_headers_user1,
                         json={'cosmetic_key': cosmetic_key})

        assert rv.status_code == 200
        data = rv.get_json()
        field = f'{entry["type"]}_key'
        assert data['kingdom']['style'][field] == cosmetic_key
        assert data['gold'] == 10
        db.session.refresh(kingdom)
        assert getattr(kingdom, field) == cosmetic_key

    def test_kingdom_rename_rejects_short_long_and_control_chars(self, client, db, two_users,
                                                                 auth_headers_user1):
        u1, _ = two_users
        u1.gold = config.KINGDOM_RENAME_PRICE_GOLD + 100
        db.session.commit()
        _add_land(db, 0, 0, owner_id=u1.id)
        kingdom = reconcile_user_kingdoms(u1.id, commit=True)[0]
        url = f'/kingdom/config/{kingdom.id}/rename'

        # Whitespace-only / too short.
        rv = client.post(url, headers=auth_headers_user1, json={'name': '  '})
        assert rv.status_code == 400
        # Control char.
        rv = client.post(url, headers=auth_headers_user1, json={'name': 'Bad\x07Name'})
        assert rv.status_code == 400
        # Too long.
        rv = client.post(url, headers=auth_headers_user1, json={'name': 'x' * 41})
        assert rv.status_code == 400
        # Missing name.
        rv = client.post(url, headers=auth_headers_user1, json={})
        assert rv.status_code == 400

    def test_kingdom_rename_rate_limit_returns_429(self, client, db, two_users,
                                                   auth_headers_user1):
        u1, _ = two_users
        u1.gold = 10_000
        db.session.commit()
        _add_land(db, 0, 0, owner_id=u1.id)
        kingdom = reconcile_user_kingdoms(u1.id, commit=True)[0]
        url = f'/kingdom/config/{kingdom.id}/rename'

        from routes.kingdom import _RENAME_ATTEMPTS
        _RENAME_ATTEMPTS.pop(u1.id, None)

        with patch.object(config, 'KINGDOM_RENAME_RATE_LIMIT_PER_HOUR', 2):
            rv1 = client.post(url, headers=auth_headers_user1, json={'name': 'A1'})
            rv2 = client.post(url, headers=auth_headers_user1, json={'name': 'A2'})
            rv3 = client.post(url, headers=auth_headers_user1, json={'name': 'A3'})
        assert rv1.status_code == 200
        assert rv2.status_code == 200
        assert rv3.status_code == 429
        _RENAME_ATTEMPTS.pop(u1.id, None)

    def test_empty_kingdoms_are_deleted_during_reconcile(self, db, two_users):
        u1, _ = two_users
        land = _add_land(db, 0, 0, owner_id=u1.id)
        kingdom = reconcile_user_kingdoms(u1.id, commit=True)[0]
        db.session.add(KingdomCosmeticUnlock(kingdom_id=kingdom.id, cosmetic_key='flag_crimson'))
        db.session.commit()

        land.owner_user_id = None
        land.kingdom_id = None
        db.session.commit()
        assert reconcile_user_kingdoms(u1.id, commit=True) == []

        assert db.session.get(Kingdom, kingdom.id) is None
        assert KingdomCosmeticUnlock.query.filter_by(kingdom_id=kingdom.id).count() == 0
        assert KingdomSkillAllocation.query.filter_by(kingdom_id=kingdom.id).count() == 0

    def test_shield_quote_purchase_and_conquer_block(self, client, db, two_users,
                                                     auth_headers_user1,
                                                     auth_headers_user2):
        u1, _ = two_users
        u1.gold = 1000
        db.session.commit()
        land = _add_land(db, 0, 0, owner_id=u1.id)
        kingdom = reconcile_user_kingdoms(u1.id, commit=True)[0]

        rv = client.post(f'/kingdom/config/{kingdom.id}/shield/quote',
                         headers=auth_headers_user1, json={'hours': 6})
        assert rv.status_code == 200
        assert rv.get_json()['quote']['price_gold'] == (
            config.KINGDOM_SHIELD_PRICE_PER_HOUR_PER_LAND * 6
        )

        now = datetime(2026, 4, 26, 12, 0, 0)
        with patch('routes.kingdom._utcnow', return_value=now):
            rv = client.post(f'/kingdom/config/{kingdom.id}/shield/purchase',
                             headers=auth_headers_user1, json={'hours': 6})
        assert rv.status_code == 200
        db.session.refresh(kingdom)
        assert kingdom.shield_until == now + timedelta(hours=6)

        with patch('routes.kingdom._utcnow', return_value=now):
            rv = client.post('/kingdom/conquer/start_battle', headers=auth_headers_user2,
                             json={'land_id': land.id})
        assert rv.status_code == 400
        data = rv.get_json()
        assert data['success'] is False
        assert data['kingdom_id'] == kingdom.id
        assert 'shield blocks attacks' in data['message']

    def test_split_copies_style_and_shield_but_resets_progression(self, db, two_users):
        """When a kingdom splits, daughter kingdoms keep style/shield but reset XP/SP."""
        u1, _ = two_users
        left = _add_land(db, 0, 0, owner_id=u1.id)
        middle = _add_land(db, 1, 0, owner_id=u1.id)
        right = _add_land(db, 2, 0, owner_id=u1.id)
        kingdom = reconcile_user_kingdoms(u1.id, commit=True)[0]
        kingdom.flag_key = 'flag_crimson'
        kingdom.shield_until = datetime(2026, 4, 26, 18, 0, 0)
        kingdom.experience = 50
        kingdom.level = 5
        kingdom.skill_points_granted = 15
        db.session.commit()

        middle.owner_user_id = None
        middle.kingdom_id = None
        db.session.commit()

        kingdoms = reconcile_user_kingdoms(u1.id, commit=True)
        kingdom_ids = {row.id for row in kingdoms}
        assert len(kingdom_ids) == 2
        db.session.refresh(left)
        db.session.refresh(right)
        assert left.kingdom_id != right.kingdom_id
        rows = Kingdom.query.filter(Kingdom.id.in_(kingdom_ids)).all()
        # Style and shield are inherited (player paid for them).
        assert {row.flag_key for row in rows} == {'flag_crimson'}
        assert {row.shield_until for row in rows} == {datetime(2026, 4, 26, 18, 0, 0)}
        # Only the original kingdom keeps progression; the new daughter
        # restarts at level 1 with starter SP and 0 XP.
        survivors = [r for r in rows if r.id == kingdom.id]
        fresh = [r for r in rows if r.id != kingdom.id]
        assert len(survivors) == 1
        assert len(fresh) == 1
        assert survivors[0].level == 5
        assert fresh[0].level == 1
        assert fresh[0].experience == 0
        assert fresh[0].skill_points_granted == config.KINGDOM_SKILL_POINTS_PER_LEVEL

    def test_persistent_gold_skill_increases_effective_gold_rate(self, db, two_users):
        u1, _ = two_users
        lands = [
            _add_land(db, 0, 0, owner_id=u1.id, gold_rate=50.0),
            _add_land(db, 1, 0, owner_id=u1.id, gold_rate=50.0),
        ]
        kingdom = reconcile_user_kingdoms(u1.id, commit=True)[0]
        # Trigger allocation row creation, then bump gold_production to level 1.
        from kingdom_service import kingdom_skill_allocations
        allocations = kingdom_skill_allocations(kingdom.id)
        allocations['gold_production'].level = 1
        db.session.commit()

        # Level 1 gold_production effect = 0.03 → 100 * 1.03 = 103.0
        assert effective_gold_rate_for_lands(lands) == 103.0

    def test_serialize_kingdom_config_does_not_mutate_vault_accrual(self, db, two_users):
        u1, _ = two_users
        _add_land(db, 0, 0, owner_id=u1.id, gold_rate=20.0)
        kingdom = reconcile_user_kingdoms(u1.id, commit=True)[0]
        from kingdom_service import kingdom_skill_allocations
        kingdom_skill_allocations(kingdom.id)
        kingdom.pending_gold = 2.5
        kingdom.last_gold_collection_at = (
            datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
        )
        db.session.commit()

        pending_before = kingdom.pending_gold
        last_before = kingdom.last_gold_collection_at

        payload = serialize_kingdom_config(kingdom)

        assert payload['vault_pending'] > pending_before
        assert kingdom.pending_gold == pending_before
        assert kingdom.last_gold_collection_at == last_before

    def test_serialize_kingdom_config_emits_pending_and_rate_aliases(self, db, two_users):
        """Client UI consumes ``pending_gold`` and ``gold_rate_per_hour`` keys."""
        u1, _ = two_users
        _add_land(db, 0, 0, owner_id=u1.id, gold_rate=20.0)
        kingdom = reconcile_user_kingdoms(u1.id, commit=True)[0]
        kingdom.pending_gold = 4.0
        kingdom.last_gold_collection_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.session.commit()

        payload = serialize_kingdom_config(kingdom)

        assert 'pending_gold' in payload
        assert 'gold_rate_per_hour' in payload
        assert payload['pending_gold'] == payload['vault_pending']
        assert payload['gold_rate_per_hour'] == payload['vault_rate_per_hour']

    def test_conquer_game_does_not_serialize_defender_kingdom_skills(self, db, two_users):
        """Conquer battles should not expose passive kingdom skills as battle info."""
        u1, _ = two_users
        land = _add_land(db, 0, 0, owner_id=u1.id)
        kingdom = reconcile_user_kingdoms(u1.id, commit=True)[0]
        from kingdom_service import kingdom_skill_allocations
        allocations = kingdom_skill_allocations(kingdom.id)
        allocations['gold_production'].level = 1
        game = Game(mode='conquer', land_id=land.id, state='open')
        db.session.add(game)
        db.session.commit()

        payload = game.serialize()
        assert kingdom.id is not None
        assert 'defender_kingdom_id' not in payload
        assert 'defender_kingdom_name' not in payload
        assert 'defender_kingdom_bonuses' not in payload
        assert 'defender_kingdom_effects' not in payload

    def test_merge_keeps_larger_style_and_unions_unlocks_and_shield(self, db, two_users):
        u1, _ = two_users
        left = _add_land(db, 0, 0, owner_id=u1.id)
        right = _add_land(db, 2, 0, owner_id=u1.id)
        kingdoms = reconcile_user_kingdoms(u1.id, commit=True)
        assert len(kingdoms) == 2
        db.session.refresh(left)
        db.session.refresh(right)
        left_kingdom = db.session.get(Kingdom, left.kingdom_id)
        right_kingdom = db.session.get(Kingdom, right.kingdom_id)
        left_kingdom.flag_key = 'flag_crimson'
        right_kingdom.flag_key = 'flag_sun'
        right_kingdom.shield_until = datetime(2026, 4, 26, 18, 0, 0)
        db.session.add(KingdomCosmeticUnlock(
            kingdom_id=right_kingdom.id,
            cosmetic_key='flag_sun',
        ))
        db.session.commit()

        bridge = _add_land(db, 1, 0, owner_id=u1.id)
        kingdoms = reconcile_user_kingdoms(u1.id, commit=True)

        assert len(kingdoms) == 1
        winner = kingdoms[0]
        assert winner.id == left_kingdom.id
        assert winner.flag_key == 'flag_crimson'
        assert winner.shield_until == datetime(2026, 4, 26, 18, 0, 0)
        assert KingdomCosmeticUnlock.query.filter_by(
            kingdom_id=winner.id,
            cosmetic_key='flag_sun',
        ).one_or_none() is not None
        for land in (left, right, bridge):
            db.session.refresh(land)
            assert land.kingdom_id == winner.id
