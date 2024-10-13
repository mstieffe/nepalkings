import pygame
from pygame.locals import *
from config import settings

class CardImg():
    def __init__(self, window, suit, rank):
        self.window = window
        self.suit = suit
        self.rank = rank

        self.front_img_path = f"{settings.CARD_IMG_PATH}{settings.SUIT_TO_IMG_PATH[self.suit]}{settings.RANK_TO_IMG_PATH[self.rank]}.png"
        self.back_img_path = f"{settings.CARD_IMG_PATH}back.png"

        self.front_img = pygame.image.load(self.front_img_path)
        self.back_img = pygame.image.load(self.back_img_path)

        self.front_img = pygame.transform.scale(self.front_img, (settings.CARD_WIDTH, settings.CARD_HEIGHT))
        self.back_img = pygame.transform.scale(self.back_img, (settings.CARD_WIDTH, settings.CARD_HEIGHT))

        self.black_overlay = pygame.Surface((settings.CARD_WIDTH, settings.CARD_HEIGHT), pygame.SRCALPHA)
        self.black_overlay.fill((0, 0, 0, settings.ALPHA_OVERLAY)) # RGBA

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
