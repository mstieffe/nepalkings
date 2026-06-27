# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
import sys as _sys
import pygame
from pygame.locals import *
from game.screens.screen import Screen
from config import settings
from config.screen_settings import _FS
from utils.utils import Button, InputField
from utils.auth_service import login, register
import utils.http_compat as _http

_IS_WEB = (_sys.platform == 'emscripten')

_SW, _SH = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT

MAX_USERNAME_LENGTH = 15
MAX_PASSWORD_LENGTH = 15

# ── Dark-theme input-field styling ─────────────────────────────────
_FIELD_W          = int(0.26 * _SW)
_FIELD_H          = int(0.045 * _FS)
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


def _response_error_message(resp, fallback):
    """Return the server-provided error message when the response has one."""
    try:
        message = resp.json().get('message')
    except Exception:
        return fallback
    return message or fallback


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
        self._legal_confirmed = False

        # Async auth state (web only)
        self._pending_rid = None   # request-id from http_compat.start_async_post
        self._pending_action = None  # 'login' or 'register'

        # ── Background (greyscale) ──────────────────────────────────
        self._bg = self._load_bg()

        # ── Button image ────────────────────────────────────────────
        self._btn_img = pygame.image.load(settings.LOGIN_BTN_IMG_PATH).convert_alpha()

        # ── Fonts ───────────────────────────────────────────────────
        self._title_font = settings.get_font(settings.GAME_MENU_TITLE_FONT_SIZE, bold=True)
        self._title_surf = self._title_font.render('Nepal Kings', True, settings.GAME_MENU_TITLE_CLR)

        self._field_font = settings.get_font(int(0.026 * _FS))
        self._label_font = settings.get_font(int(0.020 * _FS))
        self._legal_font = settings.get_font(max(12, int(0.018 * _FS)))
        self._loading_font = settings.get_font(int(0.024 * _FS))

        # ── Layout ──────────────────────────────────────────────────
        _btn_w   = settings.GAME_MENU_BTN_W
        _btn_h   = settings.GAME_MENU_BTN_H
        _btn_gap = settings.GAME_MENU_BTN_GAP
        _label_h = self._label_font.get_height() + _LABEL_GAP
        _field_gap   = int(0.020 * _SH)
        _section_gap = int(0.030 * _SH)
        _legal_gap = int(0.012 * _SH)
        _legal_h = max(int(0.047 * _SH), self._legal_font.get_height() * 2 + 4)

        title_h = self._title_surf.get_height() + settings.GAME_MENU_TITLE_PAD_BOTTOM

        content_h = (title_h
                     + _label_h + _FIELD_H + _field_gap
                     + _label_h + _FIELD_H + _legal_gap + _legal_h + _section_gap
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
        y += _FIELD_H + _legal_gap

        # Legal acceptance for registration only.
        self._legal_rect = pygame.Rect(field_x, y, _FIELD_W, _legal_h)
        box_size = min(max(14, self._legal_font.get_height()), _legal_h - 4)
        self._legal_box_rect = pygame.Rect(field_x, y + 2, box_size, box_size)
        # Tight toggle hit area (checkbox + the plain label only) and the
        # clickable Terms/Privacy link rects are computed during draw, once
        # text widths are known.
        self._legal_toggle_rect = self._legal_box_rect.copy()
        self._terms_link_rect = pygame.Rect(0, 0, 0, 0)
        self._privacy_link_rect = pygame.Rect(0, 0, 0, 0)
        # Scrollable legal-document overlay state.
        self._legal_doc = None        # {'title', 'lines', 'scroll', 'max_scroll'}
        self._legal_doc_close_rect = pygame.Rect(0, 0, 0, 0)
        self._legal_doc_cache = {}    # slug -> wrapped lines
        y += _legal_h + _section_gap

        # Buttons
        self.button_login = Button(self.window, btn_x, y,
                                   "Login", width=_btn_w, height=_btn_h)
        y += _btn_h + _btn_gap
        self.button_register = Button(self.window, btn_x, y,
                                      "Register", width=_btn_w, height=_btn_h)
        self.button_register.disabled = True

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

    _LEGAL_LINK_CLR = (120, 180, 250)

    def _draw_legal_confirmation(self):
        mouse = pygame.mouse.get_pos()
        # Checkbox — highlighted when hovered over the toggle area or checked.
        toggle_hover = self._legal_toggle_rect.collidepoint(mouse)
        bdr = _FIELD_BDR_ACTIVE if toggle_hover or self._legal_confirmed else _FIELD_BDR_PASSIVE
        pygame.draw.rect(self.window, bdr, self._legal_box_rect, 1,
                         border_radius=max(2, _FIELD_CORNER_R // 2))
        if self._legal_confirmed:
            x, y = self._legal_box_rect.x, self._legal_box_rect.y
            w, h = self._legal_box_rect.w, self._legal_box_rect.h
            pygame.draw.line(self.window, _FIELD_LABEL_CLR,
                             (x + int(0.22 * w), y + int(0.55 * h)),
                             (x + int(0.43 * w), y + int(0.76 * h)), 2)
            pygame.draw.line(self.window, _FIELD_LABEL_CLR,
                             (x + int(0.41 * w), y + int(0.76 * h)),
                             (x + int(0.80 * w), y + int(0.24 * h)), 2)

        font = self._legal_font
        gap = int(0.006 * _SW)
        x = self._legal_box_rect.right + int(0.008 * _SW)
        # Line 1: plain label, part of the toggle hit area.
        label1 = font.render("I'm 13+ and accept the", True, _FIELD_TEXT_CLR)
        ty1 = self._legal_box_rect.y
        self.window.blit(label1, (x, ty1))
        # The toggle hit area = checkbox + line-1 label only (NOT the links),
        # so clicking far right or on a link no longer toggles acceptance.
        self._legal_toggle_rect = self._legal_box_rect.union(
            pygame.Rect(x, ty1, label1.get_width(), label1.get_height()))

        # Line 2: [Terms] & [Privacy] as clickable links.
        ty2 = ty1 + label1.get_height() + 2
        terms_surf = font.render('Terms', True, self._LEGAL_LINK_CLR)
        amp_surf = font.render('  &  ', True, _FIELD_LABEL_CLR)
        privacy_surf = font.render('Privacy', True, self._LEGAL_LINK_CLR)
        lx = x
        self.window.blit(terms_surf, (lx, ty2))
        self._terms_link_rect = pygame.Rect(lx, ty2, terms_surf.get_width(),
                                             terms_surf.get_height())
        lx += terms_surf.get_width()
        self.window.blit(amp_surf, (lx, ty2))
        lx += amp_surf.get_width()
        self.window.blit(privacy_surf, (lx, ty2))
        self._privacy_link_rect = pygame.Rect(lx, ty2, privacy_surf.get_width(),
                                               privacy_surf.get_height())
        # Underline the links so they read as tappable.
        for r in (self._terms_link_rect, self._privacy_link_rect):
            underline_clr = (self._LEGAL_LINK_CLR if r.collidepoint(mouse)
                             else (90, 130, 190))
            pygame.draw.line(self.window, underline_clr,
                             (r.x, r.bottom), (r.right, r.bottom), 1)

    # ── Legal-document overlay ──────────────────────────────────────

    def _open_legal_doc(self, slug, title):
        """Fetch and show a legal document in a scrollable overlay."""
        lines = self._legal_doc_cache.get(slug)
        if lines is None:
            lines = self._fetch_legal_doc_lines(slug)
            self._legal_doc_cache[slug] = lines
        self._legal_doc = {'title': title, 'lines': lines, 'scroll': 0}
        self._recompute_legal_doc_scroll()

    def _fetch_legal_doc_lines(self, slug):
        """Return word-wrapped lines for the document, or an error notice."""
        try:
            resp = _http.get(f'{settings.SERVER_URL}/legal/{slug}', timeout=10)
            text = getattr(resp, 'text', '') or ''
            if getattr(resp, 'status_code', 200) != 200 or not text.strip():
                raise ValueError('empty')
        except Exception:
            return ['Could not load this document right now.',
                    '',
                    f'You can read it online at:',
                    f'{settings.SERVER_URL}/legal/{slug}']
        # Strip simple markdown markers for readability and word-wrap.
        max_w = self._legal_doc_panel_rect().w - int(0.04 * _SW)
        wrapped = []
        for raw in text.replace('\r\n', '\n').split('\n'):
            line = raw.rstrip()
            for marker in ('### ', '## ', '# '):
                if line.startswith(marker):
                    line = line[len(marker):]
                    break
            line = line.replace('**', '').replace('`', '')
            wrapped.extend(self._wrap_legal_line(line, max_w))
        return wrapped

    def _wrap_legal_line(self, line, max_w):
        if not line:
            return ['']
        words = line.split(' ')
        out, cur = [], ''
        for w in words:
            cand = (cur + ' ' + w).strip()
            if self._legal_font.size(cand)[0] <= max_w:
                cur = cand
            else:
                if cur:
                    out.append(cur)
                cur = w
        out.append(cur)
        return out

    @staticmethod
    def _legal_doc_panel_rect():
        w = int(0.74 * _SW)
        h = int(0.74 * _SH)
        return pygame.Rect((_SW - w) // 2, (_SH - h) // 2, w, h)

    def _legal_doc_body_rect(self):
        panel = self._legal_doc_panel_rect()
        top = panel.y + int(0.012 * _SH) + self._label_font.get_height() + int(0.012 * _SH)
        return pygame.Rect(panel.x + int(0.02 * _SW), top,
                           panel.w - int(0.04 * _SW),
                           panel.bottom - int(0.06 * _SH) - top)

    def _recompute_legal_doc_scroll(self):
        if not self._legal_doc:
            return
        line_h = self._legal_font.get_height() + 2
        content_h = len(self._legal_doc['lines']) * line_h
        view_h = self._legal_doc_body_rect().h
        self._legal_doc['max_scroll'] = max(0, content_h - view_h)
        self._legal_doc['scroll'] = max(0, min(self._legal_doc['scroll'],
                                               self._legal_doc['max_scroll']))

    def _draw_legal_doc(self):
        if not self._legal_doc:
            return
        # Dim the screen behind the panel.
        veil = pygame.Surface((_SW, _SH), pygame.SRCALPHA)
        veil.fill((0, 0, 0, 180))
        self.window.blit(veil, (0, 0))

        panel = self._legal_doc_panel_rect()
        panel_surf = pygame.Surface((panel.w, panel.h), pygame.SRCALPHA)
        pygame.draw.rect(panel_surf, (28, 26, 22, 252), panel_surf.get_rect(),
                         border_radius=10)
        self.window.blit(panel_surf, panel.topleft)
        pygame.draw.rect(self.window, (120, 105, 75), panel, 2, border_radius=10)

        # Title + close button.
        title_surf = self._label_font.render(self._legal_doc['title'], True,
                                              settings.GAME_MENU_TITLE_CLR)
        self.window.blit(title_surf, (panel.x + int(0.02 * _SW),
                                      panel.y + int(0.012 * _SH)))
        close_sz = int(0.030 * _SH)
        self._legal_doc_close_rect = pygame.Rect(
            panel.right - close_sz - int(0.012 * _SW),
            panel.y + int(0.012 * _SH), close_sz, close_sz)
        cr = self._legal_doc_close_rect
        ch = cr.collidepoint(pygame.mouse.get_pos())
        pygame.draw.rect(self.window, (90, 60, 40) if ch else (60, 45, 30), cr,
                         border_radius=5)
        pygame.draw.line(self.window, (230, 210, 180),
                         (cr.x + 6, cr.y + 6), (cr.right - 6, cr.bottom - 6), 2)
        pygame.draw.line(self.window, (230, 210, 180),
                         (cr.x + 6, cr.bottom - 6), (cr.right - 6, cr.y + 6), 2)

        # Body text (clipped + scrolled).
        body = self._legal_doc_body_rect()
        prev_clip = self.window.get_clip()
        self.window.set_clip(body)
        line_h = self._legal_font.get_height() + 2
        y = body.y - self._legal_doc['scroll']
        for line in self._legal_doc['lines']:
            if y + line_h >= body.y and y <= body.bottom:
                surf = self._legal_font.render(line, True, _FIELD_TEXT_CLR)
                self.window.blit(surf, (body.x, y))
            y += line_h
        self.window.set_clip(prev_clip)

        hint = self._legal_font.render('Scroll to read · click ✕ or outside to close',
                                       True, _FIELD_LABEL_CLR)
        self.window.blit(hint, (panel.x + int(0.02 * _SW),
                                panel.bottom - int(0.035 * _SH)))

    def _handle_legal_doc_events(self, events):
        """Process events while the doc overlay is open. Returns True if open."""
        if not self._legal_doc:
            return False
        panel = self._legal_doc_panel_rect()
        for event in events:
            if event.type == MOUSEWHEEL:
                self._legal_doc['scroll'] = max(
                    0, min(self._legal_doc.get('max_scroll', 0),
                           self._legal_doc['scroll'] - event.y * int(0.05 * _SH)))
            elif event.type == KEYDOWN and event.key in (K_ESCAPE,):
                self._legal_doc = None
                return True
            elif event.type == MOUSEBUTTONUP and event.button == 1:
                if (self._legal_doc_close_rect.collidepoint(event.pos)
                        or not panel.collidepoint(event.pos)):
                    self._legal_doc = None
                    return True
        return True

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
        self._draw_legal_confirmation()

        # Buttons
        if not self.loading:
            for btn in (self.button_login, self.button_register):
                self._draw_button(btn)
        else:
            load_surf = self._loading_font.render('Loading...', True, _LOADING_CLR)
            lx = self._box_rect.centerx - load_surf.get_width() // 2
            ly = self.button_login.rect.y + self.button_login.rect.h // 2
            self.window.blit(load_surf, (lx, ly))

        # Legal-document overlay (above the form, below status messages)
        self._draw_legal_doc()

        # Messages overlay
        super().render()

    # ── Auth handlers ───────────────────────────────────────────────

    def handle_login(self):
        if self.loading:
            return
        if _IS_WEB:
            self.loading = True
            self._pending_rid = _http.start_async_post(
                f'{settings.SERVER_URL}/auth/login',
                data={'username': self.field_username.content,
                      'password': self.field_pwd.content}
            )
            self._pending_action = 'login'
        else:
            self.loading = True
            response_data = login(self.field_username.content, self.field_pwd.content)
            self.loading = False
            self._apply_login_response(response_data)

    def handle_register(self):
        if self.loading:
            return
        if not self._legal_confirmed:
            self.state.set_msg('Confirm age, Terms, and Privacy before registering.')
            return
        legal_data = {
            'age_confirmed': 'true',
            'terms_accepted': 'true',
            'privacy_accepted': 'true',
        }
        if _IS_WEB:
            self.loading = True
            self._pending_rid = _http.start_async_post(
                f'{settings.SERVER_URL}/auth/register',
                data={'username': self.field_username.content,
                      'password': self.field_pwd.content,
                      **legal_data}
            )
            self._pending_action = 'register'
        else:
            self.loading = True
            response_data = register(
                self.field_username.content,
                self.field_pwd.content,
                legal_confirmed=True,
            )
            self.loading = False
            self._apply_register_response(response_data)

    def _poll_pending_auth(self):
        """Check whether the async XHR has finished and process the result."""
        if self._pending_rid is None:
            return
        resp = _http.check_async(self._pending_rid)
        if resp is None:
            return  # still in flight
        # Request finished
        self._pending_rid = None
        self.loading = False
        action = self._pending_action
        self._pending_action = None
        try:
            if resp.status_code == 401:
                response_data = {'success': False, 'message': 'Login failed. Username or password incorrect'}
            elif resp.status_code == 409:
                fallback = 'Registration failed. Username already exists.'
                response_data = {'success': False, 'message': _response_error_message(resp, fallback)}
            elif resp.status_code >= 400:
                fallback = f'Request failed ({resp.status_code}). Please try again.'
                response_data = {'success': False, 'message': _response_error_message(resp, fallback)}
            else:
                response_data = resp.json()
        except Exception:
            response_data = {'success': False, 'message': 'Unexpected error. Please try again.'}
        if action == 'login':
            self._apply_login_response(response_data)
        else:
            self._apply_register_response(response_data)

    def _apply_login_response(self, response_data):
        self.state.set_msg(response_data.get('message', ''))
        if response_data.get('success'):
            # Store auth token for all subsequent requests
            token = response_data.get('token')
            if token:
                _http.set_auth_token(token)
            self.state.user_dict = response_data.get('user')
            self.state.game = None
            self.state._last_seen_at = response_data.get('previous_last_active')
            self.state._known_game_ids = None
            self.state._known_challenge_ids = None
            self.state._new_game_ids = set()
            self.state._new_challenge_ids = set()
            self.state.badge_new_games = 0
            self.state.badge_new_challenges = 0
            self.state.screen = 'game_menu'
        else:
            self.field_username.empty()
            self.field_pwd.empty()

    def _apply_register_response(self, response_data):
        self.state.set_msg(response_data.get('message', ''))
        if response_data.get('success'):
            # Store auth token for all subsequent requests
            token = response_data.get('token')
            if token:
                _http.set_auth_token(token)
            self.state.user_dict = response_data.get('user')
            self.state.game = None
            self.state._last_seen_at = None
            self.state._known_game_ids = None
            self.state._known_challenge_ids = None
            self.state._new_game_ids = set()
            self.state._new_challenge_ids = set()
            self.state.badge_new_games = 0
            self.state.badge_new_challenges = 0
            self.state.screen = 'game_menu'
        else:
            self.field_username.empty()
            self.field_pwd.empty()

    # ── Events ──────────────────────────────────────────────────────

    def handle_events(self, events):
        super().handle_events(events)

        # While a legal document is open, it captures all input.
        if self._handle_legal_doc_events(events):
            return

        for event in events:
            response_username = self.field_username.handle_event(event)
            response_pwd = self.field_pwd.handle_event(event)

            if response_username == 'switch' or response_pwd == 'switch':
                self.field_username.active = not self.field_username.active
                self.field_pwd.active = not self.field_pwd.active

            if event.type == KEYDOWN and event.key == K_RETURN:
                self.handle_login()

            elif event.type == MOUSEBUTTONUP:
                if self._terms_link_rect.collidepoint(event.pos):
                    self._open_legal_doc('terms', 'Terms of Use')
                elif self._privacy_link_rect.collidepoint(event.pos):
                    self._open_legal_doc('privacy', 'Privacy Policy')
                elif self._legal_toggle_rect.collidepoint(event.pos):
                    self._legal_confirmed = not self._legal_confirmed
                elif self.button_login.collide():
                    self.handle_login()
                elif self.button_register.collide():
                    self.handle_register()

    def update(self, events):
        super().update()
        self.button_register.disabled = not self._legal_confirmed
        self.button_login.update()
        self.button_register.update()
        if _IS_WEB:
            self._poll_pending_auth()
