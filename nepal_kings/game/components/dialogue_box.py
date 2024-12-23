from utils.utils import Button
from config import settings
import pygame

import textwrap

from utils.utils import Button
from config import settings
import pygame
import textwrap

class DialogueBox:
    def __init__(self, window, message, actions=None, images=None, icon=None, title=""):
        if actions is None:
            actions = ['ok']
        if images is None:
            images = []

        self.window = window
        self.message = message
        self.images = images  # List of preloaded pygame.Surface objects or drawable objects
        self.icon = None  # Placeholder for the scaled icon image
        self.title = title
        self.font = pygame.font.Font(settings.FONT_PATH, settings.FONT_SIZE_DIALOGUE_BOX)
        self.title_font = pygame.font.Font(settings.FONT_PATH, settings.FONT_SIZE_TITLE_DIALOGUE_BOX)
        self.title_font.set_bold(True)
        self.actions = actions

        # Check and scale the icon if provided
        if icon and icon in settings.DIALOGUE_BOX_ICON_NAME_TO_IMG_DICT:
            original_icon = settings.DIALOGUE_BOX_ICON_NAME_TO_IMG_DICT[icon]
            self.icon = self.scale_icon(original_icon)

        # Calculate the message lines
        self.lines = textwrap.wrap(
            self.message,
            width=(settings.DIALOGUE_BOX_WIDTH - settings.SMALL_SPACER_X) // (2 * self.font.size(' ')[0])
        )
        self.lines_surfaces = [self.font.render(line, True, settings.MSG_TEXT_COLOR) for line in self.lines]

        # Separate drawable objects from plain images
        self.scaled_images, self.drawable_objects = self.process_images()

        # Calculate the title height
        self.title_height = self.title_font.get_height() + settings.SMALL_SPACER_Y if self.title else 0

        # Calculate the new box height
        self.text_height = len(self.lines) * (self.font.get_height() + settings.SMALL_SPACER_Y)
        self.button_height = settings.MENU_BUTTON_HEIGHT + 2 * settings.SMALL_SPACER_Y
        self.img_height = settings.DIALOGUE_BOX_IMG_HEIGHT if self.scaled_images else 0
        self.drawable_object_height = settings.DIALOGUE_BOX_DRAWABLE_OBJECT_HEIGHT if self.drawable_objects else 0
        self.img_spacing = settings.SMALL_SPACER_Y if self.scaled_images or self.drawable_objects else 0
        self.box_height = (self.title_height + self.text_height + self.img_height + self.drawable_object_height +
                           self.img_spacing + self.button_height + settings.SMALL_SPACER_Y + settings.DIALOGUE_BOX_TEXT_MARGIN_Y)

        # Calculate the position of the box to make sure it's in the center
        self.x = settings.CENTER_X - settings.DIALOGUE_BOX_WIDTH / 2
        self.y = settings.CENTER_Y - self.box_height * 0.75
        self.rect = pygame.Rect(self.x, self.y, settings.DIALOGUE_BOX_WIDTH, self.box_height)

        # Define the border rectangle (slightly larger than the dialogue box)
        self.border_rect = self.rect.inflate(settings.DIALOGUE_BOX_BORDER_WIDTH, settings.DIALOGUE_BOX_BORDER_WIDTH)

        # Adjust the buttons
        button_y = self.rect.y + self.box_height - self.button_height
        first_button_x = settings.CENTER_X - len(self.actions) * (settings.MENU_BUTTON_WIDTH / 2) - \
                         (len(self.actions) - 1) * (settings.SMALL_SPACER_X / 2)
        button_x = [first_button_x + n * (settings.MENU_BUTTON_WIDTH + settings.SMALL_SPACER_X) for n in range(len(self.actions))]
        self.buttons = [Button(self.window, button_x[i], button_y, self.actions[i]) for i in range(len(self.actions))]

    def process_images(self):
        """Separate pygame.Surface images and drawable objects, scaling the surfaces."""
        scaled_images = []
        drawable_objects = []

        for img in self.images:
            if isinstance(img, pygame.Surface):
                # Scale plain pygame.Surface images
                img_width, img_height = img.get_size()
                scale_ratio = settings.DIALOGUE_BOX_IMG_HEIGHT / img_height
                new_width = int(img_width * scale_ratio)
                scaled_images.append(pygame.transform.smoothscale(img, (new_width, settings.DIALOGUE_BOX_IMG_HEIGHT)))
            elif hasattr(img, "draw_icon"):
                # Identify objects with a draw_icon method
                drawable_objects.append(img)

        return scaled_images, drawable_objects

    def scale_icon(self, icon):
        """Scale the provided icon to fit the dialogue box."""
        icon_width, icon_height = icon.get_size()
        scale_ratio = settings.DIALOGUE_BOX_ICON_HEIGHT / icon_height
        new_width = int(icon_width * scale_ratio)
        return pygame.transform.smoothscale(icon, (new_width, settings.DIALOGUE_BOX_ICON_HEIGHT))

    def draw(self):
        # Draw border
        pygame.draw.rect(self.window, settings.COLOR_DIALOGUE_BOX_BORDER, self.border_rect)

        # Draw Box
        pygame.draw.rect(self.window, settings.COLOR_DIALOGUE_BOX, self.rect)

        current_y = self.rect.y + settings.DIALOGUE_BOX_TEXT_MARGIN_Y

        # Draw the title and icons if title is provided
        if self.title:
            title_surface = self.title_font.render(self.title, True, settings.TITLE_TEXT_COLOR)
            title_rect = title_surface.get_rect(center=(self.rect.centerx, current_y))

            if self.icon:
                # Draw icons on both sides of the title
                icon_x_left = title_rect.left - settings.SMALL_SPACER_X - self.icon.get_width()
                icon_x_right = title_rect.right + settings.SMALL_SPACER_X
                icon_y = title_rect.y + title_rect.height // 2 - self.icon.get_height() // 2
                self.window.blit(self.icon, (icon_x_left, icon_y))
                self.window.blit(self.icon, (icon_x_right, icon_y))

            self.window.blit(title_surface, title_rect)
            current_y += title_rect.height + settings.SMALL_SPACER_Y

        # Draw each line of the message
        for i, line_surface in enumerate(self.lines_surfaces):
            line_y = current_y + i * (self.font.get_height() + settings.SMALL_SPACER_Y)
            line_rect = line_surface.get_rect(center=(self.rect.centerx, line_y))
            self.window.blit(line_surface, line_rect)

        # Draw scaled images horizontally
        if self.scaled_images or self.drawable_objects:
            total_width = sum(img.get_width() for img in self.scaled_images) + \
                          (len(self.scaled_images) - 1) * settings.SMALL_SPACER_X
            for obj in self.drawable_objects:
                total_width += settings.DIALOGUE_BOX_IMG_HEIGHT + settings.SMALL_SPACER_X

            image_x_start = self.rect.centerx - total_width // 2
            image_y = current_y + len(self.lines_surfaces) * (self.font.get_height() + settings.SMALL_SPACER_Y) #+ settings.SMALL_SPACER_Y

            # Draw scaled pygame.Surface images
            for img in self.scaled_images:
                self.window.blit(img, (image_x_start, image_y))
                image_x_start += img.get_width() + settings.SMALL_SPACER_X

            # Draw objects with a custom draw_icon method
            for obj in self.drawable_objects:
                obj.draw_icon(image_x_start, image_y, settings.DIALOGUE_BOX_DRAWABLE_OBJECT_HEIGHT, settings.DIALOGUE_BOX_DRAWABLE_OBJECT_HEIGHT)
                image_x_start += settings.DIALOGUE_BOX_DRAWABLE_OBJECT_HEIGHT + settings.SMALL_SPACER_X

        # Draw the buttons
        for button in self.buttons:
            button.draw()

    def update(self, events):
        # Update the button colors
        for button in self.buttons:
            button.update()

        # Handle the button click events
        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN:
                for button in self.buttons:
                    if button.collide():
                        return button.text.lower()
        return None

    def scale_images(self):
        """Scale preloaded images to fit the dialogue box."""
        scaled_images = []
        for img in self.images:
            img_width, img_height = img.get_size()
            scale_ratio = settings.DIALOGUE_BOX_IMG_HEIGHT / img_height
            new_width = int(img_width * scale_ratio)
            scaled_img = pygame.transform.smoothscale(img, (new_width, settings.DIALOGUE_BOX_IMG_HEIGHT))
            scaled_images.append(scaled_img)
        return scaled_images

    def scale_icon(self, icon):
        """Scale the provided icon to fit the dialogue box."""
        icon_width, icon_height = icon.get_size()
        scale_ratio = settings.DIALOGUE_BOX_ICON_HEIGHT / icon_height
        new_width = int(icon_width * scale_ratio)
        return pygame.transform.smoothscale(icon, (new_width, settings.DIALOGUE_BOX_ICON_HEIGHT))
