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
