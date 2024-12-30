from flask import Blueprint, request, jsonify
from sqlalchemy.orm import joinedload
import random
from models import db, User, Challenge, Player, Game, MainCard, SideCard, Figure, CardToFigure
from game_service.deck_manager import DeckManager

import server_settings as settings

games = Blueprint('games', __name__)

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
                    color="offensive",
                    name="Djungle Maharaja",
                    suit=maharaja_card.suit.value,
                    description="Djungle maharaja",
                    upgrade_family_name=None
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
                    color="defensive",
                    name="Himalya Maharaja",
                    suit=maharaja_card.suit.value,
                    description="Himalaya maharaja",
                    upgrade_family_name=None
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
        db.session.commit()

        # flip turn player id
        game = Game.query.get(game_id)
        if game.turn_player_id == player_id:
            game.turn_player_id = game.players[0].id if game.players[0].id != player_id else game.players[1].id
            db.session.commit()
        

        return jsonify({'success': True, 'new_cards': [card.serialize() for card in new_cards], 'turns_left': player.turns_left})

    except Exception as e:
        return jsonify({'success': False, 'message': f"Failed to change cards: {str(e)}"}), 400


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


