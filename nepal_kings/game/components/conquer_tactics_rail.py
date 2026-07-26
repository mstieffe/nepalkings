# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tactics-hand rail for the unified conquer battle screen.

Single-column persistent left-side rail showing the player's *tactics
hand* (`BattleMove` rows with `played_round is None`).  Replaces the old
``BattleShopScreen`` UI for tactics-hand conquer games.

Sections (top → bottom, all rects come from
:func:`game.components.conquer_layout.compute_conquer_layout`):

* **top strip** — gamble status (desktop) and the *family filter strip*: one
  chip per tactic family plus an ``All`` chip.  The filter replaces the old
  per-family accordion: a chip tap swaps the whole list instead of growing
  it, so rows never move underneath the player's finger.
* **hand list** — scrollable column of one-row cells, one per move.  Touch
  builds grab-scroll the list (drag anywhere); desktop keeps wheel + arrows.
* **selected detail** — name, suit/rank chip, source, power (desktop only;
  mobile keeps selection feedback on the row itself).
* **action tray** — Play / Gamble / Combine / Dismantle / Skip.  Its height
  is reserved up front so selecting a tactic never shrinks the hand list.

Click handling is lightweight: the rail captures click events via
``handle_event`` and exposes the latest pending action through
``consume_pending_action``.  ``ConquerGameScreen`` is responsible for
calling the appropriate API and refreshing.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pygame

from config import settings
from game.components.battle_moves.battle_move_icon_renderer import draw_battle_move_icon
from game.components.conquer_layout import compute_conquer_layout
from game.components.suit_text import fit_suit_text, render_suit_text


# Visual constants
_BG_RGBA = (38, 29, 22, 218)
_BORDER_RGBA = (122, 92, 56)
_SELECTED_RGBA = (92, 218, 202)
_SELECTED_BG_RGBA = (22, 54, 52, 242)
_TEXT_PRIMARY = (238, 218, 170)
_TEXT_SECONDARY = (170, 152, 110)
_TEXT_MUTED = (132, 116, 86)
_DISABLED_RGBA = (78, 64, 50)


# Action keys returned via consume_pending_action
ACTION_PLAY = 'play'
ACTION_GAMBLE = 'gamble'
ACTION_COMBINE = 'combine'
ACTION_DISMANTLE = 'dismantle'
ACTION_SKIP = 'skip'

_PRIMARY_ACTION_KEYS = (ACTION_PLAY, ACTION_SKIP)


