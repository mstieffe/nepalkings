# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
# server.py
from flask import Flask, g, jsonify, request
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from models import db
import json
import logging
from logging.handlers import RotatingFileHandler
import signal
import sys
import time
import uuid

import server_settings as settings
from observability import JsonLogFormatter, configure_logging
from routes import (auth, battle_shop, challenges, collection, figures, games,
                    kingdom, legal, msg, onboarding, ops, safety, spells)

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
_IS_DEV = settings.IS_DEVELOPMENT
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
if not getattr(settings, 'DB_URL_FROM_ENV', False) and not _IS_DEV:
    raise RuntimeError(
        "DB_URL must be set explicitly in non-development environments."
    )
if (
    settings.DB_URL.startswith('sqlite:')
    and not _IS_DEV
    and not settings.ALLOW_PRODUCTION_SQLITE
):
    raise RuntimeError(
        "SQLite is disabled in non-development environments. Use PostgreSQL "
        "or set ALLOW_PRODUCTION_SQLITE=True only for an intentional legacy "
        "fallback deployment."
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
CORS(
    app,
    origins=cors_origins,
    allow_headers=['Content-Type', 'Authorization', 'X-Request-ID'],
    expose_headers=['X-Request-ID'],
    max_age=settings.CORS_PREFLIGHT_MAX_AGE_SECONDS,
)

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

# ── Maintenance and request-size guards ──
@app.before_request
def _start_request_observability():
    supplied = request.headers.get('X-Request-ID', '').strip()
    if (
        supplied
        and len(supplied) <= 64
        and all(ch.isalnum() or ch in '-_.' for ch in supplied)
    ):
        g.request_id = supplied
    else:
        g.request_id = uuid.uuid4().hex
    g.request_started_at = time.perf_counter()


@app.before_request
def _enforce_maintenance_mode():
    if not settings.MAINTENANCE_MODE:
        return None
    if (
        request.path in {'/healthz', '/readyz'}
        or request.path.startswith('/legal/')
    ):
        return None
    response = jsonify({
        'success': False,
        'message': settings.MAINTENANCE_MESSAGE,
        'reason': 'maintenance',
        'retryable': True,
    })
    response.status_code = 503
    response.headers['Retry-After'] = str(
        settings.MAINTENANCE_RETRY_AFTER_SECONDS
    )
    response.headers['Cache-Control'] = 'no-store'
    return response


@app.before_request
def _enforce_feature_switches():
    switches = {
        'auth.register': (
            settings.REGISTRATION_ENABLED,
            'registration_disabled',
            'New registrations are temporarily paused.',
        ),
        'msg.add_chat_message': (
            settings.CHAT_ENABLED,
            'chat_disabled',
            'Chat is temporarily paused.',
        ),
        'kingdom.kingdom_messages_send': (
            settings.CHAT_ENABLED,
            'chat_disabled',
            'Kingdom messages are temporarily paused.',
        ),
        'challenges.create_challenge': (
            settings.NEW_GAMES_ENABLED,
            'new_games_disabled',
            'Starting new games is temporarily paused.',
        ),
        'games.create_game': (
            settings.NEW_GAMES_ENABLED,
            'new_games_disabled',
            'Starting new games is temporarily paused.',
        ),
        'kingdom.conquer_start_battle': (
            settings.CONQUER_ENABLED,
            'conquer_disabled',
            'Starting Conquer battles is temporarily paused.',
        ),
    }
    configured = switches.get(request.endpoint)
    if configured is None or configured[0]:
        return None
    response = jsonify({
        'success': False,
        'message': configured[2],
        'reason': configured[1],
        'retryable': True,
    })
    response.status_code = 503
    response.headers['Retry-After'] = str(
        settings.MAINTENANCE_RETRY_AFTER_SECONDS
    )
    response.headers['Cache-Control'] = 'no-store'
    return response


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


@app.errorhandler(404)
def _route_not_found(_e):
    return jsonify({'success': False, 'message': 'Route not found'}), 404


@app.errorhandler(405)
def _method_not_allowed(_e):
    return jsonify({'success': False, 'message': 'Method not allowed'}), 405

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


@app.after_request
def _record_request(response):
    request_id = getattr(g, 'request_id', None)
    if request_id:
        response.headers['X-Request-ID'] = request_id
        if response.status_code >= 400 and response.is_json:
            payload = response.get_json(silent=True)
            if isinstance(payload, dict) and 'request_id' not in payload:
                payload['request_id'] = request_id
                response.set_data(json.dumps(
                    payload,
                    separators=(',', ':'),
                    ensure_ascii=False,
                ))
    started = getattr(g, 'request_started_at', None)
    duration_ms = (
        round((time.perf_counter() - started) * 1000, 1)
        if started is not None else None
    )
    logging.getLogger('nepalkings.request').info(
        'request_complete',
        extra={
            'event': 'request_complete',
            'method': request.method,
            'path': request.path,
            'endpoint': request.endpoint,
            'status': response.status_code,
            'duration_ms': duration_ms,
            'user_id': getattr(g, 'user_id', None),
        },
    )
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
configure_logging(
    environment=settings.APP_ENVIRONMENT,
    release_sha=settings.RELEASE_SHA,
    debug=settings.DEBUG_ENABLED,
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
            JsonLogFormatter(
                environment=settings.APP_ENVIRONMENT,
                release_sha=settings.RELEASE_SHA,
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
        'pool_recycle': settings.DB_POOL_RECYCLE_SECONDS,
        'pool_size': settings.DB_POOL_SIZE,
        'max_overflow': settings.DB_MAX_OVERFLOW,
        'pool_timeout': settings.DB_POOL_TIMEOUT_SECONDS,
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
        'pool_recycle': settings.DB_POOL_RECYCLE_SECONDS,
        'pool_size': settings.DB_POOL_SIZE,
        'max_overflow': settings.DB_MAX_OVERFLOW,
        'pool_timeout': settings.DB_POOL_TIMEOUT_SECONDS,
    }
db.init_app(app)

# ── Cross-worker request coordination ──
_GAME_MUTATION_BLUEPRINTS = {
    'games',
    'figures',
    'spells',
    'battle_shop',
}


@app.before_request
def _serialize_game_mutations():
    """Lock one game's PostgreSQL transaction before a mutating route."""
    if request.method not in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        return None
    if request.blueprint not in _GAME_MUTATION_BLUEPRINTS:
        return None
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        data = request.form or {}
    game_id = data.get('game_id')
    if game_id is None:
        return None
    try:
        game_id = int(game_id)
    except (TypeError, ValueError):
        return None

    from game_service.conquer_tactics_idempotency import (
        acquire_game_transaction_lock,
    )

    acquire_game_transaction_lock(game_id)
    return None


@app.before_request
def _enforce_shared_auth_rate_limits():
    """Apply exact cross-worker limits to login and registration."""
    if settings.IS_DEVELOPMENT:
        return None
    if not app.config.get('RATELIMIT_ENABLED', True):
        return None
    limits_by_endpoint = {
        'auth.login': settings.RATE_LIMIT_LOGIN,
        'auth.register': settings.RATE_LIMIT_REGISTER,
    }
    configured = limits_by_endpoint.get(request.endpoint)
    if not configured:
        return None

    from limits import parse
    from security_rate_limits import consume_rate_limit

    item = parse(configured)
    allowed, remaining, retry_after = consume_rate_limit(
        request.endpoint,
        get_remote_address(),
        limit=item.amount,
        window_seconds=item.get_expiry(),
    )
    if allowed:
        return None
    response = jsonify({
        'success': False,
        'message': 'Too many requests. Try again later.',
        'reason': 'rate_limit',
        'retryable': True,
    })
    response.status_code = 429
    response.headers['Retry-After'] = str(retry_after)
    response.headers['X-RateLimit-Remaining'] = str(remaining)
    response.headers['Cache-Control'] = 'no-store'
    return response

# Local development keeps the historical convenience. Production runs this
# command explicitly before WSGI reload:
#   python manage.py prepare-database
from startup import prepare_database, start_background_services

if settings.STARTUP_MAINTENANCE_ENABLED:
    prepare_database(app)
else:
    logger.info(
        'Import-time database maintenance disabled; expecting a prepared schema'
    )
start_background_services(app)

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
app.register_blueprint(safety, url_prefix='/safety')
app.register_blueprint(ops)

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

for _view_name in (
    'msg.add_chat_message',
    'kingdom.kingdom_messages_send',
):
    _view_fn = app.view_functions.get(_view_name)
    if _view_fn is not None:
        limiter.limit(settings.RATE_LIMIT_CHAT)(_view_fn)

_report_view = app.view_functions.get('safety.create_report')
if _report_view is not None:
    limiter.limit(settings.RATE_LIMIT_REPORT)(_report_view)

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
        app.run(host='0.0.0.0', port=5000)
    except Exception as e:
        logger.error(f'Application failed to start: {e}')
