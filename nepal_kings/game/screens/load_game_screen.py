import pygame
from pygame.locals import *
from game.screens.screen import Screen
from config import settings
from utils.utils import Button
import requests
from game.core.game import Game

class LoadGameScreen(Screen):
    def __init__(self, state):
        super().__init__(state)  # Inherit Screen's constructor

        self.games = []
        self.load_game_buttons = []
        self.last_update_time = 0  # Time tracking for throttled updates
        self.update_interval = 5000  # Update game list every 5 seconds

    def update_load_game_buttons(self):
        """Fetch games and update buttons based on the current game list."""
        try:
            self.games = self.get_games()  # Fetch games from server
        except Exception as e:
            print(f"Error fetching games: {str(e)}")
            self.games = []
            return

        # Create buttons for the fetched games
        game_names = [f"{game.opponent_name} - {game.date}" for game in self.games]
        self.load_game_buttons = self.make_buttons(game_names, 0.1, 0.2, width=settings.get_x(0.5))

    def get_games(self):
        """Fetch the list of available games for the current user."""
        response = requests.get(f'{settings.SERVER_URL}/games/get_games', params={'username': self.state.user_dict['username']})
        if response.status_code != 200:
            print("Failed to get games")
            print(response.json()['message'])
            return []
        game_dicts = response.json().get('games', [])
        return [Game(game_dict, self.state.user_dict) for game_dict in game_dicts]

    def render(self):
        """Render the Load Game Screen and its buttons."""
        self.window.fill(settings.BACKGROUND_COLOR)
        self.draw_text('Load Game', settings.MENU_TEXT_COLOR_HEADER, settings.get_x(0.1), settings.get_y(0.1))

        # Draw the game buttons
        for button in self.load_game_buttons:
            button.draw()

        super().render()  # Render control buttons, dialogue box, etc.

        pygame.display.update()

    def update(self, events):
        """Update the screen state and handle events."""
        super().update()  # Call the base class update for control buttons and dialogue handling

        # Throttle game button updates to avoid frequent server requests
        current_time = pygame.time.get_ticks()
        if current_time - self.last_update_time >= self.update_interval:
            self.last_update_time = current_time
            self.update_load_game_buttons()

        # Update game selection buttons
        for button in self.load_game_buttons:
            button.update()

    def handle_events(self, events):
        """Handle user input events, such as clicks."""
        super().handle_events(events)  # Call the base class event handler

        if not self.dialogue_box:  # Only handle button clicks if no dialogue is active
            for event in events:
                if event.type == MOUSEBUTTONDOWN:
                    self.handle_button_clicks()

        # Handle game load confirmation dialogue
        if self.state.action["task"] == "load_game" and self.state.action["status"] != "open":
            self.handle_game_loading()

    def handle_button_clicks(self):
        """Handle clicks on the load game buttons."""
        for button in self.load_game_buttons:
            if button.collide():
                # Set the action to load the game and open a dialogue box
                self.set_action("load_game", button.text, "open")
                self.make_dialogue_box(f'Do you want to load the game {button.text}?', actions=["yes", "no"])
                print(f"Selected game: {button.text}")

    def handle_game_loading(self):
        """Handle the confirmation of loading a game."""
        if self.state.action["status"] == 'yes':
            game_name = self.state.action["content"]
            game = next((game for game in self.games if f"{game.opponent_name} - {game.date}" == game_name), None)
            if game:
                # Load the game and set the screen to the actual game
                self.state.game = game
                self.state.set_msg(f"Loaded game with {game.opponent_name}")
                self.state.screen = "game"
                print(f"Game loaded successfully with {game.opponent_name}")
            else:
                print("Game not found")
                self.state.set_msg("Game not found")
        elif self.state.action["status"] == 'no':
            print("Game load cancelled")

        # Reset action to ensure further interactions are possible
        self.reset_action()

    def reset_action(self):
        """Reset the action status and clear dialogue interactions."""
        print(f"Resetting action. Task: {self.state.action['task']}, Status: {self.state.action['status']}")
        self.state.action = {"task": None, "content": None, "status": None}
