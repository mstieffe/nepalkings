# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
from __future__ import annotations
"""
AI Worker — event-driven background AI player.

When a game state change puts an AI player in a position where they need
to act, `trigger_ai_if_needed(game_id)` spawns a short-lived daemon thread
that reads the game state and executes the chosen action. Duel-mode
decisions are computed by `ai.duel_strategy`; conquer-mode decisions are
computed inline by the deterministic helpers below.
"""
import threading
import time
import logging
import random
import requests as http_requests

import server_settings as settings
from ai import get_ai_auth_headers
from ai.defence.generator import get_ai_defence_template_for_land
from ai.game_state import enrich_figures_with_skills
from ai.action_enum import detect_phase, enumerate_actions
from ai.card_change_strategy import (
    compute_side_tactic_protected_ids,
    compute_tactic_protected_ids,
    select_main_cards_to_swap,
    select_side_cards_to_swap,
    summarize_main_change,
    summarize_side_change,
)
from ai import duel_strategy

logger = logging.getLogger('nepalkings.ai.worker')

_AI_INTERNAL_REQUEST_HEADER = 'X-NepalKings-AI-Internal'

# Cache mapping AI player IDs to AI user IDs so auth headers can be built
# from worker threads without touching the Flask-bound DB session.
_ai_player_user_ids = {}
_ai_player_user_ids_lock = threading.Lock()
_internal_service_tokens = {}
_internal_service_tokens_lock = threading.Lock()
# Watchdog retry budget per game when AI loop exits unsuccessfully
_ai_watchdog_retries = {}
_ai_watchdog_first_scheduled = {}  # game_id -> monotonic timestamp of first retry
_ai_watchdog_lock = threading.Lock()
# Hard wall-clock cap on how long the watchdog will keep retrying a single
# game. Independent of the retry-count cap so a pathologically stuck game
# can't be retried for many minutes if each retry happens to take a while.
_WATCHDOG_MAX_WALL_SECONDS = 120.0
# Lock to prevent multiple AI threads for the same game
_active_games = set()
_active_games_lock = threading.Lock()
_pending_retrigger = set()  # Games that need rechecking after current loop
# Per-game planner telemetry events for debugging/rollout visibility
_planner_events = {}  # game_id -> [event, ...]
_planner_events_lock = threading.Lock()
# Keep event buffers bounded to prevent memory growth.
_MAX_PLANNER_EVENTS_PER_GAME = 80
# Per-game count of consecutive prior change_cards / change_side_cards turns.
# Read by the planner as an anti-cycling penalty so the AI doesn't grind
# multiple turns in a row swapping cards instead of building.
_recent_change_cards: dict[int, int] = {}

_CONQUER_CALL_FIELD_MAP = {
    'Call Villager': 'village',
    'Call Military': 'military',
    'Call King': 'castle',
}

_CONQUER_RED_SUITS = {'Hearts', 'Diamonds'}
_CONQUER_BLACK_SUITS = {'Clubs', 'Spades'}

_CONQUER_AUTO_GAMBLE_THRESHOLD_DEFAULT = 10
_CONQUER_AUTO_GAMBLE_THRESHOLD_MIN = 1
_CONQUER_AUTO_GAMBLE_THRESHOLD_MAX = 20


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



def get_ai_debug_snapshot(game_id, max_notes=20, max_events=40):
    """Return planner telemetry for a game. Used by rollout diagnostics routes.

    `max_notes` is retained for backwards-compatible callers but is now
    ignored: AI decisions are deterministic, so the previous LLM-era strategy
    notes have no equivalent. Planner events remain a useful observability
    surface.
    """
    try:
        max_events = max(1, min(int(max_events), 200))
    except (TypeError, ValueError):
        max_events = 40

    with _planner_events_lock:
        events = list(_planner_events.get(game_id, []))[-max_events:]

    return {
        'planner_events': events,
    }


def _ai_headers(ai_player_id):
    """Return auth headers for requests made on behalf of an AI player."""
    with _ai_player_user_ids_lock:
        ai_user_id = _ai_player_user_ids.get(ai_player_id)
    if ai_user_id is None:
        logger.warning(f"Missing AI user mapping for player_id={ai_player_id}")
        return {}

    headers = get_ai_auth_headers(ai_user_id)
    if headers:
        return headers

    # Conquer-mode defender automation can run on non-AI accounts
    # (player-owned lands defended while owner is offline). Mint an
    # internal long-lived token on demand for those service requests.
    with _internal_service_tokens_lock:
        token = _internal_service_tokens.get(ai_user_id)
        if not token:
            try:
                token = _generate_internal_service_token(ai_user_id)
                _internal_service_tokens[ai_user_id] = token
            except Exception:
                logger.exception(
                    "Failed to generate internal service token for user_id=%s",
                    ai_user_id,
                )
                return {}

    return {'Authorization': f'Bearer {token}'}


def _generate_internal_service_token(user_id):
    """Generate a service token usable by server-internal automation calls."""
    from routes.auth import generate_ai_token
    return generate_ai_token(user_id)


def _make_ai_rng(game_or_seed, iteration):
    """Build a per-iteration random.Random seeded by the game's ai_seed.

    Accepts either a Game ORM instance or an integer seed. If neither is
    available we fall back to a non-deterministic Random — losing replay
    but keeping correctness.
    """
    if isinstance(game_or_seed, int):
        seed = game_or_seed
    else:
        seed = getattr(game_or_seed, 'ai_seed', None)
    if seed is None:
        return random.Random()
    return random.Random(int(seed) * 1_000_003 + int(iteration))


def _clear_watchdog_retry(game_id):
    """Reset watchdog retry counter for a game."""
    with _ai_watchdog_lock:
        _ai_watchdog_retries.pop(game_id, None)
        _ai_watchdog_first_scheduled.pop(game_id, None)


def _schedule_watchdog_retry(app, game_id, ai_player_id, reason):
    """Schedule a delayed AI retrigger when a loop exits unsuccessfully."""
    max_retries = max(int(settings.AI_WATCHDOG_MAX_RETRIES), 0)
    delay_seconds = max(float(settings.AI_WATCHDOG_RETRY_DELAY), 0.0)

    now = time.monotonic()
    with _ai_watchdog_lock:
        first_scheduled = _ai_watchdog_first_scheduled.get(game_id)
        if first_scheduled is None:
            _ai_watchdog_first_scheduled[game_id] = now
            elapsed = 0.0
        else:
            elapsed = now - first_scheduled
        if elapsed > _WATCHDOG_MAX_WALL_SECONDS:
            logger.error(
                f"AI watchdog wall-time cap reached for game {game_id} "
                f"after {elapsed:.1f}s (reason={reason})"
            )
            _ai_watchdog_retries.pop(game_id, None)
            _ai_watchdog_first_scheduled.pop(game_id, None)
            return
        attempt = _ai_watchdog_retries.get(game_id, 0) + 1
        if attempt > max_retries:
            logger.error(
                f"AI watchdog exhausted for game {game_id} "
                f"after {max_retries} retries (reason={reason})"
            )
            _ai_watchdog_first_scheduled.pop(game_id, None)
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


def _conquer_original_attacker_player(game):
    """Return the original conquest attacker, independent of current invader."""
    players = list(getattr(game, 'players', []) or [])
    if not game or not players:
        return None
    from models import LandConfig, Player, db

    conquer_config_id = getattr(game, 'conquer_config_id', None)
    if conquer_config_id:
        cfg = db.session.get(LandConfig, conquer_config_id)
        if cfg:
            player = next((p for p in players if p.user_id == cfg.user_id), None)
            if player:
                return player
    if isinstance(getattr(game, 'last_battle_result', None), dict):
        user_id = game.last_battle_result.get('conquer_attacker_user_id')
        if user_id is not None:
            player = next((p for p in players if p.user_id == user_id), None)
            if player:
                return player
    invader_player_id = getattr(game, 'invader_player_id', None)
    if invader_player_id:
        return db.session.get(Player, invader_player_id)
    return players[0] if players else None


