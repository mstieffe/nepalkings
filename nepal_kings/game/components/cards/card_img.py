import pygame
from pygame.locals import *
from config import settings

class CardImg():
    # Class-level cache for card images (loaded once for all instances)
    _card_image_cache = {}
    
    def __init__(self, window, suit, rank, width=None, height=None):
        self.window = window
        self.suit = suit
        self.rank = rank

        self.front_img_path = f"{settings.CARD_IMG_PATH}{settings.SUIT_TO_IMG_PATH[self.suit]}{settings.RANK_TO_IMG_PATH[self.rank]}.png"
        self.back_img_path = f"{settings.CARD_IMG_PATH}back.png"

        # Load from cache or disk
        if self.front_img_path not in self._card_image_cache:
            self._card_image_cache[self.front_img_path] = pygame.image.load(self.front_img_path)
        if self.back_img_path not in self._card_image_cache:
            self._card_image_cache[self.back_img_path] = pygame.image.load(self.back_img_path)
        
        self.front_img = self._card_image_cache[self.front_img_path]
        self.back_img = self._card_image_cache[self.back_img_path]

        if width == None:
            width = settings.CARD_WIDTH
        if height == None:
            height = settings.CARD_HEIGHT

        self.front_img = pygame.transform.smoothscale(self.front_img, (width, height))
        self.back_img = pygame.transform.smoothscale(self.back_img, (width, height))

        self.black_overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        self.black_overlay.fill((0, 0, 0, settings.ALPHA_OVERLAY)) # RGBA

        self.missing_overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        self.missing_overlay.fill((0, 0, 0, settings.ALPHA_MISSING_OVERLAY)) # RGBA

        # Load red cross from cache or disk
        if 'red_cross' not in self._card_image_cache:
            self._card_image_cache['red_cross'] = pygame.image.load(settings.RED_CROSS_IMG_PATH)
        red_cross_base = self._card_image_cache['red_cross']
        self.red_cross = pygame.transform.smoothscale(red_cross_base, (settings.RED_CROSS_WIDTH, settings.RED_CROSS_HEIGHT))

    def draw_front(self, x, y):
        self.window.blit(self.front_img, (x, y))
        self.window.blit(self.black_overlay, (x, y))

    def draw_back(self, x, y):
        self.window.blit(self.back_img, (x, y))
        self.window.blit(self.black_overlay, (x, y))

    def draw_front_bright(self, x, y):
        self.window.blit(self.front_img, (x, y))

    def draw_front_battle_move(self, x, y):
        """Draw card with a grey overlay/border and a battle icon in the top-left corner."""
        self.window.blit(self.front_img, (x, y))
        if not hasattr(self, '_battle_move_overlay'):
            w = self.front_img.get_width()
            h = self.front_img.get_height()
            self._battle_move_overlay = pygame.Surface((w, h), pygame.SRCALPHA)
            self._battle_move_overlay.fill((40, 40, 40, 140))  # Dark grey tint overlay
            # Grey border
            pygame.draw.rect(self._battle_move_overlay, (100, 100, 100, 220),
                             (0, 0, w, h), 3)

        # Battle move icon in top-left (drawn UNDER the overlay)
        if not hasattr(self, '_battle_move_sword'):
            icon_size = int(self.front_img.get_width() * 0.35)
            if 'battle_sword' not in self._card_image_cache:
                self._card_image_cache['battle_sword'] = pygame.image.load(
                    'img/figures/state_icons/charge_opponent.png').convert_alpha()
            self._battle_move_sword = pygame.transform.smoothscale(
                self._card_image_cache['battle_sword'], (icon_size, icon_size))
        self.window.blit(self._battle_move_sword, (x + 3, y + 3))

        # Overlay on top of everything
        self.window.blit(self._battle_move_overlay, (x, y))

    def draw_back_bright(self, x, y):
        self.window.blit(self.back_img, (x, y))
    
    def draw_missing(self, x, y):
        self.window.blit(self.front_img, (x, y))
        self.window.blit(self.missing_overlay, (x, y))
        self.window.blit(self.red_cross, (x, y))

    def draw_icon(self, x, y, width, height):
        """Draw card at specified position and size (for use in dialogue boxes)."""
        # Scale the front image to the requested size
        scaled_img = pygame.transform.smoothscale(self.front_img, (int(width), int(height)))
        self.window.blit(scaled_img, (x, y))
