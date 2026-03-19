import pygame
from datetime import datetime
from email.utils import parsedate_to_datetime
from pygame.locals import *
from game.screens.screen import Screen
from game.screens._menu_base import MenuScreenMixin
from config import settings
from utils import http_compat as requests
from game.core.game import Game
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

_COL_DEFS = [
    ('Opponent',   0.00, 0.19),
    ('Round',      0.19, 0.10),
    ('Score',      0.29, 0.14),
    ('Duration',   0.43, 0.17),
    ('Stake',      0.60, 0.12),
    ('Turn Limit', 0.72, 0.14),
    ('',           0.86, 0.14),   # "your turn" / NEW column
]

# NEW tag colours
_NEW_TAG_BG  = (180, 140, 40)
_NEW_TAG_TXT = (30, 28, 24)

# "Your turn" tag colour
_TURN_TAG_CLR = (90, 200, 110)

# Scrollbar
_SCROLLBAR_W   = int(0.006 * _SW)
_SCROLLBAR_CLR = (100, 95, 85, 180)
_THUMB_CLR     = (200, 185, 150, 220)
_THUMB_HOVER   = (240, 220, 170, 255)

# Online-status dot
_DOT_RADIUS    = int(0.006 * _SH)
_DOT_ONLINE    = (60, 200, 80)
_DOT_OFFLINE   = (120, 110, 100)


def _draw_panel(window, rect, corner_r=None):
    r = corner_r or settings.SUB_SCREEN_PANEL_CORNER_R
    surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    pygame.draw.rect(surf, settings.SUB_SCREEN_PANEL_BG_CLR, surf.get_rect(), border_radius=r)
    window.blit(surf, rect.topleft)
    pygame.draw.rect(window, settings.SUB_SCREEN_PANEL_BORDER_CLR, rect,
                     settings.SUB_SCREEN_PANEL_BORDER_W, border_radius=r)


def _parse_date(date_str):
    """Parse ISO or HTTP-date string into a naive datetime."""
    if not date_str:
        return None
    for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f',
                '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f'):
        try:
            return datetime.strptime(date_str, fmt)
        except (ValueError, TypeError):
            continue
    try:
        return parsedate_to_datetime(date_str).replace(tzinfo=None)
    except (ValueError, TypeError):
        pass
    return None


def _duration_str(date_str):
    try:
        start = _parse_date(str(date_str))
        if not start:
            return str(date_str)
        delta = datetime.now() - start
        days = delta.days
        hours = delta.seconds // 3600
        if days > 0:
            return f"{days}d {hours}h"
        minutes = delta.seconds // 60
        if hours > 0:
            return f"{hours}h {minutes % 60}m"
        return f"{minutes}m"
    except Exception:
        return date_str


