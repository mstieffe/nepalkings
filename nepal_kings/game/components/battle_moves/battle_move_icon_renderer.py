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
    """Draw a single battle move icon with glow, frame, power number and suit icon.

    The drawing order is:
      1. Glow (suit-coloured, or yellow if used)
      2. Family icon (greyed if used)
      3. Frame (greyed if used)
      4. Power number at 3/4 height with dark circle background (white text)
      5. Suit icon centred below the icon

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

    # ── 4. Power number — centred vertically, at 0.2 icon_width from left edge ──
    label_color = (180, 170, 155) if is_used else (255, 255, 255)
    val_surf = font.render(str(power_value), True, label_color)
    val_cx = cx - int(eff_icon_s * 0.26)  # 0.2 from left edge = centre - 0.3
    val_cy = cy - 0.02 * icon_size  

    # Dark circle background for readability
    circle_r = max(val_surf.get_width(), val_surf.get_height()) // 2 + 4
    circle_surf = pygame.Surface((circle_r * 2, circle_r * 2), pygame.SRCALPHA)
    bg_alpha = 140 if is_used else 180
    pygame.draw.circle(circle_surf, (0, 0, 0, bg_alpha), (circle_r, circle_r), circle_r)
    window.blit(circle_surf, circle_surf.get_rect(center=(val_cx, val_cy)).topleft)
    window.blit(val_surf, val_surf.get_rect(center=(val_cx, val_cy)).topleft)

    # ── 5. Suit icon(s) — centred vertically, at 0.8 icon_width from left edge ──
    si_cx = cx + int(eff_icon_s * 0.26)  # 0.8 from left edge = centre + 0.3

    if suit_b and suit_b != suit:
        # Double Dagger: draw two suit icons side by side
        suit_key_a = suit.lower()
        suit_key_b = suit_b.lower()
        icon_a = suit_icon_cache.get(suit_key_a + suffix) or suit_icon_cache.get(suit_key_a)
        icon_b = suit_icon_cache.get(suit_key_b + suffix) or suit_icon_cache.get(suit_key_b)
        gap = 2
        icons = [i for i in (icon_a, icon_b) if i]
        if icons:
            total_w = sum(i.get_width() for i in icons) + gap * (len(icons) - 1)
            start_x = si_cx - total_w // 2
            for si in icons:
                si_rect = si.get_rect(topleft=(start_x, val_cy - si.get_height() // 2))
                if is_used:
                    si_copy = si.copy()
                    si_copy.set_alpha(alpha)
                    window.blit(si_copy, si_rect.topleft)
                else:
                    window.blit(si, si_rect.topleft)
                start_x += si.get_width() + gap
    else:
        # Single suit icon
        suit_key = suit.lower()
        suit_icon = suit_icon_cache.get(suit_key + suffix) or suit_icon_cache.get(suit_key)
        if suit_icon:
            si_rect = suit_icon.get_rect(center=(si_cx, val_cy))
            if is_used:
                si_copy = suit_icon.copy()
                si_copy.set_alpha(alpha)
                window.blit(si_copy, si_rect.topleft)
            else:
                window.blit(suit_icon, si_rect.topleft)
