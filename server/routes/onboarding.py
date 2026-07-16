# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Onboarding guide, milestone, and reward endpoints."""

from flask import Blueprint, jsonify, request, g

from models import db, CollectionCard, User
from analytics import track
from routes.auth import require_token
from onboarding_service import (
    DUEL_HINT_IDS,
    MENU_HINT_IDS,
    claim_reward,
    complete_starter_suit_reveal,
    complete_tutorial,
    mark_duel_hints,
    mark_menu_hints,
    mark_welcome_seen,
    prepare_starter_suit_reveal,
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


def _starter_cards_payload(user, suit):
    """Return truthful post-grant Collection counts for the starter ranks."""
    import server_settings as settings
    starter_ranks = {rank for rank, _value in settings.STARTER_OFFENSIVE_SET}
    totals = {rank: 0 for rank in starter_ranks}
    locked = {rank: 0 for rank in starter_ranks}
    for card in CollectionCard.query.filter_by(user_id=user.id, suit=suit).all():
        if card.rank not in starter_ranks:
            continue
        totals[card.rank] += 1
        if card.locked:
            locked[card.rank] += 1
    return [
        {
            'suit': suit,
            'rank': rank,
            'total': totals[rank],
            'locked': locked[rank],
        }
        for rank in sorted(starter_ranks)
    ]


@onboarding.route('/starter_reveal/prepare', methods=['POST'])
@require_token
def prepare_starter_reveal_route():
    user = _current_user()
    suit, error = prepare_starter_suit_reveal(user, commit=False)
    if error:
        return jsonify({'success': False, 'message': error}), 400
    payload = serialize_onboarding_state(user)
    db.session.commit()
    return jsonify({
        'success': True,
        'suit': suit,
        'onboarding': payload,
    })


@onboarding.route('/starter_reveal/complete', methods=['POST'])
@require_token
def complete_starter_reveal_route():
    user = _current_user()
    suit, error = complete_starter_suit_reveal(user, commit=False)
    if error:
        return jsonify({'success': False, 'message': error}), 400
    payload = serialize_onboarding_state(user)
    track('tutorial_step_completed', user_id=user.id,
          track='menu', step_id='starter_suit_reveal',
          coach_version=payload.get('coach_version'))
    cards = _starter_cards_payload(user, suit)
    db.session.commit()
    return jsonify({
        'success': True,
        'suit': suit,
        'starter_cards': cards,
        'onboarding': payload,
    })


@onboarding.route('/mark_tip', methods=['POST'])
@require_token
def mark_tip():
    user = _current_user()
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404
    data = request.get_json(silent=True) or {}
    raw_keys = data.get('tip_keys')
    if raw_keys is None:
        raw_keys = [data.get('tip_key') or data.get('hint_id')]
    if not isinstance(raw_keys, list) or not raw_keys or len(raw_keys) > 32:
        return jsonify({'success': False, 'message': 'Missing tip_key'}), 400
    if any(not isinstance(key, str) or not key for key in raw_keys):
        return jsonify({'success': False, 'message': 'Invalid tip key'}), 400

    duel_ids = []
    menu_ids = []
    welcome = False
    for tip_key in raw_keys:
        if tip_key == 'welcome':
            welcome = True
        elif tip_key.startswith('duel:'):
            hint_id = tip_key.split(':', 1)[1]
            if hint_id not in DUEL_HINT_IDS:
                return jsonify({'success': False, 'message': 'Unknown tip'}), 400
            if hint_id not in duel_ids:
                duel_ids.append(hint_id)
        elif tip_key.startswith('menu:'):
            hint_id = tip_key.split(':', 1)[1]
            if hint_id not in MENU_HINT_IDS:
                return jsonify({'success': False, 'message': 'Unknown tip'}), 400
            if hint_id not in menu_ids:
                menu_ids.append(hint_id)
        elif tip_key in DUEL_HINT_IDS:
            if tip_key not in duel_ids:
                duel_ids.append(tip_key)
        else:
            return jsonify({'success': False, 'message': 'Unknown tip'}), 400

    before = serialize_onboarding_state(user)
    if welcome:
        mark_welcome_seen(user, commit=False)
    if duel_ids:
        mark_duel_hints(user, duel_ids, commit=False)
    if menu_ids:
        mark_menu_hints(user, menu_ids, commit=False)
    after = serialize_onboarding_state(user)
    before_duel = set(before.get('duel_hints_seen') or [])
    before_menu = set(before.get('menu_hints_seen') or [])
    if welcome and not before.get('welcome_seen') and after.get('welcome_seen'):
        track('tutorial_step_completed', user_id=user.id,
              track='welcome', step_id='welcome',
              coach_version=after.get('coach_version'))
    for hint_id in duel_ids:
        if hint_id not in before_duel:
            track('tutorial_step_completed', user_id=user.id,
                  track='duel', step_id=hint_id,
                  coach_version=after.get('coach_version'))
    for hint_id in menu_ids:
        if hint_id not in before_menu:
            track('tutorial_step_completed', user_id=user.id,
                  track='menu', step_id=hint_id,
                  coach_version=after.get('coach_version'))
    event = data.get('event')
    changed_ids = (
        [f'duel:{hint_id}' for hint_id in duel_ids if hint_id not in before_duel]
        + [f'menu:{hint_id}' for hint_id in menu_ids if hint_id not in before_menu]
    )
    if event == 'lesson_dismissed' and changed_ids:
        track('tutorial_lesson_dismissed', user_id=user.id,
              step_ids=changed_ids,
              coach_version=after.get('coach_version'))
    db.session.commit()
    response_payload = {
        'success': True,
        'onboarding': after,
    }
    if welcome:
        response_payload['balances'] = {
            'gold': int(user.gold or 0),
            'booster_packs': int(user.booster_packs or 0),
            'booster_packs_side': int(user.booster_packs_side or 0),
            'maps': int(user.maps or 0),
        }
    return jsonify(response_payload)


@onboarding.route('/complete_step', methods=['POST'])
@require_token
def complete_onboarding_step():
    user = _current_user()
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404
    data = request.get_json(silent=True) or {}
    step_id = data.get('step_id')
    if step_id != 'finish_tutorial':
        return jsonify({'success': False, 'message': 'Unknown completable step'}), 400
    changed, error = complete_tutorial(user, commit=False)
    if error:
        return jsonify({'success': False, 'message': error}), 400
    onboarding_payload = serialize_onboarding_state(user)
    if changed:
        track('tutorial_completed', user_id=user.id, step_id=step_id,
              coach_version=onboarding_payload.get('coach_version'))
    db.session.commit()
    return jsonify({
        'success': True,
        'already_completed': not changed,
        'onboarding': onboarding_payload,
    })


@onboarding.route('/claim_reward', methods=['POST'])
@require_token
def claim_onboarding_reward():
    user = _current_user()
    data = request.get_json(silent=True) or {}
    reward_id = data.get('reward_id') or data.get('step_id') or data.get('goal_id')
    if not reward_id:
        return jsonify({'success': False, 'message': 'Missing reward_id'}), 400
    payload, status = claim_reward(user, reward_id, commit=False)
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
    skip_onboarding(user, commit=False)
    track('onboarding_skipped', user_id=user.id)
    track('tutorial_paused', user_id=user.id)
    onboarding_payload = serialize_onboarding_state(user)
    db.session.commit()
    return jsonify({
        'success': True,
        'onboarding': onboarding_payload,
    })


@onboarding.route('/resume', methods=['POST'])
@require_token
def resume_onboarding_route():
    user = _current_user()
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404
    resume_onboarding(user, commit=False)
    track('tutorial_resumed', user_id=user.id)
    onboarding_payload = serialize_onboarding_state(user)
    db.session.commit()
    return jsonify({
        'success': True,
        'onboarding': onboarding_payload,
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
