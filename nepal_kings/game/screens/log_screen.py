# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
import sys
import pygame
from pygame.locals import *
from datetime import datetime
from config import settings
from game.core.input_state import get_pressed as _get_pressed
from game.screens.sub_screen import SubScreen


# ═══════════════════════════════════════════════════════════════════
#  _LogToggleButton – dark-themed programmatic toggle button
# ═══════════════════════════════════════════════════════════════════

class _LogToggleButton:
    """Small dark-themed toggle button for Log / Chat filters."""

    def __init__(self, window, x, y, text, active=False):
        self.window = window
        self.text = text
        self.active = active
        self.hovered = False
        self.clicked = False
        self.rect = pygame.Rect(x, y, settings.LOG_BTN_W, settings.LOG_BTN_H)
        self.font = settings.get_font(settings.LOG_BTN_FONT_SIZE)
        self._r = settings.LOG_BTN_CORNER_R

    def collide(self):
        return self.rect.collidepoint(pygame.mouse.get_pos())

    def update(self):
        self.hovered = self.collide()
        self.clicked = self.hovered and _get_pressed()[0]

    def draw(self):
        if self.active:
            bg = settings.LOG_BTN_BG_ACTIVE_CLR
            bdr = settings.LOG_BTN_BORDER_ACTIVE_CLR
            txt = settings.LOG_BTN_TEXT_ACTIVE_CLR
        elif self.hovered:
            bg = settings.LOG_BTN_BG_HOVER_CLR
            bdr = settings.LOG_BTN_BORDER_ACTIVE_CLR
            txt = settings.LOG_BTN_TEXT_ACTIVE_CLR
        else:
            bg = settings.LOG_BTN_BG_CLR
            bdr = settings.LOG_BTN_BORDER_CLR
            txt = settings.LOG_BTN_TEXT_CLR

        surf = pygame.Surface((self.rect.w, self.rect.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, bg, surf.get_rect(), border_radius=self._r)
        self.window.blit(surf, self.rect.topleft)
        pygame.draw.rect(self.window, bdr, self.rect,
                         settings.LOG_BTN_BORDER_W, border_radius=self._r)
        text_surf = self.font.render(self.text, True, txt)
        self.window.blit(text_surf, text_surf.get_rect(center=self.rect.center))


# ═══════════════════════════════════════════════════════════════════
#  _LogInputField – dark-themed chat input
# ═══════════════════════════════════════════════════════════════════

class _LogInputField:
    """Dark-themed input field for the log screen chat."""

    def __init__(self, window, x, y, placeholder="", max_length=300):
        self.window = window
        self.content = ""
        self.placeholder = placeholder
        self.max_length = max_length
        self.active = False
        _w = int(0.54 * settings.SCREEN_WIDTH)
        self.rect = pygame.Rect(x, y, _w, settings.LOG_INPUT_H)
        self.font = settings.get_font(settings.LOG_INPUT_FONT_SIZE)
        self._r = settings.LOG_INPUT_CORNER_R

    def handle_event(self, event):
        if event.type == MOUSEBUTTONDOWN:
            was_active = self.active
            self.active = self.rect.collidepoint(event.pos)
            # On mobile web, open a browser prompt for text entry
            if self.active and not was_active and sys.platform == 'emscripten':
                from utils.web_keyboard import is_mobile, prompt
                if is_mobile():
                    result = prompt(
                        self.placeholder or 'Message', self.content,
                    )
                    self.content = result[:self.max_length]
                    self.active = False
        elif event.type == KEYDOWN and self.active:
            if event.key == K_BACKSPACE:
                self.content = self.content[:-1]
        elif event.type == pygame.TEXTINPUT and self.active:
            if len(self.content) < self.max_length:
                self.content += event.text

    def empty(self):
        self.content = ""

    def draw(self):
        bg = settings.LOG_INPUT_BG_ACTIVE_CLR if self.active else settings.LOG_INPUT_BG_CLR
        bdr = settings.LOG_INPUT_BORDER_ACTIVE_CLR if self.active else settings.LOG_INPUT_BORDER_CLR

        surf = pygame.Surface((self.rect.w, self.rect.h), pygame.SRCALPHA)
        pygame.draw.rect(surf, bg, surf.get_rect(), border_radius=self._r)
        self.window.blit(surf, self.rect.topleft)
        pygame.draw.rect(self.window, bdr, self.rect, 1, border_radius=self._r)

        # Text or placeholder
        if self.content:
            text_surf = self.font.render(self.content, True, settings.LOG_INPUT_TEXT_CLR)
        else:
            text_surf = self.font.render(self.placeholder, True, settings.LOG_INPUT_PLACEHOLDER_CLR)
        # Clip to rect
        clip_w = self.rect.w - int(0.016 * settings.SCREEN_WIDTH)
        text_area = text_surf.subsurface(
            pygame.Rect(max(0, text_surf.get_width() - clip_w), 0,
                        min(text_surf.get_width(), clip_w), text_surf.get_height())
        )
        tx = self.rect.x + int(0.008 * settings.SCREEN_WIDTH)
        ty = self.rect.centery - text_area.get_height() // 2
        self.window.blit(text_area, (tx, ty))

        # Cursor
        if self.active:
            cursor_x = tx + min(text_surf.get_width(), clip_w) + 2
            cy = self.rect.y + int(0.004 * settings.SCREEN_HEIGHT)
            ch = self.rect.h - int(0.008 * settings.SCREEN_HEIGHT)
            if (pygame.time.get_ticks() // 500) % 2 == 0:
                pygame.draw.line(self.window, settings.LOG_INPUT_TEXT_CLR,
                                 (cursor_x, cy), (cursor_x, cy + ch), 1)


class LogScreen(SubScreen):
    """Screen for displaying log and chat messages with input capabilities and an adaptive scroll bar."""

    def __init__(self, window, state, x: int = 0.0, y: int = 0.0, title=None):
        super().__init__(window, state.game, x, y, title)
        self.state = state
        self.game = state.game

        self.show_log = True
        self.show_chat = True

        self.init_ui_elements()

        self.font = settings.get_font(settings.MSG_FONT_SIZE)
        self.scroll_step = 1  # Number of lines scrolled per step

        # Preload log entry icons
        self._log_icon_size = settings.LOG_ICON_SIZE
        self._log_icon_pad = settings.LOG_ICON_PAD
        self._log_icon_offset = self._log_icon_size + self._log_icon_pad
        self._log_icons = {}
        _all_paths = set(settings.LOG_ICON_TYPE_MAP.values()) | set(settings.LOG_BATTLE_MOVE_ICON_MAP.values())
        for _path in _all_paths:
            try:
                _img = pygame.image.load(_path).convert_alpha()
                _img = pygame.transform.smoothscale(_img, (self._log_icon_size, self._log_icon_size))
                self._log_icons[_path] = _img
            except Exception as _e:
                print(f"[LogScreen] Failed to load icon: {_path} — {_e}")

        # Scrollbar attributes
        self.scrollbar_handle_color_active = settings.SCROLLBAR_HANDLE_COLOR_ACTIVE
        self.scrollbar_handle_color_passive = settings.SCROLLBAR_HANDLE_COLOR_PASSIVE
        self.scrollbar_handle_color = self.scrollbar_handle_color_passive
        self._scrollbar_r = settings.SCROLLBAR_CORNER_R

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
        self._touch_scrolling = False
        self._touch_last_y = 0
        self._touch_accum = 0.0  # sub-line pixel accumulator for smooth drag

        # Initialize with the scrollbar at the bottom
        self.scroll_offset = self.calculate_max_scroll()

    def reset_state(self):
        """Reset all game-specific transient state.

        Called by GameScreen._reset_game_screen_state() when switching games.
        """
        self.scroll_offset = self.calculate_max_scroll()
        self.dragging = False
        self._touch_scrolling = False
        self._touch_last_y = 0
        self._touch_accum = 0.0
        self.scrollbar_handle_color = self.scrollbar_handle_color_passive
        print("[LogScreen] State reset for game switch")

    def update(self, game):
        """Update toggle buttons and parent state."""
        super().update(game)
        for btn in self._toggle_buttons:
            btn.update()

    def init_ui_elements(self):
        """Initialize buttons, input fields, and other UI components."""
        super().init_sub_box_background(
            settings.MSG_TEXT_BOX_X, settings.MSG_TEXT_BOX_Y, settings.MSG_TEXT_BOX_WIDTH, settings.MSG_TEXT_BOX_HEIGHT
        )

        # Dark-themed toggle buttons for Log / Chat
        _btn_gap = int(0.006 * settings.SCREEN_HEIGHT)
        self.btn_log = _LogToggleButton(
            self.window, settings.MSG_LOG_BUTTON_X, settings.MSG_LOG_BUTTON_Y,
            "Log", active=True)
        self.btn_chat = _LogToggleButton(
            self.window, settings.MSG_LOG_BUTTON_X,
            settings.MSG_LOG_BUTTON_Y + settings.LOG_BTN_H + _btn_gap,
            "Chat", active=True)
        self.btn_send = _LogToggleButton(
            self.window, settings.MSG_SEND_BUTTON_X, settings.MSG_SEND_BUTTON_Y,
            "Send")
        self._toggle_buttons = [self.btn_log, self.btn_chat, self.btn_send]

        # Dark-themed chat input field
        self.chat_input = _LogInputField(
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

        _SH = settings.SCREEN_HEIGHT
        _bubble_r = settings.MSG_BUBBLE_CORNER_R
        _pad_x = settings.MSG_BUBBLE_PAD_X
        _pad_y = settings.MSG_BUBBLE_PAD_Y
        _line_h = self.font.get_height() + settings.MSG_BUBBLE_SPACING

        _icon_offset = self._log_icon_offset

        y = settings.MSG_TEXT_Y
        max_y = settings.MSG_TEXT_Y + settings.MSG_MAX_HEIGHT

        # Render lines within the visible range
        visible_lines = rendered_lines[self.scroll_offset:self.scroll_offset + self.max_lines_on_screen()]
        for entry in visible_lines:
            bg_color, line, icon, indented = entry[0], entry[1], entry[2], entry[3]
            date_prefix = entry[4] if len(entry) > 4 else None
            if y + self.font.get_height() > max_y:
                break

            text_x = settings.MSG_TEXT_X

            if date_prefix and icon:
                # Render: [date] [icon] message...
                date_surface = self.font.render(date_prefix, True, settings.MSG_TEXT_COLOR)
                msg_surface = self.font.render(line, True, settings.MSG_TEXT_COLOR)
                date_w = date_surface.get_width()
                icon_x_pos = text_x + date_w
                msg_x_pos = icon_x_pos + _icon_offset
                total_w = date_w + _icon_offset + msg_surface.get_width()
                text_rect = pygame.Rect(text_x, y, total_w, date_surface.get_height())
            else:
                text_surface = self.font.render(line, True, settings.MSG_TEXT_COLOR)
                text_rect = text_surface.get_rect(topleft=(text_x, y))

            # Rounded bubble background
            bubble_left = text_rect.x - _pad_x
            bubble_w = text_rect.width + _pad_x * 2
            bubble_rect = pygame.Rect(bubble_left, text_rect.y - _pad_y,
                                      bubble_w, text_rect.height + _pad_y * 2)
            bubble_surf = pygame.Surface((bubble_rect.w, bubble_rect.h), pygame.SRCALPHA)
            pygame.draw.rect(bubble_surf,
                             (*bg_color[:3], settings.MSG_BG_TRANSPARENCY),
                             bubble_surf.get_rect(), border_radius=_bubble_r)
            self.window.blit(bubble_surf, bubble_rect.topleft)

            if date_prefix and icon:
                # Blit date, icon, then message
                self.window.blit(date_surface, (text_x, y))
                icon_y = bubble_rect.centery - icon.get_height() // 2
                self.window.blit(icon, (icon_x_pos, icon_y))
                self.window.blit(msg_surface, (msg_x_pos, y))
            else:
                self.window.blit(text_surface, text_rect.topleft)

            y += _line_h + _pad_y

        # Draw scrollbar, input field, and toggle buttons
        self.draw_scrollbar()
        self.chat_input.draw()
        for btn in self._toggle_buttons:
            btn.draw()

    def _format_timestamp(self, iso_timestamp):
        """Format an ISO timestamp into a user-friendly short format."""
        try:
            dt = datetime.fromisoformat(iso_timestamp)
            now = datetime.utcnow()
            if dt.date() == now.date():
                return dt.strftime("Today %H:%M")
            elif (now - dt).days == 1:
                return dt.strftime("Yesterday %H:%M")
            elif dt.year == now.year:
                return dt.strftime("%b %d, %H:%M")
            else:
                return dt.strftime("%b %d %Y, %H:%M")
        except (ValueError, TypeError):
            return str(iso_timestamp)[:16]

    def _get_log_icon(self, message):
        """Return a pre-scaled icon surface for a log entry, or None."""
        log_type = message.get('type', '')

        # For battle_move, match the specific move family from message text
        if log_type == 'battle_move':
            msg_text = message.get('message', '')
            # Check longer names first ("Double Dagger" before "Dagger")
            for name in sorted(settings.LOG_BATTLE_MOVE_ICON_MAP, key=len, reverse=True):
                if name in msg_text:
                    return self._log_icons.get(settings.LOG_BATTLE_MOVE_ICON_MAP[name])

        # Fall back to type-based mapping
        icon_path = settings.LOG_ICON_TYPE_MAP.get(log_type)
        if icon_path:
            return self._log_icons.get(icon_path)
        return None

    def calculate_rendered_lines(self, messages):
        """Calculate all rendered lines for the given messages."""
        rendered_lines = []
        max_width = settings.MSG_MAX_WIDTH - settings.MSG_TEXT_X
        current_username = self.game.current_player.get('username', '') if self.game else ''
        _icon_offset = self._log_icon_offset

        for message in messages:
            ts = self._format_timestamp(message.get('timestamp', ''))
            if 'author' in message:
                # Log entry — choose color based on type (battle vs build-up)
                is_self = message['author'] == current_username
                log_type = message.get('type', '')
                if log_type in settings.BATTLE_LOG_TYPES:
                    bg_color = settings.BATTLE_LOG_SELF_BG_COLOR if is_self else settings.BATTLE_LOG_OPP_BG_COLOR
                else:
                    bg_color = settings.LOG_MSG_SELF_BG_COLOR if is_self else settings.LOG_MSG_OPP_BG_COLOR
                icon = self._get_log_icon(message)
                has_icon = icon is not None
                if has_icon:
                    # Icon goes after the date: [date] [icon] message...
                    date_prefix = f"[{ts}] "
                    date_px = self.font.size(date_prefix)[0]
                    first_wrap_w = max_width - date_px - _icon_offset
                    msg_lines = self.wrap_text(message['message'], first_wrap_w)
                    if not msg_lines:
                        msg_lines = ['']
                    # First line carries date_prefix and icon
                    rendered_lines.append((bg_color, msg_lines[0], icon, False, date_prefix))
                    # Subsequent wrapped lines — no icon, no indent
                    for line in msg_lines[1:]:
                        rendered_lines.append((bg_color, line, None, False, None))
                else:
                    msg_content = f"[{ts}] {message['message']}"
                    wrapped_lines = self.wrap_text(msg_content, max_width)
                    for line in wrapped_lines:
                        rendered_lines.append((bg_color, line, None, False, None))
            else:
                # Chat message
                sender = self.game.get_player_username(message['sender_id']) if self.game else 'Unknown'
                is_self = sender == current_username
                bg_color = settings.CHAT_MSG_SELF_BG_COLOR if is_self else settings.CHAT_MSG_OPP_BG_COLOR
                msg_content = f"[{ts}] {sender}: {message['message']}"
                wrapped_lines = self.wrap_text(msg_content, max_width)
                for line in wrapped_lines:
                    rendered_lines.append((bg_color, line, None, False, None))

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

            if event.type == MOUSEBUTTONUP:
                if not self._touch_scrolling:
                    if self.btn_log.collide():
                        self.btn_log.active = not self.btn_log.active
                        self.show_log = self.btn_log.active
                    elif self.btn_chat.collide():
                        self.btn_chat.active = not self.btn_chat.active
                        self.show_chat = self.btn_chat.active
                    elif self.btn_send.collide() and self.chat_input.content.strip():
                        self.handle_send_message(self.chat_input.content.strip())
                        self.chat_input.empty()

                # Release scrollbar drag and touch scroll
                self.dragging = False
                self._touch_scrolling = False
                self._touch_accum = 0.0
                self.scrollbar_handle_color = self.scrollbar_handle_color_passive

            elif event.type == MOUSEBUTTONDOWN:
                if self.handle_rect.collidepoint(event.pos):
                    self.dragging = True
                    self.scrollbar_handle_color = self.scrollbar_handle_color_active
                else:
                    # Touch-drag scroll start in the message area
                    content_rect = pygame.Rect(
                        settings.MSG_TEXT_BOX_X, settings.MSG_TEXT_BOX_Y,
                        settings.MSG_TEXT_BOX_WIDTH, settings.MSG_TEXT_BOX_HEIGHT)
                    if content_rect.collidepoint(event.pos):
                        self._touch_scrolling = True
                        self._touch_last_y = event.pos[1]
                        self._touch_accum = 0.0

            elif event.type == MOUSEMOTION:
                if self.dragging:
                    self.handle_scrollbar_drag(event)
                elif self._touch_scrolling:
                    dy = event.pos[1] - self._touch_last_y
                    self._touch_last_y = event.pos[1]
                    line_h = self.font.get_height() + settings.MSG_BUBBLE_SPACING + settings.MSG_BUBBLE_PAD_Y
                    self._touch_accum -= dy
                    lines_delta = int(self._touch_accum / line_h)
                    if lines_delta != 0:
                        self._touch_accum -= lines_delta * line_h
                        max_scroll = self.calculate_max_scroll()
                        self.scroll_offset = max(0, min(self.scroll_offset + lines_delta, max_scroll))

            if event.type == MOUSEWHEEL:
                max_scroll = self.calculate_max_scroll()
                self.scroll_offset = max(0, min(self.scroll_offset - event.y * self.scroll_step, max_scroll))

            elif event.type == KEYDOWN and event.key == K_RETURN and self.chat_input.content.strip():
                self.handle_send_message(self.chat_input.content.strip())
                self.chat_input.empty()

    def draw_scrollbar(self):
        """Draw the scrollbar with rounded track and handle."""
        self.update_scrollbar_handle()
        if self.handle_rect.height > 0:
            _r = self._scrollbar_r
            # Track
            track_surf = pygame.Surface((self.scrollbar_rect.w, self.scrollbar_rect.h), pygame.SRCALPHA)
            pygame.draw.rect(track_surf, settings.SCROLLBAR_COLOR,
                             track_surf.get_rect(), border_radius=_r)
            self.window.blit(track_surf, self.scrollbar_rect.topleft)
            # Handle
            handle_surf = pygame.Surface((self.handle_rect.w, self.handle_rect.h), pygame.SRCALPHA)
            pygame.draw.rect(handle_surf, self.scrollbar_handle_color,
                             handle_surf.get_rect(), border_radius=_r)
            self.window.blit(handle_surf, self.handle_rect.topleft)


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