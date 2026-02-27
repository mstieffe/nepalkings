from flask import Blueprint, request, jsonify
from sqlalchemy.orm import joinedload
import random
from models import db, User, Challenge, Player, Game, MainCard, SideCard, Figure, CardToFigure, LogEntry
from game_service.deck_manager import DeckManager

import server_settings as settings

games = Blueprint('games', __name__)

def _check_and_update_ceasefire(game):
    """
    Check if ceasefire should end and update game state accordingly.
    Ceasefire lasts for 3 invader turns normally.
    Blitzkrieg ceasefire ends when both players have 0 turns left.
    Returns True if ceasefire ended this check.
    """
    if not game.ceasefire_active:
        return False
    
    # Blitzkrieg ceasefire: ends when both players have 0 turns left
    # (so the invader can then do the forced advance)
    modifiers = game.battle_modifier if isinstance(game.battle_modifier, list) else []
    has_blitzkrieg = any(m.get('type') == 'Blitzkrieg' for m in modifiers)
    if has_blitzkrieg:
        all_zero = all(p.turns_left <= 0 for p in game.players)
        if all_zero:
            print(f"[CEASEFIRE] Blitzkrieg ceasefire ending (both players at 0 turns)")
            game.ceasefire_active = False
            game.ceasefire_start_turn = None
            db.session.commit()
            return True
        else:
            # Blitzkrieg ceasefire still active — skip the normal turn-based check
            return False
    
    # Normal ceasefire: lasts for 3 invader turns
    # ceasefire_start_turn stores the invader's "turn index" when ceasefire began
    # (i.e. INITIAL_TURNS_INVADER - invader.turns_left at ceasefire start)
    invader_player = Player.query.get(game.invader_player_id)
    if not invader_player:
        return False
    
    # Calculate how many invader turns have passed since ceasefire started
    current_turn = settings.INITIAL_TURNS_INVADER - invader_player.turns_left
    ceasefire_start = game.ceasefire_start_turn if game.ceasefire_start_turn is not None else 0
    invader_turns_during_ceasefire = current_turn - ceasefire_start
    
    print(f"[CEASEFIRE] Current turn index: {current_turn}, Ceasefire start index: {ceasefire_start}, Invader turns during ceasefire: {invader_turns_during_ceasefire}")
    
    # Ceasefire ends after 3 invader turns
    if invader_turns_during_ceasefire >= 3:
        print(f"[CEASEFIRE] Ceasefire ending (3 invader turns passed)")
        game.ceasefire_active = False
        game.ceasefire_start_turn = None
        db.session.commit()
        return True
    
    return False

def _is_ceasefire_active(game_id):
    """Check if ceasefire is currently active for a game."""
    game = Game.query.get(game_id)
    if not game:
        return False
    return game.ceasefire_active

def _check_and_fill_minimum_cards(game, player):
    """
    Check if player has minimum required cards and auto-fill if needed.
    Returns fill_info dict with details about what was filled, or None if no fill needed.
    """
    print(f"[AUTO-FILL] Starting check for player {player.id} in game {game.id}")
    
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
    
    print(f"[AUTO-FILL] Player {player.id}: main={main_cards_count}/{settings.NUM_MIN_MAIN_CARDS}, side={side_cards_count}/{settings.NUM_MIN_SIDE_CARDS}")
    
    if main_cards_needed == 0 and side_cards_needed == 0:
        print(f"[AUTO-FILL] No fill needed")
        return None
    
    # Auto-fill needed
    print(f"[AUTO-FILL] Need to fill: main={main_cards_needed}, side={side_cards_needed}")
    fill_info = {
        'main_cards_filled': 0,
        'side_cards_filled': 0,
        'cards': []  # List of card data (suit, rank, type)
    }
    
    if main_cards_needed > 0:
        print(f"[AUTO-FILL] Drawing {main_cards_needed} main cards")
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
        print(f"[AUTO-FILL] Drew {len(drawn_main)} main cards")
    
    if side_cards_needed > 0:
        print(f"[AUTO-FILL] Drawing {side_cards_needed} side cards")
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
        print(f"[AUTO-FILL] Drew {len(drawn_side)} side cards")
    
    print(f"[AUTO-FILL] Returning fill_info: {fill_info}")
    return fill_info

