from game.components.cards.card_img import CardImg
import pygame
from config import settings
class CardSlot():
    def __init__(self, window, content: CardImg = None, card=None, x: float = 0.0, y: float =0.0, width: float = 0.0, height: float =0.0, is_last=False):
        self.window = window
        self.x = x
        self.y = y
        self.width = width
        self.height = height

        self.content = content
        self.card = card
        #self.is_last_with_content = is_last_with_content

        self.is_last = is_last

        dx = settings.CARD_SLOT_BORDER_WIDTH/2
        self.rect_border = pygame.Rect(self.x-dx, self.y-dx, self.width+2*dx, self.height+2*dx)
        self.rect = pygame.Rect(self.x, self.y, self.width, self.height)


        #if self.is_last:
        #    self.rect = pygame.Rect(self.x+dx, self.y+dx, self.width-settings.CARD_SLOT_BORDER_WIDTH, self.height-settings.CARD_SLOT_BORDER_WIDTH)
        #else:
        #    self.rect = pygame.Rect(self.x+dx, self.y+dx, self.width-dx, self.height-settings.CARD_SLOT_BORDER_WIDTH)

        self.rec_card = pygame.Rect(self.x, self.y, settings.CARD_WIDTH, self.height)

        self.clicked = False
        self.hovered = False

        self.border_surface = pygame.Surface((self.rect_border.w, self.rect_border.h), pygame.SRCALPHA)
        self.inner_surface = pygame.Surface((self.rect.w, self.rect.h), pygame.SRCALPHA)

    def point_inside(self, x, y):
        return self.rec_card.collidepoint(x, y)

    def update(self):
        mouse_pos = pygame.mouse.get_pos()
        if self.is_last:
            if self.rec_card.collidepoint(mouse_pos):
                self.hovered = True
            else:
                self.hovered = False
        else:
            if self.rect.collidepoint(mouse_pos):
                self.hovered = True
            else:
                self.hovered = False

    def handle_events(self, events):
        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN:
                if self.is_last:
                    if self.rec_card.collidepoint(event.pos):
                        if self.clicked:
                            self.clicked = False
                        else:
                            self.clicked = True
                else:
                    if self.rect.collidepoint(event.pos):
                        if self.clicked:
                            self.clicked = False
                        else:
                            self.clicked = True

    def draw_empty(self):
        # Clear the surfaces
        self.border_surface.fill((0, 0, 0, 0))
        self.inner_surface.fill((0, 0, 0, 0))

        # Draw a rectangle onto the border surface
        pygame.draw.rect(self.border_surface, settings.CARD_SLOT_BORDER_COLOR + (128,),
                         self.border_surface.get_rect())  # (128,) is the alpha value

        # Set the color based on hover state
        color = settings.CARD_SLOT_COLOR_HOVERED if self.hovered else settings.CARD_SLOT_COLOR
        # Draw a rectangle onto the inner surface
        pygame.draw.rect(self.inner_surface, color + (128,), self.inner_surface.get_rect())  # (128,) is the alpha value

        # Blit the surfaces onto the window
        self.window.blit(self.border_surface, (self.rect_border.x, self.rect_border.y))
        self.window.blit(self.inner_surface, (self.rect.x, self.rect.y))

    """
    def draw_empty(self):
        if self.hovered:
            pygame.draw.rect(self.window, settings.CARD_SLOT_BORDER_COLOR, self.rect_border)
            pygame.draw.rect(self.window, settings.CARD_SLOT_COLOR_HOVERED, self.rect)
        else:
            pygame.draw.rect(self.window, settings.CARD_SLOT_BORDER_COLOR, self.rect_border)
            pygame.draw.rect(self.window, settings.CARD_SLOT_COLOR, self.rect)
    """

    def draw_content_at_pos(self, x, y):
        if self.content:
            if self.hovered:
                self.content.draw_front_bright(x, y)
            else:
                self.content.draw_front(x, y)

    def draw_content(self):
        if self.content:
            if self.clicked:
                y = self.y-settings.TINY_SPACER_Y
            else:
                y = self.y
            if self.hovered:
                self.content.draw_front_bright(self.x, y)
            else:
                self.content.draw_front(self.x, y)
            #if self.clicked:
            #    self.content.draw_front_bright(self.x, self.y-settings.TINY_SPACER_Y)
        """
        else:
            #pygame.draw.rect(self.window, settings.CARD_SLOT_BORDER_COLOR, self.rect, settings.CARD_SLOT_BORDER_WIDTH)
            pygame.draw.rect(self.window, settings.CARD_SLOT_BORDER_COLOR, self.rect_border)
            pygame.draw.rect(self.window, settings.CARD_SLOT_COLOR, self.rect)
        """