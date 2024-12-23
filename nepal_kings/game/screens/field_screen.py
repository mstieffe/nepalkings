import pygame
from pygame.locals import *
from config import settings
from game.screens.sub_screen import SubScreen
from game.components.figures.figure_manager import FigureManager

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

    def update(self, game):
        """Update the game state and load figures."""
        super().update(game)

        self.game = game
        self.load_figures()  # Load figures whenever the game state updates

    def load_figures(self):
        """Retrieve all figures for the current player."""
        try:
            # Load figures using the game's `get_figures` method
            families = self.figure_manager.families
            self.figures = self.game.get_figures(families)

            #if not self.figures:
            #    print("No figures found for the player.")

            # Get current figure IDs
            current_figure_ids = {figure.id for figure in self.figures}

            # Only regenerate icons if figure IDs have changed
            if current_figure_ids != self.last_figure_ids:
                self._generate_figure_icons()
                self.last_figure_ids = current_figure_ids
        except Exception as e:
            print(f"Error loading figures: {e}")

    def _generate_figure_icons(self):
        """Generate and cache icons for the current figures."""
        self.figure_icons = []
        for i, figure in enumerate(self.figures):
            # Use figure.id as the cache key
            if figure.id not in self.icon_cache:
                # Create a new icon and cache it
                self.icon_cache[figure.id] = figure.family.make_icon(
                    window=self.window,
                    game=self.game,
                    x=settings.FIELD_ICON_START_X + i * (settings.FIELD_ICON_WIDTH + settings.FIELD_ICON_PADDING_X),
                    y=settings.FIELD_ICON_START_Y,
                )
            self.figure_icons.append(self.icon_cache[figure.id])

    def handle_events(self, events):
        """Handle events for interacting with the field."""
        super().handle_events(events)
        for event in events:
            if event.type == MOUSEBUTTONDOWN:
                for icon in self.figure_icons:
                    pass
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

        # Draw each figure icon
        for icon in self.figure_icons:
            icon.draw()
