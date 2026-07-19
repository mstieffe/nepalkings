# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
import re as _re
import sys as _sys
import pygame
from pygame.locals import *
from game.screens.screen import Screen
from config import settings
from config.screen_settings import _FS, _IS_MOBILE as _MOBILE_UI, _UI_SCALE
from game.components.buttons.menu_button import Button
from game.components.inputs.input_field import InputField
from utils.auth_service import login, register
import utils.http_compat as _http

_IS_WEB = (_sys.platform == 'emscripten')

_SW, _SH = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT

# Mirror the server's rules (auth.py): username 3-30 [a-zA-Z0-9_-],
# password at least 8 characters.
MAX_USERNAME_LENGTH = 30
MAX_PASSWORD_LENGTH = 64
MIN_USERNAME_LENGTH = 3
MIN_PASSWORD_LENGTH = 8
_USERNAME_RE = _re.compile(r'^[a-zA-Z0-9_-]+$')

USERNAME_HINT = '3-30 chars: letters, numbers, _ -'
PASSWORD_HINT = 'min. 8 characters'

# ── Dark-theme input-field styling ─────────────────────────────────
_FIELD_BORDER_W   = 1
_FIELD_BG_PASSIVE = (35, 35, 45, 200)
_FIELD_BG_ACTIVE  = (50, 50, 65, 220)
_FIELD_BG_HOVER   = (45, 45, 55, 210)
_FIELD_BDR_PASSIVE = (100, 95, 85)
_FIELD_BDR_ACTIVE  = (220, 200, 140)
_FIELD_TEXT_CLR    = (230, 225, 210)
_FIELD_LABEL_CLR  = (220, 200, 140)
_FIELD_CURSOR_CLR = (220, 200, 140)
_HINT_MUTED_CLR   = (150, 142, 122)
_HINT_OK_CLR      = (150, 190, 140)
_HINT_BAD_CLR     = (222, 138, 112)

# ── Loading text ────────────────────────────────────────────────────
_LOADING_CLR = (200, 185, 150)


