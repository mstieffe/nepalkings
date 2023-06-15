import pygame
from pygame.locals import *
from Screen import Screen
import settings
from utils import Button
import requests

class LoadGameScreen(Screen):

    def __init__(self, state):
        super().__init__(state)

        self.games = []
        self.load_game_buttons = []

    def update_load_game_buttons(self):

        self.games = self.get_games()
        game_names = [f"{game['opponent']} - {game['date']}" for game in self.games]
        self.load_game_buttons = self.make_buttons(game_names, 0.1, 0.2, width=settings.get_x(0.5))

    def get_games(self):
        response = requests.get(f'{settings.SERVER_URL}/get_games', params={'username': self.state.username})
        if response.status_code != 200:
            print("Failed to get games")
            print(response.json()['message'])
            return []
        games = response.json()['games']
        return games

    def render(self):

        self.window.fill(settings.BACKGROUND_COLOR)
        self.draw_text('Load Game', settings.BLACK, settings.get_x(0.1), settings.get_x(0.1))

        for button in self.load_game_buttons:
            button.draw()

        super().render()

        pygame.display.update()

    def update(self, events):
        super().update()

        current_time = pygame.time.get_ticks()
        if current_time - self.last_update_time >= self.update_interval:
            self.last_update_time = current_time
            self.update_load_game_buttons()

        for button in self.load_game_buttons:
            button.update_color()

        for event in events:
            if event.type == MOUSEBUTTONDOWN:
                for button in self.load_game_buttons:
                    if button.collide():
                        self.set_action("load_game", button.text, "open")
                        self.make_dialogue_box('Do you want to load the game ' + button.text + '?')

        if self.state.action["task"] == "load_game" and self.state.action["status"] != "open":
            if self.state.action["status"] == 'accept':
                #opponent = self.state.action["content"]
                #self.create_challenge(opponent)
                print("load game")

            self.reset_action()
