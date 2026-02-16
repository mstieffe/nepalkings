import pygame
from pygame.locals import *
from collections import Counter
from config import settings
from game.screens.sub_screen import SubScreen
from game.components.spells.spell_manager import SpellManager
from game.components.cards.card import Card
from game.components.buttons.confirm_button import ConfirmButton
from utils import spell_service


class CastSpellScreen(SubScreen):
    """Screen for casting spells by selecting spell families and cards."""

    def __init__(self, window, state, x: int = 0.0, y: int = 0.0, title=None):
        super().__init__(window, state.game, x, y, title)

        self.state = state
        self.game = state.game
        
        # Initialize spell manager and load spells
        self.spell_manager = SpellManager()
        
        # Initialize UI components
        self.init_spell_info_box()
        self.init_spell_family_icons()
        self.init_scroll_test_list_shifter()
        
        # Store selected spells
        self.selected_spell_family = None
        self.selected_spells = []
        
        self.confirm_button = ConfirmButton(
            self.window,
            settings.CAST_SPELL_CONFIRM_BUTTON_X,
            settings.CAST_SPELL_CONFIRM_BUTTON_Y,
            "cast!"
        )
    
    def cast_spell_in_db(self, selected_spell):
        """
        Cast the selected spell using the spell service.
        Maps dummy cards to real cards and sends to server.
        """
        # Map dummy cards in the spell to real cards in the player's hand
        real_cards = self.map_spell_cards_to_hand(selected_spell)
        
        if real_cards is None:
            self.make_dialogue_box(
                message="Could not find all required cards in your hand.",
                actions=['got it!'],
                icon="error",
                title="Casting Failed"
            )
            return
        
        # TODO: If spell requires target, show target selection UI here
        target_figure_id = None
        if selected_spell.requires_target:
            # For now, we'll skip target selection
            # This will need to be implemented based on target_type
            pass
        
        # Prepare card data for server
        cards_data = [{
            'id': card.id,
            'rank': card.rank,
            'suit': card.suit,
            'value': card.value
        } for card in real_cards]
        
        # Call spell service to cast the spell
        result = spell_service.cast_spell(
            player_id=self.game.player_id,
            game_id=self.game.game_id,
            spell_name=selected_spell.name,
            spell_type=selected_spell.family.type,
            spell_family_name=selected_spell.family.name,
            suit=selected_spell.suit,
            cards=cards_data,
            target_figure_id=target_figure_id,
            counterable=selected_spell.counterable
        )
        
        if result.get('success'):
            # Update game state from server response
            if result.get('game'):
                # You may need to refresh the Game object with the new data
                # For now, just update via the existing update method
                self.game.update()
            
            # Show success message with drawn cards (if any)
            spell_effect = result.get('spell_effect', {})
            drawn_cards_data = spell_effect.get('drawn_cards', [])
            
            # Create card images from drawn cards
            card_images = []
            if drawn_cards_data:
                from game.components.cards.card import Card
                for card_data in drawn_cards_data:
                    card = Card(
                        rank=card_data['rank'],
                        suit=card_data['suit'],
                        value=card_data['value'],
                        id=card_data.get('id'),
                        type=card_data.get('type')
                    )
                    card_img = card.make_icon(self.window, self.game, 0, 0)
                    card_images.append(card_img.front_img)
            
            if selected_spell.counterable:
                dialogue_params = {
                    'message': f"{selected_spell.name} cast! Waiting for opponent to counter...",
                    'actions': ['ok'],
                    'icon': "loot",
                    'title': "Spell Cast"
                }
                if card_images:
                    dialogue_params['images'] = card_images
                self.make_dialogue_box(**dialogue_params)
            else:
                # For non-counterable spells, show drawn cards if any
                if card_images:
                    self.make_dialogue_box(
                        message=f"{selected_spell.name} cast successfully! You drew:",
                        actions=['ok'],
                        images=card_images,
                        icon="loot",
                        title="Spell Cast"
                    )
                else:
                    self.make_dialogue_box(
                        message=f"{selected_spell.name} cast successfully!",
                        actions=['ok'],
                        icon="loot",
                        title="Spell Cast"
                    )
            
            # Clear selections
            self.selected_spell_family = None
            if self.scroll_text_list_shifter:
                self.scroll_text_list_shifter.set_displayed_texts([])
            for button in self.spell_family_buttons:
                button.clicked = False
        
        else:
            # Show error message
            error_msg = result.get('message', 'Unknown error')
            self.make_dialogue_box(
                message=f"Failed to cast spell: {error_msg}",
                actions=['got it!'],
                icon="error",
                title="Casting Failed"
            )
    
    def map_spell_cards_to_hand(self, spell):
        """
        Map the spell's dummy cards to actual cards in the player's hand.
        
        :param spell: The spell with dummy cards
        :return: List of real cards from hand, or None if not all cards available
        """
        main_cards, side_cards = self.game.get_hand()
        hand_cards = main_cards + side_cards
        
        # Filter to only cards belonging to this player
        hand_cards = [card for card in hand_cards if card.player_id == self.game.player_id]
        
        # Count available cards in hand - use (suit, rank) format
        hand_counter = Counter((card.suit, card.rank) for card in hand_cards)
        
        # Count required cards for spell - use (suit, rank) format
        spell_counter = Counter((card.suit, card.rank) for card in spell.cards)
        
        # Check if all spell cards are available in hand
        for card_tuple, count in spell_counter.items():
            if hand_counter[card_tuple] < count:
                return None  # Not enough of this card in hand
        
        # Map spell cards to hand cards using indices to avoid __eq__ issues
        real_cards = []
        used_indices = set()
        
        for spell_card in spell.cards:
            for i, hand_card in enumerate(hand_cards):
                if i not in used_indices and (hand_card.suit, hand_card.rank) == (spell_card.suit, spell_card.rank):
                    real_cards.append(hand_card)
                    used_indices.add(i)
                    break
        
        return real_cards if len(real_cards) == len(spell.cards) else None
    
    def format_spell_type(self, spell_type: str) -> str:
        """Format spell type for display."""
        type_mapping = {
            'greed': 'Greed Spell',
            'enchantment': 'Enchantment Spell',
            'tactics': 'Tactics Spell'
        }
        return type_mapping.get(spell_type, spell_type.capitalize() + ' Spell')
    
    def init_scroll_test_list_shifter(self):
        """Initialize the scroll text list shifter for spell variants."""
        self.make_scroll_text_list_shifter(
            self.scroll_text_list,
            settings.CAST_SPELL_SCROLL_TEXT_X,
            settings.CAST_SPELL_SCROLL_TEXT_Y,
            scroll_height=settings.CAST_SPELL_INFO_BOX_SCROLL_HEIGHT
        )
    
    def init_spell_family_icons(self):
        """Initialize spell family icons organized by effect type (one row per type)."""
        self.spell_family_buttons = []
        
        all_families = self.spell_manager.get_all_families()
        
        # Group families by effect type
        families_by_effect = {
            'greed': [],
            'enchantment': [],
            'tactics': []
        }
        
        for family in all_families:
            if family.type in families_by_effect:
                families_by_effect[family.type].append(family)
        
        # Layout: one row per effect type
        effect_types_order = ['greed', 'enchantment', 'tactics']
        
        # Create type label surfaces
        self.type_label_font = pygame.font.Font(settings.FONT_PATH, settings.SPELL_TYPE_LABEL_FONT_SIZE)
        self.type_labels = {}
        self.type_label_positions = {}
        
        for row_index, effect_type in enumerate(effect_types_order):
            families_in_row = families_by_effect[effect_type]
            
            # Create label for this type
            label_text = effect_type.capitalize()
            label_surface = self.type_label_font.render(label_text, True, settings.SPELL_TYPE_LABEL_COLOR)
            # Rotate the label 90 degrees counterclockwise
            label_surface = pygame.transform.rotate(label_surface, 90)
            self.type_labels[effect_type] = label_surface
            
            # Position label centered with the row of icons
            row_y = settings.CAST_SPELL_ICON_START_Y + row_index * settings.SPELL_ICON_DELTA_Y
            label_rect = label_surface.get_rect()
            label_rect.midleft = (settings.SPELL_TYPE_LABEL_X, row_y)
            self.type_label_positions[effect_type] = label_rect.topleft
            
            for col_index, family in enumerate(families_in_row):
                x = settings.CAST_SPELL_ICON_START_X + col_index * settings.SPELL_ICON_DELTA_X
                y = settings.CAST_SPELL_ICON_START_Y + row_index * settings.SPELL_ICON_DELTA_Y
                
                button = family.make_icon(self.window, self.game, x, y)
                self.spell_family_buttons.append(button)
    
    def init_spell_info_box(self):
        """Initialize spell info box."""
        super().init_sub_box_background(
            settings.CAST_SPELL_INFO_BOX_X,
            settings.CAST_SPELL_INFO_BOX_Y,
            settings.CAST_SPELL_INFO_BOX_WIDTH,
            settings.CAST_SPELL_INFO_BOX_HEIGHT
        )
        super().init_scroll_background(
            settings.CAST_SPELL_INFO_BOX_SCROLL_X,
            settings.CAST_SPELL_INFO_BOX_SCROLL_Y,
            settings.CAST_SPELL_INFO_BOX_SCROLL_WIDTH,
            settings.CAST_SPELL_INFO_BOX_SCROLL_HEIGHT
        )

    def update(self, game):
        """Update the game state and button components."""
        super().update(game)
        self.game = game
        
        if self.game.turn:
            self.confirm_button.disabled = False
        else:
            self.confirm_button.disabled = True
        
        # Update icon states based on available cards
        self.update_spell_icon_states()
        
        # Update all spell family buttons
        for button in self.spell_family_buttons:
            button.update()
        
        # Update confirm button if spell selected
        if self.scroll_text_list_shifter:
            selected_spell = self.scroll_text_list_shifter.get_current_selected()
            if selected_spell:
                self.confirm_button.update()
    
    def update_spell_icon_states(self):
        """Update the active state of spell icons based on castable spells."""
        main_cards, side_cards = self.game.get_hand()
        hand_cards = main_cards + side_cards
        
        # Filter to only cards belonging to this player
        hand_cards = [card for card in hand_cards if card.player_id == self.game.player_id]
        
        castable_families = self.spell_manager.get_families_with_castable_spells(hand_cards)
        castable_family_names = {family.name for family in castable_families}
        
        for button in self.spell_family_buttons:
            # Set active if this family has at least one castable spell
            button.is_active = button.family.name in castable_family_names

    def handle_events(self, events):
        """Handle events for button interactions."""
        super().handle_events(events)
        
        # If dialogue box is active, handle it first and skip other event handling
        if self.dialogue_box:
            response = self.dialogue_box.update(events)
            if response:
                if response == 'yes':
                    # User confirmed spell casting
                    self.dialogue_box = None
                    if self.scroll_text_list_shifter:
                        selected_spell = self.scroll_text_list_shifter.get_current_selected()
                        if selected_spell:
                            self.cast_spell_in_db(selected_spell)
                
                elif response == 'cancel':
                    # User cancelled
                    self.dialogue_box = None
                
                elif response == 'got it!':
                    # Error message acknowledged
                    self.dialogue_box = None
                
                elif response == 'ok':
                    # Info message acknowledged
                    self.dialogue_box = None
            return  # Don't process other events when dialogue is active
        
        # Handle spell family button clicks
        for button in self.spell_family_buttons:
            button.handle_events(events)
            
            if button.clicked and button.family != self.selected_spell_family:
                # New family selected - refresh game state first
                self.game.update()
                self.selected_spell_family = button.family
                
                # Get castable spells
                castable_spells = self.get_spells_in_hand(button.family)
                
                # Build scroll list - show castable spells or all variants with missing cards
                if castable_spells:
                    # Show only castable spells with all cards available
                    self.scroll_text_list = [
                        {
                            "title": spell.name,
                            "text": spell.family.description,
                            "cards": spell.cards,
                            "spell_type": self.format_spell_type(spell.family.type),
                            "counterable": spell.counterable,
                            "ceasefire": spell.possible_during_ceasefire,
                            "content": spell
                        }
                        for spell in castable_spells
                    ]
                else:
                    # Show all spell variants with given/missing cards
                    self.scroll_text_list = []
                    for spell in button.family.spells:
                        given_cards, missing_cards = self.get_given_and_missing_cards_for_spell(spell)
                        
                        self.scroll_text_list.append({
                            "title": spell.name,
                            "text": spell.family.description,
                            "spell_type": self.format_spell_type(spell.family.type),
                            "counterable": spell.counterable,
                            "ceasefire": spell.possible_during_ceasefire,
                            "cards": given_cards,
                            "missing_cards": missing_cards,
                            "content": None  # None indicates spell cannot be cast
                        })
                
                # Update the scroll text list shifter with new spells
                if self.scroll_text_list_shifter:
                    self.scroll_text_list_shifter.set_displayed_texts(self.scroll_text_list)
                
                # Unclick all other buttons
                for other_button in self.spell_family_buttons:
                    if other_button != button:
                        other_button.clicked = False
        
        # Handle confirm button click
        for event in events:
                if event.type == MOUSEBUTTONDOWN:
                    if self.confirm_button.collide() and not self.confirm_button.disabled:
                        if self.scroll_text_list_shifter:
                            selected_spell = self.scroll_text_list_shifter.get_current_selected()
                            if selected_spell:
                                # Refresh game state before casting
                                self.game.update()
                                # Show confirmation dialogue with spell icon and spell cards
                                counterable_text = " (counterable)" if selected_spell.counterable else ""
                                # Include spell family icon first, then the cards being spent
                                card_img_objects = [card.make_icon(self.window, self.game, 0, 0) for card in selected_spell.cards]
                                card_images = [self.selected_spell_family.icon_img] + [card_img.front_img for card_img in card_img_objects]
                                self.make_dialogue_box(
                                    message=f"Do you want to cast {selected_spell.name}?{counterable_text}",
                                    actions=['yes', 'cancel'],
                                    images=card_images,  # Show spell icon and cards being spent
                                    icon="question",
                                    title="Cast Spell"
                                )
                    
                    elif self.confirm_button.collide() and self.confirm_button.disabled:
                        # Inform user it's not their turn
                        self.make_dialogue_box(
                            message="You can only cast spells on your turn.",
                            actions=['got it!'],
                            icon="error",
                            title="Not Your Turn"
                        )
    
    def get_spells_in_hand(self, spell_family):
        """
        Get all spells from this family that can be cast with current hand.
        
        :param spell_family: The SpellFamily to check
        :return: List of castable spells
        """
        main_cards, side_cards = self.game.get_hand()
        hand_cards = main_cards + side_cards
        
        # Filter to only cards belonging to this player
        hand_cards = [card for card in hand_cards if card.player_id == self.game.player_id]
        
        # Count available cards in hand - use (suit, rank) format
        hand_counter = Counter((card.suit, card.rank) for card in hand_cards)
        
        castable_spells = []
        for spell in spell_family.spells:
            # Count required cards for spell - use (suit, rank) format
            spell_counter = Counter((card.suit, card.rank) for card in spell.cards)
            
            # Check if all spell cards are available in sufficient quantity
            can_cast = True
            for card_tuple, count in spell_counter.items():
                if hand_counter[card_tuple] < count:
                    can_cast = False
                    break
            
            if can_cast:
                castable_spells.append(spell)
        
        return castable_spells
    
    def get_given_and_missing_cards_for_spell(self, spell):
        """
        Get cards split into given (player has) and missing (player doesn't have) for a spell.
        Each card from spell.cards goes into exactly one list.
        
        :param spell: The spell to check
        :return: Tuple of (given_cards, missing_cards)
        """
        main_cards, side_cards = self.game.get_hand()
        hand_cards = main_cards + side_cards
        
        # Filter to only cards belonging to this player
        hand_cards = [card for card in hand_cards if card.player_id == self.game.player_id]
        
        # Count occurrences of each card in the hand - use (suit, rank) format
        hand_counter = Counter((card.suit, card.rank) for card in hand_cards)
        
        # Track how many of each card we've assigned to "given"
        assigned_counter = Counter()
        
        given_cards = []
        missing_cards = []
        
        # Iterate through spell cards in order and assign each to given or missing
        for card in spell.cards:
            card_tuple = (card.suit, card.rank)
            if assigned_counter[card_tuple] < hand_counter[card_tuple]:
                # We have this card
                given_cards.append(card)
                assigned_counter[card_tuple] += 1
            else:
                # We don't have this card
                missing_cards.append(card)
        
        return given_cards, missing_cards

    def draw(self):
        """Draw the screen, including buttons and background."""
        super().draw()
        
        # Draw spell type labels
        for effect_type, label_surface in self.type_labels.items():
            pos = self.type_label_positions[effect_type]
            self.window.blit(label_surface, pos)
        
        # Draw spell family buttons (after backgrounds so they appear on top)
        for button in self.spell_family_buttons:
            button.draw()
        
        # Draw confirm button
        if self.scroll_text_list_shifter:
            selected_spell = self.scroll_text_list_shifter.get_current_selected()
            if selected_spell:
                self.confirm_button.draw()
        
        super().draw_on_top()



