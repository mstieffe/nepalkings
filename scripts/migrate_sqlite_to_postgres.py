#!/usr/bin/env python3
"""Copy a current Nepal Kings SQLite database into an empty PostgreSQL DB.

The importer is intentionally conservative:

* the source must pass SQLite integrity and be at the current schema version;
* the target must be PostgreSQL and contain no application rows;
* every known table and column must match;
* primary keys are preserved;
* nullable cyclic foreign keys are restored in a second pass;
* PostgreSQL identity sequences are reset after explicit-ID inserts;
* row counts and every declared foreign key are validated before commit.

Set ``TARGET_DATABASE_URL`` instead of passing a password on the command line.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import os
from pathlib import Path
import sqlite3
import sys

from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    func,
    inspect,
    select,
    text,
    update,
)
from sqlalchemy.engine import Engine


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = REPO_ROOT / 'server'
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from migration_runner import CURRENT_SCHEMA_VERSION  # noqa: E402
from models import db  # noqa: E402


VERSION_TABLE_NAME = 'schema_version'
COPY_BATCH_SIZE = 1_000


class MigrationError(RuntimeError):
    """Raised when a migration safety invariant is not satisfied."""


def _sqlite_url(path: Path) -> str:
    return f'sqlite+pysqlite:///{path.resolve()}'


def validate_sqlite_source(path: Path) -> None:
    if not path.is_file():
        raise MigrationError(f'SQLite source does not exist: {path}')
    if path.stat().st_size <= 0:
        raise MigrationError(f'SQLite source is empty: {path}')

    connection = sqlite3.connect(f'file:{path.resolve()}?mode=ro', uri=True)
    try:
        result = connection.execute('PRAGMA integrity_check').fetchone()
        if not result or result[0] != 'ok':
            raise MigrationError(
                f'SQLite integrity check failed: {result!r}'
            )
        row = connection.execute(
            'SELECT MAX(version) FROM schema_version'
        ).fetchone()
    except sqlite3.Error as exc:
        raise MigrationError(
            f'Unable to validate SQLite source schema: {exc}'
        ) from exc
    finally:
        connection.close()

    source_version = int((row or (0,))[0] or 0)
    if source_version != CURRENT_SCHEMA_VERSION:
        raise MigrationError(
            'SQLite source schema is not current: '
            f'{source_version} != {CURRENT_SCHEMA_VERSION}'
        )


def _version_table(metadata: MetaData) -> Table:
    return Table(
        VERSION_TABLE_NAME,
        metadata,
        Column('version', Integer, primary_key=True),
        Column('description', String(200)),
        Column('applied_at', String(32)),
        extend_existing=True,
    )


def _known_table_names() -> set[str]:
    return set(db.metadata.tables) | {VERSION_TABLE_NAME}


def _reflect_and_validate_source(engine: Engine) -> MetaData:
    metadata = MetaData()
    metadata.reflect(bind=engine)
    expected = _known_table_names()
    actual = set(metadata.tables)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise MigrationError(
            f'Source table set mismatch; missing={missing}, extra={extra}'
        )

    for name, model_table in db.metadata.tables.items():
        source_columns = set(metadata.tables[name].columns.keys())
        model_columns = set(model_table.columns.keys())
        if source_columns != model_columns:
            raise MigrationError(
                f'Source columns for {name} do not match current model; '
                f'missing={sorted(model_columns - source_columns)}, '
                f'extra={sorted(source_columns - model_columns)}'
            )
    return metadata


def _prepare_empty_target(engine: Engine) -> MetaData:
    db.metadata.create_all(bind=engine)
    version_metadata = MetaData()
    _version_table(version_metadata).create(bind=engine, checkfirst=True)

    metadata = MetaData()
    metadata.reflect(bind=engine)
    expected = _known_table_names()
    actual = set(metadata.tables)
    missing = sorted(expected - actual)
    if missing:
        raise MigrationError(f'Target schema is missing tables: {missing}')

    with engine.connect() as connection:
        nonempty = {
            name: connection.execute(
                select(func.count()).select_from(metadata.tables[name])
            ).scalar_one()
            for name in sorted(expected)
        }
    nonempty = {name: count for name, count in nonempty.items() if count}
    if nonempty:
        raise MigrationError(
            f'Target database is not empty: {nonempty}'
        )
    return metadata


def _copy_order(metadata: MetaData) -> list[str]:
    """Topologically order only non-null foreign-key dependencies.

    Nullable foreign keys can be inserted as NULL and restored after all rows
    exist. This breaks the intentional Game/Player/Figure/ActiveSpell and
    Land/Kingdom/LandConfig cycles without disabling PostgreSQL constraints.
    """
    names = _known_table_names()
    dependencies: dict[str, set[str]] = {}
    for name in names:
        table = metadata.tables[name]
        dependencies[name] = {
            fk.column.table.name
            for fk in table.foreign_keys
            if not fk.parent.nullable and fk.column.table.name != name
        }

    ordered: list[str] = []
    remaining = set(names)
    while remaining:
        ready = sorted(
            name
            for name in remaining
            if not (dependencies[name] & remaining)
        )
        if not ready:
            cycle = {
                name: sorted(dependencies[name] & remaining)
                for name in sorted(remaining)
            }
            raise MigrationError(
                f'Non-null foreign-key dependency cycle: {cycle}'
            )
        ordered.extend(ready)
        remaining.difference_update(ready)
    return ordered


def _primary_key_values(table: Table, row: dict) -> dict:
    return {
        column.name: row[column.name]
        for column in table.primary_key.columns
    }


def _copy_rows(
    source_connection,
    target_connection,
    source_metadata: MetaData,
    target_metadata: MetaData,
) -> dict[str, int]:
    inserted_tables: set[str] = set()
    deferred_updates: dict[str, list[tuple[dict, dict]]] = defaultdict(list)
    row_counts: dict[str, int] = {}

    for name in _copy_order(target_metadata):
        source_table = source_metadata.tables[name]
        target_table = target_metadata.tables[name]
        rows = [
            dict(row)
            for row in source_connection.execute(
                select(source_table)
            ).mappings()
        ]
        row_counts[name] = len(rows)

        insert_rows = []
        for source_row in rows:
            target_row = dict(source_row)
            deferred_values = {}
            for foreign_key in target_table.foreign_keys:
                column = foreign_key.parent
                referenced_table = foreign_key.column.table.name
                if (
                    column.nullable
                    and target_row.get(column.name) is not None
                    and (
                        referenced_table not in inserted_tables
                        or referenced_table == name
                    )
                ):
                    deferred_values[column.name] = target_row[column.name]
                    target_row[column.name] = None
            if deferred_values:
                deferred_updates[name].append((
                    _primary_key_values(target_table, source_row),
                    deferred_values,
                ))
            insert_rows.append(target_row)

        for offset in range(0, len(insert_rows), COPY_BATCH_SIZE):
            target_connection.execute(
                target_table.insert(),
                insert_rows[offset:offset + COPY_BATCH_SIZE],
            )
        inserted_tables.add(name)

    for name in _copy_order(target_metadata):
        table = target_metadata.tables[name]
        for primary_key, values in deferred_updates[name]:
            predicate = [
                table.c[column_name] == value
                for column_name, value in primary_key.items()
            ]
            target_connection.execute(
                update(table).where(*predicate).values(**values)
            )
    return row_counts


def _reset_postgres_sequences(connection, metadata: MetaData) -> None:
    if connection.dialect.name != 'postgresql':
        return
    for name in sorted(_known_table_names()):
        table = metadata.tables[name]
        if len(table.primary_key.columns) != 1:
            continue
        primary_key = next(iter(table.primary_key.columns))
        if not isinstance(primary_key.type, Integer):
            continue
        maximum = connection.execute(
            select(func.max(primary_key))
        ).scalar_one_or_none()
        sequence = connection.execute(
            text('SELECT pg_get_serial_sequence(:table_name, :column_name)'),
            {'table_name': name, 'column_name': primary_key.name},
        ).scalar_one_or_none()
        if not sequence:
            continue
        value = int(maximum or 1)
        connection.execute(
            text('SELECT setval(CAST(:sequence AS regclass), :value, :called)'),
            {
                'sequence': sequence,
                'value': value,
                'called': maximum is not None,
            },
        )


def _validate_foreign_keys(connection, metadata: MetaData) -> None:
    violations = {}
    for name in sorted(_known_table_names()):
        child = metadata.tables[name]
        for foreign_key in child.foreign_keys:
            parent = foreign_key.column.table
            child_alias = child.alias('child')
            parent_alias = parent.alias('parent')
            child_column = child_alias.c[foreign_key.parent.name]
            parent_column = parent_alias.c[foreign_key.column.name]
            orphan_count = connection.execute(
                select(func.count())
                .select_from(
                    child_alias.outerjoin(
                        parent_alias,
                        child_column == parent_column,
                    )
                )
                .where(
                    child_column.is_not(None),
                    parent_column.is_(None),
                )
            ).scalar_one()
            if orphan_count:
                key = (
                    f'{name}.{foreign_key.parent.name}->'
                    f'{parent.name}.{foreign_key.column.name}'
                )
                violations[key] = orphan_count
    if violations:
        raise MigrationError(f'Foreign-key validation failed: {violations}')


def _validate_row_counts(
    connection,
    metadata: MetaData,
    expected_counts: dict[str, int],
) -> None:
    mismatches = {}
    for name, expected in sorted(expected_counts.items()):
        actual = connection.execute(
            select(func.count()).select_from(metadata.tables[name])
        ).scalar_one()
        if actual != expected:
            mismatches[name] = {'source': expected, 'target': actual}
    if mismatches:
        raise MigrationError(f'Row-count validation failed: {mismatches}')


def _domain_summary(connection, metadata: MetaData) -> dict[str, int]:
    summary_tables = (
        'user',
        'collection_card',
        'game',
        'land_config',
        'kingdom',
        'region_champion',
        'land',
    )
    summary = {
        name: connection.execute(
            select(func.count()).select_from(metadata.tables[name])
        ).scalar_one()
        for name in summary_tables
    }
    game = metadata.tables['game']
    summary['open_or_active_games'] = connection.execute(
        select(func.count()).select_from(game).where(
            game.c.state.in_(('open', 'active'))
        )
    ).scalar_one()
    land = metadata.tables['land']
    summary['owned_lands'] = connection.execute(
        select(func.count()).select_from(land).where(
            land.c.owner_user_id.is_not(None)
        )
    ).scalar_one()
    return summary


def migrate(
    source_path: Path,
    target_url: str,
    *,
    allow_sqlite_target_for_tests: bool = False,
) -> tuple[dict[str, int], dict[str, int]]:
    validate_sqlite_source(source_path)
    source_engine = create_engine(_sqlite_url(source_path))
    target_engine = create_engine(target_url, pool_pre_ping=True)
    if (
        target_engine.dialect.name != 'postgresql'
        and not allow_sqlite_target_for_tests
    ):
        raise MigrationError(
            'Target must be PostgreSQL; refusing non-production target dialect '
            f'{target_engine.dialect.name!r}'
        )

    try:
        source_metadata = _reflect_and_validate_source(source_engine)
        target_metadata = _prepare_empty_target(target_engine)
        with source_engine.connect() as source_connection:
            with target_engine.begin() as target_connection:
                row_counts = _copy_rows(
                    source_connection,
                    target_connection,
                    source_metadata,
                    target_metadata,
                )
                _reset_postgres_sequences(
                    target_connection,
                    target_metadata,
                )
                _validate_row_counts(
                    target_connection,
                    target_metadata,
                    row_counts,
                )
                _validate_foreign_keys(
                    target_connection,
                    target_metadata,
                )
                summary = _domain_summary(
                    target_connection,
                    target_metadata,
                )
        return row_counts, summary
    finally:
        source_engine.dispose()
        target_engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--source',
        type=Path,
        required=True,
        help='Path to the current SQLite backup',
    )
    parser.add_argument(
        '--target-url-env',
        default='TARGET_DATABASE_URL',
        help='Environment variable containing the PostgreSQL SQLAlchemy URL',
    )
    args = parser.parse_args()

    target_url = os.environ.get(args.target_url_env)
    if not target_url:
        parser.error(
            f'{args.target_url_env} must contain the target PostgreSQL URL'
        )

    try:
        row_counts, summary = migrate(args.source, target_url)
    except MigrationError as exc:
        print(f'Migration refused: {exc}', file=sys.stderr)
        return 1
    except Exception as exc:
        print(
            f'Migration failed and the data transaction was rolled back: {exc}',
            file=sys.stderr,
        )
        return 1

    print(
        f'Migration complete: {sum(row_counts.values())} rows across '
        f'{len(row_counts)} tables'
    )
    for name, count in sorted(summary.items()):
        print(f'  {name}: {count}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
