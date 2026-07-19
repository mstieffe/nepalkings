# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
# server.py
from flask import Flask, g, jsonify, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from models import db
import logging
from logging.handlers import RotatingFileHandler
import signal
import sys

import server_settings as settings
from routes import games, challenges, auth, msg, figures, spells, battle_shop, collection, kingdom, onboarding, legal

games.settings = settings
challenges.settings = settings
auth.settings = settings
msg.settings = settings
figures.settings = settings
spells.settings = settings
battle_shop.settings = settings
onboarding.settings = settings
legal.settings = settings

app = Flask(__name__)
app.config['SECRET_KEY'] = settings.SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = settings.MAX_CONTENT_LENGTH

# ── Production safety guard ───────────────────────────────────────
# In any non-development environment, refuse to boot if SECRET_KEY is
# not set explicitly via env. A random per-process default is fine for
# local dev but means a deploy restart silently invalidates every
# issued token and signed cookie.
import os as _os
_FLASK_ENV = (_os.getenv('FLASK_ENV') or _os.getenv('ENV') or '').lower()
_IS_DEV = _FLASK_ENV in ('development', 'dev', 'local', 'test', '')
if not getattr(settings, 'SECRET_KEY_FROM_ENV', False) and not _IS_DEV:
    raise RuntimeError(
        "SECRET_KEY env var must be set in non-development environments. "
        "Refusing to boot with an ephemeral random key."
    )
if getattr(settings, 'DROP_TABLES_ON_STARTUP', False) and not _IS_DEV:
    raise RuntimeError(
        "DROP_TABLES_ON_STARTUP is True in a non-development environment. "
        "This would wipe production data. Refusing to boot."
    )

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
    # memory:// keeps per-process counters, so the effective limit is
    # limit × worker_count; point RATELIMIT_STORAGE_URI at Redis or
    # similar for shared counters across workers.
    storage_uri=settings.RATELIMIT_STORAGE_URI,
)

# ── JSON error for oversized request bodies ──
# Werkzeug only raises 413 lazily when a view reads the body, where the
# routes' blanket except-blocks would turn it into a 500 — so reject
# based on the declared Content-Length before any view runs.
@app.before_request
def _reject_oversized_body():
    length = request.content_length
    if length is not None and length > app.config['MAX_CONTENT_LENGTH']:
        return jsonify({'success': False, 'message': 'Request too large'}), 413


@app.errorhandler(413)
def _request_too_large(_e):
    return jsonify({'success': False, 'message': 'Request too large'}), 413

# ── Async-play email notifications ──
@app.after_request
def _turn_notification_hook(response):
    """After any state-changing POST that names a game, check whether an
    offline player should be emailed (it's-your-turn / game finished).
    Debouncing and eligibility live in notification_service."""
    try:
        if (request.method == 'POST'
                and getattr(settings, 'NOTIFY_EMAILS_ENABLED', True)
                and response.status_code < 400):
            game_id = None
            try:
                if request.is_json and request.json:
                    game_id = request.json.get('game_id')
                elif request.form:
                    game_id = request.form.get('game_id')
            except Exception:
                game_id = None
            if game_id:
                from notification_service import maybe_notify_turn_or_finish
                maybe_notify_turn_or_finish(
                    game_id, requester_user_id=getattr(g, 'user_id', None))
    except Exception:
        logging.getLogger('nepalkings').exception('turn notification hook failed')
    return response


# ── Security response headers ──
@app.after_request
def _set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "base-uri 'self'; "
        "frame-ancestors 'none'; "
        "object-src 'none'; "
        "form-action 'self'"
    )
    response.headers['Permissions-Policy'] = (
        'camera=(), microphone=(), geolocation=(), payment=()'
    )
    if not _IS_DEV:
        response.headers['Strict-Transport-Security'] = (
            'max-age=31536000; includeSubDomains'
        )
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
_is_sqlite = settings.DB_URL.startswith('sqlite:')
if _is_sqlite and ':memory:' in settings.DB_URL:
    # In-memory SQLite uses StaticPool — pool_size/overflow/timeout are invalid
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'connect_args': {
            'check_same_thread': False
        }
    }
elif _is_sqlite:
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'pool_size': 5,           # Max persistent connections
        'max_overflow': 2,        # Extra connections beyond pool_size
        'pool_timeout': 10,       # Seconds to wait for a connection before error
        'connect_args': {
            'timeout': float(settings.SQLITE_BUSY_TIMEOUT_SECONDS),
            'check_same_thread': False  # Important for SQLite with Flask
        }
    }
