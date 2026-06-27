# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Versioned, ordered, idempotent schema migrations.

This formalizes the pre-existing ``ensure_*()`` pattern:

- ``db.create_all()`` (run by server.py before this) creates missing
  *tables* for brand-new models.
- The MIGRATIONS list below handles everything else: added columns,
  backfills, data fixes. Applied versions are recorded in the
  ``schema_version`` table so each migration runs exactly once per
  database, in order.

Adding a migration:

1. Append ``(version, description, callable)`` to MIGRATIONS with the next
   integer version. Never renumber, edit, or remove an applied entry.
2. The callable runs inside an app context. Make it idempotent anyway —
   databases that predate this runner get all historical migrations
   replayed against an already-current schema, and idempotence makes
   that (and any partial-failure rerun) safe.
3. For SQLite-compatible column adds, follow the existing helpers in
   kingdom_service.py: inspect the table, ``ALTER TABLE ... ADD COLUMN``
   only when missing.

Production: ``deploy_server.sh`` backs up the live database before every
deploy, and this runner executes at import time on PythonAnywhere reload.
NEVER "migrate" production by resetting the database.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import text

from models import db

logger = logging.getLogger('nepalkings.migrations')


def _utcnow_iso():
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=' ',
                                                                     timespec='seconds')


# ── Migration callables ────────────────────────────────────────────
# 0001–0007 wrap the historical ensure_* helpers (all idempotent).

def _m_kingdom_production_columns():
    from kingdom_service import ensure_kingdom_production_columns
    ensure_kingdom_production_columns()


def _m_game_ai_seed_column():
    from kingdom_service import ensure_game_ai_seed_column
    ensure_game_ai_seed_column()


def _m_game_victory_reviewed_at_column():
    from kingdom_service import ensure_game_victory_reviewed_at_column
    ensure_game_victory_reviewed_at_column()


def _m_duel_game_limit_columns():
    from kingdom_service import ensure_duel_game_limit_columns
    ensure_duel_game_limit_columns()


def _m_conquer_tactics_schema():
    from kingdom_service import ensure_conquer_tactics_schema
    ensure_conquer_tactics_schema()


def _m_onboarding_state_column():
    from onboarding_service import ensure_onboarding_state_column
    ensure_onboarding_state_column()


def _m_user_legal_columns():
    from user_schema_service import ensure_user_legal_columns
    ensure_user_legal_columns()


def _add_column_if_missing(table, column, ddl_type):
    """ALTER TABLE helper, safe on SQLite and MySQL. Returns True if added."""
    from sqlalchemy import inspect as sa_inspect
    inspector = sa_inspect(db.engine)
    if table not in inspector.get_table_names():
        return False
    existing = {col['name'] for col in inspector.get_columns(table)}
    if column in existing:
        return False
    quoted = f'"{table}"' if table == 'user' else table
    db.session.execute(text(f'ALTER TABLE {quoted} ADD COLUMN {column} {ddl_type}'))
    db.session.commit()
    return True


def _m_user_notify_emails_enabled():
    _add_column_if_missing('user', 'notify_emails_enabled',
                           'BOOLEAN NOT NULL DEFAULT 1')


def _m_game_turn_email_log():
    _add_column_if_missing('game', 'turn_email_log', 'JSON')


# ── Registry ───────────────────────────────────────────────────────

MIGRATIONS = [
    (1, 'kingdom production columns', _m_kingdom_production_columns),
    (2, 'game.ai_seed column', _m_game_ai_seed_column),
    (3, 'game.victory_reviewed_at column', _m_game_victory_reviewed_at_column),
    (4, 'duel game_limit columns', _m_duel_game_limit_columns),
    (5, 'conquer tactics schema', _m_conquer_tactics_schema),
    (6, 'user.onboarding_state column', _m_onboarding_state_column),
    (7, 'user legal columns', _m_user_legal_columns),
    (8, 'user.notify_emails_enabled column', _m_user_notify_emails_enabled),
    (9, 'game.turn_email_log column', _m_game_turn_email_log),
]


# ── Runner ─────────────────────────────────────────────────────────

def _ensure_version_table():
    db.session.execute(text(
        'CREATE TABLE IF NOT EXISTS schema_version ('
        ' version INTEGER PRIMARY KEY,'
        ' description VARCHAR(200),'
        ' applied_at VARCHAR(32))'
    ))
    db.session.commit()


def applied_versions():
    _ensure_version_table()
    rows = db.session.execute(text('SELECT version FROM schema_version')).fetchall()
    return {row[0] for row in rows}


def run_migrations():
    """Apply all pending migrations in order. Returns list of applied versions.

    Stops at the first failing migration (after rollback) so later
    migrations never run against an unexpected intermediate schema.
    """
    applied = applied_versions()
    ran = []
    for version, description, fn in sorted(MIGRATIONS, key=lambda m: m[0]):
        if version in applied:
            continue
        try:
            fn()
            db.session.execute(
                text('INSERT INTO schema_version (version, description, applied_at)'
                     ' VALUES (:v, :d, :t)'),
                {'v': version, 'd': description, 't': _utcnow_iso()})
            db.session.commit()
            ran.append(version)
            logger.info('Migration %04d applied: %s', version, description)
        except Exception:
            db.session.rollback()
            logger.exception('Migration %04d FAILED: %s — halting migration run',
                             version, description)
            raise
    return ran
