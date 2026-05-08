# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Round ledger / total resolve circle for the unified conquer screen.

Renders a horizontal band along the bottom of the screen showing the
state of all three battle rounds as pill-shaped cards plus a "total"
card with a centred resolve circle.

Each round card is laid out as ``[you chip | diff pill | opp chip]``.

* "you chip" — the tactic this player committed to that round (or a
  hollow placeholder).
* "diff pill" — colour-blind-safe direction glyph (▲ player wins, ▼
  opponent wins, = tie) plus the absolute power delta.
* "opp chip" — the opponent's revealed tactic (or "?" if hidden).

The total card sits at the right and shows a circle whose colour
indicates the cumulative result. When the battle has resolved, the
circle morphs into a win/lose chip and is clickable: ``handle_event``
returns ``'open_result'`` if the user clicks it.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pygame

from config import settings
from game.components.conquer_layout import compute_conquer_layout


_BG_RGBA = (38, 29, 22, 218)
_CARD_BG_RGBA = (28, 22, 16, 230)
_BORDER_RGBA = (122, 92, 56)
_TEXT_PRIMARY = (238, 218, 170)
_TEXT_SECONDARY = (170, 152, 110)
_TEXT_MUTED = (132, 116, 86)
_WIN_GREEN = (110, 180, 110)
_LOSE_RED = (200, 90, 90)
_TIE_GREY = (180, 180, 180)
_GHOST_BLUE = (120, 205, 220)
_GHOST_RGBA = (68, 112, 122, 92)


