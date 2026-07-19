# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Repeatable SQLite-to-PostgreSQL importer regression coverage."""

from pathlib import Path
import os

import pytest
from sqlalchemy import MetaData, create_engine, select, text

from scripts.migrate_sqlite_to_postgres import (
    CURRENT_SCHEMA_VERSION,
    _version_table,
    migrate,
)
from models import db


def _sqlite_url(path: Path):
    return f'sqlite+pysqlite:///{path}'


def _build_current_source(path: Path):
    engine = create_engine(_sqlite_url(path))
    db.metadata.create_all(engine)
    version_metadata = MetaData()
    version_table = _version_table(version_metadata)
    version_table.create(engine)

    user = db.metadata.tables['user']
    game = db.metadata.tables['game']
    player = db.metadata.tables['player']
    figure = db.metadata.tables['figure']
    active_spell = db.metadata.tables['active_spell']

    with engine.begin() as connection:
        connection.execute(version_table.insert(), {
            'version': CURRENT_SCHEMA_VERSION,
            'description': 'current',
            'applied_at': '2026-07-19',
        })
        connection.execute(user.insert(), {
            'id': 41,
            'username': 'import_user',
            'password_hash': 'test-hash',
        })
        connection.execute(game.insert(), {
            'id': 51,
            'state': 'active',
            'mode': 'duel',
            'last_battle_result': {'imported': True},
        })
        connection.execute(player.insert(), {
            'id': 61,
            'user_id': 41,
            'game_id': 51,
        })
        connection.execute(figure.insert(), {
            'id': 71,
            'player_id': 61,
            'game_id': 51,
            'family_name': 'Soldier',
            'field': 'military',
            'color': 'black',
            'name': 'Importer',
            'suit': 'Spades',
        })
        connection.execute(active_spell.insert(), {
            'id': 81,
            'game_id': 51,
            'player_id': 61,
            'spell_name': 'Test Spell',
            'spell_type': 'enchantment',
            'spell_family_name': 'Test Spell',
            'suit': 'Spades',
            'cast_round': 1,
        })
        connection.execute(
            game.update().where(game.c.id == 51).values(
                invader_player_id=61,
                advancing_figure_id=71,
                pending_spell_id=81,
            )
        )
    engine.dispose()


def test_import_preserves_ids_json_and_cyclic_foreign_keys(tmp_path):
    source_path = tmp_path / 'source.db'
    target_path = tmp_path / 'target.db'
    _build_current_source(source_path)

    row_counts, summary = migrate(
        source_path,
        _sqlite_url(target_path),
        allow_sqlite_target_for_tests=True,
    )

    assert row_counts['user'] == 1
    assert summary['user'] == 1
    assert summary['open_or_active_games'] == 1

    engine = create_engine(_sqlite_url(target_path))
    metadata = MetaData()
    metadata.reflect(engine)
    with engine.connect() as connection:
        game = connection.execute(
            select(metadata.tables['game']).where(
                metadata.tables['game'].c.id == 51
            )
        ).mappings().one()
        assert game['invader_player_id'] == 61
        assert game['advancing_figure_id'] == 71
        assert game['pending_spell_id'] == 81
        assert game['last_battle_result'] == {'imported': True}
    engine.dispose()


@pytest.mark.skipif(
    not os.environ.get('TEST_DATABASE_URL'),
    reason='PostgreSQL service is only available in the compatibility CI job',
)
def test_import_runs_against_postgres_and_resets_sequences(tmp_path):
    source_path = tmp_path / 'postgres-source.db'
    _build_current_source(source_path)
    target_url = os.environ['TEST_DATABASE_URL']

    row_counts, summary = migrate(source_path, target_url)

    assert row_counts['user'] == 1
    assert summary['user'] == 1

    engine = create_engine(target_url)
    metadata = MetaData()
    metadata.reflect(engine)
    user = metadata.tables['user']
    game = metadata.tables['game']
    try:
        with engine.begin() as connection:
            imported_game = connection.execute(
                select(game).where(game.c.id == 51)
            ).mappings().one()
            assert imported_game['last_battle_result'] == {'imported': True}

            result = connection.execute(user.insert(), {
                'username': 'after_import',
                'password_hash': 'test-hash',
                'gold': 0,
                'is_ai': False,
                'email_verified': False,
                'notify_emails_enabled': True,
                'age_confirmed': False,
                'booster_packs': 0,
                'booster_packs_side': 0,
                'maps': 0,
            })
            assert result.inserted_primary_key == (42,)
    finally:
        with engine.begin() as connection:
            connection.execute(text('DROP SCHEMA public CASCADE'))
            connection.execute(text('CREATE SCHEMA public'))
        engine.dispose()
