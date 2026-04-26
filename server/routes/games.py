# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
from flask import Blueprint, request, jsonify, current_app, g
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.attributes import flag_modified
import random
import logging
from datetime import datetime, timezone, timedelta
from models import db, User, Challenge, ChallengeStatus, Player, Game, MainCard, SideCard, Figure, CardToFigure, CardRole, LogEntry, ChatMessage, BattleMove, ActiveSpell, GameResult, Land, LandAttackLog, LandConfig, LandConfigFigure, CollectionCard
from game_service.deck_manager import DeckManager
from routes.auth import require_token, verify_player_ownership

import server_settings as settings

logger = logging.getLogger('nepalkings.routes.games')

games = Blueprint('games', __name__)

_ai_logger = logging.getLogger('nepalkings.ai.trigger')

_CONQUER_PRELUDE_SPELLS = frozenset({
    'Draw 2 MainCards', 'Fill up to 10', 'Dump Cards', 'Forced Deal',
    'Poison', 'Health Boost', 'All Seeing Eye', 'Explosion',
    'Peasant War', 'Civil War', 'Blitzkrieg',
})

_TARGETED_PRELUDE_SPELLS = frozenset({'Poison', 'Health Boost', 'Explosion'})

# LogEntry.type values that count as the current player having interacted
# with the game.  Used to decide whether to show the conquer/duel intro and
# whether prelude side-effect logs (figure_destroyed, etc.) may preempt it.
_USER_ACTION_LOG_TYPES = (
    'figure_built', 'figure_upgraded', 'figure_pickup',
    'card_changed', 'spell_cast', 'spell_end', 'counter_spell',
    'battle_move', 'battle_skip', 'battle_decision', 'battle_start',
    'battle_win', 'battle_draw',
    'advance', 'counter_advance',
    'auto_loss', 'fold_win', 'deficit_loss', 'civil_war_skip',
    'game_start',
)


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _defender_already_cast_counter_this_round(game, defender_player_id):
    """True if the defender already cast a counter spell this round.

    Used to keep counter spells one-per-battle-round even when the round
    contains multiple advances (Civil War).  We rely on the LogEntry record
    of type ``counter_spell`` so the gate also covers no-valid-target casts
    that did not produce an ActiveSpell row.
    """
    if not game or not defender_player_id:
        return False
    return LogEntry.query.filter_by(
        game_id=game.id,
        player_id=defender_player_id,
        round_number=game.current_round,
        type='counter_spell',
    ).first() is not None


def _conquer_defender_counter_advance_disabled(game):
    """Return True when conquer defender auto counter-advance should be skipped.

    Player-owned land defence configs can be in fallback mode (no valid
    strategy selected), in which case the invader should immediately select
    the defender instead of giving the defender a counter-advance turn.
    """
    if not game or game.mode != 'conquer':
        return False
    if not game.defence_config_id:
        # AI-template lands always keep scripted counter-advance behavior.
        return False

    cfg = db.session.get(LandConfig, game.defence_config_id)
    if not cfg:
        return True

    has_battle_fig = (cfg.battle_figure_id is not None)
    has_counter_spell = cfg.counter_spell_name is not None
    if cfg.counter_spell_name == 'Explosion':
        has_counter_spell = False
    if cfg.counter_spell_name == 'Health Boost':
        counter_target = db.session.get(LandConfigFigure, cfg.counter_spell_target_figure_id)
        has_counter_spell = bool(counter_target and counter_target.config_id == cfg.id
                                 and not getattr(counter_target, 'checkmate', False))

    # If a counter spell already fired this round (e.g., Civil War first
    # advance), fall back to counter-advance for any remaining advances.
    defender_player = next((p for p in game.players if p.id != game.advancing_player_id), None)
    if has_counter_spell and defender_player and _defender_already_cast_counter_this_round(game, defender_player.id):
        has_counter_spell = False

    if has_battle_fig and not has_counter_spell:
        battle_cfg_fig = db.session.get(Figure, game.defending_figure_id)
        if battle_cfg_fig:
            return False
        cfg_fig = db.session.get(LandConfigFigure, cfg.battle_figure_id)
        return not (cfg_fig and cfg_fig.config_id == cfg.id)

    if has_counter_spell and not has_battle_fig:
        return False

    # Both-selected and none-selected strategies fall back to invader pick.
    return True


def _map_defence_config_figure_to_game(cfg, cfg_figure_id, game, defender_player_id):
    """Map a LandConfigFigure ID to the runtime Figure created for this conquer game.

    Uses the persistent ``Figure.source_config_figure_id`` link rather than
    insertion-order zip so the mapping is stable even when figures are
    destroyed (Explosion) before the lookup runs.
    """
    if not cfg or not cfg_figure_id:
        return None
    return Figure.query.filter_by(
        game_id=game.id,
        player_id=defender_player_id,
        source_config_figure_id=cfg_figure_id,
    ).first()


def _get_conquer_counter_spell_config(game, defender_player):
    """Return the configured defender counter spell for a conquer game."""
    if not game.defence_config_id:
        return None, None, None
    cfg = db.session.get(LandConfig, game.defence_config_id)
    if not cfg or not cfg.counter_spell_name:
        return None, None, None
    return cfg, cfg.counter_spell_name, cfg.counter_spell_data


def _resolve_conquer_counter_target(game, defender_player, cfg, spell_name):
    """Resolve the runtime target for a configured conquer counter spell."""
    if spell_name == 'Poison':
        target = db.session.get(Figure, game.advancing_figure_id)
        if target and not getattr(target, 'checkmate', False):
            return target.id
        return None
    if spell_name == 'Health Boost':
        target = _map_defence_config_figure_to_game(
            cfg,
            cfg.counter_spell_target_figure_id,
            game,
            defender_player.id,
        )
        if target and not getattr(target, 'checkmate', False):
            return target.id
        return None
    return None


def _consume_conquer_defender_response(game, defender_player):
    """Consume the automated defender response and return turn to the invader."""
    if (defender_player.turns_left or 0) > 0:
        defender_player.turns_left = defender_player.turns_left - 1
    if game.advancing_player_id:
        game.turn_player_id = game.advancing_player_id

@games.after_request
def _ai_trigger_hook(response):
    """After every POST, check if an AI player needs to act."""
    if request.method == 'POST' and settings.AI_ENABLED:
        if request.headers.get('X-NepalKings-AI-Internal') == '1':
            return response
        game_id = None
        try:
            if request.is_json and request.json:
                game_id = request.json.get('game_id')
            elif request.form:
                game_id = request.form.get('game_id')
        except Exception:
            pass
        if game_id:
            try:
                from ai.ai_worker import trigger_ai_if_needed
                trigger_ai_if_needed(int(game_id), app=current_app._get_current_object())
            except Exception as e:
                _ai_logger.warning(f"AI trigger error in games hook: {e}")
    return response

def _guard_battle_active(game, *, player_id=None, action_label='action'):
    """Return an error response if a battle is in progress, else None.

    A battle is "in progress" when:
    - battle_confirmed is True (players are in battle-move / battle phase), OR
    - battle_decisions has any entries (at least one player chose fight, waiting for
      the other to decide fight/fold).

    This prevents mutating game actions (change cards, build figure, advance,
    cast spell, pickup/upgrade figure) while a battle is being resolved.
    """
    if game.battle_confirmed or game.battle_decisions:
        logger.info(
            f"[BATTLE_LOCK] blocked action={action_label} route={request.path} "
            f"game={getattr(game, 'id', None)} player={player_id} reason=active_battle"
        )
        return jsonify({
            'success': False,
            'message': 'Action not allowed during an active battle',
            'reason': 'active_battle'
        }), 400

    # Optional hard lock: once both battle figures are selected and the game is
    # waiting for fight/fold, only battle-resolution actions should proceed.
    if (
        settings.BATTLE_RESOLUTION_HARD_LOCK_ENABLED
        and game.advancing_figure_id
        and game.defending_figure_id
        and not game.battle_confirmed
    ):
        logger.info(
            f"[BATTLE_LOCK] blocked action={action_label} route={request.path} "
            f"game={getattr(game, 'id', None)} player={player_id} reason=battle_resolution_locked"
        )
        return jsonify({
            'success': False,
            'message': 'Action not allowed while battle resolution is pending. Choose fight/fold first.',
            'reason': 'battle_resolution_locked'
        }), 400

    # Counterable spell lock: while waiting for allow/counter, no other
    # state-mutating game actions should run.
    if game.pending_spell_id and game.waiting_for_counter_player_id:
        logger.info(
            f"[SPELL_LOCK] blocked action={action_label} route={request.path} "
            f"game={getattr(game, 'id', None)} player={player_id} "
            f"reason=pending_counter_spell pending_spell_id={game.pending_spell_id}"
        )
        return jsonify({
            'success': False,
            'message': 'Action not allowed while a counterable spell is pending. Resolve allow/counter first.',
            'reason': 'pending_counter_spell'
        }), 400

    return None


def _find_pending_conquer_prelude_spell(game, player_id):
    if not game or game.mode != 'conquer' or game.invader_player_id != player_id:
        return None

    candidates = ActiveSpell.query.filter_by(
        game_id=game.id,
        player_id=player_id,
        is_active=False,
    ).all()

    for spell in candidates:
        effect_data = spell.effect_data or {}
        if isinstance(effect_data, dict) and effect_data.get('prelude_pending_target'):
            if spell.spell_name in _TARGETED_PRELUDE_SPELLS:
                valid_targets = _list_valid_conquer_prelude_targets(
                    game, player_id, spell.spell_name
                )
                if not valid_targets:
                    effect_data = dict(effect_data)
                    effect_data['prelude_status'] = 'no_valid_target'
                    effect_data.pop('prelude_pending_target', None)
                    effect_data.pop('valid_target_ids', None)
                    spell.effect_data = effect_data
                    spell.is_active = False
                    spell.is_pending = False
                    db.session.commit()
                    continue
            return spell
    return None


def _guard_pending_conquer_prelude_target(game, *, player_id=None, action_label='action'):
    """Block invader actions until pending conquer prelude target is resolved."""
    if not game or player_id is None:
        return None

    pending_spell = _find_pending_conquer_prelude_spell(game, player_id)
    if not pending_spell:
        return None

    logger.info(
        f"[PRELUDE_LOCK] blocked action={action_label} route={request.path} "
        f"game={getattr(game, 'id', None)} player={player_id} "
        f"spell_id={pending_spell.id} spell_name={pending_spell.spell_name}"
    )
    return jsonify({
        'success': False,
        'message': f"Resolve your prelude spell target for {pending_spell.spell_name} first.",
        'reason': 'pending_prelude_target',
        'pending_spell_id': pending_spell.id,
        'pending_spell_name': pending_spell.spell_name,
    }), 400


def _get_conquer_prelude_target_scope(spell_name):
    if spell_name in ('Poison', 'Explosion'):
        return 'opponent'
    if spell_name == 'Health Boost':
        return 'own'
    return None


def _list_valid_conquer_prelude_targets(game, caster_player_id, spell_name):
    scope = _get_conquer_prelude_target_scope(spell_name)
    if not scope:
        return []

    if scope == 'opponent':
        candidate_player_ids = [p.id for p in game.players if p.id != caster_player_id]
    else:
        candidate_player_ids = [caster_player_id]

    if not candidate_player_ids:
        return []

    targets = Figure.query.filter(
        Figure.game_id == game.id,
        Figure.player_id.in_(candidate_player_ids),
    ).all()
    return [f for f in targets if not getattr(f, 'checkmate', False)]


def _guard_must_advance(game, player_id, *, action_label='action'):
    """Block non-advance actions when the invader is on their last turn.

    The invader MUST advance (or trigger cannot_advance_loss) on their
    final turn.  Returns an error response if blocked, else ``None``.
    """
    if not game:
        return None

    # Only applies to the invader
    if game.invader_player_id != player_id:
        return None

    player = db.session.get(Player, player_id)
    if not player or player.turns_left > 1:
        return None

    # Check whether the invader has at least one figure that CAN advance.
    # If none can advance, they must use cannot_advance_loss.
    modifiers = game.battle_modifier if isinstance(game.battle_modifier, list) else []
    has_peasant_war = any(m.get('type') == 'Peasant War' for m in modifiers)
    has_civil_war = any(m.get('type') == 'Civil War' for m in modifiers)

    figures = Figure.query.filter_by(player_id=player_id, game_id=game.id).all()
    resting_ids = set(game.resting_figure_ids or [])
    has_advanceable = False
    for fig in figures:
        if fig.id in resting_ids:
            continue
        if (has_peasant_war or has_civil_war) and fig.field != 'village':
            continue
        if _check_figure_resource_deficit(fig, player_id, game.id):
            continue
        has_advanceable = True
        break

    if not has_advanceable:
        logger.info(
            f"[MUST_ADVANCE] blocked action={action_label} route={request.path} "
            f"game={game.id} player={player_id} reason=no_figures_to_advance "
            f"turns_left={player.turns_left}"
        )
        return jsonify({
            'success': False,
            'message': 'No figures can advance. Use cannot_advance_loss to resolve the turn.',
            'reason': 'must_advance_no_figures'
        }), 400

    logger.info(
        f"[MUST_ADVANCE] blocked action={action_label} route={request.path} "
        f"game={game.id} player={player_id} reason=invader_must_advance "
        f"turns_left={player.turns_left}"
    )
    return jsonify({
        'success': False,
        'message': 'You must advance a figure on your last turn as the invader.',
        'reason': 'must_advance'
    }), 400


def _check_and_update_ceasefire(game):
    """
    Check if ceasefire should end and update game state accordingly.
    Normal ceasefire: ends when invader has <= 1 turn left OR after 3 invader turns.
    Blitzkrieg ceasefire: ends when the *defender* has <= 1 turn left, so the
    invader gets to advance first while the defender still has turns remaining.
    Returns True if ceasefire ended this check.
    """
    if not game.ceasefire_active:
        return False
    
    invader = db.session.get(Player, game.invader_player_id)
    if not invader:
        return False

    # Determine if Blitzkrieg ceasefire is in effect
    modifiers = game.battle_modifier if isinstance(game.battle_modifier, list) else []
    has_blitzkrieg = any(m.get('type') == 'Blitzkrieg' for m in modifiers)

    if has_blitzkrieg:
        # Blitzkrieg ceasefire ends when the DEFENDER is on their last turn,
        # giving the invader the chance to advance first.
        # No invader safety net here — since turns alternate and invader goes
        # first, defender reaches turns_left=1 one step BEFORE the invader's
        # last turn, so ceasefire will always end in time.
        defender = next(
            (p for p in game.players if p.id != game.invader_player_id), None
        )
        if defender and defender.turns_left <= 1:
            logger.info(f"[CEASEFIRE] Blitzkrieg ceasefire ending (defender has {defender.turns_left} turn(s) left)")
            game.ceasefire_active = False
            game.ceasefire_start_turn = None
            db.session.commit()
            return True
        return False

    # ── Normal ceasefire ──

    # Universal end: invader is on their last turn and needs to advance
    if invader.turns_left <= 1:
        logger.info(f"[CEASEFIRE] Ceasefire ending (invader has {invader.turns_left} turn(s) left — must advance)")
        game.ceasefire_active = False
        game.ceasefire_start_turn = None
        db.session.commit()
        return True
    
    # Normal ceasefire: lasts for 3 invader turns
    # ceasefire_start_turn stores the invader's "turn index" when ceasefire began
    # (i.e. INITIAL_TURNS_INVADER - invader.turns_left at ceasefire start)
    
    # Calculate how many invader turns have passed since ceasefire started
    current_turn = settings.INITIAL_TURNS_INVADER - invader.turns_left
    ceasefire_start = game.ceasefire_start_turn if game.ceasefire_start_turn is not None else 0
    invader_turns_during_ceasefire = current_turn - ceasefire_start
    
    # Ceasefire ends after 3 invader turns
    if invader_turns_during_ceasefire >= 3:
        logger.info(f"[CEASEFIRE] Ceasefire ending (3 invader turns passed, turn_idx={current_turn}, start={ceasefire_start})")
        game.ceasefire_active = False
        game.ceasefire_start_turn = None
        db.session.commit()
        return True
    
    return False

def _is_ceasefire_active(game_id):
    """Check if ceasefire is currently active for a game."""
    game = db.session.get(Game, game_id)
    if not game:
        return False
    return game.ceasefire_active


def _check_game_over(game):
    """Check if any player has reached the game's point stake.

    If a winner is found:
    - Sets game.state = 'finished', game.winner_player_id, game.finished_at
    - Awards gold to the winner (2 × stake)
    - Creates a GameResult record for statistics
    Returns a dict with game_over info if the game ended, or None.
    """
    if game.state == 'finished':
        return None  # Already finished

    stake = game.stake or settings.DEFAULT_GAME_STAKE

    winner_player = None
    loser_player = None
    for p in game.players:
        if p.points >= stake:
            winner_player = p
            break

    if not winner_player:
        return None  # No winner yet

    return _finalize_game_over(game, winner_player, reason='stake')


def _check_checkmate_loss(game, destroyed_figure):
    """Check if a destroyed figure had checkmate — if so, its owner loses immediately.

    Returns a game_over dict if checkmate triggers, or None.
    Must be called BEFORE the figure is deleted from the session.
    """
    if game.state == 'finished':
        return None
    if not getattr(destroyed_figure, 'checkmate', False):
        return None

    # The owner of the checkmate figure loses
    loser_player = db.session.get(Player, destroyed_figure.player_id)
    winner_player = [p for p in game.players if p.id != loser_player.id][0]

    return _finalize_game_over(game, winner_player, reason='checkmate',
                               checkmate_figure_name=destroyed_figure.name)


def _compute_game_stats(game_id, player_ids):
    """Compute per-player game stats by counting LogEntry records.

    Returns a dict keyed by player_id with counts for each stat.
    """
    stats = {}
    for pid in player_ids:
        figures_built = LogEntry.query.filter_by(
            game_id=game_id, player_id=pid, type='figure_built'
        ).count()
        spells_cast = LogEntry.query.filter(
            LogEntry.game_id == game_id,
            LogEntry.player_id == pid,
            LogEntry.type.in_(['spell_cast', 'spell_cast_pending']),
        ).count()
        cards_changed = LogEntry.query.filter_by(
            game_id=game_id, player_id=pid, type='card_changed'
        ).count()
        battles_won = LogEntry.query.filter_by(
            game_id=game_id, player_id=pid, type='battle_win'
        ).count()
        stats[pid] = {
            'figures_built': figures_built,
            'spells_cast': spells_cast,
            'cards_changed': cards_changed,
            'battles_won': battles_won,
        }
    return stats


def _award_booster_packs(user, total_packs):
    """Award *total_packs* booster packs to *user*.

    Each pack is randomly assigned as main or side based on
    DUEL_BOOSTER_REWARD_PROBABILITIES.

    Returns dict ``{'main': N, 'side': M}`` with the breakdown.
    """
    if not user or total_packs <= 0:
        return {'main': 0, 'side': 0}

    probs = settings.DUEL_BOOSTER_REWARD_PROBABILITIES
    types = list(probs.keys())
    weights = [probs[t] for t in types]

    awarded = {'main': 0, 'side': 0}
    for _ in range(total_packs):
        chosen = random.choices(types, weights=weights, k=1)[0]
        awarded[chosen] += 1

    user.booster_packs += awarded['main']
    user.booster_packs_side += awarded['side']
    return awarded


def _finalize_game_over(game, winner_player, reason='stake', checkmate_figure_name=None):
    """Finalize a game-over: mark finished, award gold, create GameResult.

    reason: 'stake' (point limit reached) or 'checkmate' (checkmate figure destroyed)
    Returns a dict with game_over info.
    """
    stake = game.stake or settings.DEFAULT_GAME_STAKE

    # Determine the loser
    loser_player = [p for p in game.players if p.id != winner_player.id][0]

    # Mark game as finished
    game.state = 'finished'
    game.winner_player_id = winner_player.id
    game.finished_at = _utcnow()

    # Award gold: winner gets 2× stake, loser gets nothing (already bet their stake)
    gold_awarded = stake * 2
    winner_user = db.session.get(User, winner_player.user_id)
    loser_user = db.session.get(User, loser_player.user_id)

    if winner_user:
        winner_user.gold += gold_awarded
    if loser_user:
        # Loser already "bet" their stake when the game started — no further deduction
        pass

    # ── Booster pack rewards ────────────────────────────────────────
    winner_boosters = _award_booster_packs(winner_user, settings.DUEL_WINNER_BOOSTER_PACKS)
    loser_boosters = _award_booster_packs(loser_user, settings.DUEL_LOSER_BOOSTER_PACKS)

    winner_username = winner_user.username if winner_user else f"Player {winner_player.id}"
    loser_username = loser_user.username if loser_user else f"Player {loser_player.id}"

    # Build log message
    if reason == 'checkmate':
        log_message = (
            f"💀 CHECKMATE! {loser_username}'s {checkmate_figure_name} was destroyed — "
            f"{winner_username} wins the game! "
            f"{winner_username} earns {gold_awarded} gold."
        )
    else:
        log_message = (
            f"🏆 {winner_username} wins the game with {winner_player.points} points! "
            f"{loser_username} scored {loser_player.points}. "
            f"{winner_username} earns {gold_awarded} gold."
        )

    # Create GameResult record for statistics
    result = GameResult(
        game_id=game.id,
        winner_user_id=winner_player.user_id,
        loser_user_id=loser_player.user_id,
        winner_username=winner_username,
        loser_username=loser_username,
        winner_score=winner_player.points,
        loser_score=loser_player.points,
        stake=stake,
        gold_awarded=gold_awarded,
        rounds_played=game.current_round,
    )
    db.session.add(result)

    # Log the game result
    log_entry = LogEntry(
        game_id=game.id,
        player_id=winner_player.id,
        round_number=game.current_round,
        turn_number=0,
        message=log_message,
        author="System",
        type='game_over'
    )
    db.session.add(log_entry)

    logger.info(f"[GAME_OVER] Game {game.id} finished ({reason})! Winner: {winner_username} ({winner_player.points}pts) "
          f"Loser: {loser_username} ({loser_player.points}pts) Gold: {gold_awarded}")

    # Gather per-player stats
    game_stats = _compute_game_stats(game.id, [winner_player.id, loser_player.id])

    return {
        'game_over': True,
        'reason': reason,
        'checkmate_figure_name': checkmate_figure_name,
        'winner_player_id': winner_player.id,
        'loser_player_id': loser_player.id,
        'winner_username': winner_username,
        'loser_username': loser_username,
        'winner_score': winner_player.points,
        'loser_score': loser_player.points,
        'gold_awarded': gold_awarded,
        'stake': stake,
        'rounds_played': game.current_round,
        'stats': game_stats,
        'winner_boosters': winner_boosters,
        'loser_boosters': loser_boosters,
    }


def _build_game_over_info_from_finished(game):
    """Reconstruct game_over info dict for a game already marked as finished.

    Used when checkmate ended the game during finish_battle, but the
    subsequent pick_card / draw endpoint still needs the game_over payload.
    """
    if game.state != 'finished' or game.winner_player_id is None:
        return None

    stake = game.stake or settings.DEFAULT_GAME_STAKE
    gold_awarded = stake * 2

    winner_player = db.session.get(Player, game.winner_player_id)
    loser_player = [p for p in game.players if p.id != winner_player.id][0]

    winner_user = db.session.get(User, winner_player.user_id)
    loser_user = db.session.get(User, loser_player.user_id)

    winner_username = winner_user.username if winner_user else f"Player {winner_player.id}"
    loser_username = loser_user.username if loser_user else f"Player {loser_player.id}"

    # Try to retrieve the checkmate figure name from last_battle_result
    checkmate_figure_name = None
    if game.last_battle_result and isinstance(game.last_battle_result, dict):
        checkmate_figure_name = game.last_battle_result.get('checkmate_figure_name')

    # Determine reason from checkmate_figure_name
    reason = 'checkmate' if checkmate_figure_name else 'stake'

    return {
        'game_over': True,
        'reason': reason,
        'checkmate_figure_name': checkmate_figure_name,
        'winner_player_id': winner_player.id,
        'loser_player_id': loser_player.id,
        'winner_username': winner_username,
        'loser_username': loser_username,
        'winner_score': winner_player.points,
        'loser_score': loser_player.points,
        'gold_awarded': gold_awarded,
        'stake': stake,
        'rounds_played': game.current_round,
        'stats': _compute_game_stats(game.id, [winner_player.id, loser_player.id]),
        'winner_boosters': None,  # not available for reconstructed info
        'loser_boosters': None,
    }


