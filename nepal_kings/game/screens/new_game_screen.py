import pygame
from pygame.locals import *
from game.screens.screen import Screen
from game.core.game import Game
from config import settings
from utils.utils import Button
from utils.game_service import fetch_users, fetch_user, create_challenge, remove_challenge, create_game

class NewGameScreen(Screen):
    def __init__(self, state):
        super().__init__(state)

        self.users = []
        self.user = {}
        self.open_challenges = []
        self.open_opponents = {}
        self.possible_opponents = []

        # Buttons for challenges and possible opponents
        self.challenge_buttons = []
        self.open_challenge_buttons = []

    def update_all_challenge_buttons(self):
        """Update the buttons for open challenges and possible opponents."""
        try:
            self.users = fetch_users(self.state.user_dict['username'])
            self.user = fetch_user(self.state.user_dict['username'])
        except Exception as e:
            self.state.set_msg(f"Error fetching users or user data: {str(e)}")
            return

        self.open_challenges = self.user['challenges_issued'] + self.user['challenges_received']
        self.open_opponents = {}

        # Prepare open opponents and possible opponents
        for challenge in self.open_challenges:
            opponent_id = challenge['challenger_id'] if challenge['challenger_id'] != self.user['id'] else challenge['challenged_id']
            opponent = next(user for user in self.users if user['id'] == opponent_id)
            self.open_opponents[challenge['id']] = opponent

        self.possible_opponents = [user for user in self.users if user not in self.open_opponents.values()]

        # Create buttons for possible opponents and open challenges
        self.challenge_buttons = self.make_buttons([user['username'] for user in self.possible_opponents], 0.1, 0.2)
        self.open_challenge_buttons = self.make_buttons([opponent['username'] for opponent in self.open_opponents.values()], 0.5, 0.2)

    def render(self):
        """Render the New Game Screen and buttons."""
        self.window.fill(settings.BACKGROUND_COLOR)
        self.draw_text('Possible Opponents', settings.MENU_TEXT_COLOR_HEADER, settings.get_x(0.1), settings.get_y(0.1))
        self.draw_text('Open Challenges', settings.MENU_TEXT_COLOR_HEADER, settings.get_x(0.5), settings.get_y(0.1))

        # Draw all buttons (for both challenges and possible opponents)
        for button in self.challenge_buttons + self.open_challenge_buttons:
            button.draw()

        super().render()  # Render the dialogue box and control buttons

        pygame.display.update()

    def update(self, events):
        """Update the New Game Screen (without handling events)."""
        super().update()  # Call the base class update for buttons and other components

        # Throttle challenge button updates to avoid frequent server requests
        current_time = pygame.time.get_ticks()
        if current_time - self.last_update_time >= self.update_interval:
            self.last_update_time = current_time
            self.update_all_challenge_buttons()

        # Update buttons for challenges and possible opponents
        for button in self.challenge_buttons + self.open_challenge_buttons:
            button.update()

    def handle_events(self, events):
        """Handle user input events, such as clicks."""
        super().handle_events(events)  # Call the base class event handler for common interactions

        for event in events:
            if event.type == MOUSEBUTTONDOWN:
                self.handle_button_clicks()

        # Handle dialogue actions (for accepting/rejecting challenges)
        if self.state.action["task"] == "new_game_challenge" and self.state.action["status"] != "open":
            if self.state.action["status"] == 'accept':
                opponent = self.state.action["content"]
                self.handle_create_challenge(opponent['username'])
            self.reset_action()
        elif self.state.action["task"] == "accept_game_challenge" and self.state.action["status"] != "open":
            challenge = self.state.action["content"]
            if self.state.action["status"] == 'accept':
                self.handle_create_game(challenge)
            elif self.state.action["status"] == 'reject':
                self.handle_remove_challenge(challenge['id'])
            self.reset_action()

    def handle_button_clicks(self):
        """Handle clicks on challenge and opponent buttons."""
        # Handle challenge creation for possible opponents
        for button, user in zip(self.challenge_buttons, self.possible_opponents):
            if button.collide():
                self.set_action("new_game_challenge", user, "open")
                self.make_dialogue_box(f'Do you want to start a game with {button.text}?', actions=["accept", "reject"])

        # Handle accepting or removing open challenges
        for button, challenge in zip(self.open_challenge_buttons, self.open_challenges):
            if button.collide():
                if challenge in self.user['challenges_issued']:
                    self.make_dialogue_box(f'You have challenged {button.text} at {challenge["date"]}')
                else:
                    self.set_action("accept_game_challenge", challenge, "open")
                    self.make_dialogue_box(f'Do you want to accept a game with {button.text}?', actions=["accept", "reject"])

    def handle_create_challenge(self, opponent_name):
        """Create a new challenge and handle potential errors."""
        response = create_challenge(self.state.user_dict['username'], opponent_name)
        if response['success']:
            self.state.set_msg(f"Challenge sent to {opponent_name}")
        else:
            self.state.set_msg(response['message'])

    def handle_create_game(self, challenge):
        """Create a new game and remove the challenge after successful game creation."""
        response = create_game(challenge['id'])
        if response['success'] and 'game' in response:
            self.state.game = Game(response['game'], self.state.user_dict)
            self.handle_remove_challenge(challenge['id'])  # Remove the challenge after game creation
            self.state.screen = "game"
        else:
            self.state.set_msg(response['message'])
            print(response['message'])

    def handle_remove_challenge(self, challenge_id):
        """Remove a challenge and handle potential errors."""
        response = remove_challenge(challenge_id)
        if not response['success']:
            self.state.set_msg(response['message'])

    def reset_action(self):
        """Reset the action status and clear dialogue interactions."""
        print(f"Resetting action. Task: {self.state.action['task']}, Status: {self.state.action['status']}")
        self.state.action = {"task": None, "content": None, "status": None}
