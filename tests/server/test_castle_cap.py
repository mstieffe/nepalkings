# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for the castle-figure cap per land tier.

A land with tier N permits at most N castle figures (kings/maharajas) in
either a conquer or defence config. The cap is enforced by the build
routes in `server/routes/kingdom.py` and the in-battle build path in
`server/routes/figures.py`.
"""

import pytest
from models import db as _db, User, Land, CollectionCard


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


def _add_card(db, user_id, suit='Clubs', rank='K', value=4):
    card = CollectionCard(user_id=user_id, suit=suit, rank=rank, value=value)
    db.session.add(card)
    db.session.commit()
    return card


def _build_castle(client, headers, route, land_id, card_id):
    """Attempt to build one castle figure (single king card)."""
    return client.post(route, headers=headers, json={
        'land_id': land_id,
        'family_name': 'Himalaya King',
        'name': 'Himalaya King',
        'suit': 'Clubs',
        'color': 'defensive',
        'field': 'castle',
        'card_ids': [card_id],
        'card_roles': ['key'],
        'produces': {'villager_black': 2},
        'requires': {},
    })


# ═══════════════════════════════════════════════════════════════════
#  Conquer build_figure
# ═══════════════════════════════════════════════════════════════════

class TestConquerCastleCap:

    def test_tier1_blocks_second_castle(self, client, db, two_users, auth_headers_user1):
        u1, u2 = two_users
        land = _add_land(db, owner_id=u2.id, tier=1)
        c1 = _add_card(db, u1.id, 'Clubs', 'K', 4)
        c2 = _add_card(db, u1.id, 'Spades', 'K', 4)

        rv1 = _build_castle(client, auth_headers_user1,
                            '/kingdom/conquer/build_figure', land.id, c1.id)
        assert rv1.status_code == 200

        rv2 = _build_castle(client, auth_headers_user1,
                            '/kingdom/conquer/build_figure', land.id, c2.id)
        assert rv2.status_code == 400
        data = rv2.get_json()
        assert data.get('error_code') == 'castle_cap_reached'

    def test_tier3_allows_three_castles_blocks_fourth(self, client, db,
                                                     two_users, auth_headers_user1):
        u1, u2 = two_users
        land = _add_land(db, owner_id=u2.id, tier=3)
        cards = [
            _add_card(db, u1.id, 'Clubs', 'K', 4),
            _add_card(db, u1.id, 'Spades', 'K', 4),
            _add_card(db, u1.id, 'Hearts', 'K', 4),
            _add_card(db, u1.id, 'Diamonds', 'K', 4),
        ]
        for i in range(3):
            rv = _build_castle(client, auth_headers_user1,
                               '/kingdom/conquer/build_figure',
                               land.id, cards[i].id)
            assert rv.status_code == 200, f'castle {i+1} should build'

        rv4 = _build_castle(client, auth_headers_user1,
                            '/kingdom/conquer/build_figure',
                            land.id, cards[3].id)
        assert rv4.status_code == 400
        assert rv4.get_json().get('error_code') == 'castle_cap_reached'


# ═══════════════════════════════════════════════════════════════════
#  Defence build_figure
# ═══════════════════════════════════════════════════════════════════

class TestDefenceCastleCap:

    def test_tier1_blocks_second_castle(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        land = _add_land(db, owner_id=u1.id, tier=1)
        c1 = _add_card(db, u1.id, 'Clubs', 'K', 4)
        c2 = _add_card(db, u1.id, 'Spades', 'K', 4)

        rv1 = _build_castle(client, auth_headers_user1,
                            '/kingdom/defence/build_figure', land.id, c1.id)
        assert rv1.status_code == 200

        rv2 = _build_castle(client, auth_headers_user1,
                            '/kingdom/defence/build_figure', land.id, c2.id)
        assert rv2.status_code == 400
        assert rv2.get_json().get('error_code') == 'castle_cap_reached'

    def test_tier2_allows_two_castles(self, client, db, two_users, auth_headers_user1):
        u1, _ = two_users
        land = _add_land(db, owner_id=u1.id, tier=2)
        c1 = _add_card(db, u1.id, 'Clubs', 'K', 4)
        c2 = _add_card(db, u1.id, 'Spades', 'K', 4)
        c3 = _add_card(db, u1.id, 'Hearts', 'K', 4)

        for c in (c1, c2):
            rv = _build_castle(client, auth_headers_user1,
                               '/kingdom/defence/build_figure', land.id, c.id)
            assert rv.status_code == 200

        rv3 = _build_castle(client, auth_headers_user1,
                            '/kingdom/defence/build_figure', land.id, c3.id)
        assert rv3.status_code == 400
        assert rv3.get_json().get('error_code') == 'castle_cap_reached'
