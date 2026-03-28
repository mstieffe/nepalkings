# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Shared rendering logic for battle move icons (diamond-shaped slots).

Used by both the Battle Shop Screen (bought slots) and Battle Screen
(left panel + round slots) to draw battle move icons consistently.
"""

import pygame


def draw_battle_move_icon(
    window,
    cx, cy,
    family_name,
    suit,
    power_value,
    glow_cache,
    icon_cache,
    frame_cache,
    suit_icon_cache,
    font,
    icon_size,
    hovered=False,
    is_used=False,
    suffix='',
    suit_b=None,
):
    """Draw a single battle move icon with glow, frame, and power/suit badge.

    The drawing order is:
      1. Glow (suit-coloured, or yellow if used)
      2. Family icon (greyed if used)
      3. Frame (greyed if used)
      4. Elliptical badge at centre-bottom with power value + suit icon(s)

    Parameters
    ----------
    window : pygame.Surface
        Target surface to draw on.
    cx, cy : int
        Centre of the icon.
    family_name : str
        Battle move family name (key into icon/frame caches).
    suit : str
        Suit name, e.g. "Hearts", "Spades".
    power_value : int | str
        The numeric power value to display.
    glow_cache : dict
        Keyed by ``'green'``, ``'blue'``, ``'yellow'``, with optional ``'_big'`` variants.
    icon_cache : dict
        Keyed by ``family_name``, with optional ``'_big'`` variants.
    frame_cache : dict
        Keyed by ``family_name``, with optional ``'_big'`` variants.
    suit_icon_cache : dict
        Keyed by lowercase suit name, with optional ``'_big'`` variants.
    font : pygame.font.Font
        Font used for the power number.
    icon_size : int
        Nominal icon size (used for positioning suit icon below).
    hovered : bool
        Whether the icon is in hover state (use ``_big`` assets).
    is_used : bool
        Whether the move has been played (grey-out).
    suffix : str
        Asset suffix, typically ``''`` or ``'_big'``.  If not provided,
        derived from *hovered*.
    suit_b : str or None
        Optional second suit for Double Dagger moves. When present, both
        suit icons are drawn side-by-side.
    """
    if not suffix:
        suffix = '_big' if hovered else ''

    alpha = 100 if is_used else 255

    # Determine effective icon size from actual cached image (accounts for hover scale)
    icon_img_check = icon_cache.get(family_name + suffix) if family_name else None
    eff_icon_s = icon_img_check.get_width() if icon_img_check else icon_size

    # ── 1. Glow ──
    glow_key = 'green' if suit in ('Hearts', 'Diamonds') else 'blue'
    if is_used:
        glow_key = 'yellow'
    glow_img = glow_cache.get(glow_key + suffix)
    if glow_img:
        gr = glow_img.get_rect(center=(cx, cy))
        window.blit(glow_img, gr.topleft)

    # ── 2. Family icon ──
    icon_img = icon_cache.get(family_name + suffix)
    if icon_img:
        if is_used:
            img = icon_img.copy()
            img.set_alpha(alpha)
            window.blit(img, img.get_rect(center=(cx, cy)).topleft)
        else:
            window.blit(icon_img, icon_img.get_rect(center=(cx, cy)).topleft)

    # ── 3. Frame ──
    frame_img = frame_cache.get(family_name + suffix)
    if frame_img:
        if is_used:
            img = frame_img.copy()
            img.set_alpha(alpha)
            window.blit(img, img.get_rect(center=(cx, cy)).topleft)
        else:
            window.blit(frame_img, frame_img.get_rect(center=(cx, cy)).topleft)

    # ── 4 + 5. Combined value + suit badge — elliptical, centred at bottom ──
    label_color = (180, 170, 155) if is_used else (255, 255, 255)
    val_surf = font.render(str(power_value), True, label_color)

    # Collect suit icon(s)
    suit_icons = []
    if suit_b and suit_b != suit:
        for sk in (suit.lower(), suit_b.lower()):
            si = suit_icon_cache.get(sk + suffix) or suit_icon_cache.get(sk)
            if si:
                suit_icons.append(si)
    else:
        si = suit_icon_cache.get(suit.lower() + suffix) or suit_icon_cache.get(suit.lower())
        if si:
            suit_icons.append(si)

    # Layout: [value] [gap] [suit icon(s)]  inside an ellipse
    inner_gap = 3
    suit_gap = 2
    si_total_w = sum(s.get_width() for s in suit_icons) + suit_gap * max(0, len(suit_icons) - 1)
    si_max_h = max((s.get_height() for s in suit_icons), default=0)
    content_w = val_surf.get_width() + (inner_gap + si_total_w if suit_icons else 0)
    content_h = max(val_surf.get_height(), si_max_h)

    pad_x = 5
    pad_y = 3
    ell_w = content_w + pad_x * 2
    ell_h = content_h + pad_y * 2

    badge_cx = cx
    badge_cy = cy + int(eff_icon_s * 0.34)

    # Draw elliptical background
    bg_alpha = 140 if is_used else 180
    ell_surf = pygame.Surface((ell_w, ell_h), pygame.SRCALPHA)
    pygame.draw.ellipse(ell_surf, (0, 0, 0, bg_alpha), (0, 0, ell_w, ell_h))
    window.blit(ell_surf, ell_surf.get_rect(center=(badge_cx, badge_cy)).topleft)

    # Draw value text (left of centre within badge)
    val_x = badge_cx - content_w // 2
    val_rect = val_surf.get_rect(midleft=(val_x, badge_cy))
    if is_used:
        val_copy = val_surf.copy()
        val_copy.set_alpha(alpha)
        window.blit(val_copy, val_rect.topleft)
    else:
        window.blit(val_surf, val_rect.topleft)

    # Draw suit icon(s) (right of value)
    if suit_icons:
        si_start_x = val_rect.right + inner_gap
        for si in suit_icons:
            si_rect = si.get_rect(midleft=(si_start_x, badge_cy))
            if is_used:
                si_copy = si.copy()
                si_copy.set_alpha(alpha)
                window.blit(si_copy, si_rect.topleft)
            else:
                window.blit(si, si_rect.topleft)
            si_start_x += si.get_width() + suit_gap
