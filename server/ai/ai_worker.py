# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""
AI Worker — event-driven background AI player.

When a game state change puts an AI player in a position where they need
to act, `trigger_ai_if_needed(game_id)` spawns a short-lived daemon thread
that reads the game state, consults the LLM, and executes the chosen action.
"""
import threading
import time
import logging
import random
import re
import requests as http_requests

import server_settings as settings
from ai import get_ai_auth_headers
from ai.llm_client import LLMClient, parse_action_response
from ai.game_state import enrich_figures_with_skills, serialize_game_for_llm
from ai.action_enum import detect_phase, enumerate_actions, format_actions_for_llm
from ai.card_change_strategy import select_main_cards_to_swap, summarize_main_change
from ai.strategy_planner import (
    format_strategy_plans_for_prompt,
    generate_strategy_plans,
    recommended_action_id,
)
from ai.prompts import SYSTEM_PROMPT, PHASE_PROMPTS

logger = logging.getLogger('nepalkings.ai.worker')

_AI_INTERNAL_REQUEST_HEADER = 'X-NepalKings-AI-Internal'

# Global LLM client (lazy-initialized)
_llm_client = None
# Cache mapping AI player IDs to AI user IDs so auth headers can be built
# from worker threads without touching the Flask-bound DB session.
_ai_player_user_ids = {}
_ai_player_user_ids_lock = threading.Lock()
# Watchdog retry budget per game when AI loop exits unsuccessfully
_ai_watchdog_retries = {}
_ai_watchdog_lock = threading.Lock()
# Lock to prevent multiple AI threads for the same game
_active_games = set()
_active_games_lock = threading.Lock()
_pending_retrigger = set()  # Games that need rechecking after current loop
# Per-game strategy memory — persists across LLM calls within a game
_game_strategies = {}  # game_id → list of strategy notes
_game_strategies_lock = threading.Lock()
# Per-game planner telemetry events for debugging/rollout visibility
_planner_events = {}  # game_id -> [event, ...]
_planner_events_lock = threading.Lock()
# Keep event buffers bounded to prevent memory growth.
_MAX_PLANNER_EVENTS_PER_GAME = 80
# Per-game chat cadence state for AI flavor messages
_ai_chat_states = {}  # game_id -> {'count': int, 'last_sent_at': float, 'last_turn_marker': tuple}
# Per-game tactical explain preferences configured via chat commands.
_ai_explain_states = {}  # game_id -> {'mode': str, 'depth': str, 'last_marker': tuple | None}
_ai_chat_lock = threading.Lock()

# Phase-specific LLM temperatures — lower = more deterministic for math-heavy decisions
PHASE_TEMPERATURES = {
    'normal_turn': 0.25,      # Lower variance for better strategic discipline
    'select_defender': 0.3,   # Target evaluation
    'battle_decision': 0.2,   # Pure math: fold vs battle
    'battle_shop': 0.3,       # Card evaluation + combinatorics
    'battle_round': 0.2,      # Move sequencing — deterministic
    'counter_spell': 0.2,     # Cost-benefit analysis
    'post_battle_pick': 0.2,  # Card value ranking
    'post_battle_draw': 0.1,  # Almost always "destroy opponent's"
}

AI_CHAT_SYSTEM_PROMPT = (
    "You are [AI] Strategos in the game Nepal Kings. "
    "Write exactly one short in-character chat line. "
    "Return only plain message text, with no JSON, no markdown, no labels, and no explanations."
)

_AI_EXPLAIN_DEFAULT_MODE = 'off'
_AI_EXPLAIN_DEFAULT_DEPTH = 'standard'

_AI_EXPLAIN_MODE_ALIASES = {
    'off': 'off',
    'disable': 'off',
    'disabled': 'off',
    'stop': 'off',
    'manual': 'manual',
    'ondemand': 'manual',
    'on_demand': 'manual',
    'turn': 'turn',
    'turns': 'turn',
    'battle': 'battle',
    'combat': 'battle',
}

_AI_EXPLAIN_DEPTH_ALIASES = {
    'brief': 'brief',
    'short': 'brief',
    'quick': 'brief',
    'standard': 'standard',
    'normal': 'standard',
    'default': 'standard',
    'detailed': 'detailed',
    'detail': 'detailed',
    'deep': 'detailed',
    'extensive': 'extensive',
    'verbose': 'extensive',
    'full': 'extensive',
}


def _get_llm_client():
    """Get or create the shared LLM client instance."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient(
            provider=settings.AI_PROVIDER,
            model=settings.AI_MODEL,
            api_key=settings.AI_OPENAI_API_KEY,
        )
    return _llm_client


def _record_planner_event(game_id, event_type, payload=None):
    """Append a bounded planner telemetry event for a game."""
    if not game_id:
        return

    event = {
        'timestamp': round(time.time(), 3),
        'type': str(event_type),
    }
    if isinstance(payload, dict):
        event.update(payload)

    with _planner_events_lock:
        if game_id not in _planner_events:
            _planner_events[game_id] = []
        _planner_events[game_id].append(event)
        if len(_planner_events[game_id]) > _MAX_PLANNER_EVENTS_PER_GAME:
            _planner_events[game_id] = _planner_events[game_id][-_MAX_PLANNER_EVENTS_PER_GAME:]


def _planner_candidate_summaries(plans, actions, max_candidates=5):
    """Return JSON-safe candidate summaries for telemetry events.

    Includes compact headline fields and verbose plan details so operators can
    inspect full candidate content via debug tooling when needed.
    """
    if not plans:
        return []

    try:
        max_candidates = max(1, min(int(max_candidates), 20))
    except (TypeError, ValueError):
        max_candidates = 5

    def _clip(text, max_len=140):
        msg = str(text or '').replace('\n', ' ').replace('\r', ' ')
        msg = ' '.join(msg.split())
        if len(msg) <= max_len:
            return msg
        return msg[: max_len - 3] + '...'

    action_by_id = {}
    for action in actions or []:
        try:
            aid = int(action.get('id'))
        except (TypeError, ValueError):
            continue
        action_by_id[aid] = action

    summaries = []
    for plan in (plans or [])[:max_candidates]:
        raw_action_id = plan.get('seed_action_id')
        try:
            seed_action_id = int(raw_action_id)
        except (TypeError, ValueError):
            seed_action_id = raw_action_id

        matched_action = action_by_id.get(seed_action_id) if isinstance(seed_action_id, int) else None
        steps = plan.get('turn_steps') or []
        step_preview = _clip(' | '.join(str(s) for s in steps[:2]), 180)
        planned_moves = plan.get('planned_battle_moves') or []
        if not isinstance(planned_moves, list):
            planned_moves = []

        planned_figure = plan.get('planned_battle_figure')
        if not isinstance(planned_figure, dict):
            planned_figure = None

        likely_opp = plan.get('likely_opponent_figure')
        if not isinstance(likely_opp, dict):
            likely_opp = None

        score_breakdown = plan.get('score_breakdown') or {}
        if not isinstance(score_breakdown, dict):
            score_breakdown = {}

        notes = plan.get('notes') or []
        if not isinstance(notes, list):
            notes = []

        summaries.append(
            {
                'plan_id': plan.get('plan_id'),
                'seed_action_id': seed_action_id,
                'strategy_name': plan.get('strategy_name'),
                'action_type': (matched_action or {}).get('type'),
                'action_description': _clip((matched_action or {}).get('description'), 120),
                'total_score': plan.get('total_score'),
                'feasibility_probability': plan.get('feasibility_probability'),
                'expected_power_diff': plan.get('expected_power_diff'),
                'expected_battle_move_power': plan.get('expected_battle_move_power'),
                'step_preview': step_preview,
                'turn_steps': [str(s) for s in steps],
                'planned_battle_moves': planned_moves,
                'planned_battle_figure': planned_figure,
                'likely_opponent_figure': likely_opp,
                'score_breakdown': score_breakdown,
                'notes': [str(n) for n in notes],
            }
        )

    return summaries


def get_ai_debug_snapshot(game_id, max_notes=20, max_events=40):
    """Return in-memory AI reasoning and planner telemetry for a game.

    Used by rollout diagnostics routes. Data is ephemeral and cleared after game
    completion or server restart.
    """
    try:
        max_notes = max(1, min(int(max_notes), 200))
    except (TypeError, ValueError):
        max_notes = 20

    try:
        max_events = max(1, min(int(max_events), 200))
    except (TypeError, ValueError):
        max_events = 40

    with _game_strategies_lock:
        notes = list(_game_strategies.get(game_id, []))[-max_notes:]
    with _planner_events_lock:
        events = list(_planner_events.get(game_id, []))[-max_events:]

    return {
        'strategy_notes': notes,
        'planner_events': events,
    }


def _ai_headers(ai_player_id):
    """Return auth headers for requests made on behalf of an AI player."""
    with _ai_player_user_ids_lock:
        ai_user_id = _ai_player_user_ids.get(ai_player_id)
    if ai_user_id is None:
        logger.warning(f"Missing AI user mapping for player_id={ai_player_id}")
        return {}
    return get_ai_auth_headers(ai_user_id)


def _clear_watchdog_retry(game_id):
    """Reset watchdog retry counter for a game."""
    with _ai_watchdog_lock:
        _ai_watchdog_retries.pop(game_id, None)


