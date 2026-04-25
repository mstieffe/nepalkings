# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
# server.py
from flask import Flask
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from models import db
import logging
from logging.handlers import RotatingFileHandler
import signal
import sys

import server_settings as settings
from routes import games, challenges, auth, msg, figures, spells, battle_shop, collection, kingdom

games.settings = settings
challenges.settings = settings
auth.settings = settings
msg.settings = settings
figures.settings = settings
spells.settings = settings
battle_shop.settings = settings

app = Flask(__name__)
app.config['SECRET_KEY'] = settings.SECRET_KEY

# ── Proxy fix (PythonAnywhere / reverse-proxy environments) ──
# Without this, request.remote_addr returns the proxy IP and ALL clients
# share a single rate-limit bucket — exhausting it almost immediately.
from werkzeug.middleware.proxy_fix import ProxyFix
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)

# ── CORS ──
cors_origins = settings.CORS_ORIGINS
if cors_origins != '*':
    cors_origins = [o.strip() for o in cors_origins.split(',')]
CORS(app, origins=cors_origins, allow_headers=['Content-Type', 'Authorization'])

# ── Rate limiting ──
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[settings.RATE_LIMIT_DEFAULT],
    storage_uri='memory://',
)

# ── Security response headers ──
@app.after_request
def _set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response

# ── Logging configuration ──
# Central logging setup.  All server modules use named loggers under the
# 'nepalkings' hierarchy so that every line carries a timestamp, level,
# and the originating module — making production log analysis much easier.
logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG_ENABLED else logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger('nepalkings')

if settings.DEBUG_LOG_TO_FILE:
    try:
        file_handler = RotatingFileHandler(
            settings.DEBUG_LOG_PATH,
            maxBytes=max(int(settings.DEBUG_LOG_MAX_BYTES), 1024),
            backupCount=max(int(settings.DEBUG_LOG_BACKUP_COUNT), 1),
        )
        file_handler.setLevel(logging.DEBUG if settings.DEBUG_ENABLED else logging.INFO)
        file_handler.setFormatter(
            logging.Formatter(
                '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S',
            )
        )
        logging.getLogger().addHandler(file_handler)
        logger.info(f"File logging enabled at {settings.DEBUG_LOG_PATH}")
    except Exception:
        logger.exception(f"Failed to enable file logging at {settings.DEBUG_LOG_PATH}")

# Disable Flask's default per-request logging (very noisy)
logging.getLogger('werkzeug').setLevel(logging.ERROR)

# Configure the database URI and SQLite-specific settings
app.config['SQLALCHEMY_DATABASE_URI'] = settings.DB_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
if ':memory:' in settings.DB_URL:
    # In-memory SQLite uses StaticPool — pool_size/overflow/timeout are invalid
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'connect_args': {
            'check_same_thread': False
        }
    }
