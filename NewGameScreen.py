import pygame
from pygame.locals import *
from Screen import Screen
import settings
from utils import Button
from models import User

class NewGameScreen(Screen):
    def __init__(self):
        super().__init__()

        self.users = self.get_users()
        self.user_buttons = [Button(self.window, settings.get_x(0.1), settings.get_y(0.2 + 0.1 * i), user) for i, user in enumerate(self.users)]

    def get_users(self):
        users = User.query.all()
        return users

    def render(self):
        self.window.fill(settings.BACKGROUND_COLOR)
        self.draw_text('User List', settings.BLACK, settings.SCREEN_WIDTH * 0.1, settings.SCREEN_HEIGHT * 0.1)

        for button in self.user_buttons:
            button.draw()

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