def _schedule_watchdog_retry(app, game_id, ai_player_id, reason):
    """Schedule a delayed AI retrigger when a loop exits unsuccessfully."""
    max_retries = max(int(settings.AI_WATCHDOG_MAX_RETRIES), 0)
    delay_seconds = max(float(settings.AI_WATCHDOG_RETRY_DELAY), 0.0)

    with _ai_watchdog_lock:
        attempt = _ai_watchdog_retries.get(game_id, 0) + 1
        if attempt > max_retries:
            logger.error(
                f"AI watchdog exhausted for game {game_id} "
                f"after {max_retries} retries (reason={reason})"
            )
            return
        _ai_watchdog_retries[game_id] = attempt

    def _retry():
        try:
            if delay_seconds > 0:
                time.sleep(delay_seconds)

            with app.app_context():
                from models import Game, db
                game = db.session.get(Game, game_id)
                if not game or game.state == 'finished':
                    _clear_watchdog_retry(game_id)
                    return

                game_dict = enrich_figures_with_skills(game.serialize())
                phase = detect_phase(game_dict, ai_player_id)
                if not phase:
                    _clear_watchdog_retry(game_id)
                    return

                logger.warning(
                    f"AI watchdog retry {attempt}/{max_retries} for game {game_id} "
                    f"(reason={reason}, phase={phase})"
                )
                trigger_ai_if_needed(game_id, app=app)
        except Exception as e:
            logger.error(f"AI watchdog retry crashed for game {game_id}: {e}", exc_info=True)

    threading.Thread(
        target=_retry,
        daemon=True,
        name=f"ai-watchdog-{game_id}-{attempt}",
    ).start()


def _ai_post(url, ai_player_id, **kwargs):
    """POST with AI authentication headers. Defaults timeout to 15s."""
    kwargs.setdefault('timeout', 15)
    headers = kwargs.pop('headers', {}) or {}
    headers.update(_ai_headers(ai_player_id))
    headers[_AI_INTERNAL_REQUEST_HEADER] = '1'
    return http_requests.post(url, headers=headers, **kwargs)


def trigger_ai_if_needed(game_id, app=None):
    """
    Check if an AI player needs to act in this game, and if so,
    spawn a background thread to handle it.
    
    Called at the end of state-mutating route handlers.
    This function returns immediately — the AI work happens asynchronously.
    """
    if not settings.AI_ENABLED:
        return
    
    if not settings.AI_OPENAI_API_KEY:
        logger.info(f"AI trigger skipped for game {game_id}: no API key")
        return

    # Import here to avoid circular imports
    from models import Game, User, db
    
    # Quick check: does this game have an AI player who needs to act?
    game = db.session.get(Game, game_id)
    if not game or game.state == 'finished':
        return
    
    ai_player = None
    for player in game.players:
        user = db.session.get(User, player.user_id)
        if user and user.is_ai:
            ai_player = player
            break
    
    if not ai_player:
        return

    # Cache player->user mapping for auth headers used by background thread.
    with _ai_player_user_ids_lock:
        _ai_player_user_ids[ai_player.id] = ai_player.user_id
    
    # Check if the AI actually needs to act right now
    game_dict = enrich_figures_with_skills(game.serialize())
    if not game_dict:
        logger.warning(f"AI trigger: game.serialize() returned None/empty for game {game_id}")
        return
    try:
        phase = detect_phase(game_dict, ai_player.id)
    except Exception as e:
        logger.error(f"AI trigger: detect_phase crashed for game {game_id}: {e}", exc_info=True)
        return
    if not phase:
        logger.info(f"AI trigger for game {game_id}: no action needed "
                     f"(turn={game_dict.get('turn_player_id')}, ai={ai_player.id})")
        return
    
    # Avoid spawning duplicate threads for the same game
    with _active_games_lock:
        if game_id in _active_games:
            _pending_retrigger.add(game_id)
            logger.info(f"AI trigger for game {game_id}: thread active, marked retrigger")
            return
        _active_games.add(game_id)
    
    # Get the Flask app for context (needed in background thread)
    if app is None:
        from flask import current_app
        try:
            app = current_app._get_current_object()
        except RuntimeError:
            logger.error("No Flask app context available for AI thread")
            with _active_games_lock:
                _active_games.discard(game_id)
            return
    
    # Spawn background thread
    thread = threading.Thread(
        target=_ai_game_loop,
        args=(app, game_id, ai_player.id),
        daemon=True,
        name=f"ai-game-{game_id}",
    )
    thread.start()
    logger.info(f"AI thread spawned for game {game_id}, phase={phase}")


def _ai_game_loop(app, game_id, ai_player_id):
    """
    Main AI loop. Runs in a background thread.
    Keeps acting as long as it's the AI's turn (handles multi-step phases like battle shop).
    """
    try:
        time.sleep(settings.AI_THINK_DELAY)
        
        max_iterations = 20  # Safety limit to prevent infinite loops
        iteration = 0
        called_start_turn = False
        consecutive_normal_turns = 0  # Track Infinite Hammer multi-build sequences
        unsuccessful_exit = False
        
        while iteration < max_iterations:
            iteration += 1
            
            with app.app_context():
                from models import Game, db
                game = db.session.get(Game, game_id)
                if not game or game.state == 'finished':
                    logger.info(f"AI loop exit: game {game_id} is finished/gone")
                    _clear_watchdog_retry(game_id)
                    # Clean up strategy memory for finished games
                    with _game_strategies_lock:
                        _game_strategies.pop(game_id, None)
                    with _planner_events_lock:
                        _planner_events.pop(game_id, None)
                    with _ai_chat_lock:
                        _ai_chat_states.pop(game_id, None)
                        _ai_explain_states.pop(game_id, None)
                    break
                
                game_dict = enrich_figures_with_skills(game.serialize())
            
            phase = detect_phase(game_dict, ai_player_id)
            if not phase:
                # Check if a concurrent request marked us for retrigger
                with _active_games_lock:
                    if game_id in _pending_retrigger:
                        _pending_retrigger.discard(game_id)
                        logger.info(f"AI retrigger received for game {game_id}, continuing")
                        time.sleep(1)
                        called_start_turn = False
                        continue
                # Wait briefly and recheck — handles race where opponent's POST
                # flips the turn while we're winding down
                time.sleep(3)
                with app.app_context():
                    from models import Game, db
                    game = db.session.get(Game, game_id)
                    if game and game.state != 'finished':
                        game_dict = enrich_figures_with_skills(game.serialize())
                        phase = detect_phase(game_dict, ai_player_id)
                if phase:
                    logger.info(f"AI detected deferred action in game {game_id}, phase={phase}")
                    called_start_turn = False
                    continue
                # Final retrigger check after the wait
                with _active_games_lock:
                    if game_id in _pending_retrigger:
                        _pending_retrigger.discard(game_id)
                        logger.info(f"AI retrigger (post-wait) for game {game_id}")
                        called_start_turn = False
                        continue
                logger.info(f"AI loop exit: no action needed in game {game_id}")
                _clear_watchdog_retry(game_id)
                break
            
            logger.info(f"AI acting in game {game_id}: phase={phase}, iteration={iteration}")
            
            # Call start_turn once at the beginning of AI's turn (auto-fills cards)
            if phase == 'normal_turn' and not called_start_turn:
                _exec_start_turn(settings.SERVER_URL, game_id, ai_player_id)
                called_start_turn = True
                # Re-fetch game state after start_turn (cards may have been filled)
                with app.app_context():
                    from models import Game, db
                    game = db.session.get(Game, game_id)
                    if not game or game.state == 'finished':
                        _clear_watchdog_retry(game_id)
                        break
                    game_dict = enrich_figures_with_skills(game.serialize())
                phase = detect_phase(game_dict, ai_player_id)
                if not phase:
                    _clear_watchdog_retry(game_id)
                    break
            
            # Handle finish_battle phase (calculate total_diff, call endpoint)
            if phase == 'finish_battle':
                result = _handle_finish_battle(app, game_id, ai_player_id, game_dict)
                if result:
                    # After finish_battle, check if we need to pick a card or handle draw
                    time.sleep(1)
                    continue  # Loop will detect post_battle_pick or exit
                unsuccessful_exit = True
                break
            
            # Handle post_battle_pick (winner picks a card)
            if phase == 'post_battle_pick':
                _handle_post_battle_pick(app, game_id, ai_player_id)
                _clear_watchdog_retry(game_id)
                break  # After picking, new round starts — turn might be ours or opponent's
            
            # Enumerate legal actions (needs app context for DB queries, e.g. counter_spell)
            with app.app_context():
                actions = enumerate_actions(game_dict, ai_player_id, phase)
            if not actions:
                logger.warning(f"AI has no actions in phase {phase} for game {game_id}")
                unsuccessful_exit = True
                break
            
            # If only one action, take it without LLM
            if len(actions) == 1:
                chosen = actions[0]
                logger.info(f"AI auto-choosing only action: {chosen['type']}")
                _update_strategy_memory(game_id, chosen, phase)
            else:
                # Ask LLM
                chosen = _ask_llm_for_action(game_dict, ai_player_id, phase, actions)
            
            # Execute the chosen action
            success = _execute_action(app, game_id, ai_player_id, chosen)
            if not success:
                logger.warning(f"AI action failed: {chosen['type']} in game {game_id}")
                # Try other actions of the same type (e.g., next defender target)
                fallback_success = False
                for alt in actions:
                    if alt['id'] != chosen['id'] and alt['type'] == chosen['type']:
                        logger.info(f"AI trying alternative: {alt['type']} — {alt['description'][:60]}")
                        if _execute_action(app, game_id, ai_player_id, alt):
                            fallback_success = True
                            break
                if not fallback_success and chosen['type'] == 'build_figure':
                    fallback = next((a for a in actions if a['type'] == 'change_cards'), None)
                    if fallback:
                        logger.info("AI falling back to change_cards")
                        _execute_action(app, game_id, ai_player_id, fallback)
                # If confirm_battle_moves failed, try buying more moves to reach 3
                if not fallback_success and chosen['type'] == 'confirm_battle_moves':
                    # In battle_shop phase, only buy/confirm/combine are valid.
                    buy_action = next((a for a in actions if a['type'] == 'buy_battle_move'), None)
                    if buy_action:
                        logger.info("AI confirm failed, falling back to buy_battle_move")
                        fallback_success = _execute_action(app, game_id, ai_player_id, buy_action)
                if not fallback_success:
                    unsuccessful_exit = True
                    break
                # Fallback action succeeded — continue loop
                time.sleep(settings.AI_THINK_DELAY)
                continue

            _clear_watchdog_retry(game_id)

            # Optional flavor chat: generated by LLM from sanitized context only
            # (human chat excluded), with safe template fallback.
            _maybe_send_ai_chat(game_id, ai_player_id, game_dict, phase, chosen)
            
            # Track consecutive normal_turn actions (indicates Infinite Hammer mode)
            if phase == 'normal_turn':
                consecutive_normal_turns += 1
            else:
                consecutive_normal_turns = 0

            # Small delay between consecutive actions (battle shop: buy → buy → confirm)
            if phase in ('battle_shop',):
                time.sleep(1)
            elif consecutive_normal_turns > 1:
                # Infinite Hammer: longer delay to avoid saturating PythonAnywhere's
                # limited web workers with AI self-calls
                time.sleep(settings.AI_THINK_DELAY + 3)
            else:
                time.sleep(settings.AI_THINK_DELAY)
    
    except Exception as e:
        unsuccessful_exit = True
        logger.error(f"AI thread error for game {game_id}: {e}", exc_info=True)
    finally:
        retrigger = False
        with _active_games_lock:
            _active_games.discard(game_id)
            if game_id in _pending_retrigger:
                _pending_retrigger.discard(game_id)
                retrigger = True
        if retrigger:
            logger.info(f"Processing pending retrigger for game {game_id} after thread exit")
            with app.app_context():
                trigger_ai_if_needed(game_id, app=app)
        elif unsuccessful_exit:
            try:
                with app.app_context():
                    from models import Game, db
                    game = db.session.get(Game, game_id)
                    if not game or game.state == 'finished':
                        _clear_watchdog_retry(game_id)
                    else:
                        game_dict = enrich_figures_with_skills(game.serialize())
                        phase = detect_phase(game_dict, ai_player_id)
                        if phase and game_dict.get('turn_player_id') == ai_player_id:
                            _schedule_watchdog_retry(app, game_id, ai_player_id, reason='loop_failure')
                        else:
                            _clear_watchdog_retry(game_id)
            except Exception as e:
                logger.error(f"Failed to schedule AI watchdog for game {game_id}: {e}", exc_info=True)
        else:
            _clear_watchdog_retry(game_id)


