import sys
import pygame
from pygame.locals import *
from config import settings
from game.components.dialogue_box import DialogueBox
from utils.utils import SubScreenButton

class SubScreen:
    def __init__(self, window, game, x, y):

        # Set up the display
        self.window = window

        self.game = game

        self.x = x
        self.y = y


        self.init_background()
        self.sub_box_background = None
        self.scroll_background = None

        # Set up the font
        self.font = pygame.font.Font(settings.FONT_PATH, settings.FONT_SIZE)
        self.scroll_font = pygame.font.Font(settings.FONT_PATH, settings.FONT_SIZE_DETAIL)

        self.dialogue_box = None

        self.last_update_time = pygame.time.get_ticks()
        self.update_interval = 100  # Set default interval for updates

        self.buttons = []

    def make_button(self, text, x, y, width: int = None, height: int = None):
        """Helper to create a button."""
        return SubScreenButton(self.window, x, y, text, width=width, height=height)

    def init_background(self):
        """Initialize the background image."""
        self.background = pygame.image.load(settings.SUB_SCREEN_BACKGROUND_IMG_PATH)
        self.background = pygame.transform.scale(self.background, (settings.SUB_SCREEN_BACKGROUND_IMG_WIDTH, settings.SUB_SCREEN_BACKGROUND_IMG_HEIGHT))

    def init_sub_box_background(self, x, y, width, height):
        """Initialize the background image."""
        self.sub_box_background = pygame.image.load(settings.SUB_BOX_BACKGROUND_IMG_PATH)
        self.sub_box_background = pygame.transform.scale(self.sub_box_background, (width, height))
        self.sub_box_x = x
        self.sub_box_y = y

    def init_scroll_background(self, x, y, width, height):
        """Initialize the background image."""
        self.scroll_background = pygame.image.load(settings.SUB_BOX_SCROLL_BACKGROUND_IMG_PATH)
        self.scroll_background = pygame.transform.scale(self.scroll_background, (width, height))
        self.scroll_x = x
        self.scroll_y = y
        self.scroll_text = []

    def draw_text_in_scroll(self, text_dict, x, y, max_width=settings.SCROLL_TEXT_MAX_WIDTH):
        """Draw text to the screen with line breaks after reaching a certain width."""
        # TITLE
        title_obj = self.scroll_font.render(text_dict['title'], True, settings.SCROLL_TEXT_COLOR)
        title_rect = title_obj.get_rect()
        title_rect.midtop = (x + max_width // 2, y)  # Center the title
        self.window.blit(title_obj, title_rect)
        y += title_rect.height

        # Leave one blank line
        blank_line_height = self.scroll_font.size(" ")[1]
        y += blank_line_height

        # TEXT
        words = text_dict['text'].split(' ')
        lines = []
        current_line = ""
        
        for word in words:
            # Check the width of the current line with the new word added
            test_line = current_line + word + " "
            test_width, _ = self.scroll_font.size(test_line)
            
            if test_width <= max_width:
                current_line = test_line
            else:
                # If the line exceeds the max width, add the current line to lines and start a new line
                lines.append(current_line)
                current_line = word + " "
        
        # Add the last line to lines
        if current_line:
            lines.append(current_line)
        
        # Draw each line to the screen
        for line in lines:
            text_obj = self.scroll_font.render(line, True, settings.SCROLL_TEXT_COLOR)
            text_rect = text_obj.get_rect()
            text_rect.topleft = (x, y)
            self.window.blit(text_obj, text_rect)
            y += text_rect.height  # Move y position for the next line

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

    def make_dialogue_box(self, message, actions=None):
        """Create a dialogue box with specified message and actions."""
        self.dialogue_box = DialogueBox(self.window, message, self.font, actions=actions)

    def handle_events(self, events):
        """Handle events like mouse clicks and quit."""

        # Handle events for dialogue box
        if self.dialogue_box:
            response = self.dialogue_box.update(events)
            if response:
                self.dialogue_box = None  # Close the dialogue box once action is taken

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
        if self.scroll_text != []:
            for text in self.scroll_text:
                self.draw_text_in_scroll(text, settings.SCROLL_TEXT_X, settings.SCROLL_TEXT_Y)


        for button in self.buttons:
            button.draw()

        if self.dialogue_box:
            self.dialogue_box.draw()  # Ensure the dialogue box is rendered on top of other elements

        self.draw_msg()


    def update(self, game):
        """Update control buttons and game/menu buttons."""
        self.game = game
        for button in self.buttons:
            button.update()

