# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
from flask import Blueprint, request, jsonify, current_app, g
from models import db, User, Challenge, ChallengeStatus
import logging
import server_settings as settings
from analytics import track
from routes.auth import require_token

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
    instant_game = None
    challenge_id = None
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
        track('challenge_created', user_id=challenger_user.id,
              vs_ai=bool(opponent_user.is_ai), stake=stake, game_limit=game_limit)
        db.session.commit()

        challenge_id = challenge.id

        # Auto-accept if the opponent is an AI player. The accept runs
        # inline so the response can carry the created game and the client
        # can enter it immediately instead of polling for the acceptance.
        if opponent_user.is_ai:
            try:
                instant_game = _ai_accept_challenge(
                    challenge_id, current_app._get_current_object())
            except Exception:
                logger.exception('Inline AI accept failed; falling back to async accept')
            if instant_game is None:
                _schedule_ai_accept(challenge_id, current_app._get_current_object())
        else:
            # Tell offline human opponents they have been challenged
            try:
                from notification_service import notify_challenge_received
                notify_challenge_received(challenge)
            except Exception:
                logger.exception('challenge notification failed')

    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to create challenge')
        return jsonify({'success': False, 'message': 'Failed to create challenge'}), 400

    payload = {'success': True, 'message': 'Challenge sent'}
    if instant_game is not None:
        payload['message'] = 'Challenge accepted'
        payload['game'] = instant_game
        payload['challenge_id'] = challenge_id
    return jsonify(payload)


def _ai_accept_challenge(challenge_id, app):
    """Accept an open AI challenge and create its game.

    Returns the serialized game dict, or None if the accept failed.
    """
    challenge = db.session.get(Challenge, challenge_id)
    if not challenge or challenge.status.value != 'open':
        logger.info(f"AI accept skipped: challenge {challenge_id} no longer open")
        return None

    from routes.games import create_game as _route_create_game
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
            resp_obj, _status_code = game_response
        else:
            resp_obj = game_response

        game_data = resp_obj.get_json()

    if game_data.get('success') and 'game' in game_data:
        game_id = game_data['game']['id']
        logger.info(f"AI accepted challenge {challenge_id} → game {game_id}")
        if settings.AI_ENABLED:
            from ai.ai_worker import trigger_ai_if_needed
            trigger_ai_if_needed(game_id, app=app)
        # The inner route serialized the game for the AI viewer; re-serialize
        # for the human challenger so their hand stays visible and the AI's
        # stays hidden.
        from models import Game
        from routes.serialization import serialize_game_for_viewer
        game_obj = db.session.get(Game, game_id)
        if game_obj is not None:
            return serialize_game_for_viewer(game_obj, challenge.challenger_id)
        return None
    logger.error(f"AI accept failed: {game_data.get('message')}")
    return None


def _schedule_ai_accept(challenge_id, app):
    """Fallback: auto-accept an AI challenge on a background thread."""
    import threading

    def _do_accept():
        import time
        time.sleep(2)
        with app.app_context():
            try:
                _ai_accept_challenge(challenge_id, app)
            except Exception:
                logging.getLogger('nepalkings.ai').exception(
                    f'AI auto-accept failed for challenge {challenge_id}')

    threading.Thread(target=_do_accept, daemon=True).start()

@challenges.route('/open_challenges', methods=['GET'])
@require_token
def open_challenges():
    try:
        user = db.session.get(User, g.user_id)
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