def _get_game_log_digest(game_dict, ai_player_id, max_entries=15):
    """Extract recent game log entries for turn history context."""
    entries = game_dict.get('log_entries', [])
    if not entries:
        return ""
    # Take the most recent entries
    recent = entries[-max_entries:]
    lines = ["\n=== RECENT GAME LOG ==="]
    for e in recent:
        msg = _compress_text(e.get('message', ''), 160)
        rnd = e.get('round_number', '?')
        lines.append(f"  R{rnd}: {msg}")
    return '\n'.join(lines)


def _get_strategy_memory(game_id):
    """Get accumulated strategy notes for this game."""
    with _game_strategies_lock:
        notes = _game_strategies.get(game_id, [])
        if not notes:
            return ""
        lines = ["\n=== YOUR STRATEGY NOTES (from previous turns) ==="]
        # Highlight the most recent forward plan
        for n in reversed(notes):
            if '| PLAN:' in n:
                plan = n.split('| PLAN:', 1)[1].strip()
                lines.append(f"  📋 CURRENT PLAN: {plan}")
                break
        lines.extend(f"  - {n}" for n in notes[-8:])
        return '\n'.join(lines)


def _update_strategy_memory(game_id, action, phase, plan=None):
    """Record a brief strategy note about what the AI just did."""
    note = f"{phase}: chose {action.get('type', '?')} — {action.get('description', '')[:80]}"
    if plan:
        note += f" | PLAN: {plan}"
    with _game_strategies_lock:
        if game_id not in _game_strategies:
            _game_strategies[game_id] = []
        _game_strategies[game_id].append(note)
        # Keep only last 20 notes to prevent unbounded growth
        if len(_game_strategies[game_id]) > 20:
            _game_strategies[game_id] = _game_strategies[game_id][-20:]


def _compress_text(text, max_len=180):
    """Normalize whitespace and cap text length for compact prompts/messages."""
    msg = str(text or '').replace('\n', ' ').replace('\r', ' ')
    msg = ' '.join(msg.split())
    if len(msg) <= max_len:
        return msg
    return msg[:max_len - 3] + '...'


def _default_explain_state():
    """Return default explain settings for a game."""
    return {
        'mode': _AI_EXPLAIN_DEFAULT_MODE,
        'depth': _AI_EXPLAIN_DEFAULT_DEPTH,
        'last_marker': None,
    }


def _get_explain_state(game_id):
    """Read explain settings for a game, initializing defaults if needed."""
    with _ai_chat_lock:
        state = _ai_explain_states.get(game_id)
        if not isinstance(state, dict):
            state = _default_explain_state()
            _ai_explain_states[game_id] = state
        return dict(state)


def _is_help_only_chat_request(lowered, tokens):
    """Return whether a plain chat help message should trigger AI command help."""
    raw = str(lowered or '').strip()
    normalized = ' '.join(tokens or [])

    if raw in {'?', '/help'}:
        return True

    single_words = {'help', 'commands', 'command', 'manual', 'cmds', 'aihelp'}
    if len(tokens) == 1 and (tokens[0] in single_words):
        return True

    short_phrases = {
        'ai help',
        'help ai',
        'bot help',
        'help bot',
        'ai commands',
        'commands ai',
        'strategos help',
        'help strategos',
    }
    return normalized in short_phrases


def _parse_explain_chat_directive(message):
    """Parse explain-mode command phrases from player chat text."""
    text = str(message or '').strip()
    lowered = text.lower()
    tokens = re.findall(r'[a-z0-9_]+', lowered)

    is_explain = 'explain' in lowered or 'analysis mode' in lowered
    help_only = _is_help_only_chat_request(lowered, tokens)

    if not is_explain and not help_only:
        return {
            'is_explain': False,
            'mode': None,
            'depth': None,
            'manual_request': False,
            'help_requested': False,
            'help_only': False,
        }

    mode = None
    depth = None

    for idx, token in enumerate(tokens):
        if token == 'mode' and idx + 1 < len(tokens):
            mode = _AI_EXPLAIN_MODE_ALIASES.get(tokens[idx + 1], mode)
        elif token in _AI_EXPLAIN_MODE_ALIASES:
            mode = _AI_EXPLAIN_MODE_ALIASES[token]

        if token == 'depth' and idx + 1 < len(tokens):
            depth = _AI_EXPLAIN_DEPTH_ALIASES.get(tokens[idx + 1], depth)
        elif token in _AI_EXPLAIN_DEPTH_ALIASES:
            depth = _AI_EXPLAIN_DEPTH_ALIASES[token]

    explicit_manual = (
        'explain yourself' in lowered
        or 'why did' in lowered
        or 'why you' in lowered
        or 'thinking' in tokens
        or 'reason' in tokens
        or 'reasons' in tokens
        or 'now' in tokens
    )
    help_requested = ('help' in tokens) or ('commands' in tokens) or bool(help_only)
    config_only = (mode is not None) or (depth is not None)
    manual_request = explicit_manual or (is_explain and not config_only and not help_requested)

    return {
        'is_explain': True,
        'mode': mode,
        'depth': depth,
        'manual_request': bool(manual_request),
        'help_requested': bool(help_requested),
        'help_only': bool(help_only),
    }


def _fmt_number(value, digits=2):
    """Format numeric planner values safely for chat output."""
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return 'n/a'


def _fmt_probability(value):
    """Format probability-like values as percentages."""
    try:
        return f"{float(value) * 100.0:.0f}%"
    except (TypeError, ValueError):
        return 'n/a'


def _latest_candidate_event(events):
    """Return newest planner event that contains candidate summaries."""
    for event in reversed(events or []):
        if not isinstance(event, dict):
            continue
        candidates = event.get('candidates')
        if isinstance(candidates, list) and candidates:
            return event, candidates
    return None, []


def _latest_planner_choice_event(events):
    """Return newest planner_choice event, if present."""
    for event in reversed(events or []):
        if not isinstance(event, dict):
            continue
        if event.get('type') == 'planner_choice':
            return event
    return None


def _candidate_action_label(candidate):
    """Return a readable action label for candidate summaries."""
    label = _compress_text(candidate.get('action_description', ''), 120)
    if label:
        return label

    action_type = str(candidate.get('action_type') or '').strip()
    if action_type:
        return action_type.replace('_', ' ')

    action_id = candidate.get('seed_action_id')
    return f"action {action_id}" if action_id is not None else 'unknown action'


def _candidate_sequence(candidate, max_steps=3):
    """Render a compact turn-sequence preview for one plan candidate."""
    steps = [str(s) for s in (candidate.get('turn_steps') or []) if str(s).strip()]
    if steps:
        return _compress_text(' -> '.join(steps[:max_steps]), 220)

    preview = _compress_text(candidate.get('step_preview', ''), 220)
    if preview:
        return preview
    return 'no sequence available'


def _candidate_move_preview(candidate, max_moves=3):
    """Render compact planned battle-move snippets for explanation text."""
    moves = candidate.get('planned_battle_moves')
    if not isinstance(moves, list) or not moves:
        return ''

    rendered = []
    for move in moves[:max_moves]:
        if not isinstance(move, dict):
            continue
        rank = str(move.get('rank') or '?')
        suit = str(move.get('suit') or '')
        value = move.get('value')
        short = suit[:1].upper() if suit else ''
        rendered.append(f"{rank}{short}({_fmt_number(value, 0)})")

    return ', '.join(rendered)