def _check_and_fill_minimum_cards(game, player):
    """
    Check if player has minimum required cards and auto-fill if needed.
    Returns fill_info dict with details about what was filled, or None if no fill needed.
    """
    # Conquer mode has no shared deck — skip auto-fill
    if game.mode == 'conquer':
        return None

    logger.debug(f"[AUTO-FILL] Starting check for player {player.id} in game {game.id}")
    
    # Count current cards (in hand = not in deck and not part of figure)
    main_cards_count = MainCard.query.filter_by(
        game_id=game.id,
        player_id=player.id,
        in_deck=False,
        part_of_figure=False
    ).count()
    
    side_cards_count = SideCard.query.filter_by(
        game_id=game.id,
        player_id=player.id,
        in_deck=False,
        part_of_figure=False
    ).count()
    
    # Check if auto-fill needed
    main_cards_needed = max(0, settings.NUM_MIN_MAIN_CARDS - main_cards_count)
    side_cards_needed = max(0, settings.NUM_MIN_SIDE_CARDS - side_cards_count)
    
    logger.debug(f"[AUTO-FILL] Player {player.id}: main={main_cards_count}/{settings.NUM_MIN_MAIN_CARDS}, side={side_cards_count}/{settings.NUM_MIN_SIDE_CARDS}")
    
    if main_cards_needed == 0 and side_cards_needed == 0:
        logger.debug(f"[AUTO-FILL] No fill needed")
        return None
    
    # Auto-fill needed
    logger.debug(f"[AUTO-FILL] Need to fill: main={main_cards_needed}, side={side_cards_needed}")
    fill_info = {
        'main_cards_filled': 0,
        'side_cards_filled': 0,
        'cards': []  # List of card data (suit, rank, type)
    }
    
    if main_cards_needed > 0:
        logger.debug(f"[AUTO-FILL] Drawing {main_cards_needed} main cards")
        drawn_main = DeckManager.draw_cards_from_deck(
            game,
            player,
            main_cards_needed,
            card_type="main"
        )
        fill_info['main_cards_filled'] = len(drawn_main)
        # Add card data for client to display
        for card in drawn_main:
            fill_info['cards'].append({
                'suit': card.suit.value,
                'rank': card.rank.value,
                'type': 'main'
            })
        logger.debug(f"[AUTO-FILL] Drew {len(drawn_main)} main cards")
    
    if side_cards_needed > 0:
        logger.debug(f"[AUTO-FILL] Drawing {side_cards_needed} side cards")
        drawn_side = DeckManager.draw_cards_from_deck(
            game,
            player,
            side_cards_needed,
            card_type="side"
        )
        fill_info['side_cards_filled'] = len(drawn_side)
        # Add card data for client to display
        for card in drawn_side:
            fill_info['cards'].append({
                'suit': card.suit.value,
                'rank': card.rank.value,
                'type': 'side'
            })
        logger.debug(f"[AUTO-FILL] Drew {len(drawn_side)} side cards")
    
    logger.debug(f"[AUTO-FILL] Returning fill_info: {fill_info}")
    return fill_info

def _get_opponent_turn_summary(game, current_player_id):
    """
    Analyze recent log entries to determine what the opponent did in their last turn.
    Returns a summary dict with action type and relevant details.
    """
    from models import LogEntry, ActiveSpell
    
    logger.debug(f"[OPPONENT_TURN] Getting summary for game {game.id}, current player {current_player_id}")
    
    # Get opponent player
    opponent = None
    for player in game.players:
        if player.id != current_player_id:
            opponent = player
            break
    
    if not opponent:
        return None
    
    # Get the most recent log entry from opponent (their last action)
    # Exclude auto-fill and discard actions
    # First, let's see all logs for debugging
    all_logs = LogEntry.query.filter(
        LogEntry.game_id == game.id,
        LogEntry.player_id == opponent.id,
        LogEntry.round_number == game.current_round
    ).order_by(LogEntry.id.desc()).limit(5).all()
    logger.debug(f"[OPPONENT_TURN] Last 5 logs from opponent: {[(log.type, log.message) for log in all_logs]}")

    # Check if this is game start - each player should see it once.  For
    # conquer mode, this must be returned before prelude side-effect logs
    # such as Explosion destruction so the intro notification stays first.
    # Use a strict whitelist of user-action log types so any system-only
    # side-effect log (figure_destroyed, etc.) does not suppress the intro.
    current_player_logs = LogEntry.query.filter(
        LogEntry.game_id == game.id,
        LogEntry.player_id == current_player_id,
        LogEntry.type.in_(_USER_ACTION_LOG_TYPES),
    ).first()
    
    # Check if current player had a figure destroyed (by opponent's Explosion spell)
    destroyed_figure_log = LogEntry.query.filter(
        LogEntry.game_id == game.id,
        LogEntry.player_id == current_player_id,
        LogEntry.round_number == game.current_round,
        LogEntry.type == 'figure_destroyed'
    ).order_by(LogEntry.id.desc()).first()
    
    # If a figure was destroyed, prioritize showing this
    if destroyed_figure_log and not (game.mode == 'conquer' and not current_player_logs):
        import re
        # Extract figure name from message: "FigureName was destroyed by Explosion spell (N cards returned to deck)"
        match = re.search(r'^(.+?) was destroyed by Explosion spell', destroyed_figure_log.message)
        figure_name = match.group(1) if match else "A figure"
        
        return {
            'opponent_name': opponent.serialize()['username'],
            'action': {
                'type': 'explosion',
                'destroyed_figure': figure_name,
                'message': f'Cast Explosion and destroyed your {figure_name}',
                'affects_player': True
            }
        }
    
    # Check if opponent ended Infinite Hammer mode this turn
    infinite_hammer_log = LogEntry.query.filter(
        LogEntry.game_id == game.id,
        LogEntry.player_id == opponent.id,
        LogEntry.round_number == game.current_round,
        LogEntry.type == 'spell_end',
        LogEntry.message.like('%Infinite Hammer%')
    ).order_by(LogEntry.id.desc()).first()
    
    if infinite_hammer_log:
        # Check if there are any more recent actions after the spell_end log
        more_recent_action = LogEntry.query.filter(
            LogEntry.game_id == game.id,
            LogEntry.player_id == opponent.id,
            LogEntry.round_number == game.current_round,
            LogEntry.id > infinite_hammer_log.id,
            LogEntry.type.in_(['figure_built', 'figure_upgraded', 'spell_cast', 'figure_pickup', 'card_changed'])
        ).first()
        
        # Only show Infinite Hammer notification if it's the most recent action
        if not more_recent_action:
            import re
            # Extract actions from message: "username ended Infinite Hammer mode after: action1, action2, action3."
            logger.debug(f"[INFINITE_HAMMER] Log message: {infinite_hammer_log.message}")
            match = re.search(r'ended Infinite Hammer mode after: (.+)\.', infinite_hammer_log.message)
            if match:
                actions_text = match.group(1)
                logger.debug(f"[INFINITE_HAMMER] Extracted actions: {actions_text}")
                return {
                    'opponent_name': opponent.serialize()['username'],
                    'action': {
                        'type': 'infinite_hammer',
                        'message': f'Cast Infinite Hammer and performed: {actions_text}',
                        'spell_icon': 'infinite_hammer.png'
                    }
                }
            else:
                # No actions performed during Infinite Hammer
                logger.debug(f"[INFINITE_HAMMER] No actions match found in message")
                return {
                    'opponent_name': opponent.serialize()['username'],
                    'action': {
                        'type': 'infinite_hammer',
                        'message': f'Cast Infinite Hammer (no figures modified)',
                        'spell_icon': 'infinite_hammer.png'
                    }
                }
    
    recent_log = LogEntry.query.filter(
        LogEntry.game_id == game.id,
        LogEntry.player_id == opponent.id,
        LogEntry.round_number == game.current_round,
        LogEntry.type.in_(['figure_built', 'figure_upgraded', 'spell_cast', 'counter_spell', 'figure_pickup', 'card_changed'])
    ).order_by(LogEntry.id.desc()).first()
    
    logger.debug(f"[OPPONENT_TURN] Most recent actionable log: {recent_log.type if recent_log else 'None'} - {recent_log.message if recent_log else 'None'}")
    
    logger.debug(f"[GAME_START_CHECK] Player {current_player_id} has logs: {current_player_logs is not None}, is_turn: {game.turn_player_id == current_player_id}")
    
    # Show welcome message if player has no logs at all — they haven't
    # interacted with this game yet, regardless of what the opponent did.
    should_show_welcome = not current_player_logs

    if should_show_welcome:
        logger.debug(f"[GAME_START_CHECK] Showing welcome for player {current_player_id}")

        is_turn = game.turn_player_id == current_player_id
        is_invader = game.invader_player_id == current_player_id

        # ── Conquer mode: no Maharaja — include active prelude spells ──
        if game.mode == 'conquer':
            # Gather prelude spells for both players. Newer records include
            # effect_data.prelude_origin; keep a fallback for older games.
            all_spells = ActiveSpell.query.filter_by(game_id=game.id).all()
            prelude_spells = [
                sp for sp in all_spells
                if isinstance(sp.effect_data, dict) and sp.effect_data.get('prelude_origin')
            ]
            if not prelude_spells:
                prelude_spells = [
                    sp for sp in all_spells
                    if sp.cast_round == 1 and sp.spell_name in _CONQUER_PRELUDE_SPELLS
                ]

            visible_prelude_spells = [
                sp for sp in prelude_spells
                if sp.is_active or (
                    isinstance(sp.effect_data, dict)
                    and sp.effect_data.get('prelude_status') == 'executed'
                )
            ]

            own_spells = []
            opponent_spells = []
            for sp in visible_prelude_spells:
                effect_data = sp.effect_data if isinstance(sp.effect_data, dict) else {}
                target_name = effect_data.get('target_figure_name') or effect_data.get('destroyed_figure_name')
                if not target_name and sp.target_figure_id:
                    target = db.session.get(Figure, sp.target_figure_id)
                    target_name = target.name if target else None
                spell_info = {
                    'spell_name': sp.spell_name,
                    'spell_type': sp.spell_type,
                    'effect_data': sp.effect_data,
                    'target_figure_id': sp.target_figure_id,
                    'target_figure_name': target_name,
                }
                if sp.player_id == current_player_id:
                    own_spells.append(spell_info)
                else:
                    opponent_spells.append(spell_info)

            # Include drawn cards for the current player's greed spells
            # Only include cards that were actually drawn by the spell
            # (stored in effect_data.drawn_card_ids during prelude execution).
            drawn_card_ids = set()
            for sp in prelude_spells:
                if sp.player_id == current_player_id and sp.effect_data:
                    ids = sp.effect_data.get('drawn_card_ids', [])
                    drawn_card_ids.update(ids)

            own_drawn_cards = []
            if drawn_card_ids:
                own_main_cards = MainCard.query.filter(
                    MainCard.id.in_(drawn_card_ids)
                ).all()
                for mc in own_main_cards:
                    own_drawn_cards.append({
                        'id': mc.id, 'rank': mc.rank.value,
                        'suit': mc.suit.value, 'value': mc.value,
                        'type': 'main',
                    })

            own_no_target_spells = []
            opponent_no_target_spells = []
            pending_prelude_target = None

            for sp in prelude_spells:
                effect_data = sp.effect_data if isinstance(sp.effect_data, dict) else {}
                status = effect_data.get('prelude_status')

                if status == 'no_valid_target':
                    payload = {'spell_name': sp.spell_name}
                    if sp.player_id == current_player_id:
                        own_no_target_spells.append(payload)
                    else:
                        opponent_no_target_spells.append(payload)

                if (
                    sp.player_id == current_player_id
                    and sp.spell_name in _TARGETED_PRELUDE_SPELLS
                    and effect_data.get('prelude_pending_target')
                ):
                    valid_targets = _list_valid_conquer_prelude_targets(
                        game, current_player_id, sp.spell_name
                    )
                    if not valid_targets:
                        own_no_target_spells.append({'spell_name': sp.spell_name})
                        continue
                    pending_prelude_target = {
                        'spell_id': sp.id,
                        'spell_name': sp.spell_name,
                        'spell_type': sp.spell_type,
                        'target_scope': _get_conquer_prelude_target_scope(sp.spell_name),
                        'valid_target_ids': [f.id for f in valid_targets],
                    }
                    break

            result = {
                'action': 'game_start',
                'opponent_name': opponent.serialize()['username'],
                'is_turn': is_turn,
                'is_invader': is_invader,
                'mode': 'conquer',
                'own_prelude_spells': own_spells,
                'opponent_prelude_spells': opponent_spells,
                'own_drawn_cards': own_drawn_cards,
                'pending_prelude_target': pending_prelude_target,
                'own_prelude_no_target_spells': own_no_target_spells,
                'opponent_prelude_no_target_spells': opponent_no_target_spells,
                'battle_modifier': game.battle_modifier,
            }
            logger.debug(f"[GAME_START_CHECK] Returning conquer game_start for player {current_player_id}")
            return result

        # ── Duel mode: show Maharaja ──
        # Get the player's Maharaja figure
        maharaja = Figure.query.filter_by(
            player_id=current_player_id,
            game_id=game.id,
            field='castle'
        ).filter(
            Figure.name.in_(['Himalaya Maharaja', 'Djungle Maharaja'])
        ).first()
        
        if maharaja:
            is_turn = game.turn_player_id == current_player_id
            is_invader = game.invader_player_id == current_player_id
            
            logger.debug(f"[GAME_START_CHECK] Returning game_start action for player {current_player_id} (is_turn={is_turn}, is_invader={is_invader})")
            
            result = {
                'action': 'game_start',
                'opponent_name': opponent.serialize()['username'],
                'maharaja': maharaja.serialize(),  # Full figure data for FieldFigureIcon
                'is_turn': is_turn,
                'is_invader': is_invader
            }

            # For the defender on their first turn, the invader has already
            # played.  Attach that turn summary so the client can show both
            # the welcome *and* what the opponent did.
            if is_turn and not is_invader and recent_log:
                result['has_opponent_action'] = True
            
            return result
        else:
            logger.debug(f"[GAME_START_CHECK] No Maharaja found for player {current_player_id}")
    else:
        logger.debug(f"[GAME_START_CHECK] Player {current_player_id} has existing logs, skipping game_start")
    
    if not recent_log:
        return {
            'action': 'unknown',
            'opponent_name': opponent.serialize()['username'],
            'message': f"{opponent.serialize()['username']} completed their turn."
        }
    
    summary = {
        'opponent_name': opponent.serialize()['username'],
        'action': None,
        'log_id': recent_log.id,  # for client-side deduplication
    }
    
    # Analyze the most recent log to determine the action
    log_type = recent_log.type
    log_message = recent_log.message
    
    if log_type == 'figure_built':
        # Extract figure details from message: "username built a figure with N cards in field."
        import re
        match = re.search(r'built a figure with (\d+) cards? in (.+)\.', log_message)
        if match:
            card_count = match.group(1)
            field = match.group(2)
            summary['action'] = {
                'type': 'build',
                'message': f'Built a figure with {card_count} card{"s" if int(card_count) > 1 else ""} in {field}',
                'icon': 'hammer_active.png'
            }
        else:
            summary['action'] = {
                'type': 'build',
                'message': 'Built a figure',
                'icon': 'hammer_active.png'
            }
    
    elif log_type == 'figure_upgraded':
        # Extract upgrade details from message: "username upgraded a field OldName to NewName."
        import re
        match = re.search(r'upgraded a ([A-Za-z]+) ([A-Za-z\s]+) to ([A-Za-z\s]+)\.', log_message)
        if match:
            field = match.group(1)
            old_name = match.group(2).strip()
            new_name = match.group(3).strip()
            summary['action'] = {
                'type': 'upgrade',
                'message': f'Upgraded {field} {old_name} to {new_name}',
                'icon': 'hammer_active.png'
            }
        else:
            summary['action'] = {
                'type': 'upgrade',
                'message': 'Upgraded a figure',
                'icon': 'hammer_active.png'
            }
    
    elif log_type == 'figure_pickup':
        # Extract pickup details from message: "username picked up a figure with N cards from the field."
        import re
        match = re.search(r'picked up a figure with (\d+) cards? from the ([A-Za-z]+)', log_message)
        if match:
            card_count = match.group(1)
            field = match.group(2)
            summary['action'] = {
                'type': 'pickup',
                'message': f'Picked up a figure with {card_count} card{"s" if int(card_count) > 1 else ""} from {field}',
                'icon': 'hammer_active.png'
            }
        else:
            summary['action'] = {
                'type': 'pickup',
                'message': 'Picked up a figure',
                'icon': 'hammer_active.png'
            }
    
    elif log_type == 'card_changed':
        # Extract card change details from message: "username changed N type cards."
        import re
        match = re.search(r'changed (\d+) ([a-z]+) cards?', log_message)
        if match:
            card_count = match.group(1)
            card_type = match.group(2)
            summary['action'] = {
                'type': 'card_change',
                'message': f'Changed {card_count} {card_type} card{"s" if int(card_count) > 1 else ""}',
                'icon': 'round_arrow_active.png'
            }
        else:
            summary['action'] = {
                'type': 'card_change',
                'message': 'Changed cards',
                'icon': 'round_arrow_active.png'
            }
    
    elif log_type in ('spell_cast', 'counter_spell'):
        spell_name = None
        spell_icon = None
        # Try to extract spell name and get corresponding icon
        spell_icon_map = {
            'Forced Deal': 'forced_deal.png',
            'Dump Cards': 'dump_cards.png',
            'All Seeing Eye': 'eye.png',
            'Poison': 'poisson_portion.png',
            'Health Boost': 'health_portion.png',
            'Explosion': 'bomb.png',
            'Draw 2 SideCards': 'draw_two_side.png',
            'Draw 2 MainCards': 'draw_two_main.png',
            'Fill up to 10': 'fill10.png'
        }
        
        for spell_type in spell_icon_map.keys():
            if spell_type in log_message:
                spell_name = spell_type
                spell_icon = spell_icon_map[spell_type]
                break
        
        # Skip if no spell name found
        if not spell_name:
            return {
                'action': 'unknown',
                'opponent_name': opponent.serialize()['username'],
                'message': f"{opponent.serialize()['username']} completed their turn."
            }
        
        action_data = {
            'type': 'counter_spell' if log_type == 'counter_spell' else 'spell',
            'spell_name': spell_name,
            'spell_icon': spell_icon,
            'message': f'Cast {spell_name} as a counter spell' if log_type == 'counter_spell' else f'Cast {spell_name}'
        }
        
        logger.debug(f"[OPPONENT_TURN] Detected spell: {spell_name}")
        
        # Check if spell affects current player
        if spell_name == 'Forced Deal':
            action_data['affects_player'] = True
            # Get card swap details from ActiveSpell
            from models import ActiveSpell
            forced_deal_spell = ActiveSpell.query.filter(
                ActiveSpell.game_id == game.id,
                ActiveSpell.spell_name.like('%Forced Deal%'),
                ActiveSpell.cast_round == game.current_round,
                ActiveSpell.player_id == opponent.id
            ).order_by(ActiveSpell.id.desc()).first()
            
            if forced_deal_spell and forced_deal_spell.effect_data:
                effect_data = forced_deal_spell.effect_data
                # Include card details in action if notification is pending
                if effect_data.get('notification_pending') and effect_data.get('opponent_id') == current_player_id:
                    action_data['cards_given'] = effect_data.get('opponent_gave', [])
                    action_data['cards_received'] = effect_data.get('opponent_received', [])
                    action_data['message'] = f'Cast Forced Deal - exchanged {len(action_data["cards_received"])} for {len(action_data["cards_given"])} cards'
                    
                    # Clear the notification flag
                    forced_deal_spell.effect_data['notification_pending'] = False
                    db.session.commit()
                else:
                    action_data['details'] = 'Cards were exchanged'
            else:
                action_data['details'] = 'Cards were exchanged'
        
        elif spell_name == 'Dump Cards':
            action_data['affects_player'] = True
            # Get current player's new hand after dump (only cards in hand, not in deck or figures)
            main_cards = MainCard.query.filter_by(
                player_id=current_player_id, 
                game_id=game.id,
                in_deck=False,
                part_of_figure=False
            ).all()
            side_cards = SideCard.query.filter_by(
                player_id=current_player_id, 
                game_id=game.id,
                in_deck=False,
                part_of_figure=False
            ).all()
            
            logger.debug(f"[DUMP_CARDS_SERVER] Found {len(main_cards)} main cards and {len(side_cards)} side cards for player {current_player_id}")
            
            # Serialize cards for display
            action_data['new_cards'] = []
            for card in main_cards + side_cards:
                card_data = card.serialize()
                card_data['type'] = 'main' if isinstance(card, MainCard) else 'side'
                action_data['new_cards'].append(card_data)
            action_data['message'] = (
                f'Cast Dump Cards — both players discarded their hands; '
                f'you redrew {len(action_data["new_cards"])} fresh card(s).'
            )
            logger.debug(f"[DUMP_CARDS_SERVER] Serialized {len(action_data['new_cards'])} cards for notification")
        
        elif spell_name == 'Poison':
            # Check if the poisoned figure belongs to the current player
            from models import ActiveSpell
            poison_spell = ActiveSpell.query.filter(
                ActiveSpell.game_id == game.id,
                ActiveSpell.spell_name.like('%Poison%'),
                ActiveSpell.player_id == opponent.id,
                ActiveSpell.target_figure_id.isnot(None)
            ).order_by(ActiveSpell.id.desc()).first()
            
            if poison_spell and poison_spell.target_figure_id:
                target_figure = db.session.get(Figure, poison_spell.target_figure_id)
                if target_figure and target_figure.player_id == current_player_id:
                    target_name = (poison_spell.effect_data or {}).get('target_figure_name', target_figure.name)
                    action_data['affects_player'] = True
                    action_data['target_figure_name'] = target_name
                    action_data['target_figure_id'] = poison_spell.target_figure_id
                    action_data['message'] = f'Cast Poison on your {target_name} (-6 power)'
                else:
                    action_data['message'] = f'Cast Poison on their own figure'
        
        elif spell_name == 'Explosion':
            action_data['affects_player'] = True
            action_data['details'] = 'A figure might have been destroyed'
        
        elif spell_name == 'All Seeing Eye':
            action_data['affects_player'] = True
            action_data['details'] = 'Your figures and cards are now visible to opponent'
        
        elif spell_name == 'Fill up to 10':
            action_data['affects_player'] = False
            action_data['details'] = 'Drew main cards to fill hand to 10'
        
        summary['action'] = action_data
    
    logger.debug(f"[OPPONENT_TURN] Summary: {summary}")
    return summary

@games.route('/get_games', methods=['GET'])
def get_games():
    try:
        username = request.args.get('username')
        user = User.query.filter_by(username=username).first()
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 400

        # Explicitly specify the onclause to avoid ambiguity
        games = Game.query.join(Player, Player.game_id == Game.id).filter(
            Player.user_id == user.id
        ).all()

        return jsonify({
            'games': [game.serialize() for game in games]
        })
    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to fetch games')
        return jsonify({'success': False, 'message': 'Failed to fetch games'}), 400


@games.route('/get_game', methods=['GET'])
def get_game():
    try:
        game_id = request.args.get('game_id')
        game = db.session.get(Game, game_id)

        if not game:
            return jsonify({'success': False, 'message': 'Game not found'}), 400

        # Check if Blitzkrieg ceasefire should end (runs on every poll)
        _check_and_update_ceasefire(game)

        return jsonify({
            'game': game.serialize()
        })
    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to fetch game')
        return jsonify({'success': False, 'message': 'Failed to fetch game'}), 400


