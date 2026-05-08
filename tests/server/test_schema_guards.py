# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Startup schema guards for persistent deployments."""

from sqlalchemy import inspect

from kingdom_service import ensure_conquer_tactics_schema
from models import ConquerTactic


def test_ensure_conquer_tactics_schema_recreates_table_and_indexes(db):
    table = ConquerTactic.__table__
    index = next(iter(table.indexes))

    table.drop(bind=db.engine, checkfirst=True)
    inspector = inspect(db.engine)
    assert table.name not in inspector.get_table_names()

    ensured = ensure_conquer_tactics_schema()

    inspector = inspect(db.engine)
    assert table.name in inspector.get_table_names()
    assert table.name in ensured
    assert index.name in {item['name'] for item in inspector.get_indexes(table.name)}

    index.drop(bind=db.engine, checkfirst=True)
    inspector = inspect(db.engine)
    assert index.name not in {item['name'] for item in inspector.get_indexes(table.name)}

    ensured = ensure_conquer_tactics_schema()

    inspector = inspect(db.engine)
    assert index.name in ensured
    assert index.name in {item['name'] for item in inspector.get_indexes(table.name)}