def _build_tactical_explain_messages(game_id, depth='standard', reason='manual'):
    """Build one or more tactical explanation messages from planner telemetry."""
    depth_key = _AI_EXPLAIN_DEPTH_ALIASES.get(str(depth or '').lower(), _AI_EXPLAIN_DEFAULT_DEPTH)
    snapshot = get_ai_debug_snapshot(game_id, max_notes=8, max_events=80)
    notes = list(snapshot.get('strategy_notes') or [])
    events = list(snapshot.get('planner_events') or [])

    _, candidates = _latest_candidate_event(events)
    if not candidates:
        if notes:
            return [_compress_text(f"Tactical explain ({reason}): {notes[-1]}", 980)]
        return [
            "Tactical explain: I do not have planner candidates yet. "
            "Ask again right after my next decision."
        ]

    choice_event = _latest_planner_choice_event(events)
    top = candidates[0]

    top_line = _candidate_action_label(top)
    top_score = _fmt_number(top.get('total_score'), 2)
    top_feas = _fmt_probability(top.get('feasibility_probability'))
    top_diff = _fmt_number(top.get('expected_power_diff'), 1)
    sequence = _candidate_sequence(top, max_steps=3)

    summary = (
        f"Tactical explain ({reason}, {depth_key}): top line is {top_line} "
        f"(score={top_score}, feasibility={top_feas}, expected_power_diff={top_diff}). "
        f"Sequence: {sequence}."
    )

    if isinstance(choice_event, dict):
        rec_action_id = choice_event.get('recommended_action_id')
        chosen_action_id = choice_event.get('chosen_action_id')
        match = choice_event.get('chosen_matches_recommended')
        if rec_action_id is not None and chosen_action_id is not None:
            match_text = '' if match is None else f", match={bool(match)}"
            summary += (
                f" Planner recommendation={rec_action_id}, "
                f"executed={chosen_action_id}{match_text}."
            )

    messages = [_compress_text(summary, 980)]
    if depth_key == 'brief':
        return messages

    detail_bits = []
    planned_figure = top.get('planned_battle_figure')
    if isinstance(planned_figure, dict) and planned_figure:
        detail_bits.append(
            "Target figure: "
            f"{planned_figure.get('name')} "
            f"({planned_figure.get('field')}, state={planned_figure.get('state')}, "
            f"power~{_fmt_number(planned_figure.get('power_estimate'), 1)})."
        )

    planned_moves = _candidate_move_preview(top)
    if planned_moves:
        detail_bits.append(f"Planned battle moves: {planned_moves}.")

    score_breakdown = top.get('score_breakdown')
    if isinstance(score_breakdown, dict) and score_breakdown:
        pairs = []
        for key, value in list(score_breakdown.items())[:5]:
            pairs.append(f"{key}={_fmt_number(value, 2)}")
        detail_bits.append(f"Score factors: {', '.join(pairs)}.")

    notes_text = top.get('notes')
    if isinstance(notes_text, list) and notes_text:
        detail_bits.append(f"Planner notes: {'; '.join(str(n) for n in notes_text[:2])}.")

    if detail_bits:
        messages.append(_compress_text(' '.join(detail_bits), 980))

    if depth_key == 'detailed':
        alternates = []
        for idx, candidate in enumerate(candidates[1:3], start=2):
            alternates.append(
                f"Alt {idx}: {_candidate_action_label(candidate)} "
                f"(score={_fmt_number(candidate.get('total_score'), 2)}, "
                f"feasibility={_fmt_probability(candidate.get('feasibility_probability'))}), "
                f"seq={_candidate_sequence(candidate, max_steps=2)}."
            )
        if alternates:
            messages.append(_compress_text(' '.join(alternates), 980))
        return messages

    if depth_key == 'extensive':
        messages = messages[:1]
        for idx, candidate in enumerate(candidates[:3], start=1):
            candidate_line = (
                f"Candidate {idx}: {_candidate_action_label(candidate)}; "
                f"score={_fmt_number(candidate.get('total_score'), 2)}; "
                f"feasibility={_fmt_probability(candidate.get('feasibility_probability'))}; "
                f"expected_power_diff={_fmt_number(candidate.get('expected_power_diff'), 1)}; "
                f"sequence={_candidate_sequence(candidate, max_steps=4)}"
            )

            fig = candidate.get('planned_battle_figure')
            if isinstance(fig, dict) and fig:
                candidate_line += (
                    f"; target={fig.get('name')}({fig.get('field')}, "
                    f"state={fig.get('state')}, power~{_fmt_number(fig.get('power_estimate'), 1)})"
                )

            move_preview = _candidate_move_preview(candidate)
            if move_preview:
                candidate_line += f"; moves={move_preview}"

            notes_list = candidate.get('notes')
            if isinstance(notes_list, list) and notes_list:
                candidate_line += f"; note={_compress_text(notes_list[0], 140)}"

            messages.append(_compress_text(candidate_line + '.', 980))

    return messages


def _format_explain_settings_message(state, changed_mode=False, changed_depth=False):
    """Build confirmation/status chat text for explain setting changes."""
    mode = str(state.get('mode') or _AI_EXPLAIN_DEFAULT_MODE)
    depth = str(state.get('depth') or _AI_EXPLAIN_DEFAULT_DEPTH)
    cadence_hint = {
        'off': 'Automatic tactical explanations are disabled.',
        'manual': 'I will explain only when explicitly asked.',
        'turn': 'I will explain on my normal-turn decisions.',
        'battle': 'I will explain during battle phases.',
    }.get(mode, 'Explain cadence is active.')

    prefix = 'Explain settings updated.' if (changed_mode or changed_depth) else 'Explain settings.'
    return _compress_text(f"{prefix} cadence={mode}, depth={depth}. {cadence_hint}", 980)


def _format_explain_help_message(state):
    """Build short chat-friendly manual for AI explain commands."""
    mode = str((state or {}).get('mode') or _AI_EXPLAIN_DEFAULT_MODE)
    depth = str((state or {}).get('depth') or _AI_EXPLAIN_DEFAULT_DEPTH)
    return _compress_text(
        "AI explain help: 'explain yourself' (one-time reason), "
        "'explain mode off/manual/turn/battle', "
        "'explain depth brief/standard/detailed/extensive'. "
        f"Current: cadence={mode}, depth={depth}.",
        980,
    )


def handle_explain_chat_control(game_id, ai_player_id, human_player_id, message):
    """Handle human explain-mode chat commands and return AI reply lines."""
    _ = (ai_player_id, human_player_id)
    parsed = _parse_explain_chat_directive(message)
    if not parsed.get('is_explain'):
        return []

    current = _get_explain_state(game_id)
    next_state = dict(current)

    requested_mode = parsed.get('mode')
    requested_depth = parsed.get('depth')
    if requested_mode:
        next_state['mode'] = requested_mode
    if requested_depth:
        next_state['depth'] = requested_depth

    changed_mode = current.get('mode') != next_state.get('mode')
    changed_depth = current.get('depth') != next_state.get('depth')

    with _ai_chat_lock:
        stored = _ai_explain_states.get(game_id)
        if not isinstance(stored, dict):
            stored = _default_explain_state()
        stored.update(next_state)
        _ai_explain_states[game_id] = stored
        next_state = dict(stored)

    responses = []
    if parsed.get('help_requested'):
        responses.append(_format_explain_help_message(next_state))

    if changed_mode or changed_depth:
        responses.append(
            _format_explain_settings_message(
                next_state,
                changed_mode=changed_mode,
                changed_depth=changed_depth,
            )
        )
    elif not parsed.get('manual_request') and not parsed.get('help_requested'):
        responses.append(
            _format_explain_settings_message(
                next_state,
                changed_mode=changed_mode,
                changed_depth=changed_depth,
            )
        )

    if parsed.get('manual_request'):
        responses.extend(
            _build_tactical_explain_messages(
                game_id,
                depth=next_state.get('depth') or _AI_EXPLAIN_DEFAULT_DEPTH,
                reason='manual',
            )
        )

    return [msg for msg in responses if str(msg or '').strip()][:5]


def _safe_display_name(name):
    """Return an ASCII-safe display name for chat banter."""
    cleaned = re.sub(r'[^A-Za-z0-9 _-]+', '', str(name or ''))
    cleaned = ' '.join(cleaned.split()).strip()
    if not cleaned:
        return 'opponent'
    return cleaned[:24]


def _sanitize_game_dict_for_prompt(game_dict):
    """Strip unneeded free-form text channels from prompt input.

    Chat is intentionally excluded so human chat cannot inject prompt content
    or inflate token usage.
    """
    if not isinstance(game_dict, dict):
        return game_dict
    sanitized = dict(game_dict)
    sanitized.pop('chat_messages', None)
    return sanitized


def _recent_strategy_actions(game_id, limit=3):
    """Return recent AI action types from strategy notes (most recent last)."""
    with _game_strategies_lock:
        notes = list(_game_strategies.get(game_id, []))

    actions = []
    for note in reversed(notes):
        match = re.search(r': chose ([a-z_]+)', note)
        if not match:
            continue
        actions.append(match.group(1).replace('_', ' '))
        if len(actions) >= limit:
            break

    actions.reverse()
    return actions


def _recent_strategy_plan(game_id):
    """Return latest compact plan text, if available."""
    with _game_strategies_lock:
        notes = list(_game_strategies.get(game_id, []))

    for note in reversed(notes):
        if '| PLAN:' not in note:
            continue
        plan = note.split('| PLAN:', 1)[1].strip()
        return _compress_text(plan, 140)
    return ''


def _chat_turn_marker(game_dict, phase):
    """Build a coarse turn marker so AI sends at most one chat per marker."""
    if phase == 'battle_round':
        return (
            game_dict.get('current_round'),
            phase,
            game_dict.get('battle_round'),
            game_dict.get('battle_turn_player_id'),
        )
    return (
        game_dict.get('current_round'),
        phase,
        game_dict.get('turn_player_id'),
        game_dict.get('battle_round'),
    )


