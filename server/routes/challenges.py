from flask import Blueprint, request, jsonify
from models import db, User, Challenge
# from config import settings

challenges = Blueprint('challenges', __name__)

@challenges.route('/remove_challenge', methods=['POST'])
def remove_challenge():
    try:
        challenge_id = request.form.get('challenge_id')
        challenge = Challenge.query.get(challenge_id)
        if not challenge:
            return jsonify({'success': False, 'message': 'Challenge not found'}), 400

        db.session.delete(challenge)
        db.session.commit()
    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to remove challenge, Error: {str(e)}'}), 400
    return jsonify({'success': True, 'message': 'Challenge removed'})


@challenges.route('/create_challenge', methods=['POST'])
def create_challenge():
    try:
        challenger = request.form.get('challenger')
        opponent = request.form.get('opponent')

        # Checking if the challenger and opponent are valid users
        challenger_user = User.query.filter_by(username=challenger).first()
        opponent_user = User.query.filter_by(username=opponent).first()

        if not challenger_user or not opponent_user:
            return jsonify({'success': False, 'message': 'Challenger or opponent does not exist'}), 400

        # Creating a new challenge
        challenge = Challenge(challenger=challenger_user, challenged=opponent_user, status='open')

        db.session.add(challenge)
        db.session.commit()
    except Exception as e:
        # In case there is an exception while adding the challenge
        return jsonify({'success': False, 'message': f'Failed to create challenge, Error: {str(e)}'}), 400

    return jsonify({'success': True, 'message': 'Challenge sent'})

@challenges.route('/open_challenges', methods=['GET'])
def open_challenges():
    try:
        username = request.args.get('username')
        user = User.query.filter_by(username=username).first()
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 400

        challenges = Challenge.query.filter(
            (Challenge.challenger == user) | (Challenge.challenged == user)).filter_by(status='open').all()

        return jsonify({
            'challenges': [challenge.serialize() for challenge in challenges]
        })
    except Exception as e:
        return jsonify({'success': False, 'message': 'An error occurred: {}'.format(str(e))}), 400
