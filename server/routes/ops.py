# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Public liveness, readiness, and release metadata endpoints."""

import logging

from flask import Blueprint, jsonify
from sqlalchemy import text

from migration_runner import CURRENT_SCHEMA_VERSION
from models import db
import server_settings as settings


ops = Blueprint('ops', __name__)
logger = logging.getLogger('nepalkings.ops')


def _release_metadata():
    return {
        'environment': settings.APP_ENVIRONMENT,
        'release_sha': settings.RELEASE_SHA,
        'api_version': settings.API_VERSION,
        'minimum_client_version': settings.MIN_CLIENT_VERSION,
    }


def _no_store(response):
    response.headers['Cache-Control'] = 'no-store'
    return response


@ops.route('/healthz', methods=['GET'])
def healthz():
    """Process liveness check; deliberately performs no database work."""
    response = jsonify({
        'success': True,
        'status': 'ok',
        **_release_metadata(),
    })
    return _no_store(response)


@ops.route('/readyz', methods=['GET'])
def readyz():
    """Readiness check for database connectivity and schema compatibility."""
    try:
        db.session.execute(text('SELECT 1'))
        current_schema_version = db.session.execute(
            text('SELECT MAX(version) FROM schema_version')
        ).scalar()
        current_schema_version = int(current_schema_version or 0)
        if current_schema_version != CURRENT_SCHEMA_VERSION:
            response = jsonify({
                'success': False,
                'status': 'not_ready',
                'reason': 'schema_version_mismatch',
                'schema_version': current_schema_version,
                'expected_schema_version': CURRENT_SCHEMA_VERSION,
                **_release_metadata(),
            })
            return _no_store(response), 503

        response = jsonify({
            'success': True,
            'status': 'ready',
            'database': db.engine.dialect.name,
            'schema_version': current_schema_version,
            **_release_metadata(),
        })
        return _no_store(response)
    except Exception:
        db.session.rollback()
        logger.exception('Readiness check failed')
        response = jsonify({
            'success': False,
            'status': 'not_ready',
            'reason': 'database_unavailable',
            **_release_metadata(),
        })
        return _no_store(response), 503
