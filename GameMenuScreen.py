import pygame
from pygame.locals import *
import requests
from Screen import Screen
import settings
from utils import Button

class GameMenuScreen(Screen):
    def __init__(self, state):
        super().__init__(state)

        #self.state = state
        self.button_new = Button(self.window, settings.get_x(0.1), settings.get_y(0.2), "New Game")
        self.button_load = Button(self.window, settings.get_x(0.1), settings.get_y(0.3), "Load Game")

    def render(self):



        self.window.fill(settings.BACKGROUND_COLOR)
        self.draw_text('Game Menu', settings.BLACK, settings.SCREEN_WIDTH * 0.1, settings.SCREEN_HEIGHT * 0.1)

        self.button_new.draw()
        self.button_load.draw()

        super().render()

        pygame.display.update()

    def update(self, events):
        self.button_new.update_color()
        self.button_load.update_color()

        for event in events:
            if event.type == MOUSEBUTTONDOWN:
                if self.button_new.collide():
                    self.state.screen = 'new_game'
                    # Assuming we have a class Game to start a new game
                    #self.game = Game()
                    #self.game.start_new_game()
                    print("new game")
                elif self.button_load.collide():
                    print("load game")
                    # Assuming we have a function load_game to load an existing game
                    #load_game()

    def handle_events(self, events):
        super().handle_events(events)
