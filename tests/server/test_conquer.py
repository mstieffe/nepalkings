# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for kingdom conquer endpoints (Phase 11)."""

import pytest
from datetime import datetime, timedelta, timezone
from models import db as _db, User, Land, CollectionCard, LandConfig, LandConfigFigure, LandConfigBattleMove


# ── Helpers ──────────────────────────────────────────────────────────────────

def _add_land(db, owner_id=None, col=0, row=0, tier=1, gold_rate=5.0):
    land = Land(
        col=col, row=row, tier=tier, gold_rate=gold_rate,
        suit_bonus_suit='Hearts', suit_bonus_value=2,
        owner_user_id=owner_id,
    )
    db.session.add(land)
    db.session.commit()
    return land


def _add_collection_card(db, user_id, suit='Hearts', rank='K', value=4):
    card = CollectionCard(user_id=user_id, suit=suit, rank=rank, value=value)
    db.session.add(card)
    db.session.commit()
    return card


# ═══════════════════════════════════════════════════════════════════
#  GET /kingdom/conquer/config
# ═══════════════════════════════════════════════════════════════════

class TestGetConquerConfig:

    def test_creates_empty_config(self, client, db, two_users, auth_headers_user1):
        u1, u2 = two_users
        land = _add_land(db, owner_id=u2.id)

        rv = client.get(f'/kingdom/conquer/config?land_id={land.id}',
                        headers=auth_headers_user1)
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['success'] is True
        assert data['config']['config_type'] == 'conquer'
        assert data['config']['figures'] == []
        assert data['config']['battle_moves'] == []
        assert data['conquer_cooldown_remaining'] == 0
        assert data['maps_available'] == int(u1.maps or 0)
        assert data['land_conquer_cooldown_remaining'] == 0

    def test_config_returns_cooldown_and_maps(self, client, db, two_users,
                                              auth_headers_user1):
        u1, u2 = two_users
        u1.maps = 2
        u1.last_conquer_at = (
            datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=10)
        )
        land = _add_land(db, owner_id=u2.id)
        db.session.commit()

        rv = client.get(f'/kingdom/conquer/config?land_id={land.id}',
                        headers=auth_headers_user1)
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['maps_available'] == 2
        assert data['conquer_cooldown_remaining'] > 0

    def test_returns_existing_config(self, client, db, two_users, auth_headers_user1):
        u1, u2 = two_users
        land = _add_land(db, owner_id=u2.id)

        # First call creates
        client.get(f'/kingdom/conquer/config?land_id={land.id}',
                   headers=auth_headers_user1)
        # Second call returns same
        rv = client.get(f'/kingdom/conquer/config?land_id={land.id}',
                        headers=auth_headers_user1)
        assert rv.status_code == 200
        # Should have exactly 1 config
        configs = LandConfig.query.filter_by(user_id=u1.id, land_id=land.id).all()
        assert len(configs) == 1

    def test_rejects_own_land(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        land = _add_land(db, owner_id=u1.id)

        rv = client.get(f'/kingdom/conquer/config?land_id={land.id}',
                        headers=auth_headers_user1)
        assert rv.status_code == 400

    def test_missing_land_id(self, client, auth_headers_user1):
        rv = client.get('/kingdom/conquer/config', headers=auth_headers_user1)
        assert rv.status_code == 400

    def test_unknown_land(self, client, auth_headers_user1):
        rv = client.get('/kingdom/conquer/config?land_id=99999',
                        headers=auth_headers_user1)
        assert rv.status_code == 404

    def test_unowned_land_allowed(self, client, db, two_users, auth_headers_user1):
        """Can conquer lands with no owner (AI-defended)."""
        _add_land(db, owner_id=None)  # no owner
        land = Land.query.first()
        rv = client.get(f'/kingdom/conquer/config?land_id={land.id}',
                        headers=auth_headers_user1)
        assert rv.status_code == 200


# ═══════════════════════════════════════════════════════════════════
#  POST /kingdom/conquer/build_figure
# ═══════════════════════════════════════════════════════════════════

class TestConquerBuildFigure:

    def test_build_figure_locks_cards(self, client, db, two_users, auth_headers_user1):
        u1, u2 = two_users
        land = _add_land(db, owner_id=u2.id)
        c1 = _add_collection_card(db, u1.id, 'Clubs', 'K', 4)
        c2 = _add_collection_card(db, u1.id, 'Clubs', '8', 8)

        rv = client.post('/kingdom/conquer/build_figure',
                         headers=auth_headers_user1,
                         json={
                             'land_id': land.id,
                             'family_name': 'Himalaya King',
                             'name': 'Himalaya King',
                             'suit': 'Clubs',
                             'color': 'defensive',
                             'field': 'castle',
                             'card_ids': [c1.id, c2.id],
                             'card_roles': ['key', 'number'],
                             'produces': {'villager_black': 2},
                             'requires': {},
                         })
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['success'] is True
        assert len(data['config']['figures']) == 1

        # Cards should be locked
        db.session.refresh(c1)
        db.session.refresh(c2)
        assert c1.locked is True
        assert c1.lock_type == 'conquer_figure'
        assert c2.locked is True

    def test_rejects_locked_cards(self, client, db, two_users, auth_headers_user1):
        u1, u2 = two_users
        land = _add_land(db, owner_id=u2.id)
        c1 = _add_collection_card(db, u1.id, 'Clubs', 'K', 4)
        c1.locked = True
        db.session.commit()

        rv = client.post('/kingdom/conquer/build_figure',
                         headers=auth_headers_user1,
                         json={
                             'land_id': land.id,
                             'family_name': 'Himalaya King',
                             'name': 'Himalaya King',
                             'suit': 'Clubs',
                             'color': 'defensive',
                             'field': 'castle',
                             'card_ids': [c1.id],
                             'card_roles': ['key'],
                         })
        assert rv.status_code == 400

    def test_maharaja_requires_mk_and_uses_server_attributes(
            self, client, db, two_users, auth_headers_user1):
        u1, u2 = two_users
        land = _add_land(db, owner_id=u2.id)
        mk = _add_collection_card(db, u1.id, 'Hearts', 'MK', 4)

        rv = client.post('/kingdom/conquer/build_figure',
                         headers=auth_headers_user1,
                         json={
                             'land_id': land.id,
                             'family_name': 'Djungle Maharaja',
                             'name': 'Fake name',
                             'suit': 'Hearts',
                             'color': 'defensive',
                             'field': 'village',
                             'card_ids': [mk.id],
                             'card_roles': ['key'],
                             'produces': {'gold': 999},
                             'requires': {'warrior_red': 99},
                             'checkmate': False,
                             'cannot_be_blocked': True,
                         })

        assert rv.status_code == 200
        fig = rv.get_json()['config']['figures'][0]
        assert fig['family_name'] == 'Djungle Maharaja'
        assert fig['name'] == 'Djungle Maharaja'
        assert fig['field'] == 'castle'
        assert fig['color'] == 'offensive'
        assert fig['card_specs'] == [
            {'rank': 'MK', 'suit': 'Hearts', 'value': 4},
        ]
        assert fig['produces'] == {'villager_red': 3, 'warrior_red': 2}
        assert fig['requires'] == {}
        assert fig['checkmate'] is True
        assert fig['cannot_be_blocked'] is False

    def test_maharaja_rejects_ordinary_king_card(
            self, client, db, two_users, auth_headers_user1):
        u1, u2 = two_users
        land = _add_land(db, owner_id=u2.id)
        king = _add_collection_card(db, u1.id, 'Hearts', 'K', 4)

        rv = client.post('/kingdom/conquer/build_figure',
                         headers=auth_headers_user1,
                         json={
                             'land_id': land.id,
                             'family_name': 'Djungle Maharaja',
                             'suit': 'Hearts',
                             'field': 'castle',
                             'card_ids': [king.id],
                             'card_roles': ['key'],
                         })

        assert rv.status_code == 400
        assert 'Maharaja card' in rv.get_json()['message']
        assert king.locked is False

    def test_rejects_missing_fields(self, client, db, two_users, auth_headers_user1):
        rv = client.post('/kingdom/conquer/build_figure',
                         headers=auth_headers_user1,
                         json={'land_id': 1})
        assert rv.status_code == 400

    def test_rejects_own_land(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        land = _add_land(db, owner_id=u1.id)
        c1 = _add_collection_card(db, u1.id, 'Clubs', 'K', 4)

        rv = client.post('/kingdom/conquer/build_figure',
                         headers=auth_headers_user1,
                         json={
                             'land_id': land.id,
                             'family_name': 'Himalaya King',
                             'name': 'Himalaya King',
                             'suit': 'Clubs',
                             'color': 'defensive',
                             'field': 'castle',
                             'card_ids': [c1.id],
                             'card_roles': ['key'],
                         })
        assert rv.status_code == 400

    def test_deficit_annotated(self, client, db, two_users, auth_headers_user1):
        """Figures with unmet requirements are annotated with has_deficit=True."""
        u1, u2 = two_users
        land = _add_land(db, owner_id=u2.id)
        c1 = _add_collection_card(db, u1.id, 'Clubs', 'J', 1)
        c2 = _add_collection_card(db, u1.id, 'Clubs', '8', 8)

        rv = client.post('/kingdom/conquer/build_figure',
                         headers=auth_headers_user1,
                         json={
                             'land_id': land.id,
                             'family_name': 'Small Yack Farm',
                             'name': 'Small Yack Farm',
                             'suit': 'Clubs',
                             'color': 'defensive',
                             'field': 'village',
                             'card_ids': [c1.id, c2.id],
                             'card_roles': ['key', 'number'],
                             'produces': {'food_black': 8},
                             'requires': {'villager_black': 1},
                         })
        data = rv.get_json()
        fig = data['config']['figures'][0]
        # No castle figure providing villager_black → deficit
        assert fig['has_deficit'] is True


# ═══════════════════════════════════════════════════════════════════
#  POST /kingdom/conquer/remove_figure
# ═══════════════════════════════════════════════════════════════════

class TestConquerRemoveFigure:

    def test_remove_figure_unlocks_cards(self, client, db, two_users, auth_headers_user1):
        u1, u2 = two_users
        land = _add_land(db, owner_id=u2.id)
        c1 = _add_collection_card(db, u1.id, 'Clubs', 'K', 4)

        # Build first
        rv = client.post('/kingdom/conquer/build_figure',
                         headers=auth_headers_user1,
                         json={
                             'land_id': land.id,
                             'family_name': 'Himalaya King',
                             'name': 'Himalaya King',
                             'suit': 'Clubs',
                             'color': 'defensive',
                             'field': 'castle',
                             'card_ids': [c1.id],
                             'card_roles': ['key'],
                         })
        fig_id = rv.get_json()['config']['figures'][0]['id']

        # Remove
        rv = client.post('/kingdom/conquer/remove_figure',
                         headers=auth_headers_user1,
                         json={'figure_id': fig_id})
        assert rv.status_code == 200
        assert rv.get_json()['config']['figures'] == []

        db.session.refresh(c1)
        assert c1.locked is False

    def test_remove_other_users_figure_rejected(self, client, db, two_users,
                                                 auth_headers_user1, auth_headers_user2):
        u1, u2 = two_users
        land = _add_land(db, owner_id=None, col=0, row=0)
        c2 = _add_collection_card(db, u2.id, 'Hearts', 'K', 4)

        # User2 builds
        rv = client.post('/kingdom/conquer/build_figure',
                         headers=auth_headers_user2,
                         json={
                             'land_id': land.id,
                             'family_name': 'Djungle King',
                             'name': 'Djungle King',
                             'suit': 'Hearts',
                             'color': 'offensive',
                             'field': 'castle',
                             'card_ids': [c2.id],
                             'card_roles': ['key'],
                         })
        fig_id = rv.get_json()['config']['figures'][0]['id']

        # User1 tries to remove
        rv = client.post('/kingdom/conquer/remove_figure',
                         headers=auth_headers_user1,
                         json={'figure_id': fig_id})
        assert rv.status_code == 403


# ═══════════════════════════════════════════════════════════════════
#  POST /kingdom/conquer/buy_battle_move
# ═══════════════════════════════════════════════════════════════════

class TestConquerBuyBattleMove:

    def test_buy_move_locks_card(self, client, db, two_users, auth_headers_user1):
        u1, u2 = two_users
        land = _add_land(db, owner_id=u2.id)
        c1 = _add_collection_card(db, u1.id, 'Hearts', '7', 7)

        rv = client.post('/kingdom/conquer/buy_battle_move',
                         headers=auth_headers_user1,
                         json={
                             'land_id': land.id,
                             'family_name': 'Strike',
                             'card_id': c1.id,
                             'suit': 'Hearts',
                             'rank': '7',
                             'value': 7,
                             'round_index': 0,
                         })
        assert rv.status_code == 200
        data = rv.get_json()
        assert len(data['config']['battle_moves']) == 1
        assert data['config']['battle_moves'][0]['round_index'] == 0

        db.session.refresh(c1)
        assert c1.locked is True
        assert c1.lock_type == 'conquer_move'

    def test_duplicate_round_index_rejected(self, client, db, two_users, auth_headers_user1):
        u1, u2 = two_users
        land = _add_land(db, owner_id=u2.id)
        c1 = _add_collection_card(db, u1.id, 'Hearts', '7', 7)
        c2 = _add_collection_card(db, u1.id, 'Hearts', '8', 8)

        client.post('/kingdom/conquer/buy_battle_move',
                    headers=auth_headers_user1,
                    json={
                        'land_id': land.id,
                        'family_name': 'Strike',
                        'card_id': c1.id,
                        'suit': 'Hearts',
                        'rank': '7',
                        'value': 7,
                        'round_index': 0,
                    })

        rv = client.post('/kingdom/conquer/buy_battle_move',
                         headers=auth_headers_user1,
                         json={
                             'land_id': land.id,
                             'family_name': 'Strike',
                             'card_id': c2.id,
                             'suit': 'Hearts',
                             'rank': '8',
                             'value': 8,
                             'round_index': 0,
                         })
        assert rv.status_code == 400
        assert 'slot' in rv.get_json()['message'].lower() or 'filled' in rv.get_json()['message'].lower()

    def test_max_three_moves(self, client, db, two_users, auth_headers_user1):
        u1, u2 = two_users
        land = _add_land(db, owner_id=u2.id)

        for i in range(3):
            c = _add_collection_card(db, u1.id, 'Hearts', str(7 + i), 7 + i)
            client.post('/kingdom/conquer/buy_battle_move',
                        headers=auth_headers_user1,
                        json={
                            'land_id': land.id,
                            'family_name': 'Strike',
                            'card_id': c.id,
                            'suit': 'Hearts',
                            'rank': str(7 + i),
                            'value': 7 + i,
                            'round_index': i,
                        })

        c4 = _add_collection_card(db, u1.id, 'Hearts', '10', 10)
        rv = client.post('/kingdom/conquer/buy_battle_move',
                         headers=auth_headers_user1,
                         json={
                             'land_id': land.id,
                             'family_name': 'Strike',
                             'card_id': c4.id,
                             'suit': 'Hearts',
                             'rank': '10',
                             'value': 10,
                             'round_index': 0,  # would be duplicate anyway
                         })
        assert rv.status_code == 400

    def test_invalid_round_index(self, client, db, two_users, auth_headers_user1):
        u1, u2 = two_users
        land = _add_land(db, owner_id=u2.id)
        c1 = _add_collection_card(db, u1.id, 'Hearts', '7', 7)

        rv = client.post('/kingdom/conquer/buy_battle_move',
                         headers=auth_headers_user1,
                         json={
                             'land_id': land.id,
                             'family_name': 'Strike',
                             'card_id': c1.id,
                             'suit': 'Hearts',
                             'rank': '7',
                             'value': 7,
                             'round_index': 5,
                         })
        assert rv.status_code == 400


# ═══════════════════════════════════════════════════════════════════
#  POST /kingdom/conquer/return_battle_move
# ═══════════════════════════════════════════════════════════════════

class TestConquerReturnBattleMove:

    def test_return_move_unlocks_card(self, client, db, two_users, auth_headers_user1):
        u1, u2 = two_users
        land = _add_land(db, owner_id=u2.id)
        c1 = _add_collection_card(db, u1.id, 'Hearts', '7', 7)

        rv = client.post('/kingdom/conquer/buy_battle_move',
                         headers=auth_headers_user1,
                         json={
                             'land_id': land.id,
                             'family_name': 'Strike',
                             'card_id': c1.id,
                             'suit': 'Hearts',
                             'rank': '7',
                             'value': 7,
                             'round_index': 0,
                         })
        move_id = rv.get_json()['config']['battle_moves'][0]['id']

        rv = client.post('/kingdom/conquer/return_battle_move',
                         headers=auth_headers_user1,
                         json={'move_id': move_id})
        assert rv.status_code == 200
        assert rv.get_json()['config']['battle_moves'] == []

        db.session.refresh(c1)
        assert c1.locked is False

    def test_return_other_users_move_rejected(self, client, db, two_users,
                                               auth_headers_user1, auth_headers_user2):
        u1, u2 = two_users
        land = _add_land(db, owner_id=None, col=1, row=1)
        c2 = _add_collection_card(db, u2.id, 'Hearts', '7', 7)

        rv = client.post('/kingdom/conquer/buy_battle_move',
                         headers=auth_headers_user2,
                         json={
                             'land_id': land.id,
                             'family_name': 'Strike',
                             'card_id': c2.id,
                             'suit': 'Hearts',
                             'rank': '7',
                             'value': 7,
                             'round_index': 0,
                         })
        move_id = rv.get_json()['config']['battle_moves'][0]['id']

        rv = client.post('/kingdom/conquer/return_battle_move',
                         headers=auth_headers_user1,
                         json={'move_id': move_id})
        assert rv.status_code == 403


# ═══════════════════════════════════════════════════════════════════
#  POST /kingdom/conquer/set_modifier & remove_modifier
# ═══════════════════════════════════════════════════════════════════

class TestConquerModifier:

    def test_set_blitzkrieg(self, client, db, two_users, auth_headers_user1):
        u1, u2 = two_users
        land = _add_land(db, owner_id=u2.id)
        # Blitzkrieg requires 2× Q same-color free cards
        _add_collection_card(db, u1.id, suit='Hearts', rank='Q', value=12)
        _add_collection_card(db, u1.id, suit='Hearts', rank='Q', value=12)

        rv = client.post('/kingdom/conquer/set_modifier',
                         headers=auth_headers_user1,
                         json={'land_id': land.id, 'modifier_type': 'Blitzkrieg'})
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['config']['battle_modifier'] == {'type': 'Blitzkrieg'}

    def test_reject_non_blitzkrieg(self, client, db, two_users, auth_headers_user1):
        u1, u2 = two_users
        land = _add_land(db, owner_id=u2.id)

        rv = client.post('/kingdom/conquer/set_modifier',
                         headers=auth_headers_user1,
                         json={'land_id': land.id, 'modifier_type': 'Civil War'})
        assert rv.status_code == 400

    def test_remove_modifier(self, client, db, two_users, auth_headers_user1):
        u1, u2 = two_users
        land = _add_land(db, owner_id=u2.id)
        _add_collection_card(db, u1.id, suit='Hearts', rank='Q', value=12)
        _add_collection_card(db, u1.id, suit='Hearts', rank='Q', value=12)

        client.post('/kingdom/conquer/set_modifier',
                    headers=auth_headers_user1,
                    json={'land_id': land.id, 'modifier_type': 'Blitzkrieg'})

        rv = client.post('/kingdom/conquer/remove_modifier',
                         headers=auth_headers_user1,
                         json={'land_id': land.id})
        assert rv.status_code == 200
        assert rv.get_json()['config']['battle_modifier'] is None

    def test_remove_modifier_no_config(self, client, auth_headers_user1):
        rv = client.post('/kingdom/conquer/remove_modifier',
                         headers=auth_headers_user1,
                         json={'land_id': 99999})
        assert rv.status_code == 404