def _get_opponent_turn_summary(game, current_player_id):
    """
    Analyze recent log entries to determine what the opponent did in their last turn.
    Returns a summary dict with action type and relevant details.
    """
    from models import LogEntry, ActiveSpell
    
    print(f"[OPPONENT_TURN] Getting summary for game {game.id}, current player {current_player_id}")
    
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
    print(f"[OPPONENT_TURN] Last 5 logs from opponent: {[(log.type, log.message) for log in all_logs]}")
    
    # Check if current player had a figure destroyed (by opponent's Explosion spell)
    destroyed_figure_log = LogEntry.query.filter(
        LogEntry.game_id == game.id,
        LogEntry.player_id == current_player_id,
        LogEntry.round_number == game.current_round,
        LogEntry.type == 'figure_destroyed'
    ).order_by(LogEntry.id.desc()).first()
    
    # If a figure was destroyed, prioritize showing this
    if destroyed_figure_log:
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
            print(f"[INFINITE_HAMMER] Log message: {infinite_hammer_log.message}")
            match = re.search(r'ended Infinite Hammer mode after: (.+)\.', infinite_hammer_log.message)
            if match:
                actions_text = match.group(1)
                print(f"[INFINITE_HAMMER] Extracted actions: {actions_text}")
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
                print(f"[INFINITE_HAMMER] No actions match found in message")
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
        LogEntry.type.in_(['figure_built', 'figure_upgraded', 'spell_cast', 'figure_pickup', 'card_changed'])
    ).order_by(LogEntry.id.desc()).first()
    
    print(f"[OPPONENT_TURN] Most recent actionable log: {recent_log.type if recent_log else 'None'} - {recent_log.message if recent_log else 'None'}")
    
    # Check if this is game start - each player should see it once
    # Check if current player has any logs yet (works regardless of turn/round number)
    current_player_logs = LogEntry.query.filter(
        LogEntry.game_id == game.id,
        LogEntry.player_id == current_player_id
    ).first()
    
    # Also check if opponent has taken any meaningful action
    opponent_action_logs = LogEntry.query.filter(
        LogEntry.game_id == game.id,
        LogEntry.player_id == opponent.id,
        LogEntry.type.in_(['figure_built', 'figure_upgraded', 'spell_cast', 'figure_pickup', 'card_changed'])
    ).first()
    
    print(f"[GAME_START_CHECK] Player {current_player_id} has logs: {current_player_logs is not None}, opponent has action logs: {opponent_action_logs is not None}, is_turn: {game.turn_player_id == current_player_id}")
    
    # Show welcome message if player has no logs, UNLESS:
    # - It's their turn AND opponent has played (they already saw the game while waiting, now it's their turn)
    should_show_welcome = False
    if not current_player_logs:
        if not opponent_action_logs:
            # Neither player has played - always show welcome
            should_show_welcome = True
        elif game.turn_player_id != current_player_id:
            # Opponent has played but it's not this player's turn yet
            # This is their first view of the game while waiting - show welcome
            should_show_welcome = True
        # else: opponent has played and now it's player's turn - they already saw the game, skip welcome
    
    if should_show_welcome:
        print(f"[GAME_START_CHECK] Showing welcome for player {current_player_id}")
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
            
            print(f"[GAME_START_CHECK] Returning game_start action for player {current_player_id} (is_turn={is_turn}, is_invader={is_invader})")
            
            return {
                'action': 'game_start',
                'opponent_name': opponent.serialize()['username'],
                'maharaja': maharaja.serialize(),  # Full figure data for FieldFigureIcon
                'is_turn': is_turn,
                'is_invader': is_invader
            }
        else:
            print(f"[GAME_START_CHECK] No Maharaja found for player {current_player_id}")
    else:
        print(f"[GAME_START_CHECK] Player {current_player_id} has existing logs, skipping game_start")
    
    if not recent_log:
        return {
            'action': 'unknown',
            'opponent_name': opponent.serialize()['username'],
            'message': f"{opponent.serialize()['username']} completed their turn."
        }
    
    summary = {
        'opponent_name': opponent.serialize()['username'],
        'action': None
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
    
    elif log_type == 'spell_cast':
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
            'type': 'spell',
            'spell_name': spell_name,
            'spell_icon': spell_icon,
            'message': f'Cast {spell_name}'
        }
        
        print(f"[OPPONENT_TURN] Detected spell: {spell_name}")
        
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
            from models import MainCard, SideCard
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
            
            print(f"[DUMP_CARDS_SERVER] Found {len(main_cards)} main cards and {len(side_cards)} side cards for player {current_player_id}")
            
            # Serialize cards for display
            action_data['new_cards'] = []
            for card in main_cards + side_cards:
                card_data = card.serialize()
                card_data['type'] = 'main' if isinstance(card, MainCard) else 'side'
                action_data['new_cards'].append(card_data)
            action_data['message'] = f'Cast Dump Cards - you drew {len(action_data["new_cards"])} new cards'
            print(f"[DUMP_CARDS_SERVER] Serialized {len(action_data['new_cards'])} cards for notification")
        
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
                target_figure = Figure.query.get(poison_spell.target_figure_id)
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
    
    print(f"[OPPONENT_TURN] Summary: {summary}")
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
            (Player.user_id == user.id) & (Game.state == 'open')
        ).all()

        return jsonify({
            'games': [game.serialize() for game in games]
        })
    except Exception as e:
        return jsonify({'success': False, 'message': 'An error occurred: {}'.format(str(e))}), 400


