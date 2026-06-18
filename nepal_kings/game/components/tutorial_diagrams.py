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
    # The full Rice-Farm field-figure icon (frame + power badge) as the payoff.
    farm = field_figure_icon('Small Rice Farm', 'rice_farm1.png',
                             label='', target_h=int(target_h * 1.05))
    if farm is None:
        farm = _scaled(_load(_asset('img', 'slot_icons', 'village.png')),
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


def kingdom_overview_diagram(target_h=None):
    """A land that makes gold and holds figures: [gold] + full field figures."""
    _SH = settings.SCREEN_HEIGHT
    target_h = int(target_h or 0.16 * _SH)
    key = ('kingdom', target_h)
    if key in _CACHE:
        return _CACHE[key]

    gold = _scaled(_load(_asset('img', 'dialogue_box', 'icons', 'gold.png')),
                   int(target_h * 0.7))
    figs = [field_figure_icon(name, fb, lbl, target_h)
            for name, fb, lbl in _ARMY_FIGURES['offensive']]
    parts = [p for p in ([gold] + figs) if p]
    if not parts:
        surf = pygame.Surface((1, 1), pygame.SRCALPHA)
        _CACHE[key] = surf
        return surf
    gap = int(0.02 * settings.SCREEN_WIDTH)
    total_w = sum(p.get_width() for p in parts) + gap * (len(parts) - 1)
    h = max(p.get_height() for p in parts)
    surf = pygame.Surface((total_w, h), pygame.SRCALPHA)
    x = 0
    for p in parts:
        surf.blit(p, (x, (h - p.get_height()) // 2))
        x += p.get_width() + gap
    _CACHE[key] = surf
    return surf


# Field-figure button sets: (family_name, fallback icon file, label).
_ARMY_FIGURES = {
    'offensive': [
        ('Djungle King', 'castle_red.png', 'King'),
        ('Small Rice Farm', 'rice_farm1.png', 'Farm'),
        ('Gorkha Warriors', 'army1.png', 'Warriors'),
    ],
    'defensive': [
        ('Himalaya King', 'castle_black.png', 'King'),
        ('Small Yack Farm', 'yack_farm1.png', 'Farm'),
        ('Wooden Fortress', 'fortress1.png', 'Fortress'),
    ],
}

_FIG_MGR = None


def _figure_manager():
    """Lazily build and cache a FigureManager (loads all figure art once)."""
    global _FIG_MGR
    if _FIG_MGR is None:
        try:
            from game.components.figures.figure_manager import FigureManager
            _FIG_MGR = FigureManager()
        except Exception:
            _FIG_MGR = False
    return _FIG_MGR or None


def _skill_icons(skill_keys, size):
    try:
        from game.components.figures.family_configs.skill_config import SKILL_DEFINITIONS
    except Exception:
        return []
    icons = []
    for key in (skill_keys or [])[:2]:
        rel = (SKILL_DEFINITIONS.get(key) or {}).get('icon')
        if not rel:
            continue
        ic = _scaled(_load(_asset(*rel.split('/'))), size)
        if ic:
            icons.append(ic)
    return icons


def field_figure_icon(family_name, fallback_icon=None, label=None, target_h=None):
    """A faithful field-figure icon: real frame + icon + power/skill badge.

    Composed from the family's frame/icon art with a small power badge and any
    active skill icons, mirroring how the figure appears on the field. Falls
    back to a framed raw icon if the figure manager/art is unavailable.
    """
    _SH = settings.SCREEN_HEIGHT
    box = int(target_h or 0.16 * _SH)
    label = family_name if label is None else label  # '' => no label row
    key = ('fieldfig', family_name, box, label)
    if key in _CACHE:
        return _CACHE[key]

    label_font = settings.get_font(getattr(settings, 'FS_TINY', 14))
    lbl = label_font.render(label, True, (235, 222, 190)) if label else None
    extra = (lbl.get_height() + 8) if lbl else 0
    surf = pygame.Surface((box, box + extra), pygame.SRCALPHA)
    frame_rect = pygame.Rect(0, 0, box, box)

    mgr = _figure_manager()
    family = mgr.families.get(family_name) if mgr else None
    drew = False
    if family is not None:
        try:
            from game.components.figures.figure_img import FigureImg
            FigureImg(surf, family, box, box).draw_icon(0, 0)
            drew = True
        except Exception:
            drew = False
    if not drew:
        pygame.draw.rect(surf, (28, 22, 14, 235), frame_rect, border_radius=10)
        pygame.draw.rect(surf, (224, 182, 82), frame_rect, 2, border_radius=10)
        icon = _scaled(_load(_asset('img', 'figures', 'icons', fallback_icon)),
                       int(box * 0.78)) if fallback_icon else None
        if icon:
            surf.blit(icon, icon.get_rect(center=frame_rect.center))

    # Power + skill badge, mirroring the field info display (best-effort).
    rep = None
    if mgr:
        reps = mgr.figures_by_name.get(family_name) or []
        rep = reps[0] if reps else None
    if rep is not None:
        try:
            value = int(rep.get_value())
            badge_font = settings.get_font(getattr(settings, 'FS_SMALL', 16), bold=True)
            txt = badge_font.render(str(value), True, (255, 244, 210))
            bw = max(int(box * 0.30), txt.get_width() + 10)
            bh = txt.get_height() + 4
            badge = pygame.Rect(4, box - bh - 4, bw, bh)
            bg = pygame.Surface((badge.w, badge.h), pygame.SRCALPHA)
            pygame.draw.rect(bg, (24, 20, 14, 235), bg.get_rect(), border_radius=6)
            pygame.draw.rect(bg, (224, 182, 82), bg.get_rect(), 1, border_radius=6)
            surf.blit(bg, badge.topleft)
            surf.blit(txt, txt.get_rect(center=badge.center))
        except Exception:
            pass
        try:
            sk_size = int(box * 0.24)
            icons = _skill_icons(rep.get_active_skill_keys(), sk_size)
            sx = box - sk_size - 4
            sy = 4
            for ic in icons:
                surf.blit(ic, (sx, sy))
                sy += sk_size + 3
        except Exception:
            pass

    if lbl:
        surf.blit(lbl, lbl.get_rect(midtop=(box // 2, box + 5)))
    _CACHE[key] = surf
    return surf


def figure_buttons(color='offensive', target_h=None):
    """A row of full field-figure icons (King / Farm / Warriors|Fortress)."""
    _SH = settings.SCREEN_HEIGHT
    target_h = int(target_h or 0.16 * _SH)
    key = ('figbtns', color, target_h)
    if key in _CACHE:
        return _CACHE[key]
    figs = _ARMY_FIGURES.get(color, _ARMY_FIGURES['offensive'])
    gap = int(0.02 * settings.SCREEN_WIDTH)
    buttons = [field_figure_icon(name, fb, lbl, target_h) for name, fb, lbl in figs]
    total_w = sum(b.get_width() for b in buttons) + gap * (len(buttons) - 1)
    h = max(b.get_height() for b in buttons)
    surf = pygame.Surface((total_w, h), pygame.SRCALPHA)
    x = 0
    for b in buttons:
        surf.blit(b, (x, 0))
        x += b.get_width() + gap
    _CACHE[key] = surf
    return surf


def daggers_diagram(target_h=None):
    """Two Dagger cards joining into one bigger tactic (combine)."""
    _SH = settings.SCREEN_HEIGHT
    target_h = int(target_h or 0.18 * _SH)
    key = ('daggers', target_h)
    if key in _CACHE:
        return _CACHE[key]
    card_h = target_h
    a = _card_surface('Hearts', '8', card_h)
    b = _card_surface('Hearts', '9', card_h)
    big = _card_surface('Hearts', '10', int(card_h * 1.12))
    plus_font = settings.get_font(getattr(settings, 'FS_HEADING', 28), bold=True)
    plus = plus_font.render('+', True, (235, 222, 190))
    gap = int(0.012 * settings.SCREEN_WIDTH)
    arrow_w = int(0.05 * settings.SCREEN_WIDTH)
    total_w = (a.get_width() + gap + plus.get_width() + gap + b.get_width()
               + arrow_w + big.get_width())
    h = max(big.get_height(), card_h)
    surf = pygame.Surface((total_w, h), pygame.SRCALPHA)
    cy = h // 2
    x = 0
    surf.blit(a, (x, cy - a.get_height() // 2)); x += a.get_width() + gap
    surf.blit(plus, plus.get_rect(center=(x + plus.get_width() // 2, cy))); x += plus.get_width() + gap
    surf.blit(b, (x, cy - b.get_height() // 2)); x += b.get_width()
    _draw_arrow(surf, (x + gap, cy), (x + arrow_w - gap, cy)); x += arrow_w
    surf.blit(big, (x, cy - big.get_height() // 2))
    _CACHE[key] = surf
    return surf


def card_row(suit, ranks, max_w, target_h=None):
    """A row of the actual card images for ``ranks`` of ``suit``, scaled to fit."""
    _SH = settings.SCREEN_HEIGHT
    target_h = int(target_h or 0.13 * _SH)
    ranks = list(ranks or [])
    key = ('cardrow', suit, tuple(ranks), int(max_w), target_h)
    if key in _CACHE:
        return _CACHE[key]
    gap = max(3, int(0.004 * settings.SCREEN_WIDTH))
    cards = [_card_surface(suit, r, target_h) for r in ranks]
    total = sum(c.get_width() for c in cards) + gap * max(0, len(cards) - 1)
    if total > max_w and total > 0:
        scaled_h = max(12, int(target_h * (max_w / total)))
        cards = [_card_surface(suit, r, scaled_h) for r in ranks]
        total = sum(c.get_width() for c in cards) + gap * max(0, len(cards) - 1)
    h = max((c.get_height() for c in cards), default=1)
    surf = pygame.Surface((max(1, total), max(1, h)), pygame.SRCALPHA)
    x = 0
    for c in cards:
        surf.blit(c, (x, (h - c.get_height()) // 2))
        x += c.get_width() + gap
    _CACHE[key] = surf
    return surf


def clear_cache():
    _CACHE.clear()
