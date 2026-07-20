# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Response-compression regressions for the large kingdom map."""

import gzip

from flask import Response

import server as server_module
import server_settings as settings


def _map_response(payload):
    return Response(payload, status=200, mimetype='application/json')


def test_large_map_response_is_gzipped_for_supporting_client(app, monkeypatch):
    original = (b'{"lands":[' + (b'{"id":1},' * 600) + b']}')
    monkeypatch.setattr(settings, 'RESPONSE_COMPRESSION_ENABLED', True)
    monkeypatch.setattr(settings, 'RESPONSE_COMPRESSION_MIN_BYTES', 1024)

    with app.test_request_context(
        '/kingdom/map',
        method='GET',
        headers={'Accept-Encoding': 'gzip, deflate'},
    ):
        response = server_module._compress_large_map_response(
            _map_response(original)
        )

    assert response.headers['Content-Encoding'] == 'gzip'
    assert 'Accept-Encoding' in response.headers['Vary']
    assert int(response.headers['Content-Length']) < len(original)
    assert gzip.decompress(response.get_data()) == original


def test_map_response_stays_plain_without_gzip_acceptance(app, monkeypatch):
    original = b'x' * 4096
    monkeypatch.setattr(settings, 'RESPONSE_COMPRESSION_ENABLED', True)

    with app.test_request_context('/kingdom/map', method='GET'):
        response = server_module._compress_large_map_response(
            _map_response(original)
        )

    assert response.headers.get('Content-Encoding') is None
    assert response.get_data() == original


def test_small_map_response_is_not_compressed(app, monkeypatch):
    original = b'{"lands":[]}'
    monkeypatch.setattr(settings, 'RESPONSE_COMPRESSION_ENABLED', True)
    monkeypatch.setattr(settings, 'RESPONSE_COMPRESSION_MIN_BYTES', 1024)

    with app.test_request_context(
        '/kingdom/map',
        method='GET',
        headers={'Accept-Encoding': 'gzip'},
    ):
        response = server_module._compress_large_map_response(
            _map_response(original)
        )

    assert response.headers.get('Content-Encoding') is None
    assert response.get_data() == original


def test_compression_kill_switch_leaves_response_plain(app, monkeypatch):
    original = b'x' * 4096
    monkeypatch.setattr(settings, 'RESPONSE_COMPRESSION_ENABLED', False)

    with app.test_request_context(
        '/kingdom/map',
        method='GET',
        headers={'Accept-Encoding': 'gzip'},
    ):
        response = server_module._compress_large_map_response(
            _map_response(original)
        )

    assert response.headers.get('Content-Encoding') is None
    assert response.get_data() == original
