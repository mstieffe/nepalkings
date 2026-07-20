# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Lightweight structured logging and redaction coverage."""

import json
import logging

from observability import JsonLogFormatter, redact_log_text


def test_redaction_hides_credentials_signed_links_and_email():
    value = (
        'Bearer abc.def-123 '
        'postgresql+psycopg://role:secret-password@db.example/game '
        'https://example.test/verify?token=signed-secret&x=1 '
        'person@example.com'
    )

    redacted = redact_log_text(value)

    assert 'abc.def-123' not in redacted
    assert 'secret-password' not in redacted
    assert 'signed-secret' not in redacted
    assert 'person@example.com' not in redacted
    assert redacted.count('[REDACTED]') == 3
    assert '[REDACTED_EMAIL]' in redacted


def test_json_formatter_includes_operational_fields_and_redacts_message():
    formatter = JsonLogFormatter(
        environment='staging',
        release_sha='abc123',
    )
    record = logging.LogRecord(
        name='nepalkings.request',
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='login person@example.com Bearer signed.token',
        args=(),
        exc_info=None,
    )
    record.event = 'request_complete'
    record.method = 'POST'
    record.path = '/auth/login'
    record.endpoint = 'auth.login'
    record.status = 200
    record.duration_ms = 12.5
    record.user_id = 42

    payload = json.loads(formatter.format(record))

    assert payload['environment'] == 'staging'
    assert payload['release_sha'] == 'abc123'
    assert payload['event'] == 'request_complete'
    assert payload['method'] == 'POST'
    assert payload['path'] == '/auth/login'
    assert payload['status'] == 200
    assert payload['duration_ms'] == 12.5
    assert payload['user_id'] == 42
    assert 'person@example.com' not in payload['message']
    assert 'signed.token' not in payload['message']