@games.route('/get_ai_debug', methods=['GET'])
@require_token
def get_ai_debug():
    """Return ephemeral AI reasoning and planner telemetry for a game.

    Access is restricted to users participating in the game.
    """
    try:
        game_id = request.args.get('game_id', type=int)
        if not game_id:
            return jsonify({'success': False, 'message': 'Missing game_id'}), 400

        game = db.session.get(Game, game_id)
        if not game:
            return jsonify({'success': False, 'message': 'Game not found'}), 404

        participant_user_ids = [p.user_id for p in game.players]
        if g.user_id not in participant_user_ids:
            return jsonify({'success': False, 'message': 'Forbidden'}), 403

        max_notes = request.args.get('max_notes', default=20, type=int)
        max_events = request.args.get('max_events', default=40, type=int)

        ai_player_id = None
        ai_username = None
        for p in game.players:
            user = db.session.get(User, p.user_id)
            if user and user.is_ai:
                ai_player_id = p.id
                ai_username = user.username
                break

        from ai.ai_worker import get_ai_debug_snapshot

        snapshot = get_ai_debug_snapshot(game_id, max_notes=max_notes, max_events=max_events)

        return jsonify({
            'success': True,
            'game_id': game_id,
            'ai_player_id': ai_player_id,
            'ai_username': ai_username,
            'ai_debug': snapshot,
        })

    except Exception:
        db.session.rollback()
        logger.exception('Failed to fetch AI debug data')
        return jsonify({'success': False, 'message': 'Failed to fetch AI debug data'}), 400


@games.route('/start_turn', methods=['POST'])
@require_token
def start_turn():
    """
    Called when a player's turn begins. Checks and auto-fills minimum cards if needed.
    """
    try:
        data = request.get_json()
        game_id = data.get('game_id')
        player_id = data.get('player_id')
        
        logger.debug(f"[START_TURN] Called for game {game_id} (type={type(game_id)}), player {player_id} (type={type(player_id)})")

        if not game_id or not player_id:
            return jsonify({'success': False, 'message': 'Missing game_id or player_id'}), 400

        err = verify_player_ownership(player_id)
        if err:
            return err

        game = db.session.get(Game, game_id)
        if not game:
            return jsonify({'success': False, 'message': 'Game not found'}), 400

        player = Player.query.filter_by(game_id=game_id, id=player_id).first()
        if not player:
            return jsonify({'success': False, 'message': 'Player not found'}), 400

        # First check for game_start (works regardless of turn)
        # This allows both players to get welcome message on first load
        opponent_turn_summary = _get_opponent_turn_summary(game, player_id)
        
        # If this is game_start, return it immediately (regardless of whose turn it is)
        if opponent_turn_summary and opponent_turn_summary.get('action') == 'game_start':
            logger.debug(f"[START_TURN] Returning game_start notification for player {player_id}")
            # Write a LogEntry so subsequent polls don't repeat the welcome
            log_entry = LogEntry(
                game_id=game.id,
                player_id=player_id,
                round_number=game.current_round,
                turn_number=player.turns_left,
                message="Game started.",
                author="System",
                type='game_start'
            )
            db.session.add(log_entry)
            db.session.commit()
            return jsonify({
                'success': True,
                'auto_fill': None,
                'opponent_turn_summary': opponent_turn_summary,
                'forced_deal_notification': None
            })

        # Check if it's actually this player's turn (for normal turn processing)
        logger.debug(f"[START_TURN] Checking turn: game.turn_player_id={game.turn_player_id} (type={type(game.turn_player_id)}), player_id={player_id} (type={type(player_id)})")
        if game.turn_player_id != player_id:
            logger.debug(f"[START_TURN] Turn mismatch: game.turn_player_id={game.turn_player_id}, player_id={player_id}")
            # Still return opponent_turn_summary so notifications aren't lost
            # when the AI plays faster than the client can call start_turn.
            opponent_turn_summary = _get_opponent_turn_summary(game, player_id)
            return jsonify({
                'success': True,
                'auto_fill': None,
                'opponent_turn_summary': opponent_turn_summary,
            })

        logger.debug(f"[START_TURN] Turn check passed, calling _check_and_fill_minimum_cards")
        
        # Check if ceasefire should end
        ceasefire_ended = _check_and_update_ceasefire(game)
        
        # Check and fill minimum cards
        fill_info = _check_and_fill_minimum_cards(game, player)
        
        logger.debug(f"[START_TURN] Fill info: {fill_info}, Ceasefire ended: {ceasefire_ended}")
        
        # Get opponent's last turn summary (includes Forced Deal card details if applicable)
        opponent_turn_summary = _get_opponent_turn_summary(game, player_id)

        return jsonify({
            'success': True,
            'auto_fill': fill_info,  # None if no fill needed, otherwise dict with fill details
            'opponent_turn_summary': opponent_turn_summary,  # Summary of what opponent did (includes Forced Deal cards)
            'ceasefire_ended': ceasefire_ended  # True if ceasefire just ended
        })

    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to start turn')
        return jsonify({'success': False, 'message': 'Failed to start turn'}), 400


@games.route('/create_game', methods=['POST'])
@require_token
def create_game():
    try:
        challenge_id = request.form.get('challenge_id')
        challenge = db.session.get(Challenge, challenge_id)

        if not challenge:
            return jsonify({'success': False, 'message': 'Challenge not found'}), 400

        if g.user_id not in (challenge.challenger_id, challenge.challenged_id):
            return jsonify({'success': False, 'message': 'Forbidden'}), 403

        # Get the users from the challenge
        user1 = db.session.get(User, challenge.challenger_id)
        user2 = db.session.get(User, challenge.challenged_id)

        if not user1 or not user2:
            return jsonify({'success': False, 'message': 'One or both players do not exist'}), 400

        # Get game stake from the challenge (gold bet)
        game_stake = challenge.stake or settings.DEFAULT_GAME_STAKE

        # Deduct gold from both players (they bet the stake)
        if user1.gold < game_stake:
            return jsonify({'success': False, 'message': f'{user1.username} does not have enough gold ({user1.gold}/{game_stake})'}), 400
        if user2.gold < game_stake:
            return jsonify({'success': False, 'message': f'{user2.username} does not have enough gold ({user2.gold}/{game_stake})'}), 400

        user1.gold -= game_stake
        user2.gold -= game_stake

        # Create a new Game instance
        game = Game(
            current_round=1, 
            invader_player_id=None,
            ceasefire_active=True,
            ceasefire_start_turn=0,
            stake=game_stake,
            turn_time_limit=challenge.turn_time_limit
        )
        db.session.add(game)
        db.session.commit()

        # Create new Player instances for the users (start with defender turns)
        player1 = Player(user_id=user1.id, game_id=game.id, turns_left=settings.INITIAL_TURNS_DEFENDER, points=0)
        player2 = Player(user_id=user2.id, game_id=game.id, turns_left=settings.INITIAL_TURNS_DEFENDER, points=0)
        db.session.add(player1)
        db.session.add(player2)
        db.session.commit()

        # Set the first invader !!!!!!!!!!!!! temporary fix
        #game.invader_player_id = player1.id 
        #game.turn_player_id = player1.id
        #db.session.commit()

        # Create and shuffle deck, and deal cards using DeckManager
        DeckManager.create_and_shuffle_deck(game)

        db.session.commit()

        # put player in random order
        players = [player1, player2]
        random.shuffle(players)
        for player, color in zip(players, ['black', 'red']):
            maharaja_card = DeckManager.draw_maharaja(game, color, player)
            

            if color == 'red':##

                # Create the figure
                figure = Figure(
                    player_id=player.id,
                    game_id=game.id,
                    family_name='Djungle Maharaja',
                    field='castle',
                    color="offensive",
                    name="Djungle Maharaja",
                    suit=maharaja_card.suit.value,
                    description="Djungle maharaja",
                    upgrade_family_name=None,
                    produces={'villager_red': 3, 'warrior_red': 2},
                    requires={},
                    checkmate=True
                )
                db.session.add(figure)
                #db.session.flush() ##


                game.invader_player_id = player.id
                game.turn_player_id = player.id
                # Invader gets fewer turns than defender
                player.turns_left = settings.INITIAL_TURNS_INVADER

            else:
                logger.debug("Himalaya Maharaja")
                logger.debug(maharaja_card.suit)
                logger.debug(player.id)
                logger.debug(game.id)
                # Create the figure
                figure = Figure(
                    player_id=player.id,
                    game_id=game.id,
                    family_name='Himalaya Maharaja',
                    field='castle',
                    color="defensive",
                    name="Himalaya Maharaja",
                    suit=maharaja_card.suit.value,
                    description="Himalaya maharaja",
                    upgrade_family_name=None,
                    produces={'villager_black': 3, 'warrior_black': 2},
                    requires={},
                    checkmate=True
                )
                logger.debug(figure)
                db.session.add(figure)
                logger.debug("created figure")
            db.session.flush()

            # Add cards to the figure and update card attributes
            card_to_figure = CardToFigure(
                figure_id=figure.id,
                card_id=maharaja_card.id,
                card_type="main",
                role="key"
            )
            db.session.add(card_to_figure)

        db.session.commit()

        DeckManager.deal_cards_to_players(game, [player1, player2], 
                                          num_main_cards=settings.NUM_MAIN_CARDS_START, 
                                          num_side_cards=settings.NUM_SIDE_CARDS_START)

        # Mark the challenge as accepted and link to the created game
        db.session.expire(challenge)          # ensure fresh read before update
        challenge.status = ChallengeStatus.ACCEPTED
        challenge.game_id = game.id
        db.session.commit()

        logger.info(f"Challenge {challenge.id} accepted → game {game.id} "
                    f"(status={challenge.status}, game_id={challenge.game_id})")

        return jsonify({
            'success': True,
            'message': 'Game created successfully',
            'game': game.serialize()
        })

    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to create game')
        return jsonify({'success': False, 'message': 'Failed to create game'}), 400


@games.route('/delete_game', methods=['POST'])
@require_token
def delete_game():
    try:
        game_id = request.form.get('game_id', type=int)
        game = Game.query.options(
            joinedload(Game.players).joinedload(Player.main_hand)
        ).filter_by(id=game_id).first()

        if not game:
            return jsonify({'success': False, 'message': 'Game not found'}), 404

        player_ids = [p.user_id for p in game.players]
        if g.user_id not in player_ids:
            return jsonify({'success': False, 'message': 'Forbidden'}), 403

        # Delete all related records to avoid orphaned rows
        BattleMove.query.filter_by(game_id=game.id).delete()
        ActiveSpell.query.filter_by(game_id=game.id).delete()
        GameResult.query.filter_by(game_id=game.id).delete()
        LogEntry.query.filter_by(game_id=game.id).delete()
        ChatMessage.query.filter_by(game_id=game.id).delete()

        # Delete figures and their card-to-figure links
        figures = Figure.query.filter_by(game_id=game.id).all()
        for fig in figures:
            CardToFigure.query.filter_by(figure_id=fig.id).delete()
            db.session.delete(fig)

        # Delete all related cards (main and side)
        MainCard.query.filter_by(game_id=game.id).delete()
        SideCard.query.filter_by(game_id=game.id).delete()

        # Delete all related players
        for player in game.players:
            db.session.delete(player)

        # Finally, delete the game itself
        db.session.delete(game)

        # Commit the changes to the database
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to delete game')
        return jsonify({'success': False, 'message': 'Failed to delete game'}), 400

    return jsonify({'success': True, 'message': 'Game deleted successfully'})


@games.route('/get_hand', methods=['GET'])
def get_hand():
    try:
        player_id = request.args.get('player_id')

        main_cards = MainCard.query.filter_by(player_id=player_id).all()
        side_cards = SideCard.query.filter_by(player_id=player_id).all()

        return jsonify({
            'success': True,
            'message': 'Successfully loaded hand',
            'main_hand': [card.serialize() for card in main_cards],
            'side_hand': [card.serialize() for card in side_cards]
        })
    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to get hand')
        return jsonify({'success': False, 'message': 'Failed to get hand'}), 400


@games.route('/draw_cards', methods=['POST'])
@require_token
def draw_cards():
    try:
        game_id = request.form.get('game_id')
        player_id = request.form.get('player_id')
        card_type = request.form.get('card_type', 'main')  # 'main' or 'side'
        num_cards = int(request.form.get('num_cards', 1))  # Number of cards to draw

        game = db.session.get(Game, game_id)
        player = db.session.get(Player, player_id)

        if not game or not player:
            return jsonify({'success': False, 'message': 'Invalid game or player'}), 400

        err = verify_player_ownership(player_id)
        if err:
            return err

        battle_err = _guard_battle_active(game, player_id=player_id, action_label='draw_cards')
        if battle_err:
            return battle_err

        # Draw cards using DeckManager
        #from game_service.deck import DeckManager
        cards = DeckManager.draw_cards_from_deck(game, player, num_cards, card_type)
        return jsonify({
            'success': True,
            'message': 'Successfully drew cards',
            'cards': [card.serialize() for card in cards]
        })

    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to draw cards')
        return jsonify({'success': False, 'message': 'Failed to draw cards'}), 400


@games.route('/return_cards', methods=['POST'])
@require_token
def return_cards():
    try:
        card_ids = request.form.getlist('card_ids')  # List of card IDs to return
        card_type = request.form.get('card_type', 'main')  # 'main' or 'side'
        
        # Retrieve cards based on their type
        if card_type == "main":
            cards = MainCard.query.filter(MainCard.id.in_(card_ids)).all()
        else:
            cards = SideCard.query.filter(SideCard.id.in_(card_ids)).all()

        if not cards:
            return jsonify({'success': False, 'message': 'No cards found to return'}), 400

        player_id = cards[0].player_id
        err = verify_player_ownership(player_id)
        if err:
            return err

        game = db.session.get(Game, cards[0].game_id)
        if game:
            battle_err = _guard_battle_active(game, player_id=player_id, action_label='return_cards')
            if battle_err:
                return battle_err

        # Return the cards using DeckManager
        #from game_service.deck import DeckManager
        DeckManager.return_cards_to_deck(cards)
        return jsonify({
            'success': True,
            'message': 'Cards successfully returned to the deck'
        })
    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to return cards')
        return jsonify({'success': False, 'message': 'Failed to return cards'}), 400
    
@games.route('/change_cards', methods=['POST'])
@require_token
def change_cards():
    try:
        data = request.json
        game_id = data['game_id']
        player_id = data['player_id']
        card_ids = [card['id'] for card in data['cards']]
        card_type = data.get('card_type', 'main')  # Default to main cards

        err = verify_player_ownership(player_id)
        if err:
            return err

        game = db.session.get(Game, game_id)
        if game:
            battle_err = _guard_battle_active(game, player_id=player_id, action_label='change_cards')
            if battle_err:
                return battle_err

            prelude_err = _guard_pending_conquer_prelude_target(
                game, player_id=player_id, action_label='change_cards'
            )
            if prelude_err:
                return prelude_err

            must_adv = _guard_must_advance(game, player_id, action_label='change_cards')
            if must_adv:
                return must_adv

        logger.debug(f"Changing {card_type} cards for player {player_id} in game {game_id}")
        logger.debug(f"Selected card IDs: {card_ids}")
        
        # Handle MainCards or SideCards based on card_type
        if card_type == "main":
            selected_cards = MainCard.query.filter(MainCard.id.in_(card_ids)).all()
        elif card_type == "side":
            selected_cards = SideCard.query.filter(SideCard.id.in_(card_ids)).all()
        else:
            return jsonify({'success': False, 'message': 'Invalid card type specified'}), 400

        # Return the selected cards to the deck BEFORE drawing new ones,
        # so the hand-size check inside draw_cards_from_deck is accurate
        # and the returned cards become available for drawing again.
        DeckManager.return_cards_to_deck(selected_cards)

        # Now draw replacements
        new_cards = DeckManager.draw_cards_from_deck(
            db.session.get(Game, game_id), db.session.get(Player, player_id),
            len(card_ids), card_type)

        # Update turns left for the player
        player = db.session.get(Player, player_id)
        player.turns_left -= 1

        # flip turn player id
        game = db.session.get(Game, game_id)
        if game.turn_player_id == player_id:
            game.turn_player_id = game.players[0].id if game.players[0].id != player_id else game.players[1].id
        
        # Create log entry
        from models import User, LogEntry
        user = db.session.get(User, player.user_id)
        username = user.username if user else f"Player {player_id}"
        log_entry = LogEntry(
            game_id=game_id,
            player_id=player_id,
            round_number=game.current_round,
            turn_number=player.turns_left + 1,  # +1 because we decremented it above
            message=f"{username} changed {len(card_ids)} {card_type} card{'s' if len(card_ids) > 1 else ''}.",
            author=username,
            type='card_changed'
        )
        db.session.add(log_entry)
        db.session.commit()

        return jsonify({'success': True, 'new_cards': [card.serialize() for card in new_cards], 'turns_left': player.turns_left})

    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to change cards')
        return jsonify({'success': False, 'message': 'Failed to change cards'}), 400


@games.route('/discard_cards', methods=['POST'])
@require_token
def discard_cards():
    """Discard cards when player has too many (return to deck without drawing new ones)."""
    try:
        data = request.json
        game_id = data['game_id']
        player_id = data['player_id']
        card_ids = [card['id'] for card in data['cards']]
        card_type = data.get('card_type', 'main')  # Default to main cards
        card_ranks = [card['rank'] for card in data['cards']]

        err = verify_player_ownership(player_id)
        if err:
            return err

        game = db.session.get(Game, game_id)
        if game:
            battle_err = _guard_battle_active(game, player_id=player_id, action_label='discard_cards')
            if battle_err:
                return battle_err

        logger.debug(f"Discarding {card_type} cards for player {player_id} in game {game_id}")
        logger.debug(f"Selected card IDs: {card_ids}")
        
        # Side card ranks are 2-6, main card ranks are 7-A
        side_card_ranks = ['2', '3', '4', '5', '6']
        
        # Fetch cards based on rank (to avoid ID collision between tables)
        selected_cards = []
        for card_id, card_rank in zip(card_ids, card_ranks):
            if card_rank in side_card_ranks:
                card = db.session.get(SideCard, card_id)
            else:
                card = db.session.get(MainCard, card_id)
            
            if card:
                selected_cards.append(card)
        
        if len(selected_cards) != len(card_ids):
            return jsonify({'success': False, 'message': 'Some cards not found'}), 400

        # Return the selected cards to the deck (no drawing new ones)
        DeckManager.return_cards_to_deck(selected_cards)

        db.session.commit()

        return jsonify({'success': True})

    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to discard cards')
        return jsonify({'success': False, 'message': 'Failed to discard cards'}), 400


@games.route('/update_points', methods=['POST'])
@require_token
def update_points():
    try:
        data = request.json
        player_id = data['player_id']
        points = data['points']

        err = verify_player_ownership(player_id)
        if err:
            return err

        player = db.session.get(Player, player_id)
        if not player:
            return jsonify({'success': False, 'message': 'Player not found'}), 400

        player.points += points
        db.session.commit()

        return jsonify({'success': True, 'points': player.points})

    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to update points')
        return jsonify({'success': False, 'message': 'Failed to update points'}), 400


@games.route('/conquer_defender_counter_spell', methods=['POST'])
@require_token
def conquer_defender_counter_spell():
    """Execute the player-owned land defender's configured conquer counter spell.

    This endpoint is conquer-only and is used by deterministic defence
    automation during the defender response window.  It does not alter normal
    duel spell casting or counter-advance behavior.
    """
    try:
        data = request.json or {}
        game_id = data.get('game_id')
        player_id = data.get('player_id')

        if not game_id or not player_id:
            return jsonify({'success': False, 'message': 'Missing required fields'}), 400

        err = verify_player_ownership(player_id)
        if err:
            return err

        game = db.session.get(Game, game_id)
        if not game:
            return jsonify({'success': False, 'message': 'Game not found'}), 404
        if game.mode != 'conquer':
            return jsonify({'success': False, 'message': 'Counter spell response is conquer-only'}), 400
        if game.state == 'finished':
            return jsonify({'success': False, 'message': 'Game already finished'}), 400
        if game.last_battle_result is not None:
            return jsonify({'success': False, 'message': 'Battle already resolved'}), 400
        if game.battle_confirmed:
            return jsonify({'success': False, 'message': 'Battle already in progress'}), 400
        if game.pending_spell_id is not None:
            return jsonify({'success': False, 'message': 'Resolve pending spell first'}), 400
        if game.turn_player_id != player_id:
            return jsonify({'success': False, 'message': 'Not your turn'}), 400
        if not game.advancing_figure_id or game.advancing_player_id == player_id:
            return jsonify({'success': False, 'message': 'No opponent advance to counter'}), 400
        if game.defending_figure_id:
            return jsonify({'success': False, 'message': 'Defender already selected'}), 400
        if _defender_already_cast_counter_this_round(game, player_id):
            return jsonify({'success': False, 'message': 'Counter spell already cast this round'}), 400

        defender_player = db.session.get(Player, player_id)
        if not defender_player:
            return jsonify({'success': False, 'message': 'Player not found'}), 404

        cfg, spell_name, spell_data = _get_conquer_counter_spell_config(game, defender_player)
        if not cfg or not spell_name:
            return jsonify({'success': False, 'message': 'No counter spell configured'}), 400
        if spell_name == 'Explosion':
            return jsonify({'success': False, 'message': 'Explosion is not allowed as a counter spell'}), 400
        if spell_name not in {'Dump Cards', 'Forced Deal', 'Poison', 'Health Boost'}:
            return jsonify({'success': False, 'message': f'Unsupported counter spell: {spell_name}'}), 400

        target_figure_id = _resolve_conquer_counter_target(game, defender_player, cfg, spell_name)
        if spell_name in {'Poison', 'Health Boost'} and not target_figure_id:
            _consume_conquer_defender_response(game, defender_player)
            log_entry = LogEntry(
                game_id=game.id,
                player_id=player_id,
                round_number=game.current_round,
                turn_number=defender_player.turns_left,
                message=f"{spell_name} counter spell had no valid target.",
                author='System',
                type='counter_spell',
            )
            db.session.add(log_entry)
            db.session.commit()
            return jsonify({
                'success': True,
                'spell_name': spell_name,
                'status': 'no_valid_target',
                'game': game.serialize(),
            })

        effect_data = dict(spell_data or {}) if isinstance(spell_data, dict) else {}
        effect_data['counter_origin'] = True

        spell = ActiveSpell(
            game_id=game.id,
            player_id=defender_player.id,
            spell_name=spell_name,
            spell_type='greed' if spell_name in {'Dump Cards', 'Forced Deal'} else 'enchantment',
            spell_family_name=spell_name,
            suit='Hearts',
            target_figure_id=target_figure_id,
            cast_round=game.current_round,
            is_active=True,
            is_pending=False,
            effect_data=effect_data,
        )
        db.session.add(spell)
        db.session.flush()

        from routes.spells import _execute_spell
        result = _execute_spell(spell, game, defender_player)
        post_data = dict(spell.effect_data or {})
        post_data['counter_origin'] = True
        if result.get('error'):
            post_data['counter_status'] = 'failed'
            post_data['counter_error'] = result.get('effect') or result.get('error')
        else:
            post_data['counter_status'] = 'executed'
            if target_figure_id:
                post_data['target_figure_id'] = target_figure_id
            for key in ('drawn_cards', 'cards_given', 'cards_received', 'caster_dumped', 'opponent_dumped'):
                if key in result:
                    post_data[key] = result[key]
        spell.effect_data = post_data

        _consume_conquer_defender_response(game, defender_player)

        log_entry = LogEntry(
            game_id=game.id,
            player_id=player_id,
            round_number=game.current_round,
            turn_number=defender_player.turns_left,
            message=f"Defender cast {spell_name} as a counter spell.",
            author='System',
            type='counter_spell',
        )
        db.session.add(log_entry)
        db.session.commit()

        return jsonify({
            'success': True,
            'spell_name': spell_name,
            'status': post_data.get('counter_status'),
            'result': result,
            'game': game.serialize(),
        })

    except Exception:
        db.session.rollback()
        logger.exception('Failed to execute conquer defender counter spell')
        return jsonify({'success': False, 'message': 'Failed to execute counter spell'}), 400


