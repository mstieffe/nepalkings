import pygame
from pygame.locals import *
#from game.components.card_img import CardImg
#from game.components.card_slot import CardSlot
from config import settings
from typing import Dict
#from utils.utils import GameButton
from game.components.suit_icon_button import SuitIconButton
from nepal_kings.game.components.figure_icon import FigureIconButton
from game.components.button_list_shifter import ButtonListShifter
#from nepal_kings.game.components.buttons import FigureIconButton, SuitIconButton, ButtonListShifter
from game.components.figure import FigureManager
from utils.utils import Button


class OptionBox:
    """General box to display multiple sets of options."""

    def __init__(self, window, game, option_dict: Dict, x: int = 0.0, y: int = 0.0):
        self.window = window
        self.game = game
        self.option_dict = option_dict
        self.x = x
        self.y = y

        # Load background attributes
        self.background_image = self.load_background()

        active_option_list = list(self.option_dict.keys())[0]

        # Initialize buttons and UI components
        self.initialize_buttons()
        # Store selected figures and suits

        #self.selected_options = []

    def initialize_buttons(self):
        """Initialize option buttons and assign them to shifters."""
        self.option_buttons = []
        for i, option_list_name in enumerate(self.option_dict.keys()):
            self.option_buttons.append(
                Button(self.window, 
                       self.x + settings.BUILD_FIGURE_BACKGROUND_IMG_WIDTH*0.2 + i*settings.BUILD_FIGURE_BACKGROUND_IMG_WIDTH*0.2, 
                       self.y + settings.BUILD_FIGURE_BACKGROUND_IMG_HEIGHT*0.2, 
                       option_list_name,
                       width=settings.BUILD_FIGURE_BACKGROUND_IMG_WIDTH*0.1,
                       height=settings.BUILD_FIGURE_BACKGROUND_IMG_HEIGHT*0.1,)
            )
        print(self.option_buttons)


    def load_background(self):
        """Load and scale the background image."""
        background_image = pygame.image.load(settings.BUILD_FIGURE_BACKGROUND_IMG_PATH)
        return pygame.transform.scale(
            background_image,
            (settings.BUILD_FIGURE_BACKGROUND_IMG_WIDTH, settings.BUILD_FIGURE_BACKGROUND_IMG_HEIGHT)
        )

    def update(self, game):
        """Update the game state and button components."""
        self.game = game
        for button in self.option_buttons:
            button.update()


    def handle_events(self, events):
        """Handle events for button interactions."""
        for event in events:
            if event.type == MOUSEBUTTONDOWN:
                for button in self.option_buttons:
                    if button.collide():
                        for other_button in self.option_buttons:
                            other_button.active = False
                        button.active = True
                        self.active_option_list = button.text


    def draw(self):
        """Draw the screen, including buttons and background."""
        if self.game:
            # Draw background image
            self.window.blit(self.background_image, (self.x, self.y))

            # Draw figure and suit buttons
            for button in self.option_buttons:
                button.draw()

    def draw_text(self, text, color, x, y):
        """Draw text on the window."""
        text_obj = self.font.render(text, True, color)
        text_rect = text_obj.get_rect()
        text_rect.topleft = (x, y)
        self.window.blit(text_obj, text_rect)
