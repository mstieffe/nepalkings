# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Read-only, grouped collection snapshots shared by configuration routes."""

from sqlalchemy import case

from models import CollectionCard, db


def serialize_collection_snapshot(user):
    """Return the compact collection payload used by setup screens.

    Grouping in SQL avoids loading every physical card row merely to calculate
    the total/free/locked counts.  The result intentionally matches
    ``GET /collection/cards`` so clients can consume either source.
    """
    locked_count = db.func.sum(
        case((CollectionCard.locked.is_(True), 1), else_=0)
    )
    rows = (
        db.session.query(
            CollectionCard.suit,
            CollectionCard.rank,
            CollectionCard.value,
            db.func.count(CollectionCard.id),
            locked_count,
        )
        .filter(CollectionCard.user_id == user.id)
        .group_by(
            CollectionCard.suit,
            CollectionCard.rank,
            CollectionCard.value,
        )
        .order_by(CollectionCard.suit, CollectionCard.rank)
        .all()
    )

    cards = []
    for suit, rank, value, total, locked in rows:
        total = int(total or 0)
        locked = int(locked or 0)
        cards.append({
            'suit': suit,
            'rank': rank,
            'value': value,
            'total': total,
            'locked': locked,
            'free': total - locked,
        })

    return {
        'success': True,
        'cards': cards,
        'booster_packs': int(user.booster_packs or 0),
        'booster_packs_side': int(user.booster_packs_side or 0),
        'maps': int(user.maps or 0),
        'gold': int(user.gold or 0),
    }
