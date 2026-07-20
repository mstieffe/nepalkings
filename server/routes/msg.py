# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
from flask import Blueprint, request, jsonify, g
from sqlalchemy.orm import joinedload
from models import db, LogEntry, ChatMessage, Player
from moderation_service import (
    active_chat_mute,
    blocked_user_ids,
    direct_contact_blocked,
)
import logging

import server_settings as settings
from routes.auth import require_token, verify_game_membership, verify_player_ownership

msg = Blueprint('msg', __name__)

logger = logging.getLogger('nepalkings.routes.msg')

# ── Message length limits ──
_MAX_LOG_MESSAGE = 500
_MAX_CHAT_MESSAGE = 1000
_MAX_LOG_AUTHOR = 80
_MAX_LOG_TYPE = 50
_MAX_ROUND_TURN = 10000   # sane upper bound for round/turn counters


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
            player = db.session.get(Player, player_id)
            if not player or player.game_id != game_id:
                return jsonify({'success': False, 'message': 'Player not found in this game'}), 403
        else:
            membership_err = verify_game_membership(game_id)
            if membership_err:
                return membership_err

        try:
            round_number = int(data['round_number'])
            turn_number = int(data['turn_number'])
        except (ValueError, TypeError):
            return jsonify({'success': False, 'message': 'round_number and turn_number must be integers'}), 400
        if not (0 <= round_number <= _MAX_ROUND_TURN) or not (0 <= turn_number <= _MAX_ROUND_TURN):
            return jsonify({'success': False, 'message': 'round_number or turn_number out of range'}), 400

        message = data['message'][:_MAX_LOG_MESSAGE] if data.get('message') else ''
        author = str(data['author'])[:_MAX_LOG_AUTHOR]
        type = str(data['type'])[:_MAX_LOG_TYPE]

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
@require_token
def get_log_entries():
    try:
        game_id = request.args.get('game_id', type=int)

        if not game_id:
            return jsonify({'success': False, 'message': 'Game ID is required'}), 400
        membership_err = verify_game_membership(game_id)
        if membership_err:
            return membership_err

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
        sender = db.session.get(Player, sender_id)
        receiver = db.session.get(Player, receiver_id)
        if (
            not sender or sender.game_id != game_id
            or not receiver or receiver.game_id != game_id
        ):
            return jsonify({'success': False, 'message': 'Player not found in this game'}), 403
        if active_chat_mute(g.current_user):
            return jsonify({
                'success': False,
                'message': 'Chat is temporarily unavailable for this account.',
                'reason': 'chat_muted',
                'muted_until': g.current_user.chat_muted_until.isoformat(),
            }), 403
        if direct_contact_blocked(sender.user_id, receiver.user_id):
            return jsonify({
                'success': False,
                'message': 'Direct chat with this player is unavailable.',
                'reason': 'player_blocked',
            }), 403
        message = data['message'][:_MAX_CHAT_MESSAGE] if data.get('message') else ''
        if not message.strip():
            return jsonify({
                'success': False,
                'message': 'Message is required',
            }), 400

        chat_message = ChatMessage(
            game_id=game_id,
            sender_id=sender_id,
            receiver_id=receiver_id,
            message=message
        )
        db.session.add(chat_message)
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Chat message sent successfully',
            'chat_message': chat_message.serialize(),
        })

    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to send chat message')
        return jsonify({'success': False, 'message': 'Failed to send chat message'}), 400


@msg.route('/get_chat_messages', methods=['GET'])
@require_token
def get_chat_messages():
    try:
        game_id = request.args.get('game_id', type=int)

        if not game_id:
            return jsonify({'success': False, 'message': 'Game ID is required'}), 400
        membership_err = verify_game_membership(game_id)
        if membership_err:
            return membership_err

        query = ChatMessage.query.filter_by(game_id=game_id)
        hidden_user_ids = blocked_user_ids(g.user_id)
        if hidden_user_ids:
            hidden_player_ids = [
                player_id for (player_id,) in db.session.query(Player.id).filter(
                    Player.game_id == game_id,
                    Player.user_id.in_(hidden_user_ids),
                ).all()
            ]
            if hidden_player_ids:
                query = query.filter(
                    ChatMessage.sender_id.notin_(hidden_player_ids))
        chat_messages = query.order_by(ChatMessage.timestamp).all()

        return jsonify({'success': True, 'chat_messages': [message.serialize() for message in chat_messages]})

    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to get chat messages')
        return jsonify({'success': False, 'message': 'Failed to get chat messages'}), 400
