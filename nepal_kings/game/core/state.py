# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
import pygame
from config import settings
from utils import http_compat as _http

class State:
    def __init__(self):
        self.user_dict = None
        self.screen = "login"
        self.subscreen = "field"
        self.message_lines = []

        self.game = None # Game()
        self.action = None
        #self.user_response = None
        
        # Track pending spell cast that requires target selection
        self.pending_spell_cast = None  # Dict: {'spell': Spell, 'real_cards': List[Card]}

        # ── Badge tracking (unread indicators) ──────────────────────
        self._known_game_ids = None        # None = not yet initialised
        self._known_challenge_ids = None   # None = not yet initialised
        self.badge_new_games = 0           # count of unseen games
        self.badge_new_challenges = 0      # count of unseen received challenges
        self._new_game_ids = set()         # IDs of games that are "new" (for NEW tag)
        self._new_challenge_ids = set()    # IDs of challenges that are "new"
        self._last_seen_at = None          # ISO datetime str of previous session end

        # ── Accepted-challenge notification tracking ────────────────
        self._notified_accepted_challenges = set()  # challenge IDs already shown to user
        self._pending_accepted_challenge = None     # dict: {id, game_id, opponent_name, stake, ...} waiting for dialogue

        # ── Display info (set by launcher before window creation) ───
        self.native_screen_w = 0           # real desktop width
        self.native_screen_h = 0           # real desktop height


    def set_msg(self, msg):
        lines = msg.split('\n')  # Split the message into lines
        current_time = pygame.time.get_ticks()  # Record the current time

        for line in lines:
            self.message_lines.append((line, current_time))  # Store the line and its disappearance time

    def update(self):
        # Check for expired auth session → redirect to login
        if _http.is_session_expired() and self.screen != 'login':
            _http.clear_session_expired()
            self.user_dict = None
            self.game = None
            self.screen = 'login'
            self.set_msg('Session expired, please log in again')

        if self.message_lines:
            current_time = pygame.time.get_ticks()  # Record the current time

            # Create a new list for updated message lines
            updated_message_lines = []

            for line, line_time in self.message_lines:
                if line_time is not None:
                    # Check if the disappearance time has not passed
                    if current_time - line_time <= settings.MESSAGE_DURATION:
                        updated_message_lines.append((line, line_time))

            self.message_lines = updated_message_lines