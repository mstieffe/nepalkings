# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Kingdom routes — gold production, land management."""

import math
import logging
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request, g

from models import db, User, Land, LandAttackLog, CollectionCard, LandConfig, LandConfigFigure, LandConfigBattleMove
from routes.auth import require_token
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

def _serialize_config_with_deficit(cfg):
    """Serialize a LandConfig and annotate each figure with has_deficit."""
    from kingdom_service import get_config_deficit_map
    data = cfg.serialize()
    deficit_map = get_config_deficit_map(cfg.id)
    for fig in data['figures']:
        fig['has_deficit'] = deficit_map.get(fig['id'], False)
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
    name = data.get('name')
    suit = data.get('suit')
    color = data.get('color')
    field = data.get('field')
    card_ids = data.get('card_ids', [])
    card_roles = data.get('card_roles', [])

    if not all([land_id, family_name, name, suit, color, field]):
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400

    if not card_ids:
        return jsonify({'success': False, 'message': 'No cards provided'}), 400

    if len(card_ids) != len(card_roles):
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
        name=name,
        suit=suit,
        color=color,
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

    if not all([land_id, family_name, card_id, suit, rank]) or round_index is None:
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400

    if round_index not in (0, 1, 2):
        return jsonify({'success': False, 'message': 'round_index must be 0, 1, or 2'}), 400

    # Verify card belongs to user and is unlocked
    card = CollectionCard.query.filter_by(
        id=card_id, user_id=g.user_id
    ).first()
    if not card:
        return jsonify({'success': False, 'message': 'Card not found'}), 404

    if card.locked:
        return jsonify({'success': False, 'message': 'Card is already locked'}), 400

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

    cfg.battle_modifier = {'type': modifier_type}
    cfg.modifier_card_ids = None  # Blitzkrieg has no card cost
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
