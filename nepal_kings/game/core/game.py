# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
from utils import http_compat as requests
import threading
from config import settings
from game.components.cards.card import Card
from utils.msg_service import fetch_log_entries, add_log_entry, fetch_chat_messages, send_chat_message
from utils.figure_service import fetch_figures
from game.components.figures.figure import Figure, FigureFamily
from typing import List, Dict

class Game:
    def __init__(self, game_dict, user_dict, lightweight=False):
        self.game_id = game_dict['id']
        self.state = game_dict['state']
        self.date = game_dict['date']
        self.stake = game_dict.get('stake', 45)
        self.turn_time_limit = game_dict.get('turn_time_limit')  # Seconds per turn (None = no limit)
        self.winner_player_id = game_dict.get('winner_player_id')
        self.finished_at = game_dict.get('finished_at')
        self.players = game_dict.get('players', [])
        self.main_cards = game_dict.get('main_cards', [])
        self.side_cards = game_dict.get('side_cards', [])
        self.current_round = game_dict.get('current_round', 1)
        self.invader_player_id = game_dict.get('invader_player_id')
        self.turn_player_id = game_dict.get('turn_player_id')
        
        # Ceasefire tracking
        self.ceasefire_active = game_dict.get('ceasefire_active', False)
        self.ceasefire_start_turn = game_dict.get('ceasefire_start_turn')

        # Spell-related state
        self.pending_spell_id = game_dict.get('pending_spell_id')
        self.battle_modifier = game_dict.get('battle_modifier')
        self.waiting_for_counter_player_id = game_dict.get('waiting_for_counter_player_id')
        self.pending_spell = None  # Will be loaded if needed
        self.waiting_for_counter = False
        self.active_spell_effects = []  # Will be loaded separately
        self.cached_active_spells = []  # Populated by background poller
        self.cached_figures_data = {}   # {player_id: [figure_dicts]} populated by background poller
        self._figures_data_version = 0  # Bumped when cached_figures_data changes
        self._game_data_version = 0     # Bumped when game dict (cards, state, etc.) changes

        self.player_id = None
        self.opponent_name = None
        self.current_player = None
        self.opponent_player = None
        self.opponent_online = False

        user_id = user_dict.get('id')

        # Determine current and opponent players
        for player_dict in self.players:
            if player_dict['user_id'] == user_id:
                self.player_id = player_dict['id']
                self.current_player = player_dict
            else:
                self.opponent_name = player_dict['username']
                self.opponent_player = player_dict
                self.opponent_online = player_dict.get('is_online', False)

        # Whether it is this player's turn
        # Initialize to False so first update() can detect if it's their turn
        self.turn = False
        self.invader = True if self.invader_player_id == self.player_id else False

        # Track previous turn to detect turn changes
        # Initialize to None so first login triggers turn detection if it's their turn
        self.previous_turn_player_id = None
        
        # Track if game start notification was shown (needs to be shown once per player)
        self.game_start_notification_checked = False
        
        # Auto-fill notification (cleared after showing dialogue)
        self.pending_auto_fill = None
        
        # Opponent turn summary notification (cleared after showing dialogue)
        self.pending_opponent_turn_summary = None
        
        # Ceasefire ended notification (cleared after showing dialogue)
        self.pending_ceasefire_ended = False
        
        # Track previous ceasefire state to detect changes
        self.previous_ceasefire_active = self.ceasefire_active
        
        # Infinite Hammer mode tracking
        self.infinite_hammer_active = False
        self.infinite_hammer_dialogue_shown = False

        # Advance/battle state tracking
        self.advancing_figure_id = game_dict.get('advancing_figure_id')
        self.advancing_figure_id_2 = game_dict.get('advancing_figure_id_2')
        self.advancing_player_id = game_dict.get('advancing_player_id')
        self.defending_figure_id = game_dict.get('defending_figure_id')
        self.defending_figure_id_2 = game_dict.get('defending_figure_id_2')
        self.pending_advance_notification = False  # True when opponent advance detected
        self.pending_forced_advance = False  # True when invader must advance (0 turns)
        self.forced_advance_dialogue_shown = False  # Track if forced advance dialogue was shown
        self.pending_defender_selection = False  # True when advancing player must pick opponent's defender
        self.defender_selection_dialogue_shown = False  # Track if defender selection dialogue was shown
        self.pending_own_advance_notification = False  # True when advancing player should see own advance notification
        self.own_advance_figure_name = None  # Name of the figure that the player advanced
        self.pending_waiting_for_defender_pick = False  # True when defender is waiting for opponent to pick their battle figure
        self.waiting_for_defender_pick_shown = False  # Track if notification was shown
        self.pending_battle_ready = False  # True when both advancing and defending figures are set
        self.battle_ready_shown = False  # Track if battle-ready notification was shown
        self.pending_battle_ready = False  # True when both advancing and defending figures are set
        self.battle_ready_shown = False  # Track if battle ready notification was shown

        # Civil War second figure selection tracking
        self.civil_war_awaiting_second = False  # True when waiting for second advance figure
        self.civil_war_defender_second = False  # True when waiting for second defender figure
        self.civil_war_required_color = None  # 'offensive' or 'defensive' — required color for second pick

        # Battle decision tracking (fold/battle)
        self.battle_decisions = game_dict.get('battle_decisions')
        self.battle_confirmed = game_dict.get('battle_confirmed', False)
        self.fold_outcome = game_dict.get('fold_outcome')
        self.fold_winner_id = game_dict.get('fold_winner_id')
        self.auto_loss_reason = game_dict.get('auto_loss_reason')
        self.auto_loss_detail = game_dict.get('auto_loss_detail')
        self.resting_figure_ids = game_dict.get('resting_figure_ids', [])
        self.waiting_for_battle_decision = False  # True when waiting for opponent's decision
        self.pending_fold_result = False  # True when fold outcome detected from polling
        self.fold_result_shown = False  # Track if fold result notification was shown
        self.auto_proceed_to_battle = False  # True when both chose battle (detected via polling)

        # Battle moves phase tracking
        self.battle_moves_confirmed = game_dict.get('battle_moves_confirmed')  # {player_id: True}
        self.battle_moves_phase = False  # True when player is in mandatory battle moves selection
        self.battle_moves_ready = False  # True when this player has confirmed their moves
        self.waiting_for_opponent_battle_moves = False  # True when waiting for opponent to confirm
        self.both_battle_moves_ready = False  # True when both confirmed (proceed to battle)

        # Battle phase (active 3-round battle) tracking — client-side only
        self.in_battle_phase = False       # True while the 3-round battle is active
        self.battle_turns_left = 0         # Player's remaining battle turns (starts at 3)

        # Server-authoritative battle round tracking
        self.battle_round = game_dict.get('battle_round', 0)  # current battle round (0-2)
        self.battle_turn_player_id = game_dict.get('battle_turn_player_id')  # whose turn in battle

        # Suppress next turn notification after battle/fold (result dialogue already shown)
        self.suppress_next_turn_summary = False

        # Game-over tracking
        self.game_over = (self.state == 'finished')
        self.pending_game_over = None  # Will be set to game_over dict when detected
        self.game_over_shown = False  # Track if game-over dialogue was shown

        # Battle reconnect flag — True until the client has checked for active battle on first poll
        self.battle_reconnect_pending = True

        # Post-battle side card draw notification
        self.pending_post_battle_side_cards = None  # [{suit, rank}, ...] for current player
        self._post_battle_side_cards_round = 0  # Round for which notification was already shown

        # Loot notification for battle loser (which card the winner kept)
        self.pending_loot_notification = None  # dict with suit/rank/card_type/winner_name
        self._loot_notification_round = 0  # Round for which loot notification was already shown

        # Initialize log entries and chat messages
        self.log_entries = []
        self.chat_messages = []

        if not lightweight:
            # Fetch initial data for logs and chats
            self.update_logs()
            self.update_chats()

            # Pre-load figures so the first render isn't empty
            for player in self.players:
                pid = player['id']
                try:
                    self.cached_figures_data[pid] = fetch_figures(pid)
                except Exception:
                    self.cached_figures_data[pid] = []
            self._figures_data_version += 1

            # Pre-load active spells
            try:
                from utils import spell_service
                self.cached_active_spells = spell_service.fetch_active_spells(self.game_id)
            except Exception:
                pass

    # ── Network fetch (thread-safe, no mutations) ──────────────

    @staticmethod
    def fetch_server_data(game_id):
        """Fetch game state + logs + chats from the server.

        This method is safe to call from a background thread because it
        does not mutate any Game instance — it only returns raw dicts.
        Returns ``None`` on failure.
        """
        try:
            resp = requests.get(
                f'{settings.SERVER_URL}/games/get_game',
                params={'game_id': game_id},
                timeout=10,
            )
            if resp.status_code != 200:
                print("Failed to fetch game")
                return None

            game_dict = resp.json().get('game')
            if not game_dict:
                print("Game data not found in response")
                return None

            logs = []
            chats = []
            active_spells = []
            figures_by_player = {}
            try:
                logs = fetch_log_entries(game_id)
            except Exception as e:
                print(f"BG: Failed to fetch log entries: {e}")
            try:
                chats = fetch_chat_messages(game_id)
            except Exception as e:
                print(f"BG: Failed to fetch chat messages: {e}")
            try:
                from utils import spell_service
                active_spells = spell_service.fetch_active_spells(game_id)
            except Exception as e:
                print(f"BG: Failed to fetch active spells: {e}")
            # Fetch figures for all players in the game
            for player in game_dict.get('players', []):
                pid = player['id']
                try:
                    figures_by_player[pid] = fetch_figures(pid)
                except Exception as e:
                    print(f"BG: Failed to fetch figures for player {pid}: {e}")
                    figures_by_player[pid] = []

            return {
                'game': game_dict,
                'logs': logs,
                'chats': chats,
                'active_spells': active_spells,
                'figures': figures_by_player,
            }
        except Exception as e:
            print(f"BG fetch error: {e}")
            return None

    # ── Apply fetched data (main thread only) ──────────────────

    def apply_server_data(self, server_data):
        """Apply pre-fetched server data to this Game instance.

        *server_data* is the dict returned by ``fetch_server_data``.
        """
        if server_data is None:
            return
        game_dict = server_data['game']
        self._apply_game_dict(game_dict)
        self.log_entries = server_data.get('logs', self.log_entries)
        self.chat_messages = server_data.get('chats', self.chat_messages)
        self.cached_active_spells = server_data.get('active_spells', self.cached_active_spells)
        new_figures = server_data.get('figures', self.cached_figures_data)
        if new_figures is not self.cached_figures_data:
            self.cached_figures_data = new_figures
            self._figures_data_version += 1

    def update(self):
        """Update game state from the server (blocking / legacy path)."""
        data = self.fetch_server_data(self.game_id)
        if data:
            self.apply_server_data(data)

    def _apply_game_dict(self, game_dict):
        """Apply a game dict to this instance (main-thread only)."""
        self._game_data_version += 1
        self.game_id = game_dict['id']
        self.state = game_dict['state']
        self.date = game_dict['date']
        self.stake = game_dict.get('stake', 45)
        self.winner_player_id = game_dict.get('winner_player_id')
        self.finished_at = game_dict.get('finished_at')
        self.players = game_dict.get('players', [])
        self.main_cards = game_dict.get('main_cards', [])
        self.side_cards = game_dict.get('side_cards', [])
        self.current_round = game_dict.get('current_round', 1)
        self.invader_player_id = game_dict.get('invader_player_id')
        self.turn_player_id = game_dict.get('turn_player_id')

        # Detect game-over from server (opponent might have triggered it)
        if self.state == 'finished' and not self.game_over and not self.game_over_shown:
            self.game_over = True
            # Build game_over info from server state
            winner_player = None
            loser_player = None
            for p in self.players:
                if p['id'] == self.winner_player_id:
                    winner_player = p
                else:
                    loser_player = p
            if winner_player and loser_player:
                # Determine game-over reason from last_battle_result
                last_result = game_dict.get('last_battle_result', {}) or {}
                checkmate_figure_name = last_result.get('checkmate_figure_name')
                reason = 'checkmate' if checkmate_figure_name else 'stake'
                
                self.pending_game_over = {
                    'game_over': True,
                    'reason': reason,
                    'checkmate_figure_name': checkmate_figure_name,
                    'winner_player_id': winner_player['id'],
                    'loser_player_id': loser_player['id'],
                    'winner_username': winner_player.get('username', ''),
                    'loser_username': loser_player.get('username', ''),
                    'winner_score': winner_player.get('points', 0),
                    'loser_score': loser_player.get('points', 0),
                    'gold_awarded': self.stake * 2,
                    'stake': self.stake,
                }
                print(f"[GAME_OVER] Detected from polling: {self.pending_game_over}")
        
        # Update ceasefire tracking
        previous_ceasefire = self.ceasefire_active
        self.ceasefire_active = game_dict.get('ceasefire_active', False)
        self.ceasefire_start_turn = game_dict.get('ceasefire_start_turn')
        
        # Detect ceasefire ending (transition from active to inactive)
        if previous_ceasefire and not self.ceasefire_active:
            print(f"[CEASEFIRE] Detected ceasefire ended (was active, now inactive)")
            self.pending_ceasefire_ended = True

        # Update spell-related state
        previous_pending_spell_id = self.pending_spell_id
        self.pending_spell_id = game_dict.get('pending_spell_id')
        self.battle_modifier = game_dict.get('battle_modifier')
        self.waiting_for_counter_player_id = game_dict.get('waiting_for_counter_player_id')
        
        # Check if we're waiting for this player to counter
        if self.pending_spell_id and self.waiting_for_counter_player_id:
            self.waiting_for_counter = (self.waiting_for_counter_player_id == self.player_id)
        else:
            self.waiting_for_counter = False
            self.pending_spell = None

        # Update advance/battle state
        previous_advancing = self.advancing_figure_id
        self.advancing_figure_id = game_dict.get('advancing_figure_id')
        self.advancing_figure_id_2 = game_dict.get('advancing_figure_id_2')
        self.advancing_player_id = game_dict.get('advancing_player_id')
        self.defending_figure_id = game_dict.get('defending_figure_id')
        self.defending_figure_id_2 = game_dict.get('defending_figure_id_2')
        
        # Clear forced advance once an advance is underway
        if self.pending_forced_advance and self.advancing_figure_id:
            self.pending_forced_advance = False
        
        # Detect opponent advance (new advance appeared and it's not ours)
        # Use turn value from game_dict directly (self.turn is stale at this point)
        is_now_our_turn = (game_dict.get('turn_player_id') == self.player_id)
        if (self.advancing_figure_id and not previous_advancing and 
            self.advancing_player_id != self.player_id and is_now_our_turn):
            self.pending_advance_notification = True
            # Advance notification replaces the normal opponent turn summary
            self.pending_opponent_turn_summary = None
        # Civil War fallback: advance was detected on an earlier poll when it
        # wasn't our turn (invader was picking second figure).  Now the turn
        # just came to us — fire the advance notification we missed.
        elif (self.advancing_figure_id and previous_advancing and
              self.advancing_player_id != self.player_id and
              is_now_our_turn and
              self.previous_turn_player_id != self.player_id and
              not self.pending_advance_notification and
              not self.defending_figure_id):
            self.pending_advance_notification = True
            self.pending_opponent_turn_summary = None
        
        # Skip advance/defender detection while battle is confirmed or in progress
        # (prevents stale flags from re-triggering after battle resolution)
        battle_active = game_dict.get('battle_confirmed', False) or self.in_battle_phase

        # Check for Civil War modifier (needed for defender-pick guard below)
        modifiers = self.battle_modifier if isinstance(self.battle_modifier, list) else []
        has_civil_war = any(m.get('type') == 'Civil War' for m in modifiers)

        # Detect: advancing player's turn returned without defender selected
        # This means opponent spent their turn, now advancer must pick a defender
        # Skip if Civil War second figure selection is pending (turn stays with invader)
        # Use is_now_our_turn (fresh from game_dict) instead of self.turn (stale)
        # to avoid false positives right after build+advance with instant charge.
        if (not battle_active and
            self.advancing_figure_id and 
            self.advancing_player_id == self.player_id and 
            not self.defending_figure_id and 
            is_now_our_turn and not self.pending_defender_selection and
            not self.defender_selection_dialogue_shown and
            not self.civil_war_awaiting_second):
            self.pending_defender_selection = True

        # Detect: defender's turn ended without counter-advance
        # Opponent (advancing player) is now picking a defender from our figures.
        # In Civil War, the invader's first advance keeps the turn with the
        # invader (for second figure pick). Guard against premature detection
        # by checking the defender's turns_left: if > 0, the defender hasn't
        # had their turn yet (server set turns_left=1 on advance).
        my_turns_left = next(
            (p.get('turns_left', 0) for p in self.players
             if p['id'] == self.player_id), 0)
        if (not battle_active and
            self.advancing_figure_id and
            self.advancing_player_id != self.player_id and
            not self.defending_figure_id and
            not is_now_our_turn and
            not self.pending_waiting_for_defender_pick and
            not self.waiting_for_defender_pick_shown and
            not (has_civil_war and my_turns_left > 0)):
            self.pending_waiting_for_defender_pick = True
        
        # Battle is ready when both sides have their figures set
        battle_ready = (not battle_active and
                       self.advancing_figure_id and self.defending_figure_id and
                       not self.pending_battle_ready and not self.battle_ready_shown)
        
        # During Civil War, suppress premature battle_ready while a player
        # is still picking their second figure.  The server keeps the turn
        # with the picking player until they finish or skip, then flips it.
        # So battle is only truly ready once the turn reaches the invader
        # (advancing player), who decides fight/fold first.
        if battle_ready and has_civil_war:
            # Also suppress while our own client-side second-pick flags are set
            if (self.civil_war_awaiting_second or self.civil_war_defender_second):
                battle_ready = False
            # For the invader polling: if turn hasn't come back yet, defender
            # is still picking
            elif (self.advancing_player_id == self.player_id and
                  not is_now_our_turn):
                battle_ready = False
        
        if battle_ready:
            self.pending_battle_ready = True
            print(f"[BATTLE_READY] Figures set: advancing={self.advancing_figure_id}/{self.advancing_figure_id_2}, defending={self.defending_figure_id}/{self.defending_figure_id_2}")

        # Detect fold outcome from opponent's battle decision (polling detection)
        previous_fold_outcome = self.fold_outcome
        previous_battle_confirmed = self.battle_confirmed
        self.battle_decisions = game_dict.get('battle_decisions')
        self.battle_confirmed = game_dict.get('battle_confirmed', False)
        self.fold_outcome = game_dict.get('fold_outcome')
        self.fold_winner_id = game_dict.get('fold_winner_id')
        self.auto_loss_reason = game_dict.get('auto_loss_reason')
        self.auto_loss_detail = game_dict.get('auto_loss_detail')
        self.resting_figure_ids = game_dict.get('resting_figure_ids', [])

        # Update server-authoritative battle round tracking
        self.battle_round = game_dict.get('battle_round', 0)
        self.battle_turn_player_id = game_dict.get('battle_turn_player_id')

        # Reset fold tracking when server clears fold state (new round started)
        if previous_fold_outcome and not self.fold_outcome:
            self.fold_result_shown = False
            self.pending_fold_result = False

        # Detect new fold outcome (transition from None to set)
        if self.fold_outcome and not previous_fold_outcome and not self.fold_result_shown:
            self.pending_fold_result = True
            self.waiting_for_battle_decision = False
            print(f"[FOLD] Detected fold outcome: {self.fold_outcome}, winner: {self.fold_winner_id}")

        # Detect both chose battle (transition from False to True)
        if self.battle_confirmed and not previous_battle_confirmed and self.waiting_for_battle_decision:
            self.auto_proceed_to_battle = True
            self.waiting_for_battle_decision = False
            print(f"[BATTLE_DECISION] Both players chose battle — auto-proceeding")

        # Detect opponent confirmed battle moves while we are waiting
        previous_bm_confirmed = self.battle_moves_confirmed
        self.battle_moves_confirmed = game_dict.get('battle_moves_confirmed')
        if (self.waiting_for_opponent_battle_moves and
                self.battle_moves_confirmed and
                len(self.battle_moves_confirmed) >= 2):
            self.both_battle_moves_ready = True
            self.waiting_for_opponent_battle_moves = False
            print(f"[BATTLE_MOVES] Both players confirmed battle moves — proceed to battle")

        # Reinitialize current and opponent players
        for player_dict in self.players:
            if player_dict['id'] == self.player_id:
                self.current_player = player_dict
            else:
                self.opponent_name = player_dict['username']
                self.opponent_player = player_dict

        # Update turn and invader status
        previous_turn = self.turn
        self.turn = True if self.turn_player_id == self.player_id else False
        self.invader = True if self.invader_player_id == self.player_id else False

        # Check for game start notification on first update (regardless of turn number)
        if not self.game_start_notification_checked:
            print(f"[GAME_START] First update - player_id={self.player_id}, turn={self.turn}, invader={self.invader}")
            print(f"[GAME_START] Checking for welcome message...")
            self._start_turn_async()
            self.game_start_notification_checked = True
            print(f"[GAME_START] Flag set to True after first check")
        
        # Check if turn changed to current player - call start_turn endpoint
        elif not previous_turn and self.turn and self.previous_turn_player_id != self.turn_player_id:
            print(f"[TURN CHANGE] Detected turn change to current player. Calling start_turn...")
            self._start_turn_async()
        
        # Detect spell resolution: if our spell was pending and just resolved,
        # and it's still our turn (e.g., Invader Swap keeps turn with caster),
        # trigger _handle_start_turn for auto-fill since turn-change detection missed it
        elif previous_pending_spell_id and not self.pending_spell_id and self.turn and previous_turn:
            print(f"[SPELL_RESOLVED] Spell resolved while turn stayed with us. Calling start_turn for auto-fill...")
            self._start_turn_async()
        
        # Update previous turn player for next check
        self.previous_turn_player_id = self.turn_player_id

        # Detect post-battle side card draw
        post_battle = game_dict.get('post_battle_drawn_cards')
        if (post_battle and self.player_id and
                str(self.player_id) in post_battle and
                self.current_round != self._post_battle_side_cards_round):
            my_cards = post_battle[str(self.player_id)]
            if my_cards:
                self.pending_post_battle_side_cards = my_cards
                self._post_battle_side_cards_round = self.current_round
                print(f"[POST_BATTLE] Drew side cards for new round {self.current_round}: {my_cards}")

        # Detect loot notification for battle loser (which card the winner kept)
        last_result = game_dict.get('last_battle_result') or {}
        picked_card = last_result.get('picked_card')
        if (picked_card and self.player_id and
                last_result.get('loser_player_id') == self.player_id and
                self.current_round != self._loot_notification_round):
            self.pending_loot_notification = {
                'suit': picked_card['suit'],
                'rank': picked_card['rank'],
                'card_type': picked_card['card_type'],
                'winner_name': last_result.get('winner_name', 'Opponent'),
            }
            self._loot_notification_round = self.current_round
            print(f"[LOOT] Opponent kept card: {picked_card}")


    def update_from_dict(self, game_dict):
        """Update game state directly from a dictionary (e.g., from spell service response)."""
        self._game_data_version += 1
        # Update game data
        self.game_id = game_dict['id']
        self.state = game_dict['state']
        self.date = game_dict['date']
        self.players = game_dict.get('players', [])
        self.main_cards = game_dict.get('main_cards', [])
        self.side_cards = game_dict.get('side_cards', [])
        self.current_round = game_dict.get('current_round', 1)
        self.invader_player_id = game_dict.get('invader_player_id')
        self.turn_player_id = game_dict.get('turn_player_id')
        
        # Update ceasefire tracking
        previous_ceasefire = self.ceasefire_active
        self.ceasefire_active = game_dict.get('ceasefire_active', False)
        self.ceasefire_start_turn = game_dict.get('ceasefire_start_turn')
        
        # Detect ceasefire ending (transition from active to inactive)
        if previous_ceasefire and not self.ceasefire_active:
            print(f"[CEASEFIRE] Detected ceasefire ended (was active, now inactive)")
            self.pending_ceasefire_ended = True

        # Update spell-related state
        self.pending_spell_id = game_dict.get('pending_spell_id')
        self.battle_modifier = game_dict.get('battle_modifier')
        self.waiting_for_counter_player_id = game_dict.get('waiting_for_counter_player_id')
        
        # Update advance/battle state
        self.advancing_figure_id = game_dict.get('advancing_figure_id')
        self.advancing_figure_id_2 = game_dict.get('advancing_figure_id_2')
        self.advancing_player_id = game_dict.get('advancing_player_id')
        self.defending_figure_id = game_dict.get('defending_figure_id')
        self.defending_figure_id_2 = game_dict.get('defending_figure_id_2')
        
        # Clear forced advance once an advance is underway
        if self.pending_forced_advance and self.advancing_figure_id:
            self.pending_forced_advance = False
        
        # Update battle decision/fold state
        self.battle_decisions = game_dict.get('battle_decisions')
        self.battle_confirmed = game_dict.get('battle_confirmed', False)
        self.battle_moves_confirmed = game_dict.get('battle_moves_confirmed')
        self.fold_outcome = game_dict.get('fold_outcome')
        self.fold_winner_id = game_dict.get('fold_winner_id')
        
        # Update battle round tracking
        self.battle_round = game_dict.get('battle_round', 0)
        self.battle_turn_player_id = game_dict.get('battle_turn_player_id')
        
        # Check if we're waiting for this player to counter
        if self.pending_spell_id and self.waiting_for_counter_player_id:
            self.waiting_for_counter = (self.waiting_for_counter_player_id == self.player_id)
        else:
            self.waiting_for_counter = False
            self.pending_spell = None

        # Reinitialize current and opponent players
        for player_dict in self.players:
            if player_dict['id'] == self.player_id:
                self.current_player = player_dict
            else:
                self.opponent_name = player_dict['username']
                self.opponent_player = player_dict

        # Update turn and invader status
        previous_turn = self.turn
        self.turn = True if self.turn_player_id == self.player_id else False
        self.invader = True if self.invader_player_id == self.player_id else False
        
        # Update previous turn player for next check
        self.previous_turn_player_id = self.turn_player_id

        # Detect post-battle side card draw
        post_battle = game_dict.get('post_battle_drawn_cards')
        if (post_battle and self.player_id and
                str(self.player_id) in post_battle and
                self.current_round != self._post_battle_side_cards_round):
            my_cards = post_battle[str(self.player_id)]
            if my_cards:
                self.pending_post_battle_side_cards = my_cards
                self._post_battle_side_cards_round = self.current_round
                print(f"[POST_BATTLE] Drew side cards for new round {self.current_round}: {my_cards}")

        # Note: logs and chats are fetched by the background poller
        # No need to block here — the next poll cycle will pick them up

    def _start_turn_async(self):
        """Fire _handle_start_turn in a background thread."""
        try:
            t = threading.Thread(target=self._handle_start_turn, daemon=True)
            t.start()
        except RuntimeError:
            self._handle_start_turn()  # web fallback: run synchronously

    def _handle_start_turn(self):
        """Called when turn changes to current player. Checks and handles auto-fill."""
        try:
            payload = {
                'game_id': self.game_id,
                'player_id': self.player_id
            }
            print(f"[START_TURN] Sending payload: game_id={self.game_id} (type={type(self.game_id)}), player_id={self.player_id} (type={type(self.player_id)})")
            
            response = requests.post(
                f'{settings.SERVER_URL}/games/start_turn',
                json=payload,
                timeout=10
            )
            
            if response.status_code != 200:
                print(f"[START_TURN] Failed with status {response.status_code}: {response.json()}")
                return
            
            data = response.json()
            print(f"[START_TURN] Response: {data}")
            if data.get('success'):
                auto_fill = data.get('auto_fill')
                if auto_fill:
                    # Store for dialogue display
                    print(f"[START_TURN] Auto-fill needed: {auto_fill}")
                    self.pending_auto_fill = auto_fill
                else:
                    print(f"[START_TURN] No auto-fill needed")
                
                # Store opponent turn summary for dialogue display
                # But suppress it if an advance notification is pending (advance has its own notification)
                # Also suppress after battle/fold resolution (result dialogue already shown)
                # Exception: never suppress notifications that directly affect the player
                # (e.g. Forced Deal card swap, Dump Cards, Poison on player's figure, Explosion)
                opponent_turn_summary = data.get('opponent_turn_summary')
                action_data = opponent_turn_summary.get('action', {}) if opponent_turn_summary and isinstance(opponent_turn_summary.get('action'), dict) else {}
                affects_player = action_data.get('affects_player', False)
                
                if affects_player and opponent_turn_summary:
                    # Always show notifications that directly affect the player's state
                    print(f"[START_TURN] Opponent turn summary affects player — showing regardless of other state")
                    self.pending_opponent_turn_summary = opponent_turn_summary
                elif self.suppress_next_turn_summary:
                    self.suppress_next_turn_summary = False
                    # Only suppress if opponent hasn't taken a real action in the
                    # new round (action is a dict for real moves, string for 'unknown').
                    # After a lost battle the first start_turn carries the opponent's
                    # actual build/spell/card-change — that must NOT be discarded.
                    if opponent_turn_summary and isinstance(opponent_turn_summary.get('action'), dict):
                        print(f"[START_TURN] Suppress flag set but opponent took real action — showing notification")
                        self.pending_opponent_turn_summary = opponent_turn_summary
                    else:
                        print(f"[START_TURN] Suppressing opponent turn summary — post-battle/fold (no real action)")
                        self.pending_opponent_turn_summary = None
                elif (self.pending_advance_notification or
                      (self.advancing_figure_id and
                       self.advancing_player_id != self.player_id)):
                    print(f"[START_TURN] Suppressing opponent turn summary — advance notification pending or opponent advance active")
                elif self.pending_battle_ready:
                    print(f"[START_TURN] Suppressing opponent turn summary — battle ready pending")
                elif self.pending_fold_result:
                    print(f"[START_TURN] Suppressing opponent turn summary — fold result pending")
                elif opponent_turn_summary:
                    print(f"[START_TURN] Opponent turn summary received - action: {opponent_turn_summary.get('action')}")
                    self.pending_opponent_turn_summary = opponent_turn_summary
                else:
                    print(f"[START_TURN] No opponent turn summary")
                    self.pending_opponent_turn_summary = None
        except Exception as e:
            print(f"Error in start_turn: {str(e)}")

    def get_player_username(self, player_id):
        """Fetch the username of a player given their player_id."""
        for player in self.players:
            if player['id'] == player_id:
                return player['username']
        return "Unknown"

    def get_hand(self, is_opponent=False):
        """
        Retrieve the main and side hand of the player or their opponent, excluding cards that are part of a figure.
        """
        player_id = self.opponent_player['id'] if is_opponent else self.player_id

        # Main hand
        main_hand = [
            Card(
                rank=c['rank'],
                suit=c['suit'],
                value=c['value'],
                id=c.get('id'),
                game_id=c.get('game_id'),
                player_id=c.get('player_id'),
                in_deck=c.get('in_deck', True),
                deck_position=c.get('deck_position'),
                part_of_figure=c.get('part_of_figure', False),
                part_of_battle_move=c.get('part_of_battle_move', False),
                type=c.get('type')  # Include the card type
            )
            for c in self.main_cards
            if c['player_id'] == player_id and not c.get('part_of_figure', False) and not c.get('in_deck', False)
        ]

        # Side hand
        side_hand = [
            Card(
                rank=c['rank'],
                suit=c['suit'],
                value=c['value'],
                id=c.get('id'),
                game_id=c.get('game_id'),
                player_id=c.get('player_id'),
                in_deck=c.get('in_deck', True),
                deck_position=c.get('deck_position'),
                part_of_figure=c.get('part_of_figure', False),
                part_of_battle_move=c.get('part_of_battle_move', False),
                type=c.get('type')  # Include the card type
            )
            for c in self.side_cards
            if c['player_id'] == player_id and not c.get('part_of_figure', False) and not c.get('in_deck', False)
        ]

        return main_hand, side_hand


    def get_figures(self, families: Dict[str, FigureFamily], is_opponent=False) -> List[Figure]:
        """
        Get figures for the current or opponent player from cached data.
        Figure data is fetched by the background poller and stored in cached_figures_data.

        :param families: A dictionary mapping family names to FigureFamily instances.
        :param is_opponent: If True, get opponent's figures.
        :return: A list of Figure instances.
        """
        try:
            player_id = self.opponent_player['id'] if is_opponent else self.player_id
            figures_data = self.cached_figures_data.get(player_id, [])
            figures = []


            for figure_data in figures_data:
                family_name = figure_data['family_name']
                if family_name not in families:
                    print(f"Skipping unknown family: {family_name}")
                    continue

                family = families[family_name]

                cards = self._load_cards_from_data(figure_data['cards'])


                if not any(cards.values()):
                    print(f"Skipping figure with no valid cards: {figure_data}")
                    continue

                # Safely retrieve number_card and upgrade_card
                number_card = cards.get('number')[0] if cards.get('number') else None
                upgrade_card = cards.get('upgrade')[0] if cards.get('upgrade') else None

                # If upgrade_card is not in the saved cards, try to get it from the family definition
                # Match this figure to the correct variant in the family to get upgrade_card and combat attributes
                key_cards = cards.get('key', [])
                matched_family_figure = None
                
                # Find matching figure in family definitions
                for family_figure in family.figures:
                    # Match by suit and cards
                    if (family_figure.suit == figure_data['suit'] and 
                        len(family_figure.key_cards) == len(key_cards)):
                        # Check if key cards match
                        key_cards_match = all(
                            any(kc.rank == fkc.rank and kc.suit == fkc.suit 
                                for fkc in family_figure.key_cards)
                            for kc in key_cards
                        )
                        # Check if number cards match (if present)
                        number_cards_match = True
                        if number_card and family_figure.number_card:
                            number_cards_match = (number_card.rank == family_figure.number_card.rank and
                                                number_card.suit == family_figure.number_card.suit)
                        elif number_card or family_figure.number_card:
                            number_cards_match = False
                        
                        if key_cards_match and number_cards_match:
                            matched_family_figure = family_figure
                            if not upgrade_card:
                                upgrade_card = family_figure.upgrade_card
                            break

                # Extract combat attributes from matched family figure
                cannot_attack = matched_family_figure.cannot_attack if matched_family_figure and hasattr(matched_family_figure, 'cannot_attack') else False
                must_be_attacked = matched_family_figure.must_be_attacked if matched_family_figure and hasattr(matched_family_figure, 'must_be_attacked') else False
                rest_after_attack = matched_family_figure.rest_after_attack if matched_family_figure and hasattr(matched_family_figure, 'rest_after_attack') else False
                distance_attack = matched_family_figure.distance_attack if matched_family_figure and hasattr(matched_family_figure, 'distance_attack') else False
                buffs_allies = matched_family_figure.buffs_allies if matched_family_figure and hasattr(matched_family_figure, 'buffs_allies') else False
                buffs_allies_defence = matched_family_figure.buffs_allies_defence if matched_family_figure and hasattr(matched_family_figure, 'buffs_allies_defence') else False
                blocks_bonus = matched_family_figure.blocks_bonus if matched_family_figure and hasattr(matched_family_figure, 'blocks_bonus') else False
                cannot_defend = matched_family_figure.cannot_defend if matched_family_figure and hasattr(matched_family_figure, 'cannot_defend') else False
                instant_charge = matched_family_figure.instant_charge if matched_family_figure and hasattr(matched_family_figure, 'instant_charge') else False
                cannot_be_blocked = matched_family_figure.cannot_be_blocked if matched_family_figure and hasattr(matched_family_figure, 'cannot_be_blocked') else False
                cannot_be_targeted = matched_family_figure.cannot_be_targeted if matched_family_figure and hasattr(matched_family_figure, 'cannot_be_targeted') else False
                checkmate = figure_data.get('checkmate', False) or (matched_family_figure.checkmate if matched_family_figure and hasattr(matched_family_figure, 'checkmate') else False)
                override_base_power = matched_family_figure.override_base_power if matched_family_figure and hasattr(matched_family_figure, 'override_base_power') else None

                figure = Figure(
                    name=figure_data['name'],
                    sub_name=figure_data.get('sub_name', ""),
                    suit=figure_data['suit'],
                    family=family,
                    key_cards=key_cards,
                    number_card=number_card,
                    upgrade_card=upgrade_card,
                    description=figure_data.get('description', ""),
                    upgrade_family_name=figure_data.get('upgrade_family_name'),
                    produces=figure_data.get('produces', {}),
                    requires=figure_data.get('requires', {}),
                    id=figure_data['id'],
                    player_id=figure_data.get('player_id'),
                    cannot_attack=cannot_attack,
                    must_be_attacked=must_be_attacked,
                    rest_after_attack=rest_after_attack,
                    distance_attack=distance_attack,
                    buffs_allies=buffs_allies,
                    buffs_allies_defence=buffs_allies_defence,
                    blocks_bonus=blocks_bonus,
                    cannot_defend=cannot_defend,
                    instant_charge=instant_charge,
                    cannot_be_blocked=cannot_be_blocked,
                    cannot_be_targeted=cannot_be_targeted,
                    checkmate=checkmate,
                    override_base_power=override_base_power,
                )
                figures.append(figure)

            # Load active enchantments for all figures
            self._load_enchantments_for_figures(figures)

            return figures
        except Exception as e:
            print(f"Error loading figures: {str(e)}")
            return []
    
    def _load_enchantments_for_figures(self, figures: List[Figure]):
        """
        Load active enchantment spells and apply them to figures.
        Uses cached active spells from background poller (no HTTP call).
        
        :param figures: List of Figure instances to apply enchantments to
        """
        try:
            active_spells = self.cached_active_spells

            # Filter enchantment spells and apply to figures
            for spell_data in active_spells:
                if spell_data.get('spell_type') == 'enchantment' and spell_data.get('target_figure_id'):
                    target_figure_id = spell_data['target_figure_id']
                    
                    # Find the matching figure
                    for figure in figures:
                        if figure.id == target_figure_id:
                            # Extract enchantment data
                            effect_data = spell_data.get('effect_data', {})
                            spell_icon = effect_data.get('spell_icon', 'default_spell_icon.png')
                            power_modifier = effect_data.get('power_modifier', 0)
                            spell_name = spell_data.get('spell_name', 'Unknown Spell')
                            
                            # Apply enchantment to figure
                            figure.add_enchantment(
                                spell_name=spell_name,
                                spell_icon=spell_icon,
                                power_modifier=power_modifier
                            )
                            break
        except Exception as e:
            import traceback
            traceback.print_exc()

    def has_active_all_seeing_eye(self) -> bool:
        """
        Check if current player has an active "All Seeing Eye" spell.
        Uses cached active spells from background poller (no HTTP call).
        
        :return: True if current player has active All Seeing Eye spell, False otherwise
        """
        if not self.player_id:
            return False
        for spell_data in self.cached_active_spells:
            if (spell_data.get('spell_type') == 'enchantment' and
                'All Seeing Eye' in spell_data.get('spell_name', '') and
                spell_data.get('player_id') == self.player_id):
                return True
        return False
    
    def check_infinite_hammer_active(self) -> bool:
        """
        Check if current player has an active "Infinite Hammer" spell.
        Uses cached active spells from background poller (no HTTP call).
        
        :return: True if current player has active Infinite Hammer spell, False otherwise
        """
        if not self.player_id:
            return False
        for spell_data in self.cached_active_spells:
            if (spell_data.get('spell_type') == 'enchantment' and
                'Infinite Hammer' in spell_data.get('spell_name', '') and
                spell_data.get('player_id') == self.player_id):
                return True
        return False

    def is_battle_active(self) -> bool:
        """Return True while a battle is actually in progress (confirmed → resolution).

        When active, players should not be able to change cards, build figures,
        manipulate figures (pickup/upgrade), or cast spells.  Screen navigation
        remains allowed.

        Note: the advance/defender-selection phase (advancing_figure_id set but
        battle not yet confirmed) is NOT considered battle-active — players must
        still be free to act during that phase.  However, once a player has
        chosen to fight and is waiting for the opponent's decision, actions are
        blocked.
        """
        return bool(
            self.battle_moves_phase
            or self.battle_confirmed
            or self.waiting_for_battle_decision
        )

    def has_opponent_cast_all_seeing_eye(self) -> bool:
        """
        Check if opponent has an active "All Seeing Eye" spell.
        Uses cached active spells from background poller (no HTTP call).
        
        :return: True if opponent has active All Seeing Eye spell, False otherwise
        """
        opponent_id = self.opponent_player.get('id') if self.opponent_player else None
        if not opponent_id:
            return False
        for spell_data in self.cached_active_spells:
            if (spell_data.get('spell_type') == 'enchantment' and
                'All Seeing Eye' in spell_data.get('spell_name', '') and
                spell_data.get('player_id') == opponent_id):
                return True
        return False

    def calculate_resources(self, families: Dict[str, FigureFamily], is_opponent: bool = False) -> Dict[str, Dict[str, int]]:
        """
        Calculate total resources produced and required by all player figures.

        Figures that have a resource deficit (they require a resource whose
        total demand exceeds total supply) do NOT contribute their production.
        The calculation is iterative: removing a deficit figure's production
        may cause other figures to fall into deficit, and so on until stable.
        
        :param families: A dictionary mapping family names to FigureFamily instances.
        :param is_opponent: If True, calculate for opponent's figures instead of current player's
        :return: A dictionary with 'produces' and 'requires' keys, each containing resource totals
        """
        figures = self.get_figures(families, is_opponent=is_opponent)
        
        if settings.DEBUG_ENABLED:
            with open(settings.DEBUG_LOG_PATH, 'a') as f:
                f.write(f"[CLIENT] Calculating resources for {len(figures)} figures\n")
                for figure in figures:
                    f.write(f"[CLIENT] Figure: {figure.name}, produces: {figure.produces}, requires: {figure.requires}\n")

        # Total requires is always the sum across ALL figures (never changes)
        total_requires = {}
        for figure in figures:
            if figure.requires:
                for resource_type, amount in figure.requires.items():
                    total_requires[resource_type] = total_requires.get(resource_type, 0) + amount

        # Iteratively exclude production from deficit figures until stable
        excluded = set()  # indices of figures whose production is excluded
        stable = False
        while not stable:
            stable = True
            total_produces = {}
            for i, figure in enumerate(figures):
                if i in excluded:
                    continue
                if figure.produces:
                    for resource_type, amount in figure.produces.items():
                        total_produces[resource_type] = total_produces.get(resource_type, 0) + amount

            # Check each non-excluded figure with requirements for deficit
            for i, figure in enumerate(figures):
                if i in excluded:
                    continue
                if not figure.requires:
                    continue
                for res_name in figure.requires:
                    if total_requires.get(res_name, 0) > total_produces.get(res_name, 0):
                        excluded.add(i)
                        stable = False
                        break
        
        if settings.DEBUG_ENABLED:
            with open(settings.DEBUG_LOG_PATH, 'a') as f:
                f.write(f"[CLIENT] Total produces: {total_produces}\n")
                f.write(f"[CLIENT] Total requires: {total_requires}\n")
                if excluded:
                    f.write(f"[CLIENT] Deficit figures excluded from production: "
                            f"{[figures[i].name for i in excluded]}\n")
        return {'produces': total_produces, 'requires': total_requires}

    @staticmethod
    def _load_cards_from_data(cards_data: List[Dict]) -> Dict[str, List[Card]]:
        """
        Convert card data from the database into Card instances grouped by role.

        :param cards_data: A list of card data dictionaries from the database.
        :return: A dictionary with card roles as keys and lists of Card instances as values.
        """
        cards = {'key': [], 'number': [], 'upgrade': []}

        for card_data in cards_data:
            try:
                card = Card(
                    rank=card_data['rank'],
                    suit=card_data['suit'],
                    value=card_data['value'],
                    id=card_data.get('card_id'),
                    game_id=card_data.get('game_id'),
                    player_id=card_data.get('player_id'),
                    in_deck=card_data.get('in_deck'),
                    deck_position=card_data.get('deck_position'),
                    part_of_figure=card_data.get('part_of_figure'),
                    type=card_data.get('card_type'),
                    role=card_data.get('role')
                )
                # Group cards by their role
                if card_data.get('role') in cards:
                    cards[card_data['role']].append(card)
            except KeyError as e:
                print(f"Skipping card with missing data: {card_data}, Error: {e}")
                continue

        return cards


    def update_logs(self):
        """Fetch and update log entries."""
        try:
            self.log_entries = fetch_log_entries(self.game_id)
        except Exception as e:
            print(f"Failed to fetch log entries: {str(e)}")

    def add_log_entry(self, round_number, turn_number, message, author, entry_type):
        """Add a log entry and update the log list."""
        try:
            add_log_entry(self.game_id, self.player_id, round_number, turn_number, message, author, entry_type)
            self.update_logs()
        except Exception as e:
            print(f"Failed to add log entry: {str(e)}")

    def update_chats(self):
        """Fetch and update chat messages."""
        try:
            self.chat_messages = fetch_chat_messages(self.game_id)
        except Exception as e:
            print(f"Failed to fetch chat messages: {str(e)}")

    def send_chat_message(self, receiver_id, message):
        """Send a chat message and update the chat list."""
        try:
            send_chat_message(self.game_id, self.player_id, receiver_id, message)
            self.update_chats()
        except Exception as e:
            print(f"Failed to send chat message: {str(e)}")


    def change_main_cards(self, cards):
        """Change the selected main cards and return the new cards."""
        return self._change_cards(cards, card_type="main")

    def change_side_cards(self, cards):
        """Change the selected side cards and return the new cards."""
        return self._change_cards(cards, card_type="side")
    
    def discard_main_cards(self, cards):
        """Discard the selected main cards (return to deck without drawing new ones)."""
        return self._discard_cards(cards, card_type="main")
    
    def discard_side_cards(self, cards):
        """Discard the selected side cards (return to deck without drawing new ones)."""
        return self._discard_cards(cards, card_type="side")

    def _change_cards(self, cards, card_type):
        """Helper function to change cards on the server and return the new cards."""
        try:
            response = requests.post(f'{settings.SERVER_URL}/games/change_cards', json={
                'game_id': self.game_id,
                'player_id': self.player_id,
                'card_type': card_type,
                'cards': [card.serialize() for card in cards]
            }, timeout=10)

            if response.status_code != 200:
                print(f"Failed to change {card_type} cards: {response.json().get('message', 'Unknown error')}")
                return []

            # Update the game state after a successful response
            new_cards = response.json().get('new_cards', [])

            self.update()

            return new_cards
        except Exception as e:
            print(f"An error occurred while changing {card_type} cards: {str(e)}")
            return []
    
    def _discard_cards(self, cards, card_type):
        """Helper function to discard cards on the server (return to deck without drawing)."""
        try:
            response = requests.post(f'{settings.SERVER_URL}/games/discard_cards', json={
                'game_id': self.game_id,
                'player_id': self.player_id,
                'card_type': card_type,
                'cards': [card.serialize() for card in cards]
            }, timeout=10)

            if response.status_code != 200:
                print(f"Failed to discard {card_type} cards: {response.json().get('message', 'Unknown error')}")
                return False

            # Log the card discard action
            round_number = self.current_round
            turn_number = self.current_player.get('turns_left', 0)
            message = f"{self.current_player.get('username', 'Player')} discarded {len(cards)} {card_type} card(s)."
            self.add_log_entry(round_number, turn_number, message, self.current_player.get('username', 'Player'), 'card_discard')

            self.update()

            return True
        except Exception as e:
            print(f"An error occurred while discarding {card_type} cards: {str(e)}")
            return False
