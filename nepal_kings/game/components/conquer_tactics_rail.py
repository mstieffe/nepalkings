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
        self._action_button_rects: Dict[str, pygame.Rect] = {}
        self._scroll_up_rect: Optional[pygame.Rect] = None
        self._scroll_down_rect: Optional[pygame.Rect] = None
        # Pending action consumed by the parent each frame.
        self._pending_action: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------ data
    def _moves(self) -> List[Dict[str, Any]]:
        try:
            return list(self._parent._current_conquer_battle_moves() or [])
        except Exception:
            return []

    def _hand_moves(self) -> List[Dict[str, Any]]:
        return [m for m in self._moves() if m.get('played_round') is None]

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

    @staticmethod
    def _power(move: Dict[str, Any]) -> int:
        if move.get('family_name') == 'Block':
            return 0
        return int(move.get('value') or 0)

    @staticmethod
    def _can_combine(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
        """Two single Daggers of the same colour can combine into a Double Dagger."""
        if a.get('id') == b.get('id'):
            return False
        if a.get('family_name') != 'Dagger' or b.get('family_name') != 'Dagger':
            return False
        # Same colour group: hearts/diamonds (red) vs spades/clubs (black)
        red = {'Hearts', 'Diamonds'}
        black = {'Spades', 'Clubs'}
        sa, sb = a.get('suit'), b.get('suit')
        return (sa in red and sb in red) or (sa in black and sb in black)

    @staticmethod
    def _is_double_dagger(move: Dict[str, Any]) -> bool:
        return move.get('family_name') == 'Dagger' and bool(move.get('card_id_b'))

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
        self._combine_partner_id = None
        self._combine_pending = False
        self._pending_action = None

    def reset_after_action(self):
        """Clear ephemeral state after a server action completed."""
        self.reset_selection()

    # ------------------------------------------------------------------ events
    def handle_event(self, event) -> bool:
        """Returns True if the rail consumed the event."""
        if event.type not in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEWHEEL):
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
        if event.button != 1:
            return False
        pos = event.pos
        if not rail_rect.collidepoint(pos):
            return False
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
                return True
        return True  # consumed even if hit empty space inside the rail

    def _clamp_scroll(self):
        layout = self._ensure_layout()
        total = len(self._hand_moves())
        visible = max(1, layout.tactics_rail.cells_visible)
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
            self._pending_action = {'action': ACTION_GAMBLE, 'move': sel}
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

        bg = pygame.Surface(rail_rect.size, pygame.SRCALPHA)
        bg.fill(_BG_RGBA)
        self.window.blit(bg, rail_rect.topleft)
        pygame.draw.rect(self.window, _BORDER_RGBA, rail_rect, 2, border_radius=8)

        self._draw_top_strip(pygame.Rect(*rail.top_strip_rect))
        self._draw_hand_list(pygame.Rect(*rail.hand_list_rect), rail.cell_height,
                             rail.cells_visible)
        self._draw_selected_detail(pygame.Rect(*rail.selected_detail_rect))
        self._draw_action_tray(pygame.Rect(*rail.action_tray_rect))

    # -- top strip
    def _draw_top_strip(self, rect: pygame.Rect):
        game = getattr(self._parent.state, 'game', None)
        rd = getattr(game, 'battle_round', 0) if game else 0
        my_turn = self._is_my_battle_turn()
        if game is None or getattr(game, 'battle_turn_player_id', None) is None:
            line1 = 'Pre-battle hand'
            line2 = 'Use Gamble / Combine to shape your tactics'
        else:
            who = 'Your turn' if my_turn else "Opponent's turn"
            line1 = f'Round {rd}/3 — {who}'
            line2 = self._opponent_intent_hint(game)
        font = settings.get_font(max(11, int(settings.FS_SMALL * 0.95)), bold=True)
        sub = settings.get_font(max(10, int(settings.FS_TINY * 0.95)))
        s1 = font.render(line1, True, _TEXT_PRIMARY)
        s2 = sub.render(line2, True, _TEXT_SECONDARY)
        self.window.blit(s1, (rect.x + 8, rect.y + 4))
        self.window.blit(s2, (rect.x + 8, rect.y + 4 + s1.get_height() + 2))

    def _opponent_intent_hint(self, game) -> str:
        opp_id = getattr(game, 'battle_turn_player_id', None)
        if opp_id is None or opp_id == getattr(game, 'player_id', None):
            return 'Pick a tactic'
        return 'Awaiting opponent...'

    # -- hand list
    def _draw_hand_list(self, rect: pygame.Rect, cell_h: int, cells_visible: int):
        moves = self._hand_moves()
        self._clamp_scroll()
        self._cell_rects = []
        self._cell_move_ids = []
        if not moves:
            empty_font = settings.get_font(max(11, int(settings.FS_SMALL * 0.9)))
            t = empty_font.render('— hand empty —', True, _TEXT_MUTED)
            self.window.blit(t, t.get_rect(center=rect.center))
            return
        visible = moves[self._scroll:self._scroll + cells_visible]
        # Draw scroll indicators if needed.
        if self._scroll > 0:
            up = pygame.Rect(rect.right - 18, rect.top + 2, 14, 12)
            pygame.draw.polygon(self.window, _TEXT_PRIMARY,
                                [(up.centerx, up.top), (up.left, up.bottom),
                                 (up.right, up.bottom)])
            self._scroll_up_rect = up
        else:
            self._scroll_up_rect = None
        if self._scroll + cells_visible < len(moves):
            dn = pygame.Rect(rect.right - 18, rect.bottom - 14, 14, 12)
            pygame.draw.polygon(self.window, _TEXT_PRIMARY,
                                [(dn.centerx, dn.bottom), (dn.left, dn.top),
                                 (dn.right, dn.top)])
            self._scroll_down_rect = dn
        else:
            self._scroll_down_rect = None

        font = settings.get_font(max(11, int(settings.FS_SMALL * 0.95)), bold=True)
        chip_font = settings.get_font(max(9, int(settings.FS_TINY * 0.85)), bold=True)
        for i, move in enumerate(visible):
            cy = rect.top + i * cell_h
            cell_rect = pygame.Rect(rect.left, cy, rect.width, cell_h - 2)
            self._draw_hand_cell(cell_rect, move, font, chip_font)
            self._cell_rects.append(cell_rect)
            self._cell_move_ids.append(int(move.get('id') or 0))

    def _draw_hand_cell(self, rect: pygame.Rect, move: Dict[str, Any], font, chip_font):
        is_selected = move.get('id') == self._selected_id
        is_partner = move.get('id') == self._combine_partner_id and self._combine_pending
        bg_col = (52, 40, 30, 240) if is_selected else (32, 24, 18, 200)
        bg = pygame.Surface(rect.size, pygame.SRCALPHA)
        bg.fill(bg_col)
        self.window.blit(bg, rect.topleft)
        border_col = _SELECTED_RGBA if is_selected else (_BORDER_RGBA if not is_partner else (130, 200, 250))
        pygame.draw.rect(self.window, border_col, rect, 2, border_radius=4)

        # Icon (left)
        icon_size = max(20, int(rect.height * 0.78))
        try:
            glow_cache, icon_cache, frame_cache, suit_icon_cache, icon_font = (
                self._parent._conquer_battle_move_icon_assets(icon_size))
            cx = rect.left + icon_size // 2 + 6
            cy = rect.centery
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
        name_surf = font.render(name, True, _TEXT_PRIMARY)
        self.window.blit(name_surf, (text_x, rect.top + 6))

        chip_text = f"{move.get('suit', '?')[:1]} {move.get('rank', '?')}"
        chip_surf = chip_font.render(chip_text, True, _TEXT_SECONDARY)
        self.window.blit(chip_surf, (text_x, rect.top + 6 + name_surf.get_height() + 1))

        # Power (right edge)
        pwr_font = settings.get_font(max(13, int(settings.FS_SMALL * 1.05)), bold=True)
        pwr_surf = pwr_font.render(str(self._power(move)), True, _TEXT_PRIMARY)
        self.window.blit(pwr_surf, (rect.right - pwr_surf.get_width() - 8, rect.centery - pwr_surf.get_height() // 2))

    # -- selected detail
    def _draw_selected_detail(self, rect: pygame.Rect):
        pygame.draw.rect(self.window, (24, 18, 14), rect, 0, border_radius=4)
        pygame.draw.rect(self.window, _BORDER_RGBA, rect, 1, border_radius=4)
        sel = self._selected_move()
        title_font = settings.get_font(max(12, int(settings.FS_SMALL * 1.0)), bold=True)
        body_font = settings.get_font(max(10, int(settings.FS_TINY * 0.95)))
        if sel is None:
            t = body_font.render('Select a tactic', True, _TEXT_MUTED)
            self.window.blit(t, t.get_rect(center=rect.center))
            return
        name = sel.get('family_name', '?')
        if self._is_double_dagger(sel):
            name = 'Double Dagger'
        ts = title_font.render(name, True, _TEXT_PRIMARY)
        self.window.blit(ts, (rect.left + 8, rect.top + 6))
        # Suit • rank • power line
        suit_a = sel.get('suit', '?')
        suit_b = sel.get('suit_b')
        rank = sel.get('rank', '?')
        line = f"{suit_a}{('+' + suit_b) if suit_b else ''} • {rank} • Power {self._power(sel)}"
        bs = body_font.render(line, True, _TEXT_SECONDARY)
        self.window.blit(bs, (rect.left + 8, rect.top + 6 + ts.get_height() + 2))
        # Source
        src = body_font.render(f"Source: card #{sel.get('card_id', '?')}",
                               True, _TEXT_MUTED)
        self.window.blit(src, (rect.left + 8, rect.top + 6 + ts.get_height() + 2 + bs.get_height() + 2))

    # -- action tray
    def _draw_action_tray(self, rect: pygame.Rect):
        sel = self._selected_move()
        my_turn = self._is_my_battle_turn()
        partner = self._combine_partner_move()
        play_enabled = bool(sel and my_turn)
        skip_enabled = my_turn
        gamble_enabled = bool(sel)
        dismantle_enabled = bool(sel and self._is_double_dagger(sel))
        combine_enabled = (
            bool(sel) and not self._is_double_dagger(sel)
            and (self._combine_pending or partner is not None)
        )
        # During battle rounds, disable hand-shaping actions (gamble/combine/dismantle).
        # The plan keeps these as in-hand tools used in pre-battle.
        if my_turn or (self._parent.state.game and
                       getattr(self._parent.state.game, 'battle_turn_player_id', None) is not None):
            gamble_enabled = False
            combine_enabled = False
            dismantle_enabled = False

        buttons = [
            (ACTION_PLAY, 'Play', play_enabled),
            (ACTION_GAMBLE, 'Gamble', gamble_enabled),
            (ACTION_COMBINE, 'Combine' + (' →' if self._combine_pending else ''), combine_enabled),
            (ACTION_DISMANTLE, 'Dismantle', dismantle_enabled),
            (ACTION_SKIP, 'Skip', skip_enabled),
        ]
        font = settings.get_font(max(10, int(settings.FS_TINY * 0.95)), bold=True)
        gap = 4
        n = len(buttons)
        bw = max(1, (rect.width - gap * (n - 1)) // n)
        self._action_button_rects = {}
        for i, (key, label, enabled) in enumerate(buttons):
            br = pygame.Rect(rect.left + i * (bw + gap), rect.top, bw,
                             rect.height)
            colour = (62, 50, 36) if enabled else (36, 30, 24)
            border = _BORDER_RGBA if enabled else _DISABLED_RGBA
            text_col = _TEXT_PRIMARY if enabled else _DISABLED_RGBA
            pygame.draw.rect(self.window, colour, br, 0, border_radius=4)
            pygame.draw.rect(self.window, border, br, 1, border_radius=4)
            ts = font.render(label, True, text_col)
            self.window.blit(ts, ts.get_rect(center=br.center))
            self._action_button_rects[key] = br
