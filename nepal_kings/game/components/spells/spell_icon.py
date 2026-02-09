import pygame
from config import settings


class SpellIcon:
    """Base class for spell icons with interactive behavior."""
    
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
        Initialize the SpellIcon.
        
        :param window: The Pygame surface on which to draw
        :param name: The name of the spell
        :param x: X-coordinate of icon center
        :param y: Y-coordinate of icon center
        :param icon_img: Colored icon image
        :param icon_gray_img: Grayscale icon image (when inactive)
        :param frame_img: Normal frame image
        :param frame_closed_img: Greyscale frame (for unbuildable)
        :param frame_hidden_img: Hidden frame (for opponent spells)
        :param glow_img: Glow effect image for active state
        :param draw_name: Whether to draw the spell name
        """
        self.window = window
        self.name = name
        self.x = x
        self.y = y
        self.glow_img = glow_img
        
        # Images and frames
        self.icon_img = icon_img
        self.icon_gray_img = icon_gray_img
        self.frame_img = self.scale_image(frame_img, settings.SPELL_FRAME_SCALE)
        self.frame_closed_img = self.scale_image(frame_closed_img, settings.SPELL_FRAME_SCALE)
        self.frame_hidden_img = self.scale_image(frame_hidden_img, settings.SPELL_FRAME_SCALE) if frame_hidden_img else self.frame_closed_img
        
        self.icon_img_big = self.scale_image(icon_img, settings.SPELL_ICON_BIG_SCALE)
        self.icon_gray_img_big = self.scale_image(icon_gray_img, settings.SPELL_ICON_BIG_SCALE)
        self.frame_img_big = self.scale_image(frame_img, settings.SPELL_ICON_BIG_SCALE)
        self.frame_closed_img_big = self.scale_image(frame_closed_img, settings.SPELL_ICON_BIG_SCALE)
        self.frame_hidden_img_big = self.scale_image(frame_hidden_img, settings.SPELL_ICON_BIG_SCALE) if frame_hidden_img else self.frame_closed_img_big
        
        # Fonts
        self.font = pygame.font.Font(settings.FONT_PATH, settings.SPELL_ICON_FONT_SIZE)
        self.font_big = pygame.font.Font(settings.FONT_PATH, settings.SPELL_ICON_FONT_BIG_SIZE)
        
        # Text surfaces
        self.text_surface = self.font.render(self.name, True, settings.SPELL_ICON_CAPTION_COLOR)
        self.text_surface_big = self.font_big.render(self.name, True, settings.SPELL_ICON_CAPTION_COLOR)
        self.text_surface_grey = self.font.render(self.name, True, (50, 50, 50))
        self.text_surface_grey_big = self.font_big.render(self.name, True, (50, 50, 50))
        
        # State variables
        self.is_active = True  # Whether spell can be cast
        self.clicked = False
        self.hovered = False
        self.draw_name = draw_name
        
        # Load glow effects
        self.load_glow_effects()
        self.set_position(x, y)
    
    def scale_image(self, image: pygame.Surface, scale_factor: float) -> pygame.Surface:
        """Scale image smoothly."""
        if image is None:
            return None
        new_width = int(image.get_width() * scale_factor)
        new_height = int(image.get_height() * scale_factor)
        
        if image.get_alpha() is not None:
            image = image.convert_alpha()
        else:
            image = image.convert()
        
        return pygame.transform.smoothscale(image, (new_width, new_height))
    
    def scale_image_total_size(
        self,
        image: pygame.Surface,
        total_width: float,
        total_height: float
    ) -> pygame.Surface:
        """Scale image to specific dimensions."""
        if image is None:
            return None
        if image.get_alpha() is not None:
            image = image.convert_alpha()
        else:
            image = image.convert()
        return pygame.transform.smoothscale(image, (int(total_width), int(total_height)))
    
    def load_glow_effects(self) -> None:
        """Load and scale glow effect images."""
        glow_black = pygame.image.load('img/game_button/glow/black.png').convert_alpha()
        glow_white = pygame.image.load('img/game_button/glow/white.png').convert_alpha()
        
        # Use provided glow image or default to yellow
        glow_active = self.glow_img if self.glow_img else pygame.image.load('img/game_button/glow/yellow.png').convert_alpha()
        
        self.glow_black = pygame.transform.smoothscale(
            glow_black,
            (settings.SPELL_ICON_GLOW_WIDTH, settings.SPELL_ICON_GLOW_WIDTH)
        )
        # Make black glow semi-transparent for layered effect
        self.glow_black.set_alpha(160)  # 0-255, lower = more transparent
        
        self.glow_active = pygame.transform.smoothscale(
            glow_active,
            (settings.SPELL_ICON_GLOW_WIDTH, settings.SPELL_ICON_GLOW_WIDTH)
        )
        self.glow_active_big = pygame.transform.smoothscale(
            glow_active,
            (settings.SPELL_ICON_GLOW_BIG_WIDTH, settings.SPELL_ICON_GLOW_BIG_WIDTH)
        )
        self.glow_white_big = pygame.transform.smoothscale(
            glow_white,
            (settings.SPELL_ICON_GLOW_BIG_WIDTH, settings.SPELL_ICON_GLOW_BIG_WIDTH)
        )
    
    def set_position(self, x: int, y: int, offset_x: int = 0, offset_y: int = 0) -> None:
        """Set the icon's position."""
        self.x = x + offset_x
        self.y = y + offset_y
    
    def collide(self) -> bool:
        """Check if mouse is over the icon."""
        mouse_pos = pygame.mouse.get_pos()
        icon_width = self.icon_img.get_width() if self.icon_img else 0
        icon_height = self.icon_img.get_height() if self.icon_img else 0
        
        return (
            self.x - icon_width // 2 < mouse_pos[0] < self.x + icon_width // 2 and
            self.y - icon_height // 2 < mouse_pos[1] < self.y + icon_height // 2
        )
    
    def handle_events(self, events) -> None:
        """Handle mouse events."""
        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self.collide():
                    self.clicked = not self.clicked
    
    def update(self) -> None:
        """Update icon state."""
        self.hovered = self.collide()
    
    def draw(self) -> None:
        """Draw the spell icon with appropriate state."""
        is_mouse_pressed = pygame.mouse.get_pressed()[0]
        shadow_offset_y = settings.get_y(0.005)
        
        # Select icon and frame based on active state
        icon_img = self.icon_img if self.is_active else self.icon_gray_img
        icon_img_big = self.icon_img_big if self.is_active else self.icon_gray_img_big
        frame_img = self.frame_img if self.is_active else self.frame_closed_img
        frame_img_big = self.frame_img_big if self.is_active else self.frame_closed_img_big
        
        # Determine drawing state
        glow_img_background = None  # For layered glow effect
        if is_mouse_pressed and self.hovered:
            # Mouse pressed on icon
            glow_img = self.glow_black
            if self.is_active:
                # Draw colored glow underneath black for castable spells
                glow_img_background = self.glow_active
            current_icon = icon_img
            current_frame = frame_img
        elif self.clicked and self.hovered:
            # Clicked and hovered
            glow_img = self.glow_white_big if not self.is_active else self.glow_active_big
            current_icon = icon_img_big
            current_frame = frame_img_big
        elif self.clicked:
            # Just clicked
            glow_img = self.glow_white_big if not self.is_active else self.glow_active_big
            current_icon = icon_img_big
            current_frame = frame_img_big
        elif self.hovered:
            # Just hovered
            glow_img = self.glow_white_big if not self.is_active else self.glow_active_big
            current_icon = icon_img_big
            current_frame = frame_img_big
        else:
            # Default state
            glow_img = self.glow_black
            if self.is_active:
                # Draw colored glow underneath black for castable spells
                glow_img_background = self.glow_active
            current_icon = icon_img
            current_frame = frame_img
        
        # Draw background glow (colored glow for castable spells in default state)
        if glow_img_background:
            glow_bg_rect = glow_img_background.get_rect(center=(self.x, self.y + shadow_offset_y))
            self.window.blit(glow_img_background, glow_bg_rect.topleft)
        
        # Draw main glow
        glow_rect = glow_img.get_rect(center=(self.x, self.y + shadow_offset_y))
        self.window.blit(glow_img, glow_rect.topleft)
        
        # Draw icon
        icon_rect = current_icon.get_rect(center=(self.x, self.y))
        self.window.blit(current_icon, icon_rect.topleft)
        
        # Draw frame (on top of icon)
        frame_rect = current_frame.get_rect(center=(self.x, self.y))
        self.window.blit(current_frame, frame_rect.topleft)
        
        # Draw name if enabled
        if self.draw_name:
            is_big = self.hovered or self.clicked
            
            # Choose text color based on castability
            if self.is_active:
                text_surface = self.text_surface_big if is_big else self.text_surface
            else:
                text_surface = self.text_surface_grey_big if is_big else self.text_surface_grey
            
            text_rect = text_surface.get_rect(center=(self.x, self.y + current_frame.get_height() // 2 + 15))
            self.window.blit(text_surface, text_rect.topleft)


class CastSpellIcon(SpellIcon):
    """Spell icon for the cast spell screen."""
    
    def __init__(self, window, game, spell_family, x: int = 0, y: int = 0) -> None:
        """
        Initialize a CastSpellIcon.
        
        :param window: The Pygame surface
        :param game: Reference to the game object
        :param spell_family: The SpellFamily object
        :param x: X-coordinate
        :param y: Y-coordinate
        """
        super().__init__(
            window,
            spell_family.name,
            x,
            y,
            spell_family.icon_img,
            spell_family.icon_gray_img,
            spell_family.frame_img,
            spell_family.frame_closed_img,
            spell_family.frame_hidden_img,
            spell_family.glow_img,
            draw_name=True,
        )
        
        self.family = spell_family
        self.game = game
        self.content = spell_family.spells
        
        # Scale images to appropriate size for cast spell screen
        self._initialize_images(spell_family, x, y)
    
    def _initialize_images(self, spell_family, x, y) -> None:
        """Initialize and scale images for cast spell screen."""
        scale_factor = 1.0
        big_scale_factor = settings.SPELL_ICON_BIG_SCALE
        
        self.icon_img = self._scale_icon(spell_family.icon_img, scale_factor)
        self.icon_gray_img = self._scale_icon(spell_family.icon_gray_img, scale_factor)
        self.frame_img = self._scale_frame(spell_family.frame_img, scale_factor)
        self.frame_closed_img = self._scale_frame(spell_family.frame_closed_img, scale_factor)
        self.frame_hidden_img = self._scale_frame(spell_family.frame_hidden_img, scale_factor)
        
        self.icon_img_big = self._scale_icon(spell_family.icon_img, big_scale_factor)
        self.icon_gray_img_big = self._scale_icon(spell_family.icon_gray_img, big_scale_factor)
        self.frame_img_big = self._scale_frame(spell_family.frame_img, big_scale_factor)
        self.frame_closed_img_big = self._scale_frame(spell_family.frame_closed_img, big_scale_factor)
        self.frame_hidden_img_big = self._scale_frame(spell_family.frame_hidden_img, big_scale_factor)
        
        self.set_position(x, y)
    
    def _scale_icon(self, image, scale_factor: float) -> pygame.Surface:
        """Scale icon image."""
        return self.scale_image_total_size(
            image,
            settings.SPELL_ICON_WIDTH * scale_factor,
            settings.SPELL_ICON_HEIGHT * scale_factor,
        )
    
    def _scale_frame(self, image, scale_factor: float) -> pygame.Surface:
        """Scale frame image."""
        return self.scale_image_total_size(
            image,
            settings.SPELL_ICON_WIDTH * scale_factor * 1.4,
            settings.SPELL_ICON_HEIGHT * scale_factor * 1.4,
        )
