# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
import pygame
from pygame.locals import *
from game.screens.screen import Screen
from game.screens._menu_base import MenuScreenMixin
from config import settings
from utils.utils import Button
import logging

logger = logging.getLogger('nk.screens.kingdom')

_SW, _SH = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT


class KingdomScreen(MenuScreenMixin, Screen):
    """Placeholder kingdom screen — hex map will be added in a later phase."""

    def __init__(self, state):
        super().__init__(state)
        self.control_buttons = []
        self._init_menu_chrome()

        # ── Custom button image ─────────────────────────────────────
        self._btn_img = pygame.image.load(settings.GAME_MENU_BTN_IMG_PATH).convert_alpha()

        # ── Title ───────────────────────────────────────────────────
        self._title_font = settings.get_font(settings.GAME_MENU_TITLE_FONT_SIZE, bold=True)
        self._title_surf = self._title_font.render('Kingdom', True, settings.GAME_MENU_TITLE_CLR)
        self._coming_font = settings.get_font(settings.SUB_SCREEN_HEADER_FONT_SIZE)
        self._coming_surf = self._coming_font.render('Coming soon …', True, settings.SUB_SCREEN_HEADER_CLR)

        # ── Back button ─────────────────────────────────────────────
        _btn_w = settings.GAME_MENU_BTN_W
        _btn_h = settings.GAME_MENU_BTN_H

        btn_x = (_SW - _btn_w) // 2
        title_h = self._title_surf.get_height() + settings.GAME_MENU_TITLE_PAD_BOTTOM
        coming_h = self._coming_surf.get_height() + settings.GAME_MENU_TITLE_PAD_BOTTOM
        content_h = title_h + coming_h + _btn_h
        box_h = settings.GAME_MENU_BOX_PAD_TOP + content_h + settings.GAME_MENU_BOX_PAD_BOTTOM
        box_w = _btn_w + settings.GAME_MENU_BOX_PAD_X * 2
        self._box_rect = pygame.Rect((_SW - box_w) // 2, (_SH - box_h) // 2, box_w, box_h)

        btn_y = self._box_rect.y + settings.GAME_MENU_BOX_PAD_TOP + title_h + coming_h
        self.button_back = Button(self.window, btn_x, btn_y,
                                  "Back", width=_btn_w, height=_btn_h)
        self.button_back.button_image = pygame.transform.smoothscale(
            self._btn_img, (_btn_w, _btn_h))
        self.button_back.button_image_small = pygame.transform.smoothscale(
            self._btn_img, (int(_btn_w * 0.95), int(_btn_h * 0.95)))

        # Glow
        glow_w = int(_btn_w * settings.GAME_MENU_GLOW_W_FACTOR)
        glow_h = int(_btn_h * settings.GAME_MENU_GLOW_H_FACTOR)
        self._menu_glows = {}
        for colour in ('yellow', 'white', 'orange'):
            raw = pygame.image.load(settings.GAME_MENU_GLOW_DIR + colour + '.png').convert_alpha()
            self._menu_glows[colour] = pygame.transform.smoothscale(raw, (glow_w, glow_h))

        self.menu_buttons += [self.button_back]

        # ── Pre-render box surface ──────────────────────────────────
        self._box_surf = pygame.Surface((self._box_rect.w, self._box_rect.h), pygame.SRCALPHA)
        self._box_surf.fill(settings.GAME_MENU_BOX_BG_CLR)
        pygame.draw.rect(self._box_surf, settings.GAME_MENU_BOX_BORDER_CLR,
                         self._box_surf.get_rect(), settings.GAME_MENU_BOX_BORDER_W)

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

    def render(self):
        self._draw_menu_chrome()
        self.window.blit(self._box_surf, self._box_rect.topleft)

        title_x = self._box_rect.centerx - self._title_surf.get_width() // 2
        title_y = self._box_rect.y + settings.GAME_MENU_BOX_PAD_TOP
        self.window.blit(self._title_surf, (title_x, title_y))

        coming_x = self._box_rect.centerx - self._coming_surf.get_width() // 2
        coming_y = title_y + self._title_surf.get_height() + settings.GAME_MENU_TITLE_PAD_BOTTOM
        self.window.blit(self._coming_surf, (coming_x, coming_y))

        self._draw_menu_button(self.button_back)
        self._draw_menu_overlay()

    def update(self, events):
        super().update()
        self._update_icon_buttons()

    def handle_events(self, events):
        super().handle_events(events)
        for event in events:
            if self._handle_icon_events(event):
                continue
            if event.type == MOUSEBUTTONUP:
                if self.button_back.collide():
                    self.state.screen = 'game_menu'
                    logger.debug("Back button clicked")
