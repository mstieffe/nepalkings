from config import settings
import pygame
from collections import Counter
import math

class FigureIconButton:

    def __init__(self, window, game, fig, content, x: int = 0, y: int = 0):
        self.window = window
        self.game = game
        self.fig = fig
        self.content = content
        self.x = x
        self.y = y

        # Fonts for text rendering
        self.font = pygame.font.Font(settings.FONT_PATH, settings.FIGURE_ICON_FONT_CAPTION_FONT_SIZE)
        self.font_big = pygame.font.Font(settings.FONT_PATH, settings.FIGURE_ICON_FONT_CAPTION_BIG_FONT_SIZE)

        # Text surfaces
        self.text_surface = self.font.render(self.fig.name, True, settings.SUIT_ICON_CAPTION_COLOR)
        self.text_surface_big = self.font_big.render(self.fig.name, True, settings.SUIT_ICON_CAPTION_COLOR)

        # Initial state variables
        self.is_active = False
        self.clicked = False
        self.hovered = False
        self.time = 0  # Used for animations (like moving up and down)

        # Load the images for the figure icon and the glow effects
        self.load_images()

        # Set positions for the images and text
        self.set_position(x, y)

    def load_images(self):
        """Load and scale all the necessary images for the figure."""
        icon_mask_img = pygame.image.load(settings.FIGURE_ICON_IMG_PATH + 'mask.png')
        self.icon_mask_img = pygame.transform.scale(icon_mask_img, (settings.FIGURE_ICON_MASK_WIDTH, settings.FIGURE_ICON_MASK_HEIGHT))
        self.icon_mask_big_img = pygame.transform.scale(icon_mask_img, (settings.FIGURE_ICON_MASK_BIG_WIDTH, settings.FIGURE_ICON_MASK_BIG_HEIGHT))

        self.icon_img = pygame.transform.scale(self.fig.icon_img, (settings.FIGURE_ICON_WIDTH, settings.FIGURE_ICON_HEIGHT))
        self.icon_big_img = pygame.transform.scale(self.fig.icon_img, (settings.FIGURE_ICON_BIG_WIDTH, settings.FIGURE_ICON_BIG_HEIGHT))
        self.icon_darkwhite_img = pygame.transform.scale(self.fig.icon_darkwhite_img, (settings.FIGURE_ICON_WIDTH, settings.FIGURE_ICON_HEIGHT))
        self.icon_darkwhite_big_img = pygame.transform.scale(self.fig.icon_darkwhite_img, (settings.FIGURE_ICON_BIG_WIDTH, settings.FIGURE_ICON_BIG_HEIGHT))

        # Glow effects
        self.glow_yellow = pygame.transform.scale(pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH + 'yellow.png'), (settings.FIGURE_ICON_GLOW_WIDTH, settings.FIGURE_ICON_GLOW_WIDTH))
        self.glow_black = pygame.transform.scale(pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH + 'black.png'), (settings.FIGURE_ICON_GLOW_WIDTH, settings.FIGURE_ICON_GLOW_WIDTH))
        self.glow_orange_big = pygame.transform.scale(pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH + 'orange.png'), (settings.FIGURE_ICON_GLOW_BIG_WIDTH, settings.FIGURE_ICON_GLOW_BIG_WIDTH))
        self.glow_white_big = pygame.transform.scale(pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH + 'white.png'), (settings.FIGURE_ICON_GLOW_BIG_WIDTH, settings.FIGURE_ICON_GLOW_BIG_WIDTH))

    def set_position(self, x, y):
        """Set the position of the figure icon and glow effects."""
        self.x = x
        self.y = y

        # Center the mask, icon, and glow
        self.rect_mask = self.icon_mask_img.get_rect(center=(self.x, self.y))
        self.rect_icon = self.icon_img.get_rect(center=(self.x, self.y))
        self.rect_glow = self.glow_yellow.get_rect(center=(self.x, self.y))
        self.rect_mask_big = self.icon_mask_big_img.get_rect(center=(self.x, self.y))
        self.rect_icon_big = self.icon_big_img.get_rect(center=(self.x, self.y))
        self.rect_glow_big = self.glow_orange_big.get_rect(center=(self.x, self.y))

        # Set the text positions
        self.text_rect = self.text_surface.get_rect(center=(self.x, self.y + settings.FIGURE_ICON_BIG_WIDTH // 2 + settings.get_y(0.015)))
        self.text_rect_big = self.text_surface_big.get_rect(center=(self.x, self.y + settings.FIGURE_ICON_BIG_WIDTH // 2 + settings.get_y(0.015)))

    def is_in_hand(self, suit=None):
        """Check if the figure can be built with the cards available in hand."""
        main_cards, side_cards = self.game.get_hand()
        cards = main_cards + side_cards

        if suit:
            cards = [(card['suit'], card['rank']) for card in cards if card['suit'] == suit]
        else:
            cards = [(card['suit'], card['rank']) for card in cards]

        cards_counter = Counter(cards)

        for fig in self.content:
            fig_cards_counter = Counter(fig.cards)
            if all(cards_counter[card] >= fig_cards_counter[card] for card in fig_cards_counter):
                return True
        return False

    def collide(self):
        """Check if the mouse is hovering over the figure icon."""
        mx, my = pygame.mouse.get_pos()
        return self.rect_mask.collidepoint((mx, my))

    def draw(self):
        """Draw the figure icon with the glow and animations based on the state."""
        y_offset = settings.FIGURE_ICON_SIN_AMPL * math.sin(self.time) if self.clicked else 0

        # Determine the correct images based on whether the figure is active
        icon_img = self.icon_img if self.is_active else self.icon_darkwhite_img
        icon_big_img = self.icon_big_img if self.is_active else self.icon_darkwhite_big_img
        glow_img = self.glow_yellow if self.is_active else self.glow_black
        glow_big_img = self.glow_orange_big if self.is_active else self.glow_white_big

        # Draw based on the interaction state (hover, clicked, etc.)
        if pygame.mouse.get_pressed()[0] and self.hovered:
            # Mouse is pressed and hovering
            self.window.blit(glow_big_img, (self.rect_glow_big.topleft[0], self.rect_glow_big.topleft[1] + y_offset))
            self.window.blit(icon_img, (self.rect_icon.topleft[0], self.rect_icon.topleft[1] + y_offset))
            self.window.blit(self.icon_mask_img, (self.rect_mask.topleft[0], self.rect_mask.topleft[1] + y_offset))
            self.window.blit(self.text_surface, (self.text_rect.topleft[0], self.text_rect.topleft[1] + y_offset))

        elif self.clicked and self.hovered:
            # Clicked and hovered
            self.window.blit(glow_big_img, (self.rect_glow_big.topleft[0], self.rect_glow_big.topleft[1] + y_offset))
            self.window.blit(icon_big_img, (self.rect_icon_big.topleft[0], self.rect_icon_big.topleft[1] + y_offset))
            self.window.blit(self.icon_mask_big_img, (self.rect_mask_big.topleft[0], self.rect_mask_big.topleft[1] + y_offset))
            self.window.blit(self.text_surface_big, (self.text_rect_big.topleft[0], self.text_rect_big.topleft[1] + y_offset))

        elif self.clicked:
            # Just clicked (not hovered)
            self.window.blit(glow_big_img, (self.rect_glow_big.topleft[0], self.rect_glow_big.topleft[1] + y_offset))
            self.window.blit(icon_img, (self.rect_icon.topleft[0], self.rect_icon.topleft[1] + y_offset))
            self.window.blit(self.icon_mask_img, (self.rect_mask.topleft[0], self.rect_mask.topleft[1] + y_offset))
            self.window.blit(self.text_surface, (self.text_rect.topleft[0], self.text_rect.topleft[1] + y_offset))

        elif self.hovered:
            # Hovering (not clicked)
            self.window.blit(glow_img, self.rect_glow.topleft)
            self.window.blit(icon_big_img, self.rect_icon_big.topleft)
            self.window.blit(self.icon_mask_big_img, self.rect_mask_big.topleft)
            self.window.blit(self.text_surface_big, self.text_rect_big.topleft)

        else:
            # Default state
            self.window.blit(icon_img, self.rect_icon.topleft)
            self.window.blit(self.icon_mask_img, self.rect_mask.topleft)
            self.window.blit(self.text_surface, self.text_rect.topleft)

    def update(self, game):
        """Update the state of the button based on the game state."""
        self.game = game
        if self.game:
            if self.clicked:
                self.time += 0.1  # Create the up-and-down animation
            else:
                self.time = 0

            self.is_active = self.is_in_hand()  # Determine if the figure is active (in hand)
            self.hovered = self.collide()  # Check if the mouse is hovering

    def handle_events(self, events):
        """Handle click events for the figure icon."""
        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.hovered and self.is_active:
                self.clicked = not self.clicked  # Toggle clicked state