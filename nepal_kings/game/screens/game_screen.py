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
from game.components.figures.figure_manager import FigureManager


class GameScreen(Screen):
    def __init__(self, state):
        super().__init__(state)
        
        # Store reference to game_screen in state for button access
        self.state.parent_screen = self

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
        field_button = GameButton(
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
        self.game_buttons.append(field_button)

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
        
        # Check if subscreen changed - if so, deselect all cards
        if self.previous_subscreen != self.state.subscreen:
            self.main_hand.deselect_all_cards()
            self.side_hand.deselect_all_cards()
            self.previous_subscreen = self.state.subscreen
        
        # Skip full server poll while defender is actively responding to counter spell
        # (they don't need fresh data while deciding, and the poll blocks the UI)
        if not self.need_to_respond_to_spell:
            self.state.game.update()
        
        # Check for auto-fill notification
        self.check_auto_fill_notification()
        
        # Check for opponent turn notification (includes Forced Deal and Dump Cards details)
        self.check_opponent_turn_notification()
        
        # Check for ceasefire ended notification
        self.check_ceasefire_ended_notification()
        
        # Check for Infinite Hammer mode activation
        self.check_infinite_hammer_activation()
        
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
                if caster_id and caster_id != self.state.game.player_id:
                    descriptions = {
                        'Civil War': 'Each player selects two villagers of the same color for the next battle.',
                        'Peasant War': 'Only villagers can be selected for the upcoming battle.',
                        'Blitzkrieg': "The opponent's battle figure is selected by the caster."
                    }
                    desc = descriptions.get(modifier_type, 'A battle modifier is now active.')
                    
                    # Load icon for the notification
                    icon_img = self._battle_modifier_icons.get(modifier_type)
                    images = [icon_img] if icon_img else []
                    
                    self.queue_or_show_notification({
                        'message': f"{caster_name} activated {modifier_type}!\n\n{desc}\n\nBoth players have 1 turn left.",
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
            
            # Load spell icon if this is a spell action (and not Forced Deal/Dump Cards with cards)
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
            
            # Special handling for explosion - show destroyed figure name prominently
            if action_type == 'explosion':
                destroyed_figure = action.get('destroyed_figure', 'a figure')
                message = f"{opponent_name} cast Explosion!\n\nYour {destroyed_figure} was destroyed.\n\nIt's your turn now!"
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

        # Render figure detail box on top of everything (if open)
        if (self.state.subscreen == 'field' and 
            self.state.subscreen in self.subscreens and 
            self.subscreens[self.state.subscreen] and
            hasattr(self.subscreens[self.state.subscreen], 'figure_detail_box') and
            self.subscreens[self.state.subscreen].figure_detail_box):
            self.subscreens[self.state.subscreen].figure_detail_box.draw()
        
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
        
        # Draw counter spell waiting prompt if active
        if self.waiting_for_counter_response:
            self._draw_counter_spell_waiting_prompt()
        
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
        super().update()

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


