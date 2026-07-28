# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for client game-service helpers."""


class _Response:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError('raise_for_status should not hide JSON errors')


class _NonJsonResponse:
    def __init__(self, status_code):
        self.status_code = status_code

    def json(self):
        raise ValueError('Expecting value: line 1 column 1 (char 0)')


def test_create_game_preserves_server_error_message(monkeypatch):
    from utils import game_service

    def fake_post(*_args, **_kwargs):
        return _Response(400, {
            'success': False,
            'message': 'player2 does not have enough gold (5/10)',
        })

    monkeypatch.setattr(game_service.requests, 'post', fake_post)

    response = game_service.create_game(7)

    assert response == {
        'success': False,
        'message': 'player2 does not have enough gold (5/10)',
    }


def test_create_challenge_preserves_server_error_message(monkeypatch):
    from utils import game_service

    def fake_post(*_args, **_kwargs):
        return _Response(400, {
            'success': False,
            'message': 'Opponent is no longer available',
        })

    monkeypatch.setattr(game_service.requests, 'post', fake_post)

    response = game_service.create_challenge(
        'CurrentPlayer', 'MissingPlayer', stake=10, game_limit=7)

    assert response == {
        'success': False,
        'message': 'Opponent is no longer available',
    }


def test_finish_battle_reports_http_failure_instead_of_json_decode_error(
        monkeypatch):
    from utils import game_service

    monkeypatch.setattr(
        game_service.requests,
        'post',
        lambda *_args, **_kwargs: _NonJsonResponse(500),
    )

    response = game_service.finish_battle(23, 45, 0)

    assert response == {
        'success': False,
        'message': 'Server failed to finish the battle (HTTP 500). Please try again.',
    }


def test_finish_battle_reports_empty_browser_error_response(monkeypatch):
    from utils import game_service

    monkeypatch.setattr(
        game_service.requests,
        'post',
        lambda *_args, **_kwargs: _Response(500, {}),
    )

    response = game_service.finish_battle(24, 47, 0)

    assert response == {
        'success': False,
        'message': 'Server failed to finish the battle (HTTP 500). Please try again.',
    }
