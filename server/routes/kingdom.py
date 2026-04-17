# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Kingdom routes — gold production, land management."""

import math
import logging
from datetime import datetime, timezone
from flask import Blueprint, jsonify, g

from models import db, User, Land
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
