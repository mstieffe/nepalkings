# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Conquer battle screen.

This screen owns the in-battle conquer shell.  It deliberately exposes only
the three conquer battle views: field, battle shop, and battle arena.  The
underlying field/shop/battle components are still shared with duel mode, but
the parent navigation, HUD, routing, and input policy are conquer-specific.
"""

import math
import sys

import pygame
from pygame.locals import *

from config import settings
from config.screen_settings import _UI_SCALE
from game.components.battle_moves.battle_move_icon_renderer import draw_battle_move_icon
from game.components.battle_moves.battle_move_manager import BattleMoveManager
from game.components.conquer_timeline_panel import ConquerTimelinePanel, AUTO_ADVANCE_MS
from game.components.cards.hand import Hand
from game.components.figures.figure_manager import FigureManager
from game.screens.conquer_flow import (
    ConquerObjective,
    derive_conquer_objective,
)
from game.screens.battle_screen import BattleScreen
from game.screens.battle_shop_screen import BattleShopScreen
from game.screens.field_screen import FieldScreen
from game.screens.game_screen import GameScreen
from game.screens.screen import Screen
from utils import battle_shop_service
from utils.utils import GameButton


class ConquerGameScreen(GameScreen):
    """Focused conquer battle shell with Field / Battle Shop / Battle tabs."""

    CONQUER_SUBSCREENS = ('field', 'battle_shop', 'battle')
    # Unified top panel timeline + active info box.
    HEADER_H_FACTOR = 0.22
    CONQUER_BATTLE_MOVE_PANEL_MAX_MOVES = 10
    # When in moves phase and the user navigates away from the battle shop,
    # snap them back after this many ms.
    BATTLE_SHOP_SNAPBACK_MS = 2000

    def __init__(self, state, progress_callback=None):
        Screen.__init__(self, state)
        _report = progress_callback or (lambda f, l=None: None)
        self.state.parent_screen = self

        self._last_conquer_auto_route_key = None
        self._conquer_pending_confirmation = None
        self._conquer_objective_action_rects = {}
        self._conquer_auto_ready_attempt_key = None
        # Per-step countdown timers for non-interactive timeline steps.
        # Maps step.kind -> ms timestamp when it became active.
        self._conquer_timeline_step_started_at = {}
        # UI-only acknowledgements: kinds the user has already "Next"-ed
        # past, used to suppress info-box display for completed non-
        # interactive steps that game state still reports as completed.
        self._conquer_acknowledged_step_kinds = set()
        # Battle-shop snap-back bookkeeping (moves phase only).
        self._conquer_left_battle_shop_at = 0
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
        self._conquer_timeline_panel = ConquerTimelinePanel(self.window)
        self._conquer_battle_move_cache_key = None
        self._conquer_battle_move_cache = []
        self._conquer_battle_move_icon_caches = {}
        self._conquer_battle_move_manager = None
        self._conquer_move_panel_title_font = settings.get_font(
            max(10, int(settings.FS_TINY * 0.80)), bold=True)
        self._conquer_move_panel_empty_font = settings.get_font(
            max(12, int(settings.FS_TINY * 0.95)), bold=True)

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
        self.battle_button = GameButton(
            self.window,
            'conquer_view_battle',
            'battle',
            'plain',
            tab_start_x, tab_y + tab_gap,
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

        # Note: battle_shop is still a valid subscreen (used during the
        # move-selection phase via auto-routing), but no tab button is
        # exposed because the user should never navigate there manually.
        self.game_buttons.extend([
            self.field_button,
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
        for button in (self.field_button, self.battle_button):
            button.locked = False
            button.locked_clicked = False
        self._lock_battle_tab_if_premature()

    def _lock_battle_tab_if_premature(self):
        """Lock the battle tab until the battle has officially started.

        The battle screen would happily render an opponent's advancing or
        defending figure as soon as their ids are populated, but the redesign
        requires those figures to remain hidden until the duel begins.  We
        therefore lock the tab until both ``battle_confirmed`` is set and a
        battle turn has been assigned, i.e. the move-resolution phase begins.
        """
        game = self.state.game
        if not game:
            return
        battle_accessible = (
            bool(getattr(game, 'battle_confirmed', False))
            and getattr(game, 'battle_turn_player_id', None) is not None
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
        if self._auto_confirm_conquer_battle_moves_if_no_changes():
            return

        # Prefer the objective's target_tab so the auto-routed tab always
        # matches what the info panel says — this prevents drift between
        # "act here" instructions and the actually-selected subscreen.
        try:
            objective = self.get_conquer_objective()
        except AttributeError:
            objective = None
        objective_tab = getattr(objective, 'target_tab', None) if objective else None
        # Safety guard: never auto-flip to ``battle_shop`` (or ``battle``)
        # before the battle is actually confirmed by the server.  Otherwise
        # transient client-side states (e.g. ``pending_battle_ready`` between
        # polls) can yank the user away from the field while figures are
        # still being chosen.
        game = self.state.game
        battle_confirmed = bool(getattr(game, 'battle_confirmed', False)) if game else False
        hold_step = self._active_timeline_hold_step()
        if hold_step is not None:
            hold_key = ('timeline_hold', getattr(hold_step, 'kind', ''))
            if hold_key != self._last_conquer_auto_route_key:
                self.state.subscreen = 'field'
                self._last_conquer_auto_route_key = hold_key
            return
        if objective_tab in ('battle_shop', 'battle') and not battle_confirmed:
            objective_tab = 'field'
        if objective_tab and objective_tab in self.CONQUER_SUBSCREENS:
            obj_key = ('objective',
                       getattr(objective, 'phase', ''),
                       getattr(objective, 'headline', ''),
                       getattr(objective, 'primary_action', ''),
                       objective_tab)
            if obj_key != self._last_conquer_auto_route_key:
                self.state.subscreen = objective_tab
                self._last_conquer_auto_route_key = obj_key
            return
        # Fall back to the legacy required-tab path for states the objective
        # doesn't cover (battle round, post-battle, etc.).
        desired, key = self._conquer_required_tab()
        if desired and key != self._last_conquer_auto_route_key:
            self.state.subscreen = desired
            self._last_conquer_auto_route_key = key

    def _conquer_attention_counts(self):
        """Return badge counts for conquer tabs."""
        game = self.state.game
        if not game:
            return {'field': 0, 'battle': 0}

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

        battle = 0
        if (getattr(game, 'battle_confirmed', False)
                and getattr(game, 'battle_turn_player_id', None) is not None):
            battle = 1

        return {'field': field, 'battle': battle}

    # -------------------------------------------------- battle-shop guard
    def _enforce_battle_shop_during_moves(self):
        """During the battle moves-selection phase, force the user onto the
        battle_shop subscreen.

        The user has no business on the field while picking battle moves.
        We allow a brief 2-second peek at the field (e.g. to check the
        figures lined up for the duel) before snapping them back.
        """
        game = self.state.game
        if not game or getattr(game, 'mode', 'duel') != 'conquer':
            return
        in_moves = bool(getattr(game, 'battle_moves_phase', False))
        if not in_moves:
            self._conquer_left_battle_shop_at = 0
            return
        if self._auto_confirm_conquer_battle_moves_if_no_changes():
            self._conquer_left_battle_shop_at = 0
            return
        if getattr(game, 'battle_confirmed', False):
            return
        if self._active_timeline_hold_step() is not None:
            self._conquer_left_battle_shop_at = 0
            return
        if self.state.subscreen == 'battle_shop':
            self._conquer_left_battle_shop_at = 0
            return
        # Only manage the field<->battle_shop transition.  If the player is
        # already on the (locked) battle tab, leave them there.
        if self.state.subscreen != 'field':
            self.state.subscreen = 'battle_shop'
            self._conquer_left_battle_shop_at = 0
            return
        now = pygame.time.get_ticks()
        if not self._conquer_left_battle_shop_at:
            self._conquer_left_battle_shop_at = now
            return
        if now - self._conquer_left_battle_shop_at >= self.BATTLE_SHOP_SNAPBACK_MS:
            self.state.subscreen = 'battle_shop'
            self._conquer_left_battle_shop_at = 0

    def _enter_battle_moves_phase(self):
        game = self.state.game
        if (game and getattr(game, 'mode', 'duel') == 'conquer'
                and self._auto_confirm_conquer_battle_moves_if_no_changes(force=True)):
            return
        super()._enter_battle_moves_phase()

    def _auto_confirm_conquer_battle_moves_if_no_changes(self, *, force=False):
        """Ready conquer battle moves without visiting the shop when it has no choices."""
        game = self.state.game
        if not game or getattr(game, 'mode', 'duel') != 'conquer':
            return False
        if not getattr(game, 'battle_confirmed', False):
            return False
        if getattr(game, 'battle_turn_player_id', None) is not None:
            self.state.subscreen = 'battle'
            return True
        if (getattr(game, 'battle_moves_ready', False)
                or getattr(game, 'waiting_for_opponent_battle_moves', False)):
            return False
        if not force and not getattr(game, 'battle_moves_phase', False):
            return False

        shop = self.subscreens.get('battle_shop') if hasattr(self, 'subscreens') else None
        if shop is None:
            return False

        attempt_key = (
            getattr(game, 'game_id', None),
            getattr(game, 'player_id', None),
            getattr(game, '_game_data_version', 0),
            len(getattr(shop, 'bought_moves', []) or []),
        )
        if not force and attempt_key == self._conquer_auto_ready_attempt_key:
            return False

        shop.game = game
        if getattr(shop, 'card_source', None) is not None and hasattr(shop.card_source, 'game'):
            shop.card_source.game = game
        if hasattr(shop, '_load_bought_moves'):
            shop._load_bought_moves()

        can_ready = bool(getattr(shop, '_can_ready_for_battle', lambda: False)())
        has_changes = bool(getattr(shop, 'has_available_battle_move_changes', lambda: True)())
        if not can_ready or has_changes:
            return False

        self._conquer_auto_ready_attempt_key = attempt_key
        from utils.battle_shop_service import confirm_battle_moves
        try:
            result = confirm_battle_moves(game.game_id, game.player_id)
        except Exception:
            return False
        if not result.get('success'):
            return False

        if result.get('game') and hasattr(game, 'update_from_dict'):
            game.update_from_dict(result['game'])

        both_ready = bool(result.get('both_ready') or getattr(game, 'battle_turn_player_id', None) is not None)
        game.battle_moves_phase = False
        game.battle_moves_ready = not both_ready
        game.waiting_for_opponent_battle_moves = not both_ready
        game.both_battle_moves_ready = both_ready
        if hasattr(self, 'battle_button'):
            self.battle_button.locked = False
        self.state.subscreen = 'battle' if both_ready else 'field'
        return True

    # ----------------------------------------------------------- panel state
    def reset_conquer_panel_state(self):
        """Reset the conquer panel state to a clean slate.

        Called when a new conquest begins, so step countdowns and pending
        confirmations don't carry over from the previous fight.
        """
        self._conquer_pending_confirmation = None
        self._conquer_objective_action_rects = {}
        self._conquer_timeline_step_started_at = {}
        self._conquer_acknowledged_step_kinds = set()
        self._conquer_auto_ready_attempt_key = None
        self._last_conquer_auto_route_key = None
        self._last_battle_cycle_key = None
        self._conquer_left_battle_shop_at = 0

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

    # -------------------------------------------------- notification routing

    def _should_drop_conquer_notification(self, data):
        """In conquer mode, suppress modal notifications redundant with the
        timeline panel.

        Modal dialogues are still used for: errors, ``force_modal``, the
        battle result (``type == 'game_over'``), and the withdraw confirmation.
        """
        if not self.state.game or getattr(self.state.game, 'mode', 'duel') != 'conquer':
            return False
        if data.get('force_modal') or data.get('type') == 'game_over':
            return False
        title = (data.get('title') or '').lower()
        if 'failed' in title or title == 'error':
            return False
        # Drop informational welcome / prelude / opponent-spell receipts —
        # the timeline already shows them.
        actions = [str(a).lower() for a in data.get('actions', ['ok'])]
        return set(actions).issubset({'ok', 'got it!'})

    def _strip_conquer_notification_meta(self, data):
        stripped = dict(data)
        for key in ('event_key', 'phase', 'tone', 'spell_names', 'force_modal',
                    'target_tab', 'no_gate', 'spell_side', 'spell_role',
                    'message_after_images'):
            stripped.pop(key, None)
        return stripped

    def queue_or_show_notification(self, notification_data):
        """In conquer mode, route informational receipts away from modals."""
        data = dict(notification_data)
        if self._should_drop_conquer_notification(data):
            return
        super().queue_or_show_notification(self._strip_conquer_notification_meta(data))

    def request_conquer_figure_confirmation(self, kind, figure, icon=None,
                                            message='', title='Confirm'):
        """Ask the timeline panel to confirm a pending field action."""
        self._conquer_pending_confirmation = {
            'kind': kind,
            'figure': figure,
            'icon': icon,
            'message': message,
            'title': title,
        }

    def clear_conquer_figure_confirmation(self):
        self._conquer_pending_confirmation = None

    def _sync_pending_confirmation_state(self):
        """Drop a stale pending-confirmation if the underlying field state went
        away (e.g. server pre-empted us with an Invader Swap), so the panel
        never shows a Confirm button that no longer maps to a real action.
        """
        pending = self._conquer_pending_confirmation
        if not pending:
            return
        field = self.subscreens.get('field') if hasattr(self, 'subscreens') else None
        if field is None:
            return
        kind = pending.get('kind')
        target = None
        if kind == 'advance':
            target = getattr(field, '_pending_advance_figure', None)
        elif kind == 'opponent_defender':
            target = getattr(field, 'figure_pending_defender_selection', None)
        elif kind == 'own_defender':
            target = getattr(field, 'figure_pending_own_defender_selection', None)
        if target is None:
            self._conquer_pending_confirmation = None

    def _handle_conquer_objective_action(self, action):
        if action == 'next':
            return self._advance_active_timeline_step()
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
            if handled:
                acknowledged = {
                    'advance': 'attacker',
                    'opponent_defender': 'defender',
                    'own_defender': 'defender',
                }.get(kind)
                if acknowledged:
                    acked = getattr(self, '_conquer_acknowledged_step_kinds', None)
                    if acked is None:
                        acked = set()
                        self._conquer_acknowledged_step_kinds = acked
                    timers = getattr(self, '_conquer_timeline_step_started_at', None)
                    if timers is None:
                        timers = {}
                        self._conquer_timeline_step_started_at = timers
                    acked.add(acknowledged)
                    timers[acknowledged] = (
                        pygame.time.get_ticks() - AUTO_ADVANCE_MS - 1
                    )
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
        game = self.state.game
        if not game:
            return
        field = self.subscreens.get('field')
        if not field:
            return

        civil_war_second_defender = bool(getattr(game, 'civil_war_defender_second', False))
        try:
            own_civil_war_second_defender = bool(
                civil_war_second_defender
                and getattr(game, 'advancing_player_id', None) != getattr(game, 'player_id', None)
                and self._is_current_player_conquer_attacker()
            )
        except Exception:
            own_civil_war_second_defender = False

        if (getattr(game, 'pending_defender_selection', False)
                and getattr(game, 'defender_selection_dialogue_shown', False)
                and getattr(game, 'turn', False)):
            if not getattr(field, 'defender_selection_mode', False):
                field.defender_selection_mode = True
                field._update_defender_selectable()
        elif (getattr(field, 'defender_selection_mode', False)
              and civil_war_second_defender
              and not own_civil_war_second_defender):
            field._update_defender_selectable()
        elif getattr(field, 'defender_selection_mode', False) and not getattr(
                game, 'pending_defender_selection', False):
            field.defender_selection_mode = False
            field._reset_defender_selectable()

        if ((getattr(game, 'pending_conquer_own_defender_selection', False)
                and getattr(game, 'conquer_own_defender_selection_shown', False))
                or own_civil_war_second_defender):
            field.conquer_own_defender_mode = True
            if hasattr(field, '_update_conquer_own_defender_selectable'):
                field._update_conquer_own_defender_selectable()
            else:
                field._reset_defender_selectable()
        elif getattr(field, 'conquer_own_defender_mode', False) and not getattr(
                game, 'pending_conquer_own_defender_selection', False):
            field.conquer_own_defender_mode = False
            field._reset_defender_selectable()

    def get_conquer_objective(self):
        return derive_conquer_objective(
            self.state.game, self.state,
            self.subscreens.get('field') if hasattr(self, 'subscreens') else None,
            self.subscreens.get('battle_shop') if hasattr(self, 'subscreens') else None,
        )

    def _advance_active_timeline_step(self):
        """Expire the countdown of the currently active non-interactive step.

        Triggered by the timeline panel's Next button.  We mark the active
        step's countdown as expired so the next draw promotes the next
        timeline step to active.
        """
        steps = self._conquer_timeline_panel.derive_display_steps(self)
        for step in steps:
            if step.active and not step.interactive:
                self._conquer_acknowledged_step_kinds.add(step.kind)
                # Expire its countdown so the next draw treats it complete.
                self._conquer_timeline_step_started_at[step.kind] = (
                    pygame.time.get_ticks() - AUTO_ADVANCE_MS - 1
                )
                return True
        return False

    def _active_timeline_hold_step(self):
        step = self.active_conquer_timeline_step()
        if step is not None and not step.interactive:
            return step
        return None

    def active_conquer_timeline_step(self):
        if not hasattr(self, '_conquer_timeline_panel'):
            return None
        steps = self._conquer_timeline_panel.derive_display_steps(self)
        for step in steps:
            if step.active:
                return step
        return None

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
            'battle': self.battle_button,
        }
        for name, button in active_map.items():
            if self.state.subscreen == name:
                pad = max(4, int(settings.SCREEN_WIDTH * 0.003))
                rect = button.rect_symbol.inflate(pad, pad)
                pygame.draw.rect(self.window, (245, 205, 95), rect, 2, border_radius=6)
            if counts.get(name, 0):
                self._draw_button_badge(button, counts[name])

    # ------------------------------------------------------ battle move HUD

    def _conquer_move_title_font(self):
        font = getattr(self, '_conquer_move_panel_title_font', None)
        if font is None:
            font = settings.get_font(max(10, int(settings.FS_TINY * 0.80)), bold=True)
            self._conquer_move_panel_title_font = font
        return font

    def _conquer_move_empty_font(self):
        font = getattr(self, '_conquer_move_panel_empty_font', None)
        if font is None:
            font = settings.get_font(max(12, int(settings.FS_TINY * 0.95)), bold=True)
            self._conquer_move_panel_empty_font = font
        return font

    def _current_conquer_battle_moves(self):
        game = self.state.game
        if not game:
            return []

        battle = self.subscreens.get('battle') if hasattr(self, 'subscreens') else None
        battle_moves = getattr(battle, 'player_moves', None) if battle else None
        if (battle_moves and getattr(game, 'battle_turn_player_id', None) is not None):
            return [dict(move) for move in battle_moves]

        game_id = getattr(game, 'game_id', None)
        player_id = getattr(game, 'player_id', None)
        if not game_id or not player_id:
            return list(getattr(game, 'battle_moves', []) or [])

        cache_key = (
            game_id,
            player_id,
            getattr(game, '_game_data_version', 0),
            getattr(game, 'battle_turn_player_id', None),
            getattr(game, 'battle_round', None),
        )
        if cache_key == getattr(self, '_conquer_battle_move_cache_key', None):
            return list(getattr(self, '_conquer_battle_move_cache', []) or [])

        try:
            result = battle_shop_service.get_battle_moves(game_id, player_id)
            moves = result.get('battle_moves', []) if result.get('success') else []
        except Exception:
            moves = list(getattr(self, '_conquer_battle_move_cache', []) or [])

        self._conquer_battle_move_cache_key = cache_key
        self._conquer_battle_move_cache = [dict(move) for move in moves]
        self._sync_conquer_battle_move_subscreen_cache(self._conquer_battle_move_cache)
        return list(self._conquer_battle_move_cache)

    def _sync_conquer_battle_move_subscreen_cache(self, moves):
        shop = self.subscreens.get('battle_shop') if hasattr(self, 'subscreens') else None
        game = self.state.game
        if shop is not None and hasattr(shop, 'bought_moves'):
            shop.bought_moves = [dict(move) for move in moves]
            if hasattr(shop, '_game_identity_key'):
                shop._loaded_game_key = shop._game_identity_key(game)
            if hasattr(shop, '_bought_moves_cache_key'):
                shop._loaded_bought_moves_key = shop._bought_moves_cache_key(game)

    def _conquer_battle_moves_panel_bounds(self):
        button_rects = []
        for button in (getattr(self, 'field_button', None), getattr(self, 'battle_button', None)):
            if button is None:
                continue
            rect = getattr(button, 'rect_glow', None) or getattr(button, 'rect_symbol', None)
            if isinstance(rect, pygame.Rect):
                button_rects.append(rect)
        if not button_rects:
            return None

        sub_x, _sub_y = self._conquer_subscreen_origin()
        margin = max(6, int(settings.SCREEN_WIDTH * 0.008))
        max_w = max(0, sub_x - margin * 2)
        if max_w < 52:
            return None

        button_center_x = sum(rect.centerx for rect in button_rects) // len(button_rects)
        preferred_w = max(settings.FIELD_BUTTON_WIDTH + margin * 2,
                          int(settings.SCREEN_WIDTH * 0.075))
        panel_w = min(max_w, preferred_w)
        panel_x = button_center_x - panel_w // 2
        panel_x = max(margin, min(panel_x, sub_x - margin - panel_w))

        gap_y = max(8, int(settings.SCREEN_HEIGHT * 0.012))
        panel_y = max(rect.bottom for rect in button_rects) + gap_y
        max_h = settings.SCREEN_HEIGHT - margin - panel_y
        if max_h < 70:
            return None
        return pygame.Rect(panel_x, panel_y, panel_w, max_h)

    def _conquer_battle_moves_panel_layout(self, move_count):
        bounds = self._conquer_battle_moves_panel_bounds()
        if bounds is None:
            return None

        display_count = max(0, min(int(move_count or 0), self.CONQUER_BATTLE_MOVE_PANEL_MAX_MOVES))
        layout_count = max(1, display_count)
        columns = 1 if layout_count <= 3 else 2
        rows = int(math.ceil(layout_count / columns))

        pad = max(6, int(bounds.width * 0.055))
        gap = max(5, int(settings.SCREEN_HEIGHT * 0.006))
        title_h = self._conquer_move_title_font().get_height()
        inner_w = max(1, bounds.width - pad * 2)
        icon_h_available = bounds.height - pad * 2 - title_h - gap
        max_icon = max(30, min(68, int(settings.SCREEN_WIDTH * 0.036)))
        icon_size = min(
            max_icon,
            (inner_w - gap * (columns - 1)) // columns,
            (icon_h_available - gap * (rows - 1)) // rows,
        )
        if icon_size < 18:
            return None

        panel_h = pad * 2 + title_h + gap + rows * icon_size + (rows - 1) * gap
        rect = pygame.Rect(bounds.left, bounds.top, bounds.width, min(panel_h, bounds.height))
        grid_w = columns * icon_size + (columns - 1) * gap
        start_x = rect.centerx - grid_w // 2
        start_y = rect.top + pad + title_h + gap
        icon_rects = []
        for idx in range(display_count):
            row = idx // columns
            col = idx % columns
            icon_rects.append(pygame.Rect(
                start_x + col * (icon_size + gap),
                start_y + row * (icon_size + gap),
                icon_size,
                icon_size,
            ))

        return {
            'rect': rect,
            'icon_rects': icon_rects,
            'icon_size': icon_size,
            'columns': columns,
            'rows': rows,
            'pad': pad,
        }

    def _conquer_battle_move_manager_for_panel(self):
        manager = getattr(self, '_conquer_battle_move_manager', None)
        if manager is None:
            shop = self.subscreens.get('battle_shop') if hasattr(self, 'subscreens') else None
            manager = getattr(shop, 'battle_move_manager', None) if shop is not None else None
        if manager is None:
            manager = BattleMoveManager()
        self._conquer_battle_move_manager = manager
        return manager

    @staticmethod
    def _scaled_or_blank(surface, size):
        if surface is None:
            return pygame.Surface(size, pygame.SRCALPHA)
        return pygame.transform.smoothscale(surface, size)

    @staticmethod
    def _load_panel_image(path, size):
        try:
            raw = pygame.image.load(path).convert_alpha()
            return pygame.transform.smoothscale(raw, size)
        except Exception:
            return pygame.Surface(size, pygame.SRCALPHA)

    def _conquer_battle_move_icon_assets(self, icon_size):
        caches = getattr(self, '_conquer_battle_move_icon_caches', None)
        if caches is None:
            caches = {}
            self._conquer_battle_move_icon_caches = caches
        if icon_size in caches:
            return caches[icon_size]

        big_scale = 1.20
        glow_size = max(icon_size + 10, int(icon_size * 1.45))
        glow_big = int(glow_size * big_scale)
        icon_inner = max(1, icon_size - 6)
        icon_big = int(icon_inner * big_scale)
        frame_size = int(icon_size * 1.30)
        frame_big = int(frame_size * big_scale)
        suit_size = max(8, int(icon_size * 0.24))
        suit_big = int(suit_size * big_scale)

        glow_cache = {
            'green': self._load_panel_image('img/game_button/glow/green.png', (glow_size, glow_size)),
            'blue': self._load_panel_image('img/game_button/glow/blue.png', (glow_size, glow_size)),
            'yellow': self._load_panel_image('img/game_button/glow/yellow.png', (glow_size, glow_size)),
            'green_big': self._load_panel_image('img/game_button/glow/green.png', (glow_big, glow_big)),
            'blue_big': self._load_panel_image('img/game_button/glow/blue.png', (glow_big, glow_big)),
            'yellow_big': self._load_panel_image('img/game_button/glow/yellow.png', (glow_big, glow_big)),
        }
        suit_icon_cache = {}
        for suit_name in ('hearts', 'diamonds', 'spades', 'clubs'):
            path = settings.SUIT_ICON_IMG_PATH + suit_name + '.png'
            suit_icon_cache[suit_name] = self._load_panel_image(path, (suit_size, suit_size))
            suit_icon_cache[suit_name + '_big'] = self._load_panel_image(path, (suit_big, suit_big))

        manager = self._conquer_battle_move_manager_for_panel()
        icon_cache = {}
        frame_cache = {}
        for name, family in manager.families_by_name.items():
            icon_cache[name] = self._scaled_or_blank(getattr(family, 'icon_img', None), (icon_inner, icon_inner))
            icon_cache[name + '_big'] = self._scaled_or_blank(getattr(family, 'icon_img', None), (icon_big, icon_big))
            frame_cache[name] = self._scaled_or_blank(getattr(family, 'frame_img', None), (frame_size, frame_size))
            frame_cache[name + '_big'] = self._scaled_or_blank(getattr(family, 'frame_img', None), (frame_big, frame_big))

        font = settings.get_font(max(10, int(icon_size * 0.28)), bold=True)
        caches[icon_size] = (glow_cache, icon_cache, frame_cache, suit_icon_cache, font)
        return caches[icon_size]

    @staticmethod
    def _conquer_battle_move_display_power(move):
        if move.get('family_name') == 'Block':
            return 0
        return move.get('value', 0)

    def _draw_conquer_battle_moves_panel(self):
        game = self.state.game
        if not game or getattr(game, 'mode', 'duel') != 'conquer':
            return

        moves = self._current_conquer_battle_moves()
        layout = self._conquer_battle_moves_panel_layout(len(moves))
        if not layout:
            return

        rect = layout['rect']
        panel = pygame.Surface(rect.size, pygame.SRCALPHA)
        panel.fill((38, 29, 22, 218))
        self.window.blit(panel, rect.topleft)
        pygame.draw.rect(
            self.window,
            settings.BATTLE_SCREEN_PANEL_BORDER_COLOR,
            rect,
            settings.BATTLE_SCREEN_PANEL_BORDER_WIDTH,
            border_radius=6,
        )

        title_font = self._conquer_move_title_font()
        count_text = f'Moves {len(moves)}/{self.CONQUER_BATTLE_MOVE_PANEL_MAX_MOVES}'
        title = title_font.render(
            self._fit_text(count_text, title_font, rect.width - layout['pad'] * 2),
            True,
            (238, 218, 170),
        )
        self.window.blit(title, (rect.centerx - title.get_width() // 2, rect.top + layout['pad']))

        if not moves:
            empty_font = self._conquer_move_empty_font()
            dash = empty_font.render('-', True, (150, 132, 96))
            self.window.blit(dash, dash.get_rect(center=(rect.centerx, rect.centery + 8)))
            return

        icon_size = layout['icon_size']
        glow_cache, icon_cache, frame_cache, suit_icon_cache, font = (
            self._conquer_battle_move_icon_assets(icon_size)
        )
        mouse_pos = pygame.mouse.get_pos()
        display_moves = moves[:self.CONQUER_BATTLE_MOVE_PANEL_MAX_MOVES]
        for move, icon_rect in zip(display_moves, layout['icon_rects']):
            hovered = icon_rect.collidepoint(mouse_pos)
            draw_battle_move_icon(
                self.window,
                icon_rect.centerx,
                icon_rect.centery,
                move.get('family_name', ''),
                move.get('suit', ''),
                self._conquer_battle_move_display_power(move),
                glow_cache,
                icon_cache,
                frame_cache,
                suit_icon_cache,
                font,
                icon_size,
                hovered=hovered,
                is_used=move.get('played_round') is not None,
                suit_b=move.get('suit_b'),
            )

    @staticmethod
    def _fit_text(text, font, max_width):
        text = text or ''
        if font.size(text)[0] <= max_width:
            return text
        clipped = text
        while clipped and font.size(clipped + '...')[0] > max_width:
            clipped = clipped[:-1]
        return clipped + '...' if clipped else '...'

    def render(self):
        self.window.fill(settings.BACKGROUND_COLOR)
        if not self._ensure_conquer_screen_game() or not self.state.game:
            return

        self._normalize_conquer_subscreen()

        subscreen = self.subscreens.get(self.state.subscreen)
        if subscreen:
            subscreen.draw()

        self._conquer_timeline_panel.draw(self)

        for button in self.game_buttons:
            button.draw()
        for button in self.game_buttons:
            if hasattr(button, 'draw_hover_text'):
                button.draw_hover_text()
        self._draw_tab_state()
        self._draw_conquer_battle_moves_panel()

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

        self._conquer_timeline_panel.draw_hover_tooltips(self)

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
            self._sync_conquer_action_modes()
            self._auto_route_conquer_once()

        subscreen = self.subscreens.get(self.state.subscreen)
        if subscreen:
            subscreen.update(self.state.game)
        self._sync_conquer_action_modes()
        self._sync_pending_confirmation_state()
        self._enforce_battle_shop_during_moves()

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

        if self.waiting_for_counter_response:
            return

        active_step = self.active_conquer_timeline_step()
        subscreen = self.subscreens.get(self.state.subscreen)
        if active_step is not None and not active_step.interactive:
            if not (subscreen and getattr(subscreen, 'dialogue_box', None)):
                return

        # Field-required actions are handled by FieldScreen, but the player may
        # still inspect other tabs manually.  Only the active tab receives game
        # events.
        if subscreen:
            subscreen.handle_events(events)
            if self.state.game and self.state.game.pending_battle_ready:
                self.check_battle_ready()
