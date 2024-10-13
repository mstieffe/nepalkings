from config import settings
import pygame
from collections import Counter
import math

class ButtonListShifter():

    def __init__(self, window, button_list, x, y, delta_x, num_buttons_displayed=4, title='', title_offset_y=settings.get_y(0.05)):

        self.window = window
        self.button_list = button_list
        self.x = x
        self.y = y
        self.delta_x = delta_x
        self.num_buttons_displayed = num_buttons_displayed

        self.title = title
        self.font = pygame.font.Font(settings.FONT_PATH, settings.GAME_BUTTON_FONT_SIZE)
        self.text_surface = self.font.render(self.title, True,
                                                    settings.SUIT_ICON_CAPTION_COLOR)  # Prepare the text surface
        self.text_rect = self.text_surface.get_rect()  # Get the rectangle for positioning text
        self.title_width = self.text_surface.get_width()
        title_x = self.x + (self.num_buttons_displayed - 1) * self.delta_x / 2
        self.text_rect.center = (title_x, self.y - title_offset_y)

        self.displayed_buttons = []
        self.start_index = 0

        self.arrow_left_button = ArrowButton(self.window, self.shift_left, x=self.x - self.delta_x*0.7, y=self.y, direction='left', is_active=True)
        self.arrow_right_button = ArrowButton(self.window, self.shift_left, x=self.x + self.delta_x * (num_buttons_displayed-1) + self.delta_x*0.7, y=self.y, direction='right', is_active=True)

        self.active_button = None

    def shift_left(self):
        self.start_index = (self.start_index + 1) % len(self.button_list)
        self.update_displayed_buttons()

    def shift_right(self):
        self.start_index = (self.start_index - 1) % len(self.button_list)
        self.update_displayed_buttons()

    def update_displayed_buttons(self):
        indices = [(self.start_index + i) % len(self.button_list) for i in range(self.num_buttons_displayed)]
        self.displayed_buttons = [self.button_list[i] for i in indices]

        for i, button in enumerate(self.displayed_buttons):
            button.set_position(self.x + i * self.delta_x, self.y)

    def draw(self):
        if self.num_buttons_displayed < len(self.button_list):
            self.arrow_left_button.draw()
            self.arrow_right_button.draw()
        for button in self.displayed_buttons:
            button.draw()


        self.window.blit(self.text_surface, self.text_rect)

    def update(self, game):
        self.arrow_left_button.update()
        self.arrow_right_button.update()
        self.update_displayed_buttons()
        for button in self.displayed_buttons:
            button.update(game)



    def handle_events(self, events):

        for button in self.displayed_buttons:
            button.handle_events(events)
            """
            if button.clicked:
                if button is self.active_button:
                    # If the clicked button is the currently active button, deactivate it
                    #button.clicked = False
                    self.active_button = None
                elif self.active_button is not None:
                    # If the clicked button is not the currently active button and there is an active button, deactivate the active button
                    self.active_button.clicked = False
                    self.active_button = button
                else:
                    # If the clicked button is not the currently active button and there is no active button, make the clicked button the active button
                    self.active_button = button
            """

        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN:
                if self.arrow_left_button.hovered:
                    self.arrow_left_button.callback()
                elif self.arrow_right_button.hovered:
                    self.arrow_right_button.callback()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_LEFT:
                    self.start_index = (self.start_index - 1) % len(self.button_list)
                    self.update_displayed_buttons()
                elif event.key == pygame.K_RIGHT:
                    self.start_index = (self.start_index + 1) % len(self.button_list)
                    self.update_displayed_buttons()

