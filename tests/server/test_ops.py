# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Operational health and readiness endpoint coverage."""

from sqlalchemy import text

from migration_runner import CURRENT_SCHEMA_VERSION
from models import db


def _set_schema_version(version):
    db.session.execute(text(
        'CREATE TABLE IF NOT EXISTS schema_version ('
        ' version INTEGER PRIMARY KEY,'
        ' description VARCHAR(200),'
        ' applied_at VARCHAR(32))'
    ))
    db.session.execute(text('DELETE FROM schema_version'))
    db.session.execute(
        text(
            'INSERT INTO schema_version (version, description, applied_at) '
            "VALUES (:version, 'test', '2026-07-19')"
        ),
        {'version': version},
    )
    db.session.commit()


def test_healthz_is_database_independent(client, monkeypatch):
    def _database_must_not_be_called(*_args, **_kwargs):
        raise AssertionError('healthz accessed the database')

    monkeypatch.setattr(db.session, 'execute', _database_must_not_be_called)

    response = client.get('/healthz')

    assert response.status_code == 200
    assert response.get_json()['status'] == 'ok'
    assert response.headers['Cache-Control'] == 'no-store'


def test_readyz_reports_database_and_schema(client):
    _set_schema_version(CURRENT_SCHEMA_VERSION)

    response = client.get('/readyz')
    data = response.get_json()

    assert response.status_code == 200
    assert data['status'] == 'ready'
    assert data['database'] == db.engine.dialect.name
    assert data['schema_version'] == CURRENT_SCHEMA_VERSION
    assert data['api_version']
    assert data['release_sha']


def test_readyz_rejects_outdated_schema(client):
    _set_schema_version(CURRENT_SCHEMA_VERSION - 1)

    response = client.get('/readyz')
    data = response.get_json()

    assert response.status_code == 503
    assert data['reason'] == 'schema_version_mismatch'
    assert data['expected_schema_version'] == CURRENT_SCHEMA_VERSION


def test_readyz_rejects_database_failure(client, monkeypatch):
    def _raise_database_error(*_args, **_kwargs):
        raise RuntimeError('database unavailable')

    monkeypatch.setattr(db.session, 'execute', _raise_database_error)

    response = client.get('/readyz')

    assert response.status_code == 503
    assert response.get_json()['reason'] == 'database_unavailable'


def test_maintenance_mode_blocks_gameplay_but_keeps_ops_and_legal(
        client, monkeypatch):
    import server_settings as settings

    monkeypatch.setattr(settings, 'MAINTENANCE_MODE', True)
    monkeypatch.setattr(settings, 'MAINTENANCE_RETRY_AFTER_SECONDS', 123)

    blocked = client.post('/auth/login', data={
        'username': 'nobody',
        'password': 'invalid',
    })
    assert blocked.status_code == 503
    assert blocked.get_json()['reason'] == 'maintenance'
    assert blocked.headers['Retry-After'] == '123'

    assert client.get('/healthz').status_code == 200
    assert client.get('/legal/versions').status_code == 200


def test_request_id_is_echoed_and_invalid_value_is_replaced(client):
    supplied = client.get(
        '/healthz',
        headers={'X-Request-ID': 'player-report-123'},
    )
    assert supplied.headers['X-Request-ID'] == 'player-report-123'

    invalid = client.get(
        '/healthz',
        headers={'X-Request-ID': 'bad value with whitespace'},
    )
    generated = invalid.headers['X-Request-ID']
    assert generated != 'bad value with whitespace'
    assert len(generated) == 32
    assert generated.isalnum()


def test_request_id_is_in_json_errors_for_support(client):
    response = client.get(
        '/does-not-exist',
        headers={'X-Request-ID': 'support-case-123'},
    )

    assert response.status_code == 404
    assert response.headers['X-Request-ID'] == 'support-case-123'
    assert response.get_json()['request_id'] == 'support-case-123'


def test_cors_preflight_can_be_cached(client):
    response = client.options(
        '/auth/login',
        headers={
            'Origin': 'http://localhost',
            'Access-Control-Request-Method': 'POST',
            'Access-Control-Request-Headers': 'Authorization,X-Request-ID',
        },
    )

    assert response.status_code == 200
    assert response.headers['Access-Control-Max-Age'] == '600'
    assert 'X-Request-ID' in response.headers['Access-Control-Allow-Headers']


def test_registration_kill_switch(client, monkeypatch):
    import server_settings as settings

    monkeypatch.setattr(settings, 'REGISTRATION_ENABLED', False)
    response = client.post('/auth/register')

    assert response.status_code == 503
    assert response.get_json()['reason'] == 'registration_disabled'
    assert response.headers['Cache-Control'] == 'no-store'


def test_chat_kill_switch_blocks_both_chat_surfaces(client, monkeypatch):
    import server_settings as settings

    monkeypatch.setattr(settings, 'CHAT_ENABLED', False)

    duel_chat = client.post('/msg/add_chat_message')
    kingdom_chat = client.post('/kingdom/messages')

    assert duel_chat.status_code == 503
    assert duel_chat.get_json()['reason'] == 'chat_disabled'
    assert kingdom_chat.status_code == 503
    assert kingdom_chat.get_json()['reason'] == 'chat_disabled'


def test_new_game_and_conquer_kill_switches(client, monkeypatch):
    import server_settings as settings

    monkeypatch.setattr(settings, 'NEW_GAMES_ENABLED', False)
    monkeypatch.setattr(settings, 'CONQUER_ENABLED', False)

    challenge = client.post('/challenges/create_challenge')
    duel = client.post('/games/create_game')
    conquer = client.post('/kingdom/conquer/start_battle')

    assert challenge.status_code == 503
    assert challenge.get_json()['reason'] == 'new_games_disabled'
    assert duel.status_code == 503
    assert duel.get_json()['reason'] == 'new_games_disabled'
    assert conquer.status_code == 503
    assert conquer.get_json()['reason'] == 'conquer_disabled'
