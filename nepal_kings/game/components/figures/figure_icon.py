# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
import math
from collections import Counter
import copy

import pygame

from game.components.cards.card_img import CardImg
from config import settings
from game.core.input_state import get_pressed as _get_pressed

class FigureIcon:
    # Class-level cache for base glow images (loaded once for all instances)
    _glow_cache = {}
    _suit_icon_cache = {}  # Cache for suit icons
    _skill_icon_cache = {}  # Cache for skill icons
    _broken_icon_cache = {}  # Cache for broken state icon
    _advance_icon_cache = {}  # Cache for advance state icons
    
    @classmethod
    def _load_base_glow_images(cls):
        """Load base glow images once and cache them at class level."""
        if not cls._glow_cache:
            cls._glow_cache = {
                'black': pygame.image.load(settings.GAME_BUTTON_GLOW_RECT_IMG_PATH + 'black.png').convert_alpha(),
                'white': pygame.image.load(settings.GAME_BUTTON_GLOW_RECT_IMG_PATH + 'white.png').convert_alpha(),
                'yellow': pygame.image.load(settings.GAME_BUTTON_GLOW_RECT_IMG_PATH + 'yellow.png').convert_alpha(),
                'orange': pygame.image.load(settings.GAME_BUTTON_GLOW_RECT_IMG_PATH + 'orange.png').convert_alpha(),
            }
        return cls._glow_cache
    """
    A class representing an on-screen figure icon with optional animation,
    highlighting, and interactive behavior.
    """

    def __init__(
        self,
        window: pygame.Surface,
        name: str,
        x: int = 0,
        y: int = 0,
        icon_img: pygame.Surface = None,
        icon_gray_img: pygame.Surface = None,
        frame_img: pygame.Surface = None,
        frame_closed_img: pygame.Surface = None,
        frame_hidden_img: pygame.Surface = None,
        glow_img: pygame.Surface = None,
        draw_name: bool = True,
    ) -> None:
        """
        Initialize the FigureIcon.

        :param window: The Pygame surface on which to draw.
        :param name: The name of the figure/family.
        :param x: The initial x-coordinate of the icon's center.
        :param y: The initial y-coordinate of the icon's center.
        :param icon_img: The colored icon image.
        :param icon_gray_img: The gray (inactive) icon image.
        :param frame_img: The normal frame image.
        :param frame_closed_img: The closed-frame image (greyscale for build screen).
        :param frame_hidden_img: The hidden-frame image (colored for field screen foreigners).
        :param glow_img: The glow effect image.
        """
        self.window = window
        self.name = name
        self.x = x
        self.y = y

        # Images and frames
        self.icon_img = icon_img
        self.icon_gray_img = icon_gray_img
        self.frame_img = self.scale_image(frame_img, settings.FRAME_FIGURE_SCALE)
        self.frame_closed_img = self.scale_image(frame_closed_img, settings.FRAME_FIGURE_SCALE)
        self.frame_hidden_img = self.scale_image(frame_hidden_img, settings.FRAME_FIGURE_SCALE) if frame_hidden_img else self.frame_closed_img
        self.glow_img = glow_img

        self.icon_img_big = self.scale_image(icon_img, settings.FIGURE_ICON_BIG_SCALE)
        self.icon_gray_img_big = self.scale_image(icon_gray_img, settings.FIGURE_ICON_BIG_SCALE)
        self.frame_img_big = self.scale_image(frame_img, settings.FIGURE_ICON_BIG_SCALE)
        self.frame_closed_img_big = self.scale_image(frame_closed_img, settings.FIGURE_ICON_BIG_SCALE)
        self.frame_hidden_img_big = self.scale_image(frame_hidden_img, settings.FIGURE_ICON_BIG_SCALE) if frame_hidden_img else self.frame_closed_img_big

        # Fonts for text rendering
        self.font = settings.get_font(settings.FIGURE_ICON_FONT_CAPTION_FONT_SIZE)
        self.font_big = settings.get_font(settings.FIGURE_ICON_FONT_CAPTION_BIG_FONT_SIZE)

        # Text surfaces
        self.text_surface = self.font.render(self.name, True, settings.SUIT_ICON_CAPTION_COLOR)
        self.text_surface_big = self.font_big.render(self.name, True, settings.SUIT_ICON_CAPTION_COLOR)

        # State variables
        self.is_active = True
        self.clicked = False
        self.hovered = False
        self.is_visible = True  # Default to visible, can be overridden by subclasses
        self.time = 0  # Used for animations (like moving up and down)

        # Load glow effects and initialize positions
        self.load_glow_effects()
        self.set_position(x, y)

        self.draw_name = draw_name

    def scale_image(self, image: pygame.Surface, scale_factor: float) -> pygame.Surface:
        """
        Scale the image with a smooth interpolation.

        :param image: Image to be scaled.
        :param scale_factor: Factor by which to scale.
        :return: A new scaled pygame.Surface.
        """
        new_width = int(image.get_width() * scale_factor)
        new_height = int(image.get_height() * scale_factor)

        # Ensure the image is in a format compatible with smoothscale
        if image.get_alpha() is not None:
            image = image.convert_alpha()  # Preserve transparency
        else:
            image = image.convert()  # No transparency

        return pygame.transform.smoothscale(image, (new_width, new_height))

    def scale_image_total_size(
        self,
        image: pygame.Surface,
        total_width: float,
        total_height: float
    ) -> pygame.Surface:
        """
        Scale the image to fit within the total size.

        :param image: Image to be scaled.
        :param total_width: Max width for the image.
        :param total_height: Max height for the image.
        :return: A new pygame.Surface scaled to fit.
        """
        scale_factor = min(total_width / image.get_width(), total_height / image.get_height())
        return self.scale_image(image, scale_factor)

    def draw_text_with_background(self, big: bool = False, y_offset: float = 0) -> None:
        """
        Draw text with a background and frame.

        :param big: Whether to use the "big" text surface or the normal one.
        :param y_offset: Vertical offset to apply (used in hover or click animations).
        """
        if self.draw_name:
            padding = settings.FIGURE_NAME_PADDING

            if big:
                # Use the big text surface and rect
                text_surface = self.text_surface_big
                text_rect = self.text_rect_big
            else:
                # Use the regular text surface and rect
                text_surface = self.text_surface
                text_rect = self.text_rect

            # Draw background rectangle for text
            padding = settings.FIGURE_NAME_PADDING
            corner_r = settings.FIGURE_NAME_CORNER_R
            shadow_off = settings.FIGURE_NAME_SHADOW_OFFSET
            bg_rect = pygame.Rect(
                text_rect.x - padding,
                text_rect.y - padding + y_offset,
                text_rect.width + 2 * padding,
                text_rect.height + 2 * padding
            )

            # Drop shadow
            shadow_rect = bg_rect.move(shadow_off, shadow_off)
            shadow_surf = pygame.Surface((shadow_rect.w, shadow_rect.h), pygame.SRCALPHA)
            pygame.draw.rect(shadow_surf, settings.FIGURE_NAME_SHADOW_COLOR,
                             (0, 0, shadow_rect.w, shadow_rect.h), border_radius=corner_r)
            self.window.blit(shadow_surf, shadow_rect.topleft)

            # Draw background on the main window surface
            pygame.draw.rect(self.window, settings.FIGURE_NAME_BG_COLOR,
                             bg_rect, border_radius=corner_r)

            # Draw frame on the main window surface
            pygame.draw.rect(self.window, settings.FIGURE_NAME_FRAME_COLOR,
                             bg_rect, width=2, border_radius=corner_r)

            # Draw text on the main window surface
            self.window.blit(text_surface, (text_rect.topleft[0], text_rect.topleft[1] + y_offset))
        

    def load_glow_effects(self) -> None:
        """
        Load and scale all the necessary glow effects.
        Creates both bright and dark versions of colored glows.
        """
        # Load base images from class-level cache (loaded once for all instances)
        cache = self._load_base_glow_images()
        glow_black_img = cache['black']
        glow_white_img = cache['white']
        
        # Use provided glow_img or default to yellow
        glow_active = self.glow_img if self.glow_img else cache['yellow']
        
        # Scale colored glows (bright version)
        self.glow_yellow = pygame.transform.smoothscale(
            glow_active,
            (settings.FIGURE_ICON_GLOW_WIDTH, settings.FIGURE_ICON_GLOW_WIDTH)
        )
        self.glow_yellow_big = pygame.transform.smoothscale(
            glow_active,
            (settings.FIGURE_ICON_GLOW_BIG_WIDTH, settings.FIGURE_ICON_GLOW_BIG_WIDTH)
        )
        
        # Create dark version by preparing semi-transparent black overlay
        glow_black_overlay = pygame.transform.smoothscale(
            glow_black_img,
            (settings.FIGURE_ICON_GLOW_WIDTH, settings.FIGURE_ICON_GLOW_WIDTH)
        )
        glow_black_overlay.set_alpha(160)  # Semi-transparent for layering
        
        glow_black_overlay_big = pygame.transform.smoothscale(
            glow_black_img,
            (settings.FIGURE_ICON_GLOW_BIG_WIDTH, settings.FIGURE_ICON_GLOW_BIG_WIDTH)
        )
        glow_black_overlay_big.set_alpha(160)
        
        # Create dark colored glows by compositing colored glow with black overlay
        self.glow_yellow_dark = self.glow_yellow.copy()
        self.glow_yellow_dark.blit(glow_black_overlay, (0, 0))
        
        self.glow_yellow_dark_big = self.glow_yellow_big.copy()
        self.glow_yellow_dark_big.blit(glow_black_overlay_big, (0, 0))
        
        # Standard black glow (opaque)
        self.glow_black = pygame.transform.smoothscale(
            glow_black_img,
            (settings.FIGURE_ICON_GLOW_WIDTH, settings.FIGURE_ICON_GLOW_WIDTH)
        )
        
        # White glows
        self.glow_white = pygame.transform.smoothscale(
            glow_white_img,
            (settings.FIGURE_ICON_GLOW_WIDTH, settings.FIGURE_ICON_GLOW_WIDTH)
        )
        self.glow_white_big = pygame.transform.smoothscale(
            glow_white_img,
            (settings.FIGURE_ICON_GLOW_BIG_WIDTH, settings.FIGURE_ICON_GLOW_BIG_WIDTH)
        )
        
        # Keep orange glows for compatibility (deprecated - use dark colored glows instead)
        self.glow_orange = pygame.transform.smoothscale(
            cache['orange'],
            (settings.FIGURE_ICON_GLOW_WIDTH, settings.FIGURE_ICON_GLOW_WIDTH)
        )
        self.glow_orange_big = pygame.transform.smoothscale(
            cache['orange'],
            (settings.FIGURE_ICON_GLOW_BIG_WIDTH, settings.FIGURE_ICON_GLOW_BIG_WIDTH)
        )

    def set_position(
        self,
        x: int,
        y: int,
        icon_offset_x: float = 0.0,
        icon_offset_y: float = 0.0
    ) -> None:
        """
        Set the position of the figure icon and its elements.

        :param x: X-coordinate of the icon's center.
        :param y: Y-coordinate of the icon's center.
        :param icon_offset_x: Optional offset in the x-direction for the icon.
        :param icon_offset_y: Optional offset in the y-direction for the icon.
        """
        self.x = x
        self.y = y

        # Center the icon and frame
        self.rect_icon = self.icon_img.get_rect(center=(self.x + icon_offset_x, self.y + icon_offset_y))
        self.rect_frame = self.frame_img.get_rect(center=(self.x, self.y))
        self.rect_glow = self.glow_yellow.get_rect(center=(self.x, self.y))
        self.rect_icon_big = self.icon_img_big.get_rect(center=(self.x + icon_offset_x, self.y + icon_offset_y))
        self.rect_frame_big = self.frame_img_big.get_rect(center=(self.x, self.y))
        self.rect_glow_big = self.glow_yellow_big.get_rect(center=(self.x, self.y))

        # Set text positions
        self.text_rect = self.text_surface.get_rect(
            center=(self.x, self.y + 0.68 * settings.FIGURE_ICON_HEIGHT // 2)
        )
        self.text_rect_big = self.text_surface_big.get_rect(
            center=(self.x, self.y + 0.9 * settings.FIGURE_ICON_BIG_HEIGHT // 2)
        )

    def collide(self) -> bool:
        """
        Check if the mouse is hovering over the figure icon.

        :return: True if the mouse is over the icon's frame, False otherwise.
        """
        mx, my = pygame.mouse.get_pos()
        return self.rect_frame.collidepoint((mx, my))

    def draw_icon(
        self,
        x: int,
        y: int,
        width: int,
        height: int
    ) -> None:
        """
        Draw the figure icon with the provided dimensions at the given position
        in its default (inactive) state.

        :param x: The x-coordinate of the top-left corner.
        :param y: The y-coordinate of the top-left corner.
        :param width: The width to which the icon should be scaled.
        :param height: The height to which the icon should be scaled.
        """
        # Scale the icon and frame images to the provided dimensions
        icon_img = self.scale_image_total_size(self.icon_img, width, height)
        frame_img = self.scale_image_total_size(
            self.frame_img,
            width * settings.FRAME_FIGURE_SCALE,
            height * settings.FRAME_FIGURE_SCALE
        )

        # Calculate positions for icon and frame to center them
        icon_rect = icon_img.get_rect(center=(x + width // 2, y + height // 2))
        frame_rect = frame_img.get_rect(center=(x + width // 2, y + height // 2))

        # Draw the frame and icon
        self.window.blit(frame_img, frame_rect.topleft)
        self.window.blit(icon_img, icon_rect.topleft)

        # Draw text with background below the icon
        text_surface = self.font.render(self.name, True, settings.SUIT_ICON_CAPTION_COLOR)
        text_rect = text_surface.get_rect(center=(x + width // 2, y + height + settings.FIGURE_NAME_PADDING))

        # Draw background rectangle for text
        padding = settings.FIGURE_NAME_PADDING
        corner_r = settings.FIGURE_NAME_CORNER_R
        shadow_off = settings.FIGURE_NAME_SHADOW_OFFSET
        bg_rect = pygame.Rect(
            text_rect.x - padding,
            text_rect.y - padding,
            text_rect.width + 2 * padding,
            text_rect.height + 2 * padding
        )

        # Drop shadow
        shadow_rect = bg_rect.move(shadow_off, shadow_off)
        shadow_surf = pygame.Surface((shadow_rect.w, shadow_rect.h), pygame.SRCALPHA)
        pygame.draw.rect(shadow_surf, settings.FIGURE_NAME_SHADOW_COLOR,
                         (0, 0, shadow_rect.w, shadow_rect.h), border_radius=corner_r)
        self.window.blit(shadow_surf, shadow_rect.topleft)

        pygame.draw.rect(self.window, settings.FIGURE_NAME_BG_COLOR,
                         bg_rect, border_radius=corner_r)
        pygame.draw.rect(self.window, settings.FIGURE_NAME_FRAME_COLOR,
                         bg_rect, width=2, border_radius=corner_r)

        # Draw the text
        self.window.blit(text_surface, text_rect.topleft)

    def draw(self) -> None:
        """
        Draw the figure icon with the glow and animations based on the state.
        """
        y_offset = settings.FIGURE_ICON_SIN_AMPL * math.sin(self.time) if self.clicked else 0

        icon_img = self.icon_img if self.is_active else self.icon_gray_img
        icon_img_big = self.icon_img_big if self.is_active else self.icon_gray_img_big
        frame_img = self.frame_img if self.is_active else self.frame_closed_img
        frame_img_big = self.frame_img_big if self.is_active else self.frame_closed_img_big
        glow_img = self.glow_yellow if self.is_active else self.glow_black
        glow_img_big = self.glow_yellow_big if self.is_active else self.glow_white_big
        glow_img_clicked = self.glow_yellow_dark if self.is_active else self.glow_white
        glow_img_clicked_big = self.glow_yellow_dark_big if self.is_active else self.glow_white_big

        if _get_pressed()[0] and self.hovered:
            # If hovering while left mouse button pressed
            self.window.blit(glow_img_clicked, (self.rect_glow.topleft[0], self.rect_glow.topleft[1] + y_offset))
            self.window.blit(icon_img, (self.rect_icon.topleft[0], self.rect_icon.topleft[1] + y_offset))
            self.window.blit(frame_img, (self.rect_frame.topleft[0], self.rect_frame.topleft[1] + y_offset))
            self.window.blit(self.text_surface, (self.text_rect.topleft[0], self.text_rect.topleft[1] + y_offset))
            self.draw_text_with_background(y_offset=y_offset)

        elif self.clicked and self.hovered:
            # If clicked and hovering - use bright glow with big icon
            self.window.blit(glow_img_big, self.rect_glow_big.topleft)
            self.window.blit(icon_img_big, (self.rect_icon_big.topleft[0], self.rect_icon_big.topleft[1] + y_offset))
            self.window.blit(frame_img_big, (self.rect_frame_big.topleft[0], self.rect_frame_big.topleft[1] + y_offset))
            self.draw_text_with_background(big=True, y_offset=y_offset)

        elif self.clicked:
            # If clicked but not hovering - use dark colored glow
            self.window.blit(glow_img_clicked_big, self.rect_glow_big.topleft)
            self.window.blit(icon_img_big, (self.rect_icon_big.topleft[0], self.rect_icon_big.topleft[1] + y_offset))
            self.window.blit(frame_img_big, (self.rect_frame_big.topleft[0], self.rect_frame_big.topleft[1] + y_offset))
            self.draw_text_with_background(big=True, y_offset=y_offset)

        elif self.hovered:
            # If just hovering (not clicked)
            self.window.blit(glow_img_big, self.rect_glow_big.topleft)
            self.window.blit(icon_img_big, self.rect_icon_big.topleft)
            self.window.blit(frame_img_big, self.rect_frame_big.topleft)
            self.draw_text_with_background(big=True, y_offset=y_offset)

        else:
            # Default state
            self.window.blit(icon_img, self.rect_icon.topleft)
            self.window.blit(frame_img, self.rect_frame.topleft)
            self.draw_text_with_background(y_offset=y_offset)

    def update(self) -> None:
        """
        Update the animation and interaction state.
        Only allow hovering for visible figures.
        """
        if self.clicked:
            self.time += 0.1  # Animate
        else:
            self.time = 0
        self.hovered = self.collide() and self.is_visible

    def handle_events(self, events) -> None:
        """
        Handle click events for the figure icon.

        :param events: A list of pygame events.
        """
        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.hovered:
                self.clicked = not self.clicked  # Toggle clicked state


class BuildFigureIcon(FigureIcon):
    """
    A specialized FigureIcon that integrates with a game and a figure family.
    """

    def __init__(self, window, game, fig_fam, x: int = 0, y: int = 0) -> None:
        """
        Initialize a BuildFigureIcon instance.

        :param window: The Pygame surface on which to draw.
        :param game: Reference to the main game object.
        :param fig_fam: The figure family object containing relevant images and info.
        :param x: The x-coordinate of the icon's center.
        :param y: The y-coordinate of the icon's center.
        """
        super().__init__(
            window,
            fig_fam.name,
            x,
            y,
            fig_fam.icon_img_small,
            fig_fam.icon_gray_img_small,
            fig_fam.frame_img,
            fig_fam.frame_closed_img,
            fig_fam.frame_hidden_img,
            fig_fam.glow_img
        )

        self.family = fig_fam
        self.game = game
        self.content = fig_fam.figures

        # Call load_glow_effects to initialize glow attributes
        self.load_glow_effects()
        self._initialize_images(fig_fam, x, y)

    def _initialize_images(self, fig_fam, x, y) -> None:
        """
        Initialize and scale images based on field type.

        :param fig_fam: The figure family object with references to images.
        :param x: The x-coordinate of the icon's center.
        :param y: The y-coordinate of the icon's center.
        """
        castle_scale_factor = 1.3
        is_castle = fig_fam.field == "castle"
        scale_factor = castle_scale_factor if is_castle else 1
        big_scale_factor = scale_factor * settings.FIGURE_ICON_BIG_SCALE

        self.icon_img = self._scale_icon(fig_fam.icon_img_small, scale_factor)
        self.icon_gray_img = self._scale_icon(fig_fam.icon_gray_img_small, scale_factor)
        self.frame_img = self._scale_frame(fig_fam.frame_img, scale_factor)
        self.frame_closed_img = self._scale_frame(fig_fam.frame_closed_img, scale_factor)
        self.frame_hidden_img = self._scale_frame(fig_fam.frame_hidden_img, scale_factor)

        self.icon_img_big = self._scale_icon(fig_fam.icon_img_small, big_scale_factor)
        self.icon_gray_img_big = self._scale_icon(fig_fam.icon_gray_img_small, big_scale_factor)
        self.frame_img_big = self._scale_frame(fig_fam.frame_img, big_scale_factor)
        self.frame_closed_img_big = self._scale_frame(fig_fam.frame_closed_img, big_scale_factor)
        self.frame_hidden_img_big = self._scale_frame(fig_fam.frame_hidden_img, big_scale_factor)

        offset_y = settings.get_y(0.005) if is_castle else settings.get_y(0.00)
        self.set_position(x, y, -settings.get_x(0.00), offset_y)

    def _scale_icon(self, image, scale_factor: float) -> pygame.Surface:
        """
        Helper to scale icon images.

        :param image: The image to scale.
        :param scale_factor: The factor by which to scale.
        :return: The scaled image.
        """
        s = settings.BUILD_FIGURE_ICON_SCALE
        return self.scale_image_total_size(
            image,
            settings.BUILD_FIGURE_ICON_WIDTH * scale_factor * s,
            settings.BUILD_FIGURE_ICON_HEIGHT * scale_factor * s,
        )

    def _scale_frame(self, image, scale_factor: float) -> pygame.Surface:
        """
        Helper to scale frame images.

        :param image: The frame image to scale.
        :param scale_factor: The factor by which to scale.
        :return: The scaled frame image.
        """
        s = settings.BUILD_FIGURE_ICON_SCALE
        return self.scale_image_total_size(
            image,
            settings.BUILD_FIGURE_ICON_WIDTH * scale_factor * settings.FRAME_FIGURE_SCALE * s,
            settings.BUILD_FIGURE_ICON_HEIGHT * scale_factor * settings.FRAME_FIGURE_SCALE * s,
        )

    def is_in_hand(self, suit=None) -> bool:
        """
        Check if the figure can be built with the cards available in hand.

        :param suit: (Optional) Filter by suit. If None, check all suits.
        :return: True if at least one figure in this family can be built,
                 False otherwise.
        """
        if self.game is None:
            return False

        main_cards, side_cards = self.game.get_hand()
        cards = [
            (card['suit'], card['rank']) for card in (main_cards + side_cards)
            if suit is None or card['suit'] == suit
        ]

        cards_counter = Counter(cards)
        for fig in self.content:
            fig_cards_counter = Counter(fig.cards)
            if all(cards_counter[card] >= fig_cards_counter[card] for card in fig_cards_counter):
                return True
        return False

    def update(self) -> None:
        """
        Update the figure icon with game-specific logic.
        """
        super().update()
        # Uncomment if necessary:
        # self.is_active = self.is_in_hand()


class FieldFigureIcon(FigureIcon):
    """
    A FigureIcon variant for rendering a single 'figure' at a fixed position,
    with associated cards displayed relative to the figure's position.
    """

    def __init__(
        self,
        window: pygame.Surface,
        game,
        figure,
        is_visible: bool = True,
        x: int = 0,
        y: int = 0,
        all_player_figures = None,
        resources_data = None,
    ) -> None:
        # Set castle figure flag before calling super().__init__()
        # because parent's __init__ calls load_glow_effects() which we override
        self.is_castle_figure = figure.family.field == 'castle'
        
        super().__init__(
            window,
            figure.family.name,
            x,
            y,
            figure.family.icon_img_small,
            figure.family.icon_gray_img_small,
            figure.family.frame_img,
            figure.family.frame_closed_img,
            figure.family.frame_hidden_img,
            glow_img=figure.family.glow_img,
            draw_name=False,
        )
        self.game = game
        self.figure = figure
        self.family = figure.family
        self.is_visible = is_visible

        # Calculate scaling factor between normal and big icon
        self.icon_scale_factor = self.icon_img_big.get_width() / self.icon_img.get_width()

        # Precompute normal and big card images
        self.card_images_normal = [
            CardImg(
                self.window,
                card.suit,
                card.rank,
                width=settings.FIELD_FIGURE_CARD_WIDTH,
                height=settings.FIELD_FIGURE_CARD_HEIGHT,
            ) for card in figure.cards
        ]

        # Compute the big card width and height using the icon scale factor
        big_card_width = int(settings.FIELD_FIGURE_CARD_WIDTH * self.icon_scale_factor)
        big_card_height = int(settings.FIELD_FIGURE_CARD_HEIGHT * self.icon_scale_factor)

        self.card_images_big = [
            CardImg(
                self.window,
                card.suit,
                card.rank,
                width=big_card_width,
                height=big_card_height,
            ) for card in figure.cards
        ]

        # Load suit icon in both sizes
        self.suit_icon = self._load_suit_icon()
        self.suit_icon_big = self._load_suit_icon(is_big=True)
        
        # Load skill icons in both sizes
        self.skill_icons, self.skill_icons_big = self._load_skill_icons()
        
        # Create skill glow in both sizes
        base_size = int(settings.FIELD_FIGURE_CARD_HEIGHT * 0.8)
        self.skill_glow = self._create_skill_glow(base_size)
        self.skill_glow_big = self._create_skill_glow(int(base_size * self.icon_scale_factor))
        
        # Load advantage suit icon (for skills with suit_advantage)
        self.advantage_suit_icon, self.advantage_suit_icon_big = self._load_advantage_suit_icons()
        
        # Load own suit icon (for skills with suit_self)
        self.own_suit_icon, self.own_suit_icon_big = self._load_own_suit_icons()
        
        # Load broken state icon in both sizes
        self.broken_icon = self._load_broken_icon()
        self.broken_icon_big = self._load_broken_icon(is_big=True)
        
        # Calculate and cache battle bonus received (expensive operation, only do once)
        self.battle_bonus_received = self._calculate_battle_bonus_received(all_player_figures)
        
        # Check if figure has resource deficits
        self.has_deficit = self._check_resource_deficit(resources_data)
        
        # Load advance state icons (charge.png for own, charge_opponent.png for opponent)
        self.advance_icon = self._load_advance_icon(is_own=True)
        self.advance_icon_big = self._load_advance_icon(is_own=True, is_big=True)
        self.advance_icon_opponent = self._load_advance_icon(is_own=False)
        self.advance_icon_opponent_big = self._load_advance_icon(is_own=False, is_big=True)
        
        # Defender selection greyed-out state (set by field_screen during defender selection)
        self.defender_selectable = True
        self.in_defender_selection_mode = False

        # Blocks-bonus: when True the support bonus is negated (shown as red strikethrough)
        self.battle_bonus_blocked = False

        # Distance-attack: power penalty applied by an opponent's ranged attacker
        self.distance_attack_penalty = 0

        # Buffs-allies: base power bonus from allied buffers (e.g. +4)
        self.buffs_allies_bonus = 0

        # Buffs-allies-defence: support bonus from defending buffers (number card value)
        self.buffs_allies_defence_bonus = 0
        
        # Initialize glow effects and images (with larger glows for castle figures)
        self.load_glow_effects()
        self._initialize_images(self.family, x, y)

    def load_glow_effects(self) -> None:
        """
        Load and scale all the necessary glow effects.
        Kings and Maharajas (castle figures) get larger glows.
        Creates both bright and dark versions of colored glows.
        """
        # Use larger glow for castle figures (Kings and Maharajas)
        glow_scale = 1.2 if self.is_castle_figure else 1.0
        
        normal_glow_size = int(settings.FIGURE_ICON_GLOW_WIDTH * glow_scale)
        big_glow_size = int(settings.FIGURE_ICON_GLOW_BIG_WIDTH * glow_scale)
        
        # Load base images from class-level cache (shared with parent class)
        cache = self._load_base_glow_images()
        glow_black_img = cache['black']
        glow_white_img = cache['white']
        
        # Use provided glow_img or default to yellow
        glow_active = self.glow_img if self.glow_img else cache['yellow']
        
        # Scale colored glows (bright version)
        self.glow_yellow = pygame.transform.smoothscale(
            glow_active,
            (normal_glow_size, normal_glow_size)
        )
        self.glow_yellow_big = pygame.transform.smoothscale(
            glow_active,
            (big_glow_size, big_glow_size)
        )
        
        # Create dark version by preparing semi-transparent black overlay
        glow_black_overlay = pygame.transform.smoothscale(
            glow_black_img,
            (normal_glow_size, normal_glow_size)
        )
        glow_black_overlay.set_alpha(160)  # Semi-transparent for layering
        
        glow_black_overlay_big = pygame.transform.smoothscale(
            glow_black_img,
            (big_glow_size, big_glow_size)
        )
        glow_black_overlay_big.set_alpha(160)
        
        # Create dark colored glows by compositing colored glow with black overlay
        self.glow_yellow_dark = self.glow_yellow.copy()
        self.glow_yellow_dark.blit(glow_black_overlay, (0, 0))
        
        self.glow_yellow_dark_big = self.glow_yellow_big.copy()
        self.glow_yellow_dark_big.blit(glow_black_overlay_big, (0, 0))
        
        # Standard black glow (opaque)
        self.glow_black = pygame.transform.smoothscale(
            glow_black_img,
            (normal_glow_size, normal_glow_size)
        )
        
        # White glows for hidden figures
        self.glow_white = pygame.transform.smoothscale(
            glow_white_img,
            (normal_glow_size, normal_glow_size)
        )
        self.glow_white_big = pygame.transform.smoothscale(
            glow_white_img,
            (big_glow_size, big_glow_size)
        )
        
        # Keep orange glows for compatibility
        self.glow_orange = pygame.transform.smoothscale(
            cache['orange'],
            (normal_glow_size, normal_glow_size)
        )
        self.glow_orange_big = pygame.transform.smoothscale(
            cache['orange'],
            (big_glow_size, big_glow_size)
        )

    def draw(self, x: int, y: int) -> None:
        """
        Draw the figure icon at the specified position, along with its cards.
        """
        self.set_position(x, y)

        # Shadow offset for glow effect (shift downwards) - relative to icon size
        shadow_offset_y = int(settings.FIELD_ICON_WIDTH * 0.08)

        # Determine states
        is_mouse_pressed = _get_pressed()[0]
        is_default_state = not self.hovered and not self.clicked

        # Draw the figure icon
        if self.is_visible:
            # Check if greyed out for defender selection or resting after battle
            is_resting = (hasattr(self, 'game') and self.game and
                          hasattr(self, 'figure') and self.figure and
                          self.figure.id in (getattr(self.game, 'resting_figure_ids', None) or []))
            greyed_out = (hasattr(self, 'defender_selectable') and not self.defender_selectable) or is_resting or self.has_deficit
            
            # Choose icon/frame images based on greyed-out state
            icon_normal = self.icon_gray_img if greyed_out else self.icon_img
            icon_big = self.icon_gray_img_big if greyed_out else self.icon_img_big
            frame_normal = self.frame_closed_img if greyed_out else self.frame_img
            frame_big = self.frame_closed_img_big if greyed_out else self.frame_img_big
            glow_default = self.glow_black if greyed_out else self.glow_yellow_dark
            glow_hover = self.glow_white_big if greyed_out else self.glow_yellow_big
            glow_click_big = self.glow_black if greyed_out else self.glow_yellow_dark_big
            
            if is_default_state:
                # Default state: dark colored glow
                glow_rect = glow_default.get_rect(center=(self.x, self.y + shadow_offset_y))
                self.window.blit(glow_default, glow_rect.topleft)
                # Draw icon and frame
                self.window.blit(icon_normal, self.rect_icon.topleft)
                self.window.blit(frame_normal, self.rect_frame.topleft)
            elif self.hovered and not is_mouse_pressed:
                # Hovered (not clicked): bright glow with big icon
                glow_rect = glow_hover.get_rect(center=(self.x, self.y + shadow_offset_y))
                self.window.blit(glow_hover, glow_rect.topleft)
                self.window.blit(icon_big, self.rect_icon_big.topleft)
                self.window.blit(frame_big, self.rect_frame_big.topleft)
            elif self.clicked:
                # Clicked state: dark glow with big icon
                if is_mouse_pressed and self.hovered:
                    # Being pressed: use normal size with dark glow
                    glow_rect = glow_default.get_rect(center=(self.x, self.y + shadow_offset_y))
                    self.window.blit(glow_default, glow_rect.topleft)
                    self.window.blit(icon_normal, self.rect_icon.topleft)
                    self.window.blit(frame_normal, self.rect_frame.topleft)
                else:
                    # Clicked but not being pressed: big size with dark glow
                    glow_rect = glow_click_big.get_rect(center=(self.x, self.y + shadow_offset_y))
                    self.window.blit(glow_click_big, glow_rect.topleft)
                    self.window.blit(icon_big, self.rect_icon_big.topleft)
                    self.window.blit(frame_big, self.rect_frame_big.topleft)
        else:
            # For hidden figures: white glow for hover, black otherwise
            # Check if greyed out for defender selection
            greyed_out_hidden = hasattr(self, 'defender_selectable') and not self.defender_selectable
            is_big_state = self.hovered and not is_mouse_pressed
            
            if greyed_out_hidden:
                # Non-selectable hidden figure: use greyscale hidden frame
                glow_img = self.glow_black
                glow_rect = glow_img.get_rect(center=(self.x, self.y + shadow_offset_y))
                self.window.blit(glow_img, glow_rect.topleft)
                frame_img = self.frame_hidden_grey_img_big if is_big_state else self.frame_hidden_grey_img
                frame_rect = frame_img.get_rect(center=(self.x, self.y))
                self.window.blit(frame_img, frame_rect.topleft)
            else:
                if is_big_state:
                    # Hovered: white glow
                    glow_img = self.glow_white_big
                    glow_rect = glow_img.get_rect(center=(self.x, self.y + shadow_offset_y))
                else:
                    # Default: black glow
                    glow_img = self.glow_black
                    glow_rect = glow_img.get_rect(center=(self.x, self.y + shadow_offset_y))
                self.window.blit(glow_img, glow_rect.topleft)
                
                frame_img = self.frame_hidden_img_big if is_big_state else self.frame_hidden_img
                frame_rect = frame_img.get_rect(center=(self.x, self.y))
                self.window.blit(frame_img, frame_rect.topleft)
        
        # Draw broken state icon if figure has resource deficits (only for visible figures)
        if self.is_visible and self.has_deficit:
            # Determine which broken icon to use based on state
            is_big_for_broken = (not (is_mouse_pressed and self.hovered)) and (self.clicked or self.hovered)
            broken_icon = self.broken_icon_big if is_big_for_broken else self.broken_icon
            
            if broken_icon:
                # Calculate position for top-left corner of the frame
                # Get the frame rect to position relative to it
                frame_rect = self.rect_frame_big if is_big_for_broken else self.rect_frame
                # Position at top-left corner of frame
                broken_x = frame_rect.left
                broken_y = frame_rect.top
                self.window.blit(broken_icon, (broken_x, broken_y))

        # Draw advance overlay icon if this figure is advancing or defending
        # Show for both visible and hidden figures (including Civil War second picks)
        # Skip if show_advance_overlay is explicitly disabled (e.g. in dialogue boxes)
        if self.game and getattr(self, 'show_advance_overlay', True):
            advancing_id = getattr(self.game, 'advancing_figure_id', None)
            advancing_id_2 = getattr(self.game, 'advancing_figure_id_2', None)
            defending_id = getattr(self.game, 'defending_figure_id', None)
            defending_id_2 = getattr(self.game, 'defending_figure_id_2', None)
            
            is_advancing = (advancing_id == self.figure.id) or (advancing_id_2 == self.figure.id)
            is_defending = (defending_id == self.figure.id) or (defending_id_2 == self.figure.id)
            
            if is_advancing or is_defending:
                if self.is_visible:
                    is_big_for_advance = (not (is_mouse_pressed and self.hovered)) and (self.clicked or self.hovered)
                    frame_rect = self.rect_frame_big if is_big_for_advance else self.rect_frame
                else:
                    # For hidden figures, compute frame rect from hidden frame
                    is_big_state = self.hovered and not is_mouse_pressed
                    frame_img_adv = self.frame_hidden_img_big if is_big_state else self.frame_hidden_img
                    frame_rect = frame_img_adv.get_rect(center=(self.x, self.y))
                    is_big_for_advance = is_big_state
                
                # Determine if it's own or opponent figure
                is_own = (self.figure.player_id == self.game.player_id)
                if is_big_for_advance:
                    advance_icon = self.advance_icon_big if is_own else self.advance_icon_opponent_big
                else:
                    advance_icon = self.advance_icon if is_own else self.advance_icon_opponent
                
                if advance_icon:
                    # Own figures: top-right corner; opponent figures: top-left corner
                    if is_own:
                        adv_x = frame_rect.right - advance_icon.get_width()
                    else:
                        adv_x = frame_rect.left
                    adv_y = frame_rect.top
                    self.window.blit(advance_icon, (adv_x, adv_y))

        # Draw figure name and cards together in a box
        self.draw_figure_info()

    def draw_figure_info(self) -> None:
        """Draw figure name and info (power, bonus, suit, skills) in a single horizontal line."""
        # Determine text to display
        if self.is_visible:
            text = self.figure.name
        else:
            text = "foreigner"

        # Determine if we're in "big" state to match icon scaling exactly
        is_mouse_pressed = _get_pressed()[0]
        
        if self.is_visible:
            # Match parent FigureIcon.draw() logic exactly:
            # Big when NOT(pressing AND hovered) AND (clicked OR hovered)
            is_big_state = (not (is_mouse_pressed and self.hovered)) and (self.clicked or self.hovered)
        else:
            # For non-visible figures: big only when hovered and not pressing
            is_big_state = self.hovered and not is_mouse_pressed

        # Use appropriate font based on state
        font = self.font_big if is_big_state else self.font
        text_surface = font.render(text, True, settings.SUIT_ICON_CAPTION_COLOR)

        # Scale spacing and padding based on state
        scale_factor = self.icon_scale_factor if is_big_state else 1.0
        padding = int(settings.FIGURE_NAME_PADDING * scale_factor)
        element_spacing = int(4 * scale_factor)  # Spacing between icons in info row
        
        # Calculate default icon size for enchantments (based on suit icon sizing)
        base_size = int(settings.FIELD_FIGURE_CARD_HEIGHT * 0.8)
        default_icon_size = int(base_size * 0.95)  # Slightly smaller than suit icon
        if is_big_state:
            default_icon_size = int(default_icon_size * self.icon_scale_factor)
        
        # Check for active enchantments (for both visible and hidden figures)
        has_enchantments = hasattr(self.figure, 'active_enchantments') and len(self.figure.active_enchantments) > 0
        enchantment_icons = []
        enchantment_modifier = 0
        enchantment_modifier_surface = None
        enchantment_modifier_outline = None
        
        if has_enchantments:
            # Calculate total enchantment modifier
            enchantment_modifier = self.figure.get_total_enchantment_modifier()
            
            # Create purple modifier text with outline
            modifier_text = f"({enchantment_modifier:+d})"  # Shows +6 or -6
            enchantment_modifier_outline = font.render(modifier_text, True, (0, 0, 0))
            enchantment_modifier_surface = font.render(modifier_text, True, (150, 50, 200))  # Purple color
            
            # Load enchantment spell icons at default icon size
            for enchantment in self.figure.active_enchantments:
                icon_filename = enchantment.get('spell_icon', '')
                if icon_filename:
                    icon = self._load_enchantment_icon(icon_filename, is_big=is_big_state, target_size=default_icon_size)
                    if icon:
                        enchantment_icons.append(icon)
        
        # Only show power/suit for visible figures; show skills for both
        # Get skill icons for current state (needed for both visible and hidden)
        skill_icon_dict = self.skill_icons_big if is_big_state else self.skill_icons
        
        # Collect skill icons to display (for both visible and hidden figures)
        skills_to_display = []
        if hasattr(self.figure, 'get_active_skill_keys'):
            skills_to_display = self.figure.get_active_skill_keys()
        else:
            from game.components.figures.family_configs.skill_config import SKILL_KEYS
            skills_to_display = [k for k in SKILL_KEYS if getattr(self.figure, k, False)]
        
        # Get skill icon size from the actual pre-scaled icons
        skill_icon_size = 0
        if skills_to_display and skills_to_display[0] in skill_icon_dict:
            skill_icon_size = skill_icon_dict[skills_to_display[0]].get_height()
        
        # Get skill glow for current state
        skill_glow = self.skill_glow_big if is_big_state else self.skill_glow
        
        # Determine which skills show a suit icon behind them
        from game.components.figures.family_configs.skill_config import SKILL_DEFINITIONS as _SKILL_DEFS
        adv_suit_icon = self.advantage_suit_icon_big if is_big_state else self.advantage_suit_icon
        own_suit_icon = self.own_suit_icon_big if is_big_state else self.own_suit_icon
        adv_suit_icon_size = adv_suit_icon.get_width() if adv_suit_icon else 0
        suit_adv_skill_count = 0
        if adv_suit_icon:
            suit_adv_skill_count = sum(
                1 for k in skills_to_display if _SKILL_DEFS.get(k, {}).get('suit_advantage', False)
            )
        
        if self.is_visible:
            # Calculate power display
            base_power = self.figure.get_value()
            battle_bonus = self.battle_bonus_received  # Use cached value (calculated once in __init__)
            
            # Create power text
            power_text = f"{base_power}"
            power_surface = font.render(power_text, True, settings.SUIT_ICON_CAPTION_COLOR)

            # Create buffs-allies bonus text if applicable (same color as base power)
            buffs_allies_surface = None
            buffs_allies_bonus = getattr(self, 'buffs_allies_bonus', 0)
            if buffs_allies_bonus > 0:
                buffs_allies_surface = font.render(f"+{buffs_allies_bonus}", True, settings.SUIT_ICON_CAPTION_COLOR)

            # Create buffs-allies-defence bonus text if applicable (same color as base power)
            defence_bonus_surface = None
            defence_bonus = getattr(self, 'buffs_allies_defence_bonus', 0)
            if defence_bonus > 0:
                defence_bonus_surface = font.render(f"+{defence_bonus}", True, settings.SUIT_ICON_CAPTION_COLOR)
            
            # Create bonus text if applicable
            bonus_surface = None
            bonus_outline_surface = None
            bonus_blocked = getattr(self, 'battle_bonus_blocked', False)
            if battle_bonus > 0:
                bonus_text = f"(+{battle_bonus})"
                # Create outline for better contrast
                bonus_outline_surface = font.render(bonus_text, True, (0, 0, 0))
                # Always green — the red strikethrough dash indicates it's blocked
                bonus_surface = font.render(bonus_text, True, settings.COLOR_BATTLE_BONUS)
            
            # Create distance-attack penalty text if applicable
            distance_penalty_surface = None
            distance_penalty_outline = None
            distance_penalty = getattr(self, 'distance_attack_penalty', 0)
            if distance_penalty > 0:
                dp_text = f"(-{distance_penalty})"
                distance_penalty_outline = font.render(dp_text, True, (0, 0, 0))
                distance_penalty_surface = font.render(dp_text, True, (255, 140, 40))  # orange
            
            # Get suit icon for current state
            suit_icon = self.suit_icon_big if is_big_state else self.suit_icon
            icon_size = suit_icon.get_height() if suit_icon else int(settings.FIELD_FIGURE_CARD_HEIGHT * 0.8 * scale_factor)
            
            # Calculate total width of info row: power + buff + defence + bonus + distance penalty + enchantment + suit + skills + enchantment icons
            info_row_width = power_surface.get_width()
            if buffs_allies_surface:
                info_row_width += element_spacing + buffs_allies_surface.get_width()
            if defence_bonus_surface:
                info_row_width += element_spacing + defence_bonus_surface.get_width()
            if bonus_surface:
                info_row_width += element_spacing + bonus_surface.get_width()
            if distance_penalty_surface:
                info_row_width += element_spacing + distance_penalty_surface.get_width()
            if has_enchantments and enchantment_modifier_surface:
                info_row_width += element_spacing + enchantment_modifier_surface.get_width()
            if suit_icon:
                info_row_width += element_spacing + icon_size
            if skills_to_display and skill_icon_size > 0:
                skills_width = len(skills_to_display) * skill_icon_size + (len(skills_to_display) - 1) * element_spacing
                info_row_width += element_spacing + skills_width
            if has_enchantments and enchantment_icons:
                info_row_width += element_spacing + (len(enchantment_icons) * default_icon_size + (len(enchantment_icons) - 1) * element_spacing)
            
            # Info section height: single row only
            info_padding = int(padding * settings.FIGURE_NAME_INFO_PADDING_SCALE)
            info_height = max(power_surface.get_height(), icon_size, skill_icon_size if skill_icon_size > 0 else 0) + 2 * info_padding
            
            # Calculate box width
            box_width = max(text_surface.get_width(), info_row_width) + 2 * padding
        else:
            # For hidden figures, determine what to show.
            # Village figures: hide skills (would reveal identity);
            # other fields (castle, military): show skills.
            _is_village = (hasattr(self.figure, 'family') and
                           getattr(self.figure.family, 'field', '') == 'village')
            _show_skills = skills_to_display and not _is_village
            has_info = _show_skills or has_enchantments
            if has_info:
                # Calculate width for info row
                hidden_info_row_width = 0
                
                # Add skill icons width (non-village only)
                if _show_skills and skill_icon_size > 0:
                    skills_width = len(skills_to_display) * skill_icon_size + (len(skills_to_display) - 1) * element_spacing
                    hidden_info_row_width += skills_width
                
                # Add enchantment modifier
                if has_enchantments and enchantment_modifier_surface:
                    if hidden_info_row_width > 0:
                        hidden_info_row_width += element_spacing
                    hidden_info_row_width += enchantment_modifier_surface.get_width()
                
                # Add enchantment icons
                if has_enchantments and enchantment_icons:
                    if hidden_info_row_width > 0:
                        hidden_info_row_width += element_spacing
                    hidden_info_row_width += len(enchantment_icons) * default_icon_size + (len(enchantment_icons) - 1) * element_spacing
                
                box_width = max(text_surface.get_width(), hidden_info_row_width) + 2 * padding
                info_height = max(
                    skill_icon_size if (_show_skills and skill_icon_size > 0) else 0,
                    default_icon_size if enchantment_icons else 0,
                    enchantment_modifier_surface.get_height() if enchantment_modifier_surface else 0
                ) + 2 * padding
            else:
                # No skills or enchantments, only show name
                box_width = text_surface.get_width() + 2 * padding
                info_height = 0
        
        # Calculate y-offset for the info box
        base_offset = 0.9 if is_big_state else 0.68
        height_reference = settings.FIGURE_ICON_BIG_HEIGHT if is_big_state else settings.FIGURE_ICON_HEIGHT
        info_box_center_y = self.y + base_offset * height_reference // 2
        
        # Position text at the top of the info box
        text_y = info_box_center_y
        
        # Create text background box
        text_padding = int(padding * settings.FIGURE_NAME_TEXT_PADDING_SCALE)
        text_box_height = text_surface.get_height() + 2 * text_padding
        text_bg_rect = pygame.Rect(
            int(self.x - box_width // 2),
            int(text_y - text_surface.get_height() // 2 - text_padding),
            int(box_width),
            int(text_box_height)
        )
        
        # Create info background box (slightly darker) if visible or has enchantments
        corner_r = settings.FIGURE_NAME_CORNER_R
        shadow_off = settings.FIGURE_NAME_SHADOW_OFFSET

        if info_height > 0:
            info_bg_rect = pygame.Rect(
                int(self.x - box_width // 2),
                int(text_bg_rect.bottom),
                int(box_width),
                int(info_height)
            )
            
            total_bg_rect = pygame.Rect(
                text_bg_rect.x,
                text_bg_rect.y,
                text_bg_rect.width,
                text_bg_rect.height + info_bg_rect.height
            )

            # Drop shadow
            shadow_rect = total_bg_rect.move(shadow_off, shadow_off)
            shadow_surf = pygame.Surface((shadow_rect.w, shadow_rect.h), pygame.SRCALPHA)
            pygame.draw.rect(shadow_surf, settings.FIGURE_NAME_SHADOW_COLOR,
                             (0, 0, shadow_rect.w, shadow_rect.h), border_radius=corner_r)
            self.window.blit(shadow_surf, shadow_rect.topleft)

            # Name section background
            name_surf = pygame.Surface((text_bg_rect.w, text_bg_rect.h), pygame.SRCALPHA)
            pygame.draw.rect(name_surf, settings.FIGURE_NAME_BG_COLOR,
                             (0, 0, text_bg_rect.w, text_bg_rect.h),
                             border_top_left_radius=corner_r, border_top_right_radius=corner_r)
            self.window.blit(name_surf, text_bg_rect.topleft)

            # Info section background (darker parchment)
            info_surf = pygame.Surface((info_bg_rect.w, info_bg_rect.h), pygame.SRCALPHA)
            pygame.draw.rect(info_surf, settings.FIGURE_NAME_INFO_BG_COLOR,
                             (0, 0, info_bg_rect.w, info_bg_rect.h),
                             border_bottom_left_radius=corner_r, border_bottom_right_radius=corner_r)
            self.window.blit(info_surf, info_bg_rect.topleft)
            
            # Soft separator line
            pygame.draw.line(
                self.window, 
                settings.FIGURE_NAME_SEP_COLOR, 
                (text_bg_rect.left + 2, text_bg_rect.bottom), 
                (text_bg_rect.right - 2, text_bg_rect.bottom),
                1
            )
            
            # Outer border
            pygame.draw.rect(self.window, settings.FIGURE_NAME_FRAME_COLOR,
                             total_bg_rect, width=2, border_radius=corner_r)
        else:
            # Drop shadow
            shadow_rect = text_bg_rect.move(shadow_off, shadow_off)
            shadow_surf = pygame.Surface((shadow_rect.w, shadow_rect.h), pygame.SRCALPHA)
            pygame.draw.rect(shadow_surf, settings.FIGURE_NAME_SHADOW_COLOR,
                             (0, 0, shadow_rect.w, shadow_rect.h), border_radius=corner_r)
            self.window.blit(shadow_surf, shadow_rect.topleft)

            # Only draw text box for hidden figures
            pygame.draw.rect(self.window, settings.FIGURE_NAME_BG_COLOR,
                             text_bg_rect, border_radius=corner_r)
            pygame.draw.rect(self.window, settings.FIGURE_NAME_FRAME_COLOR,
                             text_bg_rect, width=2, border_radius=corner_r)
        
        # Draw text centered
        text_rect = text_surface.get_rect(center=(self.x, text_y))
        self.window.blit(text_surface, text_rect.topleft)
        
        # Draw info section for visible figures - all in a single horizontal row
        if self.is_visible:
            # Calculate vertical center for the single info row
            info_center_y = text_bg_rect.bottom + info_height // 2
            
            # Start from left side of the row
            current_x = self.x - info_row_width // 2
            
            # Draw power
            power_y = info_center_y - power_surface.get_height() // 2
            self.window.blit(power_surface, (current_x, power_y))
            current_x += power_surface.get_width()

            # Draw buffs-allies bonus if applicable (same color as base power)
            if buffs_allies_surface:
                current_x += element_spacing
                ba_y = info_center_y - buffs_allies_surface.get_height() // 2
                self.window.blit(buffs_allies_surface, (current_x, ba_y))
                current_x += buffs_allies_surface.get_width()

            # Draw buffs-allies-defence bonus if applicable (same color as base power)
            if defence_bonus_surface:
                current_x += element_spacing
                db_y = info_center_y - defence_bonus_surface.get_height() // 2
                self.window.blit(defence_bonus_surface, (current_x, db_y))
                current_x += defence_bonus_surface.get_width()
            
            # Draw bonus if applicable (with outline for better contrast)
            if bonus_surface:
                current_x += element_spacing
                bonus_y = info_center_y - bonus_surface.get_height() // 2
                # Draw outline (black) in 4 directions for better visibility
                if bonus_outline_surface:
                    for offset_x, offset_y in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
                        self.window.blit(bonus_outline_surface, (current_x + offset_x, bonus_y + offset_y))
                # Draw main text on top (red if blocked, green otherwise)
                self.window.blit(bonus_surface, (current_x, bonus_y))
                # Draw red strikethrough line if bonus is blocked
                if bonus_blocked:
                    strike_y = bonus_y + bonus_surface.get_height() // 2
                    pygame.draw.line(self.window, (220, 60, 60),
                                     (current_x - 1, strike_y),
                                     (current_x + bonus_surface.get_width() + 1, strike_y), 2)
                current_x += bonus_surface.get_width()
            
            # Draw distance-attack penalty if applicable (orange, with outline)
            if distance_penalty_surface:
                current_x += element_spacing
                dp_y = info_center_y - distance_penalty_surface.get_height() // 2
                if distance_penalty_outline:
                    for offset_x, offset_y in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
                        self.window.blit(distance_penalty_outline, (current_x + offset_x, dp_y + offset_y))
                self.window.blit(distance_penalty_surface, (current_x, dp_y))
                current_x += distance_penalty_surface.get_width()
            
            # Draw enchantment modifier if applicable (purple, with outline)
            if has_enchantments and enchantment_modifier_surface:
                current_x += element_spacing
                enchant_y = info_center_y - enchantment_modifier_surface.get_height() // 2
                # Draw outline (black) in 4 directions
                if enchantment_modifier_outline:
                    for offset_x, offset_y in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
                        self.window.blit(enchantment_modifier_outline, (current_x + offset_x, enchant_y + offset_y))
                # Draw main purple text on top
                self.window.blit(enchantment_modifier_surface, (current_x, enchant_y))
                current_x += enchantment_modifier_surface.get_width()
            
            # Draw suit icon
            if suit_icon:
                current_x += element_spacing
                suit_y = info_center_y - suit_icon.get_height() // 2
                self.window.blit(suit_icon, (current_x, suit_y))
                current_x += suit_icon.get_width()
            
            # Draw skill icons
            if skills_to_display:
                current_x += element_spacing
                for i, skill_key in enumerate(skills_to_display):
                    if i > 0:
                        current_x += element_spacing
                    
                    if skill_key in skill_icon_dict:
                        skill_icon = skill_icon_dict[skill_key]
                        # No runtime scaling needed - use pre-scaled icon
                        skill_y = info_center_y - skill_icon.get_height() // 2
                        # Draw white glow behind skill icon
                        if skill_glow:
                            glow_x = current_x + (skill_icon.get_width() - skill_glow.get_width()) // 2
                            glow_y = skill_y + (skill_icon.get_height() - skill_glow.get_height()) // 2
                            self.window.blit(skill_glow, (glow_x, glow_y))
                        # Draw suit advantage icon behind skill icon (background), centered
                        if adv_suit_icon and _SKILL_DEFS.get(skill_key, {}).get('suit_advantage', False):
                            adv_x = current_x + (skill_icon.get_width() - adv_suit_icon.get_width()) // 2
                            adv_y = skill_y + (skill_icon.get_height() - adv_suit_icon.get_height()) // 2
                            self.window.blit(adv_suit_icon, (adv_x, adv_y))
                        # Draw skill icon on top
                        self.window.blit(skill_icon, (current_x, skill_y))
                        current_x += skill_icon.get_width()
            
            # Draw enchantment spell icons
            if has_enchantments and enchantment_icons:
                current_x += element_spacing
                for i, enchant_icon in enumerate(enchantment_icons):
                    if i > 0:
                        current_x += element_spacing
                    icon_y = info_center_y - enchant_icon.get_height() // 2
                    self.window.blit(enchant_icon, (current_x, icon_y))
                    current_x += enchant_icon.get_width()
        
        # Draw skills and enchantments for hidden figures
        elif not self.is_visible and (skills_to_display or has_enchantments):
            # Village hidden figures: hide skills (identity leak).
            # Other fields: show skills normally.
            _is_village = (hasattr(self.figure, 'family') and
                           getattr(self.figure.family, 'field', '') == 'village')
            _show_skills = skills_to_display and not _is_village

            if not _show_skills and not has_enchantments:
                pass  # nothing to draw – badge was collapsed
            else:
                # Calculate vertical center for the info row
                info_center_y = text_bg_rect.bottom + info_height // 2

                # Calculate total row width for centering
                hidden_info_row_width = 0
                if _show_skills and skill_icon_size > 0:
                    skills_width = len(skills_to_display) * skill_icon_size + (len(skills_to_display) - 1) * element_spacing
                    hidden_info_row_width += skills_width
                if has_enchantments and enchantment_modifier_surface:
                    if hidden_info_row_width > 0:
                        hidden_info_row_width += element_spacing
                    hidden_info_row_width += enchantment_modifier_surface.get_width()
                if has_enchantments and enchantment_icons:
                    if hidden_info_row_width > 0:
                        hidden_info_row_width += element_spacing
                    hidden_info_row_width += len(enchantment_icons) * default_icon_size + (len(enchantment_icons) - 1) * element_spacing

                # Start from left side of the row
                current_x = self.x - hidden_info_row_width // 2

                # Draw skill icons (non-village only)
                if _show_skills and skill_icon_size > 0:
                    for i, skill_key in enumerate(skills_to_display):
                        if i > 0:
                            current_x += element_spacing
                        if skill_key in skill_icon_dict:
                            skill_icon = skill_icon_dict[skill_key]
                            icon_y = info_center_y - skill_icon.get_height() // 2
                            self.window.blit(skill_icon, (current_x, icon_y))
                            current_x += skill_icon_size

                # Draw enchantment modifier
                if has_enchantments and enchantment_modifier_surface:
                    if _show_skills and skill_icon_size > 0:
                        current_x += element_spacing
                    enchant_y = info_center_y - enchantment_modifier_surface.get_height() // 2
                    if enchantment_modifier_outline:
                        for offset_x, offset_y in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
                            self.window.blit(enchantment_modifier_outline, (current_x + offset_x, enchant_y + offset_y))
                    self.window.blit(enchantment_modifier_surface, (current_x, enchant_y))
                    current_x += enchantment_modifier_surface.get_width()

                # Draw enchantment spell icons
                if has_enchantments and enchantment_icons:
                    if enchantment_modifier_surface or (_show_skills and skill_icon_size > 0):
                        current_x += element_spacing
                    for i, enchant_icon in enumerate(enchantment_icons):
                        if i > 0:
                            current_x += element_spacing
                        icon_y = info_center_y - enchant_icon.get_height() // 2
                        self.window.blit(enchant_icon, (current_x, icon_y))
                        current_x += enchant_icon.get_width()

    def update(self) -> None:
        """
        Override update to include hover detection and interaction for cards.
        Only allow hovering for visible figures.
        """
        # Allow hovering for visible figures always; for hidden figures only during defender selection
        self.hovered = self.collide() and (self.is_visible or self.in_defender_selection_mode)

    def _initialize_images(self, fig_fam, x, y) -> None:
        """
        Initialize and scale images based on field type.

        :param fig_fam: The figure family object with references to images.
        :param x: The x-coordinate of the icon's center.
        :param y: The y-coordinate of the icon's center.
        """
        castle_scale_factor = 1.2
        is_castle = fig_fam.field == "castle"
        scale_factor = castle_scale_factor if is_castle else 1
        big_scale_factor = scale_factor * settings.FIGURE_ICON_BIG_SCALE

        self.icon_img = self._scale_icon(fig_fam.icon_img_small, scale_factor)
        self.icon_gray_img = self._scale_icon(fig_fam.icon_gray_img_small, scale_factor)
        self.frame_img = self._scale_frame(fig_fam.frame_img, scale_factor)
        self.frame_closed_img = self._scale_frame(fig_fam.frame_closed_img, scale_factor)
        self.frame_hidden_img = self._scale_frame(fig_fam.frame_hidden_img, scale_factor)
        # Greyscale hidden frames for non-selectable hidden figures
        if hasattr(fig_fam, 'frame_hidden_greyscale_img') and fig_fam.frame_hidden_greyscale_img:
            self.frame_hidden_grey_img = self._scale_frame(fig_fam.frame_hidden_greyscale_img, scale_factor)
        else:
            self.frame_hidden_grey_img = self.frame_hidden_img

        self.icon_img_big = self._scale_icon(fig_fam.icon_img_small, big_scale_factor)
        self.icon_gray_img_big = self._scale_icon(fig_fam.icon_gray_img_small, big_scale_factor)
        self.frame_img_big = self._scale_frame(fig_fam.frame_img, big_scale_factor)
        self.frame_closed_img_big = self._scale_frame(fig_fam.frame_closed_img, big_scale_factor)
        self.frame_hidden_img_big = self._scale_frame(fig_fam.frame_hidden_img, big_scale_factor)
        if hasattr(fig_fam, 'frame_hidden_greyscale_img') and fig_fam.frame_hidden_greyscale_img:
            self.frame_hidden_grey_img_big = self._scale_frame(fig_fam.frame_hidden_greyscale_img, big_scale_factor)
        else:
            self.frame_hidden_grey_img_big = self.frame_hidden_img_big

        offset_y = settings.get_y(0.005) if is_castle else settings.get_y(0.00)
        self.set_position(x, y, -settings.get_x(0.00), offset_y)

    def _load_suit_icon(self, is_big=False):
        """Load the suit icon for the figure in either normal or big size."""
        try:
            suit_map = {
                'clubs': 'clubs.png',
                'diamonds': 'diamonds.png',
                'hearts': 'hearts.png',
                'spades': 'spades.png'
            }
            suit_file = suit_map.get(self.figure.suit.lower())
            if suit_file:
                # Check cache first
                cache_key = suit_file
                if cache_key not in self._suit_icon_cache:
                    suit_path = settings.SUIT_ICON_IMG_PATH + suit_file
                    self._suit_icon_cache[cache_key] = pygame.image.load(suit_path).convert_alpha()
                
                suit_img = self._suit_icon_cache[cache_key]
                # Scale to appropriate size for field view
                base_size = int(settings.FIELD_FIGURE_CARD_HEIGHT * 0.8)
                if is_big:
                    icon_size = int(base_size * self.icon_scale_factor)
                else:
                    icon_size = base_size
                return pygame.transform.smoothscale(suit_img, (icon_size, icon_size))
        except Exception as e:
            print(f"[FIELD_ICON] Failed to load suit icon: {e}")
        return None
    
    def _load_skill_icons(self):
        """Load and scale skill icons for combat attributes in both normal and big sizes."""
        from game.components.figures.family_configs.skill_config import SKILL_ICON_IMG_PATH_DICT
        skill_icons_normal = {}
        skill_icons_big = {}
        
        # Calculate icon sizes based on suit icon sizing for consistency
        base_size = int(settings.FIELD_FIGURE_CARD_HEIGHT * 0.8)
        normal_size = int(base_size * 1.0)  # Slightly smaller than suit icon
        big_size = int(normal_size * self.icon_scale_factor)
        
        for skill_key, icon_path in SKILL_ICON_IMG_PATH_DICT.items():
            try:
                # Check cache first
                if skill_key not in self._skill_icon_cache:
                    # Load original high-res icon once and cache it
                    self._skill_icon_cache[skill_key] = pygame.image.load(icon_path).convert_alpha()
                
                icon = self._skill_icon_cache[skill_key]
                # Create both sizes from the cached original
                skill_icons_normal[skill_key] = pygame.transform.smoothscale(icon, (normal_size, normal_size))
                skill_icons_big[skill_key] = pygame.transform.smoothscale(icon, (big_size, big_size))
            except Exception as e:
                print(f"[FIELD_ICON] Failed to load skill icon '{skill_key}': {e}")
        
        return skill_icons_normal, skill_icons_big
    
    @staticmethod
    def _create_skill_glow(size):
        """Create a soft white radial glow surface for skill icons."""
        glow_size = int(size * 1.5)
        glow_surface = pygame.Surface((glow_size, glow_size), pygame.SRCALPHA)
        center = glow_size // 2
        radius = glow_size // 2
        for r in range(radius, 0, -1):
            alpha = int(120 * (1 - (r / radius) ** 1.5))
            pygame.draw.circle(glow_surface, (255, 255, 255, alpha), (center, center), r)
        return glow_surface
    
    def _load_advantage_suit_icons(self):
        """Load the suit icon that this figure has an advantage over, sized to match skill icons."""
        from game.components.figures.family_configs.skill_config import get_advantage_suit
        adv_suit = get_advantage_suit(getattr(self.figure, 'suit', None) or '')
        if not adv_suit:
            return None, None
        suit_file = adv_suit.lower() + '.png'
        try:
            cache_key = f'advantage_{suit_file}'
            if cache_key not in self._suit_icon_cache:
                suit_path = settings.SUIT_ICON_IMG_PATH + suit_file
                self._suit_icon_cache[cache_key] = pygame.image.load(suit_path).convert_alpha()
            suit_img = self._suit_icon_cache[cache_key]
            # Slightly smaller than skill icon for centered overlay
            base_size = int(settings.FIELD_FIGURE_CARD_HEIGHT * 0.8)
            normal_size = int(base_size * 0.85)
            big_size = int(normal_size * self.icon_scale_factor)
            return (
                pygame.transform.smoothscale(suit_img, (normal_size, normal_size)),
                pygame.transform.smoothscale(suit_img, (big_size, big_size)),
            )
        except Exception as e:
            print(f"[FIELD_ICON] Failed to load advantage suit icon '{suit_file}': {e}")
            return None, None

    def _load_own_suit_icons(self):
        """Load the figure's OWN suit icon, sized to match skill icons.

        Used for skills with ``suit_self=True`` (e.g. buffs_allies) where the
        skill icon is overlaid on the owner's suit rather than the advantage
        suit.
        """
        own_suit = getattr(self.figure, 'suit', None) or ''
        if not own_suit:
            return None, None
        suit_file = own_suit.lower() + '.png'
        try:
            cache_key = f'own_{suit_file}'
            if cache_key not in self._suit_icon_cache:
                suit_path = settings.SUIT_ICON_IMG_PATH + suit_file
                self._suit_icon_cache[cache_key] = pygame.image.load(suit_path).convert_alpha()
            suit_img = self._suit_icon_cache[cache_key]
            base_size = int(settings.FIELD_FIGURE_CARD_HEIGHT * 0.8)
            normal_size = int(base_size * 0.85)
            big_size = int(normal_size * self.icon_scale_factor)
            return (
                pygame.transform.smoothscale(suit_img, (normal_size, normal_size)),
                pygame.transform.smoothscale(suit_img, (big_size, big_size)),
            )
        except Exception as e:
            print(f"[FIELD_ICON] Failed to load own suit icon '{suit_file}': {e}")
            return None, None

    def _load_enchantment_icon(self, icon_filename, is_big=False, target_size=None):
        """
        Load and scale an enchantment spell icon.
        
        :param icon_filename: Filename of the spell icon (e.g., 'poisson_portion.png')
        :param is_big: Whether to load big or normal size
        :param target_size: Optional target size to match (e.g., skill_icon_size)
        :return: Scaled pygame Surface or None if loading fails
        """
        # Use target_size if provided, otherwise calculate like skill icons
        if target_size is None:
            base_size = int(settings.FIELD_FIGURE_CARD_HEIGHT * 0.8)
            normal_size = int(base_size * 0.85)
            icon_size = int(normal_size * self.icon_scale_factor) if is_big else normal_size
        else:
            icon_size = target_size
        
        try:
            # Spell icons are in img/spells/icons/
            icon_path = f'img/spells/icons/{icon_filename}'
            icon = pygame.image.load(icon_path).convert_alpha()
            return pygame.transform.smoothscale(icon, (icon_size, icon_size))
        except Exception as e:
            print(f"[FIELD_ICON] Failed to load enchantment icon '{icon_filename}': {e}")
            return None
    
    def _load_broken_icon(self, is_big=False):
        """Load the broken state icon for figures with resource deficits."""
        try:
            # Check cache first
            cache_key = 'broken.png'
            if cache_key not in self._broken_icon_cache:
                broken_path = 'img/figures/state_icons/broken.png'
                self._broken_icon_cache[cache_key] = pygame.image.load(broken_path).convert_alpha()
            
            broken_img = self._broken_icon_cache[cache_key]
            # Size to fit in top left corner of icon
            base_size = int(settings.FIELD_ICON_WIDTH * 0.25)
            if is_big:
                icon_size = int(base_size * self.icon_scale_factor)
            else:
                icon_size = base_size
            return pygame.transform.smoothscale(broken_img, (icon_size, icon_size))
        except Exception as e:
            print(f"[FIELD_ICON] Failed to load broken icon: {e}")
        return None
    
    def _load_advance_icon(self, is_own=True, is_big=False):
        """Load the advance state icon overlay (charge.png for own, charge_opponent.png for opponent)."""
        try:
            filename = 'charge.png' if is_own else 'charge_opponent.png'
            if filename not in self._advance_icon_cache:
                icon_path = f'img/figures/state_icons/{filename}'
                self._advance_icon_cache[filename] = pygame.image.load(icon_path).convert_alpha()
            
            advance_img = self._advance_icon_cache[filename]
            # Size to fit in top corner of icon; larger on mobile
            base_size = int(settings.FIELD_ICON_WIDTH * settings.ADVANCE_ICON_SCALE)
            if is_big:
                icon_size = int(base_size * self.icon_scale_factor)
            else:
                icon_size = base_size
            return pygame.transform.smoothscale(advance_img, (icon_size, icon_size))
        except Exception as e:
            print(f"[FIELD_ICON] Failed to load advance icon: {e}")
        return None
    
    def draw_icon(self, x: int, y: int, width: int, height: int) -> None:
        """
        Draw the figure icon with full details (power, skills, enchantments) for dialogue boxes.
        This is called by the dialogue box to render the figure in a specified area.
        
        :param x: X position (top-left)
        :param y: Y position (top-left)  
        :param width: Width of the area
        :param height: Height of the area
        """
        # Temporarily set position and draw in default state
        old_hovered = self.hovered
        old_clicked = self.clicked
        old_visible = self.is_visible
        self.hovered = False
        self.clicked = False
        # Only reveal hidden opponent figures if the player has All Seeing Eye active.
        # Own figures (already is_visible=True) are unaffected.
        if not self.is_visible and self.game and hasattr(self.game, 'has_active_all_seeing_eye'):
            self.is_visible = self.game.has_active_all_seeing_eye()
        
        # Calculate center position from top-left and dimensions
        center_x = x + width // 2
        center_y = y + height // 2
        
        # Draw the figure at the specified position
        self.draw(center_x, center_y)
        
        # Restore original state
        self.hovered = old_hovered
        self.clicked = old_clicked
        self.is_visible = old_visible
    
    def _check_resource_deficit(self, resources_data=None):
        """Check if this figure has any required resources that are in deficit."""
        try:
            # Only check for own figures that require resources
            if not hasattr(self.figure, 'requires') or not self.figure.requires:
                return False
            
            # If resources data not provided, try to calculate it
            if resources_data is None:
                from game.components.figures.figure_manager import FigureManager
                figure_manager = FigureManager()
                families = figure_manager.families
                resources_data = self.game.calculate_resources(families)
            
            if resources_data is None:
                return False
            
            produces = resources_data.get('produces', {})
            requires = resources_data.get('requires', {})
            
            # Check each resource this figure requires
            for resource_name, amount in self.figure.requires.items():
                total_required = requires.get(resource_name, 0)
                total_produced = produces.get(resource_name, 0)
                if total_required > total_produced:
                    return True  # At least one deficit found
            
            return False
        except Exception as e:
            return False
    
    def _calculate_battle_bonus_received(self, all_player_figures=None):
        """Calculate battle bonus this figure receives from other figures of the same suit."""
        try:
            # If figures not provided, fetch them (fallback for compatibility)
            if all_player_figures is None:
                # Import here to avoid circular imports
                from game.components.figures.figure_manager import FigureManager
                
                # Get all families
                figure_manager = FigureManager()
                families = figure_manager.families
                
                # Get all figures for this player
                all_player_figures = self.game.get_figures(families, is_opponent=False)
            
            # Determine this figure's type
            current_figure_type = self.figure.family.field if hasattr(self.figure.family, 'field') else None
            
            # Determine which figure types can provide bonus to this figure
            if current_figure_type == 'castle':
                # Castle gets bonus from other castle figures only
                valid_types = ['castle']
            elif current_figure_type == 'village':
                # Village gets bonus from castle figures only
                valid_types = ['castle']
            elif current_figure_type == 'military':
                # Military gets bonus from castle + village figures
                valid_types = ['castle', 'village']
            else:
                # Unknown type, no bonus
                valid_types = []
            
            # Filter for same suit, valid types, excluding current figure (important!)
            same_suit_figures = [
                fig for fig in all_player_figures 
                if (fig.suit == self.figure.suit and 
                    fig.id != self.figure.id and
                    hasattr(fig.family, 'field') and
                    fig.family.field in valid_types)
            ]
            
            # Sum battle bonuses from other figures
            total_bonus = sum(fig.get_battle_bonus() for fig in same_suit_figures)
            return total_bonus
        except Exception as e:
            # If anything fails, just return 0
            print(f"[FIELD_ICON] Failed to calculate battle bonus: {e}")
            return 0

    def _scale_icon(self, image, scale_factor: float) -> pygame.Surface:
        """
        Helper to scale icon images.

        :param image: The image to scale.
        :param scale_factor: The factor by which to scale.
        :return: The scaled image.
        """
        s = settings.FIELD_FIGURE_ICON_SCALE
        return self.scale_image_total_size(
            image,
            settings.FIELD_ICON_WIDTH * scale_factor * s,
            settings.FIELD_ICON_WIDTH * scale_factor * s,
        )

    def _scale_frame(self, image, scale_factor: float) -> pygame.Surface:
        """
        Helper to scale frame images.

        :param image: The frame image to scale.
        :param scale_factor: The factor by which to scale.
        :return: The scaled frame image.
        """
        s = settings.FIELD_FIGURE_ICON_SCALE
        return self.scale_image_total_size(
            image,
            settings.FIELD_ICON_WIDTH * scale_factor * settings.FRAME_FIGURE_SCALE * s,
            settings.FIELD_ICON_WIDTH * scale_factor * settings.FRAME_FIGURE_SCALE * s,
        )
