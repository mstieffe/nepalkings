import pygame
from pygame.locals import *
from LoginScreen import LoginScreen
import settings
import sys
import requests


# Initialize pygame
pygame.init()

pygame.display.set_caption(settings.SCREEN_CAPTION)

def main():
    login_screen = LoginScreen()

    while True:
        events = pygame.event.get()

        login_screen.handle_events(events)
        login_screen.update(events)
        login_screen.render()

        pygame.display.update()
        login_screen.clock.tick(60)

if __name__ == '__main__':
    main()