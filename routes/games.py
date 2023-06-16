from flask import Blueprint, request, jsonify
from sqlalchemy.orm import joinedload
from models import db, User, Challenge, Player, Game, Card
from deck_storage import game_decks
from Deck import Deck
#import settings

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

        # Call game_service functions here
        deck = Deck(game)
        deck.create()
        deck.shuffle()
        deck.deal_cards([player1, player2])
        game_decks[game.id] = deck
        #game_service.create_deck(game)  # Creates a deck for the game
        #game_service.deal_cards(game)  # Deals cards to the players

    except Exception as e:
        # In case there is an exception while adding the challenge
        return jsonify({'success': False, 'message': f'Failed to create game, Error: {str(e)}'}), 400

    return jsonify({'success': True,
                    'message': 'Game created successfully',
                    'game': game.serialize()})


@games.route('/delete_game', methods=['POST'])
def delete_game():
    try:
        game_id = request.form.get('game_id')
        game = Game.query.options(joinedload('players').joinedload('hand')).get(game_id)

        # Delete all related cards
        for player in game.players:
            for card in player.hand:
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

        cards = Card.query.filter_by(player_id=player_id).all()
        return jsonify({'success': True, 'message': 'successfully loaded hand', 'hand': [card.serialize() for card in cards]})
    except Exception as e:
        return jsonify({'success': False, 'message': 'An error occurred: {}'.format(str(e))}), 400
"""



# Assuming `game_id` is the ID of the game you want to delete
game = Game.query.options(joinedload('players').joinedload('hand')).get(game_id)

# Delete all related cards
for player in game.players:
    for card in player.hand:
        db.session.delete(card)

# Delete all related players
for player in game.players:
    db.session.delete(player)

# Finally, delete the game itself
db.session.delete(game)

# Commit the changes to the database
db.session.commit()
"""