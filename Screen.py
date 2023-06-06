import sys
import pygame
from pygame.locals import *
import settings

class Screen:
    def __init__(self):
        # Set up the display
        self.window = pygame.display.set_mode((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))

        # Set up the font
        self.font = pygame.font.Font(settings.FONT_PATH, settings.FONT_SIZE)

        # Set clock
        self.clock = pygame.time.Clock()
    def draw_text(self, text, color, x, y):
        text_obj = self.font.render(text, True, color)
        text_rect = text_obj.get_rect()
        text_rect.topleft = (x, y)
        self.window.blit(text_obj, text_rect)

    def handle_events(self, events):
        for event in events:
            if event.type == QUIT:
                pygame.quit()
                sys.exit()

    def render(self):
        raise NotImplementedError

    def update(self):
        raise NotImplementedError