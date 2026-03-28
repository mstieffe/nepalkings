# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
import pygame
from pygame.locals import *
from game.screens.screen import Screen
from game.screens._menu_base import MenuScreenMixin
from config import settings
from utils.auth_service import fetch_rankings
from utils.background_poller import BackgroundPoller

_SW, _SH = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT

# ── Overall box ─────────────────────────────────────────────────────
_BOX_PAD     = int(0.025 * _SH)
_BOX_X       = int(0.06 * _SW)
_BOX_Y       = int(0.12 * _SH)
_BOX_W       = int(0.85 * _SW)
_BOX_BOTTOM  = int(0.90 * _SH)
_BOX_H       = _BOX_BOTTOM - _BOX_Y

# ── Title inside box ───────────────────────────────────────────────
_TITLE_Y     = _BOX_Y + _BOX_PAD

# ── Table geometry ──────────────────────────────────────────────────
_TABLE_X     = _BOX_X + int(0.02 * _SW)
_TABLE_W     = _BOX_W - int(0.04 * _SW)
_ROW_H       = int(0.050 * _SH)
_ROW_GAP     = int(0.006 * _SH)
_HEADER_H    = int(0.040 * _SH)

# Column definitions: (label, frac_start, frac_width)
_COL_DEFS = [
    ('#',       0.00, 0.06),
    ('Player',  0.06, 0.24),
    ('Gold',    0.30, 0.14),
    ('Games',   0.44, 0.14),
    ('Wins',    0.58, 0.14),
    ('Losses',  0.72, 0.14),
    ('W/L',     0.86, 0.14),
]

# Scrollbar
_SCROLLBAR_W   = int(0.006 * _SW)
_SCROLLBAR_CLR = (100, 95, 85, 180)
_THUMB_CLR     = (200, 185, 150, 220)
_THUMB_HOVER   = (240, 220, 170, 255)

# Online-status dot
_DOT_RADIUS    = int(0.006 * _SH)
_DOT_ONLINE    = (60, 200, 80)
_DOT_OFFLINE   = (120, 110, 100)

# Sort column highlight
_HDR_ACTIVE_CLR = (240, 220, 140)


def _draw_panel(window, rect, corner_r=None):
    r = corner_r or settings.SUB_SCREEN_PANEL_CORNER_R
    surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    pygame.draw.rect(surf, settings.SUB_SCREEN_PANEL_BG_CLR, surf.get_rect(), border_radius=r)
    window.blit(surf, rect.topleft)
    pygame.draw.rect(window, settings.SUB_SCREEN_PANEL_BORDER_CLR, rect,
                     settings.SUB_SCREEN_PANEL_BORDER_W, border_radius=r)


# Mapping from column index to sort key
_SORT_KEYS = {
    2: ('gold',        True),   # Gold – descending
    3: ('total_games', True),   # Games – descending
    4: ('wins',        True),   # Wins – descending
    5: ('losses',      True),   # Losses – descending
    6: ('wl_ratio',    True),   # W/L – descending
}


