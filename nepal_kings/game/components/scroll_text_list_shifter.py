import pygame
from config import settings
from game.components.arrow_button import ArrowButton
from game.components.cards.card_img import CardImg
from game.components.cards.card import Card

class ScrollTextListShifter:
    def __init__(self, window, text_list, x, y, delta_x=-settings.get_x(0.018), num_texts_displayed=1,
                 shift_cooldown=300):
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

        # Initialize title and font
        #self.title = title
        #self.font = pygame.font.Font(settings.FONT_PATH, settings.SCROLL_TEXT_FONT_SIZE)
        #self.text_surface = self.font.render(self.title, True, settings.SUIT_ICON_CAPTION_COLOR)
        #self.text_rect = self.text_surface.get_rect(center=(self.x, self.y - title_offset_y))

        self.card_imgs = self.initialize_card_imgs()
        #self.rec_card = pygame.Rect(self.x, self.y, settings.MINI_CARD_WIDTH, settings.MINI_CARD_HEIGHT)

        # Initialize text shifter states
        self.start_index = 0
        self.displayed_texts = []

        # Initialize arrow buttons for shifting
        # Calculate the x coordinates for the left and right positions
        left_x = self.x - self.delta_x
        right_x = self.x + settings.SCROLL_TEXT_MAX_WIDTH + self.delta_x #+ settings.get_x(0.005)

        # Create the arrow buttons with the updated x coordinates
        self.arrow_up_button = ArrowButton(self.window, self.shift_up, x=left_x, y=self.y+settings.get_y(0.041), direction='left', is_active=True)
        self.arrow_down_button = ArrowButton(self.window, self.shift_down, x=right_x, y=self.y+settings.get_y(0.041), direction='right', is_active=True)

        # Update the initially displayed texts
        self.update_displayed_texts()

    def initialize_card_imgs(self):
        return {(suit, rank): CardImg(self.window, suit, rank, width=settings.MINI_CARD_WIDTH, height=settings.MINI_CARD_HEIGHT) for suit in settings.SUITS for rank in settings.RANKS_WITH_ZK}

    def shift_up(self):
        """Shift the text list upwards, respecting the cooldown."""
        current_time = pygame.time.get_ticks()
        if current_time - self.last_shift_time >= self.shift_cooldown:
            self.start_index = (self.start_index - 1) % len(self.text_list)
            self.update_displayed_texts()
            self.last_shift_time = current_time  # Reset the shift timer

    def shift_down(self):
        """Shift the text list downwards, respecting the cooldown."""
        current_time = pygame.time.get_ticks()
        if current_time - self.last_shift_time >= self.shift_cooldown:
            self.start_index = (self.start_index + 1) % len(self.text_list)
            self.update_displayed_texts()
            self.last_shift_time = current_time  # Reset the shift timer

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
        # Draw title
        #self.window.blit(self.text_surface, self.text_rect)

        # Draw arrow buttons
        if len(self.text_list) > self.num_texts_displayed:
            self.arrow_up_button.draw()
            self.arrow_down_button.draw()

        # Draw displayed texts using the custom draw function
        x_offset = 0
        for text in self.displayed_texts:
            self.draw_text_in_scroll(text, self.x + x_offset, self.y)
            x_offset += self.delta_x

    def draw_text_in_scroll(self, text_dict, x, y, max_width=settings.SCROLL_TEXT_MAX_WIDTH):
        """Draw text to the screen with line breaks after reaching a certain width."""
        # TITLE
        title_obj = self.scroll_font_bold.render(text_dict['title'], True, settings.SCROLL_TEXT_COLOR)
        title_rect = title_obj.get_rect()
        title_rect.midtop = (x + max_width // 2, y)  # Center the title
        self.window.blit(title_obj, title_rect)
        y += title_rect.height

        # Leave one blank line
        blank_line_height = self.scroll_font.size(" ")[1]
        y += blank_line_height * 0.4

        # CARDS
        if 'cards' in text_dict:
            # Leave one blank line
            y += blank_line_height * 0.4

            # Draw cards
            if 'missing_cards' in text_dict:
                cards = text_dict['cards'] + text_dict['missing_cards']
            else:
                cards = text_dict['cards']
            num_cards = len(cards)
            if num_cards > 2:
                spacer = settings.MINI_CARD_WIDTH * 0.1
            else:
                spacer = settings.MINI_CARD_WIDTH * 0.4
            total_cards_width = num_cards * settings.MINI_CARD_WIDTH + (num_cards - 1) * spacer

            # Calculate the starting x position to center the cards
            card_x = x + (max_width - total_cards_width) // 2
            card_y = y

            for card in text_dict['cards']:
                card_img = self.card_imgs[(card.suit, card.rank)]
                card_img.draw_front_bright(card_x, card_y)
                card_x += settings.MINI_CARD_WIDTH + spacer
            if 'missing_cards' in text_dict:
                for card in text_dict['missing_cards']:
                    card_img = self.card_imgs[(card.suit, card.rank)]
                    card_img.draw_front(card_x, card_y)
                    card_x += settings.MINI_CARD_WIDTH + spacer
            y += settings.MINI_CARD_HEIGHT + blank_line_height * 0.4

        # TEXT
        words = text_dict['text'].split(' ')
        lines = []
        current_line = ""

        for word in words:
            # Check the width of the current line with the new word added
            test_line = current_line + word + " "
            test_width, _ = self.scroll_font.size(test_line)

            if test_width <= max_width:
                current_line = test_line
            else:
                # If the line exceeds the max width, add the current line to lines and start a new line
                lines.append(current_line)
                current_line = word + " "

        # Add the last line to lines
        if current_line:
            lines.append(current_line)

        # Draw each line to the screen
        for line in lines:
            text_obj = self.scroll_font.render(line, True, settings.SCROLL_TEXT_COLOR)
            text_rect = text_obj.get_rect()
            text_rect.topleft = (x, y)
            self.window.blit(text_obj, text_rect)
            y += text_rect.height  # Move y position for the next line

        # Check if "figure_strength" is in the text_dict
        if 'figure_strength' in text_dict:
            # Leave one blank line
            y += blank_line_height * 0.4

            # Draw figure strength
            figure_strength_obj = self.scroll_font.render(text_dict['figure_strength'], True, settings.SCROLL_TEXT_COLOR)
            figure_strength_rect = figure_strength_obj.get_rect()
            figure_strength_rect.midtop = (x + max_width // 2, y)
            self.window.blit(figure_strength_obj, figure_strength_rect)
            y += figure_strength_rect.height


    def set_displayed_texts(self, text_list):
        """Update the list of texts to be displayed."""
        self.text_list = text_list
        self.update_displayed_texts()

    def update(self):
        """Update the arrow buttons and displayed texts."""
        self.arrow_up_button.update()
        self.arrow_down_button.update()

    def handle_events(self, events):
        """Handle events for the arrows."""
        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN:
                if self.arrow_up_button.hovered:
                    self.shift_up()  # Shift up with cooldown
                elif self.arrow_down_button.hovered:
                    self.shift_down()  # Shift down with cooldown

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:
                    self.shift_up()  # Shift up with cooldown
                elif event.key == pygame.K_DOWN:
                    self.shift_down()  # Shift down with cooldown
