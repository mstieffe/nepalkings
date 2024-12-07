import pygame
from pygame.locals import *
from collections import Counter
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
from game.components.cards.card import Card
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
        self.init_scroll_test_list_shifter()

        self.color = "offensive"
        self.suit = None

        # Store selected figures and suits
        self.selected_figure_family = None
        self.selected_figures = []
        self.selected_suits = []


    def init_scroll_test_list_shifter(self):
        self.make_scroll_text_list_shifter(
            self.scroll_text_list,
            settings.BUILD_FIGURE_SCROLL_TEXT_X, 
            settings.BUILD_FIGURE_SCROLL_TEXT_Y)

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

    def get_figures_in_hand(self, figure_family):
        """Get figures in the player's hand."""
        # Get all cards in the player's hand
        main_cards, side_cards = self.game.get_hand()
        hand_cards = main_cards + side_cards

        # Count occurrences of each card in the hand
        hand_counter = Counter(card.to_tuple() for card in hand_cards)

        possible_figures = []
        for figure in figure_family.figures:
            # Count occurrences of required cards for the figure
            figure_counter = Counter(card.to_tuple() for card in figure.cards)
            # Check if the hand has enough cards to build the figure
            if all(hand_counter[card] >= count for card, count in figure_counter.items()):
                possible_figures.append(figure)

        return possible_figures
    
    def get_missing_cards(self, figure):
        """Get missing cards for a figure."""
        # Get all cards in the player's hand
        main_cards, side_cards = self.game.get_hand()
        hand_cards = main_cards + side_cards

        # Count occurrences of each card in the hand using tuples
        hand_counter = Counter(card.to_tuple() for card in hand_cards)
        print("Hand Counter:", hand_counter)

        # Count occurrences of required cards for the figure using tuples
        figure_counter = Counter(card.to_tuple() for card in figure.cards)
        print("Figure Counter:", figure_counter)

        # Get missing cards for the figure
        missing_cards = []
        for card_tuple, count in figure_counter.items():
            if hand_counter[card_tuple] < count:
                # Find the original Card instances that match the missing card tuples
                for card in figure.cards:
                    if card.to_tuple() == card_tuple:
                        missing_cards.extend([card] * (count - hand_counter[card_tuple]))
                        break

        print("Missing Cards:", missing_cards)
        return missing_cards
    
    def get_given_cards(self, figure_family, suit):
        """Get given cards for a figure."""
        # Get all cards in the player's hand
        main_cards, side_cards = self.game.get_hand()
        hand_cards = main_cards + side_cards

        # Count occurrences of each card in the hand using tuples
        hand_counter = Counter(card.to_tuple() for card in hand_cards)
        print("Hand Counter:", hand_counter)

        figure = figure_family.get_figures_by_suit(suit)[0]
        # Count occurrences of required cards for the figure using tuples
        figure_counter = Counter(card.to_tuple() for card in figure.cards)
        print("Figure Counter:", figure_counter)

        # Get given cards for the figure
        given_cards = []
        for card_tuple, count in figure_counter.items():
            if hand_counter[card_tuple] > 0:
                # Find the original Card instances that match the given card tuples
                given_count = min(count, hand_counter[card_tuple])
                for card in figure.cards:
                    if card.to_tuple() == card_tuple and given_count > 0:
                        given_cards.append(card)
                        given_count -= 1

        print("Given Cards:", given_cards)
        return given_cards
    
    def get_missing_cards_converted_ZK(self, figure_family, suit):
        """Get missing cards for all figures in a family."""
        figure = figure_family.get_figures_by_suit(suit)[0]
        missing_cards = []
        for card in self.get_missing_cards(figure):
            if card.is_ZK:
                missing_cards.append(Card('ZK', figure.suit, 0))
            else:
                missing_cards.append(card)
        return missing_cards

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
                        figures = self.get_figures_in_hand(button.family)
                        if figures != []:
                            self.selected_figures = figures
                            self.scroll_text_list = [{"title": figure.name,
                                                 "text": figure.family.description,
                                                 "figure_strength": f"Base Power: {figure.get_value()}",
                                                 "cards": figure.cards}
                                                 for figure in figures]
                        else:
                            self.scroll_text_list = [{"title": button.family.name,
                                                "text": button.family.description,
                                                "figure_strength": "",
                                                "cards": self.get_given_cards(button.family, suit),
                                                "missing_cards": self.get_missing_cards_converted_ZK(button.family, suit)}
                                                for suit in button.family.suits]
                        self.scroll_text_list_shifter.set_displayed_texts(self.scroll_text_list)
                        #print(self.scroll_text_list)
                        #print(self.get_figures_in_hand(button.family))

                        



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

