# server.py
from flask import Flask
from models import db
import settings

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from routes import games, challenges, auth

games.settings = settings
challenges.settings = settings
auth.settings = settings

app = Flask(__name__)

# Configure the database URI
app.config['SQLALCHEMY_DATABASE_URI'] = settings.DB_URL
db.init_app(app)

with app.app_context():
    db.drop_all()

# Register the blueprints
app.register_blueprint(games, url_prefix='/games')
app.register_blueprint(challenges, url_prefix='/challenges')
app.register_blueprint(auth, url_prefix='/auth')

if __name__ == '__main__':
    try:
        with app.app_context():
            db.create_all()
        app.run(host='localhost', port=5000)
    except Exception as e:
        print(f'Application failed to start, Error: {str(e)}')

