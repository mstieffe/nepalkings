# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""
Server-side spell routes for handling spell casting, countering, and management.
"""

import logging
from flask import Blueprint, request, jsonify, current_app, g
from models import db, Game, Player, ActiveSpell, MainCard, SideCard, LogEntry, Figure, CardToFigure, User, GameResult
from datetime import datetime, timezone
from game_service.deck_manager import DeckManager
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.attributes import flag_modified
import server_settings as settings
from routes.auth import require_token, verify_player_ownership
from routes.games import _guard_must_advance

logger = logging.getLogger('nepalkings.routes.spells')

spells = Blueprint('spells', __name__)

_ai_logger = logging.getLogger('nepalkings.ai.trigger')


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

@spells.after_request
def _ai_trigger_hook(response):
    """After every POST, check if an AI player needs to act."""
    if request.method == 'POST' and settings.AI_ENABLED:
        if request.headers.get('X-NepalKings-AI-Internal') == '1':
            return response
        game_id = None
        try:
            if request.is_json and request.json:
                game_id = request.json.get('game_id')
        except Exception:
            pass
        if game_id:
            try:
                from ai.ai_worker import trigger_ai_if_needed
                _ai_logger.info(f"Spells trigger hook firing for game {game_id}")
                trigger_ai_if_needed(int(game_id), app=current_app._get_current_object())
            except Exception as e:
                _ai_logger.warning(f"AI trigger error in spells hook: {e}")
    return response


def _guard_spell_mutation(game, *, action_label='spell_action', player_id=None):
    """Block non-battle spell mutations during active battle and pre-decision lock."""
    if not game:
        return None

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

    # Counterable spell lock: while waiting for allow/counter, block other
    # spell mutations. (allow_spell/counter_spell routes do not use this guard.)
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


@spells.route('/cast_spell', methods=['POST'])
@require_token
def cast_spell():
    """
    Cast a spell (both counterable and non-counterable).
    
    Request JSON:
    {
        "player_id": int,
        "game_id": int,
        "spell_name": str,
        "spell_type": str,
        "spell_family_name": str,
        "suit": str,
        "cards": [{"id": int, "rank": str, "suit": str, ...}],
        "target_figure_id": int | None,
        "counterable": bool
    }
    """
    data = request.json
    
    player_id = data.get('player_id')
    game_id = data.get('game_id')
    spell_name = data.get('spell_name')

    err = verify_player_ownership(player_id)
    if err:
        return err
    spell_type = data.get('spell_type')
    spell_family_name = data.get('spell_family_name')
    suit = data.get('suit')
    cards = data.get('cards', [])
    target_figure_id = data.get('target_figure_id')
    counterable = data.get('counterable', False)
    possible_during_ceasefire = data.get('possible_during_ceasefire', True)
    
    # Validate required fields
    if not all([player_id, game_id, spell_name, spell_type, spell_family_name, suit]):
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400
    
    # Get game and player
    game = db.session.get(Game, game_id)
    player = db.session.get(Player, player_id)
    
    if not game or not player:
        return jsonify({'success': False, 'message': 'Game or player not found'}), 404

    # Lock spell casting while a counterable spell is pending resolution.
    if game.pending_spell_id:
        return jsonify({
            'success': False,
            'message': 'Cannot cast a new spell while a counterable spell is pending'
        }), 400
    
    battle_err = _guard_spell_mutation(game, action_label='cast_spell', player_id=player_id)
    if battle_err:
        return battle_err
    
    # Verify it's player's turn
    if game.turn_player_id != player_id:
        return jsonify({'success': False, 'message': 'Not your turn'}), 403

    # Invader must advance on last turn — no spells allowed
    must_adv = _guard_must_advance(game, player_id, action_label='cast_spell')
    if must_adv:
        return must_adv
    
    # Block tactics spells when an advance is in progress
    if spell_type == 'tactics' and game.advancing_figure_id:
        return jsonify({
            'success': False,
            'message': 'Cannot cast battle modifier spells while a figure is advancing'
        }), 403

    # Check if spell can be cast during ceasefire
    if not possible_during_ceasefire and game.ceasefire_active:
        return jsonify({
            'success': False, 
            'message': f'Cannot cast {spell_name} during ceasefire'
        }), 403
    
    # Check for duplicate battle modifier (Civil War, Peasant War, Blitzkrieg can only be cast once per round)
    if spell_name in ('Civil War', 'Peasant War', 'Blitzkrieg'):
        existing_modifiers = game.battle_modifier or []
        if isinstance(existing_modifiers, list):
            for mod in existing_modifiers:
                if mod.get('type') == spell_name:
                    return jsonify({
                        'success': False,
                        'message': f'{spell_name} is already active this round. Each battle modifier can only be cast once per round.'
                    }), 403
    
    try:
        # Validate and mark cards as used
        if not _validate_and_mark_spell_cards(player_id, cards):
            return jsonify({'success': False, 'message': 'Cards not available in hand'}), 400
        
        # Create active spell record
        active_spell = ActiveSpell(
            game_id=game_id,
            player_id=player_id,
            spell_name=spell_name,
            spell_type=spell_type,
            spell_family_name=spell_family_name,
            suit=suit,
            target_figure_id=target_figure_id,
            cast_round=game.current_round,
            counterable=counterable,
            is_pending=counterable,  # If counterable, set as pending
            is_active=not counterable  # If not counterable, activate immediately
        )
        
        db.session.add(active_spell)
        db.session.flush()  # Get spell ID
        
        # Handle based on counterability
        if counterable:
            # Set game state to waiting for counter
            game.pending_spell_id = active_spell.id
            # Get opponent player
            opponent = next((p for p in game.players if p.id != player_id), None)
            if opponent:
                game.waiting_for_counter_player_id = opponent.id
            
            # Add log entry before commit
            _add_spell_log_entry(
                game_id, player_id, game.current_round,
                player.turns_left, spell_name, 'spell_cast_pending',
                f"{player.serialize()['username']} cast {spell_name} (waiting for counter)"
            )
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'{spell_name} cast successfully. Waiting for opponent.',
                'game': game.serialize(),
                'spell_id': active_spell.id,
                'waiting_for_player_id': game.waiting_for_counter_player_id
            }), 200
        
        else:
            # Execute spell immediately
            spell_effect = _execute_spell(active_spell, game, player)
            
            # Add log entry before commit
            _add_spell_log_entry(
                game_id, player_id, game.current_round,
                player.turns_left, spell_name, 'spell_cast',
                f"{player.serialize()['username']} cast {spell_name}"
            )
            
            db.session.commit()
            
            # End turn for non-counterable spells (except Infinite Hammer)
            # Infinite Hammer allows unlimited actions, so don't end turn
            if 'Infinite Hammer' not in spell_name:
                player.turns_left -= 1
                db.session.commit()
                
                # Flip turn player
                if game.turn_player_id == player_id:
                    game.turn_player_id = game.players[0].id if game.players[0].id != player_id else game.players[1].id
                    db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'{spell_name} cast successfully',
                'game': game.serialize(),
                'spell_effect': spell_effect,
                **(({'game_over': spell_effect['game_over']} ) if 'game_over' in spell_effect else {})
            }), 200
            
    except Exception as e:
        db.session.rollback()
        logger.exception('Error casting spell')
        return jsonify({'success': False, 'message': 'Error casting spell'}), 500


@spells.route('/counter_spell', methods=['POST'])
@require_token
def counter_spell():
    """
    Counter a pending spell with another spell.
    
    Request JSON:
    {
        "player_id": int,
        "game_id": int,
        "pending_spell_id": int,
        "counter_spell_name": str,
        "counter_spell_type": str,
        "counter_spell_family_name": str,
        "counter_cards": [...]
    }
    """
    data = request.json
    
    player_id = data.get('player_id')
    game_id = data.get('game_id')
    pending_spell_id = data.get('pending_spell_id')
    counter_spell_name = data.get('counter_spell_name')
    counter_cards = data.get('counter_cards', [])
    
    if not all([player_id, game_id, pending_spell_id, counter_spell_name]):
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400

    err = verify_player_ownership(player_id)
    if err:
        return err
    
    game = db.session.get(Game, game_id)
    pending_spell = db.session.get(ActiveSpell, pending_spell_id)
    
    if not game or not pending_spell:
        return jsonify({'success': False, 'message': 'Game or spell not found'}), 404
    
    # Verify this player can counter
    if game.waiting_for_counter_player_id != player_id:
        return jsonify({'success': False, 'message': 'Not your turn to counter'}), 403
    
    try:
        # Validate counter cards (pass full card dicts, not just IDs)
        if not _validate_and_mark_spell_cards(player_id, counter_cards):
            return jsonify({'success': False, 'message': 'Counter cards not available'}), 400
        
        # Cancel the original spell
        pending_spell.is_pending = False
        pending_spell.is_active = False
        
        # Clear pending spell state
        game.pending_spell_id = None
        game.waiting_for_counter_player_id = None
        
        # Add log entry before commit
        player = db.session.get(Player, player_id)
        _add_spell_log_entry(
            game_id, player_id, game.current_round,
            player.turns_left, counter_spell_name, 'spell_countered',
            f"{player.serialize()['username']} countered {pending_spell.spell_name} with {counter_spell_name}"
        )
        
        db.session.commit()
        
        # Neither player loses a turn when a spell is countered
        # Both players lose their cards but keep their turns
        
        return jsonify({
            'success': True,
            'message': f'Spell countered with {counter_spell_name}. Both players lost cards but kept their turns.',
            'game': game.serialize(),
            'original_spell_cancelled': True,
            'no_turn_lost': True
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.exception('Error countering spell')
        return jsonify({'success': False, 'message': 'Error countering spell'}), 500


@spells.route('/allow_spell', methods=['POST'])
@require_token
def allow_spell():
    """
    Allow an opponent's pending spell to execute.
    
    Request JSON:
    {
        "player_id": int,
        "game_id": int,
        "pending_spell_id": int
    }
    """
    data = request.json
    
    player_id = data.get('player_id')
    game_id = data.get('game_id')
    pending_spell_id = data.get('pending_spell_id')
    
    if not all([player_id, game_id, pending_spell_id]):
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400

    err = verify_player_ownership(player_id)
    if err:
        return err
    
    game = db.session.get(Game, game_id)
    pending_spell = db.session.get(ActiveSpell, pending_spell_id)
    
    if not game or not pending_spell:
        return jsonify({'success': False, 'message': 'Game or spell not found'}), 404
    
    # Verify this player can allow the spell
    if game.waiting_for_counter_player_id != player_id:
        return jsonify({'success': False, 'message': 'Not your turn to respond'}), 403
    
    try:
        # Activate the spell
        pending_spell.is_pending = False
        pending_spell.is_active = True
        
        # Clear pending state
        game.pending_spell_id = None
        game.waiting_for_counter_player_id = None
        
        # Execute the spell
        caster = db.session.get(Player, pending_spell.player_id)
        spell_effect = _execute_spell(pending_spell, game, caster)
        
        # Add log entry before commit
        player = db.session.get(Player, player_id)
        _add_spell_log_entry(
            game_id, player_id, game.current_round,
            player.turns_left, pending_spell.spell_name, 'spell_allowed',
            f"{player.serialize()['username']} allowed {pending_spell.spell_name}"
        )
        
        # End the caster's turn (they used it to cast the spell)
        # Some spells (e.g., Invader Swap, battle modifiers) explicitly set turns_left
        # and should not have it decremented again
        if not spell_effect.get('sets_turns'):
            caster.turns_left -= 1
        
        # Flip turn to other player (unless the spell already set the turn explicitly)
        if not spell_effect.get('turn_set'):
            if game.turn_player_id == caster.id:
                other_player = next((p for p in game.players if p.id != caster.id), None)
                if other_player:
                    game.turn_player_id = other_player.id
        
        db.session.commit()
        
        # The defender does NOT lose a turn for allowing
        
        return jsonify({
            'success': True,
            'message': f'{pending_spell.spell_name} executed. Spell was allowed.',
            'game': game.serialize(),
            'spell_effect': spell_effect,
            'no_turn_lost': True,
            **(({'game_over': spell_effect['game_over']} ) if 'game_over' in spell_effect else {})
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.exception('Error allowing spell')
        return jsonify({'success': False, 'message': 'Error allowing spell'}), 500


@spells.route('/get_active_spells', methods=['GET'])
def get_active_spells():
    """
    Get all active spell effects for a game.
    
    Query params:
        game_id: int
        player_id: int (optional filter)
    """
    game_id = request.args.get('game_id', type=int)
    player_id = request.args.get('player_id', type=int)
    
    if not game_id:
        return jsonify({'success': False, 'message': 'game_id required'}), 400
    
    query = ActiveSpell.query.filter_by(game_id=game_id, is_active=True)
    
    if player_id:
        query = query.filter_by(player_id=player_id)
    
    active_spells = query.all()
    
    return jsonify({
        'success': True,
        'active_spells': [spell.serialize() for spell in active_spells]
    }), 200


@spells.route('/get_pending_spell', methods=['GET'])
def get_pending_spell():
    """
    Get details of a pending spell by ID.
    
    Query params:
        spell_id: int
    """
    spell_id = request.args.get('spell_id', type=int)
    
    if not spell_id:
        return jsonify({'success': False, 'message': 'spell_id required'}), 400
    
    spell = db.session.get(ActiveSpell, spell_id)
    
    if not spell:
        return jsonify({'success': False, 'message': 'Spell not found'}), 404
    
    return jsonify({
        'success': True,
        'spell': spell.serialize()
    }), 200


@spells.route('/remove_spell_effect', methods=['POST'])
@require_token
def remove_spell_effect():
    """
    Remove/deactivate a spell effect.
    
    Request JSON:
    {
        "spell_id": int
    }
    """
    data = request.json
    spell_id = data.get('spell_id')
    
    if not spell_id:
        return jsonify({'success': False, 'message': 'spell_id required'}), 400
    
    spell = db.session.get(ActiveSpell, spell_id)
    
    if not spell:
        return jsonify({'success': False, 'message': 'Spell not found'}), 404

    err = verify_player_ownership(spell.player_id)
    if err:
        return err

    game = db.session.get(Game, spell.game_id)
    battle_err = _guard_spell_mutation(game, action_label='remove_spell_effect', player_id=spell.player_id)
    if battle_err:
        return battle_err
    
    try:
        spell.is_active = False
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Spell effect removed'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.exception('Error removing spell')
        return jsonify({'success': False, 'message': 'Error removing spell'}), 500


@spells.route('/end_infinite_hammer', methods=['POST'])
@require_token
def end_infinite_hammer():
    """
    End Infinite Hammer mode and flip the turn to the opponent.
    
    Request JSON:
    {
        "game_id": int,
        "player_id": int
    }
    """
    data = request.json
    game_id = data.get('game_id')
    player_id = data.get('player_id')
    
    if not game_id or not player_id:
        return jsonify({'success': False, 'message': 'game_id and player_id required'}), 400

    err = verify_player_ownership(player_id)
    if err:
        return err
    
    try:
        # Expire session to get the latest ActiveSpell data with all accumulated actions
        db.session.expire_all()

        game = db.session.get(Game, game_id)
        if not game:
            return jsonify({'success': False, 'message': 'Game not found'}), 404

        battle_err = _guard_spell_mutation(game, action_label='end_infinite_hammer', player_id=player_id)
        if battle_err:
            return battle_err
        
        # Find the active Infinite Hammer spell for this player
        active_hammer = ActiveSpell.query.filter_by(
            player_id=player_id,
            game_id=game_id,
            is_active=True
        ).filter(ActiveSpell.spell_name.like('%Infinite Hammer%')).first()
        
        if not active_hammer:
            return jsonify({'success': False, 'message': 'No active Infinite Hammer found'}), 404
        
        # Get all accumulated actions BEFORE deactivating
        actions = active_hammer.effect_data.get('actions', []) if active_hammer.effect_data else []
        logger.debug(f"[END_INFINITE_HAMMER] Actions tracked: {actions}")
        logger.debug(f"[END_INFINITE_HAMMER] Full effect_data: {active_hammer.effect_data}")
        
        # Deactivate the spell
        active_hammer.is_active = False
        
        # Decrement turns_left (Infinite Hammer consumes one turn)
        player = db.session.get(Player, player_id)
        if player and player.turns_left > 0:
            player.turns_left -= 1
        
        # Flip the turn to the opponent
        
        if game.turn_player_id == player_id:
            game.turn_player_id = game.players[0].id if game.players[0].id != player_id else game.players[1].id
        
        # Create log entry
        user = db.session.get(User, player.user_id)
        username = user.username if user else f"Player {player_id}"
        
        # Build action summary for log
        if actions:
            action_descriptions = [action['description'] for action in actions]
            action_summary = ", ".join(action_descriptions)
            log_message = f"{username} ended Infinite Hammer mode after: {action_summary}."
        else:
            log_message = f"{username} ended Infinite Hammer mode."
        
        log_entry = LogEntry(
            game_id=game_id,
            player_id=player_id,
            round_number=game.current_round,
            turn_number=player.turns_left,
            message=log_message,
            author=username,
            type='spell_end'
        )
        db.session.add(log_entry)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Infinite Hammer mode ended'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        logger.exception('Error ending Infinite Hammer')
        return jsonify({'success': False, 'message': 'Error ending Infinite Hammer'}), 500


# Helper functions

def _validate_and_mark_spell_cards(player_id, cards_data):
    """
    Validate that cards exist in player's hand and return them to deck.
    
    :param player_id: Player ID
    :param cards_data: List of card dicts with 'id', 'rank', 'suit', 'value'
    :return: True if valid and returned to deck, False otherwise
    """
    try:
        cards_to_return = []
        
        # Side card ranks are 2-6, main card ranks are 7-A
        side_card_ranks = ['2', '3', '4', '5', '6']
        
        for card_data in cards_data:
            try:
                card_id = int(card_data['id'])
            except (TypeError, ValueError):
                return False
            card_rank = card_data['rank']
            
            # Determine which table to query based on rank
            if card_rank in side_card_ranks:
                card = db.session.get(SideCard, card_id)
            else:
                card = db.session.get(MainCard, card_id)
            
            if not card:
                return False
            
            if card.player_id != player_id or card.in_deck or card.part_of_figure:
                return False
            
            cards_to_return.append(card)
        
        # Return all cards to deck using DeckManager
        if cards_to_return:
            DeckManager.return_cards_to_deck(cards_to_return)
        
        return True
        
    except Exception as e:
        db.session.rollback()
        logger.debug(f"Error validating spell cards: {e}")
        return False


def _execute_spell(spell: ActiveSpell, game: Game, caster: Player):
    """
    Execute a spell's effect based on its type.
    
    :param spell: ActiveSpell instance
    :param game: Game instance  
    :param caster: Player who cast the spell
    :return: Dictionary describing the effect
    """
    spell_effect = {
        'spell_name': spell.spell_name,
        'spell_type': spell.spell_type,
        'effect': 'Spell executed'
    }
    
    # Handle based on spell type
    if spell.spell_type == 'greed':
        # Hand/deck manipulation spells
        spell_effect['effect'] = 'Hand manipulation effect applied'
        
        # Draw card spells
        if spell.spell_name == 'Draw 2 SideCards':
            try:
                drawn_cards = DeckManager.draw_cards_from_deck(game, caster, 2, 'side', force=True)
                spell_effect['effect'] = f'Drew {len(drawn_cards)} side cards'
                spell_effect['cards_drawn'] = len(drawn_cards)
                spell_effect['card_type'] = 'side'
                # Add type field to serialized cards
                spell_effect['drawn_cards'] = []
                for card in drawn_cards:
                    card_data = card.serialize()
                    card_data['type'] = 'side'
                    spell_effect['drawn_cards'].append(card_data)
            except Exception as e:
                db.session.rollback()
                logger.exception('Failed to draw side cards')
                spell_effect['effect'] = 'Failed to draw cards'
                spell_effect['error'] = True
        
        elif spell.spell_name == 'Draw 2 MainCards':
            try:
                drawn_cards = DeckManager.draw_cards_from_deck(game, caster, 2, 'main', force=True)
                spell_effect['effect'] = f'Drew {len(drawn_cards)} main cards'
                spell_effect['cards_drawn'] = len(drawn_cards)
                spell_effect['card_type'] = 'main'
                # Add type field to serialized cards
                spell_effect['drawn_cards'] = []
                for card in drawn_cards:
                    card_data = card.serialize()
                    card_data['type'] = 'main'
                    spell_effect['drawn_cards'].append(card_data)
            except Exception as e:
                db.session.rollback()
                logger.exception('Failed to draw main cards')
                spell_effect['effect'] = 'Failed to draw cards'
                spell_effect['error'] = True
        
        elif spell.spell_name == 'Fill up to 10':
            try:
                # Count current main cards in hand only
                main_hand_count = MainCard.query.filter_by(
                    player_id=caster.id,
                    in_deck=False,
                    part_of_figure=False
                ).count()
                
                cards_needed = max(0, 10 - main_hand_count)
                
                logger.debug(f"[FILL UP TO 10] Current hand: {main_hand_count}, Cards needed: {cards_needed}")
                
                if cards_needed > 0:
                    # Draw main cards to fill up to 10
                    drawn_cards = DeckManager.draw_cards_from_deck(game, caster, cards_needed, 'main')
                    logger.debug(f"[FILL UP TO 10] Drew {len(drawn_cards)} cards")
                    spell_effect['effect'] = f'Drew {len(drawn_cards)} main cards to reach 10 total'
                    spell_effect['cards_drawn'] = len(drawn_cards)
                    spell_effect['card_type'] = 'main'
                    spell_effect['previous_total'] = main_hand_count
                    spell_effect['new_total'] = main_hand_count + len(drawn_cards)
                    # Add type field to serialized cards
                    spell_effect['drawn_cards'] = []
                    for card in drawn_cards:
                        card_data = card.serialize()
                        card_data['type'] = 'main'
                        spell_effect['drawn_cards'].append(card_data)
                    logger.debug(f"[FILL UP TO 10] Serialized {len(spell_effect['drawn_cards'])} cards to spell_effect")
                else:
                    spell_effect['effect'] = f'Already at or above 10 main cards (current: {main_hand_count})'
                    spell_effect['cards_drawn'] = 0
                    spell_effect['drawn_cards'] = []
                    spell_effect['current_total'] = main_hand_count
                    logger.debug(f"[FILL UP TO 10] Already at {main_hand_count} cards, no draw needed")
            except Exception as e:
                db.session.rollback()
                logger.exception('Fill up to 10 failed')
                spell_effect['effect'] = 'Failed to draw cards'
                spell_effect['error'] = True
        
        elif spell.spell_name == 'Dump Cards':
            try:
                # Get both players
                opponent = None
                for player in game.players:
                    if player.id != caster.id:
                        opponent = player
                        break
                
                if not opponent:
                    spell_effect['effect'] = 'No opponent found'
                    spell_effect['error'] = 'No opponent'
                else:
                    # Return all cards to deck for both players
                    caster_main_cards = MainCard.query.filter_by(
                        player_id=caster.id,
                        in_deck=False,
                        part_of_figure=False
                    ).all()
                    
                    caster_side_cards = SideCard.query.filter_by(
                        player_id=caster.id,
                        in_deck=False,
                        part_of_figure=False
                    ).all()
                    
                    opponent_main_cards = MainCard.query.filter_by(
                        player_id=opponent.id,
                        in_deck=False,
                        part_of_figure=False
                    ).all()
                    
                    opponent_side_cards = SideCard.query.filter_by(
                        player_id=opponent.id,
                        in_deck=False,
                        part_of_figure=False
                    ).all()
                    
                    # Count dumped cards
                    caster_dumped = len(caster_main_cards) + len(caster_side_cards)
                    opponent_dumped = len(opponent_main_cards) + len(opponent_side_cards)
                    
                    # Return all cards to deck
                    all_cards_to_dump = caster_main_cards + caster_side_cards + opponent_main_cards + opponent_side_cards
                    if all_cards_to_dump:
                        DeckManager.return_cards_to_deck(all_cards_to_dump)
                    
                    # Deal new cards to both players (5 main, 4 side)
                    caster_new_main = DeckManager.draw_cards_from_deck(game, caster, 5, 'main')
                    caster_new_side = DeckManager.draw_cards_from_deck(game, caster, 4, 'side')
                    opponent_new_main = DeckManager.draw_cards_from_deck(game, opponent, 5, 'main')
                    opponent_new_side = DeckManager.draw_cards_from_deck(game, opponent, 4, 'side')
                    
                    spell_effect['effect'] = f'Both players dumped all cards and drew 5 main + 4 side cards'
                    spell_effect['caster_dumped'] = caster_dumped
                    spell_effect['opponent_dumped'] = opponent_dumped
                    spell_effect['cards_drawn'] = len(caster_new_main) + len(caster_new_side)
                    
                    # Add caster's new cards
                    spell_effect['drawn_cards'] = []
                    for card in caster_new_main:
                        card_data = card.serialize()
                        card_data['type'] = 'main'
                        spell_effect['drawn_cards'].append(card_data)
                    for card in caster_new_side:
                        card_data = card.serialize()
                        card_data['type'] = 'side'
                        spell_effect['drawn_cards'].append(card_data)
            except Exception as e:
                db.session.rollback()
                logger.exception('Failed to dump cards')
                spell_effect['effect'] = 'Failed to dump cards'
                spell_effect['error'] = True
        
        elif 'Forced Deal' in spell.spell_name:
            # Exchange 2 random cards with opponent
            try:
                import random
                
                logger.debug(f"[FORCED DEAL] Starting Forced Deal spell execution")
                
                # Get opponent
                opponent = next((p for p in game.players if p.id != caster.id), None)
                if not opponent:
                    spell_effect['effect'] = 'No opponent found'
                    spell_effect['error'] = 'No opponent'
                    logger.error(f"[FORCED DEAL] ERROR: No opponent found")
                else:
                    logger.debug(f"[FORCED DEAL] Caster: {caster.id}, Opponent: {opponent.id}")
                    
                    # Get caster's MAIN hand cards only (not in deck, not part of figure)
                    caster_main_cards = MainCard.query.filter_by(
                        player_id=caster.id,
                        in_deck=False,
                        part_of_figure=False
                    ).all()
                    
                    logger.debug(f"[FORCED DEAL] Caster has {len(caster_main_cards)} main cards in hand")
                    
                    # Get opponent's MAIN hand cards only
                    opponent_main_cards = MainCard.query.filter_by(
                        player_id=opponent.id,
                        in_deck=False,
                        part_of_figure=False
                    ).all()
                    
                    logger.debug(f"[FORCED DEAL] Opponent has {len(opponent_main_cards)} main cards in hand")
                    
                    # Check if both players have at least 2 main cards
                    if len(caster_main_cards) < 2:
                        spell_effect['effect'] = 'Not enough main cards in your hand (need at least 2)'
                        spell_effect['error'] = 'Insufficient cards'
                        logger.error(f"[FORCED DEAL] ERROR: Caster has only {len(caster_main_cards)} main cards")
                    elif len(opponent_main_cards) < 2:
                        spell_effect['effect'] = 'Opponent does not have enough main cards (need at least 2)'
                        spell_effect['error'] = 'Insufficient opponent cards'
                        logger.error(f"[FORCED DEAL] ERROR: Opponent has only {len(opponent_main_cards)} main cards")
                    else:
                        # Select 2 random MAIN cards from each player
                        caster_cards_to_swap = random.sample(caster_main_cards, 2)
                        opponent_cards_to_swap = random.sample(opponent_main_cards, 2)
                        
                        logger.debug(f"[FORCED DEAL] Swapping cards:")
                        logger.debug(f"[FORCED DEAL] Caster gives: {[f'{c.rank}{c.suit}' for c in caster_cards_to_swap]}")
                        logger.debug(f"[FORCED DEAL] Opponent gives: {[f'{c.rank}{c.suit}' for c in opponent_cards_to_swap]}")
                        
                        # Swap ownership
                        for card in caster_cards_to_swap:
                            card.player_id = opponent.id
                        
                        for card in opponent_cards_to_swap:
                            card.player_id = caster.id
                        
                        logger.debug(f"[FORCED DEAL] Card ownership updated successfully")
                        
                        spell_effect['effect'] = 'Exchanged 2 random cards with opponent'
                        spell_effect['cards_given'] = [card.serialize() for card in caster_cards_to_swap]
                        spell_effect['cards_received'] = [card.serialize() for card in opponent_cards_to_swap]
                        
                        # Store swap details in spell's effect_data for opponent notification
                        spell.effect_data = {
                            'caster_id': caster.id,
                            'opponent_id': opponent.id,
                            'caster_gave': [card.serialize() for card in caster_cards_to_swap],
                            'caster_received': [card.serialize() for card in opponent_cards_to_swap],
                            'opponent_gave': [card.serialize() for card in opponent_cards_to_swap],
                            'opponent_received': [card.serialize() for card in caster_cards_to_swap],
                            'notification_pending': True  # Flag to show this needs to be shown to opponent
                        }
                        
                        # Add opponent notification data (opponent sees opposite perspective)
                        spell_effect['opponent_notification'] = {
                            'message': f'{caster.serialize()["username"]} cast Forced Deal!',
                            'cards_given': [card.serialize() for card in opponent_cards_to_swap],
                            'cards_received': [card.serialize() for card in caster_cards_to_swap]
                        }
                        
                        logger.debug(f"[FORCED DEAL] Spell effect prepared with {len(spell_effect['cards_given'])} cards given and {len(spell_effect['cards_received'])} cards received")
                        
            except Exception as e:
                db.session.rollback()
                logger.exception('Forced Deal failed')
                spell_effect['effect'] = 'Failed to force deal'
                spell_effect['error'] = True
        
    elif spell.spell_type == 'enchantment':
        # Figure enchantment spells
        spell_effect['effect'] = 'Enchantment applied'
        
        # Handle non-targeted enchantment spells (global effects)
        if 'All Seeing Eye' in spell.spell_name:
            spell_effect['effect'] = 'Revealed all opponent cards and figures'
            spell.effect_data = {
                'spell_icon': 'eye.png',
                'caster_player_id': spell.player_id
            }
            spell.is_active = True
            spell_effect['spell_icon'] = 'eye.png'
            
        elif 'Infinite Hammer' in spell.spell_name:
            spell_effect['effect'] = 'Unlimited building this turn'
            spell.effect_data = {
                'spell_icon': 'infinite_hammer.png',
                'caster_player_id': spell.player_id
            }
            spell.is_active = True
            spell_effect['spell_icon'] = 'infinite_hammer.png'
            
        elif spell.target_figure_id:
            spell_effect['target_figure_id'] = spell.target_figure_id
            
            # Get target figure to validate it exists
            target_figure = db.session.get(Figure, spell.target_figure_id)
            if not target_figure:
                spell_effect['effect'] = 'Target figure not found'
                spell_effect['error'] = 'Invalid target'
            else:
                # Check if target figure has checkmate (immune to all spells)
                if getattr(target_figure, 'checkmate', False):
                    spell_effect['effect'] = f'{target_figure.name} is immune to spells (Checkmate)'
                    spell_effect['error'] = 'Invalid target: Checkmate figures are immune to spells'
                    db.session.commit()
                    return jsonify({
                        'success': False, 
                        'message': f'{target_figure.name} is immune to spells!',
                        'spell_effect': spell_effect
                    }), 400
                
                # Determine spell icon filename based on spell name
                spell_icon = 'default_spell_icon.png'
                power_modifier = 0
                
                if 'Poison' in spell.spell_name:
                    spell_icon = 'poisson_portion.png'
                    power_modifier = -6
                    spell_effect['effect'] = f'Poisoned {target_figure.name} (-6 power)'
                elif 'Boost' in spell.spell_name or 'Health' in spell.spell_name:
                    spell_icon = 'health_portion.png'
                    power_modifier = 6
                    spell_effect['effect'] = f'Boosted {target_figure.name} (+6 power)'
                elif 'Explosion' in spell.spell_name:
                    spell_icon = 'bomb.png'
                    power_modifier = -999  # Not used since figure is destroyed
                    
                    # Actually destroy the figure and return cards to deck
                    try:
                        # Get all cards associated with this figure
                        card_associations = CardToFigure.query.filter_by(figure_id=target_figure.id).all()
                        
                        main_card_ids = []
                        side_card_ids = []
                        for assoc in card_associations:
                            if assoc.card_type == 'main':
                                main_card_ids.append(assoc.card_id)
                            elif assoc.card_type == 'side':
                                side_card_ids.append(assoc.card_id)
                        
                        # Get the actual card objects
                        main_cards = MainCard.query.filter(MainCard.id.in_(main_card_ids)).all() if main_card_ids else []
                        side_cards = SideCard.query.filter(SideCard.id.in_(side_card_ids)).all() if side_card_ids else []
                        
                        # Return cards to deck (discard pile)
                        for card in main_cards + side_cards:
                            card.part_of_figure = False
                            card.in_deck = True
                            card.player_id = None  # No longer belongs to any player
                            card.deck_position = None  # Will be reshuffled
                        
                        # Delete card associations
                        CardToFigure.query.filter_by(figure_id=target_figure.id).delete()
                        
                        # Remove any other active enchantment spells on this figure
                        ActiveSpell.query.filter_by(
                            game_id=game.id,
                            target_figure_id=target_figure.id
                        ).delete()
                        
                        # Store figure name before deletion for logging
                        destroyed_figure_name = target_figure.name
                        destroyed_figure_field = target_figure.field
                        destroyed_figure_owner_id = target_figure.player_id
                        card_count = len(main_card_ids) + len(side_card_ids)
                        
                        # Check checkmate before deleting the figure
                        checkmate_game_over = None
                        if getattr(target_figure, 'checkmate', False) and game.state != 'finished':
                            loser_player = db.session.get(Player, target_figure.player_id)
                            winner_player = [p for p in game.players if p.id != loser_player.id][0]
                            stake = game.stake or settings.DEFAULT_GAME_STAKE
                            gold_awarded = stake * 2
                            game.state = 'finished'
                            game.winner_player_id = winner_player.id
                            game.finished_at = _utcnow()
                            winner_user = db.session.get(User, winner_player.user_id)
                            loser_user = db.session.get(User, loser_player.user_id)
                            if winner_user:
                                winner_user.gold += gold_awarded
                            winner_username = winner_user.username if winner_user else f"Player {winner_player.id}"
                            loser_username = loser_user.username if loser_user else f"Player {loser_player.id}"
                            game_result = GameResult(
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
                            db.session.add(game_result)
                            checkmate_game_over = {
                                'game_over': True,
                                'reason': 'checkmate',
                                'checkmate_figure_name': destroyed_figure_name,
                                'winner_player_id': winner_player.id,
                                'loser_player_id': loser_player.id,
                                'winner_username': winner_username,
                                'loser_username': loser_username,
                                'winner_score': winner_player.points,
                                'loser_score': loser_player.points,
                                'gold_awarded': gold_awarded,
                                'stake': stake,
                            }
                            checkmate_log = LogEntry(
                                game_id=game.id, player_id=winner_player.id,
                                round_number=game.current_round, turn_number=0,
                                message=f"💀 CHECKMATE! {loser_username}'s {destroyed_figure_name} was destroyed by Explosion — {winner_username} wins!",
                                author="System", type='game_over'
                            )
                            db.session.add(checkmate_log)
                        
                        # Delete the figure
                        db.session.delete(target_figure)
                        db.session.flush()
                        
                        spell_effect['effect'] = f'Destroyed {destroyed_figure_name} ({card_count} cards returned to deck)'
                        spell_effect['destroyed_figure_name'] = destroyed_figure_name
                        spell_effect['card_count'] = card_count
                        if checkmate_game_over:
                            spell_effect['game_over'] = checkmate_game_over
                        
                        # Don't keep this spell active since the figure is destroyed
                        spell.is_active = False
                        
                        # Add log entry for destruction
                        log_entry = LogEntry(
                            game_id=game.id,
                            player_id=destroyed_figure_owner_id,
                            round_number=game.current_round,
                            turn_number=game.current_round,
                            message=f"{destroyed_figure_name} was destroyed by Explosion spell ({card_count} cards returned to deck)",
                            author='system',
                            type='figure_destroyed'
                        )
                        db.session.add(log_entry)
                        
                    except Exception as e:
                        db.session.rollback()
                        logger.exception('Failed to destroy figure')
                        spell_effect['effect'] = 'Failed to destroy figure'
                        spell_effect['error'] = True
                        spell.is_active = False
                
                # Only store enchantment data for non-Explosion spells (Explosion destroys the figure)
                if 'Explosion' not in spell.spell_name:
                    # Store enchantment data in spell's effect_data
                    spell.effect_data = {
                        'spell_icon': spell_icon,
                        'power_modifier': power_modifier,
                        'target_figure_name': target_figure.name
                    }
                    
                    # Keep spell active so it persists until battle/end of turn
                    spell.is_active = True
                    
                    spell_effect['power_modifier'] = power_modifier
                    spell_effect['spell_icon'] = spell_icon
        else:
            spell_effect['effect'] = 'No target specified'
            spell_effect['error'] = 'Missing target'
        
    elif spell.spell_type == 'tactics':
        # Battle modification spells (stackable - battle_modifier is a list)
        spell_effect['effect'] = 'Battle modifier set'
        
        # Handle Ceasefire specifically
        if spell.spell_name == 'Ceasefire':
            try:
                # Give both players 3 additional turns
                invader_player = db.session.get(Player, game.invader_player_id)
                defender_player = next((p for p in game.players if p.id != game.invader_player_id), None)
                
                if not invader_player or not defender_player:
                    spell_effect['effect'] = 'Failed to activate ceasefire: player not found'
                    spell_effect['error'] = 'Player not found'
                else:
                    # Add 3 turns to both players
                    invader_player.turns_left += 3
                    defender_player.turns_left += 3
                    
                    # Activate ceasefire for 3 invader turns from NOW
                    game.ceasefire_active = True
                    # Record the invader's current turn index so ceasefire lasts exactly 3 more invader turns
                    game.ceasefire_start_turn = settings.INITIAL_TURNS_INVADER - invader_player.turns_left
                    
                    logger.info(f"[CEASEFIRE SPELL] Both players gained 3 turns. Invader: {invader_player.turns_left}, Defender: {defender_player.turns_left}")
                    
                    spell_effect['effect'] = 'Both players gained 3 additional turns. Ceasefire restored.'
                    spell_effect['ceasefire_activated'] = True
                    spell_effect['invader_turns'] = invader_player.turns_left
                    spell_effect['defender_turns'] = defender_player.turns_left
            except Exception as e:
                db.session.rollback()
                logger.exception('Ceasefire spell failed')
                spell_effect['effect'] = 'Failed to activate ceasefire'
                spell_effect['error'] = True
        
        elif spell.spell_name == 'Invader Swap':
            try:
                old_invader_id = game.invader_player_id
                new_invader = next((p for p in game.players if p.id != old_invader_id), None)
                
                if not new_invader:
                    spell_effect['effect'] = 'Failed to swap invader: opponent not found'
                    spell_effect['error'] = 'Player not found'
                else:
                    old_invader = db.session.get(Player, old_invader_id)
                    old_invader_name = old_invader.serialize()['username'] if old_invader else 'Unknown'
                    new_invader_name = new_invader.serialize()['username']
                    
                    # Swap invader
                    game.invader_player_id = new_invader.id
                    
                    # Set both players' turns left to 2
                    old_invader.turns_left = 2
                    new_invader.turns_left = 2
                    
                    # Invader starts next turn
                    game.turn_player_id = new_invader.id

                    # Clear any in-progress advance/defend state to prevent
                    # a stale advancing_player_id from causing a battle
                    # deadlock after the swap (Bug #3).
                    game.advancing_figure_id = None
                    game.advancing_figure_id_2 = None
                    game.advancing_player_id = None
                    game.defending_figure_id = None
                    game.defending_figure_id_2 = None
                    
                    logger.info(f"[INVADER SWAP] Swapped invader from {old_invader_name} (id={old_invader_id}) to {new_invader_name} (id={new_invader.id})")
                    logger.info(f"[INVADER SWAP] Both players' turns_left set to 2. Advance/defend state cleared. Invader starts next turn.")
                    
                    spell_effect['effect'] = f'Invader and defender roles have been swapped! {new_invader_name} is now the invader. Both players have 2 turns left. The invader starts next turn.'
                    spell_effect['turn_set'] = True
                    spell_effect['sets_turns'] = True
                    spell_effect['old_invader_id'] = old_invader_id
                    spell_effect['new_invader_id'] = new_invader.id
                    spell_effect['invader_swapped'] = True
            except Exception as e:
                db.session.rollback()
                logger.exception('Invader Swap failed')
                spell_effect['effect'] = 'Failed to swap invader'
                spell_effect['error'] = True
        
        elif spell.spell_name in ('Civil War', 'Peasant War', 'Blitzkrieg'):
            try:
                invader_player = db.session.get(Player, game.invader_player_id)
                defender_player = next((p for p in game.players if p.id != game.invader_player_id), None)
                
                if not invader_player or not defender_player:
                    spell_effect['effect'] = f'Failed to activate {spell.spell_name}: player not found'
                    spell_effect['error'] = 'Player not found'
                else:
                    caster_name = caster.serialize()['username']
                    
                    # Blitzkrieg: caster becomes the invader (if not already)
                    if spell.spell_name == 'Blitzkrieg' and game.invader_player_id != caster.id:
                        old_invader_id = game.invader_player_id
                        game.invader_player_id = caster.id
                        # Reassign invader/defender player references after swap
                        invader_player = db.session.get(Player, caster.id)
                        defender_player = next((p for p in game.players if p.id != caster.id), None)
                        logger.info(f"[BLITZKRIEG] Invader swapped from player {old_invader_id} to caster {caster.id}")
                        spell_effect['invader_swapped'] = True
                        spell_effect['old_invader_id'] = old_invader_id
                        spell_effect['new_invader_id'] = caster.id
                    
                    # Set both players' turns left to 2
                    invader_player.turns_left = 2
                    defender_player.turns_left = 2
                    
                    # Invader starts next turn
                    game.turn_player_id = invader_player.id
                    
                    # Blitzkrieg: activate ceasefire immediately for the last turn
                    # This prevents the defender from advancing or casting battle spells
                    # Ceasefire will end automatically when both players reach 0 turns
                    if spell.spell_name == 'Blitzkrieg':
                        game.ceasefire_active = True
                        # ceasefire_start_turn not needed — Blitzkrieg ceasefire uses
                        # its own end condition (both players at 0 turns)
                        logger.info(f"[BLITZKRIEG] Ceasefire activated for last turn")
                        spell_effect['ceasefire_activated'] = True
                    
                    # Initialize battle_modifier as list if needed (stackable modifiers)
                    if not isinstance(game.battle_modifier, list):
                        game.battle_modifier = []
                    
                    # Append this modifier (non-exclusive: can stack with others)
                    modifier_entry = {
                        'type': spell.spell_name,
                        'spell_id': spell.id,
                        'caster_id': caster.id,
                        'caster_name': caster_name
                    }
                    
                    game.battle_modifier.append(modifier_entry)
                    
                    # Spell-specific descriptions
                    descriptions = {
                        'Civil War': 'Each player selects two villagers of the same color for battle.',
                        'Peasant War': 'Only villagers can be selected for the upcoming battle.',
                        'Blitzkrieg': f'{caster_name} is now the invader! The advancing figure cannot be blocked. Ceasefire is in effect after the battle.'
                    }
                    
                    spell_effect['effect'] = f'{spell.spell_name} activated by {caster_name}! {descriptions[spell.spell_name]} Both players have 2 turns left. The invader starts next turn.'
                    spell_effect['turn_set'] = True
                    spell_effect['battle_modifier_added'] = spell.spell_name
                    spell_effect['caster_name'] = caster_name
                    spell_effect['sets_turns'] = True
                    
                    # Signal SQLAlchemy that the JSON column was mutated in place
                    flag_modified(game, 'battle_modifier')
                    
                    logger.debug(f"[{spell.spell_name.upper()}] Activated by {caster_name}. Battle modifier appended. Both players' turns_left set to 2. Invader starts next turn.")
                    logger.debug(f"[{spell.spell_name.upper()}] Active battle modifiers: {game.battle_modifier}")
            except Exception as e:
                db.session.rollback()
                logger.exception(f'{spell.spell_name} failed')
                spell_effect['effect'] = f'Failed to activate {spell.spell_name}'
                spell_effect['error'] = True
    
    logger.debug(f"[_EXECUTE_SPELL] Returning spell_effect: {spell_effect}")
    return spell_effect


def _add_spell_log_entry(game_id, player_id, round_number, turn_number, spell_name, entry_type, message):
    """
    Add a log entry for a spell action.
    
    :param game_id: Game ID
    :param player_id: Player ID
    :param round_number: Current round
    :param turn_number: Current turn
    :param spell_name: Name of the spell
    :param entry_type: Type of log entry
    :param message: Log message
    """
    log_entry = LogEntry(
        game_id=game_id,
        player_id=player_id,
        round_number=round_number,
        turn_number=turn_number,
        message=message,
        author='system',
        type=entry_type
    )
    db.session.add(log_entry)
