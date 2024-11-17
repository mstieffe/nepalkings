from config import settings
import pygame
from game.components.arrow_button import ArrowButton

class ButtonListShifter:

    def __init__(self, window, button_list, x, y, delta_x, num_buttons_displayed=4, title='', title_offset_y=settings.get_y(0.05), shift_cooldown=300, exclusive_selection=True):
        self.window = window
        self.button_list = button_list
        self.x = x
        self.y = y
        self.delta_x = delta_x
        self.num_buttons_displayed = num_buttons_displayed
        self.shift_cooldown = shift_cooldown  # Cooldown between shifts in milliseconds
        self.last_shift_time = 0  # To track time since the last shift
        self.exclusive_selection = exclusive_selection  # Whether selection is exclusive

        # Initialize title and font
        self.title = title
        self.font = pygame.font.Font(settings.FONT_PATH, settings.GAME_BUTTON_FONT_SIZE)
        self.text_surface = self.font.render(self.title, True, settings.SUIT_ICON_CAPTION_COLOR)
        self.text_rect = self.text_surface.get_rect(center=(self.x + (self.num_buttons_displayed - 1) * self.delta_x / 2, self.y - title_offset_y))

        # Initialize button shifter states
        self.start_index = 0
        self.displayed_buttons = []
        self.active_button = None  # Store the currently active button for exclusive selection

        # Initialize arrow buttons for shifting
        self.arrow_left_button = ArrowButton(self.window, self.shift_left, x=self.x - self.delta_x * 0.7, y=self.y, direction='left', is_active=True)
        self.arrow_right_button = ArrowButton(self.window, self.shift_right, x=self.x + self.delta_x * (num_buttons_displayed - 1) + self.delta_x * 0.7, y=self.y, direction='right', is_active=True)

        # Update the initially displayed buttons
        self.update_displayed_buttons()

    def shift_left(self):
        """Shift the button list to the left, respecting the cooldown."""
        current_time = pygame.time.get_ticks()
        if current_time - self.last_shift_time >= self.shift_cooldown:
            self.start_index = (self.start_index + 1) % len(self.button_list)
            self.update_displayed_buttons()
            self.last_shift_time = current_time  # Reset the shift timer

    def shift_right(self):
        """Shift the button list to the right, respecting the cooldown."""
        current_time = pygame.time.get_ticks()
        if current_time - self.last_shift_time >= self.shift_cooldown:
            self.start_index = (self.start_index - 1) % len(self.button_list)
            self.update_displayed_buttons()
            self.last_shift_time = current_time  # Reset the shift timer

    def update_displayed_buttons(self):
        """Update the list of buttons currently being displayed."""
        indices = [(self.start_index + i) % len(self.button_list) for i in range(self.num_buttons_displayed)]
        self.displayed_buttons = [self.button_list[i] for i in indices]

        # Set position for each displayed button
        for i, button in enumerate(self.displayed_buttons):
            button.set_position(self.x + i * self.delta_x, self.y)

    def draw(self):
        """Draw the buttons and arrow controls."""
        if len(self.button_list) > self.num_buttons_displayed:
            self.arrow_left_button.draw()
            self.arrow_right_button.draw()

        for button in self.displayed_buttons:
            button.draw()

        self.window.blit(self.text_surface, self.text_rect)

    def update(self, game):
        """Update the arrow buttons and the currently displayed buttons."""
        self.arrow_left_button.update()
        self.arrow_right_button.update()
        self.update_displayed_buttons()
        for button in self.displayed_buttons:
            button.update(game)

    def handle_events(self, events):
        """Handle events for the buttons and arrows."""
        for button in self.displayed_buttons:
            button.handle_events(events)

            # Handle exclusive selection if enabled
            if self.exclusive_selection:
                if button.clicked and button.is_active:
                    if self.active_button and self.active_button != button:
                        self.active_button.clicked = False  # Deactivate previously active button
                        self.active_button.is_active = False
                    self.active_button = button  # Set the new active button

        # Handle arrow button events
        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN:
                if self.arrow_left_button.hovered:
                    self.shift_left()  # Shift left with cooldown
                elif self.arrow_right_button.hovered:
                    self.shift_right()  # Shift right with cooldown

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_LEFT:
                    self.shift_left()  # Shift left with cooldown
                elif event.key == pygame.K_RIGHT:
                    self.shift_right()  # Shift right with cooldown

