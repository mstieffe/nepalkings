# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for the local gameplay test-account helper."""
import pytest
from werkzeug.security import check_password_hash

from scripts.debug.upsert_test_account import upsert_test_account


def test_upsert_test_account_creates_human_user_with_gold(db):
    result = upsert_test_account('KingMerk', 'merkeltonien', 100_000)

    from models import User
    user = User.query.filter_by(username='KingMerk').one()

    assert result.created is True
    assert result.password_updated is True
    assert user.gold == 100_000
    assert user.is_ai is False
    assert user.password_hash != 'merkeltonien'
    assert check_password_hash(user.password_hash, 'merkeltonien')


def test_upsert_test_account_refreshes_existing_user(db):
    from models import User

    first = upsert_test_account('KingMerk', 'old-password', 10)
    user = User.query.filter_by(username='KingMerk').one()
    old_hash = user.password_hash

    second = upsert_test_account('KingMerk', 'merkeltonien', 100_000)
    db.session.refresh(user)

    assert first.created is True
    assert second.created is False
    assert second.password_updated is True
    assert user.gold == 100_000
    assert user.password_hash != old_hash
    assert check_password_hash(user.password_hash, 'merkeltonien')


def test_upsert_test_account_can_preserve_existing_password(db):
    from models import User

    upsert_test_account('KingMerk', 'keep-this-password', 5)
    user = User.query.filter_by(username='KingMerk').one()
    old_hash = user.password_hash

    result = upsert_test_account(
        'KingMerk',
        password=None,
        gold=100_000,
        preserve_password=True,
    )
    db.session.refresh(user)

    assert result.created is False
    assert result.password_updated is False
    assert user.gold == 100_000
    assert user.password_hash == old_hash
    assert check_password_hash(user.password_hash, 'keep-this-password')


def test_upsert_test_account_rejects_invalid_username(db):
    with pytest.raises(ValueError):
        upsert_test_account('King Merk!', 'merkeltonien', 100_000)
