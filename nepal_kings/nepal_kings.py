# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
import asyncio
import pygame
import copy
from types import SimpleNamespace
#from pygame.locals import *
from game.screens.login_screen import LoginScreen
from game.screens.game_menu_screen import GameMenuScreen
from game.screens.duel_menu_screen import DuelMenuScreen
from game.screens.new_game_screen import NewGameScreen
from game.screens.load_game_screen import LoadGameScreen
from game.screens.ranking_screen import RankingScreen
from game.screens.settings_screen import SettingsScreen
from game.screens.kingdom_screen import KingdomScreen
from game.screens.kingdom_config_screen import KingdomConfigScreen
from game.screens.conquer_screen import ConquerScreen
from game.screens.defence_screen import DefenceScreen
from game.screens.collection_screen import CollectionScreen
from game.screens.game_screen import GameScreen
from game.screens.conquer_game_screen import ConquerGameScreen
from game.core.state import State
from game.core.input_state import process_events as _process_input
from config import settings
from utils.perf_monitor import PerfMonitor
from utils import web_wheel as _web_wheel
import os
#import sys
#import requests

class Client:
    def __init__(self):
        pygame.init()
        self.clock = pygame.time.Clock()
        self.running = True
        self.perf = PerfMonitor()

        self.state = State()

        # Capture native desktop resolution BEFORE creating the game window
        _info = pygame.display.Info()
        self.state.native_screen_w = _info.current_w
        self.state.native_screen_h = _info.current_h

        # ── Loading screen with progress bar ────────────────────────
        _SW, _SH = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT
        window = pygame.display.set_mode((_SW, _SH))
        pygame.display.set_caption(settings.SCREEN_CAPTION)

        # Set window icon
        _icon_path = os.path.join(os.path.dirname(__file__), 'img', 'app_icon', 'icon_128x128.png')
        if os.path.exists(_icon_path):
            pygame.display.set_icon(pygame.image.load(_icon_path))

        # Background – share the greyscale login background (cached)
        bg = LoginScreen._load_bg()

        # Fonts
        title_font = settings.get_font(settings.GAME_MENU_TITLE_FONT_SIZE, bold=True)
        title_surf = title_font.render('Nepal Kings', True, settings.GAME_MENU_TITLE_CLR)
        status_font = settings.get_font(int(0.022 * _SH))

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
            ('login',      'Loading login …',       LoginScreen,      1),
            ('game_menu',  'Loading menu …',         GameMenuScreen,   1),
            ('duel_menu',  'Loading duel menu …',    DuelMenuScreen,   1),
            ('new_game',   'Loading new game …',     NewGameScreen,    1),
            ('load_game',  'Loading load game …',    LoadGameScreen,   1),
            ('rankings',   'Loading rankings …',     RankingScreen,    1),
            ('settings',   'Loading settings …',     SettingsScreen,   1),
            ('kingdom',    'Loading kingdom …',      KingdomScreen,    1),
            ('kingdom_config', 'Loading kingdom config …', KingdomConfigScreen, 1),
            ('conquer',    'Loading conquer …',      ConquerScreen,    1),
            ('defence',    'Loading defence …',      DefenceScreen,    1),
            ('collection', 'Loading collection …',   CollectionScreen, 1),
            ('game',       'Loading game …',         GameScreen,      12),
            ('conquer_game', 'Loading conquer battle …', ConquerGameScreen, 8),
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

        if os.environ.get('NK_PERF_FIXTURE') == 'conquer_battle':
            self._init_perf_conquer_fixture(draw_progress)
            return

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

    def _init_perf_conquer_fixture(self, draw_progress):
        draw_progress(0.05, 'Loading active conquer fixture ...')
        player_figures = []
        opponent_figures = []

        def get_figures(_families, is_opponent=False):
            return list(opponent_figures if is_opponent else player_figures)

        def no_op(*_args, **_kwargs):
            return None

        game = SimpleNamespace(
            game_id=None,
            mode='conquer',
            conquer_move_model='tactics_hand',
            state='active',
            player_id=1,
            opponent_id=2,
            player_name='Perf You',
            opponent_name='Perf Opponent',
            players=[
                {'id': 1, 'username': 'Perf You'},
                {'id': 2, 'username': 'Perf Opponent'},
            ],
            opponent_player={'id': 2, 'username': 'Perf Opponent'},
            battle_confirmed=True,
            battle_turn_player_id=1,
            battle_round=1,
            battle_skipped_rounds={},
            battle_moves_confirmed={},
            battle_moves_phase=False,
            battle_moves_ready=False,
            both_battle_moves_ready=False,
            waiting_for_opponent_battle_moves=False,
            waiting_for_battle_decision=False,
            in_battle_phase=True,
            battle_turns_left=3,
            last_battle_result=None,
            advancing_player_id=1,
            advancing_figure_id=10,
            advancing_figure_id_2=None,
            defending_figure_id=20,
            defending_figure_id_2=None,
            land_suit_bonus_suit='Hearts',
            land_suit_bonus_value=2,
            conquer_resolution_step=0,
            conquer_round_deadline_ts=None,
            conquer_round_timeout_sec=None,
            battle_gamble_counts={},
            conquer_tactics=[
                self._perf_tactic(101, 1, 'Sword', 'Hearts', 'Q', 8,
                                  status='played', played_round=0,
                                  call_figure_id=30),
                self._perf_tactic(102, 1, 'Shield', 'Clubs', '9', 3,
                                  status='available'),
                self._perf_tactic(103, 1, 'Dagger', 'Diamonds', 'A', 5,
                                  status='available'),
                self._perf_tactic(201, 2, 'Shield', 'Clubs', '9', 3,
                                  status='played', played_round=0),
                self._perf_tactic(202, 2, 'Dagger', 'Spades', 'K', 4,
                                  status='available'),
                # Opponent's hidden hand (face-down on the right strip).
                self._perf_tactic(203, 2, 'Block', 'Clubs', 'Q', 2,
                                  status='available'),
                self._perf_tactic(204, 2, 'Dagger', 'Spades', '9', 9,
                                  status='available'),
            ],
            cached_active_spells=[],
            cached_figures_data={1: [], 2: []},
            log_entries=[],
            chat_messages=[],
            action_in_progress=False,
            game_over=False,
            pending_game_over=None,
            game_over_shown=False,
            pending_forced_advance=False,
            pending_defender_selection=False,
            pending_conquer_own_defender_selection=False,
            fold_outcome=None,
            fold_winner_id=None,
            _game_data_version=1,
            _figures_data_version=1,
            _conquer_game_entered=True,
            get_figures=get_figures,
            calculate_resources=lambda *_args, **_kwargs: {},
            has_active_all_seeing_eye=lambda: False,
            has_opponent_cast_all_seeing_eye=lambda: False,
            drain_pending_start_turn=no_op,
            check_action_lock_timeout=no_op,
            apply_server_data=no_op,
        )
        self.state.user_dict = {
            'id': 1,
            'username': 'Perf You',
            'gold': 0,
            'booster_packs': 0,
            'booster_packs_side': 0,
        }
        self.state.screen = 'conquer_game'
        self.state.subscreen = 'field'

        draw_progress(0.25, 'Loading conquer fixture screen ...')
        self.state.game = None
        screen = ConquerGameScreen(self.state, progress_callback=draw_progress)
        self.state.game = game
        screen.main_hand.state = self.state
        screen.main_hand.game = game
        screen.side_hand.state = self.state
        screen.side_hand.game = game
        player_figures[:], opponent_figures[:] = self._perf_conquer_figures(
            screen.figure_manager)
        screen._current_game_key = (getattr(game, 'game_id', None), game.player_id)
        screen._request_battle_state_poll = no_op
        screen.update_game = no_op
        screen.check_battle_ready = no_op
        screen.update_interval = 60 * 60 * 1000

        for subscreen in getattr(screen, 'subscreens', {}).values():
            if hasattr(subscreen, 'game'):
                subscreen.game = game

        field = screen.subscreens.get('field')
        if field is not None:
            field.load_figures()
            field._last_figures_version = game._figures_data_version
            field._last_conquer_visual_ghost_key = field._conquer_visual_ghost_key()
            field._last_conquer_spell_replay_key = field._conquer_spell_replay_visibility_key()

        self.screens = {'conquer_game': screen}
        draw_progress(1.0, 'Ready')

    @staticmethod
    def _perf_tactic(move_id, player_id, family, suit, rank, value,
                     *, status='available', played_round=None,
                     call_figure_id=None):
        return {
            'id': move_id,
            'player_id': player_id,
            'card_id': move_id + 1000,
            'family_name': family,
            'suit': suit,
            'rank': rank,
            'value': value,
            'status': status,
            'played_round': played_round,
            'call_figure_id': call_figure_id,
            'source': 'perf_fixture',
        }

    @staticmethod
    def _perf_conquer_figures(figure_manager):
        def clone(name, suit, figure_id, player_id):
            candidates = figure_manager.get_figures_by_name(name)
            template = next(
                (figure for figure in candidates if figure.suit == suit),
                candidates[0] if candidates else None,
            )
            if template is None:
                raise RuntimeError(f'Perf fixture figure not found: {name}')
            figure = copy.copy(template)
            figure.id = figure_id
            figure.player_id = player_id
            figure.active_enchantments = []
            figure.has_deficit = False
            return figure

        player_figures = [
            clone('Gorkha Warriors', 'Hearts', 10, 1),
            clone('Djungle Healer', 'Hearts', 30, 1),
            clone('Djungle Archer', 'Spades', 31, 1),
            clone('Himalaya King', 'Hearts', 32, 1),
            clone('Large Rice Farm', 'Diamonds', 33, 1),
        ]
        opponent_figures = [
            clone('Wall', 'Hearts', 20, 2),
            clone('Wall', 'Clubs', 40, 2),
            clone('Djungle King', 'Hearts', 41, 2),
            clone('Djungle Temple', 'Spades', 42, 2),
            clone('Small Yack Farm', 'Diamonds', 43, 2),
        ]
        return player_figures, opponent_figures

    def get_events(self):
        events = _web_wheel.merge_events(pygame.event.get())
        _process_input(events)
        return events

    async def run_screen(self, screen):
        scr = self.screens[screen]
        if hasattr(scr, 'on_enter'):
            scr.on_enter()
        while self.state.screen == screen:
            if not self.perf.enabled:
                events = self.get_events()

                self.screens[screen].handle_events(events)
                self.screens[screen].update(events)
                self.screens[screen].render()

                self.state.update()
                pygame.display.update()
                self.clock.tick(60)
                await asyncio.sleep(0)
                continue

            self.perf.frame_start(self._perf_context(scr))
            with self.perf.section('events'):
                events = self.get_events()
            with self.perf.section('handle_events'):
                self.screens[screen].handle_events(events)
            with self.perf.section('update'):
                self.screens[screen].update(events)
            with self.perf.section('render'):
                self.screens[screen].render()
            with self.perf.section('state_update'):
                self.state.update()
            with self.perf.section('display_update'):
                pygame.display.update()
            self.perf.frame_end()
            self.clock.tick(60)
            await asyncio.sleep(0)

    def _perf_context(self, scr):
        if not self.perf.enabled:
            return None
        context = {
            'screen': self.state.screen,
            'subscreen': getattr(self.state, 'subscreen', None),
        }
        for name, key in (
                ('_conquer_layout_mode', 'conquer_layout'),
                ('_is_battle_phase_active', 'battle_active')):
            getter = getattr(scr, name, None)
            if callable(getter):
                try:
                    context[key] = getter()
                except Exception:
                    pass
        return context

    async def run(self):
        while self.running:
            print(self.state.screen)
            if self.state.screen == 'restart':
                self._restart_game()
                return
            elif self.state.screen in self.screens:
                await self.run_screen(self.state.screen)
            else:
                self.running = False

    @staticmethod
    def _restart_game():
        """Restart the process so the new resolution takes effect."""
        import sys as _sys
        if _sys.platform == "emscripten":
            try:
                from platform import window
                window.location.reload()
            except Exception:
                pass
            return
        pygame.quit()
        python = _sys.executable
        os.execv(python, [python] + _sys.argv)
            #elif self.state.screen == 'new_game':
            #    self.screens['new_game'] = NewGameScreen(self.state)

if __name__ == '__main__':
    client = Client()
    asyncio.run(client.run())
