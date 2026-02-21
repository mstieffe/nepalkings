import pygame
from pygame.locals import *
from config import settings
from game.screens.sub_screen import SubScreen


class TutorialScreen(SubScreen):
    """Screen for displaying game tutorials and help information."""

    def __init__(self, window, state, x: int = 0.0, y: int = 0.0, title=None):
        super().__init__(window, state.game, x, y, title)
        self.state = state
        self.game = state.game

        # Tutorial content sections
        self.sections = self._build_sections()
        self.current_section = 0
        self.scroll_offset = 0

        # Fonts
        self.title_section_font = pygame.font.Font(settings.FONT_PATH, settings.SUB_SCREEN_TITLE_FONT_SIZE)
        self.title_section_font.set_bold(True)
        self.body_font = pygame.font.Font(settings.FONT_PATH, settings.MSG_FONT_SIZE)
        self.nav_font = pygame.font.Font(settings.FONT_PATH, settings.MSG_FONT_SIZE)

        # Layout constants (relative to sub screen area)
        self.content_x = settings.SUB_SCREEN_X + int(0.03 * settings.SCREEN_WIDTH)
        self.content_y = settings.SUB_SCREEN_Y + int(0.08 * settings.SCREEN_HEIGHT)
        self.content_width = int(0.28 * settings.SCREEN_WIDTH)
        self.content_height = int(0.72 * settings.SCREEN_HEIGHT)
        self.line_spacing = int(0.003 * settings.SCREEN_HEIGHT)

        # Navigation buttons
        self.init_nav_buttons()

        # Scrollbar
        self.scrollbar_width = int(0.008 * settings.SCREEN_WIDTH)
        self.scrollbar_x = self.content_x + self.content_width + int(0.005 * settings.SCREEN_WIDTH)
        self.scrollbar_y = self.content_y
        self.scrollbar_height = self.content_height
        self.dragging = False

    def _build_sections(self):
        """Build the tutorial content sections."""
        return [
            {
                'title': 'Overview',
                'lines': [
                    'Welcome to Nepal Kings!',
                    '',
                    'Nepal Kings is a strategic card game',
                    'where two players compete to build',
                    'the most powerful kingdom.',
                    '',
                    'Each round, you draw cards, build',
                    'figures, cast spells, and battle',
                    'your opponent.',
                    '',
                    'The game ends when one player',
                    'conquers the other\'s kingdom or',
                    'the deck runs out.',
                ]
            },
            {
                'title': 'Cards & Hands',
                'lines': [
                    'You have two hands:',
                    '',
                    '- Main Hand: Your primary cards',
                    '- Side Hand: Extra cards you\'ve',
                    '  acquired through spells or trades',
                    '',
                    'Cards have suits (Clubs, Diamonds,',
                    'Hearts, Spades) and values (2-14).',
                    '',
                    'Cards are used to build figures',
                    'and cast spells.',
                    '',
                    'Your hand auto-refills at the start',
                    'of each turn.',
                ]
            },
            {
                'title': 'Figures',
                'lines': [
                    'Figures are units you place on the',
                    'playing board. They have:',
                    '',
                    '- Attack: Damage dealt in battle',
                    '- Defense: Damage absorbed',
                    '- A suit requirement to build',
                    '',
                    'Figure types:',
                    '',
                    'Castle: Your home base. If it',
                    '  falls, you lose!',
                    'Village: Produces resources and',
                    '  supports your army.',
                    'Military: Soldiers that fight',
                    '  in battles.',
                ]
            },
            {
                'title': 'Spells',
                'lines': [
                    'Spells are special actions that',
                    'require specific card combinations.',
                    '',
                    'Spell families:',
                    '',
                    '- Trade: Exchange cards',
                    '- Tactics: Modify battles',
                    '- Enchantment: Buff your figures',
                    '- Sabotage: Harm your opponent',
                    '',
                    'When a spell is cast, your opponent',
                    'can try to counter it if they have',
                    'the right cards.',
                ]
            },
            {
                'title': 'Battle',
                'lines': [
                    'Battles occur at the end of each',
                    'round, after both players have',
                    'used their turns.',
                    '',
                    'Your military figures attack the',
                    'opponent\'s figures. The outcome',
                    'depends on attack vs defense values.',
                    '',
                    'Battle modifiers (Civil War,',
                    'Peasant War, Blitzkrieg) can',
                    'change the rules of engagement.',
                    '',
                    'Win by destroying your opponent\'s',
                    'castle!',
                ]
            },
        ]

    def init_nav_buttons(self):
        """Initialize navigation buttons for sections."""
        button_y = settings.SUB_SCREEN_Y + int(0.82 * settings.SCREEN_HEIGHT)
        button_x_prev = settings.SUB_SCREEN_X + int(0.05 * settings.SCREEN_WIDTH)
        button_x_next = settings.SUB_SCREEN_X + int(0.21 * settings.SCREEN_WIDTH)

        self.prev_button = self.make_button("< Prev", button_x_prev, button_y)
        self.next_button = self.make_button("Next >", button_x_next, button_y)
        self.buttons.extend([self.prev_button, self.next_button])

    def update(self, game):
        """Update the game state."""
        super().update(game)
        self.game = game

    def handle_events(self, events):
        """Handle events for navigation and scrolling."""
        super().handle_events(events)
        for event in events:
            if event.type == MOUSEBUTTONDOWN:
                if event.button == 1:
                    if self.prev_button.rect.collidepoint(event.pos):
                        if self.current_section > 0:
                            self.current_section -= 1
                            self.scroll_offset = 0
                    elif self.next_button.rect.collidepoint(event.pos):
                        if self.current_section < len(self.sections) - 1:
                            self.current_section += 1
                            self.scroll_offset = 0
                elif event.button == 4:  # Scroll up
                    self.scroll_offset = max(0, self.scroll_offset - 1)
                elif event.button == 5:  # Scroll down
                    self.scroll_offset += 1

    def draw(self):
        """Draw the tutorial screen."""
        super().draw()

        section = self.sections[self.current_section]

        # Draw section title
        title_surface = self.title_section_font.render(section['title'], True, (250, 221, 0))
        title_rect = title_surface.get_rect(midtop=(self.content_x + self.content_width // 2, self.content_y - int(0.04 * settings.SCREEN_HEIGHT)))
        self.window.blit(title_surface, title_rect)

        # Draw section indicator
        indicator = f"{self.current_section + 1} / {len(self.sections)}"
        indicator_surface = self.nav_font.render(indicator, True, (200, 200, 200))
        indicator_rect = indicator_surface.get_rect(midtop=(self.content_x + self.content_width // 2, title_rect.bottom + int(0.005 * settings.SCREEN_HEIGHT)))
        self.window.blit(indicator_surface, indicator_rect)

        # Draw content lines with scroll
        y = self.content_y
        max_y = self.content_y + self.content_height
        visible_lines = section['lines'][self.scroll_offset:]

        for line in visible_lines:
            if y + self.body_font.get_height() > max_y:
                break
            if line == '':
                y += self.body_font.get_height() // 2
                continue
            text_surface = self.body_font.render(line, True, (230, 230, 230))
            self.window.blit(text_surface, (self.content_x, y))
            y += self.body_font.get_height() + self.line_spacing

        # Update button states
        self.prev_button.active = self.current_section > 0
        self.next_button.active = self.current_section < len(self.sections) - 1