@games.route('/get_game', methods=['GET'])
def get_game():
    try:
        game_id = request.args.get('game_id')
        game = Game.query.get(game_id)

        if not game:
            return jsonify({'success': False, 'message': 'Game not found'}), 400

        # Check if Blitzkrieg ceasefire should end (runs on every poll)
        _check_and_update_ceasefire(game)

        return jsonify({
            'game': game.serialize()
        })
    except Exception as e:
        return jsonify({'success': False, 'message': 'An error occurred: {}'.format(str(e))}), 400


@games.route('/start_turn', methods=['POST'])
def start_turn():
    """
    Called when a player's turn begins. Checks and auto-fills minimum cards if needed.
    """
    try:
        data = request.get_json()
        game_id = data.get('game_id')
        player_id = data.get('player_id')
        
        print(f"[START_TURN] Called for game {game_id} (type={type(game_id)}), player {player_id} (type={type(player_id)})")

        if not game_id or not player_id:
            return jsonify({'success': False, 'message': 'Missing game_id or player_id'}), 400

        game = Game.query.get(game_id)
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
            print(f"[START_TURN] Returning game_start notification for player {player_id}")
            return jsonify({
                'success': True,
                'auto_fill': None,
                'opponent_turn_summary': opponent_turn_summary,
                'forced_deal_notification': None
            })

        # Check if it's actually this player's turn (for normal turn processing)
        print(f"[START_TURN] Checking turn: game.turn_player_id={game.turn_player_id} (type={type(game.turn_player_id)}), player_id={player_id} (type={type(player_id)})")
        if game.turn_player_id != player_id:
            print(f"[START_TURN] Turn mismatch: game.turn_player_id={game.turn_player_id}, player_id={player_id}")
            return jsonify({'success': False, 'message': 'Not your turn'}), 400

        print(f"[START_TURN] Turn check passed, calling _check_and_fill_minimum_cards")
        
        # Check if ceasefire should end
        ceasefire_ended = _check_and_update_ceasefire(game)
        
        # Check and fill minimum cards
        fill_info = _check_and_fill_minimum_cards(game, player)
        
        print(f"[START_TURN] Fill info: {fill_info}, Ceasefire ended: {ceasefire_ended}")
        
        # Get opponent's last turn summary (includes Forced Deal card details if applicable)
        opponent_turn_summary = _get_opponent_turn_summary(game, player_id)

        return jsonify({
            'success': True,
            'auto_fill': fill_info,  # None if no fill needed, otherwise dict with fill details
            'opponent_turn_summary': opponent_turn_summary,  # Summary of what opponent did (includes Forced Deal cards)
            'ceasefire_ended': ceasefire_ended  # True if ceasefire just ended
        })

    except Exception as e:
        print(f"[START_TURN] Exception occurred: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'message': f'An error occurred: {str(e)}'}), 400


@games.route('/create_game', methods=['POST'])
def create_game():
    try:
        challenge_id = request.form.get('challenge_id')
        challenge = Challenge.query.get(challenge_id)

        if not challenge:
            return jsonify({'success': False, 'message': 'Challenge not found'}), 400

        # Get the users from the challenge
        user1 = User.query.get(challenge.challenger_id)
        user2 = User.query.get(challenge.challenged_id)

        if not user1 or not user2:
            return jsonify({'success': False, 'message': 'One or both players do not exist'}), 400

        # Create a new Game instance
        game = Game(
            current_round=1, 
            invader_player_id=None,
            ceasefire_active=True,
            ceasefire_start_turn=0
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
                    produces={'villager_red': 2, 'warrior_red': 1},
                    requires={}
                )
                db.session.add(figure)
                #db.session.flush() ##


                game.invader_player_id = player.id
                game.turn_player_id = player.id
                # Invader gets fewer turns than defender
                player.turns_left = settings.INITIAL_TURNS_INVADER

            else:
                print("Himalaya Maharaja")
                print(maharaja_card.suit)
                print(player.id)
                print(game.id)
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
                    produces={'villager_black': 2, 'warrior_black': 1},
                    requires={}
                )
                print(figure)
                db.session.add(figure)
                print("created figure")
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

        return jsonify({
            'success': True,
            'message': 'Game created successfully',
            'game': game.serialize()
        })

    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to create game: {str(e)}'}), 400


