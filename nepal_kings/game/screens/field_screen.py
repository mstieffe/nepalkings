import pygame
from pygame.locals import *
from config import settings
from game.screens.sub_screen import SubScreen
from game.components.figures.figure_manager import FigureManager
from game.components.figures.figure_icon import FieldFigureIcon


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

        self.init_field_compartments()

    def update(self, game):
        """Update the game state and load figures."""
        super().update(game)

        self.game = game
        self.load_figures()  # Load figures whenever the game state updates

        for icon in self.figure_icons:
            icon.update()

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
            is_visible = category == 'self'  # Visible for self, not for opponent
            for field_type, figures in compartments.items():
                for figure in figures:
                    if figure.name == ' Himalaya Maharaja' or figure.name == 'Djungle Maharaja':
                        is_visible = True
                    if figure.id not in self.icon_cache:
                        self.icon_cache[figure.id] = FieldFigureIcon(
                            window=self.window,
                            game=self.game,
                            figure=figure,
                            is_visible=is_visible,
                        )
                    self.figure_icons.append(self.icon_cache[figure.id])

    def handle_events(self, events):
        """Handle events for interacting with the field."""
        super().handle_events(events)
        for event in events:
            if event.type == MOUSEBUTTONDOWN:
                for icon in self.figure_icons:
                    icon.handle_events(events)
                    #if icon.rect.collidepoint(event.pos):
                    #    print(f"Clicked on figure: {icon.figure.name}")
                    #    self.handle_figure_click(icon.figure)


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

                    # Calculate the y-position to center the icons in the compartment
                    icon_height = settings.FIELD_ICON_WIDTH
                    total_icons_height = len(figures) * icon_height + (len(figures) - 1) * settings.FIELD_ICON_PADDING_Y
                    icon_y_start = compartment.top + (compartment.height - total_icons_height) // 2 + 0.5*settings.FIELD_ICON_WIDTH

                    # Draw the figure icons
                    for i, figure in enumerate(figures):
                        print(i, figure)
                        icon = self.icon_cache[figure.id]
                        icon_x = compartment.left + 0.5*settings.FIELD_ICON_WIDTH 
                        icon_y = icon_y_start + i * (icon_height + settings.FIELD_ICON_PADDING_Y)
                        #icon.set_position(icon_x, icon_y)
                        icon.draw(icon_x, icon_y)



        

