import pygame
from pygame.locals import *
import requests
from Screen import Screen
import settings

class LoginScreen(Screen):
    def __init__(self):
        super().__init__()
        self.username = ''
        self.password = ''
        self.login_failed = False
        self.active_field = 'username'
        self.login_button_rect = pygame.Rect(50, 320, settings.SMALL_FIELD_WIDTH, settings.SMALL_FIELD_HEIGHT)
        self.register_button_rect = pygame.Rect(210, 320, settings.SMALL_FIELD_WIDTH, settings.SMALL_FIELD_HEIGHT)

    def render(self):

        self.window.fill(settings.WHITE)
        self.draw_text('Login', settings.BLACK, 50, 50)

        self.draw_text('Username:', settings.BLACK, 50, 120)
        pygame.draw.rect(self.window, settings.BLACK, (50, 170, settings.SMALL_FIELD_WIDTH, settings.SMALL_FIELD_HEIGHT))
        self.draw_text(self.username, settings.WHITE, 60, 175)

        self.draw_text('Password:', settings.BLACK, 50, 220)
        pygame.draw.rect(self.window, settings.BLACK, (50, 270, settings.SMALL_FIELD_WIDTH, settings.SMALL_FIELD_HEIGHT))
        self.draw_text('*' * len(self.password), settings.WHITE, 60, 275)

        if self.login_failed:
            self.draw_text('Login failed. Please try again.', settings.BLACK, 50, 320)

        pygame.draw.rect(self.window, settings.BLACK, self.login_button_rect)
        self.draw_text('Login', settings.WHITE, 60, 325)

        pygame.draw.rect(self.window, settings.BLACK, self.register_button_rect)
        self.draw_text('Register', settings.WHITE, 220, 325)


        pygame.display.update()

    def update(self, events):
        for event in events:
            if event.type == KEYDOWN:
                print("jasd")
                if event.key == K_RETURN:
                    response = requests.post(f'{settings.SERVER_URL}/login', data={'username': self.username, 'password': self.password})
                    if response.json()['success']:
                        print("login!!!")
                    else:
                        self.login_failed = True
                        self.username = ''
                        self.password = ''
                elif event.key == K_BACKSPACE:
                    if len(self.username) > 0 and self.active_field == 'username':
                        self.username = self.username[:-1]
                    elif len(self.password) > 0 and self.active_field == 'password':
                        self.password = self.password[:-1]
                elif event.key == K_TAB:
                    self.active_field = 'password' if self.active_field == 'username' else 'username'
                else:
                    field = self.username if self.active_field == 'username' else self.password
                    if len(field) < 15:
                        field += event.unicode
                    if self.active_field == 'username':
                        self.username = field
                    else:
                        self.password = field
            elif event.type == MOUSEBUTTONDOWN:
                mx, my = pygame.mouse.get_pos()
                if 50 <= mx <= (50 + settings.SMALL_FIELD_WIDTH) and 270 <= my <= (270 + settings.SMALL_FIELD_HEIGHT):
                    self.active_field = 'password'
                elif 50 <= mx <= (50 + settings.SMALL_FIELD_WIDTH) and 170 <= my <= (170 + settings.SMALL_FIELD_HEIGHT):
                    self.active_field = 'username'
                    self.login_failed = False
                elif self.login_button_rect.collidepoint((mx, my)):
                    response = requests.post(f'{settings.SERVER_URL}/login', data={'username': self.username, 'password': self.password})
                    if response.json()['success']:
                        print("login!!!")
                    else:
                        self.login_failed = True
                        self.username = ''
                        self.password = ''

    def handle_events(self, events):
        super().handle_events(events)