class RankingScreen(MenuScreenMixin, Screen):
    def __init__(self, state):
        super().__init__(state)
        self.control_buttons = []
        self._init_menu_chrome()

        self.rankings = []
        self._hovered_row = -1
        self._sort_col = 2           # default sort by Gold
        self.last_update_time = 0
        self.update_interval = 10000

        # Scroll
        self._scroll_y = 0
        self._max_scroll = 0
        self._dragging_thumb = False
        self._drag_offset = 0

        # Fonts
        self._title_font = settings.get_font(settings.SUB_SCREEN_TITLE_FONT_SIZE, bold=True)
        self._title_surf = self._title_font.render('Rankings', True, settings.SUB_SCREEN_TITLE_CLR)

        self._hdr_font = settings.get_font(settings.SUB_SCREEN_HEADER_FONT_SIZE)
        self._cell_font = settings.get_font(settings.LIST_BTN_FONT_SIZE)

        # Compute fixed layout positions
        self._title_render_y = _TITLE_Y
        title_bottom = _TITLE_Y + self._title_surf.get_height() + int(0.010 * _SH)
        self._hdr_y = title_bottom
        self._sep_y = self._hdr_y + _HEADER_H + int(0.004 * _SH)
        self._rows_top = self._sep_y + int(0.008 * _SH)
        self._rows_bottom = _BOX_Y + _BOX_H - _BOX_PAD
        self._viewport_h = self._rows_bottom - self._rows_top

        # Pre-compute header rects for click detection
        self._hdr_rects = []
        for idx, (_, frac_x, frac_w) in enumerate(_COL_DEFS):
            rx = _TABLE_X + int(frac_x * _TABLE_W)
            rw = int(frac_w * _TABLE_W)
            self._hdr_rects.append(pygame.Rect(rx, self._hdr_y, rw, _HEADER_H))

    # ── Data ──────────────────────────────────────────────────────

    def _refresh(self):
        raw = fetch_rankings()
        # Pre-compute W/L ratio
        for r in raw:
            losses = r.get('losses', 0)
            wins = r.get('wins', 0)
            r['wl_ratio'] = wins / losses if losses > 0 else float(wins)

        # Sort
        key_name, desc = _SORT_KEYS.get(self._sort_col, ('gold', True))
        raw.sort(key=lambda r: r.get(key_name, 0), reverse=desc)
        self.rankings = raw

        n = len(self.rankings)
        self._content_h = n * (_ROW_H + _ROW_GAP) - (_ROW_GAP if n else 0)
        self._max_scroll = max(0, self._content_h - self._viewport_h)
        self._scroll_y = min(self._scroll_y, self._max_scroll)

    # ── Helpers ───────────────────────────────────────────────────

    def _col_x(self, idx):
        return _TABLE_X + int(_COL_DEFS[idx][1] * _TABLE_W)

    def _needs_scroll(self):
        return self._content_h > self._viewport_h if hasattr(self, '_content_h') else False

    def _thumb_rect(self):
        if not self._needs_scroll():
            return pygame.Rect(0, 0, 0, 0)
        track_h = self._viewport_h
        thumb_h = max(int(0.03 * _SH), int(track_h * (self._viewport_h / self._content_h)))
        track_x = _BOX_X + _BOX_W - _BOX_PAD - _SCROLLBAR_W
        travel = track_h - thumb_h
        frac = self._scroll_y / self._max_scroll if self._max_scroll else 0
        thumb_y = self._rows_top + int(frac * travel)
        return pygame.Rect(track_x, thumb_y, _SCROLLBAR_W, thumb_h)

    def _track_rect(self):
        track_x = _BOX_X + _BOX_W - _BOX_PAD - _SCROLLBAR_W
        return pygame.Rect(track_x, self._rows_top, _SCROLLBAR_W, self._viewport_h)

    # ── Rendering ─────────────────────────────────────────────────

    def render(self):
        self._draw_menu_chrome()

        # Outer box
        box_rect = pygame.Rect(_BOX_X, _BOX_Y, _BOX_W, _BOX_H)
        _draw_panel(self.window, box_rect)

        # Title
        tx = _BOX_X + (_BOX_W - self._title_surf.get_width()) // 2
        self.window.blit(self._title_surf, (tx, self._title_render_y))

        # Table header
        cell_pad = int(0.012 * _SW)
        hdr_text_y = self._hdr_y + (_HEADER_H - self._hdr_font.get_height()) // 2
        for idx, (label, _, _) in enumerate(_COL_DEFS):
            clr = _HDR_ACTIVE_CLR if idx == self._sort_col else settings.SUB_SCREEN_HEADER_CLR
            surf = self._hdr_font.render(label, True, clr)
            self.window.blit(surf, (self._col_x(idx) + cell_pad, hdr_text_y))

        # Separator
        pygame.draw.line(self.window, settings.SUB_SCREEN_PANEL_BORDER_CLR,
                         (_TABLE_X, self._sep_y), (_TABLE_X + _TABLE_W, self._sep_y), 1)

        # Rows
        if not self.rankings:
            hint = self._cell_font.render("No players yet", True, (140, 140, 140))
            self.window.blit(hint, (_TABLE_X + cell_pad, self._rows_top + int(0.01 * _SH)))
        else:
            self._draw_rows(cell_pad)

        self._draw_menu_overlay()

    def _draw_rows(self, cell_pad):
        clip = pygame.Rect(_TABLE_X, self._rows_top, _TABLE_W, self._viewport_h)
        self.window.set_clip(clip)

        username = self.state.user_dict.get('username') if self.state.user_dict else None

        for i, entry in enumerate(self.rankings):
            y = self._rows_top + i * (_ROW_H + _ROW_GAP) - self._scroll_y
            rect = pygame.Rect(_TABLE_X, y, _TABLE_W, _ROW_H)

            if rect.bottom < self._rows_top or rect.top > self._rows_bottom:
                continue

            is_hover = (i == self._hovered_row)
            is_self = (entry.get('username') == username)

            # Row background
            if is_self:
                bg = (60, 55, 45, 200)
            elif is_hover:
                bg = settings.LIST_BTN_BG_HOVER_CLR
            else:
                bg = settings.LIST_BTN_BG_CLR
            r = settings.LIST_BTN_CORNER_RADIUS
            row_surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
            pygame.draw.rect(row_surf, bg, row_surf.get_rect(), border_radius=r)
            self.window.blit(row_surf, rect.topleft)

            bdr = settings.LIST_BTN_BORDER_HOVER_CLR if (is_hover or is_self) else settings.LIST_BTN_BORDER_CLR
            pygame.draw.rect(self.window, bdr, rect, settings.LIST_BTN_BORDER_W, border_radius=r)

            txt_clr = settings.LIST_BTN_TEXT_HOVER_CLR if is_hover else settings.LIST_BTN_TEXT_CLR
            text_y = rect.y + (rect.h - self._cell_font.get_height()) // 2

            # W/L display
            wl = entry.get('wl_ratio', 0)
            wl_str = f"{wl:.1f}" if entry.get('losses', 0) > 0 else f"{entry.get('wins', 0)}"

            cells = [
                str(i + 1),
                entry.get('username', '—'),
                str(entry.get('gold', 0)),
                str(entry.get('total_games', 0)),
                str(entry.get('wins', 0)),
                str(entry.get('losses', 0)),
                wl_str,
            ]
            for idx, text in enumerate(cells):
                x_off = cell_pad + (int(0.018 * _SW) if idx == 1 else 0)
                surf = self._cell_font.render(text, True, txt_clr)
                self.window.blit(surf, (self._col_x(idx) + x_off, text_y))

            # Online dot next to player name
            dot_clr = _DOT_ONLINE if entry.get('is_online', False) else _DOT_OFFLINE
            dot_x = self._col_x(1) + cell_pad + int(0.006 * _SW)
            dot_y = rect.y + rect.h // 2
            pygame.draw.circle(self.window, dot_clr, (dot_x, dot_y), _DOT_RADIUS)

        self.window.set_clip(None)

        # Scrollbar
        if self._needs_scroll():
            track = self._track_rect()
            track_surf = pygame.Surface((track.w, track.h), pygame.SRCALPHA)
            track_surf.fill(_SCROLLBAR_CLR)
            self.window.blit(track_surf, track.topleft)

            thumb = self._thumb_rect()
            mx, my = pygame.mouse.get_pos()
            clr = _THUMB_HOVER if thumb.collidepoint(mx, my) or self._dragging_thumb else _THUMB_CLR
            thumb_surf = pygame.Surface((thumb.w, thumb.h), pygame.SRCALPHA)
            pygame.draw.rect(thumb_surf, clr, thumb_surf.get_rect(), border_radius=3)
            self.window.blit(thumb_surf, thumb.topleft)

    # ── Update ────────────────────────────────────────────────────

    def update(self, events):
        super().update()
        self._update_icon_buttons()

        # Non-blocking refresh
        if not hasattr(self, '_ranking_poller'):
            self._ranking_poller = BackgroundPoller(
                fetch_rankings,
                async_get_url=f'{settings.SERVER_URL}/auth/get_rankings',
                async_transform=lambda resp: resp.json().get('rankings', []) if resp.status_code == 200 else [],
            )
        now = pygame.time.get_ticks()
        if now - self.last_update_time > self.update_interval:
            self.last_update_time = now
            if not self._ranking_poller.busy:
                self._ranking_poller.poll()
        if self._ranking_poller.has_result():
            raw = self._ranking_poller.result
            if raw is not None:
                for r in raw:
                    losses = r.get('losses', 0)
                    wins = r.get('wins', 0)
                    r['wl_ratio'] = wins / losses if losses > 0 else float(wins)
                key_name, desc = _SORT_KEYS.get(self._sort_col, ('gold', True))
                raw.sort(key=lambda r: r.get(key_name, 0), reverse=desc)
                self.rankings = raw
                n = len(self.rankings)
                self._content_h = n * (_ROW_H + _ROW_GAP) - (_ROW_GAP if n else 0)
                self._max_scroll = max(0, self._content_h - self._viewport_h)
                self._scroll_y = min(self._scroll_y, self._max_scroll)

        # Hover detection
        mx, my = pygame.mouse.get_pos()
        self._hovered_row = -1
        if hasattr(self, '_content_h'):
            for i in range(len(self.rankings)):
                y = self._rows_top + i * (_ROW_H + _ROW_GAP) - self._scroll_y
                rect = pygame.Rect(_TABLE_X, y, _TABLE_W, _ROW_H)
                if self._rows_top <= rect.centery <= self._rows_bottom and rect.collidepoint(mx, my):
                    self._hovered_row = i
                    break

    # ── Events ────────────────────────────────────────────────────

    def handle_events(self, events):
        super().handle_events(events)

        _box_rect = pygame.Rect(_BOX_X, _BOX_Y, _BOX_W, _BOX_H)

        for event in events:
            if self._handle_icon_events(event):
                continue

            # Click outside content box → back to game menu
            if (event.type == MOUSEBUTTONUP and event.button == 1
                    and not self.dialogue_box
                    and not _box_rect.collidepoint(event.pos)):
                self.state.screen = 'game_menu'
                return

            if event.type == MOUSEWHEEL:
                if self._needs_scroll():
                    self._scroll_y = max(0, min(self._max_scroll,
                        self._scroll_y - event.y * int(0.04 * _SH)))

            if event.type == MOUSEBUTTONDOWN and event.button == 1:
                # Header click to toggle sort
                for idx in _SORT_KEYS:
                    if self._hdr_rects[idx].collidepoint(event.pos):
                        self._sort_col = idx
                        self._scroll_y = 0
                        self._refresh()
                        break

                # Scrollbar thumb drag
                if self._needs_scroll():
                    thumb = self._thumb_rect()
                    if thumb.w and thumb.collidepoint(event.pos):
                        self._dragging_thumb = True
                        self._drag_offset = event.pos[1] - thumb.y
                    else:
                        # Touch-drag scroll in the content area
                        box = pygame.Rect(_BOX_X, self._rows_top, _BOX_W, self._viewport_h)
                        if box.collidepoint(event.pos):
                            self._touch_scrolling = True
                            self._touch_last_y = event.pos[1]

            if event.type == MOUSEBUTTONUP and event.button == 1:
                self._dragging_thumb = False
                self._touch_scrolling = False

            if event.type == MOUSEMOTION:
                if self._dragging_thumb:
                    track = self._track_rect()
                    thumb_h = self._thumb_rect().h
                    travel = track.h - thumb_h
                    if travel > 0:
                        new_top = event.pos[1] - self._drag_offset - track.y
                        frac = max(0.0, min(1.0, new_top / travel))
                        self._scroll_y = int(frac * self._max_scroll)
                elif getattr(self, '_touch_scrolling', False) and self._needs_scroll():
                    dy = event.pos[1] - self._touch_last_y
                    self._touch_last_y = event.pos[1]
                    self._scroll_y = max(0, min(self._max_scroll, self._scroll_y - dy))
