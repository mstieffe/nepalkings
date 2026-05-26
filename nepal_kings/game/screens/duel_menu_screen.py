# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
import pygame
from pygame.locals import *
from game.screens.screen import Screen
from game.screens._menu_base import MenuScreenMixin
from config import settings
from config.screen_settings import _UI_SCALE
from utils.utils import Button
from utils.game_service import fetch_user_games, fetch_user
import logging

logger = logging.getLogger('nk.screens.duel_menu')

_SW, _SH = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT

# Badge appearance (same as game_menu_screen)
_BADGE_RADIUS = int(0.014 * _SH * _UI_SCALE)
_BADGE_CLR    = (210, 40, 40)
_BADGE_TXT    = (255, 255, 255)


def _draw_panel(window, rect, corner_r=None):
    r = corner_r or settings.SUB_SCREEN_PANEL_CORNER_R
    surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    pygame.draw.rect(surf, settings.SUB_SCREEN_PANEL_BG_CLR, surf.get_rect(), border_radius=r)
    window.blit(surf, rect.topleft)
    pygame.draw.rect(window, settings.SUB_SCREEN_PANEL_BORDER_CLR, rect,
                     settings.SUB_SCREEN_PANEL_BORDER_W, border_radius=r)


class DuelMenuScreen(MenuScreenMixin, Screen):
    def __init__(self, state):
        super().__init__(state)
        self.control_buttons = []
        self._init_menu_chrome()

        # ── Custom button image ─────────────────────────────────────
        self._btn_img = pygame.image.load(settings.GAME_MENU_BTN_IMG_PATH).convert_alpha()

        # ── Title font ──────────────────────────────────────────────
        self._title_font = settings.get_font(settings.GAME_MENU_TITLE_FONT_SIZE, bold=True)
        self._title_surf = self._title_font.render('Duel', True, settings.GAME_MENU_TITLE_CLR)

        # ── Menu buttons (centred) ──────────────────────────────────
        _btn_w = settings.GAME_MENU_BTN_W
        _btn_h = settings.GAME_MENU_BTN_H
        _btn_gap = settings.GAME_MENU_BTN_GAP

        btn_x = (_SW - _btn_w) // 2
        title_h = self._title_surf.get_height() + settings.GAME_MENU_TITLE_PAD_BOTTOM
        n_btns = 3
        content_h = title_h + n_btns * _btn_h + (n_btns - 1) * _btn_gap
        box_h = settings.GAME_MENU_BOX_PAD_TOP + content_h + settings.GAME_MENU_BOX_PAD_BOTTOM
        box_w = _btn_w + settings.GAME_MENU_BOX_PAD_X * 2
        self._box_rect = pygame.Rect(
            (_SW - box_w) // 2,
            (_SH - box_h) // 2,
            box_w, box_h)

        first_btn_y = self._box_rect.y + settings.GAME_MENU_BOX_PAD_TOP + title_h

        self.button_new = Button(self.window, btn_x, first_btn_y,
                                 "New Game", width=_btn_w, height=_btn_h)
        self.button_load = Button(self.window, btn_x, first_btn_y + _btn_h + _btn_gap,
                                  "Load Game", width=_btn_w, height=_btn_h)
        self.button_back = Button(self.window, btn_x, first_btn_y + 2 * (_btn_h + _btn_gap),
                                  "Back", width=_btn_w, height=_btn_h)

        # Apply custom button images
        for btn in (self.button_new, self.button_load, self.button_back):
            btn.button_image = pygame.transform.smoothscale(
                self._btn_img, (btn.rect.width, btn.rect.height))
            btn.button_image_small = pygame.transform.smoothscale(
                self._btn_img, (int(btn.rect.width * 0.95), int(btn.rect.height * 0.95)))

        # ── Oversized glow images (drawn BEHIND the button) ─────────
        glow_w = int(_btn_w * settings.GAME_MENU_GLOW_W_FACTOR)
        glow_h = int(_btn_h * settings.GAME_MENU_GLOW_H_FACTOR)
        self._menu_glows = {}
        for colour in ('yellow', 'white', 'orange'):
            raw = pygame.image.load(settings.GAME_MENU_GLOW_DIR + colour + '.png').convert_alpha()
            self._menu_glows[colour] = pygame.transform.smoothscale(raw, (glow_w, glow_h))

        self.menu_buttons += [self.button_new, self.button_load, self.button_back]

        # Badge font
        self._badge_font = settings.get_font(int(0.018 * _SH * _UI_SCALE), bold=True)


    # ── helper: draw a menu button with glow BEHIND ─────────────────
    def _draw_menu_button(self, btn):
        is_disabled = hasattr(btn, 'disabled') and btn.disabled
        if not is_disabled:
            if btn.hovered and btn.clicked:
                glow = self._menu_glows['yellow']
            elif btn.hovered and not btn.active:
                glow = self._menu_glows['white']
            elif btn.active:
                glow = self._menu_glows['orange']
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

    def _draw_badge(self, btn, count):
        if count <= 0:
            return
        cx = btn.rect.right - _BADGE_RADIUS
        cy = btn.rect.top + _BADGE_RADIUS
        pygame.draw.circle(self.window, _BADGE_CLR, (cx, cy), _BADGE_RADIUS)
        txt = self._badge_font.render(str(count), True, _BADGE_TXT)
        self.window.blit(txt, txt.get_rect(center=(cx, cy)))

    def render(self):
        self._draw_menu_chrome()

        # Dark transparent box
        _draw_panel(self.window, self._box_rect)

        # Title
        title_x = self._box_rect.centerx - self._title_surf.get_width() // 2
        title_y = self._box_rect.y + settings.GAME_MENU_BOX_PAD_TOP
        self.window.blit(self._title_surf, (title_x, title_y))

        # Menu buttons
        for btn in (self.button_new, self.button_load, self.button_back):
            self._draw_menu_button(btn)

        # Badges
        self._draw_badge(self.button_load, self.state.badge_new_games)
        self._draw_badge(self.button_new, self.state.badge_new_challenges)

        self._draw_menu_overlay()
        self._draw_menu_coach(self._current_duel_menu_coach_step())

    def update(self, events):
        super().update()
        self._update_icon_buttons()

    def handle_events(self, events):
        coach_step = self._current_duel_menu_coach_step()
        if self._handle_menu_coach_events(events, coach_step):
            return

        super().handle_events(events)
        for event in events:
            if self._handle_icon_events(event):
                continue
            # Click outside content box → back to game menu
            if (event.type == MOUSEBUTTONUP and event.button == 1
                    and not self.dialogue_box
                    and not self._box_rect.collidepoint(event.pos)):
                self.state.screen = 'game_menu'
                return
            if event.type == MOUSEBUTTONUP:
                self.handle_button_clicks()

    def handle_button_clicks(self):
        if self.button_new.collide():
            self._mark_menu_coach_seen('new_game')
            # Mark current challenges as seen
            self.state.badge_new_challenges = 0
            try:
                username = self.state.user_dict.get('username') if self.state.user_dict else None
                if username:
                    user = fetch_user(username)
                    received = user.get('challenges_received', [])
                    self.state._known_challenge_ids = {c['id'] for c in received}
            except Exception:
                pass
            self.state.screen = 'new_game'
            logger.debug("New Game button clicked")
        elif self.button_load.collide():
            # Mark current games as seen
            self.state.badge_new_games = 0
            try:
                username = self.state.user_dict.get('username') if self.state.user_dict else None
                if username:
                    game_dicts = fetch_user_games(username)
                    self.state._known_game_ids = {g['id'] for g in game_dicts if g.get('mode', 'duel') == 'duel'}
            except Exception:
                pass
            self.state.screen = 'load_game'
            logger.debug("Load Game button clicked")
        elif self.button_back.collide():
            self.state.screen = 'game_menu'
            logger.debug("Back button clicked")

    def _first_duel_incomplete(self):
        onboarding = (getattr(self.state, 'user_dict', None) or {}).get('onboarding') or {}
        completed = set(onboarding.get('completed_steps') or [])
        return bool(onboarding and 'finish_first_duel' not in completed)

    def _current_duel_menu_coach_step(self):
        if not self._menu_coach_allowed_common() or not self._first_duel_incomplete():
            return None
        if 'new_game' in self._menu_coach_seen():
            return None
        return {
            'id': 'new_game',
            'rect': self.button_new.rect,
            'title': 'Create A Duel',
            'body': 'Click New Game yourself. The next screen prepares a gentle AI challenge for your first run.',
            'action': 'click',
            'mark_on_click': True,
        }
