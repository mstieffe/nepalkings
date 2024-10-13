# routes/auth.py
from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User
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

        serialized_user = user.serialize()

        return jsonify({'success': True, 'message': 'Login successful', 'user': serialized_user})
    except Exception as e:
        logging.error(f"Login failed: {e}")
        return jsonify({'success': False, 'message': 'Login failed. Please try again later.'}), 500
