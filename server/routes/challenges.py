# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
from flask import Blueprint, request, jsonify
from models import db, User, Challenge
import server_settings as settings

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
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Failed to remove challenge, Error: {str(e)}'}), 400
    return jsonify({'success': True, 'message': 'Challenge removed'})


@challenges.route('/create_challenge', methods=['POST'])
def create_challenge():
    try:
        challenger = request.form.get('challenger')
        opponent = request.form.get('opponent')
        stake = request.form.get('stake', settings.DEFAULT_GAME_STAKE, type=int)
        turn_time_limit_str = request.form.get('turn_time_limit', None)
        turn_time_limit = int(turn_time_limit_str) if turn_time_limit_str else None

        # Checking if the challenger and opponent are valid users
        challenger_user = User.query.filter_by(username=challenger).first()
        opponent_user = User.query.filter_by(username=opponent).first()

        if not challenger_user or not opponent_user:
            return jsonify({'success': False, 'message': 'Challenger or opponent does not exist'}), 400

        # Validate stake
        if stake < 1:
            return jsonify({'success': False, 'message': 'Stake must be at least 1 gold'}), 400

        # Check that the challenger has enough gold
        if challenger_user.gold < stake:
            return jsonify({'success': False, 'message': f'Not enough gold ({challenger_user.gold}/{stake})'}), 400

        # Creating a new challenge
        challenge = Challenge(
            challenger=challenger_user,
            challenged=opponent_user,
            status='open',
            stake=stake,
            turn_time_limit=turn_time_limit,
        )

        db.session.add(challenge)
        db.session.commit()

        # Auto-accept if the opponent is an AI player
        if opponent_user.is_ai:
            # Import create_game logic inline to avoid circular imports
            from routes.games import create_game as _route_create_game
            from flask import current_app
            import logging
            logger = logging.getLogger('nepalkings.ai')

            # Use Flask's test request context to call create_game internally
            with current_app.test_request_context(
                '/games/create_game',
                method='POST',
                data={'challenge_id': str(challenge.id)},
                content_type='application/x-www-form-urlencoded'
            ):
                game_response = _route_create_game()
                # game_response is a tuple (response, status_code) or just a response
                if isinstance(game_response, tuple):
                    resp_obj, status = game_response
                else:
                    resp_obj = game_response
                    status = 200

                game_data = resp_obj.get_json()

                if game_data.get('success') and 'game' in game_data:
                    logger.info(f"AI auto-accepted challenge {challenge.id} → game {game_data['game']['id']}")
                    # Trigger AI if it's the AI's turn
                    if settings.AI_ENABLED:
                        from ai.ai_worker import trigger_ai_if_needed
                        trigger_ai_if_needed(game_data['game']['id'], app=current_app._get_current_object())

                    return jsonify({
                        'success': True,
                        'message': 'Game created against AI',
                        'ai_auto_accept': True,
                        'challenge_id': challenge.id,
                        'game': game_data['game'],
                    })
                else:
                    logger.error(f"AI auto-accept failed: {game_data.get('message')}")
                    # Fall through to return normal challenge response

    except Exception as e:
        db.session.rollback()
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
        db.session.rollback()
        return jsonify({'success': False, 'message': 'An error occurred: {}'.format(str(e))}), 400
