import pygame
from config import settings
from config.screen_settings import _UI_SCALE


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
        self.text_dict = self.make_text_dict()
        self.bg_img_path = bg_img_path

        # Whether to use the dark-panel mobile design
        self._use_panel = getattr(settings, 'SCOREBOARD_USE_PANEL', False)

        # Choose text/cross colours based on mode
        if self._use_panel:
            self._text_color = settings.SCOREBOARD_PANEL_TEXT_COLOR
            self._value_color = settings.SCOREBOARD_PANEL_VALUE_COLOR
            self._cross_color = settings.SCOREBOARD_PANEL_CROSS_COLOR
            self._cross_alpha = settings.SCOREBOARD_PANEL_CROSS_ALPHA
        else:
            self._text_color = settings.SCOREBOARD_SCROLL_TEXT_COLOR
            self._value_color = settings.SCOREBOARD_SCROLL_TEXT_COLOR
            self._cross_color = settings.SCOREBOARD_CROSS_COLOR
            self._cross_alpha = settings.SCOREBOARD_CROSS_ALPHA

        self.font_col_names = pygame.font.Font(settings.FONT_PATH, settings.SCOREBOARD_SCROLL_FONT_TITLE_SIZE)
        self.font_text = pygame.font.Font(settings.FONT_PATH, settings.SCOREBOARD_SCROLL_FONT_SIZE)
        self.font_number = pygame.font.Font(settings.FONT_PATH, settings.SCOREBOARD_SCROLL_NUMBER_FONT_SIZE)
        self.font_number.set_bold(True)
        self.font_subtitle = pygame.font.Font(settings.FONT_PATH, settings.SCOREBOARD_SUBTITLE_FONT_SIZE)

        # Load black and golden rectangle glow images (scale directly to target size)
        glow_w, glow_h = int(width * 1.2), int(height * 1.2)
        raw_black = pygame.image.load(settings.GLOW_RECT_IMG_PATH + 'black.png').convert_alpha()
        self.rect_glow_black = pygame.transform.smoothscale(raw_black, (glow_w, glow_h))
        del raw_black
        raw_yellow = pygame.image.load(settings.GLOW_RECT_IMG_PATH + 'yellow.png').convert_alpha()
        self.rect_glow_yellow = pygame.transform.smoothscale(raw_yellow, (glow_w, glow_h))
        del raw_yellow

        self.rect = pygame.Rect(self.x, self.y, self.width, self.height)

        # Calculate cell dimensions for the scoreboard
        self.cell_width = self.width // 2
        self.cell_height = self.height // 2

        # Adjust height for "stake" section
        self.stake_section_height = settings.SCOREBOARD_LIMIT_SECTION_HEIGHT
        self.cross_height = self.height - self.stake_section_height

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
                'stake': getattr(self.game, 'stake', 45),  # Fallback to 45 if 'stake' isn't defined
            }
        else:
            scoreboard_dict = {
                'opponent': 'Opponent',
                'date': '2021-01-01',
                'turns_left': 0,
                'round': 0,
                'your_score': 0,
                'opponent_score': 0,
                'stake': 45,
            }
        return scoreboard_dict


    def update(self, game):
        """Update the game state."""
        self.game = game
        self.text_dict = self.make_text_dict()

    def init_background(self):
        """Initialize the background image or build a dark panel for mobile."""
        if self._use_panel:
            r = settings.SCOREBOARD_PANEL_CORNER_R
            self.background = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            pygame.draw.rect(self.background, settings.SCOREBOARD_PANEL_BG_CLR,
                             (0, 0, self.width, self.height), border_radius=r)
            pygame.draw.rect(self.background, settings.SCOREBOARD_PANEL_BORDER_CLR,
                             (0, 0, self.width, self.height),
                             width=settings.SCOREBOARD_PANEL_BORDER_WIDTH, border_radius=r)
        else:
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

        self.draw_transparent_line(horizontal_line_start, horizontal_line_end, self._cross_color, settings.SCOREBOARD_CROSS_WIDTH, self._cross_alpha)
        self.draw_transparent_line(vertical_line_start, vertical_line_end, self._cross_color, settings.SCOREBOARD_CROSS_WIDTH, self._cross_alpha)

    def draw_cell(self, text, value, cell_x, cell_y, value_color=None,
                  subtitle=None, subtitle_color=None, y_offset=0, text_spacing=None):
        """Draw the text and value in the specified cell.

        :param subtitle: optional smaller text drawn below the main label (e.g. "(battle)").
        :param y_offset: extra pixels to push the value centre downward (used for top-row cells).
        :param text_spacing: gap between title bottom and value top.  Defaults to SCOREBOARD_CELL_TEXT_SPACING.
        """
        if value_color is None:
            value_color = self._value_color
        if text_spacing is None:
            text_spacing = settings.SCOREBOARD_CELL_TEXT_SPACING

        # Render the text and value
        text_obj = self.font_text.render(text, True, self._text_color)
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

    def draw_stake(self):
        """Draw the stake value at the bottom of the scoreboard."""
        stake_text = self.text_dict.get("stake", "")
        stake_obj = self.font_col_names.render(f"{stake_text}", True, self._text_color)

        # Position at the bottom center of the scoreboard
        stake_rect = stake_obj.get_rect(center=(self.x + self.width // 2, self.y + self.height - self.stake_section_height // 2))
        self.window.blit(stake_obj, stake_rect)

    def draw_msg(self):
        """Render the scoreboard content."""
        # Top-row cells share offset + subtitle spacing so labels & values stay aligned
        top_offset = settings.SCOREBOARD_CELL_VALUE_OFFSET
        top_spacing = settings.SCOREBOARD_CELL_SUBTITLE_SPACING

        # During an active battle, show battle turns with a "(battle)" subtitle
        # Use both client-side flag and server-side indicators as fallback (web compatibility)
        in_battle = False
        if self.game:
            in_battle = (getattr(self.game, 'in_battle_phase', False) or
                         (getattr(self.game, 'battle_confirmed', False) and
                          getattr(self.game, 'battle_turn_player_id', None) is not None))
        # On mobile, skip the subtitle to save space
        _mobile = _UI_SCALE > 1.0
        if in_battle:
            battle_turns = getattr(self.game, 'battle_turns_left', 0)
            self.draw_cell("Turns Left", battle_turns, self.x, self.y,
                           subtitle=None if _mobile else "(battle)",
                           subtitle_color=(220, 60, 60),
                           y_offset=top_offset, text_spacing=top_spacing)
        else:
            self.draw_cell("Turns Left", self.text_dict.get("turns_left", ""), self.x, self.y,
                           subtitle=None if _mobile else "(build-up)",
                           subtitle_color=(90, 115, 150),
                           y_offset=top_offset, text_spacing=top_spacing)
        self.draw_cell("Round", self.text_dict.get("round", ""), self.x + self.cell_width, self.y,
                       y_offset=top_offset, text_spacing=top_spacing)
        # On mobile, nudge bottom-row values down a little so they sit inside the box
        _bot_offset = int(0.008 * settings.SCREEN_HEIGHT) if _UI_SCALE > 1.0 else 0
        self.draw_cell("You", self.text_dict.get("your_score", ""), self.x, self.y + self.cell_height, settings.COLOR_GREEN,
                       y_offset=_bot_offset)
        self.draw_cell("Opponent", self.text_dict.get("opponent_score", ""), self.x + self.cell_width, self.y + self.cell_height, settings.COLOR_RED,
                       y_offset=_bot_offset)

        # Draw the stake value
        self.draw_stake()

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
