# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Unified settings screen.

Resolution, preferences, account lifecycle, and player-safety controls are
peer tabs. Account controls deliberately live here instead of behind a second
screen/modal hierarchy.
"""

import json
import os
import sys

import pygame
from pygame.locals import KEYDOWN, K_RETURN, K_TAB, MOUSEBUTTONUP

from config import settings
from game.components.inputs.input_field import InputField
from game.screens._menu_base import (
    ListButton,
    MenuScreenMixin,
    menu_chrome_safe_top,
    menu_chrome_safe_width,
)
from game.screens.screen import Screen
from utils import account_service
from utils import http_compat as _http


_IS_WEB = sys.platform == 'emscripten'
_SW, _SH = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT

_BOX_X = int(0.17 * _SW)
_BOX_Y = menu_chrome_safe_top(int(0.10 * _SH))
_BOX_W = menu_chrome_safe_width(_BOX_X, int(0.66 * _SW))
_BOX_BOTTOM = int(0.89 * _SH)
_BOX_H = _BOX_BOTTOM - _BOX_Y
_BOX_PAD = int(0.025 * _SH)
_TITLE_Y = _BOX_Y + _BOX_PAD

_CONTENT_W = min(int(0.44 * _SW), _BOX_W - int(0.08 * _SW))
_CONTENT_X = _BOX_X + (_BOX_W - _CONTENT_W) // 2

_SECTION_CLR = (220, 200, 140)
_HINT_CLR = (150, 140, 125)
_ACTIVE_CLR = (90, 200, 110)
_RESTART_CLR = (250, 180, 60)
_RESTART_BG = (60, 45, 20, 200)
_DANGER = (225, 125, 105)

_TABS = (
    ('resolution', 'Resolution'),
    ('preferences', 'Preferences'),
    ('account', 'Account'),
    ('safety', 'Safety'),
)

_RESOLUTIONS = [
    (854, 480, '854 × 480    (FWVGA)'),
    (1024, 576, '1024 × 576    (PAL wide)'),
    (1280, 720, '1280 × 720    (HD)'),
    (1366, 768, '1366 × 768    (Laptop)'),
    (1600, 900, '1600 × 900    (HD+)'),
    (1920, 1080, '1920 × 1080  (Full HD)'),
    (2048, 1152, '2048 × 1152  (QWXGA)'),
    (2560, 1440, '2560 × 1440  (QHD)'),
    (3200, 1800, '3200 × 1800  (QHD+)'),
    (3840, 2160, '3840 × 2160  (4K UHD)'),
]

_REASONS = (
    ('harassment', 'Harassment'),
    ('hate', 'Hate'),
    ('spam', 'Spam'),
    ('sexual_content', 'Sexual content'),
    ('threats', 'Threats'),
    ('cheating', 'Cheating'),
    ('inappropriate_name', 'Bad name'),
    ('other', 'Other'),
)

_CFG_DIR = os.path.join(os.path.expanduser('~'), '.nepalkings')
_CFG_FILE = os.path.join(_CFG_DIR, 'resolution.json')


def _draw_panel(window, rect):
    surface = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    pygame.draw.rect(
        surface,
        settings.SUB_SCREEN_PANEL_BG_CLR,
        surface.get_rect(),
        border_radius=settings.SUB_SCREEN_PANEL_CORNER_R,
    )
    window.blit(surface, rect.topleft)
    pygame.draw.rect(
        window,
        settings.SUB_SCREEN_PANEL_BORDER_CLR,
        rect,
        settings.SUB_SCREEN_PANEL_BORDER_W,
        border_radius=settings.SUB_SCREEN_PANEL_CORNER_R,
    )


class SettingsScreen(MenuScreenMixin, Screen):
    """One settings destination with four equally ranked sections."""

    def __init__(self, state):
        super().__init__(state)
        self.control_buttons = []
        self._init_menu_chrome()

        self._tab = 'resolution'
        self._tab_rects = {}
        self._reason_index = 0
        self._pending_rid = None
        self._pending_action = None
        self._busy = False

        self._title_font = settings.get_font(
            settings.SUB_SCREEN_TITLE_FONT_SIZE, bold=True)
        self._title_surf = self._title_font.render(
            'Settings', True, settings.SUB_SCREEN_TITLE_CLR)
        self._section_font = settings.get_font(
            max(14, settings.mobile_font_size(
                int(0.026 * _SH), settings.FS_HEADING)),
            bold=True,
        )
        self._btn_font = settings.get_font(
            max(12, settings.mobile_font_size(
                int(0.022 * _SH), settings.FS_BODY)))
        self._hint_font = settings.get_font(
            max(11, settings.mobile_font_size(
                int(0.018 * _SH), settings.FS_SMALL)))
        self._banner_font = settings.get_font(
            max(11, settings.mobile_font_size(
                int(0.020 * _SH), settings.FS_SMALL)))

        tab_h = max(
            int(0.046 * _SH),
            int(getattr(settings, 'TOUCH_COMPACT_MIN', 0) or 0),
        )
        self._tabs_y = _TITLE_Y + int(0.065 * _SH)
        self._content_y = self._tabs_y + tab_h + int(0.035 * _SH)
        self._content_bottom = _BOX_BOTTOM - int(0.035 * _SH)
        self._content_h = self._content_bottom - self._content_y

        self._init_resolution_state()
        self._toggle_rects = {}
        self._restart_btn_rect = None
        self._resolution_rects = []

        field_h = max(
            int(0.045 * _SH),
            int(getattr(settings, 'TOUCH_COMPACT_MIN', 0) or 0),
        )
        # InputField draws its label above the field rectangle. Leave a real
        # gap below the section description so those two text rows never
        # collide on the 854×480 canvas.
        first_y = self._content_y + int(0.27 * self._content_h)
        second_y = first_y + field_h + int(0.10 * self._content_h)
        self.current_password = InputField(
            self.window,
            _CONTENT_X,
            first_y,
            'Current password',
            pwd=True,
            max_length=64,
            width=_CONTENT_W,
            height=field_h,
            web_overlay=True,
        )
        self.new_password = InputField(
            self.window,
            _CONTENT_X,
            second_y,
            'New password (8+ characters)',
            pwd=True,
            max_length=64,
            width=_CONTENT_W,
            height=field_h,
            web_overlay=True,
        )
        self.player_username = InputField(
            self.window,
            _CONTENT_X,
            first_y,
            'Player username',
            max_length=30,
            width=_CONTENT_W,
            height=field_h,
            web_overlay=True,
        )
        self.report_details = InputField(
            self.window,
            _CONTENT_X,
            second_y,
            'Short report details (optional)',
            max_length=240,
            width=_CONTENT_W,
            height=field_h,
            web_overlay=True,
        )
        self._buttons = {}
        self._build_account_buttons()

    def _init_resolution_state(self):
        self._current_w = settings.SCREEN_WIDTH
        self._current_h = settings.SCREEN_HEIGHT
        self._selected_w = self._current_w
        self._selected_h = self._current_h
        self._restart_pending = False
        self._native_w = self.state.native_screen_w or settings.SCREEN_WIDTH
        self._native_h = self.state.native_screen_h or settings.SCREEN_HEIGHT
        self._choices = [
            (width, height, label)
            for width, height, label in _RESOLUTIONS
            if width <= self._native_w and height <= self._native_h
        ]
        if not self._choices:
            self._choices = [(
                self._current_w,
                self._current_h,
                f'{self._current_w} × {self._current_h}',
            )]
        self._selected_idx = 0
        for index, (width, height, _label) in enumerate(self._choices):
            if width == self._current_w and height == self._current_h:
                self._selected_idx = index
                break

    def _build_account_buttons(self):
        button_h = max(
            int(0.050 * _SH),
            int(getattr(settings, 'TOUCH_COMPACT_MIN', 0) or 0),
        )
        gap = int(0.016 * _SW)
        button_w = min(int(0.205 * _SW), (_BOX_W - gap) // 2)
        left = _BOX_X + (_BOX_W - (2 * button_w + gap)) // 2
        right = left + button_w + gap
        row1 = self._content_y + int(0.68 * self._content_h)
        row2 = row1 + button_h + int(0.045 * self._content_h)
        self._buttons = {
            'change_password': ListButton(
                self.window, left, row1, 'Change password',
                width=button_w, height=button_h),
            'logout_all': ListButton(
                self.window, right, row1, 'Log out all devices',
                width=button_w, height=button_h),
            'export': ListButton(
                self.window, left, row2, 'Export my data',
                width=button_w, height=button_h),
            'delete': ListButton(
                self.window, right, row2, 'Delete account',
                width=button_w, height=button_h),
            'reason': ListButton(
                self.window, left, row1, 'Reason: Harassment',
                width=button_w, height=button_h),
            'report': ListButton(
                self.window, right, row1, 'Report player',
                width=button_w, height=button_h),
            'block': ListButton(
                self.window, left, row2, 'Block player',
                width=button_w, height=button_h),
            'unblock': ListButton(
                self.window, right, row2, 'Unblock player',
                width=button_w, height=button_h),
        }

    def on_enter(self):
        self._register_web_inputs()

    def render(self):
        self._draw_menu_chrome()
        panel = pygame.Rect(_BOX_X, _BOX_Y, _BOX_W, _BOX_H)
        _draw_panel(self.window, panel)
        self.window.blit(
            self._title_surf,
            self._title_surf.get_rect(
                centerx=panel.centerx,
                y=_TITLE_Y,
            ),
        )
        self._draw_tabs(panel)

        if self._tab == 'resolution':
            self._draw_resolution()
        elif self._tab == 'preferences':
            self._draw_preferences()
        else:
            self._draw_account_or_safety()
        self._draw_menu_overlay()

    def _draw_tabs(self, panel):
        gap = max(4, int(0.008 * _SW))
        usable = panel.w - int(0.05 * _SW)
        width = (usable - gap * (len(_TABS) - 1)) // len(_TABS)
        height = max(
            int(0.046 * _SH),
            int(getattr(settings, 'TOUCH_COMPACT_MIN', 0) or 0),
        )
        start_x = panel.centerx - (
            width * len(_TABS) + gap * (len(_TABS) - 1)) // 2
        mouse = pygame.mouse.get_pos()
        self._tab_rects = {}
        for index, (key, label) in enumerate(_TABS):
            rect = pygame.Rect(
                start_x + index * (width + gap),
                self._tabs_y,
                width,
                height,
            )
            self._tab_rects[key] = rect
            active = key == self._tab
            hover = rect.collidepoint(mouse)
            background = (
                settings.LIST_BTN_BG_CLICK_CLR
                if active else
                settings.LIST_BTN_BG_HOVER_CLR
                if hover else
                settings.LIST_BTN_BG_CLR
            )
            border = (
                _SECTION_CLR if active else settings.LIST_BTN_BORDER_CLR)
            pygame.draw.rect(
                self.window,
                background,
                rect,
                border_radius=settings.LIST_BTN_CORNER_RADIUS,
            )
            pygame.draw.rect(
                self.window,
                border,
                rect,
                2,
                border_radius=settings.LIST_BTN_CORNER_RADIUS,
            )
            text = self._hint_font.render(
                label,
                True,
                settings.LIST_BTN_TEXT_HOVER_CLR
                if active else settings.LIST_BTN_TEXT_CLR,
            )
            self.window.blit(text, text.get_rect(center=rect.center))

    def _draw_heading(self, title, note=None):
        heading = self._section_font.render(title, True, _SECTION_CLR)
        self.window.blit(heading, (_CONTENT_X, self._content_y))
        if note:
            note_surface = self._hint_font.render(note, True, _HINT_CLR)
            if note_surface.get_width() > _CONTENT_W:
                note_surface = self._hint_font.render(
                    'Manage this section here.', True, _HINT_CLR)
            self.window.blit(
                note_surface,
                (_CONTENT_X, self._content_y + heading.get_height() + 4),
            )

    def _draw_resolution(self):
        self._draw_heading(
            'Resolution',
            'Desktop changes apply after a restart.',
        )
        mouse = pygame.mouse.get_pos()
        count = max(1, len(self._choices))
        available_h = max(
            1,
            self._content_bottom
            - (self._content_y + int(0.09 * _SH))
            - int(0.08 * _SH),
        )
        gap = max(2, int(0.005 * _SH))
        button_h = min(
            max(20, int(0.042 * _SH)),
            max(18, (available_h - gap * (count - 1)) // count),
        )
        start_y = self._content_y + int(0.09 * _SH)
        self._resolution_rects = []
        for index, (width, height, label) in enumerate(self._choices):
            rect = pygame.Rect(
                _CONTENT_X,
                start_y + index * (button_h + gap),
                _CONTENT_W,
                button_h,
            )
            self._resolution_rects.append(rect)
            selected = index == self._selected_idx
            hover = rect.collidepoint(mouse)
            current = (
                width == self._current_w and height == self._current_h)
            if selected:
                background = settings.LIST_BTN_BG_CLICK_CLR
                border = (250, 221, 0)
                text_color = settings.LIST_BTN_TEXT_HOVER_CLR
            elif hover:
                background = settings.LIST_BTN_BG_HOVER_CLR
                border = settings.LIST_BTN_BORDER_HOVER_CLR
                text_color = settings.LIST_BTN_TEXT_HOVER_CLR
            else:
                background = settings.LIST_BTN_BG_CLR
                border = settings.LIST_BTN_BORDER_CLR
                text_color = settings.LIST_BTN_TEXT_CLR
            pygame.draw.rect(
                self.window,
                background,
                rect,
                border_radius=settings.LIST_BTN_CORNER_RADIUS,
            )
            pygame.draw.rect(
                self.window,
                border,
                rect,
                settings.LIST_BTN_BORDER_W,
                border_radius=settings.LIST_BTN_CORNER_RADIUS,
            )
            text = self._btn_font.render(label, True, text_color)
            self.window.blit(
                text,
                (rect.x + int(0.015 * _SW),
                 rect.centery - text.get_height() // 2),
            )
            tag_label = None
            if current:
                tag_label = 'current'
            elif width == self._native_w and height == self._native_h:
                tag_label = 'native'
            if tag_label:
                tag = self._hint_font.render(
                    tag_label, True, _ACTIVE_CLR)
                self.window.blit(
                    tag,
                    (rect.right - int(0.015 * _SW) - tag.get_width(),
                     rect.centery - tag.get_height() // 2),
                )

        if self._restart_pending:
            self._draw_restart_action()
        else:
            self._restart_btn_rect = None

    def _draw_restart_action(self):
        banner_text = (
            f'{self._selected_w} × {self._selected_h} selected')
        banner = self._banner_font.render(
            banner_text, True, _RESTART_CLR)
        button_w = max(int(0.14 * _SW), banner.get_width() + 24)
        button_h = max(
            int(0.042 * _SH),
            int(getattr(settings, 'TOUCH_COMPACT_MIN', 0) or 0),
        )
        self._restart_btn_rect = pygame.Rect(
            _BOX_X + (_BOX_W - button_w) // 2,
            self._content_bottom - button_h,
            button_w,
            button_h,
        )
        rect = self._restart_btn_rect
        hover = rect.collidepoint(pygame.mouse.get_pos())
        background = (100, 80, 40) if hover else _RESTART_BG[:3]
        border = (250, 221, 0) if hover else (180, 160, 130)
        pygame.draw.rect(
            self.window, background, rect, border_radius=8)
        pygame.draw.rect(
            self.window, border, rect, 2, border_radius=8)
        label = self._btn_font.render(
            'Restart Now', True, (250, 221, 0))
        self.window.blit(label, label.get_rect(center=rect.center))

    def _toggle_specs(self):
        from utils import music, sound

        user = getattr(self.state, 'user_dict', None) or {}
        has_email = bool(user.get('has_email'))
        if not user:
            email_hint = 'Log in to manage notification emails.'
        elif not has_email:
            email_hint = (
                'Turn emails require an address added during registration.')
        else:
            email_hint = 'Email me when a turn is waiting while I am offline.'
        return [
            (
                'sound',
                'Sound effects',
                sound.is_enabled(),
                True,
                'Card, battle, and interface sounds.',
            ),
            (
                'music',
                'Background music',
                music.is_enabled(),
                True,
                'Menu, kingdom, and battle themes.',
            ),
            (
                'notify_emails',
                'Email notifications',
                bool(user.get('notify_emails_enabled', True)),
                bool(user) and has_email,
                email_hint,
            ),
        ]

    def _draw_preferences(self):
        self._draw_heading(
            'Preferences',
            'Audio and optional turn notifications.',
        )
        self._toggle_rects = {}
        mouse = pygame.mouse.get_pos()
        row_y = self._content_y + int(0.12 * _SH)
        row_h = max(
            int(0.055 * _SH),
            int(getattr(settings, 'TOUCH_COMPACT_MIN', 0) or 0),
        )
        row_gap = max(10, int(0.035 * _SH))
        pill_w = int(0.055 * _SW)
        for key, label, value, enabled, hint in self._toggle_specs():
            rect = pygame.Rect(_CONTENT_X, row_y, _CONTENT_W, row_h)
            hover = enabled and rect.collidepoint(mouse)
            background = (
                settings.LIST_BTN_BG_HOVER_CLR
                if hover else settings.LIST_BTN_BG_CLR)
            border = (
                settings.LIST_BTN_BORDER_HOVER_CLR
                if hover else settings.LIST_BTN_BORDER_CLR)
            pygame.draw.rect(
                self.window,
                background,
                rect,
                border_radius=settings.LIST_BTN_CORNER_RADIUS,
            )
            pygame.draw.rect(
                self.window,
                border,
                rect,
                settings.LIST_BTN_BORDER_W,
                border_radius=settings.LIST_BTN_CORNER_RADIUS,
            )
            text = self._btn_font.render(
                label,
                True,
                settings.LIST_BTN_TEXT_CLR if enabled else _HINT_CLR,
            )
            self.window.blit(
                text,
                (rect.x + int(0.015 * _SW),
                 rect.centery - text.get_height() // 2),
            )
            pill = pygame.Rect(
                rect.right - pill_w - int(0.012 * _SW),
                rect.y + int(0.15 * rect.h),
                pill_w,
                int(0.7 * rect.h),
            )
            if not enabled:
                pill_background, pill_color, pill_label = (
                    (60, 55, 45), _HINT_CLR, '—')
            elif value:
                pill_background, pill_color, pill_label = (
                    (40, 90, 50), _ACTIVE_CLR, 'On')
            else:
                pill_background, pill_color, pill_label = (
                    (80, 50, 40), (220, 150, 130), 'Off')
            pygame.draw.rect(
                self.window, pill_background, pill, border_radius=10)
            pill_text = self._hint_font.render(
                pill_label, True, pill_color)
            self.window.blit(
                pill_text, pill_text.get_rect(center=pill.center))
            hint_text = self._hint_font.render(hint, True, _HINT_CLR)
            self.window.blit(
                hint_text,
                (rect.x + int(0.015 * _SW), rect.bottom + 3),
            )
            if enabled:
                self._toggle_rects[key] = rect
            row_y += row_h + row_gap

    def _active_fields(self):
        if self._tab == 'account':
            return self.current_password, self.new_password
        if self._tab == 'safety':
            return self.player_username, self.report_details
        return ()

    def _active_action_keys(self):
        if self._tab == 'account':
            return 'change_password', 'logout_all', 'export', 'delete'
        if self._tab == 'safety':
            return 'reason', 'report', 'block', 'unblock'
        return ()

    def _draw_account_or_safety(self):
        if self._tab == 'account':
            title = 'Account'
            note = 'Password, sessions, export, and deletion.'
        else:
            title = 'Player safety'
            note = 'Private reports and direct-contact blocks.'
        self._draw_heading(title, note)
        for field in self._active_fields():
            field.draw()
        for key in self._active_action_keys():
            self._buttons[key].draw()
        if self._busy:
            busy = self._btn_font.render(
                'Working…', True, settings.SUB_SCREEN_TITLE_CLR)
            self.window.blit(
                busy,
                busy.get_rect(
                    centerx=_BOX_X + _BOX_W // 2,
                    bottom=self._content_bottom,
                ),
            )

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
            else:
                user = self.state.user_dict or {}
                new_value = not bool(
                    user.get('notify_emails_enabled', True))
                from utils import auth_service

                result = auth_service.set_notifications(new_value)
                if result is None:
                    self.state.set_msg(
                        'Could not update notification settings')
                else:
                    user['notify_emails_enabled'] = result
                    self.state.set_msg(
                        'Email notifications '
                        + ('enabled' if result else 'disabled'))
            return True
        return False

    def _register_web_inputs(self):
        if not _IS_WEB:
            return
        try:
            from utils.web_keyboard import (
                clear_inputs,
                is_mobile,
                register_input,
                set_inputs_enabled,
            )

            clear_inputs()
            if not is_mobile() or not self._active_fields():
                return
            for field in self._active_fields():
                register_input(
                    field.name,
                    field.content,
                    field.pwd,
                    field.max_length,
                    field.rect,
                )
            set_inputs_enabled(True)
        except Exception:
            pass

    def _clear_web_inputs(self):
        if not _IS_WEB:
            return
        try:
            from utils.web_keyboard import clear_inputs

            clear_inputs()
        except Exception:
            pass

    def update(self, events):
        super().update()
        self._update_icon_buttons()
        for field in self._active_fields():
            field.sync_web_input()
            field.update_color()
        for button in self._buttons.values():
            button.update()
        self._consume_confirmation()
        self._poll_request()

    def handle_events(self, events):
        had_dialogue = bool(self.dialogue_box)
        if super().handle_events(events):
            if had_dialogue:
                return
            events = ()
        panel = pygame.Rect(_BOX_X, _BOX_Y, _BOX_W, _BOX_H)
        for event in events:
            if self._handle_icon_events(event):
                if self.state.screen != 'settings':
                    self._clear_web_inputs()
                continue
            if (
                event.type == MOUSEBUTTONUP
                and event.button == 1
                and not self.dialogue_box
                and not panel.collidepoint(event.pos)
            ):
                self._clear_web_inputs()
                self.state.screen = 'game_menu'
                return

            for field in self._active_fields():
                response = field.handle_event(event)
                if response == 'switch':
                    for candidate in self._active_fields():
                        candidate.active = candidate is not field
                elif response == 'submit':
                    self._submit_default()

            if event.type == KEYDOWN and event.key == K_TAB:
                continue
            if event.type == KEYDOWN and event.key == K_RETURN:
                self._submit_default()
            if event.type != MOUSEBUTTONUP or event.button != 1:
                continue

            for tab, rect in self._tab_rects.items():
                if rect.collidepoint(event.pos) and tab != self._tab:
                    self._tab = tab
                    self._register_web_inputs()
                    return
            if self._busy:
                continue
            if self._tab == 'preferences':
                if self._handle_toggle_click(event.pos):
                    return
            elif self._tab == 'resolution':
                if (
                    self._restart_pending
                    and self._restart_btn_rect
                    and self._restart_btn_rect.collidepoint(event.pos)
                ):
                    self._clear_web_inputs()
                    self.state.screen = 'restart'
                    return
                for index, rect in enumerate(self._resolution_rects):
                    if rect.collidepoint(event.pos):
                        self._select_resolution(index)
                        return
            else:
                for action in self._active_action_keys():
                    if self._buttons[action].rect.collidepoint(event.pos):
                        self._activate(action)
                        return

    def _select_resolution(self, index):
        width, height, _label = self._choices[index]
        self._selected_idx = index
        self._selected_w = width
        self._selected_h = height
        if width != self._current_w or height != self._current_h:
            self._restart_pending = True
            self._save_resolution(width, height)
            self.state.set_msg(
                f'Resolution set to {width}×{height}. Restart to apply.')
        else:
            self._restart_pending = False

    def _submit_default(self):
        if self._busy:
            return
        if self._tab == 'account':
            self._activate('change_password')
        elif self._tab == 'safety':
            self._activate('report')

    def _activate(self, action):
        if action == 'reason':
            self._reason_index = (
                self._reason_index + 1) % len(_REASONS)
            self._buttons['reason'].text = (
                f'Reason: {_REASONS[self._reason_index][1]}')
            return
        if action == 'change_password':
            current = self.current_password.content
            new = self.new_password.content
            if not current or len(new) < 8:
                self.state.set_msg(
                    'Enter your current password and a new password '
                    'of 8+ characters.')
                return
            self._start_request(action, {
                'current_password': current,
                'new_password': new,
            })
            return
        if action in {'logout_all', 'export'}:
            self._start_request(action)
            return
        if action == 'delete':
            if not self.current_password.content:
                self.state.set_msg(
                    'Enter your current password before deleting the account.')
                return
            self.set_action('confirm_delete', None, None)
            self.make_dialogue_box(
                'Permanently delete and anonymize this account? '
                'This cannot be undone.',
                actions=['yes', 'no'],
                title='Delete account',
            )
            return

        username = self.player_username.content.strip()
        if not username:
            self.state.set_msg('Enter a player username.')
            return
        if action == 'report':
            self._start_request(action, {
                'username': username,
                'reason': _REASONS[self._reason_index][0],
                'details': self.report_details.content.strip(),
                'context_type': 'user',
            })
        elif action in {'block', 'unblock'}:
            self._start_request(action, {'username': username})

    def _consume_confirmation(self):
        if self.state.action.get('task') != 'confirm_delete':
            return
        response = self.state.action.get('status')
        if response is None:
            return
        self.reset_action()
        if response == 'yes':
            self._start_request(
                'delete',
                {
                    'current_password': self.current_password.content,
                    'confirmation': 'DELETE',
                },
            )

    def _start_request(self, action, data=None):
        self._busy = True
        if _IS_WEB:
            if action == 'export':
                self._pending_rid = _http.start_async_get(
                    f'{settings.SERVER_URL}/auth/account/export')
            else:
                endpoints = {
                    'change_password': '/auth/account/change_password',
                    'logout_all': '/auth/account/logout_all',
                    'delete': '/auth/account/delete',
                    'report': '/safety/reports',
                    'block': '/safety/blocks',
                    'unblock': '/safety/blocks/remove',
                }
                self._pending_rid = _http.start_async_post(
                    f'{settings.SERVER_URL}{endpoints[action]}',
                    data=data,
                )
            self._pending_action = action
            return

        if action == 'change_password':
            result = account_service.change_password(
                data['current_password'], data['new_password'])
        elif action == 'logout_all':
            result = account_service.logout_all()
        elif action == 'export':
            result = account_service.export_account()
        elif action == 'delete':
            result = account_service.delete_account(
                data['current_password'])
        elif action == 'report':
            result = account_service.report_player(
                data['username'], data['reason'], data['details'])
        else:
            result = account_service.set_player_block(
                data['username'], action == 'block')
        self._busy = False
        self._apply_result(action, result)

    def _poll_request(self):
        if self._pending_rid is None:
            return
        response = _http.check_async(self._pending_rid)
        if response is None:
            return
        action = self._pending_action
        self._pending_rid = None
        self._pending_action = None
        self._busy = False
        try:
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError
        except Exception:
            payload = {
                'success': False,
                'message': 'Unexpected server response. Please try again.',
            }
        if response.status_code >= 400:
            payload['success'] = False
        self._apply_result(action, payload)

    def _apply_result(self, action, result):
        result = result or {}
        message = result.get('message') or (
            'Done.' if result.get('success') else 'Request failed.')
        self.state.set_msg(message)
        if not result.get('success'):
            if result.get('request_id'):
                self.state.set_msg(
                    f"Support request ID: {result['request_id']}")
            return
        if action == 'change_password':
            token = result.get('token')
            if token:
                _http.set_auth_token(token)
            self.current_password.empty()
            self.new_password.empty()
            self._register_web_inputs()
        elif action == 'export':
            try:
                destination = account_service.save_export(
                    result.get('export') or {})
                self.state.set_msg(
                    f'Account export saved: {destination}')
            except Exception:
                self.state.set_msg(
                    'Export was prepared, but the file could not be saved.')
        elif action in {'logout_all', 'delete'}:
            self._clear_web_inputs()
            _http.clear_auth_token()
            self.state.user_dict = None
            self.state.game = None
            self.state.screen = 'login'
        elif action == 'report':
            self.report_details.empty()

    @staticmethod
    def _save_resolution(width, height):
        if sys.platform == 'emscripten':
            return
        try:
            os.makedirs(_CFG_DIR, exist_ok=True)
            existing = {}
            if os.path.exists(_CFG_FILE):
                with open(_CFG_FILE, 'r', encoding='utf-8') as handle:
                    existing = json.load(handle)
            existing['width'] = width
            existing['height'] = height
            with open(_CFG_FILE, 'w', encoding='utf-8') as handle:
                json.dump(existing, handle, indent=2)
        except Exception:
            pass
