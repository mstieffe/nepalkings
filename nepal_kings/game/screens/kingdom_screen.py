# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Kingdom screen — interactive hex map with land details."""

import pygame
from pygame.locals import *
from game.screens.screen import Screen
from game.screens._menu_base import MenuScreenMixin
from game.components.hex_map import HexMap
from game.components.land_detail_box import LandDetailBox
from game.components.floating_text import FloatingText, FloatingTextLayer
from config import settings
from utils import http_compat as requests
import logging

logger = logging.getLogger('nk.screens.kingdom')

_SW, _SH = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT

# ── Overall box ─────────────────────────────────────────────────────
_BOX_PAD    = int(0.020 * _SH)
_BOX_X      = int(0.04 * _SW)
_BOX_Y      = int(0.10 * _SH)
_BOX_W      = int(0.87 * _SW)
_BOX_BOTTOM = int(0.92 * _SH)
_BOX_H      = _BOX_BOTTOM - _BOX_Y


def _draw_panel(window, rect, corner_r=None):
    r = corner_r or settings.SUB_SCREEN_PANEL_CORNER_R
    surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    pygame.draw.rect(surf, settings.SUB_SCREEN_PANEL_BG_CLR, surf.get_rect(), border_radius=r)
    window.blit(surf, rect.topleft)
    pygame.draw.rect(window, settings.SUB_SCREEN_PANEL_BORDER_CLR, rect,
                     settings.SUB_SCREEN_PANEL_BORDER_W, border_radius=r)


def _compute_kingdom_layout():
    """Return non-overlapping layout rects for the kingdom dashboard."""
    box = pygame.Rect(_BOX_X, _BOX_Y, _BOX_W, _BOX_H)
    pad = _BOX_PAD
    gap = settings.KINGDOM_PANEL_GAP
    header = pygame.Rect(
        box.x + pad,
        box.y + pad,
        box.w - 2 * pad,
        settings.KINGDOM_HEADER_H,
    )

    content_top = header.bottom + int(0.008 * _SH)
    content_bottom = box.bottom - pad
    content_h = max(1, content_bottom - content_top)
    activity_w = settings.KINGDOM_ACTIVITY_W
    activity = pygame.Rect(
        box.right - pad - activity_w,
        content_top,
        activity_w,
        content_h,
    )
    map_frame = pygame.Rect(
        box.x + pad,
        content_top,
        activity.x - gap - (box.x + pad),
        content_h,
    )
    map_viewport = pygame.Rect(
        map_frame.x + settings.KINGDOM_MAP_FRAME_PAD,
        map_frame.y + settings.KINGDOM_MAP_FRAME_PAD,
        map_frame.w - 2 * settings.KINGDOM_MAP_FRAME_PAD,
        map_frame.h - 2 * settings.KINGDOM_MAP_FRAME_PAD,
    )
    _xsz = int(0.028 * _SH)
    close = pygame.Rect(
        header.right - _xsz,
        header.y,
        _xsz,
        _xsz,
    )
    return {
        'box': box,
        'header': header,
        'map_frame': map_frame,
        'map_viewport': map_viewport,
        'activity': activity,
        'close': close,
    }


