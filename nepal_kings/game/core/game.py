# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
from utils import http_compat as requests
import sys as _sys
import threading
import pygame
from config import settings
from game.components.cards.card import Card
from utils.msg_service import fetch_log_entries, add_log_entry, fetch_chat_messages, send_chat_message
from utils.figure_service import fetch_figures
from game.components.figures.figure import Figure, FigureFamily
from game.components.figures.skill_display_filters import filter_figure_for_display
from typing import List, Dict
import logging

logger = logging.getLogger('nk.core.game')


def battle_modifier_types(modifiers):
    """Return normalized modifier names from a serialized modifier payload."""
    if isinstance(modifiers, dict):
        modifiers = [modifiers]
    elif not isinstance(modifiers, (list, tuple)):
        return set()
    return {
        modifier.get('type') if isinstance(modifier, dict) else modifier
        for modifier in modifiers
        if modifier
    }


def battle_required_field(modifiers):
    """Return the effective battle field restriction for the client.

    Royal Decree deliberately overrides the village-only Peasant War and
    Civil War modifiers.  Keep this in sync with the server helper in
    ``server/game_service/figure_rule_helpers.py``.
    """
    modifier_types = battle_modifier_types(modifiers)
    if 'Royal Decree' in modifier_types:
        return 'castle'
    if modifier_types & {'Peasant War', 'Civil War'}:
        return 'village'
    return None


def civil_war_pick_flow_active(modifiers):
    """True only when Civil War controls the effective battle figure pool."""
    return (
        battle_required_field(modifiers) != 'castle'
        and 'Civil War' in battle_modifier_types(modifiers)
    )


