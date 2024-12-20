from flask import Blueprint, request, jsonify
from sqlalchemy.orm import joinedload
from models import db, LogEntry, ChatMessage

import server_settings as settings

msg = Blueprint('msg', __name__)

@msg.route('/add_log_entry', methods=['POST'])
def add_log_entry():
    try:
        data = request.json
        game_id = data['game_id']
        player_id = data.get('player_id')  # Optional, as system messages may not have a player
        round_number = data['round_number']
        turn_number = data['turn_number']
        message = data['message']
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
        return jsonify({'success': False, 'message': f'Failed to add log entry: {str(e)}'}), 400

@msg.route('/get_log_entries', methods=['GET'])
def get_log_entries():
    try:
        game_id = request.args.get('game_id')

        if not game_id:
            return jsonify({'success': False, 'message': 'Game ID is required'}), 400

        log_entries = LogEntry.query.filter_by(game_id=game_id).order_by(LogEntry.timestamp).all()

        return jsonify({'success': True, 'log_entries': [entry.serialize() for entry in log_entries]})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to get log entries: {str(e)}'}), 400


@msg.route('/add_chat_message', methods=['POST'])
def add_chat_message():
    try:
        data = request.json
        game_id = data['game_id']
        sender_id = data['sender_id']
        receiver_id = data['receiver_id']
        message = data['message']

        chat_message = ChatMessage(
            game_id=game_id,
            sender_id=sender_id,
            receiver_id=receiver_id,
            message=message
        )
        db.session.add(chat_message)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Chat message sent successfully', 'chat_message': chat_message.serialize()})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to send chat message: {str(e)}'}), 400


@msg.route('/get_chat_messages', methods=['GET'])
def get_chat_messages():
    try:
        game_id = request.args.get('game_id')

        if not game_id:
            return jsonify({'success': False, 'message': 'Game ID is required'}), 400

        chat_messages = ChatMessage.query.filter_by(game_id=game_id).order_by(ChatMessage.timestamp).all()

        return jsonify({'success': True, 'chat_messages': [message.serialize() for message in chat_messages]})

    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to get chat messages: {str(e)}'}), 400
