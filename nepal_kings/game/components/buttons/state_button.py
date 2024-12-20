from config import settings
import pygame

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
                 ):
        self.window = window
        self.name = name
        self.x = x
        self.y = y
        self.glow_shift = glow_shift if glow_shift is not None else settings.GAME_BUTTON_GLOW_SHIFT
        self.font = pygame.font.Font(settings.FONT_PATH, settings.GAME_BUTTON_FONT_SIZE)
        self.state = state
        self.subscreen_trigger = subscreen
        self.track_turn = track_turn
        self.track_invader = track_invader

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

        self.hover_text_active = hover_text_active  # Store the hover_text
        self.hover_text_passive = hover_text_passive  # Store the hover_text
        self.text_surface_active = self.font.render(self.hover_text_active, True, settings.STATE_BUTTON_TEXT_COLOR_ACTIVE)  # Prepare the text surface
        self.text_surface_passive = self.font.render(self.hover_text_passive, True, settings.STATE_BUTTON_TEXT_COLOR_PASSIVE)  # Prepare the text surface
        self.text_surface_shadow_active = self.font.render(self.hover_text_active, True, settings.STATE_BUTTON_TEXT_COLOR_SHADOW)  # Prepare the text surface
        self.text_surface_shadow_passive = self.font.render(self.hover_text_passive, True, settings.STATE_BUTTON_TEXT_COLOR_SHADOW)  # Prepare the text surface
        self.text_rect = self.text_surface_active.get_rect()  # Get the rectangle for positioning text

        self.active = True

    def collide(self):
        mx, my = pygame.mouse.get_pos()
        return self.rect_symbol.collidepoint((mx, my))

    def draw(self):
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
                    mx, my = pygame.mouse.get_pos()
                    self.text_rect.center = (mx - settings.GAME_BUTTON_TEXT_SHIFT_X +1, my - settings.STATE_BUTTON_TEXT_SHIFT_Y -1)
                    self.window.blit(self.text_surface_shadow_active, self.text_rect)
                    self.text_rect.center = (mx - settings.GAME_BUTTON_TEXT_SHIFT_X, my - settings.STATE_BUTTON_TEXT_SHIFT_Y)
                    self.window.blit(self.text_surface_active, self.text_rect)
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
                    mx, my = pygame.mouse.get_pos()
                    self.text_rect.center = (mx - settings.GAME_BUTTON_TEXT_SHIFT_X +1, my - settings.STATE_BUTTON_TEXT_SHIFT_Y -1)
                    self.window.blit(self.text_surface_shadow_passive, self.text_rect)
                    self.text_rect.center = (mx - settings.GAME_BUTTON_TEXT_SHIFT_X, my - settings.STATE_BUTTON_TEXT_SHIFT_Y)
                    self.window.blit(self.text_surface_passive, self.text_rect)
                else:
                    self.window.blit(self.image_glow_black, self.rect_glow.topleft)
                    self.window.blit(self.image_symbol_passive, self.rect_symbol.topleft)

    def update(self, state):
        self.state = state
        if self.state.game:
            #self.game = self.state.game
            #self.game = state.game
            self.hovered = self.collide()
            if self.hovered and pygame.mouse.get_pressed()[0]:
                self.clicked = True
            else:
                self.clicked = False

            if self.track_turn:
                if self.state.game.turn:
                    self.active = True
                else:
                    self.active = False

            if self.track_invader:
                if self.state.game.invader:
                    self.active = False
                else:
                    self.active = True

            