class ConquerRoundLedger:
    """Bottom ledger band: 3 round cards + total resolve card.

    Parameters
    ----------
    parent : object
        The ``ConquerGameScreen`` (used for ``state.game`` and the
        battle subscreen which holds opponent round plays).
    """

    def __init__(self, parent):
        self._parent = parent
        self.window: pygame.Surface = parent.window
        self._layout = None
        self._cached_screen_size = None
        self._cached_mode = None
        self._total_circle_rect: Optional[pygame.Rect] = None

    # ------------------------------------------------------------------ data
    def _game(self):
        return getattr(self._parent.state, 'game', None)

    def _player_played_per_round(self) -> List[Optional[Dict[str, Any]]]:
        """3-slot array of this player's played moves indexed by round."""
        moves = []
        try:
            moves = list(self._parent._current_conquer_battle_moves() or [])
        except Exception:
            moves = []
        slots: List[Optional[Dict[str, Any]]] = [None, None, None]
        for m in moves:
            pr = m.get('played_round')
            if pr in (0, 1, 2):
                slots[pr] = m
        return slots

    def _opp_played_per_round(self) -> List[Optional[Dict[str, Any]]]:
        """Opponent's played moves indexed by round (best-effort)."""
        slots: List[Optional[Dict[str, Any]]] = [None, None, None]
        battle = None
        try:
            battle = self._parent.subscreens.get('battle')
        except Exception:
            return slots
        opp_played = getattr(battle, 'opp_played', None) if battle else None
        if isinstance(opp_played, list) and len(opp_played) >= 3:
            for i in range(3):
                slots[i] = opp_played[i]
        return slots

    @staticmethod
    def _power(move: Optional[Dict[str, Any]]) -> int:
        if move is None:
            return 0
        if move.get('_skipped') or move.get('family_name') == 'Skip':
            return 0
        if move.get('family_name') == 'Block':
            return 0
        return int(move.get('value') or 0)

    def _round_diff(self, you, opp) -> int:
        return self._power(you) - self._power(opp)

    def _ghost_preview(self, you_per) -> Optional[Tuple[int, Dict[str, Any]]]:
        game = self._game()
        if not game or getattr(game, 'last_battle_result', None):
            return None
        round_idx = int(getattr(game, 'battle_round', 0) or 0) - 1
        if round_idx not in (0, 1, 2):
            return None
        if you_per[round_idx] is not None:
            return None
        rail = getattr(self._parent, '_tactics_rail', None)
        preview = getattr(rail, 'preview_move', None)
        if not callable(preview):
            return None
        move = preview()
        if not isinstance(move, dict):
            return None
        if move.get('played_round') is not None:
            return None
        if move.get('status', 'available') != 'available':
            return None
        return round_idx, move

    def _total_diff(self, you_per, opp_per) -> int:
        return sum(
            (self._round_diff(y, o) if y and o else 0)
            for y, o in zip(you_per, opp_per)
        )

    def _ghost_total_diff(self, you_per, opp_per, ghost_preview) -> int:
        total = self._total_diff(you_per, opp_per)
        if not ghost_preview:
            return total
        round_idx, move = ghost_preview
        if you_per[round_idx] is not None:
            return total
        opp = opp_per[round_idx]
        if opp is not None:
            return total + self._round_diff(move, opp)
        return total + self._power(move)

    # ------------------------------------------------------------------ layout
    def _ensure_layout(self):
        size = (settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT)
        game = self._game()
        mode = 'pre_battle'
        if game is not None:
            if getattr(game, 'last_battle_result', None):
                mode = 'result'
            elif (getattr(game, 'battle_turn_player_id', None) is not None
                  or getattr(game, 'battle_round', 0) in (1, 2, 3)):
                mode = 'battle'
        if (self._layout is None
                or size != self._cached_screen_size
                or mode != self._cached_mode):
            self._layout = compute_conquer_layout(*size, mode=mode)
            self._cached_screen_size = size
            self._cached_mode = mode
        return self._layout

    def rect(self) -> pygame.Rect:
        return pygame.Rect(*self._ensure_layout().round_ledger.rect)

    # ------------------------------------------------------------------ events
    def handle_event(self, event) -> Optional[str]:
        """Return ``'open_result'`` when the user clicks the resolved circle."""
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return None
        if self._total_circle_rect is None:
            return None
        if not self._total_circle_rect.collidepoint(event.pos):
            return None
        game = self._game()
        if not game or not getattr(game, 'last_battle_result', None):
            return None
        return 'open_result'

    # ------------------------------------------------------------------ draw
    def draw(self):
        layout = self._ensure_layout()
        ledger = layout.round_ledger
        outer = pygame.Rect(*ledger.rect)
        bg = pygame.Surface(outer.size, pygame.SRCALPHA)
        bg.fill(_BG_RGBA)
        self.window.blit(bg, outer.topleft)
        pygame.draw.rect(self.window, _BORDER_RGBA, outer, 2, border_radius=8)

        you_per = self._player_played_per_round()
        opp_per = self._opp_played_per_round()
        ghost_preview = self._ghost_preview(you_per)
        cur_round = int(getattr(self._game(), 'battle_round', 0) or 0)

        for i, rect_tuple in enumerate(ledger.round_card_rects):
            ghost_move = ghost_preview[1] if ghost_preview and ghost_preview[0] == i else None
            self._draw_round_card(pygame.Rect(*rect_tuple), i, you_per[i],
                                  opp_per[i], cur_round, ghost_move=ghost_move)
        self._draw_total_card(pygame.Rect(*ledger.total_card_rect),
                              pygame.Rect(*ledger.total_circle_rect),
                              you_per, opp_per, ghost_preview=ghost_preview)

    # -- round card
    def _draw_round_card(self, rect: pygame.Rect, idx: int,
                         you, opp, cur_round: int, ghost_move=None):
        is_active = (cur_round - 1) == idx if cur_round in (1, 2, 3) else False
        bg = pygame.Surface(rect.size, pygame.SRCALPHA)
        bg.fill(_CARD_BG_RGBA)
        self.window.blit(bg, rect.topleft)
        border = (210, 168, 72) if is_active else _BORDER_RGBA
        pygame.draw.rect(self.window, border, rect, 2, border_radius=6)

        title_font = settings.get_font(max(10, int(settings.FS_TINY * 0.95)), bold=True)
        ts = title_font.render(f'Round {idx + 1}', True, _TEXT_SECONDARY)
        self.window.blit(ts, (rect.left + 6, rect.top + 4))

        # Three columns: you-chip | diff | opp-chip
        chip_w = int(rect.width * 0.34)
        diff_w = rect.width - chip_w * 2
        chip_y = rect.top + 4 + ts.get_height() + 4
        chip_h = rect.bottom - chip_y - 6
        you_rect = pygame.Rect(rect.left + 4, chip_y, chip_w - 8, chip_h)
        diff_rect = pygame.Rect(rect.left + chip_w, chip_y, diff_w, chip_h)
        opp_rect = pygame.Rect(rect.right - chip_w + 4, chip_y, chip_w - 8, chip_h)

        display_you = you if you is not None else ghost_move
        is_ghost = bool(ghost_move is not None and you is None)
        self._draw_player_chip(you_rect, display_you, is_player_self=True,
                               ghost=is_ghost)
        self._draw_player_chip(opp_rect, opp, is_player_self=False)
        self._draw_diff_pill(diff_rect, you, opp,
                             played=(you is not None and opp is not None),
                             ghost_move=ghost_move)

    def _draw_player_chip(self, rect: pygame.Rect, move, is_player_self: bool,
                          *, ghost: bool = False):
        if ghost:
            overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
            overlay.fill(_GHOST_RGBA)
            self.window.blit(overlay, rect.topleft)
            pygame.draw.rect(self.window, _GHOST_BLUE, rect, 2, border_radius=4)
        else:
            pygame.draw.rect(self.window, (20, 14, 10), rect, 0, border_radius=4)
            pygame.draw.rect(self.window, _BORDER_RGBA, rect, 1, border_radius=4)
        if move is None:
            ph_font = settings.get_font(max(11, int(settings.FS_SMALL * 0.95)), bold=True)
            label = '—' if is_player_self else '?'
            ts = ph_font.render(label, True, _TEXT_MUTED)
            self.window.blit(ts, ts.get_rect(center=rect.center))
            return
        if move.get('_skipped') or move.get('family_name') == 'Skip':
            ph_font = settings.get_font(max(10, int(settings.FS_TINY * 0.95)), bold=True)
            ts = ph_font.render('Skip', True, _TEXT_MUTED)
            self.window.blit(ts, ts.get_rect(center=rect.center))
            return
        # Family + power
        name = move.get('family_name', '?')
        if name == 'Dagger' and move.get('card_id_b'):
            name = '2x Dagger'
        name_font = settings.get_font(max(9, int(settings.FS_TINY * 0.9)), bold=True)
        pwr_font = settings.get_font(max(13, int(settings.FS_SMALL * 1.1)), bold=True)
        text_col = _GHOST_BLUE if ghost else _TEXT_SECONDARY
        power_col = _GHOST_BLUE if ghost else _TEXT_PRIMARY
        ns = name_font.render(name[:14], True, text_col)
        ps = pwr_font.render(str(self._power(move)), True, power_col)
        self.window.blit(ns, (rect.left + 4, rect.top + 2))
        self.window.blit(ps, (rect.right - ps.get_width() - 4,
                              rect.bottom - ps.get_height() - 2))

    def _draw_diff_pill(self, rect: pygame.Rect, you, opp, played: bool,
                        ghost_move=None):
        if not played:
            if ghost_move is not None:
                self._draw_ghost_diff_pill(rect, ghost_move, opp)
                return
            font = settings.get_font(max(13, int(settings.FS_SMALL * 1.0)), bold=True)
            ts = font.render('vs', True, _TEXT_MUTED)
            self.window.blit(ts, ts.get_rect(center=rect.center))
            return
        diff = self._round_diff(you, opp)
        if diff > 0:
            glyph, col = '▲', _WIN_GREEN
        elif diff < 0:
            glyph, col = '▼', _LOSE_RED
        else:
            glyph, col = '=', _TIE_GREY
        pill = rect.inflate(-rect.width // 4, -rect.height // 3)
        pygame.draw.rect(self.window, (10, 8, 6), pill, 0, border_radius=8)
        pygame.draw.rect(self.window, col, pill, 2, border_radius=8)
        font = settings.get_font(max(13, int(settings.FS_SMALL * 1.0)), bold=True)
        ts = font.render(f'{glyph}{abs(diff)}', True, col)
        self.window.blit(ts, ts.get_rect(center=pill.center))

    def _draw_ghost_diff_pill(self, rect: pygame.Rect, move, opp):
        diff = self._round_diff(move, opp) if opp is not None else self._power(move)
        if diff > 0:
            glyph = '▲'
        elif diff < 0:
            glyph = '▼'
        else:
            glyph = '='
        pill = rect.inflate(-rect.width // 4, -rect.height // 3)
        overlay = pygame.Surface(pill.size, pygame.SRCALPHA)
        overlay.fill(_GHOST_RGBA)
        self.window.blit(overlay, pill.topleft)
        pygame.draw.rect(self.window, _GHOST_BLUE, pill, 2, border_radius=8)
        font = settings.get_font(max(13, int(settings.FS_SMALL * 1.0)), bold=True)
        ts = font.render(f'{glyph}{abs(diff)}', True, _GHOST_BLUE)
        self.window.blit(ts, ts.get_rect(center=pill.center))

    # -- total card
    def _draw_total_card(self, rect: pygame.Rect, circle_rect: pygame.Rect,
                         you_per, opp_per, ghost_preview=None):
        bg = pygame.Surface(rect.size, pygame.SRCALPHA)
        bg.fill(_CARD_BG_RGBA)
        self.window.blit(bg, rect.topleft)
        pygame.draw.rect(self.window, _BORDER_RGBA, rect, 2, border_radius=6)
        title_font = settings.get_font(max(10, int(settings.FS_TINY * 0.95)), bold=True)
        ts = title_font.render('Total', True, _TEXT_SECONDARY)
        self.window.blit(ts, (rect.left + 6, rect.top + 4))

        total_diff = self._ghost_total_diff(you_per, opp_per, ghost_preview)
        played_count = sum(1 for y, o in zip(you_per, opp_per) if y and o)
        game = self._game()
        last_result = getattr(game, 'last_battle_result', None) if game else None

        if last_result:
            outcome = last_result.get('outcome') if isinstance(last_result, dict) else None
            if outcome == 'win':
                col = _WIN_GREEN
                label = 'WIN'
            elif outcome == 'loss':
                col = _LOSE_RED
                label = 'LOSE'
            else:
                col = _TIE_GREY
                label = 'TIE'
        else:
            if ghost_preview:
                col = _GHOST_BLUE
                label = f'{total_diff:+d}'
            else:
                if total_diff > 0:
                    col = _WIN_GREEN
                elif total_diff < 0:
                    col = _LOSE_RED
                else:
                    col = _TIE_GREY
                label = f'{total_diff:+d}' if played_count else '–'

        # Circle
        cx = circle_rect.centerx
        cy = circle_rect.centery
        radius = min(circle_rect.width, circle_rect.height) // 2 - 4
        pygame.draw.circle(self.window, (16, 12, 8), (cx, cy), radius)
        pygame.draw.circle(self.window, col, (cx, cy), radius, 3)
        if ghost_preview:
            pygame.draw.circle(self.window, _GHOST_BLUE, (cx, cy), max(1, radius - 7), 1)
        font = settings.get_font(max(14, int(settings.FS_SMALL * 1.15)), bold=True)
        ts = font.render(label, True, col)
        self.window.blit(ts, ts.get_rect(center=(cx, cy)))
        # Hover hint
        if last_result:
            hint = settings.get_font(max(9, int(settings.FS_TINY * 0.85)))
            hs = hint.render('click for details', True, _TEXT_MUTED)
            self.window.blit(hs, (rect.centerx - hs.get_width() // 2,
                                  rect.bottom - hs.get_height() - 3))
        # Cache for click handling
        self._total_circle_rect = pygame.Rect(cx - radius, cy - radius,
                                              radius * 2, radius * 2)
