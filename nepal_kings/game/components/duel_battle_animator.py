# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Draw-only reveal animator for the duel battle rounds panel.

Duel battle moves arrive incrementally (own plays locally, opponent plays
via the ~1s battle-state poll), so unlike the conquer reveal sequencer
there is no hidden-commit flip to choreograph — just an arrival pop per
slot and a completion beat per round.

Design contract (same philosophy as ``ConquerEffectsLayer``):
* **Additive only** — the animator never mutates battle state; it diffs
  the played-move lists it is shown and keeps its own timing records.
* **Seed on first sight** — the first ``note_slots`` call records the
  current board silently, so reconnecting into a half-played battle never
  replays pops the player has already seen.
* **Time-bounded** — every record self-expires (``POP_MS`` / ``BEAT_MS``),
  so ``is_active()`` can gate user actions without ever wedging the
  screen; ``fast_forward()`` drops all records immediately.

``now`` is injectable everywhere for tests; it defaults to
``pygame.time.get_ticks()``.
"""
from typing import Any, Dict, List, Optional, Tuple

import pygame

Slot = Tuple[str, int]  # ('player' | 'opponent', round_index)


class DuelSlotAnimator:
    POP_MS = 260   # slot entrance pop duration
    BEAT_MS = 420  # round-complete beat window

    def __init__(self):
        self._seen: Optional[Dict[Slot, Any]] = None  # None → seed on first note
        self._pops: Dict[Slot, int] = {}              # slot -> started_at
        self._beats: Dict[int, int] = {}              # round -> started_at
        self._beaten: set = set()                     # rounds that already had their beat

    # ------------------------------------------------------------------ util
    @staticmethod
    def _now(now: Optional[int]) -> int:
        return int(now) if now is not None else pygame.time.get_ticks()

    @staticmethod
    def _identity(move: Any) -> Optional[Tuple]:
        """Stable identity of a played slot (None while the slot is empty)."""
        if not isinstance(move, dict):
            return None
        if move.get('_skipped'):
            return ('skip',)
        return ('move', move.get('id'), move.get('family_name'))

    def _prune(self, now: int) -> None:
        self._pops = {k: v for k, v in self._pops.items()
                      if now - v < self.POP_MS}
        self._beats = {k: v for k, v in self._beats.items()
                       if now - v < self.BEAT_MS}

    # ----------------------------------------------------------------- events
    def note_slots(self, player_played, opponent_played, *,
                   now: Optional[int] = None) -> List[Tuple]:
        """Diff the played-move lists against the last seen state.

        Returns the newly-detected events, in order:
        ``('slot', side, round_index)`` for each newly-filled slot, then
        ``('round_complete', round_index)`` for each round whose second
        slot just arrived.
        """
        now = self._now(now)
        current: Dict[Slot, Any] = {}
        for side, slots in (('player', player_played or []),
                            ('opponent', opponent_played or [])):
            for r, move in enumerate(slots):
                ident = self._identity(move)
                if ident is not None:
                    current[(side, r)] = ident

        if self._seen is None:
            # First sight: adopt silently (reconnect / battle already running).
            self._seen = current
            self._beaten = {r for r in range(3)
                            if ('player', r) in current and ('opponent', r) in current}
            return []

        events: List[Tuple] = []
        for slot, ident in current.items():
            if self._seen.get(slot) != ident:
                self._pops[slot] = now
                events.append(('slot', slot[0], slot[1]))

        for r in range(3):
            if r in self._beaten:
                continue
            if ('player', r) in current and ('opponent', r) in current:
                self._beaten.add(r)
                self._beats[r] = now
                events.append(('round_complete', r))

        self._seen = current
        self._prune(now)
        return events

    # ---------------------------------------------------------------- queries
    def slot_anim(self, side: str, round_index: int, *,
                  now: Optional[int] = None) -> Optional[float]:
        """Pop progress 0..1 for a slot, or ``None`` once settled."""
        started = self._pops.get((side, round_index))
        if started is None:
            return None
        t = (self._now(now) - started) / max(1, self.POP_MS)
        if t >= 1.0:
            self._pops.pop((side, round_index), None)
            return None
        return max(0.0, t)

    def is_active(self, *, now: Optional[int] = None) -> bool:
        """True while any pop/beat is still playing (time-bounded)."""
        self._prune(self._now(now))
        return bool(self._pops or self._beats)

    # ---------------------------------------------------------------- control
    def fast_forward(self) -> None:
        """Drop all running animations (click-to-skip); seen state is kept."""
        self._pops.clear()
        self._beats.clear()

    def reset(self) -> None:
        """Forget everything (new battle / new game)."""
        self._seen = None
        self._pops.clear()
        self._beats.clear()
        self._beaten.clear()
