import pygame
from pygame.locals import *
from Screen import Screen
import settings
from CardImg import CardImg
from Hand import Hand
from utils import GameButton
import requests
from BuildFigureScreen import BuildFigureScreen


class GameScreen(Screen):
    def __init__(self, state):
        super().__init__(state)

        self.main_hand = Hand(self.window, self.state.game, x=settings.MAIN_HAND_X, y=settings.MAIN_HAND_Y)
        self.side_hand = Hand(self.window, self.state.game, x=settings.SIDE_HAND_X, y=settings.SIDE_HAND_Y, type="side_card")

        self.game_buttons += self.initialize_buttons()

        self.visible_screen = 'build_figure'
        self.main_screens = {'field': None,
                             'build_figure': BuildFigureScreen(self.window, self.state, x=settings.MAIN_SCREEN_X, y=settings.MAIN_SCREEN_Y)}


    def initialize_buttons(self):
        buttons = []

        # Hand button
        buttons += self.main_hand.buttons
        buttons += self.side_hand.buttons

        # Action Button
        buttons.append(GameButton(self.window, 'book', 'plant',
                                  settings.ACTION_BUTTON_X, settings.ACTION_BUTTON_Y,
                                  settings.ACTION_BUTTON_WIDTH,
                                  settings.ACTION_BUTTON_WIDTH,
                                  state=self.state,
                                  hover_text='cast spell!'))

        # Build Button
        buttons.append(GameButton(self.window, 'hammer', 'rope',
                                  settings.BUILD_BUTTON_X, settings.BUILD_BUTTON_Y,
                                  settings.BUILD_BUTTON_WIDTH,
                                  settings.BUILD_BUTTON_WIDTH,
                                  state=self.state,
                                  hover_text='build figure!',
                                  subscreen='build_figure'))

        return buttons


    #def update_hand(self):
    #    self.state.game.update_hand()

    def update_game(self):
        self.state.game.update()
        self.main_hand.update(self.state.game)
        self.side_hand.update(self.state.game)

    def render(self):

        self.window.fill(settings.BACKGROUND_COLOR)

        self.draw_text(self.state.game.opponent_name, settings.BLACK, settings.get_x(0.1), settings.get_x(0.1))

        for button in self.game_buttons:
            button.draw()
        self.side_hand.draw()
        self.main_hand.draw()

        if self.visible_screen in self.main_screens:
            self.main_screens[self.visible_screen].draw()
        super().render()

        pygame.display.update()

    def update(self, events):
        super().update()

        #self.main_hand.update(self.state.game)
        #self.side_hand.update(self.state.game)

        current_time = pygame.time.get_ticks()
        if current_time - self.last_update_time >= self.update_interval:
            self.update_game()

        self.main_screens['build_figure'].update(self.state.game)

    def handle_events(self, events):
        super().handle_events(events)

        self.main_hand.handle_events(events)
        self.side_hand.handle_events(events)
