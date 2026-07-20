# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
# routes/auth.py
import re
import secrets
import smtplib
import functools
import logging
from email.mime.text import MIMEText
from datetime import datetime, timezone

from flask import Blueprint, request, jsonify, g
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from sqlalchemy import case, func
from sqlalchemy.exc import OperationalError
from werkzeug.security import generate_password_hash, check_password_hash

from models import db, User, Player, Game
import server_settings as settings
from analytics import track

auth = Blueprint('auth', __name__)

logger = logging.getLogger('nepalkings.routes.auth')


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

# ── Validation constants ──
_USERNAME_MIN = 3
_USERNAME_MAX = 30
_USERNAME_RE = re.compile(r'^[a-zA-Z0-9_-]+$')
_PASSWORD_MIN = 8


def _is_valid_email(email):
    """Quick sanity check for email format — avoids regex ReDoS.

    Also rejects control characters to prevent SMTP header injection.
    """
    if not email or len(email) > 254:
        return False
    for ch in email:
        if ord(ch) < 32 or ord(ch) == 127:
            return False
    at_idx = email.find('@')
    if at_idx < 1 or at_idx == len(email) - 1:
        return False
    local = email[:at_idx]
    domain = email[at_idx + 1:]
    if len(local) > 64:
        return False
    if '.' not in domain or domain.startswith('.') or domain.endswith('.'):
        return False
    if ' ' in email:
        return False
    return True


def _database_busy_response(error, action):
    """Return a retryable response for transient SQLite writer contention."""
    message = str(error or '').lower()
    if not isinstance(error, OperationalError) or not any(
            marker in message for marker in ('database is locked',
                                              'database is busy')):
        return None
    logger.warning('Database busy during %s; asking client to retry', action)
    response = jsonify({
        'success': False,
        'message': 'Server is briefly busy. Please try again in a moment.',
        'retryable': True,
    })
    response.status_code = 503
    response.headers['Retry-After'] = '2'
    return response


# ── Long-lived AI service token max age (1 year) ──
_AI_TOKEN_MAX_AGE = 365 * 24 * 3600


# ── Token helpers ─────────────────────────────────────────────────

def generate_token(user_id, token_version=0):
    """Generate a short-lived signed token for a human user."""
    s = URLSafeTimedSerializer(settings.SECRET_KEY)
    return s.dumps({
        'uid': int(user_id),
        'ver': int(token_version or 0),
    }, salt='user-auth')


def generate_ai_token(user_id):
    """Generate a long-lived signed token for an AI service account (1-year TTL)."""
    s = URLSafeTimedSerializer(settings.SECRET_KEY)
    return s.dumps(user_id, salt='ai-service')


def _decode_token(token):
    """Return ``(user_id, token_version, kind)`` for a signed token.

    Tries the short-lived user-auth salt first; if that fails with
    BadSignature (wrong salt), falls back to the long-lived ai-service salt.
    Legacy human tokens encoded only an integer; they remain version zero so
    an in-progress session survives this migration until the user explicitly
    revokes it.
    """
    s = URLSafeTimedSerializer(settings.SECRET_KEY)
    try:
        payload = s.loads(
            token,
            salt='user-auth',
            max_age=settings.TOKEN_EXPIRY_SECONDS,
        )
        if isinstance(payload, dict):
            return (
                int(payload['uid']),
                int(payload.get('ver') or 0),
                'human',
            )
        return int(payload), 0, 'human'
    except SignatureExpired:
        raise  # Expired user token — let caller return 401
    except BadSignature:
        pass  # Might be an AI service token — try the other salt
    # AI service token: tolerate up to 1 year
    return (
        int(s.loads(token, salt='ai-service', max_age=_AI_TOKEN_MAX_AGE)),
        None,
        'ai',
    )


def validate_token(token):
    """Validate a Bearer token and return the encoded user id."""
    user_id, _token_version, _kind = _decode_token(token)
    return user_id