class LoadGameScreen(MenuScreenMixin, Screen):
    def __init__(self, state):
        super().__init__(state)
        self.control_buttons = []
        self._init_menu_chrome()

        self.games = []
        self._row_rects = []
        self._hovered_row = -1
        self.last_update_time = 0
        self.update_interval = 5000

        # Scroll
        self._scroll_y = 0
        self._max_scroll = 0
        self._dragging_thumb = False
        self._drag_offset = 0

        # Fonts
        self._title_font = pygame.font.Font(settings.FONT_PATH, settings.SUB_SCREEN_TITLE_FONT_SIZE)
        self._title_font.set_bold(True)
        self._title_surf = self._title_font.render('Load Game', True, settings.SUB_SCREEN_TITLE_CLR)

        self._hdr_font = pygame.font.Font(settings.FONT_PATH, settings.SUB_SCREEN_HEADER_FONT_SIZE)
        self._cell_font = pygame.font.Font(settings.FONT_PATH, settings.LIST_BTN_FONT_SIZE)
        self._tag_font = pygame.font.Font(settings.FONT_PATH, int(0.016 * _SH))
        self._tag_font.set_bold(True)

        # Compute fixed layout positions inside the box
        self._title_render_y = _TITLE_Y
        title_bottom = _TITLE_Y + self._title_surf.get_height() + int(0.015 * _SH)
        self._hdr_y = title_bottom
        self._sep_y = self._hdr_y + _HEADER_H
        self._rows_top = self._sep_y + int(0.008 * _SH)
        self._rows_bottom = _BOX_Y + _BOX_H - _BOX_PAD
        self._viewport_h = self._rows_bottom - self._rows_top

    # ── Data ──────────────────────────────────────────────────────

    def _refresh_games(self):
        try:
            self.games = self._fetch_games()
        except Exception as e:
            print(f"Error fetching games: {str(e)}")
            self.games = []

        # Compute total content height & max scroll
        n = len(self.games)
        self._content_h = n * (_ROW_H + _ROW_GAP) - (_ROW_GAP if n else 0)
        self._max_scroll = max(0, self._content_h - self._viewport_h)
        self._scroll_y = min(self._scroll_y, self._max_scroll)

        # Row rects are computed dynamically during draw (shifted by scroll)
        self._row_rects = []

    def _fetch_games(self):
        response = requests.get(
            f'{settings.SERVER_URL}/games/get_games',
            params={'username': self.state.user_dict['username']},
            timeout=10)
        if response.status_code != 200:
            return []
        game_dicts = response.json().get('games', [])
        return [Game(gd, self.state.user_dict) for gd in game_dicts]

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

        # Title (centred inside box)
        tx = _BOX_X + (_BOX_W - self._title_surf.get_width()) // 2
        self.window.blit(self._title_surf, (tx, self._title_render_y))

        # Table header
        cell_pad = int(0.012 * _SW)
        hdr_text_y = self._hdr_y + (_HEADER_H - self._hdr_font.get_height()) // 2
        for idx, (label, _, _) in enumerate(_COL_DEFS):
            surf = self._hdr_font.render(label, True, settings.SUB_SCREEN_HEADER_CLR)
            self.window.blit(surf, (self._col_x(idx) + cell_pad, hdr_text_y))

        # Separator
        pygame.draw.line(self.window, settings.SUB_SCREEN_PANEL_BORDER_CLR,
                         (_TABLE_X, self._sep_y), (_TABLE_X + _TABLE_W, self._sep_y), 1)

        # Rows (clipped to viewport)
        if not self.games:
            hint = self._cell_font.render("No active games", True, (140, 140, 140))
            self.window.blit(hint, (_TABLE_X + cell_pad, self._rows_top + int(0.01 * _SH)))
        else:
            self._draw_rows(cell_pad)

        self._draw_menu_overlay()

    def _draw_rows(self, cell_pad):
        clip = pygame.Rect(_TABLE_X, self._rows_top, _TABLE_W, self._viewport_h)
        self.window.set_clip(clip)

        self._row_rects = []
        for i, game in enumerate(self.games):
            y = self._rows_top + i * (_ROW_H + _ROW_GAP) - self._scroll_y
            rect = pygame.Rect(_TABLE_X, y, _TABLE_W, _ROW_H)

            # Skip if completely outside viewport
            if rect.bottom < self._rows_top or rect.top > self._rows_bottom:
                self._row_rects.append(rect)
                continue

            self._row_rects.append(rect)
            is_hover = (i == self._hovered_row)

            # Row background
            bg = settings.LIST_BTN_BG_HOVER_CLR if is_hover else settings.LIST_BTN_BG_CLR
            r = settings.LIST_BTN_CORNER_RADIUS
            row_surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
            pygame.draw.rect(row_surf, bg, row_surf.get_rect(), border_radius=r)
            self.window.blit(row_surf, rect.topleft)

            bdr = settings.LIST_BTN_BORDER_HOVER_CLR if is_hover else settings.LIST_BTN_BORDER_CLR
            pygame.draw.rect(self.window, bdr, rect, settings.LIST_BTN_BORDER_W, border_radius=r)

            txt_clr = settings.LIST_BTN_TEXT_HOVER_CLR if is_hover else settings.LIST_BTN_TEXT_CLR
            text_y = rect.y + (rect.h - self._cell_font.get_height()) // 2

            # --- Build per-column text ---
            my_score = game.current_player.get('points', 0) if game.current_player else 0
            opp_score = game.opponent_player.get('points', 0) if game.opponent_player else 0

            cells = [
                game.opponent_name or '—',
                f"Rd {game.current_round}",
                f"{my_score} – {opp_score}",
                _duration_str(game.date),
                f"{game.stake} gold",
                f"{game.turn_time_limit // 60} min" if game.turn_time_limit else "No limit",
            ]
            for idx, text in enumerate(cells):
                surf = self._cell_font.render(text, True, txt_clr)
                x_off = cell_pad + (int(0.018 * _SW) if idx == 0 else 0)
                self.window.blit(surf, (self._col_x(idx) + x_off, text_y))

            # --- Status column (last): "Your turn" or "NEW" tag ---
            status_x = self._col_x(len(_COL_DEFS) - 1) + cell_pad
            is_my_turn = (game.turn_player_id == game.player_id)
            is_new = game.game_id in self.state._new_game_ids

            if is_new:
                tag_text = 'NEW'
                tag_surf = self._tag_font.render(tag_text, True, _NEW_TAG_TXT)
                tw, th = tag_surf.get_size()
                pad_x, pad_y = int(0.006 * _SW), int(0.003 * _SH)
                tag_rect = pygame.Rect(status_x, rect.centery - (th + 2 * pad_y) // 2,
                                       tw + 2 * pad_x, th + 2 * pad_y)
                tag_bg = pygame.Surface((tag_rect.w, tag_rect.h), pygame.SRCALPHA)
                pygame.draw.rect(tag_bg, _NEW_TAG_BG, tag_bg.get_rect(), border_radius=4)
                self.window.blit(tag_bg, tag_rect.topleft)
                self.window.blit(tag_surf, (tag_rect.x + pad_x, tag_rect.y + pad_y))
            elif is_my_turn:
                turn_surf = self._cell_font.render("Your turn", True, _TURN_TAG_CLR)
                self.window.blit(turn_surf, (status_x, text_y))

            # Online dot next to opponent name
            dot_clr = _DOT_ONLINE if getattr(game, 'opponent_online', False) else _DOT_OFFLINE
            dot_x = self._col_x(0) + cell_pad + int(0.006 * _SW)
            dot_y = rect.y + rect.h // 2
            pygame.draw.circle(self.window, dot_clr, (dot_x, dot_y), _DOT_RADIUS)

        self.window.set_clip(None)

        # Scrollbar
        if self._needs_scroll():
            # Track
            track = self._track_rect()
            track_surf = pygame.Surface((track.w, track.h), pygame.SRCALPHA)
            track_surf.fill(_SCROLLBAR_CLR)
            self.window.blit(track_surf, track.topleft)
            # Thumb
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

        # Non-blocking game list refresh (every 5s)
        if not hasattr(self, '_games_poller'):
            self._games_poller = None
        current_time = pygame.time.get_ticks()
        if current_time - self.last_update_time >= self.update_interval:
            self.last_update_time = current_time
            if self._games_poller is None:
                self._games_poller = BackgroundPoller(self._fetch_games)
            if not self._games_poller.busy:
                self._games_poller.poll()
        # Apply when ready
        if hasattr(self, '_games_poller') and self._games_poller and self._games_poller.has_result():
            new_games = self._games_poller.result
            if new_games is not None:
                self.games = new_games
                n = len(self.games)
                self._content_h = n * (_ROW_H + _ROW_GAP) - (_ROW_GAP if n else 0)
                self._max_scroll = max(0, self._content_h - self._viewport_h)
                self._scroll_y = min(self._scroll_y, self._max_scroll)
                self._row_rects = []

        # Hover detection (only for visible, non-clipped rows)
        mx, my = pygame.mouse.get_pos()
        self._hovered_row = -1
        for i, rect in enumerate(self._row_rects):
            if (rect.top >= self._rows_top and rect.bottom <= self._rows_bottom
                    and rect.collidepoint(mx, my)):
                self._hovered_row = i
                break

    # ── Events ────────────────────────────────────────────────────

    def handle_events(self, events):
        super().handle_events(events)

        for event in events:
            if self._handle_icon_events(event):
                continue

            # Scroll wheel
            if event.type == MOUSEWHEEL:
                box = pygame.Rect(_BOX_X, self._rows_top, _BOX_W, self._viewport_h)
                if box.collidepoint(pygame.mouse.get_pos()):
                    self._scroll_y = max(0, min(self._max_scroll,
                                                self._scroll_y - event.y * int(0.04 * _SH)))

            # Scrollbar thumb drag
            if event.type == MOUSEBUTTONDOWN and event.button == 1:
                thumb = self._thumb_rect()
                if thumb.collidepoint(event.pos):
                    self._dragging_thumb = True
                    self._drag_offset = event.pos[1] - thumb.y

            if event.type == MOUSEBUTTONUP and event.button == 1:
                self._dragging_thumb = False

            if event.type == MOUSEMOTION and self._dragging_thumb:
                track = self._track_rect()
                thumb_h = self._thumb_rect().h
                travel = track.h - thumb_h
                if travel > 0:
                    new_top = event.pos[1] - self._drag_offset - track.y
                    frac = max(0.0, min(1.0, new_top / travel))
                    self._scroll_y = int(frac * self._max_scroll)

            # Row click
            if not self.dialogue_box and event.type == MOUSEBUTTONUP and event.button == 1:
                if not self._dragging_thumb:
                    self._handle_row_click()

        if self.state.action["task"] == "load_game" and self.state.action["status"] != "open":
            self._handle_game_loading()

    def _handle_row_click(self):
        mx, my = pygame.mouse.get_pos()
        for i, rect in enumerate(self._row_rects):
            if (rect.top >= self._rows_top and rect.bottom <= self._rows_bottom
                    and rect.collidepoint(mx, my)):
                game = self.games[i]
                label = f"{game.opponent_name}  —  {game.date}"
                self.set_action("load_game", label, "open")
                stake_str = f"{game.stake} gold"
                time_str = f"{game.turn_time_limit // 60} min" if game.turn_time_limit else "No Limit"
                self.make_dialogue_box(
                    f'Load game vs {game.opponent_name}?\n\n'
                    f'Stake: {stake_str}\nTurn Limit: {time_str}',
                    actions=["yes", "cancel"], title="Load Game")
                return

    def _handle_game_loading(self):
        if self.state.action["status"] == 'yes':
            game_label = self.state.action["content"]
            game = next(
                (g for g in self.games
                 if f"{g.opponent_name}  —  {g.date}" == game_label), None)
            if game:
                self.state.game = game
                self.state.set_msg(f"Loaded game with {game.opponent_name}")
                self.state.screen = "game"
            else:
                self.state.set_msg("Game not found")
        self.reset_action()

    def reset_action(self):
        print(f"Resetting action. Task: {self.state.action['task']}, Status: {self.state.action['status']}")
        self.state.action = {"task": None, "content": None, "status": None}
