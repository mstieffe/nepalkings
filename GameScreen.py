import pygame
from pygame.locals import *
from Screen import Screen
import settings
from CardImg import CardImg
from Hand import Hand
from utils import Button
import requests


class GameScreen(Screen):
    def __init__(self, state):
        super().__init__(state)

        # initialize CardImgs
        #self.card_imgs = {}
        #for suit in settings.SUITS:
        #    for rank in settings.RANKS:
        #        self.card_imgs[(suit, rank)] = CardImg(self.window, suit, rank)

        self.hand = Hand(self.window, self.state.game, x=0.1, y=0.6)
    #def update_hand(self):
    #    self.state.game.update_hand()

    def update_game(self):
        self.state.game.update()
        self.hand.update(self.state.game)

    def render(self):

        self.window.fill(settings.BACKGROUND_COLOR)

        self.draw_text(self.state.game.opponent_name, settings.BLACK, settings.get_x(0.1), settings.get_x(0.1))

        #self.draw_text(str(len(self.state.game.get_hand())), settings.BLACK, settings.get_x(0.5), settings.get_x(0.1))
        self.hand.draw()
        #for i, card in enumerate(self.state.game.get_hand()):
        #    self.draw_text(card['suit']+" "+card['rank'], settings.BLACK, settings.get_x(0.1), settings.get_x(0.1)+i*settings.SMALL_SPACER_X)

        super().render()

        pygame.display.update()

    def update(self, events):
        super().update()

        self.hand.update(self.state.game)

        current_time = pygame.time.get_ticks()
        if current_time - self.last_update_time >= self.update_interval:
            self.update_game()

    def handle_events(self, events):
        super().handle_events(events)

        self.hand.handle_events(events)


        #for button in self.challenge_buttons + self.open_challenge_buttons:
        #    button.update_color()

        #for event in events:
        #    if event.type == MOUSEBUTTONDOWN:


        #    self.reset_action()

