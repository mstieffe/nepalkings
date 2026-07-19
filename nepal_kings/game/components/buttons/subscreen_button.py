# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Sub-screen tab button widget."""

import pygame

from config import settings
from game.core.input_state import get_pressed as _get_pressed
from utils import haptics
from utils import sound


class SubScreenButton:
    def __init__(self, window, x=0, y=0, text="", width=None, height=None, button_img_active=None, button_img_inactive=None):
        self.window = window
        self.x = x
        self.y = y
        self.text = text
        self.button_img_active_path = button_img_active
        self.button_img_inactive_path = button_img_inactive

        # Load font settings
        self.font = settings.get_font(settings.FONT_SIZE_SUBSCREEN_BUTTON)
        self.font_small = settings.get_font(int(settings.FONT_SIZE_SUBSCREEN_BUTTON * 0.9))

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
        button_width = max(width or settings.SUB_SCREEN_BUTTON_WIDTH, text_obj.get_width() + settings.SMALL_SPACER_X)
        button_height = height or settings.SUB_SCREEN_BUTTON_HEIGHT

        # Define button rectangle
        self.rect = pygame.Rect(self.x, self.y, button_width, button_height)

    def load_images(self):
        """Load button and glow images and apply scaling."""
        # Load custom active/inactive images if provided, otherwise use default
        if self.button_img_active_path and self.button_img_inactive_path:
            self.button_image_active = pygame.transform.scale(
                pygame.image.load(self.button_img_active_path),
                (self.rect.width, self.rect.height)
            )
            self.button_image_active_small = pygame.transform.scale(
                self.button_image_active,
                (int(self.rect.width * 0.9), int(self.rect.height * 0.9))
            )
            self.button_image_inactive = pygame.transform.scale(
                pygame.image.load(self.button_img_inactive_path),
                (self.rect.width, self.rect.height)
            )
            self.button_image_inactive_small = pygame.transform.scale(
                self.button_image_inactive,
                (int(self.rect.width * 0.9), int(self.rect.height * 0.9))
            )
        else:
            # Use default button image for all states
            self.button_image = pygame.transform.scale(
                pygame.image.load(settings.SUB_SCREEN_BUTTON_IMG_PATH),
                (self.rect.width, self.rect.height)
            )
            self.button_image_small = pygame.transform.scale(
                self.button_image,
                (int(self.rect.width * 0.9), int(self.rect.height * 0.9))
            )
            self.button_image_active = self.button_image
            self.button_image_active_small = self.button_image_small
            self.button_image_inactive = self.button_image
            self.button_image_inactive_small = self.button_image_small

        # Load glow images and scale
        self.glow_images = {
            "yellow": pygame.transform.scale(pygame.image.load(settings.MENU_BUTTON_GLOW_DIR + 'yellow.png'),
                                             (self.rect.width * 1.4, self.rect.height * 1.4)),
            "white": pygame.transform.scale(pygame.image.load(settings.MENU_BUTTON_GLOW_DIR + 'white.png'),
                                            (self.rect.width * 1.4, self.rect.height * 1.4)),
            "orange": pygame.transform.scale(pygame.image.load(settings.MENU_BUTTON_GLOW_DIR + 'orange.png'),
                                             (self.rect.width * 1.4, self.rect.height * 1.4)),
            "black": pygame.transform.scale(pygame.image.load(settings.MENU_BUTTON_GLOW_DIR + 'black.png'),
                                             (self.rect.width * 1.4, self.rect.height * 1.4)),
        }


    def collide(self):
        """Check if the mouse is over the button.

        On mobile the hit area is padded vertically only — sub-screen
        tabs sit in a tight horizontal row, so widening would let
        neighbouring tabs' hit areas overlap.
        """
        pad = settings.TOUCH_HIT_PAD
        hit = self.rect.inflate(0, 2 * pad) if pad else self.rect
        return hit.collidepoint(pygame.mouse.get_pos())

    def draw(self):
        """Draw the button, including the background, glow, and text."""

        # Draw glow based on button state
        if self.hovered and self.clicked:
            self.draw_glow("yellow")
        elif self.hovered and not self.active:
            self.draw_glow("yellow")
        elif self.hovered and self.active:
            self.draw_glow("yellow")
        elif self.active:
            self.draw_glow("orange")
        else:
            self.draw_glow("white")

        # Select button image based on active state
        if self.active:
            button_img = self.button_image_active if not self.clicked else self.button_image_active_small
        else:
            button_img = self.button_image_inactive if not self.clicked else self.button_image_inactive_small

        # Draw button background
        self.window.blit(button_img,
                         self.rect.topleft if not self.clicked else button_img.get_rect(center=self.rect.center).topleft)

        # Draw text with appropriate size
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


# Preserve legacy runtime metadata for repr/pickle compatibility while
# ``utils.utils`` remains the supported public import path.
SubScreenButton.__module__ = 'utils.utils'
