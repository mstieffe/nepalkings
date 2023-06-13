from flask import Flask, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User, Challenge
import settings

app = Flask(__name__)

# Configure the database URI
app.config['SQLALCHEMY_DATABASE_URI'] = settings.DB_URL
db.init_app(app)

with app.app_context():
    db.drop_all()

@app.route('/challenge', methods=['POST'])
def challenge():
    print("wir sind hier ok!!!")
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
        print("ja das geht doch")
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
            return jsonify({'error': 'User not found'})

        challenges = Challenge.query.filter((Challenge.challenger == user) | (Challenge.challenged == user)).filter_by(status='open').all()
        #challenges = Challenge.query.all()

        return jsonify({
            'challenges': [
                {'challenger': challenge.challenger.username, 'challenged': challenge.challenged.username}
                for challenge in challenges
            ]
        })
    except Exception as e:

        return jsonify({'message': 'An error occurred: {}'.format(str(e))})


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
