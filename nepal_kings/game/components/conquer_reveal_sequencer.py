# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Staged round-reveal sequencer for the unified conquer battle screen.

When a battle round completes on the server, the poll delivers the
opponent's tactic and the round diff *as data*. Without staging, the
result simply pops into the round ledger — the most important beat of
the battle resolves with no drama.

This component withholds the *display* of a freshly-completed round and
plays a short choreography instead:

``HOLD``   opponent slot pulses face-down (the tension beat)
``FLIP``   both tactics flip face-up (identity reveal)
``TALLY``  the round diff counts up from zero
``IMPACT`` the diff lands — effects layer pulse + floating text
``DONE``   normal rendering resumes (gold sweep flourish)

Design rules (mirrors the spell-step replay system):

* **Display-only.** The server data is authoritative and already
  delivered; nothing here mutates game state or delays actions beyond a
  short input block while the sequence plays.
* **Seed on first sight.** On entering a game (or reloading mid-battle)
  every already-complete round is marked revealed WITHOUT animating, so
  history never replays — the same contract as
  ``_spell_anim_seeded`` / ``_spell_step_phase_map``.
* **Always skippable.** Any click fast-forwards the active sequence.
* **FIFO.** If one poll completes multiple rounds (rare), sequences
  queue and play in round order.

The sequencer is owned by ``ConquerGameScreen``; the round ledger, duel
lane and timeline consume its gated view via
``ConquerGameScreen._conquer_lane_played_tactics``.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pygame


# Stage keys, in play order.
STAGE_HOLD = 'hold'
STAGE_FLIP = 'flip'
STAGE_TALLY = 'tally'
STAGE_IMPACT = 'impact'

_STAGE_ORDER = (STAGE_HOLD, STAGE_FLIP, STAGE_TALLY, STAGE_IMPACT)

# Default per-stage durations (ms). Total ~1.7s.
STAGE_DURATIONS_MS = {
    STAGE_HOLD: 320,
    STAGE_FLIP: 360,
    STAGE_TALLY: 620,
    STAGE_IMPACT: 420,
}
# Skip-beats (either side skipped) play a shortened sequence.
SKIP_STAGE_DURATIONS_MS = {
    STAGE_HOLD: 160,
    STAGE_FLIP: 240,
    STAGE_TALLY: 360,
    STAGE_IMPACT: 300,
}
# The final round carries the battle decision — it earns a longer beat
# (~2.3s) so the tension peaks where the outcome lands.
FINAL_STAGE_DURATIONS_MS = {
    STAGE_HOLD: 520,
    STAGE_FLIP: 380,
    STAGE_TALLY: 840,
    STAGE_IMPACT: 520,
}
FINAL_ROUND_IDX = 2


