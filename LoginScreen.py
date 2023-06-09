import pygame
from pygame.locals import *
import requests
from Screen import Screen
import settings
from utils import Button, InputField


class LoginScreen(Screen):
    def __init__(self, state):
        super().__init__(state)

        self.field_username = InputField(self.window, settings.get_x(0.1), settings.get_y(0.2), "username", "", False, True)
        self.field_pwd = InputField(self.window, settings.get_x(0.1), settings.get_y(0.3), "password", "", True, False)
        self.button_login = Button(self.window, settings.get_x(0.1), settings.get_y(0.4), "login")
        self.button_register = Button(self.window, settings.get_x(0.1), settings.get_y(0.5), "register")

        self.menu_buttons += [self.button_login, self.button_register]
    def render(self):
        self.window.fill(settings.BACKGROUND_COLOR)
        self.draw_text('Login', settings.MENU_TEXT_COLOR_HEADER, settings.SCREEN_WIDTH * 0.1, settings.SCREEN_HEIGHT * 0.1)

        self.field_username.draw()
        self.field_pwd.draw()

        self.button_login.draw()
        self.button_register.draw()

        super().render()

        pygame.display.update()

    def handle_login(self):
        response = requests.post(f'{settings.SERVER_URL}/auth/login', data={'username': self.field_username.content, 'password': self.field_pwd.content})
        response_data = response.json()
        self.state.set_msg(response_data['message'])
        if response_data['success']:
            self.state.user_dict = response_data.get('user')
            self.state.screen = "game_menu"
        else:
            self.field_username.empty()
            self.field_pwd.empty()

    def handle_register(self):
        response = requests.post(f'{settings.SERVER_URL}/auth/register', data={'username': self.field_username.content, 'password': self.field_pwd.content})
        response_data = response.json()
        self.state.set_msg(response_data['message'])
        print(response_data['message'])
        if response_data['success']:
            self.state.user_dict = response_data.get('user')
            self.state.screen = "game_menu"
        else:
            self.field_username.empty()
            self.field_pwd.empty()

    def handle_keydown_event(self, event):
        if event.key == K_RETURN:
            self.handle_login()
        elif event.key == K_BACKSPACE:
            if len(self.field_username.content) > 0 and self.field_username.active:
                self.field_username.backspace()
            elif len(self.field_pwd.content) > 0 and self.field_pwd.active:
                self.field_pwd.backspace()
        elif event.key == K_TAB:
            self.field_username.active = not self.field_username.active
            self.field_pwd.active = not self.field_pwd.active
        elif event.key == K_LEFT:
            if self.field_username.active:
                self.field_username.cursor_pos = max(0, self.field_username.cursor_pos - 1)
            elif self.field_pwd.active:
                self.field_pwd.cursor_pos = max(0, self.field_pwd.cursor_pos - 1)
        elif event.key == K_RIGHT:
            if self.field_username.active:
                self.field_username.cursor_pos = min(len(self.field_username.content), self.field_username.cursor_pos + 1)
            elif self.field_pwd.active:
                self.field_pwd.cursor_pos = min(len(self.field_pwd.content), self.field_pwd.cursor_pos + 1)
        else:
            if self.field_username.active and len(self.field_username.content) < 15:
                self.field_username.insert(event.unicode)
            elif self.field_pwd.active and len(self.field_pwd.content) < 15:
                self.field_pwd.insert(event.unicode)

    def handle_mousebuttondown_event(self, event):
        if self.field_pwd.collide():
            self.field_username.active = False
            self.field_pwd.active = True
            self.field_pwd.update_cursor_pos(pygame.mouse.get_pos()[0])
        elif self.field_username.collide():
            self.field_username.active = True
            self.field_pwd.active = False
            self.field_username.update_cursor_pos(pygame.mouse.get_pos()[0])
        elif self.button_login.collide():
            self.handle_login()
        elif self.button_register.collide():
            self.handle_register()

    def update(self, events):
        super().update()

        self.field_username.update_color()
        self.field_pwd.update_color()

        #self.button_login.update()
        #self.button_register.update()

        for event in events:
            if event.type == KEYDOWN:
                self.handle_keydown_event(event)
            elif event.type == MOUSEBUTTONDOWN:
                self.handle_mousebuttondown_event(event)

    def handle_events(self, events):
        super().handle_events(events)