@games.route('/delete_game', methods=['POST'])
def delete_game():
    try:
        game_id = request.form.get('game_id')
        game = Game.query.options(joinedload('players').joinedload('main_hand')).get(game_id)

        # Delete all related cards (main and side)
        cards = MainCard.query.filter_by(game_id=game.id).all()
        for card in cards:
            db.session.delete(card)

        cards = SideCard.query.filter_by(game_id=game.id).all()
        for card in cards:
            db.session.delete(card)

        # Delete all related players
        for player in game.players:
            db.session.delete(player)

        # Finally, delete the game itself
        db.session.delete(game)

        # Commit the changes to the database
        db.session.commit()
    except Exception as e:
        return jsonify({'success': False, 'message': 'An error occurred: {}'.format(str(e))}), 400

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
        return jsonify({'success': False, 'message': 'An error occurred: {}'.format(str(e))}), 400


@games.route('/draw_cards', methods=['POST'])
def draw_cards():
    try:
        game_id = request.form.get('game_id')
        player_id = request.form.get('player_id')
        card_type = request.form.get('card_type', 'main')  # 'main' or 'side'
        num_cards = int(request.form.get('num_cards', 1))  # Number of cards to draw

        game = Game.query.get(game_id)
        player = Player.query.get(player_id)

        if not game or not player:
            return jsonify({'success': False, 'message': 'Invalid game or player'}), 400

        # Draw cards using DeckManager
        #from game_service.deck import DeckManager
        cards = DeckManager.draw_cards_from_deck(game, player, num_cards, card_type)
        return jsonify({
            'success': True,
            'message': 'Successfully drew cards',
            'cards': [card.serialize() for card in cards]
        })

    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to draw cards, Error: {str(e)}'}), 400


