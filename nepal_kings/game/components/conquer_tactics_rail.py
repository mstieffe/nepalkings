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
        # Snapshot of move IDs from the previous frame so we can detect
        # newly-added moves (used to start the new-move glow on gamble).
        self._prev_move_ids: set = set()
        # Coin-flip animation state for gambled tactic. (#8c)
        # ``{'move_id': int, 'started_at': ms, 'duration': ms}`` or None.
        self._gamble_anim: Optional[Dict[str, Any]] = None
        # Drag-and-drop combine state. (#8b)
        self._drag_origin_id: Optional[int] = None
        self._drag_pos: Optional[tuple] = None
        self._drag_active: bool = False

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
            and m.get('status', 'available') == 'available'
        ]

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

    def _power(self, move: Dict[str, Any]) -> int:
        display_power = getattr(self._parent, '_conquer_tactic_display_power', None)
        if callable(display_power):
            try:
                return int(display_power(move) or 0)
            except Exception:
                pass
        if move.get('family_name') == 'Block':
            return 0
        return int(move.get('value') or 0)

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
        mode = 'pre_battle'
        if game is not None:
            if getattr(game, 'last_battle_result', None):
                mode = 'result'
            elif (getattr(game, 'battle_turn_player_id', None) is not None
                  or getattr(game, 'battle_round', 0) in (1, 2, 3)):
                mode = 'battle'
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

    NEW_MOVE_GLOW_MS = 1500
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

    def mark_new_moves(self, move_ids) -> None:
        """Glow these move IDs for ``NEW_MOVE_GLOW_MS`` (#8c)."""
        if not move_ids:
            return
        expires = pygame.time.get_ticks() + self.NEW_MOVE_GLOW_MS
        for mid in move_ids:
            try:
                self._new_move_glow_until[int(mid)] = expires
            except Exception:
                continue

    def _detect_new_moves(self) -> None:
        """Auto-glow any move that wasn't visible last frame (#8c)."""
        try:
            current = {int(m.get('id') or 0) for m in self._hand_moves()}
        except Exception:
            current = set()
        # Skip the very first frame (empty prev set would glow everything).
        if self._prev_move_ids and current:
            new_ids = current - self._prev_move_ids
            if new_ids:
                self.mark_new_moves(new_ids)
        self._prev_move_ids = current
        # Drop stale glow entries.
        now = pygame.time.get_ticks()
        self._new_move_glow_until = {
            mid: exp for mid, exp in self._new_move_glow_until.items()
            if exp > now
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
        for rect, mid in zip(self._cell_rects, self._cell_move_ids):
            if rect.collidepoint(pos):
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
        total = len(self._hand_moves())
        rail = layout.tactics_rail
        visible = max(1, min(
            rail.cells_visible,
            max(1, rail.hand_list_rect[3] // max(1, rail.cell_height)),
        ))
        self._scroll = max(0, min(self._scroll, max(0, total - visible)))

    def _handle_cell_click(self, mid: int):
        if self._combine_pending and self._selected_id is not None and mid != self._selected_id:
            self._combine_partner_id = mid
            return
        # Plain selection / toggle.
        self._selected_id = None if self._selected_id == mid else mid
        self._combine_pending = False
        self._combine_partner_id = None

    def _trigger_action(self, key: str):
        sel = self._selected_move()
        if key == ACTION_SKIP:
            if self._is_my_battle_turn():
                self._pending_action = {'action': ACTION_SKIP}
            return
        if not sel:
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
    def draw(self):
        layout = self._ensure_layout()
        rail = layout.tactics_rail
        rail_rect = pygame.Rect(*rail.rect)
        previous_clip = self.window.get_clip()
        self.window.set_clip(rail_rect)

        # Detect newly-added moves so we can glow them (#8c) and expire
        # the banner if its TTL has passed (#8a).
        self._detect_new_moves()
        if self._result_banner and self._result_banner.get('expires_at'):
            if pygame.time.get_ticks() > self._result_banner['expires_at']:
                self._result_banner = None

        bg = pygame.Surface(rail_rect.size, pygame.SRCALPHA)
        bg.fill(_BG_RGBA)
        self.window.blit(bg, rail_rect.topleft)
        pygame.draw.rect(self.window, _BORDER_RGBA, rail_rect, 2, border_radius=8)

        self._draw_top_strip(pygame.Rect(*rail.top_strip_rect))
        self._draw_hand_list(pygame.Rect(*rail.hand_list_rect), rail.cell_height,
                             rail.cells_visible)
        self._draw_selected_detail(pygame.Rect(*rail.selected_detail_rect))
        self._draw_action_tray(pygame.Rect(*rail.action_tray_rect))
        self.window.set_clip(previous_clip)

    # -- top strip
    def _draw_top_strip(self, rect: pygame.Rect):
        if self._result_banner:
            self._draw_result_banner(rect)
            return
        game = getattr(self._parent.state, 'game', None)
        rd = getattr(game, 'battle_round', 0) if game else 0
        my_turn = self._is_my_battle_turn()
        if game is None or getattr(game, 'battle_turn_player_id', None) is None:
            line1 = 'Tactics hand'
            line2 = f'{len(self._hand_moves())} available'
        else:
            who = 'Your turn' if my_turn else "Opponent's turn"
            line1 = f'Round {rd}/3 — {who}'
            line2 = self._opponent_intent_hint(game)
        font = settings.get_font(max(11, int(settings.FS_SMALL * 0.95)), bold=True)
        sub = settings.get_font(max(10, int(settings.FS_TINY * 0.95)))
        s1 = font.render(self._fit_text(line1, font, rect.width - 16), True, _TEXT_PRIMARY)
        s2 = sub.render(self._fit_text(line2, sub, rect.width - 16), True, _TEXT_SECONDARY)
        self.window.blit(s1, (rect.x + 8, rect.y + 4))
        self.window.blit(s2, (rect.x + 8, rect.y + 4 + s1.get_height() + 2))

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
        font = settings.get_font(max(11, int(settings.FS_SMALL * 0.95)), bold=True)
        sub = settings.get_font(max(9, int(settings.FS_TINY * 0.8)))
        s1 = font.render(self._fit_text(text, font, rect.width - 16), True, color)
        self.window.blit(s1, (rect.x + 8, rect.y + 4))
        hint = sub.render('(click anywhere to dismiss)', True, _TEXT_MUTED)
        self.window.blit(hint, (rect.x + 8, rect.y + 4 + s1.get_height() + 1))

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
        moves = self._hand_moves_grouped()
        self._clamp_scroll()
        self._cell_rects = []
        self._cell_move_ids = []
        self._hovered_id = None
        if not moves:
            empty_font = settings.get_font(max(11, int(settings.FS_SMALL * 0.9)))
            t = empty_font.render('— hand empty —', True, _TEXT_MUTED)
            self.window.blit(t, t.get_rect(center=rect.center))
            self.window.set_clip(previous_clip)
            return
        visible_count = max(1, min(cells_visible, rect.height // max(1, cell_h)))
        visible = moves[self._scroll:self._scroll + visible_count]
        # Draw scroll indicators if needed.
        if self._scroll > 0:
            up = pygame.Rect(rect.right - 18, rect.top + 2, 14, 12)
            pygame.draw.polygon(self.window, _TEXT_PRIMARY,
                                [(up.centerx, up.top), (up.left, up.bottom),
                                 (up.right, up.bottom)])
            self._scroll_up_rect = up
        else:
            self._scroll_up_rect = None
        if self._scroll + visible_count < len(moves):
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
        last_group: Optional[str] = None
        y = rect.top
        for move in visible:
            group = self._family_group(move)
            # Only draw a header at *transitions* between groups; the rail
            # already has a section header above this list, so the first
            # group does not need an extra mini-header (and skipping it
            # also keeps cell-fit budgets stable).
            if (last_group is not None and group != last_group
                    and y + self.HEADER_H <= rect.bottom):
                header_rect = pygame.Rect(rect.left, y, rect.width, self.HEADER_H)
                self._draw_family_header(header_rect, group + 's' if not group.endswith('s') else group)
                y += self.HEADER_H
            last_group = group
            if y + cell_h > rect.bottom + 2:
                break
            cell_rect = pygame.Rect(rect.left, y, rect.width, cell_h - 2)
            hovered = cell_rect.collidepoint(mouse_pos)
            if hovered:
                self._hovered_id = int(move.get('id') or 0)
            self._draw_hand_cell(cell_rect, move, font, chip_font, hovered=hovered)
            self._cell_rects.append(cell_rect)
            self._cell_move_ids.append(int(move.get('id') or 0))
            y += cell_h
        # Drag ghost (#8b) — drawn last so it floats over cells.
        if self._drag_active and self._drag_origin_id is not None and self._drag_pos:
            origin_move = next((m for m in self._hand_moves()
                                if int(m.get('id') or 0) == self._drag_origin_id), None)
            if origin_move is not None:
                self._draw_drag_ghost(origin_move, self._drag_pos)
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

        # New-move glow (#8c) — short pulse on freshly added moves.
        mid = int(move.get('id') or 0)
        glow_until = self._new_move_glow_until.get(mid)
        now = pygame.time.get_ticks()
        if glow_until and glow_until > now:
            phase = (now % 600) / 600.0
            pulse = 1.0 - abs(0.5 - phase) * 2.0
            alpha = int(120 + 110 * pulse)
            glow_surf = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(glow_surf, (250, 226, 130, alpha),
                             glow_surf.get_rect().inflate(-2, -2), 3,
                             border_radius=4)
            self.window.blit(glow_surf, rect.topleft)

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

        # Power (right edge)
        pwr_font = settings.get_font(max(13, int(settings.FS_SMALL * 1.05)), bold=True)
        pwr_surf = pwr_font.render(str(self._power(move)), True, _TEXT_PRIMARY)
        max_text_w = max(24, rect.right - text_x - pwr_surf.get_width() - 18)

        name_surf = font.render(self._fit_text(name, font, max_text_w), True, _TEXT_PRIMARY)
        self.window.blit(name_surf, (text_x, rect.top + 6))

        chip_text = f"{move.get('suit', '?')[:1]} {move.get('rank', '?')}"
        chip_surf = chip_font.render(
            self._fit_text(chip_text, chip_font, max_text_w), True, _TEXT_SECONDARY)
        self.window.blit(chip_surf, (text_x, rect.top + 6 + name_surf.get_height() + 1))

        self.window.blit(pwr_surf, (rect.right - pwr_surf.get_width() - 8, rect.centery - pwr_surf.get_height() // 2))

        # Strongest-move badge (#8d) — small star/spark glyph on the
        # currently highest-power move.
        if mid == self._strongest_move_id():
            badge_font = settings.get_font(max(10, int(settings.FS_TINY * 0.9)), bold=True)
            badge_surf = badge_font.render('★', True, (250, 220, 110))
            self.window.blit(badge_surf, (rect.left + 4, rect.top + 2))

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
        # Source
        source_line = f"Source: card #{sel.get('card_id', '?')}"
        src = body_font.render(
            self._fit_text(source_line, body_font, rect.width - 16), True, _TEXT_MUTED)
        self.window.blit(src, (rect.left + 8, rect.top + 6 + ts.get_height() + 2 + bs.get_height() + 2))

    # -- action tray
    def _draw_action_tray(self, rect: pygame.Rect):
        """Always render Play / Gamble / Combine / Dismantle / Skip with
        per-button enabled state + reason tooltip when disabled (#8d).
        """
        sel = self._selected_move()
        my_turn = self._is_my_battle_turn()
        partner = self._combine_partner_move()
        hand_empty = not self._hand_moves()

        # Build (key, label, enabled, reason) for every action.
        buttons = []
        # Play
        if not sel:
            buttons.append((ACTION_PLAY, 'Play', False, 'Pick a tactic first'))
        elif not my_turn:
            buttons.append((ACTION_PLAY, 'Play', False, 'Not your battle turn'))
        else:
            buttons.append((ACTION_PLAY, 'Play', True, ''))
        # Gamble
        if not sel:
            buttons.append((ACTION_GAMBLE, 'Gamble', False, 'Pick a tactic first'))
        else:
            buttons.append((ACTION_GAMBLE, 'Gamble', True, ''))
        # Combine
        if not sel:
            combine_label = 'Combine'
            buttons.append((ACTION_COMBINE, combine_label, False, 'Pick a single Dagger first'))
        elif not self._is_single_dagger(sel):
            buttons.append((ACTION_COMBINE, 'Combine', False, 'Only single Daggers can combine'))
        elif self._combine_pending and partner is None:
            buttons.append((ACTION_COMBINE, 'Pick 2nd', True, ''))
        elif partner is not None and not self._can_combine(sel, partner):
            buttons.append((ACTION_COMBINE, 'Combine', False, 'Need 2 same-colour Daggers'))
        else:
            buttons.append((ACTION_COMBINE, 'Combine', True, ''))
        # Dismantle
        if not sel:
            buttons.append((ACTION_DISMANTLE, 'Dismantle', False, 'Pick a Double Dagger first'))
        elif not self._is_double_dagger(sel):
            buttons.append((ACTION_DISMANTLE, 'Dismantle', False, 'Only Double Daggers can be dismantled'))
        else:
            buttons.append((ACTION_DISMANTLE, 'Dismantle', True, ''))
        # Skip — only useful when it's your turn and you have nothing to play.
        if my_turn and hand_empty:
            buttons.append((ACTION_SKIP, 'Skip', True, ''))
        elif not my_turn:
            buttons.append((ACTION_SKIP, 'Skip', False, 'Not your battle turn'))
        else:
            buttons.append((ACTION_SKIP, 'Skip', False, 'Use a tactic instead of skipping'))

        font = settings.get_font(max(10, int(settings.FS_TINY * 0.9)), bold=True)
        gap = 3
        n = len(buttons)
        bw = max(1, (rect.width - gap * (n - 1)) // n)
        self._action_button_rects = {}
        # Track all rects for hover-tooltip lookup (incl. disabled).
        self._action_button_meta = []
        # Pre-compute strongest-move highlight on Play.
        sel_id = sel.get('id') if sel else None
        play_glow = bool(sel_id is not None and sel_id == self._strongest_move_id())
        try:
            mx, my = pygame.mouse.get_pos()
        except Exception:
            mx, my = (-1, -1)
        hovered_meta = None
        for i, (key, label, enabled, reason) in enumerate(buttons):
            br = pygame.Rect(rect.left + i * (bw + gap), rect.top, bw,
                             rect.height)
            colour = (62, 50, 36) if enabled else (30, 26, 22)
            border = _BORDER_RGBA if enabled else _DISABLED_RGBA
            text_col = _TEXT_PRIMARY if enabled else _DISABLED_RGBA
            pygame.draw.rect(self.window, colour, br, 0, border_radius=4)
            pygame.draw.rect(self.window, border, br, 1, border_radius=4)
            # Strongest-move glow on Play (#8d).
            if enabled and key == ACTION_PLAY and play_glow:
                now = pygame.time.get_ticks()
                phase = (now % 1000) / 1000.0
                pulse = 1.0 - abs(0.5 - phase) * 2.0
                alpha = int(110 + 110 * pulse)
                glow_surf = pygame.Surface(br.size, pygame.SRCALPHA)
                pygame.draw.rect(glow_surf, (250, 220, 110, alpha),
                                 glow_surf.get_rect().inflate(-2, -2), 2,
                                 border_radius=4)
                self.window.blit(glow_surf, br.topleft)
            ts = font.render(self._fit_text(label, font, br.width - 4), True, text_col)
            self.window.blit(ts, ts.get_rect(center=br.center))
            if enabled:
                self._action_button_rects[key] = br
            self._action_button_meta.append((key, br, enabled, reason))
            if br.collidepoint(mx, my) and not enabled and reason:
                hovered_meta = (br, reason)
        # Tooltip for hovered disabled button.
        if hovered_meta is not None:
            br, reason = hovered_meta
            tip_font = settings.get_font(max(9, int(settings.FS_TINY * 0.85)))
            tip_surf = tip_font.render(reason, True, _TEXT_PRIMARY)
            tip_w = tip_surf.get_width() + 10
            tip_h = tip_surf.get_height() + 6
            tip_x = max(rect.left, min(br.centerx - tip_w // 2,
                                       rect.right - tip_w))
            tip_y = br.top - tip_h - 2
            if tip_y < rect.top - tip_h - 2:
                tip_y = br.bottom + 2
            tip_rect = pygame.Rect(tip_x, tip_y, tip_w, tip_h)
            bg = pygame.Surface(tip_rect.size, pygame.SRCALPHA)
            bg.fill((20, 16, 12, 232))
            self.window.blit(bg, tip_rect.topleft)
            pygame.draw.rect(self.window, _BORDER_RGBA, tip_rect, 1,
                             border_radius=3)
            self.window.blit(tip_surf, (tip_rect.x + 5, tip_rect.y + 3))
