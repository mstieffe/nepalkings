# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Battle Shop screen — buy and return battle moves."""

import pygame
from pygame.locals import *
from config import settings
from game.core.figure_buffs import buffs_allies_bonus_for, buffs_allies_sources
from game.core.input_state import get_pressed as _get_pressed
from game.screens.sub_screen import SubScreen
from game.components.battle_moves.battle_move_manager import BattleMoveManager
from game.components.battle_moves.battle_move import BattleMove
from game.components.battle_moves.battle_move_detail_box import BattleMoveDetailBox
from game.components.battle_moves.battle_move_icon_renderer import draw_battle_move_icon
from game.components.figures.figure_manager import FigureManager
from game.components.cards.card import Card
from game.components.buttons.confirm_button import ConfirmButton
from game.components.floating_text import FloatingText, FloatingTextLayer
from game.components.picker_ui import (
    draw_empty_detail,
    draw_footer,
    footer_button_geometry,
    footer_rect,
)
from utils import battle_shop_service
import logging

logger = logging.getLogger('nk.screens.battle_shop')


def _is_kingdom_config_mode(mode):
    return mode in ('conquer', 'defence', 'defence_draft')


def _kingdom_mode_path(mode):
    return 'defence/draft' if mode == 'defence_draft' else mode



class BattleShopScreen(SubScreen):
    """Screen for purchasing and returning battle moves.

    Players can buy up to 3 battle moves (each requires one card).
    Buying / returning is NOT a turn action.
    """

    def __init__(self, window, state, x: int = 0.0, y: int = 0.0, title=None,
                 card_source=None, mode='duel'):
        super().__init__(window, state.game, x, y, title)
        self.state = state
        self.game = state.game

        from game.core.card_source import GameCardSource
        self.card_source = card_source or GameCardSource(self.game)
        self.mode = mode
        self._initial_family_selected = False
        self.title = {
            'duel': 'Choose Battle Moves · Duel',
            'conquer_battle': 'Choose Battle Moves · Conquer',
            'conquer': 'Starting Tactics · Attack Setup',
            'defence': 'Starting Tactics · Defence Setup',
            'defence_draft': 'Starting Tactics · Defence Setup',
        }.get(self.mode, title or 'Choose Battle Moves')

        # Manager
        self.battle_move_manager = BattleMoveManager()
        self.figure_manager = FigureManager()

        # Cached player figures for Call-move figure selection
        self._player_figures = []
        self._resources_data = None
        self._figures_loaded_game_key = None

        # UI init
        self.init_info_box()
        self.init_move_family_icons()
        self.init_scroll_test_list_shifter()

        self.selected_family = None
        self.selected_moves = []

        # Bought moves (loaded from server)
        self.bought_moves = []  # List of server dicts
        self._loaded_game_key = None  # Track (game_id, player_id) for identity reloads
        self._loaded_bought_moves_key = None  # Track server data version for live move reloads
        self._load_bought_moves()

        # Slot rendering
        self.slot_font = settings.get_font(settings.BATTLE_SHOP_TYPE_LABEL_FONT_SIZE, bold=True)
        self.slot_label_font = settings.get_font(settings.BATTLE_SHOP_TYPE_LABEL_FONT_SIZE, bold=True)

        # Slot hover state
        self._hovered_slot = None  # Index of currently hovered slot (or None)
        self._slot_remove_rects = {}
        self._replace_after_return = False

        # Confirm button
        action_label = (
            'Add Tactic'
            if _is_kingdom_config_mode(self.mode)
            else 'Add Move')
        bx, by, bw, bh = footer_button_geometry(
            self, action_label, align='left')
        self.confirm_button = ConfirmButton(
            self.window,
            bx, by, action_label, width=bw, height=bh,
        )

        # Floating text layer (buy feedback, similar to collect in kingdom config)
        self._floating_text = FloatingTextLayer()
        self._last_render_ms = pygame.time.get_ticks()

        # Pending action state
        self._pending_buy_move = None
        self._pending_return_index = None

        # Battle move detail box (shown when clicking a bought slot)
        self.battle_move_detail_box = None

        # Suit icon cache
        self._suit_icon_cache = {}

        # Slot glow/frame cache
        self._slot_glow_cache = {}
        self._slot_frame_cache = {}
        self._slot_icon_cache = {}
        self._init_slot_glow_frames()
        self._init_slot_rotated_bg()

        # --- Battle moves phase (mandatory selection before battle) ---
        self._battle_moves_confirmed = False  # This player confirmed
        self._waiting_for_opponent = False

        ready_label = (
            'Ready for Battle'
            if not _is_kingdom_config_mode(self.mode)
            else 'Done')
        rx, ry, rw, rh = footer_button_geometry(
            self, ready_label, align='right')
        self.ready_button = ConfirmButton(
            self.window,
            rx, ry, ready_label, width=rw, height=rh,
        )
        self._config_ready_pressed = False
        self.phase_banner_font = settings.get_font(settings.BATTLE_SHOP_PHASE_BANNER_FONT_SIZE, bold=True)
        self._phase_banner_rect = None

    def reset_state(self):
        """Reset all game-specific transient state.

        Called by GameScreen._reset_game_screen_state() when switching games.
        """
        self.selected_family = None
        self.selected_moves = []
        self.bought_moves = []
        self._loaded_game_key = None
        self._loaded_bought_moves_key = None
        self._figures_loaded_game_key = None
        self._player_figures = []
        self._resources_data = None
        self._hovered_slot = None
        self._pending_buy_move = None
        self._pending_return_index = None
        self.battle_move_detail_box = None
        self.dialogue_box = None
        self._battle_moves_confirmed = False
        self._waiting_for_opponent = False
        self._config_ready_pressed = False
        self._initial_family_selected = False
        self._slot_remove_rects = {}
        self._replace_after_return = False
        logger.debug("[BattleShop] State reset for game switch")

    @property
    def _is_locked(self):
        """True when battle moves must not be changed (confirmed or battle active).

        During the battle-moves selection phase (battle_confirmed but moves not
        yet confirmed) the shop must remain open for buying/returning.
        """
        if getattr(self, '_battle_moves_confirmed', False):
            return True
        # If we're still in the selection phase, don't lock
        if getattr(self.game, 'battle_moves_phase', False):
            return False
        return getattr(self.game, 'battle_confirmed', False)

    def _init_slot_glow_frames(self):
        """Load and cache glow/frame images for bought-move slot rendering.

        Creates normal and big (hover) variants of glows, icons, and frames.
        """
        gw = settings.BATTLE_SHOP_SLOT_GLOW_WIDTH
        big_scale = 1.25
        gw_big = int(gw * big_scale)

        green = pygame.image.load('img/game_button/glow/green.png').convert_alpha()
        blue = pygame.image.load('img/game_button/glow/blue.png').convert_alpha()
        yellow = pygame.image.load('img/game_button/glow/yellow.png').convert_alpha()

        self._slot_glow_cache['green'] = pygame.transform.smoothscale(green, (gw, gw))
        self._slot_glow_cache['blue'] = pygame.transform.smoothscale(blue, (gw, gw))
        self._slot_glow_cache['green_big'] = pygame.transform.smoothscale(green, (gw_big, gw_big))
        self._slot_glow_cache['blue_big'] = pygame.transform.smoothscale(blue, (gw_big, gw_big))
        self._slot_glow_cache['yellow_big'] = pygame.transform.smoothscale(yellow, (gw_big, gw_big))

        # Suit icons for slots (normal + big hover variants)
        suit_icon_s = int(settings.SUIT_ICON_WIDTH * 0.6)
        suit_icon_s_big = int(suit_icon_s * big_scale)
        for suit_name in ('hearts', 'diamonds', 'spades', 'clubs'):
            suit_path = settings.SUIT_ICON_IMG_PATH + suit_name + '.png'
            try:
                raw_suit = pygame.image.load(suit_path).convert_alpha()
                self._suit_icon_cache[suit_name] = pygame.transform.smoothscale(raw_suit, (suit_icon_s, suit_icon_s))
                self._suit_icon_cache[suit_name + '_big'] = pygame.transform.smoothscale(raw_suit, (suit_icon_s_big, suit_icon_s_big))
            except Exception:
                pass

        # Frame image for slots — shared across all families
        sw = settings.BATTLE_SHOP_SLOT_WIDTH
        sh = settings.BATTLE_SHOP_SLOT_HEIGHT
        frame_w = int(sw * settings.BATTLE_SHOP_SLOT_FRAME_SCALE)
        frame_h = int(sh * settings.BATTLE_SHOP_SLOT_FRAME_SCALE)
        frame_w_big = int(frame_w * big_scale)
        frame_h_big = int(frame_h * big_scale)
        icon_w = sw - 8
        icon_h = sh - 8
        icon_w_big = int(icon_w * big_scale)
        icon_h_big = int(icon_h * big_scale)

        # Pre-scale frames and icons per family (normal + big)
        for family in self.battle_move_manager.families:
            if family.frame_img:
                raw = family.frame_img.convert_alpha()
                self._slot_frame_cache[family.name] = pygame.transform.smoothscale(raw, (frame_w, frame_h))
                self._slot_frame_cache[family.name + '_big'] = pygame.transform.smoothscale(raw, (frame_w_big, frame_h_big))
            if family.icon_img:
                raw = family.icon_img.convert_alpha()
                self._slot_icon_cache[family.name] = pygame.transform.smoothscale(raw, (icon_w, icon_h))
                self._slot_icon_cache[family.name + '_big'] = pygame.transform.smoothscale(raw, (icon_w_big, icon_h_big))

        # Also cache hidden families (e.g. Double Dagger) for rendering existing moves
        for name, family in self.battle_move_manager.families_by_name.items():
            if name not in self._slot_frame_cache and family.frame_img:
                raw = family.frame_img.convert_alpha()
                self._slot_frame_cache[name] = pygame.transform.smoothscale(raw, (frame_w, frame_h))
                self._slot_frame_cache[name + '_big'] = pygame.transform.smoothscale(raw, (frame_w_big, frame_h_big))
            if name not in self._slot_icon_cache and family.icon_img:
                raw = family.icon_img.convert_alpha()
                self._slot_icon_cache[name] = pygame.transform.smoothscale(raw, (icon_w, icon_h))
                self._slot_icon_cache[name + '_big'] = pygame.transform.smoothscale(raw, (icon_w_big, icon_h_big))

    def _init_slot_rotated_bg(self):
        """Create rotated (45°) diamond-shaped slot background surface."""
        sw = settings.BATTLE_SHOP_SLOT_WIDTH
        sh = settings.BATTLE_SHOP_SLOT_HEIGHT
        # Draw a filled square, then rotate 45° to get a diamond
        base = pygame.Surface((sw, sh), pygame.SRCALPHA)
        base.fill(settings.BATTLE_SHOP_SLOT_BG_COLOR)
        pygame.draw.rect(base, settings.BATTLE_SHOP_SLOT_BORDER_COLOR, (0, 0, sw, sh), 2)
        self._slot_diamond = pygame.transform.rotate(base, 45)

    # ---------------------------------------------------------------- init helpers
    def init_info_box(self):
        super().init_sub_box_background(
            settings.BATTLE_SHOP_INFO_BOX_X,
            settings.BATTLE_SHOP_INFO_BOX_Y,
            settings.BATTLE_SHOP_INFO_BOX_WIDTH,
            settings.BATTLE_SHOP_INFO_BOX_HEIGHT,
        )
        super().init_scroll_background(
            settings.BATTLE_SHOP_INFO_BOX_SCROLL_X,
            settings.BATTLE_SHOP_INFO_BOX_SCROLL_Y,
            settings.BATTLE_SHOP_INFO_BOX_SCROLL_WIDTH,
            settings.BATTLE_SHOP_INFO_BOX_SCROLL_HEIGHT,
        )

    def init_scroll_test_list_shifter(self):
        self.make_scroll_text_list_shifter(
            self.scroll_text_list,
            settings.BATTLE_SHOP_SCROLL_TEXT_X,
            settings.BATTLE_SHOP_SCROLL_TEXT_Y,
            scroll_height=settings.BATTLE_SHOP_INFO_BOX_SCROLL_HEIGHT,
        )

    def init_move_family_icons(self):
        """Create one icon button per battle-move family, laid out in a single row."""
        self.move_family_buttons = []
        start_x = settings.BATTLE_SHOP_ICON_START_X
        start_y = settings.BATTLE_SHOP_ICON_START_Y
        if settings.TOUCH_TARGET_MIN > 0:
            # Mobile hierarchy: equipped tray first, then the family catalog.
            start_y += int(0.15 * settings.SCREEN_HEIGHT)
        dx = settings.BATTLE_MOVE_ICON_DELTA_X

        for i, family in enumerate(self.battle_move_manager.families):
            icon = family.make_icon(
                self.window, self.game,
                self._sx(start_x + i * dx),
                self._sy(start_y),
            )
            self.move_family_buttons.append(icon)

    # ----------------------------------------------------------- data helpers
    def _load_bought_moves(self):
        """Fetch bought battle moves from server."""
        if _is_kingdom_config_mode(self.mode):
            # In kingdom mode, moves come from the config
            if self.game:
                self.bought_moves = self.game._config.get('battle_moves', [])
                self._loaded_game_key = self._game_identity_key(self.game)
                self._loaded_bought_moves_key = self._bought_moves_cache_key(self.game)
            return
        if not self.game:
            return
        try:
            result = battle_shop_service.get_battle_moves(
                self.game.game_id, self.game.player_id
            )
            self.bought_moves = result.get('battle_moves', [])
            self._loaded_game_key = self._game_identity_key(self.game)
            self._loaded_bought_moves_key = self._bought_moves_cache_key(self.game)
        except Exception as e:
            logger.error(f"[BattleShop] Failed to load bought moves: {e}")
            self.bought_moves = []

    def _game_identity_key(self, game):
        return (getattr(game, 'game_id', None), getattr(game, 'player_id', None))

    def _bought_moves_cache_key(self, game):
        identity = self._game_identity_key(game)
        if _is_kingdom_config_mode(self.mode):
            return identity
        return (*identity, getattr(game, '_game_data_version', 0))

    def _should_reload_bought_moves(self, game):
        current_key = self._bought_moves_cache_key(game)
        return bool(current_key[0] and current_key != self._loaded_bought_moves_key)

    def _get_bought_card_ids(self):
        """Set of card IDs already reserved for battle moves."""
        return {m['card_id'] for m in self.bought_moves}

    def _get_hand_cards(self):
        """Get all cards currently in the player's hand (excluding battle-move cards)."""
        main, side = self.card_source.get_cards()
        return main + side

    def _required_battle_move_count(self):
        """How many moves must be confirmed right now.

        Duel normally requires all 3 moves.  If no more buyable moves are
        available (rare exhausted-deck/hand case), the player can ready with
        all moves currently selected.
        """
        max_moves = settings.BATTLE_SHOP_MAX_MOVES
        if _is_kingdom_config_mode(self.mode):
            return min(max_moves, len(self.bought_moves))
        hand = self._get_hand_cards()
        bought_ids = self._get_bought_card_ids()
        available = self.battle_move_manager.get_available_moves(hand, bought_ids)
        available_card_ids = {
            move.card.id
            for moves in available.values()
            for move in moves
            if getattr(move, 'card', None) is not None
        }
        return min(max_moves, len(self.bought_moves) + len(available_card_ids))

    def _can_ready_for_battle(self):
        if _is_kingdom_config_mode(self.mode):
            return len(self.bought_moves) >= settings.BATTLE_SHOP_MAX_MOVES
        required = self._required_battle_move_count()
        return len(self.bought_moves) >= required

    def has_available_battle_move_changes(self):
        """Return True when the hand offers a new battle-move card.

        Conquer battles arrive with preconfigured battle moves.  The shop is
        only useful during the pre-battle window if a newly drawn/unreserved
        hand card can actually become a move; otherwise the player can only
        press Ready and the conquer shell may skip the shop entirely.
        """
        hand = self._get_hand_cards()
        bought_ids = self._get_bought_card_ids()
        available = self.battle_move_manager.get_available_moves(hand, bought_ids)
        return any(bool(moves) for moves in available.values())

    def _rebuild_card_source_kingdom(self):
        """Re-fetch collection and rebuild the card source for kingdom mode."""
        from utils import collection_service
        from game.core.card_source import CollectionCardSource
        try:
            data = collection_service.fetch_collection_cards()
        except Exception as e:
            logger.error(f'Failed to re-fetch collection: {e}')
            return
        config = getattr(self.game, '_config', None) or {}
        cards = []
        for c in data.get('cards', []):
            qty = c.get('free', c.get('total', 0))
            for i in range(qty):
                cards.append(Card(
                    rank=c['rank'], suit=c['suit'],
                    value=settings.RANK_TO_VALUE.get(c['rank'], 0),
                    id=c.get('id', hash((c['suit'], c['rank'], i))),
                    type='main' if c['rank'] in settings.RANKS_MAIN_CARDS else 'side_card',
                ))
        locked_ids = set()
        for fig in config.get('figures', []):
            for cid in fig.get('card_ids', []):
                locked_ids.add(cid)
        for mv in config.get('battle_moves', []):
            if mv.get('card_id'):
                locked_ids.add(mv['card_id'])
        if config.get('modifier_card_ids'):
            for cid in config['modifier_card_ids']:
                locked_ids.add(cid)
        if config.get('spell_card_ids'):
            for cid in config['spell_card_ids']:
                locked_ids.add(cid)
        self.card_source = CollectionCardSource(cards, config.get('figures', []), locked_ids)

    def _sync_card_source_locked(self):
        """Update the card source's locked set from the current config."""
        if not hasattr(self.card_source, '_locked') or not self.game:
            return
        config = getattr(self.game, '_config', None)
        if not config:
            return
        locked = set()
        for fig in config.get('figures', []):
            for cid in fig.get('card_ids', []):
                locked.add(cid)
        for mv in config.get('battle_moves', []):
            if mv.get('card_id'):
                locked.add(mv['card_id'])
        if config.get('modifier_card_ids'):
            for cid in config['modifier_card_ids']:
                locked.add(cid)
        if config.get('spell_card_ids'):
            for cid in config['spell_card_ids']:
                locked.add(cid)
        self.card_source._locked = locked

    # ---------------------------------------------------------------- update
    def update(self, game):
        super().update(game)
        self.game = game
        # Keep card_source in sync for GameCardSource (duel mode)
        if hasattr(self.card_source, 'game'):
            self.card_source.game = game

        # Reload bought moves when the game changes (e.g. loading a saved game)
        current_key = self._game_identity_key(game)
        if current_key[0] and current_key != self._loaded_game_key:
            self._load_bought_moves()
            self._load_player_figures()
        elif self._should_reload_bought_moves(game):
            self._load_bought_moves()

        in_phase = getattr(game, 'battle_moves_phase', False)
        in_config = _is_kingdom_config_mode(self.mode)

        # Reset confirmed state when no longer in battle at all
        battle_active = getattr(game, 'battle_confirmed', False) or in_phase
        if not battle_active:
            self._battle_moves_confirmed = False
            self._waiting_for_opponent = False

        # --- Buy button logic (only visible outside mandatory phase) ---
        self.confirm_button.disabled = False
        if len(self.bought_moves) >= settings.BATTLE_SHOP_MAX_MOVES:
            self.confirm_button.disabled = True

        # --- Ready button logic (only during mandatory phase) ---
        self.ready_button.disabled = True
        self.ready_button.active = False
        if in_config:
            self.ready_button.disabled = not self._can_ready_for_battle()
            self.ready_button.active = not self.ready_button.disabled
        elif in_phase and not self._battle_moves_confirmed:
            if self._can_ready_for_battle():
                self.ready_button.disabled = False
                self.ready_button.active = True

        # Update icon active states based on available cards
        self._update_icon_states()
        if settings.TOUCH_TARGET_MIN > 0 and not self._initial_family_selected:
            chosen = next(
                (button for button in self.move_family_buttons
                 if button.is_active),
                self.move_family_buttons[0] if self.move_family_buttons else None,
            )
            if chosen is not None:
                self._on_family_clicked(chosen)
                self._initial_family_selected = True

        for btn in self.move_family_buttons:
            btn.update()

        if self.scroll_text_list_shifter:
            selected = self.scroll_text_list_shifter.get_current_selected()
            if selected:
                self.confirm_button.update()

        if in_phase or in_config:
            self.ready_button.update()
            if in_config and not self.ready_button.disabled:
                self.ready_button.active = not getattr(
                    self.ready_button, 'hovered', False)

    def _ready_button_hit(self, pos=None):
        if pos is not None:
            pad = getattr(self.ready_button, 'hit_pad', 0)
            hit = self.ready_button.rect.inflate(
                2 * pad, 2 * pad) if pad else self.ready_button.rect
            return hit.collidepoint(pos)
        return self.ready_button.collide()

    def _update_icon_states(self):
        """Set is_active on each family icon based on whether the player has matching cards."""
        hand = self._get_hand_cards()
        bought_ids = self._get_bought_card_ids()
        available = self.battle_move_manager.get_available_moves(hand, bought_ids)

        for btn in self.move_family_buttons:
            btn.is_active = btn.family.name in available

    def _update_glow_colors(self):
        """Set glow color: selected icon gets suit color (green/blue), white if no cards, gold otherwise."""
        if not self.scroll_text_list_shifter:
            return

        # Determine suit-based mode for the selected family icon
        suit_mode = None
        current = self.scroll_text_list_shifter.get_current_selected()
        if current is not None and hasattr(current, 'suit') and current.suit:
            suit = current.suit
            suit_mode = 'green' if suit in ('Hearts', 'Diamonds') else 'blue'
        elif self.selected_family is not None:
            # Family selected but no matching cards — use white glow
            if not self.selected_moves:
                suit_mode = 'white'
            else:
                # Has moves but no specific card shown yet — default to green
                suit_mode = 'green'

        for btn in self.move_family_buttons:
            if btn.clicked and self.selected_family and btn.family.name == self.selected_family.name:
                btn.set_glow_mode(suit_mode if suit_mode else 'gold')
            else:
                btn.set_glow_mode('gold')

    # ---------------------------------------------------------- event handling
    def handle_events(self, events):
        in_phase = getattr(self.game, 'battle_moves_phase', False)
        in_config = _is_kingdom_config_mode(self.mode)
        selected_move = None
        if self.scroll_text_list_shifter:
            selected_move = self.scroll_text_list_shifter.get_current_selected()

        # Overlay input is modal. Handle detail/dialogue controls before the
        # scroll panel, close control, family icons, or equipped slots.
        if self.battle_move_detail_box:
            response = self.battle_move_detail_box.handle_events(events)
            if response:
                if response == 'close':
                    self.battle_move_detail_box = None
                elif response == 'return':
                    # Block returning moves once confirmed or battle active
                    if self._is_locked:
                        self.battle_move_detail_box = None
                    else:
                        self._return_detail_box_move()
                elif response == 'replace':
                    if self._is_locked:
                        self.battle_move_detail_box = None
                    else:
                        self._replace_after_return = True
                        self._return_detail_box_move()
            return

        if self.dialogue_box:
            response = self.dialogue_box.update(events)
            if response:
                if response == 'yes':
                    if not self._is_locked:
                        self._buy_current_move()
                    self.dialogue_box = None
                elif response == 'return':
                    if not self._is_locked:
                        self._return_current_slot_move()
                    self.dialogue_box = None
                elif response in ('ok', 'cancel', 'got it!'):
                    self.dialogue_box = None
            return

        super().handle_events(events)

        for event in events:
            if event.type == MOUSEBUTTONDOWN:
                if (not self._is_locked
                        and self._handle_slot_remove_click(event.pos)):
                    continue

                # Family icon clicks
                for btn in self.move_family_buttons:
                    if btn.collide():
                        self._on_family_clicked(btn)

                # Buy confirm button (only outside mandatory phase or when slots not full)
                if (selected_move and
                        self.confirm_button.collide() and
                        not self.confirm_button.disabled and
                        not self._is_locked):
                    self._on_confirm(selected_move)

                # Ready button (battle moves phase only)
                if (in_phase and
                        not self._is_locked and
                        not self.ready_button.disabled and
                        self._ready_button_hit(event.pos)):
                    self._on_ready_confirm()
                    continue

                # Ready button for kingdom conquer/defence config shops.
                # Close on mouse-up below so the release event is still
                # consumed by this subscreen and cannot open a config action
                # sitting underneath it.
                if (in_config and
                        not self.ready_button.disabled and
                        self._ready_button_hit(event.pos)):
                    self._config_ready_pressed = True
                    continue

                # Slot clicks (open detail box — return blocked if locked)
                if not self._is_locked:
                    self._handle_slot_click(event)

            elif event.type == MOUSEBUTTONUP and event.button == 1:
                config_ready_pressed = bool(getattr(self, '_config_ready_pressed', False))
                self._config_ready_pressed = False
                if (in_config and
                        config_ready_pressed and
                        not self.ready_button.disabled and
                        self._ready_button_hit(event.pos)):
                    self._on_config_ready()
                    continue

        # Update glow colors after events so scroll changes take effect immediately
        self._update_glow_colors()

    def _on_family_clicked(self, btn):
        """When a family icon is clicked, populate the scroll list with available moves."""
        self.selected_family = btn.family

        # Deselect all other icons
        for other in self.move_family_buttons:
            other.clicked = False
        btn.clicked = True

        # Get available moves for this family
        hand = self._get_hand_cards()
        bought_ids = self._get_bought_card_ids()
        available = self.battle_move_manager.get_available_moves(hand, bought_ids)
        moves = available.get(btn.family.name, [])

        if moves:
            self.selected_moves = moves
            self.scroll_text_list = [
                {
                    "title": f"{move.family.name}",
                    "text": move.family.description,
                    "cards": [move.card],
                    "power": move.value,
                    "battle_move_suit": move.suit,
                    "content": move,
                }
                for move in moves
            ]
        else:
            self.selected_moves = []
            self.scroll_text_list = [
                {
                    "title": btn.family.name,
                    "text": btn.family.description + "\n\nNo matching cards in hand.",
                    "availability_reason": "No matching cards available.",
                    "content": None,
                }
            ]

        self.scroll_text_list_shifter.set_displayed_texts(self.scroll_text_list)

        # Immediately update glow so it reflects the first item's suit
        self._update_glow_colors()

    def _slot_top_y(self):
        if settings.TOUCH_TARGET_MIN > 0:
            return self._sy(
                settings.BATTLE_SHOP_INFO_BOX_Y
                + int(0.08 * settings.SCREEN_HEIGHT))
        return self._sy(settings.BATTLE_SHOP_SLOT_Y)

    def _on_confirm(self, move):
        """Show buy confirmation dialogue."""
        if len(self.bought_moves) >= settings.BATTLE_SHOP_MAX_MOVES:
            self.make_dialogue_box(
                message=f"You can only buy {settings.BATTLE_SHOP_MAX_MOVES} battle moves.",
                actions=['ok'],
                icon="error",
                title="Slots Full",
            )
            return

        # Build card preview
        card_img = move.card.make_icon(self.window, self.game, 0, 0)
        images = [card_img.front_img] if hasattr(card_img, 'front_img') else []

        self.make_dialogue_box(
            message=(
                f"Add {move.family.name} "
                f"({move.suit}, value {move.value})?"
            ),
            actions=['yes', 'cancel'],
            images=images,
            icon="question",
            title="Add Battle Move",
        )
        self._pending_buy_move = move

    def _buy_current_move(self):
        """Actually purchase the pending move via the server."""
        if getattr(self.game, 'game_over', False):
            self.dialogue_box = None
            return
        move = self._pending_buy_move
        if not move:
            self.dialogue_box = None
            return

        card_type = 'side' if move.card.type == 'side_card' else 'main'

        if _is_kingdom_config_mode(self.mode):
            result = self._buy_move_kingdom(move, card_type)
        else:
            result = battle_shop_service.buy_battle_move(
                game_id=self.game.game_id,
                player_id=self.game.player_id,
                family_name=move.family.name,
                card_id=move.card.id,
                card_type=card_type,
                suit=move.suit,
                rank=move.rank,
                value=move.value,
            )

        if result.get('success'):
            from utils import sound
            sound.play('card_place')
            if self.mode == 'duel':
                sound.play('coin', volume=0.6)
            fx = self._fx_layer()
            if fx is not None:
                fx.spawn_burst(pygame.Rect(self.confirm_button.rect),
                               (238, 206, 130), secondary=(255, 245, 200),
                               count=16, upward_bias=0.6)
            if result.get('game'):
                self.game.update_from_dict(result['game'])
            self._load_bought_moves()

            # Rebuild card source for kingdom mode (re-fetch free counts)
            if _is_kingdom_config_mode(self.mode):
                self._rebuild_card_source_kingdom()
            else:
                self._sync_card_source_locked()

            # Refresh the scroll list for the selected family
            if self.selected_family:
                for btn in self.move_family_buttons:
                    if btn.family.name == self.selected_family.name:
                        self._on_family_clicked(btn)
                        btn.clicked = True
                        break

            self.make_dialogue_box(
                message=f"{move.family.name} added!",
                actions=['ok'],
                icon="figure",
                title="Battle Move Added",
            )
            self._spawn_buy_floater(move)
            callback = getattr(self, '_on_move_bought', None)
            if callable(callback):
                callback()
            if self.mode == 'duel':
                parent = getattr(self.state, 'parent_screen', None)
                marker = getattr(parent, '_mark_duel_coach_seen', None)
                if callable(marker):
                    marker('battle_shop_select_moves')
        else:
            self.make_dialogue_box(
                message=f"Failed: {result.get('message', 'Unknown error')}",
                actions=['ok'],
                icon="error",
                title="Purchase Failed",
            )

        self._pending_buy_move = None

    def _spawn_buy_floater(self, move):
        """Spawn a rising '+MoveName' floater from the buy button (like collect in kingdom config)."""
        font = settings.get_font(settings.COLLECT_FLOAT_FONT_SIZE, bold=True)
        self._floating_text.add(FloatingText(
            f'+{move.family.name}',
            self.confirm_button.rect.center,
            color=settings.COLLECT_FLOAT_GOLD_CLR,
            duration_ms=settings.COLLECT_FLOAT_DURATION_MS,
            rise_px=settings.COLLECT_FLOAT_RISE_PX,
            font=font,
        ))

    def _buy_move_kingdom(self, move, card_type):
        """Buy a battle move via the kingdom config endpoint."""
        from utils import http_compat as requests
        land_id = getattr(self.game, 'land_id', None)

        # Auto-assign the next free round_index (0, 1, or 2)
        used_indices = {m.get('round_index') for m in self.bought_moves}
        round_index = None
        for idx in (0, 1, 2):
            if idx not in used_indices:
                round_index = idx
                break
        if round_index is None:
            return {'success': False, 'message': 'All 3 move slots are full'}

        try:
            resp = requests.post(
                f'{settings.SERVER_URL}/kingdom/{_kingdom_mode_path(self.mode)}/buy_battle_move',
                json={
                    'land_id': land_id,
                    'family_name': move.family.name,
                    'card_id': 0,
                    'card_type': card_type,
                    'suit': move.suit,
                    'rank': move.rank,
                    'value': move.value,
                    'round_index': round_index,
                },
                timeout=15,
            )
            result = resp.json()
            if result.get('success') and result.get('config'):
                self.game.set_config(result['config'])
            return result
        except Exception as e:
            logger.error(f'Kingdom buy_battle_move error: {e}')
            return {'success': False, 'message': 'Connection error'}

    def _handle_slot_click(self, event):
        """Check if the player clicked on a bought-move slot to open its detail box."""
        mx, my = event.pos
        sw = settings.BATTLE_SHOP_SLOT_WIDTH
        sh = settings.BATTLE_SHOP_SLOT_HEIGHT
        delta_x = settings.BATTLE_SHOP_SLOT_DELTA_X
        max_moves = settings.BATTLE_SHOP_MAX_MOVES

        # Use same centred positions as _draw_bought_slots
        footer = footer_rect(self)
        box_cx = footer.centerx
        total_span = (max_moves - 1) * delta_x + sw
        slot_start_x = box_cx - total_span // 2
        sy = self._slot_top_y()

        for i in range(max_moves):
            sx = slot_start_x + i * delta_x
            cx = sx + sw // 2
            cy = sy + sh // 2
            # Diamond hit: |dx|/hw + |dy|/hh <= 1
            hw = sw * 0.7  # rotated diamond is wider
            hh = sh * 0.7
            if abs(mx - cx) / hw + abs(my - cy) / hh <= 1.0:
                if i < len(self.bought_moves):
                    bm = self.bought_moves[i]
                    self._pending_return_index = i
                    eligible = self._get_eligible_figures_for_move(bm)
                    self.battle_move_detail_box = BattleMoveDetailBox(
                        self.window, bm,
                        self.battle_move_manager.families_by_name,
                        self.game,
                        eligible_figures=eligible,
                        figure_power_bonuses=self._figure_power_bonuses(),
                    )
                break

    def _return_detail_box_move(self):
        """Return a battle move via the detail box's Return button."""
        self.battle_move_detail_box = None
        self._return_current_slot_move()

    # ──────────────── figure helpers for Call detail boxes ──────────────

    _CALL_FIELD_MAP = {
        'Call Villager': 'village',
        'Call Military': 'military',
        'Call King': 'castle',
    }
    _RED_SUITS = {'Hearts', 'Diamonds'}
    _BLACK_SUITS = {'Clubs', 'Spades'}

    def _load_player_figures(self):
        """Load all player figures + resource data for Call-move eligibility."""
        try:
            families = self.figure_manager.families
            self._player_figures = self.card_source.get_figures(families, is_opponent=False)
            self._resources_data = self.game.calculate_resources(families, is_opponent=False)
            self._figures_loaded_game_key = (getattr(self.game, 'game_id', None),
                                              getattr(self.game, 'player_id', None),
                                              getattr(self.game, '_figures_data_version', 0))
        except Exception as e:
            logger.error(f"[BattleShop] Failed to load player figures: {e}")
            self._player_figures = []
            self._resources_data = None

    def _get_eligible_figures_for_move(self, bm):
        """Return figures eligible for a Call battle move.

        Filters by field type, suit colour (red→red, black→black),
        cannot_be_targeted, fighting status, and resource deficit.
        """
        family_name = bm.get('family_name', '')
        field_type = self._CALL_FIELD_MAP.get(family_name)
        if not field_type:
            return []

        # Ensure figures are loaded (re-fetches when background poller updates figure data)
        if not self._player_figures or self._figures_loaded_game_key != (getattr(self.game, 'game_id', None), getattr(self.game, 'player_id', None), getattr(self.game, '_figures_data_version', 0)):
            self._load_player_figures()

        bm_suit = bm.get('suit', '')
        bm_is_red = bm_suit in self._RED_SUITS

        # IDs of figures already in battle
        fighting_ids = self._fighting_figure_ids()

        eligible = []
        for fig in self._player_figures:
            if not hasattr(fig.family, 'field') or fig.family.field != field_type:
                continue
            if getattr(fig, 'cannot_be_targeted', False):
                continue
            if fig.id in fighting_ids:
                continue
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

    def _get_display_power(self, bm):
        """Return the power to display for a battle move icon.

        For Call moves the value is the maximum combined power
        (figure base + healer buff + move bonus if suit matches) across all
        eligible figures.  For other moves the raw move value is shown.
        """
        family_name = bm.get('family_name', '')
        bm_suit = bm.get('suit', '')
        bm_value = bm.get('value', 0)

        # Block always has power 0
        if family_name == 'Block':
            return 0

        if family_name not in self._CALL_FIELD_MAP:
            return bm_value

        eligible = self._get_eligible_figures_for_move(bm)
        if not eligible:
            return bm_value

        fighting_ids = self._fighting_figure_ids()
        healers = buffs_allies_sources(
            self._player_figures,
            has_deficit=self._figure_has_deficit,
            exclude_ids=fighting_ids,
        )

        max_power = 0
        for fig in eligible:
            base = fig.get_value()
            healer_bonus = buffs_allies_bonus_for(fig, healers)
            bonus = bm_value if fig.suit == bm_suit else 0
            total = base + healer_bonus + bonus
            if total > max_power:
                max_power = total
        return max_power

    def _figure_power_bonuses(self):
        fighting_ids = self._fighting_figure_ids()
        healers = buffs_allies_sources(
            self._player_figures,
            has_deficit=self._figure_has_deficit,
            exclude_ids=fighting_ids,
        )
        return {
            fig.id: buffs_allies_bonus_for(fig, healers)
            for fig in self._player_figures
        }

    def _fighting_figure_ids(self):
        """Return figure IDs currently committed as active battle figures."""
        fighting_ids = set()
        for attr in ('advancing_figure_id', 'advancing_figure_id_2',
                     'defending_figure_id', 'defending_figure_id_2'):
            fid = getattr(self.game, attr, None)
            if fid is not None:
                fighting_ids.add(fid)
        return fighting_ids

    def _return_current_slot_move(self):
        """Return a battle move from the slot."""
        if getattr(self.game, 'game_over', False):
            self.dialogue_box = None
            return
        idx = self._pending_return_index
        if idx is None or idx >= len(self.bought_moves):
            self.dialogue_box = None
            return

        bm = self.bought_moves[idx]

        if _is_kingdom_config_mode(self.mode):
            from utils import http_compat as requests
            try:
                resp = requests.post(
                    f'{settings.SERVER_URL}/kingdom/{_kingdom_mode_path(self.mode)}/return_battle_move',
                    json={'move_id': bm['id']},
                    timeout=10,
                )
                result = resp.json()
                if result.get('success') and result.get('config'):
                    self.game.set_config(result['config'])
            except Exception as e:
                logger.error(f'Kingdom return_battle_move error: {e}')
                result = {'success': False, 'message': 'Connection error'}
        else:
            result = battle_shop_service.return_battle_move(
                game_id=self.game.game_id,
                player_id=self.game.player_id,
                battle_move_id=bm['id'],
            )

        if result.get('success'):
            from utils import sound
            sound.play('card_slide')
            if result.get('game'):
                self.game.update_from_dict(result['game'])
            self._load_bought_moves()

            # Rebuild card source for kingdom mode (re-fetch free counts)
            if _is_kingdom_config_mode(self.mode):
                self._rebuild_card_source_kingdom()
            else:
                self._sync_card_source_locked()

            # Refresh the scroll list
            if self.selected_family:
                for btn in self.move_family_buttons:
                    if btn.family.name == self.selected_family.name:
                        self._on_family_clicked(btn)
                        btn.clicked = True
                        break

            replacing = self._replace_after_return
            self.make_dialogue_box(
                message=(
                    "Slot cleared. Choose and add its replacement."
                    if replacing else
                    "Battle move removed and its card returned."
                ),
                actions=['ok'],
                icon="figure",
                title="Choose Replacement" if replacing else "Move Removed",
            )
        else:
            self.make_dialogue_box(
                message=f"Failed: {result.get('message', 'Unknown error')}",
                actions=['ok'],
                icon="error",
                title="Return Failed",
            )

        self._pending_return_index = None
        self._replace_after_return = False

    def _on_ready_confirm(self):
        """Player confirms all required battle moves — notify server."""
        if getattr(self.game, 'game_over', False):
            return
        if not self._can_ready_for_battle():
            return

        result = battle_shop_service.confirm_battle_moves(
            game_id=self.game.game_id,
            player_id=self.game.player_id,
        )

        if result.get('success'):
            self._battle_moves_confirmed = True
            parent = getattr(self.state, 'parent_screen', None)
            marker = getattr(parent, '_mark_duel_coach_seen', None)
            if callable(marker):
                marker('battle_shop_ready')
            if result.get('game'):
                self.game.update_from_dict(result['game'])

            if result.get('both_ready'):
                # Both players are ready — transition to battle screen
                self.game.both_battle_moves_ready = True
            else:
                # Waiting for opponent
                self._waiting_for_opponent = True
                self.game.waiting_for_opponent_battle_moves = True
        else:
            self.make_dialogue_box(
                message=f"Failed: {result.get('message', 'Unknown error')}",
                actions=['ok'],
                icon="error",
                title="Confirmation Failed",
            )

    def _on_config_ready(self):
        """Return from kingdom config battle shop once all move slots are full."""
        if not self._can_ready_for_battle():
            return False
        if self._on_done:
            self._on_done()
            return True
        return False

    # ------------------------------------------------------------------- draw
    def draw(self):
        super().draw()

        in_phase = getattr(self.game, 'battle_moves_phase', False)
        in_config = _is_kingdom_config_mode(self.mode)
        count = len(self.bought_moves)
        required = self._required_battle_move_count()
        if self._is_locked:
            footer_status = 'Moves locked · waiting for battle'
            footer_tone = 'neutral'
        elif count >= required:
            footer_status = f'{count}/3 selected · configuration ready'
            footer_tone = 'good'
        else:
            footer_status = f'{count}/3 selected · choose {required - count} more'
            footer_tone = 'warning'
        selected = (
            self.scroll_text_list_shifter.get_current_selected()
            if self.scroll_text_list_shifter else None
        )
        show_action = bool(selected and not self._is_locked)
        ready_visible = (
            in_config
            or (
                in_phase
                and not self._is_locked
                and self._can_ready_for_battle()
            )
        )
        draw_footer(
            self.window, self, footer_status, tone=footer_tone,
            show_action=show_action,
            show_status=True,
            reserve_status_right=ready_visible,
        )

        # Family icons
        for btn in self.move_family_buttons:
            btn.draw()

        if not self.scroll_text_list:
            draw_empty_detail(
                self.window,
                pygame.Rect(
                    self.scroll_x, self.scroll_y,
                    self.scroll_w, self.scroll_h),
                'Choose a move',
                'Preview its card, power, effect, and available variants.',
            )

        # Scroll text list + buy confirm button
        if self.scroll_text_list_shifter:
            # Only show buy button when NOT locked (still shopping)
            if selected and not self._is_locked:
                self.confirm_button.draw()

        # Bought-move slots
        self._draw_bought_slots()

        # --- Battle moves phase UI ---
        if in_phase:
            # The shared footer already communicates selection progress. Keep
            # the legacy phase-banner slot empty so status is never rendered
            # twice underneath the action buttons.
            self._phase_banner_rect = None
            if not self._is_locked:
                if self._can_ready_for_battle():
                    self.ready_button.draw()

        if in_config:
            self.ready_button.draw()

        # Detail box on top of everything except dialogue box / msg
        if self.battle_move_detail_box:
            self.battle_move_detail_box.draw()

        # Drive and draw the floating-text layer (buy feedback, like collect in kingdom config).
        now_ms = pygame.time.get_ticks()
        dt_ms = max(0, now_ms - (self._last_render_ms or now_ms))
        self._last_render_ms = now_ms
        self._floating_text.update(dt_ms)
        self._floating_text.draw(self.window)

        super().draw_on_top()

    def _draw_phase_banner(self):
        """Draw a banner indicating the mandatory battle-move selection phase."""
        self._phase_banner_rect = None
        footer = footer_rect(self)
        box_cx = self._sx(settings.BATTLE_SHOP_INFO_BOX_X + settings.BATTLE_SHOP_INFO_BOX_WIDTH // 2)
        count = len(self.bought_moves)
        max_m = settings.BATTLE_SHOP_MAX_MOVES
        required = self._required_battle_move_count()

        if self._waiting_for_opponent:
            text = "Waiting for opponent..."
            color = settings.BATTLE_SHOP_PHASE_WAITING_COLOR
        elif self._is_locked:
            text = "Battle moves confirmed! Waiting for opponent..."
            color = settings.BATTLE_SHOP_PHASE_WAITING_COLOR
        elif count >= required:
            text = "All slots filled — press Ready!" if required >= max_m else "All available moves selected — press Ready!"
            color = settings.BATTLE_SHOP_PHASE_BANNER_COLOR
        else:
            remaining = required - count
            text = f"Select {remaining} more battle move{'s' if remaining > 1 else ''}!"
            color = settings.BATTLE_SHOP_PHASE_BANNER_COLOR

        ready_visible = (
            not self._waiting_for_opponent
            and not self._is_locked
            and count >= required
            and self._can_ready_for_battle()
        )
        banner_font = self.phase_banner_font
        if ready_visible and settings.TOUCH_TARGET_MIN > 0:
            banner_font = settings.get_font(
                max(11, int(settings.FS_SMALL * 0.92)),
                bold=True,
            )
        banner = banner_font.render(text, True, color)
        banner_rect = banner.get_rect(center=(box_cx, footer.centery))
        ready_rect = getattr(getattr(self, 'ready_button', None), 'rect', None)
        if ready_visible and ready_rect and banner_rect.colliderect(ready_rect):
            gap = max(3, int(0.006 * settings.SCREEN_HEIGHT))
            info_bottom = footer.bottom - gap
            below = banner_rect.copy()
            below.top = ready_rect.bottom + gap
            if below.bottom <= info_bottom:
                banner_rect = below
            else:
                above = banner_rect.copy()
                above.bottom = ready_rect.top - gap
                info_top = footer.top + gap
                if above.top >= info_top:
                    banner_rect = above
        self._phase_banner_rect = banner_rect.copy()
        self.window.blit(banner, banner_rect)

    def _draw_bought_slots(self):
        """Draw the 3 bought-move slots as 45° diamonds, centred in the info box.

        Empty slots show a rotated brown diamond.
        Occupied slots show only the icon, frame, and glow (no background).
        Suit icon is at bottom-center, power value at top-center.
        """
        sw = settings.BATTLE_SHOP_SLOT_WIDTH
        sh = settings.BATTLE_SHOP_SLOT_HEIGHT
        max_moves = settings.BATTLE_SHOP_MAX_MOVES
        delta_x = settings.BATTLE_SHOP_SLOT_DELTA_X

        # Centre the slots horizontally within the info box
        box_cx = self._sx(settings.BATTLE_SHOP_INFO_BOX_X + settings.BATTLE_SHOP_INFO_BOX_WIDTH // 2)
        total_span = (max_moves - 1) * delta_x + sw
        slot_start_x = box_cx - total_span // 2
        sy = self._slot_top_y()

        # Label with count — centred above the slots.  Skipped on mobile,
        # where the tray sits flush against the box top with no room for a
        # heading; the shared footer already reports the running count there.
        count = len(self.bought_moves)
        if settings.TOUCH_TARGET_MIN <= 0:
            slot_title = (
                'Starting Tactics'
                if _is_kingdom_config_mode(self.mode)
                else 'Battle Moves')
            label = self.slot_label_font.render(
                f"{slot_title} ({count}/{max_moves})",
                True, settings.BATTLE_SHOP_TYPE_LABEL_COLOR)
            label_rect = label.get_rect(
                centerx=box_cx,
                bottom=sy - int(0.04 * settings.SCREEN_HEIGHT))
            self.window.blit(label, label_rect)

        # Determine hover state
        mouse_pos = pygame.mouse.get_pos()
        mouse_pressed = _get_pressed()[0]
        self._hovered_slot = None
        self._slot_remove_rects = {}

        for i in range(max_moves):
            sx = slot_start_x + i * delta_x
            cx = sx + sw // 2
            cy = sy + sh // 2

            if i < len(self.bought_moves):
                # Hit test (diamond shape)
                hw = sw * 0.7
                hh = sh * 0.7
                is_hovered = (abs(mouse_pos[0] - cx) / hw + abs(mouse_pos[1] - cy) / hh <= 1.0)
                if is_hovered:
                    self._hovered_slot = i

                bm = self.bought_moves[i]
                suit = bm.get('suit', '')

                # Hover: big if hovered but not pressed
                hovered = is_hovered and not mouse_pressed

                draw_battle_move_icon(
                    self.window, cx, cy,
                    bm['family_name'], suit, self._get_display_power(bm),
                    self._slot_glow_cache, self._slot_icon_cache,
                    self._slot_frame_cache, self._suit_icon_cache,
                    self.slot_font, sw,
                    hovered=hovered,
                )
                if not self._is_locked:
                    visual_s = max(16, int(0.035 * settings.SCREEN_HEIGHT))
                    visual = pygame.Rect(0, 0, visual_s, visual_s)
                    visual.center = (
                        int(cx + sw * 0.43),
                        int(cy - sh * 0.43),
                    )
                    hit_s = max(visual_s, settings.TOUCH_COMPACT_MIN)
                    hit = pygame.Rect(0, 0, hit_s, hit_s)
                    hit.center = visual.center
                    self._slot_remove_rects[i] = hit
                    pygame.draw.circle(
                        self.window, (76, 42, 28), visual.center,
                        visual_s // 2)
                    pygame.draw.circle(
                        self.window, (238, 206, 130), visual.center,
                        visual_s // 2, 1)
                    close_font = settings.get_font(
                        max(9, int(settings.FS_TINY * 0.95)), bold=True)
                    close = close_font.render('×', True, (255, 238, 200))
                    self.window.blit(
                        close, close.get_rect(center=visual.center))
            else:
                # Empty slot: rotated diamond
                dr = self._slot_diamond.get_rect(center=(cx, cy))
                self.window.blit(self._slot_diamond, dr.topleft)

    def _handle_slot_remove_click(self, pos):
        for index, rect in getattr(self, '_slot_remove_rects', {}).items():
            if rect.collidepoint(pos):
                self._pending_return_index = index
                move = self.bought_moves[index]
                self.make_dialogue_box(
                    message=(
                        f"Remove {move.get('family_name', 'this tactic')} "
                        "and return its card?"
                    ),
                    actions=['return', 'cancel'],
                    icon='question',
                    title='Remove Tactic',
                )
                return True
        return False
