# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Desktop authentication errors should preserve safe server guidance."""

import importlib
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def auth_service(monkeypatch):
    # Client settings load image assets at import time using app-relative
    # paths, matching the desktop launcher's working directory.
    monkeypatch.chdir(ROOT / 'nepal_kings')
    return importlib.import_module('utils.auth_service')


class _Response:
    def __init__(self, status_code, payload, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        raise AssertionError('expected status to be handled before raise_for_status')


def _maintenance_response():
    return _Response(
        503,
        {
            'success': False,
            'message': 'Nepal Kings is temporarily unavailable for maintenance.',
            'reason': 'maintenance',
            'retryable': True,
        },
        {'Retry-After': '300'},
    )


def test_desktop_login_shows_server_maintenance_message(
        monkeypatch, auth_service):
    monkeypatch.setattr(
        auth_service.requests,
        'post',
        lambda *args, **kwargs: _maintenance_response(),
    )

    result = auth_service.login('player', 'password123')

    assert result == {
        'success': False,
        'message': 'Nepal Kings is temporarily unavailable for maintenance.',
        'reason': 'maintenance',
        'retryable': True,
        'retry_after': '300',
    }


def test_desktop_registration_shows_server_maintenance_message(
        monkeypatch, auth_service):
    monkeypatch.setattr(
        auth_service.requests,
        'post',
        lambda *args, **kwargs: _maintenance_response(),
    )

    result = auth_service.register(
        'player',
        'password123',
        legal_confirmed=True,
    )

    assert result == {
        'success': False,
        'message': 'Nepal Kings is temporarily unavailable for maintenance.',
        'reason': 'maintenance',
        'retryable': True,
        'retry_after': '300',
    }
