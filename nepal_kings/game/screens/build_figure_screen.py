import pygame
from pygame.locals import *
from collections import Counter
from config import settings
from game.screens.sub_screen import SubScreen
from game.components.figures.figure_manager import FigureManager
from game.components.cards.card import Card
from game.components.buttons.confirm_button import ConfirmButton
from game.components.figures.figure_db_service import FigureDbService


class BuildFigureScreen(SubScreen):
    """Screen for building a figure by selecting figures and suits."""

    def __init__(self, window, state, x: int = 0.0, y: int = 0.0, title=None):
        super().__init__(window, state.game, x, y, title)

        # Initialize the figure manager and load figures
        self.figure_manager = FigureManager()

        self.state = state
        self.game = state.game

        # Map display names to internal color names
        self.color_mapping = {
            'Djungle': 'offensive',
            'Himalaya': 'defensive'
        }

        # Initialize buttons and UI components
        self.init_figure_info_box()
        self.init_color_buttons()
        self.init_figure_family_icons()
        self.init_scroll_test_list_shifter()

        self.color = "Djungle"

        # Store selected figures
        self.selected_figure_family = None
        self.selected_figures = []

        self.confirm_button = ConfirmButton(
            self.window,
            settings.BUILD_FIGURE_CONFIRM_BUTTON_X,
            settings.BUILD_FIGURE_CONFIRM_BUTTON_Y,
            "create!"
        )

    def create_figure_in_db(self, selected_figure):
        """Insert the selected figure into the database."""
        # Map dummy cards in the figure to real cards in the player's hand
        real_cards = self.map_figure_cards_to_hand(selected_figure)

        if real_cards is None:
            print(f"Failed to create figure: Could not find all cards in the player's hand.")
            return

        # Update the selected figure with real cards
        selected_figure.cards = real_cards
        selected_figure.key_cards = [card for card in real_cards if card in selected_figure.key_cards]
        
        # Update number_card only if it exists
        if selected_figure.number_card is not None:
            selected_figure.number_card = next((card for card in real_cards if card == selected_figure.number_card), None)
        
        # Update upgrade_card only if it exists
        if selected_figure.upgrade_card is not None:
            selected_figure.upgrade_card = next((card for card in real_cards if card == selected_figure.upgrade_card), None)

        # Save the figure to the database
        response = FigureDbService.save_figure(
            figure=selected_figure,
            player_id=self.game.player_id,
            game_id=self.game.game_id
        )

        if response.get('success'):
            print(f"Figure {selected_figure.name} created successfully in the database.")
        else:
            print(f"Failed to create figure: {response.get('message', 'Unknown error')}")

        # make log messsage
        #self.game.add_log_entry(round_number, turn_number, message, self.current_player.get('username', 'Player'), 'card_change')
        self.game.add_log_entry(
            self.game.current_round,
            self.game.current_player.get('turns_left', 0) ,
            f"{self.game.current_player.get('username', 'Player')} created a {selected_figure.family.field} figure with {len(selected_figure.cards)} cards",
            self.game.current_player.get('username', 'Player'),
            'figure_created'
        )

        self.game.update()



    def init_scroll_test_list_shifter(self):
        """Initialize the scroll text list shifter."""
        self.make_scroll_text_list_shifter(
            self.scroll_text_list, 
            settings.BUILD_FIGURE_SCROLL_TEXT_X, 
            settings.BUILD_FIGURE_SCROLL_TEXT_Y,
            scroll_height=settings.BUILD_FIGURE_INFO_BOX_SCROLL_HEIGHT
        )


    def init_figure_family_icons(self):
        """Initialize figure family icons and their shifters.
        
        For castle families, only show the King icon (not Maharaja).
        """
        self.figure_family_buttons = {}
        
        for color in ['offensive', 'defensive']:
            families = self.figure_manager.families_by_color[color]
            buttons = []
            
            for family in families:
                # Skip Maharaja families - only show King families
                if 'Maharaja' in family.name:
                    continue
                
                buttons.append(
                    family.make_icon(
                        self.window,
                        self.game,
                        family.build_position[0],
                        family.build_position[1]
                    )
                )
            
            self.figure_family_buttons[color] = buttons

    def init_color_buttons(self):
        """Initialize color buttons."""
        colors = ['Djungle', 'Himalaya']
        self.color_buttons = [
            super(BuildFigureScreen, self).make_button(
                color,
                settings.BUILD_FIGURE_COLOR_BUTTON_X + settings.SUB_SCREEN_BUTTON_DELTA_X * i,
                settings.BUILD_FIGURE_COLOR_BUTTON_Y,
                button_img_active=settings.BUILD_FIGURE_COLOR_BUTTON_ACTIVE_IMG,
                button_img_inactive=settings.BUILD_FIGURE_COLOR_BUTTON_INACTIVE_IMG
            )
            for i, color in enumerate(colors)
        ]
        self.color_buttons[0].active = True
        self.buttons += self.color_buttons

    def init_figure_info_box(self):
        """Initialize figure info box."""
        super().init_sub_box_background(
            settings.BUILD_FIGURE_INFO_BOX_X,
            settings.BUILD_FIGURE_INFO_BOX_Y,
            settings.BUILD_FIGURE_INFO_BOX_WIDTH,
            settings.BUILD_FIGURE_INFO_BOX_HEIGHT
        )
        super().init_scroll_background(
            settings.BUILD_FIGURE_INFO_BOX_SCROLL_X,
            settings.BUILD_FIGURE_INFO_BOX_SCROLL_Y,
            settings.BUILD_FIGURE_INFO_BOX_SCROLL_WIDTH,
            settings.BUILD_FIGURE_INFO_BOX_SCROLL_HEIGHT
        )

        self.build_hierarchy = pygame.image.load(settings.BUILD_HIERARCHY_IMG_PATH).convert_alpha()
        self.build_hierarchy = pygame.transform.smoothscale(
            self.build_hierarchy,
            (settings.BUILD_HIERARCHY_WIDTH, settings.BUILD_HIERARCHY_HEIGHT)
        )

    def update(self, game):
        """Update the game state and button components."""
        super().update(game)
        self.game = game

        if self.game.turn:
            self.confirm_button.disabled = False
        else:
            self.confirm_button.disabled = True

        # Update icon states based on available cards
        self.update_family_icon_states()

        internal_color = self.color_mapping.get(self.color, self.color)
        for button in self.figure_family_buttons[internal_color]:
            button.update()

        if self.scroll_text_list_shifter:
            selected_figure = self.scroll_text_list_shifter.get_current_selected()
            if selected_figure:
                self.confirm_button.update()

    def update_family_icon_states(self):
        """Update the active state of family icons based on whether they can be built."""
        for color in ['offensive', 'defensive']:
            for button in self.figure_family_buttons[color]:
                # Check if any figure in this family can be built with current hand
                buildable_figures = self.get_figures_in_hand(button.family)
                # Set active state: true if at least one figure can be built
                button.is_active = len(buildable_figures) > 0

    def handle_events(self, events):
        """Handle events for button interactions."""
        super().handle_events(events)

        internal_color = self.color_mapping.get(self.color, self.color)
        for button in self.figure_family_buttons[internal_color]:
            button.handle_events(events)

        if self.scroll_text_list_shifter:
            selected_figure = self.scroll_text_list_shifter.get_current_selected()

        if self.dialogue_box:

            response = self.dialogue_box.update(events)
            if response:
                
                print("Response:", response)
                if response == 'yes':
                    print("Creating figure...")
                    self.create_figure_in_db(selected_figure)

                    self.make_dialogue_box(
                        message="Figure created successfully!",
                        actions=['ok'],
                        icon="figure",
                        title="Figure created!"
                    )

                elif response in ['cancel', 'got it!']:
                    self.dialogue_box = None
                elif response == 'ok':
                    self.dialogue_box = None
                    self.state.subscreen = "field"

        else:

            for event in events:
                if event.type == MOUSEBUTTONDOWN:

                    # Handle confirm button only if a figure is selected
                    if selected_figure and self.confirm_button.collide() and not self.confirm_button.disabled:
                        #self.create_figure_in_db(selected_figure)

                        # get figure family button of selected figure
                        internal_color = self.color_mapping.get(self.color, self.color)
                        for button in self.figure_family_buttons[internal_color]:
                            if button.family == selected_figure.family:
                                selected_family_button = button
                                break

                        #print("Selected Figure:", selected_figure)
                        #print("Selected Family Button:", selected_family_button)

                        self.make_dialogue_box(
                            message="Do you want to build this figure?",
                            actions=['yes', 'cancel'],
                            images=[selected_family_button],
                            icon="question",
                            title="Create Figure",

                        )
                        #print("making dialogue box")
                    elif selected_figure and self.confirm_button.collide() and self.confirm_button.disabled:
                        self.make_dialogue_box(
                            message="You can only build figures on your turn.",
                            actions=['got it!'],
                            icon="error",
                            title="Not Your Turn"
                        )
                    


                    for button in self.color_buttons:
                        if button.collide():
                            self.update_color_selection(button)

                    internal_color = self.color_mapping.get(self.color, self.color)
                    for button in self.figure_family_buttons[internal_color]:
                        if button.collide():
                            self.update_figure_family_selection(button)

    def update_color_selection(self, button):
        """Update color selection when a color button is clicked."""
        for other_button in self.buttons:
            other_button.active = False
        button.active = True
        self.color = button.text

    def update_figure_family_selection(self, button):
        """Update figure family selection."""
        self.selected_figure_family = button.family
        internal_color = self.color_mapping.get(self.color, self.color)
        for other_button in self.figure_family_buttons[internal_color]:
            other_button.clicked = False
        button.clicked = True
        
        figures = self.get_figures_in_hand(button.family)
        if figures:
            self.selected_figures = figures
            self.scroll_text_list = [{"title": figure.name,
                                      "figure_type": f"{figure.family.field.capitalize()} Figure",
                                      "text": figure.family.description,
                                      "power": figure.get_value(),
                                      "support": figure.get_battle_bonus(),
                                      "produces": figure.produces if figure.produces else None,
                                      "requires": figure.requires if figure.requires else None,
                                      "cannot_attack": getattr(figure, 'cannot_attack', False),
                                      "must_be_attacked": getattr(figure, 'must_be_attacked', False),
                                      "rest_after_attack": getattr(figure, 'rest_after_attack', False),
                                      "distance_attack": getattr(figure, 'distance_attack', False),
                                      "buffs_allies": getattr(figure, 'buffs_allies', False),
                                      "blocks_bonus": getattr(figure, 'blocks_bonus', False),
                                      "cards": figure.cards,
                                      "content": figure}
                                     for figure in figures]
        else:
            # Get figure instances to show their attributes even when cards are missing
            self.scroll_text_list = []
            for suit in button.family.suits:
                # Get figure instance to access its attributes
                figure = button.family.get_figures_by_suit(suit)[0]
                self.scroll_text_list.append({
                    "title": button.family.name,
                    "figure_type": f"{figure.family.field.capitalize()} Figure",
                    "text": button.family.description,
                    # Don't show power when cards are missing
                    "support": figure.get_battle_bonus(),
                    "produces": figure.produces if figure.produces else None,
                    "requires": figure.requires if figure.requires else None,
                    "cannot_attack": getattr(figure, 'cannot_attack', False),
                    "must_be_attacked": getattr(figure, 'must_be_attacked', False),
                    "rest_after_attack": getattr(figure, 'rest_after_attack', False),
                    "distance_attack": getattr(figure, 'distance_attack', False),
                    "buffs_allies": getattr(figure, 'buffs_allies', False),
                    "blocks_bonus": getattr(figure, 'blocks_bonus', False),
                    "cards": self.get_given_cards(button.family, suit),
                    "missing_cards": self.get_missing_cards_converted_ZK(button.family, suit),
                    "content": None
                })
        self.scroll_text_list_shifter.set_displayed_texts(self.scroll_text_list)

    def draw(self):
        """Draw the screen, including buttons and background."""
        super().draw()

        self.window.blit(self.build_hierarchy, (settings.BUILD_HIERARCHY_X, settings.BUILD_HIERARCHY_Y))

        internal_color = self.color_mapping.get(self.color, self.color)
        for button in self.figure_family_buttons[internal_color]:
            button.draw()

        if self.scroll_text_list_shifter:
            selected_figure = self.scroll_text_list_shifter.get_current_selected()
            if selected_figure:
                self.confirm_button.draw()

        super().draw_on_top()

    def map_figure_cards_to_hand(self, figure):
        """
        Map dummy cards in the figure to real cards in the player's hand.
        Handles duplicate cards correctly by tracking which cards have been used.

        :param figure: The Figure object with dummy cards.
        :return: A list of real Card objects mapped from the player's hand.
        """
        main_cards, side_cards = self.game.get_hand()
        hand_cards = main_cards + side_cards

        # Create a list of available cards (will remove as we use them)
        available_cards = hand_cards.copy()

        # Map figure cards to real cards in the hand
        real_cards = []
        for dummy_card in figure.cards:
            # Find the first matching card in available_cards
            real_card = None
            for i, card in enumerate(available_cards):
                if card.to_tuple() == dummy_card.to_tuple():
                    real_card = card
                    # Remove this card from available so we don't use it twice
                    available_cards.pop(i)
                    break
            
            if real_card:
                real_cards.append(real_card)
            else:
                print(f"Card {dummy_card} not found in hand.")
                return None  # Return None if any card is not found

        return real_cards


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

        # Count occurrences of required cards for the figure using tuples
        figure_counter = Counter(card.to_tuple() for card in figure.cards)

        # Get missing cards for the figure
        missing_cards = []
        for card_tuple, count in figure_counter.items():
            if hand_counter[card_tuple] < count:
                # Find the original Card instances that match the missing card tuples
                for card in figure.cards:
                    if card.to_tuple() == card_tuple:
                        missing_cards.extend([card] * (count - hand_counter[card_tuple]))
                        break

        return missing_cards
    
    def get_given_cards(self, figure_family, suit):
        """Get given cards for a figure."""
        # Get all cards in the player's hand
        main_cards, side_cards = self.game.get_hand()
        hand_cards = main_cards + side_cards

        # Count occurrences of each card in the hand using tuples
        hand_counter = Counter(card.to_tuple() for card in hand_cards)

        figure = figure_family.get_figures_by_suit(suit)[0]
        # Count occurrences of required cards for the figure using tuples
        figure_counter = Counter(card.to_tuple() for card in figure.cards)

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
