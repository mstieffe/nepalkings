import pygame
#from pygame.locals import *
from game.screens.login_screen import LoginScreen
from game.screens.game_menu_screen import GameMenuScreen
from game.screens.new_game_screen import NewGameScreen
from game.screens.load_game_screen import LoadGameScreen
from game.screens.game_screen import GameScreen
from game.core.state import State
from config import settings
#import sys
#import requests

class Client:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_caption(settings.SCREEN_CAPTION)
        self.clock = pygame.time.Clock()
        self.running = True

        self.state = State()

        self.screens = {
            'login': LoginScreen(self.state),
            'game_menu': GameMenuScreen(self.state),
            'new_game': NewGameScreen(self.state),
            'load_game': LoadGameScreen(self.state),
            'game': GameScreen(self.state)
        }

    def get_events(self):
        return pygame.event.get()

    def run_screen(self, screen):
        while self.state.screen == screen:
            events = self.get_events()

            self.screens[screen].handle_events(events)
            self.screens[screen].update(events)
            self.screens[screen].render()

            self.state.update()
            pygame.display.update()
            self.clock.tick(60)

    def run(self):
        while self.running:
            print(self.state.screen)
            if self.state.screen in self.screens:
                #if self.state.screen == 'new_game':
                #    self.screens['new_game'].update_users()
                #    self.screens['new_game'] = NewGameScreen(self.state)
                self.run_screen(self.state.screen)
            else:
                self.running = False
            #elif self.state.screen == 'new_game':
            #    self.screens['new_game'] = NewGameScreen(self.state)

if __name__ == '__main__':
    client = Client()
    client.run()