import pygame
from pygame.locals import *
from game.screens.screen import Screen
from game.core.game import Game
from config import settings
from utils.utils import Button
import requests

class NewGameScreen(Screen):
    def __init__(self, state):
        super().__init__(state)

        self.users = None
        self.user = []
        self.open_challenges = []
        self.open_opponents = {}
        self.possible_opponents = []

        self.challenge_buttons = []
        self.open_challenge_buttons = []

    def create_game(self, challenge_id):
        response = requests.post(f'{settings.SERVER_URL}/games/create_game',
                                 data={'challenge_id': challenge_id})
        self.state.set_msg(response.json()['message'])
        if response.status_code != 200:
            print("Failed to create game")
            print(response.json()['message'])
        game_dict = response.json()['game']
        self.state.game = Game(game_dict, self.state.user_dict)
        return response.json()

    def create_challenge(self, opponent_name):
        response = requests.post(f'{settings.SERVER_URL}/challenges/create_challenge',
                                 data={'challenger': self.state.user_dict['username'], 'opponent': opponent_name})
        self.state.set_msg(response.json()['message'])
        if response.status_code != 200:
            print("Failed to send challenge")

    def remove_challenge(self, challenge_id):
        response = requests.post(f'{settings.SERVER_URL}/challenges/remove_challenge',
                                 data={'challenge_id': challenge_id})
        self.state.set_msg(response.json()['message'])
        if response.status_code != 200:
            print("Failed to remove challenge")

    def update_all_challenge_buttons(self):
        self.users = self.get_users()
        self.user = self.get_user()
        #print(self.user)
        self.open_challenges = self.user['challenges_issued'] + self.user['challenges_received']
        self.open_opponents = {}

        for challenge in self.open_challenges:
            opponent_id = challenge['challenger_id'] if challenge['challenger_id'] != self.user['id'] else challenge['challenged_id']
            opponent = [user for user in self.users if user['id'] == opponent_id][0]
            self.open_opponents[challenge['id']] = opponent

        self.possible_opponents = [user for user in self.users if user not in self.open_opponents.values()]

        #self.possible_opponents = self.get_possible_opponents()
        challenge_button_names = [opponent['username'] for opponent in self.possible_opponents]
        self.challenge_buttons = self.make_buttons(challenge_button_names, 0.1, 0.2)
        open_challenge_button_names = [opponent['username'] for opponent in self.open_opponents.values()]
        self.open_challenge_buttons = self.make_buttons(open_challenge_button_names, 0.5, 0.2)

    #def update_open_challenges_buttons(self):
    #    self.open_challenges = self.get_open_challenges()
    #    self.open_opponents, self.challenge_dict = self.get_open_opponents()
    #    self.open_challenge_buttons = self.make_buttons(self.open_opponents, 0.5, 0.2)

    """
    def get_open_opponents(self):
        opponents, challenge_dict = [], {}
        for challenge in self.open_challenges:
            print(challenge)
            if challenge["challenger"] == self.state.user_dict['username']:
                opponents.append(challenge["challenged"]['username'])
                challenge_dict[challenge["challenged"]] = "challenger"
            else:
                opponents.append(challenge["challenger"]['username'])
                challenge_dict[challenge["challenger"]] = "challenged"
        return opponents, challenge_dict
    """

    """
    def get_possible_opponents(self):
        opponents = []
        for challenge in self.user['challenges_issued']:

        for user in self.users:
            if user['username'] not in self.open_opponents:
                opponents.append(user['username'])
        return opponents
    """

    def get_users(self):
        response = requests.get(f'{settings.SERVER_URL}/auth/get_users', params={'username': self.state.user_dict['username']})
        if response.status_code != 200:
            print("Failed to get users")
            return []
        users = response.json()['users']
        return users

    def get_user(self):
        response = requests.get(f'{settings.SERVER_URL}/auth/get_user', params={'username': self.state.user_dict['username']})
        if response.status_code != 200:
            print("Failed to get user")
            return {}
        user = response.json()['user']
        return user

    """
    def get_open_challenges(self):
        response = requests.get(f'{settings.SERVER_URL}/challenges/open_challenges', params={'username': self.state.user_dict['username']})
        if response.status_code != 200:
            print("Failed to get challenges")
            print(response.json()['message'])
            return []
        challenges = response.json()['challenges']
        return challenges
    """
    def render(self):
        self.window.fill(settings.BACKGROUND_COLOR)
        self.draw_text('Possible Opponents', settings.MENU_TEXT_COLOR_HEADER, settings.get_x(0.1), settings.get_y(0.1))
        self.draw_text('Open Challenges', settings.MENU_TEXT_COLOR_HEADER, settings.get_x(0.5), settings.get_y(0.1))

        for button in self.challenge_buttons + self.open_challenge_buttons:
            button.draw()

        super().render()

        pygame.display.update()

    def update(self, events):
        super().update()

        current_time = pygame.time.get_ticks()
        if current_time - self.last_update_time >= self.update_interval:
            self.last_update_time = current_time
            self.update_all_challenge_buttons()
            #self.update_open_challenges_buttons()

        for button in self.challenge_buttons + self.open_challenge_buttons:
            button.update()

        for event in events:
            if event.type == MOUSEBUTTONDOWN:
                for button, user in zip(self.challenge_buttons, self.possible_opponents):
                    if button.collide():
                        self.set_action("new_game_challenge", user, "open")
                        self.make_dialogue_box('Do you want to start a game with ' + button.text + '?', actions=["accept", "reject"])
                for button, challenge in zip(self.open_challenge_buttons, self.open_challenges):
                    if button.collide():
                        if challenge in self.user['challenges_issued']:
                            self.make_dialogue_box(f'You have challenged {button.text} at {challenge["date"]}')
                        else:
                            self.set_action(f"accept_game_challenge", challenge, "open")
                            self.make_dialogue_box(f'Do you want to accept a game with {button.text}?', actions=["accept", "reject"])

        if self.state.action["task"] == "new_game_challenge" and self.state.action["status"] != "open":
            if self.state.action["status"] == 'accept':
                opponent = self.state.action["content"]
                self.create_challenge(opponent['username'])
            self.reset_action()
        elif self.state.action["task"] == "accept_game_challenge" and self.state.action["status"] != "open":
            challenge = self.state.action["content"]
            if self.state.action["status"] == 'accept':
                self.create_game(challenge['id'])
                self.remove_challenge(challenge['id'])
                self.state.screen = "game"
            elif self.state.action["status"] == 'reject':
                self.remove_challenge(challenge['id'])

            self.reset_action()
