import pygame
from pygame.locals import *
from Screen import Screen
import settings
from utils import Button
import requests

class GameScreen(Screen):
    def __init__(self, state):
        super().__init__(state)

    def render(self):

        self.window.fill(settings.BACKGROUND_COLOR)

        self.draw_text(self.state.game.opponent, settings.BLACK, settings.get_x(0.1), settings.get_x(0.1))

        super().render()

        pygame.display.update()

    def update(self, events):
        super().update()

        current_time = pygame.time.get_ticks()
        #if current_time - self.last_update_time >= self.update_interval:


        #for button in self.challenge_buttons + self.open_challenge_buttons:
        #    button.update_color()

        #for event in events:
        #    if event.type == MOUSEBUTTONDOWN:


        #    self.reset_action()

