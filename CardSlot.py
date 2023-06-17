import CardImg
import pygame
import settings
class CardSlot():
    def __init__(self, window, content: CardImg = None, x: float = 0.0, y: float =0.0, width: float = 0.0, height: float =0.0, is_last=False):
        self.window = window
        self.x = x
        self.y = y
        self.width = width
        self.height = height

        self.content = content
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
        if self.hovered:
            pygame.draw.rect(self.window, settings.CARD_SLOT_BORDER_COLOR, self.rect_border)
            pygame.draw.rect(self.window, settings.CARD_SLOT_COLOR_HOVERED, self.rect)
        else:
            pygame.draw.rect(self.window, settings.CARD_SLOT_BORDER_COLOR, self.rect_border)
            pygame.draw.rect(self.window, settings.CARD_SLOT_COLOR, self.rect)

    def draw_content(self):
        if self.content:
            if self.hovered:
                self.content.draw_front_bright(self.x, self.y)
            else:
                self.content.draw_front(self.x, self.y)
            if self.clicked:
                self.content.draw_front_bright(self.x, self.y-settings.TINY_SPACER_Y)
        """
        else:
            #pygame.draw.rect(self.window, settings.CARD_SLOT_BORDER_COLOR, self.rect, settings.CARD_SLOT_BORDER_WIDTH)
            pygame.draw.rect(self.window, settings.CARD_SLOT_BORDER_COLOR, self.rect_border)
            pygame.draw.rect(self.window, settings.CARD_SLOT_COLOR, self.rect)
        """