# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Onboarding guide, milestone, and reward endpoints."""

from flask import Blueprint, jsonify, request, g

from models import db, User
from analytics import track
from routes.auth import require_token
from onboarding_service import (
    DUEL_HINT_IDS,
    MENU_HINT_IDS,
    claim_reward,
    mark_duel_hint,
    mark_menu_hint,
    mark_welcome_seen,
    reset_onboarding,
    resume_onboarding,
    serialize_onboarding_state,
    skip_onboarding,
)


onboarding = Blueprint('onboarding', __name__)


def _current_user():
    return db.session.get(User, g.user_id)


@onboarding.route('/state', methods=['GET'])
@require_token
def get_onboarding_state():
    user = _current_user()
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404
    onboarding_payload = serialize_onboarding_state(user)
    db.session.commit()
    return jsonify({
        'success': True,
        'onboarding': onboarding_payload,
    })


@onboarding.route('/mark_tip', methods=['POST'])
@require_token
def mark_tip():
    user = _current_user()
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404
    data = request.get_json(silent=True) or {}
    tip_key = data.get('tip_key') or data.get('hint_id')
    if tip_key == 'welcome':
        mark_welcome_seen(user, commit=True)
    elif isinstance(tip_key, str) and tip_key.startswith('duel:'):
        hint_id = tip_key.split(':', 1)[1]
        if hint_id not in DUEL_HINT_IDS:
            return jsonify({'success': False, 'message': 'Unknown tip'}), 400
        mark_duel_hint(user, hint_id, commit=True)
    elif isinstance(tip_key, str) and tip_key.startswith('menu:'):
        hint_id = tip_key.split(':', 1)[1]
        if hint_id not in MENU_HINT_IDS:
            return jsonify({'success': False, 'message': 'Unknown tip'}), 400
        mark_menu_hint(user, hint_id, commit=True)
    elif isinstance(tip_key, str):
        if tip_key not in DUEL_HINT_IDS:
            return jsonify({'success': False, 'message': 'Unknown tip'}), 400
        mark_duel_hint(user, tip_key, commit=True)
    else:
        return jsonify({'success': False, 'message': 'Missing tip_key'}), 400
    return jsonify({
        'success': True,
        'onboarding': serialize_onboarding_state(user),
    })


@onboarding.route('/claim_reward', methods=['POST'])
@require_token
def claim_onboarding_reward():
    user = _current_user()
    data = request.get_json(silent=True) or {}
    reward_id = data.get('reward_id') or data.get('step_id') or data.get('goal_id')
    if not reward_id:
        return jsonify({'success': False, 'message': 'Missing reward_id'}), 400
    payload, status = claim_reward(user, reward_id, commit=True)
    if status == 200 and payload.get('success'):
        track('onboarding_reward_claimed', user_id=user.id if user else None,
              reward_id=reward_id)
        db.session.commit()
    return jsonify(payload), status


@onboarding.route('/skip', methods=['POST'])
@require_token
def skip_onboarding_route():
    user = _current_user()
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404
    skip_onboarding(user, commit=True)
    track('onboarding_skipped', user_id=user.id)
    db.session.commit()
    return jsonify({
        'success': True,
        'onboarding': serialize_onboarding_state(user),
    })


@onboarding.route('/resume', methods=['POST'])
@require_token
def resume_onboarding_route():
    user = _current_user()
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404
    resume_onboarding(user, commit=True)
    return jsonify({
        'success': True,
        'onboarding': serialize_onboarding_state(user),
    })


@onboarding.route('/reset', methods=['POST'])
@require_token
def reset_onboarding_route():
    user = _current_user()
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404
    reset_onboarding(user, commit=True)
    return jsonify({
        'success': True,
        'onboarding': serialize_onboarding_state(user),
    })
