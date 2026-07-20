"""Regression tests for the authenticated Conquer smoke command."""

from __future__ import annotations

import pytest

from scripts.smoke_conquer_api import (
    _assert_advance_race,
    _request_json,
    _safe_payload,
)


class _Response:
    def __init__(self, payload, *, ok=True, status_code=200):
        self._payload = payload
        self.ok = ok
        self.status_code = status_code

    def json(self):
        return self._payload


class _Session:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.response


def test_request_accepts_successful_legacy_payload_without_success_key():
    session = _Session(_Response({'lands': [], 'recommended_tutorial_land_id': 1}))

    payload, elapsed_ms = _request_json(
        session,
        'GET',
        'https://example.invalid/kingdom/map',
        timeout=5,
    )

    assert payload['recommended_tutorial_land_id'] == 1
    assert elapsed_ms >= 0


def test_request_rejects_explicit_success_false():
    session = _Session(_Response({'success': False, 'message': 'nope'}))

    with pytest.raises(RuntimeError, match='nope'):
        _request_json(
            session,
            'POST',
            'https://example.invalid/action',
            timeout=5,
        )


def test_safe_payload_redacts_credentials_and_summarizes_large_lists():
    safe = _safe_payload({
        'token': 'secret-token',
        'nested': {'password': 'secret-password'},
        'lands': list(range(21)),
    })

    assert safe['token'] == '<redacted>'
    assert safe['nested']['password'] == '<redacted>'
    assert safe['lands'] == '<21 items>'


def test_advance_race_requires_one_success_and_one_rejection():
    _assert_advance_race([
        {'status_code': 200, 'payload': {'success': True}},
        {'status_code': 400, 'payload': {'success': False}},
    ])


def test_advance_race_rejects_two_successes():
    with pytest.raises(RuntimeError, match='did not serialize'):
        _assert_advance_race([
            {'status_code': 200, 'payload': {'success': True}},
            {'status_code': 200, 'payload': {'success': True}},
        ])
