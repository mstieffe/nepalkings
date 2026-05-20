# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for login screen auth response helpers."""


class _FakeResponse:
    def __init__(self, payload=None, error=None):
        self._payload = payload
        self._error = error

    def json(self):
        if self._error:
            raise self._error
        return self._payload


def test_response_error_message_uses_server_message():
    from game.screens.login_screen import _response_error_message

    resp = _FakeResponse({
        'success': False,
        'message': 'Password must be at least 6 characters',
    })

    assert _response_error_message(resp, 'Request failed (400). Please try again.') == (
        'Password must be at least 6 characters'
    )


def test_response_error_message_falls_back_without_message():
    from game.screens.login_screen import _response_error_message

    assert _response_error_message(_FakeResponse({}), 'fallback') == 'fallback'
    assert _response_error_message(_FakeResponse(error=ValueError()), 'fallback') == 'fallback'
