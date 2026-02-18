"""
Simple figure image class for displaying figure icons in dialogue boxes.
Similar to CardImg but for figures - shows only the icon without stats/info.
"""
import pygame
from config import settings


class FigureImg:
    """Simple figure image display for dialogue boxes."""
    
    def __init__(self, window, figure, width=None, height=None):
        """
        Initialize a simple figure image.
        
        :param window: Pygame window to draw on
        :param figure: Figure object or figure family
        :param width: Optional width override
        :param height: Optional height override
        """
        self.window = window
        self.figure = figure
        
        # Default size similar to card size for dialogue boxes
        if width is None:
            width = settings.CARD_WIDTH
        if height is None:
            height = settings.CARD_HEIGHT
        
        self.width = width
        self.height = height
        
        # Load figure icon and frame
        # Access the figure's family to get the icon
        if hasattr(figure, 'family'):
            family = figure.family
        else:
            # Figure might already be a family
            family = figure
        
        # Get the colored icon (already loaded as pygame.Surface in family)
        try:
            if hasattr(family, 'icon_img') and family.icon_img:
                self.icon_img = family.icon_img.copy()
            else:
                raise AttributeError("Family has no icon_img")
        except Exception as e:
            print(f"[FigureImg] Failed to get icon: {e}")
            # Create a placeholder
            self.icon_img = pygame.Surface((width, height))
            self.icon_img.fill((100, 100, 100))
        
        # Get frame (already loaded as pygame.Surface in family)
        try:
            if hasattr(family, 'frame_img') and family.frame_img:
                self.frame_img = family.frame_img.copy()
            else:
                self.frame_img = None
        except Exception as e:
            print(f"[FigureImg] Failed to get frame: {e}")
            self.frame_img = None
        
        # Scale images to requested size
        self.icon_img = pygame.transform.smoothscale(self.icon_img, (width, height))
        if self.frame_img:
            self.frame_img = pygame.transform.smoothscale(self.frame_img, (width, height))
    
    def draw_icon(self, x, y, width=None, height=None):
        """
        Draw the figure icon at specified position.
        
        :param x: X position
        :param y: Y position
        :param width: Optional width override
        :param height: Optional height override
        """
        # Use provided dimensions or default to initialization size
        draw_width = int(width) if width is not None else self.width
        draw_height = int(height) if height is not None else self.height
        
        # Scale if different from current size
        if draw_width != self.width or draw_height != self.height:
            icon = pygame.transform.smoothscale(self.icon_img, (draw_width, draw_height))
            if self.frame_img:
                frame = pygame.transform.smoothscale(self.frame_img, (draw_width, draw_height))
            else:
                frame = None
        else:
            icon = self.icon_img
            frame = self.frame_img
        
        # Draw icon first, then frame on top
        self.window.blit(icon, (x, y))
        if frame:
            self.window.blit(frame, (x, y))
