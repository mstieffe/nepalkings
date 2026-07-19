# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Database-backed fixed-window limits for security-sensitive operations."""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from models import db


logger = logging.getLogger('nepalkings.security.rate_limit')


def _utc_datetime(epoch_seconds):
    return datetime.fromtimestamp(
        epoch_seconds,
        tz=timezone.utc,
    ).replace(tzinfo=None)


def consume_rate_limit(scope, identity, *, limit, window_seconds, now=None):
    """Consume one shared fixed-window slot.

    Returns ``(allowed, remaining, retry_after_seconds)``. The counter key is a
    one-way digest so IP addresses and user identifiers are not stored in
    plaintext.
    """
    limit = max(1, int(limit))
    window_seconds = max(1, int(window_seconds))
    now_epoch = float(time.time() if now is None else now)
    window_id = int(now_epoch // window_seconds)
    window_end = (window_id + 1) * window_seconds
    raw_key = f'{scope}:{identity}:{window_id}'.encode('utf-8')
    key = hashlib.sha256(raw_key).hexdigest()
    expires_at = _utc_datetime(window_end)
    now_db = _utc_datetime(now_epoch)

    try:
        # Cleanup stays cheap because expires_at is indexed and sensitive
        # actions are a tiny fraction of normal gameplay polling.
        db.session.execute(
            text(
                'DELETE FROM security_rate_limit_counter '
                'WHERE expires_at <= :now'
            ),
            {'now': now_db},
        )
        count = db.session.execute(
            text(
                'INSERT INTO security_rate_limit_counter '
                '(key, count, expires_at) '
                'VALUES (:key, 1, :expires_at) '
                'ON CONFLICT (key) DO UPDATE SET '
                'count = security_rate_limit_counter.count + 1 '
                'RETURNING count'
            ),
            {
                'key': key,
                'expires_at': expires_at,
            },
        ).scalar_one()
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        # The existing Flask-Limiter process-local guard remains active. Fail
        # open here so a counter-table incident does not become an auth outage.
        logger.exception('Shared security rate-limit counter failed')
        return True, limit, 0

    remaining = max(0, limit - int(count))
    retry_after = max(1, int(window_end - now_epoch))
    return int(count) <= limit, remaining, retry_after