def _mobile_login_metrics(screen_w, screen_h, ui_scale, touch_target_min):
    """Return mobile form sizes that stay usable across web resolutions.

    The browser client renders to one of several 16:9 canvases and then scales
    that canvas to the device.  Width therefore needs to grow with the mobile
    font scale, while control height must honour the shared touch-target floor.
    Keeping this calculation independent from Pygame also makes the supported
    854/1024/1280 canvas tiers straightforward to test.
    """
    form_fraction = min(0.56, max(0.48, 0.34 * float(ui_scale)))
    return {
        'form_w': int(form_fraction * screen_w),
        'field_h': max(int(0.070 * screen_h), int(touch_target_min)),
        'button_h': max(int(0.070 * screen_h), int(touch_target_min)),
        'panel_pad_x': max(14, int(0.025 * screen_w)),
        'panel_pad_y': max(8, int(0.022 * screen_h)),
        'title_gap': max(5, int(0.014 * screen_h)),
        'label_gap': max(2, int(0.006 * screen_h)),
        # Keep padded touch regions of adjacent controls from overlapping.
        'field_gap': max(12, int(0.034 * screen_h)),
        'legal_gap': max(4, int(0.010 * screen_h)),
        'legal_h': max(32, int(0.070 * screen_h)),
        'section_gap': max(6, int(0.016 * screen_h)),
        'button_gap': max(12, int(0.034 * screen_h)),
        'message_reserve': max(36, int(0.085 * screen_h)),
    }


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
        self._mobile_ui = bool(_MOBILE_UI)

        # ── Background (greyscale) ──────────────────────────────────
        self._bg = self._load_bg()

        # ── Button image ────────────────────────────────────────────
        self._btn_img = pygame.image.load(settings.LOGIN_BTN_IMG_PATH).convert_alpha()

        # ── Fonts ───────────────────────────────────────────────────
        self._title_font = settings.get_font(settings.GAME_MENU_TITLE_FONT_SIZE, bold=True)
        self._title_surf = self._title_font.render('Nepal Kings', True, settings.GAME_MENU_TITLE_CLR)

        self._field_font = settings.get_font(int(0.026 * _FS))
        label_size = int((0.022 if self._mobile_ui else 0.020) * _FS)
        legal_size = int((0.020 if self._mobile_ui else 0.018) * _FS)
        self._label_font = settings.get_font(label_size)
        self._legal_font = settings.get_font(max(15 if self._mobile_ui else 12,
                                                 legal_size))
        self._loading_font = settings.get_font(int(0.024 * _FS))
        # Screen.draw_msg() deliberately uses unscaled desktop text.  Login
        # feedback must remain readable after the mobile canvas is downscaled.
        if self._mobile_ui:
            self._msg_font = settings.get_font(max(14, int(0.020 * _FS)))

        # ── Layout ──────────────────────────────────────────────────
        if self._mobile_ui:
            metrics = _mobile_login_metrics(
                _SW, _SH, _UI_SCALE, settings.TOUCH_TARGET_MIN)
            _field_w = metrics['form_w']
            _field_h = metrics['field_h']
            _btn_w = metrics['form_w']
            _btn_h = metrics['button_h']
            _btn_gap = metrics['button_gap']
            _panel_pad_x = metrics['panel_pad_x']
            _panel_pad_y = metrics['panel_pad_y']
            _title_gap = metrics['title_gap']
            self._label_gap = metrics['label_gap']
            _field_gap = metrics['field_gap']
            _section_gap = metrics['section_gap']
            _legal_gap = metrics['legal_gap']
            _legal_h = max(metrics['legal_h'],
                           self._legal_font.get_height() * 2 + 4)
            _message_reserve = metrics['message_reserve']
        else:
            _field_w = int(0.26 * _SW)
            _field_h = int(0.045 * _FS)
            _btn_w = settings.GAME_MENU_BTN_W
            _btn_h = settings.GAME_MENU_BTN_H
            _btn_gap = settings.GAME_MENU_BTN_GAP
            _panel_pad_x = settings.GAME_MENU_BOX_PAD_X
            _panel_pad_y = settings.GAME_MENU_BOX_PAD_TOP
            _title_gap = settings.GAME_MENU_TITLE_PAD_BOTTOM
            self._label_gap = int(0.006 * _SH)
            _field_gap = int(0.020 * _SH)
            _section_gap = int(0.030 * _SH)
            _legal_gap = int(0.012 * _SH)
            _legal_h = max(int(0.047 * _SH),
                           self._legal_font.get_height() * 2 + 4)
            _message_reserve = 0

        self._panel_pad_y = _panel_pad_y
        self._field_pad_x = max(8, int((0.014 if self._mobile_ui else 0.010) * _SW))
        self._field_corner_r = max(4, int(0.006 * _SH))
        username_label_h = self._field_label_height('Username', USERNAME_HINT,
                                                     _field_w)
        password_label_h = self._field_label_height('Password', PASSWORD_HINT,
                                                     _field_w)

        title_h = self._title_surf.get_height() + _title_gap

        content_h = (title_h
                     + username_label_h + _field_h + _field_gap
                     + password_label_h + _field_h + _legal_gap + _legal_h + _section_gap
                     + _btn_h + _btn_gap + _btn_h)

        box_w = max(_btn_w, _field_w) + _panel_pad_x * 2
        box_h = _panel_pad_y + content_h + _panel_pad_y
        usable_h = max(box_h, _SH - _message_reserve)

        self._box_rect = pygame.Rect(
            (_SW - box_w) // 2,
            max(0, (usable_h - box_h) // 2),
            box_w, box_h)

        btn_x   = (_SW - _btn_w)   // 2
        field_x = (_SW - _field_w) // 2

        y = self._box_rect.y + _panel_pad_y + title_h

        # Username
        self._username_label_y = y
        y += username_label_h
        self.field_username = InputField(self.window, field_x, y,
                                         "username", "", False, True,
                                         max_length=MAX_USERNAME_LENGTH,
                                         width=_field_w, height=_field_h,
                                         web_overlay=True)
        y += _field_h + _field_gap

        # Password
        self._pwd_label_y = y
        y += password_label_h
        self.field_pwd = InputField(self.window, field_x, y,
                                     "password", "", True, False,
                                     max_length=MAX_PASSWORD_LENGTH,
                                     width=_field_w, height=_field_h,
                                     web_overlay=True)
        self._web_inputs_enabled = None
        self._register_mobile_web_inputs()
        y += _field_h + _legal_gap

        # Legal acceptance for registration only.
        self._legal_rect = pygame.Rect(field_x, y, _field_w, _legal_h)
        box_size = min(max(14, self._legal_font.get_height()), _legal_h - 4)
        self._legal_box_rect = pygame.Rect(field_x, y + 2, box_size, box_size)
        # Tight toggle hit area (checkbox + the plain label only) and the
        # clickable Terms/Privacy link rects are computed during draw, once
        # text widths are known.
        self._legal_toggle_rect = self._legal_box_rect.copy()
        self._terms_link_rect = pygame.Rect(0, 0, 0, 0)
        self._privacy_link_rect = pygame.Rect(0, 0, 0, 0)
        self._terms_link_hit_rect = pygame.Rect(0, 0, 0, 0)
        self._privacy_link_hit_rect = pygame.Rect(0, 0, 0, 0)
        # Scrollable legal-document overlay state.
        self._legal_doc = None        # {'title', 'lines', 'scroll', 'max_scroll'}
        self._legal_doc_close_rect = pygame.Rect(0, 0, 0, 0)
        self._legal_doc_cache = {}    # slug -> wrapped lines
        self._legal_doc_drag = None   # (pointer_y, starting_scroll)
        self._legal_doc_dragged = False
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

    def _field_label_height(self, label, hint, field_w):
        """Height of a label row, wrapping its requirement on narrow forms."""
        label_w = self._label_font.size(label)[0]
        hint_w = self._legal_font.size(hint)[0] if hint else 0
        inline_gap = max(8, int(0.010 * _SW))
        if not hint or label_w + inline_gap + hint_w <= field_w:
            return max(self._label_font.get_height(),
                       self._legal_font.get_height()) + self._label_gap
        return (self._label_font.get_height() + 2
                + self._legal_font.get_height() + self._label_gap)

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

    def _draw_field(self, field, label_y, hint=None, hint_state=None):
        """Draw an input field with dark-theme styling.

        *hint* is a short requirement note drawn right-aligned on the label
        row; *hint_state* colours it (None = muted, True = ok, False = bad).
        """
        # Label
        label_surf = self._label_font.render(field.name.capitalize(), True, _FIELD_LABEL_CLR)
        lx = field.rect.x
        self.window.blit(label_surf, (lx, label_y))

        # Requirement hint.  It stays on the label row where possible and
        # moves below the label on unusually narrow canvases.
        if hint:
            if hint_state is None:
                hint_clr = _HINT_MUTED_CLR
            else:
                hint_clr = _HINT_OK_CLR if hint_state else _HINT_BAD_CLR
            hint_surf = self._legal_font.render(hint, True, hint_clr)
            inline_gap = max(8, int(0.010 * _SW))
            if label_surf.get_width() + inline_gap + hint_surf.get_width() <= field.rect.w:
                hy = label_y + (label_surf.get_height() - hint_surf.get_height()) // 2
                hx = field.rect.right - hint_surf.get_width()
            else:
                hx = field.rect.x
                hy = label_y + label_surf.get_height() + 2
            self.window.blit(hint_surf, (hx, hy))

        # Background
        if field.active:
            bg = _FIELD_BG_ACTIVE
        elif field.rect.collidepoint(pygame.mouse.get_pos()):
            bg = _FIELD_BG_HOVER
        else:
            bg = _FIELD_BG_PASSIVE
        surf = pygame.Surface((field.rect.w, field.rect.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, bg, surf.get_rect(), border_radius=self._field_corner_r)
        self.window.blit(surf, field.rect.topleft)

        # Border
        bdr = _FIELD_BDR_ACTIVE if field.active else _FIELD_BDR_PASSIVE
        pygame.draw.rect(self.window, bdr, field.rect,
                         _FIELD_BORDER_W, border_radius=self._field_corner_r)

        # Content text — clipped to the field; when the text is wider than
        # the field, keep its end (and the cursor) in view.
        visible = '*' * len(field.content) if field.pwd else field.content
        text_surf = self._field_font.render(visible, True, _FIELD_TEXT_CLR)
        ty = field.rect.y + (field.rect.h - text_surf.get_height()) // 2
        max_text_w = field.rect.w - 2 * self._field_pad_x
        text_offset = min(0, max_text_w - text_surf.get_width())
        tx = field.rect.x + self._field_pad_x + text_offset
        prev_clip = self.window.get_clip()
        self.window.set_clip(pygame.Rect(field.rect.x + self._field_pad_x, field.rect.y,
                                         max_text_w, field.rect.h))
        self.window.blit(text_surf, (tx, ty))

        # Cursor
        if field.active and pygame.time.get_ticks() % 1000 < 500:
            cursor_x = tx + self._field_font.size(visible[:field.cursor_pos])[0]
            cursor_y = field.rect.y + int(0.15 * field.rect.h)
            cursor_h = int(0.70 * field.rect.h)
            pygame.draw.line(self.window, _FIELD_CURSOR_CLR,
                             (cursor_x, cursor_y),
                             (cursor_x, cursor_y + cursor_h), 2)
        self.window.set_clip(prev_clip)

    _LEGAL_LINK_CLR = (120, 180, 250)

    def _draw_legal_confirmation(self):
        mouse = pygame.mouse.get_pos()
        font = self._legal_font
        label_surf = font.render("I'm 13+ and accept the", True, _FIELD_TEXT_CLR)
        terms_surf = font.render('Terms', True, self._LEGAL_LINK_CLR)
        amp_surf = font.render('  &  ', True, _FIELD_LABEL_CLR)
        privacy_surf = font.render('Privacy', True, self._LEGAL_LINK_CLR)
        gap = max(6, int(0.008 * _SW))
        one_line_w = (self._legal_box_rect.w + gap + label_surf.get_width()
                      + gap + terms_surf.get_width() + amp_surf.get_width()
                      + privacy_surf.get_width())
        one_line = one_line_w <= self._legal_rect.w

        if one_line:
            text_y = self._legal_rect.centery - label_surf.get_height() // 2
            self._legal_box_rect.centery = self._legal_rect.centery
        else:
            text_y = self._legal_rect.y
            self._legal_box_rect.y = self._legal_rect.y + 2

        # Checkbox — highlighted when hovered over the toggle area or checked.
        toggle_hover = self._legal_toggle_rect.collidepoint(mouse)
        bdr = _FIELD_BDR_ACTIVE if toggle_hover or self._legal_confirmed else _FIELD_BDR_PASSIVE
        pygame.draw.rect(self.window, bdr, self._legal_box_rect, 1,
                         border_radius=max(2, self._field_corner_r // 2))
        if self._legal_confirmed:
            x, y = self._legal_box_rect.x, self._legal_box_rect.y
            w, h = self._legal_box_rect.w, self._legal_box_rect.h
            pygame.draw.line(self.window, _FIELD_LABEL_CLR,
                             (x + int(0.22 * w), y + int(0.55 * h)),
                             (x + int(0.43 * w), y + int(0.76 * h)), 2)
            pygame.draw.line(self.window, _FIELD_LABEL_CLR,
                             (x + int(0.41 * w), y + int(0.76 * h)),
                             (x + int(0.80 * w), y + int(0.24 * h)), 2)

        x = self._legal_box_rect.right + int(0.008 * _SW)
        self.window.blit(label_surf, (x, text_y))
        label_rect = pygame.Rect(x, text_y, label_surf.get_width(),
                                 label_surf.get_height())
        lx = label_rect.right + (gap if one_line else 0)
        link_y = text_y if one_line else text_y + label_surf.get_height() + 2
        self.window.blit(terms_surf, (lx, link_y))
        self._terms_link_rect = pygame.Rect(lx, link_y, terms_surf.get_width(),
                                             terms_surf.get_height())
        lx += terms_surf.get_width()
        self.window.blit(amp_surf, (lx, link_y))
        amp_rect = pygame.Rect(lx, link_y, amp_surf.get_width(), amp_surf.get_height())
        lx += amp_surf.get_width()
        self.window.blit(privacy_surf, (lx, link_y))
        self._privacy_link_rect = pygame.Rect(lx, link_y, privacy_surf.get_width(),
                                               privacy_surf.get_height())

        # Each part of the legal row gets a generous, non-overlapping touch
        # region.  Links keep precedence over the acceptance toggle.
        self._legal_toggle_rect = pygame.Rect(
            self._legal_rect.x, self._legal_rect.y,
            label_rect.right - self._legal_rect.x, self._legal_rect.h)
        link_top = self._legal_rect.y if one_line else link_y
        link_h = self._legal_rect.bottom - link_top
        self._terms_link_hit_rect = pygame.Rect(
            self._terms_link_rect.x - gap // 2, link_top,
            self._terms_link_rect.w + gap // 2 + amp_rect.w // 2, link_h)
        self._privacy_link_hit_rect = pygame.Rect(
            amp_rect.centerx, link_top,
            self._privacy_link_rect.right + gap // 2 - amp_rect.centerx, link_h)

        # Underline the links so they read as tappable.
        for r, hit in ((self._terms_link_rect, self._terms_link_hit_rect),
                       (self._privacy_link_rect, self._privacy_link_hit_rect)):
            underline_clr = (self._LEGAL_LINK_CLR if hit.collidepoint(mouse)
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
        max_w = self._legal_doc_body_rect().w
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
        if _MOBILE_UI:
            w = int(0.90 * _SW)
            h = int(0.84 * _SH)
        else:
            w = int(0.74 * _SW)
            h = int(0.74 * _SH)
        return pygame.Rect((_SW - w) // 2, (_SH - h) // 2, w, h)

    def _legal_doc_close_size(self):
        if self._mobile_ui:
            return max(28, int(0.060 * _SH))
        return max(22, int(0.030 * _SH))

    def _legal_doc_body_rect(self):
        panel = self._legal_doc_panel_rect()
        pad_x = max(12, int(0.020 * _SW))
        pad_y = max(7, int(0.014 * _SH))
        header_h = max(self._label_font.get_height(), self._legal_doc_close_size())
        footer_h = self._legal_font.get_height() + pad_y * 2
        top = panel.y + pad_y + header_h + pad_y
        bottom = panel.bottom - footer_h
        scrollbar_w = max(6, int(0.008 * _SW))
        return pygame.Rect(panel.x + pad_x, top,
                           panel.w - pad_x * 2 - scrollbar_w,
                           max(1, bottom - top))

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
        pad_x = max(12, int(0.020 * _SW))
        pad_y = max(7, int(0.014 * _SH))
        title_surf = self._label_font.render(self._legal_doc['title'], True,
                                              settings.GAME_MENU_TITLE_CLR)
        close_sz = self._legal_doc_close_size()
        self._legal_doc_close_rect = pygame.Rect(
            panel.right - close_sz - pad_x,
            panel.y + pad_y, close_sz, close_sz)
        cr = self._legal_doc_close_rect
        title_y = cr.centery - title_surf.get_height() // 2
        self.window.blit(title_surf, (panel.x + pad_x, title_y))
        ch = self._touch_hit(cr, pygame.mouse.get_pos())
        pygame.draw.rect(self.window, (90, 60, 40) if ch else (60, 45, 30), cr,
                         border_radius=5)
        cross_pad = max(6, close_sz // 4)
        pygame.draw.line(self.window, (230, 210, 180),
                         (cr.x + cross_pad, cr.y + cross_pad),
                         (cr.right - cross_pad, cr.bottom - cross_pad), 2)
        pygame.draw.line(self.window, (230, 210, 180),
                         (cr.x + cross_pad, cr.bottom - cross_pad),
                         (cr.right - cross_pad, cr.y + cross_pad), 2)

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

        # Scrollbar gives touch users a visible position cue.
        max_scroll = self._legal_doc.get('max_scroll', 0)
        if max_scroll > 0:
            track = pygame.Rect(body.right + max(3, int(0.004 * _SW)),
                                body.y, max(3, int(0.004 * _SW)), body.h)
            pygame.draw.rect(self.window, (55, 50, 42), track,
                             border_radius=max(1, track.w // 2))
            content_h = body.h + max_scroll
            thumb_h = max(20, int(body.h * body.h / max(1, content_h)))
            travel = max(0, body.h - thumb_h)
            thumb_y = body.y + int(travel * self._legal_doc['scroll'] / max_scroll)
            thumb = pygame.Rect(track.x, thumb_y, track.w, thumb_h)
            pygame.draw.rect(self.window, (170, 145, 105), thumb,
                             border_radius=max(1, thumb.w // 2))

        hint_text = ('Swipe to read · tap X or outside to close'
                     if self._mobile_ui else
                     'Scroll to read · click X or outside to close')
        hint = self._legal_font.render(hint_text,
                                       True, _FIELD_LABEL_CLR)
        self.window.blit(hint, (panel.x + pad_x,
                                panel.bottom - pad_y - hint.get_height()))

    def _touch_hit(self, rect, pos):
        """Hit-test a visual rect with a mobile-sized invisible target."""
        if not self._mobile_ui:
            return rect.collidepoint(pos)
        target = settings.TOUCH_TARGET_MIN
        hit = rect.inflate(max(0, target - rect.w), max(0, target - rect.h))
        return hit.collidepoint(pos)

    def _handle_legal_doc_events(self, events):
        """Process events while the doc overlay is open. Returns True if open."""
        if not self._legal_doc:
            return False
        panel = self._legal_doc_panel_rect()
        body = self._legal_doc_body_rect()
        for event in events:
            if event.type == MOUSEWHEEL:
                self._legal_doc['scroll'] = max(
                    0, min(self._legal_doc.get('max_scroll', 0),
                           self._legal_doc['scroll'] - event.y * int(0.05 * _SH)))
            elif event.type == KEYDOWN:
                if event.key == K_ESCAPE:
                    self._legal_doc = None
                    return True
                step = 0
                if event.key in (K_UP, K_PAGEUP):
                    step = -body.h if event.key == K_PAGEUP else -int(0.05 * _SH)
                elif event.key in (K_DOWN, K_PAGEDOWN):
                    step = body.h if event.key == K_PAGEDOWN else int(0.05 * _SH)
                if step:
                    self._legal_doc['scroll'] = max(
                        0, min(self._legal_doc.get('max_scroll', 0),
                               self._legal_doc['scroll'] + step))
            elif event.type == MOUSEBUTTONDOWN and event.button == 1:
                if body.collidepoint(event.pos):
                    self._legal_doc_drag = (event.pos[1], self._legal_doc['scroll'])
                    self._legal_doc_dragged = False
            elif event.type == MOUSEMOTION and self._legal_doc_drag is not None:
                start_y, start_scroll = self._legal_doc_drag
                delta = start_y - event.pos[1]
                if abs(delta) >= max(3, int(0.006 * _SH)):
                    self._legal_doc_dragged = True
                self._legal_doc['scroll'] = max(
                    0, min(self._legal_doc.get('max_scroll', 0),
                           start_scroll + delta))
            elif event.type == MOUSEBUTTONUP and event.button == 1:
                was_dragged = self._legal_doc_dragged
                self._legal_doc_drag = None
                self._legal_doc_dragged = False
                if was_dragged:
                    continue
                if (self._touch_hit(self._legal_doc_close_rect, event.pos)
                        or not panel.collidepoint(event.pos)):
                    self._legal_doc = None
                    return True
        return True

    # ── Render ──────────────────────────────────────────────────────

    def draw_msg(self):
        """Draw readable, wrapped auth feedback in a bottom toast."""
        if not self.state.message_lines:
            return
        max_text_w = int(0.78 * _SW)
        lines = []
        for line, _ in self.state.message_lines:
            lines.extend(self._wrap_message_line(str(line), max_text_w))
        if not lines:
            return

        line_h = self._msg_font.get_height()
        spacing = max(2, int(0.004 * _SH))
        pad_x = max(10, int(0.012 * _SW))
        pad_y = max(5, int(0.008 * _SH))
        text_w = min(max_text_w, max(self._msg_font.size(line)[0] for line in lines))
        toast = pygame.Rect(0, 0,
                            text_w + pad_x * 2,
                            len(lines) * line_h + (len(lines) - 1) * spacing + pad_y * 2)
        toast.centerx = _SW // 2
        toast.bottom = _SH - max(5, int(0.012 * _SH))
        surface = pygame.Surface(toast.size, pygame.SRCALPHA)
        pygame.draw.rect(surface, (22, 20, 18, 225), surface.get_rect(),
                         border_radius=max(5, int(0.007 * _SH)))
        self.window.blit(surface, toast.topleft)
        pygame.draw.rect(self.window, (150, 125, 88), toast, 1,
                         border_radius=max(5, int(0.007 * _SH)))
        y = toast.y + pad_y
        for line in lines:
            surf = self._msg_font.render(line, True, settings.MSG_TEXT_COLOR)
            self.window.blit(surf, surf.get_rect(centerx=toast.centerx, y=y))
            y += line_h + spacing

    def _wrap_message_line(self, line, max_w):
        if not line:
            return ['']
        words = line.split()
        wrapped, current = [], ''
        for word in words:
            candidate = f'{current} {word}'.strip()
            if not current or self._msg_font.size(candidate)[0] <= max_w:
                current = candidate
            else:
                wrapped.append(current)
                current = word
        if current:
            wrapped.append(current)
        return wrapped

    def render(self):
        # Background
        self.window.blit(self._bg, (0, 0))

        # Dark box
        self.window.blit(self._box_surf, self._box_rect.topleft)

        # Title
        tx = self._box_rect.centerx - self._title_surf.get_width() // 2
        ty = self._box_rect.y + self._panel_pad_y
        self.window.blit(self._title_surf, (tx, ty))

        # Input fields (hints show the server rules before submitting)
        username_ok, pwd_ok = self._field_validity()
        self._draw_field(self.field_username, self._username_label_y,
                         hint=USERNAME_HINT, hint_state=username_ok)
        self._draw_field(self.field_pwd, self._pwd_label_y,
                         hint=PASSWORD_HINT, hint_state=pwd_ok)
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

    def _field_validity(self):
        """Return (username_ok, pwd_ok); None while a field is still empty."""
        username = self.field_username.content
        pwd = self.field_pwd.content
        username_ok = None
        if username:
            username_ok = (MIN_USERNAME_LENGTH <= len(username) <= MAX_USERNAME_LENGTH
                           and bool(_USERNAME_RE.match(username)))
        pwd_ok = len(pwd) >= MIN_PASSWORD_LENGTH if pwd else None
        return username_ok, pwd_ok

    def _register_validation_error(self):
        """Client-side mirror of the server rules; returns a message or None."""
        username = self.field_username.content
        if len(username) < MIN_USERNAME_LENGTH or len(username) > MAX_USERNAME_LENGTH:
            return f'Username must be {MIN_USERNAME_LENGTH}-{MAX_USERNAME_LENGTH} characters.'
        if not _USERNAME_RE.match(username):
            return 'Username may only use letters, numbers, _ and -.'
        if len(self.field_pwd.content) < MIN_PASSWORD_LENGTH:
            return f'Password must be at least {MIN_PASSWORD_LENGTH} characters.'
        return None

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
        validation_error = self._register_validation_error()
        if validation_error:
            self.state.set_msg(validation_error)
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
            self._clear_mobile_web_inputs()
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
            # Keep the username so a typo or network hiccup only costs
            # retyping the password.
            self.field_pwd.empty()

    def _apply_register_response(self, response_data):
        self.state.set_msg(response_data.get('message', ''))
        if response_data.get('success'):
            self._clear_mobile_web_inputs()
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
        # On failure keep both fields: the user only needs to adjust the
        # rejected value (e.g. pick another username), not start over.

    # ── Events ──────────────────────────────────────────────────────

    def _register_mobile_web_inputs(self):
        """Align native mobile inputs with the two visible canvas fields."""
        if not (_IS_WEB and self._mobile_ui):
            return
        from utils.web_keyboard import clear_inputs, register_input
        clear_inputs()
        for field in (self.field_username, self.field_pwd):
            register_input(
                field.name,
                field.content,
                field.pwd,
                field.max_length,
                field.rect,
            )

    def _set_mobile_web_inputs_enabled(self, value):
        if not (_IS_WEB and self._mobile_ui):
            return
        value = bool(value)
        if self._web_inputs_enabled == value:
            return
        from utils.web_keyboard import set_inputs_enabled
        set_inputs_enabled(value)
        self._web_inputs_enabled = value

    def _clear_mobile_web_inputs(self):
        if not (_IS_WEB and self._mobile_ui):
            return
        from utils.web_keyboard import clear_inputs
        clear_inputs()
        self._web_inputs_enabled = None

    def handle_events(self, events):
        if super().handle_events(events):
            events = ()

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
                # The legal checkbox is only relevant for registration, so a
                # ticked box signals the user is registering, not logging in.
                if self._legal_confirmed:
                    self.handle_register()
                else:
                    self.handle_login()

            elif event.type == MOUSEBUTTONUP:
                if self._terms_link_hit_rect.collidepoint(event.pos):
                    self._open_legal_doc('terms', 'Terms of Use')
                elif self._privacy_link_hit_rect.collidepoint(event.pos):
                    self._open_legal_doc('privacy', 'Privacy Policy')
                elif self._legal_toggle_rect.collidepoint(event.pos):
                    self._legal_confirmed = not self._legal_confirmed
                elif self.button_login.collide():
                    self.handle_login()
                elif self.button_register.collide():
                    self.handle_register()

    def update(self, events):
        super().update()
        # Native HTML inputs sit directly over the visible canvas fields. They
        # open the keyboard from the tap itself while the game and music run.
        self._set_mobile_web_inputs_enabled(
            self._legal_doc is None and not self.loading)
        self.field_username.sync_web_input()
        self.field_pwd.sync_web_input()
        self.button_register.disabled = not self._legal_confirmed
        self.button_login.update()
        self.button_register.update()
        if _IS_WEB:
            self._poll_pending_auth()
