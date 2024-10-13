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
        self.loading = False  # New loading state for login/register feedback

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

        if not self.loading:
            self.button_login.draw()
            self.button_register.draw()
        else:
            # Display loading feedback
            self.draw_text('Loading...', settings.MENU_TEXT_COLOR_HEADER, settings.SCREEN_WIDTH * 0.1, settings.SCREEN_HEIGHT * 0.5)

        super().render()
        pygame.display.update()

    def handle_login(self):
        """Handle the login logic."""
        self.loading = True  # Set loading state to True during the process
        response_data = login(self.field_username.content, self.field_pwd.content)
        self.loading = False  # Reset loading state after processing

        # Display the simplified user-friendly message
        self.state.set_msg(response_data['message'])

        if response_data['success']:
            self.state.user_dict = response_data.get('user')
            self.state.screen = "game_menu"
        else:
            # Clear fields if login failed
            self.field_username.empty()
            self.field_pwd.empty()

    def handle_register(self):
        """Handle the registration logic."""
        self.loading = True  # Set loading state to True during the process
        response_data = register(self.field_username.content, self.field_pwd.content)
        self.loading = False  # Reset loading state after processing
        self.state.set_msg(response_data['message'])

        if response_data['success']:
            self.state.user_dict = response_data.get('user')
            self.state.screen = "game_menu"
        else:
            self.field_username.empty()
            self.field_pwd.empty()

    def handle_keydown_event(self, event):
        """Handle key down events for text input and navigation."""
        if event.key == K_RETURN:
            self.handle_login()
        elif event.key == K_BACKSPACE:
            if self.field_username.active:
                self.field_username.backspace()
            elif self.field_pwd.active:
                self.field_pwd.backspace()
        elif event.key == K_TAB:
            self.field_username.active = not self.field_username.active
            self.field_pwd.active = not self.field_pwd.active
        elif event.key == K_LEFT:
            if pygame.key.get_mods() & KMOD_CTRL:  # Ctrl+Left to jump to start
                if self.field_username.active:
                    self.field_username.cursor_pos = 0
                else:
                    self.field_pwd.cursor_pos = 0

                #self.field_username.cursor_pos = 0 if self.field_username.active else self.field_pwd.cursor_pos = 0
            else:
                if self.field_username.active:
                    self.field_username.cursor_pos = max(0, self.field_username.cursor_pos - 1)
                elif self.field_pwd.active:
                    self.field_pwd.cursor_pos = max(0, self.field_pwd.cursor_pos - 1)
        elif event.key == K_RIGHT:
            if pygame.key.get_mods() & KMOD_CTRL:  # Ctrl+Right to jump to end
                if self.field_username.active:
                    self.field_username.cursor_pos = len(self.field_username.content)
                else:
                    self.field_pwd.cursor_pos = len(self.field_pwd.content)

                #self.field_username.cursor_pos = len(self.field_username.content) if self.field_username.active else self.field_pwd.cursor_pos = len(self.field_pwd.content)
            else:
                if self.field_username.active:
                    self.field_username.cursor_pos = min(len(self.field_username.content), self.field_username.cursor_pos + 1)
                elif self.field_pwd.active:
                    self.field_pwd.cursor_pos = min(len(self.field_pwd.content), self.field_pwd.cursor_pos + 1)
        else:
            if self.field_username.active and len(self.field_username.content) < MAX_USERNAME_LENGTH:
                self.field_username.insert(event.unicode)
            elif self.field_pwd.active and len(self.field_pwd.content) < MAX_PASSWORD_LENGTH:
                self.field_pwd.insert(event.unicode)

    def handle_mousebuttondown_event(self, event):
        """Handle mouse button down events for clicking input fields or buttons."""
        if self.field_pwd.collide():
            self.field_username.deactivate()
            self.field_pwd.activate()
            self.field_pwd.update_cursor_pos(pygame.mouse.get_pos()[0])
        elif self.field_username.collide():
            self.field_username.activate()
            self.field_pwd.deactivate()
            self.field_username.update_cursor_pos(pygame.mouse.get_pos()[0])
        elif self.button_login.collide():
            self.handle_login()
        elif self.button_register.collide():
            self.handle_register()

    def handle_events(self, events):
        """Process user input events."""
        super().handle_events(events)

        for event in events:
            if event.type == KEYDOWN:
                self.handle_keydown_event(event)
            elif event.type == MOUSEBUTTONDOWN:
                self.handle_mousebuttondown_event(event)

    def update(self, events):
        """Update the screen state (e.g., field colors, loading states)."""
        super().update()
        self.field_username.update_color()
        self.field_pwd.update_color()
