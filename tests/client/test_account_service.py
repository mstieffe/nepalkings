# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.

import importlib
import json
import stat


class _Response:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_change_password_uses_account_endpoint_and_returns_new_token(
        monkeypatch):
    service = importlib.import_module('utils.account_service')
    recorded = {}

    def fake_post(url, **kwargs):
        recorded['url'] = url
        recorded.update(kwargs)
        return _Response(200, {
            'success': True,
            'message': 'changed',
            'token': 'replacement',
        })

    monkeypatch.setattr(service.requests, 'post', fake_post)
    result = service.change_password('old-password', 'new-password')

    assert recorded['url'].endswith('/auth/account/change_password')
    assert recorded['data'] == {
        'current_password': 'old-password',
        'new_password': 'new-password',
    }
    assert result['token'] == 'replacement'


def test_report_and_block_use_player_safety_endpoints(monkeypatch):
    service = importlib.import_module('utils.account_service')
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return _Response(200, {'success': True, 'message': 'ok'})

    monkeypatch.setattr(service.requests, 'post', fake_post)
    assert service.report_player(
        'Opponent', 'spam', 'details')['success'] is True
    assert service.set_player_block('Opponent', True)['success'] is True
    assert service.set_player_block('Opponent', False)['success'] is True

    assert calls[0][0].endswith('/safety/reports')
    assert calls[0][1]['json']['reason'] == 'spam'
    assert calls[1][0].endswith('/safety/blocks')
    assert calls[2][0].endswith('/safety/blocks/remove')


def test_desktop_export_is_private_and_valid_json(monkeypatch, tmp_path):
    service = importlib.import_module('utils.account_service')
    monkeypatch.setattr(
        service.Path,
        'home',
        classmethod(lambda cls: tmp_path),
    )
    payload = {
        'account': {'username': 'Test_Player'},
        'games': [{'game_id': 1}],
    }

    destination = service.save_export(payload)
    mode = stat.S_IMODE(service.os.stat(destination).st_mode)

    assert mode == 0o600
    with open(destination, encoding='utf-8') as handle:
        assert json.load(handle) == payload
