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
        self.font_normal = pygame.font.Font(settings.FONT_PATH, settings.BATTLE_SCREEN_FONT_SIZE)
        self.font_small = pygame.font.Font(settings.FONT_PATH, settings.BATTLE_SCREEN_FONT_SIZE_SMALL)
        self.font_value = pygame.font.Font(settings.FONT_PATH, settings.BATTLE_SCREEN_VALUE_FONT_SIZE)
        self.font_value.set_bold(True)
        self.font_diff = pygame.font.Font(settings.FONT_PATH, settings.BATTLE_SCREEN_DIFF_FONT_SIZE)
        self.font_diff.set_bold(True)
        self.font_total = pygame.font.Font(settings.FONT_PATH, settings.BATTLE_SCREEN_TOTAL_FONT_SIZE)
        self.font_total.set_bold(True)
        self.font_round = pygame.font.Font(settings.FONT_PATH, settings.ROUNDS_LABEL_FONT_SIZE)
        self.font_round.set_bold(True)
        self.font_turn = pygame.font.Font(settings.FONT_PATH, settings.TURN_INDICATOR_FONT_SIZE)
        self.font_turn.set_bold(True)
        self.font_power_circle = pygame.font.Font(settings.FONT_PATH, settings.POWER_CIRCLE_FONT_SIZE)
        self.font_power_circle.set_bold(True)

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
        self._awaiting_draw_choice = False       # True while showing draw options

        # ── round-panel figure icons (clickable sub-icons next to slots) ──
        # Each entry: {'figure': Figure, 'rect': pygame.Rect, 'is_player': bool,
        #              'round': int, 'source': str}  (source = 'call' | 'skill_xxx')
        # Rebuilt every frame during _draw_rounds_panel.
        self._round_fig_icons = []
        self._round_fig_hovered_idx = None   # index into _round_fig_icons or None

        # ── loaded game id tracking ──
        self._loaded_game_id = None

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
        self.battle_move_detail_box = None
        self.figure_detail_box = None
        self._player_figures = []
        self._opponent_figures = []
        self._resources_data = None
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
        self._returnable_cards = []
        self._awaiting_card_pick = False
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
        self._loaded_game_id = None
        self.dialogue_box = None
        print("[BattleScreen] State reset for game switch")

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
        except Exception as e:
            print(f"[BattleScreen] Failed to load player moves: {e}")
            self.player_moves = []

        # Load opponent's bought battle moves (will be hidden)
        try:
            if self.game.opponent_player:
                result = battle_shop_service.get_battle_moves(
                    self.game.game_id, self.game.opponent_player['id'],
                )
                self.opponent_moves = result.get('battle_moves', [])
        except Exception as e:
            print(f"[BattleScreen] Failed to load opponent moves: {e}")
            self.opponent_moves = []

        # Determine invader status
        self.player_is_invader = self.game.invader

        # Load battling figures
        self._load_battle_figures()

        # Load all player figures + resources for Call move eligibility checks
        try:
            families = self.figure_manager.families
            self._player_figures = self.game.get_figures(families, is_opponent=False)
            self._opponent_figures = self.game.get_figures(families, is_opponent=True)
            self._resources_data = self.game.calculate_resources(families, is_opponent=False)
        except Exception as e:
            print(f"[BattleScreen] Failed to load player figures for call eligibility: {e}")
            self._player_figures = []
            self._opponent_figures = []
            self._resources_data = None

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

        self._loaded_game_id = self.game.game_id

    def _load_battle_figures(self):
        """Load the advancing and defending figures as FieldFigureIcons."""
        if not self.game:
            return

        families = self.figure_manager.families
        adv_id = self.game.advancing_figure_id
        def_id = self.game.defending_figure_id

        # Load player's figures and opponent's figures
        try:
            player_figures = self.game.get_figures(families, is_opponent=False)
            opponent_figures = self.game.get_figures(families, is_opponent=True)
        except Exception as e:
            print(f"[BattleScreen] Failed to load figures: {e}")
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
        else:
            # Player is the defender
            player_battle_figures = player_figures
            opponent_battle_figures = opponent_figures
            player_fig_id = def_id
            opponent_fig_id = adv_id

        # Find the specific figures
        self.player_figure = None
        for fig in player_battle_figures:
            if fig.id == player_fig_id:
                self.player_figure = fig
                break

        self.opponent_figure = None
        for fig in opponent_battle_figures:
            if fig.id == opponent_fig_id:
                self.opponent_figure = fig
                break

        # Create FieldFigureIcons for rendering
        if self.player_figure:
            self.player_figure_icon = FieldFigureIcon(
                window=self.window,
                game=self.game,
                figure=self.player_figure,
                is_visible=True,
                all_player_figures=player_battle_figures,
            )
            self.player_figure_icon.show_advance_overlay = False

        if self.opponent_figure:
            self.opponent_figure_icon = FieldFigureIcon(
                window=self.window,
                game=self.game,
                figure=self.opponent_figure,
                is_visible=True,  # Fully revealed during battle
                all_player_figures=opponent_battle_figures,
            )
            self.opponent_figure_icon.show_advance_overlay = False
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

    def _figure_has_deficit(self, fig):
        """Check whether a figure's resource requirements exceed available supply."""
        if not getattr(fig, 'requires', None):
            return False
        if not self._resources_data:
            return False
        produces = self._resources_data.get('produces', {})
        requires = self._resources_data.get('requires', {})
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
            bonus = bm_value if fig.suit == bm_suit else 0
            total = base + bonus
            if total > max_power:
                max_power = total
        return max_power

    # ────────────────── power calculations ─────────────────────

    def _get_figure_total_power(self, figure, figure_icon):
        """Get total power of a figure including base value, bonus, and enchantments."""
        if not figure:
            return 0
        base = figure.get_value()
        bonus = figure_icon.battle_bonus_received if figure_icon else 0
        enchant = figure.get_total_enchantment_modifier()
        return base + bonus + enchant

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
        p_val = self._get_move_effective_power(p)
        o_val = self._get_move_effective_power(o)
        return p_val - o_val

    def _get_move_effective_power(self, move):
        """Get effective power of a played move including Call-figure bonus.

        - Block → 0
        - Call + suit match → figure_base_power + BM value
        - Call + suit mismatch → figure_base_power only (BM nullified)
        - No call figure → BM value
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
            if fig_suit == bm_suit:
                return fig_power + bm_value
            return fig_power
        return bm_value

    def _get_figure_diff(self):
        """Get figure power difference (player - opponent)."""
        p_power = self._get_figure_total_power(self.player_figure, self.player_figure_icon)
        o_power = self._get_figure_total_power(self.opponent_figure, self.opponent_figure_icon)
        return p_power - o_power

    def _get_total_diff(self):
        """Get total difference: figure diff + all completed round diffs."""
        total = self._get_figure_diff()
        for i in range(3):
            rd = self._get_round_diff(i)
            if rd is not None:
                total += rd
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

    # ────────────────────── update ─────────────────────────────

    def update(self, game):
        """Update the game state."""
        super().update(game)
        self.game = game

        # Load data if needed
        current_gid = getattr(game, 'game_id', None)
        if current_gid and current_gid != self._loaded_game_id:
            self._load_battle_data()

        # Poll server for battle state changes (opponent moves, turn updates)
        self._poll_battle_state()

        # Auto-skip: if it's our turn but we have no unused moves left
        self._check_auto_skip()

        # Keep the scoreboard battle-turns count in sync
        self._sync_battle_turns()

    def _poll_battle_state(self):
        """Fetch the current battle state from the server and reconcile."""
        if not self.game or not self.game.game_id:
            return

        result = game_service.get_battle_state(
            self.game.game_id, self.game.player_id)

        if not result.get('success'):
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
        if not self.game or not self.is_player_turn or self._auto_skip_pending:
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
        print(f"[BattleScreen] No moves left — auto-skipping round {self.current_round + 1}")

        result = game_service.skip_battle_turn(
            self.game.game_id, self.game.player_id)

        if not result.get('success'):
            print(f"[BattleScreen] skip_battle_turn failed: {result.get('message')}")
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
                for fig_icon in (self.player_figure_icon, self.opponent_figure_icon):
                    if fig_icon:
                        fig_icon.hovered = fig_icon.collide() and fig_icon.is_visible
                break

        # Figure icon click handling
        for fig_icon, fig_obj, fig_list in (
            (self.player_figure_icon, self.player_figure, self._player_figures),
            (self.opponent_figure_icon, self.opponent_figure, None),
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
                        resources_data=self._resources_data,
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
                    resources_data=self._resources_data if is_player else None,
                )
                return True
        return False

    def _handle_panel_icon_click(self, event):
        """Check if player clicked a battle move icon in the left panel."""
        mx, my = event.pos
        panel_cx = settings.BATTLE_PANEL_X + settings.BATTLE_PANEL_W // 2
        icon_s = settings.BATTLE_PANEL_ICON_SIZE

        # Build the same filtered list used by _draw_battle_panel so
        # click positions match the visual positions.
        visible_moves = [(i, m) for i, m in enumerate(self.player_moves)
                         if not self._is_move_used(i)]

        for slot, (i, move) in enumerate(visible_moves):
            icon_cy = settings.BATTLE_PANEL_ICON_START_Y + slot * settings.BATTLE_PANEL_ICON_DELTA_Y
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
        print(f"[BattleScreen] Action '{action}' for move {move_idx}, figure={getattr(selected_fig, 'name', None)}")

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
            print(f"[BattleScreen] play_battle_move failed: {msg}")
            self.make_dialogue_box(
                f"Failed to play move:\n{msg}",
                actions=['ok'], icon='info', title="Error")
            return

        print(f"[BattleScreen] Played {family_name} (id={battle_move_id}) "
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

        total_diff = self._get_total_diff()
        print(f"[BattleScreen] Finishing battle — total_diff = {total_diff}")

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

        msg = (
            f"{loser}'s {fig_name} is destroyed!\n"
            f"You earn {pts} points.\n\n"
            f"Pick one card from the spoils."
        )
        large_icon = settings.DIALOGUE_BOX_LARGE_ICON_DICT.get('victory')
        images = [large_icon] if large_icon else []
        self.make_dialogue_box(msg, actions=['pick card'], icon='victory', title="Victory!", images=images)
        self._dialogue_callback = self._on_victory_dialogue

    def _show_defeat_result(self, result):
        """Display defeat dialogue — player lost the battle."""
        pts = result.get('points_awarded', 0)
        fig_name = result.get('destroyed_figure_name', 'figure')
        winner = result.get('winner_name', 'Opponent')

        msg = (
            f"Your {fig_name} is destroyed!\n"
            f"{winner} earns {pts} points."
        )
        large_icon = settings.DIALOGUE_BOX_LARGE_ICON_DICT.get('defeat')
        images = [large_icon] if large_icon else []
        self.make_dialogue_box(msg, actions=['ok'], icon='defeat', title="Defeat", images=images)
        self._dialogue_callback = self._on_defeat_acknowledged

    def _show_draw_result(self, result):
        """Display draw dialogue — the defender gets to choose."""
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
        """Handle victory dialogue: always opens card picker."""
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
            cards[:6],
            title="Pick a Card",
            callback=self._on_card_picked,
        )

    def _on_card_picked(self, card_data):
        """Handle the card picker confirm for a victory pick."""
        self._awaiting_card_pick = False
        if card_data:
            self._finalise_winner_pick(card_data.get('id'), card_data.get('card_type', 'main'))
        else:
            self._finalise_winner_pick(None, None)

    def _finalise_winner_pick(self, card_id, card_type):
        """Call the server to pick a card and do post-battle cleanup."""
        result = game_service.finish_battle_pick_card(
            self.game.game_id,
            self.game.player_id,
            picked_card_id=card_id,
            picked_card_type=card_type or 'main',
        )
        if result.get('success') and result.get('game'):
            self.game.update_from_dict(result['game'])
        self._reset_after_battle()

    # ─── defeat callback ───

    def _on_defeat_acknowledged(self, response):
        """After defeat dialogue, just reset locally.
        The winner's client handles server-side cleanup (card pick + new round).
        """
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
        result = game_service.finish_battle_draw(
            self.game.game_id,
            self.game.player_id,
            choice=choice,
        )
        if result.get('success') and result.get('game'):
            self.game.update_from_dict(result['game'])
        self._reset_after_battle()

    def _show_draw_card_pick(self):
        """Show card picker for draw defender pick_card choice."""
        cards = self._returnable_cards
        self._open_card_picker(
            cards[:6],
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
        )
        if result.get('success') and result.get('game'):
            self.game.update_from_dict(result['game'])
        self._reset_after_battle()

    def _on_draw_wait_acknowledged(self, response):
        """Non-defender acknowledged draw — battle cleanup happens when defender resolves."""
        # The defender will resolve it; we just return to field and update on next poll.
        self._reset_after_battle()

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
        btn_h = settings.MENU_BUTTON_HEIGHT
        padding = settings.SMALL_SPACER_X

        cards_row_w = num * card_w + (num - 1) * spacing
        box_w = max(cards_row_w + 2 * padding, int(0.3 * settings.SCREEN_WIDTH))
        box_h = title_h + card_h + spacing + btn_h + 2 * padding
        box_x = settings.CENTER_X - box_w // 2
        box_y = settings.CENTER_Y - box_h // 2
        self._card_picker_box_rect = pygame.Rect(box_x, box_y, box_w, box_h)

        # Create confirm button (centred at bottom of box)
        btn_x = settings.CENTER_X - settings.MENU_BUTTON_WIDTH // 2
        btn_y = box_y + box_h - btn_h - padding
        self._card_picker_confirm_btn = Button(self.window, btn_x, btn_y, "Confirm")
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

        # Semi-transparent full-screen overlay
        overlay = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.window.blit(overlay, (0, 0))

        box = self._card_picker_box_rect
        # Box background
        pygame.draw.rect(self.window, settings.COLOR_DIALOGUE_BOX, box)
        border = box.inflate(settings.DIALOGUE_BOX_BORDER_WIDTH, settings.DIALOGUE_BOX_BORDER_WIDTH)
        pygame.draw.rect(self.window, settings.COLOR_DIALOGUE_BOX_BORDER, border, settings.DIALOGUE_BOX_BORDER_WIDTH)

        # Title
        title_font = pygame.font.Font(settings.FONT_PATH, settings.FONT_SIZE_TITLE_DIALOGUE_BOX)
        title_font.set_bold(True)
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
                # Default: greyed out
                card_img.draw_front(rect.x, rect.y)

            # Card label below
            label_font = pygame.font.Font(settings.FONT_PATH, int(0.018 * settings.SCREEN_HEIGHT))
            suit = entry['card_data'].get('suit', '?')
            rank = entry['card_data'].get('rank', '?')
            label = f"{rank} of {suit}"
            label_color = (255, 255, 255) if (is_selected or is_hovered) else (140, 140, 140)
            label_surf = label_font.render(label, True, label_color)
            label_rect = label_surf.get_rect(centerx=rect.centerx, top=rect.bottom + 4)
            self.window.blit(label_surf, label_rect)

        # Draw confirm button
        btn = self._card_picker_confirm_btn
        if self._card_picker_selected is not None:
            btn.disabled = False
        else:
            btn.disabled = True

        # Draw button with disabled state styling
        if btn.disabled:
            # Grey out the button
            btn.draw()
            grey_overlay = pygame.Surface((btn.rect.width, btn.rect.height), pygame.SRCALPHA)
            grey_overlay.fill((0, 0, 0, 140))
            self.window.blit(grey_overlay, btn.rect.topleft)
        else:
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
        print("[BattleScreen] Post-battle cleanup — returning to field")

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
            self.game.battle_ready_shown = False
            self.game.pending_own_advance_notification = False
            self.game.pending_advance_notification = False
            self.game.waiting_for_battle_decision = False
            self.game.pending_fold_result = False
            self.game.fold_result_shown = False
            self.game.auto_proceed_to_battle = False
            self.game.battle_moves_phase = False
            self.game.battle_moves_ready = False
            self.game.waiting_for_opponent_battle_moves = False
            self.game.both_battle_moves_ready = False

        # Clear all local battle state
        self.reset_state()

        # Switch subscreen
        self.state.subscreen = 'field'

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
            self.font_small, icon_s, suit_b=suit_b,
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

    def draw(self):
        """Draw the entire battle screen."""
        super().draw()

        self._draw_battle_panel()
        self._draw_figures_panel()
        # Clear round-panel figure icons before redrawing
        self._round_fig_icons = []
        self._round_fig_hovered_idx = None
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
        px = settings.BATTLE_PANEL_X
        py = settings.BATTLE_PANEL_Y
        pw = settings.BATTLE_PANEL_W
        ph = settings.BATTLE_PANEL_H

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
            icon_cy = settings.BATTLE_PANEL_ICON_START_Y + slot * settings.BATTLE_PANEL_ICON_DELTA_Y

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
                self.font_small, icon_s,
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
        px = settings.FIGURES_PANEL_X
        py = settings.FIGURES_PANEL_Y
        pw = settings.FIGURES_PANEL_W
        ph = settings.FIGURES_PANEL_H
        gap = 4

        # Sub-box boundaries based on diff box position
        diff_area_top = settings.FIGURES_DIFF_Y - 24
        diff_area_bot = settings.FIGURES_DIFF_Y + settings.FIGURES_DIFF_H + 8

        # Player sub-box (top)
        self._draw_panel_sub_box(px, py, pw, diff_area_top - gap - py)
        # Diff sub-box (middle)
        self._draw_panel_sub_box(px, diff_area_top, pw, diff_area_bot - diff_area_top)
        # Opponent sub-box (bottom)
        opp_y = diff_area_bot + gap
        self._draw_panel_sub_box(px, opp_y, pw, py + ph - opp_y)

        panel_cx = px + pw // 2

        # ─── Player figure (top) ───
        label_you = self.font_normal.render("YOU", True, settings.ROUNDS_LABEL_COLOR)
        self.window.blit(label_you, label_you.get_rect(centerx=panel_cx, top=py + 6))

        if self.player_figure_icon:
            fig_cx = panel_cx
            fig_cy = settings.FIGURES_PLAYER_Y + int(0.10 * settings.SCREEN_HEIGHT)
            self.player_figure_icon.draw(fig_cx, fig_cy)

        # ─── Power difference box (middle) ───
        diff = self._get_figure_diff()
        self._draw_diff_box(
            panel_cx, settings.FIGURES_DIFF_Y,
            settings.FIGURES_DIFF_W, settings.FIGURES_DIFF_H,
            diff, label="Figure Clash (start)",
        )

        # ─── Opponent figure (bottom) — label at bottom of sub-box ───
        if self.opponent_figure_icon:
            fig_cx = panel_cx
            fig_cy = settings.FIGURES_OPPONENT_Y + int(0.10 * settings.SCREEN_HEIGHT)
            self.opponent_figure_icon.draw(fig_cx, fig_cy)

        opp_box_bottom = py + ph
        label_opp = self.font_normal.render("OPPONENT", True, settings.ROUNDS_LABEL_COLOR)
        self.window.blit(label_opp, label_opp.get_rect(centerx=panel_cx, bottom=opp_box_bottom - 6))

        # Cursor hand on figure hover (main figures + round-panel sub-icons)
        fig_hovered = False
        for fig_icon in (self.player_figure_icon, self.opponent_figure_icon):
            if fig_icon and fig_icon.hovered:
                fig_hovered = True
                break
        if not fig_hovered and self._round_fig_hovered_idx is not None:
            fig_hovered = True
        if fig_hovered and not self.battle_move_detail_box and not self.figure_detail_box:
            pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_HAND)

    # ──────────── (3) Rounds Panel (centre) ────────────────────

    def _draw_rounds_panel(self):
        """Draw the 3 round columns with slots and labels."""
        px = settings.ROUNDS_PANEL_X
        py = settings.ROUNDS_PANEL_Y
        pw = settings.ROUNDS_PANEL_W
        ph = settings.ROUNDS_PANEL_H
        gap = 4

        # Sub-box boundaries based on diff box position
        diff_area_top = settings.ROUNDS_DIFF_Y - 24
        diff_area_bot = settings.ROUNDS_DIFF_Y + settings.ROUNDS_DIFF_H + 8

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
                col_cx, settings.ROUNDS_PLAYER_SLOT_Y,
                self.player_played[r], is_current and self.is_player_turn,
                is_player=True, r_index=r,
            )

            # ─── Round difference box (middle, with round label) ───
            rd = self._get_round_diff(r)
            lbl_color = settings.ROUNDS_LABEL_ACTIVE_COLOR if is_current else settings.ROUNDS_LABEL_COLOR
            self._draw_diff_box(
                col_cx, settings.ROUNDS_DIFF_Y,
                settings.ROUNDS_DIFF_W, settings.ROUNDS_DIFF_H,
                rd, label=f"Round {r + 1}", label_color=lbl_color,
            )

            # ─── Opponent slot (bottom) ───
            self._draw_round_slot(
                col_cx, settings.ROUNDS_OPPONENT_SLOT_Y,
                self.opponent_played[r], is_current and not self.is_player_turn,
                is_player=False, r_index=r,
            )

    def _draw_all_power_circles(self):
        """Draw every power circle AFTER all panels so they sit on top."""
        # --- Figures panel circles ---
        fig_cx = settings.FIGURES_PANEL_X + settings.FIGURES_PANEL_W // 2
        player_power = self._get_figure_total_power(self.player_figure, self.player_figure_icon)
        self._draw_power_circle(fig_cx, settings.POWER_CIRCLE_PLAYER_Y, player_power)

        opp_power = self._get_figure_total_power(self.opponent_figure, self.opponent_figure_icon)
        self._draw_power_circle(fig_cx, settings.POWER_CIRCLE_OPPONENT_Y, opp_power)

        # --- Rounds panel circles (3 columns) ---
        rpx = settings.ROUNDS_PANEL_X
        rpw = settings.ROUNDS_PANEL_W
        panel_cx = rpx + rpw // 2
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
                p_val = self._get_move_effective_power(p_move)
                # If opponent played Block, player's value is crossed out
                if o_move and o_move.get('family_name') == 'Block':
                    p_crossed = True

            o_val = None
            o_crossed = False
            if o_move:
                o_val = self._get_move_effective_power(o_move)
                # If player played Block, opponent's value is crossed out
                if p_move and p_move.get('family_name') == 'Block':
                    o_crossed = True

            # Player circle
            self._draw_power_circle(col_cx, settings.POWER_CIRCLE_PLAYER_Y, p_val,
                                    crossed_out=p_crossed)
            # Opponent circle
            self._draw_power_circle(col_cx, settings.POWER_CIRCLE_OPPONENT_Y, o_val,
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

            # Draw all figure sub-icons for this slot (supports multiple)
            if slot_figures:
                self._draw_slot_figure_icons(
                    cx, slot_cy, sw, slot_figures, is_player, r_index)

            draw_battle_move_icon(
                self.window, cx, slot_cy,
                family_name, suit, power_value,
                self._slot_glow_cache, self._slot_icon_cache,
                self._slot_frame_cache, self._slot_suit_icon_cache,
                self.font_small, sw, suit_b=suit_b,
            )

            # Red strikethrough on BM value number only when called-figure suit ≠ BM suit
            if call_fig and hasattr(call_fig, 'suit'):
                bm_suit_lower = (suit or '').lower()
                cf_suit_lower = (call_fig.suit or '').lower()
                if cf_suit_lower != bm_suit_lower:
                    # Value number is at cx - 0.26*sw, centred vertically
                    val_cx = cx - int(sw * 0.26)
                    val_txt = self.font_small.render(str(power_value), True, (255, 255, 255))
                    val_hw = val_txt.get_width() // 2 + 3
                    pygame.draw.line(
                        self.window, (220, 40, 40),
                        (val_cx - val_hw, slot_cy), (val_cx + val_hw, slot_cy), 3)
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
        spacing = 4
        total_w = len(slot_figures) * frame_s + (len(slot_figures) - 1) * spacing
        start_x = cx - total_w // 2 + frame_s // 2  # centre of first icon

        for idx, (fig, source) in enumerate(slot_figures):
            icon_cx = start_x + idx * (frame_s + spacing)

            # Y position: player above the slot, opponent below
            if is_player:
                icon_cy = slot_cy - sw // 2 - frame_s // 2 - 16
            else:
                icon_cy = slot_cy + sw // 2 + frame_s // 2 + 16

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
            fig_power = fig.get_value()
            fig_suit_lower = (fig.suit or '').lower()
            suit_ico = self._slot_suit_icon_cache.get(fig_suit_lower)
            pwr_txt = self.font_small.render(str(fig_power), True, (255, 255, 255))

            ico_w = (suit_ico.get_width() + 3) if suit_ico else 0
            info_w = ico_w + pwr_txt.get_width() + 8
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
        cx = settings.TOTAL_CIRCLE_X
        cy = settings.TOTAL_CIRCLE_Y
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
        cx = settings.TURN_INDICATOR_X
        ty = settings.TURN_INDICATOR_Y

        if self._all_moves_played():
            # ─── render a clickable "finish!" button ───
            btn_w = int(0.10 * settings.SCREEN_WIDTH)
            btn_h = int(0.045 * settings.SCREEN_HEIGHT)
            btn_rect = pygame.Rect(cx - btn_w // 2, ty, btn_w, btn_h)
            self._finish_btn_rect = btn_rect

            mx, my = pygame.mouse.get_pos()
            self._finish_btn_hovered = btn_rect.collidepoint(mx, my)

            bg_color = (200, 170, 60) if self._finish_btn_hovered else (180, 140, 40)
            pygame.draw.rect(self.window, bg_color, btn_rect, border_radius=6)
            pygame.draw.rect(self.window, (250, 221, 0), btn_rect, 2, border_radius=6)

            txt = self.font_turn.render("finish!", True, (40, 20, 5))
            self.window.blit(txt, txt.get_rect(center=btn_rect.center))

            if self._finish_btn_hovered:
                pygame.mouse.set_cursor(pygame.SYSTEM_CURSOR_HAND)
        else:
            self._finish_btn_rect = None
            self._finish_btn_hovered = False

            if self.is_player_turn:
                text = "Your turn — select a battle move!"
                color = settings.TURN_YOUR_COLOR
            else:
                opp_name = self.game.opponent_name or "Opponent"
                text = f"Waiting for {opp_name}..."
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
