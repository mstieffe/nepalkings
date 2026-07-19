# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Production startup must be explicit, safe, and database-read-only."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys


SERVER_DIR = Path(__file__).resolve().parents[2] / 'server'


def _deployed_environment(environment_name='production', **overrides):
    environment = os.environ.copy()
    for name in (
        'DB_URL',
        'DATABASE_URL',
        'FLASK_ENV',
        'ENV',
        'NEPAL_KINGS_ENV_FILE',
        'ALLOW_PRODUCTION_SQLITE',
        'STARTUP_MAINTENANCE_ENABLED',
        'BACKGROUND_SERVICES_ENABLED',
    ):
        environment.pop(name, None)
    environment.update({
        'APP_ENVIRONMENT': environment_name,
        'SECRET_KEY': 'production-startup-test-secret',
        'AI_ENABLED': 'False',
        'DISABLE_BACKGROUND_SWEEPERS': '1',
    })
    environment.update(overrides)
    return environment


def _run_import(script, environment):
    return subprocess.run(
        [sys.executable, '-c', script],
        cwd=SERVER_DIR,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )


def test_production_requires_explicit_database_url():
    result = _run_import(
        'import server',
        _deployed_environment(),
    )

    assert result.returncode != 0
    assert 'DB_URL must be set explicitly' in result.stderr


def test_production_rejects_sqlite_without_legacy_override(tmp_path):
    database_path = tmp_path / 'forbidden.db'
    result = _run_import(
        'import server',
        _deployed_environment(
            DB_URL=f'sqlite:///{database_path}',
        ),
    )

    assert result.returncode != 0
    assert 'SQLite is disabled' in result.stderr
    assert not database_path.exists()


def test_production_wsgi_import_and_healthz_do_not_touch_database(tmp_path):
    database_path = tmp_path / 'legacy-fallback.db'
    script = (
        'from pathlib import Path\n'
        'import wsgi\n'
        f'database_path = Path({str(database_path)!r})\n'
        'assert not database_path.exists()\n'
        'response = wsgi.application.test_client().get("/healthz")\n'
        'assert response.status_code == 200\n'
        'assert response.get_json()["environment"] == "production"\n'
        'assert not database_path.exists()\n'
    )
    result = _run_import(
        script,
        _deployed_environment(
            DB_URL=f'sqlite:///{database_path}',
            ALLOW_PRODUCTION_SQLITE='True',
        ),
    )

    assert result.returncode == 0, result.stderr
    assert not database_path.exists()


def test_staging_wsgi_import_does_not_run_startup_maintenance(tmp_path):
    database_path = tmp_path / 'staging.db'
    result = _run_import(
        (
            'from pathlib import Path\n'
            'import wsgi\n'
            f'database_path = Path({str(database_path)!r})\n'
            'assert not database_path.exists()\n'
        ),
        _deployed_environment(
            'staging',
            DB_URL=f'sqlite:///{database_path}',
            ALLOW_PRODUCTION_SQLITE='True',
        ),
    )

    assert result.returncode == 0, result.stderr
    assert not database_path.exists()
