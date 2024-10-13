from flask import Blueprint, request, jsonify
from sqlalchemy.orm import joinedload
from models import db, User, Challenge, Player, Game, MainCard, SideCard
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

        games = Game.query.join(Player).filter(
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
        game = Game()
        db.session.add(game)
        db.session.commit()

        # Create new Player instances for the users
        player1 = Player(user_id=user1.id, game_id=game.id)
        player2 = Player(user_id=user2.id, game_id=game.id)
        db.session.add(player1)
        db.session.add(player2)
        db.session.commit()

        # Create and shuffle deck, and deal cards using DeckManager
        #from game_service.deck import DeckManager
        DeckManager.create_and_shuffle_deck(game)
        DeckManager.deal_cards_to_players(game, [player1, player2], 
            num_main_cards=settings.NUM_MAIN_CARDS_START, 
            num_side_cards=settings.NUM_SIDE_CARDS_START)

    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to create game, Error: {str(e)}'}), 400

    return jsonify({
        'success': True,
        'message': 'Game created successfully',
        'game': game.serialize()
    })


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
