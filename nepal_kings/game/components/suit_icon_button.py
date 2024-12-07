from config import settings
import pygame
import math

class SuitIconButton:

    def __init__(self, window, game, suit: str, x: int = 0, y: int = 0):
        self.window = window
        self.game = game
        self.suit = suit
        self.x = x
        self.y = y

        # Fonts for rendering text
        self.font = pygame.font.Font(settings.FONT_PATH, settings.FIGURE_ICON_FONT_CAPTION_FONT_SIZE)
        self.font_big = pygame.font.Font(settings.FONT_PATH, settings.FIGURE_ICON_FONT_CAPTION_BIG_FONT_SIZE)

        # Initialize state variables
        self.is_active = True
        self.clicked = False
        self.hovered = False
        self.time = 0  # Used for the bouncing animation

        # Load images for the suit icon and glow effects
        self.load_images()

        # Initialize the text surfaces and their positions
        self.hover_text = self.suit
        self.text_surface = self.font.render(self.hover_text, True, settings.SUIT_ICON_CAPTION_COLOR)
        self.text_surface_big = self.font_big.render(self.hover_text, True, settings.SUIT_ICON_CAPTION_COLOR)
        self.update_text_positions()

    def load_images(self):
        """Load and scale the images for the suit icon and glow effects."""
        # Load icon and darkened icon images
        suit_img_path = settings.SUIT_ICON_IMG_PATH + self.suit + '.png'
        suit_darkwhite_img_path = settings.SUIT_ICON_DARKWHITE_IMG_PATH + self.suit + '.png'

        self.icon_img = pygame.transform.smoothscale(pygame.image.load(suit_img_path).convert_alpha(), (settings.SUIT_ICON_WIDTH, settings.SUIT_ICON_HEIGHT))
        self.icon_big_img = pygame.transform.smoothscale(pygame.image.load(suit_img_path).convert_alpha(), (settings.SUIT_ICON_BIG_WIDTH, settings.SUIT_ICON_BIG_HEIGHT))

        self.icon_darkwhite_img = pygame.transform.smoothscale(pygame.image.load(suit_darkwhite_img_path).convert_alpha(), (settings.SUIT_ICON_WIDTH, settings.SUIT_ICON_HEIGHT))
        self.icon_darkwhite_big_img = pygame.transform.smoothscale(pygame.image.load(suit_darkwhite_img_path).convert_alpha(), (settings.SUIT_ICON_BIG_WIDTH, settings.SUIT_ICON_BIG_HEIGHT))

        # Load glow effects
        self.glow_yellow = pygame.transform.smoothscale(pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH + 'yellow.png').convert_alpha(), (settings.SUIT_ICON_GLOW_WIDTH, settings.SUIT_ICON_GLOW_WIDTH))
        self.glow_black = pygame.transform.smoothscale(pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH + 'black.png').convert_alpha(), (settings.SUIT_ICON_GLOW_WIDTH, settings.SUIT_ICON_GLOW_WIDTH))
        self.glow_orange_big = pygame.transform.smoothscale(pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH + 'orange.png').convert_alpha(), (settings.SUIT_ICON_GLOW_BIG_WIDTH, settings.SUIT_ICON_GLOW_BIG_WIDTH))
        self.glow_yellow_big = pygame.transform.smoothscale(pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH + 'yellow.png').convert_alpha(), (settings.SUIT_ICON_GLOW_BIG_WIDTH, settings.SUIT_ICON_GLOW_BIG_WIDTH))
        self.glow_white_big = pygame.transform.smoothscale(pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH + 'white.png').convert_alpha(), (settings.SUIT_ICON_GLOW_BIG_WIDTH, settings.SUIT_ICON_GLOW_BIG_WIDTH))
        self.glow_black_big = pygame.transform.smoothscale(pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH + 'black.png').convert_alpha(), (settings.SUIT_ICON_GLOW_BIG_WIDTH, settings.SUIT_ICON_GLOW_BIG_WIDTH))

        # Set icon positions
        self.rect_icon = self.icon_img.get_rect(center=(self.x, self.y))
        self.rect_glow = self.glow_yellow.get_rect(center=(self.x, self.y))
        self.rect_icon_big = self.icon_big_img.get_rect(center=(self.x, self.y))
        self.rect_glow_big = self.glow_orange_big.get_rect(center=(self.x, self.y))

    def update_text_positions(self):
        """Update the positions of the text surfaces."""
        self.text_rect = self.text_surface.get_rect(center=(self.x, self.y + settings.get_y(0.05)))
        self.text_rect_big = self.text_surface_big.get_rect(center=(self.x, self.y + settings.get_y(0.05)))

    def set_position(self, x, y):
        """Set the new position for the suit icon and update related elements."""
        self.x = x
        self.y = y
        self.rect_icon.center = (self.x, self.y)
        self.rect_glow.center = (self.x, self.y)
        self.rect_icon_big.center = (self.x, self.y)
        self.rect_glow_big.center = (self.x, self.y)
        self.update_text_positions()

    def is_in_hand(self, figs=None):
        """Check if there are figures available for this suit in the player's hand."""
        main_cards, side_cards = self.game.get_hand()
        cards = main_cards + side_cards

        if figs:
            cards = []
            for fig in figs:
                if fig.suit == self.suit:
                    cards += fig.cards
        else:
            cards = [(card.suit, card.rank) for card in cards if card.suit == self.suit]

        return len(cards) > 0

    def collide(self):
        """Check if the mouse is hovering over the suit icon."""
        mx, my = pygame.mouse.get_pos()
        return self.rect_icon.collidepoint((mx, my))

    def draw(self):
        """Draw the suit icon and its glow effect based on its state."""
        y_offset = settings.FIGURE_ICON_SIN_AMPL * math.sin(self.time) if self.clicked else 0

        # Select the appropriate images and glow effects based on the state
        icon_img = self.icon_img if self.is_active else self.icon_darkwhite_img
        icon_big_img = self.icon_big_img if self.is_active else self.icon_darkwhite_big_img
        glow_img = self.glow_yellow if self.is_active else self.glow_black
        glow_big_img = self.glow_orange_big if self.is_active else self.glow_white_big

        if pygame.mouse.get_pressed()[0] and self.hovered:
            # Mouse is pressed and hovering
            self.window.blit(glow_big_img, (self.rect_glow_big.topleft[0], self.rect_glow_big.topleft[1] + y_offset))
            self.window.blit(icon_img, (self.rect_icon.topleft[0], self.rect_icon.topleft[1] + y_offset))
            self.text_rect.center = (self.x, self.y + settings.get_y(0.04) + y_offset)
            self.window.blit(self.text_surface, self.text_rect)

        elif self.clicked and self.hovered:
            # Clicked and hovered
            glow_big_img = self.glow_yellow_big if self.is_active else self.glow_black_big
            self.window.blit(glow_big_img, (self.rect_glow_big.topleft[0], self.rect_glow_big.topleft[1] + y_offset))
            self.window.blit(icon_big_img, (self.rect_icon_big.topleft[0], self.rect_icon_big.topleft[1] + y_offset))
            self.text_rect_big.center = (self.x, self.y + settings.get_y(0.04) + y_offset)
            self.window.blit(self.text_surface_big, self.text_rect_big)

        elif self.clicked:
            # Just clicked (not hovered)
            self.window.blit(glow_big_img, (self.rect_glow_big.topleft[0], self.rect_glow_big.topleft[1] + y_offset))
            self.window.blit(icon_img, (self.rect_icon.topleft[0], self.rect_icon.topleft[1] + y_offset))
            #self.text_rect.center = (self.x, self.y + settings.get_y(0.04) + y_offset)
            #self.window.blit(self.text_surface, self.text_rect)

        elif self.hovered:
            # Hovering (not clicked)
            glow_img = self.glow_yellow if self.is_active else self.glow_black
            self.window.blit(glow_img, self.rect_glow.topleft)
            self.window.blit(icon_big_img, self.rect_icon_big.topleft)
            self.text_rect_big.center = (self.x, self.y + settings.get_y(0.04) + y_offset)
            self.window.blit(self.text_surface_big, self.text_rect_big)


        else:
            # Default state
            self.window.blit(icon_img, self.rect_icon.topleft)
            #self.window.blit(self.text_surface, self.text_rect)

    def update(self, game):
        """Update the state of the suit button based on the game state."""
        self.game = game
        if self.game:
            if self.clicked:
                self.time += 0.1  # Create the bouncing animation
            else:
                self.time = 0

            #self.is_active = self.is_in_hand()  # Determine if the suit is active (in hand)
            self.hovered = self.collide()  # Check if the mouse is hovering

    def handle_events(self, events):
        """Handle click events for the suit icon."""
        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.hovered and self.is_active:
                self.clicked = not self.clicked  # Toggle clicked state
