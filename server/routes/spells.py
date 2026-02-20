"""
Server-side spell routes for handling spell casting, countering, and management.
"""

from flask import Blueprint, request, jsonify
from models import db, Game, Player, ActiveSpell, MainCard, SideCard, LogEntry, Figure, CardToFigure, User
from game_service.deck_manager import DeckManager
from sqlalchemy.orm import joinedload

spells = Blueprint('spells', __name__)


@spells.route('/cast_spell', methods=['POST'])
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
    spell_type = data.get('spell_type')
    spell_family_name = data.get('spell_family_name')
    suit = data.get('suit')
    cards = data.get('cards', [])
    target_figure_id = data.get('target_figure_id')
    counterable = data.get('counterable', False)
    
    # Validate required fields
    if not all([player_id, game_id, spell_name, spell_type, spell_family_name, suit]):
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400
    
    # Get game and player
    game = Game.query.get(game_id)
    player = Player.query.get(player_id)
    
    if not game or not player:
        return jsonify({'success': False, 'message': 'Game or player not found'}), 404
    
    # Verify it's player's turn
    if game.turn_player_id != player_id:
        return jsonify({'success': False, 'message': 'Not your turn'}), 403
    
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
                'spell_effect': spell_effect
            }), 200
            
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error casting spell: {str(e)}'}), 500


@spells.route('/counter_spell', methods=['POST'])
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
    
    game = Game.query.get(game_id)
    pending_spell = ActiveSpell.query.get(pending_spell_id)
    
    if not game or not pending_spell:
        return jsonify({'success': False, 'message': 'Game or spell not found'}), 404
    
    # Verify this player can counter
    if game.waiting_for_counter_player_id != player_id:
        return jsonify({'success': False, 'message': 'Not your turn to counter'}), 403
    
    try:
        # Validate counter cards
        counter_card_ids = [card['id'] for card in counter_cards]
        if not _validate_and_mark_spell_cards(player_id, counter_card_ids):
            return jsonify({'success': False, 'message': 'Counter cards not available'}), 400
        
        # Cancel the original spell
        pending_spell.is_pending = False
        pending_spell.is_active = False
        
        # Clear pending spell state
        game.pending_spell_id = None
        game.waiting_for_counter_player_id = None
        
        # Add log entry before commit
        player = Player.query.get(player_id)
        _add_spell_log_entry(
            game_id, player_id, game.current_round,
            player.turns_left, counter_spell_name, 'spell_countered',
            f"{player.serialize()['username']} countered {pending_spell.spell_name} with {counter_spell_name}"
        )
        
        db.session.commit()
        
        # End turn for the player who countered
        player.turns_left -= 1
        db.session.commit()
        
        # Flip turn player
        if game.turn_player_id == player_id:
            game.turn_player_id = game.players[0].id if game.players[0].id != player_id else game.players[1].id
            db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Spell countered with {counter_spell_name}',
            'game': game.serialize(),
            'original_spell_cancelled': True
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error countering spell: {str(e)}'}), 500


@spells.route('/allow_spell', methods=['POST'])
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
    
    game = Game.query.get(game_id)
    pending_spell = ActiveSpell.query.get(pending_spell_id)
    
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
        caster = Player.query.get(pending_spell.player_id)
        spell_effect = _execute_spell(pending_spell, game, caster)
        
        # Add log entry before commit
        player = Player.query.get(player_id)
        _add_spell_log_entry(
            game_id, player_id, game.current_round,
            player.turns_left, pending_spell.spell_name, 'spell_allowed',
            f"{player.serialize()['username']} allowed {pending_spell.spell_name}"
        )
        
        db.session.commit()
        
        # End turn for the player who allowed the spell
        player.turns_left -= 1
        db.session.commit()
        
        # Flip turn player
        if game.turn_player_id == player_id:
            game.turn_player_id = game.players[0].id if game.players[0].id != player_id else game.players[1].id
            db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'{pending_spell.spell_name} executed',
            'game': game.serialize(),
            'spell_effect': spell_effect
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error allowing spell: {str(e)}'}), 500


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
    
    spell = ActiveSpell.query.get(spell_id)
    
    if not spell:
        return jsonify({'success': False, 'message': 'Spell not found'}), 404
    
    return jsonify({
        'success': True,
        'spell': spell.serialize()
    }), 200


