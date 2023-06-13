import pygame
from pygame.locals import *
from Screen import Screen
import settings
from utils import Button
import requests

class NewGameScreen(Screen):
    def __init__(self, state):
        super().__init__(state)

        self.users = []
        self.possible_opponents = []
        self.challenge_buttons = []

        self.open_challenges = []
        self.open_opponents = []
        self.open_challenge_buttons = []

    def make_buttons(self, button_names, x=0.0, y=0.0):
        buttons = [Button(self.window, settings.get_x(x), settings.get_y(y + 0.1 * i), user) for i, user in enumerate(button_names)]
        return buttons

    """
    def make_challenge_buttons(self):
        buttons = [Button(self.window, settings.get_x(0.1), settings.get_y(0.2 + 0.1 * i), user) for i, user in enumerate(self.possible_opponents)]
        return buttons

    def make_open_challenge_buttons(self):
        buttons = [Button(self.window, settings.get_x(0.5), settings.get_y(0.2 + 0.1 * i), user) for i, user in
                   enumerate(self.open_opponents)]
        return buttons
    """

    def send_challenge(self, opponent):
        print("eins")
        response = requests.post(f'{settings.SERVER_URL}/challenge',
                                 data={'challenger': self.state.username, 'opponent': opponent})
        print('zwei')
        self.state.set_message(response.json()['message'])
        #if response.status_code != 200:
        #    print("Failed to send challenge")
        self.render()

    def update_challenge_buttons(self):
        self.users = self.get_users()
        self.possible_opponents = self.get_possible_opponents()
        self.challenge_buttons = self.make_buttons(self.possible_opponents, 0.1, 0.2)

        #self.users = self.get_users()
        #self.possible_opponents =
        #self.challenge_buttons = [Button(self.window, settings.get_x(0.1), settings.get_y(0.2 + 0.1 * i), user) for i, user in enumerate(self.users)]

    def update_open_challenges_buttons(self):

        self.open_challenges = self.get_open_challenges()
        self.open_opponents = self.get_open_opponents()
        self.open_challenge_buttons = self.make_buttons(self.open_opponents, 0.5, 0.2)

        #self.open_challenges = self.get_open_challenges()
        #self.open_challenge_buttons = self.make_open_challenge_buttons()

    def get_open_opponents(self):
        opponents = []
        for challenge in self.open_challenges:
            if challenge["challenger"] == self.state.username:
                opponents.append(challenge["challenged"])
            else:
                opponents.append(challenge["challenger"])
        return opponents

    def get_possible_opponents(self):
        opponents = []
        for user in self.users:
            if user not in self.open_opponents:
                opponents.append(user)
        return opponents

    def get_users(self):
        response = requests.get(f'{settings.SERVER_URL}/get_users', params={'username': self.state.username})
        if response.status_code != 200:
            print("Failed to get users")
            return []
        users = response.json()['users']
        return users

    def get_open_challenges(self):
        response = requests.get(f'{settings.SERVER_URL}/open_challenges', params={'username': self.state.username})
        if response.status_code != 200:
            print("Failed to get challenges")
            print(response.json()['message'])
            return []
        challenges = response.json()['challenges']
        return challenges

    def render(self):

        self.window.fill(settings.BACKGROUND_COLOR)
        self.draw_text('Possible Opponents', settings.BLACK, settings.get_x(0.1), settings.get_x(0.1))
        self.draw_text('Open Challenges', settings.BLACK, settings.get_x(0.5), settings.get_x(0.1))

        for button in self.challenge_buttons + self.open_challenge_buttons:
            button.draw()

        super().render()

        pygame.display.update()

    def update(self, events):

        current_time = pygame.time.get_ticks()
        if current_time - self.last_update_time >= self.update_interval:
            self.last_update_time = current_time
            #self.update_users()
            #self.update_open_challenges()
            #self.update_possible_opponents()
            self.update_challenge_buttons()
            self.update_open_challenges_buttons()

        for button in self.challenge_buttons + self.open_challenge_buttons:
            button.update_color()

        for event in events:
            if event.type == MOUSEBUTTONDOWN:
                for button in self.challenge_buttons:
                    if button.collide():
                        self.set_action("new_game_challenge", button.text, "open")
                        self.make_dialogue_box('Do you want to start a game with ' + button.text + '?')
                for button in self.open_challenge_buttons:
                    if button.collide():
                        self.set_action("accept_game_challenge", button.text, "open")
                        self.make_dialogue_box('Do you want to accept a game with ' + button.text + '?')

        if self.state.action["task"] == "new_game_challenge" and self.state.action["status"] != "open":
            if self.state.action["status"] == 'accept':
                opponent = self.state.action["content"]
                self.send_challenge(opponent)
            self.reset_action()

