# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Shared fixtures for server tests."""
import os
import sys
import pytest
from sqlalchemy import text

# Make the server package importable when tests run from the repo root
SERVER_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'server')
if SERVER_DIR not in sys.path:
    sys.path.insert(0, os.path.abspath(SERVER_DIR))

# Disable AI so tests don't spin up workers
os.environ.setdefault('AI_ENABLED', 'False')
os.environ.setdefault('STARTUP_MAINTENANCE_ENABLED', 'False')
os.environ.setdefault('BACKGROUND_SERVICES_ENABLED', 'False')

# CI can provide a disposable PostgreSQL database for compatibility coverage.
# Ordinary local tests remain isolated in in-memory SQLite.
TEST_DATABASE_URL = os.environ.get(
    'TEST_DATABASE_URL',
    'sqlite:///:memory:',
)
os.environ['DB_URL'] = TEST_DATABASE_URL

from server import app as flask_app  # noqa: E402
from models import db as _db  # noqa: E402


def _reset_database_schema():
    _db.session.remove()
    if _db.engine.dialect.name == 'postgresql':
        # PostgreSQL correctly refuses metadata.drop_all() for the intentional
        # Game/Player/Figure/ActiveSpell FK cycle unless every legacy
        # constraint is named. Tests own this disposable schema, so resetting
        # the schema is both faster and more faithful.
        with _db.engine.begin() as connection:
            connection.execute(text('DROP SCHEMA IF EXISTS public CASCADE'))
            connection.execute(text('CREATE SCHEMA public'))
    else:
        _db.drop_all()


@pytest.fixture(scope='function')
def app():
    flask_app.config['TESTING'] = True
    flask_app.config['SQLALCHEMY_DATABASE_URI'] = TEST_DATABASE_URL
    flask_app.config['WTF_CSRF_ENABLED'] = False
    # Disable rate limiting during tests
    flask_app.config['RATELIMIT_ENABLED'] = False

    with flask_app.app_context():
        _reset_database_schema()
        _db.create_all()
        yield flask_app
        _reset_database_schema()


@pytest.fixture(autouse=True)
def _reset_conquer_idempotency_cache():
    """Reset the process-level conquer idempotency cache between tests.

    The cache is keyed by ``(game_id, player_id, endpoint, client_action_id)``
    which can repeat across tests because every test fixture rolls back
    to fresh ``id=1, 2, 3, …`` rows.  Without this reset, a request in
    test B can hit a stale entry from test A and return data referring
    to a now-dropped DB state (figures missing, players gone, etc.).
    """
    try:
        from game_service.conquer_tactics_idempotency import (
            reset_cache_for_tests,
        )
    except Exception:
        yield
        return
    reset_cache_for_tests()
    yield
    reset_cache_for_tests()


@pytest.fixture(autouse=True)
def _reset_conquer_timer_state():
    """Reset routes.games' module-level conquer timer/watchdog maps.

    ``_conquer_round_deadlines`` / ``_conquer_timeout_last_check`` /
    ``_conquer_ai_watchdog_last`` are keyed by game id, which repeats
    across tests (fresh DB, ids restart at 1). Stale entries would
    throttle the AI watchdog or fire round timeouts for a previous
    test's game.
    """
    import importlib
    try:
        # NOTE: ``from routes import games`` would resolve to the Blueprint
        # attribute re-exported by the package, not the module.
        _games_module = importlib.import_module('routes.games')
    except Exception:
        yield
        return
    for attr in ('_conquer_round_deadlines', '_conquer_timeout_last_check',
                 '_conquer_ai_watchdog_last'):
        getattr(_games_module, attr, {}).clear()
    yield
    for attr in ('_conquer_round_deadlines', '_conquer_timeout_last_check',
                 '_conquer_ai_watchdog_last'):
        getattr(_games_module, attr, {}).clear()


@pytest.fixture(autouse=True)
def _reset_land_coord_counter():
    """Reset the shared ``_LAND_COORD_COUNTER`` in ``test_land_battle``.

    That module-level counter is read by every test that uses
    :func:`tests.server.test_land_battle._make_land` (including helpers
    imported from other suites such as ``test_conquer_tactics_hand``).
    Without a per-test reset, the land's ``col``/``row`` shift with
    collection order, which feeds the deterministic
    :func:`ai.defence.generator._template_seed` and silently changes
    the AI defender's prelude spell — flipping
    ``test_conquer_game_finishes_after_battle`` between Forced Deal
    (harmless) and Explosion (destroys the attacker's only figure).
    """
    try:
        from tests.server import test_land_battle as _land_battle_module
    except Exception:
        try:
            import test_land_battle as _land_battle_module  # type: ignore
        except Exception:
            yield
            return
    _saved = getattr(_land_battle_module, '_LAND_COORD_COUNTER', 0)
    _land_battle_module._LAND_COORD_COUNTER = 0
    try:
        yield
    finally:
        _land_battle_module._LAND_COORD_COUNTER = _saved


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    return _db


@pytest.fixture
def two_users(db):
    """Create two test users with gold."""
    from models import User
    from werkzeug.security import generate_password_hash
    u1 = User(
        username='player1',
        password_hash=generate_password_hash('password1'),
        gold=100,
    )
    u2 = User(
        username='player2',
        password_hash=generate_password_hash('password2'),
        gold=100,
    )
    db.session.add_all([u1, u2])
    db.session.commit()
    return u1, u2


@pytest.fixture
def auth_headers_user1(app, two_users):
    """Return Bearer token headers for player1."""
    from routes.auth import generate_token
    u1, _ = two_users
    token = generate_token(u1.id)
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def auth_headers_user2(app, two_users):
    """Return Bearer token headers for player2."""
    from routes.auth import generate_token
    _, u2 = two_users
    token = generate_token(u2.id)
    return {'Authorization': f'Bearer {token}'}
