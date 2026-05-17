# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Battle Screen — the 3-round battle phase between two figures.

Layout (left → right):
  1. Battle Moves Panel   – player's 3 selected moves with action buttons
  2. Figures Panel         – player & opponent battling figures + power difference
  3. Rounds Panel          – 3 round columns with move slots and round diffs
  4. Total Summary Circle  – running total of all differences
"""

import pygame
from pygame.locals import *
from config import settings
from game.core.figure_buffs import apply_buffs_allies_to_icon_map
from game.screens.sub_screen import SubScreen
from game.components.battle_moves.battle_move_manager import BattleMoveManager
from game.components.battle_moves.battle_move_detail_box import BattleMoveDetailBox
from game.components.battle_moves.battle_move_icon_renderer import draw_battle_move_icon
from game.components.figures.figure_icon import FieldFigureIcon
from game.components.figures.figure_manager import FigureManager
from game.components.figure_detail_box import FigureDetailBox
from utils import battle_shop_service
from utils import game_service
from utils.utils import Button
from game.components.dialogue_box import _DlgButton
from utils.background_poller import BackgroundPoller
import logging

logger = logging.getLogger('nk.screens.battle')



def _rescale_battle_icon(icon, scale):
    """Rescale a FieldFigureIcon's diamond/frame/glow surfaces for the battle screen.

    The info box below the icon is intentionally NOT scaled so it stays compact.
    """
    if scale == 1.0 or icon is None:
        return

    def _ss(surf, s):
        if surf is None:
            return surf
        w, h = surf.get_size()
        return pygame.transform.smoothscale(surf, (int(w * s), int(h * s)))

    # Icon images (colour + greyscale, normal + big)
    icon.icon_img = _ss(icon.icon_img, scale)
    icon.icon_gray_img = _ss(icon.icon_gray_img, scale)
    icon.icon_img_big = _ss(icon.icon_img_big, scale)
    icon.icon_gray_img_big = _ss(icon.icon_gray_img_big, scale)

    # Frame images (normal + closed, normal + big)
    for attr in ('frame_img', 'frame_closed_img', 'frame_hidden_img',
                 'frame_img_big', 'frame_closed_img_big', 'frame_hidden_img_big'):
        setattr(icon, attr, _ss(getattr(icon, attr, None), scale))

    # Glow surfaces
    for attr in ('glow_yellow', 'glow_yellow_big', 'glow_yellow_dark',
                 'glow_yellow_dark_big', 'glow_black', 'glow_white',
                 'glow_white_big', 'glow_orange', 'glow_orange_big'):
        setattr(icon, attr, _ss(getattr(icon, attr, None), scale))

    # Broken / advance overlays
    for attr in ('broken_icon', 'broken_icon_big'):
        setattr(icon, attr, _ss(getattr(icon, attr, None), scale))


class BattleScreen(SubScreen):
    """Screen for the 3-round battle phase.

    Both players take turns (invader first) playing one battle move per round.
    After all 6 moves (3 each) the outcome is decided.
    """

    def __init__(self, window, state, x: int = 0.0, y: int = 0.0, title=None):
        super().__init__(window, state.game, x, y, title)
        self.state = state
        self.game = state.game

        # ── managers ──
        self.battle_move_manager = BattleMoveManager()
        self.figure_manager = FigureManager()

        # ── fonts ──
        self.font_normal = settings.get_font(settings.BATTLE_SCREEN_FONT_SIZE)
        self.font_small = settings.get_font(settings.BATTLE_SCREEN_FONT_SIZE_SMALL)
        self.font_icon_value = settings.get_font(settings.BATTLE_ICON_VALUE_FONT_SIZE, bold=True)
        self.font_value = settings.get_font(settings.BATTLE_SCREEN_VALUE_FONT_SIZE, bold=True)
        self.font_diff = settings.get_font(settings.BATTLE_SCREEN_DIFF_FONT_SIZE, bold=True)
        self.font_total = settings.get_font(settings.BATTLE_SCREEN_TOTAL_FONT_SIZE, bold=True)
        self.font_round = settings.get_font(settings.ROUNDS_LABEL_FONT_SIZE, bold=True)
        self.font_turn = settings.get_font(settings.TURN_INDICATOR_FONT_SIZE, bold=True)
        self.font_power_circle = settings.get_font(settings.POWER_CIRCLE_FONT_SIZE, bold=True)

        # ── battle state ──
        self.current_round = 0     # 0-indexed (0, 1, 2)
        self.is_player_turn = False
        self.player_is_invader = False

        # Bought battle moves for each player (list of server dicts)
        self.player_moves = []     # 3 bought moves
        self.opponent_moves = []   # 3 opponent moves (hidden until played)

        # Played moves per round (None = not yet played)
        # Each entry is a server dict or None
        self.player_played = [None, None, None]
        self.opponent_played = [None, None, None]

        # ── figure icons for display ──
        self.player_figure_icon = None
        self.opponent_figure_icon = None
        self.player_figure = None
        self.opponent_figure = None
        # Civil-war second figures
        self.player_figure_icon_2 = None
        self.opponent_figure_icon_2 = None
        self.player_figure_2 = None
        self.opponent_figure_2 = None

        # Blocks-bonus: figures that auto-trigger to block opponent's support bonus
        # Each is a Figure object (or None) from the player's/opponent's field/battle
        self.player_blocks_bonus_figure = None   # player's blocker → blocks opponent's bonus
        self.opponent_blocks_bonus_figure = None  # opponent's blocker → blocks player's bonus
        self.player_blocks_bonus_figures = []
        self.opponent_blocks_bonus_figures = []

        # Distance-attack: figures that auto-trigger to reduce opponent figure power
        self.player_distance_attack_figure = None
        self.opponent_distance_attack_figure = None
        self._player_da_hit_battle = False   # True if player's DA already fired on battle fig
        self._opponent_da_hit_battle = False  # True if opponent's DA already fired on battle fig
        self._player_da_archers = []   # list of {fig, adv_suit, penalty, hit_battle}
        self._opponent_da_archers = []

        # Buffs-allies: figures that boost base power of same-suit village figures by +4
        self.player_buffs_allies_figures = []   # list of Figure objects
        self.opponent_buffs_allies_figures = []

        # Buffs-allies-defence: figures that boost all allied figures when defending
        self.player_buffs_allies_defence_figures = []
        self.opponent_buffs_allies_defence_figures = []

        # ── slot rendering cache ──
        self._slot_diamond = self._make_diamond(
            settings.ROUNDS_SLOT_SIZE, settings.ROUNDS_SLOT_SIZE,
            settings.BATTLE_SLOT_BG_COLOR, settings.BATTLE_SLOT_BORDER_COLOR,
        )
        self._slot_highlight_diamond = self._make_diamond(
            settings.ROUNDS_SLOT_SIZE, settings.ROUNDS_SLOT_SIZE,
            (250, 221, 0), (250, 221, 0),
        )
        self._slot_highlight_diamond.set_alpha(50)

        # Glow / icon / frame caches for battle move slots
        self._slot_glow_cache = {}
        self._slot_icon_cache = {}
        self._slot_frame_cache = {}
        self._init_slot_caches()

        # ── panel move icon cache (left panel) ──
        self._panel_icon_cache = {}
        self._panel_frame_cache = {}
        self._panel_glow_cache = {}
        self._panel_suit_icon_cache = {}    # MUST be initialised before _init_panel_icon_caches
        self._init_panel_icon_caches()

        # ── detail box ──
        self.battle_move_detail_box = None

        # ── figure detail box (opened by clicking a figure icon) ──
        self.figure_detail_box = None

        # ── cached player figures for Call-move figure selection ──
        self._player_figures = []           # all player Figure objects
        self._opponent_figures = []         # all opponent Figure objects
        self._resources_data = None         # resource totals for deficit check
        self._opponent_resources_data = None  # opponent resource totals for deficit check

        # ── panel icon hover state ──
        self._panel_hovered_index = None    # index of hovered panel icon (0-2 or None)
        self._panel_clicked_index = None

        # ── gamble state ──
        self._gambled_this_round = False     # True once gamble is used in current round
        self._has_played_move_this_turn = False  # True once a move is played this turn
        self._pending_gamble_move = None     # move dict awaiting gamble confirmation
        self._pending_combine_data = None    # (move_a, move_b) awaiting combine confirmation
        self._pending_dismantle_move = None   # move dict awaiting dismantle confirmation
        self._dialogue_callback = None       # callback for dialogue response

        # ── skip state (no moves left) ──
        self._player_skipped_rounds = []     # list of round indices the player skipped
        self._opponent_skipped_rounds = []   # list of round indices the opponent skipped
        self._auto_skip_pending = False      # guard to avoid double-skip

        # ── finish / battle resolution state ──
        self._finish_btn_rect = None             # pygame.Rect for the finish button
        self._finish_btn_hovered = False
        self._battle_result = None               # server response from finish_battle
        self._returnable_cards = []              # cards available for winner to pick
        self._awaiting_card_pick = False         # True while showing card pick dialogue
        self._picked_card_data = None            # card_data dict of user-picked loot card
        self._awaiting_draw_choice = False       # True while showing draw options

        # ── round-panel figure icons (clickable sub-icons next to slots) ──
        # Each entry: {'figure': Figure, 'rect': pygame.Rect, 'is_player': bool,
        #              'round': int, 'source': str}  (source = 'call' | 'skill_xxx')
        # Rebuilt every frame during _draw_rounds_panel.
        self._round_fig_icons = []
        self._round_fig_hovered_idx = None   # index into _round_fig_icons or None

        # ── loaded (game_id, player_id) tracking ──
        self._loaded_game_key = None

    def reset_state(self):
        """Reset all game-specific transient state.

        Called by GameScreen._reset_game_screen_state() when switching games.
        """
        self.current_round = 0
        self.is_player_turn = False
        self.player_is_invader = False
        self.player_moves = []
        self.opponent_moves = []
        self.player_played = [None, None, None]
        self.opponent_played = [None, None, None]
        self.player_figure_icon = None
        self.opponent_figure_icon = None
        self.player_figure = None
        self.opponent_figure = None
        self.player_figure_icon_2 = None
        self.opponent_figure_icon_2 = None
        self.player_figure_2 = None
        self.opponent_figure_2 = None
        self.player_blocks_bonus_figure = None
        self.opponent_blocks_bonus_figure = None
        self.player_blocks_bonus_figures = []
        self.opponent_blocks_bonus_figures = []
        self.player_distance_attack_figure = None
        self.opponent_distance_attack_figure = None
        self._player_da_hit_battle = False
        self._opponent_da_hit_battle = False
        self._player_da_archers = []
        self._opponent_da_archers = []
        self.player_buffs_allies_figures = []
        self.opponent_buffs_allies_figures = []
        self.player_buffs_allies_defence_figures = []
        self.opponent_buffs_allies_defence_figures = []
        self.battle_move_detail_box = None
        self.figure_detail_box = None
        self._player_figures = []
        self._opponent_figures = []
        self._resources_data = None
        self._opponent_resources_data = None
        self._panel_hovered_index = None
        self._panel_clicked_index = None
        self._gambled_this_round = False
        self._has_played_move_this_turn = False
        self._pending_gamble_move = None
        self._pending_combine_data = None
        self._pending_dismantle_move = None
        self._dialogue_callback = None
        self._player_skipped_rounds = []
        self._opponent_skipped_rounds = []
        self._auto_skip_pending = False
        self._finish_btn_rect = None
        self._finish_btn_hovered = False
        self._battle_result = None
        self._game_over_pending = False
        self._returnable_cards = []
        self._awaiting_card_pick = False
        self._picked_card_data = None
        self._awaiting_draw_choice = False
        self._card_picker_active = False
        self._card_picker_cards = []
        self._card_picker_selected = None
        self._card_picker_hovered = None
        self._card_picker_callback = None
        self._card_picker_title = ""
        self._card_picker_confirm_btn = None
        self._card_picker_box_rect = None
        self._round_fig_icons = []
        self._round_fig_hovered_idx = None
        self._loaded_game_key = None
        self.dialogue_box = None
        logger.info("[BattleScreen] State reset for game switch")

    # ──────────────────────── init helpers ──────────────────────

    def _make_diamond(self, w, h, fill_color, border_color):
        """Create a 45° rotated diamond surface."""
        base = pygame.Surface((w, h), pygame.SRCALPHA)
        base.fill(fill_color)
        pygame.draw.rect(base, border_color, (0, 0, w, h), 2)
        return pygame.transform.rotate(base, 45)

    def _init_slot_caches(self):
        """Pre-scale glow/icon/frame images for round slots."""
        gw = settings.ROUNDS_SLOT_GLOW_SIZE
        sw = settings.ROUNDS_SLOT_SIZE
        frame_s = int(sw * settings.ROUNDS_SLOT_FRAME_SCALE)
        icon_s = sw - 8

        green = pygame.image.load('img/game_button/glow/green.png').convert_alpha()
        blue = pygame.image.load('img/game_button/glow/blue.png').convert_alpha()

        self._slot_glow_cache['green'] = pygame.transform.smoothscale(green, (gw, gw))
        self._slot_glow_cache['blue'] = pygame.transform.smoothscale(blue, (gw, gw))

        for family in self.battle_move_manager.families:
            if family.icon_img:
                raw = family.icon_img.convert_alpha()
                self._slot_icon_cache[family.name] = pygame.transform.smoothscale(raw, (icon_s, icon_s))
            if family.frame_img:
                raw = family.frame_img.convert_alpha()
                self._slot_frame_cache[family.name] = pygame.transform.smoothscale(raw, (frame_s, frame_s))

        # Also cache icons for hidden families (e.g. Double Dagger) used in round slots
        for name, family in self.battle_move_manager.families_by_name.items():
            if name not in self._slot_icon_cache and family.icon_img:
                raw = family.icon_img.convert_alpha()
                self._slot_icon_cache[name] = pygame.transform.smoothscale(raw, (icon_s, icon_s))
            if name not in self._slot_frame_cache and family.frame_img:
                raw = family.frame_img.convert_alpha()
                self._slot_frame_cache[name] = pygame.transform.smoothscale(raw, (frame_s, frame_s))

        # Suit icons for round slots (smaller than panel icons)
        self._slot_suit_icon_cache = {}
        slot_suit_s = int(0.012 * settings.SCREEN_WIDTH)
        for suit_name in ('hearts', 'diamonds', 'spades', 'clubs'):
            path = settings.SUIT_ICON_IMG_PATH + suit_name + '.png'
            try:
                raw = pygame.image.load(path).convert_alpha()
                self._slot_suit_icon_cache[suit_name] = pygame.transform.smoothscale(raw, (slot_suit_s, slot_suit_s))
            except Exception:
                pass

    _HOVER_SCALE = 1.15  # how much to enlarge icons on hover

    def _init_panel_icon_caches(self):
        """Pre-scale icon/frame/glow for the left battle-moves panel (normal + hover)."""
        icon_s = settings.BATTLE_PANEL_ICON_SIZE
        frame_s = int(icon_s * settings.BATTLE_PANEL_ICON_FRAME_SCALE)
        glow_s = settings.BATTLE_PANEL_ICON_GLOW_SIZE

        icon_s_big = int(icon_s * self._HOVER_SCALE)
        frame_s_big = int(frame_s * self._HOVER_SCALE)
        glow_s_big = int(glow_s * self._HOVER_SCALE)

        green = pygame.image.load('img/game_button/glow/green.png').convert_alpha()
        blue = pygame.image.load('img/game_button/glow/blue.png').convert_alpha()
        yellow = pygame.image.load('img/game_button/glow/yellow.png').convert_alpha()

        self._panel_glow_cache['green'] = pygame.transform.smoothscale(green, (glow_s, glow_s))
        self._panel_glow_cache['blue'] = pygame.transform.smoothscale(blue, (glow_s, glow_s))
        self._panel_glow_cache['yellow'] = pygame.transform.smoothscale(yellow, (glow_s, glow_s))
        # big hover variants
        self._panel_glow_cache['green_big'] = pygame.transform.smoothscale(green, (glow_s_big, glow_s_big))
        self._panel_glow_cache['blue_big'] = pygame.transform.smoothscale(blue, (glow_s_big, glow_s_big))
        self._panel_glow_cache['yellow_big'] = pygame.transform.smoothscale(yellow, (glow_s_big, glow_s_big))

        for family in self.battle_move_manager.families:
            if family.icon_img:
                raw = family.icon_img.convert_alpha()
                self._panel_icon_cache[family.name] = pygame.transform.smoothscale(raw, (icon_s, icon_s))
                self._panel_icon_cache[family.name + '_big'] = pygame.transform.smoothscale(raw, (icon_s_big, icon_s_big))
            if family.frame_img:
                raw = family.frame_img.convert_alpha()
                self._panel_frame_cache[family.name] = pygame.transform.smoothscale(raw, (frame_s, frame_s))
                self._panel_frame_cache[family.name + '_big'] = pygame.transform.smoothscale(raw, (frame_s_big, frame_s_big))

        # Also cache icons for hidden families (e.g. Double Dagger) used during battle
        for name, family in self.battle_move_manager.families_by_name.items():
            if name not in self._panel_icon_cache and family.icon_img:
                raw = family.icon_img.convert_alpha()
                self._panel_icon_cache[name] = pygame.transform.smoothscale(raw, (icon_s, icon_s))
                self._panel_icon_cache[name + '_big'] = pygame.transform.smoothscale(raw, (icon_s_big, icon_s_big))
            if name not in self._panel_frame_cache and family.frame_img:
                raw = family.frame_img.convert_alpha()
                self._panel_frame_cache[name] = pygame.transform.smoothscale(raw, (frame_s, frame_s))
                self._panel_frame_cache[name + '_big'] = pygame.transform.smoothscale(raw, (frame_s_big, frame_s_big))

        # Suit icons for the panel label area (normal + big hover variants)
        suit_icon_s = int(0.016 * settings.SCREEN_WIDTH)
        suit_icon_s_big = int(suit_icon_s * self._HOVER_SCALE)
        for suit_name in ('hearts', 'diamonds', 'spades', 'clubs'):
            path = settings.SUIT_ICON_IMG_PATH + suit_name + '.png'
            try:
                raw = pygame.image.load(path).convert_alpha()
                self._panel_suit_icon_cache[suit_name] = pygame.transform.smoothscale(raw, (suit_icon_s, suit_icon_s))
                self._panel_suit_icon_cache[suit_name + '_big'] = pygame.transform.smoothscale(raw, (suit_icon_s_big, suit_icon_s_big))
            except Exception:
                pass  # fall back to text if image missing

    # ──────────────────── data loading ─────────────────────────

    def _load_battle_data(self):
        """Load battle moves and figures for both players."""
        if not self.game or not self.game.game_id:
            return

        # Load player's bought battle moves
        try:
            result = battle_shop_service.get_battle_moves(
                self.game.game_id, self.game.player_id,
            )
            self.player_moves = result.get('battle_moves', [])
        except Exception:
            self.player_moves = []

        # Load opponent's bought battle moves (will be hidden)
        try:
            if self.game.opponent_player:
                result = battle_shop_service.get_battle_moves(
                    self.game.game_id, self.game.opponent_player['id'],
                )
                self.opponent_moves = result.get('battle_moves', [])
        except Exception as e:
            logger.error(f"[BattleScreen] Failed to load opponent moves: {e}")
            self.opponent_moves = []

        # Determine invader status
        self.player_is_invader = self.game.invader

        # Load all player figures + resources for Call move eligibility checks
        # (must happen BEFORE _load_battle_figures so FieldFigureIcons get
        #  the correct per-side resources_data for deficit checks)
        try:
            families = self.figure_manager.families
            self._player_figures = self.game.get_figures(families, is_opponent=False)
            self._opponent_figures = self.game.get_figures(families, is_opponent=True)
            self._resources_data = self.game.calculate_resources(families, is_opponent=False)
            self._opponent_resources_data = self.game.calculate_resources(families, is_opponent=True)
        except Exception as e:
            logger.error(f"[BattleScreen] Failed to load player figures for call eligibility: {e}")
            self._player_figures = []
            self._opponent_figures = []
            self._resources_data = None
            self._opponent_resources_data = None

        # Load battling figures
        self._load_battle_figures()

        # Reset played state
        self.player_played = [None, None, None]
        self.opponent_played = [None, None, None]
        self.current_round = 0

        # Reset gamble state
        self._gambled_this_round = False
        self._has_played_move_this_turn = False
        self._pending_gamble_move = None

        # Reset skip state
        self._player_skipped_rounds = []
        self._opponent_skipped_rounds = []
        self._auto_skip_pending = False

        # Determine initial turn
        self.is_player_turn = self.player_is_invader

        # Set battle phase flags on the game object for scoreboard display
        self.game.in_battle_phase = True
        self.game.battle_turns_left = 3  # each player gets 3 battle turns

        self._loaded_game_key = (self.game.game_id, self.game.player_id)

    def _load_battle_figures(self):
        """Load the advancing and defending figures as FieldFigureIcons.

        Also loads Civil-War second figures (advancing_figure_id_2 /
        defending_figure_id_2) when present.
        """
        if not self.game:
            return

        families = self.figure_manager.families
        adv_id = self.game.advancing_figure_id
        def_id = self.game.defending_figure_id
        adv_id_2 = getattr(self.game, 'advancing_figure_id_2', None)
        def_id_2 = getattr(self.game, 'defending_figure_id_2', None)

        # Load player's figures and opponent's figures
        try:
            player_figures = self.game.get_figures(families, is_opponent=False)
            opponent_figures = self.game.get_figures(families, is_opponent=True)
        except Exception as e:
            logger.error(f"[BattleScreen] Failed to load figures: {e}")
            return

        # Determine which is player's and which is opponent's
        # The advancing player is the invader
        adv_player_id = self.game.advancing_player_id

        if adv_player_id == self.game.player_id:
            # Player is the attacker
            player_battle_figures = player_figures
            opponent_battle_figures = opponent_figures
            player_fig_id = adv_id
            opponent_fig_id = def_id
            player_fig_id_2 = adv_id_2
            opponent_fig_id_2 = def_id_2
        else:
            # Player is the defender
            player_battle_figures = player_figures
            opponent_battle_figures = opponent_figures
            player_fig_id = def_id
            opponent_fig_id = adv_id
            player_fig_id_2 = def_id_2
            opponent_fig_id_2 = adv_id_2

        # Find the specific figures
        self.player_figure = None
        self.player_figure_2 = None
        for fig in player_battle_figures:
            if fig.id == player_fig_id:
                self.player_figure = fig
            elif player_fig_id_2 and fig.id == player_fig_id_2:
                self.player_figure_2 = fig

        self.opponent_figure = None
        self.opponent_figure_2 = None
        for fig in opponent_battle_figures:
            if fig.id == opponent_fig_id:
                self.opponent_figure = fig
            elif opponent_fig_id_2 and fig.id == opponent_fig_id_2:
                self.opponent_figure_2 = fig

        # Create FieldFigureIcons for rendering
        _bfis = settings.BATTLE_FIGURE_ICON_SCALE
        if self.player_figure:
            self.player_figure_icon = FieldFigureIcon(
                window=self.window,
                game=self.game,
                figure=self.player_figure,
                is_visible=True,
                all_player_figures=player_battle_figures,
                resources_data=self._resources_data,
            )
            self.player_figure_icon.show_advance_overlay = False
            _rescale_battle_icon(self.player_figure_icon, _bfis)

        if self.player_figure_2:
            self.player_figure_icon_2 = FieldFigureIcon(
                window=self.window,
                game=self.game,
                figure=self.player_figure_2,
                is_visible=True,
                all_player_figures=player_battle_figures,
                resources_data=self._resources_data,
            )
            self.player_figure_icon_2.show_advance_overlay = False
            _rescale_battle_icon(self.player_figure_icon_2, _bfis)

        if self.opponent_figure:
            self.opponent_figure_icon = FieldFigureIcon(
                window=self.window,
                game=self.game,
                figure=self.opponent_figure,
                is_visible=True,  # Fully revealed during battle
                all_player_figures=opponent_battle_figures,
                resources_data=self._opponent_resources_data,
            )
            self.opponent_figure_icon.show_advance_overlay = False
            _rescale_battle_icon(self.opponent_figure_icon, _bfis)

        if self.opponent_figure_2:
            self.opponent_figure_icon_2 = FieldFigureIcon(
                window=self.window,
                game=self.game,
                figure=self.opponent_figure_2,
                is_visible=True,
                all_player_figures=opponent_battle_figures,
                resources_data=self._opponent_resources_data,
            )
            self.opponent_figure_icon_2.show_advance_overlay = False
            _rescale_battle_icon(self.opponent_figure_icon_2, _bfis)

        # ── Detect blocks_bonus skill triggers ──
        self._detect_blocks_bonus(player_battle_figures, opponent_battle_figures)

        # ── Detect distance_attack skill triggers ──
        self._detect_distance_attack(player_battle_figures, opponent_battle_figures)

        # ── Detect buffs_allies skill triggers ──
        self._detect_buffs_allies(player_battle_figures, opponent_battle_figures)

        # ── Detect buffs_allies_defence skill triggers ──
        self._detect_buffs_allies_defence(player_battle_figures, opponent_battle_figures)

    # ────────────────── blocks_bonus detection ──────────────────

    def _detect_blocks_bonus(self, player_figures, opponent_figures):
        """Check if any figure has blocks_bonus whose suit advantage matches
        an opponent battle figure.

        Temples keep blocking while they are active battle figures.  In Civil
        War, every matching battle target is marked as blocked.
        """
        from game.components.figures.family_configs.skill_config import get_advantage_suit

        self.player_blocks_bonus_figure = None
        self.opponent_blocks_bonus_figure = None
        self.player_blocks_bonus_figures = []
        self.opponent_blocks_bonus_figures = []

        # Collect opponent battle figure suits → icon mapping
        opp_targets = []
        if self.opponent_figure:
            opp_targets.append((self.opponent_figure.suit, self.opponent_figure_icon))
        if self.opponent_figure_2:
            opp_targets.append((self.opponent_figure_2.suit, self.opponent_figure_icon_2))

        # Player's blocker → blocks opponent's battle figure bonus
        for opp_suit, opp_icon in opp_targets:
            for fig in player_figures:
                if getattr(fig, 'blocks_bonus', False):
                    # Skip figures with resource deficit
                    if self._figure_has_deficit(fig):
                        continue
                    adv_suit = get_advantage_suit(fig.suit)
                    if adv_suit and adv_suit == opp_suit:
                        if self.player_blocks_bonus_figure is None:
                            self.player_blocks_bonus_figure = fig
                        if fig not in self.player_blocks_bonus_figures:
                            self.player_blocks_bonus_figures.append(fig)
                        if opp_icon:
                            opp_icon.battle_bonus_blocked = True
                        logger.debug(f"[BLOCKS_BONUS] Player's {fig.name} (suit={fig.suit}) blocks opponent's battle figure (suit={opp_suit}) bonus")
                        break

        # Collect player battle figure suits → icon mapping
        player_targets = []
        if self.player_figure:
            player_targets.append((self.player_figure.suit, self.player_figure_icon))
        if self.player_figure_2:
            player_targets.append((self.player_figure_2.suit, self.player_figure_icon_2))

        # Opponent's blocker → blocks player's battle figure bonus
        for player_suit, player_icon in player_targets:
            for fig in opponent_figures:
                if getattr(fig, 'blocks_bonus', False):
                    if self._figure_has_deficit(fig, self._opponent_resources_data):
                        continue
                    adv_suit = get_advantage_suit(fig.suit)
                    if adv_suit and adv_suit == player_suit:
                        if self.opponent_blocks_bonus_figure is None:
                            self.opponent_blocks_bonus_figure = fig
                        if fig not in self.opponent_blocks_bonus_figures:
                            self.opponent_blocks_bonus_figures.append(fig)
                        if player_icon:
                            player_icon.battle_bonus_blocked = True
                        logger.debug(f"[BLOCKS_BONUS] Opponent's {fig.name} (suit={fig.suit}) blocks player's battle figure (suit={player_suit}) bonus")
                        break

    # ────────────────── distance_attack detection ───────────────

    def _detect_distance_attack(self, player_figures, opponent_figures):
        """Check if any field figures have distance_attack whose suit advantage
        matches the opponent's battle figure(s).  If so, store them and apply
        power penalties on the targeted battle figure icons.

        Each eligible archer fires once per battle: if it hits a battle figure
        here, it won't also hit called-in figures.  Multiple archers can fire
        independently.
        """
        from game.components.figures.family_configs.skill_config import get_advantage_suit

        # Lists of dicts: {fig, adv_suit, penalty, hit_battle}
        self._player_da_archers = []
        self._opponent_da_archers = []
        # Legacy single-figure attrs (used by display/support code)
        self.player_distance_attack_figure = None
        self.opponent_distance_attack_figure = None
        self._player_da_hit_battle = False
        self._opponent_da_hit_battle = False

        # Battle figure IDs to exclude (they are already in battle)
        battle_ids = set()
        for fig in (self.player_figure, self.player_figure_2,
                    self.opponent_figure, self.opponent_figure_2):
            if fig:
                battle_ids.add(fig.id)

        logger.debug(f"[DA_DETECT] battle_ids={battle_ids}, "
              f"player_figs={len(player_figures)}, opp_figs={len(opponent_figures)}, "
              f"opp_figure={getattr(self.opponent_figure, 'name', None)}(suit={getattr(self.opponent_figure, 'suit', None)}), "
              f"player_figure={getattr(self.player_figure, 'name', None)}(suit={getattr(self.player_figure, 'suit', None)})")

        # --- Player's distance attackers → penalise opponent's battle figures ---
        opp_targets = []
        if self.opponent_figure:
            opp_targets.append((self.opponent_figure.suit, self.opponent_figure_icon))
        if self.opponent_figure_2:
            opp_targets.append((self.opponent_figure_2.suit, self.opponent_figure_icon_2))

        for fig in player_figures:
            if fig.id in battle_ids:
                continue
            da_flag = getattr(fig, 'distance_attack', False)
            if not da_flag:
                continue
            has_deficit = self._figure_has_deficit(fig)
            if has_deficit:
                continue
            adv_suit = get_advantage_suit(fig.suit)
            if not adv_suit:
                continue
            penalty_value = fig.number_card.value if fig.number_card else 0
            hit_battle = False
            for opp_suit, opp_icon in opp_targets:
                if adv_suit == opp_suit:
                    hit_battle = True
                    if opp_icon:
                        opp_icon.distance_attack_penalty = getattr(opp_icon, 'distance_attack_penalty', 0) + penalty_value
                    break
            self._player_da_archers.append({
                'fig': fig, 'adv_suit': adv_suit, 'penalty': penalty_value,
                'hit_battle': hit_battle
            })

        # Set legacy attrs from first archer
        if self._player_da_archers:
            self.player_distance_attack_figure = self._player_da_archers[0]['fig']
            self._player_da_hit_battle = any(a['hit_battle'] for a in self._player_da_archers)

        # --- Opponent's distance attackers → penalise player's battle figures ---
        player_targets = []
        if self.player_figure:
            player_targets.append((self.player_figure.suit, self.player_figure_icon))
        if self.player_figure_2:
            player_targets.append((self.player_figure_2.suit, self.player_figure_icon_2))

        for fig in opponent_figures:
            if fig.id in battle_ids:
                continue
            da_flag = getattr(fig, 'distance_attack', False)
            if not da_flag:
                continue
            if self._figure_has_deficit(fig, self._opponent_resources_data):
                continue
            adv_suit = get_advantage_suit(fig.suit)
            if not adv_suit:
                continue
            penalty_value = fig.number_card.value if fig.number_card else 0
            hit_battle = False
            for player_suit, player_icon in player_targets:
                if adv_suit == player_suit:
                    hit_battle = True
                    if player_icon:
                        player_icon.distance_attack_penalty = getattr(player_icon, 'distance_attack_penalty', 0) + penalty_value
                    break
            self._opponent_da_archers.append({
                'fig': fig, 'adv_suit': adv_suit, 'penalty': penalty_value,
                'hit_battle': hit_battle
            })

        # Set legacy attrs from first archer
        if self._opponent_da_archers:
            self.opponent_distance_attack_figure = self._opponent_da_archers[0]['fig']
            self._opponent_da_hit_battle = any(a['hit_battle'] for a in self._opponent_da_archers)

        logger.debug(f"[DA_DETECT] Result: player_da={[a['fig'].name for a in self._player_da_archers]}, "
              f"opponent_da={[a['fig'].name for a in self._opponent_da_archers]}, "
              f"player_hits={[a['hit_battle'] for a in self._player_da_archers]}, "
              f"opponent_hits={[a['hit_battle'] for a in self._opponent_da_archers]}")

    # ────────────────── buffs_allies detection ──────────────────

    def _detect_buffs_allies(self, player_figures, opponent_figures):
        """Find field figures with buffs_allies and apply +4 base power buff
        to same-suit village battle figures / icons.

        The buff is counted as base power (not a support bonus), so it is
        NOT affected by blocks_bonus.
        """
        self.player_buffs_allies_figures = []
        self.opponent_buffs_allies_figures = []

        # Battle figure IDs (they sit on the field but are in battle)
        battle_ids = set()
        for fig in (self.player_figure, self.player_figure_2,
                    self.opponent_figure, self.opponent_figure_2):
            if fig:
                battle_ids.add(fig.id)

        player_icon_map = {
            fig.id: icon
            for fig, icon in (
                (self.player_figure, self.player_figure_icon),
                (self.player_figure_2, self.player_figure_icon_2),
            )
            if fig and icon
        }
        self.player_buffs_allies_figures = apply_buffs_allies_to_icon_map(
            player_figures,
            player_icon_map,
            has_deficit=self._figure_has_deficit,
            exclude_ids=battle_ids,
        )

        opponent_icon_map = {
            fig.id: icon
            for fig, icon in (
                (self.opponent_figure, self.opponent_figure_icon),
                (self.opponent_figure_2, self.opponent_figure_icon_2),
            )
            if fig and icon
        }
        self.opponent_buffs_allies_figures = apply_buffs_allies_to_icon_map(
            opponent_figures,
            opponent_icon_map,
            has_deficit=lambda fig: self._figure_has_deficit(
                fig, self._opponent_resources_data),
            exclude_ids=battle_ids,
        )

    # ────────────────── buffs_allies_defence detection ──────────

    def _detect_buffs_allies_defence(self, player_figures, opponent_figures):
        """Find field figures with buffs_allies_defence.

        Only active when the owner is DEFENDING (not invader).
        Bonus = number_card.value, applied to ALL battle figure icons as
        a support bonus (affected by blocks_bonus).
        """
        self.player_buffs_allies_defence_figures = []
        self.opponent_buffs_allies_defence_figures = []

        # Battle figure IDs (they sit on the field but are in battle)
        battle_ids = set()
        for fig in (self.player_figure, self.player_figure_2,
                    self.opponent_figure, self.opponent_figure_2):
            if fig:
                battle_ids.add(fig.id)

        # --- Player's defence buffers — only active when player is DEFENDING ---
        if not self.player_is_invader:
            for fig in player_figures:
                if fig.id in battle_ids:
                    continue
                if getattr(fig, 'buffs_allies_defence', False):
                    if self._figure_has_deficit(fig):
                        continue
                    self.player_buffs_allies_defence_figures.append(fig)

            # Apply defence bonus to ALL player battle figure icons
            if self.player_buffs_allies_defence_figures:
                total_bonus = sum(
                    bf.number_card.value for bf in self.player_buffs_allies_defence_figures
                    if bf.number_card
                )
                for icon in (self.player_figure_icon, self.player_figure_icon_2):
                    if icon:
                        icon.buffs_allies_defence_bonus = total_bonus
                        logger.debug(f"[BUFFS_ALLIES_DEFENCE] Player defence buff +{total_bonus}")

        # --- Opponent's defence buffers — only active when opponent is DEFENDING ---
        if self.player_is_invader:
            for fig in opponent_figures:
                if fig.id in battle_ids:
                    continue
                if getattr(fig, 'buffs_allies_defence', False):
                    if self._figure_has_deficit(fig, self._opponent_resources_data):
                        continue
                    self.opponent_buffs_allies_defence_figures.append(fig)

            if self.opponent_buffs_allies_defence_figures:
                total_bonus = sum(
                    bf.number_card.value for bf in self.opponent_buffs_allies_defence_figures
                    if bf.number_card
                )
                for icon in (self.opponent_figure_icon, self.opponent_figure_icon_2):
                    if icon:
                        icon.buffs_allies_defence_bonus = total_bonus
                        logger.debug(f"[BUFFS_ALLIES_DEFENCE] Opponent defence buff +{total_bonus}")

    # ────────────────── eligible figures for Call moves ──────────

    _RED_SUITS = {'Hearts', 'Diamonds'}
    _BLACK_SUITS = {'Clubs', 'Spades'}

    CALL_FIELD_MAP = {
        'Call Villager': 'village',
        'Call Military': 'military',
        'Call King': 'castle',
    }

    def _get_eligible_figures(self, family_name, bm_suit=''):
        """Return figures eligible for a Call move (filtered by field type, colour, deficit, etc.)"""
        field_type = self.CALL_FIELD_MAP.get(family_name)
        if not field_type:
            return []

        bm_is_red = bm_suit in self._RED_SUITS

        # IDs of figures already in battle (cannot be called)
        fighting_ids = set()
        for attr in ('advancing_figure_id', 'advancing_figure_id_2',
                     'defending_figure_id', 'defending_figure_id_2'):
            fid = getattr(self.game, attr, None)
            if fid is not None:
                fighting_ids.add(fid)

        # IDs of figures already called in previous rounds (each figure can only be called once)
        already_called_ids = set()
        for played in self.player_played:
            if played is None:
                continue
            call_fig = played.get('_call_figure')
            if call_fig:
                already_called_ids.add(getattr(call_fig, 'id', None))
            elif played.get('call_figure_id'):
                already_called_ids.add(played['call_figure_id'])
        already_called_ids.discard(None)

        eligible = []
        for fig in self._player_figures:
            # Must match the call's field type
            if not hasattr(fig.family, 'field') or fig.family.field != field_type:
                continue
            # Exclude cannot_be_targeted
            if getattr(fig, 'cannot_be_targeted', False):
                continue
            # Exclude figures already fighting
            if fig.id in fighting_ids:
                continue
            # Exclude figures already called in a previous round
            if fig.id in already_called_ids:
                continue
            # Exclude figures with resource deficit
            if self._figure_has_deficit(fig):
                continue
            # Colour check: red BM → red figure, black BM → black figure
            if bm_is_red and fig.suit not in self._RED_SUITS:
                continue
            if not bm_is_red and fig.suit not in self._BLACK_SUITS:
                continue
            eligible.append(fig)
        return eligible

    def _figure_has_deficit(self, fig, resources_data=None):
        """Check whether a figure's resource requirements exceed available supply.

        *resources_data* defaults to the current player's data.  Pass
        ``self._opponent_resources_data`` when checking an opponent figure.
        """
        if not getattr(fig, 'requires', None):
            return False
        rd = resources_data if resources_data is not None else self._resources_data
        if not rd:
            return False
        produces = rd.get('produces', {})
        requires = rd.get('requires', {})
        for res_name in fig.requires:
            total_produced = produces.get(res_name, 0)
            total_required = requires.get(res_name, 0)
            if total_required > total_produced:
                return True
        return False

    def _get_panel_display_power(self, move):
        """Return the power value to display below a battle-move icon.

        For Call moves the value is the maximum possible combined power
        (figure base + move bonus if suit matches) across all eligible
        figures.  For Double Daggers, returns ``'X+Y'`` string.
        For other moves the raw move value is shown.
        """
        family_name = move.get('family_name', '')
        bm_suit = move.get('suit', '')
        bm_value = move.get('value', 0)

        # Double Dagger: show individual values as "X+Y"
        if family_name == 'Double Dagger':
            va = move.get('value_a', 0)
            vb = move.get('value_b', 0)
            if va or vb:
                return f"{va}+{vb}"
            return bm_value

        # Block always has power 0
        if family_name == 'Block':
            return 0

        if family_name not in self.CALL_FIELD_MAP:
            return bm_value

        eligible = self._get_eligible_figures(family_name, bm_suit)
        if not eligible:
            return bm_value  # no eligible figures — show base move value

        max_power = 0
        for fig in eligible:
            base = fig.get_value()
            buffs = self._get_buffs_allies_bonus(fig, is_player=True)
            # Wall defence does NOT apply to call figures
            bonus = bm_value if fig.suit == bm_suit else 0
            total = base + buffs + bonus
            if total > max_power:
                max_power = total
        return max_power

    def _get_best_figure_index(self, eligible, bm_suit, bm_value):
        """Return the index of the strongest eligible figure for a Call move.

        Uses the same power formula as ``_get_panel_display_power`` so the
        carousel default matches the value shown on the panel icon.
        """
        if not eligible:
            return 0
        best_idx = 0
        best_power = -1
        for i, fig in enumerate(eligible):
            base = fig.get_value()
            buffs = self._get_buffs_allies_bonus(fig, is_player=True)
            # Wall defence does NOT apply to call figures
            bonus = bm_value if fig.suit == bm_suit else 0
            total = base + buffs + bonus
            if total > best_power:
                best_power = total
                best_idx = i
        return best_idx

    def _figure_power_bonuses(self, figures, is_player):
        return {
            fig.id: self._get_buffs_allies_bonus(fig, is_player)
            for fig in figures or []
        }

    # ────────────────── power calculations ─────────────────────

    def _get_figure_total_power(self, figure, figure_icon):
        """Get total power of a figure including base value, bonus, and enchantments.
        If the figure's bonus is blocked (blocks_bonus skill), the bonus is excluded.
        Distance-attack penalty (if any) is subtracted from the total.
        Buffs-allies bonus is added as base power (unaffected by blocks_bonus).
        Buffs-allies-defence bonus is a support bonus (affected by blocks_bonus).
        """
        if not figure:
            return 0
        base = figure.get_value()
        # buffs_allies bonus (treated as base power, not affected by blocks_bonus)
        buffs_bonus = getattr(figure_icon, 'buffs_allies_bonus', 0) if figure_icon else 0
        bonus = figure_icon.battle_bonus_received if figure_icon else 0
        # blocks_bonus negates the support bonus (NOT wall defence)
        if figure_icon and getattr(figure_icon, 'battle_bonus_blocked', False):
            bonus = 0
        # buffs_allies_defence (wall) bonus — NOT affected by blocks_bonus
        defence_bonus = getattr(figure_icon, 'buffs_allies_defence_bonus', 0) if figure_icon else 0
        enchant = figure.get_total_enchantment_modifier()
        # distance_attack penalty
        dist_penalty = getattr(figure_icon, 'distance_attack_penalty', 0) if figure_icon else 0
        return base + buffs_bonus + bonus + defence_bonus + enchant - dist_penalty

    def _get_round_diff(self, round_idx):
        """Get the power difference for a specific round (player - opponent).
        Returns None if the round hasn't been played yet.
        Block nullifies the round — always returns 0.
        """
        p = self.player_played[round_idx]
        o = self.opponent_played[round_idx]
        if p is None or o is None:
            return None
        # Block zeroes the entire round
        if p.get('family_name') == 'Block' or o.get('family_name') == 'Block':
            return 0
        p_val = self._get_move_effective_power(p, is_player=True, round_idx=round_idx)
        o_val = self._get_move_effective_power(o, is_player=False, round_idx=round_idx)
        return p_val - o_val

    def _get_da_call_penalty(self, for_player_da, round_idx):
        """Return the total DA penalty applied to a called-in figure in a
        specific round, from archers that didn't hit a battle figure.

        ``for_player_da=True``  → player's archers target opponent's call figs.
        ``for_player_da=False`` → opponent's archers target player's call figs.

        Each non-consumed archer fires on the first matching call figure
        it finds (scanning rounds 0-2).  Returns the sum of penalties from
        all archers whose first matching round equals *round_idx*.
        """
        if for_player_da:
            archers = self._player_da_archers
            played = self.opponent_played
        else:
            archers = self._opponent_da_archers
            played = self.player_played

        total_penalty = 0
        for archer in archers:
            if archer['hit_battle']:
                continue  # already consumed on battle fig
            adv_suit = archer['adv_suit']
            # Find the first round where this archer hits a call figure
            for r in range(3):
                move = played[r]
                if not move:
                    continue
                call_fig = move.get('_call_figure')
                if call_fig and (call_fig.suit or '').lower() == adv_suit.lower():
                    if r == round_idx:
                        total_penalty += archer['penalty']
                    break  # this archer's shot is consumed
        return total_penalty

    def _get_move_effective_power(self, move, is_player=None, round_idx=None):
        """Get effective power of a played move including Call-figure bonus.

        - Block → 0
        - Call + suit match → figure_base_power + buffs_allies + defence_buff + BM value
        - Call + suit mismatch → figure_base_power + buffs_allies + defence_buff only
        - No call figure → BM value

        Distance-attack penalty is applied only once per battle: if the DA
        already fired on a battle figure it won't fire again on a call
        figure; otherwise it fires on the first matching call figure only.
        Buffs-allies bonus is added as base power for village call figures.
        Buffs-allies-defence bonus does NOT apply to call figures.
        """
        if not move:
            return 0
        if move.get('_skipped'):
            return 0
        if move.get('family_name') == 'Block':
            return 0
        bm_value = move.get('value', 0)
        if not isinstance(bm_value, (int, float)):
            bm_value = 0
        call_fig = move.get('_call_figure')
        if call_fig:
            fig_power = call_fig.get_value()
            fig_suit = (call_fig.suit or '').lower()
            bm_suit = (move.get('suit', '') or '').lower()

            # Buffs-allies bonus: +4 per matching buffer for village call figs
            buffs_bonus = self._get_buffs_allies_bonus(call_fig, is_player)

            # Wall defence does NOT apply to call figures

            # Distance-attack penalty on the called-in figure (multi-archer)
            distance_penalty = 0
            if is_player is not None and round_idx is not None:
                distance_penalty = self._get_da_call_penalty(
                    for_player_da=not is_player, round_idx=round_idx)

            if fig_suit == bm_suit:
                return fig_power + buffs_bonus + bm_value - distance_penalty
            return fig_power + buffs_bonus - distance_penalty
        return bm_value

    def _get_buffs_allies_bonus(self, figure, is_player):
        """Return the total buffs_allies bonus for a figure.
        Only village figures can be buffed. Each matching buffer adds +4.
        """
        if not figure or is_player is None:
            return 0
        if not (hasattr(figure.family, 'field') and figure.family.field == 'village'):
            return 0
        buffers = self.player_buffs_allies_figures if is_player else self.opponent_buffs_allies_figures
        bonus = 0
        for buff_fig in buffers:
            if buff_fig.suit == figure.suit:
                bonus += 4
        return bonus

    def _get_buffs_allies_defence_bonus(self, is_player):
        """Return the total buffs_allies_defence bonus.
        Applies to ALL figures when the owner is defending.
        """
        if is_player is None:
            return 0
        buffers = (self.player_buffs_allies_defence_figures if is_player
                   else self.opponent_buffs_allies_defence_figures)
        return sum(bf.number_card.value for bf in buffers if bf.number_card)

    def _get_figure_diff(self):
        """Get figure power difference (player - opponent).

        In Civil War both sides may have two figures; the total power
        for each side is the sum of both figures' individual power.
        """
        p_power = self._get_figure_total_power(self.player_figure, self.player_figure_icon)
        p_power += self._get_figure_total_power(self.player_figure_2, self.player_figure_icon_2)
        o_power = self._get_figure_total_power(self.opponent_figure, self.opponent_figure_icon)
        o_power += self._get_figure_total_power(self.opponent_figure_2, self.opponent_figure_icon_2)
        return p_power - o_power

    def _get_total_diff(self, verbose=False):
        """Get total difference: figure diff + all completed round diffs.

        :param verbose: if True, print per-round debug info (only for finish_battle).
        """
        fig_diff = self._get_figure_diff()
        total = fig_diff
        for i in range(3):
            rd = self._get_round_diff(i)
            if rd is not None:
                total += rd
                if verbose:
                    p = self.player_played[i]
                    o = self.opponent_played[i]
                    p_val = self._get_move_effective_power(p, is_player=True, round_idx=i) if p else 0
                    o_val = self._get_move_effective_power(o, is_player=False, round_idx=i) if o else 0
                    p_info = (f"{p.get('family_name')}(v={p.get('value')},s={p.get('suit')},"
                              f"call={p.get('call_figure_id')},"
                              f"cf={'yes' if p.get('_call_figure') else 'no'})" if p else "None")
                    o_info = (f"{o.get('family_name')}(v={o.get('value')},s={o.get('suit')},"
                              f"call={o.get('call_figure_id')},"
                              f"cf={'yes' if o.get('_call_figure') else 'no'})" if o else "None")
                    # Include call figure breakdown for diagnosing discrepancies
                    p_cf_info = ""
                    if p and p.get('_call_figure'):
                        cf = p['_call_figure']
                        p_cf_info = (f" cf_name={cf.name} cf_suit={cf.suit} "
                                     f"cf_base={cf.get_value()} "
                                     f"cf_buffs={self._get_buffs_allies_bonus(cf, True)} "
                                     f"cf_da={self._get_da_call_penalty(False, i)}")
                    o_cf_info = ""
                    if o and o.get('_call_figure'):
                        cf = o['_call_figure']
                        o_cf_info = (f" cf_name={cf.name} cf_suit={cf.suit} "
                                     f"cf_base={cf.get_value()} "
                                     f"cf_buffs={self._get_buffs_allies_bonus(cf, False)} "
                                     f"cf_da={self._get_da_call_penalty(True, i)}")
                    logger.debug(f"[CLIENT_ROUND_{i}] p={p_info} p_eff={p_val}{p_cf_info} "
                          f"o={o_info} o_eff={o_val}{o_cf_info} rd={rd}")
        if verbose:
            p_power = self._get_figure_total_power(self.player_figure, self.player_figure_icon)
            p_power_2 = self._get_figure_total_power(self.player_figure_2, self.player_figure_icon_2)
            o_power = self._get_figure_total_power(self.opponent_figure, self.opponent_figure_icon)
            o_power_2 = self._get_figure_total_power(self.opponent_figure_2, self.opponent_figure_icon_2)
            # Component breakdown for main battle figures
            def _fig_breakdown(fig, icon):
                if not fig:
                    return "None"
                base = fig.get_value()
                buffs = getattr(icon, 'buffs_allies_bonus', 0) if icon else 0
                bonus = icon.battle_bonus_received if icon else 0
                blocked = getattr(icon, 'battle_bonus_blocked', False) if icon else False
                if blocked:
                    bonus = 0
                defence = getattr(icon, 'buffs_allies_defence_bonus', 0) if icon else 0
                enchant = fig.get_total_enchantment_modifier()
                da = getattr(icon, 'distance_attack_penalty', 0) if icon else 0
                return (f"{fig.name}(suit={fig.suit},base={base},buffs={buffs},"
                        f"support={bonus},blocked={blocked},wall={defence},"
                        f"enchant={enchant},da={da})")
            logger.debug(f"[CLIENT_FIG] player={_fig_breakdown(self.player_figure, self.player_figure_icon)} "
                  f"player2={_fig_breakdown(self.player_figure_2, self.player_figure_icon_2)} "
                  f"opponent={_fig_breakdown(self.opponent_figure, self.opponent_figure_icon)} "
                  f"opponent2={_fig_breakdown(self.opponent_figure_2, self.opponent_figure_icon_2)}")
            logger.debug(f"[CLIENT_TOTAL_DIFF] fig_diff={fig_diff} "
                  f"(player={p_power}+{p_power_2} opponent={o_power}+{o_power_2}) total={total} "
                  f"is_invader={self.player_is_invader}")
        return total

    def _is_move_used(self, move_idx):
        """Check if a player move has already been played in a round."""
        if move_idx >= len(self.player_moves):
            return False
        move = self.player_moves[move_idx]
        # Check server-side played_round first (set by polling)
        if move.get('played_round') is not None:
            return True
        # Fallback: check local player_played array
        for played in self.player_played:
            if played and played.get('id') == move.get('id'):
                return True
        return False

    # ─────────────────── battle-state poller ───────────────────

    @staticmethod
    def _battle_state_async_transform(resp):
        """Convert a web async-XHR response into a battle-state dict."""
        try:
            if resp is None:
                return {'success': False}
            if getattr(resp, 'status_code', 200) != 200:
                return {'success': False}
            return resp.json()
        except Exception as exc:  # noqa: BLE001
            return {'success': False, 'message': str(exc) or 'Battle state error'}

    def _build_battle_state_poller(self, game_id, player_id):
        """Build the per-second battle-state poller.

        On desktop the threaded path calls the lambda (sync requests). On
        web/emscripten the poller takes the ``async_get_url`` branch so the
        XHR no longer blocks the pygbag main thread (which was producing
        a visible per-second freeze while on the 'battle' subscreen).
        """
        return BackgroundPoller(
            lambda gid, pid: game_service.get_battle_state(gid, pid),
            args=(game_id, player_id),
            async_get_url=f'{settings.SERVER_URL}/games/get_battle_state',
            async_get_params={'game_id': game_id, 'player_id': player_id},
            async_transform=self._battle_state_async_transform,
        )

    # ────────────────────── update ─────────────────────────────

    def update(self, game):
        """Update the game state."""
        super().update(game)
        self.game = game

        # Load data if needed
        current_key = (getattr(game, 'game_id', None),
                       getattr(game, 'player_id', None))
        needs_reload = current_key[0] and current_key != self._loaded_game_key
        # Safety: reload if we're in battle phase but have no moves loaded
        if not needs_reload and current_key[0] and not self.player_moves and getattr(game, 'in_battle_phase', False):
            needs_reload = True
        if needs_reload:
            self._load_battle_data()
            # (Re)create the background poller for this game
            self._battle_poller = self._build_battle_state_poller(
                current_key[0], game.player_id)

        # Safety: retry loading figures if we're in battle but figures are
        # still missing (can happen when cached_figures_data wasn't ready yet
        # on the initial load after a reconnect, or in conquer mode where the
        # battle screen is first loaded during the prelude before figures are
        # assigned — in_battle_phase gets cleared as stale while the battle
        # hasn't started yet, so also trigger on server-confirmed battle).
        _server_battle_active = (
            getattr(game, 'battle_confirmed', False) and
            getattr(game, 'battle_turn_player_id', None) is not None
        )
        if (self.player_figure is None
                and current_key[0]
                and (getattr(game, 'in_battle_phase', False) or _server_battle_active)
                and (game.advancing_figure_id or game.defending_figure_id)):
            self._load_battle_figures()
            # Sync in_battle_phase when the server confirms the battle is active
            # but the flag was cleared (e.g. cleared as stale during prelude).
            if _server_battle_active and not getattr(game, 'in_battle_phase', False):
                game.in_battle_phase = True
            # Also refresh the supporting figure lists / resources
            try:
                families = self.figure_manager.families
                self._player_figures = game.get_figures(families, is_opponent=False)
                self._opponent_figures = game.get_figures(families, is_opponent=True)
                self._resources_data = game.calculate_resources(families, is_opponent=False)
                self._opponent_resources_data = game.calculate_resources(families, is_opponent=True)
            except Exception:
                pass

        # Non-blocking battle state poll (every ~1 s)
        now = pygame.time.get_ticks()
        if not hasattr(self, '_battle_poll_timer'):
            self._battle_poll_timer = 0
            self._battle_poller = None
        if now - self._battle_poll_timer >= 1000:
            self._battle_poll_timer = now
            if self._battle_poller is None and game and game.game_id:
                self._battle_poller = self._build_battle_state_poller(
                    game.game_id, game.player_id)
            if self._battle_poller and not self._battle_poller.busy:
                self._battle_poller.poll(
                    args=(game.game_id, game.player_id))
        # Apply result when ready (non-blocking)
        if self._battle_poller and self._battle_poller.has_result():
            self._apply_battle_state(self._battle_poller.result)

        # Auto-finish: if all moves are played and the opponent already
        # resolved the battle (battle_confirmed went False or fold_winner_id
        # appeared), auto-trigger _finish_battle for the lagging client.
        if (self._all_moves_played()
                and not self._battle_result
                and not self.dialogue_box
                and game
                and (not getattr(game, 'battle_confirmed', True)
                     or getattr(game, 'fold_winner_id', None))):
            self._finish_battle()

        # Safety net: server already cleaned up (advancing_figure_id gone,
        # battle not confirmed) but we never resolved locally.  This can
        # happen if the AI's finish_battle + pick_card completed between
        # polls and the auto-finish above failed to show a dialogue.
        if (not self._battle_result
                and not self.dialogue_box
                and game
                and not getattr(game, 'advancing_figure_id', None)
                and not getattr(game, 'battle_confirmed', True)
                and not getattr(game, 'fold_winner_id', None)
                and self._loaded_game_key):
            if self._try_resolve_server_finished_battle():
                return
            logger.warning("[BattleScreen] Safety net: battle resolved on server but "
                  "no local result — exiting battle screen")
            self._reset_after_battle()

        # Auto-skip: if it's our turn but we have no unused moves left
        self._check_auto_skip()

        # Keep the scoreboard battle-turns count in sync
        self._sync_battle_turns()

    def _poll_battle_state(self):
        """Fetch the current battle state from the server and reconcile (blocking legacy)."""
        if not self.game or not self.game.game_id:
            return
        result = game_service.get_battle_state(
            self.game.game_id, self.game.player_id)
        self._apply_battle_state(result)

    def _apply_battle_state(self, result):
        """Apply fetched battle state data (main thread only)."""
        if not result or not result.get('success'):
            return

        # Update round and turn from server
        server_round = result.get('battle_round', 0)
        server_turn_pid = result.get('battle_turn_player_id')

        self.current_round = server_round
        self.is_player_turn = (server_turn_pid == self.game.player_id)

        # Reconcile player played moves from server data
        player_moves_data = result.get('player_moves', [])
        # Build a lookup by move ID for quick access
        server_moves_by_id = {pm['id']: pm for pm in player_moves_data if 'id' in pm}

        # Update self.player_moves with played_round from server
        for i, m in enumerate(self.player_moves):
            mid = m.get('id')
            if mid and mid in server_moves_by_id:
                self.player_moves[i]['played_round'] = server_moves_by_id[mid].get('played_round')

        for pm in player_moves_data:
            pr = pm.get('played_round')
            if pr is not None and 0 <= pr <= 2:
                if self.player_played[pr] is None:
                    played = dict(pm)
                    if played.get('family_name') == 'Block':
                        played['value'] = 0
                    # Restore _call_figure reference if available
                    call_fid = pm.get('call_figure_id')
                    if call_fid:
                        played['_call_figure'] = self._find_figure_by_id(call_fid)
                    self.player_played[pr] = played

        # Reconcile opponent played moves from server data
        opponent_moves_data = result.get('opponent_moves', [])
        for om in opponent_moves_data:
            pr = om.get('played_round')
            if pr is not None and 0 <= pr <= 2:
                if self.opponent_played[pr] is None or self.opponent_played[pr].get('id') != om.get('id'):
                    played = dict(om)
                    if played.get('family_name') == 'Block':
                        played['value'] = 0
                    # Restore _call_figure reference for opponent
                    call_fid = om.get('call_figure_id')
                    if call_fid:
                        played['_call_figure'] = self._find_figure_by_id(call_fid, opponent=True)
                    self.opponent_played[pr] = played

        # Reconcile skipped rounds from server
        skipped = result.get('battle_skipped_rounds', {})
        pid = str(self.game.player_id)
        self._player_skipped_rounds = skipped.get(pid, [])
        # Find opponent player_id
        opp_id = None
        for p in (self.game.players if hasattr(self.game, 'players') else []):
            p_id = p.get('id') if isinstance(p, dict) else getattr(p, 'id', None)
            if p_id and p_id != self.game.player_id:
                opp_id = str(p_id)
                break
        if opp_id:
            self._opponent_skipped_rounds = skipped.get(opp_id, [])

        # Fill in skipped rounds as empty "skip" entries so rendering works
        for r in self._player_skipped_rounds:
            if 0 <= r <= 2 and self.player_played[r] is None:
                self.player_played[r] = {'family_name': 'Skip', 'value': 0, 'suit': '', '_skipped': True}
        for r in self._opponent_skipped_rounds:
            if 0 <= r <= 2 and self.opponent_played[r] is None:
                self.opponent_played[r] = {'family_name': 'Skip', 'value': 0, 'suit': '', '_skipped': True}

    def _derive_conquer_result_from_server_state(self):
        """Build a conquer-result payload from current synced game state."""
        if not self.game or getattr(self.game, 'mode', 'duel') != 'conquer':
            return None

        last = getattr(self.game, '_last_polled_battle_result', None) or {}
        explicit = last.get('conquer_result')
        if explicit in ('draw', 'attacker_won', 'defender_won'):
            payload = dict(last)
            payload.setdefault('success', True)
            payload.setdefault('attacker_won', explicit == 'attacker_won')
            payload.setdefault('land_tier', getattr(self.game, 'land_tier', None))
            payload.setdefault('land_gold_rate', getattr(self.game, 'land_gold_rate', 0))
            return payload

        if getattr(self.game, 'state', None) != 'finished':
            return None

        winner_id = getattr(self.game, 'winner_player_id', None)
        if winner_id is None:
            return {
                'success': True,
                'conquer_result': 'draw',
                'attacker_won': False,
                'land_tier': getattr(self.game, 'land_tier', None),
                'land_gold_rate': getattr(self.game, 'land_gold_rate', 0),
            }

        attacker_id = last.get('conquer_attacker_player_id')
        if attacker_id is None:
            attacker_id = getattr(self.game, 'invader_player_id', None)
        if attacker_id is None:
            return None

        attacker_won = (winner_id == attacker_id)
        payload = dict(last)
        payload.update({
            'success': True,
            'conquer_result': 'attacker_won' if attacker_won else 'defender_won',
            'attacker_won': attacker_won,
            'winner_player_id': winner_id,
            'land_tier': getattr(self.game, 'land_tier', None),
            'land_gold_rate': getattr(self.game, 'land_gold_rate', 0),
        })
        return payload

    def _try_resolve_server_finished_battle(self):
        """Resolve already-finished conquer battles without hard-reset fallback."""
        result = self._derive_conquer_result_from_server_state()
        if not result:
            return False

        logger.warning("[BattleScreen] Safety net: derived conquer result from "
              "server state — showing conquer end dialogue")
        self._battle_result = result
        self._handle_conquer_end(result)
        return True

    def _find_figure_by_id(self, figure_id, opponent=False):
        """Find a Figure object by ID from cached figures.

        :param opponent: if True, search opponent figures instead.
        """
        source = self._opponent_figures if opponent else self._player_figures
        for fig in source:
            if getattr(fig, 'id', None) == figure_id:
                return fig
        return None

    def _sync_battle_turns(self):
        """Update game.battle_turns_left based on how many moves the player has used."""
        if not self.game:
            return
        played_count = sum(1 for p in self.player_played if p is not None)
        self.game.battle_turns_left = 3 - played_count

    def _check_auto_skip(self):
        """Auto-skip the battle turn if it's our turn but we have no unused moves left."""
        if getattr(self.game, 'game_over', False):
            return
        if not self.game or not self.is_player_turn or self._auto_skip_pending:
            return
        if (getattr(self.game, 'mode', 'duel') == 'conquer'
                and getattr(self.game, 'conquer_move_model', 'battle_move') == 'tactics_hand'):
            return
        if self._has_played_move_this_turn:
            return
        # Don't skip if all moves are already played (game is over)
        if self._all_moves_played():
            return

        # Count unused (unplayed) moves
        unused = sum(1 for i, m in enumerate(self.player_moves) if not self._is_move_used(i))
        if unused > 0:
            return

        # No moves left to play — auto-skip
        self._auto_skip_pending = True
        logger.info(f"[BattleScreen] No moves left — auto-skipping round {self.current_round + 1}")

        result = game_service.skip_battle_turn(
            self.game.game_id, self.game.player_id)

        if not result.get('success'):
            logger.error(f"[BattleScreen] skip_battle_turn failed: {result.get('message')}")
            self._auto_skip_pending = False
            return

        # Record the skip locally
        skipped_round = self.current_round
        if skipped_round not in self._player_skipped_rounds:
            self._player_skipped_rounds.append(skipped_round)
        self.player_played[skipped_round] = {
            'family_name': 'Skip', 'value': 0, 'suit': '', '_skipped': True
        }

        # Update round and turn from server response
        self.current_round = result.get('battle_round', self.current_round)
        self.is_player_turn = (result.get('battle_turn_player_id') == self.game.player_id)
        self._has_played_move_this_turn = False
        self._auto_skip_pending = False
        self._sync_battle_turns()

    def _all_moves_played(self):
        """Return True when all 6 moves (3 per side) have been played."""
        return (
            all(p is not None for p in self.player_played)
            and all(o is not None for o in self.opponent_played)
        )

    # ──────────────────── event handling ────────────────────────

    def handle_events(self, events):
        """Handle events for the battle screen."""
        super().handle_events(events)

        # Figure detail box takes top priority (modal overlay)
        if self.figure_detail_box:
            response = self.figure_detail_box.handle_events(events)
            if response:
                # During battle any response just closes the box (read-only)
                self.figure_detail_box = None
            # Consume all events while figure detail is open
            return

        # Battle-move detail box takes priority
        if self.battle_move_detail_box:
            response = self.battle_move_detail_box.handle_events(events)
            if response:
                if response == 'close':
                    self.battle_move_detail_box = None
                elif isinstance(response, dict):
                    self._handle_battle_action(response)
                    self.battle_move_detail_box = None
            return

        if self.dialogue_box:
            response = self.dialogue_box.update(events)
            if response:
                callback = self._dialogue_callback
                self._dialogue_callback = None
                self.dialogue_box = None
                if callback:
                    callback(response)
            return

        # Card picker overlay takes priority over normal battle input
        if self._card_picker_active:
            self._handle_card_picker_events(events)
            return

        # Update figure icon hover state on mouse motion
        for event in events:
            if event.type == pygame.MOUSEMOTION:
                for fig_icon in (self.player_figure_icon, self.opponent_figure_icon,
                                 self.player_figure_icon_2, self.opponent_figure_icon_2):
                    if fig_icon:
                        fig_icon.hovered = fig_icon.collide() and fig_icon.is_visible
                break

        # Figure icon click handling
        for fig_icon, fig_obj, fig_list, res_data in (
            (self.player_figure_icon, self.player_figure, self._player_figures, self._resources_data),
            (self.player_figure_icon_2, self.player_figure_2, self._player_figures, self._resources_data),
            (self.opponent_figure_icon, self.opponent_figure, None, self._opponent_resources_data),
            (self.opponent_figure_icon_2, self.opponent_figure_2, None, self._opponent_resources_data),
        ):
            if fig_icon:
                fig_icon.handle_events(events)
                if fig_icon.clicked:
                    # Open a read-only figure detail box
                    self.figure_detail_box = FigureDetailBox(
                        self.window,
                        fig_obj,
                        self.game,
                        all_figures=fig_list,
                        resources_data=res_data,
                    )
                    fig_icon.clicked = False  # reset toggle so it doesn't re-trigger
                    return

        for event in events:
            if event.type == MOUSEBUTTONDOWN:
                # Check finish button click first
                if self._finish_btn_rect and self._finish_btn_rect.collidepoint(event.pos):
                    self._finish_battle()
                    return
                # Check round-panel figure icon clicks
                if self._handle_round_fig_icon_click(event):
                    return
                # Check panel icon clicks (open detail box)
                self._handle_panel_icon_click(event)

    def _handle_round_fig_icon_click(self, event):
        """Check if player clicked a figure icon in the rounds panel."""
        mx, my = event.pos
        for entry in self._round_fig_icons:
            if entry['rect'].collidepoint(mx, my):
                fig = entry['figure']
                is_player = entry['is_player']
                fig_list = self._player_figures if is_player else None
                self.figure_detail_box = FigureDetailBox(
                    self.window,
                    fig,
                    self.game,
                    all_figures=fig_list,
                    resources_data=self._resources_data if is_player else self._opponent_resources_data,
                )
                return True
        return False

    def _handle_panel_icon_click(self, event):
        """Check if player clicked a battle move icon in the left panel."""
        mx, my = event.pos
        icon_s = settings.BATTLE_PANEL_ICON_SIZE

        # Build the same filtered list used by _draw_battle_panel so
        # click positions match the visual positions.
        visible_moves = [(i, m) for i, m in enumerate(self.player_moves)
                         if not self._is_move_used(i)]

        for slot, (i, move) in enumerate(visible_moves):
            panel_cx, icon_cy = self._battle_panel_icon_center(slot)
            icon_rect = pygame.Rect(
                panel_cx - icon_s // 2,
                icon_cy - icon_s // 2,
                icon_s, icon_s,
            )
            if icon_rect.collidepoint(mx, my):
                family_name = move.get('family_name', '')
                bm_suit = move.get('suit', '')
                eligible = self._get_eligible_figures(family_name, bm_suit)
                combinable = self._get_combinable_daggers(move, i)
                # Disable all actions when it's not the player's turn
                not_my_turn = not self.is_player_turn
                # Combine disabled if no candidate daggers or turn conditions
                combine_off = not_my_turn or self._has_played_move_this_turn or not combinable
                # Dismantle disabled if not player turn, or splitting would exceed max moves
                unused_count = sum(1 for j, m in enumerate(self.player_moves) if not self._is_move_used(j))
                dismantle_off = not_my_turn or self._has_played_move_this_turn or unused_count >= 3
                self.battle_move_detail_box = BattleMoveDetailBox(
                    self.window, move,
                    self.battle_move_manager.families_by_name,
                    self.game,
                    is_battle_context=True,
                    eligible_figures=eligible,
                    move_index=i,
                    gamble_disabled=self._is_gamble_disabled(),
                    use_disabled=not_my_turn or self._has_played_move_this_turn,
                    combine_disabled=combine_off,
                    combinable_daggers=combinable,
                    dismantle_disabled=dismantle_off,
                    best_figure_index=self._get_best_figure_index(
                        eligible, bm_suit, move.get('value', 0)),
                    figure_power_bonuses=self._figure_power_bonuses(
                        eligible, is_player=True),
                )
                break

    def _get_combinable_daggers(self, move, move_idx):
        """Return list of other Dagger moves that can be combined with *move*.

        A dagger can combine with another dagger of the same colour (red/black).
        Double Daggers cannot be combined further.
        """
        if move.get('family_name') != 'Dagger':
            return []

        move_suit = move.get('suit', '')
        move_is_red = move_suit in ('Hearts', 'Diamonds')

        result = []
        for j, m in enumerate(self.player_moves):
            if j == move_idx:
                continue
            if m.get('family_name') != 'Dagger':
                continue
            if self._is_move_used(j):
                continue
            other_suit = m.get('suit', '')
            other_is_red = other_suit in ('Hearts', 'Diamonds')
            if move_is_red == other_is_red:
                result.append(m)
        return result

    def _handle_battle_action(self, action_dict):
        """Process an action chosen from the battle-move detail box."""
        action = action_dict.get('action')
        move_idx = action_dict.get('move_index')
        selected_fig = action_dict.get('selected_figure')
        logger.info(f"[BattleScreen] Action '{action}' for move {move_idx}, figure={getattr(selected_fig, 'name', None)}")

        if action == 'use':
            self._start_use(move_idx, selected_fig)
        elif action == 'gamble':
            self._start_gamble(move_idx)
        elif action == 'combine':
            selected_dagger = action_dict.get('selected_dagger')
            self._start_combine(move_idx, selected_dagger)
        elif action == 'dismantle':
            self._start_dismantle(move_idx)

    # ────────────────── use (play) logic ──────────────────────

    def _start_use(self, move_idx, selected_figure=None):
        """Show confirmation dialogue before playing a battle move."""
        if move_idx >= len(self.player_moves):
            return
        move = self.player_moves[move_idx]
        family_name = move.get('family_name', '')

        self._pending_use_move = move_idx
        self._pending_use_figure = selected_figure

        # Build the confirmation icon
        icon_surf = self._render_move_icon_surface(move)

        if family_name in self.CALL_FIELD_MAP and selected_figure:
            fig_name = getattr(selected_figure, 'name', str(selected_figure))
            msg = f"Play {family_name} with {fig_name}?"
        elif family_name in self.CALL_FIELD_MAP:
            msg = f"Play {family_name} with no figure (base power {move.get('value', 0)})?"
        elif family_name == 'Block':
            msg = f"Play Block?\n\nThis will nullify the current round — both players score 0."
        else:
            msg = f"Play {family_name} (power {move.get('value', 0)})?"

        self.make_dialogue_box(
            msg,
            actions=['use!', 'cancel'],
            images=[icon_surf],
            title="Play Battle Move",
        )
        self._dialogue_callback = self._on_use_confirmed

    def _on_use_confirmed(self, response):
        """Handle use-move confirmation dialogue response."""
        move_idx = getattr(self, '_pending_use_move', None)
        selected_fig = getattr(self, '_pending_use_figure', None)
        self._pending_use_move = None
        self._pending_use_figure = None

        if getattr(self.game, 'game_over', False):
            return
        if response != 'use!' or move_idx is None:
            return

        if move_idx >= len(self.player_moves):
            return

        move = self.player_moves[move_idx]  # original server dict
        family_name = move.get('family_name', '')
        battle_move_id = move.get('id')

        # Determine call_figure_id if this is a Call move
        call_figure_id = None
        if family_name in self.CALL_FIELD_MAP and selected_fig:
            call_figure_id = getattr(selected_fig, 'id', None)

        # Send to server
        result = game_service.play_battle_move(
            self.game.game_id,
            self.game.player_id,
            battle_move_id,
            call_figure_id=call_figure_id,
        )

        if not result.get('success'):
            msg = result.get('message', 'Unknown error')
            logger.error(f"[BattleScreen] play_battle_move failed: {msg}")
            self.make_dialogue_box(
                f"Failed to play move:\n{msg}",
                actions=['ok'], icon='info', title="Error")
            return

        logger.info(f"[BattleScreen] Played {family_name} (id={battle_move_id}) "
              f"in round {self.current_round + 1}")

        # Store a local copy for immediate visual feedback
        played = dict(move)  # shallow copy
        if family_name == 'Block':
            played['value'] = 0
        if family_name in self.CALL_FIELD_MAP and selected_fig:
            played['_call_figure'] = selected_fig
        played_round = self.current_round  # save before server updates it
        played['played_round'] = played_round
        self.player_played[played_round] = played

        # Mark the move as used in the player_moves list too
        self.player_moves[move_idx]['played_round'] = played_round

        self._has_played_move_this_turn = True
        self._gambled_this_round = False
        self._sync_battle_turns()

        # Update round and turn from server response
        self.current_round = result.get('battle_round', self.current_round)
        self.is_player_turn = (result.get('battle_turn_player_id') == self.game.player_id)
        self._has_played_move_this_turn = False

    # ────────────────── battle resolution ──────────────────────

    def _finish_battle(self):
        """Call the server to resolve the battle once all 6 moves have been played."""
        if not self._all_moves_played():
            return

        total_diff = self._get_total_diff(verbose=True)
        logger.info(f"[BattleScreen] Finishing battle — total_diff = {total_diff}")

        result = game_service.finish_battle(
            self.game.game_id,
            self.game.player_id,
            total_diff,
        )

        if not result.get('success'):
            msg = result.get('message', 'Unknown error')
            self.make_dialogue_box(f"Failed to finish battle:\n{msg}", actions=['ok'], icon='info', title="Error")
            return

        self._battle_result = result
        # Clear the safety-net data — we're about to show the proper dialogue
        if self.game:
            self.game._last_polled_battle_result = None

        # Finished conquer games are resolved server-side and should route
        # directly to the conquer end dialogue.
        if result.get('conquer_result'):
            self._handle_conquer_end(result)
            return

        outcome = result.get('outcome', '')

        # If already resolved by the other client, use the game state
        # from the server and show appropriate result
        if result.get('already_resolved'):
            if result.get('game'):
                self.game.update_from_dict(result['game'])
            winner_id = result.get('winner_player_id')
            if outcome == 'draw':
                self._show_draw_result(result)
            elif winner_id == self.game.player_id:
                self._show_victory_result(result)
            else:
                self._show_defeat_result(result)
            return

        if outcome == 'draw':
            self._show_draw_result(result)
        elif outcome == 'win':
            winner_id = result.get('winner_player_id')
            if winner_id == self.game.player_id:
                self._show_victory_result(result)
            else:
                self._show_defeat_result(result)
        else:
            self.make_dialogue_box("Battle resolved.", actions=['ok'], title="Battle")
            self._dialogue_callback = self._on_result_acknowledged

    def _show_victory_result(self, result):
        """Display victory dialogue — player won the battle."""
        pts = result.get('points_awarded', 0)
        fig_name = result.get('destroyed_figure_name', 'figure')
        loser = result.get('loser_name', 'Opponent')
        self._returnable_cards = result.get('returnable_cards', [])
        self._game_over_pending = result.get('game_over_pending', False)
        is_conquer = getattr(self.game, 'mode', 'duel') == 'conquer'

        if is_conquer or self._game_over_pending:
            # Game is ending — show clean victory without card pick
            if is_conquer:
                msg = f"{loser}'s {fig_name} is destroyed!"
            else:
                msg = (
                    f"{loser}'s {fig_name} is destroyed!\n"
                    f"You earn {pts} points."
                )
            actions = ['ok']
        else:
            msg = (
                f"{loser}'s {fig_name} is destroyed!\n"
                f"You earn {pts} points.\n\n"
                f"Pick one card from the spoils."
            )
            actions = ['pick card']

        images = []

        # Show destroyed opponent's figure icon with red X
        fig_family_name = result.get('destroyed_figure_family', '')
        destroyed_icon = self._make_destroyed_figure_icon(fig_family_name)
        if destroyed_icon:
            images.append(destroyed_icon)

        large_icon = settings.DIALOGUE_BOX_LARGE_ICON_DICT.get('victory')
        if large_icon:
            images.append(large_icon)

        self.make_dialogue_box(msg, actions=actions, icon='victory', title="Victory!", images=images)
        self._dialogue_callback = self._on_victory_dialogue

    def _show_defeat_result(self, result):
        """Display defeat dialogue — player lost the battle."""
        pts = result.get('points_awarded', 0)
        fig_name = result.get('destroyed_figure_name', 'figure')
        winner = result.get('winner_name', 'Opponent')
        is_conquer = getattr(self.game, 'mode', 'duel') == 'conquer'

        if is_conquer:
            msg = f"Your {fig_name} is destroyed!"
        else:
            msg = (
                f"Your {fig_name} is destroyed!\n"
                f"{winner} earns {pts} points."
            )

        images = []

        # Build destroyed-figure icon with red X overlay
        fig_family_name = result.get('destroyed_figure_family', '')
        destroyed_icon = self._make_destroyed_figure_icon(fig_family_name)
        if destroyed_icon:
            images.append(destroyed_icon)

        large_icon = settings.DIALOGUE_BOX_LARGE_ICON_DICT.get('defeat')
        if large_icon:
            images.append(large_icon)

        self.make_dialogue_box(msg, actions=['ok'], icon='defeat', title="Defeat", images=images)
        self._dialogue_callback = self._on_defeat_acknowledged

    def _make_destroyed_figure_icon(self, family_name):
        """Create a figure icon surface with a red X drawn over it."""
        if not family_name:
            return None
        family = self.figure_manager.families.get(family_name)
        if not family or not family.icon_img:
            return None
        # Start with a copy of the icon
        size = settings.DIALOGUE_BOX_IMG_HEIGHT
        raw = family.icon_img.convert_alpha()
        icon = pygame.transform.smoothscale(raw, (size, size))
        # Draw red X
        margin = int(size * 0.12)
        line_w = max(3, size // 16)
        red = (220, 40, 40)
        pygame.draw.line(icon, red, (margin, margin), (size - margin, size - margin), line_w)
        pygame.draw.line(icon, red, (size - margin, margin), (margin, size - margin), line_w)
        return icon

    def _show_draw_result(self, result):
        """Display draw dialogue — the defender gets to choose.
        In conquer mode, land ownership is unchanged and attack cards return."""
        is_conquer = getattr(self.game, 'mode', 'duel') == 'conquer'

        # Conquer mode: show result and return to kingdom. Support fallback
        # payloads that only include outcome='draw'.
        if is_conquer and (
            result.get('conquer_result') == 'draw'
            or (result.get('outcome') == 'draw' and not result.get('conquer_result'))
        ):
            conquer_payload = result
            if conquer_payload.get('conquer_result') != 'draw':
                conquer_payload = dict(conquer_payload)
                conquer_payload['conquer_result'] = 'draw'
                conquer_payload.setdefault('attacker_won', False)
            self._handle_conquer_end(conquer_payload)
            return

        defender_id = result.get('defender_player_id')
        self._returnable_cards = result.get('returnable_cards', [])

        large_icon = settings.DIALOGUE_BOX_LARGE_ICON_DICT.get('draw')
        images = [large_icon] if large_icon else []

        if defender_id == self.game.player_id:
            msg = (
                "As the defender, you may choose one:\n"
                "  • Destroy the opponent's battle figure\n"
                "  • Gain 10 points\n"
                "  • Pick one battle card"
            )
            self.make_dialogue_box(
                msg,
                actions=['destroy figure', '10 points', 'pick card'],
                icon='draw',
                title="Draw — Your Choice",
                images=images,
            )
            self._dialogue_callback = self._on_draw_choice
        else:
            opp_name = self.game.opponent_name or "Opponent"
            msg = (
                f"{opp_name} is the defender and will make a choice."
            )
            self.make_dialogue_box(msg, actions=['ok'], icon='draw', title="Draw", images=images)
            self._dialogue_callback = self._on_draw_wait_acknowledged

    # ─── victory callbacks ───

    def _on_victory_dialogue(self, response):
        """Handle victory dialogue: opens card picker or skips to game-over."""
        if getattr(self, '_game_over_pending', False):
            # Game is ending — skip card pick, finalize immediately
            self._finalise_winner_pick(None, None)
            return
        if self._returnable_cards:
            self._show_card_pick_dialogue()
        else:
            self._finalise_winner_pick(None, None)

    def _show_card_pick_dialogue(self):
        """Show the interactive card picker for the winner to pick one card."""
        cards = self._returnable_cards
        if not cards:
            self._finalise_winner_pick(None, None)
            return

        self._awaiting_card_pick = True
        self._open_card_picker(
            cards,
            title="Pick a Card",
            callback=self._on_card_picked,
        )

    def _on_card_picked(self, card_data):
        """Handle the card picker confirm for a victory pick."""
        self._awaiting_card_pick = False
        if card_data:
            self._picked_card_data = card_data
            self._finalise_winner_pick(card_data.get('id'), card_data.get('card_type', 'main'))
        else:
            self._picked_card_data = None
            self._finalise_winner_pick(None, None)

    def _collect_resting_figure_ids(self):
        """Return list of figure IDs that need to rest after this battle."""
        resting = []
        for fig in (self.player_figure, self.opponent_figure,
                     getattr(self, 'player_figure_2', None),
                     getattr(self, 'opponent_figure_2', None)):
            if fig and getattr(fig, 'rest_after_attack', False):
                resting.append(fig.id)
        return resting or None

    def _finalise_winner_pick(self, card_id, card_type):
        """Call the server to pick a card and do post-battle cleanup."""
        resting_ids = self._collect_resting_figure_ids()
        result = game_service.finish_battle_pick_card(
            self.game.game_id,
            self.game.player_id,
            picked_card_id=card_id,
            picked_card_type=card_type or 'main',
            resting_figure_ids=resting_ids,
        )
        if result.get('success') and result.get('game'):
            self.game.update_from_dict(result['game'])
        # Check if this battle ended the game
        if result.get('game_over'):
            self.game.pending_game_over = result['game_over']
            self.game.game_over = True
        # Conquer mode: server returns conquer_result instead of game_over
        if result.get('conquer_result'):
            self._handle_conquer_end(result)
            return
        self._reset_after_battle()

    # ─── defeat callback ───

    def _on_defeat_acknowledged(self, response):
        """After defeat dialogue, just reset locally.
        The winner's client handles server-side cleanup (card pick + new round).
        """
        if getattr(self.game, 'mode', 'duel') == 'conquer' and self.game:
            # Never pick a card on the loser path. Query battle status and
            # consume conquer_result once the winner has finalized their pick.
            result = game_service.finish_battle(
                self.game.game_id,
                self.game.player_id,
                total_diff=0,
            )

            if result.get('success') and result.get('game'):
                self.game.update_from_dict(result['game'])

            if result.get('conquer_result'):
                self._handle_conquer_end(result)
                return

            # Fallback: if winner pick has not completed yet, route via the
            # conquer game-over dialogue once polling catches up.
            if result.get('success'):
                self.game.pending_game_over = {
                    'winner_player_id': result.get('winner_player_id')
                }
                self.game.game_over = True

        self._reset_after_battle()

    # ─── draw callbacks ───

    def _on_draw_choice(self, response):
        """Handle the defender's draw choice."""
        choice_map = {
            'destroy figure': 'destroy',
            '10 points': 'points',
            'pick card': 'pick_card',
        }
        choice = choice_map.get(response)
        if not choice:
            return

        if choice == 'pick_card' and self._returnable_cards:
            # Show card picker then call finish_battle_draw
            self._awaiting_draw_choice = True
            self._show_draw_card_pick()
            return

        # For 'destroy' and 'points' — call server immediately
        resting_ids = self._collect_resting_figure_ids()
        result = game_service.finish_battle_draw(
            self.game.game_id,
            self.game.player_id,
            choice=choice,
            resting_figure_ids=resting_ids,
        )
        if result.get('success') and result.get('game'):
            self.game.update_from_dict(result['game'])
        if result.get('game_over'):
            self.game.pending_game_over = result['game_over']
            self.game.game_over = True
        if result.get('conquer_result'):
            self._handle_conquer_end(result)
            return
        self._reset_after_battle()

    def _show_draw_card_pick(self):
        """Show card picker for draw defender pick_card choice."""
        cards = self._returnable_cards
        self._open_card_picker(
            cards,
            title="Pick a Card",
            callback=self._on_draw_card_picked,
        )

    def _on_draw_card_picked(self, card_data):
        """Handle draw card pick confirm."""
        self._awaiting_draw_choice = False
        picked_id = card_data.get('id') if card_data else None
        picked_type = card_data.get('card_type', 'main') if card_data else 'main'

        result = game_service.finish_battle_draw(
            self.game.game_id,
            self.game.player_id,
            choice='pick_card',
            picked_card_id=picked_id,
            picked_card_type=picked_type,
            resting_figure_ids=self._collect_resting_figure_ids(),
        )
        if result.get('success') and result.get('game'):
            self.game.update_from_dict(result['game'])
        if result.get('game_over'):
            self.game.pending_game_over = result['game_over']
            self.game.game_over = True
        if result.get('conquer_result'):
            self._handle_conquer_end(result)
            return
        self._reset_after_battle()

    def _on_draw_wait_acknowledged(self, response):
        """Non-defender acknowledged draw — battle cleanup happens when defender resolves."""
        # The defender will resolve it; we just return to field and update on next poll.
        self._reset_after_battle()

    # ─── conquer end ───

    def _handle_conquer_end(self, result):
        """Handle the end of a conquer battle — show result and route to kingdom."""
        from game.components.cards.card_img import CardImg
        if self.game:
            if getattr(self.game, '_conquer_result_dialogue_shown', False):
                return
            self.game._conquer_result_dialogue_shown = True
        attacker_won = result.get('attacker_won', False)
        conquer_result = result.get('conquer_result', '')
        is_attacker = self._is_current_player_conquer_attacker(result)
        images = []

        def _card_line(card):
            if not isinstance(card, dict):
                return None
            rank = card.get('rank')
            suit = card.get('suit')
            if rank and suit:
                return f"{rank} of {suit}"
            if rank:
                return str(rank)
            if suit:
                return str(suit)
            return None

        def _card_lines(cards, max_lines=10):
            lines = []
            for card in cards or []:
                label = _card_line(card)
                if label:
                    lines.append(label)
            if len(lines) <= max_lines:
                return lines
            overflow = len(lines) - max_lines
            clipped = lines[:max_lines]
            clipped.append(f"... and {overflow} more")
            return clipped

        def _append_card_images(cards):
            for card in (cards or [])[:4]:
                if not isinstance(card, dict):
                    continue
                suit = card.get('suit')
                rank = card.get('rank')
                if suit and rank:
                    images.append(CardImg(self.window, suit, rank).front_img)

        def _append_loot_section(message, title, cards):
            lines = _card_lines(cards)
            if lines:
                message += f"\n\n{title}\n" + "\n".join(f"• {line}" for line in lines)
            return message

        if conquer_result == 'draw':
            title = "Draw!"
            icon = 'draw'
            message = (
                "The battle ended in a draw.\n\n"
                "The land remains unchanged. No cards were looted; all attack cards returned to your collection."
            )
        elif attacker_won and is_attacker:
            # Attacker won — we are the attacker
            land_tier = result.get('land_tier')
            gold_rate = result.get('land_gold_rate', 0)
            land_label = "Tier {} land".format(land_tier) if land_tier else "this land"
            title = "Land Conquered!"
            icon = 'victory'
            message = "You have conquered {}!".format(land_label)
            if gold_rate:
                message += "\n\nGold production increased by {:.1f} gold/hour.".format(gold_rate)
            loot_gained = result.get('loot_gained_cards') or result.get('loot_lost_cards') or []
            if loot_gained:
                message = _append_loot_section(
                    message,
                    "Loot gained (pending collection):",
                    loot_gained,
                )
                message += "\n\nCollect looted cards from the Loot Inbox in your kingdom configuration."
                _append_card_images(loot_gained)
        elif attacker_won and not is_attacker:
            # Attacker won — we are the defender
            title = "Land Lost!"
            icon = 'defeat'
            message = "The attacker has conquered your land."
            loot_lost = result.get('loot_lost_cards') or result.get('loot_gained_cards') or []
            if loot_lost:
                message = _append_loot_section(message, "Loot lost:", loot_lost)
                _append_card_images(loot_lost)
            message += "\n\nEvery unlooted defence card returned to your collection."
        elif not attacker_won and is_attacker:
            # Defender won — we are the attacker (we lost)
            title = "Attack Failed"
            icon = 'defeat'
            is_ai_defender = bool(result.get('is_ai_defender'))
            loot_lost_cards = result.get('loot_lost_cards') or []

            message = "You did not conquer this land."
            if loot_lost_cards:
                loot_title = "Cards destroyed by AI defence:" if is_ai_defender else "Cards looted by defending kingdom:"
                message = _append_loot_section(message, loot_title, loot_lost_cards)
                _append_card_images(loot_lost_cards)
            message += "\n\nEvery unlooted attack card returned to your collection."
        else:
            # Defender won — we are the defender
            title = "Defence Successful!"
            icon = 'victory'
            message = "You defended your land successfully!"
            loot_gained = result.get('loot_gained_cards') or result.get('loot_lost_cards') or []
            if loot_gained:
                message = _append_loot_section(
                    message,
                    "Loot gained (pending collection):",
                    loot_gained,
                )
                message += "\n\nCollect looted cards from the Loot Inbox in your kingdom configuration."
                _append_card_images(loot_gained)

        # Mark game as over so the game_screen routes back to kingdom
        if self.game:
            self.game.game_over = True
            self.game.conquer_result = conquer_result

        self.make_dialogue_box(message, actions=['ok'], icon=icon, title=title, images=images if images else None)
        self._dialogue_callback = self._on_conquer_end_acknowledged

    def _is_current_player_conquer_attacker(self, result=None):
        """Return whether this client is the original conquer attacker."""
        game = self.game
        if not game:
            return False

        result = result or {}
        last = getattr(game, 'last_battle_result', None) or getattr(
            game, '_last_polled_battle_result', {}) or {}
        attacker_id = (
            result.get('conquer_attacker_player_id')
            or last.get('conquer_attacker_player_id')
        )
        if attacker_id is not None:
            return str(attacker_id) == str(getattr(game, 'player_id', None))

        active_spells = (
            getattr(game, 'cached_active_spells', None)
            or getattr(game, 'active_spells', None)
            or []
        )
        for spell in active_spells:
            if not isinstance(spell, dict):
                continue
            effect_data = spell.get('effect_data')
            if (spell.get('spell_name') == 'Invader Swap'
                    and isinstance(effect_data, dict)
                    and effect_data.get('conquer_invader_swap')):
                old_invader_id = effect_data.get('old_invader_id')
                if old_invader_id is not None:
                    return str(old_invader_id) == str(getattr(game, 'player_id', None))

        return bool(getattr(game, 'invader', False))

    def _on_conquer_end_acknowledged(self, response):
        """After conquer end dialogue, reset and route to kingdom screen."""
        if self.game:
            self.game.in_battle_phase = False
            self.game.battle_turns_left = 0
        self._battle_result = None
        self.state.subscreen = 'field'
        # Signal the game_screen to go back to kingdom
        if self.game:
            self.game._conquer_battle_ended = True

    # ─── interactive card picker ───

    def _open_card_picker(self, cards_data, title="Pick a Card", callback=None):
        """Open the interactive card picker overlay.

        :param cards_data: list of card dicts (with suit, rank, id, card_type).
        :param title: title text shown above the cards.
        :param callback: function(card_data) called when the player confirms.
        """
        from game.components.cards.card_img import CardImg

        self._card_picker_active = True
        self._card_picker_selected = None
        self._card_picker_hovered = None
        self._card_picker_callback = callback
        self._card_picker_title = title

        # Build card objects with rects (positions will be computed in draw)
        self._card_picker_cards = []
        for c in cards_data:
            suit = c.get('suit', '?')
            rank = c.get('rank', '?')
            card_img = CardImg(self.window, suit, rank)
            self._card_picker_cards.append({
                'card_img': card_img,
                'card_data': c,
                'rect': None,  # computed during draw
            })

        # Compute the overlay box dimensions
        num = len(self._card_picker_cards)
        card_w = settings.CARD_WIDTH
        card_h = settings.CARD_HEIGHT
        spacing = settings.SMALL_SPACER_X
        title_h = int(0.06 * settings.SCREEN_HEIGHT)
        label_h = int(0.03 * settings.SCREEN_HEIGHT)
        btn_h = settings.DIALOGUE_BOX_BTN_H
        padding = settings.SMALL_SPACER_X

        cards_row_w = num * card_w + (num - 1) * spacing
        box_w = max(cards_row_w + 2 * padding, int(0.3 * settings.SCREEN_WIDTH))
        box_h = title_h + card_h + label_h + spacing + btn_h + 2 * padding
        box_x = settings.CENTER_X - box_w // 2
        box_y = settings.CENTER_Y - box_h // 2
        self._card_picker_box_rect = pygame.Rect(box_x, box_y, box_w, box_h)

        # Pre-render overlay and rounded panel
        _SW, _SH = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT
        self._card_picker_overlay = pygame.Surface((_SW, _SH), pygame.SRCALPHA)
        self._card_picker_overlay.fill(settings.DIALOGUE_BOX_OVERLAY_CLR)
        _corner_r = settings.DIALOGUE_BOX_CORNER_R
        self._card_picker_panel = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
        pygame.draw.rect(self._card_picker_panel, settings.DIALOGUE_BOX_BG_CLR,
                         self._card_picker_panel.get_rect(), border_radius=_corner_r)
        pygame.draw.rect(self._card_picker_panel, settings.DIALOGUE_BOX_BORDER_CLR,
                         self._card_picker_panel.get_rect(),
                         settings.DIALOGUE_BOX_BORDER_WIDTH, border_radius=_corner_r)

        # Create themed confirm button (centred at bottom of box)
        btn_w = settings.DIALOGUE_BOX_BTN_W
        btn_x = settings.CENTER_X - btn_w // 2
        btn_y = box_y + box_h - btn_h - padding
        self._card_picker_confirm_btn = _DlgButton(self.window, btn_x, btn_y, "Confirm",
                                                   width=btn_w, height=btn_h)
        self._card_picker_confirm_btn.disabled = True

        # Pre-compute card rects
        cards_start_x = settings.CENTER_X - cards_row_w // 2
        card_top_y = box_y + title_h + padding
        for i, entry in enumerate(self._card_picker_cards):
            cx = cards_start_x + i * (card_w + spacing)
            entry['rect'] = pygame.Rect(cx, card_top_y, card_w, card_h)

    def _draw_card_picker(self):
        """Render the card picker overlay on top of the battle screen."""
        if not self._card_picker_active:
            return

        # Pre-rendered dim overlay
        self.window.blit(self._card_picker_overlay, (0, 0))

        box = self._card_picker_box_rect
        # Pre-rendered rounded panel
        self.window.blit(self._card_picker_panel, box.topleft)

        # Title
        title_font = settings.get_font(settings.FONT_SIZE_TITLE_DIALOGUE_BOX, bold=True)
        title_surf = title_font.render(self._card_picker_title, True, settings.TITLE_TEXT_COLOR)
        # Icon on both sides of title
        icon_surface = None
        if 'loot' in settings.DIALOGUE_BOX_ICON_NAME_TO_IMG_DICT:
            orig = settings.DIALOGUE_BOX_ICON_NAME_TO_IMG_DICT['loot']
            ih = settings.DIALOGUE_BOX_ICON_HEIGHT
            iw = int(orig.get_width() * ih / orig.get_height())
            icon_surface = pygame.transform.smoothscale(orig, (iw, ih))
        title_rect = title_surf.get_rect(centerx=box.centerx, top=box.top + settings.SMALL_SPACER_Y)
        if icon_surface:
            self.window.blit(icon_surface, (title_rect.left - icon_surface.get_width() - 6,
                                            title_rect.centery - icon_surface.get_height() // 2))
            self.window.blit(icon_surface, (title_rect.right + 6,
                                            title_rect.centery - icon_surface.get_height() // 2))
        self.window.blit(title_surf, title_rect)

        # Separator below title
        sep_y = title_rect.bottom + settings.SMALL_SPACER_Y // 2
        pygame.draw.line(self.window, settings.DIALOGUE_BOX_SEP_CLR,
                         (box.left + settings.SMALL_SPACER_X, sep_y),
                         (box.right - settings.SMALL_SPACER_X, sep_y), 1)

        # Draw cards
        mx, my = pygame.mouse.get_pos()
        self._card_picker_hovered = None

        for i, entry in enumerate(self._card_picker_cards):
            card_img = entry['card_img']
            rect = entry['rect']
            is_selected = (i == self._card_picker_selected)
            is_hovered = rect.collidepoint(mx, my)

            if is_hovered:
                self._card_picker_hovered = i

            if is_selected:
                # Selected: bright + golden border
                card_img.draw_front_bright(rect.x, rect.y)
                pygame.draw.rect(self.window, (255, 215, 0), rect.inflate(6, 6), 3)
            elif is_hovered:
                # Hovered: bright
                card_img.draw_front_bright(rect.x, rect.y)
            else:
                # Default: slightly dimmed
                card_img.draw_front(rect.x, rect.y)

            # Card label below
            label_font = settings.get_font(int(0.018 * settings.SCREEN_HEIGHT))
            suit = entry['card_data'].get('suit', '?')
            rank = entry['card_data'].get('rank', '?')
            label = f"{rank} of {suit}"
            if is_selected:
                label_color = settings.TITLE_TEXT_COLOR
            elif is_hovered:
                label_color = settings.DIALOGUE_BOX_BTN_TEXT_HOVER_CLR
            else:
                label_color = settings.DIALOGUE_BOX_MSG_TEXT_CLR
            label_surf = label_font.render(label, True, label_color)
            label_rect = label_surf.get_rect(centerx=rect.centerx, top=rect.bottom + 4)
            self.window.blit(label_surf, label_rect)

        # Draw themed confirm button
        btn = self._card_picker_confirm_btn
        if self._card_picker_selected is not None:
            btn.disabled = False
        else:
            btn.disabled = True

        # Draw button (themed _DlgButton handles disabled styling internally)
        btn.draw()

    def _handle_card_picker_events(self, events):
        """Handle events for the card picker overlay. Returns True if events were consumed."""
        if not self._card_picker_active:
            return False

        btn = self._card_picker_confirm_btn
        btn.update()

        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN:
                # Check card clicks
                for i, entry in enumerate(self._card_picker_cards):
                    if entry['rect'] and entry['rect'].collidepoint(event.pos):
                        self._card_picker_selected = i
                        break

                # Check confirm button click
                if (not btn.disabled and btn.collide()):
                    selected = self._card_picker_selected
                    self._card_picker_active = False
                    callback = self._card_picker_callback
                    card_data = self._card_picker_cards[selected]['card_data'] if selected is not None else None
                    # Reset picker state
                    self._card_picker_cards = []
                    self._card_picker_selected = None
                    self._card_picker_hovered = None
                    self._card_picker_callback = None
                    self._card_picker_confirm_btn = None
                    self._card_picker_box_rect = None
                    if callback:
                        callback(card_data)

        return True  # always consume events while picker is active

    def _on_result_acknowledged(self, response):
        """Generic result acknowledgment (fallback)."""
        self._reset_after_battle()

    def _reset_after_battle(self):
        """Clean up battle state and switch back to the field screen."""
        import traceback
        caller = traceback.extract_stack(limit=3)
        caller_info = f"{caller[-2].name}" if len(caller) >= 2 else "unknown"
        had_result = self._battle_result is not None
        logger.info(f"[BattleScreen] Post-battle cleanup — returning to field "
              f"(caller={caller_info}, had_result={had_result})")

        # Safety net: if we're exiting the battle without having shown a
        # battle-result dialogue (e.g. race condition, missed finish_battle),
        # queue a fallback notification on the game_screen so the user still
        # sees who won.
        if not had_result and self.game:
            last = getattr(self.game, '_last_polled_battle_result', None) or {}
            winner_id = last.get('winner_player_id')
            loser_id = last.get('loser_player_id')
            if winner_id and loser_id:
                is_winner = (winner_id == self.game.player_id)
                destroyed = last.get('destroyed_figure_name', 'figure')
                pts = last.get('points_awarded', 0)
                winner_name = last.get('winner_name', 'Opponent')
                loser_name = last.get('loser_name', 'Opponent')
                if is_winner:
                    msg = (f"{loser_name}'s {destroyed} is destroyed!\n"
                           f"You earn {pts} points.")
                    title = "Victory!"
                    icon = 'victory'
                else:
                    msg = (f"Your {destroyed} is destroyed!\n"
                           f"{winner_name} earns {pts} points.")
                    title = "Defeat"
                    icon = 'defeat'
                parent = getattr(self.state, 'parent_screen', None)
                if parent and hasattr(parent, 'queue_or_show_notification'):
                    logger.warning(f"[BattleScreen] Safety net: queuing missed battle result "
                          f"(winner={winner_name}, loser={loser_name})")
                    parent.queue_or_show_notification({
                        'message': msg,
                        'actions': ['ok'],
                        'icon': icon,
                        'title': title,
                    })

        # Reset battle phase flags
        if self.game:
            self.game.in_battle_phase = False
            self.game.battle_turns_left = 0
            # Clear advance / defender selection state to prevent stuck prompts
            self.game.pending_defender_selection = False
            self.game.defender_selection_dialogue_shown = False
            self.game.waiting_for_defender_pick_shown = False
            self.game.pending_waiting_for_defender_pick = False
            self.game.pending_forced_advance = False
            self.game.forced_advance_dialogue_shown = False
            self.game.pending_battle_ready = False
            # Keep battle_ready_shown = True so stale in-flight polls can't
            # re-trigger the fight/fold dialogue.  It's reset by
            # _apply_game_dict when the server clears advancing_figure_id.
            self.game.battle_ready_shown = True
            self.game.pending_own_advance_notification = False
            self.game.pending_advance_notification = False
            self.game.waiting_for_battle_decision = False
            self.game.pending_fold_result = False
            # Keep fold_result_shown = True (same logic as battle_ready_shown)
            self.game.fold_result_shown = True
            self.game.auto_proceed_to_battle = False
            self.game.battle_moves_phase = False
            self.game.battle_moves_ready = False
            self.game.waiting_for_opponent_battle_moves = False
            self.game.both_battle_moves_ready = False
            # Suppress the next turn summary — battle result was already shown
            # in the victory/defeat/draw dialogue.
            self.game.suppress_next_turn_summary = True
            # Clear any stale ceasefire-ended flag so a queued notification from
            # mid-battle doesn't fire after returning to the field screen.
            self.game.pending_ceasefire_ended = False
            # Queue ceasefire-active notification for the new round
            # (only if not already displayed this round)
            if self.game.ceasefire_active and self.game._ceasefire_active_displayed_round != self.game.current_round:
                logger.info(f"[CEASEFIRE] _reset_after_battle: queuing ceasefire-active, round={self.game.current_round}")
                self.game.pending_ceasefire_active_notification = True
                # Mark as notified so polling doesn't re-trigger
                self.game._ceasefire_notified_round = self.game.current_round
                self.game._ceasefire_notified_state = 'active'

        # Clear all local battle state
        self.reset_state()

        # Force battle shop to reload moves from server (they were deleted server-side)
        parent = getattr(self.state, 'parent_screen', None)
        if parent and hasattr(parent, 'subscreens'):
            battle_shop = parent.subscreens.get('battle_shop')
            if battle_shop:
                battle_shop.bought_moves = []
                battle_shop._loaded_game_key = None
                battle_shop._battle_moves_confirmed = False
                battle_shop._waiting_for_opponent = False

        # Flush stale queued game-screen notifications from the battle phase.
        # Important flag-based notifications (side cards, loot, auto-fill) use
        # their own flags and will re-queue when their check_ methods run again.
        if parent and hasattr(parent, 'pending_notifications'):
            parent.pending_notifications = []

        # Discard any stale poller result so old server data (with modifiers/
        # ceasefire still active) doesn't re-trigger notifications after battle.
        if parent and hasattr(parent, '_game_poller') and parent._game_poller:
            if parent._game_poller.has_result():
                _ = parent._game_poller.result

        # Sync modifier tracking so stale poll data doesn't look "new"
        if parent and hasattr(parent, '_previous_battle_modifiers'):
            current = self.game.battle_modifier if self.game else []
            parent._previous_battle_modifiers = list(current) if isinstance(current, list) else []

        # Switch subscreen
        self.state.subscreen = 'field'

        # Conquer panel state lives on the parent ConquerGameScreen — when a
        # conquer battle finishes, wipe it so the next conquest doesn't show
        # stale spell icons / battle figures / events.
        if parent and hasattr(parent, 'reset_conquer_panel_state'):
            try:
                parent.reset_conquer_panel_state()
            except Exception:
                pass

        # Check for game-over after returning to field
        if self.game and self.game.pending_game_over and not self.game.game_over_shown:
            if parent and hasattr(parent, '_show_game_over_dialogue'):
                parent._show_game_over_dialogue(self.game.pending_game_over)

    # ────────────────── gamble logic ───────────────────────────

    def _is_gamble_disabled(self):
        """Return True when the gamble button should be greyed out.

        Gamble is only allowed when it is the player's turn, has not gambled
        this round yet, and has not played a move this turn.
        """
        if not self.is_player_turn:
            return True
        return self._gambled_this_round or self._has_played_move_this_turn

    def _render_gamble_result_card(self, move):
        """Render a gamble-result card: move icon on top, name + suit icon below."""
        icon_surf = self._render_move_icon_surface(move)
        family_name = move.get('family_name', '')
        suit = move.get('suit', '')

        # Name text
        name_txt = self.font_small.render(family_name, True, (230, 210, 170))
        txt_h = name_txt.get_height()

        # Suit icon scaled to match text height
        suit_icon = self._panel_suit_icon_cache.get(suit)
        if suit_icon:
            s_icon = pygame.transform.smoothscale(suit_icon, (txt_h, txt_h))
            label_w = name_txt.get_width() + 6 + txt_h
        else:
            s_icon = None
            label_w = name_txt.get_width()

        # Compose vertically: icon on top, label centred below
        gap = 6
        total_w = max(icon_surf.get_width(), label_w)
        total_h = icon_surf.get_height() + gap + txt_h
        card = pygame.Surface((total_w, total_h), pygame.SRCALPHA)
        card.blit(icon_surf, ((total_w - icon_surf.get_width()) // 2, 0))
        lx = (total_w - label_w) // 2
        card.blit(name_txt, (lx, icon_surf.get_height() + gap))
        if s_icon:
            card.blit(s_icon, (lx + name_txt.get_width() + 6, icon_surf.get_height() + gap))
        return card

    def _render_move_icon_surface(self, move):
        """Render a battle move icon (with glow, frame, power, suit) to a Surface for dialogues."""
        family_name = move.get('family_name', '')
        suit = move.get('suit', '')
        power_value = self._get_panel_display_power(move)
        suit_b = move.get('suit_b') if family_name == 'Double Dagger' else None

        icon_s = settings.BATTLE_PANEL_ICON_SIZE
        glow_s = settings.BATTLE_PANEL_ICON_GLOW_SIZE
        # The surface must be large enough for the glow (largest element)
        surf_size = max(glow_s, int(icon_s * settings.BATTLE_PANEL_ICON_FRAME_SCALE)) + 8
        surf = pygame.Surface((surf_size, surf_size), pygame.SRCALPHA)
        cx = surf_size // 2
        cy = surf_size // 2

        draw_battle_move_icon(
            surf, cx, cy,
            family_name, suit, power_value,
            self._panel_glow_cache, self._panel_icon_cache,
            self._panel_frame_cache, self._panel_suit_icon_cache,
            self.font_icon_value, icon_s, suit_b=suit_b,
        )
        return surf

    def _start_gamble(self, move_idx):
        """Show confirmation dialogue for gamble action."""
        if move_idx >= len(self.player_moves):
            return
        move = self.player_moves[move_idx]
        self._pending_gamble_move = move

        icon_surf = self._render_move_icon_surface(move)

        self.make_dialogue_box(
            f"Sacrifice your {move['family_name']} ({move['suit']})\n"
            "and draw 2 random battle moves from the stack?\n\n"
            "This cannot be undone!",
            actions=['gamble!', 'cancel'],
            images=[icon_surf],
            icon='dices',
            title="Gamble",
        )
        self._dialogue_callback = self._on_gamble_confirmed

    def _on_gamble_confirmed(self, response):
        """Handle the gamble confirmation dialogue response."""
        if response != 'gamble!':
            self._pending_gamble_move = None
            return

        if getattr(self.game, 'game_over', False):
            self._pending_gamble_move = None
            return

        move = self._pending_gamble_move
        self._pending_gamble_move = None
        if not move:
            return

        # Call server
        result = battle_shop_service.gamble_battle_move(
            self.game.game_id, self.game.player_id, move['id'],
        )

        if not result.get('success'):
            msg = result.get('message', 'Gamble failed.')
            self.make_dialogue_box(msg, actions=['ok'], icon='info', title="Gamble Failed")
            return

        # Mark gamble as used this round
        self._gambled_this_round = True

        # Update player moves: remove sacrificed, add new
        new_moves = result.get('new_moves', [])
        self.player_moves = [m for m in self.player_moves if m['id'] != move['id']]
        self.player_moves.extend(new_moves)

        # Build result dialogue cards (icon + name with suit icon)
        images = [self._render_gamble_result_card(nm) for nm in new_moves]

        self.make_dialogue_box(
            "You drew:",
            actions=['ok'],
            images=images,
            icon='dices',
            title="Gamble Result",
        )

    # ────────────────── combine logic ──────────────────────────

    def _start_combine(self, move_idx, selected_dagger):
        """Initiate the combine action for two daggers."""
        if move_idx >= len(self.player_moves) or not selected_dagger:
            return
        move = self.player_moves[move_idx]
        self._pending_combine_data = (move, selected_dagger)

        icon_a = self._render_move_icon_surface(move)
        icon_b = self._render_move_icon_surface(selected_dagger)

        self.make_dialogue_box(
            f"Combine these two daggers into a Double Dagger?\n\n"
            f"Combined power: {move.get('value', 0)} + {selected_dagger.get('value', 0)} = "
            f"{move.get('value', 0) + selected_dagger.get('value', 0)}",
            actions=['combine!', 'cancel'],
            images=[icon_a, icon_b],
            icon='dices',
            title="Combine",
        )
        self._dialogue_callback = self._on_combine_confirmed

    def _on_combine_confirmed(self, response):
        """Handle the combine confirmation dialogue response."""
        if response != 'combine!':
            self._pending_combine_data = None
            return

        if getattr(self.game, 'game_over', False):
            self._pending_combine_data = None
            return

        data = self._pending_combine_data
        self._pending_combine_data = None
        if not data:
            return
        move_a, move_b = data

        result = battle_shop_service.combine_battle_moves(
            self.game.game_id, self.game.player_id,
            move_a['id'], move_b['id'],
        )

        if not result.get('success'):
            msg = result.get('message', 'Combine failed.')
            self.make_dialogue_box(msg, actions=['ok'], icon='info', title="Combine Failed")
            return

        # Remove the two source daggers, add the combined Double Dagger
        removed_ids = set(result.get('removed_ids', []))
        self.player_moves = [m for m in self.player_moves if m['id'] not in removed_ids]
        combined_move = result.get('combined_move', {})
        self.player_moves.append(combined_move)

        # Show result
        icon_surf = self._render_move_icon_surface(combined_move)
        self.make_dialogue_box(
            "Double Dagger forged!",
            actions=['ok'],
            images=[icon_surf],
            icon='dices',
            title="Combine Result",
        )

    # ────────────────── dismantle logic ────────────────────────

    def _start_dismantle(self, move_idx):
        """Show confirmation dialogue for dismantling a Double Dagger."""
        if move_idx >= len(self.player_moves):
            return
        move = self.player_moves[move_idx]
        if move.get('family_name') != 'Double Dagger':
            return
        self._pending_dismantle_move = move

        icon_surf = self._render_move_icon_surface(move)

        va = move.get('value_a', 0)
        vb = move.get('value_b', 0)
        self.make_dialogue_box(
            f"Split this Double Dagger back into two separate Daggers?\n\n"
            f"You will get back a Dagger ({va}) and a Dagger ({vb}).",
            actions=['dismantle!', 'cancel'],
            images=[icon_surf],
            icon='dices',
            title="Dismantle",
        )
        self._dialogue_callback = self._on_dismantle_confirmed

    def _on_dismantle_confirmed(self, response):
        """Handle the dismantle confirmation dialogue response."""
        if response != 'dismantle!':
            self._pending_dismantle_move = None
            return

        if getattr(self.game, 'game_over', False):
            self._pending_dismantle_move = None
            return

        move = self._pending_dismantle_move
        self._pending_dismantle_move = None
        if not move:
            return

        result = battle_shop_service.dismantle_battle_move(
            self.game.game_id, self.game.player_id, move['id'],
        )

        if not result.get('success'):
            msg = result.get('message', 'Dismantle failed.')
            self.make_dialogue_box(msg, actions=['ok'], icon='info', title="Dismantle Failed")
            return

        # Remove Double Dagger, add back two Daggers
        self.player_moves = [m for m in self.player_moves if m['id'] != move['id']]
        restored = result.get('restored_moves', [])
        self.player_moves.extend(restored)

        images = [self._render_gamble_result_card(rm) for rm in restored]
        self.make_dialogue_box(
            "Double Dagger dismantled!",
            actions=['ok'],
            images=images,
            icon='dices',
            title="Dismantle Result",
        )

    # ────────────────────── drawing ─────────────────────────────

    def _battle_panel_rect(self):
        return pygame.Rect(
            self._sx(settings.BATTLE_PANEL_X),
            self._sy(settings.BATTLE_PANEL_Y),
            settings.BATTLE_PANEL_W,
            settings.BATTLE_PANEL_H,
        )

    def _figures_panel_rect(self):
        return pygame.Rect(
            self._sx(settings.FIGURES_PANEL_X),
            self._sy(settings.FIGURES_PANEL_Y),
            settings.FIGURES_PANEL_W,
            settings.FIGURES_PANEL_H,
        )

    def _rounds_panel_rect(self):
        return pygame.Rect(
            self._sx(settings.ROUNDS_PANEL_X),
            self._sy(settings.ROUNDS_PANEL_Y),
            settings.ROUNDS_PANEL_W,
            settings.ROUNDS_PANEL_H,
        )

    def _battle_panel_icon_center(self, slot):
        panel = self._battle_panel_rect()
        icon_y = settings.BATTLE_PANEL_ICON_START_Y + slot * settings.BATTLE_PANEL_ICON_DELTA_Y
        return panel.centerx, self._sy(icon_y)

    def draw(self):
        """Draw the entire battle screen."""
        super().draw()

        self._draw_battle_panel()
        # Clear round-panel figure icons before redrawing
        self._round_fig_icons = []
        self._round_fig_hovered_idx = None
        self._draw_figures_panel()
        self._draw_rounds_panel()
        # Update hover state for round-panel figure icons
        self._update_round_fig_hover()
        # Power circles drawn AFTER all panels/slots for correct z-order
        self._draw_all_power_circles()
        self._draw_total_circle()
        self._draw_turn_indicator()

        # Detail box on top of everything except dialogue box / msg
        if self.figure_detail_box:
            self.figure_detail_box.draw()
        elif self.battle_move_detail_box:
            self.battle_move_detail_box.draw()

        # Card picker overlay on top of everything
        self._draw_card_picker()

        super().draw_on_top()

    # ──────────── (1) Battle Moves Panel (left) ────────────────

    def _draw_battle_panel(self):
        """Draw the left panel with the player's 3 battle moves (hover-responsive + suit icons)."""
        panel_rect = self._battle_panel_rect()
        px, py = panel_rect.topleft
        pw, ph = panel_rect.size

        # Panel background
        panel_surf = pygame.Surface((pw, ph), pygame.SRCALPHA)
        panel_surf.fill((*settings.BATTLE_SCREEN_PANEL_BG_COLOR, settings.BATTLE_SCREEN_FILL_ALPHA))
        self.window.blit(panel_surf, (px, py))
        pygame.draw.rect(self.window, settings.BATTLE_SCREEN_PANEL_BORDER_COLOR,
                         (px, py, pw, ph), settings.BATTLE_SCREEN_PANEL_BORDER_WIDTH)

        # Panel title
        title = self.font_normal.render("Battle Moves", True, settings.ROUNDS_LABEL_COLOR)
        self.window.blit(title, title.get_rect(centerx=px + pw // 2, top=py + 6))

        panel_cx = px + pw // 2
        mx, my = pygame.mouse.get_pos()
        icon_s = settings.BATTLE_PANEL_ICON_SIZE

        self._panel_hovered_index = None

        # Only show moves that have NOT been played yet
        visible_moves = [(i, m) for i, m in enumerate(self.player_moves) if not self._is_move_used(i)]

        for slot, (i, move) in enumerate(visible_moves):
            _, icon_cy = self._battle_panel_icon_center(slot)

            family_name = move.get('family_name', '')
            suit = move.get('suit', '')

            # Hit-test for hover (slightly larger rect for easier targeting)
            hit_rect = pygame.Rect(
                panel_cx - icon_s // 2 - 4,
                icon_cy - icon_s // 2 - 4,
                icon_s + 8, icon_s + 8,
            )
            hovered = hit_rect.collidepoint(mx, my) and not self.battle_move_detail_box
            if hovered:
                self._panel_hovered_index = i

            power_value = self._get_panel_display_power(move)
            suit_b = move.get('suit_b') if family_name == 'Double Dagger' else None
            draw_battle_move_icon(
                self.window, panel_cx, icon_cy,
                family_name, suit, power_value,
                self._panel_glow_cache, self._panel_icon_cache,
                self._panel_frame_cache, self._panel_suit_icon_cache,
                self.font_icon_value, icon_s,
                hovered=hovered, is_used=False, suit_b=suit_b,
            )

        # Set cursor to pointer when hovering a clickable icon
        if self._panel_hovered_index is not None:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_HAND)
        elif not self.battle_move_detail_box:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_ARROW)



    # ──────────── (2) Figures Panel (centre-left) ──────────────

    def _draw_panel_sub_box(self, x, y, w, h):
        """Draw a brown sub-box with alpha background and border."""
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        surf.fill((*settings.BATTLE_SCREEN_PANEL_BG_COLOR, settings.BATTLE_SCREEN_FILL_ALPHA))
        self.window.blit(surf, (x, y))
        pygame.draw.rect(self.window, settings.BATTLE_SCREEN_PANEL_BORDER_COLOR,
                         (x, y, w, h), settings.BATTLE_SCREEN_PANEL_BORDER_WIDTH)

    def _draw_figures_panel(self):
        """Draw the two battling figures and their power difference."""
        panel_rect = self._figures_panel_rect()
        px, py = panel_rect.topleft
        pw, ph = panel_rect.size
        gap = int(0.005 * settings.SCREEN_HEIGHT)

        # ─── Centre the diff area in the panel for perfect symmetry ───
        diff_margin_top = int(0.03 * settings.SCREEN_HEIGHT)
        diff_margin_bot = int(0.01 * settings.SCREEN_HEIGHT)
        diff_h_total = diff_margin_top + settings.FIGURES_DIFF_H + diff_margin_bot
        panel_mid = py + ph // 2
        diff_area_top = panel_mid - diff_h_total // 2
        diff_area_bot = panel_mid + diff_h_total // 2
        actual_diff_y = diff_area_top + diff_margin_top

        # Player sub-box (top) — same height as opponent sub-box
        player_box_h = diff_area_top - gap - py
        self._draw_panel_sub_box(px, py, pw, player_box_h)
        # Diff sub-box (middle)
        self._draw_panel_sub_box(px, diff_area_top, pw, diff_area_bot - diff_area_top)
        # Opponent sub-box (bottom)
        opp_y = diff_area_bot + gap
        opp_box_h = (py + ph) - opp_y
        self._draw_panel_sub_box(px, opp_y, pw, opp_box_h)

        panel_cx = px + pw // 2

        # ─── Rotated labels on left outside border ───
        label_color = (90, 70, 50)  # darker color for brighter background
        label_you = self.font_normal.render("YOU", True, label_color)
        label_you_rot = pygame.transform.rotate(label_you, 90)
        label_you_rect = label_you_rot.get_rect(
            right=px - 2,
            centery=py + player_box_h // 2,
        )
        self.window.blit(label_you_rot, label_you_rect)

        # ─── Player figure (top) — centred in player sub-box ───
        # Estimate the total visual extent below the figure centre:
        # frame half-height + info box (name + power/suit row)
        frame_half = settings.FIELD_ICON_WIDTH * 0.45 * settings.FRAME_FIGURE_SCALE / 2
        info_box_est = int(0.04 * settings.SCREEN_HEIGHT)  # name row + info row
        fig_visual_below = frame_half + info_box_est

        # Collect player support figures (blocker / distance attacker / buffer)
        player_support = []
        player_blockers = getattr(self, 'player_blocks_bonus_figures', None)
        if player_blockers:
            for blocker in player_blockers:
                player_support.append(('blocks_bonus', blocker))
        elif self.player_blocks_bonus_figure:
            player_support.append(('blocks_bonus', self.player_blocks_bonus_figure))
        for archer in self._player_da_archers:
            if archer['hit_battle']:
                player_support.append(('distance_attack', archer['fig']))
        # Add buffs_allies figures that buff the player's battle figure
        for buff_fig in self.player_buffs_allies_figures:
            for bf in (self.player_figure, self.player_figure_2):
                if (bf and hasattr(bf.family, 'field') and
                        bf.family.field == 'village' and bf.suit == buff_fig.suit):
                    player_support.append(('buffs_allies', buff_fig))
                    break
        # Add buffs_allies_defence figures (active when player is defending)
        for buff_fig in self.player_buffs_allies_defence_figures:
            player_support.append(('buffs_allies_defence', buff_fig))

        if self.player_figure_icon:
            if player_support:
                # With support figures: shift battle figure down so they fit at top
                circle_space = settings.POWER_CIRCLE_RADIUS * 2 + int(0.01 * settings.SCREEN_HEIGHT)
                fig_cy = (py + player_box_h) - int(fig_visual_below) - circle_space + int(0.02 * settings.SCREEN_HEIGHT)
                support_y = py + int(player_box_h * 0.12)
            else:
                fig_cy = py + int(player_box_h * 0.42)
            if self.player_figure_icon_2:
                offset = int(0.03 * settings.SCREEN_WIDTH)
                self.player_figure_icon.draw(panel_cx - offset, fig_cy)
                self.player_figure_icon_2.draw(panel_cx + offset, fig_cy)
            else:
                self.player_figure_icon.draw(panel_cx, fig_cy)

            # Draw player support figures at top of sub-box
            if player_support:
                self._draw_support_figures(player_support, panel_cx, support_y, pw, is_player=True)

        # ─── Power difference box (middle) ───
        diff = self._get_figure_diff()
        self._draw_diff_box(
            panel_cx, actual_diff_y,
            settings.FIGURES_DIFF_W, settings.FIGURES_DIFF_H,
            diff, label="Figure Clash (start)",
        )

        # ─── Opponent figure (bottom) — centred in opponent sub-box ───
        # Collect opponent support figures (blocker / distance attacker / buffer)
        opp_support = []
        opponent_blockers = getattr(self, 'opponent_blocks_bonus_figures', None)
        if opponent_blockers:
            for blocker in opponent_blockers:
                opp_support.append(('blocks_bonus', blocker))
        elif self.opponent_blocks_bonus_figure:
            opp_support.append(('blocks_bonus', self.opponent_blocks_bonus_figure))
        for archer in self._opponent_da_archers:
            if archer['hit_battle']:
                opp_support.append(('distance_attack', archer['fig']))
        # Add buffs_allies figures that buff the opponent's battle figure
        for buff_fig in self.opponent_buffs_allies_figures:
            for bf in (self.opponent_figure, self.opponent_figure_2):
                if (bf and hasattr(bf.family, 'field') and
                        bf.family.field == 'village' and bf.suit == buff_fig.suit):
                    opp_support.append(('buffs_allies', buff_fig))
                    break
        # Add buffs_allies_defence figures (active when opponent is defending)
        for buff_fig in self.opponent_buffs_allies_defence_figures:
            opp_support.append(('buffs_allies_defence', buff_fig))

        if self.opponent_figure_icon:
            if opp_support:
                # With support figures: shift figure up so they fit at bottom
                circle_space = settings.POWER_CIRCLE_RADIUS * 2 + int(0.01 * settings.SCREEN_HEIGHT)
                fig_cy = opp_y + circle_space + int(frame_half)
                support_y = (opp_y + opp_box_h) - int(player_box_h * 0.12)
            else:
                fig_cy = opp_y + opp_box_h // 2
            if self.opponent_figure_icon_2:
                offset = int(0.03 * settings.SCREEN_WIDTH)
                self.opponent_figure_icon.draw(panel_cx - offset, fig_cy)
                self.opponent_figure_icon_2.draw(panel_cx + offset, fig_cy)
            else:
                self.opponent_figure_icon.draw(panel_cx, fig_cy)

            # Draw opponent support figures at bottom of sub-box
            if opp_support:
                self._draw_support_figures(opp_support, panel_cx, support_y, pw, is_player=False)

        label_opp = self.font_normal.render("OPPONENT", True, label_color)
        label_opp_rot = pygame.transform.rotate(label_opp, 90)
        label_opp_rect = label_opp_rot.get_rect(
            right=px - 2,
            centery=opp_y + opp_box_h // 2,
        )
        self.window.blit(label_opp_rot, label_opp_rect)

        # Cursor hand on figure hover (main figures + round-panel sub-icons)
        fig_hovered = False
        for fig_icon in (self.player_figure_icon, self.opponent_figure_icon,
                         self.player_figure_icon_2, self.opponent_figure_icon_2):
            if fig_icon and fig_icon.hovered:
                fig_hovered = True
                break
        if not fig_hovered and self._round_fig_hovered_idx is not None:
            fig_hovered = True
        if fig_hovered and not self.battle_move_detail_box and not self.figure_detail_box:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_HAND)

    def _draw_support_figures(self, support_list, panel_cx, support_y, pw, is_player):
        """Draw N support figure icons, evenly spaced in the panel."""
        if not support_list:
            return
        n = len(support_list)
        if n == 1:
            positions = [panel_cx]
        else:
            max_spread = int(pw * 0.20)
            step = min(max_spread * 2 // (n - 1), int(pw * 0.40) // max(n - 1, 1))
            total = step * (n - 1)
            positions = [panel_cx - total // 2 + i * step for i in range(n)]
        for pos_x, (skill_key, fig) in zip(positions, support_list):
            if skill_key == 'blocks_bonus':
                self._draw_blocker_icon(pos_x, support_y, fig, is_player=is_player)
            elif skill_key == 'distance_attack':
                self._draw_distance_attack_icon(pos_x, support_y, fig, is_player=is_player)
            elif skill_key == 'buffs_allies':
                self._draw_buffs_allies_icon(pos_x, support_y, fig, is_player=is_player)
            elif skill_key == 'buffs_allies_defence':
                self._draw_buffs_allies_defence_icon(pos_x, support_y, fig, is_player=is_player)

    def _draw_blocker_icon(self, cx, cy, blocker_fig, is_player=True):
        """Draw a small figure icon for a blocks_bonus support figure.

        Similar style to _draw_slot_figure_icons but placed in the figures
        panel.  Shows the blocker's frame+icon with a small 'Blocks Bonus'
        label and the skill icon.
        """
        sw = settings.ROUNDS_SLOT_SIZE
        fig_s = int(sw * 0.45)
        frame_s = int(fig_s * 1.3)
        mx, my = pygame.mouse.get_pos()
        any_modal = self.battle_move_detail_box or self.figure_detail_box

        hit_rect = pygame.Rect(cx - frame_s // 2, cy - frame_s // 2, frame_s, frame_s)
        is_hovered = hit_rect.collidepoint(mx, my) and not any_modal

        # Register for click → open FigureDetailBox
        self._round_fig_icons.append({
            'figure': blocker_fig, 'rect': hit_rect,
            'is_player': is_player, 'round': -1,
            'source': 'blocks_bonus', 'hovered': is_hovered,
        })

        # Enlarge on hover
        r_fig_s = int(fig_s * 1.2) if is_hovered else fig_s
        r_frame_s = int(frame_s * 1.2) if is_hovered else frame_s

        # Scale frame + icon
        frame_raw = getattr(blocker_fig.family, 'frame_img', None)
        icon_raw = getattr(blocker_fig.family, 'icon_img', None)
        if not icon_raw:
            return

        icon_scaled = pygame.transform.smoothscale(icon_raw, (r_fig_s, r_fig_s))
        if is_hovered:
            bright = pygame.Surface(icon_scaled.get_size(), pygame.SRCALPHA)
            bright.fill((40, 40, 40, 0))
            icon_scaled.blit(bright, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

        self.window.blit(icon_scaled, icon_scaled.get_rect(center=(cx, cy)))
        if frame_raw:
            frame_scaled = pygame.transform.smoothscale(frame_raw, (r_frame_s, r_frame_s))
            self.window.blit(frame_scaled, frame_scaled.get_rect(center=(cx, cy)))

        # Small info label to the RIGHT of the icon, vertically centered:
        # combined skill+suit icon + "Blocks Bonus" text
        from game.components.figures.family_configs.skill_config import SKILL_DEFINITIONS, get_advantage_suit
        skill_icon_path = SKILL_DEFINITIONS.get('blocks_bonus', {}).get('icon', '')
        info_color = (100, 230, 100) if is_player else (255, 100, 100)
        label_txt = self.font_small.render("Blocks Bonus", True, info_color)
        label_h = label_txt.get_height() + 4

        # Build a combined skill icon with suit icon behind it (same overlay pattern as info row)
        combined_ico = None
        adv_suit = get_advantage_suit(blocker_fig.suit)
        cache_key = f'_blocker_combined_icon_{label_h}_{adv_suit}'
        if not hasattr(self, cache_key):
            try:
                # Load skill icon
                raw_skill = pygame.image.load(skill_icon_path).convert_alpha()
                skill_scaled = pygame.transform.smoothscale(raw_skill, (label_h, label_h))
                # Load suit icon and draw behind skill icon at 85% size
                combined = pygame.Surface((label_h, label_h), pygame.SRCALPHA)
                if adv_suit:
                    suit_path = settings.SUIT_ICON_IMG_PATH + adv_suit.lower() + '.png'
                    raw_suit = pygame.image.load(suit_path).convert_alpha()
                    suit_s = int(label_h * 0.85)
                    suit_scaled = pygame.transform.smoothscale(raw_suit, (suit_s, suit_s))
                    combined.blit(suit_scaled, ((label_h - suit_s) // 2, (label_h - suit_s) // 2))
                combined.blit(skill_scaled, (0, 0))
                setattr(self, cache_key, combined)
            except Exception:
                setattr(self, cache_key, None)
        combined_ico = getattr(self, cache_key)

        ico_w = (combined_ico.get_width() + 3) if combined_ico else 0
        total_label_w = ico_w + label_txt.get_width() + 8
        info_h = label_h + 2

        # Position: overlaid on the support figure icon, at the bottom of the icon
        info_x = cx - total_label_w // 2
        info_y = cy + r_frame_s // 2 - info_h

        info_bg = pygame.Surface((total_label_w, info_h), pygame.SRCALPHA)
        info_bg.fill((40, 25, 10, 180))
        self.window.blit(info_bg, (info_x, info_y))

        draw_x = info_x + 4
        if combined_ico:
            self.window.blit(combined_ico, (draw_x, info_y + (info_h - combined_ico.get_height()) // 2))
            draw_x += combined_ico.get_width() + 3
        self.window.blit(label_txt, (draw_x, info_y + (info_h - label_txt.get_height()) // 2))

    def _draw_distance_attack_icon(self, cx, cy, attacker_fig, is_player=True):
        """Draw a small figure icon for a distance_attack support figure.

        Same visual style as _draw_blocker_icon but with 'Distance -N' label
        (N = figure's number card value) and the distance_attack skill icon.
        """
        sw = settings.ROUNDS_SLOT_SIZE
        fig_s = int(sw * 0.45)
        frame_s = int(fig_s * 1.3)
        mx, my = pygame.mouse.get_pos()
        any_modal = self.battle_move_detail_box or self.figure_detail_box

        hit_rect = pygame.Rect(cx - frame_s // 2, cy - frame_s // 2, frame_s, frame_s)
        is_hovered = hit_rect.collidepoint(mx, my) and not any_modal

        # Register for click → open FigureDetailBox
        self._round_fig_icons.append({
            'figure': attacker_fig, 'rect': hit_rect,
            'is_player': is_player, 'round': -1,
            'source': 'distance_attack', 'hovered': is_hovered,
        })

        # Enlarge on hover
        r_fig_s = int(fig_s * 1.2) if is_hovered else fig_s
        r_frame_s = int(frame_s * 1.2) if is_hovered else frame_s

        # Scale frame + icon
        frame_raw = getattr(attacker_fig.family, 'frame_img', None)
        icon_raw = getattr(attacker_fig.family, 'icon_img', None)
        if not icon_raw:
            return

        icon_scaled = pygame.transform.smoothscale(icon_raw, (r_fig_s, r_fig_s))
        if is_hovered:
            bright = pygame.Surface(icon_scaled.get_size(), pygame.SRCALPHA)
            bright.fill((40, 40, 40, 0))
            icon_scaled.blit(bright, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

        self.window.blit(icon_scaled, icon_scaled.get_rect(center=(cx, cy)))
        if frame_raw:
            frame_scaled = pygame.transform.smoothscale(frame_raw, (r_frame_s, r_frame_s))
            self.window.blit(frame_scaled, frame_scaled.get_rect(center=(cx, cy)))

        # Info label: combined skill+suit icon + "Distance -N"
        from game.components.figures.family_configs.skill_config import SKILL_DEFINITIONS, get_advantage_suit
        skill_icon_path = SKILL_DEFINITIONS.get('distance_attack', {}).get('icon', '')
        info_color = (100, 230, 100) if is_player else (255, 100, 100)
        penalty_val = attacker_fig.number_card.value if attacker_fig.number_card else 0
        label_txt = self.font_small.render(f"Distance -{penalty_val}", True, info_color)
        label_h = label_txt.get_height() + 4

        # Build combined skill icon with suit icon behind it
        combined_ico = None
        adv_suit = get_advantage_suit(attacker_fig.suit)
        cache_key = f'_distance_combined_icon_{label_h}_{adv_suit}'
        if not hasattr(self, cache_key):
            try:
                raw_skill = pygame.image.load(skill_icon_path).convert_alpha()
                skill_scaled = pygame.transform.smoothscale(raw_skill, (label_h, label_h))
                combined = pygame.Surface((label_h, label_h), pygame.SRCALPHA)
                if adv_suit:
                    suit_path = settings.SUIT_ICON_IMG_PATH + adv_suit.lower() + '.png'
                    raw_suit = pygame.image.load(suit_path).convert_alpha()
                    suit_s = int(label_h * 0.85)
                    suit_scaled = pygame.transform.smoothscale(raw_suit, (suit_s, suit_s))
                    combined.blit(suit_scaled, ((label_h - suit_s) // 2, (label_h - suit_s) // 2))
                combined.blit(skill_scaled, (0, 0))
                setattr(self, cache_key, combined)
            except Exception:
                setattr(self, cache_key, None)
        combined_ico = getattr(self, cache_key)

        ico_w = (combined_ico.get_width() + 3) if combined_ico else 0
        total_label_w = ico_w + label_txt.get_width() + 8
        info_h = label_h + 2

        # Position: overlaid on the support figure icon, at the bottom
        info_x = cx - total_label_w // 2
        info_y = cy + r_frame_s // 2 - info_h

        info_bg = pygame.Surface((total_label_w, info_h), pygame.SRCALPHA)
        info_bg.fill((40, 25, 10, 180))
        self.window.blit(info_bg, (info_x, info_y))

        draw_x = info_x + 4
        if combined_ico:
            self.window.blit(combined_ico, (draw_x, info_y + (info_h - combined_ico.get_height()) // 2))
            draw_x += combined_ico.get_width() + 3
        self.window.blit(label_txt, (draw_x, info_y + (info_h - label_txt.get_height()) // 2))

    def _draw_buffs_allies_icon(self, cx, cy, buff_fig, is_player=True):
        """Draw a small figure icon for a buffs_allies support figure.

        Same visual style as _draw_blocker_icon but with 'Buffs +4' label
        and the buffs_allies skill icon.
        """
        sw = settings.ROUNDS_SLOT_SIZE
        fig_s = int(sw * 0.45)
        frame_s = int(fig_s * 1.3)
        mx, my = pygame.mouse.get_pos()
        any_modal = self.battle_move_detail_box or self.figure_detail_box

        hit_rect = pygame.Rect(cx - frame_s // 2, cy - frame_s // 2, frame_s, frame_s)
        is_hovered = hit_rect.collidepoint(mx, my) and not any_modal

        self._round_fig_icons.append({
            'figure': buff_fig, 'rect': hit_rect,
            'is_player': is_player, 'round': -1,
            'source': 'buffs_allies', 'hovered': is_hovered,
        })

        r_fig_s = int(fig_s * 1.2) if is_hovered else fig_s
        r_frame_s = int(frame_s * 1.2) if is_hovered else frame_s

        frame_raw = getattr(buff_fig.family, 'frame_img', None)
        icon_raw = getattr(buff_fig.family, 'icon_img', None)
        if not icon_raw:
            return

        icon_scaled = pygame.transform.smoothscale(icon_raw, (r_fig_s, r_fig_s))
        if is_hovered:
            bright = pygame.Surface(icon_scaled.get_size(), pygame.SRCALPHA)
            bright.fill((40, 40, 40, 0))
            icon_scaled.blit(bright, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

        self.window.blit(icon_scaled, icon_scaled.get_rect(center=(cx, cy)))
        if frame_raw:
            frame_scaled = pygame.transform.smoothscale(frame_raw, (r_frame_s, r_frame_s))
            self.window.blit(frame_scaled, frame_scaled.get_rect(center=(cx, cy)))

        # Info label: skill icon (with suit behind if suit_self) + "Buffs +4"
        from game.components.figures.family_configs.skill_config import SKILL_DEFINITIONS
        skill_icon_path = SKILL_DEFINITIONS.get('buffs_allies', {}).get('icon', '')
        suit_self = SKILL_DEFINITIONS.get('buffs_allies', {}).get('suit_self', False)
        info_color = (100, 230, 100) if is_player else (255, 100, 100)
        label_txt = self.font_small.render("Buffs +4", True, info_color)
        label_h = label_txt.get_height() + 4

        # Build skill icon + suit icon side by side if suit_self, else skill only
        if suit_self:
            own_suit = getattr(buff_fig, 'suit', '') or ''
            cache_key = f'_buffs_allies_icon_{label_h}_{own_suit.lower()}'
            if not hasattr(self, cache_key):
                try:
                    raw_skill = pygame.image.load(skill_icon_path).convert_alpha()
                    skill_scaled = pygame.transform.smoothscale(raw_skill, (label_h, label_h))
                    if own_suit:
                        suit_path = settings.SUIT_ICON_IMG_PATH + own_suit.lower() + '.png'
                        raw_suit = pygame.image.load(suit_path).convert_alpha()
                        suit_s = int(label_h * 0.85)
                        suit_scaled = pygame.transform.smoothscale(raw_suit, (suit_s, suit_s))
                        gap = 2
                        combined_w = label_h + gap + suit_s
                        combined = pygame.Surface((combined_w, label_h), pygame.SRCALPHA)
                        combined.blit(skill_scaled, (0, 0))
                        combined.blit(suit_scaled, (label_h + gap, (label_h - suit_s) // 2))
                    else:
                        combined = skill_scaled
                    setattr(self, cache_key, combined)
                except Exception:
                    setattr(self, cache_key, None)
            skill_ico = getattr(self, cache_key)
        else:
            cache_key = f'_buffs_allies_icon_{label_h}'
            if not hasattr(self, cache_key):
                try:
                    raw_skill = pygame.image.load(skill_icon_path).convert_alpha()
                    skill_scaled = pygame.transform.smoothscale(raw_skill, (label_h, label_h))
                    setattr(self, cache_key, skill_scaled)
                except Exception:
                    setattr(self, cache_key, None)
            skill_ico = getattr(self, cache_key)

        ico_w = (skill_ico.get_width() + 3) if skill_ico else 0
        total_label_w = ico_w + label_txt.get_width() + 8
        info_h = label_h + 2

        info_x = cx - total_label_w // 2
        info_y = cy + r_frame_s // 2 - info_h

        info_bg = pygame.Surface((total_label_w, info_h), pygame.SRCALPHA)
        info_bg.fill((40, 25, 10, 180))
        self.window.blit(info_bg, (info_x, info_y))

        draw_x = info_x + 4
        if skill_ico:
            self.window.blit(skill_ico, (draw_x, info_y + (info_h - skill_ico.get_height()) // 2))
            draw_x += skill_ico.get_width() + 3
        self.window.blit(label_txt, (draw_x, info_y + (info_h - label_txt.get_height()) // 2))

    def _draw_buffs_allies_defence_icon(self, cx, cy, buff_fig, is_player=True):
        """Draw a small figure icon for a buffs_allies_defence support figure.

        Same visual style as _draw_buffs_allies_icon but with 'Defence +N'
        label and the buffs_allies_defence skill icon.
        """
        sw = settings.ROUNDS_SLOT_SIZE
        fig_s = int(sw * 0.45)
        frame_s = int(fig_s * 1.3)
        mx, my = pygame.mouse.get_pos()
        any_modal = self.battle_move_detail_box or self.figure_detail_box

        hit_rect = pygame.Rect(cx - frame_s // 2, cy - frame_s // 2, frame_s, frame_s)
        is_hovered = hit_rect.collidepoint(mx, my) and not any_modal

        self._round_fig_icons.append({
            'figure': buff_fig, 'rect': hit_rect,
            'is_player': is_player, 'round': -1,
            'source': 'buffs_allies_defence', 'hovered': is_hovered,
        })

        r_fig_s = int(fig_s * 1.2) if is_hovered else fig_s
        r_frame_s = int(frame_s * 1.2) if is_hovered else frame_s

        frame_raw = getattr(buff_fig.family, 'frame_img', None)
        icon_raw = getattr(buff_fig.family, 'icon_img', None)
        if not icon_raw:
            return

        icon_scaled = pygame.transform.smoothscale(icon_raw, (r_fig_s, r_fig_s))
        if is_hovered:
            bright = pygame.Surface(icon_scaled.get_size(), pygame.SRCALPHA)
            bright.fill((40, 40, 40, 0))
            icon_scaled.blit(bright, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

        self.window.blit(icon_scaled, icon_scaled.get_rect(center=(cx, cy)))
        if frame_raw:
            frame_scaled = pygame.transform.smoothscale(frame_raw, (r_frame_s, r_frame_s))
            self.window.blit(frame_scaled, frame_scaled.get_rect(center=(cx, cy)))

        # Info label: skill icon + "Defence +N"
        from game.components.figures.family_configs.skill_config import SKILL_DEFINITIONS
        skill_icon_path = SKILL_DEFINITIONS.get('buffs_allies_defence', {}).get('icon', '')
        bonus_val = buff_fig.number_card.value if getattr(buff_fig, 'number_card', None) else 0
        info_color = (100, 230, 100) if is_player else (255, 100, 100)
        label_txt = self.font_small.render(f"Defence +{bonus_val}", True, info_color)
        label_h = label_txt.get_height() + 4

        cache_key = f'_buffs_allies_defence_icon_{label_h}'
        if not hasattr(self, cache_key):
            try:
                raw_skill = pygame.image.load(skill_icon_path).convert_alpha()
                skill_scaled = pygame.transform.smoothscale(raw_skill, (label_h, label_h))
                setattr(self, cache_key, skill_scaled)
            except Exception:
                setattr(self, cache_key, None)
        skill_ico = getattr(self, cache_key)

        ico_w = (skill_ico.get_width() + 3) if skill_ico else 0
        total_label_w = ico_w + label_txt.get_width() + 8
        info_h = label_h + 2

        info_x = cx - total_label_w // 2
        info_y = cy + r_frame_s // 2 - info_h

        info_bg = pygame.Surface((total_label_w, info_h), pygame.SRCALPHA)
        info_bg.fill((40, 25, 10, 180))
        self.window.blit(info_bg, (info_x, info_y))

        draw_x = info_x + 4
        if skill_ico:
            self.window.blit(skill_ico, (draw_x, info_y + (info_h - skill_ico.get_height()) // 2))
            draw_x += skill_ico.get_width() + 3
        self.window.blit(label_txt, (draw_x, info_y + (info_h - label_txt.get_height()) // 2))

    # ──────────── (3) Rounds Panel (centre) ────────────────────

    def _draw_rounds_panel(self):
        """Draw the 3 round columns with slots and labels."""
        panel_rect = self._rounds_panel_rect()
        px, py = panel_rect.topleft
        pw, ph = panel_rect.size
        gap = int(0.005 * settings.SCREEN_HEIGHT)

        # Use the same centred diff area as the figures panel for alignment
        diff_margin_top = int(0.03 * settings.SCREEN_HEIGHT)
        diff_margin_bot = int(0.01 * settings.SCREEN_HEIGHT)
        diff_h_total = diff_margin_top + settings.FIGURES_DIFF_H + diff_margin_bot
        panel_mid = py + ph // 2
        diff_area_top = panel_mid - diff_h_total // 2
        diff_area_bot = panel_mid + diff_h_total // 2
        actual_diff_y = diff_area_top + diff_margin_top

        # Player sub-box (top) — includes round labels + player slots
        self._draw_panel_sub_box(px, py, pw, diff_area_top - gap - py)
        # Diff sub-box (middle)
        self._draw_panel_sub_box(px, diff_area_top, pw, diff_area_bot - diff_area_top)
        # Opponent sub-box (bottom)
        opp_y = diff_area_bot + gap
        self._draw_panel_sub_box(px, opp_y, pw, py + ph - opp_y)

        panel_cx = px + pw // 2
        # Centre the 3 columns in the panel
        total_span = 2 * settings.ROUNDS_COL_DELTA_X
        col_start_x = panel_cx - total_span // 2

        for r in range(3):
            col_cx = col_start_x + r * settings.ROUNDS_COL_DELTA_X
            is_current = (r == self.current_round)

            # ─── Player slot (top) ───
            self._draw_round_slot(
                col_cx, self._sy(settings.ROUNDS_PLAYER_SLOT_Y),
                self.player_played[r], is_current and self.is_player_turn,
                is_player=True, r_index=r,
            )

            # ─── Round difference box (middle, with round label) ───
            rd = self._get_round_diff(r)
            lbl_color = settings.ROUNDS_LABEL_ACTIVE_COLOR if is_current else settings.ROUNDS_LABEL_COLOR
            self._draw_diff_box(
                col_cx, actual_diff_y,
                settings.ROUNDS_DIFF_W, settings.ROUNDS_DIFF_H,
                rd, label=f"Round {r + 1}", label_color=lbl_color,
            )

            # ─── Opponent slot (bottom) ───
            self._draw_round_slot(
                col_cx, self._sy(settings.ROUNDS_OPPONENT_SLOT_Y),
                self.opponent_played[r], is_current and not self.is_player_turn,
                is_player=False, r_index=r,
            )

    def _draw_all_power_circles(self):
        """Draw every power circle AFTER all panels so they sit on top."""
        # --- Figures panel circles ---
        # Compute diff area boundaries (same logic as _draw_figures_panel)
        panel_rect = self._figures_panel_rect()
        py = panel_rect.y
        ph = panel_rect.h
        gap = int(0.005 * settings.SCREEN_HEIGHT)
        diff_margin_top = int(0.03 * settings.SCREEN_HEIGHT)
        diff_margin_bot = int(0.01 * settings.SCREEN_HEIGHT)
        diff_h_total = diff_margin_top + settings.FIGURES_DIFF_H + diff_margin_bot
        panel_mid = py + ph // 2
        diff_area_top = panel_mid - diff_h_total // 2
        diff_area_bot = panel_mid + diff_h_total // 2
        r = settings.POWER_CIRCLE_RADIUS

        # Place circles inside their corresponding sub-boxes (near the diff area edge)
        player_box_bottom = diff_area_top - gap
        opp_box_top = diff_area_bot + gap
        player_circle_y = player_box_bottom - r - int(0.005 * settings.SCREEN_HEIGHT)
        opp_circle_y = opp_box_top + r + int(0.005 * settings.SCREEN_HEIGHT)

        fig_cx = panel_rect.centerx
        player_power = self._get_figure_total_power(self.player_figure, self.player_figure_icon)
        player_power += self._get_figure_total_power(self.player_figure_2, self.player_figure_icon_2)
        self._draw_power_circle(fig_cx, player_circle_y, player_power)

        opp_power = self._get_figure_total_power(self.opponent_figure, self.opponent_figure_icon)
        opp_power += self._get_figure_total_power(self.opponent_figure_2, self.opponent_figure_icon_2)
        self._draw_power_circle(fig_cx, opp_circle_y, opp_power)

        # --- Rounds panel circles (3 columns) ---
        rounds_rect = self._rounds_panel_rect()
        panel_cx = rounds_rect.centerx
        total_span = 2 * settings.ROUNDS_COL_DELTA_X
        col_start_x = panel_cx - total_span // 2

        for r in range(3):
            col_cx = col_start_x + r * settings.ROUNDS_COL_DELTA_X

            p_move = self.player_played[r]
            o_move = self.opponent_played[r]

            # Determine displayed values using effective power (includes Call figure)
            p_val = None
            p_crossed = False
            if p_move:
                p_val = self._get_move_effective_power(p_move, is_player=True, round_idx=r)
                # If opponent played Block, player's value is crossed out
                if o_move and o_move.get('family_name') == 'Block':
                    p_crossed = True

            o_val = None
            o_crossed = False
            if o_move:
                o_val = self._get_move_effective_power(o_move, is_player=False, round_idx=r)
                # If player played Block, opponent's value is crossed out
                if p_move and p_move.get('family_name') == 'Block':
                    o_crossed = True

            # Player circle
            self._draw_power_circle(col_cx, self._sy(settings.POWER_CIRCLE_PLAYER_Y), p_val,
                                    crossed_out=p_crossed)
            # Opponent circle
            self._draw_power_circle(col_cx, self._sy(settings.POWER_CIRCLE_OPPONENT_Y), o_val,
                                    crossed_out=o_crossed)

    def _draw_round_slot(self, cx, cy, played_move, is_active_slot, is_player=True, r_index=0):
        """Draw a single battle move slot (diamond shape).

        :param cx: centre x
        :param cy: centre y (top of slot area; actual centre is cy + slot_size//2)
        :param played_move: server dict of the played move, or None
        :param is_active_slot: True if this is the next slot to be filled
        :param is_player: True for player row, False for opponent
        :param r_index: round index (0-2) for figure icon tracking
        """
        sw = settings.ROUNDS_SLOT_SIZE
        slot_cy = cy + sw // 2

        if played_move:
            # Skipped round — draw empty diamond slot (no battle move icon)
            if played_move.get('_skipped'):
                dr = self._slot_diamond.get_rect(center=(cx, slot_cy))
                self.window.blit(self._slot_diamond, dr.topleft)
                # Show a subtle "—" to indicate skip
                dash = self.font_small.render("—", True, (120, 100, 80))
                self.window.blit(dash, dash.get_rect(center=(cx, slot_cy)))
                return

            family_name = played_move.get('family_name', '')
            suit = played_move.get('suit', '')
            power_value = 0 if family_name == 'Block' else played_move.get('value', '')
            suit_b = played_move.get('suit_b') if family_name == 'Double Dagger' else None
            # For Double Dagger slots, show "X+Y" format
            if family_name == 'Double Dagger':
                va = played_move.get('value_a', 0)
                vb = played_move.get('value_b', 0)
                if va or vb:
                    power_value = f"{va}+{vb}"

            # ─── Collect figure icons for this slot ───
            # Each entry: (figure, source_tag).  Currently only 'call'; later
            # skill-triggered figures will be appended here.
            slot_figures = []
            call_fig = played_move.get('_call_figure')
            if call_fig and hasattr(call_fig, 'family') and hasattr(call_fig.family, 'icon_img'):
                slot_figures.append((call_fig, 'call'))

            # Add distance-attack figure on the OWNER's rounds panel
            if is_player:
                # Player's DA fires on opponent's call figs — show here
                da_penalty = self._get_da_call_penalty(for_player_da=True, round_idx=r_index)
                da_fig = self.player_distance_attack_figure
            else:
                # Opponent's DA fires on player's call figs — show here
                da_penalty = self._get_da_call_penalty(for_player_da=False, round_idx=r_index)
                da_fig = self.opponent_distance_attack_figure
            if da_fig and da_penalty > 0 and hasattr(da_fig, 'family') and hasattr(da_fig.family, 'icon_img'):
                slot_figures.append((da_fig, 'distance_attack'))

            # Add buffs_allies figures on the OWNER's rounds panel
            if call_fig and hasattr(call_fig, 'family') and hasattr(call_fig.family, 'field'):
                if call_fig.family.field == 'village':
                    buffs_list = (self.player_buffs_allies_figures if is_player
                                  else self.opponent_buffs_allies_figures)
                    for buff_fig in buffs_list:
                        if (buff_fig.suit == call_fig.suit and
                                hasattr(buff_fig, 'family') and
                                hasattr(buff_fig.family, 'icon_img')):
                            slot_figures.append((buff_fig, 'buffs_allies'))

            # Draw all figure sub-icons for this slot (supports multiple)
            if slot_figures:
                self._draw_slot_figure_icons(
                    cx, slot_cy, sw, slot_figures, is_player, r_index)

            draw_battle_move_icon(
                self.window, cx, slot_cy,
                family_name, suit, power_value,
                self._slot_glow_cache, self._slot_icon_cache,
                self._slot_frame_cache, self._slot_suit_icon_cache,
                self.font_icon_value, sw, suit_b=suit_b,
            )

            # Red strikethrough on BM value number when called-figure suit ≠ BM suit
            if call_fig and hasattr(call_fig, 'suit'):
                bm_suit_lower = (suit or '').lower()
                cf_suit_lower = (call_fig.suit or '').lower()
                if cf_suit_lower != bm_suit_lower:
                    # Use actual cached icon size (matches renderer logic)
                    icon_img_check = self._slot_icon_cache.get(family_name)
                    eff_icon_s = icon_img_check.get_width() if icon_img_check else sw
                    badge_cy = slot_cy + int(eff_icon_s * 0.34)
                    val_surf = self.font_icon_value.render(str(power_value), True, (255, 255, 255))
                    # Collect suit icon widths to compute content_w
                    inner_gap = 3
                    suit_gap = 2
                    si_total_w = 0
                    _sc = self._slot_suit_icon_cache
                    if suit_b and suit_b != suit:
                        for sk in (suit.lower(), suit_b.lower()):
                            si = _sc.get(sk) or _sc.get(sk)
                            if si:
                                si_total_w += si.get_width() + suit_gap
                        si_total_w = max(0, si_total_w - suit_gap)
                    else:
                        si = _sc.get(suit.lower())
                        if si:
                            si_total_w = si.get_width()
                    content_w = val_surf.get_width() + (inner_gap + si_total_w if si_total_w else 0)
                    # Value text midleft is at badge_cx - content_w // 2
                    val_cx = cx - content_w // 2 + val_surf.get_width() // 2
                    # Use font metric for exact vertical centre of the text
                    val_rect = val_surf.get_rect(center=(val_cx, badge_cy))
                    strike_y = val_rect.centery
                    val_hw = val_surf.get_width() // 2 + 3
                    pygame.draw.line(
                        self.window, (220, 40, 40),
                        (val_cx - val_hw, strike_y), (val_cx + val_hw, strike_y), 2)
        else:
            # Empty diamond slot
            dr = self._slot_diamond.get_rect(center=(cx, slot_cy))
            self.window.blit(self._slot_diamond, dr.topleft)

            # Highlight current active slot
            if is_active_slot:
                hr = self._slot_highlight_diamond.get_rect(center=(cx, slot_cy))
                self.window.blit(self._slot_highlight_diamond, hr.topleft)

            # "?" label for opponent hidden slots
            if not is_player:
                q = self.font_small.render("?", True, (120, 100, 80))
                self.window.blit(q, q.get_rect(center=(cx, slot_cy)))

    # ──────────── slot figure sub-icons (shared helper) ────────

    _SLOT_FIG_HOVER_SCALE = 1.2  # enlarge factor on hover

    def _draw_slot_figure_icons(self, cx, slot_cy, sw, slot_figures, is_player, r_index):
        """Draw one or more small figure icons next to a round slot.

        Figures are laid out horizontally centred on *cx*.  Each icon consists
        of frame + figure image + a small info-box (suit icon + power).

        :param slot_figures: list of (Figure, source_tag) tuples
        """
        mx, my = pygame.mouse.get_pos()
        any_modal = self.battle_move_detail_box or self.figure_detail_box

        fig_s = int(sw * 0.55)
        frame_s = int(fig_s * 1.3)
        spacing = max(2, int(sw * 0.05))
        total_w = len(slot_figures) * frame_s + (len(slot_figures) - 1) * spacing
        start_x = cx - total_w // 2 + frame_s // 2  # centre of first icon

        for idx, (fig, source) in enumerate(slot_figures):
            icon_cx = start_x + idx * (frame_s + spacing)

            # Y position: player above the slot, opponent below
            icon_gap = max(4, int(sw * 0.2))
            if is_player:
                icon_cy = slot_cy - sw // 2 - frame_s // 2 - icon_gap
            else:
                icon_cy = slot_cy + sw // 2 + frame_s // 2 + icon_gap

            # Hit rect for hover / click (based on frame size)
            hit_rect = pygame.Rect(
                icon_cx - frame_s // 2, icon_cy - frame_s // 2,
                frame_s, frame_s,
            )
            is_hovered = hit_rect.collidepoint(mx, my) and not any_modal

            # Register for click handling
            self._round_fig_icons.append({
                'figure': fig,
                'rect': hit_rect,
                'is_player': is_player,
                'round': r_index,
                'source': source,
                'hovered': is_hovered,
            })

            # Determine render sizes (enlarge on hover)
            if is_hovered:
                s = self._SLOT_FIG_HOVER_SCALE
                r_fig_s = int(fig_s * s)
                r_frame_s = int(frame_s * s)
            else:
                r_fig_s = fig_s
                r_frame_s = frame_s

            # Scale frame + icon
            frame_raw = getattr(fig.family, 'frame_img', None)
            if frame_raw:
                frame_scaled = pygame.transform.smoothscale(frame_raw, (r_frame_s, r_frame_s))
            icon_scaled = pygame.transform.smoothscale(
                fig.family.icon_img, (r_fig_s, r_fig_s))

            # Apply a subtle brightness boost on hover
            if is_hovered:
                bright = pygame.Surface(icon_scaled.get_size(), pygame.SRCALPHA)
                bright.fill((40, 40, 40, 0))
                icon_scaled.blit(bright, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

            # Draw icon first, then frame on top (foreground)
            self.window.blit(icon_scaled,
                            icon_scaled.get_rect(center=(icon_cx, icon_cy)))
            if frame_raw:
                self.window.blit(frame_scaled,
                                frame_scaled.get_rect(center=(icon_cx, icon_cy)))

            # Small info box: suit icon + base power number — top-left of frame
            # Only shown for called figures; skill support figures don't need this.
            if source == 'call':
                fig_power = fig.get_value()
                fig_suit_lower = (fig.suit or '').lower()
                suit_ico = self._slot_suit_icon_cache.get(fig_suit_lower)
                pwr_txt = self.font_small.render(str(fig_power), True, (255, 255, 255))

                # Check if this call figure receives buffs_allies bonus
                buffs_bonus_txt = None
                if hasattr(fig, 'family') and hasattr(fig.family, 'field') and fig.family.field == 'village':
                    buffs_list = (self.player_buffs_allies_figures if is_player
                                  else self.opponent_buffs_allies_figures)
                    total_buff = sum(4 for bf in buffs_list if bf.suit == fig.suit)
                    if total_buff > 0:
                        buffs_bonus_txt = self.font_small.render(
                            f"+{total_buff}", True, (255, 255, 255))

                # Check if this call figure is targeted by distance attack
                da_penalty_txt = None
                if r_index is not None:
                    # is_player call fig → opponent's DA targets it
                    da_pen_val = self._get_da_call_penalty(for_player_da=not is_player, round_idx=r_index)
                    if da_pen_val > 0:
                        da_penalty_txt = self.font_small.render(
                            f" -{da_pen_val}", True, (255, 60, 60))

                ico_w = (suit_ico.get_width() + 3) if suit_ico else 0
                buffs_w = buffs_bonus_txt.get_width() if buffs_bonus_txt else 0
                penalty_w = da_penalty_txt.get_width() if da_penalty_txt else 0
                info_w = ico_w + pwr_txt.get_width() + buffs_w + penalty_w + 8
                info_h = max(pwr_txt.get_height(),
                             suit_ico.get_height() if suit_ico else 0) + 4

                # Position at top-left corner of the frame
                info_x = icon_cx - r_frame_s // 2
                info_y = icon_cy - r_frame_s // 2

                info_rect = pygame.Rect(info_x, info_y, info_w, info_h)
                info_bg = pygame.Surface((info_w, info_h), pygame.SRCALPHA)
                info_bg.fill((40, 25, 10, 180))
                self.window.blit(info_bg, info_rect.topleft)

                draw_x = info_rect.x + 4
                if suit_ico:
                    self.window.blit(
                        suit_ico,
                        (draw_x, info_rect.centery - suit_ico.get_height() // 2))
                    draw_x += suit_ico.get_width() + 3
                self.window.blit(
                    pwr_txt,
                    (draw_x, info_rect.centery - pwr_txt.get_height() // 2))
                draw_x += pwr_txt.get_width()
                if buffs_bonus_txt:
                    self.window.blit(
                        buffs_bonus_txt,
                        (draw_x, info_rect.centery - buffs_bonus_txt.get_height() // 2))
                    draw_x += buffs_bonus_txt.get_width()
                if da_penalty_txt:
                    self.window.blit(
                        da_penalty_txt,
                        (draw_x, info_rect.centery - da_penalty_txt.get_height() // 2))

            # ─── Info tag label at the bottom of the icon ───
            self._draw_slot_fig_tag(icon_cx, icon_cy, r_frame_s, fig, source, is_player)

    def _draw_slot_fig_tag(self, icon_cx, icon_cy, r_frame_s, fig, source, is_player):
        """Draw a small label tag at the bottom of a round-slot figure icon.

        - 'call'                  → "Called"
        - 'distance_attack'       → skill+suit icon + "Distance -N"
        - 'blocks_bonus'          → skill+suit icon + "Blocks Bonus"
        - 'buffs_allies'          → skill icon + "Buffs +4"
        - 'buffs_allies_defence'  → skill icon + "Defence +N"
        """
        from game.components.figures.family_configs.skill_config import SKILL_DEFINITIONS, get_advantage_suit

        info_color = (100, 230, 100) if is_player else (255, 100, 100)

        if source == 'call':
            label_txt = self.font_small.render("Called", True, (210, 210, 210))
            label_h = label_txt.get_height() + 4
            tag_w = label_txt.get_width() + 8
            tag_h = label_h + 2
            tag_x = icon_cx - tag_w // 2
            tag_y = icon_cy + r_frame_s // 2 - tag_h
            tag_bg = pygame.Surface((tag_w, tag_h), pygame.SRCALPHA)
            tag_bg.fill((40, 25, 10, 180))
            self.window.blit(tag_bg, (tag_x, tag_y))
            self.window.blit(label_txt,
                             (tag_x + 4, tag_y + (tag_h - label_txt.get_height()) // 2))

        elif source == 'distance_attack':
            penalty_val = fig.number_card.value if getattr(fig, 'number_card', None) else 0
            label_txt = self.font_small.render(f"Distance -{penalty_val}", True, info_color)
            label_h = label_txt.get_height() + 4

            # Build combined skill+suit icon (cached)
            adv_suit = get_advantage_suit(fig.suit)
            cache_key = f'_slot_da_tag_icon_{label_h}_{adv_suit}'
            if not hasattr(self, cache_key):
                skill_icon_path = SKILL_DEFINITIONS.get('distance_attack', {}).get('icon', '')
                try:
                    raw_skill = pygame.image.load(skill_icon_path).convert_alpha()
                    skill_scaled = pygame.transform.smoothscale(raw_skill, (label_h, label_h))
                    combined = pygame.Surface((label_h, label_h), pygame.SRCALPHA)
                    if adv_suit:
                        suit_path = settings.SUIT_ICON_IMG_PATH + adv_suit.lower() + '.png'
                        raw_suit = pygame.image.load(suit_path).convert_alpha()
                        suit_s = int(label_h * 0.85)
                        suit_scaled = pygame.transform.smoothscale(raw_suit, (suit_s, suit_s))
                        combined.blit(suit_scaled, ((label_h - suit_s) // 2, (label_h - suit_s) // 2))
                    combined.blit(skill_scaled, (0, 0))
                    setattr(self, cache_key, combined)
                except Exception:
                    setattr(self, cache_key, None)
            combined_ico = getattr(self, cache_key)

            ico_w = (combined_ico.get_width() + 3) if combined_ico else 0
            tag_w = ico_w + label_txt.get_width() + 8
            tag_h = label_h + 2
            tag_x = icon_cx - tag_w // 2
            tag_y = icon_cy + r_frame_s // 2 - tag_h
            tag_bg = pygame.Surface((tag_w, tag_h), pygame.SRCALPHA)
            tag_bg.fill((40, 25, 10, 180))
            self.window.blit(tag_bg, (tag_x, tag_y))
            dx = tag_x + 4
            if combined_ico:
                self.window.blit(combined_ico,
                                 (dx, tag_y + (tag_h - combined_ico.get_height()) // 2))
                dx += combined_ico.get_width() + 3
            self.window.blit(label_txt,
                             (dx, tag_y + (tag_h - label_txt.get_height()) // 2))

        elif source == 'blocks_bonus':
            label_txt = self.font_small.render("Blocks Bonus", True, info_color)
            label_h = label_txt.get_height() + 4

            adv_suit = get_advantage_suit(fig.suit)
            cache_key = f'_slot_bb_tag_icon_{label_h}_{adv_suit}'
            if not hasattr(self, cache_key):
                skill_icon_path = SKILL_DEFINITIONS.get('blocks_bonus', {}).get('icon', '')
                try:
                    raw_skill = pygame.image.load(skill_icon_path).convert_alpha()
                    skill_scaled = pygame.transform.smoothscale(raw_skill, (label_h, label_h))
                    combined = pygame.Surface((label_h, label_h), pygame.SRCALPHA)
                    if adv_suit:
                        suit_path = settings.SUIT_ICON_IMG_PATH + adv_suit.lower() + '.png'
                        raw_suit = pygame.image.load(suit_path).convert_alpha()
                        suit_s = int(label_h * 0.85)
                        suit_scaled = pygame.transform.smoothscale(raw_suit, (suit_s, suit_s))
                        combined.blit(suit_scaled, ((label_h - suit_s) // 2, (label_h - suit_s) // 2))
                    combined.blit(skill_scaled, (0, 0))
                    setattr(self, cache_key, combined)
                except Exception:
                    setattr(self, cache_key, None)
            combined_ico = getattr(self, cache_key)

            ico_w = (combined_ico.get_width() + 3) if combined_ico else 0
            tag_w = ico_w + label_txt.get_width() + 8
            tag_h = label_h + 2
            tag_x = icon_cx - tag_w // 2
            tag_y = icon_cy + r_frame_s // 2 - tag_h
            tag_bg = pygame.Surface((tag_w, tag_h), pygame.SRCALPHA)
            tag_bg.fill((40, 25, 10, 180))
            self.window.blit(tag_bg, (tag_x, tag_y))
            dx = tag_x + 4
            if combined_ico:
                self.window.blit(combined_ico,
                                 (dx, tag_y + (tag_h - combined_ico.get_height()) // 2))
                dx += combined_ico.get_width() + 3
            self.window.blit(label_txt,
                             (dx, tag_y + (tag_h - label_txt.get_height()) // 2))

        elif source == 'buffs_allies':
            label_txt = self.font_small.render("Buffs +4", True, info_color)
            label_h = label_txt.get_height() + 4

            # Build skill icon + suit icon side by side (cached)
            suit_self = SKILL_DEFINITIONS.get('buffs_allies', {}).get('suit_self', False)
            own_suit = (getattr(fig, 'suit', '') or '').lower() if suit_self else ''
            cache_key = f'_slot_ba_tag_icon_{label_h}_{own_suit}'
            if not hasattr(self, cache_key):
                skill_icon_path = SKILL_DEFINITIONS.get('buffs_allies', {}).get('icon', '')
                try:
                    raw_skill = pygame.image.load(skill_icon_path).convert_alpha()
                    skill_scaled = pygame.transform.smoothscale(raw_skill, (label_h, label_h))
                    if own_suit:
                        suit_path = settings.SUIT_ICON_IMG_PATH + own_suit + '.png'
                        raw_suit = pygame.image.load(suit_path).convert_alpha()
                        suit_s = int(label_h * 0.85)
                        suit_scaled = pygame.transform.smoothscale(raw_suit, (suit_s, suit_s))
                        gap = 2
                        combined_w = label_h + gap + suit_s
                        combined = pygame.Surface((combined_w, label_h), pygame.SRCALPHA)
                        combined.blit(skill_scaled, (0, 0))
                        combined.blit(suit_scaled, (label_h + gap, (label_h - suit_s) // 2))
                        setattr(self, cache_key, combined)
                    else:
                        setattr(self, cache_key, skill_scaled)
                except Exception:
                    setattr(self, cache_key, None)
            skill_ico = getattr(self, cache_key)

            ico_w = (skill_ico.get_width() + 3) if skill_ico else 0
            tag_w = ico_w + label_txt.get_width() + 8
            tag_h = label_h + 2
            tag_x = icon_cx - tag_w // 2
            tag_y = icon_cy + r_frame_s // 2 - tag_h
            tag_bg = pygame.Surface((tag_w, tag_h), pygame.SRCALPHA)
            tag_bg.fill((40, 25, 10, 180))
            self.window.blit(tag_bg, (tag_x, tag_y))
            dx = tag_x + 4
            if skill_ico:
                self.window.blit(skill_ico,
                                 (dx, tag_y + (tag_h - skill_ico.get_height()) // 2))
                dx += skill_ico.get_width() + 3
            self.window.blit(label_txt,
                             (dx, tag_y + (tag_h - label_txt.get_height()) // 2))

        elif source == 'buffs_allies_defence':
            bonus_val = fig.number_card.value if getattr(fig, 'number_card', None) else 0
            label_txt = self.font_small.render(f"Defence +{bonus_val}", True, info_color)
            label_h = label_txt.get_height() + 4

            # Build combined skill icon (cached)
            cache_key = f'_slot_bad_tag_icon_{label_h}'
            if not hasattr(self, cache_key):
                skill_icon_path = SKILL_DEFINITIONS.get('buffs_allies_defence', {}).get('icon', '')
                try:
                    raw_skill = pygame.image.load(skill_icon_path).convert_alpha()
                    skill_scaled = pygame.transform.smoothscale(raw_skill, (label_h, label_h))
                    setattr(self, cache_key, skill_scaled)
                except Exception:
                    setattr(self, cache_key, None)
            skill_ico = getattr(self, cache_key)

            ico_w = (skill_ico.get_width() + 3) if skill_ico else 0
            tag_w = ico_w + label_txt.get_width() + 8
            tag_h = label_h + 2
            tag_x = icon_cx - tag_w // 2
            tag_y = icon_cy + r_frame_s // 2 - tag_h
            tag_bg = pygame.Surface((tag_w, tag_h), pygame.SRCALPHA)
            tag_bg.fill((40, 25, 10, 180))
            self.window.blit(tag_bg, (tag_x, tag_y))
            dx = tag_x + 4
            if skill_ico:
                self.window.blit(skill_ico,
                                 (dx, tag_y + (tag_h - skill_ico.get_height()) // 2))
                dx += skill_ico.get_width() + 3
            self.window.blit(label_txt,
                             (dx, tag_y + (tag_h - label_txt.get_height()) // 2))

    def _update_round_fig_hover(self):
        """Set _round_fig_hovered_idx based on current mouse position."""
        mx, my = pygame.mouse.get_pos()
        any_modal = self.battle_move_detail_box or self.figure_detail_box
        for i, entry in enumerate(self._round_fig_icons):
            if entry['rect'].collidepoint(mx, my) and not any_modal:
                self._round_fig_hovered_idx = i
                return
        self._round_fig_hovered_idx = None

    # ──────────── (4) Total Summary Circle (right) ─────────────

    def _draw_total_circle(self):
        """Draw the summary circle showing the running total difference."""
        cx = self._sx(settings.TOTAL_CIRCLE_X)
        cy = self._sy(settings.TOTAL_CIRCLE_Y)
        r = settings.TOTAL_CIRCLE_RADIUS

        total = self._get_total_diff()

        # Choose color based on total
        if total > 0:
            ring_color = settings.TOTAL_CIRCLE_POSITIVE_COLOR
        elif total < 0:
            ring_color = settings.TOTAL_CIRCLE_NEGATIVE_COLOR
        else:
            ring_color = settings.TOTAL_CIRCLE_NEUTRAL_COLOR

        # Background circle
        pygame.draw.circle(self.window, settings.TOTAL_CIRCLE_BG_COLOR, (cx, cy), r)
        # Colored ring
        pygame.draw.circle(self.window, ring_color, (cx, cy), r, settings.TOTAL_CIRCLE_BORDER_W)

        # "Total" label inside the circle (above centre)
        label = self.font_small.render("Total", True, settings.ROUNDS_LABEL_COLOR)
        self.window.blit(label, label.get_rect(centerx=cx, centery=cy - r // 3))

        # Value text (below centre)
        sign = "+" if total > 0 else ""
        val_surf = self.font_total.render(f"{sign}{total}", True, ring_color)
        self.window.blit(val_surf, val_surf.get_rect(centerx=cx, centery=cy + r // 5))

    # ──────────── Turn Indicator ───────────────────────────────

    def _draw_turn_indicator(self):
        """Draw whose turn it is — or a 'finish!' button when all moves are played."""
        cx = self._sx(settings.TURN_INDICATOR_X)
        ty = self._sy(settings.TURN_INDICATOR_Y)

        if self._all_moves_played():
            # ─── render a clickable "finish!" button ───
            btn_w = settings.FINISH_BTN_W
            btn_h = settings.FINISH_BTN_H
            btn_rect = pygame.Rect(
                self._sx(settings.FINISH_BTN_X) - btn_w // 2,
                self._sy(settings.FINISH_BTN_Y),
                btn_w, btn_h
            )
            self._finish_btn_rect = btn_rect

            mx, my = pygame.mouse.get_pos()
            self._finish_btn_hovered = btn_rect.collidepoint(mx, my)

            bg_color = settings.FINISH_BTN_HOVER_COLOR if self._finish_btn_hovered else settings.FINISH_BTN_COLOR
            pygame.draw.rect(self.window, bg_color, btn_rect, border_radius=6)
            pygame.draw.rect(self.window, settings.FINISH_BTN_BORDER_COLOR, btn_rect, 2, border_radius=6)

            txt = self.font_turn.render("finish!", True, settings.FINISH_BTN_TEXT_COLOR)
            self.window.blit(txt, txt.get_rect(center=btn_rect.center))

            if self._finish_btn_hovered:
                pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_HAND)
        else:
            self._finish_btn_rect = None
            self._finish_btn_hovered = False

            if self.is_player_turn:
                text = "Your turn!"
                color = settings.TURN_YOUR_COLOR
            else:
                text = "Waiting..."
                color = settings.TURN_OPPONENT_COLOR

            turn_surf = self.font_turn.render(text, True, color)
            self.window.blit(turn_surf, turn_surf.get_rect(centerx=cx, top=ty))

    # ──────────── Shared Helpers ───────────────────────────────

    def _draw_power_circle(self, cx, cy, value=None, crossed_out=False):
        """Draw a small circle displaying a power value.

        :param cx: centre x
        :param cy: centre y
        :param value: integer power value, or None for empty ("—")
        :param crossed_out: if True, draw a red strikethrough (Block effect)
        """
        r = settings.POWER_CIRCLE_RADIUS
        pygame.draw.circle(self.window, settings.POWER_CIRCLE_BG_COLOR, (cx, cy), r)
        pygame.draw.circle(self.window, settings.POWER_CIRCLE_BORDER_COLOR, (cx, cy), r,
                           settings.POWER_CIRCLE_BORDER_W)

        if value is not None:
            color = (160, 120, 100) if crossed_out else settings.POWER_CIRCLE_TEXT_COLOR
            txt = self.font_power_circle.render(str(value), True, color)
        else:
            txt = self.font_power_circle.render(settings.POWER_CIRCLE_EMPTY_TEXT, True,
                                                settings.POWER_CIRCLE_EMPTY_COLOR)
        self.window.blit(txt, txt.get_rect(center=(cx, cy)))

        # Red diagonal strikethrough when blocked
        if crossed_out and value is not None:
            offset = r - 3
            pygame.draw.line(self.window, (200, 60, 60),
                             (cx - offset, cy + offset),
                             (cx + offset, cy - offset), 2)

    def _draw_diff_box(self, cx, cy, w, h, diff, label=None, label_color=None):
        """Draw a small power-difference box.

        :param diff: integer difference (player - opponent), or None if not yet computed
        :param label: optional text drawn above the box
        :param label_color: color for the label (defaults to ROUNDS_LABEL_COLOR)
        """
        rect = pygame.Rect(cx - w // 2, cy, w, h)

        # Background
        pygame.draw.rect(self.window, settings.DIFF_BOX_BG_COLOR, rect)
        pygame.draw.rect(self.window, settings.DIFF_BOX_BORDER_COLOR, rect, 2)

        if diff is None:
            # Not yet played — show dash
            txt = self.font_diff.render("—", True, settings.DIFF_NEUTRAL_COLOR)
        else:
            if diff > 0:
                color = settings.DIFF_POSITIVE_COLOR
                sign = "+"
            elif diff < 0:
                color = settings.DIFF_NEGATIVE_COLOR
                sign = ""
            else:
                color = settings.DIFF_NEUTRAL_COLOR
                sign = "±"
                diff = 0
            txt = self.font_diff.render(f"{sign}{diff}", True, color)

        self.window.blit(txt, txt.get_rect(center=rect.center))

        # Optional label above
        if label:
            lbl_color = label_color or settings.ROUNDS_LABEL_COLOR
            lbl = self.font_small.render(label, True, lbl_color)
            self.window.blit(lbl, lbl.get_rect(centerx=cx, bottom=rect.top - 2))
