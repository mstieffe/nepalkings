import sys
import pygame
from pygame.locals import *
from config import settings
from game.components.dialogue_box import DialogueBox
from utils.utils import Button, ControlButton, GameButton

class Screen:
    def __init__(self, state):
        self.state = state

        # Set up the display
        self.window = pygame.display.set_mode((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))

        # Set up the font
        self.font = pygame.font.Font(settings.FONT_PATH, settings.FONT_SIZE)

        # Set clock
        self.clock = pygame.time.Clock()

        self.state.action = {
            "task": None,
            "content": None,
            "status": None
        }
        self.dialogue_box = None

        self.last_update_time = pygame.time.get_ticks()
        self.update_interval = 100  # Set default interval for updates

        # Initialize control buttons
        self.logout_button = ControlButton(self.window, settings.get_x(0.85), settings.get_y(0.0), "Logout")
        self.home_button = ControlButton(self.window, settings.get_x(0.0), settings.get_y(0.0), "Home")

        self.control_buttons = [self.logout_button, self.home_button]
        self.game_buttons = []
        self.menu_buttons = []

    def make_button(self, text, x, y, width: int = None, height: int = None):
        """Helper to create a button."""
        return Button(self.window, settings.get_x(x), settings.get_y(y), text, width=width, height=height)

    def make_buttons(self, button_names, x=0.0, y=0.0, width: int = None, height: int = None):
        """Helper to create multiple buttons."""
        return [Button(self.window, settings.get_x(x), settings.get_y(y + 0.1 * i), text, width=width, height=height) for i, text in enumerate(button_names)]

    def draw_msg(self):
        """Render any messages to the screen."""
        starting_y_position = settings.get_y(0.0)
        for line, _ in self.state.message_lines:
            line_y_position = starting_y_position + (self.state.message_lines.index((line, _)) * settings.MESSAGE_SPACING)
            self.draw_text(line, settings.MSG_TEXT_COLOR, settings.get_x(0.25), line_y_position)

    def draw_text(self, text, color, x, y):
        """Draw text to the screen."""
        text_obj = self.font.render(text, True, color)
        text_rect = text_obj.get_rect()
        text_rect.topleft = (x, y)
        self.window.blit(text_obj, text_rect)

    def make_dialogue_box(self, message, actions=None):
        """Create a dialogue box with specified message and actions."""
        self.dialogue_box = DialogueBox(self.window, message, actions=actions)

    def reset_action(self):
        """Reset the current action state."""
        self.state.action = {
            "task": None,
            "content": None,
            "status": None
        }

    def set_action(self, task: str, content: str, status: str):
        """Set the current action with the provided task, content, and status."""
        self.state.action = {
            "task": task,
            "content": content,
            "status": status
        }

    def handle_events(self, events):
        """Handle events like mouse clicks and quit."""
        for event in events:
            if event.type == QUIT:
                pygame.quit()
                sys.exit()
            elif event.type == MOUSEBUTTONDOWN:
                # Handle logout and home buttons
                if self.logout_button.collide():
                    self.state.screen = "login"
                    self.reset_action()
                    self.state.user = None
                    self.state.set_msg("Logged out")
                elif self.home_button.collide():
                    self.state.screen = "game_menu"

        # Handle events for dialogue box
        if self.dialogue_box:
            response = self.dialogue_box.update(events)
            if response:
                self.state.action["status"] = response  # "yes" or "no" from dialogue box
                self.dialogue_box = None  # Close the dialogue box once action is taken

    def render(self):
        """Render buttons, messages, and the dialogue box."""
        self.draw_msg()
        
        if self.state.screen != "login" and self.state.screen != "game":
            for button in self.control_buttons:
                button.draw()
            #self.logout_button.draw()
            #self.home_button.draw()

        for button in self.game_buttons:
            button.draw()
        for button in self.menu_buttons:
            button.draw()

        if self.dialogue_box:
            self.dialogue_box.draw()  # Ensure the dialogue box is rendered on top of other elements

    def update(self):
        """Update control buttons and game/menu buttons."""
        for button in self.control_buttons:
            button.update()
        for button in self.game_buttons:
            button.update(self.state)
        for button in self.menu_buttons:
            button.update()