else:
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
        logger.warning("Dropping all database tables (DROP_TABLES_ON_STARTUP=True)")
        db.drop_all()
        logger.info("All tables dropped")
    
    logger.info("Creating database tables...")
    db.create_all()
    
    # Auto-migrate: add missing columns to existing tables
    from sqlalchemy import inspect as sa_inspect, text
    inspector = sa_inspect(db.engine)
    if 'game' in inspector.get_table_names():
        existing_cols = {c['name'] for c in inspector.get_columns('game')}
        if 'resting_figure_ids' not in existing_cols:
            logger.info("Auto-migrate: adding 'resting_figure_ids' column to game table")
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE game ADD COLUMN resting_figure_ids JSON"))
                conn.commit()
        if 'battle_gamble_counts' not in existing_cols:
            logger.info("Auto-migrate: adding 'battle_gamble_counts' column to game table")
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE game ADD COLUMN battle_gamble_counts JSON"))
                conn.commit()
    if 'user' in inspector.get_table_names():
        existing_cols = {c['name'] for c in inspector.get_columns('user')}
        if 'last_active' not in existing_cols:
            logger.info("Auto-migrate: adding 'last_active' column to user table")
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE user ADD COLUMN last_active DATETIME"))
                conn.commit()
        if 'is_ai' not in existing_cols:
            logger.info("Auto-migrate: adding 'is_ai' column to user table")
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE user ADD COLUMN is_ai BOOLEAN DEFAULT 0"))
                conn.commit()
        if 'email' not in existing_cols:
            logger.info("Auto-migrate: adding 'email' column to user table")
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE user ADD COLUMN email VARCHAR(255)"))
                conn.commit()
        if 'email_verified' not in existing_cols:
            logger.info("Auto-migrate: adding 'email_verified' column to user table")
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE user ADD COLUMN email_verified BOOLEAN DEFAULT 0 NOT NULL"))
                conn.commit()
        if 'email_verification_token' not in existing_cols:
            logger.info("Auto-migrate: adding 'email_verification_token' column to user table")
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE user ADD COLUMN email_verification_token VARCHAR(128)"))
                conn.commit()
        if 'email_verification_sent_at' not in existing_cols:
            logger.info("Auto-migrate: adding 'email_verification_sent_at' column to user table")
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE user ADD COLUMN email_verification_sent_at DATETIME"))
                conn.commit()
    if 'challenge' in inspector.get_table_names():
        existing_cols = {c['name'] for c in inspector.get_columns('challenge')}
        if 'game_id' not in existing_cols:
            logger.info("Auto-migrate: adding 'game_id' column to challenge table")
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE challenge ADD COLUMN game_id INTEGER REFERENCES game(id)"))
                conn.commit()
    if 'land' in inspector.get_table_names():
        existing_cols = {c['name'] for c in inspector.get_columns('land')}
        if 'conquer_cooldown_until' not in existing_cols:
            logger.info("Auto-migrate: adding 'conquer_cooldown_until' column to land table")
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE land ADD COLUMN conquer_cooldown_until DATETIME"))
                conn.commit()
    if 'land_config' in inspector.get_table_names():
        existing_cols = {c['name'] for c in inspector.get_columns('land_config')}
        _lc_new_cols = {
            'prelude_spell_name':          'VARCHAR(50)',
            'prelude_spell_data':          'JSON',
            'prelude_spell_card_ids':      'JSON',
            'counter_spell_name':          'VARCHAR(50)',
            'counter_spell_data':          'JSON',
            'counter_spell_card_ids':      'JSON',
            'counter_spell_target_figure_id': 'INTEGER',
            'auto_gamble_threshold':       'INTEGER DEFAULT 10',
        }
        for col_name, col_type in _lc_new_cols.items():
            if col_name not in existing_cols:
                logger.info("Auto-migrate: adding '%s' column to land_config table", col_name)
                with db.engine.connect() as conn:
                    conn.execute(text(f"ALTER TABLE land_config ADD COLUMN {col_name} {col_type}"))
                    conn.commit()
    
    logger.info("Database initialized")

    # ── Orphan-lock sweep ─────────────────────────────────────────────
    # Find CollectionCard rows whose lock_ref_id no longer points to a
    # live LandConfigFigure / LandConfigBattleMove / LandConfig row, and
    # release the lock.  Keeps the collection consistent across server
    # restarts that follow crashes mid-transaction.
    try:
        from models import (CollectionCard, LandConfig,
                            LandConfigFigure, LandConfigBattleMove)
        figure_ids  = {fid for (fid,) in db.session.query(LandConfigFigure.id).all()}
        move_ids    = {mid for (mid,) in db.session.query(LandConfigBattleMove.id).all()}
        config_ids  = {cid for (cid,) in db.session.query(LandConfig.id).all()}
        valid_by_lock_type = {
            'conquer_figure':   figure_ids,
            'defence_figure':   figure_ids,
            'conquer_move':     move_ids,
            'defence_move':     move_ids,
            'conquer_modifier': config_ids,
            'defence_modifier': config_ids,
            'conquer_spell':    config_ids,
            'defence_spell':    config_ids,
            'conquer_prelude':  config_ids,
            'defence_prelude':  config_ids,
            'conquer_counter':  config_ids,
            'defence_counter':  config_ids,
        }
        locked_cards = CollectionCard.query.filter_by(locked=True).all()
        orphan_count = 0
        for cc in locked_cards:
            valid_set = valid_by_lock_type.get(cc.lock_type)
            if valid_set is None or cc.lock_ref_id not in valid_set:
                cc.locked = False
                cc.lock_type = None
                cc.lock_ref_id = None
                orphan_count += 1
        if orphan_count:
            db.session.commit()
            logger.warning("Orphan-lock sweep: released %d stale card lock(s)",
                           orphan_count)
        else:
            logger.info("Orphan-lock sweep: no stale locks found")
    except Exception as _olsw_err:  # pragma: no cover — safety net
        logger.exception("Orphan-lock sweep failed: %s", _olsw_err)
        db.session.rollback()

    # Seed the kingdom hex map (idempotent — skips if already seeded)
    from kingdom_service import seed_kingdom_map
    seed_kingdom_map()
    logger.info("Kingdom map seeding checked")

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
app.register_blueprint(collection, url_prefix='/collection')
app.register_blueprint(kingdom, url_prefix='/kingdom')

# ── Stricter rate limits for auth-sensitive endpoints ──
limiter.limit(settings.RATE_LIMIT_LOGIN)(app.view_functions['auth.login'])
limiter.limit(settings.RATE_LIMIT_REGISTER)(app.view_functions['auth.register'])

if __name__ == '__main__':
    def _graceful_shutdown(signum, frame):
        """Handle SIGINT/SIGTERM quickly by closing the DB engine."""
        logger.info("Shutting down server...")
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
        logger.error(f'Application failed to start: {e}')

