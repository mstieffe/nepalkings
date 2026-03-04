import pygame
from pygame.locals import *
import pandas as pd
from game.screens.screen import Screen
from config import settings
#from game.components.card_img import CardImg
from game.components.cards.hand import Hand
from game.components.info_scroll import InfoScroll
from game.components.scoreboard_scroll import ScoreboardScroll
from game.components.buttons.state_button import StateButton
from utils.utils import GameButton
from game.screens.build_figure_screen import BuildFigureScreen
from game.screens.log_screen import LogScreen
from game.screens.field_screen import FieldScreen
from game.screens.cast_spell_screen import CastSpellScreen
from game.screens.tutorial_screen import TutorialScreen
from game.screens.battle_screen import BattleScreen
from game.screens.battle_shop_screen import BattleShopScreen
from game.components.figures.figure_manager import FigureManager


class GameScreen(Screen):
    def __init__(self, state):
        super().__init__(state)
        
        # Store reference to game_screen in state for button access
        self.state.parent_screen = self

        # Track current game ID to detect game switches
        self._current_game_id = None

        # Unread chat message tracking
        self._last_seen_chat_count = 0
        self._badge_font = pygame.font.Font(settings.FONT_PATH, int(0.015 * settings.SCREEN_HEIGHT))

        # Initialize figure manager
        self.figure_manager = FigureManager()

        # Initialize hands for the game (main and side hands)
        self.main_hand = Hand(self.window, self.state.game, x=settings.MAIN_HAND_X, y=settings.MAIN_HAND_Y)
        self.side_hand = Hand(self.window, self.state.game, x=settings.SIDE_HAND_X, y=settings.SIDE_HAND_Y, type="side_card")

        # Initialize buttons and add to the game_buttons list
        self.initialize_buttons()
        self.initialize_state_buttons()

        self.display_elements = []
        self.initialiaze_scoareboard_scroll()
        self.initialize_info_scroll()

        # Define which screen is visible, allowing flexibility in switching between subscreens
        #self.active_subscreen = 'build_figure'
        self.subscreens = {
            'field': FieldScreen(self.window, self.state, x=settings.SUB_SCREEN_X, y=settings.SUB_SCREEN_Y, title='Playing Board'),
            'build_figure': BuildFigureScreen(self.window, self.state, x=settings.SUB_SCREEN_X, y=settings.SUB_SCREEN_Y, title='Figure Builder'),
            'cast_spell': CastSpellScreen(self.window, self.state, x=settings.SUB_SCREEN_X, y=settings.SUB_SCREEN_Y, title='Spell Book'),
            'log': LogScreen(self.window, self.state, x=settings.SUB_SCREEN_X, y=settings.SUB_SCREEN_Y, title='Log-Book'),
            'tutorial': TutorialScreen(self.window, self.state, x=settings.SUB_SCREEN_X, y=settings.SUB_SCREEN_Y, title='Tutorial'),
            'battle': BattleScreen(self.window, self.state, x=settings.SUB_SCREEN_X, y=settings.SUB_SCREEN_Y, title='Battle Arena'),
            'battle_shop': BattleShopScreen(self.window, self.state, x=settings.SUB_SCREEN_X, y=settings.SUB_SCREEN_Y, title='Battle Shop'),
        }
        
        # Track previous subscreen to detect changes
        self.previous_subscreen = None
        
        # Queue for pending notifications (to avoid overwriting active dialogue boxes)
        self.pending_notifications = []
        
        # Counter spell state
        self.waiting_for_counter_response = False  # True when caster is waiting
        self.need_to_respond_to_spell = False  # True when defender needs to respond
        self.pending_spell_details = None  # Store spell details for counter
        self.counter_spell_selector = None  # Active counter spell selector UI
        self._cached_castable_spells = None  # Cached castable spells for current pending spell
        self._pending_spell_fetch_ready = False  # Flag: background fetch completed
        
        # Pre-create SpellManager so spell images are loaded at startup, not on first counter-spell
        from game.components.spells.spell_manager import SpellManager
        self._cached_spell_manager = SpellManager()
        
        # Battle modifier icon cache (loaded once at init)
        self._battle_modifier_icons = {}
        self._load_battle_modifier_icons()
        self._previous_battle_modifiers = []  # Track for change detection / notifications
        self._just_allowed_spell = False  # Flag to suppress duplicate notification after allowing a spell
        self._hovered_battle_modifier = None  # Index of currently hovered modifier (or None)
        self._battle_modifier_font = pygame.font.Font(settings.FONT_PATH, settings.GAME_BUTTON_FONT_SIZE)
    
    def make_dialogue_box(self, message, actions=None, images=None, icon=None, title="", auto_close_delay=None, message_after_images=None):
        """Create a dialogue box with specified message, actions, images, and icon."""
        from game.components.dialogue_box import DialogueBox
        self.dialogue_box = DialogueBox(self.window, message, actions=actions, images=images, icon=icon, title=title, auto_close_delay=auto_close_delay, message_after_images=message_after_images)
    
    def queue_or_show_notification(self, notification_data):
        """Queue a notification if dialogue box is active, otherwise show it immediately."""
        if self.dialogue_box:
            # Dialogue box already showing - add to queue
            self.pending_notifications.append(notification_data)
        else:
            # No dialogue box - show immediately
            self.make_dialogue_box(**notification_data)
    
    def show_next_queued_notification(self):
        """Show the next queued notification if any exist."""
        if self.pending_notifications:
            notification_data = self.pending_notifications.pop(0)
            self.make_dialogue_box(**notification_data)

    def initialiaze_scoareboard_scroll(self):
        """Initialize resources for the info scroll."""

        scoreboard_scroll = ScoreboardScroll(
            self.window, 
            self.state.game,
            settings.SCOREBOARD_SCROLL_X, 
            settings.SCOREBOARD_SCROLL_Y, 
            settings.SCOREBOARD_SCROLL_WIDTH, 
            settings.SCOREBOARD_SCROLL_HEIGHT, 
            settings.SCOREBOARD_SCROLL_BG_IMG_PATH)
        self.display_elements.append(scoreboard_scroll)


    def initialize_info_scroll(self):
        """Initialize merged info scroll with resources and slots (excluding castle)."""
        info_df = pd.DataFrame({
            'element': ['village', 'military', 'food', 'material', 'amor'],
            'icon_img': [
                settings.RESOURCE_ICON_IMG_PATH_DICT['villager_red_black'],
                settings.RESOURCE_ICON_IMG_PATH_DICT['warrior_red_black'],
                settings.RESOURCE_ICON_IMG_PATH_DICT['rice_meat'],
                settings.RESOURCE_ICON_IMG_PATH_DICT['wood_stone'],
                settings.RESOURCE_ICON_IMG_PATH_DICT['sword_shield'],
            ],
            'red': ["0/0", "0/0", "0/0", "0/0", "0/0"],
            'black': ["0/0", "0/0", "0/0", "0/0", "0/0"],
            'red_deficit': [False, False, False, False, False],
            'black_deficit': [False, False, False, False, False],
        })
        info_scroll = InfoScroll(
            self.window,
            settings.INFO_SCROLL_X,
            settings.INFO_SCROLL_Y,
            settings.INFO_SCROLL_WIDTH,
            settings.INFO_SCROLL_HEIGHT,
            'Resources',
            info_df,
            settings.INFO_SCROLL_BG_IMG_PATH)
        self.display_elements.append(info_scroll)

    def initialize_state_buttons(self):
        """Initialize state buttons for the game screen."""

        # Add state buttons for the game screen
        self.game_buttons.append(StateButton(
            self.window, 
            'turn_tracker', 
            'turn', 
            settings.STATE_BUTTON_TURN_X, 
            settings.STATE_BUTTON_TURN_Y, 
            settings.STATE_BUTTON_SYMBOL_WIDTH, 
            settings.STATE_BUTTON_GLOW_WIDTH, 
            state=self.state, 
            hover_text_active='it is your turn!',
            hover_text_passive='not your turn!',
            track_turn = True
        ))

        # Add state buttons for the game screen
        self.game_buttons.append(StateButton(
            self.window, 
            'invader_tracker', 
            'invader', 
            settings.STATE_BUTTON_INVADER_X, 
            settings.STATE_BUTTON_INVADER_Y, 
            settings.STATE_BUTTON_SYMBOL_WIDTH, 
            settings.STATE_BUTTON_GLOW_WIDTH, 
            state=self.state, 
            hover_text_active='your are the defender!',
            hover_text_passive='you are the invader!',
            track_invader = True
        ))

        # Add ceasefire state button
        self.game_buttons.append(StateButton(
            self.window, 
            'ceasefire_tracker', 
            'ceasefire', 
            settings.STATE_BUTTON_CEASEFIRE_X, 
            settings.STATE_BUTTON_CEASEFIRE_Y, 
            settings.STATE_BUTTON_SYMBOL_WIDTH, 
            settings.STATE_BUTTON_GLOW_WIDTH, 
            state=self.state, 
            hover_text_active='ceasefire active - battles blocked!',
            hover_text_passive='battles are allowed!',
            track_ceasefire = True
        ))

    def initialize_buttons(self):
        """Initialize buttons for the game screen, including hand and action buttons."""
        #self.game_buttons = []

        # Add buttons from both hands (main and side hand buttons)
        self.game_buttons.extend(self.main_hand.buttons)
        self.game_buttons.extend(self.side_hand.buttons)

        # Action button (for casting spells)
        action_button = GameButton(
            self.window, 
            'cast_spell',
            'book', 
            'plant',
            settings.ACTION_BUTTON_X, settings.ACTION_BUTTON_Y,
            settings.ACTION_BUTTON_WIDTH,
            settings.ACTION_BUTTON_WIDTH,
            state=self.state,
            hover_text='cast spell!',
            subscreen='cast_spell'
        )
        self.game_buttons.append(action_button)

        # Build figure button (switches to the build figure subscreen)
        build_button = GameButton(
            self.window, 
            'build_figure',
            'hammer', 
            'rope',
            settings.BUILD_BUTTON_X, settings.BUILD_BUTTON_Y,
            settings.BUILD_BUTTON_WIDTH,
            settings.BUILD_BUTTON_WIDTH,
            state=self.state,
            hover_text='build figure!',
            subscreen='build_figure'
        )
        self.game_buttons.append(build_button)

        # Field button (switches to the field subscreen)
        field_button = GameButton(
            self.window, 
            'view_field',
            'map', 
            'plain',
            settings.FIELD_BUTTON_X, settings.FIELD_BUTTON_Y,
            settings.FIELD_BUTTON_WIDTH,
            settings.FIELD_BUTTON_WIDTH,
            glow_width=settings.FIELD_BUTTON_GLOW_WIDTH,
            symbol_width_big=settings.FIELD_BUTTON_WIDTH_BIG,
            glow_width_big=settings.FIELD_BUTTON_GLOW_WIDTH_BIG,
            state=self.state,
            hover_text='view field!',
            subscreen='field',
            track_turn = False
        )
        self.game_buttons.append(field_button)

        # Log button (switches to the log subscreen)
        self.log_button = GameButton(
            self.window, 
            'view_log',
            'letter', 
            'plain',
            settings.LETTER_BUTTON_X, settings.LETTER_BUTTON_Y,
            settings.LETTER_BUTTON_WIDTH,
            settings.LETTER_BUTTON_WIDTH,
            glow_width=settings.FIELD_BUTTON_GLOW_WIDTH,
            symbol_width_big=settings.LETTER_BUTTON_WIDTH_BIG,
            glow_width_big=settings.FIELD_BUTTON_GLOW_WIDTH_BIG,
            state=self.state,
            hover_text='view log!',
            subscreen='log',
            track_turn = False
        )
        self.game_buttons.append(self.log_button)

        # Tutorial button (switches to the tutorial subscreen)
        tutorial_button = GameButton(
            self.window, 
            'view_tutorial',
            'tutorial', 
            'plain',
            settings.TUTORIAL_BUTTON_X, settings.TUTORIAL_BUTTON_Y,
            settings.TUTORIAL_BUTTON_WIDTH,
            settings.TUTORIAL_BUTTON_WIDTH,
            glow_width=settings.FIELD_BUTTON_GLOW_WIDTH,
            symbol_width_big=settings.TUTORIAL_BUTTON_WIDTH_BIG,
            glow_width_big=settings.FIELD_BUTTON_GLOW_WIDTH_BIG,
            state=self.state,
            hover_text='tutorial!',
            subscreen='tutorial',
            track_turn = False
        )
        self.game_buttons.append(tutorial_button)

        # Battle button (switches to the battle subscreen)
        # Inactive during normal round, only becomes active in battle phase
        self.battle_button = GameButton(
            self.window, 
            'view_battle',
            'battle', 
            'plain',
            settings.BATTLE_BUTTON_X, settings.BATTLE_BUTTON_Y,
            settings.BATTLE_BUTTON_WIDTH,
            settings.BATTLE_BUTTON_WIDTH,
            glow_width=settings.FIELD_BUTTON_GLOW_WIDTH,
            symbol_width_big=settings.BATTLE_BUTTON_WIDTH_BIG,
            glow_width_big=settings.FIELD_BUTTON_GLOW_WIDTH_BIG,
            state=self.state,
            hover_text='battle!',
            subscreen='battle',
            track_turn = False,
            locked = True  # Locked until battle phase starts
        )
        self.game_buttons.append(self.battle_button)

        # Battle shop button (switches to the battle shop subscreen)
        battle_shop_button = GameButton(
            self.window, 
            'view_battle_shop',
            'battleshop', 
            'plain',
            settings.BATTLE_SHOP_BUTTON_X, settings.BATTLE_SHOP_BUTTON_Y,
            settings.BATTLE_SHOP_BUTTON_WIDTH,
            settings.BATTLE_SHOP_BUTTON_WIDTH,
            glow_width=settings.FIELD_BUTTON_GLOW_WIDTH,
            symbol_width_big=settings.BATTLE_SHOP_BUTTON_WIDTH_BIG,
            glow_width_big=settings.FIELD_BUTTON_GLOW_WIDTH_BIG,
            state=self.state,
            hover_text='battle shop!',
            subscreen='battle_shop',
            track_turn = False
        )
        self.game_buttons.append(battle_shop_button)

        home_button = GameButton(
            self.window, 
            'home',
            'home', 
            'plain',
            settings.HOME_BUTTON_X, settings.HOME_BUTTON_Y,
            settings.HOME_BUTTON_WIDTH,
            settings.HOME_BUTTON_WIDTH,
            glow_width=settings.HOME_BUTTON_GLOW_WIDTH,
            symbol_width_big=settings.HOME_BUTTON_WIDTH_BIG,
            glow_width_big=settings.HOME_BUTTON_GLOW_WIDTH_BIG,
            state=self.state,
            hover_text='home menu!',
            screen='game_menu',
            track_turn = False
        )
        self.game_buttons.append(home_button)

    def update_game(self):
        """Update the game state and related components."""
        # Check if game exists (may be None after logout)
        if not self.state.game:
            return
        
        # Detect game switch — reset stale state from previous game
        current_id = getattr(self.state.game, 'game_id', None)
        if current_id != self._current_game_id:
            self._reset_game_screen_state()
            self._current_game_id = current_id
        
        # Check if subscreen changed - if so, deselect all cards
        if self.previous_subscreen != self.state.subscreen:
            self.main_hand.deselect_all_cards()
            self.side_hand.deselect_all_cards()
            # Re-lock the battle button when leaving battle/battle_shop
            if self.previous_subscreen in ('battle', 'battle_shop') and self.state.subscreen == 'field':
                self.battle_button.locked = True
            # Mark chats as read when opening the log screen
            if self.state.subscreen == 'log' and self.state.game and self.state.game.chat_messages:
                self._last_seen_chat_count = len(self.state.game.chat_messages)
            self.previous_subscreen = self.state.subscreen
        
        # Skip full server poll while defender is actively responding to counter spell
        # (they don't need fresh data while deciding, and the poll blocks the UI)
        if not self.need_to_respond_to_spell:
            self.state.game.update()
        
        # Check for auto-fill notification
        self.check_auto_fill_notification()
        
        # Check for post-battle side card draw notification
        self.check_post_battle_side_cards()
        
        # Check for opponent turn notification (includes Forced Deal and Dump Cards details)
        self.check_opponent_turn_notification()
        
        # Check for Infinite Hammer mode activation
        self.check_infinite_hammer_activation()
        
        # Check for battle modifier changes
        self.check_battle_modifier_changes()
        
        # Check for advance/battle state
        self.check_forced_advance()
        self.check_own_advance_notification()
        self.check_opponent_advance_notification()
        self.check_defender_selection_needed()
        self.check_waiting_for_defender_pick()
        self.check_battle_ready()
        
        # Check for fold outcome and auto-proceed (polling detection for waiting player)
        self.check_fold_result()
        self.check_auto_proceed_to_battle()
        self.check_battle_moves_ready()
        
        # Reconnect: detect active battle on server that the client missed
        self.check_battle_reconnect()
        
        # Check for ceasefire ended notification AFTER action results
        # so it appears after the success message of the action that caused it
        self.check_ceasefire_ended_notification()
        
        # Check for pending counter spell state
        self.check_counter_spell_state()
        
        self.main_hand.update(self.state.game)
        self.side_hand.update(self.state.game)
        
        # Check if player needs to discard cards due to exceeding max hand size
        # Only check if it's the player's turn and they're not already in discard mode
        if self.state.game.turn and not self.main_hand.discard_mode and not self.side_hand.discard_mode:
            if self.main_hand.needs_discard():
                excess = self.main_hand.get_excess_card_count()
                self.main_hand.start_discard_mode(excess)
            elif self.side_hand.needs_discard():
                excess = self.side_hand.get_excess_card_count()
                self.side_hand.start_discard_mode(excess)
        
        for elem in self.display_elements:
            # Pass families to info scroll for resource calculation
            if isinstance(elem, InfoScroll):
                elem.update(self.state.game, families=self.figure_manager.families)
            else:
                elem.update(self.state.game)

        # Keep marking chats as read while on the log screen
        if self.state.subscreen == 'log' and self.state.game and self.state.game.chat_messages:
            self._last_seen_chat_count = len(self.state.game.chat_messages)
    
    def _reset_game_screen_state(self):
        """Reset all transient game screen state when switching to a different game."""
        # Clear pending notifications and dialogue box
        self.pending_notifications = []
        self.dialogue_box = None
        
        # Reset counter spell state
        self.waiting_for_counter_response = False
        self.need_to_respond_to_spell = False
        self.pending_spell_details = None
        self.counter_spell_selector = None
        self._cached_castable_spells = None
        self._pending_spell_fetch_ready = False
        
        # Reset battle modifier tracking
        self._previous_battle_modifiers = []
        self._hovered_battle_modifier = None
        self._just_allowed_spell = False
        
        # ── Reset ALL subscreens ──
        # Each subscreen has a reset_state() that clears its game-specific
        # transient state (pending actions, dialogue boxes, selections, etc.)
        for name, subscreen in self.subscreens.items():
            if hasattr(subscreen, 'reset_state'):
                subscreen.reset_state()
        
        # Reset waiting for defender pick state
        if self.state.game:
            self.state.game.pending_waiting_for_defender_pick = False
            self.state.game.waiting_for_defender_pick_shown = False
            self.state.game.pending_battle_ready = False
            self.state.game.battle_ready_shown = False
            # Reset Civil War second pick state
            self.state.game.civil_war_awaiting_second = False
            self.state.game.civil_war_defender_second = False
            self.state.game.civil_war_required_color = None
            # Reset fold/battle decision state
            self.state.game.waiting_for_battle_decision = False
            self.state.game.pending_fold_result = False
            self.state.game.fold_result_shown = False
            self.state.game.auto_proceed_to_battle = False
            # Reset battle moves phase state
            self.state.game.battle_moves_phase = False
            self.state.game.battle_moves_ready = False
            self.state.game.waiting_for_opponent_battle_moves = False
            self.state.game.both_battle_moves_ready = False
            # Reset active battle phase state
            self.state.game.in_battle_phase = False
            self.state.game.battle_turns_left = 0
        
        # Re-lock battle button
        self.battle_button.locked = True

        # Reset unread chat counter
        self._last_seen_chat_count = 0
        
        # Reset subscreen to default (field) so stale battle/shop view doesn't persist
        self.state.subscreen = 'field'
        
        # Reset subscreen tracking
        self.previous_subscreen = None
        
        # Reset hand discard mode
        if hasattr(self, 'main_hand'):
            self.main_hand.deselect_all_cards()
            if hasattr(self.main_hand, 'discard_mode'):
                self.main_hand.discard_mode = False
        if hasattr(self, 'side_hand'):
            self.side_hand.deselect_all_cards()
            if hasattr(self.side_hand, 'discard_mode'):
                self.side_hand.discard_mode = False
        
        print(f"[GAME_SCREEN] State reset for new game {self._current_game_id}")

    def check_counter_spell_state(self):
        """Check if player needs to respond to counter spell or is waiting for opponent."""
        if not self.state.game:
            return
        
        # Check if this player needs to respond to a counterable spell
        if self.state.game.waiting_for_counter and not self.need_to_respond_to_spell:
            # Player needs to respond - start background fetch (non-blocking)
            self.need_to_respond_to_spell = True
            self._fetch_pending_spell_async()
        
        # Show dialogue once background fetch completes (defender side)
        if self._pending_spell_fetch_ready and self.need_to_respond_to_spell and not self.dialogue_box:
            self._pending_spell_fetch_ready = False
            self._show_counter_spell_dialogue()
        
        # Check if player is waiting for opponent's response (caster side)
        if self.state.game.pending_spell_id and not self.state.game.waiting_for_counter and not self.waiting_for_counter_response:
            # Player cast a counterable spell and is waiting
            self.waiting_for_counter_response = True
            
            # Fetch spell name for display in background
            self._fetch_pending_spell_async(is_caster=True)
        
        # Pick up caster spell name once fetch completes
        if self._pending_spell_fetch_ready and self.waiting_for_counter_response:
            self._pending_spell_fetch_ready = False
            self.pending_spell_name = self.pending_spell_details.get('spell_name', 'your spell') if self.pending_spell_details else 'your spell'
            self.pending_spell_family_name = self.pending_spell_details.get('spell_family_name', self.pending_spell_name) if self.pending_spell_details else self.pending_spell_name
            # Persistent prompt will be drawn in render() - no dialogue box
        
        # Clear waiting state when spell is resolved
        if not self.state.game.pending_spell_id:
            if self.waiting_for_counter_response:
                self.waiting_for_counter_response = False
                # Show caster notification that spell was resolved
                spell_name = self.pending_spell_name or 'Your spell'
                # Check logs to determine if spell was allowed or countered
                last_log = None
                if self.state.game.log_entries:
                    for log in reversed(self.state.game.log_entries):
                        if log.get('type') in ('spell_allowed', 'spell_countered'):
                            last_log = log
                            break
                
                spell_family = getattr(self, 'pending_spell_family_name', spell_name)
                spell_images = self._get_spell_icon_image(spell_family)
                
                if last_log and last_log.get('type') == 'spell_countered':
                    self.queue_or_show_notification({
                        'message': f"{spell_name} was countered by your opponent!\n\nYour cards were consumed but the spell had no effect.\nYou keep your turn.",
                        'actions': ['ok'],
                        'images': spell_images,
                        'icon': "error",
                        'title': "Spell Countered"
                    })
                else:
                    self.queue_or_show_notification({
                        'message': f"{spell_name} was allowed by your opponent!\n\nThe spell has been executed successfully.",
                        'actions': ['ok'],
                        'images': spell_images,
                        'icon': "magic",
                        'title': "Spell Executed"
                    })
                self.pending_spell_name = None
                self.pending_spell_family_name = None
                self.pending_spell_details = None  # Clear cache when spell resolved
                self._cached_castable_spells = None
                self._pending_spell_fetch_ready = False
            if self.need_to_respond_to_spell:
                self.need_to_respond_to_spell = False
                self.pending_spell_details = None  # Clear cache when spell resolved
                self._cached_castable_spells = None
                self._pending_spell_fetch_ready = False
    
    def _get_spell_manager(self):
        """Get or create a cached SpellManager instance (avoids reloading images from disk)."""
        if self._cached_spell_manager is None:
            from game.components.spells.spell_manager import SpellManager
            self._cached_spell_manager = SpellManager()
        return self._cached_spell_manager
    
    def _get_spell_icon_image(self, spell_name):
        """Get a spell's icon image from the cached SpellManager. Returns list with icon or empty list."""
        spell_manager = self._get_spell_manager()
        family = spell_manager.get_family_by_name(spell_name)
        if family and family.icon_img:
            return [family.icon_img]
        return []
    
    def _fetch_pending_spell_async(self, is_caster=False):
        """Fetch pending spell details in a background thread to avoid blocking the game loop."""
        if self.pending_spell_details is not None:
            # Already cached - signal ready immediately
            self._pending_spell_fetch_ready = True
            return
        
        if not self.state.game or not self.state.game.pending_spell_id:
            return
        
        import threading
        spell_id = self.state.game.pending_spell_id
        
        def _fetch():
            import requests
            try:
                response = requests.get(
                    f'{settings.SERVER_URL}/spells/get_pending_spell',
                    params={'spell_id': spell_id},
                    timeout=5
                )
                if response.status_code == 200:
                    data = response.json()
                    self.pending_spell_details = data.get('spell', {})
                else:
                    self.pending_spell_details = {}
            except:
                self.pending_spell_details = {}
            
            # Cache castable spells (SpellManager is already pre-loaded, so this is fast)
            if not is_caster:
                self._cache_castable_spells()
            
            # Signal that data is ready (picked up on next update cycle)
            self._pending_spell_fetch_ready = True
        
        thread = threading.Thread(target=_fetch, daemon=True)
        thread.start()
    
    def _cache_castable_spells(self):
        """Compute and cache castable counter spells for the current pending spell."""
        spell_data = self.pending_spell_details or {}
        spell_family_name = spell_data.get('spell_family_name')
        
        if not spell_family_name:
            self._cached_castable_spells = []
            return
        
        main_hand_cards = self.main_hand.cards if hasattr(self, 'main_hand') else []
        side_hand_cards = self.side_hand.cards if hasattr(self, 'side_hand') else []
        all_cards = main_hand_cards + side_hand_cards
        
        spell_manager = self._get_spell_manager()
        family = spell_manager.get_family_by_name(spell_family_name)
        if family:
            self._cached_castable_spells = [
                spell for spell in spell_manager.find_castable_spells(all_cards)
                if spell.family.name == spell_family_name
            ]
        else:
            self._cached_castable_spells = []
    
    def _load_battle_modifier_icons(self):
        """Pre-load battle modifier icons at startup."""
        import os
        icon_dir = settings.SPELL_ICON_IMG_DIR
        icon_size = settings.BATTLE_MODIFIER_ICON_SIZE
        modifier_types = {
            'Civil War': 'civil_war.png',
            'Peasant War': 'peasant_war.png',
            'Blitzkrieg': 'blitzkrieg.png',
        }
        for modifier_name, filename in modifier_types.items():
            icon_path = os.path.join(icon_dir, filename)
            if os.path.exists(icon_path):
                img = pygame.image.load(icon_path).convert_alpha()
                img = pygame.transform.smoothscale(img, (icon_size, icon_size))
                self._battle_modifier_icons[modifier_name] = img
    
    def _draw_battle_modifier_icons(self):
        """Draw active battle modifier icons below the resource scroll and track hover."""
        if not self.state.game or not self.state.game.battle_modifier:
            self._hovered_battle_modifier = None
            return
        
        modifiers = self.state.game.battle_modifier
        if not isinstance(modifiers, list) or len(modifiers) == 0:
            self._hovered_battle_modifier = None
            return
        
        icon_size = settings.BATTLE_MODIFIER_ICON_SIZE
        padding = settings.BATTLE_MODIFIER_ICON_PADDING
        y_offset = settings.BATTLE_MODIFIER_ICON_Y_OFFSET
        
        # Position below the InfoScroll
        start_x = settings.INFO_SCROLL_X
        start_y = settings.INFO_SCROLL_Y + settings.INFO_SCROLL_HEIGHT + y_offset
        
        mx, my = pygame.mouse.get_pos()
        self._hovered_battle_modifier = None
        
        for i, modifier in enumerate(modifiers):
            modifier_type = modifier.get('type', '')
            icon = self._battle_modifier_icons.get(modifier_type)
            if icon:
                x = start_x + i * (icon_size + padding)
                self.window.blit(icon, (x, start_y))
                
                # Check hover
                icon_rect = pygame.Rect(x, start_y, icon_size, icon_size)
                if icon_rect.collidepoint(mx, my):
                    self._hovered_battle_modifier = i
    
    def _draw_battle_modifier_hover_text(self):
        """Draw hover text for battle modifier icons on top of everything."""
        if self._hovered_battle_modifier is None or not self.state.game:
            return
        
        modifiers = self.state.game.battle_modifier
        if not isinstance(modifiers, list) or self._hovered_battle_modifier >= len(modifiers):
            return
        
        modifier = modifiers[self._hovered_battle_modifier]
        modifier_type = modifier.get('type', 'Unknown')
        caster_id = modifier.get('caster_id')
        caster_name = modifier.get('caster_name', 'Unknown')
        
        # Determine if caster is the current player
        is_self = (caster_id == self.state.game.player_id)
        who = "You" if is_self else caster_name
        text_color = settings.STATE_BUTTON_TEXT_COLOR_ACTIVE if is_self else settings.STATE_BUTTON_TEXT_COLOR_PASSIVE
        shadow_color = settings.STATE_BUTTON_TEXT_COLOR_SHADOW
        
        hover_text = f"{who} casted {modifier_type}"
        text_surface = self._battle_modifier_font.render(hover_text, True, text_color)
        shadow_surface = self._battle_modifier_font.render(hover_text, True, shadow_color)
        text_rect = text_surface.get_rect()
        
        mx, my = pygame.mouse.get_pos()
        # Position text to the right of the cursor (icons are on the left edge of the screen)
        text_rect.midleft = (mx + 12 + 1, my - 1)
        self.window.blit(shadow_surface, text_rect)
        text_rect.midleft = (mx + 12, my)
        self.window.blit(text_surface, text_rect)
    
    def check_battle_modifier_changes(self):
        """Detect new battle modifiers and show notifications to the opponent."""
        if not self.state.game:
            return
        
        current_modifiers = self.state.game.battle_modifier
        if not isinstance(current_modifiers, list):
            current_modifiers = []
        
        previous_types = [m.get('type') for m in self._previous_battle_modifiers]
        current_types = [m.get('type') for m in current_modifiers]
        
        # Detect newly added modifiers
        if len(current_modifiers) > len(self._previous_battle_modifiers):
            new_modifiers = current_modifiers[len(self._previous_battle_modifiers):]
            for modifier in new_modifiers:
                modifier_type = modifier.get('type', 'Unknown')
                caster_name = modifier.get('caster_name', 'Opponent')
                caster_id = modifier.get('caster_id')
                
                # Only notify if the caster is the opponent (not self)
                # AND we didn't just allow this spell (which already showed its own notification)
                if caster_id and caster_id != self.state.game.player_id:
                    # Skip if we just came from allowing this spell
                    # (the _handle_counter_spell_allow already showed a notification)
                    if hasattr(self, '_just_allowed_spell') and self._just_allowed_spell:
                        self._just_allowed_spell = False
                    else:
                        descriptions = {
                            'Civil War': 'Each player may choose up to two villagers of the same color. Both players have 2 turns left. The invader starts next turn.',
                            'Peasant War': 'Only villagers can be selected for the battle. Both players have 2 turns left. The invader starts next turn.',
                            'Blitzkrieg': "The advancing figure cannot be blocked. Both players have 2 turns left. The invader starts next turn. Ceasefire is active until the last turn."
                        }
                        desc = descriptions.get(modifier_type, 'A battle modifier is now active.')
                        
                        # Load icon for the notification
                        icon_img = self._battle_modifier_icons.get(modifier_type)
                        images = [icon_img] if icon_img else []
                        
                        self.queue_or_show_notification({
                            'message': f"{caster_name} activated {modifier_type}!\n\n{desc}",
                            'actions': ['ok'],
                            'images': images,
                            'icon': "magic",
                            'title': f"{modifier_type}"
                        })
        
        # Update tracked state
        self._previous_battle_modifiers = list(current_modifiers)
    

    def _show_counter_spell_dialogue(self):
        """Show dialogue asking player to counter or allow spell."""
        if not self.state.game or not self.state.game.pending_spell_id:
            return
        
        # Use cached spell data and castable spells (no network request, no image loading)
        spell_data = self.pending_spell_details or {}
        spell_name = spell_data.get('spell_name', 'a spell')
        spell_family_name = spell_data.get('spell_family_name', spell_name)
        
        # Get spell icon for the dialogue
        spell_images = self._get_spell_icon_image(spell_family_name)
        
        # Use cached castable spells
        castable_spells = self._cached_castable_spells or []
        can_counter = len(castable_spells) > 0
        
        # Show appropriate dialogue based on whether player can counter
        if can_counter:
            message = f"Opponent cast {spell_name}!\n\nDo you want to counter it or allow it?"
            actions = ['counter', 'allow']
        else:
            message = f"Opponent cast {spell_name}!\n\nYou don't have the cards to counter.\nYou must allow it."
            actions = ['allow']
        
        self.make_dialogue_box(
            message=message,
            actions=actions,
            images=spell_images,
            icon="magic",
            title="Counter Spell?" if can_counter else "Allow Spell"
        )
    
    def check_auto_fill_notification(self):
        """Check for auto-fill notification and show dialogue if needed."""
        if not self.state.game or not self.state.game.pending_auto_fill:
            return
        
        auto_fill = self.state.game.pending_auto_fill
        main_filled = auto_fill.get('main_cards_filled', 0)
        side_filled = auto_fill.get('side_cards_filled', 0)
        cards_data = auto_fill.get('cards', [])
        
        # Build message
        message_parts = []
        if main_filled > 0:
            message_parts.append(f"{main_filled} main card{'s' if main_filled > 1 else ''}")
        if side_filled > 0:
            message_parts.append(f"{side_filled} side card{'s' if side_filled > 1 else ''}")
        
        message = f"Your hand was below the minimum. Refilled: {' and '.join(message_parts)}."
        
        # Create card images from the cards data
        from game.components.cards.card_img import CardImg
        card_images = []
        for card_data in cards_data:
            card_img = CardImg(self.window, card_data['suit'], card_data['rank'])
            card_images.append(card_img.front_img)
        
        # Queue or show dialogue
        self.queue_or_show_notification({
            'message': message,
            'actions': ['ok'],
            'images': card_images,
            'icon': "loot",
            'title': "Cards Refilled"
        })
        
        # Clear the notification
        self.state.game.pending_auto_fill = None
    
    def check_post_battle_side_cards(self):
        """Check for post-battle side card draw notification and show dialogue."""
        if not self.state.game or not self.state.game.pending_post_battle_side_cards:
            return

        cards_data = self.state.game.pending_post_battle_side_cards
        count = len(cards_data)
        if count == 0:
            self.state.game.pending_post_battle_side_cards = None
            return

        message = f"New round! You drew {count} side card{'s' if count > 1 else ''}."

        # Create card images from the cards data
        from game.components.cards.card_img import CardImg
        card_images = []
        for card_data in cards_data:
            card_img = CardImg(self.window, card_data['suit'], card_data['rank'])
            card_images.append(card_img.front_img)

        # Queue or show dialogue
        self.queue_or_show_notification({
            'message': message,
            'actions': ['ok'],
            'images': card_images,
            'icon': "loot",
            'title': "Side Cards Drawn"
        })

        # Clear the notification
        self.state.game.pending_post_battle_side_cards = None

    def check_opponent_turn_notification(self):
        """Check for opponent turn summary and show dialogue if needed."""
        if not self.state.game or not self.state.game.pending_opponent_turn_summary:
            return
        
        summary = self.state.game.pending_opponent_turn_summary
        opponent_name = summary.get('opponent_name', 'Opponent')
        action = summary.get('action')
        
        print(f"\n{'='*60}")
        print(f"[OPPONENT_TURN_CLIENT] Processing notification")
        print(f"[OPPONENT_TURN_CLIENT] Summary: {summary}")
        print(f"[OPPONENT_TURN_CLIENT] Action: {action}")
        print(f"{'='*60}\n")
        print(f"[WELCOME_MSG] Processing notification - action: {action}")
        print(f"{'='*60}\n")
        
        # Check for game start notification
        if action == 'game_start':
            maharaja_data = summary.get('maharaja', {})
            is_turn = summary.get('is_turn', False)
            is_invader = summary.get('is_invader', False)
            
            # Create Figure object from maharaja data to generate FieldFigureIcon
            from game.components.figures.figure import Figure
            from game.components.figures.figure_manager import FigureManager
            
            # Get families for figure reconstruction
            figure_manager = FigureManager()
            families = figure_manager.families
            
            # Convert maharaja data to Figure instance
            maharaja_figure = self._create_figure_from_data(maharaja_data, families)
            
            if maharaja_figure:
                print(f"[WELCOME_MSG] Creating FieldFigureIcon for {maharaja_figure.name}")
                print(f"[WELCOME_MSG] Figure has {len(maharaja_figure.cards)} cards")
                
                # Create FieldFigureIcon for the maharaja (same as explosion spell)
                from game.components.figures.figure_icon import FieldFigureIcon
                maharaja_icon = FieldFigureIcon(
                    self.window,
                    self.state.game,
                    maharaja_figure,
                    is_visible=True,
                    x=0,
                    y=0,
                    all_player_figures=[maharaja_figure],
                    resources_data={}
                )
                
                # Load invader/defender icon based on player's actual role
                # IMPORTANT: Logic is inverted in the icon naming
                # is_invader=True (offensive/red) -> show invader_passive.png
                # is_invader=False (defensive/black) -> show invader_active.png
                import os
                invader_icon_name = 'invader_passive.png' if is_invader else 'invader_active.png'
                invader_icon_path = os.path.join('img', 'status_icons', invader_icon_name)
                
                # Build images list - maharaja_icon will be drawn by DialogueBox via draw_icon()
                # Don't manually scale the invader icon - let DialogueBox handle sizing
                images = [maharaja_icon]
                if os.path.exists(invader_icon_path):
                    invader_img = pygame.image.load(invader_icon_path)
                    images.append(invader_img)
                
                print(f"[WELCOME_MSG] Showing dialogue with {len(images)} images")
                
                # Build welcome message with game information
                role_text = "invader" if is_invader else "defender"
                maharaja_name = maharaja_figure.name
                turn_status = "It's your turn!" if is_turn else "It's your opponent's turn."
                
                turn_msg = f"Hello Adventurer!\n\nYou are playing with the {maharaja_name} and start with the {role_text} role. You are fighting {opponent_name}.\n\n{turn_status}"
                
                self.queue_or_show_notification({
                    'message': turn_msg,
                    'actions': ['ok'],
                    'images': images,
                    'icon': "loot",
                    'title': "Game Started"
                })
            
            # Clear the notification
            self.state.game.pending_opponent_turn_summary = None
            return
        
        # Check if action is missing, None, or the string 'unknown'
        if not action or action == 'unknown':
            # Generic message if no specific action detected
            message = summary.get('message', f"{opponent_name} completed their turn.")
            self.queue_or_show_notification({
                'message': f"{message}\n\nIt's your turn now!",
                'actions': ['ok'],
                'icon': "info",
                'title': "Your Turn"
            })
        else:
            # Build message based on the action (action is a dict)
            action_type = action.get('type')
            action_message = action.get('message', 'completed their turn')
            spell_name = action.get('spell_name', '')
            
            print(f"[OPPONENT_TURN_CLIENT] Processing action: type={action_type}, spell={repr(spell_name)}, has_new_cards={'new_cards' in action}")
            if 'new_cards' in action:
                print(f"[OPPONENT_TURN_CLIENT] new_cards present with {len(action.get('new_cards', []))} cards")
            
            # Load icons for actions
            images = []
            
            # Special handling for Forced Deal with card details
            if (action_type == 'spell' and spell_name == 'Forced Deal' and 
                'cards_given' in action and 'cards_received' in action):
                
                from game.components.cards.card import Card
                import os
                
                cards_given = action.get('cards_given', [])
                cards_received = action.get('cards_received', [])
                
                print(f"[FORCED_DEAL_CLIENT] Showing cards: gave {len(cards_given)}, received {len(cards_received)}")
                
                # Add received cards (show first)
                for card_data in cards_received:
                    card = Card(
                        rank=card_data['rank'],
                        suit=card_data['suit'],
                        value=card_data['value'],
                        id=card_data.get('id'),
                        type=card_data.get('type', 'main')
                    )
                    card_img = card.make_icon(self.window, self.state.game, 0, 0)
                    images.append(card_img.front_img)
                
                # Add given cards (with transparency and red cross)
                for card_data in cards_given:
                    card = Card(
                        rank=card_data['rank'],
                        suit=card_data['suit'],
                        value=card_data['value'],
                        id=card_data.get('id'),
                        type=card_data.get('type', 'main')
                    )
                    card_img = card.make_icon(self.window, self.state.game, 0, 0)
                    given_card_img = card_img.front_img.copy()
                    given_card_img.set_alpha(128)  # 50% transparency
                    
                    # Add red cross overlay
                    red_cross_path = os.path.join('img', 'new_cards', 'red_cross.png')
                    if os.path.exists(red_cross_path):
                        red_cross = pygame.image.load(red_cross_path)
                        cross_size = min(given_card_img.get_width(), given_card_img.get_height())
                        red_cross = pygame.transform.scale(red_cross, (cross_size, cross_size))
                        cross_x = (given_card_img.get_width() - cross_size) // 2
                        cross_y = (given_card_img.get_height() - cross_size) // 2
                        given_card_img.blit(red_cross, (cross_x, cross_y))
                    
                    images.append(given_card_img)
            
            # Special handling for Dump Cards with new cards
            elif (action_type == 'spell' and spell_name == 'Dump Cards' and 
                  'new_cards' in action):
                
                print(f"[DUMP_CARDS_CLIENT] ENTERING Dump Cards card display block")
                
                from game.components.cards.card import Card
                new_cards = action.get('new_cards', [])
                
                print(f"[DUMP_CARDS_CLIENT] Showing {len(new_cards)} new cards from opponent turn notification")
                print(f"[DUMP_CARDS_CLIENT] new_cards data: {new_cards}")
                
                # Add all new cards
                for card_data in new_cards:
                    card = Card(
                        rank=card_data['rank'],
                        suit=card_data['suit'],
                        value=card_data['value'],
                        id=card_data.get('id'),
                        type=card_data.get('type', 'main')
                    )
                    card_img = card.make_icon(self.window, self.state.game, 0, 0)
                    images.append(card_img.front_img)
            
            # Special handling for Poison with affected figure
            elif (action_type == 'spell' and spell_name == 'Poison' and 
                  action.get('affects_player') and action.get('target_figure_id')):
                import os
                spell_icon_path = os.path.join('img', 'spells', 'icons', action.get('spell_icon', 'poisson_portion.png'))
                if os.path.exists(spell_icon_path):
                    spell_icon_img = pygame.image.load(spell_icon_path)
                    images.append(spell_icon_img)
                # Find figure icon for the affected figure
                target_figure_id = action.get('target_figure_id')
                field_screen = self.subscreens.get('field')
                if field_screen:
                    for icon in getattr(field_screen, 'figure_icons', []):
                        if icon.figure.id == target_figure_id:
                            images.append(icon)
                            break
            
            # Load spell icon if this is a spell action (and not Forced Deal/Dump Cards/Poison with cards)
            elif action_type == 'spell' and action.get('spell_icon'):
                import os
                spell_icon_path = os.path.join('img', 'spells', 'icons', action.get('spell_icon'))
                if os.path.exists(spell_icon_path):
                    spell_icon_img = pygame.image.load(spell_icon_path)
                    images.append(spell_icon_img)
            
            # Load spell icon for infinite_hammer notification
            elif action_type == 'infinite_hammer' and action.get('spell_icon'):
                import os
                spell_icon_path = os.path.join('img', 'spells', 'icons', action.get('spell_icon'))
                if os.path.exists(spell_icon_path):
                    spell_icon_img = pygame.image.load(spell_icon_path)
                    images.append(spell_icon_img)
            
            # Load action icon for build, upgrade, pickup, or card_change actions
            elif action.get('icon'):
                import os
                action_icon_path = os.path.join('img', 'game_button', 'symbol', action.get('icon'))
                if os.path.exists(action_icon_path):
                    action_icon_img = pygame.image.load(action_icon_path)
                    images.append(action_icon_img)
            
            # Special handling for explosion - show bomb icon and destroyed figure name prominently
            if action_type == 'explosion':
                import os
                bomb_icon_path = os.path.join('img', 'spells', 'icons', 'bomb.png')
                if os.path.exists(bomb_icon_path):
                    bomb_icon_img = pygame.image.load(bomb_icon_path)
                    images.append(bomb_icon_img)
                destroyed_figure = action.get('destroyed_figure', 'a figure')
                message = f"{opponent_name} cast Explosion!\n\nYour {destroyed_figure} was destroyed.\n\nIt's your turn now!"
                message_after = None
                icon = "error"
            # Special handling for Poison on player's figure
            elif (action_type == 'spell' and spell_name == 'Poison' and 
                  action.get('affects_player') and action.get('target_figure_name')):
                target_name = action.get('target_figure_name')
                message = f"{opponent_name} cast Poison!\n\nYour {target_name} was poisoned (-6 power).\n\nIt's your turn now!"
                message_after = None
                icon = "error"
            else:
                # Split message: title before icon, details after icon
                message = f"{opponent_name}'s turn:"
                
                # Build the message after icon
                message_after = f"• {action_message}"
                
                # Add details if spell affects player
                if action.get('affects_player'):
                    details = action.get('details', '')
                    if details:
                        message_after += f"\n  > {details}"
                
                message_after += "\n\nIt's your turn now!"
                
                icon = "info"
            
            self.queue_or_show_notification({
                'message': message,
                'actions': ['ok'],
                'icon': icon,
                'title': "Your Turn",
                'images': images if images else None,
                'message_after_images': message_after if not action_type == 'explosion' else None
            })
        
        # Clear the notification
        self.state.game.pending_opponent_turn_summary = None
    
    def check_ceasefire_ended_notification(self):
        """Check if ceasefire ended and show notification if needed."""
        if not self.state.game or not self.state.game.pending_ceasefire_ended:
            return
        
        # Load ceasefire passive icon
        import os
        icon_path = os.path.join('img', 'status_icons', 'ceasefire_passive.png')
        images = []
        if os.path.exists(icon_path):
            ceasefire_img = pygame.image.load(icon_path)
            images.append(ceasefire_img)
        
        # Show notification to both players
        self.queue_or_show_notification({
            'message': "Ceasefire has ended!\n\nBattles can now begin.",
            'actions': ['ok'],
            'images': images if images else None,
            'icon': "info",
            'title': "Ceasefire Ended"
        })
        
        # Clear the notification
        self.state.game.pending_ceasefire_ended = False
    
    def check_infinite_hammer_activation(self):
        """Check if Infinite Hammer spell was just activated and show initial dialogue."""
        if not self.state.game:
            return
        
        # Check if Infinite Hammer just became active
        is_active = self.state.game.check_infinite_hammer_active()
        
        if is_active and not self.state.game.infinite_hammer_dialogue_shown:
            # Show initial dialogue explaining mode
            self.queue_or_show_notification({
                'message': "Infinite Hammer is now active!\n\nYou can build, upgrade, and pickup figures without ending your turn.\n\nCard changes and other spells are blocked.\n\nPress ESC when you're ready to end your turn.",
                'actions': ['ok'],
                'icon': "infinite_hammer",
                'title': "Infinite Hammer Active"
            })
            
            # Mark dialogue as shown and enable mode
            self.state.game.infinite_hammer_dialogue_shown = True
            self.state.game.infinite_hammer_active = True
        elif not is_active and self.state.game.infinite_hammer_active:
            # Spell is no longer active - clear client state
            self.state.game.infinite_hammer_active = False
            self.state.game.infinite_hammer_dialogue_shown = False
    
    def check_forced_advance(self):
        """Check if player must advance (turns_left <= 1) and show forced advance dialogue."""
        if not self.state.game or not self.state.game.turn:
            return
        
        # Force advance when: 1 or fewer turns left, ceasefire not active,
        # no active advance already, and dialogue not already shown.
        # Any player (invader or defender) on their last turn must advance.
        if (self.state.game.current_player.get('turns_left', 0) <= 1 and
            not self.state.game.ceasefire_active and
            not self.state.game.advancing_figure_id and
            not self.state.game.forced_advance_dialogue_shown):
            
            # Check if ANY figure can actually advance
            can_any_advance = self._check_any_figure_can_advance()
            
            if not can_any_advance:
                # No figure can advance — auto-lose the battle
                self.state.game.forced_advance_dialogue_shown = True
                self._handle_cannot_advance_loss()
                return
            
            self.state.game.pending_forced_advance = True
            self.state.game.forced_advance_dialogue_shown = True
            
            # Show notification dialogue
            import os
            icon_path = os.path.join('img', 'figures', 'state_icons', 'charge.png')
            images = []
            if os.path.exists(icon_path):
                advance_img = pygame.image.load(icon_path).convert_alpha()
                images.append(advance_img)
            
            self.queue_or_show_notification({
                'message': "Last turn!\n\nIt's time to advance a figure toward battle.\n\nGo to the field and select a figure to advance.",
                'actions': ['ok'],
                'images': images if images else None,
                'icon': None if images else "info",
                'title': "Battle Time"
            })
    
    def _check_any_figure_can_advance(self):
        """Check if any of the player's figures can be advanced given current modifiers."""
        field_screen = self.subscreens.get('field')
        if not field_screen or not hasattr(field_screen, 'categorized_figures'):
            return True  # Assume yes if we can't check
        
        own_figures = field_screen.categorized_figures.get('self', {})
        all_own_figures = []
        for field_type, fig_list in own_figures.items():
            all_own_figures.extend(fig_list)
        
        if not all_own_figures:
            return False
        
        modifiers = self.state.game.battle_modifier if isinstance(self.state.game.battle_modifier, list) else []
        modifier_types = [m.get('type') for m in modifiers]
        
        # Check if opponent's advancing figure has cannot_be_blocked
        # (would block counter-advance for all figures)
        if self.state.game.advancing_figure_id and self.state.game.advancing_player_id != self.state.game.player_id:
            for fig in all_own_figures:
                if hasattr(fig, 'id') and fig.id == self.state.game.advancing_figure_id:
                    if hasattr(fig, 'cannot_be_blocked') and fig.cannot_be_blocked:
                        return False
        
        # Blitzkrieg: defender cannot counter-advance
        if 'Blitzkrieg' in modifier_types:
            if (self.state.game.advancing_figure_id and 
                self.state.game.advancing_player_id != self.state.game.player_id):
                return False
        
        # Get icon cache for deficit checks
        icon_cache = getattr(field_screen, 'icon_cache', {})
        
        for fig in all_own_figures:
            # Skip figures that cannot attack
            if hasattr(fig, 'cannot_attack') and fig.cannot_attack:
                continue
            
            # Skip figures with resource deficit (check from icon cache)
            icon = icon_cache.get(fig.id)
            if icon and getattr(icon, 'has_deficit', False):
                continue
            
            # Peasant War / Civil War: only village figures can advance
            if 'Peasant War' in modifier_types or 'Civil War' in modifier_types:
                figure_field = getattr(fig.family, 'field', None) if hasattr(fig, 'family') else None
                if figure_field != 'village':
                    continue
            
            # This figure can advance
            return True
        
        return False
    
    def _handle_cannot_advance_loss(self):
        """Handle the case where the player cannot advance any figure — auto-lose."""
        from utils.game_service import cannot_advance_loss
        result = cannot_advance_loss(self.state.game.game_id, self.state.game.player_id)
        
        if result.get('success'):
            winner = result.get('winner', 'Opponent')
            points = result.get('points', 10)
            
            # Update game state from response
            if result.get('game'):
                self.state.game.update_from_dict(result['game'])
            
            # Reset all battle state (includes suppress_next_turn_summary)
            self._reset_battle_state()
            
            new_round = self.state.game.current_round
            
            # Mark fold result as shown so check_fold_result() doesn't double-show
            self.state.game.fold_result_shown = True
            
            self.queue_or_show_notification({
                'message': (f"You have no figures that can advance!\n\n"
                           f"{winner} wins {points} points and is now the invader.\n\n"
                           f"Round {new_round} begins. It's your turn!"),
                'actions': ['ok'],
                'icon': 'magic',
                'title': "Defeat"
            })
        else:
            error_msg = result.get('message', 'Unknown error')
            print(f"[GAME_SCREEN] Auto-loss failed: {error_msg}")
    
    def _check_any_defender_selectable(self):
        """Check if any of the opponent's figures can be selected as a defender."""
        field_screen = self.subscreens.get('field')
        if not field_screen or not hasattr(field_screen, 'categorized_figures'):
            return True  # Assume yes if we can't check
        
        opponent_figures = field_screen.categorized_figures.get('opponent', {})
        all_opponent_figures = []
        for field_type, fig_list in opponent_figures.items():
            all_opponent_figures.extend(fig_list)
        
        if not all_opponent_figures:
            return False
        
        # Get advancing figure for cannot_be_blocked check
        advancing_figure = None
        if self.state.game.advancing_figure_id:
            for fig in getattr(field_screen, 'figures', []):
                if fig.id == self.state.game.advancing_figure_id:
                    advancing_figure = fig
                    break
        
        advancing_cannot_be_blocked = (
            advancing_figure and 
            hasattr(advancing_figure, 'cannot_be_blocked') and 
            advancing_figure.cannot_be_blocked
        )
        
        modifiers = self.state.game.battle_modifier if isinstance(self.state.game.battle_modifier, list) else []
        modifier_types = [m.get('type') for m in modifiers]
        has_blitzkrieg = 'Blitzkrieg' in modifier_types
        village_only = 'Peasant War' in modifier_types or 'Civil War' in modifier_types
        skip_must_be_attacked = advancing_cannot_be_blocked or has_blitzkrieg
        
        eligible = []
        for fig in all_opponent_figures:
            if hasattr(fig, 'cannot_defend') and fig.cannot_defend:
                continue
            if hasattr(fig, 'cannot_be_targeted') and fig.cannot_be_targeted:
                continue
            if village_only and hasattr(fig, 'family') and fig.family.field != 'village':
                continue
            eligible.append(fig)
        
        if not eligible:
            return False
        
        # Check must_be_attacked constraint
        if not skip_must_be_attacked:
            must_be_attacked = [f for f in eligible if hasattr(f, 'must_be_attacked') and f.must_be_attacked]
            if must_be_attacked:
                return True  # At least one must_be_attacked figure exists
        
        return len(eligible) > 0
    
    def _handle_defender_no_figures_loss(self):
        """Handle the case where the defender has no valid figures — defender auto-loses."""
        from utils.game_service import defender_no_figures_loss
        result = defender_no_figures_loss(self.state.game.game_id, self.state.game.player_id)
        
        if result.get('success'):
            loser = result.get('loser', 'Opponent')
            points = result.get('points', 10)
            
            # Update game state from response
            if result.get('game'):
                self.state.game.update_from_dict(result['game'])
            
            # Reset all battle state
            self._reset_battle_state()
            
            new_round = self.state.game.current_round
            
            # Mark fold result as shown so check_fold_result() doesn't double-show
            self.state.game.fold_result_shown = True
            
            self.queue_or_show_notification({
                'message': (f"{loser} has no valid figures for battle!\n\n"
                           f"You win {points} points.\n\n"
                           f"You are now the invader.\n\n"
                           f"Round {new_round} begins. It's your turn!"),
                'actions': ['ok'],
                'icon': 'magic',
                'title': "Victory!"
            })
        else:
            error_msg = result.get('message', 'Unknown error')
            print(f"[GAME_SCREEN] Defender auto-loss failed: {error_msg}")
    
    def _get_battle_modifier_info(self):
        """Get battle modifier summary text and icon images for notification dialogues."""
        modifiers = self.state.game.battle_modifier if isinstance(self.state.game.battle_modifier, list) else []
        if not modifiers:
            return "", []
        
        modifier_texts = []
        modifier_images = []
        for mod in modifiers:
            mod_type = mod.get('type', 'Unknown')
            icon_img = self._battle_modifier_icons.get(mod_type)
            if icon_img:
                modifier_images.append(icon_img)
            if mod_type == 'Peasant War':
                modifier_texts.append("Peasant War: Only village figures can be selected for battle.")
            elif mod_type == 'Blitzkrieg':
                modifier_texts.append("Blitzkrieg: The advancing figure cannot be blocked. Ceasefire is active until the last turn.")
            elif mod_type == 'Civil War':
                modifier_texts.append("Civil War: Each player selects two village figures of the same color for battle.")
        
        text = "\n".join(modifier_texts)
        return text, modifier_images

    def check_own_advance_notification(self):
        """Check if Blitzkrieg combine-advance-and-select is needed.
        For normal advances, the persistent prompt replaces the dialogue."""
        if not self.state.game or not self.state.game.pending_own_advance_notification:
            return
        
        figure_name = self.state.game.own_advance_figure_name or "your figure"
        
        # Check active battle modifiers
        modifiers = self.state.game.battle_modifier if isinstance(self.state.game.battle_modifier, list) else []
        modifier_types = [m.get('type') for m in modifiers]
        has_blitzkrieg = 'Blitzkrieg' in modifier_types
        
        # Blitzkrieg: combine advance notification with defender selection into one dialogue
        # (Under Blitzkrieg the turn stays with the invader, so they need a single combined dialogue)
        if has_blitzkrieg:
            self.state.game.pending_own_advance_notification = False
            # Pre-empt the separate defender selection dialogue
            self.state.game.pending_defender_selection = True
            self.state.game.defender_selection_dialogue_shown = True
            
            # Gather icons (include second CW figure if present)
            images = []
            if self.state.game.advancing_figure_id:
                field_screen = self.subscreens.get('field')
                if field_screen:
                    for icon in getattr(field_screen, 'figure_icons', []):
                        if hasattr(icon, 'figure') and icon.figure.id == self.state.game.advancing_figure_id:
                            images.append(icon)
                        if (self.state.game.advancing_figure_id_2 and
                            hasattr(icon, 'figure') and icon.figure.id == self.state.game.advancing_figure_id_2):
                            images.append(icon)
            modifier_text, modifier_icons = self._get_battle_modifier_info()
            images.extend(modifier_icons)
            
            message = (f"You advanced {figure_name} toward battle!\n\n"
                       f"Blitzkrieg is active — your opponent cannot counter-advance.\n\n"
                       f"Select one of your opponent's figures to face {figure_name} in battle.")
            
            self.queue_or_show_notification({
                'message': message,
                'actions': ['got it!'],
                'images': images if images else None,
                'icon': None if images else "info",
                'title': "Blitzkrieg Advance"
            })
            return
        
        # For normal/Civil War/Peasant War advances: no dialogue needed.
        # The persistent prompt (YOUR FIGURE ADVANCING) already shows the status.
        self.state.game.pending_own_advance_notification = False

    def check_opponent_advance_notification(self):
        """Check if opponent advanced a figure and show notification."""
        if not self.state.game or not self.state.game.pending_advance_notification:
            return
        
        # Check if advancing figure has cannot_be_blocked
        advancing_fig = None
        advancing_icon = None
        has_cannot_be_blocked = False
        advancing_description = "a figure"
        if self.state.game.advancing_figure_id:
            field_screen = self.subscreens.get('field')
            if field_screen:
                for fig in getattr(field_screen, 'figures', []):
                    if fig.id == self.state.game.advancing_figure_id:
                        advancing_fig = fig
                        has_cannot_be_blocked = hasattr(fig, 'cannot_be_blocked') and fig.cannot_be_blocked
                        # Build anonymous description: field type + card count
                        field_type = getattr(fig.family, 'field', 'unknown') if hasattr(fig, 'family') else 'unknown'
                        card_count = len(fig.cards) if hasattr(fig, 'cards') else '?'
                        advancing_description = f"a {field_type} figure with {card_count} cards"
                        break
                # Find the advancing figure's FieldFigureIcon for display
                for icon in getattr(field_screen, 'figure_icons', []):
                    if hasattr(icon, 'figure') and icon.figure.id == self.state.game.advancing_figure_id:
                        advancing_icon = icon
                        break
        
        # Always show the charge_opponent icon (not the hidden field icon)
        images = []
        import os
        icon_path = os.path.join('img', 'figures', 'state_icons', 'charge_opponent.png')
        if os.path.exists(icon_path):
            advance_img = pygame.image.load(icon_path).convert_alpha()
            images.append(advance_img)
        
        # Check for battle modifiers
        modifiers = self.state.game.battle_modifier if isinstance(self.state.game.battle_modifier, list) else []
        modifier_types = [m.get('type') for m in modifiers]
        
        # Add battle modifier icons
        modifier_text, modifier_icons = self._get_battle_modifier_info()
        images.extend(modifier_icons)
        
        # Build message with prominent modifier context
        # Message before images: "Your opponent advanced..."
        # Message after images: options/instructions
        message_after = None
        if 'Blitzkrieg' in modifier_types and not has_cannot_be_blocked:
            title = "Blitzkrieg — Opponent Advancing"
            message = f"Your opponent advanced {advancing_description}!"
            message_after = (f"Blitzkrieg is active — you cannot counter-advance.\n\n"
                       f"Spend your turn on something else. The opponent will select your battle figure.")
        elif has_cannot_be_blocked:
            title = "Opponent Advancing"
            message = f"Your opponent advanced {advancing_description}!"
            message_after = (f"This figure cannot be blocked — you cannot counter-advance.\n\n"
                       f"Spend your turn on something else (e.g. build figures, cast spells, or manage your hand). "
                       f"After your turn, the opponent will select one of your figures to face them in battle.")
            if modifier_text:
                message_after += f"\n\n{modifier_text}"
        elif 'Civil War' in modifier_types:
            title = "Civil War — Opponent Advancing"
            message = f"Your opponent advanced {advancing_description}!"
            message_after = (f"Civil War is active — you may counter-advance with up to two village figures of the same color, "
                       f"or spend your turn normally and the opponent will select your battle figures.")
        elif 'Peasant War' in modifier_types:
            title = "Peasant War — Opponent Advancing"
            message = f"Your opponent advanced {advancing_description}!"
            message_after = (f"Peasant War is active — only village figures may be used for battle.\n\n"
                       f"You can counter-advance with a village figure, or spend your turn normally "
                       f"and the opponent will select your battle figure.")
        else:
            title = "Opponent Advancing"
            message = f"Your opponent advanced {advancing_description}!"
            message_after = (f"You have two options:\n"
                       f"• Counter-advance: select one of your own figures on the field and advance it. "
                       f"Your figure will face the opponent's figure in battle.\n"
                       f"• Spend your turn normally (build figures, cast spells, etc.). "
                       f"The opponent will then choose which of your figures faces them in battle.")
            if modifier_text:
                message_after += f"\n\n{modifier_text}"
        
        self.queue_or_show_notification({
            'message': message,
            'actions': ['ok'],
            'images': images if images else None,
            'icon': None if images else "info",
            'title': title,
            'message_after_images': message_after
        })
        
        self.state.game.pending_advance_notification = False

    def check_defender_selection_needed(self):
        """Check if the advancing player's turn returned and they need to select a defender."""
        if not self.state.game or not self.state.game.pending_defender_selection:
            return
        
        # Don't re-queue if dialogue was already shown
        if self.state.game.defender_selection_dialogue_shown:
            return
        
        # Check if any opponent figure is selectable before showing dialogue
        # If none are eligible, the defender auto-loses
        if not self._check_any_defender_selectable():
            self.state.game.defender_selection_dialogue_shown = True
            self._handle_defender_no_figures_loss()
            return
        
        # Find the advancing figure name(s) and icon(s)
        advancing_figure_name = "your figure"
        advancing_icons = []
        if self.state.game.advancing_figure_id:
            field_screen = self.subscreens.get('field')
            if field_screen:
                for fig in getattr(field_screen, 'figures', []):
                    if fig.id == self.state.game.advancing_figure_id:
                        advancing_figure_name = fig.name
                        break
                # Find the FieldFigureIcon(s) for display
                for icon in getattr(field_screen, 'figure_icons', []):
                    if hasattr(icon, 'figure') and icon.figure.id == self.state.game.advancing_figure_id:
                        advancing_icons.append(icon)
                    if (self.state.game.advancing_figure_id_2 and
                        hasattr(icon, 'figure') and icon.figure.id == self.state.game.advancing_figure_id_2):
                        advancing_icons.append(icon)
                        advancing_figure_name = "your figures"
        
        images = []
        if advancing_icons:
            images.extend(advancing_icons)
        else:
            import os
            icon_path = os.path.join('img', 'figures', 'state_icons', 'charge.png')
            if os.path.exists(icon_path):
                advance_img = pygame.image.load(icon_path).convert_alpha()
                images.append(advance_img)
        
        # Build message with battle modifier context
        base_msg = f"Your opponent did not counter-advance.\n\nSelect one of your opponent's figures to face {advancing_figure_name} in battle."
        
        modifiers = self.state.game.battle_modifier if isinstance(self.state.game.battle_modifier, list) else []
        modifier_types = [m.get('type') for m in modifiers]
        
        if 'Peasant War' in modifier_types:
            base_msg += "\n\nPeasant War is active — you may only select village figures."
        elif 'Civil War' in modifier_types:
            base_msg += "\n\nCivil War is active — you may only select village figures."
        
        modifier_text, modifier_icons = self._get_battle_modifier_info()
        images.extend(modifier_icons)
        
        self.queue_or_show_notification({
            'message': base_msg,
            'actions': ['got it!'],
            'images': images if images else None,
            'icon': None if images else "info",
            'title': "Select Opponent's Defender"
        })
        
        # Prevent re-queuing on subsequent update cycles
        self.state.game.defender_selection_dialogue_shown = True

    def _handle_forced_advance_dialogue_response(self):
        """Handle response from forced advance confirmation — switch to field screen."""
        self.state.subscreen = 'field'
    
    def check_waiting_for_defender_pick(self):
        """Check if defender (Player B) should be notified that opponent is picking their battle figure.
        Instead of a click-through dialogue, we just activate the persistent 'BATTLE INCOMING' prompt."""
        if not self.state.game or not self.state.game.pending_waiting_for_defender_pick:
            return
        
        # Don't re-activate if already shown
        if self.state.game.waiting_for_defender_pick_shown:
            return
        
        # Activate persistent prompt directly (no click-through dialogue)
        self.state.game.waiting_for_defender_pick_shown = True
    
    def check_battle_ready(self):
        """Check if both advancing and defending figures are set — battle is ready to begin.
        Sequential flow: invader (advancing player) decides first, then defender.
        Handles reconnect: skips dialogue if server already has our decision or battle_confirmed."""
        if not self.state.game or not self.state.game.pending_battle_ready:
            return
        
        # Don't re-queue if already shown
        if self.state.game.battle_ready_shown:
            return
        
        # ── Reconnect guard: battle already confirmed on server ──
        if self.state.game.battle_confirmed:
            self.state.game.battle_ready_shown = True
            self.state.game.pending_battle_ready = False

            bmc = self.state.game.battle_moves_confirmed or {}
            player_ids = [str(p['id']) for p in self.state.game.players]
            both_moves_ready = all(bmc.get(pid) for pid in player_ids)
            my_moves_ready = bmc.get(str(self.state.game.player_id))

            if both_moves_ready:
                # Both players already confirmed moves — go straight to battle
                self.battle_button.locked = False
                self.state.subscreen = 'battle'
                print("[BATTLE_READY] Reconnect: both moves confirmed — entering battle screen")
            elif my_moves_ready:
                # We confirmed but opponent hasn't — go to battle shop in waiting mode
                self.battle_button.locked = False
                self.state.game.battle_moves_phase = True
                self.state.game.battle_moves_ready = True
                self.state.game.waiting_for_opponent_battle_moves = True
                self.state.subscreen = 'battle_shop'
                shop = self.subscreens.get('battle_shop')
                if shop:
                    shop._load_bought_moves()
                    shop._battle_moves_confirmed = True
                    shop._waiting_for_opponent = True
                print("[BATTLE_READY] Reconnect: our moves confirmed — waiting for opponent")
            else:
                # Neither confirmed yet — enter battle shop normally
                self.battle_button.locked = False
                self.state.game.auto_proceed_to_battle = True
                print("[BATTLE_READY] Reconnect: battle confirmed, moves not yet selected")
            return
        
        # ── Reconnect guard: we already submitted our decision ──
        decisions = self.state.game.battle_decisions or {}
        my_decision = decisions.get(str(self.state.game.player_id))
        if my_decision == 'battle':
            self.state.game.battle_ready_shown = True
            self.state.game.waiting_for_battle_decision = True
            print("[BATTLE_READY] Reconnect: our decision already recorded — resuming wait")
            return
        
        is_advancing = (self.state.game.advancing_player_id == self.state.game.player_id)
        
        # Find the advancing and defending figure icons from the field screen
        advancing_icons = []
        defending_icons = []
        field_screen = self.subscreens.get('field')
        if field_screen:
            for icon in getattr(field_screen, 'figure_icons', []):
                if icon.figure.id == self.state.game.advancing_figure_id:
                    advancing_icons.append(icon)
                if self.state.game.advancing_figure_id_2 and icon.figure.id == self.state.game.advancing_figure_id_2:
                    advancing_icons.append(icon)
                if icon.figure.id == self.state.game.defending_figure_id:
                    defending_icons.append(icon)
                if self.state.game.defending_figure_id_2 and icon.figure.id == self.state.game.defending_figure_id_2:
                    defending_icons.append(icon)
        
        # Own figures always on the left, with "vs." separator between groups
        # Create a "vs." text surface at the target image height to avoid distortion
        target_height = settings.DIALOGUE_BOX_IMG_HEIGHT
        vs_font_size = max(12, target_height // 3)
        vs_font = pygame.font.Font(settings.FONT_PATH, vs_font_size)
        vs_font.set_bold(True)
        vs_text = vs_font.render("vs.", True, settings.TITLE_TEXT_COLOR)
        # Create transparent surface at target height with text centered
        vs_surface = pygame.Surface((vs_text.get_width() + settings.SMALL_SPACER_X * 2, target_height), pygame.SRCALPHA)
        vs_x = (vs_surface.get_width() - vs_text.get_width()) // 2
        vs_y = (target_height - vs_text.get_height()) // 2
        vs_surface.blit(vs_text, (vs_x, vs_y))
        
        if is_advancing:
            images = advancing_icons + [vs_surface] + defending_icons
        else:
            images = defending_icons + [vs_surface] + advancing_icons
        
        # Build description of opponent's figure(s) for the message
        opponent_figure_desc = ""
        if field_screen:
            opponent_fig_ids = []
            if is_advancing:
                # Invader's opponent is the defender
                opponent_fig_ids.append(self.state.game.defending_figure_id)
                if self.state.game.defending_figure_id_2:
                    opponent_fig_ids.append(self.state.game.defending_figure_id_2)
            else:
                # Defender's opponent is the invader
                opponent_fig_ids.append(self.state.game.advancing_figure_id)
                if self.state.game.advancing_figure_id_2:
                    opponent_fig_ids.append(self.state.game.advancing_figure_id_2)
            
            fig_descs = []
            for fig_id in opponent_fig_ids:
                for fig in getattr(field_screen, 'figures', []):
                    if fig.id == fig_id:
                        field_type = getattr(fig.family, 'field', 'unknown') if hasattr(fig, 'family') else 'unknown'
                        card_count = len(fig.cards) if hasattr(fig, 'cards') else '?'
                        fig_descs.append(f"a {field_type} figure with {card_count} cards")
                        break
            if fig_descs:
                opponent_figure_desc = f"\n\nYour opponent's figure: {', and '.join(fig_descs)}."
        
        if is_advancing:
            # --- Invader sees fight/fold dialogue immediately ---
            self.battle_button.locked = False
            
            message = ("Both battle figures have been selected!\n\n"
                       "You are the attacker."
                       f"{opponent_figure_desc}\n\n"
                       "Do you want to fight or fold?")
            
            self.queue_or_show_notification({
                'message': message,
                'actions': ['to battle!', 'fold'],
                'images': images if images else None,
                'icon': None if images else 'magic',
                'title': "Battle Phase Begins"
            })
            
            if field_screen:
                field_screen.defender_selection_mode = False
                field_screen._reset_defender_selectable()
            
            self.state.game.battle_ready_shown = True
        else:
            # --- Defender: wait for invader's decision first ---
            decisions = self.state.game.battle_decisions or {}
            invader_decided = decisions.get(str(self.state.game.advancing_player_id)) == 'battle'
            
            if not invader_decided:
                # Invader hasn't decided yet — waiting prompt is drawn in draw()
                return
            
            # Invader chose to fight — now show fight/fold dialogue to defender
            self.battle_button.locked = False
            
            message = ("Both battle figures have been selected!\n\n"
                       "You are the defender.\n\n"
                       "The invader has chosen to fight."
                       f"{opponent_figure_desc}\n\n"
                       "Do you want to fight or fold?")
            
            self.queue_or_show_notification({
                'message': message,
                'actions': ['to battle!', 'fold'],
                'images': images if images else None,
                'icon': None if images else 'magic',
                'title': "Battle Phase Begins"
            })
            
            if field_screen:
                field_screen.defender_selection_mode = False
                field_screen._reset_defender_selectable()
            
            self.state.game.battle_ready_shown = True
    
    def _submit_battle_decision(self, decision):
        """Submit a battle decision (battle or fold) to the server and handle the response."""
        from utils.game_service import battle_decision
        result = battle_decision(self.state.game.game_id, self.state.game.player_id, decision)
        
        if not result.get('success'):
            print(f"[GAME_SCREEN] Battle decision failed: {result.get('message')}")
            # Reconnect fallback: if server rejects because our decision was
            # already recorded, resume waiting for the opponent's decision
            if decision == 'battle':
                self.state.game.waiting_for_battle_decision = True
            return
        
        if result.get('resolved'):
            outcome = result.get('outcome')
            if outcome == 'battle':
                # Both chose to fight — go to battle shop for move selection
                if result.get('game'):
                    self.state.game.update_from_dict(result['game'])
                self._enter_battle_moves_phase()
            elif outcome == 'fold_win':
                # One player folded
                if result.get('game'):
                    self.state.game.update_from_dict(result['game'])
                self._reset_battle_state()
                
                winner = result.get('winner', 'Opponent')
                loser = result.get('loser', 'You')
                points = result.get('points', 10)
                new_round = self.state.game.current_round
                
                if self.state.game.fold_winner_id == self.state.game.player_id:
                    title = "Victory!"
                    message = (f"{loser} has folded!\n\n"
                               f"You win {points} points.\n\n"
                               f"You are now the invader.\n\n"
                               f"Round {new_round} begins. It's your turn!")
                else:
                    title = "Defeat"
                    message = (f"You have folded.\n\n"
                               f"{winner} wins {points} points and is now the invader.\n\n"
                               f"Round {new_round} begins. It's your turn!")
                
                self.state.game.fold_result_shown = True
                self.queue_or_show_notification({
                    'message': message,
                    'actions': ['ok'],
                    'icon': 'magic',
                    'title': title
                })
        else:
            # Waiting for opponent's decision (invader chose battle, waiting for defender)
            self.state.game.waiting_for_battle_decision = True

    def _reset_battle_state(self):
        """Reset all battle-related state after fold or loss."""
        self.state.game.pending_battle_ready = False
        self.state.game.battle_ready_shown = False
        self.state.game.pending_forced_advance = False
        self.state.game.forced_advance_dialogue_shown = False
        self.state.game.pending_defender_selection = False
        self.state.game.defender_selection_dialogue_shown = False
        self.state.game.pending_waiting_for_defender_pick = False
        self.state.game.waiting_for_defender_pick_shown = False
        # Suppress the next turn notification since battle/fold result was already shown
        self.state.game.suppress_next_turn_summary = True
        self.state.game.civil_war_awaiting_second = False
        self.state.game.civil_war_defender_second = False
        self.state.game.civil_war_required_color = None
        self.state.game.waiting_for_battle_decision = False
        self.state.game.auto_proceed_to_battle = False
        # Reset battle moves phase state
        self.state.game.battle_moves_phase = False
        self.state.game.battle_moves_ready = False
        self.state.game.waiting_for_opponent_battle_moves = False
        self.state.game.both_battle_moves_ready = False
        # Reset active battle phase state
        self.state.game.in_battle_phase = False
        self.state.game.battle_turns_left = 0
        self._previous_battle_modifiers = []
        
        self.battle_button.locked = True
        
        field_screen = self.subscreens.get('field')
        if field_screen:
            field_screen.defender_selection_mode = False
            field_screen._reset_defender_selectable()
            field_screen.load_figures()

    def check_fold_result(self):
        """Check if a fold outcome was detected via polling (for the waiting player)."""
        if not self.state.game or not self.state.game.pending_fold_result:
            return
        if self.state.game.fold_result_shown:
            return
        
        self._reset_battle_state()
        
        fold_outcome = self.state.game.fold_outcome
        fold_winner_id = self.state.game.fold_winner_id
        new_round = self.state.game.current_round
        opponent_name = self.state.game.opponent_name or "Opponent"
        
        if fold_outcome != 'fold_win':
            return
        
        if fold_winner_id == self.state.game.player_id:
            title = "Victory!"
            message = (f"{opponent_name} has folded!\n\n"
                       f"You win 10 points.\n\n"
                       f"You are now the invader.\n\n"
                       f"Round {new_round} begins. It's your turn!")
        else:
            title = "Defeat"
            message = (f"{opponent_name} wins 10 points and is now the invader.\n\n"
                       f"Round {new_round} begins. It's your turn!")
        
        self.state.game.fold_result_shown = True
        self.state.game.pending_fold_result = False
        
        self.queue_or_show_notification({
            'message': message,
            'actions': ['ok'],
            'icon': 'magic',
            'title': title
        })

    def check_auto_proceed_to_battle(self):
        """Check if both players chose battle (detected via polling for the waiting player)."""
        if not self.state.game or not self.state.game.auto_proceed_to_battle:
            return
        
        self.state.game.auto_proceed_to_battle = False
        self._enter_battle_moves_phase()

    def _enter_battle_moves_phase(self):
        """Transition both players into the battle shop for mandatory battle-move selection."""
        self.state.game.battle_moves_phase = True
        self.state.game.battle_moves_ready = False
        self.state.game.waiting_for_opponent_battle_moves = False
        self.state.game.both_battle_moves_ready = False
        self.state.subscreen = 'battle_shop'

        # Reload bought moves in the battle shop screen
        shop = self.subscreens.get('battle_shop')
        if shop:
            shop._load_bought_moves()

        # Show instruction notification
        self.queue_or_show_notification({
            'message': "Both warriors chose to fight!\n\n"
                       "Select 3 battle moves before the battle begins.\n"
                       "Press 'Ready!' when done.",
            'actions': ['got it!'],
            'icon': 'magic',
            'title': 'Prepare for Battle'
        })

    def check_battle_moves_ready(self):
        """Check if both players have confirmed their battle moves (polling detection)."""
        if not self.state.game or not self.state.game.both_battle_moves_ready:
            return

        self.state.game.both_battle_moves_ready = False
        self.state.game.battle_moves_phase = False
        self.state.subscreen = 'battle'

    def check_battle_reconnect(self):
        """Detect an active 3-round battle on the server that the client isn't showing.

        On reconnect (logout/login), all client-side battle flags are reset.
        If the server still has battle_confirmed + battle_turn_player_id set
        (i.e. the battle is in progress), route straight to the battle screen.
        """
        if not self.state.game:
            return
        if not getattr(self.state.game, 'battle_reconnect_pending', False):
            return
        # Only check once per login
        self.state.game.battle_reconnect_pending = False

        # Already on the battle screen — nothing to do
        if self.state.subscreen == 'battle':
            return

        # Server indicators for an active 3-round battle
        if (self.state.game.battle_confirmed and
                self.state.game.battle_turn_player_id is not None and
                not self.state.game.in_battle_phase):
            print("[BATTLE_RECONNECT] Detected active battle on server — entering battle screen")
            self.battle_button.locked = False
            self.state.game.in_battle_phase = True
            self.state.game.battle_turns_left = 3  # will be synced by battle screen poll
            self.state.subscreen = 'battle'

    def _handle_battle_ready_response(self):
        """Handle response from battle-ready notification — switch to battle screen."""
        self.state.subscreen = 'battle'
    
    def _draw_forced_advance_prompt(self):
        """Draw a persistent prompt indicating player must advance a figure."""
        # Create prompt text
        target_prompt_font = pygame.font.Font(settings.FONT_PATH, settings.FIELD_TITLE_FONT_SIZE)
        prompt_text = "BATTLE TIME"
        prompt_surface = target_prompt_font.render(prompt_text, True, (255, 200, 100))  # Orange
        
        # Create instruction text
        cancel_font = pygame.font.Font(settings.FONT_PATH, settings.FIELD_TITLE_FONT_SIZE - 2)
        instruction_text = "Select a figure on the field and advance it toward battle"
        instruction_surface = cancel_font.render(instruction_text, True, (255, 230, 150))  # Light orange
        
        # Create background box for better visibility
        text_width = max(prompt_surface.get_width(), instruction_surface.get_width())
        text_height = prompt_surface.get_height() + instruction_surface.get_height() + 10
        padding = 20
        
        box_rect = pygame.Rect(
            (settings.SCREEN_WIDTH - text_width - 2 * padding) // 2,
            settings.get_y(0.02),
            text_width + 2 * padding,
            text_height + 2 * padding
        )
        
        # Draw semi-transparent black background
        background = pygame.Surface((box_rect.width, box_rect.height))
        background.set_alpha(200)
        background.fill((0, 0, 0))
        self.window.blit(background, box_rect.topleft)
        
        # Draw orange border for emphasis
        pygame.draw.rect(self.window, (255, 200, 100), box_rect, 4)
        
        # Draw main prompt text centered in box
        text_x = box_rect.centerx - prompt_surface.get_width() // 2
        text_y = box_rect.top + padding
        self.window.blit(prompt_surface, (text_x, text_y))
        
        # Draw instruction text below
        instruction_x = box_rect.centerx - instruction_surface.get_width() // 2
        instruction_y = text_y + prompt_surface.get_height() + 10
        self.window.blit(instruction_surface, (instruction_x, instruction_y))
        
        # Add pulsing effect to main prompt
        pulse_alpha = int(128 + 127 * abs(pygame.time.get_ticks() % 1000 - 500) / 500)
        pulse_surface = prompt_surface.copy()
        pulse_surface.set_alpha(pulse_alpha)
        self.window.blit(pulse_surface, (text_x, text_y))
    
    def _draw_own_advance_waiting_prompt(self):
        """Draw a persistent prompt showing the advancing player is waiting for opponent."""
        target_prompt_font = pygame.font.Font(settings.FONT_PATH, settings.FIELD_TITLE_FONT_SIZE - 2)
        
        # Include active modifier name in prompt header
        modifiers = self.state.game.battle_modifier if isinstance(self.state.game.battle_modifier, list) else []
        modifier_types = [m.get('type') for m in modifiers]
        if 'Civil War' in modifier_types:
            prompt_text = "YOUR FIGURE ADVANCING (Civil War)"
        elif 'Peasant War' in modifier_types:
            prompt_text = "YOUR FIGURE ADVANCING (Peasant War)"
        else:
            prompt_text = "YOUR FIGURE ADVANCING"
        prompt_surface = target_prompt_font.render(prompt_text, True, (100, 255, 150))  # Green
        
        detail_font = pygame.font.Font(settings.FONT_PATH, settings.FIELD_TITLE_FONT_SIZE - 4)
        figure_name = self.state.game.own_advance_figure_name or "your figure"
        detail_text = f"Waiting for opponent's reaction to {figure_name}"
        detail_surface = detail_font.render(detail_text, True, (180, 255, 200))  # Light green
        
        text_width = max(prompt_surface.get_width(), detail_surface.get_width())
        text_height = prompt_surface.get_height() + detail_surface.get_height() + 10
        padding = 20
        
        box_rect = pygame.Rect(
            (settings.SCREEN_WIDTH - text_width - 2 * padding) // 2,
            settings.get_y(0.02),
            text_width + 2 * padding,
            text_height + 2 * padding
        )
        
        background = pygame.Surface((box_rect.width, box_rect.height))
        background.set_alpha(200)
        background.fill((0, 0, 0))
        self.window.blit(background, box_rect.topleft)
        
        pygame.draw.rect(self.window, (100, 255, 150), box_rect, 4)
        
        text_x = box_rect.centerx - prompt_surface.get_width() // 2
        text_y = box_rect.top + padding
        self.window.blit(prompt_surface, (text_x, text_y))
        
        detail_x = box_rect.centerx - detail_surface.get_width() // 2
        detail_y = text_y + prompt_surface.get_height() + 10
        self.window.blit(detail_surface, (detail_x, detail_y))
    
    def _draw_opponent_advance_prompt(self):
        """Draw a prompt showing opponent has advanced a figure."""
        target_prompt_font = pygame.font.Font(settings.FONT_PATH, settings.FIELD_TITLE_FONT_SIZE - 2)
        
        # Include active modifier name in prompt header
        modifiers = self.state.game.battle_modifier if isinstance(self.state.game.battle_modifier, list) else []
        modifier_types = [m.get('type') for m in modifiers]
        
        # Check if advancing figure has cannot_be_blocked
        has_cannot_be_blocked = False
        if self.state.game.advancing_figure_id:
            field_screen = self.subscreens.get('field')
            if field_screen:
                for fig in getattr(field_screen, 'figures', []):
                    if fig.id == self.state.game.advancing_figure_id:
                        has_cannot_be_blocked = hasattr(fig, 'cannot_be_blocked') and fig.cannot_be_blocked
                        break
        
        if 'Blitzkrieg' in modifier_types:
            prompt_text = "OPPONENT ADVANCING (Blitzkrieg)"
        elif 'Civil War' in modifier_types:
            prompt_text = "OPPONENT ADVANCING (Civil War)"
        elif 'Peasant War' in modifier_types:
            prompt_text = "OPPONENT ADVANCING (Peasant War)"
        else:
            prompt_text = "OPPONENT ADVANCING"
        prompt_surface = target_prompt_font.render(prompt_text, True, (255, 200, 100))  # Orange
        
        detail_font = pygame.font.Font(settings.FONT_PATH, settings.FIELD_TITLE_FONT_SIZE - 4)
        if 'Blitzkrieg' in modifier_types:
            detail_text = "Blitzkrieg — you cannot counter-advance"
        elif has_cannot_be_blocked:
            detail_text = "Cannot be blocked — spend your turn on something else"
        elif 'Civil War' in modifier_types:
            detail_text = "Counter-advance with up to two village figures (same color)"
        elif 'Peasant War' in modifier_types:
            detail_text = "Counter-advance with a village figure or spend your turn"
        else:
            detail_text = "Counter-advance or spend your turn on something else"
        detail_surface = detail_font.render(detail_text, True, (255, 230, 150))  # Light orange
        
        text_width = max(prompt_surface.get_width(), detail_surface.get_width())
        text_height = prompt_surface.get_height() + detail_surface.get_height() + 10
        padding = 20
        
        box_rect = pygame.Rect(
            (settings.SCREEN_WIDTH - text_width - 2 * padding) // 2,
            settings.get_y(0.02),
            text_width + 2 * padding,
            text_height + 2 * padding
        )
        
        background = pygame.Surface((box_rect.width, box_rect.height))
        background.set_alpha(200)
        background.fill((0, 0, 0))
        self.window.blit(background, box_rect.topleft)
        
        pygame.draw.rect(self.window, (255, 200, 100), box_rect, 4)
        
        text_x = box_rect.centerx - prompt_surface.get_width() // 2
        text_y = box_rect.top + padding
        self.window.blit(prompt_surface, (text_x, text_y))
        
        detail_x = box_rect.centerx - detail_surface.get_width() // 2
        detail_y = text_y + prompt_surface.get_height() + 10
        self.window.blit(detail_surface, (detail_x, detail_y))

    def _draw_waiting_for_defender_pick_prompt(self):
        """Draw a persistent prompt for the defender waiting for opponent to pick their battle figure."""
        target_prompt_font = pygame.font.Font(settings.FONT_PATH, settings.FIELD_TITLE_FONT_SIZE - 2)
        prompt_text = "BATTLE INCOMING"
        prompt_surface = target_prompt_font.render(prompt_text, True, (255, 150, 150))  # Red-ish

        detail_font = pygame.font.Font(settings.FONT_PATH, settings.FIELD_TITLE_FONT_SIZE - 4)
        # Check if Blitzkrieg prevented counter-advance
        modifiers = self.state.game.battle_modifier if isinstance(self.state.game.battle_modifier, list) else []
        modifier_types = [m.get('type') for m in modifiers]
        if 'Blitzkrieg' in modifier_types:
            detail_text = "Blitzkrieg prevented counter-advance — opponent is selecting your battle figure"
        else:
            detail_text = "Opponent is selecting which of your figures faces them in battle"
        detail_surface = detail_font.render(detail_text, True, (255, 200, 200))  # Light red

        text_width = max(prompt_surface.get_width(), detail_surface.get_width())
        text_height = prompt_surface.get_height() + detail_surface.get_height() + 10
        padding = 20

        box_rect = pygame.Rect(
            (settings.SCREEN_WIDTH - text_width - 2 * padding) // 2,
            settings.get_y(0.02),
            text_width + 2 * padding,
            text_height + 2 * padding
        )

        background = pygame.Surface((box_rect.width, box_rect.height))
        background.set_alpha(200)
        background.fill((0, 0, 0))
        self.window.blit(background, box_rect.topleft)

        pygame.draw.rect(self.window, (255, 150, 150), box_rect, 4)

        text_x = box_rect.centerx - prompt_surface.get_width() // 2
        text_y = box_rect.top + padding
        self.window.blit(prompt_surface, (text_x, text_y))

        detail_x = box_rect.centerx - detail_surface.get_width() // 2
        detail_y = text_y + prompt_surface.get_height() + 10
        self.window.blit(detail_surface, (detail_x, detail_y))

        # Add pulsing effect
        pulse_alpha = int(128 + 127 * abs(pygame.time.get_ticks() % 1000 - 500) / 500)
        pulse_surface = prompt_surface.copy()
        pulse_surface.set_alpha(pulse_alpha)
        self.window.blit(pulse_surface, (text_x, text_y))

    def _draw_waiting_for_battle_decision_prompt(self):
        """Draw a persistent prompt while waiting for opponent's battle/fold decision."""
        target_prompt_font = pygame.font.Font(settings.FONT_PATH, settings.FIELD_TITLE_FONT_SIZE - 2)
        is_advancing = (self.state.game.advancing_player_id == self.state.game.player_id)
        
        if is_advancing:
            prompt_text = "WAITING FOR DEFENDER"
            detail_text = "You chose to fight — waiting for the defender to decide"
        else:
            prompt_text = "WAITING FOR INVADER"
            detail_text = "The invader is deciding whether to fight or fold"
        
        prompt_surface = target_prompt_font.render(prompt_text, True, (200, 200, 100))  # Yellow-ish

        detail_font = pygame.font.Font(settings.FONT_PATH, settings.FIELD_TITLE_FONT_SIZE - 4)
        detail_surface = detail_font.render(detail_text, True, (220, 220, 150))  # Light yellow

        text_width = max(prompt_surface.get_width(), detail_surface.get_width())
        text_height = prompt_surface.get_height() + detail_surface.get_height() + 10
        padding = 20

        box_rect = pygame.Rect(
            (settings.SCREEN_WIDTH - text_width - 2 * padding) // 2,
            settings.get_y(0.02),
            text_width + 2 * padding,
            text_height + 2 * padding
        )

        background = pygame.Surface((box_rect.width, box_rect.height))
        background.set_alpha(200)
        background.fill((0, 0, 0))
        self.window.blit(background, box_rect.topleft)

        pygame.draw.rect(self.window, (200, 200, 100), box_rect, 4)

        text_x = box_rect.centerx - prompt_surface.get_width() // 2
        text_y = box_rect.top + padding
        self.window.blit(prompt_surface, (text_x, text_y))

        detail_x = box_rect.centerx - detail_surface.get_width() // 2
        detail_y = text_y + prompt_surface.get_height() + 10
        self.window.blit(detail_surface, (detail_x, detail_y))

        # Add pulsing effect
        pulse_alpha = int(128 + 127 * abs(pygame.time.get_ticks() % 1000 - 500) / 500)
        pulse_surface = prompt_surface.copy()
        pulse_surface.set_alpha(pulse_alpha)
        self.window.blit(pulse_surface, (text_x, text_y))

    def _draw_select_defender_prompt(self):
        """Draw a persistent prompt for the advancing player to select an opponent's defender."""
        target_prompt_font = pygame.font.Font(settings.FONT_PATH, settings.FIELD_TITLE_FONT_SIZE)
        prompt_text = "SELECT OPPONENT'S DEFENDER"
        prompt_surface = target_prompt_font.render(prompt_text, True, (100, 200, 255))  # Blue

        detail_font = pygame.font.Font(settings.FONT_PATH, settings.FIELD_TITLE_FONT_SIZE - 4)
        
        # Build detail text based on active battle modifiers and must_be_attacked
        detail_text = "Go to the field and select an opponent figure to face your advance"
        
        # Check active battle modifiers
        modifiers = self.state.game.battle_modifier if isinstance(self.state.game.battle_modifier, list) else []
        modifier_types = [m.get('type') for m in modifiers]
        
        if 'Peasant War' in modifier_types:
            detail_text = "Peasant War active — select an opponent's village figure"
        elif 'Civil War' in modifier_types:
            detail_text = "Civil War active — select an opponent's village figure"
        else:
            # Check if must_be_attacked constraint applies
            field_screen = self.subscreens.get('field')
            has_must_be_attacked = False
            if field_screen:
                for fig in getattr(field_screen, 'figures', []):
                    if (fig.player_id != self.state.game.player_id and
                        hasattr(fig, 'must_be_attacked') and fig.must_be_attacked and
                        not (hasattr(fig, 'cannot_defend') and fig.cannot_defend) and
                        not (hasattr(fig, 'cannot_be_targeted') and fig.cannot_be_targeted)):
                        has_must_be_attacked = True
                        break
            if has_must_be_attacked:
                detail_text = "Select a figure with 'Must Be Attacked' first"
            else:
                detail_text = "Select any opponent figure on the field"
        
        detail_surface = detail_font.render(detail_text, True, (180, 220, 255))  # Light blue

        text_width = max(prompt_surface.get_width(), detail_surface.get_width())
        text_height = prompt_surface.get_height() + detail_surface.get_height() + 10
        padding = 20

        box_rect = pygame.Rect(
            (settings.SCREEN_WIDTH - text_width - 2 * padding) // 2,
            settings.get_y(0.02),
            text_width + 2 * padding,
            text_height + 2 * padding
        )

        background = pygame.Surface((box_rect.width, box_rect.height))
        background.set_alpha(200)
        background.fill((0, 0, 0))
        self.window.blit(background, box_rect.topleft)

        pygame.draw.rect(self.window, (100, 200, 255), box_rect, 4)

        text_x = box_rect.centerx - prompt_surface.get_width() // 2
        text_y = box_rect.top + padding
        self.window.blit(prompt_surface, (text_x, text_y))

        detail_x = box_rect.centerx - detail_surface.get_width() // 2
        detail_y = text_y + prompt_surface.get_height() + 10
        self.window.blit(detail_surface, (detail_x, detail_y))

        # Pulsing effect
        pulse_alpha = int(128 + 127 * abs(pygame.time.get_ticks() % 1000 - 500) / 500)
        pulse_surface = prompt_surface.copy()
        pulse_surface.set_alpha(pulse_alpha)
        self.window.blit(pulse_surface, (text_x, text_y))

    def _handle_infinite_hammer_esc(self, events):
        """Handle ESC key press during Infinite Hammer mode to prompt for turn end confirmation."""
        for event in events:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    # Show confirmation dialogue
                    self.make_dialogue_box(
                        message="Are you sure you want to end Infinite Hammer mode and pass your turn to your opponent?",
                        actions=['yes', 'no'],
                        icon="infinite_hammer",
                        title="End Turn?"
                    )
                    return True
        return False
    
    def _end_infinite_hammer_mode(self):
        """End Infinite Hammer mode and send request to server to flip turn."""
        try:
            import requests
            from config import settings
            
            response = requests.post(
                f'{settings.SERVER_URL}/spells/end_infinite_hammer',
                json={
                    'game_id': self.state.game.game_id,
                    'player_id': self.state.game.player_id
                }
            )
            
            if response.status_code == 200:
                # Success - clear client state
                self.state.game.infinite_hammer_active = False
                self.state.game.infinite_hammer_dialogue_shown = False
                
                # Update game state to reflect turn flip
                self.state.game.update()
                
                print(f"[INFINITE_HAMMER] Mode ended successfully")
            else:
                error_msg = response.json().get('message', 'Unknown error')
                print(f"[INFINITE_HAMMER] Failed to end mode: {error_msg}")
                self.state.set_msg(f"Error ending Infinite Hammer: {error_msg}")
        
        except Exception as e:
            print(f"[INFINITE_HAMMER] Error ending mode: {str(e)}")
            self.state.set_msg(f"Error ending Infinite Hammer mode: {str(e)}")
    
    def _handle_counter_spell_counter(self):
        """Handle player choosing to counter the spell."""
        if not self.state.game or not self.state.game.pending_spell_id:
            return
        
        # Use cached pending spell details and castable spells (no network request, no image loading)
        try:
            spell_data = self.pending_spell_details or {}
            spell_name = spell_data.get('spell_name', 'Unknown')
            
            # Use cached castable spells
            castable_spells = self._cached_castable_spells or []
            
            if not castable_spells:
                self.make_dialogue_box(
                    message=f"You don't have the cards to counter {spell_name}.\nYou'll need to allow it.",
                    actions=['allow'],
                    icon="error",
                    title="Cannot Counter"
                )
                # Don't clear need_to_respond_to_spell - dialogue will handle the response
                return
            
            # Show counter spell selection
            self._show_counter_spell_selection(castable_spells, spell_name)
            
        except Exception as e:
            print(f"[COUNTER_SPELL] Error: {str(e)}")
            self.make_dialogue_box(
                message=f"Error loading counter spells: {str(e)}",
                actions=['ok'],
                icon="error",
                title="Error"
            )
            self.need_to_respond_to_spell = False
    
    def _handle_counter_spell_allow(self):
        """Handle player choosing to allow the spell."""
        if not self.state.game or not self.state.game.pending_spell_id:
            return
        
        from utils import spell_service
        
        # Save spell data before clearing cache (needed for icon lookup)
        spell_data = self.pending_spell_details or {}
        
        result = spell_service.allow_spell(
            player_id=self.state.game.player_id,
            game_id=self.state.game.game_id,
            pending_spell_id=self.state.game.pending_spell_id
        )
        
        if result.get('success'):
            self.need_to_respond_to_spell = False
            
            # Clear spell cache immediately so next spell gets fresh data
            self.pending_spell_details = None
            self._cached_castable_spells = None
            self._pending_spell_fetch_ready = False
            
            # Mark that we just allowed a spell so check_battle_modifier_changes
            # doesn't show a duplicate notification for the same modifier
            self._just_allowed_spell = True
            
            # Update game state directly from response (no server call needed)
            if result.get('game'):
                self.state.game.update_from_dict(result['game'])
            
            # Trigger start_turn so auto-fill fires
            # (update_from_dict sets turn state, preventing update() from detecting the change)
            if self.state.game.turn:
                self.state.game._handle_start_turn()
                # Clear stale opponent turn summary — we already show our own spell notification
                self.state.game.pending_opponent_turn_summary = None
            
            # Show spell effect result
            spell_effect = result.get('spell_effect', {})
            effect_message = spell_effect.get('effect', 'Spell executed successfully')
            spell_name = spell_effect.get('spell_name', 'The spell')
            
            # Get spell icon (use saved family name before cache was cleared)
            spell_family = spell_data.get('spell_family_name', spell_name) if spell_data else spell_name
            spell_images = self._get_spell_icon_image(spell_family)
            
            self.queue_or_show_notification({
                'message': f"You allowed {spell_name}.\n\n{effect_message}",
                'actions': ['ok'],
                'images': spell_images,
                'icon': "magic",
                'title': "Spell Allowed"
            })
        else:
            self.need_to_respond_to_spell = False
            # Clear spell cache on error too
            self.pending_spell_details = None
            self._cached_castable_spells = None
            self._pending_spell_fetch_ready = False
            self.queue_or_show_notification({
                'message': f"Error: {result.get('message')}",
                'actions': ['ok'],
                'icon': "error",
                'title': "Error"
            })
    
    def _draw_counter_spell_waiting_prompt(self):
        """Draw a prominent prompt indicating player is waiting for counter spell response."""
        # Get spell name if available
        spell_name = getattr(self, 'pending_spell_name', None) or 'your spell'
        
        # Create prompt text
        target_prompt_font = pygame.font.Font(settings.FONT_PATH, settings.FIELD_TITLE_FONT_SIZE - 2)
        prompt_text = f"WAITING FOR OPPONENT"
        prompt_surface = target_prompt_font.render(prompt_text, True, (255, 200, 100))  # Orange
        
        # Create detail text
        detail_font = pygame.font.Font(settings.FONT_PATH, settings.FIELD_TITLE_FONT_SIZE - 4)
        detail_text = f"You cast {spell_name}. Opponent can counter or allow it."
        detail_surface = detail_font.render(detail_text, True, (255, 230, 150))  # Light orange
        
        # Create background box for better visibility
        text_width = max(prompt_surface.get_width(), detail_surface.get_width())
        text_height = prompt_surface.get_height() + detail_surface.get_height() + 10
        padding = 20
        
        box_rect = pygame.Rect(
            (settings.SCREEN_WIDTH - text_width - 2 * padding) // 2,
            settings.get_y(0.02),
            text_width + 2 * padding,
            text_height + 2 * padding
        )
        
        # Draw semi-transparent black background
        background = pygame.Surface((box_rect.width, box_rect.height))
        background.set_alpha(200)
        background.fill((0, 0, 0))
        self.window.blit(background, box_rect.topleft)
        
        # Draw orange border for emphasis
        pygame.draw.rect(self.window, (255, 200, 100), box_rect, 4)
        
        # Draw main prompt text centered in box
        text_x = box_rect.centerx - prompt_surface.get_width() // 2
        text_y = box_rect.top + padding
        self.window.blit(prompt_surface, (text_x, text_y))
        
        # Draw detail text below
        detail_x = box_rect.centerx - detail_surface.get_width() // 2
        detail_y = text_y + prompt_surface.get_height() + 10
        self.window.blit(detail_surface, (detail_x, detail_y))
    
    def _show_counter_spell_selection(self, castable_spells, target_spell_name):
        """Show UI for selecting which counter spell to cast."""
        from game.components.counter_spell_selector import CounterSpellSelector
        from collections import Counter
        
        # Get player's actual playable hand from the Hand UI components
        # These contain only the cards currently visible/playable in the hand
        main_hand_cards = self.main_hand.cards if hasattr(self, 'main_hand') else []
        side_hand_cards = self.side_hand.cards if hasattr(self, 'side_hand') else []
        all_cards = main_hand_cards + side_hand_cards
        
        print(f"[COUNTER_SPELL_SELECTOR] Main hand cards count: {len(main_hand_cards)}")
        print(f"[COUNTER_SPELL_SELECTOR] Side hand cards count: {len(side_hand_cards)}")
        print(f"[COUNTER_SPELL_SELECTOR] Total playable cards: {len(all_cards)}")
        print(f"[COUNTER_SPELL_SELECTOR] Main hand: {[(c.suit, c.rank) for c in main_hand_cards]}")
        print(f"[COUNTER_SPELL_SELECTOR] Side hand: {[(c.suit, c.rank) for c in side_hand_cards]}")
        
        hand_counter = Counter((card.suit, card.rank) for card in all_cards)
        
        print(f"[COUNTER_SPELL_SELECTOR] Player hand: {dict(hand_counter)}")
        print(f"[COUNTER_SPELL_SELECTOR] Input castable_spells count: {len(castable_spells)}")
        
        # Double-check each spell is actually castable with current hand
        verified_spells = []
        for spell in castable_spells:
            spell_counter = Counter((card.suit, card.rank) for card in spell.cards)
            can_cast = all(hand_counter[card_tuple] >= count 
                          for card_tuple, count in spell_counter.items())
            print(f"[COUNTER_SPELL_SELECTOR] Spell '{spell.name}' requires {dict(spell_counter)}, can_cast={can_cast}")
            if can_cast:
                verified_spells.append(spell)
        
        print(f"[COUNTER_SPELL_SELECTOR] Verified spells count: {len(verified_spells)}")
        
        if not verified_spells:
            # No valid spells after verification - player cannot counter
            print(f"[COUNTER_SPELL_SELECTOR] No verified spells found")
            self.make_dialogue_box(
                message=f"You don't have the cards to counter {target_spell_name}.\n\nYou'll need to allow it.",
                actions=['allow'],
                icon="error",
                title="Cannot Counter"
            )
            # Don't clear need_to_respond_to_spell - dialogue will handle the response
            return
        
        # Create spell selection options from all verified spells
        spell_options = []
        for spell in verified_spells:
            cards_text = " + ".join([f"{card.rank}{card.suit[0]}" for card in spell.cards])
            spell_options.append({
                'label': f"{spell.name} ({cards_text})",
                'spell': spell
            })
        
        if len(spell_options) == 1:
            # Only one option - cast it directly
            self._cast_counter_spell(spell_options[0]['spell'])
            return  # Exit after casting
        else:
            # Multiple options - show counter spell selector
            selector_width = settings.get_x(0.35)
            selector_height = settings.get_y(0.5)
            selector_x = (settings.SCREEN_WIDTH - selector_width) // 2
            selector_y = settings.get_y(0.25)
            
            self.counter_spell_selector = CounterSpellSelector(
                self.window,
                spell_options,
                selector_x,
                selector_y,
                selector_width,
                selector_height
            )
    
    def _cast_counter_spell(self, spell):
        """Cast the selected counter spell."""
        from utils import spell_service
        from collections import Counter
        
        # Get player's actual playable hand from the Hand UI components (same as in selector)
        main_hand_cards = self.main_hand.cards if hasattr(self, 'main_hand') else []
        side_hand_cards = self.side_hand.cards if hasattr(self, 'side_hand') else []
        all_cards = main_hand_cards + side_hand_cards
        
        # Match spell template cards to actual cards in hand and build counter_cards list
        spell_requirements = Counter((card.suit, card.rank) for card in spell.cards)
        counter_cards = []
        used_card_ids = []
        
        # For each required card, find matching card in hand
        for (suit, rank), count in spell_requirements.items():
            matching_cards = [c for c in all_cards if c.suit == suit and c.rank == rank and c.id not in used_card_ids]
            if len(matching_cards) < count:
                self.make_dialogue_box(
                    message=f"Error: Not enough {rank} of {suit} cards in hand.",
                    actions=['ok'],
                    icon="error",
                    title="Error"
                )
                self.need_to_respond_to_spell = False
                return
            # Take the required number of cards and build card dictionaries
            for i in range(count):
                card = matching_cards[i]
                counter_cards.append({
                    'id': card.id,
                    'suit': card.suit,
                    'rank': card.rank,
                    'value': card.value
                })
                used_card_ids.append(card.id)
        
        result = spell_service.counter_spell(
            player_id=self.state.game.player_id,
            game_id=self.state.game.game_id,
            pending_spell_id=self.state.game.pending_spell_id,
            counter_spell_name=spell.name,
            counter_spell_type=spell.family.type,
            counter_spell_family_name=spell.family.name,
            counter_cards=counter_cards
        )
        
        if result.get('success'):
            self.need_to_respond_to_spell = False
            
            # Clear spell cache immediately so next spell gets fresh data
            self.pending_spell_details = None
            self._cached_castable_spells = None
            self._pending_spell_fetch_ready = False
            
            # Update game state directly from response (no server call needed)
            if result.get('game'):
                self.state.game.update_from_dict(result['game'])
            
            # Trigger start_turn so auto-fill fires
            # (update_from_dict sets turn state, preventing update() from detecting the change)
            if self.state.game.turn:
                self.state.game._handle_start_turn()
                # Clear stale opponent turn summary — we already show our own spell notification
                self.state.game.pending_opponent_turn_summary = None
            
            # Show result
            effect = result.get('effect', 'Spell countered!')
            spell_images = self._get_spell_icon_image(spell.family.name)
            self.queue_or_show_notification({
                'message': f"You countered with {spell.name}!\n\n{effect}\n\nYou did not lose a turn.",
                'actions': ['ok'],
                'images': spell_images,
                'icon': "magic",
                'title': "Spell Countered"
            })
        else:
            error_msg = result.get('message', 'Unknown error')
            self.queue_or_show_notification({
                'message': f"Failed to counter spell: {error_msg}",
                'actions': ['ok'],
                'icon': "error",
                'title': "Error"
            })
            self.need_to_respond_to_spell = False
            # Clear spell cache on error too
            self.pending_spell_details = None
            self._cached_castable_spells = None
            self._pending_spell_fetch_ready = False
    
    def _draw_infinite_hammer_prompt(self):
        """Draw a prominent prompt indicating Infinite Hammer mode is active."""
        # Create prompt text
        target_prompt_font = pygame.font.Font(settings.FONT_PATH, settings.FIELD_TITLE_FONT_SIZE)
        prompt_text = "INFINITE HAMMER MODE"
        prompt_surface = target_prompt_font.render(prompt_text, True, (255, 215, 0))  # Gold
        
        # Create instruction text
        cancel_font = pygame.font.Font(settings.FONT_PATH, settings.FIELD_TITLE_FONT_SIZE - 2)
        instruction_text = "Build, upgrade, and pickup without ending turn • Press ESC to end turn"
        instruction_surface = cancel_font.render(instruction_text, True, (255, 255, 150))  # Light yellow
        
        # Create background box for better visibility
        text_width = max(prompt_surface.get_width(), instruction_surface.get_width())
        text_height = prompt_surface.get_height() + instruction_surface.get_height() + 10
        padding = 20
        
        box_rect = pygame.Rect(
            (settings.SCREEN_WIDTH - text_width - 2 * padding) // 2,
            settings.get_y(0.02),
            text_width + 2 * padding,
            text_height + 2 * padding
        )
        
        # Draw semi-transparent black background
        background = pygame.Surface((box_rect.width, box_rect.height))
        background.set_alpha(200)
        background.fill((0, 0, 0))
        self.window.blit(background, box_rect.topleft)
        
        # Draw gold border for emphasis
        pygame.draw.rect(self.window, (255, 215, 0), box_rect, 4)
        
        # Draw main prompt text centered in box
        text_x = box_rect.centerx - prompt_surface.get_width() // 2
        text_y = box_rect.top + padding
        self.window.blit(prompt_surface, (text_x, text_y))
        
        # Draw instruction text below
        instruction_x = box_rect.centerx - instruction_surface.get_width() // 2
        instruction_y = text_y + prompt_surface.get_height() + 10
        self.window.blit(instruction_surface, (instruction_x, instruction_y))
        
        # Add pulsing effect to main prompt
        pulse_alpha = int(128 + 127 * abs(pygame.time.get_ticks() % 1000 - 500) / 500)
        pulse_surface = prompt_surface.copy()
        pulse_surface.set_alpha(pulse_alpha)
        self.window.blit(pulse_surface, (text_x, text_y))
    
    
    
    def _create_figure_from_data(self, figure_data, families):
        """Helper method to create a Figure instance from serialized data."""
        from game.components.figures.figure import Figure
        from game.components.cards.card import Card
        
        family_name = figure_data.get('family_name')
        if family_name not in families:
            return None
        
        family = families[family_name]
        
        # Reconstruct cards from figure data
        cards_data = figure_data.get('cards', [])
        key_cards = []
        number_card = None
        upgrade_card = None
        
        for card_data in cards_data:
            card = Card(
                rank=card_data['rank'],
                suit=card_data['suit'],
                value=card_data['value'],
                id=card_data.get('card_id'),  # Use card_id, not id
                type=card_data.get('card_type', 'main')
            )
            # Check the role to categorize the card
            role = card_data.get('role', 'key')
            if role == 'key':
                key_cards.append(card)
            elif role == 'number':
                number_card = card
            elif role == 'upgrade':
                upgrade_card = card
        
        # Try to match family figure for combat attributes
        matched_family_figure = None
        for family_figure in family.figures:
            if family_figure.suit == figure_data.get('suit'):
                matched_family_figure = family_figure
                if not upgrade_card:
                    upgrade_card = family_figure.upgrade_card
                break
        
        # Create Figure instance (no game_id parameter)
        figure = Figure(
            name=figure_data.get('name', ''),
            sub_name='',  # Not stored in DB
            suit=figure_data.get('suit'),
            family=family,
            key_cards=key_cards,
            number_card=number_card,
            upgrade_card=upgrade_card,
            upgrade_family_name=figure_data.get('upgrade_family_name'),
            produces=figure_data.get('produces', {}),
            requires=figure_data.get('requires', {}),
            description=figure_data.get('description', ''),
            id=figure_data.get('id'),
            player_id=figure_data.get('player_id'),
            # Copy combat attributes from matched family figure if found
            cannot_attack=matched_family_figure.cannot_attack if matched_family_figure else False,
            must_be_attacked=matched_family_figure.must_be_attacked if matched_family_figure else False,
            rest_after_attack=matched_family_figure.rest_after_attack if matched_family_figure else False,
            distance_attack=matched_family_figure.distance_attack if matched_family_figure else False,
            buffs_allies=matched_family_figure.buffs_allies if matched_family_figure else False,
            blocks_bonus=matched_family_figure.blocks_bonus if matched_family_figure else False,
            cannot_defend=matched_family_figure.cannot_defend if matched_family_figure else False,
            instant_charge=matched_family_figure.instant_charge if matched_family_figure else False,
            cannot_be_blocked=matched_family_figure.cannot_be_blocked if matched_family_figure else False,
            cannot_be_targeted=matched_family_figure.cannot_be_targeted if matched_family_figure else False,
        )
        
        # Apply enchantments if present
        enchantments = figure_data.get('enchantments', [])
        for enchantment in enchantments:
            figure.add_enchantment(
                spell_name=enchantment.get('spell_name', 'Unknown'),
                spell_icon=enchantment.get('spell_icon', 'default_spell_icon.png'),
                power_modifier=enchantment.get('power_modifier', 0)
            )
        
        return figure

    def _draw_unread_chat_badge(self):
        """Draw a red circle with unread message count on the log button."""
        if not self.state.game or not self.state.game.chat_messages:
            return
        # Only count opponent messages (not our own)
        current_player_id = self.state.game.player_id
        opponent_messages = [m for m in self.state.game.chat_messages if m.get('sender_id') != current_player_id]
        total_opponent = len(opponent_messages)
        # Count how many opponent messages existed when we last opened the log
        seen_opponent = 0
        if self._last_seen_chat_count > 0:
            # We stored total chat count; recount opponent msgs up to that point
            all_msgs = self.state.game.chat_messages
            for i, m in enumerate(all_msgs):
                if i >= self._last_seen_chat_count:
                    break
                if m.get('sender_id') != current_player_id:
                    seen_opponent += 1
        unread = total_opponent - seen_opponent
        if unread <= 0 or self.state.subscreen == 'log':
            return
        # Draw red circle badge at top-right of log button
        badge_radius = int(0.006 * settings.SCREEN_WIDTH)
        badge_x = self.log_button.rect_symbol.right - badge_radius // 2
        badge_y = self.log_button.rect_symbol.top + badge_radius // 2
        pygame.draw.circle(self.window, (220, 40, 40), (badge_x, badge_y), badge_radius)
        pygame.draw.circle(self.window, (255, 255, 255), (badge_x, badge_y), badge_radius, 2)
        # Draw count text
        count_text = str(min(unread, 99))
        text_surface = self._badge_font.render(count_text, True, (255, 255, 255))
        text_rect = text_surface.get_rect(center=(badge_x, badge_y))
        self.window.blit(text_surface, text_rect)

    def render(self):
        """Render the game screen, buttons, and active subscreen."""
        self.window.fill(settings.BACKGROUND_COLOR)

        # Check if game exists (may be None after logout)
        if not self.state.game:
            pygame.display.update()
            return

        for element in self.display_elements:
            element.draw()

        # Draw active battle modifier icons below the resource scroll
        self._draw_battle_modifier_icons()

        # Draw game-specific text (e.g., opponent name)
        #self.draw_text(self.state.game.opponent_name, settings.BLACK, settings.get_x(0.1), settings.get_x(0.1))

        # Render game buttons
        #for button in self.game_buttons:
        #    button.draw()



        # Render the currently active subscreen
        if self.state.subscreen in self.subscreens and self.subscreens[self.state.subscreen]:
            self.subscreens[self.state.subscreen].draw()

        # Render the main and side hands
        self.main_hand.draw()
        self.side_hand.draw()

        # Render any general elements (e.g., dialogue box) from the parent class
        super().render()

        # Draw unread chat badge on top of log button
        self._draw_unread_chat_badge()

        # Render figure detail box on top of everything (if open)
        if (self.state.subscreen in ('field', 'battle') and 
            self.state.subscreen in self.subscreens and 
            self.subscreens[self.state.subscreen] and
            hasattr(self.subscreens[self.state.subscreen], 'figure_detail_box') and
            self.subscreens[self.state.subscreen].figure_detail_box):
            self.subscreens[self.state.subscreen].figure_detail_box.draw()
        
        # Render battle move detail box on top of everything (if open)
        if (self.state.subscreen in ('battle_shop', 'battle') and 
            self.state.subscreen in self.subscreens and 
            self.subscreens[self.state.subscreen] and
            hasattr(self.subscreens[self.state.subscreen], 'battle_move_detail_box') and
            self.subscreens[self.state.subscreen].battle_move_detail_box):
            self.subscreens[self.state.subscreen].battle_move_detail_box.draw()
        
        # Render dialogue box on top of everything (if open)
        if (self.state.subscreen == 'field' and 
            self.state.subscreen in self.subscreens and 
            self.subscreens[self.state.subscreen] and
            hasattr(self.subscreens[self.state.subscreen], 'dialogue_box') and
            self.subscreens[self.state.subscreen].dialogue_box):
            self.subscreens[self.state.subscreen].dialogue_box.draw()
        
        # Draw Infinite Hammer mode prompt if active (appears on all subscreens)
        if self.state.game and self.state.game.infinite_hammer_active:
            self._draw_infinite_hammer_prompt()
        
        # Draw forced advance prompt (invader must advance)
        if (self.state.game and self.state.game.pending_forced_advance and 
            self.state.game.forced_advance_dialogue_shown and not self.dialogue_box):
            self._draw_forced_advance_prompt()
        
        # Draw own advance waiting prompt (advancing player waiting for opponent's reaction)
        if (self.state.game and self.state.game.advancing_figure_id and
            self.state.game.advancing_player_id == self.state.game.player_id and
            not self.state.game.turn and not self.state.game.defending_figure_id):
            self._draw_own_advance_waiting_prompt()
        
        # Draw opponent advance prompt (opponent advanced, your turn to respond: counter-advance or spend turn)
        # Shows only for the non-advancing player when it's their turn and before counter-advance
        if (self.state.game and self.state.game.advancing_figure_id and 
            self.state.game.advancing_player_id != self.state.game.player_id and
            self.state.game.turn and not self.state.game.pending_forced_advance and
            not self.state.game.defending_figure_id):
            self._draw_opponent_advance_prompt()
        
        # Draw waiting for defender pick prompt (defender finished turn, opponent is choosing battle figure)
        if (self.state.game and self.state.game.advancing_figure_id and
            self.state.game.advancing_player_id != self.state.game.player_id and
            not self.state.game.turn and not self.state.game.defending_figure_id and
            self.state.game.waiting_for_defender_pick_shown):
            self._draw_waiting_for_defender_pick_prompt()
        
        # Draw defender selection prompt for advancing player (pick opponent's figure)
        # Don't draw if field screen is already in defender_selection_mode (it draws its own)
        field_screen = self.subscreens.get('field')
        defender_selecting = field_screen and getattr(field_screen, 'defender_selection_mode', False)
        if (self.state.game and self.state.game.pending_defender_selection and
            self.state.game.defender_selection_dialogue_shown and
            not self.dialogue_box and not defender_selecting):
            self._draw_select_defender_prompt()
        
        # Draw counter spell waiting prompt if active
        if self.waiting_for_counter_response:
            self._draw_counter_spell_waiting_prompt()
        
        # Draw waiting for battle decision prompt if active
        if self.state.game and not self.dialogue_box:
            # Suppress waiting prompts if fold outcome detected (fold supersedes waiting)
            fold_active = (self.state.game.fold_outcome or self.state.game.pending_fold_result)
            if self.state.game.waiting_for_battle_decision and not fold_active:
                # Invader chose battle, waiting for defender's decision
                self._draw_waiting_for_battle_decision_prompt()
            elif (self.state.game.pending_battle_ready and
                  not self.state.game.battle_ready_shown and
                  self.state.game.advancing_player_id != self.state.game.player_id and
                  not fold_active):
                # Defender waiting for invader to decide first
                self._draw_waiting_for_battle_decision_prompt()
        
        # Draw counter spell selector on top of everything if active
        if self.counter_spell_selector:
            # Draw semi-transparent overlay
            overlay = pygame.Surface((settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT))
            overlay.set_alpha(180)
            overlay.fill((0, 0, 0))
            self.window.blit(overlay, (0, 0))
            
            # Draw selector
            self.counter_spell_selector.draw()

        # Draw battle modifier hover text on top of everything
        self._draw_battle_modifier_hover_text()

        # Update the display
        pygame.display.update()



    def update(self, events):
        """Update the game screen and all relevant components."""
        # During defender selection or forced advance, block subscreen changes from button clicks
        # super().update() calls button.update() which can change state.subscreen
        field_screen = self.subscreens.get('field')
        block_subscreen_change = (
            self.state.game and (
                (self.state.game.pending_forced_advance and self.state.game.forced_advance_dialogue_shown) or
                (self.state.game.pending_defender_selection and 
                 self.state.game.defender_selection_dialogue_shown and
                 field_screen and field_screen.defender_selection_mode) or
                (self.state.game.battle_moves_phase)
            )
        )
        
        if block_subscreen_change:
            saved_subscreen = self.state.subscreen
        
        super().update()
        
        if block_subscreen_change:
            self.state.subscreen = saved_subscreen

        # Check if game exists (may be None after logout)
        if not self.state.game:
            return

        # Handle click on locked battle button
        if self.battle_button.locked and self.battle_button.locked_clicked:
            self.battle_button.locked_clicked = False
            if not self.dialogue_box:
                self.queue_or_show_notification({
                    'message': "The Battle Arena becomes available\nonce the battle phase begins.",
                    'actions': ['ok'],
                    'icon': 'magic',
                })

        # Throttle updates to avoid constant re-rendering
        current_time = pygame.time.get_ticks()
        if current_time - self.last_update_time >= self.update_interval:
            self.update_game()

        # Update the active subscreen if necessary
        if self.state.subscreen in self.subscreens and self.subscreens[self.state.subscreen]:
            self.subscreens[self.state.subscreen].update(self.state.game)

    def handle_events(self, events):
        """Handle user input events (e.g., clicks, key presses)."""
        # Handle dialogue box first if present
        if self.dialogue_box:
            response = self.dialogue_box.update(events)
            if response:
                # Handle counter spell responses
                if response == 'counter':
                    self.dialogue_box = None  # Clear dialogue before calling handler
                    self._handle_counter_spell_counter()
                    return
                elif response == 'allow':
                    self.dialogue_box = None  # Clear dialogue before calling handler
                    self._handle_counter_spell_allow()
                    return
                # Handle Infinite Hammer end confirmation
                elif response == 'yes' and self.state.game and self.state.game.infinite_hammer_active:
                    self._end_infinite_hammer_mode()
                # Handle forced advance 'got it!' response — switch to field screen
                elif (response == 'got it!' and self.state.game and 
                      self.state.game.pending_forced_advance):
                    self._handle_forced_advance_dialogue_response()
                # Handle defender selection 'got it!' response — switch to field screen
                elif (response == 'got it!' and self.state.game and
                      self.state.game.pending_defender_selection):
                    self.state.subscreen = 'field'
                    field_screen = self.subscreens.get('field')
                    if field_screen:
                        field_screen.defender_selection_mode = True
                        field_screen._update_defender_selectable()
                    self.state.game.defender_selection_dialogue_shown = True
                # Handle battle ready 'to battle!' response — submit battle decision
                elif (response == 'to battle!' and self.state.game and
                      self.state.game.pending_battle_ready):
                    self.dialogue_box = None
                    self._submit_battle_decision('battle')
                    self.show_next_queued_notification()
                    return
                # Handle battle ready 'fold' response — submit fold decision
                elif (response == 'fold' and self.state.game and
                      self.state.game.pending_battle_ready):
                    self.dialogue_box = None
                    self._submit_battle_decision('fold')
                    self.show_next_queued_notification()
                    return
                self.dialogue_box = None  # Close dialogue box
                # Show next queued notification if any
                self.show_next_queued_notification()
                return  # Don't process other events while dialogue is open
        
        # Check for ESC during Infinite Hammer mode (works across all subscreens)
        if self.state.game and self.state.game.infinite_hammer_active:
            if self._handle_infinite_hammer_esc(events):
                return  # ESC was pressed, dialogue shown, block other events
        
        # Block actions for defender who needs to respond (dialogue will handle it)
        if self.need_to_respond_to_spell:
            # Defender should only interact with the dialogue or counter spell selector
            # Handle counter spell selector events if active
            if self.counter_spell_selector:
                result = self.counter_spell_selector.handle_events(events)
                if result == 'CANCEL':
                    # Player cancelled - go back to counter/allow dialogue
                    self.counter_spell_selector = None
                    # Only show dialogue if there isn't one already
                    if not self.dialogue_box:
                        self._show_counter_spell_dialogue()
                elif result:
                    # Player selected a spell to counter with
                    self.counter_spell_selector = None
                    self._cast_counter_spell(result)
            return
        
        # During forced advance, only allow field screen access
        if self.state.game and self.state.game.pending_forced_advance:
            # Block screen-changing buttons (handled by GameButton clicks)
            # Force subscreen to field
            if self.state.subscreen != 'field':
                self.state.subscreen = 'field'
            # Still allow field screen interaction
            super().handle_events(events)
            if not self.state.game:
                return
            if self.state.subscreen in self.subscreens and self.subscreens[self.state.subscreen]:
                self.subscreens[self.state.subscreen].handle_events(events)
            return
        
        # During defender selection, only allow field screen access
        field_screen = self.subscreens.get('field')
        if (self.state.game and self.state.game.pending_defender_selection and
            self.state.game.defender_selection_dialogue_shown and
            field_screen and field_screen.defender_selection_mode):
            if self.state.subscreen != 'field':
                self.state.subscreen = 'field'
            super().handle_events(events)
            if not self.state.game:
                return
            if self.state.subscreen in self.subscreens and self.subscreens[self.state.subscreen]:
                self.subscreens[self.state.subscreen].handle_events(events)
            return
        
        # During Civil War second figure selection, only allow field screen access
        # Player must pick a second figure or skip — no builds, spells, pickups, etc.
        if (self.state.game and 
            (getattr(self.state.game, 'civil_war_awaiting_second', False) or
             getattr(self.state.game, 'civil_war_defender_second', False))):
            if self.state.subscreen != 'field':
                self.state.subscreen = 'field'
            super().handle_events(events)
            if not self.state.game:
                return
            if self.state.subscreen in self.subscreens and self.subscreens[self.state.subscreen]:
                self.subscreens[self.state.subscreen].handle_events(events)
            return
        
        # For caster waiting for response, allow view actions but show error for game actions
        # This is handled by subscreens checking self.state.game.turn
        # The waiting_for_counter_response flag will be checked in action handlers
        
        super().handle_events(events)

        # Check if game exists (may be None after logout)
        if not self.state.game:
            return

        # Handle events for the main and side hands
        self.main_hand.handle_events(events)
        self.side_hand.handle_events(events)

        # Pass events to the active subscreen
        if self.state.subscreen in self.subscreens and self.subscreens[self.state.subscreen]:
            self.subscreens[self.state.subscreen].handle_events(events)


