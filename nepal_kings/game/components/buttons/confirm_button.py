from config import settings
import pygame


class ConfirmButton:
    def __init__(self, window, x=0, y=0, text="", width=None, height=None, disabled=False):
        self.window = window
        self.x = x
        self.y = y
        self.text = text
        self.disabled = disabled  # New attribute for disabling the button

        # Load font settings
        self.font = pygame.font.Font(settings.FONT_PATH, settings.CONFIRM_BUTTON_FONT_SIZE)
        self.font_small = pygame.font.Font(settings.FONT_PATH, int(settings.CONFIRM_BUTTON_FONT_SIZE_SMALL))

        # Set button dimensions based on text and provided width/height
        self.set_dimensions(width, height)

        # Load button images and glow images
        self.load_images()

        # Button states
        self.hovered = False
        self.clicked = False
        self.active = False

    def set_dimensions(self, width, height):
        """Calculate button dimensions and text alignment."""
        text_obj = self.font.render(self.text, True, settings.CONFIRM_BUTTON_TEXT_COLOR_PASSIVE)
        button_width = max(width or settings.CONFIRM_BUTTON_WIDTH, text_obj.get_width() + settings.SMALL_SPACER_X)
        button_height = height or settings.CONFIRM_BUTTON_HEIGHT

        # Define button rectangle
        self.rect = pygame.Rect(self.x, self.y, button_width, button_height)

    def load_images(self):
        """Load button and glow images and apply scaling."""
        self.button_images = {
            "passive": pygame.transform.scale(
                pygame.image.load(settings.CONFIRM_BUTTON_IMG_PATH.replace("confirm_button.png", "blue.png")),
                (self.rect.width, self.rect.height),
            ),
            "hovered": pygame.transform.scale(
                pygame.image.load(settings.CONFIRM_BUTTON_IMG_PATH.replace("confirm_button.png", "yellow.png")),
                (self.rect.width, self.rect.height),
            ),
            "active": pygame.transform.scale(
                pygame.image.load(settings.CONFIRM_BUTTON_IMG_PATH.replace("confirm_button.png", "green.png")),
                (self.rect.width, self.rect.height),
            ),
            "disabled": pygame.transform.scale(
                pygame.image.load(settings.CONFIRM_BUTTON_IMG_PATH.replace("confirm_button.png", "grey.png")),
                (self.rect.width, self.rect.height),
            ),
        }

        # Load glow images and scale
        self.glow_images = {
            "white": pygame.transform.scale(
                pygame.image.load(settings.CONFIRM_BUTTON_GLOW_DIR + "white.png"),
                (int(self.rect.width * 1.4), int(self.rect.height * 1.4)),
            ),
            "yellow": pygame.transform.scale(
                pygame.image.load(settings.CONFIRM_BUTTON_GLOW_DIR + "yellow.png"),
                (int(self.rect.width * 1.4), int(self.rect.height * 1.4)),
            ),
            "orange": pygame.transform.scale(
                pygame.image.load(settings.CONFIRM_BUTTON_GLOW_DIR + "orange.png"),
                (int(self.rect.width * 1.4), int(self.rect.height * 1.4)),
            ),
        }

    def collide(self):
        """Check if the mouse is over the button."""
        return self.rect.collidepoint(pygame.mouse.get_pos())

    def draw(self):
        """Draw the button, including the background, glow, and text."""

        # If disabled, draw grey button and skip hover/glow
        if self.disabled:
            self.window.blit(self.button_images["disabled"], self.rect.topleft)
            text_obj = self.font.render(self.text, True, settings.CONFIRM_BUTTON_TEXT_COLOR_DISABLED)
            self.window.blit(text_obj, text_obj.get_rect(center=self.rect.center))
            return

        # Draw glow based on button state
        if self.hovered and self.active:
            self.draw_glow("orange")
        elif self.hovered:
            self.draw_glow("yellow")
        elif self.active:
            self.draw_glow("orange")
        else:
            self.draw_glow("white")

        # Draw button background
        button_image = (
            self.button_images["active"] if self.active else
            self.button_images["active"] if self.hovered and pygame.mouse.get_pressed()[0] else
            self.button_images["hovered"] if self.hovered else
            self.button_images["passive"]
        )
        self.window.blit(button_image, self.rect.topleft)

        # Draw text with appropriate size
        text_obj = (self.font_small if self.clicked else self.font).render(self.text, True, self.get_text_color())
        self.window.blit(text_obj, text_obj.get_rect(center=self.rect.center))

    def draw_glow(self, color):
        """Draw the glow image based on the given color."""
        glow_image = self.glow_images.get(color)
        if glow_image:
            self.window.blit(glow_image, glow_image.get_rect(center=self.rect.center).topleft)

    def get_text_color(self):
        """Return the appropriate text color based on the button state."""
        if self.disabled:
            return settings.CONFIRM_BUTTON_TEXT_COLOR_DISABLED
        if self.hovered:
            return settings.CONFIRM_BUTTON_TEXT_COLOR_HOVERED
        elif self.active:
            return settings.CONFIRM_BUTTON_TEXT_COLOR_ACTIVE
        return settings.CONFIRM_BUTTON_TEXT_COLOR_PASSIVE

    def update(self):
        """Update the button's state based on mouse interaction."""
        if not self.disabled:
            self.hovered = self.collide()
            self.clicked = self.hovered and pygame.mouse.get_pressed()[0]
        else:
            self.hovered = False
            self.clicked = False
