# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Selection, serialization, and persistence helpers for conquer loot."""

import random

from game_service.card_values import AI_DEFENCE_RANK_VALUES
from models import CollectionCard, KingdomLootEvent, db
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


def _config_figure_key_card_ids(cfg):
    """Return collection card IDs used as key cards in a land config's figures."""
    if not cfg:
        return []
    key_card_ids = []
    for fig in cfg.figures:
        for cid, role in zip(fig.card_ids or [], fig.card_roles or []):
            if str(role or '').lower() == 'key':
                key_card_ids.append(cid)
    return key_card_ids


def _template_figure_key_cards(template):
    """Return AI-template figure cards explicitly marked as key cards."""
    key_cards = []
    for fig in (template or {}).get('figures', []):
        cards = list(fig.get('cards') or [])
        roles = list(fig.get('card_roles') or [])
        for index, card in enumerate(cards):
            if not isinstance(card, dict):
                continue
            role = card.get('role')
            if role is None and index < len(roles):
                role = roles[index]
            if str(role or '').lower() == 'key':
                key_cards.append(card)
    return key_cards


def _conquer_loot_base_quota(land_tier):
    """Return ``(key_cards, number_cards)`` base loot quota for a land tier."""
    try:
        tier = max(1, int(land_tier or 1))
    except (TypeError, ValueError):
        tier = 1
    # The rule is intentionally simple and scales linearly: tier 1 loots up to
    # 1 key + 1 number card, tier 2 up to 2 + 2, ..., tier 6 up to 6 + 6.
    return tier, tier


def _random_pick_without_replacement(pool, count, rng):
    chosen = []
    remaining = list(pool or [])
    count = min(max(0, int(count or 0)), len(remaining))
    for _ in range(count):
        picked = rng.choice(remaining)
        chosen.append(picked)
        remaining.remove(picked)
    return chosen


def _select_conquer_loot_cards(cards, land_tier, *, extra_chance=0.0, rng=None):
    """Select loot cards from eligible snapshot rows.

    Base selection takes up to the tier quota from key and number buckets
    (classification is rank-based, see :func:`_loot_card_bucket`).
    ``extra_chance`` then rolls independently for every remaining card; this is
    used only by the defending kingdom's loot skill.
    """
    rng = rng or random
    key_quota, number_quota = _conquer_loot_base_quota(land_tier)
    cards = list(cards or [])
    key_cards = [c for c in cards if c.get('bucket') == 'key']
    number_cards = [c for c in cards if c.get('bucket') != 'key']

    selected = []
    selected.extend(_random_pick_without_replacement(key_cards, key_quota, rng))
    selected.extend(_random_pick_without_replacement(number_cards, number_quota, rng))
    selected_ids = {id(c) for c in selected}

    try:
        chance = max(0.0, min(1.0, float(extra_chance or 0.0)))
    except (TypeError, ValueError):
        chance = 0.0
    if chance > 0:
        for card in cards:
            if id(card) in selected_ids:
                continue
            if rng.random() < chance:
                selected.append(card)
                selected_ids.add(id(card))
    return selected


def _loot_cards_public(cards, include_id=False):
    """Strip internal fields from loot-card rows for API/UI/event storage."""
    out = []
    for card in cards or []:
        if not isinstance(card, dict):
            continue
        row = {
            'suit': card.get('suit'),
            'rank': card.get('rank'),
            'value': int(card.get('value') or 0),
            'role': card.get('role'),
            'source': card.get('source'),
            'bucket': card.get('bucket'),
        }
        if include_id and card.get('id'):
            row['id'] = card.get('id')
        out.append(row)
    return out


def _create_kingdom_loot_events(*, attack_log_id, land_id, gained_user_id,
                                lost_user_id=None, gained_kingdom_id=None,
                                lost_kingdom_id=None, source=None,
                                cards=None):
    """Create pending gain/loss inbox rows for selected loot cards."""
    public_cards = _loot_cards_public(cards, include_id=False)
    if not public_cards:
        return
    if gained_user_id:
        db.session.add(KingdomLootEvent(
            user_id=gained_user_id,
            kingdom_id=gained_kingdom_id,
            land_id=land_id,
            attack_log_id=attack_log_id,
            direction='gained',
            source=source,
            counterparty_user_id=lost_user_id,
            cards=public_cards,
            collected=False,
            seen=False,
        ))
    if lost_user_id:
        db.session.add(KingdomLootEvent(
            user_id=lost_user_id,
            kingdom_id=lost_kingdom_id,
            land_id=land_id,
            attack_log_id=attack_log_id,
            direction='lost',
            source=source,
            counterparty_user_id=gained_user_id,
            cards=public_cards,
            collected=True,
            seen=False,
        ))


def _delete_looted_collection_cards(cards):
    ids = [c.get('id') for c in cards or [] if c.get('id')]
    if ids:
        CollectionCard.query.filter(
            CollectionCard.id.in_(ids)
        ).delete(synchronize_session='fetch')


# Keep the historical route-level repr and pickle lookup while routes.games
# re-exports this canonical implementation.
_config_figure_key_card_ids.__module__ = 'routes.games'
_conquer_loot_base_quota.__module__ = 'routes.games'
_create_kingdom_loot_events.__module__ = 'routes.games'
_delete_looted_collection_cards.__module__ = 'routes.games'
_loot_card_bucket.__module__ = 'routes.games'
_loot_cards_public.__module__ = 'routes.games'
_normalise_loot_card.__module__ = 'routes.games'
_random_pick_without_replacement.__module__ = 'routes.games'
_select_conquer_loot_cards.__module__ = 'routes.games'
_snapshot_config_loot_cards.__module__ = 'routes.games'
_snapshot_template_loot_cards.__module__ = 'routes.games'
_template_figure_key_cards.__module__ = 'routes.games'
