import pygame

from config import settings


class ScoreboardScroll:
    def __init__(
            self, 
            window: pygame.Surface, 
            x: int, 
            y: int, 
            width: int, 
            height: int, 
            text_dict: dict, 
            bg_img_path: str):
        self.window = window
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.text_dict = text_dict
        self.bg_img_path = bg_img_path

        self.font_col_names = pygame.font.Font(settings.FONT_PATH, settings.SCOREBOARD_SCROLL_FONT_SIZE)
        self.font_col_names.set_italic(True)
        self.font_text = pygame.font.Font(settings.FONT_PATH, settings.SCOREBOARD_SCROLL_FONT_SIZE)

        # Load black and golden rectangle glow images
        self.rect_glow_black = pygame.image.load(settings.GLOW_RECT_IMG_PATH + 'black.png').convert_alpha()
        self.rect_glow_black = pygame.transform.smoothscale(self.rect_glow_black, (width * 1.2, height * 1.2))
        self.rect_glow_yellow = pygame.image.load(settings.GLOW_RECT_IMG_PATH + 'yellow.png').convert_alpha()
        self.rect_glow_yellow = pygame.transform.smoothscale(self.rect_glow_yellow, (width * 1.2, height * 1.2))

        self.rect = pygame.Rect(self.x, self.y, self.width, self.height)

        self.init_background()

    def init_background(self):
        """Initialize the background image."""
        self.background = pygame.image.load(self.bg_img_path)
        self.background = pygame.transform.smoothscale(self.background, (self.width, self.height))

    def draw_msg(self):
        """Render the keys and values to the screen."""
        starting_y_position = self.y + settings.SCOREBOARD_SCROLL_Y_TEXT_MARGIN

        for key, value in self.text_dict.items():
            # Render the key
            key_text = self.font_col_names.render(str(key), True, settings.SCOREBOARD_SCROLL_TEXT_COLOR)
            key_rect = key_text.get_rect()
            key_rect.topleft = (self.x + settings.SCOREBOARD_SCROLL_X_TEXT_MARGIN, starting_y_position)

            # Render the value
            value_text = self.font_text.render(str(value), True, settings.SCOREBOARD_SCROLL_TEXT_COLOR)
            value_rect = value_text.get_rect()
            value_rect.topleft = (key_rect.right + settings.SCOREBOARD_SCROLL_SPACER, starting_y_position)

            # Draw both on the same line
            self.window.blit(key_text, key_rect)
            self.window.blit(value_text, value_rect)

            starting_y_position += settings.SCOREBOARD_SCROLL_LINE_SPACING

    def draw(self):
        """Draw the background and message to the screen."""
        # Glow effect based on mouse hover
        if self.collide():
            self.window.blit(self.rect_glow_yellow, (self.x - 0.1 * self.width, self.y - 0.1 * self.height))
        else:
            self.window.blit(self.rect_glow_black, (self.x - 0.1 * self.width, self.y - 0.1 * self.height))

        # Draw the background and the formatted message
        self.window.blit(self.background, (self.x, self.y))
        self.draw_msg()

    def collide(self):
        """Check if the mouse is over the scroll."""
        return self.rect.collidepoint(pygame.mouse.get_pos())