# ── Auth decorator ────────────────────────────────────────────────

def require_token(f):
    """Decorator that validates a Bearer token in the Authorization header.

    On success, sets ``flask.g.user_id`` to the authenticated user's ID.
    Returns 401 JSON on missing / expired / invalid tokens.
    """
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'success': False, 'message': 'Authentication required'}), 401
        token = auth_header[7:]  # strip 'Bearer '
        try:
            user_id, token_version, token_kind = _decode_token(token)
        except SignatureExpired:
            return jsonify({'success': False, 'message': 'Session expired, please log in again'}), 401
        except (BadSignature, KeyError, TypeError, ValueError):
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        user = db.session.get(User, user_id)
        if not user:
            return jsonify({
                'success': False,
                'message': 'Session is no longer valid',
                'reason': 'session_revoked',
            }), 401
        if (
            token_kind == 'human'
            and int(token_version or 0) != int(user.token_version or 0)
        ):
            return jsonify({
                'success': False,
                'message': 'Session was revoked. Please log in again.',
                'reason': 'session_revoked',
            }), 401
        status = (user.account_status or 'active').strip().lower()
        now = _utcnow()
        if status in {'deleted', 'banned'}:
            return jsonify({
                'success': False,
                'message': 'This account is unavailable.',
                'reason': f'account_{status}',
            }), 403
        if (
            status == 'suspended'
            and (user.suspended_until is None or user.suspended_until > now)
        ):
            return jsonify({
                'success': False,
                'message': 'This account is temporarily suspended.',
                'reason': 'account_suspended',
                'suspended_until': (
                    user.suspended_until.isoformat()
                    if user.suspended_until else None
                ),
            }), 403
        g.user_id = user_id
        g.current_user = user
        return f(*args, **kwargs)
    return decorated


# ── Player-ownership helper ───────────────────────────────────────

def verify_player_ownership(player_id):
    """Check that the authenticated user (g.user_id) owns player_id.

    Returns a JSON error response tuple on failure, or None on success.
    Must be called inside a route protected by @require_token.

    Side-effect: bumps Game.last_activity_at for the player's game so the
    stuck-game sweeper doesn't kill games with active client activity.
    Only conquer games get the timestamp bump — regular battles don't have
    a sweeper, so updating their timestamp on every poll is unnecessary
    write churn.
    """
    player = db.session.get(Player, player_id)
    if not player:
        return jsonify({'success': False, 'message': 'Player not found'}), 404
    if player.user_id != g.user_id:
        return jsonify({'success': False, 'message': 'Forbidden: player does not belong to authenticated user'}), 403
    # Touch game activity timestamp for conquer games only (best-effort,
    # don't fail auth on error).  The stuck-game sweeper only targets
    # conquer mode, so other game modes don't need this write.
    try:
        if player.game_id:
            game = db.session.get(Game, player.game_id)
            if (game is not None
                    and game.mode == 'conquer'
                    and game.state != 'finished'):
                game.last_activity_at = datetime.now(timezone.utc)
    except Exception:
        pass
    return None


def get_game_membership(game_id):
    """Return the authenticated player's row for a game, or an error tuple."""
    # Query-string values arrive as text unless every caller explicitly asks
    # Flask to coerce them.  SQLite accepts comparisons such as
    # ``INTEGER = "3"``, but PostgreSQL rejects the resulting
    # ``integer = character varying`` expression.  Normalize at this shared
    # authorization boundary so a missed route-level conversion cannot turn
    # an ownership check into a server error.
    if isinstance(game_id, bool):
        normalized_game_id = None
    elif isinstance(game_id, int):
        normalized_game_id = game_id
    elif isinstance(game_id, str) and game_id.strip().isdigit():
        normalized_game_id = int(game_id.strip())
    else:
        normalized_game_id = None

    if normalized_game_id is None or normalized_game_id <= 0:
        return (
            None,
            jsonify({'success': False, 'message': 'Invalid game ID'}),
            400,
        )

    game = db.session.get(Game, normalized_game_id)
    if not game:
        return None, jsonify({'success': False, 'message': 'Game not found'}), 404
    player = Player.query.filter_by(
        game_id=normalized_game_id,
        user_id=g.user_id,
    ).first()
    if not player:
        return None, jsonify({'success': False, 'message': 'Forbidden'}), 403
    return player, None, None


