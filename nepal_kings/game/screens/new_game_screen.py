# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
import pygame
from pygame.locals import *
from game.screens.screen import Screen
from game.screens._menu_base import MenuScreenMixin, ListButton
from game.core.game import Game
from config import settings
from utils.utils import Button, InputField
from utils.game_service import fetch_users, fetch_user, create_challenge, remove_challenge, create_game, fetch_game
from utils.background_poller import BackgroundPoller

_SW, _SH = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT

DEFAULT_STAKE = 45
DEFAULT_TURN_TIME = ''

# Online-status dot
_DOT_RADIUS    = int(0.006 * _SH)
_DOT_ONLINE    = (60, 200, 80)
_DOT_OFFLINE   = (120, 110, 100)

# NEW tag colours
_NEW_TAG_BG  = (180, 140, 40)
_NEW_TAG_TXT = (30, 28, 24)

# Sent / Received tag colours
_SENT_TAG_BG  = (80, 70, 55, 200)
_SENT_TAG_TXT = (180, 170, 140)
_RECV_TAG_BG  = (55, 90, 70, 200)
_RECV_TAG_TXT = (140, 210, 170)

# ── Overall box ─────────────────────────────────────────────────────
_BOX_PAD    = int(0.025 * _SH)
_BOX_X      = int(0.04 * _SW)
_BOX_Y      = int(0.12 * _SH)
_BOX_W      = int(0.87 * _SW)
_BOX_BOTTOM = int(0.90 * _SH)
_BOX_H      = _BOX_BOTTOM - _BOX_Y

# ── Two-column list areas ──────────────────────────────────────────
_COL1_X     = _BOX_X + int(0.02 * _SW)
_COL2_X     = _BOX_X + int(0.48 * _SW)
_COL_W      = int(0.37 * _SW)

# Config panel lives in the bottom portion of the box
_CONFIG_Y   = int(0.64 * _SH)

# List viewport runs from headers+gap to just above config separator
_LIST_TOP    = None   # computed in __init__ after font metrics
_LIST_BOTTOM = _CONFIG_Y - int(0.010 * _SH)

# Scrollbar
_SCROLLBAR_W   = int(0.006 * _SW)
_SCROLLBAR_CLR = (100, 95, 85, 180)
_THUMB_CLR     = (200, 185, 150, 220)
_THUMB_HOVER   = (240, 220, 170, 255)


def _draw_panel(window, rect, corner_r=None):
    r = corner_r or settings.SUB_SCREEN_PANEL_CORNER_R
    surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    pygame.draw.rect(surf, settings.SUB_SCREEN_PANEL_BG_CLR, surf.get_rect(), border_radius=r)
    window.blit(surf, rect.topleft)
    pygame.draw.rect(window, settings.SUB_SCREEN_PANEL_BORDER_CLR, rect,
                     settings.SUB_SCREEN_PANEL_BORDER_W, border_radius=r)


