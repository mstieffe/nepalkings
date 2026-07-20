# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Shared, deliberately small moderation helpers."""

from datetime import datetime, timezone

from models import db, UserBlock


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def blocked_user_ids(user_id):
    """Return users hidden by *user_id*.

    A player's own block list controls what that player sees. Sending direct
    contact is stricter: :func:`direct_contact_blocked` checks both directions.
    """
    rows = db.session.query(UserBlock.blocked_user_id).filter_by(
        blocker_user_id=user_id).all()
    return {row[0] for row in rows}


def direct_contact_blocked(user_a_id, user_b_id):
    """Return True if either human has blocked the other."""
    if not user_a_id or not user_b_id:
        return False
    return UserBlock.query.filter(
        db.or_(
            db.and_(
                UserBlock.blocker_user_id == user_a_id,
                UserBlock.blocked_user_id == user_b_id,
            ),
            db.and_(
                UserBlock.blocker_user_id == user_b_id,
                UserBlock.blocked_user_id == user_a_id,
            ),
        )
    ).first() is not None


def active_chat_mute(user):
    """Return the mute expiry, clearing an expired mute in memory."""
    muted_until = getattr(user, 'chat_muted_until', None)
    if muted_until and muted_until <= utcnow():
        user.chat_muted_until = None
        return None
    return muted_until
