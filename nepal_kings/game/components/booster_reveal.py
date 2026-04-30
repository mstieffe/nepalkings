# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Booster pack reveal overlay — face-down cards with tier reveal polish."""

import pygame
from config import settings
from game.components.cards.card_img import CardImg

_SW, _SH = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT

# Card dimensions for the reveal overlay
_CARD_W = int(0.10 * _SW)
_CARD_H = int(0.25 * _SH)
_CARD_GAP = int(0.04 * _SW)
_SCALE_HOVER = 1.15

# Glow dimensions
_GLOW_W = int(_CARD_W * 1.5)
_GLOW_H = int(_CARD_H * 1.3)

# Close button
_CLOSE_W = int(0.12 * _SW)
_CLOSE_H = int(0.045 * _SH)


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


class BoosterRevealOverlay:
    """Full-screen overlay showing 3 face-down booster cards.

    Each card starts face-down. The user clicks cards to reveal them.
    Once all 3 are revealed a Close button appears.
    """

    def __init__(self, window, drawn_cards, pack_type='main'):
        """
        Args:
            window: pygame display surface
            drawn_cards: list of dicts [{suit, rank, value, tier}, ...]
            pack_type: 'main' or 'side', used to infer tiers for legacy responses
        """
        self.window = window
        self._cards = drawn_cards[:3]  # ensure max 3
        self._pack_type = pack_type
        self._tiers = [_card_tier(c, pack_type) for c in self._cards]

        # State per card slot: 'hidden' | 'revealing' | 'revealed'
        self._states = ['hidden'] * len(self._cards)
        self._reveal_started_at = [None] * len(self._cards)

        # Dim overlay
        self._overlay = pygame.Surface((_SW, _SH), pygame.SRCALPHA)
        self._overlay.fill((0, 0, 0, 180))

        # Load varied card backs for a little pack-opening texture.
        self._back_imgs = []
        self._back_imgs_big = []
        back_names = ('back.png', 'back2.png', 'back3.png')
        for i in range(max(1, len(self._cards))):
            back_raw = pygame.image.load(
                settings.CARD_IMG_PATH + back_names[i % len(back_names)]).convert_alpha()
            self._back_imgs.append(pygame.transform.smoothscale(back_raw, (_CARD_W, _CARD_H)))
            self._back_imgs_big.append(pygame.transform.smoothscale(
                back_raw, (int(_CARD_W * _SCALE_HOVER), int(_CARD_H * _SCALE_HOVER))))

        # Build front images for each card
        self._front_imgs = []
        self._front_imgs_big = []
        for c in self._cards:
            ci = CardImg(window, c['suit'], c['rank'], _CARD_W, _CARD_H)
            self._front_imgs.append(ci.front_img)
            ci_big = CardImg(window, c['suit'], c['rank'],
                             int(_CARD_W * _SCALE_HOVER), int(_CARD_H * _SCALE_HOVER))
            self._front_imgs_big.append(ci_big.front_img)

        # Glow images. Hidden cards keep the existing white/orange language;
        # revealed cards receive a tint based on booster tier.
        self._hidden_glows = {}
        glow_path = 'img/glow/rect/'
        for colour in ('white', 'orange'):
            raw = pygame.image.load(glow_path + colour + '.png').convert_alpha()
            self._hidden_glows[colour] = pygame.transform.smoothscale(raw, (_GLOW_W, _GLOW_H))
        glow_base_raw = pygame.image.load(glow_path + 'white.png').convert_alpha()
        self._glow_base = pygame.transform.smoothscale(glow_base_raw, (_GLOW_W, _GLOW_H))
        self._tier_glows = {
            tier: self._make_tier_glow(settings.COLLECTION_TIER_GLOW_TINTS[tier])
            for tier in settings.COLLECTION_TIER_LABELS
        }

        # Card positions (centred horizontally)
        n = len(self._cards)
        total_w = n * _CARD_W + (n - 1) * _CARD_GAP
        start_x = (_SW - total_w) // 2
        card_y = (_SH - _CARD_H) // 2 - int(0.03 * _SH)
        self._card_y = card_y
        self._slots = []
        for i in range(n):
            x = start_x + i * (_CARD_W + _CARD_GAP)
            self._slots.append(pygame.Rect(x, card_y, _CARD_W, _CARD_H))

        # Close button (appears when all revealed)
        self._close_rect = pygame.Rect(
            (_SW - _CLOSE_W) // 2,
            card_y + _CARD_H + int(0.04 * _SH),
            _CLOSE_W, _CLOSE_H)
        self._close_font = settings.get_font(int(0.022 * _SH))

        # Title / label fonts
        self._title_font = settings.get_font(int(0.028 * _SH), bold=True)
        self._subtitle_font = settings.get_font(int(0.018 * _SH))
        self._tier_font = settings.get_font(settings.COLLECTION_REVEAL_TIER_LABEL_FONT_SIZE, bold=True)

    def _make_tier_glow(self, tint):
        glow = self._glow_base.copy()
        glow.fill(tint, special_flags=pygame.BLEND_RGBA_MULT)
        return glow

    @property
    def all_revealed(self):
        return all(s == 'revealed' for s in self._states)

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
        pack_label = 'Side Booster Pack' if self._pack_type == 'side' else 'Main Booster Pack'
        title = self._title_font.render(pack_label, True, (250, 221, 0))
        tx = (_SW - title.get_width()) // 2
        ty = self._card_y - int(0.074 * _SH)
        self.window.blit(title, (tx, ty))
        subtitle_text = 'Click each card to reveal its tier glow'
        if self.all_revealed:
            subtitle_text = 'All cards added to your collection'
        subtitle = self._subtitle_font.render(subtitle_text, True, (220, 210, 180))
        self.window.blit(subtitle, subtitle.get_rect(center=(_SW // 2, ty + int(0.040 * _SH))))

        mouse_pos = pygame.mouse.get_pos()

        for i, slot in enumerate(self._slots):
            state = self._states[i]
            hovered = slot.inflate(int(_CARD_W * 0.3), int(_CARD_H * 0.3)).collidepoint(mouse_pos)

            if state == 'hidden':
                self._draw_hidden_card(i, slot, hovered)
            elif state == 'revealing':
                self._draw_revealing_card(i, slot, hovered)
            else:
                self._draw_revealed_card(i, slot, hovered)

        # Close button (only when all revealed)
        if self.all_revealed:
            btn_hovered = self._close_rect.collidepoint(mouse_pos)
            bg_clr = (80, 70, 40, 220) if btn_hovered else (35, 35, 40, 200)
            txt_clr = (250, 240, 200) if btn_hovered else (200, 190, 160)
            surf = pygame.Surface((self._close_rect.w, self._close_rect.h), pygame.SRCALPHA)
            surf.fill(bg_clr)
            pygame.draw.rect(surf, (120, 110, 90, 200), surf.get_rect(), 1)
            self.window.blit(surf, self._close_rect.topleft)
            txt = self._close_font.render('Close', True, txt_clr)
            self.window.blit(txt, txt.get_rect(center=self._close_rect.center))

    def _draw_hidden_card(self, i, slot, hovered):
        glow_key = 'orange' if hovered else 'white'
        self._draw_glow(self._hidden_glows[glow_key], slot)

        img = self._back_imgs_big[i] if hovered else self._back_imgs[i]
        pos = img.get_rect(center=slot.center).topleft if hovered else slot.topleft
        self.window.blit(img, pos)

    def _draw_revealing_card(self, i, slot, hovered):
        tier = self._tiers[i]
        self._draw_tier_glow(slot, tier, pulse=True)
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

        self._draw_card_labels(i, slot)

    def _draw_card_labels(self, i, slot):
        c = self._cards[i]
        tier = self._tiers[i]
        tier_label = settings.COLLECTION_TIER_LABELS.get(tier, 'Common')
        tier_color = settings.COLLECTION_TIER_COLORS.get(tier, (220, 210, 180))

        label = self._close_font.render(
            f"{c['suit']} {c['rank']}", True, (230, 220, 190))
        self.window.blit(label, label.get_rect(center=(slot.centerx, slot.bottom + int(0.012 * _SH))))

        tier_surf = self._tier_font.render(tier_label.upper(), True, tier_color)
        pill_pad_x = int(0.008 * _SW)
        pill_pad_y = int(0.003 * _SH)
        pill = pygame.Rect(0, 0,
                           tier_surf.get_width() + pill_pad_x * 2,
                           tier_surf.get_height() + pill_pad_y * 2)
        pill.center = (slot.centerx, slot.bottom + int(0.040 * _SH))
        pill_bg = pygame.Surface((pill.w, pill.h), pygame.SRCALPHA)
        pygame.draw.rect(pill_bg, (24, 24, 30, 210), pill_bg.get_rect(), border_radius=6)
        pygame.draw.rect(pill_bg, (*tier_color, 190), pill_bg.get_rect(), 1, border_radius=6)
        self.window.blit(pill_bg, pill.topleft)
        self.window.blit(tier_surf, tier_surf.get_rect(center=pill.center))

    def _draw_tier_glow(self, slot, tier, pulse=False):
        glow = self._tier_glows.get(tier) or self._tier_glows[1]
        if pulse:
            now = pygame.time.get_ticks()
            pulse_ms = max(1, settings.COLLECTION_REVEAL_RARE_PULSE_MS)
            phase = (now % pulse_ms) / pulse_ms
            scale = 1.0 + (0.08 if tier == 3 else 0.04) * (1.0 - abs(0.5 - phase) * 2.0)
            if abs(scale - 1.0) > 0.01:
                gw = max(1, int(glow.get_width() * scale))
                gh = max(1, int(glow.get_height() * scale))
                glow = pygame.transform.smoothscale(glow, (gw, gh))
        self._draw_glow(glow, slot)

        if tier == 3:
            ring = slot.inflate(int(0.018 * _SW), int(0.022 * _SH))
            pygame.draw.rect(self.window, settings.COLLECTION_TIER_COLORS[3], ring, 2, border_radius=10)

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
        if self.all_revealed:
            if self._close_rect.collidepoint(pos):
                return True

        # Reveal hidden cards on click
        for i, slot in enumerate(self._slots):
            if self._states[i] == 'hidden' and slot.collidepoint(pos):
                self._states[i] = 'revealing'
                self._reveal_started_at[i] = pygame.time.get_ticks()
                break

        return False
