# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Shared fixtures for server tests."""
import os
import sys
import pytest

# Make the server package importable when tests run from the repo root
SERVER_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'server')
if SERVER_DIR not in sys.path:
    sys.path.insert(0, os.path.abspath(SERVER_DIR))

# Disable AI so tests don't spin up workers
os.environ.setdefault('AI_ENABLED', 'False')

# Force in-memory DB BEFORE importing server — prevents the real test.db
# from being initialised at module level when server.py runs db.init_app().
os.environ['DB_URL'] = 'sqlite:///:memory:'

from server import app as flask_app  # noqa: E402
from models import db as _db  # noqa: E402


@pytest.fixture(scope='function')
def app():
    flask_app.config['TESTING'] = True
    flask_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    flask_app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'connect_args': {'check_same_thread': False}
    }
    flask_app.config['WTF_CSRF_ENABLED'] = False
    # Disable rate limiting during tests
    flask_app.config['RATELIMIT_ENABLED'] = False

    with flask_app.app_context():
        _db.create_all()
        yield flask_app
        _db.session.remove()
        _db.drop_all()


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
