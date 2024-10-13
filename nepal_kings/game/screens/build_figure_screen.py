import pygame
from game.components.card_img import CardImg
from game.components.card_slot import CardSlot
from config import settings
from utils.utils import GameButton
from game.components.buttons import FigureIconButton, ButtonListShifter, SuitIconButton
from game.components.figure import Figure, FigureManager

class BuildFigureScreen:
    """Hand class for pygame application. This class represents a hand of cards."""

    def __init__(self, window, game, x: int = 0.0, y: int = 0.0):
        self.window = window
        self.font = pygame.font.Font(settings.FONT_PATH, settings.FONT_SIZE_DETAIL)
        self.game = game
        self.x = x
        self.y = y

        self.icon_start_index = 0

        self.figure_manager = FigureManager()
        self.initialize_icon_buttons()
        self.initilialize_suit_buttons()

        self.initialize_background_attributes()

        self.selected_figures = []
        self.selected_suits = []


        print("hier geht es los")
        for name in self.figure_manager.figures_by_name.keys():
            print(name)
            print("-------")


    #def update_selected_figures(self):
    #    self.selected_figures = []
    #    for button in self.icon_buttons:
    #        if button.clicked:
    #            self.selected_figures += button.content

    #def update_selected_suit(self):
    #    for button in self.suit_buttons:
    #        if button.clicked:
    #            self.selected_suits += button.suit

    def initialize_background_attributes(self):

        self.background_image_width = settings.BUILD_FIGURE_BACKGROUND_IMG_WIDTH
        self.background_image_height = settings.BUILD_FIGURE_BACKGROUND_IMG_HEIGHT

        self.background_image = pygame.image.load(settings.BUILD_FIGURE_BACKGROUND_IMG_PATH)


        self.background_image = pygame.transform.scale(self.background_image,
                                                       (self.background_image_width,
                                                        self.background_image_height))

    def initialize_icon_buttons(self):

        #icon_mask_img = pygame.image.load(settings.FIGURE_ICON_IMG_PATH+ 'mask.png')
        #icon_mask_img = pygame.transform.scale(icon_mask_img, (settings.FIGURE_ICON_MASK_WIDTH, settings.FIGURE_ICON_MASK_HEIGHT))

        self.icon_buttons = []
        for fig_name in self.figure_manager.figures_by_name.keys():
            if not "Altar" in fig_name:
                fig = self.figure_manager.figures_by_name[fig_name][0]
                self.icon_buttons.append(FigureIconButton(self.window, self.game, fig, self.figure_manager.figures_by_name[fig_name], self.x , self.y))
        x = self.x + settings.BUILD_FIGURE_BACKGROUND_IMG_WIDTH * 0.28
        y = self.y + settings.BUILD_FIGURE_BACKGROUND_IMG_HEIGHT * 0.68
        dx = settings.FIGURE_ICON_DELTA_X
        self.icon_buttons_shifter = ButtonListShifter(self.window, self.icon_buttons, x, y, dx, num_buttons_displayed=4, title='Choose a figure family!', title_offset_y=settings.get_y(0.07))
        #self.update_displayed_icon_buttons()


    def initilialize_suit_buttons(self):

        self.suit_buttons = []
        for suit in ['spades', 'hearts', 'diamonds', 'clubs']:
            self.suit_buttons.append(SuitIconButton(self.window, self.game, suit, self.x, self.y))
        x = self.x + settings.BUILD_FIGURE_BACKGROUND_IMG_WIDTH * 0.28
        y = self.y + settings.BUILD_FIGURE_BACKGROUND_IMG_HEIGHT * 0.3
        dx = settings.FIGURE_ICON_DELTA_X
        self.suit_buttons_shifter = ButtonListShifter(self.window, self.suit_buttons, x, y, dx, num_buttons_displayed=4, title="Choose a kingdom!")

    def draw_text(self, text, color, x, y):
        """Draw text on the window."""
        text_obj = self.font.render(text, True, color)
        text_rect = text_obj.get_rect()
        text_rect.topleft = (x, y)
        self.window.blit(text_obj, text_rect)

    def update(self, game):
        """Update the game state."""
        self.game = game
        self.icon_buttons_shifter.update(game)
        self.suit_buttons_shifter.update(game)
        #for button in self.icon_buttons:
        #    button.update(game)


    def handle_events(self, events):
        self.icon_buttons_shifter.handle_events(events)
        self.suit_buttons_shifter.handle_events(events)

    def draw(self):
        """Draw elements on the window."""
        if self.game:
            self.window.blit(self.background_image, (self.x, self.y))

            self.icon_buttons_shifter.draw()
            self.suit_buttons_shifter.draw()
            #for button in self.displayed_icon_buttons:
            #    button.draw()
            #for i, fig in enumerate(self.icon_buttons[6:]):
            #    if not "Altar" in fig.name:
            #        fig.draw_icon(self.window, self.x + i*settings.FIGURE_ICON_DELTA_X, self.y)



