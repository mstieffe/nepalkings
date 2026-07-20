# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Deployment/runtime metadata and startup policy."""

import os


def _boolean(name, default):
    value = os.getenv(name)
    if value is None:
        return bool(default)
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


_flask_environment = (
    os.getenv('APP_ENVIRONMENT')
    or os.getenv('FLASK_ENV')
    or os.getenv('ENV')
    or 'development'
).strip().lower()

APP_ENVIRONMENT = _flask_environment
IS_DEVELOPMENT = APP_ENVIRONMENT in {
    'development',
    'dev',
    'local',
    'test',
}
IS_PRODUCTION = APP_ENVIRONMENT in {'production', 'prod'}

# Public, non-secret release metadata exposed by /healthz and /readyz.
RELEASE_SHA = os.getenv('RELEASE_SHA', 'unknown').strip() or 'unknown'
API_VERSION = os.getenv('API_VERSION', '1').strip() or '1'
MIN_CLIENT_VERSION = (
    os.getenv('MIN_CLIENT_VERSION', '0.0.0').strip() or '0.0.0'
)

# Compress the large authenticated map snapshot at the application boundary.
# PythonAnywhere does not guarantee dynamic-response compression, and the
# uncompressed 4,800-land JSON is several megabytes.
RESPONSE_COMPRESSION_ENABLED = _boolean(
    'RESPONSE_COMPRESSION_ENABLED',
    True,
)
RESPONSE_COMPRESSION_MIN_BYTES = max(
    1024,
    int(os.getenv('RESPONSE_COMPRESSION_MIN_BYTES', '1024')),
)

# Development keeps the historical import-time convenience. Production must
# run ``python manage.py prepare-database`` explicitly before reloading WSGI.
STARTUP_MAINTENANCE_ENABLED = _boolean(
    'STARTUP_MAINTENANCE_ENABLED',
    IS_DEVELOPMENT,
)

# Production background work belongs in a dedicated always-on task. This flag
# only preserves the convenient in-process services for local development.
BACKGROUND_SERVICES_ENABLED = _boolean(
    'BACKGROUND_SERVICES_ENABLED',
    IS_DEVELOPMENT,
)

# Cutover/incident switch. A maintenance worker serves only liveness,
# readiness, and legal documents; every gameplay/auth route returns 503.
MAINTENANCE_MODE = _boolean('MAINTENANCE_MODE', False)
MAINTENANCE_MESSAGE = (
    os.getenv(
        'MAINTENANCE_MESSAGE',
        'Nepal Kings is temporarily unavailable for maintenance.',
    ).strip()
    or 'Nepal Kings is temporarily unavailable for maintenance.'
)
MAINTENANCE_RETRY_AFTER_SECONDS = max(
    1,
    int(os.getenv('MAINTENANCE_RETRY_AFTER_SECONDS', '300')),
)
