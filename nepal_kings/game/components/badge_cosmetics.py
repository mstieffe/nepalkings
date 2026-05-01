# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Cached procedural art for kingdom name-badge cosmetics.

Each ``render_badge`` call returns a ready-to-blit ``pygame.Surface``
containing the badge background, frame, ornaments and the rendered text.
Surfaces are cached by ``(badge_key, text, font_id, target_h, shimmer_bucket)``
so the heavy procedural drawing only happens on cache misses; per-frame work
is a single ``window.blit``.

For epic-tier badges with ``shimmer: True``, the optional ``shimmer_phase``
argument selects one of ``_SHIMMER_PHASES`` quantized frames (12 buckets per
1.2 s loop is enough for a smooth pulse without thrashing the cache).
"""

import functools
import math

import pygame

from config import settings


# Quantize the shimmer animation so the LRU cache stays small.
_SHIMMER_PHASES = 12

# Cache headroom: ~kingdom count * SKUs * shimmer_buckets.  256 covers a
# stress case of ~25 visible kingdoms with epic shimmer plus the chip
# variants at high zoom.
_BADGE_CACHE_MAX = 256


# ── Public helpers ─────────────────────────────────────────────────

def badge_style(badge_key):
    styles = getattr(settings, 'HEX_BADGE_STYLES', {}) or {}
    default = styles.get(getattr(settings, 'HEX_BADGE_DEFAULT_KEY',
                                 'badge_plain'), {})
    return styles.get(badge_key, default)


def badge_rarity(badge_key):
    return (badge_style(badge_key) or {}).get('rarity', 'default')


def badge_supports_shimmer(badge_key):
    return bool((badge_style(badge_key) or {}).get('shimmer'))


def shimmer_phase_for(now_ms, *, period_ms=1200):
    """Quantize ``now_ms`` to a shimmer bucket in ``[0, _SHIMMER_PHASES)``."""
    if period_ms <= 0:
        return 0
    return int((now_ms % period_ms) / period_ms * _SHIMMER_PHASES) % _SHIMMER_PHASES


def render_badge(badge_key, text, font, *, target_h=None, shimmer_phase=0):
    """Return a cached badge surface for ``(badge_key, text)``.

    The returned surface is shared between callers; **never** mutate it.
    Use ``surface.blit`` only.

    Parameters
    ----------
    badge_key : str
        A key from ``settings.HEX_BADGE_STYLES``.
    text : str
        The kingdom name (or other label) to render inside the badge.
    font : pygame.font.Font
        The font used to render the text.
    target_h : int | None
        Optional vertical scale hint (chip size at high zoom, larger pill at
        low zoom).  Defaults to ``font.get_height() * 1.6``.
    shimmer_phase : int
        Bucket index in ``[0, _SHIMMER_PHASES)``.  Ignored for non-shimmer
        badges.
    """
    style = badge_style(badge_key)
    if not style:
        return _blank_surface()
    if not badge_supports_shimmer(badge_key):
        shimmer_phase = 0
    if target_h is None:
        target_h = int(font.get_height() * 1.6)
    text = str(text or '')
    return _cached_render(badge_key, text, id(font), int(target_h),
                          int(shimmer_phase) % _SHIMMER_PHASES, font)


def clear_badge_cache():
    _cached_render.cache_clear()


# ── Cache layer ────────────────────────────────────────────────────

@functools.lru_cache(maxsize=_BADGE_CACHE_MAX)
def _cached_render(badge_key, text, font_id, target_h, shimmer_phase, font):
    """LRU-cached factory.  ``font`` is passed positionally to keep the cache
    key hashable (we hash by ``font_id``, not the Font object)."""
    style = badge_style(badge_key)
    text_clr = style.get('text', (255, 238, 150))
    text_surf = font.render(text, True, text_clr)
    th = max(target_h, text_surf.get_height() + 4)

    shape = style.get('shape', 'pill')
    renderer = _SHAPE_RENDERERS.get(shape, _render_pill)
    return renderer(style, text_surf, th, shimmer_phase)


def _blank_surface():
    return pygame.Surface((1, 1), pygame.SRCALPHA)


# ── Geometry helpers ───────────────────────────────────────────────

def _pad_for(text_h):
    pad_x = max(4, int(text_h * 0.45))
    pad_y = max(2, int(text_h * 0.25))
    return pad_x, pad_y


def _vertical_gradient(surf, rect, top_clr, bot_clr, *, steps=10,
                       border_radius=0):
    """Fill ``rect`` with a stacked-band vertical gradient.  Alpha-aware."""
    if rect.h <= 0 or rect.w <= 0:
        return
    band_h = max(1, rect.h // max(1, steps))
    y = rect.y
    end_y = rect.y + rect.h
    while y < end_y:
        t = (y - rect.y) / max(1, rect.h - 1)
        clr = (
            int(top_clr[0] * (1 - t) + bot_clr[0] * t),
            int(top_clr[1] * (1 - t) + bot_clr[1] * t),
            int(top_clr[2] * (1 - t) + bot_clr[2] * t),
            int((top_clr[3] if len(top_clr) > 3 else 255) * (1 - t)
                + (bot_clr[3] if len(bot_clr) > 3 else 255) * t),
        )
        h = min(band_h, end_y - y)
        if border_radius > 0:
            band = pygame.Rect(rect.x, y, rect.w, h)
            pygame.draw.rect(surf, clr, band)
        else:
            pygame.draw.rect(surf, clr, pygame.Rect(rect.x, y, rect.w, h))
        y += band_h


def _round_clip_mask(size, radius):
    mask = pygame.Surface(size, pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255),
                     pygame.Rect(0, 0, *size), border_radius=radius)
    return mask


def _seed_for(*parts):
    seed = 0
    for p in parts:
        for ch in str(p):
            seed = (seed * 131 + ord(ch)) & 0xFFFFFFFF
    return seed or 1


def _lcg(seed):
    state = [seed & 0xFFFFFFFF or 1]

    def nxt():
        state[0] = (state[0] * 1103515245 + 12345) & 0x7FFFFFFF
        return state[0] / float(0x7FFFFFFF)

    return nxt


# ═══════════════════════════════════════════════════════════════════
#  Shape renderers
# ═══════════════════════════════════════════════════════════════════

def _render_pill(style, text_surf, th, shimmer_phase):
    pad_x, pad_y = _pad_for(text_surf.get_height())
    inner_w = text_surf.get_width()
    inner_h = th
    w = inner_w + pad_x * 2
    h = inner_h + pad_y * 2
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    radius = max(2, h // 2)

    fill = style.get('fill')
    if fill is not None:
        pygame.draw.rect(surf, fill, surf.get_rect(), border_radius=radius)
    else:
        top = style.get('fill_top', (60, 60, 60, 235))
        bot = style.get('fill_bot', (30, 30, 30, 235))
        _vertical_gradient(surf, surf.get_rect(), top, bot)
        # Round-corner clip
        mask = _round_clip_mask(surf.get_size(), radius)
        surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

    # Specular highlight band along top quarter (subtle).
    hl = style.get('highlight_clr')
    if hl is not None:
        band = pygame.Surface((w, max(2, h // 4)), pygame.SRCALPHA)
        pygame.draw.rect(band, hl, band.get_rect(),
                         border_radius=radius)
        # Fade out lower half by blending with transparent.
        fade = pygame.Surface(band.get_size(), pygame.SRCALPHA)
        fade.fill((255, 255, 255, 0))
        for i in range(band.get_height()):
            t = i / max(1, band.get_height() - 1)
            alpha = int(255 * (1 - t))
            pygame.draw.line(fade, (255, 255, 255, alpha),
                             (0, i), (band.get_width(), i))
        band.blit(fade, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surf.blit(band, (0, 0))

    # SKU-specific ornaments (laurel, gems).
    if style.get('laurel_clr'):
        _draw_laurel(surf, style, shimmer_phase)
    if style.get('gem_left') or style.get('gem_right'):
        _draw_gems(surf, style, shimmer_phase)

    border = style.get('border')
    if border:
        pygame.draw.rect(surf, border, surf.get_rect(), 1,
                         border_radius=radius)

    surf.blit(text_surf,
              text_surf.get_rect(center=(w // 2, h // 2)))
    return surf


def _render_scroll(style, text_surf, th, shimmer_phase):
    """Parchment scroll: cream gradient with rolled curls at each end."""
    pad_x, pad_y = _pad_for(text_surf.get_height())
    inner_w = text_surf.get_width()
    inner_h = th
    body_w = inner_w + pad_x * 2
    body_h = inner_h + pad_y * 2
    curl_r = max(4, body_h // 2 - 1)
    extra = curl_r * 2 + 4
    w = body_w + extra
    h = body_h
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    body_x = curl_r + 2
    body_rect = pygame.Rect(body_x, 0, body_w, body_h)

    top = style.get('fill_top', (244, 232, 198, 235))
    bot = style.get('fill_bot', (220, 198, 154, 235))
    _vertical_gradient(surf, body_rect, top, bot)
    # Round-corner clip on body.
    mask = pygame.Surface((body_w, body_h), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255),
                     mask.get_rect(), border_radius=4)
    body_pixels = surf.subsurface(body_rect).copy()
    body_pixels.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    surf.fill((0, 0, 0, 0), body_rect)
    surf.blit(body_pixels, body_rect.topleft)

    # Ink fibers — deterministic short strokes over the parchment.
    fiber = style.get('fiber_clr', (180, 152, 110, 70))
    rng = _lcg(_seed_for(style.get('shape', 'scroll'), inner_w, inner_h))
    for _ in range(8):
        fx = body_rect.x + int(rng() * body_w)
        fy = body_rect.y + int(rng() * body_h)
        flen = int(4 + rng() * 10)
        pygame.draw.line(surf, fiber, (fx, fy), (fx + flen, fy), 1)

    # Curls: filled circle backed by darker rim, attached to each short end.
    curl_clr = style.get('curl_clr', (162, 122, 76))
    curl_inner = (
        min(255, curl_clr[0] + 40),
        min(255, curl_clr[1] + 40),
        min(255, curl_clr[2] + 40),
    )
    for cx, side in ((body_rect.x, -1), (body_rect.right, 1)):
        offset_x = cx + side * (curl_r // 2)
        cy = body_rect.centery
        pygame.draw.circle(surf, curl_clr, (offset_x, cy), curl_r)
        pygame.draw.circle(surf, curl_inner, (offset_x, cy),
                           max(1, curl_r - 2))
        pygame.draw.circle(surf, curl_clr, (offset_x, cy), curl_r, 1)

    border = style.get('border', (122, 92, 56))
    pygame.draw.rect(surf, border, body_rect, 1, border_radius=4)

    surf.blit(text_surf,
              text_surf.get_rect(center=body_rect.center))
    return surf


def _render_plank(style, text_surf, th, shimmer_phase):
    """Iron-banded wooden plank with corner rivets."""
    pad_x, pad_y = _pad_for(text_surf.get_height())
    pad_x = int(pad_x * 1.15)  # extra room for rivets
    w = text_surf.get_width() + pad_x * 2
    h = max(th, text_surf.get_height() + pad_y * 2)
    surf = pygame.Surface((w, h), pygame.SRCALPHA)

    top = style.get('fill_top', (148, 110, 70, 235))
    bot = style.get('fill_bot', (96, 64, 38, 235))
    _vertical_gradient(surf, surf.get_rect(), top, bot)

    # Wood-grain horizontal fibers.
    fiber = style.get('fiber_clr', (60, 36, 18, 90))
    rng = _lcg(_seed_for('plank', w, h))
    for _ in range(5):
        fy = int(rng() * h)
        pygame.draw.line(surf, fiber, (2, fy), (w - 2, fy), 1)

    # Iron border bands (top/bottom 2px) implied by the dark border below.
    border = style.get('border', (28, 22, 18))
    pygame.draw.rect(surf, border, surf.get_rect(), 2, border_radius=2)

    rivet_clr = style.get('rivet_clr', (40, 36, 32))
    rivet_hl = style.get('rivet_highlight', (210, 200, 188))
    inset = max(3, h // 4)
    rivet_r = max(2, h // 8)
    for (rx, ry) in (
        (inset, inset), (w - inset, inset),
        (inset, h - inset), (w - inset, h - inset),
    ):
        pygame.draw.circle(surf, rivet_clr, (rx, ry), rivet_r)
        pygame.draw.circle(surf, rivet_hl, (rx - 1, ry - 1),
                           max(1, rivet_r - 2))
        pygame.draw.circle(surf, (0, 0, 0), (rx, ry), rivet_r, 1)

    surf.blit(text_surf,
              text_surf.get_rect(center=(w // 2, h // 2)))
    return surf


def _render_tablet(style, text_surf, th, shimmer_phase):
    """Stone tablet with chiseled bevel."""
    pad_x, pad_y = _pad_for(text_surf.get_height())
    w = text_surf.get_width() + pad_x * 2
    h = max(th, text_surf.get_height() + pad_y * 2)
    surf = pygame.Surface((w, h), pygame.SRCALPHA)

    top = style.get('fill_top', (188, 188, 192, 235))
    bot = style.get('fill_bot', (132, 130, 134, 235))
    _vertical_gradient(surf, surf.get_rect(), top, bot, border_radius=3)
    # Round-corner clip.
    mask = _round_clip_mask((w, h), 3)
    surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

    hl = style.get('highlight_clr', (224, 224, 226))
    sh = style.get('shadow_clr', (52, 50, 54))
    # Top + left highlight, bottom + right shadow → bevel.
    pygame.draw.line(surf, hl, (1, 1), (w - 2, 1))
    pygame.draw.line(surf, hl, (1, 1), (1, h - 2))
    pygame.draw.line(surf, sh, (1, h - 2), (w - 2, h - 2))
    pygame.draw.line(surf, sh, (w - 2, 1), (w - 2, h - 2))

    # A few chip-nicks for stone texture.
    rng = _lcg(_seed_for('tablet', w))
    for _ in range(4):
        nx = int(rng() * w)
        ny = int(rng() * h)
        pygame.draw.circle(surf, sh, (nx, ny), 1)

    border = style.get('border', (74, 72, 76))
    pygame.draw.rect(surf, border, surf.get_rect(), 1, border_radius=3)

    # Recessed text effect: light highlight 1px down/right, then dark text.
    text_hl = style.get('text_highlight', (236, 236, 238))
    base_clr = style.get('text', (32, 30, 34))
    if base_clr != text_hl:
        text_lower = pygame.Surface(text_surf.get_size(), pygame.SRCALPHA)
        text_lower.blit(text_surf, (0, 0))
        # Pre-rendered text_surf already uses base_clr; for highlight pass
        # we draw a lightened ghost behind it.
        ghost_overlay = pygame.Surface(text_surf.get_size(), pygame.SRCALPHA)
        ghost_overlay.fill((*text_hl[:3], 180))
        ghost = text_surf.copy()
        ghost.blit(ghost_overlay, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surf.blit(ghost,
                  ghost.get_rect(center=(w // 2 + 1, h // 2 + 1)))
    surf.blit(text_surf,
              text_surf.get_rect(center=(w // 2, h // 2)))
    return surf


def _render_swallowtail(style, text_surf, th, shimmer_phase):
    """Banner ribbon with swallowtail notches at each short end."""
    pad_x, pad_y = _pad_for(text_surf.get_height())
    inner_w = text_surf.get_width() + pad_x * 2
    h = max(th, text_surf.get_height() + pad_y * 2)
    notch = max(4, h // 3)
    w = inner_w + notch * 2
    surf = pygame.Surface((w, h), pygame.SRCALPHA)

    top = style.get('fill_top', (188, 52, 60, 240))
    bot = style.get('fill_bot', (124, 28, 36, 240))
    body = pygame.Rect(notch, 0, inner_w, h)
    _vertical_gradient(surf, body, top, bot)

    # Triangle "tails" extending past the body on each side.
    accent = style.get('accent', (250, 220, 138))
    fold = style.get('fold_clr', (96, 22, 28, 110))
    left_tri = [(notch, 0), (0, h // 2), (notch, h)]
    right_tri = [(w - notch, 0), (w, h // 2), (w - notch, h)]
    pygame.draw.polygon(surf, top, left_tri)
    pygame.draw.polygon(surf, bot, right_tri)

    # Vertical fabric fold (subtle column dim down each side).
    fold_band = pygame.Surface((max(2, body.w // 14), body.h), pygame.SRCALPHA)
    fold_band.fill(fold)
    surf.blit(fold_band, (body.x + body.w // 4, body.y))
    surf.blit(fold_band, (body.x + body.w * 3 // 4, body.y))

    # Bottom accent stripe.
    stripe_h = max(1, h // 12)
    pygame.draw.rect(surf, accent,
                     pygame.Rect(body.x, body.bottom - stripe_h,
                                 body.w, stripe_h))

    border = style.get('border', (60, 14, 18))
    # Outline the full silhouette (body + tails).
    silhouette = [
        (notch, 0),
        (w - notch, 0),
        (w, h // 2),
        (w - notch, h),
        (notch, h),
        (0, h // 2),
    ]
    pygame.draw.polygon(surf, border, silhouette, 1)

    surf.blit(text_surf,
              text_surf.get_rect(center=(w // 2, h // 2)))
    return surf


def _render_plaque(style, text_surf, th, shimmer_phase):
    """Marble plaque with serpent heads bracketing the text (epic)."""
    pad_x, pad_y = _pad_for(text_surf.get_height())
    pad_x = int(pad_x * 1.4)
    head_w = max(8, th // 2)
    extra = head_w * 2 + 4
    body_w = text_surf.get_width() + pad_x * 2
    h = max(th, text_surf.get_height() + pad_y * 2)
    w = body_w + extra
    surf = pygame.Surface((w, h), pygame.SRCALPHA)

    body = pygame.Rect(head_w + 2, 0, body_w, h)
    top = style.get('fill_top', (240, 236, 228, 240))
    bot = style.get('fill_bot', (210, 204, 192, 240))
    _vertical_gradient(surf, body, top, bot)
    mask = pygame.Surface(body.size, pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(),
                     border_radius=3)
    body_pixels = surf.subsurface(body).copy()
    body_pixels.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    surf.fill((0, 0, 0, 0), body)
    surf.blit(body_pixels, body.topleft)

    # Marble veins — deterministic per-text jagged thin lines.
    vein = style.get('vein_clr', (118, 108, 132, 180))
    rng = _lcg(_seed_for('plaque', body_w, text_surf.get_width()))
    for _ in range(4):
        sx = body.x + int(rng() * body.w)
        sy = body.y + int(rng() * body.h)
        last = (sx, sy)
        for _ in range(3):
            nx = last[0] + int((rng() - 0.5) * body.w * 0.4)
            ny = last[1] + int((rng() - 0.5) * body.h * 0.6)
            nx = max(body.x, min(body.right - 1, nx))
            ny = max(body.y, min(body.bottom - 1, ny))
            pygame.draw.line(surf, vein, last, (nx, ny), 1)
            last = (nx, ny)

    # Gold scrollwork frame.
    scroll_clr = style.get('scrollwork_clr', (180, 144, 56))
    pygame.draw.rect(surf, scroll_clr, body, 2, border_radius=3)
    # Corner triangles.
    tri = max(3, h // 6)
    for (cx, cy, dx, dy) in (
        (body.x, body.y, 1, 1),
        (body.right - 1, body.y, -1, 1),
        (body.x, body.bottom - 1, 1, -1),
        (body.right - 1, body.bottom - 1, -1, -1),
    ):
        pts = [(cx, cy), (cx + dx * tri, cy), (cx, cy + dy * tri)]
        pygame.draw.polygon(surf, scroll_clr, pts)

    # Serpent heads at each short end.
    serpent = style.get('serpent_clr', (132, 96, 36))
    eye_clr = style.get('serpent_eye', (224, 64, 64))
    eye_r = 1 + (1 if shimmer_phase >= _SHIMMER_PHASES // 2 else 0)
    for (cx, facing) in ((head_w // 2 + 2, 1), (w - head_w // 2 - 2, -1)):
        cy = h // 2
        # teardrop body
        pygame.draw.ellipse(surf, serpent,
                            pygame.Rect(cx - head_w // 2, cy - h // 4,
                                        head_w, h // 2))
        # snout — pointed tip toward the text
        snout = [
            (cx, cy - h // 8),
            (cx + facing * head_w, cy),
            (cx, cy + h // 8),
        ]
        pygame.draw.polygon(surf, serpent, snout)
        # eye
        pygame.draw.circle(surf, eye_clr,
                           (cx, cy - max(1, h // 8)), eye_r)

    border = style.get('border', (124, 96, 36))
    pygame.draw.rect(surf, border, body, 1, border_radius=3)

    surf.blit(text_surf,
              text_surf.get_rect(center=body.center))
    return surf


# ── Ornament helpers (laurel & gems for pill-shaped epics) ────────

def _draw_laurel(surf, style, shimmer_phase):
    w, h = surf.get_size()
    leaf_clr = style.get('laurel_clr', (172, 132, 48))
    leaf_hl = style.get('laurel_highlight', (244, 222, 138))
    leaf_w = max(3, h // 3)
    leaf_h = max(2, h // 5)
    cy = h // 2
    for side in (-1, 1):
        anchor_x = (h // 2 + 2) if side < 0 else (w - h // 2 - 2)
        for i, (dx, dy, angle) in enumerate((
            (-side * 2, -h // 5, -25),
            (-side * 6, -h // 12, -10),
            (-side * 6, h // 12, 10),
            (-side * 2, h // 5, 25),
        )):
            ex = anchor_x + dx
            ey = cy + dy
            leaf_rect = pygame.Rect(0, 0, leaf_w, leaf_h)
            leaf_rect.center = (ex, ey)
            pygame.draw.ellipse(surf, leaf_clr, leaf_rect)
            pygame.draw.ellipse(surf, leaf_hl, leaf_rect, 1)

    # Diagonal shimmer band sweeps across pill.
    if style.get('shimmer'):
        band_alpha = 60
        band = pygame.Surface((w, h), pygame.SRCALPHA)
        band_w = max(4, w // 5)
        # Sweep from -band_w to w over the phase cycle.
        progress = shimmer_phase / max(1, _SHIMMER_PHASES - 1)
        x0 = int(-band_w + progress * (w + band_w))
        pts = [
            (x0, 0),
            (x0 + band_w, 0),
            (x0 + band_w + h, h),
            (x0 + h, h),
        ]
        pygame.draw.polygon(band, (255, 255, 255, band_alpha), pts)
        surf.blit(band, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)


def _draw_gems(surf, style, shimmer_phase):
    w, h = surf.get_size()
    cy = h // 2
    gem_r = max(2, h // 5)
    inset = h // 2 + 2
    pulse = math.sin(shimmer_phase / max(1, _SHIMMER_PHASES) * math.tau)
    glow_alpha = max(0, int(80 + pulse * 60))
    for (cx, gem_clr_key, glow_key) in (
        (inset, 'gem_left', 'gem_glow_left'),
        (w - inset, 'gem_right', 'gem_glow_right'),
    ):
        gem_clr = style.get(gem_clr_key, (224, 46, 70))
        glow_clr = style.get(glow_key, (255, 96, 120, 0))
        if style.get('shimmer') and glow_alpha > 0:
            glow = pygame.Surface((gem_r * 6, gem_r * 6), pygame.SRCALPHA)
            pygame.draw.circle(glow,
                               (glow_clr[0], glow_clr[1], glow_clr[2],
                                glow_alpha),
                               (gem_r * 3, gem_r * 3), gem_r * 3)
            surf.blit(glow, (cx - gem_r * 3, cy - gem_r * 3),
                      special_flags=pygame.BLEND_RGBA_ADD)
        pygame.draw.circle(surf, (0, 0, 0), (cx, cy), gem_r + 1)
        pygame.draw.circle(surf, gem_clr, (cx, cy), gem_r)
        pygame.draw.circle(surf, (255, 255, 255, 220),
                           (cx - max(1, gem_r // 2),
                            cy - max(1, gem_r // 2)),
                           max(1, gem_r // 3))


# ── Renderer registry ─────────────────────────────────────────────

_SHAPE_RENDERERS = {
    'pill':        _render_pill,
    'scroll':      _render_scroll,
    'plank':       _render_plank,
    'tablet':      _render_tablet,
    'swallowtail': _render_swallowtail,
    'plaque':      _render_plaque,
}
