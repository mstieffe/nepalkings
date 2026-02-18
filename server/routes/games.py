from flask import Blueprint, request, jsonify
from sqlalchemy.orm import joinedload
import random
from models import db, User, Challenge, Player, Game, MainCard, SideCard, Figure, CardToFigure
from game_service.deck_manager import DeckManager

import server_settings as settings

games = Blueprint('games', __name__)

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
        
        # Check if spell affects current player
        if spell_name == 'Forced Deal':
            action_data['affects_player'] = True
            action_data['details'] = 'Cards were exchanged'
        
        elif spell_name == 'Dump Cards':
            action_data['affects_player'] = True
            action_data['details'] = 'All hands were dumped'
        
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

def _get_forced_deal_notification(game, current_player_id):
    """
    Check if there's a pending Forced Deal notification for the current player.
    Returns card swap details if found, otherwise None.
    """
    from models import ActiveSpell
    
    print(f"[FORCED_DEAL_NOTIF] Checking for notification for player {current_player_id}")
    
    # Look for recent Forced Deal spells in this round that have notification_pending flag
    forced_deal_spells = ActiveSpell.query.filter(
        ActiveSpell.game_id == game.id,
        ActiveSpell.spell_name.like('%Forced Deal%'),
        ActiveSpell.cast_round == game.current_round,
        ActiveSpell.player_id != current_player_id  # Cast by opponent
    ).order_by(ActiveSpell.id.desc()).all()
    
    for spell in forced_deal_spells:
        if spell.effect_data and isinstance(spell.effect_data, dict):
            # Check if notification is pending for this player
            if spell.effect_data.get('notification_pending') and spell.effect_data.get('opponent_id') == current_player_id:
                print(f"[FORCED_DEAL_NOTIF] Found pending notification for spell {spell.id}")
                
                # Get the swap details for this player (opponent perspective)
                notification = {
                    'cards_given': spell.effect_data.get('opponent_gave', []),
                    'cards_received': spell.effect_data.get('opponent_received', []),
                    'caster_name': None
                }
                
                # Get caster name
                for player in game.players:
                    if player.id == spell.player_id:
                        notification['caster_name'] = player.serialize()['username']
                        break
                
                # Clear the notification flag
                spell.effect_data['notification_pending'] = False
                db.session.commit()
                
                print(f"[FORCED_DEAL_NOTIF] Returning notification: {notification}")
                return notification
    
    print(f"[FORCED_DEAL_NOTIF] No pending notification found")
    return None

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
        
        # Check and fill minimum cards
        fill_info = _check_and_fill_minimum_cards(game, player)
        
        print(f"[START_TURN] Fill info: {fill_info}")
        
        # Get opponent's last turn summary for normal turn processing
        opponent_turn_summary = _get_opponent_turn_summary(game, player_id)
        
        # Check for pending Forced Deal notification
        forced_deal_notification = _get_forced_deal_notification(game, player_id)

        return jsonify({
            'success': True,
            'auto_fill': fill_info,  # None if no fill needed, otherwise dict with fill details
            'opponent_turn_summary': opponent_turn_summary,  # Summary of what opponent did
            'forced_deal_notification': forced_deal_notification  # Specific cards swapped in Forced Deal
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
        game = Game(current_round=1, invader_player_id=None)  # Initialize the round and invader
        db.session.add(game)
        db.session.commit()

        # Create new Player instances for the users
        player1 = Player(user_id=user1.id, game_id=game.id, turns_left=settings.INITIAL_TURNS, points=0)
        player2 = Player(user_id=user2.id, game_id=game.id, turns_left=settings.INITIAL_TURNS, points=0)
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


