# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Kingdom routes — gold production, land management."""

import math
import logging
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, g

from models import (db, User, Land, LandAttackLog, CollectionCard,
                    LandConfig, LandConfigFigure, LandConfigBattleMove,
                    Game, Player, Figure, BattleMove, CardToFigure, ActiveSpell,
                    MainCard, SideCard, Suit, MainRank, CardRole)
from routes.auth import require_token
from game_service.deck_manager import DeckManager
import server_settings as config

kingdom = Blueprint('kingdom', __name__)
logger = logging.getLogger('nepalkings.routes.kingdom')


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── POST /kingdom/collect_gold ──────────────────────────────────────────────

@kingdom.route('/collect_gold', methods=['POST'])
@require_token
def collect_gold():
    """Collect accumulated gold from all owned lands.

    Gold = floor(total_gold_rate × elapsed_hours).
    Elapsed is capped at GOLD_PRODUCTION_MAX_ACCUMULATION_HOURS.
    """
    user = db.session.get(User, g.user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    now = _utcnow()

    # Sum gold_rate from all owned lands
    lands = Land.query.filter_by(owner_user_id=user.id).all()
    total_rate = sum(land.gold_rate for land in lands)

    if total_rate <= 0 or not lands:
        return jsonify({
            'gold_earned': 0,
            'total_gold': user.gold,
            'total_production_rate': 0.0,
            'lands_owned': 0,
        })

    # Elapsed time since last collection (or account creation)
    last = user.last_gold_collection
    if last is None:
        # First collection ever — no accumulation yet
        user.last_gold_collection = now
        db.session.commit()
        return jsonify({
            'gold_earned': 0,
            'total_gold': user.gold,
            'total_production_rate': total_rate,
            'lands_owned': len(lands),
        })

    elapsed_seconds = (now - last).total_seconds()
    max_seconds = config.GOLD_PRODUCTION_MAX_ACCUMULATION_HOURS * 3600
    elapsed_seconds = min(elapsed_seconds, max_seconds)
    elapsed_hours = elapsed_seconds / 3600.0

    earned = math.floor(total_rate * elapsed_hours)

    if earned > 0:
        user.gold += earned
        user.last_gold_collection = now
        db.session.commit()
    else:
        # Update timestamp even if 0 earned to prevent drift
        user.last_gold_collection = now
        db.session.commit()

    return jsonify({
        'gold_earned': earned,
        'total_gold': user.gold,
        'total_production_rate': total_rate,
        'lands_owned': len(lands),
    })


# ── GET /kingdom/rankings ──────────────────────────────────────────────────

@kingdom.route('/rankings', methods=['GET'])
def get_kingdom_rankings():
    """Return kingdom ranking data for all users with owned lands.

    Returns list sorted by lands_owned descending, then total_gold_rate descending.
    """
    try:
        from sqlalchemy import func, case, or_

        # Subquery: per-user land stats
        land_stats = (
            db.session.query(
                Land.owner_user_id.label('user_id'),
                func.count(Land.id).label('lands_owned'),
                func.coalesce(func.sum(Land.gold_rate), 0.0).label('total_gold_rate'),
            )
            .filter(Land.owner_user_id.isnot(None))
            .group_by(Land.owner_user_id)
            .subquery()
        )

        # Subquery: conquer attempts (user was attacker)
        conquer_attempts = (
            db.session.query(
                LandAttackLog.attacker_user_id.label('user_id'),
                func.count(LandAttackLog.id).label('conquer_attempts'),
                func.sum(
                    case(
                        (LandAttackLog.result == 'attacker_won', 1),
                        else_=0,
                    )
                ).label('conquer_wins'),
            )
            .group_by(LandAttackLog.attacker_user_id)
            .subquery()
        )

        # Subquery: defence wins (user was defender and won)
        defence_stats = (
            db.session.query(
                LandAttackLog.defender_user_id.label('user_id'),
                func.sum(
                    case(
                        (LandAttackLog.result == 'defender_won', 1),
                        else_=0,
                    )
                ).label('defence_wins'),
            )
            .filter(LandAttackLog.defender_user_id.isnot(None))
            .group_by(LandAttackLog.defender_user_id)
            .subquery()
        )

        # Get all users that have land or attack log entries
        # Use LEFT OUTER JOINs to include users with partial data
        rows = (
            db.session.query(
                User.username,
                func.coalesce(land_stats.c.lands_owned, 0).label('lands_owned'),
                func.coalesce(land_stats.c.total_gold_rate, 0.0).label('total_gold_rate'),
                func.coalesce(conquer_attempts.c.conquer_attempts, 0).label('conquer_attempts'),
                func.coalesce(conquer_attempts.c.conquer_wins, 0).label('conquer_wins'),
                func.coalesce(defence_stats.c.defence_wins, 0).label('defence_wins'),
            )
            .outerjoin(land_stats, User.id == land_stats.c.user_id)
            .outerjoin(conquer_attempts, User.id == conquer_attempts.c.user_id)
            .outerjoin(defence_stats, User.id == defence_stats.c.user_id)
            .filter(
                or_(
                    land_stats.c.lands_owned > 0,
                    conquer_attempts.c.conquer_attempts > 0,
                    defence_stats.c.defence_wins > 0,
                )
            )
            .order_by(
                func.coalesce(land_stats.c.lands_owned, 0).desc(),
                func.coalesce(land_stats.c.total_gold_rate, 0.0).desc(),
            )
            .all()
        )

        rankings = []
        for row in rows:
            rankings.append({
                'username': row.username,
                'lands_owned': int(row.lands_owned),
                'total_gold_rate': round(float(row.total_gold_rate), 1),
                'conquer_attempts': int(row.conquer_attempts),
                'conquer_wins': int(row.conquer_wins),
                'defence_wins': int(row.defence_wins),
            })

        return jsonify({'success': True, 'rankings': rankings})
    except Exception as e:
        db.session.rollback()
        logger.error(f'Kingdom rankings failed: {e}')
        return jsonify({'success': False, 'message': 'Failed to fetch kingdom rankings'}), 500


# ── GET /kingdom/map ────────────────────────────────────────────────────────

@kingdom.route('/map', methods=['GET'])
@require_token
def get_kingdom_map():
    """Return all lands with ownership info for the hex map.

    Response includes per-land data (tier, gold rate, suit bonus, owner)
    and aggregate stats for the requesting user.
    """
    from kingdom_service import check_defence_incomplete

    user = db.session.get(User, g.user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    lands = Land.query.order_by(Land.row, Land.col).all()

    my_total_gold_rate = 0.0
    my_lands_count = 0
    lands_data = []

    for land in lands:
        is_mine = (land.owner_user_id == user.id)
        if is_mine:
            my_total_gold_rate += land.gold_rate
            my_lands_count += 1

        land_dict = land.serialize()
        land_dict['is_mine'] = is_mine
        if is_mine:
            land_dict['defence_incomplete'] = check_defence_incomplete(
                land.id, user.id)
        lands_data.append(land_dict)

    # Conquer cooldown
    cooldown_remaining = 0
    if user.last_conquer_at:
        elapsed = (_utcnow() - user.last_conquer_at).total_seconds()
        remaining = config.CONQUER_COOLDOWN_SECONDS - elapsed
        cooldown_remaining = max(0, int(remaining))

    return jsonify({
        'lands': lands_data,
        'my_total_gold_rate': round(my_total_gold_rate, 1),
        'my_lands_count': my_lands_count,
        'conquer_cooldown_remaining': cooldown_remaining,
    })


# ── Conquer Config Helpers ───────────────────────────────────────────────────

# Card requirements for each modifier/spell: (rank, count, color_constraint)
# color_constraint: None = any same-color pair, 'red' = Hearts/Diamonds, 'black' = Clubs/Spades
_RED_SUITS = ('Hearts', 'Diamonds')
_BLACK_SUITS = ('Clubs', 'Spades')

_MODIFIER_CARD_REQS = {
    'Blitzkrieg':  ('Q', 2, None),
    'Peasant War': ('J', 2, None),
    'Civil War':   ('5', 2, None),
}

_SPELL_CARD_REQS = {
    'health_boost': ('3', 2, 'red'),
    'poison':       ('3', 2, 'black'),
}

# ── Prelude / Counter spell system ──────────────────────────────────────────
_SPELL_CARD_COST = {
    'Draw 2 MainCards': ('8', 1, None),
    'Fill 10':          ('10', 1, None),
    'Dump Cards':       ('7', 4, None),
    'Forced Deal':      ('4', 2, None),
    'Poison':           ('3', 2, 'black'),
    'Health Boost':     ('3', 2, 'red'),
    'All Seeing Eye':   ('9', 2, None),
    'Explosion':        ('6', 4, None),
    'Peasant War':      ('J', 2, None),
    'Civil War':        ('5', 2, None),
    'Blitzkrieg':       ('Q', 2, None),
}

_CONQUER_PRELUDE_SPELLS = frozenset({
    'Draw 2 MainCards', 'Fill 10', 'Dump Cards', 'Forced Deal',
    'Poison', 'Health Boost', 'All Seeing Eye', 'Explosion',
    'Peasant War', 'Civil War', 'Blitzkrieg',
})

_DEFENCE_PRELUDE_SPELLS = frozenset({
    'Dump Cards', 'Forced Deal', 'Poison', 'Health Boost',
    'Explosion', 'Peasant War', 'Civil War',
})

_DEFENCE_COUNTER_SPELLS = frozenset({
    'Dump Cards', 'Forced Deal', 'Poison', 'Health Boost', 'Explosion',
})

# Spells that must also be recorded in game.battle_modifier for existing
# game logic (advance restrictions, turn updates, ceasefire, etc.)
_BATTLE_MODIFIER_SPELLS = frozenset({'Peasant War', 'Civil War', 'Blitzkrieg'})

# Spell type classification used when creating ActiveSpell records at game
# creation time.  Matches the family types in spell_configs.
_SPELL_TYPE_MAP = {
    'Draw 2 MainCards': 'greed',
    'Fill 10':          'greed',
    'Dump Cards':       'greed',
    'Forced Deal':      'greed',
    'Poison':           'enchantment',
    'Health Boost':     'enchantment',
    'All Seeing Eye':   'enchantment',
    'Explosion':        'enchantment',
    'Peasant War':      'tactics',
    'Civil War':        'tactics',
    'Blitzkrieg':       'tactics',
}


def _find_free_cards(user_id, rank, count, color_constraint=None):
    """Find `count` free (unlocked) collection cards of `rank` with the same suit color.

    Returns a list of card IDs if found, or None if insufficient cards.
    """
    query = CollectionCard.query.filter(
        CollectionCard.user_id == user_id,
        CollectionCard.rank == rank,
        CollectionCard.locked == False,
    )
    if color_constraint == 'red':
        query = query.filter(CollectionCard.suit.in_(_RED_SUITS))
    elif color_constraint == 'black':
        query = query.filter(CollectionCard.suit.in_(_BLACK_SUITS))

    cards = query.all()
    if not cards:
        return None

    # Group by color and find a color group with enough cards
    red = [c for c in cards if c.suit in _RED_SUITS]
    black = [c for c in cards if c.suit in _BLACK_SUITS]

    if color_constraint == 'red':
        pool = red
    elif color_constraint == 'black':
        pool = black
    else:
        # Pick whichever color has enough
        pool = red if len(red) >= count else black

    if len(pool) < count:
        return None
    return [c.id for c in pool[:count]]


def _serialize_config_with_deficit(cfg):
    """Serialize a LandConfig and annotate each figure with has_deficit + card details."""
    from kingdom_service import get_config_deficit_map
    data = cfg.serialize()
    deficit_map = get_config_deficit_map(cfg.id)

    # Collect all referenced collection-card IDs so we can resolve suit/rank
    all_card_ids = set()
    for fig in data['figures']:
        fig['has_deficit'] = deficit_map.get(fig['id'], False)
        all_card_ids.update(fig.get('card_ids') or [])
    all_card_ids.update(data.get('modifier_card_ids') or [])
    all_card_ids.update(data.get('spell_card_ids') or [])
    all_card_ids.update(data.get('prelude_spell_card_ids') or [])
    all_card_ids.update(data.get('counter_spell_card_ids') or [])

    # Bulk-fetch card details once
    card_map = {}
    if all_card_ids:
        cards = CollectionCard.query.filter(CollectionCard.id.in_(all_card_ids)).all()
        card_map = {c.id: {'suit': c.suit, 'rank': c.rank} for c in cards}

    # Attach per-card details to figures
    for fig in data['figures']:
        fig['card_details'] = [card_map.get(cid, {}) for cid in (fig.get('card_ids') or [])]

    # Attach modifier / spell card details at config level
    data['modifier_card_details'] = [card_map.get(cid, {}) for cid in (data.get('modifier_card_ids') or [])]
    data['spell_card_details'] = [card_map.get(cid, {}) for cid in (data.get('spell_card_ids') or [])]
    data['prelude_spell_card_details'] = [card_map.get(cid, {}) for cid in (data.get('prelude_spell_card_ids') or [])]
    data['counter_spell_card_details'] = [card_map.get(cid, {}) for cid in (data.get('counter_spell_card_ids') or [])]

    return data


def _lock_collection_cards(card_ids, lock_type, lock_ref_id):
    """Mark collection cards as locked."""
    CollectionCard.query.filter(
        CollectionCard.id.in_(card_ids)
    ).update({
        CollectionCard.locked: True,
        CollectionCard.lock_type: lock_type,
        CollectionCard.lock_ref_id: lock_ref_id,
    }, synchronize_session='fetch')


def _unlock_collection_cards(card_ids):
    """Mark collection cards as unlocked."""
    if not card_ids:
        return
    CollectionCard.query.filter(
        CollectionCard.id.in_(card_ids)
    ).update({
        CollectionCard.locked: False,
        CollectionCard.lock_type: None,
        CollectionCard.lock_ref_id: None,
    }, synchronize_session='fetch')


def _get_or_create_conquer_config(user_id, land_id):
    """Get the user's active conquer config for a land, or create one."""
    cfg = LandConfig.query.filter_by(
        user_id=user_id, config_type='conquer', land_id=land_id
    ).first()
    if not cfg:
        cfg = LandConfig(user_id=user_id, config_type='conquer', land_id=land_id)
        db.session.add(cfg)
        db.session.flush()
    return cfg


def _wipe_config(cfg):
    """Delete a config and all its children, unlocking every collection card."""
    card_ids = []
    for fig in cfg.figures:
        if fig.card_ids:
            card_ids.extend(fig.card_ids)
    for move in cfg.battle_moves:
        if move.card_id:
            card_ids.append(move.card_id)
    if cfg.modifier_card_ids:
        card_ids.extend(cfg.modifier_card_ids)
    if cfg.spell_card_ids:
        card_ids.extend(cfg.spell_card_ids)
    if cfg.prelude_spell_card_ids:
        card_ids.extend(cfg.prelude_spell_card_ids)
    if cfg.counter_spell_card_ids:
        card_ids.extend(cfg.counter_spell_card_ids)

    _unlock_collection_cards(card_ids)
    LandConfigBattleMove.query.filter_by(config_id=cfg.id).delete()
    LandConfigFigure.query.filter_by(config_id=cfg.id).delete()
    db.session.delete(cfg)


# ── GET /kingdom/conquer/config ──────────────────────────────────────────────

@kingdom.route('/conquer/config', methods=['GET'])
@require_token
def get_conquer_config():
    """Return the user's conquer configuration for a given land.

    Query params: land_id (required).
    Creates a new empty config if none exists.
    """
    land_id = request.args.get('land_id', type=int)
    if land_id is None:
        return jsonify({'error': 'land_id is required'}), 400

    land = db.session.get(Land, land_id)
    if not land:
        return jsonify({'error': 'Land not found'}), 404

    if land.owner_user_id == g.user_id:
        return jsonify({'error': 'Cannot conquer your own land'}), 400

    cfg = _get_or_create_conquer_config(g.user_id, land_id)
    db.session.commit()

    return jsonify({
        'success': True,
        'config': _serialize_config_with_deficit(cfg),
        'land': land.serialize(),
    })


# ── POST /kingdom/conquer/reset_config ───────────────────────────────────────

@kingdom.route('/conquer/reset_config', methods=['POST'])
@require_token
def conquer_reset_config():
    """Wipe the user's conquer config for a land, unlocking all cards."""
    land_id = (request.json or {}).get('land_id')
    if land_id is None:
        return jsonify({'error': 'land_id is required'}), 400

    cfg = LandConfig.query.filter_by(
        user_id=g.user_id, config_type='conquer', land_id=land_id
    ).first()
    if cfg:
        _wipe_config(cfg)
        db.session.commit()

    return jsonify({'success': True})


# ── Helper: resolve collection cards by suit+rank ────────────────────────────

def _resolve_cards_by_specs(user_id, card_specs):
    """Resolve card_specs ([{suit, rank}, ...]) to actual CollectionCard rows.

    Returns (card_ids, error_response).  If successful, error_response is None.
    Each spec consumes one distinct free (unlocked) card of that suit+rank.
    """
    card_ids = []
    # Group specs to handle duplicates efficiently
    from collections import Counter
    needed = Counter((s['suit'], s['rank']) for s in card_specs)

    for (suit, rank), count in needed.items():
        free_cards = CollectionCard.query.filter_by(
            user_id=user_id, suit=suit, rank=rank, locked=False
        ).limit(count).all()
        if len(free_cards) < count:
            msg = f'Not enough free {suit} {rank} cards (need {count}, have {len(free_cards)})'
            return None, jsonify({'success': False, 'message': msg}), 400
        card_ids.extend(c.id for c in free_cards)

    return card_ids, None


# ── POST /kingdom/conquer/build_figure ───────────────────────────────────────

@kingdom.route('/conquer/build_figure', methods=['POST'])
@require_token
def conquer_build_figure():
    """Build a figure for a conquer config using collection cards.

    Expects JSON: {
        land_id, family_name, name, suit, color, field,
        card_ids: [int, ...], card_roles: [str, ...],
        produces: {}, requires: {}, description: str,
        upgrade_family_name: str|null,
        checkmate: bool, cannot_be_blocked: bool, rest_after_attack: bool
    }
    """
    data = request.json
    land_id = data.get('land_id')
    family_name = data.get('family_name')
    name = data.get('name', family_name)      # default to family_name
    suit = data.get('suit')
    color = data.get('color', suit)            # default to suit name
    field = data.get('field')
    card_ids = data.get('card_ids', [])
    card_specs = data.get('card_specs', [])    # [{suit, rank}, ...]
    card_roles = data.get('card_roles', [])

    if not all([land_id, family_name, suit, field]):
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400

    # Resolve card_specs to real card IDs if card_ids not provided
    if not card_ids and card_specs:
        resolved, err = _resolve_cards_by_specs(g.user_id, card_specs)
        if err:
            return err
        card_ids = resolved

    if not card_ids:
        return jsonify({'success': False, 'message': 'No cards provided'}), 400

    if card_roles and len(card_ids) != len(card_roles):
        return jsonify({'success': False, 'message': 'card_ids and card_roles length mismatch'}), 400

    land = db.session.get(Land, land_id)
    if not land:
        return jsonify({'success': False, 'message': 'Land not found'}), 404

    if land.owner_user_id == g.user_id:
        return jsonify({'success': False, 'message': 'Cannot conquer your own land'}), 400

    # Verify all cards belong to user and are unlocked
    cards = CollectionCard.query.filter(
        CollectionCard.id.in_(card_ids),
        CollectionCard.user_id == g.user_id,
    ).all()

    if len(cards) != len(card_ids):
        return jsonify({'success': False, 'message': 'Some cards not found or not owned'}), 400

    locked_cards = [c for c in cards if c.locked]
    if locked_cards:
        return jsonify({'success': False, 'message': 'Some cards are already locked'}), 400

    cfg = _get_or_create_conquer_config(g.user_id, land_id)

    figure = LandConfigFigure(
        config_id=cfg.id,
        family_name=family_name,
        name=name or family_name,
        suit=suit,
        color=color or suit,
        field=field,
        card_ids=card_ids,
        card_roles=card_roles,
        produces=data.get('produces'),
        requires=data.get('requires'),
        description=data.get('description', ''),
        upgrade_family_name=data.get('upgrade_family_name'),
        checkmate=data.get('checkmate', False),
        cannot_be_blocked=data.get('cannot_be_blocked', False),
        rest_after_attack=data.get('rest_after_attack', False),
    )
    db.session.add(figure)
    db.session.flush()

    _lock_collection_cards(card_ids, 'conquer_figure', figure.id)
    db.session.commit()

    return jsonify({
        'success': True,
        'config': _serialize_config_with_deficit(cfg),
    })


# ── POST /kingdom/conquer/remove_figure ──────────────────────────────────────

@kingdom.route('/conquer/remove_figure', methods=['POST'])
@require_token
def conquer_remove_figure():
    """Remove a figure from a conquer config and unlock its cards.

    Expects JSON: { figure_id }
    """
    data = request.json
    figure_id = data.get('figure_id')
    if not figure_id:
        return jsonify({'success': False, 'message': 'figure_id is required'}), 400

    figure = db.session.get(LandConfigFigure, figure_id)
    if not figure:
        return jsonify({'success': False, 'message': 'Figure not found'}), 404

    cfg = figure.config
    if cfg.user_id != g.user_id:
        return jsonify({'success': False, 'message': 'Not your config'}), 403

    if cfg.config_type != 'conquer':
        return jsonify({'success': False, 'message': 'Not a conquer config'}), 400

    # If this figure is set as battle figure, clear that reference
    if cfg.battle_figure_id == figure.id:
        cfg.battle_figure_id = None

    # Unlock cards
    _unlock_collection_cards(figure.card_ids or [])

    # Remove any battle moves that call this figure
    for move in list(cfg.battle_moves):
        if move.call_figure_id == figure.id:
            move.call_figure_id = None

    db.session.delete(figure)
    db.session.commit()

    return jsonify({
        'success': True,
        'config': _serialize_config_with_deficit(cfg),
    })


# ── POST /kingdom/conquer/buy_battle_move ────────────────────────────────────

@kingdom.route('/conquer/buy_battle_move', methods=['POST'])
@require_token
def conquer_buy_battle_move():
    """Buy a battle move for a conquer config using one collection card.

    Expects JSON: {
        land_id, family_name, card_id, suit, rank, value,
        round_index (0|1|2), call_figure_id (optional)
    }
    """
    data = request.json
    land_id = data.get('land_id')
    family_name = data.get('family_name')
    card_id = data.get('card_id')
    suit = data.get('suit')
    rank = data.get('rank')
    value = data.get('value', 0)
    round_index = data.get('round_index')

    if not all([land_id, family_name, suit, rank]) or round_index is None:
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400

    if round_index not in (0, 1, 2):
        return jsonify({'success': False, 'message': 'round_index must be 0, 1, or 2'}), 400

    # Resolve card by suit+rank if card_id is not a valid DB ID
    if not card_id or not isinstance(card_id, int) or card_id < 0:
        card = CollectionCard.query.filter_by(
            user_id=g.user_id, suit=suit, rank=rank, locked=False
        ).first()
    else:
        card = CollectionCard.query.filter_by(
            id=card_id, user_id=g.user_id
        ).first()
    if not card:
        return jsonify({'success': False, 'message': 'Card not found'}), 404

    if card.locked:
        return jsonify({'success': False, 'message': 'Card is already locked'}), 400

    card_id = card.id

    cfg = _get_or_create_conquer_config(g.user_id, land_id)

    # Check if slot is already taken
    existing = LandConfigBattleMove.query.filter_by(
        config_id=cfg.id, round_index=round_index
    ).first()
    if existing:
        return jsonify({'success': False, 'message': f'Round {round_index} slot is already filled'}), 400

    # Max 3 moves
    move_count = LandConfigBattleMove.query.filter_by(config_id=cfg.id).count()
    if move_count >= 3:
        return jsonify({'success': False, 'message': 'Maximum 3 battle moves reached'}), 400

    move = LandConfigBattleMove(
        config_id=cfg.id,
        family_name=family_name,
        card_id=card_id,
        suit=suit,
        rank=rank,
        value=int(value),
        round_index=round_index,
        call_figure_id=data.get('call_figure_id'),
    )
    db.session.add(move)
    db.session.flush()

    _lock_collection_cards([card_id], 'conquer_move', move.id)
    db.session.commit()

    return jsonify({
        'success': True,
        'config': _serialize_config_with_deficit(cfg),
    })


# ── POST /kingdom/conquer/return_battle_move ─────────────────────────────────

@kingdom.route('/conquer/return_battle_move', methods=['POST'])
@require_token
def conquer_return_battle_move():
    """Return a battle move from a conquer config and unlock the card.

    Expects JSON: { move_id }
    """
    data = request.json
    move_id = data.get('move_id')
    if not move_id:
        return jsonify({'success': False, 'message': 'move_id is required'}), 400

    move = db.session.get(LandConfigBattleMove, move_id)
    if not move:
        return jsonify({'success': False, 'message': 'Move not found'}), 404

    cfg = move.config
    if cfg.user_id != g.user_id:
        return jsonify({'success': False, 'message': 'Not your config'}), 403

    if cfg.config_type != 'conquer':
        return jsonify({'success': False, 'message': 'Not a conquer config'}), 400

    _unlock_collection_cards([move.card_id])

    db.session.delete(move)
    db.session.commit()

    return jsonify({
        'success': True,
        'config': _serialize_config_with_deficit(cfg),
    })


# ── POST /kingdom/conquer/set_modifier ───────────────────────────────────────

@kingdom.route('/conquer/set_modifier', methods=['POST'])
@require_token
def conquer_set_modifier():
    """Set (or replace) the battle modifier for a conquer config.

    Expects JSON: { land_id, modifier_type: 'Blitzkrieg' }
    Only Blitzkrieg is allowed for conquer.
    """
    data = request.json
    land_id = data.get('land_id')
    modifier_type = data.get('modifier_type')

    if not land_id or not modifier_type:
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400

    if modifier_type != 'Blitzkrieg':
        return jsonify({'success': False, 'message': 'Only Blitzkrieg modifier is allowed for conquer'}), 400

    cfg = _get_or_create_conquer_config(g.user_id, land_id)

    # Clear any existing modifier card locks
    if cfg.modifier_card_ids:
        _unlock_collection_cards(cfg.modifier_card_ids)

    # Find required free cards for this modifier
    req = _MODIFIER_CARD_REQS.get(modifier_type)
    if req:
        rank, count, color = req
        card_ids = _find_free_cards(g.user_id, rank, count, color)
        if card_ids is None:
            return jsonify({'success': False,
                            'message': f'{modifier_type} requires {count}× rank {rank} same-color free cards'}), 400
        _lock_collection_cards(card_ids, 'conquer_modifier', cfg.id)
        cfg.modifier_card_ids = card_ids
    else:
        cfg.modifier_card_ids = None

    cfg.battle_modifier = {'type': modifier_type}
    db.session.commit()

    return jsonify({
        'success': True,
        'config': _serialize_config_with_deficit(cfg),
    })


# ── POST /kingdom/conquer/remove_modifier ────────────────────────────────────

@kingdom.route('/conquer/remove_modifier', methods=['POST'])
@require_token
def conquer_remove_modifier():
    """Clear the battle modifier from a conquer config.

    Expects JSON: { land_id }
    """
    data = request.json
    land_id = data.get('land_id')
    if not land_id:
        return jsonify({'success': False, 'message': 'land_id is required'}), 400

    cfg = LandConfig.query.filter_by(
        user_id=g.user_id, config_type='conquer', land_id=land_id
    ).first()
    if not cfg:
        return jsonify({'success': False, 'message': 'No conquer config found'}), 404

    if cfg.modifier_card_ids:
        _unlock_collection_cards(cfg.modifier_card_ids)

    cfg.battle_modifier = None
    cfg.modifier_card_ids = None
    db.session.commit()

    return jsonify({
        'success': True,
        'config': _serialize_config_with_deficit(cfg),
    })


# ── POST /kingdom/conquer/set_prelude_spell ──────────────────────────────────

@kingdom.route('/conquer/set_prelude_spell', methods=['POST'])
@require_token
def conquer_set_prelude_spell():
    """Set a prelude spell for a conquer config.

    Expects JSON: { land_id, spell_name, spell_data: {}|null }
    """
    data = request.json
    land_id = data.get('land_id')
    spell_name = data.get('spell_name')
    spell_data = data.get('spell_data')

    if not land_id or not spell_name:
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400

    if spell_name not in _CONQUER_PRELUDE_SPELLS:
        return jsonify({'success': False,
                        'message': f'Spell "{spell_name}" is not allowed as conquer prelude'}), 400

    cfg = _get_or_create_conquer_config(g.user_id, land_id)

    # Unlock previous prelude spell cards
    if cfg.prelude_spell_card_ids:
        _unlock_collection_cards(cfg.prelude_spell_card_ids)

    # Find required free cards
    req = _SPELL_CARD_COST.get(spell_name)
    if req:
        rank, count, color = req
        card_ids = _find_free_cards(g.user_id, rank, count, color)
        if card_ids is None:
            return jsonify({'success': False,
                            'message': f'{spell_name} requires {count}× rank {rank} free cards'}), 400
        _lock_collection_cards(card_ids, 'conquer_prelude', cfg.id)
        cfg.prelude_spell_card_ids = card_ids
    else:
        cfg.prelude_spell_card_ids = None

    cfg.prelude_spell_name = spell_name
    cfg.prelude_spell_data = spell_data
    db.session.commit()

    return jsonify({'success': True, 'config': _serialize_config_with_deficit(cfg)})


# ── POST /kingdom/conquer/clear_prelude_spell ────────────────────────────────

@kingdom.route('/conquer/clear_prelude_spell', methods=['POST'])
@require_token
def conquer_clear_prelude_spell():
    """Clear the prelude spell from a conquer config."""
    data = request.json
    land_id = data.get('land_id')
    if not land_id:
        return jsonify({'success': False, 'message': 'land_id is required'}), 400

    cfg = LandConfig.query.filter_by(
        user_id=g.user_id, config_type='conquer', land_id=land_id
    ).first()
    if not cfg:
        return jsonify({'success': False, 'message': 'No conquer config found'}), 404

    if cfg.prelude_spell_card_ids:
        _unlock_collection_cards(cfg.prelude_spell_card_ids)

    cfg.prelude_spell_name = None
    cfg.prelude_spell_data = None
    cfg.prelude_spell_card_ids = None
    db.session.commit()

    return jsonify({'success': True, 'config': _serialize_config_with_deficit(cfg)})


# ═════════════════════════════════════════════════════════════════════════════
#  Defence Configuration Endpoints
# ═════════════════════════════════════════════════════════════════════════════

_DEFENCE_MODIFIERS = ('Peasant War', 'Civil War')


def _get_or_create_defence_config(user_id, land_id):
    """Get the user's defence config for a land, or create one."""
    cfg = LandConfig.query.filter_by(
        user_id=user_id, config_type='defence', land_id=land_id
    ).first()
    if not cfg:
        cfg = LandConfig(user_id=user_id, config_type='defence', land_id=land_id)
        db.session.add(cfg)
        db.session.flush()
    return cfg


def _validate_land_ownership(land_id, user_id):
    """Return (land, error_response) — error_response is None on success."""
    land = db.session.get(Land, land_id)
    if not land:
        return None, (jsonify({'success': False, 'message': 'Land not found'}), 404)
    if land.owner_user_id != user_id:
        return None, (jsonify({'success': False, 'message': 'You do not own this land'}), 403)
    return land, None


# ── GET /kingdom/defence/config ──────────────────────────────────────────────

@kingdom.route('/defence/config', methods=['GET'])
@require_token
def get_defence_config():
    """Return the user's defence configuration for an owned land.

    Query params: land_id (required).
    """
    land_id = request.args.get('land_id', type=int)
    if land_id is None:
        return jsonify({'error': 'land_id is required'}), 400

    land, err = _validate_land_ownership(land_id, g.user_id)
    if err:
        return err

    cfg = _get_or_create_defence_config(g.user_id, land_id)
    db.session.commit()

    return jsonify({
        'success': True,
        'config': _serialize_config_with_deficit(cfg),
        'land': land.serialize(),
    })


# ── POST /kingdom/defence/reset_config ───────────────────────────────────────

@kingdom.route('/defence/reset_config', methods=['POST'])
@require_token
def defence_reset_config():
    """Wipe the user's defence config for a land, unlocking all cards."""
    land_id = (request.json or {}).get('land_id')
    if land_id is None:
        return jsonify({'error': 'land_id is required'}), 400

    land, err = _validate_land_ownership(land_id, g.user_id)
    if err:
        return err

    cfg = LandConfig.query.filter_by(
        user_id=g.user_id, config_type='defence', land_id=land_id
    ).first()
    if cfg:
        _wipe_config(cfg)
        db.session.commit()

    return jsonify({'success': True})


# ── POST /kingdom/defence/build_figure ───────────────────────────────────────

@kingdom.route('/defence/build_figure', methods=['POST'])
@require_token
def defence_build_figure():
    """Build a figure for a defence config using collection cards."""
    data = request.json
    land_id = data.get('land_id')
    family_name = data.get('family_name')
    name = data.get('name', family_name)
    suit = data.get('suit')
    color = data.get('color', suit)
    field = data.get('field')
    card_ids = data.get('card_ids', [])
    card_specs = data.get('card_specs', [])
    card_roles = data.get('card_roles', [])

    if not all([land_id, family_name, suit, field]):
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400

    # Resolve card_specs to real card IDs if card_ids not provided
    if not card_ids and card_specs:
        resolved, err = _resolve_cards_by_specs(g.user_id, card_specs)
        if err:
            return err
        card_ids = resolved

    if not card_ids:
        return jsonify({'success': False, 'message': 'No cards provided'}), 400
    if card_roles and len(card_ids) != len(card_roles):
        return jsonify({'success': False, 'message': 'card_ids and card_roles length mismatch'}), 400

    land, err = _validate_land_ownership(land_id, g.user_id)
    if err:
        return err

    cards = CollectionCard.query.filter(
        CollectionCard.id.in_(card_ids),
        CollectionCard.user_id == g.user_id,
    ).all()
    if len(cards) != len(card_ids):
        return jsonify({'success': False, 'message': 'Some cards not found or not owned'}), 400
    if any(c.locked for c in cards):
        return jsonify({'success': False, 'message': 'Some cards are already locked'}), 400

    cfg = _get_or_create_defence_config(g.user_id, land_id)

    figure = LandConfigFigure(
        config_id=cfg.id,
        family_name=family_name, name=name or family_name,
        suit=suit, color=color or suit, field=field,
        card_ids=card_ids, card_roles=card_roles,
        produces=data.get('produces'), requires=data.get('requires'),
        description=data.get('description', ''),
        upgrade_family_name=data.get('upgrade_family_name'),
        checkmate=data.get('checkmate', False),
        cannot_be_blocked=data.get('cannot_be_blocked', False),
        rest_after_attack=data.get('rest_after_attack', False),
    )
    db.session.add(figure)
    db.session.flush()
    _lock_collection_cards(card_ids, 'defence_figure', figure.id)
    db.session.commit()

    return jsonify({'success': True, 'config': _serialize_config_with_deficit(cfg)})


# ── POST /kingdom/defence/remove_figure ──────────────────────────────────────

@kingdom.route('/defence/remove_figure', methods=['POST'])
@require_token
def defence_remove_figure():
    """Remove a figure from a defence config and unlock its cards."""
    data = request.json
    figure_id = data.get('figure_id')
    if not figure_id:
        return jsonify({'success': False, 'message': 'figure_id is required'}), 400

    figure = db.session.get(LandConfigFigure, figure_id)
    if not figure:
        return jsonify({'success': False, 'message': 'Figure not found'}), 404

    cfg = figure.config
    if cfg.user_id != g.user_id:
        return jsonify({'success': False, 'message': 'Not your config'}), 403
    if cfg.config_type != 'defence':
        return jsonify({'success': False, 'message': 'Not a defence config'}), 400

    # Clear battle figure references
    if cfg.battle_figure_id == figure.id:
        cfg.battle_figure_id = None
    if cfg.battle_figure_id_2 == figure.id:
        cfg.battle_figure_id_2 = None

    _unlock_collection_cards(figure.card_ids or [])

    for move in list(cfg.battle_moves):
        if move.call_figure_id == figure.id:
            move.call_figure_id = None

    db.session.delete(figure)
    db.session.commit()

    return jsonify({'success': True, 'config': _serialize_config_with_deficit(cfg)})


# ── POST /kingdom/defence/buy_battle_move ────────────────────────────────────

@kingdom.route('/defence/buy_battle_move', methods=['POST'])
@require_token
def defence_buy_battle_move():
    """Buy a battle move for a defence config."""
    data = request.json
    land_id = data.get('land_id')
    family_name = data.get('family_name')
    card_id = data.get('card_id')
    suit = data.get('suit')
    rank = data.get('rank')
    value = data.get('value', 0)
    round_index = data.get('round_index')

    if not all([land_id, family_name, suit, rank]) or round_index is None:
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400
    if round_index not in (0, 1, 2):
        return jsonify({'success': False, 'message': 'round_index must be 0, 1, or 2'}), 400

    land, err = _validate_land_ownership(land_id, g.user_id)
    if err:
        return err

    # Resolve card by suit+rank if card_id is not a valid DB ID
    if not card_id or not isinstance(card_id, int) or card_id < 0:
        card = CollectionCard.query.filter_by(
            user_id=g.user_id, suit=suit, rank=rank, locked=False
        ).first()
    else:
        card = CollectionCard.query.filter_by(id=card_id, user_id=g.user_id).first()
    if not card:
        return jsonify({'success': False, 'message': 'Card not found'}), 404
    if card.locked:
        return jsonify({'success': False, 'message': 'Card is already locked'}), 400

    card_id = card.id

    cfg = _get_or_create_defence_config(g.user_id, land_id)

    existing = LandConfigBattleMove.query.filter_by(
        config_id=cfg.id, round_index=round_index
    ).first()
    if existing:
        return jsonify({'success': False, 'message': f'Round {round_index} slot is already filled'}), 400

    if LandConfigBattleMove.query.filter_by(config_id=cfg.id).count() >= 3:
        return jsonify({'success': False, 'message': 'Maximum 3 battle moves reached'}), 400

    move = LandConfigBattleMove(
        config_id=cfg.id, family_name=family_name, card_id=card_id,
        suit=suit, rank=rank, value=int(value), round_index=round_index,
        call_figure_id=data.get('call_figure_id'),
    )
    db.session.add(move)
    db.session.flush()
    _lock_collection_cards([card_id], 'defence_move', move.id)
    db.session.commit()

    return jsonify({'success': True, 'config': _serialize_config_with_deficit(cfg)})


# ── POST /kingdom/defence/return_battle_move ─────────────────────────────────

@kingdom.route('/defence/return_battle_move', methods=['POST'])
@require_token
def defence_return_battle_move():
    """Return a battle move from a defence config and unlock the card."""
    data = request.json
    move_id = data.get('move_id')
    if not move_id:
        return jsonify({'success': False, 'message': 'move_id is required'}), 400

    move = db.session.get(LandConfigBattleMove, move_id)
    if not move:
        return jsonify({'success': False, 'message': 'Move not found'}), 404

    cfg = move.config
    if cfg.user_id != g.user_id:
        return jsonify({'success': False, 'message': 'Not your config'}), 403
    if cfg.config_type != 'defence':
        return jsonify({'success': False, 'message': 'Not a defence config'}), 400

    _unlock_collection_cards([move.card_id])
    db.session.delete(move)
    db.session.commit()

    return jsonify({'success': True, 'config': _serialize_config_with_deficit(cfg)})


# ── POST /kingdom/defence/set_modifier ───────────────────────────────────────

@kingdom.route('/defence/set_modifier', methods=['POST'])
@require_token
def defence_set_modifier():
    """Set the battle modifier for a defence config.

    Expects JSON: { land_id, modifier_type: 'Peasant War'|'Civil War' }
    If the modifier changes and invalidates the current battle figure,
    the battle figure is auto-cleared.
    """
    data = request.json
    land_id = data.get('land_id')
    modifier_type = data.get('modifier_type')

    if not land_id or not modifier_type:
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400

    if modifier_type not in _DEFENCE_MODIFIERS:
        return jsonify({'success': False,
                        'message': f'Only {", ".join(_DEFENCE_MODIFIERS)} allowed for defence'}), 400

    land, err = _validate_land_ownership(land_id, g.user_id)
    if err:
        return err

    cfg = _get_or_create_defence_config(g.user_id, land_id)

    if cfg.modifier_card_ids:
        _unlock_collection_cards(cfg.modifier_card_ids)

    # Find required free cards for this modifier
    req = _MODIFIER_CARD_REQS.get(modifier_type)
    if req:
        rank, count, color = req
        card_ids = _find_free_cards(g.user_id, rank, count, color)
        if card_ids is None:
            return jsonify({'success': False,
                            'message': f'{modifier_type} requires {count}× rank {rank} same-color free cards'}), 400
        _lock_collection_cards(card_ids, 'defence_modifier', cfg.id)
        cfg.modifier_card_ids = card_ids
    else:
        cfg.modifier_card_ids = None

    cfg.battle_modifier = {'type': modifier_type}

    # Auto-clear battle figure if incompatible with new modifier
    if modifier_type == 'Civil War':
        # Civil War needs 2 same-color figures
        if cfg.battle_figure_id and not cfg.battle_figure_id_2:
            cfg.battle_figure_id = None
        if cfg.battle_figure_id and cfg.battle_figure_id_2:
            fig1 = db.session.get(LandConfigFigure, cfg.battle_figure_id)
            fig2 = db.session.get(LandConfigFigure, cfg.battle_figure_id_2)
            if fig1 and fig2 and fig1.color != fig2.color:
                cfg.battle_figure_id = None
                cfg.battle_figure_id_2 = None
    else:
        # Non-civil-war: clear second battle figure
        cfg.battle_figure_id_2 = None

    db.session.commit()
    return jsonify({'success': True, 'config': _serialize_config_with_deficit(cfg)})


# ── POST /kingdom/defence/remove_modifier ────────────────────────────────────

@kingdom.route('/defence/remove_modifier', methods=['POST'])
@require_token
def defence_remove_modifier():
    """Clear the battle modifier from a defence config."""
    data = request.json
    land_id = data.get('land_id')
    if not land_id:
        return jsonify({'success': False, 'message': 'land_id is required'}), 400

    land, err = _validate_land_ownership(land_id, g.user_id)
    if err:
        return err

    cfg = LandConfig.query.filter_by(
        user_id=g.user_id, config_type='defence', land_id=land_id
    ).first()
    if not cfg:
        return jsonify({'success': False, 'message': 'No defence config found'}), 404

    if cfg.modifier_card_ids:
        _unlock_collection_cards(cfg.modifier_card_ids)

    cfg.battle_modifier = None
    cfg.modifier_card_ids = None
    cfg.battle_figure_id_2 = None  # second fig only relevant for civil war
    db.session.commit()

    return jsonify({'success': True, 'config': _serialize_config_with_deficit(cfg)})


# ── POST /kingdom/defence/set_prelude_spell ──────────────────────────────────

@kingdom.route('/defence/set_prelude_spell', methods=['POST'])
@require_token
def defence_set_prelude_spell():
    """Set a prelude spell for a defence config.

    Expects JSON: { land_id, spell_name, spell_data: {}|null }
    """
    data = request.json
    land_id = data.get('land_id')
    spell_name = data.get('spell_name')
    spell_data = data.get('spell_data')

    if not land_id or not spell_name:
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400

    if spell_name not in _DEFENCE_PRELUDE_SPELLS:
        return jsonify({'success': False,
                        'message': f'Spell "{spell_name}" is not allowed as defence prelude'}), 400

    land, err = _validate_land_ownership(land_id, g.user_id)
    if err:
        return err

    cfg = _get_or_create_defence_config(g.user_id, land_id)

    # Unlock previous prelude spell cards
    if cfg.prelude_spell_card_ids:
        _unlock_collection_cards(cfg.prelude_spell_card_ids)

    # Find required free cards
    req = _SPELL_CARD_COST.get(spell_name)
    if req:
        rank, count, color = req
        card_ids = _find_free_cards(g.user_id, rank, count, color)
        if card_ids is None:
            return jsonify({'success': False,
                            'message': f'{spell_name} requires {count}× rank {rank} free cards'}), 400
        _lock_collection_cards(card_ids, 'defence_prelude', cfg.id)
        cfg.prelude_spell_card_ids = card_ids
    else:
        cfg.prelude_spell_card_ids = None

    cfg.prelude_spell_name = spell_name
    cfg.prelude_spell_data = spell_data
    db.session.commit()

    return jsonify({'success': True, 'config': _serialize_config_with_deficit(cfg)})


# ── POST /kingdom/defence/clear_prelude_spell ────────────────────────────────

@kingdom.route('/defence/clear_prelude_spell', methods=['POST'])
@require_token
def defence_clear_prelude_spell():
    """Clear the prelude spell from a defence config."""
    data = request.json
    land_id = data.get('land_id')
    if not land_id:
        return jsonify({'success': False, 'message': 'land_id is required'}), 400

    land, err = _validate_land_ownership(land_id, g.user_id)
    if err:
        return err

    cfg = LandConfig.query.filter_by(
        user_id=g.user_id, config_type='defence', land_id=land_id
    ).first()
    if not cfg:
        return jsonify({'success': False, 'message': 'No defence config found'}), 404

    if cfg.prelude_spell_card_ids:
        _unlock_collection_cards(cfg.prelude_spell_card_ids)

    cfg.prelude_spell_name = None
    cfg.prelude_spell_data = None
    cfg.prelude_spell_card_ids = None
    db.session.commit()

    return jsonify({'success': True, 'config': _serialize_config_with_deficit(cfg)})


# ── POST /kingdom/defence/set_battle_figure ──────────────────────────────────

@kingdom.route('/defence/set_battle_figure', methods=['POST'])
@require_token
def defence_set_battle_figure():
    """Set the battle figure(s) for a defence config.

    Expects JSON: { land_id, figure_id, figure_id_2 (optional, civil war) }
    Figures with resource deficit cannot be selected.
    """
    from kingdom_service import get_config_deficit_map

    data = request.json
    land_id = data.get('land_id')
    figure_id = data.get('figure_id')
    figure_id_2 = data.get('figure_id_2')

    if not land_id or not figure_id:
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400

    land, err = _validate_land_ownership(land_id, g.user_id)
    if err:
        return err

    cfg = LandConfig.query.filter_by(
        user_id=g.user_id, config_type='defence', land_id=land_id
    ).first()
    if not cfg:
        return jsonify({'success': False, 'message': 'No defence config found'}), 404

    # Verify figure belongs to this config
    fig1 = db.session.get(LandConfigFigure, figure_id)
    if not fig1 or fig1.config_id != cfg.id:
        return jsonify({'success': False, 'message': 'Figure not in this config'}), 400

    # Check deficit
    deficit_map = get_config_deficit_map(cfg.id)
    if deficit_map.get(figure_id, False):
        return jsonify({'success': False, 'message': 'Cannot select a figure with resource deficit'}), 400

    # Spell and battle figure are mutually exclusive
    if cfg.spell_name:
        return jsonify({'success': False,
                        'message': 'Cannot set battle figure while a spell is active. Remove spell first.'}), 400

    # Civil War validation
    modifier = cfg.battle_modifier or {}
    is_civil_war = modifier.get('type') == 'Civil War'

    if is_civil_war:
        if not figure_id_2:
            return jsonify({'success': False,
                            'message': 'Civil War requires two battle figures'}), 400
        fig2 = db.session.get(LandConfigFigure, figure_id_2)
        if not fig2 or fig2.config_id != cfg.id:
            return jsonify({'success': False, 'message': 'Second figure not in this config'}), 400
        if deficit_map.get(figure_id_2, False):
            return jsonify({'success': False,
                            'message': 'Cannot select a figure with resource deficit'}), 400
        if fig1.color != fig2.color:
            return jsonify({'success': False,
                            'message': 'Civil War: both figures must be the same color'}), 400
    else:
        figure_id_2 = None

    cfg.battle_figure_id = figure_id
    cfg.battle_figure_id_2 = figure_id_2
    db.session.commit()

    return jsonify({'success': True, 'config': _serialize_config_with_deficit(cfg)})


# ── POST /kingdom/defence/clear_battle_figure ────────────────────────────────

@kingdom.route('/defence/clear_battle_figure', methods=['POST'])
@require_token
def defence_clear_battle_figure():
    """Clear the battle figure selection from a defence config."""
    data = request.json
    land_id = data.get('land_id')
    if not land_id:
        return jsonify({'success': False, 'message': 'land_id is required'}), 400

    land, err = _validate_land_ownership(land_id, g.user_id)
    if err:
        return err

    cfg = LandConfig.query.filter_by(
        user_id=g.user_id, config_type='defence', land_id=land_id
    ).first()
    if not cfg:
        return jsonify({'success': False, 'message': 'No defence config found'}), 404

    cfg.battle_figure_id = None
    cfg.battle_figure_id_2 = None
    db.session.commit()

    return jsonify({'success': True, 'config': _serialize_config_with_deficit(cfg)})


# ── POST /kingdom/defence/set_spell ──────────────────────────────────────────

@kingdom.route('/defence/set_spell', methods=['POST'])
@require_token
def defence_set_spell():
    """Set a spell for a defence config.

    Expects JSON: {
        land_id, spell_name: 'health_boost'|'poison',
        spell_card_ids: [int, ...],
        spell_target_figure_id: int|null  (required for health_boost)
    }
    """
    from kingdom_service import get_config_deficit_map

    data = request.json
    land_id = data.get('land_id')
    spell_name = data.get('spell_name')
    spell_card_ids = data.get('spell_card_ids', [])
    target_fig_id = data.get('spell_target_figure_id')

    if not land_id or not spell_name:
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400

    if spell_name not in ('health_boost', 'poison'):
        return jsonify({'success': False, 'message': 'Invalid spell name'}), 400

    land, err = _validate_land_ownership(land_id, g.user_id)
    if err:
        return err

    cfg = LandConfig.query.filter_by(
        user_id=g.user_id, config_type='defence', land_id=land_id
    ).first()
    if not cfg:
        return jsonify({'success': False, 'message': 'No defence config found'}), 404

    # Spell and battle figure are mutually exclusive
    if cfg.battle_figure_id:
        return jsonify({'success': False,
                        'message': 'Cannot set spell while a battle figure is selected. Clear battle figure first.'}), 400

    # Auto-find spell cards if none provided
    if not spell_card_ids:
        req = _SPELL_CARD_REQS.get(spell_name)
        if req:
            rank, count, color = req
            spell_card_ids = _find_free_cards(g.user_id, rank, count, color)
            if spell_card_ids is None:
                return jsonify({'success': False,
                                'message': f'{spell_name} requires {count}× rank {rank} same-color free cards'}), 400

    # Verify spell cards belong to user and are unlocked
    if spell_card_ids:
        cards = CollectionCard.query.filter(
            CollectionCard.id.in_(spell_card_ids),
            CollectionCard.user_id == g.user_id,
        ).all()
        if len(cards) != len(spell_card_ids):
            return jsonify({'success': False, 'message': 'Some spell cards not found'}), 400
        if any(c.locked for c in cards):
            return jsonify({'success': False, 'message': 'Some spell cards are locked'}), 400

    # Health boost requires a target figure
    if spell_name == 'health_boost':
        if not target_fig_id:
            return jsonify({'success': False, 'message': 'Health boost requires a target figure'}), 400
        fig = db.session.get(LandConfigFigure, target_fig_id)
        if not fig or fig.config_id != cfg.id:
            return jsonify({'success': False, 'message': 'Target figure not in this config'}), 400

    # Unlock previous spell cards
    if cfg.spell_card_ids:
        _unlock_collection_cards(cfg.spell_card_ids)

    # Lock new spell cards
    if spell_card_ids:
        _lock_collection_cards(spell_card_ids, 'defence_spell', cfg.id)

    cfg.spell_name = spell_name
    cfg.spell_card_ids = spell_card_ids or None
    cfg.spell_target_figure_id = target_fig_id
    db.session.commit()

    return jsonify({'success': True, 'config': _serialize_config_with_deficit(cfg)})


# ── POST /kingdom/defence/clear_spell ────────────────────────────────────────

@kingdom.route('/defence/clear_spell', methods=['POST'])
@require_token
def defence_clear_spell():
    """Clear the spell from a defence config and unlock spell cards."""
    data = request.json
    land_id = data.get('land_id')
    if not land_id:
        return jsonify({'success': False, 'message': 'land_id is required'}), 400

    land, err = _validate_land_ownership(land_id, g.user_id)
    if err:
        return err

    cfg = LandConfig.query.filter_by(
        user_id=g.user_id, config_type='defence', land_id=land_id
    ).first()
    if not cfg:
        return jsonify({'success': False, 'message': 'No defence config found'}), 404

    if cfg.spell_card_ids:
        _unlock_collection_cards(cfg.spell_card_ids)

    cfg.spell_name = None
    cfg.spell_card_ids = None
    cfg.spell_target_figure_id = None
    db.session.commit()

    return jsonify({'success': True, 'config': _serialize_config_with_deficit(cfg)})


# ── POST /kingdom/defence/set_counter_spell ──────────────────────────────────

@kingdom.route('/defence/set_counter_spell', methods=['POST'])
@require_token
def defence_set_counter_spell():
    """Set a counter spell for a defence config.

    Expects JSON: { land_id, spell_name, spell_data: {}|null }
    Counter spell is mutually exclusive with battle figure.
    """
    data = request.json
    land_id = data.get('land_id')
    spell_name = data.get('spell_name')
    spell_data = data.get('spell_data')

    if not land_id or not spell_name:
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400

    if spell_name not in _DEFENCE_COUNTER_SPELLS:
        return jsonify({'success': False,
                        'message': f'Spell "{spell_name}" is not allowed as counter action'}), 400

    land, err = _validate_land_ownership(land_id, g.user_id)
    if err:
        return err

    cfg = LandConfig.query.filter_by(
        user_id=g.user_id, config_type='defence', land_id=land_id
    ).first()
    if not cfg:
        return jsonify({'success': False, 'message': 'No defence config found'}), 404

    # Counter spell and battle figure are mutually exclusive
    if cfg.battle_figure_id:
        return jsonify({'success': False,
                        'message': 'Cannot set counter spell while a battle figure is selected. '
                                   'Clear battle figure first.'}), 400

    # Unlock previous counter spell cards
    if cfg.counter_spell_card_ids:
        _unlock_collection_cards(cfg.counter_spell_card_ids)

    # Find required free cards
    req = _SPELL_CARD_COST.get(spell_name)
    if req:
        rank, count, color = req
        card_ids = _find_free_cards(g.user_id, rank, count, color)
        if card_ids is None:
            return jsonify({'success': False,
                            'message': f'{spell_name} requires {count}× rank {rank} free cards'}), 400
        _lock_collection_cards(card_ids, 'defence_counter', cfg.id)
        cfg.counter_spell_card_ids = card_ids
    else:
        cfg.counter_spell_card_ids = None

    cfg.counter_spell_name = spell_name
    cfg.counter_spell_data = spell_data
    cfg.counter_spell_target_figure_id = None
    db.session.commit()

    return jsonify({'success': True, 'config': _serialize_config_with_deficit(cfg)})


# ── POST /kingdom/defence/clear_counter_spell ────────────────────────────────

@kingdom.route('/defence/clear_counter_spell', methods=['POST'])
@require_token
def defence_clear_counter_spell():
    """Clear the counter spell from a defence config."""
    data = request.json
    land_id = data.get('land_id')
    if not land_id:
        return jsonify({'success': False, 'message': 'land_id is required'}), 400

    land, err = _validate_land_ownership(land_id, g.user_id)
    if err:
        return err

    cfg = LandConfig.query.filter_by(
        user_id=g.user_id, config_type='defence', land_id=land_id
    ).first()
    if not cfg:
        return jsonify({'success': False, 'message': 'No defence config found'}), 404

    if cfg.counter_spell_card_ids:
        _unlock_collection_cards(cfg.counter_spell_card_ids)

    cfg.counter_spell_name = None
    cfg.counter_spell_data = None
    cfg.counter_spell_card_ids = None
    cfg.counter_spell_target_figure_id = None
    db.session.commit()

    return jsonify({'success': True, 'config': _serialize_config_with_deficit(cfg)})


# ── POST /kingdom/defence/set_auto_gamble ────────────────────────────────────

@kingdom.route('/defence/set_auto_gamble', methods=['POST'])
@require_token
def defence_set_auto_gamble():
    """Toggle auto-gamble for a defence config.

    Expects JSON: { land_id, auto_gamble: bool }
    """
    data = request.json
    land_id = data.get('land_id')
    auto_gamble = data.get('auto_gamble')

    if not land_id or auto_gamble is None:
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400

    land, err = _validate_land_ownership(land_id, g.user_id)
    if err:
        return err

    cfg = LandConfig.query.filter_by(
        user_id=g.user_id, config_type='defence', land_id=land_id
    ).first()
    if not cfg:
        return jsonify({'success': False, 'message': 'No defence config found'}), 404

    cfg.auto_gamble = bool(auto_gamble)
    db.session.commit()

    return jsonify({'success': True, 'config': _serialize_config_with_deficit(cfg)})


# ═════════════════════════════════════════════════════════════════════════════
#  Conquer Battle — Phase 13
# ═════════════════════════════════════════════════════════════════════════════

_RANK_TO_VALUE = {
    '7': 7, '8': 8, '9': 9, '10': 10,
    'J': 1, 'Q': 2, 'K': 4, 'A': 3,
}


# ── Figure-power helpers for fallback selection ─────────────────────────────

_FIELD_OVERRIDE_BASE_POWER = {'castle': 15}


def _fb_base_power(figure):
    """Base power of a game Figure (castle=15, else sum of card values)."""
    override = _FIELD_OVERRIDE_BASE_POWER.get(figure.field)
    if override is not None:
        return override
    total = 0
    for assoc in CardToFigure.query.filter_by(figure_id=figure.id).all():
        card = (db.session.get(MainCard, assoc.card_id) if assoc.card_type == 'main'
                else db.session.get(SideCard, assoc.card_id))
        if card:
            total += card.value
    return total


def _fb_support_bonus(figure, all_figures, game_id, land_suit_bonus=None):
    """Support bonus from same-player, same-suit figures."""
    fig_field = (figure.field or '').lower()
    if fig_field == 'castle':
        valid_fields = {'castle'}
    elif fig_field == 'village':
        valid_fields = {'castle'}
    elif fig_field == 'military':
        valid_fields = {'castle', 'village'}
    else:
        return 0

    total = 0
    for f in all_figures:
        if f.id == figure.id or f.player_id != figure.player_id:
            continue
        if (f.suit or '').lower() != (figure.suit or '').lower():
            continue
        f_field = (f.field or '').lower()
        if f_field not in valid_fields or f_field == 'military':
            continue
        if _fb_has_deficit(f, f.player_id, game_id):
            continue
        if f_field == 'castle':
            total += 5 if 'Maharaja' in (f.name or '') else 4
        else:
            for assoc in CardToFigure.query.filter_by(figure_id=f.id).all():
                if assoc.role == CardRole.KEY:
                    card = (db.session.get(MainCard, assoc.card_id)
                            if assoc.card_type == 'main'
                            else db.session.get(SideCard, assoc.card_id))
                    if card:
                        total += card.value

    if land_suit_bonus:
        bonus_suit, bonus_value = land_suit_bonus
        if (figure.suit or '').lower() == bonus_suit.lower():
            total += bonus_value
    return total


def _fb_healer_buff(figure, all_figures, game_id):
    """Healer buff: +4 per same-suit Healer for village figures."""
    if (figure.field or '').lower() != 'village':
        return 0
    buff = 0
    for f in all_figures:
        if f.player_id != figure.player_id:
            continue
        if 'Healer' not in (f.name or ''):
            continue
        if (f.suit or '').lower() != (figure.suit or '').lower():
            continue
        if _fb_has_deficit(f, f.player_id, game_id):
            continue
        buff += 4
    return buff


def _fb_wall_total(all_figures, player_id, game_id):
    """Sum of Wall side-card values for the player (defender wall bonus)."""
    total = 0
    for f in all_figures:
        if f.player_id != player_id:
            continue
        if 'Wall' not in (f.name or ''):
            continue
        if _fb_has_deficit(f, player_id, game_id):
            continue
        for assoc in CardToFigure.query.filter_by(figure_id=f.id).all():
            if assoc.card_type == 'side':
                card = db.session.get(SideCard, assoc.card_id)
                if card:
                    total += card.value
    return total


def _fb_enchantment_mod(figure_id, game_id, player_id):
    """Sum of active enchantment power modifiers on a figure."""
    spells = ActiveSpell.query.filter_by(
        game_id=game_id, player_id=player_id, is_active=True
    ).all()
    total = 0
    for s in spells:
        if s.target_figure_id != figure_id:
            continue
        ed = s.effect_data or {}
        pm = ed.get('power_modifier', 0)
        if isinstance(pm, (int, float)) and pm != -999:
            total += int(pm)
    return total


def _fb_has_deficit(figure, player_id, game_id):
    """Check if a game Figure has a resource deficit."""
    if not figure.requires:
        return False
    all_figs = Figure.query.filter_by(
        player_id=player_id, game_id=game_id).all()
    total_requires = {}
    for fig in all_figs:
        if fig.requires:
            for res, amt in fig.requires.items():
                total_requires[res] = total_requires.get(res, 0) + amt
    excluded = set()
    stable = False
    while not stable:
        stable = True
        total_produces = {}
        for i, fig in enumerate(all_figs):
            if i in excluded:
                continue
            if fig.produces:
                for res, amt in fig.produces.items():
                    total_produces[res] = total_produces.get(res, 0) + amt
        for i, fig in enumerate(all_figs):
            if i in excluded or not fig.requires:
                continue
            for res_name in fig.requires:
                if total_requires.get(res_name, 0) > total_produces.get(res_name, 0):
                    excluded.add(i)
                    stable = False
                    break
    for res_name in figure.requires:
        if total_requires.get(res_name, 0) > total_produces.get(res_name, 0):
            return True
    return False


def _pick_strongest_figure(game_figures, game):
    """Pick the strongest non-deficit figure using full power computation.

    Power = base + support + healer + wall + enchantment + land suit bonus.

    Returns the game figure ID of the strongest eligible figure, or
    the first figure's ID if none are eligible.
    """
    if not game_figures:
        return None

    player_id = game_figures[0].player_id
    game_id = game.id
    all_figures = Figure.query.filter_by(game_id=game_id).all()

    # Land suit bonus for conquer mode
    land_suit_bonus = None
    if game.mode == 'conquer' and game.land_id:
        land = db.session.get(Land, game.land_id)
        if land and land.suit_bonus_suit and land.suit_bonus_value:
            land_suit_bonus = (land.suit_bonus_suit, land.suit_bonus_value)

    # Wall total (defender gets wall bonus)
    wall = _fb_wall_total(all_figures, player_id, game_id)

    best_id = None
    best_power = -1

    for gf in game_figures:
        if _fb_has_deficit(gf, player_id, game_id):
            continue
        base = _fb_base_power(gf)
        support = _fb_support_bonus(gf, all_figures, game_id,
                                    land_suit_bonus=land_suit_bonus)
        healer = _fb_healer_buff(gf, all_figures, game_id)
        enchant = _fb_enchantment_mod(gf.id, game_id, player_id)
        power = base + support + healer + wall + enchant

        if power > best_power:
            best_power = power
            best_id = gf.id

    if best_id is None:
        best_id = game_figures[0].id

    return best_id


def _build_figures_from_config(cfg_figures, player, game):
    """Create Figure + CardToFigure records from LandConfigFigure list.

    Creates real MainCard records from the collection cards so that
    CardToFigure.serialize() can include rank/suit/value data.

    Returns a list of created Figure objects (flushed, with IDs).
    """
    figures = []
    for cfg_fig in cfg_figures:
        fig = Figure(
            player_id=player.id,
            game_id=game.id,
            family_name=cfg_fig.family_name,
            name=cfg_fig.name,
            suit=cfg_fig.suit,
            color=cfg_fig.color,
            field=cfg_fig.field,
            description=cfg_fig.description or '',
            upgrade_family_name=cfg_fig.upgrade_family_name,
            produces=cfg_fig.produces,
            requires=cfg_fig.requires,
            checkmate=cfg_fig.checkmate,
            cannot_be_blocked=cfg_fig.cannot_be_blocked,
            rest_after_attack=cfg_fig.rest_after_attack,
        )
        db.session.add(fig)
        db.session.flush()

        card_ids = cfg_fig.card_ids or []
        card_roles = cfg_fig.card_roles or []
        for i, role in enumerate(card_roles):
            # Look up the collection card to get rank/suit/value
            rank = None
            suit = cfg_fig.suit
            value = 0
            if i < len(card_ids) and card_ids[i]:
                cc = db.session.get(CollectionCard, card_ids[i])
                if cc:
                    rank = cc.rank
                    suit = cc.suit
                    value = cc.value
            if not rank:
                # Fallback: derive from figure suit and role
                rank = 'K' if role == 'key' else '10'
                value = _RANK_TO_VALUE.get(rank, 0)

            mc = MainCard(
                rank=rank,
                suit=suit,
                value=value,
                game_id=game.id,
                player_id=player.id,
                in_deck=False,
                part_of_figure=True,
            )
            db.session.add(mc)
            db.session.flush()

            ctf = CardToFigure(
                figure_id=fig.id,
                card_id=mc.id,
                card_type='main',
                role=role,
            )
            db.session.add(ctf)

        figures.append(fig)
    return figures


def _build_figures_from_template(template_figures, player, game):
    """Create Figure records from AI template figure dicts.

    Creates real MainCard records from the template's ``cards`` list so that
    CardToFigure.serialize() can include rank/suit/value data.

    Returns a list of created Figure objects (flushed, with IDs).
    """
    figures = []
    for tpl_fig in template_figures:
        fig = Figure(
            player_id=player.id,
            game_id=game.id,
            family_name=tpl_fig['family_name'],
            name=tpl_fig.get('name', tpl_fig['family_name']),
            suit=tpl_fig['suit'],
            color=tpl_fig['color'],
            field=tpl_fig['field'],
            description=tpl_fig.get('description', ''),
            upgrade_family_name=tpl_fig.get('upgrade_family_name'),
            produces=tpl_fig.get('produces'),
            requires=tpl_fig.get('requires'),
            checkmate=tpl_fig.get('checkmate', False),
            cannot_be_blocked=tpl_fig.get('cannot_be_blocked', False),
            rest_after_attack=tpl_fig.get('rest_after_attack', False),
        )
        db.session.add(fig)
        db.session.flush()

        tpl_cards = tpl_fig.get('cards', [])
        card_roles = tpl_fig.get('card_roles', [])
        for i, role in enumerate(card_roles):
            if i < len(tpl_cards):
                rank = tpl_cards[i].get('rank', 'K' if role == 'key' else '10')
                suit = tpl_cards[i].get('suit', tpl_fig['suit'])
            else:
                rank = 'K' if role == 'key' else '10'
                suit = tpl_fig['suit']
            value = _RANK_TO_VALUE.get(rank, 0)

            mc = MainCard(
                rank=rank,
                suit=suit,
                value=value,
                game_id=game.id,
                player_id=player.id,
                in_deck=False,
                part_of_figure=True,
            )
            db.session.add(mc)
            db.session.flush()

            ctf = CardToFigure(
                figure_id=fig.id,
                card_id=mc.id,
                card_type='main',
                role=role,
            )
            db.session.add(ctf)

        figures.append(fig)
    return figures


def _build_battle_moves_from_config(cfg_moves, player, game, config_figure_map=None):
    """Create BattleMove records from LandConfigBattleMove list.

    Creates a real MainCard for each move so the card appears in the
    player's hand display.  config_figure_map: optional dict mapping
    LandConfigFigure.id -> Figure.id for resolving call_figure_id.
    """
    for cfg_move in cfg_moves:
        call_fig_id = None
        if cfg_move.call_figure_id and config_figure_map:
            call_fig_id = config_figure_map.get(cfg_move.call_figure_id)

        mc = MainCard(
            rank=cfg_move.rank,
            suit=cfg_move.suit,
            value=cfg_move.value,
            game_id=game.id,
            player_id=player.id,
            in_deck=False,
            part_of_figure=False,
            part_of_battle_move=True,
        )
        db.session.add(mc)
        db.session.flush()

        move = BattleMove(
            game_id=game.id,
            player_id=player.id,
            family_name=cfg_move.family_name,
            card_id=mc.id,
            card_type='main',
            suit=cfg_move.suit,
            rank=cfg_move.rank,
            value=cfg_move.value,
            call_figure_id=call_fig_id,
        )
        db.session.add(move)


def _build_battle_moves_from_template(template_moves, player, game,
                                      template_figures=None, game_figures=None):
    """Create BattleMove records from AI template move dicts.

    Creates a real MainCard for each move.  template_figures and
    game_figures are parallel lists to resolve call_figure references
    by index.
    """
    for tpl_move in template_moves:
        call_fig_id = None
        # Resolve call figure for Call Villager/Call Military/Call King
        if tpl_move['family_name'] in ('Call Villager', 'Call Military', 'Call King'):
            field_map = {
                'Call Villager': 'village',
                'Call Military': 'military',
                'Call King': 'castle',
            }
            target_field = field_map[tpl_move['family_name']]
            if game_figures:
                for gf in game_figures:
                    if gf.field == target_field:
                        call_fig_id = gf.id
                        break

        mc = MainCard(
            rank=tpl_move['rank'],
            suit=tpl_move['suit'],
            value=tpl_move['value'],
            game_id=game.id,
            player_id=player.id,
            in_deck=False,
            part_of_figure=False,
            part_of_battle_move=True,
        )
        db.session.add(mc)
        db.session.flush()

        move = BattleMove(
            game_id=game.id,
            player_id=player.id,
            family_name=tpl_move['family_name'],
            card_id=mc.id,
            card_type=tpl_move.get('card_type', 'main'),
            suit=tpl_move['suit'],
            rank=tpl_move['rank'],
            value=tpl_move['value'],
            call_figure_id=call_fig_id,
        )
        db.session.add(move)


def _get_or_create_ai_user():
    """Get the AI user for unowned land battles."""
    ai_username = config.AI_USERNAMES[0] if config.AI_USERNAMES else '[AI] Strategos'
    ai_user = User.query.filter_by(username=ai_username).first()
    if not ai_user:
        from werkzeug.security import generate_password_hash
        ai_user = User(
            username=ai_username,
            password_hash=generate_password_hash('ai_internal'),
            gold=config.AI_INITIAL_GOLD,
            is_ai=True,
        )
        db.session.add(ai_user)
        db.session.flush()
    return ai_user


def _create_prelude_spell(game, player, spell_name, spell_data, game_figures):
    """Create an ActiveSpell for a prelude spell and execute it immediately.

    For battle-modifier spells (Peasant War / Civil War / Blitzkrieg) the
    modifier is also appended to ``game.battle_modifier`` so that existing
    game logic (advance restrictions, turn handling, ceasefire) continues to
    work without changes.

    All other prelude spells (greed / enchantment) are executed right away so
    that their effects (draw cards, dump hands, etc.) are applied before the
    first turn.
    """
    spell = ActiveSpell(
        game_id=game.id,
        player_id=player.id,
        spell_name=spell_name,
        spell_type=_SPELL_TYPE_MAP.get(spell_name, 'enchantment'),
        spell_family_name=spell_name,
        suit=game_figures[0].suit if game_figures else 'Hearts',
        target_figure_id=None,
        cast_round=1,
        is_active=True,
        is_pending=False,
        effect_data=spell_data,
    )
    db.session.add(spell)

    if spell_name in _BATTLE_MODIFIER_SPELLS:
        if not isinstance(game.battle_modifier, list):
            game.battle_modifier = []
        game.battle_modifier.append({'type': spell_name, 'caster_id': player.id})
    else:
        # Greed / enchantment prelude spells: execute immediately
        db.session.flush()
        from routes.spells import _execute_spell
        result = _execute_spell(spell, game, player)
        if result.get('error'):
            logger.warning(f'Prelude spell {spell_name} execution failed: {result}')


# ── POST /kingdom/conquer/start_battle ───────────────────────────────────────

@kingdom.route('/conquer/start_battle', methods=['POST'])
@require_token
def conquer_start_battle():
    """Start a conquer battle for a land.

    Expects JSON: { land_id }

    Creates a Game with mode='conquer', pre-populates figures and battle
    moves from the attacker's conquer config and the defender's defence
    config (or AI template for unowned lands).
    """
    from kingdom_service import check_land_config_deficit

    data = request.json
    land_id = data.get('land_id')

    if not land_id:
        return jsonify({'success': False, 'message': 'land_id is required'}), 400

    user = db.session.get(User, g.user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    land = db.session.get(Land, land_id)
    if not land:
        return jsonify({'success': False, 'message': 'Land not found'}), 404

    if land.owner_user_id == user.id:
        return jsonify({'success': False, 'message': 'Cannot conquer your own land'}), 400

    # Cooldown check
    if user.last_conquer_at:
        elapsed = (_utcnow() - user.last_conquer_at).total_seconds()
        if elapsed < config.CONQUER_COOLDOWN_SECONDS:
            remaining = int(config.CONQUER_COOLDOWN_SECONDS - elapsed)
            return jsonify({'success': False,
                            'message': f'Conquer on cooldown. {remaining}s remaining.'}), 400

    # Load attacker's conquer config
    atk_cfg = LandConfig.query.filter_by(
        user_id=user.id, config_type='conquer', land_id=land_id
    ).first()
    if not atk_cfg:
        return jsonify({'success': False, 'message': 'No conquer config found'}), 400

    atk_figures = LandConfigFigure.query.filter_by(config_id=atk_cfg.id).all()
    atk_moves = LandConfigBattleMove.query.filter_by(config_id=atk_cfg.id).all()

    if not atk_figures:
        return jsonify({'success': False, 'message': 'Conquer config has no figures'}), 400
    if not atk_moves:
        return jsonify({'success': False, 'message': 'Conquer config has no battle moves'}), 400

    # Validate attacker figures aren't ALL in deficit
    non_deficit_figures = [
        f for f in atk_figures
        if not check_land_config_deficit(f, atk_figures)
    ]
    if not non_deficit_figures:
        return jsonify({'success': False,
                        'message': 'All figures have resource deficit'}), 400

    # Determine defender
    is_ai_land = land.owner_user_id is None
    defender_user = None
    def_cfg = None
    template = None

    if is_ai_land:
        defender_user = _get_or_create_ai_user()
        # Load AI template
        templates = config.AI_DEFENCE_TEMPLATES.get(land.tier, [])
        tpl_idx = land.ai_template_index or 0
        if tpl_idx < len(templates):
            template = templates[tpl_idx]
        else:
            template = templates[0] if templates else None
        if not template:
            return jsonify({'success': False,
                            'message': 'No AI template available for this land'}), 400
    else:
        defender_user = db.session.get(User, land.owner_user_id)
        if not defender_user:
            return jsonify({'success': False, 'message': 'Defender not found'}), 400
        def_cfg = LandConfig.query.filter_by(
            user_id=defender_user.id, config_type='defence', land_id=land_id
        ).first()
        if not def_cfg:
            return jsonify({'success': False,
                            'message': 'Defender has no defence config'}), 400

    # ── Create the Game ──
    game = Game(
        mode='conquer',
        land_id=land_id,
        conquer_config_id=atk_cfg.id,
        defence_config_id=def_cfg.id if def_cfg else None,
        state='open',
        stake=0,
        current_round=1,
        ceasefire_active=False,
        battle_confirmed=False,
    )
    db.session.add(game)
    db.session.flush()

    # Create players
    atk_player = Player(user_id=user.id, game_id=game.id,
                        turns_left=1, points=0)
    def_player = Player(user_id=defender_user.id, game_id=game.id,
                        turns_left=1, points=0)
    db.session.add_all([atk_player, def_player])
    db.session.flush()

    # Set attacker as invader and turn player
    game.invader_player_id = atk_player.id
    game.turn_player_id = atk_player.id

    # ── Create deck (no dealing – figures are pre-built from collection) ──
    DeckManager.create_and_shuffle_deck(game)

    # ── Build attacker figures & moves ──
    atk_game_figures = _build_figures_from_config(atk_figures, atk_player, game)

    # Map config figure IDs -> game figure IDs for call_figure resolution
    cfg_fig_map = {}
    for cfg_fig, game_fig in zip(atk_figures, atk_game_figures):
        cfg_fig_map[cfg_fig.id] = game_fig.id

    _build_battle_moves_from_config(atk_moves, atk_player, game,
                                    config_figure_map=cfg_fig_map)

    # ── Build defender figures & moves ──
    if is_ai_land:
        def_game_figures = _build_figures_from_template(
            template['figures'], def_player, game)
        _build_battle_moves_from_template(
            template['battle_moves'], def_player, game,
            template_figures=template['figures'],
            game_figures=def_game_figures)

        # Set defender battle figure from template
        battle_fig_idx = template.get('battle_figure_index', 0)
        if battle_fig_idx < len(def_game_figures):
            game.defending_figure_id = def_game_figures[battle_fig_idx].id

        # ── AI prelude spell ──
        if template.get('prelude_spell_name'):
            _create_prelude_spell(game, def_player,
                                  template['prelude_spell_name'],
                                  template.get('prelude_spell_data'),
                                  def_game_figures)
        elif template.get('battle_modifier'):
            # Backward compat: old template battle_modifier
            mod = template['battle_modifier']
            game.battle_modifier = [mod] if isinstance(mod, dict) else mod

        # ── AI counter spell ──
        if template.get('counter_spell_name'):
            spell = ActiveSpell(
                game_id=game.id,
                player_id=def_player.id,
                spell_name=template['counter_spell_name'],
                spell_type=_SPELL_TYPE_MAP.get(
                    template['counter_spell_name'], 'enchantment'),
                spell_family_name=template['counter_spell_name'],
                suit=def_game_figures[0].suit if def_game_figures else 'Hearts',
                target_figure_id=None,
                cast_round=1,
                is_active=True,
                is_pending=False,
                effect_data=template.get('counter_spell_data'),
            )
            db.session.add(spell)
        elif template.get('spell'):
            # Backward compat: old template spell
            spell_data = template['spell']
            target_fig_id = None
            if spell_data.get('spell_target_figure_id') is not None:
                tgt_idx = spell_data['spell_target_figure_id']
                if isinstance(tgt_idx, int) and tgt_idx < len(def_game_figures):
                    target_fig_id = def_game_figures[tgt_idx].id
            spell = ActiveSpell(
                game_id=game.id,
                player_id=def_player.id,
                spell_name=spell_data.get('spell_name', ''),
                spell_type='enchantment',
                spell_family_name=spell_data.get('spell_name', ''),
                suit=def_game_figures[0].suit if def_game_figures else 'Hearts',
                target_figure_id=target_fig_id,
                cast_round=1,
                is_active=True,
                is_pending=False,
            )
            db.session.add(spell)

    else:
        def_config_figures = LandConfigFigure.query.filter_by(
            config_id=def_cfg.id).all()
        def_config_moves = LandConfigBattleMove.query.filter_by(
            config_id=def_cfg.id).all()

        def_game_figures = _build_figures_from_config(
            def_config_figures, def_player, game)

        def_cfg_fig_map = {}
        for cfg_fig, game_fig in zip(def_config_figures, def_game_figures):
            def_cfg_fig_map[cfg_fig.id] = game_fig.id

        _build_battle_moves_from_config(
            def_config_moves, def_player, game,
            config_figure_map=def_cfg_fig_map)

        # Set defender battle figure from config
        if def_cfg.battle_figure_id:
            mapped_id = def_cfg_fig_map.get(def_cfg.battle_figure_id)
            if mapped_id:
                game.defending_figure_id = mapped_id
        if def_cfg.battle_figure_id_2:
            mapped_id = def_cfg_fig_map.get(def_cfg.battle_figure_id_2)
            if mapped_id:
                game.defending_figure_id_2 = mapped_id

        # ── Fallback: pick strongest eligible figure when neither
        #    battle figure nor counter spell is configured (both turns
        #    empty → auto-advance with strongest figure) ──
        if (not game.defending_figure_id
                and not def_cfg.counter_spell_name
                and not def_cfg.spell_name
                and def_game_figures):
            game.defending_figure_id = _pick_strongest_figure(
                def_game_figures, game)

        # ── Defender prelude spell ──
        if def_cfg.prelude_spell_name:
            _create_prelude_spell(game, def_player,
                                  def_cfg.prelude_spell_name,
                                  def_cfg.prelude_spell_data,
                                  def_game_figures)
        elif def_cfg.battle_modifier:
            # Backward compat: old battle_modifier field
            mod = def_cfg.battle_modifier
            game.battle_modifier = [mod] if isinstance(mod, dict) else mod

        # ── Defender counter spell ──
        if def_cfg.counter_spell_name:
            target_fig_id = None
            if def_cfg.counter_spell_target_figure_id:
                target_fig_id = def_cfg_fig_map.get(
                    def_cfg.counter_spell_target_figure_id)
            spell = ActiveSpell(
                game_id=game.id,
                player_id=def_player.id,
                spell_name=def_cfg.counter_spell_name,
                spell_type=_SPELL_TYPE_MAP.get(
                    def_cfg.counter_spell_name, 'enchantment'),
                spell_family_name=def_cfg.counter_spell_name,
                suit=def_game_figures[0].suit if def_game_figures else 'Hearts',
                target_figure_id=target_fig_id,
                cast_round=1,
                is_active=True,
                is_pending=False,
                effect_data=def_cfg.counter_spell_data,
            )
            db.session.add(spell)
        elif def_cfg.spell_name:
            # Backward compat: old spell_name field
            target_fig_id = None
            if def_cfg.spell_target_figure_id:
                target_fig_id = def_cfg_fig_map.get(
                    def_cfg.spell_target_figure_id)
            spell = ActiveSpell(
                game_id=game.id,
                player_id=def_player.id,
                spell_name=def_cfg.spell_name,
                spell_type='enchantment',
                spell_family_name=def_cfg.spell_name,
                suit=def_game_figures[0].suit if def_game_figures else 'Hearts',
                target_figure_id=target_fig_id,
                cast_round=1,
                is_active=True,
                is_pending=False,
            )
            db.session.add(spell)

    # ── Attacker prelude spell ──
    if atk_cfg.prelude_spell_name:
        _create_prelude_spell(game, atk_player,
                              atk_cfg.prelude_spell_name,
                              atk_cfg.prelude_spell_data,
                              atk_game_figures)
    elif not game.battle_modifier and atk_cfg.battle_modifier:
        # Backward compat: old battle_modifier fallback
        mod = atk_cfg.battle_modifier
        game.battle_modifier = [mod] if isinstance(mod, dict) else mod

    # Set cooldown
    user.last_conquer_at = _utcnow()

    db.session.commit()

    logger.info(f"[CONQUER] Battle started: game={game.id} land={land_id} "
                f"attacker={user.username} defender={defender_user.username} "
                f"ai_land={is_ai_land}")

    return jsonify({
        'success': True,
        'game_id': game.id,
        'game': game.serialize(),
    })


# ── GET /kingdom/attack_notifications ────────────────────────────────────────

@kingdom.route('/attack_notifications', methods=['GET'])
@require_token
def attack_notifications():
    """Return unseen attack logs where the current user was the defender."""
    logs = LandAttackLog.query.filter_by(
        defender_user_id=g.user_id,
        seen_by_defender=False,
    ).order_by(LandAttackLog.timestamp.desc()).all()

    result = []
    for log in logs:
        land = db.session.get(Land, log.land_id)
        attacker = db.session.get(User, log.attacker_user_id)
        entry = log.serialize()
        entry['land_col'] = land.col if land else None
        entry['land_row'] = land.row if land else None
        entry['attacker_username'] = attacker.username if attacker else None
        result.append(entry)

    return jsonify({'success': True, 'notifications': result})


# ── POST /kingdom/attack_notifications/mark_seen ────────────────────────────

@kingdom.route('/attack_notifications/mark_seen', methods=['POST'])
@require_token
def attack_notifications_mark_seen():
    """Mark attack notifications as seen by the defender."""
    data = request.json or {}
    notification_ids = data.get('notification_ids', [])

    if not notification_ids or not isinstance(notification_ids, list):
        return jsonify({'success': False,
                        'message': 'notification_ids is required'}), 400

    updated = LandAttackLog.query.filter(
        LandAttackLog.id.in_(notification_ids),
        LandAttackLog.defender_user_id == g.user_id,
    ).update({'seen_by_defender': True}, synchronize_session='fetch')

    db.session.commit()

    return jsonify({'success': True, 'marked': updated})


# ── GET /kingdom/attack_history ──────────────────────────────────────────────

@kingdom.route('/attack_history', methods=['GET'])
@require_token
def attack_history():
    """Return paginated attack history for the current user (attacker or defender)."""
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 50)

    query = LandAttackLog.query.filter(
        db.or_(
            LandAttackLog.attacker_user_id == g.user_id,
            LandAttackLog.defender_user_id == g.user_id,
        )
    ).order_by(LandAttackLog.timestamp.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    results = []
    for log in pagination.items:
        land = db.session.get(Land, log.land_id)
        attacker = db.session.get(User, log.attacker_user_id)
        defender = db.session.get(User, log.defender_user_id) if log.defender_user_id else None
        entry = log.serialize()
        entry['land_col'] = land.col if land else None
        entry['land_row'] = land.row if land else None
        entry['attacker_username'] = attacker.username if attacker else None
        entry['defender_username'] = defender.username if defender else 'AI'
        results.append(entry)

    return jsonify({
        'success': True,
        'history': results,
        'page': pagination.page,
        'pages': pagination.pages,
        'total': pagination.total,
    })
