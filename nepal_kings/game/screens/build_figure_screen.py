import pygame
from pygame.locals import *
#from game.components.card_img import CardImg
#from game.components.card_slot import CardSlot
from config import settings
#from utils.utils import GameButton
from game.components.suit_icon_button import SuitIconButton
#from nepal_kings.game.components.figure_icon import FigureIconButton
from game.components.button_list_shifter import ButtonListShifter
#from game.components.option_box import OptionBox
#from nepal_kings.game.components.buttons import FigureIconButton, SuitIconButton, ButtonListShifter
#from game.components.figure import FigureManager
from game.screens.sub_screen import SubScreen
from game.components.figures.figure_manager import FigureManager
from utils.utils import get_opp_color


class BuildFigureScreen(SubScreen):
    """Screen for building a figure by selecting figures and suits."""

    def __init__(self, window, state, x: int = 0.0, y: int = 0.0):
        super().__init__(window, state.game, x, y)

        # Initialize the figure manager and load figures
        self.figure_manager = FigureManager()

        self.state = state
        self.game = state.game
        # Initialize buttons and UI components
        #self.initialize_option_box()

        # Load background attributes
        #self.background_image = self.load_background()


        #self.initialize_background()
        #self.initialize_color_buttons({"black", "red"})
        #self.initialiaze_suit_buttons_shifter()

        self.init_figure_info_box()
        self.init_color_buttons()
        self.init_suit_icon_buttons()
        self.init_figure_family_icons()

        self.color = "offensive"
        self.suit = None

        # Store selected figures and suits
        self.selected_figure_family = None
        self.selected_figures = []
        self.selected_suits = []


    def init_figure_family_icons(self):
        """Initialize figure family icons and their shifters."""
        # Create figure family icon buttons
        self.figure_family_buttons = {
            'offensive': [family.make_icon(self.window, self.game, family.build_position[0], family.build_position[1]) for family in self.figure_manager.families_by_color['offensive']],
            'defensive': [family.make_icon(self.window, self.game, family.build_position[0], family.build_position[1]) for family in self.figure_manager.families_by_color['defensive']]
        }

    def init_color_buttons(self):
        """Initialize figure and suit buttons and their shifters."""
        # Create suit icon buttons
        colors = ['offensive', 'defensive']
        self.color_buttons = [
            super(BuildFigureScreen, self).make_button(color, settings.BUILD_FIGURE_COLOR_BUTTON_X + settings.SUB_SCREEN_BUTTON_DELTA_X*i, settings.BUILD_FIGURE_COLOR_BUTTON_Y)
            for i, color in enumerate(colors)
        ]
        self.color_buttons[0].active = True

        self.buttons += self.color_buttons

    def init_figure_info_box(self):
        super().init_sub_box_background(settings.BUILD_FIGURE_INFO_BOX_X, settings.BUILD_FIGURE_INFO_BOX_Y, settings.BUILD_FIGURE_INFO_BOX_WIDTH, settings.BUILD_FIGURE_INFO_BOX_HEIGHT)
        super().init_scroll_background(settings.BUILD_FIGURE_INFO_BOX_SCROLL_X, settings.BUILD_FIGURE_INFO_BOX_SCROLL_Y, settings.BUILD_FIGURE_INFO_BOX_SCROLL_WIDTH, settings.BUILD_FIGURE_INFO_BOX_SCROLL_HEIGHT)

        # load build_hierchy image
        self.build_hierarchy = pygame.image.load(settings.BUILD_HIERARCHY_IMG_PATH).convert_alpha()
        self.build_hierarchy = pygame.transform.smoothscale(self.build_hierarchy, (settings.BUILD_HIERARCHY_WIDTH, settings.BUILD_HIERARCHY_HEIGHT))


    def init_suit_icon_buttons(self):
        # Define coordinates as tuples for easy looping
        button_coords = [
            (settings.BUILD_FIGURE_SUIT1_X, settings.BUILD_FIGURE_SUIT1_Y),
            (settings.BUILD_FIGURE_SUIT2_X, settings.BUILD_FIGURE_SUIT2_Y),
            (settings.BUILD_FIGURE_SUIT3_X, settings.BUILD_FIGURE_SUIT3_Y),
            (settings.BUILD_FIGURE_SUIT4_X, settings.BUILD_FIGURE_SUIT4_Y)
        ]

        self.offensive_suit_buttons = {
            'hearts': SuitIconButton(self.window, self.game, 'hearts', *button_coords[0]),
            'diamonds': SuitIconButton(self.window, self.game, 'diamonds', *button_coords[1])
        }
        self.defensive_suit_buttons = {
            'spades': SuitIconButton(self.window, self.game, 'spades', *button_coords[2]),
            'clubs': SuitIconButton(self.window, self.game, 'clubs', *button_coords[3])
        }
        self.suit_buttons_dict = {
            'offensive': list(self.offensive_suit_buttons.values()),
            'defensive': list(self.defensive_suit_buttons.values())
        }

        # init offensive suit buttons with clicked = True
        for button in self.offensive_suit_buttons.values():
            button.clicked = True

        self.suit_buttons = list(self.offensive_suit_buttons.values()) + list(self.defensive_suit_buttons.values())


    def update(self, game):
        """Update the game state and button components."""
        super().update(game)
        self.game = game

        for button in self.suit_buttons:
            button.update(game)
        for button in self.figure_family_buttons[self.color]:
            button.update()



    def handle_events(self, events):
        """Handle events for button interactions."""
        #self.option_box.handle_events(events)
        super().handle_events(events)
        for button in self.suit_buttons:
            button.handle_events(events)
        for button in self.figure_family_buttons[self.color]:
            button.handle_events(events)
        for event in events:
            if event.type == MOUSEBUTTONDOWN:
                # Handle color buttons
                for button in self.color_buttons:
                    if button.collide():
                        for other_button in self.buttons:
                            other_button.active = False
                        button.active = True
                        self.color = button.text
                        self.suit = None
                        for other_button in self.suit_buttons_dict[get_opp_color(self.color)]:
                            other_button.clicked = False
                        for other_button in self.suit_buttons_dict[self.color]:
                            other_button.clicked = True
                # Handle suit buttons
                for button in self.suit_buttons:
                    if button.collide():
                        if self.color != settings.SUIT_TO_COLOR[button.suit]:
                            for other_button in self.color_buttons:
                                other_button.active = not other_button.active
                        self.suit = button.suit
                        print(self.suit)
                        self.color = settings.SUIT_TO_COLOR[self.suit]
                        for other_button in self.suit_buttons_dict[get_opp_color(self.color)]:
                            other_button.clicked = False
                # Handle figure family buttons
                for button in self.figure_family_buttons[self.color]:
                    if button.collide():
                        self.selected_figure_family = button.family
                        for other_button in self.figure_family_buttons[self.color]:
                            other_button.clicked = False
                        button.clicked = True
                        self.scroll_text = [{"title": button.family.name,
                                             "text": button.family.description}]

                        



    def draw(self):
        """Draw the screen, including buttons and background."""
        super().draw()

        self.window.blit(self.build_hierarchy, (settings.BUILD_HIERARCHY_X, settings.BUILD_HIERARCHY_Y))

        for button in self.suit_buttons:
            button.draw()
        for button in self.figure_family_buttons[self.color]:
            button.draw()
        #if self.game:
            # Draw background image
            #self.window.blit(self.background, (self.x, self.y))
            #self.window.blit(self.background_image, (self.x, self.y))



            # Draw figure and suit buttons
            #self.option_box.draw()
            #self.icon_buttons_shifter.draw()
            #self.suit_buttons_shifter.draw()

