import pygame
from pygame.locals import *
from config import settings
from game.screens.sub_screen import SubScreen

class FieldScreen(SubScreen):
    """Screen for building a figure by selecting figures and suits."""

    def __init__(self, window, state, x: int = 0.0, y: int = 0.0, title=None):
        super().__init__(window, state.game, x, y, title)


        self.state = state
        self.game = state.game
      

    def update(self, game):
        """Update the game state and button components."""
        super().update(game)
        self.game = game


    def handle_events(self, events):
        """Handle events for button interactions."""
        #self.option_box.handle_events(events)
        super().handle_events(events)
        for event in events:
            if event.type == MOUSEBUTTONDOWN:
                # Handle color buttons
               pass


    def draw(self):
        """Draw the screen, including buttons and background."""
        super().draw()


