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


def _recipe_row(cards, result_surf, label, row_h, label_w):
    """[card][card] → [result] label — one recipe line."""
    label_font = settings.get_font(getattr(settings, 'FS_SMALL', 18))
    lbl = label_font.render(label, True, (235, 222, 190)) if label else None
    card_h = int(row_h * 0.92)
    card_surfs = [_card_surface(s, r, card_h) for (r, s) in cards]
    gap = max(3, int(0.004 * settings.SCREEN_WIDTH))
    arrow_w = int(0.045 * settings.SCREEN_WIDTH)
    cards_w = sum(c.get_width() for c in card_surfs) + gap * max(0, len(card_surfs) - 1)
    res_w = result_surf.get_width() if result_surf else 0
    lbl_gap = int(0.012 * settings.SCREEN_WIDTH)
    total_w = cards_w + arrow_w + res_w + (lbl_gap + label_w if lbl else 0)
    h = max(row_h, result_surf.get_height() if result_surf else 0)
    surf = pygame.Surface((total_w, h), pygame.SRCALPHA)
    cy = h // 2
    x = 0
    for c in card_surfs:
        surf.blit(c, (x, cy - c.get_height() // 2))
        x += c.get_width() + gap
    _draw_arrow(surf, (x + gap, cy), (x + arrow_w - gap, cy))
    x += arrow_w
    if result_surf:
        surf.blit(result_surf, (x, cy - result_surf.get_height() // 2))
        x += res_w + lbl_gap
    if lbl:
        surf.blit(lbl, (x, cy - lbl.get_height() // 2))
    return surf


def _recipe_diagram(cache_key, entries, target_h=None):
    """A vertical stack of recipe rows ([cards] → [result] label)."""
    _SH = settings.SCREEN_HEIGHT
    row_h = int(target_h or 0.072 * _SH)
    if cache_key in _CACHE:
        return _CACHE[cache_key]
    label_font = settings.get_font(getattr(settings, 'FS_SMALL', 18))
    label_w = max((label_font.size(e.get('label', ''))[0] for e in entries), default=0)
    rows = []
    for e in entries:
        result = _result_surface(e['kind'], e['ref'], row_h)
        rows.append(_recipe_row(e['cards'], result, e.get('label', ''), row_h, label_w))
    row_gap = int(0.016 * _SH)
    w = max((r.get_width() for r in rows), default=1)
    h = sum(r.get_height() for r in rows) + row_gap * max(0, len(rows) - 1)
    surf = pygame.Surface((max(1, w), max(1, h)), pygame.SRCALPHA)
    y = 0
    for r in rows:
        surf.blit(r, (0, y))
        y += r.get_height() + row_gap
    _CACHE[cache_key] = surf
    return surf


def card_recipe_examples(target_h=None):
    """Window 1: cards combine into figures AND spells."""
    entries = [
        {'cards': [('K', 'Hearts')], 'kind': 'figure', 'ref': 'Djungle King',
         'label': 'King (figure)'},
        {'cards': [('J', 'Hearts'), ('7', 'Hearts')], 'kind': 'figure',
         'ref': 'Small Rice Farm', 'label': 'Rice Farm (figure)'},
        {'cards': [('A', 'Hearts'), ('7', 'Hearts')], 'kind': 'figure',
         'ref': 'Gorkha Warriors', 'label': 'Warriors (figure)'},
        {'cards': [('3', 'Spades'), ('3', 'Spades')], 'kind': 'spell',
         'ref': 'Poison', 'label': 'Poison (spell)'},
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
