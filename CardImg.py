import pygame
from pygame.locals import *
import settings
from utils import scale, brighten

class CardImg():
    def __init__(self, window, suit, rank):
        self.window = window
        self.suit = suit
        self.rank = rank

        self.front_img_path = f"{settings.CARD_IMG_PATH}{settings.RANK_TO_IMG_PATH[self.rank]}{settings.SUIT_TO_IMG_PATH[self.suit]}.gif"
        self.back_img_path = f"{settings.CARD_IMG_PATH}back.png"

        self.front_img = pygame.image.load(self.front_img_path)
        self.back_img = pygame.image.load(self.back_img_path)

        self.front_img = pygame.transform.scale(self.front_img, (settings.CARD_WIDTH, settings.CARD_HEIGHT))
        self.back_img = pygame.transform.scale(self.back_img, (settings.CARD_WIDTH, settings.CARD_HEIGHT))

        #self.front_img = scale(self.front_img, settings.CARD_RELATIVE_WIDTH)
        #self.back_img = scale(self.back_img, settings.CARD_RELATIVE_WIDTH)

        self.front_img_bright = brighten(self.front_img, settings.BRIGHTNESS_FACTOR)
        self.back_img_bright = brighten(self.back_img, settings.BRIGHTNESS_FACTOR)

        """
        self.hovered = False
        self.hovered_partial = False

        self.clicked_on = False
        self.clicked_on_partial = False

        # Set the card's rectangle based on the image size
        self.rect = self.front_img.get_rect()
        self.rect_partial = pygame.Rect(self.rect.left, self.rect.top, settings.CARD_SPACER, self.rect.height)
        """
    """
    def update(self):
        mouse_pos = pygame.mouse.get_pos()
        if self.rect.collidepoint(mouse_pos):
            self.hovered = True
        else:
            self.hovered = False
        if self.rect.collidepoint(mouse_pos):
            self.hovered_partial = True
        else:
            self.hovered_partial = False

    def handle_events(self, events):
        for event in events:
            if event.type == MOUSEBUTTONDOWN:
                if self.rect.collidepoint(event.pos):
                    self.clicked_on = True
                else:
                    self.clicked_on = False
                if self.rect_partial.collidepoint(event.pos):
                    self.clicked_on_partial = True
                else:
                    self.clicked_on_partial = False
    """

    def draw_front(self, x, y):
        self.window.blit(self.front_img, (x, y))

    def draw_back(self, x, y):
        self.window.blit(self.back_img, (x, y))

    def draw_front_bright(self, x, y):
        self.window.blit(self.front_img_bright, (x, y))

    def draw_back_bright(self, x, y):
        self.window.blit(self.back_img_bright, (x, y))
