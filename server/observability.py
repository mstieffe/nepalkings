# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Small, dependency-free production logging helpers.

The beta does not need a tracing platform. It does need machine-readable,
redacted logs and a request identifier that can be reported by a player and
found in the provider log.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from flask import g, has_request_context


_REDACTIONS = (
    (
        re.compile(r'(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+'),
        'Bearer [REDACTED]',
    ),
    (
        re.compile(
            r'(?i)\b(postgresql(?:\+psycopg)?://[^:\s/]+:)[^@\s]+(@)'
        ),
        r'\1[REDACTED]\2',
    ),
    (
        re.compile(r'(?i)([?&](?:token|sig|password)=)[^&\s]+'),
        r'\1[REDACTED]',
    ),
    (
        re.compile(
            r'(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b'
        ),
        '[REDACTED_EMAIL]',
    ),
)

_EXTRA_FIELDS = (
    'event',
    'method',
    'path',
    'endpoint',
    'status',
    'duration_ms',
    'user_id',
)


def redact_log_text(value) -> str:
    """Return text with credentials, signed links, and email addresses hidden."""
    text = str(value)
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


class JsonLogFormatter(logging.Formatter):
    """Format one compact JSON object per line."""

    def __init__(self, *, environment: str, release_sha: str):
        super().__init__()
        self.environment = environment
        self.release_sha = release_sha

    def format(self, record):
        payload = {
            'timestamp': datetime.now(timezone.utc).isoformat(
                timespec='milliseconds'
            ),
            'level': record.levelname,
            'logger': record.name,
            'message': redact_log_text(record.getMessage()),
            'environment': self.environment,
            'release_sha': self.release_sha,
        }
        if has_request_context():
            request_id = getattr(g, 'request_id', None)
            if request_id:
                payload['request_id'] = request_id
        for field in _EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload['exception'] = redact_log_text(
                self.formatException(record.exc_info)
            )
        return json.dumps(
            payload,
            ensure_ascii=True,
            separators=(',', ':'),
            sort_keys=True,
        )


def configure_logging(*, environment: str, release_sha: str, debug: bool):
    """Configure root handlers without adding duplicate handlers on re-import."""
    level = logging.DEBUG if debug else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)
    formatter = JsonLogFormatter(
        environment=environment,
        release_sha=release_sha,
    )

    if not root.handlers:
        handler = logging.StreamHandler()
        root.addHandler(handler)
    for handler in root.handlers:
        handler.setLevel(level)
        handler.setFormatter(formatter)
