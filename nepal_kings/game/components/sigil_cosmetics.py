"""Procedural kingdom sigil glyphs.

Sigils are small monochrome-ish symbols overlaid on a kingdom's cluster on
the map (and as watermarks on individual hexes at high zoom).  Renderers
are intentionally cheap geometric primitives so they read clearly at the
small render sizes used in the world map / minimap.

Output surfaces are cached by ``(sigil_key, size, color)`` so per-frame
work is a single ``window.blit``.
"""

import functools
import math

import pygame

from config import settings


_SIGIL_CACHE_MAX = 128


def sigil_style(sigil_key):
    styles = getattr(settings, 'KINGDOM_SIGIL_STYLES', {}) or {}
    default = styles.get(getattr(settings, 'KINGDOM_SIGIL_DEFAULT_KEY',
                                 'sigil_none'), {})
    return styles.get(sigil_key, default)


def render_sigil(sigil_key, size, color):
    """Return a cached transparent surface containing the sigil glyph.

    ``size`` is the bounding box edge length in pixels.  ``color`` is the
    primary glyph color (typically the owner accent).  ``sigil_none``
    returns ``None`` so callers can skip blitting entirely.
    """
    if not sigil_key or sigil_key == 'sigil_none':
        return None
    size = int(max(8, size))
    color = tuple(int(c) for c in color[:3])
    return _render_sigil_cached(sigil_key, size, color)


@functools.lru_cache(maxsize=_SIGIL_CACHE_MAX)
def _render_sigil_cached(sigil_key, size, color):
    style = sigil_style(sigil_key) or {}
    shape = style.get('shape', 'none')
    drawer = _SHAPE_DRAWERS.get(shape)
    if drawer is None:
        return None
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    drawer(surf, size, color)
    return surf


# ── Shape drawers ─────────────────────────────────────────────────
#
# All drawers receive a fully-transparent ``size x size`` surface and the
# primary ``color`` tuple.  They render a soft outline pass underneath so
# the glyph reads against bright or dark tile backgrounds.

def _outline(color, darken=110):
    r, g, b = color
    return (max(0, r - darken), max(0, g - darken), max(0, b - darken))


def _draw_mountain(surf, sz, color):
    o = _outline(color)
    pts = [(sz * 0.08, sz * 0.85), (sz * 0.38, sz * 0.30),
           (sz * 0.55, sz * 0.55), (sz * 0.72, sz * 0.18),
           (sz * 0.95, sz * 0.85)]
    pygame.draw.polygon(surf, color, pts)
    pygame.draw.polygon(surf, o, pts, max(1, int(sz * 0.05)))


def _draw_sword(surf, sz, color):
    o = _outline(color)
    w = max(2, int(sz * 0.10))
    # Blade
    pygame.draw.line(surf, color, (sz / 2, sz * 0.08), (sz / 2, sz * 0.72), w)
    # Crossguard
    pygame.draw.line(surf, color, (sz * 0.25, sz * 0.72),
                     (sz * 0.75, sz * 0.72), w)
    # Hilt
    pygame.draw.line(surf, color, (sz / 2, sz * 0.72),
                     (sz / 2, sz * 0.92), w)
    # Pommel
    pygame.draw.circle(surf, color, (int(sz / 2), int(sz * 0.92)),
                       max(2, int(sz * 0.07)))
    pygame.draw.circle(surf, o, (int(sz / 2), int(sz * 0.92)),
                       max(2, int(sz * 0.07)), 1)


def _draw_wolf(surf, sz, color):
    o = _outline(color)
    # Stylized wolf head: triangle + ears
    pts = [(sz * 0.18, sz * 0.40), (sz * 0.30, sz * 0.20),
           (sz * 0.42, sz * 0.42), (sz * 0.58, sz * 0.42),
           (sz * 0.70, sz * 0.20), (sz * 0.82, sz * 0.40),
           (sz * 0.70, sz * 0.85), (sz * 0.30, sz * 0.85)]
    pygame.draw.polygon(surf, color, pts)
    pygame.draw.polygon(surf, o, pts, max(1, int(sz * 0.04)))
    # Eyes
    eye_r = max(1, int(sz * 0.06))
    pygame.draw.circle(surf, o, (int(sz * 0.38), int(sz * 0.55)), eye_r)
    pygame.draw.circle(surf, o, (int(sz * 0.62), int(sz * 0.55)), eye_r)