@games.route('/advance_figure', methods=['POST'])
@require_token
def advance_figure():
    """
    Player advances a figure toward battle. This sets the advancing figure
    on the game and flips the turn to the opponent. Does NOT consume a turn.
    In Civil War, each player selects up to 2 village figures of the same color.
    """
    try:
        data = request.json
        game_id = data['game_id']
        player_id = data['player_id']
        figure_id = data['figure_id']

        err = verify_player_ownership(player_id)
        if err:
            return err

        game = db.session.get(Game, game_id)
        if not game:
            return jsonify({'success': False, 'message': 'Game not found'}), 404

        player = db.session.get(Player, player_id)
        if not player:
            return jsonify({'success': False, 'message': 'Player not found'}), 404

        # Validate it's this player's turn
        if game.turn_player_id != player_id:
            return jsonify({'success': False, 'message': 'Not your turn'}), 400

        # Block advance during an active battle
        battle_err = _guard_battle_active(game, player_id=player_id, action_label='advance_figure')
        if battle_err:
            return battle_err

        prelude_err = _guard_pending_conquer_prelude_target(
            game, player_id=player_id, action_label='advance_figure'
        )
        if prelude_err:
            return prelude_err

        # Clear stale fold state from a previous battle phase (fold_outcome
        # lingers for client polling; safe to clear on a new advance)
        if game.fold_outcome:
            game.fold_outcome = None
            game.fold_winner_id = None
            game.auto_loss_reason = None
            game.auto_loss_detail = None

        # Validate ceasefire is not active
        if game.ceasefire_active:
            return jsonify({'success': False, 'message': 'Cannot advance during ceasefire'}), 400

        # Validate figure belongs to this player
        figure = db.session.get(Figure, figure_id)
        if not figure or figure.player_id != player_id:
            return jsonify({'success': False, 'message': 'Figure not found or not yours'}), 400

        # Check resource deficit — figures with deficit cannot advance or counter-advance
        if _check_figure_resource_deficit(figure, player_id, game.id):
            return jsonify({'success': False, 'message': 'This figure has a resource deficit and cannot advance toward battle.', 'reason': 'resource_deficit'}), 400

        # Check battle modifiers
        modifiers = game.battle_modifier if isinstance(game.battle_modifier, list) else []
        has_civil_war = any(m.get('type') == 'Civil War' for m in modifiers)
        has_blitzkrieg = any(m.get('type') == 'Blitzkrieg' for m in modifiers)
        has_peasant_war = any(m.get('type') == 'Peasant War' for m in modifiers)

        # Peasant War: only village figures can advance
        if has_peasant_war and figure.field != 'village':
            return jsonify({'success': False, 'message': 'Peasant War: only village figures can advance'}), 400

        # Determine if this is a counter-advance (opponent already advanced)
        is_counter_advance = (game.advancing_figure_id is not None and 
                              game.advancing_player_id != player_id)

        # Cannot counter-advance if advancing figure has cannot_be_blocked
        if is_counter_advance and game.advancing_figure_id:
            advancing_fig = db.session.get(Figure, game.advancing_figure_id)
            if advancing_fig and advancing_fig.cannot_be_blocked:
                return jsonify({'success': False, 'message': 'Cannot counter-advance: opponent\'s figure cannot be blocked'}), 400

        # Blitzkrieg: defender cannot counter-advance
        if has_blitzkrieg and is_counter_advance:
            return jsonify({'success': False, 'message': 'Blitzkrieg: defender cannot counter-advance'}), 400

        civil_war_need_second = False
        civil_war_color = None
        is_second_pick = False

        if has_civil_war:
            # Civil War: each player selects up to 2 village figures of the same color
            if is_counter_advance:
                # Defending player's counter-advance picks
                if game.defending_figure_id and game.defending_figure_id_2:
                    return jsonify({'success': False, 'message': 'You already have 2 defending figures'}), 400
                
                if game.defending_figure_id and not game.defending_figure_id_2:
                    # Prevent selecting the same figure twice
                    if figure_id == game.defending_figure_id:
                        return jsonify({'success': False, 'message': 'This figure is already selected'}), 400
                    # Second counter-advance pick — validate same color
                    first_figure = db.session.get(Figure, game.defending_figure_id)
                    if first_figure and first_figure.color != figure.color:
                        return jsonify({'success': False, 'message': 'Second figure must be the same color as the first'}), 400
                    game.defending_figure_id_2 = figure_id
                    is_second_pick = True
                else:
                    # First counter-advance pick
                    game.defending_figure_id = figure_id
                    # Check if there's another eligible village figure of same color
                    # Exclude figures with resource deficit (they can't advance)
                    eligible_seconds = Figure.query.filter(
                        Figure.player_id == player_id,
                        Figure.id != figure_id,
                        Figure.field == 'village',
                        Figure.color == figure.color
                    ).all()
                    eligible_seconds = [
                        f for f in eligible_seconds
                        if not _check_figure_resource_deficit(f, player_id, game.id)
                    ]
                    if eligible_seconds:
                        civil_war_need_second = True
                        civil_war_color = figure.color
            else:
                # Advancing player's picks
                if game.advancing_figure_id and game.advancing_figure_id_2 and game.advancing_player_id == player_id:
                    return jsonify({'success': False, 'message': 'You already have 2 advancing figures'}), 400
                
                if game.advancing_figure_id and game.advancing_player_id == player_id and not game.advancing_figure_id_2:
                    # Prevent selecting the same figure twice
                    if figure_id == game.advancing_figure_id:
                        return jsonify({'success': False, 'message': 'This figure is already selected'}), 400
                    # Second advance pick — validate same color
                    first_figure = db.session.get(Figure, game.advancing_figure_id)
                    if first_figure and first_figure.color != figure.color:
                        return jsonify({'success': False, 'message': 'Second figure must be the same color as the first'}), 400
                    game.advancing_figure_id_2 = figure_id
                    is_second_pick = True
                else:
                    # First advance pick
                    game.advancing_figure_id = figure_id
                    game.advancing_player_id = player_id
                    # Check if there's another eligible village figure of same color
                    # Exclude figures with resource deficit (they can't advance)
                    eligible_seconds = Figure.query.filter(
                        Figure.player_id == player_id,
                        Figure.id != figure_id,
                        Figure.field == 'village',
                        Figure.color == figure.color
                    ).all()
                    eligible_seconds = [
                        f for f in eligible_seconds
                        if not _check_figure_resource_deficit(f, player_id, game.id)
                    ]
                    if eligible_seconds:
                        civil_war_need_second = True
                        civil_war_color = figure.color
        else:
            # Normal (non-Civil War) flow
            if game.advancing_figure_id and game.advancing_player_id == player_id:
                return jsonify({'success': False, 'message': 'You already have a figure advancing'}), 400
            
            if is_counter_advance:
                game.defending_figure_id = figure_id
            else:
                game.advancing_figure_id = figure_id
                game.advancing_player_id = player_id

        # Determine turn flip behavior
        other_player = game.players[0] if game.players[0].id != player_id else game.players[1]

        if is_counter_advance:
            # Counter-advance consumes a turn
            player.turns_left -= 1
        elif not is_second_pick:
            # First advance — advancing player becomes invader
            game.invader_player_id = player_id
            # Advancing player's turns exhausted; opponent gets 1 turn to counter-advance
            player.turns_left = 0
            other_player.turns_left = 1

        conquer_skip_counter_advance = (
            game.mode == 'conquer' and
            not is_counter_advance and
            _conquer_defender_counter_advance_disabled(game)
        )

        if civil_war_need_second:
            # Don't flip turn — player needs to pick a second figure
            logger.info(f"[ADVANCE] Civil War — waiting for second figure pick (color: {civil_war_color})")
        elif conquer_skip_counter_advance:
            logger.info(
                f"[ADVANCE] Conquer fallback strategy — turn stays on invader "
                f"for defender selection (game={game_id})"
            )
            game.turn_player_id = player_id
        elif has_blitzkrieg and not is_counter_advance:
            if game.mode == 'conquer':
                # Conquer: defender doesn't play interactively.  Keep turn on
                # the invader so they can immediately select the defender's
                # battle figure via select_defender().
                logger.info(f"[ADVANCE] Blitzkrieg + conquer — turn stays on invader for defender selection")
                game.turn_player_id = player_id
            else:
                # Duel: give defender their last turn (build, etc.) before
                # the invader selects which defender figure to fight.
                # Counter-advance is blocked separately, so the defender can only
                # do non-advance actions on this turn.
                logger.info(f"[ADVANCE] Blitzkrieg active — defender gets last turn before defender selection")
                game.turn_player_id = other_player.id
        else:
            # Normal: flip turn to opponent
            game.turn_player_id = other_player.id

        # Create log entry
        user = db.session.get(User, player.user_id)
        username = user.username if user else f"Player {player_id}"
        action_type = 'counter_advance' if is_counter_advance else 'advance'
        pick_suffix = " (2nd Civil War pick)" if is_second_pick else ""
        log_entry = LogEntry(
            game_id=game_id,
            player_id=player_id,
            round_number=game.current_round,
            turn_number=player.turns_left,
            message=f"{username} advanced {figure.name} toward battle.{pick_suffix}",
            author=username,
            type=action_type
        )
        db.session.add(log_entry)
        db.session.commit()

        return jsonify({
            'success': True,
            'is_counter_advance': is_counter_advance,
            'civil_war_need_second': civil_war_need_second,
            'civil_war_color': civil_war_color,
            'is_second_pick': is_second_pick,
            'figure_name': figure.name,
            'game': game.serialize()
        })

    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to advance figure')
        return jsonify({'success': False, 'message': 'Failed to advance figure'}), 400


@games.route('/select_defender', methods=['POST'])
@require_token
def select_defender():
    """
    The advancing player selects a defending figure from the OPPONENT's figures.
    Used after the opponent spent their turn without counter-advancing.
    The advancing player picks which opponent figure will face the advance.
    """
    try:
        data = request.json
        game_id = data['game_id']
        player_id = data['player_id']
        figure_id = data['figure_id']

        err = verify_player_ownership(player_id)
        if err:
            return err

        game = db.session.get(Game, game_id)
        if not game:
            return jsonify({'success': False, 'message': 'Game not found'}), 404

        # There must be an active advance
        if not game.advancing_figure_id:
            return jsonify({'success': False, 'message': 'No advancing figure in play'}), 400

        # The caller must be the advancing player (they pick the opponent's defender)
        if game.advancing_player_id != player_id:
            return jsonify({'success': False, 'message': 'Only the advancing player can select the defender'}), 400

        # Defender selection must happen on the advancing player's turn.
        if game.turn_player_id != player_id:
            return jsonify({'success': False, 'message': 'Not your turn to select defender'}), 400

        # Validate figure belongs to the OPPONENT (not the advancing player)
        figure = db.session.get(Figure, figure_id)
        if not figure:
            return jsonify({'success': False, 'message': 'Figure not found'}), 400
        if figure.player_id == player_id:
            return jsonify({'success': False, 'message': 'You must select an opponent\'s figure, not your own'}), 400
        
        # Check checkmate constraint (checkmate figures cannot be selected
        # as defenders UNLESS the opponent has no other valid figures).
        if getattr(figure, 'checkmate', False):
            opponent_id = figure.player_id
            other_figures = Figure.query.filter(
                Figure.player_id == opponent_id,
                Figure.id != figure_id,
                Figure.game_id == game_id
            ).all()
            has_non_checkmate = any(
                not getattr(f, 'checkmate', False)
                for f in other_figures
            )
            if has_non_checkmate:
                return jsonify({'success': False, 'message': f'{figure.name} has Checkmate and cannot be selected as a defender'}), 400
            # else: opponent only has checkmate figures — allow targeting
        
        # Check battle modifiers for Civil War
        modifiers = game.battle_modifier if isinstance(game.battle_modifier, list) else []
        has_civil_war = any(m.get('type') == 'Civil War' for m in modifiers)
        
        civil_war_need_second = False
        civil_war_color = None
        is_second_pick = False
        
        if has_civil_war:
            if game.defending_figure_id and not game.defending_figure_id_2:
                # Prevent selecting the same figure twice
                if figure_id == game.defending_figure_id:
                    return jsonify({'success': False, 'message': 'This figure is already selected'}), 400
                # Second defender pick — validate same color
                first_defender = db.session.get(Figure, game.defending_figure_id)
                if first_defender and first_defender.color != figure.color:
                    # Graceful fallback: keep first defender only and proceed.
                    # This avoids deadlocks from accidental wrong-color picks.
                    msg = (f"Civil War requires same-color defenders. "
                           f"Keeping first defender only: {first_defender.name}.")
                    logger.info(f"[CIVIL_WAR] Wrong-color second defender rejected. "
                                f"game={game_id}, invader={player_id}, first={first_defender.id}, "
                                f"first_color={first_defender.color}, attempted={figure_id}, "
                                f"attempted_color={figure.color}")
                    return jsonify({
                        'success': True,
                        'figure_name': first_defender.name,
                        'civil_war_need_second': False,
                        'civil_war_color': first_defender.color,
                        'is_second_pick': False,
                        'civil_war_second_rejected': True,
                        'message': msg,
                        'game': game.serialize()
                    })
                game.defending_figure_id_2 = figure_id
                is_second_pick = True
            else:
                # First defender pick
                game.defending_figure_id = figure_id
                # Check if there's another eligible opponent village figure of same color
                opponent_id = figure.player_id
                eligible_seconds = Figure.query.filter(
                    Figure.player_id == opponent_id,
                    Figure.id != figure_id,
                    Figure.field == 'village',
                    Figure.color == figure.color
                ).all()
                if eligible_seconds:
                    civil_war_need_second = True
                    civil_war_color = figure.color
        else:
            game.defending_figure_id = figure_id

        # Check if the selected defender has a resource deficit.
        # The invader can pick deficit figures (can't tell if it's a bluff),
        # but if the figure truly has a deficit, the defender auto-loses.
        defender_owner_id = figure.player_id
        if _check_figure_resource_deficit(figure, defender_owner_id, game.id):
            # Defender's figure has a deficit — defender auto-loses the battle
            invader_player = db.session.get(Player, player_id)
            defender_player = db.session.get(Player, defender_owner_id)
            invader_user = db.session.get(User, invader_player.user_id)
            defender_user = db.session.get(User, defender_player.user_id)
            invader_name = invader_user.username if invader_user else f"Player {player_id}"
            defender_name = defender_user.username if defender_user else f"Player {defender_owner_id}"
            return _resolve_deficit_loss(game, invader_player, defender_player, invader_name, defender_name, figure.name)

        db.session.commit()

        return jsonify({
            'success': True,
            'figure_name': figure.name,
            'civil_war_need_second': civil_war_need_second,
            'civil_war_color': civil_war_color,
            'is_second_pick': is_second_pick,
            'game': game.serialize()
        })

    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to select defender')
        return jsonify({'success': False, 'message': 'Failed to select defender'}), 400


@games.route('/skip_civil_war_second', methods=['POST'])
@require_token
def skip_civil_war_second():
    """
    Player skips selecting a second Civil War figure.
    Flips the turn to the opponent (or proceeds with defender selection).
    """
    try:
        data = request.json
        game_id = data['game_id']
        player_id = data['player_id']
        context = data.get('context', 'advance')  # 'advance' or 'defender'

        err = verify_player_ownership(player_id)
        if err:
            return err

        game = db.session.get(Game, game_id)
        if not game:
            return jsonify({'success': False, 'message': 'Game not found'}), 404

        player = db.session.get(Player, player_id)
        if not player:
            return jsonify({'success': False, 'message': 'Player not found'}), 404

        # Validate it's this player's turn
        if game.turn_player_id != player_id:
            return jsonify({'success': False, 'message': 'Not your turn'}), 400

        # Only flip turn for advance context (defender gets to respond)
        # For defender selection context, turn stays with invader for fight/fold
        if context == 'advance':
            other_player = game.players[0] if game.players[0].id != player_id else game.players[1]
            game.turn_player_id = other_player.id

        # Log
        user = db.session.get(User, player.user_id)
        username = user.username if user else f"Player {player_id}"
        log_entry = LogEntry(
            game_id=game_id,
            player_id=player_id,
            round_number=game.current_round,
            turn_number=player.turns_left,
            message=f"{username} chose to fight with only one figure (Civil War).",
            author=username,
            type='civil_war_skip'
        )
        db.session.add(log_entry)
        db.session.commit()

        logger.info(f"[CIVIL_WAR] {username} skipped second pick ({context}). Turn flipped.")

        return jsonify({
            'success': True,
            'game': game.serialize()
        })

    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to skip civil war second')
        return jsonify({'success': False, 'message': 'Failed to skip'}), 400


def _resolve_conquer_auto_loss(game, winner_player, loser_player,
                               requesting_player, log_message, log_type,
                               auto_loss_reason, auto_loss_detail):
    """Resolve an auto-loss / fold while in conquer mode.

    Conquer games are single-battle: an auto-loss must end the game and
    transfer land/cards via :func:`_resolve_conquer_battle`. It must NOT
    fall through to duel-mode behaviour (10-point award, side-card draw,
    new round, winner-becomes-invader).
    """
    log_entry = LogEntry(
        game_id=game.id,
        player_id=loser_player.id,
        round_number=game.current_round,
        turn_number=loser_player.turns_left,
        message=log_message,
        author="System",
        type=log_type,
    )
    db.session.add(log_entry)

    # Same pre-resolve cleanup as the regular conquer finish_battle path.
    _return_unplayed_battle_move_cards(game.id)
    _delete_all_battle_moves(game.id)
    _deactivate_all_spells(game)
    _clear_battle_state(game)

    result = _resolve_conquer_battle(game, winner_player, requesting_player)

    # Surface the auto-loss reason so the client can show a tailored
    # message even though the game is already 'finished'.
    result['auto_loss_reason'] = auto_loss_reason
    result['auto_loss_detail'] = auto_loss_detail

    db.session.commit()
    logger.info(
        f"[CONQUER_AUTO_LOSS] game={game.id} reason={auto_loss_reason} "
        f"winner={winner_player.id} loser={loser_player.id}"
    )
    return result


@games.route('/cannot_advance_loss', methods=['POST'])
@require_token
def cannot_advance_loss():
    """
    Handle the case where a player cannot advance any figure (e.g., all figures
    restricted by battle modifiers). The player automatically loses the battle.
    Clears battle state and starts a new round.
    """
    try:
        data = request.json
        game_id = data['game_id']
        player_id = data['player_id']

        err = verify_player_ownership(player_id)
        if err:
            return err

        game = db.session.get(Game, game_id)
        if not game:
            return jsonify({'success': False, 'message': 'Game not found'}), 404

        player = db.session.get(Player, player_id)
        if not player:
            return jsonify({'success': False, 'message': 'Player not found'}), 404

        # Validate it's this player's turn
        if game.turn_player_id != player_id:
            return jsonify({'success': False, 'message': 'Not your turn'}), 400

        # Get player info for logging
        user = db.session.get(User, player.user_id)
        username = user.username if user else f"Player {player_id}"

        # Get opponent
        opponent = next((p for p in game.players if p.id != player_id), None)
        opponent_user = db.session.get(User, opponent.user_id) if opponent else None
        opponent_name = opponent_user.username if opponent_user else "Opponent"

        # ── Conquer mode: single-battle game, no new round / side cards. ──
        if game.mode == 'conquer':
            return jsonify(_resolve_conquer_auto_loss(
                game,
                winner_player=opponent,
                loser_player=player,
                requesting_player=player,
                log_message=(
                    f"{username} could not advance any figure and loses the "
                    f"battle. {opponent_name} conquers!"
                ),
                log_type='auto_loss',
                auto_loss_reason='no_figures_to_advance',
                auto_loss_detail=username,
            ))

        # Award points to winner (same as fold)
        opponent.points += 10

        # Log the auto-loss
        log_entry = LogEntry(
            game_id=game_id,
            player_id=player_id,
            round_number=game.current_round,
            turn_number=player.turns_left,
            message=f"{username} could not advance any figure and loses the battle. {opponent_name} wins 10 points!",
            author="System",
            type='auto_loss'
        )
        db.session.add(log_entry)

        # Set fold outcome so opponent detects it via polling
        game.fold_outcome = 'fold_win'
        game.fold_winner_id = opponent.id
        game.auto_loss_reason = 'no_figures_to_advance'
        game.auto_loss_detail = username  # The loser's name

        # Collect resting figure IDs BEFORE clearing battle state
        resting_ids = _collect_resting_figure_ids(game)

        # Full post-battle cleanup: battle moves, spells, battle state, new round with side cards
        _return_unplayed_battle_move_cards(game_id)
        _delete_all_battle_moves(game_id)
        _deactivate_all_spells(game)
        _clear_battle_state(game)
        # Restore fold state that _clear_battle_state just cleared
        game.fold_outcome = 'fold_win'
        game.fold_winner_id = opponent.id
        game.auto_loss_reason = 'no_figures_to_advance'
        game.auto_loss_detail = username

        # ── Check game-over condition ──
        game_over_info = _check_game_over(game)
        if game_over_info:
            db.session.commit()
            return jsonify({
                'success': True,
                'outcome': 'auto_loss',
                'game_over': game_over_info,
                'game': game.serialize(),
            })

        # Start new round — opponent (winner) becomes invader, draws side cards
        _start_new_round(game, opponent)

        # Set resting figures for the new round (server-side — figures with rest_after_attack)
        if resting_ids:
            game.resting_figure_ids = resting_ids

        db.session.commit()

        logger.info(f"[AUTO_LOSS] {username} cannot advance — loses battle. Round {game.current_round} starts. New invader: {game.invader_player_id}")

        return jsonify({
            'success': True,
            'loser': username,
            'winner': opponent_name,
            'points': 10,
            'game': game.serialize()
        })

    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to process auto-loss')
        return jsonify({'success': False, 'message': 'Failed to process auto-loss'}), 400


@games.route('/defender_no_figures_loss', methods=['POST'])
@require_token
def defender_no_figures_loss():
    """
    Handle the case where the defender has no valid figures for battle selection.
    Called by the invader when they enter defender selection mode and find no selectable
    opponent figures. The defender automatically loses the battle.
    Clears battle state and starts a new round.
    """
    try:
        data = request.json
        game_id = data['game_id']
        player_id = data['player_id']  # The invader calling this

        err = verify_player_ownership(player_id)
        if err:
            return err

        game = db.session.get(Game, game_id)
        if not game:
            return jsonify({'success': False, 'message': 'Game not found'}), 404

        player = db.session.get(Player, player_id)
        if not player:
            return jsonify({'success': False, 'message': 'Player not found'}), 404

        # Validate it's this player's turn (the invader)
        if game.turn_player_id != player_id:
            return jsonify({'success': False, 'message': 'Not your turn'}), 400

        # Validate this is the advancing player
        if game.advancing_player_id != player_id:
            return jsonify({'success': False, 'message': 'Only the advancing player can report this'}), 400

        # Get invader info
        user = db.session.get(User, player.user_id)
        username = user.username if user else f"Player {player_id}"

        # Get defender (opponent) info
        opponent = next((p for p in game.players if p.id != player_id), None)
        opponent_user = db.session.get(User, opponent.user_id) if opponent else None
        opponent_name = opponent_user.username if opponent_user else "Opponent"

        # ── Conquer mode: single-battle game, no new round / side cards. ──
        if game.mode == 'conquer':
            return jsonify(_resolve_conquer_auto_loss(
                game,
                winner_player=player,
                loser_player=opponent,
                requesting_player=player,
                log_message=(
                    f"{opponent_name} has no valid battle figures and loses "
                    f"the battle. {username} conquers!"
                ),
                log_type='auto_loss',
                auto_loss_reason='no_defender_figures',
                auto_loss_detail=opponent_name,
            ))

        # Award points to winner (same as fold)
        player.points += 10

        # Log the auto-loss for the defender
        log_entry = LogEntry(
            game_id=game_id,
            player_id=opponent.id,
            round_number=game.current_round,
            turn_number=opponent.turns_left if opponent else 0,
            message=f"{opponent_name} has no valid battle figures and loses the battle. {username} wins 10 points!",
            author="System",
            type='auto_loss'
        )
        db.session.add(log_entry)

        # Set fold outcome so opponent detects it via polling
        game.fold_outcome = 'fold_win'
        game.fold_winner_id = player.id
        game.auto_loss_reason = 'no_defender_figures'
        game.auto_loss_detail = opponent_name  # The loser's name

        # Collect resting figure IDs BEFORE clearing battle state
        resting_ids = _collect_resting_figure_ids(game)

        # Full post-battle cleanup: battle moves, spells, battle state, new round with side cards
        _return_unplayed_battle_move_cards(game_id)
        _delete_all_battle_moves(game_id)
        _deactivate_all_spells(game)
        _clear_battle_state(game)
        # Restore fold state that _clear_battle_state just cleared
        game.fold_outcome = 'fold_win'
        game.fold_winner_id = player.id
        game.auto_loss_reason = 'no_defender_figures'
        game.auto_loss_detail = opponent_name

        # ── Check game-over condition ──
        game_over_info = _check_game_over(game)
        if game_over_info:
            db.session.commit()
            return jsonify({
                'success': True,
                'outcome': 'auto_loss',
                'game_over': game_over_info,
                'game': game.serialize(),
            })

        # Start new round — invader (winner) stays invader, draws side cards
        _start_new_round(game, player)

        # Set resting figures for the new round (server-side — figures with rest_after_attack)
        if resting_ids:
            game.resting_figure_ids = resting_ids

        db.session.commit()

        logger.info(f"[DEFENDER_NO_FIGURES] {opponent_name} has no valid figures — loses battle. Round {game.current_round} starts. New invader: {game.invader_player_id}")

        return jsonify({
            'success': True,
            'loser': opponent_name,
            'winner': username,
            'points': 10,
            'game': game.serialize()
        })

    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to process defender auto-loss')
        return jsonify({'success': False, 'message': 'Failed to process defender auto-loss'}), 400