class KingdomScreen(MenuScreenMixin, Screen):
    """Kingdom screen with hex-map, minimap, land detail box, and nav controls."""

    def __init__(self, state):
        super().__init__(state)
        self.control_buttons = []
        self._init_menu_chrome()

        # ── State ───────────────────────────────────────────────────
        self._hex_map = None          # built on first enter
        self._detail_box = None       # LandDetailBox (modal)
        self._map_data = None         # raw server response
        self._cooldown = 0            # conquer cooldown seconds
        self._loading = False
        self._error = None

        # ── Attack notifications ────────────────────────────────────
        self._notifications = []      # unseen attack notifications
        self._attack_history = []     # recent attack history for this user
        self._messages = []           # kingdom user messages
        self._message_unread_count = 0
        self._activity_tab = 'alerts'
        self._activity_tab_rects = {}
        self._activity_row_rects = []
        self._activity_scroll_offsets = {'alerts': 0, 'history': 0, 'messages': 0}
        self._activity_scrollbar_rect = None
        self._mark_read_rect = None
        self._mark_read_kind = None
        self._message_compose = None
        self._message_input_rect = None
        self._message_send_rect = None
        self._message_cancel_rect = None

        # ── Layout ──────────────────────────────────────────────────
        self._layout = _compute_kingdom_layout()
        self._box_rect = self._layout['box']
        self._header_rect = self._layout['header']
        self._map_frame_rect = self._layout['map_frame']
        self._map_viewport_rect = self._layout['map_viewport']
        self._activity_rect = self._layout['activity']

        # ── Title ───────────────────────────────────────────────────
        self._title_font = settings.get_font(settings.SUB_SCREEN_TITLE_FONT_SIZE, bold=True)
        self._title_surf = self._title_font.render('Kingdom', True, settings.SUB_SCREEN_TITLE_CLR)
        self._title_y = self._header_rect.y

        # ── Fonts ───────────────────────────────────────────────────
        self._info_font = settings.get_font(settings.KINGDOM_INFO_FONT_SIZE)
        self._nav_font = settings.get_font(settings.KINGDOM_INFO_FONT_SIZE, bold=True)
        self._activity_title_font = settings.get_font(settings.FS_SMALL, bold=True)
        self._activity_font = settings.get_font(settings.FS_TINY)
        self._activity_small_font = settings.get_font(int(settings.FS_TINY * 0.86))

        # ── Navigation zoom buttons (inside map frame, bottom-left) ─
        btn_sz = settings.NAV_BTN_SIZE
        margin = settings.NAV_BTN_MARGIN
        nav_by = self._map_frame_rect.bottom - settings.KINGDOM_MAP_FRAME_PAD - btn_sz
        nav_x = self._map_frame_rect.x + settings.KINGDOM_MAP_FRAME_PAD

        self._nav_rects = {
            'zoom_in':  pygame.Rect(nav_x, nav_by - btn_sz - margin, btn_sz, btn_sz),
            'zoom_out': pygame.Rect(nav_x, nav_by, btn_sz, btn_sz),
        }
        self._nav_labels = {
            'zoom_in': '+',
            'zoom_out': '\u2212',  # minus sign
        }

        # ── X close button (top-right of header) ───────────────────
        self._btn_close_rect = self._layout['close']

        # ── Collect All gold button (drawn in info bar) ────────────
        self._collect_all_rect = None
        self._collect_all_enabled = False
        self._floating_text = FloatingTextLayer()
        self._floating_text_last_tick = pygame.time.get_ticks()
        self._collect_float_font = settings.get_font(
            getattr(settings, 'COLLECT_FLOAT_FONT_SIZE', settings.FS_HEADING), bold=True)

        # ── Track last load time ────────────────────────────────────
        self._last_load_tick = 0

    # ── Lifecycle ────────────────────────────────────────────────────

    def on_enter(self):
        """Called each time the kingdom screen becomes active."""
        self._hex_map = None
        self._last_load_tick = 0
        self._floating_text_last_tick = pygame.time.get_ticks()

    # ── Data loading ────────────────────────────────────────────────

    def _load_map(self):
        """Fetch map data from the server and build/update the hex map."""
        self._loading = True
        self._error = None
        try:
            resp = requests.get(f'{settings.SERVER_URL}/kingdom/map', timeout=15)
            if resp.status_code != 200:
                self._error = 'Failed to load kingdom map'
                logger.error(f'Kingdom map load failed: {resp.status_code}')
                self._loading = False
                return
            data = resp.json()
            self._map_data = data
            self._cooldown = data.get('conquer_cooldown_remaining', 0)

            lands = data.get('lands', [])
            if self._hex_map is None:
                self._hex_map = HexMap(lands, self.window, viewport_rect=self._map_viewport_rect)
            else:
                self._hex_map.set_viewport(self._map_viewport_rect)
                self._hex_map.update_data(lands)

            # Position minimap inside the framed map viewport (bottom-right)
            mm_w = settings.MINIMAP_W
            mm_h = settings.MINIMAP_H
            self._hex_map.minimap_origin = (
                self._map_viewport_rect.right - mm_w - settings.MINIMAP_MARGIN,
                self._map_viewport_rect.bottom - mm_h - settings.MINIMAP_MARGIN,
            )

            # On enter/reload, focus on the center of the player's largest
            # connected kingdom so the map opens where most owned lands are.
            self._focus_largest_kingdom_component()

            self._loading = False
            logger.debug(f'Kingdom map loaded: {len(lands)} lands')
            self._load_activity()
        except Exception as e:
            self._error = 'Connection error'
            logger.error(f'Kingdom map load error: {e}')
            self._loading = False

    def _focus_largest_kingdom_component(self):
        """Center map camera on the largest connected component of owned lands."""
        if not self._hex_map or not isinstance(self._map_data, dict):
            return None

        my_kingdom = self._map_data.get('my_kingdom') or {}
        components = my_kingdom.get('components') or []
        if not components:
            return None

        best_land_ids = None
        best_key = None
        for component in components:
            land_ids = [
                land_id for land_id in (component.get('land_ids') or [])
                if isinstance(land_id, int)
            ]
            if not land_ids:
                continue
            size = int(component.get('size') or len(land_ids))
            key = (size, -min(land_ids))
            if best_key is None or key > best_key:
                best_key = key
                best_land_ids = land_ids

        if not best_land_ids:
            return None

        if hasattr(self._hex_map, 'focus_lands'):
            return self._hex_map.focus_lands(best_land_ids)

        # Backward-compatible fallback for older HexMap instances.
        return self._hex_map.focus_land(best_land_ids[0])

    def _load_notifications(self):
        """Fetch unseen kingdom notifications for attack and defence outcomes."""
        try:
            resp = requests.get(
                f'{settings.SERVER_URL}/kingdom/notifications', timeout=10)
            if resp.status_code == 200:
                self._notifications = resp.json().get('notifications', [])
            else:
                self._notifications = []
        except Exception as e:
            logger.warning(f'Failed to load notifications: {e}')
            self._notifications = []

    def _visible_notifications(self):
        """Return notification rows that should still appear in Alerts."""
        return [n for n in getattr(self, '_notifications', []) if not n.get('seen', False)]

    def _load_messages(self):
        """Fetch recent kingdom messages for the activity panel."""
        try:
            resp = requests.get(
                f'{settings.SERVER_URL}/kingdom/messages?limit=50', timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                self._messages = data.get('messages', [])
                self._message_unread_count = data.get('unread_count', 0)
            else:
                self._messages = []
                self._message_unread_count = 0
        except Exception as e:
            logger.warning(f'Failed to load kingdom messages: {e}')
            self._messages = []
            self._message_unread_count = 0

    def _load_activity(self):
        """Fetch unseen alerts and recent attack history for the activity panel."""
        self._load_notifications()
        try:
            resp = requests.get(
                f'{settings.SERVER_URL}/kingdom/attack_history?per_page=50', timeout=10)
            if resp.status_code == 200:
                self._attack_history = resp.json().get('history', [])
            else:
                self._attack_history = []
        except Exception as e:
            logger.warning(f'Failed to load attack history: {e}')
            self._attack_history = []
        self._load_messages()

    # ── Rendering ───────────────────────────────────────────────────

    def render(self):
        self._draw_menu_chrome()

        # Outer box
        _draw_panel(self.window, self._box_rect)

        # Title (centred inside box)
        tx = self._header_rect.x + (self._header_rect.w - self._title_surf.get_width()) // 2
        self.window.blit(self._title_surf, (tx, self._title_y))
        self._draw_info_bar()
        self._draw_map_frame()
        self._draw_activity_panel()

        if self._loading:
            txt = self._info_font.render('Loading kingdom map...', True,
                                         settings.KINGDOM_INFO_CLR)
            self.window.blit(txt, txt.get_rect(center=self._map_frame_rect.center))
        elif self._error:
            txt = self._info_font.render(self._error, True, (200, 80, 80))
            self.window.blit(txt, txt.get_rect(center=self._map_frame_rect.center))
        elif self._hex_map:
            self._hex_map.set_viewport(self._map_viewport_rect)
            self._hex_map.render()
            self._draw_nav_buttons()

        self._draw_close_x_button()

        # Modal layer
        if self._detail_box:
            self._detail_box.render()
        if self._message_compose:
            self._draw_message_compose()

        # Floating text (gold collect / level up) above modals' chrome
        now_ms = pygame.time.get_ticks()
        dt_ms = max(0, now_ms - getattr(self, '_floating_text_last_tick', now_ms))
        self._floating_text_last_tick = now_ms
        self._floating_text.update(dt_ms)
        self._floating_text.draw(self.window)

        self._draw_menu_overlay()

    def _draw_close_x_button(self):
        r = self._btn_close_rect
        mouse_pos = pygame.mouse.get_pos()
        hovered = r.collidepoint(mouse_pos)
        bg_clr = (80, 50, 25, 220) if hovered else (55, 35, 18, 200)
        border_clr = (180, 160, 120) if hovered else (120, 100, 70)
        txt_clr = (255, 240, 200) if hovered else (200, 180, 140)
        surf = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, bg_clr, surf.get_rect(), border_radius=4)
        pygame.draw.rect(surf, border_clr, surf.get_rect(), 1, border_radius=4)
        self.window.blit(surf, r.topleft)
        _xfont = settings.get_font(int(settings.FONT_SIZE * 0.85), bold=True)
        txt = _xfont.render('\u00d7', True, txt_clr)
        self.window.blit(txt, txt.get_rect(center=r.center))

    def _draw_map_frame(self):
        """Draw the dedicated map frame that owns map rendering and input."""
        r = self._map_frame_rect
        surf = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, settings.KINGDOM_MAP_FRAME_BG, surf.get_rect(), border_radius=8)
        self.window.blit(surf, r.topleft)
        pygame.draw.rect(self.window, settings.KINGDOM_MAP_FRAME_BORDER, r,
                         settings.KINGDOM_MAP_FRAME_BORDER_W, border_radius=8)

    def _activity_scroll_offsets_map(self):
        offsets = getattr(self, '_activity_scroll_offsets', None)
        if not isinstance(offsets, dict):
            offsets = {'alerts': 0, 'history': 0, 'messages': 0}
            self._activity_scroll_offsets = offsets
        return offsets

    def _activity_content_top(self):
        tab_y = self._activity_rect.y + 34
        tab_h = int(0.036 * _SH)
        return tab_y + tab_h + 10

    def _activity_visible_count(self):
        row_h = settings.KINGDOM_ACTIVITY_ROW_H
        available_h = self._activity_rect.bottom - 10 - self._activity_content_top()
        return max(1, available_h // row_h)

    def _activity_rows_for_tab(self, tab=None):
        tab = tab or self._activity_tab
        if tab == 'alerts':
            return self._visible_notifications(), 'No new kingdom alerts.'
        if tab == 'history':
            return getattr(self, '_attack_history', []), 'No attacks yet.'
        if tab == 'messages':
            return (getattr(self, '_messages', []),
                    'No kingdom messages yet. Click another player land and choose Message.')
        return [], 'Select a kingdom activity tab.'

    def _clamp_activity_scroll(self, tab=None, row_count=None, visible_count=None):
        tab = tab or self._activity_tab
        if row_count is None:
            rows, _empty = self._activity_rows_for_tab(tab)
            row_count = len(rows)
        if visible_count is None:
            visible_count = self._activity_visible_count()
        max_offset = max(0, int(row_count) - int(visible_count))
        offsets = self._activity_scroll_offsets_map()
        offset = max(0, min(int(offsets.get(tab, 0) or 0), max_offset))
        offsets[tab] = offset
        return offset

    def _scroll_activity_tab(self, delta_rows, tab=None):
        """Scroll the active activity tab by row count. Returns True if changed."""
        tab = tab or self._activity_tab
        rows, _empty = self._activity_rows_for_tab(tab)
        visible_count = self._activity_visible_count()
        max_offset = max(0, len(rows) - visible_count)
        offsets = self._activity_scroll_offsets_map()
        before = self._clamp_activity_scroll(tab, len(rows), visible_count)
        after = max(0, min(before + int(delta_rows), max_offset))
        offsets[tab] = after
        return after != before

    def _draw_activity_scrollbar(self, panel_rect, content_top, max_bottom,
                                 row_count, visible_count, offset):
        if row_count <= visible_count:
            self._activity_scrollbar_rect = None
            return
        track_h = max(1, max_bottom - content_top - 2)
        track = pygame.Rect(panel_rect.right - 14, content_top, 5, track_h)
        self._activity_scrollbar_rect = track
        pygame.draw.rect(self.window, (48, 44, 58), track, border_radius=3)
        knob_h = max(14, int(track.h * (visible_count / float(row_count))))
        max_offset = max(1, row_count - visible_count)
        knob_y = track.y + int((track.h - knob_h) * (offset / float(max_offset)))
        knob = pygame.Rect(track.x, knob_y, track.w, knob_h)
        pygame.draw.rect(self.window, settings.KINGDOM_ACTIVITY_BORDER, knob, border_radius=3)

    def _draw_activity_panel(self):
        """Draw the right-side activity panel with alert/history tabs."""
        r = self._activity_rect
        self._activity_tab_rects = {}
        self._activity_row_rects = []
        self._activity_scrollbar_rect = None
        self._mark_read_rect = None
        self._mark_read_kind = None

        surf = pygame.Surface((r.w, r.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, settings.KINGDOM_ACTIVITY_BG, surf.get_rect(), border_radius=8)
        self.window.blit(surf, r.topleft)
        pygame.draw.rect(self.window, settings.KINGDOM_ACTIVITY_BORDER, r, 1, border_radius=8)

        old_clip = self.window.get_clip()
        self.window.set_clip(r)
        try:
            title = self._activity_title_font.render('Kingdom Activity', True, settings.KINGDOM_INFO_CLR)
            self.window.blit(title, (r.x + 10, r.y + 8))

            alert_rows = self._visible_notifications()

            msg_label = 'Messages'
            if self._message_unread_count:
                msg_label = f'Messages ({self._message_unread_count})'
            tabs = [('alerts', f'Alerts ({len(alert_rows)})'),
                    ('history', 'History'),
                    ('messages', msg_label)]
            tab_y = r.y + 34
            tab_h = int(0.036 * _SH)
            tab_gap = 4
            tab_w = (r.w - 20 - tab_gap * (len(tabs) - 1)) // len(tabs)
            for i, (key, label) in enumerate(tabs):
                tr = pygame.Rect(r.x + 10 + i * (tab_w + tab_gap), tab_y, tab_w, tab_h)
                self._activity_tab_rects[key] = tr
                bg = (settings.KINGDOM_ACTIVITY_TAB_ACTIVE_BG
                      if self._activity_tab == key else settings.KINGDOM_ACTIVITY_TAB_BG)
                pygame.draw.rect(self.window, bg, tr, border_radius=5)
                pygame.draw.rect(self.window, settings.KINGDOM_ACTIVITY_BORDER, tr, 1, border_radius=5)
                label = self._fit_text(label, self._activity_small_font, tr.w - 8)
                lbl = self._activity_small_font.render(label, True, settings.KINGDOM_ACTIVITY_TEXT_CLR)
                self.window.blit(lbl, lbl.get_rect(center=tr.center))

            content_top = self._activity_content_top()
            rows, empty = self._activity_rows_for_tab(self._activity_tab)
            if self._activity_tab == 'alerts' and rows:
                self._mark_read_rect = pygame.Rect(r.right - 102, r.y + 8, 88, 20)
                self._mark_read_kind = 'alerts'
                pygame.draw.rect(self.window, settings.KINGDOM_ACTIVITY_TAB_BG,
                                 self._mark_read_rect, border_radius=5)
                pygame.draw.rect(self.window, settings.KINGDOM_ACTIVITY_BORDER,
                                 self._mark_read_rect, 1, border_radius=5)
                mark = self._activity_small_font.render('Mark read', True, settings.KINGDOM_ACTIVITY_TEXT_CLR)
                self.window.blit(mark, mark.get_rect(center=self._mark_read_rect.center))
            elif self._activity_tab == 'messages' and self._message_unread_count:
                self._mark_read_rect = pygame.Rect(r.right - 102, r.y + 8, 88, 20)
                self._mark_read_kind = 'messages'
                pygame.draw.rect(self.window, settings.KINGDOM_ACTIVITY_TAB_BG,
                                 self._mark_read_rect, border_radius=5)
                pygame.draw.rect(self.window, settings.KINGDOM_ACTIVITY_BORDER,
                                 self._mark_read_rect, 1, border_radius=5)
                mark = self._activity_small_font.render('Mark read', True, settings.KINGDOM_ACTIVITY_TEXT_CLR)
                self.window.blit(mark, mark.get_rect(center=self._mark_read_rect.center))

            if not rows:
                empty_rect = pygame.Rect(r.x + 12, content_top + 8,
                                         r.w - 24, r.bottom - content_top - 18)
                self._draw_wrapped_text(empty, self._activity_font,
                                        settings.KINGDOM_ACTIVITY_DIM_CLR, empty_rect)
                return

            row_h = settings.KINGDOM_ACTIVITY_ROW_H
            y = content_top
            max_bottom = r.bottom - 10
            visible_count = self._activity_visible_count()
            offset = self._clamp_activity_scroll(self._activity_tab, len(rows), visible_count)
            scrolling = len(rows) > visible_count
            row_right_pad = 30 if scrolling else 20
            self._draw_activity_scrollbar(r, content_top, max_bottom,
                                          len(rows), visible_count, offset)
            for item in rows[offset:offset + visible_count]:
                if y + row_h > max_bottom:
                    break
                rr = pygame.Rect(r.x + 10, y, r.w - row_right_pad, row_h - 4)
                self._activity_row_rects.append((rr, item))
                self._draw_activity_row(rr, item)
                y += row_h
        finally:
            self.window.set_clip(old_clip)

    def _draw_activity_row(self, rect, item):
        pygame.draw.rect(self.window, settings.KINGDOM_ACTIVITY_ROW_BG, rect, border_radius=6)
        pygame.draw.rect(self.window, (90, 85, 105), rect, 1, border_radius=6)
        title, detail, good = self._format_activity_item(item)
        max_w = rect.w - 16
        title = self._fit_text(title, self._activity_font, max_w)
        detail = self._fit_text(detail, self._activity_small_font, max_w)
        if self._is_message_item(item):
            unread = (item.get('recipient_user_id') == self._current_user_id()
                      and not item.get('seen_by_recipient'))
            title_clr = settings.KINGDOM_INFO_CLR if unread else settings.KINGDOM_ACTIVITY_TEXT_CLR
        elif item.get('activity_tone') == 'neutral':
            title_clr = settings.KINGDOM_ACTIVITY_TEXT_CLR
        else:
            title_clr = (settings.KINGDOM_ACTIVITY_GOOD_CLR if good else settings.KINGDOM_ACTIVITY_BAD_CLR)
        title_surf = self._activity_font.render(title, True, title_clr)
        detail_surf = self._activity_small_font.render(detail, True, settings.KINGDOM_ACTIVITY_TEXT_CLR)
        self.window.blit(title_surf, (rect.x + 8, rect.y + 6))
        self.window.blit(detail_surf, (rect.x + 8, rect.y + 26))

        land = self._activity_small_font.render(self._activity_land_label(item), True,
                                                settings.KINGDOM_ACTIVITY_DIM_CLR)
        self.window.blit(land, (rect.x + 8, rect.bottom - land.get_height() - 5))

    def _draw_wrapped_text(self, text, font, color, rect, line_gap=2):
        """Draw text wrapped inside rect and clipped to rect bounds."""
        old_clip = self.window.get_clip()
        self.window.set_clip(rect.clip(old_clip))
        try:
            line_h = font.get_height() + line_gap
            max_lines = max(1, rect.h // line_h)
            for i, line in enumerate(self._wrap_text(text, font, rect.w, max_lines=max_lines)):
                surf = font.render(line, True, color)
                self.window.blit(surf, (rect.x, rect.y + i * line_h))
        finally:
            self.window.set_clip(old_clip)

    def _wrap_text(self, text, font, max_width, max_lines=None):
        """Return text lines that fit max_width, adding ellipsis if truncated."""
        words = str(text).split()
        if not words:
            return ['']
        lines = []
        current = ''
        for word in words:
            candidate = word if not current else f'{current} {word}'
            if font.size(candidate)[0] <= max_width:
                current = candidate
                continue
            if current:
                lines.append(current)
                current = word
                if font.size(current)[0] > max_width:
                    lines.append(self._fit_text(current, font, max_width))
                    current = ''
            else:
                lines.append(self._fit_text(word, font, max_width))
                current = ''
            if max_lines and len(lines) >= max_lines:
                break
        if current and (not max_lines or len(lines) < max_lines):
            lines.append(current)
        if max_lines and len(lines) >= max_lines and words:
            lines[-1] = self._fit_text(lines[-1], font, max_width)
        return lines or ['']

    def _fit_text(self, text, font, max_width):
        if font.size(text)[0] <= max_width:
            return text
        ellipsis = '...'
        clipped = text
        while clipped and font.size(clipped + ellipsis)[0] > max_width:
            clipped = clipped[:-1]
        return (clipped + ellipsis) if clipped else ellipsis

    def _format_activity_item(self, item):
        if item.get('activity_title') is not None or item.get('activity_detail') is not None:
            title = item.get('activity_title') or 'Kingdom event'
            detail = item.get('activity_detail') or ''
            tone = item.get('activity_tone') or 'neutral'
            return title, detail, tone != 'bad'
        if self._is_message_item(item):
            return self._format_message_item(item)
        if self._is_kingdom_event_item(item):
            return self._format_kingdom_event_item(item)
        attacker = item.get('attacker_username') or item.get('attacker_name') or 'Unknown'
        defender = item.get('defender_username') or 'AI'
        result = item.get('result')
        role = item.get('role')
        current_user_id = self._current_user_id()
        is_attacker = current_user_id is not None and item.get('attacker_user_id') == current_user_id
        is_defender = current_user_id is not None and item.get('defender_user_id') == current_user_id
        is_attacker_perspective = role == 'attacker' if role else is_attacker
        is_defender_perspective = role == 'defender' if role else is_defender
        if result == 'attacker_won':
            if is_defender_perspective:
                title = f'{attacker} conquered your land'
                deleted = item.get('kingdom_deleted_name')
                detail = (f'{deleted} had no lands left and was dissolved.' if deleted
                          else (self._loot_detail(item, 'Loot lost')
                          or self._card_pair_detail(
                              item, 'card_won_suit', 'card_won_rank', 'Loot lost')
                          or self._card_pair_detail(
                              item, 'card_lost_suit', 'card_lost_rank', 'Loot lost')
                          or 'Land ownership changed.'))
                return title, detail, False
            if is_attacker_perspective:
                title = f'You conquered {defender}'
                detail = self._card_detail(item, won=True) or 'Attack succeeded.'
                return title, detail, True
            title = f'{attacker} conquered {defender}'
            detail = self._card_detail(item, won=True) or 'Attack succeeded.'
            return title, detail, True
        if result == 'defender_won':
            if is_defender_perspective:
                title = f'{attacker} failed to conquer you'
                detail = (
                    self._loot_detail(item, 'Loot gained')
                    or self._card_pair_detail(
                        item, 'card_lost_suit', 'card_lost_rank', 'Loot gained')
                    or self._card_pair_detail(
                        item, 'card_won_suit', 'card_won_rank', 'Loot gained')
                    or 'Your defence held.'
                )
                return title, detail, True
            if is_attacker_perspective:
                title = f'Your attack on {defender} failed'
                detail = self._card_detail(item, lost=True) or 'Attack failed.'
                return title, detail, False
            title = f'{attacker} failed against {defender}'
            detail = self._card_detail(item, lost=True) or 'Attack failed.'
            return title, detail, False
        if is_defender_perspective:
            title = f'{attacker} failed to conquer you'
        elif is_attacker_perspective:
            title = f'Attack on {defender} updated'
        else:
            title = f'{attacker} vs {defender}'
        detail = 'Battle result updated.'
        return title, detail, False

    def _is_message_item(self, item):
        return 'sender_user_id' in item and 'recipient_user_id' in item and 'message' in item

    def _format_message_item(self, item):
        current_user_id = self._current_user_id()
        is_sent = item.get('sender_user_id') == current_user_id
        other = item.get('recipient_username') if is_sent else item.get('sender_username')
        other = other or 'Unknown'
        title = f'To {other}' if is_sent else f'From {other}'
        detail = item.get('message') or ''
        return title, detail, True

    def _is_kingdom_event_item(self, item):
        """True for KingdomNotification rows (have ``kind`` + ``payload``)."""
        return ('kind' in item and 'payload' in item
                and 'attacker_user_id' not in item
                and 'sender_user_id' not in item)

    def _format_kingdom_event_item(self, item):
        kind = item.get('kind') or ''
        payload = item.get('payload') or {}
        if kind == 'xp_gained':
            amount = int(payload.get('amount') or 0)
            reason = payload.get('reason') or 'conquer'
            level = int(payload.get('level') or 0)
            title = f'+{amount} XP gained'
            detail = f'Kingdom level {level} ({reason}).' if level else f'Earned from {reason}.'
            return title, detail, True
        if kind == 'level_up':
            new_level = int(payload.get('new_level') or 0)
            sp = int(payload.get('sp_gained') or 0)
            title = f'Kingdom reached level {new_level}!'
            detail = f'+{sp} skill point{"s" if sp != 1 else ""}.' if sp else 'Level up!'
            return title, detail, True
        if kind == 'kingdoms_merged':
            absorbed = payload.get('absorbed_kingdom_name') or 'A kingdom'
            lands = int(payload.get('absorbed_lands') or 0)
            xp = int(payload.get('xp_awarded') or 0)
            title = 'Kingdoms merged'
            detail = f'{absorbed} absorbed ({lands} lands, +{xp} XP).'
            return title, detail, True
        if kind == 'card_looted':
            rank = payload.get('rank') or '?'
            suit = payload.get('suit') or 'card'
            defender = payload.get('defender_name')
            if not defender and payload.get('is_ai_defender'):
                defender = 'AI defender'
            title = 'Card looted'
            detail = f'{rank} of {suit} lost to {defender or "the defender"}.'
            return title, detail, False
        if kind == 'shield_expired':
            name = payload.get('kingdom_name') or 'Your kingdom'
            title = 'Shield expired'
            detail = f'{name} can be attacked again.'
            return title, detail, False
        if kind == 'kingdom_dissolved':
            name = payload.get('kingdom_name') or 'Your kingdom'
            title = 'Kingdom dissolved'
            detail = f'{name} had no lands left.'
            return title, detail, False
        if kind == 'skill_downgraded':
            skill = payload.get('skill') or 'A skill'
            title = 'Skill downgraded'
            detail = f'{skill} level decreased.'
            return title, detail, False
        # Generic fallback
        title = (kind or 'Kingdom event').replace('_', ' ').capitalize()
        detail = ''
        return title, detail, True

    def _current_user_id(self):
        data = getattr(self.state, 'user_dict', None) or {}
        return data.get('id') or data.get('user_id')

    def _card_detail(self, item, won=False, lost=False):
        if won:
            return self._loot_detail(item, 'Loot gained') or self._card_pair_detail(
                item, 'card_won_suit', 'card_won_rank', 'Loot gained')
        if lost:
            return self._loot_detail(item, 'Loot lost') or self._card_pair_detail(
                item, 'card_lost_suit', 'card_lost_rank', 'Loot lost')
        return ''

    def _loot_detail(self, item, label):
        cards = item.get('loot_cards') or []
        count = int(item.get('loot_card_count') or len(cards or []))
        if not count:
            return ''
        first = cards[0] if cards else {}
        first_label = ''
        if isinstance(first, dict) and first.get('rank') and first.get('suit'):
            first_label = f" ({first.get('rank')} of {first.get('suit')}"
            if count > 1:
                first_label += f' + {count - 1} more'
            first_label += ')'
        noun = 'card' if count == 1 else 'cards'
        return f'{label}: {count} {noun}{first_label}'

    def _card_pair_detail(self, item, suit_key, rank_key, label):
        suit = item.get(suit_key)
        rank = item.get(rank_key)
        if suit and rank:
            return f'{label}: {rank} of {suit}'
        return ''

    def _activity_land_label(self, item):
        if item.get('activity_land_label'):
            return str(item.get('activity_land_label'))
        col = item.get('land_col')
        row = item.get('land_row')
        land_id = item.get('land_id')
        payload = item.get('payload') if isinstance(item.get('payload'), dict) else {}
        if col is None:
            col = payload.get('land_col')
        if row is None:
            row = payload.get('land_row')
        if land_id is None:
            land_id = payload.get('land_id')
        if col is not None and row is not None:
            return f'Land ({col}, {row})'
        if land_id is not None:
            return f'Land #{land_id}'
        if self._is_kingdom_event_item(item):
            kingdom_name = payload.get('kingdom_name') or payload.get('absorbed_kingdom_name')
            return kingdom_name or 'Kingdom event'
        return 'Kingdom land'

    def _draw_info_bar(self):
        """Draw production rate / lands count bar at top of box, below title."""
        # Reset clickable rect each frame
        self._collect_all_rect = None
        self._collect_all_enabled = False
        if not self._map_data:
            return

        rate = self._map_data.get('my_total_gold_rate', 0)
        effective_rate = self._map_data.get('my_effective_gold_rate', rate)
        count = self._map_data.get('my_lands_count', 0)

        # Aggregate vault stats across all owned kingdoms
        my_kingdoms = self._map_data.get('my_kingdoms') or []
        num_kingdoms = len(my_kingdoms)
        pending_total = 0.0
        collectable_total = 0
        collectable_main_boosters = 0
        collectable_side_boosters = 0
        any_full = False
        any_near_full = False
        near_ratio = float(getattr(settings, 'KINGDOM_VAULT_NEAR_FULL_RATIO', 0.80))
        for k in my_kingdoms:
            pending = float(k.get('pending_gold') or 0.0)
            cap = float(k.get('vault_cap') or 0.0)
            pending_total += pending
            collectable_total += int(pending)
            if cap > 0:
                ratio = pending / cap if cap else 0
                if ratio >= 0.999:
                    any_full = True
                elif ratio >= near_ratio:
                    any_near_full = True
            production = k.get('production') if isinstance(k.get('production'), dict) else {}
            main_item = production.get('main_booster') if isinstance(production.get('main_booster'), dict) else {}
            side_item = production.get('side_booster') if isinstance(production.get('side_booster'), dict) else {}
            main_pending = int(main_item.get('pending', k.get('pending_main_boosters') or 0) or 0)
            side_pending = int(side_item.get('pending', k.get('pending_side_boosters') or 0) or 0)
            collectable_main_boosters += main_pending
            collectable_side_boosters += side_pending
            # NB: ``any_full`` only signals "gold production is stalled".
            # Booster packs being ready is normal/desired, not a warning,
            # so we deliberately do not set ``any_full`` for boosters.

        base_rate = float(rate or 0)
        bonus_rate = max(0.0, float(effective_rate or 0) - base_rate)
        header_base = (
            f'kingdoms: {num_kingdoms}  '
            f'lands: {int(count or 0)}  '
            f'gold: {base_rate:.1f}/hr'
        )
        if self._cooldown > 0:
            hours = self._cooldown // 3600
            mins = (self._cooldown % 3600) // 60
            cooldown_text = f'  conquer cooldown: {hours}h {mins}m'
        else:
            cooldown_text = ''

        # Color gold-rate-bearing text red when any vault is full (production stalled)
        info_clr = (220, 90, 90) if any_full else settings.KINGDOM_INFO_CLR
        bonus_clr = getattr(settings, 'KINGDOM_CONFIG_GOOD_CLR', (132, 220, 142))
        segments = [
            self._info_font.render(header_base, True, info_clr),
            self._info_font.render(f' +{bonus_rate:.1f}', True, bonus_clr),
        ]
        if cooldown_text:
            segments.append(self._info_font.render(cooldown_text, True, info_clr))
        px = settings.KINGDOM_INFO_PAD_X
        py = settings.KINGDOM_INFO_PAD_Y
        text_w = sum(s.get_width() for s in segments)
        text_h = max((s.get_height() for s in segments), default=0)
        bw = text_w + px * 2
        bh = text_h + py * 2

        box = pygame.Surface((bw, bh), pygame.SRCALPHA)
        box.fill(settings.KINGDOM_INFO_BG_CLR)
        bar_x = self._header_rect.x + (self._header_rect.w - bw) // 2
        bar_y = self._header_rect.y + self._title_surf.get_height() + int(0.006 * _SH)
        self.window.blit(box, (bar_x, bar_y))
        tx = bar_x + px
        ty = bar_y + py
        for surf in segments:
            self.window.blit(surf, (tx, ty + (text_h - surf.get_height()) // 2))
            tx += surf.get_width()

        # Collect All button (right of info bar)
        if my_kingdoms:
            # Server collects ``int(pending)`` per kingdom, then sums those
            # integers. Mirror that here so the button amount reflects what
            # would actually be collected right now.
            collectable = (
                collectable_total > 0
                or collectable_main_boosters > 0
                or collectable_side_boosters > 0
            )
            parts = []
            if collectable_total > 0:
                parts.append(f'{collectable_total}g')
            if collectable_main_boosters:
                parts.append(f'{collectable_main_boosters} main')
            if collectable_side_boosters:
                parts.append(f'{collectable_side_boosters} side')
            label = 'Collect All' if not parts else 'Collect All: ' + ' + '.join(parts)
            if any_full:
                label += '  (FULL!)'
            btn_font = self._nav_font
            btn_surf = btn_font.render(label, True, (240, 230, 180))
            bpx = int(0.012 * _SW)
            bpy = int(0.006 * _SH)
            btn_w = btn_surf.get_width() + bpx * 2
            btn_h = max(bh, btn_surf.get_height() + bpy * 2)
            btn_x = bar_x + bw + int(0.010 * _SW)
            # Keep button inside header area; if overflow, place to right of title within header
            max_right = self._header_rect.right - self._btn_close_rect.w - int(0.012 * _SW)
            if btn_x + btn_w > max_right:
                btn_x = max(self._header_rect.x, max_right - btn_w)
            btn_y = bar_y + (bh - btn_h) // 2
            rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)

            mx, my = pygame.mouse.get_pos()
            hovered = rect.collidepoint(mx, my) and collectable
            if not collectable:
                bg = (42, 40, 42, 205)
                border = (120, 110, 100)
            elif any_full:
                bg = (140, 50, 50, 230) if hovered else (110, 40, 40, 210)
                border = (220, 120, 120)
            elif any_near_full:
                bg = (130, 110, 50, 230) if hovered else (100, 85, 40, 210)
                border = (220, 200, 120)
            else:
                bg = (60, 80, 60, 230) if hovered else (45, 60, 45, 210)
                border = (160, 200, 160)
            bsurf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
            pygame.draw.rect(bsurf, bg, bsurf.get_rect(), border_radius=6)
            pygame.draw.rect(bsurf, border, bsurf.get_rect(), 1, border_radius=6)
            self.window.blit(bsurf, rect.topleft)
            self.window.blit(btn_surf, btn_surf.get_rect(center=rect.center))
            self._collect_all_rect = rect
            self._collect_all_enabled = collectable

    def _draw_nav_buttons(self):
        """Draw zoom +/- buttons in the bottom-left corner."""
        mx, my = pygame.mouse.get_pos()
        for key, rect in self._nav_rects.items():
            hovered = rect.collidepoint(mx, my)
            surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
            pygame.draw.rect(surf, settings.NAV_BTN_BG_CLR, surf.get_rect(),
                             border_radius=4)
            pygame.draw.rect(surf, settings.NAV_BTN_BORDER_CLR, surf.get_rect(), 1,
                             border_radius=4)
            self.window.blit(surf, rect.topleft)
            clr = settings.NAV_BTN_HOVER_CLR if hovered else settings.NAV_BTN_TEXT_CLR
            label = self._nav_labels.get(key, '?')
            lbl = self._nav_font.render(label, True, clr)
            self.window.blit(lbl, lbl.get_rect(center=rect.center))

    # ── Update / events ─────────────────────────────────────────────

    def update(self, events):
        super().update()
        self._update_icon_buttons()

        # Auto-load map on first frame (or re-enter)
        now = pygame.time.get_ticks()
        if self._hex_map is None and not self._loading and (now - self._last_load_tick > 2000):
            self._last_load_tick = now
            self._load_map()

        if self._detail_box:
            self._detail_box.update()

    def handle_events(self, events):
        super().handle_events(events)

        for event in events:
            # Icon buttons (settings, home, logout) — highest priority
            if self._handle_icon_events(event):
                continue

            # Message composer captures normal kingdom input.
            if self._message_compose:
                self._handle_message_compose_event(event)
                continue

            # X close button
            if (event.type == MOUSEBUTTONUP and event.button == 1
                    and not self.dialogue_box
                    and not self._detail_box
                    and self._btn_close_rect.collidepoint(event.pos)):
                self.state.screen = 'game_menu'
                return

            # Click outside content box → back to game menu
            if (event.type == MOUSEBUTTONUP and event.button == 1
                    and not self.dialogue_box
                    and not self._detail_box
                    and not (self._hex_map and self._hex_map.is_drag_release(event))
                    and not self._box_rect.collidepoint(event.pos)):
                self.state.screen = 'game_menu'
                return

            # If detail box is open, route events there
            if self._detail_box:
                action = self._detail_box.handle_event(event)
                if action == 'conquer':
                    land_id = self._detail_box.tile.land_id if self._detail_box else '?'
                    logger.info(f'Conquer requested for land {land_id}')
                    self._detail_box = None
                elif action == 'defence':
                    land_id = self._detail_box.tile.land_id if self._detail_box else '?'
                    logger.info(f'Defence config requested for land {land_id}')
                    self._detail_box = None
                elif action == 'message':
                    self._detail_box = None
                elif action == 'close':
                    self._detail_box = None
                continue

            if event.type == MOUSEWHEEL:
                if self._activity_rect.collidepoint(pygame.mouse.get_pos()):
                    self._scroll_activity_tab(-getattr(event, 'y', 0))
                    continue

            if event.type == MOUSEBUTTONUP and event.button == 1:
                if self._handle_activity_click(event.pos):
                    continue

                # Collect All gold button (info bar)
                if (self._collect_all_rect
                    and getattr(self, '_collect_all_enabled', False)
                        and self._collect_all_rect.collidepoint(event.pos)):
                    self._collect_all_gold()
                    continue

                # Nav buttons
                handled_nav = False
                for key, rect in self._nav_rects.items():
                    if rect.collidepoint(event.pos):
                        if key == 'zoom_in' and self._hex_map:
                            self._hex_map.zoom_in()
                        elif key == 'zoom_out' and self._hex_map:
                            self._hex_map.zoom_out()
                        handled_nav = True
                        break
                if handled_nav:
                    continue

                # Minimap click
                if self._hex_map and self._hex_map.handle_minimap_click(*event.pos):
                    continue

            # Hex map events (pan, zoom wheel, click)
            if self._hex_map and not self._detail_box:
                clicked_tile = self._hex_map.handle_event(event)
                if clicked_tile:
                    self._open_detail(clicked_tile)

        # Keyboard pan (continuous)
        keys = pygame.key.get_pressed()
        if self._hex_map and not self._detail_box:
            pan_speed = 8 / self._hex_map.zoom
            if keys[K_LEFT] or keys[K_a]:
                self._hex_map.pan(-pan_speed, 0)
            if keys[K_RIGHT] or keys[K_d]:
                self._hex_map.pan(pan_speed, 0)
            if keys[K_UP] or keys[K_w]:
                self._hex_map.pan(0, -pan_speed)
            if keys[K_DOWN] or keys[K_s]:
                self._hex_map.pan(0, pan_speed)

        if keys[K_ESCAPE] and not self._detail_box:
            self.state.screen = 'game_menu'

    def _collect_all_gold(self):
        """POST to collect all kingdom production and spawn feedback."""
        if not self._collect_all_rect:
            return
        try:
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/collect_production_all', timeout=15)
            if resp.status_code != 200:
                logger.error(f'collect_production_all failed: {resp.status_code}')
                return
            data = resp.json() or {}
        except Exception as exc:
            logger.error(f'collect_production_all error: {exc}')
            return

        gold_after = data.get('gold', data.get('total_gold'))
        total_collected = int(round(float(
            data.get('collected_gold_total', data.get('collected_total', data.get('collected') or 0))
        )))
        main_collected = int(data.get('collected_main_boosters_total', 0) or 0)
        side_collected = int(data.get('collected_side_boosters_total', 0) or 0)
        if total_collected > 0 and hasattr(self, '_suppress_next_gold_floater'):
            # Keep collect feedback anchored to the clicked Collect-All button
            # instead of duplicating it at the top-left HUD gold widget.
            self._suppress_next_gold_floater()
        if gold_after is not None and getattr(self.state, 'user_dict', None) is not None:
            self.state.user_dict['gold'] = int(gold_after)
        if getattr(self.state, 'user_dict', None) is not None:
            if 'booster_packs' in data:
                self.state.user_dict['booster_packs'] = int(data.get('booster_packs') or 0)
            if 'booster_packs_side' in data:
                self.state.user_dict['booster_packs_side'] = int(data.get('booster_packs_side') or 0)

        breakdown = data.get('kingdoms') or []
        if total_collected <= 0 and breakdown:
            total_collected = sum(
                int(round(float(entry.get('collected_gold', entry.get('collected') or 0) or 0)))
                for entry in breakdown
            )
            main_collected = sum(int(entry.get('collected_main_boosters') or 0)
                                 for entry in breakdown)
            side_collected = sum(int(entry.get('collected_side_boosters') or 0)
                                 for entry in breakdown)
        center = self._collect_all_rect.center
        rise_px = int(getattr(settings, 'COLLECT_FLOAT_RISE_PX',
                              int(0.07 * _SH)))
        duration = int(getattr(settings, 'COLLECT_FLOAT_DURATION_MS', 900))
        gold_clr = getattr(settings, 'COLLECT_FLOAT_GOLD_CLR', (255, 220, 90))
        if total_collected > 0:
            self._floating_text.add(FloatingText(
                f'+{total_collected}g',
                center,
                color=gold_clr,
                duration_ms=duration,
                rise_px=rise_px,
                font=self._collect_float_font,
            ))
        if main_collected or side_collected:
            parts = []
            if main_collected:
                parts.append(f'+{main_collected} main booster')
            if side_collected:
                parts.append(f'+{side_collected} side booster')
            if hasattr(self.state, 'set_msg'):
                self.state.set_msg('Collected ' + ', '.join(parts))
        # Refresh map data so vault bars / pending totals update.
        # Reset the floater tick after the blocking reload so network latency
        # does not instantly age out the newly added burst.
        self._load_map()
        self._floating_text_last_tick = pygame.time.get_ticks()

    def _handle_activity_click(self, pos):
        """Handle clicks in the right activity panel. Returns True if handled."""
        if not self._activity_rect.collidepoint(pos):
            return False
        for key, rect in self._activity_tab_rects.items():
            if rect.collidepoint(pos):
                self._activity_tab = key
                self._clamp_activity_scroll(key)
                return True
        if self._mark_read_rect and self._mark_read_rect.collidepoint(pos):
            if self._mark_read_kind == 'messages':
                self._mark_messages_seen()
            else:
                self._mark_notifications_seen()
            return True
        if self._activity_scrollbar_rect and self._activity_scrollbar_rect.collidepoint(pos):
            rows, _empty = self._activity_rows_for_tab(self._activity_tab)
            visible = self._activity_visible_count()
            offset = self._clamp_activity_scroll(self._activity_tab, len(rows), visible)
            direction = -visible if pos[1] < self._activity_scrollbar_rect.centery else visible
            self._scroll_activity_tab(direction)
            if offset == self._activity_scroll_offsets_map().get(self._activity_tab, 0):
                # Keep the click consumed even if the list was already at an edge.
                return True
            return True
        for rect, item in self._activity_row_rects:
            if rect.collidepoint(pos):
                if self._is_message_item(item):
                    self._open_reply_to_message(item)
                    return True
                land_id = item.get('land_id')
                if land_id and self._hex_map:
                    tile = self._hex_map.focus_land(land_id)
                    if tile:
                        self.state.set_msg(f'Focused {self._activity_land_label(item)}')
                return True
        return True

    # ── Kingdom messages ─────────────────────────────────────────────────────────

    def _open_message_compose(self, recipient_user_id, recipient_username, land_id=None):
        """Open the message composer for a kingdom user."""
        if not recipient_user_id:
            self.state.set_msg('Cannot message AI defenders.')
            return
        if recipient_user_id == self._current_user_id():
            self.state.set_msg('You cannot message yourself.')
            return
        self._message_compose = {
            'recipient_user_id': recipient_user_id,
            'recipient_username': recipient_username or 'Player',
            'land_id': land_id,
            'text': '',
            'error': '',
        }
        self._activity_tab = 'messages'

    def _open_reply_to_message(self, item):
        """Open composer to reply to the other participant in a message row."""
        current_user_id = self._current_user_id()
        if item.get('sender_user_id') == current_user_id:
            recipient_user_id = item.get('recipient_user_id')
            recipient_username = item.get('recipient_username')
        else:
            recipient_user_id = item.get('sender_user_id')
            recipient_username = item.get('sender_username')
        self._open_message_compose(
            recipient_user_id,
            recipient_username,
            land_id=item.get('land_id'),
        )

    def _handle_message_compose_event(self, event):
        """Handle input for the message composer. Returns True when captured."""
        if not self._message_compose:
            return False
        if event.type == KEYDOWN:
            if event.key == K_ESCAPE:
                self._message_compose = None
            elif event.key == K_BACKSPACE:
                self._message_compose['text'] = self._message_compose.get('text', '')[:-1]
                self._message_compose['error'] = ''
            elif event.key == K_RETURN:
                self._send_kingdom_message()
            return True
        if event.type == pygame.TEXTINPUT:
            text = self._message_compose.get('text', '')
            if len(text) < 500:
                self._message_compose['text'] = (text + event.text)[:500]
                self._message_compose['error'] = ''
            return True
        if event.type == MOUSEBUTTONUP and event.button == 1:
            if self._message_cancel_rect and self._message_cancel_rect.collidepoint(event.pos):
                self._message_compose = None
                return True
            if self._message_send_rect and self._message_send_rect.collidepoint(event.pos):
                self._send_kingdom_message()
                return True
        return True

    def _send_kingdom_message(self):
        """Send the current composer text through the kingdom message endpoint."""
        if not self._message_compose:
            return False
        text = (self._message_compose.get('text') or '').strip()
        if not text:
            self._message_compose['error'] = 'Write a message first.'
            return False
        payload = {
            'recipient_user_id': self._message_compose.get('recipient_user_id'),
            'land_id': self._message_compose.get('land_id'),
            'message': text,
        }
        try:
            resp = requests.post(f'{settings.SERVER_URL}/kingdom/messages',
                                 json=payload, timeout=10)
            data = resp.json() if hasattr(resp, 'json') else {}
            if resp.status_code == 200 and data.get('success'):
                recipient = self._message_compose.get('recipient_username') or 'player'
                self._message_compose = None
                self._activity_tab = 'messages'
                self._load_messages()
                self.state.set_msg(f'Message sent to {recipient}.')
                return True
            self._message_compose['error'] = data.get('message', 'Message failed.')
        except Exception as e:
            logger.warning(f'Failed to send kingdom message: {e}')
            self._message_compose['error'] = 'Connection error.'
        return False

    def _draw_message_compose(self):
        """Draw a modal message composer."""
        sw, sh = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT
        overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 130))
        self.window.blit(overlay, (0, 0))

        box = pygame.Rect(0, 0, int(0.42 * sw), int(0.31 * sh))
        box.center = (sw // 2, sh // 2)
        surf = pygame.Surface((box.w, box.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, settings.KINGDOM_ACTIVITY_BG, surf.get_rect(), border_radius=8)
        self.window.blit(surf, box.topleft)
        pygame.draw.rect(self.window, settings.KINGDOM_ACTIVITY_BORDER, box, 1, border_radius=8)

        pad = int(0.018 * sh)
        y = box.y + pad
        recipient = self._message_compose.get('recipient_username') or 'Player'
        title = self._activity_title_font.render(f'Message {recipient}', True, settings.KINGDOM_INFO_CLR)
        self.window.blit(title, (box.x + pad, y))
        y += title.get_height() + 8

        land_id = self._message_compose.get('land_id')
        helper = 'Enter sends. Esc cancels.'
        if land_id:
            helper = f'About Land #{land_id}.  {helper}'
        helper_surf = self._activity_small_font.render(helper, True, settings.KINGDOM_ACTIVITY_DIM_CLR)
        self.window.blit(helper_surf, (box.x + pad, y))
        y += helper_surf.get_height() + 10

        self._message_input_rect = pygame.Rect(
            box.x + pad,
            y,
            box.w - 2 * pad,
            int(0.072 * sh),
        )
        pygame.draw.rect(self.window, (18, 17, 24, 235), self._message_input_rect, border_radius=6)
        pygame.draw.rect(self.window, settings.KINGDOM_ACTIVITY_BORDER,
                         self._message_input_rect, 1, border_radius=6)
        text = self._message_compose.get('text') or ''
        placeholder = 'Write message...'
        display = text if text else placeholder
        color = settings.KINGDOM_ACTIVITY_TEXT_CLR if text else settings.KINGDOM_ACTIVITY_DIM_CLR
        input_text = self._fit_text(display, self._activity_font, self._message_input_rect.w - 16)
        input_surf = self._activity_font.render(input_text, True, color)
        self.window.blit(input_surf, (self._message_input_rect.x + 8,
                                      self._message_input_rect.centery - input_surf.get_height() // 2))

        if text and (pygame.time.get_ticks() // 500) % 2 == 0:
            cursor_x = self._message_input_rect.x + 10 + min(
                self._activity_font.size(text)[0], self._message_input_rect.w - 24)
            pygame.draw.line(self.window, settings.KINGDOM_ACTIVITY_TEXT_CLR,
                             (cursor_x, self._message_input_rect.y + 8),
                             (cursor_x, self._message_input_rect.bottom - 8), 1)

        y = self._message_input_rect.bottom + 8
        err = self._message_compose.get('error')
        if err:
            err_surf = self._activity_small_font.render(err, True, settings.KINGDOM_ACTIVITY_BAD_CLR)
            self.window.blit(err_surf, (box.x + pad, y))

        btn_w = int(0.095 * sw)
        btn_h = int(0.042 * sh)
        gap = int(0.012 * sw)
        by = box.bottom - pad - btn_h
        self._message_cancel_rect = pygame.Rect(box.right - pad - btn_w * 2 - gap, by, btn_w, btn_h)
        self._message_send_rect = pygame.Rect(box.right - pad - btn_w, by, btn_w, btn_h)
        self._draw_compose_button(self._message_cancel_rect, 'Cancel', active=False)
        self._draw_compose_button(self._message_send_rect, 'Send', active=True)

    def _draw_compose_button(self, rect, label, active=False):
        bg = settings.KINGDOM_ACTIVITY_TAB_ACTIVE_BG if active else settings.KINGDOM_ACTIVITY_TAB_BG
        pygame.draw.rect(self.window, bg, rect, border_radius=5)
        pygame.draw.rect(self.window, settings.KINGDOM_ACTIVITY_BORDER, rect, 1, border_radius=5)
        txt = self._activity_font.render(label, True, settings.KINGDOM_ACTIVITY_TEXT_CLR)
        self.window.blit(txt, txt.get_rect(center=rect.center))

    def _mark_notifications_seen(self):
        """Tell the server to mark current notifications as seen."""
        attack_log_ids = []
        kingdom_notification_ids = []
        for n in self._visible_notifications():
            nid = n.get('id')
            if not nid:
                continue
            if self._is_kingdom_event_item(n) or n.get('source') == 'kingdom_notification':
                kingdom_notification_ids.append(nid)
            else:
                attack_log_ids.append(nid)
        if not attack_log_ids and not kingdom_notification_ids:
            self._notifications = []
            self._activity_scroll_offsets_map()['alerts'] = 0
            return
        try:
            requests.post(
                f'{settings.SERVER_URL}/kingdom/notifications/mark_seen',
                json={
                    'attack_log_ids': attack_log_ids,
                    'kingdom_notification_ids': kingdom_notification_ids,
                }, timeout=10)
        except Exception as e:
            logger.warning(f'Failed to mark notifications seen: {e}')
        self._notifications = []
        self._activity_scroll_offsets_map()['alerts'] = 0

    def _mark_messages_seen(self):
        """Tell the server to mark received kingdom messages as read."""
        current_user_id = self._current_user_id()
        ids = [m.get('id') for m in self._messages
               if m.get('id') and m.get('recipient_user_id') == current_user_id]
        if not ids:
            self._message_unread_count = 0
            self._activity_scroll_offsets_map()['messages'] = 0
            return
        try:
            requests.post(
                f'{settings.SERVER_URL}/kingdom/messages/mark_seen',
                json={'message_ids': ids}, timeout=10)
        except Exception as e:
            logger.warning(f'Failed to mark kingdom messages seen: {e}')
        for msg in self._messages:
            if msg.get('id') in ids:
                msg['seen_by_recipient'] = True
        self._message_unread_count = 0
        self._activity_scroll_offsets_map()['messages'] = 0

    # ── Detail box ──────────────────────────────────────────────────

    def _open_detail(self, tile):
        """Open the land detail modal for *tile*."""
        self._detail_box = LandDetailBox(
            self.window, tile,
            cooldown=self._cooldown,
            land_cooldown=getattr(tile, 'conquer_cooldown_remaining', 0),
            on_conquer=self._on_conquer,
            on_defence=self._on_defence,
            on_config=self._on_configure_kingdom,
            on_message=self._on_message_owner,
            on_close=lambda: setattr(self, '_detail_box', None),
        )

    def _on_conquer(self, tile):
        """Transition to the conquer screen for this land."""
        self.state.conquer_land_id = tile.land_id
        self.state.screen = 'conquer'
        self._detail_box = None

    def _on_defence(self, tile):
        """Transition to the defence screen for this owned land."""
        self.state.defence_land_id = tile.land_id
        self.state.screen = 'defence'
        self._detail_box = None

    def _on_configure_kingdom(self, tile):
        """Transition to the kingdom configuration screen for this land."""
        self.state.kingdom_config_land_id = tile.land_id
        self.state.kingdom_config_id = getattr(tile, 'kingdom_id', None)
        self.state.screen = 'kingdom_config'
        self._detail_box = None

    def _on_message_owner(self, tile):
        """Open the kingdom message composer for a land owner."""
        self._detail_box = None
        self._open_message_compose(
            getattr(tile, 'owner_user_id', None),
            getattr(tile, 'owner_username', None) or 'Owner',
            land_id=getattr(tile, 'land_id', None),
        )
