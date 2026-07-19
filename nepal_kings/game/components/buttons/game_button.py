# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""In-game navigation button widget."""

import pygame

from config import settings
from game.core.input_state import get_pressed as _get_pressed
from utils import haptics
from utils import sound


class GameButton:
    def __init__(self,
                 window,
                 name,
                 symbol_img,
                 stone_img,
                 x: int = 0,
                 y: int = 0,
                 symbol_width: int = None,
                 stone_width: int = None,
                 glow_width: int = None,
                 symbol_width_big: int = None,
                 glow_width_big: int = None,
                 glow_shift: int = None,
                 state = None,
                 hover_text = '',
                 subscreen = None,
                 screen = None,
                 track_turn = True,
                 locked = False,
                 tooltip_anchor = 'bottom'):
        self.window = window
        self.name = name
        self.x = x
        self.y = y
        self.locked = locked
        self.locked_clicked = False
        self.glow_shift = glow_shift if glow_shift is not None else settings.GAME_BUTTON_GLOW_SHIFT
        self.font = settings.get_font(settings.GAME_BUTTON_FONT_SIZE)
        self.state = state
        self.subscreen_trigger = subscreen
        self.screen_trigger = screen
        self.track_turn = track_turn
        self.tooltip_anchor = tooltip_anchor

        # Load images
        self.images = []

        self.image_stone = pygame.image.load(settings.GAME_BUTTON_STONE_IMG_PATH + stone_img + '.png')

        self.image_symbol_active_origin = pygame.image.load(
            settings.GAME_BUTTON_SYMBOL_IMG_PATH + symbol_img + '_active.png')
        self.image_symbol_passive_origin = pygame.image.load(
            settings.GAME_BUTTON_SYMBOL_IMG_PATH + symbol_img + '_passive.png')

        self.image_glow_yellow = pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH +'yellow.png')
        self.image_glow_white = pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH +'white.png')
        self.image_glow_black = pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH + 'black.png')
        self.image_glow_orange = pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH + 'orange.png')


        # Scale images to the given width and height
        symbol_width = symbol_width if symbol_width is not None else settings.GAME_BUTTON_SYMBOL_WIDTH
        symbol_width_big = symbol_width_big if symbol_width_big is not None else settings.GAME_BUTTON_SYMBOL_BIG_WIDTH
        glow_width = glow_width if glow_width is not None else settings.GAME_BUTTON_GLOW_WIDTH
        glow_width_big = glow_width_big if glow_width_big is not None else settings.GAME_BUTTON_GLOW_BIG_WIDTH
        stone_width = stone_width if stone_width is not None else settings.GAME_BUTTON_STONE_WIDTH


        # ...
        self.image_symbol_active = pygame.transform.smoothscale(self.image_symbol_active_origin, (symbol_width, symbol_width))
        self.image_symbol_passive = pygame.transform.smoothscale(self.image_symbol_passive_origin,(symbol_width, symbol_width))
        # ...
        self.image_symbol_active_big = pygame.transform.smoothscale(self.image_symbol_active_origin,(symbol_width_big, symbol_width_big))
        self.image_symbol_passive_big = pygame.transform.smoothscale(self.image_symbol_passive_origin, (symbol_width_big, symbol_width_big))

        self.image_glow_yellow = pygame.transform.smoothscale(self.image_glow_yellow, (glow_width, glow_width))
        self.image_glow_white = pygame.transform.smoothscale(self.image_glow_white, (glow_width, glow_width))
        self.image_glow_black = pygame.transform.smoothscale(self.image_glow_black, (glow_width, glow_width))
        self.image_glow_orange = pygame.transform.smoothscale(self.image_glow_orange, (glow_width, glow_width))


        self.image_glow_yellow_big = pygame.transform.smoothscale(self.image_glow_yellow, (glow_width_big, glow_width_big))
        self.image_glow_white_big = pygame.transform.smoothscale(self.image_glow_white, (glow_width_big, glow_width_big))
        self.image_glow_black_big = pygame.transform.smoothscale(self.image_glow_black, (glow_width_big, glow_width_big))
        self.image_glow_orange_big = pygame.transform.smoothscale(self.image_glow_orange, (glow_width_big, glow_width_big))

        self.image_stone = pygame.transform.smoothscale(self.image_stone, (stone_width, stone_width))


        self.rect_symbol = self.image_symbol_active.get_rect()
        self.rect_glow = self.image_glow_yellow.get_rect()
        self.rect_stone = self.image_symbol_passive.get_rect()
        self.rect_symbol_big = self.image_symbol_active_big.get_rect()
        self.rect_glow_big = self.image_glow_yellow_big.get_rect()

        # Adjust positions based on image dimensions
        symbol_width_diff = stone_width - symbol_width
        self.rect_symbol.center = (self.x+ symbol_width_diff // 2, self.y + symbol_width_diff // 2)
        self.rect_glow.center = (self.x - self.glow_shift + symbol_width_diff // 2, self.y - self.glow_shift + symbol_width_diff // 2)
        self.rect_stone.center = (self.x, self.y)
        self.rect_symbol_big.center = (self.x+ symbol_width_diff // 2, self.y + symbol_width_diff // 2)
        self.rect_glow_big.center = (self.x - self.glow_shift+ symbol_width_diff // 2, self.y - self.glow_shift + symbol_width_diff // 2)

        # Clickable footprint = the full visible stone, not the smaller
        # symbol — so taps anywhere on the button art register.
        self.rect_hit = self.image_stone.get_rect(topleft=self.rect_stone.topleft)

        # Initialize button states
        self.clicked = False
        self.hovered = False

        self.hover_text = hover_text
        # Tooltip pill surfaces
        self._tt_font = settings.get_font(settings.TOOLTIP_FONT_SIZE)
        self._tt_surf = self._tt_font.render(self.hover_text, True, settings.TOOLTIP_TEXT_COLOR)
        self._is_active_state = True  # tracked during draw for tooltip dot colour

    def collide(self):
        return self.rect_hit.collidepoint(pygame.mouse.get_pos())

    def draw(self):
        # Depending on the state of the game and mouse interaction, blit the appropriate image
        if self.state.game:
            self.window.blit(self.image_stone, self.rect_stone.topleft)
            if self.locked:
                self._is_active_state = False
                # Locked buttons show passive icon
                if self.hovered:
                    self.window.blit(self.image_glow_white, self.rect_glow.topleft)
                    self.window.blit(self.image_symbol_passive_big, self.rect_symbol_big.topleft)
                else:
                    self.window.blit(self.image_glow_black, self.rect_glow.topleft)
                    self.window.blit(self.image_symbol_passive, self.rect_symbol.topleft)
            elif self.state.game.turn or not self.track_turn:
                self._is_active_state = True
                if self.hovered:
                    if self.clicked:
                        self.window.blit(self.image_glow_orange_big, self.rect_glow_big.topleft)
                        self.window.blit(self.image_symbol_active, self.rect_symbol.topleft)
                    else:
                        self.window.blit(self.image_glow_yellow, self.rect_glow.topleft)
                        self.window.blit(self.image_symbol_active_big, self.rect_symbol_big.topleft)
                else:
                    self.window.blit(self.image_glow_black, self.rect_glow.topleft)
                    self.window.blit(self.image_symbol_active, self.rect_symbol.topleft)
            else:
                self._is_active_state = False
                if self.hovered:
                    if self.clicked:
                        self.window.blit(self.image_glow_black_big, self.rect_glow_big.topleft)
                        self.window.blit(self.image_symbol_passive, self.rect_symbol.topleft)
                    else:
                        self.window.blit(self.image_glow_white, self.rect_glow.topleft)
                        self.window.blit(self.image_symbol_passive_big, self.rect_symbol_big.topleft)
                else:
                    self.window.blit(self.image_glow_black, self.rect_glow.topleft)
                    self.window.blit(self.image_symbol_passive, self.rect_symbol.topleft)

    def draw_hover_text(self):
        """Draw a styled tooltip pill anchored relative to the button icon."""
        if not (self.state.game and self.hovered):
            return

        text_surf = self._tt_surf

        pad_x = settings.TOOLTIP_PAD_X
        pad_y = settings.TOOLTIP_PAD_Y
        corner_r = settings.TOOLTIP_CORNER_R

        tw, th = text_surf.get_size()
        pill_w = pad_x + tw + pad_x
        pill_h = th + pad_y * 2

        if self.tooltip_anchor == 'top-left':
            # Right edge of pill touches icon's top-left corner
            pill_x = self.rect_symbol.left - pill_w
            pill_y = self.rect_symbol.top - pill_h // 2
        else:
            # 'bottom' — centred below the glow area
            pill_x = self.x - pill_w // 2
            pill_y = self.rect_glow.bottom + settings.TOOLTIP_OFFSET_Y

        # Clamp to screen
        pill_x = max(4, min(pill_x, settings.SCREEN_WIDTH - pill_w - 4))
        pill_y = max(4, min(pill_y, settings.SCREEN_HEIGHT - pill_h - 4))

        # Draw pill background
        pill = pygame.Surface((pill_w, pill_h), pygame.SRCALPHA)
        pygame.draw.rect(pill, settings.TOOLTIP_BG_COLOR,
                         (0, 0, pill_w, pill_h), border_radius=corner_r)
        pygame.draw.rect(pill, settings.TOOLTIP_BORDER_COLOR,
                         (0, 0, pill_w, pill_h),
                         settings.TOOLTIP_BORDER_WIDTH, border_radius=corner_r)
        self.window.blit(pill, (pill_x, pill_y))

        # Draw text centred in the pill
        self.window.blit(text_surf, (pill_x + pad_x, pill_y + pad_y))

    def update(self, state):
        self.state = state
        if self.state.game:
            # Locked buttons track hover and click but don't trigger screen changes
            if self.locked:
                self.hovered = self.collide()
                if self.hovered and _get_pressed()[0]:
                    self.locked_clicked = True
                else:
                    self.locked_clicked = False
                self.clicked = False
                return

            self.hovered = self.collide()

            if self.hovered and _get_pressed()[0]:
                self.clicked = True
                # Allow all subscreen changes (including during waiting for counter response)
                # Action blocking happens at the action level, not screen access level
                if self.subscreen_trigger:
                    self.state.subscreen = self.subscreen_trigger
                if self.screen_trigger:
                    self.state.screen = self.screen_trigger
            else:
                self.clicked = False

            haptics.tap_edge(self)
            sound.tap_edge(self)


# Preserve legacy runtime metadata for repr/pickle compatibility while
# ``utils.utils`` remains the supported public import path.
GameButton.__module__ = 'utils.utils'
