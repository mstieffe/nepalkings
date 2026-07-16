# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Collection routes — card collection, booster packs, selling cards."""

import random
import logging
from flask import Blueprint, request, jsonify, g

from models import db, User, CollectionCard
from routes.auth import require_token
import server_settings as config
from analytics import track

collection = Blueprint('collection', __name__)
logger = logging.getLogger('nepalkings.routes.collection')

SUITS = ['Hearts', 'Diamonds', 'Clubs', 'Spades']

RANK_TO_VALUE = {
    'A': 3, 'K': 4, 'Q': 2, 'J': 1,
    '10': 10, '9': 9, '8': 8, '7': 7,
    '6': 6, '5': 5, '4': 4, '3': 3, '2': 2,
}

ALL_MAIN_RANKS = ['7', '8', '9', '10', 'J', 'Q', 'K', 'A']
ALL_SIDE_RANKS = ['2', '3', '4', '5', '6']

_RED_SUITS = {'Hearts', 'Diamonds'}
_BLACK_SUITS = {'Clubs', 'Spades'}

# Card-to-card conversion ratios.
# Same colour: spend 2 source cards to get 1 target card.
# Different colour: spend 4 source cards to get 1 target card.
CONVERT_RATIO_SAME_COLOUR = 2
CONVERT_RATIO_DIFFERENT_COLOUR = 4


def _suit_colour(suit):
    if suit in _RED_SUITS:
        return 'red'
    if suit in _BLACK_SUITS:
        return 'black'
    return None


def _convert_ratio(source_suit, target_suit):
    """Return number of source copies needed per produced target copy.

    Returns ``None`` if either suit is invalid or both suits are equal.
    """
    sc, tc = _suit_colour(source_suit), _suit_colour(target_suit)
    if sc is None or tc is None or source_suit == target_suit:
        return None
    return CONVERT_RATIO_SAME_COLOUR if sc == tc else CONVERT_RATIO_DIFFERENT_COLOUR


def _sell_price(rank, quantity=1):
    """Calculate the gold earned from selling *quantity* cards of *rank*."""
    value = RANK_TO_VALUE.get(rank, 0)
    if rank in config.KEY_CARD_RANKS:
        return value * config.CARD_SELL_KEY_MULTIPLIER * quantity
    return value * quantity


def _draw_cards(count, tier_probs, tier_ranks):
    """Draw *count* random cards using given tier probabilities and rank tables.

    Returns a list of dicts: ``[{suit, rank, value}, ...]``
    """
    tiers = list(tier_probs.keys())
    weights = [tier_probs[t] for t in tiers]
    cards = []
    for _ in range(count):
        tier = random.choices(tiers, weights=weights, k=1)[0]
        rank = random.choice(tier_ranks[tier])
        suit = random.choice(SUITS)
        cards.append({'suit': suit, 'rank': rank,
                      'value': RANK_TO_VALUE[rank], 'tier': tier})
    return cards


def _request_quantity(default=1):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = request.form or {}
    raw = data.get('quantity', default)
    if raw in (None, ''):
        raw = default
    try:
        quantity = int(raw)
    except (TypeError, ValueError):
        return None
    if quantity < 1:
        return None
    return quantity


def _add_drawn_cards(user, drawn):
    for card in drawn:
        cc = CollectionCard(
            user_id=user.id,
            suit=card['suit'],
            rank=card['rank'],
            value=card['value'],
        )
        db.session.add(cc)


# ── GET /collection/cards ───────────────────────────────────────────────────

