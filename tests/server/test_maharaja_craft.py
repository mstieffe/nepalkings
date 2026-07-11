# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for crafting Maharaja ('MK') cards and their downstream handling.

Covers POST /collection/craft_maharaja, the resulting GET /collection/cards
grouping, and the two runtime touch points that must recognise 'MK':
``routes.kingdom._normalize_main_rank`` (conquer battle runtime) and
``routes.games._loot_card_bucket`` (conquer loot classification).
"""

from models import db as _db, CollectionCard
from routes.collection import MAHARAJA_CRAFT_RANKS


# ── Helpers ──────────────────────────────────────────────────────────────────

def _add_cards(db, user_id, suit, rank, value, count=1, locked=False):
    """Insert *count* CollectionCard rows."""
    for _ in range(count):
        db.session.add(CollectionCard(
            user_id=user_id, suit=suit, rank=rank, value=value, locked=locked))
    db.session.commit()


def _grant_full_suit(db, user_id, suit, extra=None, skip=None, lock_rank=None):
    """Grant one free copy of every craft rank for *suit*.

    ``extra`` duplicates a given rank (list of ranks to add a second copy of).
    ``skip`` omits a rank entirely. ``lock_rank`` grants the rank but locked.
    """
    extra = extra or []
    for rank in MAHARAJA_CRAFT_RANKS:
        if rank == skip:
            continue
        if rank == lock_rank:
            _add_cards(db, user_id, suit, rank, 4, count=1, locked=True)
            continue
        _add_cards(db, user_id, suit, rank, 4, count=1)
        if rank in extra:
            _add_cards(db, user_id, suit, rank, 4, count=1)


# ═══════════════════════════════════════════════════════════════════
#  POST /collection/craft_maharaja
# ═══════════════════════════════════════════════════════════════════

class TestCraftMaharaja:
    def test_craft_succeeds_with_one_of_each(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        _grant_full_suit(db, u1.id, 'Hearts')

        rv = client.post('/collection/craft_maharaja', headers=auth_headers_user1,
                         json={'suit': 'Hearts'})
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['success'] is True
        assert data['card'] == {'suit': 'Hearts', 'rank': 'MK', 'value': 4}
        assert data['consumed'] == 13

        # All 13 source cards gone
        for rank in MAHARAJA_CRAFT_RANKS:
            assert CollectionCard.query.filter_by(
                user_id=u1.id, suit='Hearts', rank=rank).count() == 0

        # Exactly one MK card created
        mk_cards = CollectionCard.query.filter_by(
            user_id=u1.id, suit='Hearts', rank='MK').all()
        assert len(mk_cards) == 1
        assert mk_cards[0].value == 4
        assert mk_cards[0].locked is False

    def test_craft_fails_when_rank_missing(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        _grant_full_suit(db, u1.id, 'Spades', skip='Q')

        rv = client.post('/collection/craft_maharaja', headers=auth_headers_user1,
                         json={'suit': 'Spades'})
        assert rv.status_code == 400
        data = rv.get_json()
        assert data['success'] is False
        assert 'Q' in data['message']

        # Nothing consumed
        remaining = CollectionCard.query.filter_by(user_id=u1.id, suit='Spades').count()
        assert remaining == 12  # 13 ranks minus the skipped one
        assert CollectionCard.query.filter_by(
            user_id=u1.id, suit='Spades', rank='MK').count() == 0

    def test_craft_fails_when_only_locked_copy_present(self, client, db, two_users,
                                                        auth_headers_user1):
        u1, _ = two_users
        _grant_full_suit(db, u1.id, 'Clubs', lock_rank='K')

        rv = client.post('/collection/craft_maharaja', headers=auth_headers_user1,
                         json={'suit': 'Clubs'})
        assert rv.status_code == 400
        assert rv.get_json()['success'] is False

        # Nothing consumed — the locked K is untouched, others remain too
        assert CollectionCard.query.filter_by(
            user_id=u1.id, suit='Clubs', rank='K', locked=True).count() == 1
        assert CollectionCard.query.filter_by(user_id=u1.id, suit='Clubs').count() == 13
        assert CollectionCard.query.filter_by(
            user_id=u1.id, suit='Clubs', rank='MK').count() == 0

    def test_craft_consumes_only_one_of_duplicated_rank(self, client, db, two_users,
                                                          auth_headers_user1):
        u1, _ = two_users
        _grant_full_suit(db, u1.id, 'Diamonds', extra=['7'])

        rv = client.post('/collection/craft_maharaja', headers=auth_headers_user1,
                         json={'suit': 'Diamonds'})
        assert rv.status_code == 200
        assert rv.get_json()['success'] is True

        # The duplicate 7 survives craft (only one consumed)
        assert CollectionCard.query.filter_by(
            user_id=u1.id, suit='Diamonds', rank='7').count() == 1
        assert CollectionCard.query.filter_by(
            user_id=u1.id, suit='Diamonds', rank='MK').count() == 1

    def test_craft_invalid_suit(self, client, auth_headers_user1):
        rv = client.post('/collection/craft_maharaja', headers=auth_headers_user1,
                         json={'suit': 'Bogus'})
        assert rv.status_code == 400
        assert rv.get_json()['success'] is False

    def test_craft_missing_suit(self, client, auth_headers_user1):
        rv = client.post('/collection/craft_maharaja', headers=auth_headers_user1, json={})
        assert rv.status_code == 400

    def test_craft_requires_auth(self, client):
        rv = client.post('/collection/craft_maharaja', json={'suit': 'Hearts'})
        assert rv.status_code == 401

    def test_craft_then_get_cards_shows_mk_row(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        _grant_full_suit(db, u1.id, 'Hearts')
        client.post('/collection/craft_maharaja', headers=auth_headers_user1,
                    json={'suit': 'Hearts'})

        rv = client.get('/collection/cards', headers=auth_headers_user1)
        data = rv.get_json()
        assert data['success'] is True
        mk_entry = next((c for c in data['cards']
                          if c['suit'] == 'Hearts' and c['rank'] == 'MK'), None)
        assert mk_entry is not None
        assert mk_entry['total'] == 1
        assert mk_entry['free'] == 1
        assert mk_entry['locked'] == 0
        assert mk_entry['value'] == 4


# ═══════════════════════════════════════════════════════════════════
#  Runtime rank handling for 'MK'
# ═══════════════════════════════════════════════════════════════════

class TestMaharajaRuntimeMapping:
    def test_normalize_main_rank_maps_mk_to_king(self, app):
        from routes.kingdom import _normalize_main_rank
        assert _normalize_main_rank('MK') == 'K'

    def test_loot_card_bucket_mk_is_key(self, app):
        from routes.games import _loot_card_bucket
        assert _loot_card_bucket('MK') == 'key'
