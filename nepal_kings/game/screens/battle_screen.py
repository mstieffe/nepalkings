import pygame
from pygame.locals import *
from config import settings
from game.screens.sub_screen import SubScreen


class BattleScreen(SubScreen):
    """Screen for displaying the battle phase.
    
    This screen is only accessible once the battle phase of the round starts.
    During the regular round it remains inactive.
    """

    def __init__(self, window, state, x: int = 0.0, y: int = 0.0, title=None):
        super().__init__(window, state.game, x, y, title)
        self.state = state
        self.game = state.game

        # Fonts
        self.header_font = pygame.font.Font(settings.FONT_PATH, settings.SUB_SCREEN_TITLE_FONT_SIZE)
        self.header_font.set_bold(True)
        self.body_font = pygame.font.Font(settings.FONT_PATH, settings.MSG_FONT_SIZE)
        self.info_font = pygame.font.Font(settings.FONT_PATH, settings.MSG_FONT_SIZE)

        # Layout
        self.content_x = settings.SUB_SCREEN_X + int(0.03 * settings.SCREEN_WIDTH)
        self.content_y = settings.SUB_SCREEN_Y + int(0.08 * settings.SCREEN_HEIGHT)
        self.content_width = int(0.28 * settings.SCREEN_WIDTH)

    def update(self, game):
        """Update the game state."""
        super().update(game)
        self.game = game

    def handle_events(self, events):
        """Handle events for the battle screen."""
        super().handle_events(events)
        for event in events:
            if event.type == MOUSEBUTTONDOWN:
                pass

    def draw(self):
        """Draw the battle screen."""
        super().draw()

        # Placeholder content - to be expanded when battle phase is implemented
        y = self.content_y

        header_surface = self.header_font.render("Battle Phase", True, (250, 221, 0))
        header_rect = header_surface.get_rect(midtop=(self.content_x + self.content_width // 2, y))
        self.window.blit(header_surface, header_rect)
        y = header_rect.bottom + int(0.03 * settings.SCREEN_HEIGHT)

        info_lines = [
            "The battle phase begins after",
            "both players have completed",
            "their turns for this round.",
            "",
            "Your military figures will",
            "engage the opponent's forces.",
            "",
            "Battle details will appear here",
            "once the phase is active.",
        ]

        for line in info_lines:
            if line == '':
                y += self.body_font.get_height() // 2
                continue
            text_surface = self.body_font.render(line, True, (200, 200, 200))
            self.window.blit(text_surface, (self.content_x, y))
            y += self.body_font.get_height() + int(0.003 * settings.SCREEN_HEIGHT)
