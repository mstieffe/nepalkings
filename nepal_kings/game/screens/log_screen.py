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
        self.show_chat = False

        self.init_ui_elements()

        self.font = pygame.font.Font(settings.FONT_PATH, settings.FONT_SIZE_DETAIL)
        self.scroll_offset = 0  # Track vertical scrolling
        self.scroll_step = 20  # Scroll step in pixels

        # Scrollbar attributes
        self.scrollbar_width = 10
        self.scrollbar_color = settings.SCROLLBAR_COLOR
        self.scrollbar_handle_color = settings.SCROLLBAR_HANDLE_COLOR
        self.scrollbar_rect = pygame.Rect(
            settings.MSG_MAX_WIDTH - self.scrollbar_width - 10,
            settings.MSG_TEXT_Y,
            self.scrollbar_width,
            settings.MSG_MAX_HEIGHT #- settings.MSG_TEXT_Y
        )
        self.dragging = False  # Track if the scrollbar handle is being dragged
        self.handle_rect = pygame.Rect(0, 0, self.scrollbar_width, 50)  # Placeholder for the scrollbar handle

    def init_ui_elements(self):
        """Initialize buttons, input fields, and other UI components."""
        # Buttons for toggling log and chat
        self.buttons.extend([
            self.make_button("Log", settings.MSG_LOG_BUTTON_X, settings.MSG_LOG_BUTTON_Y),
            self.make_button("Chat", settings.MSG_CHAT_BUTTON_X, settings.MSG_CHAT_BUTTON_Y),
            self.make_button("Send", settings.MSG_SEND_BUTTON_X, settings.MSG_SEND_BUTTON_Y),
        ])
        self.buttons[0].active = True

        # Input field for chat messages
        self.chat_input = InputField(
            self.window,
            settings.MSG_INPUT_X,
            settings.MSG_INPUT_Y,
            "Type your message...",
            max_length=200,
        )

    def handle_events(self, events):
        """Handle events for scrolling, toggling views, and sending chat messages."""
        super().handle_events(events)
        for event in events:
            # Handle InputField events
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

                # Check if the scrollbar handle is clicked
                if self.handle_rect.collidepoint(event.pos):
                    self.dragging = True

            elif event.type == MOUSEBUTTONUP:
                self.dragging = False

            elif event.type == MOUSEMOTION and self.dragging:
                self.handle_scrollbar_drag(event)

            # Scroll up or down using the mouse wheel
            if event.type == MOUSEWHEEL:
                self.scroll_offset = max(0, self.scroll_offset - event.y * self.scroll_step)
                max_scroll = self.calculate_max_scroll()
                self.scroll_offset = min(self.scroll_offset, max_scroll)

            # Handle enter key for sending messages
            elif event.type == KEYDOWN and event.key == K_RETURN and self.chat_input.content.strip():
                self.handle_send_message(self.chat_input.content.strip())
                self.chat_input.empty()

    def handle_scrollbar_drag(self, event):
        """Adjust the scroll offset based on scrollbar handle movement."""
        handle_y_min = self.scrollbar_rect.y
        handle_y_max = self.scrollbar_rect.y + self.scrollbar_rect.height - self.handle_rect.height
        self.handle_rect.y = max(handle_y_min, min(handle_y_max, event.pos[1]))

        # Update scroll offset proportionally
        content_height = len(self.get_combined_messages()) * (self.font.get_height() + 10)
        if content_height > settings.MSG_MAX_HEIGHT:
            scroll_ratio = (self.handle_rect.y - handle_y_min) / (handle_y_max - handle_y_min)
            self.scroll_offset = int(scroll_ratio * (content_height - settings.MSG_MAX_HEIGHT))

    def calculate_max_scroll(self):
        """Calculate the maximum scroll offset."""
        content_height = len(self.get_combined_messages()) * (self.font.get_height() + 10)
        return max(content_height - settings.MSG_MAX_HEIGHT, 0)

    def get_combined_messages(self):
        """Combine log and chat messages, sorted by timestamp."""
        combined = []
        if self.show_log:
            combined.extend(self.game.log_entries)
        if self.show_chat:
            combined.extend(self.game.chat_messages)
        combined.sort(key=lambda msg: msg['timestamp'])  # Sort by timestamp
        return combined

    def draw_scrollbar(self):
        """Draw the scrollbar and its handle only if necessary."""
        content_height = len(self.get_combined_messages()) * (self.font.get_height() + 10)

        # Determine if the scrollbar is necessary
        if content_height <= settings.MSG_MAX_HEIGHT:
            return  # Do not draw the scrollbar if all messages fit in the visible area

        # Calculate handle height proportionally to the content height
        handle_height = max(settings.MSG_MAX_HEIGHT * (settings.MSG_MAX_HEIGHT / content_height), 20)

        # Update handle position
        scroll_ratio = self.scroll_offset / max(self.calculate_max_scroll(), 1)
        handle_y = self.scrollbar_rect.y + scroll_ratio * (self.scrollbar_rect.height - handle_height)
        self.handle_rect = pygame.Rect(
            self.scrollbar_rect.x,
            handle_y,
            self.scrollbar_width,
            handle_height
        )

        # Draw the scrollbar track
        pygame.draw.rect(self.window, self.scrollbar_color, self.scrollbar_rect)
        # Draw the scrollbar handle
        pygame.draw.rect(self.window, self.scrollbar_handle_color, self.handle_rect)

    def draw(self):
        """Draw the log and chat messages on the screen."""
        super().draw()

        # Draw combined messages directly onto the main window
        y = settings.MSG_TEXT_Y - self.scroll_offset
        max_y = settings.MSG_TEXT_Y + settings.MSG_MAX_HEIGHT  # Limit to MSG_MAX_HEIGHT

        for message in self.get_combined_messages():
            if y > max_y:  # Stop drawing if exceeding maximum height
                break

            if y + self.font.get_height() >= settings.MSG_TEXT_Y:  # Only draw visible messages
                # Distinguish log and chat messages
                if 'author' in message:
                    is_log = True
                    bg_color = settings.LOG_MSG_BG_COLOR
                    author = message['author']
                else:
                    is_log = False
                    bg_color = settings.CHAT_MSG_BG_COLOR
                    sender = self.game.get_player_username(message['sender_id'])
                    receiver = self.game.get_player_username(message['receiver_id'])
                    author = f"{sender} -> {receiver}"

                text_color = settings.MSG_TEXT_COLOR

                # Prepare message string
                msg_content = f"[{message['timestamp']}] {author}: {message['message']}"

                # Render background rectangle
                text_surface = self.font.render(msg_content, True, text_color)
                text_rect = text_surface.get_rect(topleft=(settings.MSG_TEXT_X, y))
                pygame.draw.rect(self.window, bg_color, text_rect)

                # Render text
                self.window.blit(text_surface, text_rect.topleft)
            y += self.font.get_height() + 10  # Add spacing between messages

        # Draw the scrollbar
        self.draw_scrollbar()

        # Draw the chat input field and send button
        self.chat_input.draw()
        for button in self.buttons:
            if button.text == "Send":
                button.draw()

    def update(self, game):
        """Update the log and chat messages."""
        super().update(game)
        self.game = game
        self.chat_input.update_color()


    def handle_send_message(self, message):
        """Send the chat message to the opponent using the `Game` instance."""
        opponent_id = self.game.opponent_player['id']
        try:
            self.game.send_chat_message(opponent_id, message)
        except Exception as e:
            print(f"Failed to send message: {str(e)}")
