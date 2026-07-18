# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
import pygame
from config import settings
from config.screen_settings import _UI_SCALE, _IS_MOBILE
from game.core.input_state import get_pressed as _get_pressed
from game.components.picker_ui import draw_caption_cell


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
        fixed_size: bool = False,
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
        self.font = settings.get_font(settings.SPELL_ICON_FONT_SIZE)
        self.font_big = settings.get_font(settings.SPELL_ICON_FONT_BIG_SIZE)
        
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
        self.visible = True
        # Stable caption cells prevent long spell names from colliding with
        # adjacent icons.  Picker screens can override this after layout.
        self.caption_max_width = int(0.096 * settings.SCREEN_WIDTH)
        # Fixed-size cells: hover/selected feedback via glow only, the
        # icon/frame footprint never changes (used by the prelude picker).
        self.fixed_size = fixed_size
        # Compact grid mode tightens the caption gap so the desktop "all
        # families on one page" layout fits three category rows cleanly.
        self.grid_mode = False

        # Load glow effects
        self.load_glow_effects()
        self.set_position(x, y)
    
    def rescale(self, factor: float) -> None:
        """Shrink the icon/frame/glow footprint in place (dense grids).

        Called once at construction time for the desktop all-families page so
        three category rows fit; the semi-transparent black glow keeps its
        layering alpha after the rescale.
        """
        if factor == 1.0:
            return

        def _s(img):
            if img is None:
                return None
            w = max(1, int(img.get_width() * factor))
            h = max(1, int(img.get_height() * factor))
            return pygame.transform.smoothscale(img, (w, h))

        for attr in (
            'icon_img', 'icon_gray_img', 'frame_img', 'frame_closed_img',
            'frame_hidden_img', 'icon_img_big', 'icon_gray_img_big',
            'frame_img_big', 'frame_closed_img_big', 'frame_hidden_img_big',
            'glow_black', 'glow_active', 'glow_active_big', 'glow_white_big',
        ):
            img = getattr(self, attr, None)
            if img is not None:
                setattr(self, attr, _s(img))
        if getattr(self, 'glow_black', None) is not None:
            self.glow_black.set_alpha(160)

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
        if not self.visible:
            return False
        mouse_pos = pygame.mouse.get_pos()
        frame_width = self.frame_img.get_width() if self.frame_img else 0
        frame_height = self.frame_img.get_height() if self.frame_img else 0
        hit_w = max(frame_width, settings.TOUCH_TARGET_MIN)
        hit_h = max(frame_height, settings.TOUCH_TARGET_MIN)
        return pygame.Rect(0, 0, hit_w, hit_h).move(
            self.x - hit_w // 2, self.y - hit_h // 2).collidepoint(mouse_pos)
    
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
        if not self.visible:
            return
        is_mouse_pressed = _get_pressed()[0]
        shadow_offset_y = settings.get_y(0.005)
        
        # Select icon and frame based on active state
        icon_img = self.icon_img if self.is_active else self.icon_gray_img
        icon_img_big = self.icon_img_big if self.is_active else self.icon_gray_img_big
        frame_img = self.frame_img if self.is_active else self.frame_closed_img
        frame_img_big = self.frame_img_big if self.is_active else self.frame_closed_img_big
        if self.fixed_size:
            # Hover/selected states keep the normal footprint.
            icon_img_big = icon_img
            frame_img_big = frame_img
        
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
            if _IS_MOBILE:
                _name_gap = 3
            elif self.grid_mode:
                _name_gap = 5
            else:
                _name_gap = 15
            draw_caption_cell(
                self.window,
                self.name,
                self.x,
                self.y + frame_img.get_height() // 2 + _name_gap,
                self.caption_max_width,
                color=settings.SPELL_ICON_CAPTION_COLOR,
                inactive=not self.is_active,
                selected=self.clicked,
                preferred_size=settings.SPELL_ICON_FONT_SIZE,
            )


class CastSpellIcon(SpellIcon):
    """Spell icon for the cast spell screen."""

    def __init__(self, window, game, spell_family, x: int = 0, y: int = 0,
                 fixed_size: bool = False) -> None:
        """
        Initialize a CastSpellIcon.

        :param window: The Pygame surface
        :param game: Reference to the game object
        :param spell_family: The SpellFamily object
        :param x: X-coordinate
        :param y: Y-coordinate
        :param fixed_size: Keep the icon footprint constant across states
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
            fixed_size=fixed_size,
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
