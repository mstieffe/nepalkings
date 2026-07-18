# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
import pygame
from typing import List, Dict, Any

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
        text_data: List[Dict[str, Any]],
        bg_img_path: str,
    ):
        self.window = window
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.title = title
        self.text_data = text_data
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
        if italic:
            # Italic not in global cache – create a private instance
            font = pygame.font.Font(settings.FONT_PATH, size)
            font.set_bold(bold)
            font.set_italic(True)
            return font
        return settings.get_font(size, bold=bold)

    def _load_scaled_image(self, path, width, height):
        """Load and scale an image."""
        image = pygame.image.load(path).convert_alpha()
        return pygame.transform.smoothscale(image, (int(width), int(height)))

    def _preload_icons(self):
        """Preload and preprocess icons from the data."""
        preloaded_icons = {}
        for row in self.text_data:
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

    def _resource_row_rects(self, starting_y_position):
        """Return the icon and two value cells for one resource row.

        Deriving both pill widths from the panel's inner bounds keeps the
        mobile legibility font from pushing the black value past the border.
        """
        icon_rect = pygame.Rect(
            self.x + settings.INFO_SCROLL_ICON_MARGIN,
            starting_y_position,
            settings.INFO_SCROLL_ICON_SIZE,
            settings.INFO_SCROLL_ICON_SIZE,
        )
        pill_x = icon_rect.right + settings.INFO_SCROLL_TEXT_MARGIN
        content_right = self.rect.right - settings.INFO_SCROLL_ICON_MARGIN
        gap = settings.INFO_SCROLL_ICON_SPACING
        available = max(2, content_right - pill_x - gap)
        red_w = available // 2
        black_w = available - red_w
        pill_h = (
            self.font_text.get_height()
            + 2 * settings.INFO_SCROLL_TEXT_PADDING
        )
        pill_y = icon_rect.centery - pill_h // 2
        red_rect = pygame.Rect(pill_x, pill_y, red_w, pill_h)
        black_rect = pygame.Rect(red_rect.right + gap, pill_y, black_w, pill_h)
        return icon_rect, red_rect, black_rect

    def _font_for_pill(self, text, width):
        """Use the normal resource font, shrinking only unusually wide values."""
        max_text_w = max(
            1, width - 2 * settings.INFO_SCROLL_TEXT_PADDING)
        font = self.font_text
        if font.size(text)[0] <= max_text_w:
            return font

        size = settings.INFO_SCROLL_FONT_SIZE
        minimum = max(10, int(size * 0.70))
        while size > minimum:
            size -= 1
            font = settings.get_font(size, allow_small=True)
            if font.size(text)[0] <= max_text_w:
                break
        return font

    def _draw_text_with_background(
            self, text, color, rect, has_deficit=False):
        """Render text centred inside a bounded colored value pill."""
        text_color = (255, 255, 255)
        text_obj = self._font_for_pill(text, rect.w).render(
            text, True, text_color)
        bg_rect = pygame.Rect(rect)

        # Draw pill background with rounded corners
        pill_surface = pygame.Surface((bg_rect.width, bg_rect.height), pygame.SRCALPHA)
        pygame.draw.rect(pill_surface, (*color, 220), (0, 0, bg_rect.width, bg_rect.height), border_radius=3)
        self.window.blit(pill_surface, bg_rect.topleft)

        # Draw red border if deficit
        if has_deficit:
            pygame.draw.rect(self.window, settings.INFO_SCROLL_DEFICIT_BORDER_CLR, bg_rect, 2, border_radius=3)

        # Centre text horizontally within the pill
        text_rect = text_obj.get_rect(center=bg_rect.center)
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
        for row in self.text_data:
            icon_rect, red_rect, black_rect = self._resource_row_rects(
                starting_y_position)

            if 'icon_img_red' in row and 'icon_img_black' in row:
                # Scenario: resources_df with two icons
                self.window.blit(
                    self.preloaded_icons[row['icon_img_red']],
                    icon_rect.topleft)

                # Draw corresponding text with green/blue, use red for deficit
                red_text = str(row['red'])
                black_text = str(row['black'])
                
                # Check for deficit
                red_deficit = row.get('red_deficit', False)
                black_deficit = row.get('black_deficit', False)
                
                # Muted pill colours for dark theme
                red_color = settings.INFO_SCROLL_RED_PILL_CLR
                black_color = settings.INFO_SCROLL_BLACK_PILL_CLR

                self._draw_text_with_background(
                    red_text, red_color, red_rect,
                    has_deficit=red_deficit
                )
                self._draw_text_with_background(
                    black_text, black_color, black_rect,
                    has_deficit=black_deficit
                )

            elif 'icon_img' in row:
                # Scenario: slots_df with one icon
                self.window.blit(
                    self.preloaded_icons[row['icon_img']],
                    icon_rect.topleft)

                # Draw corresponding text with green/blue, use red for deficit
                red_text = str(row['red'])
                black_text = str(row['black'])
                
                # Check for deficit
                red_deficit = row.get('red_deficit', False)
                black_deficit = row.get('black_deficit', False)
                
                # Muted pill colours for dark theme
                red_color = settings.INFO_SCROLL_RED_PILL_CLR
                black_color = settings.INFO_SCROLL_BLACK_PILL_CLR

                self._draw_text_with_background(
                    red_text, red_color, red_rect,
                    has_deficit=red_deficit
                )
                self._draw_text_with_background(
                    black_text, black_color, black_rect,
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
            
            # Update text_data with calculated resources
            for row in self.text_data:
                element = row['element']
                
                # Map element names to resource keys (showing total_required/total_produced)
                if element == 'food':
                    red_req = requires.get('food_red', 0)
                    red_prod = produces.get('food_red', 0)
                    black_req = requires.get('food_black', 0)
                    black_prod = produces.get('food_black', 0)
                    
                    row['red'] = f"{red_req}/{red_prod}"
                    row['black'] = f"{black_req}/{black_prod}"
                    row['red_deficit'] = red_req > red_prod
                    row['black_deficit'] = black_req > black_prod
                    
                elif element == 'amor':
                    red_req = requires.get('armor_red', 0)
                    red_prod = produces.get('armor_red', 0)
                    black_req = requires.get('armor_black', 0)
                    black_prod = produces.get('armor_black', 0)
                    
                    row['red'] = f"{red_req}/{red_prod}"
                    row['black'] = f"{black_req}/{black_prod}"
                    row['red_deficit'] = red_req > red_prod
                    row['black_deficit'] = black_req > black_prod
                    
                elif element == 'material':
                    red_req = requires.get('material_red', 0)
                    red_prod = produces.get('material_red', 0)
                    black_req = requires.get('material_black', 0)
                    black_prod = produces.get('material_black', 0)
                    
                    row['red'] = f"{red_req}/{red_prod}"
                    row['black'] = f"{black_req}/{black_prod}"
                    row['red_deficit'] = red_req > red_prod
                    row['black_deficit'] = black_req > black_prod
                    
                elif element == 'village':
                    red_req = requires.get('villager_red', 0)
                    red_prod = produces.get('villager_red', 0)
                    black_req = requires.get('villager_black', 0)
                    black_prod = produces.get('villager_black', 0)
                    
                    row['red'] = f"{red_req}/{red_prod}"
                    row['black'] = f"{black_req}/{black_prod}"
                    row['red_deficit'] = red_req > red_prod
                    row['black_deficit'] = black_req > black_prod
                    
                elif element == 'military':
                    red_req = requires.get('warrior_red', 0)
                    red_prod = produces.get('warrior_red', 0)
                    black_req = requires.get('warrior_black', 0)
                    black_prod = produces.get('warrior_black', 0)
                    
                    row['red'] = f"{red_req}/{red_prod}"
                    row['black'] = f"{black_req}/{black_prod}"
                    row['red_deficit'] = red_req > red_prod
                    row['black_deficit'] = black_req > black_prod
        
