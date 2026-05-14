# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Castle-cap indicator helpers for kingdom config screens."""

import os

import pygame
from config import settings


_CHECKMATE_ICON_CACHE = {}
_CHECKMATE_ICON_PATH = os.path.join(
    settings.RESOURCE_BASE, 'img', 'figures', 'state_icons', 'checkmate.png')


def castle_cap_for_land(land):
    """Return the configured castle-figure cap for a land dict/object."""
    if isinstance(land, dict):
        tier = land.get('tier', 1)
    else:
        tier = getattr(land, 'tier', 1)
    try:
        tier_i = int(tier or 1)
    except (TypeError, ValueError):
        tier_i = 1
    limits = getattr(settings, 'CASTLE_FIGURE_LIMIT_BY_TIER', {}) or {}
    return int(limits.get(tier_i, max(1, tier_i)))


def _figure_field(figure):
    if isinstance(figure, dict):
        return figure.get('field')
    family = getattr(figure, 'family', None)
    return getattr(family, 'field', None) or getattr(figure, 'field', None)


def count_castle_figures(figures):
    return sum(
        1 for figure in (figures or [])
        if str(_figure_field(figure) or '').lower() == 'castle'
    )


def castle_cap_reached(land, figures):
    cap = castle_cap_for_land(land)
    count = count_castle_figures(figures)
    return count >= cap, count, cap


def _load_checkmate_icon(size):
    size = max(1, int(size))
    cached = _CHECKMATE_ICON_CACHE.get(size)
    if cached is not None:
        return cached
    try:
        icon = pygame.image.load(_CHECKMATE_ICON_PATH)
        if pygame.display.get_surface() is not None:
            icon = icon.convert_alpha()
        icon = pygame.transform.smoothscale(icon, (size, size))
    except Exception:
        icon = None
    _CHECKMATE_ICON_CACHE[size] = icon
    return icon


def _draw_fallback_crown_icon(surface, rect, color, shadow_color):
    rect = pygame.Rect(rect)
    if rect.w <= 0 or rect.h <= 0:
        return
    base_y = rect.bottom - max(3, rect.h // 5)
    top_y = rect.top + max(2, rect.h // 7)
    mid_y = rect.top + rect.h // 2
    left = rect.left + max(1, rect.w // 8)
    right = rect.right - max(1, rect.w // 8)
    cx = rect.centerx
    points = [
        (left, base_y),
        (left + rect.w // 6, mid_y),
        (cx, top_y),
        (right - rect.w // 6, mid_y),
        (right, base_y),
    ]
    shadow_points = [(x + 1, y + 1) for x, y in points]
    pygame.draw.polygon(surface, shadow_color, shadow_points)
    pygame.draw.polygon(surface, color, points)
    band = pygame.Rect(left, base_y - 2, max(1, right - left), max(2, rect.h // 5))
    pygame.draw.rect(surface, shadow_color, band.move(1, 1), border_radius=2)
    pygame.draw.rect(surface, color, band, border_radius=2)
    for x, y in (points[1], points[2], points[3]):
        pygame.draw.circle(surface, color, (int(x), int(y)), max(1, rect.w // 12))


def draw_castle_cap_indicator(window, rect, current, cap, *, font=None,
                              always=False):
    """Draw a compact checkmate + ``N/N`` badge inside ``rect``.

    By default the badge only renders when the cap is reached.  Passing
    ``always=True`` renders it whenever ``cap > 0``; in that mode the badge
    uses a muted style until the cap is reached, then flips to the full
    (gold-on-dark) style.

    Returns the badge rect when drawn, otherwise ``None``.
    """
    try:
        current_i = int(current or 0)
        cap_i = int(cap or 0)
    except (TypeError, ValueError):
        return None
    if cap_i <= 0:
        return None
    full = current_i >= cap_i
    if not full and not always:
        return None

    rect = pygame.Rect(rect)
    label = f'{current_i}/{cap_i}'
    font = font or settings.get_font(
        max(10, min(settings.FS_TINY, int(rect.h * 0.055))), bold=True)
    text_color = (255, 236, 172) if full else (215, 205, 175)
    text = font.render(label, True, text_color)
    pad_x = max(5, int(rect.w * 0.025))
    pad_y = max(2, int(rect.h * 0.010))
    icon_size = max(12, min(18, text.get_height() + 3))
    badge_h = max(icon_size + 2 * pad_y, text.get_height() + 2 * pad_y)
    badge_w = icon_size + text.get_width() + pad_x * 3
    badge_w = min(max(1, rect.w - 12), badge_w)
    badge = pygame.Rect(0, 0, badge_w, badge_h)
    badge.right = rect.right - 6
    badge.top = rect.top + 5

    bg = pygame.Surface(badge.size, pygame.SRCALPHA)
    if full:
        bg_color = (54, 38, 16, 232)
        border_color = (224, 182, 82)
        crown_color = (248, 210, 96)
        crown_shadow = (62, 34, 8)
    else:
        bg_color = (40, 36, 30, 200)
        border_color = (150, 140, 110)
        crown_color = (200, 190, 160)
        crown_shadow = (55, 50, 40)
    pygame.draw.rect(bg, bg_color, bg.get_rect(),
                     border_radius=badge_h // 2)
    window.blit(bg, badge.topleft)
    pygame.draw.rect(window, border_color, badge, 1,
                     border_radius=badge_h // 2)

    icon_rect = pygame.Rect(0, 0, icon_size, icon_size)
    icon_rect.left = badge.left + pad_x
    icon_rect.centery = badge.centery
    checkmate_icon = _load_checkmate_icon(icon_size)
    if checkmate_icon is not None:
        window.blit(checkmate_icon, checkmate_icon.get_rect(center=icon_rect.center))
    else:
        _draw_fallback_crown_icon(window, icon_rect, crown_color, crown_shadow)

    text_x = icon_rect.right + pad_x
    max_text_w = max(0, badge.right - pad_x - text_x)
    if text.get_width() > max_text_w and max_text_w > 0:
        label = label[-max(1, len(label) - 1):]
        text = font.render(label, True, text_color)
    window.blit(text, text.get_rect(midleft=(text_x, badge.centery)))
    return badge
