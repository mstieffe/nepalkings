# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
import logging
from flask import Blueprint, request, jsonify, current_app, g
from models import db, User, Challenge, ChallengeStatus
import server_settings as settings
from routes.auth import require_token

challenges = Blueprint('challenges', __name__)

@challenges.route('/remove_challenge', methods=['POST'])
@require_token
def remove_challenge():
    try:
        challenge_id = request.form.get('challenge_id')
        challenge = Challenge.query.get(challenge_id)
        if not challenge:
            return jsonify({'success': False, 'message': 'Challenge not found'}), 400

        # Only the challenger or challenged user may remove the challenge
        if g.user_id not in (challenge.challenger_id, challenge.challenged_id):
            return jsonify({'success': False, 'message': 'Forbidden'}), 403

        db.session.delete(challenge)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logging.error(f"Failed to remove challenge: {e}")
        return jsonify({'success': False, 'message': 'Failed to remove challenge'}), 400
    return jsonify({'success': True, 'message': 'Challenge removed'})


@challenges.route('/create_challenge', methods=['POST'])
@require_token
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

        # The authenticated user must be the challenger
        if g.user_id != challenger_user.id:
            return jsonify({'success': False, 'message': 'Forbidden: you can only create challenges as yourself'}), 403

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
            status=ChallengeStatus.OPEN,
            stake=stake,
            turn_time_limit=turn_time_limit,
        )

        db.session.add(challenge)
        db.session.commit()

        # Auto-accept if the opponent is an AI player (with a short delay)
        if opponent_user.is_ai:
            _schedule_ai_accept(challenge.id, current_app._get_current_object())

    except Exception as e:
        db.session.rollback()
        # In case there is an exception while adding the challenge
        logging.error(f"Failed to create challenge: {e}")
        return jsonify({'success': False, 'message': 'Failed to create challenge'}), 400

    return jsonify({'success': True, 'message': 'Challenge sent'})


def _schedule_ai_accept(challenge_id, app):
    """Auto-accept a challenge from an AI opponent after a short delay."""
    import threading

    def _do_accept():
        import time
        time.sleep(2)  # Small delay so it feels natural
        with app.app_context():
            from routes.games import create_game as _route_create_game
            import logging
            from flask import g
            logger = logging.getLogger('nepalkings.ai')

            challenge = Challenge.query.get(challenge_id)
            if not challenge or challenge.status.value != 'open':
                logger.info(f"AI auto-accept skipped: challenge {challenge_id} no longer open")
                return

            # Get the AI token so create_game can authenticate the request
            ai_user_id = challenge.challenged_id
            from ai import get_ai_token
            ai_token = get_ai_token(ai_user_id) or ''

            with app.test_request_context(
                '/games/create_game',
                method='POST',
                data={'challenge_id': str(challenge_id)},
                content_type='application/x-www-form-urlencoded',
                headers={'Authorization': f'Bearer {ai_token}'},
            ):
                # Manually set g.user_id for the @require_token decorator
                g.user_id = ai_user_id
                game_response = _route_create_game()
                if isinstance(game_response, tuple):
                    resp_obj, status_code = game_response
                else:
                    resp_obj = game_response

                game_data = resp_obj.get_json()

                if game_data.get('success') and 'game' in game_data:
                    logger.info(f"AI auto-accepted challenge {challenge_id} → game {game_data['game']['id']}")
                    if settings.AI_ENABLED:
                        from ai.ai_worker import trigger_ai_if_needed
                        trigger_ai_if_needed(game_data['game']['id'], app=app)
                else:
                    logger.error(f"AI auto-accept failed: {game_data.get('message')}")

    threading.Thread(target=_do_accept, daemon=True).start()

@challenges.route('/open_challenges', methods=['GET'])
def open_challenges():
    try:
        username = request.args.get('username')
        user = User.query.filter_by(username=username).first()
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 400

        challenges = Challenge.query.filter(
            (Challenge.challenger == user) | (Challenge.challenged == user)).filter_by(status=ChallengeStatus.OPEN).all()

        return jsonify({
            'challenges': [challenge.serialize() for challenge in challenges]
        })
    except Exception as e:
        db.session.rollback()
        logging.error(f"An error occurred fetching open challenges: {e}")
        return jsonify({'success': False, 'message': 'An unexpected error occurred'}), 400
