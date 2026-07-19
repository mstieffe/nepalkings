# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for the versioned startup migration runner."""

import pytest
from sqlalchemy import inspect as sa_inspect, text

import migration_runner
from migration_runner import (MIGRATIONS, _add_column_if_missing,
                              applied_versions, run_migrations)
from models import db


@pytest.fixture(autouse=True)
def _clean_version_table(app):
    """Each test starts with no recorded migration history."""
    db.session.execute(text('DROP TABLE IF EXISTS schema_version'))
    db.session.commit()
    yield


def test_run_applies_all_and_records_versions(app):
    ran = run_migrations()
    assert ran == sorted(m[0] for m in MIGRATIONS)
    assert applied_versions() == set(ran)


def test_rerun_is_a_noop(app):
    run_migrations()
    assert run_migrations() == []


def test_migrations_are_strictly_ordered_and_unique():
    versions = [m[0] for m in MIGRATIONS]
    assert versions == sorted(versions)
    assert len(versions) == len(set(versions))


def test_failure_halts_and_does_not_record(app, monkeypatch):
    def _boom():
        raise RuntimeError('migration exploded')

    # Replace the last migration with a failing one.
    patched = MIGRATIONS[:-1] + [(MIGRATIONS[-1][0], 'boom', _boom)]
    monkeypatch.setattr(migration_runner, 'MIGRATIONS', patched)

    with pytest.raises(RuntimeError):
        run_migrations()

    applied = applied_versions()
    assert MIGRATIONS[-1][0] not in applied
    # Everything before the failure was recorded.
    assert {m[0] for m in MIGRATIONS[:-1]} <= applied


def test_add_column_if_missing_is_idempotent(app):
    assert _add_column_if_missing('game', 'test_migration_col', 'INTEGER') is True
    assert _add_column_if_missing('game', 'test_migration_col', 'INTEGER') is False
    cols = {c['name'] for c in sa_inspect(db.engine).get_columns('game')}
    assert 'test_migration_col' in cols


def test_new_columns_exist_after_run(app):
    run_migrations()
    challenge_cols = {c['name'] for c in sa_inspect(db.engine).get_columns('challenge')}
    user_cols = {c['name'] for c in sa_inspect(db.engine).get_columns('user')}
    game_cols = {c['name'] for c in sa_inspect(db.engine).get_columns('game')}
    assert 'turn_time_limit' in challenge_cols
    assert 'notify_emails_enabled' in user_cols
    assert 'turn_email_log' in game_cols
    assert 'turn_time_limit' in game_cols
    assert 'battle_round_deadline_round' in game_cols
    assert 'battle_round_deadline_at' in game_cols
    table_names = set(sa_inspect(db.engine).get_table_names())
    assert 'conquer_action_receipt' in table_names
    assert 'security_rate_limit_counter' in table_names


def test_duel_turn_time_limit_migration_adds_legacy_columns(app):
    db.session.execute(text('ALTER TABLE challenge DROP COLUMN turn_time_limit'))
    db.session.execute(text('ALTER TABLE game DROP COLUMN turn_time_limit'))
    db.session.commit()

    migration_runner._m_duel_turn_time_limit_columns()

    challenge_cols = {c['name'] for c in sa_inspect(db.engine).get_columns('challenge')}
    game_cols = {c['name'] for c in sa_inspect(db.engine).get_columns('game')}
    assert 'turn_time_limit' in challenge_cols
    assert 'turn_time_limit' in game_cols


def test_finished_game_orphan_config_migration_is_selective(app):
    from models import Game, LandConfig, User

    if db.engine.dialect.name == 'postgresql':
        user = User(username='migration_owner', password_hash='test')
        db.session.add(user)
        db.session.flush()
        config = LandConfig(
            user_id=user.id,
            config_type='conquer',
        )
        db.session.add(config)
        db.session.flush()
        finished = Game(
            state='finished',
            mode='conquer',
            conquer_config_id=config.id,
        )
        db.session.add(finished)
        db.session.commit()
        finished_id = finished.id

        migration_runner._m_clear_finished_game_orphan_config_refs()

        assert (
            db.session.get(Game, finished_id).conquer_config_id
            == config.id
        )
        return

    finished = Game(
        state='finished',
        mode='conquer',
        conquer_config_id=987654,
    )
    active = Game(
        state='active',
        mode='conquer',
        conquer_config_id=987655,
    )
    db.session.add_all([finished, active])
    db.session.commit()
    finished_id = finished.id
    active_id = active.id

    migration_runner._m_clear_finished_game_orphan_config_refs()

    assert db.session.get(Game, finished_id).conquer_config_id is None
    assert db.session.get(Game, active_id).conquer_config_id == 987655


def test_password_hash_column_supports_current_scrypt_length(app):
    from models import User
    from werkzeug.security import generate_password_hash

    password_hash = generate_password_hash('test-password')
    assert len(password_hash) > 128

    user = User(username='scrypt_length', password_hash=password_hash)
    db.session.add(user)
    db.session.commit()

    assert db.session.get(User, user.id).password_hash == password_hash
