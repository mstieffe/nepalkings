# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for kingdom defence endpoints (Phase 12)."""

import pytest
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


def _build_figure(client, headers, land_id, card_ids, card_roles=None,
                  family='Himalaya King', field='castle', color='defensive',
                  produces=None, requires=None):
    """Helper to build a figure and return the response JSON."""
    rv = client.post('/kingdom/defence/build_figure', headers=headers,
                     json={
                         'land_id': land_id,
                         'family_name': family,
                         'name': family,
                         'suit': 'Clubs',
                         'color': color,
                         'field': field,
                         'card_ids': card_ids,
                         'card_roles': card_roles or ['key'] * len(card_ids),
                         'produces': produces or {},
                         'requires': requires or {},
                     })
    return rv


# ═══════════════════════════════════════════════════════════════════
#  GET /kingdom/defence/config
# ═══════════════════════════════════════════════════════════════════

class TestGetDefenceConfig:

    def test_creates_empty_config(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        land = _add_land(db, owner_id=u1.id)

        rv = client.get(f'/kingdom/defence/config?land_id={land.id}',
                        headers=auth_headers_user1)
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['success'] is True
        assert data['config']['config_type'] == 'defence'
        assert data['config']['figures'] == []
        assert data['config']['battle_moves'] == []

    def test_returns_existing_config(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        land = _add_land(db, owner_id=u1.id)

        client.get(f'/kingdom/defence/config?land_id={land.id}',
                   headers=auth_headers_user1)
        rv = client.get(f'/kingdom/defence/config?land_id={land.id}',
                        headers=auth_headers_user1)
        assert rv.status_code == 200
        configs = LandConfig.query.filter_by(
            user_id=u1.id, config_type='defence', land_id=land.id
        ).all()
        assert len(configs) == 1

    def test_rejects_non_owned_land(self, client, db, two_users, auth_headers_user1):
        _, u2 = two_users
        land = _add_land(db, owner_id=u2.id)

        rv = client.get(f'/kingdom/defence/config?land_id={land.id}',
                        headers=auth_headers_user1)
        assert rv.status_code == 403

    def test_rejects_unowned_land(self, client, db, two_users, auth_headers_user1):
        land = _add_land(db, owner_id=None)

        rv = client.get(f'/kingdom/defence/config?land_id={land.id}',
                        headers=auth_headers_user1)
        assert rv.status_code == 403

    def test_missing_land_id(self, client, auth_headers_user1):
        rv = client.get('/kingdom/defence/config', headers=auth_headers_user1)
        assert rv.status_code == 400

    def test_unknown_land(self, client, auth_headers_user1):
        rv = client.get('/kingdom/defence/config?land_id=99999',
                        headers=auth_headers_user1)
        assert rv.status_code == 404


# ═══════════════════════════════════════════════════════════════════
#  POST /kingdom/defence/build_figure
# ═══════════════════════════════════════════════════════════════════

class TestDefenceBuildFigure:

    def test_build_figure_locks_cards(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        land = _add_land(db, owner_id=u1.id)
        c1 = _add_collection_card(db, u1.id, 'Clubs', 'K', 4)
        c2 = _add_collection_card(db, u1.id, 'Clubs', '8', 8)

        rv = _build_figure(client, auth_headers_user1, land.id, [c1.id, c2.id],
                           ['key', 'number'])
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['success'] is True
        assert len(data['config']['figures']) == 1

        db.session.refresh(c1)
        db.session.refresh(c2)
        assert c1.locked is True
        assert c1.lock_type == 'defence_figure'
        assert c2.locked is True

    def test_rejects_locked_cards(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        land = _add_land(db, owner_id=u1.id)
        c1 = _add_collection_card(db, u1.id, 'Clubs', 'K', 4)
        c1.locked = True
        db.session.commit()

        rv = _build_figure(client, auth_headers_user1, land.id, [c1.id])
        assert rv.status_code == 400

    def test_rejects_non_owned_land(self, client, db, two_users, auth_headers_user1):
        _, u2 = two_users
        land = _add_land(db, owner_id=u2.id)
        c1 = _add_collection_card(db, two_users[0].id, 'Clubs', 'K', 4)

        rv = _build_figure(client, auth_headers_user1, land.id, [c1.id])
        assert rv.status_code == 403


# ═══════════════════════════════════════════════════════════════════
#  POST /kingdom/defence/remove_figure
# ═══════════════════════════════════════════════════════════════════

class TestDefenceRemoveFigure:

    def test_remove_figure_unlocks_cards(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        land = _add_land(db, owner_id=u1.id)
        c1 = _add_collection_card(db, u1.id, 'Clubs', 'K', 4)

        rv = _build_figure(client, auth_headers_user1, land.id, [c1.id])
        fig_id = rv.get_json()['config']['figures'][0]['id']

        rv = client.post('/kingdom/defence/remove_figure',
                         headers=auth_headers_user1,
                         json={'figure_id': fig_id})
        assert rv.status_code == 200
        assert rv.get_json()['config']['figures'] == []

        db.session.refresh(c1)
        assert c1.locked is False

    def test_clears_battle_figure_ref_on_remove(self, client, db, two_users,
                                                 auth_headers_user1):
        u1, _ = two_users
        land = _add_land(db, owner_id=u1.id)
        c1 = _add_collection_card(db, u1.id, 'Clubs', 'K', 4)

        rv = _build_figure(client, auth_headers_user1, land.id, [c1.id],
                           produces={'villager_black': 2})
        fig_id = rv.get_json()['config']['figures'][0]['id']

        # Set as battle figure
        client.post('/kingdom/defence/set_battle_figure',
                    headers=auth_headers_user1,
                    json={'land_id': land.id, 'figure_id': fig_id})

        # Remove the figure
        rv = client.post('/kingdom/defence/remove_figure',
                         headers=auth_headers_user1,
                         json={'figure_id': fig_id})
        assert rv.status_code == 200
        cfg = rv.get_json()['config']
        assert cfg.get('battle_figure_id') is None

    def test_rejects_conquer_figure(self, client, db, two_users, auth_headers_user1):
        """Cannot remove a conquer figure via defence endpoint."""
        u1, u2 = two_users
        land = _add_land(db, owner_id=u2.id)
        c1 = _add_collection_card(db, u1.id, 'Clubs', 'K', 4)

        # Build a conquer figure
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

        rv = client.post('/kingdom/defence/remove_figure',
                         headers=auth_headers_user1,
                         json={'figure_id': fig_id})
        assert rv.status_code == 400


# ═══════════════════════════════════════════════════════════════════
#  POST /kingdom/defence/buy_battle_move & return_battle_move
# ═══════════════════════════════════════════════════════════════════

class TestDefenceBattleMoves:

    def test_buy_move_locks_card(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        land = _add_land(db, owner_id=u1.id)
        c1 = _add_collection_card(db, u1.id, 'Hearts', '7', 7)

        rv = client.post('/kingdom/defence/buy_battle_move',
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

        db.session.refresh(c1)
        assert c1.locked is True
        assert c1.lock_type == 'defence_move'

    def test_duplicate_round_index_rejected(self, client, db, two_users,
                                             auth_headers_user1):
        u1, _ = two_users
        land = _add_land(db, owner_id=u1.id)
        c1 = _add_collection_card(db, u1.id, 'Hearts', '7', 7)
        c2 = _add_collection_card(db, u1.id, 'Hearts', '8', 8)

        client.post('/kingdom/defence/buy_battle_move',
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

        rv = client.post('/kingdom/defence/buy_battle_move',
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

    def test_return_move_unlocks_card(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        land = _add_land(db, owner_id=u1.id)
        c1 = _add_collection_card(db, u1.id, 'Hearts', '7', 7)

        rv = client.post('/kingdom/defence/buy_battle_move',
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

        rv = client.post('/kingdom/defence/return_battle_move',
                         headers=auth_headers_user1,
                         json={'move_id': move_id})
        assert rv.status_code == 200
        assert rv.get_json()['config']['battle_moves'] == []

        db.session.refresh(c1)
        assert c1.locked is False

    def test_return_conquer_move_rejected(self, client, db, two_users,
                                          auth_headers_user1):
        """Cannot return a conquer move via defence endpoint."""
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

        rv = client.post('/kingdom/defence/return_battle_move',
                         headers=auth_headers_user1,
                         json={'move_id': move_id})
        assert rv.status_code == 400


# ═══════════════════════════════════════════════════════════════════
#  POST /kingdom/defence/set_modifier & remove_modifier
# ═══════════════════════════════════════════════════════════════════

class TestDefenceModifier:

    def test_set_peasant_war(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        land = _add_land(db, owner_id=u1.id)
        # Peasant War requires 2× J same-color
        _add_collection_card(db, u1.id, 'Hearts', 'J', 11)
        _add_collection_card(db, u1.id, 'Hearts', 'J', 11)

        rv = client.post('/kingdom/defence/set_modifier',
                         headers=auth_headers_user1,
                         json={'land_id': land.id, 'modifier_type': 'Peasant War'})
        assert rv.status_code == 200
        assert rv.get_json()['config']['battle_modifier'] == {'type': 'Peasant War'}

    def test_set_civil_war(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        land = _add_land(db, owner_id=u1.id)
        # Civil War requires 2× 5 same-color
        _add_collection_card(db, u1.id, 'Hearts', '5', 5)
        _add_collection_card(db, u1.id, 'Hearts', '5', 5)

        rv = client.post('/kingdom/defence/set_modifier',
                         headers=auth_headers_user1,
                         json={'land_id': land.id, 'modifier_type': 'Civil War'})
        assert rv.status_code == 200
        assert rv.get_json()['config']['battle_modifier'] == {'type': 'Civil War'}

    def test_reject_blitzkrieg(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        land = _add_land(db, owner_id=u1.id)

        rv = client.post('/kingdom/defence/set_modifier',
                         headers=auth_headers_user1,
                         json={'land_id': land.id, 'modifier_type': 'Blitzkrieg'})
        assert rv.status_code == 400

    def test_remove_modifier(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        land = _add_land(db, owner_id=u1.id)
        # Peasant War requires 2× J same-color
        _add_collection_card(db, u1.id, 'Hearts', 'J', 11)
        _add_collection_card(db, u1.id, 'Hearts', 'J', 11)

        client.post('/kingdom/defence/set_modifier',
                    headers=auth_headers_user1,
                    json={'land_id': land.id, 'modifier_type': 'Peasant War'})

        rv = client.post('/kingdom/defence/remove_modifier',
                         headers=auth_headers_user1,
                         json={'land_id': land.id})
        assert rv.status_code == 200
        assert rv.get_json()['config']['battle_modifier'] is None

    def test_remove_modifier_clears_second_battle_figure(self, client, db, two_users,
                                                          auth_headers_user1):
        u1, _ = two_users
        land = _add_land(db, owner_id=u1.id)

        # Set civil war + two same-color figures
        c1 = _add_collection_card(db, u1.id, 'Clubs', 'K', 4)
        c2 = _add_collection_card(db, u1.id, 'Clubs', 'Q', 3)
        # Civil War requires 2× 5 same-color
        _add_collection_card(db, u1.id, 'Hearts', '5', 5)
        _add_collection_card(db, u1.id, 'Hearts', '5', 5)
        _build_figure(client, auth_headers_user1, land.id, [c1.id],
                      produces={'villager_black': 2})
        rv = _build_figure(client, auth_headers_user1, land.id, [c2.id],
                           family='Mountain Queen', produces={'villager_black': 1})
        figs = rv.get_json()['config']['figures']
        fig1_id, fig2_id = figs[0]['id'], figs[1]['id']

        client.post('/kingdom/defence/set_modifier',
                    headers=auth_headers_user1,
                    json={'land_id': land.id, 'modifier_type': 'Civil War'})

        client.post('/kingdom/defence/set_battle_figure',
                    headers=auth_headers_user1,
                    json={'land_id': land.id, 'figure_id': fig1_id,
                          'figure_id_2': fig2_id})

        # Remove modifier → second battle figure cleared
        rv = client.post('/kingdom/defence/remove_modifier',
                         headers=auth_headers_user1,
                         json={'land_id': land.id})
        cfg = rv.get_json()['config']
        assert cfg.get('battle_figure_id_2') is None


# ═══════════════════════════════════════════════════════════════════
#  POST /kingdom/defence/set_battle_figure & clear_battle_figure
# ═══════════════════════════════════════════════════════════════════

class TestDefenceBattleFigure:

    def _setup_config_with_figure(self, client, db, u1, auth_headers_user1,
                                   produces=None):
        """Create a land + config + one figure, return (land, fig_id)."""
        land = _add_land(db, owner_id=u1.id)
        c1 = _add_collection_card(db, u1.id, 'Clubs', 'K', 4)
        rv = _build_figure(client, auth_headers_user1, land.id, [c1.id],
                           produces=produces or {'villager_black': 2})
        fig_id = rv.get_json()['config']['figures'][0]['id']
        return land, fig_id

    def test_set_battle_figure(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        land, fig_id = self._setup_config_with_figure(
            client, db, u1, auth_headers_user1)

        rv = client.post('/kingdom/defence/set_battle_figure',
                         headers=auth_headers_user1,
                         json={'land_id': land.id, 'figure_id': fig_id})
        assert rv.status_code == 200
        assert rv.get_json()['config']['battle_figure_id'] == fig_id

    def test_clear_battle_figure(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        land, fig_id = self._setup_config_with_figure(
            client, db, u1, auth_headers_user1)

        client.post('/kingdom/defence/set_battle_figure',
                    headers=auth_headers_user1,
                    json={'land_id': land.id, 'figure_id': fig_id})

        rv = client.post('/kingdom/defence/clear_battle_figure',
                         headers=auth_headers_user1,
                         json={'land_id': land.id})
        assert rv.status_code == 200
        assert rv.get_json()['config']['battle_figure_id'] is None

    def test_reject_deficit_figure(self, client, db, two_users, auth_headers_user1):
        """Figure with resource deficit cannot be selected as battle figure."""
        u1, _ = two_users
        land = _add_land(db, owner_id=u1.id)
        c1 = _add_collection_card(db, u1.id, 'Clubs', 'J', 1)
        c2 = _add_collection_card(db, u1.id, 'Clubs', '8', 8)

        rv = _build_figure(client, auth_headers_user1, land.id,
                           [c1.id, c2.id], ['key', 'number'],
                           family='Small Yack Farm', field='village',
                           produces={'food_black': 8},
                           requires={'villager_black': 1})
        fig_id = rv.get_json()['config']['figures'][0]['id']

        rv = client.post('/kingdom/defence/set_battle_figure',
                         headers=auth_headers_user1,
                         json={'land_id': land.id, 'figure_id': fig_id})
        assert rv.status_code == 400
        assert 'deficit' in rv.get_json()['message'].lower()

    def test_mutual_exclusion_with_spell(self, client, db, two_users,
                                          auth_headers_user1):
        """Cannot set battle figure while a spell is active."""
        u1, _ = two_users
        land, fig_id = self._setup_config_with_figure(
            client, db, u1, auth_headers_user1)

        # Poison requires 2× 3 same-color black
        _add_collection_card(db, u1.id, 'Clubs', '3', 3)
        _add_collection_card(db, u1.id, 'Clubs', '3', 3)

        # Set spell first
        client.post('/kingdom/defence/set_spell',
                    headers=auth_headers_user1,
                    json={'land_id': land.id, 'spell_name': 'poison',
                          'spell_card_ids': []})

        # Try to set battle figure
        rv = client.post('/kingdom/defence/set_battle_figure',
                         headers=auth_headers_user1,
                         json={'land_id': land.id, 'figure_id': fig_id})
        assert rv.status_code == 400
        assert 'spell' in rv.get_json()['message'].lower()

    def test_civil_war_requires_two_figures(self, client, db, two_users,
                                             auth_headers_user1):
        u1, _ = two_users
        land, fig_id = self._setup_config_with_figure(
            client, db, u1, auth_headers_user1)

        # Civil War requires 2× 5 same-color
        _add_collection_card(db, u1.id, 'Hearts', '5', 5)
        _add_collection_card(db, u1.id, 'Hearts', '5', 5)

        client.post('/kingdom/defence/set_modifier',
                    headers=auth_headers_user1,
                    json={'land_id': land.id, 'modifier_type': 'Civil War'})

        rv = client.post('/kingdom/defence/set_battle_figure',
                         headers=auth_headers_user1,
                         json={'land_id': land.id, 'figure_id': fig_id})
        assert rv.status_code == 400
        assert 'two' in rv.get_json()['message'].lower()

    def test_civil_war_same_color(self, client, db, two_users, auth_headers_user1):
        """Civil War: both figures must be the same color."""
        u1, _ = two_users
        land = _add_land(db, owner_id=u1.id)
        c1 = _add_collection_card(db, u1.id, 'Clubs', 'K', 4)
        c2 = _add_collection_card(db, u1.id, 'Hearts', 'K', 4)
        # Civil War requires 2× 5 same-color
        _add_collection_card(db, u1.id, 'Hearts', '5', 5)
        _add_collection_card(db, u1.id, 'Hearts', '5', 5)

        rv1 = _build_figure(client, auth_headers_user1, land.id, [c1.id],
                            color='defensive', produces={'villager_black': 2})
        rv2 = _build_figure(client, auth_headers_user1, land.id, [c2.id],
                            family='Djungle King', color='offensive',
                            produces={'villager_red': 2})
        f1 = rv1.get_json()['config']['figures'][0]['id']
        f2 = rv2.get_json()['config']['figures'][-1]['id']

        client.post('/kingdom/defence/set_modifier',
                    headers=auth_headers_user1,
                    json={'land_id': land.id, 'modifier_type': 'Civil War'})

        rv = client.post('/kingdom/defence/set_battle_figure',
                         headers=auth_headers_user1,
                         json={'land_id': land.id, 'figure_id': f1,
                               'figure_id_2': f2})
        assert rv.status_code == 400
        assert 'color' in rv.get_json()['message'].lower()

    def test_civil_war_same_color_success(self, client, db, two_users,
                                           auth_headers_user1):
        u1, _ = two_users
        land = _add_land(db, owner_id=u1.id)
        c1 = _add_collection_card(db, u1.id, 'Clubs', 'K', 4)
        c2 = _add_collection_card(db, u1.id, 'Clubs', 'Q', 3)
        # Civil War requires 2× 5 same-color
        _add_collection_card(db, u1.id, 'Hearts', '5', 5)
        _add_collection_card(db, u1.id, 'Hearts', '5', 5)

        rv1 = _build_figure(client, auth_headers_user1, land.id, [c1.id],
                            produces={'villager_black': 2})
        rv2 = _build_figure(client, auth_headers_user1, land.id, [c2.id],
                            family='Mountain Queen', produces={'villager_black': 1})
        f1 = rv1.get_json()['config']['figures'][0]['id']
        f2 = rv2.get_json()['config']['figures'][-1]['id']

        client.post('/kingdom/defence/set_modifier',
                    headers=auth_headers_user1,
                    json={'land_id': land.id, 'modifier_type': 'Civil War'})

        rv = client.post('/kingdom/defence/set_battle_figure',
                         headers=auth_headers_user1,
                         json={'land_id': land.id, 'figure_id': f1,
                               'figure_id_2': f2})
        assert rv.status_code == 200
        cfg = rv.get_json()['config']
        assert cfg['battle_figure_id'] == f1
        assert cfg['battle_figure_id_2'] == f2


# ═══════════════════════════════════════════════════════════════════
#  POST /kingdom/defence/set_spell & clear_spell
# ═══════════════════════════════════════════════════════════════════

class TestDefenceSpell:

    def test_set_poison(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        land = _add_land(db, owner_id=u1.id)
        # Need config first
        client.get(f'/kingdom/defence/config?land_id={land.id}',
                   headers=auth_headers_user1)
        # Poison requires 2× 3 same-color black
        _add_collection_card(db, u1.id, 'Clubs', '3', 3)
        _add_collection_card(db, u1.id, 'Clubs', '3', 3)

        rv = client.post('/kingdom/defence/set_spell',
                         headers=auth_headers_user1,
                         json={'land_id': land.id, 'spell_name': 'poison',
                               'spell_card_ids': []})
        assert rv.status_code == 200
        assert rv.get_json()['config']['spell_name'] == 'poison'

    def test_set_health_boost_requires_target(self, client, db, two_users,
                                                auth_headers_user1):
        u1, _ = two_users
        land = _add_land(db, owner_id=u1.id)
        client.get(f'/kingdom/defence/config?land_id={land.id}',
                   headers=auth_headers_user1)
        # Health boost requires 2× 3 same-color red
        _add_collection_card(db, u1.id, 'Hearts', '3', 3)
        _add_collection_card(db, u1.id, 'Hearts', '3', 3)

        rv = client.post('/kingdom/defence/set_spell',
                         headers=auth_headers_user1,
                         json={'land_id': land.id, 'spell_name': 'health_boost',
                               'spell_card_ids': []})
        assert rv.status_code == 400
        assert 'target' in rv.get_json()['message'].lower()

    def test_set_health_boost_with_target(self, client, db, two_users,
                                           auth_headers_user1):
        u1, _ = two_users
        land = _add_land(db, owner_id=u1.id)
        c1 = _add_collection_card(db, u1.id, 'Clubs', 'K', 4)
        # Health boost requires 2× 3 same-color red
        _add_collection_card(db, u1.id, 'Hearts', '3', 3)
        _add_collection_card(db, u1.id, 'Hearts', '3', 3)
        rv = _build_figure(client, auth_headers_user1, land.id, [c1.id],
                           produces={'villager_black': 2})
        fig_id = rv.get_json()['config']['figures'][0]['id']

        rv = client.post('/kingdom/defence/set_spell',
                         headers=auth_headers_user1,
                         json={'land_id': land.id, 'spell_name': 'health_boost',
                               'spell_card_ids': [],
                               'spell_target_figure_id': fig_id})
        assert rv.status_code == 200
        cfg = rv.get_json()['config']
        assert cfg['spell_name'] == 'health_boost'
        assert cfg['spell_target_figure_id'] == fig_id

    def test_invalid_spell_name(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        land = _add_land(db, owner_id=u1.id)
        client.get(f'/kingdom/defence/config?land_id={land.id}',
                   headers=auth_headers_user1)

        rv = client.post('/kingdom/defence/set_spell',
                         headers=auth_headers_user1,
                         json={'land_id': land.id, 'spell_name': 'fireball'})
        assert rv.status_code == 400

    def test_spell_mutual_exclusion_with_battle_figure(self, client, db, two_users,
                                                        auth_headers_user1):
        """Cannot set spell while a battle figure is selected."""
        u1, _ = two_users
        land = _add_land(db, owner_id=u1.id)
        c1 = _add_collection_card(db, u1.id, 'Clubs', 'K', 4)
        rv = _build_figure(client, auth_headers_user1, land.id, [c1.id],
                           produces={'villager_black': 2})
        fig_id = rv.get_json()['config']['figures'][0]['id']

        # Set battle figure
        client.post('/kingdom/defence/set_battle_figure',
                    headers=auth_headers_user1,
                    json={'land_id': land.id, 'figure_id': fig_id})

        # Try to set spell
        rv = client.post('/kingdom/defence/set_spell',
                         headers=auth_headers_user1,
                         json={'land_id': land.id, 'spell_name': 'poison',
                               'spell_card_ids': []})
        assert rv.status_code == 400
        assert 'battle figure' in rv.get_json()['message'].lower()

    def test_clear_spell(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        land = _add_land(db, owner_id=u1.id)
        client.get(f'/kingdom/defence/config?land_id={land.id}',
                   headers=auth_headers_user1)
        # Poison requires 2× 3 same-color black
        _add_collection_card(db, u1.id, 'Clubs', '3', 3)
        _add_collection_card(db, u1.id, 'Clubs', '3', 3)

        client.post('/kingdom/defence/set_spell',
                    headers=auth_headers_user1,
                    json={'land_id': land.id, 'spell_name': 'poison',
                          'spell_card_ids': []})

        rv = client.post('/kingdom/defence/clear_spell',
                         headers=auth_headers_user1,
                         json={'land_id': land.id})
        assert rv.status_code == 200
        cfg = rv.get_json()['config']
        assert cfg['spell_name'] is None
        assert cfg['spell_card_ids'] is None

    def test_spell_locks_and_unlocks_cards(self, client, db, two_users,
                                            auth_headers_user1):
        u1, _ = two_users
        land = _add_land(db, owner_id=u1.id)
        client.get(f'/kingdom/defence/config?land_id={land.id}',
                   headers=auth_headers_user1)
        sc1 = _add_collection_card(db, u1.id, 'Diamonds', '7', 7)
        sc2 = _add_collection_card(db, u1.id, 'Diamonds', '8', 8)

        # Set spell with cards
        client.post('/kingdom/defence/set_spell',
                    headers=auth_headers_user1,
                    json={'land_id': land.id, 'spell_name': 'poison',
                          'spell_card_ids': [sc1.id, sc2.id]})

        db.session.refresh(sc1)
        db.session.refresh(sc2)
        assert sc1.locked is True
        assert sc1.lock_type == 'defence_spell'
        assert sc2.locked is True

        # Clear spell → unlock
        client.post('/kingdom/defence/clear_spell',
                    headers=auth_headers_user1,
                    json={'land_id': land.id})

        db.session.refresh(sc1)
        db.session.refresh(sc2)
        assert sc1.locked is False
        assert sc2.locked is False


# ═══════════════════════════════════════════════════════════════════
#  POST /kingdom/defence/set_auto_gamble
# ═══════════════════════════════════════════════════════════════════

class TestDefenceAutoGamble:

    def test_set_auto_gamble_on(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        land = _add_land(db, owner_id=u1.id)
        client.get(f'/kingdom/defence/config?land_id={land.id}',
                   headers=auth_headers_user1)

        rv = client.post('/kingdom/defence/set_auto_gamble',
                         headers=auth_headers_user1,
                         json={'land_id': land.id, 'auto_gamble': True})
        assert rv.status_code == 200
        assert rv.get_json()['config']['auto_gamble'] is True
        assert rv.get_json()['config']['auto_gamble_threshold'] == 10

    def test_set_auto_gamble_off(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        land = _add_land(db, owner_id=u1.id)
        client.get(f'/kingdom/defence/config?land_id={land.id}',
                   headers=auth_headers_user1)

        client.post('/kingdom/defence/set_auto_gamble',
                    headers=auth_headers_user1,
                    json={'land_id': land.id, 'auto_gamble': True})

        rv = client.post('/kingdom/defence/set_auto_gamble',
                         headers=auth_headers_user1,
                         json={'land_id': land.id, 'auto_gamble': False})
        assert rv.status_code == 200
        assert rv.get_json()['config']['auto_gamble'] is False
        assert rv.get_json()['config']['auto_gamble_threshold'] == 10

    def test_rejects_non_owned_land(self, client, db, two_users, auth_headers_user1):
        _, u2 = two_users
        land = _add_land(db, owner_id=u2.id)

        rv = client.post('/kingdom/defence/set_auto_gamble',
                         headers=auth_headers_user1,
                         json={'land_id': land.id, 'auto_gamble': True})
        assert rv.status_code == 403


class TestDefenceAutoGambleThreshold:

    def test_set_threshold_updates_config(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        land = _add_land(db, owner_id=u1.id)
        client.get(f'/kingdom/defence/config?land_id={land.id}',
                   headers=auth_headers_user1)

        rv = client.post('/kingdom/defence/set_auto_gamble_threshold',
                         headers=auth_headers_user1,
                         json={'land_id': land.id, 'auto_gamble_threshold': 13})
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['config']['auto_gamble_threshold'] == 13

        cfg = LandConfig.query.filter_by(
            user_id=u1.id, config_type='defence', land_id=land.id
        ).first()
        assert cfg.auto_gamble_threshold == 13

    def test_set_threshold_clamps_to_bounds(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        land = _add_land(db, owner_id=u1.id)
        client.get(f'/kingdom/defence/config?land_id={land.id}',
                   headers=auth_headers_user1)

        rv_high = client.post('/kingdom/defence/set_auto_gamble_threshold',
                              headers=auth_headers_user1,
                              json={'land_id': land.id, 'auto_gamble_threshold': 999})
        assert rv_high.status_code == 200
        assert rv_high.get_json()['config']['auto_gamble_threshold'] == 20

        rv_low = client.post('/kingdom/defence/set_auto_gamble_threshold',
                             headers=auth_headers_user1,
                             json={'land_id': land.id, 'auto_gamble_threshold': -5})
        assert rv_low.status_code == 200
        assert rv_low.get_json()['config']['auto_gamble_threshold'] == 1

    def test_set_threshold_rejects_non_owned_land(self, client, db, two_users, auth_headers_user1):
        _, u2 = two_users
        land = _add_land(db, owner_id=u2.id)

        rv = client.post('/kingdom/defence/set_auto_gamble_threshold',
                         headers=auth_headers_user1,
                         json={'land_id': land.id, 'auto_gamble_threshold': 12})
        assert rv.status_code == 403
