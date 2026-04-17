# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Kingdom screen — interactive hex map with land details."""

import pygame
from pygame.locals import *
from game.screens.screen import Screen
from game.screens._menu_base import MenuScreenMixin
from game.components.hex_map import HexMap
from game.components.land_detail_box import LandDetailBox
from config import settings
from utils import http_compat as requests
import logging

logger = logging.getLogger('nk.screens.kingdom')

_SW, _SH = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT


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

        # ── Fonts ───────────────────────────────────────────────────
        self._info_font = settings.get_font(settings.KINGDOM_INFO_FONT_SIZE)
        self._nav_font = settings.get_font(settings.KINGDOM_INFO_FONT_SIZE, bold=True)

        # ── Navigation zoom buttons (bottom-left) ──────────────────
        btn_sz = settings.NAV_BTN_SIZE
        margin = settings.NAV_BTN_MARGIN
        by = _SH - margin - btn_sz

        self._nav_rects = {
            'zoom_in':  pygame.Rect(margin, by - btn_sz - margin, btn_sz, btn_sz),
            'zoom_out': pygame.Rect(margin, by, btn_sz, btn_sz),
        }
        self._nav_labels = {
            'zoom_in': '+',
            'zoom_out': '\u2212',  # minus sign
        }

        # ── Track last load time ────────────────────────────────────
        self._last_load_tick = 0

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
                self._hex_map = HexMap(lands, self.window)
            else:
                self._hex_map.update_data(lands)

            self._loading = False
            logger.debug(f'Kingdom map loaded: {len(lands)} lands')
        except Exception as e:
            self._error = 'Connection error'
            logger.error(f'Kingdom map load error: {e}')
            self._loading = False

    # ── Rendering ───────────────────────────────────────────────────

    def render(self):
        self._draw_menu_chrome()

        if self._loading:
            txt = self._info_font.render('Loading kingdom map...', True,
                                         settings.KINGDOM_INFO_CLR)
            self.window.blit(txt, txt.get_rect(center=(_SW // 2, _SH // 2)))
        elif self._error:
            txt = self._info_font.render(self._error, True, (200, 80, 80))
            self.window.blit(txt, txt.get_rect(center=(_SW // 2, _SH // 2)))
        elif self._hex_map:
            self._hex_map.render()
            self._draw_info_bar()
            self._draw_nav_buttons()

        # Modal layer
        if self._detail_box:
            self._detail_box.render()

        self._draw_menu_overlay()

    def _draw_info_bar(self):
        """Draw production rate / lands count bar at top-centre."""
        if not self._map_data:
            return

        rate = self._map_data.get('my_total_gold_rate', 0)
        count = self._map_data.get('my_lands_count', 0)
        text = f'Your lands: {count}    Gold rate: {rate:.1f}/hr'
        if self._cooldown > 0:
            hours = self._cooldown // 3600
            mins = (self._cooldown % 3600) // 60
            text += f'    Conquer cooldown: {hours}h {mins}m'

        txt_surf = self._info_font.render(text, True, settings.KINGDOM_INFO_CLR)
        px = settings.KINGDOM_INFO_PAD_X
        py = settings.KINGDOM_INFO_PAD_Y
        bw = txt_surf.get_width() + px * 2
        bh = txt_surf.get_height() + py * 2

        box = pygame.Surface((bw, bh), pygame.SRCALPHA)
        box.fill(settings.KINGDOM_INFO_BG_CLR)
        bar_x = (_SW - bw) // 2
        bar_y = int(0.015 * _SH)
        self.window.blit(box, (bar_x, bar_y))
        self.window.blit(txt_surf, (bar_x + px, bar_y + py))

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

            # If detail box is open, route events there
            if self._detail_box:
                action = self._detail_box.handle_event(event)
                if action == 'conquer':
                    logger.info(f'Conquer requested for land {self._detail_box.tile.land_id}')
                    self._detail_box = None
                elif action == 'defence':
                    logger.info(f'Defence config requested for land {self._detail_box.tile.land_id}')
                    self._detail_box = None
                elif action == 'close':
                    self._detail_box = None
                continue

            if event.type == MOUSEBUTTONUP and event.button == 1:
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

    # ── Detail box ──────────────────────────────────────────────────

    def _open_detail(self, tile):
        """Open the land detail modal for *tile*."""
        self._detail_box = LandDetailBox(
            self.window, tile,
            cooldown=self._cooldown,
            on_conquer=self._on_conquer,
            on_defence=self._on_defence,
            on_close=lambda: setattr(self, '_detail_box', None),
        )

    def _on_conquer(self, tile):
        """Transition to the conquer screen for this land."""
        self.state.conquer_land_id = tile.land_id
        self.state.screen = 'conquer'
        self._detail_box = None

    def _on_defence(self, tile):
        """Defence config action — Phase 12 will implement the actual transition."""
        logger.info(f'Defence config action for land ({tile.col}, {tile.row})')
        self._detail_box = None
