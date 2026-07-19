# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Database-related runtime configuration."""
import os

# ── Database URL ──────────────────────────────────────────────────
_configured_db_url = os.getenv('DB_URL') or os.getenv('DATABASE_URL')
DB_URL_FROM_ENV = bool(_configured_db_url)
DB_URL = _configured_db_url or 'sqlite:///test.db'

# Some providers still expose the deprecated postgres:// scheme. SQLAlchemy
# requires an explicit dialect/driver name for Psycopg 3.
if DB_URL.startswith('postgres://'):
    DB_URL = 'postgresql+psycopg://' + DB_URL[len('postgres://'):]
elif DB_URL.startswith('postgresql://'):
    DB_URL = 'postgresql+psycopg://' + DB_URL[len('postgresql://'):]

ALLOW_PRODUCTION_SQLITE = (
    os.getenv('ALLOW_PRODUCTION_SQLITE', 'False').lower() == 'true'
)

# Keep pools deliberately small because each PythonAnywhere WSGI worker has
# its own SQLAlchemy pool. The values can be tuned after the concurrency test.
DB_POOL_SIZE = max(1, int(os.getenv('DB_POOL_SIZE', '2')))
DB_MAX_OVERFLOW = max(0, int(os.getenv('DB_MAX_OVERFLOW', '1')))
DB_POOL_TIMEOUT_SECONDS = max(
    1, int(os.getenv('DB_POOL_TIMEOUT_SECONDS', '10'))
)
DB_POOL_RECYCLE_SECONDS = max(
    30, int(os.getenv('DB_POOL_RECYCLE_SECONDS', '280'))
)

# Keep SQLite's busy wait shorter than the client's HTTP timeout. A persistent
# writer should produce a retryable JSON response instead of looking like a
# network outage after the client gives up at ten seconds.
SQLITE_BUSY_TIMEOUT_SECONDS = max(
    0.25, float(os.getenv('SQLITE_BUSY_TIMEOUT_SECONDS', '5.0')))

# ── Schema reset on startup ───────────────────────────────────────
# When True the server drops and recreates all tables on startup -- useful
# for local schema iteration but DESTRUCTIVE in production. Default is
# False; opt in explicitly via env var when you really want it.
DROP_TABLES_ON_STARTUP = os.getenv('DROP_TABLES_ON_STARTUP', 'False').lower() == 'true'
