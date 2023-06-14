import settings
import pygame

class Button():

    def __init__(self, window, x: int = 0, y: int =0, text: str = ""):
        self.window = window
        self.x = x
        self.y = y
        self.text= text
        self.color_rect = settings.BUTTON_COLOR_PASSIVE
        self.color_text = settings.TEXT_COLOR_PASSIVE
        self.font = pygame.font.Font(settings.FONT_PATH, settings.FONT_SIZE)
        self.rect = pygame.Rect(self.x, self.y, settings.BUTTON_WIDTH, settings.BUTTON_HEIGHT)

    def collide(self):
        mx, my = pygame.mouse.get_pos()
        return self.rect.collidepoint((mx, my))

    def draw(self):
        pygame.draw.rect(self.window, self.color_rect, self.rect)
        text_obj = self.font.render(self.text, True, self.color_text)
        text_rect = text_obj.get_rect(center=(self.x + settings.BUTTON_WIDTH / 2, self.y + settings.BUTTON_HEIGHT / 2))
        self.window.blit(text_obj, text_rect)

    def update_color(self):
        mx, my = pygame.mouse.get_pos()
        if self.rect.collidepoint((mx, my)):
            self.color_rect = settings.BUTTON_COLOR_ACTIVE  # Hover color
            self.color_text = settings.TEXT_COLOR_ACTIVE
        else:
            self.color_rect = settings.BUTTON_COLOR_PASSIVE  # Default color
            self.color_text = settings.TEXT_COLOR_PASSIVE

class LogoutButton(Button):

        def __init__(self, window, x: int = 0, y: int =0, text: str = ""):
            super().__init__(window, x, y, text)
            self.font = pygame.font.Font(settings.FONT_PATH, settings.LOGOUT_FONT_SIZE)
            self.rect = pygame.Rect(self.x, self.y, settings.LOGOUT_BUTTON_WIDTH, settings.LOGOUT_BUTTON_HEIGHT)

        def draw(self):
            pygame.draw.rect(self.window, self.color_rect, self.rect)
            text_obj = self.font.render(self.text, True, self.color_text)
            text_rect = text_obj.get_rect(center=(self.x + settings.LOGOUT_BUTTON_WIDTH / 2, self.y + settings.LOGOUT_BUTTON_HEIGHT / 2))
            self.window.blit(text_obj, text_rect)

        def update_color(self):
            mx, my = pygame.mouse.get_pos()
            if self.rect.collidepoint((mx, my)):
                self.color_rect = settings.BUTTON_COLOR_ACTIVE  # Hover color
                self.color_text = settings.TEXT_COLOR_ACTIVE
            else:
                self.color_rect = settings.BUTTON_COLOR_PASSIVE  # Default color
                self.color_text = settings.TEXT_COLOR_PASSIVE

class InputField():

    def __init__(self, window, x: int = 0, y: int =0, name: str = "", content: str = "", pwd: bool = False, active: bool = False):
        self.window = window
        self.x = x
        self.y = y
        self.name = name
        self.content = content
        self.pwd = pwd
        self.color_rect = settings.FIELD_COLOR_PASSIVE
        self.color_text = settings.TEXT_COLOR_PASSIVE
        self.font = pygame.font.Font(settings.FONT_PATH, settings.FONT_SIZE)
        self.rect = pygame.Rect(self.x, self.y, settings.SMALL_FIELD_WIDTH, settings.SMALL_FIELD_HEIGHT)

        self.cursor_pos = 0
        self.cursor_surface = pygame.Surface((int(self.font.size('|')[0]), int(self.font.get_height())))
        self.cursor_surface.fill((0, 0, 0))  # fill the cursor surface with black color

        self.active = active

    def insert(self, character):
        self.content = self.content[:self.cursor_pos] + character + self.content[self.cursor_pos:]
        self.cursor_pos += 1

    def backspace(self):
        if self.cursor_pos:
            self.content = self.content[:self.cursor_pos - 1] + self.content[self.cursor_pos:]
            self.cursor_pos = max(0, self.cursor_pos - 1)

    def empty(self):
        self.content = ''
        self.cursor_pos = 0

    def collide(self):
        mx, my = pygame.mouse.get_pos()
        return self.rect.collidepoint((mx, my))

    def draw(self):
        # Name of input field
        text_obj = self.font.render(self.name, True, settings.COLOR_HEADER)
        text_rect = text_obj.get_rect(midleft=(self.x, self.y - settings.SMALL_SPACER_Y))
        self.window.blit(text_obj, text_rect)

        # rect of input field
        pygame.draw.rect(self.window, self.color_rect, self.rect)

        # content of input field
        if self.pwd:
            visible_content = '*' * len(self.content)
        else:
            visible_content = self.content
        text_obj = self.font.render(visible_content, True, self.color_text)
        text_rect = text_obj.get_rect(midleft=(self.x + settings.TINY_SPACER_X, self.y + settings.SMALL_FIELD_HEIGHT / 2))
        self.window.blit(text_obj, text_rect)

        # curser
        cursor_y_pos = self.y + (settings.SMALL_FIELD_HEIGHT - self.cursor_surface.get_height()) // 2
        cursor_x_pos = self.x + settings.TINY_SPACER_X + self.font.size(visible_content[:self.cursor_pos])[0]
        if self.active:  # if this field is active
            self.window.blit(self.cursor_blink(), (cursor_x_pos, cursor_y_pos))

    def update_color(self):
        mx, my = pygame.mouse.get_pos()
        if self.rect.collidepoint((mx, my)):
            self.color_rect = settings.FIELD_COLOR_ACTIVE  # Hover color
            self.color_text = settings.TEXT_COLOR_ACTIVE
        else:
            self.color_rect = settings.FIELD_COLOR_PASSIVE  # Default color
            self.color_text = settings.TEXT_COLOR_PASSIVE

    def cursor_blink(self):
        if pygame.time.get_ticks() % 1000 // 500:  # every half second
            return self.cursor_surface
        else:
            return pygame.Surface((0, 0))  # transparent surface

    def update_cursor_pos(self, mouse_x):
        """Updates the cursor position based on the mouse's x-coordinate."""
        for i in range(len(self.content)):
            if self.font.size(self.content[:i+1])[0] + self.x >= mouse_x:
                self.cursor_pos = i
                return
        self.cursor_pos = len(self.content)