def _draw_lotus(surf, sz, color):
    o = _outline(color)
    cx, cy = sz / 2, sz * 0.60
    petal_r = sz * 0.30
    for ang_deg in (-90, -45, 0, 45, 90, 135, 180, 225):
        ang = math.radians(ang_deg)
        px = cx + math.cos(ang) * petal_r * 0.55
        py = cy + math.sin(ang) * petal_r * 0.55
        pygame.draw.ellipse(surf, color,
                            (px - petal_r * 0.45, py - petal_r * 0.25,
                             petal_r * 0.9, petal_r * 0.5))
    pygame.draw.circle(surf, o, (int(cx), int(cy)),
                       max(2, int(sz * 0.10)))


def _draw_tower(surf, sz, color):
    o = _outline(color)
    body = pygame.Rect(sz * 0.30, sz * 0.30, sz * 0.40, sz * 0.55)
    pygame.draw.rect(surf, color, body)
    pygame.draw.rect(surf, o, body, max(1, int(sz * 0.04)))
    # Battlements
    for i, x in enumerate((sz * 0.30, sz * 0.45, sz * 0.60)):
        r = pygame.Rect(x, sz * 0.20, sz * 0.10, sz * 0.12)
        pygame.draw.rect(surf, color, r)
        pygame.draw.rect(surf, o, r, 1)
    # Door
    pygame.draw.rect(surf, o,
                     (sz * 0.45, sz * 0.62, sz * 0.10, sz * 0.23))


def _draw_eagle(surf, sz, color):
    o = _outline(color)
    # Body
    pygame.draw.polygon(surf, color, [
        (sz * 0.50, sz * 0.30), (sz * 0.58, sz * 0.55),
        (sz * 0.50, sz * 0.85), (sz * 0.42, sz * 0.55)])
    # Wings
    pygame.draw.polygon(surf, color, [
        (sz * 0.50, sz * 0.40), (sz * 0.08, sz * 0.30),
        (sz * 0.20, sz * 0.55), (sz * 0.45, sz * 0.55)])
    pygame.draw.polygon(surf, color, [
        (sz * 0.50, sz * 0.40), (sz * 0.92, sz * 0.30),
        (sz * 0.80, sz * 0.55), (sz * 0.55, sz * 0.55)])
    # Head
    pygame.draw.circle(surf, color,
                       (int(sz * 0.50), int(sz * 0.25)),
                       max(2, int(sz * 0.08)))
    pygame.draw.circle(surf, o,
                       (int(sz * 0.50), int(sz * 0.25)),
                       max(2, int(sz * 0.08)), 1)


def _draw_sun(surf, sz, color):
    o = _outline(color)
    cx, cy = sz / 2, sz / 2
    r_inner = sz * 0.20
    r_outer = sz * 0.42
    for i in range(12):
        ang = math.radians(i * 30)
        x1 = cx + math.cos(ang) * r_inner
        y1 = cy + math.sin(ang) * r_inner
        x2 = cx + math.cos(ang) * r_outer
        y2 = cy + math.sin(ang) * r_outer
        pygame.draw.line(surf, color, (x1, y1), (x2, y2),
                         max(2, int(sz * 0.07)))
    pygame.draw.circle(surf, color, (int(cx), int(cy)), int(r_inner))
    pygame.draw.circle(surf, o, (int(cx), int(cy)), int(r_inner),
                       max(1, int(sz * 0.04)))


def _draw_crescent(surf, sz, color):
    o = _outline(color)
    cx, cy = sz / 2, sz / 2
    r = sz * 0.40
    # Full circle then subtract an offset circle for the bite.
    pygame.draw.circle(surf, color, (int(cx), int(cy)), int(r))
    pygame.draw.circle(surf, (0, 0, 0, 0),
                       (int(cx + r * 0.45), int(cy - r * 0.15)),
                       int(r * 0.85))
    # Outline by drawing the full disc edge then re-cutting.
    pygame.draw.circle(surf, o, (int(cx), int(cy)), int(r),
                       max(1, int(sz * 0.04)))
    pygame.draw.circle(surf, (0, 0, 0, 0),
                       (int(cx + r * 0.45), int(cy - r * 0.15)),
                       int(r * 0.85))