@collection.route('/cards', methods=['GET'])
@require_token
def get_cards():
    """Return user's card collection grouped by (suit, rank)."""
    user = db.session.get(User, g.user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    all_cards = CollectionCard.query.filter_by(user_id=user.id).all()

    # Group by (suit, rank)
    grouped = {}
    for card in all_cards:
        key = (card.suit, card.rank)
        if key not in grouped:
            grouped[key] = {'suit': card.suit, 'rank': card.rank,
                            'value': card.value, 'total': 0, 'locked': 0}
        grouped[key]['total'] += 1
        if card.locked:
            grouped[key]['locked'] += 1

    cards = []
    for entry in grouped.values():
        entry['free'] = entry['total'] - entry['locked']
        cards.append(entry)

    return jsonify({
        'success': True,
        'cards': cards,
        'booster_packs': user.booster_packs,
        'booster_packs_side': user.booster_packs_side,
        'maps': int(user.maps or 0),
        'gold': user.gold,
    })


# ── POST /collection/sell_card ──────────────────────────────────────────────

@collection.route('/sell_card', methods=['POST'])
@require_token
def sell_card():
    """Sell unlocked cards from the collection for gold."""
    data = request.get_json(silent=True) or {}
    suit = data.get('suit', '').strip()
    rank = data.get('rank', '').strip()
    quantity = data.get('quantity', 1)

    if not suit or not rank:
        return jsonify({'success': False, 'message': 'Missing suit or rank'}), 400
    if not isinstance(quantity, int) or quantity < 1:
        return jsonify({'success': False, 'message': 'Quantity must be a positive integer'}), 400
    if rank not in RANK_TO_VALUE:
        return jsonify({'success': False, 'message': f'Invalid rank: {rank}'}), 400
    if suit not in SUITS:
        return jsonify({'success': False, 'message': f'Invalid suit: {suit}'}), 400

    user = db.session.get(User, g.user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    # Find unlocked cards to sell
    free_cards = CollectionCard.query.filter_by(
        user_id=user.id, suit=suit, rank=rank, locked=False
    ).limit(quantity).all()

    if len(free_cards) < quantity:
        return jsonify({
            'success': False,
            'message': f'Not enough free cards to sell (have {len(free_cards)}, need {quantity})',
        }), 400

    gold_earned = _sell_price(rank, quantity)
    for card in free_cards:
        db.session.delete(card)
    user.gold += gold_earned
    from onboarding_service import mark_step, record_gold_earned
    mark_step(user, 'sell_first_card')
    record_gold_earned(user, gold_earned)
    db.session.commit()

    return jsonify({
        'success': True,
        'gold_earned': gold_earned,
        'gold': user.gold,
    })


# ── POST /collection/buy_booster ───────────────────────────────────────────

@collection.route('/buy_booster', methods=['POST'])
@require_token
def buy_booster():
    """Buy main-card booster packs with gold."""
    data = request.get_json(silent=True) or {}
    quantity = data.get('quantity', 1)

    if not isinstance(quantity, int) or quantity < 1:
        return jsonify({'success': False, 'message': 'Quantity must be a positive integer'}), 400

    user = db.session.get(User, g.user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    cost = quantity * config.BOOSTER_PACK_PRICE
    if user.gold < cost:
        return jsonify({'success': False, 'message': 'Insufficient gold'}), 400

    user.gold -= cost
    user.booster_packs += quantity
    db.session.commit()

    return jsonify({
        'success': True,
        'booster_packs': user.booster_packs,
        'gold': user.gold,
    })


# ── POST /collection/buy_booster_side ──────────────────────────────────────

@collection.route('/buy_booster_side', methods=['POST'])
@require_token
def buy_booster_side():
    """Buy side-card booster packs with gold."""
    data = request.get_json(silent=True) or {}
    quantity = data.get('quantity', 1)

    if not isinstance(quantity, int) or quantity < 1:
        return jsonify({'success': False, 'message': 'Quantity must be a positive integer'}), 400

    user = db.session.get(User, g.user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    cost = quantity * config.BOOSTER_PACK_SIDE_PRICE
    if user.gold < cost:
        return jsonify({'success': False, 'message': 'Insufficient gold'}), 400

    user.gold -= cost
    user.booster_packs_side += quantity
    db.session.commit()

    return jsonify({
        'success': True,
        'booster_packs_side': user.booster_packs_side,
        'gold': user.gold,
    })


# ── POST /collection/open_booster ──────────────────────────────────────────

@collection.route('/open_booster', methods=['POST'])
@require_token
def open_booster():
    """Open one or more main-card booster packs, drawing random cards."""
    quantity = _request_quantity()
    if quantity is None:
        return jsonify({'success': False,
                        'message': 'Quantity must be a positive integer'}), 400

    user = db.session.get(User, g.user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    if user.booster_packs < 1:
        return jsonify({'success': False, 'message': 'No booster packs available'}), 400
    if user.booster_packs < quantity:
        return jsonify({
            'success': False,
            'message': f'Not enough booster packs available (have {user.booster_packs}, need {quantity})',
        }), 400

    user.booster_packs -= quantity
    drawn = _draw_cards(config.BOOSTER_PACK_CARDS * quantity,
                        config.BOOSTER_TIER_PROBABILITIES,
                        config.BOOSTER_TIER_RANKS)

    _add_drawn_cards(user, drawn)
    from onboarding_service import serialize_onboarding_state
    track('booster_opened', user_id=user.id, kind='main',
          quantity=quantity if quantity > 1 else None)
    db.session.commit()

    return jsonify({
        'success': True,
        'cards': drawn,
        'opened_boosters': quantity,
        'booster_packs': user.booster_packs,
        'onboarding': serialize_onboarding_state(user),
    })


# ── POST /collection/open_booster_side ─────────────────────────────────────

@collection.route('/open_booster_side', methods=['POST'])
@require_token
def open_booster_side():
    """Open one or more side-card booster packs, drawing random cards."""
    quantity = _request_quantity()
    if quantity is None:
        return jsonify({'success': False,
                        'message': 'Quantity must be a positive integer'}), 400

    user = db.session.get(User, g.user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    if user.booster_packs_side < 1:
        return jsonify({'success': False, 'message': 'No side booster packs available'}), 400
    if user.booster_packs_side < quantity:
        return jsonify({
            'success': False,
            'message': f'Not enough side booster packs available (have {user.booster_packs_side}, need {quantity})',
        }), 400

    user.booster_packs_side -= quantity
    drawn = _draw_cards(config.BOOSTER_PACK_CARDS * quantity,
                        config.BOOSTER_SIDE_TIER_PROBABILITIES,
                        config.BOOSTER_SIDE_TIER_RANKS)

    _add_drawn_cards(user, drawn)
    from onboarding_service import mark_step
    mark_step(user, 'open_first_side_booster')
    track('booster_opened', user_id=user.id, kind='side',
          quantity=quantity if quantity > 1 else None)
    db.session.commit()

    return jsonify({
        'success': True,
        'cards': drawn,
        'opened_boosters': quantity,
        'booster_packs_side': user.booster_packs_side,
    })


# ── POST /collection/convert_card ──────────────────────────────────────────

@collection.route('/convert_card', methods=['POST'])
@require_token
def convert_card():
    """Convert N copies of one (suit, rank) card into copies of another suit.

    Same rank only. Same colour conversion costs 2 source copies per target;
    different colour costs 4. Only unlocked source copies are consumed.
    """
    data = request.get_json(silent=True) or {}
    suit = data.get('suit', '').strip() if isinstance(data.get('suit'), str) else ''
    rank = data.get('rank', '').strip() if isinstance(data.get('rank'), str) else ''
    target_suit = data.get('target_suit', '').strip() if isinstance(data.get('target_suit'), str) else ''
    quantity = data.get('quantity', 1)

    if not suit or not rank or not target_suit:
        return jsonify({'success': False, 'message': 'Missing suit, rank, or target_suit'}), 400
    if suit not in SUITS:
        return jsonify({'success': False, 'message': f'Invalid suit: {suit}'}), 400
    if target_suit not in SUITS:
        return jsonify({'success': False, 'message': f'Invalid target suit: {target_suit}'}), 400
    if suit == target_suit:
        return jsonify({'success': False, 'message': 'Source and target suits must differ'}), 400
    if rank not in RANK_TO_VALUE:
        return jsonify({'success': False, 'message': f'Invalid rank: {rank}'}), 400
    if not isinstance(quantity, int) or quantity < 1:
        return jsonify({'success': False, 'message': 'Quantity must be a positive integer'}), 400

    ratio = _convert_ratio(suit, target_suit)
    if ratio is None:
        # Defensive — earlier checks should have handled all invalid cases.
        return jsonify({'success': False, 'message': 'Invalid suit pair'}), 400
    needed = ratio * quantity

    user = db.session.get(User, g.user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    free_cards = CollectionCard.query.filter_by(
        user_id=user.id, suit=suit, rank=rank, locked=False
    ).limit(needed).all()

    if len(free_cards) < needed:
        return jsonify({
            'success': False,
            'message': (f'Not enough free cards to convert '
                        f'(have {len(free_cards)}, need {needed})'),
        }), 400

    value = RANK_TO_VALUE[rank]
    for card in free_cards:
        db.session.delete(card)
    for _ in range(quantity):
        db.session.add(CollectionCard(
            user_id=user.id, suit=target_suit, rank=rank, value=value))
    from onboarding_service import mark_step
    mark_step(user, 'trade_first_card')
    db.session.commit()

    return jsonify({
        'success': True,
        'consumed': needed,
        'produced': quantity,
        'ratio': ratio,
        'gold': user.gold,
    })


# ── POST /collection/craft_maharaja ─────────────────────────────────────────

MAHARAJA_RANK = 'MK'
MAHARAJA_VALUE = 4
MAHARAJA_CRAFT_RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']


@collection.route('/craft_maharaja', methods=['POST'])
@require_token
def craft_maharaja():
    """Craft a Maharaja card for one suit from one free copy of every rank.

    Consumes exactly one unlocked copy of each of the 13 ranks (2..A) in the
    given suit and produces one 'MK' card. All-or-nothing: if any rank is
    missing a free copy, nothing is consumed.
    """
    data = request.get_json(silent=True) or {}
    suit = data.get('suit', '').strip() if isinstance(data.get('suit'), str) else ''

    if not suit:
        return jsonify({'success': False, 'message': 'Missing suit'}), 400
    if suit not in SUITS:
        return jsonify({'success': False, 'message': f'Invalid suit: {suit}'}), 400

    user = db.session.get(User, g.user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    # Select candidate IDs first, then claim all thirteen with one conditional
    # DELETE.  The row-count check makes concurrent craft/build requests
    # all-or-nothing: a card locked or consumed after this read causes a
    # rollback instead of producing an unearned Maharaja.
    to_consume_ids = []
    missing = []
    for rank in MAHARAJA_CRAFT_RANKS:
        card_id = db.session.query(CollectionCard.id).filter_by(
            user_id=user.id, suit=suit, rank=rank, locked=False
        ).limit(1).scalar()
        if card_id is None:
            missing.append(rank)
        else:
            to_consume_ids.append(card_id)

    if missing:
        return jsonify({
            'success': False,
            'message': f'Missing free {suit} cards for rank(s): {", ".join(missing)}',
        }), 400

    deleted = CollectionCard.query.filter(
        CollectionCard.id.in_(to_consume_ids),
        CollectionCard.user_id == user.id,
        CollectionCard.suit == suit,
        CollectionCard.locked.is_(False),
    ).delete(synchronize_session=False)
    if deleted != len(MAHARAJA_CRAFT_RANKS):
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': 'Cards changed while crafting. Refresh and try again.',
        }), 409

    db.session.add(CollectionCard(
        user_id=user.id, suit=suit, rank=MAHARAJA_RANK, value=MAHARAJA_VALUE))
    track('maharaja_crafted', user_id=user.id, suit=suit)
    db.session.commit()

    return jsonify({
        'success': True,
        'card': {'suit': suit, 'rank': MAHARAJA_RANK, 'value': MAHARAJA_VALUE},
        'consumed': len(MAHARAJA_CRAFT_RANKS),
    })