def _conquer_automated_defender_player(game):
    """Return the land defender controlled by the rule-based conquer worker."""
    attacker = _conquer_original_attacker_player(game)
    players = list(getattr(game, 'players', []) or [])
    if attacker and game and players:
        defender = next((p for p in players if p.id != attacker.id), None)
        if defender:
            return defender
    invader_player_id = getattr(game, 'invader_player_id', None)
    if game and invader_player_id is not None:
        return next((p for p in players if p.id != invader_player_id), None)
    return None


def trigger_ai_if_needed(game_id, app=None):
    """
    Check if an AI player needs to act in this game, and if so,
    spawn a background thread to handle it.
    
    Called at the end of state-mutating route handlers.
    This function returns immediately — the AI work happens asynchronously.
    """
    if not settings.AI_ENABLED:
        return

    # Import here to avoid circular imports
    from models import Game, User, db

    # Quick check: does this game have an automated player who needs to act?
    game = db.session.get(Game, game_id)
    if not game or game.state == 'finished':
        return

    automated_player = None
    if game.mode == 'conquer':
        # Conquer uses a scripted defender flow regardless of defender account
        # type (AI or human-owned land config).
        automated_player = _conquer_automated_defender_player(game)
        if automated_player is None:
            logger.warning(
                "AI trigger skipped for conquer game %s: defender player not found",
                game_id,
            )
            return
    else:
        for player in game.players:
            user = db.session.get(User, player.user_id)
            if user and user.is_ai:
                automated_player = player
                break

        if automated_player is None:
            return

    # Cache player->user mapping for auth headers used by background thread.
    with _ai_player_user_ids_lock:
        _ai_player_user_ids[automated_player.id] = automated_player.user_id
    
    # Check if the AI actually needs to act right now
    game_dict = enrich_figures_with_skills(game.serialize())
    if not game_dict:
        logger.warning(f"AI trigger: game.serialize() returned None/empty for game {game_id}")
        return
    try:
        phase = detect_phase(game_dict, automated_player.id)
    except Exception as e:
        logger.error(f"AI trigger: detect_phase crashed for game {game_id}: {e}", exc_info=True)
        return
    if not phase:
        logger.info(f"AI trigger for game {game_id}: no action needed "
                     f"(turn={game_dict.get('turn_player_id')}, actor={automated_player.id})")
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
    
    # Pick the right loop — conquer games use simple rule-based logic
    loop_fn = _conquer_ai_loop if game.mode == 'conquer' else _ai_game_loop

    # Spawn background thread
    thread = threading.Thread(
        target=loop_fn,
        args=(app, game_id, automated_player.id),
        daemon=True,
        name=f"ai-game-{game_id}",
    )
    thread.start()
    logger.info(
        f"AI thread spawned for game {game_id}, phase={phase}, "
        f"mode={game.mode}, actor={automated_player.id}"
    )


