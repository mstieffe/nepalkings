import pygame
from pygame.locals import *
from game.screens.screen import Screen
from config import settings
from utils.utils import Button

class GameMenuScreen(Screen):
    def __init__(self, state):
        super().__init__(state)

        # Initialize menu buttons
        self.button_new = Button(self.window, settings.get_x(0.1), settings.get_y(0.2), "New Game")
        self.button_load = Button(self.window, settings.get_x(0.1), settings.get_y(0.3), "Load Game")

        # Add buttons to menu_buttons list for centralized management
        self.menu_buttons += [self.button_new, self.button_load]

    def render(self):
        """Render the Game Menu Screen and buttons."""
        self.window.fill(settings.BACKGROUND_COLOR)
        self.draw_text('Game Menu', settings.MENU_TEXT_COLOR_HEADER, settings.SCREEN_WIDTH * 0.1, settings.SCREEN_HEIGHT * 0.1)

        # Explicitly render each button
        for button in self.menu_buttons:
            button.draw()

        super().render()

        pygame.display.update()

    def update(self, events):
        """Update the Game Menu Screen and handle events."""
        super().update()  # This will update the buttons and other components

        # Handle user input events like button clicks
        self.handle_events(events)

    def handle_events(self, events):
        """Handle button click events."""
        super().handle_events(events)  # Call parent class handle_events for common events

        for event in events:
            if event.type == MOUSEBUTTONDOWN:
                if self.button_new.collide():
                    self.state.screen = 'new_game'  # Transition to New Game screen
                elif self.button_load.collide():
                    self.state.screen = 'load_game'  # Transition to Load Game screen
