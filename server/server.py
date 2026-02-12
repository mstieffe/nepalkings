# server.py
from flask import Flask
from models import db
import logging

#import os
#import sys
#project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
#if project_root not in sys.path:
#    sys.path.insert(0, project_root)

import server_settings as settings
from routes import games, challenges, auth, msg, figures, spells

games.settings = settings
challenges.settings = settings
auth.settings = settings
msg.settings = settings
figures.settings = settings
spells.settings = settings

app = Flask(__name__)

# Disable Flask's default request logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)  # Only show errors, not every request

# Configure the database URI
app.config['SQLALCHEMY_DATABASE_URI'] = settings.DB_URL
db.init_app(app)

# Ensure the database is initialized correctly
with app.app_context():
    db.drop_all()
    db.create_all()

# Register Blueprints
app.register_blueprint(games, url_prefix='/games')
app.register_blueprint(challenges, url_prefix='/challenges')
app.register_blueprint(auth, url_prefix='/auth')
app.register_blueprint(msg, url_prefix='/msg')
app.register_blueprint(figures, url_prefix='/figures')
app.register_blueprint(spells, url_prefix='/spells')

if __name__ == '__main__':
    try:
        with app.app_context():
            db.create_all()
        app.run(host='localhost', port=5000)
    except Exception as e:
        print(f'Application failed to start, Error: {str(e)}')