class ArrowButton:

    def __init__(self, window, callback, x=0, y=0 ,direction='right', is_active=True):
        self.window = window
        self.x = x
        self.y = y
        self.callback = callback

        # Load arrow image
        arrow_image = settings.LEFT_ARROW_IMG_PATH if direction == 'left' else settings.RIGHT_ARROW_IMG_PATH
        image_arrow = pygame.image.load(arrow_image)

        self.image_arrow = pygame.transform.scale(image_arrow, (settings.ARROW_WIDTH, settings.ARROW_HEIGHT))
        self.image_arrow_big = pygame.transform.scale(image_arrow, (settings.ARROW_BIG_WIDTH, settings.ARROW_BIG_HEIGHT))


        self.image_glow_yellow = pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH +'yellow.png')
        self.image_glow_white = pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH +'white.png')
        self.image_glow_black = pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH +'black.png')
        self.image_glow_orange = pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH + 'orange.png')

        self.image_glow_yellow = pygame.transform.scale(self.image_glow_yellow, (settings.ARROW_GLOW_WIDTH, settings.ARROW_GLOW_WIDTH))
        self.image_glow_white = pygame.transform.scale(self.image_glow_white, (settings.ARROW_GLOW_WIDTH, settings.ARROW_GLOW_WIDTH))
        self.image_glow_black = pygame.transform.scale(self.image_glow_black, (settings.ARROW_GLOW_WIDTH, settings.ARROW_GLOW_WIDTH))
        self.image_glow_orange = pygame.transform.scale(self.image_glow_orange, (settings.ARROW_GLOW_WIDTH, settings.ARROW_GLOW_WIDTH))


        self.image_glow_yellow_big = pygame.transform.scale(self.image_glow_yellow, (settings.ARROW_GLOW_BIG_WIDTH, settings.ARROW_GLOW_BIG_WIDTH))
        self.image_glow_white_big = pygame.transform.scale(self.image_glow_white, (settings.ARROW_GLOW_BIG_WIDTH, settings.ARROW_GLOW_BIG_WIDTH))
        self.image_glow_orange_big = pygame.transform.scale(self.image_glow_orange, (settings.ARROW_GLOW_BIG_WIDTH, settings.ARROW_GLOW_BIG_WIDTH))

        self.rect_arrow = self.image_arrow.get_rect()
        self.rect_glow = self.image_glow_yellow.get_rect()
        self.rect_arrow_big = self.image_arrow_big.get_rect()
        self.rect_glow_big = self.image_glow_yellow_big.get_rect()


        self.rect_arrow.center = (self.x, self.y)
        self.rect_glow.center = (self.x - settings.ARROW_WIDTH*0.2, self.y)
        self.rect_arrow_big.center = (self.x, self.y)
        self.rect_glow_big.center = (self.x - settings.ARROW_WIDTH*0.2, self.y)

        # Initialize button states
        self.clicked = False
        self.hovered = False
        self.is_active = is_active

    def set_position(self, x, y):
        self.x = x
        self.y = y
        self.rect_arrow.center = (self.x, self.y)
        self.rect_glow.center = (self.x, self.y)
        self.rect_arrow_big.center = (self.x, self.y)
        self.rect_glow_big.center = (self.x, self.y)



    def collide(self):
        mx, my = pygame.mouse.get_pos()
        return self.rect_arrow.collidepoint((mx, my))

    def draw(self):
            if self.is_active:
                arrow_img = self.image_arrow
                arrow_big_img = self.image_arrow_big
                glow_img = self.image_glow_yellow
                glow_big_img = self.image_glow_orange_big
            else:
                arrow_img = self.image_arrow
                arrow_big_img = self.image_arrow_big
                glow_img = self.image_glow_black
                glow_big_img = self.image_glow_white_big

            if self.hovered:
                if self.clicked:
                    self.window.blit(glow_big_img, self.rect_glow_big.topleft)
                    self.window.blit(arrow_img, self.rect_arrow.topleft)
                else:
                    self.window.blit(glow_img, self.rect_glow.topleft)
                    self.window.blit(arrow_big_img, self.rect_arrow_big.topleft)

            else:
                self.window.blit(arrow_img, self.rect_arrow.topleft)

    def update(self):
        self.hovered = self.collide()

        if self.hovered and pygame.mouse.get_pressed()[0]:
            self.clicked = True
            #self.callback()
        else:
            self.clicked = False