@games.route('/battle_decision', methods=['POST'])
@require_token
def battle_decision():
    """
    Record a player's battle decision (fight or fold), sequential order.
    The invader (advancing player) decides first, then the defender.
    - Invader folds: defender wins 10 points, new round, winner = invader, ceasefire starts
    - Invader fights, defender folds: invader wins 10 points, new round, invader stays, ceasefire starts
    - Both fight: battle_confirmed = True, proceed to battle screen
    """
    try:
        data = request.json
        game_id = data['game_id']
        player_id = data['player_id']
        decision = data['decision']  # 'battle' or 'fold'

        if decision not in ('battle', 'fold'):
            return jsonify({'success': False, 'message': 'Invalid decision. Must be "battle" or "fold".'}), 400

        err = verify_player_ownership(player_id)
        if err:
            return err

        game = db.session.get(Game, game_id)
        if not game:
            return jsonify({'success': False, 'message': 'Game not found'}), 404

        player = db.session.get(Player, player_id)
        if not player:
            return jsonify({'success': False, 'message': 'Player not found'}), 404

        is_advancing = (player_id == game.advancing_player_id)

        # Guard: battle already confirmed — no new decisions allowed
        if game.battle_confirmed:
            return jsonify({
                'success': True,
                'resolved': True,
                'outcome': 'battle',
                'game': game.serialize()
            })

        decisions = dict(game.battle_decisions) if game.battle_decisions else {}

        # Get player info
        user = db.session.get(User, player.user_id)
        username = user.username if user else f"Player {player_id}"
        opponent = next((p for p in game.players if p.id != player_id), None)
        opponent_user = db.session.get(User, opponent.user_id) if opponent else None
        opponent_name = opponent_user.username if opponent_user else "Opponent"

        # Log the decision
        log_entry = LogEntry(
            game_id=game_id,
            player_id=player_id,
            round_number=game.current_round,
            turn_number=player.turns_left,
            message=f"{username} chose to {'fight' if decision == 'battle' else 'fold'}.",
            author="System",
            type='battle_decision'
        )
        db.session.add(log_entry)

        if is_advancing:
            # --- Invader decides first ---
            if decisions:
                return jsonify({'success': False, 'message': 'Invader decision already recorded'}), 400

            if decision == 'fold':
                # Invader folds — defender (opponent) wins
                winner_player = opponent
                loser_player = player
                winner_name = opponent_name
                loser_name = username
                return _resolve_fold(game, winner_player, loser_player, winner_name, loser_name)
            else:
                # Invader fights — record decision, wait for defender
                decisions[str(player_id)] = 'battle'
                game.battle_decisions = decisions
                db.session.commit()
                logger.info(f"[BATTLE_DECISION] {username} (invader) chose to fight. Waiting for defender.")
                return jsonify({
                    'success': True,
                    'resolved': False,
                    'waiting': True
                })
        else:
            # --- Defender decides second ---
            advancing_id = str(game.advancing_player_id)
            if decisions.get(advancing_id) != 'battle':
                return jsonify({'success': False, 'message': 'Invader has not decided yet or already resolved'}), 400

            if decision == 'fold':
                # Defender folds — invader (advancing player) wins
                invader_player = db.session.get(Player, game.advancing_player_id)
                invader_user = db.session.get(User, invader_player.user_id)
                winner_name = invader_user.username if invader_user else "Invader"
                loser_name = username
                return _resolve_fold(game, invader_player, player, winner_name, loser_name)
            else:
                # Both chose to fight — proceed to battle
                game.battle_confirmed = True
                game.battle_decisions = None
                # Enter a fresh battle-moves selection phase.
                # These fields can contain stale values after reconnects or
                # interrupted clients and must be reset before confirmations.
                game.battle_moves_confirmed = None
                game.battle_round = 0
                game.battle_turn_player_id = None
                game.battle_skipped_rounds = None
                game.battle_gamble_counts = None

                # Auto-fill both players' hands before entering battle shop
                invader_player = db.session.get(Player, game.advancing_player_id)
                defender_player = player  # current player is the defender
                auto_fill_invader = _check_and_fill_minimum_cards(game, invader_player)
                auto_fill_defender = _check_and_fill_minimum_cards(game, defender_player)
                if auto_fill_invader:
                    logger.info(f"[BATTLE_DECISION] Auto-filled invader {invader_player.id}: {auto_fill_invader}")
                if auto_fill_defender:
                    logger.info(f"[BATTLE_DECISION] Auto-filled defender {defender_player.id}: {auto_fill_defender}")

                log_entry = LogEntry(
                    game_id=game_id,
                    player_id=None,
                    round_number=game.current_round,
                    turn_number=0,
                    message="Both players chose to fight! Battle begins.",
                    author="System",
                    type='battle_start'
                )
                db.session.add(log_entry)
                db.session.commit()
                logger.info(f"[BATTLE_DECISION] Both players chose battle. Proceeding to battle screen.")
                return jsonify({
                    'success': True,
                    'resolved': True,
                    'outcome': 'battle',
                    'game': game.serialize()
                })

    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to process battle decision')
        return jsonify({'success': False, 'message': 'Failed to process battle decision'}), 400


def _check_figure_resource_deficit(figure, player_id, game_id):
    """Check if a figure has a resource deficit (requires more than produced by the player's figures).

    Figures that themselves have a deficit do NOT contribute their production,
    so the check is iterative until stable.
    """
    if not figure.requires:
        return False

    # Calculate total produces and requires across ALL of this player's figures
    all_figures = Figure.query.filter_by(player_id=player_id, game_id=game_id).all()

    # Total requires is always the full sum
    total_requires = {}
    for fig in all_figures:
        if fig.requires:
            for res, amount in fig.requires.items():
                total_requires[res] = total_requires.get(res, 0) + amount

    # Iteratively exclude production from deficit figures until stable
    excluded = set()
    stable = False
    while not stable:
        stable = True
        total_produces = {}
        for i, fig in enumerate(all_figures):
            if i in excluded:
                continue
            if fig.produces:
                for res, amount in fig.produces.items():
                    total_produces[res] = total_produces.get(res, 0) + amount
        for i, fig in enumerate(all_figures):
            if i in excluded:
                continue
            if not fig.requires:
                continue
            for res_name in fig.requires:
                if total_requires.get(res_name, 0) > total_produces.get(res_name, 0):
                    excluded.add(i)
                    stable = False
                    break

    # Check if the target figure's required resources are in deficit
    for resource_name in figure.requires:
        total_req = total_requires.get(resource_name, 0)
        total_prod = total_produces.get(resource_name, 0)
        if total_req > total_prod:
            return True
    return False


def _resolve_deficit_loss(game, winner_player, loser_player, winner_name, loser_name, figure_name):
    """Resolve an auto-loss due to a figure having resource deficit in battle."""
    # ── Conquer mode: single-battle, end the game cleanly. ──
    if game.mode == 'conquer':
        return jsonify(_resolve_conquer_auto_loss(
            game,
            winner_player=winner_player,
            loser_player=loser_player,
            requesting_player=winner_player,
            log_message=(
                f"{loser_name}'s {figure_name} has a resource deficit and "
                f"cannot fight. {winner_name} conquers!"
            ),
            log_type='deficit_loss',
            auto_loss_reason='resource_deficit',
            auto_loss_detail=figure_name,
        ))

    winner_player.points += 10

    game.battle_decisions = None
    game.fold_outcome = 'fold_win'
    game.fold_winner_id = winner_player.id
    game.auto_loss_reason = 'resource_deficit'
    game.auto_loss_detail = figure_name  # The figure with the deficit

    log_entry = LogEntry(
        game_id=game.id,
        player_id=loser_player.id,
        round_number=game.current_round,
        turn_number=loser_player.turns_left,
        message=f"{loser_name}'s {figure_name} has a resource deficit and cannot fight. {winner_name} wins 10 points!",
        author="System",
        type='deficit_loss'
    )
    db.session.add(log_entry)

    # Collect resting figure IDs BEFORE clearing battle state
    resting_ids = _collect_resting_figure_ids(game)

    # Full post-battle cleanup: battle moves, spells, battle state, new round with side cards
    _return_unplayed_battle_move_cards(game.id)
    _delete_all_battle_moves(game.id)
    _deactivate_all_spells(game)
    _clear_battle_state(game)
    # Restore fold state that _clear_battle_state just cleared
    game.fold_outcome = 'fold_win'
    game.fold_winner_id = winner_player.id
    game.auto_loss_reason = 'resource_deficit'
    game.auto_loss_detail = figure_name

    # ── Check game-over condition ──
    game_over_info = _check_game_over(game)
    if game_over_info:
        db.session.commit()
        return jsonify({
            'success': True,
            'deficit_loss': True,
            'game_over': game_over_info,
            'game': game.serialize()
        })

    # Start new round — winner becomes invader, draws side cards
    _start_new_round(game, winner_player)

    # Set resting figures for the new round (server-side — figures with rest_after_attack)
    if resting_ids:
        game.resting_figure_ids = resting_ids

    db.session.commit()
    logger.info(f"[DEFICIT_LOSS] {loser_name}'s {figure_name} has resource deficit. {winner_name} wins 10 points. Round {game.current_round} starts.")

    return jsonify({
        'success': True,
        'deficit_loss': True,
        'deficit_figure_name': figure_name,
        'winner': winner_name,
        'loser': loser_name,
        'points': 10,
        'game': game.serialize()
    })


def _resolve_fold(game, winner_player, loser_player, winner_name, loser_name):
    """Helper to resolve a fold: award points, reset round, start ceasefire."""
    # ── Conquer mode: single-battle, end the game cleanly. ──
    if game.mode == 'conquer':
        return jsonify(_resolve_conquer_auto_loss(
            game,
            winner_player=winner_player,
            loser_player=loser_player,
            requesting_player=winner_player,
            log_message=(
                f"{loser_name} folded. {winner_name} conquers!"
            ),
            log_type='fold_win',
            auto_loss_reason='fold',
            auto_loss_detail=loser_name,
        ))

    # Award points to winner
    winner_player.points += 10

    game.battle_decisions = None
    game.fold_outcome = 'fold_win'
    game.fold_winner_id = winner_player.id
    game.auto_loss_reason = 'fold'
    game.auto_loss_detail = loser_name  # The player who folded

    log_entry = LogEntry(
        game_id=game.id,
        player_id=loser_player.id,
        round_number=game.current_round,
        turn_number=loser_player.turns_left,
        message=f"{loser_name} folded. {winner_name} wins 10 points! A new round begins.",
        author="System",
        type='fold_win'
    )
    db.session.add(log_entry)

    # Collect resting figure IDs BEFORE clearing battle state
    resting_ids = _collect_resting_figure_ids(game)

    # Full post-battle cleanup: battle moves, spells, battle state, new round with side cards
    _return_unplayed_battle_move_cards(game.id)
    _delete_all_battle_moves(game.id)
    _deactivate_all_spells(game)
    _clear_battle_state(game)
    # Restore fold state that _clear_battle_state just cleared
    game.fold_outcome = 'fold_win'
    game.fold_winner_id = winner_player.id
    game.auto_loss_reason = 'fold'
    game.auto_loss_detail = loser_name

    # ── Check game-over condition ──
    game_over_info = _check_game_over(game)
    if game_over_info:
        db.session.commit()
        return jsonify({
            'success': True,
            'resolved': True,
            'outcome': 'fold_win',
            'game_over': game_over_info,
            'game': game.serialize()
        })

    # Start new round — winner becomes invader, draws side cards
    _start_new_round(game, winner_player)

    # Set resting figures for the new round (server-side — figures with rest_after_attack)
    if resting_ids:
        game.resting_figure_ids = resting_ids

    db.session.commit()
    logger.info(f"[BATTLE_DECISION] {loser_name} folded. {winner_name} wins 10 points. Round {game.current_round} starts. New invader: {winner_player.id}")

    return jsonify({
        'success': True,
        'resolved': True,
        'outcome': 'fold_win',
        'winner': winner_name,
        'loser': loser_name,
        'points': 10,
        'game': game.serialize()
    })


# ────────────────────── battle resolution ─────────────────────────

# Override base power by field type (family-level config).
# Figures whose ``field`` matches a key here use the fixed value
# instead of summing their card values.
_FIELD_OVERRIDE_BASE_POWER = {
    'castle': 15,
}


def _compute_figure_base_power(figure):
    """Compute a figure's base power on the server side.

    If the figure's field has an override (e.g. castle → 15), that fixed
    value is returned.  Otherwise the sum of card values is used.
    """
    override = _FIELD_OVERRIDE_BASE_POWER.get(figure.field)
    if override is not None:
        return override
    card_assocs = CardToFigure.query.filter_by(figure_id=figure.id).all()
    total = 0
    for assoc in card_assocs:
        if assoc.card_type == 'main':
            card = db.session.get(MainCard, assoc.card_id)
        else:
            card = db.session.get(SideCard, assoc.card_id)
        if card:
            total += card.value
    return total


# ── Server-authoritative total_diff computation ──────────────────
# Spades → Hearts → Clubs → Diamonds → Spades
_SUIT_ADVANTAGE = {
    'Spades': 'Hearts',
    'Hearts': 'Clubs',
    'Clubs': 'Diamonds',
    'Diamonds': 'Spades',
}


def _get_advantage_suit(suit):
    """Return the suit that *suit* has an advantage over."""
    return _SUIT_ADVANTAGE.get(suit)


def _compute_support_bonus(figure, all_figures, game_id,
                           land_suit_bonus=None):
    """Support bonus from same-player, same-suit figures of appropriate type.

    Matches client ``_calculate_battle_bonus_received`` exactly.
    Figures in resource deficit do NOT provide support bonus.

    *land_suit_bonus*: optional ``(suit_str, value_int)`` tuple for conquer
    mode.  Every figure whose suit matches gets *value* added.
    """
    fig_field = (figure.field or '').lower()
    if fig_field == 'castle':
        valid_fields = {'castle'}
    elif fig_field == 'village':
        valid_fields = {'castle'}
    elif fig_field == 'military':
        valid_fields = {'castle', 'village'}
    else:
        return 0

    total = 0
    for f in all_figures:
        if f.id == figure.id or f.player_id != figure.player_id:
            continue
        if (f.suit or '').lower() != (figure.suit or '').lower():
            continue
        f_field = (f.field or '').lower()
        if f_field not in valid_fields:
            continue
        # Military figures provide 0 bonus
        if f_field == 'military':
            continue
        # Figures in deficit provide nothing
        if _check_figure_resource_deficit(f, f.player_id, game_id):
            continue
        # Castle: Maharaja +5, King +4
        if f_field == 'castle':
            total += 5 if 'Maharaja' in (f.name or '') else 4
        else:
            # Village: sum of KEY card values only (not number/upgrade cards)
            for assoc in CardToFigure.query.filter_by(figure_id=f.id).all():
                if assoc.role == CardRole.KEY:
                    if assoc.card_type == 'main':
                        card = db.session.get(MainCard, assoc.card_id)
                    else:
                        card = db.session.get(SideCard, assoc.card_id)
                    if card:
                        total += card.value

    # Conquer mode: land suit bonus (applied to every matching figure)
    if land_suit_bonus:
        bonus_suit, bonus_value = land_suit_bonus
        if (figure.suit or '').lower() == bonus_suit.lower():
            total += bonus_value

    return total


def _find_healer_figures(player_id, all_figures, battle_ids, game_id):
    """Return list of Healer figures for *player_id* that are not in battle
    and not in resource deficit.  Matches client ``_detect_buffs_allies``."""
    healers = []
    for f in all_figures:
        if f.player_id != player_id:
            continue
        if f.id in battle_ids:
            continue
        if 'Healer' not in (f.name or ''):
            continue
        if _check_figure_resource_deficit(f, player_id, game_id):
            continue
        healers.append(f)
    return healers


def _compute_healer_buff(figure, healers):
    """Healer buff: +4 per same-suit Healer for village figures.

    *healers* must already be pre-filtered by ``_find_healer_figures``
    (excludes battle figures and deficit figures).
    """
    if (figure.field or '').lower() != 'village':
        return 0
    buff = 0
    for h in healers:
        if (h.suit or '').lower() == (figure.suit or '').lower():
            buff += 4
    return buff


def _find_wall_figures(player_id, all_figures, battle_ids, game_id):
    """Return list of Wall figures for *player_id* that are not in battle
    and not in resource deficit.  Matches client ``_detect_buffs_allies_defence``."""
    walls = []
    for f in all_figures:
        if f.player_id != player_id:
            continue
        if f.id in battle_ids:
            continue
        if 'Wall' not in (f.name or ''):
            continue
        if _check_figure_resource_deficit(f, player_id, game_id):
            continue
        walls.append(f)
    return walls


def _compute_wall_defence_total(walls):
    """Sum of Wall number-card (side-card) values.

    *walls* must already be pre-filtered by ``_find_wall_figures``.
    """
    total = 0
    for f in walls:
        for assoc in CardToFigure.query.filter_by(figure_id=f.id).all():
            if assoc.card_type == 'side':
                card = db.session.get(SideCard, assoc.card_id)
                if card:
                    total += card.value
    return total


def _find_temple_blocker(target_figure, opponent_player_id, all_figures,
                         battle_ids, game_id):
    """True if opponent has a non-deficit, non-battle Temple with suit
    advantage over *target_figure*.

    Matches client ``_detect_blocks_bonus``.
    """
    for f in all_figures:
        if f.player_id != opponent_player_id:
            continue
        if f.id in battle_ids:
            continue
        if 'Temple' not in (f.name or ''):
            continue
        if _check_figure_resource_deficit(f, opponent_player_id, game_id):
            continue
        adv = _get_advantage_suit(f.suit)
        if adv and adv.lower() == (target_figure.suit or '').lower():
            return True
    return False


def _find_all_archer_da(player_id, all_figures, battle_ids, game_id):
    """Return a list of (advantage_suit, penalty_value) for ALL eligible Archers.

    Excludes battle figures and deficit figures.
    Matches client ``_detect_distance_attack`` (multi-archer).
    Returns an empty list if no eligible Archer found.
    """
    results = []
    for f in all_figures:
        if f.player_id != player_id:
            continue
        if f.id in battle_ids:
            logger.debug(f"[ARCHER_DA] Skipping {f.name} (id={f.id}): in battle_ids")
            continue
        if 'Archer' not in (f.name or ''):
            continue
        if _check_figure_resource_deficit(f, player_id, game_id):
            logger.debug(f"[ARCHER_DA] Skipping {f.name} (id={f.id}, suit={f.suit}): resource deficit")
            continue
        adv = _get_advantage_suit(f.suit)
        if not adv:
            logger.debug(f"[ARCHER_DA] Skipping {f.name} (id={f.id}, suit={f.suit}): no advantage suit")
            continue
        # Use the NUMBER card value as the penalty (matches client logic).
        # The Archer's key card and number card may both be side-deck cards;
        # we must pick the one with role='NUMBER'.
        assocs = CardToFigure.query.filter_by(figure_id=f.id).all()
        number_val = 0
        for assoc in assocs:
            if assoc.role == CardRole.NUMBER and assoc.card_type == 'side':
                card = db.session.get(SideCard, assoc.card_id)
                if card:
                    number_val = card.value
                    break
        if number_val == 0:
            # Fallback: use any side card value (shouldn't normally happen)
            for assoc in assocs:
                if assoc.card_type == 'side':
                    card = db.session.get(SideCard, assoc.card_id)
                    if card:
                        number_val = card.value
                        break
        if number_val == 0:
            logger.debug(f"[ARCHER_DA] Skipping {f.name} (id={f.id}): no side card found")
            continue
        logger.debug(f"[ARCHER_DA] Found {f.name} (id={f.id}, suit={f.suit}) → adv={adv}, penalty={number_val}")
        results.append((adv, number_val))
    if not results:
        logger.debug(f"[ARCHER_DA] No eligible Archer found for player {player_id}")
    return results


def _compute_enchantment_mod(figure_id, enchantment_spells):
    """Sum of active enchantment power modifiers on a figure."""
    total = 0
    for spell in enchantment_spells:
        if spell.target_figure_id != figure_id:
            continue
        ed = spell.effect_data or {}
        pm = ed.get('power_modifier', 0)
        if isinstance(pm, (int, float)) and pm != -999:
            total += int(pm)
    return total


def _compute_figure_full_power(figure, all_figures, enchant_spells,
                               opponent_player_id,
                               battle_ids, game_id,
                               own_healers, wall_total,
                               land_suit_bonus=None):
    """Full battle-figure power.  Matches client ``_get_figure_total_power``.

    Formula::

        base
        + healer_buff           (NOT affected by Temple)
        + support               (zeroed if Temple blocks)
        + wall                  (NOT affected by Temple)
        + enchantment
        − DA penalty            (handled externally, not here)

    *own_healers*: pre-filtered healer list for the figure's player
        (from ``_find_healer_figures``).
    *wall_total*: pre-computed wall defence total for the figure's player
        (0 when attacking, since only the defender gets wall defence).
    *land_suit_bonus*: optional ``(suit, value)`` for conquer mode land bonus.
    """
    if not figure:
        return 0
    base = _compute_figure_base_power(figure)

    # Healer buff (NOT affected by Temple)
    healer_buff = _compute_healer_buff(figure, own_healers)

    # Support bonus (includes land suit bonus in conquer mode)
    support = _compute_support_bonus(figure, all_figures, game_id,
                                     land_suit_bonus=land_suit_bonus)

    # Wall defence (pre-computed; 0 for attackers)
    wall = wall_total

    # Enchantment
    enchant = _compute_enchantment_mod(figure.id, enchant_spells)

    # Temple blocking zeroes support only (NOT healer, NOT wall)
    if _find_temple_blocker(figure, opponent_player_id, all_figures,
                            battle_ids, game_id):
        support = 0

    total = base + healer_buff + support + wall + enchant
    logger.debug(f"[FIG_POWER] {figure.name}(id={figure.id},suit={figure.suit}) "
          f"base={base} healer={healer_buff} support={support} "
          f"wall={wall} enchant={enchant} total={total}")
    return total


def _compute_move_effective_value(move, all_figures, game,
                                  player_id, own_healers):
    """Effective battle-move value including call-figure bonuses.

    *own_healers*: pre-filtered healer list for the move's player.

    Wall defence does NOT apply to call figures.
    DA on call figures is handled externally in ``_compute_server_total_diff``.
    """
    if not move or move.family_name == 'Block':
        return 0
    bm_value = move.value or 0
    if move.call_figure_id:
        call_fig = next(
            (f for f in all_figures if f.id == move.call_figure_id), None)
        if not call_fig:
            call_fig = db.session.get(Figure, move.call_figure_id)
        if call_fig:
            fig_power = _compute_figure_base_power(call_fig)
            healer = _compute_healer_buff(call_fig, own_healers)
            bm_suit = (move.suit or '').lower()
            fig_suit = (call_fig.suit or '').lower()
            if bm_suit == fig_suit:
                return fig_power + healer + bm_value
            return fig_power + healer
    return bm_value


