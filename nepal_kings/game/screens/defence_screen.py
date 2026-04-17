# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Defence screen — configure figures, battle moves, spells & gamble for defending a land."""

import pygame
from pygame.locals import *
from game.screens.screen import Screen
from game.screens._menu_base import MenuScreenMixin
from config import settings
from utils import http_compat as requests
import logging

logger = logging.getLogger('nk.screens.defence')

_SW, _SH = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT


class DefenceScreen(MenuScreenMixin, Screen):
    """Defence configuration screen.

    Reads ``state.defence_land_id`` to know which owned land the player
    wants to set up defences for.  Fetches (or creates) the LandConfig
    from the server and lets the user build figures, buy battle moves,
    set a modifier, select a battle figure or spell, and toggle auto-gamble.
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

        # ── Layout rects ────────────────────────────────────────────
        self._field_rects = {}       # 'castle'/'village'/'military' → Rect
        self._move_rects = []        # 3 Rects for battle move slots
        self._btn_build = None
        self._btn_buy_move = None
        self._btn_modifier = None
        self._btn_battle_fig = None
        self._btn_spell = None
        self._btn_auto_gamble = None
        self._btn_back = None
        self._layout_built = False

    # ── Layout ──────────────────────────────────────────────────────

    def _build_layout(self):
        pad = int(0.02 * _SW)
        top = int(0.09 * _SH)

        # Left: 3 field compartments
        field_w = int(0.14 * _SW)
        field_h = int(0.55 * _SH)
        fx = pad
        for field in ('castle', 'village', 'military'):
            self._field_rects[field] = pygame.Rect(fx, top, field_w, field_h)
            fx += field_w + pad

        btn_w = int(0.12 * _SW)
        btn_h = int(0.045 * _SH)
        self._btn_build = pygame.Rect(pad, top + field_h + pad, btn_w, btn_h)

        # Right: battle moves + modifier + battle figure + spell + auto-gamble
        right_x = int(0.52 * _SW)
        move_w = int(0.13 * _SW)
        move_h = int(0.10 * _SH)
        my = top
        self._move_rects = []
        for i in range(3):
            self._move_rects.append(pygame.Rect(right_x, my, move_w, move_h))
            my += move_h + pad

        self._btn_buy_move = pygame.Rect(right_x, my, btn_w, btn_h)
        my += btn_h + pad

        mod_w = int(0.18 * _SW)
        self._btn_modifier = pygame.Rect(right_x, my, mod_w, btn_h)
        my += btn_h + pad

        # Battle figure / spell toggle area
        self._btn_battle_fig = pygame.Rect(right_x, my, mod_w, btn_h)
        my += btn_h + pad

        self._btn_spell = pygame.Rect(right_x, my, mod_w, btn_h)
        my += btn_h + pad

        self._btn_auto_gamble = pygame.Rect(right_x, my, mod_w, btn_h)

        # Back button
        back_w = int(0.10 * _SW)
        self._btn_back = pygame.Rect(
            pad, _SH - int(0.08 * _SH), back_w, btn_h,
        )

        self._layout_built = True

    # ── Data loading ────────────────────────────────────────────────

    def _load_config(self):
        self._loading = True
        self._error = None
        try:
            resp = requests.get(
                f'{settings.SERVER_URL}/kingdom/defence/config',
                params={'land_id': self._land_id},
                timeout=15,
            )
            if resp.status_code != 200:
                err = resp.json() if resp.headers.get('content-type', '').startswith('application/json') else {}
                self._error = err.get('message', err.get('error', 'Failed to load defence config'))
                self._loading = False
                return
            data = resp.json()
            self._config = data.get('config')
            self._land = data.get('land')
            self._loading = False
            logger.debug(f'Defence config loaded for land {self._land_id}')
        except Exception as e:
            self._error = 'Connection error'
            logger.error(f'Defence config load error: {e}')
            self._loading = False

    # ── Server actions ──────────────────────────────────────────────

    def _server_remove_figure(self, figure_id):
        try:
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/defence/remove_figure',
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
                f'{settings.SERVER_URL}/kingdom/defence/return_battle_move',
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

    def _server_set_modifier(self, modifier_type):
        try:
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/defence/set_modifier',
                json={'land_id': self._land_id, 'modifier_type': modifier_type},
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
                f'{settings.SERVER_URL}/kingdom/defence/remove_modifier',
                json={'land_id': self._land_id},
                timeout=10,
            )
            data = resp.json()
            if data.get('success'):
                self._config = data['config']
        except Exception as e:
            logger.error(f'Remove modifier error: {e}')

    def _server_set_battle_figure(self, figure_id, figure_id_2=None):
        try:
            payload = {'land_id': self._land_id, 'figure_id': figure_id}
            if figure_id_2:
                payload['figure_id_2'] = figure_id_2
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/defence/set_battle_figure',
                json=payload, timeout=10,
            )
            data = resp.json()
            if data.get('success'):
                self._config = data['config']
            else:
                logger.warning(f'Set battle figure failed: {data.get("message")}')
        except Exception as e:
            logger.error(f'Set battle figure error: {e}')

    def _server_clear_battle_figure(self):
        try:
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/defence/clear_battle_figure',
                json={'land_id': self._land_id},
                timeout=10,
            )
            data = resp.json()
            if data.get('success'):
                self._config = data['config']
        except Exception as e:
            logger.error(f'Clear battle figure error: {e}')

    def _server_set_spell(self, spell_name, spell_card_ids=None, target_fig_id=None):
        try:
            payload = {
                'land_id': self._land_id,
                'spell_name': spell_name,
                'spell_card_ids': spell_card_ids or [],
            }
            if target_fig_id:
                payload['spell_target_figure_id'] = target_fig_id
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/defence/set_spell',
                json=payload, timeout=10,
            )
            data = resp.json()
            if data.get('success'):
                self._config = data['config']
            else:
                logger.warning(f'Set spell failed: {data.get("message")}')
        except Exception as e:
            logger.error(f'Set spell error: {e}')

    def _server_clear_spell(self):
        try:
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/defence/clear_spell',
                json={'land_id': self._land_id},
                timeout=10,
            )
            data = resp.json()
            if data.get('success'):
                self._config = data['config']
        except Exception as e:
            logger.error(f'Clear spell error: {e}')

    def _server_set_auto_gamble(self, enabled):
        try:
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/defence/set_auto_gamble',
                json={'land_id': self._land_id, 'auto_gamble': enabled},
                timeout=10,
            )
            data = resp.json()
            if data.get('success'):
                self._config = data['config']
        except Exception as e:
            logger.error(f'Set auto gamble error: {e}')

    # ── Rendering ───────────────────────────────────────────────────

    def render(self):
        self._draw_menu_chrome()

        if self._loading:
            txt = self._label_font.render('Loading defence config…', True, (200, 185, 150))
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
        title = f'Defence Setup — Your Land (Tier {tier})'
        t_surf = self._title_font.render(title, True, (100, 200, 255))
        self.window.blit(t_surf, t_surf.get_rect(centerx=_SW // 2, top=int(0.025 * _SH)))

        # ── Field compartments ──────────────────────────────────────
        self._draw_field_compartments()

        # ── Battle moves ────────────────────────────────────────────
        self._draw_battle_moves()

        # ── Modifier ────────────────────────────────────────────────
        self._draw_modifier()

        # ── Battle figure / spell ───────────────────────────────────
        self._draw_battle_figure_row()
        self._draw_spell_row()

        # ── Auto-gamble ─────────────────────────────────────────────
        self._draw_auto_gamble()

        # ── Buttons ─────────────────────────────────────────────────
        self._draw_button(self._btn_build, 'Build Figure', (60, 140, 60))
        self._draw_button(self._btn_buy_move, 'Buy Move', (60, 100, 160))

        self._draw_back_button()
        self._draw_menu_overlay()

    def _draw_field_compartments(self):
        figures = self._config.get('figures', [])
        for field_name, rect in self._field_rects.items():
            surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
            surf.fill((30, 30, 35, 200))
            self.window.blit(surf, rect.topleft)
            pygame.draw.rect(self.window, (120, 100, 70), rect, 1, border_radius=2)
            lbl = self._label_font.render(field_name.upper(), True, (180, 160, 120))
            self.window.blit(lbl, (rect.x + 6, rect.y + 4))

            field_figs = [f for f in figures if f.get('field') == field_name]
            fy = rect.y + 30
            for fig in field_figs:
                self._draw_figure_entry(fig, rect.x + 6, fy, rect.w - 12)
                fy += int(0.08 * _SH)

    def _draw_figure_entry(self, fig, x, y, w):
        deficit = fig.get('has_deficit', False)
        is_battle = fig['id'] in (
            self._config.get('battle_figure_id'),
            self._config.get('battle_figure_id_2'),
        )
        clr = (180, 80, 80) if deficit else (100, 200, 255) if is_battle else (200, 200, 200)
        name = fig.get('name', fig.get('family_name', '?'))
        suit = fig.get('suit', '')
        prefix = '[B] ' if is_battle else ''
        txt = self._small_font.render(f'{prefix}{name} ({suit})', True, clr)
        self.window.blit(txt, (x, y))

        if deficit:
            dtxt = self._small_font.render('DEFICIT', True, (220, 60, 60))
            self.window.blit(dtxt, (x + w - dtxt.get_width(), y))

        xbtn = pygame.Rect(x + w - 20, y, 18, 18)
        pygame.draw.rect(self.window, (140, 50, 50), xbtn, border_radius=2)
        xt = self._small_font.render('X', True, (255, 255, 255))
        self.window.blit(xt, xt.get_rect(center=xbtn.center))
        fig['_remove_rect'] = xbtn

    def _draw_battle_moves(self):
        moves = self._config.get('battle_moves', [])
        move_by_round = {m['round_index']: m for m in moves}

        label = self._label_font.render('BATTLE MOVES', True, (180, 160, 120))
        self.window.blit(label, (self._move_rects[0].x, self._move_rects[0].y - 24))

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
                xbtn = pygame.Rect(rect.right - 24, rect.y + 4, 18, 18)
                pygame.draw.rect(self.window, (140, 50, 50), xbtn, border_radius=2)
                xt = self._small_font.render('X', True, (255, 255, 255))
                self.window.blit(xt, xt.get_rect(center=xbtn.center))
                m['_remove_rect'] = xbtn
            else:
                txt = self._small_font.render(f'Round {i + 1}: empty', True, (100, 100, 100))
                self.window.blit(txt, (rect.x + 6, rect.y + rect.h // 2 - 8))

    def _draw_modifier(self):
        mod = self._config.get('battle_modifier')
        if mod:
            label = f"Modifier: {mod.get('type', '?')}  [remove]"
            clr = (200, 180, 80)
        else:
            label = 'Set Modifier …'
            clr = (130, 130, 130)

        rect = self._btn_modifier
        surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        surf.fill((30, 30, 35, 200))
        self.window.blit(surf, rect.topleft)
        pygame.draw.rect(self.window, (120, 100, 70), rect, 1, border_radius=2)
        txt = self._btn_font.render(label, True, clr)
        self.window.blit(txt, txt.get_rect(center=rect.center))

    def _draw_battle_figure_row(self):
        bf_id = self._config.get('battle_figure_id')
        bf_id_2 = self._config.get('battle_figure_id_2')
        if bf_id:
            fig_name = self._figure_name(bf_id)
            label = f'Battle Fig: {fig_name}'
            if bf_id_2:
                label += f' + {self._figure_name(bf_id_2)}'
            label += '  [clear]'
            clr = (100, 200, 255)
        else:
            label = 'Select Battle Figure …'
            clr = (130, 130, 130)

        rect = self._btn_battle_fig
        surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        surf.fill((30, 30, 35, 200))
        self.window.blit(surf, rect.topleft)
        pygame.draw.rect(self.window, (80, 100, 130), rect, 1, border_radius=2)
        txt = self._btn_font.render(label, True, clr)
        self.window.blit(txt, txt.get_rect(center=rect.center))

    def _draw_spell_row(self):
        spell = self._config.get('spell_name')
        if spell:
            label = f'Spell: {spell}  [clear]'
            clr = (180, 100, 220)
        else:
            label = 'Set Spell …'
            clr = (130, 130, 130)

        rect = self._btn_spell
        surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        surf.fill((30, 30, 35, 200))
        self.window.blit(surf, rect.topleft)
        pygame.draw.rect(self.window, (100, 70, 130), rect, 1, border_radius=2)
        txt = self._btn_font.render(label, True, clr)
        self.window.blit(txt, txt.get_rect(center=rect.center))

    def _draw_auto_gamble(self):
        enabled = self._config.get('auto_gamble', False)
        label = 'Auto-Gamble: ON' if enabled else 'Auto-Gamble: OFF'
        clr = (100, 220, 100) if enabled else (130, 130, 130)

        rect = self._btn_auto_gamble
        surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        surf.fill((30, 30, 35, 200))
        self.window.blit(surf, rect.topleft)
        pygame.draw.rect(self.window, (70, 120, 70), rect, 1, border_radius=2)
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

    # ── Helpers ─────────────────────────────────────────────────────

    def _figure_name(self, figure_id):
        for fig in self._config.get('figures', []):
            if fig['id'] == figure_id:
                return fig.get('name', fig.get('family_name', '?'))
        return '?'

    # ── Readiness check ─────────────────────────────────────────────

    def _is_defence_ready(self):
        """True when the defence configuration is complete enough."""
        if not self._config:
            return False
        figures = self._config.get('figures', [])
        moves = self._config.get('battle_moves', [])

        has_valid_figure = any(not f.get('has_deficit', False) for f in figures)
        has_moves = len(moves) == 3
        # Defence also requires either a battle figure or a spell (or auto-gamble)
        has_battle_fig = self._config.get('battle_figure_id') is not None
        has_spell = self._config.get('spell_name') is not None
        has_auto_gamble = self._config.get('auto_gamble', False)
        has_strategy = has_battle_fig or has_spell or has_auto_gamble
        return has_valid_figure and has_moves and has_strategy

    # ── Modifier cycling ───────────────────────────────────────────

    _MODIFIERS = ['Peasant War', 'Civil War']

    def _cycle_modifier(self):
        """Cycle through no modifier → Peasant War → Civil War → none."""
        mod = self._config.get('battle_modifier')
        if not mod:
            self._server_set_modifier(self._MODIFIERS[0])
        else:
            current = mod.get('type')
            try:
                idx = self._MODIFIERS.index(current)
            except ValueError:
                idx = -1
            next_idx = idx + 1
            if next_idx >= len(self._MODIFIERS):
                self._server_remove_modifier()
            else:
                self._server_set_modifier(self._MODIFIERS[next_idx])

    # ── Update / events ─────────────────────────────────────────────

    def update(self, events):
        super().update()
        self._update_icon_buttons()

        target_land = getattr(self.state, 'defence_land_id', None)
        if target_land and target_land != self._land_id:
            self._land_id = target_land
            self._config = None
            self._land = None
            self._loading = False
            self._error = None

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
                    continue

                # Buy Move button
                if self._btn_buy_move and self._btn_buy_move.collidepoint(pos):
                    logger.info('Buy Move clicked — would open BattleShopScreen with CollectionCardSource')
                    continue

                # Modifier toggle
                if self._btn_modifier and self._btn_modifier.collidepoint(pos):
                    self._cycle_modifier()
                    continue

                # Battle figure toggle
                if self._btn_battle_fig and self._btn_battle_fig.collidepoint(pos):
                    if self._config.get('battle_figure_id'):
                        self._server_clear_battle_figure()
                    else:
                        # Pick first non-deficit figure as battle figure
                        figs = self._config.get('figures', [])
                        valid = [f for f in figs if not f.get('has_deficit', False)]
                        if valid:
                            self._server_set_battle_figure(valid[0]['id'])
                    continue

                # Spell toggle
                if self._btn_spell and self._btn_spell.collidepoint(pos):
                    if self._config.get('spell_name'):
                        self._server_clear_spell()
                    else:
                        logger.info('Set spell clicked — would open spell selection UI')
                    continue

                # Auto-gamble toggle
                if self._btn_auto_gamble and self._btn_auto_gamble.collidepoint(pos):
                    current = self._config.get('auto_gamble', False)
                    self._server_set_auto_gamble(not current)
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
