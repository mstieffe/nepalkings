# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Mobile virtual-keyboard helpers for pygbag web builds.

On mobile browsers the virtual keyboard only opens when a native HTML
``<input>`` element receives focus.  The login screen uses the non-blocking
input overlay published by ``web/index.html`` so Web Audio and the game loop
can keep running while the keyboard is open.  ``prompt()`` remains as a
fallback for older/custom web shells and other fields.
"""

import json
import sys

_is_web = sys.platform == 'emscripten'
_is_mobile = False


def init():
    """Detect mobile touch device.  Call once at startup on emscripten."""
    global _is_mobile
    if not _is_web:
        return
    try:
        import embed as _embed
        _is_mobile = bool(_embed.js(
            "(/iPhone|iPad|iPod|Android|webOS|BlackBerry|IEMobile|Opera Mini/i"
            ".test(navigator.userAgent)"
            " || (navigator.maxTouchPoints > 0"
            " && (navigator.platform === 'MacIntel'"
            " || (window.matchMedia"
            " && window.matchMedia('(pointer: coarse)').matches))))"
        ))
    except Exception:
        _is_mobile = False


def is_mobile():
    """Return True when running on a mobile touch-capable web device."""
    return _is_mobile


def _js_call(function_name, *values):
    """Call one page-level keyboard bridge function."""
    if not _is_web:
        return False
    try:
        import embed as _embed
        args = ','.join(
            json.dumps(value, separators=(',', ':')) for value in values)
        return bool(_embed.js(
            f"window.{function_name}&&window.{function_name}({args})"))
    except Exception:
        return False


def register_input(
        label, current, is_password, max_length, rect,
        input_mode='text'):
    """Place an invisible native input directly over a canvas field."""
    return _js_call(
        'nk_keyboard_register',
        str(label), str(current), bool(is_password), int(max_length),
        int(rect.x), int(rect.y), int(rect.w), int(rect.h),
        str(input_mode or 'text'),
    )


def set_inputs_enabled(value):
    """Show or hide registered canvas-aligned input targets."""
    return _js_call('nk_keyboard_set_enabled', bool(value))


def clear_inputs():
    """Remove all registered input targets from the page."""
    return _js_call('nk_keyboard_clear')


def open_input(
        label='', current='', is_password=False, max_length=64,
        input_mode='text'):
    """Focus a registered canvas-aligned native input."""
    return _js_call(
        'nk_keyboard_focus',
        str(label), str(current), bool(is_password), int(max_length),
        str(input_mode or 'text'),
    )


def poll_input(label=''):
    """Return the latest overlay state for *label*, or ``None``.

    The returned mapping contains ``value``, ``active``, and ``done``.
    """
    if not _is_web:
        return None
    try:
        import embed as _embed
        label_json = json.dumps(str(label), separators=(',', ':'))
        raw = _embed.js(
            "JSON.stringify(window.nk_keyboard_poll&&"
            f"window.nk_keyboard_poll({label_json}))")
        if raw is None or str(raw) in ('', 'null', 'undefined'):
            return None
        state = json.loads(str(raw))
        return state if isinstance(state, dict) else None
    except Exception:
        return None


def prompt(label='', current='', is_password=False):
    """Show a browser ``prompt()`` dialog and return the entered text.

    Returns *current* unchanged when the user cancels the dialog.
    """
    if not _is_web:
        return current
    try:
        import embed as _embed
        safe_label = (label
                      .replace('\\', '\\\\')
                      .replace("'", "\\'")
                      .replace('\n', '\\n'))
        safe_cur = (current
                    .replace('\\', '\\\\')
                    .replace("'", "\\'")
                    .replace('\n', '\\n'))
        _embed.js("window.nk_audio_resume&&window.nk_audio_resume()")
        result = _embed.js(f"window.prompt('{safe_label}','{safe_cur}')")
        _embed.js("window.nk_audio_resume&&window.nk_audio_resume()")
        return str(result) if result is not None else current
    except Exception:
        return current
