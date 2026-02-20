from config import settings
import pygame
from pygame.locals import *

def get_opp_color(color):
    if color == "offensive":
        return "defensive"
    elif color == "defensive":
        return "offensive"
    else:
        return None

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
                 track_turn = True):
        self.window = window
        self.name = name
        self.x = x
        self.y = y
        self.glow_shift = glow_shift if glow_shift is not None else settings.GAME_BUTTON_GLOW_SHIFT
        self.font = pygame.font.Font(settings.FONT_PATH, settings.GAME_BUTTON_FONT_SIZE)
        self.state = state
        self.subscreen_trigger = subscreen
        self.screen_trigger = screen
        self.track_turn = track_turn

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
            if self.state.game.turn or not self.track_turn:
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
                        self.window.blit(self.image_symbol_passive_big, self.rect_symbol_big.topleft)
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
                # Allow all subscreen changes during Infinite Hammer (cast button is blocked instead)
                if self.subscreen_trigger:
                    self.state.subscreen = self.subscreen_trigger
                if self.screen_trigger:
                    self.state.screen = self.screen_trigger
            else:
                self.clicked = False


class Button:
    def __init__(self, window, x=0, y=0, text="", width=None, height=None):
        self.window = window
        self.x = x
        self.y = y
        self.text = text

        # Load font settings
        self.font = pygame.font.Font(settings.FONT_PATH, settings.FONT_SIZE_BUTTON)
        self.font_small = pygame.font.Font(settings.FONT_PATH, int(settings.FONT_SIZE_BUTTON * 0.9))

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
        """Check if the mouse is over the button."""
        return self.rect.collidepoint(pygame.mouse.get_pos())

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
            self.clicked = self.hovered and pygame.mouse.get_pressed()[0]


class SubScreenButton:
    def __init__(self, window, x=0, y=0, text="", width=None, height=None, button_img_active=None, button_img_inactive=None):
        self.window = window
        self.x = x
        self.y = y
        self.text = text
        self.button_img_active_path = button_img_active
        self.button_img_inactive_path = button_img_inactive

        # Load font settings
        self.font = pygame.font.Font(settings.FONT_PATH, settings.FONT_SIZE_SUBSCREEN_BUTTON)
        self.font_small = pygame.font.Font(settings.FONT_PATH, int(settings.FONT_SIZE_SUBSCREEN_BUTTON * 0.9))

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
        """Check if the mouse is over the button."""
        return self.rect.collidepoint(pygame.mouse.get_pos())

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
            self.clicked = self.hovered and pygame.mouse.get_pressed()[0]

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

    def update(self):
        mx, my = pygame.mouse.get_pos()
        if self.rect.collidepoint((mx, my)):
            self.color_rect = settings.BUTTON_COLOR_ACTIVE  # Hover color
            self.color_text = settings.TEXT_COLOR_ACTIVE
        else:
            self.color_rect = settings.BUTTON_COLOR_PASSIVE  # Default color
            self.color_text = settings.TEXT_COLOR_PASSIVE


class InputField:
    def __init__(self, window, x: int = 0, y: int = 0, name: str = "", content: str = "", pwd: bool = False, active: bool = False, max_length: int = 15, width: int = None, height: int = None):
        self.window = window
        self.x = x
        self.y = y
        self.name = name
        self.content = content
        self.pwd = pwd
        self.active = active  # Track if the field is currently active
        self.max_length = max_length

        self.color_rect = settings.INPUTFIELD_COLOR_PASSIVE
        self.color_text = settings.TEXT_COLOR_PASSIVE
        self.border_color = settings.INPUTFIELD_BORDER_COLOR_PASSIVE  # Border color for the input field
        self.font = pygame.font.Font(settings.FONT_PATH, settings.INPUTFIELD_FONT_SIZE)
        self.font_title = pygame.font.Font(settings.FONT_PATH, settings.INPUTFIELD_FONT_SIZE_TITLE)

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
                elif len(self.content) < self.max_length:
                    self.insert(event.unicode)
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
        """Check if the mouse is over the input field."""
        mx, my = pygame.mouse.get_pos()
        return self.rect.collidepoint((mx, my))

    def activate(self):
        """Activate the input field, setting it as the active field."""
        self.active = True

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


