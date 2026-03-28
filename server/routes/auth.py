# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
# routes/auth.py
from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Player, Game
from datetime import datetime
import logging  # For logging errors instead of exposing them to the user

auth = Blueprint('auth', __name__)

@auth.route('/get_users', methods=['GET'])
def get_users():
    try:
        current_username = request.args.get('username')
        users = User.query.filter(User.username != current_username).all()

        serialized_users = [user.serialize() for user in users]

        return jsonify({'users': serialized_users})
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error fetching users: {e}")
        return jsonify({'success': False, 'message': 'An error occurred while fetching users'}), 500

@auth.route('/get_user', methods=['GET'])
def get_user():
    try:
        username = request.args.get('username')
        user = User.query.filter_by(username=username).first()

        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404

        serialized_user = user.serialize()

        return jsonify({'success': True, 'user': serialized_user})
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error fetching user: {e}")
        return jsonify({'success': False, 'message': 'An error occurred while fetching the user'}), 500

@auth.route('/register', methods=['POST'])
def register():
    try:
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            return jsonify({'success': False, 'message': 'Missing username or password'}), 400

        if User.query.filter_by(username=username).first():
            return jsonify({'success': False, 'message': 'Username already exists'}), 409

        # Ensure password is hashed
        user = User(username=username, password_hash=generate_password_hash(password))
        db.session.add(user)
        db.session.commit()

        serialized_user = user.serialize()

        return jsonify({'success': True, 'message': 'Registration successful', 'user': serialized_user})
    except Exception as e:
        db.session.rollback()
        logging.error(f"Registration failed: {e}")
        return jsonify({'success': False, 'message': 'Registration failed. Please try again later.'}), 500

@auth.route('/login', methods=['POST'])
def login():
    try:
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            return jsonify({'success': False, 'message': 'Missing username or password'}), 400

        user = User.query.filter_by(username=username).first()

        # Check if the user exists and if the password matches
        if not user or not check_password_hash(user.password_hash, password):
            return jsonify({'success': False, 'message': 'Invalid username or password'}), 401

        # Capture the previous last_active before updating (for offline-badge detection)
        previous_last_active = user.last_active
        user.last_active = datetime.utcnow()
        db.session.commit()

        serialized_user = user.serialize()

        return jsonify({
            'success': True,
            'message': 'Login successful',
            'user': serialized_user,
            'previous_last_active': previous_last_active.isoformat() if previous_last_active else None,
        })
    except Exception as e:
        db.session.rollback()
        logging.error(f"Login failed: {e}")
        return jsonify({'success': False, 'message': 'Login failed. Please try again later.'}), 500

@auth.route('/heartbeat', methods=['POST'])
def heartbeat():
    try:
        username = request.form.get('username')
        if not username:
            return jsonify({'success': False, 'message': 'Missing username'}), 400
        user = User.query.filter_by(username=username).first()
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        user.last_active = datetime.utcnow()
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        logging.error(f"Heartbeat failed: {e}")
        return jsonify({'success': False, 'message': 'Heartbeat failed'}), 500

@auth.route('/get_rankings', methods=['GET'])
def get_rankings():
    """Return ranking data for all users: gold, total games, wins, losses."""
    try:
        users = User.query.all()
        rankings = []
        for user in users:
            # Count finished games where this user was a player
            player_entries = Player.query.filter_by(user_id=user.id).all()
            total = 0
            wins = 0
            losses = 0
            for p in player_entries:
                game = Game.query.get(p.game_id)
                if game and game.state == 'finished':
                    total += 1
                    if game.winner_player_id == p.id:
                        wins += 1
                    else:
                        losses += 1
            is_online = False
            if user.last_active:
                is_online = (datetime.utcnow() - user.last_active).total_seconds() < 60
            rankings.append({
                'username': user.username,
                'gold': user.gold,
                'total_games': total,
                'wins': wins,
                'losses': losses,
                'is_online': is_online,
            })
        return jsonify({'success': True, 'rankings': rankings})
    except Exception as e:
        db.session.rollback()
        logging.error(f"Rankings failed: {e}")
        return jsonify({'success': False, 'message': 'Failed to fetch rankings'}), 500
