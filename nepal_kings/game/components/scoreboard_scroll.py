import pygame
from config import settings


class ScoreboardScroll:
    def __init__(
            self,
            window: pygame.Surface,
            game,
            x: int,
            y: int,
            width: int,
            height: int,
            bg_img_path: str):
        self.window = window
        self.game = game
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        #self.text_dict = text_dict
        self.text_dict = self.make_text_dict()
        self.bg_img_path = bg_img_path

        self.font_col_names = pygame.font.Font(settings.FONT_PATH, settings.SCOREBOARD_SCROLL_FONT_TITLE_SIZE)
        self.font_text = pygame.font.Font(settings.FONT_PATH, settings.SCOREBOARD_SCROLL_FONT_SIZE)
        self.font_number = pygame.font.Font(settings.FONT_PATH, settings.SCOREBOARD_SCROLL_NUMBER_FONT_SIZE)
        self.font_number.set_bold(True)
        self.font_subtitle = pygame.font.Font(settings.FONT_PATH, settings.SCOREBOARD_SUBTITLE_FONT_SIZE)

        # Load black and golden rectangle glow images
        self.rect_glow_black = pygame.image.load(settings.GLOW_RECT_IMG_PATH + 'black.png').convert_alpha()
        self.rect_glow_black = pygame.transform.smoothscale(self.rect_glow_black, (width * 1.2, height * 1.2))
        self.rect_glow_yellow = pygame.image.load(settings.GLOW_RECT_IMG_PATH + 'yellow.png').convert_alpha()
        self.rect_glow_yellow = pygame.transform.smoothscale(self.rect_glow_yellow, (width * 1.2, height * 1.2))

        self.rect = pygame.Rect(self.x, self.y, self.width, self.height)

        # Calculate cell dimensions for the scoreboard
        self.cell_width = self.width // 2
        self.cell_height = self.height // 2

        # Adjust height for "limit" section
        self.limit_section_height = settings.SCOREBOARD_LIMIT_SECTION_HEIGHT
        self.cross_height = self.height - self.limit_section_height

        self.init_background()

    def make_text_dict(self):
        """Create a dictionary of text values to display on the scoreboard."""
        if self.game:
            scoreboard_dict = {
                'opponent': self.game.opponent_name,
                'date': self.game.date,
                'turns_left': self.game.current_player.get('turns_left', 0),
                'round': self.game.current_round,  # Assuming `self.game.round` exists
                'your_score': self.game.current_player.get('points', 0),
                'opponent_score': self.game.opponent_player.get('points', 0),
                'limit': getattr(self.game, 'limit', 45),  # Fallback to 45 if 'limit' isn't defined
            }
        else:
            scoreboard_dict = {
                'opponent': 'Opponent',
                'date': '2021-01-01',
                'turns_left': 0,
                'round': 0,
                'your_score': 0,
                'opponent_score': 0,
                'limit': 45,
            }
        return scoreboard_dict


    def update(self, game):
        """Update the game state."""
        self.game = game
        self.text_dict = self.make_text_dict()

    def init_background(self):
        """Initialize the background image."""
        self.background = pygame.image.load(self.bg_img_path)
        self.background = pygame.transform.smoothscale(self.background, (self.width, self.height))

    def draw_transparent_line(self, start, end, color, width, alpha):
        """Draw a transparent line."""
        surface = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        pygame.draw.line(surface, (*color, alpha), start, end, width)
        self.window.blit(surface, (self.x, self.y))

    def draw_cross(self):
        """Draw the cross centered on top of the scroll background."""
        # Horizontal line
        horizontal_line_start = (0, self.height // 2)
        horizontal_line_end = (self.width, self.height // 2)
        # Vertical line
        vertical_line_start = (self.width // 2, 0)
        vertical_line_end = (self.width // 2, self.cross_height)

        self.draw_transparent_line(horizontal_line_start, horizontal_line_end, settings.SCOREBOARD_CROSS_COLOR, settings.SCOREBOARD_CROSS_WIDTH, settings.SCOREBOARD_CROSS_ALPHA)
        self.draw_transparent_line(vertical_line_start, vertical_line_end, settings.SCOREBOARD_CROSS_COLOR, settings.SCOREBOARD_CROSS_WIDTH, settings.SCOREBOARD_CROSS_ALPHA)

    def draw_cell(self, text, value, cell_x, cell_y, value_color=settings.SCOREBOARD_SCROLL_TEXT_COLOR,
                  subtitle=None, subtitle_color=None, y_offset=0, text_spacing=None):
        """Draw the text and value in the specified cell.

        :param subtitle: optional smaller text drawn below the main label (e.g. "(battle)").
        :param y_offset: extra pixels to push the value centre downward (used for top-row cells).
        :param text_spacing: gap between title bottom and value top.  Defaults to SCOREBOARD_CELL_TEXT_SPACING.
        """
        if text_spacing is None:
            text_spacing = settings.SCOREBOARD_CELL_TEXT_SPACING

        # Render the text and value
        text_obj = self.font_text.render(text, True, settings.SCOREBOARD_SCROLL_TEXT_COLOR)
        value_obj = self.font_number.render(str(value), True, value_color)

        # Centre text horizontally
        text_rect = text_obj.get_rect(centerx=cell_x + self.cell_width // 2)
        # Centre the value horizontally; push down from cell centre by y_offset
        value_rect = value_obj.get_rect(center=(cell_x + self.cell_width // 2,
                                                cell_y + self.cell_height // 2 + y_offset))

        # Position the title above the value with the given spacing (consistent for every cell in the row)
        text_rect.y = value_rect.y - text_spacing - text_rect.height

        # Draw subtitle between title and value if present (no title shift — keeps alignment)
        if subtitle:
            sub_obj = self.font_subtitle.render(subtitle, True, subtitle_color or (220, 60, 60))
            sub_rect = sub_obj.get_rect(centerx=cell_x + self.cell_width // 2)
            sub_rect.y = text_rect.bottom + 1
            self.window.blit(sub_obj, sub_rect)

        self.window.blit(text_obj, text_rect)
        self.window.blit(value_obj, value_rect)

    def draw_limit(self):
        """Draw the limit value at the bottom of the scoreboard."""
        limit_text = self.text_dict.get("limit", "")
        limit_obj = self.font_col_names.render(f"{limit_text}", True, settings.SCOREBOARD_SCROLL_TEXT_COLOR)

        # Position at the bottom center of the scoreboard
        limit_rect = limit_obj.get_rect(center=(self.x + self.width // 2, self.y + self.height - self.limit_section_height // 2))
        self.window.blit(limit_obj, limit_rect)

    def draw_msg(self):
        """Render the scoreboard content."""
        # Top-row cells share offset + subtitle spacing so labels & values stay aligned
        top_offset = settings.SCOREBOARD_CELL_VALUE_OFFSET
        top_spacing = settings.SCOREBOARD_CELL_SUBTITLE_SPACING

        # During an active battle, show battle turns with a "(battle)" subtitle
        in_battle = getattr(self.game, 'in_battle_phase', False) if self.game else False
        if in_battle:
            battle_turns = getattr(self.game, 'battle_turns_left', 0)
            self.draw_cell("Turns Left", battle_turns, self.x, self.y,
                           subtitle="(battle)", subtitle_color=(220, 60, 60),
                           y_offset=top_offset, text_spacing=top_spacing)
        else:
            self.draw_cell("Turns Left", self.text_dict.get("turns_left", ""), self.x, self.y,
                           subtitle="(build-up)", subtitle_color=(90, 115, 150),
                           y_offset=top_offset, text_spacing=top_spacing)
        self.draw_cell("Round", self.text_dict.get("round", ""), self.x + self.cell_width, self.y,
                       y_offset=top_offset, text_spacing=top_spacing)
        self.draw_cell("You", self.text_dict.get("your_score", ""), self.x, self.y + self.cell_height, settings.COLOR_GREEN)
        self.draw_cell("Opponent", self.text_dict.get("opponent_score", ""), self.x + self.cell_width, self.y + self.cell_height, settings.COLOR_RED)

        # Draw the limit value
        self.draw_limit()

    def draw(self):
        """Draw the background, cross, and message to the screen."""
        # Glow effect based on mouse hover
        if self.collide():
            self.window.blit(self.rect_glow_yellow, (self.x - 0.1 * self.width, self.y - 0.1 * self.height))
        else:
            self.window.blit(self.rect_glow_black, (self.x - 0.1 * self.width, self.y - 0.1 * self.height))

        # Draw the background
        self.window.blit(self.background, (self.x, self.y))

        # Draw the cross and scoreboard
        self.draw_cross()
        self.draw_msg()

    def collide(self):
        """Check if the mouse is over the scroll."""
        return self.rect.collidepoint(pygame.mouse.get_pos())
