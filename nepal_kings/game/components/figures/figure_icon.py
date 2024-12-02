import pygame
import math
from collections import Counter
from config import settings


class FigureIcon:
    def __init__(
            self, 
            window, 
            name: str, 
            x: int = 0, 
            y: int = 0, 
            icon_img: pygame.Surface = None, 
            icon_gray_img: pygame.Surface = None, 
            frame_img: pygame.Surface = None, 
            frame_closed_img: pygame.Surface = None,
            ):
        self.window = window
        self.name = name  # Name of the figure/family
        self.x = x
        self.y = y

        # Images and frames
        self.icon_img = icon_img
        self.icon_gray_img = icon_gray_img
        self.frame_img = self.scale_image(frame_img, settings.FRAME_FIGURE_SCALE)
        self.frame_closed_img = self.scale_image(frame_closed_img, settings.FRAME_FIGURE_SCALE)

        self.icon_img_big = self.scale_image(icon_img, settings.FIGURE_ICON_BIG_SCALE)
        self.icon_gray_img_big = self.scale_image(icon_gray_img, settings.FIGURE_ICON_BIG_SCALE)
        self.frame_img_big = self.scale_image(frame_img, settings.FIGURE_ICON_BIG_SCALE)
        self.frame_closed_img_big = self.scale_image(frame_closed_img, settings.FIGURE_ICON_BIG_SCALE)

        #self.icon_img = pygame.transform.scale(icon_img, (icon_width, icon_height))
        #self.icon_gray_img = pygame.transform.scale(icon_gray_img, (icon_width, icon_height))
        #self.frame_img = pygame.transform.scale(frame_img, (icon_width, icon_height))
        #self.frame_closed_img = pygame.transform.scale(frame_closed_img, (icon_width, icon_height))

        #self.icon_img_big = pygame.transform.scale(icon_img, (icon_big_width, icon_big_height))
        #self.icon_gray_img_big = pygame.transform.scale(icon_gray_img, (icon_big_width, icon_big_height))
        #self.frame_img_big = pygame.transform.scale(frame_img, (icon_big_width, icon_big_height))
        #self.frame_closed_img_big = pygame.transform.scale(frame_closed_img, (icon_big_width, icon_big_height))

        # Fonts for text rendering
        self.font = pygame.font.Font(settings.FONT_PATH, settings.FIGURE_ICON_FONT_CAPTION_FONT_SIZE)
        self.font_big = pygame.font.Font(settings.FONT_PATH, settings.FIGURE_ICON_FONT_CAPTION_BIG_FONT_SIZE)

        # Text surfaces
        self.text_surface = self.font.render(self.name, True, settings.SUIT_ICON_CAPTION_COLOR)
        self.text_surface_big = self.font_big.render(self.name, True, settings.SUIT_ICON_CAPTION_COLOR)

        # State variables
        self.is_active = False
        self.clicked = False
        self.hovered = False
        self.time = 0  # Used for animations (like moving up and down)

        # Load glow effects and initialize positions
        self.load_glow_effects()
        self.set_position(x, y)

    def scale_image(self, image, scale_factor):
        """Scales the image with a smooth interpolation."""
        new_width = int(image.get_width() * scale_factor)
        new_height = int(image.get_height() * scale_factor)
        
        # Ensure the image is in a format compatible with smoothscale
        if image.get_alpha() is not None:
            image = image.convert_alpha()  # Preserve transparency
        else:
            image = image.convert()  # No transparency
        
        return pygame.transform.smoothscale(image, (new_width, new_height))
    
    def scale_image_total_size(self, image, total_width, total_height):
        """Scales the image to fit within the total size."""
        scale_factor = min(total_width / image.get_width(), total_height / image.get_height())
        return self.scale_image(image, scale_factor)
    

    def load_glow_effects(self):
        """Load and scale all the necessary glow effects."""
        self.glow_yellow = pygame.transform.smoothscale(pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH + 'yellow.png'), (settings.FIGURE_ICON_GLOW_WIDTH, settings.FIGURE_ICON_GLOW_WIDTH))
        self.glow_black = pygame.transform.smoothscale(pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH + 'black.png'), (settings.FIGURE_ICON_GLOW_WIDTH, settings.FIGURE_ICON_GLOW_WIDTH))
        self.glow_orange_big = pygame.transform.smoothscale(pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH + 'orange.png'), (settings.FIGURE_ICON_GLOW_BIG_WIDTH, settings.FIGURE_ICON_GLOW_BIG_WIDTH))
        self.glow_white_big = pygame.transform.smoothscale(pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH + 'white.png'), (settings.FIGURE_ICON_GLOW_BIG_WIDTH, settings.FIGURE_ICON_GLOW_BIG_WIDTH))
        self.glow_orange = pygame.transform.smoothscale(pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH + 'orange.png'), (settings.FIGURE_ICON_GLOW_WIDTH, settings.FIGURE_ICON_GLOW_WIDTH))
        self.glow_white = pygame.transform.smoothscale(pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH + 'white.png'), (settings.FIGURE_ICON_GLOW_WIDTH, settings.FIGURE_ICON_GLOW_WIDTH))

    def set_position(self, x, y, icon_offset_x=0, icon_offset_y=0):
        """Set the position of the figure icon and its elements."""
        self.x = x
        self.y = y

        # Center the icon and frame
        self.rect_icon = self.icon_img.get_rect(center=(self.x + icon_offset_x, self.y + icon_offset_y))
        self.rect_frame = self.frame_img.get_rect(center=(self.x, self.y))
        self.rect_glow = self.glow_yellow.get_rect(center=(self.x, self.y))
        self.rect_icon_big = self.icon_img_big.get_rect(center=(self.x + icon_offset_x, self.y + icon_offset_y))
        self.rect_frame_big = self.frame_img_big.get_rect(center=(self.x, self.y))
        self.rect_glow_big = self.glow_orange_big.get_rect(center=(self.x, self.y))

        # Set text positions
        self.text_rect = self.text_surface.get_rect(center=(self.x, self.y + settings.FIGURE_ICON_BIG_WIDTH // 2 + settings.get_y(0.015)))
        self.text_rect_big = self.text_surface_big.get_rect(center=(self.x, self.y + settings.FIGURE_ICON_BIG_WIDTH // 2 + settings.get_y(0.015)))

    def collide(self):
        """Check if the mouse is hovering over the figure icon."""
        mx, my = pygame.mouse.get_pos()
        return self.rect_frame.collidepoint((mx, my))

    def draw(self):
        """Draw the figure icon with the glow and animations based on the state."""
        y_offset = settings.FIGURE_ICON_SIN_AMPL * math.sin(self.time) if self.clicked else 0

        icon_img = self.icon_img if self.is_active else self.icon_gray_img
        icon_img_big = self.icon_img_big if self.is_active else self.icon_gray_img_big
        glow_img = self.glow_yellow if self.is_active else self.glow_black
        glow_img_big = self.glow_orange_big if self.is_active else self.glow_white_big
        glow_img_clicked = self.glow_orange if self.is_active else self.glow_white

        if pygame.mouse.get_pressed()[0] and self.hovered:
            self.window.blit(glow_img, (self.rect_glow.topleft[0], self.rect_glow.topleft[1] + y_offset))
            self.window.blit(icon_img, (self.rect_icon.topleft[0], self.rect_icon.topleft[1] + y_offset))
            self.window.blit(self.frame_img, (self.rect_frame.topleft[0], self.rect_frame.topleft[1] + y_offset))
            self.window.blit(self.text_surface, (self.text_rect.topleft[0], self.text_rect.topleft[1] + y_offset))

        elif self.clicked and self.hovered:
            self.window.blit(glow_img_big, (self.rect_glow_big.topleft[0], self.rect_glow_big.topleft[1] + y_offset))
            self.window.blit(icon_img_big, (self.rect_icon_big.topleft[0], self.rect_icon_big.topleft[1] + y_offset))
            self.window.blit(self.frame_img_big, (self.rect_frame_big.topleft[0], self.rect_frame_big.topleft[1] + y_offset))
            self.window.blit(self.text_surface_big, (self.text_rect_big.topleft[0], self.text_rect_big.topleft[1] + y_offset))

        elif self.clicked:
            self.window.blit(glow_img_clicked, (self.rect_glow.topleft[0], self.rect_glow.topleft[1] + y_offset))
            self.window.blit(icon_img_big, (self.rect_icon.topleft[0], self.rect_icon.topleft[1] + y_offset))
            self.window.blit(self.frame_img, (self.rect_frame.topleft[0], self.rect_frame.topleft[1] + y_offset))
            self.window.blit(self.text_surface, (self.text_rect.topleft[0], self.text_rect.topleft[1] + y_offset))

        elif self.hovered:
            self.window.blit(glow_img_big, self.rect_glow_big.topleft)
            self.window.blit(icon_img_big, self.rect_icon_big.topleft)
            self.window.blit(self.frame_img_big, self.rect_frame_big.topleft)
            self.window.blit(self.text_surface_big, self.text_rect_big.topleft)

        else:
            self.window.blit(icon_img, self.rect_icon.topleft)
            self.window.blit(self.frame_img, self.rect_frame.topleft)
            self.window.blit(self.text_surface, self.text_rect.topleft)
   

    def update(self):
        """Update the animation and interaction state."""
        if self.clicked:
            self.time += 0.1  # Animate
        else:
            self.time = 0
        self.hovered = self.collide()

    def handle_events(self, events):
        """Handle click events for the figure icon."""
        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.hovered:
                self.clicked = not self.clicked  # Toggle clicked state


class BuildFigureIcon(FigureIcon):
    def __init__(self, window, game, fig_fam, x: int = 0, y: int = 0):
        super().__init__(window, fig_fam.name, x, y, fig_fam.icon_img, fig_fam.icon_gray_img, fig_fam.frame_img, fig_fam.frame_closed_img)

        if fig_fam.field != "castle":
            self.icon_img = self.scale_image_total_size(fig_fam.icon_img, settings.BUILD_FIGURE_ICON_WIDTH, settings.BUILD_FIGURE_ICON_HEIGHT)
            self.icon_gray_img = self.scale_image_total_size(fig_fam.icon_gray_img, settings.BUILD_FIGURE_ICON_WIDTH, settings.BUILD_FIGURE_ICON_HEIGHT)
            self.frame_img = self.scale_image_total_size(fig_fam.frame_img, settings.BUILD_FIGURE_ICON_WIDTH*settings.FRAME_FIGURE_SCALE, settings.BUILD_FIGURE_ICON_HEIGHT*settings.FRAME_FIGURE_SCALE)
            self.frame_closed_img = self.scale_image_total_size(fig_fam.frame_closed_img, settings.BUILD_FIGURE_ICON_WIDTH*settings.FRAME_FIGURE_SCALE, settings.BUILD_FIGURE_ICON_HEIGHT*settings.FRAME_FIGURE_SCALE)

            self.icon_img_big = self.scale_image_total_size(fig_fam.icon_img, settings.BUILD_FIGURE_ICON_WIDTH*settings.FIGURE_ICON_BIG_SCALE, settings.BUILD_FIGURE_ICON_HEIGHT*settings.FIGURE_ICON_BIG_SCALE)
            self.icon_gray_img_big = self.scale_image_total_size(fig_fam.icon_gray_img, settings.BUILD_FIGURE_ICON_WIDTH*settings.FIGURE_ICON_BIG_SCALE, settings.BUILD_FIGURE_ICON_HEIGHT*settings.FIGURE_ICON_BIG_SCALE)
            self.frame_img_big = self.scale_image_total_size(fig_fam.frame_img, settings.BUILD_FIGURE_ICON_WIDTH*settings.FIGURE_ICON_BIG_SCALE*settings.FRAME_FIGURE_SCALE, settings.BUILD_FIGURE_ICON_HEIGHT*settings.FIGURE_ICON_BIG_SCALE*settings.FRAME_FIGURE_SCALE)
            self.frame_closed_img_big = self.scale_image_total_size(fig_fam.frame_closed_img, settings.BUILD_FIGURE_ICON_WIDTH*settings.FIGURE_ICON_BIG_SCALE*settings.FRAME_FIGURE_SCALE, settings.BUILD_FIGURE_ICON_HEIGHT*settings.FIGURE_ICON_BIG_SCALE*settings.FRAME_FIGURE_SCALE)
            
            self.set_position(x, y, -settings.get_x(0.00), +settings.get_y(0.00))
        else:
            castle_scale_factor = 1.3
            self.icon_img = self.scale_image_total_size(fig_fam.icon_img, settings.BUILD_FIGURE_ICON_WIDTH*castle_scale_factor, settings.BUILD_FIGURE_ICON_HEIGHT*castle_scale_factor)
            self.icon_gray_img = self.scale_image_total_size(fig_fam.icon_gray_img, settings.BUILD_FIGURE_ICON_WIDTH*castle_scale_factor, settings.BUILD_FIGURE_ICON_HEIGHT*castle_scale_factor)
            self.frame_img = self.scale_image_total_size(fig_fam.frame_img, settings.BUILD_FIGURE_ICON_WIDTH*castle_scale_factor*settings.FRAME_FIGURE_SCALE, settings.BUILD_FIGURE_ICON_HEIGHT*castle_scale_factor*settings.FRAME_FIGURE_SCALE)
            self.frame_closed_img = self.scale_image_total_size(fig_fam.frame_closed_img, settings.BUILD_FIGURE_ICON_WIDTH*castle_scale_factor*settings.FRAME_FIGURE_SCALE, settings.BUILD_FIGURE_ICON_HEIGHT*castle_scale_factor*settings.FRAME_FIGURE_SCALE)

            self.icon_img_big = self.scale_image_total_size(fig_fam.icon_img, settings.BUILD_FIGURE_ICON_WIDTH*settings.FIGURE_ICON_BIG_SCALE*castle_scale_factor, settings.BUILD_FIGURE_ICON_HEIGHT*settings.FIGURE_ICON_BIG_SCALE*castle_scale_factor)
            self.icon_gray_img_big = self.scale_image_total_size(fig_fam.icon_gray_img, settings.BUILD_FIGURE_ICON_WIDTH*settings.FIGURE_ICON_BIG_SCALE*castle_scale_factor, settings.BUILD_FIGURE_ICON_HEIGHT*settings.FIGURE_ICON_BIG_SCALE*castle_scale_factor)
            self.frame_img_big = self.scale_image_total_size(fig_fam.frame_img, settings.BUILD_FIGURE_ICON_WIDTH*settings.FIGURE_ICON_BIG_SCALE*settings.FRAME_FIGURE_SCALE*castle_scale_factor, settings.BUILD_FIGURE_ICON_HEIGHT*settings.FIGURE_ICON_BIG_SCALE*settings.FRAME_FIGURE_SCALE*castle_scale_factor)
            self.frame_closed_img_big = self.scale_image_total_size(fig_fam.frame_closed_img, settings.BUILD_FIGURE_ICON_WIDTH*settings.FIGURE_ICON_BIG_SCALE*settings.FRAME_FIGURE_SCALE*castle_scale_factor, settings.BUILD_FIGURE_ICON_HEIGHT*settings.FIGURE_ICON_BIG_SCALE*settings.FRAME_FIGURE_SCALE*castle_scale_factor)

            self.set_position(x, y, -settings.get_x(0.00), +settings.get_y(0.005))

        self.family = fig_fam
        self.game = game
        self.content = fig_fam.figures

    def is_in_hand(self, suit=None):
        """Check if the figure can be built with the cards available in hand."""
        if self.game is not None:
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

    def update(self):
        """Update the figure icon with game-specific logic."""
        super().update()
        self.is_active = self.is_in_hand()
