# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Conquer battle screen.

This screen owns the in-battle conquer shell.  It deliberately exposes only
the three conquer battle views: field, battle shop, and battle arena.  The
underlying field/shop/battle components are still shared with duel mode, but
the parent navigation, HUD, routing, and input policy are conquer-specific.
"""

import sys

import pygame
from pygame.locals import *

from config import settings
from config.screen_settings import _UI_SCALE
from game.components.cards.hand import Hand
from game.components.figures.figure_manager import FigureManager
from game.screens.battle_screen import BattleScreen
from game.screens.battle_shop_screen import BattleShopScreen
from game.screens.field_screen import FieldScreen
from game.screens.game_screen import GameScreen
from game.screens.screen import Screen
from utils.utils import GameButton


class ConquerGameScreen(GameScreen):
    """Focused conquer battle shell with Field / Battle Shop / Battle tabs."""

    CONQUER_SUBSCREENS = ('field', 'battle_shop', 'battle')
    HEADER_H_FACTOR = 0.075

    def __init__(self, state, progress_callback=None):
        Screen.__init__(self, state)
        _report = progress_callback or (lambda f, l=None: None)
        self.state.parent_screen = self

        self._last_conquer_auto_route_key = None
        self._current_game_key = None
        self._game_poller = None
        self._poller_data_version = 0
        self.update_interval = 2000

        self._last_seen_chat_count = 0
        self._badge_font = settings.get_font(int(0.015 * settings.SCREEN_HEIGHT * _UI_SCALE))

        self._field_unseen_count = 0
        self._last_seen_figure_ids = None
        self._battle_unseen_count = 0
        self._last_seen_battle_round = None

        _report(0.10, 'Loading conquer figures ...')
        self.figure_manager = FigureManager()

        # Hands are kept as data sources for prelude-drawn cards and battle-shop
        # eligibility, but they are not exposed as conquer UI chrome.
        _report(0.20, 'Loading conquer cards ...')
        self.main_hand = Hand(self.window, self.state.game,
                              x=settings.MAIN_HAND_X, y=settings.MAIN_HAND_Y)
        self.side_hand = Hand(self.window, self.state.game,
                              x=settings.SIDE_HAND_X, y=settings.SIDE_HAND_Y,
                              type="side_card")

        _report(0.30, 'Loading conquer tabs ...')
        self.initialize_buttons()
        self.initialize_state_buttons()
        self.display_elements = []

        sub_x, sub_y = self._conquer_subscreen_origin()

        _report(0.45, 'Loading conquer field ...')
        self.subscreens = {
            'field': FieldScreen(
                self.window, self.state,
                x=sub_x, y=sub_y,
                title='Conquer Field',
            ),
        }

        _report(0.60, 'Loading conquer battle shop ...')
        self.subscreens['battle_shop'] = BattleShopScreen(
            self.window, self.state,
            x=sub_x, y=sub_y,
            title='Battle Shop',
        )

        _report(0.75, 'Loading conquer battle arena ...')
        self.subscreens['battle'] = BattleScreen(
            self.window, self.state,
            x=sub_x, y=sub_y,
            title='Battle Arena',
        )

        self.previous_subscreen = None
        self.pending_notifications = []
        self._active_dialogue_type = None

        self.waiting_for_counter_response = False
        self.need_to_respond_to_spell = False
        self.pending_spell_details = None
        self.counter_spell_selector = None
        self._cached_castable_spells = None
        self._pending_spell_fetch_ready = False
        self._last_resolved_spell_id = None

        _report(0.88, 'Loading conquer spells ...')
        from game.components.spells.spell_manager import SpellManager
        self._cached_spell_manager = SpellManager()

        _report(0.95, 'Loading conquer modifiers ...')
        self._battle_modifier_icons = {}
        self._load_battle_modifier_icons()
        self._previous_battle_modifiers = []
        self._just_allowed_spell = False
        self._hovered_battle_modifier = None
        self._seen_conquer_opponent_spell_ids = set()
        self._battle_modifier_font = settings.get_font(settings.GAME_BUTTON_FONT_SIZE)
        self._spell_box_title_font = settings.get_font(settings.BATTLE_SPELL_BOX_TITLE_FONT_SIZE, bold=True)
        self._tooltip_font = settings.get_font(settings.TOOLTIP_FONT_SIZE)

        self._conquer_header_font = settings.get_font(settings.FS_HEADING, bold=True)
        self._conquer_hint_font = settings.get_font(settings.FS_SMALL)
        self._conquer_badge_font = settings.get_font(
            int(0.015 * settings.SCREEN_HEIGHT * _UI_SCALE), bold=True)

        if getattr(self.state, 'subscreen', None) not in self.subscreens:
            self.state.subscreen = 'field'

    def on_enter(self):
        """Mark this screen as the active parent and reset to the field if needed."""
        self.state.parent_screen = self
        self._ensure_conquer_screen_game()
        self._normalize_conquer_subscreen()
        if self.state.game and getattr(self.state.game, '_conquer_game_entered', False) is False:
            self.state.subscreen = 'field'
            self.state.game._conquer_game_entered = True

    # ------------------------------------------------------------------ setup
    def initialize_buttons(self):
        """Create conquer-only tab buttons.

        No hand buttons, build/cast/log/tutorial buttons, or duel home button
        are registered here.  Hidden duel controls therefore cannot update
        ``state.subscreen`` behind the renderer.
        """
        self.game_buttons = []

        self.field_button = GameButton(
            self.window,
            'conquer_view_field',
            'map',
            'plain',
            settings.FIELD_BUTTON_X, settings.FIELD_BUTTON_Y,
            settings.FIELD_BUTTON_WIDTH,
            settings.FIELD_BUTTON_WIDTH,
            glow_width=settings.FIELD_BUTTON_GLOW_WIDTH,
            symbol_width_big=settings.FIELD_BUTTON_WIDTH_BIG,
            glow_width_big=settings.FIELD_BUTTON_GLOW_WIDTH_BIG,
            state=self.state,
            hover_text='field',
            subscreen='field',
            track_turn=False,
            tooltip_anchor='top-left',
        )
        self.battle_shop_button = GameButton(
            self.window,
            'conquer_view_battle_shop',
            'battleshop',
            'plain',
            settings.BATTLE_SHOP_BUTTON_X, settings.BATTLE_SHOP_BUTTON_Y,
            settings.BATTLE_SHOP_BUTTON_WIDTH,
            settings.BATTLE_SHOP_BUTTON_WIDTH,
            glow_width=settings.FIELD_BUTTON_GLOW_WIDTH,
            symbol_width_big=settings.BATTLE_SHOP_BUTTON_WIDTH_BIG,
            glow_width_big=settings.FIELD_BUTTON_GLOW_WIDTH_BIG,
            state=self.state,
            hover_text='battle shop',
            subscreen='battle_shop',
            track_turn=False,
            tooltip_anchor='top-left',
        )
        self.battle_button = GameButton(
            self.window,
            'conquer_view_battle',
            'battle',
            'plain',
            settings.BATTLE_BUTTON_X, settings.BATTLE_BUTTON_Y,
            settings.BATTLE_BUTTON_WIDTH,
            settings.BATTLE_BUTTON_WIDTH,
            glow_width=settings.FIELD_BUTTON_GLOW_WIDTH,
            symbol_width_big=settings.BATTLE_BUTTON_WIDTH_BIG,
            glow_width_big=settings.FIELD_BUTTON_GLOW_WIDTH_BIG,
            state=self.state,
            hover_text='battle',
            subscreen='battle',
            track_turn=False,
            locked=False,
            tooltip_anchor='top-left',
        )

        self.game_buttons.extend([
            self.field_button,
            self.battle_shop_button,
            self.battle_button,
        ])

    def initialize_state_buttons(self):
        """Conquer uses a compact header instead of duel state buttons."""
        return

    def initialiaze_scoareboard_scroll(self):
        """Conquer shell hides the duel scoreboard scroll."""
        return

    def initialize_info_scroll(self):
        """Conquer shell hides the duel resource scroll."""
        return

    def _conquer_subscreen_origin(self):
        """Return the conquer shell's centered, header-safe subscreen origin."""
        x = (settings.SCREEN_WIDTH - settings.SUB_SCREEN_BACKGROUND_IMG_WIDTH) // 2
        header_h = int(settings.SCREEN_HEIGHT * self.HEADER_H_FACTOR)
        y = header_h + int(settings.SCREEN_HEIGHT * 0.018)
        return max(0, x), max(0, y)

    # -------------------------------------------------------------- mode guards
    def _is_conquer_screen_game_valid(self):
        return bool(
            self.state.game and
            getattr(self.state.game, 'mode', 'duel') == 'conquer'
        )

    def _ensure_conquer_screen_game(self):
        """Route accidental duel games back to the duel GameScreen."""
        if self.state.game and getattr(self.state.game, 'mode', 'duel') != 'conquer':
            self.state.screen = 'game'
            return False
        return True

    def _normalize_conquer_subscreen(self):
        if getattr(self.state, 'subscreen', None) not in self.CONQUER_SUBSCREENS:
            self.state.subscreen = 'field'

    def _unlock_conquer_tabs(self):
        for button in (self.field_button, self.battle_shop_button, self.battle_button):
            button.locked = False
            button.locked_clicked = False

    def _lock_battle_tab_if_premature(self):
        """Lock the battle tab until both sides have confirmed the battle.

        The opponent's advancing figure is known from game state as soon as
        figure selection is complete, but it must not be visible until the
        battle actually begins — locking the button prevents early navigation
        to the BattleScreen where the figure would be loaded and displayed.
        Auto-routing (which sets state.subscreen directly) still works because
        it bypasses the button entirely.
        """
        game = self.state.game
        if not game:
            return
        battle_accessible = (
            getattr(game, 'battle_confirmed', False)
            or getattr(game, 'both_battle_moves_ready', False)
        )
        if not battle_accessible:
            self.battle_button.locked = True

    # -------------------------------------------------------------- auto route
    def _conquer_required_tab(self):
        """Return (tab, key) for one-shot automatic routing."""
        game = self.state.game
        if not game:
            return None, None

        if (getattr(game, 'pending_conquer_prelude_target', False)
                or getattr(self.state, 'pending_conquer_prelude_target', None)):
            return 'field', ('field', 'prelude', getattr(game, 'pending_spell_id', None))

        if getattr(game, 'pending_forced_advance', False) and not getattr(game, 'advancing_figure_id', None):
            return 'field', ('field', 'forced_advance', getattr(game, 'current_round', None))

        field_screen = self.subscreens.get('field')
        if (getattr(game, 'pending_defender_selection', False)
                and getattr(game, 'defender_selection_dialogue_shown', False)):
            return 'field', ('field', 'select_defender', getattr(game, 'advancing_figure_id', None))

        if (field_screen and getattr(field_screen, 'conquer_own_defender_mode', False)
                or getattr(game, 'pending_conquer_own_defender_selection', False)):
            return 'field', ('field', 'own_defender', getattr(game, 'advancing_figure_id', None))

        if (getattr(game, 'battle_confirmed', False)
                and getattr(game, 'battle_turn_player_id', None) is not None):
            return 'battle', ('battle', getattr(game, 'battle_round', 0),
                              getattr(game, 'battle_turn_player_id', None))

        if getattr(game, 'both_battle_moves_ready', False):
            return 'battle', ('battle_ready', getattr(game, 'current_round', None))

        if (getattr(game, 'battle_moves_phase', False)
                and not getattr(game, 'battle_moves_ready', False)
                and not getattr(game, 'waiting_for_opponent_battle_moves', False)):
            return 'battle_shop', ('battle_shop', 'moves_phase',
                                   len(getattr(self.subscreens.get('battle_shop'), 'bought_moves', []) or []))

        return None, None

    def _auto_route_conquer_once(self):
        desired, key = self._conquer_required_tab()
        if desired and key != self._last_conquer_auto_route_key:
            self.state.subscreen = desired
            self._last_conquer_auto_route_key = key

    def _conquer_attention_counts(self):
        """Return badge counts for conquer tabs."""
        game = self.state.game
        if not game:
            return {'field': 0, 'battle_shop': 0, 'battle': 0}

        field = 0
        if (getattr(game, 'pending_conquer_prelude_target', False)
                or getattr(self.state, 'pending_conquer_prelude_target', None)
                or (getattr(game, 'pending_forced_advance', False)
                    and not getattr(game, 'advancing_figure_id', None))
                or (getattr(game, 'pending_defender_selection', False)
                    and getattr(game, 'defender_selection_dialogue_shown', False))
                or getattr(game, 'pending_conquer_own_defender_selection', False)
                or getattr(game, 'civil_war_awaiting_second', False)
                or getattr(game, 'civil_war_defender_second', False)):
            field = 1

        shop = 0
        if (getattr(game, 'battle_moves_phase', False)
                and not getattr(game, 'battle_moves_ready', False)
                and not getattr(game, 'waiting_for_opponent_battle_moves', False)):
            shop = 1

        battle = 0
        if (getattr(game, 'battle_confirmed', False)
                and getattr(game, 'battle_turn_player_id', None) is not None):
            battle = 1

        return {'field': field, 'battle_shop': shop, 'battle': battle}

    # ------------------------------------------------------------------- draw
    def _conquer_status_text(self):
        game = self.state.game
        if not game:
            return '', ''

        tier = getattr(game, 'land_tier', None)
        land = f'Tier {tier} Land' if tier else 'Conquer Battle'
        opponent = getattr(game, 'opponent_name', None) or 'Defender'
        role = 'Invader' if getattr(game, 'invader', False) else 'Defender'
        title = f'{land} vs {opponent}'

        desired, _key = self._conquer_required_tab()
        if desired == 'field':
            hint = 'Field action needed'
        elif desired == 'battle_shop':
            hint = 'Confirm battle moves'
        elif desired == 'battle':
            hint = 'Battle ready'
        elif getattr(game, 'waiting_for_opponent_battle_moves', False):
            hint = 'Waiting for opponent moves'
        elif getattr(game, 'turn', False):
            hint = f'{role} turn'
        else:
            hint = f'{role} waiting'
        return title, hint

    def _draw_conquer_shell(self):
        header_h = int(settings.SCREEN_HEIGHT * self.HEADER_H_FACTOR)
        panel = pygame.Surface((settings.SCREEN_WIDTH, header_h), pygame.SRCALPHA)
        panel.fill((24, 22, 18, 230))
        self.window.blit(panel, (0, 0))
        pygame.draw.line(
            self.window, (178, 143, 76),
            (0, header_h - 1), (settings.SCREEN_WIDTH, header_h - 1), 2)

        title, hint = self._conquer_status_text()
        title_surf = self._conquer_header_font.render(title, True, (245, 222, 170))
        hint_surf = self._conquer_hint_font.render(hint, True, (210, 190, 145))
        self.window.blit(title_surf, (settings.get_x(0.035), settings.get_y(0.014)))
        self.window.blit(hint_surf, (settings.get_x(0.035),
                                     settings.get_y(0.014) + title_surf.get_height() + 2))

    def _draw_tab_state(self):
        counts = self._conquer_attention_counts()
        active_map = {
            'field': self.field_button,
            'battle_shop': self.battle_shop_button,
            'battle': self.battle_button,
        }
        for name, button in active_map.items():
            if self.state.subscreen == name:
                pad = max(4, int(settings.SCREEN_WIDTH * 0.003))
                rect = button.rect_symbol.inflate(pad, pad)
                pygame.draw.rect(self.window, (245, 205, 95), rect, 2, border_radius=6)
            if counts.get(name, 0):
                self._draw_button_badge(button, counts[name])

    def render(self):
        self.window.fill(settings.BACKGROUND_COLOR)
        if not self._ensure_conquer_screen_game() or not self.state.game:
            return

        self._normalize_conquer_subscreen()
        self._draw_conquer_shell()

        subscreen = self.subscreens.get(self.state.subscreen)
        if subscreen:
            subscreen.draw()

        for button in self.game_buttons:
            button.draw()
        for button in self.game_buttons:
            if hasattr(button, 'draw_hover_text'):
                button.draw_hover_text()
        self._draw_tab_state()

        # Shared top-level overlays used by the conquer flow.
        if (self.state.subscreen in ('field', 'battle') and subscreen and
                getattr(subscreen, 'figure_detail_box', None)):
            subscreen.figure_detail_box.draw()
        if (self.state.subscreen in ('battle_shop', 'battle') and subscreen and
                getattr(subscreen, 'battle_move_detail_box', None)):
            subscreen.battle_move_detail_box.draw()
        if self.state.subscreen == 'field' and subscreen and getattr(subscreen, 'dialogue_box', None):
            subscreen.dialogue_box.draw()

        subscreen_dialogue_open = bool(subscreen and getattr(subscreen, 'dialogue_box', None))
        in_result_phase = bool(getattr(self.state.game, 'game_over', False)
                               or getattr(self.state.game, 'pending_game_over', False))

        if (self.state.game.pending_forced_advance
                and self.state.game.forced_advance_dialogue_shown
                and not self.dialogue_box
                and not self.state.game.advancing_figure_id):
            self._draw_forced_advance_prompt()

        if (self.state.game.advancing_figure_id
                and self.state.game.advancing_player_id == self.state.game.player_id
                and not self.state.game.turn
                and not self.state.game.defending_figure_id
                and not subscreen_dialogue_open and not in_result_phase):
            self._draw_own_advance_waiting_prompt()

        if (self.state.game.advancing_figure_id
                and self.state.game.advancing_player_id != self.state.game.player_id
                and self.state.game.turn
                and not self.state.game.pending_forced_advance
                and not self.state.game.defending_figure_id
                and not subscreen_dialogue_open and not in_result_phase):
            self._draw_opponent_advance_prompt()

        if (self.state.game.advancing_figure_id
                and self.state.game.advancing_player_id != self.state.game.player_id
                and not self.state.game.turn
                and not self.state.game.defending_figure_id
                and self.state.game.waiting_for_defender_pick_shown
                and not subscreen_dialogue_open and not in_result_phase):
            self._draw_waiting_for_defender_pick_prompt()

        field_screen = self.subscreens.get('field')
        defender_selecting = field_screen and getattr(field_screen, 'defender_selection_mode', False)
        if (self.state.game.pending_defender_selection
                and self.state.game.defender_selection_dialogue_shown
                and self.state.game.turn and not self.dialogue_box
                and not defender_selecting):
            self._draw_select_defender_prompt()

        if self.waiting_for_counter_response:
            self._draw_counter_spell_waiting_prompt()

        if self.counter_spell_selector:
            self.counter_spell_selector.draw()

        if self.dialogue_box:
            self.dialogue_box.draw()

    # ----------------------------------------------------------------- update
    def update(self, events):
        if not self._ensure_conquer_screen_game():
            return
        self._normalize_conquer_subscreen()
        self._unlock_conquer_tabs()

        for button in self.game_buttons:
            button.update(self.state)

        self._normalize_conquer_subscreen()

        if not self.state.game:
            return

        current_time = pygame.time.get_ticks()
        if current_time - self.last_update_time >= self.update_interval:
            self.last_update_time = current_time
            self.update_game()
            self._unlock_conquer_tabs()
            self._auto_route_conquer_once()

        subscreen = self.subscreens.get(self.state.subscreen)
        if subscreen:
            subscreen.update(self.state.game)

    # -------------------------------------------------------------- event input
    def handle_events(self, events):
        if not self._ensure_conquer_screen_game():
            return

        for event in events:
            if event.type == QUIT:
                pygame.quit()
                sys.exit()

        # Reuse GameScreen's dialogue semantics for conquer notifications.
        if self.dialogue_box:
            response = self.dialogue_box.update(events)
            if response:
                if response == 'counter':
                    self.dialogue_box = None
                    self._handle_counter_spell_counter()
                    return
                if response == 'allow':
                    self.dialogue_box = None
                    self._handle_counter_spell_allow()
                    return
                if (response == 'got it!' and self.state.game
                        and self.state.game.pending_forced_advance):
                    self._handle_forced_advance_dialogue_response()
                elif (response == 'got it!' and self.state.game
                      and self.state.game.pending_defender_selection):
                    self.state.subscreen = 'field'
                    field_screen = self.subscreens.get('field')
                    if field_screen:
                        field_screen.defender_selection_mode = True
                        field_screen._update_defender_selectable()
                    self.state.game.defender_selection_dialogue_shown = True
                elif (response == 'ok' and self.state.game
                      and getattr(self.state.game, 'pending_conquer_own_defender_selection', False)
                      and not getattr(self.state.game, 'defending_figure_id', None)):
                    self.state.subscreen = 'field'
                    field_screen = self.subscreens.get('field')
                    if field_screen:
                        field_screen.conquer_own_defender_mode = True
                elif (response == 'got it!' and self.state.game
                      and getattr(self.state.game, 'pending_conquer_prelude_target', False)):
                    self.state.subscreen = 'field'
                elif (response == 'ok' and self.state.game
                      and self.state.game.game_over
                      and self._active_dialogue_type == 'game_over'):
                    self.dialogue_box = None
                    self._active_dialogue_type = None
                    self._on_game_over_acknowledged()
                    return
                self.dialogue_box = None
                self.show_next_queued_notification()
                return

        if self.need_to_respond_to_spell:
            if self.counter_spell_selector:
                result = self.counter_spell_selector.handle_events(events)
                if result == 'CANCEL':
                    self.counter_spell_selector = None
                    if not self.dialogue_box:
                        self._show_counter_spell_dialogue()
                elif result:
                    self.counter_spell_selector = None
                    self._cast_counter_spell(result)
            return

        # Tabs are always accessible; hidden duel controls are not registered.
        for button in self.game_buttons:
            button.update(self.state)
        self._normalize_conquer_subscreen()

        if self.waiting_for_counter_response:
            return

        # Field-required actions are handled by FieldScreen, but the player may
        # still inspect other tabs manually.  Only the active tab receives game
        # events.
        subscreen = self.subscreens.get(self.state.subscreen)
        if subscreen:
            subscreen.handle_events(events)
            if self.state.game and self.state.game.pending_battle_ready:
                self.check_battle_ready()