def _compute_server_total_diff(game, return_breakdown=False):
    """Authoritative total_diff from DB.  Positive = invader wins.

    Mirrors the client's ``_get_total_diff()`` logic exactly:
    * figure power = base + healer + support + wall + enchant − DA
    * Healer/Wall/Temple/Archer with resource deficit are skipped
    * DA fires ONCE per archer per battle (battle figure first, then
      first matching call figure in rounds — never both)
    * Wall defence only applies to the DEFENDING side
    * Block zeroes the entire round

    If *return_breakdown* is True, returns ``(total, breakdown_dict)``
    instead of just ``total``.
    """
    adv_fig = (db.session.get(Figure, game.advancing_figure_id)
               if game.advancing_figure_id else None)
    def_fig = (db.session.get(Figure, game.defending_figure_id)
               if game.defending_figure_id else None)
    if not adv_fig or not def_fig:
        return 0

    adv_pid = game.advancing_player_id
    def_pid = next(p.id for p in game.players if p.id != adv_pid)

    all_figures = Figure.query.filter_by(game_id=game.id).all()
    enchant_spells = ActiveSpell.query.filter_by(
        game_id=game.id, is_active=True, spell_type='enchantment').all()
    all_moves = BattleMove.query.filter_by(game_id=game.id).all()

    # IDs of figures currently in battle (excluded from skill sources)
    battle_ids = set()
    for fid in (game.advancing_figure_id, game.advancing_figure_id_2,
                game.defending_figure_id, game.defending_figure_id_2):
        if fid:
            battle_ids.add(fid)

    # ── Pre-compute healer/wall lists (with deficit filtering) ──
    adv_healers = _find_healer_figures(adv_pid, all_figures, battle_ids,
                                       game.id)
    def_healers = _find_healer_figures(def_pid, all_figures, battle_ids,
                                       game.id)
    # Wall defence only applies to the defending side
    def_walls = _find_wall_figures(def_pid, all_figures, battle_ids, game.id)
    def_wall_total = _compute_wall_defence_total(def_walls)

    # ── Conquer mode: land suit bonus (applied via support bonus) ──
    land_suit_bonus = None
    if game.mode == 'conquer' and game.land_id:
        land = db.session.get(Land, game.land_id)
        if land and land.suit_bonus_suit and land.suit_bonus_value:
            land_suit_bonus = (land.suit_bonus_suit, land.suit_bonus_value)

    # ── figure power WITHOUT distance-attack (handled below) ──
    adv_power = _compute_figure_full_power(
        adv_fig, all_figures, enchant_spells,
        def_pid, battle_ids, game.id,
        adv_healers, 0,
        land_suit_bonus=land_suit_bonus)  # attacker: wall = 0
    def_power = _compute_figure_full_power(
        def_fig, all_figures, enchant_spells,
        adv_pid, battle_ids, game.id,
        def_healers, def_wall_total,
        land_suit_bonus=land_suit_bonus)

    if game.advancing_figure_id_2:
        f2 = db.session.get(Figure, game.advancing_figure_id_2)
        if f2:
            adv_power += _compute_figure_full_power(
                f2, all_figures, enchant_spells,
                def_pid, battle_ids, game.id,
                adv_healers, 0,
                land_suit_bonus=land_suit_bonus)
    if game.defending_figure_id_2:
        f2 = db.session.get(Figure, game.defending_figure_id_2)
        if f2:
            def_power += _compute_figure_full_power(
                f2, all_figures, enchant_spells,
                adv_pid, battle_ids, game.id,
                def_healers, def_wall_total,
                land_suit_bonus=land_suit_bonus)

    # ── Distance-attack: each eligible archer fires once per battle ──
    # Build list of defender targets
    def_targets = [def_fig]
    if game.defending_figure_id_2:
        f2 = db.session.get(Figure, game.defending_figure_id_2)
        if f2:
            def_targets.append(f2)

    adv_da_list = _find_all_archer_da(adv_pid, all_figures,
                                       battle_ids, game.id)
    adv_da_applied = []
    # Each archer fires at most once; each target can be hit by multiple archers
    for da_suit, da_val in adv_da_list:
        for fig in def_targets:
            if fig and da_suit.lower() == (fig.suit or '').lower():
                def_power -= da_val
                adv_da_applied.append((da_suit, da_val))
                logger.debug(f"[DA_APPLY] Adv archer DA fires: adv_suit={da_suit} vs "
                      f"def_fig={fig.name}(suit={fig.suit}) → def_power-={da_val}")
                break  # this archer consumed its shot

    # Build list of advancing targets
    adv_targets = [adv_fig]
    if game.advancing_figure_id_2:
        f2 = db.session.get(Figure, game.advancing_figure_id_2)
        if f2:
            adv_targets.append(f2)

    def_da_list = _find_all_archer_da(def_pid, all_figures,
                                       battle_ids, game.id)
    def_da_applied = []
    for da_suit, da_val in def_da_list:
        for fig in adv_targets:
            if fig and da_suit.lower() == (fig.suit or '').lower():
                adv_power -= da_val
                def_da_applied.append((da_suit, da_val))
                logger.debug(f"[DA_APPLY] Def archer DA fires: def_suit={da_suit} vs "
                      f"adv_fig={fig.name}(suit={fig.suit}) → adv_power-={da_val}")
                break  # this archer consumed its shot

    fig_diff = adv_power - def_power
    logger.debug(f"[TOTAL_DIFF] adv_power={adv_power} def_power={def_power} fig_diff={fig_diff} "
          f"adv_da={adv_da_applied} def_da={def_da_applied}")

    # ── round diffs from BattleMove records ──
    round_diff = 0
    for rnd in range(3):
        adv_m = [m for m in all_moves
                 if m.played_round == rnd and m.player_id == adv_pid]
        def_m = [m for m in all_moves
                 if m.played_round == rnd and m.player_id == def_pid]
        if not adv_m and not def_m:
            logger.debug(f"[ROUND_{rnd}] no moves — skipped")
            continue
        if any(m.family_name == 'Block' for m in adv_m + def_m):
            logger.debug(f"[ROUND_{rnd}] Block detected — zeroed")
            continue

        adv_val = sum(_compute_move_effective_value(
            m, all_figures, game, adv_pid, adv_healers) for m in adv_m)
        def_val = sum(_compute_move_effective_value(
            m, all_figures, game, def_pid, def_healers) for m in def_m)

        # Log per-move details
        for m in adv_m:
            mv = _compute_move_effective_value(m, all_figures, game, adv_pid, adv_healers)
            logger.debug(f"[ROUND_{rnd}] ADV move id={m.id} family={m.family_name} "
                  f"value={m.value} call_fig={m.call_figure_id} suit={m.suit} "
                  f"eff_val={mv}")
        for m in def_m:
            mv = _compute_move_effective_value(m, all_figures, game, def_pid, def_healers)
            logger.debug(f"[ROUND_{rnd}] DEF move id={m.id} family={m.family_name} "
                  f"value={m.value} call_fig={m.call_figure_id} suit={m.suit} "
                  f"eff_val={mv}")

        # Unfired DA archers target first matching call figure in opponent's moves
        for da_suit, da_val in adv_da_list:
            if (da_suit, da_val) in adv_da_applied:
                continue  # already consumed on a battle figure
            for m in def_m:
                if m.call_figure_id:
                    cf = next((f for f in all_figures
                               if f.id == m.call_figure_id), None)
                    if cf and da_suit.lower() == (cf.suit or '').lower():
                        def_val -= da_val
                        adv_da_applied.append((da_suit, da_val))
                        break
        for da_suit, da_val in def_da_list:
            if (da_suit, da_val) in def_da_applied:
                continue  # already consumed on a battle figure
            for m in adv_m:
                if m.call_figure_id:
                    cf = next((f for f in all_figures
                               if f.id == m.call_figure_id), None)
                    if cf and da_suit.lower() == (cf.suit or '').lower():
                        adv_val -= da_val
                        def_da_applied.append((da_suit, da_val))
                        break

        round_diff += adv_val - def_val
        logger.debug(f"[ROUND_{rnd}] adv_val={adv_val} def_val={def_val} "
              f"diff={adv_val - def_val} cumulative={round_diff}")

    total = fig_diff + round_diff

    # Land suit bonus is now included in each figure's support bonus
    # (computed inside _compute_figure_full_power via _compute_support_bonus)

    logger.debug(f"[SERVER_TOTAL_DIFF] game={game.id} "
          f"fig_diff={fig_diff} (adv={adv_power} def={def_power}) "
          f"round_diff={round_diff} land_suit_bonus={land_suit_bonus} total={total}")

    if return_breakdown:
        breakdown = {
            'adv_fig': adv_fig.name if adv_fig else None,
            'adv_fig_suit': adv_fig.suit if adv_fig else None,
            'def_fig': def_fig.name if def_fig else None,
            'def_fig_suit': def_fig.suit if def_fig else None,
            'adv_power': adv_power,
            'def_power': def_power,
            'adv_da_applied': adv_da_applied,
            'def_da_applied': def_da_applied,
            'def_wall_total': def_wall_total,
            'fig_diff': fig_diff,
            'round_diff': round_diff,
            'land_suit_bonus': land_suit_bonus,
            'total': total,
        }
        return total, breakdown
    return total


def _collect_battle_move_cards(game_id):
    """Collect all cards reserved for battle moves in a game.

    Returns (cards_list, battle_moves) where cards_list is a list of
    (card_obj, card_type_str) tuples and battle_moves is the queryset.
    """
    moves = BattleMove.query.filter_by(game_id=game_id).all()
    cards = []
    for bm in moves:
        # Primary card
        if bm.card_type == 'side':
            card = db.session.get(SideCard, bm.card_id)
        else:
            card = db.session.get(MainCard, bm.card_id)
        if card:
            cards.append((card, bm.card_type))

        # Second card (Double Dagger)
        if bm.card_id_b is not None:
            ct_b = bm.card_type_b or 'main'
            if ct_b == 'side':
                card_b = db.session.get(SideCard, bm.card_id_b)
            else:
                card_b = db.session.get(MainCard, bm.card_id_b)
            if card_b:
                cards.append((card_b, ct_b))
    return cards, moves


def _destroy_figure_and_collect_cards(figure):
    """Delete a figure and return its cards as a list of (card_obj, type_str).

    Does NOT return cards to deck yet — caller decides what happens with them.
    Cards are detached from the player (player_id=None) so they appear as
    orphans until finish_battle_pick_card returns them to the deck.
    """
    card_assocs = CardToFigure.query.filter_by(figure_id=figure.id).all()
    cards = []
    for assoc in card_assocs:
        if assoc.card_type == 'main':
            card = db.session.get(MainCard, assoc.card_id)
        else:
            card = db.session.get(SideCard, assoc.card_id)
        if card:
            card.part_of_figure = False
            card.player_id = None
            cards.append((card, assoc.card_type))

    # Delete associations and the figure
    CardToFigure.query.filter_by(figure_id=figure.id).delete()
    db.session.delete(figure)
    return cards


def _clear_battle_state(game):
    """Reset all battle / advance state on the game after resolution."""
    game.advancing_figure_id = None
    game.advancing_figure_id_2 = None
    game.advancing_player_id = None
    game.defending_figure_id = None
    game.defending_figure_id_2 = None
    game.battle_modifier = []
    game.battle_confirmed = False
    game.battle_decisions = None
    game.battle_moves_confirmed = None
    game.fold_outcome = None
    game.fold_winner_id = None
    game.auto_loss_reason = None
    game.auto_loss_detail = None
    game.battle_round = 0
    game.battle_turn_player_id = None
    game.battle_skipped_rounds = None
    game.battle_gamble_counts = None


def _collect_resting_figure_ids(game):
    """Return list of figure IDs that have rest_after_attack and were in the battle.

    MUST be called BEFORE _clear_battle_state, which wipes the advancing/defending IDs.
    Checks all four possible battle participants (advancing × 2, defending × 2).
    """
    resting = []
    for fig_id in (game.advancing_figure_id, game.advancing_figure_id_2,
                   game.defending_figure_id, game.defending_figure_id_2):
        if fig_id is not None:
            fig = db.session.get(Figure, fig_id)
            if fig and fig.rest_after_attack:
                resting.append(fig_id)
    return resting or None


def _deactivate_all_spells(game):
    """Deactivate all active spells in a game (post-battle cleanup)."""
    active = ActiveSpell.query.filter_by(game_id=game.id, is_active=True).all()
    for spell in active:
        spell.is_active = False


def _return_unplayed_battle_move_cards(game_id):
    """Return cards from unplayed battle moves back to their owners.

    Unplayed moves (played_round IS NULL) have their cards restored
    to the player's hand (part_of_battle_move=False, in_deck=False).
    The corresponding BattleMove rows are deleted.
    Played moves are left untouched for the loot/deck pool.
    """
    unplayed = BattleMove.query.filter_by(game_id=game_id).filter(
        BattleMove.played_round.is_(None)
    ).all()
    if unplayed:
        logger.info(f"[RETURN_UNPLAYED] game={game_id} returning {len(unplayed)} unplayed BM cards to owners")
    for bm in unplayed:
        # Primary card
        if bm.card_type == 'side':
            card = db.session.get(SideCard, bm.card_id)
        else:
            card = db.session.get(MainCard, bm.card_id)
        if card:
            card.part_of_battle_move = False
            card.in_deck = False
            logger.debug(f"[RETURN_UNPLAYED] bm_id={bm.id} card_id={card.id} ({bm.family_name}/{bm.suit}) → player {bm.player_id}")

        # Second card (Double Dagger)
        if bm.card_id_b is not None:
            ct_b = bm.card_type_b or 'main'
            if ct_b == 'side':
                card_b = db.session.get(SideCard, bm.card_id_b)
            else:
                card_b = db.session.get(MainCard, bm.card_id_b)
            if card_b:
                card_b.part_of_battle_move = False
                card_b.in_deck = False

        db.session.delete(bm)


def _delete_all_battle_moves(game_id):
    """Remove all BattleMove rows for a game."""
    BattleMove.query.filter_by(game_id=game_id).delete()


def _serialize_battle_card(card, card_type):
    """Create a serialisable dict for a card involved in the battle."""
    data = card.serialize() if hasattr(card, 'serialize') else {}
    data['card_type'] = card_type
    return data


def _start_new_round(game, winner_player):
    """Bump round counter, set invader, reset turns, start ceasefire, draw 2 side cards per player."""
    game.invader_player_id = winner_player.id
    game.current_round += 1
    for p in game.players:
        if p.id == game.invader_player_id:
            p.turns_left = settings.INITIAL_TURNS_INVADER
        else:
            p.turns_left = settings.INITIAL_TURNS_DEFENDER
    game.turn_player_id = game.invader_player_id
    game.ceasefire_active = True
    game.ceasefire_start_turn = 0

    # Clear resting figures — they have rested for the previous round
    game.resting_figure_ids = None

    # Draw 2 side cards per player for the new round
    drawn_cards_map = {}
    for p in game.players:
        try:
            cards = DeckManager.draw_cards_from_deck(game, p, 2, 'side')
            drawn_cards_map[str(p.id)] = [
                {'suit': c.suit.value, 'rank': c.rank.value}
                for c in cards
            ]
            logger.debug(f"[NEW_ROUND] Player {p.id} drew 2 side cards: {drawn_cards_map[str(p.id)]}")
        except ValueError:
            # Not enough side cards in deck
            drawn_cards_map[str(p.id)] = []
            logger.debug(f"[NEW_ROUND] Player {p.id}: no side cards available in deck")
    game.post_battle_drawn_cards = drawn_cards_map


# ─────────────────── 3-round battle turn management ───────────────────

@games.route('/play_battle_move', methods=['POST'])
@require_token
def play_battle_move():
    """Record a player playing one battle move in the current battle round.

    Expects JSON: {
        game_id, player_id, battle_move_id,
        call_figure_id (optional) — ID of the called figure
    }

    The endpoint:
    1. Validates it's the player's turn in the battle.
    2. Marks the BattleMove.played_round = current battle_round.
    3. Stores call_figure_id if provided.
    4. Switches battle_turn to the other player.
    5. If both have now played in this round, advances to next round
       (turn goes back to invader).
    """
    data = request.json
    game_id = data.get('game_id')
    player_id = data.get('player_id')
    battle_move_id = data.get('battle_move_id')
    call_figure_id = data.get('call_figure_id')

    if not game_id or not player_id or not battle_move_id:
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400

    err = verify_player_ownership(player_id)
    if err:
        return err

    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({'success': False, 'message': 'Game not found'}), 404

    # Verify battle is active (battle_confirmed must be True)
    if not game.battle_confirmed:
        return jsonify({'success': False, 'message': 'Battle is not active'}), 400

    # Verify it's this player's battle turn
    if game.battle_turn_player_id != player_id:
        return jsonify({'success': False,
                        'message': "It is not your turn in the battle"}), 400

    # Look up the battle move
    move = db.session.get(BattleMove, battle_move_id)
    if not move:
        return jsonify({'success': False, 'message': 'Battle move not found'}), 404
    if move.game_id != game_id or move.player_id != player_id:
        return jsonify({'success': False, 'message': 'Move does not belong to this player/game'}), 400
    if move.played_round is not None:
        return jsonify({'success': False, 'message': 'Move has already been played'}), 400

    # Play the move
    move.played_round = game.battle_round
    if call_figure_id:
        move.call_figure_id = call_figure_id
        # Log call figure details for debugging (Bug #4)
        call_fig = db.session.get(Figure, call_figure_id)
        if call_fig:
            logger.info(f"[PLAY_BM] game={game_id} player={player_id} bm_id={battle_move_id} "
                        f"family={move.family_name} suit={move.suit} round={game.battle_round} "
                        f"call_figure_id={call_figure_id} call_fig_name={call_fig.name} call_fig_suit={call_fig.suit}")
        else:
            logger.warning(f"[PLAY_BM] game={game_id} call_figure_id={call_figure_id} NOT FOUND")
    else:
        logger.info(f"[PLAY_BM] game={game_id} player={player_id} bm_id={battle_move_id} "
                    f"family={move.family_name} suit={move.suit} round={game.battle_round} (no call figure)")

    # Remove the card(s) from the player's hand so they can't be
    # accidentally sacrificed / auto-removed while the battle continues.
    # The card stays in the DB (in_deck=True) for post-battle resolution.
    if move.card_type == 'side':
        card = db.session.get(SideCard, move.card_id)
    else:
        card = db.session.get(MainCard, move.card_id)
    if card:
        card.in_deck = True

    # Double Dagger second card
    if move.card_id_b is not None:
        ct_b = move.card_type_b or 'main'
        if ct_b == 'side':
            card_b = db.session.get(SideCard, move.card_id_b)
        else:
            card_b = db.session.get(MainCard, move.card_id_b)
        if card_b:
            card_b.in_deck = True

    # Determine the other player
    other_player = None
    for p in game.players:
        if p.id != player_id:
            other_player = p
            break

    if not other_player:
        return jsonify({'success': False, 'message': 'Opponent not found'}), 500

    # Check if the other player has already played in this round
    other_played = BattleMove.query.filter_by(
        game_id=game_id,
        player_id=other_player.id,
        played_round=game.battle_round,
    ).first()

    if other_played:
        # Both have played this round — advance to next round (if not last)
        if game.battle_round < 2:
            game.battle_round += 1
        # Turn goes back to invader for the next round
        game.battle_turn_player_id = game.invader_player_id
    else:
        # Switch turn to the other player
        game.battle_turn_player_id = other_player.id

    db.session.commit()

    # Log the battle move
    player = db.session.get(Player, player_id)
    user = db.session.get(User, player.user_id) if player else None
    username = user.username if user else f"Player {player_id}"
    log_entry = LogEntry(
        game_id=game_id,
        player_id=player_id,
        round_number=game.current_round,
        turn_number=move.played_round + 1,
        message=f"{username} played {move.family_name} (power {move.value}) in battle round {move.played_round + 1}.",
        author=username,
        type='battle_move'
    )
    db.session.add(log_entry)
    db.session.commit()

    logger.info(f"[BATTLE_MOVE] Player {player_id} played move {battle_move_id} "
          f"in round {move.played_round}. Next turn: {game.battle_turn_player_id}, "
          f"battle_round: {game.battle_round}")

    return jsonify({
        'success': True,
        'battle_round': game.battle_round,
        'battle_turn_player_id': game.battle_turn_player_id,
        'game': game.serialize(),
    })


@games.route('/get_battle_state', methods=['GET'])
def get_battle_state():
    """Return the current 3-round battle state for polling.

    Query params: game_id, player_id

    Returns: battle_round, battle_turn_player_id, all battle moves
    (with played_round showing which are played and where).
    For opponent's unplayed moves, family_name is hidden.
    """
    game_id = request.args.get('game_id', type=int)
    player_id = request.args.get('player_id', type=int)

    if not game_id or not player_id:
        return jsonify({'success': False, 'message': 'Missing game_id or player_id'}), 400

    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({'success': False, 'message': 'Game not found'}), 404

    # Get all battle moves for this game
    all_moves = BattleMove.query.filter_by(game_id=game_id).all()

    player_moves = []
    opponent_moves = []
    for m in all_moves:
        s = m.serialize()
        if m.player_id == player_id:
            player_moves.append(s)
        else:
            if m.played_round is not None:
                # Opponent's played move — reveal it
                opponent_moves.append(s)
            else:
                # Opponent's unplayed move — hide details
                opponent_moves.append({
                    'id': m.id,
                    'player_id': m.player_id,
                    'played_round': None,
                })

    return jsonify({
        'success': True,
        'battle_round': game.battle_round,
        'battle_turn_player_id': game.battle_turn_player_id,
        'invader_player_id': game.invader_player_id,
        'player_moves': player_moves,
        'opponent_moves': opponent_moves,
        'battle_skipped_rounds': game.battle_skipped_rounds or {},
    })


@games.route('/skip_battle_turn', methods=['POST'])
@require_token
def skip_battle_turn():
    """Auto-skip a player's battle turn when they have no moves left.

    Expects JSON: { game_id, player_id }

    Records a skip for the current battle_round and advances the turn/round
    the same way play_battle_move does.
    """
    data = request.json
    game_id = data.get('game_id')
    player_id = data.get('player_id')

    if not game_id or not player_id:
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400

    err = verify_player_ownership(player_id)
    if err:
        return err

    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({'success': False, 'message': 'Game not found'}), 404

    if not game.battle_confirmed:
        return jsonify({'success': False, 'message': 'Battle is not active'}), 400

    if game.battle_turn_player_id != player_id:
        return jsonify({'success': False, 'message': 'It is not your turn in the battle'}), 400

    # Reject skip if the player still has unplayed battle moves
    unplayed_count = BattleMove.query.filter_by(
        game_id=game_id, player_id=player_id, played_round=None
    ).count()
    if unplayed_count > 0:
        return jsonify({
            'success': False,
            'message': 'You must play a battle move — you still have unplayed moves'
        }), 400

    # Record the skip
    skipped = game.battle_skipped_rounds or {}
    pid_key = str(player_id)
    if pid_key not in skipped:
        skipped[pid_key] = []
    if game.battle_round not in skipped[pid_key]:
        skipped[pid_key].append(game.battle_round)
    game.battle_skipped_rounds = skipped
    flag_modified(game, 'battle_skipped_rounds')

    # Determine the other player
    other_player = None
    for p in game.players:
        if p.id != player_id:
            other_player = p
            break

    if not other_player:
        return jsonify({'success': False, 'message': 'Opponent not found'}), 500

    # Check if the other player has already played (or skipped) in this round
    other_played = BattleMove.query.filter_by(
        game_id=game_id,
        player_id=other_player.id,
        played_round=game.battle_round,
    ).first()
    other_skipped = str(other_player.id) in skipped and game.battle_round in skipped[str(other_player.id)]

    if other_played or other_skipped:
        # Both have played/skipped this round — advance to next round
        if game.battle_round < 2:
            game.battle_round += 1
        game.battle_turn_player_id = game.invader_player_id
    else:
        # Switch turn to the other player
        game.battle_turn_player_id = other_player.id

    db.session.commit()

    # Log the battle skip
    player_obj = db.session.get(Player, player_id)
    user = db.session.get(User, player_obj.user_id) if player_obj else None
    username = user.username if user else f"Player {player_id}"
    skip_round = skipped[pid_key][-1]
    log_entry = LogEntry(
        game_id=game_id,
        player_id=player_id,
        round_number=game.current_round,
        turn_number=skip_round + 1,
        message=f"{username} skipped battle round {skip_round + 1} (no moves left).",
        author=username,
        type='battle_skip'
    )
    db.session.add(log_entry)
    db.session.commit()

    logger.info(f"[BATTLE_SKIP] Player {player_id} skipped round {skipped[pid_key][-1]}. "
          f"Next turn: {game.battle_turn_player_id}, battle_round: {game.battle_round}")

    return jsonify({
        'success': True,
        'battle_round': game.battle_round,
        'battle_turn_player_id': game.battle_turn_player_id,
        'battle_skipped_rounds': game.battle_skipped_rounds or {},
        'game': game.serialize(),
    })


