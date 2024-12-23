import pygame
from pygame.locals import *
from game.screens.screen import Screen
from config import settings
from utils.utils import Button, InputField
from utils.auth_service import login, register

MAX_USERNAME_LENGTH = 15
MAX_PASSWORD_LENGTH = 15

class LoginScreen(Screen):
    def __init__(self, state):
        super().__init__(state)
        self.loading = False  # Loading state for login/register feedback

        self.field_username = InputField(self.window, settings.get_x(0.1), settings.get_y(0.2), "username", "", False, True, width=settings.INPUTFIELD_WIDTH_SMALL)
        self.field_pwd = InputField(self.window, settings.get_x(0.1), settings.get_y(0.3), "password", "", True, False, width=settings.INPUTFIELD_WIDTH_SMALL)
        self.button_login = Button(self.window, settings.get_x(0.1), settings.get_y(0.4), "login")
        self.button_register = Button(self.window, settings.get_x(0.1), settings.get_y(0.5), "register")

        self.menu_buttons += [self.button_login, self.button_register]

    def render(self):
        self.window.fill(settings.BACKGROUND_COLOR)
        self.draw_text('Login', settings.MENU_TEXT_COLOR_HEADER, settings.SCREEN_WIDTH * 0.1, settings.SCREEN_HEIGHT * 0.1)

        self.field_username.draw()
        self.field_pwd.draw()

        if not self.loading:
            self.button_login.draw()
            self.button_register.draw()
        else:
            self.draw_text('Loading...', settings.MENU_TEXT_COLOR_HEADER, settings.SCREEN_WIDTH * 0.1, settings.SCREEN_HEIGHT * 0.5)

        super().render()
        pygame.display.update()

    def handle_login(self):
        self.loading = True
        response_data = login(self.field_username.content, self.field_pwd.content)
        self.loading = False

        self.state.set_msg(response_data['message'])
        if response_data['success']:
            self.state.user_dict = response_data.get('user')
            self.state.screen = "game_menu"
        else:
            self.field_username.empty()
            self.field_pwd.empty()

    def handle_register(self):
        self.loading = True
        response_data = register(self.field_username.content, self.field_pwd.content)
        self.loading = False
        self.state.set_msg(response_data['message'])

        if response_data['success']:
            self.state.user_dict = response_data.get('user')
            self.state.screen = "game_menu"
        else:
            self.field_username.empty()
            self.field_pwd.empty()

    def handle_events(self, events):
        super().handle_events(events)

        for event in events:
            response_username = self.field_username.handle_event(event)
            response_pwd = self.field_pwd.handle_event(event)

            if response_username == 'switch' or response_pwd == 'switch':
                self.field_username.active = not self.field_username.active
                self.field_pwd.active = not self.field_pwd.active

            if event.type == KEYDOWN and event.key == K_RETURN:
                self.handle_login()

            elif event.type == MOUSEBUTTONDOWN:
                if self.button_login.collide():
                    self.handle_login()
                elif self.button_register.collide():
                    self.handle_register()

    def update(self, events):
        super().update()
        self.field_username.update_color()
        self.field_pwd.update_color()
