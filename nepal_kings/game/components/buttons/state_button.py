# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
from config import settings
import pygame
from game.core.input_state import get_pressed as _get_pressed

class StateButton:
    def __init__(self, 
                 window,
                 name,
                 symbol_img,
                 x: int = 0,
                 y: int = 0,
                 symbol_width: int = None,
                 glow_width: int = None,
                 symbol_width_big: int = None,
                 glow_width_big: int = None,
                 glow_shift: int = None,
                 state = None,
                 hover_text_active = '',
                 hover_text_passive = '',
                 subscreen = None,
                 track_turn = False,
                 track_invader = False,
                 track_ceasefire = False,
                 ):
        self.window = window
        self.name = name
        self.x = x
        self.y = y
        self.glow_shift = glow_shift if glow_shift is not None else settings.GAME_BUTTON_GLOW_SHIFT
        self.font = settings.get_font(settings.GAME_BUTTON_FONT_SIZE)
        self.state = state
        self.subscreen_trigger = subscreen
        self.track_turn = track_turn
        self.track_invader = track_invader
        self.track_ceasefire = track_ceasefire

        # Load images
        self.images = []

        self.image_symbol_active_origin = pygame.image.load(
            settings.STATE_BUTTON_SYMBOL_IMG_PATH + symbol_img + '_active.png')
        self.image_symbol_passive_origin = pygame.image.load(
            settings.STATE_BUTTON_SYMBOL_IMG_PATH + symbol_img + '_passive.png')

        self.image_glow_yellow = pygame.image.load(settings.STATE_BUTTON_GLOW_IMG_PATH +'yellow.png')
        self.image_glow_white = pygame.image.load(settings.STATE_BUTTON_GLOW_IMG_PATH +'white.png')
        self.image_glow_black = pygame.image.load(settings.STATE_BUTTON_GLOW_IMG_PATH + 'black.png')
        self.image_glow_orange = pygame.image.load(settings.STATE_BUTTON_GLOW_IMG_PATH + 'orange.png')


        # Scale images to the given width and height
        symbol_width = symbol_width if symbol_width is not None else settings.STATE_BUTTON_SYMBOL_WIDTH
        symbol_width_big = symbol_width_big if symbol_width_big is not None else symbol_width
        glow_width = glow_width if glow_width is not None else settings.STATE_BUTTON_GLOW_WIDTH
        glow_width_big = glow_width_big if glow_width_big is not None else glow_width


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



        self.rect_symbol = self.image_symbol_active.get_rect()
        self.rect_glow = self.image_glow_yellow.get_rect()
        self.rect_symbol_big = self.image_symbol_active_big.get_rect()
        self.rect_glow_big = self.image_glow_yellow_big.get_rect()

        # Adjust positions based on image dimensions
        self.rect_symbol.center = (self.x, self.y)
        self.rect_glow.center = (self.x, self.y)
        self.rect_symbol_big.center = (self.x, self.y)
        self.rect_glow_big.center = (self.x, self.y)

        # Initialize button states
        self.clicked = False
        self.hovered = False

        self.hover_text_active = hover_text_active
        self.hover_text_passive = hover_text_passive

        # Tooltip font (dedicated smaller size for pill)
        self._tt_font = settings.get_font(settings.TOOLTIP_FONT_SIZE)
        self._tt_surf_active = self._tt_font.render(self.hover_text_active, True, settings.TOOLTIP_TEXT_COLOR)
        self._tt_surf_passive = self._tt_font.render(self.hover_text_passive, True, settings.TOOLTIP_TEXT_COLOR)

        self.active = True

    def collide(self):
        mx, my = pygame.mouse.get_pos()
        return self.rect_symbol.collidepoint((mx, my))

    def draw(self):
        """Draw button graphics (glow and symbol) only. Hover text is drawn separately."""
        # Depending on the state of the game and mouse interaction, blit the appropriate image
        if self.state.game:
            if self.active:
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
        """Draw a styled tooltip pill anchored to the right of the icon."""
        if not (self.state.game and self.hovered):
            return

        text_surf = self._tt_surf_active if self.active else self._tt_surf_passive
        dot_clr = settings.TOOLTIP_DOT_ACTIVE_CLR if self.active else settings.TOOLTIP_DOT_PASSIVE_CLR

        pad_x = settings.TOOLTIP_PAD_X
        pad_y = settings.TOOLTIP_PAD_Y
        dot_r = settings.TOOLTIP_DOT_RADIUS
        dot_sp = settings.TOOLTIP_DOT_SPACING
        corner_r = settings.TOOLTIP_CORNER_R

        tw, th = text_surf.get_size()
        pill_w = pad_x + dot_r * 2 + dot_sp + tw + pad_x
        pill_h = th + pad_y * 2

        # Anchor to the right of the icon centre
        pill_x = self.x + settings.STATE_BUTTON_SYMBOL_WIDTH // 2 + settings.TOOLTIP_OFFSET_X
        pill_y = self.y - pill_h // 2 + settings.TOOLTIP_OFFSET_Y

        # Clamp to screen
        pill_x = min(pill_x, settings.SCREEN_WIDTH - pill_w - 4)
        pill_y = max(4, min(pill_y, settings.SCREEN_HEIGHT - pill_h - 4))

        # Draw pill background
        pill = pygame.Surface((pill_w, pill_h), pygame.SRCALPHA)
        pygame.draw.rect(pill, settings.TOOLTIP_BG_COLOR,
                         (0, 0, pill_w, pill_h), border_radius=corner_r)
        pygame.draw.rect(pill, settings.TOOLTIP_BORDER_COLOR,
                         (0, 0, pill_w, pill_h),
                         settings.TOOLTIP_BORDER_WIDTH, border_radius=corner_r)
        self.window.blit(pill, (pill_x, pill_y))

        # Draw status dot
        dot_cx = pill_x + pad_x + dot_r
        dot_cy = pill_y + pill_h // 2
        pygame.draw.circle(self.window, dot_clr, (dot_cx, dot_cy), dot_r)

        # Draw text
        self.window.blit(text_surf, (pill_x + pad_x + dot_r * 2 + dot_sp, pill_y + pad_y))

    def update(self, state):
        self.state = state
        if self.state.game:
            #self.game = self.state.game
            #self.game = state.game
            self.hovered = self.collide()
            if self.hovered and _get_pressed()[0]:
                self.clicked = True
            else:
                self.clicked = False

            if self.track_turn:
                # During battle phase, track battle turn instead of build-up turn
                if getattr(self.state.game, 'in_battle_phase', False) and self.state.game.battle_turn_player_id:
                    self.active = self.state.game.battle_turn_player_id == self.state.game.player_id
                elif self.state.game.turn:
                    self.active = True
                else:
                    self.active = False

            if self.track_invader:
                if self.state.game.invader:
                    self.active = False
                else:
                    self.active = True

            if self.track_ceasefire:
                if self.state.game.ceasefire_active:
                    self.active = True
                else:
                    self.active = False

            