@games.route('/finish_battle', methods=['POST'])
@require_token
def finish_battle():
    """Resolve a 3-round battle and return result + returnable cards.

    Expects JSON: {
        game_id, player_id,
        total_diff: int   # (advisory only — server computes its own)
    }

    The endpoint computes the authoritative total_diff server-side from
    figure power (including support, healer, wall, enchantment, distance-
    attack bonuses) and battle-move records.

    1. Validates the game / players / state.
    2. Determines outcome (win / lose / draw).
    3. For win/lose: awards points = loser-figure base power to winner,
       destroys loser figure, collects all battle-move + figure cards.
    4. Returns the list of returnable cards so the winner can pick one.
    5. For draw: returns draw options for the defender.
    """
    data = request.json
    game_id = data.get('game_id')
    player_id = data.get('player_id')
    client_total_diff = data.get('total_diff', 0)  # advisory only

    if not game_id or not player_id:
        return jsonify({'success': False, 'message': 'Missing game_id or player_id'}), 400

    err = verify_player_ownership(player_id)
    if err:
        return err

    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({'success': False, 'message': 'Game not found'}), 404

    player = Player.query.filter_by(id=player_id, game_id=game_id).first()
    if not player:
        return jsonify({'success': False, 'message': 'Player not found'}), 404

    finished_conquer = _serialize_finished_conquer_result(game)
    if finished_conquer:
        return jsonify(finished_conquer)

    other_player = [p for p in game.players if p.id != player_id][0]

    # Idempotency: if battle was already resolved by the other client
    # (figures destroyed, fold_winner_id set), return the cached result.
    adv_figure = db.session.get(Figure, game.advancing_figure_id) if game.advancing_figure_id else None
    def_figure = db.session.get(Figure, game.defending_figure_id) if game.defending_figure_id else None

    if (not adv_figure or not def_figure) and game.fold_winner_id:
        logger.info(f"[FINISH_BATTLE] Battle already resolved for game {game_id} (figure destroyed)")
        winner_id = game.fold_winner_id
        if winner_id == player_id:
            outcome = 'win'
        else:
            outcome = 'lose'

        # For winners, collect returnable cards (all played BM cards + orphaned figure cards)
        returnable_cards = []
        if outcome == 'win':
            bm_cards, _ = _collect_battle_move_cards(game_id)
            orphaned_main = MainCard.query.filter_by(
                game_id=game_id, in_deck=False, part_of_figure=False, player_id=None
            ).all()
            orphaned_side = SideCard.query.filter_by(
                game_id=game_id, in_deck=False, part_of_figure=False, player_id=None
            ).all()
            # Battle move cards first, then orphaned figure cards
            all_cards = bm_cards + [(c, 'main') for c in orphaned_main] + [(c, 'side') for c in orphaned_side]
            returnable_cards = [_serialize_battle_card(c, ct) for c, ct in all_cards]

        other_user = db.session.get(User, other_player.user_id)
        other_name = other_user.username if other_user else f"Player {other_player.id}"
        player_user_inner = db.session.get(User, player.user_id)
        player_name_inner = player_user_inner.username if player_user_inner else f"Player {player_id}"

        saved = game.last_battle_result or {}

        return jsonify({
            'success': True,
            'outcome': outcome,
            'already_resolved': True,
            'winner_player_id': winner_id,
            'winner_name': player_name_inner if outcome == 'win' else other_name,
            'loser_name': other_name if outcome == 'win' else player_name_inner,
            'points_awarded': saved.get('points_awarded', 0),
            'destroyed_figure_name': saved.get('destroyed_figure_name', 'figure'),
            'destroyed_figure_family': saved.get('destroyed_figure_family', ''),
            'returnable_cards': returnable_cards,
            'game': game.serialize(),
        })

    if not adv_figure or not def_figure:
        # Battle already fully resolved by the other client (figures destroyed,
        # fold_winner_id cleared by new-round cleanup).  Return a safe
        # already-resolved response so the second client can show the result.
        saved = game.last_battle_result or {}

        player_user_fb = db.session.get(User, player.user_id)
        player_name_fb = player_user_fb.username if player_user_fb else f"Player {player_id}"
        other_user_fb = db.session.get(User, other_player.user_id)
        other_name_fb = other_user_fb.username if other_user_fb else f"Player {other_player.id}"

        # Use saved result if available, otherwise infer from invader status
        if saved:
            winner_id = saved.get('winner_player_id')
            outcome = 'win' if winner_id == player_id else 'lose'
        elif game.invader_player_id == player_id:
            outcome = 'win'
            winner_id = player_id
        else:
            outcome = 'lose'
            winner_id = game.invader_player_id

        return jsonify({
            'success': True,
            'outcome': outcome,
            'already_resolved': True,
            'winner_player_id': winner_id,
            'winner_name': saved.get('winner_name') or (player_name_fb if outcome == 'win' else other_name_fb),
            'loser_name': saved.get('loser_name') or (other_name_fb if outcome == 'win' else player_name_fb),
            'points_awarded': saved.get('points_awarded', 0),
            'destroyed_figure_name': saved.get('destroyed_figure_name', 'figure'),
            'destroyed_figure_family': saved.get('destroyed_figure_family', ''),
            'returnable_cards': [],
            'game': game.serialize(),
        })

    # Determine who the invader/defender is
    is_invader = (game.invader_player_id == player_id)

    # ── Server-authoritative total_diff ──
    server_diff, breakdown = _compute_server_total_diff(game,
                                                        return_breakdown=True)
    # server_diff > 0 means invader wins; convert to caller's perspective
    total_diff = server_diff if is_invader else -server_diff

    # ── Discrepancy check ──
    # Compare client value with server value (both in caller perspective)
    diff_delta = abs(total_diff - client_total_diff)
    if diff_delta != 0:
        logger.warning(f"[FINISH_BATTLE] ⚠️  DISCREPANCY: player={player_id} "
              f"client_diff={client_total_diff} server_diff(caller)={total_diff} "
              f"delta={diff_delta}  (server is authoritative)")
        logger.warning(f"[FINISH_BATTLE] ⚠️  BREAKDOWN: {breakdown}")
    logger.info(f"[FINISH_BATTLE] player={player_id} is_invader={is_invader} "
          f"client_diff={client_total_diff} server_diff={server_diff} "
          f"used_diff={total_diff}")

    if is_invader:
        player_figure = adv_figure
        opponent_figure = def_figure
        winner_player = player if total_diff > 0 else other_player
        loser_player = other_player if total_diff > 0 else player
        winner_figure = player_figure if total_diff > 0 else opponent_figure
        loser_figure = opponent_figure if total_diff > 0 else player_figure
    else:
        player_figure = def_figure
        opponent_figure = adv_figure
        winner_player = player if total_diff > 0 else other_player
        loser_player = other_player if total_diff > 0 else player
        winner_figure = player_figure if total_diff > 0 else opponent_figure
        loser_figure = opponent_figure if total_diff > 0 else player_figure

    # Get user names
    winner_user = db.session.get(User, winner_player.user_id)
    loser_user = db.session.get(User, loser_player.user_id)
    winner_name = winner_user.username if winner_user else f"Player {winner_player.id}"
    loser_name = loser_user.username if loser_user else f"Player {loser_player.id}"

    player_user = db.session.get(User, player.user_id)
    player_name = player_user.username if player_user else f"Player {player_id}"

    # Return unplayed battle move cards to their owners (only played
    # cards go into the loot / return-to-deck pool)
    _return_unplayed_battle_move_cards(game_id)

    if total_diff == 0:
        # ──── DRAW ────

        # Conquer mode draw: no consequences — game ends cleanly
        if game.mode == 'conquer':
            _return_unplayed_battle_move_cards(game_id)
            _delete_all_battle_moves(game_id)
            _deactivate_all_spells(game)
            _clear_battle_state(game)
            game.state = 'finished'
            game.finished_at = _utcnow()
            # No winner — draw
            game.winner_player_id = None

            # Consume the attacker's single-use cards (battle moves,
            # modifiers, spells) and return their figure cards.  The defender's
            # active defence remains in place because the land did not fall.
            draw_consumed_cards = []
            atk_cfg = (db.session.get(LandConfig, game.conquer_config_id)
                       if game.conquer_config_id else None)

            if atk_cfg:
                draw_consumed_cards = _snapshot_config_battle_cards(atk_cfg)
                _consume_config_battle_cards(atk_cfg)
                _wipe_land_config(atk_cfg)

            log_entry = LogEntry(
                game_id=game.id,
                player_id=player_id,
                round_number=game.current_round,
                turn_number=player.turns_left,
                message="Conquer battle ended in a draw — no consequences.",
                author="System",
                type='battle_draw'
            )
            db.session.add(log_entry)
            db.session.commit()

            return jsonify({
                'success': True,
                'outcome': 'draw',
                'conquer_result': 'draw',
                'attacker_won': False,
                'land_id': game.land_id,
                'message': 'Conquer battle ended in a draw — no consequences.',
                'consumed_cards': draw_consumed_cards,
                'loot_lost_cards': [],
                'game': game.serialize(),
            })

        # Collect remaining (played) battle move cards from BOTH players
        bm_cards, bm_records = _collect_battle_move_cards(game_id)
        # Defender gets to choose: destroy opponent figure, 10 pts, or pick a card
        # Determine who the defender is
        defender_player_id = None
        for p in game.players:
            if p.id != game.invader_player_id:
                defender_player_id = p.id
                break

        # Persist unplayed-card returns before responding
        db.session.commit()

        # Serialize the played battle move cards so the client can show them
        returnable_cards = [_serialize_battle_card(c, ct) for c, ct in bm_cards]

        return jsonify({
            'success': True,
            'outcome': 'draw',
            'total_diff': 0,
            'defender_player_id': defender_player_id,
            'returnable_cards': returnable_cards,
            'game': game.serialize(),
        })

    else:
        # ──── WIN / LOSE ────
        # Collect played battle move cards from BOTH players.
        # All played BM cards go into the loot pool (winner picks 1,
        # rest go to deck).  Winner's figure stays; loser's is destroyed.
        bm_cards, bm_records = _collect_battle_move_cards(game_id)

        points_awarded = _compute_figure_base_power(loser_figure)

        # Civil War: determine loser's second figure and add its power too
        loser_figure_2 = None
        if is_invader:
            # loser is defender → loser_figure_2 is defending_figure_id_2
            loser_fig_2_id = game.defending_figure_id_2 if total_diff > 0 else game.advancing_figure_id_2
        else:
            # loser is invader → loser_figure_2 is advancing_figure_id_2
            loser_fig_2_id = game.advancing_figure_id_2 if total_diff > 0 else game.defending_figure_id_2
        if loser_fig_2_id:
            loser_figure_2 = db.session.get(Figure, loser_fig_2_id)
        if loser_figure_2:
            points_awarded += _compute_figure_base_power(loser_figure_2)

        winner_player.points += points_awarded

        # Check checkmate BEFORE destroying the figure (record is deleted after)
        checkmate_game_over = _check_checkmate_loss(game, loser_figure)
        if not checkmate_game_over and loser_figure_2:
            checkmate_game_over = _check_checkmate_loss(game, loser_figure_2)

        # Destroy loser's figure — collect its cards
        figure_cards = _destroy_figure_and_collect_cards(loser_figure)

        # Destroy loser's second CW figure if present
        if loser_figure_2:
            figure_cards += _destroy_figure_and_collect_cards(loser_figure_2)

        # Build destroyed figure description (may include second figure)
        destroyed_name = loser_figure.name
        destroyed_family = loser_figure.family_name
        if loser_figure_2:
            destroyed_name += f" & {loser_figure_2.name}"
            destroyed_family += f" & {loser_figure_2.family_name}"

        # Clear the destroyed figure's reference on the game
        if game.advancing_figure_id and loser_figure.id == game.advancing_figure_id:
            game.advancing_figure_id = None
        if game.defending_figure_id and loser_figure.id == game.defending_figure_id:
            game.defending_figure_id = None
        # Clear second figure references for the loser
        if loser_figure_2:
            if game.advancing_figure_id_2 and loser_figure_2.id == game.advancing_figure_id_2:
                game.advancing_figure_id_2 = None
            if game.defending_figure_id_2 and loser_figure_2.id == game.defending_figure_id_2:
                game.defending_figure_id_2 = None

        db.session.flush()

        # Returnable cards = all played battle move cards (both players)
        # + destroyed loser figure cards.  BM cards listed first.
        all_returnable = bm_cards + figure_cards
        returnable_cards = [_serialize_battle_card(c, ct) for c, ct in all_returnable]

        # Log
        log_entry = LogEntry(
            game_id=game.id,
            player_id=winner_player.id,
            round_number=game.current_round,
            turn_number=winner_player.turns_left,
            message=(
                f"{winner_name} wins the battle! {loser_name}'s "
                f"{destroyed_name} is destroyed. "
                f"{winner_name} earns {points_awarded} points."
            ),
            author="System",
            type='battle_win'
        )
        db.session.add(log_entry)

        # Store the winner so the second client can retrieve the result
        game.fold_winner_id = winner_player.id

        # Persist battle result for the second client (survives _clear_battle_state)
        game.last_battle_result = {
            'winner_player_id': winner_player.id,
            'loser_player_id': loser_player.id,
            'winner_name': winner_name,
            'loser_name': loser_name,
            'points_awarded': points_awarded,
            'destroyed_figure_name': destroyed_name,
            'destroyed_figure_family': destroyed_family,
            'checkmate_figure_name': checkmate_game_over.get('checkmate_figure_name') if checkmate_game_over else None,
        }

        # Check if someone reached the stake (will be finalized in pick_card)
        game_over_info = None
        if checkmate_game_over:
            game_over_info = True  # Checkmate overrides — game ends at pick_card
        else:
            for p in game.players:
                if p.points >= (game.stake or settings.DEFAULT_GAME_STAKE):
                    game_over_info = True
                    break

        # Pre-compute game stats if game is ending (so the polling client
        # can display them without a separate request)
        if game_over_info:
            game.last_battle_result['game_stats'] = _compute_game_stats(
                game.id, [winner_player.id, loser_player.id])

        db.session.commit()

        response = {
            'success': True,
            'outcome': 'win',
            'winner_player_id': winner_player.id,
            'loser_player_id': loser_player.id,
            'winner_name': winner_name,
            'loser_name': loser_name,
            'points_awarded': points_awarded,
            'destroyed_figure_name': destroyed_name,
            'destroyed_figure_family': destroyed_family,
            'total_diff': total_diff,
            'returnable_cards': returnable_cards,
            'game': game.serialize(),
        }
        if game_over_info:
            response['game_over_pending'] = True
        return jsonify(response)


def _resolve_conquer_battle(game, winner, requesting_player):
    """Resolve a conquer battle after the single battle round.

    Handles land ownership transfer, card consumption, card rewards,
    and attack log.  Returns a JSON-serialisable dict for the response.
    """
    import random as _random
    import server_settings as _cfg

    atk_player = db.session.get(Player, game.invader_player_id)
    def_player = [p for p in game.players if p.id != atk_player.id][0]

    attacker_won = (winner.id == atk_player.id)
    attacker_user = db.session.get(User, atk_player.user_id)
    defender_user = db.session.get(User, def_player.user_id)
    land = db.session.get(Land, game.land_id)
    is_ai_land = defender_user and defender_user.is_ai

    saved = game.last_battle_result or {}

    # Mark game as finished
    game.state = 'finished'
    game.winner_player_id = winner.id
    game.finished_at = _utcnow()

    # Snapshot all cards committed to this attack before any consumption.
    all_attack_cards = []
    if game.conquer_config_id:
        atk_cfg_cards = db.session.get(LandConfig, game.conquer_config_id)
        if atk_cfg_cards:
            attack_card_ids = []
            for fig in atk_cfg_cards.figures:
                if fig.card_ids:
                    attack_card_ids.extend(fig.card_ids)
            attack_card_ids.extend(_config_battle_card_ids(atk_cfg_cards))
            all_attack_cards = _snapshot_collection_cards(attack_card_ids, include_id=True)

    # ── Consume attacker's conquer config battle-move cards ──
    if game.conquer_config_id:
        atk_cfg = db.session.get(LandConfig, game.conquer_config_id)
        if atk_cfg:
            _consume_config_battle_cards(atk_cfg)

    # ── Card reward / penalty ──
    card_won_suit = None
    card_won_rank = None
    card_lost_suit = None
    card_lost_rank = None
    looted_lost_cards = []
    defence_consumed_cards = []

    if attacker_won:
        # ── Attacker wins: gets a card from the defender ──
        if is_ai_land and land:
            # AI land: create a new CollectionCard from the template
            templates = _cfg.AI_DEFENCE_TEMPLATES.get(land.tier, [])
            tpl_idx = land.ai_template_index or 0
            tpl = templates[tpl_idx] if tpl_idx < len(templates) else (
                templates[0] if templates else None)
            if tpl:
                # Collect all template cards
                all_cards = []
                for fig in tpl.get('figures', []):
                    all_cards.extend(fig.get('cards', []))
                if all_cards:
                    picked = _random.choice(all_cards)
                    rank_values = {'A': 3, 'K': 4, 'Q': 2, 'J': 1,
                                   '10': 10, '9': 9, '8': 8, '7': 7,
                                   '6': 6, '5': 5, '4': 4, '3': 3, '2': 2}
                    new_cc = CollectionCard(
                        user_id=attacker_user.id,
                        suit=picked['suit'],
                        rank=picked['rank'],
                        value=rank_values.get(picked['rank'], 0),
                        locked=False,
                    )
                    db.session.add(new_cc)
                    card_won_suit = picked['suit']
                    card_won_rank = picked['rank']
        else:
            # Player land: take a random key card from defender's config
            if game.defence_config_id:
                def_cfg = db.session.get(LandConfig, game.defence_config_id)
                if def_cfg:
                    key_cards = []
                    for fig in def_cfg.figures:
                        if fig.card_ids and fig.card_roles:
                            for cid, role in zip(fig.card_ids, fig.card_roles):
                                if role == 'key':
                                    key_cards.append(cid)
                    if key_cards:
                        chosen_id = _random.choice(key_cards)
                        cc = db.session.get(CollectionCard, chosen_id)
                        if cc:
                            card_won_suit = cc.suit
                            card_won_rank = cc.rank
                            # Transfer to attacker
                            cc.user_id = attacker_user.id
                            cc.locked = False
                            cc.lock_type = None
                            cc.lock_ref_id = None

        # Transfer land ownership
        if land:
            land.owner_user_id = attacker_user.id
            land.owned_since = _utcnow()
            protect_seconds = max(int(getattr(_cfg, 'LAND_CONQUER_PROTECTION_SECONDS', 0)), 0)
            if protect_seconds > 0:
                land.conquer_cooldown_until = _utcnow() + timedelta(seconds=protect_seconds)
            else:
                land.conquer_cooldown_until = None

        # Convert attacker's conquer config to defence config.
        # Battle/modifier/spell cards have already been consumed above,
        # so only figure cards remain locked — re-key their lock_type so
        # subsequent defence-side cleanup recognises them.
        if game.conquer_config_id:
            atk_cfg = db.session.get(LandConfig, game.conquer_config_id)
            if atk_cfg:
                atk_cfg.config_type = 'defence'
                atk_cfg.land_id = game.land_id
                _rekey_config_lock_types(atk_cfg, 'defence')
                if land:
                    land.defence_config_id = atk_cfg.id

        # The old defender's battle moves and spells are one-shot, but only
        # finally consumed when the land falls.  Figure cards are handled by
        # loot/unlock rules inside `_wipe_land_config`.
        if game.defence_config_id:
            def_cfg = db.session.get(LandConfig, game.defence_config_id)
            if def_cfg:
                defence_consumed_cards = _snapshot_config_battle_cards(def_cfg)
                _consume_config_battle_cards(def_cfg)
                _wipe_land_config(def_cfg)
        if defender_user and not is_ai_land:
            _wipe_defence_drafts_for_lost_land(defender_user.id, game.land_id)

    else:
        # ── Defender wins: attacker loses a key card ──
        if game.conquer_config_id:
            atk_cfg = db.session.get(LandConfig, game.conquer_config_id)
            if atk_cfg:
                key_cards = []
                for fig in atk_cfg.figures:
                    if fig.card_ids and fig.card_roles:
                        for cid, role in zip(fig.card_ids, fig.card_roles):
                            if role == 'key':
                                key_cards.append(cid)
                if key_cards:
                    chosen_id = _random.choice(key_cards)
                    cc = db.session.get(CollectionCard, chosen_id)
                    if cc:
                        card_lost_suit = cc.suit
                        card_lost_rank = cc.rank
                        looted_lost_cards = [{'id': cc.id, 'suit': cc.suit, 'rank': cc.rank}]
                        if is_ai_land:
                            # AI defender: just delete the card
                            db.session.delete(cc)
                        else:
                            # Player defender: transfer to defender
                            cc.user_id = defender_user.id
                            cc.locked = False
                            cc.lock_type = None
                            cc.lock_ref_id = None

                # Consume the entire attacker config: every remaining card
                # (figures, plus any spell/modifier cards not already deleted
                # in `_consume_config_battle_cards` if a future code-path
                # changes ordering) is destroyed, and the cfg row removed.
                protected_ids = [c['id'] for c in looted_lost_cards if c.get('id')]
                _destroy_land_config(atk_cfg, exclude_card_ids=protected_ids)

    looted_ids = {c['id'] for c in looted_lost_cards if c.get('id')}
    consumed_cards = [
        {'suit': c['suit'], 'rank': c['rank']}
        for c in all_attack_cards
        if c.get('id') not in looted_ids
    ]
    looted_lost_cards = [
        {'suit': c['suit'], 'rank': c['rank']}
        for c in looted_lost_cards
    ]

    # Create attack log
    log = LandAttackLog(
        land_id=game.land_id,
        attacker_user_id=attacker_user.id,
        defender_user_id=defender_user.id if defender_user and not is_ai_land else None,
        result='attacker_won' if attacker_won else 'defender_won',
        card_won_suit=card_won_suit,
        card_won_rank=card_won_rank,
        card_lost_suit=card_lost_suit,
        card_lost_rank=card_lost_rank,
    )
    db.session.add(log)

    result = 'attacker_won' if attacker_won else 'defender_won'
    logger.info(f"[CONQUER_RESOLVE] game={game.id} land={game.land_id} "
                f"result={result}")

    # For failed attacks, all committed cards are either consumed or looted.
    cards_spent = 0 if attacker_won else (len(consumed_cards) + len(looted_lost_cards))

    merged_last_result = dict(saved) if isinstance(saved, dict) else {}
    merged_last_result.update({
        'conquer_consumed_cards': consumed_cards,
        'defence_consumed_cards': defence_consumed_cards,
        'conquer_loot_lost_cards': looted_lost_cards,
        'cards_spent': cards_spent,
        'card_lost_suit': card_lost_suit,
        'card_lost_rank': card_lost_rank,
        'card_won_suit': card_won_suit,
        'card_won_rank': card_won_rank,
    })
    game.last_battle_result = merged_last_result

    return {
        'success': True,
        'message': f'Conquer battle resolved: {result}',
        'conquer_result': result,
        'attacker_won': attacker_won,
        'land_id': game.land_id,
        'land_gold_rate': land.gold_rate if land else 0,
        'land_tier': land.tier if land else None,
        'points_awarded': saved.get('points_awarded', 0),
        'destroyed_figure_name': saved.get('destroyed_figure_name', ''),
        'card_won_suit': card_won_suit,
        'card_won_rank': card_won_rank,
        'card_lost_suit': card_lost_suit,
        'card_lost_rank': card_lost_rank,
        'loot_lost_cards': looted_lost_cards,
        'consumed_cards': consumed_cards,
        'defence_consumed_cards': defence_consumed_cards,
        'cards_spent': cards_spent,
        'game': game.serialize(),
    }


