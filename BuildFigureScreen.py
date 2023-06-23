import pygame
from CardImg import CardImg
from CardSlot import CardSlot
import settings
from utils import GameButton, FigureIconButton
from Figure import Figure, FigureManager

class BuildFigureScreen:
    """Hand class for pygame application. This class represents a hand of cards."""

    def __init__(self, window, game, x: int = 0.0, y: int = 0.0):
        self.window = window
        self.font = pygame.font.Font(settings.FONT_PATH, settings.FONT_SIZE_DETAIL)
        self.game = game
        self.x = x
        self.y = y

        self.figure_manager = FigureManager()
        self.initialize_icon_buttons()

        self.initialize_background_attributes()

        print("hier geht es los")
        for name in self.figure_manager.figures_by_name.keys():
            print(name)
            print("-------")



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

        self.icon_buttons, i = [], 0
        dx =  settings.BUILD_FIGURE_BACKGROUND_IMG_WIDTH *0.3
        dy = settings.BUILD_FIGURE_BACKGROUND_IMG_HEIGHT * 0.3
        for fig_name in self.figure_manager.figures_by_name.keys():
            if not "Altar" in fig_name:
                fig = self.figure_manager.figures_by_name[fig_name][0]
                self.icon_buttons.append(FigureIconButton(self.window, self.game, fig, self.figure_manager.figures_by_name[fig_name], self.x +dx + i*settings.FIGURE_ICON_DELTA_X, self.y+dy))
                i += 1

    def draw_text(self, text, color, x, y):
        """Draw text on the window."""
        text_obj = self.font.render(text, True, color)
        text_rect = text_obj.get_rect()
        text_rect.topleft = (x, y)
        self.window.blit(text_obj, text_rect)

    def update(self, game):
        """Update the game state."""
        self.game = game
        for button in self.icon_buttons:
            button.update(game)

    def handle_events(self, events):
        """Handle game events."""

    def draw(self):
        """Draw elements on the window."""
        if self.game:
            self.window.blit(self.background_image, (self.x, self.y))

            for button in self.icon_buttons:
                button.draw()
            #for i, fig in enumerate(self.icon_buttons[6:]):
            #    if not "Altar" in fig.name:
            #        fig.draw_icon(self.window, self.x + i*settings.FIGURE_ICON_DELTA_X, self.y)



