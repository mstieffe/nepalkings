# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for the non-blocking mobile text-input bridge."""

import sys
import types

from utils import web_keyboard


def test_web_keyboard_bridge_opens_and_polls_native_input(monkeypatch):
    calls = []

    def js(script):
        calls.append(script)
        if script.startswith('window.nk_keyboard_open'):
            return True
        return '{"value":"Malla","done":false,"cancelled":false}'

    monkeypatch.setitem(sys.modules, 'embed', types.SimpleNamespace(js=js))
    monkeypatch.setattr(web_keyboard, '_is_web', True)

    assert web_keyboard.open_input('username', 'Mal', False, 30) is True
    assert web_keyboard.poll_input('username') == {
        'value': 'Malla',
        'done': False,
        'cancelled': False,
    }
    assert calls == [
        'window.nk_keyboard_open&&window.nk_keyboard_open('
        '"username","Mal",false,30)',
        'JSON.stringify(window.nk_keyboard_poll&&'
        'window.nk_keyboard_poll("username"))',
    ]


def test_input_field_syncs_non_blocking_mobile_overlay(monkeypatch):
    from utils import utils as utils_module
    from utils.utils import InputField

    opened = []
    states = iter([
        {'value': 'Malla', 'done': False, 'cancelled': False},
        {'value': 'MallaKing', 'done': True, 'cancelled': False},
    ])
    monkeypatch.setattr(utils_module.sys, 'platform', 'emscripten')
    monkeypatch.setattr(web_keyboard, 'is_mobile', lambda: True)
    monkeypatch.setattr(
        web_keyboard,
        'open_input',
        lambda *args: opened.append(args) or True,
    )
    monkeypatch.setattr(web_keyboard, 'poll_input', lambda _label: next(states))
    monkeypatch.setattr(
        web_keyboard,
        'prompt',
        lambda *_args: (_ for _ in ()).throw(
            AssertionError('blocking prompt should not be used')),
    )

    field = object.__new__(InputField)
    field.name = 'username'
    field.content = 'Mal'
    field.pwd = False
    field.max_length = 30
    field.cursor_pos = 3
    field.active = False
    field.web_overlay = True
    field._web_input_pending = False
    field._web_input_original = 'Mal'

    field.activate()
    assert opened == [('username', 'Mal', False, 30)]
    assert field.active is True
    assert field._web_input_pending is True

    assert field.sync_web_input() is True
    assert field.content == 'Malla'
    assert field.active is True

    assert field.sync_web_input() is True
    assert field.content == 'MallaKing'
    assert field.cursor_pos == len('MallaKing')
    assert field.active is False
    assert field._web_input_pending is False


def test_cancelled_mobile_overlay_restores_original_value(monkeypatch):
    from utils.utils import InputField

    monkeypatch.setattr(
        web_keyboard,
        'poll_input',
        lambda _label: {'value': 'typo', 'done': True, 'cancelled': True},
    )
    field = object.__new__(InputField)
    field.name = 'password'
    field.content = 'typo'
    field.max_length = 64
    field.cursor_pos = 4
    field.active = True
    field._web_input_pending = True
    field._web_input_original = 'secret'

    assert field.sync_web_input() is True
    assert field.content == 'secret'
    assert field.active is False
