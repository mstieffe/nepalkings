import pygame
from pygame.locals import *
from Screen import Screen
import settings
from utils import Button
import requests
from Game import Game

class LoadGameScreen(Screen):
    def __init__(self, state):
        super().__init__(state)

        self.games = []
        self.load_game_buttons = []

    def update_load_game_buttons(self):
        self.games = self.get_games()
        self.load_game_buttons = []

        game_names = [f"{game.opponent_name} - {game.date}" for game in self.games]
        self.load_game_buttons = self.make_buttons(game_names, 0.1, 0.2, width=settings.get_x(0.5))
        #for i, game in enumerate(self.games):
        #    game_name = f"{game.opponent_name} - {game.date}"
        #    self.load_game_buttons.append(self.make_button(game_name, 0.1, 0.2, width=settings.get_x(0.5)))

    def get_games(self):
        response = requests.get(f'{settings.SERVER_URL}/games/get_games', params={'username': self.state.user_dict['username']})
        if response.status_code != 200:
            print("Failed to get games")
            print(response.json()['message'])
            return []
        game_dicts = response.json().get('games', [])
        games = [Game(game_dict, self.state.user_dict) for game_dict in game_dicts]
        return games

    def render(self):
        self.window.fill(settings.BACKGROUND_COLOR)
        self.draw_text('Load Game', settings.MENU_TEXT_COLOR_HEADER, settings.get_x(0.1), settings.get_y(0.1))

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
            button.update()

        for event in events:
            if event.type == MOUSEBUTTONDOWN:
                for button in self.load_game_buttons:
                    if button.collide():
                        self.set_action("load_game", button.text, "open")
                        self.make_dialogue_box('Do you want to load the game ' + button.text + '?', actions=["yes", "no"])

        if self.state.action["task"] == "load_game" and self.state.action["status"] != "open":
            if self.state.action["status"] == 'yes':
                game_name = self.state.action["content"]
                game = next((game for game in self.games if f"{game.opponent_name} - {game.date}" == game_name), None)
                if game:
                    self.state.game = game
                    self.state.set_msg(f"Loaded game with {game.opponent_name}")
                    self.state.screen = "game"
                else:
                    print("Game not found")
            self.reset_action()
