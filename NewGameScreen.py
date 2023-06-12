import pygame
from pygame.locals import *
from Screen import Screen
import settings
from utils import Button
import requests

class NewGameScreen(Screen):
    def __init__(self, state):
        super().__init__(state)

        #self.state = state
        self.users = self.get_users()
        self.user_buttons = [Button(self.window, settings.get_x(0.1), settings.get_y(0.2 + 0.1 * i), user) for i, user in enumerate(self.users)]

    def update_users(self):
        self.users = self.get_users()
        self.user_buttons = [Button(self.window, settings.get_x(0.1), settings.get_y(0.2 + 0.1 * i), user) for i, user in enumerate(self.users)]

    def get_users(self):
        response = requests.get(f'{settings.SERVER_URL}/get_users', params={'username': self.state.username})
        if response.status_code != 200:
            print("Failed to get users")
            return []
        users = response.json()['users']
        return users

    def render(self):

        self.window.fill(settings.BACKGROUND_COLOR)
        self.draw_text('User List', settings.BLACK, settings.SCREEN_WIDTH * 0.1, settings.SCREEN_HEIGHT * 0.1)

        for button in self.user_buttons:
            button.draw()

        super().render()

        pygame.display.update()

    def update(self, events):
        for button in self.user_buttons:
            button.update_color()

        for event in events:
            if event.type == MOUSEBUTTONDOWN:
                for button in self.user_buttons:
                    if button.collide():
                        print(f"User {button.text} selected")
                        # TODO: implement what happens when a user is selected
