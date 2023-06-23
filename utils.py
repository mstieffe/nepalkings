import settings
import pygame

import pygame
import settings

import pygame
from collections import Counter

class FigureIconButton:

    def __init__(self,
                 window,
                 game,
                 fig,
                 content,
                 x: int = 0,
                 y: int = 0):
        self.window = window
        self.game = game
        self.x = x
        self.y = y
        self.fig=fig
        self.content=content
        self.font = pygame.font.Font(settings.FONT_PATH, settings.GAME_BUTTON_FONT_SIZE)

        self.is_active = False

        icon_mask_img = pygame.image.load(settings.FIGURE_ICON_IMG_PATH+ 'mask.png')
        self.icon_mask_img = pygame.transform.scale(icon_mask_img, (settings.FIGURE_ICON_MASK_WIDTH, settings.FIGURE_ICON_MASK_HEIGHT))
        self.icon_mask_big_img = pygame.transform.scale(icon_mask_img, (settings.FIGURE_ICON_MASK_BIG_WIDTH, settings.FIGURE_ICON_MASK_BIG_HEIGHT))

        #self.icon_img = self.fig.icon_img
        self.icon_img = pygame.transform.scale(self.fig.icon_img, (settings.FIGURE_ICON_WIDTH, settings.FIGURE_ICON_HEIGHT))
        self.icon_big_img = pygame.transform.scale(self.fig.icon_img, (settings.FIGURE_ICON_BIG_WIDTH, settings.FIGURE_ICON_BIG_HEIGHT))

        self.icon_darkwhite_img = pygame.transform.scale(self.fig.icon_darkwhite_img, (settings.FIGURE_ICON_WIDTH, settings.FIGURE_ICON_HEIGHT))
        self.icon_darkwhite_big_img = pygame.transform.scale(self.fig.icon_darkwhite_img, (settings.FIGURE_ICON_BIG_WIDTH, settings.FIGURE_ICON_BIG_HEIGHT))

        self.image_glow_yellow = pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH +'yellow.png')
        self.image_glow_white = pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH +'white.png')
        self.image_glow_black = pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH +'black.png')
        self.image_glow_orange = pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH + 'orange.png')

        self.image_glow_yellow = pygame.transform.scale(self.image_glow_yellow, (settings.FIGURE_ICON_GLOW_WIDTH, settings.FIGURE_ICON_GLOW_WIDTH))
        self.image_glow_white = pygame.transform.scale(self.image_glow_white, (settings.FIGURE_ICON_GLOW_WIDTH, settings.FIGURE_ICON_GLOW_WIDTH))
        self.image_glow_black = pygame.transform.scale(self.image_glow_black, (settings.FIGURE_ICON_GLOW_WIDTH, settings.FIGURE_ICON_GLOW_WIDTH))
        self.image_glow_orange = pygame.transform.scale(self.image_glow_orange, (settings.FIGURE_ICON_GLOW_WIDTH, settings.FIGURE_ICON_GLOW_WIDTH))


        self.image_glow_yellow_big = pygame.transform.scale(self.image_glow_yellow, (settings.FIGURE_ICON_GLOW_BIG_WIDTH, settings.FIGURE_ICON_GLOW_BIG_WIDTH))
        self.image_glow_white_big = pygame.transform.scale(self.image_glow_white, (settings.FIGURE_ICON_GLOW_BIG_WIDTH, settings.FIGURE_ICON_GLOW_BIG_WIDTH))
        self.image_glow_orange_big = pygame.transform.scale(self.image_glow_orange, (settings.FIGURE_ICON_GLOW_BIG_WIDTH, settings.FIGURE_ICON_GLOW_BIG_WIDTH))

        self.rect_mask= self.icon_mask_img.get_rect()
        self.rect_icon = self.icon_img.get_rect()
        self.rect_glow = self.image_glow_yellow.get_rect()
        self.rect_mask_big= self.icon_mask_big_img.get_rect()
        self.rect_icon_big = self.icon_big_img.get_rect()
        self.rect_glow_big = self.image_glow_yellow_big.get_rect()

        # Adjust positions based on image dimensions
        width_diff_icon = settings.FIGURE_ICON_GLOW_BIG_WIDTH - settings.FIGURE_ICON_WIDTH
        width_diff_mask = settings.FIGURE_ICON_GLOW_BIG_WIDTH - settings.FIGURE_ICON_MASK_WIDTH
        width_diff_glow = settings.FIGURE_ICON_GLOW_BIG_WIDTH - settings.FIGURE_ICON_GLOW_WIDTH
        width_diff_icon_big = settings.FIGURE_ICON_GLOW_BIG_WIDTH - settings.FIGURE_ICON_BIG_WIDTH
        width_diff_mask_big = settings.FIGURE_ICON_GLOW_BIG_WIDTH - settings.FIGURE_ICON_MASK_BIG_WIDTH

        #self.rect_mask.center = (self.x + width_diff_mask//2, self.y + width_diff_mask//2)
        #self.rect_icon.center = (self.x + width_diff_icon//2, self.y + width_diff_icon//2)
        #self.rect_glow.center = (self.x + width_diff_glow//2, self.y + width_diff_glow//2)
        #self.rect_mask_big.center = (self.x + width_diff_mask_big//2, self.y + width_diff_mask_big//2)
        #self.rect_icon_big.center = (self.x + width_diff_icon_big//2, self.y + width_diff_icon_big//2)
        #self.rect_glow_big.center = (self.x, self.y)


        self.rect_mask.center = (self.x, self.y)
        self.rect_icon.center = (self.x, self.y)
        self.rect_glow.center = (self.x, self.y)
        self.rect_mask_big.center = (self.x, self.y)
        self.rect_icon_big.center = (self.x, self.y)
        self.rect_glow_big.center = (self.x, self.y)
        # Initialize button states
        self.clicked = False
        self.hovered = False

        self.hover_text = self.fig.name  # Store the hover_text
        self.text_surface_active = self.font.render(self.hover_text, True,
                                                    settings.GAME_BUTTON_TEXT_COLOR_ACTIVE)  # Prepare the text surface
        self.text_surface_passive = self.font.render(self.hover_text, True,
                                                     settings.GAME_BUTTON_TEXT_COLOR_PASSIVE)  # Prepare the text surface
        self.text_surface_shadow = self.font.render(self.hover_text, True,
                                                    settings.GAME_BUTTON_TEXT_COLOR_SHADOW)  # Prepare the text surface
        self.text_rect = self.text_surface_active.get_rect()  # Get the rectangle for positioning text

    def is_in_hand(self, suit=None):
        main_cards, side_cards = self.game.get_hand()
        cards = main_cards + side_cards
        if suit:
            cards = [(card['suit'], card['rank']) for card in cards if card['suit'] == suit]
        else:
            cards = [(card['suit'], card['rank']) for card in cards]
        cards_counter = Counter(cards)

        for fig in self.content:
            fig_cards_counter = Counter(fig.cards)
            if all(cards_counter[card] >= fig_cards_counter[card] for card in fig_cards_counter):
                return True
        return False
    def collide(self):
        mx, my = pygame.mouse.get_pos()
        return self.rect_mask.collidepoint((mx, my))

    def draw(self):
            if self.is_active:
                icon_img = self.icon_img
                icon_big_img = self.icon_big_img
                glow_img = self.image_glow_yellow
                glow_big_img = self.image_glow_orange_big
            else:
                icon_img = self.icon_darkwhite_img
                icon_big_img = self.icon_darkwhite_big_img
                glow_img = self.image_glow_black
                glow_big_img = self.image_glow_white_big

            if self.hovered:
                if self.clicked:
                    self.window.blit(glow_big_img, self.rect_glow_big.topleft)
                    self.window.blit(icon_img, self.rect_icon.topleft)
                    self.window.blit(self.icon_mask_img, self.rect_mask.topleft)
                else:
                    self.window.blit(glow_img, self.rect_glow.topleft)
                    self.window.blit(icon_big_img, self.rect_icon_big.topleft)
                    self.window.blit(self.icon_mask_big_img, self.rect_mask_big.topleft)
                mx, my = pygame.mouse.get_pos()
                self.text_rect.center = (mx - settings.GAME_BUTTON_TEXT_SHIFT_X +1, my - settings.GAME_BUTTON_TEXT_SHIFT_Y -1)
                self.window.blit(self.text_surface_shadow, self.text_rect)
                self.text_rect.center = (mx - settings.GAME_BUTTON_TEXT_SHIFT_X, my - settings.GAME_BUTTON_TEXT_SHIFT_Y)
                self.window.blit(self.text_surface_active, self.text_rect)
            else:
                #self.window.blit(self.image_glow_black, self.rect_glow.topleft)
                self.window.blit(icon_img, self.rect_icon.topleft)
                self.window.blit(self.icon_mask_img, self.rect_mask.topleft)

    def update(self, game):
        self.game = game
        if self.game:
            self.is_active = self.is_in_hand()
            #self.game = self.state.game
            #self.game = state.game
            self.hovered = self.collide()

            if self.hovered and pygame.mouse.get_pressed()[0]:
                self.clicked = True
                #self.state.subscreen = self.subscreen_trigger
            else:
                self.clicked = False

