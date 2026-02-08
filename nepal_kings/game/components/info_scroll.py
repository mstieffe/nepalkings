import pygame
import pandas as pd

from config import settings


class InfoScroll:
    def __init__(
        self,
        window: pygame.Surface,
        x: int,
        y: int,
        width: int,
        height: int,
        title: str,
        text_df: pd.DataFrame,
        bg_img_path: str,
    ):
        self.window = window
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.title = title
        self.text_df = text_df
        self.bg_img_path = bg_img_path

        self.font_title = self._load_font(settings.INFO_SCROLL_FONT_SIZE, bold=True)
        self.font_col_names = self._load_font(settings.INFO_SCROLL_FONT_SIZE, italic=True)
        self.font_text = self._load_font(settings.INFO_SCROLL_FONT_SIZE)

        self.rect_glow_black = self._load_scaled_image(
            settings.GLOW_RECT_IMG_PATH + 'black.png', width * 1.2, height * 1.2
        )
        self.rect_glow_yellow = self._load_scaled_image(
            settings.GLOW_RECT_IMG_PATH + 'yellow.png', width * 1.2, height * 1.2
        )

        self.rect = pygame.Rect(self.x, self.y, self.width, self.height)

        self.background = self._load_scaled_image(bg_img_path, self.width, self.height)
        self.preloaded_icons = self._preload_icons()

    def _load_font(self, size, bold=False, italic=False):
        """Load a font with optional styles."""
        font = pygame.font.Font(settings.FONT_PATH, size)
        font.set_bold(bold)
        font.set_italic(italic)
        return font

    def _load_scaled_image(self, path, width, height):
        """Load and scale an image."""
        image = pygame.image.load(path).convert_alpha()
        return pygame.transform.smoothscale(image, (int(width), int(height)))

    def _preload_icons(self):
        """Preload and preprocess icons from the DataFrame."""
        preloaded_icons = {}
        for _, row in self.text_df.iterrows():
            for icon_type in ['icon_img_red', 'icon_img_black', 'icon_img']:
                if icon_type in row and row[icon_type] not in preloaded_icons:
                    preloaded_icons[row[icon_type]] = self._load_scaled_image(
                        row[icon_type], settings.INFO_SCROLL_ICON_SIZE, settings.INFO_SCROLL_ICON_SIZE
                    )
        return preloaded_icons

    def _draw_text_with_background(self, text, color, x, y):
        """Render text with a colored background."""
        text_obj = self.font_text.render(text, True, settings.INFO_SCROLL_SCORE_COLOR)
        text_rect = text_obj.get_rect(topleft=(x, y - text_obj.get_height() // 2))
        bg_rect = pygame.Rect(
            text_rect.x - settings.INFO_SCROLL_TEXT_PADDING,
            text_rect.y - settings.INFO_SCROLL_TEXT_PADDING,
            text_rect.width + 2 * settings.INFO_SCROLL_TEXT_PADDING,
            text_rect.height + 2 * settings.INFO_SCROLL_TEXT_PADDING
        )
        pygame.draw.rect(self.window, color, bg_rect)
        self.window.blit(text_obj, text_rect)

    def draw_msg(self):
        """Render the title, table, and preloaded icons to the screen."""
        starting_y_position = self.y + settings.INFO_SCROLL_Y_TITLE_MARGIN

        # Draw the title
        text_obj = self.font_title.render(self.title, True, settings.INFO_SCROLL_TEXT_COLOR)
        text_rect = text_obj.get_rect(centerx=self.x + self.width // 2, top=starting_y_position)
        self.window.blit(text_obj, text_rect)
        starting_y_position += settings.INFO_SCROLL_TITLE_SPACING

        # Draw rows with preloaded icons
        for _, row in self.text_df.iterrows():
            icon_x = self.x + settings.INFO_SCROLL_ICON_MARGIN
            text_y = starting_y_position + (settings.INFO_SCROLL_ICON_SIZE // 2)

            if 'icon_img_red' in row and 'icon_img_black' in row:
                # Scenario: resources_df with two icons
                self.window.blit(self.preloaded_icons[row['icon_img_red']], (icon_x, starting_y_position))
                self.window.blit(
                    self.preloaded_icons[row['icon_img_black']],
                    (icon_x + settings.INFO_SCROLL_ICON_SIZE + settings.INFO_SCROLL_ICON_SPACING, starting_y_position)
                )

                # Draw corresponding text
                self._draw_text_with_background(
                    str(row['red']), settings.COLOR_RED,
                    icon_x + settings.INFO_SCROLL_ICON_SIZE + settings.INFO_SCROLL_TEXT_MARGIN,
                    text_y
                )
                self._draw_text_with_background(
                    str(row['black']), settings.COLOR_BLACK,
                    icon_x + 2 * settings.INFO_SCROLL_ICON_SIZE + settings.INFO_SCROLL_ICON_SPACING + settings.INFO_SCROLL_TEXT_MARGIN,
                    text_y
                )

            elif 'icon_img' in row:
                # Scenario: slots_df with one icon
                self.window.blit(self.preloaded_icons[row['icon_img']], (icon_x, starting_y_position))
                self._draw_text_with_background(
                    str(row['red']), settings.COLOR_RED,
                    icon_x + settings.INFO_SCROLL_ICON_SIZE + settings.INFO_SCROLL_TEXT_MARGIN,
                    text_y
                )
                self._draw_text_with_background(
                    str(row['black']), settings.COLOR_BLACK,
                    icon_x + settings.INFO_SCROLL_ICON_SIZE + settings.INFO_SCROLL_TEXT_MARGIN + settings.INFO_SCROLL_TEXT_PADDING * 10,
                    text_y
                )

            starting_y_position += settings.INFO_SCROLL_LINE_SPACING

    def draw(self):
        """Draw the background and message to the screen."""
        # Glow effect based on mouse hover
        glow = self.rect_glow_yellow if self.collide() else self.rect_glow_black
        self.window.blit(glow, (self.x - 0.1 * self.width, self.y - 0.1 * self.height))

        # Draw the background and the formatted message
        self.window.blit(self.background, (self.x, self.y))
        self.draw_msg()

    def collide(self):
        """Check if the mouse is over the scroll."""
        return self.rect.collidepoint(pygame.mouse.get_pos())
    
    def update(self, game, families=None):
        """Update the state of the info scroll based on the game state."""
        if families:
            resources_data = game.calculate_resources(families)
            produces = resources_data.get('produces', {})
            requires = resources_data.get('requires', {})
            
            # Update text_df with calculated resources
            for idx, row in self.text_df.iterrows():
                element = row['element']
                
                # Map element names to resource keys (showing total_required/total_produced)
                if element == 'food':
                    self.text_df.at[idx, 'red'] = f"{requires.get('food_red', 0)}/{produces.get('food_red', 0)}"
                    self.text_df.at[idx, 'black'] = f"{requires.get('food_black', 0)}/{produces.get('food_black', 0)}"
                elif element == 'amor':
                    self.text_df.at[idx, 'red'] = f"{requires.get('armor_red', 0)}/{produces.get('armor_red', 0)}"
                    self.text_df.at[idx, 'black'] = f"{requires.get('armor_black', 0)}/{produces.get('armor_black', 0)}"
                elif element == 'material':
                    self.text_df.at[idx, 'red'] = f"{requires.get('material_red', 0)}/{produces.get('material_red', 0)}"
                    self.text_df.at[idx, 'black'] = f"{requires.get('material_black', 0)}/{produces.get('material_black', 0)}"
                elif element == 'village':
                    self.text_df.at[idx, 'red'] = f"{requires.get('villager_red', 0)}/{produces.get('villager_red', 0)}"
                    self.text_df.at[idx, 'black'] = f"{requires.get('villager_black', 0)}/{produces.get('villager_black', 0)}"
                elif element == 'military':
                    self.text_df.at[idx, 'red'] = f"{requires.get('warrior_red', 0)}/{produces.get('warrior_red', 0)}"
                    self.text_df.at[idx, 'black'] = f"{requires.get('warrior_black', 0)}/{produces.get('warrior_black', 0)}"
        