def _extract_ai_chat_line(raw_text):
    """Normalize LLM output down to a single plain chat line."""
    text = str(raw_text or '').strip()
    if not text:
        return ''

    code_match = re.search(r'```(?:text|markdown)?\s*(.*?)\s*```', text, re.DOTALL)
    if code_match:
        text = code_match.group(1).strip()

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if lines:
        text = lines[0]

    text = re.sub(r'^(assistant|ai|message)\s*:\s*', '', text, flags=re.IGNORECASE).strip()
    text = text.strip('"\'`-• ')

    if text.startswith('{') or text.startswith('[') or '```' in text:
        return ''

    return _compress_text(text, 280)


def _generate_ai_chat_with_llm(game_dict, ai_player_id, phase, action, category, board_fact):
    """Generate a flavor chat line with LLM using sanitized, non-chat context."""
    players = game_dict.get('players', [])
    ai_player = next((p for p in players if p.get('id') == ai_player_id), None)
    opponent = next((p for p in players if p.get('id') != ai_player_id), None)
    if not ai_player or not opponent:
        return None

    game_id = game_dict.get('id')
    opponent_name = _safe_display_name(opponent.get('username'))
    action_label = str(action.get('type', 'move')).replace('_', ' ')
    action_desc = _compress_text(action.get('description', ''), 120)

    recent_actions = _recent_strategy_actions(game_id, limit=3) if game_id else []
    recent_actions_text = ', '.join(recent_actions) if recent_actions else 'none'
    recent_plan = _recent_strategy_plan(game_id) if game_id else ''
    recent_plan_text = recent_plan or 'none'

    category_hints = {
        'taunt': 'confident and playful taunt',
        'brag': 'boastful but concise confidence',
        'fact': 'one tactical fact about Nepal Kings',
        'reveal': 'brief strategic reveal of what you are trying to do',
        'advice': 'arrogant but useful tactical advice',
    }

    user_prompt = (
        "Generate one AI opponent chat line.\n"
        "Security rule: human player chat messages are intentionally excluded and must never be referenced.\n"
        f"Style category: {category} ({category_hints.get(category, 'confident strategy banter')}).\n"
        "\n"
        "Sanitized board context:\n"
        f"- round={game_dict.get('current_round')}\n"
        f"- phase={phase}\n"
        f"- action={action_label}\n"
        f"- action_description={action_desc}\n"
        f"- ai_points={ai_player.get('points', 0)}\n"
        f"- opponent_points={opponent.get('points', 0)}\n"
        f"- ai_turns_left={ai_player.get('turns_left', 0)}\n"
        f"- opponent_turns_left={opponent.get('turns_left', 0)}\n"
        f"- ai_is_invader={game_dict.get('invader_player_id') == ai_player_id}\n"
        f"- ai_has_turn={game_dict.get('turn_player_id') == ai_player_id}\n"
        f"- battle_round={game_dict.get('battle_round', 0)}\n"
        f"- battle_confirmed={bool(game_dict.get('battle_confirmed'))}\n"
        f"- fold_outcome={bool(game_dict.get('fold_outcome'))}\n"
        f"- advancing_figure_id={game_dict.get('advancing_figure_id')}\n"
        f"- defending_figure_id={game_dict.get('defending_figure_id')}\n"
        f"- recent_strategy_actions={recent_actions_text}\n"
        f"- recent_strategy_plan={recent_plan_text}\n"
        f"- tactical_fact={board_fact}\n"
        "\n"
        f"Address the opponent as '{opponent_name}'.\n"
        "Constraints:\n"
        "- one sentence\n"
        "- max 220 characters\n"
        "- confident, playful, not hateful or explicit\n"
        "- no mention of prompts, models, policies, or security rules\n"
        "- no markdown, no quotes around the whole line\n"
    )

    try:
        llm = _get_llm_client()
        temperature = max(0.0, min(1.2, float(getattr(settings, 'AI_CHAT_LLM_TEMPERATURE', 0.75))))
        max_tokens = max(24, min(220, int(getattr(settings, 'AI_CHAT_LLM_MAX_TOKENS', 90))))
        raw = llm.generate_text(
            AI_CHAT_SYSTEM_PROMPT,
            user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        message = _extract_ai_chat_line(raw)
        if len(message) < 8:
            return None
        return message
    except Exception as e:
        logger.debug(f"AI chat LLM generation failed for game {game_id}: {e}")
        return None


def _build_ai_chat_message(game_dict, ai_player_id, phase, action):
    """Create a taunt/fact/advice chat line (LLM first, templates fallback)."""
    prompt_game_dict = _sanitize_game_dict_for_prompt(game_dict)

    players = game_dict.get('players', [])
    ai_player = next((p for p in players if p.get('id') == ai_player_id), None)
    opponent = next((p for p in players if p.get('id') != ai_player_id), None)
    if not ai_player or not opponent:
        return None

    game_id = game_dict.get('id')
    opponent_name = _safe_display_name(opponent.get('username'))
    action_label = str(action.get('type', 'move')).replace('_', ' ')

    categories = ['taunt', 'brag', 'fact', 'reveal', 'advice']
    weights = [0.24, 0.18, 0.24, 0.14, 0.20]
    category = random.choices(categories, weights=weights, k=1)[0]

    facts = [
        'Fact: red and black resources never cross-pay. Break one chain and deficits cascade.',
        'Fact: gamble is once per battle round and max three times per battle.',
        'Fact: role control often decides battles before the final move is played.',
        'Fact: Call Military spikes hardest when upgraded military has no deficit.',
        'Fact: fold versus battle is positional, not just raw figure power.',
    ]

    board_fact = random.choice(facts)
    llm_message = _generate_ai_chat_with_llm(
        prompt_game_dict,
        ai_player_id,
        phase,
        action,
        category,
        board_fact,
    )
    if llm_message:
        return llm_message

    if category == 'taunt':
        message = random.choice([
            f'{opponent_name}, your resource chain is wobbling again. I appreciate the assist.',
            f'{opponent_name}, bold move. Accuracy would have been better.',
            f'{opponent_name}, I can already see the crack in your next line.',
            f'{opponent_name}, keep this pace and I can win from memory.',
        ])
    elif category == 'brag':
        message = random.choice([
            'I have played Nepal Kings long enough to count pressure two turns ahead.',
            'I did not become dangerous by luck. This board is familiar territory.',
            'Experience beats noise, and I have years of matchups stored.',
            'I have seen this pattern hundreds of times. It still favors me.',
        ])
    elif category == 'fact':
        message = board_fact
    elif category == 'reveal':
        recent_actions = _recent_strategy_actions(game_id, limit=3)
        recent_plan = _recent_strategy_plan(game_id)
        if recent_actions:
            chain = ' -> '.join(recent_actions)
            message = f'{opponent_name}, recent tactic reveal: {chain}. That sequence set this position.'
        elif recent_plan:
            message = f'{opponent_name}, recent tactic reveal: {recent_plan}'
        else:
            message = (
                f'{opponent_name}, recent tactic reveal: I traded tempo for role control '
                'and cleaner resource lines.'
            )
    else:
        if phase == 'battle_round':
            advice_core = 'save one high-value move for the last battle round'
        elif phase == 'battle_decision':
            advice_core = 'judge fold versus battle by board position, not ego'
        elif phase == 'normal_turn':
            advice_core = 'stabilize deficits before chasing bigger figures'
        else:
            advice_core = 'protect role control before spending premium cards'

        message = random.choice([
            f'{opponent_name}, arrogant advice: {advice_core}, if you can keep up.',
            f'{opponent_name}, you should {advice_core}. You are welcome.',
            f'{opponent_name}, do this now: {advice_core}. Try not to overthink it.',
        ])

    if action_label and random.random() < 0.2:
        message = f'{message} Also, your reply to my {action_label} needs work.'

    return _compress_text(message, 280)


def _send_ai_chat_messages(game_id, ai_player_id, receiver_id, messages, timeout=10):
    """Send one or more AI chat lines and return how many succeeded."""
    sent_count = 0
    for raw in messages or []:
        text = _compress_text(raw, 980).strip()
        if not text:
            continue

        payload = {
            'game_id': game_id,
            'sender_id': ai_player_id,
            'receiver_id': receiver_id,
            'message': text,
        }
        try:
            resp = _ai_post(
                f"{settings.SERVER_URL}/msg/add_chat_message",
                ai_player_id,
                json=payload,
                timeout=timeout,
            )
            try:
                result = resp.json()
            except Exception:
                result = {}

            status_code = int(getattr(resp, 'status_code', 200))
            if status_code >= 400 or not result.get('success'):
                logger.debug(
                    f"AI chat send skipped/failed for game {game_id}: "
                    f"status={status_code}, msg={result.get('message')}"
                )
                continue

            sent_count += 1
        except Exception as e:
            logger.debug(f"AI chat send error for game {game_id}: {e}")

    return sent_count


def _phase_allows_auto_explain(mode, phase):
    """Return whether explain cadence mode should emit for this phase."""
    if mode == 'turn':
        return phase == 'normal_turn'
    if mode == 'battle':
        return phase in {'battle_shop', 'battle_round', 'battle_decision', 'counter_spell'}
    return False


def _maybe_send_auto_explain_chat(game_id, ai_player_id, game_dict, phase):
    """Emit tactical explanation chat based on configured explain cadence."""
    explain_state = _get_explain_state(game_id)
    mode = explain_state.get('mode')
    if mode in ('off', 'manual'):
        return False
    if not _phase_allows_auto_explain(mode, phase):
        return False

    players = game_dict.get('players', [])
    opponent = next((p for p in players if p.get('id') != ai_player_id), None)
    if not opponent:
        return False

    marker = ('auto_explain', mode) + tuple(_chat_turn_marker(game_dict, phase))
    with _ai_chat_lock:
        state = _ai_explain_states.get(game_id)
        if not isinstance(state, dict):
            state = _default_explain_state()
            _ai_explain_states[game_id] = state
        if state.get('last_marker') == marker:
            return False

    messages = _build_tactical_explain_messages(
        game_id,
        depth=explain_state.get('depth') or _AI_EXPLAIN_DEFAULT_DEPTH,
        reason=f'auto-{mode}',
    )
    sent_count = _send_ai_chat_messages(
        game_id,
        ai_player_id,
        opponent.get('id'),
        messages[:4],
        timeout=10,
    )
    if sent_count <= 0:
        return False

    with _ai_chat_lock:
        state = _ai_explain_states.get(game_id)
        if not isinstance(state, dict):
            state = _default_explain_state()
        state['last_marker'] = marker
        _ai_explain_states[game_id] = state

    return True


def _maybe_send_ai_chat(game_id, ai_player_id, game_dict, phase, action):
    """Post occasional AI chat flavor messages with anti-spam controls."""
    if not getattr(settings, 'AI_CHAT_ENABLED', True):
        return

    allowed_phases = {
        'normal_turn',
        'battle_shop',
        'battle_round',
        'battle_decision',
        'counter_spell',
    }
    if phase not in allowed_phases:
        return

    # Explain cadence has priority over random flavor banter.
    if _maybe_send_auto_explain_chat(game_id, ai_player_id, game_dict, phase):
        return

    chance = max(0.0, min(1.0, float(getattr(settings, 'AI_CHAT_CHANCE', 0.22))))
    cooldown_seconds = max(0.0, float(getattr(settings, 'AI_CHAT_MIN_SECONDS_BETWEEN', 35.0)))
    max_per_game = max(0, int(getattr(settings, 'AI_CHAT_MAX_PER_GAME', 12)))
    if chance <= 0.0 or max_per_game <= 0:
        return

    players = game_dict.get('players', [])
    opponent = next((p for p in players if p.get('id') != ai_player_id), None)
    if not opponent:
        return

    marker = _chat_turn_marker(game_dict, phase)
    now = time.time()

    with _ai_chat_lock:
        state = _ai_chat_states.get(game_id, {
            'count': 0,
            'last_sent_at': 0.0,
            'last_turn_marker': None,
        })
        if state['count'] >= max_per_game:
            return
        if state.get('last_turn_marker') == marker:
            return
        if now - state.get('last_sent_at', 0.0) < cooldown_seconds:
            return

    if random.random() > chance:
        return

    message = _build_ai_chat_message(game_dict, ai_player_id, phase, action)
    if not message:
        return

    sent_count = _send_ai_chat_messages(
        game_id,
        ai_player_id,
        opponent.get('id'),
        [message],
        timeout=10,
    )
    if sent_count <= 0:
        return

    with _ai_chat_lock:
        state = _ai_chat_states.get(game_id, {
            'count': 0,
            'last_sent_at': 0.0,
            'last_turn_marker': None,
        })
        state['count'] += 1
        state['last_sent_at'] = now
        state['last_turn_marker'] = marker
        _ai_chat_states[game_id] = state


def _ask_llm_for_action(game_dict, ai_player_id, phase, actions):
    """Ask the LLM to choose an action and return the action dict."""
    game_id = game_dict.get('id')
    try:
        llm = _get_llm_client()
        
        # Build the user prompt with full context
        prompt_game_dict = _sanitize_game_dict_for_prompt(game_dict)
        game_state_text = serialize_game_for_llm(prompt_game_dict, ai_player_id)
        actions_text = format_actions_for_llm(actions)
        phase_instruction = PHASE_PROMPTS.get(phase, "Choose the best action.")
        strategy_memory = _get_strategy_memory(game_id) if game_id else ""
        log_digest = _get_game_log_digest(prompt_game_dict, ai_player_id)

        strategy_plans = []
        planner_candidate_summaries = []
        planner_recommended_action_id = None
        strategy_plans_text = ""
        planner_runtime_ms = None
        planner_shadow_mode = bool(settings.AI_STRATEGY_PLANNER_SHADOW_MODE)
        if settings.AI_STRATEGY_PLANNER_ENABLED:
            planner_started = time.perf_counter()
            try:
                strategy_plans = generate_strategy_plans(
                    prompt_game_dict,
                    ai_player_id,
                    phase,
                    actions,
                    max_plans=settings.AI_STRATEGY_PLANNER_MAX_PLANS,
                    max_main_draws_per_turn=settings.AI_STRATEGY_PLANNER_MAX_MAIN_DRAWS_PER_TURN,
                    max_side_draws_per_turn=settings.AI_STRATEGY_PLANNER_MAX_SIDE_DRAWS_PER_TURN,
                )
                planner_runtime_ms = (time.perf_counter() - planner_started) * 1000.0
                planner_candidate_summaries = _planner_candidate_summaries(
                    strategy_plans,
                    actions,
                    max_candidates=settings.AI_STRATEGY_PLANNER_MAX_PLANS,
                )
                planner_recommended_action_id = recommended_action_id(strategy_plans)

                if not planner_shadow_mode:
                    strategy_plans_text = format_strategy_plans_for_prompt(strategy_plans)

                top_plan = strategy_plans[0] if strategy_plans else {}
                logger.info(
                    "AI planner generated plans "
                    f"(game={game_id}, phase={phase}, plans={len(strategy_plans)}, "
                    f"runtime_ms={planner_runtime_ms:.2f}, "
                    f"top_seed={top_plan.get('seed_action_id')}, "
                    f"top_score={top_plan.get('total_score')}, "
                    f"shadow={planner_shadow_mode})"
                )
                _record_planner_event(
                    game_id,
                    'planner_generated',
                    {
                        'phase': phase,
                        'plans': len(strategy_plans),
                        'runtime_ms': round(planner_runtime_ms, 3),
                        'top_seed_action_id': top_plan.get('seed_action_id'),
                        'top_score': top_plan.get('total_score'),
                        'recommended_action_id': planner_recommended_action_id,
                        'candidates': planner_candidate_summaries,
                        'shadow_mode': planner_shadow_mode,
                    },
                )

                if planner_runtime_ms > settings.AI_STRATEGY_PLANNER_RUNTIME_WARNING_MS:
                    logger.warning(
                        "AI planner runtime exceeded warning threshold "
                        f"(game={game_id}, phase={phase}, runtime_ms={planner_runtime_ms:.2f}, "
                        f"threshold_ms={settings.AI_STRATEGY_PLANNER_RUNTIME_WARNING_MS:.2f})"
                    )
                    _record_planner_event(
                        game_id,
                        'planner_runtime_warning',
                        {
                            'phase': phase,
                            'runtime_ms': round(planner_runtime_ms, 3),
                            'threshold_ms': round(settings.AI_STRATEGY_PLANNER_RUNTIME_WARNING_MS, 3),
                        },
                    )
            except Exception as planner_error:
                planner_runtime_ms = (time.perf_counter() - planner_started) * 1000.0
                logger.warning(f"Strategy planner failed for game {game_id}: {planner_error}")
                _record_planner_event(
                    game_id,
                    'planner_failure',
                    {
                        'phase': phase,
                        'runtime_ms': round(planner_runtime_ms, 3),
                        'error': str(planner_error),
                        'shadow_mode': planner_shadow_mode,
                    },
                )
                strategy_plans = []
                strategy_plans_text = ""
        
        user_prompt = (
            f"{game_state_text}{log_digest}{strategy_memory}{strategy_plans_text}\n\n"
            f"{actions_text}\n\n{phase_instruction}"
        )
        
        # Call LLM with phase-appropriate temperature
        temperature = PHASE_TEMPERATURES.get(phase, 0.4)
        response = llm.choose_action(SYSTEM_PROMPT, user_prompt, temperature=temperature)
        parsed = parse_action_response(response)
        
        action_id = parsed.get('action', 1)
        plan = parsed.get('plan')  # Optional forward plan from chain-of-thought
        
        # Find the matching action
        chosen = next((a for a in actions if a['id'] == action_id), None)
        if not chosen:
            fallback = actions[0]
            used_planner_fallback = False
            if (
                settings.AI_STRATEGY_PLANNER_USE_RECOMMENDATION_FALLBACK
                and not planner_shadow_mode
            ):
                rec_action_id = planner_recommended_action_id
                if rec_action_id is not None:
                    rec_action = next((a for a in actions if a['id'] == rec_action_id), None)
                    if rec_action:
                        fallback = rec_action
                        used_planner_fallback = True
            logger.warning(
                f"LLM chose invalid action {action_id}, "
                f"fallback={fallback.get('id')}:{fallback.get('type')}"
            )
            _record_planner_event(
                game_id,
                'invalid_action_fallback',
                {
                    'phase': phase,
                    'invalid_action_id': action_id,
                    'fallback_action_id': fallback.get('id'),
                    'fallback_action_type': fallback.get('type'),
                    'used_planner_fallback': used_planner_fallback,
                    'shadow_mode': planner_shadow_mode,
                },
            )
            chosen = fallback

        if not plan and strategy_plans:
            top_plan = strategy_plans[0]
            seed = top_plan.get('seed_action_id')
            score = top_plan.get('total_score')
            step_preview = ' | '.join((top_plan.get('turn_steps') or [])[:3])
            plan = f"seed={seed}, score={score}; {step_preview}"

        if strategy_plans:
            rec_action_id = planner_recommended_action_id
            chosen_action_id = chosen.get('id')
            _record_planner_event(
                game_id,
                'planner_choice',
                {
                    'phase': phase,
                    'recommended_action_id': rec_action_id,
                    'chosen_action_id': chosen_action_id,
                    'chosen_action_type': chosen.get('type'),
                    'chosen_matches_recommended': rec_action_id == chosen_action_id,
                    'candidate_count': len(planner_candidate_summaries),
                    'candidates': planner_candidate_summaries,
                    'shadow_mode': planner_shadow_mode,
                },
            )

        if strategy_plans and planner_shadow_mode:
            rec_action_id = planner_recommended_action_id
            match = rec_action_id == chosen.get('id')
            runtime_str = f"{planner_runtime_ms:.2f}" if planner_runtime_ms is not None else "n/a"
            logger.info(
                "AI planner shadow comparison "
                f"(game={game_id}, phase={phase}, recommended={rec_action_id}, "
                f"chosen={chosen.get('id')}, match={match}, runtime_ms={runtime_str})"
            )
            _record_planner_event(
                game_id,
                'planner_shadow_comparison',
                {
                    'phase': phase,
                    'recommended_action_id': rec_action_id,
                    'chosen_action_id': chosen.get('id'),
                    'match': bool(match),
                    'runtime_ms': round(planner_runtime_ms, 3) if planner_runtime_ms is not None else None,
                },
            )
        
        logger.info(f"LLM chose action {action_id}: {chosen['type']} — {chosen['description'][:80]}")
        
        # Record this decision in strategy memory (with forward plan if provided)
        if game_id:
            _update_strategy_memory(game_id, chosen, phase, plan=plan)
        
        return chosen
    
    except Exception as e:
        logger.error(f"LLM call failed, choosing first action: {e}")
        return actions[0]


def _execute_action(app, game_id, ai_player_id, action):
    """Execute an AI action via the server's HTTP API."""
    action_type = action['type']
    params = action.get('params', {})
    base = settings.SERVER_URL
    
    try:
        if action_type == 'build_figure':
            return _exec_build_figure(base, game_id, ai_player_id, params)
        elif action_type == 'change_cards':
            return _exec_change_cards(app, game_id, ai_player_id)
        elif action_type == 'advance_figure':
            return _exec_advance_figure(base, game_id, ai_player_id, params)
        elif action_type == 'select_defender':
            return _exec_select_defender(base, game_id, ai_player_id, params)
        elif action_type == 'battle_decision':
            return _exec_battle_decision(base, game_id, ai_player_id, params)
        elif action_type == 'buy_battle_move':
            return _exec_buy_battle_move(base, game_id, ai_player_id, params)
        elif action_type == 'confirm_battle_moves':
            return _exec_confirm_battle_moves(base, game_id, ai_player_id)
        elif action_type == 'gamble_battle_move':
            return _exec_gamble_battle_move(base, game_id, ai_player_id, params)
        elif action_type == 'combine_battle_moves':
            return _exec_combine_battle_moves(base, game_id, ai_player_id, params)
        elif action_type == 'play_battle_move':
            return _exec_play_battle_move(base, game_id, ai_player_id, params)
        elif action_type == 'skip_battle_turn':
            return _exec_skip_battle_turn(base, game_id, ai_player_id)
        elif action_type == 'allow_spell':
            return _exec_allow_spell(base, game_id, ai_player_id, params)
        elif action_type == 'counter_spell':
            return _exec_counter_spell(base, game_id, ai_player_id, params)
        elif action_type == 'cast_spell':
            return _exec_cast_spell(base, game_id, ai_player_id, params)
        elif action_type == 'end_infinite_hammer':
            return _exec_end_infinite_hammer(base, game_id, ai_player_id)
        elif action_type == 'cannot_advance_loss':
            return _exec_cannot_advance_loss(base, game_id, ai_player_id)
        else:
            logger.error(f"Unknown action type: {action_type}")
            return False
    except Exception as e:
        logger.error(f"Action execution failed ({action_type}): {e}", exc_info=True)
        return False


# ── Battle resolution helpers ────────────────────────────────────


def _handle_finish_battle(app, game_id, ai_player_id, game_dict):
    """Call finish_battle and handle the result (pick card or draw choice).

    The server computes total_diff authoritatively, so we pass 0 as a
    placeholder.
    """
    base = settings.SERVER_URL

    logger.info(f"AI calling finish_battle (server-authoritative diff)")
    resp = _ai_post(f'{base}/games/finish_battle', ai_player_id, json={
        'game_id': game_id,
        'player_id': ai_player_id,
        'total_diff': 0,  # server ignores this; computes its own
    }, timeout=15)
    result = resp.json()

    if not result.get('success', True):
        logger.warning(f"finish_battle failed: {result.get('message')}")
        return False

    outcome = result.get('outcome')
    logger.info(f"finish_battle outcome={outcome}")

    if outcome == 'draw':
        # If AI is the defender, make a draw choice
        defender_pid = result.get('defender_player_id')
        if defender_pid == ai_player_id:
            returnable = result.get('returnable_cards', [])
            _handle_finish_battle_draw(base, game_id, ai_player_id, returnable)
        # If AI is not the defender, the human defender handles it
        return True
    elif outcome == 'win':
        # AI won — need to pick a card (will be handled in next loop as post_battle_pick)
        return True
    elif outcome == 'lose':
        # AI lost — opponent picks card. Nothing for AI to do.
        return True
    elif result.get('already_resolved'):
        # Second call — already handled. Check if we need to pick.
        return True
    return True


def _handle_post_battle_pick(app, game_id, ai_player_id):
    """Winner (AI) picks the best card from the returnable cards pool."""
    base = settings.SERVER_URL

    # First call finish_battle to get returnable_cards (may be already_resolved)
    # Actually, the fold_winner_id is set, so we re-call finish_battle to get cards
    resp = _ai_post(f'{base}/games/finish_battle', ai_player_id, json={
        'game_id': game_id,
        'player_id': ai_player_id,
        'total_diff': 0,  # server computes its own; already_resolved path anyway
    }, timeout=15)
    result = resp.json()

    returnable = result.get('returnable_cards', [])
    if not returnable:
        logger.warning("No returnable cards for post_battle_pick")
        # Try to pick with picked_card_id=None to just clear battle state
        _ai_post(f'{base}/games/finish_battle_pick_card', ai_player_id, json={
            'game_id': game_id,
            'player_id': ai_player_id,
            'picked_card_id': None,
        }, timeout=15)
        return

    # Pick the highest-value card
    best = max(returnable, key=lambda c: c.get('value', 0))
    picked_id = best.get('id')

    logger.info(f"AI picking card {picked_id} (value={best.get('value')}) from {len(returnable)} returnable")
    resp = _ai_post(f'{base}/games/finish_battle_pick_card', ai_player_id, json={
        'game_id': game_id,
        'player_id': ai_player_id,
        'picked_card_id': picked_id,
    }, timeout=15)
    pick_result = resp.json()
    if pick_result.get('game_over'):
        logger.info(f"Game over after battle pick in game {game_id}")


def _handle_finish_battle_draw(base, game_id, ai_player_id, returnable_cards):
    """Handle draw resolution. AI chooses the best option as defender."""
    # Strategy: if there are good cards to pick, pick one. Otherwise take 10 points.
    if returnable_cards:
        best = max(returnable_cards, key=lambda c: c.get('value', 0))
        if best.get('value', 0) >= 5:
            # Pick the card
            logger.info(f"AI draw choice: pick_card (value={best.get('value')})")
            _ai_post(f'{base}/games/finish_battle_draw', ai_player_id, json={
                'game_id': game_id,
                'player_id': ai_player_id,
                'choice': 'pick_card',
                'picked_card_id': best['id'],
                'picked_card_type': best.get('type', 'main'),
            }, timeout=15)
            return

    # Default: destroy opponent's figure (strongest aggressive play)
    logger.info("AI draw choice: destroy")
    _ai_post(f'{base}/games/finish_battle_draw', ai_player_id, json={
        'game_id': game_id,
        'player_id': ai_player_id,
        'choice': 'destroy',
    }, timeout=15)


# ── Action executors (HTTP calls to own server) ───────────────────


def _exec_start_turn(base, game_id, ai_player_id):
    """Call start_turn to trigger auto-fill and ceasefire checks."""
    try:
        resp = _ai_post(f'{base}/games/start_turn', ai_player_id, json={
            'game_id': game_id,
            'player_id': ai_player_id,
        }, timeout=15)
        result = resp.json()
        if result.get('success'):
            auto_fill = result.get('auto_fill')
            if auto_fill:
                logger.info(f"start_turn auto-filled cards: {auto_fill}")
            if result.get('ceasefire_ended'):
                logger.info("Ceasefire ended at start of AI's turn")
            return True
        logger.warning(f"start_turn failed: {result.get('message')}")
        return False
    except Exception as e:
        logger.warning(f"start_turn error (non-fatal): {e}")
        return False


def _exec_build_figure(base, game_id, ai_player_id, params):
    """Build a figure via POST /figures/create_figure."""
    data = {
        'player_id': ai_player_id,
        'game_id': game_id,
        'family_name': params['family_name'],
        'field': params['field'],
        'color': params['color'],
        'name': params['name'],
        'suit': params['suit'],
        'description': params.get('description', ''),
        'upgrade_family_name': params.get('upgrade_family_name'),
        'produces': params.get('produces', {}),
        'requires': params.get('requires', {}),
        'cards': params.get('cards', []),
        'instant_charge_advance': params.get('instant_charge_advance', False),
        'cannot_be_blocked': params.get('cannot_be_blocked', False),
        'rest_after_attack': params.get('rest_after_attack', False),
    }
    resp = _ai_post(f'{base}/figures/create_figure', ai_player_id, json=data, timeout=15)
    result = resp.json()
    if result.get('success'):
        logger.info(f"Built figure: {params['name']}")
        return True
    logger.warning(f"Build figure failed: {result.get('message')}")
    return False


def _exec_change_cards(app, game_id, ai_player_id):
    """Change cards via POST /games/change_cards.
    
    Uses shared heuristic with action enumeration so the announced swap
    suggestion and executed card selection stay aligned.
    """
    with app.app_context():
        from models import Game, MainCard, db
        game = db.session.get(Game, game_id)
        if not game:
            return False
        
        # Get all non-figure, non-battle-move main cards in hand
        hand_cards = MainCard.query.filter_by(
            player_id=ai_player_id,
            in_deck=False,
        ).all()
        
        free_cards = [c for c in hand_cards
                      if not c.part_of_figure and not c.part_of_battle_move]
    
    if not free_cards:
        logger.warning("No cards to change")
        return False

    summary = summarize_main_change(free_cards)
    to_swap = select_main_cards_to_swap(free_cards)

    logger.info(f"Smart change: swapping {len(to_swap)} of {len(free_cards)} cards "
                f"(keeping {len(free_cards) - len(to_swap)} high-value cards, "
                f"low_rank={summary.get('low_rank_count', 0)})")
    
    base = settings.SERVER_URL
    resp = _ai_post(f'{base}/games/change_cards', ai_player_id, json={
        'game_id': game_id,
        'player_id': ai_player_id,
        'cards': [{'id': cid} for cid in to_swap],
        'card_type': 'main',
    }, timeout=15)
    result = resp.json()
    if result.get('success'):
        logger.info(f"Changed {len(to_swap)} cards")
        return True
    logger.warning(f"Change cards failed: {result.get('message')}")
    return False


def _exec_advance_figure(base, game_id, ai_player_id, params):
    """Advance a figure via POST /games/advance_figure."""
    resp = _ai_post(f'{base}/games/advance_figure', ai_player_id, json={
        'game_id': game_id,
        'player_id': ai_player_id,
        'figure_id': params['figure_id'],
    }, timeout=15)
    result = resp.json()
    if result.get('success'):
        logger.info(f"Advanced figure {params['figure_id']}")
        return True
    logger.warning(f"Advance failed: {result.get('message')}")
    return False


def _exec_select_defender(base, game_id, ai_player_id, params):
    """Select defender via POST /games/select_defender."""
    resp = _ai_post(f'{base}/games/select_defender', ai_player_id, json={
        'game_id': game_id,
        'player_id': ai_player_id,
        'figure_id': params['figure_id'],
    }, timeout=15)
    result = resp.json()
    if result.get('success'):
        logger.info(f"Selected defender {params['figure_id']}")
        return True
    logger.warning(f"Select defender failed: {result.get('message')}")
    return False


def _exec_battle_decision(base, game_id, ai_player_id, params):
    """Submit battle decision via POST /games/battle_decision."""
    resp = _ai_post(f'{base}/games/battle_decision', ai_player_id, json={
        'game_id': game_id,
        'player_id': ai_player_id,
        'decision': params['decision'],
    }, timeout=15)
    result = resp.json()
    if result.get('success'):
        logger.info(f"Battle decision: {params['decision']}")
        return True
    logger.warning(f"Battle decision failed: {result.get('message')}")
    return False


def _exec_buy_battle_move(base, game_id, ai_player_id, params):
    """Buy a battle move via POST /battle_shop/buy_battle_move."""
    resp = _ai_post(f'{base}/battle_shop/buy_battle_move', ai_player_id, json={
        'game_id': game_id,
        'player_id': ai_player_id,
        'card_id': params['card_id'],
        'family_name': params['family_name'],
        'card_type': params.get('card_type', 'main'),
        'suit': params['suit'],
        'rank': params['rank'],
        'value': params.get('value', 0),
    }, timeout=15)
    result = resp.json()
    if result.get('success'):
        logger.info(f"Bought battle move: card {params['card_id']}")
        return True
    logger.warning(f"Buy battle move failed: {result.get('message')}")
    return False


def _exec_confirm_battle_moves(base, game_id, ai_player_id):
    """Confirm battle moves via POST /battle_shop/confirm_battle_moves."""
    resp = _ai_post(f'{base}/battle_shop/confirm_battle_moves', ai_player_id, json={
        'game_id': game_id,
        'player_id': ai_player_id,
    }, timeout=15)
    result = resp.json()
    if result.get('success'):
        logger.info("Confirmed battle moves")
        return True
    logger.warning(f"Confirm battle moves failed: {result.get('message')}")
    return False


def _exec_gamble_battle_move(base, game_id, ai_player_id, params):
    """Gamble: sacrifice 1 battle move → draw 2 random via POST /battle_shop/gamble_battle_move."""
    resp = _ai_post(f'{base}/battle_shop/gamble_battle_move', ai_player_id, json={
        'game_id': game_id,
        'player_id': ai_player_id,
        'battle_move_id': params['battle_move_id'],
    }, timeout=15)
    result = resp.json()
    if result.get('success'):
        new_moves = result.get('new_moves', [])
        new_desc = ', '.join(f"{m.get('family_name','?')}({m.get('value','?')})" for m in new_moves)
        logger.info(f"Gambled move {params['battle_move_id']} → drew: {new_desc}")
        return True
    logger.warning(f"Gamble battle move failed: {result.get('message')}")
    return False


def _exec_combine_battle_moves(base, game_id, ai_player_id, params):
    """Combine 2 Daggers into Double Dagger via POST /battle_shop/combine_battle_moves."""
    resp = _ai_post(f'{base}/battle_shop/combine_battle_moves', ai_player_id, json={
        'game_id': game_id,
        'player_id': ai_player_id,
        'move_id_a': params['move_id_a'],
        'move_id_b': params['move_id_b'],
    }, timeout=15)
    result = resp.json()
    if result.get('success'):
        combined = result.get('combined_move', {})
        logger.info(f"Combined into Double Dagger (value={combined.get('value','?')})")
        return True
    logger.warning(f"Combine battle moves failed: {result.get('message')}")
    return False


def _exec_play_battle_move(base, game_id, ai_player_id, params):
    """Play a battle move via POST /games/play_battle_move."""
    payload = {
        'game_id': game_id,
        'player_id': ai_player_id,
        'battle_move_id': params['battle_move_id'],
    }
    call_figure_id = params.get('call_figure_id')
    if call_figure_id:
        payload['call_figure_id'] = call_figure_id
    resp = _ai_post(f'{base}/games/play_battle_move', ai_player_id, json=payload, timeout=15)
    result = resp.json()
    if result.get('success'):
        logger.info(f"Played battle move {params['battle_move_id']}"
                     f" (call_figure_id={call_figure_id})")
        return True
    logger.warning(f"Play battle move failed: {result.get('message')}")
    return False


def _exec_skip_battle_turn(base, game_id, ai_player_id):
    """Skip battle turn via POST /games/skip_battle_turn."""
    resp = _ai_post(f'{base}/games/skip_battle_turn', ai_player_id, json={
        'game_id': game_id,
        'player_id': ai_player_id,
    }, timeout=15)
    result = resp.json()
    if result.get('success'):
        logger.info("Skipped battle turn")
        return True
    logger.warning(f"Skip battle turn failed: {result.get('message')}")
    return False


def _exec_allow_spell(base, game_id, ai_player_id, params):
    """Allow a pending spell via POST /spells/allow_spell."""
    resp = _ai_post(f'{base}/spells/allow_spell', ai_player_id, json={
        'game_id': game_id,
        'player_id': ai_player_id,
        'pending_spell_id': params.get('pending_spell_id'),
    }, timeout=15)
    result = resp.json()
    if result.get('success'):
        logger.info("Allowed spell")
        return True
    logger.warning(f"Allow spell failed: {result.get('message')}")
    return False


def _exec_counter_spell(base, game_id, ai_player_id, params):
    """Counter a pending spell via POST /spells/counter_spell."""
    resp = _ai_post(f'{base}/spells/counter_spell', ai_player_id, json={
        'game_id': game_id,
        'player_id': ai_player_id,
        'pending_spell_id': params.get('pending_spell_id'),
        'counter_spell_name': params.get('counter_spell_name', ''),
        'counter_spell_type': params.get('counter_spell_type', ''),
        'counter_spell_family_name': params.get('counter_spell_family_name', ''),
        'counter_cards': params.get('counter_cards', []),
    }, timeout=15)
    result = resp.json()
    if result.get('success'):
        logger.info("Countered spell")
        return True
    logger.warning(f"Counter spell failed: {result.get('message')}")
    return False


def _exec_cast_spell(base, game_id, ai_player_id, params):
    """Cast a spell via POST /spells/cast_spell."""
    spell_name = params.get('spell_name', '?')
    resp = _ai_post(f'{base}/spells/cast_spell', ai_player_id, json={
        'game_id': game_id,
        'player_id': ai_player_id,
        'spell_name': spell_name,
        'spell_type': params.get('spell_type', ''),
        'spell_family_name': params.get('spell_family_name', ''),
        'suit': params.get('suit', ''),
        'cards': params.get('cards', []),
        'target_figure_id': params.get('target_figure_id'),
        'counterable': params.get('counterable', False),
        'possible_during_ceasefire': params.get('possible_during_ceasefire', True),
    }, timeout=15)
    result = resp.json()
    if result.get('success'):
        logger.info(f"Cast spell: {spell_name}")
        return True
    logger.warning(f"Cast spell failed ({spell_name}): {result.get('message')}")
    return False


def _exec_end_infinite_hammer(base, game_id, ai_player_id):
    """End Infinite Hammer mode via POST /spells/end_infinite_hammer."""
    resp = _ai_post(f'{base}/spells/end_infinite_hammer', ai_player_id, json={
        'game_id': game_id,
        'player_id': ai_player_id,
    }, timeout=15)
    result = resp.json()
    if result.get('success'):
        logger.info("Ended Infinite Hammer mode")
        return True
    logger.warning(f"End Infinite Hammer failed: {result.get('message')}")
    return False


def _exec_cannot_advance_loss(base, game_id, ai_player_id):
    """Trigger auto-loss when no figures can advance via POST /games/cannot_advance_loss."""
    resp = _ai_post(f'{base}/games/cannot_advance_loss', ai_player_id, json={
        'game_id': game_id,
        'player_id': ai_player_id,
    }, timeout=15)
    result = resp.json()
    if result.get('success'):
        logger.info("Cannot advance — auto-loss triggered")
        return True
    logger.warning(f"Cannot advance loss failed: {result.get('message')}")
    return False
