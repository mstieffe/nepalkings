# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Mobile virtual-keyboard helpers for pygbag web builds.

On mobile browsers the virtual keyboard only opens when a native HTML
<input> element receives focus.  Since pygbag renders everything into a
<canvas>, this module provides ``prompt()`` as a simple text-entry
fallback for touch devices.
"""

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
            "(/iPhone|iPod|Android|webOS|BlackBerry|IEMobile|Opera Mini/i"
            ".test(navigator.userAgent)"
            " || (navigator.maxTouchPoints > 0"
            " && Math.min(window.innerWidth, window.innerHeight) < 768))"
        ))
    except Exception:
        _is_mobile = False


def is_mobile():
    """Return True when running on a mobile touch-capable web device."""
    return _is_mobile


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
        result = _embed.js(f"window.prompt('{safe_label}','{safe_cur}')")
        return str(result) if result is not None else current
    except Exception:
        return current
