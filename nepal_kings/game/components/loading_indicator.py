"""Shared animated loading indicator for menu/config screens."""

import math

import pygame

from config import settings


_PANEL_BG = (24, 20, 16, 218)
_PANEL_BORDER = (188, 152, 84, 210)
_TEXT = (236, 220, 178)
_TEXT_MUTED = (176, 154, 110)
_ACCENT = (234, 188, 82)


def draw_loading_indicator(surface, rect, message, *, progress=None,
                           started_at_ms=None, title=None, font=None,
                           small_font=None):
    """Draw an animated spinner with optional step text/progress.

    The caller owns the surrounding screen state; this helper is intentionally
    stateless so map, defence, and conquer screens can share the same visual.
    """
    if surface is None:
        return None
    rect = pygame.Rect(rect)
    if rect.width <= 0 or rect.height <= 0:
        return None

    now = pygame.time.get_ticks()
    started_at_ms = now if started_at_ms is None else int(started_at_ms or now)
    elapsed = max(0, now - started_at_ms)
    font = font or settings.get_font(settings.FS_BODY, bold=True)
    small_font = small_font or settings.get_font(settings.FS_SMALL)

    box_w = min(max(280, int(rect.width * 0.46)), max(120, rect.width - 24))
    box_h = min(max(116, int(rect.height * 0.24)), max(86, rect.height - 24))
    box = pygame.Rect(0, 0, box_w, box_h)
    box.center = rect.center

    overlay = pygame.Surface(box.size, pygame.SRCALPHA)
    pygame.draw.rect(overlay, _PANEL_BG, overlay.get_rect(), border_radius=8)
    pygame.draw.rect(overlay, _PANEL_BORDER, overlay.get_rect(), 2, border_radius=8)

    spinner_cx = box_w // 2
    spinner_cy = 28 if title is None else 32
    radius = max(12, min(20, box_h // 5))
    tick_count = 12
    active = int((elapsed / 80) % tick_count)
    for idx in range(tick_count):
        phase = (idx - active) % tick_count
        alpha = max(42, 235 - phase * 16)
        angle = math.tau * idx / tick_count
        dot_r = max(2, int(radius * (0.12 + (tick_count - phase) / tick_count * 0.08)))
        x = int(spinner_cx + math.cos(angle) * radius)
        y = int(spinner_cy + math.sin(angle) * radius)
        pygame.draw.circle(overlay, (*_ACCENT, alpha), (x, y), dot_r)

    if title:
        title_surf = font.render(str(title), True, _TEXT)
        overlay.blit(title_surf, title_surf.get_rect(midtop=(box_w // 2, spinner_cy + radius + 8)))
        msg_top = spinner_cy + radius + 10 + title_surf.get_height() + 4
    else:
        msg_top = spinner_cy + radius + 12

    msg = str(message or 'Loading...')
    if small_font.size(msg)[0] > box_w - 28:
        clipped = msg
        while clipped and small_font.size(clipped + '...')[0] > box_w - 28:
            clipped = clipped[:-1]
        msg = clipped + '...' if clipped else '...'
    msg_surf = small_font.render(msg, True, _TEXT_MUTED)
    overlay.blit(msg_surf, msg_surf.get_rect(midtop=(box_w // 2, msg_top)))

    if progress is not None:
        try:
            pct = max(0.0, min(1.0, float(progress)))
        except (TypeError, ValueError):
            pct = 0.0
        bar_w = box_w - 42
        bar_h = max(5, int(box_h * 0.055))
        bar = pygame.Rect((box_w - bar_w) // 2, box_h - bar_h - 16, bar_w, bar_h)
        pygame.draw.rect(overlay, (60, 48, 32, 230), bar, border_radius=bar_h // 2)
        fill = pygame.Rect(bar.x, bar.y, int(bar.w * pct), bar.h)
        if fill.w > 0:
            pygame.draw.rect(overlay, (*_ACCENT, 235), fill, border_radius=bar_h // 2)

    surface.blit(overlay, box.topleft)
    return box