def verify_game_membership(game_id):
    """Check the authenticated user participates in game_id."""
    _, response, status = get_game_membership(game_id)
    if response is not None:
        return response, status
    return None


def serialize_public_user(user):
    is_online = user.is_ai
    if not is_online and user.last_active:
        is_online = (_utcnow() - user.last_active).total_seconds() < 60
    return {
        'id': user.id,
        'username': user.username,
        'is_online': is_online,
        'is_ai': user.is_ai,
    }


def serialize_private_user(user):
    return user.serialize()


def _truthy_form_value(name):
    value = request.form.get(name)
    if value is None and request.is_json:
        value = (request.get_json(silent=True) or {}).get(name)
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def _request_value(name, default=None):
    value = request.form.get(name)
    if value is None and request.is_json:
        value = (request.get_json(silent=True) or {}).get(name)
    return default if value is None else value


# ── Email helper ──────────────────────────────────────────────────

def _send_verification_email(user):
    """Send (or log) an email-verification link for the given user."""
    token = user.email_verification_token
    verify_url = f"{settings.SERVER_BASE_URL}/auth/verify_email?token={token}"

    if not settings.EMAIL_VERIFICATION_ENABLED or not settings.SMTP_HOST:
        logger.info(
            "Email verification not sent because SMTP delivery is disabled"
        )
        return

    try:
        body = (
            f"Welcome to Nepal Kings, {user.username}!\n\n"
            f"Please verify your email address by clicking the link below:\n\n"
            f"  {verify_url}\n\n"
            f"This link is valid for 48 hours.\n\n"
            f"If you did not create an account, you can safely ignore this email."
        )
        msg = MIMEText(body)
        msg['Subject'] = 'Nepal Kings — Verify your email address'
        msg['From'] = settings.SMTP_FROM
        msg['To'] = user.email

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as smtp:
            smtp.ehlo()
            smtp.starttls()
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(msg)

        logger.info(f"Verification email sent to {user.email} for user '{user.username}'")
    except Exception:
        logger.exception(f"Failed to send verification email to {user.email}")


# ── Routes ────────────────────────────────────────────────────────

@auth.route('/get_users', methods=['GET'])
@require_token
def get_users():
    try:
        current_user = db.session.get(User, g.user_id)
        if not current_user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        users = User.query.filter(
            User.id != current_user.id,
            User.account_status == 'active',
        ).all()

        serialized_users = [serialize_public_user(user) for user in users]

        return jsonify({'success': True, 'users': serialized_users})
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error fetching users: {e}")
        return jsonify({'success': False, 'message': 'An error occurred while fetching users'}), 500

@auth.route('/get_user', methods=['GET'])
@require_token
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

        serialized_user = (
            serialize_private_user(user)
            if user.id == g.user_id
            else serialize_public_user(user)
        )

        return jsonify({'success': True, 'user': serialized_user})
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error fetching user {username}: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'An error occurred while fetching the user'}), 500