class Game:
    def __init__(self, game_dict, user_dict, lightweight=False):
        self.game_id = game_dict['id']
        self.state = game_dict['state']
        self.mode = game_dict.get('mode', 'duel')  # 'duel' or 'conquer'
        # Conquer-only: 'battle_move' (legacy pre-bought BattleMove flow) vs
        # 'tactics_hand' (Phase 9 redesign: persistent tactics rail). Default
        # is 'battle_move' so duel/legacy games behave unchanged.
        self.conquer_move_model = game_dict.get('conquer_move_model', 'battle_move')
        self.land_id = game_dict.get('land_id')  # conquer mode only
        self.land_tier = game_dict.get('land_tier')  # conquer mode only (1..KINGDOM_TIER_COUNT)
        self.land_gold_rate = game_dict.get('land_gold_rate')  # conquer mode only
        self.land_suit_bonus_suit = game_dict.get('land_suit_bonus_suit')  # conquer mode only
        self.land_suit_bonus_value = game_dict.get('land_suit_bonus_value')  # conquer mode only
        self.date = game_dict['date']
        self.stake = game_dict.get('stake', 45)
        self.game_limit = game_dict.get('game_limit', self.stake)
        self.turn_time_limit = game_dict.get('turn_time_limit')  # Seconds per turn (None = no limit)
        self.winner_player_id = game_dict.get('winner_player_id')
        self.finished_at = game_dict.get('finished_at')
        self.last_battle_result = game_dict.get('last_battle_result') or {}
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

        for player_dict in self.players:
            if 'figures' in player_dict:
                self.cached_figures_data[player_dict['id']] = player_dict.get('figures') or []
        if self.cached_figures_data:
            self._figures_data_version += 1

        # Whether it is this player's turn
        # Initialize to False so first update() can detect if it's their turn
        self.turn = False
        self.invader = True if self.invader_player_id == self.player_id else False
        # Conquer battles are player-driven from the very first frame (the
        # invader must advance a figure) and their game-start notification is
        # fired explicitly on screen entry — not via first-poll turn-change
        # detection. Seed `turn` from the snapshot so the pre-battle UI
        # (forced-advance prompt, timeline attacker step) works even if the
        # first full poll is discarded or short-circuited; duel keeps the
        # False seed so its first-update turn detection still fires.
        if self.mode == 'conquer':
            self.turn = self.turn_player_id == self.player_id

        # Track previous turn to detect turn changes
        # Initialize to None so first login triggers turn detection if it's their turn
        self.previous_turn_player_id = None
        
        # Track opponent's turns_left to detect missed intermediate turn states
        # (e.g. AI responds faster than polling interval)
        self._last_opponent_turns_left = None
        
        # Track if game start notification was shown (needs to be shown once per player)
        self.game_start_notification_checked = False
        self._game_start_pending = False  # True while game_start request is in flight / unprocessed
        
        # Auto-fill notification (cleared after showing dialogue)
        self.pending_auto_fill = None
        
        # Opponent turn summaries (shown as turn-dialogue notifications in FIFO order)
        self.pending_opponent_turn_summary = None
        self.pending_opponent_turn_summaries = []
        self._last_shown_summary_log_id = None  # dedup stale notifications

        # Conquer startup lock: invader must resolve pending prelude target.
        self.pending_conquer_prelude_target = False

        # Conquer prelude spell snapshots captured at game_start (the
        # ActiveSpell entries don't carry a phase_cast field, so we keep
        # the summary-provided lists for the timeline panel).
        self.conquer_own_prelude_spells = []
        self.conquer_opp_prelude_spells = []
        
        # Ceasefire ended notification (cleared after showing dialogue)
        self.pending_ceasefire_ended = False
        
        # Ceasefire active notification (set after battle/fold when new round starts)
        self.pending_ceasefire_active_notification = False
        
        # Track previous ceasefire state to detect changes
        self.previous_ceasefire_active = self.ceasefire_active
        
        # Polling-only ceasefire snapshot — only _apply_game_dict updates this.
        # update_from_dict must NOT touch it, so action responses can't create
        # false transitions.
        self._last_polled_ceasefire = self.ceasefire_active
        
        # Round-based dedup: tracks (round, state) we last notified about
        # so repeated polls for the same round don't re-fire notifications.
        # state: 'active' or 'ended'
        self._ceasefire_notified_round = None
        self._ceasefire_notified_state = None
        
        # Display-level dedup: the round for which ceasefire-active was
        # already shown on screen.  Prevents any code path from showing
        # it twice in the same round.
        self._ceasefire_active_displayed_round = None
        
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
        self._last_advance_notified_id = None  # advancing_figure_id already notified about
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
        self._last_polled_advancing = self.advancing_figure_id  # Poll-only advance snapshot (not affected by update_from_dict)
        self._last_battle_ready_block_signature = None  # Dedup repeated "battle ready blocked" diagnostics across polls

        # Civil War second figure selection tracking
        self.civil_war_awaiting_second = False  # True when waiting for second advance figure
        self.civil_war_defender_second = False  # True when waiting for second defender figure
        self.civil_war_required_color = None  # 'offensive' or 'defensive' — required color for second pick

        # Conquer Invader Swap: original conquerer must select their own defender
        # after the automated invader advances a blockable figure.
        self.pending_conquer_own_defender_selection = False
        self.conquer_own_defender_selection_shown = False

        # Battle decision tracking (fold/battle)
        self.battle_decisions = game_dict.get('battle_decisions')
        self.battle_confirmed = game_dict.get('battle_confirmed', False)
        self.fold_outcome = game_dict.get('fold_outcome')
        self.fold_winner_id = game_dict.get('fold_winner_id')
        self.auto_loss_reason = game_dict.get('auto_loss_reason')
        self.auto_loss_detail = game_dict.get('auto_loss_detail')
        self.resting_figure_ids = game_dict.get('resting_figure_ids', [])
        self.waiting_for_battle_decision = False  # True when waiting for opponent's decision
        self._battle_decision_miss_count = 0  # consecutive polls without our decision
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
        self.battle_skipped_rounds = game_dict.get('battle_skipped_rounds') or {}
        # Viewer-oriented authoritative score supplied by get_battle_state
        # once all three conquer tactic rounds are complete.
        self.battle_total_diff = game_dict.get('battle_total_diff')
        # Conquer per-round 60s timer (unix timestamp) — None when no timer.
        self.conquer_round_deadline_ts = game_dict.get('conquer_round_deadline_ts')
        self.conquer_round_timeout_sec = game_dict.get('conquer_round_timeout_sec')
        self.conquer_resolution_step = int(game_dict.get('conquer_resolution_step', 0) or 0)
        self.conquer_tactics = game_dict.get('conquer_tactics', []) or []
        # Per-player gamble usage (tactics_hand conquer): {pid: {count, rounds}}.
        self.battle_gamble_counts = game_dict.get('battle_gamble_counts') or {}
        # All Seeing Eye gamble previews (owner-only, server-redacted):
        # {str(player_id): {tactic_id, round, specs}}.
        self.battle_gamble_previews = game_dict.get('battle_gamble_previews') or {}

        # Suppress next turn notification after battle/fold (result dialogue already shown)
        self.suppress_next_turn_summary = False

        # Last polled battle result — kept for safety-net notification if the
        # battle screen exits without showing a result dialogue.
        self._last_polled_battle_result = None

        # Game-over tracking
        self.game_over = (self.state == 'finished')
        self.pending_game_over = None  # Will be set to game_over dict when detected
        self.game_over_shown = False  # Track if game-over dialogue was shown

        # Prevent double-actions: set True when an action starts, cleared when
        # fresh game state arrives (via _apply_game_dict / update_from_dict).
        # A safety timeout (ms) auto-clears the lock if the server never responds.
        self.action_in_progress = False
        self._action_lock_time = 0          # pygame.time.get_ticks() when lock was set
        self._ACTION_LOCK_TIMEOUT_MS = 8000  # safety valve: 8 seconds

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
                logger.error("Failed to fetch game")
                return None

            game_dict = resp.json().get('game')
            if not game_dict:
                logger.debug("Game data not found in response")
                return None

            logs = []
            chats = []
            active_spells = []
            figures_by_player = {}
            try:
                logs = fetch_log_entries(game_id)
            except Exception as e:
                logger.error(f"BG: Failed to fetch log entries: {e}")
            try:
                chats = fetch_chat_messages(game_id)
            except Exception as e:
                logger.error(f"BG: Failed to fetch chat messages: {e}")
            try:
                from utils import spell_service
                active_spells = spell_service.fetch_active_spells(game_id)
            except Exception as e:
                logger.error(f"BG: Failed to fetch active spells: {e}")
            # Fetch figures for all players in the game
            for player in game_dict.get('players', []):
                pid = player['id']
                try:
                    figures_by_player[pid] = fetch_figures(pid)
                except Exception as e:
                    logger.error(f"BG: Failed to fetch figures for player {pid}: {e}")
                    figures_by_player[pid] = []

            return {
                'game': game_dict,
                'logs': logs,
                'chats': chats,
                'active_spells': active_spells,
                'figures': figures_by_player,
            }
        except Exception as e:
            logger.error(f"BG fetch error: {e}")
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
        if new_figures != self.cached_figures_data:
            self.cached_figures_data = new_figures
            self._figures_data_version += 1

    def update(self):
        """Update game state from the server (blocking / legacy path)."""
        data = self.fetch_server_data(self.game_id)
        if data:
            self.apply_server_data(data)

    # ── Action lock helpers ────────────────────────────────────

    def lock_actions(self):
        """Set the action lock.  Call before a server action."""
        self.action_in_progress = True
        self._action_lock_time = pygame.time.get_ticks()

    def unlock_actions(self):
        """Clear the action lock (e.g. on failure / error)."""
        self.action_in_progress = False
        self._action_lock_time = 0

    def check_action_lock_timeout(self):
        """Auto-clear the lock if it's been held too long (safety valve)."""
        if self.action_in_progress and self._action_lock_time:
            elapsed = pygame.time.get_ticks() - self._action_lock_time
            if elapsed > self._ACTION_LOCK_TIMEOUT_MS:
                logger.info(f"[ACTION_LOCK] Timeout after {elapsed}ms — force-unlocking")
                self.unlock_actions()

    def _clear_conquer_advance_dependent_flags(self):
        """Clear local latches that are only valid while an advance exists."""
        if getattr(self, 'mode', None) != 'conquer':
            return
        self.pending_defender_selection = False
        self.defender_selection_dialogue_shown = False
        self.pending_waiting_for_defender_pick = False
        self.waiting_for_defender_pick_shown = False
        self.pending_battle_ready = False
        self.battle_ready_shown = False
        self.pending_advance_notification = False
        self.pending_own_advance_notification = False
        self.own_advance_figure_name = None
        self.pending_conquer_own_defender_selection = False
        self.conquer_own_defender_selection_shown = False
        self.civil_war_awaiting_second = False
        self.civil_war_defender_second = False
        self.civil_war_required_color = None

    def _clear_conquer_battle_cycle_flags(self):
        """Clear client-side conquer prompts when the server resets a battle."""
        if getattr(self, 'mode', None) != 'conquer':
            return
        self.pending_forced_advance = False
        self.forced_advance_dialogue_shown = False
        self._clear_conquer_advance_dependent_flags()

    def _apply_game_dict(self, game_dict):
        """Apply a game dict to this instance (main-thread only)."""
        self._game_data_version += 1
        # Fresh server state arrived — unlock actions
        self.unlock_actions()
        self.game_id = game_dict['id']
        self.state = game_dict['state']
        self.mode = game_dict.get('mode', self.mode)
        self.conquer_move_model = game_dict.get(
            'conquer_move_model', getattr(self, 'conquer_move_model', 'battle_move'))
        self.land_id = game_dict.get('land_id', self.land_id)
        self.land_tier = game_dict.get('land_tier', self.land_tier)
        self.land_gold_rate = game_dict.get('land_gold_rate', self.land_gold_rate)
        self.land_suit_bonus_suit = game_dict.get(
            'land_suit_bonus_suit', self.land_suit_bonus_suit)
        self.land_suit_bonus_value = game_dict.get(
            'land_suit_bonus_value', self.land_suit_bonus_value)
        self.date = game_dict['date']
        self.stake = game_dict.get('stake', 45)
        self.game_limit = game_dict.get('game_limit', self.stake)
        self.winner_player_id = game_dict.get('winner_player_id')
        self.finished_at = game_dict.get('finished_at')
        self.last_battle_result = game_dict.get('last_battle_result') or {}
        self.players = game_dict.get('players', [])
        self.main_cards = game_dict.get('main_cards', [])
        self.side_cards = game_dict.get('side_cards', [])
        self.current_round = game_dict.get('current_round', 1)
        self.invader_player_id = game_dict.get('invader_player_id')
        self.turn_player_id = game_dict.get('turn_player_id')

        # Detect game-over from server (opponent might have triggered it)
        # Skip for conquer mode — battle_screen handles conquer end directly
        if self.state == 'finished' and not self.game_over and not self.game_over_shown and self.mode != 'conquer':
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
                    'game_limit': self.game_limit,
                    'rounds_played': game_dict.get('current_round', 1),
                    'stats': last_result.get('game_stats', {}),
                    'reward_draws': last_result.get('game_over_reward_draws'),
                    'reward_expectations': last_result.get('game_over_reward_expectations'),
                    'winner_rewards': last_result.get('game_over_winner_rewards'),
                    'loser_rewards': last_result.get('game_over_loser_rewards'),
                    'winner_boosters': last_result.get('game_over_winner_boosters'),
                    'loser_boosters': last_result.get('game_over_loser_boosters'),
                }
                logger.info(f"[GAME_OVER] Detected from polling: {self.pending_game_over}")
        
        # Update ceasefire tracking — use _last_polled_ceasefire for transition
        # detection so that update_from_dict (action responses) can't create
        # false transitions between polls.
        previous_ceasefire = self._last_polled_ceasefire
        self.ceasefire_active = game_dict.get('ceasefire_active', False)
        self.ceasefire_start_turn = game_dict.get('ceasefire_start_turn')
        self._last_polled_ceasefire = self.ceasefire_active
        cur_round = game_dict.get('current_round', self.current_round)
        
        # Detect ceasefire ending (transition from active to inactive)
        # Skip if a battle just ended (suppress_next_turn_summary is set by
        # _reset_battle_state / _reset_after_battle).  Blitzkrieg ceasefire
        # always ends when its battle resolves; we don't want a stale or
        # fresh post-battle poll to trigger a ceasefire-ended notification.
        if previous_ceasefire and not self.ceasefire_active and not self.suppress_next_turn_summary:
            # Dedup: only fire once per (round, state) pair
            if self._ceasefire_notified_round != cur_round or self._ceasefire_notified_state != 'ended':
                logger.info(f"[CEASEFIRE] Detected ceasefire ended (was active, now inactive) round={cur_round}")
                self.pending_ceasefire_ended = True
                self.pending_ceasefire_active_notification = False
                self._ceasefire_notified_round = cur_round
                self._ceasefire_notified_state = 'ended'
                # Mark display-round so stale poll data can't re-show "active"
                # for a round where ceasefire already ended.
                self._ceasefire_active_displayed_round = cur_round
        
        # Detect ceasefire activation (transition from inactive to active)
        if not previous_ceasefire and self.ceasefire_active:
            # Ignore if ceasefire already ended this round — stale server data
            # from a concurrent request that loaded the game before the
            # ceasefire-end commit was visible.
            if self._ceasefire_notified_round == cur_round and self._ceasefire_notified_state == 'ended':
                logger.info(f"[CEASEFIRE] _apply_game_dict: ignoring activation — ceasefire already ended round={cur_round} (stale poll data)")
            elif self._ceasefire_notified_round != cur_round or self._ceasefire_notified_state != 'active':
                logger.info(f"[CEASEFIRE] _apply_game_dict: activating notification, prev_polled={previous_ceasefire}, now={self.ceasefire_active}, round={cur_round}, displayed_round={self._ceasefire_active_displayed_round}")
                self.pending_ceasefire_active_notification = True
                self._ceasefire_notified_round = cur_round
                self._ceasefire_notified_state = 'active'

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
        # Use _last_polled_advancing (updated only here) instead of
        # self.advancing_figure_id which update_from_dict may have already
        # changed, hiding the set→None transition that resets battle_ready_shown.
        previous_advancing = self._last_polled_advancing
        self.advancing_figure_id = game_dict.get('advancing_figure_id')
        self.advancing_figure_id_2 = game_dict.get('advancing_figure_id_2')
        self.advancing_player_id = game_dict.get('advancing_player_id')
        self.defending_figure_id = game_dict.get('defending_figure_id')
        self.defending_figure_id_2 = game_dict.get('defending_figure_id_2')
        self._last_polled_advancing = self.advancing_figure_id
        
        # Clear forced advance once an advance is underway
        if self.pending_forced_advance and self.advancing_figure_id:
            self.pending_forced_advance = False
        
        # Reset advance-notification tracking when advance is fully cleared
        if not self.advancing_figure_id:
            self._last_advance_notified_id = None
            if self.mode == 'conquer':
                self._clear_conquer_advance_dependent_flags()
            # Server cleared battle state (new round) — allow battle_ready
            # detection again.  Until this moment, battle_ready_shown stays
            # True to block stale in-flight polls from re-triggering the
            # battle/fold dialogue.
            if previous_advancing:
                self.battle_ready_shown = False
                self.pending_battle_ready = False
                # Conquer redesign: a battle just ended (advancing/defending
                # cleared by the server).  Wipe any client-side latches and
                # heuristic flags that survived the previous cycle, otherwise
                # the next conquest would inherit ghost dialogues / modes.
                self._clear_conquer_battle_cycle_flags()
        elif not previous_advancing:
            # A brand-new advance appeared (None → set).  Reset battle_ready
            # tracking so the fight/fold dialogue can fire for this new battle.
            # This is needed after folds: _reset_battle_state sets
            # battle_ready_shown=True to block stale polls, but the next
            # advance in the new round must be allowed through.
            self.battle_ready_shown = False
            self.pending_battle_ready = False

        # Detect opponent advance (new advance appeared and it's not ours)
        # Use turn value from game_dict directly (self.turn is stale at this point)
        is_now_our_turn = (game_dict.get('turn_player_id') == self.player_id)
        if (self.advancing_figure_id and not previous_advancing and 
            self.advancing_player_id != self.player_id and is_now_our_turn
            and self.advancing_figure_id != self._last_advance_notified_id):
            self.pending_advance_notification = True
            self._last_advance_notified_id = self.advancing_figure_id
            # Advance has its own notification; do not drop already queued turn summaries.
        # Civil War fallback: advance was detected on an earlier poll when it
        # wasn't our turn (invader was picking second figure).  Now the turn
        # just came to us — fire the advance notification we missed.
        elif (self.advancing_figure_id and previous_advancing and
              self.advancing_player_id != self.player_id and
              is_now_our_turn and
              self.previous_turn_player_id != self.player_id and
              not self.pending_advance_notification and
              not self.defending_figure_id and
              self.advancing_figure_id != self._last_advance_notified_id):
            self.pending_advance_notification = True
            self._last_advance_notified_id = self.advancing_figure_id
            # Advance has its own notification; do not drop already queued turn summaries.
        
        # Sync local in-battle flag from server state.
        # If a client misses a cleanup path after battle resolution, a stale
        # in_battle_phase=True would block all future battle-ready detection.
        server_battle_confirmed = game_dict.get('battle_confirmed', False)
        server_battle_turn_player_id = game_dict.get('battle_turn_player_id')
        if self.in_battle_phase and not server_battle_confirmed and server_battle_turn_player_id is None:
            logger.warning("[BATTLE_PHASE] Clearing stale in_battle_phase based on server state")
            self.in_battle_phase = False
            self.battle_turns_left = 0

        # Skip advance/defender detection while a battle is active on the
        # server (prevents stale flags from re-triggering after resolution).
        battle_active = (
            server_battle_confirmed
            or bool(game_dict.get('battle_decisions'))
            or bool(game_dict.get('fold_outcome'))
        )

        # Check the *effective* Civil War modifier. Royal Decree overrides
        # Civil War's village-only/two-figure flow, so the presence of a stale
        # or stacked Civil War entry alone must not hold battle-ready state.
        modifiers = self.battle_modifier if isinstance(self.battle_modifier, list) else []
        has_civil_war = civil_war_pick_flow_active(modifiers)
        if not has_civil_war:
            self.civil_war_awaiting_second = False
            self.civil_war_defender_second = False
            self.civil_war_required_color = None

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

        # Detect: Conquer Invader Swap — original conquerer must select own defender.
        # Active when: mode=conquer, Invader Swap spell executed, we are the
        # original conquerer (old_invader_id), opponent has advanced, it's our
        # turn, no defender chosen, and advance is blockable.
        if (not battle_active
                and self.mode == 'conquer'
                and is_now_our_turn
                and self.advancing_figure_id
                and self.advancing_player_id != self.player_id
                and not self.defending_figure_id
                and not self.pending_conquer_own_defender_selection
                and not self.conquer_own_defender_selection_shown):
            active_spells = game_dict.get('active_spells', [])
            swap_spell = next(
                (s for s in active_spells
                 if s.get('spell_name') == 'Invader Swap'
                 and isinstance(s.get('effect_data'), dict)
                 and s['effect_data'].get('conquer_invader_swap')
                 and s['effect_data'].get('old_invader_id') == self.player_id),
                None,
            )
            if swap_spell:
                # Check if the advancing figure is cannot_be_blocked
                # (if so, AI picks the target, not the conquerer)
                adv_fig_blockable = True
                for p in game_dict.get('players', []):
                    for fig in p.get('figures', []):
                        if fig.get('id') == self.advancing_figure_id:
                            if fig.get('cannot_be_blocked'):
                                adv_fig_blockable = False
                            break
                if adv_fig_blockable:
                    self.pending_conquer_own_defender_selection = True
                    # Suppress the generic waiting-for-defender notification
                    self.pending_waiting_for_defender_pick = False
                    logger.info(
                        f"[INVADER_SWAP] Own defender selection triggered: "
                        f"advancing={self.advancing_figure_id}"
                    )
        
        # Battle is ready when both sides have their figures set.
        # NOTE: an opponent-only entry in battle_decisions must NOT block
        # this — the invader decides first, so when only their decision is
        # recorded we (the defender) still owe ours.  Blocking here stalled
        # conquer games where the automated invader's decision was recorded
        # server-side before the client ever saw the completed selection.
        decisions_now = game_dict.get('battle_decisions') or {}
        own_decision_recorded = str(self.player_id) in decisions_now
        battle_ready_blocked = (
            server_battle_confirmed
            or own_decision_recorded
            or bool(game_dict.get('fold_outcome'))
        )
        battle_ready = (not battle_ready_blocked and
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

        # High-signal diagnostics for "no fight/fold dialogue" incidents.
        # Log once per distinct blocked state to avoid poll spam.
        if self.advancing_figure_id and self.defending_figure_id:
            if battle_ready:
                self._last_battle_ready_block_signature = None
            else:
                blocked_reasons = []
                if battle_ready_blocked:
                    blocked_reasons.append('battle_active')
                if self.pending_battle_ready:
                    blocked_reasons.append('pending_battle_ready')
                if self.battle_ready_shown:
                    blocked_reasons.append('battle_ready_shown')
                if has_civil_war and self.civil_war_awaiting_second:
                    blocked_reasons.append('civil_war_invader_second_pending')
                if has_civil_war and self.civil_war_defender_second:
                    blocked_reasons.append('civil_war_defender_second_pending')
                if (has_civil_war and self.advancing_player_id == self.player_id
                        and not is_now_our_turn):
                    blocked_reasons.append('civil_war_turn_not_returned')

                signature = (
                    self.advancing_figure_id,
                    self.defending_figure_id,
                    tuple(blocked_reasons),
                    self.advancing_player_id,
                    game_dict.get('turn_player_id'),
                )
                if signature != self._last_battle_ready_block_signature:
                    logger.warning(
                        f"[BATTLE_READY_BLOCKED] adv={self.advancing_figure_id}/{self.advancing_figure_id_2} "
                        f"def={self.defending_figure_id}/{self.defending_figure_id_2} "
                        f"reasons={blocked_reasons or ['unknown']} "
                        f"advancing_player={self.advancing_player_id} turn_player={game_dict.get('turn_player_id')}"
                    )
                    self._last_battle_ready_block_signature = signature
        
        if battle_ready:
            self.pending_battle_ready = True
            logger.info(f"[BATTLE_READY] Figures set: advancing={self.advancing_figure_id}/{self.advancing_figure_id_2}, defending={self.defending_figure_id}/{self.defending_figure_id_2}")

        # Detect fold outcome from opponent's battle decision (polling detection)
        was_battle_moves_phase = self.battle_moves_phase
        previous_fold_outcome = self.fold_outcome
        previous_battle_confirmed = self.battle_confirmed
        self.battle_decisions = game_dict.get('battle_decisions')
        self.battle_confirmed = game_dict.get('battle_confirmed', False)
        self.battle_moves_confirmed = game_dict.get('battle_moves_confirmed')
        self.fold_outcome = game_dict.get('fold_outcome')
        self.fold_winner_id = game_dict.get('fold_winner_id')
        self.auto_loss_reason = game_dict.get('auto_loss_reason')
        self.auto_loss_detail = game_dict.get('auto_loss_detail')
        self.resting_figure_ids = game_dict.get('resting_figure_ids', [])

        # Safety net: if we think we're waiting for the opponent's decision
        # but the server has NO record of our decision, the POST may have
        # failed (e.g. server restart mid-request).  Only reset after
        # several consecutive misses to avoid a race with the POST still
        # in flight.
        if (self.waiting_for_battle_decision and
                self.advancing_figure_id and self.defending_figure_id and
                not self.battle_confirmed and not self.fold_outcome):
            decisions = self.battle_decisions or {}
            my_decision = decisions.get(str(self.player_id))
            if my_decision is None:
                self._battle_decision_miss_count += 1
                if self._battle_decision_miss_count >= 3:
                    logger.warning("[BATTLE_DECISION] Safety net: waiting but server has no record of our decision after %d polls — resetting", self._battle_decision_miss_count)
                    self.waiting_for_battle_decision = False
                    self._battle_decision_miss_count = 0
                    self.battle_ready_shown = False
                    self.pending_battle_ready = False  # will be re-set by battle_ready check below
            else:
                self._battle_decision_miss_count = 0

        # Update server-authoritative battle round tracking
        self.battle_round = game_dict.get('battle_round', 0)
        self.battle_turn_player_id = game_dict.get('battle_turn_player_id')
        self.battle_skipped_rounds = game_dict.get('battle_skipped_rounds') or {}
        self.conquer_round_deadline_ts = game_dict.get('conquer_round_deadline_ts')
        self.conquer_round_timeout_sec = game_dict.get('conquer_round_timeout_sec')
        self.conquer_resolution_step = int(game_dict.get('conquer_resolution_step', 0) or 0)
        self.conquer_tactics = game_dict.get('conquer_tactics', []) or []
        self.battle_gamble_counts = game_dict.get('battle_gamble_counts') or {}
        self.battle_gamble_previews = game_dict.get('battle_gamble_previews') or {}
        self._sync_battle_moves_phase_from_server()

        # Reset fold tracking when server clears fold state (new round started)
        if previous_fold_outcome and not self.fold_outcome:
            self.fold_result_shown = False
            self.pending_fold_result = False

        # Detect new fold outcome (transition from None to set)
        if self.fold_outcome and not previous_fold_outcome and not self.fold_result_shown:
            self.pending_fold_result = True
            self.waiting_for_battle_decision = False
            logger.info(f"[FOLD] Detected fold outcome: {self.fold_outcome}, winner: {self.fold_winner_id}")

        # Detect both chose battle (transition from False to True)
        if (self.battle_confirmed and not previous_battle_confirmed and
                (self.waiting_for_battle_decision or self.mode == 'conquer')):
            self.auto_proceed_to_battle = True
            self.waiting_for_battle_decision = False
            logger.info(f"[BATTLE_DECISION] Both players chose battle — auto-proceeding")

        # Detect transition from move-selection to active battle rounds.
        player_ids = [str(p.get('id')) for p in (self.players or []) if p.get('id') is not None]
        confirmed = self.battle_moves_confirmed or {}
        all_confirmed = bool(player_ids) and all(confirmed.get(pid) for pid in player_ids)
        if (was_battle_moves_phase and
            all_confirmed and
            self.battle_turn_player_id is not None):
            self.both_battle_moves_ready = True
            self.waiting_for_opponent_battle_moves = False
            logger.debug(f"[BATTLE_MOVES] Both players confirmed battle moves — proceed to battle")

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

        # Track opponent's turns_left for missed-turn detection
        opp_turns = None
        for p in self.players:
            if p['id'] != self.player_id:
                opp_turns = p.get('turns_left')
                break
        prev_opp_turns = self._last_opponent_turns_left
        self._last_opponent_turns_left = opp_turns

        # Check for game start notification on first update (regardless of turn number)
        if not self.game_start_notification_checked:
            self.start_game_start_notification_if_needed()
        
        # Suppress all turn-change detection while game_start is in flight /
        # unprocessed.  Without this guard, a fast AI opponent causes a race:
        # the turn-change _start_turn_async and the game_start _start_turn_async
        # both write to pending_opponent_turn_summary and the last writer wins,
        # potentially losing the opponent action notification.
        elif self._game_start_pending:
            pass
        
        # Check if turn changed to current player - call start_turn endpoint
        elif not previous_turn and self.turn and self.previous_turn_player_id != self.turn_player_id:
            logger.info(f"[TURN CHANGE] Detected turn change to current player. Calling start_turn...")
            self._start_turn_async()
        
        # Detect spell resolution: if our spell was pending and just resolved,
        # and it's still our turn (e.g., Invader Swap keeps turn with caster),
        # trigger _handle_start_turn for auto-fill since turn-change detection missed it
        elif previous_pending_spell_id and not self.pending_spell_id and self.turn and previous_turn:
            logger.info(f"[SPELL_RESOLVED] Spell resolved while turn stayed with us. Calling start_turn for auto-fill...")
            self._start_turn_async()
        
        # Missed intermediate turn: it was our turn before, it's our turn now,
        # but the opponent's turns_left changed — meaning the opponent took a
        # turn between polls and we never observed the turn=AI state.
        elif (self.turn and previous_turn and
              prev_opp_turns is not None and opp_turns is not None and
              opp_turns != prev_opp_turns):
            logger.info(f"[TURN CHANGE] Missed intermediate turn — opponent turns_left {prev_opp_turns}→{opp_turns}. Calling start_turn...")
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
                logger.info(f"[POST_BATTLE] Drew side cards for new round {self.current_round}: {my_cards}")

        # Detect loot notification for battle loser (which card the winner kept)
        last_result = game_dict.get('last_battle_result') or {}
        # Keep a copy for the battle-screen safety net (missed result dialogue)
        if last_result and (last_result.get('winner_player_id') or last_result.get('conquer_resolved')):
            self._last_polled_battle_result = dict(last_result)
        picked_card = last_result.get('picked_card')
        loser_id = last_result.get('loser_player_id')
        if last_result and picked_card and loser_id == self.player_id and self.current_round != self._loot_notification_round:
            logger.debug(f"[LOOT_DEBUG] _apply_game_dict: picked_card={picked_card}, loser_id={loser_id}, round={self.current_round}")
        if (picked_card and self.player_id and
                loser_id == self.player_id and
                self.current_round != self._loot_notification_round):
            self.pending_loot_notification = {
                'suit': picked_card['suit'],
                'rank': picked_card['rank'],
                'card_type': picked_card['card_type'],
                'winner_name': last_result.get('winner_name', 'Opponent'),
            }
            self._loot_notification_round = self.current_round
            logger.info(f"[LOOT] Opponent kept card: {picked_card}")


    def update_from_dict(self, game_dict):
        """Update game state directly from a dictionary (e.g., from spell service response)."""
        self._game_data_version += 1
        # Fresh server state arrived — unlock actions
        self.unlock_actions()
        # Update game data
        self.game_id = game_dict['id']
        self.state = game_dict['state']
        self.mode = game_dict.get('mode', self.mode)
        self.conquer_move_model = game_dict.get(
            'conquer_move_model', getattr(self, 'conquer_move_model', 'battle_move'))
        self.land_id = game_dict.get('land_id', self.land_id)
        self.land_tier = game_dict.get('land_tier', self.land_tier)
        self.land_gold_rate = game_dict.get('land_gold_rate', self.land_gold_rate)
        self.land_suit_bonus_suit = game_dict.get(
            'land_suit_bonus_suit', self.land_suit_bonus_suit)
        self.land_suit_bonus_value = game_dict.get(
            'land_suit_bonus_value', self.land_suit_bonus_value)
        self.date = game_dict['date']
        self.stake = game_dict.get('stake', getattr(self, 'stake', 45))
        self.game_limit = game_dict.get('game_limit', self.stake)
        self.winner_player_id = game_dict.get('winner_player_id')
        self.finished_at = game_dict.get('finished_at')
        self.last_battle_result = game_dict.get('last_battle_result') or {}
        self.players = game_dict.get('players', [])
        self.main_cards = game_dict.get('main_cards', [])
        self.side_cards = game_dict.get('side_cards', [])
        self.current_round = game_dict.get('current_round', 1)
        self.invader_player_id = game_dict.get('invader_player_id')
        self.turn_player_id = game_dict.get('turn_player_id')
        
        # Update ceasefire tracking — raw fields only.
        # Transition detection is handled exclusively by _apply_game_dict (polling)
        # to avoid stale action-response data re-triggering notifications.
        self.ceasefire_active = game_dict.get('ceasefire_active', False)
        self.ceasefire_start_turn = game_dict.get('ceasefire_start_turn')

        # Update spell-related state
        self.pending_spell_id = game_dict.get('pending_spell_id')
        self.battle_modifier = game_dict.get('battle_modifier')
        self.waiting_for_counter_player_id = game_dict.get('waiting_for_counter_player_id')
        if not civil_war_pick_flow_active(self.battle_modifier):
            self.civil_war_awaiting_second = False
            self.civil_war_defender_second = False
            self.civil_war_required_color = None
        
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

        if self.mode == 'conquer' and not self.advancing_figure_id:
            self._clear_conquer_advance_dependent_flags()
            if previous_advancing:
                self.battle_ready_shown = False
                self.pending_battle_ready = False
                self._clear_conquer_battle_cycle_flags()
        
        # Update battle decision/fold state
        self.battle_decisions = game_dict.get('battle_decisions')
        previous_battle_confirmed = self.battle_confirmed
        self.battle_confirmed = game_dict.get('battle_confirmed', False)
        self.battle_moves_confirmed = game_dict.get('battle_moves_confirmed')
        previous_fold_outcome = self.fold_outcome
        self.fold_outcome = game_dict.get('fold_outcome')
        self.fold_winner_id = game_dict.get('fold_winner_id')

        battle_active = (
            self.battle_confirmed
            or bool(self.battle_decisions)
            or bool(self.fold_outcome)
        )
        is_now_our_turn = (self.turn_player_id == self.player_id)
        if (not battle_active and
            self.advancing_figure_id and
            self.advancing_player_id == self.player_id and
            not self.defending_figure_id and
            is_now_our_turn and
            not self.pending_defender_selection and
            not self.defender_selection_dialogue_shown and
            not self.civil_war_awaiting_second):
            self.pending_defender_selection = True

        # Fix: If battle is confirmed, forcibly set guards to prevent double notification
        if self.battle_confirmed:
            self.pending_battle_ready = False
            self.battle_ready_shown = True

        # Detect both chose battle (transition) — mirrors _apply_game_dict
        if (self.battle_confirmed and not previous_battle_confirmed and
                (self.waiting_for_battle_decision or self.mode == 'conquer')):
            self.auto_proceed_to_battle = True
            self.waiting_for_battle_decision = False
            logger.info("[BATTLE_DECISION] update_from_dict: both players chose battle — auto-proceeding")

        # Detect fold outcome (transition) — mirrors _apply_game_dict
        if (self.fold_outcome and not previous_fold_outcome and
                not self.fold_result_shown):
            self.pending_fold_result = True
            self.waiting_for_battle_decision = False
            logger.info(f"[FOLD] update_from_dict: fold outcome={self.fold_outcome}, winner={self.fold_winner_id}")
        
        # Detect battle_ready when both figures are set (e.g. after select_defender)
        if (self.advancing_figure_id and self.defending_figure_id and
                not self.battle_confirmed and
                not self.pending_battle_ready and not self.battle_ready_shown):
            self.pending_battle_ready = True
            logger.info(f"[BATTLE_READY] update_from_dict: both figures set, triggering battle_ready")
        
        # Update battle round tracking
        self.battle_round = game_dict.get('battle_round', 0)
        self.battle_turn_player_id = game_dict.get('battle_turn_player_id')
        self.battle_skipped_rounds = game_dict.get('battle_skipped_rounds') or {}
        # Conquer per-round 60s move deadline (unix ts) — None if no timer.
        self.conquer_round_deadline_ts = game_dict.get('conquer_round_deadline_ts')
        self.conquer_round_timeout_sec = game_dict.get('conquer_round_timeout_sec')
        self.conquer_resolution_step = int(game_dict.get('conquer_resolution_step', 0) or 0)
        self.conquer_tactics = game_dict.get('conquer_tactics', []) or []
        self.battle_gamble_counts = game_dict.get('battle_gamble_counts') or {}
        self.battle_gamble_previews = game_dict.get('battle_gamble_previews') or {}
        self._sync_battle_moves_phase_from_server()

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
                logger.info(f"[POST_BATTLE] Drew side cards for new round {self.current_round}: {my_cards}")

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
            logger.info(f"[LOOT] Opponent kept card (update_from_dict): {picked_card}")

        # Note: logs and chats are fetched by the background poller
        # No need to block here — the next poll cycle will pick them up

    def _start_turn_async(self):
        """Fire _handle_start_turn in a background thread (desktop) or via
        non-blocking async XHR (web). On emscripten the prior
        ``threading.Thread`` path silently fell back to a synchronous
        ``requests.post`` that blocked the main loop on every turn change —
        causing a regular ~2s hitch during conquer battles where turns flip
        between player and AI on each poll cycle.
        """
        if _sys.platform == "emscripten":
            self._start_async_start_turn_web()
            return
        try:
            t = threading.Thread(target=self._handle_start_turn, daemon=True)
            t.start()
        except RuntimeError:
            self._handle_start_turn()  # fallback: run synchronously

    def start_game_start_notification_if_needed(self):
        """Kick off the one-shot game-start summary request immediately."""
        if self.game_start_notification_checked:
            return False
        logger.info(
            f"[GAME_START] First update — player_id={self.player_id}, "
            f"turn={self.turn}, invader={self.invader}"
        )
        self.game_start_notification_checked = True
        self._game_start_pending = True
        self._start_turn_async()
        return True

    def _start_async_start_turn_web(self):
        """Web-only: fire start_turn POST asynchronously, drain on main thread."""
        try:
            from utils.http_compat import start_async_post_json
        except Exception as e:
            logger.error(f"[START_TURN] async helper unavailable: {e}")
            return
        payload = {'game_id': self.game_id, 'player_id': self.player_id}
        if getattr(self, '_pending_start_turn_rids', None) is None:
            self._pending_start_turn_rids = []
        try:
            rid = start_async_post_json(
                f'{settings.SERVER_URL}/games/start_turn', payload)
            self._pending_start_turn_rids.append(rid)
        except Exception as e:
            logger.error(f"[START_TURN] async POST failed to start: {e}")
            if self.mode == 'conquer':
                self._game_start_pending = False

    def drain_pending_start_turn(self):
        """Apply any completed start_turn responses (web async path).

        Safe to call every frame; cheap when nothing is pending.
        Desktop path uses real threads and does not need this drain.
        """
        rids = getattr(self, '_pending_start_turn_rids', None)
        if not rids:
            return
        try:
            from utils.http_compat import check_async
        except Exception:
            return
        still = []
        for rid in rids:
            try:
                resp = check_async(rid)
            except Exception as e:
                logger.debug(f"[START_TURN] async check error: {e}")
                resp = None
            if resp is None:
                still.append(rid)
                continue
            if resp.status_code != 200:
                try:
                    body = resp.json()
                except Exception:
                    body = resp.text[:200] if hasattr(resp, 'text') else ''
                logger.error(f"[START_TURN] Failed with status {resp.status_code}: {body}")
                if self.mode == 'conquer':
                    self._game_start_pending = False
                continue
            try:
                data = resp.json()
            except Exception as e:
                logger.error(f"[START_TURN] bad JSON: {e}")
                if self.mode == 'conquer':
                    self._game_start_pending = False
                continue
            try:
                self._apply_start_turn_response(data)
            except Exception as e:
                logger.error(f"[START_TURN] apply error: {e}")
                if self.mode == 'conquer':
                    self._game_start_pending = False
        self._pending_start_turn_rids = still

    def _handle_start_turn(self):
        """Called when turn changes to current player. Checks and handles auto-fill."""
        try:
            payload = {
                'game_id': self.game_id,
                'player_id': self.player_id
            }
            logger.debug(f"[START_TURN] Sending payload: game_id={self.game_id} (type={type(self.game_id)}), player_id={self.player_id} (type={type(self.player_id)})")
            
            response = requests.post(
                f'{settings.SERVER_URL}/games/start_turn',
                json=payload,
                timeout=10
            )
            
            if response.status_code != 200:
                logger.error(f"[START_TURN] Failed with status {response.status_code}: {response.json()}")
                return
            
            data = response.json()
            logger.debug(f"[START_TURN] Response: {data}")
            self._apply_start_turn_response(data)
        except Exception as e:
            logger.error(f"Error in start_turn: {str(e)}")

    def _apply_start_turn_response(self, data):
        """Apply the parsed JSON body returned by ``/games/start_turn``."""
        if not data.get('success'):
            if self.mode == 'conquer':
                self._game_start_pending = False
            return
        auto_fill = data.get('auto_fill')
        if auto_fill:
            # Store for dialogue display
            logger.debug(f"[START_TURN] Auto-fill needed: {auto_fill}")
            self.pending_auto_fill = auto_fill
        else:
            logger.debug(f"[START_TURN] No auto-fill needed")

        # Store opponent turn summary for dialogue display
        # But suppress it if an advance notification is pending (advance has its own notification)
        # Also suppress after battle/fold resolution (result dialogue already shown)
        # Exception: never suppress notifications that directly affect the player
        # (e.g. Forced Deal card swap, Dump Cards, Poison on player's figure, Explosion)
        # In conquer mode, suppress all non-game_start turn summaries
        opponent_turn_summary = data.get('opponent_turn_summary')
        action_data = opponent_turn_summary.get('action', {}) if opponent_turn_summary and isinstance(opponent_turn_summary.get('action'), dict) else {}
        affects_player = action_data.get('affects_player', False)
        action_type = opponent_turn_summary.get('action') if opponent_turn_summary else None

        # In conquer mode, suppress only truly empty/unknown turn summaries.
        # Allow spell casts, counter-advances, and player-affecting actions through.
        action_type_str = action_data.get('type', '') if isinstance(action_data, dict) else ''
        is_meaningful = (affects_player
                         or action_type == 'game_start'
                         or action_type_str in ('spell', 'counter_advance', 'advance'))
        if self.mode == 'conquer' and not is_meaningful:
            logger.debug(f"[START_TURN] Suppressing opponent turn summary — conquer mode (action_type={action_type_str})")
        elif affects_player and opponent_turn_summary:
            # Always show notifications that directly affect the player's state
            logger.debug(f"[START_TURN] Opponent turn summary affects player — showing regardless of other state")
            self._queue_opponent_turn_summary(opponent_turn_summary)
        elif self.suppress_next_turn_summary:
            self.suppress_next_turn_summary = False
            # Fully suppress the post-battle/fold turn summary — the
            # round-start notifications (victory/defeat, ceasefire, side
            # cards) already cover what the player needs to know.
            logger.debug(f"[START_TURN] Suppressing opponent turn summary — post-battle/fold")
        elif (self.pending_advance_notification or
              (self.advancing_figure_id and
               self.advancing_player_id != self.player_id)):
            logger.debug(f"[START_TURN] Suppressing opponent turn summary — advance notification pending or opponent advance active")
        elif self.pending_battle_ready:
            logger.debug(f"[START_TURN] Suppressing opponent turn summary — battle ready pending")
        elif self.pending_fold_result:
            logger.debug(f"[START_TURN] Suppressing opponent turn summary — fold result pending")
        elif opponent_turn_summary:
            # Deduplicate: skip if this exact log was already shown
            summary_log_id = opponent_turn_summary.get('log_id')
            if summary_log_id and summary_log_id == self._last_shown_summary_log_id:
                logger.debug(f"[START_TURN] Skipping duplicate opponent turn summary (log_id={summary_log_id})")
            else:
                logger.debug(f"[START_TURN] Opponent turn summary received - action: {opponent_turn_summary.get('action')}")
                self._queue_opponent_turn_summary(opponent_turn_summary)
        else:
            logger.debug(f"[START_TURN] No opponent turn summary")

        # Conquer's timeline waits on the game-start summary so prelude spell
        # snapshots can be seeded before the overview advances.  Some web
        # start-turn responses legitimately contain no summary (or only an
        # empty one); in that case there is nothing left to process and the
        # overview gate must open instead of waiting forever.
        if self.mode == 'conquer' and getattr(self, '_game_start_pending', False):
            if not self._has_pending_conquer_game_start_summary():
                self._game_start_pending = False

    def _has_pending_conquer_game_start_summary(self):
        """Return True if a queued turn summary still needs game-start handling."""
        pending = []
        summary = getattr(self, 'pending_opponent_turn_summary', None)
        if summary:
            pending.append(summary)
        queue = getattr(self, 'pending_opponent_turn_summaries', None) or []
        pending.extend(queue)
        for item in pending:
            if not isinstance(item, dict):
                continue
            if item.get('action') == 'game_start' and item.get('mode') == 'conquer':
                return True
        return False

    def _queue_opponent_turn_summary(self, summary):
        """Queue a turn summary without overwriting an older unseen one."""
        if not summary:
            return
        queue = getattr(self, 'pending_opponent_turn_summaries', None)
        if queue is None:
            queue = []
            self.pending_opponent_turn_summaries = queue

        pending = getattr(self, 'pending_opponent_turn_summary', None)
        if pending and not queue:
            queue.append(pending)

        summary_log_id = summary.get('log_id') if isinstance(summary, dict) else None
        if summary_log_id:
            if summary_log_id == self._last_shown_summary_log_id:
                return
            for queued in queue:
                if isinstance(queued, dict) and queued.get('log_id') == summary_log_id:
                    return
            if isinstance(pending, dict) and pending.get('log_id') == summary_log_id:
                return

        queue.append(summary)
        self.pending_opponent_turn_summary = queue[0] if queue else None

    def pop_pending_opponent_turn_summary(self):
        """Pop the next queued opponent turn summary, preserving legacy single-value state."""
        queue = getattr(self, 'pending_opponent_turn_summaries', None)
        if queue:
            summary = queue.pop(0)
        else:
            summary = getattr(self, 'pending_opponent_turn_summary', None)

        self.pending_opponent_turn_summary = queue[0] if queue else None
        if isinstance(summary, dict):
            summary_log_id = summary.get('log_id')
            if summary_log_id:
                self._last_shown_summary_log_id = summary_log_id
        return summary

    def clear_pending_opponent_turn_summaries(self):
        """Clear queued and legacy opponent-turn summaries."""
        self.pending_opponent_turn_summaries = []
        self.pending_opponent_turn_summary = None

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
            if c['player_id'] == player_id and not c.get('in_deck', False) and not c.get('part_of_figure', False)
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
            if c['player_id'] == player_id and not c.get('in_deck', False) and not c.get('part_of_figure', False)
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
                    logger.warning(f"Skipping unknown family: {family_name}")
                    continue

                family = families[family_name]

                cards = self._load_cards_from_data(figure_data['cards'])


                if not any(cards.values()):
                    logger.warning(f"Skipping figure with no valid cards: {figure_data}")
                    continue

                # Safely retrieve number_card and upgrade_card
                number_card = cards.get('number')[0] if cards.get('number') else None
                upgrade_card = cards.get('upgrade')[0] if cards.get('upgrade') else None

                # Match this figure to the correct variant in the family to get upgrade_card
                # and combat attributes that are not stored on the server Figure model.
                # Match by suit only — key-card rank matching is intentionally skipped because
                # players may use collection cards with non-standard ranks, which would cause
                # the match to fail and silently zero-out all combat attributes.
                key_cards = cards.get('key', [])
                matched_family_figure = None

                for family_figure in family.figures:
                    if family_figure.suit != figure_data['suit']:
                        continue
                    matched_family_figure = family_figure
                    if not upgrade_card:
                        upgrade_card = family_figure.upgrade_card
                    # Prefer the variant whose number-card rank exactly matches.
                    if number_card and family_figure.number_card:
                        if number_card.rank == family_figure.number_card.rank:
                            break

                # Extract combat attributes. Attributes persisted on the server Figure model
                # (cannot_be_blocked, rest_after_attack) are read directly from figure_data so
                # they remain correct even when the family-figure match is imprecise.
                # All other attributes are derived from the matched family figure.
                _mff = matched_family_figure
                cannot_attack        = getattr(_mff, 'cannot_attack', False)        if _mff else False
                must_be_attacked     = getattr(_mff, 'must_be_attacked', False)     if _mff else False
                distance_attack      = getattr(_mff, 'distance_attack', False)      if _mff else False
                buffs_allies         = getattr(_mff, 'buffs_allies', False)         if _mff else False
                buffs_allies_defence = getattr(_mff, 'buffs_allies_defence', False) if _mff else False
                blocks_bonus         = getattr(_mff, 'blocks_bonus', False)         if _mff else False
                cannot_defend        = getattr(_mff, 'cannot_defend', False)        if _mff else False
                instant_charge       = getattr(_mff, 'instant_charge', False)       if _mff else False
                cannot_be_targeted   = getattr(_mff, 'cannot_be_targeted', False)   if _mff else False
                override_base_power  = getattr(_mff, 'override_base_power', None)   if _mff else None
                # Prefer server-stored values; fall back to family definition.
                cannot_be_blocked = figure_data.get(
                    'cannot_be_blocked', getattr(_mff, 'cannot_be_blocked', False) if _mff else False)
                rest_after_attack = figure_data.get(
                    'rest_after_attack', getattr(_mff, 'rest_after_attack', False) if _mff else False)
                checkmate = figure_data.get('checkmate', False) or (
                    getattr(_mff, 'checkmate', False) if _mff else False)

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
                    is_clone=bool(figure_data.get('is_clone', False)),
                )
                if self.mode == 'conquer':
                    figure = filter_figure_for_display(
                        figure,
                        hide_instant_charge=True,
                    )
                figures.append(figure)

            # Load active enchantments for all figures
            self._load_enchantments_for_figures(figures)

            return figures
        except Exception as e:
            logger.error(f"Error loading figures: {str(e)}")
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
            logger.exception(f"Error loading enchantments: {e}")

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

    def _sync_battle_moves_phase_from_server(self):
        """Synchronize battle-move selection flags from server battle fields.

        Selection phase is authoritative when battle is confirmed but the first
        battle turn has not been assigned yet (battle_turn_player_id is None).
        In conquer mode, moves are pre-purchased — skip the selection phase.
        """
        # Conquer mode: moves are pre-purchased in the config screen.
        # However, if the player has extra hand cards (from prelude spells)
        # the client opens the battle shop and sets battle_moves_phase=True.
        # Don't overwrite that — use the server's confirmed state instead.
        if self.mode == 'conquer':
            if self.battle_confirmed and self.battle_turn_player_id is None:
                # Battle confirmed but moves not finalized — keep current
                # battle_moves_phase flag (may be True if shop is open)
                confirmed = self.battle_moves_confirmed or {}
                my_pid = str(self.player_id) if self.player_id is not None else None
                player_ids = [str(p.get('id')) for p in (self.players or []) if p.get('id') is not None]
                all_ready = bool(player_ids) and all(confirmed.get(pid) for pid in player_ids)
                if all_ready:
                    self.both_battle_moves_ready = True
                elif my_pid and confirmed.get(my_pid):
                    self.waiting_for_opponent_battle_moves = True
            elif not self.battle_confirmed:
                # No battle yet — default conquer state
                self.battle_moves_phase = False
                self.battle_moves_ready = True
                self.waiting_for_opponent_battle_moves = False
                self.both_battle_moves_ready = False
            return

        in_selection_phase = bool(
            self.battle_confirmed and
            self.battle_turn_player_id is None and
            not self.fold_outcome
        )

        if in_selection_phase:
            confirmed = self.battle_moves_confirmed or {}
            my_pid = str(self.player_id) if self.player_id is not None else None
            player_ids = [str(p.get('id')) for p in (self.players or []) if p.get('id') is not None]
            all_ready = bool(player_ids) and all(confirmed.get(pid) for pid in player_ids)
            self.battle_moves_phase = True
            self.battle_moves_ready = bool(my_pid and confirmed.get(my_pid))
            self.waiting_for_opponent_battle_moves = bool(self.battle_moves_ready and not all_ready)
            self.both_battle_moves_ready = False
            return

        # Outside selection phase, clear local waiting flags.
        self.battle_moves_phase = False
        self.battle_moves_ready = False
        self.waiting_for_opponent_battle_moves = False
        if not self.battle_confirmed:
            self.both_battle_moves_ready = False

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

    def landslide_active(self) -> bool:
        """True when a Landslide battle modifier inverts the land bonus."""
        modifiers = self.battle_modifier if isinstance(self.battle_modifier, list) else []
        return any(
            isinstance(m, dict) and m.get('type') == 'Landslide'
            for m in modifiers
        )

    def effective_land_bonus(self):
        """Return ``(suit, value)`` of the land bonus after battle modifiers.

        Landslide inverts the bonus for the whole battle: figures matching
        the land suit get ``-value`` instead of ``+value`` (both sides).
        Returns ``(None, 0)`` when the game has no land bonus.
        """
        suit = getattr(self, 'land_suit_bonus_suit', None)
        value = getattr(self, 'land_suit_bonus_value', None)
        if not suit or not value:
            return None, 0
        value = int(value)
        if self.landslide_active():
            return suit, -abs(value)
        return suit, value

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
        
        logger.debug(f"Calculating resources for {len(figures)} figures")

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
        
        if excluded:
            logger.debug(f"Resource deficit: excluded={[figures[i].name for i in excluded]}, "
                         f"produces={total_produces}, requires={total_requires}")
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
                logger.error(f"Skipping card with missing data: {card_data}, Error: {e}")
                continue

        return cards


    def update_logs(self):
        """Fetch and update log entries."""
        try:
            self.log_entries = fetch_log_entries(self.game_id)
        except Exception as e:
            logger.error(f"Failed to fetch log entries: {str(e)}")

    def add_log_entry(self, round_number, turn_number, message, author, entry_type):
        """Add a log entry and update the log list."""
        try:
            add_log_entry(self.game_id, self.player_id, round_number, turn_number, message, author, entry_type)
            self.update_logs()
        except Exception as e:
            logger.error(f"Failed to add log entry: {str(e)}")

    def update_chats(self):
        """Fetch and update chat messages."""
        try:
            self.chat_messages = fetch_chat_messages(self.game_id)
        except Exception as e:
            logger.error(f"Failed to fetch chat messages: {str(e)}")

    def send_chat_message(self, receiver_id, message):
        """Send a chat message and update the chat list."""
        try:
            send_chat_message(self.game_id, self.player_id, receiver_id, message)
            self.update_chats()
        except Exception as e:
            logger.error(f"Failed to send chat message: {str(e)}")


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
                logger.error(f"Failed to change {card_type} cards: {response.json().get('message', 'Unknown error')}")
                return []

            # Update the game state after a successful response
            new_cards = response.json().get('new_cards', [])

            self.update()

            return new_cards
        except Exception as e:
            logger.error(f"An error occurred while changing {card_type} cards: {str(e)}")
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
                logger.error(f"Failed to discard {card_type} cards: {response.json().get('message', 'Unknown error')}")
                return False

            # Log the card discard action
            round_number = self.current_round
            turn_number = self.current_player.get('turns_left', 0)
            message = f"{self.current_player.get('username', 'Player')} discarded {len(cards)} {card_type} card(s)."
            self.add_log_entry(round_number, turn_number, message, self.current_player.get('username', 'Player'), 'card_discard')

            self.update()

            return True
        except Exception as e:
            logger.error(f"An error occurred while discarding {card_type} cards: {str(e)}")
            return False
