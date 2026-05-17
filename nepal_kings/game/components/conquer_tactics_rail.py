# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tactics-hand rail for the unified conquer battle screen.

Single-column persistent left-side rail showing the player's *tactics
hand* (`BattleMove` rows with `played_round is None`).  Replaces the old
``BattleShopScreen`` UI for tactics-hand conquer games.

Sections (top → bottom, all rects come from
:func:`game.components.conquer_layout.compute_conquer_layout`):

* **top strip** — round/turn indicator + an opponent-intent hint.
* **hand list** — scrollable column of one-row cells, one per move.
* **selected detail** — name, suit/rank chip, source, power.
* **action tray** — Play / Gamble / Combine / Dismantle / Skip.

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


# Visual constants
_BG_RGBA = (38, 29, 22, 218)
_BORDER_RGBA = (122, 92, 56)
_SELECTED_RGBA = (210, 168, 72)
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
        self._scroll = 0
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
        # Drag-and-drop combine state. (#8b)
        self._drag_origin_id: Optional[int] = None
        self._drag_pos: Optional[tuple] = None
        self._drag_active: bool = False
        # Category-collapse state (round 13). Defaults: any group with >1
        # member is collapsed (representative + ×N chip). Explicit user
        # toggles override the default in either direction.
        self._collapsed_groups: set = set()
        self._expanded_groups: set = set()
        # Per-cell metadata captured during draw — used by click handling
        # to distinguish collapsed-group rows from individual move rows.
        self._cell_kinds: List[str] = []
        self._cell_groups: List[Optional[str]] = []
        self._cell_group_toggle_rects: List[Optional[pygame.Rect]] = []
        # Dynamic top-strip overflow lines (round 13 wrap). When the
        # banner/title needs more height than the layout's fixed top
        # strip, the rail steals pixels from the hand list (subject to a
        # minimum visible-cell floor) and remembers them here so layout
        # helpers stay in sync.
        self._dyn_top_strip_rect: Optional[pygame.Rect] = None
        self._dyn_hand_list_rect: Optional[pygame.Rect] = None
        self._cached_render_key = None
        self._cached_render_surface: Optional[pygame.Surface] = None

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
        if getattr(game, 'battle_turn_player_id', None) is None:
            return False
        return getattr(game, 'battle_turn_player_id', None) == getattr(game, 'player_id', None)

    GAMBLE_PER_BATTLE_LIMIT = 3

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

    # ------------------------------------------------------------------ public
    def consume_pending_action(self) -> Optional[Dict[str, Any]]:
        """Return and clear the latest queued action (one-shot)."""
        action = self._pending_action
        self._pending_action = None
        return action

    def reset_selection(self):
        self._selected_id = None
        self._hovered_id = None
        self._combine_partner_id = None
        self._combine_pending = False
        self._pending_action = None

    def preview_move(self) -> Optional[Dict[str, Any]]:
        if not self._is_my_battle_turn() or self._hovered_id is None:
            return None
        # Don't preview the representative of a collapsed group — the
        # cell is meant to be clicked to expand, not to act on a single
        # move.
        try:
            i = self._cell_move_ids.index(self._hovered_id)
            if i < len(self._cell_kinds) and self._cell_kinds[i] == 'collapsed':
                return None
        except ValueError:
            pass
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

        Also captures spell-removed moves as ghost rows so the player can
        see what disappeared for ``REMOVED_GHOST_MS`` after the change.
        """
        try:
            hand = self._hand_moves()
            current_by_id = {int(m.get('id') or 0): m for m in hand}
            current = set(current_by_id.keys())
        except Exception:
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
        """Map a move to its display family group (#8a)."""
        fam = (move.get('family_name') or '').strip()
        if fam in ('Dagger', 'Double Dagger'):
            return 'Dagger'
        if fam == 'Buff':
            return 'Buff'
        if fam == 'Block':
            return 'Block'
        if fam == 'Call':
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

    def _group_is_expanded(self, group_label: str, members: List[Dict[str, Any]]) -> bool:
        """Return True if the group should render every member.

        Groups with one member are always "expanded" (nothing to collapse).
        Otherwise: explicit user toggle wins; auto-expand the Dagger group
        whenever the player is mid-combine so partners stay visible.
        """
        if len(members) <= 1:
            return True
        if group_label in self._expanded_groups:
            return True
        if group_label in self._collapsed_groups:
            return False
        # Auto-expand Daggers when a single Dagger is selected or the
        # combine flow is armed — partners must stay visible.
        if group_label == 'Dagger':
            sel = self._selected_move()
            if (sel is not None and self._is_single_dagger(sel)) or self._combine_pending:
                return True
        # Default: collapse multi-member groups.
        return False

    def _toggle_group(self, group_label: str) -> None:
        """Toggle a group's collapsed/expanded state via explicit user click."""
        # Determine current effective state without consulting auto-expand,
        # so a user click on an auto-expanded group force-collapses it.
        if group_label in self._expanded_groups:
            self._expanded_groups.discard(group_label)
            self._collapsed_groups.add(group_label)
        elif group_label in self._collapsed_groups:
            self._collapsed_groups.discard(group_label)
            self._expanded_groups.add(group_label)
        else:
            # Default state was collapsed → switch to explicit expand,
            # unless auto-expand was active in which case collapse.
            members = next(
                (lst for g, lst in self._hand_groups_in_order() if g == group_label),
                [],
            )
            if self._group_is_expanded(group_label, members):
                self._collapsed_groups.add(group_label)
            else:
                self._expanded_groups.add(group_label)

    def _visible_hand_items(self) -> List[Dict[str, Any]]:
        """Flatten groups into render rows, collapsing where appropriate.

        Each item is one of:
          * ``{'kind': 'move', 'move': dict, 'group': str}``
          * ``{'kind': 'collapsed', 'group': str, 'representative': dict,
                'count': int, 'all_ids': List[int]}``
        """
        items: List[Dict[str, Any]] = []
        for group_label, members in self._hand_groups_in_order():
            if not members:
                continue
            if self._group_is_expanded(group_label, members):
                for idx, m in enumerate(members):
                    items.append({
                        'kind': 'move',
                        'move': m,
                        'group': group_label,
                        'group_count': len(members),
                        'group_first': idx == 0,
                        'can_collapse': len(members) > 1,
                    })
            else:
                rep = members[0]  # already sorted desc by power
                items.append({
                    'kind': 'collapsed',
                    'group': group_label,
                    'representative': rep,
                    'count': len(members),
                    'all_ids': [int(m.get('id') or 0) for m in members],
                })
        return items

    def handle_event(self, event) -> bool:
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
        # Banner — click anywhere inside it to dismiss (#8a).
        if self._result_banner is not None:
            top_strip = self._dyn_top_strip_rect
            if top_strip is None:
                try:
                    top_strip = pygame.Rect(*layout.tactics_rail.top_strip_rect)
                except Exception:
                    top_strip = None
            if top_strip is not None and top_strip.collidepoint(pos):
                self._result_banner = None
                return True
        # Scroll buttons
        if self._scroll_up_rect and self._scroll_up_rect.collidepoint(pos):
            self._scroll = max(0, self._scroll - 1)
            self._clamp_scroll()
            return True
        if self._scroll_down_rect and self._scroll_down_rect.collidepoint(pos):
            self._scroll += 1
            self._clamp_scroll()
            return True
        # Action buttons
        for key, rect in self._action_button_rects.items():
            if rect.collidepoint(pos):
                self._trigger_action(key)
                return True
        # Cell selection
        for i, (rect, mid) in enumerate(zip(self._cell_rects, self._cell_move_ids)):
            if rect.collidepoint(pos):
                kind = (self._cell_kinds[i]
                        if i < len(self._cell_kinds) else 'move')
                if kind == 'collapsed':
                    group = (self._cell_groups[i]
                             if i < len(self._cell_groups) else None)
                    if group:
                        self._toggle_group(group)
                    return True
                toggle_rect = (self._cell_group_toggle_rects[i]
                               if i < len(self._cell_group_toggle_rects) else None)
                if toggle_rect is not None and toggle_rect.collidepoint(pos):
                    group = (self._cell_groups[i]
                             if i < len(self._cell_groups) else None)
                    if group:
                        self._toggle_group(group)
                    return True
                self._handle_cell_click(mid)
                # Arm drag-and-drop combine (#8b) — only meaningful for
                # single Daggers; the actual drag promotes on motion.
                move = next((m for m in self._hand_moves()
                             if int(m.get('id') or 0) == mid), None)
                if move is not None and self._is_single_dagger(move):
                    self._drag_origin_id = mid
                    self._drag_pos = pos
                    self._drag_active = False
                return True
        return True  # consumed even if hit empty space inside the rail

    def _cell_rect_for(self, move_id: int) -> Optional[pygame.Rect]:
        for rect, mid in zip(self._cell_rects, self._cell_move_ids):
            if mid == move_id:
                return rect
        return None

    def _cancel_drag(self) -> None:
        self._drag_origin_id = None
        self._drag_pos = None
        self._drag_active = False

    def _clamp_scroll(self):
        layout = self._ensure_layout()
        items = self._visible_hand_items()
        total = len(items)
        rail = layout.tactics_rail
        # Use the dynamic hand-list rect when available so scroll respects
        # the runtime header overflow (round 13 wrap).
        list_h = (self._dyn_hand_list_rect.height
                  if self._dyn_hand_list_rect is not None
                  else rail.hand_list_rect[3])
        visible_cells = max(1, min(
            rail.cells_visible,
            max(1, list_h // max(1, rail.cell_height)),
        ))
        # Active removed-ghost cells share the visible budget (each one
        # steals a slot from the bottom).
        ghost_count = len(getattr(self, '_removed_ghosts', {}) or {})
        effective_visible = max(1, visible_cells - ghost_count)
        self._scroll = max(0, min(self._scroll, max(0, total - effective_visible)))

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
        self._selected_id = None if self._selected_id == mid else mid
        self._combine_pending = False
        self._combine_partner_id = None

    def _trigger_action(self, key: str):
        # If the button was rendered as disabled this frame, surface the
        # reason instead of silently doing nothing.
        disabled_reasons = getattr(self, '_disabled_action_reasons', None) or {}
        if key in disabled_reasons:
            self.set_result_banner(disabled_reasons[key], ttl_ms=1800)
            return
        # Block all actions while a played-tactic flight animation is in
        # progress.  Without this the player can fire a second mutating
        # request before the first one's animation finishes — racing
        # cache state and the server's per-game lock.
        try:
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
            # Gambling is a tactics-hand mutation, not a battle-turn action.
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
            if partner is not None and self._can_combine(sel, partner):
                self._pending_action = {
                    'action': ACTION_COMBINE,
                    'move': sel,
                    'partner': partner,
                }
                self._combine_pending = False
                self._combine_partner_id = None
            else:
                self._combine_pending = True
                self._combine_partner_id = None

    # ------------------------------------------------------------------ draw
    def _rail_render_cache_key(self, rail_rect: pygame.Rect, now: int):
        if rail_rect.collidepoint(pygame.mouse.get_pos()):
            return None
        if self._drag_active or self._drag_origin_id is not None:
            return None
        if self._gamble_anim:
            started = int(self._gamble_anim.get('started_at', 0) or 0)
            duration = int(self._gamble_anim.get('duration', 0) or 0)
            if now < started + duration:
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
            self._scroll,
            self._selected_id,
            self._combine_partner_id,
            self._combine_pending,
            tuple(sorted(self._collapsed_groups)),
            tuple(sorted(self._expanded_groups)),
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
        # Dynamic top-strip wrap (round 13). Grow the strip downward when
        # the title or banner needs more lines, stealing from the hand
        # list. Floor: keep room for at least 3 cells in the hand list.
        required_h = self._measure_top_strip_height(top_strip_rect.width)
        extra = max(0, required_h - top_strip_rect.height)
        if extra > 0:
            min_list_h = 3 * rail.cell_height
            hand_slack = max(0, hand_list_rect.height - min_list_h)
            detail_slack = selected_detail_rect.height if self._result_banner else 0
            grow = min(extra, detail_slack + hand_slack)
            if grow > 0:
                top_strip_rect.height += grow
                detail_shrink = min(grow, detail_slack)
                if detail_shrink:
                    selected_detail_rect.y += detail_shrink
                    selected_detail_rect.height -= detail_shrink
                hand_grow = grow - detail_shrink
                if hand_grow:
                    hand_list_rect.y += hand_grow
                    hand_list_rect.height -= hand_grow
        self._dyn_top_strip_rect = top_strip_rect
        self._dyn_hand_list_rect = hand_list_rect

        self._draw_top_strip(top_strip_rect)
        self._draw_hand_list(hand_list_rect, rail.cell_height,
                             rail.cells_visible)
        self._draw_selected_detail(selected_detail_rect)
        self._draw_action_tray(pygame.Rect(*rail.action_tray_rect))
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

    def _measure_top_strip_height(self, width: int) -> int:
        """Compute the pixel height required to render the top strip.

        Returns the natural fit; ``draw()`` decides whether/how to grow
        the strip into the hand list.
        """
        font = settings.get_font(max(11, int(settings.FS_SMALL * 0.95)), bold=True)
        sub = settings.get_font(max(10, int(settings.FS_TINY * 0.95)))
        avail = max(1, width - 16)
        if self._result_banner:
            text = self._result_banner.get('text', '')
            lines = self._wrap_text(text, font, avail)
            hint_h = settings.get_font(
                max(9, int(settings.FS_TINY * 0.8))).get_height()
            return 4 + len(lines) * (font.get_height() + 1) + hint_h + 7
        game = getattr(self._parent.state, 'game', None)
        hand_count = len(self._hand_moves())
        word = 'battle move' if hand_count == 1 else 'battle moves'
        line1 = f'{hand_count} {word}'
        gamble_text, _ = self._gamble_status_for_strip(game)
        line2 = gamble_text
        l1 = self._wrap_text(line1, font, avail)
        l2 = self._wrap_text(line2, sub, avail)
        return (4 + len(l1) * (font.get_height() + 1)
                + 2 + len(l2) * (sub.get_height() + 1) + 4)

    # -- top strip
    def _draw_top_strip(self, rect: pygame.Rect):
        if self._result_banner:
            self._draw_result_banner(rect)
            return
        # Two-row strip: tactics-in-hand count + gamble status. The
        # "Action pending" hint and Round X/3 line were removed -- the
        # ledger and timeline communicate round / turn already.
        hand_count = len(self._hand_moves())
        word = 'battle move' if hand_count == 1 else 'battle moves'
        line1 = f'{hand_count} {word}'
        game = getattr(self._parent.state, 'game', None)
        gamble_text, gamble_state = self._gamble_status_for_strip(game)
        line2 = gamble_text
        font = settings.get_font(max(11, int(settings.FS_SMALL * 0.95)), bold=True)
        sub = settings.get_font(max(10, int(settings.FS_TINY * 0.95)))
        avail = max(1, rect.width - 16)
        y = rect.y + 4
        for line in self._wrap_text(line1, font, avail):
            if y + font.get_height() > rect.bottom:
                break
            surf = font.render(line, True, _TEXT_PRIMARY)
            self.window.blit(surf, (rect.x + 8, y))
            y += font.get_height() + 1
        y += 2
        # Muted grey when the player has already gambled this round.
        line2_color = (140, 132, 116) if gamble_state == 'used' else _TEXT_SECONDARY
        for line in self._wrap_text(line2, sub, avail):
            if y + sub.get_height() > rect.bottom:
                break
            surf = sub.render(line, True, line2_color)
            self.window.blit(surf, (rect.x + 8, y))
            y += sub.get_height() + 1

    def _gamble_status_for_strip(self, game):
        """Return (text, state) where state is 'ready'|'used'|'limit'|'idle'."""
        if game is None:
            return ('', 'idle')
        counts = getattr(game, 'battle_gamble_counts', None) or {}
        my_id = getattr(game, 'player_id', None)
        state = counts.get(str(my_id), 0)
        if isinstance(state, dict):
            try:
                used = int(state.get('count', 0) or 0)
            except (TypeError, ValueError):
                used = 0
        else:
            try:
                used = int(state or 0)
            except (TypeError, ValueError):
                used = 0
        try:
            current_round = int(getattr(game, 'battle_round', 0) or 0)
        except (TypeError, ValueError):
            current_round = 0
        round_used = isinstance(state, dict) and current_round in {
            int(round_value) for round_value in (state.get('rounds', []) or [])
            if str(round_value).lstrip('-').isdigit()
        }
        if round_used:
            return ('Already gambled', 'used')
        if used >= self.GAMBLE_PER_BATTLE_LIMIT:
            return (f'Gamble limit reached ({used}/{self.GAMBLE_PER_BATTLE_LIMIT})', 'limit')
        return ('Gamble ready this round', 'ready')

    def _top_strip_subtitle(self, game) -> str:
        hint = self._opponent_intent_hint(game)
        counts = self._top_strip_count_text(game)
        return f'{hint} · {counts}' if counts else hint

    def _top_strip_count_text(self, game) -> str:
        if game is None:
            return ''
        tactics_remaining = len(self._hand_moves())
        counts = getattr(game, 'battle_gamble_counts', None) or {}
        my_id = getattr(game, 'player_id', None)
        state = counts.get(str(my_id), 0)
        if isinstance(state, dict):
            try:
                used = int(state.get('count', 0) or 0)
            except (TypeError, ValueError):
                used = 0
        else:
            try:
                used = int(state or 0)
            except (TypeError, ValueError):
                used = 0
        try:
            current_round = int(getattr(game, 'battle_round', 0) or 0)
        except (TypeError, ValueError):
            current_round = 0
        round_used = isinstance(state, dict) and current_round in {
            int(round_value) for round_value in (state.get('rounds', []) or [])
            if str(round_value).lstrip('-').isdigit()
        }
        if round_used:
            gamble_text = 'Gamble used this round'
        elif used >= self.GAMBLE_PER_BATTLE_LIMIT:
            gamble_text = 'Gamble limit reached'
        else:
            gamble_text = 'Gamble ready this round'
        tactic_word = 'tactic' if tactics_remaining == 1 else 'tactics'
        return f'{tactics_remaining} {tactic_word} · {gamble_text}'

    def _opponent_intent_hint(self, game) -> str:
        opp_id = getattr(game, 'battle_turn_player_id', None)
        if opp_id is None or opp_id == getattr(game, 'player_id', None):
            return 'Action pending'
        return 'Opponent action hidden'

    def _draw_result_banner(self, rect: pygame.Rect):
        banner = self._result_banner or {}
        text = banner.get('text', '')
        color = banner.get('color', _TEXT_PRIMARY)
        # Background — slightly brighter than the rail header so it pops.
        bg = pygame.Surface(rect.size, pygame.SRCALPHA)
        bg.fill((58, 44, 28, 232))
        self.window.blit(bg, rect.topleft)
        pygame.draw.rect(self.window, color, rect, 2, border_radius=4)
        sub = settings.get_font(max(9, int(settings.FS_TINY * 0.8)))
        avail = max(1, rect.width - 16)
        base_size = max(11, int(settings.FS_SMALL * 0.95))
        min_size = max(8, int(settings.FS_TINY * 0.72))
        font = settings.get_font(base_size, bold=True)
        lines = self._wrap_text(text, font, avail)
        for size in range(base_size, min_size - 1, -1):
            candidate = settings.get_font(size, bold=True)
            candidate_lines = self._wrap_text(text, candidate, avail)
            needed = (4 + len(candidate_lines) * (candidate.get_height() + 1)
                      + sub.get_height() + 7)
            if needed <= rect.height:
                font = candidate
                lines = candidate_lines
                break
        y = rect.y + 4
        for line in lines:
            if y + font.get_height() > rect.bottom - sub.get_height() - 4:
                break
            surf = font.render(line, True, color)
            self.window.blit(surf, (rect.x + 8, y))
            y += font.get_height() + 1
        hint = sub.render('(click anywhere to dismiss)', True, _TEXT_MUTED)
        self.window.blit(hint, (rect.x + 8, rect.bottom - sub.get_height() - 3))

    # -- hand list
    HEADER_H = 14

    def _draw_family_header(self, rect: pygame.Rect, label: str) -> None:
        bg = pygame.Surface(rect.size, pygame.SRCALPHA)
        bg.fill((26, 22, 18, 210))
        self.window.blit(bg, rect.topleft)
        pygame.draw.line(self.window, _BORDER_RGBA,
                         (rect.left + 2, rect.bottom - 1),
                         (rect.right - 2, rect.bottom - 1), 1)
        font = settings.get_font(max(9, int(settings.FS_TINY * 0.85)), bold=True)
        s = font.render(label, True, _TEXT_SECONDARY)
        self.window.blit(s, (rect.left + 6, rect.top + 1))

    def _draw_hand_list(self, rect: pygame.Rect, cell_h: int, cells_visible: int):
        previous_clip = self.window.get_clip()
        self.window.set_clip(rect)
        items = self._visible_hand_items()
        self._clamp_scroll()
        self._cell_rects = []
        self._cell_move_ids = []
        self._cell_kinds = []
        self._cell_groups = []
        self._cell_group_toggle_rects = []
        self._hovered_id = None
        if not items:
            empty_font = settings.get_font(max(11, int(settings.FS_SMALL * 0.9)))
            t = empty_font.render('— hand empty —', True, _TEXT_MUTED)
            self.window.blit(t, t.get_rect(center=rect.center))
            self.window.set_clip(previous_clip)
            return
        visible_count = max(1, min(cells_visible, rect.height // max(1, cell_h)))
        visible = items[self._scroll:self._scroll + visible_count]
        # Draw scroll indicators if needed.
        if self._scroll > 0:
            up = pygame.Rect(rect.right - 18, rect.top + 2, 14, 12)
            pygame.draw.polygon(self.window, _TEXT_PRIMARY,
                                [(up.centerx, up.top), (up.left, up.bottom),
                                 (up.right, up.bottom)])
            self._scroll_up_rect = up
        else:
            self._scroll_up_rect = None
        if self._scroll + visible_count < len(items):
            dn = pygame.Rect(rect.right - 18, rect.bottom - 14, 14, 12)
            pygame.draw.polygon(self.window, _TEXT_PRIMARY,
                                [(dn.centerx, dn.bottom), (dn.left, dn.top),
                                 (dn.right, dn.top)])
            self._scroll_down_rect = dn
        else:
            self._scroll_down_rect = None

        font = settings.get_font(max(11, int(settings.FS_SMALL * 0.95)), bold=True)
        chip_font = settings.get_font(max(9, int(settings.FS_TINY * 0.85)), bold=True)
        mouse_pos = pygame.mouse.get_pos()
        y = rect.top
        # Spell-removed ghost cells (#round4).
        now_ms = pygame.time.get_ticks()
        for mid, ghost in list(self._removed_ghosts.items()):
            if y + cell_h > rect.bottom + 2:
                break
            ghost_move = ghost.get('move') or {}
            ghost_rect = pygame.Rect(rect.left, y, rect.width, cell_h - 2)
            self._draw_removed_ghost_cell(ghost_rect, ghost_move, font, chip_font,
                                          expires_at=ghost.get('expires_at', now_ms))
            y += cell_h
        for item in visible:
            if y + cell_h > rect.bottom + 2:
                break
            cell_rect = pygame.Rect(rect.left, y, rect.width, cell_h - 2)
            hovered = cell_rect.collidepoint(mouse_pos)
            if item['kind'] == 'collapsed':
                rep = item['representative']
                rep_id = int(rep.get('id') or 0)
                if hovered:
                    self._hovered_id = rep_id
                self._draw_collapsed_group_cell(
                    cell_rect, item, font, chip_font, hovered=hovered)
                self._cell_rects.append(cell_rect)
                self._cell_move_ids.append(rep_id)
                self._cell_kinds.append('collapsed')
                self._cell_groups.append(item['group'])
                self._cell_group_toggle_rects.append(None)
            else:
                move = item['move']
                if hovered:
                    self._hovered_id = int(move.get('id') or 0)
                self._draw_hand_cell(cell_rect, move, font, chip_font, hovered=hovered)
                toggle_rect = None
                if item.get('can_collapse') and item.get('group_first'):
                    toggle_rect = self._draw_expanded_group_toggle(
                        cell_rect, item, chip_font, hovered=hovered)
                self._cell_rects.append(cell_rect)
                self._cell_move_ids.append(int(move.get('id') or 0))
                self._cell_kinds.append('move')
                self._cell_groups.append(item['group'])
                self._cell_group_toggle_rects.append(toggle_rect)
            y += cell_h
        # Drag ghost (#8b) — drawn last so it floats over cells.
        if self._drag_active and self._drag_origin_id is not None and self._drag_pos:
            origin_move = next((m for m in self._hand_moves()
                                if int(m.get('id') or 0) == self._drag_origin_id), None)
            if origin_move is not None:
                self._draw_drag_ghost(origin_move, self._drag_pos)
        self.window.set_clip(previous_clip)

    def _draw_expanded_group_toggle(self, rect: pygame.Rect, item: Dict[str, Any],
                                    chip_font, *, hovered: bool = False) -> pygame.Rect:
        count = int(item.get('group_count') or 1)
        pill_text = f'×{count}'
        pill_surf = chip_font.render(pill_text, True, (24, 18, 12))
        pill_w = pill_surf.get_width() + 24
        pill_h = pill_surf.get_height() + 5
        pill_rect = pygame.Rect(0, 0, pill_w, pill_h)
        pill_rect.right = rect.right - 6
        pill_rect.centery = rect.centery
        bg = pygame.Surface(pill_rect.size, pygame.SRCALPHA)
        fill = (220, 185, 92, 245) if hovered else (194, 150, 64, 226)
        pygame.draw.rect(bg, fill, bg.get_rect(), border_radius=pill_h // 2)
        self.window.blit(bg, pill_rect.topleft)
        self.window.blit(pill_surf, pill_surf.get_rect(
            midleft=(pill_rect.left + 7, pill_rect.centery)))
        cx = pill_rect.right - 10
        cy = pill_rect.centery
        pygame.draw.polygon(
            self.window,
            (40, 30, 18),
            [(cx - 5, cy + 3), (cx + 5, cy + 3), (cx, cy - 4)],
        )
        return pill_rect

    def _draw_collapsed_group_cell(self, rect: pygame.Rect, item: Dict[str, Any],
                                    font, chip_font, *, hovered: bool = False) -> None:
        """Render a collapsed-group cell: representative move + ×N badge.

        The representative is the strongest move in the group. Click
        anywhere on the cell toggles expansion (handled in
        ``_handle_cell_click``).
        """
        rep = item['representative']
        count = int(item.get('count') or 1)
        # Reuse the regular hand-cell renderer for the representative —
        # this keeps glow/animation behaviour consistent.
        self._draw_hand_cell(rect, rep, font, chip_font, hovered=hovered)
        # Overlay the "×N" pill on the right edge, plus a chevron glyph
        # marking this row as expandable.
        previous_clip = self.window.get_clip()
        self.window.set_clip(rect)
        pill_font = settings.get_font(max(9, int(settings.FS_TINY * 0.85)), bold=True)
        pill_text = f'×{count}'
        pill_surf = pill_font.render(pill_text, True, (24, 18, 12))
        pill_w = pill_surf.get_width() + 10
        pill_h = pill_surf.get_height() + 4
        pill_rect = pygame.Rect(0, 0, pill_w, pill_h)
        pill_rect.right = rect.right - 22  # leave space for chevron
        pill_rect.centery = rect.centery
        bg = pygame.Surface(pill_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(bg, (210, 168, 72, 240), bg.get_rect(),
                         border_radius=pill_h // 2)
        self.window.blit(bg, pill_rect.topleft)
        self.window.blit(pill_surf, pill_surf.get_rect(center=pill_rect.center))
        # Down-chevron marking expand affordance.
        chev_color = (220, 196, 130) if hovered else _TEXT_SECONDARY
        cx = rect.right - 10
        cy = rect.centery
        pygame.draw.polygon(
            self.window, chev_color,
            [(cx - 5, cy - 3), (cx + 5, cy - 3), (cx, cy + 4)])
        self.window.set_clip(previous_clip)


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
        bg_col = (52, 40, 30, 240) if is_selected else (38, 32, 25, 224) if hovered else (32, 24, 18, 200)
        bg = pygame.Surface(rect.size, pygame.SRCALPHA)
        bg.fill(bg_col)
        self.window.blit(bg, rect.topleft)
        border_col = _SELECTED_RGBA if is_selected else (190, 178, 120) if hovered else (_BORDER_RGBA if not is_partner else (130, 200, 250))
        pygame.draw.rect(self.window, border_col, rect, 2, border_radius=4)

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
            ribbon_font = settings.get_font(max(8, int(settings.FS_TINY * 0.7)), bold=True)
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
        icon_size = max(20, int(rect.height * 0.78))
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

        # Name + suit/rank chip (right of icon)
        text_x = rect.left + icon_size + 18
        name = move.get('family_name', '?')
        if self._is_double_dagger(move):
            name = 'Double Dagger'

        # Power is already rendered inside the battle-move icon itself, so
        # we omit the duplicate right-edge number to free horizontal
        # space for the move name + suit chip (#round5).
        max_text_w = max(24, rect.right - text_x - 18)

        name_surf = font.render(self._fit_text(name, font, max_text_w), True, _TEXT_PRIMARY)
        self.window.blit(name_surf, (text_x, rect.top + 6))

        chip_text = f"{move.get('suit', '?')[:1]} {move.get('rank', '?')}"
        chip_surf = chip_font.render(
            self._fit_text(chip_text, chip_font, max_text_w), True, _TEXT_SECONDARY)
        self.window.blit(chip_surf, (text_x, rect.top + 6 + name_surf.get_height() + 1))

        # Strongest-move badge (#8d) — small star/spark glyph on the
        # currently highest-power move.
        if mid == self._strongest_move_id():
            badge_font = settings.get_font(max(10, int(settings.FS_TINY * 0.9)), bold=True)
            badge_surf = badge_font.render('★', True, (250, 220, 110))
            self.window.blit(badge_surf, (rect.left + 4, rect.top + 2))

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
                    max(9, int(settings.FS_TINY * 0.85)), bold=True)
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
                    max(10, int(settings.FS_TINY * 1.1)), bold=True)
                glyph = glyph_font.render('✺', True, (170, 200, 240))
                self.window.blit(
                    glyph,
                    (rect.right - glyph.get_width() - 6, rect.top + 4),
                )
            except Exception:
                pass

        self.window.set_clip(previous_clip)

    # -- selected detail
    def _draw_selected_detail(self, rect: pygame.Rect):
        pygame.draw.rect(self.window, (24, 18, 14), rect, 0, border_radius=4)
        pygame.draw.rect(self.window, _BORDER_RGBA, rect, 1, border_radius=4)
        sel = self._selected_move()
        title_font = settings.get_font(max(12, int(settings.FS_SMALL * 1.0)), bold=True)
        body_font = settings.get_font(max(10, int(settings.FS_TINY * 0.95)))
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
        line = f"{suit_a}{('+' + suit_b) if suit_b else ''} • {rank} • Power {self._power(sel)}"
        bs = body_font.render(
            self._fit_text(line, body_font, rect.width - 16), True, _TEXT_SECONDARY)
        self.window.blit(bs, (rect.left + 8, rect.top + 6 + ts.get_height() + 2))

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
        partner = self._combine_partner_move()
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
            specs.append((ACTION_GAMBLE, 'Gamble'))
        elif gamble_reason not in ('Not your battle turn',
                                   'Gamble only during active battle rounds',
                                   'No active game'):
            # Surface meaningful gates (limit hit, already gambled this
            # round) as a disabled button with a hover tooltip.
            specs.append((ACTION_GAMBLE, 'Gamble', gamble_reason))
        if self._is_single_dagger(sel):
            if self._combine_pending and partner is None:
                specs.append((ACTION_COMBINE, 'Pick 2nd'))
            else:
                specs.append((ACTION_COMBINE, 'Combine'))
        if self._is_double_dagger(sel):
            specs.append((ACTION_DISMANTLE, 'Dismantle'))
        return specs

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
            # Hollow circle with a "?" letter for dice/random.
            pygame.draw.circle(surface, color, (cx, cy), s, 2)
            font = settings.get_font(max(9, s * 2 - 2), bold=True)
            q = font.render('?', True, color)
            surface.blit(q, q.get_rect(center=(cx, cy)))
        elif key == ACTION_COMBINE:
            # Two small overlapping squares.
            r1 = pygame.Rect(cx - s, cy - s, s + 2, s + 2)
            r2 = pygame.Rect(cx - 2, cy - 2, s + 2, s + 2)
            pygame.draw.rect(surface, color, r1, 2, border_radius=2)
            pygame.draw.rect(surface, color, r2, 2, border_radius=2)
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

        Replaces the previous always-on row of disabled buttons. Buttons
        are rounded with a leading icon glyph + label and lift on hover.
        """
        specs = self._action_specs()
        # While a played-tactic flight animation is in progress, freeze all
        # action buttons — they should not appear pressable and click-through
        # is already blocked by ``_trigger_action``.  Surfacing this visually
        # prevents the player from queuing a second action mid-animation.
        flight_active = False
        try:
            flight_check = getattr(self._parent, 'is_tactic_flight_active', None)
            flight_active = bool(callable(flight_check) and flight_check())
        except Exception:
            flight_active = False
        # Normalize to 3-tuples (key, label, disabled_reason or '').
        if flight_active:
            norm_specs = [
                (s[0], s[1], s[2] if len(s) > 2 and s[2] else 'Tactic in flight…')
                for s in specs
            ]
        else:
            norm_specs = [
                (s[0], s[1], s[2] if len(s) > 2 else '') for s in specs
            ]
        self._action_button_rects = {}
        if not norm_specs:
            # Subtle hint when no actions apply (e.g. opponent's turn,
            # nothing selected). Avoid empty-looking dead space.
            sel = self._selected_move()
            hint = ('Pick a tactic to act' if sel is None
                    else "Wait for your battle turn")
            font = settings.get_font(max(10, int(settings.FS_TINY * 0.9)))
            surf = font.render(hint, True, _TEXT_MUTED)
            self.window.blit(surf, surf.get_rect(center=rect.center))
            return
        font = settings.get_font(max(10, int(settings.FS_TINY * 0.95)), bold=True)
        gap = 8
        n = len(norm_specs)
        # Compute button width: room for icon (~18 px) + gap (4 px) + label.
        icon_w = 18
        labels = [label for _k, label, _d in norm_specs]
        label_w = max(font.size(lbl)[0] for lbl in labels)
        natural_w = icon_w + 4 + label_w + 18  # padding 9 px each side
        max_total = rect.width - gap * (n - 1)
        bw = min(natural_w, max(60, max_total // n))
        total_w = bw * n + gap * (n - 1)
        start_x = rect.left + max(0, (rect.width - total_w) // 2)
        bh = min(rect.height - 4, 30)
        by = rect.top + (rect.height - bh) // 2
        try:
            mx, my = pygame.mouse.get_pos()
        except Exception:
            mx, my = (-1, -1)
        hovered_tooltip: Optional[tuple] = None
        for i, (key, label, disabled_reason) in enumerate(norm_specs):
            br = pygame.Rect(start_x + i * (bw + gap), by, bw, bh)
            hovered = br.collidepoint(mx, my)
            is_disabled = bool(disabled_reason)
            # Hover lift: shift the button up by 2 px so it visually pops.
            # Disabled buttons stay put (no affordance for press).
            draw_rect = br.move(0, -2) if (hovered and not is_disabled) else br
            shadow = pygame.Rect(br.left, br.bottom - 2, br.width, 4)
            shadow_surf = pygame.Surface(shadow.size, pygame.SRCALPHA)
            pygame.draw.rect(shadow_surf, (0, 0, 0, 90), shadow_surf.get_rect(),
                             border_radius=3)
            self.window.blit(shadow_surf, shadow.topleft)
            if is_disabled:
                colour = (44, 38, 30)
                border = (110, 96, 70)
                fg = _TEXT_MUTED
            else:
                colour = (84, 66, 44) if hovered else (62, 50, 36)
                border = (220, 180, 90) if hovered else _BORDER_RGBA
                fg = _TEXT_PRIMARY
            pygame.draw.rect(self.window, colour, draw_rect, 0, border_radius=6)
            pygame.draw.rect(self.window, border, draw_rect, 1, border_radius=6)
            # Icon on the left.
            icon_rect = pygame.Rect(draw_rect.left + 8,
                                    draw_rect.top + (draw_rect.height - 14) // 2,
                                    14, 14)
            self._draw_action_icon(self.window, key, icon_rect, fg)
            # Label centered in the remaining space.
            label_rect = pygame.Rect(icon_rect.right + 4, draw_rect.top,
                                     draw_rect.right - icon_rect.right - 12,
                                     draw_rect.height)
            ts = font.render(self._fit_text(label, font, label_rect.width),
                             True, fg)
            self.window.blit(ts, ts.get_rect(center=label_rect.center))
            # The click region tracks the *base* rect (not the lifted one),
            # so hovering doesn't shift the click target. Disabled keys
            # are recorded so the click handler can surface the reason
            # rather than silently swallowing the click.
            self._action_button_rects[key] = br
            if hovered and is_disabled and hovered_tooltip is None:
                hovered_tooltip = (br, disabled_reason)
            if is_disabled:
                # Remember why so _trigger_action can show a banner.
                if not hasattr(self, '_disabled_action_reasons'):
                    self._disabled_action_reasons = {}
                self._disabled_action_reasons[key] = disabled_reason
            else:
                if hasattr(self, '_disabled_action_reasons'):
                    self._disabled_action_reasons.pop(key, None)
        # Draw any active tooltip last so it sits above the buttons.
        if hovered_tooltip is not None:
            self._draw_action_tooltip(*hovered_tooltip)

    def _draw_action_tooltip(self, anchor_rect: pygame.Rect, text: str) -> None:
        if not text:
            return
        font = settings.get_font(max(9, int(settings.FS_TINY * 0.85)))
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
