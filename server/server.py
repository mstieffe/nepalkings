# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
# server.py
from flask import Flask
from flask_cors import CORS
from models import db
import logging
import signal
import sys

import server_settings as settings
from routes import games, challenges, auth, msg, figures, spells, battle_shop

games.settings = settings
challenges.settings = settings
auth.settings = settings
msg.settings = settings
figures.settings = settings
spells.settings = settings
battle_shop.settings = settings

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests from game clients

# ── Logging configuration ──
# Set up a proper logger so route files can use logging.info/warning/error
# instead of print(), which avoids unbounded stdout buffer growth.
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG_ENABLED else logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S',
)
logger = logging.getLogger('nepalkings')

# Disable Flask's default request logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)  # Only show errors, not every request

# Configure the database URI and SQLite-specific settings
app.config['SQLALCHEMY_DATABASE_URI'] = settings.DB_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
    'pool_size': 5,           # Max persistent connections
    'max_overflow': 2,        # Extra connections beyond pool_size
    'pool_timeout': 10,       # Seconds to wait for a connection before error
    'connect_args': {
        'timeout': 30,
        'check_same_thread': False  # Important for SQLite with Flask
    }
}
db.init_app(app)

# Initialize database tables
with app.app_context():
    if settings.DROP_TABLES_ON_STARTUP:
        print("⚠️  WARNING: Dropping all database tables (DROP_TABLES_ON_STARTUP=True)")
        db.drop_all()
        print("✅ All tables dropped")
    
    print("Creating database tables...")
    db.create_all()
    
    # Auto-migrate: add missing columns to existing tables
    from sqlalchemy import inspect as sa_inspect, text
    inspector = sa_inspect(db.engine)
    if 'game' in inspector.get_table_names():
        existing_cols = {c['name'] for c in inspector.get_columns('game')}
        if 'resting_figure_ids' not in existing_cols:
            print("  ↳ Adding 'resting_figure_ids' column to game table...")
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE game ADD COLUMN resting_figure_ids JSON"))
                conn.commit()
    if 'user' in inspector.get_table_names():
        existing_cols = {c['name'] for c in inspector.get_columns('user')}
        if 'last_active' not in existing_cols:
            print("  ↳ Adding 'last_active' column to user table...")
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE user ADD COLUMN last_active DATETIME"))
                conn.commit()
        if 'is_ai' not in existing_cols:
            print("  ↳ Adding 'is_ai' column to user table...")
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE user ADD COLUMN is_ai BOOLEAN DEFAULT 0"))
                conn.commit()
    
    print("✅ Database initialized")

    # Create AI users if enabled
    if settings.AI_ENABLED:
        from ai import init_ai_users
        init_ai_users()

# ── Session cleanup on every request teardown ──
@app.teardown_appcontext
def shutdown_session(exception=None):
    """Ensure the DB session is properly closed after every request.
    
    This prevents leaked connections from accumulating over time,
    which is the main cause of slow server shutdown.
    """
    if exception:
        db.session.rollback()
    db.session.remove()

# Register Blueprints
app.register_blueprint(games, url_prefix='/games')
app.register_blueprint(challenges, url_prefix='/challenges')
app.register_blueprint(auth, url_prefix='/auth')
app.register_blueprint(msg, url_prefix='/msg')
app.register_blueprint(figures, url_prefix='/figures')
app.register_blueprint(spells, url_prefix='/spells')
app.register_blueprint(battle_shop, url_prefix='/battle_shop')

if __name__ == '__main__':
    def _graceful_shutdown(signum, frame):
        """Handle SIGINT/SIGTERM quickly by closing the DB engine."""
        print("\n🛑 Shutting down server...")
        with app.app_context():
            db.session.remove()
            db.engine.dispose()
        sys.exit(0)

    signal.signal(signal.SIGINT, _graceful_shutdown)
    signal.signal(signal.SIGTERM, _graceful_shutdown)

    try:
        with app.app_context():
            db.create_all()
        app.run(host='0.0.0.0', port=5000)
    except Exception as e:
        print(f'Application failed to start, Error: {str(e)}')