class GameButton:
    def __init__(self, window,
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
                 subscreen = 'field'):
        self.window = window
        self.x = x
        self.y = y
        self.glow_shift = glow_shift if glow_shift is not None else settings.GAME_BUTTON_GLOW_SHIFT
        self.font = pygame.font.Font(settings.FONT_PATH, settings.GAME_BUTTON_FONT_SIZE)
        self.state = state
        self.subscreen_trigger = subscreen

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
        self.image_symbol_active = pygame.transform.scale(self.image_symbol_active_origin, (symbol_width, symbol_width))
        self.image_symbol_passive = pygame.transform.scale(self.image_symbol_passive_origin,(symbol_width, symbol_width))
        # ...
        self.image_symbol_active_big = pygame.transform.scale(self.image_symbol_active_origin,(symbol_width_big, symbol_width_big))
        self.image_symbol_passive_big = pygame.transform.scale(self.image_symbol_passive_origin, (symbol_width_big, symbol_width_big))

        self.image_glow_yellow = pygame.transform.scale(self.image_glow_yellow, (glow_width, glow_width))
        self.image_glow_white = pygame.transform.scale(self.image_glow_white, (glow_width, glow_width))
        self.image_glow_black = pygame.transform.scale(self.image_glow_black, (glow_width, glow_width))
        self.image_glow_orange = pygame.transform.scale(self.image_glow_orange, (glow_width, glow_width))


        self.image_glow_yellow_big = pygame.transform.scale(self.image_glow_yellow, (glow_width_big, glow_width_big))
        self.image_glow_white_big = pygame.transform.scale(self.image_glow_white, (glow_width_big, glow_width_big))
        self.image_glow_black_big = pygame.transform.scale(self.image_glow_black, (glow_width_big, glow_width_big))
        self.image_glow_orange_big = pygame.transform.scale(self.image_glow_orange, (glow_width_big, glow_width_big))

        self.image_stone = pygame.transform.scale(self.image_stone, (stone_width, stone_width))


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

        # Initialize button states
        self.clicked = False
        self.hovered = False

        self.hover_text = hover_text  # Store the hover_text
        self.text_surface_active = self.font.render(self.hover_text, True, settings.GAME_BUTTON_TEXT_COLOR_ACTIVE)  # Prepare the text surface
        self.text_surface_passive = self.font.render(self.hover_text, True, settings.GAME_BUTTON_TEXT_COLOR_PASSIVE)  # Prepare the text surface
        self.text_surface_shadow = self.font.render(self.hover_text, True, settings.GAME_BUTTON_TEXT_COLOR_SHADOW)  # Prepare the text surface
        self.text_rect = self.text_surface_active.get_rect()  # Get the rectangle for positioning text

    def collide(self):
        mx, my = pygame.mouse.get_pos()
        return self.rect_symbol.collidepoint((mx, my))

    def draw(self):
        # Depending on the state of the game and mouse interaction, blit the appropriate image
        if self.state.game:
            self.window.blit(self.image_stone, self.rect_stone.topleft)
            if self.state.game.turn:
                if self.hovered:
                    if self.clicked:
                        self.window.blit(self.image_glow_orange_big, self.rect_glow_big.topleft)
                        self.window.blit(self.image_symbol_active, self.rect_symbol.topleft)
                    else:
                        self.window.blit(self.image_glow_yellow, self.rect_glow.topleft)
                        self.window.blit(self.image_symbol_active_big, self.rect_symbol_big.topleft)
                    mx, my = pygame.mouse.get_pos()
                    self.text_rect.center = (mx - settings.GAME_BUTTON_TEXT_SHIFT_X +1, my - settings.GAME_BUTTON_TEXT_SHIFT_Y -1)
                    self.window.blit(self.text_surface_shadow, self.text_rect)
                    self.text_rect.center = (mx - settings.GAME_BUTTON_TEXT_SHIFT_X, my - settings.GAME_BUTTON_TEXT_SHIFT_Y)
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
                        self.window.blit(self.image_symbol_passive_big, self.rect_symbol.topleft)
                    mx, my = pygame.mouse.get_pos()
                    self.text_rect.center = (mx - settings.GAME_BUTTON_TEXT_SHIFT_X +1, my - settings.GAME_BUTTON_TEXT_SHIFT_Y -1)
                    self.window.blit(self.text_surface_shadow, self.text_rect)
                    self.text_rect.center = (mx - settings.GAME_BUTTON_TEXT_SHIFT_X, my - settings.GAME_BUTTON_TEXT_SHIFT_Y)
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
                self.state.subscreen = self.subscreen_trigger
            else:
                self.clicked = False


