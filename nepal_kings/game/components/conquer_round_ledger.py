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
from game.components.battle_moves.battle_move_icon_renderer import draw_battle_move_icon
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


def _draw_diff_glyph(surface, center, size, direction, color):
    """Draw a triangle-up / triangle-down / equals glyph using primitives.

    The default font on some platforms lacks the BMP arrow glyphs (▲/▼) and
    renders them as box tofus. Drawing primitives sidesteps the font issue.

    Parameters
    ----------
    direction : 'up' | 'down' | 'eq'
    """
    cx, cy = int(center[0]), int(center[1])
    s = max(2, int(size))
    half = s // 2
    if direction == 'up':
        points = [(cx, cy - half), (cx - half, cy + half), (cx + half, cy + half)]
        pygame.draw.polygon(surface, color, points)
    elif direction == 'down':
        points = [(cx, cy + half), (cx - half, cy - half), (cx + half, cy - half)]
        pygame.draw.polygon(surface, color, points)
    else:
        thickness = max(2, s // 4)
        gap = max(2, s // 4)
        bar_w = s
        top = pygame.Rect(cx - bar_w // 2, cy - gap // 2 - thickness, bar_w, thickness)
        bot = pygame.Rect(cx - bar_w // 2, cy + gap // 2, bar_w, thickness)
        pygame.draw.rect(surface, color, top)
        pygame.draw.rect(surface, color, bot)


class ConquerRoundLedger:
    """Bottom ledger band: 3 round cards + total resolve card.

    Parameters
    ----------
    parent : object
        The ``ConquerGameScreen`` (used for ``state.game`` and the
        battle subscreen which holds opponent round plays).
    """

    REVEAL_REPLAY_MS = 620

    def __init__(self, parent):
        self._parent = parent
        self.window: pygame.Surface = parent.window
        self._layout = None
        self._cached_screen_size = None
        self._cached_mode = None
        self._total_circle_rect: Optional[pygame.Rect] = None
        self._hover_round_idx: Optional[int] = None
        self._hover_popover_rect: Optional[pygame.Rect] = None
        self._revealed_round_keys: Dict[int, Tuple[Any, Any]] = {}
        self._round_reveal_animations: Dict[int, Dict[str, int]] = {}

    # ------------------------------------------------------------------ data
    def _game(self):
        return getattr(self._parent.state, 'game', None)

    def _player_played_per_round(self) -> List[Optional[Dict[str, Any]]]:
        """3-slot array of this player's played moves indexed by round."""
        moves = []
        try:
            getter = getattr(self._parent, '_current_conquer_tactics', None)
            if getter is None:
                getter = getattr(self._parent, '_current_conquer_battle_moves', None)
            moves = list(getter() or []) if getter is not None else []
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

        try:
            getter = getattr(self._parent, '_current_conquer_opponent_tactics', None)
            opponent_tactics = list(getter() or []) if getter is not None else []
        except Exception:
            opponent_tactics = []
        for move in opponent_tactics:
            if not isinstance(move, dict):
                continue
            played_round = move.get('played_round')
            if played_round in (0, 1, 2):
                slots[played_round] = move

        battle = None
        try:
            battle = self._parent.subscreens.get('battle')
        except Exception:
            return slots
        opp_played = getattr(battle, 'opp_played', None) if battle else None
        if isinstance(opp_played, list):
            for i, move in enumerate(opp_played[:3]):
                if not move:
                    continue
                if isinstance(move, dict) and move.get('played_round') in (0, 1, 2):
                    slots[move['played_round']] = move
                elif slots[i] is None:
                    slots[i] = move
        return slots

    def _power(self, move: Optional[Dict[str, Any]]) -> int:
        if move is None:
            return 0
        display_power = getattr(self._parent, '_conquer_tactic_display_power', None)
        if callable(display_power):
            try:
                return int(display_power(move) or 0)
            except Exception:
                pass
        if move.get('_skipped') or move.get('family_name') == 'Skip':
            return 0
        if move.get('family_name') == 'Block':
            return 0
        return int(move.get('value') or 0)

    @staticmethod
    def _move_label(move: Optional[Dict[str, Any]]) -> str:
        if move is None:
            return 'Pending'
        if move.get('_skipped') or move.get('family_name') == 'Skip':
            return 'Skip'
        name = move.get('family_name') or 'Tactic'
        if name == 'Dagger' and move.get('card_id_b'):
            return '2x Dagger'
        return str(name)

    @staticmethod
    def _move_identity(move: Optional[Dict[str, Any]]):
        if move is None:
            return None
        return (
            move.get('id'),
            move.get('card_id'),
            move.get('card_id_b'),
            move.get('family_name'),
            move.get('value'),
            move.get('played_round'),
        )

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

    def _round_diff(self, you, opp) -> int:
        # Block nullifies both sides of the round regardless of opponent's
        # move — both players score 0 for the round.
        if self._is_block(you) or self._is_block(opp):
            return 0
        return self._power(you) - self._power(opp)

    @staticmethod
    def _is_block(move) -> bool:
        return bool(move) and isinstance(move, dict) and move.get('family_name') == 'Block'

    def _ghost_preview(self, you_per) -> Optional[Tuple[int, Dict[str, Any]]]:
        game = self._game()
        if not game or getattr(game, 'last_battle_result', None):
            return None
        round_idx = int(getattr(game, 'battle_round', 0) or 0)
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

    def _figure_diff(self) -> int:
        """Player - opponent total figure power (mirrors legacy ``_get_figure_diff``)."""
        getter = getattr(self._parent, '_conquer_lane_figure_diff', None)
        if callable(getter):
            try:
                return int(getter() or 0)
            except Exception:
                return 0
        return 0

    def _total_diff(self, you_per, opp_per) -> int:
        return self._figure_diff() + sum(
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

    @staticmethod
    def _same_id(left, right) -> bool:
        if left is None or right is None:
            return False
        return str(left) == str(right)

    def _resolved_total_status(self, last_result, total_diff: int):
        if not isinstance(last_result, dict):
            return None
        game = self._game()
        player_id = getattr(game, 'player_id', None) if game else None

        outcome = str(last_result.get('outcome') or '').lower()
        if outcome == 'win':
            return _WIN_GREEN, 'WIN'
        if outcome in ('loss', 'lose'):
            return _LOSE_RED, 'LOSE'
        if outcome in ('draw', 'tie'):
            return _TIE_GREY, 'TIE'

        conquer_result = last_result.get('conquer_result')
        if conquer_result == 'draw':
            return _TIE_GREY, 'TIE'

        winner_id = (
            last_result.get('winner_player_id')
            or last_result.get('winner')
            or last_result.get('fold_winner_id')
        )
        if winner_id is None and conquer_result in ('attacker_won', 'defender_won'):
            attacker_id = (
                last_result.get('conquer_attacker_player_id')
                or getattr(game, 'conquer_attacker_player_id', None)
                or getattr(game, 'invader_player_id', None)
            )
            defender_id = (
                last_result.get('conquer_defender_player_id')
                or getattr(game, 'conquer_defender_player_id', None)
            )
            winner_id = attacker_id if conquer_result == 'attacker_won' else defender_id

        if winner_id is not None and player_id is not None:
            return ((_WIN_GREEN, 'WIN')
                    if self._same_id(winner_id, player_id)
                    else (_LOSE_RED, 'LOSE'))
        if winner_id is not None:
            return _WIN_GREEN, 'WIN'
        if total_diff > 0:
            return _WIN_GREEN, f'{total_diff:+d}'
        if total_diff < 0:
            return _LOSE_RED, f'{total_diff:+d}'
        return _TEXT_SECONDARY, 'DONE'

    def _update_round_reveal_animations(self, you_per, opp_per):
        now = pygame.time.get_ticks()
        for idx, (you, opp) in enumerate(zip(you_per, opp_per)):
            if you is None or opp is None:
                self._revealed_round_keys.pop(idx, None)
                self._round_reveal_animations.pop(idx, None)
                continue
            key = (self._move_identity(you), self._move_identity(opp))
            if self._revealed_round_keys.get(idx) == key:
                continue
            self._revealed_round_keys[idx] = key
            self._round_reveal_animations[idx] = {
                'started_at': now,
                'duration': self.REVEAL_REPLAY_MS,
            }

    def _round_card_hover_index(self, mouse_pos, ledger, you_per, opp_per):
        for idx, rect_tuple in enumerate(ledger.round_card_rects):
            if not (you_per[idx] is not None and opp_per[idx] is not None):
                continue
            if pygame.Rect(*rect_tuple).collidepoint(mouse_pos):
                return idx
        return None

    # ------------------------------------------------------------------ layout
    def _ensure_layout(self):
        size = (settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT)
        game = self._game()
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
        self._update_round_reveal_animations(you_per, opp_per)
        cur_round = int(getattr(self._game(), 'battle_round', 0) or 0)

        for i, rect_tuple in enumerate(ledger.round_card_rects):
            ghost_move = ghost_preview[1] if ghost_preview and ghost_preview[0] == i else None
            self._draw_round_card(pygame.Rect(*rect_tuple), i, you_per[i],
                                  opp_per[i], cur_round, ghost_move=ghost_move,
                                  reveal_animation=self._round_reveal_animations.get(i))
        self._draw_total_card(pygame.Rect(*ledger.total_card_rect),
                              pygame.Rect(*ledger.total_circle_rect),
                              you_per, opp_per, ghost_preview=ghost_preview)
        self._draw_round_hover_popover(ledger, you_per, opp_per)

    # -- round card
    def _draw_round_card(self, rect: pygame.Rect, idx: int,
                         you, opp, cur_round: int, ghost_move=None,
                         reveal_animation=None):
        is_active = cur_round == idx if cur_round in (0, 1, 2) else False
        bg = pygame.Surface(rect.size, pygame.SRCALPHA)
        bg.fill(_CARD_BG_RGBA)
        self.window.blit(bg, rect.topleft)
        # Reveal glow drawn behind chips so the move icons stay legible.
        self._draw_round_reveal_animation(rect, idx, reveal_animation)
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
        # Block nullifies the other side: when one player plays Block, the
        # opponent's chip is shown with a red strike overlay to communicate
        # that the tactic was negated.
        you_blocked = self._is_block(opp) and not self._is_block(display_you) and display_you is not None
        opp_blocked = self._is_block(display_you) and not self._is_block(opp) and opp is not None
        self._draw_player_chip(you_rect, display_you, is_player_self=True,
                               ghost=is_ghost, blocked=you_blocked)
        self._draw_player_chip(opp_rect, opp, is_player_self=False,
                               blocked=opp_blocked)
        self._draw_diff_pill(diff_rect, you, opp,
                             played=(you is not None and opp is not None),
                             ghost_move=ghost_move)

    def _draw_round_reveal_animation(self, rect: pygame.Rect, idx: int,
                                     animation):
        if not animation:
            return
        now = pygame.time.get_ticks()
        started_at = int(animation.get('started_at') or now)
        duration = max(1, int(animation.get('duration') or self.REVEAL_REPLAY_MS))
        elapsed = now - started_at
        if elapsed > duration:
            self._round_reveal_animations.pop(idx, None)
            return
        progress = max(0.0, min(1.0, elapsed / duration))
        eased = 1 - (1 - progress) * (1 - progress)
        alpha = max(0, int(160 * (1.0 - progress)))
        if alpha <= 0:
            return

        flash = pygame.Surface(rect.size, pygame.SRCALPHA)
        flash.fill((238, 204, 116, max(18, alpha // 5)))
        self.window.blit(flash, rect.topleft)

        sweep_w = max(10, rect.width // 7)
        sweep_x = int(rect.left - sweep_w + (rect.width + sweep_w * 2) * eased)
        sweep = pygame.Surface((sweep_w, rect.height), pygame.SRCALPHA)
        sweep.fill((250, 226, 150, alpha))
        self.window.blit(sweep, (sweep_x, rect.top))
        pygame.draw.rect(self.window, (238, 204, 116, alpha), rect, 3, border_radius=6)

    def _draw_player_chip(self, rect: pygame.Rect, move, is_player_self: bool,
                          *, ghost: bool = False, blocked: bool = False):
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
        name = self._move_label(move)
        name_font = settings.get_font(max(9, int(settings.FS_TINY * 0.9)), bold=True)
        pwr_font = settings.get_font(max(13, int(settings.FS_SMALL * 1.1)), bold=True)
        text_col = _GHOST_BLUE if ghost else _TEXT_SECONDARY
        power_col = _GHOST_BLUE if ghost else _TEXT_PRIMARY
        icon_size = max(28, min(rect.height - 4, int(rect.width * 0.58)))
        icon_x = rect.left + 4 + icon_size // 2
        icon_y = rect.centery
        icon_drawn = self._draw_move_icon(icon_x, icon_y, icon_size, move, ghost=ghost)
        text_x = rect.left + (icon_size + 9 if icon_drawn else 4)
        max_text_w = max(14, rect.right - text_x - 4)
        ns = name_font.render(self._fit_text(name, name_font, max_text_w), True, text_col)
        ps = pwr_font.render(str(self._power(move)), True, power_col)
        self.window.blit(ns, (text_x, rect.top + 2))
        self.window.blit(ps, (rect.right - ps.get_width() - 4,
                              rect.bottom - ps.get_height() - 2))
        if blocked:
            # Red translucent tint + diagonal strike to indicate the move
            # was nullified by the opponent's Block.
            tint = pygame.Surface(rect.size, pygame.SRCALPHA)
            tint.fill((180, 40, 40, 70))
            self.window.blit(tint, rect.topleft)
            pygame.draw.line(self.window, (220, 70, 60),
                             rect.topleft, rect.bottomright, 3)
            pygame.draw.line(self.window, (220, 70, 60),
                             (rect.left, rect.bottom), (rect.right, rect.top), 3)

    def _draw_move_icon(self, cx: int, cy: int, icon_size: int, move,
                        *, ghost: bool = False) -> bool:
        try:
            glow_cache, icon_cache, frame_cache, suit_icon_cache, icon_font = (
                self._parent._conquer_battle_move_icon_assets(icon_size))
            draw_battle_move_icon(
                self.window,
                cx,
                cy,
                move.get('family_name', ''),
                move.get('suit', ''),
                self._power(move),
                glow_cache,
                icon_cache,
                frame_cache,
                suit_icon_cache,
                icon_font,
                icon_size,
                hovered=False,
                is_used=False,
                suit_b=move.get('suit_b'),
            )
            return True
        except Exception:
            fallback = pygame.Rect(0, 0, icon_size, icon_size)
            fallback.center = (cx, cy)
            pygame.draw.rect(self.window, (70, 58, 44), fallback, border_radius=4)
            pygame.draw.rect(self.window, _GHOST_BLUE if ghost else _BORDER_RGBA,
                             fallback, 1, border_radius=4)
            return True

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
            direction, col = 'up', _WIN_GREEN
        elif diff < 0:
            direction, col = 'down', _LOSE_RED
        else:
            direction, col = 'eq', _TIE_GREY
        pill = rect.inflate(-rect.width // 4, -rect.height // 3)
        pygame.draw.rect(self.window, (10, 8, 6), pill, 0, border_radius=8)
        pygame.draw.rect(self.window, col, pill, 2, border_radius=8)
        font = settings.get_font(max(13, int(settings.FS_SMALL * 1.0)), bold=True)
        num_surf = font.render(f'{abs(diff)}', True, col)
        glyph_size = max(6, min(pill.height - 6, font.get_height() - 2))
        gap = 2
        total_w = glyph_size + gap + num_surf.get_width()
        glyph_cx = pill.centerx - total_w // 2 + glyph_size // 2
        _draw_diff_glyph(self.window, (glyph_cx, pill.centery), glyph_size, direction, col)
        num_rect = num_surf.get_rect(midleft=(glyph_cx + glyph_size // 2 + gap, pill.centery))
        self.window.blit(num_surf, num_rect)

    def _draw_ghost_diff_pill(self, rect: pygame.Rect, move, opp):
        diff = self._round_diff(move, opp) if opp is not None else self._power(move)
        if diff > 0:
            direction = 'up'
        elif diff < 0:
            direction = 'down'
        else:
            direction = 'eq'
        pill = rect.inflate(-rect.width // 4, -rect.height // 3)
        overlay = pygame.Surface(pill.size, pygame.SRCALPHA)
        overlay.fill(_GHOST_RGBA)
        self.window.blit(overlay, pill.topleft)
        pygame.draw.rect(self.window, _GHOST_BLUE, pill, 2, border_radius=8)
        font = settings.get_font(max(13, int(settings.FS_SMALL * 1.0)), bold=True)
        num_surf = font.render(f'{abs(diff)}', True, _GHOST_BLUE)
        glyph_size = max(6, min(pill.height - 6, font.get_height() - 2))
        gap = 2
        total_w = glyph_size + gap + num_surf.get_width()
        glyph_cx = pill.centerx - total_w // 2 + glyph_size // 2
        _draw_diff_glyph(self.window, (glyph_cx, pill.centery), glyph_size, direction, _GHOST_BLUE)
        num_rect = num_surf.get_rect(midleft=(glyph_cx + glyph_size // 2 + gap, pill.centery))
        self.window.blit(num_surf, num_rect)

    # -- total card
    def _draw_total_card(self, rect: pygame.Rect, circle_rect: pygame.Rect,
                         you_per, opp_per, ghost_preview=None):
        # Subtle gold-tinted background so the "battle total" reads as the
        # dominant readout in the ledger band.
        bg = pygame.Surface(rect.size, pygame.SRCALPHA)
        bg.fill((44, 33, 20, 240))
        self.window.blit(bg, rect.topleft)
        pygame.draw.rect(self.window, (210, 168, 72), rect, 2, border_radius=6)
        title_font = settings.get_font(max(11, int(settings.FS_TINY * 1.05)), bold=True)
        ts = title_font.render('BATTLE TOTAL', True, (238, 206, 130))
        self.window.blit(ts, ts.get_rect(midtop=(rect.centerx, rect.top + 3)))

        total_diff = self._ghost_total_diff(you_per, opp_per, ghost_preview)
        played_count = sum(1 for y, o in zip(you_per, opp_per) if y and o)
        game = self._game()
        last_result = getattr(game, 'last_battle_result', None) if game else None

        if last_result:
            col, label = self._resolved_total_status(last_result, total_diff)
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

        # Circle -- enlarged + gold halo so the battle-total reading
        # dominates the ledger band. The circle is anchored below the
        # "BATTLE TOTAL" caption so they don't overlap.
        title_clearance = title_font.get_height() + 6
        avail_h = max(8, rect.height - title_clearance - 4)
        diameter = min(circle_rect.width, avail_h)
        radius = max(8, diameter // 2 - 2)
        cx = circle_rect.centerx
        cy = rect.top + title_clearance + (avail_h // 2)
        # Outer halo glow.
        halo = pygame.Surface((radius * 2 + 16, radius * 2 + 16), pygame.SRCALPHA)
        for i, alpha in enumerate((40, 70, 110)):
            pygame.draw.circle(
                halo, (*col, alpha),
                (halo.get_width() // 2, halo.get_height() // 2),
                radius + 6 - i * 2, 2,
            )
        self.window.blit(halo, halo.get_rect(center=(cx, cy)))
        pygame.draw.circle(self.window, (16, 12, 8), (cx, cy), radius)
        pygame.draw.circle(self.window, col, (cx, cy), radius, 4)
        if ghost_preview:
            pygame.draw.circle(self.window, _GHOST_BLUE, (cx, cy), max(1, radius - 8), 1)
        value_size = max(14, min(int(radius * 1.05), int(settings.FS_SMALL * 1.55)))
        font = settings.get_font(value_size, bold=True)
        ts = font.render(label, True, col)
        self.window.blit(ts, ts.get_rect(center=(cx, cy)))
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

    def _draw_round_hover_popover(self, ledger, you_per, opp_per, mouse_pos=None):
        mouse_pos = mouse_pos if mouse_pos is not None else pygame.mouse.get_pos()
        idx = self._round_card_hover_index(mouse_pos, ledger, you_per, opp_per)
        self._hover_round_idx = idx
        self._hover_popover_rect = None
        if idx is None:
            return

        card_rect = pygame.Rect(*ledger.round_card_rects[idx])
        popup_w = min(max(260, int(card_rect.width * 0.86)), settings.SCREEN_WIDTH - 24)
        popup_h = max(86, int(settings.SCREEN_HEIGHT * 0.095))
        margin = max(8, int(settings.SCREEN_WIDTH * 0.006))
        x = max(margin, min(card_rect.centerx - popup_w // 2,
                           settings.SCREEN_WIDTH - margin - popup_w))
        y = card_rect.top - popup_h - 8
        if y < margin:
            y = min(settings.SCREEN_HEIGHT - margin - popup_h, card_rect.bottom + 8)
        rect = pygame.Rect(x, y, popup_w, popup_h)
        self._hover_popover_rect = rect

        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        panel.fill((28, 22, 16, 244))
        self.window.blit(panel, rect.topleft)
        pygame.draw.rect(self.window, (210, 168, 72), rect, 2, border_radius=7)

        you = you_per[idx]
        opp = opp_per[idx]
        diff = self._round_diff(you, opp)
        if diff > 0:
            glyph, col = '^', _WIN_GREEN
        elif diff < 0:
            glyph, col = 'v', _LOSE_RED
        else:
            glyph, col = '=', _TIE_GREY

        title_font = settings.get_font(max(10, int(settings.FS_SMALL * 0.90)), bold=True)
        body_font = settings.get_font(max(9, int(settings.FS_TINY * 0.85)), bold=True)
        title = title_font.render(f'Round {idx + 1} recap', True, _TEXT_PRIMARY)
        self.window.blit(title, (rect.left + 10, rect.top + 7))

        line_w = rect.width - 20
        you_line = f'You: {self._move_label(you)} {self._power(you)}'
        opp_line = f'Opp: {self._move_label(opp)} {self._power(opp)}'
        diff_line = f'Diff: {glyph}{abs(diff)}'
        lines = [
            (you_line, (154, 218, 206)),
            (opp_line, (226, 168, 152)),
            (diff_line, col),
        ]
        y_cursor = rect.top + 10 + title.get_height() + 3
        for line, color in lines:
            surf = body_font.render(self._fit_text(line, body_font, line_w), True, color)
            self.window.blit(surf, (rect.left + 10, y_cursor))
            y_cursor += surf.get_height() + 2
