# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Database-related runtime configuration."""
import os

# ── Database URL ──────────────────────────────────────────────────
DB_URL = os.getenv('DB_URL', 'sqlite:///test.db')

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
