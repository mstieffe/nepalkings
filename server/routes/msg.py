# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
from flask import Blueprint, request, jsonify, g
from sqlalchemy.orm import joinedload
from models import db, LogEntry, ChatMessage, Player, User
import logging

import server_settings as settings
from routes.auth import require_token, verify_player_ownership

msg = Blueprint('msg', __name__)

logger = logging.getLogger('nepalkings.routes.msg')

# ── Message length limits ──
_MAX_LOG_MESSAGE = 500
_MAX_CHAT_MESSAGE = 1000


def _ai_explain_replies_for_message(game_id, sender_id, receiver_id, message):
    """Return AI tactical explain replies for human->AI command messages."""
    sender = db.session.get(Player, sender_id)
    receiver = db.session.get(Player, receiver_id)
    if not sender or not receiver:
        return []
    if sender.game_id != game_id or receiver.game_id != game_id:
        return []

    sender_user = db.session.get(User, sender.user_id)
    receiver_user = db.session.get(User, receiver.user_id)
    if not sender_user or not receiver_user:
        return []

    # Only human->AI chats may trigger explain control responses.
    if sender_user.is_ai or not receiver_user.is_ai:
        return []

    try:
        from ai.ai_worker import handle_explain_chat_control

        return handle_explain_chat_control(
            game_id=game_id,
            ai_player_id=receiver_id,
            human_player_id=sender_id,
            message=message,
        )
    except Exception:
        logger.exception('Failed to evaluate AI explain command')
        return []

@msg.route('/add_log_entry', methods=['POST'])
@require_token
def add_log_entry():
    try:
        data = request.json
        game_id = data['game_id']
        player_id = data.get('player_id')  # Optional, as system messages may not have a player

        if player_id:
            err = verify_player_ownership(player_id)
            if err:
                return err

        round_number = data['round_number']
        turn_number = data['turn_number']
        message = data['message'][:_MAX_LOG_MESSAGE] if data.get('message') else ''
        author = data['author']
        type = data['type']

        log_entry = LogEntry(
            game_id=game_id,
            player_id=player_id,
            round_number=round_number,
            turn_number=turn_number,
            message=message,
            author=author,
            type=type
        )
        db.session.add(log_entry)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Log entry added successfully', 'log_entry': log_entry.serialize()})

    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to add log entry')
        return jsonify({'success': False, 'message': 'Failed to add log entry'}), 400

@msg.route('/get_log_entries', methods=['GET'])
def get_log_entries():
    try:
        game_id = request.args.get('game_id')

        if not game_id:
            return jsonify({'success': False, 'message': 'Game ID is required'}), 400

        log_entries = LogEntry.query.filter_by(game_id=game_id).order_by(LogEntry.timestamp).all()

        return jsonify({'success': True, 'log_entries': [entry.serialize() for entry in log_entries]})

    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to get log entries')
        return jsonify({'success': False, 'message': 'Failed to get log entries'}), 400


@msg.route('/add_chat_message', methods=['POST'])
@require_token
def add_chat_message():
    try:
        data = request.json
        game_id = data['game_id']
        sender_id = data['sender_id']

        err = verify_player_ownership(sender_id)
        if err:
            return err

        receiver_id = data['receiver_id']
        message = data['message'][:_MAX_CHAT_MESSAGE] if data.get('message') else ''
        ai_reply_lines = _ai_explain_replies_for_message(game_id, sender_id, receiver_id, message)

        chat_message = ChatMessage(
            game_id=game_id,
            sender_id=sender_id,
            receiver_id=receiver_id,
            message=message
        )
        db.session.add(chat_message)

        ai_auto_messages = []
        for line in ai_reply_lines:
            reply = str(line or '').strip()
            if not reply:
                continue
            ai_message = ChatMessage(
                game_id=game_id,
                sender_id=receiver_id,
                receiver_id=sender_id,
                message=reply[:_MAX_CHAT_MESSAGE],
            )
            db.session.add(ai_message)
            ai_auto_messages.append(ai_message)

        db.session.commit()

        response_payload = {
            'success': True,
            'message': 'Chat message sent successfully',
            'chat_message': chat_message.serialize(),
        }
        if ai_auto_messages:
            response_payload['ai_auto_messages'] = [m.serialize() for m in ai_auto_messages]

        return jsonify(response_payload)

    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to send chat message')
        return jsonify({'success': False, 'message': 'Failed to send chat message'}), 400


@msg.route('/get_chat_messages', methods=['GET'])
def get_chat_messages():
    try:
        game_id = request.args.get('game_id')

        if not game_id:
            return jsonify({'success': False, 'message': 'Game ID is required'}), 400

        chat_messages = ChatMessage.query.filter_by(game_id=game_id).order_by(ChatMessage.timestamp).all()

        return jsonify({'success': True, 'chat_messages': [message.serialize() for message in chat_messages]})

    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to get chat messages')
        return jsonify({'success': False, 'message': 'Failed to get chat messages'}), 400
