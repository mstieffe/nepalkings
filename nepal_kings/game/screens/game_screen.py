import pygame
from pygame.locals import *
from game.screens.screen import Screen
from config import settings
#from game.components.card_img import CardImg
from game.components.cards.hand import Hand
from utils.utils import GameButton
from game.screens.build_figure_screen import BuildFigureScreen


class GameScreen(Screen):
    def __init__(self, state):
        super().__init__(state)

        # Initialize hands for the game (main and side hands)
        self.main_hand = Hand(self.window, self.state.game, x=settings.MAIN_HAND_X, y=settings.MAIN_HAND_Y)
        self.side_hand = Hand(self.window, self.state.game, x=settings.SIDE_HAND_X, y=settings.SIDE_HAND_Y, type="side_card")

        # Initialize buttons and add to the game_buttons list
        self.initialize_buttons()

        # Define which screen is visible, allowing flexibility in switching between subscreens
        self.active_subscreen = 'build_figure'
        self.subscreens = {
            'field': None,
            'build_figure': BuildFigureScreen(self.window, self.state, x=settings.SUB_SCREEN_X, y=settings.SUB_SCREEN_Y)
        }

    def initialize_buttons(self):
        """Initialize buttons for the game screen, including hand and action buttons."""
        #self.game_buttons = []

        # Add buttons from both hands (main and side hand buttons)
        self.game_buttons.extend(self.main_hand.buttons)
        self.game_buttons.extend(self.side_hand.buttons)

        # Action button (for casting spells)
        action_button = GameButton(
            self.window, 'book', 'plant',
            settings.ACTION_BUTTON_X, settings.ACTION_BUTTON_Y,
            settings.ACTION_BUTTON_WIDTH,
            settings.ACTION_BUTTON_WIDTH,
            state=self.state,
            hover_text='cast spell!'
        )
        self.game_buttons.append(action_button)

        # Build figure button (switches to the build figure subscreen)
        build_button = GameButton(
            self.window, 'hammer', 'rope',
            settings.BUILD_BUTTON_X, settings.BUILD_BUTTON_Y,
            settings.BUILD_BUTTON_WIDTH,
            settings.BUILD_BUTTON_WIDTH,
            state=self.state,
            hover_text='build figure!',
            subscreen='build_figure'
        )
        self.game_buttons.append(build_button)

    def update_game(self):
        """Update the game state and related components."""
        self.state.game.update()
        self.main_hand.update(self.state.game)
        self.side_hand.update(self.state.game)

    def render(self):
        """Render the game screen, buttons, and active subscreen."""
        self.window.fill(settings.BACKGROUND_COLOR)

        # Draw game-specific text (e.g., opponent name)
        self.draw_text(self.state.game.opponent_name, settings.BLACK, settings.get_x(0.1), settings.get_x(0.1))

        # Render game buttons
        #for button in self.game_buttons:
        #    button.draw()

        # Render the main and side hands
        self.main_hand.draw()
        self.side_hand.draw()

        # Render the currently active subscreen
        if self.active_subscreen in self.subscreens and self.subscreens[self.active_subscreen]:
            self.subscreens[self.active_subscreen].draw()

        # Render any general elements (e.g., dialogue box) from the parent class
        super().render()

        # Update the display
        pygame.display.update()

    def update(self, events):
        """Update the game screen and all relevant components."""
        super().update()

        # Throttle updates to avoid constant re-rendering
        current_time = pygame.time.get_ticks()
        if current_time - self.last_update_time >= self.update_interval:
            self.update_game()

        # Update the active subscreen if necessary
        if self.active_subscreen in self.subscreens and self.subscreens[self.active_subscreen]:
            self.subscreens[self.active_subscreen].update(self.state.game)

    def handle_events(self, events):
        """Handle user input events (e.g., clicks, key presses)."""
        super().handle_events(events)

        # Handle events for the main and side hands
        self.main_hand.handle_events(events)
        self.side_hand.handle_events(events)

        # Pass events to the active subscreen
        if self.active_subscreen in self.subscreens and self.subscreens[self.active_subscreen]:
            self.subscreens[self.active_subscreen].handle_events(events)