class Button:
    def __init__(self, window, x: int = 0, y: int = 0, text: str = "", width: int = None, height: int = None):
        self.window = window
        self.x = x
        self.y = y
        self.text = text
        self.color_rect = settings.BUTTON_COLOR_PASSIVE
        self.color_text = settings.TEXT_COLOR_PASSIVE
        self.font = pygame.font.Font(settings.FONT_PATH, settings.FONT_SIZE)

        # Render the text and adjust the button width if necessary
        text_obj = self.font.render(self.text, True, self.color_text)
        text_rect = text_obj.get_rect()

        # If no custom width is provided, use the settings' button width
        button_width = width if width is not None else settings.BUTTON_WIDTH
        button_width = max(button_width, text_rect.width + settings.SMALL_SPACER_X)  # Adjusted button width

        button_height = height if height is not None else settings.BUTTON_HEIGHT

        # Adjust button width to fit text at initialization
        self.rect = pygame.Rect(self.x, self.y, button_width, button_height)

    def collide(self):
        mx, my = pygame.mouse.get_pos()
        return self.rect.collidepoint((mx, my))

    def draw(self):
        pygame.draw.rect(self.window, self.color_rect, self.rect)
        text_obj = self.font.render(self.text, True, self.color_text)

        # Re-calculate the center position of the text Rect
        text_rect = text_obj.get_rect(center=self.rect.center)

        self.window.blit(text_obj, text_rect)

    def update(self):
        mx, my = pygame.mouse.get_pos()
        if self.rect.collidepoint((mx, my)):
            self.color_rect = settings.BUTTON_COLOR_ACTIVE  # Hover color
            self.color_text = settings.TEXT_COLOR_ACTIVE
        else:
            self.color_rect = settings.BUTTON_COLOR_PASSIVE  # Default color
            self.color_text = settings.TEXT_COLOR_PASSIVE


