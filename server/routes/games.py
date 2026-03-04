from flask import Blueprint, request, jsonify
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.attributes import flag_modified
import random
from models import db, User, Challenge, Player, Game, MainCard, SideCard, Figure, CardToFigure, LogEntry, BattleMove, ActiveSpell
from game_service.deck_manager import DeckManager

import server_settings as settings

games = Blueprint('games', __name__)

def _check_and_update_ceasefire(game):
    """
    Check if ceasefire should end and update game state accordingly.
    Universal rule: ceasefire always ends when the invader has <= 1 turn left
    (so forced advance can trigger at turns_left == 1).
    Normal ceasefire also has a 3-invader-turns duration limit.
    Returns True if ceasefire ended this check.
    """
    if not game.ceasefire_active:
        return False
    
    # Universal ceasefire end: invader is on their last turn and needs to advance
    invader = Player.query.get(game.invader_player_id)
    if invader and invader.turns_left <= 1:
        print(f"[CEASEFIRE] Ceasefire ending (invader has {invader.turns_left} turn(s) left — must advance)")
        game.ceasefire_active = False
        game.ceasefire_start_turn = None
        db.session.commit()
        return True
    
    # Blitzkrieg ceasefire: handled by universal check above
    modifiers = game.battle_modifier if isinstance(game.battle_modifier, list) else []
    has_blitzkrieg = any(m.get('type') == 'Blitzkrieg' for m in modifiers)
    if has_blitzkrieg:
        # Blitzkrieg ceasefire stays active until universal check fires
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

        # Check resource deficit — figures with deficit cannot advance or counter-advance
        if _check_figure_resource_deficit(figure, player_id, game.id):
            return jsonify({'success': False, 'message': 'This figure has a resource deficit and cannot advance toward battle.', 'reason': 'resource_deficit'}), 400

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

        if civil_war_need_second:
            # Don't flip turn — player needs to pick a second figure
            print(f"[ADVANCE] Civil War — waiting for second figure pick (color: {civil_war_color})")
        elif has_blitzkrieg and not is_counter_advance:
            # Blitzkrieg: invader keeps the turn, goes to defender selection immediately
            print(f"[ADVANCE] Blitzkrieg active — turn stays with invader for defender selection")
        else:
            # Normal: flip turn to opponent
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

        # Check if the selected defender has a resource deficit.
        # The invader can pick deficit figures (can't tell if it's a bluff),
        # but if the figure truly has a deficit, the defender auto-loses.
        defender_owner_id = figure.player_id
        if _check_figure_resource_deficit(figure, defender_owner_id, game.id):
            # Defender's figure has a deficit — defender auto-loses the battle
            invader_player = Player.query.get(player_id)
            defender_player = Player.query.get(defender_owner_id)
            invader_user = User.query.get(invader_player.user_id)
            defender_user = User.query.get(defender_player.user_id)
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


def _check_figure_resource_deficit(figure, player_id, game_id):
    """Check if a figure has a resource deficit (requires more than produced by the player's figures)."""
    if not figure.requires:
        return False

    # Calculate total produces and requires across ALL of this player's figures
    all_figures = Figure.query.filter_by(player_id=player_id, game_id=game_id).all()
    total_produces = {}
    total_requires = {}
    for fig in all_figures:
        if fig.produces:
            for res, amount in fig.produces.items():
                total_produces[res] = total_produces.get(res, 0) + amount
        if fig.requires:
            for res, amount in fig.requires.items():
                total_requires[res] = total_requires.get(res, 0) + amount

    # Check if any resource THIS figure requires is in deficit
    for resource_name in figure.requires:
        total_req = total_requires.get(resource_name, 0)
        total_prod = total_produces.get(resource_name, 0)
        if total_req > total_prod:
            return True
    return False


def _resolve_deficit_loss(game, winner_player, loser_player, winner_name, loser_name, figure_name):
    """Resolve an auto-loss due to a figure having resource deficit in battle."""
    winner_player.points += 10

    game.battle_decisions = None
    game.fold_outcome = 'fold_win'
    game.fold_winner_id = winner_player.id

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
    print(f"[DEFICIT_LOSS] {loser_name}'s {figure_name} has resource deficit. {winner_name} wins 10 points. Round {game.current_round} starts.")

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


# ────────────────────── battle resolution ─────────────────────────

