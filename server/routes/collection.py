# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Collection routes — card collection, booster packs, selling cards."""

import random
import logging
from flask import Blueprint, request, jsonify, g

from models import db, User, CollectionCard
from routes.auth import require_token
import server_settings as config

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
    """Open one main-card booster pack, drawing random cards."""
    user = db.session.get(User, g.user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    if user.booster_packs < 1:
        return jsonify({'success': False, 'message': 'No booster packs available'}), 400

    user.booster_packs -= 1
    drawn = _draw_cards(config.BOOSTER_PACK_CARDS,
                        config.BOOSTER_TIER_PROBABILITIES,
                        config.BOOSTER_TIER_RANKS)

    for card in drawn:
        cc = CollectionCard(
            user_id=user.id,
            suit=card['suit'],
            rank=card['rank'],
            value=card['value'],
        )
        db.session.add(cc)
    db.session.commit()

    return jsonify({
        'success': True,
        'cards': drawn,
        'booster_packs': user.booster_packs,
    })


# ── POST /collection/open_booster_side ─────────────────────────────────────

@collection.route('/open_booster_side', methods=['POST'])
@require_token
def open_booster_side():
    """Open one side-card booster pack, drawing random cards."""
    user = db.session.get(User, g.user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    if user.booster_packs_side < 1:
        return jsonify({'success': False, 'message': 'No side booster packs available'}), 400

    user.booster_packs_side -= 1
    drawn = _draw_cards(config.BOOSTER_PACK_CARDS,
                        config.BOOSTER_SIDE_TIER_PROBABILITIES,
                        config.BOOSTER_SIDE_TIER_RANKS)

    for card in drawn:
        cc = CollectionCard(
            user_id=user.id,
            suit=card['suit'],
            rank=card['rank'],
            value=card['value'],
        )
        db.session.add(cc)
    db.session.commit()

    return jsonify({
        'success': True,
        'cards': drawn,
        'booster_packs_side': user.booster_packs_side,
    })
