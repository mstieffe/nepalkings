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
from werkzeug.security import generate_password_hash, check_password_hash

from models import db, User, Player, Game
import server_settings as settings

auth = Blueprint('auth', __name__)

logger = logging.getLogger('nepalkings.routes.auth')


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

# ── Validation constants ──
_USERNAME_MIN = 3
_USERNAME_MAX = 30
_USERNAME_RE = re.compile(r'^[a-zA-Z0-9_-]+$')
_PASSWORD_MIN = 6


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


# ── Long-lived AI service token max age (1 year) ──
_AI_TOKEN_MAX_AGE = 365 * 24 * 3600


# ── Token helpers ─────────────────────────────────────────────────

def generate_token(user_id):
    """Generate a short-lived signed token for a human user."""
    s = URLSafeTimedSerializer(settings.SECRET_KEY)
    return s.dumps(user_id, salt='user-auth')


def generate_ai_token(user_id):
    """Generate a long-lived signed token for an AI service account (1-year TTL)."""
    s = URLSafeTimedSerializer(settings.SECRET_KEY)
    return s.dumps(user_id, salt='ai-service')


def validate_token(token):
    """Validate a Bearer token and return the user_id it encodes.

    Tries the short-lived user-auth salt first; if that fails with
    BadSignature (wrong salt), falls back to the long-lived ai-service salt.
    Raises SignatureExpired or BadSignature on failure.
    """
    s = URLSafeTimedSerializer(settings.SECRET_KEY)
    try:
        return s.loads(token, salt='user-auth', max_age=settings.TOKEN_EXPIRY_SECONDS)
    except SignatureExpired:
        raise  # Expired user token — let caller return 401
    except BadSignature:
        pass  # Might be an AI service token — try the other salt
    # AI service token: tolerate up to 1 year
    return s.loads(token, salt='ai-service', max_age=_AI_TOKEN_MAX_AGE)


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
            g.user_id = validate_token(token)
        except SignatureExpired:
            return jsonify({'success': False, 'message': 'Session expired, please log in again'}), 401
        except BadSignature:
            return jsonify({'success': False, 'message': 'Invalid token'}), 401
        return f(*args, **kwargs)
    return decorated


# ── Player-ownership helper ───────────────────────────────────────

def verify_player_ownership(player_id):
    """Check that the authenticated user (g.user_id) owns player_id.

    Returns a JSON error response tuple on failure, or None on success.
    Must be called inside a route protected by @require_token.

    Side-effect: bumps Game.last_activity_at for the player's game so the
    stuck-game sweeper doesn't kill games with active client activity.
    """
    player = db.session.get(Player, player_id)
    if not player:
        return jsonify({'success': False, 'message': 'Player not found'}), 404
    if player.user_id != g.user_id:
        return jsonify({'success': False, 'message': 'Forbidden: player does not belong to authenticated user'}), 403
    # Touch game activity timestamp (best-effort, don't fail auth on error).
    try:
        if player.game_id:
            game = db.session.get(Game, player.game_id)
            if game and game.state != 'finished':
                game.last_activity_at = datetime.now(timezone.utc)
    except Exception:
        pass
    return None


# ── Email helper ──────────────────────────────────────────────────

def _send_verification_email(user):
    """Send (or log) an email-verification link for the given user."""
    token = user.email_verification_token
    verify_url = f"{settings.SERVER_BASE_URL}/auth/verify_email?token={token}"

    if not settings.EMAIL_VERIFICATION_ENABLED or not settings.SMTP_HOST:
        logger.info(
            f"[EMAIL VERIFICATION] User '{user.username}' — verify URL (no SMTP configured): {verify_url}"
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
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        email = request.form.get('email', '').strip().lower() or None

        if not username or not password:
            return jsonify({'success': False, 'message': 'Missing username or password'}), 400

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
            booster_packs=settings.STARTER_BOOSTER_PACKS,
            booster_packs_side=settings.STARTER_BOOSTER_PACKS_SIDE,
        )
        db.session.add(user)
        db.session.commit()

        if email and verification_token:
            _send_verification_email(user)

        auth_token = generate_token(user.id)
        serialized_user = user.serialize()

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
        user.last_active = _utcnow()
        db.session.commit()

        token = generate_token(user.id)
        serialized_user = user.serialize()

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
                game = db.session.get(Game, p.game_id)
                if game and game.state == 'finished':
                    total += 1
                    if game.winner_player_id == p.id:
                        wins += 1
                    else:
                        losses += 1
            is_online = False
            if user.last_active:
                is_online = (_utcnow() - user.last_active).total_seconds() < 60
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