@games.route('/return_cards', methods=['POST'])
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

        # Return the cards using DeckManager
        #from game_service.deck import DeckManager
        DeckManager.return_cards_to_deck(cards)
        return jsonify({
            'success': True,
            'message': 'Cards successfully returned to the deck'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to return cards, Error: {str(e)}'}), 400
    
@games.route('/change_cards', methods=['POST'])
def change_cards():
    try:
        data = request.json
        game_id = data['game_id']
        player_id = data['player_id']
        card_ids = [card['id'] for card in data['cards']]
        card_type = data.get('card_type', 'main')  # Default to main cards

        print(f"Changing {card_type} cards for player {player_id} in game {game_id}")
        print(f"Selected card IDs: {card_ids}")
        
        # Handle MainCards or SideCards based on card_type
        if card_type == "main":
            selected_cards = MainCard.query.filter(MainCard.id.in_(card_ids)).all()
            new_cards = DeckManager.draw_cards_from_deck(Game.query.get(game_id), Player.query.get(player_id), len(card_ids), "main")
        elif card_type == "side":
            selected_cards = SideCard.query.filter(SideCard.id.in_(card_ids)).all()
            new_cards = DeckManager.draw_cards_from_deck(Game.query.get(game_id), Player.query.get(player_id), len(card_ids), "side")
        else:
            return jsonify({'success': False, 'message': 'Invalid card type specified'}), 400

        # Return the selected cards to the deck
        DeckManager.return_cards_to_deck(selected_cards)

        # Update turns left for the player
        player = Player.query.get(player_id)
        player.turns_left -= 1

        # flip turn player id
        game = Game.query.get(game_id)
        if game.turn_player_id == player_id:
            game.turn_player_id = game.players[0].id if game.players[0].id != player_id else game.players[1].id
        
        # Create log entry
        from models import User, LogEntry
        user = User.query.get(player.user_id)
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
        return jsonify({'success': False, 'message': f"Failed to change cards: {str(e)}"}), 400


@games.route('/discard_cards', methods=['POST'])
def discard_cards():
    """Discard cards when player has too many (return to deck without drawing new ones)."""
    try:
        data = request.json
        game_id = data['game_id']
        player_id = data['player_id']
        card_ids = [card['id'] for card in data['cards']]
        card_type = data.get('card_type', 'main')  # Default to main cards
        card_ranks = [card['rank'] for card in data['cards']]

        print(f"Discarding {card_type} cards for player {player_id} in game {game_id}")
        print(f"Selected card IDs: {card_ids}")
        
        # Side card ranks are 2-6, main card ranks are 7-A
        side_card_ranks = ['2', '3', '4', '5', '6']
        
        # Fetch cards based on rank (to avoid ID collision between tables)
        selected_cards = []
        for card_id, card_rank in zip(card_ids, card_ranks):
            if card_rank in side_card_ranks:
                card = SideCard.query.get(card_id)
            else:
                card = MainCard.query.get(card_id)
            
            if card:
                selected_cards.append(card)
        
        if len(selected_cards) != len(card_ids):
            return jsonify({'success': False, 'message': 'Some cards not found'}), 400

        # Return the selected cards to the deck (no drawing new ones)
        DeckManager.return_cards_to_deck(selected_cards)

        db.session.commit()

        return jsonify({'success': True})

    except Exception as e:
        return jsonify({'success': False, 'message': f"Failed to discard cards: {str(e)}"}), 400


@games.route('/update_points', methods=['POST'])
def update_points():
    try:
        data = request.json
        player_id = data['player_id']
        points = data['points']

        player = Player.query.get(player_id)
        if not player:
            return jsonify({'success': False, 'message': 'Player not found'}), 400

        player.points += points
        db.session.commit()

        return jsonify({'success': True, 'points': player.points})

    except Exception as e:
        return jsonify({'success': False, 'message': f"Failed to update points: {str(e)}"}), 400


@games.route('/advance_figure', methods=['POST'])
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

        game = Game.query.get(game_id)
        if not game:
            return jsonify({'success': False, 'message': 'Game not found'}), 404

        player = Player.query.get(player_id)
        if not player:
            return jsonify({'success': False, 'message': 'Player not found'}), 404

        # Validate it's this player's turn
        if game.turn_player_id != player_id:
            return jsonify({'success': False, 'message': 'Not your turn'}), 400

        # Clear stale fold/battle decision state from previous battle phase
        if game.fold_outcome or game.battle_confirmed or game.battle_decisions:
            game.fold_outcome = None
            game.fold_winner_id = None
            game.battle_confirmed = False
            game.battle_decisions = None

        # Validate ceasefire is not active
        if game.ceasefire_active:
            return jsonify({'success': False, 'message': 'Cannot advance during ceasefire'}), 400

        # Validate figure belongs to this player
        figure = Figure.query.get(figure_id)
        if not figure or figure.player_id != player_id:
            return jsonify({'success': False, 'message': 'Figure not found or not yours'}), 400

        # Check battle modifiers
        modifiers = game.battle_modifier if isinstance(game.battle_modifier, list) else []
        has_civil_war = any(m.get('type') == 'Civil War' for m in modifiers)
        has_blitzkrieg = any(m.get('type') == 'Blitzkrieg' for m in modifiers)

        # Determine if this is a counter-advance (opponent already advanced)
        is_counter_advance = (game.advancing_figure_id is not None and 
                              game.advancing_player_id != player_id)

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
                    first_figure = Figure.query.get(game.defending_figure_id)
                    if first_figure and first_figure.color != figure.color:
                        return jsonify({'success': False, 'message': 'Second figure must be the same color as the first'}), 400
                    game.defending_figure_id_2 = figure_id
                    is_second_pick = True
                else:
                    # First counter-advance pick
                    game.defending_figure_id = figure_id
                    # Check if there's another eligible village figure of same color
                    eligible_seconds = Figure.query.filter(
                        Figure.player_id == player_id,
                        Figure.id != figure_id,
                        Figure.field == 'village',
                        Figure.color == figure.color
                    ).all()
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
                    first_figure = Figure.query.get(game.advancing_figure_id)
                    if first_figure and first_figure.color != figure.color:
                        return jsonify({'success': False, 'message': 'Second figure must be the same color as the first'}), 400
                    game.advancing_figure_id_2 = figure_id
                    is_second_pick = True
                else:
                    # First advance pick
                    game.advancing_figure_id = figure_id
                    game.advancing_player_id = player_id
                    # Check if there's another eligible village figure of same color
                    eligible_seconds = Figure.query.filter(
                        Figure.player_id == player_id,
                        Figure.id != figure_id,
                        Figure.field == 'village',
                        Figure.color == figure.color
                    ).all()
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
        if civil_war_need_second:
            # Don't flip turn — player needs to pick a second figure
            print(f"[ADVANCE] Civil War — waiting for second figure pick (color: {civil_war_color})")
        elif has_blitzkrieg and not is_counter_advance:
            # Blitzkrieg: invader keeps the turn, goes to defender selection immediately
            print(f"[ADVANCE] Blitzkrieg active — turn stays with invader for defender selection")
        else:
            # Normal: flip turn to opponent (advance does NOT consume a turn)
            other_player = game.players[0] if game.players[0].id != player_id else game.players[1]
            game.turn_player_id = other_player.id

        # Create log entry
        user = User.query.get(player.user_id)
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
        return jsonify({'success': False, 'message': f"Failed to advance figure: {str(e)}"}), 400


@games.route('/select_defender', methods=['POST'])
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

        game = Game.query.get(game_id)
        if not game:
            return jsonify({'success': False, 'message': 'Game not found'}), 404

        # There must be an active advance
        if not game.advancing_figure_id:
            return jsonify({'success': False, 'message': 'No advancing figure in play'}), 400

        # The caller must be the advancing player (they pick the opponent's defender)
        if game.advancing_player_id != player_id:
            return jsonify({'success': False, 'message': 'Only the advancing player can select the defender'}), 400

        # Validate figure belongs to the OPPONENT (not the advancing player)
        figure = Figure.query.get(figure_id)
        if not figure:
            return jsonify({'success': False, 'message': 'Figure not found'}), 400
        if figure.player_id == player_id:
            return jsonify({'success': False, 'message': 'You must select an opponent\'s figure, not your own'}), 400
        
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
                first_defender = Figure.query.get(game.defending_figure_id)
                if first_defender and first_defender.color != figure.color:
                    return jsonify({'success': False, 'message': 'Second defender must be the same color as the first'}), 400
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
        return jsonify({'success': False, 'message': f"Failed to select defender: {str(e)}"}), 400


@games.route('/skip_civil_war_second', methods=['POST'])
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

        game = Game.query.get(game_id)
        if not game:
            return jsonify({'success': False, 'message': 'Game not found'}), 404

        player = Player.query.get(player_id)
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
        user = User.query.get(player.user_id)
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

        print(f"[CIVIL_WAR] {username} skipped second pick ({context}). Turn flipped.")

        return jsonify({
            'success': True,
            'game': game.serialize()
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f"Failed to skip: {str(e)}"}), 400


@games.route('/cannot_advance_loss', methods=['POST'])
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

        game = Game.query.get(game_id)
        if not game:
            return jsonify({'success': False, 'message': 'Game not found'}), 404

        player = Player.query.get(player_id)
        if not player:
            return jsonify({'success': False, 'message': 'Player not found'}), 404

        # Validate it's this player's turn
        if game.turn_player_id != player_id:
            return jsonify({'success': False, 'message': 'Not your turn'}), 400

        # Get player info for logging
        user = User.query.get(player.user_id)
        username = user.username if user else f"Player {player_id}"

        # Get opponent
        opponent = next((p for p in game.players if p.id != player_id), None)
        opponent_user = User.query.get(opponent.user_id) if opponent else None
        opponent_name = opponent_user.username if opponent_user else "Opponent"

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

        # Clear battle state
        game.advancing_figure_id = None
        game.advancing_figure_id_2 = None
        game.advancing_player_id = None
        game.defending_figure_id = None
        game.defending_figure_id_2 = None
        game.battle_modifier = []
        game.battle_decisions = None
        game.battle_confirmed = False
        # Set fold outcome so opponent detects it via polling
        game.fold_outcome = 'fold_win'
        game.fold_winner_id = opponent.id

        # Start new round — swap invader role
        old_invader_id = game.invader_player_id
        new_invader = next((p for p in game.players if p.id != old_invader_id), None)
        if new_invader:
            game.invader_player_id = new_invader.id

        # Reset turns for both players
        for p in game.players:
            if p.id == game.invader_player_id:
                p.turns_left = settings.INITIAL_TURNS_INVADER
            else:
                p.turns_left = settings.INITIAL_TURNS_DEFENDER

        # Increment round
        game.current_round += 1

        # Set turn to new invader
        game.turn_player_id = game.invader_player_id

        # Ceasefire starts at beginning of each new round (3 invader turns)
        game.ceasefire_active = True
        game.ceasefire_start_turn = 0

        db.session.commit()

        print(f"[AUTO_LOSS] {username} cannot advance — loses battle. Round {game.current_round} starts. New invader: {game.invader_player_id}")

        return jsonify({
            'success': True,
            'loser': username,
            'winner': opponent_name,
            'points': 10,
            'game': game.serialize()
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f"Failed to process auto-loss: {str(e)}"}), 400


@games.route('/defender_no_figures_loss', methods=['POST'])
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

        game = Game.query.get(game_id)
        if not game:
            return jsonify({'success': False, 'message': 'Game not found'}), 404

        player = Player.query.get(player_id)
        if not player:
            return jsonify({'success': False, 'message': 'Player not found'}), 404

        # Validate it's this player's turn (the invader)
        if game.turn_player_id != player_id:
            return jsonify({'success': False, 'message': 'Not your turn'}), 400

        # Validate this is the advancing player
        if game.advancing_player_id != player_id:
            return jsonify({'success': False, 'message': 'Only the advancing player can report this'}), 400

        # Get invader info
        user = User.query.get(player.user_id)
        username = user.username if user else f"Player {player_id}"

        # Get defender (opponent) info
        opponent = next((p for p in game.players if p.id != player_id), None)
        opponent_user = User.query.get(opponent.user_id) if opponent else None
        opponent_name = opponent_user.username if opponent_user else "Opponent"

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

        # Clear battle state
        game.advancing_figure_id = None
        game.advancing_figure_id_2 = None
        game.advancing_player_id = None
        game.defending_figure_id = None
        game.defending_figure_id_2 = None
        game.battle_modifier = []
        game.battle_decisions = None
        game.battle_confirmed = False
        # Set fold outcome so opponent detects it via polling
        game.fold_outcome = 'fold_win'
        game.fold_winner_id = player.id

        # Start new round — swap invader role
        old_invader_id = game.invader_player_id
        new_invader = next((p for p in game.players if p.id != old_invader_id), None)
        if new_invader:
            game.invader_player_id = new_invader.id

        # Reset turns for both players
        for p in game.players:
            if p.id == game.invader_player_id:
                p.turns_left = settings.INITIAL_TURNS_INVADER
            else:
                p.turns_left = settings.INITIAL_TURNS_DEFENDER

        # Increment round
        game.current_round += 1

        # Set turn to new invader
        game.turn_player_id = game.invader_player_id

        # Ceasefire starts at beginning of each new round
        game.ceasefire_active = True
        game.ceasefire_start_turn = 0

        db.session.commit()

        print(f"[DEFENDER_NO_FIGURES] {opponent_name} has no valid figures — loses battle. Round {game.current_round} starts. New invader: {game.invader_player_id}")

        return jsonify({
            'success': True,
            'loser': opponent_name,
            'winner': username,
            'points': 10,
            'game': game.serialize()
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f"Failed to process defender auto-loss: {str(e)}"}), 400


@games.route('/battle_decision', methods=['POST'])
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

        game = Game.query.get(game_id)
        if not game:
            return jsonify({'success': False, 'message': 'Game not found'}), 404

        player = Player.query.get(player_id)
        if not player:
            return jsonify({'success': False, 'message': 'Player not found'}), 404

        is_advancing = (player_id == game.advancing_player_id)
        decisions = dict(game.battle_decisions) if game.battle_decisions else {}

        # Get player info
        user = User.query.get(player.user_id)
        username = user.username if user else f"Player {player_id}"
        opponent = next((p for p in game.players if p.id != player_id), None)
        opponent_user = User.query.get(opponent.user_id) if opponent else None
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
                print(f"[BATTLE_DECISION] {username} (invader) chose to fight. Waiting for defender.")
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
                invader_player = Player.query.get(game.advancing_player_id)
                invader_user = User.query.get(invader_player.user_id)
                winner_name = invader_user.username if invader_user else "Invader"
                loser_name = username
                return _resolve_fold(game, invader_player, player, winner_name, loser_name)
            else:
                # Both chose to fight — proceed to battle
                game.battle_confirmed = True
                game.battle_decisions = None

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
                print(f"[BATTLE_DECISION] Both players chose battle. Proceeding to battle screen.")
                return jsonify({
                    'success': True,
                    'resolved': True,
                    'outcome': 'battle',
                    'game': game.serialize()
                })

    except Exception as e:
        db.session.rollback()
        print(f"[BATTLE_DECISION] Error: {str(e)}")
        return jsonify({'success': False, 'message': f"Failed to process battle decision: {str(e)}"}), 400


def _resolve_fold(game, winner_player, loser_player, winner_name, loser_name):
    """Helper to resolve a fold: award points, reset round, start ceasefire."""
    # Award points to winner
    winner_player.points += 10

    game.battle_decisions = None
    game.fold_outcome = 'fold_win'
    game.fold_winner_id = winner_player.id

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

    # Clear battle state
    game.advancing_figure_id = None
    game.advancing_figure_id_2 = None
    game.advancing_player_id = None
    game.defending_figure_id = None
    game.defending_figure_id_2 = None
    game.battle_modifier = []
    game.battle_confirmed = False

    # Winner becomes invader
    game.invader_player_id = winner_player.id

    # Round increases, turns reset, ceasefire starts
    game.current_round += 1
    for p in game.players:
        if p.id == game.invader_player_id:
            p.turns_left = settings.INITIAL_TURNS_INVADER
        else:
            p.turns_left = settings.INITIAL_TURNS_DEFENDER
    game.turn_player_id = game.invader_player_id
    game.ceasefire_active = True
    game.ceasefire_start_turn = 0

    db.session.commit()
    print(f"[BATTLE_DECISION] {loser_name} folded. {winner_name} wins 10 points. Round {game.current_round} starts. New invader: {winner_player.id}")

    return jsonify({
        'success': True,
        'resolved': True,
        'outcome': 'fold_win',
        'winner': winner_name,
        'loser': loser_name,
        'points': 10,
        'game': game.serialize()
    })
