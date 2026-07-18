# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""
Settings screen – resolution picker and future settings.

Accessible via the gear icon on any menu screen.
"""

import json
import os
import pygame
from pygame.locals import *
from game.screens.screen import Screen
from game.screens._menu_base import (
    MenuScreenMixin,
    menu_chrome_safe_top,
    menu_chrome_safe_width,
)
from config import settings

_SW, _SH = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT

# ── Overall box ─────────────────────────────────────────────────────
_BOX_PAD     = int(0.025 * _SH)
_BOX_X       = int(0.20 * _SW)
_BOX_Y       = menu_chrome_safe_top(int(0.10 * _SH))
_BOX_W       = menu_chrome_safe_width(_BOX_X, int(0.60 * _SW))
_BOX_BOTTOM  = int(0.88 * _SH)
_BOX_H       = _BOX_BOTTOM - _BOX_Y

# ── Title inside box ───────────────────────────────────────────────
_TITLE_Y     = _BOX_Y + _BOX_PAD

# ── Resolution button layout ───────────────────────────────────────
_RES_START_Y = _TITLE_Y + int(0.07 * _SH)
_RES_BTN_W   = int(0.38 * _SW)
_RES_BTN_H   = int(0.042 * _SH)
_RES_BTN_GAP = int(0.006 * _SH)

# ── Colours ─────────────────────────────────────────────────────────
_SECTION_CLR = (220, 200, 140)          # section label
_HINT_CLR    = (150, 140, 125)          # hint text
_ACTIVE_CLR  = (90, 200, 110)           # "current" / "native" tag
_RESTART_CLR = (250, 180, 60)           # restart-needed banner
_RESTART_BG  = (60, 45, 20, 200)

# Available resolutions — 16∶9 aspect ratio
_RESOLUTIONS = [
    ( 854,  480,  '854 × 480    (FWVGA)'),
    (1024,  576, '1024 × 576    (PAL wide)'),
    (1280,  720, '1280 × 720    (HD)'),
    (1366,  768, '1366 × 768    (Laptop)'),
    (1600,  900, '1600 × 900    (HD+)'),
    (1920, 1080, '1920 × 1080  (Full HD)'),
    (2048, 1152, '2048 × 1152  (QWXGA)'),
    (2560, 1440, '2560 × 1440  (QHD)'),
    (3200, 1800, '3200 × 1800  (QHD+)'),
    (3840, 2160, '3840 × 2160  (4K UHD)'),
]

# ── Config path (matches main.py) ──────────────────────────────────
_CFG_DIR  = os.path.join(os.path.expanduser('~'), '.nepalkings')
_CFG_FILE = os.path.join(_CFG_DIR, 'resolution.json')


def _draw_panel(window, rect, corner_r=None):
    r = corner_r or settings.SUB_SCREEN_PANEL_CORNER_R
    surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    pygame.draw.rect(surf, settings.SUB_SCREEN_PANEL_BG_CLR, surf.get_rect(), border_radius=r)
    window.blit(surf, rect.topleft)
    pygame.draw.rect(window, settings.SUB_SCREEN_PANEL_BORDER_CLR, rect,
                     settings.SUB_SCREEN_PANEL_BORDER_W, border_radius=r)


class SettingsScreen(MenuScreenMixin, Screen):
    def __init__(self, state):
        super().__init__(state)
        self.control_buttons = []
        self._init_menu_chrome()

        # ── Fonts ───────────────────────────────────────────────────
        self._title_font = settings.get_font(settings.SUB_SCREEN_TITLE_FONT_SIZE, bold=True)
        self._title_surf = self._title_font.render('Settings', True,
                                                   settings.SUB_SCREEN_TITLE_CLR)

        self._section_font = settings.get_font(settings.mobile_font_size(
            int(0.026 * _SH), settings.FS_HEADING), bold=True)
        self._btn_font = settings.get_font(settings.mobile_font_size(
            int(0.022 * _SH), settings.FS_BODY))
        self._hint_font = settings.get_font(settings.mobile_font_size(
            int(0.018 * _SH), settings.FS_SMALL))
        self._banner_font = settings.get_font(settings.mobile_font_size(
            int(0.020 * _SH), settings.FS_SMALL))

        # ── Resolution state ────────────────────────────────────────
        self._current_w = settings.SCREEN_WIDTH
        self._current_h = settings.SCREEN_HEIGHT
        self._selected_w = self._current_w
        self._selected_h = self._current_h
        self._restart_pending = False      # True once user picks a different res

        # Use native desktop size captured before window creation
        self._native_w = self.state.native_screen_w or settings.SCREEN_WIDTH
        self._native_h = self.state.native_screen_h or settings.SCREEN_HEIGHT

        # Filter resolutions that fit
        self._choices = [(w, h, lbl) for w, h, lbl in _RESOLUTIONS
                         if w <= self._native_w and h <= self._native_h]
        if not self._choices:
            self._choices = [(self._current_w, self._current_h,
                              f'{self._current_w} × {self._current_h}')]

        # Pre-select current resolution
        self._selected_idx = 0
        for i, (w, h, _) in enumerate(self._choices):
            if w == self._current_w and h == self._current_h:
                self._selected_idx = i
                break

        # ── Layout ──────────────────────────────────────────────────
        self._hovered_idx  = -1
        self._restart_btn_rect = None

        # ── Toggle rows (notifications etc.) ────────────────────────
        self._toggle_rects = {}

    # ── Rendering ───────────────────────────────────────────────────

    def render(self):
        self._draw_menu_chrome()

        box_rect = pygame.Rect(_BOX_X, _BOX_Y, _BOX_W, _BOX_H)
        _draw_panel(self.window, box_rect)

        # Title
        tx = _BOX_X + (_BOX_W - self._title_surf.get_width()) // 2
        self.window.blit(self._title_surf, (tx, _TITLE_Y))

        # Section label
        section_y = _RES_START_Y - int(0.035 * _SH)
        sec_surf = self._section_font.render('Resolution', True, _SECTION_CLR)
        self.window.blit(sec_surf, (_BOX_X + int(0.04 * _SW), section_y))

        # Resolution buttons
        btn_x = _BOX_X + (_BOX_W - _RES_BTN_W) // 2
        mx, my = pygame.mouse.get_pos()

        for i, (w, h, label) in enumerate(self._choices):
            y = _RES_START_Y + i * (_RES_BTN_H + _RES_BTN_GAP)
            r = pygame.Rect(btn_x, y, _RES_BTN_W, _RES_BTN_H)

            is_sel = (i == self._selected_idx)
            is_hover = r.collidepoint(mx, my)
            is_current = (w == self._current_w and h == self._current_h)

            # Choose colours
            if is_sel:
                bg  = settings.LIST_BTN_BG_CLICK_CLR
                bdr = (250, 221, 0)
                txt_clr = settings.LIST_BTN_TEXT_HOVER_CLR
            elif is_hover:
                bg  = settings.LIST_BTN_BG_HOVER_CLR
                bdr = settings.LIST_BTN_BORDER_HOVER_CLR
                txt_clr = settings.LIST_BTN_TEXT_HOVER_CLR
            else:
                bg  = settings.LIST_BTN_BG_CLR
                bdr = settings.LIST_BTN_BORDER_CLR
                txt_clr = settings.LIST_BTN_TEXT_CLR

            cr = settings.LIST_BTN_CORNER_RADIUS
            surf = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
            pygame.draw.rect(surf, bg, surf.get_rect(), border_radius=cr)
            self.window.blit(surf, r.topleft)
            pygame.draw.rect(self.window, bdr, r, settings.LIST_BTN_BORDER_W, border_radius=cr)

            # Label text
            txt = self._btn_font.render(label, True, txt_clr)
            self.window.blit(txt, (r.x + int(0.015 * _SW),
                                   r.y + (r.h - txt.get_height()) // 2))

            # Tags (right side)
            tag_x = r.right - int(0.015 * _SW)
            if is_current:
                tag = self._hint_font.render('current', True, _ACTIVE_CLR)
                self.window.blit(tag, (tag_x - tag.get_width(),
                                       r.y + (r.h - tag.get_height()) // 2))
            elif w == self._native_w and h == self._native_h:
                tag = self._hint_font.render('native', True, _ACTIVE_CLR)
                self.window.blit(tag, (tag_x - tag.get_width(),
                                       r.y + (r.h - tag.get_height()) // 2))
            elif is_sel:
                dot = self._btn_font.render('●', True, (250, 221, 0))
                self.window.blit(dot, (tag_x - dot.get_width(),
                                       r.y + (r.h - dot.get_height()) // 2))

        # ── Toggle rows ─────────────────────────────────────────────
        toggles_y = (_RES_START_Y + len(self._choices) * (_RES_BTN_H + _RES_BTN_GAP)
                     + int(0.025 * _SH))
        toggles_y = self._draw_toggle_rows(toggles_y, mx, my)

        # ── Restart banner + button ─────────────────────────────────
        if self._restart_pending:
            after_y = toggles_y + int(0.015 * _SH)

            # Banner text
            banner_text = (f'Resolution changed to '
                           f'{self._selected_w} × {self._selected_h}.')
            banner_surf = self._banner_font.render(banner_text, True, _RESTART_CLR)
            bw = banner_surf.get_width() + int(0.03 * _SW)
            bh = banner_surf.get_height() + int(0.016 * _SH)
            bx = _BOX_X + (_BOX_W - bw) // 2
            bg_surf = pygame.Surface((bw, bh), pygame.SRCALPHA)
            bg_surf.fill(_RESTART_BG)
            pygame.draw.rect(bg_surf, (180, 140, 60), bg_surf.get_rect(), 1, border_radius=6)
            self.window.blit(bg_surf, (bx, after_y))
            self.window.blit(banner_surf,
                             (bx + (bw - banner_surf.get_width()) // 2,
                              after_y + (bh - banner_surf.get_height()) // 2))

            # "Restart Now" button
            rbtn_w = int(0.14 * _SW)
            rbtn_h = int(0.042 * _SH)
            rbtn_y = after_y + bh + int(0.012 * _SH)
            self._restart_btn_rect = pygame.Rect(
                _BOX_X + (_BOX_W - rbtn_w) // 2, rbtn_y, rbtn_w, rbtn_h)
            rr = self._restart_btn_rect
            r_hover = rr.collidepoint(mx, my)
            r_bg  = (100, 80, 40) if r_hover else (60, 50, 30)
            r_bdr = (250, 221, 0) if r_hover else (180, 160, 130)
            pygame.draw.rect(self.window, r_bg, rr, border_radius=8)
            pygame.draw.rect(self.window, r_bdr, rr, 2, border_radius=8)
            rtxt = self._btn_font.render('Restart Now', True, (250, 221, 0))
            self.window.blit(rtxt, (rr.x + (rr.w - rtxt.get_width()) // 2,
                                    rr.y + (rr.h - rtxt.get_height()) // 2))
        else:
            self._restart_btn_rect = None

        # ── Hint ────────────────────────────────────────────────────
        hint = self._hint_font.render('Click a resolution, then restart the game to apply.',
                                      True, _HINT_CLR)
        self.window.blit(hint,
                         (_BOX_X + (_BOX_W - hint.get_width()) // 2,
                          _BOX_Y + _BOX_H - int(0.04 * _SH)))

        self._draw_menu_overlay()

    # ── Toggle rows ─────────────────────────────────────────────────

    def _toggle_specs(self):
        """Return the list of toggle rows to draw: (key, label, value, enabled, hint)."""
        from utils import music, sound
        ud = getattr(self.state, 'user_dict', None) or {}
        has_email = bool(ud.get('has_email'))
        notify_on = bool(ud.get('notify_emails_enabled', True))
        if not ud:
            email_hint = 'Log in to manage notification emails.'
        elif not has_email:
            email_hint = 'Add an email at registration to get turn notifications.'
        else:
            email_hint = "Emailed when it's your turn and you are offline."
        return [
            ('sound', 'Sound effects', sound.is_enabled(), True,
             'Card, battle, and interface sounds.'),
            ('music', 'Background music', music.is_enabled(), True,
             'Low-volume themes for menus, kingdoms, and battles.'),
            ('notify_emails', 'Email notifications', notify_on,
             bool(ud) and has_email, email_hint),
        ]

    def _draw_toggle_rows(self, y, mx, my):
        """Draw all toggle rows starting at y; returns the y below them."""
        self._toggle_rects = {}
        compact = len(self._choices) >= 9
        sec_surf = self._section_font.render('Preferences', True, _SECTION_CLR)
        self.window.blit(sec_surf, (_BOX_X + int(0.04 * _SW), y))
        y += sec_surf.get_height() + int(0.008 * _SH)

        row_x = _BOX_X + (_BOX_W - _RES_BTN_W) // 2
        pill_w = int(0.055 * _SW)
        for key, label, value, enabled, hint in self._toggle_specs():
            row_h = int(0.030 * _SH) if compact else _RES_BTN_H
            row = pygame.Rect(row_x, y, _RES_BTN_W, row_h)
            hover = enabled and row.collidepoint(mx, my)
            bg = settings.LIST_BTN_BG_HOVER_CLR if hover else settings.LIST_BTN_BG_CLR
            bdr = (settings.LIST_BTN_BORDER_HOVER_CLR if hover
                   else settings.LIST_BTN_BORDER_CLR)
            cr = settings.LIST_BTN_CORNER_RADIUS
            surf = pygame.Surface((row.w, row.h), pygame.SRCALPHA)
            pygame.draw.rect(surf, bg, surf.get_rect(), border_radius=cr)
            self.window.blit(surf, row.topleft)
            pygame.draw.rect(self.window, bdr, row, settings.LIST_BTN_BORDER_W,
                             border_radius=cr)

            txt_clr = (settings.LIST_BTN_TEXT_CLR if enabled else _HINT_CLR)
            txt = self._btn_font.render(label, True, txt_clr)
            self.window.blit(txt, (row.x + int(0.015 * _SW),
                                   row.y + (row.h - txt.get_height()) // 2))

            # On/Off pill on the right
            pill = pygame.Rect(row.right - pill_w - int(0.012 * _SW),
                               row.y + int(0.15 * row.h),
                               pill_w, int(0.7 * row.h))
            if not enabled:
                pill_bg, pill_txt, pill_label = (60, 55, 45), _HINT_CLR, '—'
            elif value:
                pill_bg, pill_txt, pill_label = (40, 90, 50), _ACTIVE_CLR, 'On'
            else:
                pill_bg, pill_txt, pill_label = (80, 50, 40), (220, 150, 130), 'Off'
            pygame.draw.rect(self.window, pill_bg, pill, border_radius=10)
            ptxt = self._hint_font.render(pill_label, True, pill_txt)
            self.window.blit(ptxt, (pill.x + (pill.w - ptxt.get_width()) // 2,
                                    pill.y + (pill.h - ptxt.get_height()) // 2))
            if enabled:
                self._toggle_rects[key] = row
            y += row.h + int((0.002 if compact else 0.004) * _SH)

            if not compact:
                hint_surf = self._hint_font.render(hint, True, _HINT_CLR)
                self.window.blit(hint_surf, (row.x + int(0.015 * _SW), y))
                y += hint_surf.get_height() + int(0.008 * _SH)
        return y

    def _handle_toggle_click(self, pos):
        for key, rect in self._toggle_rects.items():
            if not rect.collidepoint(pos):
                continue
            if key == 'sound':
                from utils import sound
                sound.set_enabled(not sound.is_enabled())
                if sound.is_enabled():
                    sound.play('ui_click')
            elif key == 'music':
                from utils import music
                music.set_enabled(not music.is_enabled())
            elif key == 'notify_emails':
                ud = self.state.user_dict or {}
                new_value = not bool(ud.get('notify_emails_enabled', True))
                from utils import auth_service
                result = auth_service.set_notifications(new_value)
                if result is None:
                    self.state.set_msg('Could not update notification settings')
                else:
                    ud['notify_emails_enabled'] = result
                    self.state.set_msg(
                        'Email notifications ' + ('enabled' if result else 'disabled'))
            return True
        return False

    # ── Update / Events ─────────────────────────────────────────────

    def update(self, events):
        super().update()
        self._update_icon_buttons()

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
            if event.type == MOUSEBUTTONUP and event.button == 1:
                # Toggle rows (notifications etc.)
                if self._handle_toggle_click(event.pos):
                    continue
                # "Restart Now" button
                if (self._restart_pending
                        and self._restart_btn_rect
                        and self._restart_btn_rect.collidepoint(event.pos)):
                    self.state.screen = 'restart'
                    return
                # Check resolution buttons
                btn_x = _BOX_X + (_BOX_W - _RES_BTN_W) // 2
                for i, (w, h, _) in enumerate(self._choices):
                    y = _RES_START_Y + i * (_RES_BTN_H + _RES_BTN_GAP)
                    r = pygame.Rect(btn_x, y, _RES_BTN_W, _RES_BTN_H)
                    if r.collidepoint(event.pos):
                        self._selected_idx = i
                        self._selected_w = w
                        self._selected_h = h
                        if w != self._current_w or h != self._current_h:
                            self._restart_pending = True
                            self._save_resolution(w, h)
                            self.state.set_msg(
                                f'Resolution set to {w}×{h}. Restart to apply.')
                        else:
                            self._restart_pending = False
                        break

    # ── Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _save_resolution(w, h):
        """Write the chosen resolution to the user config directory, preserving other settings."""
        import sys
        if sys.platform == 'emscripten':
            return  # no persistent filesystem on web
        try:
            os.makedirs(_CFG_DIR, exist_ok=True)
            existing = {}
            if os.path.exists(_CFG_FILE):
                with open(_CFG_FILE, 'r') as f:
                    existing = json.load(f)
            existing['width'] = w
            existing['height'] = h
            with open(_CFG_FILE, 'w') as f:
                json.dump(existing, f, indent=2)
        except Exception:
            pass
