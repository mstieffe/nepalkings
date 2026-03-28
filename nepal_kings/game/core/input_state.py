# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Event-based mouse button tracking for reliable touch support on mobile.

On emscripten/mobile, ``pygame.mouse.get_pressed()`` can miss quick taps
because both MOUSEBUTTONDOWN and MOUSEBUTTONUP may arrive in the same frame.
Call ``process_events(events)`` once per frame (before game logic) and use
``get_pressed()`` as a drop-in replacement.
"""

import pygame

_btn1_held = False          # tracks real held state across frames
_btn1_pressed_frame = False  # True if btn1 went down during this frame's batch


def process_events(events):
    """Scan *events* for mouse button state changes.  Call once per frame."""
    global _btn1_held, _btn1_pressed_frame
    _btn1_pressed_frame = False
    for e in events:
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
            _btn1_held = True
            _btn1_pressed_frame = True
        elif e.type == pygame.MOUSEBUTTONUP and e.button == 1:
            _btn1_held = False


def get_pressed():
    """Drop-in replacement for ``pygame.mouse.get_pressed()``.

    Button-1 is reported as *True* for the entire frame in which
    MOUSEBUTTONDOWN was received, even if MOUSEBUTTONUP arrived in
    the same event batch.
    """
    native = pygame.mouse.get_pressed()
    btn1 = native[0] or _btn1_held or _btn1_pressed_frame
    return (btn1, native[1], native[2])
