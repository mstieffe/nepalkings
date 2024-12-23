import pygame
from config import settings
from game.components.arrow_button import ArrowButton
from game.components.cards.card_img import CardImg


class ScrollTextListShifter:
    def __init__(self, window, text_list, x, y, delta_x=-settings.get_x(0.01), num_texts_displayed=1,
                 shift_cooldown=300):
        """
        :param text_list: List of text dictionaries, each representing an item.
        """
        self.window = window
        self.scroll_font = pygame.font.Font(settings.FONT_PATH, settings.FONT_SIZE_DETAIL)
        self.scroll_font_bold = pygame.font.Font(settings.FONT_PATH, settings.FONT_SIZE_DETAIL)
        self.scroll_font_bold.set_bold(True)
        self.text_list = text_list  # List of text dictionaries
        self.x = x
        self.y = y
        self.delta_x = delta_x  # Vertical spacing between text items
        self.num_texts_displayed = num_texts_displayed
        self.shift_cooldown = shift_cooldown  # Cooldown between shifts in milliseconds
        self.last_shift_time = 0  # To track time since the last shift

        self.card_imgs = self.initialize_card_imgs()

        # Initialize text shifter states
        self.start_index = 0
        self.displayed_texts = []

        # Initialize arrow buttons for shifting
        left_x = self.x - self.delta_x
        right_x = self.x + settings.SCROLL_TEXT_MAX_WIDTH + self.delta_x

        self.arrow_up_button = ArrowButton(self.window, self.shift_up, x=left_x, y=self.y + settings.get_y(0.044),
                                           direction='left', is_active=True)
        self.arrow_down_button = ArrowButton(self.window, self.shift_down, x=right_x, y=self.y + settings.get_y(0.044),
                                             direction='right', is_active=True)

        # Update the initially displayed texts
        self.update_displayed_texts()

    def initialize_card_imgs(self):
        """Initialize card images."""
        return {(suit, rank): CardImg(self.window, suit, rank, width=settings.MINI_CARD_WIDTH,
                                      height=settings.MINI_CARD_HEIGHT) for suit in settings.SUITS for rank in
                settings.RANKS_WITH_ZK}

    def shift_up(self):
        """Shift the text list upwards, respecting the cooldown."""
        current_time = pygame.time.get_ticks()
        if current_time - self.last_shift_time >= self.shift_cooldown:
            self.start_index = (self.start_index - 1) % len(self.text_list)
            self.update_displayed_texts()
            self.last_shift_time = current_time

    def shift_down(self):
        """Shift the text list downwards, respecting the cooldown."""
        current_time = pygame.time.get_ticks()
        if current_time - self.last_shift_time >= self.shift_cooldown:
            self.start_index = (self.start_index + 1) % len(self.text_list)
            self.update_displayed_texts()
            self.last_shift_time = current_time

    def update_displayed_texts(self):
        """Update the list of texts currently being displayed."""
        if len(self.text_list) <= self.num_texts_displayed:
            self.displayed_texts = self.text_list
        elif len(self.text_list) == 0:
            self.displayed_texts = []
        else:
            indices = [(self.start_index + i) % len(self.text_list) for i in range(self.num_texts_displayed)]
            self.displayed_texts = [self.text_list[i] for i in indices]

    def draw(self):
        """Draw the texts and arrow controls."""
        # Draw arrow buttons
        if len(self.text_list) > self.num_texts_displayed:
            self.arrow_up_button.draw()
            self.arrow_down_button.draw()

        # Draw displayed texts using the custom draw function
        x_offset = 0
        for text_dict in self.displayed_texts:
            self.draw_text_in_scroll(text_dict, self.x + x_offset, self.y)
            x_offset += self.delta_x

    def draw_text_in_scroll(self, text_dict, x, y, max_width=settings.SCROLL_TEXT_MAX_WIDTH):
        """Draw text to the screen with line breaks after reaching a certain width."""
        # TITLE
        title_obj = self.scroll_font_bold.render(text_dict.get('title', ''), True, settings.SCROLL_TEXT_COLOR)
        title_rect = title_obj.get_rect()
        title_rect.midtop = (x + max_width // 2, y)
        self.window.blit(title_obj, title_rect)
        y += title_rect.height

        # Leave one blank line
        blank_line_height = self.scroll_font.size(" ")[1]
        y += blank_line_height * 0.4

        # CARDS
        if 'cards' in text_dict:
            y += blank_line_height * 0.4  # Additional spacing
            cards = text_dict.get('cards', [])
            missing_cards = text_dict.get('missing_cards', [])
            total_cards = cards + missing_cards

            num_cards = len(total_cards)
            spacer = settings.MINI_CARD_WIDTH * (0.1 if num_cards > 2 else 0.4)
            total_width = num_cards * settings.MINI_CARD_WIDTH + (num_cards - 1) * spacer

            card_x = x + (max_width - total_width) // 2
            for card in total_cards:
                card_img = self.card_imgs.get((card.suit, card.rank))
                if card in missing_cards:
                    card_img.draw_missing(card_x, y)
                else:
                    card_img.draw_front_bright(card_x, y)
                card_x += settings.MINI_CARD_WIDTH + spacer

            y += settings.MINI_CARD_HEIGHT + blank_line_height * 0.4

        # TEXT
        for line in self.wrap_text_lines(text_dict.get('text', ''), max_width):
            text_obj = self.scroll_font.render(line, True, settings.SCROLL_TEXT_COLOR)
            text_rect = text_obj.get_rect(topleft=(x, y))
            self.window.blit(text_obj, text_rect)
            y += text_rect.height

        # FIGURE STRENGTH
        if 'figure_strength' in text_dict:
            y += blank_line_height * 0.4
            strength_obj = self.scroll_font.render(text_dict['figure_strength'], True, settings.SCROLL_TEXT_COLOR)
            strength_rect = strength_obj.get_rect(midtop=(x + max_width // 2, y))
            self.window.blit(strength_obj, strength_rect)
            y += strength_rect.height

    def wrap_text_lines(self, text, max_width):
        """Wrap text into multiple lines based on maximum width."""
        words = text.split(' ')
        lines = []
        current_line = ""

        for word in words:
            test_line = f"{current_line} {word}".strip()
            if self.scroll_font.size(test_line)[0] <= max_width:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = word

        if current_line:
            lines.append(current_line)

        return lines

    def set_displayed_texts(self, text_list):
        """Update the list of texts to be displayed."""
        self.text_list = text_list
        self.update_displayed_texts()

    def get_current_selected(self):
        """Return the currently selected content."""
        if not self.displayed_texts:  # Ensure there are displayed texts
            return None
        if self.num_texts_displayed == 1:
            selected = self.displayed_texts[0] if self.displayed_texts else None
            return selected.get('content', selected) if selected else None  # Safeguard against None
        return [text_dict.get('content', text_dict) for text_dict in self.displayed_texts if text_dict]


    def update(self):
        """Update the arrow buttons."""
        self.arrow_up_button.update()
        self.arrow_down_button.update()

    def handle_events(self, events):
        """Handle events for the arrows."""
        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN:
                if self.arrow_up_button.hovered:
                    self.shift_up()
                elif self.arrow_down_button.hovered:
                    self.shift_down()
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:
                    self.shift_up()
                elif event.key == pygame.K_DOWN:
                    self.shift_down()