class FigureIconButton:

    def __init__(self,
                 window,
                 game,
                 fig,
                 content,
                 x: int = 0,
                 y: int = 0):
        self.window = window
        self.game = game
        self.x = x
        self.y = y
        self.fig=fig
        self.content=content
        #self.selected_suits = selected_suits
        self.font = pygame.font.Font(settings.FONT_PATH, settings.FIGURE_ICON_FONT_CAPTION_FONT_SIZE)
        self.font_big = pygame.font.Font(settings.FONT_PATH, settings.FIGURE_ICON_FONT_CAPTION_BIG_FONT_SIZE)

        self.is_active = False

        icon_mask_img = pygame.image.load(settings.FIGURE_ICON_IMG_PATH+ 'mask.png')
        self.icon_mask_img = pygame.transform.scale(icon_mask_img, (settings.FIGURE_ICON_MASK_WIDTH, settings.FIGURE_ICON_MASK_HEIGHT))
        self.icon_mask_big_img = pygame.transform.scale(icon_mask_img, (settings.FIGURE_ICON_MASK_BIG_WIDTH, settings.FIGURE_ICON_MASK_BIG_HEIGHT))

        #self.icon_img = self.fig.icon_img
        self.icon_img = pygame.transform.scale(self.fig.icon_img, (settings.FIGURE_ICON_WIDTH, settings.FIGURE_ICON_HEIGHT))
        self.icon_big_img = pygame.transform.scale(self.fig.icon_img, (settings.FIGURE_ICON_BIG_WIDTH, settings.FIGURE_ICON_BIG_HEIGHT))

        self.icon_darkwhite_img = pygame.transform.scale(self.fig.icon_darkwhite_img, (settings.FIGURE_ICON_WIDTH, settings.FIGURE_ICON_HEIGHT))
        self.icon_darkwhite_big_img = pygame.transform.scale(self.fig.icon_darkwhite_img, (settings.FIGURE_ICON_BIG_WIDTH, settings.FIGURE_ICON_BIG_HEIGHT))

        self.image_glow_yellow = pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH +'yellow.png')
        self.image_glow_white = pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH +'white.png')
        self.image_glow_black = pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH +'black.png')
        self.image_glow_orange = pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH + 'orange.png')

        self.image_glow_yellow = pygame.transform.scale(self.image_glow_yellow, (settings.FIGURE_ICON_GLOW_WIDTH, settings.FIGURE_ICON_GLOW_WIDTH))
        self.image_glow_white = pygame.transform.scale(self.image_glow_white, (settings.FIGURE_ICON_GLOW_WIDTH, settings.FIGURE_ICON_GLOW_WIDTH))
        self.image_glow_black = pygame.transform.scale(self.image_glow_black, (settings.FIGURE_ICON_GLOW_WIDTH, settings.FIGURE_ICON_GLOW_WIDTH))
        self.image_glow_orange = pygame.transform.scale(self.image_glow_orange, (settings.FIGURE_ICON_GLOW_WIDTH, settings.FIGURE_ICON_GLOW_WIDTH))


        self.image_glow_yellow_big = pygame.transform.scale(self.image_glow_yellow, (settings.FIGURE_ICON_GLOW_BIG_WIDTH, settings.FIGURE_ICON_GLOW_BIG_WIDTH))
        self.image_glow_white_big = pygame.transform.scale(self.image_glow_white, (settings.FIGURE_ICON_GLOW_BIG_WIDTH, settings.FIGURE_ICON_GLOW_BIG_WIDTH))
        self.image_glow_orange_big = pygame.transform.scale(self.image_glow_orange, (settings.FIGURE_ICON_GLOW_BIG_WIDTH, settings.FIGURE_ICON_GLOW_BIG_WIDTH))

        self.rect_mask= self.icon_mask_img.get_rect()
        self.rect_icon = self.icon_img.get_rect()
        self.rect_glow = self.image_glow_yellow.get_rect()
        self.rect_mask_big= self.icon_mask_big_img.get_rect()
        self.rect_icon_big = self.icon_big_img.get_rect()
        self.rect_glow_big = self.image_glow_yellow_big.get_rect()

        # Adjust positions based on image dimensions
        width_diff_icon = settings.FIGURE_ICON_GLOW_BIG_WIDTH - settings.FIGURE_ICON_WIDTH
        width_diff_mask = settings.FIGURE_ICON_GLOW_BIG_WIDTH - settings.FIGURE_ICON_MASK_WIDTH
        width_diff_glow = settings.FIGURE_ICON_GLOW_BIG_WIDTH - settings.FIGURE_ICON_GLOW_WIDTH
        width_diff_icon_big = settings.FIGURE_ICON_GLOW_BIG_WIDTH - settings.FIGURE_ICON_BIG_WIDTH
        width_diff_mask_big = settings.FIGURE_ICON_GLOW_BIG_WIDTH - settings.FIGURE_ICON_MASK_BIG_WIDTH

        #self.rect_mask.center = (self.x + width_diff_mask//2, self.y + width_diff_mask//2)
        #self.rect_icon.center = (self.x + width_diff_icon//2, self.y + width_diff_icon//2)
        #self.rect_glow.center = (self.x + width_diff_glow//2, self.y + width_diff_glow//2)
        #self.rect_mask_big.center = (self.x + width_diff_mask_big//2, self.y + width_diff_mask_big//2)
        #self.rect_icon_big.center = (self.x + width_diff_icon_big//2, self.y + width_diff_icon_big//2)
        #self.rect_glow_big.center = (self.x, self.y)


        self.rect_mask.center = (self.x, self.y)
        self.rect_icon.center = (self.x, self.y)
        self.rect_glow.center = (self.x, self.y)
        self.rect_mask_big.center = (self.x, self.y)
        self.rect_icon_big.center = (self.x, self.y)
        self.rect_glow_big.center = (self.x, self.y)
        # Initialize button states
        self.clicked = False
        self.hovered = False
        self.time = 0

        self.text_surface = self.font.render(self.fig.name, True,
                                                    settings.SUIT_ICON_CAPTION_COLOR)  # Prepare the text surface
        self.text_surface_big = self.font_big.render(self.fig.name, True,
                                                     settings.SUIT_ICON_CAPTION_COLOR)  # Prepare the text surface

        self.text_rect = self.text_surface.get_rect()  # Get the rectangle for positioning text
        self.text_rect_big = self.text_surface_big.get_rect()  # Get the rectangle for positioning text
        self.text_rect_big.center = (self.x, self.y + settings.FIGURE_ICON_BIG_WIDTH//2 + settings.get_y(0.015))
        self.text_rect.center = (self.x, self.y + settings.FIGURE_ICON_BIG_WIDTH//2 + settings.get_y(0.015))

    def set_position(self, x, y):
        self.x = x
        self.y = y
        self.rect_mask.center = (self.x, self.y)
        self.rect_icon.center = (self.x, self.y)
        self.rect_glow.center = (self.x, self.y)
        self.rect_mask_big.center = (self.x, self.y)
        self.rect_icon_big.center = (self.x, self.y)
        self.rect_glow_big.center = (self.x, self.y)
        self.text_rect_big.center = (self.x, self.y + settings.FIGURE_ICON_BIG_WIDTH//2 + settings.get_y(0.015))
        self.text_rect.center = (self.x, self.y + settings.FIGURE_ICON_BIG_WIDTH//2 + settings.get_y(0.015))

    def is_in_hand(self, suit=None):
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
        mx, my = pygame.mouse.get_pos()
        return self.rect_mask.collidepoint((mx, my))

    def draw(self):
        y_offset = settings.FIGURE_ICON_SIN_AMPL * math.sin(self.time) if self.clicked else 0
        self.window.blit(self.image_glow_white, self.rect_glow.topleft)
        if self.is_active:
            icon_img = self.icon_img
            icon_big_img = self.icon_big_img
            glow_img = self.image_glow_yellow
            glow_big_img = self.image_glow_orange_big
        else:
            icon_img = self.icon_darkwhite_img
            icon_big_img = self.icon_darkwhite_big_img
            glow_img = self.image_glow_black
            glow_big_img = self.image_glow_white_big
        if pygame.mouse.get_pressed()[0] and self.hovered:
            self.window.blit(glow_big_img, (self.rect_glow_big.topleft[0], self.rect_glow_big.topleft[1] + y_offset))
            self.window.blit(icon_img, (self.rect_icon.topleft[0], self.rect_icon.topleft[1] + y_offset))
            self.window.blit(self.icon_mask_img, (self.rect_mask.topleft[0], self.rect_mask.topleft[1] + y_offset))
            #self.text_rect.center = (self.x, self.text_y  + y_offset)
            self.window.blit(self.text_surface, (self.text_rect.topleft[0], self.text_rect.topleft[1] + y_offset))
        elif self.clicked and self.hovered:
            self.window.blit(glow_big_img, (self.rect_glow_big.topleft[0], self.rect_glow_big.topleft[1] + y_offset))
            self.window.blit(icon_big_img, (self.rect_icon_big.topleft[0], self.rect_icon_big.topleft[1] + y_offset))
            self.window.blit(self.icon_mask_big_img, (self.rect_mask_big.topleft[0], self.rect_mask_big.topleft[1] + y_offset))
            self.window.blit(self.text_surface_big, (self.text_rect_big.topleft[0], self.text_rect_big.topleft[1] + y_offset))
        elif self.clicked:
            self.window.blit(glow_big_img, (self.rect_glow_big.topleft[0], self.rect_glow_big.topleft[1] + y_offset))
            self.window.blit(icon_img, (self.rect_icon.topleft[0], self.rect_icon.topleft[1] + y_offset))
            self.window.blit(self.icon_mask_img, (self.rect_mask.topleft[0], self.rect_mask.topleft[1] + y_offset))
            self.window.blit(self.text_surface, (self.text_rect.topleft[0], self.text_rect.topleft[1] + y_offset))
        elif self.hovered:
            self.window.blit(glow_img, self.rect_glow.topleft)
            self.window.blit(icon_big_img, self.rect_icon_big.topleft)
            self.window.blit(self.icon_mask_big_img, self.rect_mask_big.topleft)
            self.window.blit(self.text_surface_big, (self.text_rect_big.topleft[0], self.text_rect_big.topleft[1] + y_offset))
        else:
            #self.window.blit(self.image_glow_black, self.rect_glow.topleft)
            self.window.blit(icon_img, self.rect_icon.topleft)
            self.window.blit(self.icon_mask_img, self.rect_mask.topleft)
            self.window.blit(self.text_surface, (self.text_rect.topleft[0], self.text_rect.topleft[1] + y_offset))

    def update(self, game):
        self.game = game
        if self.game:
            if self.clicked:
                self.time += 0.1
            else:
                self.time = 0

            self.is_active = self.is_in_hand()
            #self.game = self.state.game
            #self.game = state.game
            self.hovered = self.collide()

            #if self.is_active and self.hovered and pygame.mouse.get_pressed()[0]:
            #    self.clicked = not self.clicked
            #self.state.subscreen = self.subscreen_trigger
            #else:
            #    self.clicked = False

    def handle_events(self, events):
        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    if self.hovered and self.is_active:
                        self.clicked = not self.clicked


class SuitIconButton:

    def __init__(self,
                 window,
                 game,
                 suit: str,
                 x: int = 0,
                 y: int = 0):
        self.window = window
        self.game = game
        self.x = x
        self.y = y
        self.suit = suit
        self.font = pygame.font.Font(settings.FONT_PATH, settings.FIGURE_ICON_FONT_CAPTION_FONT_SIZE)
        self.font_big = pygame.font.Font(settings.FONT_PATH, settings.FIGURE_ICON_FONT_CAPTION_BIG_FONT_SIZE)

        self.is_active = False

        suit_img_path = settings.SUIT_ICON_IMG_PATH + suit + '.png'
        suit_darkwhite_img_path = settings.SUIT_ICON_DARKWHITE_IMG_PATH + suit + '.png'

        self.icon_original_img = pygame.image.load(suit_img_path)
        self.icon_darkwhite_original_img = pygame.image.load(suit_darkwhite_img_path)

        self.icon_img = pygame.transform.scale(self.icon_original_img, (settings.SUIT_ICON_WIDTH, settings.SUIT_ICON_HEIGHT))
        self.icon_big_img = pygame.transform.scale(self.icon_original_img, (settings.SUIT_ICON_BIG_WIDTH, settings.SUIT_ICON_BIG_HEIGHT))

        self.icon_darkwhite_img = pygame.transform.scale(self.icon_darkwhite_original_img, (settings.SUIT_ICON_WIDTH, settings.SUIT_ICON_HEIGHT))
        self.icon_darkwhite_big_img = pygame.transform.scale(self.icon_darkwhite_original_img, (settings.SUIT_ICON_BIG_WIDTH, settings.SUIT_ICON_BIG_HEIGHT))

        self.image_glow_yellow = pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH +'yellow.png')
        self.image_glow_white = pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH +'white.png')
        self.image_glow_black = pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH +'black.png')
        self.image_glow_orange = pygame.image.load(settings.GAME_BUTTON_GLOW_IMG_PATH + 'orange.png')

        self.image_glow_yellow = pygame.transform.scale(self.image_glow_yellow, (settings.SUIT_ICON_GLOW_WIDTH, settings.SUIT_ICON_GLOW_WIDTH))
        self.image_glow_white = pygame.transform.scale(self.image_glow_white, (settings.SUIT_ICON_GLOW_WIDTH, settings.SUIT_ICON_GLOW_WIDTH))
        self.image_glow_black = pygame.transform.scale(self.image_glow_black, (settings.SUIT_ICON_GLOW_WIDTH, settings.SUIT_ICON_GLOW_WIDTH))
        self.image_glow_orange = pygame.transform.scale(self.image_glow_orange, (settings.SUIT_ICON_GLOW_WIDTH, settings.SUIT_ICON_GLOW_WIDTH))


        self.image_glow_yellow_big = pygame.transform.scale(self.image_glow_yellow, (settings.SUIT_ICON_GLOW_BIG_WIDTH, settings.SUIT_ICON_GLOW_BIG_WIDTH))
        self.image_glow_white_big = pygame.transform.scale(self.image_glow_white, (settings.SUIT_ICON_GLOW_BIG_WIDTH, settings.SUIT_ICON_GLOW_BIG_WIDTH))
        self.image_glow_orange_big = pygame.transform.scale(self.image_glow_orange, (settings.SUIT_ICON_GLOW_BIG_WIDTH, settings.SUIT_ICON_GLOW_BIG_WIDTH))

        self.rect_icon = self.icon_img.get_rect()
        self.rect_glow = self.image_glow_yellow.get_rect()
        self.rect_icon_big = self.icon_big_img.get_rect()
        self.rect_glow_big = self.image_glow_yellow_big.get_rect()


        self.rect_icon.center = (self.x, self.y)
        self.rect_glow.center = (self.x, self.y)
        self.rect_icon_big.center = (self.x, self.y)
        self.rect_glow_big.center = (self.x, self.y)
        # Initialize button states
        self.clicked = False
        self.hovered = False
        self.time = 0

        self.hover_text = self.suit  # Store the hover_text
        self.text_surface = self.font.render(self.hover_text, True,
                                                    settings.SUIT_ICON_CAPTION_COLOR)  # Prepare the text surface
        self.text_surface_big = self.font_big.render(self.hover_text, True,
                                                     settings.SUIT_ICON_CAPTION_COLOR)  # Prepare the text surface

        self.text_rect = self.text_surface.get_rect()  # Get the rectangle for positioning text
        self.text_rect_big = self.text_surface_big.get_rect()  # Get the rectangle for positioning text

        #self.caption_width = self.text_surface.get_width()
        #self.caption_big_width = self.text_surface_big.get_width()
        #self.caption_dx = (self.caption_big_width - self.caption_width)/4
        #self.caption_dx = 0

    def set_position(self, x, y):
        self.x = x
        self.y = y
        self.rect_icon.center = (self.x, self.y)
        self.rect_glow.center = (self.x, self.y)
        self.rect_icon_big.center = (self.x, self.y)
        self.rect_glow_big.center = (self.x, self.y)

    def is_in_hand(self, figs=None):
        main_cards, side_cards = self.game.get_hand()
        cards = main_cards + side_cards
        if figs:
            cards = []
            for fig in figs:
                if fig.suit == self.suit:
                    cards += fig.cards
        else:
            cards = [(card['suit'], card['rank']) for card in cards if card['suit'].lower() == self.suit]

        if cards == []:
            return False
        else:
            return True

    def collide(self):
        mx, my = pygame.mouse.get_pos()
        return self.rect_icon.collidepoint((mx, my))

    def draw(self):
        y_offset = settings.FIGURE_ICON_SIN_AMPL * math.sin(self.time) if self.clicked else 0

        self.window.blit(self.image_glow_white, self.rect_glow.topleft)


        if self.is_active:
            icon_img = self.icon_img
            icon_big_img = self.icon_big_img
            glow_img = self.image_glow_yellow
            glow_big_img = self.image_glow_orange_big
        else:
            icon_img = self.icon_darkwhite_img
            icon_big_img = self.icon_darkwhite_big_img
            glow_img = self.image_glow_black
            glow_big_img = self.image_glow_white_big
        if pygame.mouse.get_pressed()[0] and self.hovered:
            self.window.blit(glow_big_img, (self.rect_glow_big.topleft[0], self.rect_glow_big.topleft[1] + y_offset))
            self.window.blit(icon_img, (self.rect_icon.topleft[0], self.rect_icon.topleft[1] + y_offset))
            self.text_rect.center = (self.x, self.y + settings.get_y(0.05) + y_offset)
            self.window.blit(self.text_surface, self.text_rect)
        elif self.clicked and self.hovered:
            self.window.blit(glow_big_img, (self.rect_glow_big.topleft[0], self.rect_glow_big.topleft[1] + y_offset))
            self.window.blit(icon_big_img, (self.rect_icon_big.topleft[0], self.rect_icon_big.topleft[1] + y_offset))
            self.text_rect_big.center = (self.x, self.y + settings.get_y(0.05) + y_offset)
            self.window.blit(self.text_surface_big, self.text_rect_big)
        elif self.clicked:
            self.window.blit(glow_big_img, (self.rect_glow_big.topleft[0], self.rect_glow_big.topleft[1] + y_offset))
            self.window.blit(icon_img, (self.rect_icon.topleft[0], self.rect_icon.topleft[1] + y_offset))
            self.text_rect.center = (self.x, self.y + settings.get_y(0.05) + y_offset)
            self.window.blit(self.text_surface, self.text_rect)
        elif self.hovered:
            self.window.blit(glow_img, self.rect_glow.topleft)
            self.window.blit(icon_big_img, self.rect_icon_big.topleft)
            self.text_rect_big.center = (self.x , self.y + settings.get_y(0.05) + y_offset)
            self.window.blit(self.text_surface_big, self.text_rect_big)
            #mx, my = pygame.mouse.get_pos()
            #self.text_rect.center = (mx - settings.GAME_BUTTON_TEXT_SHIFT_X +1, my - settings.GAME_BUTTON_TEXT_SHIFT_Y -1)
            #self.window.blit(self.text_surface_shadow, self.text_rect)
            #self.text_rect.center = (mx - settings.GAME_BUTTON_TEXT_SHIFT_X, my - settings.GAME_BUTTON_TEXT_SHIFT_Y)
            #self.window.blit(self.text_surface_active, self.text_rect)
        else:
            #self.window.blit(self.image_glow_black, self.rect_glow.topleft)
            self.window.blit(icon_img, self.rect_icon.topleft)

            #self.text_rect.center = (self.x, self.y - settings.get_y(0.05))
            #self.window.blit(self.text_surface_shadow, self.text_rect)
            self.text_rect.center = (self.x , self.y + settings.get_y(0.05))
            self.window.blit(self.text_surface, self.text_rect)


    def update(self, game):
        self.game = game
        if self.game:
            if self.clicked:
                self.time += 0.1
            else:
                self.time = 0

            self.is_active = self.is_in_hand()
            self.hovered = self.collide()

            #if self.is_active and self.hovered and pygame.mouse.get_pressed()[0]:
            #    self.clicked = not self.clicked


    def handle_events(self, events):
        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    if self.hovered and self.is_active:
                        self.clicked = not self.clicked