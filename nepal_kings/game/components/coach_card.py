# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Shared visuals for the on-screen tutorial coach cards.

All three coach renderers (menu coach in ``_menu_base``, the in-duel coach in
``game_screen``, and the conquer-battle coach in ``conquer_game_screen``) draw
the same highlight around their target: a dimmed "spotlight" overlay that makes
the highlighted control pop, plus a smoothly pulsing gold border. These helpers
keep that look identical everywhere. They are draw-only — event handling and
click pass-through live in each screen, so the spotlight never blocks input.
"""

import math

import pygame

# The target rect is inflated by this much so the highlight/hole sits clear of
# the control's edges. Must match across the spotlight hole and the border.
_INFLATE = 14
_HIGHLIGHT_CLR = (250, 218, 92)
# Skip dimming when the target already covers most of the screen (e.g. the whole
# map viewport) — a hole that big leaves nothing to dim and just darkens edges.
_MAX_SPOTLIGHT_COVERAGE = 0.55


def _inflated(rects):
    return [pygame.Rect(rect).inflate(_INFLATE, _INFLATE) for rect in rects if rect]


def draw_coach_spotlight(window, target_rects, alpha=120):
    """Dim the whole screen except the target rect(s), so the highlight pops.

    Draws a translucent black overlay with rectangular holes punched out over
    each (inflated) target. Skipped when the targets already cover most of the
    screen, where dimming would add nothing.
    """
    holes = _inflated(target_rects)
    if not holes:
        return
    sw, sh = window.get_size()
    screen_area = max(1, sw * sh)
    covered = 0
    bounds = holes[0].copy()
    for rect in holes[1:]:
        bounds.union_ip(rect)
    covered = bounds.width * bounds.height
    if covered >= _MAX_SPOTLIGHT_COVERAGE * screen_area:
        return
    overlay = pygame.Surface((sw, sh), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, alpha))
    for rect in holes:
        # Filling an SRCALPHA surface with a fully transparent colour clears the
        # sub-rect, leaving an undimmed rectangular "window" onto the target.
        overlay.fill((0, 0, 0, 0), rect.clip(overlay.get_rect()))
    window.blit(overlay, (0, 0))


def draw_coach_highlight(window, target_rects, ticks):
    """Draw a smoothly pulsing gold border around each (inflated) target.

    Replaces the old 2px<->3px width blink with a sine-animated alpha glow at a
    constant 2px width, which reads as a gentle breathing highlight.
    """
    rects = _inflated(target_rects)
    if not rects:
        return
    # 150..255 over a ~2.4s cycle.
    alpha = 150 + int(105 * (0.5 + 0.5 * math.sin(ticks / 380.0)))
    alpha = max(0, min(255, alpha))
    for rect in rects:
        glow = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        # Soft outer halo, then the crisp inner border.
        pygame.draw.rect(glow, (*_HIGHLIGHT_CLR, alpha // 3),
                         glow.get_rect(), 4, border_radius=10)
        pygame.draw.rect(glow, (*_HIGHLIGHT_CLR, alpha),
                         glow.get_rect().inflate(-2, -2), 2, border_radius=8)
        window.blit(glow, rect.topleft)

