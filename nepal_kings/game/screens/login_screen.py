import pygame
from pygame.locals import *
from game.screens.screen import Screen
from config import settings
from utils.utils import Button, InputField
from utils.auth_service import login, register

_SW, _SH = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT

MAX_USERNAME_LENGTH = 15
MAX_PASSWORD_LENGTH = 15

# ── Dark-theme input-field styling ─────────────────────────────────
_FIELD_W          = int(0.26 * _SW)
_FIELD_H          = int(0.045 * _SH)
_FIELD_CORNER_R   = int(0.006 * _SH)
_FIELD_BORDER_W   = 1
_FIELD_BG_PASSIVE = (35, 35, 45, 200)
_FIELD_BG_ACTIVE  = (50, 50, 65, 220)
_FIELD_BG_HOVER   = (45, 45, 55, 210)
_FIELD_BDR_PASSIVE = (100, 95, 85)
_FIELD_BDR_ACTIVE  = (220, 200, 140)
_FIELD_TEXT_CLR    = (230, 225, 210)
_FIELD_LABEL_CLR  = (220, 200, 140)
_FIELD_CURSOR_CLR = (220, 200, 140)
_FIELD_PAD_X      = int(0.010 * _SW)
_LABEL_GAP        = int(0.006 * _SH)

# ── Loading text ────────────────────────────────────────────────────
_LOADING_CLR = (200, 185, 150)


