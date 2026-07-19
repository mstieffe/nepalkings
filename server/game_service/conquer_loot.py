# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Selection, serialization, and persistence helpers for conquer loot."""

from game_service.card_values import AI_DEFENCE_RANK_VALUES
from models import CollectionCard, db
import server_settings as settings


def _loot_card_bucket(rank):
    """Return the loot bucket ('key' or 'number') for a card rank.

    Buckets are rank-only: every card belongs to exactly one bucket.  Unknown
    ranks default to ``'number'`` defensively.
    """
    r = str(rank or '').strip()
    if r in settings.LOOT_KEY_RANKS:
        return 'key'
    if r in settings.LOOT_NUMBER_RANKS:
        return 'number'
    return 'number'


def _normalise_loot_card(card, *, source, role=None, card_id=None):
    """Return a stable loot-card dict from a CollectionCard/template card."""
    if not card:
        return None
    if isinstance(card, dict):
        suit = card.get('suit')
        rank = card.get('rank')
        value = card.get('value')
        card_role = role if role is not None else card.get('role')
        source_card_id = card_id if card_id is not None else card.get('id')
    else:
        suit = getattr(card, 'suit', None)
        rank = getattr(card, 'rank', None)
        value = getattr(card, 'value', None)
        card_role = role
        source_card_id = card_id if card_id is not None else getattr(card, 'id', None)
    if not suit or not rank:
        return None
    if value is None:
        value = AI_DEFENCE_RANK_VALUES.get(rank, 0)
    return {
        'id': source_card_id,
        'suit': suit,
        'rank': rank,
        'value': int(value or 0),
        'role': str(getattr(card_role, 'value', card_role) or source or 'card'),
        'source': source,
        'bucket': _loot_card_bucket(rank),
    }


def _snapshot_config_loot_cards(cfg):
    """Snapshot every persistent card in a conquer/defence config for loot risk.

    Figure key cards are in the ``key`` bucket. Every other committed card —
    figure number/upgrade cards, battle moves, modifiers, and spells — is in
    the ``support`` bucket.  The snapshot includes collection-card IDs so the
    loser can lose the exact physical copies.
    """
    if not cfg:
        return []
    rows = []
    seen = set()

    def add_card_id(cid, source, role):
        if not cid or cid in seen:
            return
        cc = db.session.get(CollectionCard, cid)
        if not cc:
            return
        data = _normalise_loot_card(cc, source=source, role=role, card_id=cid)
        if data:
            rows.append(data)
            seen.add(cid)

    for fig in cfg.figures:
        roles = list(fig.card_roles or [])
        for index, cid in enumerate(fig.card_ids or []):
            role = roles[index] if index < len(roles) else 'number'
            add_card_id(cid, 'figure', role)
    for move in cfg.battle_moves:
        add_card_id(move.card_id, 'battle_move', 'battle_move')
    for source, ids in (
        ('modifier', cfg.modifier_card_ids),
        ('spell', cfg.spell_card_ids),
        ('prelude_spell', cfg.prelude_spell_card_ids),
        ('counter_spell', cfg.counter_spell_card_ids),
    ):
        for cid in ids or []:
            add_card_id(cid, source, source)
    return rows


def _snapshot_template_loot_cards(template):
    """Snapshot every AI-template card that can become conquer loot."""
    rows = []
    for fig in (template or {}).get('figures', []):
        cards = list(fig.get('cards') or [])
        roles = list(fig.get('card_roles') or [])
        for index, card in enumerate(cards):
            if not isinstance(card, dict):
                continue
            role = card.get('role')
            if role is None and index < len(roles):
                role = roles[index]
            data = _normalise_loot_card(card, source='figure', role=role)
            if data:
                rows.append(data)
    for move in (template or {}).get('battle_moves', []) or []:
        data = _normalise_loot_card(
            move,
            source='battle_move',
            role='battle_move',
        )
        if data:
            rows.append(data)
    return rows


def _delete_looted_collection_cards(cards):
    ids = [c.get('id') for c in cards or [] if c.get('id')]
    if ids:
        CollectionCard.query.filter(
            CollectionCard.id.in_(ids)
        ).delete(synchronize_session='fetch')


# Keep the historical route-level repr and pickle lookup while routes.games
# re-exports this canonical implementation.
_delete_looted_collection_cards.__module__ = 'routes.games'
_loot_card_bucket.__module__ = 'routes.games'
_normalise_loot_card.__module__ = 'routes.games'
_snapshot_config_loot_cards.__module__ = 'routes.games'
_snapshot_template_loot_cards.__module__ = 'routes.games'
