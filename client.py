import pygame
#from pygame.locals import *
from LoginScreen import LoginScreen
from GameMenuScreen import GameMenuScreen
from NewGameScreen import NewGameScreen
from LoadGameScreen import LoadGameScreen
from GameState import GameState
import settings
#import sys
#import requests

class Client:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_caption(settings.SCREEN_CAPTION)
        self.clock = pygame.time.Clock()
        self.running = True

        self.state = GameState()

        self.screens = {
            'login': LoginScreen(self.state),
            'game_menu': GameMenuScreen(self.state),
            'new_game': NewGameScreen(self.state),
            'load_game': LoadGameScreen(self.state)
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
            #elif self.state.screen == 'new_game':
            #    self.screens['new_game'] = NewGameScreen(self.state)

if __name__ == '__main__':
    client = Client()
    client.run()