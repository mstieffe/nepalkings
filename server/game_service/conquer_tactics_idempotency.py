# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""In-process idempotency cache and per-game mutex for conquer tactic actions.

Clients optionally include a ``client_action_id`` (UUID) with each mutating
conquer-tactic request. When the server processes the request it stores the
resulting JSON-serialisable response keyed by ``(game_id, player_id, endpoint,
client_action_id)``. If the client retries with the same ``client_action_id``
(e.g. after a network timeout) the cached response is returned verbatim — no
duplicate state mutation occurs.

This module also exposes :func:`game_lock` so the five mutating conquer-tactic
endpoints can serialise concurrent requests on the same game (e.g. a withdraw
arriving while the opponent is mid-play). The lock is a per-process
``threading.RLock`` keyed by game id; it is best-effort only and does not span
multiple workers, but combined with the idempotency cache it eliminates the
most common race patterns observed in the unified conquer redesign.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from contextlib import contextmanager
from typing import Any, Optional


_CACHE_TTL_SECONDS = 60.0
_CACHE_MAX_ENTRIES = 2048


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
    return (int(game_id) if game_id is not None else None,
            int(player_id) if player_id is not None else None,
            str(endpoint),
            str(client_action_id))


def get_cached_response(game_id, player_id, endpoint,
                       client_action_id) -> Optional[Any]:
    """Return a cached response for an idempotent retry, or None."""
    if not client_action_id:
        return None
    return _RESPONSE_CACHE.get(
        _cache_key(game_id, player_id, endpoint, client_action_id))


def store_response(game_id, player_id, endpoint, client_action_id,
                  response) -> None:
    """Cache a response so a future retry with the same id replays it."""
    if not client_action_id:
        return
    _RESPONSE_CACHE.set(
        _cache_key(game_id, player_id, endpoint, client_action_id),
        response,
    )


def reset_cache_for_tests() -> None:
    """Test helper: drop all cached responses and per-game locks."""
    _RESPONSE_CACHE.clear()
    with _GAME_LOCK_GUARD:
        _GAME_LOCKS.clear()


@contextmanager
def game_lock(game_id):
    """Serialise mutations on a single conquer game within this process.

    Falls back to a no-op when ``game_id`` is None so callers can defer
    validation without breaking the context-manager protocol.
    """
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
        yield
    finally:
        lock.release()
