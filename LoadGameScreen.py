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
        self.load_game_buttons = []
        self.button_to_game = {}
        for game in self.games:
            game_name = f"{game['opponent']} - {game['date']}"
            self.button_to_game[game_name] = game
            self.load_game_buttons.append(self.make_button(game_name, 0.1, 0.2, width=settings.get_x(0.5)))

        #self.games = self.get_games()
        #game_names = [f"{game['opponent']} - {game['date']}" for game in self.games]
        #self.load_game_buttons = self.make_buttons(game_names, 0.1, 0.2, width=settings.get_x(0.5))

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
                        self.make_dialogue_box('Do you want to load the game ' + button.text + '?', actions=["yes", "no"])

        if self.state.action["task"] == "load_game" and self.state.action["status"] != "open":
            if self.state.action["status"] == 'yes':
                self.state.game.id = self.button_to_game[self.state.action["content"]]['id']
                self.state.game.date = self.button_to_game[self.state.action["content"]]['date']
                self.state.game.opponent = self.button_to_game[self.state.action["content"]]['opponent']
                self.state.set_msg(f"Loaded game with {self.state.game.opponent}")
                self.state.screen = "game"
                #opponent = self.state.action["content"]
                #self.create_challenge(opponent)
                #print("load game")
                #self.state.

            self.reset_action()
