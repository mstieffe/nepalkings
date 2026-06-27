# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Email notifications for asynchronous play.

Without these, an async duel dies the moment one player closes the app —
they never learn it's their turn again. Three notification kinds:

- challenge received   (hooked in routes/challenges.py)
- it's your turn       (app-level after_request hook, debounced per game)
- game finished        (same hook, once per recipient)

Safety properties:
- Only sent to human accounts that have an email, have not opted out
  (User.notify_emails_enabled, one-click unsubscribe link in every mail),
  and are NOT currently online (heartbeat within ONLINE_WINDOW_SECONDS).
- "Your turn" is debounced: at most one email per game per recipient per
  TURN_EMAIL_MIN_INTERVAL_HOURS, tracked in Game.turn_email_log.
- SMTP happens on a daemon thread; the request never waits on it.
- Without SMTP_HOST configured (or with NOTIFY_EMAILS_ENABLED=False) the
  would-be email is logged instead — safe default for dev.
"""

import hashlib
import hmac
import logging
import smtplib
import threading
from datetime import datetime, timezone
from email.mime.text import MIMEText

from sqlalchemy.orm.attributes import flag_modified

import server_settings as settings
import security_settings
from models import db, Game, Player, User

logger = logging.getLogger('nepalkings.notifications')

ONLINE_WINDOW_SECONDS = 120
TURN_EMAIL_MIN_INTERVAL_HOURS = 6


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── Eligibility ────────────────────────────────────────────────────

def _user_wants_email(user):
    if not user or getattr(user, 'is_ai', False) or not user.email:
        return False
    if not getattr(user, 'notify_emails_enabled', True):
        return False
    # Only require a verified address when verification is actually enforced.
    if settings.EMAIL_VERIFICATION_ENABLED and not user.email_verified:
        return False
    return True


def _user_recently_active(user, window_seconds=ONLINE_WINDOW_SECONDS):
    if not user or not user.last_active:
        return False
    return (_utcnow() - user.last_active).total_seconds() < window_seconds


# ── Unsubscribe links ──────────────────────────────────────────────

def unsubscribe_sig(user_id):
    """Stable HMAC so unsubscribe links work without a login."""
    key = security_settings.SECRET_KEY.encode()
    msg = f'unsubscribe:{int(user_id)}'.encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()[:32]


def verify_unsubscribe_sig(user_id, sig):
    try:
        return hmac.compare_digest(unsubscribe_sig(user_id), str(sig or ''))
    except (TypeError, ValueError):
        return False


def _footer(user):
    base = settings.SERVER_BASE_URL.rstrip('/')
    link = f'{base}/auth/unsubscribe?uid={user.id}&sig={unsubscribe_sig(user.id)}'
    play = getattr(settings, 'WEB_CLIENT_URL', '') or ''
    lines = ['']
    if play:
        lines.append(f'Play now: {play}')
    lines.append(f'Stop these emails: {link}')
    return '\n'.join(lines)


# ── Transport ──────────────────────────────────────────────────────

def _send_sync(to_addr, subject, body):
    if not getattr(settings, 'NOTIFY_EMAILS_ENABLED', True) or not settings.SMTP_HOST:
        logger.info('[EMAIL OFF] To: %s — %s', to_addr, subject)
        return False
    try:
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = settings.SMTP_FROM
        msg['To'] = to_addr
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as smtp:
            smtp.ehlo()
            smtp.starttls()
            if settings.SMTP_USER and settings.SMTP_PASSWORD:
                smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(msg)
        logger.info('Notification sent to %s — %s', to_addr, subject)
        return True
    except Exception:
        logger.exception('Failed to send notification to %s', to_addr)
        return False


def _send_async(to_addr, subject, body):
    threading.Thread(target=_send_sync, args=(to_addr, subject, body),
                     daemon=True, name='nk-notify-email').start()


# ── Notifications ──────────────────────────────────────────────────

def notify_challenge_received(challenge):
    """Email the challenged player. Call after the challenge is committed."""
    try:
        opponent = challenge.challenged
        challenger = challenge.challenger
        if not _user_wants_email(opponent) or _user_recently_active(opponent):
            return False
        subject = f'{challenger.username} challenged you to a duel — Nepal Kings'
        body = (
            f'Hi {opponent.username},\n\n'
            f'{challenger.username} has challenged you to a duel '
            f'(stake {challenge.stake} gold, first to {challenge.game_limit} points).\n\n'
            f'Log in to accept or decline.\n'
            f'{_footer(opponent)}'
        )
        _send_async(opponent.email, subject, body)
        return True
    except Exception:
        logger.exception('notify_challenge_received failed')
        return False


def _turn_log(game):
    log = game.turn_email_log
    return dict(log) if isinstance(log, dict) else {}


def _opponent_username(game, player):
    for p in game.players:
        if p.id != player.id:
            u = db.session.get(User, p.user_id)
            return u.username if u else 'your opponent'
    return 'your opponent'


def _notify_turn(game, player, user):
    log = _turn_log(game)
    key = f'turn:{user.id}'
    last = log.get(key)
    if last:
        try:
            last_dt = datetime.fromisoformat(last)
            hours = (_utcnow() - last_dt).total_seconds() / 3600.0
            if hours < TURN_EMAIL_MIN_INTERVAL_HOURS:
                return False
        except (TypeError, ValueError):
            pass
    log[key] = _utcnow().isoformat(timespec='seconds')
    game.turn_email_log = log
    flag_modified(game, 'turn_email_log')
    db.session.commit()

    opponent_name = _opponent_username(game, player)
    subject = f"It's your turn against {opponent_name} — Nepal Kings"
    body = (
        f'Hi {user.username},\n\n'
        f'Your duel against {opponent_name} is waiting on you '
        f'(game #{game.id}, round {game.current_round}).\n\n'
        f'Log in to make your move.\n'
        f'{_footer(user)}'
    )
    _send_async(user.email, subject, body)
    return True


def _notify_finished(game, player, user):
    log = _turn_log(game)
    key = f'finish:{user.id}'
    if log.get(key):
        return False
    log[key] = _utcnow().isoformat(timespec='seconds')
    game.turn_email_log = log
    flag_modified(game, 'turn_email_log')
    db.session.commit()

    opponent_name = _opponent_username(game, player)
    won = game.winner_player_id == player.id
    if game.winner_player_id is None:
        outcome = 'Your game ended in a draw'
    elif won:
        outcome = 'You WON your game'
    else:
        outcome = 'You lost your game'
    subject = f'{outcome.split("your")[0].strip()} against {opponent_name} — Nepal Kings'
    body = (
        f'Hi {user.username},\n\n'
        f'{outcome} against {opponent_name} (game #{game.id}).\n\n'
        f'Log in to review the result and start your next match.\n'
        f'{_footer(user)}'
    )
    _send_async(user.email, subject, body)
    return True


def maybe_notify_turn_or_finish(game_id, requester_user_id=None):
    """Inspect a game after a state-changing request and email whoever
    should hear about it. Cheap, debounced, never raises."""
    try:
        game = db.session.get(Game, int(game_id))
        if not game or game.mode != 'duel':
            return False

        if game.state == 'finished':
            sent = False
            for p in game.players:
                user = db.session.get(User, p.user_id)
                if not _user_wants_email(user) or user.id == requester_user_id:
                    continue
                if _user_recently_active(user):
                    continue
                sent = _notify_finished(game, p, user) or sent
            return sent

        turn_player_id = game.turn_player_id
        if not turn_player_id:
            return False
        player = db.session.get(Player, turn_player_id)
        if not player:
            return False
        user = db.session.get(User, player.user_id)
        if not _user_wants_email(user):
            return False
        if user.id == requester_user_id:
            return False  # it's the requester's own turn; they're right here
        if _user_recently_active(user):
            return False  # actively playing — in-app polling covers them
        return _notify_turn(game, player, user)
    except Exception:
        logger.exception('maybe_notify_turn_or_finish failed for game %s', game_id)
        try:
            db.session.rollback()
        except Exception:
            pass
        return False
