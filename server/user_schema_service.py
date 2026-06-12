# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Idempotent user-table schema helpers for lightweight deployments."""

from sqlalchemy import inspect, text

from models import db


def ensure_user_legal_columns():
    inspector = inspect(db.engine)
    existing = {col['name'] for col in inspector.get_columns('user')}
    added = []
    columns = {
        'age_confirmed': 'BOOLEAN DEFAULT 0 NOT NULL',
        'age_confirmed_at': 'DATETIME',
        'terms_version': 'VARCHAR(32)',
        'terms_accepted_at': 'DATETIME',
        'privacy_version': 'VARCHAR(32)',
        'privacy_accepted_at': 'DATETIME',
    }
    for name, ddl in columns.items():
        if name in existing:
            continue
        db.session.execute(text(f'ALTER TABLE user ADD COLUMN {name} {ddl}'))
        added.append(name)
    if added:
        db.session.commit()
    return added
