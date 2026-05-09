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
from game.components.conquer_round_ledger import ConquerRoundLedger
from game.components.conquer_layout import compute_conquer_layout
from game.components.conquer_tactics_rail import (
    ACTION_COMBINE,
    ACTION_DISMANTLE,
    ACTION_GAMBLE,
    ACTION_PLAY,
    ACTION_SKIP,
    ConquerTacticsRail,
)
from game.components.conquer_timeline_panel import ConquerTimelinePanel, AUTO_ADVANCE_MS
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
from utils import battle_shop_service, game_service
from utils.utils import GameButton


class ConquerGameScreen(GameScreen):
    """Focused conquer battle shell with Field / Battle Shop / Battle tabs."""

    CONQUER_SUBSCREENS = ('field', 'battle_shop', 'battle')
    # Unified top panel timeline + active info box.
    HEADER_H_FACTOR = 0.22
    CONQUER_BATTLE_MOVE_PANEL_MAX_MOVES = 10
    TIMELINE_OVERLAY_MS = 3500
    TACTIC_FLIGHT_MS = 320
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
        self._conquer_timeline_overlay_until = 0
        self._conquer_collapsed_header_rect = None
        self._conquer_timeline_collapse_rect = None
        self._conquer_tactic_cache_key = None
        self._conquer_tactic_cache = []
        self._conquer_opponent_tactic_cache_key = None
        self._conquer_opponent_tactic_cache = []
        self._conquer_battle_move_cache_key = None
        self._conquer_battle_move_cache = []
        self._conquer_battle_move_icon_caches = {}
        self._conquer_battle_move_manager = None
        self._conquer_move_panel_title_font = settings.get_font(
            max(10, int(settings.FS_TINY * 0.80)), bold=True)
        self._conquer_move_panel_empty_font = settings.get_font(
            max(12, int(settings.FS_TINY * 0.95)), bold=True)

        # Unified tactics-hand UI (Phase 9 redesign).  These are lightweight
        # overlays — when the active game uses ``conquer_move_model='tactics_hand'``
        # they render on top of the field/battle subscreens; for legacy
        # ``battle_move`` games they remain inert.
        self._tactics_rail = ConquerTacticsRail(self)
        self._round_ledger = ConquerRoundLedger(self)
        self._tactic_flight_animation = None

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

    def _should_use_collapsed_conquer_header(self):
        return (
            self._is_tactics_hand_game()
            and self._conquer_layout_mode() in ('battle', 'result')
        )

    def _is_conquer_timeline_overlay_open(self):
        return pygame.time.get_ticks() < getattr(
            self, '_conquer_timeline_overlay_until', 0)

    def _close_conquer_timeline_overlay(self):
        self._conquer_timeline_overlay_until = 0

    def _conquer_header_layout(self):
        mode = self._conquer_layout_mode()
        return compute_conquer_layout(
            settings.SCREEN_WIDTH,
            settings.SCREEN_HEIGHT,
            mode=mode,
        ).header

    def _conquer_header_title(self):
        game = self.state.game
        if not game:
            return 'Conquer Battle'
        tier = getattr(game, 'land_tier', None)
        opponent = getattr(game, 'opponent_name', None) or 'Defender'
        land = f'Tier {tier} Land' if tier else 'Conquer Battle'
        return f'{land} vs {opponent}'

    def _conquer_status_chips(self):
        game = self.state.game
        if not game:
            return []

        round_no = getattr(game, 'battle_round', 0) or 0
        result = getattr(game, 'last_battle_result', None)
        if result:
            phase = 'Result'
        elif round_no in (1, 2, 3):
            phase = f'Round {round_no}/3'
        else:
            phase = 'Battle'

        turn_pid = getattr(game, 'battle_turn_player_id', None)
        player_id = getattr(game, 'player_id', None)
        if result:
            turn = 'Resolved'
        elif turn_pid is None:
            turn = 'Preparing'
        elif turn_pid == player_id:
            turn = 'Your turn'
        else:
            turn = 'Opponent turn'

        chips = [phase, turn]
        tier = getattr(game, 'land_tier', None)
        if tier:
            chips.append(f'Stake: Tier {tier}')
        suit = getattr(game, 'land_suit_bonus_suit', None)
        bonus = getattr(game, 'land_suit_bonus_value', None)
        if suit and bonus:
            chips.append(f'{suit} +{bonus}')
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
        if turn_pid == player_id:
            return f'Round {round_no}: your tactic action is pending.'
        if turn_pid is not None:
            return f'Round {round_no}: waiting for the opponent tactic.'
        return 'Battle rounds are being prepared.'

    def _conquer_battle_timeline_steps(self, base_steps):
        game = self.state.game
        if not game:
            return base_steps
        battle_started = (
            getattr(game, 'battle_turn_player_id', None) is not None
            or getattr(game, 'battle_round', 0) in (1, 2, 3)
            or bool(getattr(game, 'last_battle_result', None))
        )
        if not battle_started:
            return base_steps

        player_slots, opponent_slots = self._conquer_lane_played_tactics()
        current_round = int(getattr(game, 'battle_round', 0) or 0) - 1
        opponent_name = getattr(game, 'opponent_name', None) or 'Opponent'
        steps = list(base_steps)
        for idx in range(3):
            you = player_slots[idx]
            opp = opponent_slots[idx]
            has_play = you is not None or opp is not None
            is_current = idx == current_round and not getattr(game, 'last_battle_result', None)
            if not has_play and not is_current:
                continue

            you_label = self._conquer_lane_move_name(you) if you else 'pending'
            opp_label = self._conquer_lane_move_name(opp) if opp else 'hidden'
            played = you is not None and opp is not None
            if played:
                diff = self._conquer_lane_move_power(you) - self._conquer_lane_move_power(opp)
                body = f'You played {you_label}; {opponent_name} played {opp_label}. Round diff {diff:+d}.'
                tone = 'good' if diff >= 0 else 'warning'
            elif you is not None:
                body = f'You played {you_label}. Waiting for {opponent_name}.'
                tone = 'waiting'
            elif opp is not None:
                body = f'{opponent_name} played {opp_label}. Choose your reply.'
                tone = 'action'
            else:
                body = 'Choose a tactic from the command rail.'
                tone = (
                    'action'
                    if getattr(game, 'battle_turn_player_id', None) == getattr(game, 'player_id', None)
                    else 'waiting'
                )

            icon_move = you or opp
            steps.append(TimelineStep(
                kind=f'battle_round_{idx + 1}',
                title=f'Round {idx + 1}',
                owner='',
                icon_kind='tactic',
                icon_payload={'move': icon_move} if icon_move else None,
                completed=played,
                active=is_current and not played,
                interactive=False,
                tone=tone,
                sidenote='tactics',
                info_headline=f'Round {idx + 1} tactics',
                info_body=body,
            ))
        return steps

    def _open_tactics_hand_result_dialogue(self):
        game = self.state.game
        result = getattr(game, 'last_battle_result', None) if game else None
        if isinstance(result, dict) and result.get('conquer_result'):
            self._handle_conquer_result_response(result)

    def _draw_conquer_status_chip(self, rect, label, border_color):
        pygame.draw.rect(self.window, (44, 36, 28), rect, border_radius=6)
        pygame.draw.rect(self.window, border_color, rect, 1, border_radius=6)
        font = self._conquer_badge_font
        text = self._fit_text(label, font, rect.width - 12)
        surf = font.render(text, True, (238, 218, 170))
        self.window.blit(surf, surf.get_rect(center=rect.center))

    def _conquer_withdraw_available(self):
        game = self.state.game
        if not game or getattr(game, 'game_over', False) or getattr(game, 'state', None) == 'finished':
            return False
        if getattr(self, '_withdraw_dialogue_open', False):
            return False
        try:
            return bool(self._is_current_player_conquer_attacker())
        except Exception:
            return False

    def _draw_conquer_header_button(self, rect, label, color):
        mouse = pygame.mouse.get_pos()
        hovered = rect.collidepoint(mouse)
        bg = tuple(min(255, c + 24) for c in color) if hovered else color
        pygame.draw.rect(self.window, bg, rect, border_radius=6)
        pygame.draw.rect(self.window, (238, 219, 172), rect, 1, border_radius=6)
        font = self._conquer_badge_font
        text = self._fit_text(label, font, rect.width - 12)
        surf = font.render(text, True, (255, 244, 216))
        self.window.blit(surf, surf.get_rect(center=rect.center))

    def _draw_conquer_collapsed_header(self):
        self._conquer_objective_action_rects = {}
        header = self._conquer_header_layout()
        if not header.status_strip_rect or not header.log_strip_rect:
            self._conquer_collapsed_header_rect = None
            return

        status_rect = pygame.Rect(*header.status_strip_rect)
        log_rect = pygame.Rect(*header.log_strip_rect)
        self._conquer_collapsed_header_rect = status_rect.union(log_rect)

        status = pygame.Surface(status_rect.size, pygame.SRCALPHA)
        status.fill((19, 18, 16, 242))
        self.window.blit(status, status_rect.topleft)
        pygame.draw.line(self.window, (189, 149, 75),
                         (status_rect.left, status_rect.bottom - 1),
                         (status_rect.right, status_rect.bottom - 1), 2)

        pad_x = max(12, int(settings.SCREEN_WIDTH * 0.018))
        title_font = self._conquer_header_font
        title = self._fit_text(
            self._conquer_header_title(),
            title_font,
            max(80, int(settings.SCREEN_WIDTH * 0.42)),
        )
        title_surf = title_font.render(title, True, (246, 222, 170))
        title_y = status_rect.centery - title_surf.get_height() // 2
        self.window.blit(title_surf, (pad_x, title_y))

        chip_gap = max(6, int(settings.SCREEN_WIDTH * 0.004))
        right_limit = status_rect.right - pad_x
        if self._conquer_withdraw_available():
            button_w = max(86, int(settings.SCREEN_WIDTH * 0.070))
            button_h = max(24, min(status_rect.height - 12, int(settings.SCREEN_HEIGHT * 0.030)))
            button_rect = pygame.Rect(
                right_limit - button_w,
                status_rect.centery - button_h // 2,
                button_w,
                button_h,
            )
            self._conquer_objective_action_rects['withdraw'] = button_rect
            self._draw_conquer_header_button(button_rect, 'Withdraw', (93, 52, 48))
            right_limit = button_rect.left - chip_gap

        chips = self._conquer_status_chips()
        chip_h = max(24, min(status_rect.height - 12, int(settings.SCREEN_HEIGHT * 0.030)))
        x = right_limit
        border_colors = ((255, 211, 116), (176, 209, 255), (165, 235, 168), (200, 180, 120))
        for idx, label in enumerate(reversed(chips)):
            font = self._conquer_badge_font
            chip_w = min(
                max(78, font.size(label)[0] + 22),
                int(settings.SCREEN_WIDTH * 0.16),
            )
            x -= chip_w
            rect = pygame.Rect(x, status_rect.centery - chip_h // 2, chip_w, chip_h)
            if rect.left <= pad_x + title_surf.get_width() + chip_gap:
                break
            color = border_colors[idx % len(border_colors)]
            self._draw_conquer_status_chip(rect, label, color)
            x -= chip_gap

        log = pygame.Surface(log_rect.size, pygame.SRCALPHA)
        log.fill((28, 22, 16, 228))
        self.window.blit(log, log_rect.topleft)
        pygame.draw.line(self.window, (92, 72, 46),
                         (log_rect.left, log_rect.bottom - 1),
                         (log_rect.right, log_rect.bottom - 1), 1)
        narration_font = self._conquer_hint_font
        narration = self._fit_text(
            self._conquer_narration_line(),
            narration_font,
            log_rect.width - 2 * pad_x,
        )
        narration_surf = narration_font.render(narration, True, (220, 204, 164))
        self.window.blit(
            narration_surf,
            (pad_x, log_rect.centery - narration_surf.get_height() // 2),
        )

    def _draw_conquer_timeline_collapse_button(self):
        title_h = int(settings.SCREEN_HEIGHT * 0.040)
        button_w = max(82, int(settings.SCREEN_WIDTH * 0.064))
        button_h = max(24, int(settings.SCREEN_HEIGHT * 0.030))
        pad = max(10, int(settings.SCREEN_WIDTH * 0.012))
        rect = pygame.Rect(
            settings.SCREEN_WIDTH - pad - button_w,
            title_h + 6,
            button_w,
            button_h,
        )
        self._conquer_timeline_collapse_rect = rect
        self._draw_conquer_header_button(rect, 'Collapse', (68, 58, 46))

    def _handle_collapsed_header_events(self, events):
        if not self._should_use_collapsed_conquer_header():
            return False
        rect = self._conquer_collapsed_header_rect
        if rect is None:
            header = self._conquer_header_layout()
            if header.status_strip_rect and header.log_strip_rect:
                rect = pygame.Rect(*header.status_strip_rect).union(
                    pygame.Rect(*header.log_strip_rect))
        if rect is None:
            return False
        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                collapse_rect = getattr(self, '_conquer_timeline_collapse_rect', None)
                if (self._is_conquer_timeline_overlay_open()
                        and collapse_rect is not None
                        and collapse_rect.collidepoint(event.pos)):
                    self._close_conquer_timeline_overlay()
                    return True
                if rect.collidepoint(event.pos):
                    self._conquer_timeline_overlay_until = (
                        pygame.time.get_ticks() + self.TIMELINE_OVERLAY_MS)
                    return True
        return False

    def _active_round_player_slot_rect(self):
        game = self.state.game
        round_idx = int(getattr(game, 'battle_round', 0) or 0) - 1 if game else -1
        if round_idx not in (0, 1, 2):
            return None
        layout = compute_conquer_layout(
            settings.SCREEN_WIDTH,
            settings.SCREEN_HEIGHT,
            mode=self._conquer_layout_mode(),
        )
        card = pygame.Rect(*layout.round_ledger.round_card_rects[round_idx])
        title_font = settings.get_font(max(10, int(settings.FS_TINY * 0.95)), bold=True)
        chip_w = int(card.width * 0.34)
        chip_y = card.top + 4 + title_font.get_height() + 4
        chip_h = card.bottom - chip_y - 6
        return pygame.Rect(card.left + 4, chip_y, chip_w - 8, chip_h)

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
            return

        progress = max(0.0, min(1.0, elapsed / duration))
        eased = 1 - (1 - progress) * (1 - progress)
        source = pygame.Rect(animation['source'])
        target = pygame.Rect(animation['target'])
        cx = int(source.centerx + (target.centerx - source.centerx) * eased)
        cy = int(source.centery + (target.centery - source.centery) * eased)

        move = animation.get('move') or {}
        name = move.get('family_name') or 'Tactic'
        if name == 'Dagger' and (move.get('card_id_b') or move.get('secondary_card_id')):
            name = '2x Dagger'
        power = 0 if name == 'Block' else int(move.get('value') or 0)
        font = settings.get_font(max(9, int(settings.FS_TINY * 0.85)), bold=True)
        label = self._fit_text(f'{name} {power}', font, max(72, target.width))
        label_surf = font.render(label, True, (218, 246, 244))
        pill = label_surf.get_rect()
        pill.inflate_ip(18, 10)
        pill.center = (cx, cy)
        panel = pygame.Surface(pill.size, pygame.SRCALPHA)
        panel.fill((38, 70, 72, 218))
        self.window.blit(panel, pill.topleft)
        pygame.draw.rect(self.window, (120, 205, 220), pill, 2, border_radius=pill.height // 2)
        self.window.blit(label_surf, label_surf.get_rect(center=pill.center))

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
                game_service.play_battle_move(gid, pid, mid)
            elif action == ACTION_SKIP:
                game_service.skip_battle_turn(gid, pid)
            elif self._is_tactics_hand_game() and action == ACTION_GAMBLE and mid is not None:
                game_service.gamble_conquer_tactic(gid, pid, mid)
            elif action == ACTION_GAMBLE and mid is not None:
                battle_shop_service.gamble_battle_move(gid, pid, mid)
            elif self._is_tactics_hand_game() and action == ACTION_DISMANTLE and mid is not None:
                game_service.dismantle_conquer_tactic(gid, pid, mid)
            elif action == ACTION_DISMANTLE and mid is not None:
                battle_shop_service.dismantle_battle_move(gid, pid, mid)
            elif action == ACTION_COMBINE and mid is not None:
                partner = action_payload.get('partner') or {}
                pmid = partner.get('id')
                if pmid is not None:
                    if self._is_tactics_hand_game():
                        game_service.combine_conquer_tactics(gid, pid, mid, pmid)
                    else:
                        battle_shop_service.combine_battle_moves(gid, pid, mid, pmid)
        except Exception:
            # Network errors are rendered via the standard polling cycle —
            # we don't want a transient failure to blow up the input loop.
            pass
        # Show a banner reflecting the action that was just submitted; the
        # rail's auto-glow will highlight any newly-arrived moves once the
        # next poll lands. (#8a / #8c)
        set_banner = getattr(rail, 'set_result_banner', None) if rail else None
        if callable(set_banner):
            label = f"{family} {rank}".strip()
            if action == ACTION_PLAY:
                set_banner(f"Played {label}", color=(180, 220, 160), ttl_ms=4500)
            elif action == ACTION_GAMBLE:
                set_banner(f"Gambling {label}…", color=(238, 218, 170), ttl_ms=5500)
            elif action == ACTION_COMBINE:
                set_banner(f"Combined {label}", color=(170, 200, 240), ttl_ms=4500)
            elif action == ACTION_DISMANTLE:
                set_banner(f"Dismantled {label}", color=(220, 170, 170), ttl_ms=4500)
            elif action == ACTION_SKIP:
                set_banner("Skipped battle turn", color=(190, 190, 190), ttl_ms=3500)
        self._tactics_rail.reset_after_action()
        self._conquer_tactic_cache_key = None  # force refetch
        self._conquer_battle_move_cache_key = None  # force refetch

    def _reset_game_screen_state(self):
        """Reset shared and conquer-only state when entering a different game."""
        super()._reset_game_screen_state()
        self.reset_conquer_panel_state()
        self._tactic_flight_animation = None
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
            font = settings.get_font(max(10, int(settings.FS_TINY * 0.80)), bold=True)
            self._conquer_move_panel_title_font = font
        return font

    def _conquer_move_empty_font(self):
        font = getattr(self, '_conquer_move_panel_empty_font', None)
        if font is None:
            font = settings.get_font(max(12, int(settings.FS_TINY * 0.95)), bold=True)
            self._conquer_move_panel_empty_font = font
        return font

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

        cache_key = (
            'tactics',
            game_id,
            player_id,
            getattr(game, '_game_data_version', 0),
            getattr(game, 'battle_turn_player_id', None),
            getattr(game, 'battle_round', None),
        )
        if cache_key == getattr(self, '_conquer_tactic_cache_key', None):
            return self._filter_conquer_tactics_by_displayed_step(
                list(getattr(self, '_conquer_tactic_cache', []) or []))
        try:
            result = game_service.get_battle_state(game_id, player_id)
            tactics = result.get('player_tactics') or result.get('player_moves') or []
            opponent_tactics = result.get('opponent_tactics') or result.get('opponent_moves') or []
            self._conquer_resolution_step_server = int(
                result.get('conquer_resolution_step') or 0)
        except Exception:
            tactics = list(getattr(self, '_conquer_tactic_cache', []) or [])
            opponent_tactics = list(getattr(self, '_conquer_opponent_tactic_cache', []) or [])
        self._conquer_tactic_cache_key = cache_key
        self._conquer_tactic_cache = [dict(move) for move in tactics]
        self._conquer_opponent_tactic_cache_key = cache_key
        self._conquer_opponent_tactic_cache = [
            dict(move) for move in opponent_tactics if isinstance(move, dict)
        ]
        return self._filter_conquer_tactics_by_displayed_step(
            list(self._conquer_tactic_cache))

    def _displayed_conquer_step(self):
        """Resolution step the client is currently displaying.

        Defaults to the server's authoritative ``conquer_resolution_step`` so
        without explicit animation handling the latest state is shown. The
        timeline panel may temporarily report a smaller value during a spell
        animation to keep pre-mutation tactics visible until the animation
        completes.
        """
        timeline = getattr(self, '_conquer_timeline_panel', None) \
            or getattr(self, 'conquer_timeline_panel', None)
        if timeline is not None:
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
        cached = getattr(self, '_conquer_resolution_step_server', None)
        if cached is not None:
            return int(cached)
        game = self.state.game
        return int(getattr(game, 'conquer_resolution_step', 0) or 0) if game else 0

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
            # spell_purged after displayed step → still alive (treat as 'available'
            # for the purposes of the rail rendering).
            if status == 'spell_purged':
                if discarded is None or int(discarded) <= displayed:
                    continue
                replay = dict(t)
                replay['status'] = 'available'
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
            return [
                dict(move)
                for move in (getattr(game, 'conquer_opponent_tactics', []) or [])
                if isinstance(move, dict)
            ]

        cache_key = (
            'tactics',
            game_id,
            player_id,
            getattr(game, '_game_data_version', 0),
            getattr(game, 'battle_turn_player_id', None),
            getattr(game, 'battle_round', None),
        )
        if cache_key != getattr(self, '_conquer_opponent_tactic_cache_key', None):
            self._current_conquer_tactics()
        return list(getattr(self, '_conquer_opponent_tactic_cache', []) or [])

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

    def _conquer_lane_figures(self):
        game = self.state.game
        field = self.subscreens.get('field') if hasattr(self, 'subscreens') else None
        figures = getattr(field, 'figures', []) or []
        if not game or not figures:
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
        if getattr(game, 'advancing_player_id', None) == getattr(game, 'player_id', None):
            return advancing, defending
        return defending, advancing

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
        player_slots = [None, None, None]
        opponent_slots = [None, None, None]

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

        return player_slots, opponent_slots

    def _conquer_lane_focus_round(self, player_slots, opponent_slots):
        game = self.state.game
        current = int(getattr(game, 'battle_round', 0) or 0) - 1 if game else -1
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
        current = int(getattr(game, 'battle_round', 0) or 0) - 1
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
        if not game:
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
            player_figs, opp_figs = self._conquer_lane_figures()
        except Exception:
            return ids
        for is_player in (True, False):
            try:
                entries = self._conquer_lane_support_entries(
                    player_figs, opp_figs, is_player=is_player)
            except Exception:
                entries = []
            for entry in entries or []:
                fig = entry.get('figure')
                fig_id = getattr(fig, 'id', None)
                if fig_id is not None:
                    ids.add(fig_id)
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
        for icon in getattr(field, 'figure_icons', []) or []:
            fig = getattr(icon, 'figure', None)
            fig_id = getattr(fig, 'id', None)
            icon.conquer_battle_dimmed = bool(
                fig_id is not None and fig_id not in involved)

    def _apply_conquer_support_hover_visibility(self):
        """Force the opponent field figure corresponding to the currently-
        hovered support badge to be face-up for this frame (#2)."""
        self._conquer_support_hover_visibility_restore = []
        hovered = getattr(self, '_conquer_hovered_support_badge', None)
        if not hovered:
            return
        fig_id = hovered.get('figure_id')
        if fig_id is None:
            return
        field = self.subscreens.get('field') if hasattr(self, 'subscreens') else None
        for icon in getattr(field, 'figure_icons', []) or []:
            fig = getattr(icon, 'figure', None)
            if getattr(fig, 'id', None) != fig_id:
                continue
            if not getattr(icon, 'is_visible', True):
                self._conquer_support_hover_visibility_restore.append(icon)
                icon.is_visible = True
            break

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
            return advancing_player_id != player_id
        return advancing_player_id == player_id

    def _conquer_lane_support_entries(self, player_figures, opponent_figures, *, is_player):
        game = self.state.game
        if not game:
            return []
        player_id = getattr(game, 'player_id', None)
        side_player_id = player_id if is_player else getattr(game, 'opponent_id', None)
        if side_player_id is None:
            battle_figs = player_figures if is_player else opponent_figures
            if battle_figs:
                side_player_id = getattr(battle_figs[0], 'player_id', None)
        if side_player_id is None:
            return []

        own_targets = player_figures if is_player else opponent_figures
        enemy_targets = opponent_figures if is_player else player_figures
        battle_ids = self._conquer_lane_battle_figure_ids()
        entries = []
        seen = set()

        def add(kind, figure, label, value_text, numeric_value=0,
                target_figure_ids=None, per_target_value=None):
            key = (kind, getattr(figure, 'id', None))
            if key in seen:
                return
            seen.add(key)
            entries.append({
                'kind': kind,
                'figure': figure,
                'label': label,
                'value': value_text,
                'numeric_value': int(numeric_value or 0),
                'target_figure_ids': list(target_figure_ids or []),
                'per_target_value': int(
                    numeric_value if per_target_value is None else per_target_value),
            })

        for figure in self._conquer_lane_all_figures():
            if getattr(figure, 'player_id', None) != side_player_id:
                continue
            fig_id = getattr(figure, 'id', None)
            in_battle = fig_id in battle_ids
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
                            per_target_value=per_target)

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
                        per_target_value=4)

            if (not in_battle
                    and self._conquer_lane_has_skill(figure, 'buffs_allies_defence')
                    and self._conquer_lane_is_defending_side(is_player=is_player)):
                value = self._conquer_lane_number_value(figure)
                add('buffs_allies_defence', figure, 'Wall', f'+{value}',
                    value * len(own_targets),
                    target_figure_ids=[getattr(t, 'id', None) for t in own_targets],
                    per_target_value=value)

            if (self._conquer_lane_has_skill(figure, 'blocks_bonus') and adv_suit
                    and any(getattr(target, 'suit', None) == adv_suit for target in enemy_targets)):
                add('blocks_bonus', figure, 'Block', 'Block')

            if (not in_battle
                    and self._conquer_lane_has_skill(figure, 'distance_attack') and adv_suit):
                da_targets = [t for t in enemy_targets if getattr(t, 'suit', None) == adv_suit]
                if da_targets:
                    value = self._conquer_lane_number_value(figure)
                    add('distance_attack', figure, 'Range', f'-{value}',
                        value, target_figure_ids=[getattr(t, 'id', None) for t in da_targets],
                        per_target_value=value)

        # Called figures: any figure referenced as call_figure_id on this
        # side's currently-played tactics (#1 — show called figures in the
        # support lane even when they are not "boosting" the lane sum).
        try:
            player_slots, opponent_slots = self._conquer_lane_played_tactics()
        except Exception:
            player_slots, opponent_slots = ([], [])
        side_slots = player_slots if is_player else opponent_slots
        for move in side_slots or []:
            if not isinstance(move, dict):
                continue
            cf_id = move.get('call_figure_id')
            if cf_id is None:
                continue
            cf = self._conquer_lane_find_figure(cf_id)
            if cf is None or getattr(cf, 'id', None) in battle_ids:
                continue
            label = self._conquer_lane_move_name(move) or 'Call'
            add('called', cf, label, '', 0,
                target_figure_ids=[],
                per_target_value=0)

        order = {
            'support_bonus': 0,
            'buffs_allies': 1,
            'buffs_allies_defence': 2,
            'blocks_bonus': 3,
            'distance_attack': 4,
            'called': 5,
        }
        return sorted(entries, key=lambda e: (order.get(e['kind'], 99), getattr(e['figure'], 'id', 0)))

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
        land_suit = getattr(game, 'land_suit_bonus_suit', None) if game else None
        land_bonus = getattr(game, 'land_suit_bonus_value', None) if game else None
        if land_suit and land_bonus and any(getattr(fig, 'suit', None) == land_suit for fig in figures or []):
            chips.append({'label': 'Land', 'value': f'+{int(land_bonus)}'})

        enchant_total = self._conquer_lane_enchantment_total(figures)
        if enchant_total:
            chips.append({'label': 'Spell', 'value': f'{enchant_total:+d}'})
        return chips

    @staticmethod
    def _conquer_lane_surface(asset, size):
        if not isinstance(asset, pygame.Surface):
            return None
        return pygame.transform.smoothscale(asset, (size, size))

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

    def _draw_conquer_lane_band(self, rect, label, figures, *, is_player):
        band = pygame.Rect(rect).inflate(-6, -4)
        if band.width <= 0 or band.height <= 0:
            return
        bg = (34, 44, 50, 165) if is_player else (52, 40, 43, 165)
        pygame.draw.rect(self.window, bg, band, border_radius=7)

        label_font = settings.get_font(max(10, int(settings.FS_TINY * 0.78)), bold=True)
        text = label_font.render(label, True, (230, 222, 190))
        self.window.blit(text, (band.left + 8, band.top + 4))

        if not figures:
            dash = label_font.render('-', True, (150, 132, 96))
            self.window.blit(dash, dash.get_rect(center=band.center))
            return

        # Compute full-power for each figure on this side.
        player_figures, opponent_figures = self._conquer_lane_figures()
        own_support = self._conquer_lane_support_entries(
            player_figures, opponent_figures, is_player=is_player)
        enemy_support = self._conquer_lane_support_entries(
            player_figures, opponent_figures, is_player=not is_player)
        side_blocked = any(e.get('kind') == 'blocks_bonus' for e in enemy_support)

        name_font = settings.get_font(max(11, int(settings.FS_TINY * 0.92)), bold=True)
        value_font = settings.get_font(max(12, int(settings.FS_TINY * 0.95)), bold=True)
        count = min(2, len(figures))
        slot_w = max(1, band.width // count)
        # Larger figure art.
        art_size = max(38, min(int(band.height * 0.70), int(slot_w * 0.62)))
        rects = getattr(self, '_conquer_lane_figure_rects', None)
        if rects is None:
            rects = []
            self._conquer_lane_figure_rects = rects
        for idx, figure in enumerate(figures[:2]):
            slot = pygame.Rect(band.left + idx * slot_w, band.top, slot_w, band.height)
            center = (slot.centerx, band.top + int(band.height * 0.46))
            # Hit rect for hover/click. Sized like the visible figure ring.
            hit = pygame.Rect(0, 0, art_size + 8, art_size + 8)
            hit.center = center
            mouse = pygame.mouse.get_pos()
            hovered = hit.collidepoint(mouse)
            self._draw_conquer_lane_figure_art(figure, center, art_size,
                                               hovered=hovered)
            # Block visualization: red ring + small "BLOCKED" tag.
            if side_blocked:
                ring = pygame.Rect(0, 0, art_size + 10, art_size + 10)
                ring.center = center
                pygame.draw.rect(self.window, (210, 70, 70), ring, 3,
                                 border_radius=max(4, ring.height // 6))
                tag_font = settings.get_font(max(8, int(settings.FS_TINY * 0.62)), bold=True)
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
            self.window.blit(name_surf, name_surf.get_rect(
                center=(slot.centerx, band.bottom - int(band.height * 0.14))))

            base = self._conquer_lane_figure_power(figure)
            total = self._conquer_lane_figure_full_power(
                figure,
                support_entries=own_support,
                enemy_support_entries=enemy_support,
                is_player=is_player,
            )
            # Legacy parity color coding: green when boosted, red when penalised, gold otherwise.
            if total > base:
                chip_bg = (40, 110, 60)
                text_col = (235, 250, 220)
            elif total < base:
                chip_bg = (148, 50, 50)
                text_col = (250, 230, 220)
            else:
                chip_bg = (238, 206, 111)
                text_col = (42, 32, 20)
            value_surf = value_font.render(str(total), True, text_col)
            chip = value_surf.get_rect()
            chip.inflate_ip(14, 7)
            chip.center = (center[0] + art_size // 2 - 2, center[1] - art_size // 2 + 4)
            pygame.draw.rect(self.window, chip_bg, chip, border_radius=chip.height // 2)
            pygame.draw.rect(self.window, (24, 18, 12), chip, 1, border_radius=chip.height // 2)
            self.window.blit(value_surf, value_surf.get_rect(center=chip.center))

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

    def _draw_conquer_lane_support_badge(self, badge, entry, *, is_player,
                                         pulse=False, hovered=False):
        figure = entry['figure']
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

        family = getattr(figure, 'family', None)
        icon_raw = getattr(family, 'icon_img', None) or getattr(family, 'icon_img_small', None)
        frame_raw = getattr(family, 'frame_img', None)
        art_size = max(12, int(badge.width * 0.58))
        art_center = (badge.centerx, badge.top + int(badge.height * 0.38))
        if isinstance(icon_raw, pygame.Surface):
            icon = pygame.transform.smoothscale(icon_raw, (art_size, art_size))
            self.window.blit(icon, icon.get_rect(center=art_center))
        else:
            fallback = pygame.Rect(0, 0, art_size, art_size)
            fallback.center = art_center
            pygame.draw.rect(self.window, (104, 94, 68), fallback, border_radius=5)
        if isinstance(frame_raw, pygame.Surface):
            frame_size = max(art_size + 8, int(badge.width * 0.75))
            frame = pygame.transform.smoothscale(frame_raw, (frame_size, frame_size))
            self.window.blit(frame, frame.get_rect(center=art_center))

        label_font = settings.get_font(max(7, int(settings.FS_TINY * 0.50)), bold=True)
        label = str(entry.get('label') or entry.get('kind') or 'Support')
        label_surf = label_font.render(
            self._fit_text(label, label_font, max(1, badge.width - 8)),
            True,
            (246, 239, 214),
        )
        label_bg = label_surf.get_rect()
        label_bg.inflate_ip(6, 3)
        label_bg.midtop = (badge.centerx, badge.top + 3)
        pygame.draw.rect(self.window, (24, 18, 12), label_bg, border_radius=max(2, label_bg.height // 3))
        self.window.blit(label_surf, label_surf.get_rect(center=label_bg.center))

        skill_size = max(12, int(badge.width * 0.28))
        skill_icon = self._load_conquer_skill_icon(entry['kind'], skill_size)
        skill_rect = pygame.Rect(badge.left + 4, badge.bottom - skill_size - 4,
                                 skill_size, skill_size)
        if skill_icon:
            self.window.blit(skill_icon, skill_rect.topleft)
        else:
            pygame.draw.rect(self.window, border, skill_rect, border_radius=3)
            tiny = settings.get_font(max(7, int(settings.FS_TINY * 0.50)), bold=True)
            letter = tiny.render(entry['label'][:1], True, (20, 16, 10))
            self.window.blit(letter, letter.get_rect(center=skill_rect.center))

        value_font = settings.get_font(max(7, int(settings.FS_TINY * 0.52)), bold=True)
        value = str(entry.get('value') or '')
        value_surf = value_font.render(self._fit_text(value, value_font, badge.width - 8), True, (246, 239, 214))
        value_chip = value_surf.get_rect()
        value_chip.inflate_ip(6, 4)
        value_chip.bottomright = (badge.right - 3, badge.bottom - 3)
        pygame.draw.rect(self.window, (24, 18, 12), value_chip, border_radius=value_chip.height // 2)
        pygame.draw.rect(self.window, border, value_chip, 1, border_radius=value_chip.height // 2)
        self.window.blit(value_surf, value_surf.get_rect(center=value_chip.center))

    def _register_conquer_support_badge_rect(self, badge, entry, *, is_player):
        rects = getattr(self, '_conquer_support_badge_rects', None)
        if rects is None:
            rects = []
            self._conquer_support_badge_rects = rects
        figure = entry.get('figure') if isinstance(entry, dict) else None
        rects.append({
            'rect': pygame.Rect(badge),
            'entry': entry,
            'figure_id': getattr(figure, 'id', None),
            'is_player': is_player,
        })

    def _current_conquer_support_hover_entry(self):
        mouse = pygame.mouse.get_pos()
        for info in reversed(getattr(self, '_conquer_support_badge_rects', []) or []):
            rect = info.get('rect')
            if rect and pygame.Rect(rect).collidepoint(mouse):
                return info
            source_rect = self._conquer_support_source_rect(info.get('figure_id'))
            if source_rect and source_rect.collidepoint(mouse):
                return info
        return None

    def _current_conquer_support_overflow_entry(self):
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
        source_id = support_info.get('figure_id') if support_info else None
        field = getattr(self, 'subscreens', {}).get('field') if hasattr(self, 'subscreens') else None
        if field is not None:
            field._conquer_hover_source_figure_id = source_id
        return support_info

    def _conquer_support_source_rect(self, figure_id):
        if figure_id is None:
            return None
        field = getattr(self, 'subscreens', {}).get('field') if hasattr(self, 'subscreens') else None
        icon = getattr(field, 'icon_cache', {}).get(figure_id) if field is not None else None
        rect = getattr(icon, 'rect_frame', None) or getattr(icon, 'rect_frame_big', None)
        return pygame.Rect(rect) if rect else None

    def _draw_conquer_lane_source_link(self, badge_rect, source_rect, *, is_player):
        badge_rect = pygame.Rect(badge_rect)
        source_rect = pygame.Rect(source_rect)
        start = badge_rect.midleft if is_player else badge_rect.midright
        target_center = source_rect.center
        # End the line at the field-figure ring edge instead of its centre.
        # The figure art is roughly inscribed in source_rect, so we approximate
        # the ring radius as min(width, height) / 2 and walk back along the
        # link direction.
        radius = max(4, min(source_rect.width, source_rect.height) // 2)
        dx = target_center[0] - start[0]
        dy = target_center[1] - start[1]
        dist = (dx * dx + dy * dy) ** 0.5
        if dist > radius:
            scale = (dist - radius) / dist
            end = (int(start[0] + dx * scale), int(start[1] + dy * scale))
        else:
            end = target_center
        color = (120, 220, 235, 210)
        pygame.draw.line(self.window, color, start, end, 3)
        pygame.draw.circle(self.window, color, start, 4)
        pygame.draw.circle(self.window, color, target_center,
                           radius, 2)

    def _draw_conquer_support_overflow_popover(self):
        info = self._current_conquer_support_overflow_entry()
        if not info:
            return
        entries = info.get('entries') or []
        if not entries:
            return
        anchor = pygame.Rect(info.get('rect'))
        is_player = info.get('is_player', True)
        font = settings.get_font(max(8, int(settings.FS_TINY * 0.58)), bold=True)
        title_font = settings.get_font(max(9, int(settings.FS_TINY * 0.66)), bold=True)
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
            figure = entry.get('figure')
            name = getattr(figure, 'name', 'Figure')
            label = entry.get('label') or entry.get('kind') or 'Support'
            value = entry.get('value') or ''
            text = self._fit_text(f'{label} {value} · {name}', font, panel.width - 16)
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
        if not entries:
            return

        visible = entries[:4]
        gap = max(4, int(rail.height * 0.018))
        badge_h = min(rail.width, max(24, (rail.height - gap * (len(visible) + 1)) // len(visible)))
        y = rail.top + gap
        mouse = pygame.mouse.get_pos()
        for entry in visible:
            badge = pygame.Rect(0, 0, max(1, rail.width - 4), badge_h)
            badge.centerx = rail.centerx
            badge.top = y
            source_rect = self._conquer_support_source_rect(
                getattr(entry.get('figure'), 'id', None))
            hovered = badge.collidepoint(mouse) or bool(
                source_rect and source_rect.collidepoint(mouse))
            self._register_conquer_support_badge_rect(badge, entry, is_player=is_player)
            self._draw_conquer_lane_support_badge(
                badge,
                entry,
                is_player=is_player,
                pulse=pulse,
                hovered=hovered,
            )
            y += badge_h + gap
        overflow = len(entries) - len(visible)
        if overflow > 0:
            font = settings.get_font(max(8, int(settings.FS_TINY * 0.58)), bold=True)
            text = font.render(f'+{overflow}', True, (246, 239, 214))
            chip = text.get_rect(center=(rail.centerx, rail.bottom - max(8, text.get_height())))
            chip.inflate_ip(10, 5)
            overflow_hovered = chip.collidepoint(mouse)
            if not hasattr(self, '_conquer_support_overflow_rects'):
                self._conquer_support_overflow_rects = []
            self._conquer_support_overflow_rects.append({
                'rect': pygame.Rect(chip),
                'entries': entries[len(visible):],
                'is_player': is_player,
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
        if not chips:
            return
        font = settings.get_font(max(7, int(settings.FS_TINY * 0.52)), bold=True)
        max_visible = min(4, len(chips))
        gap = max(3, int(rail.height * 0.014))
        chip_h = min(max(20, int(rail.width * 1.10)),
                     max(12, (rail.height - gap * (max_visible + 1)) // max_visible))
        y = rail.top + gap
        for chip_data in chips[:max_visible]:
            chip = pygame.Rect(rail.left + 1, y, max(1, rail.width - 2), chip_h)
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

        tiny = settings.get_font(max(8, int(settings.FS_TINY * 0.62)), bold=True)
        name_font = settings.get_font(max(8, int(settings.FS_TINY * 0.68)), bold=True)
        value_font = settings.get_font(max(11, int(settings.FS_TINY * 0.88)), bold=True)
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
            player_figures, opponent_figures = self._conquer_lane_figures()
            player_id = getattr(self.state.game, 'player_id', None)
            move_player_id = move.get('player_id')
            is_player = move_player_id is None or move_player_id == player_id
            support_entries = self._conquer_lane_support_entries(
                player_figures,
                opponent_figures,
                is_player=is_player,
            )
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
                best = self._conquer_best_call_figure_for_tactic(move)
                if best is not None:
                    return self._conquer_lane_call_effective_power(
                        move, best, support_entries)
            return self._conquer_lane_move_effective_power(move, support_entries)
        except Exception:
            return self._conquer_lane_move_power(move)

    def _conquer_best_call_figure_for_tactic(self, move):
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
        player_figures, opponent_figures = self._conquer_lane_figures()
        support_entries = self._conquer_lane_support_entries(
            player_figures,
            opponent_figures,
            is_player=True,
        )
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
        blocked = any(e.get('kind') == 'blocks_bonus'
                      for e in enemy_support_entries or [])

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

        return base + buffs + support + wall + enchant - da_penalty

    def _conquer_lane_figure_diff(self):
        """Player figure total power minus opponent figure total power."""
        player_figures, opponent_figures = self._conquer_lane_figures()
        if not player_figures and not opponent_figures:
            return 0
        p_support = self._conquer_lane_support_entries(
            player_figures, opponent_figures, is_player=True)
        o_support = self._conquer_lane_support_entries(
            player_figures, opponent_figures, is_player=False)
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
        land_suit = getattr(game, 'land_suit_bonus_suit', None) if game else None
        land_bonus = getattr(game, 'land_suit_bonus_value', None) if game else None
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

    @staticmethod
    def _conquer_support_entry_ids(entries, kind):
        return [
            getattr(entry.get('figure'), 'id', None)
            for entry in entries
            if entry.get('kind') == kind and getattr(entry.get('figure'), 'id', None) is not None
        ]

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
        blocked_by_enemy = any(entry.get('kind') == 'blocks_bonus' for entry in enemy_support_entries)
        own_block = any(entry.get('kind') == 'blocks_bonus' for entry in support_entries)
        support = 0 if blocked_by_enemy else raw_support
        land = 0 if blocked_by_enemy else land
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
                source_figure_ids=self._conquer_support_entry_ids(support_entries, 'support_bonus'),
            ))
        if buffs:
            rows.append(self._conquer_receipt_row(
                'Buffs',
                buffs,
                source_figure_ids=self._conquer_support_entry_ids(support_entries, 'buffs_allies'),
            ))
        if wall:
            rows.append(self._conquer_receipt_row(
                'Wall',
                wall,
                source_figure_ids=self._conquer_support_entry_ids(support_entries, 'buffs_allies_defence'),
            ))
        if land:
            land_suit = getattr(self.state.game, 'land_suit_bonus_suit', None)
            rows.append(self._conquer_receipt_row(
                'Land',
                land,
                source_figure_ids=[
                    getattr(fig, 'id', None) for fig in figures
                    if getattr(fig, 'suit', None) == land_suit and getattr(fig, 'id', None) is not None
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
                source_figure_ids=self._conquer_support_entry_ids(enemy_support_entries, 'distance_attack'),
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
                source_figure_ids=self._conquer_support_entry_ids(enemy_support_entries, 'blocks_bonus'),
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

    def _register_conquer_receipt_row_hitrects(self, area, rows, *, align_right,
                                                top_offset=0):
        """Populate ``_conquer_receipt_row_rects`` with hit-rects for each row.

        Used so hover-based UX (tooltips, support-source highlighting) works even
        when the rows themselves are not currently being blitted (e.g. compact
        summary mode).
        """
        area = pygame.Rect(area)
        font = settings.get_font(max(8, int(settings.FS_TINY * 0.62)), bold=True)
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
        font = settings.get_font(max(8, int(settings.FS_TINY * 0.62)), bold=True)
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

    def _draw_conquer_lane_diff(self, rect, player_figures, opponent_figures,
                                player_move=None, opponent_move=None, round_idx=0):
        band = pygame.Rect(rect).inflate(-12, -4)
        if band.width <= 0 or band.height <= 0:
            return
        pygame.draw.rect(self.window, (26, 25, 28, 176), band, border_radius=8)
        player_support = self._conquer_lane_support_entries(
            player_figures, opponent_figures, is_player=True)
        opponent_support = self._conquer_lane_support_entries(
            player_figures, opponent_figures, is_player=False)
        player_rows, player_total = self._conquer_lane_receipt_components(
            player_figures, player_move, player_support, opponent_support)
        opponent_rows, opponent_total = self._conquer_lane_receipt_components(
            opponent_figures, opponent_move, opponent_support, player_support)
        diff = player_total - opponent_total
        diff_text = 'VS' if not player_figures or not opponent_figures else f'{diff:+d}'
        font = settings.get_font(max(14, int(settings.FS_SMALL * 1.05)), bold=True)
        color = (130, 220, 190) if diff > 0 else (226, 145, 130) if diff < 0 else (232, 220, 180)
        surf = font.render(diff_text, True, color)
        self.window.blit(surf, surf.get_rect(center=(band.centerx, band.top + int(band.height * 0.24))))

        receipt_area_top = band.top + int(band.height * 0.42)
        receipt_h = max(1, band.bottom - receipt_area_top - 4)
        col_gap = max(8, band.width // 20)
        col_w = (band.width - col_gap - 16) // 2
        left_area = pygame.Rect(band.left + 8, receipt_area_top, col_w, receipt_h)
        right_area = pygame.Rect(band.right - 8 - col_w, receipt_area_top, col_w, receipt_h)
        # Compact single-line summary per side (hover full lane band for details).
        compact_font = settings.get_font(max(8, int(settings.FS_TINY * 0.62)), bold=True)
        left_text = self._fit_text(
            self._conquer_lane_compact_receipt(player_rows),
            compact_font, left_area.width)
        right_text = self._fit_text(
            self._conquer_lane_compact_receipt(opponent_rows),
            compact_font, right_area.width)
        left_surf = compact_font.render(left_text, True, (154, 218, 206))
        right_surf = compact_font.render(right_text, True, (226, 168, 152))
        self.window.blit(left_surf, (left_area.left, left_area.top))
        self.window.blit(right_surf, (right_area.right - right_surf.get_width(),
                                      right_area.top))
        # Always register row hit-rects (off-screen) so hover-based UX (e.g. tooltips
        # in tests) keeps working without requiring the expanded panel to be visible.
        self._register_conquer_receipt_row_hitrects(
            left_area, player_rows, align_right=False, top_offset=left_surf.get_height() + 2)
        self._register_conquer_receipt_row_hitrects(
            right_area, opponent_rows, align_right=True, top_offset=right_surf.get_height() + 2)
        # Hover-to-expand: when mouse is over either compact line, show the full row breakdown.
        mouse = pygame.mouse.get_pos()
        left_hit = pygame.Rect(left_area.left, left_area.top,
                               left_surf.get_width(), left_surf.get_height())
        right_hit = pygame.Rect(right_area.right - right_surf.get_width(),
                                right_area.top,
                                right_surf.get_width(), right_surf.get_height())
        if left_hit.collidepoint(mouse):
            expand = pygame.Rect(left_area.left, left_area.top + left_surf.get_height() + 2,
                                 left_area.width,
                                 max(0, left_area.bottom - (left_area.top + left_surf.get_height() + 2)))
            self._draw_conquer_lane_receipt_rows(
                expand, player_rows, align_right=False, color=(154, 218, 206))
        elif right_hit.collidepoint(mouse):
            expand = pygame.Rect(right_area.left,
                                 right_area.top + right_surf.get_height() + 2,
                                 right_area.width,
                                 max(0, right_area.bottom - (right_area.top + right_surf.get_height() + 2)))
            self._draw_conquer_lane_receipt_rows(
                expand, opponent_rows, align_right=True, color=(226, 168, 152))

    def _draw_conquer_duel_lane(self):
        if not (self._is_tactics_hand_game() and self._is_battle_phase_active()):
            return
        player_figures, opponent_figures = self._conquer_lane_figures()
        if not player_figures and not opponent_figures:
            return
        layout = compute_conquer_layout(
            settings.SCREEN_WIDTH,
            settings.SCREEN_HEIGHT,
            mode=self._conquer_layout_mode(),
        )
        lane = layout.battlefield.duel_lane
        lane_rect = pygame.Rect(lane.rect)
        backdrop = pygame.Surface(lane_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(backdrop, (18, 20, 24, 118), backdrop.get_rect(), border_radius=8)
        self.window.blit(backdrop, lane_rect.topleft)

        player_slots, opponent_slots = self._conquer_lane_played_tactics()
        round_idx = self._conquer_lane_focus_round(player_slots, opponent_slots)
        player_move = player_slots[round_idx]
        opponent_move = opponent_slots[round_idx]
        preview_move = self._conquer_lane_preview_move(player_slots, round_idx)
        player_display_move = player_move if player_move is not None else preview_move
        player_move_is_preview = player_move is None and preview_move is not None
        player_support = self._conquer_lane_support_entries(
            player_figures, opponent_figures, is_player=True)
        opponent_support = self._conquer_lane_support_entries(
            player_figures, opponent_figures, is_player=False)
        player_chips = self._conquer_lane_modifier_chips(player_display_move, player_figures)
        opponent_chips = self._conquer_lane_modifier_chips(opponent_move, opponent_figures)
        self._conquer_support_badge_rects = []
        self._conquer_support_overflow_rects = []
        self._conquer_receipt_row_rects = []
        self._conquer_lane_figure_rects = []

        # Side rails first (subpanel frames in background) so the figure
        # bands and diff band can paint their content on top — otherwise
        # the rail backdrops occlude figure power chips at lane edges (#3).
        self._draw_conquer_lane_support_rail(
            lane.you_support_badge_rail,
            player_support,
            is_player=True,
            pulse=player_move_is_preview,
        )
        self._draw_conquer_lane_support_rail(
            lane.opp_support_badge_rail,
            opponent_support,
            is_player=False,
        )
        self._draw_conquer_lane_chip_rail(
            lane.you_support_chip_rail,
            player_chips,
            is_player=True,
        )
        self._draw_conquer_lane_chip_rail(
            lane.opp_support_chip_rail,
            opponent_chips,
            is_player=False,
        )
        self._draw_conquer_lane_band(lane.you_fighter_band, 'YOU', player_figures, is_player=True)
        opponent = getattr(self.state.game, 'opponent_name', None) or 'OPPONENT'
        opponent_font = settings.get_font(max(10, int(settings.FS_TINY * 0.78)), bold=True)
        self._draw_conquer_lane_band(
            lane.opp_fighter_band,
            self._fit_text(opponent.upper(), opponent_font, 86),
            opponent_figures,
            is_player=False,
        )
        # Diff/math band drawn AFTER the side rails so the surrounding rail
        # frames cannot occlude the math numbers (#5).  Shrink the diff
        # band's drawn rect so that it stays inside the inner channel
        # between the badge/chip rails — otherwise its receipt text
        # collides with the tactic badges drawn on the chip rails.
        diff_inner = pygame.Rect(lane.diff_band)
        chip_w = max(0, lane.you_support_chip_rail[2])
        badge_w = max(0, lane.you_support_badge_rail[2])
        side_inset = chip_w + badge_w + 4
        diff_inner = pygame.Rect(
            diff_inner.left + side_inset, diff_inner.top,
            max(20, diff_inner.width - 2 * side_inset), diff_inner.height,
        )
        self._draw_conquer_lane_diff(
            diff_inner,
            player_figures,
            opponent_figures,
            player_move=player_display_move,
            opponent_move=opponent_move,
            round_idx=round_idx,
        )
        hovered_support = self._update_conquer_support_hover_state()
        if hovered_support:
            source_rect = self._conquer_support_source_rect(hovered_support.get('figure_id'))
            if source_rect:
                self._draw_conquer_lane_source_link(
                    hovered_support.get('rect'),
                    source_rect,
                    is_player=hovered_support.get('is_player', True),
                )
        self._draw_conquer_lane_tactic_badge(
            lane.you_support_chip_rail,
            player_display_move,
            round_idx,
            is_player=True,
            ghost=player_move_is_preview,
        )
        self._draw_conquer_lane_tactic_badge(
            lane.opp_support_chip_rail,
            opponent_move,
            round_idx,
            is_player=False,
        )
        self._draw_conquer_support_overflow_popover()

    def render(self):
        self.window.fill(settings.BACKGROUND_COLOR)
        if not self._ensure_conquer_screen_game() or not self.state.game:
            return

        self._normalize_conquer_subscreen()
        if self._is_tactics_hand_game():
            self._update_conquer_support_hover_state()
            self._update_conquer_battle_dim_flags()
            self._apply_conquer_support_hover_visibility()

        subscreen = self.subscreens.get(self.state.subscreen)
        if subscreen:
            subscreen.draw()
        # Restore any temporarily-flipped opponent icons after the subscreen
        # render so subsequent code paths see unmodified visibility.
        self._restore_conquer_support_hover_visibility()
        self._draw_conquer_duel_lane()

        use_collapsed_header = self._should_use_collapsed_conquer_header()
        if use_collapsed_header:
            self._draw_conquer_collapsed_header()
            if self._is_conquer_timeline_overlay_open():
                self._conquer_timeline_panel.draw(self)
                self._draw_conquer_timeline_collapse_button()
        else:
            self._conquer_timeline_panel.draw(self)

        for button in self._conquer_nav_buttons():
            button.draw()
        for button in self._conquer_nav_buttons():
            if hasattr(button, 'draw_hover_text'):
                button.draw_hover_text()
        self._draw_tab_state()
        # Tactics-hand games show the persistent rail + ledger instead of
        # the small 10-icon HUD panel used by legacy battle_move conquer.
        if self._is_tactics_hand_game():
            self._tactics_rail.draw()
            self._round_ledger.draw()
            self._draw_tactic_flight_animation()
        else:
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

        if (not use_collapsed_header) or self._is_conquer_timeline_overlay_open():
            self._conquer_timeline_panel.draw_hover_tooltips(self)

    # ----------------------------------------------------------------- update
    def update(self, events):
        if not self._ensure_conquer_screen_game():
            return
        self._normalize_conquer_subscreen()
        self._refresh_conquer_tab_locks()

        for button in self._conquer_nav_buttons():
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

        if self._handle_collapsed_header_events(events):
            return

        # Tactics-hand rail + ledger event capture (Phase 9 redesign).
        # Runs *before* subscreen event handling so the rail can intercept
        # clicks that would otherwise hit the field/battle subscreen.
        if self._is_tactics_hand_game():
            for event in events:
                if (event.type == MOUSEBUTTONDOWN and event.button == 1
                        and self._handle_conquer_lane_figure_click(event.pos)):
                    return
                if self._round_ledger.handle_event(event) == 'open_result':
                    self._open_tactics_hand_result_dialogue()
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
                return

        # Field-required actions are handled by FieldScreen, but the player may
        # still inspect other tabs manually.  Only the active tab receives game
        # events.
        if subscreen:
            subscreen.handle_events(events)
            if self.state.game and self.state.game.pending_battle_ready:
                self.check_battle_ready()
