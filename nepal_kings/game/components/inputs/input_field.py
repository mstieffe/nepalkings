# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Shared text input component."""

import sys

import pygame
from pygame.locals import *

from config import settings


class InputField:
    def __init__(self, window, x: int = 0, y: int = 0, name: str = "",
                 content: str = "", pwd: bool = False, active: bool = False,
                 max_length: int = 15, width: int = None, height: int = None,
                 web_overlay: bool = False):
        self.window = window
        self.x = x
        self.y = y
        self.name = name
        self.content = content
        self.pwd = pwd
        self.active = active  # Track if the field is currently active
        self.max_length = max_length
        self.web_overlay = bool(web_overlay)
        self.web_input_mode = 'text'
        self._web_input_pending = False

        self.color_rect = settings.INPUTFIELD_COLOR_PASSIVE
        self.color_text = settings.TEXT_COLOR_PASSIVE
        self.border_color = settings.INPUTFIELD_BORDER_COLOR_PASSIVE  # Border color for the input field
        self.font = settings.get_font(settings.INPUTFIELD_FONT_SIZE)
        self.font_title = settings.get_font(settings.INPUTFIELD_FONT_SIZE_TITLE)

        self.height = height or settings.INPUTFIELD_HEIGHT
        self.width = width or settings.INPUTFIELD_WIDTH

        self.rect = pygame.Rect(self.x, self.y, self.width, self.height)

        self.cursor_pos = 0
        self.cursor_surface = pygame.Surface((int(self.font.size('|')[0]), int(self.font.get_height())))
        self.cursor_surface.fill((0, 0, 0))  # Black cursor

    def handle_event(self, event):
        """Handle key and mouse events for the input field."""
        if event.type == KEYDOWN:
            if self.active:
                if event.key == K_BACKSPACE:
                    self.backspace()
                elif event.key == K_RETURN:
                    return 'submit'  # Indicates the user pressed Enter
                elif event.key == K_TAB:
                    return 'switch'  # Indicates the user pressed Tab
        elif event.type == pygame.TEXTINPUT:
            if self.active and len(self.content) < self.max_length:
                self.insert(event.text)
        elif event.type == MOUSEBUTTONDOWN:
            if self.collide():
                self.activate()
            else:
                self.deactivate()
        return None

    def insert(self, character):
        """Insert a character at the current cursor position."""
        self.content = self.content[:self.cursor_pos] + character + self.content[self.cursor_pos:]
        self.cursor_pos += 1

    def backspace(self):
        """Remove the character to the left of the cursor."""
        if self.cursor_pos > 0:
            self.content = self.content[:self.cursor_pos - 1] + self.content[self.cursor_pos:]
            self.cursor_pos = max(0, self.cursor_pos - 1)

    def empty(self):
        """Clear the input field content."""
        self.content = ''
        self.cursor_pos = 0

    def collide(self):
        """Check if the mouse is over the input field (mobile: padded hit area)."""
        pad = settings.TOUCH_HIT_PAD
        hit = self.rect.inflate(2 * pad, 2 * pad) if pad else self.rect
        return hit.collidepoint(pygame.mouse.get_pos())

    def activate(self):
        """Activate the input field, setting it as the active field."""
        self.active = True
        # Mobile login fields use a native, non-blocking HTML input so opening
        # the virtual keyboard does not suspend Web Audio. Other fields retain
        # the browser prompt as a compatibility fallback.
        if sys.platform == 'emscripten':
            from utils.web_keyboard import is_mobile, open_input, prompt
            if is_mobile():
                if self.web_overlay:
                    if open_input(
                            self.name, self.content, self.pwd, self.max_length,
                            getattr(self, 'web_input_mode', 'text')):
                        self._web_input_pending = True
                    return
                result = prompt(self.name, self.content, self.pwd)
                self.content = result[:self.max_length]
                self.cursor_pos = len(self.content)
                self.active = False

    def sync_web_input(self):
        """Mirror a canvas-aligned browser input into this field."""
        if not self.web_overlay and not self._web_input_pending:
            return False
        from utils.web_keyboard import poll_input
        state = poll_input(self.name)
        if state is None:
            return False

        done = bool(state.get('done'))
        value = str(state.get('value', self.content))
        self.content = value[:self.max_length]
        self.cursor_pos = len(self.content)

        if done:
            self._web_input_pending = False
            self.active = False
        else:
            self._web_input_pending = bool(state.get('active'))
            self.active = self._web_input_pending
        return True

    def deactivate(self):
        """Deactivate the input field, removing it from the active state."""
        self.active = False

    def draw(self):
        """Draw the input field, including the name, content, and cursor."""
        # Update border color based on the active state
        self.border_color = settings.INPUTFIELD_BORDER_COLOR_ACTIVE if self.active else settings.INPUTFIELD_BORDER_COLOR_PASSIVE

        # Draw the border around the input field
        border_rect = self.rect.inflate(6, 6)  # Slightly larger than the input field
        pygame.draw.rect(self.window, self.border_color, border_rect)

        # Draw the rectangle around the input field
        pygame.draw.rect(self.window, self.color_rect, self.rect)

        # Name of input field
        text_obj = self.font_title.render(self.name, True, settings.INPUTFIELD_TEXT_COLOR_HEADER)
        text_rect = text_obj.get_rect(midleft=(self.x, self.y - settings.SMALL_SPACER_Y))
        self.window.blit(text_obj, text_rect)

        # Display the content of the input field, obfuscating content if it's a password field
        visible_content = '*' * len(self.content) if self.pwd else self.content
        text_obj = self.font.render(visible_content, True, self.color_text)
        text_rect = text_obj.get_rect(midleft=(self.x + settings.TINY_SPACER_X, self.y + self.height / 2))
        self.window.blit(text_obj, text_rect)

        # Draw the cursor
        if self.active:
            cursor_y_pos = self.y + (self.height - self.cursor_surface.get_height()) // 2
            cursor_x_pos = self.x + settings.TINY_SPACER_X + self.font.size(visible_content[:self.cursor_pos])[0]
            self.window.blit(self.cursor_blink(), (cursor_x_pos, cursor_y_pos))

    def update_color(self):
        """Update the color of the input field based on whether the mouse is hovering over it."""
        mx, my = pygame.mouse.get_pos()
        if self.rect.collidepoint((mx, my)):
            self.color_rect = settings.INPUTFIELD_COLOR_ACTIVE  # Hover color
            self.color_text = settings.TEXT_COLOR_ACTIVE
        else:
            self.color_rect = settings.INPUTFIELD_COLOR_PASSIVE  # Default color
            self.color_text = settings.TEXT_COLOR_PASSIVE

    def cursor_blink(self):
        """Blink the cursor every 500 milliseconds."""
        if pygame.time.get_ticks() % 1000 // 500:  # Blinking every 500ms
            return self.cursor_surface
        else:
            return pygame.Surface((0, 0))  # Transparent surface when cursor is "invisible"


# Keep historical repr and pickle lookup behavior while utils.utils re-exports
# this canonical implementation.
InputField.__module__ = 'utils.utils'
