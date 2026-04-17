# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for GET /kingdom/rankings endpoint."""

import pytest
from models import db as _db, Land, LandAttackLog


# ── Helpers ──────────────────────────────────────────────────────────────────

def _add_land(db, owner_id, col, row, gold_rate=5.0):
    land = Land(
        col=col, row=row, tier=1, gold_rate=gold_rate,
        suit_bonus_suit='Hearts', suit_bonus_value=1,
        owner_user_id=owner_id,
    )
    db.session.add(land)
    db.session.commit()
    return land


def _add_attack_log(db, land_id, attacker_id, defender_id, result):
    log = LandAttackLog(
        land_id=land_id,
        attacker_user_id=attacker_id,
        defender_user_id=defender_id,
        result=result,
    )
    db.session.add(log)
    db.session.commit()
    return log


# ═══════════════════════════════════════════════════════════════════
#  GET /kingdom/rankings
# ═══════════════════════════════════════════════════════════════════

class TestKingdomRankings:

    def test_empty_rankings(self, client, auth_headers_user1):
        """No lands or attacks → empty rankings."""
        rv = client.get('/kingdom/rankings', headers=auth_headers_user1)
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['success'] is True
        assert data['rankings'] == []

    def test_one_user_with_lands(self, client, db, two_users, auth_headers_user1):
        """User with lands appears in rankings."""
        u1, _ = two_users
        _add_land(db, u1.id, 0, 0, gold_rate=10.0)
        _add_land(db, u1.id, 1, 0, gold_rate=5.0)

        rv = client.get('/kingdom/rankings', headers=auth_headers_user1)
        data = rv.get_json()
        assert len(data['rankings']) == 1
        r = data['rankings'][0]
        assert r['username'] == 'player1'
        assert r['lands_owned'] == 2
        assert r['total_gold_rate'] == 15.0

    def test_sorted_by_lands_owned_desc(self, client, db, two_users, auth_headers_user1):
        """Rankings sorted by lands_owned descending."""
        u1, u2 = two_users
        _add_land(db, u1.id, 0, 0)
        _add_land(db, u2.id, 1, 0)
        _add_land(db, u2.id, 2, 0)

        rv = client.get('/kingdom/rankings', headers=auth_headers_user1)
        data = rv.get_json()
        assert data['rankings'][0]['username'] == 'player2'
        assert data['rankings'][1]['username'] == 'player1'

    def test_attack_stats(self, client, db, two_users, auth_headers_user1):
        """Conquer attempts, wins and defence wins counted correctly."""
        u1, u2 = two_users
        land = _add_land(db, u2.id, 0, 0)
        # u1 attacks u2: 2 attempts, 1 win
        _add_attack_log(db, land.id, u1.id, u2.id, 'attacker_won')
        _add_attack_log(db, land.id, u1.id, u2.id, 'defender_won')

        rv = client.get('/kingdom/rankings', headers=auth_headers_user1)
        data = rv.get_json()
        rankings = {r['username']: r for r in data['rankings']}

        assert rankings['player1']['conquer_attempts'] == 2
        assert rankings['player1']['conquer_wins'] == 1
        assert rankings['player2']['defence_wins'] == 1

    def test_user_with_only_attacks_appears(self, client, db, two_users, auth_headers_user1):
        """User with no lands but attack logs still appears."""
        u1, u2 = two_users
        land = _add_land(db, u2.id, 0, 0)
        _add_attack_log(db, land.id, u1.id, u2.id, 'defender_won')

        rv = client.get('/kingdom/rankings', headers=auth_headers_user1)
        data = rv.get_json()
        usernames = [r['username'] for r in data['rankings']]
        assert 'player1' in usernames

    def test_no_auth_required(self, client, db, two_users):
        """Rankings endpoint does not require authentication."""
        u1, _ = two_users
        _add_land(db, u1.id, 0, 0)
        rv = client.get('/kingdom/rankings')
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['success'] is True
