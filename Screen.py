import sys
import pygame
from pygame.locals import *
import settings
from DialogueBox import DialogueBox
from utils import Button, ControlButton

class Screen:
    def __init__(self, state):

        self.state = state

        # Set up the display
        self.window = pygame.display.set_mode((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))

        # Set up the font
        self.font = pygame.font.Font(settings.FONT_PATH, settings.FONT_SIZE)

        # Set clock
        self.clock = pygame.time.Clock()

        self.state.action = {"task": None,
                             "content": None,
                             "status": None}
        self.dialogue_box = None
        #self.info_box = None

        self.last_update_time = pygame.time.get_ticks()
        self.update_interval = 100
        # Initialize buttons
        #self.accept_button = None
        #self.reject_button = None

        self.logout_button = ControlButton(self.window, settings.get_x(0.85), settings.get_y(0.0), "Logout")
        self.home_button = ControlButton(self.window, settings.get_x(0.0), settings.get_y(0.0), "Home")

        self.control_buttons = [self.logout_button, self.home_button]
        self.game_buttons = []
        self.menu_buttons = []

    """
    def draw_msg(self):
        if self.state.msg:
            self.draw_text(self.state.msg, settings.BLACK, settings.SCREEN_WIDTH * 0.1, settings.SCREEN_HEIGHT * 0.6)
    """
    def make_button(self, text, x, y, width: int = None, height: int = None):
        button = Button(self.window, settings.get_x(x), settings.get_y(y), text, width=width, height=height)
        return button
    def make_buttons(self, button_names, x=0.0, y=0.0, width: int = None, height: int = None):
        buttons = [Button(self.window, settings.get_x(x), settings.get_y(y + 0.1 * i), text, width=width, height=height) for i, text in enumerate(button_names)]
        return buttons

    def draw_msg(self):
        #line_spacing = 20  # Adjust this value based on your desired line spacing
        starting_y_position = settings.get_y(0.6)  # Specify the initial y-coordinate position

        for line, _ in self.state.message_lines:
            line_y_position = starting_y_position + (self.state.message_lines.index((line, _)) * settings.MESSAGE_SPACING)
            self.draw_text(line, settings.BLACK, settings.get_x(0.1), line_y_position)

    def draw_text(self, text, color, x, y):
        text_obj = self.font.render(text, True, color)
        text_rect = text_obj.get_rect()
        text_rect.topleft = (x, y)
        self.window.blit(text_obj, text_rect)

    def make_dialogue_box(self, message, actions=None):
        self.dialogue_box = DialogueBox(self.window, message, self.font, actions=actions)

    """
    def make_info_box(self, message):
        self.info_box = InfoBox(self.window, message, self.font)
    """

    #def reset_user_response(self):
    #    self.state.user_response = None

    def reset_action(self):
        self.state.action = {"task": None,
                             "content": None,
                             "status": None}

    #def set_user_respone(self, response: str):
    #    self.state.user_response = response

    def set_action(self, task: str, content: str, status: str):
        self.state.action = {"task": task,
                             "content": content,
                             "status": status}

    def handle_events(self, events):
        for event in events:
            if event.type == QUIT:
                pygame.quit()
                sys.exit()
            elif event.type == MOUSEBUTTONDOWN:
                if self.logout_button.collide():
                    self.state.screen = "login"
                    self.reset_action()
                    self.state.user = None
                    self.state.set_msg("Logged out")
                elif self.home_button.collide():
                    self.state.screen = "game_menu"


        if self.dialogue_box:
            response = self.dialogue_box.update(events)
            if response:
                self.state.action["status"] = response
                self.dialogue_box = None

        """
        if self.info_box:
            response = self.info_box.update(events)
            if response:
                self.info_box = None
        """

    def render(self):
        self.draw_msg()
        if self.state.screen != "login":
            self.logout_button.draw()
            self.home_button.draw()
        if self.dialogue_box:
            self.dialogue_box.draw()
        #if self.info_box:
        #    self.info_box.draw()
        #raise NotImplementedError

    def update(self):
        for button in self.control_buttons:
            button.update()
        for button in self.game_buttons:
            button.update(self.state)
        for button in self.menu_buttons:
            button.update()
        #raise NotImplementedError