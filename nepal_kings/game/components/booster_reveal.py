# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Booster pack reveal overlay — face-down cards with tier reveal polish."""

import math

import pygame
from config import settings
from game.components.cards.card_img import CardImg

_SW, _SH = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT
# True on mobile web, where the canvas is CSS-downscaled and text/buttons sized
# off the raw screen height end up too small to read or tap.
_IS_MOBILE = getattr(settings, 'TOUCH_TARGET_MIN', 0) > 0

# Card dimensions for the reveal overlay
_CARD_W = int(0.10 * _SW)
_CARD_H = int(0.25 * _SH)
_CARD_GAP = int(0.04 * _SW)
_SCALE_HOVER = 1.15

# Glow dimensions
_GLOW_W = int(_CARD_W * 1.85)
_GLOW_H = int(_CARD_H * 1.55)
_CARDS_PER_PACK = 3
_REVEAL_ALL_STAGGER_MS = 95
_UNCOMMON_CELEBRATION_MS = 760
_RARE_CELEBRATION_MS = 1120

# Close / nav buttons. On mobile they are widened and given a touch-friendly
# height floor so the labels stay readable and tappable after CSS downscaling.
_CLOSE_W = int((0.20 if _IS_MOBILE else 0.12) * _SW)
_CLOSE_H = max(int(0.05 * _SH), getattr(settings, 'TOUCH_TARGET_MIN', 0))
_NAV_W = int((0.15 if _IS_MOBILE else 0.095) * _SW)

_RAW_IMAGE_CACHE = {}
_SCALED_IMAGE_CACHE = {}
_CARD_FRONT_CACHE = {}
_TIER_GLOW_CACHE = {}


def _load_raw_image(path):
    if path not in _RAW_IMAGE_CACHE:
        _RAW_IMAGE_CACHE[path] = pygame.image.load(path).convert_alpha()
    return _RAW_IMAGE_CACHE[path]


def _load_scaled_image(path, size):
    key = (path, size)
    if key not in _SCALED_IMAGE_CACHE:
        _SCALED_IMAGE_CACHE[key] = pygame.transform.smoothscale(
            _load_raw_image(path), size)
    return _SCALED_IMAGE_CACHE[key]


def _card_front_image(window, suit, rank, size):
    key = (suit, rank, size)
    if key not in _CARD_FRONT_CACHE:
        _CARD_FRONT_CACHE[key] = CardImg(window, suit, rank, size[0], size[1]).front_img
    return _CARD_FRONT_CACHE[key]


def _tier_glow_image(tier, base_glow):
    key = (tier, base_glow.get_size())
    if key not in _TIER_GLOW_CACHE:
        glow = base_glow.copy()
        glow.fill(settings.COLLECTION_TIER_GLOW_TINTS[tier],
                  special_flags=pygame.BLEND_RGBA_MULT)
        _TIER_GLOW_CACHE[key] = glow
    return _TIER_GLOW_CACHE[key]


def _card_tier(card, pack_type='main'):
    """Return the booster tier for a drawn card, falling back to rank inference."""
    try:
        tier = int(card.get('tier', 0))
        if tier in settings.COLLECTION_TIER_LABELS:
            return tier
    except (TypeError, ValueError, AttributeError):
        pass

    rank = card.get('rank') if isinstance(card, dict) else None
    if pack_type == 'side':
        return settings.COLLECTION_SIDE_RANK_TO_TIER.get(rank, 1)
    if pack_type == 'main':
        return settings.COLLECTION_MAIN_RANK_TO_TIER.get(rank, 1)
    return (settings.COLLECTION_MAIN_RANK_TO_TIER.get(rank)
            or settings.COLLECTION_SIDE_RANK_TO_TIER.get(rank)
            or 1)


def _impact_badge_label(card):
    """Only genuinely new card types need a reveal badge."""
    if not isinstance(card, dict) or '_impact_owned_after' not in card:
        return ''
    return 'NEW' if card.get('_impact_new_type') else ''


