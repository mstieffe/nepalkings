# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Player-facing report and block controls."""

from flask import Blueprint, g, jsonify, request

from models import (
    ChatMessage,
    db,
    Kingdom,
    KingdomMessage,
    Player,
    SafetyReport,
    User,
    UserBlock,
)
from routes.auth import require_token


safety = Blueprint('safety', __name__)

_REPORT_REASONS = {
    'harassment',
    'hate',
    'spam',
    'sexual_content',
    'threats',
    'cheating',
    'inappropriate_name',
    'other',
}
_CONTEXT_TYPES = {'user', 'duel_chat', 'kingdom_message', 'kingdom_name'}


def _request_data():
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form


def _resolve_target(data):
    target = None
    raw_id = data.get('reported_user_id') or data.get('user_id')
    if raw_id not in (None, ''):
        try:
            target = db.session.get(User, int(raw_id))
        except (TypeError, ValueError):
            target = None
    if target is None and data.get('username'):
        target = User.query.filter_by(
            username=str(data.get('username')).strip()).first()
    return target


def _context_evidence(context_type, context_id, target_user_id):
    """Validate that the reporter can see the context and snapshot it."""
    if context_type == 'user':
        return {'reported_username': (
            db.session.get(User, target_user_id).username)}

    if context_id is None:
        raise ValueError('context_id is required for this report context')

    if context_type == 'kingdom_name':
        item = db.session.get(Kingdom, context_id)
        if not item or item.owner_user_id != target_user_id:
            raise PermissionError('Kingdom is not available to report')
        return {
            'kingdom_id': item.id,
            'owner_user_id': item.owner_user_id,
            'kingdom_name': item.name,
        }

    if context_type == 'kingdom_message':
        item = db.session.get(KingdomMessage, context_id)
        if (
            not item
            or g.user_id not in (item.sender_user_id, item.recipient_user_id)
            or target_user_id != item.sender_user_id
        ):
            raise PermissionError('Message is not available to report')
        return {
            'message_id': item.id,
            'sender_user_id': item.sender_user_id,
            'recipient_user_id': item.recipient_user_id,
            'message': item.message,
            'timestamp': item.timestamp.isoformat() if item.timestamp else None,
        }

    item = db.session.get(ChatMessage, context_id)
    if not item:
        raise PermissionError('Message is not available to report')
    sender = db.session.get(Player, item.sender_id)
    receiver = db.session.get(Player, item.receiver_id)
    if (
        not sender
        or not receiver
        or g.user_id not in (sender.user_id, receiver.user_id)
        or target_user_id != sender.user_id
    ):
        raise PermissionError('Message is not available to report')
    return {
        'message_id': item.id,
        'game_id': item.game_id,
        'sender_user_id': sender.user_id,
        'receiver_user_id': receiver.user_id,
        'message': item.message,
        'timestamp': item.timestamp.isoformat() if item.timestamp else None,
    }


@safety.route('/reports', methods=['POST'])
@require_token
def create_report():
    data = _request_data()
    target = _resolve_target(data)
    if not target or target.is_ai or target.id == g.user_id:
        return jsonify({
            'success': False,
            'message': 'Select another player to report.',
        }), 400

    reason = str(data.get('reason') or '').strip().lower()
    if reason not in _REPORT_REASONS:
        return jsonify({
            'success': False,
            'message': 'Select a valid report reason.',
            'valid_reasons': sorted(_REPORT_REASONS),
        }), 400
    details = str(data.get('details') or '').strip()[:1000] or None
    context_type = str(data.get('context_type') or 'user').strip().lower()
    if context_type not in _CONTEXT_TYPES:
        return jsonify({
            'success': False,
            'message': 'Invalid report context.',
        }), 400
    raw_context_id = data.get('context_id')
    try:
        context_id = (
            int(raw_context_id) if raw_context_id not in (None, '') else None)
    except (TypeError, ValueError):
        return jsonify({
            'success': False,
            'message': 'Invalid context_id.',
        }), 400

    try:
        evidence = _context_evidence(
            context_type, context_id, target.id)
    except ValueError as exc:
        return jsonify({'success': False, 'message': str(exc)}), 400
    except PermissionError as exc:
        return jsonify({'success': False, 'message': str(exc)}), 403

    report = SafetyReport(
        reporter_user_id=g.user_id,
        reported_user_id=target.id,
        reason=reason,
        details=details,
        context_type=context_type,
        context_id=context_id,
        evidence=evidence,
    )
    db.session.add(report)
    db.session.commit()
    return jsonify({
        'success': True,
        'message': 'Report submitted. Thank you.',
        'report': report.serialize_for_reporter(),
    }), 201


@safety.route('/reports', methods=['GET'])
@require_token
def list_own_reports():
    reports = SafetyReport.query.filter_by(
        reporter_user_id=g.user_id,
    ).order_by(SafetyReport.created_at.desc()).limit(50).all()
    return jsonify({
        'success': True,
        'reports': [report.serialize_for_reporter() for report in reports],
    })


@safety.route('/blocks', methods=['POST'])
@require_token
def block_user():
    data = _request_data()
    target = _resolve_target(data)
    if not target or target.is_ai or target.id == g.user_id:
        return jsonify({
            'success': False,
            'message': 'Select another player to block.',
        }), 400
    row = UserBlock.query.filter_by(
        blocker_user_id=g.user_id,
        blocked_user_id=target.id,
    ).first()
    if row is None:
        db.session.add(UserBlock(
            blocker_user_id=g.user_id,
            blocked_user_id=target.id,
        ))
        db.session.commit()
    return jsonify({
        'success': True,
        'message': f'{target.username} is blocked.',
        'blocked_user_id': target.id,
        'blocked_username': target.username,
    })


@safety.route('/blocks/remove', methods=['POST'])
@require_token
def unblock_user():
    data = _request_data()
    target = _resolve_target(data)
    if not target:
        return jsonify({
            'success': False,
            'message': 'Player not found.',
        }), 404
    UserBlock.query.filter_by(
        blocker_user_id=g.user_id,
        blocked_user_id=target.id,
    ).delete(synchronize_session=False)
    db.session.commit()
    return jsonify({
        'success': True,
        'message': f'{target.username} is unblocked.',
    })


@safety.route('/blocks', methods=['GET'])
@require_token
def list_blocks():
    rows = UserBlock.query.filter_by(
        blocker_user_id=g.user_id,
    ).order_by(UserBlock.created_at.desc()).all()
    return jsonify({
        'success': True,
        'blocks': [
            {
                'user_id': row.blocked_user_id,
                'username': row.blocked.username if row.blocked else None,
                'created_at': (
                    row.created_at.isoformat() if row.created_at else None),
            }
            for row in rows
        ],
    })
