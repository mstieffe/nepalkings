from flask import Flask, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from models import db, User
import settings

app = Flask(__name__)

# Configure your database URI
app.config['SQLALCHEMY_DATABASE_URI'] = settings.DB_URL
#db = SQLAlchemy(app)
db.init_app(app)

#with app.app_context():
#    db.drop_all()

@app.route('/challenge', methods=['POST'])
def challenge():
    challenger = request.form.get('challenger')
    opponent = request.form.get('opponent')

    # TODO: Add code here to update the database with the new challenge

    return jsonify({'success': True, 'message': 'Challenge sent'})

@app.route('/get_users', methods=['GET'])
def get_users():
    current_username = request.args.get('username')  # Get the 'username' parameter from the request
    print(current_username)
    users = User.query.filter(User.username != current_username).all()  # Query for all users excluding the current user
    print([user.username for user in users])
    return jsonify({'users': [user.username for user in users]})

@app.route('/register', methods=['POST'])
def register():
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


@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')


    print("ha halskd kasd")
    if not username or not password:
        return jsonify({'success': False, 'message': 'Missing username or password'})

    user = User.query.filter_by(username=username).first()

    if not user or not user.check_password(password):
        return jsonify({'success': False, 'message': 'Invalid username or password'})

    return jsonify({'success': True, 'message': 'Login successful'})


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='localhost', port=5000)