class ControlButton(Button):

        def __init__(self, window, x: int = 0, y: int =0, text: str = ""):
            super().__init__(window, x, y, text)
            self.font = pygame.font.Font(settings.FONT_PATH, settings.LOGOUT_FONT_SIZE)
            self.rect = pygame.Rect(self.x, self.y, settings.CONTROL_BUTTON_WIDTH, settings.CONTROL_BUTTON_HEIGHT)

        def draw(self):
            pygame.draw.rect(self.window, self.color_rect, self.rect)
            text_obj = self.font.render(self.text, True, self.color_text)
            text_rect = text_obj.get_rect(center=(self.x + settings.CONTROL_BUTTON_WIDTH / 2, self.y + settings.CONTROL_BUTTON_HEIGHT / 2))
            self.window.blit(text_obj, text_rect)

        def update_color(self):
            mx, my = pygame.mouse.get_pos()
            if self.rect.collidepoint((mx, my)):
                self.color_rect = settings.BUTTON_COLOR_ACTIVE  # Hover color
                self.color_text = settings.TEXT_COLOR_ACTIVE
            else:
                self.color_rect = settings.BUTTON_COLOR_PASSIVE  # Default color
                self.color_text = settings.TEXT_COLOR_PASSIVE

class InputField():

    def __init__(self, window, x: int = 0, y: int =0, name: str = "", content: str = "", pwd: bool = False, active: bool = False):
        self.window = window
        self.x = x
        self.y = y
        self.name = name
        self.content = content
        self.pwd = pwd
        self.color_rect = settings.FIELD_COLOR_PASSIVE
        self.color_text = settings.TEXT_COLOR_PASSIVE
        self.font = pygame.font.Font(settings.FONT_PATH, settings.FONT_SIZE)
        self.rect = pygame.Rect(self.x, self.y, settings.SMALL_FIELD_WIDTH, settings.SMALL_FIELD_HEIGHT)

        self.cursor_pos = 0
        self.cursor_surface = pygame.Surface((int(self.font.size('|')[0]), int(self.font.get_height())))
        self.cursor_surface.fill((0, 0, 0))  # fill the cursor surface with black color

        self.active = active

    def insert(self, character):
        self.content = self.content[:self.cursor_pos] + character + self.content[self.cursor_pos:]
        self.cursor_pos += 1

    def backspace(self):
        if self.cursor_pos:
            self.content = self.content[:self.cursor_pos - 1] + self.content[self.cursor_pos:]
            self.cursor_pos = max(0, self.cursor_pos - 1)

    def empty(self):
        self.content = ''
        self.cursor_pos = 0

    def collide(self):
        mx, my = pygame.mouse.get_pos()
        return self.rect.collidepoint((mx, my))

    def draw(self):
        # Name of input field
        text_obj = self.font.render(self.name, True, settings.TEXT_COLOR_HEADER_INPUTFIELD)
        text_rect = text_obj.get_rect(midleft=(self.x, self.y - settings.SMALL_SPACER_Y))
        self.window.blit(text_obj, text_rect)

        # rect of input field
        pygame.draw.rect(self.window, self.color_rect, self.rect)

        # content of input field
        if self.pwd:
            visible_content = '*' * len(self.content)
        else:
            visible_content = self.content
        text_obj = self.font.render(visible_content, True, self.color_text)
        text_rect = text_obj.get_rect(midleft=(self.x + settings.TINY_SPACER_X, self.y + settings.SMALL_FIELD_HEIGHT / 2))
        self.window.blit(text_obj, text_rect)

        # curser
        cursor_y_pos = self.y + (settings.SMALL_FIELD_HEIGHT - self.cursor_surface.get_height()) // 2
        cursor_x_pos = self.x + settings.TINY_SPACER_X + self.font.size(visible_content[:self.cursor_pos])[0]
        if self.active:  # if this field is active
            self.window.blit(self.cursor_blink(), (cursor_x_pos, cursor_y_pos))

    def update_color(self):
        mx, my = pygame.mouse.get_pos()
        if self.rect.collidepoint((mx, my)):
            self.color_rect = settings.FIELD_COLOR_ACTIVE  # Hover color
            self.color_text = settings.TEXT_COLOR_ACTIVE
        else:
            self.color_rect = settings.FIELD_COLOR_PASSIVE  # Default color
            self.color_text = settings.TEXT_COLOR_PASSIVE

    def cursor_blink(self):
        if pygame.time.get_ticks() % 1000 // 500:  # every half second
            return self.cursor_surface
        else:
            return pygame.Surface((0, 0))  # transparent surface

    def update_cursor_pos(self, mouse_x):
        """Updates the cursor position based on the mouse's x-coordinate."""
        for i in range(len(self.content)):
            if self.font.size(self.content[:i+1])[0] + self.x >= mouse_x:
                self.cursor_pos = i
                return
        self.cursor_pos = len(self.content)

def scale(img, relative_width):
    new_width = int(settings.SCREEN_WIDTH * relative_width)
    new_height = new_width * img.get_height() / img.get_width()

    #relative_height = relative_width * img.get_height() / img.get_width()

    # Calculate the scaled dimensions based on the screen size
    #new_width = int(settings.SCREEN_WIDTH * relative_width)
    #new_height = int(settings.SCREEN_HEIGHT * relative_height)

    scaled_image = pygame.transform.scale(img, (new_width, new_height))

    return scaled_image

def brighten(img, brightness_factor):
    # Create a copy of the image
    image_copy = img.copy()

    # Lock the image surface to allow pixel-level access
    image_copy.lock()

    # Iterate over each pixel in the image
    for x in range(image_copy.get_width()):
        for y in range(image_copy.get_height()):
            # Get the color of the pixel
            r, g, b, a = image_copy.get_at((x, y))

            # Increase the brightness of RGB components
            r = min(int(r * brightness_factor), 255)
            g = min(int(g * brightness_factor), 255)
            b = min(int(b * brightness_factor), 255)

            # Update the pixel with the modified color
            image_copy.set_at((x, y), (r, g, b, a))

    # Unlock the image surface
    image_copy.unlock()

    # Return the modified image
    return image_copy


