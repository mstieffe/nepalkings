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


def _wrap_lines(font, text, max_width, max_lines):
    lines = []
    current = ''
    for word in str(text or '').split():
        candidate = word if not current else f'{current} {word}'
        if font.size(candidate)[0] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines[:max_lines]


def _fit_text(font, text, max_width):
    text = str(text or '')
    if font.size(text)[0] <= max_width:
        return text
    ellipsis = '...'
    room = max(0, max_width - font.size(ellipsis)[0])
    fitted = ''
    for char in text:
        if font.size(fitted + char)[0] > room:
            break
        fitted += char
    return fitted.rstrip() + ellipsis


def draw_coach_panel(window, target_rects, *, title, body, title_font,
                     body_font, ticks, width_ratio=0.36, min_width=320,
                     max_width=420, min_height=152, max_lines=5,
                     has_button_row=True):
    """Draw shared coach chrome and return ``(card_rect, button_height)``.

    Screens retain their own progression and event routing while this helper
    keeps typography, spacing, placement, spotlight, and panel styling aligned.
    """
    rects = [pygame.Rect(rect) for rect in target_rects if rect]
    if not rects:
        return None, 0
    draw_coach_spotlight(window, rects)
    draw_coach_highlight(window, rects, ticks)
    target = rects[0].copy()
    for rect in rects[1:]:
        target.union_ip(rect)
    target.inflate_ip(_INFLATE, _INFLATE)

    screen_w, screen_h = window.get_size()
    card_w = min(max_width, max(min_width, int(width_ratio * screen_w)), screen_w - 16)
    body_lines = _wrap_lines(body_font, body, card_w - 28, max_lines)
    title_h = title_font.get_height()
    body_line_h = body_font.get_height() + 3
    button_h = max(30, body_font.get_height() + 10)
    button_space = button_h + 16 if has_button_row else 8
    card_h = max(
        min_height,
        22 + title_h + 10 + len(body_lines) * body_line_h + button_space,
    )
    gap = 14
    if target.right + gap + card_w < screen_w:
        card_x = target.right + gap
    else:
        card_x = max(8, target.left - gap - card_w)
    card_y = max(8, min(target.centery - card_h // 2, screen_h - card_h - 8))
    card = pygame.Rect(card_x, card_y, card_w, card_h)
    surf = pygame.Surface((card.w, card.h), pygame.SRCALPHA)
    pygame.draw.rect(surf, (24, 20, 16, 235), surf.get_rect(), border_radius=8)
    window.blit(surf, card.topleft)
    pygame.draw.rect(window, (220, 185, 88), card, 2, border_radius=8)

    title_surf = title_font.render(
        _fit_text(title_font, title, card.w - 24), True, (248, 232, 180))
    window.blit(title_surf, (card.x + 12, card.y + 10))
    y = card.y + 10 + title_h + 10
    for line in body_lines:
        line_surf = body_font.render(line, True, (214, 204, 174))
        window.blit(line_surf, (card.x + 12, y))
        y += body_line_h
    return card, button_h


def draw_coach_button(window, rect, label, font, *, muted=False):
    """Draw the shared primary or secondary coach button style."""
    hovered = rect.collidepoint(pygame.mouse.get_pos())
    if muted:
        bg = (40, 37, 32) if hovered else (30, 28, 24)
        border = (110, 100, 84) if hovered else (78, 72, 60)
        text_color = (170, 160, 142) if hovered else (132, 124, 108)
    else:
        bg = (96, 70, 34) if hovered else (58, 45, 28)
        border = (235, 204, 105) if hovered else (150, 126, 74)
        text_color = (245, 232, 190)
    pygame.draw.rect(window, bg, rect, border_radius=4)
    pygame.draw.rect(window, border, rect, 1, border_radius=4)
    text_surf = font.render(label, True, text_color)
    window.blit(text_surf, text_surf.get_rect(center=rect.center))
