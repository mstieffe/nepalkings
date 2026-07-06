# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Reusable visual effects layer for the conquer battle screen.

The conquer screen relies almost entirely on text + static badges to
communicate spell casts, round transitions, and damage / heal events.
This module adds a lightweight, self-contained animation layer that
draws on top of the existing render stack each frame.

Design goals
------------
* **Additive only** — primitives are stateless animation records driven
  by ``pygame.time.get_ticks()``; nothing here mutates game state.
* **No external deps** — uses only ``pygame`` primitives + helpers from
  ``config.settings``.
* **Fail-soft** — every animation tolerates missing rects / assets so a
  surprise asset gap never crashes the conquer screen.

Public surface
--------------
``ConquerEffectsLayer`` is the single entry point.  ``ConquerGameScreen``
owns one instance, calls :meth:`spawn_*` from event hooks, and calls
:meth:`draw` once per frame near the end of its own ``draw()``.  The
layer also exposes :meth:`screen_shake_offset` so the parent can apply
a small drawing offset to make destructive events feel impactful.

Each primitive returns a token (sequence id) that callers may discard.
"""
from __future__ import annotations

import math
import random
from typing import Any, Callable, Dict, List, Optional, Tuple

import pygame

from config import settings


# ---------------------------------------------------------------------------
# Easing helpers
# ---------------------------------------------------------------------------

def _clamp01(x: float) -> float:
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def ease_out_quad(t: float) -> float:
    t = _clamp01(t)
    return 1.0 - (1.0 - t) * (1.0 - t)


def ease_in_quad(t: float) -> float:
    t = _clamp01(t)
    return t * t


def ease_in_out(t: float) -> float:
    t = _clamp01(t)
    return t * t * (3.0 - 2.0 * t)


# ---------------------------------------------------------------------------
# Visual style presets per spell
# ---------------------------------------------------------------------------

#: Maps spell name -> (primary_color, secondary_color, icon_label)
SPELL_VISUAL_PRESETS: Dict[str, Tuple[Tuple[int, int, int], Tuple[int, int, int], str]] = {
    'Poison':       ((148, 76, 196), (96, 200, 132), 'P'),
    'Health Boost': ((110, 220, 140), (255, 240, 180), '+'),
    'Explosion':    ((255, 168, 56),  (255, 240, 200), '!'),
    'Draw 2 MainCards': ((80, 185, 230), (220, 245, 255), '2'),
    'Draw 2 SideCards': ((80, 185, 230), (220, 245, 255), '2'),
    'Draw 4 MainCards': ((80, 185, 230), (220, 245, 255), '4'),
    'Fill up to 10': ((80, 185, 230), (220, 245, 255), '10'),
    'Dump Cards': ((230, 140, 78), (255, 225, 170), 'R'),
    'Forced Deal': ((225, 188, 88), (255, 245, 190), 'S'),
    'Peasant War': ((214, 178, 92), (255, 230, 160), 'P'),
    'Civil War': ((214, 118, 108), (255, 215, 190), 'C'),
    'Blitzkrieg': ((255, 196, 86), (255, 245, 190), 'B'),
    'Invader Swap': ((196, 160, 250), (240, 230, 255), 'I'),
    'All Seeing Eye': ((130, 190, 255), (230, 244, 255), 'O'),
    'Royal Decree': ((250, 208, 80), (255, 245, 200), 'K'),
    'Copy Figure': ((120, 210, 220), (225, 250, 250), 'C'),
    'Landslide': ((176, 128, 84), (230, 205, 170), 'L'),
}


def spell_preset(spell_name: str) -> Tuple[Tuple[int, int, int], Tuple[int, int, int], str]:
    """Return (primary, secondary, label) for the named spell or a default."""
    return SPELL_VISUAL_PRESETS.get(
        spell_name,
        ((200, 200, 220), (240, 240, 250), '?'),
    )


# ---------------------------------------------------------------------------
# ConquerEffectsLayer
# ---------------------------------------------------------------------------

class ConquerEffectsLayer:
    """Owns and renders transient conquer animations.

    Parameters
    ----------
    window : pygame.Surface
        Target surface (typically the main screen).
    rect_lookup : callable
        ``(figure_id) -> Optional[pygame.Rect]``.  Returns the on-screen
        rect of the figure or ``None`` if it is not currently rendered.
        ``ConquerGameScreen`` provides this by combining its duel-lane
        rect cache with the field-screen figure icons.
    """

    PROJECTILE_MS = 420
    IMPACT_MS = 520
    SHAKE_MS = 120
    SHAKE_AMPLITUDE = 4  # px
    FLOATING_TEXT_MS = 720
    BANNER_MS = 900
    COPY_MS = 1500

    def __init__(self, window: pygame.Surface, rect_lookup: Callable[[Any], Optional[pygame.Rect]]):
        self.window = window
        self.rect_lookup = rect_lookup
        self._projectiles: List[Dict[str, Any]] = []
        self._impacts: List[Dict[str, Any]] = []
        self._particles: List[Dict[str, Any]] = []
        self._shakes: List[Dict[str, Any]] = []
        self._floats: List[Dict[str, Any]] = []
        self._banners: List[Dict[str, Any]] = []
        self._copies: List[Dict[str, Any]] = []
        self._next_token = 1

    # ------------------------------------------------------------------ util
    def _ms(self) -> int:
        return pygame.time.get_ticks()

    def _new_token(self) -> int:
        token = self._next_token
        self._next_token += 1
        return token

    def _resolve_target(self, target_figure_id: Any) -> Optional[pygame.Rect]:
        if target_figure_id is None:
            return None
        try:
            rect = self.rect_lookup(target_figure_id)
        except Exception:
            return None
        if rect is None:
            return None
        return pygame.Rect(rect)

    @staticmethod
    def _resolve_static_rect(rect: Any) -> Optional[pygame.Rect]:
        if rect is None:
            return None
        try:
            return pygame.Rect(rect)
        except Exception:
            return None

    def _projectile_target_rect(self, projectile: Dict[str, Any]) -> Optional[pygame.Rect]:
        rect = self._resolve_static_rect(projectile.get('target_rect'))
        if rect is not None:
            return rect
        return self._resolve_target(projectile.get('target_id'))

    def _effect_target_rect(self, effect: Dict[str, Any]) -> Optional[pygame.Rect]:
        rect = self._resolve_static_rect(effect.get('target_rect'))
        if rect is not None:
            return rect
        return self._resolve_target(effect.get('target_id'))

    def clear(self) -> None:
        """Drop all active animations (e.g. on screen leave / game change)."""
        self._projectiles.clear()
        self._impacts.clear()
        self._particles.clear()
        self._shakes.clear()
        self._floats.clear()
        self._banners.clear()
        self._copies.clear()

    # ----------------------------------------------------------------- spawn
    def spawn_spell_cast(self, spell_name: str, source_rect: Optional[pygame.Rect],
                         target_figure_id: Any,
                         *,
                         floating_text: Optional[str] = None,
                         extra_targets: Optional[List[Any]] = None) -> int:
        """Trigger a projectile + impact sequence for the named spell.

        ``source_rect`` may be ``None`` — in that case a sensible default is
        chosen (top-centre of the window) so the cast still draws something.
        ``extra_targets`` (optional) spawns lighter impact pulses on
        additional figures (e.g. multi-target buffs).
        """
        primary, secondary, label = spell_preset(spell_name)
        target_rect = self._resolve_target(target_figure_id)
        if target_rect is None and not extra_targets:
            # Nothing to anchor to — still flash a banner so the user sees something.
            self.spawn_banner(f'{spell_name} cast', primary, duration_ms=self.BANNER_MS)
            return 0
        # Pick a sensible source if missing.
        if source_rect is None:
            w = self.window.get_width()
            source_rect = pygame.Rect(w // 2 - 24, 8, 48, 36)
        token = self._new_token()
        now = self._ms()
        # Primary projectile.
        if target_rect is not None:
            self._projectiles.append({
                'token': token,
                'spell': spell_name,
                'label': label,
                'primary': primary,
                'secondary': secondary,
                'source': pygame.Rect(source_rect),
                'target_id': target_figure_id,
                'started_at': now,
                'duration': self.PROJECTILE_MS,
            })
        # Extra weaker pulses on supplementary targets — no projectile, just glow.
        for extra in extra_targets or []:
            extra_rect = self._resolve_target(extra)
            if extra_rect is None:
                continue
            self._impacts.append({
                'token': token,
                'spell': spell_name,
                'primary': primary,
                'secondary': secondary,
                'target_id': extra,
                'started_at': now + 80,
                'duration': int(self.IMPACT_MS * 0.7),
                'scale': 0.7,
            })
        if floating_text and target_rect is not None:
            self._floats.append({
                'text': floating_text,
                'color': primary,
                'target_id': target_figure_id,
                'started_at': now + self.PROJECTILE_MS - 60,
                'duration': self.FLOATING_TEXT_MS,
            })
        return token

    def spawn_spell_to_rect(self, spell_name: str,
                            source_rect: Optional[pygame.Rect],
                            target_rect: Optional[pygame.Rect],
                            *,
                            floating_text: Optional[str] = None) -> int:
        """Trigger a spell glyph flying to a fixed UI rectangle."""
        target_rect = self._resolve_static_rect(target_rect)
        primary, secondary, label = spell_preset(spell_name)
        if target_rect is None:
            self.spawn_banner(f'{spell_name} cast', primary, duration_ms=self.BANNER_MS)
            return 0
        if source_rect is None:
            w = self.window.get_width()
            source_rect = pygame.Rect(w // 2 - 24, 8, 48, 36)
        token = self._new_token()
        now = self._ms()
        self._projectiles.append({
            'token': token,
            'spell': spell_name,
            'label': label,
            'primary': primary,
            'secondary': secondary,
            'source': pygame.Rect(source_rect),
            'target_id': None,
            'target_rect': pygame.Rect(target_rect),
            'started_at': now,
            'duration': self.PROJECTILE_MS,
        })
        if floating_text:
            self._floats.append({
                'text': floating_text,
                'color': primary,
                'target_id': None,
                'target_rect': pygame.Rect(target_rect),
                'started_at': now + self.PROJECTILE_MS - 60,
                'duration': self.FLOATING_TEXT_MS,
            })
        return token

    def spawn_rect_pulse(self, target_rect: Optional[pygame.Rect],
                         color: Tuple[int, int, int],
                         *,
                         secondary: Optional[Tuple[int, int, int]] = None,
                         duration_ms: Optional[int] = None,
                         delay_ms: int = 0,
                         scale: float = 1.0) -> int:
        """Draw the same radial impact pulse around a fixed UI rectangle."""
        target_rect = self._resolve_static_rect(target_rect)
        token = self._new_token()
        if target_rect is None:
            return token
        self._impacts.append({
            'token': token,
            'spell': '',
            'primary': color,
            'secondary': secondary or color,
            'target_id': None,
            'target_rect': pygame.Rect(target_rect),
            'started_at': self._ms() + max(0, int(delay_ms)),
            'duration': int(duration_ms or self.IMPACT_MS),
            'scale': float(scale or 1.0),
        })
        return token

    def spawn_explosion(self, source_rect: Optional[pygame.Rect],
                        target_figure_id: Any) -> int:
        """Convenience: explosion with screen shake + particle burst."""
        token = self.spawn_spell_cast('Explosion', source_rect, target_figure_id)
        # On-impact: schedule shake + sparkle particle burst at target.
        target_rect = self._resolve_target(target_figure_id)
        if target_rect is None:
            return token
        now = self._ms()
        impact_at = now + self.PROJECTILE_MS
        self._shakes.append({
            'started_at': impact_at,
            'duration': self.SHAKE_MS,
            'amplitude': self.SHAKE_AMPLITUDE,
        })
        # Particle burst (radial sparks).
        cx, cy = target_rect.center
        rng = random.Random(token * 9973 + target_rect.x)
        primary, secondary, _ = spell_preset('Explosion')
        for _ in range(18):
            angle = rng.uniform(0, math.tau)
            speed = rng.uniform(110, 220)  # px/sec
            self._particles.append({
                'x': float(cx),
                'y': float(cy),
                'vx': math.cos(angle) * speed,
                'vy': math.sin(angle) * speed,
                'started_at': impact_at,
                'duration': rng.randint(360, 560),
                'radius': rng.randint(2, 4),
                'color': primary if rng.random() < 0.6 else secondary,
            })
        return token

    def spawn_impact(self, target_figure_id: Any, color: Tuple[int, int, int], *,
                     duration_ms: Optional[int] = None) -> int:
        token = self._new_token()
        target_rect = self._resolve_target(target_figure_id)
        if target_rect is None:
            return token
        self._impacts.append({
            'token': token,
            'spell': '',
            'primary': color,
            'secondary': color,
            'target_id': target_figure_id,
            'started_at': self._ms(),
            'duration': int(duration_ms or self.IMPACT_MS),
            'scale': 1.0,
        })
        return token

    def spawn_floating_text(self, target_figure_id: Any, text: str,
                            color: Tuple[int, int, int] = (240, 230, 200),
                            *, delay_ms: int = 0,
                            duration_ms: Optional[int] = None) -> int:
        token = self._new_token()
        self._floats.append({
            'text': str(text),
            'color': color,
            'target_id': target_figure_id,
            'started_at': self._ms() + max(0, int(delay_ms)),
            'duration': int(duration_ms or self.FLOATING_TEXT_MS),
        })
        return token

    def spawn_floating_text_at_rect(self, target_rect: Optional[pygame.Rect],
                                    text: str,
                                    color: Tuple[int, int, int] = (240, 230, 200),
                                    *, delay_ms: int = 0,
                                    duration_ms: Optional[int] = None) -> int:
        """Floating text anchored to a fixed UI rectangle (not a figure)."""
        token = self._new_token()
        target_rect = self._resolve_static_rect(target_rect)
        if target_rect is None:
            return token
        self._floats.append({
            'text': str(text),
            'color': color,
            'target_id': None,
            'target_rect': pygame.Rect(target_rect),
            'started_at': self._ms() + max(0, int(delay_ms)),
            'duration': int(duration_ms or self.FLOATING_TEXT_MS),
        })
        return token

    def spawn_banner(self, text: str, color: Tuple[int, int, int],
                     *, duration_ms: Optional[int] = None,
                     anchor_rect: Optional[pygame.Rect] = None) -> int:
        token = self._new_token()
        self._banners.append({
            'text': str(text),
            'color': color,
            'started_at': self._ms(),
            'duration': int(duration_ms or self.BANNER_MS),
            'anchor': pygame.Rect(anchor_rect) if anchor_rect else None,
        })
        return token

    def spawn_shake(self, *, amplitude: Optional[int] = None,
                    duration_ms: Optional[int] = None) -> None:
        self._shakes.append({
            'started_at': self._ms(),
            'duration': int(duration_ms or self.SHAKE_MS),
            'amplitude': int(amplitude or self.SHAKE_AMPLITUDE),
        })

    def spawn_copy_ghost(self, source_rect: Optional[pygame.Rect],
                         target_rect: Optional[pygame.Rect],
                         *,
                         color: Tuple[int, int, int] = (120, 210, 235),
                         secondary: Tuple[int, int, int] = (225, 250, 255),
                         duration_ms: Optional[int] = None) -> int:
        """Copy Figure: a cluster of ghost orbs spins around the source, then
        spirals onto the copied figure and lands with an impact pulse.

        One-shot (``duration_ms`` total) — recreates the lively spinning look
        of the old animation without the per-frame re-fire that stalled it.
        """
        source_rect = self._resolve_static_rect(source_rect)
        target_rect = self._resolve_static_rect(target_rect)
        if source_rect is None:
            w = self.window.get_width()
            source_rect = pygame.Rect(w // 2 - 20, 24, 40, 40)
        if target_rect is None:
            target_rect = pygame.Rect(source_rect)
        token = self._new_token()
        self._copies.append({
            'token': token,
            'source': pygame.Rect(source_rect),
            'target': pygame.Rect(target_rect),
            'primary': color,
            'secondary': secondary,
            'started_at': self._ms(),
            'duration': int(duration_ms or self.COPY_MS),
            'landed': False,
        })
        return token

    # ---------------------------------------------------------------- queries
    def screen_shake_offset(self) -> Tuple[int, int]:
        """Return current frame's (dx, dy) shake offset.

        The conquer screen applies this post-composition at the end of
        ``render()`` (a whole-frame scroll), so every active shake moves
        the full scene as one camera jolt.
        """
        now = self._ms()
        dx = dy = 0
        for s in self._shakes:
            start = int(s.get('started_at') or 0)
            dur = max(1, int(s.get('duration') or self.SHAKE_MS))
            if now < start or now > start + dur:
                continue
            t = (now - start) / dur
            falloff = 1.0 - t
            amp = max(1, int(s.get('amplitude') or self.SHAKE_AMPLITUDE)) * falloff
            # Pseudo-random oscillation using two sines at different freqs.
            phase = (now - start) * 0.05
            dx += int(math.sin(phase * 4.0 + s.get('started_at', 0)) * amp)
            dy += int(math.cos(phase * 3.3 + s.get('started_at', 0)) * amp)
        return dx, dy

    # ------------------------------------------------------------------ draw
    def draw(self) -> None:
        now = self._ms()
        self._draw_projectiles(now)
        self._draw_copies(now)
        self._draw_impacts(now)
        self._draw_particles(now)
        self._draw_floating_texts(now)
        self._draw_banners(now)
        self._prune(now)

    # ---- projectiles -------------------------------------------------------
    def _draw_projectiles(self, now: int) -> None:
        finished: List[Dict[str, Any]] = []
        for p in self._projectiles:
            start = int(p['started_at'])
            dur = max(1, int(p['duration']))
            t = (now - start) / dur
            if t < 0:
                continue
            target_rect = self._projectile_target_rect(p)
            if target_rect is None:
                finished.append(p)
                continue
            if t >= 1.0:
                # Spawn the impact glow at target + queue completion.
                self._impacts.append({
                    'token': p['token'],
                    'spell': p['spell'],
                    'primary': p['primary'],
                    'secondary': p['secondary'],
                    'target_id': p['target_id'],
                    'target_rect': pygame.Rect(target_rect) if p.get('target_rect') is not None else None,
                    'started_at': now,
                    'duration': self.IMPACT_MS,
                    'scale': 1.0,
                })
                finished.append(p)
                continue
            eased = ease_in_out(t)
            source = p['source']
            cx = int(source.centerx + (target_rect.centerx - source.centerx) * eased)
            cy = int(source.centery + (target_rect.centery - source.centery) * eased)
            # Slight arc.
            arc = math.sin(eased * math.pi) * 24.0
            cy = int(cy - arc)
            self._draw_projectile_glyph(cx, cy, p, t)
        for p in finished:
            try:
                self._projectiles.remove(p)
            except ValueError:
                pass

    def _draw_projectile_glyph(self, cx: int, cy: int, p: Dict[str, Any], t: float) -> None:
        primary = p['primary']
        secondary = p['secondary']
        label = p['label']
        # Trail (older positions, fading).
        source = p['source']
        target_rect = self._projectile_target_rect(p)
        if target_rect is None:
            return
        for k in range(1, 5):
            t2 = max(0.0, t - 0.04 * k)
            eased2 = ease_in_out(t2)
            tx = int(source.centerx + (target_rect.centerx - source.centerx) * eased2)
            ty = int(source.centery + (target_rect.centery - source.centery) * eased2)
            arc2 = math.sin(eased2 * math.pi) * 24.0
            ty = int(ty - arc2)
            alpha = max(0, 130 - k * 28)
            r = 10 - k
            if r <= 0 or alpha <= 0:
                continue
            surf = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            pygame.draw.circle(surf, (*primary, alpha), (r, r), r)
            self.window.blit(surf, (tx - r, ty - r))
        # Main glyph: filled circle + ring + label.
        size = 26
        surf = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
        # Outer halo
        pygame.draw.circle(surf, (*secondary, 80), (size, size), size)
        # Body
        pygame.draw.circle(surf, (*primary, 240), (size, size), 14)
        # Ring
        pygame.draw.circle(surf, (255, 255, 255, 220), (size, size), 14, 2)
        # Label
        try:
            font = settings.get_font(max(11, int(settings.FS_TINY * 0.95)), bold=True)
            text_surf = font.render(label, True, (255, 255, 255))
            surf.blit(text_surf, text_surf.get_rect(center=(size, size)))
        except Exception:
            pass
        self.window.blit(surf, (cx - size, cy - size))

    # ---- copy ghosts (spinning duplication) -------------------------------
    def _draw_copy_orb(self, cx: float, cy: float, r: int,
                       color: Tuple[int, int, int],
                       ring: Tuple[int, int, int], alpha: int) -> None:
        if r <= 0 or alpha <= 0:
            return
        pad = r * 3
        surf = pygame.Surface((pad * 2, pad * 2), pygame.SRCALPHA)
        c = (pad, pad)
        pygame.draw.circle(surf, (*ring, max(0, alpha // 3)), c, r * 2)   # halo
        pygame.draw.circle(surf, (*color, alpha), c, r)                    # body
        pygame.draw.circle(surf, (255, 255, 255, min(255, alpha + 40)),
                           c, r, max(1, r // 3))                           # rim
        self.window.blit(surf, (int(cx) - pad, int(cy) - pad),
                         special_flags=pygame.BLEND_RGBA_ADD)

    def _draw_copies(self, now: int) -> None:
        finished: List[Dict[str, Any]] = []
        for c in self._copies:
            start = int(c['started_at'])
            dur = max(1, int(c['duration']))
            t = (now - start) / dur
            if t < 0:
                continue
            if t >= 1.0:
                # Landing impact pulse on the copied figure.
                self._impacts.append({
                    'token': c['token'],
                    'spell': 'Copy Figure',
                    'primary': c['primary'],
                    'secondary': c['secondary'],
                    'target_id': None,
                    'target_rect': pygame.Rect(c['target']),
                    'started_at': now,
                    'duration': self.IMPACT_MS,
                    'scale': 1.05,
                })
                finished.append(c)
                continue

            src = c['source']
            tgt = c['target']
            primary = c['primary']
            secondary = c['secondary']
            # The orbit centre travels source → target, arriving by ~88%.
            travel = ease_in_out(min(1.0, t / 0.88))
            cx = src.centerx + (tgt.centerx - src.centerx) * travel
            cy = src.centery + (tgt.centery - src.centery) * travel
            cy -= math.sin(travel * math.pi) * 34.0  # gentle arc
            # Orbit radius blooms early then collapses onto the target.
            base_r = max(18.0, max(src.width, src.height) * 0.62)
            radius = base_r * (0.35 + 0.65 * math.sin(min(1.0, t / 0.9) * math.pi)) \
                * (1.0 - 0.55 * travel) + 4.0
            spin = t * math.tau * 3.2  # ~3 revolutions over the flight
            orbs = 3
            for i in range(orbs):
                ang = spin + i * (math.tau / orbs)
                ox = cx + math.cos(ang) * radius
                oy = cy + math.sin(ang) * radius * 0.6  # squash → 3D orbit feel
                orb_r = int(5 + 6 * travel)
                depth = 0.5 + 0.5 * math.sin(ang)  # front orbs brighter
                alpha = int((150 + 90 * depth) * min(1.0, (1.0 - t) * 3.0 + 0.4))
                self._draw_copy_orb(ox, oy, orb_r, primary, secondary, alpha)
            # Bright convergence core.
            core_alpha = int(230 * min(1.0, (1.0 - t) * 3.0 + 0.35))
            self._draw_copy_orb(cx, cy, int(4 + 5 * travel),
                                secondary, primary, core_alpha)
        for c in finished:
            try:
                self._copies.remove(c)
            except ValueError:
                pass

    # ---- impacts (radial pulses) ------------------------------------------
    def _draw_impacts(self, now: int) -> None:
        finished: List[Dict[str, Any]] = []
        for im in self._impacts:
            start = int(im['started_at'])
            dur = max(1, int(im['duration']))
            t = (now - start) / dur
            if t < 0:
                continue
            if t >= 1.0:
                finished.append(im)
                continue
            target_rect = self._effect_target_rect(im)
            if target_rect is None:
                finished.append(im)
                continue
            cx, cy = target_rect.center
            base_r = max(target_rect.width, target_rect.height) // 2
            scale = float(im.get('scale') or 1.0)
            eased = ease_out_quad(t)
            # Three concentric rings expanding outward.
            for i, ring_scale in enumerate((0.9, 1.25, 1.7)):
                r = int(base_r * ring_scale * (0.85 + 0.55 * eased) * scale)
                alpha = max(0, int(220 * (1.0 - t) * (1.0 - 0.18 * i)))
                if r <= 0 or alpha <= 0:
                    continue
                surf = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
                color = im['primary'] if i % 2 == 0 else im['secondary']
                width = max(2, 5 - i)
                pygame.draw.circle(surf, (*color, alpha), (r + 2, r + 2), r, width)
                self.window.blit(surf, (cx - r - 2, cy - r - 2))
            # Inner soft glow.
            r_glow = int(base_r * (0.6 + 0.2 * eased) * scale)
            if r_glow > 0:
                alpha = max(0, int(120 * (1.0 - t)))
                glow = pygame.Surface((r_glow * 2, r_glow * 2), pygame.SRCALPHA)
                pygame.draw.circle(glow, (*im['primary'], alpha), (r_glow, r_glow), r_glow)
                self.window.blit(glow, (cx - r_glow, cy - r_glow), special_flags=pygame.BLEND_RGBA_ADD)
        for im in finished:
            try:
                self._impacts.remove(im)
            except ValueError:
                pass

    # ---- particles --------------------------------------------------------
    def _draw_particles(self, now: int) -> None:
        finished: List[Dict[str, Any]] = []
        for pt in self._particles:
            start = int(pt['started_at'])
            dur = max(1, int(pt['duration']))
            t = (now - start) / dur
            if t < 0:
                continue
            if t >= 1.0:
                finished.append(pt)
                continue
            dt = (now - start) / 1000.0
            # Apply gravity-ish slow-down.
            x = pt['x'] + pt['vx'] * dt
            y = pt['y'] + pt['vy'] * dt + 60.0 * dt * dt  # mild gravity
            alpha = max(0, int(255 * (1.0 - t)))
            r = max(1, int(pt['radius']))
            if alpha <= 0:
                continue
            surf = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
            color = pt['color']
            pygame.draw.circle(surf, (*color, alpha), (r + 1, r + 1), r)
            self.window.blit(surf, (int(x) - r, int(y) - r))
        for pt in finished:
            try:
                self._particles.remove(pt)
            except ValueError:
                pass

    # ---- floating texts ---------------------------------------------------
    def _draw_floating_texts(self, now: int) -> None:
        finished: List[Dict[str, Any]] = []
        for f in self._floats:
            start = int(f['started_at'])
            dur = max(1, int(f['duration']))
            t = (now - start) / dur
            if t < 0:
                continue
            if t >= 1.0:
                finished.append(f)
                continue
            target_rect = self._effect_target_rect(f)
            if target_rect is None:
                finished.append(f)
                continue
            try:
                font = settings.get_font(max(12, int(settings.FS_SMALL * 1.05)), bold=True)
            except Exception:
                continue
            text_surf = font.render(f['text'], True, f['color'])
            text_surf.set_alpha(max(0, int(255 * (1.0 - t * t))))
            cx, cy = target_rect.center
            rise = int(36 * ease_out_quad(t))
            self.window.blit(
                text_surf,
                text_surf.get_rect(center=(cx, target_rect.top - 6 - rise)),
            )
        for f in finished:
            try:
                self._floats.remove(f)
            except ValueError:
                pass

    # ---- banners ----------------------------------------------------------
    def _draw_banners(self, now: int) -> None:
        finished: List[Dict[str, Any]] = []
        for b in self._banners:
            start = int(b['started_at'])
            dur = max(1, int(b['duration']))
            t = (now - start) / dur
            if t < 0:
                continue
            if t >= 1.0:
                finished.append(b)
                continue
            try:
                font = settings.get_font(int(settings.FS_HEADING * 1.3), bold=True)
            except Exception:
                continue
            text = b['text']
            color = b['color']
            # Alpha: fast fade-in, hold, fade-out.
            if t < 0.18:
                alpha = int(255 * (t / 0.18))
            elif t > 0.72:
                alpha = int(255 * (1.0 - (t - 0.72) / 0.28))
            else:
                alpha = 255
            # Scale: tiny zoom-in.
            scale = 0.85 + 0.15 * ease_out_quad(min(1.0, t / 0.4))
            text_surf = font.render(text, True, color)
            if scale != 1.0:
                w = max(1, int(text_surf.get_width() * scale))
                h = max(1, int(text_surf.get_height() * scale))
                try:
                    text_surf = pygame.transform.smoothscale(text_surf, (w, h))
                except Exception:
                    pass
            text_surf.set_alpha(max(0, min(255, alpha)))
            anchor = b.get('anchor')
            if anchor is not None:
                center = anchor.center
            else:
                center = (self.window.get_width() // 2,
                          int(self.window.get_height() * 0.34))
            # Backing pill for legibility.
            pad_x, pad_y = 22, 10
            pill = pygame.Rect(0, 0,
                               text_surf.get_width() + pad_x * 2,
                               text_surf.get_height() + pad_y * 2)
            pill.center = center
            bg = pygame.Surface(pill.size, pygame.SRCALPHA)
            bg.fill((18, 14, 10, max(0, min(220, alpha - 30))))
            self.window.blit(bg, pill.topleft)
            pygame.draw.rect(self.window, (*color, max(0, min(220, alpha))),
                             pill, 2, border_radius=pill.height // 2)
            self.window.blit(text_surf, text_surf.get_rect(center=pill.center))
        for b in finished:
            try:
                self._banners.remove(b)
            except ValueError:
                pass

    # ---- cleanup ----------------------------------------------------------
    def _prune(self, now: int) -> None:
        self._shakes = [s for s in self._shakes
                        if now <= int(s.get('started_at') or 0) + int(s.get('duration') or 0)]