class ConquerTacticsRail:
    """Stateful left-side tactics rail.

    Parameters
    ----------
    parent : object
        ``ConquerGameScreen``. Used for icon-asset access and the
        ``state.game`` data source. The parent must expose
        ``_conquer_battle_move_icon_assets(size)`` returning the
        ``(glow_cache, icon_cache, frame_cache, suit_icon_cache, font)``
        tuple.
    """

    def __init__(self, parent):
        self._parent = parent
        self.window: pygame.Surface = parent.window
        # Scroll position is stored in pixels so touch drags can follow the
        # finger; ``_scroll`` remains an item index for every other caller.
        self._scroll_px = 0
        self._selected_id: Optional[int] = None
        # Pending second selection for "combine" two-step flow.
        self._combine_partner_id: Optional[int] = None
        self._combine_pending: bool = False
        # Layout caches.
        self._layout = None
        self._cached_screen_size = None
        # Rect caches updated on draw().
        self._cell_rects: List[pygame.Rect] = []
        self._cell_move_ids: List[int] = []
        self._hovered_id: Optional[int] = None
        self._action_button_rects: Dict[str, pygame.Rect] = {}
        self._scroll_up_rect: Optional[pygame.Rect] = None
        self._scroll_down_rect: Optional[pygame.Rect] = None
        # Pending action consumed by the parent each frame.
        self._pending_action: Optional[Dict[str, Any]] = None
        # Monotonic user-selection version. The parent snapshots this when a
        # server mutation begins so a response never erases a choice the
        # player made while that request was in flight.
        self._selection_revision = 0
        # One server mutation may be pending while the rail remains locally
        # interactive. Shape: {'action': str, 'move_id': int|None} or None.
        self._server_action_pending: Optional[Dict[str, Any]] = None
        # Sticky result banner — shown at the top of the rail until next
        # action or until ttl expires. (#8a)
        self._result_banner: Optional[Dict[str, Any]] = None
        # Recently-added move IDs (e.g. from gamble) that should glow.
        # Maps move_id → expires_at (ms). (#8c)
        self._new_move_glow_until: Dict[int, int] = {}
        # Optional anchor binding a glow to the active timeline step kind.
        # When set, the glow is also expired the moment the active step
        # changes — so card-change feedback persists *exactly* while the
        # corresponding timeline step is active (round 10 #4).
        self._new_move_step_kind: Dict[int, str] = {}
        # Snapshot of move IDs from the previous frame so we can detect
        # newly-added moves (used to start the new-move glow on gamble).
        self._prev_move_ids: set = set()
        # Snapshot of full move-data from the previous frame, keyed by id.
        # Used to render ghost cells for spell-removed moves briefly. (#round4)
        self._prev_moves_by_id: Dict[int, Dict[str, Any]] = {}
        # Recently spell-removed move IDs → (move_data_snapshot, expires_at).
        self._removed_ghosts: Dict[int, Dict[str, Any]] = {}
        # Coin-flip animation state for gambled tactic. (#8c)
        # ``{'move_id': int, 'started_at': ms, 'duration': ms}`` or None.
        self._gamble_anim: Optional[Dict[str, Any]] = None
        # Two-step gamble confirm (devil's-bargain ritual): first click
        # arms the button, second click within ``GAMBLE_CONFIRM_MS``
        # fires. ``{'move_id': int, 'until_ms': int}`` or None.
        self._gamble_armed: Optional[Dict[str, Any]] = None
        # Drag-and-drop combine state. (#8b)
        self._drag_origin_id: Optional[int] = None
        self._drag_pos: Optional[tuple] = None
        self._drag_active: bool = False
        # Family filter (round 14). ``None`` shows the whole hand; otherwise
        # only the named family group renders. Replaces the per-group
        # accordion: filtering swaps the list instead of resizing it, so a
        # tap never shifts the row under the player's finger.
        self._active_family: Optional[str] = None
        self._filter_chip_rects: List[tuple] = []
        # Touch grab-scroll. A press inside the list still selects
        # immediately (responsive), but promoting the gesture to a drag
        # restores the previous selection and scrolls instead.
        self._list_press: Optional[Dict[str, Any]] = None
        self._list_drag_active: bool = False
        # Per-cell metadata captured during draw.
        self._cell_kinds: List[str] = []
        self._cell_groups: List[Optional[str]] = []
        # Resolved zone rects for the current frame. The filter strip and the
        # action tray are sized up front (never from the current selection),
        # so the hand list keeps a constant height for the whole battle.
        self._dyn_top_strip_rect: Optional[pygame.Rect] = None
        self._dyn_filter_strip_rect: Optional[pygame.Rect] = None
        self._dyn_hand_list_rect: Optional[pygame.Rect] = None
        self._dyn_action_tray_rect: Optional[pygame.Rect] = None
        # Overlay rect of the sticky banner, so taps can dismiss it.
        self._banner_rect: Optional[pygame.Rect] = None
        self._cached_render_key = None
        self._cached_render_surface: Optional[pygame.Surface] = None

    # ------------------------------------------------------------------ scroll
    def _cell_height(self) -> int:
        try:
            return max(1, int(self._ensure_layout().tactics_rail.cell_height))
        except Exception:
            return 1

    @property
    def _scroll(self) -> int:
        """First visible item index (derived from the pixel offset)."""
        return int(self._scroll_px // self._cell_height())

    @_scroll.setter
    def _scroll(self, value) -> None:
        try:
            index = max(0, int(value))
        except (TypeError, ValueError):
            index = 0
        self._scroll_px = index * self._cell_height()

    # ------------------------------------------------------------------ data
    def _moves(self) -> List[Dict[str, Any]]:
        try:
                getter = getattr(self._parent, '_current_conquer_tactics', None)
                if getter is None:
                    getter = getattr(self._parent, '_current_conquer_battle_moves', None)
                return list(getter() or []) if getter is not None else []
        except Exception:
            return []

    def _hand_moves(self) -> List[Dict[str, Any]]:
        return [
            m for m in self._moves()
            if m.get('played_round') is None
            and (
                m.get('status', 'available') == 'available'
                or bool(m.get('_render_ghost'))
            )
        ]

    @staticmethod
    def _is_ghost_move(move: Optional[Dict[str, Any]]) -> bool:
        return bool(move and move.get('_render_ghost'))

    def _selected_move(self) -> Optional[Dict[str, Any]]:
        if self._selected_id is None:
            return None
        for m in self._hand_moves():
            if m.get('id') == self._selected_id:
                return m
        # Selection no longer in hand → drop it.
        self._selected_id = None
        return None

    def _combine_partner_move(self) -> Optional[Dict[str, Any]]:
        if self._combine_partner_id is None:
            return None
        for m in self._hand_moves():
            if m.get('id') == self._combine_partner_id:
                return m
        return None

    def _is_my_battle_turn(self) -> bool:
        game = getattr(self._parent.state, 'game', None)
        if not game:
            return False
        turn_player_id = getattr(game, 'battle_turn_player_id', None)
        if turn_player_id is None:
            return False
        return str(turn_player_id) == str(getattr(game, 'player_id', None))

    GAMBLE_PER_BATTLE_LIMIT = 3
    GAMBLE_CONFIRM_MS = 2600

    @staticmethod
    def _gamble_counts_state(game) -> tuple:
        """Return ``(used_count, used_rounds)`` from ``battle_gamble_counts``."""
        counts = getattr(game, 'battle_gamble_counts', None) or {}
        my_id = getattr(game, 'player_id', None)
        state = counts.get(str(my_id), 0)
        used_count = 0
        used_rounds: list = []
        if isinstance(state, dict):
            try:
                used_count = int(state.get('count', 0) or 0)
            except (TypeError, ValueError):
                used_count = 0
            for r in state.get('rounds', []) or []:
                try:
                    used_rounds.append(int(r))
                except (TypeError, ValueError):
                    continue
        else:
            try:
                used_count = int(state or 0)
            except (TypeError, ValueError):
                used_count = 0
        return used_count, used_rounds

    def _gamble_armed_for(self, move_id) -> bool:
        armed = self._gamble_armed
        if not armed:
            return False
        if pygame.time.get_ticks() >= int(armed.get('until_ms') or 0):
            self._gamble_armed = None
            return False
        try:
            return int(armed.get('move_id') or -1) == int(move_id or -2)
        except (TypeError, ValueError):
            return False

    _SPEC_SUIT_CHARS = {'Hearts': '♥', 'Diamonds': '♦',
                        'Clubs': '♣', 'Spades': '♠'}

    @classmethod
    def _gamble_spec_label(cls, spec) -> str:
        """Short 'K♥ Call King' label for a previewed replacement tactic."""
        if not isinstance(spec, dict):
            return '?'
        suit_char = cls._SPEC_SUIT_CHARS.get(spec.get('suit'), '?')
        name = spec.get('family_name') or 'Dagger'
        return f"{spec.get('rank')}{suit_char} {name}"

    def _gamble_preview_specs(self, move_id=None):
        """Pinned All Seeing Eye forecast for the CURRENT round, or None.

        The forecast is per round, not per tactic — ``move_id`` is ignored
        (kept for call-site compatibility): gambling any tactic yields the
        same two cards.
        """
        game = getattr(self._parent.state, 'game', None)
        previews = getattr(game, 'battle_gamble_previews', None) or {}
        entry = previews.get(str(getattr(game, 'player_id', None)))
        if not isinstance(entry, dict):
            return None
        try:
            if int(entry.get('round', -1)) != int(getattr(game, 'battle_round', 0) or 0):
                return None
        except (TypeError, ValueError):
            return None
        specs = entry.get('specs') or []
        return specs if len(specs) == 2 else None

    def _gamble_block_reason(self) -> str:
        """Return human-readable reason gambling is blocked, '' if allowed.

        Mirrors server-side gating in
        ``server/routes/battle_shop.py::battle_shop_gamble`` so the
        rail's Gamble button shows the right tooltip without a round-trip.
        """
        game = getattr(self._parent.state, 'game', None)
        if game is None:
            return 'No active game'
        # Battle must be confirmed (i.e. an active battle round).
        if not getattr(game, 'battle_confirmed', False):
            return 'Gamble only during active battle rounds'
        # Must be your turn.
        my_id = getattr(game, 'player_id', None)
        turn_id = getattr(game, 'battle_turn_player_id', None)
        if turn_id is None or turn_id != my_id:
            return 'Not your battle turn'
        # Per-round + per-battle gamble caps.
        counts = getattr(game, 'battle_gamble_counts', None) or {}
        pid_str = str(my_id)
        state = counts.get(pid_str, 0)
        used_count = 0
        used_rounds: list = []
        if isinstance(state, dict):
            try:
                used_count = int(state.get('count', 0) or 0)
            except (TypeError, ValueError):
                used_count = 0
            for r in state.get('rounds', []) or []:
                try:
                    used_rounds.append(int(r))
                except (TypeError, ValueError):
                    continue
        else:
            try:
                used_count = int(state or 0)
            except (TypeError, ValueError):
                used_count = 0
        try:
            current_round = int(getattr(game, 'battle_round', 0) or 0)
        except (TypeError, ValueError):
            current_round = 0
        if current_round in used_rounds:
            return 'Already gambled this round'
        if used_count >= self.GAMBLE_PER_BATTLE_LIMIT:
            return f'Gamble limit reached ({used_count}/{self.GAMBLE_PER_BATTLE_LIMIT})'
        return ''

    def _power(self, move: Dict[str, Any]) -> int:
        cache_key = (
            move.get('id'),
            move.get('family_name'),
            move.get('value'),
            move.get('suit'),
            move.get('suit_b'),
            move.get('rank'),
            move.get('status'),
            move.get('played_round'),
            move.get('call_figure_id'),
        )
        cache = getattr(self, '_power_cache', None)
        if isinstance(cache, dict) and cache_key in cache:
            return cache[cache_key]
        display_power = getattr(self._parent, '_conquer_tactic_display_power', None)
        if callable(display_power):
            try:
                value = int(display_power(move) or 0)
                if isinstance(cache, dict):
                    cache[cache_key] = value
                return value
            except Exception:
                pass
        if move.get('family_name') == 'Block':
            value = 0
        else:
            value = int(move.get('value') or 0)
        if isinstance(cache, dict):
            cache[cache_key] = value
        return value

    @staticmethod
    def _fit_text(text: str, font, max_width: int) -> str:
        text = text or ''
        if max_width <= 0:
            return ''
        if font.size(text)[0] <= max_width:
            return text
        clipped = text
        while clipped and font.size(clipped + '...')[0] > max_width:
            clipped = clipped[:-1]
        return clipped + '...' if clipped else '...'

    @staticmethod
    def _wrap_text(text: str, font, max_width: int) -> List[str]:
        """Greedy word-wrap, falling back to char-wrap for over-wide tokens."""
        text = (text or '').strip()
        if not text or max_width <= 0:
            return [text] if text else ['']
        words = text.split()
        lines: List[str] = []
        current = ''
        for word in words:
            candidate = (current + ' ' + word).strip() if current else word
            if font.size(candidate)[0] <= max_width:
                current = candidate
                continue
            if current:
                lines.append(current)
                current = ''
            # Word itself too long → char-wrap.
            if font.size(word)[0] > max_width:
                buf = ''
                for ch in word:
                    nxt = buf + ch
                    if font.size(nxt)[0] > max_width and buf:
                        lines.append(buf)
                        buf = ch
                    else:
                        buf = nxt
                current = buf
            else:
                current = word
        if current:
            lines.append(current)
        return lines or ['']

    @staticmethod
    def _can_combine(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
        """Two single Daggers of the same colour can combine into a Double Dagger."""
        if a.get('id') == b.get('id'):
            return False
        if a.get('family_name') != 'Dagger' or b.get('family_name') != 'Dagger':
            return False
        if a.get('card_id_b') or b.get('card_id_b'):
            return False
        # Same colour group: hearts/diamonds (red) vs spades/clubs (black)
        red = {'Hearts', 'Diamonds'}
        black = {'Spades', 'Clubs'}
        sa, sb = a.get('suit'), b.get('suit')
        return (sa in red and sb in red) or (sa in black and sb in black)

    def _eligible_combine_partners(
            self, move: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Available same-colour single Daggers that can join ``move``."""
        move = move or self._selected_move()
        if move is None or not self._is_single_dagger(move):
            return []
        partners: List[Dict[str, Any]] = []
        for candidate in self._hand_moves():
            if self._is_ghost_move(candidate):
                continue
            if self._can_combine(move, candidate):
                partners.append(candidate)
        return partners

    def _best_combine_partner(
            self, move: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Strongest currently available partner for one-tap Combine."""
        partners = self._eligible_combine_partners(move)
        if not partners:
            return None

        def key(candidate: Dict[str, Any]) -> tuple:
            try:
                move_id = int(candidate.get('id') or 0)
            except (TypeError, ValueError):
                move_id = 0
            return (self._power(candidate), move_id)

        return max(partners, key=key)

    @staticmethod
    def _is_double_dagger(move: Dict[str, Any]) -> bool:
        return move.get('family_name') in ('Dagger', 'Double Dagger') and bool(move.get('card_id_b'))

    @staticmethod
    def _is_single_dagger(move: Dict[str, Any]) -> bool:
        return move.get('family_name') == 'Dagger' and not bool(move.get('card_id_b'))

    # ------------------------------------------------------------------ layout
    def _ensure_layout(self):
        size = (settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT)
        game = getattr(self._parent.state, 'game', None)
        effective_mode = getattr(self._parent, '_conquer_effective_layout_mode', None)
        if callable(effective_mode):
            mode = effective_mode()
        elif game is not None:
            if getattr(game, 'last_battle_result', None):
                mode = 'result'
            elif (getattr(game, 'battle_turn_player_id', None) is not None
                  or getattr(game, 'battle_round', 0) in (1, 2, 3)):
                mode = 'battle'
            else:
                mode = 'pre_battle'
        else:
            mode = 'pre_battle'
        if (self._layout is None
                or size != self._cached_screen_size
                or self._layout.mode != mode):
            self._layout = compute_conquer_layout(*size, mode=mode)
            self._cached_screen_size = size
        return self._layout

    def rect(self) -> pygame.Rect:
        return pygame.Rect(*self._ensure_layout().tactics_rail.rect)

    @staticmethod
    def _touch_rect(rect: Optional[pygame.Rect],
                    min_w: Optional[int] = None,
                    min_h: Optional[int] = None) -> Optional[pygame.Rect]:
        if rect is None or settings.TOUCH_TARGET_MIN <= 0:
            return rect
        min_w = min_w or settings.TOUCH_TARGET_MIN
        min_h = min_h or settings.TOUCH_TARGET_MIN
        grow_w = max(0, min_w - rect.width)
        grow_h = max(0, min_h - rect.height)
        return rect.inflate(grow_w, grow_h)

    @classmethod
    def _touch_collide(cls, rect: Optional[pygame.Rect], pos,
                       min_w: Optional[int] = None,
                       min_h: Optional[int] = None) -> bool:
        hit = cls._touch_rect(rect, min_w=min_w, min_h=min_h)
        return bool(hit and hit.collidepoint(pos))

    # ------------------------------------------------------------------ public
    def consume_pending_action(self) -> Optional[Dict[str, Any]]:
        """Return and clear the latest queued action (one-shot)."""
        action = self._pending_action
        self._pending_action = None
        return action

    def reset_selection(self, *, record_revision: bool = False):
        changed = self._selected_id is not None
        self._selected_id = None
        self._hovered_id = None
        self._combine_partner_id = None
        self._combine_pending = False
        self._pending_action = None
        self._gamble_armed = None
        if changed and record_revision:
            self._selection_revision += 1

    def selection_revision(self) -> int:
        return int(self._selection_revision)

    def begin_server_action(self, action: str, move_id=None) -> None:
        """Mark one mutation pending without locking local rail navigation."""
        try:
            move_id = int(move_id) if move_id is not None else None
        except (TypeError, ValueError):
            move_id = None
        self._server_action_pending = {
            'action': str(action or 'action'),
            'move_id': move_id,
        }

    def clear_server_action(self) -> None:
        self._server_action_pending = None

    def _scroll_move_into_view(self, move_id: int) -> None:
        items = self._visible_hand_items()
        target_index = None
        for index, item in enumerate(items):
            try:
                if int((item.get('move') or {}).get('id') or 0) == int(move_id):
                    target_index = index
                    break
            except (TypeError, ValueError):
                continue
        if target_index is None:
            return
        visible = self._visible_cell_capacity()
        if target_index < self._scroll:
            self._scroll = target_index
        elif target_index >= self._scroll + visible:
            self._scroll = max(0, target_index - visible + 1)
        self._clamp_scroll()

    def focus_move(self, move_id, *, reveal_group: bool = False) -> bool:
        """Programmatically select and reveal a still-available tactic."""
        try:
            wanted = int(move_id)
        except (TypeError, ValueError):
            return False
        target = next(
            (move for move in self._hand_moves()
             if int(move.get('id') or 0) == wanted),
            None,
        )
        if target is None:
            return False
        if reveal_group:
            # A filtered rail must not hide the tactic it is focusing.
            group = self._family_group(target)
            if self._active_family is not None and self._active_family != group:
                self._active_family = group
                self._scroll_px = 0
        self._selected_id = wanted
        self._combine_partner_id = None
        self._combine_pending = False
        self._gamble_armed = None
        self._scroll_move_into_view(wanted)
        return True

    def complete_server_action(self, *, submit_revision: int,
                               preferred_move_ids=None,
                               select_strongest_fallback: bool = False) -> None:
        """Finish a mutation without erasing selection made during its wait."""
        self.clear_server_action()
        self._hovered_id = None
        self._combine_partner_id = None
        self._combine_pending = False
        self._pending_action = None
        self._gamble_armed = None

        user_reselected = self._selection_revision != int(submit_revision)
        current = self._selected_move()
        if user_reselected and current is not None:
            self._scroll_move_into_view(int(current.get('id') or 0))
            return

        for move_id in preferred_move_ids or []:
            if self.focus_move(move_id, reveal_group=True):
                return
        if select_strongest_fallback:
            moves = [m for m in self._hand_moves() if not self._is_ghost_move(m)]
            if moves:
                strongest = max(moves, key=lambda move: self._power(move))
                if self.focus_move(strongest.get('id'), reveal_group=True):
                    return
        self._selected_id = None

    def preview_move(self) -> Optional[Dict[str, Any]]:
        if not self._is_my_battle_turn() or self._hovered_id is None:
            return None
        for move in self._hand_moves():
            if move.get('id') == self._hovered_id:
                return move
        return None

    def move_cell_rect(self, move_id: int) -> Optional[pygame.Rect]:
        for rect, mid in zip(self._cell_rects, self._cell_move_ids):
            if mid == move_id:
                return pygame.Rect(rect)
        return None

    def reset_after_action(self):
        """Clear ephemeral state after a server action completed."""
        self.clear_server_action()
        self.reset_selection()

    NEW_MOVE_GLOW_MS = 3500
    RESULT_BANNER_DEFAULT_MS = 4500

    def set_result_banner(self, text: str,
                          color=(238, 218, 170),
                          ttl_ms: Optional[int] = None) -> None:
        """Show a sticky banner at the top of the rail (#8a).

        ``ttl_ms = None`` keeps the banner until the next call. Pass an
        explicit value to auto-expire it.
        """
        self._result_banner = {
            'text': str(text or ''),
            'color': color,
            'expires_at': (pygame.time.get_ticks() + int(ttl_ms))
                if ttl_ms else None,
        }

    def clear_result_banner(self) -> None:
        self._result_banner = None

    def mark_new_moves(self, move_ids, *, step_kind: Optional[str] = None) -> None:
        """Glow these move IDs for ``NEW_MOVE_GLOW_MS`` (#8c).

        ``step_kind`` optionally anchors the glow to the active timeline
        step; the glow is expired as soon as the active step changes.
        """
        if not move_ids:
            return
        expires = pygame.time.get_ticks() + self.NEW_MOVE_GLOW_MS
        for mid in move_ids:
            try:
                key = int(mid)
            except Exception:
                continue
            self._new_move_glow_until[key] = expires
            if step_kind:
                self._new_move_step_kind[key] = step_kind

    REMOVED_GHOST_MS = 4000

    def _detect_new_moves(self) -> None:
        """Auto-glow any move that wasn't visible last frame (#8c).

        Also captures genuinely spell-removed moves as ghost rows so the
        player can see what disappeared for ``REMOVED_GHOST_MS`` after the
        change. A tactic that merely left the hand because it was played,
        gambled, or combined remains in the complete tactic snapshot and must
        not be mislabeled as "removed by spell".
        """
        try:
            all_moves = self._moves()
            all_moves_by_id = {
                int(m.get('id') or 0): m for m in all_moves
                if isinstance(m, dict)
            }
            hand = [
                m for m in all_moves
                if m.get('played_round') is None
                and (
                    m.get('status', 'available') == 'available'
                    or bool(m.get('_render_ghost'))
                )
            ]
            current_by_id = {int(m.get('id') or 0): m for m in hand}
            current = set(current_by_id.keys())
        except Exception:
            all_moves_by_id = {}
            current_by_id = {}
            current = set()
        # Skip the very first frame (empty prev set would glow everything).
        if self._prev_move_ids and current is not None:
            new_ids = current - self._prev_move_ids
            if new_ids:
                step_kind = None
                getter = getattr(self._parent, 'active_conquer_timeline_step', None)
                if callable(getter):
                    try:
                        active_step = getter()
                        if active_step is not None:
                            step_kind = getattr(active_step, 'kind', None)
                    except Exception:
                        step_kind = None
                self.mark_new_moves(new_ids, step_kind=step_kind)
            removed_ids = self._prev_move_ids - current
            if removed_ids:
                expires = pygame.time.get_ticks() + self.REMOVED_GHOST_MS
                for mid in removed_ids:
                    # Played/discarded tactics disappear from ``_hand_moves``
                    # but remain in ``_moves`` with their new authoritative
                    # state. Only an item absent from the full visible list is
                    # a removal transition that warrants the spell ghost.
                    if mid in all_moves_by_id:
                        self._removed_ghosts.pop(mid, None)
                        continue
                    snapshot = self._prev_moves_by_id.get(mid)
                    if snapshot is None:
                        continue
                    self._removed_ghosts[mid] = {
                        'move': snapshot,
                        'expires_at': expires,
                    }
        self._prev_move_ids = current
        self._prev_moves_by_id = dict(current_by_id)
        # Drop stale glow / ghost entries.
        now = pygame.time.get_ticks()
        # Expire step-anchored glows the moment the active step changes.
        if self._new_move_step_kind:
            active_kind = None
            getter = getattr(self._parent, 'active_conquer_timeline_step', None)
            if callable(getter):
                try:
                    active_step = getter()
                    if active_step is not None:
                        active_kind = getattr(active_step, 'kind', None)
                except Exception:
                    active_kind = None
            for mid, kind in list(self._new_move_step_kind.items()):
                if kind != active_kind:
                    self._new_move_glow_until.pop(mid, None)
                    self._new_move_step_kind.pop(mid, None)
                else:
                    # Keep the glow alive while the bound step is active
                    # so the highlight pulses for the full step duration.
                    self._new_move_glow_until[mid] = pygame.time.get_ticks() + self.NEW_MOVE_GLOW_MS
        self._new_move_glow_until = {
            mid: exp for mid, exp in self._new_move_glow_until.items()
            if exp > now
        }
        for mid in list(self._new_move_step_kind.keys()):
            if mid not in self._new_move_glow_until:
                self._new_move_step_kind.pop(mid, None)
        self._removed_ghosts = {
            mid: data for mid, data in self._removed_ghosts.items()
            if data.get('expires_at', 0) > now
        }

    def _strongest_move_id(self) -> Optional[int]:
        """ID of the highest-power move in the hand (#8d badge)."""
        try:
            moves = self._hand_moves()
        except Exception:
            return None
        if not moves:
            return None
        try:
            best = max(moves, key=lambda m: self._power(m))
            return int(best.get('id') or 0) or None
        except Exception:
            return None

    # ------------------------------------------------------------------ events
    DRAG_START_PX = 6
    FAMILY_GROUP_ORDER = ('Dagger', 'Buff', 'Block', 'Call')

    def _family_group(self, move: Dict[str, Any]) -> str:
        """Map a move to its display family group (#8a).

        The three server call families (``Call Villager`` / ``Call Military``
        / ``Call King``) share one group: they are one decision for the
        player ("summon a figure"), and keeping them apart would push the
        filter strip past the chips a narrow rail can hold.
        """
        fam = (move.get('family_name') or '').strip()
        if fam in ('Dagger', 'Double Dagger'):
            return 'Dagger'
        if fam == 'Buff':
            return 'Buff'
        if fam == 'Block':
            return 'Block'
        if fam == 'Call' or fam.startswith('Call '):
            return 'Call'
        return fam or 'Other'

    def _hand_moves_grouped(self) -> List[Dict[str, Any]]:
        """Hand moves sorted by family group, then by descending power."""
        groups = {g: [] for g in self.FAMILY_GROUP_ORDER}
        misc: List[Dict[str, Any]] = []
        for m in self._hand_moves():
            g = self._family_group(m)
            if g in groups:
                groups[g].append(m)
            else:
                misc.append(m)
        out: List[Dict[str, Any]] = []
        for g in self.FAMILY_GROUP_ORDER:
            out.extend(sorted(groups[g], key=lambda x: -self._power(x)))
        out.extend(misc)
        return out

    def _hand_groups_in_order(self) -> List[tuple]:
        """Return list of ``(group_label, [moves sorted desc by power])``
        in display order — known families first, misc last."""
        groups = {g: [] for g in self.FAMILY_GROUP_ORDER}
        misc_by_group: Dict[str, List[Dict[str, Any]]] = {}
        for m in self._hand_moves():
            g = self._family_group(m)
            if g in groups:
                groups[g].append(m)
            else:
                misc_by_group.setdefault(g, []).append(m)
        ordered: List[tuple] = []
        for g in self.FAMILY_GROUP_ORDER:
            if groups[g]:
                ordered.append((g, sorted(groups[g], key=lambda x: -self._power(x))))
        for g, lst in misc_by_group.items():
            ordered.append((g, sorted(lst, key=lambda x: -self._power(x))))
        return ordered

    FILTER_ALL = 'all'

    def _family_filter_chips(self) -> List[Dict[str, Any]]:
        """Chip descriptors for the filter strip, in display order.

        Returns nothing for a single-family hand: the strip would only repeat
        what the list already shows, and the rail spends the row on tactics
        instead.  :meth:`_draw_filter_strip` may drop the leading ``All`` chip
        on a rail too narrow for all of them.
        """
        groups = self._hand_groups_in_order()
        if len(groups) < 2:
            # One family (or none) — the strip would only repeat the list.
            return []
        chips: List[Dict[str, Any]] = [{
            'key': self.FILTER_ALL,
            'label': 'All',
            'count': sum(len(members) for _label, members in groups),
            'icon_families': (),
        }]
        for label, members in groups:
            chips.append({
                'key': label,
                'label': label,
                'count': len(members),
                'icon_families': self._group_icon_families(members),
            })
        return chips

    # Fixed order for a group's composite chip icon, so the artwork does not
    # reshuffle when the hand's strongest call changes.
    ICON_FAMILY_ORDER = ('Dagger', 'Double Dagger', 'Block',
                         'Call Villager', 'Call Military', 'Call King')

    @classmethod
    def _group_icon_families(cls, members: List[Dict[str, Any]]) -> tuple:
        """Distinct family names in a group, in stable display order."""
        seen = []
        for move in members:
            name = (move.get('family_name') or '').strip()
            if name and name not in seen:
                seen.append(name)

        def order(name: str) -> tuple:
            try:
                return (cls.ICON_FAMILY_ORDER.index(name), name)
            except ValueError:
                return (len(cls.ICON_FAMILY_ORDER), name)

        return tuple(sorted(seen, key=order))

    def _sync_active_family(self) -> None:
        """Drop a filter whose family has been emptied (played out)."""
        if self._active_family is None:
            return
        if not any(label == self._active_family
                   for label, _members in self._hand_groups_in_order()):
            self._active_family = None

    def _set_active_family(self, key: Optional[str]) -> None:
        """Apply a filter chip tap.

        Selection is dropped whenever it would leave the visible list: an
        invisible selection with a live action tray is the worst of both
        worlds — the tray acts on a tactic the player can no longer see.
        """
        family = None if key in (None, self.FILTER_ALL) else str(key)
        if family == self._active_family:
            # Tapping the active chip returns to the full hand.
            family = None
        self._active_family = family
        self._scroll_px = 0
        selected = self._selected_move()
        if selected is not None and family is not None:
            if self._family_group(selected) != family:
                self._selected_id = None
                self._selection_revision += 1
        self._combine_pending = False
        self._combine_partner_id = None
        self._gamble_armed = None
        if self._selected_id is not None:
            self._scroll_move_into_view(self._selected_id)

    def _visible_hand_items(self) -> List[Dict[str, Any]]:
        """Rows to render: the active family, or the whole hand.

        Each item is ``{'kind': 'move', 'move': dict, 'group': str}``.  The
        ``kind`` key is retained so callers can stay agnostic about how the
        list was built.
        """
        self._sync_active_family()
        items: List[Dict[str, Any]] = []
        for group_label, members in self._hand_groups_in_order():
            if self._active_family is not None and group_label != self._active_family:
                continue
            for move in members:
                items.append({
                    'kind': 'move',
                    'move': move,
                    'group': group_label,
                })
        return items

    def handle_event(self, event, *, allow_actions: bool = True) -> bool:
        """Returns True if the rail consumed the event."""
        if event.type not in (
            pygame.MOUSEBUTTONDOWN,
            pygame.MOUSEBUTTONUP,
            pygame.MOUSEMOTION,
            pygame.MOUSEWHEEL,
        ):
            return False
        layout = self._ensure_layout()
        rail_rect = pygame.Rect(*layout.tactics_rail.rect)
        if event.type == pygame.MOUSEWHEEL:
            mx, my = pygame.mouse.get_pos()
            if rail_rect.collidepoint(mx, my):
                self._scroll = max(0, self._scroll - event.y)
                self._clamp_scroll()
                return True
            return False
        # Drag-and-drop combine handling. (#8b)
        if event.type == pygame.MOUSEMOTION:
            if self._list_press is not None:
                return self._update_list_drag(event.pos)
            if self._drag_origin_id is None:
                return False
            self._drag_pos = event.pos
            if not self._drag_active:
                # Promote to active drag once the cursor moves far enough.
                origin_rect = self._cell_rect_for(self._drag_origin_id)
                if origin_rect is not None:
                    dx = event.pos[0] - origin_rect.centerx
                    dy = event.pos[1] - origin_rect.centery
                    if (dx * dx + dy * dy) ** 0.5 >= self.DRAG_START_PX:
                        self._drag_active = True
            return self._drag_active
        if event.type == pygame.MOUSEBUTTONUP:
            if self._list_press is not None:
                was_drag = self._list_drag_active
                self._list_press = None
                self._list_drag_active = False
                if was_drag:
                    self._snap_scroll_to_row()
                    return True
            if event.button != 1 or self._drag_origin_id is None:
                self._cancel_drag()
                return False
            origin_id = self._drag_origin_id
            was_active = self._drag_active
            self._cancel_drag()
            if not was_active:
                return False
            # Find the cell the cursor is over.
            target_id = None
            for rect, mid in zip(self._cell_rects, self._cell_move_ids):
                if rect.collidepoint(event.pos):
                    target_id = mid
                    break
            if target_id is None or target_id == origin_id:
                return True
            origin = next((m for m in self._hand_moves()
                           if int(m.get('id') or 0) == origin_id), None)
            target = next((m for m in self._hand_moves()
                           if int(m.get('id') or 0) == target_id), None)
            if (origin is not None and target is not None
                    and self._can_combine(origin, target)):
                self._pending_action = {
                    'action': ACTION_COMBINE,
                    'move': origin,
                    'partner': target,
                }
                self._combine_pending = False
                self._combine_partner_id = None
            return True
        # MOUSEBUTTONDOWN
        if event.button != 1:
            return False
        pos = event.pos
        if not rail_rect.collidepoint(pos):
            return False
        # Banner — click anywhere inside it to dismiss (#8a). The banner is an
        # overlay now, so its own rect is the dismiss target.
        if self._result_banner is not None and self._banner_rect is not None:
            if self._banner_rect.collidepoint(pos):
                self._result_banner = None
                return True
        # Family filter chips — a chip swaps the visible family outright.
        for key, chip_rect in self._filter_chip_rects:
            if self._touch_collide(chip_rect, pos,
                                   min_w=chip_rect.width,
                                   min_h=settings.TOUCH_COMPACT_MIN):
                self._set_active_family(key)
                return True
        # Scroll buttons (desktop only — touch builds grab-scroll the list,
        # so an arrow sitting on top of a row would only steal taps).
        if self._touch_collide(self._scroll_up_rect, pos,
                               settings.TOUCH_COMPACT_MIN, settings.TOUCH_COMPACT_MIN):
            self._scroll = max(0, self._scroll - 1)
            self._clamp_scroll()
            return True
        if self._touch_collide(self._scroll_down_rect, pos,
                               settings.TOUCH_COMPACT_MIN, settings.TOUCH_COMPACT_MIN):
            self._scroll += 1
            self._clamp_scroll()
            return True
        # Action buttons
        for key, rect in self._action_button_rects.items():
            if self._touch_collide(rect, pos,
                                   settings.TOUCH_COMPACT_MIN,
                                   settings.TOUCH_COMPACT_MIN):
                if allow_actions:
                    self._trigger_action(key)
                return True
        # Cell selection
        for rect, mid in zip(self._cell_rects, self._cell_move_ids):
            # Adjacent tactic rows are already compact touch targets.  Do not
            # inflate them to the global full-size target: the inflated rectangles
            # overlap vertically and make taps near a row boundary select the
            # preceding tactic.  Compact-min preserves a generous hit area
            # without crossing into a neighbour.
            if self._touch_collide(
                    rect, pos,
                    settings.TOUCH_COMPACT_MIN,
                    settings.TOUCH_COMPACT_MIN):
                previous_selection = self._selected_id
                self._handle_cell_click(mid)
                # Remember the press so a swipe can take the gesture back:
                # selection feels instant, but dragging restores it and
                # scrolls instead of leaving a stray selection behind.
                # Touch only — on desktop the same motion is drag-to-combine,
                # and the wheel/arrows already scroll.
                if settings.TOUCH_TARGET_MIN > 0:
                    self._list_press = {
                        'y': pos[1],
                        'x': pos[0],
                        'previous_selection': previous_selection,
                    }
                    self._list_drag_active = False
                # Arm drag-and-drop combine (#8b) — only meaningful for
                # single Daggers; the actual drag promotes on motion.  Touch
                # builds never arm it: a swipe over two same-colour Daggers
                # would fire an unconfirmed, destructive Combine.
                move = next((m for m in self._hand_moves()
                             if int(m.get('id') or 0) == mid), None)
                if (allow_actions and settings.TOUCH_TARGET_MIN <= 0
                        and move is not None and self._is_single_dagger(move)):
                    self._drag_origin_id = mid
                    self._drag_pos = pos
                    self._drag_active = False
                return True
        # Empty space below the last row still starts a scroll drag.
        hand_rect = self._dyn_hand_list_rect
        if (settings.TOUCH_TARGET_MIN > 0 and hand_rect is not None
                and hand_rect.collidepoint(pos)):
            self._list_press = {
                'y': pos[1], 'x': pos[0], 'previous_selection': self._selected_id,
            }
            self._list_drag_active = False
        return True  # consumed even if hit empty space inside the rail

    # ------------------------------------------------------- list grab-scroll
    def _update_list_drag(self, pos) -> bool:
        """Follow the pointer while a press inside the hand list is held."""
        press = self._list_press
        if press is None:
            return False
        dy = pos[1] - press['y']
        if not self._list_drag_active:
            if abs(dy) < self.DRAG_START_PX:
                return False
            self._list_drag_active = True
            # The press had selected a row optimistically; a drag means the
            # player wanted to scroll, so give the previous selection back.
            if self._selected_id != press.get('previous_selection'):
                self._selected_id = press.get('previous_selection')
                self._selection_revision += 1
            self._combine_pending = False
            self._combine_partner_id = None
        press['y'] = pos[1]
        self._scroll_px = max(0, self._scroll_px - dy)
        self._clamp_scroll()
        return True

    def _snap_scroll_to_row(self) -> None:
        """Settle a released drag on the nearest row boundary."""
        cell_h = self._cell_height()
        self._scroll_px = int(
            round(self._scroll_px / float(cell_h))) * cell_h
        self._clamp_scroll()

    def _cell_rect_for(self, move_id: int) -> Optional[pygame.Rect]:
        for rect, mid in zip(self._cell_rects, self._cell_move_ids):
            if mid == move_id:
                return rect
        return None

    def _cancel_drag(self) -> None:
        self._drag_origin_id = None
        self._drag_pos = None
        self._drag_active = False

    def _visible_cell_capacity(self) -> int:
        """How many whole rows the hand viewport can show right now."""
        rail = self._ensure_layout().tactics_rail
        list_h = (self._dyn_hand_list_rect.height
                  if self._dyn_hand_list_rect is not None
                  else rail.hand_list_rect[3])
        height_capacity = max(1, list_h // max(1, rail.cell_height))
        visible_cap = rail.cells_visible
        if settings.TOUCH_TARGET_MIN > 0:
            visible_cap = max(visible_cap, height_capacity)
        return max(1, min(visible_cap, height_capacity))

    def _clamp_scroll(self):
        total = len(self._visible_hand_items())
        # Active removed-ghost cells share the visible budget (each one
        # steals a slot from the bottom).
        ghost_count = len(getattr(self, '_removed_ghosts', {}) or {})
        effective_visible = max(1, self._visible_cell_capacity() - ghost_count)
        max_px = max(0, (total - effective_visible)) * self._cell_height()
        self._scroll_px = max(0, min(int(self._scroll_px), max_px))

    def _handle_cell_click(self, mid: int):
        # Ghost cells represent tactics that the server has already marked
        # as spell-purged but the local spell replay is still showing them
        # alive at the displayed timeline step.  They are visible for
        # continuity but must NOT be selectable or actionable — otherwise
        # the player can fire requests that the server immediately rejects.
        target = next(
            (m for m in self._hand_moves() if int(m.get('id') or 0) == mid),
            None,
        )
        if self._is_ghost_move(target):
            self.set_result_banner('Resolving spell…', ttl_ms=1200)
            return
        if self._combine_pending and self._selected_id is not None and mid != self._selected_id:
            # Auto-fire combine on partner click — no second confirm needed.
            origin = self._selected_move()
            partner = None
            for m in self._hand_moves():
                if m.get('id') == mid:
                    partner = m
                    break
            if origin is not None and partner is not None and self._can_combine(origin, partner):
                self._pending_action = {
                    'action': ACTION_COMBINE,
                    'move': origin,
                    'partner': partner,
                }
                self._combine_pending = False
                self._combine_partner_id = None
                self._selected_id = None
                return
            # Invalid pair — fall through to plain selection toggle so the
            # player can pick a different partner without re-arming.
        # Plain selection / toggle.
        next_id = None if self._selected_id == mid else mid
        if next_id != self._selected_id:
            self._selection_revision += 1
        self._selected_id = next_id
        self._combine_pending = False
        self._combine_partner_id = None

    def _trigger_action(self, key: str):
        # If the button was rendered as disabled this frame, surface the
        # reason instead of silently doing nothing.
        disabled_reasons = getattr(self, '_disabled_action_reasons', None) or {}
        if key in disabled_reasons:
            self.set_result_banner(disabled_reasons[key], ttl_ms=1800)
            return
        # Block all actions while a played-tactic flight animation or a
        # round-reveal sequence is in progress.  Without this the player
        # can fire a second mutating request before the first one's
        # animation finishes — racing cache state and the server's
        # per-game lock.
        try:
            reason_getter = getattr(self._parent, 'conquer_action_block_reason', None)
            if callable(reason_getter):
                reason = reason_getter()
                if reason:
                    self.set_result_banner(reason, ttl_ms=900)
                    return
            else:
                flight_check = getattr(self._parent, 'is_tactic_flight_active', None)
                if callable(flight_check) and flight_check():
                    self.set_result_banner('Tactic in flight…', ttl_ms=900)
                    return
        except Exception:
            pass
        sel = self._selected_move()
        if key == ACTION_SKIP:
            if self._is_my_battle_turn():
                self._pending_action = {'action': ACTION_SKIP}
            return
        if not sel:
            return
        if self._is_ghost_move(sel):
            # Defence in depth: a ghost should never have been selectable
            # in the first place, but block any action that slips through.
            self.set_result_banner('Resolving spell…', ttl_ms=1200)
            return
        if key == ACTION_PLAY:
            if self._is_my_battle_turn():
                self._pending_action = {'action': ACTION_PLAY, 'move': sel}
            return
        if key == ACTION_GAMBLE:
            # Devil's bargain: first click arms, second click (within the
            # confirm window) commits. Gambling is a tactics-hand mutation,
            # not a battle-turn action.
            sel_id = sel.get('id')
            if not self._gamble_armed_for(sel_id):
                now = pygame.time.get_ticks()
                try:
                    self._gamble_armed = {
                        'move_id': int(sel_id or 0),
                        'until_ms': now + self.GAMBLE_CONFIRM_MS,
                    }
                except Exception:
                    self._gamble_armed = None
                    return
                game = getattr(self._parent.state, 'game', None)
                used, _rounds = self._gamble_counts_state(game)
                name = sel.get('family_name') or 'tactic'
                # All Seeing Eye: reveal exactly what the gamble would yield.
                # The server pins the previewed specs, so gambling this
                # tactic delivers precisely these two replacements.
                specs = self._gamble_preview_specs(sel_id)
                if specs is None and game is not None:
                    ase_check = getattr(game, 'has_active_all_seeing_eye', None)
                    if callable(ase_check) and ase_check():
                        fetch = getattr(self._parent,
                                        'request_conquer_gamble_preview', None)
                        if callable(fetch):
                            specs = fetch(sel_id)
                if specs:
                    # The overlay panel shows the actual cards; the banner
                    # just narrates what is happening.
                    self.set_result_banner(
                        'The Eye reveals your gamble — click Gamble again '
                        'to take these cards.',
                        color=(130, 190, 255), ttl_ms=self.GAMBLE_CONFIRM_MS)
                elif used >= self.GAMBLE_PER_BATTLE_LIMIT - 1:
                    self.set_result_banner(
                        f'LAST gamble — burn {name} for 2 random? Click again.',
                        color=(255, 170, 96), ttl_ms=self.GAMBLE_CONFIRM_MS)
                else:
                    self.set_result_banner(
                        f'Burn {name} for 2 random tactics? Click again.',
                        color=(250, 226, 130), ttl_ms=self.GAMBLE_CONFIRM_MS)
                return
            self._gamble_armed = None
            self._pending_action = {'action': ACTION_GAMBLE, 'move': sel}
            # Kick off the coin-flip animation on the source cell. (#8c)
            try:
                self._gamble_anim = {
                    'move_id': int(sel.get('id') or 0),
                    'started_at': pygame.time.get_ticks(),
                    'duration': 1100,
                }
            except Exception:
                self._gamble_anim = None
            return
        if key == ACTION_DISMANTLE:
            if self._is_double_dagger(sel):
                self._pending_action = {'action': ACTION_DISMANTLE, 'move': sel}
            return
        if key == ACTION_COMBINE:
            partner = self._combine_partner_move()
            if partner is None or not self._can_combine(sel, partner):
                partner = self._best_combine_partner(sel)
            if partner is not None and self._can_combine(sel, partner):
                self._pending_action = {
                    'action': ACTION_COMBINE,
                    'move': sel,
                    'partner': partner,
                }
                self._combine_pending = False
                self._combine_partner_id = None
            else:
                self.set_result_banner('No matching Dagger', ttl_ms=1600)
                self._combine_pending = False
                self._combine_partner_id = None

    # ------------------------------------------------------------------ draw
    def _rail_render_cache_key(self, rail_rect: pygame.Rect, now: int):
        if rail_rect.collidepoint(pygame.mouse.get_pos()):
            return None
        if self._drag_active or self._drag_origin_id is not None:
            return None
        if self._gamble_armed is not None:
            # Armed-confirm state renders a live countdown affordance.
            return None
        if self._gamble_anim:
            started = int(self._gamble_anim.get('started_at', 0) or 0)
            duration = int(self._gamble_anim.get('duration', 0) or 0)
            if now < started + duration:
                return None
        if self._server_action_pending is not None:
            # Pending source rows use a small live pulse while the non-blocking
            # request is in flight.
            return None
        if any(int(expires or 0) > now for expires in self._new_move_glow_until.values()):
            return None
        if any(int(data.get('expires_at') or 0) > now for data in self._removed_ghosts.values()):
            return None

        game = getattr(self._parent.state, 'game', None)
        moves_key = tuple(
            sorted(
                (
                    move.get('id'),
                    move.get('family_name'),
                    move.get('suit'),
                    move.get('rank'),
                    move.get('value'),
                    move.get('status'),
                    move.get('played_round'),
                    move.get('call_figure_id'),
                    bool(move.get('_render_ghost')),
                )
                for move in self._moves()
            )
        )
        banner_key = None
        if self._result_banner:
            banner_key = (
                self._result_banner.get('text'),
                self._result_banner.get('kind'),
                bool(self._result_banner.get('expires_at')),
            )
        return (
            rail_rect.x, rail_rect.y, rail_rect.w, rail_rect.h,
            moves_key,
            self._scroll_px,
            self._selected_id,
            self._combine_partner_id,
            self._combine_pending,
            self._active_family,
            banner_key,
            getattr(game, 'battle_confirmed', None),
            getattr(game, 'battle_turn_player_id', None),
            getattr(game, 'player_id', None),
            getattr(game, 'battle_round', None),
            repr(getattr(game, 'battle_gamble_counts', None)),
        )

    def draw(self):
        self._power_cache = {}
        layout = self._ensure_layout()
        rail = layout.tactics_rail
        rail_rect = pygame.Rect(*rail.rect)
        now = pygame.time.get_ticks()

        # Detect newly-added moves so we can glow them (#8c) and expire
        # the banner if its TTL has passed (#8a).
        self._detect_new_moves()
        if self._result_banner and self._result_banner.get('expires_at'):
            if now > self._result_banner['expires_at']:
                self._result_banner = None

        cache_key = self._rail_render_cache_key(rail_rect, now)
        if (cache_key is not None and self._cached_render_key == cache_key
                and self._cached_render_surface is not None):
            self.window.blit(self._cached_render_surface, rail_rect.topleft)
            return

        previous_clip = self.window.get_clip()
        self.window.set_clip(rail_rect)

        bg = pygame.Surface(rail_rect.size, pygame.SRCALPHA)
        bg.fill(_BG_RGBA)
        self.window.blit(bg, rail_rect.topleft)
        pygame.draw.rect(self.window, _BORDER_RGBA, rail_rect, 2, border_radius=8)

        top_strip_rect = pygame.Rect(*rail.top_strip_rect)
        selected_detail_rect = pygame.Rect(*rail.selected_detail_rect)
        hand_list_rect = pygame.Rect(*rail.hand_list_rect)
        action_tray_rect = pygame.Rect(*rail.action_tray_rect)
        mobile_compact = settings.TOUCH_TARGET_MIN > 0

        # ── Family filter strip ─────────────────────────────────────
        # Mobile spends the whole (already minimal) top strip on chips; the
        # per-family counts make the old "N battle moves" title redundant.
        # Desktop keeps its status line and puts the chips underneath.
        chips = self._family_filter_chips()
        filter_rect = pygame.Rect(top_strip_rect.x, top_strip_rect.y,
                                  top_strip_rect.width, 0)
        if chips:
            chip_h = self._filter_strip_height()
            if mobile_compact:
                filter_rect.height = chip_h
                grow = max(0, chip_h - top_strip_rect.height)
                top_strip_rect.height = 0
                if grow:
                    hand_list_rect.y += grow
                    hand_list_rect.height -= grow
                    selected_detail_rect.y += grow
                    selected_detail_rect.height = max(
                        0, selected_detail_rect.height - grow)
            else:
                # Desktop keeps its gamble status line above the chips. Borrow
                # from the list only if the band cannot hold both.
                status_h = settings.get_font(
                    max(settings.FS_CONQUER_LABEL,
                        int(settings.FS_TINY * 0.95))).get_height() + 8
                deficit = max(0, chip_h + status_h - top_strip_rect.height)
                grow = min(deficit,
                           max(0, hand_list_rect.height - 2 * rail.cell_height))
                if grow:
                    top_strip_rect.height += grow
                    selected_detail_rect.y += grow
                    hand_list_rect.y += grow
                    hand_list_rect.height -= grow
                chip_h = min(chip_h, max(0, top_strip_rect.height - 4))
                filter_rect.height = chip_h
                filter_rect.y = top_strip_rect.bottom - chip_h
                top_strip_rect.height = max(0, top_strip_rect.height - chip_h)

        # ── Action tray: reserved, never selection-driven ───────────
        # The tray used to grow when a tactic was selected, stealing a row
        # from the hand — so tapping the bottom row made that very row
        # disappear.  Reserve the worst-case height up front instead: the
        # hand viewport then keeps one constant size for the whole battle.
        action_h = max(action_tray_rect.height,
                       self._reserved_action_tray_height(action_tray_rect.width))
        min_list_h = 2 * rail.cell_height
        hand_slack = max(0, hand_list_rect.height - min_list_h)
        grow = min(max(0, action_h - action_tray_rect.height), hand_slack)
        if grow > 0:
            action_tray_rect.y -= grow
            action_tray_rect.height += grow
            hand_list_rect.height -= grow

        # On touch layouts the selected-detail card repeated information
        # already present in the highlighted row, while costing almost a full
        # extra tactic slot.  Fold that band into the scrollable hand instead.
        # The action tray remains the unambiguous place to act on the selected
        # row, and desktop keeps its richer hover/detail presentation.
        if mobile_compact and selected_detail_rect.height > 0:
            hand_list_rect = hand_list_rect.union(selected_detail_rect)
            selected_detail_rect.height = 0
        self._dyn_top_strip_rect = top_strip_rect
        self._dyn_filter_strip_rect = filter_rect if filter_rect.height else None
        self._dyn_hand_list_rect = hand_list_rect
        self._dyn_action_tray_rect = action_tray_rect

        if top_strip_rect.height > 0:
            self._draw_top_strip(top_strip_rect)
        self._filter_chip_rects = []
        if filter_rect.height > 0:
            self._draw_filter_strip(filter_rect, chips)
        visible_cells = rail.cells_visible
        if mobile_compact:
            visible_cells = max(
                visible_cells,
                hand_list_rect.height // max(1, rail.cell_height),
            )
        self._draw_hand_list(hand_list_rect, rail.cell_height, visible_cells)
        if selected_detail_rect.height > 0:
            self._draw_selected_detail(selected_detail_rect)
        self._draw_action_tray(action_tray_rect)
        # The banner floats over the bottom of the list: a layout-consuming
        # banner used to shrink the hand mid-interaction.
        self._draw_result_banner(hand_list_rect)
        # The All Seeing Eye gamble preview takes over the whole hand +
        # detail region so the two forecast cards have room to be legible.
        self._draw_gamble_preview_overlay(
            hand_list_rect.union(selected_detail_rect))
        self.window.set_clip(previous_clip)

        if cache_key is not None:
            try:
                self._cached_render_surface = self.window.subsurface(rail_rect).copy()
                self._cached_render_key = cache_key
            except Exception:
                self._cached_render_surface = None
                self._cached_render_key = None
        else:
            self._cached_render_surface = None
            self._cached_render_key = None

    @staticmethod
    def _draw_eye_glyph(window, cx, cy, w, color):
        """Draw a small all-seeing-eye glyph (almond + iris + pupil)."""
        h = max(3, int(w * 0.55))
        rect = pygame.Rect(0, 0, w, h)
        rect.center = (int(cx), int(cy))
        pygame.draw.ellipse(window, color, rect, max(1, w // 14))
        iris_r = max(2, int(h * 0.42))
        pygame.draw.circle(window, color, (int(cx), int(cy)), iris_r,
                           max(1, w // 18))
        pygame.draw.circle(window, color, (int(cx), int(cy)),
                           max(1, iris_r // 2))

    def _draw_gamble_preview_overlay(self, rect: pygame.Rect) -> None:
        """All Seeing Eye: a clean forecast panel showing the two pinned
        replacement tactics as real card faces while the Gamble confirm is
        armed.  Occupies the hand+detail region so the cards read clearly.
        """
        armed = self._gamble_armed
        if not armed or rect is None or rect.height < 60 or rect.width < 60:
            return
        if pygame.time.get_ticks() >= int(armed.get('until_ms') or 0):
            return
        specs = list(self._gamble_preview_specs(armed.get('move_id')) or [])[:2]
        if not specs:
            return

        accent = (130, 190, 255)
        # ── Panel backing ───────────────────────────────────────────
        panel = rect.inflate(-8, -8)
        bg = pygame.Surface(panel.size, pygame.SRCALPHA)
        bg.fill((12, 20, 32, 248))
        self.window.blit(bg, panel.topleft)
        pygame.draw.rect(self.window, accent, panel, 2, border_radius=10)
        inner = panel.inflate(-16, -14)

        title_font = settings.get_font(max(settings.FS_CONQUER_LABEL, int(settings.FS_TINY * 0.95)), bold=True)
        sub_font = settings.get_font(max(settings.FS_CONQUER_META, int(settings.FS_TINY * 0.8)))
        label_font = settings.get_font(max(settings.FS_CONQUER_META, int(settings.FS_TINY * 0.78)), bold=True)

        # ── Header: eye glyph + title + subtitle ────────────────────
        y = inner.y
        eye_w = max(12, int(inner.width * 0.16))
        self._draw_eye_glyph(self.window, inner.centerx,
                             y + eye_w * 0.30, eye_w, accent)
        y += int(eye_w * 0.30) + max(4, eye_w // 3)
        title = title_font.render('ALL-SEEING EYE', True, (196, 224, 255))
        self.window.blit(title, (inner.centerx - title.get_width() // 2, y))
        y += title.get_height() + 1
        sub = sub_font.render('Your gamble will draw:', True, (150, 178, 210))
        self.window.blit(sub, (inner.centerx - sub.get_width() // 2, y))
        y += sub.get_height() + 6

        # ── Footer call-to-action (reserve space first) ─────────────
        cta_text = 'Click Gamble again ▸'
        cta = label_font.render(cta_text, True, (14, 22, 34))
        cta_pill = pygame.Rect(0, 0, cta.get_width() + 20, cta.get_height() + 8)
        cta_pill.centerx = inner.centerx
        cta_pill.bottom = inner.bottom

        # ── Cards region (between header and CTA) ───────────────────
        cards_top = y
        cards_bottom = cta_pill.top - 8
        avail_h = max(20, cards_bottom - cards_top)
        label_h = label_font.get_height() + 3
        gap = 10
        # Fit two cards side by side within width and height.
        card_h = min(avail_h - label_h, int((inner.width - gap) / 2 * 1.42))
        card_h = max(24, card_h)
        card_w = max(16, int(card_h / 1.42))
        if card_w * 2 + gap > inner.width:
            card_w = max(14, (inner.width - gap) // 2)
            card_h = int(card_w * 1.42)
        total_w = card_w * 2 + gap
        x = inner.centerx - total_w // 2
        card_y = cards_top + max(0, (avail_h - label_h - card_h) // 2)
        for spec in specs:
            card_rect = pygame.Rect(x, card_y, card_w, card_h)
            surf = None
            try:
                from game.components.cards.card_img import CardImg
                surf = CardImg(self.window, spec.get('suit'), spec.get('rank'),
                               width=card_w, height=card_h).front_img
            except Exception:
                surf = None
            if surf is not None:
                self.window.blit(surf, card_rect.topleft)
            else:
                pygame.draw.rect(self.window, (44, 62, 84), card_rect,
                                 border_radius=4)
            pygame.draw.rect(self.window, accent, card_rect, 2, border_radius=4)
            name = self._fit_text(str(spec.get('family_name') or 'Dagger'),
                                  label_font, card_w + gap)
            label = label_font.render(name, True, (206, 226, 250))
            self.window.blit(label, (card_rect.centerx - label.get_width() // 2,
                                     card_rect.bottom + 2))
            x += card_w + gap

        # ── Draw the CTA pill on top ────────────────────────────────
        pygame.draw.rect(self.window, accent, cta_pill, border_radius=cta_pill.height // 2)
        self.window.blit(cta, (cta_pill.centerx - cta.get_width() // 2,
                               cta_pill.centery - cta.get_height() // 2))

    # -- top strip
    def _draw_top_strip(self, rect: pygame.Rect):
        if settings.TOUCH_TARGET_MIN > 0:
            self._draw_mobile_top_strip(rect)
            return
        # Tactics-in-hand count + gamble status. The count line is dropped
        # when the filter strip is showing: its chips already carry per-family
        # counts, and the "All" chip carries the total.
        game = getattr(self._parent.state, 'game', None)
        gamble_text, gamble_state = self._gamble_status_for_strip(game)
        line2 = gamble_text
        font = settings.get_font(max(settings.FS_CONQUER_LABEL, int(settings.FS_SMALL * 0.95)), bold=True)
        sub = settings.get_font(max(settings.FS_CONQUER_LABEL, int(settings.FS_TINY * 0.95)))
        # The pip cluster lives in the strip's top-right corner; text has to
        # stop short of it or the two overprint each other.
        avail = max(1, rect.width - 16 - self._gamble_pip_span(rect))
        if sub.size(line2)[0] > avail:
            # Narrow strip (chips + pips took the room): the compact wording
            # beats wrapping a status line onto a second row that has no space.
            line2 = line2.replace(' this round', '').replace(' of the battle', '')
        y = rect.y + 4
        if not self._family_filter_chips():
            hand_count = len(self._hand_moves())
            word = 'battle move' if hand_count == 1 else 'battle moves'
            for line in self._wrap_text(f'{hand_count} {word}', font, avail):
                if y + font.get_height() > rect.bottom:
                    break
                surf = font.render(line, True, _TEXT_PRIMARY)
                self.window.blit(surf, (rect.x + 8, y))
                y += font.get_height() + 1
            y += 2
        # Muted grey when the player has already gambled this round; warm
        # ember for the final remaining gamble.
        if gamble_state == 'used':
            line2_color = (140, 132, 116)
        elif gamble_state == 'last':
            line2_color = (255, 170, 96)
        else:
            line2_color = _TEXT_SECONDARY
        for line in self._wrap_text(line2, sub, avail):
            if y + sub.get_height() > rect.bottom:
                break
            surf = sub.render(line, True, line2_color)
            self.window.blit(surf, (rect.x + 8, y))
            y += sub.get_height() + 1
        self._draw_gamble_pips(rect, game)

    def _draw_mobile_top_strip(self, rect: pygame.Rect) -> None:
        """Draw a collision-free one-line summary for narrow touch rails."""
        game = getattr(self._parent.state, 'game', None)
        hand_count = len(self._hand_moves())
        title_font = settings.get_font(
            max(settings.FS_CONQUER_META, int(settings.FS_TINY * 0.82)),
            bold=True,
        )
        badge_font = settings.get_font(
            max(settings.FS_CONQUER_META, int(settings.FS_TINY * 0.82)),
            bold=True,
        )

        _gamble_text, gamble_state = self._gamble_status_for_strip(game)
        used, _used_rounds = (
            self._gamble_counts_state(game) if game is not None else (0, [])
        )
        remaining = max(0, self.GAMBLE_PER_BATTLE_LIMIT - used)
        if gamble_state == 'used':
            badge_label = 'USED'
        elif gamble_state == 'limit':
            badge_label = '0'
        else:
            badge_label = f'×{remaining}'

        badge_text = badge_font.render(badge_label, True, (26, 21, 15))
        badge_rect = badge_text.get_rect()
        icon_size = max(9, badge_text.get_height())
        badge_rect.width += icon_size + 14
        badge_rect.height += 6
        badge_rect.right = rect.right - 6
        badge_rect.centery = rect.centery
        if gamble_state == 'used':
            badge_fill = (112, 102, 84)
        elif gamble_state == 'last':
            badge_fill = (225, 142, 70)
        elif gamble_state == 'limit':
            badge_fill = (92, 76, 62)
        else:
            badge_fill = (200, 164, 76)
        pygame.draw.rect(
            self.window, badge_fill, badge_rect,
            border_radius=max(3, badge_rect.height // 2),
        )
        icon_rect = pygame.Rect(0, 0, icon_size, icon_size)
        icon_rect.midleft = (badge_rect.left + 5, badge_rect.centery)
        self._draw_action_icon(
            self.window, ACTION_GAMBLE, icon_rect, (38, 29, 18))
        text_area = pygame.Rect(
            icon_rect.right + 3, badge_rect.top,
            badge_rect.right - icon_rect.right - 7, badge_rect.height,
        )
        self.window.blit(
            badge_text,
            badge_text.get_rect(center=text_area.center),
        )

        title_x = rect.left + 7
        title_max_w = max(1, badge_rect.left - title_x - 4)
        title = f'TACTICS {hand_count}'
        title_surf = title_font.render(
            self._fit_text(title, title_font, title_max_w),
            True,
            _TEXT_PRIMARY,
        )
        self.window.blit(title_surf, title_surf.get_rect(
            midleft=(title_x, rect.centery)))
        pygame.draw.line(
            self.window, (94, 72, 46),
            (rect.left + 4, rect.bottom - 1),
            (rect.right - 4, rect.bottom - 1),
            1,
        )

    # -- family filter strip
    FILTER_CHIP_MIN_W = 26

    def _filter_strip_height(self) -> int:
        """One row of chips, tall enough for family art above its count.

        The mobile hand list runs with ~20 px of slack (four 48 px rows in a
        212 px viewport), so the extra height here costs no tactic row.
        """
        if settings.TOUCH_TARGET_MIN > 0:
            return max(settings.TOUCH_COMPACT_MIN + 8, 38)
        return 34

    def _family_icon(self, family_name: str, size: int):
        """One family's artwork at ``size`` px, or ``None`` if unavailable.

        ``_conquer_battle_move_icon_assets`` scales its icons to
        ``requested - 6``, so ask for the extra pixels rather than getting a
        sliver back.
        """
        if not family_name or size <= 0:
            return None
        try:
            _glow, icon_cache, _frame, _suit, _font = (
                self._parent._conquer_battle_move_icon_assets(size + 6))
        except Exception:
            return None
        return icon_cache.get(family_name)

    # A fan of three battle-move figures needs roughly this much room before
    # the individual silhouettes survive; below it the overlap is mush and a
    # single emblem reads far better.
    COMPOSITE_ICON_MIN_PX = 34

    # Which member family stands for a multi-family group on a chip too small
    # to fan them. First one the player actually holds wins, so the chip never
    # advertises a tactic that is not in the hand.
    GROUP_EMBLEM_PREFERENCE = {
        'Call': ('Call King', 'Call Military', 'Call Villager'),
        'Dagger': ('Dagger', 'Double Dagger'),
    }

    def _filter_chip_icon(self, chip: Dict[str, Any], size: int):
        """Artwork for a chip, composited where the space allows it.

        A group like ``Call`` covers three server families (Villager /
        Military / King), and borrowing whichever one happened to be
        strongest made the chip change picture between hands. Wide chips fan
        all members into one icon; narrow ones fall back to a fixed emblem.
        """
        families = [name for name in (chip.get('icon_families') or []) if name]
        if not families or size <= 0:
            return None
        if len(families) == 1:
            return self._family_icon(families[0], size)
        if size >= self.COMPOSITE_ICON_MIN_PX:
            composite = self._composite_family_icon(families, size)
            if composite is not None:
                return composite
        for name in self.GROUP_EMBLEM_PREFERENCE.get(chip.get('key'), ()):
            if name in families:
                icon = self._family_icon(name, size)
                if icon is not None:
                    return icon
        return self._family_icon(families[0], size)

    def _composite_family_icon(self, families: List[str], size: int):
        """Fan a group's family icons into one ``size``-square surface."""
        cache = getattr(self, '_chip_icon_cache', None)
        if cache is None:
            cache = {}
            self._chip_icon_cache = cache
        key = (tuple(families), int(size))
        if key in cache:
            return cache[key]

        step = max(3, size // 6)
        # Each extra layer shrinks every icon, so stop stacking once the
        # members would drop below the size where they read at all.
        families = families[:max(2, (size - self.COMPOSITE_ICON_MIN_PX // 2) // step)]
        side = max(8, size - step * (len(families) - 1))
        icons = [icon for icon in
                 (self._family_icon(name, side) for name in families)
                 if icon is not None]
        if not icons:
            cache[key] = None
            return None
        surface = pygame.Surface((size, size), pygame.SRCALPHA)
        x = max(0, (size - (side + step * (len(icons) - 1))) // 2)
        y = max(0, (size - side) // 2)
        for icon in icons:
            if icon.get_size() != (side, side):
                icon = pygame.transform.smoothscale(icon, (side, side))
            surface.blit(icon, (x, y))
            x += step
        cache[key] = surface
        return surface

    # Text fallback when a family has no artwork (or in headless tests).
    FILTER_CHIP_ABBREVIATIONS = {
        'Dagger': 'DAG',
        'Block': 'BLK',
        'Call': 'CALL',
        'Buff': 'BUF',
    }

    @classmethod
    def _filter_chip_label(cls, chip: Dict[str, Any], font=None,
                           max_width: int = 0) -> str:
        """Shortest label that still fits: 'CALL' → 'CAL' → 'CA' → 'C'."""
        if chip['key'] == cls.FILTER_ALL:
            return 'ALL'
        label = str(chip.get('label') or '')
        text = cls.FILTER_CHIP_ABBREVIATIONS.get(label, label[:3].upper())
        if font is None or max_width <= 0:
            return text
        while len(text) > 1 and font.size(text)[0] > max_width:
            text = text[:-1]
        return text

    def _draw_filter_strip(self, rect: pygame.Rect,
                           chips: List[Dict[str, Any]]) -> None:
        """Draw one chip per family (plus ``All``) and record tap rects.

        Chips share the strip width evenly.  When ``All`` would squeeze the
        family chips below a tappable width it is dropped — the active chip
        then toggles back to the full hand, and an emptied family resets the
        filter automatically.
        """
        chips = list(chips)
        gap = 3
        if settings.TOUCH_TARGET_MIN > 0:
            # Run the strip out to the rail edge like a tab bar: on a 137 px
            # rail those few pixels are the difference between a 27 px and a
            # 33 px chip.
            try:
                rail_rect = pygame.Rect(*self._ensure_layout().tactics_rail.rect)
                rect = pygame.Rect(rail_rect.left + 3, rect.y,
                                   rail_rect.width - 6, rect.height)
            except Exception:
                pass
        usable = rect.width - 4
        while (len(chips) > 1
               and (usable - gap * (len(chips) - 1)) // len(chips)
               < self.FILTER_CHIP_MIN_W
               and chips[0]['key'] == self.FILTER_ALL):
            chips = chips[1:]
        count = max(1, len(chips))
        chip_w = max(1, (usable - gap * (count - 1)) // count)
        chip_h = max(1, rect.height - 4)
        label_font = settings.get_font(
            max(settings.FS_CONQUER_META, int(settings.FS_TINY * 0.78)), bold=True)
        count_font = settings.get_font(
            max(settings.FS_CONQUER_META, int(settings.FS_TINY * 0.72)), bold=True)
        x = rect.x + 2
        y = rect.y + 2
        for index, chip in enumerate(chips):
            width = (rect.right - 2 - x) if index == count - 1 else chip_w
            chip_rect = pygame.Rect(x, y, max(1, width), chip_h)
            is_all = chip['key'] == self.FILTER_ALL
            active = ((self._active_family is None and is_all)
                      or (self._active_family == chip['key'] and not is_all))
            fill = (58, 92, 88) if active else (44, 36, 28)
            border = _SELECTED_RGBA if active else (108, 88, 58)
            pygame.draw.rect(self.window, fill, chip_rect, 0, border_radius=5)
            pygame.draw.rect(self.window, border, chip_rect,
                             2 if active else 1, border_radius=5)
            fg = (226, 246, 242) if active else _TEXT_SECONDARY
            count_surf = count_font.render(
                str(chip['count']), True, fg if active else _TEXT_MUTED)
            icon_size = max(0, min(chip_rect.width - 8,
                                   chip_rect.height - count_surf.get_height() - 4))
            icon = None if is_all else self._filter_chip_icon(chip, icon_size)
            # Family art beats a clipped word: at 30 px the legibility floor
            # turns "DAG" into "D…", while the icon matches the row art the
            # player is already reading.
            head = icon
            if head is None:
                name = self._filter_chip_label(
                    chip, label_font, chip_rect.width - 4)
                head = label_font.render(name, True, fg)
            total_h = head.get_height() + count_surf.get_height() - 1
            top = chip_rect.centery - total_h // 2
            self.window.blit(head, head.get_rect(
                midtop=(chip_rect.centerx, top)))
            self.window.blit(count_surf, count_surf.get_rect(
                midtop=(chip_rect.centerx, top + head.get_height() - 1)))
            # Hit rects meet in the middle of the gap so the strip has no
            # dead zones, but never overlap a neighbour.
            self._filter_chip_rects.append(
                (chip['key'], chip_rect.inflate(gap, 0)))
            x = chip_rect.right + gap

    @classmethod
    def _gamble_pip_size(cls, rect: pygame.Rect) -> int:
        return max(4, int(rect.height * 0.14))

    @classmethod
    def _gamble_pip_span(cls, rect: pygame.Rect) -> int:
        """Horizontal room the pip cluster needs on the strip's right edge."""
        size = cls._gamble_pip_size(rect)
        gap = size * 2 + 4
        return 10 + size + gap * (cls.GAMBLE_PER_BATTLE_LIMIT - 1) + size

    def _draw_gamble_pips(self, rect: pygame.Rect, game) -> None:
        """Three diamond pips, top-right of the strip: remaining gambles.

        Gold diamonds = gambles still available this battle; hollow dim
        diamonds = spent. The final remaining pip pulses ember-orange so
        the last gamble reads as a moment, not a stat.
        """
        if game is None:
            return
        used, _rounds = self._gamble_counts_state(game)
        used = max(0, min(self.GAMBLE_PER_BATTLE_LIMIT, used))
        remaining = self.GAMBLE_PER_BATTLE_LIMIT - used
        size = self._gamble_pip_size(rect)
        gap = size * 2 + 4
        cy = rect.y + 6 + size
        cx = rect.right - 10 - size
        now = pygame.time.get_ticks()
        for i in range(self.GAMBLE_PER_BATTLE_LIMIT):
            # Right-most pip is the first spent.
            is_available = i >= used
            points = [(cx, cy - size), (cx + size, cy),
                      (cx, cy + size), (cx - size, cy)]
            if is_available:
                color = (250, 226, 130)
                if remaining == 1:
                    phase = (now % 900) / 900.0
                    pulse = 1.0 - abs(0.5 - phase) * 2.0
                    color = (255, 170 + int(56 * pulse), 96 + int(34 * pulse))
                pygame.draw.polygon(self.window, color, points)
                pygame.draw.polygon(self.window, (120, 96, 52), points, 1)
            else:
                pygame.draw.polygon(self.window, (78, 66, 50), points, 1)
            cx -= gap

    def _gamble_status_for_strip(self, game):
        """Return (text, state) where state is 'ready'|'last'|'used'|'limit'|'idle'."""
        if game is None:
            return ('', 'idle')
        used, used_rounds = self._gamble_counts_state(game)
        try:
            current_round = int(getattr(game, 'battle_round', 0) or 0)
        except (TypeError, ValueError):
            current_round = 0
        round_used = current_round in used_rounds
        if round_used:
            return (
                ('Gamble used', 'used')
                if settings.TOUCH_TARGET_MIN > 0 else
                ('Already gambled', 'used')
            )
        if used >= self.GAMBLE_PER_BATTLE_LIMIT:
            return (
                (f'Limit {used}/{self.GAMBLE_PER_BATTLE_LIMIT}', 'limit')
                if settings.TOUCH_TARGET_MIN > 0 else
                (f'Gamble limit reached ({used}/{self.GAMBLE_PER_BATTLE_LIMIT})', 'limit')
            )
        if used == self.GAMBLE_PER_BATTLE_LIMIT - 1:
            return (
                ('Last gamble!', 'last')
                if settings.TOUCH_TARGET_MIN > 0 else
                ('Last gamble of the battle!', 'last')
            )
        return (
            ('Gamble ready', 'ready')
            if settings.TOUCH_TARGET_MIN > 0 else
            ('Gamble ready this round', 'ready')
        )

    def _draw_result_banner(self, list_rect: pygame.Rect):
        """Float the sticky banner over the bottom of the hand list.

        The banner used to own a layout band, so every confirmation prompt
        stole a tactic row from an already short list.  As an overlay it
        costs nothing permanent and disappears on the next tap.
        """
        self._banner_rect = None
        if not self._result_banner or list_rect.height <= 0:
            return
        banner = self._result_banner
        text = banner.get('text', '')
        color = banner.get('color', _TEXT_PRIMARY)
        sub = settings.get_font(max(settings.FS_CONQUER_META, int(settings.FS_TINY * 0.8)))
        avail = max(1, list_rect.width - 16)
        base_size = max(settings.FS_CONQUER_LABEL, int(settings.FS_SMALL * 0.95))
        min_size = max(settings.FS_CONQUER_META, int(settings.FS_TINY * 0.72))
        max_h = max(24, int(list_rect.height * 0.75))
        font = settings.get_font(min_size, bold=True)
        lines = self._wrap_text(text, font, avail)
        for size in range(base_size, min_size - 1, -1):
            candidate = settings.get_font(size, bold=True)
            candidate_lines = self._wrap_text(text, candidate, avail)
            needed = (5 + len(candidate_lines) * (candidate.get_height() + 1)
                      + sub.get_height() + 7)
            if needed <= max_h:
                font = candidate
                lines = candidate_lines
                break
        height = min(max_h,
                     5 + len(lines) * (font.get_height() + 1)
                     + sub.get_height() + 7)
        rect = pygame.Rect(list_rect.x, list_rect.bottom - height,
                           list_rect.width, height)
        bg = pygame.Surface(rect.size, pygame.SRCALPHA)
        bg.fill((58, 44, 28, 244))
        self.window.blit(bg, rect.topleft)
        pygame.draw.rect(self.window, color, rect, 2, border_radius=4)
        y = rect.y + 4
        for line in lines:
            if y + font.get_height() > rect.bottom - sub.get_height() - 4:
                break
            surf = font.render(line, True, color)
            self.window.blit(surf, (rect.x + 8, y))
            y += font.get_height() + 1
        hint = sub.render('(tap to dismiss)' if settings.TOUCH_TARGET_MIN > 0
                          else '(click anywhere to dismiss)', True, _TEXT_MUTED)
        self.window.blit(hint, (rect.x + 8, rect.bottom - sub.get_height() - 3))
        self._banner_rect = rect

    # -- hand list
    def _draw_hand_list(self, rect: pygame.Rect, cell_h: int, cells_visible: int):
        previous_clip = self.window.get_clip()
        self.window.set_clip(rect)
        items = self._visible_hand_items()
        self._clamp_scroll()
        self._cell_rects = []
        self._cell_move_ids = []
        self._cell_kinds = []
        self._cell_groups = []
        self._hovered_id = None
        if not items:
            empty_font = settings.get_font(max(settings.FS_CONQUER_LABEL, int(settings.FS_SMALL * 0.9)))
            label = ('— hand empty —' if not self._hand_moves()
                     else '— none in this family —')
            t = empty_font.render(label, True, _TEXT_MUTED)
            self.window.blit(t, t.get_rect(center=rect.center))
            self._scroll_up_rect = None
            self._scroll_down_rect = None
            self.window.set_clip(previous_clip)
            return
        # Spell-removed ghost cells take the top slots for their TTL.
        ghosts = list(self._removed_ghosts.items())
        list_top = rect.top + len(ghosts) * cell_h
        # Pixel offset lets a touch drag follow the finger instead of
        # jumping a whole row at a time.
        offset = int(self._scroll_px) % max(1, cell_h)
        first_index = int(self._scroll_px) // max(1, cell_h)
        visible_count = max(1, min(cells_visible, rect.height // max(1, cell_h)))
        visible = items[first_index:first_index + visible_count + 1]
        self._draw_scroll_affordance(
            rect, first_index, visible_count, len(items))

        font = settings.get_font(max(settings.FS_CONQUER_LABEL, int(settings.FS_SMALL * 0.95)), bold=True)
        chip_font = settings.get_font(max(settings.FS_CONQUER_META, int(settings.FS_TINY * 0.85)), bold=True)
        mouse_pos = pygame.mouse.get_pos()
        y = rect.top
        now_ms = pygame.time.get_ticks()
        for mid, ghost in ghosts:
            if y + cell_h > rect.bottom + 2:
                break
            ghost_move = ghost.get('move') or {}
            ghost_rect = pygame.Rect(rect.left, y, rect.width, cell_h - 2)
            self._draw_removed_ghost_cell(ghost_rect, ghost_move, font, chip_font,
                                          expires_at=ghost.get('expires_at', now_ms))
            y += cell_h
        y = list_top - offset
        for item in visible:
            if y >= rect.bottom:
                break
            cell_rect = pygame.Rect(rect.left, y, rect.width, cell_h - 2)
            move = item['move']
            hovered = cell_rect.collidepoint(mouse_pos)
            if hovered:
                self._hovered_id = int(move.get('id') or 0)
            self._draw_hand_cell(cell_rect, move, font, chip_font, hovered=hovered)
            # A row scrolled halfway out of view must not accept taps meant
            # for its neighbour: only register rows that are fully visible.
            if cell_rect.top >= rect.top - 1 and cell_rect.bottom <= rect.bottom + 2:
                self._cell_rects.append(cell_rect)
                self._cell_move_ids.append(int(move.get('id') or 0))
                self._cell_kinds.append('move')
                self._cell_groups.append(item['group'])
            y += cell_h
        # A row peeking out of the bottom edge is the clearest "there is more
        # below" cue on touch, but a hard clip reads as a glitch — fade it.
        if first_index + visible_count < len(items):
            fade_h = min(14, max(4, rect.height // 12))
            fade = pygame.Surface((rect.width, fade_h), pygame.SRCALPHA)
            for row in range(fade_h):
                alpha = int(190 * (row + 1) / float(fade_h))
                pygame.draw.line(fade, (24, 18, 14, alpha),
                                 (0, row), (rect.width, row))
            self.window.blit(fade, (rect.left, rect.bottom - fade_h))
        # Filtered view: say how much of the hand is out of sight, so an
        # empty-looking rail never reads as "that's all you have".
        hidden = len(self._hand_moves()) - len(items)
        if self._active_family is not None and hidden > 0 and y < rect.bottom - 4:
            hint_font = settings.get_font(
                max(settings.FS_CONQUER_META, int(settings.FS_TINY * 0.78)))
            hint = hint_font.render(f'+{hidden} more in ALL', True, _TEXT_MUTED)
            hint_rect = hint.get_rect(
                midtop=(rect.centerx, min(y + 4, rect.bottom - hint.get_height() - 2)))
            self.window.blit(hint, hint_rect)
        # Drag ghost (#8b) — drawn last so it floats over cells.
        if self._drag_active and self._drag_origin_id is not None and self._drag_pos:
            origin_move = next((m for m in self._hand_moves()
                                if int(m.get('id') or 0) == self._drag_origin_id), None)
            if origin_move is not None:
                self._draw_drag_ghost(origin_move, self._drag_pos)
        self.window.set_clip(previous_clip)

    def _draw_scroll_affordance(self, rect: pygame.Rect, first_index: int,
                                visible_count: int, total: int) -> None:
        """Show where the list is.

        Desktop keeps clickable arrows.  Touch gets a passive scrollbar
        instead: an arrow drawn over the first/last row inflates into a
        33 px hit target that swallowed taps meant for that tactic, and
        grab-scrolling has made it redundant.
        """
        self._scroll_up_rect = None
        self._scroll_down_rect = None
        if total <= visible_count:
            return
        if settings.TOUCH_TARGET_MIN > 0:
            track = pygame.Rect(rect.right - 5, rect.top + 2, 3,
                                max(6, rect.height - 4))
            pygame.draw.rect(self.window, (70, 58, 42), track,
                             border_radius=2)
            thumb_h = max(12, int(track.height * visible_count / float(total)))
            span = max(1, total - visible_count)
            travel = max(0, track.height - thumb_h)
            offset = int(travel * min(1.0, first_index / float(span)))
            thumb = pygame.Rect(track.x, track.y + offset, track.width, thumb_h)
            pygame.draw.rect(self.window, (196, 154, 68), thumb,
                             border_radius=2)
            return
        if first_index > 0:
            up = pygame.Rect(rect.right - 18, rect.top + 2, 14, 12)
            pygame.draw.polygon(self.window, _TEXT_PRIMARY,
                                [(up.centerx, up.top), (up.left, up.bottom),
                                 (up.right, up.bottom)])
            self._scroll_up_rect = up
        if first_index + visible_count < total:
            dn = pygame.Rect(rect.right - 18, rect.bottom - 14, 14, 12)
            pygame.draw.polygon(self.window, _TEXT_PRIMARY,
                                [(dn.centerx, dn.bottom), (dn.left, dn.top),
                                 (dn.right, dn.top)])
            self._scroll_down_rect = dn

    def _draw_drag_ghost(self, move: Dict[str, Any], pos: tuple) -> None:
        size = 28
        x, y = pos
        ghost_rect = pygame.Rect(x - size // 2, y - size // 2, size, size)
        bg = pygame.Surface(ghost_rect.size, pygame.SRCALPHA)
        bg.fill((52, 40, 30, 210))
        self.window.blit(bg, ghost_rect.topleft)
        pygame.draw.rect(self.window, _SELECTED_RGBA, ghost_rect, 2, border_radius=4)
        try:
            (glow_cache, icon_cache, frame_cache, suit_icon_cache,
             icon_font) = self._parent._conquer_battle_move_icon_assets(size - 6)
            draw_battle_move_icon(
                self.window, ghost_rect.centerx, ghost_rect.centery,
                move.get('family_name', ''),
                move.get('suit', ''),
                self._power(move),
                glow_cache, icon_cache, frame_cache, suit_icon_cache,
                icon_font, size - 6,
                hovered=False, is_used=False,
                suit_b=move.get('suit_b'),
            )
        except Exception:
            pass

    def _draw_removed_ghost_cell(self, rect: pygame.Rect, move: Dict[str, Any],
                                  font, chip_font, *, expires_at: int) -> None:
        """Render a strike-through ghost cell for a spell-removed move.

        Fades alpha as the TTL approaches zero so the visual transition is
        smooth (#round4 spell sync).
        """
        previous_clip = self.window.get_clip()
        self.window.set_clip(rect)
        now = pygame.time.get_ticks()
        remaining = max(0, expires_at - now)
        # Fade ramp over the last 800 ms.
        ramp_ms = 800
        if remaining < ramp_ms:
            alpha_factor = max(0.0, remaining / ramp_ms)
        else:
            alpha_factor = 1.0
        bg_alpha = int(170 * alpha_factor)
        bg = pygame.Surface(rect.size, pygame.SRCALPHA)
        bg.fill((58, 22, 22, bg_alpha))
        self.window.blit(bg, rect.topleft)
        pygame.draw.rect(self.window, (180, 70, 70, int(220 * alpha_factor)),
                         rect, 1, border_radius=4)
        # Move icon (greyscale-ish red tint via low alpha).
        size = max(20, rect.height - 8)
        try:
            (glow_cache, icon_cache, frame_cache, suit_icon_cache,
             icon_font) = self._parent._conquer_battle_move_icon_assets(size)
            icon_surf = pygame.Surface((size, size), pygame.SRCALPHA)
            draw_battle_move_icon(
                icon_surf, size // 2, size // 2,
                move.get('family_name', ''),
                move.get('suit', ''),
                self._power(move),
                glow_cache, icon_cache, frame_cache, suit_icon_cache,
                icon_font, size,
                hovered=False, is_used=False,
                suit_b=move.get('suit_b'),
            )
            icon_surf.set_alpha(int(180 * alpha_factor))
            self.window.blit(icon_surf, (rect.left + 6, rect.centery - size // 2))
        except Exception:
            pass
        # Trailing tag "removed by spell" rendered first so we can size the
        # move name to fit the remaining horizontal space without overlap.
        tag = chip_font.render('removed by spell', True, (240, 180, 180))
        tag.set_alpha(int(220 * alpha_factor))
        tag_x = rect.right - tag.get_width() - 6
        tag_y = rect.centery - tag.get_height() // 2
        # Move name with strike-through, clipped so it never overlaps the tag.
        name = str(move.get('family_name') or 'Move')
        text_x = rect.left + 6 + max(20, rect.height - 8) + 8
        name_max_w = max(0, tag_x - 6 - text_x)
        name_fit = self._parent._fit_text(name, font, name_max_w) if name_max_w > 0 else ''
        if name_fit:
            name_surf = font.render(name_fit, True, (220, 170, 170))
            name_surf.set_alpha(int(220 * alpha_factor))
            text_y = rect.centery - name_surf.get_height() // 2
            self.window.blit(name_surf, (text_x, text_y))
            # Strike-through line covering only the rendered name.
            line_y = text_y + name_surf.get_height() // 2
            pygame.draw.line(self.window, (220, 90, 90, int(255 * alpha_factor)),
                             (text_x - 2, line_y),
                             (text_x + name_surf.get_width() + 2, line_y), 2)
        self.window.blit(tag, (tag_x, tag_y))
        self.window.set_clip(previous_clip)

    def _draw_hand_cell(self, rect: pygame.Rect, move: Dict[str, Any], font, chip_font,
                        *, hovered: bool = False):
        previous_clip = self.window.get_clip()
        self.window.set_clip(rect)
        is_selected = move.get('id') == self._selected_id
        is_partner = move.get('id') == self._combine_partner_id and self._combine_pending
        pending = self._server_action_pending or {}
        try:
            is_pending = int(pending.get('move_id') or -1) == int(move.get('id') or -2)
        except (TypeError, ValueError):
            is_pending = False
        bg_col = (_SELECTED_BG_RGBA if is_selected
                  else (38, 32, 25, 224) if hovered
                  else (32, 24, 18, 200))
        bg = pygame.Surface(rect.size, pygame.SRCALPHA)
        bg.fill(bg_col)
        self.window.blit(bg, rect.topleft)
        border_col = (_SELECTED_RGBA if is_selected
                      else (130, 200, 250) if is_pending or is_partner
                      else (190, 178, 120) if hovered
                      else _BORDER_RGBA)
        pygame.draw.rect(
            self.window, border_col, rect,
            3 if is_selected else 2, border_radius=4)
        if is_selected:
            # Selection owns a dedicated teal language: dark tint, stronger
            # border, and a solid leading bar. Gold remains reserved for
            # strongest/new-card feedback.
            pygame.draw.rect(
                self.window, _SELECTED_RGBA,
                pygame.Rect(rect.left + 2, rect.top + 4, 4, rect.height - 8),
                border_radius=2,
            )
        if is_pending:
            phase = (pygame.time.get_ticks() % 600) / 600.0
            pulse = 110 + int(100 * (1.0 - abs(0.5 - phase) * 2.0))
            pending_surf = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(
                pending_surf, (130, 200, 250, pulse),
                pending_surf.get_rect().inflate(-4, -4), 2,
                border_radius=4,
            )
            self.window.blit(pending_surf, rect.topleft)

        # New-move glow (#round5) — stronger pulse + outer halo + corner
        # NEW ribbon for ``NEW_MOVE_GLOW_MS`` after a new move appears.
        mid = int(move.get('id') or 0)
        glow_until = self._new_move_glow_until.get(mid)
        now = pygame.time.get_ticks()
        if glow_until and glow_until > now:
            phase = (now % 700) / 700.0
            pulse = 1.0 - abs(0.5 - phase) * 2.0
            # Last 600 ms fade ramp so the glow gracefully exits.
            remaining = max(0, glow_until - now)
            ramp = max(0.25, min(1.0, remaining / 600.0)) if remaining < 600 else 1.0
            alpha = int((140 + 115 * pulse) * ramp)
            # Outer halo — drawn larger for a more eye-catching effect.
            halo = pygame.Surface((rect.width + 8, rect.height + 8), pygame.SRCALPHA)
            pygame.draw.rect(halo, (250, 226, 130, max(0, alpha // 2)),
                             halo.get_rect(), 4, border_radius=6)
            self.window.blit(halo, (rect.left - 4, rect.top - 4))
            # Inner thick border pulse.
            glow_surf = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(glow_surf, (250, 226, 130, alpha),
                             glow_surf.get_rect().inflate(-2, -2), 4,
                             border_radius=4)
            self.window.blit(glow_surf, rect.topleft)
            # NEW ribbon top-right.
            ribbon_font = settings.get_font(max(settings.FS_CONQUER_META, int(settings.FS_TINY * 0.7)), bold=True)
            ribbon_surf = ribbon_font.render('NEW', True, (24, 18, 12))
            ribbon_rect = ribbon_surf.get_rect()
            ribbon_rect.inflate_ip(8, 4)
            ribbon_rect.topright = (rect.right - 4, rect.top + 2)
            ribbon_bg = pygame.Surface(ribbon_rect.size, pygame.SRCALPHA)
            pygame.draw.rect(ribbon_bg, (250, 226, 130, int(245 * ramp)),
                             ribbon_bg.get_rect(),
                             border_radius=ribbon_rect.height // 2)
            self.window.blit(ribbon_bg, ribbon_rect.topleft)
            self.window.blit(ribbon_surf, ribbon_surf.get_rect(center=ribbon_rect.center))

        # Combine-pulse (#8b): when a single dagger is selected, all
        # eligible partner daggers in the rail pulse blue.
        sel = self._selected_move()
        if (sel is not None and sel.get('id') != mid
                and self._is_single_dagger(sel)
                and self._is_single_dagger(move)
                and self._can_combine(sel, move)):
            phase = (now % 800) / 800.0
            pulse = 1.0 - abs(0.5 - phase) * 2.0
            alpha = int(80 + 130 * pulse)
            pulse_surf = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(pulse_surf, (130, 200, 250, alpha),
                             pulse_surf.get_rect().inflate(-2, -2), 3,
                             border_radius=4)
            self.window.blit(pulse_surf, rect.topleft)

        # Icon (left)
        icon_scale = 0.68 if settings.TOUCH_TARGET_MIN > 0 else 0.78
        icon_size = max(20, int(rect.height * icon_scale))
        # Compute gamble-flip squash factor (#8c). When the cell matches
        # the active anim, horizontally squash the icon over the duration.
        flip_scale_x = 1.0
        anim = self._gamble_anim
        if anim and int(anim.get('move_id') or -1) == mid:
            now_ms = pygame.time.get_ticks()
            elapsed = now_ms - int(anim.get('started_at', now_ms))
            duration = max(1, int(anim.get('duration', 1000)))
            if elapsed >= duration:
                self._gamble_anim = None
            else:
                # Three squash cycles across the duration.
                import math
                t = elapsed / duration
                flip_scale_x = abs(math.cos(t * math.pi * 3.0))
                flip_scale_x = max(0.08, flip_scale_x)
        try:
            glow_cache, icon_cache, frame_cache, suit_icon_cache, icon_font = (
                self._parent._conquer_battle_move_icon_assets(icon_size))
            cx = rect.left + icon_size // 2 + 6
            cy = rect.centery
            if flip_scale_x < 0.999:
                # Render icon onto a scratch surface then scale X for the
                # flip effect.
                scratch = pygame.Surface((icon_size, icon_size), pygame.SRCALPHA)
                draw_battle_move_icon(
                    scratch, icon_size // 2, icon_size // 2,
                    move.get('family_name', ''),
                    move.get('suit', ''),
                    self._power(move),
                    glow_cache, icon_cache, frame_cache, suit_icon_cache,
                    icon_font, icon_size,
                    hovered=False, is_used=False,
                    suit_b=move.get('suit_b'),
                )
                new_w = max(1, int(icon_size * flip_scale_x))
                squashed = pygame.transform.smoothscale(
                    scratch, (new_w, icon_size))
                self.window.blit(squashed, squashed.get_rect(center=(cx, cy)))
            else:
                draw_battle_move_icon(
                    self.window, cx, cy,
                    move.get('family_name', ''),
                    move.get('suit', ''),
                    self._power(move),
                    glow_cache, icon_cache, frame_cache, suit_icon_cache,
                    icon_font, icon_size,
                    hovered=False,
                    is_used=False,
                    suit_b=move.get('suit_b'),
                )
        except Exception:
            pygame.draw.rect(self.window, (90, 70, 50),
                             pygame.Rect(rect.left + 4, rect.top + 4,
                                         icon_size, icon_size), 0, border_radius=3)

        # Name + rank chip (right of icon).  The battle-move icon already
        # carries the suit marker, so repeating it here only adds visual noise.
        text_gap = 14 if settings.TOUCH_TARGET_MIN > 0 else 18
        text_x = rect.left + icon_size + text_gap
        name = move.get('family_name', '?')
        if self._is_double_dagger(move):
            name = 'Double Dagger'
        elif (self._active_family == 'Call' and name.startswith('Call ')):
            # The chip already says CALL; dropping the prefix is what stops
            # "Call Villager" and "Call Military" from both clipping to
            # "Call ..." on a 123 px rail.
            name = name[len('Call '):]

        # Power is already rendered inside the battle-move icon itself, so
        # we omit the duplicate right-edge number to free horizontal
        # space for the move name + rank chip (#round5).
        # The mobile check is only 14 px wide. Keep a small safety gap without
        # needlessly truncating short family names such as "Dagger".
        selected_reserve = (
            15 if is_selected and settings.TOUCH_TARGET_MIN > 0
            else 19 if is_selected
            else 0
        )
        max_text_w = max(24, rect.right - text_x - 8 - selected_reserve)

        name_surf = font.render(self._fit_text(name, font, max_text_w), True, _TEXT_PRIMARY)
        name_y = rect.top + (4 if settings.TOUCH_TARGET_MIN > 0 else 6)
        self.window.blit(name_surf, (text_x, name_y))

        # Rank + suit pip.  A filtered list is mostly one family, so the name
        # repeats down the column and the rank/suit pair becomes the thing
        # the player actually reads to tell two rows apart.
        chip_text = str(move.get('rank', '?'))
        suit = move.get('suit')
        suit_b = move.get('suit_b')
        if suit:
            chip_text = f'{chip_text} {suit}'
        if suit_b and suit_b != suit:
            chip_text = f'{chip_text} {suit_b}'
        chip_surf = render_suit_text(
            fit_suit_text(chip_text, chip_font, max_text_w),
            chip_font,
            _TEXT_SECONDARY,
        )
        chip_y = (rect.bottom - chip_surf.get_height() - 5
                  if settings.TOUCH_TARGET_MIN > 0
                  else name_y + name_surf.get_height() + 1)
        self.window.blit(chip_surf, (text_x, chip_y))

        # Strongest-move badge (#8d). Draw the sparkle with primitives: the
        # mobile/browser font does not reliably contain the old ★ glyph and
        # could render a missing-character box in this corner.
        if mid == self._strongest_move_id():
            self._draw_strongest_marker(self.window, rect)

        glow_active = bool(glow_until and glow_until > now)
        if is_selected and not glow_active:
            # Vector checkmark: browser fonts are not guaranteed to contain a
            # reliable check glyph at this scale.
            center = (rect.right - 10, rect.top + 11)
            pygame.draw.circle(self.window, (18, 48, 46), center, 7)
            pygame.draw.circle(self.window, _SELECTED_RGBA, center, 7, 2)
            pygame.draw.lines(
                self.window, _SELECTED_RGBA, False,
                [(center[0] - 3, center[1]),
                 (center[0] - 1, center[1] + 3),
                 (center[0] + 4, center[1] - 3)],
                2,
            )

        # Combine-flow position indicator (#3.2). Show "1/2" on the
        # origin and "2/2" on the partner so the player understands the
        # multi-step combine action without having to read the action
        # tray hint.
        if self._combine_pending:
            slot_label = None
            if is_selected:
                slot_label = '1/2'
            elif is_partner:
                slot_label = '2/2'
            if slot_label:
                slot_font = settings.get_font(
                    max(settings.FS_CONQUER_META, int(settings.FS_TINY * 0.85)), bold=True)
                slot_surf = slot_font.render(slot_label, True, (130, 200, 250))
                pad_x, pad_y = 4, 1
                box = pygame.Rect(
                    rect.right - slot_surf.get_width() - pad_x * 2 - 4,
                    rect.bottom - slot_surf.get_height() - pad_y * 2 - 4,
                    slot_surf.get_width() + pad_x * 2,
                    slot_surf.get_height() + pad_y * 2,
                )
                bg = pygame.Surface(box.size, pygame.SRCALPHA)
                bg.fill((20, 30, 50, 200))
                self.window.blit(bg, box.topleft)
                pygame.draw.rect(self.window, (130, 200, 250), box, 1,
                                 border_radius=3)
                self.window.blit(slot_surf,
                                 (box.left + pad_x, box.top + pad_y))

        # Ghost overlay — a tactic that the server has marked spell-purged
        # but the local spell replay is still showing.  Dim heavily and
        # mark with a "swirl" glyph so the player understands it's
        # transient and non-interactive.
        if self._is_ghost_move(move):
            ghost_overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
            ghost_overlay.fill((10, 8, 6, 150))
            self.window.blit(ghost_overlay, rect.topleft)
            # Strikethrough line + corner glyph make it obvious this entry
            # has been removed by a spell and is non-interactive.
            try:
                line_y = rect.centery
                line_color = (190, 110, 110, 220)
                line_surf = pygame.Surface((rect.width - 8, 2), pygame.SRCALPHA)
                line_surf.fill(line_color)
                self.window.blit(line_surf, (rect.left + 4, line_y - 1))
            except Exception:
                pass
            try:
                glyph_font = settings.get_font(
                    max(settings.FS_CONQUER_LABEL, int(settings.FS_TINY * 1.1)), bold=True)
                glyph = glyph_font.render('✺', True, (170, 200, 240))
                self.window.blit(
                    glyph,
                    (rect.right - glyph.get_width() - 6, rect.top + 4),
                )
            except Exception:
                pass

        self.window.set_clip(previous_clip)

    @staticmethod
    def _draw_strongest_marker(surface: pygame.Surface,
                               rect: pygame.Rect) -> None:
        """Draw a font-independent sparkle badge in a tactic-row corner."""
        outer = 5 if settings.TOUCH_TARGET_MIN > 0 else 6
        inner = max(2, outer // 2)
        cx = rect.left + outer + 3
        cy = rect.top + outer + 3
        pygame.draw.circle(surface, (30, 22, 14), (cx, cy), outer + 2)
        pygame.draw.circle(surface, (126, 94, 42), (cx, cy), outer + 2, 1)
        points = [
            (cx, cy - outer),
            (cx + inner, cy - inner),
            (cx + outer, cy),
            (cx + inner, cy + inner),
            (cx, cy + outer),
            (cx - inner, cy + inner),
            (cx - outer, cy),
            (cx - inner, cy - inner),
        ]
        pygame.draw.polygon(surface, (250, 220, 110), points)
        pygame.draw.circle(surface, (255, 242, 170), (cx, cy), 1)

    # -- selected detail
    def _draw_selected_detail(self, rect: pygame.Rect):
        pygame.draw.rect(self.window, (24, 18, 14), rect, 0, border_radius=4)
        pygame.draw.rect(self.window, _BORDER_RGBA, rect, 1, border_radius=4)
        sel = self._selected_move()
        title_font = settings.get_font(max(settings.FS_CONQUER_LABEL, int(settings.FS_SMALL * 1.0)), bold=True)
        body_font = settings.get_font(max(settings.FS_CONQUER_LABEL, int(settings.FS_TINY * 0.95)))
        if sel is None:
            t = body_font.render('Select a tactic', True, _TEXT_MUTED)
            self.window.blit(t, (rect.left + 8, rect.top + 6))
            return
        name = sel.get('family_name', '?')
        if self._is_double_dagger(sel):
            name = 'Double Dagger'
        ts = title_font.render(
            self._fit_text(name, title_font, rect.width - 16), True, _TEXT_PRIMARY)
        self.window.blit(ts, (rect.left + 8, rect.top + 6))
        # Suit • rank • power line
        suit_a = sel.get('suit', '?')
        suit_b = sel.get('suit_b')
        rank = sel.get('rank', '?')
        if settings.TOUCH_TARGET_MIN > 0:
            line = f"{suit_a}{('+' + suit_b) if suit_b else ''} {rank}  P{self._power(sel)}"
        else:
            line = f"{suit_a}{('+' + suit_b) if suit_b else ''} • {rank} • Power {self._power(sel)}"
        bs = render_suit_text(
            fit_suit_text(line, body_font, rect.width - 16),
            body_font,
            _TEXT_SECONDARY,
        )
        self.window.blit(bs, (rect.left + 8, rect.top + 6 + ts.get_height() + 2))
        # Gamble stake hint — only when a gamble is actually available for
        # this tactic and there is vertical room for a third line.
        stake_y = rect.top + 6 + ts.get_height() + 2 + bs.get_height() + 2
        if (not self._gamble_block_reason()
                and stake_y + body_font.get_height() <= rect.bottom - 2):
            stake = body_font.render(
                self._fit_text('Gamble: burn this → draw 2 random',
                               body_font, rect.width - 16),
                True, (196, 176, 120))
            self.window.blit(stake, (rect.left + 8, stake_y))

    # -- action tray
    def _action_specs(self) -> List[tuple]:
        """Return list of ``(key, label[, disabled_reason])`` for currently-applicable actions.

        Round 13: context-only display — disabled buttons are normally
        hidden, but the Gamble button is kept visible-and-disabled with a
        hover tooltip when the *reason* it is blocked is information the
        player needs (limit hit, already gambled this round).
        Skip is shown only when the hand is empty *and* it's the player's
        battle turn (the player has nothing to play). Otherwise the
        player must spend a tactic.
        """
        sel = self._selected_move()
        my_turn = self._is_my_battle_turn()
        hand_empty = not self._hand_moves()
        specs: List[tuple] = []
        if my_turn and hand_empty:
            specs.append((ACTION_SKIP, 'Skip'))
            return specs
        if not sel:
            return specs
        if my_turn:
            specs.append((ACTION_PLAY, 'Play'))
        gamble_reason = self._gamble_block_reason()
        if not gamble_reason:
            if sel is not None and self._gamble_armed_for(sel.get('id')):
                gamble_label = 'Sure?'
            else:
                # The mobile top strip that used to carry the gamble budget
                # is now the filter strip, so the remaining count rides on
                # the button that spends it.
                gamble_label = 'Gamble'
                if settings.TOUCH_TARGET_MIN > 0:
                    used, _rounds = self._gamble_counts_state(
                        getattr(self._parent.state, 'game', None))
                    remaining = max(0, self.GAMBLE_PER_BATTLE_LIMIT - used)
                    gamble_label = f'Gamble ×{remaining}'
            specs.append((ACTION_GAMBLE, gamble_label))
        elif gamble_reason not in ('Not your battle turn',
                                   'Gamble only during active battle rounds',
                                   'No active game'):
            # Surface meaningful gates (limit hit, already gambled this
            # round) as a disabled button with a hover tooltip.
            specs.append((ACTION_GAMBLE, 'Gamble', gamble_reason))
        if self._is_single_dagger(sel) and self._best_combine_partner(sel) is not None:
            specs.append((ACTION_COMBINE, 'Combine'))
        if self._is_double_dagger(sel):
            specs.append((ACTION_DISMANTLE, 'Dismantle'))
        return specs

    def _normalized_action_specs(self, specs: Optional[List[tuple]] = None) -> List[tuple]:
        specs = self._action_specs() if specs is None else specs
        block_reason = ''
        try:
            reason_getter = getattr(self._parent, 'conquer_action_block_reason', None)
            if callable(reason_getter):
                block_reason = str(reason_getter() or '')
            else:
                flight_check = getattr(self._parent, 'is_tactic_flight_active', None)
                if callable(flight_check) and flight_check():
                    block_reason = 'Tactic in flight…'
        except Exception:
            block_reason = ''
        if block_reason:
            return [
                (spec[0], spec[1], spec[2] if len(spec) > 2 and spec[2] else block_reason)
                for spec in specs
            ]
        return [
            (spec[0], spec[1], spec[2] if len(spec) > 2 else '')
            for spec in specs
        ]

    def _reserved_action_tray_height(self, width: int) -> int:
        """Worst-case tray height, independent of the current selection.

        Sizing the tray from the *current* actions made the hand list
        breathe: selecting a tactic added a row of buttons and pushed a
        tactic out of view — including, at the bottom of the list, the one
        just selected.  Reserving the maximum keeps the viewport still.
        """
        target_h = max(30, settings.TOUCH_COMPACT_MIN)
        # The richest tray is Play + Gamble + Combine/Dismantle: one primary
        # plus two secondaries (Combine and Dismantle are mutually
        # exclusive — single vs. double Dagger).
        worst_case = [
            (ACTION_PLAY, 'Play', ''),
            (ACTION_GAMBLE, 'Gamble', ''),
            (ACTION_COMBINE, 'Combine', ''),
        ]
        if self._action_tray_uses_column_layout(width, worst_case):
            row_h = max(28, min(target_h, int(width * 0.24)))
            return row_h * len(worst_case) + 5 * (len(worst_case) - 1) + 4
        if self._action_tray_uses_stacked_layout(width, worst_case):
            return target_h * 2 + 9
        return target_h + 4

    @staticmethod
    def _action_tray_uses_column_layout(width: int, specs: List[tuple]) -> bool:
        has_primary = any(spec[0] in _PRIMARY_ACTION_KEYS for spec in specs)
        secondary_count = sum(
            1 for spec in specs if spec[0] not in _PRIMARY_ACTION_KEYS)
        return has_primary and secondary_count >= 3 and width < 130

    @staticmethod
    def _action_tray_uses_stacked_layout(width: int, specs: List[tuple]) -> bool:
        has_primary = any(spec[0] in _PRIMARY_ACTION_KEYS for spec in specs)
        has_secondary = any(spec[0] not in _PRIMARY_ACTION_KEYS for spec in specs)
        return has_primary and has_secondary and width < 220

    @staticmethod
    def _action_label_candidates(key: str, label: str) -> tuple:
        if key == ACTION_GAMBLE:
            # 'Gamble ×2' → 'Gamble' → 'Swap' as the button narrows.
            base = label.split(' ×')[0]
            return (label, base, 'Swap') if base != label else (label, 'Swap')
        if key == ACTION_COMBINE:
            return (label, 'Join')
        if key == ACTION_DISMANTLE:
            return (label, 'Split')
        return (label,)

    @staticmethod
    def _fit_action_label(key: str, label: str, max_width: int,
                          base_size: int, min_size: int = 7):
        max_width = max(1, int(max_width))
        for candidate in ConquerTacticsRail._action_label_candidates(key, label):
            for font_size in range(max(min_size, int(base_size)), min_size - 1, -1):
                font = settings.get_font(font_size, bold=True)
                if font.size(candidate)[0] <= max_width:
                    return font, candidate
        font = settings.get_font(min_size, bold=True)
        return font, ConquerTacticsRail._fit_text(label, font, max_width)

    @staticmethod
    def _action_tooltip_text(key: str, label: str) -> str:
        if key == ACTION_PLAY:
            return 'Commit this tactic to the current round.'
        if key == ACTION_GAMBLE:
            # Odds mirror the server's uniform draw: 8 ranks × 4 suits,
            # ranks 7–10 → Dagger (50%), J/Q/K/A → one call family each.
            return ('Burn this tactic for 2 random ones · '
                    '50% Dagger · 12.5% each Call/Block.')
        if key == ACTION_COMBINE:
            return 'Join with your strongest same-colour Dagger.'
        if key == ACTION_DISMANTLE:
            return 'Split this Double Dagger back into two tactics.'
        if key == ACTION_SKIP:
            return 'Pass this round because no tactic is available.'
        return label

    @staticmethod
    def _draw_action_icon(surface: pygame.Surface, key: str,
                          rect: pygame.Rect, color: tuple) -> None:
        """Draw a simple icon glyph for an action key inside ``rect``."""
        cx, cy = rect.center
        s = min(rect.width, rect.height) // 2
        if key == ACTION_PLAY:
            # Right-pointing filled triangle.
            pygame.draw.polygon(surface, color, [
                (cx - s // 2, cy - s),
                (cx + s, cy),
                (cx - s // 2, cy + s),
            ])
        elif key == ACTION_GAMBLE:
            die = pygame.Rect(cx - s, cy - s, 2 * s, 2 * s)
            pygame.draw.rect(surface, color, die, 2, border_radius=max(2, s // 3))
            pip_r = max(1, s // 5)
            for px, py in ((die.left + s // 2, die.top + s // 2),
                           (die.centerx, die.centery),
                           (die.right - s // 2, die.bottom - s // 2)):
                pygame.draw.circle(surface, color, (px, py), pip_r)
        elif key == ACTION_COMBINE:
            # Two small overlapping squares.
            r1 = pygame.Rect(cx - s, cy - s, s + 2, s + 2)
            r2 = pygame.Rect(cx - 2, cy - 2, s + 2, s + 2)
            pygame.draw.rect(surface, color, r1, 2, border_radius=2)
            pygame.draw.rect(surface, color, r2, 2, border_radius=2)
            pygame.draw.line(surface, color, (cx - s // 2, cy), (cx + s // 2, cy), 2)
            pygame.draw.line(surface, color, (cx, cy - s // 2), (cx, cy + s // 2), 2)
        elif key == ACTION_DISMANTLE:
            # X mark.
            pygame.draw.line(surface, color,
                             (cx - s, cy - s), (cx + s, cy + s), 2)
            pygame.draw.line(surface, color,
                             (cx - s, cy + s), (cx + s, cy - s), 2)
        elif key == ACTION_SKIP:
            # Two right-chevrons.
            for off in (-s // 2, s // 2):
                pygame.draw.lines(surface, color, False, [
                    (cx + off - s // 2, cy - s),
                    (cx + off + s // 2, cy),
                    (cx + off - s // 2, cy + s),
                ], 2)

    def _draw_action_tray(self, rect: pygame.Rect):
        """Render only the currently-applicable actions (round 13).

        Play/Skip is treated as the primary action. On narrow rails the
        primary action takes the full top row and tactical utilities sit on a
        compact second row, avoiding clipped labels.
        """
        norm_specs = self._normalized_action_specs()
        self._action_button_rects = {}
        self._disabled_action_reasons = {}
        if not norm_specs:
            # Subtle hint when no actions apply (e.g. opponent's turn,
            # nothing selected). Avoid empty-looking dead space.
            sel = self._selected_move()
            hint = (('Tap a tactic' if settings.TOUCH_TARGET_MIN > 0
                     else 'Pick a tactic to act') if sel is None
                    else "Wait for your battle turn")
            font = settings.get_font(max(settings.FS_CONQUER_LABEL, int(settings.FS_TINY * 0.9)))
            surf = font.render(hint, True, _TEXT_MUTED)
            self.window.blit(surf, surf.get_rect(center=rect.center))
            return
        try:
            mx, my = pygame.mouse.get_pos()
        except Exception:
            mx, my = (-1, -1)
        hovered_tooltip: Optional[tuple] = None
        button_rects = self._layout_action_buttons(rect, norm_specs)
        for key, label, disabled_reason, base_rect, role in button_rects:
            hovered = base_rect.collidepoint(mx, my)
            is_disabled = bool(disabled_reason)
            self._draw_action_button(base_rect, key, label, role, hovered, is_disabled)
            self._action_button_rects[key] = base_rect
            if is_disabled:
                self._disabled_action_reasons[key] = disabled_reason
            if hovered and hovered_tooltip is None:
                text = disabled_reason or self._action_tooltip_text(key, label)
                if role == 'secondary' or is_disabled:
                    hovered_tooltip = (base_rect, text)
        # Draw any active tooltip last so it sits above the buttons.
        if hovered_tooltip is not None:
            self._draw_action_tooltip(*hovered_tooltip)

    def _layout_action_buttons(self, rect: pygame.Rect, specs: List[tuple]) -> List[tuple]:
        gap = 5
        pad_y = 2
        target_h = max(30, settings.TOUCH_COMPACT_MIN)
        primary = [spec for spec in specs if spec[0] in _PRIMARY_ACTION_KEYS]
        secondary = [spec for spec in specs if spec[0] not in _PRIMARY_ACTION_KEYS]
        out = []
        if primary and secondary and self._action_tray_uses_column_layout(rect.width, specs):
            row_count = len(specs)
            row_h = min(target_h, max(18, (rect.height - gap * (row_count - 1) - pad_y * 2) // row_count))
            y = rect.top + pad_y
            for index, spec in enumerate((primary[0], *secondary)):
                role = 'primary' if index == 0 else 'secondary'
                out.append((*spec, pygame.Rect(rect.left, y, rect.width, row_h), role))
                y += row_h + gap
            return out
        if primary and secondary and self._action_tray_uses_stacked_layout(rect.width, specs):
            row_h = min(target_h, max(18, (rect.height - gap - pad_y * 2) // 2))
            top = rect.top + pad_y
            primary_rect = pygame.Rect(rect.left, top, rect.width, row_h)
            out.append((*primary[0], primary_rect, 'primary'))
            sec_top = primary_rect.bottom + gap
            sec_h = max(16, min(target_h, rect.bottom - pad_y - sec_top))
            sec_count = len(secondary)
            sec_w = max(1, (rect.width - gap * (sec_count - 1)) // sec_count)
            for index, spec in enumerate(secondary):
                x = rect.left + index * (sec_w + gap)
                width = rect.right - x if index == sec_count - 1 else sec_w
                out.append((*spec, pygame.Rect(x, sec_top, width, sec_h), 'secondary'))
            return out
        if primary and secondary:
            bh = min(target_h, max(18, rect.height - pad_y * 2))
            y = rect.top + (rect.height - bh) // 2
            secondary_count = len(secondary)
            secondary_total = min(
                max(54 * secondary_count + gap * (secondary_count - 1), int(rect.width * 0.45)),
                max(1, rect.width - 78 - gap),
            )
            primary_w = max(70, rect.width - gap - secondary_total)
            primary_rect = pygame.Rect(rect.left, y, primary_w, bh)
            out.append((*primary[0], primary_rect, 'primary'))
            sec_x = primary_rect.right + gap
            sec_w = max(1, (rect.right - sec_x - gap * (secondary_count - 1)) // secondary_count)
            for index, spec in enumerate(secondary):
                x = sec_x + index * (sec_w + gap)
                width = rect.right - x if index == secondary_count - 1 else sec_w
                out.append((*spec, pygame.Rect(x, y, width, bh), 'secondary'))
            return out
        count = len(specs)
        bh = min(target_h, max(18, rect.height - pad_y * 2))
        y = rect.top + (rect.height - bh) // 2
        bw = max(1, (rect.width - gap * (count - 1)) // count)
        for index, spec in enumerate(specs):
            x = rect.left + index * (bw + gap)
            width = rect.right - x if index == count - 1 else bw
            role = 'primary' if spec[0] in _PRIMARY_ACTION_KEYS else 'secondary'
            out.append((*spec, pygame.Rect(x, y, width, bh), role))
        return out

    def _draw_action_button(self, base_rect: pygame.Rect, key: str, label: str,
                            role: str, hovered: bool, is_disabled: bool) -> None:
        # 'Gamble ×2' never fits a compact secondary button, and dropping the
        # suffix would lose the budget the mobile top strip used to show.
        # Render it as a corner badge instead.
        badge_text = ''
        if key == ACTION_GAMBLE and ' ×' in label:
            label, _, badge_text = label.partition(' ×')
        draw_rect = base_rect.move(0, -2) if (hovered and not is_disabled) else base_rect
        shadow = pygame.Rect(base_rect.left, base_rect.bottom - 2, base_rect.width, 4)
        shadow_surf = pygame.Surface(shadow.size, pygame.SRCALPHA)
        pygame.draw.rect(shadow_surf, (0, 0, 0, 90), shadow_surf.get_rect(),
                         border_radius=4)
        self.window.blit(shadow_surf, shadow.topleft)
        if is_disabled:
            colour = (44, 38, 30)
            border = (110, 96, 70)
            fg = _TEXT_MUTED
        elif role == 'primary':
            colour = (112, 78, 34) if hovered else (88, 62, 32)
            border = (248, 204, 94) if hovered else (222, 168, 72)
            fg = (255, 238, 190)
        else:
            colour = (50, 62, 58) if key in (ACTION_GAMBLE, ACTION_COMBINE) else (58, 50, 44)
            if hovered:
                colour = tuple(min(255, c + 18) for c in colour)
            border = (112, 190, 176) if key == ACTION_GAMBLE else (
                (122, 174, 226) if key == ACTION_COMBINE else _BORDER_RGBA)
            fg = _TEXT_PRIMARY
        pygame.draw.rect(self.window, colour, draw_rect, 0, border_radius=6)
        pygame.draw.rect(self.window, border, draw_rect, 1, border_radius=6)
        if badge_text and not is_disabled:
            self._draw_button_corner_badge(draw_rect, badge_text)
        compact = role == 'secondary' and draw_rect.width < 68
        if compact:
            icon_size = min(13, max(9, draw_rect.height // 2 - 1))
            icon_rect = pygame.Rect(0, 0, icon_size, icon_size)
            icon_rect.center = (draw_rect.centerx, draw_rect.top + icon_size // 2 + 3)
            self._draw_action_icon(self.window, key, icon_rect, fg)
            label_top = icon_rect.bottom
            label_rect = pygame.Rect(draw_rect.left + 2, label_top,
                                     draw_rect.width - 4, draw_rect.bottom - label_top - 1)
            font, fitted = self._fit_action_label(
                key, label, label_rect.width,
                max(settings.FS_CONQUER_META, int(settings.FS_TINY * 0.72)),
                settings.FS_CONQUER_META if settings.TOUCH_TARGET_MIN > 0 else 7)
            text = font.render(fitted, True, fg)
            self.window.blit(text, text.get_rect(center=label_rect.center))
            return
        icon_size = 14 if role == 'secondary' else 16
        icon_rect = pygame.Rect(draw_rect.left + 8,
                                draw_rect.top + (draw_rect.height - icon_size) // 2,
                                icon_size, icon_size)
        self._draw_action_icon(self.window, key, icon_rect, fg)
        label_rect = pygame.Rect(icon_rect.right + 5, draw_rect.top,
                                 draw_rect.right - icon_rect.right - 12,
                                 draw_rect.height)
        base_size = max(settings.FS_CONQUER_LABEL,
                        int(settings.FS_TINY * (1.02 if role == 'primary' else 0.88)))
        font, fitted = self._fit_action_label(
            key, label, label_rect.width, base_size,
            settings.FS_CONQUER_META if settings.TOUCH_TARGET_MIN > 0 else 8)
        text = font.render(fitted, True, fg)
        self.window.blit(text, text.get_rect(center=label_rect.center))

    def _draw_button_corner_badge(self, rect: pygame.Rect, text: str) -> None:
        """Small count pill in a button's top-right corner (gambles left)."""
        font = settings.get_font(
            max(settings.FS_CONQUER_META, int(settings.FS_TINY * 0.68)), bold=True)
        surf = font.render(str(text), True, (28, 22, 14))
        pill = surf.get_rect().inflate(7, 3)
        pill.topright = (rect.right - 2, rect.top + 1)
        pygame.draw.rect(self.window, (200, 164, 76), pill,
                         border_radius=max(3, pill.height // 2))
        self.window.blit(surf, surf.get_rect(center=pill.center))

    def _draw_action_tooltip(self, anchor_rect: pygame.Rect, text: str) -> None:
        if not text:
            return
        font = settings.get_font(max(settings.FS_CONQUER_META, int(settings.FS_TINY * 0.85)))
        surf = font.render(text, True, (245, 230, 195))
        pad_x, pad_y = 8, 4
        box = pygame.Rect(0, 0, surf.get_width() + pad_x * 2,
                          surf.get_height() + pad_y * 2)
        # Anchor above the button; flip below if it would clip the top.
        box.midbottom = (anchor_rect.centerx, anchor_rect.top - 4)
        try:
            clip = self.window.get_clip()
        except Exception:
            clip = None
        if clip is not None and box.top < clip.top:
            box.midtop = (anchor_rect.centerx, anchor_rect.bottom + 4)
        bg = pygame.Surface(box.size, pygame.SRCALPHA)
        bg.fill((22, 18, 14, 230))
        self.window.blit(bg, box.topleft)
        pygame.draw.rect(self.window, (200, 170, 90), box, 1, border_radius=4)
        self.window.blit(surf, (box.left + pad_x, box.top + pad_y))
