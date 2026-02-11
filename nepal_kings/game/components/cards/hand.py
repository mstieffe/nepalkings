import pygame
from game.components.cards.card_img import CardImg
from game.components.cards.card_slot import CardSlot
from config import settings
from utils.utils import GameButton
from utils.utils import Button
from game.components.dialogue_box import DialogueBox


class Hand:
    """Hand class for pygame application. This class represents a hand of cards."""

    def __init__(self, window, state, x: float = 0.0, y: float = 0.0, type="main_card", hidden=False):
        self.window = window
        self.font = pygame.font.Font(settings.FONT_PATH, settings.FONT_SIZE_DETAIL)
        self.state = state
        self.game = state.game if state else None
        self.type = type

        self.cards = self.initialize_cards()
        self.cards.sort(key=lambda card: card.rank)

        self.x = x
        self.y = y

        self.hidden = hidden
        self.card_imgs = self.initialize_card_imgs()

        self.num_slots = settings.MAX_MAIN_CARD_SLOTS if self.type == "main_card" else settings.MAX_SIDE_CARD_SLOTS
        self.card_slots = self.initialize_card_slots()

        self.slots_width = (self.num_slots - 1) * (settings.CARD_SPACER + settings.CARD_SLOT_BORDER_WIDTH) + settings.CARD_WIDTH + settings.CARD_SLOT_BORDER_WIDTH

        self.initialize_background_attributes()

        self.buttons = self.initialize_buttons()

        self.dialogue_box = None  # To store the active dialogue box
        self.discard_mode = False  # Track if we're in discard mode
        self.cards_to_discard_count = 0  # How many cards need to be discarded

    def get_selected_cards(self):
        return [slot.card for slot in self.card_slots if slot.clicked and slot.card]
    
    def deselect_all_cards(self):
        """Deselect all card slots."""
        for slot in self.card_slots:
            slot.clicked = False
    
    def needs_discard(self):
        """Check if player has too many cards and needs to discard."""
        return len(self.cards) > self.num_slots
    
    def get_excess_card_count(self):
        """Get the number of cards that exceed the max hand size."""
        return max(0, len(self.cards) - self.num_slots)

    def initialize_cards(self):

        if self.game:
            return self.game.get_hand()[0] if self.type == "main_card" else self.game.get_hand()[1]
        else:
            return []

    def initialize_card_imgs(self):
        return {(suit, rank): CardImg(self.window, suit, rank) for suit in settings.SUITS for rank in settings.RANKS}

    def initialize_card_slots(self):
        """Initialize slots - we'll position them dynamically in update_slot_positions."""
        # Create enough slots to handle max + some extra for overflow during discard
        max_slots = max(self.num_slots + 5, 20)  # Allow for overflow
        slots = []
        # All slots are the same - we'll handle positioning dynamically
        for i in range(max_slots):
            slot = CardSlot(self.window, x=self.x, y=self.y,
                          width=settings.CARD_WIDTH, height=settings.CARD_HEIGHT, is_last=True)
            slots.append(slot)
        return slots
    
    def update_slot_positions(self):
        """Dynamically position slots based on number of cards to maintain constant total width."""
        num_cards = len(self.cards)
        if num_cards == 0:
            return
        
        # Total available width for the hand
        total_width = self.slots_width
        
        if num_cards == 1:
            # Single card: center it
            start_x = self.x + (total_width - settings.CARD_WIDTH) / 2
            spacing = 0
        else:
            # Multiple cards: distribute evenly across full width
            # First card at self.x, last card ends at self.x + total_width
            # So last card starts at self.x + total_width - CARD_WIDTH
            start_x = self.x
            # Calculate spacing so cards span the full width
            spacing = (total_width - settings.CARD_WIDTH) / (num_cards - 1)
        
        # Position and update rectangles for all active slots
        for i in range(num_cards):
            if i < len(self.card_slots):
                slot = self.card_slots[i]
                slot.x = start_x + i * spacing
                slot.y = self.y
                
                # Update all rectangles for proper collision detection
                dx = settings.CARD_SLOT_BORDER_WIDTH / 2
                slot.rect_border = pygame.Rect(slot.x - dx, slot.y - dx, slot.width + 2*dx, slot.height + 2*dx)
                slot.rect = pygame.Rect(slot.x, slot.y, slot.width, slot.height)
                slot.rec_card = pygame.Rect(slot.x, slot.y, settings.CARD_WIDTH, slot.height)

    def initialize_background_attributes(self):
        attributes = {
            'main_card': {
                'width_ratio': 0.22,
                'height_ratio': 1.66,
                'dx_ratio': 0.1,
                'dy_ratio': 0.39,
                'image_path': './img/icons/main_hand.png',
                'addon_path': './img/icons/main_hand_addon.png',
                'text_offset_x': 0.0
            },
            'default': {
                'width_ratio': 0.28,
                'height_ratio': 1.75,
                'dx_ratio': 0.12,
                'dy_ratio': 0.42,
                'image_path': './img/icons/hand_holder.png',
                'addon_path': './img/icons/hand_holder_addon2.png',
                'text_offset_x': 0.05
            }
        }

        type_attributes = attributes.get(self.type, attributes['default'])

        self.background_image_width = self.slots_width + self.slots_width * type_attributes['width_ratio']
        self.background_image_height = settings.CARD_HEIGHT * type_attributes['height_ratio']
        self.backgorund_dx = self.background_image_width * type_attributes['dx_ratio']
        self.backgorund_dy = settings.CARD_HEIGHT * type_attributes['dy_ratio']
        self.background_image = pygame.image.load(type_attributes['image_path'])
        self.background_image_addon = pygame.image.load(type_attributes['addon_path']).convert_alpha()
        self.text_occupied_slots_x = self.x + self.slots_width * type_attributes['text_offset_x']

        self.background_image = pygame.transform.scale(self.background_image,
                                                       (self.background_image_width,
                                                        self.background_image_height))
        self.background_image_addon = pygame.transform.scale(self.background_image_addon,
                                                             (self.background_image_width,
                                                              self.background_image_height))

    def initialize_buttons(self):
        buttons = []

        # Change Card Button
        button_x = self.x + self.slots_width + self.slots_width * 0.02
        button_y = self.y - settings.CARD_HEIGHT * 0.2
        buttons.append(GameButton(self.window,
                                    'change_cards',
                                    'round_arrow', 
                                    'plain',
                                    button_x, button_y,
                                    symbol_width=settings.HAND_BUTTON_SYMBOL_WIDTH,
                                    stone_width=settings.HAND_BUTTON_STONE_WIDTH,
                                    glow_width=settings.HAND_BUTTON_GLOW_WIDTH,
                                    symbol_width_big=settings.HAND_BUTTON_SYMBOL_BIG_WIDTH,
                                    glow_width_big=settings.HAND_BUTTON_GLOW_BIG_WIDTH,
                                    glow_shift=settings.HAND_BUTTON_GLOW_SHIFT,
                                    state=self.state,
                                    hover_text='change cards!'))

        return buttons

    def draw_text(self, text, color, x, y):
        """Draw text on the window."""
        text_obj = self.font.render(text, True, color)
        text_rect = text_obj.get_rect()
        text_rect.topleft = (x, y)
        self.window.blit(text_obj, text_rect)

    def handle_button_click(self):
        """Handle the click on the round_arrow button."""
        selected_cards = self.get_selected_cards()

        if selected_cards:

            if self.game.turn:
                # Open DialogueBox for card selection
                self.dialogue_box = DialogueBox(
                    self.window,
                    title="Change Cards",
                    message="Do you want to change those cards?",
                    actions=['yes', 'cancel'],
                    images=[self.card_imgs[(card.suit, card.rank)].front_img for card in selected_cards],
                    icon="question"
                )
            else:
                # Open DialogueBox for no turn
                self.dialogue_box = DialogueBox(
                    self.window,
                    title="No Turn",
                    message="It's not your turn...!",
                    actions=['ok'],
                    icon="error"
                )

        else:
            # Open DialogueBox for no selection
            self.dialogue_box = DialogueBox(
                self.window,
                title="No Cards",
                message="No cards selected...!",
                actions=['ok'],
                icon="error"
            )

    def start_discard_mode(self, num_to_discard):
        """
        Initiate discard mode when player has too many cards.
        
        :param num_to_discard: Number of cards that must be discarded
        """
        self.discard_mode = True
        self.cards_to_discard_count = num_to_discard
        self.update_discard_dialogue()
    
    def update_discard_dialogue(self):
        """Update the discard dialogue box with current selection."""
        if not self.discard_mode:
            return
        
        selected_cards = self.get_selected_cards()
        num_selected = len(selected_cards)
        num_needed = self.cards_to_discard_count
        
        # Build message
        if num_selected == 0:
            message = f"You have too many cards! Select {num_needed} card{'s' if num_needed > 1 else ''} to discard."
        elif num_selected < num_needed:
            still_needed = num_needed - num_selected
            message = f"Select {still_needed} more card{'s' if still_needed > 1 else ''} to discard."
        elif num_selected == num_needed:
            message = f"Confirm to discard {num_selected} card{'s' if num_selected > 1 else ''}."
        else:
            too_many = num_selected - num_needed
            message = f"Too many cards selected! Deselect {too_many} card{'s' if too_many > 1 else ''}."
        
        # Only show confirm button if correct number selected
        if num_selected == num_needed:
            actions = ['confirm']
        else:
            actions = []  # No actions available until correct number selected
        
        # Show images of selected cards
        card_images = [self.card_imgs[(card.suit, card.rank)].front_img for card in selected_cards] if selected_cards else None
        
        self.dialogue_box = DialogueBox(
            self.window,
            title="Discard Cards",
            message=message,
            actions=actions,
            images=card_images,
            icon="error"
        )
    
    def handle_discard_confirm(self):
        """Handle confirmation of card discard."""
        selected_cards = self.get_selected_cards()
        
        if len(selected_cards) == self.cards_to_discard_count:
            # Discard the cards
            if self.type == "main_card":
                success = self.game.discard_main_cards(selected_cards)
            else:
                success = self.game.discard_side_cards(selected_cards)
            
            if success:
                # Exit discard mode
                self.discard_mode = False
                self.cards_to_discard_count = 0
                self.dialogue_box = None
                
                # Deselect all slots
                for slot in self.card_slots:
                    slot.clicked = False
                
                return True
        
        return False

    def update(self, game):
        """Update the game state."""
        self.game = game
        self.cards = self.initialize_cards()
        self.cards.sort(key=lambda card: card.rank)

        # Update slot positions based on number of cards
        self.update_slot_positions()

        # First pass: update all slots without hover (we'll handle hover separately)
        for slot in self.card_slots:
            slot.hovered = False  # Reset hover state

        # Assign cards to slots (only as many as we have cards)
        for i, card in enumerate(self.cards):
            if i < len(self.card_slots):
                slot = self.card_slots[i]
                slot.content = self.card_imgs[(card.suit, card.rank)]
                slot.card = card
        
        # Reset unused slots and deselect them
        for i in range(len(self.cards), len(self.card_slots)):
            self.card_slots[i].content = None
            self.card_slots[i].card = None
            self.card_slots[i].clicked = False
        
        # Handle hover detection - only the topmost card under the mouse should be hovered
        # Iterate in reverse order (last card drawn is on top)
        mouse_pos = pygame.mouse.get_pos()
        hovered_slot = None
        for i in range(len(self.cards) - 1, -1, -1):
            if i < len(self.card_slots):
                slot = self.card_slots[i]
                if slot.card and slot.rec_card.collidepoint(mouse_pos):
                    hovered_slot = slot
                    break  # Found topmost card under mouse
        
        # Set hover state only for the topmost card
        if hovered_slot:
            hovered_slot.hovered = True

    def handle_events(self, events):
        """Handle game events."""
        if self.dialogue_box:
            # Update the dialogue box
            response = self.dialogue_box.update(events)
            
            if self.discard_mode:
                # In discard mode, handle confirm action
                if response == 'confirm':
                    self.handle_discard_confirm()
                # Don't close dialogue on other responses - it's persistent
            else:
                # Normal mode dialogue handling
                if response == 'yes':
                    print("Cards changed!")
                    # Change the selected cards
                    selected_cards = self.get_selected_cards()

                    if selected_cards:
                        # Call the appropriate card change method based on type and fetch new cards
                        if self.type == "main_card":
                            new_cards = self.game.change_main_cards(selected_cards)
                        else:  # SideCards
                            new_cards = self.game.change_side_cards(selected_cards)

                        # Open a new DialogueBox to display the drawn cards
                        self.dialogue_box = DialogueBox(
                            self.window,
                            title="New Cards",
                            message="You have drawn the following cards:",
                            actions=['ok'],
                            icon="loot",
                            images=[self.card_imgs[(card['suit'], card['rank'])].front_img for card in new_cards]
                        )
                        
                        # Deselect all cards after exchange
                        self.deselect_all_cards()
                elif response in ['cancel', 'ok']:
                    self.dialogue_box = None
        else:
            # Check for button clicks (only in normal mode)
            if not self.discard_mode:
                for event in events:
                    if event.type == pygame.MOUSEBUTTONDOWN:
                        for button in self.buttons:
                            if button.collide() and button.name == 'change_cards':
                                self.handle_button_click()

        # Handle slot events - only for the topmost card under the mouse
        # This prevents multiple overlapping cards from being selected
        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN:
                # Find topmost card under mouse (iterate in reverse)
                clicked_slot = None
                for i in range(len(self.cards) - 1, -1, -1):
                    if i < len(self.card_slots):
                        slot = self.card_slots[i]
                        if slot.card and slot.rec_card.collidepoint(event.pos):
                            clicked_slot = slot
                            break  # Found topmost card
                
                # Toggle clicked state only for the topmost card
                if clicked_slot:
                    clicked_slot.clicked = not clicked_slot.clicked
        
        # Update discard dialogue if in discard mode and a card selection changed
        if self.discard_mode:
            self.update_discard_dialogue()

    def draw(self):
        """Draw elements on the window."""
        if self.game:
            self.window.blit(self.background_image, (self.x - self.backgorund_dx, self.y - self.backgorund_dy))
            
            # Only draw slots that have cards assigned
            num_cards = len(self.cards)
            #for i in range(num_cards):
            #    if i < len(self.card_slots):
            #        self.card_slots[i].draw_empty()
            

            # Draw all cards in order to maintain natural hierarchy
            for i in range(num_cards):
                if i < len(self.card_slots):
                    self.card_slots[i].draw_content()

            # Draw the background addon frame behind the cards
            self.window.blit(self.background_image_addon, (self.x - self.backgorund_dx, self.y - self.backgorund_dy))

            self.draw_text(f'{str(len(self.cards))}/{self.num_slots} cards', settings.BLACK, self.text_occupied_slots_x,
                           self.y + settings.CARD_HEIGHT * 1.04 + settings.TINY_SPACER_Y)

            for button in self.buttons:
                button.draw()

            # Draw the dialogue box if active
            if self.dialogue_box:
                self.dialogue_box.draw()
