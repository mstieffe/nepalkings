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


def open_input(label='', current='', is_password=False, max_length=64):
    """Open the page's non-blocking native input overlay.

    Returns ``False`` when the current web shell does not publish the bridge,
    allowing callers to fall back to ``prompt()``.
    """
    if not _is_web:
        return False
    try:
        import embed as _embed
        args = ','.join(json.dumps(value, separators=(',', ':')) for value in (
            str(label), str(current), bool(is_password), int(max_length)))
        return bool(_embed.js(
            f"window.nk_keyboard_open&&window.nk_keyboard_open({args})"))
    except Exception:
        return False


def poll_input(label=''):
    """Return the latest overlay state for *label*, or ``None``.

    The returned mapping contains ``value``, ``done``, and ``cancelled``.
    Completed state is consumed by the page bridge after this poll.
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
