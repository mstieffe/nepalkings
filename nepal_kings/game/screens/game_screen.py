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
from game.components.figures.figure_manager import FigureManager


class GameScreen(Screen):
    def __init__(self, state):
        super().__init__(state)

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
        }
        
        # Track previous subscreen to detect changes
        self.previous_subscreen = None
        
        # Track last processed log entry to detect new spell notifications
        self.last_processed_log_id = None
    
    def make_dialogue_box(self, message, actions=None, images=None, icon=None, title=""):
        """Create a dialogue box with specified message, actions, images, and icon."""
        from game.components.dialogue_box import DialogueBox
        self.dialogue_box = DialogueBox(self.window, message, actions=actions, images=images, icon=icon, title=title)

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
        
        self.state.game.update()
        
        # Check for opponent spell notifications (like Dump Cards)
        self.check_opponent_spell_notifications()
        
        # Check for auto-fill notification
        self.check_auto_fill_notification()
        
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
    
    def check_opponent_spell_notifications(self):
        """Check for spells cast by opponent that should trigger notifications."""
        if not self.state.game or not self.state.game.log_entries:
            return
        
        # Get most recent log entry
        recent_logs = sorted(self.state.game.log_entries, key=lambda x: x.get('id', 0), reverse=True)
        if not recent_logs:
            return
        
        latest_log = recent_logs[0]
        log_id = latest_log.get('id')
        
        # Skip if we've already processed this log entry
        if log_id == self.last_processed_log_id:
            return
        
        self.last_processed_log_id = log_id
        
        # Check if this log entry is about a spell cast by the opponent
        log_type = latest_log.get('type', '')
        log_message = latest_log.get('message', '')
        player_id = latest_log.get('player_id')
        
        # Only show notification if it was cast by opponent
        if player_id == self.state.game.player_id:
            return
        
        # Check for Dump Cards spell
        if log_type == 'spell_cast' and 'Dump Cards' in log_message:
            # Show notification to opponent with their new cards
            main_cards, side_cards = self.state.game.get_hand()
            
            # Create card images from current hand
            from game.components.cards.card_img import CardImg
            card_images = []
            for card in main_cards + side_cards:
                card_img = CardImg(self.window, card.suit, card.rank)
                card_images.append(card_img.front_img)
            
            # Show dialogue box
            self.make_dialogue_box(
                message=f"{self.state.game.opponent_name} cast Dump Cards! All hands were dumped. You drew:",
                actions=['ok'],
                images=card_images,
                icon="loot",
                title="Opponent Cast Spell"
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
        
        # Show dialogue
        self.make_dialogue_box(
            message=message,
            actions=['ok'],
            images=card_images,
            icon="loot",
            title="Cards Refilled"
        )
        
        # Clear the notification
        self.state.game.pending_auto_fill = None

    def render(self):
        """Render the game screen, buttons, and active subscreen."""
        self.window.fill(settings.BACKGROUND_COLOR)

        # Check if game exists (may be None after logout)
        if not self.state.game:
            pygame.display.update()
            return

        for element in self.display_elements:
            element.draw()

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

        # Update the display
        pygame.display.update()



    def update(self, events):
        """Update the game screen and all relevant components."""
        super().update()

        # Check if game exists (may be None after logout)
        if not self.state.game:
            return

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
                self.dialogue_box = None  # Close dialogue box
                return  # Don't process other events while dialogue is open
        
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


