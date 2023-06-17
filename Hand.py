import pygame
import settings
from CardImg import CardImg
from CardSlot import CardSlot
class Hand():
    def __init__(self, window, game, x: float = 0.0, y: float =0.0, hidden=False):
        self.window = window
        self.font = pygame.font.Font(settings.FONT_PATH, settings.FONT_SIZE_DETAIL)
        self.game = game
        if self.game:
            self.cards = self.game.get_hand()
        else:
            self.cards = []

        self.x = settings.get_x(x)
        self.y = settings.get_y(y)

        self.hidden = hidden

        # initialize CardImgs
        self.card_imgs = {}
        for suit in settings.SUITS:
            for rank in settings.RANKS:
                self.card_imgs[(suit, rank)] = CardImg(self.window, suit, rank)

        self.card_slots = [CardSlot(self.window,
                                    x=self.x + i * settings.CARD_SPACER,
                                    y=self.y,
                                    width=settings.CARD_SPACER,
                                    height=settings.CARD_HEIGHT)
                           for i in range(settings.MAX_MAIN_CARD_SLOTS-1)]
        self.card_slots.append(CardSlot(self.window,
                                        x=self.x + (settings.MAX_MAIN_CARD_SLOTS-1) * settings.CARD_SPACER,
                                        y=self.y,
                                        width=settings.CARD_WIDTH,
                                        height=settings.CARD_HEIGHT,
                                        is_last=True))

    def draw_text(self, text, color, x, y):
        text_obj = self.font.render(text, True, color)
        text_rect = text_obj.get_rect()
        text_rect.topleft = (x, y)
        self.window.blit(text_obj, text_rect)

    def update(self, game):
        self.game = game
        if self.game:
            self.cards = self.game.get_hand()
        for slot in self.card_slots:
            slot.update()
        for card, slot in zip(self.cards, reversed(self.card_slots)):
            slot.content = self.card_imgs[(card['suit'], card['rank'])]
        #self.card_slots[len(self.cards)-1].is_last_with_content = True
            #self.card_imgs[(card['suit'], card['rank'])].update()

    def handle_events(self, events):
        for slot in self.card_slots:
            slot.handle_events(events)
        #for card, slot in zip(self.cards, reversed(self.card_slots)):
        #    self.card_imgs[(card['suit'], card['rank'])].handle_events(events)

    def draw(self):
        if self.game:
            self.draw_text(f'number of cards: {str(len(self.cards))}/{settings.MAX_MAIN_CARD_SLOTS}', settings.BLACK, self.x, self.y + settings.CARD_HEIGHT + settings.TINY_SPACER_Y)
            for slot in reversed(self.card_slots):
                slot.draw_empty()
            for slot in self.card_slots:
                slot.draw_content()
            """
            for i, card in enumerate(self.cards):
                card_img = self.card_imgs[(card['suit'], card['rank'])]
                if card_img.hovered_partial:
                    card_img.draw_front_bright(self.x + i * settings.CARD_SPACER, self.y)
                else:
                    card_img.draw_front(self.x + i * settings.CARD_SPACER, self.y)
            """
            #self.card_imgs[(card['suit'], card['rank'])].draw_front(self.x + i * settings.CARD_SPACER, self.y)

