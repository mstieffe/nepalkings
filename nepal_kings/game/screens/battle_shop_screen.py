"""Battle Shop screen — buy and return battle moves."""

import pygame
from pygame.locals import *
from config import settings
from game.screens.sub_screen import SubScreen
from game.components.battle_moves.battle_move_manager import BattleMoveManager
from game.components.battle_moves.battle_move import BattleMove
from game.components.battle_moves.battle_move_detail_box import BattleMoveDetailBox
from game.components.battle_moves.battle_move_icon_renderer import draw_battle_move_icon
from game.components.figures.figure_manager import FigureManager
from game.components.cards.card import Card
from game.components.buttons.confirm_button import ConfirmButton
from utils import battle_shop_service


class BattleShopScreen(SubScreen):
    """Screen for purchasing and returning battle moves.

    Players can buy up to 3 battle moves (each requires one card).
    Buying / returning is NOT a turn action.
    """

    def __init__(self, window, state, x: int = 0.0, y: int = 0.0, title=None):
        super().__init__(window, state.game, x, y, title)
        self.state = state
        self.game = state.game

        # Manager
        self.battle_move_manager = BattleMoveManager()
        self.figure_manager = FigureManager()

        # Cached player figures for Call-move figure selection
        self._player_figures = []
        self._resources_data = None
        self._figures_loaded_game_id = None

        # UI init
        self.init_info_box()
        self.init_move_family_icons()
        self.init_scroll_test_list_shifter()

        self.selected_family = None
        self.selected_moves = []

        # Bought moves (loaded from server)
        self.bought_moves = []  # List of server dicts
        self._loaded_game_id = None  # Track which game_id was last loaded
        self._load_bought_moves()

        # Slot rendering
        self.slot_font = pygame.font.Font(settings.FONT_PATH, settings.BATTLE_SHOP_TYPE_LABEL_FONT_SIZE)
        self.slot_font.set_bold(True)
        self.slot_label_font = pygame.font.Font(settings.FONT_PATH, settings.BATTLE_SHOP_TYPE_LABEL_FONT_SIZE)
        self.slot_label_font.set_bold(True)

        # Slot hover state
        self._hovered_slot = None  # Index of currently hovered slot (or None)

        # Confirm button
        self.confirm_button = ConfirmButton(
            self.window,
            settings.BATTLE_SHOP_CONFIRM_BUTTON_X,
            settings.BATTLE_SHOP_CONFIRM_BUTTON_Y,
            "buy!"
        )

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

        self.ready_button = ConfirmButton(
            self.window,
            settings.BATTLE_SHOP_READY_BUTTON_X,
            settings.BATTLE_SHOP_READY_BUTTON_Y,
            "ready!"
        )
        self.phase_banner_font = pygame.font.Font(
            settings.FONT_PATH,
            settings.BATTLE_SHOP_PHASE_BANNER_FONT_SIZE,
        )
        self.phase_banner_font.set_bold(True)

    def reset_state(self):
        """Reset all game-specific transient state.

        Called by GameScreen._reset_game_screen_state() when switching games.
        """
        self.selected_family = None
        self.selected_moves = []
        self.bought_moves = []
        self._loaded_game_id = None
        self._figures_loaded_game_id = None
        self._player_figures = []
        self._resources_data = None
        self._hovered_slot = None
        self._pending_buy_move = None
        self._pending_return_index = None
        self.battle_move_detail_box = None
        self.dialogue_box = None
        self._battle_moves_confirmed = False
        self._waiting_for_opponent = False
        print("[BattleShop] State reset for game switch")

    @property
    def _is_locked(self):
        """True when battle moves must not be changed (confirmed or battle active).

        During the battle-moves selection phase (battle_confirmed but moves not
        yet confirmed) the shop must remain open for buying/returning.
        """
        if self._battle_moves_confirmed:
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
        dx = settings.BATTLE_MOVE_ICON_DELTA_X

        for i, family in enumerate(self.battle_move_manager.families):
            icon = family.make_icon(
                self.window, self.game,
                start_x + i * dx,
                start_y,
            )
            self.move_family_buttons.append(icon)

    # ----------------------------------------------------------- data helpers
    def _load_bought_moves(self):
        """Fetch bought battle moves from server."""
        try:
            result = battle_shop_service.get_battle_moves(
                self.game.game_id, self.game.player_id
            )
            self.bought_moves = result.get('battle_moves', [])
            self._loaded_game_id = getattr(self.game, 'game_id', None)
        except Exception as e:
            print(f"[BattleShop] Failed to load bought moves: {e}")
            self.bought_moves = []

    def _get_bought_card_ids(self):
        """Set of card IDs already reserved for battle moves."""
        return {m['card_id'] for m in self.bought_moves}

    def _get_hand_cards(self):
        """Get all cards currently in the player's hand (excluding battle-move cards)."""
        main, side = self.game.get_hand()
        return main + side

    # ---------------------------------------------------------------- update
    def update(self, game):
        super().update(game)
        self.game = game

        # Reload bought moves when the game changes (e.g. loading a saved game)
        current_gid = getattr(game, 'game_id', None)
        if current_gid and current_gid != self._loaded_game_id:
            self._load_bought_moves()
            self._load_player_figures()

        in_phase = getattr(game, 'battle_moves_phase', False)

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
        if in_phase and not self._battle_moves_confirmed:
            if len(self.bought_moves) >= settings.BATTLE_SHOP_MAX_MOVES:
                self.ready_button.disabled = False

        # Update icon active states based on available cards
        self._update_icon_states()

        for btn in self.move_family_buttons:
            btn.update()

        if self.scroll_text_list_shifter:
            selected = self.scroll_text_list_shifter.get_current_selected()
            if selected:
                self.confirm_button.update()

        if in_phase:
            self.ready_button.update()

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
        super().handle_events(events)

        in_phase = getattr(self.game, 'battle_moves_phase', False)
        selected_move = None
        if self.scroll_text_list_shifter:
            selected_move = self.scroll_text_list_shifter.get_current_selected()

        # Handle battle move detail box events first (if open)
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

        for event in events:
            if event.type == MOUSEBUTTONDOWN:
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
                        self.ready_button.collide()):
                    self._on_ready_confirm()

                # Slot clicks (open detail box — return blocked if locked)
                if not self._is_locked:
                    self._handle_slot_click(event)

        # Forward events to scroll text list shifter (arrow scrolling)
        if self.scroll_text_list_shifter:
            self.scroll_text_list_shifter.handle_events(events)

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
                    "content": None,
                }
            ]

        self.scroll_text_list_shifter.set_displayed_texts(self.scroll_text_list)

        # Immediately update glow so it reflects the first item's suit
        self._update_glow_colors()

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
            message=f"Buy {move.family.name} ({move.suit}, value {move.value})?",
            actions=['yes', 'cancel'],
            images=images,
            icon="question",
            title="Buy Battle Move",
        )
        self._pending_buy_move = move

    def _buy_current_move(self):
        """Actually purchase the pending move via the server."""
        move = self._pending_buy_move
        if not move:
            self.dialogue_box = None
            return

        card_type = 'side' if move.card.type == 'side_card' else 'main'
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
            if result.get('game'):
                self.game.update_from_dict(result['game'])
            self._load_bought_moves()

            # Refresh the scroll list for the selected family
            if self.selected_family:
                for btn in self.move_family_buttons:
                    if btn.family.name == self.selected_family.name:
                        self._on_family_clicked(btn)
                        btn.clicked = True
                        break

            self.make_dialogue_box(
                message=f"{move.family.name} purchased!",
                actions=['ok'],
                icon="figure",
                title="Battle Move Bought",
            )
        else:
            self.make_dialogue_box(
                message=f"Failed: {result.get('message', 'Unknown error')}",
                actions=['ok'],
                icon="error",
                title="Purchase Failed",
            )

        self._pending_buy_move = None

    def _handle_slot_click(self, event):
        """Check if the player clicked on a bought-move slot to open its detail box."""
        mx, my = event.pos
        sw = settings.BATTLE_SHOP_SLOT_WIDTH
        sh = settings.BATTLE_SHOP_SLOT_HEIGHT
        delta_x = settings.BATTLE_SHOP_SLOT_DELTA_X
        max_moves = settings.BATTLE_SHOP_MAX_MOVES

        # Use same centred positions as _draw_bought_slots
        box_cx = settings.BATTLE_SHOP_INFO_BOX_X + settings.BATTLE_SHOP_INFO_BOX_WIDTH // 2
        total_span = (max_moves - 1) * delta_x + sw
        slot_start_x = box_cx - total_span // 2
        sy = settings.BATTLE_SHOP_SLOT_Y

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
            self._player_figures = self.game.get_figures(families, is_opponent=False)
            self._resources_data = self.game.calculate_resources(families, is_opponent=False)
            self._figures_loaded_game_id = getattr(self.game, 'game_id', None)
        except Exception as e:
            print(f"[BattleShop] Failed to load player figures: {e}")
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

        # Ensure figures are loaded
        if not self._player_figures or self._figures_loaded_game_id != getattr(self.game, 'game_id', None):
            self._load_player_figures()

        bm_suit = bm.get('suit', '')
        bm_is_red = bm_suit in self._RED_SUITS

        # IDs of figures already in battle
        fighting_ids = set()
        for attr in ('advancing_figure_id', 'advancing_figure_id_2',
                     'defending_figure_id', 'defending_figure_id_2'):
            fid = getattr(self.game, attr, None)
            if fid is not None:
                fighting_ids.add(fid)

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
        (figure base + move bonus if suit matches) across all eligible
        figures.  For other moves the raw move value is shown.
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

        max_power = 0
        for fig in eligible:
            base = fig.get_value()
            bonus = bm_value if fig.suit == bm_suit else 0
            total = base + bonus
            if total > max_power:
                max_power = total
        return max_power

    def _return_current_slot_move(self):
        """Return a battle move from the slot."""
        idx = self._pending_return_index
        if idx is None or idx >= len(self.bought_moves):
            self.dialogue_box = None
            return

        bm = self.bought_moves[idx]
        result = battle_shop_service.return_battle_move(
            game_id=self.game.game_id,
            player_id=self.game.player_id,
            battle_move_id=bm['id'],
        )

        if result.get('success'):
            if result.get('game'):
                self.game.update_from_dict(result['game'])
            self._load_bought_moves()

            # Refresh the scroll list
            if self.selected_family:
                for btn in self.move_family_buttons:
                    if btn.family.name == self.selected_family.name:
                        self._on_family_clicked(btn)
                        btn.clicked = True
                        break

            self.make_dialogue_box(
                message="Battle move returned.",
                actions=['ok'],
                icon="figure",
                title="Returned",
            )
        else:
            self.make_dialogue_box(
                message=f"Failed: {result.get('message', 'Unknown error')}",
                actions=['ok'],
                icon="error",
                title="Return Failed",
            )

        self._pending_return_index = None

    def _on_ready_confirm(self):
        """Player confirms their 3 battle moves — notify server."""
        if len(self.bought_moves) < settings.BATTLE_SHOP_MAX_MOVES:
            return

        result = battle_shop_service.confirm_battle_moves(
            game_id=self.game.game_id,
            player_id=self.game.player_id,
        )

        if result.get('success'):
            self._battle_moves_confirmed = True
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

    # ------------------------------------------------------------------- draw
    def draw(self):
        super().draw()

        in_phase = getattr(self.game, 'battle_moves_phase', False)

        # Family icons
        for btn in self.move_family_buttons:
            btn.draw()

        # Scroll text list + buy confirm button
        if self.scroll_text_list_shifter:
            selected = self.scroll_text_list_shifter.get_current_selected()
            # Only show buy button when NOT locked (still shopping)
            if selected and not self._is_locked:
                self.confirm_button.draw()

        # Bought-move slots
        self._draw_bought_slots()

        # --- Battle moves phase UI ---
        if in_phase:
            self._draw_phase_banner()
            if not self._is_locked:
                if len(self.bought_moves) >= settings.BATTLE_SHOP_MAX_MOVES:
                    self.ready_button.draw()

        # Detail box on top of everything except dialogue box / msg
        if self.battle_move_detail_box:
            self.battle_move_detail_box.draw()

        super().draw_on_top()

    def _draw_phase_banner(self):
        """Draw a banner indicating the mandatory battle-move selection phase."""
        box_cx = settings.BATTLE_SHOP_INFO_BOX_X + settings.BATTLE_SHOP_INFO_BOX_WIDTH // 2
        count = len(self.bought_moves)
        max_m = settings.BATTLE_SHOP_MAX_MOVES

        if self._waiting_for_opponent:
            text = "Waiting for opponent..."
            color = settings.BATTLE_SHOP_PHASE_WAITING_COLOR
        elif self._is_locked:
            text = "Battle moves confirmed! Waiting for opponent..."
            color = settings.BATTLE_SHOP_PHASE_WAITING_COLOR
        elif count >= max_m:
            text = "All slots filled — press Ready!"
            color = settings.BATTLE_SHOP_PHASE_BANNER_COLOR
        else:
            text = f"Select {max_m - count} more battle move{'s' if max_m - count > 1 else ''}!"
            color = settings.BATTLE_SHOP_PHASE_BANNER_COLOR

        banner = self.phase_banner_font.render(text, True, color)
        banner_rect = banner.get_rect(
            centerx=box_cx,
            bottom=settings.BATTLE_SHOP_INFO_BOX_Y + settings.BATTLE_SHOP_INFO_BOX_HEIGHT - int(0.02 * settings.SCREEN_HEIGHT),
        )
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
        box_cx = settings.BATTLE_SHOP_INFO_BOX_X + settings.BATTLE_SHOP_INFO_BOX_WIDTH // 2
        total_span = (max_moves - 1) * delta_x + sw
        slot_start_x = box_cx - total_span // 2
        sy = settings.BATTLE_SHOP_SLOT_Y

        # Label with count — centred above the slots
        count = len(self.bought_moves)
        label = self.slot_label_font.render(f"Battle Moves ({count}/{max_moves})", True, settings.BATTLE_SHOP_TYPE_LABEL_COLOR)
        label_rect = label.get_rect(centerx=box_cx, bottom=sy - int(0.02 * settings.SCREEN_HEIGHT))
        self.window.blit(label, label_rect)

        # Determine hover state
        mouse_pos = pygame.mouse.get_pos()
        mouse_pressed = pygame.mouse.get_pressed()[0]
        self._hovered_slot = None

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
            else:
                # Empty slot: rotated diamond
                dr = self._slot_diamond.get_rect(center=(cx, cy))
                self.window.blit(self._slot_diamond, dr.topleft)
