import sys
import pygame
from pygame.locals import *
from config import settings
from game.components.dialogue_box import DialogueBox
from game.components.scroll_text_list_shifter import ScrollTextListShifter
from utils.utils import SubScreenButton

class SubScreen:
    def __init__(self, window, game, x, y, title=None):

        # Set up the display
        self.window = window

        self.game = game

        self.x = x
        self.y = y

        self.title = title

        self.init_background()
        self.sub_box_background = None
        self.scroll_background = None

        # Set up the font
        self.font = pygame.font.Font(settings.FONT_PATH, settings.FONT_SIZE)
        self.title_font = pygame.font.Font(settings.FONT_PATH, settings.SUB_SCREEN_TITLE_FONT_SIZE)

        self.dialogue_box = None

        self.last_update_time = pygame.time.get_ticks()
        self.update_interval = 100  # Set default interval for updates

        self.buttons = []

        self.scroll_text_list = []
        self.scroll_text_list_shifter = None

    def make_button(self, text, x, y, width: int = None, height: int = None, button_img_active=None, button_img_inactive=None):
        """Helper to create a button."""
        return SubScreenButton(self.window, x, y, text, width=width, height=height, 
                             button_img_active=button_img_active, button_img_inactive=button_img_inactive)

    def draw_title(self):
        """Draw the title of the sub screen."""
        if self.title:
            # Render the title text
            title_text = self.title_font.render(self.title, True, settings.SUB_SCREEN_TITLE_COLOR)
            title_rect = title_text.get_rect(center=(settings.SUB_SCREEN_TITLE_X, settings.SUB_SCREEN_TITLE_Y))

            # Draw the background rectangle
            bg_rect = pygame.Rect(
                title_rect.left - settings.SUB_SCREEN_TITLE_PADDING,
                title_rect.top - settings.SUB_SCREEN_TITLE_PADDING,
                title_rect.width + 2 * settings.SUB_SCREEN_TITLE_PADDING,
                title_rect.height + 2 * settings.SUB_SCREEN_TITLE_PADDING
            )
            pygame.draw.rect(self.window, settings.SUB_SCREEN_TITLE_BG_COLOR, bg_rect)

            # Draw the border
            pygame.draw.rect(self.window, settings.SUB_SCREEN_TITLE_BORDER_COLOR, bg_rect, settings.SUB_SCREEN_TITLE_BORDER_WIDTH)

            # Draw the title text
            self.window.blit(title_text, title_rect)

            


    def init_background(self):
        """Initialize the background image."""
        self.background = pygame.image.load(settings.SUB_SCREEN_BACKGROUND_IMG_PATH)
        self.background = pygame.transform.smoothscale(self.background, (settings.SUB_SCREEN_BACKGROUND_IMG_WIDTH, settings.SUB_SCREEN_BACKGROUND_IMG_HEIGHT))

    def init_sub_box_background(self, x, y, width, height):
        """Initialize the background image."""
        self.sub_box_background = pygame.image.load(settings.SUB_BOX_BACKGROUND_IMG_PATH)
        self.sub_box_background = pygame.transform.smoothscale(self.sub_box_background, (width, height))
        self.sub_box_x = x
        self.sub_box_y = y

    def init_scroll_background(self, x, y, width, height):
        """Initialize the background image."""
        self.scroll_background = pygame.image.load(settings.SUB_BOX_SCROLL_BACKGROUND_IMG_PATH)
        self.scroll_background = pygame.transform.smoothscale(self.scroll_background, (width, height))
        self.scroll_x = x
        self.scroll_y = y
        self.scroll_text_list = []


    def draw_msg(self):
        """Render any messages to the screen."""
        pass
        #starting_y_position = settings.get_y(0.6)
        #for line, _ in self.state.message_lines:
        #    line_y_position = starting_y_position + (self.state.message_lines.index((line, _)) * settings.MESSAGE_SPACING)
        #    self.draw_text(line, settings.MSG_TEXT_COLOR, settings.get_x(0.1), line_y_position)

    def draw_text(self, text, color, x, y):
        """Draw text to the screen."""
        text_obj = self.font.render(text, True, color)
        text_rect = text_obj.get_rect()
        text_rect.topleft = (x, y)
        self.window.blit(text_obj, text_rect)


    def make_dialogue_box(self, message, actions=None, images=None, icon=None, title="", auto_close_delay=None):
        """Create a dialogue box with specified message and actions."""
        self.dialogue_box = DialogueBox(self.window, message, actions=actions, images=images, icon=icon, title=title, auto_close_delay=auto_close_delay)

    def make_scroll_text_list_shifter(self, text_list, x, y, scroll_height=None):
        """Create a scroll text list shifter."""
        self.scroll_text_list_shifter = ScrollTextListShifter(self.window, text_list, x, y, scroll_height=scroll_height)

    def handle_events(self, events):
        """Handle events like mouse clicks and quit."""
        pass
        # Handle events for dialogue box
        #if self.dialogue_box:
        #    response = self.dialogue_box.update(events)
        #    if response:
        #        self.dialogue_box = None  # Close the dialogue box once action is taken

    def draw(self):
        """Render buttons, messages, and the dialogue box."""

        # Draw the background image
        self.window.blit(self.background, (self.x, self.y))

        # Draw the sub box background image
        if self.sub_box_background:
            self.window.blit(self.sub_box_background, (self.sub_box_x, self.sub_box_y))
        
        # Draw the scroll background image
        if self.scroll_background:
            self.window.blit(self.scroll_background, (self.scroll_x, self.scroll_y))
        if self.scroll_text_list != [] and self.scroll_text_list_shifter:
            self.scroll_text_list_shifter.draw()
        #if self.scroll_text != []:
        #    #for text in self.scroll_text:
        #    #    self.draw_text_in_scroll(text, settings.SCROLL_TEXT_X, settings.SCROLL_TEXT_Y)


        for button in self.buttons:
            button.draw()
            
        self.draw_title()

    def draw_on_top(self):

        if self.dialogue_box:
            self.dialogue_box.draw()  # Ensure the dialogue box is rendered on top of other elements

        self.draw_msg()



    def update(self, game):
        """Update control buttons and game/menu buttons."""
        self.game = game
        for button in self.buttons:
            button.update()
        if self.scroll_text_list_shifter:
            self.scroll_text_list_shifter.update()

