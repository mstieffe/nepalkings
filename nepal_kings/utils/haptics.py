# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Lightweight haptic-feedback bridge for the pygbag web build.

On mobile web (emscripten) this calls the browser Vibration API
(``navigator.vibrate``).  On desktop, or on browsers without the
Vibration API, every call is a cheap no-op — callers never need a
platform guard of their own.

Support note: Android Chrome/Firefox honour ``navigator.vibrate``;
iOS Safari does not expose the API at all.  ``init()`` detects this
once so unsupported browsers skip the JS round-trip entirely.

This module follows the "minimal" feedback profile: a single short
pulse on UI taps.  Nothing else vibrates.
"""

import sys

_IS_WEB = sys.platform == "emscripten"

# Pulse length in milliseconds — deliberately short ("minimal" profile):
# just enough to feel a tap-tick without being intrusive.
_TAP_MS = 12

_enabled = True       # global on/off (settings hook for future use)
_supported = False    # set by init() once support is known


def init():
    """Detect Vibration API support once at startup.  Safe to call anywhere."""
    global _supported
    if not _IS_WEB:
        return
    try:
        import embed as _embed
        _supported = bool(_embed.js(
            "(typeof navigator !== 'undefined' && 'vibrate' in navigator)"
        ))
    except Exception:
        _supported = False


def set_enabled(value):
    """Enable or disable haptics globally (e.g. from a settings toggle)."""
    global _enabled
    _enabled = bool(value)


def is_enabled():
    """Return True when haptic feedback is currently enabled."""
    return _enabled


def _vibrate(ms):
    """Fire a vibration pulse of *ms* milliseconds.  No-op when unsupported."""
    if not (_IS_WEB and _enabled and _supported):
        return
    try:
        import embed as _embed
        _embed.js(f"navigator.vibrate({int(ms)})")
    except Exception:
        pass


def tap():
    """Fire a short pulse for a UI tap / button press."""
    _vibrate(_TAP_MS)


def tap_edge(obj):
    """Fire a tap pulse on the rising edge of ``obj.clicked``.

    The previous click state is stored on the object itself, so a held
    press fires exactly once (on press-down) rather than every frame.
    Call once per frame, after the button's ``clicked`` flag has been
    refreshed for that frame.
    """
    now = bool(getattr(obj, 'clicked', False))
    if now and not getattr(obj, '_haptic_prev_click', False):
        tap()
    obj._haptic_prev_click = now
