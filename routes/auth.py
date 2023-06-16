# routes/auth.py
from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User
#import settings

auth = Blueprint('auth', __name__)

@auth.route('/get_users', methods=['GET'])
def get_users():
    try:
        current_username = request.args.get('username')
        users = User.query.filter(User.username != current_username).all()

        serialized_users = [user.serialize() for user in users]

        return jsonify({'users': serialized_users})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 400


@auth.route('/register', methods=['POST'])
def register():
    try:
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            return jsonify({'success': False, 'message': 'Missing username or password'}), 400

        if User.query.filter_by(username=username).first():
            return jsonify({'success': False, 'message': 'Username already exists'}), 400

        user = User(username=username, password_hash=generate_password_hash(password))
        db.session.add(user)
        db.session.commit()

        serialized_user = user.serialize()

        return jsonify({'success': True, 'message': 'Registration successful', 'user': serialized_user})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Registration failed, Error: {str(e)}'}), 400

@auth.route('/login', methods=['POST'])
def login():
    try:
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            return jsonify({'success': False, 'message': 'Missing username or password'}), 400

        user = User.query.filter_by(username=username).first()

        if not user or not user.check_password(password):
            return jsonify({'success': False, 'message': 'Invalid username or password'}), 400

        serialized_user = user.serialize()

        return jsonify({'success': True, 'message': 'Login successful', 'user': serialized_user})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Login failed, Error: {str(e)}'}), 400
