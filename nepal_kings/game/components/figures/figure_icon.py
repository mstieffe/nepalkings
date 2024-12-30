import math
from collections import Counter

import pygame

from config import settings


class FigureIcon:
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
        :param frame_closed_img: The closed-frame image.
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

        self.icon_img_big = self.scale_image(icon_img, settings.FIGURE_ICON_BIG_SCALE)
        self.icon_gray_img_big = self.scale_image(icon_gray_img, settings.FIGURE_ICON_BIG_SCALE)
        self.frame_img_big = self.scale_image(frame_img, settings.FIGURE_ICON_BIG_SCALE)
        self.frame_closed_img_big = self.scale_image(frame_closed_img, settings.FIGURE_ICON_BIG_SCALE)

        # Fonts for text rendering
        self.font = pygame.font.Font(settings.FONT_PATH, settings.FIGURE_ICON_FONT_CAPTION_FONT_SIZE)
        self.font_big = pygame.font.Font(settings.FONT_PATH, settings.FIGURE_ICON_FONT_CAPTION_BIG_FONT_SIZE)

        # Text surfaces
        self.text_surface = self.font.render(self.name, True, settings.SUIT_ICON_CAPTION_COLOR)
        self.text_surface_big = self.font_big.render(self.name, True, settings.SUIT_ICON_CAPTION_COLOR)

        # State variables
        self.is_active = True
        self.clicked = False
        self.hovered = False
        self.time = 0  # Used for animations (like moving up and down)

        # Load glow effects and initialize positions
        self.load_glow_effects()
        self.set_position(x, y)

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
        padding = settings.FIGURE_NAME_PADDING

        if big:
            # Use the big text surface and rect
            text_surface = self.text_surface_big
            text_rect = self.text_rect_big
        else:
            # Use the regular text surface and rect
            text_surface = self.text_surface
            text_rect = self.text_rect

        # Calculate the rectangle for the background
        bg_rect = pygame.Rect(
            text_rect.x - padding,
            text_rect.y - padding + y_offset,
            text_rect.width + 2 * padding,
            text_rect.height + 2 * padding
        )

        # Draw background on the main window surface
        pygame.draw.rect(self.window, settings.FIGURE_NAME_BG_COLOR, bg_rect)

        # Draw frame on the main window surface
        pygame.draw.rect(self.window, settings.FIGURE_NAME_FRAME_COLOR, bg_rect, width=2)

        # Draw text on the main window surface
        self.window.blit(text_surface, (text_rect.topleft[0], text_rect.topleft[1] + y_offset))

    def load_glow_effects(self) -> None:
        """
        Load and scale all the necessary glow effects.
        """
        self.glow_yellow = pygame.transform.smoothscale(
            pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH + 'yellow.png'),
            (settings.FIGURE_ICON_GLOW_WIDTH, settings.FIGURE_ICON_GLOW_WIDTH)
        )
        self.glow_yellow_big = pygame.transform.smoothscale(
            pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH + 'yellow.png'),
            (settings.FIGURE_ICON_GLOW_BIG_WIDTH, settings.FIGURE_ICON_GLOW_BIG_WIDTH)
        )
        self.glow_black = pygame.transform.smoothscale(
            pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH + 'black.png'),
            (settings.FIGURE_ICON_GLOW_WIDTH, settings.FIGURE_ICON_GLOW_WIDTH)
        )
        self.glow_orange_big = pygame.transform.smoothscale(
            pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH + 'orange.png'),
            (settings.FIGURE_ICON_GLOW_BIG_WIDTH, settings.FIGURE_ICON_GLOW_BIG_WIDTH)
        )
        self.glow_white_big = pygame.transform.smoothscale(
            pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH + 'white.png'),
            (settings.FIGURE_ICON_GLOW_BIG_WIDTH, settings.FIGURE_ICON_GLOW_BIG_WIDTH)
        )
        self.glow_orange = pygame.transform.smoothscale(
            pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH + 'orange.png'),
            (settings.FIGURE_ICON_GLOW_WIDTH, settings.FIGURE_ICON_GLOW_WIDTH)
        )
        self.glow_white = pygame.transform.smoothscale(
            pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH + 'white.png'),
            (settings.FIGURE_ICON_GLOW_WIDTH, settings.FIGURE_ICON_GLOW_WIDTH)
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
        self.rect_glow_big = self.glow_orange_big.get_rect(center=(self.x, self.y))

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
        bg_rect = pygame.Rect(
            text_rect.x - padding,
            text_rect.y - padding,
            text_rect.width + 2 * padding,
            text_rect.height + 2 * padding
        )
        pygame.draw.rect(self.window, settings.FIGURE_NAME_BG_COLOR, bg_rect)
        pygame.draw.rect(self.window, settings.FIGURE_NAME_FRAME_COLOR, bg_rect, width=2)

        # Draw the text
        self.window.blit(text_surface, text_rect.topleft)

    def draw(self) -> None:
        """
        Draw the figure icon with the glow and animations based on the state.
        """
        y_offset = settings.FIGURE_ICON_SIN_AMPL * math.sin(self.time) if self.clicked else 0

        icon_img = self.icon_img if self.is_active else self.icon_gray_img
        icon_img_big = self.icon_img_big if self.is_active else self.icon_gray_img_big
        glow_img = self.glow_yellow if self.is_active else self.glow_black
        glow_img_big = self.glow_yellow_big if self.is_active else self.glow_white_big
        glow_img_clicked = self.glow_orange if self.is_active else self.glow_white

        if pygame.mouse.get_pressed()[0] and self.hovered:
            # If hovering while left mouse button pressed
            self.window.blit(glow_img_clicked, (self.rect_glow.topleft[0], self.rect_glow.topleft[1] + y_offset))
            self.window.blit(icon_img, (self.rect_icon.topleft[0], self.rect_icon.topleft[1] + y_offset))
            self.window.blit(self.frame_img, (self.rect_frame.topleft[0], self.rect_frame.topleft[1] + y_offset))
            self.window.blit(self.text_surface, (self.text_rect.topleft[0], self.text_rect.topleft[1] + y_offset))
            self.draw_text_with_background(y_offset=y_offset)

        elif self.clicked and self.hovered:
            # If clicked and hovering
            self.window.blit(glow_img_clicked, (self.rect_glow.topleft[0], self.rect_glow.topleft[1] + y_offset))
            self.window.blit(icon_img_big, (self.rect_icon_big.topleft[0], self.rect_icon_big.topleft[1] + y_offset))
            self.window.blit(self.frame_img_big, (self.rect_frame_big.topleft[0], self.rect_frame_big.topleft[1] + y_offset))
            self.draw_text_with_background(big=True, y_offset=y_offset)

        elif self.clicked:
            # If clicked but not hovering
            self.window.blit(glow_img_clicked, (self.rect_glow.topleft[0], self.rect_glow.topleft[1] + y_offset))
            self.window.blit(icon_img_big, (self.rect_icon.topleft[0], self.rect_icon.topleft[1] + y_offset))
            self.window.blit(self.frame_img, (self.rect_frame.topleft[0], self.rect_frame.topleft[1] + y_offset))
            self.draw_text_with_background(y_offset=y_offset)

        elif self.hovered:
            # If just hovering (not clicked)
            self.window.blit(glow_img_big, self.rect_glow_big.topleft)
            self.window.blit(icon_img_big, self.rect_icon_big.topleft)
            self.window.blit(self.frame_img_big, self.rect_frame_big.topleft)
            self.draw_text_with_background(big=True, y_offset=y_offset)

        else:
            # Default state
            self.window.blit(icon_img, self.rect_icon.topleft)
            self.window.blit(self.frame_img, self.rect_frame.topleft)
            self.draw_text_with_background(y_offset=y_offset)

    def update(self) -> None:
        """
        Update the animation and interaction state.
        """
        if self.clicked:
            self.time += 0.1  # Animate
        else:
            self.time = 0
        self.hovered = self.collide()

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
            fig_fam.icon_img,
            fig_fam.icon_gray_img,
            fig_fam.frame_img,
            fig_fam.frame_closed_img
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

        self.icon_img = self._scale_icon(fig_fam.icon_img, scale_factor)
        self.icon_gray_img = self._scale_icon(fig_fam.icon_gray_img, scale_factor)
        self.frame_img = self._scale_frame(fig_fam.frame_img, scale_factor)
        self.frame_closed_img = self._scale_frame(fig_fam.frame_closed_img, scale_factor)

        self.icon_img_big = self._scale_icon(fig_fam.icon_img, big_scale_factor)
        self.icon_gray_img_big = self._scale_icon(fig_fam.icon_gray_img, big_scale_factor)
        self.frame_img_big = self._scale_frame(fig_fam.frame_img, big_scale_factor)
        self.frame_closed_img_big = self._scale_frame(fig_fam.frame_closed_img, big_scale_factor)

        offset_y = settings.get_y(0.005) if is_castle else settings.get_y(0.00)
        self.set_position(x, y, -settings.get_x(0.00), offset_y)

    def _scale_icon(self, image, scale_factor: float) -> pygame.Surface:
        """
        Helper to scale icon images.

        :param image: The image to scale.
        :param scale_factor: The factor by which to scale.
        :return: The scaled image.
        """
        return self.scale_image_total_size(
            image,
            settings.BUILD_FIGURE_ICON_WIDTH * scale_factor,
            settings.BUILD_FIGURE_ICON_HEIGHT * scale_factor,
        )

    def _scale_frame(self, image, scale_factor: float) -> pygame.Surface:
        """
        Helper to scale frame images.

        :param image: The frame image to scale.
        :param scale_factor: The factor by which to scale.
        :return: The scaled frame image.
        """
        return self.scale_image_total_size(
            image,
            settings.BUILD_FIGURE_ICON_WIDTH * scale_factor * settings.FRAME_FIGURE_SCALE,
            settings.BUILD_FIGURE_ICON_HEIGHT * scale_factor * settings.FRAME_FIGURE_SCALE,
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
    without the sinusoidal animation.
    """

    def __init__(
        self,
        window: pygame.Surface,
        game,
        figure,
        x: int = 0,
        y: int = 0,
    ) -> None:
        """
        :param window: The Pygame surface on which to draw.
        :param figure: The specific figure object. Must have a .family attribute.
        :param x: The initial x-coordinate of the icon's center.
        :param y: The initial y-coordinate of the icon's center.
        """
        # Instead of fig_fam, we pass figure, which has figure.family.
        super().__init__(
            window,
            figure.family.name,
            x,
            y,
            figure.family.icon_img,
            figure.family.icon_gray_img,
            figure.family.frame_img,
            figure.family.frame_closed_img
        )
        self.game = game
        self.figure = figure
        self.family = figure.family  # As requested

        # Call load_glow_effects to initialize glow attributes
        self.load_glow_effects()
        self._initialize_images(self.family, x, y)

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

        self.icon_img = self._scale_icon(fig_fam.icon_img, scale_factor)
        self.icon_gray_img = self._scale_icon(fig_fam.icon_gray_img, scale_factor)
        self.frame_img = self._scale_frame(fig_fam.frame_img, scale_factor)
        self.frame_closed_img = self._scale_frame(fig_fam.frame_closed_img, scale_factor)

        self.icon_img_big = self._scale_icon(fig_fam.icon_img, big_scale_factor)
        self.icon_gray_img_big = self._scale_icon(fig_fam.icon_gray_img, big_scale_factor)
        self.frame_img_big = self._scale_frame(fig_fam.frame_img, big_scale_factor)
        self.frame_closed_img_big = self._scale_frame(fig_fam.frame_closed_img, big_scale_factor)

        offset_y = settings.get_y(0.005) if is_castle else settings.get_y(0.00)
        self.set_position(x, y, -settings.get_x(0.00), offset_y)

    def _scale_icon(self, image, scale_factor: float) -> pygame.Surface:
        """
        Helper to scale icon images.

        :param image: The image to scale.
        :param scale_factor: The factor by which to scale.
        :return: The scaled image.
        """
        return self.scale_image_total_size(
            image,
            settings.FIELD_ICON_WIDTH * scale_factor * 0.45,
            settings.FIELD_ICON_WIDTH * scale_factor * 0.45,
        )

    def _scale_frame(self, image, scale_factor: float) -> pygame.Surface:
        """
        Helper to scale frame images.

        :param image: The frame image to scale.
        :param scale_factor: The factor by which to scale.
        :return: The scaled frame image.
        """
        return self.scale_image_total_size(
            image,
            settings.FIELD_ICON_WIDTH * scale_factor* 0.8,
            settings.FIELD_ICON_WIDTH * scale_factor* 0.8,
        )

    def draw(self, x: int, y: int) -> None:
        """
        Draw this icon at a *specific* (x, y) position with no sinusoidal movement.

        :param x: The x-coordinate at which to draw the icon.
        :param y: The y-coordinate at which to draw the icon.
        """
        # Override the parent's draw method so we can place
        # this icon at the given position and remove the 'time' sinus offset.
        self.set_position(x, y)

        # Everything else mirrors the parent's draw, except we eliminate y_offset.
        icon_img = self.icon_img if self.is_active else self.icon_gray_img
        icon_img_big = self.icon_img_big if self.is_active else self.icon_gray_img_big
        glow_img = self.glow_yellow if self.is_active else self.glow_black
        glow_img_big = self.glow_yellow_big if self.is_active else self.glow_white_big
        glow_img_clicked = self.glow_orange if self.is_active else self.glow_white

        # We always use y_offset = 0 (no sinus movement)
        y_offset = 0

        if pygame.mouse.get_pressed()[0] and self.hovered:
            self.window.blit(glow_img_clicked, (self.rect_glow.x, self.rect_glow.y))
            self.window.blit(icon_img, (self.rect_icon.x, self.rect_icon.y))
            self.window.blit(self.frame_img, (self.rect_frame.x, self.rect_frame.y))
            self.window.blit(self.text_surface, (self.text_rect.x, self.text_rect.y))
            self.draw_text_with_background(y_offset=y_offset)

        elif self.clicked and self.hovered:
            self.window.blit(glow_img_clicked, (self.rect_glow.x, self.rect_glow.y))
            self.window.blit(icon_img_big, (self.rect_icon_big.x, self.rect_icon_big.y))
            self.window.blit(self.frame_img_big, (self.rect_frame_big.x, self.rect_frame_big.y))
            self.draw_text_with_background(big=True, y_offset=y_offset)

        elif self.clicked:
            self.window.blit(glow_img_clicked, (self.rect_glow.x, self.rect_glow.y))
            self.window.blit(icon_img_big, (self.rect_icon.x, self.rect_icon.y))
            self.window.blit(self.frame_img, (self.rect_frame.x, self.rect_frame.y))
            self.draw_text_with_background(y_offset=y_offset)

        elif self.hovered:
            self.window.blit(glow_img_big, self.rect_glow_big.topleft)
            self.window.blit(icon_img_big, self.rect_icon_big.topleft)
            self.window.blit(self.frame_img_big, self.rect_frame_big.topleft)
            self.draw_text_with_background(big=True, y_offset=y_offset)

        else:
            self.window.blit(icon_img, self.rect_icon.topleft)
            self.window.blit(self.frame_img, self.rect_frame.topleft)
            self.draw_text_with_background(y_offset=y_offset)

    def update(self) -> None:
        """
        Override the update to skip sinus-based animation.
        (We still keep hover detection and clicked logic.)
        """
        # We do not increment self.time for sinus movement.
        # Everything else remains the same.
        self.hovered = self.collide()