class LoginScreen(Screen):
    # Class-level cache: greyscale background loaded once, shared
    _bg_cache = None

    @classmethod
    def _load_bg(cls):
        if cls._bg_cache is None:
            raw_bg = pygame.image.load(settings.LOGIN_BG_IMG_PATH).convert()
            cls._bg_cache = pygame.transform.smoothscale(raw_bg, (_SW, _SH))
        return cls._bg_cache

    def __init__(self, state):
        super().__init__(state)
        self.loading = False
        self.control_buttons = []

        # ── Background (greyscale) ──────────────────────────────────
        self._bg = self._load_bg()

        # ── Button image ────────────────────────────────────────────
        self._btn_img = pygame.image.load(settings.LOGIN_BTN_IMG_PATH).convert_alpha()

        # ── Fonts ───────────────────────────────────────────────────
        self._title_font = pygame.font.Font(settings.FONT_PATH, settings.GAME_MENU_TITLE_FONT_SIZE)
        self._title_font.set_bold(True)
        self._title_surf = self._title_font.render('Nepal Kings', True, settings.GAME_MENU_TITLE_CLR)

        self._field_font = pygame.font.Font(settings.FONT_PATH, int(0.026 * _SH))
        self._label_font = pygame.font.Font(settings.FONT_PATH, int(0.020 * _SH))
        self._loading_font = pygame.font.Font(settings.FONT_PATH, int(0.024 * _SH))

        # ── Layout ──────────────────────────────────────────────────
        _btn_w   = settings.GAME_MENU_BTN_W
        _btn_h   = settings.GAME_MENU_BTN_H
        _btn_gap = settings.GAME_MENU_BTN_GAP
        _label_h = self._label_font.get_height() + _LABEL_GAP
        _field_gap   = int(0.020 * _SH)
        _section_gap = int(0.030 * _SH)

        title_h = self._title_surf.get_height() + settings.GAME_MENU_TITLE_PAD_BOTTOM

        content_h = (title_h
                     + _label_h + _FIELD_H + _field_gap
                     + _label_h + _FIELD_H + _section_gap
                     + _btn_h + _btn_gap + _btn_h)

        box_w = _btn_w + settings.GAME_MENU_BOX_PAD_X * 2
        box_h = settings.GAME_MENU_BOX_PAD_TOP + content_h + settings.GAME_MENU_BOX_PAD_BOTTOM

        self._box_rect = pygame.Rect(
            (_SW - box_w) // 2,
            (_SH - box_h) // 2,
            box_w, box_h)

        btn_x   = (_SW - _btn_w)   // 2
        field_x = (_SW - _FIELD_W) // 2

        y = self._box_rect.y + settings.GAME_MENU_BOX_PAD_TOP + title_h

        # Username
        self._username_label_y = y
        y += _label_h
        self.field_username = InputField(self.window, field_x, y,
                                         "username", "", False, True,
                                         max_length=MAX_USERNAME_LENGTH,
                                         width=_FIELD_W, height=_FIELD_H)
        y += _FIELD_H + _field_gap

        # Password
        self._pwd_label_y = y
        y += _label_h
        self.field_pwd = InputField(self.window, field_x, y,
                                     "password", "", True, False,
                                     max_length=MAX_PASSWORD_LENGTH,
                                     width=_FIELD_W, height=_FIELD_H)
        y += _FIELD_H + _section_gap

        # Buttons
        self.button_login = Button(self.window, btn_x, y,
                                   "Login", width=_btn_w, height=_btn_h)
        y += _btn_h + _btn_gap
        self.button_register = Button(self.window, btn_x, y,
                                      "Register", width=_btn_w, height=_btn_h)

        # Apply custom button images
        for btn in (self.button_login, self.button_register):
            btn.button_image = pygame.transform.smoothscale(
                self._btn_img, (btn.rect.width, btn.rect.height))
            btn.button_image_small = pygame.transform.smoothscale(
                self._btn_img, (int(btn.rect.width * 0.95),
                                int(btn.rect.height * 0.95)))

        # Glow images (same glow dir as game menu)
        glow_w = int(_btn_w * settings.GAME_MENU_GLOW_W_FACTOR)
        glow_h = int(_btn_h * settings.GAME_MENU_GLOW_H_FACTOR)
        self._glows = {}
        for colour in ('yellow', 'white', 'orange'):
            raw = pygame.image.load(
                settings.GAME_MENU_GLOW_DIR + colour + '.png').convert_alpha()
            self._glows[colour] = pygame.transform.smoothscale(raw, (glow_w, glow_h))

        # Dark box surface
        self._box_surf = pygame.Surface(
            (self._box_rect.w, self._box_rect.h), pygame.SRCALPHA)
        self._box_surf.fill(settings.GAME_MENU_BOX_BG_CLR)
        pygame.draw.rect(self._box_surf, settings.GAME_MENU_BOX_BORDER_CLR,
                         self._box_surf.get_rect(), settings.GAME_MENU_BOX_BORDER_W)

    # ── Custom button draw (glow BEHIND) ────────────────────────────

    def _draw_button(self, btn):
        is_disabled = hasattr(btn, 'disabled') and btn.disabled
        if not is_disabled:
            if btn.hovered and btn.clicked:
                glow = self._glows['yellow']
            elif btn.hovered and not btn.active:
                glow = self._glows['white']
            elif btn.active:
                glow = self._glows['orange']
            else:
                glow = None
            if glow:
                gx = btn.rect.centerx - glow.get_width() // 2
                gy = btn.rect.centery - glow.get_height() // 2
                self.window.blit(glow, (gx, gy))

        if btn.clicked:
            img = btn.button_image_small
            pos = img.get_rect(center=btn.rect.center).topleft
        else:
            img = btn.button_image
            pos = btn.rect.topleft
        self.window.blit(img, pos)

        font = btn.font_small if btn.clicked else btn.font
        text_surf = font.render(btn.text, True, btn.get_text_color())
        self.window.blit(text_surf, text_surf.get_rect(center=btn.rect.center))

    # ── Custom input-field draw (dark theme) ────────────────────────

    def _draw_field(self, field, label_y):
        """Draw an input field with dark-theme styling."""
        # Label
        label_surf = self._label_font.render(field.name.capitalize(), True, _FIELD_LABEL_CLR)
        lx = field.rect.x
        self.window.blit(label_surf, (lx, label_y))

        # Background
        if field.active:
            bg = _FIELD_BG_ACTIVE
        elif field.rect.collidepoint(pygame.mouse.get_pos()):
            bg = _FIELD_BG_HOVER
        else:
            bg = _FIELD_BG_PASSIVE
        surf = pygame.Surface((field.rect.w, field.rect.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, bg, surf.get_rect(), border_radius=_FIELD_CORNER_R)
        self.window.blit(surf, field.rect.topleft)

        # Border
        bdr = _FIELD_BDR_ACTIVE if field.active else _FIELD_BDR_PASSIVE
        pygame.draw.rect(self.window, bdr, field.rect,
                         _FIELD_BORDER_W, border_radius=_FIELD_CORNER_R)

        # Content text
        visible = '*' * len(field.content) if field.pwd else field.content
        text_surf = self._field_font.render(visible, True, _FIELD_TEXT_CLR)
        ty = field.rect.y + (field.rect.h - text_surf.get_height()) // 2
        self.window.blit(text_surf, (field.rect.x + _FIELD_PAD_X, ty))

        # Cursor
        if field.active and pygame.time.get_ticks() % 1000 < 500:
            cursor_x = (field.rect.x + _FIELD_PAD_X
                        + self._field_font.size(visible[:field.cursor_pos])[0])
            cursor_y = field.rect.y + int(0.15 * field.rect.h)
            cursor_h = int(0.70 * field.rect.h)
            pygame.draw.line(self.window, _FIELD_CURSOR_CLR,
                             (cursor_x, cursor_y),
                             (cursor_x, cursor_y + cursor_h), 2)

    # ── Render ──────────────────────────────────────────────────────

    def render(self):
        # Background
        self.window.blit(self._bg, (0, 0))

        # Dark box
        self.window.blit(self._box_surf, self._box_rect.topleft)

        # Title
        tx = self._box_rect.centerx - self._title_surf.get_width() // 2
        ty = self._box_rect.y + settings.GAME_MENU_BOX_PAD_TOP
        self.window.blit(self._title_surf, (tx, ty))

        # Input fields
        self._draw_field(self.field_username, self._username_label_y)
        self._draw_field(self.field_pwd, self._pwd_label_y)

        # Buttons
        if not self.loading:
            for btn in (self.button_login, self.button_register):
                self._draw_button(btn)
        else:
            load_surf = self._loading_font.render('Loading...', True, _LOADING_CLR)
            lx = self._box_rect.centerx - load_surf.get_width() // 2
            ly = self.button_login.rect.y + self.button_login.rect.h // 2
            self.window.blit(load_surf, (lx, ly))

        # Messages overlay
        super().render()

    # ── Auth handlers ───────────────────────────────────────────────

    def handle_login(self):
        self.loading = True
        response_data = login(self.field_username.content, self.field_pwd.content)
        self.loading = False

        self.state.set_msg(response_data['message'])
        if response_data['success']:
            self.state.user_dict = response_data.get('user')
            self.state.game = None
            # Store when the user was last online (for offline-aware badges)
            self.state._last_seen_at = response_data.get('previous_last_active')
            # Reset badge tracking so first poll uses _last_seen_at
            self.state._known_game_ids = None
            self.state._known_challenge_ids = None
            self.state._new_game_ids = set()
            self.state._new_challenge_ids = set()
            self.state.badge_new_games = 0
            self.state.badge_new_challenges = 0
            self.state.screen = "game_menu"
        else:
            self.field_username.empty()
            self.field_pwd.empty()

    def handle_register(self):
        self.loading = True
        response_data = register(self.field_username.content, self.field_pwd.content)
        self.loading = False
        self.state.set_msg(response_data['message'])

        if response_data['success']:
            self.state.user_dict = response_data.get('user')
            self.state.game = None
            # New user — no previous session
            self.state._last_seen_at = None
            self.state._known_game_ids = None
            self.state._known_challenge_ids = None
            self.state._new_game_ids = set()
            self.state._new_challenge_ids = set()
            self.state.badge_new_games = 0
            self.state.badge_new_challenges = 0
            self.state.screen = "game_menu"
        else:
            self.field_username.empty()
            self.field_pwd.empty()

    # ── Events ──────────────────────────────────────────────────────

    def handle_events(self, events):
        super().handle_events(events)

        for event in events:
            response_username = self.field_username.handle_event(event)
            response_pwd = self.field_pwd.handle_event(event)

            if response_username == 'switch' or response_pwd == 'switch':
                self.field_username.active = not self.field_username.active
                self.field_pwd.active = not self.field_pwd.active

            if event.type == KEYDOWN and event.key == K_RETURN:
                self.handle_login()

            elif event.type == MOUSEBUTTONUP:
                if self.button_login.collide():
                    self.handle_login()
                elif self.button_register.collide():
                    self.handle_register()

    def update(self, events):
        super().update()
        self.button_login.update()
        self.button_register.update()
