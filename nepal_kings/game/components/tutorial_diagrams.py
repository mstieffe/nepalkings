# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Runtime-composed teaching diagrams for the tutorial windows.

Each diagram is built once from existing art (suit icons, card images, field
slot icons) and cached. Asset loads are guarded so a missing file degrades to a
smaller/partial diagram rather than crashing the onboarding.
"""

import math
import os

import pygame

from config import settings

_CACHE = {}

# Suit-advantage cycle (each suit beats the next): ♥ → ♣ → ♦ → ♠ → ♥.
_BEATS_ORDER = ('Hearts', 'Clubs', 'Diamonds', 'Spades')
_SUIT_LABEL = {'Hearts': 'Hearts', 'Diamonds': 'Diamonds',
               'Clubs': 'Clubs', 'Spades': 'Spades'}


def _asset(*parts):
    return os.path.join(settings.RESOURCE_BASE, *parts)


def _load(path):
    try:
        return pygame.image.load(path).convert_alpha()
    except Exception:
        try:
            return pygame.image.load(path)
        except Exception:
            return None


def _scaled(surf, target_h):
    if surf is None or target_h <= 0:
        return None
    ratio = target_h / surf.get_height()
    return pygame.transform.smoothscale(
        surf, (max(1, int(surf.get_width() * ratio)), int(target_h)))


def _suit_icon(suit, size):
    return _scaled(_load(_asset('img', 'suits', f'{suit.lower()}.png')), size)


def suit_icon(suit, size):
    """Public, cached suit icon scaled to ``size`` px tall (or None)."""
    key = ('suit', suit, int(size))
    if key not in _CACHE:
        _CACHE[key] = _suit_icon(suit, int(size))
    return _CACHE[key]


def _card_surface(suit, rank, height):
    """Card front via CardImg (runtime), guarded for headless/test use."""
    try:
        from game.components.cards.card_img import CardImg
        w = int(height * (settings.CARD_WIDTH / settings.CARD_HEIGHT))
        return CardImg(None, suit, rank, width=w, height=int(height)).front_img
    except Exception:
        surf = pygame.Surface((int(height * 0.7), int(height)), pygame.SRCALPHA)
        pygame.draw.rect(surf, (245, 240, 225), surf.get_rect(), border_radius=6)
        pygame.draw.rect(surf, (120, 100, 70), surf.get_rect(), 2, border_radius=6)
        return surf


def _draw_arrow(surf, start, end, color=(230, 200, 120), width=4, head=12):
    pygame.draw.line(surf, color, start, end, width)
    ang = math.atan2(end[1] - start[1], end[0] - start[0])
    for da in (math.radians(150), math.radians(-150)):
        hx = end[0] + head * math.cos(ang + da)
        hy = end[1] + head * math.sin(ang + da)
        pygame.draw.line(surf, color, end, (hx, hy), width)


def card_combo_to_figure(target_h=None):
    """[J][7] → (Farm) : cards combine into a field figure."""
    _SH = settings.SCREEN_HEIGHT
    target_h = int(target_h or 0.16 * _SH)
    key = ('combo', target_h)
    if key in _CACHE:
        return _CACHE[key]

    card_h = target_h
    card_w = int(card_h * (settings.CARD_WIDTH / settings.CARD_HEIGHT))
    j_card = _card_surface('Hearts', 'J', card_h)
    seven_card = _card_surface('Hearts', '7', card_h)
    farm = _scaled(_load(_asset('img', 'slot_icons', 'village.png')),
                   int(target_h * 0.9))
    if farm is None:
        farm = _scaled(_load(_asset('img', 'figures', 'village', 'farm1.png')),
                       int(target_h * 0.9))

    gap = int(0.012 * settings.SCREEN_WIDTH)
    arrow_w = int(0.06 * settings.SCREEN_WIDTH)
    farm_w = farm.get_width() if farm else int(target_h * 0.9)
    total_w = card_w + gap + card_w + arrow_w + farm_w + gap * 2
    surf = pygame.Surface((total_w, target_h), pygame.SRCALPHA)

    x = 0
    cy = target_h // 2
    for card in (j_card, seven_card):
        surf.blit(card, (x, cy - card.get_height() // 2))
        x += card.get_width() + gap
    a0 = (x + gap, cy)
    a1 = (x + arrow_w - gap, cy)
    _draw_arrow(surf, a0, a1)
    x += arrow_w
    if farm:
        surf.blit(farm, (x, cy - farm.get_height() // 2))

    _CACHE[key] = surf
    return surf


def suit_advantage_wheel(target_h=None):
    """Four suits on a circle with arrows in beats order (♥→♣→♦→♠→♥)."""
    _SH = settings.SCREEN_HEIGHT
    target_h = int(target_h or 0.26 * _SH)
    key = ('wheel', target_h)
    if key in _CACHE:
        return _CACHE[key]

    size = target_h
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    center = (size // 2, size // 2)
    radius = int(size * 0.34)
    icon = int(size * 0.20)
    # Clockwise from top: Hearts(top), Clubs(right), Diamonds(bottom), Spades(left).
    angles = {
        'Hearts': -90, 'Clubs': 0, 'Diamonds': 90, 'Spades': 180,
    }
    pos = {}
    for suit, deg in angles.items():
        rad = math.radians(deg)
        pos[suit] = (center[0] + radius * math.cos(rad),
                     center[1] + radius * math.sin(rad))

    # Arrows along the beats cycle.
    for i, suit in enumerate(_BEATS_ORDER):
        nxt = _BEATS_ORDER[(i + 1) % len(_BEATS_ORDER)]
        sx, sy = pos[suit]
        ex, ey = pos[nxt]
        ang = math.atan2(ey - sy, ex - sx)
        pad = icon * 0.65
        start = (sx + pad * math.cos(ang), sy + pad * math.sin(ang))
        end = (ex - pad * math.cos(ang), ey - pad * math.sin(ang))
        _draw_arrow(surf, start, end)

    for suit, (px, py) in pos.items():
        ic = _suit_icon(suit, icon)
        if ic:
            surf.blit(ic, (px - ic.get_width() // 2, py - ic.get_height() // 2))

    _CACHE[key] = surf
    return surf


def clear_cache():
    _CACHE.clear()
