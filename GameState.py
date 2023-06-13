import pygame

class GameState:
    def __init__(self):
        self.username = None
        self.screen = "login"
        self.msg = ''
        self.msg_time = None  # Time when the message was set

        self.user_response = None

    def set_message(self, msg):
        self.msg = msg
        self.msg_time = pygame.time.get_ticks()  # Record the current time

    def update(self):
        if self.msg:
            # Check if 5 seconds (5000 milliseconds) have passed
            if pygame.time.get_ticks() - self.msg_time > 5000:
                self.msg = ''
                self.msg_time = None