@auth.route('/register', methods=['POST'])
def register():
    try:
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        email = request.form.get('email', '').strip().lower() or None
        age_confirmed = _truthy_form_value('age_confirmed')
        terms_accepted = _truthy_form_value('terms_accepted')
        privacy_accepted = _truthy_form_value('privacy_accepted')

        if not username or not password:
            return jsonify({'success': False, 'message': 'Missing username or password'}), 400
        if not age_confirmed:
            return jsonify({'success': False, 'message': 'You must confirm that you are at least 13 years old.'}), 400
        if not terms_accepted or not privacy_accepted:
            return jsonify({'success': False, 'message': 'You must accept the Terms and acknowledge the Privacy Policy.'}), 400

        # Input validation
        if len(username) < _USERNAME_MIN or len(username) > _USERNAME_MAX:
            return jsonify({'success': False, 'message': f'Username must be {_USERNAME_MIN}-{_USERNAME_MAX} characters'}), 400
        if not _USERNAME_RE.match(username):
            return jsonify({'success': False, 'message': 'Username may only contain letters, digits, hyphens, and underscores'}), 400
        if len(password) < _PASSWORD_MIN:
            return jsonify({'success': False, 'message': f'Password must be at least {_PASSWORD_MIN} characters'}), 400

        if email and not _is_valid_email(email):
            return jsonify({'success': False, 'message': 'Invalid email address'}), 400

        if User.query.filter_by(username=username).first():
            return jsonify({'success': False, 'message': 'Username already exists'}), 409

        if email and User.query.filter_by(email=email).first():
            return jsonify({'success': False, 'message': 'Email address already registered'}), 409

        verification_token = secrets.token_urlsafe(32) if email else None

        user = User(
            username=username,
            password_hash=generate_password_hash(password),
            email=email,
            email_verified=False,
            email_verification_token=verification_token,
            email_verification_sent_at=_utcnow() if email else None,
            age_confirmed=True,
            age_confirmed_at=_utcnow(),
            terms_version=settings.LEGAL_TERMS_VERSION,
            terms_accepted_at=_utcnow(),
            privacy_version=settings.LEGAL_PRIVACY_VERSION,
            privacy_accepted_at=_utcnow(),
            # No items are granted at signup. Starter cards arrive after the
            # Collection roulette; economy rewards arrive at journey completion.
            gold=0,
            booster_packs=0,
            booster_packs_side=0,
            maps=0,
        )
        try:
            from onboarding_service import set_initial_onboarding
            set_initial_onboarding(user)
        except Exception:
            logger.exception("Failed to initialize onboarding for new user")
        db.session.add(user)
        db.session.flush()
        # The starter suit + offensive set are NOT assigned at signup. The suit
        # is selected for the Collection roulette and its cards are granted only
        # after that reel settles. No defensive set is
        # granted: after a won conquest the conquer config is converted into the
        # land's defence config. See grant_starter_set() in onboarding_service.
        track('signup', user_id=user.id, has_email=bool(email))
        db.session.commit()

        if email and verification_token:
            _send_verification_email(user)

        auth_token = generate_token(user.id, user.token_version)
        serialized_user = serialize_private_user(user)

        response = {
            'success': True,
            'message': 'Registration successful',
            'user': serialized_user,
            'token': auth_token,
        }
        if email and not user.email_verified:
            response['email_verification_pending'] = True

        return jsonify(response)
    except Exception as e:
        db.session.rollback()
        busy_response = _database_busy_response(e, 'registration')
        if busy_response is not None:
            return busy_response
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
        status = (user.account_status or 'active').strip().lower()
        if status in {'deleted', 'banned'}:
            return jsonify({
                'success': False,
                'message': 'This account is unavailable.',
                'reason': f'account_{status}',
            }), 403
        if (
            status == 'suspended'
            and (
                user.suspended_until is None
                or user.suspended_until > _utcnow()
            )
        ):
            return jsonify({
                'success': False,
                'message': 'This account is temporarily suspended.',
                'reason': 'account_suspended',
                'suspended_until': (
                    user.suspended_until.isoformat()
                    if user.suspended_until else None
                ),
            }), 403
        if status == 'suspended':
            # The timed suspension has elapsed. Persist the transition on the
            # first successful login so user lists and challenges no longer
            # treat the player as unavailable.
            user.account_status = 'active'
            user.suspended_until = None

        # Capture the previous last_active before updating (for offline-badge detection)
        previous_last_active = user.last_active
        user.last_active = _utcnow()
        track('login', user_id=user.id)
        db.session.commit()

        token = generate_token(user.id, user.token_version)
        serialized_user = serialize_private_user(user)

        response = {
            'success': True,
            'message': 'Login successful',
            'token': token,
            'user': serialized_user,
            'previous_last_active': previous_last_active.isoformat() if previous_last_active else None,
        }
        if user.email and not user.email_verified:
            response['email_verification_pending'] = True

        return jsonify(response)
    except Exception as e:
        db.session.rollback()
        busy_response = _database_busy_response(e, 'login')
        if busy_response is not None:
            return busy_response
        logging.error(f"Login failed: {e}")
        return jsonify({'success': False, 'message': 'Login failed. Please try again later.'}), 500

