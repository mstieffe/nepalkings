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
        self.rect_glow.center = (self.x, self.y)
        self.rect_glow_big.center = (self.x, self.y)

    def collide(self):
        """Check if the mouse is hovering over the arrow."""
        mx, my = pygame.mouse.get_pos()
        return self.rect_arrow.collidepoint((mx, my))

    def draw(self):
        """Draw the arrow and glow images based on the state."""
        arrow_img = self.image_arrow_big if self.clicked or self.hovered else self.image_arrow
        glow_img = self.glow_images['yellow_big'] if self.clicked else self.glow_images['yellow']

        if not self.is_active:
            glow_img = self.glow_images['black'] if not self.hovered else self.glow_images['white']
            arrow_img = self.image_arrow

        if self.hovered:
            if self.clicked:
                self.window.blit(self.glow_images['orange_big'], self.rect_glow_big.topleft)
            else:
                self.window.blit(glow_img, self.rect_glow.topleft)

        self.window.blit(arrow_img, self.rect_arrow.topleft)

    def update(self):
        """Update the hovered and clicked state."""
        self.hovered = self.collide()

        if self.hovered and pygame.mouse.get_pressed()[0]:
            self.clicked = True
            self.callback()  # Trigger the callback when clicked
        else:
            self.clicked = False