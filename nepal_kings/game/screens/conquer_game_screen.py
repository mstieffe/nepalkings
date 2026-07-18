# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Conquer battle screen.

This screen owns the in-battle conquer shell.  It deliberately exposes only
the three conquer battle views: field, battle shop, and battle arena.  The
underlying field/shop/battle components are still shared with duel mode, but
the parent navigation, HUD, routing, and input policy are conquer-specific.
"""

import logging
import math
import sys
from types import SimpleNamespace

import pygame
from pygame.locals import *

from config import settings
from config.screen_settings import _UI_SCALE
from game.components.battle_moves.battle_move_icon_renderer import draw_battle_move_icon
from game.components.battle_moves.battle_move_manager import BattleMoveManager
from game.components.coach_card import draw_coach_button, draw_coach_panel
from game.components.conquer_round_ledger import ConquerRoundLedger
from game.components.conquer_effects import ConquerEffectsLayer
from game.components.conquer_layout import compute_conquer_layout
from game.components.conquer_reveal_sequencer import (
    ConquerRevealSequencer,
    draw_face_down_card,
)
from game.components.conquer_tactics_rail import (
    ACTION_COMBINE,
    ACTION_DISMANTLE,
    ACTION_GAMBLE,
    ACTION_PLAY,
    ACTION_SKIP,
    ConquerTacticsRail,
)
from game.components.conquer_timeline_panel import ConquerTimelinePanel, AUTO_ADVANCE_MS
from game.components.easing import clamp01, ease_out_back, ease_out_quad
from game.components.cards.hand import Hand
from game.components.figures.family_configs.skill_config import (
    SKILL_DEFINITIONS,
    get_advantage_suit,
)
from game.components.figures.figure_manager import FigureManager
from game.screens.conquer_flow import (
    ConquerObjective,
    TimelineStep,
    derive_conquer_objective,
)
from game.screens.battle_screen import BattleScreen
from game.screens.battle_shop_screen import BattleShopScreen
from game.screens.field_screen import FieldScreen
from game.screens.game_screen import GameScreen
from game.screens.screen import Screen
from utils import battle_shop_service, game_service, onboarding_service
from utils.background_poller import BackgroundPoller
from utils.perf_monitor import perf_section
from utils.utils import GameButton


logger = logging.getLogger('nk.screens.conquer_game')


class ConquerGameScreen(GameScreen):
    """Focused conquer battle shell with Field / Battle Shop / Battle tabs."""

    CONQUER_SUBSCREENS = ('field', 'battle_shop', 'battle')
    # Unified top panel timeline + active info box.
    HEADER_H_FACTOR = 0.22
    CONQUER_BATTLE_MOVE_PANEL_MAX_MOVES = 10
    TACTIC_FLIGHT_MS = 450
    FIELD_REPLAY_ENCHANTMENT_SPELLS = ('Poison', 'Health Boost')
    FIELD_REPLAY_TARGETED_SPELLS = ('Poison', 'Health Boost', 'Explosion')
    CONQUER_CARD_EFFECT_SPELLS = (
        'Draw 2 MainCards',
        'Draw 2 SideCards',
        'Draw 4 MainCards',
        'Fill up to 10',
        'Dump Cards',
        'Forced Deal',
    )
    CONQUER_CARD_EFFECT_KEYS = (
        'drawn_cards',
        'cards_drawn',
        'cards_given',
        'cards_received',
        'caster_gave',
        'caster_received',
        'opponent_gave',
        'opponent_received',
        'caster_dumped',
        'opponent_dumped',
        'caster_dumped_cards',
        'opponent_dumped_cards',
        'opponent_drawn_cards',
        'main_cards_filled',
        'side_cards_filled',
    )
    # If the player does not press the "Finish Battle" header button within
    # this many milliseconds of it becoming available, auto-trigger the
    # resolution so a lingering tab does not stall the conquer game.
    FINISH_BATTLE_AUTO_TRIGGER_MS = 10000
    # When in moves phase and the user navigates away from the battle shop,
    # snap them back after this many ms.
    BATTLE_SHOP_SNAPBACK_MS = 2000
    BATTLE_STATE_POLL_MS = 850

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
        self._badge_font = settings.get_font(settings.mobile_font_size(
            int(0.015 * settings.SCREEN_HEIGHT * _UI_SCALE),
            settings.FS_BODY), bold=True)

        self._field_unseen_count = 0
        self._last_seen_figure_ids = None
        self._battle_unseen_count = 0
        self._last_seen_battle_round = None

        _report(0.10, 'Loading conquer figures ...')
        self.figure_manager = FigureManager()

        # Hands are kept as data sources for prelude-drawn cards and battle-shop
        # eligibility, but they are not exposed as conquer UI chrome.
        _report(0.20, 'Loading conquer cards ...')
        self.main_hand = Hand(self.window, self.state,
                              x=settings.MAIN_HAND_X, y=settings.MAIN_HAND_Y)
        self.side_hand = Hand(self.window, self.state,
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
            mode='conquer_battle',
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
            max(settings.FS_CONQUER_META,
                int(0.015 * settings.SCREEN_HEIGHT * _UI_SCALE)), bold=True)
        self._conquer_battle_coach_buttons = []
        self._conquer_battle_coach_step = None
        self._conquer_battle_coach_pressed_button_action = None
        self._conquer_battle_coach_font = settings.get_font(
            max(14, int(0.018 * settings.SCREEN_HEIGHT)))
        self._conquer_battle_coach_title_font = settings.get_font(
            max(16, int(0.024 * settings.SCREEN_HEIGHT)), bold=True)
        # Slightly larger font for the persistent top-row Withdraw button
        # and status pill so the round indicator stays readable at a glance.
        self._conquer_status_font = settings.get_font(
            settings.FS_SMALL, bold=True)
        self._conquer_timeline_panel = ConquerTimelinePanel(self.window)
        self._conquer_timeline_hover_open = False
        self._conquer_timeline_expanded_rect = None
        self._conquer_timeline_toggle_rect = None
        self._conquer_collapsed_header_rect = None
        # Tracks when the "Finish Battle" header button first became available
        # so we can auto-trigger after a short timeout if the user does not
        # click it.  Reset whenever the button is unavailable again.
        self._finish_battle_available_since_ms = None
        # Tracks an interactive timeline step that currently has exactly one
        # eligible option, so we can auto-fire it after AUTO_ADVANCE_MS while
        # still letting the user pre-empt with the timeline 'Next' button.
        # Shape: ((kind, payload), first_seen_tick_ms) or None.
        self._auto_single_option_pending = None
        self._conquer_tactic_cache_key = None
        self._conquer_tactic_cache = []
        self._conquer_opponent_tactic_cache_key = None
        self._conquer_opponent_tactic_cache = []
        self._battle_state_poller = None
        self._battle_state_poller_key = None
        self._battle_state_pending_key = None
        self._battle_state_last_poll_ms = 0
        self._conquer_battle_move_cache_key = None
        self._conquer_battle_move_cache = []
        self._conquer_battle_move_icon_caches = {}
        self._conquer_battle_move_manager = None
        self._battle_intro_dialogue = None  # first-battle teaching window
        self._conquer_lane_context_cache_key = None
        self._conquer_lane_context_cache = None
        self._conquer_duel_lane_render_cache_key = None
        self._conquer_duel_lane_render_cache_surface = None
        self._conquer_duel_lane_render_cache_rect = None
        self._conquer_tactic_power_cache_key = None
        self._conquer_tactic_power_cache = {}
        self._conquer_move_panel_title_font = settings.get_font(
            settings.FS_CONQUER_LABEL, bold=True)
        self._conquer_move_panel_empty_font = settings.get_font(
            max(settings.FS_CONQUER_LABEL, int(settings.FS_TINY * 0.95)), bold=True)

        # Unified tactics-hand UI (Phase 9 redesign).  These are lightweight
        # overlays — when the active game uses ``conquer_move_model='tactics_hand'``
        # they render on top of the field/battle subscreens; for legacy
        # ``battle_move`` games they remain inert.
        self._tactics_rail = ConquerTacticsRail(self)
        self._round_ledger = ConquerRoundLedger(self)
        # Touch pin owner: phones have no hover, so explanations pin on tap.
        # Only one pin may be active across the three pinnable surfaces
        # (support badges here, timeline steps in the panel, round cards in
        # the ledger); setting any pin dismisses the others.
        self._conquer_support_touch_pin = None
        self._tactic_flight_animation = None
        # Battle-result payoff: the outcome banner/confetti sequence that
        # plays on this screen before the result dialogue opens.
        # ``_conquer_payoff_pending`` holds the stashed server result while
        # the sequence plays; ``_conquer_payoff_until_ms`` is 0 until the
        # effects actually start (they wait for any in-flight round reveal).
        self._conquer_payoff_pending = None
        self._conquer_payoff_until_ms = 0
        # Battle-start moment: "3·2·1·GO!" countdown fired when the tactics
        # phase begins (battle_turn_player_id assigned / the diff appears),
        # plus per-beat sound bookkeeping.  Rail actions are blocked while
        # the countdown plays (see conquer_action_block_reason).
        self._battle_countdown_started_ms = 0
        self._battle_countdown_until_ms = 0
        self._battle_countdown_last_beat = -1
        # Battle-start detection: ``_conquer_countdown_done`` fires the
        # moment once per game; ``_conquer_saw_prebattle`` records that we
        # watched the pre-battle → tactics transition on-screen (so a reload
        # straight into an in-progress battle stays silent).
        self._conquer_countdown_done = False
        self._conquer_saw_prebattle = False
        # Duel-lane fighter entrances: fighters scale-pop into the lane the
        # first time they appear.  ``None`` seen-set = unseeded; a game that
        # is already mid-battle on first sight seeds silently so rejoining
        # never replays the entrance (same contract as the reveal sequencer).
        self._conquer_lane_figure_seen = None
        self._conquer_lane_figure_entrances = {}
        # Staged round-reveal choreography (display-only; see
        # ``game/components/conquer_reveal_sequencer.py``).
        self._conquer_reveal_sequencer = ConquerRevealSequencer(self)
        # Rolling battle feed: short narration entries emitted at reveal
        # beats (flip / impact) and gamble results. Each entry is
        # ``{'text', 'color', 'added_ms'}``; entries fade out after
        # ``CONQUER_FEED_TTL_MS``.
        self._conquer_battle_feed = []

        # Visual-effects layer (spell projectiles, impact glows, particle
        # bursts, floating numbers, round banners).  See
        # ``game/components/conquer_effects.py``.
        self._conquer_effects = ConquerEffectsLayer(
            self.window, self._lookup_conquer_figure_rect)
        # Frame-to-frame trackers used by spell-event detection.  ``_seen_*``
        # filters dedupe events across poller ticks; ``_prev_*`` snapshots
        # enable disappearance / round-change diffs.
        self._seen_active_spell_anim_ids: set = set()
        self._prev_visible_figure_rects = {}
        self._spell_anim_fired = set()
        # Maps a spell ``step_key`` -> ms timestamp at which the spell's
        # card animation reaches the tactics rail.  The rail withholds that
        # spell's resolution-step mutation until this moment so the effect
        # becomes visible exactly when the animation lands (see
        # ``conquer_revealed_spell_step_count`` and the timeline panel's
        # ``currently_resolved_step_index``).
        self._conquer_spell_anim_impact_ms: dict = {}
        self._recent_spell_timeline_names = []
        self._last_announced_battle_round = 0
        self._round_transition_until_ms = 0
        # Round-reveal UX state: the last tally-tick sound timestamp
        # (rate limit) and whether the final round was announced as
        # contested (drives the ledger's stakes border).
        self._conquer_tally_tick_last_ms = 0
        self._final_round_contested = False

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
                self._battle_state_poller = None
                self._battle_state_poller_key = None
                self._battle_state_pending_key = None
                if getattr(self.state.game, 'state', None) != 'finished':
                    self.state.game.game_over = False
                    self.state.game.pending_game_over = None
                    self.state.game.game_over_shown = False
        self._normalize_conquer_subscreen()
        if self.state.game and getattr(self.state.game, '_conquer_game_entered', False) is False:
            self.state.subscreen = 'field'
            self.state.game._conquer_game_entered = True
        if self.state.game:
            starter = getattr(
                self.state.game, 'start_game_start_notification_if_needed', None)
            if callable(starter):
                try:
                    starter()
                except Exception:
                    pass
        # Cold-load priming: request a tactics snapshot up front so the
        # round ledger / timeline catch up without a blocking render fetch.
        if self.state.game and self._is_tactics_hand_game():
            self._request_battle_state_poll(force=True)
        # Figure entrance: the field figures cascade in whenever the battle
        # screen is (re)entered — the config screen does the same on open.
        field = self.subscreens.get('field') if hasattr(self, 'subscreens') else None
        if field is not None and hasattr(field, 'begin_figure_entrance_cascade'):
            try:
                field.begin_figure_entrance_cascade()
            except Exception:
                pass

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
        if self._is_tactics_hand_game():
            self.state.subscreen = 'field'
            return
        if getattr(self.state, 'subscreen', None) not in self.CONQUER_SUBSCREENS:
            self.state.subscreen = 'field'

    # ----------------------------------------------------- tactics-hand mode
    def _is_tactics_hand_game(self):
        """True if the active conquer game uses the unified tactics-hand UI."""
        game = self.state.game
        if not game or getattr(game, 'mode', 'duel') != 'conquer':
            return False
        return getattr(game, 'conquer_move_model', 'battle_move') == 'tactics_hand'

    def _first_conquest_tutorial_active(self):
        """True while the player is still in their first conquer battle.

        Drives one-time educational callouts (e.g. what a Dagger does). The
        ``finish_first_conquer_battle`` step is only marked once the first
        conquer battle resolves, so it is reliably absent during it.
        """
        onboarding = (getattr(self.state, 'user_dict', None) or {}).get('onboarding') or {}
        if not onboarding or onboarding.get('onboarding_skipped'):
            return False
        completed = set(onboarding.get('completed_steps') or [])
        return 'finish_first_conquer_battle' not in completed

    def _is_battle_phase_active(self):
        """True if any battle round (1..3) is in flight or just resolved."""
        game = self.state.game
        if not game:
            return False
        if getattr(game, 'last_battle_result', None):
            return True
        if getattr(game, 'battle_turn_player_id', None) is not None:
            return True
        return getattr(game, 'battle_round', 0) in (1, 2, 3)

    def _uses_lightweight_active_battle_polling(self):
        game = self.state.game
        if not game or not self._is_tactics_hand_game():
            return False
        if getattr(game, 'last_battle_result', None) or getattr(game, 'game_over', False):
            return False
        return self._is_battle_phase_active()

    def _conquer_nav_buttons(self):
        if self._is_tactics_hand_game():
            return []
        return self.game_buttons

    def _conquer_layout_mode(self):
        game = self.state.game
        if not game:
            return 'pre_battle'
        if getattr(game, 'last_battle_result', None):
            return 'result'
        if (getattr(game, 'battle_turn_player_id', None) is not None
                or getattr(game, 'battle_round', 0) in (1, 2, 3)):
            return 'battle'
        return 'pre_battle'

    def _conquer_effective_layout_mode(self):
        mode = self._conquer_layout_mode()
        if (mode in ('battle', 'result')
                and self._should_use_collapsed_conquer_header()
                and self._is_conquer_timeline_overlay_open()):
            return 'pre_battle'
        return mode

    def _should_use_collapsed_conquer_header(self):
        # Tactics-hand games always use the persistent two-row header so
        # the top row is constant across pre-battle / battle / result and
        # only the timeline row reacts to hover-expansion.
        return self._is_tactics_hand_game()

    def _is_conquer_timeline_overlay_open(self):
        # Explicit toggle (via chevron button) replaces the old hover
        # expansion. The state survives across frames until the user
        # collapses again.
        return bool(getattr(self, '_conquer_timeline_hover_open', False))

    def _close_conquer_timeline_overlay(self):
        self._conquer_timeline_hover_open = False
        self._conquer_timeline_expanded_rect = None

    def _toggle_conquer_timeline_overlay(self):
        self._conquer_timeline_hover_open = not bool(
            getattr(self, '_conquer_timeline_hover_open', False))
        if not self._conquer_timeline_hover_open:
            self._conquer_timeline_expanded_rect = None

    def _conquer_timeline_overlay_rect(self):
        # The overlay extends only the timeline row downward so the top
        # row stays untouched between collapsed and expanded states.
        header = self._conquer_header_layout()
        timeline_row = header.timeline_row_rect
        if not timeline_row or timeline_row[3] <= 0:
            return pygame.Rect(
                0, 0, settings.SCREEN_WIDTH,
                int(settings.SCREEN_HEIGHT * self.HEADER_H_FACTOR),
            )
        x, y, w, _h = timeline_row
        expanded_header = compute_conquer_layout(
            settings.SCREEN_WIDTH,
            settings.SCREEN_HEIGHT,
            mode='pre_battle',
        ).header.full_rect
        bottom = max(y + _h, expanded_header[1] + expanded_header[3])
        return pygame.Rect(x, y, w, bottom - y)

    def _sync_conquer_timeline_hover_state(self):
        # The timeline overlay is an explicit toggle (chevron button); it
        # never opens on its own — auto-opening at battle start compressed
        # the battle layout until the player found the chevron. We only
        # keep the overlay rect in sync with the current header layout.
        if not self._should_use_collapsed_conquer_header():
            self._close_conquer_timeline_overlay()
            return
        if self._conquer_layout_mode() == 'pre_battle':
            self._close_conquer_timeline_overlay()
            return
        if getattr(self, '_conquer_timeline_hover_open', False):
            self._conquer_timeline_expanded_rect = self._conquer_timeline_overlay_rect()
        else:
            self._conquer_timeline_expanded_rect = None

    def _conquer_header_layout(self):
        mode = self._conquer_layout_mode()
        return compute_conquer_layout(
            settings.SCREEN_WIDTH,
            settings.SCREEN_HEIGHT,
            mode=mode,
        ).header

    def _conquer_header_title(self):
        """Compact, redundancy-free top-row title.

        Combines tier, land suit bonus and opponent name into a single
        bullet-separated string; falls back gracefully when fields are
        missing.
        """
        game = self.state.game
        if not game:
            return 'Conquer Battle'
        tier = getattr(game, 'land_tier', None)
        opponent = getattr(game, 'opponent_name', None) or 'Defender'
        bonus_suit, bonus_value = self._conquer_effective_land_bonus(game)
        parts = []
        if tier:
            parts.append(f'Tier {tier} Land')
        else:
            parts.append('Conquer Battle')
        if bonus_suit and bonus_value:
            parts.append(f'{bonus_suit} {bonus_value:+d}')
        parts.append(f'vs {opponent}')
        return '  ·  '.join(parts)

    @staticmethod
    def _conquer_effective_land_bonus(game):
        """(suit, value) of the land bonus with Landslide inversion applied."""
        if game is None:
            return None, 0
        getter = getattr(game, 'effective_land_bonus', None)
        if callable(getter):
            return getter()
        suit = getattr(game, 'land_suit_bonus_suit', None)
        value = getattr(game, 'land_suit_bonus_value', None)
        return (suit, int(value)) if suit and value else (None, 0)

    def _conquer_combined_status_label(self):
        """Single status string for the top row (no chip soup)."""
        game = self.state.game
        if not game:
            return ''
        result = getattr(game, 'last_battle_result', None)
        if isinstance(result, dict) and result:
            outcome = result.get('conquer_result') or result.get('outcome')
            if outcome == 'draw':
                return 'Resolved · Draw'
            winner = result.get('winner_name')
            return f'Resolved · {winner} won' if winner else 'Resolved'

        active_step = self.active_conquer_timeline_step()
        if active_step is not None:
            title = getattr(active_step, 'title', '') or 'Next step'
            tone = getattr(active_step, 'tone', '')
            if getattr(active_step, 'primary_action', None) == 'next':
                prefix = 'Next'
            elif getattr(active_step, 'interactive', False) or tone == 'action':
                prefix = 'Action'
            elif tone == 'waiting':
                prefix = 'Waiting'
            else:
                prefix = 'Status'
            return f'{prefix} · {title}'

        round_no = getattr(game, 'battle_round', 0) or 0
        turn_pid = getattr(game, 'battle_turn_player_id', None)
        player_id = getattr(game, 'player_id', None)
        if turn_pid is not None:
            phase = f'Round {min(int(round_no) + 1, 3)}/3'
        else:
            phase = 'Pre-battle'
        if turn_pid is None:
            who = 'Preparing'
        elif self._ids_equal(turn_pid, player_id):
            who = 'Your move'
        else:
            who = 'Opponent move'
        return f'{phase} · {who}'

    def _conquer_status_chips(self):
        game = self.state.game
        if not game:
            return []

        round_no = getattr(game, 'battle_round', 0) or 0
        result = getattr(game, 'last_battle_result', None)
        turn_pid = getattr(game, 'battle_turn_player_id', None)
        player_id = getattr(game, 'player_id', None)
        if result:
            phase = 'Result'
        elif turn_pid is not None:
            phase = f'Round {min(int(round_no) + 1, 3)}/3'
        else:
            phase = 'Battle'

        if result:
            turn = 'Resolved'
        elif turn_pid is None:
            turn = 'Preparing'
        elif self._ids_equal(turn_pid, player_id):
            turn = 'Your turn'
        else:
            turn = 'Opponent turn'

        chips = [phase, turn]
        tier = getattr(game, 'land_tier', None)
        if tier:
            chips.append(f'Stake: Tier {tier}')
        suit, bonus = self._conquer_effective_land_bonus(game)
        if suit and bonus:
            chips.append(f'{suit} {bonus:+d}')
        return chips

    def _conquer_narration_line(self):
        game = self.state.game
        if not game:
            return ''
        result = getattr(game, 'last_battle_result', None)
        if isinstance(result, dict) and result:
            conquer_result = result.get('conquer_result') or result.get('outcome')
            if conquer_result == 'draw':
                return 'Battle resolved as a draw. No loot changed hands.'
            winner = result.get('winner_name')
            loser = result.get('loser_name')
            if winner and loser:
                return f'Battle resolved: {winner} defeated {loser}.'
            return 'Battle resolved. Open the result to review the final outcome.'

        round_no = getattr(game, 'battle_round', 0) or 0
        turn_pid = getattr(game, 'battle_turn_player_id', None)
        player_id = getattr(game, 'player_id', None)
        round_label = min(int(round_no) + 1, 3) if turn_pid is not None else 1
        if self._ids_equal(turn_pid, player_id):
            return f'Round {round_label}: your tactic action is pending.'
        if turn_pid is not None:
            return f'Round {round_label}: waiting for the opponent tactic.'
        return 'Battle rounds are being prepared.'

    def _conquer_battle_timeline_steps(self, base_steps):
        game = self.state.game
        if not game:
            return base_steps
        base_steps = self._apply_single_option_step_info(base_steps)
        battle_started = (
            getattr(game, 'battle_turn_player_id', None) is not None
            or getattr(game, 'battle_round', 0) in (1, 2, 3)
            or bool(getattr(game, 'last_battle_result', None))
        )
        if not battle_started:
            return base_steps

        player_slots, opponent_slots = self._conquer_lane_played_tactics()
        current_round = int(getattr(game, 'battle_round', 0) or 0)
        opponent_name = getattr(game, 'opponent_name', None) or 'Opponent'
        finished = bool(getattr(game, 'last_battle_result', None))
        turn_pid = getattr(game, 'battle_turn_player_id', None)
        player_id = getattr(game, 'player_id', None)
        steps = list(base_steps)
        for idx in range(3):
            you = player_slots[idx]
            opp = opponent_slots[idx]
            you_played = you is not None
            opp_played = opp is not None
            is_current = idx == current_round and not finished
            if not (you_played or opp_played) and not is_current:
                continue

            you_label = self._conquer_lane_move_name(you) if you_played else 'pending'
            opp_label = self._conquer_lane_move_name(opp) if opp_played else 'hidden'

            # ---- player step --------------------------------------
            you_active = (
                is_current and not you_played
                and (self._ids_equal(turn_pid, player_id) or turn_pid is None)
            )
            if you_played:
                you_body = f'You played {you_label}.'
                you_tone = 'good'
            elif you_active:
                you_body = 'Pick a tactic to commit.'
                you_tone = 'action'
            elif is_current:
                you_body = f'Waiting for {opponent_name}.'
                you_tone = 'waiting'
            else:
                you_body = 'Your tactic was not played.'
                you_tone = 'neutral'
            steps.append(TimelineStep(
                kind=f'battle_round_{idx + 1}_player',
                title=f'R{idx + 1} You',
                owner='you',
                icon_kind='tactic',
                icon_payload={'move': you, 'side': 'you'},
                completed=you_played,
                active=you_active,
                interactive=False,
                tone=you_tone,
                sidenote='your tactic',
                info_headline=f'Round {idx + 1} · You',
                info_body=you_body,
                info_assets=tuple(
                    [{'kind': 'tactic', 'move': you}] if you is not None else []
                ),
            ))

            # ---- opponent step ------------------------------------
            opp_active = (
                is_current and not opp_played
                and turn_pid is not None and not self._ids_equal(turn_pid, player_id)
            )
            if opp_played:
                opp_body = f'{opponent_name} played {opp_label}.'
                opp_tone = 'neutral'
            elif opp_active:
                opp_body = f'{opponent_name} is choosing a tactic.'
                opp_tone = 'waiting'
            elif is_current:
                opp_body = f'{opponent_name} will reply after you.'
                opp_tone = 'neutral'
            else:
                opp_body = f'{opponent_name} did not play.'
                opp_tone = 'neutral'
            steps.append(TimelineStep(
                kind=f'battle_round_{idx + 1}_opponent',
                title=f'R{idx + 1} {opponent_name[:6]}',
                owner='opp',
                icon_kind='tactic',
                icon_payload={'move': opp, 'side': 'opp'},
                completed=opp_played,
                active=opp_active,
                interactive=False,
                tone=opp_tone,
                sidenote='opponent tactic',
                info_headline=f'Round {idx + 1} · {opponent_name}',
                info_body=opp_body,
                info_assets=tuple(
                    [{'kind': 'tactic', 'move': opp}] if opp is not None else []
                ),
            ))
        return steps

    def _open_tactics_hand_result_dialogue(self):
        game = self.state.game
        result = getattr(game, 'last_battle_result', None) if game else None
        if isinstance(result, dict) and result.get('conquer_result'):
            self._handle_conquer_result_response(result)

    # ------------------------------------------------- battle-result payoff

    #: Duration of the on-screen outcome payoff before the result dialogue.
    PAYOFF_WIN_MS = 1500
    PAYOFF_LOSE_MS = 1200

    def _conquer_outcome_kind(self, result):
        """Collapse a conquer result payload to ``'win' | 'lose' | 'draw'``.

        Mirrors the branch conditions of the base
        ``_handle_conquer_result_response`` so the on-screen payoff always
        matches the dialogue title family ('Land Conquered!' / 'Defence
        Successful!' → win; 'Land Lost!' / 'Attack Failed' → lose).
        """
        if result.get('conquer_result') == 'draw':
            return 'draw'
        attacker_won = bool(result.get('attacker_won'))
        is_attacker = self._is_current_player_conquer_attacker(result)
        return 'win' if attacker_won == is_attacker else 'lose'

    def _handle_conquer_result_response(self, result):
        """Conquer override: stage an on-screen payoff before the dialogue.

        Stashes the result and defers the base implementation (which owns
        the ``game_over`` dialogue, its fanfare, and the
        ``_conquer_result_dialogue_shown`` flag) until the payoff finishes.
        Fail-soft: any problem falls straight through to the base path so
        the result dialogue can never be lost.
        """
        try:
            game = self.state.game if self.state else None
            effects = getattr(self, '_conquer_effects', None)
            if (not isinstance(result, dict)
                    or not result.get('conquer_result')
                    or game is None or effects is None):
                return super()._handle_conquer_result_response(result)
            # Re-entrancy: the battle-state poll drain re-delivers the
            # result every poll until the dialogue has shown; once a payoff
            # is staged (or the dialogue already showed) swallow the repeat.
            if getattr(game, '_conquer_result_dialogue_shown', False):
                return True
            if self._conquer_payoff_pending is not None:
                return True
            self._conquer_payoff_pending = result
            self._conquer_payoff_until_ms = 0  # effects start in the pump
            return True
        except Exception:
            self._conquer_payoff_pending = None
            return super()._handle_conquer_result_response(result)

    def _conquer_reveal_sequencer_busy(self):
        """True while the round-reveal choreography still owns the stage."""
        sequencer = getattr(self, '_conquer_reveal_sequencer', None)
        if sequencer is None:
            return False
        try:
            return bool(sequencer.is_active() or sequencer.has_pending())
        except Exception:
            return False

    def _start_conquer_result_payoff(self, kind):
        """Spawn the celebration / rout effects for the battle outcome.

        Draw-only and fail-soft.  No fanfare here — the result dialogue
        plays the real win/lose sound via ``sound.play_for_dialogue`` when
        it opens; the payoff only uses light in-world cues.
        """
        effects = getattr(self, '_conquer_effects', None)
        if effects is None:
            return
        screen_rect = pygame.Rect(0, 0, self.window.get_width(),
                                  self.window.get_height())
        ledger = getattr(self, '_round_ledger', None)
        circle = getattr(ledger, '_total_circle_rect', None) if ledger else None
        try:
            if kind == 'win':
                effects.spawn_banner('VICTORY', (238, 206, 130),
                                     duration_ms=self.PAYOFF_WIN_MS)
                effects.spawn_confetti(
                    screen_rect,
                    [(238, 206, 130), (150, 230, 170), (255, 245, 200),
                     (214, 184, 112)],
                    count=54, delay_ms=120)
                effects.spawn_shake(amplitude=5, duration_ms=260)
                if circle is not None:
                    circle = pygame.Rect(circle)
                    effects.spawn_rect_pulse(circle, (238, 206, 130),
                                             duration_ms=700, scale=1.2)
                    effects.spawn_burst(circle, (238, 206, 130),
                                        secondary=(150, 230, 170),
                                        count=22, upward_bias=0.65,
                                        speed=(150.0, 280.0), delay_ms=120)
                    effects.spawn_burst(circle, (255, 245, 200),
                                        secondary=(238, 206, 130),
                                        count=16, upward_bias=0.65,
                                        speed=(120.0, 220.0), delay_ms=340)
            elif kind == 'lose':
                effects.spawn_banner('DEFEAT', (210, 90, 80),
                                     duration_ms=self.PAYOFF_LOSE_MS)
                # Slow ember/ash fall instead of festive confetti.
                effects.spawn_confetti(
                    screen_rect,
                    [(120, 96, 88), (96, 78, 70), (168, 110, 92)],
                    count=36, fall_speed=(60.0, 130.0), gravity=90.0,
                    life_ms=(800, 1400))
                effects.spawn_shake(amplitude=6, duration_ms=200)
                if circle is not None:
                    effects.spawn_rect_pulse(pygame.Rect(circle),
                                             (210, 90, 80),
                                             duration_ms=620, scale=1.1)
            else:
                effects.spawn_banner('DRAW', (210, 200, 170),
                                     duration_ms=self.PAYOFF_LOSE_MS)
                if circle is not None:
                    effects.spawn_rect_pulse(pygame.Rect(circle),
                                             (210, 200, 170),
                                             duration_ms=560, scale=1.0)
        except Exception:
            pass
        try:
            from utils import sound
            sound.play('coin' if kind == 'win' else 'figure_place')
        except Exception:
            pass

    def _pump_conquer_result_payoff(self):
        """Advance the deferred battle-result payoff (called from update()).

        Starts the effects once any in-flight round reveal has finished
        (so the outcome banner never talks over the final flip), then fires
        the base result handler — dialogue, fanfare, state flags — when the
        payoff window elapses.
        """
        pending = getattr(self, '_conquer_payoff_pending', None)
        if pending is None:
            return
        if self.state.game is None:
            self._conquer_payoff_pending = None
            self._conquer_payoff_until_ms = 0
            return
        now = pygame.time.get_ticks()
        if not self._conquer_payoff_until_ms:
            if self._conquer_reveal_sequencer_busy():
                return
            kind = 'draw'
            try:
                kind = self._conquer_outcome_kind(pending)
            except Exception:
                pass
            self._start_conquer_result_payoff(kind)
            self._conquer_payoff_until_ms = now + (
                self.PAYOFF_WIN_MS if kind == 'win' else self.PAYOFF_LOSE_MS)
            return
        if now < int(self._conquer_payoff_until_ms):
            return
        self._conquer_payoff_pending = None
        self._conquer_payoff_until_ms = 0
        try:
            super()._handle_conquer_result_response(pending)
        except Exception:
            logging.exception('conquer result dialogue failed after payoff')

    def _draw_conquer_status_chip(self, rect, label, border_color):
        pygame.draw.rect(self.window, (44, 36, 28), rect, border_radius=6)
        # Subtle pulsing border so the player's attention is drawn to the
        # current turn state without being noisy.  Pulse colour is anchored
        # to the supplied ``border_color`` (gold for your turn, blue-ish
        # for opponent's turn).  See Tier 4.3 in the conquer polish plan.
        try:
            pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() * 0.004)
            pr = int(border_color[0] + (255 - border_color[0]) * 0.35 * pulse)
            pg = int(border_color[1] + (255 - border_color[1]) * 0.35 * pulse)
            pb = int(border_color[2] + (255 - border_color[2]) * 0.35 * pulse)
            pulse_color = (max(0, min(255, pr)),
                           max(0, min(255, pg)),
                           max(0, min(255, pb)))
        except Exception:
            pulse_color = border_color
        pygame.draw.rect(self.window, pulse_color, rect, 2, border_radius=6)
        font = self._conquer_status_font
        text = self._fit_text(label, font, rect.width - 12)
        surf = font.render(text, True, (238, 218, 170))
        self.window.blit(surf, surf.get_rect(center=rect.center))

    def _conquer_withdraw_available(self):
        game = self.state.game
        if not game or getattr(game, 'game_over', False) or getattr(game, 'state', None) == 'finished':
            return False
        if getattr(self, '_withdraw_dialogue_open', False):
            return False
        # Once all three battle moves are played by both sides, the battle
        # is essentially over -- only Finish Battle should be available.
        try:
            if self._conquer_finish_available():
                return False
        except Exception:
            pass
        try:
            return bool(self._is_current_player_conquer_attacker())
        except Exception:
            return False

    def _conquer_finish_available(self):
        """True when all three battle rounds are played but unresolved.

        Surfaces a manual ``Finish Battle`` button so the user can trigger
        resolution if the auto-flow misses it after the last move.
        """
        game = self.state.game
        if not game or getattr(game, 'game_over', False):
            return False
        if getattr(game, 'last_battle_result', None):
            return False
        try:
            if not self._is_battle_phase_active():
                return False
        except Exception:
            return False
        try:
            context = self._conquer_lane_context()
            player_slots = context.get('player_slots') or []
            opponent_slots = context.get('opponent_slots') or []
        except Exception:
            return False
        if len(player_slots) < 3 or len(opponent_slots) < 3:
            return False
        # Hold the Finish button until the final round's reveal choreography
        # lands — resolving mid-reveal would step on the impact beat.
        sequencer = getattr(self, '_conquer_reveal_sequencer', None)
        if sequencer is not None:
            try:
                if sequencer.has_pending():
                    return False
            except Exception:
                pass
        return (all(p is not None for p in player_slots)
                and all(o is not None for o in opponent_slots))

    def _trigger_conquer_finish_battle(self):
        from utils.game_service import finish_battle
        game = self.state.game
        if not game:
            return False
        result = finish_battle(game.game_id, game.player_id, 0)
        if not result.get('success'):
            msg = result.get('message', 'Unknown error')
            self.make_dialogue_box(
                f'Failed to finish battle:\n{msg}',
                actions=['ok'], icon='info', title='Error')
            return False
        try:
            game.last_battle_result = result
        except Exception:
            pass
        if result.get('conquer_result'):
            self._handle_conquer_result_response(result)
        return True

    def _maybe_auto_trigger_finish_battle(self):
        """Auto-press the Finish Battle button after a short timeout.

        The user asked for the same idle behaviour as the rest of the
        timeline: if the player walks away while the resolution is
        waiting on the final click, fire it for them after
        ``FINISH_BATTLE_AUTO_TRIGGER_MS``.
        """
        try:
            available = bool(self._conquer_finish_available())
        except Exception:
            available = False
        if not available:
            self._finish_battle_available_since_ms = None
            return
        # Do not auto-fire while a modal dialogue or in-flight action holds
        # the screen — that would race the user's response.
        if self.dialogue_box is not None:
            return
        game = self.state.game
        if game is None or getattr(game, 'action_in_progress', False):
            return
        if getattr(game, 'last_battle_result', None):
            # Battle already resolved; the result dialogue handles the rest.
            self._finish_battle_available_since_ms = None
            return
        now = pygame.time.get_ticks()
        if self._finish_battle_available_since_ms is None:
            self._finish_battle_available_since_ms = now
            return
        if now - self._finish_battle_available_since_ms < \
                self.FINISH_BATTLE_AUTO_TRIGGER_MS:
            return
        # Fire once and clear the timer so we do not retry on transient
        # failures (the regular per-frame check will start a new timer if
        # the button is still around after a poll).
        self._finish_battle_available_since_ms = None
        try:
            self._trigger_conquer_finish_battle()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Auto-advance single-option interactive timeline steps
    # ------------------------------------------------------------------
    def _detect_single_option_context(self):
        """Return ``(kind, payload)`` for an active interactive selection
        that has exactly one eligible option, else ``(None, None)``.

        Mirrors the user-facing selection prompts so the same auto-hold
        UX as for non-interactive prelude steps can apply.
        """
        game = self.state.game
        field = self.subscreens.get('field') if hasattr(self, 'subscreens') else None
        if game is None or field is None:
            return None, None
        # Opponent defender selection (attacker picking who to hit).
        if getattr(field, 'defender_selection_mode', False):
            try:
                ids = field.selectable_defender_figure_ids()
            except Exception:
                ids = []
            if len(ids) == 1:
                return 'defender', int(ids[0])
        # Own defender selection (e.g. Invader Swap).
        if getattr(field, 'conquer_own_defender_mode', False):
            try:
                ids = field.selectable_own_defender_figure_ids()
            except Exception:
                ids = []
            if len(ids) == 1:
                return 'own_defender', int(ids[0])
        # Prelude-spell target selection.
        pending = getattr(self.state, 'pending_conquer_prelude_target', None)
        if isinstance(pending, dict):
            valid_ids = pending.get('valid_target_ids') or []
            if len(valid_ids) == 1:
                try:
                    return 'prelude_target', int(valid_ids[0])
                except (TypeError, ValueError):
                    return None, None
        return None, None

    def _maybe_auto_advance_single_option_step(self):
        """Hold a single-option interactive step for ``AUTO_ADVANCE_MS``
        then fire it automatically, matching prelude-spell hold timing.

        The timeline ``Next`` button can still skip the hold by calling
        :meth:`_fire_pending_single_option` directly.
        """
        if self._is_battle_phase_active():
            self._auto_single_option_pending = None
            return
        if self.dialogue_box is not None:
            self._auto_single_option_pending = None
            return
        game = self.state.game
        if game is None or getattr(game, 'action_in_progress', False):
            return
        kind, payload = self._detect_single_option_context()
        if kind is None:
            self._auto_single_option_pending = None
            return
        now = pygame.time.get_ticks()
        pending = self._auto_single_option_pending
        if pending is None or pending[0] != (kind, payload):
            self._auto_single_option_pending = ((kind, payload), now)
            return
        if now - pending[1] < AUTO_ADVANCE_MS:
            return
        self._fire_pending_single_option()

    def conquer_single_option_hold_ratio(self):
        """Remaining-time ratio [0, 1] of the pending single-option auto-pick.

        ``None`` when no auto-pick hold is running.  The timeline panel uses
        this to draw a countdown ring + Next button on the active interactive
        step so the auto-selection never fires without visible warning.
        """
        pending = getattr(self, '_auto_single_option_pending', None)
        if pending is None:
            return None
        elapsed = pygame.time.get_ticks() - pending[1]
        return max(0.0, min(1.0, 1.0 - elapsed / float(AUTO_ADVANCE_MS)))

    def _apply_single_option_step_info(self, steps):
        """Align the active selection step's info text with the auto-pick.

        While a single-option hold is running the panel adds a countdown +
        Next button; the step body derived from game state still says
        "select on the field", so rewrite it to announce the auto-selection.
        """
        if self.conquer_single_option_hold_ratio() is None:
            return steps
        kind, _payload = self._detect_single_option_context()
        step_kind = {
            'defender': 'defender',
            'own_defender': 'defender',
            'prelude_target': 'prelude_own',
        }.get(kind)
        if step_kind is None:
            return steps
        for step in steps:
            if step.kind == step_kind and step.active and step.interactive:
                step.info_body = (
                    'Only one legal choice — it will be selected '
                    'automatically. Press Next to continue now.'
                )
        return steps

    def _fire_pending_single_option(self):
        """Resolve the currently pending single-option step (if any)."""
        pending = self._auto_single_option_pending
        if pending is None:
            kind, payload = self._detect_single_option_context()
            if kind is None:
                return False
        else:
            kind, payload = pending[0]
        self._auto_single_option_pending = None
        game = self.state.game
        field = self.subscreens.get('field') if hasattr(self, 'subscreens') else None
        if game is None or field is None:
            return False
        if kind in ('defender', 'own_defender') and not getattr(game, 'advancing_figure_id', None):
            self._clear_stale_conquer_defender_flags_if_no_advance()
            if getattr(field, 'defender_selection_mode', False):
                field.defender_selection_mode = False
            if getattr(field, 'conquer_own_defender_mode', False):
                field.conquer_own_defender_mode = False
            if hasattr(field, '_reset_defender_selectable'):
                field._reset_defender_selectable()
            return False
        try:
            if kind == 'defender':
                from utils.game_service import select_defender
                result = select_defender(game.game_id, game.player_id, payload)
                if result.get('success'):
                    if result.get('game'):
                        game.update_from_dict(result['game'])
                    field.defender_selection_mode = False
                    if hasattr(field, '_reset_defender_selectable'):
                        field._reset_defender_selectable()
                    # Single-option auto-pick: the player made no real choice, so
                    # the timeline must not tag this figure "Chosen by you".
                    field._auto_selected_defender_id = payload
                    field._player_selected_defender_id = None
            elif kind == 'own_defender':
                from utils.game_service import select_conquer_own_defender
                result = select_conquer_own_defender(
                    game.game_id, game.player_id, payload
                )
                if result.get('success'):
                    if result.get('game'):
                        game.update_from_dict(result['game'])
                    field.conquer_own_defender_mode = False
                    if hasattr(field, '_reset_defender_selectable'):
                        field._reset_defender_selectable()
                    game.pending_conquer_own_defender_selection = False
            elif kind == 'prelude_target':
                target_fig = None
                for fig in getattr(field, 'figures', []) or []:
                    if getattr(fig, 'id', None) == payload:
                        target_fig = fig
                        break
                if target_fig is not None and hasattr(
                        field, '_apply_conquer_prelude_to_target'):
                    field._apply_conquer_prelude_to_target(target_fig)
        except Exception:
            return False
        try:
            self._sync_conquer_action_modes()
            self._auto_route_conquer_once()
        except Exception:
            pass
        return True

    def _draw_conquer_header_button(self, rect, label, color):
        mouse = pygame.mouse.get_pos()
        hovered = rect.collidepoint(mouse)
        bg = tuple(min(255, c + 24) for c in color) if hovered else color
        pygame.draw.rect(self.window, bg, rect, border_radius=6)
        pygame.draw.rect(self.window, (238, 219, 172), rect, 1, border_radius=6)
        font = self._conquer_status_font
        text = self._fit_text(label, font, rect.width - 12)
        surf = font.render(text, True, (255, 244, 216))
        self.window.blit(surf, surf.get_rect(center=rect.center))

    def _draw_conquer_collapsed_header(self):
        """Persistent two-row header.

        Top row: combined title · single status pill · withdraw button.
        It stays constant across collapsed and hover-expanded states.
        Timeline row: full timeline inline in pre-battle, or compact
        icon strip in battle/result (which the overlay can extend).
        """
        self._conquer_objective_action_rects = {}
        header = self._conquer_header_layout()
        top_row_rect = header.top_row_rect
        timeline_row_rect = header.timeline_row_rect
        if (not top_row_rect or top_row_rect[3] <= 0
                or not timeline_row_rect or timeline_row_rect[3] <= 0):
            self._conquer_collapsed_header_rect = None
            return

        top_rect = pygame.Rect(*top_row_rect)
        timeline_rect = pygame.Rect(*timeline_row_rect)
        self._conquer_collapsed_header_rect = top_rect.union(timeline_rect)

        # ---- top row ------------------------------------------------
        top_surface = pygame.Surface(top_rect.size, pygame.SRCALPHA)
        top_surface.fill((19, 18, 16, 242))
        self.window.blit(top_surface, top_rect.topleft)
        pygame.draw.line(self.window, (189, 149, 75),
                         (top_rect.left, top_rect.bottom - 1),
                         (top_rect.right, top_rect.bottom - 1), 2)

        pad_x = max(12, int(settings.SCREEN_WIDTH * 0.018))
        right_limit = top_rect.right - pad_x
        # Height tuned to fit the larger status font with a comfortable margin.
        status_font = self._conquer_status_font
        chip_h = max(28, min(top_rect.height - 6,
                             status_font.get_height() + 12))
        if self._conquer_finish_available():
            button_w = max(120, int(settings.SCREEN_WIDTH * 0.09))
            button_h = chip_h
            button_rect = pygame.Rect(
                right_limit - button_w,
                top_rect.centery - button_h // 2,
                button_w,
                button_h,
            )
            self._conquer_objective_action_rects['finish'] = button_rect
            # Saturated gold so it reads as the dominant call-to-action.
            self._draw_conquer_header_button(button_rect, 'Finish Battle', (152, 110, 36))
            right_limit = button_rect.left - max(8, pad_x // 2)
        if self._conquer_withdraw_available():
            button_w = max(96, int(settings.SCREEN_WIDTH * 0.075))
            button_h = chip_h
            button_rect = pygame.Rect(
                right_limit - button_w,
                top_rect.centery - button_h // 2,
                button_w,
                button_h,
            )
            self._conquer_objective_action_rects['withdraw'] = button_rect
            self._draw_conquer_header_button(button_rect, 'Withdraw', (93, 52, 48))
            right_limit = button_rect.left - max(8, pad_x // 2)

        status_label = self._conquer_combined_status_label()
        chip_font = status_font
        if status_label:
            chip_w = min(
                max(150, chip_font.size(status_label)[0] + 28),
                int(settings.SCREEN_WIDTH * 0.26),
            )
            chip_rect = pygame.Rect(
                right_limit - chip_w,
                top_rect.centery - chip_h // 2,
                chip_w,
                chip_h,
            )
            border = (255, 211, 116)
            game = self.state.game
            if game is not None:
                turn_pid = getattr(game, 'battle_turn_player_id', None)
                player_id = getattr(game, 'player_id', None)
                if getattr(game, 'last_battle_result', None):
                    border = (200, 180, 120)
                elif turn_pid is None:
                    border = (180, 160, 110)
                elif turn_pid == player_id:
                    border = (255, 211, 116)
                else:
                    border = (176, 209, 255)
            self._draw_conquer_status_chip(chip_rect, status_label, border)
            right_limit = chip_rect.left - max(8, pad_x // 2)

        title_font = self._conquer_header_font
        title_max_w = max(80, right_limit - top_rect.left - pad_x)
        title = self._fit_text(
            self._conquer_header_title(),
            title_font,
            title_max_w,
        )
        title_surf = title_font.render(title, True, (246, 222, 170))
        title_y = top_rect.centery - title_surf.get_height() // 2
        self.window.blit(title_surf, (top_rect.left + pad_x, title_y))

        # ---- timeline row ------------------------------------------
        timeline_surface = pygame.Surface(timeline_rect.size, pygame.SRCALPHA)
        timeline_surface.fill((19, 18, 16, 240))
        self.window.blit(timeline_surface, timeline_rect.topleft)
        pygame.draw.line(self.window, (110, 86, 50),
                         (timeline_rect.left, timeline_rect.bottom - 1),
                         (timeline_rect.right, timeline_rect.bottom - 1), 1)

        panel = getattr(self, '_conquer_timeline_panel', None)
        if panel is None:
            return
        # Pre-battle has plenty of vertical room: render the full timeline
        # body inline in the second row. Battle / result keep the compact\n        # icon strip with a chevron toggle to expand/collapse the full\n        # timeline as an overlay.
        layout_mode = self._conquer_layout_mode()
        inline_rect = timeline_rect.inflate(-int(pad_x * 0.5), -6)
        # Reserve a small button on the right edge of the collapsed strip
        # (battle / result) for the expand/collapse chevron. Pre-battle
        # mode renders the full timeline inline so no toggle is needed.
        self._conquer_timeline_toggle_rect = None
        if layout_mode == 'pre_battle' and inline_rect.height >= 60:
            if hasattr(panel, 'draw_within'):
                panel.draw_within(self, inline_rect)
            else:
                panel.draw_collapsed_strip(self, inline_rect)
        else:
            btn_size = max(16, min(inline_rect.height, 24))
            btn_rect = pygame.Rect(0, 0, btn_size, btn_size)
            btn_rect.right = inline_rect.right - 2
            btn_rect.centery = inline_rect.centery
            # Countdown label (60s per-round timer) sits left of the toggle.
            countdown_text = self._conquer_round_countdown_text()
            countdown_w = 0
            if countdown_text:
                cd_color = self._conquer_round_countdown_color()
                cache_key = (countdown_text, cd_color)
                cached = getattr(self, '_conquer_countdown_cache', None)
                if cached is None or cached[0] != cache_key:
                    cd_font = settings.get_font(
                        max(settings.FS_CONQUER_LABEL, int(settings.FS_SMALL * 1.0)), bold=True)
                    cd_surf = cd_font.render(countdown_text, True, cd_color)
                    self._conquer_countdown_cache = (cache_key, cd_surf)
                else:
                    cd_surf = cached[1]
                countdown_w = cd_surf.get_width() + 8
                cd_rect = cd_surf.get_rect(midright=(btn_rect.left - 6,
                                                     inline_rect.centery))
                self.window.blit(cd_surf, cd_rect.topleft)
            strip_right = btn_rect.left - countdown_w - 4
            strip_rect = pygame.Rect(
                inline_rect.left,
                inline_rect.top,
                max(1, strip_right - inline_rect.left),
                inline_rect.height,
            )
            # Mobile focus card: the history strip alone leaves the active
            # step unreadable until the overlay is expanded, so give the
            # right half of the row to a one-line icon + headline card
            # (tap pins the full tooltip).
            focus_rect = None
            focus_step = None
            if (settings.TOUCH_TARGET_MIN > 0 and strip_rect.width >= 260
                    and hasattr(panel, 'draw_focus_card')):
                focus_step = panel.active_step(self)
                if focus_step is not None:
                    focus_w = int(strip_rect.width * 0.56)
                    focus_rect = pygame.Rect(
                        strip_rect.right - focus_w,
                        strip_rect.top + 1,
                        focus_w,
                        max(1, strip_rect.height - 2),
                    )
                    strip_rect.width = max(1, strip_rect.width - focus_w - 6)
            if strip_rect.width >= 80 and strip_rect.height >= 16:
                panel.draw_collapsed_strip(self, strip_rect)
                if focus_rect is not None and focus_step is not None:
                    panel.draw_focus_card(self, focus_rect, focus_step)
            self._draw_conquer_timeline_toggle_button(btn_rect)
            self._conquer_timeline_toggle_rect = btn_rect

    def _conquer_round_countdown_text(self):
        """Return MM:SS countdown for the current battle round or '' if no
        timer applies (e.g. duel, pre-battle, finished, opponent's turn AI)."""
        game = getattr(self.state, 'game', None) if hasattr(self, 'state') else None
        if not game:
            return ''
        deadline = getattr(game, 'conquer_round_deadline_ts', None)
        if not deadline:
            return ''
        import time as _t
        remaining = max(0, int(round(float(deadline) - _t.time())))
        return f'{remaining // 60:02d}:{remaining % 60:02d}'

    def _conquer_round_countdown_color(self):
        game = getattr(self.state, 'game', None) if hasattr(self, 'state') else None
        deadline = getattr(game, 'conquer_round_deadline_ts', None) if game else None
        if not deadline:
            return (210, 200, 188)
        import time as _t
        remaining = float(deadline) - _t.time()
        if remaining <= 10:
            return (220, 80, 70)
        if remaining <= 20:
            return (230, 180, 80)
        return (210, 200, 188)

    def _draw_conquer_timeline_toggle_button(self, rect):
        """Small chevron button to expand/collapse the timeline overlay."""
        mouse = pygame.mouse.get_pos()
        hovered = rect.collidepoint(mouse)
        open_state = self._is_conquer_timeline_overlay_open()
        bg = (60, 48, 30) if hovered else (38, 30, 20)
        pygame.draw.rect(self.window, bg, rect, border_radius=4)
        pygame.draw.rect(self.window, (190, 152, 84), rect, 1, border_radius=4)
        cx, cy = rect.center
        s = max(3, min(rect.width, rect.height) // 3)
        color = (238, 218, 170)
        # Chevron up when expanded (to collapse), down when collapsed.
        if open_state:
            points = [(cx - s, cy + s // 2), (cx, cy - s // 2), (cx + s, cy + s // 2)]
        else:
            points = [(cx - s, cy - s // 2), (cx, cy + s // 2), (cx + s, cy - s // 2)]
        pygame.draw.lines(self.window, color, False, points, 2)

    @staticmethod
    def _conquer_touch_hit_rect(rect, min_size=None):
        """Return a screen-clipped touch target around a compact control."""
        hit = pygame.Rect(rect)
        target = int(min_size if min_size is not None
                     else settings.TOUCH_TARGET_MIN)
        if target > 0:
            hit = hit.inflate(
                max(0, target - hit.width),
                max(0, target - hit.height),
            )
        screen_rect = pygame.Rect(
            0, 0, settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT)
        # ``clip`` would shave pixels from controls near a screen edge. Clamp
        # instead so the target shifts inward and retains its ergonomic size.
        return hit.clamp(screen_rect)

    def _handle_collapsed_header_events(self, events):
        if not self._should_use_collapsed_conquer_header():
            return False
        toggle = getattr(self, '_conquer_timeline_toggle_rect', None)
        if toggle is None:
            return False
        for event in events:
            if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
                continue
            if self._conquer_touch_hit_rect(toggle).collidepoint(event.pos):
                self._toggle_conquer_timeline_overlay()
                return True
        return False

    # ------------------------------------------------------------ touch pins

    def _clear_conquer_touch_pins(self, except_for=None):
        """Enforce the single-pin rule across the pinnable surfaces.

        Support badges (this screen), timeline steps (the panel) and round
        cards (the ledger) each pin on tap; whichever pins last dismisses
        the others so at most one popover is ever on screen.
        """
        if except_for != 'support':
            self._conquer_support_touch_pin = None
        if except_for != 'timeline':
            panel = getattr(self, '_conquer_timeline_panel', None)
            if panel is not None and hasattr(panel, 'clear_touch_pin'):
                panel.clear_touch_pin()
        if except_for != 'ledger':
            ledger = getattr(self, '_round_ledger', None)
            if ledger is not None and hasattr(ledger, 'clear_touch_pin'):
                ledger.clear_touch_pin()

    def _conquer_support_pin_key(self, info):
        """Stable per-frame identity for a registered badge/chip rect."""
        entry = info.get('entry') if isinstance(info, dict) else None
        entry = entry if isinstance(entry, dict) else {}
        return (
            'badge',
            bool(info.get('is_player')),
            self._conquer_support_section_key(entry),
            str(entry.get('kind') or ''),
            str(entry.get('suit') or ''),
            str(entry.get('label') or ''),
            tuple(sorted(str(fig_id) for fig_id in
                         entry.get('source_figure_ids') or []
                         if fig_id is not None)),
        )

    def _conquer_support_tap_target(self, pos):
        """Badge/overflow chip under a tap, nearest-center among the
        touch-inflated hit rects (badge stacks overlap once inflated)."""
        best = None
        best_d = None
        for kind, infos in (
            ('badge', getattr(self, '_conquer_support_badge_rects', None) or []),
            ('overflow', getattr(self, '_conquer_support_overflow_rects', None) or []),
        ):
            for info in infos:
                rect = info.get('rect')
                if not rect:
                    continue
                rect = pygame.Rect(rect)
                if not self._conquer_touch_hit_rect(rect).collidepoint(pos):
                    continue
                d = ((rect.centerx - pos[0]) ** 2
                     + (rect.centery - pos[1]) ** 2)
                if best_d is None or d < best_d:
                    best, best_d = (kind, info), d
        return best

    def _conquer_support_overflow_pin_key(self, info):
        return ('overflow', bool(info.get('is_player')),
                str(info.get('section') or ''))

    def _handle_conquer_touch_pin_events(self, events):
        """Tap-to-pin dispatch (touch only).

        Slotted after the CTA buttons and the header chevron so those always
        win, and before lane-figure clicks so a badge tap cannot fall
        through to the figure underneath. Unclaimed taps dismiss any active
        pin but are NOT consumed — they still reach the surfaces below.
        """
        if settings.TOUCH_TARGET_MIN <= 0:
            return False
        if self.dialogue_box:
            return False
        sequencer = getattr(self, '_conquer_reveal_sequencer', None)
        if sequencer is not None and sequencer.is_active():
            return False
        for event in events:
            if event.type != MOUSEBUTTONDOWN or getattr(event, 'button', 0) != 1:
                continue
            panel = getattr(self, '_conquer_timeline_panel', None)
            if (panel is not None and hasattr(panel, 'handle_tap')
                    and panel.handle_tap(event.pos)):
                self._clear_conquer_touch_pins(except_for='timeline')
                return True
            target = self._conquer_support_tap_target(event.pos)
            if target is not None:
                kind, info = target
                key = (self._conquer_support_pin_key(info) if kind == 'badge'
                       else self._conquer_support_overflow_pin_key(info))
                toggled_off = (self._conquer_support_touch_pin == key)
                self._clear_conquer_touch_pins(except_for='support')
                self._conquer_support_touch_pin = None if toggled_off else key
                return True
            self._clear_conquer_touch_pins()
        return False

    def _conquer_timeline_overlay_right_reserve(self):
        """Width on the right edge of the expanded overlay reserved for the
        always-on countdown timer + chevron toggle.  Used to shrink the rect
        passed to ``ConquerTimelinePanel.draw_within`` so the last timeline
        bubble does not slide under the chrome."""
        toggle = getattr(self, '_conquer_timeline_toggle_rect', None)
        if toggle is None:
            return 0
        countdown_w = 0
        cached = getattr(self, '_conquer_countdown_cache', None)
        if cached and len(cached) >= 2 and cached[1] is not None:
            try:
                countdown_w = cached[1].get_width()
            except Exception:
                countdown_w = 0
        return int(toggle.width) + int(countdown_w) + 16

    def _redraw_collapsed_header_chrome_over_overlay(self, overlay_rect):
        """Re-draw the collapse chevron and round-countdown label on top of
        the expanded timeline overlay so they remain visible / clickable.

        ``_draw_conquer_collapsed_header`` stashes ``_conquer_timeline_toggle_rect``
        at the right edge of the collapsed strip; we reuse that position so
        click hit-testing keeps working unchanged.
        """
        toggle_rect = getattr(self, '_conquer_timeline_toggle_rect', None)
        if toggle_rect is None:
            return
        # Paint a small backing strip behind the chevron + countdown so the
        # overlay's panel chrome does not bleed through.
        bg_rect = pygame.Rect(toggle_rect)
        countdown_text = self._conquer_round_countdown_text()
        cd_surf = None
        if countdown_text:
            cd_color = self._conquer_round_countdown_color()
            cache_key = (countdown_text, cd_color)
            cached = getattr(self, '_conquer_countdown_cache', None)
            if cached is None or cached[0] != cache_key:
                cd_font = settings.get_font(
                    max(settings.FS_CONQUER_LABEL, int(settings.FS_SMALL * 1.0)), bold=True)
                cd_surf = cd_font.render(countdown_text, True, cd_color)
                self._conquer_countdown_cache = (cache_key, cd_surf)
            else:
                cd_surf = cached[1]
            extra_w = cd_surf.get_width() + 10
            bg_rect = pygame.Rect(
                toggle_rect.left - extra_w,
                toggle_rect.top - 2,
                toggle_rect.width + extra_w + 2,
                toggle_rect.height + 4,
            )
        else:
            bg_rect = bg_rect.inflate(4, 4)
        bg_surface = pygame.Surface(bg_rect.size, pygame.SRCALPHA)
        bg_surface.fill((19, 18, 16, 240))
        self.window.blit(bg_surface, bg_rect.topleft)
        if cd_surf is not None:
            cd_pos = cd_surf.get_rect(
                midright=(toggle_rect.left - 6, toggle_rect.centery))
            self.window.blit(cd_surf, cd_pos.topleft)
        self._draw_conquer_timeline_toggle_button(toggle_rect)

    def _active_round_player_slot_rect(self):
        game = self.state.game
        round_idx = int(getattr(game, 'battle_round', 0) or 0) if game else -1
        if round_idx not in (0, 1, 2):
            return None
        layout = compute_conquer_layout(
            settings.SCREEN_WIDTH,
            settings.SCREEN_HEIGHT,
            mode=self._conquer_effective_layout_mode(),
        )
        card = pygame.Rect(*layout.round_ledger.round_card_rects[round_idx])
        title_font = settings.get_font(max(settings.FS_CONQUER_LABEL, int(settings.FS_TINY * 0.95)), bold=True)
        chip_w = int(card.width * 0.34)
        chip_y = card.top + 4 + title_font.get_height() + 4
        chip_h = card.bottom - chip_y - 6
        return pygame.Rect(card.left + 4, chip_y, chip_w - 8, chip_h)

    def is_tactic_flight_active(self) -> bool:
        """True while the played-tactic flight animation is in progress.

        The rail consults this to disable action buttons during flight so
        the player cannot fire a second action (e.g. another play, or a
        skip) that would race the animation.
        """
        return bool(self.conquer_action_block_reason())

    def conquer_action_block_reason(self) -> str:
        """Human-readable reason rail actions are blocked, or ''.

        Covers the played-tactic flight animation, the round-transition
        pause, and the staged round-reveal sequence.
        """
        animation = getattr(self, '_tactic_flight_animation', None)
        if animation:
            try:
                now = pygame.time.get_ticks()
                duration = max(1, int(animation.get('duration') or self.TACTIC_FLIGHT_MS))
                elapsed = now - int(animation.get('started_at') or now)
                if elapsed <= duration:
                    return 'Tactic in flight…'
            except Exception:
                return 'Tactic in flight…'
        sequencer = getattr(self, '_conquer_reveal_sequencer', None)
        if sequencer is not None:
            try:
                if sequencer.is_active():
                    return 'Revealing round…'
            except Exception:
                pass
        # Battle-start countdown: the rail unlocks on GO.
        try:
            if self._is_battle_countdown_active():
                return 'Battle starting…'
        except Exception:
            pass
        # Brief round-transition pause (Tier 3.1): also block actions while
        # the "Round N" banner is animating in so the player gets a beat
        # to register the new round before being able to act.
        try:
            until = int(getattr(self, '_round_transition_until_ms', 0) or 0)
            if until and pygame.time.get_ticks() < until:
                return 'Tactic in flight…'
        except Exception:
            pass
        return ''

    def _start_tactic_flight_animation(self, move):
        if not (self._is_tactics_hand_game() and move):
            return
        target_rect = self._active_round_player_slot_rect()
        if target_rect is None:
            return
        move_id = move.get('id')
        source_rect = None
        rail = getattr(self, '_tactics_rail', None)
        cell_rect = getattr(rail, 'move_cell_rect', None)
        if callable(cell_rect) and move_id is not None:
            source_rect = cell_rect(int(move_id))
        if source_rect is None and rail is not None and hasattr(rail, 'rect'):
            try:
                source_rect = rail.rect()
            except Exception:
                source_rect = None
        if source_rect is None:
            source_rect = target_rect
        self._tactic_flight_animation = {
            'move': dict(move),
            'source': pygame.Rect(source_rect),
            'target': pygame.Rect(target_rect),
            'started_at': pygame.time.get_ticks(),
            'duration': self.TACTIC_FLIGHT_MS,
        }

    def _draw_tactic_flight_animation(self):
        animation = getattr(self, '_tactic_flight_animation', None)
        if not animation:
            return
        now = pygame.time.get_ticks()
        duration = max(1, int(animation.get('duration') or self.TACTIC_FLIGHT_MS))
        elapsed = now - int(animation.get('started_at') or now)
        if elapsed > duration:
            self._tactic_flight_animation = None
            # Landing beat: one-shot pulse on the slot the tactic settled
            # into so the flight has a visible payoff (fail-soft).
            effects = getattr(self, '_conquer_effects', None)
            if effects is not None:
                try:
                    effects.spawn_rect_pulse(
                        pygame.Rect(animation['target']), (120, 205, 220),
                        duration_ms=260, scale=0.7)
                except Exception:
                    pass
            return

        progress = max(0.0, min(1.0, elapsed / duration))
        eased = ease_out_quad(progress)
        source = pygame.Rect(animation['source'])
        target = pygame.Rect(animation['target'])
        cx = int(source.centerx + (target.centerx - source.centerx) * eased)
        cy = int(source.centery + (target.centery - source.centery) * eased)

        move = animation.get('move') or {}
        name = move.get('family_name') or 'Tactic'
        if name == 'Dagger' and (move.get('card_id_b') or move.get('secondary_card_id')):
            name = '2x Dagger'
        power = 0 if name == 'Block' else int(move.get('value') or 0)
        font = settings.get_font(settings.FS_CONQUER_LABEL, bold=True)
        label = self._fit_text(f'{name} {power}', font, max(72, target.width))
        label_surf = font.render(label, True, (218, 246, 244))
        pill = label_surf.get_rect()
        pill.inflate_ip(18, 10)
        # Landing squash: compress the pill vertically over the last stretch
        # of the flight so it visibly "settles" into the slot.
        land_t = (progress - 0.82) / 0.18
        if land_t > 0.0:
            squash = 1.0 - 0.22 * math.sin(clamp01(land_t) * math.pi)
            pill.height = max(label_surf.get_height() + 2, int(pill.height * squash))
        pill.center = (cx, cy)
        # Trailing glow: a few older positions, fading, behind the pill.  Adds
        # motion-feel without obscuring the label.
        for k in range(1, 5):
            tp = max(0.0, progress - 0.07 * k)
            ep = ease_out_quad(tp)
            tx = int(source.centerx + (target.centerx - source.centerx) * ep)
            ty = int(source.centery + (target.centery - source.centery) * ep)
            alpha = max(0, 110 - k * 22)
            r = max(0, 9 - k * 2)
            if r <= 0 or alpha <= 0:
                continue
            trail = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            pygame.draw.circle(trail, (120, 205, 220, alpha), (r, r), r)
            self.window.blit(trail, (tx - r, ty - r))
        panel = pygame.Surface(pill.size, pygame.SRCALPHA)
        panel.fill((38, 70, 72, 218))
        self.window.blit(panel, pill.topleft)
        pygame.draw.rect(self.window, (120, 205, 220), pill, 2, border_radius=pill.height // 2)
        self.window.blit(label_surf, label_surf.get_rect(center=pill.center))

    # --------------------------------------------------------- round reveal
    @staticmethod
    def _conquer_round_banner_label(battle_round: int) -> str:
        """Banner label for a zero-indexed ``battle_round`` (0..2)."""
        display = min(int(battle_round) + 1, 3)
        return 'Final Round' if display == 3 else f'Round {display}'

    def _is_conquer_final_round_contested(self) -> bool:
        """True when round 3 begins with the battle still inside one big
        tactic swing — close enough that the last round can flip it."""
        ledger = getattr(self, '_round_ledger', None)
        total = getattr(ledger, 'current_total_diff', None)
        if not callable(total):
            return False
        try:
            return abs(int(total())) <= 12
        except Exception:
            return False

    def conquer_round_reveal_stage(self, round_idx):
        """Stage info for the ledger's reveal choreography, or ``None``."""
        sequencer = getattr(self, '_conquer_reveal_sequencer', None)
        if sequencer is None:
            return None
        try:
            return sequencer.stage_for_round(round_idx)
        except Exception:
            return None

    def _conquer_round_card_rect(self, round_idx):
        if round_idx not in (0, 1, 2):
            return None
        try:
            layout = compute_conquer_layout(
                settings.SCREEN_WIDTH,
                settings.SCREEN_HEIGHT,
                mode=self._conquer_effective_layout_mode(),
            )
            return pygame.Rect(*layout.round_ledger.round_card_rects[round_idx])
        except Exception:
            return None

    def _on_conquer_round_reveal_event(self, round_idx, event, payload):
        """Reveal-sequencer beat hook: sound, effects, and feed entries."""
        from utils import sound
        try:
            player_slots, opponent_slots = self._conquer_lane_played_tactics_raw()
        except Exception:
            player_slots, opponent_slots = [None] * 3, [None] * 3
        you = player_slots[round_idx] if round_idx in (0, 1, 2) else None
        opp = opponent_slots[round_idx] if round_idx in (0, 1, 2) else None
        opponent_name = (getattr(self.state.game, 'opponent_name', None)
                         or 'Opponent') if self.state.game else 'Opponent'
        card_rect = self._conquer_round_card_rect(round_idx)
        effects = getattr(self, '_conquer_effects', None)

        if event == 'start':
            # HOLD tension beat: a soft riser + anticipation pulse on the
            # round card. Skip-beats and opp-seen entries (short/zero HOLD)
            # stay silent so the cue never doubles up with the flip sound.
            if int(payload.get('hold_ms') or 0) >= 200:
                if effects is not None and card_rect is not None:
                    try:
                        effects.spawn_rect_pulse(card_rect, (196, 162, 92),
                                                 duration_ms=300, scale=0.55)
                    except Exception:
                        pass
                try:
                    sound.play('reveal_hold')
                except Exception:
                    pass
            return

        if event == 'flip':
            if isinstance(opp, dict):
                if opp.get('_skipped') or opp.get('family_name') == 'Skip':
                    self.push_conquer_feed(
                        f'{opponent_name} skips round {round_idx + 1}.',
                        (196, 186, 160))
                else:
                    name = self._conquer_lane_move_name(opp)
                    power = self._conquer_lane_move_power(opp)
                    detail = f' ({power})' if power else ''
                    self.push_conquer_feed(
                        f'{opponent_name} reveals {name}{detail}!',
                        (226, 168, 152))
            try:
                sound.play('card_place')
            except Exception:
                pass
            return

        if event == 'impact':
            diff = 0
            try:
                ledger = getattr(self, '_round_ledger', None)
                if ledger is not None:
                    diff = ledger._round_diff(you, opp)
            except Exception:
                diff = 0
            if diff > 0:
                color, text = (130, 220, 190), f'+{diff}'
                feed = f'Round {round_idx + 1} falls to you (+{diff}).'
                snd = 'round_win'
            elif diff < 0:
                color, text = (226, 145, 130), f'\u2212{abs(diff)}'
                feed = f'Round {round_idx + 1} goes to {opponent_name} ({diff}).'
                snd = 'round_loss'
            else:
                color, text = (232, 220, 180), '\u00b10'
                feed = f'Round {round_idx + 1} is dead even.'
                snd = 'card_slide'
            self.push_conquer_feed(feed, color)
            if effects is not None and card_rect is not None:
                # Impact intensity escalates toward the final round; a
                # fast-forwarded (skipped) reveal never jolts the screen.
                try:
                    effects.spawn_rect_pulse(card_rect, color,
                                             duration_ms=520,
                                             scale=0.8 + 0.15 * round_idx)
                    effects.spawn_floating_text_at_rect(
                        card_rect, text, color,
                        duration_ms=820 + 80 * round_idx)
                    if not payload.get('fast_forwarded'):
                        if diff != 0:
                            # Decisive round: particle payoff scaled by the
                            # margin and the battle position (later rounds
                            # hit harder).  Confetti for the battle OUTCOME
                            # is reserved for the result payoff — a won
                            # round is not a won battle.  Own guard so a
                            # burst hiccup never eats the shakes below.
                            try:
                                burst_count = int(min(
                                    28, 8 + abs(diff) * 1.4 + round_idx * 4))
                                if diff > 0:
                                    effects.spawn_burst(
                                        card_rect, (238, 206, 130),
                                        secondary=(150, 230, 170),
                                        count=burst_count,
                                        upward_bias=0.6,
                                        speed=(140.0, 260.0))
                                else:
                                    effects.spawn_burst(
                                        card_rect, (200, 110, 96),
                                        secondary=(120, 96, 88),
                                        count=max(6, burst_count - 6),
                                        upward_bias=0.15,
                                        speed=(90.0, 170.0),
                                        gravity=110.0)
                            except Exception:
                                pass
                        if abs(diff) >= 10:
                            effects.spawn_shake(amplitude=6, duration_ms=240)
                        if round_idx == 2 and diff != 0:
                            effects.spawn_shake(amplitude=4, duration_ms=200)
                except Exception:
                    pass
            try:
                sound.play(snd)
            except Exception:
                pass
            return

        if event == 'done':
            # Final-round resolve beat: once the last reveal lands and the
            # battle is complete, pulse the BATTLE TOTAL circle so the eye
            # travels to the resolution readout before Finish appears.
            game = self.state.game
            if game is None or getattr(game, 'last_battle_result', None):
                return
            sequencer = getattr(self, '_conquer_reveal_sequencer', None)
            if sequencer is not None and sequencer.has_pending():
                return
            try:
                player_slots, opponent_slots = self._conquer_lane_played_tactics_raw()
                all_done = (all(s is not None for s in player_slots)
                            and all(s is not None for s in opponent_slots))
            except Exception:
                all_done = False
            if not all_done:
                return
            ledger = getattr(self, '_round_ledger', None)
            circle = getattr(ledger, '_total_circle_rect', None) if ledger else None
            if effects is not None and circle is not None:
                try:
                    effects.spawn_rect_pulse(pygame.Rect(circle), (238, 206, 130),
                                             duration_ms=760, scale=1.15)
                except Exception:
                    pass
            self.push_conquer_feed('All rounds resolved \u2014 finish the battle!',
                                   (238, 206, 130))
            try:
                sound.play('battle_total')
            except Exception:
                pass

    def _on_conquer_tally_tick(self, shown, diff):
        """Ledger hook: soft tick as the round-diff count-up increments.

        Rate-limited so a fast count-up (big diff over the same tally
        window) coalesces into an even tick train instead of a burr.
        """
        now = pygame.time.get_ticks()
        if now - int(getattr(self, '_conquer_tally_tick_last_ms', 0) or 0) < 45:
            return
        self._conquer_tally_tick_last_ms = now
        from utils import sound
        try:
            sound.play('tally_tick')
        except Exception:
            pass

    # ------------------------------------------------------------ battle feed
    CONQUER_FEED_TTL_MS = 6500
    CONQUER_FEED_MAX = 4

    def push_conquer_feed(self, text, color=(238, 218, 170)):
        """Append a short narration entry to the rolling battle feed."""
        feed = getattr(self, '_conquer_battle_feed', None)
        if feed is None:
            feed = []
            self._conquer_battle_feed = feed
        feed.append({
            'text': str(text or ''),
            'color': tuple(color),
            'added_ms': pygame.time.get_ticks(),
        })
        del feed[:-self.CONQUER_FEED_MAX]

    def _draw_conquer_battle_feed(self):
        """Rolling reveal-narration feed, centred just above the round ledger.

        The pills stack upward from the ledger's top edge, horizontally
        centred over the battlefield — right where the round-card pulses
        fire — so "Round N goes to …" reads as a caption for the ledger
        instead of overlapping the tactics rail on the left.

        Entries fade over their last second. Non-interactive; capped to
        ``CONQUER_FEED_MAX`` compact lines so it never crowds the field.
        """
        feed = getattr(self, '_conquer_battle_feed', None)
        if not feed:
            return
        now = pygame.time.get_ticks()
        live = [entry for entry in feed
                if now - int(entry.get('added_ms') or now) < self.CONQUER_FEED_TTL_MS]
        if len(live) != len(feed):
            self._conquer_battle_feed = live
        if not live:
            return
        try:
            ledger_rect = self._round_ledger.rect()
        except Exception:
            ledger_rect = pygame.Rect(0, settings.SCREEN_HEIGHT - 80,
                                      settings.SCREEN_WIDTH, 80)
        # Centre over the battlefield panel when available (keeps the feed
        # clear of the tactics rail); fall back to the ledger centre.
        try:
            layout = compute_conquer_layout(
                settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT,
                mode=self._conquer_effective_layout_mode())
            anchor_cx = pygame.Rect(layout.battlefield.rect).centerx
        except Exception:
            anchor_cx = ledger_rect.centerx
        font = settings.get_font(max(settings.FS_CONQUER_LABEL, int(settings.FS_TINY * 0.9)), bold=True)
        line_h = font.get_height() + 6
        y = ledger_rect.top - 10 - line_h
        max_w = max(120, int(settings.SCREEN_WIDTH * 0.34))
        for entry in reversed(live):
            age = now - int(entry.get('added_ms') or now)
            remaining = self.CONQUER_FEED_TTL_MS - age
            alpha = 255 if remaining > 1000 else max(0, int(255 * remaining / 1000))
            if alpha <= 0:
                continue
            text = self._fit_text(entry.get('text', ''), font, max_w - 16)
            surf = font.render(text, True, entry.get('color', (238, 218, 170)))
            pill = pygame.Rect(0, y, surf.get_width() + 14, line_h)
            pill.centerx = anchor_cx
            bg = pygame.Surface(pill.size, pygame.SRCALPHA)
            pygame.draw.rect(bg, (20, 16, 12, min(210, alpha)),
                             bg.get_rect(), border_radius=6)
            pygame.draw.rect(bg, (*entry.get('color', (238, 218, 170)),
                                  min(140, alpha)),
                             bg.get_rect(), 1, border_radius=6)
            surf.set_alpha(alpha)
            self.window.blit(bg, pill.topleft)
            self.window.blit(surf, (pill.left + 7,
                                    pill.centery - surf.get_height() // 2))
            y -= line_h + 3

    # ------------------------------------------------------------------ effects
    def _lookup_conquer_figure_rect(self, figure_id):
        """Return the on-screen rect of ``figure_id`` or ``None``.

        Looks first at the duel-lane fighter rects (visible during battle
        rounds), then falls back to the field-screen figure icon cache.
        Used by :class:`ConquerEffectsLayer` to anchor spell animations.
        """
        if figure_id is None:
            return None
        # Synthetic orphan-explosion ids (negative) resolve to remembered rects
        # so the burst can still anchor after the real figure has been removed.
        if isinstance(figure_id, int) and figure_id < 0:
            return self._orphan_explosion_lookup(figure_id)
        # 1. Duel-lane figures (the small icons inside the YOU/OPP bands).
        rects = getattr(self, '_conquer_lane_figure_rects', None) or []
        for info in rects:
            fig = info.get('figure') if isinstance(info, dict) else None
            if fig is not None and getattr(fig, 'id', None) == figure_id:
                rect = info.get('rect')
                if rect is not None:
                    return pygame.Rect(rect)
        # 2. Field figure icons (visible when the field tab is open).
        field = self.subscreens.get('field') if hasattr(self, 'subscreens') else None
        if field is not None:
            icon = (getattr(field, 'icon_cache', None) or {}).get(figure_id)
            if icon is None:
                for candidate in getattr(field, 'figure_icons', None) or []:
                    if getattr(getattr(candidate, 'figure', None), 'id', None) == figure_id:
                        icon = candidate
                        break
            if icon is not None:
                # FigureIcon exposes rect_frame for the unselected state.
                rect = getattr(icon, 'rect_frame', None) or getattr(icon, 'rect_icon', None)
                if rect is not None:
                    return pygame.Rect(rect)
                x = getattr(icon, 'x', None)
                y = getattr(icon, 'y', None)
                if x is not None and y is not None:
                    return pygame.Rect(int(x) - 24, int(y) - 24, 48, 48)
        ghost_rect = self._spell_target_ghost_lookup(figure_id)
        if ghost_rect is not None:
            return ghost_rect
        return None

    def _conquer_timeline_anchor_rect(self):
        """Return a sensible projectile source rect (the active timeline bubble
        or the top header strip)."""
        panel = getattr(self, '_conquer_timeline_panel', None)
        if panel is not None:
            anchor = getattr(panel, '_active_step_rect', None)
            if anchor is not None:
                try:
                    return pygame.Rect(anchor)
                except Exception:
                    pass
        header = getattr(self, '_conquer_collapsed_header_rect', None)
        if header is not None:
            try:
                rect = pygame.Rect(header)
                return pygame.Rect(rect.centerx - 24, rect.centery - 18, 48, 36)
            except Exception:
                pass
        return None

    @staticmethod
    def _spell_step_replay_key(step):
        key = getattr(step, 'replay_key', None)
        if key is not None:
            return key
        kind = getattr(step, 'kind', '')
        payload = getattr(step, 'icon_payload', None)
        owner = getattr(step, 'owner', '') or ''
        return (kind, payload, owner)

    @staticmethod
    def _spell_step_phase(step):
        if getattr(step, 'active', False):
            return 'active'
        if getattr(step, 'completed', False):
            return 'completed'
        return 'pending'

    def _pump_conquer_spell_animations(self):
        """Trigger spell animations driven by timeline step transitions.

        The conquer timeline panel is the narrative source of truth: each
        prelude / counter step that carries a spell payload becomes
        ``active`` while the user is watching its bubble, then flips to
        ``completed``.  We mirror that progression — animations fire only
        when a spell step's phase transitions *during this session* from
        a not-yet-seen state to ``active`` (or directly to ``completed``
        when the user pre-empts the auto-advance).

        On the first frame after entering the screen / switching games we
        snapshot every step's current phase as the baseline so spells
        that already played in earlier sessions or that completed before
        the screen mounted do not replay as ghost casts.
        """
        effects = getattr(self, '_conquer_effects', None)
        if effects is None:
            return
        game = getattr(self.state, 'game', None)
        if game is None:
            return
        panel = getattr(self, '_conquer_timeline_panel', None)
        if panel is None:
            return

        # Reset animation tracking when the active game changes so a
        # subsequent game's history does not animate on entry.
        game_key = (getattr(game, 'game_id', None),
                    getattr(game, 'player_id', None))
        if getattr(self, '_spell_anim_game_key', None) != game_key:
            self._spell_anim_game_key = game_key
            self._spell_step_phase_map = {}
            self._spell_anim_seeded = False
            self._spell_anim_fired = set()
            self._spell_anim_target_fired = set()
            self._spell_sound_fired = set()
            self._conquer_spell_anim_impact_ms = {}
            self._last_announced_battle_round = 0
            self._prev_visible_figure_rects = {}
            self._last_seen_figure_rects = {}
            self._field_explosion_ghost_hold_until = {}
            # Effects from a stale game should not bleed into the new one.
            try:
                effects.clear()
            except Exception:
                pass

        try:
            steps = panel.derive_display_steps(self) or []
        except Exception:
            steps = []

        # Build the current phase map for spell-bearing timeline steps.
        current_phase = {}
        current_step_info = {}
        for step in steps:
            kind = getattr(step, 'kind', '')
            if kind not in ('prelude_own', 'prelude_opp', 'counter'):
                continue
            payload = getattr(step, 'icon_payload', None)
            if not isinstance(payload, str) or not payload:
                continue
            key = self._spell_step_replay_key(step)
            current_phase[key] = self._spell_step_phase(step)
            current_step_info[key] = (kind, payload)

        self._refresh_spell_target_ghosts(steps, current_phase)

        # Track latest known rect per figure so we can anchor an Explosion
        # burst even if the figure has just disappeared.
        for info in (getattr(self, '_conquer_lane_figure_rects', None) or []):
            fig = info.get('figure') if isinstance(info, dict) else None
            fid = getattr(fig, 'id', None)
            rect = info.get('rect') if isinstance(info, dict) else None
            if fid is not None and rect is not None:
                self._last_seen_figure_rects[fid] = pygame.Rect(rect)

        prev_phase = getattr(self, '_spell_step_phase_map', None) or {}
        fired_steps = getattr(self, '_spell_anim_fired', None)
        if fired_steps is None:
            fired_steps = set()
            self._spell_anim_fired = fired_steps

        if not getattr(self, '_spell_anim_seeded', False):
            # First-frame seed: record current phases, but if the timeline
            # is already holding a spell as active, play it immediately so
            # the visible active bubble and animation stay in sync.
            anchor = self._conquer_timeline_anchor_rect()
            for key, phase in current_phase.items():
                if phase == 'active' and key not in fired_steps:
                    step_kind, spell_name = current_step_info.get(key, (None, None))
                    if self._fire_spell_step_animation(
                            key, anchor, step_kind=step_kind, spell_name=spell_name):
                        fired_steps.add(key)
            # Card-effect spells that already completed before the screen
            # mounted get no replay animation — mark their tactics-rail
            # mutation as landed immediately so it stays revealed.
            for key, phase in current_phase.items():
                if (phase in ('active', 'completed')
                        and key not in self._conquer_spell_anim_impact_ms):
                    s_kind, s_name = current_step_info.get(key, (None, None))
                    s_info = self._resolve_spell_step_info(s_kind, s_name)
                    if self._is_conquer_card_effect_spell(s_name, s_info):
                        self._conquer_spell_anim_impact_ms[key] = 0
                        fired_steps.add(key)
            self._spell_step_phase_map = dict(current_phase)
            self._spell_anim_seeded = True
        else:
            anchor = self._conquer_timeline_anchor_rect()
            for key, phase in current_phase.items():
                old = prev_phase.get(key, 'pending')
                step_kind, spell_name = current_step_info.get(key, (None, None))
                # Fire when a spell step first becomes active in this
                # session, or transitions straight from pending to
                # completed (happens if the user clicks "Next" quickly).
                if (old == 'pending'
                        and phase in ('active', 'completed')
                        and key not in fired_steps):
                    if self._fire_spell_step_animation(
                            key, anchor, step_kind=step_kind, spell_name=spell_name):
                        fired_steps.add(key)
                        self._play_conquer_spell_cast_sound(key)
                elif (phase in ('active', 'completed')
                      and key not in getattr(self, '_spell_anim_target_fired', set())):
                    # A prior fire on this step was banner-only because
                    # the target was still unresolved (pending-target
                    # prelude like Health Boost).  Re-fire now that the
                    # target id is known so the real animation plays.
                    spell_info = self._resolve_spell_step_info(step_kind, spell_name)
                    if self._prelude_spell_target_id(spell_info) is not None:
                        if self._fire_spell_step_animation(
                                key, anchor, step_kind=step_kind, spell_name=spell_name):
                            fired_steps.add(key)
                            # Targeted spells (Health Boost / Poison / Explosion)
                            # only fire for real here, once their target is
                            # known — the first pass was a banner-only no-op.
                            self._play_conquer_spell_cast_sound(key)
            self._spell_step_phase_map = dict(current_phase)

        # --- Round transition banner (Tier 3.3) ---
        # ``battle_round`` is zero-indexed on the server (0..2), so the
        # banner label is round + 1; the last round gets its own callout.
        # The banner is deferred while a round-reveal sequence is pending
        # so "Round N" never announces on top of the previous round's
        # reveal choreography.
        battle_round = int(getattr(game, 'battle_round', 0) or 0)
        confirmed = bool(getattr(game, 'battle_confirmed', False))
        sequencer = getattr(self, '_conquer_reveal_sequencer', None)
        reveal_busy = bool(sequencer is not None and sequencer.has_pending())
        if (confirmed and battle_round in (1, 2, 3) and not reveal_busy
                and battle_round != self._last_announced_battle_round):
            if self._last_announced_battle_round != 0:
                # Only banner subsequent rounds, not the initial seed.
                label = self._conquer_round_banner_label(battle_round)
                color = ((255, 170, 96) if label == 'Final Round'
                         else (255, 211, 116))
                duration_ms = 900
                if label == 'Final Round':
                    # Stakes callout when the battle is still genuinely
                    # undecided — the total sits inside one Double-Dagger
                    # swing. The ledger pulses round 3's border in step.
                    self._final_round_contested = (
                        self._is_conquer_final_round_contested())
                    if self._final_round_contested:
                        label = 'Final Round — all hangs on this'
                        duration_ms = 1200
                        self.push_conquer_feed(
                            'Everything rides on the final round!',
                            (255, 170, 96))
                        try:
                            from utils import sound
                            sound.play('battle_start', volume=0.5)
                        except Exception:
                            pass
                effects.spawn_banner(label, color, duration_ms=duration_ms)
                self._round_transition_until_ms = pygame.time.get_ticks() + 500
            self._last_announced_battle_round = battle_round
        elif not confirmed:
            self._last_announced_battle_round = 0
            self._final_round_contested = False

    def _play_conquer_spell_cast_sound(self, step_key):
        """Play the spell-cast sparkle once per spell step that fires live
        (prelude / counter / tactic spell animating during the battle)."""
        fired = getattr(self, '_spell_sound_fired', None)
        if fired is None:
            fired = set()
            self._spell_sound_fired = fired
        if step_key in fired:
            return
        fired.add(step_key)
        from utils import sound
        try:
            kind, spell_name = step_key[:2]
        except Exception:
            kind, spell_name = '', None
        sound.play_spell(spell_name,
                         counter='counter' in str(kind).lower())

    def _fire_spell_step_animation(self, step_key, anchor_rect, *,
                                   step_kind=None, spell_name=None):
        """Spawn the appropriate effect for a transitioned spell step."""
        kind = step_kind
        if spell_name is None:
            try:
                kind, spell_name, _owner = step_key
            except Exception:
                return False
        if kind is None:
            try:
                kind = step_key[0]
            except Exception:
                kind = ''
        if not spell_name:
            return False
        spell_info = self._resolve_spell_step_info(kind, spell_name)
        if spell_name == 'Royal Decree':
            # Battle modifier AND card effect: crown banner + castle-lane
            # pulse, then redraw projectiles to both players' hands.
            self._spawn_conquer_modifier_spell_animation(spell_name, anchor_rect)
            impact_ms = self._spawn_conquer_card_spell_animation(
                spell_name, anchor_rect, spell_info, step_kind=kind)
            if impact_ms is not None:
                self._conquer_spell_anim_impact_ms[step_key] = int(impact_ms)
            return True
        if spell_name == 'Copy Figure':
            # Mirror the Poison/Health-Boost once-only contract: the update
            # loop re-fires targeted spells whose first fire happened before
            # the target was chosen (banner-only). Register the step as
            # target-fired exactly when a resolved target/copy is known —
            # earlier fires stay banner-only and may be upgraded once;
            # marking unconditionally would suppress the real ghost-flight,
            # never marking would re-fire it every frame and stall the game.
            effect_data = self._spell_effect_data(spell_info)
            target_known = (
                effect_data.get('copied_figure_id') is not None
                or effect_data.get('source_figure_id') is not None
                or self._prelude_spell_target_id(spell_info) is not None
            )
            if target_known:
                fired_set = getattr(self, '_spell_anim_target_fired', None)
                if fired_set is None:
                    fired_set = set()
                    self._spell_anim_target_fired = fired_set
                fired_set.add(step_key)
            return self._spawn_conquer_copy_figure_animation(
                spell_name, anchor_rect, spell_info)
        if spell_name == 'All Seeing Eye':
            # Eye sweep toward the hidden opponent hand/tactics strip.
            effects = getattr(self, '_conquer_effects', None)
            if effects is None:
                return False
            opp_strip = self._conquer_opponent_hand_target_rect()
            spawn_to_rect = getattr(effects, 'spawn_spell_to_rect', None)
            if opp_strip is not None and callable(spawn_to_rect):
                spawn_to_rect(spell_name, anchor_rect, opp_strip,
                              floating_text='revealed')
            else:
                spawn_banner = getattr(effects, 'spawn_banner', None)
                if callable(spawn_banner):
                    spawn_banner(spell_name, (130, 190, 255), duration_ms=900)
            return True
        if self._is_conquer_card_effect_spell(spell_name, spell_info):
            impact_ms = self._spawn_conquer_card_spell_animation(
                spell_name, anchor_rect, spell_info, step_kind=kind)
            if impact_ms is not None:
                self._conquer_spell_anim_impact_ms[step_key] = int(impact_ms)
            return True
        if self._is_conquer_battle_modifier_spell(spell_name, spell_info):
            self._spawn_conquer_modifier_spell_animation(spell_name, anchor_rect)
            return True
        if spell_name not in ('Poison', 'Health Boost', 'Explosion'):
            return False
        target_id = self._prelude_spell_target_id(spell_info)
        fired_set = getattr(self, '_spell_anim_target_fired', None)
        if fired_set is None:
            fired_set = set()
            self._spell_anim_target_fired = fired_set
        if target_id is not None:
            fired_set.add(step_key)
        target_rect = self._lookup_conquer_figure_rect(target_id) if target_id else None
        # Fallback: figure may already be gone (Explosion) — use last-seen rect.
        if target_rect is None and target_id is not None:
            target_rect = (getattr(self, '_last_seen_figure_rects', None) or {}).get(target_id)
        if target_rect is None and target_id is not None and self._prelude_spell_target_snapshot(spell_info):
            target_rect = self._ensure_spell_target_ghost(
                spell_info, target_id, kind, duration_ms=1800,
                draw=(spell_name != 'Explosion'))
        effects = self._conquer_effects
        if spell_name == 'Explosion':
            if target_rect is not None and target_id is not None and self._lookup_conquer_figure_rect(target_id) is None:
                # Figure no longer rendered; spawn an orphan burst at the
                # remembered rect rather than skipping the animation.
                self._spawn_orphan_explosion(target_rect, anchor_rect)
            elif target_id is not None:
                effects.spawn_explosion(anchor_rect, target_id)
            else:
                # No target known — just flash the banner so the user notices.
                effects.spawn_banner('Explosion', (255, 168, 56), duration_ms=900)
                return False
            return True
        # Poison / Health Boost
        if target_id is None:
            effects.spawn_banner(spell_name,
                                 (148, 76, 196) if spell_name == 'Poison' else (110, 220, 140),
                                 duration_ms=900)
            return False
        ftext = '-6 power' if spell_name == 'Poison' else '+ Health'
        # If the figure isn't currently rendered, fall back to orphan rect anim.
        if self._lookup_conquer_figure_rect(target_id) is None and target_rect is not None:
            synthetic = self._register_orphan_rect(target_rect)
            effects.spawn_spell_cast(spell_name, anchor_rect, synthetic,
                                     floating_text=ftext)
        else:
            effects.spawn_spell_cast(spell_name, anchor_rect, target_id,
                                     floating_text=ftext)
        return True

    @staticmethod
    def _spell_effect_data(spell_info):
        if not isinstance(spell_info, dict):
            return {}
        data = spell_info.get('effect_data')
        return data if isinstance(data, dict) else {}

    def _is_conquer_card_effect_spell(self, spell_name, spell_info=None):
        if spell_name in self.CONQUER_CARD_EFFECT_SPELLS:
            return True
        effect_data = self._spell_effect_data(spell_info)
        return any(key in effect_data for key in self.CONQUER_CARD_EFFECT_KEYS)

    def _is_conquer_battle_modifier_spell(self, spell_name, spell_info=None):
        if self._is_battle_modifier_spell(spell_name):
            return True
        effect_data = self._spell_effect_data(spell_info)
        return bool(
            effect_data.get('battle_modifier_added')
            or effect_data.get('battle_modifier_origin')
        )

    def _conquer_tactics_rail_target_rect(self):
        rail = getattr(self, '_tactics_rail', None)
        if rail is not None:
            for attr in ('_dyn_hand_list_rect', '_dyn_top_strip_rect'):
                rect = getattr(rail, attr, None)
                if rect is not None:
                    try:
                        return pygame.Rect(rect)
                    except Exception:
                        pass
            rect_fn = getattr(rail, 'rect', None)
            if callable(rect_fn):
                try:
                    return pygame.Rect(rect_fn())
                except Exception:
                    pass
        try:
            layout = compute_conquer_layout(
                settings.SCREEN_WIDTH,
                settings.SCREEN_HEIGHT,
                mode=self._conquer_effective_layout_mode(),
            )
            return pygame.Rect(*layout.tactics_rail.rect)
        except Exception:
            return None

    def _conquer_duel_lane_target_rect(self):
        rect = getattr(self, '_conquer_duel_lane_last_rect', None)
        if rect is not None:
            try:
                return pygame.Rect(rect)
            except Exception:
                pass
        try:
            layout = compute_conquer_layout(
                settings.SCREEN_WIDTH,
                settings.SCREEN_HEIGHT,
                mode=self._conquer_effective_layout_mode(),
            )
            return pygame.Rect(layout.battlefield.duel_lane.rect)
        except Exception:
            return None

    def _conquer_onboarding(self):
        ud = getattr(self.state, 'user_dict', None) or {}
        onboarding = ud.get('onboarding')
        return onboarding if isinstance(onboarding, dict) else None

    def _conquer_menu_coach_seen(self):
        onboarding = self._conquer_onboarding()
        return set(onboarding.get('menu_hints_seen') or []) if onboarding else set()

    def _conquer_completed_onboarding_steps(self):
        onboarding = self._conquer_onboarding()
        return set(onboarding.get('completed_steps') or []) if onboarding else set()

    def _conquer_battle_coach_allowed(self):
        onboarding = self._conquer_onboarding()
        if not onboarding:
            return False
        if onboarding.get('onboarding_skipped'):
            return False
        # The teaching window is modal; suppress anchored coach cards under it.
        if getattr(self, '_battle_intro_dialogue', None) is not None:
            return False
        if 'finish_first_conquer_battle' in self._conquer_completed_onboarding_steps():
            return False
        game = getattr(self.state, 'game', None)
        if not game or getattr(game, 'mode', None) != 'conquer':
            return False
        if not self._is_tactics_hand_game():
            return False
        if getattr(self, 'dialogue_box', None) is not None:
            return False
        if getattr(self, '_withdraw_dialogue_open', False):
            return False
        if getattr(self, 'waiting_for_counter_response', False):
            return False
        if getattr(self, 'need_to_respond_to_spell', False):
            return False
        if getattr(self, 'counter_spell_selector', None) is not None:
            return False
        subscreen = None
        if hasattr(self, 'subscreens'):
            subscreen = self.subscreens.get(getattr(self.state, 'subscreen', None))
        if getattr(subscreen, 'dialogue_box', None) is not None:
            return False
        return True

    def _mark_conquer_battle_coach_seen(self, step_id):
        if not step_id:
            return
        try:
            data = onboarding_service.mark_tip(f'menu:{step_id}')
            onboarding = data.get('onboarding') if isinstance(data, dict) else None
            if onboarding is not None and getattr(self.state, 'user_dict', None) is not None:
                self.state.user_dict['onboarding'] = onboarding
            return
        except Exception as exc:
            logger.debug('Failed to persist conquer battle coach hint %s: %s', step_id, exc)
        ud = getattr(self.state, 'user_dict', None)
        if not ud:
            return
        onboarding = dict(ud.get('onboarding') or {})
        seen = list(onboarding.get('menu_hints_seen') or [])
        if step_id not in seen:
            seen.append(step_id)
        onboarding['menu_hints_seen'] = seen
        ud['onboarding'] = onboarding

    # ── First-battle teaching window (replaces the dense battle coach cards) ──
    def _maybe_show_battle_intro_window(self):
        if getattr(self, '_battle_intro_dialogue', None) is not None:
            return
        if 'battle_intro_window' in self._conquer_menu_coach_seen():
            return
        if not self._conquer_battle_coach_allowed():
            return
        # Show the intro as the FIRST thing on the first conquer tutorial battle
        # — on entering the screen, before any setup/tactics coaching — rather
        # than waiting for a battle round to be active.
        from game.components.tutorial_window import TutorialWindowDialogue
        from game.tutorial_content import conquer_battle_intro_pages
        self._battle_intro_dialogue = TutorialWindowDialogue(
            self.window,
            conquer_battle_intro_pages(),
            title='How Battles Work',
        )

    def _handle_battle_intro_window_events(self, events):
        win = getattr(self, '_battle_intro_dialogue', None)
        if win is None:
            return False
        if any(getattr(e, 'type', None) == QUIT for e in events):
            return False
        if win.update(events) == 'done':
            self._battle_intro_dialogue = None
            self._mark_conquer_battle_coach_seen('battle_intro_window')
            # The modal held the overview step in place. Release that duplicate
            # beat immediately so the prepared pre-battle sequence starts now.
            self._advance_active_timeline_step()
        return True

    @staticmethod
    def _conquer_battle_coach_bounds(rects):
        usable = [pygame.Rect(rect) for rect in rects if rect]
        if not usable:
            return None
        bounds = usable[0].copy()
        for rect in usable[1:]:
            bounds.union_ip(rect)
        return bounds

    def _conquer_battle_coach_target_rects(self, step):
        if not step:
            return []
        if step.get('rects'):
            return [pygame.Rect(rect) for rect in step.get('rects') if rect]
        if step.get('rect'):
            return [pygame.Rect(step['rect'])]
        return []

    def _conquer_battle_timeline_target_rects(self):
        for attr in ('_conquer_timeline_info_rect', '_conquer_collapsed_header_rect'):
            rect = getattr(self, attr, None)
            if rect is not None:
                return [pygame.Rect(rect)]
        try:
            return [pygame.Rect(self._conquer_timeline_overlay_rect())]
        except Exception:
            return []

    def _conquer_battle_prelude_target_rects(self):
        active_step = self.active_conquer_timeline_step()
        if active_step is None or getattr(active_step, 'kind', '') not in (
                'prelude_own', 'prelude_opp', 'counter'):
            return []
        return self._conquer_battle_timeline_target_rects()

    def _conquer_battle_field_target_rects(self):
        active_step = self.active_conquer_timeline_step()
        field_actions = {
            'confirm',
            'confirm_figure',
            'select_target',
            'select_advance',
            'select_second',
            'select_defender',
            'select_own_defender',
        }
        primary_action = getattr(active_step, 'primary_action', None)
        if primary_action not in field_actions:
            return []
        rects = []
        lane_rect = self._conquer_duel_lane_target_rect()
        if lane_rect is not None:
            rects.append(pygame.Rect(lane_rect))
        confirm_rect = (getattr(self, '_conquer_objective_action_rects', {}) or {}).get('confirm')
        if confirm_rect is not None:
            rects.append(pygame.Rect(confirm_rect))
        return rects

    def _conquer_battle_field_overview_rects(self):
        lane_rect = self._conquer_duel_lane_target_rect()
        if lane_rect is not None:
            return [pygame.Rect(lane_rect)]
        try:
            layout = compute_conquer_layout(
                settings.SCREEN_WIDTH,
                settings.SCREEN_HEIGHT,
                mode=self._conquer_effective_layout_mode(),
            )
            return [pygame.Rect(layout.battlefield.rect)]
        except Exception:
            return []

    def _conquer_battle_tactics_target_rects(self):
        rect = self._conquer_tactics_rail_target_rect()
        return [pygame.Rect(rect)] if rect is not None else []

    def _conquer_battle_tactic_action_rects(self):
        rail = getattr(self, '_tactics_rail', None)
        button_rects = []
        for rect in (getattr(rail, '_action_button_rects', {}) or {}).values():
            if rect is not None:
                button_rects.append(pygame.Rect(rect))
        if not button_rects:
            return []
        rects = []
        hand_rect = getattr(rail, '_dyn_hand_list_rect', None)
        if hand_rect is not None:
            rects.append(pygame.Rect(hand_rect))
        rects.extend(button_rects)
        return rects

    def _conquer_battle_round_ledger_rects(self):
        ledger = getattr(self, '_round_ledger', None)
        rect_fn = getattr(ledger, 'rect', None)
        if callable(rect_fn):
            try:
                return [pygame.Rect(rect_fn())]
            except Exception:
                return []
        return []

    def _conquer_battle_finish_rects(self):
        try:
            if not self._conquer_finish_available():
                return []
        except Exception:
            return []
        rect = (getattr(self, '_conquer_objective_action_rects', {}) or {}).get('finish')
        return [pygame.Rect(rect)] if rect is not None else []

    @staticmethod
    def _conquer_battle_intro_step_ids():
        # The concepts are taught up front by the 'How Battles Work' window; keep
        # only a tiny action pointer so the tutorial does not keep interrupting.
        return (
            'conquer_battle_tactics',
        )

    def _conquer_battle_intro_fallback_rects(self):
        rects = self._conquer_battle_timeline_target_rects()
        if rects:
            return rects
        return [pygame.Rect(
            int(settings.SCREEN_WIDTH * 0.34),
            int(settings.SCREEN_HEIGHT * 0.18),
            int(settings.SCREEN_WIDTH * 0.32),
            max(48, int(settings.SCREEN_HEIGHT * 0.08)),
        )]

    def _current_conquer_battle_intro_step(self, seen=None):
        seen = set(seen or self._conquer_menu_coach_seen())
        for step_id in self._conquer_battle_intro_step_ids():
            if step_id in seen:
                continue
            if step_id == 'conquer_battle_tactics':
                if not self._conquer_tactics_coach_ready():
                    return None
                rects = (self._conquer_battle_tactic_action_rects()
                         or []) + (self._conquer_battle_tactics_target_rects() or [])
                rects = rects or self._conquer_battle_intro_fallback_rects()
                return {
                    'id': step_id,
                    'rect': rects[0],
                    'rects': rects,
                    'title': 'Choose A Tactic',
                    'body': 'Pick one prepared tactic each round. Play it, or Gamble it for two replacements.',
                    'action': 'next',
                    'button_label': 'Choose a tactic',
                    'max_lines': 4,
                }
        return None

    def _conquer_tactics_coach_ready(self):
        """Wait for the complete battle-start reveal before coaching tactics."""
        game = getattr(self.state, 'game', None)
        if not game or getattr(game, 'last_battle_result', None):
            return False
        try:
            if not self._is_battle_phase_active():
                return False
            if self._conquer_clash_diff_hidden():
                return False
        except Exception:
            return False
        # These rects are populated only after the fighters have actually been
        # drawn into the duel lane; two entries cover the normal one-v-one case.
        if len(getattr(self, '_conquer_lane_figure_rects', None) or []) < 2:
            return False
        return bool(
            self._conquer_battle_tactic_action_rects()
            or self._conquer_battle_tactics_target_rects()
        )

    def _conquer_battle_intro_paused(self):
        # Only the modal explainer pauses the prepared pre-battle sequence. The
        # tactics card is delayed until battle is already live.
        return getattr(self, '_battle_intro_dialogue', None) is not None

    def _current_conquer_battle_coach_step(self):
        if not self._conquer_battle_coach_allowed():
            return None
        return self._current_conquer_battle_intro_step(self._conquer_menu_coach_seen())

    def _wrap_conquer_battle_coach_lines(self, text, max_width, max_lines=5):
        words = str(text or '').split()
        lines = []
        current = ''
        for word in words:
            candidate = word if not current else f'{current} {word}'
            if self._conquer_battle_coach_font.size(candidate)[0] <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines[:max_lines]

    def _draw_conquer_battle_coach_button(self, rect, label, action, muted=False):
        draw_coach_button(
            self.window, rect, label, self._conquer_battle_coach_font,
            muted=muted)
        self._conquer_battle_coach_buttons.append((rect.copy(), action))

    def _draw_conquer_battle_coach(self):
        step = self._current_conquer_battle_coach_step()
        self._conquer_battle_coach_buttons = []
        self._conquer_battle_coach_step = step
        if not step:
            return
        target_rects = self._conquer_battle_coach_target_rects(step)
        target = self._conquer_battle_coach_bounds(target_rects)
        if target is None:
            return
        draws_next = step.get('action', 'next') == 'next'
        draws_skip = not (self._conquer_onboarding() or {}).get('onboarding_skipped')
        card, button_h = draw_coach_panel(
            self.window,
            target_rects,
            title=step['title'],
            body=step['body'],
            title_font=self._conquer_battle_coach_title_font,
            body_font=self._conquer_battle_coach_font,
            ticks=pygame.time.get_ticks(),
            width_ratio=0.34,
            min_width=330,
            max_width=420,
            min_height=152,
            max_lines=step.get('max_lines', 5),
            has_button_row=draws_next or draws_skip,
        )
        if card is None:
            return

        if draws_next:
            button_label = step.get('button_label') or 'Next'
            button_w = max(76, self._conquer_battle_coach_font.size(button_label)[0] + 28)
            next_rect = pygame.Rect(card.right - button_w - 14,
                                    card.bottom - button_h - 12,
                                    button_w, button_h)
            self._draw_conquer_battle_coach_button(next_rect, button_label, ('next', step['id']))
        if draws_skip:
            skip_label = 'Pause guidance'
            skip_w = max(96, self._conquer_battle_coach_font.size(skip_label)[0] + 20)
            skip_rect = pygame.Rect(card.x + 14, card.bottom - button_h - 12,
                                    skip_w, button_h)
            self._draw_conquer_battle_coach_button(
                skip_rect, skip_label, ('skip_tutorial', step['id']), muted=True)

    @staticmethod
    def _conquer_battle_coach_blocking_event_types():
        event_types = {MOUSEBUTTONDOWN, MOUSEBUTTONUP, MOUSEWHEEL, KEYDOWN, KEYUP}
        text_input = getattr(pygame, 'TEXTINPUT', None)
        if text_input is not None:
            event_types.add(text_input)
        return event_types

    def _handle_conquer_battle_coach_events(self, events):
        step = getattr(self, '_conquer_battle_coach_step', None)
        if step is None:
            step = self._current_conquer_battle_coach_step()
            self._conquer_battle_coach_step = step
        if not step:
            return False
        action = step.get('action', 'next')
        target_rects = self._conquer_battle_coach_target_rects(step)
        block_types = self._conquer_battle_coach_blocking_event_types()
        for event in events:
            if event.type == QUIT:
                continue
            if event.type not in block_types:
                continue
            if event.type == MOUSEBUTTONDOWN and getattr(event, 'button', 0) == 1:
                pos = getattr(event, 'pos', pygame.mouse.get_pos())
                self._conquer_battle_coach_pressed_button_action = None
                for rect, button_action in list(self._conquer_battle_coach_buttons):
                    if rect.collidepoint(pos):
                        self._conquer_battle_coach_pressed_button_action = button_action
                        return True
                if action != 'click':
                    return True
                if any(rect.collidepoint(pos) for rect in target_rects):
                    continue
                return True
            if event.type == MOUSEBUTTONUP and getattr(event, 'button', 0) == 1:
                pos = getattr(event, 'pos', pygame.mouse.get_pos())
                pressed_action = getattr(self, '_conquer_battle_coach_pressed_button_action', None)
                self._conquer_battle_coach_pressed_button_action = None
                for rect, button_action in list(self._conquer_battle_coach_buttons):
                    if not rect.collidepoint(pos):
                        continue
                    if pressed_action and pressed_action != button_action:
                        return True
                    kind, step_id = button_action
                    from utils import sound
                    sound.play('ui_back' if kind == 'skip_tutorial' else 'ui_click')
                    if kind == 'next':
                        self._mark_conquer_battle_coach_seen(step_id)
                    elif kind == 'skip_tutorial':
                        self._pause_onboarding_tutorial()
                        self._conquer_battle_coach_pressed_button_action = None
                    return True
                if action == 'click':
                    if any(rect.collidepoint(pos) for rect in target_rects):
                        self._mark_conquer_battle_coach_seen(step.get('id'))
                        continue
                    return True
                return True
            return True
        return False

    def _card_spell_floating_text(self, spell_name, spell_info=None):
        effect_data = self._spell_effect_data(spell_info)
        if spell_name in ('Draw 2 MainCards', 'Draw 2 SideCards',
                          'Draw 4 MainCards', 'Fill up to 10'):
            count = effect_data.get('cards_drawn')
            if count is None:
                cards = effect_data.get('drawn_cards')
                count = len(cards) if isinstance(cards, list) else None
            if count is None and spell_name == 'Draw 4 MainCards':
                count = 4
            return f'+{count} cards' if count else '+cards'
        if spell_name == 'Forced Deal':
            return 'swap'
        if spell_name in ('Dump Cards', 'Royal Decree'):
            return 'redraw'
        return 'cards'

    # Card-effect spells that mutate BOTH players' hands, so the animation flies
    # to both the player's tactics rail and the opponent's hand strip. Every
    # other card-effect spell is single-player and flies only to the caster.
    _BOTH_PLAYER_CARD_SPELLS = frozenset({'Dump Cards', 'Forced Deal',
                                          'Royal Decree'})

    def _conquer_card_spell_target_rects(self, spell_name, step_kind):
        """Destination rect(s) for a card-effect spell's projectile.

        Both-player spells (Dump Cards / Forced Deal) hit both hands; single
        spells (Draw 2 / Fill up to 10) hit only the caster's hand — the player
        tactics rail for own preludes, the opponent hand strip for opponent
        preludes.
        """
        player_rail = self._conquer_tactics_rail_target_rect()
        opp_strip = self._conquer_opponent_hand_target_rect()
        if spell_name in self._BOTH_PLAYER_CARD_SPELLS:
            return [r for r in (player_rail, opp_strip) if r is not None]
        cast_by_opponent = (step_kind == 'prelude_opp')
        target = opp_strip if cast_by_opponent else player_rail
        return [target] if target is not None else []

    def _spawn_conquer_card_spell_animation(self, spell_name, anchor_rect,
                                            spell_info=None, step_kind=None):
        """Spawn the card-effect spell animation aimed at the affected hand(s).

        Returns the ms timestamp at which the animation reaches its target —
        callers gate the spell's resolution-step mutation on this so the effect
        appears exactly when the projectile lands.  Banner-only fallbacks (no
        target rect / no projectile helper) return ``now`` so the reveal is not
        stalled.
        """
        now = pygame.time.get_ticks()
        effects = getattr(self, '_conquer_effects', None)
        if effects is None:
            return now
        targets = self._conquer_card_spell_target_rects(spell_name, step_kind)
        if not targets:
            spawn_banner = getattr(effects, 'spawn_banner', None)
            if callable(spawn_banner):
                spawn_banner(spell_name, (80, 185, 230), duration_ms=900)
            return now
        floating_text = self._card_spell_floating_text(spell_name, spell_info)
        spawn_to_rect = getattr(effects, 'spawn_spell_to_rect', None)
        if callable(spawn_to_rect):
            for target_rect in targets:
                spawn_to_rect(spell_name, anchor_rect, target_rect,
                              floating_text=floating_text)
            projectile_ms = int(getattr(effects, 'PROJECTILE_MS', 420) or 0)
            return now + projectile_ms
        spawn_banner = getattr(effects, 'spawn_banner', None)
        if callable(spawn_banner):
            for target_rect in targets:
                spawn_banner(spell_name, (80, 185, 230), duration_ms=900,
                             anchor_rect=target_rect)
        return now

    def _spawn_conquer_modifier_spell_animation(self, spell_name, anchor_rect=None):
        effects = getattr(self, '_conquer_effects', None)
        if effects is None:
            return
        from game.components.conquer_effects import spell_preset
        target_rect = self._conquer_duel_lane_target_rect()
        if spell_name in ('Royal Decree', 'Landslide'):
            color, _secondary, _label = spell_preset(spell_name)
        else:
            color = (255, 196, 86) if spell_name == 'Blitzkrieg' else (214, 178, 92)
        spawn_banner = getattr(effects, 'spawn_banner', None)
        if callable(spawn_banner):
            spawn_banner(spell_name, color, duration_ms=1100,
                         anchor_rect=anchor_rect or target_rect)
        spawn_pulse = getattr(effects, 'spawn_rect_pulse', None)
        if callable(spawn_pulse):
            spawn_pulse(target_rect, color, secondary=(255, 240, 170),
                        duration_ms=820, scale=0.9)
        spawn_float = getattr(effects, 'spawn_floating_text_at_rect', None)
        if spell_name == 'Royal Decree' and callable(spawn_float):
            spawn_float(target_rect, 'castle only', color, delay_ms=350)
        elif spell_name == 'Landslide':
            # Rock-fall feel: short shake + inverted-bonus callout.
            spawn_shake = getattr(effects, 'spawn_shake', None)
            if callable(spawn_shake):
                spawn_shake(amplitude=5, duration_ms=260)
            if callable(spawn_float):
                spawn_float(target_rect, 'land bonus inverted', color, delay_ms=350)

    def _spawn_conquer_copy_figure_animation(self, spell_name, anchor_rect,
                                             spell_info=None):
        """Copy Figure: spinning ghost-orbs bloom on the source then spiral
        onto the copied figure and land — a single lively one-shot."""
        effects = getattr(self, '_conquer_effects', None)
        if effects is None:
            return False
        effect_data = self._spell_effect_data(spell_info)
        source_id = effect_data.get('source_figure_id')
        copied_id = effect_data.get('copied_figure_id')
        source_rect = self._lookup_conquer_figure_rect(source_id) if source_id else None
        copied_rect = self._lookup_conquer_figure_rect(copied_id) if copied_id else None
        from game.components.conquer_effects import spell_preset
        color, secondary, _label = spell_preset(spell_name)

        spawn_copy = getattr(effects, 'spawn_copy_ghost', None)
        if callable(spawn_copy) and (source_rect is not None or copied_rect is not None):
            # A quick anticipation pulse on the source, then the spinning
            # ghost cluster spirals to where the clone materialises.
            if source_rect is not None:
                spawn_pulse = getattr(effects, 'spawn_rect_pulse', None)
                if callable(spawn_pulse):
                    spawn_pulse(source_rect, color, secondary=secondary,
                                duration_ms=520, scale=0.9)
            spawn_copy(source_rect or anchor_rect, copied_rect or source_rect,
                       color=color, secondary=secondary)
            spawn_float = getattr(effects, 'spawn_floating_text_at_rect', None)
            land_rect = copied_rect or source_rect
            if callable(spawn_float) and land_rect is not None:
                spawn_float(land_rect, 'copy', secondary,
                            delay_ms=int(getattr(effects, 'COPY_MS', 1500) * 0.82))
            return True

        # Fallback: no anchor rects yet — flash a banner so the cast reads.
        spawn_banner = getattr(effects, 'spawn_banner', None)
        if callable(spawn_banner):
            spawn_banner('Copy Figure', color, duration_ms=900,
                         anchor_rect=anchor_rect)
        return True

    def conquer_field_visual_ghost_specs(self):
        """Return destroyed Explosion victims that should occupy field slots.

        The server has already removed Explosion victims by the time the
        conquer replay screen opens.  The timeline, however, must show the
        victim as an ordinary field figure until the Explosion bubble itself
        becomes the leading active step.  Poison and Health Boost do not get
        field ghosts here: their real targets remain on the field and their
        enchantment badges are gated separately.
        """
        game = getattr(self.state, 'game', None)
        if game is None or getattr(game, 'mode', 'duel') != 'conquer':
            return []

        phases = self._conquer_prelude_step_phases()
        specs = []
        prebattle = not (
            bool(getattr(game, 'battle_confirmed', False))
            or self._is_battle_phase_active()
        )
        if not prebattle:
            return specs
        for step_kind, spells in self._conquer_prelude_spell_groups():
            phase = phases.get(step_kind, 'pending')
            for spell in spells or []:
                if not isinstance(spell, dict):
                    continue
                spell_name = spell.get('spell_name')
                if spell_name != 'Explosion':
                    continue
                if phase in ('active', 'completed'):
                    continue
                target_id = self._prelude_spell_target_id(spell)
                if target_id is None:
                    continue
                snapshot = self._prelude_spell_target_snapshot(spell)
                if not snapshot:
                    continue
                specs.append({
                    'target_id': target_id,
                    'snapshot': snapshot,
                    'step_kind': step_kind,
                    'spell_name': spell_name,
                    'phase': 'pending',
                    'visual_only': False,
                    'force_visible': True,
                })
        return specs

    def conquer_prelude_enchantment_visibility(self):
        """Return prelude enchantment target keys visible at this timeline step."""
        game = getattr(self.state, 'game', None)
        if game is None or getattr(game, 'mode', 'duel') != 'conquer':
            return {'tracked': set(), 'revealed': set()}
        phases = self._conquer_prelude_step_phases()
        tracked = set()
        revealed = set()
        reveal_all = bool(getattr(game, 'battle_confirmed', False)) or self._is_battle_phase_active()
        for step_kind, spells in self._conquer_prelude_spell_groups():
            phase = phases.get(step_kind, 'completed' if reveal_all else 'pending')
            for spell in spells or []:
                if not isinstance(spell, dict):
                    continue
                spell_name = spell.get('spell_name')
                if spell_name not in self.FIELD_REPLAY_ENCHANTMENT_SPELLS:
                    continue
                target_id = self._prelude_spell_target_id(spell)
                if target_id is None:
                    continue
                key = (spell_name, target_id)
                tracked.add(key)
                if reveal_all or phase in ('active', 'completed'):
                    revealed.add(key)
        counter_phase = phases.get('counter', 'completed' if reveal_all else 'pending')
        for spell in self._conquer_counter_spells():
            if not isinstance(spell, dict):
                continue
            spell_name = spell.get('spell_name')
            if spell_name not in self.FIELD_REPLAY_ENCHANTMENT_SPELLS:
                continue
            target_id = self._prelude_spell_target_id(spell)
            if target_id is None:
                continue
            key = (spell_name, target_id)
            tracked.add(key)
            if reveal_all or counter_phase in ('active', 'completed'):
                revealed.add(key)
        return {'tracked': tracked, 'revealed': revealed}

    def _conquer_prelude_spell_groups(self):
        """Return own/opponent prelude spell snapshots plus active-spell fallback."""
        game = getattr(self.state, 'game', None)
        if game is None:
            return (('prelude_own', []), ('prelude_opp', []))
        try:
            from game.screens.conquer_flow import _own_prelude_spells, _opp_prelude_spells
            groups = {
                'prelude_own': list(_own_prelude_spells(game) or []),
                'prelude_opp': list(_opp_prelude_spells(game) or []),
            }
        except Exception:
            groups = {'prelude_own': [], 'prelude_opp': []}

        seen = set()
        for step_kind, spells in groups.items():
            for spell in spells:
                if not isinstance(spell, dict):
                    continue
                seen.add(self._conquer_prelude_spell_key(step_kind, spell))

        player_id = getattr(game, 'player_id', None)
        for spell in getattr(game, 'cached_active_spells', []) or []:
            if not isinstance(spell, dict):
                continue
            if not self._is_conquer_prelude_spell_record(spell):
                continue
            step_kind = (
                'prelude_own'
                if spell.get('player_id') == player_id
                else 'prelude_opp'
            )
            normalized = self._normalize_conquer_prelude_spell(spell)
            key = self._conquer_prelude_spell_key(step_kind, normalized)
            if key in seen:
                continue
            groups[step_kind].append(normalized)
            seen.add(key)
        return (('prelude_own', groups['prelude_own']),
                ('prelude_opp', groups['prelude_opp']))

    def _conquer_counter_spells(self):
        game = getattr(self.state, 'game', None)
        if game is None:
            return []
        try:
            from game.screens.conquer_flow import _counter_spells
            return list(_counter_spells(game) or [])
        except Exception:
            return []

    def _conquer_prelude_spell_key(self, step_kind, spell):
        effect_data = spell.get('effect_data') if isinstance(spell, dict) else {}
        if not isinstance(effect_data, dict):
            effect_data = {}
        return (
            step_kind,
            spell.get('spell_name'),
            self._prelude_spell_target_id(spell),
            effect_data.get('prelude_status'),
        )

    def _is_conquer_prelude_spell_record(self, spell):
        effect_data = spell.get('effect_data') if isinstance(spell, dict) else {}
        if not isinstance(effect_data, dict):
            effect_data = {}
        if effect_data.get('counter_origin'):
            return False
        if (effect_data.get('prelude_origin')
                or effect_data.get('prelude_status')
                or effect_data.get('prelude_pending_target')):
            return True
        return (
            int(spell.get('cast_round') or 0) == 1
            and spell.get('spell_name') in self.FIELD_REPLAY_TARGETED_SPELLS
        )

    def _normalize_conquer_prelude_spell(self, spell):
        effect_data = spell.get('effect_data') if isinstance(spell, dict) else {}
        if not isinstance(effect_data, dict):
            effect_data = {}
        return {
            'spell_id': spell.get('spell_id') or spell.get('id'),
            'spell_name': spell.get('spell_name'),
            'spell_type': spell.get('spell_type'),
            'effect_data': effect_data,
            'target_figure_id': (
                spell.get('target_figure_id')
                or effect_data.get('target_figure_id')
                or effect_data.get('affected_figure_id')
                or effect_data.get('destroyed_figure_id')
            ),
            'target_figure_name': (
                spell.get('target_figure_name')
                or effect_data.get('target_figure_name')
                or effect_data.get('destroyed_figure_name')
            ),
            'target_figure_snapshot': (
                spell.get('target_figure_snapshot')
                or spell.get('destroyed_figure_snapshot')
                or effect_data.get('target_figure_snapshot')
                or effect_data.get('destroyed_figure_snapshot')
            ),
        }

    def _conquer_prelude_step_phases(self):
        panel = getattr(self, '_conquer_timeline_panel', None)
        if panel is None:
            return {}
        try:
            steps = panel.derive_display_steps(self) or []
        except Exception:
            return {}
        phases = {}
        active_idx = None
        for idx, step in enumerate(steps):
            if getattr(step, 'active', False):
                active_idx = idx
                break
        for idx, step in enumerate(steps):
            kind = getattr(step, 'kind', '')
            if kind not in ('prelude_own', 'prelude_opp', 'counter'):
                continue
            if active_idx is not None and idx > active_idx:
                phases[kind] = 'pending'
            elif getattr(step, 'active', False):
                phases[kind] = 'active'
            elif getattr(step, 'completed', False):
                phases[kind] = 'completed'
            else:
                phases[kind] = 'pending'
        return phases

    def _hold_conquer_field_explosion_ghost(self, target_id, *, duration_ms):
        holds = getattr(self, '_field_explosion_ghost_hold_until', None)
        if holds is None:
            holds = {}
            self._field_explosion_ghost_hold_until = holds
        holds[target_id] = max(
            int(holds.get(target_id, 0) or 0),
            pygame.time.get_ticks() + int(duration_ms),
        )

    def _refresh_spell_target_ghosts(self, steps, current_phase):
        """Keep missing targeted-spell anchors available for active preludes."""
        now = pygame.time.get_ticks()
        ghosts = getattr(self, '_spell_target_ghosts', None)
        if ghosts is None:
            ghosts = {}
            self._spell_target_ghosts = ghosts
        for figure_id, info in list(ghosts.items()):
            if now > int(info.get('expires_at', 0) or 0):
                ghosts.pop(figure_id, None)

        for step in steps or []:
            kind = getattr(step, 'kind', '')
            if kind not in ('prelude_own', 'prelude_opp', 'counter'):
                continue
            spell_name = getattr(step, 'icon_payload', None)
            if spell_name not in ('Poison', 'Health Boost', 'Explosion'):
                continue
            phase = current_phase.get(self._spell_step_replay_key(step), 'pending')
            if phase not in ('pending', 'active'):
                continue
            spell_info = self._resolve_spell_step_info(kind, spell_name)
            target_id = self._prelude_spell_target_id(spell_info)
            if target_id is None:
                continue
            if self._live_conquer_figure_rect(target_id) is not None:
                continue
            self._ensure_spell_target_ghost(spell_info, target_id, kind,
                                            duration_ms=650,
                                            draw=not (spell_name == 'Explosion'
                                                      and phase == 'active'))

    def _live_conquer_figure_rect(self, figure_id):
        """Return a rect only for figures still rendered by normal UI."""
        if figure_id is None:
            return None
        rects = getattr(self, '_conquer_lane_figure_rects', None) or []
        for info in rects:
            fig = info.get('figure') if isinstance(info, dict) else None
            if fig is not None and getattr(fig, 'id', None) == figure_id:
                rect = info.get('rect')
                if rect is not None:
                    return pygame.Rect(rect)
        field = self.subscreens.get('field') if hasattr(self, 'subscreens') else None
        if field is not None:
            icon = (getattr(field, 'icon_cache', None) or {}).get(figure_id)
            if icon is not None:
                rect = getattr(icon, 'rect_frame', None) or getattr(icon, 'rect_icon', None)
                if rect is not None:
                    return pygame.Rect(rect)
        return None

    def _resolve_prelude_spell_info(self, step_kind, spell_name):
        """Return the matching prelude spell snapshot dict, if any."""
        spells = []
        for group_kind, group_spells in self._conquer_prelude_spell_groups():
            if group_kind == step_kind:
                spells = group_spells
                break
        for spell in spells or []:
            if not isinstance(spell, dict):
                continue
            if (spell.get('spell_name') or '') == spell_name:
                return spell
        return None

    def _resolve_counter_spell_info(self, spell_name):
        for spell in self._conquer_counter_spells():
            if not isinstance(spell, dict):
                continue
            if (spell.get('spell_name') or '') == spell_name:
                return spell
        return None

    def _resolve_spell_step_info(self, step_kind, spell_name):
        if step_kind == 'counter':
            return self._resolve_counter_spell_info(spell_name)
        return self._resolve_prelude_spell_info(step_kind, spell_name)

    @staticmethod
    def _prelude_spell_target_id(spell_info):
        if not isinstance(spell_info, dict):
            return None
        effect_data = spell_info.get('effect_data')
        if not isinstance(effect_data, dict):
            effect_data = {}
        return (spell_info.get('target_figure_id')
                or spell_info.get('affected_figure_id')
                or spell_info.get('destroyed_figure_id')
                or effect_data.get('target_figure_id')
                or effect_data.get('affected_figure_id')
                or effect_data.get('destroyed_figure_id'))

    @staticmethod
    def _prelude_spell_target_snapshot(spell_info):
        if not isinstance(spell_info, dict):
            return None
        effect_data = spell_info.get('effect_data')
        if not isinstance(effect_data, dict):
            effect_data = {}
        snapshot = (
            spell_info.get('target_figure_snapshot')
            or spell_info.get('destroyed_figure_snapshot')
            or effect_data.get('target_figure_snapshot')
            or effect_data.get('destroyed_figure_snapshot')
        )
        return snapshot if isinstance(snapshot, dict) else None

    def _ensure_spell_target_ghost(self, spell_info, target_id, step_kind,
                                   *, duration_ms, draw=True):
        rect = self._spell_target_ghost_rect(spell_info, target_id, step_kind)
        if rect is None:
            return None
        ghosts = getattr(self, '_spell_target_ghosts', None)
        if ghosts is None:
            ghosts = {}
            self._spell_target_ghosts = ghosts
        snapshot = self._prelude_spell_target_snapshot(spell_info) or {}
        ghosts[target_id] = {
            'rect': pygame.Rect(rect),
            'snapshot': snapshot,
            'spell_name': ((spell_info or {}).get('spell_name', 'Explosion')
                           if isinstance(spell_info, dict) else 'Explosion'),
            'expires_at': pygame.time.get_ticks() + int(duration_ms),
            'draw': bool(draw),
        }
        return pygame.Rect(rect)

    def _spell_target_ghost_lookup(self, figure_id):
        ghosts = getattr(self, '_spell_target_ghosts', None) or {}
        info = ghosts.get(figure_id)
        if not info:
            return None
        if pygame.time.get_ticks() > int(info.get('expires_at', 0) or 0):
            ghosts.pop(figure_id, None)
            return None
        rect = info.get('rect')
        return pygame.Rect(rect) if rect is not None else None

    def _spell_target_ghost_rect(self, spell_info, target_id, step_kind):
        snapshot = self._prelude_spell_target_snapshot(spell_info) or {}
        target_rect = (getattr(self, '_last_seen_figure_rects', None) or {}).get(target_id)
        if target_rect is not None:
            return pygame.Rect(target_rect)

        field = self.subscreens.get('field') if hasattr(self, 'subscreens') else None
        if field is not None:
            sync_layout = getattr(field, '_sync_field_compartments_layout', None)
            if callable(sync_layout):
                try:
                    sync_layout()
                except Exception:
                    pass
            rect = self._spell_target_field_fallback_rect(field, snapshot, target_id, step_kind)
            if rect is not None:
                return rect

        return self._spell_target_lane_fallback_rect(step_kind)

    def _spell_target_field_fallback_rect(self, field, snapshot, target_id, step_kind):
        compartments = getattr(field, 'compartments', None) or {}
        if not compartments:
            return None
        game = getattr(self.state, 'game', None)
        player_id = getattr(game, 'player_id', None)
        target_player_id = snapshot.get('player_id')
        if target_player_id is not None and player_id is not None:
            side = 'self' if target_player_id == player_id else 'opponent'
        else:
            side = 'opponent' if step_kind == 'prelude_own' else 'self'
        field_type = snapshot.get('field')
        if field_type not in ('castle', 'village', 'military'):
            field_type = self._spell_target_snapshot_family_field(field, snapshot)
        if field_type not in ('castle', 'village', 'military'):
            field_type = 'military'
        compartment = (compartments.get(side) or {}).get(field_type)
        if compartment is None:
            return None
        compartment = pygame.Rect(compartment)
        figures = []
        categorized = getattr(field, 'categorized_figures', None) or {}
        for fig in ((categorized.get(side) or {}).get(field_type) or []):
            fid = getattr(fig, 'id', None)
            if fid is not None:
                figures.append(fid)
        figure_ids = sorted(set(figures + [target_id]))
        try:
            ghost_index = figure_ids.index(target_id)
        except ValueError:
            ghost_index = max(0, len(figure_ids) - 1)
        count = max(1, len(figure_ids))
        frame_h = settings.FRAME_FIGURE_SCALE * settings.FIGURE_ICON_HEIGHT
        top_margin = settings.FIGURE_ICON_HEIGHT * 0.42
        caption_h = int(settings.FIGURE_ICON_FONT_CAPTION_FONT_SIZE * 2.6)
        bottom_margin = 0.34 * settings.FIGURE_ICON_HEIGHT + caption_h
        title_space = settings.FIELD_TITLE_FONT_SIZE + settings.FIELD_TITLE_PADDING
        total_height = compartment.height - 2 * settings.FIELD_BORDER_WIDTH
        first_center = compartment.top + title_space + top_margin
        last_center = compartment.top + total_height - bottom_margin
        if count == 1:
            center_y = (first_center + last_center) / 2
        else:
            default_spacing = top_margin + bottom_margin + settings.FIELD_ICON_PADDING_Y
            max_spacing = (last_center - first_center) / max(1, count - 1)
            if max_spacing >= default_spacing:
                spacing = default_spacing
                offset = ((last_center - first_center) - (count - 1) * spacing) / 2
                center_y = first_center + offset + ghost_index * spacing
            else:
                spacing = max_spacing
                center_y = first_center + ghost_index * spacing
        width = max(44, int(settings.FIGURE_ICON_WIDTH * settings.FRAME_FIGURE_SCALE))
        height = max(54, int(frame_h))
        rect = pygame.Rect(0, 0, width, height)
        rect.center = (compartment.centerx, int(center_y))
        return rect

    @staticmethod
    def _spell_target_snapshot_family_field(field, snapshot):
        family_name = snapshot.get('family_name') or snapshot.get('name')
        families = getattr(getattr(field, 'figure_manager', None), 'families', None) or {}
        family = families.get(family_name)
        return getattr(family, 'field', None) if family is not None else None

    def _spell_target_lane_fallback_rect(self, step_kind):
        layout = compute_conquer_layout(
            settings.SCREEN_WIDTH,
            settings.SCREEN_HEIGHT,
            mode=self._conquer_effective_layout_mode(),
        )
        lane = layout.battlefield.duel_lane
        band_rect = lane.opp_fighter_band if step_kind == 'prelude_own' else lane.you_fighter_band
        band = self._conquer_lane_center_channel_rect(band_rect, lane)
        rect = pygame.Rect(0, 0, 58, 68)
        rect.center = pygame.Rect(band).center
        return rect

    def _draw_conquer_spell_target_ghosts(self):
        ghosts = getattr(self, '_spell_target_ghosts', None) or {}
        now = pygame.time.get_ticks()
        for target_id, info in list(ghosts.items()):
            if now > int(info.get('expires_at', 0) or 0):
                ghosts.pop(target_id, None)
                continue
            rect = info.get('rect')
            if rect is None:
                continue
            if info.get('draw') is False:
                continue
            rect = pygame.Rect(rect)
            snapshot = info.get('snapshot') if isinstance(info.get('snapshot'), dict) else {}
            family = self._spell_target_ghost_family(snapshot)
            alpha = 170 + int(40 * (0.5 + 0.5 * math.sin(now * 0.010)))
            halo = pygame.Surface((rect.width + 20, rect.height + 20), pygame.SRCALPHA)
            pygame.draw.ellipse(halo, (255, 168, 56, 72), halo.get_rect())
            self.window.blit(halo, halo.get_rect(center=rect.center))
            if family is not None:
                ghost = SimpleNamespace(
                    id=target_id,
                    player_id=snapshot.get('player_id'),
                    name=snapshot.get('name') or snapshot.get('family_name') or 'Target',
                    suit=snapshot.get('suit'),
                    family=family,
                )
                icon_surface = pygame.Surface((rect.width + 24, rect.height + 24), pygame.SRCALPHA)
                original_window = self.window
                self.window = icon_surface
                try:
                    self._draw_conquer_lane_figure_art(
                        ghost,
                        icon_surface.get_rect().center,
                        max(36, min(rect.width, rect.height)),
                    )
                finally:
                    self.window = original_window
                icon_surface.set_alpha(alpha)
                self.window.blit(icon_surface, icon_surface.get_rect(center=rect.center))
            else:
                pygame.draw.ellipse(self.window, (80, 50, 30), rect)
                pygame.draw.ellipse(self.window, (255, 168, 56), rect, 2)
                font = settings.get_font(max(12, int(settings.FS_TINY)), bold=True)
                label = font.render('!', True, (255, 240, 200))
                self.window.blit(label, label.get_rect(center=rect.center))
            name = snapshot.get('name') or snapshot.get('family_name') or 'Target'
            font = settings.get_font(settings.FS_CONQUER_LABEL, bold=True)
            label = self._fit_text(name, font, max(48, rect.width + 28))
            surf = font.render(label, True, (255, 228, 176))
            label_rect = surf.get_rect(midtop=(rect.centerx, rect.bottom + 2))
            self.window.blit(surf, label_rect)

    def _spell_target_ghost_family(self, snapshot):
        family_name = snapshot.get('family_name') or snapshot.get('name')
        if not family_name:
            return None
        field = self.subscreens.get('field') if hasattr(self, 'subscreens') else None
        families = getattr(getattr(field, 'figure_manager', None), 'families', None) or {}
        return families.get(family_name)

    def _resolve_prelude_spell_target(self, step_kind, spell_name):
        """Return the target figure id for a prelude spell, or ``None``."""
        return self._prelude_spell_target_id(
            self._resolve_prelude_spell_info(step_kind, spell_name))

    def _register_orphan_rect(self, rect):
        """Register a remembered rect under a synthetic negative id."""
        if not hasattr(self, '_orphan_explosion_rects'):
            self._orphan_explosion_rects = {}
        synthetic_id = -1 * (1000 + len(self._orphan_explosion_rects) + 1)
        self._orphan_explosion_rects[synthetic_id] = (
            pygame.Rect(rect),
            pygame.time.get_ticks() + 2000,
        )
        return synthetic_id

    def _spawn_orphan_explosion(self, target_rect, anchor_rect):
        """Spawn an explosion burst at a rect whose figure is gone.

        Builds a tiny one-shot anchor so the effects layer's rect-lookup
        callback can resolve the target id.  We register the rect under a
        synthetic negative figure id that will not collide with real ones.
        """
        if target_rect is None:
            return
        effects = self._conquer_effects
        synthetic_id = -1 * (1000 + len(getattr(self, '_orphan_explosion_rects', {})))
        if not hasattr(self, '_orphan_explosion_rects'):
            self._orphan_explosion_rects = {}
        self._orphan_explosion_rects[synthetic_id] = (pygame.Rect(target_rect),
                                                     pygame.time.get_ticks() + 1500)
        effects.spawn_explosion(anchor_rect, synthetic_id)

    def _orphan_explosion_lookup(self, figure_id):
        """Resolve synthetic orphan-explosion figure ids."""
        entries = getattr(self, '_orphan_explosion_rects', None) or {}
        info = entries.get(figure_id)
        if info is None:
            return None
        rect, expires_at = info
        if pygame.time.get_ticks() > expires_at:
            entries.pop(figure_id, None)
            return None
        return rect

    def _handle_conquer_lane_figure_click(self, pos):
        """Open the figure detail box when a duel-lane figure icon is clicked."""
        rects = getattr(self, '_conquer_lane_figure_rects', None) or []
        for info in rects:
            rect = info.get('rect')
            if rect and pygame.Rect(rect).collidepoint(pos):
                figure = info.get('figure')
                field = self.subscreens.get('field') if hasattr(self, 'subscreens') else None
                if field is None or figure is None:
                    return False
                icon = getattr(field, 'icon_cache', {}).get(getattr(figure, 'id', None))
                if icon is None:
                    for candidate in getattr(field, 'figure_icons', []) or []:
                        if getattr(candidate, 'figure', None) is figure:
                            icon = candidate
                            break
                if icon is None:
                    return False
                opener = getattr(field, '_open_tactics_hand_battle_detail', None)
                if callable(opener):
                    opener(icon)
                    return True
        return False

    def request_conquer_gamble_preview(self, tactic_id):
        """Fetch (and pin) the All Seeing Eye gamble preview for a tactic.

        Returns the two replacement-tactic specs, or ``None`` when the
        preview is unavailable (no All Seeing Eye, already previewed this
        round, network error, ...).  The server pins the returned specs so
        gambling this tactic yields exactly the previewed replacements.
        """
        game = self.state.game
        if game is None:
            return None
        ase_check = getattr(game, 'has_active_all_seeing_eye', None)
        if not callable(ase_check) or not ase_check():
            return None
        try:
            result = game_service.conquer_gamble_preview(
                game.game_id, game.player_id, tactic_id)
        except Exception:
            return None
        if not isinstance(result, dict) or not result.get('success'):
            return None
        if result.get('game'):
            game.update_from_dict(result['game'])
        preview = result.get('preview') or {}
        specs = preview.get('specs') or []
        return specs if len(specs) == 2 else None

    def _dispatch_tactics_rail_action(self, action_payload):
        """Apply a tactics-rail action by calling the appropriate API."""
        if not action_payload:
            return
        game = self.state.game
        if not game:
            return
        gid = getattr(game, 'game_id', None)
        pid = getattr(game, 'player_id', None)
        if gid is None or pid is None:
            return
        action = action_payload.get('action')
        move = action_payload.get('move') or {}
        mid = move.get('id')
        # Friendly label for the banner.
        family = (move.get('family_name') or move.get('family')
                  or move.get('name') or 'Tactic')
        rank = move.get('rank') or ''
        rail = getattr(self, '_tactics_rail', None)
        result = None
        from utils import sound
        sound.play({
            ACTION_PLAY: 'card_place',
            ACTION_GAMBLE: 'card_slide',
            ACTION_COMBINE: 'figure_place',
            ACTION_DISMANTLE: 'card_slide',
            ACTION_SKIP: 'ui_back',
        }.get(action, 'ui_click'))
        try:
            if self._is_tactics_hand_game() and action == ACTION_PLAY and mid is not None:
                call_figure = self._conquer_best_call_figure_for_tactic(move)
                call_figure_id = (
                    getattr(call_figure, 'id', None)
                    if call_figure is not None
                    else move.get('call_figure_id')
                )
                if call_figure_id is not None:
                    result = game_service.play_conquer_tactic(
                        gid, pid, mid, call_figure_id=call_figure_id)
                else:
                    result = game_service.play_conquer_tactic(gid, pid, mid)
                if not isinstance(result, dict) or result.get('success', True):
                    self._start_tactic_flight_animation(move)
            elif action == ACTION_PLAY and mid is not None:
                result = game_service.play_battle_move(gid, pid, mid)
            elif action == ACTION_SKIP:
                result = game_service.skip_battle_turn(gid, pid)
            elif self._is_tactics_hand_game() and action == ACTION_GAMBLE and mid is not None:
                result = game_service.gamble_conquer_tactic(gid, pid, mid)
            elif action == ACTION_GAMBLE and mid is not None:
                result = battle_shop_service.gamble_battle_move(gid, pid, mid)
            elif self._is_tactics_hand_game() and action == ACTION_DISMANTLE and mid is not None:
                result = game_service.dismantle_conquer_tactic(gid, pid, mid)
            elif action == ACTION_DISMANTLE and mid is not None:
                result = battle_shop_service.dismantle_battle_move(gid, pid, mid)
            elif action == ACTION_COMBINE and mid is not None:
                partner = action_payload.get('partner') or {}
                pmid = partner.get('id')
                if pmid is not None:
                    if self._is_tactics_hand_game():
                        result = game_service.combine_conquer_tactics(gid, pid, mid, pmid)
                    else:
                        result = battle_shop_service.combine_battle_moves(gid, pid, mid, pmid)
        except Exception as exc:
            result = {'success': False, 'message': str(exc) or 'Action failed'}
        if isinstance(result, dict) and result.get('success') is False:
            sound.play('error')
            set_banner = getattr(rail, 'set_result_banner', None) if rail else None
            message = result.get('message') or 'Action failed'
            if callable(set_banner):
                set_banner(message, color=(232, 140, 120), ttl_ms=5000)
                if action == ACTION_GAMBLE and hasattr(rail, '_gamble_anim'):
                    rail._gamble_anim = None
            else:
                self.make_dialogue_box(message, actions=['ok'], icon='info', title='Error')
            self._conquer_tactic_cache_key = None  # force refetch
            self._conquer_battle_move_cache_key = None  # force refetch
            if getattr(self, '_battle_state_poller', None) is not None:
                self._request_battle_state_poll(force=True)
            return
        # Show a banner reflecting the action that was just submitted; the
        # rail's auto-glow will highlight any newly-arrived moves once the
        # next poll lands. (#8a / #8c)
        set_banner = getattr(rail, 'set_result_banner', None) if rail else None
        # Apply the server-returned game state immediately so gates that
        # depend on it (e.g. gamble lockout) reflect the new state without
        # waiting for the next poll. Mitigates double-gamble in a round
        # when the user double-clicks before the poll catches up.
        try:
            game_state = isinstance(result, dict) and result.get('game')
            game_obj = self.state.game if hasattr(self, 'state') else None
            if game_state and game_obj is not None and hasattr(game_obj, 'update_from_dict'):
                game_obj.update_from_dict(game_state)
                try:
                    self._sync_conquer_action_modes()
                    self._auto_route_conquer_once()
                except Exception:
                    pass
        except Exception:
            pass
        if callable(set_banner):
            label = f"{family} {rank}".strip()
            if action == ACTION_PLAY:
                # First-conquest tutorial: explain *why* a Dagger matters the
                # first time one is played, not just that it was played.
                if ('Dagger' in str(family)
                        and self._first_conquest_tutorial_active()
                        and not getattr(self, '_tutorial_dagger_explained', False)):
                    self._tutorial_dagger_explained = True
                    set_banner(
                        f"Played {label} — Daggers add their value to your attack total.",
                        color=(180, 220, 160), ttl_ms=6000)
                else:
                    set_banner(f"Played {label}", color=(180, 220, 160), ttl_ms=4500)
            elif action == ACTION_GAMBLE:
                drawn = result.get('new_tactics') if isinstance(result, dict) else None
                if drawn:
                    names = []
                    for tactic in drawn[:2]:
                        if not isinstance(tactic, dict):
                            continue
                        t_name = tactic.get('family_name') or 'Tactic'
                        t_rank = tactic.get('rank') or ''
                        names.append(f'{t_name} {t_rank}'.strip())
                    if names:
                        drew = ' + '.join(names)
                        set_banner(f'Drew {drew}', color=(250, 226, 130),
                                   ttl_ms=6000)
                        self.push_conquer_feed(
                            f'Gambled {label} → drew {drew}.',
                            (250, 226, 130))
                    else:
                        set_banner(f'Gambling {label}…',
                                   color=(238, 218, 170), ttl_ms=5500)
                else:
                    set_banner(f'Gambling {label}…', color=(238, 218, 170),
                               ttl_ms=5500)
            elif action == ACTION_COMBINE:
                set_banner(f"Combined {label}", color=(170, 200, 240), ttl_ms=4500)
            elif action == ACTION_DISMANTLE:
                set_banner(f"Dismantled {label}", color=(220, 170, 170), ttl_ms=4500)
            elif action == ACTION_SKIP:
                set_banner("Skipped battle turn", color=(190, 190, 190), ttl_ms=3500)
        self._tactics_rail.reset_after_action()
        self._conquer_tactic_cache_key = None  # force refetch
        self._conquer_battle_move_cache_key = None  # force refetch
        if getattr(self, '_battle_state_poller', None) is not None:
            self._request_battle_state_poll(force=True)

    def _reset_game_screen_state(self):
        """Reset shared and conquer-only state when entering a different game."""
        super()._reset_game_screen_state()
        self.reset_conquer_panel_state()
        self._tactic_flight_animation = None
        self._conquer_payoff_pending = None
        self._conquer_payoff_until_ms = 0
        self._battle_countdown_started_ms = 0
        self._battle_countdown_until_ms = 0
        self._battle_countdown_last_beat = -1
        self._conquer_countdown_done = False
        self._conquer_saw_prebattle = False
        self._conquer_lane_figure_seen = None
        self._conquer_lane_figure_entrances = {}
        effects = getattr(self, '_conquer_effects', None)
        if effects is not None:
            effects.clear()
        sequencer = getattr(self, '_conquer_reveal_sequencer', None)
        if sequencer is not None:
            sequencer.reset()
        self._conquer_battle_feed = []
        self._battle_state_poller = None
        self._battle_state_poller_key = None
        self._battle_state_pending_key = None
        self._battle_state_last_poll_ms = 0
        self._conquer_tactic_cache_key = None
        self._conquer_tactic_cache = []
        self._conquer_opponent_tactic_cache_key = None
        self._conquer_opponent_tactic_cache = []
        self._conquer_lane_context_cache_key = None
        self._conquer_lane_context_cache = None
        self._conquer_tactic_power_cache_key = None
        self._conquer_tactic_power_cache = {}
        self._withdraw_dialogue_open = False
        self._tutorial_dagger_explained = False
        self._battle_intro_dialogue = None
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
        if self._is_tactics_hand_game():
            self.battle_button.locked = True
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
        advancing_id = getattr(game, 'advancing_figure_id', None)

        if (getattr(game, 'pending_conquer_prelude_target', False)
                or getattr(self.state, 'pending_conquer_prelude_target', None)):
            return 'field', ('field', 'prelude', getattr(game, 'pending_spell_id', None))

        if getattr(game, 'pending_forced_advance', False) and not getattr(game, 'advancing_figure_id', None):
            return 'field', ('field', 'forced_advance', getattr(game, 'current_round', None))

        field_screen = self.subscreens.get('field')
        if (advancing_id
                and getattr(game, 'pending_defender_selection', False)
                and getattr(game, 'defender_selection_dialogue_shown', False)):
            return 'field', ('field', 'select_defender', advancing_id)

        if advancing_id and (
                (field_screen and getattr(field_screen, 'conquer_own_defender_mode', False))
                or getattr(game, 'pending_conquer_own_defender_selection', False)):
            return 'field', ('field', 'own_defender', advancing_id)

        if (getattr(game, 'battle_confirmed', False)
                and getattr(game, 'battle_turn_player_id', None) is not None):
            if self._is_tactics_hand_game():
                return 'field', ('field', 'tactics_hand_battle',
                                 getattr(game, 'battle_round', 0),
                                 getattr(game, 'battle_turn_player_id', None))
            return 'battle', ('battle', getattr(game, 'battle_round', 0),
                              getattr(game, 'battle_turn_player_id', None))

        if getattr(game, 'both_battle_moves_ready', False):
            if self._is_tactics_hand_game():
                return 'field', ('field', 'tactics_hand_battle_ready',
                                 getattr(game, 'current_round', None))
            return 'battle', ('battle_ready', getattr(game, 'current_round', None))

        if (getattr(game, 'battle_moves_phase', False)
                and not getattr(game, 'battle_moves_ready', False)
                and not getattr(game, 'waiting_for_opponent_battle_moves', False)):
            if self._is_tactics_hand_game():
                # Tactics-hand never enters battle_moves_phase server-side
                # but if a stale flag lingers in the client snapshot, route
                # to the field rather than the (gone) battle_shop subscreen.
                return 'field', ('field', 'tactics_hand_moves_phase')
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
        if objective_tab in ('battle_shop', 'battle') and self._is_tactics_hand_game():
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
        advancing_id = getattr(game, 'advancing_figure_id', None)

        field = 0
        if (getattr(game, 'pending_conquer_prelude_target', False)
                or getattr(self.state, 'pending_conquer_prelude_target', None)
                or (getattr(game, 'pending_forced_advance', False)
                    and not advancing_id)
                or (advancing_id
                    and getattr(game, 'pending_defender_selection', False)
                    and getattr(game, 'defender_selection_dialogue_shown', False))
                or (advancing_id and getattr(game, 'pending_conquer_own_defender_selection', False))
                or (advancing_id and getattr(game, 'civil_war_awaiting_second', False))
                or (advancing_id and getattr(game, 'civil_war_defender_second', False))):
            field = 1

        battle = 0
        if (getattr(game, 'battle_confirmed', False)
                and getattr(game, 'battle_turn_player_id', None) is not None):
            if self._is_tactics_hand_game():
                field = 1
            else:
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
        # Tactics-hand games never visit battle_shop — the unified tactics
        # rail replaces it entirely.  Skip all of the moves-phase routing.
        if self._is_tactics_hand_game():
            self._conquer_left_battle_shop_at = 0
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
        if self._is_tactics_hand_game():
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
            try:
                self._sync_conquer_action_modes()
                self._auto_route_conquer_once()
            except Exception:
                pass

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

    def queue_or_show_notification(self, notification_data):
        """In conquer mode, route informational receipts away from modals.

        Base GameScreen already strips routing/dedup metadata; conquer also
        suppresses `message_after_images` since the timeline panel already
        narrates the same content.
        """
        data = dict(notification_data)
        if self._should_drop_conquer_notification(data):
            return
        data.pop('message_after_images', None)
        super().queue_or_show_notification(data)

    def request_conquer_figure_confirmation(self, kind, figure, icon=None,
                                            message='', title='Confirm'):
        """Ask the timeline panel to confirm a pending field action."""
        # Soft feedback when a figure is selected for advance/defence (the
        # confirm itself plays a firmer 'card_slide' via the objective action).
        if not self._conquer_pending_confirmation:
            from utils import sound
            sound.play('ui_click', volume=0.8)
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
        from utils import sound
        sound.play({'next': 'ui_click', 'confirm': 'card_slide',
                    'finish': 'battle_start', 'cancel': 'ui_back',
                    'withdraw': 'ui_back'}.get(action, 'ui_click'))
        if action == 'next':
            return self._advance_active_timeline_step()
        if action == 'withdraw':
            self._open_withdraw_dialogue()
            return True
        if action == 'finish':
            return self._trigger_conquer_finish_battle()
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
            game = self.state.game
            if (kind in ('opponent_defender', 'own_defender')
                    and game is not None
                    and not getattr(game, 'advancing_figure_id', None)):
                self._clear_stale_conquer_defender_flags_if_no_advance()
                self.clear_conquer_figure_confirmation()
                return True
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
                hit_rect = pygame.Rect(rect) if rect else None
                if hit_rect is not None and settings.TOUCH_TARGET_MIN > 0:
                    hit_rect = hit_rect.inflate(
                        max(0, settings.TOUCH_TARGET_MIN - hit_rect.width),
                        max(0, settings.TOUCH_TARGET_MIN - hit_rect.height),
                    )
                if hit_rect and hit_rect.collidepoint(event.pos):
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

        if self._is_battle_phase_active():
            if getattr(field, 'defender_selection_mode', False):
                field.defender_selection_mode = False
                if hasattr(field, '_reset_defender_selectable'):
                    field._reset_defender_selectable()
            if getattr(field, 'conquer_own_defender_mode', False):
                field.conquer_own_defender_mode = False
                if hasattr(field, '_reset_defender_selectable'):
                    field._reset_defender_selectable()
            self._auto_single_option_pending = None
            return

        if not getattr(game, 'advancing_figure_id', None):
            self._clear_stale_conquer_defender_flags_if_no_advance()
            if getattr(field, 'defender_selection_mode', False):
                field.defender_selection_mode = False
                field._reset_defender_selectable()
            if getattr(field, 'conquer_own_defender_mode', False):
                field.conquer_own_defender_mode = False
                field._reset_defender_selectable()
            self._auto_single_option_pending = None
            return

        civil_war_second_defender = bool(getattr(game, 'civil_war_defender_second', False))
        try:
            own_civil_war_second_defender = bool(
                civil_war_second_defender
                and not self._ids_equal(getattr(game, 'advancing_player_id', None),
                                        getattr(game, 'player_id', None))
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
        timeline step to active.  If the active step is an interactive
        single-option step, fire it immediately instead so the player can
        skip the auto-advance hold.
        """
        if self._conquer_battle_intro_paused():
            return False
        # Pre-empt the auto-advance hold for single-option interactive steps.
        if self._auto_single_option_pending is not None or \
                self._detect_single_option_context()[0] is not None:
            if self._fire_pending_single_option():
                return True
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

    def conquer_revealed_spell_step_count(self, steps=None):
        """Count card-effect spell timeline beats whose rail animation landed.

        Walks the timeline in order and tallies each prelude/counter spell
        bubble that (a) mutates the tactics rail (a *card-effect* spell such
        as Draw 2 / Forced Deal / Dump Cards / Fill up to 10) and (b) has had
        its animation reach the rail.  Figure/modifier spells are skipped —
        they never mutate tactics and must not advance the gate.  Because the
        beats are sequenced, the walk stops at the first card-effect spell
        whose animation has not landed yet, so a later beat never surfaces
        before each preceding one is shown on screen.

        Used by :meth:`ConquerTimelinePanel.currently_resolved_step_index` to
        keep the rail's spell-driven mutations in lockstep with the
        animations instead of revealing them the instant a bubble lights up.
        """
        if steps is None:
            panel = getattr(self, '_conquer_timeline_panel', None)
            if panel is None:
                return 0
            try:
                steps = panel.derive_display_steps(self)
            except Exception:
                return 0
        impacts = getattr(self, '_conquer_spell_anim_impact_ms', None) or {}
        now = pygame.time.get_ticks()
        count = 0
        for step in steps or []:
            if getattr(step, 'kind', '') not in (
                    'prelude_own', 'prelude_opp', 'counter'):
                continue
            if not (getattr(step, 'completed', False)
                    or getattr(step, 'active', False)):
                continue
            payload = getattr(step, 'icon_payload', None)
            if not isinstance(payload, str) or not payload:
                continue
            try:
                spell_info = self._resolve_spell_step_info(step.kind, payload)
            except Exception:
                spell_info = None
            if not self._is_conquer_card_effect_spell(payload, spell_info):
                # Figure / battle-modifier spell — never touches the rail.
                continue
            replay_key_fn = getattr(
                self, '_spell_step_replay_key',
                ConquerGameScreen._spell_step_replay_key)
            key = replay_key_fn(step)
            impact = impacts.get(key)
            if impact is None:
                # Animation has not been fired yet (it spawns later this
                # frame); hold here until its impact time is recorded.
                break
            if now < int(impact):
                # Projectile still in flight — hold this and every later beat.
                break
            count += 1
        return count

    def conquer_unlanded_spell_step_count(self, steps=None, kinds=('counter',)):
        """Count card-effect spell beats whose rail animation has not landed.

        During the battle phase the prelude replay is finished, so the rail
        mirrors the server's ``conquer_resolution_step`` directly — except for
        counter spells, which resolve mid-battle and animate towards the rail.
        Subtracting this count from the server step withholds each counter
        spell's tactics mutation until its projectile reaches the rail.

        ``kinds`` selects which spell beats are impact-gated (defaults to
        counter spells, the only spell beats that resolve during battle).
        """
        if steps is None:
            panel = getattr(self, '_conquer_timeline_panel', None)
            if panel is None:
                return 0
            try:
                steps = panel.derive_display_steps(self)
            except Exception:
                return 0
        impacts = getattr(self, '_conquer_spell_anim_impact_ms', None) or {}
        now = pygame.time.get_ticks()
        pending = 0
        for step in steps or []:
            if getattr(step, 'kind', '') not in kinds:
                continue
            if not (getattr(step, 'completed', False)
                    or getattr(step, 'active', False)):
                continue
            payload = getattr(step, 'icon_payload', None)
            if not isinstance(payload, str) or not payload:
                continue
            try:
                spell_info = self._resolve_spell_step_info(step.kind, payload)
            except Exception:
                spell_info = None
            if not self._is_conquer_card_effect_spell(payload, spell_info):
                # Figure / battle-modifier spell — never touches the rail.
                continue
            replay_key_fn = getattr(
                self, '_spell_step_replay_key',
                ConquerGameScreen._spell_step_replay_key)
            key = replay_key_fn(step)
            impact = impacts.get(key)
            if impact is None or now < int(impact):
                pending += 1
        return pending

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
        if self._is_tactics_hand_game():
            return
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
            font = settings.get_font(settings.FS_CONQUER_LABEL, bold=True)
            self._conquer_move_panel_title_font = font
        return font

    def _conquer_move_empty_font(self):
        font = getattr(self, '_conquer_move_panel_empty_font', None)
        if font is None:
            font = settings.get_font(max(settings.FS_CONQUER_LABEL, int(settings.FS_TINY * 0.95)), bold=True)
            self._conquer_move_panel_empty_font = font
        return font

    @staticmethod
    def _fetch_battle_state_data(game_id, player_id):
        """Threaded desktop worker for the conquer battle-state snapshot."""
        return game_service.get_battle_state(game_id, player_id)

    @staticmethod
    def _transform_battle_state_async_response(resp):
        """Convert a web async-XHR response into a battle-state dict."""
        try:
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            return {'success': False, 'message': str(exc) or 'Battle state error'}

    def _battle_state_key(self):
        game = getattr(self.state, 'game', None)
        if not game:
            return None
        game_id = getattr(game, 'game_id', None)
        player_id = getattr(game, 'player_id', None)
        if not game_id or not player_id:
            return None
        return (game_id, player_id)

    def _battle_state_cache_key(self):
        game = getattr(self.state, 'game', None)
        key = self._battle_state_key()
        if not game or not key:
            return None
        return (
            'tactics',
            key[0],
            key[1],
            getattr(game, 'battle_turn_player_id', None),
            getattr(game, 'battle_round', None),
            bool(getattr(game, 'last_battle_result', None)),
            int(getattr(self, '_conquer_resolution_step_server',
                        getattr(game, 'conquer_resolution_step', 0)) or 0),
        )

    def _ensure_battle_state_poller(self):
        key = self._battle_state_key()
        if not key:
            return None
        if (getattr(self, '_battle_state_poller', None) is None
                or key != getattr(self, '_battle_state_poller_key', None)):
            game_id, player_id = key
            self._battle_state_poller = BackgroundPoller(
                self._fetch_battle_state_data,
                args=(game_id, player_id),
                async_get_url=f'{settings.SERVER_URL}/games/get_battle_state',
                async_get_params={'game_id': game_id, 'player_id': player_id},
                async_transform=self._transform_battle_state_async_response,
            )
            self._battle_state_poller_key = key
            self._battle_state_pending_key = None
            self._battle_state_last_poll_ms = 0
        return self._battle_state_poller

    def _apply_battle_state_result(self, result):
        if not isinstance(result, dict) or result.get('success') is False:
            return
        game = getattr(self.state, 'game', None)
        if not game:
            return

        state_changed = False

        def _update_game_attr(attr, value):
            nonlocal state_changed
            try:
                if getattr(game, attr, None) != value:
                    setattr(game, attr, value)
                    state_changed = True
            except Exception:
                pass

        tactics = result.get('player_tactics') or result.get('player_moves') or []
        opponent_tactics = result.get('opponent_tactics') or result.get('opponent_moves') or []
        self._conquer_tactic_cache = [
            dict(move) for move in tactics if isinstance(move, dict)
        ]
        self._conquer_opponent_tactic_cache = [
            dict(move) for move in opponent_tactics if isinstance(move, dict)
        ]

        if 'battle_round' in result:
            _update_game_attr('battle_round', result.get('battle_round'))
        if 'battle_turn_player_id' in result:
            _update_game_attr('battle_turn_player_id', result.get('battle_turn_player_id'))
        if 'battle_confirmed' in result:
            _update_game_attr('battle_confirmed', bool(result.get('battle_confirmed')))
        elif (getattr(game, 'battle_turn_player_id', None) is not None
              or bool(result.get('battle_complete'))):
            _update_game_attr('battle_confirmed', True)
        if 'invader_player_id' in result:
            _update_game_attr('invader_player_id', result.get('invader_player_id'))
        for attr in (
                'advancing_player_id', 'advancing_figure_id', 'advancing_figure_id_2',
                'defending_figure_id', 'defending_figure_id_2'):
            if attr in result:
                _update_game_attr(attr, result.get(attr))
        if 'battle_skipped_rounds' in result:
            _update_game_attr('battle_skipped_rounds', result.get('battle_skipped_rounds') or {})
        if 'battle_total_diff' in result:
            incoming_total = result.get('battle_total_diff')
            known_total = getattr(game, 'battle_total_diff', None)
            resolved = bool(result.get('battle_complete')
                            or result.get('conquer_result'))
            # Resolution destroys the losing figure, so a snapshot caught
            # between the live calculation and the persisted result can carry
            # ``None``.  Never let that completed snapshot erase the last
            # authoritative value already shown by the ledger.
            if not (resolved and incoming_total is None and known_total is not None):
                _update_game_attr('battle_total_diff', incoming_total)
        if 'conquer_round_deadline_ts' in result:
            _update_game_attr('conquer_round_deadline_ts', result.get('conquer_round_deadline_ts'))
        if 'conquer_round_timeout_sec' in result:
            _update_game_attr('conquer_round_timeout_sec', result.get('conquer_round_timeout_sec'))
        if 'active_spells' in result:
            try:
                previous_spells = getattr(game, 'cached_active_spells', None)
                active_spells = result.get('active_spells') or []
                if previous_spells != active_spells:
                    game.cached_active_spells = active_spells
                    game._figures_data_version = int(
                        getattr(game, '_figures_data_version', 0) or 0) + 1
                    state_changed = True
            except Exception:
                pass
        if 'battle_modifier' in result:
            _update_game_attr('battle_modifier', result.get('battle_modifier'))
        if 'conquer_resolution_step' in result:
            try:
                step = int(result.get('conquer_resolution_step') or 0)
                self._conquer_resolution_step_server = step
                if getattr(game, 'conquer_resolution_step', None) != step:
                    setattr(game, 'conquer_resolution_step', step)
                    state_changed = True
            except Exception:
                pass

        self._conquer_tactic_cache_key = self._battle_state_cache_key()
        self._conquer_opponent_tactic_cache_key = self._conquer_tactic_cache_key
        self._battle_state_pending_key = None
        if state_changed:
            try:
                game._game_data_version = int(
                    getattr(game, '_game_data_version', 0) or 0) + 1
            except Exception:
                pass
        try:
            self._sync_conquer_action_modes()
            self._auto_route_conquer_once()
        except Exception:
            pass

        if result.get('conquer_result') and not getattr(
                self.state.game, '_conquer_result_dialogue_shown', False):
            try:
                self._handle_conquer_result_response(result)
            except Exception:
                pass

    def _seed_battle_state_cache_from_game(self):
        """Use the game snapshot as a temporary cache until async poll returns."""
        if getattr(self, '_conquer_tactic_cache', None):
            return
        game = getattr(self.state, 'game', None)
        player_id = getattr(game, 'player_id', None) if game else None
        tactics = getattr(game, 'conquer_tactics', None) if game else None
        if not player_id or not isinstance(tactics, list):
            return

        player_tactics = []
        opponent_tactics = []
        reveal = self._own_all_seeing_eye_active()
        for tactic in tactics:
            if not isinstance(tactic, dict):
                continue
            if self._ids_equal(tactic.get('player_id'), player_id):
                player_tactics.append(dict(tactic))
                continue
            if (tactic.get('status') == 'played'
                    or tactic.get('played_round') is not None
                    or (reveal and tactic.get('rank') and tactic.get('suit'))):
                opponent_tactics.append(dict(tactic))
            else:
                opponent_tactics.append({
                    'id': tactic.get('id'),
                    'player_id': tactic.get('player_id'),
                    'status': tactic.get('status'),
                    'played_round': None,
                })
        if player_tactics or opponent_tactics:
            self._conquer_tactic_cache = player_tactics
            self._conquer_opponent_tactic_cache = opponent_tactics
            self._conquer_tactic_cache_key = self._battle_state_cache_key()
            self._conquer_opponent_tactic_cache_key = self._conquer_tactic_cache_key

    def _drain_battle_state_poller(self):
        poller = getattr(self, '_battle_state_poller', None)
        if poller is None or not poller.has_result():
            return False
        self._apply_battle_state_result(poller.result)
        return True

    def _request_battle_state_poll(self, force=False):
        if not self._is_tactics_hand_game():
            return
        poller = self._ensure_battle_state_poller()
        if poller is None:
            return
        with perf_section('conquer.poll.battle_state_drain'):
            self._drain_battle_state_poller()
        if getattr(poller, '_busy', False):
            return
        now = pygame.time.get_ticks()
        due = (
            now - int(getattr(self, '_battle_state_last_poll_ms', 0) or 0)
            >= self.BATTLE_STATE_POLL_MS
        )
        cache_empty = (
            not getattr(self, '_conquer_tactic_cache', None)
            and not getattr(self, '_conquer_opponent_tactic_cache', None)
        )
        desired_key = self._battle_state_cache_key()
        stale = desired_key != getattr(self, '_conquer_tactic_cache_key', None)
        if not (force or due or cache_empty or stale):
            return
        self._battle_state_last_poll_ms = now
        self._battle_state_pending_key = desired_key
        key = self._battle_state_key()
        if key:
            with perf_section('conquer.poll.battle_state_start'):
                poller.poll(args=key)

    def _current_conquer_tactics(self):
        game = self.state.game
        if not game:
            return []
        if not self._is_tactics_hand_game():
            return []

        game_id = getattr(game, 'game_id', None)
        player_id = getattr(game, 'player_id', None)
        if not game_id or not player_id:
            return self._filter_conquer_tactics_by_displayed_step(
                list(getattr(game, 'conquer_tactics', []) or []))

        self._seed_battle_state_cache_from_game()
        cache_key = self._battle_state_cache_key()
        if cache_key != getattr(self, '_conquer_tactic_cache_key', None):
            tactics = [
                dict(tactic)
                for tactic in (getattr(game, 'conquer_tactics', []) or [])
                if isinstance(tactic, dict) and self._ids_equal(tactic.get('player_id'), player_id)
            ]
            if tactics:
                return self._filter_conquer_tactics_by_displayed_step(tactics)
        return self._filter_conquer_tactics_by_displayed_step(
            list(getattr(self, '_conquer_tactic_cache', []) or []))

    def _displayed_conquer_step(self):
        """Resolution step the client is currently displaying.

        Defaults to the server's authoritative ``conquer_resolution_step`` so
        without explicit animation handling the latest state is shown. The
        timeline panel may temporarily report a smaller value during a spell
        animation to keep pre-mutation tactics visible until the animation
        completes.
        """
        cached = getattr(self, '_conquer_resolution_step_server', None)
        game = self.state.game
        server_step = int(cached) if cached is not None else (
            int(getattr(game, 'conquer_resolution_step', 0) or 0) if game else 0
        )
        timeline = getattr(self, '_conquer_timeline_panel', None) \
            or getattr(self, 'conquer_timeline_panel', None)
        if timeline is not None:
            if getattr(timeline, '_deriving_display_steps', False):
                return server_step
            getter = getattr(timeline, 'currently_resolved_step_index', None)
            if callable(getter):
                try:
                    result = getter(self)
                except TypeError:
                    try:
                        result = getter()
                    except Exception:
                        result = None
                except Exception:
                    result = None
                if result is not None:
                    return int(result)
        # Fall back to the server's current step. Use either the cached value
        # from the most recent get_battle_state call or the snapshot on Game.
        return server_step

    def _filter_conquer_tactics_by_displayed_step(self, tactics):
        """Apply spell-timeline replay to a serialized tactics list."""
        if not tactics:
            return []
        displayed = self._displayed_conquer_step()
        out = []
        for t in tactics:
            if not isinstance(t, dict):
                out.append(t)
                continue
            revealed = t.get('revealed_step_index')
            discarded = t.get('discarded_step_index')
            status = t.get('status')
            # Hide tactics that haven't been revealed yet.
            if revealed is not None and int(revealed) > displayed:
                continue
            # spell_purged before/at displayed step → hidden;
            # spell_purged after displayed step → still alive but rendered
            # as a non-interactive "ghost" cell.  We deliberately do NOT
            # rewrite ``status`` to 'available' here — earlier revisions
            # did that and allowed the player to click a tactic that the
            # server already considered purged, producing a mismatch
            # between the spell-replay overlay and live actions.
            if status == 'spell_purged':
                if discarded is None or int(discarded) <= displayed:
                    continue
                replay = dict(t)
                replay['_render_ghost'] = True
                replay.pop('discarded_step_index', None)
                out.append(replay)
                continue
            out.append(t)
        return out

    def _current_conquer_opponent_tactics(self):
        game = self.state.game
        if not game or not self._is_tactics_hand_game():
            return []
        game_id = getattr(game, 'game_id', None)
        player_id = getattr(game, 'player_id', None)
        if not game_id or not player_id:
            return self._filter_conquer_tactics_by_displayed_step([
                dict(move)
                for move in (getattr(game, 'conquer_opponent_tactics', []) or [])
                if isinstance(move, dict)
            ])

        cache_key = self._battle_state_cache_key()
        if cache_key != getattr(self, '_conquer_opponent_tactic_cache_key', None):
            reveal = self._own_all_seeing_eye_active()
            tactics = []
            for tactic in (getattr(game, 'conquer_tactics', []) or []):
                if not isinstance(tactic, dict):
                    continue
                if self._ids_equal(tactic.get('player_id'), player_id):
                    continue
                if (tactic.get('status') == 'played'
                        or tactic.get('played_round') is not None
                        # All Seeing Eye: the server already sent full data —
                        # don't re-redact it client-side.
                        or (reveal and tactic.get('rank') and tactic.get('suit'))):
                    tactics.append(dict(tactic))
                else:
                    tactics.append({
                        'id': tactic.get('id'),
                        'game_id': tactic.get('game_id'),
                        'player_id': tactic.get('player_id'),
                        'status': tactic.get('status'),
                        'played_round': None,
                        'revealed_step_index': tactic.get('revealed_step_index'),
                        'discarded_step_index': tactic.get('discarded_step_index'),
                    })
            if tactics:
                return self._filter_conquer_tactics_by_displayed_step(tactics)
        return self._filter_conquer_tactics_by_displayed_step(
            list(getattr(self, '_conquer_opponent_tactic_cache', []) or []))

    def _own_all_seeing_eye_active(self):
        """True when the player's own All Seeing Eye currently reveals the
        opponent's hand/tactics — gated on the timeline (see
        :meth:`_conquer_all_seeing_eye_revealed`)."""
        return self._conquer_all_seeing_eye_revealed()

    def _conquer_all_seeing_eye_revealed(self):
        """True when the player's own All Seeing Eye reveal should be visible.

        Gated on the timeline: during the pre-battle prelude replay the
        reveal only activates once the All Seeing Eye step becomes active or
        has passed.  Once the battle proper begins (replay finished) it is
        always revealed.
        """
        game = self.state.game
        if game is None:
            return False
        ase_check = getattr(game, 'has_active_all_seeing_eye', None)
        if not callable(ase_check) or not ase_check():
            return False
        # Battle underway / finished → the prelude replay is done.
        if getattr(game, 'battle_confirmed', False) or self._is_battle_phase_active():
            return True
        panel = getattr(self, '_conquer_timeline_panel', None)
        if panel is None:
            return True
        try:
            steps = panel.derive_display_steps(self) or []
        except Exception:
            return True
        active_idx = None
        ase_idx = None
        for idx, step in enumerate(steps):
            if active_idx is None and getattr(step, 'active', False):
                active_idx = idx
            if (ase_idx is None
                    and getattr(step, 'kind', '') == 'prelude_own'
                    and getattr(step, 'icon_payload', None) == 'All Seeing Eye'):
                ase_idx = idx
        if ase_idx is None:
            return True  # step not on the timeline → don't over-hide
        if active_idx is None:
            return True  # replay finished, nothing active → revealed
        # Revealed once the leading step reaches or passes the ASE cast.
        return active_idx >= ase_idx

    def _current_conquer_battle_moves(self):
        game = self.state.game
        if not game:
            return []
        if self._is_tactics_hand_game():
            return self._current_conquer_tactics()

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
        suit_size = max(13 if settings.TOUCH_TARGET_MIN > 0 else 8,
                        int(icon_size * 0.24))
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

        # The power number inside the move icon is the single most-read
        # value in the rail cells and ledger chips. Icon-proportional sizing
        # bottoms out around 10px on the mobile canvas (~8 CSS px after the
        # phone downscale), so mobile floors it at the LABEL tier — the
        # badge ellipse sizes itself from the text, so it simply grows.
        power_floor = (settings.FS_CONQUER_LABEL
                       if settings.TOUCH_TARGET_MIN > 0 else 10)
        font = settings.get_font(
            max(power_floor, int(icon_size * 0.28)), bold=True)
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
        title_budget = rect.width - layout['pad'] * 2
        fitted = self._fit_text(count_text, title_font, title_budget)
        if fitted != count_text:
            # Narrow panel: an ellipsized "Moves…" hides the count, which is
            # the whole point of the title — show the bare count instead.
            fitted = self._fit_text(
                f'{len(moves)}/{self.CONQUER_BATTLE_MOVE_PANEL_MAX_MOVES}',
                title_font, title_budget)
        title = title_font.render(fitted, True, (238, 218, 170))
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
                is_used=False,
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

    @staticmethod
    def _id_key(value):
        return None if value is None else str(value)

    @classmethod
    def _ids_equal(cls, left, right):
        left_key = cls._id_key(left)
        right_key = cls._id_key(right)
        return left_key is not None and left_key == right_key

    def _conquer_lane_figures(self):
        game = self.state.game
        field = self.subscreens.get('field') if hasattr(self, 'subscreens') else None
        figures = getattr(field, 'figures', []) or []
        if not game or not figures or not self._is_battle_phase_active():
            return [], []

        by_id = {str(getattr(fig, 'id', None)): fig for fig in figures}

        def pick(*ids):
            picked = []
            seen = set()
            for fig_id in ids:
                if fig_id is None or fig_id in seen:
                    continue
                key = str(fig_id)
                if key in seen:
                    continue
                seen.add(key)
                fig = by_id.get(key)
                if fig is not None:
                    picked.append(fig)
            return picked

        advancing = pick(
            getattr(game, 'advancing_figure_id', None),
            getattr(game, 'advancing_figure_id_2', None),
        )
        defending = pick(
            getattr(game, 'defending_figure_id', None),
            getattr(game, 'defending_figure_id_2', None),
        )
        player_id = getattr(game, 'player_id', None)
        opponent = getattr(game, 'opponent_player', None)
        opponent_id = getattr(game, 'opponent_id', None)
        if opponent_id is None and isinstance(opponent, dict):
            opponent_id = opponent.get('id')

        def owned_by_player(fig):
            owner_id = getattr(fig, 'player_id', None)
            return (owner_id is None or player_id is None
                    or self._ids_equal(owner_id, player_id))

        def owned_by_opponent(fig):
            owner_id = getattr(fig, 'player_id', None)
            if owner_id is None:
                return True
            if opponent_id is not None:
                return self._ids_equal(owner_id, opponent_id)
            return player_id is None or not self._ids_equal(owner_id, player_id)

        if self._ids_equal(getattr(game, 'advancing_player_id', None),
                           getattr(game, 'player_id', None)):
            player_figures, opponent_figures = advancing, defending
        else:
            player_figures, opponent_figures = defending, advancing
        return (
            [fig for fig in player_figures if owned_by_player(fig)],
            [fig for fig in opponent_figures if owned_by_opponent(fig)],
        )

    def _conquer_lane_context_key(self):
        game = self.state.game
        if not game:
            return None
        field = self.subscreens.get('field') if hasattr(self, 'subscreens') else None
        figures = getattr(field, 'figures', []) or []

        figure_rows = []
        for figure in figures:
            family = getattr(figure, 'family', None)
            figure_rows.append((
                getattr(figure, 'id', None),
                getattr(figure, 'player_id', None),
                getattr(figure, 'suit', None),
                getattr(family, 'field', None),
                bool(getattr(figure, 'has_deficit', False)),
                bool(getattr(figure, '_conquer_timeline_snapshot', False)),
            ))

        def tactic_rows(tactics):
            rows = []
            for tactic in tactics or []:
                if not isinstance(tactic, dict):
                    continue
                rows.append((
                    tactic.get('id'),
                    tactic.get('player_id'),
                    tactic.get('status'),
                    tactic.get('played_round'),
                    tactic.get('call_figure_id'),
                    tactic.get('family_name'),
                    tactic.get('suit'),
                    tactic.get('suit_b'),
                    tactic.get('rank'),
                    tactic.get('value'),
                ))
            return tuple(rows)

        skipped = getattr(game, 'battle_skipped_rounds', None) or {}
        skipped_rows = tuple(sorted(
            (str(pid), tuple(rounds or []))
            for pid, rounds in skipped.items()
        )) if isinstance(skipped, dict) else ()

        sequencer = getattr(self, '_conquer_reveal_sequencer', None)
        reveal_version = sequencer.display_version() if sequencer is not None else 0

        return (
            getattr(game, 'game_id', None),
            getattr(game, 'player_id', None),
            getattr(game, '_game_data_version', 0),
            getattr(game, '_figures_data_version', 0),
            getattr(game, 'battle_turn_player_id', None),
            getattr(game, 'battle_round', None),
            bool(getattr(game, 'last_battle_result', None)),
            getattr(game, 'advancing_player_id', None),
            getattr(game, 'advancing_figure_id', None),
            getattr(game, 'advancing_figure_id_2', None),
            getattr(game, 'defending_figure_id', None),
            getattr(game, 'defending_figure_id_2', None),
            getattr(game, 'land_suit_bonus_suit', None),
            getattr(game, 'land_suit_bonus_value', None),
            skipped_rows,
            reveal_version,
            tuple(figure_rows),
            tactic_rows(self._current_conquer_tactics()),
            tactic_rows(self._current_conquer_opponent_tactics()),
        )

    def _conquer_lane_context_fast_key(self):
        game = self.state.game
        if not game:
            return None
        field = self.subscreens.get('field') if hasattr(self, 'subscreens') else None
        figures = getattr(field, 'figures', None)
        tactics = getattr(game, 'conquer_tactics', None)
        try:
            displayed_step = self._displayed_conquer_step()
        except Exception:
            displayed_step = None
        sequencer = getattr(self, '_conquer_reveal_sequencer', None)
        reveal_version = sequencer.display_version() if sequencer is not None else 0
        return (
            getattr(game, 'game_id', None),
            getattr(game, 'player_id', None),
            getattr(game, '_game_data_version', 0),
            getattr(game, '_figures_data_version', 0),
            reveal_version,
            id(figures),
            len(figures or []),
            id(tactics),
            len(tactics or []),
            getattr(game, 'battle_turn_player_id', None),
            getattr(game, 'battle_round', None),
            bool(getattr(game, 'last_battle_result', None)),
            getattr(game, 'advancing_player_id', None),
            getattr(game, 'advancing_figure_id', None),
            getattr(game, 'advancing_figure_id_2', None),
            getattr(game, 'defending_figure_id', None),
            getattr(game, 'defending_figure_id_2', None),
            getattr(game, 'land_suit_bonus_suit', None),
            getattr(game, 'land_suit_bonus_value', None),
            getattr(self, '_conquer_tactic_cache_key', None),
            getattr(self, '_conquer_opponent_tactic_cache_key', None),
            self._conquer_tactic_cache_signature(
                getattr(self, '_conquer_tactic_cache', None)),
            self._conquer_tactic_cache_signature(
                getattr(self, '_conquer_opponent_tactic_cache', None)),
            displayed_step,
        )

    @staticmethod
    def _conquer_tactic_cache_signature(tactics):
        rows = []
        for tactic in tactics or []:
            if not isinstance(tactic, dict):
                continue
            rows.append((
                tactic.get('id'),
                tactic.get('player_id'),
                tactic.get('status'),
                tactic.get('played_round'),
                tactic.get('call_figure_id'),
                tactic.get('family_name'),
                tactic.get('suit'),
                tactic.get('suit_b'),
                tactic.get('rank'),
                tactic.get('value'),
                tactic.get('revealed_step_index'),
                tactic.get('discarded_step_index'),
            ))
        return tuple(rows)

    def _conquer_lane_context(self):
        fast_key = self._conquer_lane_context_fast_key()
        if fast_key == getattr(self, '_conquer_lane_context_fast_cache_key', None):
            cached = getattr(self, '_conquer_lane_context_cache', None)
            if cached is not None:
                return cached
        key = self._conquer_lane_context_key()
        if key is None:
            return {
                'key': None,
                'player_figures': [],
                'opponent_figures': [],
                'player_slots': [None, None, None],
                'opponent_slots': [None, None, None],
                'player_support': [],
                'opponent_support': [],
                'player_support_ids': set(),
                'opponent_support_ids': set(),
                'involved_ids': set(),
            }
        if key == getattr(self, '_conquer_lane_context_cache_key', None):
            cached = getattr(self, '_conquer_lane_context_cache', None)
            if cached is not None:
                return cached

        player_figures, opponent_figures = self._conquer_lane_figures()
        player_slots, opponent_slots = self._conquer_lane_played_tactics()
        played_slots = (player_slots, opponent_slots)
        player_support = self._conquer_lane_support_entries(
            player_figures, opponent_figures, is_player=True,
            played_slots=played_slots)
        opponent_support = self._conquer_lane_support_entries(
            player_figures, opponent_figures, is_player=False,
            played_slots=played_slots)

        def support_ids(entries):
            ids = set()
            for entry in entries or []:
                figure = entry.get('figure') if isinstance(entry, dict) else None
                fig_id = getattr(figure, 'id', None)
                if fig_id is not None:
                    ids.add(fig_id)
                for source_id in (entry.get('source_figure_ids') or []) if isinstance(entry, dict) else []:
                    if source_id is not None:
                        ids.add(source_id)
            return ids

        player_support_ids = support_ids(player_support)
        opponent_support_ids = support_ids(opponent_support)
        involved_ids = set(self._conquer_lane_battle_figure_ids())
        involved_ids.update(player_support_ids)
        involved_ids.update(opponent_support_ids)
        context = {
            'key': key,
            'player_figures': player_figures,
            'opponent_figures': opponent_figures,
            'player_slots': player_slots,
            'opponent_slots': opponent_slots,
            'player_support': player_support,
            'opponent_support': opponent_support,
            'player_support_ids': player_support_ids,
            'opponent_support_ids': opponent_support_ids,
            'involved_ids': involved_ids,
        }
        self._conquer_lane_context_cache_key = key
        self._conquer_lane_context_fast_cache_key = fast_key
        self._conquer_lane_context_cache = context
        if key != getattr(self, '_conquer_tactic_power_cache_key', None):
            self._conquer_tactic_power_cache_key = key
            self._conquer_tactic_power_cache = {}
        return context

    @staticmethod
    def _conquer_lane_figure_power(figure):
        getter = getattr(figure, 'get_value', None)
        if callable(getter):
            try:
                return int(getter() or 0)
            except Exception:
                pass
        number_card = getattr(figure, 'number_card', None)
        if number_card is not None and getattr(number_card, 'value', None) is not None:
            return int(getattr(number_card, 'value', 0) or 0)
        return int(getattr(figure, 'value', 0) or 0)

    @staticmethod
    def _conquer_lane_move_power(move):
        if not move or move.get('_skipped') or move.get('family_name') == 'Skip':
            return 0
        if move.get('family_name') == 'Block':
            return 0
        return int(move.get('value') or 0)

    @staticmethod
    def _conquer_lane_move_name(move):
        if not move:
            return 'Pending'
        name = move.get('family_name') or move.get('family') or 'Tactic'
        if name == 'Dagger' and (move.get('card_id_b') or move.get('secondary_card_id')):
            return '2x Dagger'
        return str(name)

    def _conquer_lane_played_tactics(self):
        """Gated view of the per-round played tactics.

        Freshly-completed rounds stay hidden (opponent slot ``None``)
        until the reveal sequencer plays its FLIP beat. All display
        consumers — ledger, duel lane, timeline — read this method;
        the sequencer itself reads the raw variant below.
        """
        player_slots, opponent_slots = self._conquer_lane_played_tactics_raw()
        sequencer = getattr(self, '_conquer_reveal_sequencer', None)
        if sequencer is None:
            return player_slots, opponent_slots
        try:
            return sequencer.gate_slots(player_slots, opponent_slots)
        except Exception:
            return player_slots, opponent_slots

    def _conquer_lane_played_tactics_raw(self):
        game = self.state.game
        player_slots = [None, None, None]
        opponent_slots = [None, None, None]

        def skipped_slot(round_idx, player_id=None):
            return {
                'family_name': 'Skip',
                'value': 0,
                'suit': '',
                '_skipped': True,
                'played_round': round_idx,
                'player_id': player_id,
            }

        def add_skipped(slots, player_id):
            if game is None or player_id is None:
                return
            skipped = getattr(game, 'battle_skipped_rounds', None) or {}
            for raw_round in skipped.get(str(player_id), []) or []:
                try:
                    round_idx = int(raw_round)
                except (TypeError, ValueError):
                    continue
                if round_idx in (0, 1, 2) and slots[round_idx] is None:
                    slots[round_idx] = skipped_slot(round_idx, player_id)

        try:
            player_moves = self._current_conquer_tactics() or []
        except Exception:
            player_moves = []
        for move in player_moves:
            played_round = move.get('played_round') if isinstance(move, dict) else None
            if played_round in (0, 1, 2):
                player_slots[played_round] = move

        battle = self.subscreens.get('battle') if hasattr(self, 'subscreens') else None
        opp_played = getattr(battle, 'opp_played', None) if battle is not None else None
        if isinstance(opp_played, list):
            for idx, move in enumerate(opp_played[:3]):
                if move:
                    opponent_slots[idx] = move

        try:
            opponent_tactics = self._current_conquer_opponent_tactics() or []
        except Exception:
            opponent_tactics = []
        for move in opponent_tactics:
            if not isinstance(move, dict):
                continue
            played_round = move.get('played_round')
            if played_round in (0, 1, 2):
                opponent_slots[played_round] = move

        player_id = getattr(game, 'player_id', None) if game is not None else None
        add_skipped(player_slots, player_id)

        opponent_ids = []
        if game is not None:
            for player in getattr(game, 'players', []) or []:
                pid = player.get('id') if isinstance(player, dict) else getattr(player, 'id', None)
                if pid is not None and not self._ids_equal(pid, player_id):
                    opponent_ids.append(pid)
            skipped = getattr(game, 'battle_skipped_rounds', None) or {}
            for raw_pid in skipped.keys():
                if str(raw_pid) != str(player_id):
                    opponent_ids.append(raw_pid)
        seen_opponents = set()
        for opponent_id in opponent_ids:
            key = str(opponent_id)
            if key in seen_opponents:
                continue
            seen_opponents.add(key)
            add_skipped(opponent_slots, opponent_id)

        return player_slots, opponent_slots

    def _conquer_lane_focus_round(self, player_slots, opponent_slots):
        game = self.state.game
        current = int(getattr(game, 'battle_round', 0) or 0) if game else -1
        if current in (0, 1, 2):
            return current
        for idx in (2, 1, 0):
            if player_slots[idx] or opponent_slots[idx]:
                return idx
        return 0

    def _conquer_lane_preview_move(self, player_slots, round_idx):
        game = self.state.game
        if (not game or round_idx not in (0, 1, 2)
                or getattr(game, 'last_battle_result', None)):
            return None
        if player_slots[round_idx] is not None:
            return None
        current = int(getattr(game, 'battle_round', 0) or 0)
        if current != round_idx:
            return None
        rail = getattr(self, '_tactics_rail', None)
        preview = getattr(rail, 'preview_move', None)
        if not callable(preview):
            return None
        move = preview()
        if not isinstance(move, dict):
            return None
        if move.get('played_round') is not None:
            return None
        if move.get('status', 'available') != 'available':
            return None
        return move

    def _conquer_lane_all_figures(self):
        field = self.subscreens.get('field') if hasattr(self, 'subscreens') else None
        return list(getattr(field, 'figures', []) or [])

    def _conquer_lane_battle_figure_ids(self):
        game = self.state.game
        if not game or not self._is_battle_phase_active():
            return set()
        ids = set()
        for attr in (
                'advancing_figure_id', 'advancing_figure_id_2',
                'defending_figure_id', 'defending_figure_id_2'):
            fig_id = getattr(game, attr, None)
            if fig_id is not None:
                ids.add(fig_id)
        return ids

    def _conquer_battle_involved_figure_ids(self):
        """Set of figure ids that contribute to the current battle.

        Includes the advancing/defending pair plus every figure that
        appears as a support source (call / buff / block / distance /
        healer) on either side. Used to grey-out non-involved field
        figures (#4).
        """
        ids = set(self._conquer_lane_battle_figure_ids())
        try:
            context = self._conquer_lane_context()
        except Exception:
            return ids
        involved = context.get('involved_ids')
        if involved:
            return set(involved)
        return ids

    def conquer_active_support_figure_ids(self, *, opponent_only=False):
        """Return cached support-source figure ids for the active battle."""
        try:
            context = self._conquer_lane_context()
        except Exception:
            return set()
        if opponent_only:
            return set(context.get('opponent_support_ids') or set())
        ids = set(context.get('player_support_ids') or set())
        ids.update(context.get('opponent_support_ids') or set())
        return ids

    def _update_conquer_battle_dim_flags(self):
        """Mark every field figure not involved in the current battle as
        ``conquer_battle_dimmed = True`` so FieldFigureIcon renders it
        greyed out (#4)."""
        if not self._is_battle_phase_active():
            field = self.subscreens.get('field') if hasattr(self, 'subscreens') else None
            for icon in getattr(field, 'figure_icons', []) or []:
                if hasattr(icon, 'conquer_battle_dimmed'):
                    icon.conquer_battle_dimmed = False
            return
        involved = self._conquer_battle_involved_figure_ids()
        field = self.subscreens.get('field') if hasattr(self, 'subscreens') else None
        icons = getattr(field, 'figure_icons', []) or []
        involved_keys = {str(fig_id) for fig_id in involved if fig_id is not None}
        # Defensive guard against the "all-grey flicker": when the poller
        # just applied a new game state, ``advancing_figure_id`` /
        # ``defending_figure_id`` may already point at the new battle pair
        # while ``field.figure_icons`` still holds the previous frame's
        # figures (the field rebuilds via ``load_figures`` on the next
        # tick). In that one-frame window, the involved-id set has no
        # overlap with any icon and every figure would get dimmed,
        # producing a visible all-grey flash every poll cycle. If the
        # involved set is non-empty but none of the current icons match,
        # leave the existing dim flags alone for this frame.
        if involved_keys:
            current_ids = {getattr(getattr(icon, 'figure', None), 'id', None)
                           for icon in icons}
            current_ids.discard(None)
            current_keys = {str(fig_id) for fig_id in current_ids}
            if current_keys and involved_keys.isdisjoint(current_keys):
                return
        for icon in icons:
            fig = getattr(icon, 'figure', None)
            fig_id = getattr(fig, 'id', None)
            icon.conquer_battle_dimmed = bool(
                fig_id is not None and str(fig_id) not in involved_keys)

    def _apply_conquer_support_hover_visibility(self):
        """Force every opponent figure backing the currently-hovered
        support badge to be face-up for this frame (round 10 #7)."""
        self._conquer_support_hover_visibility_restore = []
        hovered = getattr(self, '_conquer_hovered_support_badge', None)
        if not hovered:
            return
        target_ids = set()
        primary_id = hovered.get('figure_id')
        if primary_id is not None:
            target_ids.add(primary_id)
        for sid in hovered.get('source_figure_ids') or []:
            if sid is not None:
                target_ids.add(sid)
        if not target_ids:
            return
        field = self.subscreens.get('field') if hasattr(self, 'subscreens') else None
        for icon in getattr(field, 'figure_icons', []) or []:
            fig = getattr(icon, 'figure', None)
            if getattr(fig, 'id', None) not in target_ids:
                continue
            if not getattr(icon, 'is_visible', True):
                self._conquer_support_hover_visibility_restore.append(icon)
                icon.is_visible = True

    def _restore_conquer_support_hover_visibility(self):
        for icon in getattr(self, '_conquer_support_hover_visibility_restore', []) or []:
            icon.is_visible = False
        self._conquer_support_hover_visibility_restore = []

    @staticmethod
    def _conquer_lane_family_field(figure):
        family = getattr(figure, 'family', None)
        return str(getattr(family, 'field', None) or getattr(figure, 'field', '') or '').lower()

    @staticmethod
    def _conquer_lane_has_skill(figure, skill_key):
        getter = getattr(figure, 'get_active_skill_keys', None)
        if callable(getter):
            try:
                return skill_key in set(getter() or [])
            except Exception:
                return False
        family = getattr(figure, 'family', None)
        return bool(getattr(figure, skill_key, False) or getattr(family, skill_key, False))

    def _conquer_lane_active_skill_keys(self, figure):
        getter = getattr(figure, 'get_active_skill_keys', None)
        if callable(getter):
            try:
                keys = [key for key in getter() or [] if key in SKILL_DEFINITIONS]
                if keys:
                    return keys
            except Exception:
                return []
        keys = []
        for skill_key in (
                'support_bonus', 'buffs_allies', 'buffs_allies_defence',
                'blocks_bonus', 'distance_attack'):
            if skill_key in SKILL_DEFINITIONS and self._conquer_lane_has_skill(figure, skill_key):
                keys.append(skill_key)
        return keys

    @staticmethod
    def _conquer_lane_number_value(figure):
        number_card = getattr(figure, 'number_card', None)
        if number_card is not None and getattr(number_card, 'value', None) is not None:
            return int(getattr(number_card, 'value', 0) or 0)
        return ConquerGameScreen._conquer_lane_figure_power(figure)

    @staticmethod
    def _conquer_lane_regular_support_value(figure):
        getter = getattr(figure, 'get_battle_bonus', None)
        if callable(getter):
            try:
                return int(getter() or 0)
            except Exception:
                pass
        field = ConquerGameScreen._conquer_lane_family_field(figure)
        if field == 'castle':
            name = str(getattr(figure, 'name', '') or '')
            return 5 if 'maharaja' in name.lower() else 4
        return ConquerGameScreen._conquer_lane_number_value(figure)

    @staticmethod
    def _conquer_lane_valid_support_fields(target):
        field = ConquerGameScreen._conquer_lane_family_field(target)
        if field == 'castle':
            return {'castle'}
        if field == 'village':
            return {'castle'}
        if field == 'military':
            return {'castle', 'village'}
        return set()

    def _conquer_lane_is_defending_side(self, *, is_player):
        game = self.state.game
        if not game:
            return False
        player_id = getattr(game, 'player_id', None)
        advancing_player_id = getattr(game, 'advancing_player_id', None)
        if player_id is None or advancing_player_id is None:
            return False
        if is_player:
            return not self._ids_equal(advancing_player_id, player_id)
        return self._ids_equal(advancing_player_id, player_id)

    def _conquer_lane_support_entries(self, player_figures, opponent_figures, *,
                                      is_player, played_slots=None):
        game = self.state.game
        if not game:
            return []
        player_id = getattr(game, 'player_id', None)
        opponent = getattr(game, 'opponent_player', None)
        opponent_id = getattr(game, 'opponent_id', None)
        if opponent_id is None and isinstance(opponent, dict):
            opponent_id = opponent.get('id')
        side_player_id = player_id if is_player else opponent_id
        if side_player_id is None:
            battle_figs = player_figures if is_player else opponent_figures
            if battle_figs:
                side_player_id = getattr(battle_figs[0], 'player_id', None)
        if side_player_id is None:
            return []

        own_targets = player_figures if is_player else opponent_figures
        enemy_targets = opponent_figures if is_player else player_figures
        battle_ids = self._conquer_lane_battle_figure_ids()
        battle_id_keys = {
            self._id_key(fig_id) for fig_id in battle_ids if fig_id is not None
        }
        entries = []
        seen = set()

        def add(kind, figure, label, value_text, numeric_value=0,
                target_figure_ids=None, per_target_value=None, *,
                section='clash', round_idx=None, move=None, suit=None,
            source_figure_ids=None, target_suit=None,
            suit_match_bonus=0):
            key = (kind, getattr(figure, 'id', None))
            if kind in {'called', 'land_bonus'}:
                key = (kind, getattr(figure, 'id', None), round_idx, suit)
            if key in seen:
                return
            seen.add(key)
            default_source_ids = []
            fig_id = getattr(figure, 'id', None)
            if fig_id is not None:
                default_source_ids.append(fig_id)
            entries.append({
                'kind': kind,
                'figure': figure,
                'label': label,
                'value': value_text,
                'numeric_value': int(numeric_value or 0),
                'target_figure_ids': list(target_figure_ids or []),
                'per_target_value': int(
                    numeric_value if per_target_value is None else per_target_value),
                'section': section,
                'round_idx': round_idx,
                'move': move,
                'suit': suit or getattr(figure, 'suit', None),
                'target_suit': target_suit,
                'source_figure_ids': list(
                    default_source_ids if source_figure_ids is None else source_figure_ids),
                'suit_match_bonus': int(suit_match_bonus or 0),
            })

        for figure in self._conquer_lane_all_figures():
            if not self._ids_equal(getattr(figure, 'player_id', None), side_player_id):
                continue
            fig_id = getattr(figure, 'id', None)
            in_battle = self._id_key(fig_id) in battle_id_keys
            if getattr(figure, 'has_deficit', False):
                continue
            suit = getattr(figure, 'suit', None)
            adv_suit = get_advantage_suit(suit) if suit else None
            source_field = self._conquer_lane_family_field(figure)

            if not in_battle and source_field in {'castle', 'village'}:
                support_targets = [
                    target for target in own_targets
                    if getattr(target, 'id', None) != fig_id
                    and getattr(target, 'suit', None) == suit
                    and source_field in self._conquer_lane_valid_support_fields(target)
                ]
                if support_targets:
                    per_target = self._conquer_lane_regular_support_value(figure)
                    support_value = per_target * len(support_targets)
                    if support_value:
                        add('support_bonus', figure, 'Support',
                            f'+{support_value}', support_value,
                            target_figure_ids=[getattr(t, 'id', None) for t in support_targets],
                            per_target_value=per_target,
                            target_suit=suit)

            if not in_battle and self._conquer_lane_has_skill(figure, 'buffs_allies'):
                buff_targets = [
                    target for target in own_targets
                    if self._conquer_lane_family_field(target) == 'village'
                    and getattr(target, 'suit', None) == suit
                ]
                if buff_targets:
                    add('buffs_allies', figure, 'Buff', '+4',
                        4 * len(buff_targets),
                        target_figure_ids=[getattr(t, 'id', None) for t in buff_targets],
                        per_target_value=4,
                        target_suit=suit)

            if (not in_battle
                    and self._conquer_lane_has_skill(figure, 'buffs_allies_defence')
                    and self._conquer_lane_is_defending_side(is_player=is_player)):
                value = self._conquer_lane_number_value(figure)
                add('buffs_allies_defence', figure, 'Wall', f'+{value}',
                    value * len(own_targets),
                    target_figure_ids=[getattr(t, 'id', None) for t in own_targets],
                    per_target_value=value)

            if self._conquer_lane_has_skill(figure, 'blocks_bonus') and adv_suit:
                block_targets = [
                    target for target in enemy_targets
                    if getattr(target, 'suit', None) == adv_suit
                ]
                if block_targets:
                    add('blocks_bonus', figure, 'Block', 'Block',
                        target_figure_ids=[getattr(t, 'id', None) for t in block_targets],
                        target_suit=adv_suit)

            if (not in_battle
                    and self._conquer_lane_has_skill(figure, 'distance_attack') and adv_suit):
                da_targets = [t for t in enemy_targets if getattr(t, 'suit', None) == adv_suit]
                if da_targets:
                    value = self._conquer_lane_number_value(figure)
                    add('distance_attack', figure, 'Range', f'-{value}',
                        value, target_figure_ids=[getattr(t, 'id', None) for t in da_targets],
                        per_target_value=value,
                        target_suit=adv_suit)

        # Land bonus is not sourced by a figure, but belongs in the same
        # visible clash-support lane as the other always-on modifiers.
        # Landslide flips it to a malus for matching figures (both sides).
        land_suit, land_bonus = self._conquer_effective_land_bonus(game)
        if land_suit and land_bonus:
            land_targets = [
                target for target in own_targets
                if getattr(target, 'suit', None) == land_suit
            ]
            if land_targets:
                per_target = int(land_bonus)
                total = per_target * len(land_targets)
                add(
                    'land_bonus', None, 'Land', f'{total:+d}',
                    total,
                    target_figure_ids=[getattr(t, 'id', None) for t in land_targets],
                    per_target_value=per_target,
                    suit=land_suit,
                    source_figure_ids=[],
                )

        # Called figures: any figure referenced as call_figure_id on this
        # side's currently-played tactics (#1 — show called figures in the
        # support lane even when they are not "boosting" the lane sum).
        if played_slots is None:
            try:
                player_slots, opponent_slots = self._conquer_lane_played_tactics()
            except Exception:
                player_slots, opponent_slots = ([], [])
        else:
            player_slots, opponent_slots = played_slots
        side_slots = player_slots if is_player else opponent_slots
        for idx, move in enumerate(side_slots or []):
            if not isinstance(move, dict):
                continue
            cf_id = move.get('call_figure_id')
            if cf_id is None:
                continue
            cf = self._conquer_lane_find_figure(cf_id)
            if cf is None or getattr(cf, 'id', None) in battle_ids:
                continue
            label = self._conquer_lane_move_name(move) or 'Call'
            call_power = self._conquer_lane_call_effective_power(
                move, cf, support_entries=entries)
            # Suit-match bonus: when the call tactic's suit matches the
            # called figure's suit, the move's base value stacks on top of
            # the figure's power. Expose it so the badge can highlight it.
            suit_match_bonus = 0
            if (str(getattr(cf, 'suit', '') or '').lower()
                    == str(move.get('suit') or '').lower()) and move.get('suit'):
                suit_match_bonus = self._conquer_lane_move_power(move)
            add('called', cf, label, f'+{call_power}' if call_power else '', call_power,
                target_figure_ids=[],
                per_target_value=0,
                section=f'round_{idx}',
                round_idx=idx,
                move=move,
                suit=move.get('suit') or getattr(cf, 'suit', None),
                suit_match_bonus=suit_match_bonus)

        order = {
            'support_bonus': 0,
            'buffs_allies': 1,
            'buffs_allies_defence': 2,
            'blocks_bonus': 3,
            'distance_attack': 4,
            'land_bonus': 5,
            'called': 6,
        }
        return sorted(entries, key=lambda e: (
            str(e.get('section') or 'clash'),
            order.get(e['kind'], 99),
            getattr(e.get('figure'), 'id', 0) or 0,
        ))

    def _conquer_lane_find_figure(self, figure_id):
        if figure_id is None:
            return None
        needle = str(figure_id)
        for figure in self._conquer_lane_all_figures():
            if str(getattr(figure, 'id', None)) == needle:
                return figure
        return None

    @staticmethod
    def _conquer_lane_enchantment_total(figures):
        total = 0
        for figure in figures or []:
            getter = getattr(figure, 'get_total_enchantment_modifier', None)
            if callable(getter):
                try:
                    total += int(getter() or 0)
                    continue
                except Exception:
                    pass
            for enchantment in getattr(figure, 'active_enchantments', []) or []:
                total += int(enchantment.get('power_modifier', 0) or 0)
        return total

    def _conquer_lane_modifier_chips(self, move, figures):
        chips = []
        call_figure = self._conquer_lane_find_figure(
            move.get('call_figure_id') if isinstance(move, dict) else None)
        if call_figure is not None:
            chips.append({'label': 'Call', 'value': f'+{self._conquer_lane_figure_power(call_figure)}'})

        game = self.state.game
        land_suit, land_bonus = self._conquer_effective_land_bonus(game)
        if land_suit and land_bonus and any(getattr(fig, 'suit', None) == land_suit for fig in figures or []):
            chips.append({'label': 'Land', 'value': f'{int(land_bonus):+d}'})

        enchant_total = self._conquer_lane_enchantment_total(figures)
        if enchant_total:
            chips.append({'label': 'Spell', 'value': f'{enchant_total:+d}'})
        return chips

    @staticmethod
    def _conquer_lane_surface(asset, size):
        if not isinstance(asset, pygame.Surface):
            return None
        return pygame.transform.smoothscale(asset, (size, size))

    @staticmethod
    def _conquer_lane_side_rail_inset(lane):
        return max(
            int(lane.you_support_badge_rail[2] or 0) + int(lane.you_support_chip_rail[2] or 0),
            int(lane.opp_support_badge_rail[2] or 0) + int(lane.opp_support_chip_rail[2] or 0),
        ) + 6

    def _conquer_lane_center_channel_rect(self, rect, lane):
        rect = pygame.Rect(rect)
        side_inset = self._conquer_lane_side_rail_inset(lane)
        return pygame.Rect(
            rect.left + side_inset,
            rect.top,
            max(20, rect.width - 2 * side_inset),
            rect.height,
        )

    #: Lane fighter entrance timing.
    LANE_ENTRANCE_MS = 460
    LANE_ENTRANCE_STAGGER_MS = 160

    def _stamp_conquer_lane_entrances(self, player_figures, opponent_figures):
        """Track lane fighters; stamp entrance records for new arrivals.

        Seeding contract (mirrors the reveal sequencer): the first sighting
        of an already-active battle seeds silently so rejoining a fight
        never replays the entrance.  ``_start_conquer_battle_countdown``
        resets the seen-set to empty on the live battle-start transition so
        the fighters enter *during* the countdown.
        """
        try:
            now = pygame.time.get_ticks()
            current = []
            for side_idx, figures in enumerate(
                    (player_figures or [], opponent_figures or [])):
                for slot_idx, fig in enumerate(figures[:2]):
                    fid = getattr(fig, 'id', None)
                    if fid is not None:
                        current.append((str(fid), side_idx, slot_idx))
            seen = self._conquer_lane_figure_seen
            if seen is None:
                # First sighting this game: seed without animating.
                self._conquer_lane_figure_seen = {fid for fid, _, _ in current}
                return
            for fid, side_idx, slot_idx in current:
                if fid in seen:
                    continue
                seen.add(fid)
                self._conquer_lane_figure_entrances[fid] = {
                    'started_at': (now
                                   + side_idx * self.LANE_ENTRANCE_STAGGER_MS
                                   + slot_idx * 80),
                    'is_player': side_idx == 0,
                }
        except Exception:
            pass

    def _conquer_lane_entrance_progress(self, figure, hit_rect=None):
        """Entrance progress for a lane fighter, or ``None`` when settled.

        Returns a float: ``<= 0`` while the (staggered) entrance has not
        started, ``0..1`` mid-flight.  On completion the record is popped
        and a one-shot landing pulse fires on ``hit_rect``.
        """
        entrances = getattr(self, '_conquer_lane_figure_entrances', None)
        if not entrances:
            return None
        fid = str(getattr(figure, 'id', None))
        rec = entrances.get(fid)
        if rec is None:
            return None
        now = pygame.time.get_ticks()
        t = (now - int(rec.get('started_at') or now)) / max(
            1, self.LANE_ENTRANCE_MS)
        if t < 1.0:
            return t
        entrances.pop(fid, None)
        effects = getattr(self, '_conquer_effects', None)
        if effects is not None and hit_rect is not None:
            color = ((120, 205, 220) if rec.get('is_player')
                     else (226, 145, 130))
            try:
                effects.spawn_rect_pulse(pygame.Rect(hit_rect), color,
                                         duration_ms=300, scale=0.75)
            except Exception:
                pass
        return None

    def _draw_conquer_lane_figure_art(self, figure, center, size, *,
                                      hovered=False):
        # When hovered, scale the whole composite up so the icon "responds"
        # like a normal figure icon.
        scale = 1.12 if hovered else 1.0
        size = max(1, int(size * scale))
        family = getattr(figure, 'family', None)
        # Frame image is designed for a figure inset of ~1/FRAME_FIGURE_SCALE
        # of the outer box. Match that so the frame doesn't visually swallow
        # the icon (was 0.58 → looked oversized).
        try:
            from config.figure_settings import FRAME_FIGURE_SCALE  # noqa: WPS433
            inset = 1.0 / max(1.05, float(FRAME_FIGURE_SCALE))
        except Exception:
            inset = 0.72
        # Shrink the outer frame slightly so it sits closer to the icon.
        frame_size = max(1, int(size * 0.86))
        icon_size = max(1, int(size * inset))
        frame = self._conquer_lane_surface(getattr(family, 'frame_img', None), frame_size)
        icon = self._conquer_lane_surface(
            getattr(family, 'icon_img', None) or getattr(family, 'icon_img_small', None),
            icon_size,
        )
        fallback_rect = pygame.Rect(0, 0, icon_size, icon_size)
        fallback_rect.center = center
        pygame.draw.circle(self.window, (43, 37, 30), center, frame_size // 2)
        pygame.draw.circle(self.window, (203, 176, 104), center, frame_size // 2, 2)
        if icon:
            self.window.blit(icon, icon.get_rect(center=center))
        else:
            pygame.draw.rect(self.window, (110, 94, 64), fallback_rect, border_radius=6)
        if frame:
            self.window.blit(frame, frame.get_rect(center=center))

    def _draw_conquer_lane_band(self, rect, label, figures, *, is_player,
                                support_entries=None,
                                enemy_support_entries=None):
        band = pygame.Rect(rect).inflate(-6, -4)
        if band.width <= 0 or band.height <= 0:
            return
        bg = (34, 44, 50, 165) if is_player else (52, 40, 43, 165)
        pygame.draw.rect(self.window, bg, band, border_radius=7)

        label_font = settings.get_font(settings.FS_CONQUER_LABEL, bold=True)
        text = label_font.render(label, True, (230, 222, 190))
        self.window.blit(text, (band.left + 8, band.top + 4))

        if not figures:
            dash = label_font.render('-', True, (150, 132, 96))
            self.window.blit(dash, dash.get_rect(center=band.center))
            return

        # Compute full-power for each figure on this side.  The active
        # battle renderer passes cached support entries because constructing
        # them walks the whole field + tactics state and is expensive on web.
        if support_entries is None or enemy_support_entries is None:
            player_figures, opponent_figures = self._conquer_lane_figures()
            if support_entries is None:
                support_entries = self._conquer_lane_support_entries(
                    player_figures, opponent_figures, is_player=is_player)
            if enemy_support_entries is None:
                enemy_support_entries = self._conquer_lane_support_entries(
                    player_figures, opponent_figures, is_player=not is_player)
        own_support = support_entries or []
        enemy_support = enemy_support_entries or []
        side_blocked = any(e.get('kind') == 'blocks_bonus' for e in enemy_support)

        # The battle math is the headline of this band: the figure's total
        # renders a full tier above its name and breakdown segments. The
        # name runs slightly under LABEL so common figure names still fit
        # the lane slot un-ellipsized.
        name_font = settings.get_font(
            max(settings.FS_CONQUER_META, int(settings.FS_TINY * 0.92)),
            bold=True)
        value_font = settings.get_font(settings.FS_CONQUER_SECONDARY, bold=True)
        count = min(2, len(figures))
        slot_w = max(1, band.width // count)
        max_art_size = max(34, min(int(band.height * 0.50), int(slot_w * 0.56)))
        rects = getattr(self, '_conquer_lane_figure_rects', None)
        if rects is None:
            rects = []
            self._conquer_lane_figure_rects = rects
        for idx, figure in enumerate(figures[:2]):
            slot = pygame.Rect(band.left + idx * slot_w, band.top, slot_w, band.height)
            metadata_icon_size = max(10, min(17, int(band.height * 0.12)))
            # Reserve a compact metadata row under the power pill.
            metadata_area = pygame.Rect(
                slot.left + 6,
                band.bottom - metadata_icon_size - 2,
                max(1, slot.width - 12),
                metadata_icon_size,
            )
            power_bottom_limit = metadata_area.top - 1
            name_center_y = min(
                band.top + int(band.height * 0.64),
                power_bottom_limit - value_font.get_height() - 5,
            )
            name_center_y = max(
                band.top + label_font.get_height() + 8,
                name_center_y,
            )
            art_top_limit = band.top + label_font.get_height() + 10
            art_bottom_limit = name_center_y - name_font.get_height() // 2 - 5
            art_size = max(30, min(max_art_size, max(30, (art_bottom_limit - art_top_limit) * 2)))
            center_y = min(
                band.top + int(band.height * 0.34),
                art_bottom_limit - art_size // 2,
            )
            center_y = max(art_top_limit + art_size // 2, center_y)
            center = (slot.centerx, center_y)
            # Hit rect for hover/click. Sized like the visible figure ring.
            hit = pygame.Rect(0, 0, art_size + 8, art_size + 8)
            hit.center = center
            mouse = pygame.mouse.get_pos()
            hovered = hit.collidepoint(mouse)
            # Fighter entrance: while entering, only the figure art draws —
            # scaling up into place with a small rise; the name/pills/badges
            # pop in with the landing pulse.  Hit rects stay at rest.
            entrance_t = self._conquer_lane_entrance_progress(figure, hit)
            if entrance_t is not None:
                if entrance_t > 0.0:
                    e_size = max(8, int(art_size * (
                        0.30 + 0.70 * ease_out_back(entrance_t))))
                    rise = int((1.0 - ease_out_quad(entrance_t))
                               * band.height * 0.20)
                    self._draw_conquer_lane_figure_art(
                        figure, (center[0], center[1] + rise), e_size)
                continue
            self._draw_conquer_lane_figure_art(figure, center, art_size,
                                               hovered=hovered)
            # Block visualization: red ring + small "BLOCKED" tag.
            if side_blocked:
                ring = pygame.Rect(0, 0, art_size + 10, art_size + 10)
                ring.center = center
                pygame.draw.rect(self.window, (210, 70, 70), ring, 3,
                                 border_radius=max(4, ring.height // 6))
                tag_font = settings.get_font(settings.FS_CONQUER_META, bold=True)
                tag = tag_font.render('BLOCKED', True, (252, 232, 222))
                tag_bg = tag.get_rect()
                tag_bg.inflate_ip(8, 4)
                tag_bg.midbottom = (center[0], center[1] + art_size // 2 + 2)
                pygame.draw.rect(self.window, (148, 38, 38), tag_bg,
                                 border_radius=max(2, tag_bg.height // 3))
                pygame.draw.rect(self.window, (24, 14, 12), tag_bg, 1,
                                 border_radius=max(2, tag_bg.height // 3))
                self.window.blit(tag, tag.get_rect(center=tag_bg.center))
            # Hit rect for opening detail box.
            rects.append({'rect': hit, 'figure': figure, 'is_player': is_player})

            name = self._fit_text(getattr(figure, 'name', 'Figure'), name_font, slot.width - 14)
            name_surf = name_font.render(name, True, (246, 239, 214))
            # Keep the name above the figure-power badge; the badge sits
            # directly below the name so neither overlaps the frame label.
            name_rect = name_surf.get_rect(center=(slot.centerx, name_center_y))
            self.window.blit(name_surf, name_rect)

            base = self._conquer_lane_figure_power(figure)
            total = self._conquer_lane_figure_full_power(
                figure,
                support_entries=own_support,
                enemy_support_entries=enemy_support,
                is_player=is_player,
            )
            breakdown = self._conquer_lane_figure_power_breakdown(
                figure,
                support_entries=own_support,
                enemy_support_entries=enemy_support,
                is_player=is_player,
            )
            # Segmented colour-coded pill (#2): [base|+buff|+spell|+sup] = total.
            # Anchored directly below the name so it no longer collides
            # with long figure labels (#round6). Segments stay a step under
            # the total so the full breakdown keeps fitting the slot width
            # (overflow falls back to a lone total chip, hiding the math).
            seg_font = settings.get_font(
                max(settings.FS_CONQUER_META, int(settings.FS_TINY * 0.78)),
                bold=True)
            total_color = (235, 250, 220) if total > base else (250, 230, 220) if total < base else (42, 32, 20)
            total_bg = (40, 110, 60) if total > base else (148, 50, 50) if total < base else (238, 206, 111)
            pill_anchor_y = min(name_rect.bottom + 2, power_bottom_limit - 2)
            power_badge_rect = None
            if len(breakdown) <= 1:
                value_surf = value_font.render(str(total), True, total_color)
                chip = value_surf.get_rect()
                chip.inflate_ip(14, 7)
                chip.midtop = (slot.centerx, pill_anchor_y)
                if chip.bottom > power_bottom_limit:
                    chip.bottom = power_bottom_limit
                power_badge_rect = pygame.Rect(chip)
                pygame.draw.rect(self.window, total_bg, chip, border_radius=chip.height // 2)
                pygame.draw.rect(self.window, (24, 18, 12), chip, 1, border_radius=chip.height // 2)
                self.window.blit(value_surf, value_surf.get_rect(center=chip.center))
            else:
                # Build segments and lay them out left-to-right with a
                # final total chip at the right edge.
                seg_surfaces = []
                for label, value in breakdown:
                    colour = self._conquer_receipt_label_color(label)
                    if label == 'Base':
                        text = f'{value}'
                    elif value < 0 or label == 'Range':
                        text = f'\u2212{abs(value)}'
                    else:
                        text = f'+{value}'
                    seg_surfaces.append((seg_font.render(text, True, (24, 18, 12)), colour))
                total_surf = value_font.render(f'={total}', True, total_color)
                pad_x = 4
                gap = 2
                total_w = sum(s.get_width() + 2 * pad_x for s, _ in seg_surfaces) + gap * len(seg_surfaces) + total_surf.get_width() + 2 * pad_x
                # Anchor directly below the figure name.
                pill_h = max(seg_font.get_height(), value_font.get_height()) + 6
                pill = pygame.Rect(0, 0, total_w + 4, pill_h)
                pill.midtop = (slot.centerx, pill_anchor_y)
                if pill.bottom > power_bottom_limit:
                    pill.bottom = power_bottom_limit
                # Clamp horizontally inside the slot.
                pill.left = max(slot.left + 2, min(pill.left, slot.right - pill.width - 2))
                # If still too wide, fall back to single total chip.
                if pill.width > slot.width - 4:
                    value_surf = value_font.render(str(total), True, total_color)
                    chip = value_surf.get_rect()
                    chip.inflate_ip(14, 7)
                    chip.midtop = (slot.centerx, pill_anchor_y)
                    if chip.bottom > power_bottom_limit:
                        chip.bottom = power_bottom_limit
                    power_badge_rect = pygame.Rect(chip)
                    pygame.draw.rect(self.window, total_bg, chip, border_radius=chip.height // 2)
                    pygame.draw.rect(self.window, (24, 18, 12), chip, 1, border_radius=chip.height // 2)
                    self.window.blit(value_surf, value_surf.get_rect(center=chip.center))
                else:
                    power_badge_rect = pygame.Rect(pill)
                    pygame.draw.rect(self.window, (22, 18, 12), pill, border_radius=pill.height // 2)
                    pygame.draw.rect(self.window, (24, 18, 12), pill, 1, border_radius=pill.height // 2)
                    x = pill.left + 2
                    for surf, colour in seg_surfaces:
                        seg_rect = pygame.Rect(x, pill.top + 2, surf.get_width() + 2 * pad_x, pill.height - 4)
                        pygame.draw.rect(self.window, colour, seg_rect, border_radius=seg_rect.height // 2)
                        self.window.blit(surf, surf.get_rect(center=seg_rect.center))
                        x = seg_rect.right + gap
                    total_rect = pygame.Rect(x, pill.top + 2, total_surf.get_width() + 2 * pad_x, pill.height - 4)
                    pygame.draw.rect(self.window, total_bg, total_rect, border_radius=total_rect.height // 2)
                    self.window.blit(total_surf, total_surf.get_rect(center=total_rect.center))
            if power_badge_rect is not None:
                metadata_top = min(
                    power_badge_rect.bottom + 1,
                    band.bottom - metadata_icon_size - 1,
                )
                metadata_area = pygame.Rect(
                    slot.left + 6,
                    metadata_top,
                    max(1, slot.width - 12),
                    metadata_icon_size,
                )
            self._draw_conquer_lane_figure_metadata(
                metadata_area, figure, is_player=is_player)

    def _load_conquer_skill_icon(self, skill_key, size):
        cache = getattr(self, '_conquer_skill_icon_cache', None)
        if cache is None:
            cache = {}
            self._conquer_skill_icon_cache = cache
        key = (skill_key, int(size))
        if key in cache:
            return cache[key]
        icon_path = SKILL_DEFINITIONS.get(skill_key, {}).get('icon')
        surf = None
        if icon_path:
            try:
                surf = pygame.image.load(icon_path).convert_alpha()
                surf = pygame.transform.smoothscale(surf, (int(size), int(size)))
            except Exception:
                surf = None
        cache[key] = surf
        return surf

    def _load_conquer_state_icon(self, icon_name, size):
        cache = getattr(self, '_conquer_state_icon_cache', None)
        if cache is None:
            cache = {}
            self._conquer_state_icon_cache = cache
        key = (icon_name, int(size))
        if key in cache:
            return cache[key]
        path = f'img/figures/state_icons/{icon_name}.png'
        surf = None
        try:
            surf = pygame.image.load(path).convert_alpha()
            surf = pygame.transform.smoothscale(surf, (int(size), int(size)))
        except Exception:
            surf = None
        cache[key] = surf
        return surf

    def _load_conquer_suit_icon(self, suit, size):
        if not suit:
            return None
        cache = getattr(self, '_conquer_suit_icon_cache', None)
        if cache is None:
            cache = {}
            self._conquer_suit_icon_cache = cache
        key = (str(suit).lower(), int(size))
        if key in cache:
            return cache[key]
        path = settings.SUIT_ICON_IMG_PATH + str(suit).lower() + '.png'
        surf = None
        try:
            surf = pygame.image.load(path).convert_alpha()
            surf = pygame.transform.smoothscale(surf, (int(size), int(size)))
        except Exception:
            surf = None
        cache[key] = surf
        return surf

    def _draw_conquer_call_family_icon(self, rect, move):
        family_name = move.get('family_name', '') if isinstance(move, dict) else ''
        icon_size = max(12, min(rect.width, rect.height))
        try:
            _glow_cache, icon_cache, _frame_cache, _suit_cache, _font = (
                self._conquer_battle_move_icon_assets(icon_size + 6))
            icon = icon_cache.get(family_name)
        except Exception:
            icon = None
        if icon:
            scale = min(
                max(1, rect.width) / max(1, icon.get_width()),
                max(1, rect.height) / max(1, icon.get_height()),
            )
            target_size = (
                max(1, int(icon.get_width() * scale)),
                max(1, int(icon.get_height() * scale)),
            )
            icon = pygame.transform.smoothscale(icon, target_size)
            self.window.blit(icon, icon.get_rect(center=rect.center))
            return
        pygame.draw.rect(self.window, (184, 142, 71), rect, border_radius=5)

    def _draw_conquer_lane_figure_metadata(self, area, figure, *, is_player):
        area = pygame.Rect(area)
        if area.width <= 0 or area.height <= 0:
            return

        icon_size = max(10, min(17, area.height - 2, area.width // 5))
        if icon_size <= 0:
            return
        gap = 3
        items = []
        suit = getattr(figure, 'suit', None)
        suit_icon = self._load_conquer_suit_icon(suit, icon_size)
        items.append(('suit', str(suit or ''), suit_icon))
        for skill_key in self._conquer_lane_active_skill_keys(figure):
            items.append((skill_key, SKILL_DEFINITIONS.get(skill_key, {}).get('label', skill_key),
                          self._load_conquer_skill_icon(skill_key, icon_size)))

        max_items = max(1, min(4, (area.width + gap) // (icon_size + gap)))
        visible = items[:max_items]
        overflow = max(0, len(items) - len(visible))
        total_w = len(visible) * icon_size + max(0, len(visible) - 1) * gap
        if overflow:
            count_font = settings.get_font(
                settings.FS_CONQUER_LABEL, bold=True)
            count_surf = count_font.render(f'+{overflow}', True, (246, 239, 214))
            count_w = max(icon_size, count_surf.get_width() + 6)
            total_w += gap + count_w
        x = area.centerx - total_w // 2
        y = area.centery - icon_size // 2
        bg_col = (22, 36, 34, 214) if is_player else (42, 28, 30, 214)
        border_col = (84, 150, 132) if is_player else (160, 94, 88)
        tooltip_labels = []
        for key, label, icon in visible:
            icon_rect = pygame.Rect(x, y, icon_size, icon_size)
            pygame.draw.rect(self.window, bg_col, icon_rect.inflate(3, 3),
                             border_radius=5)
            pygame.draw.rect(self.window, border_col, icon_rect.inflate(3, 3),
                             1, border_radius=5)
            if icon:
                self.window.blit(icon, icon.get_rect(center=icon_rect.center))
            else:
                tiny = settings.get_font(settings.FS_CONQUER_META, bold=True)
                letter = (label or key or '?')[:1].upper()
                surf = tiny.render(letter, True, (238, 222, 178))
                self.window.blit(surf, surf.get_rect(center=icon_rect.center))
            if label:
                tooltip_labels.append(label)
            x += icon_size + gap

        if overflow:
            count_rect = pygame.Rect(x, y, count_w, icon_size)
            pygame.draw.rect(self.window, bg_col, count_rect.inflate(3, 3),
                             border_radius=5)
            pygame.draw.rect(self.window, border_col, count_rect.inflate(3, 3),
                             1, border_radius=5)
            self.window.blit(count_surf, count_surf.get_rect(center=count_rect.center))

        if tooltip_labels:
            if not hasattr(self, '_conquer_lane_tooltips'):
                self._conquer_lane_tooltips = []
            self._conquer_lane_tooltips.append({
                'rect': area,
                'text': ', '.join(tooltip_labels),
            })

    @staticmethod
    def _conquer_support_section_key(entry):
        return entry.get('section') or 'clash'

    @staticmethod
    def _conquer_support_display_group_key(entry):
        kind = entry.get('kind') or 'support'
        section = ConquerGameScreen._conquer_support_section_key(entry)
        if kind in {'support_bonus', 'land_bonus', 'buffs_allies',
                    'blocks_bonus', 'distance_attack'}:
            detail = (
                entry.get('target_suit')
                or entry.get('suit')
                or getattr(entry.get('figure'), 'suit', None)
            )
        elif kind == 'called':
            move = entry.get('move') if isinstance(entry.get('move'), dict) else {}
            detail = move.get('family_name') or entry.get('label') or 'Call'
        else:
            detail = kind
        return section, kind, detail

    def _conquer_support_display_sections(self, entries):
        section_order = ('clash', 'round_0', 'round_1', 'round_2')
        sections = {key: [] for key in section_order}
        grouped = {}
        for entry in entries or []:
            key = self._conquer_support_display_group_key(entry)
            group = grouped.get(key)
            if group is None:
                group = dict(entry)
                group['source_entries'] = [entry]
                group['source_figure_ids'] = list(entry.get('source_figure_ids') or [])
                group['target_figure_ids'] = list(entry.get('target_figure_ids') or [])
                group['numeric_value'] = int(entry.get('numeric_value') or 0)
                group['blocked_value'] = int(entry.get('blocked_value') or 0)
                group['unblocked_numeric_value'] = int(
                    entry.get('unblocked_numeric_value')
                    if entry.get('unblocked_numeric_value') is not None
                    else group['numeric_value'])
                group['blocked_bonus'] = bool(entry.get('blocked_bonus'))
                group['aggregate_count'] = 1
                grouped[key] = group
                continue
            group['source_entries'].append(entry)
            group['aggregate_count'] += 1
            group['numeric_value'] = int(group.get('numeric_value') or 0) + int(entry.get('numeric_value') or 0)
            group['blocked_value'] = int(group.get('blocked_value') or 0) + int(entry.get('blocked_value') or 0)
            group['unblocked_numeric_value'] = int(group.get('unblocked_numeric_value') or 0) + int(
                entry.get('unblocked_numeric_value')
                if entry.get('unblocked_numeric_value') is not None
                else entry.get('numeric_value') or 0)
            group['blocked_bonus'] = bool(group.get('blocked_bonus') or entry.get('blocked_bonus'))
            for attr in ('source_figure_ids', 'target_figure_ids'):
                ids = group.setdefault(attr, [])
                for fig_id in entry.get(attr, []) or []:
                    if fig_id is not None and fig_id not in ids:
                        ids.append(fig_id)

        for group in grouped.values():
            kind = group.get('kind')
            value = int(group.get('numeric_value') or 0)
            if kind == 'blocks_bonus':
                group['value'] = 'Block'
            elif kind == 'support_bonus' and group.get('blocked_bonus'):
                unblocked = int(group.get('unblocked_numeric_value') or 0)
                blocked = int(group.get('blocked_value') or 0)
                group['blocked_full'] = blocked >= value and value > 0
                group['value'] = f'+{unblocked}' if unblocked > 0 else f'+{abs(value)}'
            elif value:
                if kind == 'distance_attack':
                    group['value'] = f'-{abs(value)}'
                else:
                    # Honour the real sign so Landslide's inverted land bonus
                    # renders as a negative badge, not a forced "+".
                    group['value'] = f'{value:+d}'
            else:
                group['value'] = group.get('value') or ''
            sections.setdefault(self._conquer_support_section_key(group), []).append(group)

        order = {
            'support_bonus': 0,
            'land_bonus': 1,
            'buffs_allies': 2,
            'buffs_allies_defence': 3,
            'blocks_bonus': 4,
            'distance_attack': 5,
            'called': 6,
        }
        for key in sections:
            sections[key].sort(key=lambda e: (
                order.get(e.get('kind'), 99),
                str(e.get('suit') or ''),
                str(e.get('label') or ''),
            ))
        return sections

    def _draw_conquer_lane_support_badge(self, badge, entry, *, is_player,
                                         pulse=False, hovered=False):
        badge = pygame.Rect(badge)
        fill = (28, 56, 50, 232) if is_player else (62, 40, 42, 232)
        border = (112, 220, 150) if is_player else (232, 118, 110)
        if hovered:
            border = (120, 220, 235)
        pygame.draw.rect(self.window, fill, badge, border_radius=6)
        pygame.draw.rect(self.window, border, badge, 3 if hovered else 2, border_radius=6)
        if pulse or hovered:
            phase = (pygame.time.get_ticks() % 900) / 900.0
            pulse_alpha = int(70 + 90 * (1.0 - abs(0.5 - phase) * 2.0))
            glow = pygame.Surface(badge.size, pygame.SRCALPHA)
            pygame.draw.rect(glow, (*border, pulse_alpha), glow.get_rect().inflate(-2, -2), 3, border_radius=6)
            self.window.blit(glow, badge.topleft)

        icon_box = pygame.Rect(badge).inflate(-8, -10)
        icon_box.height = max(12, icon_box.height - 8)
        icon_box.centery = badge.centery - 2
        kind = entry.get('kind')
        icon_size = max(12, min(icon_box.width, icon_box.height))
        icon_center = icon_box.center

        if kind == 'called' and isinstance(entry.get('move'), dict):
            self._draw_conquer_call_family_icon(icon_box, entry['move'])
            # Suit-match boost: when the called tactic's suit matches the
            # called figure's suit, the move's base value stacks on top.
            # Highlight with a small suit emblem in the top-right corner.
            if entry.get('suit_match_bonus'):
                suit_icon = self._load_conquer_suit_icon(
                    entry.get('suit'),
                    max(12, int(icon_size * 0.48)))
                if suit_icon:
                    suit_rect = suit_icon.get_rect()
                    suit_rect.topright = (badge.right - 3, badge.top + 3)
                    bg = suit_rect.inflate(5, 5)
                    pygame.draw.ellipse(self.window, (60, 38, 12), bg)
                    pygame.draw.ellipse(self.window, (246, 200, 96), bg, 1)
                    self.window.blit(suit_icon, suit_rect.topleft)
        else:
            if kind == 'support_bonus':
                icon = self._load_conquer_state_icon('support_bonus', icon_size)
            elif kind == 'land_bonus':
                icon = self._load_conquer_state_icon('land_bonus', icon_size)
            else:
                icon = self._load_conquer_skill_icon(kind, icon_size)
            if icon:
                self.window.blit(icon, icon.get_rect(center=icon_center))
            else:
                pygame.draw.rect(self.window, border, icon_box, border_radius=5)
                tiny = settings.get_font(settings.FS_CONQUER_META, bold=True)
                label = str(entry.get('label') or kind or '?')[:1]
                letter = tiny.render(label, True, (20, 16, 10))
                self.window.blit(letter, letter.get_rect(center=icon_center))
            if kind in {'support_bonus', 'land_bonus', 'blocks_bonus',
                        'buffs_allies', 'buffs_allies_defence',
                        'distance_attack'}:
                suit_icon = self._load_conquer_suit_icon(
                    entry.get('target_suit') if kind == 'blocks_bonus' else entry.get('suit'),
                    max(12, int(icon_size * 0.48)))
                if suit_icon:
                    suit_rect = suit_icon.get_rect()
                    suit_rect.topright = (badge.right - 3, badge.top + 3)
                    bg = suit_rect.inflate(5, 5)
                    pygame.draw.ellipse(self.window, (18, 14, 10), bg)
                    self.window.blit(suit_icon, suit_rect.topleft)

        count = int(entry.get('aggregate_count') or 1)
        if count > 1:
            count_font = settings.get_font(
                settings.FS_CONQUER_LABEL, bold=True)
            count_surf = count_font.render(f'x{count}', True, (24, 18, 12))
            count_chip = count_surf.get_rect()
            count_chip.inflate_ip(6, 4)
            count_chip.topleft = (badge.left + 3, badge.top + 3)
            pygame.draw.rect(self.window, (246, 226, 150), count_chip,
                             border_radius=count_chip.height // 2)
            self.window.blit(count_surf, count_surf.get_rect(center=count_chip.center))

        value_font = settings.get_font(settings.FS_CONQUER_LABEL, bold=True)
        value = str(entry.get('value') or '')
        if not value:
            return
        blocked_bonus = bool(entry.get('blocked_bonus'))
        full_block = bool(entry.get('blocked_full'))
        suit_match_bonus = int(entry.get('suit_match_bonus') or 0)
        if blocked_bonus and full_block:
            text_col = (170, 150, 128)
        elif suit_match_bonus and not blocked_bonus:
            # Gold tint signals the suit-match boost is active.
            text_col = (255, 222, 138)
        else:
            text_col = (246, 239, 214)
        value_surf = value_font.render(self._fit_text(value, value_font, badge.width - 8), True, text_col)
        value_chip = value_surf.get_rect()
        value_chip.inflate_ip(7, 5)
        value_chip.bottomright = (badge.right - 3, badge.bottom - 3)
        chip_bg = (32, 24, 22) if blocked_bonus else (24, 18, 12)
        chip_border = (220, 72, 62) if blocked_bonus else (
            (246, 200, 96) if suit_match_bonus else border)
        pygame.draw.rect(self.window, chip_bg, value_chip, border_radius=value_chip.height // 2)
        pygame.draw.rect(self.window, chip_border, value_chip, 1, border_radius=value_chip.height // 2)
        self.window.blit(value_surf, value_surf.get_rect(center=value_chip.center))
        if blocked_bonus:
            pygame.draw.line(
                self.window,
                (225, 58, 52),
                (value_chip.left + 3, value_chip.bottom - 4),
                (value_chip.right - 3, value_chip.top + 4),
                2,
            )

    def _register_conquer_support_badge_rect(self, badge, entry, *, is_player):
        rects = getattr(self, '_conquer_support_badge_rects', None)
        if rects is None:
            rects = []
            self._conquer_support_badge_rects = rects
        figure = entry.get('figure') if isinstance(entry, dict) else None
        source_ids = [sid for sid in entry.get('source_figure_ids', []) if sid is not None]
        if not source_ids and getattr(figure, 'id', None) is not None:
            source_ids = [getattr(figure, 'id', None)]
        rects.append({
            'rect': pygame.Rect(badge),
            'entry': entry,
            'figure_id': getattr(figure, 'id', None),
            'source_figure_ids': source_ids,
            'is_player': is_player,
        })

    def _current_conquer_support_hover_entry(self):
        # A touch pin substitutes for hover, so every hover consumer (badge
        # glow, field source highlight, face-down reveal, popovers) behaves
        # identically for pinned badges without further changes.
        pin = getattr(self, '_conquer_support_touch_pin', None)
        if pin is not None:
            if pin[0] != 'badge':
                return None
            for info in reversed(getattr(self, '_conquer_support_badge_rects', []) or []):
                if self._conquer_support_pin_key(info) == pin:
                    return info
            return None
        mouse = pygame.mouse.get_pos()
        for info in reversed(getattr(self, '_conquer_support_badge_rects', []) or []):
            rect = info.get('rect')
            if rect and pygame.Rect(rect).collidepoint(mouse):
                return info
            for fig_id in info.get('source_figure_ids', []) or [info.get('figure_id')]:
                source_rect = self._conquer_support_source_rect(fig_id)
                if source_rect and source_rect.collidepoint(mouse):
                    return info
        return None

    def _current_conquer_support_overflow_entry(self):
        pin = getattr(self, '_conquer_support_touch_pin', None)
        if pin is not None:
            if pin[0] != 'overflow':
                return None
            for info in reversed(getattr(self, '_conquer_support_overflow_rects', []) or []):
                if self._conquer_support_overflow_pin_key(info) == pin:
                    return info
            return None
        mouse = pygame.mouse.get_pos()
        for info in reversed(getattr(self, '_conquer_support_overflow_rects', []) or []):
            rect = info.get('rect')
            if rect and pygame.Rect(rect).collidepoint(mouse):
                return info
        return None

    def _current_conquer_receipt_hover_entry(self):
        mouse = pygame.mouse.get_pos()
        for info in reversed(getattr(self, '_conquer_receipt_row_rects', []) or []):
            rect = info.get('rect')
            if rect and pygame.Rect(rect).collidepoint(mouse):
                return info
        return None

    def _update_conquer_support_hover_state(self):
        support_info = self._current_conquer_support_hover_entry()
        receipt_info = self._current_conquer_receipt_hover_entry()
        self._conquer_hovered_support_badge = support_info
        self._conquer_hovered_receipt_row = receipt_info
        source_ids = support_info.get('source_figure_ids') if support_info else []
        source_id = source_ids[0] if source_ids else (support_info.get('figure_id') if support_info else None)
        field = getattr(self, 'subscreens', {}).get('field') if hasattr(self, 'subscreens') else None
        if field is not None:
            field._conquer_hover_source_figure_ids = set(source_ids or [])
            field._conquer_hover_source_figure_id = source_id
        return support_info

    @staticmethod
    def _annotate_blocked_support_entries(entries, enemy_entries):
        blocked_target_ids = {
            target_id
            for entry in enemy_entries or []
            if entry.get('kind') == 'blocks_bonus'
            for target_id in (entry.get('target_figure_ids') or [])
            if target_id is not None
        }
        if not blocked_target_ids:
            return list(entries or [])
        annotated = []
        for entry in entries or []:
            item = dict(entry)
            if item.get('kind') == 'support_bonus':
                targets = [t for t in item.get('target_figure_ids') or [] if t is not None]
                blocked_targets = [t for t in targets if t in blocked_target_ids]
                if blocked_targets:
                    per = int(item.get('per_target_value') or 0)
                    if not per and targets:
                        per = int(item.get('numeric_value') or 0) // max(1, len(targets))
                    blocked_value = per * len(blocked_targets)
                    raw_value = int(item.get('numeric_value') or 0)
                    item['blocked_bonus'] = blocked_value > 0
                    item['blocked_value'] = blocked_value
                    item['unblocked_numeric_value'] = max(0, raw_value - blocked_value)
                    item['blocked_target_figure_ids'] = blocked_targets
            annotated.append(item)
        return annotated

    def _conquer_support_source_rect(self, figure_id):
        if figure_id is None:
            return None
        field = getattr(self, 'subscreens', {}).get('field') if hasattr(self, 'subscreens') else None
        icon = getattr(field, 'icon_cache', {}).get(figure_id) if field is not None else None
        rect = getattr(icon, 'rect_frame', None) or getattr(icon, 'rect_frame_big', None)
        return pygame.Rect(rect) if rect else None

    def _conquer_support_source_marker_endpoint(self, figure_id, *, is_own):
        """Return the marker midpoint for the source figure's selection bar.

        Used as the terminal point of the support/block link line so the
        link visibly anchors to the same side marker the figure displays
        when highlighted (round 12).
        """
        if figure_id is None:
            return None
        field = getattr(self, 'subscreens', {}).get('field') if hasattr(self, 'subscreens') else None
        if field is None:
            return None
        icon = getattr(field, 'icon_cache', {}).get(figure_id)
        if not icon:
            return None
        rect = getattr(icon, 'rect_frame', None) or getattr(icon, 'rect_frame_big', None)
        if not rect:
            return None
        center = pygame.Rect(rect).center
        marker = field._conquer_icon_marker_geometry(
            icon, center, is_own=is_own)
        return marker['midpoint']

    @staticmethod
    def _conquer_source_halo_rect(source_rect):
        halo = pygame.Rect(source_rect)
        halo.inflate_ip(4, 4)
        return halo

    @staticmethod
    def _conquer_rect_edge_point(rect, start):
        rect = pygame.Rect(rect)
        center = rect.center
        vx = float(start[0] - center[0])
        vy = float(start[1] - center[1])
        if vx == 0 and vy == 0:
            return center
        candidates = []
        if vx < 0:
            candidates.append((rect.left - center[0]) / vx)
        elif vx > 0:
            candidates.append((rect.right - center[0]) / vx)
        if vy < 0:
            candidates.append((rect.top - center[1]) / vy)
        elif vy > 0:
            candidates.append((rect.bottom - center[1]) / vy)
        scale = min((c for c in candidates if c >= 0), default=0)
        return (int(center[0] + vx * scale), int(center[1] + vy * scale))

    def _draw_conquer_lane_source_link(self, badge_rect, endpoint, *, is_player):
        if endpoint is None:
            return
        badge_rect = pygame.Rect(badge_rect)
        start = badge_rect.midleft if is_player else badge_rect.midright
        end = (int(endpoint[0]), int(endpoint[1]))
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        distance = math.hypot(dx, dy)
        if distance < 2:
            return

        pad = 14
        bounds = pygame.Rect(
            min(start[0], end[0]) - pad,
            min(start[1], end[1]) - pad,
            abs(dx) + pad * 2 + 1,
            abs(dy) + pad * 2 + 1,
        )
        overlay = pygame.Surface(bounds.size, pygame.SRCALPHA)
        local_start = (start[0] - bounds.left, start[1] - bounds.top)
        local_end = (end[0] - bounds.left, end[1] - bounds.top)

        shadow = (7, 15, 18, 120)
        color = (120, 220, 235, 220)
        highlight = (228, 252, 255, 170)
        pygame.draw.line(overlay, shadow, local_start, local_end, 4)
        pygame.draw.line(overlay, color, local_start, local_end, 2)
        pygame.draw.aaline(overlay, highlight, local_start, local_end)
        pygame.draw.circle(overlay, shadow, (local_start[0], local_start[1] + 1), 4)
        pygame.draw.circle(overlay, color, local_start, 3)
        self.window.blit(overlay, bounds.topleft)

    def _draw_conquer_support_overflow_popover(self):
        info = self._current_conquer_support_overflow_entry()
        if not info:
            return
        entries = info.get('entries') or []
        if not entries:
            return
        anchor = pygame.Rect(info.get('rect'))
        is_player = info.get('is_player', True)
        font = settings.get_font(settings.FS_CONQUER_META, bold=True)
        title_font = settings.get_font(settings.FS_CONQUER_META, bold=True)
        width = 178
        line_h = font.get_height() + 3
        visible = entries[:5]
        height = 12 + title_font.get_height() + len(visible) * line_h
        panel = pygame.Rect(0, 0, width, height)
        panel.centery = anchor.centery
        if is_player:
            panel.left = anchor.right + 8
        else:
            panel.right = anchor.left - 8
        panel.clamp_ip(pygame.Rect(0, 0, settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
        bg = pygame.Surface(panel.size, pygame.SRCALPHA)
        pygame.draw.rect(bg, (22, 20, 18, 238), bg.get_rect(), border_radius=7)
        border = (120, 220, 235)
        pygame.draw.rect(bg, border, bg.get_rect(), 1, border_radius=7)
        self.window.blit(bg, panel.topleft)

        title = title_font.render(f'+{len(entries)} support', True, (246, 226, 150))
        self.window.blit(title, (panel.left + 8, panel.top + 6))
        y = panel.top + 8 + title_font.get_height()
        for entry in visible:
            source_names = []
            for source in entry.get('source_entries', []) or [entry]:
                figure = source.get('figure')
                if figure is not None:
                    source_names.append(getattr(figure, 'name', 'Figure'))
            if not source_names and entry.get('kind') == 'land_bonus':
                source_names.append(str(entry.get('suit') or 'Land'))
            name = ', '.join(source_names[:2]) if source_names else 'Effect'
            if len(source_names) > 2:
                name += f' +{len(source_names) - 2}'
            label = entry.get('label') or entry.get('kind') or 'Support'
            value = entry.get('value') or ''
            text = self._fit_text(f'{label} {value} · {name}', font, panel.width - 16)
            surf = font.render(text, True, (232, 220, 180))
            self.window.blit(surf, (panel.left + 8, y))
            y += line_h

    def _conquer_support_chip_summary(self, sections):
        """Fold grouped support entries into a few aggregate chips (mobile).

        Returns synthetic entry dicts compatible with the badge rect
        registration / pin / popover pipeline: each carries the union of
        contributing ``source_figure_ids`` (so a pinned chip highlights every
        contributing figure on the field) plus the flat ``source_entries``
        rows the breakdown popover lists. Called-tactic entries keep their
        own icon chips — folding them would lose the call identity.
        """
        plus, ranged, blocks, called = [], [], [], []
        plus_total = 0
        ranged_total = 0
        block_count = 0
        for section_entries in sections.values():
            for entry in section_entries:
                kind = entry.get('kind')
                if kind == 'called':
                    called.append(entry)
                    continue
                if kind == 'blocks_bonus':
                    blocks.append(entry)
                    block_count += int(entry.get('aggregate_count') or 1)
                    continue
                if entry.get('blocked_bonus'):
                    value = int(entry.get('unblocked_numeric_value') or 0)
                else:
                    value = int(entry.get('numeric_value') or 0)
                if kind == 'distance_attack':
                    # This side's outgoing ranged damage onto the enemy
                    # fighter — displayed as the projected minus.
                    ranged.append(entry)
                    ranged_total += abs(value)
                else:
                    # Support / buffs / land. Landslide can flip land
                    # negative, which correctly lowers the support sum.
                    plus.append(entry)
                    plus_total += value

        def _fold(kind, label, value, folded):
            sources = []
            fig_ids = []
            for entry in folded:
                sources.extend(entry.get('source_entries') or [entry])
                for fig_id in entry.get('source_figure_ids') or []:
                    if fig_id is not None and fig_id not in fig_ids:
                        fig_ids.append(fig_id)
            return {
                'kind': kind,
                'label': label,
                'value': value,
                'source_entries': sources,
                'source_figure_ids': fig_ids,
                'section': 'aggregate',
            }

        chips = []
        if plus:
            chips.append(_fold(
                'aggregate_support', 'SUP', f'{plus_total:+d}', plus))
        if blocks:
            chips.append(_fold(
                'aggregate_block', 'BLK', f'x{block_count}', blocks))
        if ranged:
            chips.append(_fold(
                'aggregate_ranged', 'RNG', f'-{ranged_total}', ranged))
        chips.extend(called)
        return chips

    def _draw_conquer_support_chip(self, chip, entry, *, is_player,
                                   hovered=False, pulse=False):
        kind = entry.get('kind')
        if kind == 'aggregate_support':
            fill, border = (24, 62, 46, 236), (112, 220, 150)
            value_color = (198, 248, 204)
        elif kind == 'aggregate_block':
            fill, border = (30, 46, 66, 236), (130, 180, 235)
            value_color = (200, 226, 250)
        elif kind == 'aggregate_ranged':
            fill, border = (66, 32, 34, 236), (235, 130, 118)
            value_color = (250, 198, 190)
        else:  # called tactic keeps the side palette + family icon
            fill = (28, 56, 50, 232) if is_player else (62, 40, 42, 232)
            border = (112, 220, 150) if is_player else (232, 118, 110)
            value_color = (246, 226, 150)
        if hovered:
            border = (120, 220, 235)
        pygame.draw.rect(self.window, fill, chip, border_radius=8)
        pygame.draw.rect(self.window, border, chip, 3 if hovered else 2,
                         border_radius=8)
        if pulse or hovered:
            phase = (pygame.time.get_ticks() % 900) / 900.0
            pulse_alpha = int(70 + 90 * (1.0 - abs(0.5 - phase) * 2.0))
            glow = pygame.Surface(chip.size, pygame.SRCALPHA)
            pygame.draw.rect(glow, (*border, pulse_alpha),
                             glow.get_rect().inflate(-2, -2), 3,
                             border_radius=8)
            self.window.blit(glow, chip.topleft)

        if kind == 'called' and isinstance(entry.get('move'), dict):
            icon_box = pygame.Rect(chip).inflate(-10, -12)
            self._draw_conquer_call_family_icon(icon_box, entry['move'])
            value = str(entry.get('value') or '')
            if value:
                value_font = settings.get_font(
                    settings.FS_CONQUER_LABEL, bold=True)
                value_surf = value_font.render(value, True, value_color)
                value_chip = value_surf.get_rect().inflate(6, 3)
                value_chip.midbottom = (chip.centerx, chip.bottom - 2)
                pygame.draw.rect(self.window, (24, 18, 12), value_chip,
                                 border_radius=value_chip.height // 2)
                self.window.blit(value_surf,
                                 value_surf.get_rect(center=value_chip.center))
            return

        label_font = settings.get_font(settings.FS_CONQUER_META, bold=True)
        value_font = settings.get_font(settings.FS_CONQUER_SECONDARY, bold=True)
        label_surf = label_font.render(
            str(entry.get('label') or ''), True, border)
        self.window.blit(label_surf, label_surf.get_rect(
            midtop=(chip.centerx, chip.top + 3)))
        value_text = str(entry.get('value') or '')
        value_surf = value_font.render(value_text, True, value_color)
        # Drop to the LABEL tier when the SECONDARY rendering would spill
        # out of the chip or overlap the label band above it.
        value_room_h = chip.height - label_surf.get_height() - 8
        if (value_surf.get_width() > chip.width - 6
                or value_surf.get_height() > value_room_h):
            small = settings.get_font(settings.FS_CONQUER_LABEL, bold=True)
            value_surf = small.render(value_text, True, value_color)
        self.window.blit(value_surf, value_surf.get_rect(
            midbottom=(chip.centerx, chip.bottom - 3)))

    def _draw_conquer_lane_support_chips(self, rail, sections, *, is_player,
                                         pulse=False):
        """Mobile support rail: 2–3 aggregated, tappable chips instead of
        stacked per-effect micro-badges. Section identity (R1/R2/R3) lives
        in the pinned breakdown popover rather than persistent labels."""
        border = (84, 150, 132) if is_player else (160, 94, 88)
        header_font = settings.get_font(settings.FS_CONQUER_META, bold=True)
        header_surf = header_font.render('SUP', True, border)
        header_h = header_surf.get_height() + 4
        self.window.blit(header_surf, header_surf.get_rect(
            center=(rail.centerx, rail.top + header_h // 2)))
        if not hasattr(self, '_conquer_lane_tooltips'):
            self._conquer_lane_tooltips = []
        self._conquer_lane_tooltips.append({
            'rect': pygame.Rect(rail.left, rail.top, rail.width, header_h),
            'text': 'Support on this side — tap a chip for the breakdown',
        })
        chips = self._conquer_support_chip_summary(sections)
        if not chips:
            return
        inner = pygame.Rect(rail.left + 2, rail.top + header_h + 2,
                            rail.width - 4, rail.height - header_h - 4)
        label_h = settings.get_font(settings.FS_CONQUER_META, bold=True).get_height()
        value_h = settings.get_font(settings.FS_CONQUER_SECONDARY, bold=True).get_height()
        chip_h = min(max(label_h + value_h + 9,
                         settings.TOUCH_COMPACT_MIN or 36), 58)
        gap = 5
        max_fit = max(1, (inner.height + gap) // (chip_h + gap))
        visible = chips[:max_fit]
        if len(chips) > len(visible) and len(visible) > 1:
            visible = visible[:-1]
        pin = getattr(self, '_conquer_support_touch_pin', None)
        mouse = pygame.mouse.get_pos()
        y = inner.top
        for entry in visible:
            chip = pygame.Rect(inner.left, y, inner.width, chip_h)
            hovered = chip.collidepoint(mouse)
            if pin is not None and not hovered:
                hovered = (self._conquer_support_pin_key(
                    {'entry': entry, 'is_player': is_player}) == pin)
            self._register_conquer_support_badge_rect(
                chip, entry, is_player=is_player)
            self._draw_conquer_support_chip(
                chip, entry, is_player=is_player, hovered=hovered,
                pulse=pulse and entry.get('kind') == 'aggregate_support')
            y += chip_h + gap
        overflow_entries = chips[len(visible):]
        if overflow_entries:
            font = settings.get_font(settings.FS_CONQUER_LABEL, bold=True)
            text = font.render(f'+{len(overflow_entries)}', True,
                               (246, 239, 214))
            chip = text.get_rect().inflate(10, 6)
            chip.midbottom = (inner.centerx, inner.bottom - 1)
            if not hasattr(self, '_conquer_support_overflow_rects'):
                self._conquer_support_overflow_rects = []
            self._conquer_support_overflow_rects.append({
                'rect': pygame.Rect(chip),
                'entries': overflow_entries,
                'is_player': is_player,
                'section': 'aggregate',
            })
            pygame.draw.rect(self.window, (26, 20, 14), chip,
                             border_radius=chip.height // 2)
            pygame.draw.rect(self.window, border, chip, 1,
                             border_radius=chip.height // 2)
            self.window.blit(text, text.get_rect(center=chip.center))

    def _draw_conquer_support_badge_popover(self):
        """Breakdown popover for the hovered/pinned aggregate support chip.

        Mobile chip mode only — desktop badges explain themselves through
        field highlights and per-badge values.
        """
        if settings.TOUCH_TARGET_MIN <= 0:
            return
        info = self._current_conquer_support_hover_entry()
        if not info:
            return
        entry = info.get('entry') if isinstance(info, dict) else None
        entry = entry if isinstance(entry, dict) else {}
        if not str(entry.get('kind') or '').startswith('aggregate'):
            return
        rows = entry.get('source_entries') or []
        if not rows:
            return
        anchor = pygame.Rect(info.get('rect'))
        is_player = info.get('is_player', True)
        font = settings.get_font(settings.FS_CONQUER_META, bold=True)
        title_font = settings.get_font(settings.FS_CONQUER_LABEL, bold=True)
        titles = {
            'aggregate_support': 'Support',
            'aggregate_block': 'Blocks',
            'aggregate_ranged': 'Ranged strikes',
        }
        title_text = (f"{titles.get(entry.get('kind'), 'Support')} "
                      f"{entry.get('value') or ''}").strip()
        width = max(200, int(settings.SCREEN_WIDTH * 0.26))
        line_h = font.get_height() + 3
        visible = rows[:6]
        height = 12 + title_font.get_height() + len(visible) * line_h
        panel = pygame.Rect(0, 0, width, height)
        panel.centery = anchor.centery
        if is_player:
            panel.left = anchor.right + 8
        else:
            panel.right = anchor.left - 8
        panel.clamp_ip(pygame.Rect(0, 0, settings.SCREEN_WIDTH,
                                   settings.SCREEN_HEIGHT))
        bg = pygame.Surface(panel.size, pygame.SRCALPHA)
        pygame.draw.rect(bg, (22, 20, 18, 238), bg.get_rect(), border_radius=7)
        pygame.draw.rect(bg, (120, 220, 235), bg.get_rect(), 1, border_radius=7)
        self.window.blit(bg, panel.topleft)
        title = title_font.render(title_text, True, (246, 226, 150))
        self.window.blit(title, (panel.left + 8, panel.top + 6))
        y = panel.top + 8 + title_font.get_height()
        for row in visible:
            source_names = []
            figure = row.get('figure')
            if figure is not None:
                source_names.append(getattr(figure, 'name', 'Figure'))
            if not source_names and row.get('kind') == 'land_bonus':
                source_names.append(str(row.get('suit') or 'Land'))
            name = ', '.join(source_names[:2]) if source_names else 'Effect'
            label = row.get('label') or row.get('kind') or 'Support'
            value = row.get('value') or ''
            text = self._fit_text(f'{label} {value} · {name}'.strip(),
                                  font, panel.width - 16)
            surf = font.render(text, True, (232, 220, 180))
            self.window.blit(surf, (panel.left + 8, y))
            y += line_h

    def _draw_conquer_lane_support_rail(self, rect, entries, *, is_player, pulse=False):
        rail = pygame.Rect(rect).inflate(-3, -8)
        if rail.width <= 0 or rail.height <= 0:
            return
        bg = (20, 40, 38, 156) if is_player else (44, 30, 32, 156)
        border = (84, 150, 132) if is_player else (160, 94, 88)
        pygame.draw.rect(self.window, bg, rail, border_radius=7)
        pygame.draw.rect(self.window, border, rail, 1, border_radius=7)

        # Mobile: aggregated, tappable chips instead of per-effect badges.
        if settings.TOUCH_TARGET_MIN > 0:
            sections = self._conquer_support_display_sections(entries)
            self._draw_conquer_lane_support_chips(
                rail, sections, is_player=is_player, pulse=pulse)
            return

        # Header label so players know what the column represents (#6).
        header_font = settings.get_font(settings.FS_CONQUER_META, bold=True)
        header_text = self._fit_text('SUPPORT', header_font, rail.width - 4)
        header_surf = header_font.render(header_text, True, border)
        header_h = header_surf.get_height() + 4
        self.window.blit(header_surf, header_surf.get_rect(
            center=(rail.centerx, rail.top + header_h // 2)))
        # Register hover tooltip rect for the header.
        if not hasattr(self, '_conquer_lane_tooltips'):
            self._conquer_lane_tooltips = []
        self._conquer_lane_tooltips.append({
            'rect': pygame.Rect(rail.left, rail.top, rail.width, header_h),
            'text': 'Figures supporting this side from adjacent fields',
        })
        rail_inner = pygame.Rect(rail.left, rail.top + header_h, rail.width, rail.height - header_h)
        sections = self._conquer_support_display_sections(entries)
        # Round 10 #11: only render sections for rounds that have begun
        # OR that already have entries to display. Clash is always shown.
        game = getattr(getattr(self, 'state', None), 'game', None)
        current_round_no = int(getattr(game, 'battle_round', 0) or 0) if game else 0
        all_section_defs = (
            ('clash', 'CLASH', 0),
            ('round_0', 'R1', 1),
            ('round_1', 'R2', 2),
            ('round_2', 'R3', 3),
        )
        section_defs = []
        for key, title, round_no in all_section_defs:
            section_entries = sections.get(key, [])
            has_started = round_no == 0 or current_round_no >= round_no
            if has_started or section_entries:
                section_defs.append((key, title))
        if not section_defs:
            section_defs = [('clash', 'CLASH')]
        title_font = settings.get_font(settings.FS_CONQUER_META, bold=True)
        gap = max(3, int(rail_inner.height * 0.010))
        section_h = max(1, (rail_inner.height - gap * (len(section_defs) - 1)) // len(section_defs))
        mouse = pygame.mouse.get_pos()
        for idx, (section_key, title) in enumerate(section_defs):
            top = rail_inner.top + idx * (section_h + gap)
            section_rect = pygame.Rect(rail_inner.left + 2, top,
                                       max(1, rail_inner.width - 4), section_h)
            if idx:
                pygame.draw.line(self.window, (*border, 150),
                                 (section_rect.left + 2, section_rect.top - gap // 2),
                                 (section_rect.right - 2, section_rect.top - gap // 2), 1)
            title_surf = title_font.render(title, True, border)
            title_bg = title_surf.get_rect()
            title_bg.inflate_ip(5, 2)
            title_bg.midtop = (section_rect.centerx, section_rect.top + 1)
            pygame.draw.rect(self.window, (22, 18, 14), title_bg,
                             border_radius=max(2, title_bg.height // 3))
            self.window.blit(title_surf, title_surf.get_rect(center=title_bg.center))

            section_entries = sections.get(section_key, [])
            if not section_entries:
                continue
            entry_top = title_bg.bottom + 3
            entry_area_h = max(0, section_rect.bottom - entry_top - 2)
            badge_w = max(24, min(section_rect.width - 4, int(section_rect.width * 0.86)))
            badge_h = max(24, min(badge_w, max(1, entry_area_h)))
            entry_gap = max(2, int(entry_area_h * 0.05))
            max_visible = max(1, (entry_area_h + entry_gap) // max(1, badge_h + entry_gap))
            visible = section_entries[:max_visible]
            if len(section_entries) > len(visible) and len(visible) > 1:
                visible = visible[:-1]
            y = entry_top
            pin = getattr(self, '_conquer_support_touch_pin', None)
            for entry in visible:
                badge = pygame.Rect(0, 0, badge_w, badge_h)
                badge.centerx = section_rect.centerx
                badge.top = y
                hovered = badge.collidepoint(mouse)
                for fig_id in entry.get('source_figure_ids', []) or []:
                    source_rect = self._conquer_support_source_rect(fig_id)
                    if source_rect and source_rect.collidepoint(mouse):
                        hovered = True
                        break
                if pin is not None and not hovered:
                    hovered = (self._conquer_support_pin_key(
                        {'entry': entry, 'is_player': is_player}) == pin)
                self._register_conquer_support_badge_rect(badge, entry, is_player=is_player)
                self._draw_conquer_lane_support_badge(
                    badge,
                    entry,
                    is_player=is_player,
                    pulse=pulse and section_key == 'round_0',
                    hovered=hovered,
                )
                y += badge_h + entry_gap
            overflow_entries = section_entries[len(visible):]
            if overflow_entries:
                font = settings.get_font(
                    settings.FS_CONQUER_LABEL, bold=True)
                text = font.render(f'+{len(overflow_entries)}', True, (246, 239, 214))
                chip = text.get_rect()
                chip.inflate_ip(8, 4)
                chip.midbottom = (section_rect.centerx, section_rect.bottom - 1)
                overflow_hovered = chip.collidepoint(mouse)
                if not hasattr(self, '_conquer_support_overflow_rects'):
                    self._conquer_support_overflow_rects = []
                self._conquer_support_overflow_rects.append({
                    'rect': pygame.Rect(chip),
                    'entries': overflow_entries,
                    'is_player': is_player,
                    'section': section_key,
                })
                pygame.draw.rect(self.window, (26, 20, 14), chip, border_radius=chip.height // 2)
                pygame.draw.rect(self.window, (120, 220, 235) if overflow_hovered else border,
                                 chip, 2 if overflow_hovered else 1, border_radius=chip.height // 2)
                self.window.blit(text, text.get_rect(center=chip.center))

    def _draw_conquer_lane_chip_rail(self, rect, chips, *, is_player):
        rail = pygame.Rect(rect).inflate(-2, -8)
        if rail.width <= 0 or rail.height <= 0:
            return
        bg = (18, 34, 36, 144) if is_player else (38, 28, 30, 144)
        border = (92, 164, 172) if is_player else (178, 110, 104)
        pygame.draw.rect(self.window, bg, rail, border_radius=7)
        pygame.draw.rect(self.window, border, rail, 1, border_radius=7)

        # Header label so players know what the column represents (#6).
        header_font = settings.get_font(settings.FS_CONQUER_META, bold=True)
        header_text = self._fit_text('MOD', header_font, rail.width - 2)
        header_surf = header_font.render(header_text, True, border)
        header_h = header_surf.get_height() + 3
        self.window.blit(header_surf, header_surf.get_rect(
            center=(rail.centerx, rail.top + header_h // 2)))
        if not hasattr(self, '_conquer_lane_tooltips'):
            self._conquer_lane_tooltips = []
        self._conquer_lane_tooltips.append({
            'rect': pygame.Rect(rail.left, rail.top, rail.width, header_h),
            'text': 'Modifiers: Call / Land / Spell',
        })
        rail_inner = pygame.Rect(rail.left, rail.top + header_h, rail.width, rail.height - header_h)
        if not chips:
            return
        font = settings.get_font(settings.FS_CONQUER_META, bold=True)
        max_visible = min(4, len(chips))
        gap = max(3, int(rail_inner.height * 0.014))
        chip_h = min(max(20, int(rail_inner.width * 1.10)),
                     max(12, (rail_inner.height - gap * (max_visible + 1)) // max_visible))
        y = rail_inner.top + gap
        for chip_data in chips[:max_visible]:
            chip = pygame.Rect(rail_inner.left + 1, y, max(1, rail_inner.width - 2), chip_h)
            pygame.draw.rect(self.window, (25, 20, 14), chip, border_radius=chip.height // 2)
            pygame.draw.rect(self.window, border, chip, 1, border_radius=chip.height // 2)
            label = str(chip_data.get('label', '?'))[:1]
            value = str(chip_data.get('value', ''))
            text = label if chip.width < 34 else self._fit_text(f'{label}{value}', font, chip.width - 4)
            surf = font.render(text, True, (238, 222, 178))
            self.window.blit(surf, surf.get_rect(center=chip.center))
            y += chip_h + gap

    def _draw_conquer_lane_tactic_badge(self, rect, move, round_idx, *, is_player,
                                        ghost=False):
        rail = pygame.Rect(rect).inflate(-5, -10)
        if rail.width <= 0 or rail.height <= 0:
            return
        center_y = rail.centery
        badge_h = min(max(54, rail.width + 18), max(1, rail.height - 8))
        badge = pygame.Rect(0, 0, rail.width, badge_h)
        badge.center = (rail.centerx, center_y)
        fill = (36, 55, 58, 232) if is_player else (60, 42, 44, 232)
        border = (126, 198, 190) if is_player else (212, 145, 130)
        if ghost:
            fill = (34, 64, 70, 228)
            border = (120, 205, 220)
        pygame.draw.rect(self.window, fill, badge, border_radius=6)
        pygame.draw.rect(self.window, border, badge, 2, border_radius=6)
        if ghost:
            phase = (pygame.time.get_ticks() % 900) / 900.0
            pulse = 1.0 - abs(0.5 - phase) * 2.0
            alpha = int(80 + 95 * pulse)
            pulse_surf = pygame.Surface(badge.size, pygame.SRCALPHA)
            pygame.draw.rect(
                pulse_surf,
                (120, 205, 220, alpha),
                pulse_surf.get_rect().inflate(-2, -2),
                3,
                border_radius=6,
            )
            self.window.blit(pulse_surf, badge.topleft)

        tiny = settings.get_font(settings.FS_CONQUER_META, bold=True)
        name_font = settings.get_font(settings.FS_CONQUER_LABEL, bold=True)
        value_font = settings.get_font(max(settings.FS_CONQUER_LABEL, int(settings.FS_TINY * 0.88)), bold=True)
        round_surf = tiny.render(f'R{round_idx + 1}', True, (232, 220, 180))
        self.window.blit(round_surf, round_surf.get_rect(center=(badge.centerx, badge.top + 9)))

        if move:
            name = self._fit_text(self._conquer_lane_move_name(move), name_font, badge.width - 6)
            name_surf = name_font.render(name, True, (246, 239, 214))
            value_col = (154, 232, 238) if ghost else (245, 214, 122)
            value_surf = value_font.render(str(self._conquer_lane_move_power(move)), True, value_col)
            if badge.width < 44:
                self.window.blit(value_surf, value_surf.get_rect(center=(badge.centerx, badge.centery + 4)))
            else:
                self.window.blit(name_surf, name_surf.get_rect(center=(badge.centerx, badge.centery)))
                self.window.blit(value_surf, value_surf.get_rect(center=(badge.centerx, badge.bottom - 11)))
        else:
            wait = tiny.render('...', True, (156, 140, 102))
            self.window.blit(wait, wait.get_rect(center=(badge.centerx, badge.centery + 8)))

    def _draw_conquer_lane_leader_line(self, from_rect, to_rect, *, is_player,
                                       ghost=False):
        start = pygame.Rect(from_rect).center
        end_rect = pygame.Rect(to_rect).inflate(-16, -12)
        end = (end_rect.left, end_rect.centery) if is_player else (end_rect.right, end_rect.centery)
        color = (126, 198, 190) if is_player else (212, 145, 130)
        width = 2
        if ghost:
            color = (120, 205, 220)
            width = 3
        pygame.draw.line(self.window, color, start, end, width)
        pygame.draw.circle(self.window, color, start, 3 if not ghost else 4)

    def _conquer_lane_call_power(self, move):
        call_figure = self._conquer_lane_find_figure(
            move.get('call_figure_id') if isinstance(move, dict) else None)
        return self._conquer_lane_call_effective_power(move, call_figure)

    def _conquer_lane_healer_bonus_for(self, figure, support_entries):
        if figure is None or self._conquer_lane_family_field(figure) != 'village':
            return 0
        suit = getattr(figure, 'suit', None)
        return sum(
            self._conquer_lane_support_value(entry)
            for entry in support_entries or []
            if entry.get('kind') == 'buffs_allies'
            and getattr(entry.get('figure'), 'suit', None) == suit
        )

    def _conquer_lane_call_effective_power(self, move, call_figure=None,
                                          support_entries=None):
        if not isinstance(move, dict):
            return 0
        call_figure = call_figure or self._conquer_lane_find_figure(
            move.get('call_figure_id'))
        if call_figure is None:
            return 0
        total = self._conquer_lane_figure_power(call_figure)
        total += self._conquer_lane_healer_bonus_for(call_figure, support_entries or [])
        if (str(getattr(call_figure, 'suit', '') or '').lower()
                == str(move.get('suit') or '').lower()):
            total += self._conquer_lane_move_power(move)
        return total

    def _conquer_lane_move_effective_power(self, move, support_entries=None):
        if not isinstance(move, dict):
            return 0
        if move.get('_skipped') or move.get('family_name') == 'Skip':
            return 0
        if move.get('family_name') == 'Block':
            return 0
        if move.get('call_figure_id'):
            return self._conquer_lane_call_effective_power(
                move,
                support_entries=support_entries or [],
            )
        return self._conquer_lane_move_power(move)

    def _conquer_tactic_display_power(self, move):
        if not isinstance(move, dict):
            return 0
        try:
            context = self._conquer_lane_context()
            cache_key = (
                context.get('key'),
                move.get('id'),
                move.get('status'),
                move.get('played_round'),
                move.get('call_figure_id'),
                move.get('family_name'),
                move.get('suit'),
                move.get('suit_b'),
                move.get('rank'),
                move.get('value'),
            )
            cache = getattr(self, '_conquer_tactic_power_cache', None)
            if isinstance(cache, dict) and cache_key in cache:
                return cache[cache_key]

            player_id = getattr(self.state.game, 'player_id', None)
            move_player_id = move.get('player_id')
            is_player = move_player_id is None or move_player_id == player_id
            support_entries = (
                context.get('player_support') if is_player
                else context.get('opponent_support')
            ) or []
            # For unbound Call tactics, mirror legacy ``_get_panel_display_power``:
            # show the maximum potential combined power across eligible figures.
            family_to_field = {
                'Call Villager': 'village',
                'Call Military': 'military',
                'Call King': 'castle',
            }
            if (is_player
                    and not move.get('call_figure_id')
                    and move.get('family_name') in family_to_field):
                best = self._conquer_best_call_figure_for_tactic(
                    move, context=context, support_entries=support_entries)
                if best is not None:
                    value = self._conquer_lane_call_effective_power(
                        move, best, support_entries)
                    if isinstance(cache, dict):
                        cache[cache_key] = value
                    return value
            value = self._conquer_lane_move_effective_power(move, support_entries)
            if isinstance(cache, dict):
                cache[cache_key] = value
            return value
        except Exception:
            return self._conquer_lane_move_power(move)

    def _conquer_best_call_figure_for_tactic(self, move, *, context=None,
                                            support_entries=None):
        if not isinstance(move, dict) or move.get('call_figure_id') is not None:
            return None
        family_to_field = {
            'Call Villager': 'village',
            'Call Military': 'military',
            'Call King': 'castle',
        }
        target_field = family_to_field.get(move.get('family_name'))
        if not target_field:
            return None
        if context is None:
            context = self._conquer_lane_context()
        if support_entries is None:
            support_entries = context.get('player_support') or []
        battle_ids = self._conquer_lane_battle_figure_ids()
        called_ids = {
            tactic.get('call_figure_id')
            for tactic in self._current_conquer_tactics() or []
            if (isinstance(tactic, dict)
                and tactic.get('call_figure_id') is not None)
        }
        move_is_red = move.get('suit') in {'Hearts', 'Diamonds'}
        candidates = []
        for figure in self._conquer_lane_all_figures():
            if (getattr(figure, 'player_id', None)
                    != getattr(self.state.game, 'player_id', None)):
                continue
            if (getattr(figure, 'id', None) in battle_ids
                    or getattr(figure, 'id', None) in called_ids):
                continue
            if self._conquer_lane_family_field(figure) != target_field:
                continue
            if (getattr(figure, 'has_deficit', False)
                    or getattr(figure, 'cannot_be_targeted', False)):
                continue
            fig_is_red = getattr(figure, 'suit', None) in {'Hearts', 'Diamonds'}
            if fig_is_red != move_is_red:
                continue
            candidates.append(figure)
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda fig: self._conquer_lane_call_effective_power(
                move,
                fig,
                support_entries,
            ),
        )

    def _conquer_lane_figure_full_power(self, figure, *, support_entries=None,
                                        enemy_support_entries=None,
                                        is_player=True):
        """Per-figure total power matching legacy ``_get_figure_total_power``.

        Components: base + buffs_allies (village, suit-matched) + support
        (castle/village, suit-matched, blocked by enemy ``blocks_bonus``)
        + wall (when defending) + enchant - distance_attack penalty
        (suit-advantage from enemy archers).
        """
        if figure is None:
            return 0
        base = self._conquer_lane_figure_power(figure)
        if support_entries is None:
            player_figures, opponent_figures = self._conquer_lane_figures()
            support_entries = self._conquer_lane_support_entries(
                player_figures, opponent_figures, is_player=is_player)
        if enemy_support_entries is None:
            player_figures, opponent_figures = self._conquer_lane_figures()
            enemy_support_entries = self._conquer_lane_support_entries(
                player_figures, opponent_figures, is_player=not is_player)

        suit = getattr(figure, 'suit', None)
        field = self._conquer_lane_family_field(figure)
        fig_id = getattr(figure, 'id', None)
        blocked = self._conquer_figure_blocked_by_entries(
            fig_id, enemy_support_entries)

        buffs = 0
        support = 0
        wall = 0
        for e in support_entries or []:
            kind = e.get('kind')
            targets = e.get('target_figure_ids') or []
            if fig_id is not None and fig_id not in targets:
                continue
            per = e.get('per_target_value')
            if per is None:
                per = int(e.get('numeric_value') or 0)
            if kind == 'buffs_allies':
                buffs += int(per)
            elif kind == 'support_bonus' and not blocked:
                support += int(per)
            elif kind == 'buffs_allies_defence':
                if self._conquer_lane_is_defending_side(is_player=is_player):
                    wall += int(per)

        enchant = 0
        getter = getattr(figure, 'get_total_enchantment_modifier', None)
        if callable(getter):
            try:
                enchant = int(getter() or 0)
            except Exception:
                enchant = 0

        land = 0 if blocked else self._conquer_lane_land_bonus_for([figure])

        # Distance-attack penalty: only if this figure is among targets
        da_penalty = 0
        for e in enemy_support_entries or []:
            if e.get('kind') != 'distance_attack':
                continue
            targets = e.get('target_figure_ids') or []
            if fig_id is not None and fig_id not in targets:
                continue
            per = e.get('per_target_value')
            if per is None:
                per = int(e.get('numeric_value') or 0)
            da_penalty += int(per)

        return base + buffs + support + wall + land + enchant - da_penalty

    def _conquer_lane_figure_power_breakdown(self, figure, *,
                                             support_entries=None,
                                             enemy_support_entries=None,
                                             is_player=True):
        """Return ordered ``[(label, value), ...]`` for a fighter chip.

        Mirrors :meth:`_conquer_lane_figure_full_power` but exposes each
        non-zero component so the band's power chip can render them as a
        colour-coded segmented pill (#2).
        """
        if figure is None:
            return []
        if support_entries is None or enemy_support_entries is None:
            player_figures, opponent_figures = self._conquer_lane_figures()
            if support_entries is None:
                support_entries = self._conquer_lane_support_entries(
                    player_figures, opponent_figures, is_player=is_player)
            if enemy_support_entries is None:
                enemy_support_entries = self._conquer_lane_support_entries(
                    player_figures, opponent_figures, is_player=not is_player)
        base = self._conquer_lane_figure_power(figure)
        fig_id = getattr(figure, 'id', None)
        blocked = self._conquer_figure_blocked_by_entries(
            fig_id, enemy_support_entries)
        buffs = support = wall = 0
        for e in support_entries or []:
            kind = e.get('kind')
            targets = e.get('target_figure_ids') or []
            if fig_id is not None and fig_id not in targets:
                continue
            per = e.get('per_target_value')
            if per is None:
                per = int(e.get('numeric_value') or 0)
            if kind == 'buffs_allies':
                buffs += int(per)
            elif kind == 'support_bonus' and not blocked:
                support += int(per)
            elif kind == 'buffs_allies_defence':
                if self._conquer_lane_is_defending_side(is_player=is_player):
                    wall += int(per)
        enchant = 0
        getter = getattr(figure, 'get_total_enchantment_modifier', None)
        if callable(getter):
            try:
                enchant = int(getter() or 0)
            except Exception:
                enchant = 0
        da_penalty = 0
        for e in enemy_support_entries or []:
            if e.get('kind') != 'distance_attack':
                continue
            targets = e.get('target_figure_ids') or []
            if fig_id is not None and fig_id not in targets:
                continue
            per = e.get('per_target_value')
            if per is None:
                per = int(e.get('numeric_value') or 0)
            da_penalty += int(per)
        rows = [('Base', base)]
        if buffs:
            rows.append(('Buffs', buffs))
        if support:
            rows.append(('Support', support))
        if wall:
            rows.append(('Wall', wall))
        land = 0 if blocked else self._conquer_lane_land_bonus_for([figure])
        if land:
            rows.append(('Land', land))
        if enchant:
            rows.append(('Spell', enchant))
        if da_penalty:
            rows.append(('Range', -da_penalty))
        return rows

    def _conquer_lane_figure_diff(self):
        """Player figure total power minus opponent figure total power."""
        context = self._conquer_lane_context()
        player_figures = context.get('player_figures') or []
        opponent_figures = context.get('opponent_figures') or []
        if not player_figures and not opponent_figures:
            return 0
        p_support = context.get('player_support') or []
        o_support = context.get('opponent_support') or []
        p_total = sum(self._conquer_lane_figure_full_power(
            f, support_entries=p_support, enemy_support_entries=o_support,
            is_player=True) for f in player_figures)
        o_total = sum(self._conquer_lane_figure_full_power(
            f, support_entries=o_support, enemy_support_entries=p_support,
            is_player=False) for f in opponent_figures)
        return p_total - o_total

    @staticmethod
    def _conquer_lane_support_value(entry):
        if entry.get('numeric_value') is not None:
            return int(entry.get('numeric_value') or 0)
        kind = entry.get('kind')
        figure = entry.get('figure')
        if kind == 'support_bonus':
            return ConquerGameScreen._conquer_lane_regular_support_value(figure)
        if kind == 'buffs_allies':
            return 4
        if kind == 'buffs_allies_defence':
            return ConquerGameScreen._conquer_lane_number_value(figure)
        if kind == 'distance_attack':
            return ConquerGameScreen._conquer_lane_number_value(figure)
        return 0

    def _conquer_lane_land_bonus_for(self, figures):
        game = self.state.game
        land_suit, land_bonus = self._conquer_effective_land_bonus(game)
        if not land_suit or not land_bonus:
            return 0
        if any(getattr(fig, 'suit', None) == land_suit for fig in figures or []):
            return int(land_bonus)
        return 0

    @staticmethod
    def _conquer_receipt_row(label, value, *, source_figure_ids=None, kind=None):
        return {
            'label': label,
            'value': value,
            'source_figure_ids': list(source_figure_ids or []),
            'kind': kind or label.lower(),
        }

    @staticmethod
    def _conquer_receipt_row_parts(row):
        if isinstance(row, dict):
            return row.get('label', ''), row.get('value')
        return row[0], row[1]

    _CONQUER_RECEIPT_LABEL_COLORS = {
        'Base':   (238, 206, 111),
        'Called': (240, 178, 96),
        'Support':(146, 222, 220),
        'Buffs':  (146, 230, 160),
        'Wall':   (140, 200, 230),
        'Land':   (216, 196, 138),
        'Spell':  (200, 168, 240),
        'Tactic': (245, 214, 122),
        'Range':  (236, 130, 120),
        'Block':  (200, 200, 200),
        'Blocked':(200, 200, 200),
        'Total':  (250, 240, 200),
    }

    @classmethod
    def _conquer_receipt_label_color(cls, label):
        return cls._CONQUER_RECEIPT_LABEL_COLORS.get(label, (220, 210, 180))

    @staticmethod
    def _conquer_support_entry_targets_figure(entry, fig_id):
        targets = entry.get('target_figure_ids') or []
        if not targets:
            return True
        return fig_id is not None and fig_id in targets

    @staticmethod
    def _conquer_figure_blocked_by_entries(fig_id, entries):
        for entry in entries or []:
            if entry.get('kind') != 'blocks_bonus':
                continue
            targets = entry.get('target_figure_ids') or []
            if not targets or (fig_id is not None and fig_id in targets):
                return True
        return False

    @staticmethod
    def _conquer_support_entry_ids(entries, kind, target_figure_ids=None):
        target_set = set(target_figure_ids or [])
        ids = []
        for entry in entries:
            if entry.get('kind') != kind:
                continue
            if target_set:
                targets = set(entry.get('target_figure_ids') or [])
                if targets and not targets.intersection(target_set):
                    continue
            explicit = [sid for sid in entry.get('source_figure_ids', []) if sid is not None]
            if explicit:
                ids.extend(explicit)
                continue
            fig_id = getattr(entry.get('figure'), 'id', None)
            if fig_id is not None:
                ids.append(fig_id)
        return ids

    def _conquer_lane_receipt_components(self, figures, move, support_entries,
                                         enemy_support_entries):
        base = sum(self._conquer_lane_figure_power(fig) for fig in figures)
        tactic = self._conquer_lane_move_power(move)
        call = self._conquer_lane_call_effective_power(
            move,
            support_entries=support_entries,
        )
        figure_ids = {getattr(fig, 'id', None) for fig in figures or []}

        def _value_for_battle_targets(entry):
            targets = entry.get('target_figure_ids') or []
            if not targets:
                return 0
            count = sum(1 for t in targets if t in figure_ids)
            per = entry.get('per_target_value')
            if per is None:
                per = self._conquer_lane_support_value(entry)
            return int(per) * count

        blocked_target_ids = {
            target_id
            for entry in enemy_support_entries
            if entry.get('kind') == 'blocks_bonus'
            for target_id in (entry.get('target_figure_ids') or [])
            if target_id in figure_ids
        }
        unblocked_figure_ids = figure_ids - blocked_target_ids

        def _unblocked_value_for_battle_targets(entry):
            targets = entry.get('target_figure_ids') or []
            if not targets:
                return 0
            count = sum(
                1 for t in targets
                if t in figure_ids and t not in blocked_target_ids
            )
            per = entry.get('per_target_value')
            if per is None:
                per = self._conquer_lane_support_value(entry)
            return int(per) * count

        raw_support = sum(
            _value_for_battle_targets(entry)
            for entry in support_entries
            if entry.get('kind') == 'support_bonus'
        )
        buffs = sum(
            _value_for_battle_targets(entry)
            for entry in support_entries
            if entry.get('kind') == 'buffs_allies'
        )
        wall = sum(
            _value_for_battle_targets(entry)
            for entry in support_entries
            if entry.get('kind') == 'buffs_allies_defence'
        )
        land = sum(self._conquer_lane_land_bonus_for([fig]) for fig in figures or [])
        enchant = self._conquer_lane_enchantment_total(figures)
        distance_penalty = sum(
            _value_for_battle_targets(entry)
            for entry in enemy_support_entries
            if entry.get('kind') == 'distance_attack'
        )
        blocked_by_enemy = bool(blocked_target_ids)
        own_block = any(entry.get('kind') == 'blocks_bonus' for entry in support_entries)
        support = sum(
            _unblocked_value_for_battle_targets(entry)
            for entry in support_entries
            if entry.get('kind') == 'support_bonus'
        )
        land = sum(
            self._conquer_lane_land_bonus_for([fig])
            for fig in figures or []
            if getattr(fig, 'id', None) not in blocked_target_ids
        )
        if isinstance(move, dict) and move.get('call_figure_id'):
            tactic = 0
        total = base + call + support + buffs + wall + land + enchant + tactic - distance_penalty
        base_ids = [getattr(fig, 'id', None) for fig in figures if getattr(fig, 'id', None) is not None]
        rows = [self._conquer_receipt_row('Base', base, source_figure_ids=base_ids)]
        if call:
            rows.append(self._conquer_receipt_row(
                'Called',
                call,
                source_figure_ids=[move.get('call_figure_id')] if isinstance(move, dict) else [],
                kind='called',
            ))
        if raw_support:
            rows.append(self._conquer_receipt_row(
                'Support',
                support,
                source_figure_ids=self._conquer_support_entry_ids(
                    support_entries, 'support_bonus', unblocked_figure_ids),
            ))
        if buffs:
            rows.append(self._conquer_receipt_row(
                'Buffs',
                buffs,
                source_figure_ids=self._conquer_support_entry_ids(
                    support_entries, 'buffs_allies', figure_ids),
            ))
        if wall:
            rows.append(self._conquer_receipt_row(
                'Wall',
                wall,
                source_figure_ids=self._conquer_support_entry_ids(
                    support_entries, 'buffs_allies_defence', figure_ids),
            ))
        if land:
            land_suit = getattr(self.state.game, 'land_suit_bonus_suit', None)
            rows.append(self._conquer_receipt_row(
                'Land',
                land,
                source_figure_ids=[
                    getattr(fig, 'id', None) for fig in figures
                    if (getattr(fig, 'suit', None) == land_suit
                        and getattr(fig, 'id', None) is not None
                        and getattr(fig, 'id', None) not in blocked_target_ids)
                ],
            ))
        if enchant:
            rows.append(self._conquer_receipt_row('Spell', enchant, source_figure_ids=base_ids))
        if tactic:
            rows.append(self._conquer_receipt_row('Tactic', tactic))
        if distance_penalty:
            rows.append(self._conquer_receipt_row(
                'Range',
                -distance_penalty,
                source_figure_ids=self._conquer_support_entry_ids(
                    enemy_support_entries, 'distance_attack', figure_ids),
            ))
        if own_block:
            rows.append(self._conquer_receipt_row(
                'Block',
                'on',
                source_figure_ids=self._conquer_support_entry_ids(support_entries, 'blocks_bonus'),
            ))
        if blocked_by_enemy and (raw_support or self._conquer_lane_land_bonus_for(figures)):
            rows.append(self._conquer_receipt_row(
                'Blocked',
                'support',
                source_figure_ids=self._conquer_support_entry_ids(
                    enemy_support_entries, 'blocks_bonus', figure_ids),
            ))
        rows.append(self._conquer_receipt_row('Total', total, source_figure_ids=base_ids))
        return rows, total

    def _conquer_lane_compact_receipt(self, rows):
        """Build a one-line summary string from receipt rows.

        Format: ``Base 10 +Sup 4 +Buff 4 +Spell 2 −Range 3 = 17``.
        """
        # Short labels for compact display.
        short = {
            'Base': 'B', 'Called': 'Call', 'Support': 'Sup',
            'Buff': 'Buff', 'Wall': 'Wall', 'Land': 'Land',
            'Spell': 'Sp', 'Tactic': 'T', 'Range': 'R',
            'Block': 'Blk',
        }
        parts = []
        total_text = '0'
        for row in rows or []:
            label, value = self._conquer_receipt_row_parts(row)
            if label == 'Total':
                total_text = str(value if not isinstance(value, str) else value)
                continue
            if isinstance(value, str):
                continue
            value = int(value or 0)
            if label != 'Base' and value == 0:
                continue
            tag = short.get(label, label)
            if label == 'Base':
                parts.append(f'{tag}{value}')
            elif value < 0 or label == 'Range':
                # Range values arrive as positive in the receipt but represent a penalty.
                v = abs(value)
                parts.append(f'\u2212{tag}{v}')
            else:
                parts.append(f'+{tag}{value}')
        if not parts:
            return f'= {total_text}'
        return ' '.join(parts) + f' = {total_text}'

    def _draw_conquer_lane_verbose_math(self, area, rows, *, prefix='YOU',
                                        prefix_color=(154, 218, 206),
                                        align_right=False):
        """Render a verbose, colour-coded math row inside ``area``.

        Format: ``15 base +4 buff +2 spell +14 tactic = 33`` with each
        segment painted in its receipt-row colour (#5).  The ``prefix``
        argument is retained for backwards-compat but no longer rendered
        — the side is identified by the ``prefix_color`` total chip and
        the row's vertical position (#round5).  If the line does not fit,
        falls back to short codes so the math is still readable.
        """
        area = pygame.Rect(area)
        if area.width <= 0 or area.height <= 0:
            return
        font = settings.get_font(settings.FS_CONQUER_LABEL, bold=True)
        # Build segments: (text, color)
        segments = []
        total_text = '0'
        first_value = True
        for row in rows or []:
            label, value = self._conquer_receipt_row_parts(row)
            if label == 'Total':
                total_text = str(value)
                continue
            if isinstance(value, str):
                continue
            value = int(value or 0)
            if label != 'Base' and value == 0:
                continue
            colour = self._conquer_receipt_label_color(label)
            if label == 'Base':
                segments.append((f'{value} {label.lower()}', colour))
                first_value = False
            else:
                if value < 0 or label == 'Range':
                    magnitude = abs(value)
                    sign = '\u2212'
                else:
                    magnitude = value
                    sign = '+'
                prefix_space = ' ' if not first_value else ''
                segments.append((f'{prefix_space}{sign}{magnitude} {label.lower()}', colour))
                first_value = False
        segments.append((f'  =  {total_text}', prefix_color))

        # Pre-render and measure.
        rendered = [(font.render(text, True, colour), text, colour) for text, colour in segments]
        total_w = sum(s.get_width() for s, _, _ in rendered)
        if total_w > area.width:
            # Fall back to compact one-liner (no side prefix).
            compact = self._fit_text(self._conquer_lane_compact_receipt(rows), font, area.width)
            surf = font.render(compact, True, prefix_color)
            x = area.right - surf.get_width() if align_right else area.left
            self.window.blit(surf, (x, area.top))
            return
        x = area.right - total_w if align_right else area.left
        for surf, _, _ in rendered:
            self.window.blit(surf, (x, area.top))
            x += surf.get_width()

    def _register_conquer_receipt_row_hitrects(self, area, rows, *, align_right,
                                                top_offset=0):
        """Populate ``_conquer_receipt_row_rects`` with hit-rects for each row.

        Used so hover-based UX (tooltips, support-source highlighting) works even
        when the rows themselves are not currently being blitted (e.g. compact
        summary mode).
        """
        area = pygame.Rect(area)
        font = settings.get_font(settings.FS_CONQUER_META, bold=True)
        line_h = font.get_height() + 1
        rects = getattr(self, '_conquer_receipt_row_rects', None)
        if rects is None:
            rects = []
            self._conquer_receipt_row_rects = rects
        y = area.top + top_offset
        for row in rows:
            label, value = self._conquer_receipt_row_parts(row)
            if isinstance(value, str):
                value_text = value
            else:
                sign = '+' if isinstance(value, (int, float)) and value > 0 and label != 'Base' else ''
                value_text = f'{sign}{value}'
            text = self._fit_text(f'{label} {value_text}', font, area.width)
            surf = font.render(text, True, (255, 255, 255))
            x = area.right - surf.get_width() if align_right else area.left
            row_rect = pygame.Rect(x - 2, y - 1, surf.get_width() + 4, line_h)
            rects.append({'rect': row_rect, 'row': row, 'align_right': align_right})
            y += line_h

    def _draw_conquer_lane_receipt_rows(self, area, rows, *, align_right, color):
        area = pygame.Rect(area)
        font = settings.get_font(settings.FS_CONQUER_META, bold=True)
        if area.width <= 0 or area.height <= 0:
            return
        line_h = font.get_height() + 1
        max_lines = max(1, area.height // line_h)
        if len(rows) > max_lines:
            rows = rows[:max(0, max_lines - 1)] + [rows[-1]]
        y = area.top
        mouse = pygame.mouse.get_pos()
        rects = getattr(self, '_conquer_receipt_row_rects', None)
        if rects is None:
            rects = []
            self._conquer_receipt_row_rects = rects
        for row in rows:
            label, value = self._conquer_receipt_row_parts(row)
            if isinstance(value, str):
                value_text = value
            else:
                sign = '+' if isinstance(value, (int, float)) and value > 0 and label != 'Base' else ''
                value_text = f'{sign}{value}'
            text = self._fit_text(f'{label} {value_text}', font, area.width)
            surf = font.render(text, True, color if label != 'Total' else (246, 226, 150))
            x = area.right - surf.get_width() if align_right else area.left
            row_rect = pygame.Rect(x - 2, y - 1, surf.get_width() + 4, line_h)
            rects.append({'rect': row_rect, 'row': row, 'align_right': align_right})
            if row_rect.collidepoint(mouse):
                highlight = pygame.Surface(row_rect.size, pygame.SRCALPHA)
                pygame.draw.rect(highlight, (120, 220, 235, 72), highlight.get_rect(), border_radius=4)
                self.window.blit(highlight, row_rect.topleft)
            self.window.blit(surf, (x, y))
            y += line_h

    def _draw_conquer_lane_diff_popover(self, anchor, player_rows, player_total,
                                        opponent_rows, opponent_total, diff):
        panel = pygame.Rect(anchor)
        if panel.width <= 0 or panel.height <= 0:
            return
        font = settings.get_font(settings.FS_CONQUER_META, bold=True)
        title_font = settings.get_font(settings.FS_CONQUER_META, bold=True)
        rows_left = [row for row in player_rows if self._conquer_receipt_row_parts(row)[0] != 'Total']
        rows_right = [row for row in opponent_rows if self._conquer_receipt_row_parts(row)[0] != 'Total']
        line_h = font.get_height() + 1
        bg = pygame.Surface(panel.size, pygame.SRCALPHA)
        pygame.draw.rect(bg, (18, 17, 16, 246), bg.get_rect(), border_radius=8)
        pygame.draw.rect(bg, (190, 152, 84), bg.get_rect(), 1, border_radius=8)
        self.window.blit(bg, panel.topleft)

        diff_col = (130, 220, 190) if diff > 0 else (226, 145, 130) if diff < 0 else (232, 220, 180)
        title = title_font.render(
            self._fit_text(f'FIGURES  YOU {player_total}  Δ {diff:+d}  OPP {opponent_total}',
                           title_font, panel.width - 12),
            True,
            diff_col,
        )
        self.window.blit(title, title.get_rect(
            center=(panel.centerx, panel.top + 5 + title_font.get_height() // 2)))

        col_gap = 6
        col_w = max(1, (panel.width - 14 - col_gap) // 2)
        rows_top = panel.top + 8 + title_font.get_height()
        row_capacity = max(1, (panel.bottom - rows_top - 4) // line_h)
        left_area = pygame.Rect(panel.left + 6, rows_top, col_w, row_capacity * line_h)
        right_area = pygame.Rect(left_area.right + col_gap, left_area.top, col_w, left_area.height)
        rects = getattr(self, '_conquer_receipt_row_rects', None)
        if rects is None:
            rects = []
            self._conquer_receipt_row_rects = rects

        def draw_rows(area, rows, *, align_right=False):
            y = area.top
            for row in rows[:row_capacity]:
                label, value = self._conquer_receipt_row_parts(row)
                if isinstance(value, str):
                    value_text = value
                else:
                    sign = '+' if isinstance(value, (int, float)) and value > 0 and label != 'Base' else ''
                    value_text = f'{sign}{value}'
                text = self._fit_text(f'{label[:4]} {value_text}', font, area.width)
                colour = self._conquer_receipt_label_color(label)
                surf = font.render(text, True, colour)
                x = area.right - surf.get_width() if align_right else area.left
                row_rect = pygame.Rect(x - 2, y - 1, surf.get_width() + 4, line_h)
                rects.append({'rect': row_rect, 'row': row, 'align_right': align_right})
                self.window.blit(surf, (x, y))
                y += line_h

        draw_rows(left_area, rows_left, align_right=False)
        draw_rows(right_area, rows_right, align_right=True)

    def _draw_conquer_lane_diff(self, rect, player_figures, opponent_figures,
                                player_move=None, opponent_move=None, round_idx=0,
                                player_support=None, opponent_support=None):
        band = pygame.Rect(rect).inflate(-12, -4)
        if band.width <= 0 or band.height <= 0:
            return
        pygame.draw.rect(self.window, (26, 25, 28, 176), band, border_radius=8)
        if player_support is None:
            player_support = self._conquer_lane_support_entries(
                player_figures, opponent_figures, is_player=True)
        if opponent_support is None:
            opponent_support = self._conquer_lane_support_entries(
                player_figures, opponent_figures, is_player=False)
        # Figures-only totals (no tactic / called bonus). This panel shows
        # the standing power of the battle figures themselves; the bottom
        # ledger's "BATTLE TOTAL" is the authoritative figures+tactics
        # number.
        player_rows, player_total = self._conquer_lane_receipt_components(
            player_figures, None, player_support, opponent_support)
        opponent_rows, opponent_total = self._conquer_lane_receipt_components(
            opponent_figures, None, opponent_support, player_support)
        diff = player_total - opponent_total
        # Hide the whole "FIGURES / VS" readout during pre-battle and the
        # battle-start countdown so the centre panel stays clean for the
        # countdown; the real number is revealed (with a pulse) only once the
        # reveal completes — never shown, even as "VS", before then.
        show_number = bool(player_figures and opponent_figures
                           and not self._conquer_clash_diff_hidden())
        if not show_number:
            # Leave the panel empty and reset the pulse tracker so the number
            # pops in when it is finally revealed.
            self._conquer_diff_prev_value = None
            return
        diff_text = f'{diff:+d}'
        # Pulse animation: when the current battle total changes we briefly
        # scale the number up so the UI clearly broadcasts the swing.
        now = pygame.time.get_ticks()
        prev = getattr(self, '_conquer_diff_prev_value', None)
        pulse_until = getattr(self, '_conquer_diff_pulse_until', 0) or 0
        if prev != diff:
            self._conquer_diff_prev_value = diff
            self._conquer_diff_pulse_until = now + 650
            pulse_until = self._conquer_diff_pulse_until
        base_size = max(22, int(settings.FS_SMALL * 1.75))
        if pulse_until and now < pulse_until:
            t = 1.0 - (pulse_until - now) / 650.0
            # Eased pulse: quick spike then settle (sin curve).
            import math
            scale = 1.0 + 0.25 * math.sin(min(1.0, t * 1.4) * math.pi)
        else:
            scale = 1.0
        font_size = max(18, int(base_size * scale))
        font = settings.get_font(font_size, bold=True)
        color = (130, 220, 190) if diff > 0 else (226, 145, 130) if diff < 0 else (232, 220, 180)
        # Outlined / chip background so the value reads against the busy
        # lane backdrop and the colour swap (green/red/gold) is unmissable.
        surf = font.render(diff_text, True, color)
        chip = surf.get_rect()
        chip.inflate_ip(14, 8)
        chip.center = band.center
        bg = pygame.Surface(chip.size, pygame.SRCALPHA)
        pygame.draw.rect(bg, (18, 14, 10, 230), bg.get_rect(),
                         border_radius=chip.height // 2)
        pygame.draw.rect(bg, (*color, 230), bg.get_rect(), 2,
                         border_radius=chip.height // 2)
        self.window.blit(bg, chip.topleft)
        self.window.blit(surf, surf.get_rect(center=chip.center))

        # Small caption above the chip clarifying this is figures-only.
        caption_font = settings.get_font(settings.FS_CONQUER_META, bold=True)
        caption_surf = caption_font.render('FIGURES', True, (190, 170, 130))
        caption_rect = caption_surf.get_rect(
            midbottom=(chip.centerx, chip.top - 2))
        if caption_rect.top >= band.top:
            self.window.blit(caption_surf, caption_rect.topleft)

        try:
            mouse = pygame.mouse.get_pos()
        except Exception:
            mouse = (-1, -1)
        if band.collidepoint(mouse):
            self._draw_conquer_lane_diff_popover(
                band, player_rows, player_total, opponent_rows, opponent_total, diff)

    def _draw_conquer_duel_lane(self):
        if not self._is_tactics_hand_game():
            return
        # Draw an empty duel-panel skeleton during pre-battle so the
        # spatial layout stays consistent (round 10 #10).
        battle_active = self._is_battle_phase_active()
        context = self._conquer_lane_context()
        player_figures = context.get('player_figures') or []
        opponent_figures = context.get('opponent_figures') or []
        if not battle_active and not player_figures and not opponent_figures:
            # No fighters yet at all — still draw an empty backdrop so the
            # lane is visible.
            pass
        layout = compute_conquer_layout(
            settings.SCREEN_WIDTH,
            settings.SCREEN_HEIGHT,
            mode=self._conquer_effective_layout_mode(),
        )
        lane = layout.battlefield.duel_lane
        lane_rect = pygame.Rect(lane.rect)
        # Stash for the figure overlay redraw so we only repaint figures
        # that actually overlap the duel lane.
        self._conquer_duel_lane_last_rect = lane_rect.copy()
        # Solid card so the busy battlefield/figure tiles can't bleed
        # through the duel panel (#1).  Two-tone backdrop with a thin gold
        # border reads as a parchment card sitting on top of the field.
        # The backdrop art depends only on the lane size, so it is cached
        # and reused across frames instead of being re-rasterized each draw.
        backdrop_cache = getattr(self, '_conquer_duel_lane_backdrop_cache', None)
        if backdrop_cache is None or backdrop_cache[0] != lane_rect.size:
            backdrop = pygame.Surface(lane_rect.size, pygame.SRCALPHA)
            pygame.draw.rect(backdrop, (22, 19, 16, 240), backdrop.get_rect(), border_radius=10)
            pygame.draw.rect(backdrop, (38, 32, 24, 240), backdrop.get_rect().inflate(-6, -6), border_radius=8)
            pygame.draw.rect(backdrop, (188, 152, 84, 220), backdrop.get_rect(), 2, border_radius=10)
            self._conquer_duel_lane_backdrop_cache = (lane_rect.size, backdrop)
        else:
            backdrop = backdrop_cache[1]
        self.window.blit(backdrop, lane_rect.topleft)

        # Fighter entrances: stamp new lane arrivals before the bands draw.
        self._stamp_conquer_lane_entrances(player_figures, opponent_figures)

        player_slots = context.get('player_slots') or [None, None, None]
        opponent_slots = context.get('opponent_slots') or [None, None, None]
        round_idx = self._conquer_lane_focus_round(player_slots, opponent_slots)
        player_move = player_slots[round_idx]
        opponent_move = opponent_slots[round_idx]
        preview_move = self._conquer_lane_preview_move(player_slots, round_idx)
        player_display_move = player_move if player_move is not None else preview_move
        player_move_is_preview = player_move is None and preview_move is not None
        player_support = context.get('player_support') or []
        opponent_support = context.get('opponent_support') or []
        self._conquer_support_badge_rects = []
        self._conquer_support_overflow_rects = []
        self._conquer_receipt_row_rects = []
        self._conquer_lane_figure_rects = []
        self._conquer_lane_tooltips = []

        you_band = self._conquer_lane_center_channel_rect(lane.you_fighter_band, lane)
        opp_band = self._conquer_lane_center_channel_rect(lane.opp_fighter_band, lane)
        diff_inner = self._conquer_lane_center_channel_rect(lane.diff_band, lane)
        # Stash the clash-diff panel rect so the battle-start moment can
        # spotlight it (see _pump_conquer_battle_countdown GO beat).
        self._conquer_lane_diff_rect = pygame.Rect(diff_inner)

        self._draw_conquer_lane_band(
            you_band, 'YOU', player_figures, is_player=True,
            support_entries=player_support,
            enemy_support_entries=opponent_support,
        )
        opponent = getattr(self.state.game, 'opponent_name', None) or 'OPPONENT'
        opponent_font = settings.get_font(settings.FS_CONQUER_LABEL, bold=True)
        # Allow ~10 more characters of opponent name before truncating
        # so common usernames are not clipped (round 10 #5).
        opp_band_rect = pygame.Rect(opp_band)
        opp_label_budget = max(160, opp_band_rect.width - 28)
        self._draw_conquer_lane_band(
            opp_band,
            self._fit_text(opponent.upper(), opponent_font, opp_label_budget),
            opponent_figures,
            is_player=False,
            support_entries=opponent_support,
            enemy_support_entries=player_support,
        )
        self._draw_conquer_lane_diff(
            diff_inner,
            player_figures,
            opponent_figures,
            player_move=player_display_move,
            opponent_move=opponent_move,
            round_idx=round_idx,
            player_support=player_support,
            opponent_support=opponent_support,
        )

        # Support rails are drawn after the center channel so their
        # sectioned cause icons stay visible instead of being hidden by
        # the fighter band backdrops.
        player_support_display = self._annotate_blocked_support_entries(
            player_support, opponent_support)
        opponent_support_display = self._annotate_blocked_support_entries(
            opponent_support, player_support)
        self._draw_conquer_lane_support_rail(
            lane.you_support_badge_rail,
            player_support_display,
            is_player=True,
            pulse=player_move_is_preview,
        )
        self._draw_conquer_lane_support_rail(
            lane.opp_support_badge_rail,
            opponent_support_display,
            is_player=False,
        )
        hovered_support = self._update_conquer_support_hover_state()
        if hovered_support:
            is_player_side = hovered_support.get('is_player', True)
            for fig_id in hovered_support.get('source_figure_ids', []) or [hovered_support.get('figure_id')]:
                endpoint = self._conquer_support_source_marker_endpoint(
                    fig_id, is_own=is_player_side)
                if not endpoint:
                    continue
                self._draw_conquer_lane_source_link(
                    hovered_support.get('rect'),
                    endpoint,
                    is_player=is_player_side,
                )
        self._draw_conquer_support_overflow_popover()
        self._draw_conquer_support_badge_popover()
        self._draw_conquer_lane_tooltips()

    def _draw_conquer_lane_tooltips(self):
        tooltips = getattr(self, '_conquer_lane_tooltips', None)
        if not tooltips:
            return
        mouse = pygame.mouse.get_pos()
        for tip in tooltips:
            rect = tip.get('rect')
            if not rect or not rect.collidepoint(mouse):
                continue
            text = str(tip.get('text', ''))
            if not text:
                continue
            font = settings.get_font(settings.FS_CONQUER_LABEL, bold=False)
            surf = font.render(text, True, (244, 230, 188))
            box = surf.get_rect()
            box.inflate_ip(12, 8)
            box.midbottom = (rect.centerx, rect.top - 4)
            box.left = max(4, min(box.left, settings.SCREEN_WIDTH - box.width - 4))
            box.top = max(4, box.top)
            bg = pygame.Surface(box.size, pygame.SRCALPHA)
            pygame.draw.rect(bg, (24, 20, 16, 240), bg.get_rect(), border_radius=6)
            pygame.draw.rect(bg, (188, 152, 84), bg.get_rect(), 1, border_radius=6)
            self.window.blit(bg, box.topleft)
            self.window.blit(surf, surf.get_rect(center=box.center))
            return

    def _conquer_duel_lane_render_key(self):
        rect = getattr(self, '_conquer_duel_lane_last_rect', None)
        if rect is not None and rect.collidepoint(pygame.mouse.get_pos()):
            return None
        # A pinned support chip renders its pulsing glow + breakdown popover
        # inside the lane pass; the cache would freeze a pre-pin frame (and
        # popover pixels must never leak into a snapshot).
        if getattr(self, '_conquer_support_touch_pin', None) is not None:
            return None
        if getattr(self, '_tactic_flight_animation', None):
            return None
        # Fighter entrances animate inside the lane — bypass the cache
        # while any are in flight so they draw live each frame.
        if getattr(self, '_conquer_lane_figure_entrances', None):
            return None
        # Battle-start countdown masks the clash-diff number — redraw live
        # so the real number is revealed the instant the countdown ends.
        if self._is_battle_countdown_active():
            return None
        sequencer = getattr(self, '_conquer_reveal_sequencer', None)
        if sequencer is not None and sequencer.is_active():
            return None
        try:
            layout_key = self._conquer_effective_layout_mode()
        except Exception:
            layout_key = None
        try:
            context_key = self._conquer_lane_context_fast_key()
        except Exception:
            context_key = self._conquer_lane_context_key()
        return (
            settings.SCREEN_WIDTH,
            settings.SCREEN_HEIGHT,
            layout_key,
            context_key,
            getattr(self, '_conquer_support_hover_figure_id', None),
            getattr(self, '_conquer_support_hover_side', None),
            getattr(self, '_conquer_support_hover_kind', None),
        )

    def _draw_conquer_duel_lane_cached(self):
        cache_key = self._conquer_duel_lane_render_key()
        cached_rect = getattr(self, '_conquer_duel_lane_render_cache_rect', None)
        if (cache_key is not None
                and getattr(self, '_conquer_duel_lane_render_cache_key', None) == cache_key
                and getattr(self, '_conquer_duel_lane_render_cache_surface', None) is not None
                and cached_rect is not None):
            self.window.blit(
                getattr(self, '_conquer_duel_lane_render_cache_surface'),
                cached_rect.topleft)
            return

        self._draw_conquer_duel_lane()
        cache_key = self._conquer_duel_lane_render_key()
        lane_rect = getattr(self, '_conquer_duel_lane_last_rect', None)
        if cache_key is None or lane_rect is None:
            self._conquer_duel_lane_render_cache_key = None
            self._conquer_duel_lane_render_cache_surface = None
            self._conquer_duel_lane_render_cache_rect = None
            return
        try:
            rect = pygame.Rect(lane_rect)
            self._conquer_duel_lane_render_cache_surface = (
                self.window.subsurface(rect).copy())
            self._conquer_duel_lane_render_cache_rect = rect
            self._conquer_duel_lane_render_cache_key = cache_key
        except Exception:
            self._conquer_duel_lane_render_cache_key = None
            self._conquer_duel_lane_render_cache_surface = None
            self._conquer_duel_lane_render_cache_rect = None

    def _opponent_fan_tactics(self):
        """Ordered list of the opponent's unplayed tactics for the hand fan.

        One source of truth for the strip: the count and the per-slot
        face-up/face-down decision both derive from THIS list, so a revealed
        card can never land in the wrong slot (which previously left a stray
        face-down card among revealed ones under All Seeing Eye).
        """
        fan = []
        for t in self._current_conquer_opponent_tactics():
            if not isinstance(t, dict) or t.get('played_round') is not None:
                continue
            status = t.get('status', 'available')
            if status != 'available' and not t.get('_render_ghost'):
                continue
            fan.append(t)
        return fan

    def _opponent_hidden_hand_count(self):
        """How many unplayed tactics the opponent currently holds."""
        return len(self._opponent_fan_tactics())

    def _conquer_opponent_hand_strip(self):
        """The far-right strip rect reserved for the opponent's hidden hand."""
        try:
            layout = compute_conquer_layout(
                settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT,
                mode=self._conquer_effective_layout_mode())
            strip = pygame.Rect(layout.battlefield.opp_hand_strip)
            return strip if strip.width > 0 and strip.height > 0 else None
        except Exception:
            return None

    def _conquer_opponent_hand_target_rect(self):
        """Animation destination for opponent-bound card-effect spells."""
        rect = getattr(self, '_conquer_opponent_hand_strip_rect', None)
        if rect is not None:
            try:
                return pygame.Rect(rect)
            except Exception:
                pass
        return self._conquer_opponent_hand_strip()

    @staticmethod
    def _draw_face_down_card(window, rect):
        """A small stylised face-down tactic card (no identity revealed)."""
        draw_face_down_card(window, rect)

    def _opponent_revealed_tactic_specs(self):
        """(suit, rank) per fan slot when All Seeing Eye reveals the opponent.

        Same ordering/length as :meth:`_opponent_fan_tactics`; entries are
        ``None`` for any slot whose identity is (still) unknown so the strip
        can pair each slot with its own card exactly.
        """
        if not self._conquer_all_seeing_eye_revealed():
            return []
        specs = []
        for tactic in self._opponent_fan_tactics():
            suit, rank = tactic.get('suit'), tactic.get('rank')
            specs.append((suit, rank) if (suit and rank) else None)
        return specs

    def _draw_opponent_strip_card_front(self, rect, spec):
        """Draw one revealed opponent tactic card face-up in the strip fan."""
        cache = getattr(self, '_opp_strip_front_cache', None)
        if cache is None:
            cache = {}
            self._opp_strip_front_cache = cache
        suit, rank = spec
        key = (suit, rank, rect.width, rect.height)
        surf = cache.get(key)
        if key not in cache:
            try:
                from game.components.cards.card_img import CardImg
                surf = CardImg(self.window, suit, rank,
                               width=rect.width, height=rect.height).front_img
            except Exception:
                surf = None
            if len(cache) > 64:
                cache.clear()
            cache[key] = surf
        if surf is None:
            self._draw_face_down_card(self.window, rect)
            return
        self.window.blit(surf, rect.topleft)
        pygame.draw.rect(self.window, (130, 190, 255), rect, 1, border_radius=3)

    def _draw_conquer_opponent_hand_strip(self):
        """Draw the opponent's hidden hand as a fanned column of face-down
        tactic cards on the far-right strip — count-only, since identities are
        withheld server-side. Gives card-effect spells a truthful destination.

        While the player's All Seeing Eye is active the same fan flips
        face-up: identical slots and count, real card faces.
        """
        if self.state.subscreen not in ('field', 'battle'):
            return
        if not self._is_tactics_hand_game():
            return
        strip = self._conquer_opponent_hand_strip()
        if strip is None:
            return
        self._conquer_opponent_hand_strip_rect = strip.copy()
        count = self._opponent_hidden_hand_count()
        if count <= 0:
            return
        revealed = self._opponent_revealed_tactic_specs()

        pad_x = max(1, int(strip.width * 0.08))
        card_w = max(8, strip.width - 2 * pad_x)
        card_h = int(card_w * 1.42)

        # Overlapping fan: each card reveals ~55% of the one beneath it. Up to
        # MAX_VISIBLE cards show; the badge always reports the true total.
        MAX_VISIBLE = 6
        visible = min(count, MAX_VISIBLE)
        step = int(card_h * 0.55)
        stack_h = card_h + (visible - 1) * step

        # Count badge dimensions (centred just below the fan).
        font = settings.get_font(settings.FS_CONQUER_LABEL, bold=True)
        label = font.render(str(count), True, (244, 232, 200))
        badge_gap = max(2, int(card_h * 0.16))
        bw, bh = label.get_width() + 12, label.get_height() + 4
        group_h = stack_h + badge_gap + bh

        # Shrink the overlap if the whole group would overflow the strip.
        max_group = strip.height - int(strip.height * 0.06)
        if group_h > max_group and visible > 1:
            step = max(int(card_h * 0.26),
                       (max_group - card_h - badge_gap - bh) // (visible - 1))
            stack_h = card_h + (visible - 1) * step
            group_h = stack_h + badge_gap + bh

        x = strip.x + (strip.width - card_w) // 2
        y = strip.y + max(int(strip.height * 0.03), (strip.height - group_h) // 2)
        for i in range(visible):
            card_rect = pygame.Rect(x, y, card_w, card_h)
            spec = revealed[i] if i < len(revealed) else None
            if spec is not None:
                # All Seeing Eye: same slot, flipped face-up.
                self._draw_opponent_strip_card_front(card_rect, spec)
            else:
                self._draw_face_down_card(self.window, card_rect)
            y += step
        stack_bottom = y - step + card_h

        bx = strip.x + (strip.width - bw) // 2
        by = stack_bottom + badge_gap
        badge = pygame.Surface((bw, bh), pygame.SRCALPHA)
        pygame.draw.rect(badge, (26, 21, 16, 235), badge.get_rect(), border_radius=bh // 2)
        pygame.draw.rect(badge, (150, 120, 70), badge.get_rect(), 1, border_radius=bh // 2)
        self.window.blit(badge, (bx, by))
        self.window.blit(label, (bx + 6, by + 2))

    def render(self):
        with perf_section('conquer.fill'):
            self.window.fill(settings.BACKGROUND_COLOR)
        if not self._ensure_conquer_screen_game() or not self.state.game:
            return

        with perf_section('conquer.prep'):
            self._normalize_conquer_subscreen()
            if self._is_tactics_hand_game():
                sequencer = getattr(self, '_conquer_reveal_sequencer', None)
                if sequencer is not None:
                    with perf_section('conquer.reveal_pump'):
                        sequencer.pump()
                self._update_conquer_support_hover_state()
                self._update_conquer_battle_dim_flags()
                self._apply_conquer_support_hover_visibility()
                self._sync_conquer_timeline_hover_state()

        subscreen = self.subscreens.get(self.state.subscreen)
        if subscreen:
            with perf_section(f'conquer.subscreen.{self.state.subscreen}'):
                subscreen.draw()
        # Restore any temporarily-flipped opponent icons after the subscreen
        # render so subsequent code paths see unmodified visibility.
        with perf_section('conquer.restore_hover'):
            self._restore_conquer_support_hover_visibility()
        with perf_section('conquer.duel_lane'):
            self._draw_conquer_duel_lane_cached()
        # Re-draw field figure icons (and their info boxes) above the duel
        # lane so figures always stay in the foreground. Limit the redraw
        # to icons that actually intersect the duel lane (performance).
        if self.state.subscreen == 'field' and subscreen is not None:
            overlay = getattr(subscreen, 'draw_figures_overlay', None)
            if callable(overlay):
                try:
                    with perf_section('conquer.figure_overlay'):
                        clip = getattr(self, '_conquer_duel_lane_last_rect', None)
                        subscreen._figure_overlay_clip_rect = clip
                        overlay()
                except Exception:
                    pass

        # Opponent's hidden hand: face-down tactic cards on the far-right strip,
        # a truthful destination for opponent card-effect spell animations.
        with perf_section('conquer.opp_hand'):
            self._draw_conquer_opponent_hand_strip()

        with perf_section('conquer.timeline_header'):
            use_collapsed_header = self._should_use_collapsed_conquer_header()
            if use_collapsed_header:
                self._draw_conquer_collapsed_header()
                if self._is_conquer_timeline_overlay_open():
                    overlay_rect = self._conquer_timeline_expanded_rect or \
                        self._conquer_timeline_overlay_rect()
                    panel = self._conquer_timeline_panel
                    if hasattr(panel, 'draw_within'):
                        reserve_w = self._conquer_timeline_overlay_right_reserve()
                        panel.draw_within(self, pygame.Rect(overlay_rect), reserve_w)
                    else:
                        panel.draw(self)
                    # The overlay paints over the timeline row, which means the
                    # collapse chevron and round countdown drawn by
                    # ``_draw_conquer_collapsed_header`` get covered. Re-draw the
                    # countdown label and chevron toggle on top of the overlay
                    # so the user can always read the timer and collapse the
                    # panel.
                    self._redraw_collapsed_header_chrome_over_overlay(
                        pygame.Rect(overlay_rect))
            else:
                self._conquer_timeline_hover_open = False
                self._conquer_timeline_expanded_rect = None
                self._conquer_timeline_panel.draw(self)

        with perf_section('conquer.nav'):
            for button in self._conquer_nav_buttons():
                button.draw()
            for button in self._conquer_nav_buttons():
                if hasattr(button, 'draw_hover_text'):
                    button.draw_hover_text()
            self._draw_tab_state()
        # Tactics-hand games show the persistent rail + ledger instead of
        # the small 10-icon HUD panel used by legacy battle_move conquer.
        with perf_section('conquer.rail_ledger'):
            if self._is_tactics_hand_game():
                self._tactics_rail.draw()
                self._round_ledger.draw()
                self._draw_tactic_flight_animation()
                self._draw_conquer_battle_feed()
            else:
                self._draw_conquer_battle_moves_panel()

        # Spell / round visual effects layer (projectiles, impacts, banners).
        # Runs after rails so animations float above HUD chrome.
        try:
            with perf_section('conquer.effects'):
                self._pump_conquer_spell_animations()
                self._draw_conquer_spell_target_ghosts()
                self._conquer_effects.draw()
        except Exception:
            pass

        # Shared top-level overlays used by the conquer flow.
        with perf_section('conquer.overlays'):
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

            if (not use_collapsed_header) or self._is_conquer_timeline_overlay_open() \
                    or self._is_tactics_hand_game():
                self._conquer_timeline_panel.draw_hover_tooltips(self)

        with perf_section('conquer.coach'):
            self._draw_conquer_battle_coach()
            if getattr(self, '_battle_intro_dialogue', None) is not None:
                self._battle_intro_dialogue.draw()

        # Camera shake, applied post-composition so the whole scene moves
        # as one. scroll() shifts the frame in place; the vacated edge
        # strips are refilled with a copy of the pre-scroll edge (instead of
        # flat background color) so shakes never flash bright seams. The
        # snapshots are at most two ≤8px strips, and only on shake frames.
        with perf_section('conquer.shake'):
            try:
                dx, dy = self._conquer_effects.screen_shake_offset()
                if dx or dy:
                    dx = max(-8, min(8, int(dx)))
                    dy = max(-8, min(8, int(dy)))
                    w, h = self.window.get_size()
                    strips = []
                    if dx > 0:
                        strips.append((self.window.subsurface(
                            pygame.Rect(0, 0, dx, h)).copy(), (0, 0)))
                    elif dx < 0:
                        strips.append((self.window.subsurface(
                            pygame.Rect(w + dx, 0, -dx, h)).copy(), (w + dx, 0)))
                    if dy > 0:
                        strips.append((self.window.subsurface(
                            pygame.Rect(0, 0, w, dy)).copy(), (0, 0)))
                    elif dy < 0:
                        strips.append((self.window.subsurface(
                            pygame.Rect(0, h + dy, w, -dy)).copy(), (0, h + dy)))
                    self.window.scroll(dx, dy)
                    for strip, pos in strips:
                        self.window.blit(strip, pos)
            except Exception:
                pass

    # ----------------------------------------------------------------- update

    def _play_conquer_transition_sounds(self):
        """Fire the battle-start moment once, when the tactics phase begins.

        The moment must land exactly when the clash begins — the frame the
        power diff appears (``battle_turn_player_id`` gets assigned) — not on
        screen entry, because the player spends a visible pre-battle beat on
        this screen first (prelude / figure setup).  We therefore watch for
        the pre-battle → tactics transition on-screen.

        Suppression: a reload/resume straight into an already-active battle
        never watched the transition, so it stays silent.  The config
        screen's ``state.conquer_battle_countdown_pending`` flag is honoured
        as a "freshly started" hint for the rare case where the tactics
        phase is already active on the very first frame (pre-battle skipped).

        Tactics-hand games get the "3·2·1·GO!" countdown (the war drum lands
        on GO); legacy battle-move games get the immediate drum.
        """
        try:
            game = self.state.game
            if game is None or self._conquer_countdown_done:
                return
            # "Active" == the tactics phase is on-screen: the exact predicate
            # that makes the fighters + power diff appear in the duel lane, so
            # the moment lands on the frame the diff shows.
            active = bool(self._is_battle_phase_active()
                          and not getattr(game, 'last_battle_result', None))
            fresh_start = bool(getattr(
                self.state, 'conquer_battle_countdown_pending', False))
            if not active:
                # Still pre-battle: remember we watched this side of the
                # transition so the upcoming edge is known to be genuine.
                self._conquer_saw_prebattle = True
                return
            # Tactics phase is active.
            self._conquer_countdown_done = True
            self.state.conquer_battle_countdown_pending = False
            if not (self._conquer_saw_prebattle or fresh_start):
                # First-ever frame was already active with no fresh-start
                # hint → we reloaded mid-battle. Stay silent.
                return
            from utils import sound
            if not self._start_conquer_battle_countdown():
                sound.play('battle_start')
        except Exception:
            pass

    #: Battle-start countdown timing (three number beats + the GO beat).
    COUNTDOWN_BEAT_MS = 500
    COUNTDOWN_GO_MS = 700

    def _conquer_clash_diff_hidden(self):
        """True while the battle-start moment plays: the figures clash-diff
        number stays masked ("VS") until the "3·2·1·GO!" countdown and the
        lane-fighter entrance animations finish, so the real number is only
        revealed once the reveal sequence completes — never before."""
        try:
            if self._is_battle_countdown_active():
                return True
            if getattr(self, '_conquer_lane_figure_entrances', None):
                return True
        except Exception:
            pass
        return False

    def _conquer_battle_clash_rect(self):
        """Rect of the clash-diff panel in the active battle layout, or None.

        Computed from the layout (not the render-stashed rect) so it is
        correct on the very frame the battle starts — before the lane has
        re-rendered in the battle layout.
        """
        try:
            layout = compute_conquer_layout(
                settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT,
                mode=self._conquer_effective_layout_mode())
            lane = layout.battlefield.duel_lane
            return self._conquer_lane_center_channel_rect(lane.diff_band, lane)
        except Exception:
            return getattr(self, '_conquer_lane_diff_rect', None)

    def _start_conquer_battle_countdown(self):
        """Kick off the "3·2·1·GO!" battle-start moment (tactics-hand only).

        Returns True when the countdown was started — the caller then defers
        the war drum to the GO beat.  Fail-soft: any problem returns False
        and the caller falls back to the plain ``battle_start`` drum.
        """
        try:
            if not self._is_tactics_hand_game():
                return False
            game = self.state.game
            if game is None or getattr(game, 'last_battle_result', None):
                return False
            effects = getattr(self, '_conquer_effects', None)
            if effects is None:
                return False
            now = pygame.time.get_ticks()
            # Anchor the countdown to the clash-diff panel so it plays right
            # in the centre where the battle resolves; stash the rect so the
            # GO spotlight targets the same spot.  Font is sized to the panel
            # height so the digits sit inside the panel (compact style).
            clash_rect = self._conquer_battle_clash_rect()
            font_px = None
            if clash_rect is not None:
                self._conquer_lane_diff_rect = pygame.Rect(clash_rect)
                font_px = max(16, int(clash_rect.height * 0.9))
            effects.spawn_countdown(
                ('3', '2', '1', 'GO!'),
                beat_ms=self.COUNTDOWN_BEAT_MS,
                final_ms=self.COUNTDOWN_GO_MS,
                anchor_rect=clash_rect,
                font_px=font_px)
            self._battle_countdown_started_ms = now
            self._battle_countdown_until_ms = (
                now + 3 * self.COUNTDOWN_BEAT_MS + self.COUNTDOWN_GO_MS)
            self._battle_countdown_last_beat = -1
            # Live battle-start transition: reset the lane seen-set so the
            # fighters play their entrance during the countdown, even when
            # the auto-route lands here with the battle already flagged
            # active (the silent-seed path would otherwise swallow it).
            self._conquer_lane_figure_seen = set()
            self._conquer_lane_figure_entrances = {}
            self.push_conquer_feed('Battle begins!', (255, 211, 116))
            return True
        except Exception:
            return False

    def _is_battle_countdown_active(self):
        until = int(getattr(self, '_battle_countdown_until_ms', 0) or 0)
        return bool(until and pygame.time.get_ticks() < until)

    def _skip_conquer_battle_countdown(self):
        """Collapse the countdown immediately (click-to-skip)."""
        went_early = self._battle_countdown_last_beat < 3
        self._battle_countdown_until_ms = 0
        self._battle_countdown_last_beat = -1
        effects = getattr(self, '_conquer_effects', None)
        if effects is not None:
            try:
                effects.dismiss_countdowns()
            except Exception:
                pass
        if went_early:
            # The GO beat owns the war drum — keep it on a skip for closure.
            try:
                from utils import sound
                sound.play('battle_start')
            except Exception:
                pass

    def _pump_conquer_battle_countdown(self):
        """Per-beat countdown sounds: soft ticks on 3/2/1, drum + jolt on GO."""
        if not getattr(self, '_battle_countdown_until_ms', 0):
            return
        now = pygame.time.get_ticks()
        if now >= self._battle_countdown_until_ms:
            self._battle_countdown_until_ms = 0
            self._battle_countdown_last_beat = -1
            return
        beat = min(3, (now - self._battle_countdown_started_ms)
                   // self.COUNTDOWN_BEAT_MS)
        if beat == self._battle_countdown_last_beat:
            return
        self._battle_countdown_last_beat = beat
        try:
            from utils import sound
            if beat >= 3:
                sound.play('battle_start')
                self._spotlight_conquer_clash_diff()
            else:
                sound.play('tally_tick')
        except Exception:
            pass

    def _spotlight_conquer_clash_diff(self):
        """GO beat: jolt the screen and spotlight the clash-diff panel so the
        eye lands on the power comparison as the tactics phase opens."""
        effects = getattr(self, '_conquer_effects', None)
        if effects is None:
            return
        try:
            effects.spawn_shake(amplitude=4, duration_ms=220)
            diff_rect = getattr(self, '_conquer_lane_diff_rect', None)
            if diff_rect is None:
                return
            diff_rect = pygame.Rect(diff_rect)
            # Layered pulses + a small upward spark burst read as a spotlight
            # snapping onto the diff panel.
            effects.spawn_rect_pulse(diff_rect, (238, 206, 130),
                                     secondary=(255, 236, 170),
                                     duration_ms=720, scale=1.3)
            effects.spawn_rect_pulse(diff_rect, (255, 236, 170),
                                     duration_ms=520, scale=1.0, delay_ms=150)
            effects.spawn_burst(diff_rect, (238, 206, 130),
                                secondary=(150, 230, 170),
                                count=12, upward_bias=0.45,
                                speed=(140.0, 250.0))
        except Exception:
            pass

    def update(self, events):
        self._play_conquer_transition_sounds()
        if not self._ensure_conquer_screen_game():
            return
        self._pump_conquer_result_payoff()
        self._pump_conquer_battle_countdown()
        self._normalize_conquer_subscreen()
        self._refresh_conquer_tab_locks()

        for button in self._conquer_nav_buttons():
            button.update(self.state)

        self._normalize_conquer_subscreen()

        if not self.state.game:
            return

        with perf_section('conquer.update.battle_state_poll'):
            self._request_battle_state_poll(force=False)
        # Drain any in-flight async start_turn responses every frame so that
        # auto-fill / opponent-turn summaries land as soon as the XHR returns,
        # not only on the next 2s update_game tick.
        with perf_section('conquer.update.start_turn_drain'):
            try:
                self.state.game.drain_pending_start_turn()
            except Exception:
                pass

        current_time = pygame.time.get_ticks()
        if current_time - self.last_update_time >= self.update_interval:
            self.last_update_time = current_time
            if not self._uses_lightweight_active_battle_polling():
                with perf_section('conquer.update.full_game_poll'):
                    self.update_game()
            self._check_battle_cycle_reset()
            self._refresh_conquer_tab_locks()
            self._sync_conquer_action_modes()
            self._auto_route_conquer_once()

        subscreen = self.subscreens.get(self.state.subscreen)
        if subscreen:
            with perf_section(f'conquer.update.subscreen.{self.state.subscreen}'):
                subscreen.update(self.state.game)
        with perf_section('conquer.update.bookkeeping'):
            if getattr(self.state.game, 'pending_defender_selection', False):
                self.check_defender_selection_needed()
            self._sync_conquer_action_modes()
            self._sync_pending_confirmation_state()
            self._enforce_battle_shop_during_moves()
            self._maybe_show_battle_intro_window()
            if not self._conquer_battle_intro_paused():
                self._maybe_auto_trigger_finish_battle()
                self._maybe_auto_advance_single_option_step()
            else:
                self._finish_battle_available_since_ms = None
                self._auto_single_option_pending = None

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
                      and self.state.game.advancing_figure_id
                      and self.state.game.pending_defender_selection):
                    self.state.subscreen = 'field'
                    field_screen = self.subscreens.get('field')
                    if field_screen:
                        field_screen.defender_selection_mode = True
                        field_screen._update_defender_selectable()
                    self.state.game.defender_selection_dialogue_shown = True
                elif (response == 'ok' and self.state.game
                      and getattr(self.state.game, 'advancing_figure_id', None)
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

        # While the battle-start countdown plays, any click skips straight
        # to GO (and never leaks into the UI below).
        if self._is_battle_countdown_active():
            for event in events:
                if event.type == MOUSEBUTTONDOWN and event.button == 1:
                    self._skip_conquer_battle_countdown()
                    break
            return

        # While the battle-result payoff is staged, clicks skip ahead and
        # never leak into the UI below.  Placed before the battle intro /
        # coach / command / header / rail dispatch on purpose: a payoff
        # click must not trigger those handlers.
        if getattr(self, '_conquer_payoff_pending', None) is not None:
            for event in events:
                if event.type == MOUSEBUTTONDOWN and event.button == 1:
                    if self._conquer_payoff_until_ms:
                        # Payoff already playing → collapse to "done" so the
                        # next update() opens the result dialogue.
                        self._conquer_payoff_until_ms = pygame.time.get_ticks()
                    else:
                        # Still waiting on the round reveal → fast-forward it.
                        sequencer = getattr(self, '_conquer_reveal_sequencer', None)
                        if sequencer is not None:
                            try:
                                sequencer.fast_forward()
                            except Exception:
                                pass
                    break
            return

        if self._handle_battle_intro_window_events(events):
            return

        if self._handle_conquer_battle_coach_events(events):
            return

        if self._handle_conquer_command_events(events):
            return

        if self._handle_collapsed_header_events(events):
            return

        if self._handle_conquer_touch_pin_events(events):
            return

        # Tactics-hand rail + ledger event capture (Phase 9 redesign).
        # Runs *before* subscreen event handling so the rail can intercept
        # clicks that would otherwise hit the field/battle subscreen.
        if self._is_tactics_hand_game():
            # While a round-reveal sequence plays, any click fast-forwards
            # it to the resolved state instead of acting on the UI below.
            sequencer = getattr(self, '_conquer_reveal_sequencer', None)
            if sequencer is not None and sequencer.is_active():
                for event in events:
                    if event.type == MOUSEBUTTONDOWN and event.button == 1:
                        sequencer.fast_forward()
                        return
                return
            for event in events:
                if (event.type == MOUSEBUTTONDOWN and event.button == 1
                        and self._handle_conquer_lane_figure_click(event.pos)):
                    return
                ledger_action = self._round_ledger.handle_event(event)
                if ledger_action == 'open_result':
                    self._clear_conquer_touch_pins()
                    self._open_tactics_hand_result_dialogue()
                    return
                if ledger_action:
                    self._clear_conquer_touch_pins(except_for='ledger')
                    return
                if self._tactics_rail.handle_event(event):
                    pending = self._tactics_rail.consume_pending_action()
                    if pending:
                        self._dispatch_tactics_rail_action(pending)
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

        # Legacy conquer tabs stay accessible; tactics-hand games use the unified field canvas.
        for button in self._conquer_nav_buttons():
            button.update(self.state)
        self._normalize_conquer_subscreen()

        if self.waiting_for_counter_response:
            return

        active_step = self.active_conquer_timeline_step()
        subscreen = self.subscreens.get(self.state.subscreen)
        if active_step is not None and not active_step.interactive:
            if not (subscreen and getattr(subscreen, 'dialogue_box', None)):
                can_inspect_field = (
                    self.state.subscreen == 'field'
                    and subscreen is not None
                    and callable(getattr(
                        subscreen, '_is_tactics_hand_battle_field_view_only', None))
                    and subscreen._is_tactics_hand_battle_field_view_only()
                )
                if can_inspect_field:
                    subscreen.handle_events(events)
                return

        # Field-required actions are handled by FieldScreen, but the player may
        # still inspect other tabs manually.  Only the active tab receives game
        # events.
        if subscreen:
            subscreen.handle_events(events)
            if self.state.game and self.state.game.pending_battle_ready:
                self.check_battle_ready()
