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
        try:
            if self._is_tactics_hand_game() and action == ACTION_PLAY and mid is not None:
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
        self._tactics_rail.reset_after_action()
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

    def _current_conquer_battle_moves(self):
        game = self.state.game
        if not game:
            return []

        if self._is_tactics_hand_game():
            game_id = getattr(game, 'game_id', None)
            player_id = getattr(game, 'player_id', None)
            if not game_id or not player_id:
                return list(getattr(game, 'conquer_tactics', []) or [])

            cache_key = (
                'tactics',
                game_id,
                player_id,
                getattr(game, '_game_data_version', 0),
                getattr(game, 'battle_turn_player_id', None),
                getattr(game, 'battle_round', None),
            )
            if cache_key == getattr(self, '_conquer_battle_move_cache_key', None):
                return list(getattr(self, '_conquer_battle_move_cache', []) or [])
            try:
                result = game_service.get_battle_state(game_id, player_id)
                moves = result.get('player_tactics') or result.get('player_moves') or []
            except Exception:
                moves = list(getattr(self, '_conquer_battle_move_cache', []) or [])
            self._conquer_battle_move_cache_key = cache_key
            self._conquer_battle_move_cache = [dict(move) for move in moves]
            self._sync_conquer_battle_move_subscreen_cache(self._conquer_battle_move_cache)
            return list(self._conquer_battle_move_cache)

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
            player_moves = self._current_conquer_battle_moves() or []
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

    @staticmethod
    def _conquer_lane_surface(asset, size):
        if not isinstance(asset, pygame.Surface):
            return None
        return pygame.transform.smoothscale(asset, (size, size))

    def _draw_conquer_lane_figure_art(self, figure, center, size):
        family = getattr(figure, 'family', None)
        frame = self._conquer_lane_surface(getattr(family, 'frame_img', None), size)
        icon_size = max(1, int(size * 0.58))
        icon = self._conquer_lane_surface(
            getattr(family, 'icon_img', None) or getattr(family, 'icon_img_small', None),
            icon_size,
        )
        fallback_rect = pygame.Rect(0, 0, icon_size, icon_size)
        fallback_rect.center = center
        pygame.draw.circle(self.window, (43, 37, 30), center, size // 2)
        pygame.draw.circle(self.window, (203, 176, 104), center, size // 2, 2)
        if icon:
            self.window.blit(icon, icon.get_rect(center=center))
        else:
            pygame.draw.rect(self.window, (110, 94, 64), fallback_rect, border_radius=6)
        if frame:
            self.window.blit(frame, frame.get_rect(center=center))

    def _draw_conquer_lane_band(self, rect, label, figures, *, is_player):
        band = pygame.Rect(rect).inflate(-8, -6)
        if band.width <= 0 or band.height <= 0:
            return
        bg = (34, 44, 50, 175) if is_player else (52, 40, 43, 175)
        border = (138, 190, 196) if is_player else (196, 145, 132)
        pygame.draw.rect(self.window, bg, band, border_radius=7)
        pygame.draw.rect(self.window, border, band, 1, border_radius=7)

        label_font = settings.get_font(max(10, int(settings.FS_TINY * 0.78)), bold=True)
        text = label_font.render(label, True, (230, 222, 190))
        self.window.blit(text, (band.left + 8, band.top + 5))

        if not figures:
            dash = label_font.render('-', True, (150, 132, 96))
            self.window.blit(dash, dash.get_rect(center=band.center))
            return

        name_font = settings.get_font(max(11, int(settings.FS_TINY * 0.90)), bold=True)
        value_font = settings.get_font(max(10, int(settings.FS_TINY * 0.82)), bold=True)
        count = min(2, len(figures))
        slot_w = max(1, band.width // count)
        art_size = max(26, min(int(band.height * 0.48), int(slot_w * 0.44)))
        for idx, figure in enumerate(figures[:2]):
            slot = pygame.Rect(band.left + idx * slot_w, band.top, slot_w, band.height)
            center = (slot.centerx, band.top + int(band.height * 0.48))
            self._draw_conquer_lane_figure_art(figure, center, art_size)
            name = self._fit_text(getattr(figure, 'name', 'Figure'), name_font, slot.width - 14)
            name_surf = name_font.render(name, True, (246, 239, 214))
            self.window.blit(name_surf, name_surf.get_rect(
                center=(slot.centerx, band.bottom - int(band.height * 0.18))))

            value = str(self._conquer_lane_figure_power(figure))
            value_surf = value_font.render(value, True, (42, 32, 20))
            chip = value_surf.get_rect()
            chip.inflate_ip(12, 6)
            chip.center = (center[0] + art_size // 2 - 3, center[1] - art_size // 2 + 4)
            pygame.draw.rect(self.window, (238, 206, 111), chip, border_radius=chip.height // 2)
            self.window.blit(value_surf, value_surf.get_rect(center=chip.center))

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

    def _draw_conquer_lane_diff(self, rect, player_figures, opponent_figures,
                                player_move=None, opponent_move=None, round_idx=0):
        band = pygame.Rect(rect).inflate(-12, -4)
        if band.width <= 0 or band.height <= 0:
            return
        pygame.draw.rect(self.window, (26, 25, 28, 190), band, border_radius=8)
        pygame.draw.rect(self.window, (226, 196, 112), band, 1, border_radius=8)
        player_power = sum(self._conquer_lane_figure_power(fig) for fig in player_figures)
        opponent_power = sum(self._conquer_lane_figure_power(fig) for fig in opponent_figures)
        player_total = player_power + self._conquer_lane_move_power(player_move)
        opponent_total = opponent_power + self._conquer_lane_move_power(opponent_move)
        diff = player_total - opponent_total
        diff_text = 'VS' if not player_figures or not opponent_figures else f'{diff:+d}'
        font = settings.get_font(max(14, int(settings.FS_SMALL * 1.05)), bold=True)
        color = (130, 220, 190) if diff > 0 else (226, 145, 130) if diff < 0 else (232, 220, 180)
        surf = font.render(diff_text, True, color)
        self.window.blit(surf, surf.get_rect(center=(band.centerx, band.centery - 5)))

        receipt_font = settings.get_font(max(9, int(settings.FS_TINY * 0.72)), bold=True)
        you_name = self._fit_text(self._conquer_lane_move_name(player_move), receipt_font, band.width // 2 - 10)
        opp_name = self._fit_text(self._conquer_lane_move_name(opponent_move), receipt_font, band.width // 2 - 10)
        you_line = f'R{round_idx + 1}  {player_power}+{self._conquer_lane_move_power(player_move)}={player_total}'
        opp_line = f'{opponent_power}+{self._conquer_lane_move_power(opponent_move)}={opponent_total}  R{round_idx + 1}'
        label_y = band.top + 7
        value_y = band.bottom - receipt_font.get_height() - 6
        you_label = receipt_font.render(you_name, True, (154, 218, 206))
        opp_label = receipt_font.render(opp_name, True, (226, 168, 152))
        you_value = receipt_font.render(you_line, True, (232, 220, 180))
        opp_value = receipt_font.render(opp_line, True, (232, 220, 180))
        self.window.blit(you_label, (band.left + 8, label_y))
        self.window.blit(opp_label, (band.right - opp_label.get_width() - 8, label_y))
        self.window.blit(you_value, (band.left + 8, value_y))
        self.window.blit(opp_value, (band.right - opp_value.get_width() - 8, value_y))

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
        pygame.draw.rect(backdrop, (226, 196, 112, 145), backdrop.get_rect(), 2, border_radius=8)
        self.window.blit(backdrop, lane_rect.topleft)

        player_slots, opponent_slots = self._conquer_lane_played_tactics()
        round_idx = self._conquer_lane_focus_round(player_slots, opponent_slots)
        player_move = player_slots[round_idx]
        opponent_move = opponent_slots[round_idx]
        preview_move = self._conquer_lane_preview_move(player_slots, round_idx)
        player_display_move = player_move if player_move is not None else preview_move
        player_move_is_preview = player_move is None and preview_move is not None

        self._draw_conquer_lane_band(lane.you_fighter_band, 'YOU', player_figures, is_player=True)
        self._draw_conquer_lane_diff(
            lane.diff_band,
            player_figures,
            opponent_figures,
            player_move=player_display_move,
            opponent_move=opponent_move,
            round_idx=round_idx,
        )
        opponent = getattr(self.state.game, 'opponent_name', None) or 'OPPONENT'
        opponent_font = settings.get_font(max(10, int(settings.FS_TINY * 0.78)), bold=True)
        self._draw_conquer_lane_band(
            lane.opp_fighter_band,
            self._fit_text(opponent.upper(), opponent_font, 86),
            opponent_figures,
            is_player=False,
        )
        self._draw_conquer_lane_leader_line(
            lane.you_support_badge_rail,
            lane.you_fighter_band,
            is_player=True,
            ghost=player_move_is_preview,
        )
        self._draw_conquer_lane_leader_line(
            lane.opp_support_badge_rail,
            lane.opp_fighter_band,
            is_player=False,
        )
        self._draw_conquer_lane_tactic_badge(
            lane.you_support_badge_rail,
            player_display_move,
            round_idx,
            is_player=True,
            ghost=player_move_is_preview,
        )
        self._draw_conquer_lane_tactic_badge(
            lane.opp_support_badge_rail,
            opponent_move,
            round_idx,
            is_player=False,
        )

    def render(self):
        self.window.fill(settings.BACKGROUND_COLOR)
        if not self._ensure_conquer_screen_game() or not self.state.game:
            return

        self._normalize_conquer_subscreen()

        subscreen = self.subscreens.get(self.state.subscreen)
        if subscreen:
            subscreen.draw()
        self._draw_conquer_duel_lane()

        use_collapsed_header = self._should_use_collapsed_conquer_header()
        if use_collapsed_header:
            self._draw_conquer_collapsed_header()
            if self._is_conquer_timeline_overlay_open():
                self._conquer_timeline_panel.draw(self)
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
