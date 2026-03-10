import pygame
#from pygame.locals import *
from game.screens.login_screen import LoginScreen
from game.screens.game_menu_screen import GameMenuScreen
from game.screens.new_game_screen import NewGameScreen
from game.screens.load_game_screen import LoadGameScreen
from game.screens.ranking_screen import RankingScreen
from game.screens.settings_screen import SettingsScreen
from game.screens.game_screen import GameScreen
from game.core.state import State
from config import settings
import os
#import sys
#import requests

class Client:
    def __init__(self):
        pygame.init()
        self.clock = pygame.time.Clock()
        self.running = True

        self.state = State()

        # Capture native desktop resolution BEFORE creating the game window
        _info = pygame.display.Info()
        self.state.native_screen_w = _info.current_w
        self.state.native_screen_h = _info.current_h

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
        # weight = relative time cost (used for smooth progress)
        screen_steps = [
            ('login',     'Loading login …',      LoginScreen,    1),
            ('game_menu', 'Loading menu …',        GameMenuScreen, 1),
            ('new_game',  'Loading new game …',    NewGameScreen,  1),
            ('load_game', 'Loading load game …',   LoadGameScreen, 1),
            ('rankings',  'Loading rankings …',    RankingScreen,  1),
            ('settings',  'Loading settings …',    SettingsScreen, 1),
            ('game',      'Loading game …',        GameScreen,    12),
        ]
        total_weight = sum(w for *_, w in screen_steps)

        def draw_progress(fraction, label):
            """Draw the progress bar.  fraction is 0.0 – 1.0."""
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
            fill_w = int(bar_w * min(fraction, 1.0))
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
        weight_done = 0
        for key, label, cls, weight in screen_steps:
            frac_start = weight_done / total_weight
            frac_end = (weight_done + weight) / total_weight
            draw_progress(frac_start, label)

            # For heavy screens, pass a sub-progress callback
            if weight > 1:
                def _sub_progress(sub_frac, sub_label, _s=frac_start, _e=frac_end, _lbl=label):
                    f = _s + (_e - _s) * sub_frac
                    draw_progress(f, sub_label or _lbl)
                self.screens[key] = cls(self.state, progress_callback=_sub_progress)
            else:
                self.screens[key] = cls(self.state)

            weight_done += weight
            draw_progress(frac_end, label)

        draw_progress(1.0, 'Ready')

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
            if self.state.screen == 'restart':
                self._restart_game()
                return
            elif self.state.screen in self.screens:
                #if self.state.screen == 'new_game':
                #    self.screens['new_game'].update_users()
                #    self.screens['new_game'] = NewGameScreen(self.state)
                self.run_screen(self.state.screen)
            else:
                self.running = False

    @staticmethod
    def _restart_game():
        """Restart the process so the new resolution takes effect."""
        import sys as _sys
        pygame.quit()
        python = _sys.executable
        os.execv(python, [python] + _sys.argv)
            #elif self.state.screen == 'new_game':
            #    self.screens['new_game'] = NewGameScreen(self.state)

if __name__ == '__main__':
    client = Client()
    client.run()