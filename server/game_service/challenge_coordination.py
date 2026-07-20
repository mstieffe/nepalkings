# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Cross-worker coordination for accepting one Duel challenge."""

from __future__ import annotations

import threading
from contextlib import contextmanager

from models import Challenge, db


_CHALLENGE_LOCKS: dict[int, threading.RLock] = {}
_CHALLENGE_LOCKS_GUARD = threading.Lock()


@contextmanager
def locked_challenge_for_game_creation(challenge_id):
    """Yield one challenge while preventing concurrent game creation.

    The process-local mutex covers SQLite development and multiple request
    threads in one worker. PostgreSQL's ``FOR UPDATE`` row lock covers all
    WSGI workers and is held until the caller commits or rolls back.
    """
    try:
        key = int(challenge_id)
    except (TypeError, ValueError):
        yield None
        return

    with _CHALLENGE_LOCKS_GUARD:
        local_lock = _CHALLENGE_LOCKS.get(key)
        if local_lock is None:
            local_lock = threading.RLock()
            _CHALLENGE_LOCKS[key] = local_lock

    local_lock.acquire()
    try:
        statement = (
            db.select(Challenge)
            .where(Challenge.id == key)
            .with_for_update()
        )
        challenge = db.session.execute(statement).scalar_one_or_none()
        yield challenge
    finally:
        local_lock.release()
