import pygame
#from pygame.locals import *
from game.screens.login_screen import LoginScreen
from game.screens.game_menu_screen import GameMenuScreen
from game.screens.new_game_screen import NewGameScreen
from game.screens.load_game_screen import LoadGameScreen
from game.screens.ranking_screen import RankingScreen
from game.screens.game_screen import GameScreen
from game.core.state import State
from config import settings
#import sys
#import requests

class Client:
    def __init__(self):
        pygame.init()
        self.clock = pygame.time.Clock()
        self.running = True

        self.state = State()

        # ── Loading screen with progress bar ────────────────────────
        _SW, _SH = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT
        window = pygame.display.set_mode((_SW, _SH))
        pygame.display.set_caption(settings.SCREEN_CAPTION)

        # Background – reuse the greyscale login background
        raw_bg = pygame.image.load(settings.LOGIN_BG_IMG_PATH).convert()
        bg = pygame.transform.smoothscale(raw_bg, (_SW, _SH))

        # Fonts
        title_font = pygame.font.Font(settings.FONT_PATH, settings.GAME_MENU_TITLE_FONT_SIZE)
        title_font.set_bold(True)
        title_surf = title_font.render('Nepal Kings', True, settings.GAME_MENU_TITLE_CLR)
        status_font = pygame.font.Font(settings.FONT_PATH, int(0.022 * _SH))

        # Bar geometry
        bar_w = int(0.36 * _SW)
        bar_h = int(0.022 * _SH)
        bar_x = (_SW - bar_w) // 2
        bar_y = _SH // 2 + int(0.04 * _SH)
        bar_border_clr = (180, 160, 130)
        bar_fill_clr   = (250, 221, 0)
        bar_bg_clr     = (35, 35, 40)
        status_clr     = (200, 185, 150)

        # Screen constructors in load order
        screen_steps = [
            ('login',     'Loading login …',      LoginScreen),
            ('game_menu', 'Loading menu …',        GameMenuScreen),
            ('new_game',  'Loading new game …',    NewGameScreen),
            ('load_game', 'Loading load game …',   LoadGameScreen),
            ('rankings',  'Loading rankings …',    RankingScreen),
            ('game',      'Loading game …',        GameScreen),
        ]
        total = len(screen_steps)

        def draw_progress(step_index, label):
            surf = pygame.display.get_surface()
            surf.blit(bg, (0, 0))
            # Title
            surf.blit(title_surf,
                      ((_SW - title_surf.get_width()) // 2,
                       _SH // 2 - int(0.06 * _SH)))
            # Status text
            stat = status_font.render(label, True, status_clr)
            surf.blit(stat, ((_SW - stat.get_width()) // 2,
                             bar_y - stat.get_height() - int(0.008 * _SH)))
            # Bar background
            pygame.draw.rect(surf, bar_bg_clr,
                             (bar_x, bar_y, bar_w, bar_h), border_radius=4)
            # Bar fill
            fill_w = int(bar_w * (step_index / total))
            if fill_w > 0:
                pygame.draw.rect(surf, bar_fill_clr,
                                 (bar_x, bar_y, fill_w, bar_h), border_radius=4)
            # Bar border
            pygame.draw.rect(surf, bar_border_clr,
                             (bar_x, bar_y, bar_w, bar_h), 1, border_radius=4)
            pygame.display.flip()
            # Keep the window responsive
            pygame.event.pump()

        self.screens = {}
        for i, (key, label, cls) in enumerate(screen_steps):
            draw_progress(i, label)
            self.screens[key] = cls(self.state)
            draw_progress(i + 1, label)

        draw_progress(total, 'Ready')

    def get_events(self):
        return pygame.event.get()

    def run_screen(self, screen):
        while self.state.screen == screen:
            events = self.get_events()

            self.screens[screen].handle_events(events)
            self.screens[screen].update(events)
            self.screens[screen].render()

            self.state.update()
            pygame.display.update()
            self.clock.tick(60)

    def run(self):
        while self.running:
            print(self.state.screen)
            if self.state.screen in self.screens:
                #if self.state.screen == 'new_game':
                #    self.screens['new_game'].update_users()
                #    self.screens['new_game'] = NewGameScreen(self.state)
                self.run_screen(self.state.screen)
            else:
                self.running = False
            #elif self.state.screen == 'new_game':
            #    self.screens['new_game'] = NewGameScreen(self.state)

if __name__ == '__main__':
    client = Client()
    client.run()