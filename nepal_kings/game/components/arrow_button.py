from config import settings
import pygame

class ArrowButton:
    def __init__(self, window, callback, x=0, y=0, direction='right', is_active=True):
        self.window = window
        self.callback = callback
        self.x = x
        self.y = y
        self.is_active = is_active

        # Load and scale arrow images based on direction
        arrow_image_path = settings.LEFT_ARROW_IMG_PATH if direction == 'left' else settings.RIGHT_ARROW_IMG_PATH
        arrow_image = pygame.image.load(arrow_image_path)
        self.image_arrow = pygame.transform.scale(arrow_image, (settings.ARROW_WIDTH, settings.ARROW_HEIGHT))
        self.image_arrow_big = pygame.transform.scale(arrow_image, (settings.ARROW_BIG_WIDTH, settings.ARROW_BIG_HEIGHT))
        self.image_arrow_transparent = pygame.transform.scale(arrow_image, (settings.ARROW_WIDTH, settings.ARROW_HEIGHT))
        self.image_arrow_transparent.set_alpha(0.5)
        self.image_arrow_big_transparent = pygame.transform.scale(arrow_image, (settings.ARROW_BIG_WIDTH, settings.ARROW_BIG_HEIGHT))
        self.image_arrow_big_transparent.set_alpha(0.5)

        # Load and scale glow images
        self.glow_images = {
            'yellow': pygame.transform.scale(pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH + 'yellow.png'), (settings.ARROW_GLOW_WIDTH, settings.ARROW_GLOW_WIDTH)),
            'white': pygame.transform.scale(pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH + 'white.png'), (settings.ARROW_GLOW_WIDTH, settings.ARROW_GLOW_WIDTH)),
            'black': pygame.transform.scale(pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH + 'black.png'), (settings.ARROW_GLOW_WIDTH, settings.ARROW_GLOW_WIDTH)),
            'orange': pygame.transform.scale(pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH + 'orange.png'), (settings.ARROW_GLOW_WIDTH, settings.ARROW_GLOW_WIDTH)),
            'yellow_big': pygame.transform.scale(pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH + 'yellow.png'), (settings.ARROW_GLOW_BIG_WIDTH, settings.ARROW_GLOW_BIG_WIDTH)),
            'white_big': pygame.transform.scale(pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH + 'white.png'), (settings.ARROW_GLOW_BIG_WIDTH, settings.ARROW_GLOW_BIG_WIDTH)),
            'orange_big': pygame.transform.scale(pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH + 'orange.png'), (settings.ARROW_GLOW_BIG_WIDTH, settings.ARROW_GLOW_BIG_WIDTH))
        }

        # Set up rectangles for positioning
        self.rect_arrow = self.image_arrow.get_rect(center=(self.x, self.y))
        self.rect_arrow_big = self.image_arrow_big.get_rect(center=(self.x, self.y))
        self.rect_glow = self.glow_images['yellow'].get_rect(center=(self.x, self.y))
        self.rect_glow_big = self.glow_images['yellow_big'].get_rect(center=(self.x, self.y))

        # Initialize button states
        self.clicked = False
        self.hovered = False

    def set_position(self, x, y):
        """Set the position of the arrow and glow images."""
        self.x = x
        self.y = y
        self.rect_arrow.center = (self.x, self.y)
        self.rect_arrow_big.center = (self.x, self.y)
        delta_x_glow = settings.ARROW_WIDTH*0.03 if self.direction == 'left' else -settings.ARROW_WIDTH*0.03
        delta_x_glow_big = settings.ARROW_BIG_WIDTH*0.03 if self.direction == 'left' else -settings.ARROW_BIG_WIDTH*0.03
        self.rect_glow.center = (self.x+delta_x_glow, self.y)
        self.rect_glow_big.center = (self.x+delta_x_glow_big, self.y)

    def collide(self):
        """Check if the mouse is hovering over the arrow."""
        mx, my = pygame.mouse.get_pos()
        return self.rect_arrow.collidepoint((mx, my))

    def draw(self):
        """Draw the arrow and glow images based on the state."""
        arrow_image = self.image_arrow if self.is_active else self.image_arrow_transparent
        arrow_image_big = self.image_arrow_big if self.is_active else self.image_arrow_big_transparent

        glow_image = self.glow_images['orange'] if self.is_active else self.glow_images['white']
        glow_image_clicked = self.glow_images['orange'] if self.is_active else self.glow_images['white']
        glow_image_big = self.glow_images['yellow_big'] if self.is_active else self.glow_images['black_big']

        if self.hovered and pygame.mouse.get_pressed()[0]:
            self.window.blit(glow_image, self.rect_glow)
            self.window.blit(arrow_image, self.rect_arrow)
        elif self.hovered:
            self.window.blit(glow_image_big, self.rect_glow_big)
            self.window.blit(arrow_image_big, self.rect_arrow_big)
        elif self.clicked:
            self.window.blit(glow_image_clicked, self.rect_glow)
            self.window.blit(arrow_image, self.rect_arrow)
        else:
            self.window.blit(arrow_image, self.rect_arrow)

    def update(self):
        """Update the hovered and clicked state."""
        self.hovered = self.collide()

        if self.hovered and pygame.mouse.get_pressed()[0]:
            self.clicked = True
            self.callback()  # Trigger the callback when clicked
        else:
            self.clicked = False