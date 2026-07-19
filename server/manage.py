#!/usr/bin/env python3
# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Nepal Kings server management commands."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv


def _load_private_environment():
    env_file = os.environ.get('NEPAL_KINGS_ENV_FILE')
    if not env_file:
        return
    path = Path(env_file).expanduser()
    if not path.is_file():
        raise RuntimeError(f'NEPAL_KINGS_ENV_FILE does not exist: {path}')
    load_dotenv(path, override=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'command',
        choices=('prepare-database', 'run-worker'),
    )
    args = parser.parse_args()

    _load_private_environment()

    # This command owns database preparation. Never let importing the WSGI
    # application perform the same work first, even if a local environment
    # file enables the historical development convenience.
    os.environ['STARTUP_MAINTENANCE_ENABLED'] = 'False'
    os.environ['BACKGROUND_SERVICES_ENABLED'] = 'False'

    # Import only after the private environment has been loaded.
    from server import app
    if args.command == 'prepare-database':
        from startup import prepare_database

        prepare_database(app)
        print('Database preparation completed successfully')
        return 0
    if args.command == 'run-worker':
        from background_worker import run_forever

        run_forever(app)
        return 0
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