class BoosterRevealOverlay:
    """Full-screen overlay showing face-down booster cards.

    Each card starts face-down with its rarity glow visible. The user clicks
    cards to reveal them. Once all cards are revealed a Close button appears.
    """

    def __init__(self, window, drawn_cards, pack_type='main', title=None):
        """
        Args:
            window: pygame display surface
            drawn_cards: list of dicts [{suit, rank, value, tier}, ...]
            pack_type: 'main' or 'side', used to infer tiers for legacy responses
            title: optional header override for non-pack reveals (e.g. crafts);
                defaults to the pack-type label
        """
        self.window = window
        self._cards = list(drawn_cards or [])
        self._pack_type = pack_type
        self._title_override = title
        self._tiers = [_card_tier(c, pack_type) for c in self._cards]

        # State per card slot: 'hidden' | 'revealing' | 'revealed'
        self._states = ['hidden'] * len(self._cards)
        self._reveal_started_at = [None] * len(self._cards)

        # Dim overlay
        self._overlay = pygame.Surface((_SW, _SH), pygame.SRCALPHA)
        self._overlay.fill((0, 0, 0, 180))

        # Title / label fonts. Sized off the shared FS_* groups (which inflate on
        # mobile) rather than raw screen height, so text stays legible on phones.
        self._title_font = settings.get_font(settings.FS_SUBTITLE, bold=True)
        self._subtitle_font = settings.get_font(settings.FS_SMALL)
        self._close_font = settings.get_font(settings.FS_BUTTON)
        self._label_font = settings.get_font(settings.FS_SMALL)
        self._impact_font = settings.get_font(settings.FS_TINY, bold=True)

        self._bulk = len(self._cards) > _CARDS_PER_PACK
        self._configure_layout()

        # Use the same simple card back for every slot for a consistent pack reveal.
        self._back_imgs = []
        self._back_imgs_big = []
        back_path = settings.CARD_IMG_PATH + 'back.png'
        for i in range(max(1, len(self._cards))):
            self._back_imgs.append(_load_scaled_image(
                back_path, (self._card_w, self._card_h)))
            self._back_imgs_big.append(_load_scaled_image(
                back_path, (int(self._card_w * self._hover_scale),
                            int(self._card_h * self._hover_scale))))

        # Build front images for each card
        self._front_imgs = []
        self._front_imgs_big = []
        for c in self._cards:
            self._front_imgs.append(_card_front_image(
                window, c['suit'], c['rank'], (self._card_w, self._card_h)))
            self._front_imgs_big.append(_card_front_image(
                window, c['suit'], c['rank'],
                (int(self._card_w * self._hover_scale),
                 int(self._card_h * self._hover_scale))))

        # Glow images use the booster tier even before the card face is shown.
        glow_path = 'img/glow/rect/'
        self._glow_base = _load_scaled_image(
            glow_path + 'white.png', (self._glow_w, self._glow_h))
        self._tier_glows = {
            tier: _tier_glow_image(tier, self._glow_base)
            for tier in settings.COLLECTION_TIER_LABELS
        }

        # Close button (appears when all revealed)
        self._close_rect = pygame.Rect(
            (_SW - _CLOSE_W) // 2,
            self._button_y,
            _CLOSE_W, _CLOSE_H)
        self._reveal_all_rect = pygame.Rect(
            (_SW - _CLOSE_W) // 2,
            self._button_y,
            _CLOSE_W, _CLOSE_H)
        nav_y = self._button_y
        self._prev_rect = pygame.Rect(
            max(int(0.18 * _SW), self._close_rect.left - _NAV_W - int(0.024 * _SW)),
            nav_y,
            _NAV_W, _CLOSE_H)
        self._next_rect = pygame.Rect(
            min(_SW - int(0.18 * _SW) - _NAV_W,
                self._close_rect.right + int(0.024 * _SW)),
            nav_y,
            _NAV_W, _CLOSE_H)

    @property
    def all_revealed(self):
        return all(s == 'revealed' for s in self._states)

    def _has_hidden_cards(self):
        return any(s == 'hidden' for s in self._states)

    def _impact_summary_text(self):
        annotated = [c for c in self._cards if '_impact_owned_after' in c]
        if not annotated:
            return f'All {len(self._cards)} cards added to your collection'
        new_types = sum(1 for c in annotated if c.get('_impact_new_type'))
        copies = len(annotated)
        copy_label = 'free copy' if copies == 1 else 'free copies'
        if new_types:
            type_label = 'new card type' if new_types == 1 else 'new card types'
            return f'{copies} {copy_label} added  ·  {new_types} {type_label}'
        return f'{copies} {copy_label} added to your usable stock'

    def _configure_layout(self):
        n = len(self._cards)
        card_aspect = _CARD_W / max(1, _CARD_H)
        if not self._bulk:
            self._card_w = _CARD_W
            self._card_h = _CARD_H
            self._gap_x = _CARD_GAP
            self._gap_y = int(0.042 * _SH)
            self._cols = max(1, n)
            self._rows = 1
            self._page_size = max(1, n)
            self._page_count = 1
            self._hover_scale = _SCALE_HOVER
            total_w = n * self._card_w + max(0, n - 1) * self._gap_x
            start_x = (_SW - total_w) // 2
            self._card_y = (_SH - self._card_h) // 2 - int(0.03 * _SH)
            self._slots = [
                pygame.Rect(start_x + i * (self._card_w + self._gap_x),
                            self._card_y, self._card_w, self._card_h)
                for i in range(n)
            ]
            self._button_y = self._card_y + self._card_h + int(0.075 * _SH)
        else:
            self._card_h = max(64, int(0.16 * _SH))
            self._card_w = max(42, int(self._card_h * card_aspect))
            self._gap_x = max(12, int(0.018 * _SW))
            self._gap_y = max(22, int(0.050 * _SH))
            max_w = int(0.78 * _SW)
            self._cols = max(2, min(6, (max_w + self._gap_x)
                                    // (self._card_w + self._gap_x)))
            label_band = self._label_font.get_height() + int(0.022 * _SH)
            max_grid_h = int(0.48 * _SH)
            row_stride = self._card_h + label_band + self._gap_y
            self._rows = max(1, min(3, (max_grid_h + self._gap_y)
                                    // max(1, row_stride)))
            self._page_size = max(1, self._cols * self._rows)
            self._page_count = max(1, math.ceil(n / self._page_size))
            self._hover_scale = 1.08
            grid_w = self._cols * self._card_w + (self._cols - 1) * self._gap_x
            start_x = (_SW - grid_w) // 2
            grid_h = self._rows * self._card_h + (self._rows - 1) * self._gap_y
            self._card_y = max(int(0.24 * _SH),
                               min(int(0.33 * _SH),
                                   (_SH - grid_h) // 2 - int(0.02 * _SH)))
            self._slots = []
            for i in range(n):
                local = i % self._page_size
                row = local // self._cols
                col = local % self._cols
                x = start_x + col * (self._card_w + self._gap_x)
                y = self._card_y + row * (self._card_h + self._gap_y)
                self._slots.append(pygame.Rect(x, y, self._card_w, self._card_h))
            grid_bottom = self._card_y + grid_h
            self._button_y = min(
                _SH - _CLOSE_H - int(0.045 * _SH),
                grid_bottom + label_band + int(0.040 * _SH),
            )
        self._page_index = 0
        self._glow_w = int(self._card_w * 1.85)
        self._glow_h = int(self._card_h * 1.55)

    def _visible_indices(self):
        if self._page_count <= 1:
            return range(len(self._cards))
        start = self._page_index * self._page_size
        end = min(len(self._cards), start + self._page_size)
        return range(start, end)

    def update(self):
        """Advance reveal animations."""
        now = pygame.time.get_ticks()
        duration = settings.COLLECTION_REVEAL_FLIP_MS
        for i, state in enumerate(self._states):
            if state == 'revealing' and self._reveal_started_at[i] is not None:
                if now - self._reveal_started_at[i] >= duration:
                    self._states[i] = 'revealed'

    def draw(self):
        """Render the overlay."""
        self.window.blit(self._overlay, (0, 0))

        # Title
        if self._title_override:
            pack_label = self._title_override
        else:
            base_label = 'Side Booster Pack' if self._pack_type == 'side' else 'Main Booster Pack'
            pack_count = max(1, math.ceil(len(self._cards) / _CARDS_PER_PACK))
            if pack_count > 1:
                pack_label = f'{pack_count} {base_label}s'
            else:
                pack_label = base_label
        title = self._title_font.render(pack_label, True, (250, 221, 0))
        subtitle_text = 'Click each card to reveal its face'
        if self._bulk:
            subtitle_text = 'Click cards to reveal them, or reveal all'
        if self.all_revealed:
            subtitle_text = self._impact_summary_text()
        subtitle = self._subtitle_font.render(subtitle_text, True, (220, 210, 180))
        header_surfs = [title, subtitle]
        if self._page_count > 1:
            header_surfs.append(self._subtitle_font.render(
                f'Page {self._page_index + 1}/{self._page_count}',
                True, (190, 180, 150)))
        # Stack the header by actual font heights and seat it just above the
        # cards, so larger (mobile) fonts never overlap or collide with the grid.
        line_gap = int(0.008 * _SH)
        header_h = (sum(s.get_height() for s in header_surfs)
                    + line_gap * (len(header_surfs) - 1))
        y = max(int(0.012 * _SH),
                self._card_y - int(0.024 * _SH) - header_h)
        for surf in header_surfs:
            self.window.blit(surf, surf.get_rect(midtop=(_SW // 2, y)))
            y += surf.get_height() + line_gap

        mouse_pos = pygame.mouse.get_pos()

        for i in self._visible_indices():
            slot = self._slots[i]
            state = self._states[i]
            hovered = slot.inflate(int(slot.w * 0.3), int(slot.h * 0.3)).collidepoint(mouse_pos)

            if state == 'hidden':
                self._draw_hidden_card(i, slot, hovered)
            elif state == 'revealing':
                self._draw_revealing_card(i, slot, hovered)
            else:
                self._draw_revealed_card(i, slot, hovered)

        if self._page_count > 1:
            self._draw_overlay_button(
                self._prev_rect, 'Prev', self._page_index > 0)
            self._draw_overlay_button(
                self._next_rect, 'Next', self._page_index < self._page_count - 1)

        if self._has_hidden_cards() and len(self._cards) > 1:
            self._draw_overlay_button(self._reveal_all_rect, 'Reveal all')

        # Close button (only when all revealed)
        if self.all_revealed:
            self._draw_overlay_button(self._close_rect, 'Close')

    def _draw_overlay_button(self, rect, text, enabled=True):
        mouse_pos = pygame.mouse.get_pos()
        hovered = enabled and rect.collidepoint(mouse_pos)
        if not enabled:
            bg_clr = (40, 40, 40, 180)
            txt_clr = (100, 100, 100)
        elif hovered:
            bg_clr = (80, 70, 40, 220)
            txt_clr = (250, 240, 200)
        else:
            bg_clr = (35, 35, 40, 200)
            txt_clr = (200, 190, 160)
        surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
        surf.fill(bg_clr)
        pygame.draw.rect(surf, (120, 110, 90, 200), surf.get_rect(), 1)
        self.window.blit(surf, rect.topleft)
        txt = self._close_font.render(text, True, txt_clr)
        self.window.blit(txt, txt.get_rect(center=rect.center))

    def _draw_hidden_card(self, i, slot, hovered):
        tier = self._tiers[i]
        self._draw_tier_glow(slot, tier, pulse=hovered)

        img = self._back_imgs_big[i] if hovered else self._back_imgs[i]
        pos = img.get_rect(center=slot.center).topleft if hovered else slot.topleft
        self.window.blit(img, pos)

    def _draw_revealing_card(self, i, slot, hovered):
        tier = self._tiers[i]
        self._draw_tier_glow(slot, tier, pulse=True)
        self._draw_special_celebration(i, slot)
        progress = self._reveal_progress(i)
        # Flip illusion: squeeze horizontally until midpoint, then expand front.
        if progress < 0.5:
            img = self._back_imgs[i]
            scale_x = max(0.08, 1.0 - progress * 1.85)
        else:
            img = self._front_imgs[i]
            scale_x = max(0.08, (progress - 0.5) * 2.0)
        scale_y = 1.0 + 0.05 * (1.0 - abs(0.5 - progress) * 2.0)
        self._draw_scaled_center(img, slot.center, scale_x, scale_y)

    def _draw_revealed_card(self, i, slot, hovered):
        tier = self._tiers[i]
        self._draw_tier_glow(slot, tier, pulse=(tier == 3))

        if hovered:
            img = self._front_imgs_big[i]
            pos = img.get_rect(center=slot.center).topleft
            self.window.blit(img, pos)
        else:
            self.window.blit(self._front_imgs[i], slot.topleft)

        self._draw_special_celebration(i, slot)
        self._draw_impact_badge(i, slot)
        self._draw_card_labels(i, slot)

    def _draw_impact_badge(self, i, slot):
        card = self._cards[i]
        # Duplicate draws already show the resulting owned count below the
        # card. Reserve the reveal badge for genuinely new card types.
        text = _impact_badge_label(card)
        if not text:
            return
        text_clr = (45, 33, 5)
        bg_clr = (250, 221, 0, 242)
        text_surf = self._impact_font.render(text, True, text_clr)
        pad_x = max(4, int(0.006 * _SW))
        pad_y = max(2, int(0.003 * _SH))
        pill = pygame.Surface(
            (text_surf.get_width() + pad_x * 2,
             text_surf.get_height() + pad_y * 2),
            pygame.SRCALPHA,
        )
        pygame.draw.rect(pill, bg_clr, pill.get_rect(), border_radius=5)
        pygame.draw.rect(
            pill,
            (255, 244, 180, 220),
            pill.get_rect(), 1, border_radius=5,
        )
        pill_pos = (slot.right - pill.get_width() - 3, slot.y + 3)
        self.window.blit(pill, pill_pos)
        self.window.blit(text_surf, (
            pill_pos[0] + pad_x,
            pill_pos[1] + pad_y,
        ))

    @staticmethod
    def _celebration_duration_for_tier(tier):
        if tier == 3:
            return _RARE_CELEBRATION_MS
        if tier == 2:
            return _UNCOMMON_CELEBRATION_MS
        return 0

    def _celebration_progress(self, i):
        tier = self._tiers[i]
        duration = self._celebration_duration_for_tier(tier)
        start = self._reveal_started_at[i]
        if duration <= 0 or start is None:
            return None
        elapsed = pygame.time.get_ticks() - start
        if elapsed < 0:
            return 0.0
        total = settings.COLLECTION_REVEAL_FLIP_MS + duration
        if elapsed > total:
            return None
        return max(0.0, min(1.0, elapsed / max(1, total)))

    def _draw_special_celebration(self, i, slot):
        tier = self._tiers[i]
        progress = self._celebration_progress(i)
        if progress is None:
            return
        color = settings.COLLECTION_TIER_COLORS.get(tier, (255, 220, 90))
        strength = 1.0 if tier == 3 else 0.58
        self._draw_celebration_rings(slot, color, tier, progress, strength)
        self._draw_celebration_sparkles(i, slot, color, tier, progress, strength)

    def _draw_celebration_rings(self, slot, color, tier, progress, strength):
        ring_count = 2 if tier == 3 else 1
        for ring_idx in range(ring_count):
            local_t = max(0.0, min(1.0, progress * 1.2 - ring_idx * 0.18))
            if local_t <= 0.0:
                continue
            pulse = math.sin(math.pi * local_t)
            alpha = int((120 if tier == 3 else 82) * strength * (1.0 - local_t) * (0.65 + 0.35 * pulse))
            if alpha <= 0:
                continue
            inflate_x = int(slot.w * (0.28 + 0.55 * local_t + ring_idx * 0.16))
            inflate_y = int(slot.h * (0.18 + 0.38 * local_t + ring_idx * 0.10))
            ring_rect = slot.inflate(inflate_x, inflate_y)
            surf = pygame.Surface(ring_rect.size, pygame.SRCALPHA)
            pygame.draw.ellipse(
                surf,
                (*color, alpha),
                surf.get_rect().inflate(-2, -2),
                max(1, 2 if tier == 3 else 1),
            )
            self.window.blit(surf, ring_rect.topleft)

    def _draw_celebration_sparkles(self, i, slot, color, tier, progress, strength):
        count = 10 if tier == 3 else 6
        now = pygame.time.get_ticks()
        orbit = (now % 1200) / 1200.0
        fade = max(0.0, 1.0 - progress)
        for k in range(count):
            angle = (2.0 * math.pi * (k / count) + i * 0.41
                     + orbit * (1.35 if tier == 3 else 0.62))
            wobble = 0.5 + 0.5 * math.sin((progress * 6.0 + k) * math.pi)
            alpha = int((160 if tier == 3 else 105) * strength * fade * (0.45 + 0.55 * wobble))
            if alpha <= 0:
                continue
            rx = slot.w * (0.74 + 0.20 * math.sin(k * 1.7 + progress * math.pi))
            ry = slot.h * (0.62 + 0.14 * math.cos(k * 1.3 + progress * math.pi))
            x = int(slot.centerx + math.cos(angle) * rx)
            y = int(slot.centery + math.sin(angle) * ry)
            size = max(1, int((3 if tier == 3 else 2) * (0.7 + wobble)))
            sparkle_rect = pygame.Rect(x - size * 2, y - size * 2, size * 4, size * 4)
            surf = pygame.Surface(sparkle_rect.size, pygame.SRCALPHA)
            centre = surf.get_rect().center
            pygame.draw.line(surf, (*color, alpha),
                             (centre[0] - size, centre[1]),
                             (centre[0] + size, centre[1]), 1)
            pygame.draw.line(surf, (*color, alpha),
                             (centre[0], centre[1] - size),
                             (centre[0], centre[1] + size), 1)
            if tier == 3:
                pygame.draw.circle(surf, (*color, min(255, alpha + 35)), centre, 1)
            self.window.blit(surf, sparkle_rect.topleft)

    def _draw_card_labels(self, i, slot):
        c = self._cards[i]
        label_text = f"{c['suit']} {c['rank']}"
        if '_impact_owned_after' in c:
            label_text += f"  ·  ×{c['_impact_owned_after']}"
        label = self._label_font.render(label_text, True, (230, 220, 190))
        self.window.blit(label, label.get_rect(center=(slot.centerx, slot.bottom + int(0.012 * _SH))))

    def _draw_tier_glow(self, slot, tier, pulse=False):
        glow = self._tier_glows.get(tier) or self._tier_glows[1]
        self._draw_soft_halo(slot, tier)
        if pulse:
            now = pygame.time.get_ticks()
            pulse_ms = max(1, settings.COLLECTION_REVEAL_RARE_PULSE_MS)
            phase = (now % pulse_ms) / pulse_ms
            scale = 1.0 + (0.14 if tier == 3 else 0.08) * (1.0 - abs(0.5 - phase) * 2.0)
            if abs(scale - 1.0) > 0.01:
                gw = max(1, int(glow.get_width() * scale))
                gh = max(1, int(glow.get_height() * scale))
                glow = pygame.transform.smoothscale(glow, (gw, gh))
        self._draw_glow(glow, slot)

    def _draw_soft_halo(self, slot, tier):
        """Draw a feathered radial halo behind the card.

        Uses several concentric ellipses with decreasing alpha so the
        halo fades smoothly into the dim overlay instead of showing a
        hard edge.
        """
        color = settings.COLLECTION_TIER_COLORS.get(tier, (210, 210, 210))
        peak_alpha = 80 if tier == 3 else 62 if tier == 2 else 52
        halo_rect = slot.inflate(int(slot.w * 1.2), int(slot.h * 0.75))
        halo = pygame.Surface((halo_rect.w, halo_rect.h), pygame.SRCALPHA)
        layers = 8
        for step in range(layers, 0, -1):
            t = step / layers  # 1.0 outer → ~0 inner
            inset_x = int(halo_rect.w * 0.5 * (1.0 - t))
            inset_y = int(halo_rect.h * 0.5 * (1.0 - t))
            ring = pygame.Rect(
                inset_x, inset_y,
                halo_rect.w - inset_x * 2,
                halo_rect.h - inset_y * 2,
            )
            if ring.w <= 0 or ring.h <= 0:
                continue
            # Quadratic falloff so the centre stays bright and edges fade softly.
            layer_alpha = max(0, int(peak_alpha * (1.0 - t) ** 2))
            if layer_alpha == 0:
                continue
            pygame.draw.ellipse(halo, (*color, layer_alpha), ring)
        self.window.blit(halo, halo_rect.topleft)

    def _draw_glow(self, glow, slot):
        gx = slot.centerx - glow.get_width() // 2
        gy = slot.centery - glow.get_height() // 2
        self.window.blit(glow, (gx, gy))

    def _draw_scaled_center(self, img, center, scale_x, scale_y):
        w = max(1, int(img.get_width() * scale_x))
        h = max(1, int(img.get_height() * scale_y))
        scaled = pygame.transform.smoothscale(img, (w, h))
        self.window.blit(scaled, scaled.get_rect(center=center).topleft)

    def _reveal_progress(self, i):
        start = self._reveal_started_at[i]
        if start is None:
            return 0.0
        elapsed = pygame.time.get_ticks() - start
        progress = max(0.0, min(1.0, elapsed / max(1, settings.COLLECTION_REVEAL_FLIP_MS)))
        # Smoothstep easing keeps the flip polished but restrained.
        return progress * progress * (3.0 - 2.0 * progress)

    def handle_click(self, pos):
        """Handle a mouse click. Returns True when the overlay should close."""
        if self._page_count > 1:
            if self._prev_rect.collidepoint(pos) and self._page_index > 0:
                self._page_index -= 1
                return False
            if (self._next_rect.collidepoint(pos)
                    and self._page_index < self._page_count - 1):
                self._page_index += 1
                return False

        if self._has_hidden_cards() and self._reveal_all_rect.collidepoint(pos):
            now = pygame.time.get_ticks()
            reveal_index = 0
            for i, state in enumerate(self._states):
                if state != 'hidden':
                    continue
                self._states[i] = 'revealing'
                self._reveal_started_at[i] = now + reveal_index * _REVEAL_ALL_STAGGER_MS
                reveal_index += 1
            from utils import sound
            sound.play('booster_reveal')
            return False

        if self.all_revealed:
            if self._close_rect.collidepoint(pos):
                return True

        # Reveal hidden cards on click
        for i in self._visible_indices():
            slot = self._slots[i]
            if self._states[i] == 'hidden' and slot.collidepoint(pos):
                self._states[i] = 'revealing'
                self._reveal_started_at[i] = pygame.time.get_ticks()
                from utils import sound
                sound.play('booster_reveal')
                break

        return False
