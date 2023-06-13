import sys
import pygame
from pygame.locals import *
import settings
from DialogueBox import DialogueBox
from utils import Button

class Screen:
    def __init__(self, state):

        self.state = state

        # Set up the display
        self.window = pygame.display.set_mode((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))

        # Set up the font
        self.font = pygame.font.Font(settings.FONT_PATH, settings.FONT_SIZE)

        # Set clock
        self.clock = pygame.time.Clock()

        self.dialogue_box = None
        # Initialize buttons
        #self.accept_button = None
        #self.reject_button = None

    def draw_msg(self):
        if self.state.msg:
            self.draw_text(self.state.msg, settings.BLACK, settings.SCREEN_WIDTH * 0.1, settings.SCREEN_HEIGHT * 0.6)

    def draw_text(self, text, color, x, y):
        text_obj = self.font.render(text, True, color)
        text_rect = text_obj.get_rect()
        text_rect.topleft = (x, y)
        self.window.blit(text_obj, text_rect)

    def make_dialogue_box(self, message):
        self.dialogue_box = DialogueBox(self.window, message, self.font)

    def reset_user_response(self):
        self.state.user_response = None

    def handle_events(self, events):
        for event in events:
            if event.type == QUIT:
                pygame.quit()
                sys.exit()
        if self.dialogue_box:
            response = self.dialogue_box.update(events)
            if response:
                self.state.user_response = response
                self.dialogue_box = None

    def render(self):
        self.draw_msg()
        if self.dialogue_box:
            self.dialogue_box.draw()
        #raise NotImplementedError

    def update(self):
        raise NotImplementedError