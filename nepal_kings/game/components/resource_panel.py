# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Shared resource panel rendering used by kingdom config + build screens."""

import pygame
from config import settings


# Layout shared across screens. Castle resources go on the left, village on
# the right in the full panel; the compact variant lays everything in a row.
CASTLE_ROWS = [
    ('village',  'villager_red_black', [('villager_red', 'villager_black')]),
    ('military', 'warrior_red_black',  [('warrior_red', 'warrior_black')]),
]
VILLAGE_ROWS = [
    ('food',     'rice_meat',          [('food_red', 'food_black')]),
    ('material', 'wood_stone',         [('material_red', 'material_black')]),
    ('armor',    'sword_shield',       [('armor_red', 'armor_black')]),
]


def calc_resources(figures):
    """Aggregate produces/requires across an iterable of figure dicts."""
    produces, requires = {}, {}
    for fig in (figures or []):
        for res, amt in (fig.get('produces') or {}).items():
            produces[res] = produces.get(res, 0) + amt
        for res, amt in (fig.get('requires') or {}).items():
            requires[res] = requires.get(res, 0) + amt
    return {'produces': produces, 'requires': requires}


def load_resource_icons(icon_size):
    """Load and scale resource icons for the panel."""
    icons = {}
    paths = getattr(settings, 'RESOURCE_ICON_IMG_PATH_DICT', {}) or {}
    for key, path in paths.items():
        try:
            raw = pygame.image.load(path).convert_alpha()
            icons[key] = pygame.transform.smoothscale(raw, (icon_size, icon_size))
        except Exception:
            pass
    return icons


def _draw_pill(window, x, y, icon_size, req, prod, pill_clr, font, pill_min_w):
    deficit = req > prod
    text = f'{req}/{prod}'
    t_surf = font.render(text, True, (255, 255, 255))
    pw = max(t_surf.get_width() + 8, pill_min_w)
    ph = t_surf.get_height() + 4
    pr = pygame.Rect(x, y + (icon_size - ph) // 2, pw, ph)
    pill = pygame.Surface((pw, ph), pygame.SRCALPHA)
    pygame.draw.rect(pill, (*pill_clr, 220), pill.get_rect(), border_radius=3)
    window.blit(pill, pr.topleft)
    if deficit:
        pygame.draw.rect(window, (200, 50, 50), pr, 2, border_radius=3)
    tr = t_surf.get_rect(center=pr.center)
    window.blit(t_surf, tr.topleft)
    return pw


def draw_resource_panel(window, rect, resources_data, icons, font, *,
                        compact=False, show_label=True):
    """Draw the resource panel inside ``rect``.

    Parameters
    ----------
    compact:
        When True, render a single-row horizontal pill strip (used in the
        build figure screen).  Otherwise render the original two-column
        castle/village layout used in the conquer/defence config screens.
    show_label:
        When True, draw the small "Resources" label above the panel.
    """
    if not rect:
        return

    produces = resources_data.get('produces', {}) if resources_data else {}
    requires = resources_data.get('requires', {}) if resources_data else {}

    sw = pygame.display.get_surface().get_width() if pygame.display.get_surface() else 1920
    icon_s = int(0.019 * sw)
    pill_min_w = font.size("00/00")[0] + 8

    if show_label:
        lbl = font.render('Resources', True, (180, 170, 140))
        window.blit(lbl, (rect.x, rect.y - lbl.get_height() - 2))

    surf = pygame.Surface((rect.w, rect.h), pygame.SRCALPHA)
    pygame.draw.rect(surf, (35, 30, 25, 200), surf.get_rect(), border_radius=4)
    window.blit(surf, rect.topleft)
    pygame.draw.rect(window, (140, 130, 110), rect, 1, border_radius=4)

    if compact:
        _draw_compact_row(window, rect, produces, requires, icons,
                          icon_s, font, pill_min_w)
    else:
        _draw_two_column(window, rect, produces, requires, icons,
                         icon_s, font, pill_min_w)


def _draw_two_column(window, rect, produces, requires, icons,
                     icon_s, font, pill_min_w):
    half_w = rect.w // 2
    for col_offset, rows in [(0, CASTLE_ROWS), (half_w, VILLAGE_ROWS)]:
        y = rect.y + 8
        for label, icon_key, res_pairs in rows:
            ix = rect.x + col_offset + 8
            icon = icons.get(icon_key)
            if icon:
                window.blit(icon, (ix, y))
                ix += icon_s + 6
            for red_key, black_key in res_pairs:
                for res_key, pill_clr in [
                        (red_key,   (45, 90, 45)),
                        (black_key, (35, 60, 110))]:
                    pw = _draw_pill(
                        window, ix, y, icon_s,
                        requires.get(res_key, 0),
                        produces.get(res_key, 0),
                        pill_clr, font, pill_min_w)
                    ix += pw + 4
            y += icon_s + 6


def _draw_compact_row(window, rect, produces, requires, icons,
                      icon_s, font, pill_min_w):
    """Single horizontal row: [icon][r][b]  [icon][r][b] ... across rect."""
    all_rows = CASTLE_ROWS + VILLAGE_ROWS
    group_widths = []
    for _, icon_key, res_pairs in all_rows:
        w = icon_s + 6
        for _ in res_pairs:
            w += 2 * (pill_min_w + 4)
        group_widths.append(w)

    total = sum(group_widths)
    available = max(1, rect.w - 16)
    gap = max(6, (available - total) // max(1, len(all_rows) - 1)) if total < available else 6

    x = rect.x + 8
    y = rect.y + (rect.h - icon_s) // 2
    for (label, icon_key, res_pairs), gw in zip(all_rows, group_widths):
        icon = icons.get(icon_key)
        if icon:
            window.blit(icon, (x, y))
            x += icon_s + 6
        for red_key, black_key in res_pairs:
            for res_key, pill_clr in [
                    (red_key,   (45, 90, 45)),
                    (black_key, (35, 60, 110))]:
                pw = _draw_pill(
                    window, x, y, icon_s,
                    requires.get(res_key, 0),
                    produces.get(res_key, 0),
                    pill_clr, font, pill_min_w)
                x += pw + 4
        x += gap
