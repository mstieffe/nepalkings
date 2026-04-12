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
import requests as http_requests

import server_settings as settings
from ai import get_ai_auth_headers
from ai.llm_client import LLMClient, parse_action_response
from ai.game_state import serialize_game_for_llm
from ai.action_enum import detect_phase, enumerate_actions, format_actions_for_llm
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

# Phase-specific LLM temperatures — lower = more deterministic for math-heavy decisions
PHASE_TEMPERATURES = {
    'normal_turn': 0.4,       # Balanced — strategic + math
    'select_defender': 0.3,   # Target evaluation
    'battle_decision': 0.2,   # Pure math: fold vs battle
    'battle_shop': 0.3,       # Card evaluation + combinatorics
    'battle_round': 0.2,      # Move sequencing — deterministic
    'counter_spell': 0.2,     # Cost-benefit analysis
    'post_battle_pick': 0.2,  # Card value ranking
    'post_battle_draw': 0.1,  # Almost always "destroy opponent's"
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
                from models import Game
                game = Game.query.get(game_id)
                if not game or game.state == 'finished':
                    _clear_watchdog_retry(game_id)
                    return

                game_dict = game.serialize()
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
    from models import Game, User
    
    # Quick check: does this game have an AI player who needs to act?
    game = Game.query.get(game_id)
    if not game or game.state == 'finished':
        return
    
    ai_player = None
    for player in game.players:
        user = User.query.get(player.user_id)
        if user and user.is_ai:
            ai_player = player
            break
    
    if not ai_player:
        return

    # Cache player->user mapping for auth headers used by background thread.
    with _ai_player_user_ids_lock:
        _ai_player_user_ids[ai_player.id] = ai_player.user_id
    
    # Check if the AI actually needs to act right now
    game_dict = game.serialize()
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
                from models import Game
                game = Game.query.get(game_id)
                if not game or game.state == 'finished':
                    logger.info(f"AI loop exit: game {game_id} is finished/gone")
                    _clear_watchdog_retry(game_id)
                    # Clean up strategy memory for finished games
                    with _game_strategies_lock:
                        _game_strategies.pop(game_id, None)
                    break
                
                game_dict = game.serialize()
            
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
                    game = Game.query.get(game_id)
                    if game and game.state != 'finished':
                        game_dict = game.serialize()
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
                    game = Game.query.get(game_id)
                    if not game or game.state == 'finished':
                        _clear_watchdog_retry(game_id)
                        break
                    game_dict = game.serialize()
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
                # If confirm_battle_moves failed, try gamble or buy to reach 3 moves
                if not fallback_success and chosen['type'] == 'confirm_battle_moves':
                    # Priority: gamble (produces more moves) > buy > combine
                    gamble_action = next((a for a in actions if a['type'] == 'gamble_battle_move'), None)
                    buy_action = next((a for a in actions if a['type'] == 'buy_battle_move'), None)
                    combine_action = next((a for a in actions if a['type'] == 'combine_battle_moves'), None)
                    for fb in [gamble_action, buy_action, combine_action]:
                        if fb:
                            logger.info(f"AI confirm failed, falling back to {fb['type']}")
                            if _execute_action(app, game_id, ai_player_id, fb):
                                fallback_success = True
                                break
                if not fallback_success:
                    unsuccessful_exit = True
                    break
                # Fallback action succeeded — continue loop
                time.sleep(settings.AI_THINK_DELAY)
                continue

            _clear_watchdog_retry(game_id)
            
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
                    from models import Game
                    game = Game.query.get(game_id)
                    if not game or game.state == 'finished':
                        _clear_watchdog_retry(game_id)
                    else:
                        game_dict = game.serialize()
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
        msg = e.get('message', '')
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


def _ask_llm_for_action(game_dict, ai_player_id, phase, actions):
    """Ask the LLM to choose an action and return the action dict."""
    game_id = game_dict.get('id')
    try:
        llm = _get_llm_client()
        
        # Build the user prompt with full context
        game_state_text = serialize_game_for_llm(game_dict, ai_player_id)
        actions_text = format_actions_for_llm(actions)
        phase_instruction = PHASE_PROMPTS.get(phase, "Choose the best action.")
        strategy_memory = _get_strategy_memory(game_id) if game_id else ""
        log_digest = _get_game_log_digest(game_dict, ai_player_id)
        
        user_prompt = f"{game_state_text}{log_digest}{strategy_memory}\n\n{actions_text}\n\n{phase_instruction}"
        
        # Call LLM with phase-appropriate temperature
        temperature = PHASE_TEMPERATURES.get(phase, 0.4)
        response = llm.choose_action(SYSTEM_PROMPT, user_prompt, temperature=temperature)
        parsed = parse_action_response(response)
        
        action_id = parsed.get('action', 1)
        plan = parsed.get('plan')  # Optional forward plan from chain-of-thought
        
        # Find the matching action
        chosen = next((a for a in actions if a['id'] == action_id), None)
        if not chosen:
            logger.warning(f"LLM chose invalid action {action_id}, defaulting to first")
            chosen = actions[0]
        
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
    
    Smart card selection: keep high-value battle cards (K, A, 10, 9) and
    key cards needed for building (J for village, Q for temple, A for military).
    Only swap low-value or duplicate cards we can't use.
    """
    with app.app_context():
        from models import Game, MainCard
        game = Game.query.get(game_id)
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
    
    # Rank cards by value for keeping: K(4), A(3), 10, 9, Q, 8, J, 7
    # Keep: K (battle=4, Maharaja build), A (battle=3, military build),
    #        10 (battle=10), 9 (battle=9), Q (temple build, battle block)
    # Swap: 7, 8, and excess duplicates
    KEEP_RANKS = {'K', 'A', '10', '9'}
    MAYBE_KEEP = {'Q', 'J'}  # Keep 1-2 of each for building

    to_swap = []
    kept_counts = {}
    
    # Sort: highest value last so we process low-value first
    sorted_cards = sorted(free_cards, key=lambda c: c.value or 0)
    
    for card in sorted_cards:
        rank = card.rank
        kept_counts[rank] = kept_counts.get(rank, 0)
        
        if rank in KEEP_RANKS:
            # Always keep K, A, 10, 9
            kept_counts[rank] += 1
            continue
        elif rank in MAYBE_KEEP:
            # Keep up to 2 of Q and J
            if kept_counts[rank] < 2:
                kept_counts[rank] += 1
                continue
        # Swap 7s, 8s, and excess Q/J
        to_swap.append(card.id)
    
    if not to_swap:
        # Nothing worth swapping — swap lowest value card anyway
        to_swap = [sorted_cards[0].id]
    
    logger.info(f"Smart change: swapping {len(to_swap)} of {len(free_cards)} cards "
                f"(keeping {len(free_cards) - len(to_swap)} high-value cards)")
    
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
