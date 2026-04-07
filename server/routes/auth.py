# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
# routes/auth.py
from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Player, Game
from datetime import datetime
import logging  # For logging errors instead of exposing them to the user
import re

auth = Blueprint('auth', __name__)

logger = logging.getLogger('nepalkings.routes.auth')

# ── Input validation constants ──
_USERNAME_MIN = 3
_USERNAME_MAX = 30
_USERNAME_RE = re.compile(r'^[a-zA-Z0-9_-]+$')
_PASSWORD_MIN = 6

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

        # Log accepted challenges for debugging notification flow
        accepted = [c for c in user.challenges_issued
                    if c.status and c.status.value == 'accepted']
        if accepted:
            logging.info(f"[get_user] {username}: {len(accepted)} accepted challenge(s) "
                         f"in challenges_issued: {[(c.id, c.game_id) for c in accepted]}")

        serialized_user = user.serialize()

        return jsonify({'success': True, 'user': serialized_user})
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error fetching user {username}: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'An error occurred while fetching the user'}), 500

@auth.route('/register', methods=['POST'])
def register():
    try:
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            return jsonify({'success': False, 'message': 'Missing username or password'}), 400

        # Input validation
        if len(username) < _USERNAME_MIN or len(username) > _USERNAME_MAX:
            return jsonify({'success': False, 'message': f'Username must be {_USERNAME_MIN}-{_USERNAME_MAX} characters'}), 400
        if not _USERNAME_RE.match(username):
            return jsonify({'success': False, 'message': 'Username may only contain letters, digits, hyphens, and underscores'}), 400
        if len(password) < _PASSWORD_MIN:
            return jsonify({'success': False, 'message': f'Password must be at least {_PASSWORD_MIN} characters'}), 400

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

        # Block login as AI users
        if user.is_ai:
            return jsonify({'success': False, 'message': 'Cannot log in as an AI player'}), 403

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
