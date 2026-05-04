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
from game.components.conquer_command_layer import ConquerCommandLayer
from game.components.cards.hand import Hand
from game.components.figures.figure_manager import FigureManager
from game.screens.conquer_flow import (
    ConquerEvent,
    ConquerObjective,
    derive_conquer_objective,
    infer_spell_metadata,
)
from game.screens.battle_screen import BattleScreen
from game.screens.battle_shop_screen import BattleShopScreen
from game.screens.field_screen import FieldScreen
from game.screens.game_screen import GameScreen
from game.screens.screen import Screen
from utils.utils import GameButton


class ConquerGameScreen(GameScreen):
    """Focused conquer battle shell with Field / Battle Shop / Battle tabs."""

    CONQUER_SUBSCREENS = ('field', 'battle_shop', 'battle')
    # Unified top panel: replaces the old header + bottom-log split.  All
    # status, spells, battle figures and the action prompt live in this single
    # panel so the subscreen content can use the rest of the screen.
    HEADER_H_FACTOR = 0.22
    # Kept for backwards compatibility with code paths that still read it;
    # there is no separate bottom log in the new design.
    BOTTOM_LOG_H_FACTOR = 0.0

    def __init__(self, state, progress_callback=None):
        Screen.__init__(self, state)
        _report = progress_callback or (lambda f, l=None: None)
        self.state.parent_screen = self

        self._last_conquer_auto_route_key = None
        self._conquer_events = []
        self._conquer_event_keys = set()
        self._conquer_event_seq = 0
        self._conquer_pending_confirmation = None
        self._conquer_objective_action_rects = {}
        self._conquer_pending_gate = None
        self._conquer_gate_queue = []
        self._withdraw_dialogue_open = False
        self._current_game_key = None
        # Battle-cycle reset bookkeeping: clear conquer events whenever the
        # advancing/defending figure pair changes (start of a new conquest).
        self._last_battle_cycle_key = None
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
        self._conquer_command_layer = ConquerCommandLayer(self.window)

        if getattr(self.state, 'subscreen', None) not in self.subscreens:
            self.state.subscreen = 'field'

    def on_enter(self):
        """Mark this screen as the active parent and reset to the field if needed."""
        self.state.parent_screen = self
        self._ensure_conquer_screen_game()
        if self.state.game:
            current_key = (getattr(self.state.game, 'game_id', None),
                           getattr(self.state.game, 'player_id', None))
            if current_key != getattr(self, '_current_game_key', None):
                if hasattr(self, 'battle_button') and hasattr(self, 'subscreens'):
                    self._reset_game_screen_state()
                self._current_game_key = current_key
                self._game_poller = None
                if getattr(self.state.game, 'state', None) != 'finished':
                    self.state.game.game_over = False
                    self.state.game.pending_game_over = None
                    self.state.game.game_over_shown = False
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

        # Tab buttons sit in the left margin, below the unified top panel.
        # The stone glow extends ~stone_width/2 in each direction from (x, y),
        # so x must be ≥ stone_radius to avoid clipping the left edge of the
        # screen, and tab_y must clear the top panel so the first button does
        # not overlap the panel's bottom border.
        header_h = int(settings.SCREEN_HEIGHT * self.HEADER_H_FACTOR)
        tab_start_x = int(settings.SCREEN_WIDTH * 0.040)
        tab_y = header_h + int(settings.SCREEN_HEIGHT * 0.072)
        tab_gap = settings.FIELD_BUTTON_WIDTH + int(settings.SCREEN_HEIGHT * 0.014)

        self.field_button = GameButton(
            self.window,
            'conquer_view_field',
            'map',
            'plain',
            tab_start_x, tab_y,
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
            tab_start_x, tab_y + tab_gap,
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
            tab_start_x, tab_y + tab_gap * 2,
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
        y = header_h + int(settings.SCREEN_HEIGHT * 0.010)
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

    def _reset_game_screen_state(self):
        """Reset shared and conquer-only state when entering a different game."""
        super()._reset_game_screen_state()
        self.reset_conquer_panel_state()
        self._withdraw_dialogue_open = False
        if self.state.game and getattr(self.state.game, 'state', None) != 'finished':
            self.state.game.game_over = False
            self.state.game.pending_game_over = None
            self.state.game.game_over_shown = False
            if hasattr(self.state.game, '_conquer_result_dialogue_shown'):
                self.state.game._conquer_result_dialogue_shown = False

    def _refresh_conquer_tab_locks(self):
        for button in (self.field_button, self.battle_shop_button, self.battle_button):
            button.locked = False
            button.locked_clicked = False
        self._lock_battle_tab_if_premature()

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
        if self._conquer_flow_gate_active():
            return
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

    # ----------------------------------------------------------- command events
    def emit_conquer_event(self, key, title, detail='', phase='start',
                           tone='info', spell_names=None,
                           spell_side='', spell_role=''):
        """Append a de-duplicated event to the conquer command log."""
        if not key:
            key = f'event:{self._conquer_event_seq}:{title}:{detail}'
        if key in self._conquer_event_keys:
            return None
        self._conquer_event_seq += 1
        names = tuple(n for n in (spell_names or []) if n)
        event = ConquerEvent(
            key=str(key),
            phase=phase or 'start',
            title=title or 'Conquer event',
            detail=detail or '',
            tone=tone or 'info',
            spell_names=names,
            order=self._conquer_event_seq,
            spell_side=spell_side or '',
            spell_role=spell_role or '',
        )
        self._conquer_events.append(event)
        self._conquer_event_keys.add(event.key)
        if len(self._conquer_events) > 24:
            dropped = self._conquer_events.pop(0)
            self._conquer_event_keys.discard(dropped.key)
        return event

    def reset_conquer_panel_state(self):
        """Reset the conquer panel state to a clean slate.

        Called when a new conquest begins, so the spell, battle figure and
        info compartments don't carry over data from the previous fight.
        """
        self._conquer_events = []
        self._conquer_event_keys = set()
        self._conquer_event_seq = 0
        self._conquer_pending_gate = None
        self._conquer_gate_queue = []
        self._conquer_pending_confirmation = None
        self._conquer_objective_action_rects = {}
        self._last_conquer_auto_route_key = None
        self._last_battle_cycle_key = None

    def _conquer_battle_cycle_key(self):
        """Identity tuple for a given conquest cycle (changes between fights).

        Used to detect that a new fight is starting and that the panel state
        should be wiped to avoid the previous fight's spells/figures bleeding
        into the new one.
        """
        game = self.state.game
        if not game:
            return None
        return (
            getattr(game, 'game_id', None),
            getattr(game, 'advancing_player_id', None),
            getattr(game, 'advancing_figure_id', None),
            getattr(game, 'defending_figure_id', None),
            getattr(game, 'current_round', None),
        )

    def _check_battle_cycle_reset(self):
        """Detect a new conquer cycle and clear stale panel state.

        A conquest is identified by ``_conquer_battle_cycle_key``. When the
        previous cycle ended (key transitioned from a populated state back to
        a "no battle" state) we reset so the next cycle's compartments fill
        progressively from a clean slate.
        """
        new_key = self._conquer_battle_cycle_key()
        prev_key = self._last_battle_cycle_key

        # Detect end of a battle (previous cycle had advancing/defending
        # figure ids and now both are cleared).
        prev_had_figures = bool(prev_key and (prev_key[2] or prev_key[3]))
        new_no_figures = bool(new_key and not (new_key[2] or new_key[3]))
        if prev_had_figures and new_no_figures:
            # Battle ended — clear panel state so the next conquest is fresh.
            self.reset_conquer_panel_state()
            self._last_battle_cycle_key = new_key
            return

        self._last_battle_cycle_key = new_key

    def _should_convert_conquer_notification(self, data):
        if not self.state.game or getattr(self.state.game, 'mode', 'duel') != 'conquer':
            return False
        if data.get('force_modal') or data.get('type') == 'game_over':
            return False
        # Welcome / battle-intro notifications are shown as dialogue boxes,
        # mirroring the battle result modal at the end of a conquer fight.
        if data.get('phase') == 'start':
            return False
        title = (data.get('title') or '').lower()
        if 'failed' in title or title == 'error':
            return False
        actions = [str(a).lower() for a in data.get('actions', ['ok'])]
        return set(actions).issubset({'ok', 'got it!'})

    def _notification_to_event(self, data):
        message = data.get('message') or ''
        after = data.get('message_after_images') or ''
        detail = message
        if after:
            detail = f'{detail} {after}' if detail else after
        detail = ' '.join(str(detail).split())
        title = data.get('title') or 'Conquer event'
        key = data.get('event_key') or f'notification:{title}:{detail}'
        spell_side, spell_role = infer_spell_metadata(data)
        return self.emit_conquer_event(
            key=key,
            title=title,
            detail=detail,
            phase=data.get('phase') or 'start',
            tone=data.get('tone') or 'info',
            spell_names=data.get('spell_names') or (),
            spell_side=spell_side,
            spell_role=spell_role,
        )

    def _should_gate_conquer_notification(self, data):
        """Always returns False — the gate mechanism is no longer used.

        Welcome/intro notifications are now shown as dialogue boxes directly.
        Selection-step notifications (action tone) activate field modes
        immediately via ``_sync_conquer_action_modes`` without blocking the
        player with a Next button.
        """
        return False

    def _queue_conquer_gate(self, event, data):
        if not event:
            return
        gate = {
            'key': event.key,
            'phase': event.phase,
            'title': event.title,
            'detail': event.detail,
            'tone': event.tone,
            'spell_names': event.spell_names,
            'target_tab': data.get('target_tab'),
        }
        if not hasattr(self, '_conquer_gate_queue'):
            self._conquer_gate_queue = []
        if not hasattr(self, '_conquer_pending_gate'):
            self._conquer_pending_gate = None
        queued_keys = {g.get('key') for g in self._conquer_gate_queue}
        active_key = (self._conquer_pending_gate or {}).get('key')
        if gate['key'] == active_key or gate['key'] in queued_keys:
            return
        if self._conquer_pending_gate:
            self._conquer_gate_queue.append(gate)
        else:
            self._conquer_pending_gate = gate
            self._suspend_conquer_selection_modes()

    def _advance_conquer_gate(self):
        current = self._conquer_pending_gate or {}
        self._conquer_pending_gate = (
            self._conquer_gate_queue.pop(0) if self._conquer_gate_queue else None
        )
        if self._conquer_pending_gate:
            self._suspend_conquer_selection_modes()
            return True
        target_tab = current.get('target_tab')
        if not target_tab:
            target_tab = derive_conquer_objective(
                self.state.game, self.state,
                self.subscreens.get('field') if hasattr(self, 'subscreens') else None,
                self.subscreens.get('battle_shop') if hasattr(self, 'subscreens') else None,
            ).target_tab
        if target_tab in self.CONQUER_SUBSCREENS:
            self.state.subscreen = target_tab
        self._sync_conquer_action_modes()
        self._auto_route_conquer_once()
        return True

    def _conquer_flow_gate_active(self):
        return getattr(self, '_conquer_pending_gate', None) is not None

    def _suspend_conquer_selection_modes(self):
        field = self.subscreens.get('field') if hasattr(self, 'subscreens') else None
        if not field:
            return
        if getattr(field, 'defender_selection_mode', False):
            field.defender_selection_mode = False
            field._reset_defender_selectable()
        if getattr(field, 'conquer_own_defender_mode', False):
            field.conquer_own_defender_mode = False
            field._reset_defender_selectable()

    def _strip_conquer_notification_meta(self, data):
        stripped = dict(data)
        for key in ('event_key', 'phase', 'tone', 'spell_names', 'force_modal',
                    'target_tab', 'no_gate'):
            stripped.pop(key, None)
        return stripped

    def queue_or_show_notification(self, notification_data):
        """In conquer mode, route informational receipts to the command log."""
        data = dict(notification_data)
        if self._should_convert_conquer_notification(data):
            event = self._notification_to_event(data)
            if self._should_gate_conquer_notification(data):
                self._queue_conquer_gate(event, data)
            return
        super().queue_or_show_notification(self._strip_conquer_notification_meta(data))

    def request_conquer_figure_confirmation(self, kind, figure, icon=None,
                                            message='', title='Confirm'):
        """Ask the command panel to confirm a pending field action."""
        self._conquer_pending_confirmation = {
            'kind': kind,
            'figure': figure,
            'icon': icon,
            'message': message,
            'title': title,
        }

    def clear_conquer_figure_confirmation(self):
        self._conquer_pending_confirmation = None

    def _handle_conquer_objective_action(self, action):
        if action == 'next_gate':
            return self._advance_conquer_gate()
        if action == 'withdraw':
            self._open_withdraw_dialogue()
            return True
        if action == 'cancel':
            field = self.subscreens.get('field')
            if field and hasattr(field, 'cancel_conquer_panel_confirmation'):
                field.cancel_conquer_panel_confirmation()
            self.clear_conquer_figure_confirmation()
            return True
        if action == 'confirm':
            field = self.subscreens.get('field')
            pending = self._conquer_pending_confirmation or {}
            kind = pending.get('kind')
            handled = False
            if field:
                if kind == 'advance' and hasattr(field, 'confirm_pending_advance'):
                    handled = field.confirm_pending_advance()
                elif kind == 'opponent_defender' and hasattr(field, 'confirm_pending_defender_selection'):
                    handled = field.confirm_pending_defender_selection()
                elif kind == 'own_defender' and hasattr(field, 'confirm_pending_own_defender_selection'):
                    handled = field.confirm_pending_own_defender_selection()
            self.clear_conquer_figure_confirmation()
            return handled
        return False

    def _handle_conquer_command_events(self, events):
        if self.dialogue_box:
            return False
        rects = getattr(self, '_conquer_objective_action_rects', {}) or {}
        if not rects:
            return False
        for event in events:
            if event.type != MOUSEBUTTONDOWN or event.button != 1:
                continue
            for action, rect in rects.items():
                if rect and rect.collidepoint(event.pos):
                    return self._handle_conquer_objective_action(action)
        return False

    def _open_withdraw_dialogue(self):
        if self._withdraw_dialogue_open:
            return
        self._withdraw_dialogue_open = True
        self.make_dialogue_box(
            message=(
                'Withdraw from this conquest?\n\n'
                'The defender wins immediately. Your committed attack cards '
                'are resolved through the normal conquer loot rules.'
            ),
            actions=['Withdraw', 'Cancel'],
            icon='error',
            title='Withdraw Conquest',
        )

    def _confirm_withdraw(self):
        from utils.game_service import conquer_withdraw
        result = conquer_withdraw(self.state.game.game_id, self.state.game.player_id)
        if result.get('success') and result.get('conquer_result'):
            self.emit_conquer_event(
                key='withdraw:confirmed',
                title='Conquest withdrawn',
                detail='You withdrew. The defender wins this conquer battle.',
                phase='result',
                tone='bad',
            )
            self._handle_conquer_result_response(result)
            return
        self.make_dialogue_box(
            message=result.get('message', 'Failed to withdraw from conquest.'),
            actions=['ok'],
            icon='error',
            title='Withdraw Failed',
        )

    def _sync_conquer_action_modes(self):
        """Enable field modes that used to wait for informational modal clicks."""
        if self._conquer_flow_gate_active():
            return
        if not self.state.game:
            return
        field = self.subscreens.get('field')
        if not field:
            return

        if (getattr(self.state.game, 'pending_defender_selection', False)
                and getattr(self.state.game, 'defender_selection_dialogue_shown', False)
                and getattr(self.state.game, 'turn', False)):
            if not getattr(field, 'defender_selection_mode', False):
                field.defender_selection_mode = True
                field._update_defender_selectable()
        elif getattr(field, 'defender_selection_mode', False) and not getattr(
                self.state.game, 'pending_defender_selection', False):
            field.defender_selection_mode = False
            field._reset_defender_selectable()

        if (getattr(self.state.game, 'pending_conquer_own_defender_selection', False)
                and getattr(self.state.game, 'conquer_own_defender_selection_shown', False)):
            field.conquer_own_defender_mode = True
            field._update_defender_selectable()
        elif getattr(field, 'conquer_own_defender_mode', False) and not getattr(
                self.state.game, 'pending_conquer_own_defender_selection', False):
            field.conquer_own_defender_mode = False

    def get_conquer_objective(self):
        gate = self._conquer_pending_gate
        if gate:
            detail = gate.get('detail') or 'Review the latest conquer event.'
            return ConquerObjective(
                phase=gate.get('phase') or 'start',
                headline=gate.get('title') or 'Conquer update',
                instruction=f'{detail} Press Next to continue.',
                target_tab=gate.get('target_tab'),
                primary_action='next_gate',
                waiting=True,
                tone=gate.get('tone') or 'action',
            )
        return derive_conquer_objective(
            self.state.game, self.state,
            self.subscreens.get('field') if hasattr(self, 'subscreens') else None,
            self.subscreens.get('battle_shop') if hasattr(self, 'subscreens') else None,
        )

    # ------------------------------------------------------------------- draw
    def _conquer_status_text(self):
        game = self.state.game
        if not game:
            return '', ''

        tier = getattr(game, 'land_tier', None)
        land = f'Tier {tier} Land' if tier else 'Conquer Battle'
        opponent = getattr(game, 'opponent_name', None) or 'Defender'
        title = f'{land} vs {opponent}'
        objective = self.get_conquer_objective()
        hint = objective.headline
        return title, hint

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

        subscreen = self.subscreens.get(self.state.subscreen)
        if subscreen:
            subscreen.draw()

        self._conquer_command_layer.draw(self)

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
        self._refresh_conquer_tab_locks()

        for button in self.game_buttons:
            button.update(self.state)

        self._normalize_conquer_subscreen()

        if not self.state.game:
            return

        current_time = pygame.time.get_ticks()
        if current_time - self.last_update_time >= self.update_interval:
            self.last_update_time = current_time
            self.update_game()
            self._check_battle_cycle_reset()
            self._refresh_conquer_tab_locks()
            if not self._conquer_flow_gate_active():
                self._sync_conquer_action_modes()
                self._auto_route_conquer_once()

        subscreen = self.subscreens.get(self.state.subscreen)
        if subscreen:
            subscreen.update(self.state.game)
        if not self._conquer_flow_gate_active():
            self._sync_conquer_action_modes()

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
                if self._withdraw_dialogue_open:
                    self._withdraw_dialogue_open = False
                    self.dialogue_box = None
                    if response == 'withdraw':
                        self._confirm_withdraw()
                    return
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

        if self._handle_conquer_command_events(events):
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

        if self._conquer_flow_gate_active():
            return

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