else:
    # DBAPI-specific SQLite arguments such as ``check_same_thread`` make a
    # PostgreSQL deployment fail during engine creation. Keep the shared pool
    # tuning while allowing the target driver to use its native defaults.
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'pool_size': 5,
        'max_overflow': 2,
        'pool_timeout': 10,
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

    try:
        from migration_runner import run_migrations
        _applied = run_migrations()
        if _applied:
            logger.info("Applied schema migrations: %s",
                        ', '.join(f'{v:04d}' for v in _applied))
    except Exception as _migration_err:  # pragma: no cover — startup safety
        logger.exception(
            "Schema migration failed: %s — refusing to start with a partial "
            "or incompatible schema.", _migration_err)
        db.session.rollback()
        raise RuntimeError(
            'Required database migration failed; application startup aborted'
        ) from _migration_err

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
            'defence_draft_figure': figure_ids,
            'conquer_move':     move_ids,
            'defence_move':     move_ids,
            'defence_draft_move': move_ids,
            'conquer_modifier': config_ids,
            'defence_modifier': config_ids,
            'defence_draft_modifier': config_ids,
            'conquer_spell':    config_ids,
            'defence_spell':    config_ids,
            'defence_draft_spell': config_ids,
            'conquer_prelude':  config_ids,
            'defence_prelude':  config_ids,
            'defence_draft_prelude': config_ids,
            'conquer_counter':  config_ids,
            'defence_counter':  config_ids,
            'defence_draft_counter': config_ids,
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
    try:
        from kingdom_service import reconcile_all_kingdoms
        reconcile_all_kingdoms(commit=True)
        logger.info("Persistent kingdom reconciliation checked")
    except Exception as _kingdom_reconcile_err:  # pragma: no cover — safety net
        logger.exception("Persistent kingdom reconciliation failed: %s", _kingdom_reconcile_err)
        db.session.rollback()
    if settings.RECONCILE_REGION_CHAMPIONS_ON_STARTUP:
        try:
            from region_service import reconcile_region_champions
            reconcile_region_champions(commit=True)
            logger.info("Historic region Champion reconciliation checked")
        except Exception as _region_reconcile_err:  # pragma: no cover — safety net
            logger.exception(
                "Historic region Champion reconciliation failed: %s",
                _region_reconcile_err,
            )
            db.session.rollback()
    else:
        logger.info(
            "Historic region Champion startup reconciliation skipped"
        )

    # Create AI users if enabled
    if settings.AI_ENABLED:
        from ai import init_ai_users
        init_ai_users()

    # Start the stuck-conquer-game sweeper (daemon thread).  Skipped when
    # running tests (pytest sets PYTEST_CURRENT_TEST or sys.modules has
    # pytest) — tests call sweep_stuck_conquer_games directly when they
    # need to exercise the sweeper.
    import sys as _sys
    _is_pytest = ('pytest' in _sys.modules or
                  _os.environ.get('PYTEST_CURRENT_TEST') is not None or
                  _os.environ.get('DISABLE_BACKGROUND_SWEEPERS') == '1')
    if not _is_pytest:
        try:
            from sweepers import start_stuck_conquer_sweeper
            start_stuck_conquer_sweeper(app)
        except Exception:
            logger.exception("Failed to start stuck-conquer sweeper")

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
app.register_blueprint(onboarding, url_prefix='/onboarding')
app.register_blueprint(legal, url_prefix='/legal')

# ── Stricter rate limits for auth-sensitive endpoints ──
limiter.limit(settings.RATE_LIMIT_LOGIN)(app.view_functions['auth.login'])
limiter.limit(settings.RATE_LIMIT_REGISTER)(app.view_functions['auth.register'])

_lookup_views = (
    'auth.get_user',
    'auth.get_users',
    'auth.get_rankings',
    'kingdom.get_kingdom_rankings',
    'challenges.open_challenges',
    'games.game_results',
)
for _view_name in _lookup_views:
    _view_fn = app.view_functions.get(_view_name)
    if _view_fn is not None:
        limiter.limit(settings.RATE_LIMIT_LOOKUP)(_view_fn)

# ── Per-user rate limits for kingdom mutation endpoints ──
_kingdom_mutate_views = (
    'kingdom.kingdom_config_cosmetic_purchase',
    'kingdom.kingdom_config_cosmetic_equip',
    'kingdom.kingdom_config_skill_upgrade',
    'kingdom.kingdom_config_skill_reset',
    'kingdom.kingdom_config_shield_purchase',
)
for _view_name in _kingdom_mutate_views:
    _view_fn = app.view_functions.get(_view_name)
    if _view_fn is not None:
        limiter.limit(settings.KINGDOM_MUTATE_RATE_LIMIT)(_view_fn)

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
            from migration_runner import run_migrations
            run_migrations()
        app.run(host='0.0.0.0', port=5000)
    except Exception as e:
        logger.error(f'Application failed to start: {e}')