def _compute_figure_base_power(figure):
    """Compute a figure's base power on the server side.

    Castle figures (Maharaja / King) always return 15.
    All others return the sum of their card values.
    """
    if figure.field == 'castle':
        return 15
    card_assocs = CardToFigure.query.filter_by(figure_id=figure.id).all()
    total = 0
    for assoc in card_assocs:
        if assoc.card_type == 'main':
            card = MainCard.query.get(assoc.card_id)
        else:
            card = SideCard.query.get(assoc.card_id)
        if card:
            total += card.value
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
            card = SideCard.query.get(bm.card_id)
        else:
            card = MainCard.query.get(bm.card_id)
        if card:
            cards.append((card, bm.card_type))

        # Second card (Double Dagger)
        if bm.card_id_b is not None:
            ct_b = bm.card_type_b or 'main'
            if ct_b == 'side':
                card_b = SideCard.query.get(bm.card_id_b)
            else:
                card_b = MainCard.query.get(bm.card_id_b)
            if card_b:
                cards.append((card_b, ct_b))
    return cards, moves


def _destroy_figure_and_collect_cards(figure):
    """Delete a figure and return its cards as a list of (card_obj, type_str).

    Does NOT return cards to deck yet — caller decides what happens with them.
    """
    card_assocs = CardToFigure.query.filter_by(figure_id=figure.id).all()
    cards = []
    for assoc in card_assocs:
        if assoc.card_type == 'main':
            card = MainCard.query.get(assoc.card_id)
        else:
            card = SideCard.query.get(assoc.card_id)
        if card:
            card.part_of_figure = False
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
    game.battle_round = 0
    game.battle_turn_player_id = None
    game.battle_skipped_rounds = None


def _deactivate_all_spells(game):
    """Deactivate all active spells in a game (post-battle cleanup)."""
    active = ActiveSpell.query.filter_by(game_id=game.id, is_active=True).all()
    for spell in active:
        spell.is_active = False


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

    # Draw 2 side cards per player for the new round
    drawn_cards_map = {}
    for p in game.players:
        try:
            cards = DeckManager.draw_cards_from_deck(game, p, 2, 'side')
            drawn_cards_map[str(p.id)] = [
                {'suit': c.suit.value, 'rank': c.rank.value}
                for c in cards
            ]
            print(f"[NEW_ROUND] Player {p.id} drew 2 side cards: {drawn_cards_map[str(p.id)]}")
        except ValueError:
            # Not enough side cards in deck
            drawn_cards_map[str(p.id)] = []
            print(f"[NEW_ROUND] Player {p.id}: no side cards available in deck")
    game.post_battle_drawn_cards = drawn_cards_map


# ─────────────────── 3-round battle turn management ───────────────────

