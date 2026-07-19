# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""WSGI entry point for PythonAnywhere (or any WSGI host).

In PythonAnywhere's Web tab, set the WSGI configuration file to point here:

    import sys
    sys.path.insert(0, '/home/YOUR_USERNAME/nepalkings/server')
    from wsgi import application
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# Ensure the server directory is on the path
_dir = os.path.dirname(os.path.abspath(__file__))
if _dir not in sys.path:
    sys.path.insert(0, _dir)

# Load secrets/configuration from a private file outside the repository when
# the provider WSGI file points NEPAL_KINGS_ENV_FILE at one. Dependencies must
# be installed during deployment; WSGI imports never mutate the environment.
_env_file = os.environ.get('NEPAL_KINGS_ENV_FILE')
if _env_file:
    _env_path = Path(_env_file).expanduser()
    if not _env_path.is_file():
        raise RuntimeError(
            f'NEPAL_KINGS_ENV_FILE does not exist: {_env_path}'
        )
    load_dotenv(_env_path, override=False)

# Safe non-destructive default. DB_URL must come from the private environment
# file in production; local development falls back in database_settings.py.
os.environ.setdefault('DROP_TABLES_ON_STARTUP', 'False')

from server import app as application  # noqa: E402
