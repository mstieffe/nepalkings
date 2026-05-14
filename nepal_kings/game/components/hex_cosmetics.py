# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Cached procedural cosmetic art for hex tiles.

This module produces fully-rendered ``pygame.Surface`` art for kingdom
cosmetics — surfaces, center emblems, and border vertex ornaments.  All
results are LRU-cached by ``(skin_key, hex_size)`` so the heavy procedural
drawing only happens once per zoom level and is then cheaply blitted every
frame.  This keeps the kingdom view smooth on the web client even with a
remote server in the loop.

Public API:

    render_surface_art(skin_key, hex_size)       -> pygame.Surface
    render_center_emblem(skin_key, hex_size)     -> pygame.Surface | None
    render_vertex_ornament(border_key, hex_size) -> pygame.Surface | None
    border_style(border_key)                     -> str
    border_rarity(border_key)                    -> str

The drawing primitives stay deterministic by seeding a tiny LCG with the skin
name, so the same skin always produces the same procedural pattern.
"""

import functools
import math
import pygame

from config import settings


# ── Geometry helpers ───────────────────────────────────────────────

_HEX_ANGLES = [math.radians(60 * i) for i in range(6)]


def _hex_polygon(cx, cy, size):
    return [(cx + size * math.cos(a), cy + size * math.sin(a))
            for a in _HEX_ANGLES]


def _make_alpha(w, h):
    return pygame.Surface((w, h), pygame.SRCALPHA)


def _seed_for(skin_key):
    """Stable 32-bit seed derived from the skin key."""
    seed = 0
    for ch in skin_key:
        seed = (seed * 131 + ord(ch)) & 0xFFFFFFFF
    return seed or 1


def _lcg(seed):
    """Return a function yielding deterministic floats in [0, 1)."""
    state = [seed & 0xFFFFFFFF or 1]

    def nxt():
        state[0] = (state[0] * 1103515245 + 12345) & 0x7FFFFFFF
        return state[0] / float(0x7FFFFFFF)

    return nxt


def _apply_hex_mask(surf, hex_size):
    """Multiply ``surf`` alpha by a hex polygon centered on the surface."""
    w, h = surf.get_size()
    cx, cy = w / 2, h / 2
    mask = _make_alpha(w, h)
    pygame.draw.polygon(mask, (255, 255, 255, 255), _hex_polygon(cx, cy, hex_size))
    surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)


def _draw_radial_gradient(surf, cx, cy, radius, center_clr, rim_clr, steps=12):
    """Cheap radial gradient via concentric polygon fills (no per-pixel work)."""
    if radius <= 0:
        return
    for i in range(steps, 0, -1):
        t = i / steps
        clr = (
            int(rim_clr[0] * t + center_clr[0] * (1 - t)),
            int(rim_clr[1] * t + center_clr[1] * (1 - t)),
            int(rim_clr[2] * t + center_clr[2] * (1 - t)),
            int((rim_clr[3] if len(rim_clr) > 3 else 255) * t
                + (center_clr[3] if len(center_clr) > 3 else 255) * (1 - t)),
        )
        r = max(1.0, radius * t)
        pygame.draw.polygon(surf, clr, _hex_polygon(cx, cy, r))


def _draw_vertical_gradient(surf, cx, cy, radius, top_clr, bot_clr, steps=10):
    """Banded vertical gradient inside the hex bounding box."""
    if radius <= 0:
        return
    top = int(cy - radius)
    band_h = max(1, int((2 * radius) / steps))
    for i in range(steps):
        t = i / max(1, steps - 1)
        clr = (
            int(top_clr[0] * (1 - t) + bot_clr[0] * t),
            int(top_clr[1] * (1 - t) + bot_clr[1] * t),
            int(top_clr[2] * (1 - t) + bot_clr[2] * t),
            int((top_clr[3] if len(top_clr) > 3 else 255) * (1 - t)
                + (bot_clr[3] if len(bot_clr) > 3 else 255) * t),
        )
        rect = pygame.Rect(int(cx - radius - 1), top + i * band_h,
                           int(radius * 2 + 2), band_h + 1)
        pygame.draw.rect(surf, clr, rect)


# ═══════════════════════════════════════════════════════════════════
#  Surface art generators
# ═══════════════════════════════════════════════════════════════════

def _draw_cobblestones(surf, cx, cy, sz, skin):
    base = skin.get('base_clr', (180, 178, 172, 210))
    mortar = skin.get('mortar_clr', (52, 50, 48, 230))
    hl = skin.get('highlight_clr', (220, 218, 210, 200))
    sh = skin.get('shadow_clr', (110, 108, 102, 180))
    pygame.draw.polygon(surf, base, _hex_polygon(cx, cy, sz))

    rng = _lcg(_seed_for('cobblestone'))
    # 14 cobblestones placed on a jittered grid covering the hex.
    cols, rows = 4, 4
    span = sz * 1.7
    step_x = span / cols
    step_y = span / rows
    stones = []
    for r in range(rows):
        for c in range(cols):
            jx = (rng() - 0.5) * step_x * 0.4
            jy = (rng() - 0.5) * step_y * 0.4
            px = cx - span / 2 + step_x * (c + 0.5) + jx
            py = cy - span / 2 + step_y * (r + 0.5) + jy
            radius = step_x * (0.42 + rng() * 0.18)
            sides = 5 + int(rng() * 3)
            shade_jitter = int((rng() - 0.5) * 26)
            stone_clr = (
                max(0, min(255, base[0] + shade_jitter)),
                max(0, min(255, base[1] + shade_jitter)),
                max(0, min(255, base[2] + shade_jitter)),
                base[3] if len(base) > 3 else 255,
            )
            pts = []
            for s in range(sides):
                a = 2 * math.pi * s / sides + rng() * 0.4
                rr = radius * (0.78 + rng() * 0.36)
                pts.append((px + math.cos(a) * rr, py + math.sin(a) * rr))
            stones.append((pts, stone_clr, px, py, radius))

    # Mortar under-coat (drawn before stones) — solid dark base wash.
    pygame.draw.polygon(surf, mortar, _hex_polygon(cx, cy, sz * 0.99))
    # Stones overlap one another so the mortar shows only at gaps.
    for pts, stone_clr, _px, _py, _r in stones:
        pygame.draw.polygon(surf, stone_clr, pts)

    # Top-edge highlights and bottom-edge shadows for relief.
    for pts, _stone_clr, px, py, r in stones:
        top_pts = [p for p in pts if p[1] < py]
        bot_pts = [p for p in pts if p[1] >= py]
        if len(top_pts) >= 2:
            top_pts.sort(key=lambda p: p[0])
            pygame.draw.lines(surf, hl, False, top_pts,
                              max(1, int(sz * 0.025)))
        if len(bot_pts) >= 2:
            bot_pts.sort(key=lambda p: p[0])
            pygame.draw.lines(surf, sh, False, bot_pts,
                              max(1, int(sz * 0.020)))


def _draw_parchment(surf, cx, cy, sz, skin):
    top = skin.get('base_clr_top', (250, 232, 188, 215))
    bot = skin.get('base_clr_bot', (228, 198, 144, 215))
    ink = skin.get('ink_clr', (118, 76, 32, 175))
    stain = skin.get('stain_clr', (96, 56, 22, 95))
    _draw_vertical_gradient(surf, cx, cy, sz, top, bot, steps=14)

    rng = _lcg(_seed_for('parchment'))
    line_w = max(1, int(sz * 0.014))
    # 40 short cross-hatched ink strokes covering the whole hex at two angles.
    for i in range(40):
        angle = math.radians(15 if i % 2 == 0 else -15)
        x = cx + (rng() * 2 - 1) * sz * 0.95
        y = cy + (rng() * 2 - 1) * sz * 0.85
        length = sz * (0.10 + rng() * 0.10)
        x2 = x + math.cos(angle) * length
        y2 = y + math.sin(angle) * length
        pygame.draw.line(surf, ink, (x, y), (x2, y2), line_w)

    # 4 corner ink stains as soft dark blobs.
    for corner in (0, 1, 3, 4):
        a = _HEX_ANGLES[corner]
        bx = cx + math.cos(a) * sz * 0.78
        by = cy + math.sin(a) * sz * 0.78
        for j in range(3):
            r = int(sz * (0.18 - j * 0.04))
            pygame.draw.circle(surf, stain, (int(bx), int(by)), max(1, r))


def _draw_grass(surf, cx, cy, sz, skin):
    base = skin.get('base_clr', (86, 142, 64, 210))
    dark = skin.get('blade_dark', (44, 96, 36, 220))
    light = skin.get('blade_light', (164, 200, 110, 220))
    flowers = skin.get('flower_clrs', ((250, 244, 200, 220),))
    pygame.draw.polygon(surf, base, _hex_polygon(cx, cy, sz))

    rng = _lcg(_seed_for('grass'))
    blade_h = max(2, int(sz * 0.13))
    line_w = max(1, int(sz * 0.025))
    # ~80 blade strokes tiled across the hex.
    for _ in range(80):
        x = cx + (rng() * 2 - 1) * sz * 0.95
        y = cy + (rng() * 2 - 1) * sz * 0.85
        tilt = (rng() - 0.5) * blade_h * 0.6
        clr = light if rng() < 0.4 else dark
        pygame.draw.line(surf, clr, (x, y),
                         (x + tilt, y - blade_h), line_w)
    # Sprinkle a few micro-flowers.
    for _ in range(8):
        x = cx + (rng() * 2 - 1) * sz * 0.85
        y = cy + (rng() * 2 - 1) * sz * 0.8
        col = flowers[int(rng() * len(flowers)) % len(flowers)]
        pygame.draw.circle(surf, col, (int(x), int(y)), max(1, int(sz * 0.022)))


def _draw_snow(surf, cx, cy, sz, skin):
    center = skin.get('base_clr_center', (246, 252, 255, 220))
    rim = skin.get('base_clr_rim', (188, 220, 240, 220))
    flake = skin.get('flake_clr', (255, 255, 255, 235))
    halo = skin.get('halo_clr', (255, 255, 255, 80))
    _draw_radial_gradient(surf, cx, cy, sz, center, rim, steps=12)

    rng = _lcg(_seed_for('snow'))
    line_w = max(1, int(sz * 0.018))
    arm = max(3, int(sz * 0.10))
    # 4×3 jittered snowflake field covering the whole hex.
    for r in range(3):
        for c in range(4):
            jx = (rng() - 0.5) * sz * 0.25
            jy = (rng() - 0.5) * sz * 0.25
            fx = cx - sz * 0.85 + sz * 0.55 * c + jx
            fy = cy - sz * 0.65 + sz * 0.55 * r + jy
            pygame.draw.line(surf, flake, (fx - arm, fy), (fx + arm, fy), line_w)
            pygame.draw.line(surf, flake, (fx, fy - arm), (fx, fy + arm), line_w)
            pygame.draw.line(surf, flake,
                             (fx - arm * 0.7, fy - arm * 0.7),
                             (fx + arm * 0.7, fy + arm * 0.7), line_w)
            pygame.draw.line(surf, flake,
                             (fx - arm * 0.7, fy + arm * 0.7),
                             (fx + arm * 0.7, fy - arm * 0.7), line_w)
    # 1-pixel inner halo ring for frosted edge feel.
    pygame.draw.polygon(surf, halo, _hex_polygon(cx, cy, sz * 0.96), 2)


def _draw_forest(surf, cx, cy, sz, skin):
    base = skin.get('base_clr', (32, 78, 44, 215))
    dark = skin.get('leaf_dark', (52, 116, 64, 230))
    light = skin.get('leaf_light', (108, 184, 102, 230))
    dapple = skin.get('dapple_clr', (224, 240, 158, 145))
    pygame.draw.polygon(surf, base, _hex_polygon(cx, cy, sz))

    rng = _lcg(_seed_for('forest'))
    # 60 overlapping ellipse leaves covering the hex.
    leaves = []
    for _ in range(60):
        x = cx + (rng() * 2 - 1) * sz * 0.92
        y = cy + (rng() * 2 - 1) * sz * 0.85
        w = int(sz * (0.13 + rng() * 0.10))
        h = max(2, int(w * 0.55))
        clr = light if rng() < 0.45 else dark
        leaves.append((x, y, w, h, clr))
    # Back-to-front by y for depth.
    leaves.sort(key=lambda l: l[1])
    for x, y, w, h, clr in leaves:
        rect = pygame.Rect(int(x - w / 2), int(y - h / 2), w, h)
        pygame.draw.ellipse(surf, clr, rect)
    # Dappled-light specks.
    for _ in range(20):
        x = cx + (rng() * 2 - 1) * sz * 0.85
        y = cy + (rng() * 2 - 1) * sz * 0.8
        pygame.draw.circle(surf, dapple, (int(x), int(y)),
                           max(1, int(sz * 0.025)))


def _draw_marble(surf, cx, cy, sz, skin):
    base = skin.get('base_clr', (240, 236, 228, 215))
    vein = skin.get('vein_clr', (118, 108, 132, 165))
    vein_dark = skin.get('vein_dark', (78, 70, 92, 145))
    hl = skin.get('highlight_clr', (255, 252, 244, 130))
    pygame.draw.polygon(surf, base, _hex_polygon(cx, cy, sz))

    rng = _lcg(_seed_for('marble'))
    # 6 long flowing veins drawn as multi-segment polylines.
    for v in range(6):
        a0 = 2 * math.pi * (v / 6) + rng() * 0.4
        x = cx + math.cos(a0) * sz * 0.95
        y = cy + math.sin(a0) * sz * 0.95
        pts = [(x, y)]
        for _ in range(8):
            a0 += (rng() - 0.5) * 0.9
            x += math.cos(a0) * sz * 0.22
            y += math.sin(a0) * sz * 0.22
            pts.append((x, y))
        thick = max(1, int(sz * 0.035))
        pygame.draw.lines(surf, vein_dark, False, pts, thick)
        pygame.draw.lines(surf, vein, False, pts, max(1, thick - 1))
    # Soft warm highlight at upper area (single ellipse with low alpha).
    pygame.draw.ellipse(surf, hl, pygame.Rect(
        int(cx - sz * 0.6), int(cy - sz * 0.7),
        int(sz * 1.2), int(sz * 0.55)))


def _draw_dusk(surf, cx, cy, sz, skin):
    center = skin.get('base_clr_center', (90, 50, 156, 225))
    rim = skin.get('base_clr_rim', (20, 14, 52, 230))
    star = skin.get('star_clr', (250, 226, 132, 230))
    star2 = skin.get('star_clr_alt', (200, 180, 240, 220))
    _draw_radial_gradient(surf, cx, cy, sz, center, rim, steps=14)

    rng = _lcg(_seed_for('dusk'))
    # 25 4-point stars in two sizes scattered across the hex.
    for _ in range(25):
        x = cx + (rng() * 2 - 1) * sz * 0.92
        y = cy + (rng() * 2 - 1) * sz * 0.85
        big = rng() < 0.35
        r = sz * (0.05 if big else 0.028)
        clr = star if rng() < 0.7 else star2
        pts = [
            (x, y - r),
            (x + r * 0.32, y - r * 0.32),
            (x + r, y),
            (x + r * 0.32, y + r * 0.32),
            (x, y + r),
            (x - r * 0.32, y + r * 0.32),
            (x - r, y),
            (x - r * 0.32, y - r * 0.32),
        ]
        pygame.draw.polygon(surf, clr, pts)


def _draw_lava(surf, cx, cy, sz, skin):
    center = skin.get('base_clr_center', (132, 36, 16, 230))
    rim = skin.get('base_clr_rim', (28, 10, 8, 235))
    crack = skin.get('crack_clr', (255, 156, 60, 235))
    crack_core = skin.get('crack_core_clr', (255, 232, 140, 230))
    ember = skin.get('ember_clr', (255, 196, 96, 230))
    _draw_radial_gradient(surf, cx, cy, sz, center, rim, steps=14)

    rng = _lcg(_seed_for('lava'))
    # 12 glowing cracks radiating from center outward.
    for v in range(12):
        a0 = 2 * math.pi * (v / 12) + rng() * 0.3
        x, y = cx, cy
        pts = [(x, y)]
        for _ in range(6):
            a0 += (rng() - 0.5) * 0.7
            step = sz * (0.13 + rng() * 0.06)
            x += math.cos(a0) * step
            y += math.sin(a0) * step
            pts.append((x, y))
        thick = max(2, int(sz * 0.045))
        pygame.draw.lines(surf, crack, False, pts, thick)
        pygame.draw.lines(surf, crack_core, False, pts, max(1, thick - 2))
    # Ember speckles near cracks.
    for _ in range(18):
        x = cx + (rng() * 2 - 1) * sz * 0.85
        y = cy + (rng() * 2 - 1) * sz * 0.8
        pygame.draw.circle(surf, ember, (int(x), int(y)),
                           max(1, int(sz * 0.025)))


def _draw_starter(surf, cx, cy, sz, skin):
    """Default 'starter' surface: faint cross-hatch + soft vignette.

    Used for the free ``surface_plain`` so newly-conquered land is visually
    distinct from neutral terrain without competing with premium surfaces.
    """
    base_top = skin.get('base_clr_top', (236, 220, 184, 110))
    base_bot = skin.get('base_clr_bot', (196, 174, 128, 110))
    hatch_clr = skin.get('hatch_clr', (96, 72, 36, 55))
    vignette_clr = skin.get('vignette_clr', (32, 22, 12, 70))

    # Soft warm tinted vertical gradient (low alpha keeps suit fill readable).
    _draw_vertical_gradient(surf, cx, cy, sz, base_top, base_bot, steps=10)

    # Thin diagonal cross-hatch lines (two directions).
    step = max(3, int(sz * 0.18))
    thick = max(1, int(sz * 0.035))
    bound = int(sz * 1.05)
    # Diagonal: top-left → bottom-right.
    for i in range(-bound, bound + 1, step):
        p0 = (cx - bound, cy + i - bound)
        p1 = (cx + bound, cy + i + bound)
        pygame.draw.line(surf, hatch_clr, p0, p1, thick)
    # Diagonal: top-right → bottom-left.
    for i in range(-bound, bound + 1, step):
        p0 = (cx - bound, cy - i + bound)
        p1 = (cx + bound, cy - i - bound)
        pygame.draw.line(surf, hatch_clr, p0, p1, thick)

    # Soft rim vignette so the centre stays luminous and edges darken slightly.
    rim_steps = 6
    for i in range(rim_steps):
        t = 1.0 - i / rim_steps
        r = int(sz * (1.0 - i * 0.08))
        a = int(vignette_clr[3] * (1.0 - t) * 0.6)
        if a <= 0 or r <= 0:
            continue
        pygame.draw.polygon(
            surf,
            (vignette_clr[0], vignette_clr[1], vignette_clr[2], a),
            _hex_polygon(cx, cy, r),
            max(1, int(sz * 0.06)),
        )


_SURFACE_DRAWERS = {
    'starter': _draw_starter,
    'cobblestone': _draw_cobblestones,
    'parchment': _draw_parchment,
    'grass': _draw_grass,
    'snow': _draw_snow,
    'forest_canopy': _draw_forest,
    'marble': _draw_marble,
    'dusk_stars': _draw_dusk,
    'lava': _draw_lava,
}


@functools.lru_cache(maxsize=128)
def render_surface_art(skin_key, hex_size):
    """Return a fully-rendered cosmetic surface for one hex.

    The returned surface is ``2*hex_size × 2*hex_size`` with per-pixel alpha;
    blit it at ``(scx - hex_size, scy - hex_size)``.  Pixels outside the hex
    polygon have alpha 0.  The result is cached per ``(skin_key, hex_size)``.
    """
    target_sz = max(8, int(hex_size))
    # Supersample small hexes so procedural detail survives downscaling.
    scale = 4 if target_sz < 16 else (2 if target_sz < 32 else 1)
    sz = target_sz * scale
    surf = _make_alpha(sz * 2, sz * 2)
    cx, cy = sz, sz
    skin = settings.HEX_SURFACE_SKINS.get(skin_key) or \
        settings.HEX_SURFACE_SKINS.get('surface_plain', {})
    style = skin.get('style')
    drawer = _SURFACE_DRAWERS.get(style)
    if drawer is None:
        if scale > 1:
            return pygame.transform.smoothscale(surf, (target_sz * 2, target_sz * 2))
        return surf
    drawer(surf, cx, cy, sz, skin)
    _apply_hex_mask(surf, sz)
    if scale > 1:
        surf = pygame.transform.smoothscale(surf, (target_sz * 2, target_sz * 2))
    return surf


# ═══════════════════════════════════════════════════════════════════
#  Center emblems
# ═══════════════════════════════════════════════════════════════════

_EMBLEM_BASE_CLR = (255, 255, 255, 70)
_EMBLEM_DARK_CLR = (10, 10, 10, 90)


def _emblem_clr(skin):
    """Pick an emblem colour that contrasts with the surface base."""
    # Lava + dusk (dark surfaces) get a luminous warm emblem.
    base = (skin.get('base_clr_center') or skin.get('base_clr')
            or (180, 180, 180, 255))
    luminance = (base[0] * 0.299 + base[1] * 0.587 + base[2] * 0.114)
    return _EMBLEM_BASE_CLR if luminance < 140 else _EMBLEM_DARK_CLR


def _draw_emblem_feather(surf, cx, cy, sz, clr):
    pts = [
        (cx, cy - sz),
        (cx + sz * 0.30, cy - sz * 0.45),
        (cx + sz * 0.20, cy + sz * 0.35),
        (cx, cy + sz * 0.5),
        (cx - sz * 0.20, cy + sz * 0.35),
        (cx - sz * 0.30, cy - sz * 0.45),
    ]
    pygame.draw.polygon(surf, clr, pts)
    pygame.draw.line(surf, clr, (cx, cy - sz * 0.85),
                     (cx, cy + sz * 0.45), max(1, int(sz * 0.06)))


def _draw_emblem_arch(surf, cx, cy, sz, clr):
    rect = pygame.Rect(int(cx - sz * 0.7), int(cy - sz * 0.7),
                       int(sz * 1.4), int(sz * 1.4))
    pygame.draw.arc(surf, clr, rect, 0, math.pi, max(2, int(sz * 0.18)))
    pygame.draw.line(surf, clr,
                     (cx - sz * 0.7, cy), (cx - sz * 0.7, cy + sz * 0.5),
                     max(2, int(sz * 0.14)))
    pygame.draw.line(surf, clr,
                     (cx + sz * 0.7, cy), (cx + sz * 0.7, cy + sz * 0.5),
                     max(2, int(sz * 0.14)))


def _draw_emblem_leaf(surf, cx, cy, sz, clr):
    pts = [
        (cx, cy - sz * 0.85),
        (cx + sz * 0.55, cy - sz * 0.20),
        (cx + sz * 0.30, cy + sz * 0.55),
        (cx, cy + sz * 0.85),
        (cx - sz * 0.30, cy + sz * 0.55),
        (cx - sz * 0.55, cy - sz * 0.20),
    ]
    pygame.draw.polygon(surf, clr, pts)


def _draw_emblem_column(surf, cx, cy, sz, clr):
    cap = pygame.Rect(int(cx - sz * 0.55), int(cy - sz * 0.85),
                      int(sz * 1.1), int(sz * 0.20))
    base = pygame.Rect(int(cx - sz * 0.55), int(cy + sz * 0.65),
                       int(sz * 1.1), int(sz * 0.20))
    shaft = pygame.Rect(int(cx - sz * 0.30), int(cy - sz * 0.65),
                        int(sz * 0.60), int(sz * 1.30))
    for r in (cap, base, shaft):
        pygame.draw.rect(surf, clr, r)


def _draw_emblem_crescent(surf, cx, cy, sz, clr):
    pygame.draw.circle(surf, clr, (int(cx), int(cy)), int(sz * 0.85))
    cut = (clr[0], clr[1], clr[2], 0)
    pygame.draw.circle(surf, cut,
                       (int(cx + sz * 0.30), int(cy - sz * 0.10)),
                       int(sz * 0.78))


def _draw_emblem_flame(surf, cx, cy, sz, clr):
    pts = [
        (cx, cy - sz * 0.95),
        (cx + sz * 0.32, cy - sz * 0.20),
        (cx + sz * 0.50, cy + sz * 0.50),
        (cx + sz * 0.10, cy + sz * 0.85),
        (cx - sz * 0.30, cy + sz * 0.55),
        (cx - sz * 0.45, cy - sz * 0.10),
        (cx - sz * 0.10, cy - sz * 0.55),
    ]
    pygame.draw.polygon(surf, clr, pts)


_EMBLEM_DRAWERS = {
    'feather': _draw_emblem_feather,
    'arch': _draw_emblem_arch,
    'leaf': _draw_emblem_leaf,
    'column': _draw_emblem_column,
    'crescent': _draw_emblem_crescent,
    'flame': _draw_emblem_flame,
}


@functools.lru_cache(maxsize=128)
def render_center_emblem(skin_key, hex_size):
    """Return a small emblem surface, or ``None`` if this skin has no emblem.

    Emblems are only drawn for surfaces with rarity ≥ rare.
    """
    skin = settings.HEX_SURFACE_SKINS.get(skin_key)
    if not skin:
        return None
    if skin.get('rarity') not in ('rare', 'epic'):
        return None
    name = skin.get('emblem')
    drawer = _EMBLEM_DRAWERS.get(name)
    if drawer is None:
        return None
    target_sz = max(10, int(hex_size * 0.40))
    scale = 4 if target_sz < 16 else (2 if target_sz < 32 else 1)
    sz = target_sz * scale
    surf = _make_alpha(sz * 2, sz * 2)
    drawer(surf, sz, sz, sz * 0.85, _emblem_clr(skin))
    if scale > 1:
        surf = pygame.transform.smoothscale(surf, (target_sz * 2, target_sz * 2))
    return surf


# ═══════════════════════════════════════════════════════════════════
#  Vertex ornaments (border-tied)
# ═══════════════════════════════════════════════════════════════════

@functools.lru_cache(maxsize=64)
def render_vertex_ornament(border_key, hex_size):
    """Return a small ornament centered on a hex corner, or ``None``.

    Ornaments are only emitted at rarity ≥ rare:
        rare  → small filled gem (circle)
        epic  → 5-point star outline
    """
    skin = settings.HEX_BORDER_SKINS.get(border_key)
    if not skin:
        return None
    rarity = skin.get('rarity')
    if rarity not in ('rare', 'epic'):
        return None
    target_r = max(3, int(hex_size * 0.10))
    scale = 4 if target_r < 6 else (2 if target_r < 12 else 1)
    r = target_r * scale
    surf = _make_alpha(r * 4, r * 4)
    cx = cy = r * 2
    outer = skin.get('outer', (40, 40, 40))
    main = skin.get('main', (220, 220, 220))
    hl = skin.get('highlight', (255, 255, 255))
    if rarity == 'rare':
        pygame.draw.circle(surf, outer, (cx, cy), r + 1)
        pygame.draw.circle(surf, main, (cx, cy), r)
        pygame.draw.circle(surf, hl,
                           (int(cx - r * 0.3), int(cy - r * 0.3)),
                           max(1, r // 3))
    else:  # epic
        pts = []
        for i in range(10):
            a = -math.pi / 2 + i * math.pi / 5
            rr = r if i % 2 == 0 else r * 0.45
            pts.append((cx + math.cos(a) * rr, cy + math.sin(a) * rr))
        pygame.draw.polygon(surf, outer, pts)
        pygame.draw.polygon(surf, main, pts, max(1, int(r * 0.30)))
    if scale > 1:
        surf = pygame.transform.smoothscale(surf, (target_r * 4, target_r * 4))
    return surf


# ═══════════════════════════════════════════════════════════════════
#  Border style accessors (used by hex_map)
# ═══════════════════════════════════════════════════════════════════

def border_style(border_key):
    skin = settings.HEX_BORDER_SKINS.get(border_key)
    if not skin:
        return 'simple'
    return skin.get('style', 'simple')


def border_rarity(border_key):
    skin = settings.HEX_BORDER_SKINS.get(border_key)
    if not skin:
        return 'default'
    return skin.get('rarity', 'default')


def clear_caches():
    """Drop all LRU caches; called by tests and by zoom changes if desired."""
    render_surface_art.cache_clear()
    render_center_emblem.cache_clear()
    render_vertex_ornament.cache_clear()
