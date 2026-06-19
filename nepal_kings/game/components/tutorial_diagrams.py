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


def _resource_icon(name, size):
    return _scaled(_load(_asset('img', 'resource_icons', f'{name}.png')), size)


def figure_anatomy_diagram(target_h=None):
    """Window 2: a figure is built from same-suit cards and trades resources.

    [J♥][7♥] → (Rice Farm)   requires [villager] · produces [rice].
    """
    _SH = settings.SCREEN_HEIGHT
    target_h = int(target_h or 0.15 * _SH)
    key = ('anatomy', target_h)
    if key in _CACHE:
        return _CACHE[key]

    card_h = target_h
    j = _card_surface('Hearts', 'J', card_h)
    seven = _card_surface('Hearts', '7', card_h)
    farm = field_figure_icon('Small Rice Farm', 'rice_farm1.png', label='',
                             target_h=int(target_h * 1.05))
    gap = int(0.012 * settings.SCREEN_WIDTH)
    arrow_w = int(0.05 * settings.SCREEN_WIDTH)

    # Resource line below.
    res_sz = int(target_h * 0.34)
    font = settings.get_font(getattr(settings, 'FS_TINY', 16))
    villager = _resource_icon('villager_red', res_sz)
    rice = _resource_icon('rice', res_sz)
    req_lbl = font.render('requires', True, (235, 222, 190))
    prod_lbl = font.render('produces', True, (235, 222, 190))
    res_parts = [p for p in [req_lbl, villager, prod_lbl, rice] if p]
    rgap = int(0.008 * settings.SCREEN_WIDTH)
    res_w = sum(p.get_width() for p in res_parts) + rgap * max(0, len(res_parts) - 1)
    res_h = max((p.get_height() for p in res_parts), default=0)

    top_w = (j.get_width() + gap + seven.get_width() + arrow_w
             + (farm.get_width() if farm else 0))
    w = max(top_w, res_w)
    line_gap = int(0.018 * _SH)
    top_h = max(card_h, farm.get_height() if farm else 0)
    surf = pygame.Surface((w, top_h + line_gap + res_h), pygame.SRCALPHA)

    x = (w - top_w) // 2
    cy = top_h // 2
    surf.blit(j, (x, cy - j.get_height() // 2)); x += j.get_width() + gap
    surf.blit(seven, (x, cy - seven.get_height() // 2)); x += seven.get_width()
    _draw_arrow(surf, (x + gap, cy), (x + arrow_w - gap, cy)); x += arrow_w
    if farm:
        surf.blit(farm, (x, cy - farm.get_height() // 2))

    x = (w - res_w) // 2
    ry = top_h + line_gap
    for p in res_parts:
        surf.blit(p, (x, ry + (res_h - p.get_height()) // 2))
        x += p.get_width() + rgap

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


def _figure_info_pill(rep, label, suit, max_w):
    """A parchment info pill (name + power + suit + skills), like the field's
    figure info line. Returns a Surface or None."""
    name_font = settings.get_font(getattr(settings, 'FS_TINY', 18))
    name = label or (getattr(rep, 'name', '') if rep else '')
    parts = []  # (surface, baseline_h)
    if name:
        parts.append(name_font.render(name, True, settings.SUIT_ICON_CAPTION_COLOR))
    line_h = name_font.get_height()
    icon_sz = int(line_h * 0.95)
    if rep is not None:
        try:
            parts.append(name_font.render(str(int(rep.get_value())), True,
                                          settings.SUIT_ICON_CAPTION_COLOR))
        except Exception:
            pass
    si = _suit_icon(suit, icon_sz) if suit else None
    if si:
        parts.append(si)
    if rep is not None:
        try:
            parts.extend(_skill_icons(rep.get_active_skill_keys(), icon_sz))
        except Exception:
            pass
    if not parts:
        return None
    gap = max(3, int(0.003 * settings.SCREEN_WIDTH))
    pad_x = int(line_h * 0.45)
    pad_y = max(2, int(line_h * 0.12))
    content_w = sum(p.get_width() for p in parts) + gap * (len(parts) - 1)
    h = max(p.get_height() for p in parts) + pad_y * 2
    w = content_w + pad_x * 2
    pill = pygame.Surface((w, h), pygame.SRCALPHA)
    corner = getattr(settings, 'FIGURE_NAME_CORNER_R', 5)
    pygame.draw.rect(pill, settings.FIGURE_NAME_BG_COLOR, pill.get_rect(), border_radius=corner)
    pygame.draw.rect(pill, settings.FIGURE_NAME_FRAME_COLOR, pill.get_rect(), 2, border_radius=corner)
    x = pad_x
    for p in parts:
        pill.blit(p, (x, (h - p.get_height()) // 2))
        x += p.get_width() + gap
    if w > max_w and w > 0:
        pill = pygame.transform.smoothscale(pill, (max_w, max(1, int(h * max_w / w))))
    return pill


def field_figure_icon(family_name, fallback_icon=None, label=None, target_h=None):
    """A faithful field-figure icon, rendered exactly like the field/conquer
    screens: the icon sits INSIDE a frame scaled to FRAME_FIGURE_SCALE x the
    icon (so it never overflows), with a parchment info pill (name, power,
    suit, skill icons) below it.
    """
    _SH = settings.SCREEN_HEIGHT
    box = int(target_h or 0.16 * _SH)
    label = family_name if label is None else label  # '' => no info pill
    key = ('fieldfig', family_name, box, label)
    if key in _CACHE:
        return _CACHE[key]

    mgr = _figure_manager()
    family = mgr.families.get(family_name) if mgr else None
    rep = None
    if mgr:
        reps = mgr.figures_by_name.get(family_name) or []
        rep = reps[0] if reps else None
    suit = getattr(rep, 'suit', None)

    # Match FigureIcon.draw_icon: frame is FRAME_FIGURE_SCALE x the icon, both
    # centred, so the icon sits inside the frame instead of filling it.
    frame_scale = getattr(settings, 'FRAME_FIGURE_SCALE', 1.4)
    icon_box = int(box / frame_scale)
    frame_src = getattr(family, 'frame_img', None) if family else None
    icon_src = getattr(family, 'icon_img', None) if family else None
    if icon_src is None and fallback_icon:
        icon_src = _load(_asset('img', 'figures', 'icons', fallback_icon))
    frame_img = _scaled(frame_src, box) if frame_src is not None else None
    icon_img = _scaled(icon_src, icon_box) if icon_src is not None else None

    frame_w = frame_img.get_width() if frame_img is not None else box
    frame_h = frame_img.get_height() if frame_img is not None else box
    pill = _figure_info_pill(rep, label, suit, box) if label else None
    pill_h = (pill.get_height() + max(2, int(box * 0.04))) if pill else 0
    w = max(box, frame_w, pill.get_width() if pill else 0)
    top_h = max(box, frame_h)
    surf = pygame.Surface((w, top_h + pill_h), pygame.SRCALPHA)
    cx = w // 2

    cy = top_h // 2
    # Match the field draw order: icon first, then the frame ON TOP, so the
    # frame border overlaps the icon edges (icon never floats over the frame).
    if icon_img is not None:
        surf.blit(icon_img, icon_img.get_rect(center=(cx, cy)))
    if frame_img is not None:
        surf.blit(frame_img, frame_img.get_rect(center=(cx, cy)))
    else:
        fr = pygame.Rect(0, 0, box, box)
        fr.center = (cx, cy)
        pygame.draw.rect(surf, (224, 182, 82), fr, 2, border_radius=10)
    if pill is not None:
        surf.blit(pill, pill.get_rect(midtop=(cx, top_h + max(2, int(box * 0.02)))))

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


_SPELL_ICON_FILES = {
    'Poison': 'poisson_portion.png',
    'Blitzkrieg': 'blitzkrieg.png',
    'Draw 2 MainCards': 'draw_two_main.png',
    'Health Boost': 'health_portion.png',
    'All Seeing Eye': 'eye.png',
}


def _chip(icon, box, accent=(224, 182, 82)):
    """Frame an icon in a small rounded 'button' chip."""
    surf = pygame.Surface((box, box), pygame.SRCALPHA)
    r = surf.get_rect()
    pygame.draw.rect(surf, (28, 22, 14, 235), r, border_radius=8)
    pygame.draw.rect(surf, accent, r, 2, border_radius=8)
    ic = _scaled(icon, int(box * 0.74)) if icon else None
    if ic:
        surf.blit(ic, ic.get_rect(center=r.center))
    return surf


def _spell_chip(name, box):
    icon = _load(_asset('img', 'spells', 'icons', _SPELL_ICON_FILES.get(name, '')))
    return _chip(icon, box, accent=(170, 120, 210))


def _dagger_chip(box):
    icon = _load(_asset('img', 'battle', 'icons', 'dagger.png'))
    return _chip(icon, box, accent=(210, 170, 120))


def _result_surface(kind, ref, box):
    if kind == 'figure':
        return field_figure_icon(ref, None, label='', target_h=box)
    if kind == 'spell':
        return _spell_chip(ref, box)
    if kind == 'dagger':
        return _dagger_chip(box)
    return _chip(None, box)


def _recipe_diagram(cache_key, entries, target_h=None):
    """A grid of recipe rows ([cards] → [result] label) with COLUMN ALIGNMENT.

    Cards are right-aligned to a shared column so every arrow lands on the same
    vertical axis; results and labels share their own aligned columns too.
    """
    _SH = settings.SCREEN_HEIGHT
    row_h = int(target_h or 0.072 * _SH)
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    label_font = settings.get_font(getattr(settings, 'FS_SMALL', 18))
    card_h = int(row_h * 0.92)
    gap = max(3, int(0.004 * settings.SCREEN_WIDTH))
    col_gap = int(0.012 * settings.SCREEN_WIDTH)
    arrow_w = int(0.045 * settings.SCREEN_WIDTH)
    right_pad = int(0.008 * settings.SCREEN_WIDTH)

    built = []
    for e in entries:
        cards = [_card_surface(s, r, card_h) for (r, s) in e['cards']]
        result = _result_surface(e['kind'], e['ref'], row_h)
        label = e.get('label', '')
        lbl = label_font.render(label, True, (235, 222, 190)) if label else None
        cards_w = sum(c.get_width() for c in cards) + gap * max(0, len(cards) - 1)
        built.append((cards, cards_w, result, lbl))

    cards_col = max((b[1] for b in built), default=0)
    result_col = max((b[2].get_width() if b[2] else 0 for b in built), default=0)
    label_col = max((b[3].get_width() if b[3] else 0 for b in built), default=0)
    row_w = cards_col + col_gap + arrow_w + col_gap + result_col + col_gap + label_col + right_pad
    row_gap = int(0.016 * _SH)
    n = len(built)
    surf = pygame.Surface((max(1, row_w), max(1, n * row_h + row_gap * max(0, n - 1))),
                          pygame.SRCALPHA)

    # Shared column x-positions (so all arrows align on one axis).
    arrow_x0 = cards_col + col_gap
    arrow_x1 = arrow_x0 + arrow_w
    result_x = arrow_x1 + col_gap
    label_x = result_x + result_col + col_gap

    y = 0
    for cards, cards_w, result, lbl in built:
        cy = y + row_h // 2
        # Cards: right-aligned to the cards column so the arrow start is fixed.
        cx = cards_col - cards_w
        for c in cards:
            surf.blit(c, (cx, cy - c.get_height() // 2))
            cx += c.get_width() + gap
        _draw_arrow(surf, (arrow_x0, cy), (arrow_x1, cy))
        if result:
            surf.blit(result, (result_x + (result_col - result.get_width()) // 2,
                               cy - result.get_height() // 2))
        if lbl:
            surf.blit(lbl, (label_x, cy - lbl.get_height() // 2))
        y += row_h + row_gap

    _CACHE[cache_key] = surf
    return surf


def field_compartments_diagram(target_h=None):
    """Window 2: the three fields (Castle / Village / Military), each holding a
    representative figure — illustrating where figures stand."""
    _SH = settings.SCREEN_HEIGHT
    target_h = int(target_h or 0.16 * _SH)
    key = ('compartments', target_h)
    if key in _CACHE:
        return _CACHE[key]
    fields = [
        ('Castle', 'Djungle King', 'castle_red.png'),
        ('Village', 'Small Rice Farm', 'rice_farm1.png'),
        ('Military', 'Gorkha Warriors', 'army1.png'),
    ]
    header_font = settings.get_font(getattr(settings, 'FS_SMALL', 18), bold=True)
    icon_h = int(target_h * 0.86)
    header_gap = max(4, int(0.01 * _SH))
    cols = []
    for field_name, fam, fb in fields:
        icon = field_figure_icon(fam, fb, label='', target_h=icon_h)
        header = header_font.render(field_name, True, (240, 210, 140))
        col_w = max(icon.get_width(), header.get_width())
        col_h = header.get_height() + header_gap + icon.get_height()
        col = pygame.Surface((col_w, col_h), pygame.SRCALPHA)
        col.blit(header, header.get_rect(midtop=(col_w // 2, 0)))
        col.blit(icon, icon.get_rect(midtop=(col_w // 2, header.get_height() + header_gap)))
        cols.append(col)
    gap = int(0.03 * settings.SCREEN_WIDTH)
    total_w = sum(c.get_width() for c in cols) + gap * (len(cols) - 1)
    h = max(c.get_height() for c in cols)
    surf = pygame.Surface((total_w, h), pygame.SRCALPHA)
    x = 0
    for c in cols:
        surf.blit(c, (x, 0))
        x += c.get_width() + gap
    _CACHE[key] = surf
    return surf


def offensive_vs_defensive_diagram(target_h=None):
    """Welcome window 2: an offensive figure (Warriors) vs a defensive one
    (Wooden Fortress / 'Tower'), shown as full field-figure icons."""
    _SH = settings.SCREEN_HEIGHT
    target_h = int(target_h or 0.18 * _SH)
    key = ('off_vs_def', target_h)
    if key in _CACHE:
        return _CACHE[key]
    header_font = settings.get_font(getattr(settings, 'FS_SMALL', 18), bold=True)
    icon_h = int(target_h * 0.86)
    header_gap = max(4, int(0.01 * _SH))

    def column(field_name, header_color, fam, fb, lbl):
        icon = field_figure_icon(fam, fb, label=lbl, target_h=icon_h)
        header = header_font.render(field_name, True, header_color)
        col_w = max(icon.get_width(), header.get_width())
        col_h = header.get_height() + header_gap + icon.get_height()
        col = pygame.Surface((col_w, col_h), pygame.SRCALPHA)
        col.blit(header, header.get_rect(midtop=(col_w // 2, 0)))
        col.blit(icon, icon.get_rect(midtop=(col_w // 2, header.get_height() + header_gap)))
        return col

    left = column('OFFENSIVE', (232, 138, 120), 'Gorkha Warriors', 'army1.png', 'Warriors')
    right = column('DEFENSIVE', (130, 178, 224), 'Wooden Fortress', 'fortress1.png', 'Tower')
    vs_font = settings.get_font(getattr(settings, 'FS_HEADING', 28), bold=True)
    vs = vs_font.render('vs', True, (235, 222, 190))
    gap = int(0.03 * settings.SCREEN_WIDTH)
    total_w = left.get_width() + gap + vs.get_width() + gap + right.get_width()
    h = max(left.get_height(), right.get_height())
    surf = pygame.Surface((total_w, h), pygame.SRCALPHA)
    x = 0
    surf.blit(left, (x, 0)); x += left.get_width() + gap
    surf.blit(vs, vs.get_rect(center=(x + vs.get_width() // 2, h // 2))); x += vs.get_width() + gap
    surf.blit(right, (x, 0))
    _CACHE[key] = surf
    return surf


def card_recipe_examples(target_h=None):
    """Window 1: one figure and one spell example."""
    entries = [
        {'cards': [('J', 'Hearts'), ('7', 'Hearts')], 'kind': 'figure',
         'ref': 'Small Rice Farm', 'label': 'Rice Farm (figure)'},
        {'cards': [('Q', 'Hearts'), ('Q', 'Hearts')], 'kind': 'spell',
         'ref': 'Blitzkrieg', 'label': 'Blitzkrieg (spell)'},
    ]
    return _recipe_diagram(('recipe_examples', int(target_h or 0)), entries, target_h)


def land_hex_diagram(target_h=None):
    """Window 4: a land hex showing gold production and its tier."""
    _SH = settings.SCREEN_HEIGHT
    size = int(target_h or 0.22 * _SH)
    key = ('landhex', size)
    if key in _CACHE:
        return _CACHE[key]
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    cx, cy = size // 2, int(size * 0.42)
    R = int(size * 0.36)
    pts = [(cx + R * math.cos(math.radians(60 * i)),
            cy + R * math.sin(math.radians(60 * i))) for i in range(6)]
    pygame.draw.polygon(surf, (70, 104, 64), pts)          # land green
    pygame.draw.polygon(surf, (224, 182, 82), pts, 3)      # gold rim

    gold = _scaled(_load(_asset('img', 'dialogue_box', 'icons', 'gold.png')),
                   int(size * 0.26))
    if gold:
        surf.blit(gold, gold.get_rect(center=(cx, cy - int(size * 0.04))))
    font = settings.get_font(getattr(settings, 'FS_TINY', 16), bold=True)
    rate = font.render('gold / hour', True, (255, 244, 210))
    surf.blit(rate, rate.get_rect(center=(cx, cy + int(size * 0.16))))
    tier = font.render('Tiers 1–6 · harder = richer', True, (235, 222, 190))
    surf.blit(tier, tier.get_rect(center=(cx, int(size * 0.92))))
    _CACHE[key] = surf
    return surf


def _hex_points(cx, cy, R):
    return [(cx + R * math.cos(math.radians(60 * i)),
             cy + R * math.sin(math.radians(60 * i))) for i in range(6)]


def _label_below(surf, text, color=(235, 222, 190), bold=False):
    """Stack a caption under a surface, centered."""
    font = settings.get_font(getattr(settings, 'FS_TINY', 16), bold=bold)
    lbl = font.render(text, True, color)
    gap = max(3, int(0.006 * settings.SCREEN_HEIGHT))
    w = max(surf.get_width(), lbl.get_width())
    out = pygame.Surface((w, surf.get_height() + gap + lbl.get_height()), pygame.SRCALPHA)
    out.blit(surf, surf.get_rect(midtop=(w // 2, 0)))
    out.blit(lbl, lbl.get_rect(midtop=(w // 2, surf.get_height() + gap)))
    return out


def _hex_tile(size, fill, rim, *, glow=False, icon_file=None, glyph=None):
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    cx = cy = size // 2
    R = int(size * 0.44)
    if glow:
        pygame.draw.polygon(surf, (255, 214, 110, 70), _hex_points(cx, cy, int(R * 1.16)))
    pygame.draw.polygon(surf, fill, _hex_points(cx, cy, R))
    pygame.draw.polygon(surf, rim, _hex_points(cx, cy, R), 3)
    if icon_file:
        ic = _scaled(_load(_asset('img', 'resource_icons', icon_file)), int(R * 0.85))
        if ic is None:
            ic = _scaled(_load(_asset('img', 'dialogue_box', 'icons', icon_file)), int(R * 0.85))
        if ic:
            surf.blit(ic, ic.get_rect(center=(cx, cy)))
    if glyph:
        gf = settings.get_font(int(size * 0.4), bold=True)
        gs = gf.render(glyph, True, (255, 244, 210))
        surf.blit(gs, gs.get_rect(center=(cx, cy)))
    return surf


def map_legend_diagram(target_h=None):
    """Kingdom window: read the map — your land, the target, a rival."""
    _SH = settings.SCREEN_HEIGHT
    size = int(target_h or 0.16 * _SH)
    key = ('maplegend', size)
    if key in _CACHE:
        return _CACHE[key]
    tiles = [
        _label_below(_hex_tile(size, (74, 116, 196), (235, 220, 150),
                               icon_file='castle.png'), 'Your land', bold=True),
        _label_below(_hex_tile(size, (70, 120, 70), (255, 224, 120), glow=True,
                               icon_file='gold.png'), 'Target', bold=True),
        _label_below(_hex_tile(size, (150, 74, 70), (150, 140, 130), glyph='?'),
                     'Rival', bold=True),
    ]
    gap = int(0.02 * settings.SCREEN_WIDTH)
    total_w = sum(t.get_width() for t in tiles) + gap * (len(tiles) - 1)
    h = max(t.get_height() for t in tiles)
    surf = pygame.Surface((total_w, h), pygame.SRCALPHA)
    x = 0
    for t in tiles:
        surf.blit(t, (x, 0))
        x += t.get_width() + gap
    _CACHE[key] = surf
    return surf


def growth_loop_diagram(target_h=None):
    """Kingdom window: conquer -> produce gold -> grow -> repeat."""
    _SH = settings.SCREEN_HEIGHT
    chip = int(target_h or 0.11 * _SH)
    key = ('growthloop', chip)
    if key in _CACHE:
        return _CACHE[key]
    steps = [
        (_load(_asset('img', 'resource_icons', 'sword.png')), 'Conquer'),
        (_load(_asset('img', 'dialogue_box', 'icons', 'gold.png')), 'Produce'),
        (_load(_asset('img', 'dialogue_box', 'icons', 'booster_pack.png')), 'Grow'),
    ]
    cells = [_label_below(_chip(icon, chip), lbl, bold=True) for icon, lbl in steps]
    arrow_w = int(0.04 * settings.SCREEN_WIDTH)
    cell_h = max(c.get_height() for c in cells)
    total_w = sum(c.get_width() for c in cells) + arrow_w * (len(cells) - 1)
    extra = int(0.05 * _SH)  # room for the return loop arrow
    surf = pygame.Surface((total_w, cell_h + extra), pygame.SRCALPHA)
    cy = chip // 2
    xs = []
    x = 0
    for i, c in enumerate(cells):
        surf.blit(c, (x, 0))
        xs.append((x, x + c.get_width()))
        x += c.get_width()
        if i < len(cells) - 1:
            _draw_arrow(surf, (x + 4, cy), (x + arrow_w - 4, cy))
            x += arrow_w
    # Return loop arrow from last chip back to the first, under the row.
    ry = cell_h + int(0.02 * _SH)
    start = (xs[-1][0] + chip // 2, cy + chip // 2)
    pygame.draw.line(surf, (230, 200, 120), start, (start[0], ry), 3)
    pygame.draw.line(surf, (230, 200, 120), (start[0], ry),
                     (xs[0][0] + chip // 2, ry), 3)
    _draw_arrow(surf, (xs[0][0] + chip // 2, ry),
                (xs[0][0] + chip // 2, cy + chip // 2))
    _CACHE[key] = surf
    return surf


def attack_defend_diagram(target_h=None):
    """Kingdom window: you attack rival lands; rivals attack yours, so you
    defend. Warriors -> land <- Tower."""
    _SH = settings.SCREEN_HEIGHT
    target_h = int(target_h or 0.16 * _SH)
    key = ('attackdefend', target_h)
    if key in _CACHE:
        return _CACHE[key]
    warriors = field_figure_icon('Gorkha Warriors', 'army1.png', label='', target_h=target_h)
    tower = field_figure_icon('Wooden Fortress', 'fortress1.png', label='', target_h=target_h)
    land = _hex_tile(int(target_h * 0.92), (70, 104, 64), (224, 182, 82), icon_file='gold.png')
    sword = _scaled(_load(_asset('img', 'resource_icons', 'sword.png')), int(target_h * 0.3))
    shield = _scaled(_load(_asset('img', 'resource_icons', 'shield.png')), int(target_h * 0.3))
    gap = int(0.012 * settings.SCREEN_WIDTH)
    parts = [warriors, sword, land, shield, tower]
    parts = [p for p in parts if p]
    total_w = sum(p.get_width() for p in parts) + gap * (len(parts) - 1)
    h = max(p.get_height() for p in parts)
    surf = pygame.Surface((total_w, h), pygame.SRCALPHA)
    x = 0
    for p in parts:
        surf.blit(p, (x, (h - p.get_height()) // 2))
        x += p.get_width() + gap
    _CACHE[key] = surf
    return surf


def starter_set_breakdown(kind, suit, target_h=None):
    """Window 5: the granted cards mapped to the figures / spell / tactics
    they build (offensive or defensive set)."""
    if kind == 'offensive':
        entries = [
            {'cards': [('K', suit)], 'kind': 'figure', 'ref': 'Djungle King',
             'label': 'King'},
            {'cards': [('J', suit), ('7', suit)], 'kind': 'figure',
             'ref': 'Small Rice Farm', 'label': 'Farm'},
            {'cards': [('A', suit), ('7', suit)], 'kind': 'figure',
             'ref': 'Gorkha Warriors', 'label': 'Warriors'},
            {'cards': [('8', suit)], 'kind': 'spell', 'ref': 'Draw 2 MainCards',
             'label': 'Prelude'},
            {'cards': [('8', suit), ('9', suit), ('10', suit)], 'kind': 'dagger',
             'ref': None, 'label': '3 Daggers'},
        ]
    else:
        entries = [
            {'cards': [('K', suit)], 'kind': 'figure', 'ref': 'Himalaya King',
             'label': 'King'},
            {'cards': [('J', suit), ('7', suit)], 'kind': 'figure',
             'ref': 'Small Yack Farm', 'label': 'Farm'},
            {'cards': [('A', suit), ('7', suit)], 'kind': 'figure',
             'ref': 'Wooden Fortress', 'label': 'Fortress'},
            {'cards': [('8', suit), ('9', suit), ('10', suit)], 'kind': 'dagger',
             'ref': None, 'label': '3 Daggers'},
        ]
    return _recipe_diagram(('starter_breakdown', kind, suit, int(target_h or 0)),
                           entries, target_h)


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
