# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Shared "(i)" info-button + anchored popup used by the config screens.

The screens own the state (`_info_button_rects`, `_active_info_key`,
`_active_info_popup_rect`) and the copy dicts; this module owns geometry,
drawing and click handling so both screens stay pixel-identical.
"""

import pygame
from pygame.locals import MOUSEBUTTONUP

from config import settings
from game.components.config_screen_common import (
    POPUP_BG,
    POPUP_BODY,
    POPUP_BORDER,
    POPUP_TITLE,
)

_SW, _SH = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT


def info_button_rect(panel_rect):
    """Return the (i) button rect anchored to a panel's top-right corner."""
    size = max(int(0.022 * _SH), 18, settings.TOUCH_ICON_MIN)
    margin_x = int(0.008 * _SW)
    margin_y = int(0.010 * _SH)
    return pygame.Rect(
        panel_rect.right - margin_x - size,
        panel_rect.y + margin_y,
        size,
        size,
    )


def draw_info_button(window, rect, active=False):
    if not rect:
        return
    hovered = rect.collidepoint(pygame.mouse.get_pos())
    center = rect.center
    radius = rect.w // 2
    fill = (80, 70, 45, 235) if active else ((70, 62, 42, 225) if hovered else (45, 40, 32, 210))
    border = (230, 210, 140) if active or hovered else (150, 135, 95)
    text_clr = (255, 240, 185) if active or hovered else (195, 180, 130)
    pygame.draw.circle(window, fill, center, radius)
    pygame.draw.circle(window, border, center, radius, 1)
    font = settings.get_font(max(int(rect.h * 0.72), 9), bold=True)
    txt = font.render('i', True, text_clr)
    window.blit(txt, txt.get_rect(center=center))


def wrap_info_text(text, font, max_width):
    lines = []
    for paragraph in str(text).split('\n'):
        words = paragraph.split()
        current = ''
        for word in words:
            candidate = f'{current} {word}'.strip()
            if current and font.size(candidate)[0] > max_width:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
    return lines


def draw_info_popup(window, info, anchor, *, box_rect, box_pad,
                    max_panel_w, title_font, body_font):
    """Draw the popup for an active info key; returns its rect (or None)."""
    if not info or not anchor:
        return None

    pad = int(0.010 * _SW)
    gap = int(0.006 * _SH)
    popup_w = min(int(0.30 * _SW), max(int(0.20 * _SW), max_panel_w - 2 * pad))
    text_w = popup_w - 2 * pad
    title = info['title']
    lines = wrap_info_text(info['message'], body_font, text_w)
    line_gap = 3
    popup_h = (
        pad
        + title_font.get_height()
        + int(0.006 * _SH)
        + len(lines) * body_font.get_height()
        + max(0, len(lines) - 1) * line_gap
        + pad
    )
    x = min(anchor.right - popup_w, box_rect.right - box_pad - popup_w)
    x = max(box_rect.x + box_pad, x)
    y = anchor.bottom + gap
    if y + popup_h > box_rect.bottom - box_pad:
        y = anchor.top - popup_h - gap
    y = max(box_rect.y + box_pad, y)
    popup_rect = pygame.Rect(int(x), int(y), int(popup_w), int(popup_h))

    surf = pygame.Surface((popup_rect.w, popup_rect.h), pygame.SRCALPHA)
    pygame.draw.rect(surf, POPUP_BG, surf.get_rect(), border_radius=6)
    window.blit(surf, popup_rect.topleft)
    pygame.draw.rect(window, POPUP_BORDER, popup_rect, 1, border_radius=6)

    cx = popup_rect.x + pad
    cy = popup_rect.y + pad
    title_surf = title_font.render(title, True, POPUP_TITLE)
    window.blit(title_surf, (cx, cy))
    cy += title_surf.get_height() + int(0.006 * _SH)
    for line in lines:
        line_surf = body_font.render(line, True, POPUP_BODY)
        window.blit(line_surf, (cx, cy))
        cy += body_font.get_height() + line_gap
    return popup_rect


def handle_info_event(event, button_rects, active_key, popup_rect, *, collide):
    """Route a click through the info buttons/popup.

    Returns ``(consumed, new_active_key, hit_button)``. ``hit_button`` is
    True only when an (i) button itself was clicked (for click feedback).
    """
    if event.type != MOUSEBUTTONUP or event.button != 1:
        return False, active_key, False
    pos = event.pos
    for key, rect in button_rects.items():
        if collide(rect, pos, settings.TOUCH_COMPACT_MIN, settings.TOUCH_COMPACT_MIN):
            return True, (None if active_key == key else key), True
    if active_key:
        if popup_rect and popup_rect.collidepoint(pos):
            return True, active_key, False
        return True, None, False
    return False, active_key, False
