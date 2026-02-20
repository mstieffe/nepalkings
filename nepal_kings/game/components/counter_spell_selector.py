"""
Counter Spell Selector Component

A UI component for selecting which counter spell to cast in response to an opponent's spell.
Based on scroll_text_list_shifter but designed specifically for counter spell selection.
"""

import pygame
from config import settings
from game.components.arrow_button import ArrowButton
from game.components.cards.card_img import CardImg
from utils.utils import Button


class CounterSpellSelector:
    """Interactive selector for choosing which counter spell to cast."""
    
    def __init__(self, window, spell_options, x, y, width, height):
        """
        Initialize the counter spell selector.
        
        :param window: Pygame window surface
        :param spell_options: List of dicts with 'spell' (Spell object) and 'label' (str)
        :param x: X position for the selector
        :param y: Y position for the selector
        :param width: Width of the selector area
        :param height: Height of the selector area
        """
        self.window = window
        self.spell_options = spell_options
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        
        # Fonts
        self.title_font = pygame.font.Font(settings.FONT_PATH, int(settings.FONT_SIZE_DETAIL * 1.2))
        self.title_font.set_bold(True)
        self.spell_font = pygame.font.Font(settings.FONT_PATH, int(settings.FONT_SIZE_DETAIL * 1.0))
        self.detail_font = pygame.font.Font(settings.FONT_PATH, int(settings.FONT_SIZE_DETAIL * 0.85))
        
        # Current selection
        self.current_index = 0
        self.shift_cooldown = 200  # ms between shifts
        self.last_shift_time = 0
        
        # Initialize card images
        self.card_imgs = self.initialize_card_imgs()
        
        # Calculate arrow positions (inside the selector box, near the edges)
        arrow_horizontal_padding = settings.get_x(0.015)  # Padding from box edge
        arrow_y = self.y + self.height // 2  # Center vertically in selector
        left_x = self.x + arrow_horizontal_padding
        right_x = self.x + self.width - arrow_horizontal_padding
        
        self.arrow_left_button = ArrowButton(
            self.window, self.shift_left, 
            x=left_x, y=arrow_y,
            direction='left', is_active=True
        )
        self.arrow_right_button = ArrowButton(
            self.window, self.shift_right,
            x=right_x, y=arrow_y,
            direction='right', is_active=True
        )
        
        # Select and Cancel buttons
        button_width = settings.get_x(0.12)
        button_height = settings.get_y(0.04)
        button_spacing = settings.get_x(0.02)
        
        # Position buttons side by side
        total_button_width = button_width * 2 + button_spacing
        button_start_x = self.x + (self.width - total_button_width) // 2
        button_y = self.y + self.height - button_height - settings.get_y(0.02)
        
        self.select_button = Button(
            self.window,
            x=button_start_x,
            y=button_y,
            text="Cast Counter",
            width=button_width,
            height=button_height
        )
        
        self.cancel_button = Button(
            self.window,
            x=button_start_x + button_width + button_spacing,
            y=button_y,
            text="Cancel",
            width=button_width,
            height=button_height
        )
        
        self.selected_spell = None  # Will be set when player clicks select button
    
    def initialize_card_imgs(self):
        """Initialize card images for spell cards."""
        card_width = int(settings.MINI_CARD_WIDTH * 1.6)
        card_height = int(settings.MINI_CARD_HEIGHT * 1.6)
        return {
            (suit, rank): CardImg(self.window, suit, rank, width=card_width, height=card_height)
            for suit in settings.SUITS 
            for rank in settings.RANKS_WITH_ZK
        }
    
    def shift_left(self):
        """Shift selection to the left (previous spell)."""
        current_time = pygame.time.get_ticks()
        if current_time - self.last_shift_time >= self.shift_cooldown:
            self.current_index = (self.current_index - 1) % len(self.spell_options)
            self.last_shift_time = current_time
    
    def shift_right(self):
        """Shift selection to the right (next spell)."""
        current_time = pygame.time.get_ticks()
        if current_time - self.last_shift_time >= self.shift_cooldown:
            self.current_index = (self.current_index + 1) % len(self.spell_options)
            self.last_shift_time = current_time
    
    def draw(self):
        """Draw the counter spell selector UI."""
        if not self.spell_options:
            return
        
        # Draw background box with border (similar to dialogue box styling)
        border_width = 8
        border_color = (40, 40, 40)
        background_color = (80, 80, 80)
        
        # Draw border
        border_rect = pygame.Rect(
            self.x - border_width,
            self.y - border_width,
            self.width + 2 * border_width,
            self.height + 2 * border_width
        )
        pygame.draw.rect(self.window, border_color, border_rect)
        
        # Draw background
        background_rect = pygame.Rect(self.x, self.y, self.width, self.height)
        pygame.draw.rect(self.window, background_color, background_rect)
        
        # Draw arrows if more than one option (center them vertically)
        if len(self.spell_options) > 1:
            self.arrow_left_button.draw()
            self.arrow_right_button.draw()
        
        # Draw current spell option
        current_option = self.spell_options[self.current_index]
        spell = current_option['spell']
        
        # Add padding for content
        content_padding_top = settings.get_y(0.03)
        current_y = self.y + content_padding_top
        
        # Draw title
        title_text = f"Counter Spell Option {self.current_index + 1}/{len(self.spell_options)}"
        title_surface = self.title_font.render(title_text, True, settings.SCROLL_TEXT_COLOR)
        title_rect = title_surface.get_rect(midtop=(self.x + self.width // 2, current_y))
        self.window.blit(title_surface, title_rect)
        
        current_y = title_rect.bottom + settings.get_y(0.01)
        
        # Draw spell name
        spell_name_surface = self.spell_font.render(spell.name, True, settings.SCROLL_TEXT_COLOR)
        spell_name_rect = spell_name_surface.get_rect(midtop=(self.x + self.width // 2, current_y))
        self.window.blit(spell_name_surface, spell_name_rect)
        
        current_y = spell_name_rect.bottom + settings.get_y(0.015)
        
        # Draw spell cards
        cards = spell.cards
        if cards:
            num_cards = len(cards)
            card_img = self.card_imgs.get((cards[0].suit, cards[0].rank))
            if card_img:
                card_width = card_img.front_img.get_width()
                card_height = card_img.front_img.get_height()
                
                # Calculate spacing
                if num_cards > 2:
                    spacer = card_width * 0.15
                else:
                    spacer = card_width * 0.25
                
                total_width = card_width * num_cards + spacer * (num_cards - 1)
                card_x = self.x + (self.width - total_width) // 2
                
                for card in cards:
                    card_img = self.card_imgs.get((card.suit, card.rank))
                    if card_img:
                        card_img.draw_front_bright(card_x, current_y)
                        card_x += card_width + spacer
                
                current_y += card_height + settings.get_y(0.01)
        
        # Draw spell type and suit
        type_text = f"{spell.family.type.title()} Spell ({spell.suit})"
        type_surface = self.detail_font.render(type_text, True, settings.SCROLL_TEXT_COLOR)
        type_rect = type_surface.get_rect(midtop=(self.x + self.width // 2, current_y))
        self.window.blit(type_surface, type_rect)
        
        current_y = type_rect.bottom + settings.get_y(0.015)
        
        # Draw description
        if spell.family.description:
            # Word wrap description
            words = spell.family.description.split()
            lines = []
            current_line = []
            max_line_width = int(self.width * 0.9)
            
            for word in words:
                test_line = ' '.join(current_line + [word])
                test_surface = self.detail_font.render(test_line, True, settings.SCROLL_TEXT_COLOR)
                if test_surface.get_width() <= max_line_width:
                    current_line.append(word)
                else:
                    if current_line:
                        lines.append(' '.join(current_line))
                    current_line = [word]
            
            if current_line:
                lines.append(' '.join(current_line))
            
            # Draw lines
            for line in lines[:3]:  # Limit to 3 lines
                line_surface = self.detail_font.render(line, True, settings.SCROLL_TEXT_COLOR)
                line_rect = line_surface.get_rect(midtop=(self.x + self.width // 2, current_y))
                self.window.blit(line_surface, line_rect)
                current_y = line_rect.bottom + settings.get_y(0.005)
        
        # Draw select and cancel buttons
        self.select_button.draw()
        self.cancel_button.draw()
    
    def handle_events(self, events):
        """
        Handle user input events.
        
        :param events: List of pygame events
        :return: Selected spell object if player clicked select, 'CANCEL' if cancelled, None otherwise
        """
        # Update button hover states first
        self.select_button.update()
        self.cancel_button.update()
        if len(self.spell_options) > 1:
            self.arrow_left_button.update()
            self.arrow_right_button.update()
        
        # Handle arrow button clicks
        if len(self.spell_options) > 1:
            for event in events:
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if self.arrow_left_button.collide():
                        self.shift_left()
                    elif self.arrow_right_button.collide():
                        self.shift_right()
        
        # Handle select and cancel buttons
        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN:
                if self.select_button.collide():
                    self.select_button.clicked = True
                    self.selected_spell = self.spell_options[self.current_index]['spell']
                    return self.selected_spell
                elif self.cancel_button.collide():
                    self.cancel_button.clicked = True
                    return 'CANCEL'
        
        # Handle keyboard shortcuts
        for event in events:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_LEFT and len(self.spell_options) > 1:
                    self.shift_left()
                elif event.key == pygame.K_RIGHT and len(self.spell_options) > 1:
                    self.shift_right()
                elif event.key == pygame.K_RETURN or event.key == pygame.K_SPACE:
                    self.selected_spell = self.spell_options[self.current_index]['spell']
                    return self.selected_spell
                elif event.key == pygame.K_ESCAPE:
                    return 'CANCEL'
        
        return None
    
    def update(self):
        """Update button hover states - no longer needed as update is called in handle_events."""
        pass
