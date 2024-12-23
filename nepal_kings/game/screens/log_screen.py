import pygame
from pygame.locals import *
from config import settings
from game.screens.sub_screen import SubScreen
from utils.utils import InputField, Button


class LogScreen(SubScreen):
    """Screen for displaying log and chat messages with input capabilities and an adaptive scroll bar."""

    def __init__(self, window, state, x: int = 0.0, y: int = 0.0, title=None):
        super().__init__(window, state.game, x, y, title)
        self.state = state
        self.game = state.game

        self.show_log = True
        self.show_chat = True

        self.init_ui_elements()

        self.font = pygame.font.Font(settings.FONT_PATH, settings.MSG_FONT_SIZE)
        self.scroll_step = 1  # Number of lines scrolled per step

        # Scrollbar attributes
        self.scrollbar_color = settings.SCROLLBAR_COLOR
        self.scrollbar_handle_color_active = settings.SCROLLBAR_HANDLE_COLOR_ACTIVE
        self.scrollbar_handle_color_passive = settings.SCROLLBAR_HANDLE_COLOR_PASSIVE
        self.scrollbar_handle_color = self.scrollbar_handle_color_passive

        self.scrollbar_rect = pygame.Rect(
            settings.SCROLLBAR_X,
            settings.SCROLLBAR_Y,
            settings.SCROLLBAR_WIDTH,
            settings.SCROLLBAR_HEIGHT
        )
        self.handle_rect = pygame.Rect(
            settings.SCROLLBAR_X,
            settings.SCROLLBAR_Y,
            settings.SCROLLBAR_WIDTH,
            50  # Placeholder height; updated dynamically
        )
        self.dragging = False

        # Initialize with the scrollbar at the bottom
        self.scroll_offset = self.calculate_max_scroll()

    def init_ui_elements(self):
        """Initialize buttons, input fields, and other UI components."""
        super().init_sub_box_background(
            settings.MSG_TEXT_BOX_X, settings.MSG_TEXT_BOX_Y, settings.MSG_TEXT_BOX_WIDTH, settings.MSG_TEXT_BOX_HEIGHT
        )

        # Buttons for toggling log and chat
        self.buttons.extend([
            self.make_button("Log", settings.MSG_LOG_BUTTON_X, settings.MSG_LOG_BUTTON_Y),
            self.make_button("Chat", settings.MSG_CHAT_BUTTON_X, settings.MSG_CHAT_BUTTON_Y),
            self.make_button("Send", settings.MSG_SEND_BUTTON_X, settings.MSG_SEND_BUTTON_Y),
        ])
        self.buttons[0].active = True
        self.buttons[1].active = True


        # Input field for chat messages
        self.chat_input = InputField(
            self.window,
            settings.MSG_INPUT_X,
            settings.MSG_INPUT_Y,
            "Type your message...",
            max_length=300,
        )


    def draw(self):
        """Draw the log and chat messages on the screen."""
        super().draw()

        messages = self.get_combined_messages()
        rendered_lines = self.calculate_rendered_lines(messages)

        # Clamp scroll_offset to valid range
        max_scroll = max(0, len(rendered_lines) - self.max_lines_on_screen())
        self.scroll_offset = min(self.scroll_offset, max_scroll)

        y = settings.MSG_TEXT_Y
        max_y = settings.MSG_TEXT_Y + settings.MSG_MAX_HEIGHT

        # Render lines within the visible range
        visible_lines = rendered_lines[self.scroll_offset:self.scroll_offset + self.max_lines_on_screen()]
        for bg_color, line in visible_lines:
            if y + self.font.get_height() > max_y:
                break

            text_surface = self.font.render(line, True, settings.MSG_TEXT_COLOR)
            text_rect = text_surface.get_rect(topleft=(settings.MSG_TEXT_X, y))
            self.draw_transparent_background(self.window, bg_color, text_rect)
            self.window.blit(text_surface, text_rect.topleft)

            y += self.font.get_height() + 5

        # Draw scrollbar and input field
        self.draw_scrollbar()
        self.chat_input.draw()
        for button in self.buttons:
            if button.text == "Send":
                button.draw()

    def calculate_rendered_lines(self, messages):
        """Calculate all rendered lines for the given messages."""
        rendered_lines = []
        max_width = settings.MSG_MAX_WIDTH - settings.MSG_TEXT_X

        for message in messages:
            if 'author' in message:
                bg_color = (
                    settings.LOG_MSG_SELF_BG_COLOR if message['author'] == (self.game.current_player.get('username') if self.game else '')
                    else settings.LOG_MSG_OPP_BG_COLOR
                )
                msg_content = f"[{message['timestamp'][:16]}] {message['message']}"
            else:
                sender = self.game.get_player_username(message['sender_id']) if self.game else 'Unknown'
                bg_color = (
                    settings.CHAT_MSG_SELF_BG_COLOR if sender == (self.game.current_player.get('username') if self.game else '')
                    else settings.CHAT_MSG_OPP_BG_COLOR
                )
                msg_content = f"[{message['timestamp'][:16]}] {sender}: {message['message']}"

            # Wrap text and store lines with their corresponding background color
            wrapped_lines = self.wrap_text(msg_content, max_width)
            for line in wrapped_lines:
                rendered_lines.append((bg_color, line))

        return rendered_lines
    

    def handle_scrollbar_drag(self, event):
        """Adjust scroll offset based on scrollbar drag."""
        handle_y_min = self.scrollbar_rect.y
        handle_y_max = self.scrollbar_rect.y + self.scrollbar_rect.height - self.handle_rect.height

        # Clamp handle position
        self.handle_rect.y = max(handle_y_min, min(handle_y_max, event.pos[1]))

        # Update scroll_offset proportional to handle position
        content_height = len(self.get_combined_messages())
        max_scroll = max(0, content_height - settings.MSG_MAX_HEIGHT // (self.font.get_height() + 5))
        handle_ratio = (self.handle_rect.y - handle_y_min) / (handle_y_max - handle_y_min)
        self.scroll_offset = int(handle_ratio * max_scroll)

    def handle_events(self, events):
        """Handle events for scrolling, toggling views, and sending chat messages."""
        super().handle_events(events)
        for event in events:
            self.chat_input.handle_event(event)

            if event.type == MOUSEBUTTONDOWN:
                for button in self.buttons:
                    if button.collide():
                        button.active = not button.active
                        if button.text == "Log":
                            self.show_log = not self.show_log
                        elif button.text == "Chat":
                            self.show_chat = not self.show_chat
                        elif button.text == "Send" and self.chat_input.content.strip():
                            self.handle_send_message(self.chat_input.content.strip())
                            self.chat_input.empty()
                            button.active = False

                if self.handle_rect.collidepoint(event.pos):
                    self.dragging = True
                    self.scrollbar_handle_color = self.scrollbar_handle_color_active

            elif event.type == MOUSEBUTTONUP:
                self.dragging = False
                self.scrollbar_handle_color = self.scrollbar_handle_color_passive

            elif event.type == MOUSEMOTION and self.dragging:
                self.handle_scrollbar_drag(event)

            if event.type == MOUSEWHEEL:
                max_scroll = self.calculate_max_scroll()
                self.scroll_offset = max(0, min(self.scroll_offset - event.y * self.scroll_step, max_scroll))

            elif event.type == KEYDOWN and event.key == K_RETURN and self.chat_input.content.strip():
                self.handle_send_message(self.chat_input.content.strip())
                self.chat_input.empty()

    def draw_scrollbar(self):
        """Draw the scrollbar and its handle."""
        self.update_scrollbar_handle()
        if self.handle_rect.height > 0:
            pygame.draw.rect(self.window, self.scrollbar_color, self.scrollbar_rect)
            pygame.draw.rect(self.window, self.scrollbar_handle_color, self.handle_rect)


    def update_scrollbar_handle(self):
        """Update the scrollbar handle's size and position."""
        rendered_lines = self.calculate_rendered_lines(self.get_combined_messages())
        total_lines = len(rendered_lines)
        max_visible_lines = self.max_lines_on_screen()

        # Determine the maximum scroll value
        max_scroll = max(0, total_lines - max_visible_lines)

        if total_lines <= max_visible_lines:
            self.handle_rect.height = 0  # Hide the scrollbar
        else:
            # Calculate handle height proportionally to total lines
            visible_ratio = max_visible_lines / total_lines
            handle_height = max(settings.SCROLLBAR_HEIGHT * visible_ratio, 20)  # Minimum height of 20px
            handle_y = self.scrollbar_rect.y + (self.scroll_offset / max_scroll if max_scroll > 0 else 0) * (
                self.scrollbar_rect.height - handle_height
            )
            self.handle_rect.update(self.scrollbar_rect.x, handle_y, settings.SCROLLBAR_WIDTH, handle_height)


    def wrap_text(self, text, max_width):
        """Wrap text into multiple lines based on the maximum allowed width."""
        words = text.split()
        wrapped_lines = []
        current_line = ""

        for word in words:
            test_line = f"{current_line} {word}".strip()
            if self.font.size(test_line)[0] <= max_width:
                current_line = test_line
            else:
                wrapped_lines.append(current_line)
                current_line = word

        if current_line:
            wrapped_lines.append(current_line)

        return wrapped_lines

    def draw_transparent_background(self, surface, color, rect):
        """Draw a rectangle with a transparent background."""
        temp_surface = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        temp_surface.fill((*color[:3], settings.MSG_BG_TRANSPARENCY))
        surface.blit(temp_surface, rect.topleft)

    def get_combined_messages(self):
        """Combine log and chat messages, sorted by timestamp."""
        if not self.game:  # If game is not initialized, return an empty list
            return []
        combined = []
        if self.show_log and self.game.log_entries is not None:
            combined.extend(self.game.log_entries)
        if self.show_chat and self.game.chat_messages is not None:
            combined.extend(self.game.chat_messages)
        combined.sort(key=lambda msg: msg['timestamp'])
        return combined

    def calculate_max_scroll(self):
        """Calculate the maximum scroll offset based on rendered lines."""
        rendered_lines = self.calculate_rendered_lines(self.get_combined_messages())
        total_lines = len(rendered_lines)
        return max(0, total_lines - self.max_lines_on_screen())

    def handle_send_message(self, message):
        """Send the chat message to the opponent using the `Game` instance."""
        if not self.game:  # Do nothing if the game is not initialized
            print("Cannot send message: Game is not initialized.")
            return
        opponent_id = self.game.opponent_player.get('id', -1)
        try:
            self.game.send_chat_message(opponent_id, message)
            # After sending, scroll to the bottom
            self.scroll_offset = self.calculate_max_scroll()
            self.update_scrollbar_handle()
        except Exception as e:
            print(f"Failed to send message: {str(e)}")

    def max_lines_on_screen(self):
        """Calculate the maximum number of lines that can fit on the screen."""
        return settings.MSG_MAX_HEIGHT // (self.font.get_height() + 5)