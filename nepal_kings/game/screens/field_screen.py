import pygame
from pygame.locals import *
from config import settings
from game.screens.sub_screen import SubScreen
from game.components.figures.figure_manager import FigureManager
from game.components.figures.figure_icon import FieldFigureIcon
from game.components.figure_detail_box import FigureDetailBox
from utils.figure_service import pickup_figure, upgrade_figure


class FieldScreen(SubScreen):
    """Screen for displaying figures on the field."""

    def __init__(self, window, state, x: int = 0.0, y: int = 0.0, title=None):
        super().__init__(window, state.game, x, y, title)
        self.state = state
        self.game = state.game

        self.figure_manager = FigureManager()

        self.figures = []  # List to store the player's figures
        self.figure_icons = []  # List to store figure icons for rendering
        self.icon_cache = {}  # Cache to store pre-rendered icons
        self.last_figure_ids = set()  # Track the last set of figure IDs
        self.last_player_id = None  # Track the last player ID to detect player changes
        self.figure_detail_box = None  # Detail box for selected figure
        self.figure_pending_pickup = None  # Figure waiting for pickup confirmation
        self.figure_pending_upgrade = None  # Figure waiting for upgrade confirmation

        self.init_field_compartments()

    def update(self, game):
        """Update the game state and load figures."""
        super().update(game)

        self.game = game
        self.load_figures()  # Load figures whenever the game state updates

        # Update hover state: only one figure can be hovered at a time
        # Check in reverse order (topmost figures get priority)
        hovered_icon = None
        for icon in reversed(self.figure_icons):
            if icon.collide() and hovered_icon is None:
                icon.hovered = True
                hovered_icon = icon
            else:
                icon.hovered = False

    def init_field_compartments(self):
        """Initialize compartments for the field screen.
        generates rectangle of size settings.FIELD_ICON_WIDTH and settings.FIELD_HEIGHT. Fill it with settings.FIELD_FILL_COLOR and make a border with settings.FIELD_BORDER_COLOR of width settings.FIELD_BORDER_WIDTH.
        Make 3 fields each for the swlf and opponent, starting at position settings.FIELD_SELF_X, settings.FIELD_OPPONENT_X and y position settings.FIELD_Y.
        Set transparency of the field to settings.FIELD_TRANSPARENCY.
        Margin in x direction is settings.FIELD_ICON_PADDING
        """
        compartments = {'self': {}, 'opponent': {}}

        compartments['self']['castle'] = pygame.Rect(settings.FIELD_SELF_X, settings.FIELD_Y, settings.FIELD_ICON_WIDTH, settings.FIELD_HEIGHT)
        compartments['self']['village'] = pygame.Rect(settings.FIELD_SELF_X + settings.FIELD_ICON_WIDTH + settings.FIELD_ICON_PADDING_X, settings.FIELD_Y, settings.FIELD_ICON_WIDTH, settings.FIELD_HEIGHT)
        compartments['self']['military'] = pygame.Rect(settings.FIELD_SELF_X + 2*(settings.FIELD_ICON_WIDTH + settings.FIELD_ICON_PADDING_X), settings.FIELD_Y, settings.FIELD_ICON_WIDTH, settings.FIELD_HEIGHT)

        compartments['opponent']['military'] = pygame.Rect(settings.FIELD_OPPONENT_X, settings.FIELD_Y, settings.FIELD_ICON_WIDTH, settings.FIELD_HEIGHT)
        compartments['opponent']['village'] = pygame.Rect(settings.FIELD_OPPONENT_X + settings.FIELD_ICON_WIDTH + settings.FIELD_ICON_PADDING_X, settings.FIELD_Y, settings.FIELD_ICON_WIDTH, settings.FIELD_HEIGHT)
        compartments['opponent']['castle'] = pygame.Rect(settings.FIELD_OPPONENT_X + 2*(settings.FIELD_ICON_WIDTH + settings.FIELD_ICON_PADDING_X), settings.FIELD_Y, settings.FIELD_ICON_WIDTH, settings.FIELD_HEIGHT)

        self.compartments = compartments

    def load_figures(self):
        """Retrieve all figures for the current player."""
        try:
            # Check if player has changed and clear cache if so
            if self.last_player_id != self.game.player_id:
                self.icon_cache.clear()
                self.last_figure_ids.clear()
                self.last_player_id = self.game.player_id
            
            # Load figures using the game's `get_figures` method
            families = self.figure_manager.families

            # Categorize figures into compartments
            categorized_figures = {
                'self': {'castle': [], 'village': [], 'military': []}, 
                'opponent': {'castle': [], 'village': [], 'military': []}
            }
            
            self_figures = self.game.get_figures(families)
            opponent_figures = self.game.get_figures(families, is_opponent=True)
            
            for figure in self_figures:
                if figure.family.field == 'castle':
                    categorized_figures['self']['castle'].append(figure)
                elif figure.family.field == 'village':
                    categorized_figures['self']['village'].append(figure)
                elif figure.family.field == 'military':
                    categorized_figures['self']['military'].append(figure)
            for figure in opponent_figures:
                if figure.family.field == 'castle':
                    categorized_figures['opponent']['castle'].append(figure)
                elif figure.family.field == 'village':
                    categorized_figures['opponent']['village'].append(figure)
                elif figure.family.field == 'military':
                    categorized_figures['opponent']['military'].append(figure)
                    
            self.figures = self_figures + opponent_figures
            self.categorized_figures = categorized_figures

            # Get current figure IDs
            current_figure_ids = {figure.id for figure in self.figures}

            # Only regenerate icons if figure IDs have changed
            if current_figure_ids != self.last_figure_ids:
                # check if the figure is opponent or not
                self._generate_figure_icons()
                self.last_figure_ids = current_figure_ids
        except Exception as e:
            print(f"Error loading figures: {e}")

    def _generate_figure_icons(self, is_visible=True):
        """Generate and cache icons for the current figures."""


        
        self.figure_icons = []

        for category, compartments in self.categorized_figures.items():
            for field_type, figures in compartments.items():
                for figure in figures:
                    # Determine visibility: own figures are visible, opponent figures are hidden except Maharajas
                    is_visible = category == 'self' or figure.name in ['Himalaya Maharaja', 'Djungle Maharaja']
                    if figure.id not in self.icon_cache:
                        self.icon_cache[figure.id] = FieldFigureIcon(
                            window=self.window,
                            game=self.game,
                            figure=figure,
                            is_visible=is_visible,
                        )
                    else:
                        # Update visibility for cached icon
                        self.icon_cache[figure.id].is_visible = is_visible
                    self.figure_icons.append(self.icon_cache[figure.id])

    def handle_events(self, events):
        """Handle events for interacting with the field."""
        super().handle_events(events)
        
        # Handle dialogue box events first (for pickup confirmation)
        if self.dialogue_box:
            response = self.dialogue_box.update(events)
            if response:
                if response == 'yes':
                    # Check which action is pending
                    if self.figure_pending_pickup:
                        # User confirmed pickup
                        try:
                            # Call server to pick up the figure
                            result = pickup_figure(
                                self.figure_pending_pickup.id,
                                self.game.player_id,
                                self.game.game_id
                            )
                            
                            if result.get('success'):
                                # Success message
                                card_count = result.get('main_card_count', 0) + result.get('side_card_count', 0)
                                print(f"Successfully picked up {self.figure_pending_pickup.name}. {card_count} cards returned to hand.")
                                
                                # Trigger a game update to refresh the state
                                # This will reload figures and cards from the server
                                self.state.set_msg(f"Picked up {self.figure_pending_pickup.name}. {card_count} cards returned to your hand.")
                                
                            else:
                                # Show error message
                                error_msg = result.get('message', 'Unknown error')
                                print(f"Failed to pick up figure: {error_msg}")
                                self.state.set_msg(f"Failed to pick up figure: {error_msg}")
                                
                        except Exception as e:
                            print(f"Error picking up figure: {str(e)}")
                            self.state.set_msg(f"Error picking up figure: {str(e)}")
                        
                        # Close the detail box and dialogue box
                        self.figure_detail_box = None
                        for icon in self.figure_icons:
                            icon.clicked = False
                        self.figure_pending_pickup = None
                    
                    elif self.figure_pending_upgrade:
                        # User confirmed upgrade
                        try:
                            # Find the upgrade card in the player's hand
                            main_hand, side_hand = self.game.get_hand()
                            hand_cards = main_hand + side_hand
                            
                            upgrade_card_template = self.figure_pending_upgrade.upgrade_card
                            upgrade_card = None
                            
                            # Find the actual card in hand that matches the upgrade_card template
                            for card in hand_cards:
                                if card.to_tuple() == upgrade_card_template.to_tuple():
                                    upgrade_card = card
                                    break
                            
                            if not upgrade_card:
                                raise Exception("Upgrade card not found in hand")
                            
                            # Determine card type
                            upgrade_card_type = 'main' if upgrade_card.is_main_card else 'side'
                            
                            # Call server to upgrade the figure
                            result = upgrade_figure(
                                self.figure_pending_upgrade.id,
                                self.game.player_id,
                                self.game.game_id,
                                upgrade_card.id,
                                upgrade_card_type
                            )
                            
                            if result.get('success'):
                                # Success message
                                print(f"Successfully upgraded {self.figure_pending_upgrade.name} to {self.figure_pending_upgrade.upgrade_family_name}.")
                                self.state.set_msg(f"Upgraded {self.figure_pending_upgrade.name} to {self.figure_pending_upgrade.upgrade_family_name}.")
                            else:
                                # Show error message
                                error_msg = result.get('message', 'Unknown error')
                                print(f"Failed to upgrade figure: {error_msg}")
                                self.state.set_msg(f"Failed to upgrade figure: {error_msg}")
                                
                        except Exception as e:
                            print(f"Error upgrading figure: {str(e)}")
                            self.state.set_msg(f"Error upgrading figure: {str(e)}")
                        
                        # Close the detail box and dialogue box
                        self.figure_detail_box = None
                        for icon in self.figure_icons:
                            icon.clicked = False
                        self.figure_pending_upgrade = None
                        
                elif response == 'no' or response == 'cancel':
                    # User cancelled action
                    self.figure_pending_pickup = None
                    self.figure_pending_upgrade = None
                    # Keep the detail box open
                
                # Close the dialogue box
                self.dialogue_box = None
            return  # Don't process other events when dialogue box is open
        
        # Handle figure detail box events first (if open)
        if self.figure_detail_box:
            response = self.figure_detail_box.handle_events(events)
            if response:
                if response == 'close':
                    self.figure_detail_box = None
                    # Deselect the figure
                    for icon in self.figure_icons:
                        icon.clicked = False
                elif response == 'charge':
                    # Handle charge action
                    print(f"Charge action for {self.figure_detail_box.figure.name}")
                elif response == 'upgrade':
                    # Handle upgrade action - show confirmation dialogue with upgrade card image
                    upgrade_card = self.figure_detail_box.figure.upgrade_card
                    if upgrade_card:
                        self.figure_pending_upgrade = self.figure_detail_box.figure
                        # Create card image for display in dialogue
                        from game.components.cards.card_img import CardImg
                        card_img = CardImg(self.window, upgrade_card.suit, upgrade_card.rank)
                        self.make_dialogue_box(
                            f"Are you sure you want to upgrade {self.figure_pending_upgrade.name} to {self.figure_pending_upgrade.upgrade_family_name}? This will cost you:",
                            actions=['yes', 'no'],
                            images=[card_img]
                        )
                elif response == 'pick up':
                    # Handle pick up action - show confirmation dialogue
                    self.figure_pending_pickup = self.figure_detail_box.figure
                    self.make_dialogue_box(
                        f"Are you sure you want to pick up {self.figure_pending_pickup.name}? This will remove the figure from the field and return it to your hand.",
                        actions=['yes', 'no']
                    )
            # If response is 'close', we already handled it above
            # For other actions, keep the box open unless user clicks close/outside
            return  # Don't process other events when detail box is open
        
        for event in events:
            if event.type == MOUSEBUTTONDOWN:
                # Only allow one figure to be selected at a time
                # Check in reverse order (topmost figure gets priority)
                clicked_icon = None
                for icon in reversed(self.figure_icons):
                    if icon.hovered:
                        clicked_icon = icon
                        break
                
                if clicked_icon:
                    # Deselect all other icons
                    for icon in self.figure_icons:
                        if icon != clicked_icon:
                            icon.clicked = False
                    # Toggle the clicked icon
                    was_clicked = clicked_icon.clicked
                    clicked_icon.clicked = not clicked_icon.clicked
                    
                    # Open detail box if figure was just selected and is visible
                    if clicked_icon.clicked and not was_clicked and clicked_icon.is_visible:
                        # Calculate resources once for efficiency
                        resources_data = self.game.calculate_resources(self.figure_manager.families)
                        
                        self.figure_detail_box = FigureDetailBox(
                            self.window,
                            clicked_icon.figure,
                            self.game,
                            all_figures=self.figures,  # Pass cached figures to avoid server call
                            resources_data=resources_data  # Pass pre-calculated resources
                        )
                    # Close detail box if figure was deselected
                    elif not clicked_icon.clicked:
                        self.figure_detail_box = None


    def handle_figure_click(self, figure):
        """Handle actions when a figure is clicked."""
        print(f"Selected figure: {figure.name}")
        # Add additional functionality for interacting with the figure

    def draw(self):
        """Draw the screen, including the field background and figure icons."""
        super().draw()

        if self.figures:
            for player in ['self', 'opponent']:
                for field in ['castle', 'village', 'military']:

                    compartment = self.compartments[player][field]
                    figures = self.categorized_figures[player][field]   

                    # Draw the field background

                    # Create a new surface with per-pixel alpha
                    compartment_surface = pygame.Surface((compartment.width, compartment.height), pygame.SRCALPHA)
                    
                    # Draw the filled rectangle with transparency
                    fill_color = (*settings.FIELD_FILL_COLOR[:3], settings.FIELD_TRANSPARENCY)
                    pygame.draw.rect(compartment_surface, fill_color, compartment_surface.get_rect())
                    
                    # Draw the border rectangle with transparency
                    border_color = (*settings.FIELD_BORDER_COLOR[:3], settings.FIELD_TRANSPARENCY)
                    pygame.draw.rect(compartment_surface, border_color, compartment_surface.get_rect(), settings.FIELD_BORDER_WIDTH)
                    
                    # Blit the new surface onto the main window
                    self.window.blit(compartment_surface, compartment.topleft)

                    if len(figures) > 0:
                        # Calculate the y-position to center the icons in the compartment
                        icon_height = settings.FIELD_ICON_WIDTH
                        available_height = compartment.height - 2 * settings.FIELD_BORDER_WIDTH
                        
                        # Calculate dynamic spacing to fit all figures within available height
                        if len(figures) == 1:
                            icon_spacing = 0
                            total_icons_height = icon_height
                        else:
                            # Calculate total height with default spacing
                            default_total_height = len(figures) * icon_height + (len(figures) - 1) * settings.FIELD_ICON_PADDING_Y
                            
                            # If it fits, use default spacing; otherwise, reduce spacing to fit
                            if default_total_height <= available_height:
                                icon_spacing = settings.FIELD_ICON_PADDING_Y
                                total_icons_height = default_total_height
                            else:
                                # Calculate reduced spacing to fit within available height
                                # Formula: total_height = N * icon_height + (N-1) * spacing
                                # Solving for spacing: spacing = (available_height - N * icon_height) / (N - 1)
                                icon_spacing = (available_height - len(figures) * icon_height) / (len(figures) - 1)
                                total_icons_height = available_height
                        
                        icon_y_start = compartment.top + (compartment.height - total_icons_height) // 2 + 0.5*settings.FIELD_ICON_WIDTH

                        # Calculate positions and separate into layers: regular, selected, hovered
                        regular_positions = []
                        selected_positions = []
                        hovered_item = None
                        
                        for i, figure in enumerate(figures):
                            icon = self.icon_cache[figure.id]
                            icon_x = compartment.left + 0.5*settings.FIELD_ICON_WIDTH 
                            icon_y = icon_y_start + i * (icon_height + icon_spacing)
                            
                            if icon.hovered:
                                hovered_item = (icon, icon_x, icon_y)
                            elif icon.clicked:
                                selected_positions.append((icon, icon_x, icon_y))
                            else:
                                regular_positions.append((icon, icon_x, icon_y))
                        
                        # Draw in layers: regular -> selected -> hovered
                        # Each layer in reverse order (topmost figures in foreground)
                        for icon, icon_x, icon_y in reversed(regular_positions):
                            icon.draw(icon_x, icon_y)
                        
                        for icon, icon_x, icon_y in reversed(selected_positions):
                            icon.draw(icon_x, icon_y)
                        
                        # Draw hovered icon last (on top of everything)
                        if hovered_item:
                            icon, icon_x, icon_y = hovered_item
                            icon.draw(icon_x, icon_y)

        # Note: Figure detail box is drawn in game_screen.py to ensure it's on top of hand cards