@auth.route('/verify_email', methods=['GET'])
def verify_email():
    """Verify a user's email address via the token sent in the verification email."""
    from datetime import timedelta
    _VERIFY_TOKEN_MAX_AGE_HOURS = 48

    token = request.args.get('token', '')
    if not token:
        return jsonify({'success': False, 'message': 'Missing verification token'}), 400

    user = User.query.filter_by(email_verification_token=token).first()
    if not user:
        return jsonify({'success': False, 'message': 'Invalid or expired verification token'}), 400

    if user.email_verification_sent_at:
        age = _utcnow() - user.email_verification_sent_at
        if age > timedelta(hours=_VERIFY_TOKEN_MAX_AGE_HOURS):
            user.email_verification_token = None
            db.session.commit()
            return jsonify({
                'success': False,
                'message': f'Verification link has expired (valid for {_VERIFY_TOKEN_MAX_AGE_HOURS} hours). Please register again or request a new link.'
            }), 400

    user.email_verified = True
    user.email_verification_token = None
    db.session.commit()
    logger.info(f"Email verified for user '{user.username}'")

    return jsonify({'success': True, 'message': 'Email address verified successfully'})

@auth.route('/heartbeat', methods=['POST'])
@require_token
def heartbeat():
    try:
        user = db.session.get(User, g.user_id)
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404
        user.last_active = _utcnow()
        try:
            from onboarding_service import ensure_daily_quest
            ensure_daily_quest(user, commit=False)
        except Exception:
            logger.exception("Failed to refresh daily quest during heartbeat")
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        logging.error(f"Heartbeat failed: {e}")
        return jsonify({'success': False, 'message': 'Heartbeat failed'}), 500


# ── Account safety and privacy choices ────────────────────────────

@auth.route('/account/change_password', methods=['POST'])
@require_token
def change_password():
    """Change a password and revoke every other issued human session."""
    user = db.session.get(User, g.user_id)
    current_password = str(_request_value('current_password', '') or '')
    new_password = str(_request_value('new_password', '') or '')
    if not user or not user.check_password(current_password):
        return jsonify({
            'success': False,
            'message': 'Current password is incorrect.',
        }), 401
    if len(new_password) < _PASSWORD_MIN:
        return jsonify({
            'success': False,
            'message': f'New password must be at least {_PASSWORD_MIN} characters.',
        }), 400
    if user.check_password(new_password):
        return jsonify({
            'success': False,
            'message': 'Choose a different password.',
        }), 400

    user.set_password(new_password)
    user.token_version = int(user.token_version or 0) + 1
    db.session.commit()
    token = generate_token(user.id, user.token_version)
    logger.info(
        'Password changed and prior sessions revoked',
        extra={'event': 'password_changed', 'user_id': user.id},
    )
    return jsonify({
        'success': True,
        'message': 'Password changed. Other devices have been logged out.',
        'token': token,
    })


