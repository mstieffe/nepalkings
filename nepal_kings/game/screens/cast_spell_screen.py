# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
import pygame
from pygame.locals import *
from collections import Counter
from config import settings
from game.screens.sub_screen import SubScreen
from game.components.spells.spell_manager import SpellManager
from game.components.cards.card import Card
from game.components.buttons.confirm_button import ConfirmButton
from game.components.picker_ui import (
    SegmentedTabs,
    draw_empty_detail,
    draw_footer,
    draw_section_header,
    footer_button_geometry,
    layout_family_grid_desktop,
)
from utils import spell_service
import logging

logger = logging.getLogger('nk.screens.cast_spell')



class CastSpellScreen(SubScreen):
    """Screen for casting spells by selecting spell families and cards."""

    def __init__(self, window, state, x: int = 0.0, y: int = 0.0, title=None,
                 card_source=None, mode='duel'):
        super().__init__(window, state.game, x, y, title)

        self.state = state
        self.game = state.game

        from game.core.card_source import GameCardSource
        self.card_source = card_source or GameCardSource(self.game)
        self.mode = mode
        self._active_spell_type = 'greed'
        self._initial_family_selected = False
        self._desktop_headers = []
        self.title = (
            'Cast Spell · Duel' if self.mode == 'duel'
            else title or 'Cast Spell')
        
        # Initialize spell manager and load spells
        self.spell_manager = SpellManager()
        
        # Initialize UI components
        self.init_spell_info_box()
        self.init_spell_category_tabs()
        self.init_spell_family_icons()
        self.init_scroll_test_list_shifter()
        
        # Store selected spells
        self.selected_spell_family = None
        self.selected_spells = []

        # Version tracking to avoid per-frame recalculation
        self._last_game_data_version = -1

        # Tracks which families were castable last update (one-shot pulse)
        self._prev_castable_family_names = None
        
        action_label = 'Cast Spell'
        bx, by, bw, bh = footer_button_geometry(
            self, action_label, align='center')
        self.confirm_button = ConfirmButton(
            self.window,
            bx, by, action_label, width=bw, height=bh,
        )
    
    def reset_state(self):
        """Reset all game-specific transient state.

        Called by GameScreen._reset_game_screen_state() when switching games.
        """
        self.selected_spell_family = None
        self.selected_spells = []
        self._last_game_data_version = -1
        self.dialogue_box = None
        self._prev_castable_family_names = None
        self._initial_family_selected = False
        logger.debug("[CastSpellScreen] State reset for game switch")

    def cast_spell_in_db(self, selected_spell):
        """
        Cast the selected spell using the spell service.
        Maps dummy cards to real cards and sends to server.
        """
        if getattr(self.game, 'game_over', False):
            return

        if self.game.action_in_progress:
            return

        # Check if player is waiting for counter spell response
        if hasattr(self.state, 'parent_screen') and hasattr(self.state.parent_screen, 'waiting_for_counter_response'):
            if self.state.parent_screen.waiting_for_counter_response:
                self.make_dialogue_box(
                    message="You cannot cast a spell while waiting for opponent's response to your previous spell.",
                    actions=['ok'],
                    icon="error",
                    title="Action Blocked"
                )
                return

        # Check if battle is active
        if hasattr(self.game, 'is_battle_active') and self.game.is_battle_active():
            self.make_dialogue_box(
                message="You cannot cast a spell while a battle is in progress.",
                actions=['ok'],
                icon="error",
                title="Action Blocked"
            )
            return
        
        # Map dummy cards in the spell to real cards in the player's hand
        real_cards = self.map_spell_cards_to_hand(selected_spell)
        
        if real_cards is None:
            self.make_dialogue_box(
                message="Could not find all required cards in your hand.",
                actions=['ok'],
                icon="error",
                title="Casting Failed"
            )
            return
        
        # TODO: If spell requires target, show target selection UI here
        target_figure_id = None
        if selected_spell.requires_target:
            # Store spell and cards in state for target selection
            self.state.pending_spell_cast = {
                'spell': selected_spell,
                'real_cards': real_cards
            }
            
            # Switch to field screen for target selection
            # The field screen will display a prominent prompt
            self.state.subscreen = "field"
            return
        
        # Prepare card data for server
        cards_data = [{
            'id': card.id,
            'rank': card.rank,
            'suit': card.suit,
            'value': card.value
        } for card in real_cards]
        
        # Call spell service to cast the spell
        self.game.lock_actions()
        try:
            result = spell_service.cast_spell(
                player_id=self.game.player_id,
                game_id=self.game.game_id,
                spell_name=selected_spell.name,
                spell_type=selected_spell.family.type,
                spell_family_name=selected_spell.family.name,
                suit=selected_spell.suit,
                cards=cards_data,
                target_figure_id=target_figure_id,
                counterable=selected_spell.counterable,
                possible_during_ceasefire=selected_spell.possible_during_ceasefire
            )
        except Exception:
            self.game.unlock_actions()
            raise
        
        if result.get('success'):
            from utils import sound
            sound.play_spell(selected_spell.name)
            # Cast flourish: spell glyph arcs up from the family icon and a
            # short banner names the cast (duel only; conquer is inert here).
            fx = self._fx_layer()
            if fx is not None:
                from game.components.conquer_effects import spell_preset
                primary = spell_preset(selected_spell.name)[0]
                source_rect = None
                for button in self.spell_family_buttons:
                    if button.family.name == selected_spell.family.name:
                        source_rect = (getattr(button, 'rect_frame', None)
                                       or getattr(button, 'rect_icon', None))
                        break
                if source_rect is not None:
                    target = pygame.Rect(source_rect).move(0, -int(0.08 * settings.SCREEN_HEIGHT))
                    fx.spawn_spell_to_rect(selected_spell.name,
                                           pygame.Rect(source_rect), target)
                fx.spawn_banner(selected_spell.name, primary, duration_ms=800)
            # Check if waiting for opponent to respond (counterable spell)
            waiting_for_player_id = result.get('waiting_for_player_id')
            if waiting_for_player_id:
                self.game.unlock_actions()
                # Store spell name in game_screen for waiting prompt
                if hasattr(self.state, 'parent_screen') and self.state.parent_screen:
                    self.state.parent_screen.pending_spell_name = selected_spell.name
                self.state.subscreen = 'field'
                return
            
            # Update game state from server response
            # (update_from_dict -> unlock_actions)
            if result.get('game'):
                # Update directly from returned game state (no extra server call)
                self.game.update_from_dict(result['game'])
            
            # Show success message with drawn cards (if any)
            spell_effect = result.get('spell_effect', {})
            drawn_cards_data = spell_effect.get('drawn_cards', [])
            cards_received_data = spell_effect.get('cards_received', [])
            cards_given_data = spell_effect.get('cards_given', [])
            
            logger.debug(f"[CAST_SPELL_SCREEN] Full spell_effect: {spell_effect}")
            logger.debug(f"[CAST_SPELL_SCREEN] Spell effect received: {spell_effect.get('effect')}")
            logger.debug(f"[CAST_SPELL_SCREEN] Drawn cards data: {len(drawn_cards_data)} cards")
            logger.debug(f"[CAST_SPELL_SCREEN] Cards received: {len(cards_received_data)} cards")
            logger.debug(f"[CAST_SPELL_SCREEN] Cards given: {len(cards_given_data)} cards")
            
            # Create card images from drawn cards or swapped cards
            card_images = []
            message_text = f"{selected_spell.name} cast successfully!"
            
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
                message_text = f"{selected_spell.name} cast successfully! You drew:"
            
            elif cards_received_data and cards_given_data:
                # For Forced Deal: show both cards received and given
                from game.components.cards.card import Card
                
                # Add received cards
                for card_data in cards_received_data:
                    card = Card(
                        rank=card_data['rank'],
                        suit=card_data['suit'],
                        value=card_data['value'],
                        id=card_data.get('id'),
                        type=card_data.get('type')
                    )
                    card_img = card.make_icon(self.window, self.game, 0, 0)
                    card_images.append(card_img.front_img)
                
                # Add visual separator or indicator between given and received
                # For now, just add given cards after received cards with red cross overlay
                for card_data in cards_given_data:
                    card = Card(
                        rank=card_data['rank'],
                        suit=card_data['suit'],
                        value=card_data['value'],
                        id=card_data.get('id'),
                        type=card_data.get('type')
                    )
                    card_img = card.make_icon(self.window, self.game, 0, 0)
                    # Make the card slightly transparent to show it was given away
                    given_card_img = card_img.front_img.copy()
                    given_card_img.set_alpha(128)  # 50% transparency
                    
                    # Add red cross overlay
                    import os
                    red_cross_path = os.path.join('img', 'new_cards', 'red_cross.png')
                    if os.path.exists(red_cross_path):
                        red_cross = pygame.image.load(red_cross_path)
                        # Scale red cross to fit the card
                        cross_size = min(given_card_img.get_width(), given_card_img.get_height())
                        red_cross = pygame.transform.scale(red_cross, (cross_size, cross_size))
                        # Center the cross on the card
                        cross_x = (given_card_img.get_width() - cross_size) // 2
                        cross_y = (given_card_img.get_height() - cross_size) // 2
                        given_card_img.blit(red_cross, (cross_x, cross_y))
                    
                    card_images.append(given_card_img)
                
                message_text = f"{selected_spell.name} cast! You received {len(cards_received_data)} main cards and gave {len(cards_given_data)} main cards."
            
            if selected_spell.counterable:
                dialogue_params = {
                    'message': f"{selected_spell.name} cast! Exiting to field view...\n\nWaiting for opponent to respond.",
                    'actions': [],  # No actions - auto-close
                    'icon': "magic",
                    'title': "Spell Cast",
                    'auto_close_delay': 2000  # Auto-close after 2 seconds
                }
                if card_images:
                    dialogue_params['images'] = card_images
                self.make_dialogue_box(**dialogue_params)
            else:
                # For non-counterable spells, show cards if any
                # Skip success dialogue for Infinite Hammer (it has its own mode dialogue)
                if 'Infinite Hammer' not in selected_spell.name:
                    if card_images:
                        self.make_dialogue_box(
                            message=message_text,
                            actions=['ok'],
                            images=card_images,
                            icon="magic",
                            title="Spell Cast"
                        )
                    else:
                        self.make_dialogue_box(
                            message=message_text,
                            actions=['ok'],
                            icon="magic",
                            title="Spell Cast"
                        )
            
            # Clear selections
            self.selected_spell_family = None
            if self.scroll_text_list_shifter:
                self.scroll_text_list_shifter.set_displayed_texts([])
            for button in self.spell_family_buttons:
                button.clicked = False
        
        else:
            self.game.unlock_actions()
            # Show error message
            error_msg = result.get('message', 'Unknown error')
            self.make_dialogue_box(
                message=f"Failed to cast spell: {error_msg}",
                actions=['ok'],
                icon="error",
                title="Casting Failed"
            )
    
    def map_spell_cards_to_hand(self, spell):
        """
        Map the spell's dummy cards to actual cards in the player's hand.
        
        :param spell: The spell with dummy cards
        :return: List of real cards from hand, or None if not all cards available
        """
        main_cards, side_cards = self.card_source.get_cards()
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

    def init_spell_category_tabs(self):
        """Horizontal spell categories replace hard-to-read vertical labels."""
        offset_x = getattr(self, '_layout_offset_x', 0)
        offset_y = getattr(self, '_layout_offset_y', 0)
        box_x = int(settings.CAST_SPELL_INFO_BOX_X + offset_x)
        box_y = int(settings.CAST_SPELL_INFO_BOX_Y + offset_y)
        margin = max(8, int(0.012 * settings.SCREEN_WIDTH))
        tab_h = max(
            26,
            settings.TOUCH_COMPACT_MIN
            if settings.TOUCH_TARGET_MIN > 0 else 0,
        )
        self.spell_category_tabs = SegmentedTabs(
            self.window,
            pygame.Rect(
                box_x + margin,
                box_y + max(6, int(0.012 * settings.SCREEN_HEIGHT)),
                settings.CAST_SPELL_INFO_BOX_WIDTH - 2 * margin,
                tab_h,
            ),
            [
                ('greed', 'Greed'),
                ('enchantment', 'Enchantment'),
                ('tactics', 'Tactics'),
            ],
            active_key=self._active_spell_type,
        )
    
    def init_spell_family_icons(self):
        """Create spell families; category tabs decide which grid is visible."""
        if not hasattr(self, '_active_spell_type'):
            self._active_spell_type = 'greed'
        if not hasattr(self, 'spell_category_tabs'):
            self.init_spell_category_tabs()
        self.spell_family_buttons = []
        all_families = self.spell_manager.get_all_families()
        for family in all_families:
            # Conquer-only families (Royal Decree, Copy Figure, Landslide,
            # Draw 4 MainCards) never appear in the duel spell book.
            if getattr(family, 'conquer_only', False):
                continue
            button = family.make_icon(
                self.window, self.game, 0, 0, fixed_size=True)
            if settings.TOUCH_TARGET_MIN <= 0:
                # Desktop packs all three category rows on one page.
                button.grid_mode = True
                button.rescale(settings.PICKER_DESKTOP_ICON_SCALE)
            self.spell_family_buttons.append(button)

        # Kept as empty dictionaries for compatibility with callers/tests that
        # inspect these attributes; labels are now the horizontal tabs above.
        self.type_labels = {}
        self.type_label_positions = {}
        self._layout_spell_family_icons()

    def _visible_spell_buttons(self):
        # Desktop shows the whole spell book at once; mobile pages by category.
        if settings.TOUCH_TARGET_MIN <= 0:
            return list(self.spell_family_buttons)
        active_type = getattr(self, '_active_spell_type', 'greed')
        return [
            button for button in self.spell_family_buttons
            if button.family.type == active_type
        ]

    def _layout_spell_family_icons(self):
        offset_x = getattr(self, '_layout_offset_x', 0)
        offset_y = getattr(self, '_layout_offset_y', 0)
        box = pygame.Rect(
            int(settings.CAST_SPELL_INFO_BOX_X + offset_x),
            int(settings.CAST_SPELL_INFO_BOX_Y + offset_y),
            settings.CAST_SPELL_INFO_BOX_WIDTH,
            settings.CAST_SPELL_INFO_BOX_HEIGHT,
        )
        mobile = settings.TOUCH_TARGET_MIN > 0
        if not mobile:
            # All families on one page, grouped into category rows.
            self._desktop_headers = layout_family_grid_desktop(
                self.spell_family_buttons, box)
            return
        cols = 5 if mobile else 6
        # Edge-column captions are centred on the column, so the margin must
        # cover half a caption width or they bleed over the panel border.
        margin_x = max(int(0.07 * box.w), int(0.085 * box.w) + 2)
        usable_w = box.w - 2 * margin_x
        pitch_x = usable_w // max(1, cols - 1)
        start_x = box.x + margin_x
        start_y = self.spell_category_tabs.rect.bottom + int(
            0.105 * settings.SCREEN_HEIGHT)
        pitch_y = int(0.205 * settings.SCREEN_HEIGHT)
        visible = set(self._visible_spell_buttons())
        caption_w = min(max(48, int(pitch_x * 0.92)),
                        max(48, 2 * (margin_x - 4)))
        for button in self.spell_family_buttons:
            button.visible = button in visible
            button.caption_max_width = caption_w
        for index, button in enumerate(self._visible_spell_buttons()):
            row, col = divmod(index, cols)
            button.set_position(
                start_x + col * pitch_x,
                start_y + row * pitch_y,
            )

    def _select_spell_family(self, button):
        self.selected_spell_family = button.family
        castable_spells = self.get_spells_in_hand(button.family)
        if castable_spells:
            self.scroll_text_list = [
                self._spell_detail_item(spell, content=spell)
                for spell in castable_spells
            ]
        else:
            self.scroll_text_list = []
            for spell in button.family.spells:
                given_cards, missing_cards = (
                    self.get_given_and_missing_cards_for_spell(spell))
                self.scroll_text_list.append(
                    self._spell_detail_item(
                        spell,
                        content=None,
                        cards=given_cards,
                        missing_cards=missing_cards,
                    )
                )
        self.scroll_text_list_shifter.set_displayed_texts(
            self.scroll_text_list)
        for other_button in self.spell_family_buttons:
            other_button.clicked = other_button is button

    def _spell_detail_item(self, spell, *, content, cards=None,
                           missing_cards=None):
        item = {
            'title': spell.name,
            'text': spell.family.description,
            'cards': spell.cards if cards is None else cards,
            'spell_type': self.format_spell_type(spell.family.type),
            'counterable': spell.counterable,
            'ceasefire': spell.possible_during_ceasefire,
            'content': content,
        }
        if missing_cards:
            item['missing_cards'] = missing_cards
        return item

    def _select_initial_spell_family(self):
        if self._initial_family_selected:
            return
        visible = self._visible_spell_buttons()
        if not visible:
            return
        chosen = next((button for button in visible if button.is_active),
                      visible[0])
        self._select_spell_family(chosen)
        self._initial_family_selected = True

    @staticmethod
    def _confirm_action_label(selected_spell):
        return (
            'Choose Target'
            if getattr(selected_spell, 'requires_target', False)
            else 'Cast Spell'
        )
    
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
        # Keep card_source in sync for GameCardSource (duel mode)
        if hasattr(self.card_source, 'game'):
            self.card_source.game = game
        
        # Check if confirm button should be disabled
        if not self.game.turn:
            self.confirm_button.disabled = True
        elif self.scroll_text_list_shifter:
            # Check if selected spell can be cast during ceasefire
            selected_spell = self.scroll_text_list_shifter.get_current_selected()
            if selected_spell and self.game.ceasefire_active and not selected_spell.possible_during_ceasefire:
                self.confirm_button.disabled = True
            elif selected_spell and getattr(self.game, 'advancing_figure_id', None) and selected_spell.family.type == 'tactics':
                self.confirm_button.disabled = True
            else:
                self.confirm_button.disabled = False
        else:
            self.confirm_button.disabled = False
        
        # Only recalculate spell states when game data actually changes
        if self.game._game_data_version != self._last_game_data_version:
            self._last_game_data_version = self.game._game_data_version
            self.update_spell_icon_states()
        self._layout_spell_family_icons()
        if settings.TOUCH_TARGET_MIN > 0:
            self._select_initial_spell_family()
        
        # Update all spell family buttons
        for button in self.spell_family_buttons:
            button.update()
        
        # Update confirm button if spell selected
        if self.scroll_text_list_shifter:
            selected_spell = self.scroll_text_list_shifter.get_current_selected()
            if selected_spell:
                self.confirm_button.set_text(
                    self._confirm_action_label(selected_spell))
                self.confirm_button.update()
    
    def update_spell_icon_states(self):
        """Update the active state of spell icons based on castable spells."""
        main_cards, side_cards = self.card_source.get_cards()
        hand_cards = main_cards + side_cards
        
        # Filter to only cards belonging to this player
        hand_cards = [card for card in hand_cards if card.player_id == self.game.player_id]
        
        castable_families = self.spell_manager.get_families_with_castable_spells(hand_cards)
        castable_family_names = {family.name for family in castable_families}

        # One-shot pulse on families that just became castable (only while
        # the spell book is open — inactive subscreens don't update()).
        prev_castable = self._prev_castable_family_names
        self._prev_castable_family_names = set(castable_family_names)
        if prev_castable is not None:
            newly_castable = castable_family_names - prev_castable
            if newly_castable and getattr(self.state, 'subscreen', None) == 'cast_spell':
                fx = self._fx_layer()
                if fx is not None:
                    for button in self.spell_family_buttons:
                        if button.family.name not in newly_castable:
                            continue
                        rect = (getattr(button, 'rect_frame', None)
                                or getattr(button, 'rect_icon', None))
                        if rect is not None:
                            fx.spawn_rect_pulse(pygame.Rect(rect),
                                                (238, 206, 130),
                                                secondary=(255, 245, 200))

        for button in self.spell_family_buttons:
            # Set active if this family has at least one castable spell
            button.is_active = button.family.name in castable_family_names
        
        # Refresh the spell list for the currently selected family
        # so stale entries (e.g. cards consumed by a countered spell) disappear
        if self.selected_spell_family and self.scroll_text_list_shifter:
            castable_spells = self.get_spells_in_hand(self.selected_spell_family)
            if castable_spells:
                new_list = [
                    self._spell_detail_item(spell, content=spell)
                    for spell in castable_spells
                ]
            else:
                # No castable spells left — show all variants with given/missing cards
                new_list = []
                for spell in self.selected_spell_family.spells:
                    given_cards, missing_cards = self.get_given_and_missing_cards_for_spell(spell)
                    new_list.append(self._spell_detail_item(
                        spell,
                        content=None,
                        cards=given_cards,
                        missing_cards=missing_cards,
                    ))
            self.scroll_text_list = new_list
            self.scroll_text_list_shifter.set_displayed_texts(self.scroll_text_list)

    def handle_events(self, events):
        """Handle events for button interactions."""
        # Dialogue input is modal. Do not let its click reach the picker,
        # scroll panel, or subscreen close control underneath.
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
                
                elif response in ('got it!', 'ok'):
                    # Error/info message acknowledged
                    self.dialogue_box = None
            return  # Don't process other events when dialogue is active

        super().handle_events(events)

        if settings.TOUCH_TARGET_MIN > 0:
            changed_type = self.spell_category_tabs.handle_events(events)
            if changed_type is not None:
                self._active_spell_type = changed_type
                self.selected_spell_family = None
                self.scroll_text_list = []
                self.scroll_text_list_shifter.set_displayed_texts([])
                self._initial_family_selected = False
                self._layout_spell_family_icons()
                self._select_initial_spell_family()
        
        # Handle spell family button clicks
        for button in self._visible_spell_buttons():
            button.handle_events(events)
            
            if button.clicked and button.family != self.selected_spell_family:
                self._select_spell_family(button)
        
        # Handle confirm button click
        for event in events:
                if event.type == MOUSEBUTTONDOWN:
                    if self.confirm_button.collide() and not self.confirm_button.disabled:
                        # Block casting spells during Infinite Hammer mode
                        if hasattr(self.game, 'infinite_hammer_active') and self.game.infinite_hammer_active:
                            self.make_dialogue_box(
                                message="You cannot cast spells during Infinite Hammer mode.\n\nPress ESC to end the mode.",
                                actions=['ok'],
                                icon="error",
                                title="Action Blocked"
                            )
                        elif self.scroll_text_list_shifter:
                            selected_spell = self.scroll_text_list_shifter.get_current_selected()
                            if selected_spell:
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
                        # Check if disabled due to ceasefire, advance, or not being player's turn
                        if self.scroll_text_list_shifter:
                            selected_spell = self.scroll_text_list_shifter.get_current_selected()
                            if selected_spell and self.game.ceasefire_active and not selected_spell.possible_during_ceasefire:
                                self.make_dialogue_box(
                                    message="This spell cannot be cast during ceasefire.\n\nWait for the ceasefire to end or cast a different spell.",
                                    actions=['ok'],
                                    icon="ceasefire_passive",
                                    title="Ceasefire Active"
                                )
                            elif selected_spell and getattr(self.game, 'advancing_figure_id', None) and selected_spell.family.type == 'tactics':
                                self.make_dialogue_box(
                                    message="Battle spells cannot be cast while a figure is advancing.\n\nThe battle conditions are already set.",
                                    actions=['ok'],
                                    icon="error",
                                    title="Advance Active"
                                )
                            else:
                                # Inform user it's not their turn
                                self.make_dialogue_box(
                                    message="You can only cast spells on your turn.",
                                    actions=['ok'],
                                    icon="error",
                                    title="Not Your Turn"
                                )
                        else:
                            # Inform user it's not their turn
                            self.make_dialogue_box(
                                message="You can only cast spells on your turn.",
                                actions=['ok'],
                                icon="error",
                                title="Not Your Turn"
                            )
    
    def get_spells_in_hand(self, spell_family):
        """
        Get all spells from this family that can be cast with current hand.
        
        :param spell_family: The SpellFamily to check
        :return: List of castable spells
        """
        main_cards, side_cards = self.card_source.get_cards()
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
        main_cards, side_cards = self.card_source.get_cards()
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

        selected_spell = (
            self.scroll_text_list_shifter.get_current_selected()
            if self.scroll_text_list_shifter else None
        )
        if selected_spell:
            status = 'Casting spends the shown cards from your hand'
            tone = 'good'
        else:
            status = ''
            tone = 'neutral'
        draw_footer(
            self.window, self, status, tone=tone,
            show_action=bool(selected_spell),
            show_status=bool(status),
        )
        if settings.TOUCH_TARGET_MIN > 0:
            self.spell_category_tabs.draw()
        else:
            for spell_type, header_rect in getattr(self, '_desktop_headers', []):
                draw_section_header(self.window, spell_type, header_rect)

        # Draw spell family buttons (after backgrounds so they appear on top)
        for button in self._visible_spell_buttons():
            button.draw()

        if not self.scroll_text_list:
            draw_empty_detail(
                self.window,
                pygame.Rect(
                    self.scroll_x, self.scroll_y,
                    self.scroll_w, self.scroll_h),
                'Choose a spell',
                'Preview its card cost, timing, target, and counter rules.',
            )
        
        # Draw confirm button
        if selected_spell:
            self.confirm_button.draw()
        
        super().draw_on_top()