def draw_face_down_card(window: pygame.Surface, rect: pygame.Rect) -> None:
    """A small stylised face-down tactic card (no identity revealed).

    Shared by the opponent hidden-hand strip and the round ledger's
    pre-reveal opponent chip so the "hidden card" language stays
    consistent across the battle UI.
    """
    radius = max(3, rect.width // 6)
    surf = pygame.Surface(rect.size, pygame.SRCALPHA)
    br = surf.get_rect()
    # Slate card-back with warm gold trim and a centred diamond emblem so it
    # reads as a real (hidden) card rather than an empty frame.
    pygame.draw.rect(surf, (34, 38, 58), br, border_radius=radius)
    pygame.draw.rect(surf, (58, 64, 92), br.inflate(-3, -3), border_radius=radius)
    pygame.draw.rect(surf, (196, 162, 92), br, 2, border_radius=radius)
    cx, cy = br.center
    d = max(3, int(min(rect.width, rect.height) * 0.22))
    diamond = [(cx, cy - d), (cx + d, cy), (cx, cy + d), (cx - d, cy)]
    pygame.draw.polygon(surf, (150, 124, 76), diamond)
    pygame.draw.polygon(surf, (214, 184, 112), diamond, 1)
    window.blit(surf, rect.topleft)


def _move_identity(move: Optional[Dict[str, Any]]):
    if not isinstance(move, dict):
        return None
    return (
        move.get('id'),
        move.get('card_id'),
        move.get('card_id_b'),
        move.get('family_name'),
        move.get('value'),
        move.get('played_round'),
        bool(move.get('_skipped')),
    )


def _is_skip(move: Optional[Dict[str, Any]]) -> bool:
    return bool(isinstance(move, dict)
                and (move.get('_skipped') or move.get('family_name') == 'Skip'))


class ConquerRevealSequencer:
    """Owns per-round reveal state for one conquer battle at a time.

    Parameters
    ----------
    parent : object
        ``ConquerGameScreen``. Used for game identity, raw played-tactic
        slots, and stage-event callbacks
        (``_on_conquer_round_reveal_event``). All access is defensive so
        minimal test doubles keep working.
    """

    def __init__(self, parent):
        self._parent = parent
        self._game_key = None
        self._seeded = False
        self._revealed: set = set()          # round idx fully revealed
        self._queue: List[Dict[str, Any]] = []   # pending sequences (FIFO)
        self._active: Optional[Dict[str, Any]] = None
        # Rounds observed *incomplete* during this session. Only these are
        # eligible for reveal choreography — anything else (history that
        # arrives complete with the first poll after a reload) reveals
        # instantly. Maps round idx → {'opp_seen': bool} where opp_seen
        # records that the opponent identity was already legitimately
        # visible before the round completed (opponent played first, e.g.
        # after Invader Swap) so the flip beat is skipped.
        self._eligible: Dict[int, Dict[str, Any]] = {}
        # Monotonic counter bumped whenever the gated display output
        # changes (enqueue / flip-midpoint / done). Consumed by lane
        # context cache keys so cached slots never go stale mid-reveal.
        self._display_version = 0

    # ------------------------------------------------------------------ util
    def _now(self) -> int:
        return pygame.time.get_ticks()

    def _current_game_key(self):
        state = getattr(self._parent, 'state', None)
        game = getattr(state, 'game', None) if state else None
        if game is None:
            return None
        return (getattr(game, 'game_id', None), getattr(game, 'player_id', None))

    def _game(self):
        state = getattr(self._parent, 'state', None)
        return getattr(state, 'game', None) if state else None

    def _emit(self, round_idx: int, event: str, payload: Optional[Dict[str, Any]] = None):
        handler = getattr(self._parent, '_on_conquer_round_reveal_event', None)
        if callable(handler):
            try:
                handler(round_idx, event, payload or {})
            except Exception:
                pass

    # ---------------------------------------------------------------- public
    def display_version(self) -> int:
        """Cache-key ingredient: bumps whenever gated output changes."""
        return self._display_version

    def is_active(self) -> bool:
        """True while a reveal sequence is playing (input-block window)."""
        return self._active is not None

    def has_pending(self) -> bool:
        return bool(self._queue) or self.is_active()

    def is_round_revealed(self, round_idx: int) -> bool:
        return round_idx in self._revealed

    def stage_for_round(self, round_idx: int) -> Optional[Dict[str, Any]]:
        """Return ``{'stage', 'progress', 'opp_visible', 'diff_factor'}``
        for the actively-animating round, else ``None``."""
        active = self._active
        if not active or active.get('round') != round_idx:
            return None
        return {
            'stage': active.get('stage'),
            'progress': float(active.get('progress') or 0.0),
            'opp_visible': bool(active.get('opp_visible')),
            'diff_factor': float(active.get('diff_factor') or 0.0),
        }

    def fast_forward(self) -> bool:
        """Skip the active sequence (and drain the queue) to DONE.

        Returns True if anything was skipped — callers use this to
        decide whether the triggering click was consumed.
        """
        skipped = False
        if self._active is not None:
            self._finish_active(emit_impact=True)
            skipped = True
        while self._queue:
            entry = self._queue.pop(0)
            self._reveal_instantly(entry['round'])
            skipped = True
        return skipped

    def reset(self):
        self._game_key = None
        self._seeded = False
        self._revealed = set()
        self._queue = []
        self._active = None
        self._eligible = {}
        self._display_version += 1

    # ------------------------------------------------------------------ gate
    def gate_slots(self, player_slots, opponent_slots):
        """Return display copies of the played-tactic slot arrays.

        For rounds that are complete but not yet revealed (queued, or in
        an active sequence before the FLIP midpoint) the opponent slot is
        replaced with ``None`` so every consumer — ledger, duel lane,
        timeline — renders it as "still hidden". The player's own tactic
        is never gated (they know what they played), and an opponent
        tactic that was already visible *before* the round completed
        (opponent committed first, e.g. after Invader Swap) is never
        un-revealed.
        """
        if not self._seeded:
            return list(player_slots), list(opponent_slots)
        gated_opp = list(opponent_slots)
        for idx in range(min(3, len(gated_opp))):
            if gated_opp[idx] is None or idx in self._revealed:
                continue
            # Incomplete rounds are never gated — the server only reveals
            # a played opponent tactic, and if the player has not yet
            # committed they legitimately get to see it.
            if idx >= len(player_slots) or player_slots[idx] is None:
                continue
            active = self._active
            if active is not None and active.get('round') == idx:
                if active.get('opp_visible'):
                    continue
                gated_opp[idx] = None
                continue
            queued = next(
                (entry for entry in self._queue if entry.get('round') == idx),
                None)
            if queued is not None and queued.get('opp_seen'):
                continue
            gated_opp[idx] = None
        return list(player_slots), gated_opp

    # ------------------------------------------------------------------ pump
    def pump(self):
        """Advance the sequencer one frame. Call once per rendered frame."""
        game = self._game()
        if game is None:
            return
        key = self._current_game_key()
        if key != self._game_key:
            self.reset()
            self._game_key = key

        raw_getter = getattr(self._parent, '_conquer_lane_played_tactics_raw', None)
        if not callable(raw_getter):
            return
        try:
            player_slots, opponent_slots = raw_getter()
        except Exception:
            return

        finished = bool(getattr(game, 'last_battle_result', None))

        if not self._seeded:
            # First frame for this game: everything already complete is
            # history — reveal instantly, never animate.
            for idx in range(3):
                if (idx < len(player_slots) and idx < len(opponent_slots)
                        and player_slots[idx] is not None
                        and opponent_slots[idx] is not None):
                    self._revealed.add(idx)
            self._seeded = True
            self._display_version += 1
            return

        if finished:
            # Result already on screen (withdraw / auto-resolution):
            # drop any withheld display so the ledger matches the result.
            if self.has_pending():
                self.fast_forward()
            for idx in range(3):
                if (idx < len(player_slots) and idx < len(opponent_slots)
                        and player_slots[idx] is not None
                        and opponent_slots[idx] is not None
                        and idx not in self._revealed):
                    self._reveal_instantly(idx)
            return

        # Record rounds observed incomplete: only these may animate later.
        # This is the replay guard — a freshly-mounted screen whose first
        # battle-state poll arrives *after* seeding would otherwise treat
        # historical rounds as "new" and replay their reveals.
        for idx in range(3):
            if idx in self._revealed or idx in self._eligible:
                continue
            if idx >= len(player_slots) or idx >= len(opponent_slots):
                continue
            you = player_slots[idx]
            opp = opponent_slots[idx]
            if you is not None and opp is None:
                self._eligible[idx] = {'opp_seen': False}
            elif opp is not None and you is None:
                # Opponent committed first (their identity is already
                # server-revealed) — never "un-reveal" it; skip the flip.
                self._eligible[idx] = {'opp_seen': True}
            elif you is None and opp is None:
                try:
                    current_round = int(getattr(game, 'battle_round', 0) or 0)
                except (TypeError, ValueError):
                    current_round = -1
                if (idx == current_round
                        and getattr(game, 'battle_turn_player_id', None) is not None):
                    self._eligible[idx] = {'opp_seen': False}

        # Detect newly-completed rounds → enqueue in round order.
        for idx in range(3):
            if idx in self._revealed:
                continue
            if idx >= len(player_slots) or idx >= len(opponent_slots):
                continue
            you = player_slots[idx]
            opp = opponent_slots[idx]
            if you is None or opp is None:
                continue
            if self._active is not None and self._active.get('round') == idx:
                continue
            if any(entry.get('round') == idx for entry in self._queue):
                continue
            eligibility = self._eligible.get(idx)
            if eligibility is None:
                # Never observed incomplete in this session → history.
                self._reveal_instantly(idx)
                continue
            self._enqueue(idx, you, opp,
                          opp_seen=bool(eligibility.get('opp_seen')))

        self._advance()

    # -------------------------------------------------------------- internal
    def _enqueue(self, round_idx: int, you: Dict[str, Any], opp: Dict[str, Any],
                 *, opp_seen: bool = False):
        if _is_skip(you) or _is_skip(opp):
            durations = dict(SKIP_STAGE_DURATIONS_MS)
        elif round_idx == FINAL_ROUND_IDX:
            durations = dict(FINAL_STAGE_DURATIONS_MS)
        else:
            durations = dict(STAGE_DURATIONS_MS)
        if opp_seen:
            # Identity already visible — no tension beat / flip, straight
            # to the tally so the previously-shown tactic never blinks out.
            durations[STAGE_HOLD] = 0
            durations[STAGE_FLIP] = 0
        self._queue.append({
            'round': round_idx,
            'you_key': _move_identity(you),
            'opp_key': _move_identity(opp),
            'durations': durations,
            'opp_seen': bool(opp_seen),
        })
        self._queue.sort(key=lambda entry: entry.get('round', 0))
        self._display_version += 1

    def _start_next(self):
        if self._active is not None or not self._queue:
            return
        entry = self._queue.pop(0)
        entry.update({
            'started_at': self._now(),
            'stage': STAGE_HOLD,
            'progress': 0.0,
            'opp_visible': bool(entry.get('opp_seen')),
            'diff_factor': 0.0,
            'events_fired': set(['flip']) if entry.get('opp_seen') else set(),
        })
        self._active = entry
        # hold_ms lets the handler stay silent for opp-seen entries
        # (HOLD zeroed) and skip-beats without knowing stage tables.
        durations = entry.get('durations') or {}
        self._emit(entry['round'], 'start', {
            'hold_ms': int(durations.get(STAGE_HOLD) or 0),
        })

    def _advance(self):
        if self._active is None:
            self._start_next()
            if self._active is None:
                return
        active = self._active
        now = self._now()
        elapsed = max(0, now - int(active.get('started_at') or now))
        durations = active.get('durations') or STAGE_DURATIONS_MS

        stage = None
        stage_start = 0
        for candidate in _STAGE_ORDER:
            dur = max(0, int(durations.get(candidate) or 0))
            if dur <= 0:
                continue
            if elapsed < stage_start + dur:
                stage = candidate
                active['progress'] = (elapsed - stage_start) / dur
                break
            stage_start += dur
        if stage is None:
            self._finish_active(emit_impact=True)
            self._start_next()
            return

        active['stage'] = stage
        fired = active['events_fired']

        # FLIP midpoint: opponent identity becomes visible.
        if stage == STAGE_FLIP and active['progress'] >= 0.5 and not active['opp_visible']:
            active['opp_visible'] = True
            self._display_version += 1
            if 'flip' not in fired:
                fired.add('flip')
                self._emit(active['round'], 'flip', {})
        elif stage in (STAGE_TALLY, STAGE_IMPACT) and not active['opp_visible']:
            active['opp_visible'] = True
            self._display_version += 1
            if 'flip' not in fired:
                fired.add('flip')
                self._emit(active['round'], 'flip', {})

        # TALLY: eased 0→1 factor for the diff count-up.
        if stage == STAGE_TALLY:
            t = active['progress']
            active['diff_factor'] = 1.0 - (1.0 - t) * (1.0 - t)
        elif stage == STAGE_IMPACT:
            active['diff_factor'] = 1.0
            if 'impact' not in fired:
                fired.add('impact')
                self._emit(active['round'], 'impact', {})

    def _finish_active(self, *, emit_impact: bool):
        active = self._active
        if active is None:
            return
        fired = active.get('events_fired') or set()
        if 'flip' not in fired:
            self._emit(active['round'], 'flip', {})
        if emit_impact and 'impact' not in fired:
            self._emit(active['round'], 'impact', {'fast_forwarded': True})
        round_idx = active['round']
        self._active = None
        self._revealed.add(round_idx)
        self._display_version += 1
        self._emit(round_idx, 'done', {})

    def _reveal_instantly(self, round_idx: int):
        self._revealed.add(round_idx)
        self._display_version += 1
