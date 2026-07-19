# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Durable idempotency and cross-worker locking for game mutations.

Clients optionally include a ``client_action_id`` with mutating Conquer
requests. Successful responses are cached in-process and persisted briefly in
the database so a retry routed to another WSGI worker receives the same
response.

PostgreSQL deployments also use transaction-level advisory locks keyed by game
ID. SQLite and local tests retain a per-process ``threading.RLock`` fallback.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from collections import OrderedDict
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from flask import has_app_context
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError


_CACHE_TTL_SECONDS = 60.0
_CACHE_MAX_ENTRIES = 2048
_POSTGRES_GAME_LOCK_NAMESPACE = 20043

logger = logging.getLogger('nepalkings.conquer.coordination')


class _LRUTTLCache:
    """Tiny LRU + TTL cache used to dedupe replayed mutating requests."""

    def __init__(self, max_entries: int = _CACHE_MAX_ENTRIES,
                 ttl_seconds: float = _CACHE_TTL_SECONDS) -> None:
        self._max_entries = max_entries
        self._ttl = ttl_seconds
        self._store: "OrderedDict[tuple, tuple[float, Any]]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: tuple) -> Optional[Any]:
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at < now:
                self._store.pop(key, None)
                return None
            self._store.move_to_end(key)
            return value

    def set(self, key: tuple, value: Any) -> None:
        expires_at = time.monotonic() + self._ttl
        with self._lock:
            self._store[key] = (expires_at, value)
            self._store.move_to_end(key)
            while len(self._store) > self._max_entries:
                self._store.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


_RESPONSE_CACHE = _LRUTTLCache()
_GAME_LOCKS: "dict[int, threading.RLock]" = {}
_GAME_LOCK_GUARD = threading.Lock()


def _cache_key(game_id, player_id, endpoint, client_action_id):
    action_digest = hashlib.sha256(
        str(client_action_id).encode('utf-8'),
    ).hexdigest()
    return (
        int(game_id) if game_id is not None else None,
        int(player_id) if player_id is not None else None,
        str(endpoint),
        action_digest,
    )


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _get_persisted_response(key) -> Optional[Any]:
    if not has_app_context():
        return None
    try:
        from models import ConquerActionReceipt

        game_id, player_id, endpoint, client_action_id = key
        receipt = ConquerActionReceipt.query.filter_by(
            game_id=game_id,
            player_id=player_id,
            endpoint=endpoint,
            client_action_id=client_action_id,
        ).first()
        if receipt is None or receipt.expires_at <= _utcnow():
            return None
        return receipt.response_body
    except SQLAlchemyError:
        # Production deploys create this table before reload. The fallback
        # keeps a partially migrated local database usable long enough to run
        # the explicit preparation command.
        from models import db

        db.session.rollback()
        logger.exception('Failed to read durable Conquer action receipt')
        return None


def get_cached_response(game_id, player_id, endpoint,
                        client_action_id) -> Optional[Any]:
    """Return a cached response for an idempotent retry, or ``None``."""
    if not client_action_id:
        return None
    key = _cache_key(game_id, player_id, endpoint, client_action_id)
    cached = _RESPONSE_CACHE.get(key)
    if cached is not None:
        return cached
    persisted = _get_persisted_response(key)
    if persisted is not None:
        _RESPONSE_CACHE.set(key, persisted)
    return persisted


def store_response(game_id, player_id, endpoint, client_action_id,
                   response) -> None:
    """Store a short-lived response receipt for cross-worker retries."""
    if not client_action_id:
        return
    key = _cache_key(game_id, player_id, endpoint, client_action_id)
    _RESPONSE_CACHE.set(key, response)
    if not has_app_context():
        return

    from models import ConquerActionReceipt, db

    now = _utcnow()
    expires_at = now + timedelta(seconds=_CACHE_TTL_SECONDS)
    try:
        ConquerActionReceipt.query.filter(
            ConquerActionReceipt.expires_at <= now,
        ).delete(synchronize_session=False)
        receipt = ConquerActionReceipt.query.filter_by(
            game_id=key[0],
            player_id=key[1],
            endpoint=key[2],
            client_action_id=key[3],
        ).first()
        if receipt is None:
            db.session.add(ConquerActionReceipt(
                game_id=key[0],
                player_id=key[1],
                endpoint=key[2],
                client_action_id=key[3],
                response_body=response,
                created_at=now,
                expires_at=expires_at,
            ))
        else:
            receipt.response_body = response
            receipt.expires_at = expires_at
        db.session.commit()
    except IntegrityError:
        # A concurrent worker stored the same successful action first.
        db.session.rollback()
    except SQLAlchemyError:
        db.session.rollback()
        logger.exception('Failed to persist Conquer action receipt')


def reset_cache_for_tests() -> None:
    """Drop process-local cached responses and mutexes."""
    _RESPONSE_CACHE.clear()
    with _GAME_LOCK_GUARD:
        _GAME_LOCKS.clear()


def acquire_game_transaction_lock(game_id):
    """Acquire the PostgreSQL transaction lock for one game.

    PostgreSQL holds this lock until the current SQLAlchemy transaction commits
    or rolls back. Non-PostgreSQL databases rely on :func:`game_lock`'s local
    mutex.
    """
    if game_id is None or not has_app_context():
        return False

    from models import db

    bind = db.session.get_bind()
    if bind.dialect.name != 'postgresql':
        return False
    db.session.execute(
        text('SELECT pg_advisory_xact_lock(:namespace, :game_id)'),
        {
            'namespace': _POSTGRES_GAME_LOCK_NAMESPACE,
            'game_id': int(game_id),
        },
    )
    return True


@contextmanager
def game_lock(game_id):
    """Serialise mutations on one game across threads and WSGI workers."""
    if game_id is None:
        yield
        return
    key = int(game_id)
    with _GAME_LOCK_GUARD:
        lock = _GAME_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _GAME_LOCKS[key] = lock
    lock.acquire()
    try:
        acquire_game_transaction_lock(key)
        yield
    finally:
        lock.release()
