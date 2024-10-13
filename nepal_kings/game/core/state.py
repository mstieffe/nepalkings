import pygame
from config import settings
#from Game import Game

class State:
    def __init__(self):
        self.user_dict = None
        self.screen = "login"
        self.subscreen = "field"
        self.message_lines = []

        self.game = None # Game()
        self.action = None
        #self.user_response = None


    def set_msg(self, msg):
        lines = msg.split('\n')  # Split the message into lines
        current_time = pygame.time.get_ticks()  # Record the current time

        for line in lines:
            self.message_lines.append((line, current_time))  # Store the line and its disappearance time

    def update(self):
        if self.message_lines:
            current_time = pygame.time.get_ticks()  # Record the current time

            # Create a new list for updated message lines
            updated_message_lines = []

            for line, line_time in self.message_lines:
                if line_time is not None:
                    # Check if the disappearance time has not passed
                    if current_time - line_time <= settings.MESSAGE_DURATION:
                        updated_message_lines.append((line, line_time))

            self.message_lines = updated_message_lines