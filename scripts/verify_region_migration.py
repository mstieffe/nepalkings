#!/usr/bin/env python3
"""Dry-run migration 14 against a copied production-like SQLite backup.

The source backup is never opened for writing.  A successful run proves that
the copy reaches the exact regional-map shape while preserving account-scoped
inventory tables and passing SQLite integrity/foreign-key checks.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path


TARGET_VERSION = 14
TARGET_LANDS = 4_800
TARGET_REGIONS = 5
PRESERVED_TABLES = (
    'user',
    'collection_card',
    'figure',
    'kingdom_loot_event',
    'kingdom_message',
)


def _scalar(connection, sql):
    row = connection.execute(sql).fetchone()
    return row[0] if row else None


def _counts(connection):
    return {
        table: int(_scalar(connection, f'SELECT COUNT(*) FROM "{table}"') or 0)
        for table in PRESERVED_TABLES
    }


def verify(backup_path: Path) -> None:
    if not backup_path.is_file() or backup_path.stat().st_size <= 0:
        raise RuntimeError(f'Backup is missing or empty: {backup_path}')

    with sqlite3.connect(f'file:{backup_path}?mode=ro', uri=True) as source:
        if _scalar(source, 'PRAGMA integrity_check') != 'ok':
            raise RuntimeError('Source backup failed PRAGMA integrity_check')
        before = _counts(source)
        active = int(_scalar(
            source,
            "SELECT COUNT(*) FROM game WHERE mode='conquer' "
            "AND state IN ('open', 'active')") or 0)
        if active:
            raise RuntimeError(
                f'Regional reset blocked by {active} open/active Conquer games')

    with tempfile.TemporaryDirectory(prefix='nk-region-migration-') as tmp_dir:
        migrated_path = Path(tmp_dir) / 'migration-dry-run.db'
        shutil.copy2(backup_path, migrated_path)

        repo_root = Path(__file__).resolve().parents[1]
        server_dir = repo_root / 'server'
        sys.path.insert(0, str(server_dir))
        os.environ['DB_URL'] = f'sqlite:///{migrated_path}'
        os.environ['AI_ENABLED'] = 'False'
        os.environ['DEBUG_ENABLED'] = 'False'

        # Importing the app runs the same create_all + migration path used on
        # PythonAnywhere reload.  The process exits immediately after checks.
        __import__('server')

        with sqlite3.connect(migrated_path) as migrated:
            version = int(_scalar(
                migrated,
                'SELECT COALESCE(MAX(version), 0) FROM schema_version') or 0)
            if version < TARGET_VERSION:
                raise RuntimeError(
                    f'Migration did not reach version {TARGET_VERSION} (got {version})')
            if _scalar(migrated, 'PRAGMA integrity_check') != 'ok':
                raise RuntimeError('Migrated copy failed PRAGMA integrity_check')
            fk_errors = list(migrated.execute('PRAGMA foreign_key_check'))
            if fk_errors:
                raise RuntimeError(
                    f'Migrated copy has {len(fk_errors)} foreign-key violations')

            lands, regions, missing_regions = migrated.execute(
                'SELECT COUNT(*), COUNT(DISTINCT region), '
                'SUM(CASE WHEN region IS NULL THEN 1 ELSE 0 END) FROM land'
            ).fetchone()
            if (lands, regions, int(missing_regions or 0)) != (
                    TARGET_LANDS, TARGET_REGIONS, 0):
                raise RuntimeError(
                    'Unexpected generated map: '
                    f'{lands} lands, {regions} regions, {missing_regions} missing')

            after = _counts(migrated)
            changed = {
                table: (before[table], after[table])
                for table in PRESERVED_TABLES
                if before[table] != after[table]
            }
            if changed:
                raise RuntimeError(f'Preserved table counts changed: {changed}')
            if int(_scalar(migrated, 'SELECT COUNT(*) FROM kingdom') or 0):
                raise RuntimeError('Old kingdom progression rows survived reset')
            if int(_scalar(
                    migrated,
                    "SELECT COUNT(*) FROM land_config "
                    "WHERE config_type='defence'") or 0):
                raise RuntimeError('Defence configurations survived reset')
            if int(_scalar(
                    migrated,
                    "SELECT COUNT(*) FROM collection_card "
                    "WHERE lock_type LIKE 'defence%'") or 0):
                raise RuntimeError('Defence card locks survived reset')

        print(
            'Region migration dry-run passed: '
            f'{TARGET_LANDS} lands, {TARGET_REGIONS} regions, '
            'preserved account inventory, clean integrity checks.'
        )


def main() -> int:
    if len(sys.argv) != 2:
        print(f'Usage: {Path(sys.argv[0]).name} <sqlite-backup>', file=sys.stderr)
        return 2
    try:
        verify(Path(sys.argv[1]).expanduser().resolve())
    except Exception as exc:
        print(f'Region migration verification failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
