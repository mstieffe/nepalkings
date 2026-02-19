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
        
        # Queue for pending notifications (to avoid overwriting active dialogue boxes)
        self.pending_notifications = []
    
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
        
        # Check for auto-fill notification
        self.check_auto_fill_notification()
        
        # Check for opponent turn notification (includes Forced Deal and Dump Cards details)
        self.check_opponent_turn_notification()
        
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
                # Split message into before and after icon parts
                message = f"{opponent_name}'s turn:\n• {action_message}"
                message_after = "\nIt's your turn now!"
                
                # Add details if spell affects player (keep in first part)
                if action.get('affects_player'):
                    details = action.get('details', '')
                    if details:
                        message += f"\n  > {details}"
                
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
                # Show next queued notification if any
                self.show_next_queued_notification()
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