@spells.route('/remove_spell_effect', methods=['POST'])
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
    
    spell = ActiveSpell.query.get(spell_id)
    
    if not spell:
        return jsonify({'success': False, 'message': 'Spell not found'}), 404
    
    try:
        spell.is_active = False
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Spell effect removed'
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error removing spell: {str(e)}'}), 500


@spells.route('/end_infinite_hammer', methods=['POST'])
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
    
    try:
        # Expire session to get the latest ActiveSpell data with all accumulated actions
        db.session.expire_all()
        
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
        print(f"[END_INFINITE_HAMMER] Actions tracked: {actions}")
        print(f"[END_INFINITE_HAMMER] Full effect_data: {active_hammer.effect_data}")
        
        # Deactivate the spell
        active_hammer.is_active = False
        
        # Flip the turn to the opponent
        game = Game.query.get(game_id)
        if not game:
            return jsonify({'success': False, 'message': 'Game not found'}), 404
        
        if game.turn_player_id == player_id:
            game.turn_player_id = game.players[0].id if game.players[0].id != player_id else game.players[1].id
        
        # Create log entry
        player = Player.query.get(player_id)
        user = User.query.get(player.user_id)
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
        return jsonify({'success': False, 'message': f'Error ending Infinite Hammer: {str(e)}'}), 500


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
            card_id = card_data['id']
            card_rank = card_data['rank']
            
            # Determine which table to query based on rank
            if card_rank in side_card_ranks:
                card = SideCard.query.get(card_id)
            else:
                card = MainCard.query.get(card_id)
            
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
        print(f"Error validating spell cards: {e}")
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
                drawn_cards = DeckManager.draw_cards_from_deck(game, caster, 2, 'side')
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
                spell_effect['effect'] = f'Failed to draw cards: {str(e)}'
                spell_effect['error'] = str(e)
        
        elif spell.spell_name == 'Draw 2 MainCards':
            try:
                drawn_cards = DeckManager.draw_cards_from_deck(game, caster, 2, 'main')
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
                spell_effect['effect'] = f'Failed to draw cards: {str(e)}'
                spell_effect['error'] = str(e)
        
        elif spell.spell_name == 'Fill up to 10':
            try:
                # Count current main cards in hand only
                main_hand_count = MainCard.query.filter_by(
                    player_id=caster.id,
                    in_deck=False,
                    part_of_figure=False
                ).count()
                
                cards_needed = max(0, 10 - main_hand_count)
                
                print(f"[FILL UP TO 10] Current hand: {main_hand_count}, Cards needed: {cards_needed}")
                
                if cards_needed > 0:
                    # Draw main cards to fill up to 10
                    drawn_cards = DeckManager.draw_cards_from_deck(game, caster, cards_needed, 'main')
                    print(f"[FILL UP TO 10] Drew {len(drawn_cards)} cards")
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
                    print(f"[FILL UP TO 10] Serialized {len(spell_effect['drawn_cards'])} cards to spell_effect")
                else:
                    spell_effect['effect'] = f'Already at or above 10 main cards (current: {main_hand_count})'
                    spell_effect['cards_drawn'] = 0
                    spell_effect['drawn_cards'] = []
                    spell_effect['current_total'] = main_hand_count
                    print(f"[FILL UP TO 10] Already at {main_hand_count} cards, no draw needed")
            except Exception as e:
                print(f"[FILL UP TO 10] ERROR: {str(e)}")
                spell_effect['effect'] = f'Failed to draw cards: {str(e)}'
                spell_effect['error'] = str(e)
        
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
                spell_effect['effect'] = f'Failed to dump cards: {str(e)}'
                spell_effect['error'] = str(e)
        
        elif 'Forced Deal' in spell.spell_name:
            # Exchange 2 random cards with opponent
            try:
                import random
                
                print(f"[FORCED DEAL] Starting Forced Deal spell execution")
                
                # Get opponent
                opponent = next((p for p in game.players if p.id != caster.id), None)
                if not opponent:
                    spell_effect['effect'] = 'No opponent found'
                    spell_effect['error'] = 'No opponent'
                    print(f"[FORCED DEAL] ERROR: No opponent found")
                else:
                    print(f"[FORCED DEAL] Caster: {caster.id}, Opponent: {opponent.id}")
                    
                    # Get caster's MAIN hand cards only (not in deck, not part of figure)
                    caster_main_cards = MainCard.query.filter_by(
                        player_id=caster.id,
                        in_deck=False,
                        part_of_figure=False
                    ).all()
                    
                    print(f"[FORCED DEAL] Caster has {len(caster_main_cards)} main cards in hand")
                    
                    # Get opponent's MAIN hand cards only
                    opponent_main_cards = MainCard.query.filter_by(
                        player_id=opponent.id,
                        in_deck=False,
                        part_of_figure=False
                    ).all()
                    
                    print(f"[FORCED DEAL] Opponent has {len(opponent_main_cards)} main cards in hand")
                    
                    # Check if both players have at least 2 main cards
                    if len(caster_main_cards) < 2:
                        spell_effect['effect'] = 'Not enough main cards in your hand (need at least 2)'
                        spell_effect['error'] = 'Insufficient cards'
                        print(f"[FORCED DEAL] ERROR: Caster has only {len(caster_main_cards)} main cards")
                    elif len(opponent_main_cards) < 2:
                        spell_effect['effect'] = 'Opponent does not have enough main cards (need at least 2)'
                        spell_effect['error'] = 'Insufficient opponent cards'
                        print(f"[FORCED DEAL] ERROR: Opponent has only {len(opponent_main_cards)} main cards")
                    else:
                        # Select 2 random MAIN cards from each player
                        caster_cards_to_swap = random.sample(caster_main_cards, 2)
                        opponent_cards_to_swap = random.sample(opponent_main_cards, 2)
                        
                        print(f"[FORCED DEAL] Swapping cards:")
                        print(f"[FORCED DEAL] Caster gives: {[f'{c.rank}{c.suit}' for c in caster_cards_to_swap]}")
                        print(f"[FORCED DEAL] Opponent gives: {[f'{c.rank}{c.suit}' for c in opponent_cards_to_swap]}")
                        
                        # Swap ownership
                        for card in caster_cards_to_swap:
                            card.player_id = opponent.id
                        
                        for card in opponent_cards_to_swap:
                            card.player_id = caster.id
                        
                        print(f"[FORCED DEAL] Card ownership updated successfully")
                        
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
                        
                        print(f"[FORCED DEAL] Spell effect prepared with {len(spell_effect['cards_given'])} cards given and {len(spell_effect['cards_received'])} cards received")
                        
            except Exception as e:
                spell_effect['effect'] = f'Failed to force deal: {str(e)}'
                spell_effect['error'] = str(e)
                print(f"[FORCED DEAL] EXCEPTION: {str(e)}")
                import traceback
                traceback.print_exc()
        
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
            target_figure = Figure.query.get(spell.target_figure_id)
            if not target_figure:
                spell_effect['effect'] = 'Target figure not found'
                spell_effect['error'] = 'Invalid target'
            else:
                # Check if trying to cast Explosion on a Maharaja
                if 'Explosion' in spell.spell_name and target_figure.name in ['Himalaya Maharaja', 'Djungle Maharaja']:
                    spell_effect['effect'] = 'Explosion cannot be cast on Maharajas'
                    spell_effect['error'] = 'Invalid target: Maharajas are immune to Explosion'
                    db.session.commit()
                    return jsonify({
                        'success': False, 
                        'message': 'Explosion cannot be cast on Maharajas!',
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
                        
                        # Delete the figure
                        db.session.delete(target_figure)
                        db.session.flush()
                        
                        spell_effect['effect'] = f'Destroyed {destroyed_figure_name} ({card_count} cards returned to deck)'
                        spell_effect['destroyed_figure_name'] = destroyed_figure_name
                        spell_effect['card_count'] = card_count
                        
                        # Don't keep this spell active since the figure is destroyed
                        spell.is_active = False
                        
                        # Add log entry for destruction
                        log_entry = LogEntry(
                            game_id=game.id,
                            player_id=destroyed_figure_owner_id,
                            round_number=game.current_round,
                            turn_number=game.current_turn,
                            message=f"{destroyed_figure_name} was destroyed by Explosion spell ({card_count} cards returned to deck)",
                            author='system',
                            type='figure_destroyed'
                        )
                        db.session.add(log_entry)
                        
                    except Exception as e:
                        spell_effect['effect'] = f'Failed to destroy figure: {str(e)}'
                        spell_effect['error'] = str(e)
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
        # Battle modification spells
        spell_effect['effect'] = 'Battle modifier set'
        game.battle_modifier = {
            'type': spell.spell_name,
            'spell_id': spell.id,
            'effect_data': {}  # Spell-specific data
        }
        # TODO: Implement civil war, peasant war, etc.
    
    print(f"[_EXECUTE_SPELL] Returning spell_effect: {spell_effect}")
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
