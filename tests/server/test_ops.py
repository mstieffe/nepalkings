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