def _serialize_finished_conquer_result(game):
    """Return a stable conquer_result payload for an already-finished conquer game."""
    if not game or game.mode != 'conquer' or game.state != 'finished':
        return None

    land = db.session.get(Land, game.land_id) if game.land_id else None
    invader_id = game.invader_player_id

    if game.winner_player_id is None:
        conquer_result = 'draw'
        attacker_won = False
    else:
        attacker_won = (game.winner_player_id == invader_id)
        conquer_result = 'attacker_won' if attacker_won else 'defender_won'

    payload = {
        'success': True,
        'message': f'Conquer battle already resolved: {conquer_result}',
        'already_resolved': True,
        'conquer_result': conquer_result,
        'attacker_won': attacker_won,
        'land_id': game.land_id,
        'land_gold_rate': land.gold_rate if land else 0,
        'land_tier': land.tier if land else None,
        'game': game.serialize(),
    }

    if conquer_result == 'draw':
        payload['outcome'] = 'draw'
        return payload

    payload['outcome'] = 'win'
    payload['winner_player_id'] = game.winner_player_id

    defender_player_id = None
    for p in game.players:
        if p.id != invader_id:
            defender_player_id = p.id
            break

    payload['loser_player_id'] = defender_player_id if attacker_won else invader_id

    # Pull card transfer details from the latest attack log when available.
    if game.land_id:
        latest_log = LandAttackLog.query.filter_by(
            land_id=game.land_id
        ).order_by(LandAttackLog.id.desc()).first()
        if latest_log:
            payload['card_won_suit'] = latest_log.card_won_suit
            payload['card_won_rank'] = latest_log.card_won_rank
            payload['card_lost_suit'] = latest_log.card_lost_suit
            payload['card_lost_rank'] = latest_log.card_lost_rank

    last_result = game.last_battle_result if isinstance(game.last_battle_result, dict) else {}
    if 'cards_spent' in last_result:
        payload['cards_spent'] = last_result.get('cards_spent')
    if 'conquer_consumed_cards' in last_result:
        payload['consumed_cards'] = last_result.get('conquer_consumed_cards') or []
    if 'defence_consumed_cards' in last_result:
        payload['defence_consumed_cards'] = last_result.get('defence_consumed_cards') or []
    if 'conquer_loot_lost_cards' in last_result:
        payload['loot_lost_cards'] = last_result.get('conquer_loot_lost_cards') or []

    return payload


def _config_battle_card_ids(cfg):
    """Return battle-move/modifier/spell card IDs referenced by a land config."""
    if not cfg:
        return []
    card_ids = []
    for move in cfg.battle_moves:
        if move.card_id:
            card_ids.append(move.card_id)
    for arr in (cfg.modifier_card_ids, cfg.spell_card_ids,
                cfg.prelude_spell_card_ids, cfg.counter_spell_card_ids):
        if arr:
            card_ids.extend(arr)
    return card_ids


def _snapshot_collection_cards(card_ids, include_id=False):
    """Snapshot suit/rank for collection cards, preserving input order."""
    unique_ids = []
    seen_ids = set()
    for cid in card_ids or []:
        if not cid or cid in seen_ids:
            continue
        seen_ids.add(cid)
        unique_ids.append(cid)
    if not unique_ids:
        return []

    cards = CollectionCard.query.filter(CollectionCard.id.in_(unique_ids)).all()
    cards_by_id = {card.id: card for card in cards}
    snapshot = []
    for cid in unique_ids:
        card = cards_by_id.get(cid)
        if not card:
            continue
        data = {'suit': card.suit, 'rank': card.rank}
        if include_id:
            data['id'] = card.id
        snapshot.append(data)
    return snapshot


def _snapshot_config_battle_cards(cfg, include_id=False):
    """Snapshot cards that are spent when a config's battle/spell package is consumed."""
    return _snapshot_collection_cards(
        _config_battle_card_ids(cfg),
        include_id=include_id,
    )


def _consume_config_battle_cards(cfg):
    """Delete collection cards used for battle moves, modifiers, and spells.

    Spell cards (main, prelude, counter) are one-shot: they are consumed
    together with battle move and modifier cards.  Stale references on the
    config are cleared so the row can either be re-purposed or deleted
    safely afterwards.
    """
    from models import CollectionCard, LandConfigBattleMove

    moves = LandConfigBattleMove.query.filter_by(config_id=cfg.id).all()
    card_ids = _config_battle_card_ids(cfg)

    if card_ids:
        CollectionCard.query.filter(
            CollectionCard.id.in_(card_ids)
        ).delete(synchronize_session='fetch')

    # Delete the move records
    for m in moves:
        db.session.delete(m)

    # Clear stale references so the cfg cannot accidentally be reused
    cfg.modifier_card_ids = []
    cfg.spell_card_ids = []
    cfg.prelude_spell_card_ids = []
    cfg.counter_spell_card_ids = []
    cfg.spell_name = None
    cfg.spell_target_figure_id = None
    cfg.prelude_spell_name = None
    cfg.prelude_spell_data = None
    cfg.counter_spell_name = None
    cfg.counter_spell_data = None
    cfg.counter_spell_target_figure_id = None


def _consume_config_figure_cards(cfg, exclude_card_ids=None):
    """Delete collection cards used for figures in a config (loser's figures consumed)."""
    from models import CollectionCard, LandConfigFigure

    excluded = set(exclude_card_ids or [])
    figures = LandConfigFigure.query.filter_by(config_id=cfg.id).all()
    card_ids = []
    for fig in figures:
        if fig.card_ids:
            card_ids.extend(cid for cid in fig.card_ids if cid not in excluded)

    if card_ids:
        CollectionCard.query.filter(
            CollectionCard.id.in_(card_ids)
        ).delete(synchronize_session='fetch')

    # Delete the figure records
    for fig in figures:
        db.session.delete(fig)


def _wipe_land_config(cfg):
    """Delete a land config and all its figures, moves, and unlock cards."""
    from models import CollectionCard, LandConfigFigure, LandConfigBattleMove

    # Collect all card IDs to unlock
    card_ids = []
    for fig in cfg.figures:
        if fig.card_ids:
            card_ids.extend(fig.card_ids)
    for move in cfg.battle_moves:
        if move.card_id:
            card_ids.append(move.card_id)
    if cfg.modifier_card_ids:
        card_ids.extend(cfg.modifier_card_ids)
    if cfg.spell_card_ids:
        card_ids.extend(cfg.spell_card_ids)
    if cfg.prelude_spell_card_ids:
        card_ids.extend(cfg.prelude_spell_card_ids)
    if cfg.counter_spell_card_ids:
        card_ids.extend(cfg.counter_spell_card_ids)

    # Unlock all cards
    if card_ids:
        CollectionCard.query.filter(
            CollectionCard.id.in_(card_ids)
        ).update({
            CollectionCard.locked: False,
            CollectionCard.lock_type: None,
            CollectionCard.lock_ref_id: None,
        }, synchronize_session='fetch')

    # Delete figures and moves
    LandConfigBattleMove.query.filter_by(config_id=cfg.id).delete()
    LandConfigFigure.query.filter_by(config_id=cfg.id).delete()
    db.session.delete(cfg)


def _wipe_defence_drafts_for_lost_land(user_id, land_id):
    """Delete editable defence drafts for a land that changed owner."""
    if not user_id or not land_id:
        return
    drafts = LandConfig.query.filter_by(
        user_id=user_id,
        land_id=land_id,
        config_type='defence',
        status='draft',
    ).all()
    for draft in drafts:
        _wipe_land_config(draft)


def _destroy_land_config(cfg, exclude_card_ids=None):
    """Delete a land config and DELETE every collection card it referenced.

    Used when an attacker loses: all cards committed to the attack are
    consumed.  `exclude_card_ids` lets the caller protect cards that have
    already been transferred elsewhere (e.g. looted by the defender).
    """
    from models import CollectionCard, LandConfigFigure, LandConfigBattleMove

    excluded = set(exclude_card_ids or [])
    card_ids = []
    for fig in cfg.figures:
        if fig.card_ids:
            card_ids.extend(cid for cid in fig.card_ids if cid not in excluded)
    for move in cfg.battle_moves:
        if move.card_id and move.card_id not in excluded:
            card_ids.append(move.card_id)
    for arr in (cfg.modifier_card_ids, cfg.spell_card_ids,
                cfg.prelude_spell_card_ids, cfg.counter_spell_card_ids):
        if arr:
            card_ids.extend(cid for cid in arr if cid not in excluded)

    if card_ids:
        CollectionCard.query.filter(
            CollectionCard.id.in_(card_ids)
        ).delete(synchronize_session='fetch')

    LandConfigBattleMove.query.filter_by(config_id=cfg.id).delete()
    LandConfigFigure.query.filter_by(config_id=cfg.id).delete()
    db.session.delete(cfg)


def _rekey_config_lock_types(cfg, new_config_type):
    """Re-key the lock_type of every CollectionCard locked by this config.

    Used when a winning attacker's conquer config is converted into the
    new defence config: every 'conquer_*' lock_type must become 'defence_*'
    so subsequent unlock/wipe logic recognises them.
    """
    from models import CollectionCard

    mapping = {
        'conquer_figure':   f'{new_config_type}_figure',
        'conquer_move':     f'{new_config_type}_move',
        'conquer_modifier': f'{new_config_type}_modifier',
        'conquer_spell':    f'{new_config_type}_spell',
        'conquer_prelude':  f'{new_config_type}_prelude',
        'conquer_counter':  f'{new_config_type}_counter',
    }

    # Gather every card id that is part of this cfg (figures only at this
    # point — battle/modifier/spell cards have already been consumed).
    card_ids = []
    for fig in cfg.figures:
        if fig.card_ids:
            card_ids.extend(fig.card_ids)
    if not card_ids:
        return

    cards = CollectionCard.query.filter(
        CollectionCard.id.in_(card_ids)
    ).all()
    for cc in cards:
        new_lt = mapping.get(cc.lock_type)
        if new_lt:
            cc.lock_type = new_lt


@games.route('/finish_battle_pick_card', methods=['POST'])
@require_token
def finish_battle_pick_card():
    """Winner picks one card from the returnable pool, rest go to deck.

    Expects JSON: {
        game_id, player_id,
        picked_card_id: int | null,    # ID of the chosen card (null = skip)
        picked_card_type: 'main'|'side'
    }

    This also triggers the full post-battle cleanup.
    """
    data = request.json
    game_id = data.get('game_id')
    player_id = data.get('player_id')
    picked_card_id = data.get('picked_card_id')
    picked_card_type = data.get('picked_card_type', 'main')

    if not game_id or not player_id:
        return jsonify({'success': False, 'message': 'Missing game_id or player_id'}), 400

    err = verify_player_ownership(player_id)
    if err:
        return err

    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({'success': False, 'message': 'Game not found'}), 404

    player = Player.query.filter_by(id=player_id, game_id=game_id).first()
    if not player:
        return jsonify({'success': False, 'message': 'Player not found'}), 404

    # Idempotency: if battle state was already cleaned up, just return success
    if not game.advancing_figure_id and not game.defending_figure_id and not game.battle_confirmed:
        finished_conquer = _serialize_finished_conquer_result(game)
        if finished_conquer:
            return jsonify(finished_conquer)
        logger.debug(f"[FINISH_BATTLE_PICK] Already cleaned up for game {game_id}, returning success")
        return jsonify({
            'success': True,
            'message': 'Battle already resolved.',
            'game': game.serialize(),
        })

    # Return unplayed battle move cards to their owners (safety — normally
    # already done in finish_battle, but handles reconnect edge cases)
    _return_unplayed_battle_move_cards(game_id)

    # Collect remaining played battle move cards (from both players)
    bm_cards, bm_records = _collect_battle_move_cards(game_id)

    # If winner picked a card, give it to them
    picked_card_info = None
    if picked_card_id:
        if picked_card_type == 'side':
            picked = db.session.get(SideCard, picked_card_id)
        else:
            picked = db.session.get(MainCard, picked_card_id)
        if picked and picked.game_id == game_id:
            picked_card_info = {
                'suit': picked.suit.value,
                'rank': picked.rank.value,
                'card_type': picked_card_type,
            }
            picked.player_id = player_id
            picked.in_deck = False
            picked.part_of_figure = False
            picked.part_of_battle_move = False

    # Store picked card info in last_battle_result BEFORE any db.session.commit()
    # calls (return_cards_to_deck commits internally, which would lose uncommitted
    # JSON column changes due to SQLAlchemy's plain db.JSON not tracking mutations).
    logger.debug(f"[PICK_CARD] picked_card_info={picked_card_info}, last_battle_result exists={game.last_battle_result is not None}")
    if picked_card_info:
        result_dict = dict(game.last_battle_result) if game.last_battle_result else {}
        result_dict['picked_card'] = picked_card_info
        game.last_battle_result = result_dict
        flag_modified(game, 'last_battle_result')
        logger.debug(f"[PICK_CARD] Stored picked_card in last_battle_result: {picked_card_info}")
    else:
        logger.debug(f"[PICK_CARD] No card picked (winner skipped or no cards)")

    # Return remaining battle-move cards to deck
    main_to_deck = []
    side_to_deck = []
    for card, ct in bm_cards:
        if picked_card_id and card.id == picked_card_id:
            continue  # already assigned to winner
        card.part_of_battle_move = False
        if isinstance(card, MainCard):
            main_to_deck.append(card)
        elif isinstance(card, SideCard):
            side_to_deck.append(card)

    # Also return any remaining figure cards that are orphaned
    # (figure was already destroyed in finish_battle, but cards may still
    #  be floating with part_of_figure=False and no player_id)
    orphaned_main = MainCard.query.filter_by(
        game_id=game_id, in_deck=False, part_of_figure=False, player_id=None
    ).all()
    orphaned_side = SideCard.query.filter_by(
        game_id=game_id, in_deck=False, part_of_figure=False, player_id=None
    ).all()
    for c in orphaned_main:
        if picked_card_id and c.id == picked_card_id:
            continue
        main_to_deck.append(c)
    for c in orphaned_side:
        if picked_card_id and c.id == picked_card_id:
            continue
        side_to_deck.append(c)

    if main_to_deck:
        DeckManager.return_cards_to_deck(main_to_deck)
    if side_to_deck:
        DeckManager.return_cards_to_deck(side_to_deck)

    # Delete all battle move records
    _delete_all_battle_moves(game_id)

    # Deactivate all spells
    _deactivate_all_spells(game)

    # Read the actual winner BEFORE _clear_battle_state clears fold_winner_id
    winner_id = game.fold_winner_id
    winner = db.session.get(Player, winner_id) if winner_id else player
    if not winner or winner.game_id != game_id:
        winner = player  # fallback

    # Collect resting figure IDs BEFORE clearing battle state
    resting_ids = _collect_resting_figure_ids(game)

    # Clear battle state (this resets fold_winner_id to None)
    _clear_battle_state(game)

    # ── Conquer mode: always resolves after one battle ──
    if game.mode == 'conquer':
        conquer_result = _resolve_conquer_battle(game, winner, player)
        db.session.commit()
        return jsonify(conquer_result)

    # ── Check game-over condition before starting a new round ──
    game_over_info = _check_game_over(game)
    if not game_over_info and game.state == 'finished':
        # Game was already ended by checkmate during finish_battle
        game_over_info = _build_game_over_info_from_finished(game)
    if game_over_info:
        db.session.commit()
        return jsonify({
            'success': True,
            'message': 'Game over!',
            'game_over': game_over_info,
            'game': game.serialize(),
        })

    # Start a new round — battle winner becomes invader
    _start_new_round(game, winner)

    # Set resting figures for the new round (server-side — figures with rest_after_attack)
    if resting_ids:
        game.resting_figure_ids = resting_ids

    db.session.commit()
    logger.info(f"[FINISH_BATTLE] Card picked. Post-battle cleanup done. Round {game.current_round} starts. Winner/invader={winner.id}")

    return jsonify({
        'success': True,
        'message': 'Battle resolved. New round started.',
        'game': game.serialize(),
    })


@games.route('/finish_battle_draw', methods=['POST'])
@require_token
def finish_battle_draw():
    """Handle the defender's choice after a draw.

    Expects JSON: {
        game_id, player_id,   (must be the defender)
        choice: 'destroy' | 'points' | 'pick_card',
        picked_card_id: int | null,      (only if choice == 'pick_card')
        picked_card_type: 'main'|'side'  (only if choice == 'pick_card')
    }
    """
    data = request.json
    game_id = data.get('game_id')
    player_id = data.get('player_id')
    choice = data.get('choice')
    picked_card_id = data.get('picked_card_id')
    picked_card_type = data.get('picked_card_type', 'main')

    if not game_id or not player_id or not choice:
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400

    err = verify_player_ownership(player_id)
    if err:
        return err

    game = db.session.get(Game, game_id)
    if not game:
        return jsonify({'success': False, 'message': 'Game not found'}), 404

    player = Player.query.filter_by(id=player_id, game_id=game_id).first()
    if not player:
        return jsonify({'success': False, 'message': 'Player not found'}), 404

    other_player = [p for p in game.players if p.id != player_id][0]

    player_user = db.session.get(User, player.user_id)
    other_user = db.session.get(User, other_player.user_id)
    player_name = player_user.username if player_user else f"Player {player_id}"
    other_name = other_user.username if other_user else f"Player {other_player.id}"

    # Determine opponent's figure (the invader's figure, since player is defender)
    opponent_figure = db.session.get(Figure, game.advancing_figure_id) if game.advancing_figure_id else None
    opponent_figure_2 = db.session.get(Figure, game.advancing_figure_id_2) if game.advancing_figure_id_2 else None

    result_msg = ""

    if choice == 'destroy':
        # Destroy the opponent's battle figure(s)
        destroyed_names = []
        checkmate_game_over = None
        if opponent_figure:
            destroyed_names.append(opponent_figure.name)
            # Check checkmate BEFORE destroying
            if not checkmate_game_over:
                checkmate_game_over = _check_checkmate_loss(game, opponent_figure)
            figure_cards = _destroy_figure_and_collect_cards(opponent_figure)
            # Return figure cards to deck
            main_fc = [c for c, ct in figure_cards if isinstance(c, MainCard)]
            side_fc = [c for c, ct in figure_cards if isinstance(c, SideCard)]
            if main_fc:
                DeckManager.return_cards_to_deck(main_fc)
            if side_fc:
                DeckManager.return_cards_to_deck(side_fc)
            game.advancing_figure_id = None
        if opponent_figure_2:
            destroyed_names.append(opponent_figure_2.name)
            # Check checkmate BEFORE destroying
            if not checkmate_game_over:
                checkmate_game_over = _check_checkmate_loss(game, opponent_figure_2)
            figure_cards_2 = _destroy_figure_and_collect_cards(opponent_figure_2)
            main_fc2 = [c for c, ct in figure_cards_2 if isinstance(c, MainCard)]
            side_fc2 = [c for c, ct in figure_cards_2 if isinstance(c, SideCard)]
            if main_fc2:
                DeckManager.return_cards_to_deck(main_fc2)
            if side_fc2:
                DeckManager.return_cards_to_deck(side_fc2)
            game.advancing_figure_id_2 = None
        if destroyed_names:
            fig_names = " & ".join(destroyed_names)
            result_msg = f"{player_name} chose to destroy {other_name}'s {fig_names}!"
        else:
            result_msg = f"Draw — no figure to destroy."

    elif choice == 'points':
        # Award 10 points to the defender
        player.points += 10
        result_msg = f"{player_name} chose 10 points from the draw."

    elif choice == 'pick_card':
        # Pick one card from the battle move cards
        if picked_card_id:
            if picked_card_type == 'side':
                picked = db.session.get(SideCard, picked_card_id)
            else:
                picked = db.session.get(MainCard, picked_card_id)
            if picked and picked.game_id == game_id:
                picked.player_id = player_id
                picked.in_deck = False
                picked.part_of_figure = False
                picked.part_of_battle_move = False
                result_msg = f"{player_name} picked a card from the battle."
        if not result_msg:
            result_msg = f"{player_name} chose to pick a card but none was selected."

    else:
        return jsonify({'success': False, 'message': f'Invalid choice: {choice}'}), 400

    # Return unplayed battle move cards to their owners (safety)
    _return_unplayed_battle_move_cards(game_id)

    # Return remaining played battle-move cards to deck
    bm_cards, bm_records = _collect_battle_move_cards(game_id)
    main_to_deck = []
    side_to_deck = []
    for card, ct in bm_cards:
        if choice == 'pick_card' and picked_card_id and card.id == picked_card_id:
            continue
        card.part_of_battle_move = False
        if isinstance(card, MainCard):
            main_to_deck.append(card)
        elif isinstance(card, SideCard):
            side_to_deck.append(card)

    # Also return orphaned (destroyed) figure cards
    orphaned_main = MainCard.query.filter_by(
        game_id=game_id, in_deck=False, part_of_figure=False, player_id=None
    ).all()
    orphaned_side = SideCard.query.filter_by(
        game_id=game_id, in_deck=False, part_of_figure=False, player_id=None
    ).all()
    for c in orphaned_main:
        if choice == 'pick_card' and picked_card_id and c.id == picked_card_id:
            continue
        main_to_deck.append(c)
    for c in orphaned_side:
        if choice == 'pick_card' and picked_card_id and c.id == picked_card_id:
            continue
        side_to_deck.append(c)

    if main_to_deck:
        DeckManager.return_cards_to_deck(main_to_deck)
    if side_to_deck:
        DeckManager.return_cards_to_deck(side_to_deck)

    # Delete all battle move records
    _delete_all_battle_moves(game_id)

    # Deactivate all spells
    _deactivate_all_spells(game)

    # Collect resting figure IDs BEFORE clearing battle state
    resting_ids = _collect_resting_figure_ids(game)

    # Clear battle state
    _clear_battle_state(game)

    # Log
    log_entry = LogEntry(
        game_id=game.id,
        player_id=player_id,
        round_number=game.current_round,
        turn_number=player.turns_left,
        message=result_msg,
        author="System",
        type='battle_draw'
    )
    db.session.add(log_entry)

    # ── Conquer mode: resolve after one battle ──
    if game.mode == 'conquer':
        # Win/lose draws are handled in finish_battle directly;
        # if we get here, the defender made their choice — resolve normally.
        conquer_result = _resolve_conquer_battle(game, player, player)
        db.session.commit()
        return jsonify(conquer_result)

    # ── Check game-over condition before starting a new round ──
    game_over_info = _check_game_over(game)
    if not game_over_info and game.state == 'finished':
        # Game was already ended by checkmate during destroy choice
        game_over_info = _build_game_over_info_from_finished(game)
    if game_over_info:
        db.session.commit()
        return jsonify({
            'success': True,
            'outcome': 'draw',
            'choice': choice,
            'message': result_msg,
            'game_over': game_over_info,
            'game': game.serialize(),
        })

    # Start a new round — defender (the choosing player) becomes invader
    _start_new_round(game, player)

    # Set resting figures for the new round (server-side — figures with rest_after_attack)
    if resting_ids:
        game.resting_figure_ids = resting_ids

    db.session.commit()
    logger.info(f"[FINISH_BATTLE_DRAW] {result_msg} Round {game.current_round} starts.")

    return jsonify({
        'success': True,
        'outcome': 'draw',
        'choice': choice,
        'message': result_msg,
        'game': game.serialize(),
    })


@games.route('/game_results', methods=['GET'])
def game_results():
    """Get game results for a user (for statistics/ranking).
    
    Query params:
        username: str — the player whose results to fetch
        limit: int (optional) — max number of results (default 50)
    """
    try:
        username = request.args.get('username')
        max_results = request.args.get('limit', 50, type=int)

        user = User.query.filter_by(username=username).first()
        if not user:
            return jsonify({'success': False, 'message': 'User not found'}), 404

        results = GameResult.query.filter(
            (GameResult.winner_user_id == user.id) | (GameResult.loser_user_id == user.id)
        ).order_by(GameResult.finished_at.desc()).limit(max_results).all()

        wins = sum(1 for r in results if r.winner_user_id == user.id)
        losses = len(results) - wins
        total_gold_won = sum(r.gold_awarded for r in results if r.winner_user_id == user.id)

        return jsonify({
            'success': True,
            'username': username,
            'gold': user.gold,
            'wins': wins,
            'losses': losses,
            'total_gold_won': total_gold_won,
            'results': [r.serialize() for r in results],
        })
    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to fetch game results')
        return jsonify({'success': False, 'message': 'Failed to fetch game results'}), 400
