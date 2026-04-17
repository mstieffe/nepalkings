# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Booster pack reveal overlay — 3 face-down cards that flip on click."""

import pygame
from config import settings
from game.components.cards.card_img import CardImg
from game.core.input_state import get_pressed as _get_pressed

_SW, _SH = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT

# Card dimensions for the reveal overlay
_CARD_W = int(0.10 * _SW)
_CARD_H = int(0.25 * _SH)
_CARD_GAP = int(0.04 * _SW)
_SCALE_HOVER = 1.15

# Glow dimensions
_GLOW_W = int(_CARD_W * 1.5)
_GLOW_H = int(_CARD_H * 1.3)

# Close button
_CLOSE_W = int(0.12 * _SW)
_CLOSE_H = int(0.045 * _SH)


class BoosterRevealOverlay:
    """Full-screen overlay showing 3 face-down booster cards.

    Each card starts face-down. The user clicks cards to reveal them.
    Once all 3 are revealed a Close button appears.
    """

    def __init__(self, window, drawn_cards):
        """
        Args:
            window: pygame display surface
            drawn_cards: list of dicts [{suit, rank, value}, ...]
        """
        self.window = window
        self._cards = drawn_cards[:3]  # ensure max 3

        # State per card slot: 'hidden' | 'revealed'
        self._states = ['hidden'] * len(self._cards)

        # Dim overlay
        self._overlay = pygame.Surface((_SW, _SH), pygame.SRCALPHA)
        self._overlay.fill((0, 0, 0, 180))

        # Load card back image
        back_raw = pygame.image.load(settings.CARD_IMG_PATH + 'back.png').convert_alpha()
        self._back_img = pygame.transform.smoothscale(back_raw, (_CARD_W, _CARD_H))
        self._back_img_big = pygame.transform.smoothscale(
            back_raw, (int(_CARD_W * _SCALE_HOVER), int(_CARD_H * _SCALE_HOVER)))

        # Build front images for each card
        self._front_imgs = []
        self._front_imgs_big = []
        for c in self._cards:
            ci = CardImg(window, c['suit'], c['rank'], _CARD_W, _CARD_H)
            self._front_imgs.append(ci.front_img)
            ci_big = CardImg(window, c['suit'], c['rank'],
                             int(_CARD_W * _SCALE_HOVER), int(_CARD_H * _SCALE_HOVER))
            self._front_imgs_big.append(ci_big.front_img)

        # Glow images
        self._glows = {}
        glow_path = 'img/glow/rect/'
        for colour in ('white', 'orange', 'yellow'):
            raw = pygame.image.load(glow_path + colour + '.png').convert_alpha()
            self._glows[colour] = pygame.transform.smoothscale(raw, (_GLOW_W, _GLOW_H))

        # Card positions (centred horizontally)
        n = len(self._cards)
        total_w = n * _CARD_W + (n - 1) * _CARD_GAP
        start_x = (_SW - total_w) // 2
        card_y = (_SH - _CARD_H) // 2 - int(0.03 * _SH)
        self._slots = []
        for i in range(n):
            x = start_x + i * (_CARD_W + _CARD_GAP)
            self._slots.append(pygame.Rect(x, card_y, _CARD_W, _CARD_H))

        # Close button (appears when all revealed)
        self._close_rect = pygame.Rect(
            (_SW - _CLOSE_W) // 2,
            card_y + _CARD_H + int(0.04 * _SH),
            _CLOSE_W, _CLOSE_H)
        self._close_font = settings.get_font(int(0.022 * _SH))

        # Title font
        self._title_font = settings.get_font(int(0.028 * _SH), bold=True)

    @property
    def all_revealed(self):
        return all(s == 'revealed' for s in self._states)

    def update(self):
        """Called every frame — no-op but keeps API consistent."""
        pass

    def draw(self):
        """Render the overlay."""
        self.window.blit(self._overlay, (0, 0))

        # Title
        title = self._title_font.render('Booster Pack', True, (250, 221, 0))
        tx = (_SW - title.get_width()) // 2
        ty = self._slots[0].y - int(0.06 * _SH)
        self.window.blit(title, (tx, ty))

        mouse_pos = pygame.mouse.get_pos()

        for i, slot in enumerate(self._slots):
            state = self._states[i]
            hovered = slot.inflate(int(_CARD_W * 0.3), int(_CARD_H * 0.3)).collidepoint(mouse_pos)

            if state == 'hidden':
                # Glow
                glow_key = 'orange' if hovered else 'white'
                glow = self._glows[glow_key]
                gx = slot.centerx - glow.get_width() // 2
                gy = slot.centery - glow.get_height() // 2
                self.window.blit(glow, (gx, gy))

                if hovered:
                    # Scaled up back
                    img = self._back_img_big
                    pos = img.get_rect(center=slot.center).topleft
                    self.window.blit(img, pos)
                else:
                    self.window.blit(self._back_img, slot.topleft)
            else:
                # Revealed — yellow glow + bright front
                glow = self._glows['yellow']
                gx = slot.centerx - glow.get_width() // 2
                gy = slot.centery - glow.get_height() // 2
                self.window.blit(glow, (gx, gy))

                if hovered:
                    img = self._front_imgs_big[i]
                    pos = img.get_rect(center=slot.center).topleft
                    self.window.blit(img, pos)
                else:
                    self.window.blit(self._front_imgs[i], slot.topleft)

                # Card name label
                c = self._cards[i]
                label = self._close_font.render(
                    f"{c['suit']} {c['rank']}", True, (220, 210, 180))
                lx = slot.centerx - label.get_width() // 2
                ly = slot.bottom + int(0.008 * _SH)
                self.window.blit(label, (lx, ly))

        # Close button (only when all revealed)
        if self.all_revealed:
            btn_hovered = self._close_rect.collidepoint(mouse_pos)
            bg_clr = (80, 70, 40, 220) if btn_hovered else (35, 35, 40, 200)
            txt_clr = (250, 240, 200) if btn_hovered else (200, 190, 160)
            surf = pygame.Surface((self._close_rect.w, self._close_rect.h), pygame.SRCALPHA)
            surf.fill(bg_clr)
            pygame.draw.rect(surf, (120, 110, 90, 200), surf.get_rect(), 1)
            self.window.blit(surf, self._close_rect.topleft)
            txt = self._close_font.render('Close', True, txt_clr)
            self.window.blit(txt, txt.get_rect(center=self._close_rect.center))

    def handle_click(self, pos):
        """Handle a mouse click. Returns True when the overlay should close."""
        if self.all_revealed:
            if self._close_rect.collidepoint(pos):
                return True

        # Reveal hidden cards on click
        for i, slot in enumerate(self._slots):
            if self._states[i] == 'hidden' and slot.collidepoint(pos):
                self._states[i] = 'revealed'
                break

        return False
