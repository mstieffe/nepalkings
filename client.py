import pygame
from pygame.locals import *
from LoginScreen import LoginScreen
from GameMenuScreen import GameMenuScreen
import settings
import sys
import requests

class Client:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_caption(settings.SCREEN_CAPTION)
        self.clock = pygame.time.Clock()
        self.running = True
        self.state = 'login'

        self.login_screen = LoginScreen()
        self.game_menu_screen = GameMenuScreen()

    def run_login_screen(self):
        while self.state == 'login':
            events = pygame.event.get()

            self.login_screen.handle_events(events)
            self.login_screen.update(events)
            self.login_screen.render()

            if self.login_screen.login_success:
                self.state = 'game_menu'

            pygame.display.update()
            self.clock.tick(60)

    def run_game_menu_screen(self):
        while self.state == 'game_menu':
            events = pygame.event.get()

            self.game_menu_screen.handle_events(events)
            self.game_menu_screen.update(events)
            self.game_menu_screen.render()

            #if self.login_screen.login_success:
            #    self.state = 'game'

            pygame.display.update()
            self.clock.tick(60)

    def run(self):
        while self.running:
            if self.state == 'login':
                self.run_login_screen()
            elif self.state == 'game_menu':
                self.run_game_menu_screen()

if __name__ == '__main__':
    client = Client()
    client.run()

