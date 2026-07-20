"""Regression tests for the authenticated Conquer smoke command."""

from __future__ import annotations

import pytest

from scripts.smoke_conquer_api import (
    _assert_advance_race,
    _assert_advance_withdraw_race,
    _request_json,
    _request_json_result,
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


def test_race_result_omits_full_game_snapshot(monkeypatch):
    response = _Response({
        'success': True,
        'figure_name': 'Test King',
        'game': {'players': [{'main_hand': list(range(100))}]},
    })
    session = _Session(response)
    monkeypatch.setattr(
        'scripts.smoke_conquer_api.requests.Session',
        lambda: session,
    )

    class _Start:
        @staticmethod
        def wait(timeout):
            assert timeout == 5

    result = _request_json_result(
        'POST',
        'https://example.invalid/games/advance_figure',
        token='secret',
        timeout=5,
        json_payload={'game_id': 1},
        start=_Start(),
    )

    assert result['payload'] == {
        'success': True,
        'figure_name': 'Test King',
    }


@pytest.mark.parametrize('advance_status', [200, 409])
def test_advance_withdraw_race_accepts_both_lock_orders(advance_status):
    _assert_advance_withdraw_race([
        {
            'action': 'advance',
            'status_code': advance_status,
            'payload': {'success': advance_status == 200},
        },
        {
            'action': 'withdraw',
            'status_code': 200,
            'payload': {'success': True},
        },
    ])


def test_advance_withdraw_race_requires_successful_withdrawal():
    with pytest.raises(RuntimeError, match='serialized outcome'):
        _assert_advance_withdraw_race([
            {
                'action': 'advance',
                'status_code': 200,
                'payload': {'success': True},
            },
            {
                'action': 'withdraw',
                'status_code': 500,
                'payload': {'success': False},
            },
        ])
