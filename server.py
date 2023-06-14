from flask import Flask, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Challenge, Player, Game
import settings

app = Flask(__name__)

# Configure the database URI
app.config['SQLALCHEMY_DATABASE_URI'] = settings.DB_URL
db.init_app(app)

with app.app_context():
    db.drop_all()

@app.route('/create_game', methods=['POST'])
def create_game():
    try:
        challenge_id = request.form.get('challenge_id')
        challenge = Challenge.query.get(challenge_id)

        if not challenge:
            return jsonify({'success': False, 'message': 'Challenge not found'})

        # Get the users from the challenge
        user1 = User.query.get(challenge.challenger_id)
        user2 = User.query.get(challenge.challenged_id)

        if not user1 or not user2:
            return jsonify({'success': False, 'message': 'One or both players do not exist'})

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

    except Exception as e:
        # In case there is an exception while adding the challenge
        return jsonify({'success': False, 'message': f'Failed to create game, Error: {str(e)}'})

    return jsonify({'success': True, 'message': 'Game created successfully'})

@app.route('/remove_challenge', methods=['POST'])
def remove_challenge():
    try:
        challenge_id = request.form.get('challenge_id')
        challenge = Challenge.query.filter_by(id=challenge_id).first()
        if not challenge:
            return jsonify({'success': False, 'message': 'Challenge not found'})

        db.session.delete(challenge)
        db.session.commit()
    except Exception as e:
        return jsonify({'success': False, 'message': f'Failed to remove challenge, Error: {str(e)}'})
    return jsonify({'success': True, 'message': 'Challenge removed'})


@app.route('/create_challenge', methods=['POST'])
def create_challenge():
    try:
        challenger = request.form.get('challenger')
        opponent = request.form.get('opponent')

        # Checking if the challenger and opponent are valid users
        challenger_user = User.query.filter_by(username=challenger).first()
        opponent_user = User.query.filter_by(username=opponent).first()

        if not challenger_user or not opponent_user:
            return jsonify({'success': False, 'message': 'Challenger or opponent does not exist'})

        # Creating a new challenge
        challenge = Challenge(challenger_id=challenger_user.id, challenged_id=opponent_user.id, status='open')

        db.session.add(challenge)
        db.session.commit()
    except Exception as e:
        # In case there is an exception while adding the challenge
        return jsonify({'success': False, 'message': f'Failed to create challenge, Error: {str(e)}'})

    return jsonify({'success': True, 'message': 'Challenge sent'})

@app.route('/open_challenges', methods=['GET'])
def open_challenges():
    try:
        username = request.args.get('username')
        user = User.query.filter_by(username=username).first()
        if not user:
            return jsonify({'success': False, 'error': 'User not found'})

        challenges = Challenge.query.filter(
            (Challenge.challenger_id == user.id) | (Challenge.challenged_id == user.id)).filter_by(status='open').all()

        #challenges = Challenge.query.filter((Challenge.challenger == user) | (Challenge.challenged == user)).filter_by(status='open').all()
        #challenges = Challenge.query.all()

        return jsonify({
            'challenges': [
                {'challenger': challenge.challenger.username,
                 'challenged': challenge.challenged.username,
                 'date': challenge.date,
                 'id': challenge.id}
                for challenge in challenges
            ]
        })
    except Exception as e:

        return jsonify({'success': False, 'message': 'An error occurred: {}'.format(str(e))})

@app.route('/get_games', methods=['GET'])
def get_games():
    try:
        username = request.args.get('username')
        user = User.query.filter_by(username=username).first()
        if not user:
            return jsonify({'success': False, 'error': 'User not found'})

        games = Game.query.filter(
            (Challenge.challenger_id == user.id) | (Challenge.challenged_id == user.id)).filter_by(status='open').all()

        #challenges = Challenge.query.filter((Challenge.challenger == user) | (Challenge.challenged == user)).filter_by(status='open').all()
        #challenges = Challenge.query.all()

        return jsonify({
            'games': [
                {'opponent': ???,
                 'date': game.date,
                 'id': game.id}
                for game in games
            ]
        })
    except Exception as e:

        return jsonify({'success': False, 'message': 'An error occurred: {}'.format(str(e))})

@app.route('/get_users', methods=['GET'])
def get_users():
    try:
        current_username = request.args.get('username')
        users = User.query.filter(User.username != current_username).all()

        return jsonify({'users': [user.username for user in users]})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/register', methods=['POST'])
def register():
    try:
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            return jsonify({'success': False, 'message': 'Missing username or password'})

        if User.query.filter_by(username=username).first():
            return jsonify({'success': False, 'message': 'Username already exists'})

        user = User(username=username, password_hash=generate_password_hash(password))
        db.session.add(user)
        db.session.commit()

        return jsonify({'success': True, 'message': 'Registration successful'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Registration failed, Error: {str(e)}'})

@app.route('/login', methods=['POST'])
def login():
    try:
        username = request.form.get('username')
        password = request.form.get('password')

        if not username or not password:
            return jsonify({'success': False, 'message': 'Missing username or password'})

        user = User.query.filter_by(username=username).first()

        if not user or not user.check_password(password):
            return jsonify({'success': False, 'message': 'Invalid username or password'})

        return jsonify({'success': True, 'message': 'Login successful'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Login failed, Error: {str(e)}'})

if __name__ == '__main__':
    try:
        with app.app_context():
            db.create_all()
        app.run(host='localhost', port=5000)
    except Exception as e:
        print(f'Application failed to start, Error: {str(e)}')