def _draw_lion(surf, sz, color):
    o = _outline(color)
    cx, cy = sz / 2, sz * 0.55
    # Mane
    mane_r = sz * 0.42
    points = []
    for i in range(16):
        ang = math.radians(i * (360 / 16))
        bump = 1.0 if i % 2 == 0 else 0.82
        points.append((cx + math.cos(ang) * mane_r * bump,
                       cy + math.sin(ang) * mane_r * bump))
    pygame.draw.polygon(surf, color, points)
    pygame.draw.polygon(surf, o, points, max(1, int(sz * 0.04)))
    # Face
    pygame.draw.circle(surf, o, (int(cx), int(cy)), int(sz * 0.22))
    eye_r = max(1, int(sz * 0.04))
    pygame.draw.circle(surf, color, (int(cx - sz * 0.08), int(cy - sz * 0.02)), eye_r)
    pygame.draw.circle(surf, color, (int(cx + sz * 0.08), int(cy - sz * 0.02)), eye_r)


def _draw_phoenix(surf, sz, color):
    o = _outline(color)
    # Spread wings + flame tail
    pygame.draw.polygon(surf, color, [
        (sz * 0.50, sz * 0.10), (sz * 0.20, sz * 0.50),
        (sz * 0.10, sz * 0.85), (sz * 0.35, sz * 0.65),
        (sz * 0.50, sz * 0.90), (sz * 0.65, sz * 0.65),
        (sz * 0.90, sz * 0.85), (sz * 0.80, sz * 0.50),
    ])
    pygame.draw.polygon(surf, o, [
        (sz * 0.50, sz * 0.10), (sz * 0.20, sz * 0.50),
        (sz * 0.10, sz * 0.85), (sz * 0.35, sz * 0.65),
        (sz * 0.50, sz * 0.90), (sz * 0.65, sz * 0.65),
        (sz * 0.90, sz * 0.85), (sz * 0.80, sz * 0.50),
    ], max(1, int(sz * 0.04)))


def _draw_dragon(surf, sz, color):
    o = _outline(color)
    # Serpentine body with wings
    pts = [
        (sz * 0.10, sz * 0.55), (sz * 0.25, sz * 0.30),
        (sz * 0.45, sz * 0.40), (sz * 0.55, sz * 0.20),
        (sz * 0.78, sz * 0.30), (sz * 0.90, sz * 0.55),
        (sz * 0.75, sz * 0.75), (sz * 0.55, sz * 0.65),
        (sz * 0.40, sz * 0.85), (sz * 0.25, sz * 0.78),
    ]
    pygame.draw.polygon(surf, color, pts)
    pygame.draw.polygon(surf, o, pts, max(1, int(sz * 0.04)))
    # Eye
    pygame.draw.circle(surf, o,
                       (int(sz * 0.78), int(sz * 0.40)),
                       max(2, int(sz * 0.05)))


def _draw_crown(surf, sz, color):
    o = _outline(color)
    base = pygame.Rect(sz * 0.15, sz * 0.55, sz * 0.70, sz * 0.20)
    pygame.draw.rect(surf, color, base)
    pygame.draw.rect(surf, o, base, max(1, int(sz * 0.04)))
    # 3 spires with jewels
    spires = [(sz * 0.22, sz * 0.20),
              (sz * 0.50, sz * 0.08),
              (sz * 0.78, sz * 0.20)]
    for sx, sy in spires:
        pygame.draw.polygon(surf, color,
                            [(sx, sy), (sx - sz * 0.07, sz * 0.55),
                             (sx + sz * 0.07, sz * 0.55)])
        pygame.draw.circle(surf, o, (int(sx), int(sy)),
                           max(2, int(sz * 0.05)))


def _draw_serpent(surf, sz, color):
    o = _outline(color)
    # S-curve drawn as a thick poly-line
    pts = []
    steps = 24
    for i in range(steps + 1):
        t = i / steps
        x = sz * 0.10 + (sz * 0.80) * t
        y = sz * 0.50 + math.sin(t * math.pi * 2.0) * sz * 0.22
        pts.append((x, y))
    pygame.draw.lines(surf, color, False, pts, max(3, int(sz * 0.10)))
    # Head
    head_cx, head_cy = pts[-1]
    pygame.draw.circle(surf, color, (int(head_cx), int(head_cy)),
                       max(2, int(sz * 0.10)))
    pygame.draw.circle(surf, o, (int(head_cx), int(head_cy)),
                       max(2, int(sz * 0.10)), 1)


_SHAPE_DRAWERS = {
    'mountain': _draw_mountain,
    'sword':    _draw_sword,
    'wolf':     _draw_wolf,
    'lotus':    _draw_lotus,
    'tower':    _draw_tower,
    'eagle':    _draw_eagle,
    'sun':      _draw_sun,
    'crescent': _draw_crescent,
    'lion':     _draw_lion,
    'phoenix':  _draw_phoenix,
    'dragon':   _draw_dragon,
    'crown':    _draw_crown,
    'serpent':  _draw_serpent,
}