class NewGameScreen(MenuScreenMixin, Screen):
    def __init__(self, state):
        super().__init__(state)
        self.control_buttons = []
        self._init_menu_chrome()

        self.users = []
        self.user = {}
        self.open_challenges = []
        self.open_opponents = {}
        self.possible_opponents = []

        self.challenge_buttons = []
        self.open_challenge_buttons = []
        self._selected_opponent = None

        # Fonts
        self._title_font = settings.get_font(settings.SUB_SCREEN_TITLE_FONT_SIZE, bold=True)
        self._title_surf = self._title_font.render('New Game', True, settings.SUB_SCREEN_TITLE_CLR)

        self._header_font = settings.get_font(settings.SUB_SCREEN_HEADER_FONT_SIZE)
        self._panel_font = settings.get_font(settings.LIST_BTN_FONT_SIZE)
        self._tag_font = settings.get_font(int(0.016 * _SH), bold=True)

        # Layout positions inside box
        self._title_y = _BOX_Y + _BOX_PAD
        title_bottom = self._title_y + self._title_surf.get_height() + int(0.010 * _SH)
        self._hdr_y = title_bottom
        self._list_top = self._hdr_y + self._header_font.get_height() + int(0.010 * _SH)
        self._list_bottom = _LIST_BOTTOM

        # Scroll state (one per column)
        self._scroll_col1 = 0
        self._scroll_col2 = 0
        self._max_scroll_col1 = 0
        self._max_scroll_col2 = 0
        self._dragging_thumb = None  # 'col1' | 'col2' | None
        self._drag_offset = 0

        # ── Config panel widgets ────────────────────────────────────
        field_x = _BOX_X + int(0.20 * _SW)
        field_w = int(0.06 * _SW)
        field_h = int(0.032 * _SH)
        cfg_row1 = _CONFIG_Y + int(0.050 * _SH)
        cfg_row2 = cfg_row1 + field_h + int(0.035 * _SH)

        self.stake_field = InputField(
            self.window, field_x, cfg_row1,
            "Stake (gold)", str(DEFAULT_STAKE), False, False,
            max_length=6, width=field_w, height=field_h)

        self.time_field = InputField(
            self.window, field_x, cfg_row2,
            "Turn Time (min)", DEFAULT_TURN_TIME, False, False,
            max_length=4, width=field_w, height=field_h)

        # Smaller fonts for config-panel input fields
        _cfg_font_sz  = int(0.022 * _SH)
        _cfg_title_sz = int(0.018 * _SH)
        for fld in (self.stake_field, self.time_field):
            fld.font       = settings.get_font(_cfg_font_sz)
            fld.font_title = settings.get_font(_cfg_title_sz)

        self.no_time_limit = True
        self._checkbox_size = int(0.022 * _SH)
        self._checkbox_x = field_x + field_w + int(0.012 * _SW)
        self._checkbox_y = cfg_row2 + (field_h - self._checkbox_size) // 2

        # ── Send button (menu-button style) ─────────────────────────
        _send_w = int(0.18 * _SW)
        _send_h = int(0.055 * _SH)
        _send_x = _BOX_X + int(0.54 * _SW)
        _send_y = _CONFIG_Y + int(0.075 * _SH)
        self.send_button = Button(
            self.window, _send_x, _send_y,
            "Send Challenge", width=_send_w, height=_send_h)

        # Apply menu button image
        raw_btn = pygame.image.load(settings.GAME_MENU_BTN_IMG_PATH).convert_alpha()
        self.send_button.button_image = pygame.transform.smoothscale(
            raw_btn, (_send_w, _send_h))
        self.send_button.button_image_small = pygame.transform.smoothscale(
            raw_btn, (int(_send_w * 0.95), int(_send_h * 0.95)))

        # Glow behind button
        glow_w = int(_send_w * settings.GAME_MENU_GLOW_W_FACTOR)
        glow_h = int(_send_h * settings.GAME_MENU_GLOW_H_FACTOR)
        self._send_glows = {}
        for clr_name in ('yellow', 'white', 'orange'):
            raw_g = pygame.image.load(settings.GAME_MENU_GLOW_DIR + clr_name + '.png').convert_alpha()
            self._send_glows[clr_name] = pygame.transform.smoothscale(raw_g, (glow_w, glow_h))

    # ── Data fetching ─────────────────────────────────────────────

    def update_all_challenge_buttons(self):
        try:
            self.users = fetch_users(self.state.user_dict['username'])
            self.user = fetch_user(self.state.user_dict['username'])
        except Exception as e:
            self.state.set_msg(f"Error fetching users or user data: {str(e)}")
            return

        all_challenges = self.user['challenges_issued'] + self.user['challenges_received']
        self.open_challenges = [ch for ch in all_challenges if ch.get('status') == 'open']
        self.open_opponents = {}
        for ch in self.open_challenges:
            opp_id = ch['challenger_id'] if ch['challenger_id'] != self.user['id'] else ch['challenged_id']
            opp = next(u for u in self.users if u['id'] == opp_id)
            self.open_opponents[ch['id']] = opp

    @staticmethod
    def _bg_fetch_challenges(username):
        """Thread-safe fetch of users + user data."""
        users = fetch_users(username)
        user = fetch_user(username)
        return {'users': users, 'user': user}

    @staticmethod
    def _parse_challenge_responses(responses):
        """Transform multi-request async responses into challenge data."""
        users = responses['users'].json().get('users', [])
        user = responses['user'].json().get('user', {})
        return {'users': users, 'user': user}

    def _rebuild_challenge_buttons(self):
        """Rebuild challenge / opponent button lists from self.users / self.open_opponents."""
        self.possible_opponents = [u for u in self.users if u not in self.open_opponents.values()]

        # Sort: online first, then alphabetical
        self.possible_opponents.sort(key=lambda u: (not u.get('is_online', False), u['username'].lower()))

        btn_w = _COL_W - _SCROLLBAR_W - int(0.008 * _SW)
        btn_h = settings.LIST_BTN_H
        gap = int(0.008 * _SH)

        self.challenge_buttons = []
        for i, u in enumerate(self.possible_opponents):
            y = self._list_top + i * (btn_h + gap)
            btn = ListButton(self.window, _COL1_X, y, u['username'], width=btn_w, height=btn_h)
            btn.is_online = u.get('is_online', False)
            self.challenge_buttons.append(btn)

        self.open_challenge_buttons = []
        for i, (ch_id, opp) in enumerate(self.open_opponents.items()):
            y = self._list_top + i * (btn_h + gap)
            btn = ListButton(self.window, _COL2_X, y, opp['username'], width=btn_w, height=btn_h)
            btn.is_online = opp.get('is_online', False)
            btn.challenge_id = ch_id  # Store for NEW tag lookup
            # Determine if this challenge was sent by us or received
            ch = next((c for c in self.open_challenges if c['id'] == ch_id), None)
            btn.is_sent = ch is not None and ch.get('challenger_id') == self.user.get('id')
            self.open_challenge_buttons.append(btn)

        # Scroll limits
        viewport_h = self._list_bottom - self._list_top
        n1 = len(self.challenge_buttons)
        n2 = len(self.open_challenge_buttons)
        content1 = n1 * (btn_h + gap) - (gap if n1 else 0)
        content2 = n2 * (btn_h + gap) - (gap if n2 else 0)
        self._content_h_col1 = content1
        self._content_h_col2 = content2
        self._max_scroll_col1 = max(0, content1 - viewport_h)
        self._max_scroll_col2 = max(0, content2 - viewport_h)
        self._scroll_col1 = min(self._scroll_col1, self._max_scroll_col1)
        self._scroll_col2 = min(self._scroll_col2, self._max_scroll_col2)

    # ── Scroll helpers ────────────────────────────────────────────

    def _viewport_h(self):
        return self._list_bottom - self._list_top

    def _thumb_rect(self, col):
        scroll = self._scroll_col1 if col == 'col1' else self._scroll_col2
        max_s = self._max_scroll_col1 if col == 'col1' else self._max_scroll_col2
        content = getattr(self, f'_content_h_{col}', 0)
        vp = self._viewport_h()
        if max_s <= 0 or content <= 0:
            return pygame.Rect(0, 0, 0, 0)
        col_x = _COL1_X if col == 'col1' else _COL2_X
        btn_w = _COL_W - _SCROLLBAR_W - int(0.008 * _SW)
        track_x = col_x + btn_w + int(0.004 * _SW)
        thumb_h = max(int(0.03 * _SH), int(vp * (vp / content)))
        travel = vp - thumb_h
        frac = scroll / max_s if max_s else 0
        thumb_y = self._list_top + int(frac * travel)
        return pygame.Rect(track_x, thumb_y, _SCROLLBAR_W, thumb_h)

    def _track_rect(self, col):
        col_x = _COL1_X if col == 'col1' else _COL2_X
        btn_w = _COL_W - _SCROLLBAR_W - int(0.008 * _SW)
        track_x = col_x + btn_w + int(0.004 * _SW)
        return pygame.Rect(track_x, self._list_top, _SCROLLBAR_W, self._viewport_h())

    def _needs_scroll(self, col):
        content = getattr(self, f'_content_h_{col}', 0)
        return content > self._viewport_h()

    # ── Rendering ─────────────────────────────────────────────────

    def render(self):
        self._draw_menu_chrome()

        # Outer box
        box_rect = pygame.Rect(_BOX_X, _BOX_Y, _BOX_W, _BOX_H)
        _draw_panel(self.window, box_rect)

        # Title (centred inside box)
        tx = _BOX_X + (_BOX_W - self._title_surf.get_width()) // 2
        self.window.blit(self._title_surf, (tx, self._title_y))

        # Column headers
        hdr1 = self._header_font.render('Possible Opponents', True, settings.SUB_SCREEN_HEADER_CLR)
        hdr2 = self._header_font.render('Open Challenges', True, settings.SUB_SCREEN_HEADER_CLR)
        self.window.blit(hdr1, (_COL1_X, self._hdr_y))
        self.window.blit(hdr2, (_COL2_X, self._hdr_y))

        # Column 1 list
        self._draw_scrollable_list(self.challenge_buttons, _COL1_X, self._scroll_col1, 'col1')
        # Column 2 list
        self._draw_scrollable_list(self.open_challenge_buttons, _COL2_X, self._scroll_col2, 'col2')

        # Config panel separator + content
        self._draw_config_panel()

        self._draw_menu_overlay()

    def _draw_scrollable_list(self, buttons, col_x, scroll, col_key):
        if not buttons:
            return

        btn_h = settings.LIST_BTN_H
        gap = int(0.008 * _SH)
        clip = pygame.Rect(col_x, self._list_top, _COL_W, self._viewport_h())
        self.window.set_clip(clip)

        for i, btn in enumerate(buttons):
            # Shift vertically by scroll
            original_y = self._list_top + i * (btn_h + gap)
            btn.rect.y = original_y - scroll
            if btn.rect.bottom >= self._list_top and btn.rect.top <= self._list_bottom:
                btn.draw()
                # Online dot
                dot_clr = _DOT_ONLINE if getattr(btn, 'is_online', False) else _DOT_OFFLINE
                dot_x = btn.rect.x + int(0.012 * _SW)
                dot_y = btn.rect.centery
                pygame.draw.circle(self.window, dot_clr, (dot_x, dot_y), _DOT_RADIUS)

                # Sent / Received tag
                is_sent = getattr(btn, 'is_sent', None)
                if is_sent is not None:
                    tag_label = 'SENT' if is_sent else 'RECV'
                    tag_bg_clr = _SENT_TAG_BG if is_sent else _RECV_TAG_BG
                    tag_txt_clr = _SENT_TAG_TXT if is_sent else _RECV_TAG_TXT
                    sr_surf = self._tag_font.render(tag_label, True, tag_txt_clr)
                    srw, srh = sr_surf.get_size()
                    sr_pad_x, sr_pad_y = int(0.005 * _SW), int(0.002 * _SH)
                    sr_x = btn.rect.right - srw - 2 * sr_pad_x - int(0.008 * _SW)
                    sr_y = btn.rect.centery - (srh + 2 * sr_pad_y) // 2
                    sr_rect = pygame.Rect(sr_x, sr_y, srw + 2 * sr_pad_x, srh + 2 * sr_pad_y)
                    sr_bg = pygame.Surface((sr_rect.w, sr_rect.h), pygame.SRCALPHA)
                    pygame.draw.rect(sr_bg, tag_bg_clr, sr_bg.get_rect(), border_radius=4)
                    self.window.blit(sr_bg, sr_rect.topleft)
                    self.window.blit(sr_surf, (sr_rect.x + sr_pad_x, sr_rect.y + sr_pad_y))

                # NEW tag (only for open challenges with a stored challenge_id)
                ch_id = getattr(btn, 'challenge_id', None)
                if ch_id is not None and ch_id in self.state._new_challenge_ids:
                    tag_surf = self._tag_font.render('NEW', True, _NEW_TAG_TXT)
                    tw, th = tag_surf.get_size()
                    pad_x, pad_y = int(0.005 * _SW), int(0.002 * _SH)
                    # Shift NEW tag left of SENT/RECV tag if present
                    new_offset = sr_rect.w + int(0.004 * _SW) if is_sent is not None else 0
                    tag_x = btn.rect.right - tw - 2 * pad_x - int(0.008 * _SW) - new_offset
                    tag_y = btn.rect.centery - (th + 2 * pad_y) // 2
                    tag_rect = pygame.Rect(tag_x, tag_y, tw + 2 * pad_x, th + 2 * pad_y)
                    tag_bg = pygame.Surface((tag_rect.w, tag_rect.h), pygame.SRCALPHA)
                    pygame.draw.rect(tag_bg, _NEW_TAG_BG, tag_bg.get_rect(), border_radius=4)
                    self.window.blit(tag_bg, tag_rect.topleft)
                    self.window.blit(tag_surf, (tag_rect.x + pad_x, tag_rect.y + pad_y))

        self.window.set_clip(None)

        # Scrollbar
        if self._needs_scroll(col_key):
            track = self._track_rect(col_key)
            ts = pygame.Surface((track.w, track.h), pygame.SRCALPHA)
            ts.fill(_SCROLLBAR_CLR)
            self.window.blit(ts, track.topleft)
            thumb = self._thumb_rect(col_key)
            mx, my = pygame.mouse.get_pos()
            clr = _THUMB_HOVER if thumb.collidepoint(mx, my) or self._dragging_thumb == col_key else _THUMB_CLR
            ths = pygame.Surface((thumb.w, thumb.h), pygame.SRCALPHA)
            pygame.draw.rect(ths, clr, ths.get_rect(), border_radius=3)
            self.window.blit(ths, thumb.topleft)

    def _draw_config_panel(self):
        # Separator
        pygame.draw.line(self.window, settings.SUB_SCREEN_PANEL_BORDER_CLR,
                         (_BOX_X + int(0.01 * _SW), _CONFIG_Y),
                         (_BOX_X + _BOX_W - int(0.01 * _SW), _CONFIG_Y), 1)

        if self._selected_opponent:
            header = self._panel_font.render(
                f"Challenge: {self._selected_opponent['username']}",
                True, (220, 200, 100))
            self.window.blit(header, (_COL1_X, _CONFIG_Y + int(0.025 * _SH)))

            self.stake_field.draw()
            self.time_field.draw()
            self._draw_checkbox()
            self._draw_send_button()
        else:
            hint = self._panel_font.render(
                "Select an opponent to configure a challenge",
                True, (140, 140, 140))
            self.window.blit(hint, (_COL1_X, _CONFIG_Y + int(0.038 * _SH)))

    def _draw_send_button(self):
        """Draw the send-challenge button with menu-button glow."""
        btn = self.send_button
        is_disabled = hasattr(btn, 'disabled') and btn.disabled
        if not is_disabled:
            if btn.hovered and btn.clicked:
                glow = self._send_glows['yellow']
            elif btn.hovered and not btn.active:
                glow = self._send_glows['white']
            elif btn.active:
                glow = self._send_glows['orange']
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

    def _draw_checkbox(self):
        box_rect = pygame.Rect(self._checkbox_x, self._checkbox_y,
                               self._checkbox_size, self._checkbox_size)
        pygame.draw.rect(self.window, (180, 180, 180), box_rect, 2)
        if self.no_time_limit:
            inner = box_rect.inflate(-6, -6)
            pygame.draw.rect(self.window, (250, 170, 0), inner)
        label = self._panel_font.render("No Limit", True, (200, 200, 200))
        self.window.blit(label, (self._checkbox_x + self._checkbox_size + 8,
                                 self._checkbox_y + (self._checkbox_size - label.get_height()) // 2))

    # ── Update ────────────────────────────────────────────────────

    def update(self, events):
        super().update()
        self._update_icon_buttons()

        # ── Non-blocking challenge polling (every 5s) ─────────
        if not hasattr(self, '_challenge_poller'):
            self._challenge_poller = None
        current_time = pygame.time.get_ticks()
        if current_time - self.last_update_time >= 5000:
            self.last_update_time = current_time
            username = self.state.user_dict.get('username', '')
            if self._challenge_poller is None:
                base = settings.SERVER_URL
                self._challenge_poller = BackgroundPoller(
                    self._bg_fetch_challenges, args=(username,),
                    async_requests=[
                        {'key': 'users',
                         'url': f'{base}/auth/get_users',
                         'params': {'username': 0}},
                        {'key': 'user',
                         'url': f'{base}/auth/get_user',
                         'params': {'username': 0}},
                    ],
                    async_transform=self._parse_challenge_responses)
            if not self._challenge_poller.busy:
                self._challenge_poller.poll(args=(username,))
        # Apply result if ready
        if hasattr(self, '_challenge_poller') and self._challenge_poller and self._challenge_poller.has_result():
            data = self._challenge_poller.result
            if data:
                self.users = data['users']
                self.user = data['user']
                # Check for accepted challenges (notify challenger)
                try:
                    self._check_accepted_challenges()
                except Exception as e:
                    print(f"[new_game] _check_accepted_challenges error: {e}")
                all_challenges = self.user['challenges_issued'] + self.user['challenges_received']
                self.open_challenges = [ch for ch in all_challenges if ch.get('status') == 'open']
                self.open_opponents = {}
                for ch in self.open_challenges:
                    opp_id = ch['challenger_id'] if ch['challenger_id'] != self.user['id'] else ch['challenged_id']
                    opp = next((u for u in self.users if u['id'] == opp_id), None)
                    if opp:
                        self.open_opponents[ch['id']] = opp
                self._rebuild_challenge_buttons()
        # ──────────────────────────────────────────────────────

        # Only update hover/click for visible buttons
        for btn in self.challenge_buttons + self.open_challenge_buttons:
            if btn.rect.bottom >= self._list_top and btn.rect.top <= self._list_bottom:
                btn.update()
            else:
                btn.hovered = False
                btn.clicked = False

        if self._selected_opponent:
            self.stake_field.update_color()
            if not self.no_time_limit:
                self.time_field.update_color()
            self.send_button.update()

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

            if self._selected_opponent:
                self.stake_field.handle_event(event)
                if not self.no_time_limit:
                    self.time_field.handle_event(event)

            # Scroll wheel
            if event.type == MOUSEWHEEL:
                mx, my = pygame.mouse.get_pos()
                scroll_step = int(0.04 * _SH)
                # Which column?
                col1_clip = pygame.Rect(_COL1_X, self._list_top, _COL_W, self._viewport_h())
                col2_clip = pygame.Rect(_COL2_X, self._list_top, _COL_W, self._viewport_h())
                if col1_clip.collidepoint(mx, my):
                    self._scroll_col1 = max(0, min(self._max_scroll_col1,
                                                   self._scroll_col1 - event.y * scroll_step))
                elif col2_clip.collidepoint(mx, my):
                    self._scroll_col2 = max(0, min(self._max_scroll_col2,
                                                   self._scroll_col2 - event.y * scroll_step))

            # Thumb dragging
            if event.type == MOUSEBUTTONDOWN and event.button == 1:
                _started_thumb = False
                for col_key in ('col1', 'col2'):
                    thumb = self._thumb_rect(col_key)
                    if thumb.w and thumb.collidepoint(event.pos):
                        self._dragging_thumb = col_key
                        self._drag_offset = event.pos[1] - thumb.y
                        _started_thumb = True
                        break
                if not _started_thumb:
                    # Touch-drag scroll in the content columns
                    col1_clip = pygame.Rect(_COL1_X, self._list_top, _COL_W, self._viewport_h())
                    col2_clip = pygame.Rect(_COL2_X, self._list_top, _COL_W, self._viewport_h())
                    if col1_clip.collidepoint(event.pos):
                        self._touch_scrolling = 'col1'
                        self._touch_last_y = event.pos[1]
                    elif col2_clip.collidepoint(event.pos):
                        self._touch_scrolling = 'col2'
                        self._touch_last_y = event.pos[1]

            if event.type == MOUSEBUTTONUP and event.button == 1:
                self._dragging_thumb = None
                self._touch_scrolling = None

            if event.type == MOUSEMOTION:
                if self._dragging_thumb:
                    col_key = self._dragging_thumb
                    track = self._track_rect(col_key)
                    thumb_h = self._thumb_rect(col_key).h
                    travel = track.h - thumb_h
                    max_s = self._max_scroll_col1 if col_key == 'col1' else self._max_scroll_col2
                    if travel > 0:
                        new_top = event.pos[1] - self._drag_offset - track.y
                        frac = max(0.0, min(1.0, new_top / travel))
                        val = int(frac * max_s)
                        if col_key == 'col1':
                            self._scroll_col1 = val
                        else:
                            self._scroll_col2 = val
                elif getattr(self, '_touch_scrolling', None):
                    dy = event.pos[1] - self._touch_last_y
                    self._touch_last_y = event.pos[1]
                    col_key = self._touch_scrolling
                    max_s = self._max_scroll_col1 if col_key == 'col1' else self._max_scroll_col2
                    if col_key == 'col1':
                        self._scroll_col1 = max(0, min(max_s, self._scroll_col1 - dy))
                    else:
                        self._scroll_col2 = max(0, min(max_s, self._scroll_col2 - dy))

            # Clicks
            if not self.dialogue_box and event.type == MOUSEBUTTONUP and event.button == 1:
                if not self._dragging_thumb:
                    self._handle_clicks()

        # Dialogue actions
        if self.state.action["task"] == "accept_game_challenge" and self.state.action["status"] != "open":
            challenge = self.state.action["content"]
            if self.state.action["status"] == 'accept':
                self.handle_create_game(challenge)
            elif self.state.action["status"] == 'reject':
                self.handle_remove_challenge(challenge['id'])
            self.reset_action()

        # Accepted challenge notification actions
        if self.state.action["task"] == "challenge_accepted" and self.state.action["status"] != "open":
            pending = self.state._pending_accepted_challenge
            if pending:
                challenge_id = pending['challenge_id']
                if self.state.action["status"] == 'go to game':
                    game_dict = pending.get('game_dict')
                    if not game_dict and pending.get('game_id'):
                        try:
                            game_dict = fetch_game(pending['game_id'])
                        except Exception:
                            game_dict = None
                    if game_dict:
                        self.state.game = Game(game_dict, self.state.user_dict)
                        remove_challenge(challenge_id)
                        self.state._notified_accepted_challenges.discard(challenge_id)
                        self.state._pending_accepted_challenge = None
                        self.reset_action()
                        self.state.screen = "game"
                        return
                    else:
                        self.state.set_msg("Failed to load game")
                else:  # "close"
                    remove_challenge(challenge_id)
                self.state._notified_accepted_challenges.discard(challenge_id)
                self.state._pending_accepted_challenge = None
            self.reset_action()

    def _handle_clicks(self):
        # Checkbox
        if self._selected_opponent:
            label_w = self._panel_font.size("No Limit")[0] + self._checkbox_size + 8
            click_rect = pygame.Rect(self._checkbox_x, self._checkbox_y,
                                     label_w, self._checkbox_size)
            if click_rect.collidepoint(pygame.mouse.get_pos()):
                self.no_time_limit = not self.no_time_limit
                if self.no_time_limit:
                    self.time_field.deactivate()
                    self.time_field.content = ''
                    self.time_field.cursor_pos = 0
                return

        # Send button
        if self._selected_opponent and self.send_button.collide():
            self._send_challenge()
            return

        # Opponent selection (only visible buttons)
        for btn, user in zip(self.challenge_buttons, self.possible_opponents):
            if (btn.rect.top >= self._list_top and btn.rect.bottom <= self._list_bottom
                    and btn.collide()):
                self._selected_opponent = user
                self.stake_field.content = str(DEFAULT_STAKE)
                self.stake_field.cursor_pos = len(self.stake_field.content)
                self.time_field.content = ''
                self.time_field.cursor_pos = 0
                self.no_time_limit = True
                self.stake_field.activate()
                self.time_field.deactivate()
                return

        # Open challenges (only visible buttons)
        for btn, ch in zip(self.open_challenge_buttons, self.open_challenges):
            if (btn.rect.top >= self._list_top and btn.rect.bottom <= self._list_bottom
                    and btn.collide()):
                stake = ch.get('stake', 45)
                turn_time = ch.get('turn_time_limit')
                time_str = f"{turn_time // 60} min" if turn_time else "No Limit"
                if ch in self.user['challenges_issued']:
                    self.make_dialogue_box(
                        f'You have challenged {btn.text} at {ch["date"]}\n\n'
                        f'Stake: {stake} gold\nTurn Time: {time_str}',
                        actions=['ok'], title="Challenge Pending")
                else:
                    self.set_action("accept_game_challenge", ch, "open")
                    self.make_dialogue_box(
                        f'Do you want to accept a game with {btn.text}?\n\n'
                        f'Stake: {stake} gold\nTurn Time: {time_str}',
                        actions=["accept", "reject"], title="Accept Challenge")
                return

    # ── Accepted-challenge notification ─────────────────────────

    def _check_accepted_challenges(self):
        """Check if any issued challenges have been accepted and show notification."""
        issued = self.user.get('challenges_issued', [])
        accepted = [ch for ch in issued if ch.get('status') == 'accepted']
        if accepted:
            print(f"[new_game] Found {len(accepted)} accepted challenge(s): "
                  f"{[(ch['id'], ch.get('game_id')) for ch in accepted]}, "
                  f"already notified: {self.state._notified_accepted_challenges}, "
                  f"dialogue_box: {bool(self.dialogue_box)}")
        if self.dialogue_box:
            return
        # If a previous notification was set on another screen (or the dialogue
        # was dismissed by navigating away), clean up the stale state.
        if self.state._pending_accepted_challenge:
            stale_id = self.state._pending_accepted_challenge['challenge_id']
            try:
                remove_challenge(stale_id)
            except Exception:
                pass
            self.state._notified_accepted_challenges.discard(stale_id)
            self.state._pending_accepted_challenge = None
            if self.state.action.get('task') == 'challenge_accepted':
                self.reset_action()
        for ch in self.user.get('challenges_issued', []):
            if (ch.get('status') == 'accepted'
                    and ch['id'] not in self.state._notified_accepted_challenges):
                opponent_name = ch.get('challenged_name', 'opponent')
                stake = ch.get('stake', 45)
                self.state._pending_accepted_challenge = {
                    'challenge_id': ch['id'],
                    'game_id': ch.get('game_id'),
                    'opponent_name': opponent_name,
                    'stake': stake,
                }
                self.state._notified_accepted_challenges.add(ch['id'])
                self.set_action("challenge_accepted", ch['id'], "open")
                self.make_dialogue_box(
                    f'{opponent_name} accepted your challenge!\n\n'
                    f'Stake: {stake} gold',
                    actions=["Go to Game", "Close"],
                    title="Challenge Accepted")
                break

    # ── Challenge submission ──────────────────────────────────────

    def _send_challenge(self):
        try:
            stake = int(self.stake_field.content)
        except (ValueError, TypeError):
            self.state.set_msg("Stake must be a number")
            return
        if stake < 1:
            self.state.set_msg("Stake must be at least 1 gold")
            return

        gold = self.user.get('gold', 0) if self.user else 0
        if gold < stake:
            self.state.set_msg(f"Not enough gold ({gold}/{stake})")
            return

        turn_time_limit = None
        if not self.no_time_limit:
            try:
                minutes = int(self.time_field.content)
                if minutes < 1:
                    self.state.set_msg("Turn time must be at least 1 minute")
                    return
                turn_time_limit = minutes * 60
            except (ValueError, TypeError):
                self.state.set_msg("Turn time must be a number (minutes)")
                return

        opponent_name = self._selected_opponent['username']
        self.handle_create_challenge(opponent_name, stake, turn_time_limit)
        self._selected_opponent = None

    # ── Actions ───────────────────────────────────────────────────

    def handle_create_challenge(self, opponent_name, stake=45, turn_time_limit=None):
        response = create_challenge(self.state.user_dict['username'], opponent_name, stake=stake, turn_time_limit=turn_time_limit)
        if response.get('success'):
            self.state.set_msg(f"Challenge sent to {opponent_name}")
        else:
            self.state.set_msg(response.get('message', 'Failed to create challenge'))

    def handle_create_game(self, challenge):
        response = create_game(challenge['id'])
        if response['success'] and 'game' in response:
            self.state.game = Game(response['game'], self.state.user_dict)
            self.state.screen = "game"
        else:
            self.state.set_msg(response['message'])

    def handle_remove_challenge(self, challenge_id):
        response = remove_challenge(challenge_id)
        if not response['success']:
            self.state.set_msg(response['message'])

    def reset_action(self):
        print(f"Resetting action. Task: {self.state.action['task']}, Status: {self.state.action['status']}")
        self.state.action = {"task": None, "content": None, "status": None}
