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
