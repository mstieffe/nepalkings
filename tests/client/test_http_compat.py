# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Regression tests for the browser HTTP response compatibility layer."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import sys


def _load_web_http_compat(monkeypatch, js_result):
    module_path = (
        Path(__file__).resolve().parents[2]
        / 'nepal_kings' / 'utils' / 'http_compat.py'
    )
    fake_embed = SimpleNamespace(js=lambda _script: js_result)
    monkeypatch.setitem(sys.modules, 'embed', fake_embed)
    monkeypatch.setattr(sys, 'platform', 'emscripten')
    spec = importlib.util.spec_from_file_location('_test_web_http_compat', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_web_response_exposes_content_type_headers(monkeypatch):
    module = _load_web_http_compat(monkeypatch, {
        's': 200,
        't': json.dumps({'success': True}),
        'c': 'application/json; charset=utf-8',
    })

    response = module.post('/kingdom/defence/clear_active', json={'land_id': 7})

    assert response.status_code == 200
    assert response.headers['content-type'] == 'application/json; charset=utf-8'
    assert response.json() == {'success': True}
