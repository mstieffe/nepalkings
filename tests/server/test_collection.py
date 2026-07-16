# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for collection routes — cards, selling, buying and opening boosters."""

import pytest
from models import db as _db, User, CollectionCard
import server_settings as settings


# ── Helpers ──────────────────────────────────────────────────────────────────

def _add_cards(db, user_id, suit, rank, value, count=1, locked=False):
    """Insert *count* CollectionCard rows."""
    for _ in range(count):
        db.session.add(CollectionCard(
            user_id=user_id, suit=suit, rank=rank, value=value, locked=locked))
    db.session.commit()


# ═══════════════════════════════════════════════════════════════════
#  GET /collection/cards
# ═══════════════════════════════════════════════════════════════════

class TestGetCards:
    def test_empty_collection(self, client, auth_headers_user1):
        rv = client.get('/collection/cards', headers=auth_headers_user1)
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['success'] is True
        assert data['cards'] == []

    def test_returns_grouped_cards(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        _add_cards(db, u1.id, 'Hearts', 'K', 4, count=3)
        _add_cards(db, u1.id, 'Hearts', 'K', 4, count=1, locked=True)
        _add_cards(db, u1.id, 'Spades', '7', 7, count=2)

        rv = client.get('/collection/cards', headers=auth_headers_user1)
        data = rv.get_json()
        assert data['success'] is True
        assert len(data['cards']) == 2

        hearts_k = next(c for c in data['cards'] if c['suit'] == 'Hearts' and c['rank'] == 'K')
        assert hearts_k['total'] == 4
        assert hearts_k['locked'] == 1
        assert hearts_k['free'] == 3
        assert hearts_k['value'] == 4

        spades_7 = next(c for c in data['cards'] if c['suit'] == 'Spades' and c['rank'] == '7')
        assert spades_7['total'] == 2
        assert spades_7['locked'] == 0
        assert spades_7['free'] == 2

    def test_returns_booster_and_gold(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        u1.booster_packs = 5
        u1.booster_packs_side = 3
        u1.gold = 999
        db.session.commit()

        rv = client.get('/collection/cards', headers=auth_headers_user1)
        data = rv.get_json()
        assert data['booster_packs'] == 5
        assert data['booster_packs_side'] == 3
        assert data['gold'] == 999

    def test_requires_auth(self, client):
        rv = client.get('/collection/cards')
        assert rv.status_code == 401


# ═══════════════════════════════════════════════════════════════════
#  POST /collection/sell_card
# ═══════════════════════════════════════════════════════════════════

class TestSellCard:
    def test_sell_number_card(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        _add_cards(db, u1.id, 'Hearts', '9', 9, count=3)
        u1.gold = 50
        db.session.commit()

        rv = client.post('/collection/sell_card', headers=auth_headers_user1,
                         json={'suit': 'Hearts', 'rank': '9', 'quantity': 2})
        data = rv.get_json()
        assert data['success'] is True
        assert data['gold_earned'] == 18  # 9 × 2
        assert data['gold'] == 68        # 50 + 18

        remaining = CollectionCard.query.filter_by(user_id=u1.id, suit='Hearts', rank='9').count()
        assert remaining == 1

    def test_sell_key_card(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        _add_cards(db, u1.id, 'Spades', 'K', 4, count=2)
        u1.gold = 0
        db.session.commit()

        rv = client.post('/collection/sell_card', headers=auth_headers_user1,
                         json={'suit': 'Spades', 'rank': 'K', 'quantity': 1})
        data = rv.get_json()
        assert data['success'] is True
        assert data['gold_earned'] == 40  # 4 × 10
        assert data['gold'] == 40

    def test_sell_side_card(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        _add_cards(db, u1.id, 'Clubs', '3', 3, count=2)
        u1.gold = 10
        db.session.commit()

        rv = client.post('/collection/sell_card', headers=auth_headers_user1,
                         json={'suit': 'Clubs', 'rank': '3', 'quantity': 1})
        data = rv.get_json()
        assert data['success'] is True
        assert data['gold_earned'] == 3  # face value
        assert data['gold'] == 13

    def test_sell_not_enough_free(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        _add_cards(db, u1.id, 'Hearts', 'Q', 2, count=1)
        _add_cards(db, u1.id, 'Hearts', 'Q', 2, count=1, locked=True)

        rv = client.post('/collection/sell_card', headers=auth_headers_user1,
                         json={'suit': 'Hearts', 'rank': 'Q', 'quantity': 2})
        assert rv.status_code == 400
        assert 'Not enough free cards' in rv.get_json()['message']

    def test_sell_locked_cards_excluded(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        _add_cards(db, u1.id, 'Diamonds', 'A', 3, count=2, locked=True)

        rv = client.post('/collection/sell_card', headers=auth_headers_user1,
                         json={'suit': 'Diamonds', 'rank': 'A', 'quantity': 1})
        assert rv.status_code == 400

    def test_sell_invalid_rank(self, client, auth_headers_user1):
        rv = client.post('/collection/sell_card', headers=auth_headers_user1,
                         json={'suit': 'Hearts', 'rank': 'X', 'quantity': 1})
        assert rv.status_code == 400

    def test_sell_invalid_suit(self, client, auth_headers_user1):
        rv = client.post('/collection/sell_card', headers=auth_headers_user1,
                         json={'suit': 'Bananas', 'rank': '7', 'quantity': 1})
        assert rv.status_code == 400

    def test_sell_zero_quantity(self, client, auth_headers_user1):
        rv = client.post('/collection/sell_card', headers=auth_headers_user1,
                         json={'suit': 'Hearts', 'rank': '7', 'quantity': 0})
        assert rv.status_code == 400

    def test_sell_missing_fields(self, client, auth_headers_user1):
        rv = client.post('/collection/sell_card', headers=auth_headers_user1, json={})
        assert rv.status_code == 400

    def test_sell_maharaja_rejected(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        _add_cards(db, u1.id, 'Hearts', 'MK', 4, count=1)

        rv = client.post('/collection/sell_card', headers=auth_headers_user1,
                         json={'suit': 'Hearts', 'rank': 'MK', 'quantity': 1})
        assert rv.status_code == 400
        assert rv.get_json()['success'] is False


# ═══════════════════════════════════════════════════════════════════
#  POST /collection/buy_booster
# ═══════════════════════════════════════════════════════════════════

class TestBuyBooster:
    def test_buy_one(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        u1.gold = 200
        db.session.commit()

        rv = client.post('/collection/buy_booster', headers=auth_headers_user1,
                         json={'quantity': 1})
        data = rv.get_json()
        assert data['success'] is True
        assert data['booster_packs'] == 1
        assert data['gold'] == 100  # 200 - 100

    def test_buy_multiple(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        u1.gold = 500
        db.session.commit()

        rv = client.post('/collection/buy_booster', headers=auth_headers_user1,
                         json={'quantity': 3})
        data = rv.get_json()
        assert data['success'] is True
        assert data['booster_packs'] == 3
        assert data['gold'] == 200

    def test_buy_insufficient_gold(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        u1.gold = 50
        db.session.commit()

        rv = client.post('/collection/buy_booster', headers=auth_headers_user1,
                         json={'quantity': 1})
        assert rv.status_code == 400
        assert 'Insufficient gold' in rv.get_json()['message']

    def test_buy_invalid_quantity(self, client, auth_headers_user1):
        rv = client.post('/collection/buy_booster', headers=auth_headers_user1,
                         json={'quantity': -1})
        assert rv.status_code == 400


# ═══════════════════════════════════════════════════════════════════
#  POST /collection/buy_booster_side
# ═══════════════════════════════════════════════════════════════════

class TestBuyBoosterSide:
    def test_buy_one(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        u1.gold = 200
        db.session.commit()

        rv = client.post('/collection/buy_booster_side', headers=auth_headers_user1,
                         json={'quantity': 1})
        data = rv.get_json()
        assert data['success'] is True
        assert data['booster_packs_side'] == 1
        assert data['gold'] == 100

    def test_buy_insufficient_gold(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        u1.gold = 50
        db.session.commit()

        rv = client.post('/collection/buy_booster_side', headers=auth_headers_user1,
                         json={'quantity': 1})
        assert rv.status_code == 400


# ═══════════════════════════════════════════════════════════════════
#  POST /collection/open_booster
# ═══════════════════════════════════════════════════════════════════

class TestOpenBooster:
    def test_open_one(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        u1.booster_packs = 2
        # Isolate the booster draw from the first-open starter-set grant.
        u1.onboarding_state = dict(u1.onboarding_state or {}, starter_set_granted=True)
        db.session.commit()

        rv = client.post('/collection/open_booster', headers=auth_headers_user1)
        data = rv.get_json()
        assert data['success'] is True
        assert len(data['cards']) == 3  # BOOSTER_PACK_CARDS
        assert data['booster_packs'] == 1

        # Cards should be valid main-card ranks
        for card in data['cards']:
            assert card['rank'] in ['7', '8', '9', '10', 'J', 'Q', 'K', 'A']
            assert card['suit'] in ['Hearts', 'Diamonds', 'Clubs', 'Spades']
            assert card['value'] > 0
            assert card['tier'] in settings.BOOSTER_TIER_RANKS
            assert card['rank'] in settings.BOOSTER_TIER_RANKS[card['tier']]

        # Cards should exist in DB
        db_cards = CollectionCard.query.filter_by(user_id=u1.id).all()
        assert len(db_cards) == 3

    def test_open_no_packs(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        u1.booster_packs = 0
        db.session.commit()

        rv = client.post('/collection/open_booster', headers=auth_headers_user1)
        assert rv.status_code == 400
        assert 'No booster packs' in rv.get_json()['message']

    def test_open_multiple_accumulate(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        u1.booster_packs = 3
        # Isolate the booster draw from the first-open starter-set grant.
        u1.onboarding_state = dict(u1.onboarding_state or {}, starter_set_granted=True)
        db.session.commit()

        # Open twice
        client.post('/collection/open_booster', headers=auth_headers_user1)
        rv = client.post('/collection/open_booster', headers=auth_headers_user1)
        data = rv.get_json()
        assert data['booster_packs'] == 1

        db_cards = CollectionCard.query.filter_by(user_id=u1.id).all()
        assert len(db_cards) == 6  # 3 + 3

    def test_open_quantity_opens_many_in_one_response(self, client, db, two_users,
                                                       auth_headers_user1):
        u1, _ = two_users
        u1.booster_packs = 4
        # Isolate the booster draw from the first-open starter-set grant.
        u1.onboarding_state = dict(u1.onboarding_state or {}, starter_set_granted=True)
        db.session.commit()

        rv = client.post('/collection/open_booster', headers=auth_headers_user1,
                         json={'quantity': 4})
        data = rv.get_json()

        assert data['success'] is True
        assert data['opened_boosters'] == 4
        assert data['booster_packs'] == 0
        assert len(data['cards']) == 12
        assert CollectionCard.query.filter_by(user_id=u1.id).count() == 12

    def test_open_quantity_rejects_more_than_owned(self, client, db, two_users,
                                                   auth_headers_user1):
        u1, _ = two_users
        u1.booster_packs = 2
        db.session.commit()

        rv = client.post('/collection/open_booster', headers=auth_headers_user1,
                         json={'quantity': 3})

        assert rv.status_code == 400
        assert 'Not enough booster packs' in rv.get_json()['message']


# ═══════════════════════════════════════════════════════════════════
#  POST /collection/open_booster_side
# ═══════════════════════════════════════════════════════════════════

class TestOpenBoosterSide:
    def test_open_one(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        u1.booster_packs_side = 2
        db.session.commit()

        rv = client.post('/collection/open_booster_side', headers=auth_headers_user1)
        data = rv.get_json()
        assert data['success'] is True
        assert len(data['cards']) == 3
        assert data['booster_packs_side'] == 1

        # Cards should be valid side-card ranks
        for card in data['cards']:
            assert card['rank'] in ['2', '3', '4', '5', '6']
            assert card['suit'] in ['Hearts', 'Diamonds', 'Clubs', 'Spades']
            assert card['value'] > 0
            assert card['tier'] in settings.BOOSTER_SIDE_TIER_RANKS
            assert card['rank'] in settings.BOOSTER_SIDE_TIER_RANKS[card['tier']]

        db_cards = CollectionCard.query.filter_by(user_id=u1.id).all()
        assert len(db_cards) == 3

    def test_open_no_packs(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        u1.booster_packs_side = 0
        db.session.commit()

        rv = client.post('/collection/open_booster_side', headers=auth_headers_user1)
        assert rv.status_code == 400

    def test_open_quantity_side(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        u1.booster_packs_side = 3
        db.session.commit()

        rv = client.post('/collection/open_booster_side', headers=auth_headers_user1,
                         json={'quantity': 3})
        data = rv.get_json()

        assert data['success'] is True
        assert data['opened_boosters'] == 3
        assert data['booster_packs_side'] == 0
        assert len(data['cards']) == 9
        assert CollectionCard.query.filter_by(user_id=u1.id).count() == 9


# ═══════════════════════════════════════════════════════════════════
#  Registration starter packs
# ═══════════════════════════════════════════════════════════════════

class TestRegistrationStarterPacks:
    def test_registration_and_welcome_grant_no_economy_items(self, client, db):
        rv = client.post('/auth/register', data={
            'username': 'newplayer',
            'password': 'secret123',
            'age_confirmed': 'true',
            'terms_accepted': 'true',
            'privacy_accepted': 'true',
        })
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['success'] is True

        user = User.query.filter_by(username='newplayer').first()
        assert user is not None
        # No economy items are granted at signup.
        assert user.gold == 0
        assert user.booster_packs == 0
        assert user.booster_packs_side == 0
        assert data['user']['booster_packs'] == 0
        assert data['user']['booster_packs_side'] == 0

        # Starting the tutorial also grants nothing; all economy items remain
        # in the First Journey completion reward.
        welcome = client.post(
            '/onboarding/mark_tip',
            headers={'Authorization': f"Bearer {data['token']}"},
            json={'tip_key': 'welcome'},
        )
        assert welcome.status_code == 200
        assert welcome.get_json()['balances'] == {
            'gold': 0,
            'booster_packs': 0,
            'booster_packs_side': 0,
            'maps': 0,
        }
        db.session.refresh(user)
        assert (user.gold, user.booster_packs,
                user.booster_packs_side, user.maps) == (0, 0, 0, 0)


# ═══════════════════════════════════════════════════════════════════
#  POST /collection/convert_card
# ═══════════════════════════════════════════════════════════════════

class TestConvertCard:
    def test_same_colour_conversion_two_to_one(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        # 4 free Hearts 7 → request producing 2 Diamonds 7 (cost 4)
        _add_cards(db, u1.id, 'Hearts', '7', 7, count=4)
        rv = client.post('/collection/convert_card',
                         json={'suit': 'Hearts', 'rank': '7',
                               'target_suit': 'Diamonds', 'quantity': 2},
                         headers=auth_headers_user1)
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['success'] is True
        assert data['ratio'] == 2
        assert data['consumed'] == 4
        assert data['produced'] == 2
        # Collection state
        hearts = CollectionCard.query.filter_by(
            user_id=u1.id, suit='Hearts', rank='7').count()
        diamonds = CollectionCard.query.filter_by(
            user_id=u1.id, suit='Diamonds', rank='7').count()
        assert hearts == 0
        assert diamonds == 2

    def test_different_colour_conversion_four_to_one(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        _add_cards(db, u1.id, 'Hearts', 'K', 4, count=4)
        rv = client.post('/collection/convert_card',
                         json={'suit': 'Hearts', 'rank': 'K',
                               'target_suit': 'Spades', 'quantity': 1},
                         headers=auth_headers_user1)
        assert rv.status_code == 200
        data = rv.get_json()
        assert data['ratio'] == 4
        assert data['consumed'] == 4
        assert data['produced'] == 1
        hearts = CollectionCard.query.filter_by(
            user_id=u1.id, suit='Hearts', rank='K').count()
        spades = CollectionCard.query.filter_by(
            user_id=u1.id, suit='Spades', rank='K').count()
        assert hearts == 0
        assert spades == 1
        # Verify created spade carries the same value as source
        new_card = CollectionCard.query.filter_by(
            user_id=u1.id, suit='Spades', rank='K').first()
        assert new_card.value == 4
        assert new_card.locked is False

    def test_locked_copies_excluded(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        _add_cards(db, u1.id, 'Hearts', '8', 8, count=1)              # 1 free
        _add_cards(db, u1.id, 'Hearts', '8', 8, count=2, locked=True)  # 2 locked
        # Need 2 source for 1 same-colour target, but only 1 free available
        rv = client.post('/collection/convert_card',
                         json={'suit': 'Hearts', 'rank': '8',
                               'target_suit': 'Diamonds', 'quantity': 1},
                         headers=auth_headers_user1)
        assert rv.status_code == 400
        assert rv.get_json()['success'] is False
        # Locked rows untouched
        assert CollectionCard.query.filter_by(
            user_id=u1.id, suit='Hearts', rank='8', locked=True).count() == 2
        assert CollectionCard.query.filter_by(
            user_id=u1.id, suit='Diamonds', rank='8').count() == 0

    def test_insufficient_cards(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        _add_cards(db, u1.id, 'Hearts', '9', 9, count=1)
        rv = client.post('/collection/convert_card',
                         json={'suit': 'Hearts', 'rank': '9',
                               'target_suit': 'Diamonds', 'quantity': 1},
                         headers=auth_headers_user1)
        assert rv.status_code == 400
        assert 'Not enough' in rv.get_json()['message']

    def test_same_suit_rejected(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        _add_cards(db, u1.id, 'Hearts', '7', 7, count=4)
        rv = client.post('/collection/convert_card',
                         json={'suit': 'Hearts', 'rank': '7',
                               'target_suit': 'Hearts', 'quantity': 1},
                         headers=auth_headers_user1)
        assert rv.status_code == 400

    def test_invalid_suit_rejected(self, client, auth_headers_user1):
        rv = client.post('/collection/convert_card',
                         json={'suit': 'Bogus', 'rank': '7',
                               'target_suit': 'Diamonds', 'quantity': 1},
                         headers=auth_headers_user1)
        assert rv.status_code == 400

    def test_invalid_quantity_rejected(self, client, auth_headers_user1):
        rv = client.post('/collection/convert_card',
                         json={'suit': 'Hearts', 'rank': '7',
                               'target_suit': 'Diamonds', 'quantity': 0},
                         headers=auth_headers_user1)
        assert rv.status_code == 400

    def test_side_card_conversion(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        # Side cards work the same: rank 6 (Hearts) → 6 (Spades), diff colour 4:1
        _add_cards(db, u1.id, 'Hearts', '6', 6, count=4)
        rv = client.post('/collection/convert_card',
                         json={'suit': 'Hearts', 'rank': '6',
                               'target_suit': 'Spades', 'quantity': 1},
                         headers=auth_headers_user1)
        assert rv.status_code == 200
        assert rv.get_json()['ratio'] == 4

    def test_partial_consumption(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        # 5 free Hearts 7. Convert producing 2 Diamonds (cost 4); 1 should remain.
        _add_cards(db, u1.id, 'Hearts', '7', 7, count=5)
        rv = client.post('/collection/convert_card',
                         json={'suit': 'Hearts', 'rank': '7',
                               'target_suit': 'Diamonds', 'quantity': 2},
                         headers=auth_headers_user1)
        assert rv.status_code == 200
        remaining = CollectionCard.query.filter_by(
            user_id=u1.id, suit='Hearts', rank='7').count()
        assert remaining == 1

    def test_convert_maharaja_rejected(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        _add_cards(db, u1.id, 'Hearts', 'MK', 4, count=1)

        rv = client.post('/collection/convert_card',
                         json={'suit': 'Hearts', 'rank': 'MK',
                               'target_suit': 'Diamonds', 'quantity': 1},
                         headers=auth_headers_user1)
        assert rv.status_code == 400
        assert rv.get_json()['success'] is False
