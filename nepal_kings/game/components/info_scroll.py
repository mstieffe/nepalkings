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
        self.bg_img_path = bg_img_path  # kept for API compat, no longer used

        self.font_title = self._load_font(settings.INFO_SCROLL_FONT_SIZE, bold=True)
        self.font_col_names = self._load_font(settings.INFO_SCROLL_FONT_SIZE, italic=True)
        self.font_text = self._load_font(settings.INFO_SCROLL_FONT_SIZE)

        self.rect = pygame.Rect(self.x, self.y, self.width, self.height)

        # Build the dark semi-transparent background panel
        self._build_panel()
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

    def _build_panel(self):
        """Build the dark semi-transparent background panel surface."""
        r = settings.INFO_SCROLL_CORNER_R
        self._panel = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        pygame.draw.rect(self._panel, settings.INFO_SCROLL_BG_CLR,
                         (0, 0, self.width, self.height), border_radius=r)
        pygame.draw.rect(self._panel, settings.INFO_SCROLL_BORDER_CLR,
                         (0, 0, self.width, self.height),
                         width=settings.INFO_SCROLL_BORDER_WIDTH, border_radius=r)

    def _draw_text_with_background(self, text, color, x, y, has_deficit=False):
        """Render text with a colored background pill, using red border if deficit."""
        text_color = (255, 255, 255)
        text_obj = self.font_text.render(text, True, text_color)
        text_rect = text_obj.get_rect(topleft=(x, y - text_obj.get_height() // 2))
        bg_rect = pygame.Rect(
            text_rect.x - settings.INFO_SCROLL_TEXT_PADDING,
            text_rect.y - settings.INFO_SCROLL_TEXT_PADDING,
            text_rect.width + 2 * settings.INFO_SCROLL_TEXT_PADDING,
            text_rect.height + 2 * settings.INFO_SCROLL_TEXT_PADDING
        )

        # Draw pill background with rounded corners
        pill_surface = pygame.Surface((bg_rect.width, bg_rect.height), pygame.SRCALPHA)
        pygame.draw.rect(pill_surface, (*color, 220), (0, 0, bg_rect.width, bg_rect.height), border_radius=3)
        self.window.blit(pill_surface, bg_rect.topleft)

        # Draw red border if deficit
        if has_deficit:
            pygame.draw.rect(self.window, settings.INFO_SCROLL_DEFICIT_BORDER_CLR, bg_rect, 2, border_radius=3)

        self.window.blit(text_obj, text_rect)

    def draw_msg(self):
        """Render the title, table, and preloaded icons to the screen."""
        starting_y_position = self.y + settings.INFO_SCROLL_Y_TITLE_MARGIN

        # Draw the title in gold
        text_obj = self.font_title.render(self.title, True, settings.INFO_SCROLL_TITLE_COLOR)
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

                # Draw corresponding text with green/blue, use red for deficit
                red_text = str(row['red'])
                black_text = str(row['black'])
                
                # Check for deficit
                red_deficit = row.get('red_deficit', False)
                black_deficit = row.get('black_deficit', False)
                
                # Muted pill colours for dark theme
                red_color = settings.INFO_SCROLL_RED_PILL_CLR
                black_color = settings.INFO_SCROLL_BLACK_PILL_CLR
                
                # Adjust green text position slightly to the left
                red_text_x = icon_x + settings.INFO_SCROLL_ICON_SIZE + settings.INFO_SCROLL_TEXT_MARGIN - 5
                
                self._draw_text_with_background(
                    red_text, red_color,
                    red_text_x,
                    text_y,
                    has_deficit=red_deficit
                )
                self._draw_text_with_background(
                    black_text, black_color,
                    icon_x + 2 * settings.INFO_SCROLL_ICON_SIZE + settings.INFO_SCROLL_ICON_SPACING + settings.INFO_SCROLL_TEXT_MARGIN,
                    text_y,
                    has_deficit=black_deficit
                )

            elif 'icon_img' in row:
                # Scenario: slots_df with one icon
                self.window.blit(self.preloaded_icons[row['icon_img']], (icon_x, starting_y_position))
                
                # Draw corresponding text with green/blue, use red for deficit
                red_text = str(row['red'])
                black_text = str(row['black'])
                
                # Check for deficit
                red_deficit = row.get('red_deficit', False)
                black_deficit = row.get('black_deficit', False)
                
                # Muted pill colours for dark theme
                red_color = settings.INFO_SCROLL_RED_PILL_CLR
                black_color = settings.INFO_SCROLL_BLACK_PILL_CLR
                
                # Adjust green text position slightly to the left
                red_text_x = icon_x + settings.INFO_SCROLL_ICON_SIZE + settings.INFO_SCROLL_TEXT_MARGIN - 5
                
                self._draw_text_with_background(
                    red_text, red_color,
                    red_text_x,
                    text_y,
                    has_deficit=red_deficit
                )
                self._draw_text_with_background(
                    black_text, black_color,
                    icon_x + settings.INFO_SCROLL_ICON_SIZE + settings.INFO_SCROLL_TEXT_MARGIN + settings.INFO_SCROLL_TEXT_PADDING * 10,
                    text_y,
                    has_deficit=black_deficit
                )

            starting_y_position += settings.INFO_SCROLL_LINE_SPACING

    def draw(self):
        """Draw the background panel and resource content."""
        # Draw the dark semi-transparent panel
        self.window.blit(self._panel, (self.x, self.y))

        # Subtle gold highlight border on hover
        if self.collide():
            r = settings.INFO_SCROLL_CORNER_R
            pygame.draw.rect(self.window, (250, 221, 0, 50),
                             (self.x, self.y, self.width, self.height),
                             width=2, border_radius=r)

        # Draw the formatted resource data
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
                    red_req = requires.get('food_red', 0)
                    red_prod = produces.get('food_red', 0)
                    black_req = requires.get('food_black', 0)
                    black_prod = produces.get('food_black', 0)
                    
                    self.text_df.at[idx, 'red'] = f"{red_req}/{red_prod}"
                    self.text_df.at[idx, 'black'] = f"{black_req}/{black_prod}"
                    self.text_df.at[idx, 'red_deficit'] = red_req > red_prod
                    self.text_df.at[idx, 'black_deficit'] = black_req > black_prod
                    
                elif element == 'amor':
                    red_req = requires.get('armor_red', 0)
                    red_prod = produces.get('armor_red', 0)
                    black_req = requires.get('armor_black', 0)
                    black_prod = produces.get('armor_black', 0)
                    
                    self.text_df.at[idx, 'red'] = f"{red_req}/{red_prod}"
                    self.text_df.at[idx, 'black'] = f"{black_req}/{black_prod}"
                    self.text_df.at[idx, 'red_deficit'] = red_req > red_prod
                    self.text_df.at[idx, 'black_deficit'] = black_req > black_prod
                    
                elif element == 'material':
                    red_req = requires.get('material_red', 0)
                    red_prod = produces.get('material_red', 0)
                    black_req = requires.get('material_black', 0)
                    black_prod = produces.get('material_black', 0)
                    
                    self.text_df.at[idx, 'red'] = f"{red_req}/{red_prod}"
                    self.text_df.at[idx, 'black'] = f"{black_req}/{black_prod}"
                    self.text_df.at[idx, 'red_deficit'] = red_req > red_prod
                    self.text_df.at[idx, 'black_deficit'] = black_req > black_prod
                    
                elif element == 'village':
                    red_req = requires.get('villager_red', 0)
                    red_prod = produces.get('villager_red', 0)
                    black_req = requires.get('villager_black', 0)
                    black_prod = produces.get('villager_black', 0)
                    
                    self.text_df.at[idx, 'red'] = f"{red_req}/{red_prod}"
                    self.text_df.at[idx, 'black'] = f"{black_req}/{black_prod}"
                    self.text_df.at[idx, 'red_deficit'] = red_req > red_prod
                    self.text_df.at[idx, 'black_deficit'] = black_req > black_prod
                    
                elif element == 'military':
                    red_req = requires.get('warrior_red', 0)
                    red_prod = produces.get('warrior_red', 0)
                    black_req = requires.get('warrior_black', 0)
                    black_prod = produces.get('warrior_black', 0)
                    
                    self.text_df.at[idx, 'red'] = f"{red_req}/{red_prod}"
                    self.text_df.at[idx, 'black'] = f"{black_req}/{black_prod}"
                    self.text_df.at[idx, 'red_deficit'] = red_req > red_prod
                    self.text_df.at[idx, 'black_deficit'] = black_req > black_prod
        
