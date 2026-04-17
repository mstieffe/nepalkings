# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Conquer screen — configure figures + battle moves for attacking a land."""

import pygame
from pygame.locals import *
from game.screens.screen import Screen
from game.screens._menu_base import MenuScreenMixin
from config import settings
from utils import http_compat as requests
import logging

logger = logging.getLogger('nk.screens.conquer')

_SW, _SH = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT


class ConquerScreen(MenuScreenMixin, Screen):
    """Conquer configuration screen.

    Reads ``state.conquer_land_id`` to know which land the player
    wants to attack.  Fetches (or creates) the LandConfig from the
    server and lets the user build figures, buy battle moves, and set
    a battle modifier.
    """

    def __init__(self, state):
        super().__init__(state)
        self.control_buttons = []
        self._init_menu_chrome()

        # ── Persistent state ────────────────────────────────────────
        self._land_id = None
        self._land = None          # server dict
        self._config = None        # serialised LandConfig
        self._loading = False
        self._error = None

        # ── Fonts ───────────────────────────────────────────────────
        self._title_font = settings.get_font(int(0.035 * _SH), bold=True)
        self._label_font = settings.get_font(int(0.022 * _SH))
        self._value_font = settings.get_font(int(0.022 * _SH), bold=True)
        self._btn_font = settings.get_font(int(0.020 * _SH), bold=True)
        self._small_font = settings.get_font(int(0.018 * _SH))

        # ── Layout rects (initialised lazily after first data load) ─
        self._field_rects = {}       # 'castle'/'village'/'military' → Rect
        self._move_rects = []        # 3 Rects for battle move slots
        self._btn_build = None       # "Build Figure" button rect
        self._btn_buy_move = None    # "Buy Move" button rect
        self._btn_modifier = None    # modifier toggle rect
        self._btn_battle = None      # "To Battle!" button rect
        self._btn_back = None        # Back button rect
        self._layout_built = False

    # ── Layout ──────────────────────────────────────────────────────

    def _build_layout(self):
        """Compute rects based on screen dimensions."""
        pad = int(0.02 * _SW)
        top = int(0.09 * _SH)

        # Left half: 3 field compartments stacked horizontally
        field_w = int(0.14 * _SW)
        field_h = int(0.60 * _SH)
        fx = pad
        for field in ('castle', 'village', 'military'):
            self._field_rects[field] = pygame.Rect(fx, top, field_w, field_h)
            fx += field_w + pad

        # Build Figure button below fields
        btn_w = int(0.12 * _SW)
        btn_h = int(0.045 * _SH)
        self._btn_build = pygame.Rect(pad, top + field_h + pad, btn_w, btn_h)

        # Right half: battle moves + modifier + To Battle
        right_x = int(0.52 * _SW)
        move_w = int(0.13 * _SW)
        move_h = int(0.12 * _SH)
        my = top
        self._move_rects = []
        for i in range(3):
            self._move_rects.append(pygame.Rect(right_x, my, move_w, move_h))
            my += move_h + pad

        self._btn_buy_move = pygame.Rect(right_x, my, btn_w, btn_h)
        my += btn_h + pad * 2

        # Modifier
        mod_w = int(0.18 * _SW)
        self._btn_modifier = pygame.Rect(right_x, my, mod_w, btn_h)
        my += btn_h + pad * 2

        # To Battle
        battle_w = int(0.20 * _SW)
        battle_h = int(0.055 * _SH)
        self._btn_battle = pygame.Rect(
            (_SW - battle_w) // 2,
            _SH - int(0.12 * _SH),
            battle_w, battle_h,
        )

        # Back button
        back_w = int(0.10 * _SW)
        self._btn_back = pygame.Rect(
            pad, _SH - int(0.08 * _SH), back_w, btn_h,
        )

        self._layout_built = True

    # ── Data loading ────────────────────────────────────────────────

    def _load_config(self):
        """Fetch (or create) the conquer config from the server."""
        self._loading = True
        self._error = None
        try:
            resp = requests.get(
                f'{settings.SERVER_URL}/kingdom/conquer/config',
                params={'land_id': self._land_id},
                timeout=15,
            )
            if resp.status_code != 200:
                err = resp.json() if resp.headers.get('content-type', '').startswith('application/json') else {}
                self._error = err.get('error', 'Failed to load conquer config')
                self._loading = False
                return
            data = resp.json()
            self._config = data.get('config')
            self._land = data.get('land')
            self._loading = False
            logger.debug(f'Conquer config loaded for land {self._land_id}')
        except Exception as e:
            self._error = 'Connection error'
            logger.error(f'Conquer config load error: {e}')
            self._loading = False

    # ── Server actions ──────────────────────────────────────────────

    def _server_remove_figure(self, figure_id):
        try:
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/conquer/remove_figure',
                json={'figure_id': figure_id},
                timeout=10,
            )
            data = resp.json()
            if data.get('success'):
                self._config = data['config']
            else:
                logger.warning(f'Remove figure failed: {data.get("message")}')
        except Exception as e:
            logger.error(f'Remove figure error: {e}')

    def _server_return_move(self, move_id):
        try:
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/conquer/return_battle_move',
                json={'move_id': move_id},
                timeout=10,
            )
            data = resp.json()
            if data.get('success'):
                self._config = data['config']
            else:
                logger.warning(f'Return move failed: {data.get("message")}')
        except Exception as e:
            logger.error(f'Return move error: {e}')

    def _server_set_modifier(self):
        try:
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/conquer/set_modifier',
                json={'land_id': self._land_id, 'modifier_type': 'Blitzkrieg'},
                timeout=10,
            )
            data = resp.json()
            if data.get('success'):
                self._config = data['config']
        except Exception as e:
            logger.error(f'Set modifier error: {e}')

    def _server_remove_modifier(self):
        try:
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/conquer/remove_modifier',
                json={'land_id': self._land_id},
                timeout=10,
            )
            data = resp.json()
            if data.get('success'):
                self._config = data['config']
        except Exception as e:
            logger.error(f'Remove modifier error: {e}')

    # ── Rendering ───────────────────────────────────────────────────

    def render(self):
        self._draw_menu_chrome()

        if self._loading:
            txt = self._label_font.render('Loading conquer config…', True, (200, 185, 150))
            self.window.blit(txt, txt.get_rect(center=(_SW // 2, _SH // 2)))
            self._draw_menu_overlay()
            return

        if self._error:
            txt = self._label_font.render(self._error, True, (200, 80, 80))
            self.window.blit(txt, txt.get_rect(center=(_SW // 2, _SH // 2)))
            self._draw_back_button()
            self._draw_menu_overlay()
            return

        if not self._config:
            self._draw_menu_overlay()
            return

        if not self._layout_built:
            self._build_layout()

        # ── Title ───────────────────────────────────────────────────
        land = self._land or {}
        tier = land.get('tier', '?')
        owner = land.get('owner')
        owner_name = owner.get('username', 'AI') if owner else 'AI'
        title = f'Conquer Land (Tier {tier}) — Defended by {owner_name}'
        t_surf = self._title_font.render(title, True, (250, 221, 0))
        self.window.blit(t_surf, t_surf.get_rect(centerx=_SW // 2, top=int(0.025 * _SH)))

        # ── Field compartments ──────────────────────────────────────
        self._draw_field_compartments()

        # ── Battle moves ────────────────────────────────────────────
        self._draw_battle_moves()

        # ── Modifier ────────────────────────────────────────────────
        self._draw_modifier()

        # ── Buttons ─────────────────────────────────────────────────
        self._draw_button(self._btn_build, 'Build Figure', (60, 140, 60))
        self._draw_button(self._btn_buy_move, 'Buy Move', (60, 100, 160))

        # To Battle — enabled only when ready
        ready = self._is_battle_ready()
        battle_clr = (200, 170, 0) if ready else (80, 80, 80)
        self._draw_button(self._btn_battle, 'To Battle!', battle_clr)

        self._draw_back_button()
        self._draw_menu_overlay()

    def _draw_field_compartments(self):
        """Draw the three field compartments with any built figures."""
        figures = self._config.get('figures', [])

        for field_name, rect in self._field_rects.items():
            # Background
            surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
            surf.fill((30, 30, 35, 200))
            self.window.blit(surf, rect.topleft)
            # Border
            pygame.draw.rect(self.window, (120, 100, 70), rect, 1, border_radius=2)
            # Title
            lbl = self._label_font.render(field_name.upper(), True, (180, 160, 120))
            self.window.blit(lbl, (rect.x + 6, rect.y + 4))

            # Figures in this compartment
            field_figs = [f for f in figures if f.get('field') == field_name]
            fy = rect.y + 30
            for fig in field_figs:
                self._draw_figure_entry(fig, rect.x + 6, fy, rect.w - 12)
                fy += int(0.08 * _SH)

    def _draw_figure_entry(self, fig, x, y, w):
        """Draw a single figure summary line with [X] remove button."""
        deficit = fig.get('has_deficit', False)
        clr = (180, 80, 80) if deficit else (200, 200, 200)
        name = fig.get('name', fig.get('family_name', '?'))
        suit = fig.get('suit', '')
        txt = self._small_font.render(f'{name} ({suit})', True, clr)
        self.window.blit(txt, (x, y))

        if deficit:
            dtxt = self._small_font.render('DEFICIT', True, (220, 60, 60))
            self.window.blit(dtxt, (x + w - dtxt.get_width(), y))

        # [X] button
        xbtn = pygame.Rect(x + w - 20, y, 18, 18)
        pygame.draw.rect(self.window, (140, 50, 50), xbtn, border_radius=2)
        xt = self._small_font.render('X', True, (255, 255, 255))
        self.window.blit(xt, xt.get_rect(center=xbtn.center))
        fig['_remove_rect'] = xbtn  # stash for hit testing

    def _draw_battle_moves(self):
        """Draw the 3 battle move slots."""
        moves = self._config.get('battle_moves', [])
        move_by_round = {m['round_index']: m for m in moves}

        label = self._label_font.render('BATTLE MOVES', True, (180, 160, 120))
        self.window.blit(label,
                         (self._move_rects[0].x, self._move_rects[0].y - 24))

        for i, rect in enumerate(self._move_rects):
            surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
            surf.fill((30, 30, 35, 200))
            self.window.blit(surf, rect.topleft)
            pygame.draw.rect(self.window, (120, 100, 70), rect, 1, border_radius=2)

            if i in move_by_round:
                m = move_by_round[i]
                txt = self._value_font.render(
                    f"R{i + 1}: {m['family_name']} {m['rank']}{m['suit'][0]}",
                    True, (200, 200, 200),
                )
                self.window.blit(txt, (rect.x + 6, rect.y + 8))

                # [X] remove button
                xbtn = pygame.Rect(rect.right - 24, rect.y + 4, 18, 18)
                pygame.draw.rect(self.window, (140, 50, 50), xbtn, border_radius=2)
                xt = self._small_font.render('X', True, (255, 255, 255))
                self.window.blit(xt, xt.get_rect(center=xbtn.center))
                m['_remove_rect'] = xbtn
            else:
                txt = self._small_font.render(f'Round {i + 1}: empty', True, (100, 100, 100))
                self.window.blit(txt, (rect.x + 6, rect.y + rect.h // 2 - 8))

    def _draw_modifier(self):
        """Draw the modifier toggle / display."""
        mod = self._config.get('battle_modifier')
        if mod:
            label = f"Modifier: {mod.get('type', '?')}  [remove]"
            clr = (200, 180, 80)
        else:
            label = 'Set Modifier: Blitzkrieg'
            clr = (130, 130, 130)

        rect = self._btn_modifier
        surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        surf.fill((30, 30, 35, 200))
        self.window.blit(surf, rect.topleft)
        pygame.draw.rect(self.window, (120, 100, 70), rect, 1, border_radius=2)
        txt = self._btn_font.render(label, True, clr)
        self.window.blit(txt, txt.get_rect(center=rect.center))

    def _draw_button(self, rect, text, color):
        if not rect:
            return
        mx, my = pygame.mouse.get_pos()
        hovered = rect.collidepoint(mx, my)
        c = tuple(min(v + 30, 255) for v in color) if hovered else color
        pygame.draw.rect(self.window, c, rect, border_radius=4)
        pygame.draw.rect(self.window, (200, 180, 140), rect, 1, border_radius=4)
        txt = self._btn_font.render(text, True, (255, 255, 255))
        self.window.blit(txt, txt.get_rect(center=rect.center))

    def _draw_back_button(self):
        if not self._btn_back:
            if not self._layout_built:
                self._build_layout()
        self._draw_button(self._btn_back, 'Back', (80, 80, 80))

    # ── Readiness check ────────────────────────────────────────────

    def _is_battle_ready(self):
        """True when the user can initiate the conquer battle."""
        if not self._config:
            return False
        figures = self._config.get('figures', [])
        moves = self._config.get('battle_moves', [])

        # Need at least 1 non-deficit figure
        has_valid_figure = any(not f.get('has_deficit', False) for f in figures)
        # Need exactly 3 battle moves
        has_moves = len(moves) == 3
        return has_valid_figure and has_moves

    # ── Update / events ─────────────────────────────────────────────

    def update(self, events):
        super().update()
        self._update_icon_buttons()

        # Check if the land_id changed (new conquer target)
        target_land = getattr(self.state, 'conquer_land_id', None)
        if target_land and target_land != self._land_id:
            self._land_id = target_land
            self._config = None
            self._land = None
            self._loading = False
            self._error = None

        # Auto-load config if needed
        if self._land_id and not self._config and not self._loading and not self._error:
            self._load_config()

    def handle_events(self, events):
        super().handle_events(events)

        for event in events:
            if self._handle_icon_events(event):
                continue

            if event.type == MOUSEBUTTONUP and event.button == 1:
                pos = event.pos

                # Back button
                if self._btn_back and self._btn_back.collidepoint(pos):
                    self.state.screen = 'kingdom'
                    return

                if not self._config:
                    continue

                # Build Figure button
                if self._btn_build and self._btn_build.collidepoint(pos):
                    logger.info('Build Figure clicked — would open BuildFigureScreen with CollectionCardSource')
                    # Phase 11 integration: transition to build figure
                    continue

                # Buy Move button
                if self._btn_buy_move and self._btn_buy_move.collidepoint(pos):
                    logger.info('Buy Move clicked — would open BattleShopScreen with CollectionCardSource')
                    continue

                # Modifier toggle
                if self._btn_modifier and self._btn_modifier.collidepoint(pos):
                    mod = self._config.get('battle_modifier')
                    if mod:
                        self._server_remove_modifier()
                    else:
                        self._server_set_modifier()
                    continue

                # To Battle
                if self._btn_battle and self._btn_battle.collidepoint(pos):
                    if self._is_battle_ready():
                        logger.info(f'To Battle! for land {self._land_id}')
                        # Phase 13/15 will implement actual battle initiation
                    continue

                # Remove figure [X] buttons
                for fig in self._config.get('figures', []):
                    xrect = fig.get('_remove_rect')
                    if xrect and xrect.collidepoint(pos):
                        self._server_remove_figure(fig['id'])
                        break

                # Remove battle move [X] buttons
                for move in self._config.get('battle_moves', []):
                    xrect = move.get('_remove_rect')
                    if xrect and xrect.collidepoint(pos):
                        self._server_return_move(move['id'])
                        break

            # ESC → back to kingdom
            if event.type == KEYDOWN and event.key == K_ESCAPE:
                self.state.screen = 'kingdom'
                return