def _normalize_conquer_auto_gamble_threshold(value):
    """Clamp conquer auto-gamble threshold to a stable integer range."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = _CONQUER_AUTO_GAMBLE_THRESHOLD_DEFAULT

    if parsed < _CONQUER_AUTO_GAMBLE_THRESHOLD_MIN:
        return _CONQUER_AUTO_GAMBLE_THRESHOLD_MIN
    if parsed > _CONQUER_AUTO_GAMBLE_THRESHOLD_MAX:
        return _CONQUER_AUTO_GAMBLE_THRESHOLD_MAX
    return parsed


def _as_plain_suit(value):
    """Return a plain suit string from raw model/enum values."""
    if value is None:
        return ''
    if hasattr(value, 'value'):
        return str(value.value)
    return str(value)


def _conquer_same_colour(suit_a, suit_b):
    """Return True when both suits are red or both are black."""
    a = _as_plain_suit(suit_a)
    b = _as_plain_suit(suit_b)
    if a in _CONQUER_RED_SUITS and b in _CONQUER_RED_SUITS:
        return True
    if a in _CONQUER_BLACK_SUITS and b in _CONQUER_BLACK_SUITS:
        return True
    return False


def _conquer_battle_ids(game):
    """IDs of figures already engaged in the current battle."""
    return {
        fid for fid in (
            game.advancing_figure_id,
            game.advancing_figure_id_2,
            game.defending_figure_id,
            game.defending_figure_id_2,
        ) if fid is not None
    }


def _get_conquer_auto_gamble_settings(game, ai_player_id):
    """Resolve (enabled, threshold) for conquer auto-gamble runtime."""
    from models import Land, LandConfig, db

    automated_defender = _conquer_automated_defender_player(game)
    cfg_id = (
        game.defence_config_id
        if automated_defender and ai_player_id == automated_defender.id
        else game.conquer_config_id
    )
    if cfg_id:
        cfg = db.session.get(LandConfig, cfg_id)
        if cfg:
            return (
                bool(cfg.auto_gamble),
                _normalize_conquer_auto_gamble_threshold(cfg.auto_gamble_threshold),
            )

    land = game.land if getattr(game, 'land', None) else None
    if not land and game.land_id:
        land = db.session.get(Land, game.land_id)
    if land and land.owner_user_id is None:
        template = get_ai_defence_template_for_land(land)
        return (
            bool(template.get('auto_gamble', False)),
            _normalize_conquer_auto_gamble_threshold(
                template.get('auto_gamble_threshold', _CONQUER_AUTO_GAMBLE_THRESHOLD_DEFAULT)
            )
        )

    return False, _CONQUER_AUTO_GAMBLE_THRESHOLD_DEFAULT


def _conquer_template_counter_spell(game):
    from models import Land, db

    if not game or game.defence_config_id or not game.land_id:
        return None
    land = game.land if getattr(game, 'land', None) else db.session.get(Land, game.land_id)
    if not land or land.owner_user_id is not None:
        return None
    template = get_ai_defence_template_for_land(land)
    return template.get('counter_spell_name') if template else None


def _figure_has_family_skill(figure, skill_name):
    if not figure:
        return False
    if bool(getattr(figure, skill_name, False)):
        return True
    try:
        from ai.figure_recipes import FAMILY_SKILLS
        skills = FAMILY_SKILLS.get(figure.family_name) or FAMILY_SKILLS.get(figure.name) or {}
        return bool(skills.get(skill_name))
    except Exception:
        return False


def _conquer_figure_can_advance(figure, player_id, game_id, *, counter=False):
    if not figure:
        return False
    from models import Game, db
    game = db.session.get(Game, game_id)
    if game and figure.id in set(game.resting_figure_ids or []):
        return False
    modifiers = game.battle_modifier if game and isinstance(game.battle_modifier, list) else []
    from game_service.figure_rule_helpers import modifiers_require_village
    if modifiers_require_village(modifiers) and figure.field != 'village':
        return False
    if _figure_has_family_skill(figure, 'cannot_attack'):
        return False
    if counter and _figure_has_family_skill(figure, 'cannot_defend'):
        return False
    from routes.games import _check_figure_resource_deficit
    if _check_figure_resource_deficit(figure, player_id, game_id):
        return False
    return True


def _conquer_call_candidates(move, all_figures, game_id, player_id, battle_ids, called_ids):
    """Return eligible candidate figures for this Call move."""
    from routes.games import _check_figure_resource_deficit

    target_field = _CONQUER_CALL_FIELD_MAP.get(move.family_name)
    if not target_field:
        return []

    bm_suit = _as_plain_suit(move.suit)
    candidates = []
    for fig in all_figures:
        if fig.player_id != player_id:
            continue
        if (fig.field or '').lower() != target_field:
            continue
        if fig.id in battle_ids:
            continue
        if fig.id in called_ids:
            continue
        if _check_figure_resource_deficit(fig, player_id, game_id):
            continue

        fig_suit = _as_plain_suit(fig.suit)
        if bm_suit in _CONQUER_RED_SUITS and fig_suit not in _CONQUER_RED_SUITS:
            continue
        if bm_suit in _CONQUER_BLACK_SUITS and fig_suit not in _CONQUER_BLACK_SUITS:
            continue
        candidates.append(fig)

    return candidates


def _conquer_move_effective_value(move, call_figure, own_healers):
    """Estimate move strength, matching server-side battle-move valuation."""
    from routes.games import _compute_figure_base_power, _compute_healer_buff

    if not move or move.family_name == 'Block':
        return 0

    base_value = move.value or 0
    if not call_figure:
        return base_value

    fig_power = _compute_figure_base_power(call_figure)
    healer_bonus = _compute_healer_buff(call_figure, own_healers)
    bm_suit = _as_plain_suit(move.suit).lower()
    fig_suit = _as_plain_suit(call_figure.suit).lower()
    if bm_suit == fig_suit:
        return fig_power + healer_bonus + base_value
    return fig_power + healer_bonus


def _conquer_collect_move_infos(game, ai_player_id):
    """Collect unplayed moves with best call target and effective value."""
    from models import BattleMove, ConquerTactic, Figure, db
    from routes.games import _find_healer_figures

    tactics_hand = (getattr(game, 'conquer_move_model', None) or 'battle_move') == 'tactics_hand'
    move_model = ConquerTactic if tactics_hand else BattleMove

    all_figures = Figure.query.filter_by(game_id=game.id).all()
    battle_ids = _conquer_battle_ids(game)

    called_ids = {
        cfid for (cfid,) in db.session.query(move_model.call_figure_id)
        .filter_by(game_id=game.id, player_id=ai_player_id)
        .filter(move_model.played_round.isnot(None))
        .filter(move_model.call_figure_id.isnot(None))
        .all()
    }

    own_healers = _find_healer_figures(ai_player_id, all_figures, battle_ids, game.id)
    query = move_model.query.filter_by(game_id=game.id, player_id=ai_player_id)
    if tactics_hand:
        query = query.filter_by(status='available')
    else:
        query = query.filter(move_model.played_round.is_(None))
    moves = query.order_by(move_model.id).all()

    infos = []
    for move in moves:
        call_figure_id = None
        eff_value = _conquer_move_effective_value(move, None, own_healers)

        if move.family_name in _CONQUER_CALL_FIELD_MAP:
            candidates = _conquer_call_candidates(
                move, all_figures, game.id, ai_player_id, battle_ids, called_ids)

            if not candidates and move.call_figure_id:
                fallback_fig = next(
                    (f for f in all_figures
                     if f.id == move.call_figure_id and f.player_id == ai_player_id),
                    None,
                )
                if fallback_fig:
                    candidates = [fallback_fig]

            best_candidate = None
            best_value = None
            for fig in candidates:
                val = _conquer_move_effective_value(move, fig, own_healers)
                if best_value is None or val > best_value:
                    best_value = val
                    best_candidate = fig

            if best_candidate is not None:
                call_figure_id = best_candidate.id
                eff_value = best_value

        infos.append({
            'move': move,
            'effective_value': int(eff_value or 0),
            'call_figure_id': call_figure_id,
        })

    return infos, all_figures


def _conquer_choose_gamble_target(move_infos, threshold):
    """Pick the weakest non-block move below threshold for gambling."""
    target_pool = []
    for info in move_infos:
        move = info['move']
        if move.family_name in ('Block', 'Double Dagger'):
            continue
        if info['effective_value'] < threshold:
            target_pool.append(info)

    if not target_pool:
        return None

    return min(
        target_pool,
        key=lambda item: (
            int(item.get('effective_value') or 0),
            int(item['move'].value or 0),
            int(item['move'].id),
        ),
    )


def _conquer_choose_best_dagger_pair(moves):
    """Choose the strongest same-colour dagger pair to combine."""
    daggers = [m for m in moves if m.family_name == 'Dagger']
    if len(daggers) < 2:
        return None

    best_pair = None
    best_value = None
    for i, move_a in enumerate(daggers):
        for move_b in daggers[i + 1:]:
            if not _conquer_same_colour(move_a.suit, move_b.suit):
                continue
            combined = int(move_a.value or 0) + int(move_b.value or 0)
            if best_value is None or combined > best_value:
                best_value = combined
                best_pair = (move_a.id, move_b.id)

    return best_pair


def _conquer_opponent_move_value_for_round(game, ai_player_id, current_round, all_figures):
    """Return opponent move effective value in the current round, if known."""
    from models import BattleMove, ConquerTactic, Figure, db
    from routes.games import _find_healer_figures

    tactics_hand = (getattr(game, 'conquer_move_model', None) or 'battle_move') == 'tactics_hand'
    move_model = ConquerTactic if tactics_hand else BattleMove

    opponent = next((p for p in game.players if p.id != ai_player_id), None)
    if not opponent:
        return None

    opp_query = move_model.query.filter_by(
        game_id=game.id,
        player_id=opponent.id,
        played_round=current_round,
    )
    if tactics_hand:
        opp_query = opp_query.filter_by(status='played')
    opp_move = opp_query.first()
    if not opp_move:
        return None

    battle_ids = _conquer_battle_ids(game)
    opp_healers = _find_healer_figures(opponent.id, all_figures, battle_ids, game.id)
    call_fig = None
    if opp_move.call_figure_id:
        call_fig = next((f for f in all_figures if f.id == opp_move.call_figure_id), None)
        if not call_fig:
            call_fig = db.session.get(Figure, opp_move.call_figure_id)

    return _conquer_move_effective_value(opp_move, call_fig, opp_healers)


def _conquer_opponent_played_block_for_round(game, ai_player_id, current_round):
    """Return True when opponent already played Block this round."""
    from models import BattleMove, ConquerTactic

    tactics_hand = (getattr(game, 'conquer_move_model', None) or 'battle_move') == 'tactics_hand'
    move_model = ConquerTactic if tactics_hand else BattleMove

    opponent = next((p for p in game.players if p.id != ai_player_id), None)
    if not opponent:
        return False

    opp_query = move_model.query.filter_by(
        game_id=game.id,
        player_id=opponent.id,
        played_round=current_round,
    )
    if tactics_hand:
        opp_query = opp_query.filter_by(status='played')
    opp_move = opp_query.first()
    if not opp_move:
        return False

    return opp_move.family_name == 'Block'


def _conquer_choose_play_move(move_infos, opponent_round_value):
    """Pick strongest move; optionally prefer Block when strongest is not better."""
    if not move_infos:
        return None

    block_info = next((m for m in move_infos if m['move'].family_name == 'Block'), None)
    non_block = [m for m in move_infos if m['move'].family_name != 'Block']

    strongest = None
    if non_block:
        strongest = max(
            non_block,
            key=lambda item: (
                int(item.get('effective_value') or 0),
                int(item['move'].value or 0),
                -int(item['move'].id),
            ),
        )

    if block_info and strongest is not None and opponent_round_value is not None:
        strongest_advantage = int(strongest['effective_value'] or 0) - int(opponent_round_value or 0)
        if strongest_advantage <= 0:
            return block_info

    if strongest is not None:
        return strongest
    return block_info


def _conquer_choose_weakest_play_move(move_infos):
    """Pick the weakest available move (used to answer opponent Block)."""
    if not move_infos:
        return None

    return min(
        move_infos,
        key=lambda item: (
            int(item.get('effective_value') or 0),
            int(item['move'].value or 0),
            int(item['move'].id),
        ),
    )


def _reload_conquer_game(game_id):
    """Reload a conquer game row with fresh DB state."""
    from models import Game, db

    db.session.expire_all()
    return db.session.get(Game, game_id)


def _conquer_try_finish_battle_if_ready(base, game_id, ai_player_id):
    """Resolve battle when state already transitioned to finish_battle."""
    game = _reload_conquer_game(game_id)
    if not game or not hasattr(game, 'serialize'):
        return False

    game_dict = game.serialize()
    phase = detect_phase(game_dict, ai_player_id)
    if phase != 'finish_battle':
        return False

    resp = _ai_post(f'{base}/games/finish_battle', ai_player_id, json={
        'game_id': game_id,
        'player_id': ai_player_id,
    })
    result = resp.json()
    if result.get('success'):
        logger.info(f"[CONQUER-AI] finish_battle fallback resolved game={game_id}")
        return True

    logger.warning(f"[CONQUER-AI] finish_battle fallback failed game={game_id}: {result.get('message')}")
    return False


def _conquer_skip_battle_turn_with_fallback(base, game, ai_player_id, auto_enabled):
    """Try skipping battle turn; recover from stale-state/race failures."""
    if _exec_skip_battle_turn(base, game.id, ai_player_id):
        return True

    refreshed = _reload_conquer_game(game.id)
    if not refreshed or not hasattr(refreshed, 'serialize'):
        return False

    game_dict = refreshed.serialize()
    phase = detect_phase(game_dict, ai_player_id)

    if phase == 'finish_battle':
        return _conquer_try_finish_battle_if_ready(base, game.id, ai_player_id)

    if phase != 'battle_round':
        logger.info(f"[CONQUER-AI] skip fallback: phase shifted to {phase}, game={game.id}")
        return True

    move_infos, all_figures = _conquer_collect_move_infos(refreshed, ai_player_id)
    if not move_infos:
        logger.warning(f"[CONQUER-AI] skip fallback: still no playable move game={game.id}")
        return False

    current_round = int(refreshed.battle_round or 0)
    opponent_round_value = _conquer_opponent_move_value_for_round(
        refreshed, ai_player_id, current_round, all_figures)
    opponent_played_block = _conquer_opponent_played_block_for_round(
        refreshed, ai_player_id, current_round)

    if auto_enabled and opponent_played_block:
        chosen = _conquer_choose_weakest_play_move(move_infos)
    else:
        chosen = _conquer_choose_play_move(move_infos, opponent_round_value)

    if not chosen:
        logger.warning(f"[CONQUER-AI] skip fallback: no move selected game={game.id}")
        return False

    move = chosen['move']
    params = {'battle_move_id': move.id}
    if chosen.get('call_figure_id'):
        params['call_figure_id'] = chosen['call_figure_id']

    logger.warning(
        f"[CONQUER-AI] skip rejected; playing fallback move game={game.id} move={move.id}"
    )
    tactics_hand = (getattr(refreshed, 'conquer_move_model', None) or 'battle_move') == 'tactics_hand'
    if ((tactics_hand and _exec_play_conquer_tactic(base, game.id, ai_player_id, params))
            or (not tactics_hand and _exec_play_battle_move(base, game.id, ai_player_id, params))):
        return True

    return _conquer_try_finish_battle_if_ready(base, game.id, ai_player_id)


def _conquer_confirm_battle_moves_with_fallback(app, base, game_id, ai_player_id):
    """Try confirm_battle_moves with fallback buy/combine recovery."""
    if _exec_confirm_battle_moves(base, game_id, ai_player_id):
        return True

    game = _reload_conquer_game(game_id)
    if not game or not hasattr(game, 'serialize'):
        return False

    game_dict = enrich_figures_with_skills(game.serialize())
    phase = detect_phase(game_dict, ai_player_id)

    if phase == 'finish_battle':
        return _conquer_try_finish_battle_if_ready(base, game_id, ai_player_id)

    if phase != 'battle_shop':
        logger.info(
            f"[CONQUER-AI] confirm fallback: phase shifted to {phase}, game={game_id}"
        )
        return phase in (None, 'battle_round')

    actions = enumerate_actions(game_dict, ai_player_id, 'battle_shop')
    fallback = next((a for a in actions if a.get('type') == 'buy_battle_move'), None)
    if not fallback:
        fallback = next((a for a in actions if a.get('type') == 'combine_battle_moves'), None)

    if not fallback:
        logger.warning(f"[CONQUER-AI] confirm fallback: no buy/combine option game={game_id}")
        return False

    logger.info(
        f"[CONQUER-AI] confirm fallback executing {fallback.get('type')} game={game_id}"
    )
    return _execute_action(app, game_id, ai_player_id, fallback)


def _conquer_play_battle_round(base, game, ai_player_id):
    """Execute conquer battle-round policy including optional auto-gamble flow."""
    auto_enabled, threshold = _get_conquer_auto_gamble_settings(game, ai_player_id)
    tactics_hand = (getattr(game, 'conquer_move_model', None) or 'battle_move') == 'tactics_hand'
    move_infos, all_figures = _conquer_collect_move_infos(game, ai_player_id)
    if not move_infos:
        logger.info(f"[CONQUER-AI] no unplayed move, skipping turn game={game.id}")
        return _conquer_skip_battle_turn_with_fallback(base, game, ai_player_id, auto_enabled)

    if auto_enabled:
        gamble_target = _conquer_choose_gamble_target(move_infos, threshold)
        if gamble_target:
            gamble_move = gamble_target['move']
            logger.info(
                f"[CONQUER-AI] auto-gamble game={game.id} move={gamble_move.id} "
                f"eff={gamble_target['effective_value']} threshold={threshold}"
            )
            gamble_params = {'battle_move_id': gamble_move.id, 'tactic_id': gamble_move.id}
            if ((tactics_hand and _exec_gamble_conquer_tactic(base, game.id, ai_player_id,
                                                              gamble_params))
                    or (not tactics_hand and _exec_gamble_battle_move(base, game.id, ai_player_id,
                                                                      gamble_params))):
                refreshed = _reload_conquer_game(game.id)
                if refreshed:
                    game = refreshed
                move_infos, all_figures = _conquer_collect_move_infos(game, ai_player_id)
                if not move_infos:
                    logger.info(f"[CONQUER-AI] no moves after gamble, skipping game={game.id}")
                    return _conquer_skip_battle_turn_with_fallback(base, game, ai_player_id, auto_enabled)

        dagger_pair = _conquer_choose_best_dagger_pair([info['move'] for info in move_infos])
        if dagger_pair:
            logger.info(
                f"[CONQUER-AI] auto-combine daggers game={game.id} pair={dagger_pair[0]},{dagger_pair[1]}"
            )
            combine_params = {'move_id_a': dagger_pair[0], 'move_id_b': dagger_pair[1]}
            if ((tactics_hand and _exec_combine_conquer_tactics(
                    base, game.id, ai_player_id, combine_params))
                    or (not tactics_hand and _exec_combine_battle_moves(
                        base, game.id, ai_player_id, combine_params))):
                refreshed = _reload_conquer_game(game.id)
                if refreshed:
                    game = refreshed
                move_infos, all_figures = _conquer_collect_move_infos(game, ai_player_id)
                if not move_infos:
                    logger.info(f"[CONQUER-AI] no moves after combine, skipping game={game.id}")
                    return _conquer_skip_battle_turn_with_fallback(base, game, ai_player_id, auto_enabled)

    current_round = int(game.battle_round or 0)
    opponent_round_value = _conquer_opponent_move_value_for_round(
        game, ai_player_id, current_round, all_figures)
    opponent_played_block = _conquer_opponent_played_block_for_round(
        game, ai_player_id, current_round)

    if auto_enabled and opponent_played_block:
        chosen = _conquer_choose_weakest_play_move(move_infos)
    else:
        chosen = _conquer_choose_play_move(move_infos, opponent_round_value)

    if not chosen:
        logger.info(f"[CONQUER-AI] no playable decision, skipping turn game={game.id}")
        return _conquer_skip_battle_turn_with_fallback(base, game, ai_player_id, auto_enabled)

    move = chosen['move']
    params = {'battle_move_id': move.id}
    if chosen.get('call_figure_id'):
        params['call_figure_id'] = chosen['call_figure_id']

    logger.info(
        f"[CONQUER-AI] play game={game.id} move={move.id} family={move.family_name} "
        f"eff={chosen['effective_value']} opp_eff={opponent_round_value} "
        f"call={chosen.get('call_figure_id')} auto={auto_enabled} threshold={threshold} "
        f"opp_block={opponent_played_block}"
    )
    if ((tactics_hand and _exec_play_conquer_tactic(base, game.id, ai_player_id, params))
            or (not tactics_hand and _exec_play_battle_move(base, game.id, ai_player_id, params))):
        return True
    return _conquer_try_finish_battle_if_ready(base, game.id, ai_player_id)


def _conquer_should_cast_counter_spell(game, ai_player_id):
    """Return True when this defender response should use its configured counter spell.

    Returns False when Invader Swap is active because the counter spell is
    ignored after the role swap (see plan section 7).
    """
    if not game or game.mode != 'conquer':
        return False
    # After Invader Swap the AI may now be the invader — counter spell
    # is only cast by the defender, and is always ignored after swap anyway.
    from routes.games import _conquer_invader_swap_active
    if _conquer_invader_swap_active(game):
        return False
    automated_defender = _conquer_automated_defender_player(game)
    if automated_defender and automated_defender.id != ai_player_id:
        return False
    if not game.advancing_figure_id or game.advancing_player_id == ai_player_id:
        return False
    if game.defending_figure_id:
        return False
    from models import LandConfig, LandConfigFigure, LogEntry, db
    cfg = db.session.get(LandConfig, game.defence_config_id) if game.defence_config_id else None
    counter_spell_name = cfg.counter_spell_name if cfg else _conquer_template_counter_spell(game)
    if not counter_spell_name:
        return False
    if counter_spell_name == 'Explosion':
        return False
    # Civil War: only cast a counter spell on the first advance per round.
    already_cast = LogEntry.query.filter_by(
        game_id=game.id,
        player_id=ai_player_id,
        round_number=game.current_round,
        type='counter_spell',
    ).first()
    if already_cast:
        return False
    if not cfg:
        return counter_spell_name in {'Dump Cards', 'Forced Deal', 'Poison', 'Health Boost'}
    if counter_spell_name == 'Health Boost':
        target = db.session.get(LandConfigFigure, cfg.counter_spell_target_figure_id)
        return bool(target and target.config_id == cfg.id and not getattr(target, 'checkmate', False))
    return counter_spell_name in {'Dump Cards', 'Forced Deal', 'Poison'}


def _conquer_pick_counter_advance_figure(game, ai_player_id):
    """Pick the next legal automated conquer figure.

    Normally this selects a counter-advance defender.  After Invader Swap the
    same original land defender may be the current invader, so normal advance
    eligibility must not reject figures with ``cannot_defend``.

    After Invader Swap and when the AI is the new invader, this function picks
    the advance figure using defence-config priority: configured battle figure
    first (if legal), then strongest legal figure by power proxy.
    """
    from models import Figure, LandConfig, db
    from routes.games import _conquer_invader_swap_active
    modifiers = game.battle_modifier if isinstance(game.battle_modifier, list) else []
    has_civil_war = any(m.get('type') == 'Civil War' for m in modifiers)

    # After Invader Swap: AI is the new invader advancing for the first time
    swap_active = _conquer_invader_swap_active(game)
    is_new_invader_after_swap = (
        swap_active
        and game.invader_player_id == ai_player_id
        and not game.advancing_figure_id
    )

    def _configured_defence_game_figure(cfg_figure_id):
        if not cfg_figure_id:
            return None
        return Figure.query.filter_by(
            game_id=game.id,
            player_id=ai_player_id,
            source_config_figure_id=cfg_figure_id,
        ).first()

    def _defence_config():
        if not game.defence_config_id:
            return None
        return db.session.get(LandConfig, game.defence_config_id)

    if is_new_invader_after_swap:
        # Try configured defence battle figure first
        cfg = _defence_config()
        if cfg and cfg.battle_figure_id:
            game_fig = _configured_defence_game_figure(cfg.battle_figure_id)
            if game_fig and _conquer_figure_can_advance(
                game_fig, ai_player_id, game.id, counter=False
            ):
                return game_fig.id

        # Fallback: strongest legal advance figure (proxy: sum of card values)
        candidates = Figure.query.filter_by(
            game_id=game.id,
            player_id=ai_player_id,
        ).all()
        legal = [
            f for f in candidates
            if _conquer_figure_can_advance(f, ai_player_id, game.id, counter=False)
        ]
        if not legal:
            return None
        def _figure_power_proxy(fig):
            try:
                card_sum = sum(
                    c.card.value for c in fig.cards
                    if c.card and hasattr(c.card, 'value') and c.card.value
                )
            except Exception:
                card_sum = 0
            return (card_sum, -(fig.id))
        legal.sort(key=_figure_power_proxy, reverse=True)
        return legal[0].id

    is_counter = bool(game.advancing_figure_id and game.advancing_player_id != ai_player_id)

    def _pick_second(first_id, preferred_config_figure_id=None):
        first = Figure.query.filter_by(
            id=first_id,
            game_id=game.id,
            player_id=ai_player_id,
        ).first()
        if not first:
            return None
        preferred = _configured_defence_game_figure(preferred_config_figure_id)
        if (
            preferred
            and preferred.id != first.id
            and preferred.field == 'village'
            and preferred.color == first.color
            and _conquer_figure_can_advance(
                preferred,
                ai_player_id,
                game.id,
                counter=is_counter,
            )
        ):
            return preferred.id
        second_candidates = Figure.query.filter(
            Figure.game_id == game.id,
            Figure.player_id == ai_player_id,
            Figure.id != first.id,
            Figure.field == 'village',
            Figure.color == first.color,
        ).order_by(Figure.id.asc()).all()
        for second in second_candidates:
            if _conquer_figure_can_advance(
                second,
                ai_player_id,
                game.id,
                counter=is_counter,
            ):
                return second.id
        return None

    if has_civil_war and is_counter and game.defending_figure_id and not game.defending_figure_id_2:
        cfg = _defence_config()
        preferred_id = cfg.battle_figure_id_2 if cfg else None
        return _pick_second(game.defending_figure_id, preferred_id)

    if has_civil_war and not is_counter and game.advancing_figure_id \
            and game.advancing_player_id == ai_player_id \
            and not game.advancing_figure_id_2:
        cfg = _defence_config() if swap_active and game.invader_player_id == ai_player_id else None
        preferred_id = cfg.battle_figure_id_2 if cfg else None
        return _pick_second(game.advancing_figure_id, preferred_id)

    if is_counter and game.defending_figure_id:
        fig = Figure.query.filter_by(
            id=game.defending_figure_id,
            game_id=game.id,
            player_id=ai_player_id,
        ).first()
        if _conquer_figure_can_advance(fig, ai_player_id, game.id, counter=True):
            return fig.id
        logger.info(
            "[CONQUER-AI] configured defender figure invalid for counter-advance; "
            "falling back to another candidate game=%s figure_id=%s",
            game.id,
            game.defending_figure_id,
        )

    candidates = Figure.query.filter_by(
        game_id=game.id,
        player_id=ai_player_id,
    ).order_by(Figure.id.asc()).all()
    # Prefer the configured battle figure (when set on the defence config)
    # before falling back to the first eligible figure by id ascending.  This
    # respects the defender's strategy choice for the both-selected case.
    cfg = _defence_config()
    preferred_cfg_fig_id = cfg.battle_figure_id if cfg else None
    if preferred_cfg_fig_id:
        preferred = _configured_defence_game_figure(preferred_cfg_fig_id)
        if preferred and _conquer_figure_can_advance(
            preferred, ai_player_id, game.id, counter=is_counter
        ):
            return preferred.id
    for fig in candidates:
        if _conquer_figure_can_advance(fig, ai_player_id, game.id, counter=is_counter):
            return fig.id
    return None


def _conquer_civil_war_second_pick_pending(game, ai_player_id):
    """True when the AI holds the turn only to pick/skip a second Civil War figure.

    Covers both sides: the defender counter-advance second pick (first
    defender chosen, second missing) and the post-Invader-Swap advancing
    second pick (first attacker chosen, second missing).  In this state the
    server keeps the turn with the AI until it either advances a second
    figure or calls skip_civil_war_second — anything else stalls the game.
    """
    if not game or game.mode != 'conquer':
        return False
    modifiers = game.battle_modifier if isinstance(game.battle_modifier, list) else []
    if not any(m.get('type') == 'Civil War' for m in modifiers):
        return False
    if game.turn_player_id != ai_player_id or not game.advancing_figure_id:
        return False
    if (game.advancing_player_id != ai_player_id
            and game.defending_figure_id
            and not game.defending_figure_id_2):
        return True
    if (game.advancing_player_id == ai_player_id
            and not game.advancing_figure_id_2):
        return True
    return False


def _conquer_ai_loop(app, game_id, ai_player_id):
    """Rule-based defender auto-play for conquer-mode games.

    Unlike the LLM-backed ``_ai_game_loop``, this loop makes deterministic
    decisions: always counter-advance with the pre-configured battle figure,
    always fight (never fold), auto-confirm pre-populated battle moves, and
    play battle rounds via strongest-move policy (optionally using auto-gamble).
    """
    try:
        time.sleep(max(settings.AI_THINK_DELAY * 0.5, 0.3))
        base = settings.SERVER_URL
        max_iterations = 20

        for iteration in range(max_iterations):
            with app.app_context():
                from models import Game, Player, Figure, BattleMove, db
                game = db.session.get(Game, game_id)
                if not game or game.state == 'finished':
                    logger.info(f"[CONQUER-AI] game {game_id} finished/gone")
                    break

                game_dict = game.serialize()

            phase = detect_phase(game_dict, ai_player_id)
            if not phase:
                # Brief wait for turn flip race
                time.sleep(1)
                with app.app_context():
                    from models import Game, db
                    game = db.session.get(Game, game_id)
                    if game and game.state != 'finished':
                        phase = detect_phase(game.serialize(), ai_player_id)
                if not phase:
                    logger.info(f"[CONQUER-AI] no action for game {game_id}")
                    break

            logger.info(f"[CONQUER-AI] game={game_id} phase={phase} iter={iteration}")
            time.sleep(0.3)  # Small delay for realism

            if phase == 'normal_turn':
                # Defender response: configured counter spells replace counter-advance.
                with app.app_context():
                    from models import Game, db
                    game = db.session.get(Game, game_id)
                    should_cast_counter = _conquer_should_cast_counter_spell(game, ai_player_id)
                    fig_id = None if should_cast_counter else _conquer_pick_counter_advance_figure(game, ai_player_id)
                    is_current_invader = bool(game and game.invader_player_id == ai_player_id)
                    cw_second_pick_pending = _conquer_civil_war_second_pick_pending(game, ai_player_id)

                if should_cast_counter:
                    resp = _ai_post(f'{base}/games/conquer_defender_counter_spell',
                                    ai_player_id, json={
                                        'game_id': game_id,
                                        'player_id': ai_player_id,
                                    })
                    if resp.ok:
                        continue
                    # Only fall back to counter-advance if the response window
                    # is still open.  For race conditions such as 'Defender
                    # already selected' or 'Not your turn', stop and let the
                    # next loop iteration re-detect the phase.
                    fallback_safe = False
                    try:
                        err_msg = (resp.json() or {}).get('message', '')
                    except Exception:
                        err_msg = ''
                    logger.warning(
                        f"[CONQUER-AI] counter spell failed ({resp.status_code}): {err_msg}"
                    )
                    with app.app_context():
                        from models import Game, db
                        game = db.session.get(Game, game_id)
                        if game and game.mode == 'conquer' and game.state != 'finished':
                            fallback_safe = (
                                game.advancing_figure_id is not None
                                and game.advancing_player_id != ai_player_id
                                and game.defending_figure_id is None
                                and game.turn_player_id == ai_player_id
                            )
                            fig_id = (
                                _conquer_pick_counter_advance_figure(game, ai_player_id)
                                if fallback_safe else None
                            )
                    if not fallback_safe:
                        logger.info(
                            f"[CONQUER-AI] response window closed; skipping counter-advance fallback"
                        )
                        continue

                if fig_id:
                    advanced = _exec_advance_figure(base, game_id, ai_player_id,
                                                    {'figure_id': fig_id})
                    if not advanced and cw_second_pick_pending:
                        # Second Civil War pick was rejected — skip it rather
                        # than stalling the game with the turn stuck on the AI.
                        logger.info(
                            f"[CONQUER-AI] second Civil War pick rejected; "
                            f"skipping second figure, game={game_id}"
                        )
                        _exec_skip_civil_war_second(base, game_id, ai_player_id)
                elif cw_second_pick_pending:
                    # No legal second Civil War figure — skip so the turn
                    # returns to the opponent and the battle can proceed.
                    logger.info(
                        f"[CONQUER-AI] no second Civil War figure available; "
                        f"skipping second pick, game={game_id}"
                    )
                    _exec_skip_civil_war_second(base, game_id, ai_player_id)
                else:
                    if is_current_invader:
                        _exec_cannot_advance_loss(base, game_id, ai_player_id)
                        break
                    logger.warning(f"[CONQUER-AI] no figure to advance, game={game_id}")
                    break

            elif phase == 'select_defender':
                # AI picks opponent figure — for normal conquer: choose first available.
                # After Invader Swap with a cannot_be_blocked advance: use
                # field-priority selection (village → military → castle).
                with app.app_context():
                    from models import Game, Player, Figure, db
                    from routes.games import (
                        _conquer_invader_swap_active,
                        _defender_selection_ignores_must_be_attacked,
                        _figure_can_be_selected_as_defender,
                    )
                    from game_service.figure_rule_helpers import modifiers_require_village
                    game = db.session.get(Game, game_id)
                    opp_player = Player.query.filter(
                        Player.game_id == game_id,
                        Player.id != ai_player_id
                    ).first()
                    fig_id = None
                    no_legal_defender = False
                    if opp_player and game:
                        opp_figs = Figure.query.filter_by(
                            game_id=game_id, player_id=opp_player.id
                        ).all()
                        modifiers = game.battle_modifier if isinstance(game.battle_modifier, list) else []
                        village_only = modifiers_require_village(modifiers)
                        valid_figs = [
                            f for f in opp_figs
                            if _figure_can_be_selected_as_defender(f)
                            and (not village_only or f.field == 'village')
                        ]
                        # Check if this is an Invader Swap + unblockable advance
                        swap_unblockable = (
                            _conquer_invader_swap_active(game)
                            and game.advancing_figure_id
                        )
                        adv_fig = db.session.get(Figure, game.advancing_figure_id) if game.advancing_figure_id else None
                        if swap_unblockable and adv_fig and getattr(adv_fig, 'cannot_be_blocked', False):
                            # Server rejects checkmate defenders while a
                            # non-checkmate alternative exists — mirror that.
                            non_checkmate = [
                                f for f in valid_figs
                                if not getattr(f, 'checkmate', False)
                            ]
                            swap_pool = non_checkmate or valid_figs
                            # Field-priority selection: village → military → castle
                            rng = _make_ai_rng(game, iteration)
                            for field_priority in ('village', 'military', 'castle'):
                                pool = [f for f in swap_pool if f.field == field_priority]
                                if pool:
                                    fig_id = rng.choice(pool).id
                                    break
                            if not fig_id and swap_pool:
                                fig_id = rng.choice(swap_pool).id
                        else:
                            # Mirror the server selection rules so the pick is
                            # never rejected in a loop: must_be_attacked figures
                            # take priority (unless bypassed), checkmate figures
                            # are a last resort.
                            candidates = list(valid_figs)
                            if not _defender_selection_ignores_must_be_attacked(game):
                                forced = [
                                    f for f in candidates
                                    if _figure_has_family_skill(f, 'must_be_attacked')
                                    and not getattr(f, 'checkmate', False)
                                ]
                                if forced:
                                    candidates = forced
                            non_checkmate = [
                                f for f in candidates
                                if not getattr(f, 'checkmate', False)
                            ]
                            pick_pool = non_checkmate or candidates
                            fig_id = pick_pool[0].id if pick_pool else None
                        no_legal_defender = not fig_id
                if fig_id:
                    _exec_select_defender(base, game_id, ai_player_id,
                                          {'figure_id': fig_id})
                elif no_legal_defender:
                    # Opponent has no selectable figure (e.g. no village
                    # figures under Civil/Peasant War) — resolve as defender
                    # auto-loss instead of stalling in this phase forever.
                    logger.info(
                        f"[CONQUER-AI] no legal defender to select; "
                        f"triggering defender auto-loss, game={game_id}"
                    )
                    _exec_defender_no_figures_loss(base, game_id, ai_player_id)
                    break

            elif phase == 'battle_decision':
                _exec_battle_decision(base, game_id, ai_player_id,
                                      {'decision': 'battle'})

            elif phase == 'battle_shop':
                _conquer_confirm_battle_moves_with_fallback(
                    app, base, game_id, ai_player_id
                )

            elif phase == 'battle_round':
                # Deterministic policy: optional auto-gamble/auto-combine,
                # then strongest move with Block tie-break logic.
                with app.app_context():
                    from models import Game, db
                    game = db.session.get(Game, game_id)
                    if game:
                        if not _conquer_play_battle_round(base, game, ai_player_id):
                            _conquer_try_finish_battle_if_ready(base, game_id, ai_player_id)

            elif phase == 'finish_battle':
                _ai_post(f'{base}/games/finish_battle', ai_player_id, json={
                    'game_id': game_id, 'player_id': ai_player_id,
                })

            elif phase == 'post_battle_pick':
                # AI won — pick arbitrary card
                with app.app_context():
                    from models import Game, db
                    game = db.session.get(Game, game_id)
                    returnable = game.serialize().get('returnable_cards', [])
                    card_id = returnable[0]['id'] if returnable else None
                if card_id:
                    _ai_post(f'{base}/games/finish_battle_pick_card',
                             ai_player_id, json={
                                 'game_id': game_id,
                                 'player_id': ai_player_id,
                                 'card_id': card_id,
                             })

            elif phase == 'counter_spell':
                # Always allow spells
                _exec_allow_spell(base, game_id, ai_player_id, {
                    'pending_spell_id': game_dict.get('pending_spell_id'),
                })

            else:
                logger.warning(f"[CONQUER-AI] unhandled phase {phase}, game={game_id}")
                break

    except Exception:
        logger.error(f"[CONQUER-AI] crash in game {game_id}", exc_info=True)
    finally:
        retrigger = False
        with _active_games_lock:
            _active_games.discard(game_id)
            if game_id in _pending_retrigger:
                _pending_retrigger.discard(game_id)
                retrigger = True
        if retrigger:
            logger.info(f"[CONQUER-AI] processing pending retrigger for game {game_id}")
            with app.app_context():
                trigger_ai_if_needed(game_id, app=app)


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
                    with _planner_events_lock:
                        _planner_events.pop(game_id, None)
                    _recent_change_cards.pop(game_id, None)
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
            
            # If only one action, take it without consulting the strategy module.
            if len(actions) == 1:
                chosen = actions[0]
                logger.info(f"AI auto-choosing only action: {chosen['type']}")
            else:
                rng = _make_ai_rng(game_dict.get('ai_seed'), iteration)
                planner_context = {
                    'recent_change_cards_count': _recent_change_cards.get(game_id, 0),
                }
                chosen = duel_strategy.choose_action(
                    game_dict, ai_player_id, phase, actions, rng,
                    context=planner_context,
                )

            # Execute the chosen action
            success = _execute_action(app, game_id, ai_player_id, chosen)
            if not success:
                logger.warning(f"AI action failed: {chosen['type']} in game {game_id}")
                # Track already-tried (and failed) action IDs so we never pick
                # the same dead action twice in this loop iteration.
                tried_ids = {chosen['id']}
                fallback_success = False
                # First: other actions of the same type (e.g., next defender target).
                for alt in actions:
                    if alt['id'] in tried_ids or alt['type'] != chosen['type']:
                        continue
                    logger.info(f"AI trying alternative: {alt['type']} — {alt['description'][:60]}")
                    tried_ids.add(alt['id'])
                    if _execute_action(app, game_id, ai_player_id, alt):
                        fallback_success = True
                        break
                # Phase-specific fallbacks to a different action type.
                if not fallback_success and chosen['type'] == 'build_figure':
                    fallback = next(
                        (a for a in actions
                         if a['type'] == 'change_cards' and a['id'] not in tried_ids),
                        None,
                    )
                    if fallback:
                        logger.info("AI falling back to change_cards")
                        tried_ids.add(fallback['id'])
                        fallback_success = _execute_action(app, game_id, ai_player_id, fallback)
                if not fallback_success and chosen['type'] == 'confirm_battle_moves':
                    buy_action = next(
                        (a for a in actions
                         if a['type'] == 'buy_battle_move' and a['id'] not in tried_ids),
                        None,
                    )
                    if buy_action:
                        logger.info("AI confirm failed, falling back to buy_battle_move")
                        tried_ids.add(buy_action['id'])
                        fallback_success = _execute_action(app, game_id, ai_player_id, buy_action)
                # Last-resort generic fallback: pick the next best action via the
                # strategy module from the actions we haven't tried yet. This
                # prevents a single permanently-failing action (e.g. legal-looking
                # but server-rejected) from emptying the watchdog budget.
                if not fallback_success:
                    remaining = [a for a in actions if a['id'] not in tried_ids]
                    if remaining and len(remaining) != len(actions):
                        rng = _make_ai_rng(
                            game_dict.get('ai_seed'),
                            iteration * 1000 + len(tried_ids),
                        )
                        try:
                            retry = duel_strategy.choose_action(
                                game_dict, ai_player_id, phase, remaining, rng,
                            )
                        except Exception as _err:  # pragma: no cover - safety
                            retry = remaining[0]
                        logger.info(
                            f"AI retrying with next-best action: {retry['type']} "
                            f"— {retry['description'][:60]}"
                        )
                        tried_ids.add(retry['id'])
                        fallback_success = _execute_action(
                            app, game_id, ai_player_id, retry,
                        )
                if not fallback_success:
                    unsuccessful_exit = True
                    break
                # Fallback action succeeded — recovery path, not a clean
                # cycle; reset the anti-cycling counter and continue.
                _recent_change_cards[game_id] = 0
                time.sleep(settings.AI_THINK_DELAY)
                continue

            _clear_watchdog_retry(game_id)

            # Track consecutive change_cards / change_side_cards turns so the
            # planner can apply an anti-cycling penalty next turn.
            if chosen['type'] in ('change_cards', 'change_side_cards'):
                _recent_change_cards[game_id] = _recent_change_cards.get(game_id, 0) + 1
            else:
                _recent_change_cards[game_id] = 0

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
        elif action_type == 'change_side_cards':
            return _exec_change_side_cards(app, game_id, ai_player_id)
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
        elif action_type == 'gamble_conquer_tactic':
            return _exec_gamble_conquer_tactic(base, game_id, ai_player_id, params)
        elif action_type == 'combine_battle_moves':
            return _exec_combine_battle_moves(base, game_id, ai_player_id, params)
        elif action_type == 'combine_conquer_tactics':
            return _exec_combine_conquer_tactics(base, game_id, ai_player_id, params)
        elif action_type == 'play_battle_move':
            return _exec_play_battle_move(base, game_id, ai_player_id, params)
        elif action_type == 'play_conquer_tactic':
            return _exec_play_conquer_tactic(base, game_id, ai_player_id, params)
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
        elif action_type == 'defender_no_figures_loss':
            return _exec_defender_no_figures_loss(base, game_id, ai_player_id)
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
    suggestion and executed card selection stay aligned.  Cards needed for
    the AI's top figure-building targets are protected from swapping.
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

        # Compute tactic-protected card IDs from top figure targets
        game_dict = enrich_figures_with_skills(game.serialize())
    
    if not free_cards:
        logger.warning("No cards to change")
        return False

    from ai.figure_completion import best_figure_targets
    targets = best_figure_targets(game_dict, ai_player_id, max_results=3)
    # Serialize free cards as dicts for the target matcher
    free_dicts = [{'id': c.id, 'rank': c.rank.value if hasattr(c.rank, 'value') else c.rank, 'suit': c.suit.value if hasattr(c.suit, 'value') else c.suit, 'value': c.value} for c in free_cards]
    protect_ids = compute_tactic_protected_ids(free_dicts, targets, max_targets=3)

    if protect_ids:
        logger.info(f"Tactic-protected card IDs: {protect_ids}")

    summary = summarize_main_change(free_cards, protect_ids=protect_ids)
    to_swap = select_main_cards_to_swap(free_cards, protect_ids=protect_ids)

    logger.info(f"Smart change: swapping {len(to_swap)} of {len(free_cards)} cards "
                f"(keeping {len(free_cards) - len(to_swap)} cards, "
                f"tactic_protected={len(protect_ids)}, "
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


def _exec_change_side_cards(app, game_id, ai_player_id):
    """Change side cards via POST /games/change_cards with card_type='side'.

    Mirrors ``_exec_change_cards`` but operates on the side hand.
    """
    with app.app_context():
        from models import Game, SideCard, db
        game = db.session.get(Game, game_id)
        if not game:
            return False

        hand_cards = SideCard.query.filter_by(
            player_id=ai_player_id,
            in_deck=False,
        ).all()

        free_cards = [c for c in hand_cards
                      if not c.part_of_figure and not c.part_of_battle_move]

        game_dict = enrich_figures_with_skills(game.serialize())

    if not free_cards:
        logger.warning("No side cards to change")
        return False

    from ai.figure_completion import best_figure_targets
    targets = best_figure_targets(game_dict, ai_player_id, max_results=3)
    free_dicts = [{'id': c.id, 'rank': c.rank.value if hasattr(c.rank, 'value') else c.rank,
                   'suit': c.suit.value if hasattr(c.suit, 'value') else c.suit,
                   'value': c.value} for c in free_cards]
    protect_ids = compute_side_tactic_protected_ids(free_dicts, targets, max_targets=3)

    if protect_ids:
        logger.info(f"Side tactic-protected card IDs: {protect_ids}")

    summary = summarize_side_change(free_cards, protect_ids=protect_ids)
    to_swap = select_side_cards_to_swap(free_cards, protect_ids=protect_ids)

    logger.info(f"Smart side change: swapping {len(to_swap)} of {len(free_cards)} side cards "
                f"(keeping {len(free_cards) - len(to_swap)} cards, "
                f"tactic_protected={len(protect_ids)}, "
                f"swap_count={summary.get('swap_count', 0)})")

    base = settings.SERVER_URL
    resp = _ai_post(f'{base}/games/change_cards', ai_player_id, json={
        'game_id': game_id,
        'player_id': ai_player_id,
        'cards': [{'id': cid} for cid in to_swap],
        'card_type': 'side',
    }, timeout=15)
    result = resp.json()
    if result.get('success'):
        logger.info(f"Changed {len(to_swap)} side cards")
        return True
    logger.warning(f"Change side cards failed: {result.get('message')}")
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


def _exec_gamble_conquer_tactic(base, game_id, ai_player_id, params):
    """Gamble a conquer tactic via POST /games/gamble_conquer_tactic."""
    tactic_id = params.get('tactic_id') or params.get('battle_move_id')
    resp = _ai_post(f'{base}/games/gamble_conquer_tactic', ai_player_id, json={
        'game_id': game_id,
        'player_id': ai_player_id,
        'tactic_id': tactic_id,
    }, timeout=15)
    result = resp.json()
    if result.get('success'):
        new_moves = result.get('new_tactics') or result.get('new_moves') or []
        new_desc = ', '.join(f"{m.get('family_name','?')}({m.get('value','?')})" for m in new_moves)
        logger.info(f"Gambled conquer tactic {tactic_id} → drew: {new_desc}")
        return True
    logger.warning(f"Gamble conquer tactic failed: {result.get('message')}")
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


def _exec_combine_conquer_tactics(base, game_id, ai_player_id, params):
    """Combine two conquer tactics via POST /games/combine_conquer_tactics."""
    resp = _ai_post(f'{base}/games/combine_conquer_tactics', ai_player_id, json={
        'game_id': game_id,
        'player_id': ai_player_id,
        'tactic_id_a': params['move_id_a'],
        'tactic_id_b': params['move_id_b'],
    }, timeout=15)
    result = resp.json()
    if result.get('success'):
        combined = result.get('combined_tactic') or result.get('combined_move') or {}
        logger.info(f"Combined conquer tactics into Double Dagger (value={combined.get('value','?')})")
        return True
    logger.warning(f"Combine conquer tactics failed: {result.get('message')}")
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


def _exec_play_conquer_tactic(base, game_id, ai_player_id, params):
    """Play a conquer tactic via POST /games/play_conquer_tactic."""
    tactic_id = params.get('tactic_id') or params.get('battle_move_id')
    payload = {
        'game_id': game_id,
        'player_id': ai_player_id,
        'tactic_id': tactic_id,
    }
    call_figure_id = params.get('call_figure_id')
    if call_figure_id:
        payload['call_figure_id'] = call_figure_id
    resp = _ai_post(f'{base}/games/play_conquer_tactic', ai_player_id, json=payload, timeout=15)
    result = resp.json()
    if result.get('success'):
        logger.info(f"Played conquer tactic {tactic_id} (call_figure_id={call_figure_id})")
        return True
    logger.warning(f"Play conquer tactic failed: {result.get('message')}")
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


def _exec_defender_no_figures_loss(base, game_id, ai_player_id):
    """Trigger defender auto-loss when no legal defender can be selected."""
    resp = _ai_post(f'{base}/games/defender_no_figures_loss', ai_player_id, json={
        'game_id': game_id,
        'player_id': ai_player_id,
    }, timeout=15)
    result = resp.json()
    if result.get('success'):
        logger.info("Defender has no legal figures — auto-loss triggered")
        return True
    logger.warning(f"Defender no-figures loss failed: {result.get('message')}")
    return False


def _exec_skip_civil_war_second(base, game_id, ai_player_id, context='advance'):
    """Skip the optional second Civil War figure via POST /games/skip_civil_war_second.

    Used as a deadlock escape: when the server keeps the turn on the AI for
    an optional second Civil War pick but no legal second figure can be
    played, skipping hands the turn back instead of stalling the game.
    """
    resp = _ai_post(f'{base}/games/skip_civil_war_second', ai_player_id, json={
        'game_id': game_id,
        'player_id': ai_player_id,
        'context': context,
    }, timeout=15)
    result = resp.json()
    if result.get('success'):
        logger.info("Skipped second Civil War figure")
        return True
    logger.warning(f"Skip Civil War second failed: {result.get('message')}")
    return False
