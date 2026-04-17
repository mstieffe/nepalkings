# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Kingdom routes — gold production, land management."""

import math
import logging
from datetime import datetime, timezone
from flask import Blueprint, jsonify, g

from models import db, User, Land, LandAttackLog
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
