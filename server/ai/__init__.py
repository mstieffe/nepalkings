# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""
AI Opponent module for Nepal Kings.

Manages AI user registration, background AI worker threads,
and LLM-based decision making.
"""
import logging
import secrets
from models import db, User
from werkzeug.security import generate_password_hash
import server_settings as settings

logger = logging.getLogger('nepalkings.ai')


def init_ai_users():
    """Create AI user accounts if they don't exist. Called at server startup."""
    for ai_name in settings.AI_USERNAMES:
        existing = User.query.filter_by(username=ai_name).first()
        if existing:
            # Ensure the is_ai flag is set (for migration from older versions)
            if not existing.is_ai:
                existing.is_ai = True
                db.session.commit()
            # Ensure AI has enough gold
            if existing.gold < settings.AI_INITIAL_GOLD:
                existing.gold = settings.AI_INITIAL_GOLD
                db.session.commit()
            logger.info(f"AI user '{ai_name}' already exists (id={existing.id})")
        else:
            # Create with a random unguessable password (AI never logs in via auth)
            ai_user = User(
                username=ai_name,
                password_hash=generate_password_hash(secrets.token_hex(32)),
                gold=settings.AI_INITIAL_GOLD,
                is_ai=True,
            )
            db.session.add(ai_user)
            db.session.commit()
            logger.info(f"Created AI user '{ai_name}' (id={ai_user.id})")


def is_ai_user(user_id):
    """Check if a user_id belongs to an AI player."""
    user = User.query.get(user_id)
    return user is not None and user.is_ai


def get_ai_player_in_game(game):
    """Return the Player object for the AI in this game, or None."""
    for player in game.players:
        user = User.query.get(player.user_id)
        if user and user.is_ai:
            return player
    return None
