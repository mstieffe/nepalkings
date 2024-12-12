import pygame
from pygame.locals import *
import pandas as pd
from game.screens.screen import Screen
from config import settings
#from game.components.card_img import CardImg
from game.components.cards.hand import Hand
from game.components.info_scroll import InfoScroll
from game.components.scoreboard_scroll import ScoreboardScroll
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

        self.display_elements = []
        self.initialiaze_scoareboard_scroll()
        self.initialize_info_scroll_resources()
        self.initialize_info_scroll_slots()

        # Define which screen is visible, allowing flexibility in switching between subscreens
        self.active_subscreen = 'build_figure'
        self.subscreens = {
            'field': None,
            'build_figure': BuildFigureScreen(self.window, self.state, x=settings.SUB_SCREEN_X, y=settings.SUB_SCREEN_Y, title='Figure Builder'),
        }

    def initialiaze_scoareboard_scroll(self):
        """Initialize resources for the info scroll."""
        if self.state.game:
            opponent_name = self.state.game.opponent_name
        else:
            opponent_name = "Opponent"
        scoreboard_dict = {
            'Opponent': opponent_name,
            'Turns Left': 4,
            'Round': 1,
            'Score': 0,
            'Opponent Score': 0
        }
        scoreboard_scroll = ScoreboardScroll(
            self.window, 
            settings.SCOREBOARD_SCROLL_X, 
            settings.SCOREBOARD_SCROLL_Y, 
            settings.SCOREBOARD_SCROLL_WIDTH, 
            settings.SCOREBOARD_SCROLL_HEIGHT, 
            scoreboard_dict, 
            settings.SCOREBOARD_SCROLL_BG_IMG_PATH)
        self.display_elements.append(scoreboard_scroll)


    def initialize_info_scroll_resources(self):
        """Initialize resources for the info scroll."""
        resources_df = pd.DataFrame({
            'element': ['food', 'amor', 'material'],
            'icon_img_red': [settings.RESOURCE_ICON_IMG_PATH_DICT['rice'], settings.RESOURCE_ICON_IMG_PATH_DICT['sword'], settings.RESOURCE_ICON_IMG_PATH_DICT['wood']],
            'icon_img_black': [settings.RESOURCE_ICON_IMG_PATH_DICT['meat'], settings.RESOURCE_ICON_IMG_PATH_DICT['shield'], settings.RESOURCE_ICON_IMG_PATH_DICT['stone']],
            'red': [3, 7, 5],
            'black': [0, 0, 6],
        })
        info_scroll = InfoScroll(
            self.window, 
            settings.INFO_SCROLL_RESOURCES_X, 
            settings.INFO_SCROLL_RESOURCES_Y, 
            settings.INFO_SCROLL_WIDTH, 
            settings.INFO_SCROLL_HEIGHT, 
            'Resources', 
            resources_df, 
            settings.INFO_SCROLL_BG_IMG_PATH)
        self.display_elements.append(info_scroll)

    def initialize_info_scroll_slots(self):
        """Initialize slots for the info scroll."""
        slots_df = pd.DataFrame({
            'element': ['castle', 'village', 'military'],
            'icon_img': [settings.SLOT_ICON_IMG_PATH_DICT['castle'], settings.SLOT_ICON_IMG_PATH_DICT['village'], settings.SLOT_ICON_IMG_PATH_DICT['military']],
            'red': ["0/3", "0/0", "0/0"],
            'black': ["2/4", "1/2", "1/1"],
        })
        info_scroll = InfoScroll(
            self.window, 
            settings.INFO_SCROLL_SLOTS_X, 
            settings.INFO_SCROLL_SLOTS_Y, 
            settings.INFO_SCROLL_WIDTH, 
            settings.INFO_SCROLL_HEIGHT, 
            'Slots', 
            slots_df, 
            settings.INFO_SCROLL_BG_IMG_PATH)
        self.display_elements.append(info_scroll)

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

        # Field button (switches to the field subscreen)
        field_button = GameButton(
            self.window, 'map', 'plain',
            settings.FIELD_BUTTON_X, settings.FIELD_BUTTON_Y,
            settings.FIELD_BUTTON_WIDTH,
            settings.FIELD_BUTTON_WIDTH,
            glow_width=settings.FIELD_BUTTON_GLOW_WIDTH,
            symbol_width_big=settings.FIELD_BUTTON_WIDTH_BIG,
            glow_width_big=settings.FIELD_BUTTON_GLOW_WIDTH_BIG,
            state=self.state,
            hover_text='view field!',
            subscreen='field'
        )
        self.game_buttons.append(field_button)

        # Log button (switches to the log subscreen)
        field_button = GameButton(
            self.window, 'letter', 'plain',
            settings.LETTER_BUTTON_X, settings.LETTER_BUTTON_Y,
            settings.LETTER_BUTTON_WIDTH,
            settings.LETTER_BUTTON_WIDTH,
            glow_width=settings.FIELD_BUTTON_GLOW_WIDTH,
            symbol_width_big=settings.LETTER_BUTTON_WIDTH_BIG,
            glow_width_big=settings.FIELD_BUTTON_GLOW_WIDTH_BIG,
            state=self.state,
            hover_text='view log!',
            subscreen='log'
        )
        self.game_buttons.append(field_button)

        home_button = GameButton(
            self.window, 'home', 'plain',
            settings.HOME_BUTTON_X, settings.HOME_BUTTON_Y,
            settings.HOME_BUTTON_WIDTH,
            settings.HOME_BUTTON_WIDTH,
            glow_width=settings.HOME_BUTTON_GLOW_WIDTH,
            symbol_width_big=settings.HOME_BUTTON_WIDTH_BIG,
            glow_width_big=settings.HOME_BUTTON_GLOW_WIDTH_BIG,
            state=self.state,
            hover_text='home menu!',
            subscreen=None
        )
        self.game_buttons.append(home_button)

    def update_game(self):
        """Update the game state and related components."""
        self.state.game.update()
        self.main_hand.update(self.state.game)
        self.side_hand.update(self.state.game)

    def render(self):
        """Render the game screen, buttons, and active subscreen."""
        self.window.fill(settings.BACKGROUND_COLOR)

        for element in self.display_elements:
            element.draw()

        # Draw game-specific text (e.g., opponent name)
        #self.draw_text(self.state.game.opponent_name, settings.BLACK, settings.get_x(0.1), settings.get_x(0.1))

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


