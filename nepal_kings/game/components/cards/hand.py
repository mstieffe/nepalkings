import pygame
from game.components.cards.card_img import CardImg
from game.components.cards.card_slot import CardSlot
from config import settings
from utils.utils import GameButton


class Hand:
    """Hand class for pygame application. This class represents a hand of cards."""

    def __init__(self, window, state, x: float = 0.0, y: float = 0.0, type="main_card", hidden=False):
        self.window = window
        self.font = pygame.font.Font(settings.FONT_PATH, settings.FONT_SIZE_DETAIL)
        self.state = state
        self.game = state.game if state else None
        self.type = type

        self.cards = self.initialize_cards()
        self.cards.sort(key=lambda card: card.rank)

        self.x = x
        self.y = y

        self.hidden = hidden
        self.card_imgs = self.initialize_card_imgs()

        self.num_slots = settings.MAX_MAIN_CARD_SLOTS if self.type == "main_card" else settings.MAX_SIDE_CARD_SLOTS
        self.card_slots = self.initialize_card_slots()

        self.slots_width = (self.num_slots - 1) * (settings.CARD_SPACER + settings.CARD_SLOT_BORDER_WIDTH) + settings.CARD_WIDTH + settings.CARD_SLOT_BORDER_WIDTH

        self.initialize_background_attributes()

        self.buttons = self.initialize_buttons()

    def initialize_cards(self):
        if self.game:
            return self.game.get_hand()[0] if self.type == "main_card" else self.game.get_hand()[1]
        else:
            return []

    def initialize_card_imgs(self):
        return {(suit, rank): CardImg(self.window, suit, rank) for suit in settings.SUITS for rank in settings.RANKS}

    def initialize_card_slots(self):
        slots = [CardSlot(self.window, x=self.x + i * (settings.CARD_SPACER + settings.CARD_SLOT_BORDER_WIDTH), y=self.y,
                          width=settings.CARD_SPACER, height=settings.CARD_HEIGHT) for i in range(self.num_slots - 1)]
        slots.append(CardSlot(self.window, x=self.x + (self.num_slots - 1) * (settings.CARD_SPACER + settings.CARD_SLOT_BORDER_WIDTH), y=self.y,
                              width=settings.CARD_WIDTH, height=settings.CARD_HEIGHT, is_last=True))
        return slots

    def initialize_background_attributes(self):
        attributes = {
            'main_card': {
                'width_ratio': 0.22,
                'height_ratio': 1.66,
                'dx_ratio': 0.1,
                'dy_ratio': 0.36,
                'image_path': './img/icons/main_hand.png',
                'addon_path': './img/icons/main_hand_addon.png',
                'text_offset_x': 0.0
            },
            'default': {
                'width_ratio': 0.28,
                'height_ratio': 1.75,
                'dx_ratio': 0.12,
                'dy_ratio': 0.4,
                'image_path': './img/icons/hand_holder.png',
                'addon_path': './img/icons/hand_holder_addon2.png',
                'text_offset_x': 0.05
            }
        }

        type_attributes = attributes.get(self.type, attributes['default'])

        self.background_image_width = self.slots_width + self.slots_width * type_attributes['width_ratio']
        self.background_image_height = settings.CARD_HEIGHT * type_attributes['height_ratio']
        self.backgorund_dx = self.background_image_width * type_attributes['dx_ratio']
        self.backgorund_dy = settings.CARD_HEIGHT * type_attributes['dy_ratio']
        self.background_image = pygame.image.load(type_attributes['image_path'])
        self.background_image_addon = pygame.image.load(type_attributes['addon_path']).convert_alpha()
        self.text_occupied_slots_x = self.x + self.slots_width * type_attributes['text_offset_x']

        self.background_image = pygame.transform.scale(self.background_image,
                                                       (self.background_image_width,
                                                        self.background_image_height))
        self.background_image_addon = pygame.transform.scale(self.background_image_addon,
                                                             (self.background_image_width,
                                                              self.background_image_height))

    def initialize_buttons(self):
        buttons = []

        # Change Card Button
        button_x = self.x + self.slots_width + self.slots_width * 0.02
        button_y = self.y - settings.CARD_HEIGHT * 0.2
        buttons.append(GameButton(self.window,
                                    'round_arrow', 'plain',
                                    button_x, button_y,
                                    symbol_width=settings.HAND_BUTTON_SYMBOL_WIDTH,
                                    stone_width=settings.HAND_BUTTON_STONE_WIDTH,
                                    glow_width=settings.HAND_BUTTON_GLOW_WIDTH,
                                    symbol_width_big=settings.HAND_BUTTON_SYMBOL_BIG_WIDTH,
                                    glow_width_big=settings.HAND_BUTTON_GLOW_BIG_WIDTH,
                                    glow_shift=settings.HAND_BUTTON_GLOW_SHIFT,
                                    state=self.state,
                                    hover_text='change cards!'))

        return buttons

    def draw_text(self, text, color, x, y):
        """Draw text on the window."""
        text_obj = self.font.render(text, True, color)
        text_rect = text_obj.get_rect()
        text_rect.topleft = (x, y)
        self.window.blit(text_obj, text_rect)

    def update(self, game):
        """Update the game state."""
        self.game = game
        self.cards = self.initialize_cards()
        self.cards.sort(key=lambda card: card.rank)

        for slot in self.card_slots:
            slot.update()

        for card, slot in zip(self.cards, reversed(self.card_slots)):
            slot.content = self.card_imgs[(card.suit, card.rank)]
            slot.card = card

        #for button in self.buttons:
        #    button.update(game)

    def handle_events(self, events):
        """Handle game events."""
        for slot in self.card_slots:
            slot.handle_events(events)

    def draw(self):
        """Draw elements on the window."""
        if self.game:
            self.window.blit(self.background_image, (self.x - self.backgorund_dx, self.y - self.backgorund_dy))
            for slot in reversed(self.card_slots):
                slot.draw_empty()
            for slot in self.card_slots:
                slot.draw_content()

            self.window.blit(self.background_image_addon, (self.x - self.backgorund_dx, self.y - self.backgorund_dy))

            self.draw_text(f'{str(len(self.cards))}/{self.num_slots} cards', settings.BLACK, self.text_occupied_slots_x,
                           self.y + settings.CARD_HEIGHT * 1.04 + settings.TINY_SPACER_Y)

            for button in self.buttons:
                button.draw()
