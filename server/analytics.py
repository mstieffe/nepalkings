# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""First-party product analytics: a minimal append-only event log.

Usage from any route or service running inside the app context:

    from analytics import track
    track('game_finished', user_id=winner.user_id, mode=game.mode)

Contract:
- track() NEVER raises into the caller; failures are logged and swallowed.
- The event rides along with the caller's session — call track() before the
  route's db.session.commit() so the event commits atomically with the
  action it records. If the route rolls back, the event rolls back too,
  which is the desired behaviour (events describe committed reality).
- No third parties, no IPs, no user agents: only the user id, an event
  name, and small JSON props. See docs/legal/PRIVACY.md.

Disable entirely with ANALYTICS_ENABLED=False in the environment.
"""

import logging

import server_settings as settings
from models import db, Event

logger = logging.getLogger(__name__)

_MAX_NAME_LEN = 64


def track(name, user_id=None, **props):
    """Record one analytics event. Returns True if queued on the session."""
    if not getattr(settings, 'ANALYTICS_ENABLED', True):
        return False
    try:
        event = Event(
            user_id=int(user_id) if user_id is not None else None,
            name=str(name)[:_MAX_NAME_LEN],
            props={k: v for k, v in props.items() if v is not None} or None,
        )
        db.session.add(event)
        return True
    except Exception:
        logger.exception('analytics.track(%r) failed', name)
        return False
