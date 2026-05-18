# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
from config import settings
import pygame
from game.core.input_state import get_pressed as _get_pressed
from utils import haptics


class ConfirmButton:
    def __init__(self, window, x=0, y=0, text="", width=None, height=None, disabled=False,
                 hit_pad=None):
        self.window = window
        self.x = x
        self.y = y
        self.text = text
        self.disabled = disabled

        # Extra touch hit-area padding per side.  Defaults to the global
        # mobile pad; callers that stack confirm buttons tightly should
        # pass ``hit_pad=0`` so neighbouring hit areas don't overlap.
        self.hit_pad = settings.TOUCH_HIT_PAD if hit_pad is None else hit_pad

        # Fonts
        self.font = settings.get_font(settings.CONFIRM_BUTTON_FONT_SIZE)
        self.font_small = settings.get_font(settings.CONFIRM_BUTTON_FONT_SIZE_SMALL)

        # Dimensions
        self.set_dimensions(width, height)

        # Images
        self.load_images()

        # States
        self.hovered = False
        self.clicked = False
        self.active = False

    def set_dimensions(self, width, height):
        text_obj = self.font.render(self.text, True, settings.CONFIRM_BUTTON_TEXT_COLOR_PASSIVE)
        button_width = max(width or settings.CONFIRM_BUTTON_WIDTH,
                           text_obj.get_width() + settings.SMALL_SPACER_X)
        button_height = height or settings.CONFIRM_BUTTON_HEIGHT
        self.rect = pygame.Rect(self.x, self.y, button_width, button_height)

    def load_images(self):
        w, h = self.rect.width, self.rect.height

        # Normal button (same as login menu)
        raw = pygame.image.load(settings.CONFIRM_BUTTON_IMG_PATH).convert_alpha()
        self.button_image = pygame.transform.smoothscale(raw, (w, h))
        self.button_image_small = pygame.transform.smoothscale(raw,
                                    (int(w * 0.95), int(h * 0.95)))

        # Disabled / greyscale button
        raw_gs = pygame.image.load(settings.CONFIRM_BUTTON_IMG_DISABLED_PATH).convert_alpha()
        self.button_image_disabled = pygame.transform.smoothscale(raw_gs, (w, h))

        # Glow images
        glow_w = int(w * settings.CONFIRM_BUTTON_GLOW_W_FACTOR)
        glow_h = int(h * settings.CONFIRM_BUTTON_GLOW_H_FACTOR)
        self.glow_images = {}
        for colour in ('yellow', 'white', 'orange'):
            g = pygame.image.load(settings.CONFIRM_BUTTON_GLOW_DIR + colour + '.png').convert_alpha()
            self.glow_images[colour] = pygame.transform.smoothscale(g, (glow_w, glow_h))

    def collide(self):
        pad = self.hit_pad
        hit = self.rect.inflate(2 * pad, 2 * pad) if pad else self.rect
        return hit.collidepoint(pygame.mouse.get_pos())

    def draw(self):
        # ---- Disabled state: greyscale, no glow ----
        if self.disabled:
            self.window.blit(self.button_image_disabled, self.rect.topleft)
            txt = self.font.render(self.text, True, settings.CONFIRM_BUTTON_TEXT_COLOR_DISABLED)
            self.window.blit(txt, txt.get_rect(center=self.rect.center))
            return

        # ---- Glow ----
        if self.hovered and self.active:
            self._draw_glow('orange')
        elif self.hovered:
            self._draw_glow('yellow')
        elif self.active:
            self._draw_glow('orange')
        else:
            self._draw_glow('white')

        # ---- Button image (slightly smaller when click-pressed) ----
        if self.clicked:
            img = self.button_image_small
            r = img.get_rect(center=self.rect.center)
            self.window.blit(img, r.topleft)
        else:
            self.window.blit(self.button_image, self.rect.topleft)

        # ---- Text ----
        font = self.font_small if self.clicked else self.font
        txt = font.render(self.text, True, self._text_color())
        self.window.blit(txt, txt.get_rect(center=self.rect.center))

    def _draw_glow(self, colour):
        glow = self.glow_images.get(colour)
        if glow:
            self.window.blit(glow, glow.get_rect(center=self.rect.center).topleft)

    def _text_color(self):
        if self.disabled:
            return settings.CONFIRM_BUTTON_TEXT_COLOR_DISABLED
        if self.hovered:
            return settings.CONFIRM_BUTTON_TEXT_COLOR_HOVERED
        if self.active:
            return settings.CONFIRM_BUTTON_TEXT_COLOR_ACTIVE
        return settings.CONFIRM_BUTTON_TEXT_COLOR_PASSIVE

    def update(self):
        if not self.disabled:
            self.hovered = self.collide()
            self.clicked = self.hovered and _get_pressed()[0]
        else:
            self.hovered = False
            self.clicked = False
        haptics.tap_edge(self)
