# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Kingdom routes — gold production, land management."""

import math
import logging
from datetime import datetime, timezone, timedelta
from flask import Blueprint, jsonify, request, g

from models import (db, User, Land, LandAttackLog, KingdomMessage,
                    KingdomNotification, KingdomLootEvent,
                    Kingdom as KingdomModel, KingdomCosmeticUnlock,
                    KingdomSkillAllocation,
                    CollectionCard,
                    LandConfig, LandConfigFigure, LandConfigBattleMove,
                    Game, Player, Figure, BattleMove, ConquerTactic,
                    CardToFigure, ActiveSpell,
                    MainCard, SideCard, Suit, MainRank, CardRole)
from routes.auth import require_token
from game_service.deck_manager import DeckManager
from ai.defence.generator import get_ai_defence_template_for_land
import server_settings as config

kingdom = Blueprint('kingdom', __name__)
logger = logging.getLogger('nepalkings.routes.kingdom')


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── Cosmetic / style helpers ────────────────────────────────────────────────

_COSMETIC_STYLE_FIELDS = {
    'badge': 'badge_key',
    'border': 'border_key',
    'surface': 'surface_key',
}


def _cosmetic_catalog():
    return getattr(config, 'KINGDOM_COSMETIC_CATALOG', {}) or {}


def _default_style_dict():
    return dict(getattr(config, 'KINGDOM_DEFAULT_STYLE', {}) or {
        'badge_key': 'badge_plain',
        'border_key': 'border_simple_gold',
        'surface_key': 'surface_plain',
    })


def _serialize_skill_definitions():
    """Return the static skill definition table as a JSON-friendly list."""
    out = []
    for sdef in (config.KINGDOM_SKILL_DEFINITIONS or ()):
        out.append({
            'key': sdef.key,
            'name': sdef.name,
            'description': sdef.description,
            'icon_path': sdef.icon_path,
            'max_level': sdef.max_level,
            'cost_multiplier': sdef.cost_multiplier,
            'effect_values': list(sdef.effect_values),
            'level_costs': [
                config.skill_cost_to_buy_level(sdef.key, lvl)
                for lvl in range(1, sdef.max_level + 1)
            ],
        })
    return out


def _booster_production_config_payload():
    """Static booster-production constants exposed to the client."""
    return {
        'main_booster': {
            'base_hours': config.KINGDOM_MAIN_BOOSTER_PRODUCTION_BASE_HOURS,
            'halving_factor': config.KINGDOM_MAIN_BOOSTER_PRODUCTION_HALVING_FACTOR,
            'capacity': config.KINGDOM_MAIN_BOOSTER_PRODUCTION_CAPACITY,
        },
        'side_booster': {
            'base_hours': config.KINGDOM_SIDE_BOOSTER_PRODUCTION_BASE_HOURS,
            'halving_factor': config.KINGDOM_SIDE_BOOSTER_PRODUCTION_HALVING_FACTOR,
            'capacity': config.KINGDOM_SIDE_BOOSTER_PRODUCTION_CAPACITY,
        },
        'map': {
            'base_hours': config.KINGDOM_MAP_PRODUCTION_BASE_HOURS,
            'halving_factor': config.KINGDOM_MAP_PRODUCTION_HALVING_FACTOR,
            'default_capacity': config.KINGDOM_ATLAS_DEFAULT_CAPACITY,
        },
    }


def _lock_user_for_spend(user_id):
    """Lock the User row before mutating gold to avoid lost-update races.

    On SQLite ``with_for_update`` is a no-op; on Postgres/MySQL it issues
    ``SELECT ... FOR UPDATE`` so concurrent gold spends serialize.
    """
    try:
        return User.query.with_for_update().filter_by(id=user_id).first()
    except Exception:
        db.session.rollback()
        return db.session.get(User, user_id)


# In-memory rate-limit window for per-user kingdom rename attempts.
_RENAME_ATTEMPTS = {}


def _check_rename_rate_limit(user_id):
    """Return True if this rename attempt is within the per-user hourly cap."""
    cap = int(getattr(config, 'KINGDOM_RENAME_RATE_LIMIT_PER_HOUR', 10) or 10)
    if cap <= 0:
        return True
    now = _utcnow()
    window_start = now - timedelta(hours=1)
    history = [t for t in _RENAME_ATTEMPTS.get(user_id, []) if t >= window_start]
    if len(history) >= cap:
        _RENAME_ATTEMPTS[user_id] = history
        return False
    history.append(now)
    _RENAME_ATTEMPTS[user_id] = history
    return True


# ── POST /kingdom/<id>/collect_gold|collect_production ─────────────────────

