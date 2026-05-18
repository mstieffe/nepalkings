# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Create or refresh a local gameplay test account.

This is intentionally a maintenance script, not a server route.  It writes a
hashed password through the normal User model and can be rerun whenever the
test account needs its gold topped back up.
"""
from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
from dataclasses import dataclass

from flask import Flask


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
SERVER_DIR = os.path.join(REPO_ROOT, 'server')
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from models import User, db  # noqa: E402
import server_settings as settings  # noqa: E402


USERNAME_RE = re.compile(r'^[a-zA-Z0-9_-]+$')
DEV_ENVS = {'', 'dev', 'development', 'local', 'test'}
DEFAULT_USERNAME = 'KingMerk'
DEFAULT_GOLD = 100_000


@dataclass(frozen=True)
class UpsertResult:
    username: str
    gold: int
    created: bool
    password_updated: bool


def _is_development_environment() -> bool:
    env = (os.getenv('FLASK_ENV') or os.getenv('ENV') or '').strip().lower()
    return env in DEV_ENVS


def _validate_username(username: str) -> None:
    if not 3 <= len(username) <= 30:
        raise ValueError('username must be 3-30 characters')
    if not USERNAME_RE.match(username):
        raise ValueError('username may only contain letters, digits, hyphens, and underscores')


def _validate_gold(gold: int) -> None:
    if gold < 0:
        raise ValueError('gold must be zero or greater')


def create_app(db_url: str) -> Flask:
    """Build a tiny Flask app bound to the same instance folder as server.py."""
    app = Flask(
        'nepalkings_test_account_upsert',
        instance_path=os.path.join(SERVER_DIR, 'instance'),
    )
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_pre_ping': True,
        'connect_args': {
            'timeout': 30,
            'check_same_thread': False,
        },
    }
    db.init_app(app)
    return app


def upsert_test_account(
    username: str,
    password: str | None,
    gold: int,
    *,
    preserve_password: bool = False,
) -> UpsertResult:
    """Create or update a human test account in the active app context."""
    username = username.strip()
    _validate_username(username)
    _validate_gold(gold)

    if not preserve_password and not password:
        raise ValueError('password is required unless --preserve-password is used')

    user = User.query.filter_by(username=username).first()
    created = user is None
    password_updated = False

    if created:
        if not password:
            raise ValueError('password is required when creating the account')
        user = User(
            username=username,
            gold=gold,
            is_ai=False,
            booster_packs=settings.STARTER_BOOSTER_PACKS,
            booster_packs_side=settings.STARTER_BOOSTER_PACKS_SIDE,
            maps=settings.STARTER_MAPS,
        )
        user.set_password(password)
        db.session.add(user)
        password_updated = True
    else:
        user.gold = gold
        user.is_ai = False
        if not preserve_password:
            user.set_password(password)
            password_updated = True

    db.session.commit()
    return UpsertResult(
        username=user.username,
        gold=int(user.gold),
        created=created,
        password_updated=password_updated,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Create or refresh a local Nepal Kings gameplay test account.',
    )
    parser.add_argument(
        '--username',
        default=os.getenv('NK_TEST_ACCOUNT_USERNAME', DEFAULT_USERNAME),
        help=f'Account username. Defaults to {DEFAULT_USERNAME!r}.',
    )
    parser.add_argument(
        '--gold',
        type=int,
        default=int(os.getenv('NK_TEST_ACCOUNT_GOLD', str(DEFAULT_GOLD))),
        help=f'Gold balance to set. Defaults to {DEFAULT_GOLD}.',
    )
    parser.add_argument(
        '--password',
        default=os.getenv('NK_TEST_ACCOUNT_PASSWORD'),
        help='Password to set. Prefer NK_TEST_ACCOUNT_PASSWORD or the hidden prompt.',
    )
    parser.add_argument(
        '--preserve-password',
        action='store_true',
        help='Update gold without changing the password for an existing account.',
    )
    parser.add_argument(
        '--db-url',
        default=os.getenv('DB_URL', settings.DB_URL),
        help='Database URL. Defaults to DB_URL/server settings.',
    )
    parser.add_argument(
        '--allow-non-dev',
        action='store_true',
        help='Allow running when FLASK_ENV/ENV is not development/local/test.',
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if not args.allow_non_dev and not _is_development_environment():
        print(
            'Refusing to upsert a test account outside a development environment. '
            'Set FLASK_ENV=development or pass --allow-non-dev if this is intentional.',
            file=sys.stderr,
        )
        return 2

    password = args.password
    if not args.preserve_password and not password:
        password = getpass.getpass(f'Password for {args.username}: ')

    app = create_app(args.db_url)
    with app.app_context():
        db.create_all()
        try:
            result = upsert_test_account(
                args.username,
                password,
                args.gold,
                preserve_password=args.preserve_password,
            )
        except Exception:
            db.session.rollback()
            raise

    action = 'created' if result.created else 'updated'
    password_note = 'password updated' if result.password_updated else 'password preserved'
    print(f'{action} {result.username}: gold={result.gold}, {password_note}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