@games.route('/play_battle_move', methods=['POST'])
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

    game = Game.query.get(game_id)
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
    move = BattleMove.query.get(battle_move_id)
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

    # Remove the card(s) from the player's hand so they can't be
    # accidentally sacrificed / auto-removed while the battle continues.
    # The card stays in the DB (in_deck=True) for post-battle resolution.
    if move.card_type == 'side':
        card = SideCard.query.get(move.card_id)
    else:
        card = MainCard.query.get(move.card_id)
    if card:
        card.in_deck = True

    # Double Dagger second card
    if move.card_id_b is not None:
        ct_b = move.card_type_b or 'main'
        if ct_b == 'side':
            card_b = SideCard.query.get(move.card_id_b)
        else:
            card_b = MainCard.query.get(move.card_id_b)
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
    player = Player.query.get(player_id)
    user = User.query.get(player.user_id) if player else None
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

    print(f"[BATTLE_MOVE] Player {player_id} played move {battle_move_id} "
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

    game = Game.query.get(game_id)
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

    game = Game.query.get(game_id)
    if not game:
        return jsonify({'success': False, 'message': 'Game not found'}), 404

    if not game.battle_confirmed:
        return jsonify({'success': False, 'message': 'Battle is not active'}), 400

    if game.battle_turn_player_id != player_id:
        return jsonify({'success': False, 'message': 'It is not your turn in the battle'}), 400

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
    player_obj = Player.query.get(player_id)
    user = User.query.get(player_obj.user_id) if player_obj else None
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

    print(f"[BATTLE_SKIP] Player {player_id} skipped round {skipped[pid_key][-1]}. "
          f"Next turn: {game.battle_turn_player_id}, battle_round: {game.battle_round}")

    return jsonify({
        'success': True,
        'battle_round': game.battle_round,
        'battle_turn_player_id': game.battle_turn_player_id,
        'battle_skipped_rounds': game.battle_skipped_rounds or {},
        'game': game.serialize(),
    })


@games.route('/finish_battle', methods=['POST'])
def finish_battle():
    """Resolve a 3-round battle and return result + returnable cards.

    Expects JSON: {
        game_id, player_id,
        player_played: [{id, family_name, value, ...}, ...],  # 3 played moves
        total_diff: int   # total power diff (positive = player wins)
    }

    The endpoint:
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
    total_diff = data.get('total_diff', 0)  # positive = player wins

    if not game_id or not player_id:
        return jsonify({'success': False, 'message': 'Missing game_id or player_id'}), 400

    game = Game.query.get(game_id)
    if not game:
        return jsonify({'success': False, 'message': 'Game not found'}), 404

    player = Player.query.filter_by(id=player_id, game_id=game_id).first()
    if not player:
        return jsonify({'success': False, 'message': 'Player not found'}), 404

    other_player = [p for p in game.players if p.id != player_id][0]

    # Idempotency: if battle was already resolved by the other client
    # (figures destroyed, fold_winner_id set), return the cached result.
    adv_figure = Figure.query.get(game.advancing_figure_id) if game.advancing_figure_id else None
    def_figure = Figure.query.get(game.defending_figure_id) if game.defending_figure_id else None

    if (not adv_figure or not def_figure) and game.fold_winner_id:
        print(f"[FINISH_BATTLE] Battle already resolved for game {game_id} (figure destroyed)")
        winner_id = game.fold_winner_id
        if winner_id == player_id:
            outcome = 'win'
        else:
            outcome = 'lose'

        # For winners, collect returnable cards (battle move + orphaned figure cards)
        returnable_cards = []
        if outcome == 'win':
            bm_cards, _ = _collect_battle_move_cards(game_id)
            orphaned_main = MainCard.query.filter_by(
                game_id=game_id, in_deck=False, part_of_figure=False, player_id=None
            ).all()
            orphaned_side = SideCard.query.filter_by(
                game_id=game_id, in_deck=False, part_of_figure=False, player_id=None
            ).all()
            all_cards = bm_cards + [(c, 'main') for c in orphaned_main] + [(c, 'side') for c in orphaned_side]
            returnable_cards = [_serialize_battle_card(c, ct) for c, ct in all_cards]

        other_user = User.query.get(other_player.user_id)
        other_name = other_user.username if other_user else f"Player {other_player.id}"
        player_user_inner = User.query.get(player.user_id)
        player_name_inner = player_user_inner.username if player_user_inner else f"Player {player_id}"

        return jsonify({
            'success': True,
            'outcome': outcome,
            'already_resolved': True,
            'winner_player_id': winner_id,
            'winner_name': player_name_inner if outcome == 'win' else other_name,
            'loser_name': other_name if outcome == 'win' else player_name_inner,
            'returnable_cards': returnable_cards,
            'game': game.serialize(),
        })

    if not adv_figure or not def_figure:
        return jsonify({'success': False, 'message': 'Battle figures not found'}), 400

    # Determine who the invader/defender is
    is_invader = (game.invader_player_id == player_id)

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
    winner_user = User.query.get(winner_player.user_id)
    loser_user = User.query.get(loser_player.user_id)
    winner_name = winner_user.username if winner_user else f"Player {winner_player.id}"
    loser_name = loser_user.username if loser_user else f"Player {loser_player.id}"

    player_user = User.query.get(player.user_id)
    player_name = player_user.username if player_user else f"Player {player_id}"

    # Collect battle move cards (from BOTH players)
    bm_cards, bm_records = _collect_battle_move_cards(game_id)

    if total_diff == 0:
        # ──── DRAW ────
        # Defender gets to choose: destroy opponent figure, 10 pts, or pick a card
        # Determine who the defender is
        defender_player_id = None
        for p in game.players:
            if p.id != game.invader_player_id:
                defender_player_id = p.id
                break

        # Serialize the battle move cards so the client can show them
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
        points_awarded = _compute_figure_base_power(loser_figure)
        winner_player.points += points_awarded

        # Destroy loser's figure — collect its cards
        figure_cards = _destroy_figure_and_collect_cards(loser_figure)

        # Clear the destroyed figure's reference on the game
        if game.advancing_figure_id and loser_figure.id == game.advancing_figure_id:
            game.advancing_figure_id = None
        if game.defending_figure_id and loser_figure.id == game.defending_figure_id:
            game.defending_figure_id = None

        db.session.flush()

        # All returnable cards = figure cards + battle move cards
        all_returnable = figure_cards + bm_cards
        returnable_cards = [_serialize_battle_card(c, ct) for c, ct in all_returnable]

        # Log
        log_entry = LogEntry(
            game_id=game.id,
            player_id=winner_player.id,
            round_number=game.current_round,
            turn_number=winner_player.turns_left,
            message=(
                f"{winner_name} wins the battle! {loser_name}'s "
                f"{loser_figure.name} is destroyed. "
                f"{winner_name} earns {points_awarded} points."
            ),
            author="System",
            type='battle_win'
        )
        db.session.add(log_entry)

        # Store the winner so the second client can retrieve the result
        game.fold_winner_id = winner_player.id

        db.session.commit()

        return jsonify({
            'success': True,
            'outcome': 'win',
            'winner_player_id': winner_player.id,
            'loser_player_id': loser_player.id,
            'winner_name': winner_name,
            'loser_name': loser_name,
            'points_awarded': points_awarded,
            'destroyed_figure_name': loser_figure.name,
            'total_diff': total_diff,
            'returnable_cards': returnable_cards,
            'game': game.serialize(),
        })


@games.route('/finish_battle_pick_card', methods=['POST'])
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

    game = Game.query.get(game_id)
    if not game:
        return jsonify({'success': False, 'message': 'Game not found'}), 404

    player = Player.query.filter_by(id=player_id, game_id=game_id).first()
    if not player:
        return jsonify({'success': False, 'message': 'Player not found'}), 404

    # Idempotency: if battle state was already cleaned up, just return success
    if not game.advancing_figure_id and not game.defending_figure_id and not game.battle_confirmed:
        print(f"[FINISH_BATTLE_PICK] Already cleaned up for game {game_id}, returning success")
        return jsonify({
            'success': True,
            'message': 'Battle already resolved.',
            'game': game.serialize(),
        })

    # Collect ALL battle move cards (in case finish_battle didn't return them yet)
    bm_cards, bm_records = _collect_battle_move_cards(game_id)

    # If winner picked a card, give it to them
    if picked_card_id:
        if picked_card_type == 'side':
            picked = SideCard.query.get(picked_card_id)
        else:
            picked = MainCard.query.get(picked_card_id)
        if picked and picked.game_id == game_id:
            picked.player_id = player_id
            picked.in_deck = False
            picked.part_of_figure = False
            picked.part_of_battle_move = False

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
    winner = Player.query.get(winner_id) if winner_id else player
    if not winner or winner.game_id != game_id:
        winner = player  # fallback

    # Clear battle state (this resets fold_winner_id to None)
    _clear_battle_state(game)

    # Start a new round — battle winner becomes invader
    _start_new_round(game, winner)

    db.session.commit()
    print(f"[FINISH_BATTLE] Card picked. Post-battle cleanup done. Round {game.current_round} starts. Winner/invader={winner.id}")

    return jsonify({
        'success': True,
        'message': 'Battle resolved. New round started.',
        'game': game.serialize(),
    })


@games.route('/finish_battle_draw', methods=['POST'])
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

    game = Game.query.get(game_id)
    if not game:
        return jsonify({'success': False, 'message': 'Game not found'}), 404

    player = Player.query.filter_by(id=player_id, game_id=game_id).first()
    if not player:
        return jsonify({'success': False, 'message': 'Player not found'}), 404

    other_player = [p for p in game.players if p.id != player_id][0]

    player_user = User.query.get(player.user_id)
    other_user = User.query.get(other_player.user_id)
    player_name = player_user.username if player_user else f"Player {player_id}"
    other_name = other_user.username if other_user else f"Player {other_player.id}"

    # Determine opponent's figure (the invader's figure, since player is defender)
    opponent_figure = Figure.query.get(game.advancing_figure_id) if game.advancing_figure_id else None

    result_msg = ""

    if choice == 'destroy':
        # Destroy the opponent's battle figure
        if opponent_figure:
            figure_name = opponent_figure.name
            figure_cards = _destroy_figure_and_collect_cards(opponent_figure)
            # Return figure cards to deck
            main_fc = [c for c, ct in figure_cards if isinstance(c, MainCard)]
            side_fc = [c for c, ct in figure_cards if isinstance(c, SideCard)]
            if main_fc:
                DeckManager.return_cards_to_deck(main_fc)
            if side_fc:
                DeckManager.return_cards_to_deck(side_fc)
            game.advancing_figure_id = None
            result_msg = f"{player_name} chose to destroy {other_name}'s {figure_name}!"
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
                picked = SideCard.query.get(picked_card_id)
            else:
                picked = MainCard.query.get(picked_card_id)
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

    # Return remaining battle-move cards to deck
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

    # Start a new round — defender (the choosing player) becomes invader
    _start_new_round(game, player)

    db.session.commit()
    print(f"[FINISH_BATTLE_DRAW] {result_msg} Round {game.current_round} starts.")

    return jsonify({
        'success': True,
        'outcome': 'draw',
        'choice': choice,
        'message': result_msg,
        'game': game.serialize(),
    })
