import pygame
from pygame.locals import *
from datetime import datetime
from email.utils import parsedate_to_datetime
from game.screens.screen import Screen
from game.screens._menu_base import MenuScreenMixin
from config import settings
from utils.utils import Button
from utils.game_service import fetch_user_games, fetch_user
from utils.auth_service import send_heartbeat
from utils.background_poller import BackgroundPoller

_SW, _SH = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT

# Badge appearance
_BADGE_RADIUS = int(0.014 * _SH)
_BADGE_CLR    = (210, 40, 40)
_BADGE_TXT    = (255, 255, 255)


class GameMenuScreen(MenuScreenMixin, Screen):
    def __init__(self, state):
        super().__init__(state)

        # Disable base-class ControlButtons (we use icon buttons instead)
        self.control_buttons = []

        # ── Shared chrome (background, gold, icon buttons) ──────────
        self._init_menu_chrome()

        # ── Custom button image ─────────────────────────────────────
        self._btn_img = pygame.image.load(settings.GAME_MENU_BTN_IMG_PATH).convert_alpha()

        # ── Title font ──────────────────────────────────────────────
        self._title_font = pygame.font.Font(settings.FONT_PATH, settings.GAME_MENU_TITLE_FONT_SIZE)
        self._title_font.set_bold(True)
        self._title_surf = self._title_font.render('Nepal Kings', True, settings.GAME_MENU_TITLE_CLR)

        # ── Menu buttons (centred) ──────────────────────────────────
        _btn_w = settings.GAME_MENU_BTN_W
        _btn_h = settings.GAME_MENU_BTN_H
        _btn_gap = settings.GAME_MENU_BTN_GAP

        btn_x = (_SW - _btn_w) // 2
        title_h = self._title_surf.get_height() + settings.GAME_MENU_TITLE_PAD_BOTTOM
        n_btns = 3
        content_h = title_h + n_btns * _btn_h + (n_btns - 1) * _btn_gap
        box_h = settings.GAME_MENU_BOX_PAD_TOP + content_h + settings.GAME_MENU_BOX_PAD_BOTTOM
        box_w = _btn_w + settings.GAME_MENU_BOX_PAD_X * 2
        self._box_rect = pygame.Rect(
            (_SW - box_w) // 2,
            (_SH - box_h) // 2,
            box_w, box_h)

        first_btn_y = self._box_rect.y + settings.GAME_MENU_BOX_PAD_TOP + title_h

        self.button_new  = Button(self.window, btn_x, first_btn_y,
                                  "New Game", width=_btn_w, height=_btn_h)
        self.button_load = Button(self.window, btn_x, first_btn_y + _btn_h + _btn_gap,
                                  "Load Game", width=_btn_w, height=_btn_h)
        self.button_rankings = Button(self.window, btn_x, first_btn_y + 2 * (_btn_h + _btn_gap),
                                  "Rankings", width=_btn_w, height=_btn_h)

        # Apply custom button images
        for btn in (self.button_new, self.button_load, self.button_rankings):
            btn.button_image = pygame.transform.smoothscale(
                self._btn_img, (btn.rect.width, btn.rect.height))
            btn.button_image_small = pygame.transform.smoothscale(
                self._btn_img, (int(btn.rect.width * 0.95), int(btn.rect.height * 0.95)))

        # ── Oversized glow images (drawn BEHIND the button) ─────────
        glow_w = int(_btn_w * settings.GAME_MENU_GLOW_W_FACTOR)
        glow_h = int(_btn_h * settings.GAME_MENU_GLOW_H_FACTOR)
        self._menu_glows = {}
        for colour in ('yellow', 'white', 'orange'):
            raw = pygame.image.load(settings.GAME_MENU_GLOW_DIR + colour + '.png').convert_alpha()
            self._menu_glows[colour] = pygame.transform.smoothscale(raw, (glow_w, glow_h))

        self.menu_buttons += [self.button_new, self.button_load, self.button_rankings]

        # ── Badge polling ───────────────────────────────────────────
        self._badge_timer = 0
        self._badge_interval = 5000          # ms between server polls
        self._badge_font = pygame.font.Font(settings.FONT_PATH, int(0.018 * _SH))
        self._badge_font.set_bold(True)

        # ── Pre-render the dark box surface ─────────────────────────
        self._box_surf = pygame.Surface(
            (self._box_rect.w, self._box_rect.h), pygame.SRCALPHA)
        self._box_surf.fill(settings.GAME_MENU_BOX_BG_CLR)
        pygame.draw.rect(self._box_surf, settings.GAME_MENU_BOX_BORDER_CLR,
                         self._box_surf.get_rect(), settings.GAME_MENU_BOX_BORDER_W)

    # ── helper: draw a menu button with glow BEHIND ─────────────────
    def _draw_menu_button(self, btn):
        """Draw *btn* with the glow rendered behind the button image."""
        is_disabled = hasattr(btn, 'disabled') and btn.disabled

        # 1) Glow first (behind everything)
        if not is_disabled:
            if btn.hovered and btn.clicked:
                glow = self._menu_glows['yellow']
            elif btn.hovered and not btn.active:
                glow = self._menu_glows['white']
            elif btn.active:
                glow = self._menu_glows['orange']
            else:
                glow = None
            if glow:
                gx = btn.rect.centerx - glow.get_width() // 2
                gy = btn.rect.centery - glow.get_height() // 2
                self.window.blit(glow, (gx, gy))

        # 2) Button image
        if btn.clicked:
            img = btn.button_image_small
            pos = img.get_rect(center=btn.rect.center).topleft
        else:
            img = btn.button_image
            pos = btn.rect.topleft
        self.window.blit(img, pos)

        # 3) Text on top
        font = btn.font_small if btn.clicked else btn.font
        text_surf = font.render(btn.text, True, btn.get_text_color())
        self.window.blit(text_surf, text_surf.get_rect(center=btn.rect.center))

    def render(self):
        """Render the Game Menu Screen."""
        # Background + gold display
        self._draw_menu_chrome()

        # Dark transparent box
        self.window.blit(self._box_surf, self._box_rect.topleft)

        # Title
        title_x = self._box_rect.centerx - self._title_surf.get_width() // 2
        title_y = self._box_rect.y + settings.GAME_MENU_BOX_PAD_TOP
        self.window.blit(self._title_surf, (title_x, title_y))

        # Menu buttons – custom draw with glow behind
        for btn in (self.button_new, self.button_load, self.button_rankings):
            self._draw_menu_button(btn)

        # Badges
        self._draw_badge(self.button_load, self.state.badge_new_games)
        self._draw_badge(self.button_new, self.state.badge_new_challenges)

        # Messages / dialogue / icon buttons (overlay)
        self._draw_menu_overlay()


    # ── badge helpers ────────────────────────────────────────────────

    @staticmethod
    def _parse_date(date_str):
        """Parse a date string from the server into a naive datetime object.

        Handles ISO format (``2026-03-09T15:00:00``) as well as the HTTP‑date
        format used by Flask's default JSON serializer
        (``Mon, 09 Mar 2026 15:00:00 GMT``).
        """
        if not date_str:
            return None
        # Fast path — ISO formats (used by explicit .isoformat() calls)
        for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f',
                    '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f'):
            try:
                return datetime.strptime(date_str, fmt)
            except (ValueError, TypeError):
                continue
        # Fallback — HTTP‑date / RFC 2822 (Flask's jsonify default for datetime)
        try:
            return parsedate_to_datetime(date_str).replace(tzinfo=None)
        except (ValueError, TypeError):
            pass
        return None

    @staticmethod
    def _bg_poll_badges(username):
        """Thread-safe: heartbeat + fetch games/user."""
        send_heartbeat(username)
        games = fetch_user_games(username)
        user = fetch_user(username)
        return {'games': games, 'user': user}

    def _poll_badges(self):
        """Fetch game / challenge counts from the server and update badges.

        On the very first poll after login, items whose date is newer than the
        user's previous ``last_active`` are treated as unseen so the badge
        correctly reflects changes that happened while the user was offline.
        """
        username = self.state.user_dict.get('username') if self.state.user_dict else None
        if not username:
            return

        # Kick off background fetch
        if not hasattr(self, '_badge_poller') or self._badge_poller is None:
            self._badge_poller = BackgroundPoller(
                self._bg_poll_badges, args=(username,))
        if not self._badge_poller.busy:
            self._badge_poller.poll(args=(username,))

    def _apply_badge_data(self, data):
        """Apply badge data fetched in background thread."""
        if not data:
            return
        username = self.state.user_dict.get('username') if self.state.user_dict else None
        if not username:
            return

        last_seen = self._parse_date(self.state._last_seen_at)

        try:
            game_dicts = data['games']
            user = data['user']
            current_game_ids = {g['id'] for g in game_dicts}
            if self.state._known_game_ids is None:
                # First poll after login — check which games appeared while offline
                if last_seen:
                    new_ids = set()
                    for g in game_dicts:
                        dt = self._parse_date(str(g.get('date', '')))
                        if dt and dt > last_seen:
                            new_ids.add(g['id'])
                    self.state.badge_new_games = len(new_ids)
                    self.state._new_game_ids = set(new_ids)
                    self.state._known_game_ids = current_game_ids - new_ids
                else:
                    # No previous session — treat everything as seen
                    self.state._known_game_ids = set(current_game_ids)
                    self.state._new_game_ids = set()
                    self.state.badge_new_games = 0
            else:
                new_ids = current_game_ids - self.state._known_game_ids
                self.state.badge_new_games = len(new_ids)
                self.state._new_game_ids = set(new_ids)

            # -- new challenges received --
            received = user.get('challenges_received', [])
            current_ch_ids = {c['id'] for c in received}
            if self.state._known_challenge_ids is None:
                if last_seen:
                    new_ch = set()
                    for c in received:
                        dt = self._parse_date(str(c.get('date', '')))
                        if dt and dt > last_seen:
                            new_ch.add(c['id'])
                    self.state.badge_new_challenges = len(new_ch)
                    self.state._new_challenge_ids = set(new_ch)
                    self.state._known_challenge_ids = current_ch_ids - new_ch
                else:
                    self.state._known_challenge_ids = set(current_ch_ids)
                    self.state._new_challenge_ids = set()
                    self.state.badge_new_challenges = 0
            else:
                new_ch = current_ch_ids - self.state._known_challenge_ids
                self.state.badge_new_challenges = len(new_ch)
                self.state._new_challenge_ids = set(new_ch)
        except Exception:
            pass  # network failure — keep previous counts

    def _draw_badge(self, btn, count):
        """Draw a small red notification badge at the top-right of *btn*."""
        if count <= 0:
            return
        cx = btn.rect.right - _BADGE_RADIUS
        cy = btn.rect.top + _BADGE_RADIUS
        pygame.draw.circle(self.window, _BADGE_CLR, (cx, cy), _BADGE_RADIUS)
        txt = self._badge_font.render(str(count), True, _BADGE_TXT)
        self.window.blit(txt, txt.get_rect(center=(cx, cy)))

    def update(self, events):
        """Update the Game Menu Screen."""
        super().update()
        self._update_icon_buttons()

        # Periodic badge poll
        now = pygame.time.get_ticks()
        if now - self._badge_timer >= self._badge_interval:
            self._badge_timer = now
            self._poll_badges()

        # Apply badge data when background fetch completes
        if hasattr(self, '_badge_poller') and self._badge_poller and self._badge_poller.has_result():
            self._apply_badge_data(self._badge_poller.result)

    def handle_events(self, events):
        """Handle button click events."""
        super().handle_events(events)

        for event in events:
            if self._handle_icon_events(event):
                continue
            if event.type == MOUSEBUTTONUP:
                self.handle_button_clicks()

    def handle_button_clicks(self):
        """Handle clicks on the menu buttons."""
        if self.button_new.collide():
            # Mark current challenges as seen
            self.state.badge_new_challenges = 0
            try:
                username = self.state.user_dict.get('username') if self.state.user_dict else None
                if username:
                    user = fetch_user(username)
                    received = user.get('challenges_received', [])
                    self.state._known_challenge_ids = {c['id'] for c in received}
            except Exception:
                pass
            self.state.screen = 'new_game'
            print("New Game button clicked")
        elif self.button_load.collide():
            # Mark current games as seen
            self.state.badge_new_games = 0
            try:
                username = self.state.user_dict.get('username') if self.state.user_dict else None
                if username:
                    game_dicts = fetch_user_games(username)
                    self.state._known_game_ids = {g['id'] for g in game_dicts}
            except Exception:
                pass
            self.state.screen = 'load_game'
            print("Load Game button clicked")
        elif self.button_rankings.collide():
            self.state.screen = 'rankings'
            print("Rankings button clicked")