@auth.route('/account/logout_all', methods=['POST'])
@require_token
def logout_all():
    """Revoke every human token for the current account, including this one."""
    user = db.session.get(User, g.user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404
    user.token_version = int(user.token_version or 0) + 1
    db.session.commit()
    logger.info(
        'All sessions revoked',
        extra={'event': 'sessions_revoked', 'user_id': user.id},
    )
    return jsonify({
        'success': True,
        'message': 'All devices have been logged out.',
    })


@auth.route('/account/export', methods=['GET'])
@require_token
def export_account():
    """Return an account-scoped JSON export for the requesting player."""
    from models import (
        ChatMessage,
        CollectionCard,
        Event,
        Kingdom,
        KingdomMessage,
        ModerationAction,
        SafetyReport,
        UserBlock,
    )

    user = db.session.get(User, g.user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404
    players = Player.query.filter_by(user_id=user.id).order_by(Player.id).all()
    player_ids = [row.id for row in players]
    games = []
    for player in players:
        game = db.session.get(Game, player.game_id)
        if not game:
            continue
        games.append({
            'game_id': game.id,
            'mode': game.mode,
            'state': game.state,
            'date': game.date.isoformat() if game.date else None,
            'finished_at': (
                game.finished_at.isoformat() if game.finished_at else None
            ),
            'stake': game.stake,
            'game_limit': game.game_limit,
            'player_id': player.id,
            'points': player.points,
            'status': player.status,
            'won': game.winner_player_id == player.id,
        })

    duel_messages = []
    if player_ids:
        duel_messages = [
            row.serialize()
            for row in ChatMessage.query.filter(
                (ChatMessage.sender_id.in_(player_ids))
                | (ChatMessage.receiver_id.in_(player_ids))
            ).order_by(ChatMessage.id).all()
        ]

    payload = {
        'generated_at': _utcnow().isoformat(),
        'account': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'email_verified': bool(user.email_verified),
            'notify_emails_enabled': bool(user.notify_emails_enabled),
            'age_confirmed': bool(user.age_confirmed),
            'age_confirmed_at': (
                user.age_confirmed_at.isoformat()
                if user.age_confirmed_at else None
            ),
            'terms_version': user.terms_version,
            'terms_accepted_at': (
                user.terms_accepted_at.isoformat()
                if user.terms_accepted_at else None
            ),
            'privacy_version': user.privacy_version,
            'privacy_accepted_at': (
                user.privacy_accepted_at.isoformat()
                if user.privacy_accepted_at else None
            ),
            'account_status': user.account_status or 'active',
            'gold': int(user.gold or 0),
            'booster_packs': int(user.booster_packs or 0),
            'booster_packs_side': int(user.booster_packs_side or 0),
            'maps': int(user.maps or 0),
        },
        'collection': [
            row.serialize()
            for row in CollectionCard.query.filter_by(
                user_id=user.id
            ).order_by(CollectionCard.id).all()
        ],
        'games': games,
        'challenges': {
            'issued': [row.serialize() for row in user.challenges_issued],
            'received': [row.serialize() for row in user.challenges_received],
        },
        'kingdoms': [
            row.serialize()
            for row in Kingdom.query.filter_by(
                owner_user_id=user.id
            ).order_by(Kingdom.id).all()
        ],
        'duel_messages': duel_messages,
        'kingdom_messages': [
            row.serialize()
            for row in KingdomMessage.query.filter(
                (KingdomMessage.sender_user_id == user.id)
                | (KingdomMessage.recipient_user_id == user.id)
            ).order_by(KingdomMessage.id).all()
        ],
        'analytics_events': [
            row.serialize()
            for row in Event.query.filter_by(
                user_id=user.id
            ).order_by(Event.id).all()
        ],
        'player_safety': {
            'blocks': [
                {
                    'blocked_user_id': row.blocked_user_id,
                    'blocked_username': (
                        row.blocked.username if row.blocked else None),
                    'created_at': (
                        row.created_at.isoformat()
                        if row.created_at else None),
                }
                for row in UserBlock.query.filter_by(
                    blocker_user_id=user.id
                ).order_by(UserBlock.id).all()
            ],
            'reports_submitted': [
                {
                    **row.serialize_for_reporter(),
                    # This is the requesting player's own submitted content.
                    # Private evidence and operator data remain excluded.
                    'details': row.details,
                }
                for row in SafetyReport.query.filter_by(
                    reporter_user_id=user.id
                ).order_by(SafetyReport.id).all()
            ],
            # Never expose another reporter, private evidence, or operator
            # identity through the target player's export.
            'account_actions': [
                {
                    'action': row.action,
                    'reason': row.reason,
                    'created_at': (
                        row.created_at.isoformat()
                        if row.created_at else None),
                }
                for row in ModerationAction.query.filter_by(
                    target_user_id=user.id
                ).order_by(ModerationAction.id).all()
            ],
        },
    }
    response = jsonify({'success': True, 'export': payload})
    response.headers['Content-Disposition'] = (
        f'attachment; filename="nepal-kings-account-{user.id}.json"'
    )
    response.headers['Cache-Control'] = 'no-store'
    logger.info(
        'Account data exported',
        extra={'event': 'account_exported', 'user_id': user.id},
    )
    return response


@auth.route('/account/delete', methods=['POST'])
@require_token
def delete_account():
    """Anonymize a human account while preserving game/economy integrity."""
    from models import (
        ChatMessage,
        Challenge,
        ChallengeStatus,
        Event,
        Kingdom,
        KingdomMessage,
        LogEntry,
        UserBlock,
    )

    user = db.session.get(User, g.user_id)
    current_password = str(_request_value('current_password', '') or '')
    confirmation = str(_request_value('confirmation', '') or '')
    if not user or not user.check_password(current_password):
        return jsonify({
            'success': False,
            'message': 'Current password is incorrect.',
        }), 401
    if confirmation != 'DELETE':
        return jsonify({
            'success': False,
            'message': 'Type DELETE to confirm account deletion.',
        }), 400
    if user.is_ai:
        return jsonify({
            'success': False,
            'message': 'Service accounts cannot be deleted here.',
        }), 403

    player_ids = [
        row.id
        for row in Player.query.filter_by(user_id=user.id).all()
    ]
    if player_ids:
        ChatMessage.query.filter(
            ChatMessage.sender_id.in_(player_ids)
        ).update(
            {ChatMessage.message: '[deleted by former player]'},
            synchronize_session=False,
        )
        LogEntry.query.filter(
            LogEntry.player_id.in_(player_ids)
        ).update(
            {LogEntry.author: 'Deleted player'},
            synchronize_session=False,
        )
    KingdomMessage.query.filter(
        KingdomMessage.sender_user_id == user.id
    ).update(
        {KingdomMessage.message: '[deleted by former player]'},
        synchronize_session=False,
    )
    KingdomMessage.query.filter(
        KingdomMessage.recipient_user_id == user.id
    ).delete(synchronize_session=False)
    for kingdom in Kingdom.query.filter_by(owner_user_id=user.id).all():
        kingdom.name = f'Former Kingdom #{kingdom.id}'
    Event.query.filter_by(user_id=user.id).update(
        {Event.user_id: None},
        synchronize_session=False,
    )
    UserBlock.query.filter(
        (UserBlock.blocker_user_id == user.id)
        | (UserBlock.blocked_user_id == user.id)
    ).delete(synchronize_session=False)
    for challenge in Challenge.query.filter(
        Challenge.status == ChallengeStatus.OPEN,
        (
            (Challenge.challenger_id == user.id)
            | (Challenge.challenged_id == user.id)
        ),
    ).all():
        challenge.status = ChallengeStatus.REJECTED

    now = _utcnow()
    # Do not use only the predictable numeric id: another account could have
    # registered that future name and thereby prevent deletion at commit time.
    while True:
        anonymous_username = f'DeletedPlayer-{secrets.token_hex(8)}'
        if not User.query.filter(
            User.id != user.id,
            User.username == anonymous_username,
        ).first():
            break
    user.username = anonymous_username
    user.email = None
    user.email_verified = False
    user.email_verification_token = None
    user.email_verification_sent_at = None
    user.notify_emails_enabled = False
    user.last_active = None
    user.onboarding_state = {}
    user.account_status = 'deleted'
    user.deleted_at = now
    user.suspended_until = None
    user.chat_muted_until = None
    user.is_moderator = False
    user.token_version = int(user.token_version or 0) + 1
    user.set_password(secrets.token_urlsafe(48))
    db.session.commit()
    logger.info(
        'Account anonymized',
        extra={'event': 'account_deleted', 'user_id': user.id},
    )
    return jsonify({
        'success': True,
        'message': 'Your account has been deleted and anonymized.',
    })

@auth.route('/get_rankings', methods=['GET'])
def get_rankings():
    """Return ranking data for all users: gold, total games, wins, losses."""
    try:
        # Aggregate finished-game stats per user in a single query instead
        # of per-user/per-game lookups (the endpoint is public, so its cost
        # must stay flat as the user base grows).
        stat_rows = (
            db.session.query(
                Player.user_id,
                func.count(Game.id).label('total'),
                func.sum(
                    case((Game.winner_player_id == Player.id, 1), else_=0)
                ).label('wins'),
            )
            .join(Game, Game.id == Player.game_id)
            .filter(Game.state == 'finished')
            .group_by(Player.user_id)
            .all()
        )
        stats_by_user = {row.user_id: row for row in stat_rows}

        rankings = []
        # AI opponents participate in games, but rankings are a comparison
        # between human players.  Filter on the persisted flag rather than a
        # username convention so renamed/additional bots stay excluded.
        for user in User.query.filter(User.is_ai.is_(False)).all():
            stats = stats_by_user.get(user.id)
            total = stats.total if stats else 0
            wins = int(stats.wins) if stats and stats.wins is not None else 0
            is_online = False
            if user.last_active:
                is_online = (_utcnow() - user.last_active).total_seconds() < 60
            rankings.append({
                'username': user.username,
                'gold': user.gold,
                'total_games': total,
                'wins': wins,
                'losses': total - wins,
                'is_online': is_online,
            })
        return jsonify({'success': True, 'rankings': rankings})
    except Exception as e:
        db.session.rollback()
        logging.error(f"Rankings failed: {e}")
        return jsonify({'success': False, 'message': 'Failed to fetch rankings'}), 500


# ── Notification email preferences ────────────────────────────────

@auth.route('/unsubscribe', methods=['GET'])
def unsubscribe():
    """One-click opt-out used in every notification email (no login needed,
    authenticated by an HMAC of the user id)."""
    from notification_service import verify_unsubscribe_sig

    uid = request.args.get('uid', '')
    sig = request.args.get('sig', '')
    try:
        user_id = int(uid)
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Invalid link'}), 400
    if not verify_unsubscribe_sig(user_id, sig):
        return jsonify({'success': False, 'message': 'Invalid link'}), 400
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'success': False, 'message': 'Invalid link'}), 400
    user.notify_emails_enabled = False
    db.session.commit()
    logger.info(f"User '{user.username}' unsubscribed from notification emails")
    return (
        '<html><body style="font-family:sans-serif;text-align:center;padding-top:4em">'
        '<h2>Unsubscribed</h2>'
        '<p>You will no longer receive gameplay emails from Nepal Kings.</p>'
        '<p>You can re-enable them anytime in the in-game settings.</p>'
        '</body></html>',
        200,
        {'Content-Type': 'text/html; charset=utf-8'},
    )


@auth.route('/set_notifications', methods=['POST'])
@require_token
def set_notifications():
    """Toggle gameplay notification emails for the logged-in user."""
    user = db.session.get(User, g.user_id)
    if not user:
        return jsonify({'success': False, 'message': 'User not found'}), 404
    user.notify_emails_enabled = _truthy_form_value('enabled')
    db.session.commit()
    return jsonify({
        'success': True,
        'notify_emails_enabled': bool(user.notify_emails_enabled),
    })