@kingdom.route('/<int:kingdom_id>/collect_gold', methods=['POST'])
@kingdom.route('/<int:kingdom_id>/collect_production', methods=['POST'])
@require_token
def collect_kingdom_production_route(kingdom_id):
    """Collect this kingdom's ready production into the user's account.

    Gold uses the vault cap; booster production stores at most one pending
    main/side pack per kingdom.  The legacy ``collect_gold`` path returns the
    same gold aliases while also including booster fields for updated clients.
    """
    user = _lock_user_for_spend(g.user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    from kingdom_service import (collect_kingdom_production,
                                 _normalize_collect_production_keys,
                                 reconcile_user_kingdoms,
                                 summarize_user_kingdom)

    reconcile_user_kingdoms(user.id, commit=False)
    db.session.flush()
    kingdom_row = db.session.get(KingdomModel, kingdom_id)
    if not kingdom_row or kingdom_row.owner_user_id != user.id:
        return jsonify({'error': 'Kingdom not found'}), 404

    data = request.json or {}
    requested_keys = None
    if 'item_keys' in data and data.get('item_keys') is not None:
        if not isinstance(data.get('item_keys'), list):
            return jsonify({'success': False, 'message': 'item_keys must be a list'}), 400
        requested_keys = data.get('item_keys') or []
    elif 'item_key' in data and data.get('item_key') is not None:
        requested_keys = [data.get('item_key')]

    normalized_keys = _normalize_collect_production_keys(requested_keys)
    if requested_keys is not None and requested_keys and not normalized_keys:
        return jsonify({'success': False, 'message': 'Unknown production item'}), 400

    result = collect_kingdom_production(
        kingdom_row, user, item_keys=requested_keys, now=_utcnow())
    db.session.commit()

    return jsonify({
        'success': True,
        'kingdom_id': kingdom_row.id,
        **result,
        'kingdom': summarize_user_kingdom(user.id, None),
    })


@kingdom.route('/collect_gold_all', methods=['POST'])
@kingdom.route('/collect_production_all', methods=['POST'])
@require_token
def collect_production_all_route():
    """Collect ready production from EVERY kingdom owned by the user.

    Returns one combined gold total plus booster totals and a per-kingdom
    breakdown so the client can stage floating-text animations.
    """
    user = _lock_user_for_spend(g.user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    from kingdom_service import (collect_kingdom_production,
                                 reconcile_user_kingdoms,
                                 summarize_user_kingdom)

    reconcile_user_kingdoms(user.id, commit=False)
    db.session.flush()
    now = _utcnow()
    breakdown = []
    total_gold = 0
    total_main = 0
    total_side = 0
    total_maps = 0
    cap_total = 0
    for k in KingdomModel.query.filter_by(owner_user_id=user.id).all():
        result = collect_kingdom_production(k, user, now=now)
        cap_total += int(result.get('vault_cap') or 0)
        collected_gold = int(result.get('collected_gold', result.get('collected') or 0) or 0)
        collected_main = int(result.get('collected_main_boosters') or 0)
        collected_side = int(result.get('collected_side_boosters') or 0)
        collected_maps = int(result.get('collected_maps') or 0)
        total_gold += collected_gold
        total_main += collected_main
        total_side += collected_side
        total_maps += collected_maps
        breakdown.append({
            'kingdom_id': k.id,
            'kingdom_name': k.name or f'Kingdom #{k.id}',
            'collected': collected_gold,
            'collected_gold': collected_gold,
            'collected_main_boosters': collected_main,
            'collected_side_boosters': collected_side,
            'collected_maps': collected_maps,
            'vault_cap': int(result.get('vault_cap') or 0),
            'production': result.get('production') or {},
        })
    db.session.commit()

    return jsonify({
        'success': True,
        'collected_total': total_gold,
        'collected_gold_total': total_gold,
        'collected_main_boosters_total': total_main,
        'collected_side_boosters_total': total_side,
        'collected_maps_total': total_maps,
        'vault_cap_total': cap_total,
        'gold': int(user.gold or 0),
        'total_gold': int(user.gold or 0),
        'booster_packs': int(user.booster_packs or 0),
        'booster_packs_side': int(user.booster_packs_side or 0),
        'maps': int(user.maps or 0),
        'kingdoms': breakdown,
        'kingdom': summarize_user_kingdom(user.id, None),
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


# ── Persistent kingdom configuration ───────────────────────────────────────

def _kingdom_config_or_404(kingdom_id):
    kingdom_row = db.session.get(KingdomModel, kingdom_id)
    if not kingdom_row or kingdom_row.owner_user_id != g.user_id:
        return None
    return kingdom_row


def _serialize_land_context(land):
    from kingdom_service import serialize_land_with_kingdom_context
    return serialize_land_with_kingdom_context(land)


def _kingdom_style_updates_from_payload(data):
    catalog = _cosmetic_catalog()
    updates = {}

    cosmetic_key = data.get('cosmetic_key')
    if cosmetic_key:
        item = catalog.get(cosmetic_key)
        if not item:
            raise ValueError('Unknown cosmetic')
        style_field = _COSMETIC_STYLE_FIELDS.get(item.get('type'))
        if not style_field:
            raise ValueError('Invalid cosmetic type')
        updates[style_field] = cosmetic_key

    for style_field in ('badge_key', 'border_key', 'surface_key'):
        key = data.get(style_field)
        if not key:
            continue
        item = catalog.get(key)
        expected_type = style_field.replace('_key', '')
        if not item:
            raise ValueError(f'Unknown cosmetic: {key}')
        if item.get('type') != expected_type:
            raise ValueError(f'{key} is not a {expected_type} cosmetic')
        updates[style_field] = key
    return updates


@kingdom.route('/config', methods=['GET'])
@require_token
def kingdom_config_list():
    """Return all persistent kingdoms owned by the current user."""
    from kingdom_service import reconcile_user_kingdoms, serialize_kingdom_config

    user = db.session.get(User, g.user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404

    kingdoms = reconcile_user_kingdoms(user.id, commit=False)
    db.session.commit()

    selected = None
    land_id = request.args.get('land_id', type=int)
    if land_id:
        land = db.session.get(Land, land_id)
        if land and land.owner_user_id == user.id and land.kingdom_id:
            selected = land.kingdom_id
    if selected is None and kingdoms:
        selected = kingdoms[0].id

    return jsonify({
        'success': True,
        'catalog': _cosmetic_catalog(),
        'default_style': _default_style_dict(),
        'skill_definitions': _serialize_skill_definitions(),
        'skill_base_cost_curve': list(config.KINGDOM_SKILL_BASE_COST_CURVE),
        'level_max': int(config.KINGDOM_LEVEL_MAX),
        'skill_points_per_level': int(config.KINGDOM_SKILL_POINTS_PER_LEVEL),
        'vault_default_cap': int(config.KINGDOM_VAULT_DEFAULT_CAP),
        'booster_production_config': _booster_production_config_payload(),
        'shield_options_hours': getattr(config, 'KINGDOM_SHIELD_DURATION_OPTIONS_HOURS', []),
        'shield_price_per_hour_per_land': getattr(config, 'KINGDOM_SHIELD_PRICE_PER_HOUR_PER_LAND', 0),
        'rename_price_gold': getattr(config, 'KINGDOM_RENAME_PRICE_GOLD', 0),
        'selected_kingdom_id': selected,
        'kingdoms': [serialize_kingdom_config(row) for row in kingdoms],
        'gold': user.gold,
    })


@kingdom.route('/config/<int:kingdom_id>', methods=['GET'])
@require_token
def kingdom_config_detail(kingdom_id):
    from kingdom_service import reconcile_user_kingdoms, serialize_kingdom_config

    reconcile_user_kingdoms(g.user_id, commit=False)
    kingdom_row = _kingdom_config_or_404(kingdom_id)
    if not kingdom_row:
        db.session.rollback()
        return jsonify({'success': False, 'message': 'Kingdom not found'}), 404
    db.session.commit()
    return jsonify({
        'success': True,
        'catalog': _cosmetic_catalog(),
        'skill_definitions': _serialize_skill_definitions(),
        'skill_base_cost_curve': list(config.KINGDOM_SKILL_BASE_COST_CURVE),
        'level_max': int(config.KINGDOM_LEVEL_MAX),
        'skill_points_per_level': int(config.KINGDOM_SKILL_POINTS_PER_LEVEL),
        'vault_default_cap': int(config.KINGDOM_VAULT_DEFAULT_CAP),
        'booster_production_config': _booster_production_config_payload(),
        'shield_options_hours': getattr(config, 'KINGDOM_SHIELD_DURATION_OPTIONS_HOURS', []),
        'rename_price_gold': getattr(config, 'KINGDOM_RENAME_PRICE_GOLD', 0),
        'kingdom': serialize_kingdom_config(kingdom_row),
        'gold': db.session.get(User, g.user_id).gold,
    })


@kingdom.route('/config/<int:kingdom_id>/loot/collect', methods=['POST'])
@require_token
def kingdom_config_loot_collect(kingdom_id):
    """Move pending looted cards from the inbox into the user's collection."""
    from kingdom_service import serialize_kingdom_config, serialize_loot_inbox

    kingdom_row = _kingdom_config_or_404(kingdom_id)
    if not kingdom_row:
        return jsonify({'success': False, 'message': 'Kingdom not found'}), 404

    data = request.json or {}
    event_ids = data.get('event_ids') or []
    query = KingdomLootEvent.query.filter_by(
        user_id=g.user_id,
        direction='gained',
        collected=False,
    )
    if event_ids:
        query = query.filter(KingdomLootEvent.id.in_(event_ids))
    events = query.order_by(KingdomLootEvent.created_at.asc(),
                            KingdomLootEvent.id.asc()).all()

    collected_cards = []
    for event in events:
        for card in event.cards or []:
            suit = card.get('suit')
            rank = card.get('rank')
            if not suit or not rank:
                continue
            new_card = CollectionCard(
                user_id=g.user_id,
                suit=suit,
                rank=rank,
                value=int(card.get('value') or 0),
                locked=False,
            )
            db.session.add(new_card)
            collected_cards.append({
                'suit': suit,
                'rank': rank,
                'value': int(card.get('value') or 0),
                'role': card.get('role'),
                'source': card.get('source'),
                'bucket': card.get('bucket'),
            })
        event.collected = True
        event.seen = True

    db.session.commit()
    return jsonify({
        'success': True,
        'collected_count': len(collected_cards),
        'collected_cards': collected_cards,
        'loot_inbox': serialize_loot_inbox(g.user_id, kingdom_id),
        'kingdom': serialize_kingdom_config(kingdom_row),
    })


@kingdom.route('/config/<int:kingdom_id>/loot/acknowledge', methods=['POST'])
@require_token
def kingdom_config_loot_acknowledge(kingdom_id):
    """Mark lost-loot rows as noticed in the kingdom loot inbox."""
    from kingdom_service import serialize_kingdom_config, serialize_loot_inbox

    kingdom_row = _kingdom_config_or_404(kingdom_id)
    if not kingdom_row:
        return jsonify({'success': False, 'message': 'Kingdom not found'}), 404

    data = request.json or {}
    event_ids = data.get('event_ids') or []
    query = KingdomLootEvent.query.filter_by(
        user_id=g.user_id,
        direction='lost',
        seen=False,
    )
    if event_ids:
        query = query.filter(KingdomLootEvent.id.in_(event_ids))
    events = query.all()
    for event in events:
        event.seen = True
    db.session.commit()
    return jsonify({
        'success': True,
        'acknowledged_count': len(events),
        'loot_inbox': serialize_loot_inbox(g.user_id, kingdom_id),
        'kingdom': serialize_kingdom_config(kingdom_row),
    })


@kingdom.route('/config/<int:kingdom_id>/rename', methods=['POST'])
@require_token
def kingdom_config_rename(kingdom_id):
    from kingdom_service import serialize_kingdom_config

    if not _check_rename_rate_limit(g.user_id):
        return jsonify({
            'success': False,
            'message': 'Too many rename attempts. Try again later.',
        }), 429

    kingdom_row = _kingdom_config_or_404(kingdom_id)
    user = _lock_user_for_spend(g.user_id)
    if not kingdom_row or not user:
        return jsonify({'success': False, 'message': 'Kingdom not found'}), 404

    data = request.json or {}
    raw_name = data.get('name')
    if not isinstance(raw_name, str):
        return jsonify({'success': False, 'message': 'Kingdom name is required'}), 400
    name = raw_name.strip()
    if any(ord(c) < 32 or ord(c) == 127 for c in name):
        return jsonify({'success': False,
                        'message': 'Kingdom name contains invalid characters'}), 400
    if len(name) < 2:
        return jsonify({'success': False,
                        'message': 'Kingdom name must be at least 2 characters'}), 400
    if len(name) > 40:
        return jsonify({'success': False, 'message': 'Kingdom name is too long'}), 400

    price = max(0, int(getattr(config, 'KINGDOM_RENAME_PRICE_GOLD', 0) or 0))
    if user.gold < price:
        return jsonify({'success': False, 'message': 'Not enough gold'}), 400

    user.gold -= price
    kingdom_row.name = name
    kingdom_row.updated_at = _utcnow()
    db.session.commit()

    return jsonify({
        'success': True,
        'kingdom': serialize_kingdom_config(kingdom_row),
        'gold': user.gold,
        'rename_price_gold': price,
    })


@kingdom.route('/config/<int:kingdom_id>/cosmetics/purchase', methods=['POST'])
@require_token
def kingdom_config_cosmetic_purchase(kingdom_id):
    from kingdom_service import kingdom_unlocked_cosmetics, serialize_kingdom_config

    data = request.json or {}
    cosmetic_key = data.get('cosmetic_key')
    catalog = _cosmetic_catalog()
    item = catalog.get(cosmetic_key)
    if not item:
        return jsonify({'success': False, 'message': 'Unknown cosmetic'}), 404

    kingdom_row = _kingdom_config_or_404(kingdom_id)
    user = _lock_user_for_spend(g.user_id)
    if not kingdom_row or not user:
        return jsonify({'success': False, 'message': 'Kingdom not found'}), 404

    unlocked = kingdom_unlocked_cosmetics(kingdom_row.id)
    if cosmetic_key in unlocked:
        return jsonify({
            'success': True,
            'already_unlocked': True,
            'kingdom': serialize_kingdom_config(kingdom_row),
            'gold': user.gold,
        })

    price = max(0, int(item.get('price_gold', 0) or 0))
    if user.gold < price:
        return jsonify({'success': False, 'message': 'Not enough gold'}), 400

    user.gold -= price
    db.session.add(KingdomCosmeticUnlock(
        kingdom_id=kingdom_row.id, cosmetic_key=cosmetic_key))
    style_field = _COSMETIC_STYLE_FIELDS.get(item.get('type'))
    if style_field:
        setattr(kingdom_row, style_field, cosmetic_key)
    kingdom_row.updated_at = _utcnow()
    db.session.commit()

    return jsonify({
        'success': True,
        'cosmetic_key': cosmetic_key,
        'kingdom': serialize_kingdom_config(kingdom_row),
        'gold': user.gold,
    })


@kingdom.route('/config/<int:kingdom_id>/cosmetics/equip', methods=['POST'])
@require_token
def kingdom_config_cosmetic_equip(kingdom_id):
    from kingdom_service import kingdom_unlocked_cosmetics, serialize_kingdom_config

    data = request.json or {}
    kingdom_row = _kingdom_config_or_404(kingdom_id)
    if not kingdom_row:
        return jsonify({'success': False, 'message': 'Kingdom not found'}), 404
    try:
        updates = _kingdom_style_updates_from_payload(data)
    except ValueError as err:
        return jsonify({'success': False, 'message': str(err)}), 400
    if not updates:
        return jsonify({'success': False, 'message': 'No cosmetics supplied'}), 400

    unlocked = kingdom_unlocked_cosmetics(kingdom_row.id)
    for cosmetic_key in updates.values():
        if cosmetic_key not in unlocked:
            return jsonify({'success': False, 'message': f'{cosmetic_key} is locked'}), 403

    for style_field, cosmetic_key in updates.items():
        setattr(kingdom_row, style_field, cosmetic_key)
    kingdom_row.updated_at = _utcnow()
    db.session.commit()

    return jsonify({
        'success': True,
        'kingdom': serialize_kingdom_config(kingdom_row),
    })


@kingdom.route('/config/<int:kingdom_id>/skills/upgrade', methods=['POST'])
@require_token
def kingdom_config_skill_upgrade(kingdom_id):
    """Spend SP to advance a skill by one level (skills are permanent)."""
    from kingdom_service import (kingdom_skill_allocations,
                                 kingdom_spent_skill_points,
                                 kingdom_total_skill_points,
                                 serialize_kingdom_config)

    data = request.json or {}
    skill_key = data.get('skill_key')
    sdef = config.skill_definition(skill_key)
    if not sdef:
        return jsonify({'success': False, 'message': 'Unknown skill'}), 404
    kingdom_row = _kingdom_config_or_404(kingdom_id)
    if not kingdom_row:
        return jsonify({'success': False, 'message': 'Kingdom not found'}), 404

    allocations = kingdom_skill_allocations(kingdom_row.id)
    allocation = allocations[skill_key]
    if allocation.level >= sdef.max_level:
        return jsonify({'success': False, 'message': 'Skill is already maxed'}), 400

    next_level = allocation.level + 1
    cost = config.skill_cost_to_buy_level(skill_key, next_level)
    granted = kingdom_total_skill_points(kingdom_row)
    spent = kingdom_spent_skill_points(kingdom_row.id)
    if spent + cost > granted:
        return jsonify({'success': False, 'message': 'Not enough skill points'}), 400

    old_level = int(allocation.level or 0)
    allocation.level = next_level
    now = _utcnow()
    allocation.last_upgraded_at = now
    if old_level <= 0 and skill_key == 'main_booster_production':
        kingdom_row.pending_main_boosters = 0
        kingdom_row.last_main_booster_collection_at = now
    elif old_level <= 0 and skill_key == 'side_booster_production':
        kingdom_row.pending_side_boosters = 0
        kingdom_row.last_side_booster_collection_at = now
    elif old_level <= 0 and skill_key == 'map_production':
        kingdom_row.pending_maps = 0
        kingdom_row.last_maps_collection_at = now
    kingdom_row.updated_at = now
    db.session.commit()

    return jsonify({
        'success': True,
        'kingdom': serialize_kingdom_config(kingdom_row),
    })


# Skill-reset endpoint removed: skills are permanent in the kingdom-levels
# rework.  Clients should no longer call POST /kingdom/config/<id>/skills/reset.


@kingdom.route('/config/<int:kingdom_id>/shield/quote', methods=['POST'])
@require_token
def kingdom_config_shield_quote(kingdom_id):
    from kingdom_service import shield_quote_for_kingdom

    kingdom_row = _kingdom_config_or_404(kingdom_id)
    if not kingdom_row:
        return jsonify({'success': False, 'message': 'Kingdom not found'}), 404
    data = request.json or {}
    try:
        quote = shield_quote_for_kingdom(kingdom_row, data.get('hours'))
    except (TypeError, ValueError) as err:
        return jsonify({'success': False, 'message': str(err) or 'Invalid shield duration'}), 400
    return jsonify({'success': True, 'quote': quote})


@kingdom.route('/config/<int:kingdom_id>/shield/purchase', methods=['POST'])
@require_token
def kingdom_config_shield_purchase(kingdom_id):
    from kingdom_service import shield_quote_for_kingdom, serialize_kingdom_config

    kingdom_row = _kingdom_config_or_404(kingdom_id)
    user = _lock_user_for_spend(g.user_id)
    if not kingdom_row or not user:
        return jsonify({'success': False, 'message': 'Kingdom not found'}), 404

    data = request.json or {}
    try:
        quote = shield_quote_for_kingdom(kingdom_row, data.get('hours'))
    except (TypeError, ValueError) as err:
        return jsonify({'success': False, 'message': str(err) or 'Invalid shield duration'}), 400

    if user.gold < quote['price_gold']:
        return jsonify({'success': False, 'message': 'Not enough gold'}), 400

    now = _utcnow()
    base_until = now
    if kingdom_row.shield_until and kingdom_row.shield_until > now:
        if not getattr(config, 'KINGDOM_SHIELD_EXTENSION_ENABLED', True):
            return jsonify({'success': False, 'message': 'Kingdom is already shielded'}), 400
        base_until = kingdom_row.shield_until
    new_until = base_until + timedelta(hours=quote['hours'])
    max_until = now + timedelta(hours=int(getattr(config, 'KINGDOM_SHIELD_MAX_HOURS', 24) or 24))
    if new_until > max_until:
        return jsonify({'success': False, 'message': 'Shield would exceed maximum duration'}), 400

    user.gold -= quote['price_gold']
    kingdom_row.shield_until = new_until
    kingdom_row.updated_at = now
    db.session.commit()

    return jsonify({
        'success': True,
        'quote': quote,
        'kingdom': serialize_kingdom_config(kingdom_row),
        'gold': user.gold,
    })


# ── GET /kingdom/map ────────────────────────────────────────────────────────

@kingdom.route('/map', methods=['GET'])
@require_token
def get_kingdom_map():
    """Return all lands with ownership info for the hex map.

    Response includes per-land data (tier, gold rate, suit bonus, owner)
    and aggregate stats for the requesting user.
    """
    from kingdom_service import (check_defence_incomplete, compute_owned_land_components,
                                 describe_kingdom_bonuses, effective_gold_rate_for_lands,
                                 kingdom_shield_block_reason, kingdom_skill_bonuses,
                                 reconcile_all_kingdoms, serialize_kingdom_config,
                                 summarize_user_kingdom)

    user = db.session.get(User, g.user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404

    reconcile_all_kingdoms(commit=True)
    lands = Land.query.order_by(Land.row, Land.col).all()
    kingdom_ids = {land.kingdom_id for land in lands if land.kingdom_id}
    kingdoms_by_id = {
        row.id: row for row in KingdomModel.query.filter(KingdomModel.id.in_(kingdom_ids)).all()
    } if kingdom_ids else {}
    component_info_by_land, _ = compute_owned_land_components(lands)
    my_kingdom = summarize_user_kingdom(user.id, lands)
    my_persistent_kingdoms = [
        serialize_kingdom_config(row)
        for row in sorted(kingdoms_by_id.values(), key=lambda k: k.id)
        if row.owner_user_id == user.id
    ]
    my_effective_gold_rate = effective_gold_rate_for_lands(
        [land for land in lands if land.owner_user_id == user.id])

    my_total_gold_rate = 0.0
    my_lands_count = 0
    lands_data = []

    for land in lands:
        is_mine = (land.owner_user_id == user.id)
        if is_mine:
            my_total_gold_rate += land.gold_rate
            my_lands_count += 1

        land_dict = land.serialize()
        land_dict.update(component_info_by_land.get(land.id, {
            'kingdom_component_id': None,
            'kingdom_component_size': 0,
            'kingdom_level': 0,
            'kingdom_tier_name': None,
            'kingdom_bonuses': {},
            'kingdom_raw_gold_rate': 0,
            'kingdom_effective_gold_rate': 0,
        }))
        persistent_kingdom = kingdoms_by_id.get(land.kingdom_id)
        shield_remaining = 0
        shield_reason = None
        if persistent_kingdom:
            shield_remaining, _shield_kingdom, shield_reason = kingdom_shield_block_reason(
                land, now=_utcnow())
        legacy_bonuses = dict(land_dict.get('kingdom_bonuses') or {})
        legacy_bonuses.update(kingdom_skill_bonuses(persistent_kingdom))
        land_dict['kingdom_id'] = land.kingdom_id
        land_dict['kingdom_name'] = (
            persistent_kingdom.name or f'Kingdom #{persistent_kingdom.id}'
            if persistent_kingdom else None
        )
        land_dict['kingdom_level'] = (
            int(persistent_kingdom.level or 1)
            if persistent_kingdom else int(land_dict.get('kingdom_level') or 0)
        )
        land_dict['kingdom_bonuses'] = legacy_bonuses
        land_dict['kingdom_skill_effects'] = describe_kingdom_bonuses(legacy_bonuses)
        land_dict['kingdom_shield_until'] = (
            persistent_kingdom.shield_until.isoformat()
            if persistent_kingdom and persistent_kingdom.shield_until else None
        )
        land_dict['kingdom_shield_remaining'] = shield_remaining
        land_dict['kingdom_shield_reason'] = shield_reason
        land_dict['kingdom_is_shielded'] = bool(shield_reason)
        if land.owner_user_id:
            land_dict['owner_style'] = (
                persistent_kingdom.serialize_style()
                if persistent_kingdom else _default_style_dict()
            )
        land_dict['is_mine'] = is_mine
        land_cooldown_remaining = 0
        if land.conquer_cooldown_until:
            land_cooldown_remaining = max(
                0,
                int((land.conquer_cooldown_until - _utcnow()).total_seconds()),
            )
        land_dict['conquer_cooldown_remaining'] = land_cooldown_remaining
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
        'my_effective_gold_rate': round(my_effective_gold_rate, 3),
        'my_lands_count': my_lands_count,
        'my_kingdom': my_kingdom,
        'my_kingdoms': my_persistent_kingdoms,
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
    'Fill up to 10':    ('10', 1, None),
    'Dump Cards':       ('7', 4, None),
    'Forced Deal':      ('4', 2, None),
    'Poison':           ('3', 2, 'black'),
    'Health Boost':     ('3', 2, 'red'),
    'All Seeing Eye':   ('9', 2, None),
    'Explosion':        ('6', 4, None),
    'Peasant War':      ('J', 2, None),
    'Civil War':        ('5', 2, None),
    'Blitzkrieg':       ('Q', 2, None),
    'Invader Swap':     ('A', 2, None),
}

_CONQUER_PRELUDE_SPELLS = frozenset({
    'Draw 2 MainCards', 'Fill up to 10', 'Dump Cards', 'Forced Deal',
    'Poison', 'Health Boost', 'All Seeing Eye', 'Explosion',
    'Peasant War', 'Civil War', 'Blitzkrieg',
    'Invader Swap',
})

_TARGETED_PRELUDE_SPELLS = frozenset({'Poison', 'Health Boost', 'Explosion'})

_DEFENCE_PRELUDE_SPELLS = frozenset({
    'Dump Cards', 'Forced Deal', 'Poison', 'Health Boost',
    'Explosion', 'Peasant War', 'Civil War',
})

_DEFENCE_COUNTER_SPELLS = frozenset({
    'Dump Cards', 'Forced Deal', 'Poison', 'Health Boost',
})

# Spells that must also be recorded in game.battle_modifier for existing
# game logic (advance restrictions, turn updates, ceasefire, etc.)
_BATTLE_MODIFIER_SPELLS = frozenset({'Peasant War', 'Civil War', 'Blitzkrieg'})

# ── Prelude effect_data keys ────────────────────────────────────────
# Centralised so future additions don't have to grep magic strings.
PRELUDE_KEY_ORIGIN          = 'prelude_origin'
PRELUDE_KEY_STATUS          = 'prelude_status'
PRELUDE_KEY_REQUIRES_TARGET = 'prelude_requires_target'
PRELUDE_KEY_PENDING_TARGET  = 'prelude_pending_target'
PRELUDE_KEY_VALID_TARGET_IDS = 'valid_target_ids'
PRELUDE_KEY_TARGET_SCOPE    = 'target_scope'

PRELUDE_STATUS_EXECUTED        = 'executed'
PRELUDE_STATUS_PENDING_TARGET  = 'pending_target'
PRELUDE_STATUS_NO_VALID_TARGET = 'no_valid_target'
PRELUDE_STATUS_FAILED          = 'failed'

# Keys cleared when transitioning out of the pending-target state.
_PRELUDE_PENDING_KEYS = (
    PRELUDE_KEY_PENDING_TARGET,
    PRELUDE_KEY_VALID_TARGET_IDS,
)


def _update_prelude_effect_data(spell, *, status=None, clear_pending=False, **updates):
    """Forward-compatible helper for mutating an ActiveSpell.effect_data dict.

    Always clones the existing dict so unknown keys from older / newer
    builds are preserved across writes.  Pass ``clear_pending=True`` to
    drop the pending-target sentinel keys.
    """
    data = dict(spell.effect_data or {}) if isinstance(spell.effect_data, dict) else {}
    if status is not None:
        data[PRELUDE_KEY_STATUS] = status
    if clear_pending:
        for key in _PRELUDE_PENDING_KEYS:
            data.pop(key, None)
    for key, value in updates.items():
        data[key] = value
    spell.effect_data = data
    return data

# Spell type classification used when creating ActiveSpell records at game
# creation time.  Matches the family types in spell_configs.
_SPELL_TYPE_MAP = {
    'Draw 2 MainCards': 'greed',
    'Fill up to 10':    'greed',
    'Dump Cards':       'greed',
    'Forced Deal':      'greed',
    'Poison':           'enchantment',
    'Health Boost':     'enchantment',
    'All Seeing Eye':   'enchantment',
    'Explosion':        'enchantment',
    'Peasant War':      'tactics',
    'Civil War':        'tactics',
    'Blitzkrieg':       'tactics',
    'Invader Swap':     'tactics',
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

    fig_by_id = {fig.get('id'): fig for fig in data.get('figures', [])}

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

    prelude_data = data.get('prelude_spell_data') or {}
    if isinstance(prelude_data, dict):
        prelude_target_id = prelude_data.get('target_figure_id')
        prelude_target = fig_by_id.get(prelude_target_id)
        if prelude_target:
            data['prelude_spell_target_figure'] = {
                'id': prelude_target.get('id'),
                'name': prelude_target.get('name'),
                'family_name': prelude_target.get('family_name'),
                'field': prelude_target.get('field'),
                'suit': prelude_target.get('suit'),
            }
        else:
            data['prelude_spell_target_figure'] = None
    else:
        data['prelude_spell_target_figure'] = None

    counter_target = fig_by_id.get(data.get('counter_spell_target_figure_id'))
    if counter_target:
        data['counter_spell_target_figure'] = {
            'id': counter_target.get('id'),
            'name': counter_target.get('name'),
            'family_name': counter_target.get('family_name'),
            'field': counter_target.get('field'),
            'suit': counter_target.get('suit'),
        }
    else:
        data['counter_spell_target_figure'] = None

    return data


def _coerce_int(value):
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _validate_config_own_spell_target(cfg, target_fig_id):
    """Validate a stored defence config target for own-target spells."""
    target_fig_id = _coerce_int(target_fig_id)
    if not target_fig_id:
        return None, 'Target figure is required'
    fig = db.session.get(LandConfigFigure, target_fig_id)
    if not fig or fig.config_id != cfg.id:
        return None, 'Target figure not in this config'
    if getattr(fig, 'checkmate', False):
        return None, 'Checkmate figures are immune to spells'
    return fig, None


def _config_counter_advance_error(fig, cfg, deficit_map=None, planned_modifiers=None):
    """Return why a defence-config figure cannot be a battle figure."""
    from game_service.figure_rule_helpers import (
        config_strategy_modifiers,
        explain_counter_advance_block,
        modifiers_require_village,
    )

    modifiers = (planned_modifiers if planned_modifiers is not None
                 else config_strategy_modifiers(cfg))
    deficit = bool((deficit_map or {}).get(getattr(fig, 'id', None), False))
    return explain_counter_advance_block(
        fig,
        require_village=modifiers_require_village(modifiers),
        deficit=deficit,
    )


def _config_figure_can_counter_advance(fig, cfg, deficit_map=None, planned_modifiers=None):
    return _config_counter_advance_error(
        fig,
        cfg,
        deficit_map=deficit_map,
        planned_modifiers=planned_modifiers,
    ) is None


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


def _unlock_collection_cards_for_ref(card_ids, lock_type, lock_ref_id):
    """Unlock only cards still owned by a specific config-row lock."""
    if not card_ids:
        return
    CollectionCard.query.filter(
        CollectionCard.id.in_(card_ids),
        CollectionCard.lock_type == lock_type,
        CollectionCard.lock_ref_id == lock_ref_id,
    ).update({
        CollectionCard.locked: False,
        CollectionCard.lock_type: None,
        CollectionCard.lock_ref_id: None,
    }, synchronize_session='fetch')


_CONFIG_STATUS_ACTIVE = 'active'
_CONFIG_STATUS_DRAFT = 'draft'
_CONFIG_STATUS_ARCHIVED = 'archived'


def _is_defence_draft_request():
    return '/defence/draft/' in request.path


def _defence_status_filter(status):
    if status == _CONFIG_STATUS_ACTIVE:
        # Treat legacy rows created before the status column existed as active.
        return db.or_(LandConfig.status == _CONFIG_STATUS_ACTIVE,
                      LandConfig.status.is_(None))
    return LandConfig.status == status


def _defence_config_query(user_id, land_id, status=_CONFIG_STATUS_ACTIVE):
    return LandConfig.query.filter(
        LandConfig.user_id == user_id,
        LandConfig.config_type == 'defence',
        LandConfig.land_id == land_id,
        _defence_status_filter(status),
    )


def _get_active_defence_config(user_id, land_id):
    return _defence_config_query(user_id, land_id, _CONFIG_STATUS_ACTIVE).first()


def _get_draft_defence_config(user_id, land_id):
    return _defence_config_query(user_id, land_id, _CONFIG_STATUS_DRAFT).first()


def _defence_lock_type(base_lock_type, status=None):
    if status is None:
        status = _CONFIG_STATUS_DRAFT if _is_defence_draft_request() else _CONFIG_STATUS_ACTIVE
    if status == _CONFIG_STATUS_DRAFT and base_lock_type.startswith('defence_'):
        return base_lock_type.replace('defence_', 'defence_draft_', 1)
    return base_lock_type


def _touch_config(cfg):
    cfg.version = int(cfg.version or 1) + 1
    cfg.updated_at = _utcnow()


def _is_defence_draft_dirty(cfg):
    return bool(cfg and cfg.status == _CONFIG_STATUS_DRAFT and int(cfg.version or 1) > 1)


def _copy_json(value, fallback=None):
    if value is None:
        return fallback
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, list):
        return list(value)
    return value


def _clone_defence_config_to_draft(active_cfg, user_id, land_id):
    """Create a draft config as an editable copy of the active defence."""
    draft = LandConfig(
        user_id=user_id,
        config_type='defence',
        status=_CONFIG_STATUS_DRAFT,
        base_config_id=active_cfg.id if active_cfg else None,
        land_id=land_id,
        battle_modifier=_copy_json(active_cfg.battle_modifier) if active_cfg else None,
        modifier_card_ids=_copy_json(active_cfg.modifier_card_ids) if active_cfg else None,
        spell_name=active_cfg.spell_name if active_cfg else None,
        spell_target_figure_id=None,
        spell_card_ids=_copy_json(active_cfg.spell_card_ids) if active_cfg else None,
        prelude_spell_name=active_cfg.prelude_spell_name if active_cfg else None,
        prelude_spell_data=_copy_json(active_cfg.prelude_spell_data) if active_cfg else None,
        prelude_spell_card_ids=_copy_json(active_cfg.prelude_spell_card_ids) if active_cfg else None,
        counter_spell_name=active_cfg.counter_spell_name if active_cfg else None,
        counter_spell_data=_copy_json(active_cfg.counter_spell_data) if active_cfg else None,
        counter_spell_card_ids=_copy_json(active_cfg.counter_spell_card_ids) if active_cfg else None,
        counter_spell_target_figure_id=None,
        auto_gamble=bool(active_cfg.auto_gamble) if active_cfg else False,
        auto_gamble_threshold=(active_cfg.auto_gamble_threshold
                               if active_cfg and active_cfg.auto_gamble_threshold is not None
                               else _AUTO_GAMBLE_THRESHOLD_DEFAULT),
        version=1,
    )
    db.session.add(draft)
    db.session.flush()

    fig_id_map = {}
    if active_cfg:
        for fig in active_cfg.figures:
            clone = LandConfigFigure(
                config_id=draft.id,
                family_name=fig.family_name,
                name=fig.name,
                suit=fig.suit,
                color=fig.color,
                field=fig.field,
                card_ids=_copy_json(fig.card_ids, []),
                card_roles=_copy_json(fig.card_roles, []),
                produces=_copy_json(fig.produces, {}),
                requires=_copy_json(fig.requires, {}),
                description=fig.description,
                upgrade_family_name=fig.upgrade_family_name,
                checkmate=fig.checkmate,
                cannot_be_blocked=fig.cannot_be_blocked,
                rest_after_attack=fig.rest_after_attack,
            )
            db.session.add(clone)
            db.session.flush()
            fig_id_map[fig.id] = clone.id

        for move in active_cfg.battle_moves:
            clone = LandConfigBattleMove(
                config_id=draft.id,
                family_name=move.family_name,
                card_id=move.card_id,
                suit=move.suit,
                rank=move.rank,
                value=move.value,
                round_index=move.round_index,
                call_figure_id=fig_id_map.get(move.call_figure_id),
            )
            db.session.add(clone)

        draft.battle_figure_id = fig_id_map.get(active_cfg.battle_figure_id)
        draft.battle_figure_id_2 = fig_id_map.get(active_cfg.battle_figure_id_2)
        draft.spell_target_figure_id = fig_id_map.get(active_cfg.spell_target_figure_id)
        draft.counter_spell_target_figure_id = fig_id_map.get(active_cfg.counter_spell_target_figure_id)

        if isinstance(draft.prelude_spell_data, dict):
            # Assign a fresh dict after remapping. SQLAlchemy's plain JSON
            # column does not reliably track in-place nested mutations.
            prelude_data = dict(draft.prelude_spell_data)
            old_target = prelude_data.get('target_figure_id')
            if old_target:
                mapped = fig_id_map.get(old_target)
                if mapped:
                    prelude_data['target_figure_id'] = mapped
                else:
                    prelude_data.pop('target_figure_id', None)
                draft.prelude_spell_data = prelude_data or None

    return draft


def _matching_draft_figure_id(active_cfg, draft, active_figure_id):
    """Find the draft clone of an active figure by stable figure attributes."""
    active_figure_id = _coerce_int(active_figure_id)
    if not active_cfg or not active_figure_id:
        return None
    active_fig = next((fig for fig in active_cfg.figures if fig.id == active_figure_id), None)
    if not active_fig:
        return None

    active_card_ids = tuple(active_fig.card_ids or [])
    for draft_fig in draft.figures:
        if (
            draft_fig.family_name == active_fig.family_name
            and draft_fig.name == active_fig.name
            and draft_fig.suit == active_fig.suit
            and draft_fig.field == active_fig.field
            and tuple(draft_fig.card_ids or []) == active_card_ids
        ):
            return draft_fig.id
    return None


def _repair_defence_draft_target_refs(draft):
    """Repair stale spell targets that still point at the base active config."""
    if not draft or draft.status != _CONFIG_STATUS_DRAFT:
        return
    active = (db.session.get(LandConfig, draft.base_config_id)
              if draft.base_config_id else _get_active_defence_config(draft.user_id, draft.land_id))
    if not active:
        return

    draft_figure_ids = {fig.id for fig in draft.figures}

    if isinstance(draft.prelude_spell_data, dict):
        prelude_data = dict(draft.prelude_spell_data)
        target_id = _coerce_int(prelude_data.get('target_figure_id'))
        if target_id and target_id not in draft_figure_ids:
            mapped = _matching_draft_figure_id(active, draft, target_id)
            if mapped:
                prelude_data['target_figure_id'] = mapped
            else:
                prelude_data.pop('target_figure_id', None)
            draft.prelude_spell_data = prelude_data or None

    counter_target_id = _coerce_int(draft.counter_spell_target_figure_id)
    if counter_target_id and counter_target_id not in draft_figure_ids:
        draft.counter_spell_target_figure_id = _matching_draft_figure_id(
            active, draft, counter_target_id)


def _get_or_create_defence_draft(user_id, land_id):
    draft = _get_draft_defence_config(user_id, land_id)
    if draft:
        _repair_defence_draft_target_refs(draft)
        return draft
    active = _get_active_defence_config(user_id, land_id)
    draft = _clone_defence_config_to_draft(active, user_id, land_id)
    _repair_defence_draft_target_refs(draft)
    return draft


def _get_defence_edit_config(user_id, land_id):
    if _is_defence_draft_request():
        return _get_or_create_defence_draft(user_id, land_id)
    return _get_or_create_defence_config(user_id, land_id)


def _serialize_defence_edit_config(cfg):
    data = _serialize_config_with_deficit(cfg)
    data['draft_dirty'] = _is_defence_draft_dirty(cfg)
    return data


def _collect_config_card_ids(cfg):
    card_ids = set()
    if not cfg:
        return card_ids
    for fig in cfg.figures:
        card_ids.update(fig.card_ids or [])
    for move in cfg.battle_moves:
        if move.card_id:
            card_ids.add(move.card_id)
    card_ids.update(cfg.modifier_card_ids or [])
    card_ids.update(cfg.spell_card_ids or [])
    card_ids.update(cfg.prelude_spell_card_ids or [])
    card_ids.update(cfg.counter_spell_card_ids or [])
    return card_ids


def _iter_config_card_locks(cfg, status=_CONFIG_STATUS_ACTIVE):
    if not cfg:
        return
    for fig in cfg.figures:
        yield fig.card_ids or [], _defence_lock_type('defence_figure', status), fig.id
    for move in cfg.battle_moves:
        if move.card_id:
            yield [move.card_id], _defence_lock_type('defence_move', status), move.id
    if cfg.modifier_card_ids:
        yield cfg.modifier_card_ids, _defence_lock_type('defence_modifier', status), cfg.id
    if cfg.spell_card_ids:
        yield cfg.spell_card_ids, _defence_lock_type('defence_spell', status), cfg.id
    if cfg.prelude_spell_card_ids:
        yield cfg.prelude_spell_card_ids, _defence_lock_type('defence_prelude', status), cfg.id
    if cfg.counter_spell_card_ids:
        yield cfg.counter_spell_card_ids, _defence_lock_type('defence_counter', status), cfg.id


def _get_defence_config_problems(cfg):
    """Return detailed validation errors for a defence config."""
    problems = []
    if not cfg:
        return ['Configuration not loaded.']

    from kingdom_service import get_config_deficit_map
    figures = list(cfg.figures)
    moves = list(cfg.battle_moves)
    prelude = cfg.prelude_spell_name
    modifier_type = (
        (cfg.battle_modifier or {}).get('type')
        if isinstance(cfg.battle_modifier, dict) else None
    )
    village_only_name = (
        prelude if prelude in ('Peasant War', 'Civil War') else modifier_type
    )
    village_only = village_only_name in ('Peasant War', 'Civil War')
    deficit_map = get_config_deficit_map(cfg.id)

    if not figures:
        problems.append('No figures on the field.')
    else:
        can_fight = [fig for fig in figures if not deficit_map.get(fig.id, False)]
        if not can_fight:
            problems.append('All figures have a resource deficit.')
        elif village_only and not any(fig.field == 'village' for fig in can_fight):
            problems.append(
                f'{village_only_name} is selected — only village figures can fight, '
                'but none of your village figures are available.'
            )

    if len(moves) < 3:
        missing = 3 - len(moves)
        problems.append(f'{missing} battle move{"s" if missing > 1 else ""} still missing (need 3).')

    has_battle_fig = cfg.battle_figure_id is not None
    has_counter_spell = cfg.counter_spell_name is not None
    if has_battle_fig and has_counter_spell:
        problems.append('Select exactly one strategy: battle figure or counter spell (not both).')
    elif not has_battle_fig and not has_counter_spell:
        problems.append('Select exactly one strategy: battle figure or counter spell.')

    figure_ids = {fig.id for fig in figures}
    figures_by_id = {fig.id: fig for fig in figures}
    if has_battle_fig and cfg.battle_figure_id not in figure_ids:
        problems.append('Selected battle figure is no longer in this configuration.')
    elif has_battle_fig:
        err = _config_counter_advance_error(
            figures_by_id.get(cfg.battle_figure_id),
            cfg,
            deficit_map=deficit_map,
        )
        if err:
            problems.append(err)

    is_civil_war = (
        prelude == 'Civil War'
        or (isinstance(cfg.battle_modifier, dict)
            and cfg.battle_modifier.get('type') == 'Civil War')
    )
    if has_battle_fig and is_civil_war:
        if not cfg.battle_figure_id_2:
            problems.append('Civil War requires two battle figures.')
        elif cfg.battle_figure_id_2 not in figure_ids:
            problems.append('Second battle figure is no longer in this configuration.')
        elif cfg.battle_figure_id_2 == cfg.battle_figure_id:
            problems.append('Civil War requires two different battle figures.')
        else:
            fig1 = figures_by_id.get(cfg.battle_figure_id)
            fig2 = figures_by_id.get(cfg.battle_figure_id_2)
            err = _config_counter_advance_error(fig2, cfg, deficit_map=deficit_map)
            if err:
                problems.append(f'Second battle figure: {err}')
            if fig1 and fig2 and fig1.color != fig2.color:
                problems.append('Civil War: both battle figures must be the same color.')
    elif cfg.battle_figure_id_2:
        problems.append('Second battle figure is only valid with Civil War.')

    prelude_data = cfg.prelude_spell_data if isinstance(cfg.prelude_spell_data, dict) else {}
    if prelude == 'Health Boost':
        target_id = prelude_data.get('target_figure_id')
        if not target_id or target_id not in figure_ids:
            problems.append('Health Boost prelude needs one of your figures as target.')
    if cfg.counter_spell_name == 'Health Boost':
        target_id = cfg.counter_spell_target_figure_id
        if not target_id or target_id not in figure_ids:
            problems.append('Health Boost counter spell needs one of your figures as target.')

    return problems


def _promote_defence_draft(draft):
    """Promote a valid draft to the active defence config."""
    active = _get_active_defence_config(draft.user_id, draft.land_id)
    active_card_ids = _collect_config_card_ids(active)
    draft_card_ids = _collect_config_card_ids(draft)

    if active and active.id != draft.id:
        active.status = _CONFIG_STATUS_ARCHIVED
        active.version = int(active.version or 1) + 1
        active.updated_at = _utcnow()

    removed_ids = list(active_card_ids - draft_card_ids)
    _unlock_collection_cards(removed_ids)

    draft.status = _CONFIG_STATUS_ACTIVE
    draft.base_config_id = None
    draft.version = int(draft.version or 1) + 1
    draft.updated_at = _utcnow()

    for card_ids, lock_type, lock_ref_id in _iter_config_card_locks(draft, _CONFIG_STATUS_ACTIVE):
        _lock_collection_cards(card_ids, lock_type, lock_ref_id)

    land = db.session.get(Land, draft.land_id)
    if land:
        land.defence_config_id = draft.id

    return draft


def _get_or_create_conquer_config(user_id, land_id):
    """Get the user's active conquer config for a land, or create one.

    Safety net: if the existing cfg is still attached to a finished conquer
    Game whose card consumption / loot transfer never ran (e.g. attacker
    disconnected before finish_battle_pick_card), resolve that game lazily
    here.  After resolution the cfg row has been destroyed by
    ``_resolve_conquer_battle``, so we re-query and create a fresh one.
    """
    cfg = LandConfig.query.filter_by(
        user_id=user_id, config_type='conquer', land_id=land_id
    ).first()
    if cfg is not None:
        stale_game = Game.query.filter_by(
            conquer_config_id=cfg.id, state='finished'
        ).order_by(Game.id.desc()).first()
        if stale_game is not None:
            try:
                from routes.games import _resolve_conquer_battle
                winner_player = None
                if stale_game.winner_player_id:
                    winner_player = db.session.get(Player, stale_game.winner_player_id)
                if winner_player is None:
                    # Default to the defender (attacker abandoned / no winner)
                    other_players = [p for p in stale_game.players
                                     if p.user_id != user_id]
                    winner_player = other_players[0] if other_players else None
                if winner_player is not None:
                    _resolve_conquer_battle(stale_game, winner_player, winner_player)
                    db.session.commit()
                    logger.info(
                        "[CONQUER_REENTRY] resolved stale game %s for user %s land %s",
                        stale_game.id, user_id, land_id,
                    )
            except Exception:
                logger.exception(
                    "[CONQUER_REENTRY] failed to resolve stale game for user %s land %s",
                    user_id, land_id,
                )
            # Cfg may have been destroyed; re-query.
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
        'land': _serialize_land_context(land),
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

    if len(set(card_ids)) != len(card_ids):
        return jsonify({'success': False, 'message': 'Duplicate card ids in request'}), 400

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

_AUTO_GAMBLE_THRESHOLD_DEFAULT = 10
_AUTO_GAMBLE_THRESHOLD_MIN = 1
_AUTO_GAMBLE_THRESHOLD_MAX = 20


def _normalize_auto_gamble_threshold(value):
    """Coerce auto-gamble threshold to a safe integer range."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = _AUTO_GAMBLE_THRESHOLD_DEFAULT

    if parsed < _AUTO_GAMBLE_THRESHOLD_MIN:
        return _AUTO_GAMBLE_THRESHOLD_MIN
    if parsed > _AUTO_GAMBLE_THRESHOLD_MAX:
        return _AUTO_GAMBLE_THRESHOLD_MAX
    return parsed


def _get_or_create_defence_config(user_id, land_id):
    """Get the user's active defence config for a land, or create one."""
    cfg = _get_active_defence_config(user_id, land_id)
    if not cfg:
        cfg = LandConfig(
            user_id=user_id,
            config_type='defence',
            status=_CONFIG_STATUS_ACTIVE,
            land_id=land_id,
            auto_gamble_threshold=_AUTO_GAMBLE_THRESHOLD_DEFAULT,
        )
        db.session.add(cfg)
        db.session.flush()
    elif not cfg.status:
        cfg.status = _CONFIG_STATUS_ACTIVE
    if cfg.auto_gamble_threshold is None:
        cfg.auto_gamble_threshold = _AUTO_GAMBLE_THRESHOLD_DEFAULT
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
        'land': _serialize_land_context(land),
    })


# ── Defence draft lifecycle ────────────────────────────────────────────────

@kingdom.route('/defence/draft/open', methods=['POST'])
@require_token
def defence_draft_open():
    """Open an editable defence draft, cloning active defence if needed."""
    land_id = (request.json or {}).get('land_id')
    if land_id is None:
        return jsonify({'error': 'land_id is required'}), 400

    land, err = _validate_land_ownership(land_id, g.user_id)
    if err:
        return err

    draft = _get_or_create_defence_draft(g.user_id, land_id)
    db.session.commit()
    return jsonify({
        'success': True,
        'config': _serialize_defence_edit_config(draft),
        'land': _serialize_land_context(land),
        'dirty': _is_defence_draft_dirty(draft),
    })


@kingdom.route('/defence/draft/config', methods=['GET'])
@require_token
def get_defence_draft_config():
    """Return the current editable defence draft for an owned land."""
    land_id = request.args.get('land_id', type=int)
    if land_id is None:
        return jsonify({'error': 'land_id is required'}), 400

    land, err = _validate_land_ownership(land_id, g.user_id)
    if err:
        return err

    draft = _get_or_create_defence_draft(g.user_id, land_id)
    db.session.commit()
    return jsonify({
        'success': True,
        'config': _serialize_defence_edit_config(draft),
        'land': _serialize_land_context(land),
        'dirty': _is_defence_draft_dirty(draft),
    })


@kingdom.route('/defence/draft/validate', methods=['POST'])
@require_token
def defence_draft_validate():
    """Validate the editable defence draft and return detailed problems."""
    land_id = (request.json or {}).get('land_id')
    if land_id is None:
        return jsonify({'error': 'land_id is required'}), 400

    land, err = _validate_land_ownership(land_id, g.user_id)
    if err:
        return err

    draft = _get_or_create_defence_draft(g.user_id, land_id)
    problems = _get_defence_config_problems(draft)
    db.session.commit()
    return jsonify({
        'success': not problems,
        'valid': not problems,
        'problems': problems,
        'config': _serialize_defence_edit_config(draft),
        'land': _serialize_land_context(land),
        'dirty': _is_defence_draft_dirty(draft),
    })


@kingdom.route('/defence/draft/save', methods=['POST'])
@require_token
def defence_draft_save():
    """Promote a valid draft to the active defence config."""
    land_id = (request.json or {}).get('land_id')
    if land_id is None:
        return jsonify({'error': 'land_id is required'}), 400

    land, err = _validate_land_ownership(land_id, g.user_id)
    if err:
        return err

    draft = _get_draft_defence_config(g.user_id, land_id)
    if not draft:
        return jsonify({'success': False, 'message': 'No defence draft found'}), 404

    problems = _get_defence_config_problems(draft)
    if problems:
        return jsonify({'success': False, 'valid': False, 'problems': problems,
                        'message': 'Defence draft is incomplete'}), 400

    active = _promote_defence_draft(draft)
    db.session.commit()
    return jsonify({
        'success': True,
        'valid': True,
        'config': _serialize_defence_edit_config(active),
        'land': _serialize_land_context(land),
    })


@kingdom.route('/defence/draft/discard', methods=['POST'])
@require_token
def defence_draft_discard():
    """Delete only the editable draft and unlock draft-only cards."""
    land_id = (request.json or {}).get('land_id')
    if land_id is None:
        return jsonify({'error': 'land_id is required'}), 400

    land, err = _validate_land_ownership(land_id, g.user_id)
    if err:
        return err

    draft = _get_draft_defence_config(g.user_id, land_id)
    if draft:
        for card_ids, lock_type, lock_ref_id in _iter_config_card_locks(draft, _CONFIG_STATUS_DRAFT):
            _unlock_collection_cards_for_ref(card_ids, lock_type, lock_ref_id)
        LandConfigBattleMove.query.filter_by(config_id=draft.id).delete()
        LandConfigFigure.query.filter_by(config_id=draft.id).delete()
        db.session.delete(draft)
        db.session.flush()

    active = _get_active_defence_config(g.user_id, land_id)
    db.session.commit()
    payload = {
        'success': True,
        'land': _serialize_land_context(land),
        'dirty': False,
    }
    if active:
        payload['config'] = _serialize_defence_edit_config(active)
    return jsonify(payload)


@kingdom.route('/defence/clear_active', methods=['POST'])
@require_token
def defence_clear_active():
    """Explicitly clear the saved active defence config for a land."""
    land_id = (request.json or {}).get('land_id')
    if land_id is None:
        return jsonify({'error': 'land_id is required'}), 400

    land, err = _validate_land_ownership(land_id, g.user_id)
    if err:
        return err

    draft = _get_draft_defence_config(g.user_id, land_id)
    if draft:
        for card_ids, lock_type, lock_ref_id in _iter_config_card_locks(draft, _CONFIG_STATUS_DRAFT):
            _unlock_collection_cards_for_ref(card_ids, lock_type, lock_ref_id)
        LandConfigBattleMove.query.filter_by(config_id=draft.id).delete()
        LandConfigFigure.query.filter_by(config_id=draft.id).delete()
        db.session.delete(draft)

    active = _get_active_defence_config(g.user_id, land_id)
    if active:
        _wipe_config(active)
        if land.defence_config_id == active.id:
            land.defence_config_id = None
    db.session.commit()
    return jsonify({'success': True, 'land': _serialize_land_context(land)})


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

    cfg = _get_active_defence_config(g.user_id, land_id)
    if cfg:
        _wipe_config(cfg)
        if land.defence_config_id == cfg.id:
            land.defence_config_id = None
        db.session.commit()

    return jsonify({'success': True})


# ── POST /kingdom/defence/build_figure ───────────────────────────────────────

@kingdom.route('/defence/build_figure', methods=['POST'])
@kingdom.route('/defence/draft/build_figure', methods=['POST'])
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
    if len(set(card_ids)) != len(card_ids):
        return jsonify({'success': False, 'message': 'Duplicate card ids in request'}), 400
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

    cfg = _get_defence_edit_config(g.user_id, land_id)

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
    _lock_collection_cards(card_ids, _defence_lock_type('defence_figure'), figure.id)
    if _is_defence_draft_request():
        _touch_config(cfg)
    db.session.commit()

    return jsonify({'success': True, 'config': _serialize_defence_edit_config(cfg)})


# ── POST /kingdom/defence/remove_figure ──────────────────────────────────────

@kingdom.route('/defence/remove_figure', methods=['POST'])
@kingdom.route('/defence/draft/remove_figure', methods=['POST'])
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
    if _is_defence_draft_request() and cfg.status != _CONFIG_STATUS_DRAFT:
        return jsonify({'success': False, 'message': 'Not a defence draft'}), 400
    if not _is_defence_draft_request() and cfg.status == _CONFIG_STATUS_DRAFT:
        return jsonify({'success': False, 'message': 'Draft figure requires draft endpoint'}), 400

    # Clear battle figure references
    if cfg.battle_figure_id == figure.id:
        cfg.battle_figure_id = None
    if cfg.battle_figure_id_2 == figure.id:
        cfg.battle_figure_id_2 = None
    if cfg.counter_spell_target_figure_id == figure.id:
        cfg.counter_spell_target_figure_id = None
    if cfg.spell_target_figure_id == figure.id:
        cfg.spell_target_figure_id = None
    prelude_data = dict(cfg.prelude_spell_data or {}) if isinstance(cfg.prelude_spell_data, dict) else {}
    if prelude_data.get('target_figure_id') == figure.id:
        prelude_data.pop('target_figure_id', None)
        cfg.prelude_spell_data = prelude_data or None

    if _is_defence_draft_request():
        _unlock_collection_cards_for_ref(
            figure.card_ids or [], _defence_lock_type('defence_figure'), figure.id)
    else:
        _unlock_collection_cards(figure.card_ids or [])

    for move in list(cfg.battle_moves):
        if move.call_figure_id == figure.id:
            move.call_figure_id = None

    db.session.delete(figure)
    if _is_defence_draft_request():
        _touch_config(cfg)
    db.session.commit()

    return jsonify({'success': True, 'config': _serialize_defence_edit_config(cfg)})


# ── POST /kingdom/defence/buy_battle_move ────────────────────────────────────

@kingdom.route('/defence/buy_battle_move', methods=['POST'])
@kingdom.route('/defence/draft/buy_battle_move', methods=['POST'])
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

    cfg = _get_defence_edit_config(g.user_id, land_id)

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
    _lock_collection_cards([card_id], _defence_lock_type('defence_move'), move.id)
    if _is_defence_draft_request():
        _touch_config(cfg)
    db.session.commit()

    return jsonify({'success': True, 'config': _serialize_defence_edit_config(cfg)})


# ── POST /kingdom/defence/return_battle_move ─────────────────────────────────

@kingdom.route('/defence/return_battle_move', methods=['POST'])
@kingdom.route('/defence/draft/return_battle_move', methods=['POST'])
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
    if _is_defence_draft_request() and cfg.status != _CONFIG_STATUS_DRAFT:
        return jsonify({'success': False, 'message': 'Not a defence draft'}), 400
    if not _is_defence_draft_request() and cfg.status == _CONFIG_STATUS_DRAFT:
        return jsonify({'success': False, 'message': 'Draft move requires draft endpoint'}), 400

    if _is_defence_draft_request():
        _unlock_collection_cards_for_ref(
            [move.card_id], _defence_lock_type('defence_move'), move.id)
    else:
        _unlock_collection_cards([move.card_id])
    db.session.delete(move)
    if _is_defence_draft_request():
        _touch_config(cfg)
    db.session.commit()

    return jsonify({'success': True, 'config': _serialize_defence_edit_config(cfg)})


# ── POST /kingdom/defence/set_modifier ───────────────────────────────────────

@kingdom.route('/defence/set_modifier', methods=['POST'])
@kingdom.route('/defence/draft/set_modifier', methods=['POST'])
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

    cfg = _get_defence_edit_config(g.user_id, land_id)

    if cfg.modifier_card_ids:
        if _is_defence_draft_request():
            _unlock_collection_cards_for_ref(
                cfg.modifier_card_ids,
                _defence_lock_type('defence_modifier'),
                cfg.id,
            )
        else:
            _unlock_collection_cards(cfg.modifier_card_ids)

    # Find required free cards for this modifier
    req = _MODIFIER_CARD_REQS.get(modifier_type)
    if req:
        rank, count, color = req
        card_ids = _find_free_cards(g.user_id, rank, count, color)
        if card_ids is None:
            return jsonify({'success': False,
                            'message': f'{modifier_type} requires {count}× rank {rank} same-color free cards'}), 400
        _lock_collection_cards(card_ids, _defence_lock_type('defence_modifier'), cfg.id)
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

    if _is_defence_draft_request():
        _touch_config(cfg)
    db.session.commit()
    return jsonify({'success': True, 'config': _serialize_defence_edit_config(cfg)})


# ── POST /kingdom/defence/remove_modifier ────────────────────────────────────

@kingdom.route('/defence/remove_modifier', methods=['POST'])
@kingdom.route('/defence/draft/remove_modifier', methods=['POST'])
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

    cfg = (_get_draft_defence_config(g.user_id, land_id)
           if _is_defence_draft_request()
           else _get_active_defence_config(g.user_id, land_id))
    if not cfg:
        return jsonify({'success': False, 'message': 'No defence config found'}), 404

    if cfg.modifier_card_ids:
        if _is_defence_draft_request():
            _unlock_collection_cards_for_ref(
                cfg.modifier_card_ids,
                _defence_lock_type('defence_modifier'),
                cfg.id,
            )
        else:
            _unlock_collection_cards(cfg.modifier_card_ids)

    cfg.battle_modifier = None
    cfg.modifier_card_ids = None
    cfg.battle_figure_id_2 = None  # second fig only relevant for civil war
    if _is_defence_draft_request():
        _touch_config(cfg)
    db.session.commit()

    return jsonify({'success': True, 'config': _serialize_defence_edit_config(cfg)})


# ── POST /kingdom/defence/set_prelude_spell ──────────────────────────────────

@kingdom.route('/defence/set_prelude_spell', methods=['POST'])
@kingdom.route('/defence/draft/set_prelude_spell', methods=['POST'])
@require_token
def defence_set_prelude_spell():
    """Set a prelude spell for a defence config.

    Expects JSON: { land_id, spell_name, spell_data: {}|null, target_figure_id?: int }
    """
    data = request.json
    land_id = data.get('land_id')
    spell_name = data.get('spell_name')
    spell_data = data.get('spell_data')
    target_fig_id = data.get('target_figure_id')

    if not land_id or not spell_name:
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400

    if spell_name not in _DEFENCE_PRELUDE_SPELLS:
        return jsonify({'success': False,
                        'message': f'Spell "{spell_name}" is not allowed as defence prelude'}), 400

    land, err = _validate_land_ownership(land_id, g.user_id)
    if err:
        return err

    cfg = _get_defence_edit_config(g.user_id, land_id)

    normalized_spell_data = dict(spell_data or {}) if isinstance(spell_data, dict) else {}
    if target_fig_id is None:
        target_fig_id = normalized_spell_data.get('target_figure_id')

    if spell_name == 'Health Boost':
        target_fig_id = _coerce_int(target_fig_id)
        if target_fig_id:
            fig, err_msg = _validate_config_own_spell_target(cfg, target_fig_id)
            if err_msg:
                return jsonify({'success': False, 'message': err_msg}), 400
            normalized_spell_data['target_figure_id'] = fig.id
        else:
            normalized_spell_data.pop('target_figure_id', None)
    else:
        normalized_spell_data.pop('target_figure_id', None)

    # Unlock previous prelude spell cards
    if cfg.prelude_spell_card_ids:
        if _is_defence_draft_request():
            _unlock_collection_cards_for_ref(
                cfg.prelude_spell_card_ids,
                _defence_lock_type('defence_prelude'),
                cfg.id,
            )
        else:
            _unlock_collection_cards(cfg.prelude_spell_card_ids)

    # Find required free cards
    req = _SPELL_CARD_COST.get(spell_name)
    if req:
        rank, count, color = req
        card_ids = _find_free_cards(g.user_id, rank, count, color)
        if card_ids is None:
            return jsonify({'success': False,
                            'message': f'{spell_name} requires {count}× rank {rank} free cards'}), 400
        _lock_collection_cards(card_ids, _defence_lock_type('defence_prelude'), cfg.id)
        cfg.prelude_spell_card_ids = card_ids
    else:
        cfg.prelude_spell_card_ids = None

    cfg.prelude_spell_name = spell_name
    cfg.prelude_spell_data = normalized_spell_data or None
    if _is_defence_draft_request():
        _touch_config(cfg)
    db.session.commit()

    return jsonify({'success': True, 'config': _serialize_defence_edit_config(cfg)})


# ── POST /kingdom/defence/clear_prelude_spell ────────────────────────────────

@kingdom.route('/defence/clear_prelude_spell', methods=['POST'])
@kingdom.route('/defence/draft/clear_prelude_spell', methods=['POST'])
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

    cfg = (_get_draft_defence_config(g.user_id, land_id)
           if _is_defence_draft_request()
           else _get_active_defence_config(g.user_id, land_id))
    if not cfg:
        return jsonify({'success': False, 'message': 'No defence config found'}), 404

    if cfg.prelude_spell_card_ids:
        if _is_defence_draft_request():
            _unlock_collection_cards_for_ref(
                cfg.prelude_spell_card_ids,
                _defence_lock_type('defence_prelude'),
                cfg.id,
            )
        else:
            _unlock_collection_cards(cfg.prelude_spell_card_ids)

    cfg.prelude_spell_name = None
    cfg.prelude_spell_data = None
    cfg.prelude_spell_card_ids = None
    if _is_defence_draft_request():
        _touch_config(cfg)
    db.session.commit()

    return jsonify({'success': True, 'config': _serialize_defence_edit_config(cfg)})


# ── POST /kingdom/defence/set_battle_figure ──────────────────────────────────

@kingdom.route('/defence/set_battle_figure', methods=['POST'])
@kingdom.route('/defence/draft/set_battle_figure', methods=['POST'])
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

    cfg = (_get_draft_defence_config(g.user_id, land_id)
           if _is_defence_draft_request()
           else _get_active_defence_config(g.user_id, land_id))
    if not cfg:
        return jsonify({'success': False, 'message': 'No defence config found'}), 404

    # Verify figure belongs to this config
    fig1 = db.session.get(LandConfigFigure, figure_id)
    if not fig1 or fig1.config_id != cfg.id:
        return jsonify({'success': False, 'message': 'Figure not in this config'}), 400

    # Check counter-advance legality (includes resource deficit, family
    # cannot_attack/cannot_defend, and Peasant/Civil village-only rules).
    deficit_map = get_config_deficit_map(cfg.id)
    err_msg = _config_counter_advance_error(fig1, cfg, deficit_map=deficit_map)
    if err_msg:
        return jsonify({'success': False, 'message': err_msg}), 400

    # Spell and battle figure are mutually exclusive
    if cfg.spell_name:
        return jsonify({'success': False,
                        'message': 'Cannot set battle figure while a spell is active. Remove spell first.'}), 400
    if cfg.counter_spell_name:
        return jsonify({'success': False,
                        'message': 'Cannot set battle figure while a counter spell is selected. Clear counter spell first.'}), 400

    # Civil War validation
    from game_service.figure_rule_helpers import config_strategy_modifiers
    is_civil_war = any(
        mod.get('type') == 'Civil War'
        for mod in config_strategy_modifiers(cfg)
        if isinstance(mod, dict)
    )

    if is_civil_war:
        if not figure_id_2:
            return jsonify({'success': False,
                            'message': 'Civil War requires two battle figures'}), 400
        if figure_id_2 == figure_id:
            return jsonify({'success': False,
                            'message': 'Civil War requires two different battle figures'}), 400
        fig2 = db.session.get(LandConfigFigure, figure_id_2)
        if not fig2 or fig2.config_id != cfg.id:
            return jsonify({'success': False, 'message': 'Second figure not in this config'}), 400
        err_msg = _config_counter_advance_error(fig2, cfg, deficit_map=deficit_map)
        if err_msg:
            return jsonify({'success': False, 'message': err_msg}), 400
        if fig1.color != fig2.color:
            return jsonify({'success': False,
                            'message': 'Civil War: both figures must be the same color'}), 400
    else:
        figure_id_2 = None

    cfg.battle_figure_id = figure_id
    cfg.battle_figure_id_2 = figure_id_2
    if _is_defence_draft_request():
        _touch_config(cfg)
    db.session.commit()

    return jsonify({'success': True, 'config': _serialize_defence_edit_config(cfg)})


# ── POST /kingdom/defence/clear_battle_figure ────────────────────────────────

@kingdom.route('/defence/clear_battle_figure', methods=['POST'])
@kingdom.route('/defence/draft/clear_battle_figure', methods=['POST'])
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

    cfg = (_get_draft_defence_config(g.user_id, land_id)
           if _is_defence_draft_request()
           else _get_active_defence_config(g.user_id, land_id))
    if not cfg:
        return jsonify({'success': False, 'message': 'No defence config found'}), 404

    cfg.battle_figure_id = None
    cfg.battle_figure_id_2 = None
    if _is_defence_draft_request():
        _touch_config(cfg)
    db.session.commit()

    return jsonify({'success': True, 'config': _serialize_defence_edit_config(cfg)})


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

    cfg = _get_active_defence_config(g.user_id, land_id)
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

    cfg = _get_active_defence_config(g.user_id, land_id)
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
@kingdom.route('/defence/draft/set_counter_spell', methods=['POST'])
@require_token
def defence_set_counter_spell():
    """Set a counter spell for a defence config.

    Expects JSON: { land_id, spell_name, spell_data: {}|null, target_figure_id?: int,
                    clear_battle_figure?: bool }
    Counter spell is mutually exclusive with battle figure.  When
    ``clear_battle_figure`` is true the existing battle figure (and its
    second slot, if any) is cleared atomically as part of this request so
    clients don't have to perform a separate ``clear_battle_figure`` call
    that could race with the server-side mutual-exclusion check.
    """
    data = request.json
    land_id = data.get('land_id')
    spell_name = data.get('spell_name')
    spell_data = data.get('spell_data')
    target_fig_id = data.get('target_figure_id')
    clear_battle_figure = bool(data.get('clear_battle_figure'))

    if not land_id or not spell_name:
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400

    if spell_name not in _DEFENCE_COUNTER_SPELLS:
        return jsonify({'success': False,
                        'message': f'Spell "{spell_name}" is not allowed as counter action'}), 400

    land, err = _validate_land_ownership(land_id, g.user_id)
    if err:
        return err

    cfg = (_get_draft_defence_config(g.user_id, land_id)
           if _is_defence_draft_request()
           else _get_active_defence_config(g.user_id, land_id))
    if not cfg:
        return jsonify({'success': False, 'message': 'No defence config found'}), 404

    # Counter spell and battle figure are mutually exclusive.  Optionally
    # clear the battle figure first, atomically, so the caller doesn't need
    # to make a separate request.
    if cfg.battle_figure_id:
        if not clear_battle_figure:
            return jsonify({'success': False,
                            'message': 'Cannot set counter spell while a battle figure is selected. '
                                       'Clear battle figure first.'}), 400
        cfg.battle_figure_id = None
        cfg.battle_figure_id_2 = None

    if spell_name == 'Health Boost':
        if target_fig_id is None and isinstance(spell_data, dict):
            target_fig_id = spell_data.get('target_figure_id')
        target_fig_id = _coerce_int(target_fig_id)
        if target_fig_id:
            fig, err_msg = _validate_config_own_spell_target(cfg, target_fig_id)
            if err_msg:
                return jsonify({'success': False, 'message': err_msg}), 400
            target_fig_id = fig.id
        else:
            target_fig_id = None
    else:
        target_fig_id = None

    # Unlock previous counter spell cards
    if cfg.counter_spell_card_ids:
        if _is_defence_draft_request():
            _unlock_collection_cards_for_ref(
                cfg.counter_spell_card_ids,
                _defence_lock_type('defence_counter'),
                cfg.id,
            )
        else:
            _unlock_collection_cards(cfg.counter_spell_card_ids)

    # Find required free cards
    req = _SPELL_CARD_COST.get(spell_name)
    if req:
        rank, count, color = req
        card_ids = _find_free_cards(g.user_id, rank, count, color)
        if card_ids is None:
            return jsonify({'success': False,
                            'message': f'{spell_name} requires {count}× rank {rank} free cards'}), 400
        _lock_collection_cards(card_ids, _defence_lock_type('defence_counter'), cfg.id)
        cfg.counter_spell_card_ids = card_ids
    else:
        cfg.counter_spell_card_ids = None

    cfg.counter_spell_name = spell_name
    cfg.counter_spell_data = spell_data
    cfg.counter_spell_target_figure_id = target_fig_id
    if _is_defence_draft_request():
        _touch_config(cfg)
    db.session.commit()

    return jsonify({'success': True, 'config': _serialize_defence_edit_config(cfg)})


# ── POST /kingdom/defence/clear_counter_spell ────────────────────────────────

@kingdom.route('/defence/clear_counter_spell', methods=['POST'])
@kingdom.route('/defence/draft/clear_counter_spell', methods=['POST'])
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

    cfg = (_get_draft_defence_config(g.user_id, land_id)
           if _is_defence_draft_request()
           else _get_active_defence_config(g.user_id, land_id))
    if not cfg:
        return jsonify({'success': False, 'message': 'No defence config found'}), 404

    if cfg.counter_spell_card_ids:
        if _is_defence_draft_request():
            _unlock_collection_cards_for_ref(
                cfg.counter_spell_card_ids,
                _defence_lock_type('defence_counter'),
                cfg.id,
            )
        else:
            _unlock_collection_cards(cfg.counter_spell_card_ids)

    cfg.counter_spell_name = None
    cfg.counter_spell_data = None
    cfg.counter_spell_card_ids = None
    cfg.counter_spell_target_figure_id = None
    if _is_defence_draft_request():
        _touch_config(cfg)
    db.session.commit()

    return jsonify({'success': True, 'config': _serialize_defence_edit_config(cfg)})


# ── POST /kingdom/defence/set_auto_gamble ────────────────────────────────────

@kingdom.route('/defence/set_auto_gamble', methods=['POST'])
@kingdom.route('/defence/draft/set_auto_gamble', methods=['POST'])
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

    cfg = (_get_draft_defence_config(g.user_id, land_id)
           if _is_defence_draft_request()
           else _get_active_defence_config(g.user_id, land_id))
    if not cfg:
        return jsonify({'success': False, 'message': 'No defence config found'}), 404

    cfg.auto_gamble = bool(auto_gamble)
    if _is_defence_draft_request():
        _touch_config(cfg)
    db.session.commit()

    return jsonify({'success': True, 'config': _serialize_defence_edit_config(cfg)})


@kingdom.route('/defence/set_auto_gamble_threshold', methods=['POST'])
@kingdom.route('/defence/draft/set_auto_gamble_threshold', methods=['POST'])
@require_token
def defence_set_auto_gamble_threshold():
    """Set the auto-gamble threshold for a defence config.

    Expects JSON: { land_id, auto_gamble_threshold: int }
    """
    data = request.json
    land_id = data.get('land_id')
    threshold = data.get('auto_gamble_threshold')

    if not land_id or threshold is None:
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400

    land, err = _validate_land_ownership(land_id, g.user_id)
    if err:
        return err

    cfg = (_get_draft_defence_config(g.user_id, land_id)
           if _is_defence_draft_request()
           else _get_active_defence_config(g.user_id, land_id))
    if not cfg:
        return jsonify({'success': False, 'message': 'No defence config found'}), 404

    cfg.auto_gamble_threshold = _normalize_auto_gamble_threshold(threshold)
    if _is_defence_draft_request():
        _touch_config(cfg)
    db.session.commit()

    return jsonify({'success': True, 'config': _serialize_defence_edit_config(cfg)})


# ═════════════════════════════════════════════════════════════════════════════
#  Conquer Battle — Phase 13
# ═════════════════════════════════════════════════════════════════════════════

_RANK_TO_VALUE = {
    '7': 7, '8': 8, '9': 9, '10': 10,
    'J': 1, 'Q': 2, 'K': 4, 'A': 3,
}

_SIDE_RANK_TO_VALUE = {
    '2': 2, '3': 3, '4': 4, '5': 5, '6': 6,
}

_MAIN_RANKS = set(_RANK_TO_VALUE.keys())
_NUMERIC_TO_MAIN_RANK = {v: k for k, v in _RANK_TO_VALUE.items()}
_NUMERIC_TO_MAIN_RANK.update({11: 'J', 12: 'Q', 13: 'K', 14: 'A'})
_SIDE_RANKS = set(_SIDE_RANK_TO_VALUE.keys())
_NUMERIC_TO_SIDE_RANK = {v: k for k, v in _SIDE_RANK_TO_VALUE.items()}
_VALID_SUITS = {s.value for s in Suit}


def _enum_value(raw):
    return raw.value if hasattr(raw, 'value') else raw


def _normalize_main_rank(rank, *, fallback_rank='10', value=None, context=''):
    """Normalize input rank into a valid main-rank string."""
    fallback = str(_enum_value(fallback_rank) or '10').strip().upper()
    if fallback not in _MAIN_RANKS:
        fallback = '10'

    raw_rank = _enum_value(rank)
    candidate = str(raw_rank).strip().upper() if raw_rank is not None else ''
    if candidate in _MAIN_RANKS:
        return candidate

    for source, source_name in ((candidate, 'rank'), (value, 'value')):
        try:
            numeric = int(source)
        except (TypeError, ValueError):
            continue
        mapped = _NUMERIC_TO_MAIN_RANK.get(numeric)
        if mapped:
            if candidate and candidate != mapped:
                logger.warning(
                    "[CONQUER] normalized non-main rank '%s' -> '%s' via %s (context=%s)",
                    candidate, mapped, source_name, context or 'n/a')
            return mapped

    if candidate:
        logger.warning(
            "[CONQUER] invalid main rank '%s', using fallback '%s' (context=%s)",
            candidate, fallback, context or 'n/a')
    return fallback


def _normalize_main_value(rank, value, *, context=''):
    """Return canonical value for a main rank, correcting mismatched inputs."""
    expected = int(_RANK_TO_VALUE.get(rank, 0))
    try:
        raw = int(value)
    except (TypeError, ValueError):
        raw = None

    if raw == expected:
        return raw

    if raw is not None:
        logger.warning(
            "[CONQUER] normalized card value %s -> %s for rank '%s' (context=%s)",
            raw, expected, rank, context or 'n/a')
    return expected


def _normalize_side_rank(rank, *, fallback_rank='6', value=None, context=''):
    """Normalize input rank into a valid side-rank string."""
    fallback = str(_enum_value(fallback_rank) or '6').strip()
    if fallback not in _SIDE_RANKS:
        fallback = '6'

    raw_rank = _enum_value(rank)
    candidate = str(raw_rank).strip() if raw_rank is not None else ''
    if candidate in _SIDE_RANKS:
        return candidate

    for source, source_name in ((candidate, 'rank'), (value, 'value')):
        try:
            numeric = int(source)
        except (TypeError, ValueError):
            continue
        mapped = _NUMERIC_TO_SIDE_RANK.get(numeric)
        if mapped:
            if candidate and candidate != mapped:
                logger.warning(
                    "[CONQUER] normalized non-side rank '%s' -> '%s' via %s (context=%s)",
                    candidate, mapped, source_name, context or 'n/a')
            return mapped

    if candidate:
        logger.warning(
            "[CONQUER] invalid side rank '%s', using fallback '%s' (context=%s)",
            candidate, fallback, context or 'n/a')
    return fallback


def _normalize_side_value(rank, value, *, context=''):
    """Return canonical value for a side rank, correcting mismatched inputs."""
    expected = int(_SIDE_RANK_TO_VALUE.get(rank, 0))
    try:
        raw = int(value)
    except (TypeError, ValueError):
        raw = None

    if raw == expected:
        return raw

    if raw is not None:
        logger.warning(
            "[CONQUER] normalized side-card value %s -> %s for rank '%s' (context=%s)",
            raw, expected, rank, context or 'n/a')
    return expected


def _normalize_suit(suit, *, fallback='Hearts', context=''):
    """Normalize input suit into one of the canonical suit names."""
    raw_suit = _enum_value(suit)
    candidate = str(raw_suit).strip().title() if raw_suit is not None else ''
    if candidate in _VALID_SUITS:
        return candidate

    fallback_suit = str(_enum_value(fallback) or 'Hearts').strip().title()
    if fallback_suit not in _VALID_SUITS:
        fallback_suit = 'Hearts'

    if candidate:
        logger.warning(
            "[CONQUER] invalid suit '%s', using fallback '%s' (context=%s)",
            candidate, fallback_suit, context or 'n/a')
    return fallback_suit


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
            source_config_figure_id=cfg_fig.id,
        )
        db.session.add(fig)
        db.session.flush()

        card_ids = cfg_fig.card_ids or []
        card_roles = cfg_fig.card_roles or []
        for i, role in enumerate(card_roles):
            # Look up the collection card to get rank/suit/value
            raw_rank = None
            raw_suit = cfg_fig.suit
            raw_value = 0
            if i < len(card_ids) and card_ids[i]:
                cc = db.session.get(CollectionCard, card_ids[i])
                if cc:
                    raw_rank = cc.rank
                    raw_suit = cc.suit
                    raw_value = cc.value

            fallback_rank = 'K' if role == 'key' else '10'
            if not raw_rank:
                # Fallback: derive from figure suit and role
                raw_rank = fallback_rank
                raw_value = _RANK_TO_VALUE.get(raw_rank, 0)

            context = f'cfg_fig={cfg_fig.id} role={role} card_id={card_ids[i] if i < len(card_ids) else None}'
            rank = _normalize_main_rank(
                raw_rank,
                fallback_rank=fallback_rank,
                value=raw_value,
                context=context,
            )
            suit = _normalize_suit(raw_suit, fallback=cfg_fig.suit or 'Hearts', context=context)
            value = _normalize_main_value(rank, raw_value, context=context)

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
            card_data = tpl_cards[i] if i < len(tpl_cards) else {}
            card_type = str(card_data.get('card_type', 'main') or 'main').strip().lower()
            if card_type not in ('main', 'side'):
                logger.warning(
                    "[CONQUER] invalid template card_type '%s' for figure '%s'; using 'main'",
                    card_type,
                    tpl_fig.get('family_name', 'unknown'),
                )
                card_type = 'main'

            if card_type == 'side':
                fallback_rank = '2' if role == 'key' else '6'
            else:
                fallback_rank = 'K' if role == 'key' else '10'

            if i < len(tpl_cards):
                raw_rank = card_data.get('rank', fallback_rank)
                raw_suit = card_data.get('suit', tpl_fig['suit'])
                raw_value = card_data.get('value')
            else:
                raw_rank = fallback_rank
                raw_suit = tpl_fig['suit']
                raw_value = (
                    _SIDE_RANK_TO_VALUE.get(raw_rank, 0)
                    if card_type == 'side'
                    else _RANK_TO_VALUE.get(raw_rank, 0)
                )

            context = f'tpl_fig={tpl_fig.get("family_name", "unknown")} role={role} idx={i}'
            suit = _normalize_suit(raw_suit, fallback=tpl_fig.get('suit', 'Hearts'), context=context)

            if card_type == 'side':
                rank = _normalize_side_rank(
                    raw_rank,
                    fallback_rank=fallback_rank,
                    value=raw_value,
                    context=context,
                )
                value = _normalize_side_value(rank, raw_value, context=context)

                sc = SideCard(
                    rank=rank,
                    suit=suit,
                    value=value,
                    game_id=game.id,
                    player_id=player.id,
                    in_deck=False,
                    part_of_figure=True,
                )
                db.session.add(sc)
                db.session.flush()

                ctf = CardToFigure(
                    figure_id=fig.id,
                    card_id=sc.id,
                    card_type='side',
                    role=role,
                )
            else:
                rank = _normalize_main_rank(
                    raw_rank,
                    fallback_rank=fallback_rank,
                    value=raw_value,
                    context=context,
                )
                value = _normalize_main_value(rank, raw_value, context=context)

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

        context = f'cfg_move={cfg_move.id} family={cfg_move.family_name}'
        rank = _normalize_main_rank(
            cfg_move.rank,
            fallback_rank='10',
            value=cfg_move.value,
            context=context,
        )
        suit = _normalize_suit(cfg_move.suit, fallback='Hearts', context=context)
        value = _normalize_main_value(rank, cfg_move.value, context=context)

        mc = MainCard(
            rank=rank,
            suit=suit,
            value=value,
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
            suit=suit,
            rank=rank,
            value=value,
            call_figure_id=call_fig_id,
        )
        db.session.add(move)


def _build_conquer_tactics_from_config(cfg_moves, player, game,
                                       config_figure_map=None, source='config'):
    """Create ConquerTactic records from configured conquer/defence moves."""
    for sort_order, cfg_move in enumerate(cfg_moves):
        call_fig_id = None
        if cfg_move.call_figure_id and config_figure_map:
            call_fig_id = config_figure_map.get(cfg_move.call_figure_id)

        context = f'cfg_move={cfg_move.id} family={cfg_move.family_name}'
        rank = _normalize_main_rank(
            cfg_move.rank,
            fallback_rank='10',
            value=cfg_move.value,
            context=context,
        )
        suit = _normalize_suit(cfg_move.suit, fallback='Hearts', context=context)
        value = _normalize_main_value(rank, cfg_move.value, context=context)

        mc = MainCard(
            rank=rank,
            suit=suit,
            value=value,
            game_id=game.id,
            player_id=player.id,
            in_deck=False,
            part_of_figure=False,
            part_of_battle_move=True,
        )
        db.session.add(mc)
        db.session.flush()

        tactic = ConquerTactic(
            game_id=game.id,
            player_id=player.id,
            family_name=cfg_move.family_name,
            card_id=mc.id,
            card_type='main',
            suit=suit,
            rank=rank,
            value=value,
            source=source,
            status='available',
            call_figure_id=call_fig_id,
            sort_order=getattr(cfg_move, 'round_index', None)
            if getattr(cfg_move, 'round_index', None) is not None else sort_order,
        )
        db.session.add(tactic)


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

        context = f"tpl_move={tpl_move.get('family_name', 'unknown')}"
        rank = _normalize_main_rank(
            tpl_move.get('rank'),
            fallback_rank='10',
            value=tpl_move.get('value'),
            context=context,
        )
        suit = _normalize_suit(
            tpl_move.get('suit'),
            fallback='Hearts',
            context=context,
        )
        value = _normalize_main_value(rank, tpl_move.get('value'), context=context)

        mc = MainCard(
            rank=rank,
            suit=suit,
            value=value,
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
            suit=suit,
            rank=rank,
            value=value,
            call_figure_id=call_fig_id,
        )
        db.session.add(move)


def _build_conquer_tactics_from_template(template_moves, player, game,
                                         template_figures=None, game_figures=None):
    """Create ConquerTactic records from AI template move dicts."""
    for sort_order, tpl_move in enumerate(template_moves):
        call_fig_id = None
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

        context = f"tpl_move={tpl_move.get('family_name', 'unknown')}"
        rank = _normalize_main_rank(
            tpl_move.get('rank'),
            fallback_rank='10',
            value=tpl_move.get('value'),
            context=context,
        )
        suit = _normalize_suit(
            tpl_move.get('suit'),
            fallback='Hearts',
            context=context,
        )
        value = _normalize_main_value(rank, tpl_move.get('value'), context=context)

        mc = MainCard(
            rank=rank,
            suit=suit,
            value=value,
            game_id=game.id,
            player_id=player.id,
            in_deck=False,
            part_of_figure=False,
            part_of_battle_move=True,
        )
        db.session.add(mc)
        db.session.flush()

        tactic = ConquerTactic(
            game_id=game.id,
            player_id=player.id,
            family_name=tpl_move['family_name'],
            card_id=mc.id,
            card_type=tpl_move.get('card_type', 'main'),
            suit=suit,
            rank=rank,
            value=value,
            source='template',
            status='available',
            call_figure_id=call_fig_id,
            sort_order=sort_order,
        )
        db.session.add(tactic)


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


def _prelude_spell_requires_target(spell_name):
    return spell_name in _TARGETED_PRELUDE_SPELLS


def _get_prelude_target_scope(spell_name):
    if spell_name in ('Poison', 'Explosion'):
        return 'opponent'
    if spell_name == 'Health Boost':
        return 'own'
    return None


def _list_valid_prelude_targets(game, caster_player_id, spell_name):
    """Return valid prelude targets, excluding checkmate figures."""
    scope = _get_prelude_target_scope(spell_name)
    if not scope:
        return []

    if scope == 'opponent':
        candidate_player_ids = [p.id for p in game.players if p.id != caster_player_id]
    else:
        candidate_player_ids = [caster_player_id]

    if not candidate_player_ids:
        return []

    targets = Figure.query.filter(
        Figure.game_id == game.id,
        Figure.player_id.in_(candidate_player_ids),
    ).all()
    return [f for f in targets if not getattr(f, 'checkmate', False)]


def _pick_deterministic_prelude_target(figures):
    """Pick one target deterministically by highest base power, then lowest ID."""
    if not figures:
        return None

    from routes.games import _compute_figure_base_power

    return sorted(figures, key=lambda f: (-_compute_figure_base_power(f), f.id))[0]


def _figure_card_count(figure):
    return CardToFigure.query.filter_by(figure_id=figure.id).count()


def _figure_has_instant_charge(figure):
    try:
        from ai.figure_recipes import FAMILY_SKILLS
        skills = FAMILY_SKILLS.get(figure.family_name) or FAMILY_SKILLS.get(figure.name) or {}
        return bool(skills.get('instant_charge'))
    except Exception:
        return False


def _figure_has_family_skill(figure, skill_name):
    if not figure:
        return False
    if bool(getattr(figure, skill_name, False)):
        return True
    try:
        from ai.figure_recipes import FAMILY_SKILLS
        skills = FAMILY_SKILLS.get(figure.family_name) or FAMILY_SKILLS.get(figure.name) or {}
        return bool(skills.get(skill_name))
    except Exception:
        return False


def _has_must_be_attacked_figure(figures):
    return any(_figure_has_family_skill(fig, 'must_be_attacked') for fig in figures or [])


def _pick_defence_prelude_target(figures, planned_modifiers=None):
    """Pick a target for automated defence Poison/Explosion preludes.

    Selection is fully deterministic so that defence start-of-battle
    behaviour is reproducible and unit-testable.  Tie-breakers prefer the
    figure with the highest base power, then the lowest figure ID.
    """
    if not figures:
        return None

    from routes.games import _compute_figure_base_power

    def _rank_key(fig):
        # Higher base power first; on ties the lowest ID wins.
        return (-_compute_figure_base_power(fig), fig.id)

    modifiers = planned_modifiers if isinstance(planned_modifiers, list) else []
    modifier_types = {m.get('type') for m in modifiers if isinstance(m, dict)}

    # Tier 1: Civil War / Peasant War — village figures with the most cards
    # built into them are the highest-impact targets to disable.
    if 'Civil War' in modifier_types or 'Peasant War' in modifier_types:
        village_targets = [f for f in figures if (f.field or '').lower() == 'village']
        if village_targets:
            max_cards = max(_figure_card_count(f) for f in village_targets)
            top = [f for f in village_targets if _figure_card_count(f) == max_cards]
            return sorted(top, key=_rank_key)[0]

    # Tier 2: figures that bypass blocking or have instant charge are the
    # most dangerous attackers; disable them first.
    fast_targets = [
        f for f in figures
        if getattr(f, 'cannot_be_blocked', False) or _figure_has_instant_charge(f)
    ]
    if fast_targets:
        return sorted(fast_targets, key=_rank_key)[0]

    # Tier 3: castle / village figures (production / economy targets).
    castle_or_village = [
        f for f in figures
        if (f.field or '').lower() in {'castle', 'village'}
    ]
    if castle_or_village:
        return sorted(castle_or_village, key=_rank_key)[0]

    return sorted(figures, key=_rank_key)[0]


def _planned_conquer_modifiers(def_cfg_or_template, atk_cfg):
    """Return battle modifiers that are expected to exist after preludes resolve."""
    modifiers = []

    def _append_spell_modifier(spell_name, caster_label):
        if spell_name in _BATTLE_MODIFIER_SPELLS:
            modifiers.append({'type': spell_name, 'caster': caster_label})

    if isinstance(def_cfg_or_template, dict):
        _append_spell_modifier(def_cfg_or_template.get('prelude_spell_name'), 'defender')
        legacy = def_cfg_or_template.get('battle_modifier')
    else:
        _append_spell_modifier(getattr(def_cfg_or_template, 'prelude_spell_name', None), 'defender')
        legacy = getattr(def_cfg_or_template, 'battle_modifier', None)
    if legacy:
        if isinstance(legacy, list):
            modifiers.extend([m for m in legacy if isinstance(m, dict)])
        elif isinstance(legacy, dict):
            modifiers.append(legacy)

    _append_spell_modifier(getattr(atk_cfg, 'prelude_spell_name', None), 'attacker')
    legacy_atk = getattr(atk_cfg, 'battle_modifier', None)
    if legacy_atk:
        if isinstance(legacy_atk, list):
            modifiers.extend([m for m in legacy_atk if isinstance(m, dict)])
        elif isinstance(legacy_atk, dict):
            modifiers.append(legacy_atk)
    return modifiers


def _mark_prelude_spell_no_target(spell):
    _update_prelude_effect_data(
        spell,
        status=PRELUDE_STATUS_NO_VALID_TARGET,
        clear_pending=True,
        **{
            PRELUDE_KEY_ORIGIN: True,
            PRELUDE_KEY_REQUIRES_TARGET: True,
        },
    )
    spell.is_active = False
    spell.is_pending = False


def _create_prelude_spell(game, player, spell_name, spell_data, game_figures,
                          *, target_resolution='immediate', configured_target_id=None,
                          target_modifiers=None):
    """Create an ActiveSpell for a prelude spell and resolve startup behavior.

    For battle-modifier spells (Peasant War / Civil War / Blitzkrieg) the
    modifier is also appended to ``game.battle_modifier`` so that existing
    game logic (advance restrictions, turn handling, ceasefire) continues to
    work without changes.

    All other prelude spells (greed / enchantment) are executed right away so
    that their effects (draw cards, dump hands, etc.) are applied before the
    first turn.

    ``target_resolution`` controls target-required spells:
    - ``'auto'``: deterministic automatic target selection and execution.
    - ``'defence_auto'``: automated defence heuristic target selection.
    - ``'configured'``: use a pre-configured runtime target ID.
    - ``'pending'``: mark the spell as pending target selection for the invader.
    - ``'immediate'``: immediate execution path (non-target spells).
    """
    effect_data = dict(spell_data) if isinstance(spell_data, dict) else {}
    effect_data[PRELUDE_KEY_ORIGIN] = True

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
        effect_data=effect_data,
    )
    db.session.add(spell)

    if spell_name in _BATTLE_MODIFIER_SPELLS:
        if not isinstance(game.battle_modifier, list):
            game.battle_modifier = []
        game.battle_modifier.append({'type': spell_name, 'caster_id': player.id})
        _update_prelude_effect_data(spell, status=PRELUDE_STATUS_EXECUTED)
    else:
        # Target-required prelude spells can be auto-resolved (defender) or
        # deferred for explicit invader target selection.
        if _prelude_spell_requires_target(spell_name):
            valid_targets = _list_valid_prelude_targets(game, player.id, spell_name)
            if not valid_targets:
                _mark_prelude_spell_no_target(spell)
                return

            if target_resolution == 'pending':
                _update_prelude_effect_data(
                    spell,
                    status=PRELUDE_STATUS_PENDING_TARGET,
                    **{
                        PRELUDE_KEY_REQUIRES_TARGET: True,
                        PRELUDE_KEY_PENDING_TARGET: True,
                        PRELUDE_KEY_TARGET_SCOPE: _get_prelude_target_scope(spell_name),
                        PRELUDE_KEY_VALID_TARGET_IDS: [f.id for f in valid_targets],
                    },
                )
                spell.is_active = False
                spell.is_pending = False
                return

            if target_resolution == 'configured':
                chosen_target = next(
                    (f for f in valid_targets if f.id == configured_target_id),
                    None,
                )
                if not chosen_target:
                    _mark_prelude_spell_no_target(spell)
                    return
                spell.target_figure_id = chosen_target.id
            elif target_resolution == 'defence_auto':
                chosen_target = _pick_defence_prelude_target(
                    valid_targets,
                    planned_modifiers=target_modifiers,
                )
                spell.target_figure_id = chosen_target.id if chosen_target else None
            elif target_resolution == 'auto':
                chosen_target = _pick_deterministic_prelude_target(valid_targets)
                spell.target_figure_id = chosen_target.id if chosen_target else None

        # Greed / enchantment prelude spells: execute immediately
        db.session.flush()
        from routes.spells import _execute_spell
        result = _execute_spell(spell, game, player)
        if result.get('error'):
            logger.warning(f'Prelude spell {spell_name} execution failed: {result}')
            _update_prelude_effect_data(
                spell,
                status=PRELUDE_STATUS_FAILED,
                **{PRELUDE_KEY_ORIGIN: True},
            )
        else:
            # Persist prelude metadata and actually-drawn cards on the spell so
            # game-start notifications can report precise effects.
            extras = {PRELUDE_KEY_ORIGIN: True}
            drawn = result.get('drawn_cards', [])
            if drawn:
                extras['drawn_card_ids'] = [c['id'] for c in drawn]
            for key in (
                'target_figure_id', 'power_modifier', 'spell_icon',
                'destroyed_figure_name', 'card_count', 'caster_dumped',
                'opponent_dumped', 'caster_dumped_cards', 'opponent_dumped_cards',
                'drawn_cards', 'opponent_drawn_cards', 'cards_given',
                'cards_received', 'opponent_notification',
                'conquer_invader_swap', 'old_invader_id', 'new_invader_id',
                'invader_swapped',
            ):
                if key in result:
                    extras[key] = result[key]
            _update_prelude_effect_data(spell, status=PRELUDE_STATUS_EXECUTED, **extras)


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
    from kingdom_service import (check_land_config_deficit,
                                 get_config_deficit_map,
                                 conquer_cooldown_seconds_for_target,
                                 reconcile_user_kingdoms)

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

    if land.owner_user_id:
        reconcile_user_kingdoms(land.owner_user_id, commit=False)
        db.session.flush()
        from kingdom_service import kingdom_shield_block_reason
        shield_remaining, defended_kingdom, reason = kingdom_shield_block_reason(land, now=_utcnow())
        if reason and defended_kingdom:
            if reason == 'core_protection':
                return jsonify({
                    'success': False,
                    'message': 'Core Protection: this is one of the kingdom\'s last lands and cannot be conquered.',
                    'core_protection': True,
                    'kingdom_id': defended_kingdom.id,
                }), 400
            return jsonify({
                'success': False,
                'message': f'Kingdom shield blocks attacks. {shield_remaining}s remaining.',
                'shield_remaining': shield_remaining,
                'kingdom_id': defended_kingdom.id,
            }), 400

    # Land-level conquer protection after a successful ownership transfer.
    if land.conquer_cooldown_until:
        remaining = int((land.conquer_cooldown_until - _utcnow()).total_seconds())
        if remaining > 0:
            return jsonify({
                'success': False,
                'message': f'Land is under conquer protection. {remaining}s remaining.'
            }), 400

    # Cooldown check
    effective_conquer_cooldown = conquer_cooldown_seconds_for_target(user.id, land)
    use_map = bool((data or {}).get('use_map'))
    cooldown_remaining = 0
    if user.last_conquer_at:
        elapsed = (_utcnow() - user.last_conquer_at).total_seconds()
        if elapsed < effective_conquer_cooldown:
            cooldown_remaining = int(effective_conquer_cooldown - elapsed)

    if cooldown_remaining > 0:
        if not use_map:
            return jsonify({
                'success': False,
                'message': f'Conquer on cooldown. {cooldown_remaining}s remaining.',
                'code': 'cooldown',
                'cooldown_remaining': cooldown_remaining,
                'maps_available': int(user.maps or 0),
            }), 400
        if int(user.maps or 0) <= 0:
            return jsonify({
                'success': False,
                'message': 'No maps available to bypass the cooldown.',
                'code': 'no_maps',
                'cooldown_remaining': cooldown_remaining,
                'maps_available': 0,
            }), 400
        # Map will be consumed at the very end (after all other checks pass),
        # so a failed start_battle never burns a map.
    elif use_map:
        return jsonify({
            'success': False,
            'message': 'Cooldown is not active; no map needed.',
            'code': 'no_cooldown',
            'cooldown_remaining': 0,
            'maps_available': int(user.maps or 0),
        }), 400

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
    defender_strategy_mode = 'template'

    if is_ai_land:
        defender_user = _get_or_create_ai_user()
        template = get_ai_defence_template_for_land(land)
        if not template:
            return jsonify({'success': False,
                            'message': 'No AI defence available for this land'}), 400
    else:
        defender_user = db.session.get(User, land.owner_user_id)
        if not defender_user:
            return jsonify({'success': False, 'message': 'Defender not found'}), 400
        def_cfg = _get_active_defence_config(defender_user.id, land_id)
        if not def_cfg:
            return jsonify({'success': False,
                            'message': 'Defender has no defence config'}), 400

        has_battle_fig = (def_cfg.battle_figure_id is not None)
        has_counter_spell = (
            def_cfg.counter_spell_name is not None or def_cfg.spell_name is not None
        )
        if def_cfg.counter_spell_name == 'Explosion':
            has_counter_spell = False
        if def_cfg.counter_spell_name == 'Health Boost':
            counter_target = db.session.get(
                LandConfigFigure,
                def_cfg.counter_spell_target_figure_id,
            )
            has_counter_spell = bool(counter_target and counter_target.config_id == def_cfg.id
                                     and not getattr(counter_target, 'checkmate', False))

        battle_cfg_fig_valid = False
        if has_battle_fig:
            battle_cfg_fig = db.session.get(LandConfigFigure, def_cfg.battle_figure_id)
            planned_modifiers = _planned_conquer_modifiers(def_cfg, atk_cfg)
            battle_cfg_fig_valid = bool(
                battle_cfg_fig and battle_cfg_fig.config_id == def_cfg.id
                and _config_figure_can_counter_advance(
                    battle_cfg_fig,
                    def_cfg,
                    deficit_map=get_config_deficit_map(def_cfg.id),
                    planned_modifiers=planned_modifiers,
                )
            )

        if has_battle_fig and not has_counter_spell and battle_cfg_fig_valid:
            defender_strategy_mode = 'battle_figure'
        elif has_counter_spell and not has_battle_fig:
            defender_strategy_mode = 'counter_spell'
        elif has_counter_spell and has_battle_fig and battle_cfg_fig_valid:
            # Both-selected: the counter spell fires on the response window
            # and the configured battle figure is the counter-advance fallback
            # if the spell can't (or shouldn't) be cast.  Pick the
            # counter-spell branch so the response window opens; the AI worker
            # falls back to the battle figure via cfg.battle_figure_id.
            defender_strategy_mode = 'counter_spell'
        else:
            defender_strategy_mode = 'none'
            logger.info(
                "[CONQUER] Defender strategy fallback enabled for land=%s: "
                "has_battle_fig=%s has_counter_spell=%s battle_fig_valid=%s",
                land_id,
                has_battle_fig,
                has_counter_spell,
                battle_cfg_fig_valid,
            )

    # ── Create the Game ──
    # New conquer games default to the unified "tactics_hand" model:
    # configured battle moves become the starting tactics hand, no battle_shop
    # buy/confirm phase. The legacy 'battle_move' model can be re-enabled via
    # CONQUER_TACTICS_HAND_ENABLED=False for rollback.
    _move_model = 'tactics_hand' if getattr(config,
                                            'CONQUER_TACTICS_HAND_ENABLED',
                                            True) else 'battle_move'
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
        conquer_move_model=_move_model,
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

    if _move_model == 'tactics_hand':
        _build_conquer_tactics_from_config(
            atk_moves, atk_player, game, config_figure_map=cfg_fig_map,
            source='config')
    else:
        _build_battle_moves_from_config(atk_moves, atk_player, game,
                                        config_figure_map=cfg_fig_map)

    # ── Build defender figures & moves ──
    if is_ai_land:
        def_game_figures = _build_figures_from_template(
            template['figures'], def_player, game)
        if _move_model == 'tactics_hand':
            _build_conquer_tactics_from_template(
                template['battle_moves'], def_player, game,
                template_figures=template['figures'],
                game_figures=def_game_figures)
        else:
            _build_battle_moves_from_template(
                template['battle_moves'], def_player, game,
                template_figures=template['figures'],
                game_figures=def_game_figures)

        # Set defender battle figure from template
        battle_fig_idx = template.get('battle_figure_index', 0)
        defer_template_defender = (
            bool(template.get('counter_spell_name')) or
            _has_must_be_attacked_figure(def_game_figures)
        )
        if battle_fig_idx < len(def_game_figures) and not defer_template_defender:
            game.defending_figure_id = def_game_figures[battle_fig_idx].id

        planned_modifiers = _planned_conquer_modifiers(template, atk_cfg)

        # ── AI prelude spell ──
        if template.get('prelude_spell_name'):
            _create_prelude_spell(game, def_player,
                                  template['prelude_spell_name'],
                                  template.get('prelude_spell_data'),
                                  def_game_figures,
                                  target_resolution='defence_auto',
                                  target_modifiers=planned_modifiers)
        elif template.get('battle_modifier'):
            # Backward compat: old template battle_modifier
            mod = template['battle_modifier']
            game.battle_modifier = [mod] if isinstance(mod, dict) else mod

        # Counter spells are executed only when the defender response window
        # occurs. Do not create an active spell at battle start.

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

        if _move_model == 'tactics_hand':
            _build_conquer_tactics_from_config(
                def_config_moves, def_player, game,
                config_figure_map=def_cfg_fig_map,
                source='config')
        else:
            _build_battle_moves_from_config(
                def_config_moves, def_player, game,
                config_figure_map=def_cfg_fig_map)

        # NOTE: We intentionally do NOT pre-set ``game.defending_figure_id``
        # for ``'battle_figure'`` mode any more.  The AI defender response
        # loop counter-advances with the configured battle figure when the
        # invader advances, so the player visibly sees the response instead
        # of being dropped straight into ``battle_decision`` against an
        # already-locked defender.

        planned_modifiers = _planned_conquer_modifiers(def_cfg, atk_cfg)

        # ── Defender prelude spell ──
        if def_cfg.prelude_spell_name:
            prelude_data = dict(def_cfg.prelude_spell_data or {}) if isinstance(def_cfg.prelude_spell_data, dict) else {}
            target_resolution = 'defence_auto'
            configured_target_id = None
            if def_cfg.prelude_spell_name == 'Health Boost':
                configured_cfg_id = _coerce_int(prelude_data.get('target_figure_id'))
                configured_target_id = def_cfg_fig_map.get(configured_cfg_id)
                target_resolution = 'configured'
            _create_prelude_spell(game, def_player,
                                  def_cfg.prelude_spell_name,
                                  prelude_data,
                                  def_game_figures,
                                  target_resolution=target_resolution,
                                  configured_target_id=configured_target_id,
                                  target_modifiers=planned_modifiers)
        elif def_cfg.battle_modifier:
            # Backward compat: old battle_modifier field
            mod = def_cfg.battle_modifier
            game.battle_modifier = [mod] if isinstance(mod, dict) else mod

        # ── Defender counter spell ──
        # Counter spells are executed only when the defender response
        # window occurs. Do not create an active spell at battle start.

    # ── Attacker prelude spell ──
    if atk_cfg.prelude_spell_name:
        _create_prelude_spell(game, atk_player,
                              atk_cfg.prelude_spell_name,
                              atk_cfg.prelude_spell_data,
                              atk_game_figures,
                              target_resolution='pending')
    elif not game.battle_modifier and atk_cfg.battle_modifier:
        # Backward compat: old battle_modifier fallback
        mod = atk_cfg.battle_modifier
        game.battle_modifier = [mod] if isinstance(mod, dict) else mod

    # Greed preludes such as Forced Deal / Dump Cards intentionally disrupt
    # pre-built battle moves by moving or recycling their backing cards.  The
    # conquerer can manually select replacements, but the configured/AI
    # defender is automated; rebuild its missing moves from any new runtime
    # hand cards after *both* players' preludes have resolved.
    from game_service.battle_move_replenisher import replenish_automated_conquer_defender_moves
    replenish_automated_conquer_defender_moves(
        game,
        def_player,
        reason='conquer_prelude',
    )

    if game.defending_figure_id:
        selected_defender = db.session.get(Figure, game.defending_figure_id)
        from routes.games import _figure_can_counter_advance
        if (
            not selected_defender
            or selected_defender.player_id != def_player.id
            or not _figure_can_counter_advance(selected_defender, def_player.id, game.id)
        ):
            logger.info(
                "[CONQUER] Clearing invalid preselected defender figure "
                "game=%s figure_id=%s",
                game.id,
                game.defending_figure_id,
            )
            game.defending_figure_id = None
            game.defending_figure_id_2 = None

    # ── Blitzkrieg: ignore the defender's pre-configured battle figure.
    #    The invader will select the opponent's figure via select_defender()
    #    after advancing (Blitzkrieg's core mechanic). ──
    if game.battle_modifier and any(
        m.get('type') == 'Blitzkrieg' for m in game.battle_modifier
    ):
        game.defending_figure_id = None
        game.defending_figure_id_2 = None

    # Set cooldown
    map_consumed = False
    if cooldown_remaining > 0 and use_map:
        # All pre-battle validation has passed; safe to consume the map now.
        user.maps = max(0, int(user.maps or 0) - 1)
        user.last_conquer_at = None
        map_consumed = True
    else:
        user.last_conquer_at = _utcnow()

    db.session.commit()

    logger.info(f"[CONQUER] Battle started: game={game.id} land={land_id} "
                f"attacker={user.username} defender={defender_user.username} "
                f"ai_land={is_ai_land} map_consumed={map_consumed}")

    return jsonify({
        'success': True,
        'game_id': game.id,
        'game': game.serialize(),
        'map_consumed': map_consumed,
        'maps': int(user.maps or 0),
    })


@kingdom.route('/conquer/resolve_prelude_target', methods=['POST'])
@require_token
def conquer_resolve_prelude_target():
    """Resolve invader prelude target selection in conquer game_start flow."""
    data = request.json or {}
    game_id = data.get('game_id')
    spell_id = data.get('spell_id')
    target_figure_id = data.get('target_figure_id')

    if game_id is None or spell_id is None or target_figure_id is None:
        return jsonify({
            'success': False,
            'message': 'game_id, spell_id, and target_figure_id are required'
        }), 400

    game = db.session.get(Game, game_id)
    if not game or game.mode != 'conquer':
        return jsonify({'success': False, 'message': 'Conquer game not found'}), 404

    player = Player.query.filter_by(game_id=game.id, user_id=g.user_id).first()
    if not player:
        return jsonify({'success': False, 'message': 'Player not found in game'}), 403

    if player.id != game.invader_player_id:
        return jsonify({
            'success': False,
            'message': 'Only the invader can resolve prelude targets'
        }), 403

    if game.turn_player_id != player.id:
        return jsonify({'success': False, 'message': 'Not your turn'}), 400

    spell = db.session.get(ActiveSpell, spell_id)
    if not spell or spell.game_id != game.id or spell.player_id != player.id:
        return jsonify({'success': False, 'message': 'Prelude spell not found'}), 404

    effect_data = dict(spell.effect_data or {})
    if not effect_data.get('prelude_pending_target'):
        return jsonify({
            'success': False,
            'message': 'Spell is not waiting for target selection'
        }), 400

    valid_targets = _list_valid_prelude_targets(game, player.id, spell.spell_name)
    if not valid_targets:
        _mark_prelude_spell_no_target(spell)
        db.session.commit()
        return jsonify({
            'success': False,
            'message': f'No valid target is available for {spell.spell_name}.',
            'reason': 'no_valid_target',
            'game': game.serialize(),
        }), 400

    valid_target_ids = {f.id for f in valid_targets}
    if target_figure_id not in valid_target_ids:
        return jsonify({
            'success': False,
            'message': 'Selected figure is not a valid target.',
            'reason': 'invalid_target',
            'valid_target_ids': sorted(valid_target_ids),
        }), 400

    spell.target_figure_id = target_figure_id
    spell.is_active = True
    effect_data.pop('prelude_pending_target', None)
    effect_data.pop('valid_target_ids', None)
    effect_data['prelude_origin'] = True
    effect_data['prelude_status'] = 'executing'
    spell.effect_data = effect_data

    from routes.spells import _execute_spell
    result = _execute_spell(spell, game, player)
    if result.get('error'):
        spell.is_active = False
        failed_data = dict(spell.effect_data or {})
        failed_data['prelude_origin'] = True
        failed_data['prelude_status'] = 'failed'
        spell.effect_data = failed_data
        db.session.commit()
        return jsonify({
            'success': False,
            'message': result.get('effect', 'Failed to execute prelude spell.'),
            'reason': 'spell_execution_failed',
            'spell_effect': result,
            'game': game.serialize(),
        }), 400

    resolved_data = dict(spell.effect_data or {})
    resolved_data['prelude_origin'] = True
    resolved_data['prelude_status'] = 'executed'
    drawn = result.get('drawn_cards', [])
    if drawn:
        resolved_data['drawn_card_ids'] = [c['id'] for c in drawn]
    for key in (
        'target_figure_id', 'power_modifier', 'spell_icon',
        'destroyed_figure_name', 'card_count', 'caster_dumped',
        'opponent_dumped', 'caster_dumped_cards', 'opponent_dumped_cards',
        'drawn_cards', 'opponent_drawn_cards', 'cards_given',
        'cards_received', 'opponent_notification',
    ):
        if key in result:
            resolved_data[key] = result[key]
    spell.effect_data = resolved_data

    db.session.commit()
    return jsonify({
        'success': True,
        'message': f'{spell.spell_name} was applied successfully.',
        'spell_effect': result,
        'game': game.serialize(),
    })


# ── Activity serialization helpers ───────────────────────────────────────────

def _serialize_attack_activity(log, role=None):
    """Serialize a land attack log with usernames, land position, and role."""
    land = db.session.get(Land, log.land_id)
    attacker = db.session.get(User, log.attacker_user_id)
    defender = db.session.get(User, log.defender_user_id) if log.defender_user_id else None
    entry = log.serialize()
    entry['source'] = 'attack_log'
    entry['land_col'] = land.col if land else None
    entry['land_row'] = land.row if land else None
    entry['attacker_username'] = attacker.username if attacker else None
    entry['defender_username'] = defender.username if defender else 'AI'
    if role:
        entry['role'] = role
        entry['seen'] = (log.seen_by_attacker if role == 'attacker'
                         else log.seen_by_defender)
    direction = None
    if role == 'attacker':
        direction = 'gained' if log.result == 'attacker_won' else 'lost'
    elif role == 'defender':
        direction = 'lost' if log.result == 'attacker_won' else 'gained'
    if direction:
        loot_event = KingdomLootEvent.query.filter_by(
            attack_log_id=log.id,
            user_id=g.user_id,
            direction=direction,
        ).order_by(KingdomLootEvent.id.desc()).first()
        if loot_event:
            entry['loot_cards'] = loot_event.cards or []
            entry['loot_card_count'] = len(loot_event.cards or [])
            entry['loot_direction'] = direction
    entry.update(_attack_activity_presentation(entry))
    entry['activity_land_label'] = _activity_land_label(entry)
    return entry


def _activity_card_detail(entry, won=False, lost=False):
    """Return a short card outcome detail for an activity row."""
    loot_direction = entry.get('loot_direction')
    if won and loot_direction == 'gained':
        return _activity_loot_detail(entry, 'Loot gained')
    if lost and loot_direction == 'lost':
        return _activity_loot_detail(entry, 'Loot lost')
    if won:
        return _activity_card_pair_detail(
            entry, 'card_won_suit', 'card_won_rank', 'Loot gained')
    if lost:
        return _activity_card_pair_detail(
            entry, 'card_lost_suit', 'card_lost_rank', 'Loot lost')
    return ''


def _activity_loot_detail(entry, label):
    cards = entry.get('loot_cards') or []
    count = int(entry.get('loot_card_count') or len(cards or []))
    if not count:
        return ''
    first = cards[0] if cards else {}
    first_label = ''
    if first.get('rank') and first.get('suit'):
        first_label = f" ({first.get('rank')} of {first.get('suit')}"
        if count > 1:
            first_label += f' + {count - 1} more'
        first_label += ')'
    noun = 'card' if count == 1 else 'cards'
    return f'{label}: {count} {noun}{first_label}'


def _activity_card_pair_detail(entry, suit_key, rank_key, label):
    suit = entry.get(suit_key)
    rank = entry.get(rank_key)
    if suit and rank:
        return f'{label}: {rank} of {suit}'
    return ''


def _attack_activity_presentation(entry):
    """Presentation contract for attack log rows.

    ``activity_tone`` is one of ``good``, ``bad``, or ``neutral`` from the
    current user's perspective when ``role`` is present.
    """
    attacker = entry.get('attacker_username') or entry.get('attacker_name') or 'Unknown'
    defender = entry.get('defender_username') or 'AI'
    result = entry.get('result')
    role = entry.get('role')
    is_attacker_perspective = role == 'attacker'
    is_defender_perspective = role == 'defender'

    if result == 'attacker_won':
        if is_defender_perspective:
            deleted = entry.get('kingdom_deleted_name')
            detail = (f'{deleted} had no lands left and was dissolved.' if deleted
                      else _activity_loot_detail(entry, 'Loot lost')
                      or _activity_card_pair_detail(
                          entry, 'card_won_suit', 'card_won_rank', 'Loot lost')
                      or _activity_card_pair_detail(
                          entry, 'card_lost_suit', 'card_lost_rank', 'Loot lost')
                      or 'Land ownership changed.')
            return {
                'activity_title': f'{attacker} conquered your land',
                'activity_detail': detail,
                'activity_tone': 'bad',
            }
        if is_attacker_perspective:
            return {
                'activity_title': f'You conquered {defender}',
                'activity_detail': _activity_card_detail(entry, won=True) or 'Attack succeeded.',
                'activity_tone': 'good',
            }
        return {
            'activity_title': f'{attacker} conquered {defender}',
            'activity_detail': _activity_card_detail(entry, won=True) or 'Attack succeeded.',
            'activity_tone': 'neutral',
        }

    if result == 'defender_won':
        if is_defender_perspective:
            return {
                'activity_title': f'{attacker} failed to conquer you',
                'activity_detail': _activity_loot_detail(entry, 'Loot gained')
                    or _activity_card_pair_detail(
                    entry, 'card_lost_suit', 'card_lost_rank', 'Loot gained')
                    or _activity_card_pair_detail(
                        entry, 'card_won_suit', 'card_won_rank', 'Loot gained')
                    or 'Your defence held.',
                'activity_tone': 'good',
            }
        if is_attacker_perspective:
            return {
                'activity_title': f'Your attack on {defender} failed',
                'activity_detail': _activity_card_detail(entry, lost=True) or 'Attack failed.',
                'activity_tone': 'bad',
            }
        return {
            'activity_title': f'{attacker} failed against {defender}',
            'activity_detail': _activity_card_detail(entry, lost=True) or 'Attack failed.',
            'activity_tone': 'neutral',
        }

    if is_defender_perspective:
        title = f'{attacker} failed to conquer you'
    elif is_attacker_perspective:
        title = f'Attack on {defender} updated'
    else:
        title = f'{attacker} vs {defender}'
    return {
        'activity_title': title,
        'activity_detail': 'Battle result updated.',
        'activity_tone': 'neutral',
    }


def _kingdom_event_activity_presentation(entry):
    """Presentation contract for KingdomNotification rows."""
    kind = entry.get('kind') or ''
    payload = entry.get('payload') or {}
    if kind == 'xp_gained':
        amount = int(payload.get('amount') or 0)
        reason = payload.get('reason') or 'conquer'
        level = int(payload.get('level') or 0)
        return {
            'activity_title': f'+{amount} XP gained',
            'activity_detail': (f'Kingdom level {level} ({reason}).'
                                if level else f'Earned from {reason}.'),
            'activity_tone': 'good',
        }
    if kind == 'level_up':
        new_level = int(payload.get('new_level') or 0)
        sp = int(payload.get('sp_gained') or 0)
        return {
            'activity_title': f'Kingdom reached level {new_level}!',
            'activity_detail': (f'+{sp} skill point{"s" if sp != 1 else ""}.'
                                if sp else 'Level up!'),
            'activity_tone': 'good',
        }
    if kind == 'kingdoms_merged':
        absorbed = payload.get('absorbed_kingdom_name') or 'A kingdom'
        lands = int(payload.get('absorbed_lands') or 0)
        xp = int(payload.get('xp_awarded') or 0)
        return {
            'activity_title': 'Kingdoms merged',
            'activity_detail': f'{absorbed} absorbed ({lands} lands, +{xp} XP).',
            'activity_tone': 'good',
        }
    if kind == 'card_looted':
        rank = payload.get('rank') or '?'
        suit = payload.get('suit') or 'card'
        defender = payload.get('defender_name')
        if not defender and payload.get('is_ai_defender'):
            defender = 'AI defender'
        return {
            'activity_title': 'Card looted',
            'activity_detail': f'{rank} of {suit} lost to {defender or "the defender"}.',
            'activity_tone': 'bad',
        }
    if kind == 'shield_expired':
        name = payload.get('kingdom_name') or 'Your kingdom'
        return {
            'activity_title': 'Shield expired',
            'activity_detail': f'{name} can be attacked again.',
            'activity_tone': 'bad',
        }
    if kind == 'kingdom_dissolved':
        name = payload.get('kingdom_name') or 'Your kingdom'
        return {
            'activity_title': 'Kingdom dissolved',
            'activity_detail': f'{name} had no lands left.',
            'activity_tone': 'bad',
        }
    if kind == 'skill_downgraded':
        skill = payload.get('skill') or 'A skill'
        return {
            'activity_title': 'Skill downgraded',
            'activity_detail': f'{skill} level decreased.',
            'activity_tone': 'bad',
        }
    return {
        'activity_title': (kind or 'Kingdom event').replace('_', ' ').capitalize(),
        'activity_detail': '',
        'activity_tone': 'neutral',
    }


def _activity_land_label(entry):
    """Return a normalized land/kingdom label for activity rows."""
    payload = entry.get('payload') if isinstance(entry.get('payload'), dict) else {}
    col = entry.get('land_col')
    row = entry.get('land_row')
    land_id = entry.get('land_id')
    if col is None:
        col = payload.get('land_col')
    if row is None:
        row = payload.get('land_row')
    if land_id is None:
        land_id = payload.get('land_id')
    if col is not None and row is not None:
        return f'Land ({col}, {row})'
    if land_id is not None:
        return f'Land #{land_id}'
    kingdom_name = payload.get('kingdom_name') or payload.get('absorbed_kingdom_name')
    return kingdom_name or 'Kingdom event'


def _serialize_kingdom_notification_activity(notification):
    """Serialize a KingdomNotification with activity presentation fields."""
    entry = notification.serialize()
    entry.update(_kingdom_event_activity_presentation(entry))
    entry['activity_land_label'] = _activity_land_label(entry)
    return entry


def _serialize_kingdom_message_activity(message, current_user_id):
    """Serialize a user message with activity presentation fields."""
    entry = message.serialize()
    is_sent = entry.get('sender_user_id') == current_user_id
    other = entry.get('recipient_username') if is_sent else entry.get('sender_username')
    other = other or 'Unknown'
    entry['activity_role'] = 'sender' if is_sent else 'recipient'
    entry['activity_title'] = f'To {other}' if is_sent else f'From {other}'
    entry['activity_detail'] = entry.get('message') or ''
    entry['activity_tone'] = 'neutral'
    entry['activity_land_label'] = _activity_land_label(entry)
    return entry


# ── GET /kingdom/notifications ───────────────────────────────────────────────

@kingdom.route('/notifications', methods=['GET'])
@require_token
def kingdom_notifications():
    """Return unseen kingdom notifications for the current user.

    Merges legacy attack-result rows from ``LandAttackLog`` with the new
    ``KingdomNotification`` stream (skill downgrades, kingdom dissolution,
    shield expiry).  Lazy: emits a ``shield_expired`` notification on read
    if a previously active shield has lapsed.
    """
    from sqlalchemy import and_, or_
    from kingdom_service import reconcile_user_kingdoms
    from models import KingdomNotification

    try:
        reconcile_user_kingdoms(g.user_id, commit=False)
    except Exception as exc:
        logger.warning('reconcile failed in /notifications: %s', exc)

    # Lazy shield-expired emission.
    now = _utcnow()
    owned_kingdoms = KingdomModel.query.filter_by(owner_user_id=g.user_id).all()
    for k in owned_kingdoms:
        if not k.shield_until or k.shield_until > now:
            continue
        expiry_iso = k.shield_until.isoformat()
        existing = KingdomNotification.query.filter_by(
            user_id=g.user_id,
            kind='shield_expired',
            kingdom_id=k.id,
        ).order_by(KingdomNotification.created_at.desc()).first()
        if existing and (existing.payload or {}).get('expiry') == expiry_iso:
            continue
        db.session.add(KingdomNotification(
            user_id=g.user_id,
            kind='shield_expired',
            kingdom_id=k.id,
            payload={'expiry': expiry_iso, 'kingdom_name': k.name},
        ))
    db.session.commit()

    logs = LandAttackLog.query.filter(
        or_(
            and_(LandAttackLog.attacker_user_id == g.user_id,
                 LandAttackLog.seen_by_attacker == False),
            and_(LandAttackLog.defender_user_id == g.user_id,
                 LandAttackLog.seen_by_defender == False),
        )
    ).order_by(LandAttackLog.timestamp.desc()).all()

    result = []
    for log in logs:
        role = 'attacker' if log.attacker_user_id == g.user_id else 'defender'
        result.append(_serialize_attack_activity(log, role=role))

    kingdom_notifs = KingdomNotification.query.filter_by(
        user_id=g.user_id, seen=False
    ).order_by(KingdomNotification.created_at.desc()).all()
    for n in kingdom_notifs:
        result.append(_serialize_kingdom_notification_activity(n))

    result.sort(key=lambda entry: entry.get('timestamp') or '', reverse=True)

    return jsonify({'success': True, 'notifications': result})


# ── POST /kingdom/notifications/mark_seen ───────────────────────────────────

@kingdom.route('/notifications/mark_seen', methods=['POST'])
@require_token
def kingdom_notifications_mark_seen():
    """Mark kingdom notifications as seen.

    Prefer typed ID lists so unrelated ``LandAttackLog`` and
    ``KingdomNotification`` rows with the same numeric ID cannot accidentally
    mark each other.  The legacy ``notification_ids`` list is still accepted
    for older clients.
    """
    from models import KingdomNotification

    data = request.json or {}
    typed_payload = ('attack_log_ids' in data or 'kingdom_notification_ids' in data)
    if typed_payload:
        attack_log_ids = data.get('attack_log_ids') or []
        kingdom_notification_ids = data.get('kingdom_notification_ids') or []
        if not isinstance(attack_log_ids, list) or not isinstance(kingdom_notification_ids, list):
            return jsonify({'success': False,
                            'message': 'typed notification IDs must be lists'}), 400
        if not attack_log_ids and not kingdom_notification_ids:
            return jsonify({'success': False,
                            'message': 'at least one notification ID is required'}), 400
    else:
        notification_ids = data.get('notification_ids', [])
        if not notification_ids or not isinstance(notification_ids, list):
            return jsonify({'success': False,
                            'message': 'notification_ids is required'}), 400
        attack_log_ids = notification_ids
        kingdom_notification_ids = notification_ids

    attacker_updated = LandAttackLog.query.filter(
        LandAttackLog.id.in_(attack_log_ids),
        LandAttackLog.attacker_user_id == g.user_id,
    ).update({'seen_by_attacker': True}, synchronize_session='fetch')
    defender_updated = LandAttackLog.query.filter(
        LandAttackLog.id.in_(attack_log_ids),
        LandAttackLog.defender_user_id == g.user_id,
    ).update({'seen_by_defender': True}, synchronize_session='fetch')
    kingdom_updated = KingdomNotification.query.filter(
        KingdomNotification.id.in_(kingdom_notification_ids),
        KingdomNotification.user_id == g.user_id,
    ).update({'seen': True}, synchronize_session='fetch')

    db.session.commit()

    return jsonify({
        'success': True,
        'marked': attacker_updated + defender_updated + kingdom_updated,
    })


# ── Defender-only attack notification compatibility endpoints ───────────────

def _maybe_deprecate_attack_notifications_response(response):
    """Mark legacy defender-only notification endpoints as deprecated."""
    if request.path.startswith('/kingdom/attack_notifications'):
        response.headers['Deprecation'] = 'true'
        response.headers['Link'] = '</kingdom/notifications>; rel="successor-version"'
        response.headers['Warning'] = (
            '299 - "/kingdom/attack_notifications is defender-only and deprecated; '
            'use /kingdom/notifications"'
        )
    return response


def _defender_attack_notifications_payload():
    """Return unseen attack logs where the current user was the defender."""
    logs = LandAttackLog.query.filter_by(
        defender_user_id=g.user_id,
        seen_by_defender=False,
    ).order_by(LandAttackLog.timestamp.desc()).all()

    result = []
    for log in logs:
        result.append(_serialize_attack_activity(log, role='defender'))

    return {'success': True, 'notifications': result}


# ── GET /kingdom/defender_attack_notifications ──────────────────────────────

@kingdom.route('/defender_attack_notifications', methods=['GET'])
@kingdom.route('/attack_notifications', methods=['GET'])
@require_token
def attack_notifications():
    """Return defender-only unseen attack logs.

    Prefer unified ``/kingdom/notifications`` for new clients.  The clearer
    ``/kingdom/defender_attack_notifications`` alias is retained for callers
    that explicitly need defender-only rows.
    """
    return _maybe_deprecate_attack_notifications_response(
        jsonify(_defender_attack_notifications_payload()))


# ── POST /kingdom/defender_attack_notifications/mark_seen ───────────────────

@kingdom.route('/defender_attack_notifications/mark_seen', methods=['POST'])
@kingdom.route('/attack_notifications/mark_seen', methods=['POST'])
@require_token
def attack_notifications_mark_seen():
    """Mark defender-only attack notifications as seen."""
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

    return _maybe_deprecate_attack_notifications_response(
        jsonify({'success': True, 'marked': updated}))


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
        role = 'attacker' if log.attacker_user_id == g.user_id else 'defender'
        results.append(_serialize_attack_activity(log, role=role))

    return jsonify({
        'success': True,
        'history': results,
        'page': pagination.page,
        'pages': pagination.pages,
        'total': pagination.total,
    })


# ── Kingdom user messages ───────────────────────────────────────────────────

_MAX_KINGDOM_MESSAGE = 500


@kingdom.route('/messages', methods=['GET'])
@require_token
def kingdom_messages():
    """Return recent kingdom messages sent or received by the current user."""
    from kingdom_service import reconcile_user_kingdoms
    try:
        reconcile_user_kingdoms(g.user_id, commit=False)
    except Exception as exc:
        logger.warning('reconcile failed in /messages: %s', exc)
    limit = max(1, min(request.args.get('limit', 30, type=int), 50))
    messages = KingdomMessage.query.filter(
        db.or_(
            KingdomMessage.sender_user_id == g.user_id,
            KingdomMessage.recipient_user_id == g.user_id,
        )
    ).order_by(KingdomMessage.timestamp.desc()).limit(limit).all()
    unread_count = KingdomMessage.query.filter_by(
        recipient_user_id=g.user_id,
        seen_by_recipient=False,
    ).count()
    return jsonify({
        'success': True,
        'messages': [_serialize_kingdom_message_activity(m, g.user_id) for m in messages],
        'unread_count': unread_count,
    })


@kingdom.route('/messages', methods=['POST'])
@require_token
def kingdom_messages_send():
    """Send a kingdom-layer message to another user."""
    data = request.json or {}
    raw_message = data.get('message', data.get('body', ''))
    message = str(raw_message or '').strip()
    if not message:
        return jsonify({'success': False, 'message': 'Message is required'}), 400

    recipient = None
    recipient_id = data.get('recipient_user_id') or data.get('recipient_id')
    if recipient_id is not None:
        try:
            recipient = db.session.get(User, int(recipient_id))
        except (TypeError, ValueError):
            recipient = None
    elif data.get('recipient_username'):
        recipient = User.query.filter_by(username=data.get('recipient_username')).first()

    if not recipient:
        return jsonify({'success': False, 'message': 'Recipient not found'}), 404
    if recipient.id == g.user_id:
        return jsonify({'success': False, 'message': 'Cannot message yourself'}), 400
    if recipient.is_ai:
        return jsonify({'success': False, 'message': 'Cannot message AI defenders'}), 400

    land_id = data.get('land_id')
    if land_id in ('', None):
        land_id = None
    else:
        try:
            land_id = int(land_id)
        except (TypeError, ValueError):
            return jsonify({'success': False, 'message': 'Invalid land_id'}), 400
        if not db.session.get(Land, land_id):
            return jsonify({'success': False, 'message': 'Land not found'}), 404

    msg = KingdomMessage(
        sender_user_id=g.user_id,
        recipient_user_id=recipient.id,
        land_id=land_id,
        message=message[:_MAX_KINGDOM_MESSAGE],
    )
    db.session.add(msg)
    db.session.commit()
    return jsonify({
        'success': True,
        'message': 'Message sent',
        'kingdom_message': msg.serialize(),
    })


@kingdom.route('/messages/mark_seen', methods=['POST'])
@require_token
def kingdom_messages_mark_seen():
    """Mark received kingdom messages as read."""
    data = request.json or {}
    message_ids = data.get('message_ids', [])
    if not message_ids or not isinstance(message_ids, list):
        return jsonify({'success': False,
                        'message': 'message_ids is required'}), 400

    updated = KingdomMessage.query.filter(
        KingdomMessage.id.in_(message_ids),
        KingdomMessage.recipient_user_id == g.user_id,
    ).update({'seen_by_recipient': True}, synchronize_session='fetch')
    db.session.commit()
    return jsonify({'success': True, 'marked': updated})
