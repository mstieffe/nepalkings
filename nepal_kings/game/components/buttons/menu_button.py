# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Menu and screen-control button widgets."""

import pygame

from config import settings
from game.core.input_state import get_pressed as _get_pressed
from utils import haptics
from utils import sound


class Button:
    def __init__(self, window, x=0, y=0, text="", width=None, height=None):
        self.window = window
        self.x = x
        self.y = y
        self.text = text

        # Load font settings
        self.font = settings.get_font(settings.FONT_SIZE_BUTTON)
        self.font_small = settings.get_font(int(settings.FONT_SIZE_BUTTON * 0.9))

        # Set button dimensions based on text and provided width/height
        self.set_dimensions(width, height)

        # Load button images
        self.load_images()

        # Button states
        self.hovered = False
        self.clicked = False
        self.active = False

    def set_dimensions(self, width, height):
        """Calculate button dimensions and text alignment."""
        text_obj = self.font.render(self.text, True, settings.TEXT_COLOR_PASSIVE)
        button_width = max(width or settings.MENU_BUTTON_WIDTH, text_obj.get_width() + settings.SMALL_SPACER_X)
        button_height = height or settings.MENU_BUTTON_HEIGHT

        # Define button rectangle
        self.rect = pygame.Rect(self.x, self.y, button_width, button_height)

    def load_images(self):
        """Load button and glow images and apply scaling."""
        self.button_image = pygame.transform.scale(
            pygame.image.load(settings.MENU_BUTTON_IMG_PATH),
            (self.rect.width, self.rect.height)
        )
        self.button_image_small = pygame.transform.scale(self.button_image, (self.rect.width * 0.9, self.rect.height * 0.9))

        # Load glow images and scale
        self.glow_images = {
            "yellow": pygame.transform.scale(pygame.image.load(settings.MENU_BUTTON_GLOW_DIR + 'yellow.png'),
                                             (self.rect.width * 0.85, self.rect.height * 0.6)),
            "white": pygame.transform.scale(pygame.image.load(settings.MENU_BUTTON_GLOW_DIR + 'white.png'),
                                            (self.rect.width * 0.85, self.rect.height * 0.6)),
            "orange": pygame.transform.scale(pygame.image.load(settings.MENU_BUTTON_GLOW_DIR + 'orange.png'),
                                             (self.rect.width * 0.85, self.rect.height * 0.6)),
        }

    def collide(self):
        """Check if the mouse is over the button (mobile: padded hit area)."""
        pad = settings.TOUCH_HIT_PAD
        hit = self.rect.inflate(2 * pad, 2 * pad) if pad else self.rect
        return hit.collidepoint(pygame.mouse.get_pos())

    def draw(self):
        """Draw the button, including the background, glow, and text."""
        # Check if button is disabled
        is_disabled = hasattr(self, 'disabled') and self.disabled

        # Draw button background
        self.window.blit(self.button_image if not self.clicked else self.button_image_small,
                         self.rect.topleft if not self.clicked else self.button_image_small.get_rect(center=self.rect.center).topleft)

        # Draw glow based on button state (no glow if disabled)
        if not is_disabled:
            if self.hovered and self.clicked:
                self.draw_glow("yellow")
            elif self.hovered and not self.active:
                self.draw_glow("white")
            elif self.active:
                self.draw_glow("orange")

        # Draw text with appropriate size and color
        text_obj = (self.font_small if self.clicked else self.font).render(self.text, True, self.get_text_color())
        self.window.blit(text_obj, text_obj.get_rect(center=self.rect.center))

    def draw_glow(self, color):
        """Draw the glow image based on the given color."""
        glow_image = self.glow_images.get(color)
        if glow_image:
            self.window.blit(glow_image, glow_image.get_rect(center=self.rect.center).topleft)

    def get_text_color(self):
        """Return the appropriate text color based on the button state."""
        # Check if button is disabled
        if hasattr(self, 'disabled') and self.disabled:
            return (100, 100, 100)  # Grey color for disabled state

        if self.hovered:
            return settings.MENU_BUTTON_TEXT_COLOR_HOVERED
        elif self.active:
            return settings.MENU_BUTTON_TEXT_COLOR_ACTIVE
        return settings.TEXT_COLOR_PASSIVE

    def update(self):
        """Update the button's state based on mouse interaction."""
        # Don't allow hover or click if button is disabled
        is_disabled = hasattr(self, 'disabled') and self.disabled

        if is_disabled:
            self.hovered = False
            self.clicked = False
        else:
            self.hovered = self.collide()
            self.clicked = self.hovered and _get_pressed()[0]
        haptics.tap_edge(self)
        sound.tap_edge(self)


class ControlButton(Button):

    def __init__(self, window, x: int = 0, y: int = 0, text: str = ""):
        super().__init__(window, x, y, text)
        self.font = settings.get_font(settings.LOGOUT_FONT_SIZE)
        self.rect = pygame.Rect(self.x, self.y, settings.CONTROL_BUTTON_WIDTH, settings.CONTROL_BUTTON_HEIGHT)

    def draw(self):
        pygame.draw.rect(self.window, self.color_rect, self.rect)
        text_obj = self.font.render(self.text, True, self.color_text)
        text_rect = text_obj.get_rect(center=(self.x + settings.CONTROL_BUTTON_WIDTH / 2, self.y + settings.CONTROL_BUTTON_HEIGHT / 2))
        self.window.blit(text_obj, text_rect)

    def update(self):
        mx, my = pygame.mouse.get_pos()
        if self.rect.collidepoint((mx, my)):
            self.color_rect = settings.BUTTON_COLOR_ACTIVE  # Hover color
            self.color_text = settings.TEXT_COLOR_ACTIVE
        else:
            self.color_rect = settings.BUTTON_COLOR_PASSIVE  # Default color
            self.color_text = settings.TEXT_COLOR_PASSIVE


# Preserve legacy runtime metadata for repr/pickle compatibility while
# ``utils.utils`` remains the supported public import path.
Button.__module__ = 'utils.utils'
ControlButton.__module__ = 'utils.utils'
