# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
from flask import Blueprint, request, jsonify, current_app, g
from models import db, User, Challenge, ChallengeStatus
import logging
import server_settings as settings
from routes.auth import require_token, verify_player_ownership

challenges = Blueprint('challenges', __name__)

logger = logging.getLogger('nepalkings.routes.challenges')

@challenges.route('/remove_challenge', methods=['POST'])
@require_token
def remove_challenge():
    try:
        challenge_id = request.form.get('challenge_id')
        challenge = db.session.get(Challenge, challenge_id)
        if not challenge:
            return jsonify({'success': False, 'message': 'Challenge not found'}), 400

        if g.user_id not in (challenge.challenger_id, challenge.challenged_id):
            return jsonify({'success': False, 'message': 'Forbidden'}), 403

        db.session.delete(challenge)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to remove challenge')
        return jsonify({'success': False, 'message': 'Failed to remove challenge'}), 400
    return jsonify({'success': True, 'message': 'Challenge removed'})


@challenges.route('/create_challenge', methods=['POST'])
@require_token
def create_challenge():
    try:
        challenger = request.form.get('challenger')
        opponent = request.form.get('opponent')
        stake = request.form.get('stake', settings.DEFAULT_GAME_STAKE, type=int)
        game_limit_raw = request.form.get('game_limit')
        if game_limit_raw in (None, ''):
            game_limit = stake
        else:
            try:
                game_limit = int(game_limit_raw)
            except (TypeError, ValueError):
                return jsonify({'success': False, 'message': 'Game limit must be a number'}), 400
        turn_time_limit_str = request.form.get('turn_time_limit', None)
        turn_time_limit = int(turn_time_limit_str) if turn_time_limit_str else None

        # Checking if the challenger and opponent are valid users
        challenger_user = User.query.filter_by(username=challenger).first()
        opponent_user = User.query.filter_by(username=opponent).first()

        if not challenger_user or not opponent_user:
            return jsonify({'success': False, 'message': 'Challenger or opponent does not exist'}), 400

        if g.user_id != challenger_user.id:
            return jsonify({'success': False, 'message': 'Forbidden'}), 403

        # Validate stake
        if stake < 1:
            return jsonify({'success': False, 'message': 'Stake must be at least 1 gold'}), 400
        if game_limit < 1:
            return jsonify({'success': False, 'message': 'Game limit must be at least 1 point'}), 400
        max_game_limit = int(getattr(settings, 'MAX_GAME_LIMIT', 100) or 100)
        if game_limit > max_game_limit:
            return jsonify({'success': False, 'message': f'Game limit must be at most {max_game_limit} points'}), 400

        # Check that the challenger has enough gold
        if challenger_user.gold < stake:
            return jsonify({'success': False, 'message': f'Not enough gold ({challenger_user.gold}/{stake})'}), 400

        # Creating a new challenge
        challenge = Challenge(
            challenger=challenger_user,
            challenged=opponent_user,
            status=ChallengeStatus.OPEN,
            stake=stake,
            game_limit=game_limit,
            turn_time_limit=turn_time_limit,
        )

        db.session.add(challenge)
        db.session.commit()

        # Auto-accept if the opponent is an AI player (with a short delay)
        if opponent_user.is_ai:
            _schedule_ai_accept(challenge.id, current_app._get_current_object())

    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to create challenge')
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
            logger = logging.getLogger('nepalkings.ai')

            challenge = db.session.get(Challenge, challenge_id)
            if not challenge or challenge.status.value != 'open':
                logger.info(f"AI auto-accept skipped: challenge {challenge_id} no longer open")
                return

            # Get AI auth token for the challenged (AI) user
            from ai import get_ai_auth_headers
            ai_headers = get_ai_auth_headers(challenge.challenged_id)
            auth_header = ai_headers.get('Authorization', '')

            with app.test_request_context(
                '/games/create_game',
                method='POST',
                data={'challenge_id': str(challenge_id)},
                content_type='application/x-www-form-urlencoded',
                headers={'Authorization': auth_header}
            ):
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
        logger.exception('Failed to fetch open challenges')
        return jsonify({'success': False, 'message': 'Failed to fetch open challenges'}), 400
