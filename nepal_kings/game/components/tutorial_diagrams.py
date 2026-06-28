# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Runtime-composed teaching diagrams for the tutorial windows.

Each diagram is built once from existing art (suit icons, card images, field
slot icons) and cached. Asset loads are guarded so a missing file degrades to a
smaller/partial diagram rather than crashing the onboarding.
"""

import contextlib
import math
import os

import pygame

from config import settings

_CACHE = {}

# Supersample diagrams on large (desktop) canvases: compose at a higher internal
# resolution and downscale once, so the raster art (cards, figure frames) keeps
# its detail instead of looking soft. Small mobile canvases are already sharp and
# skip this to avoid the extra memory/CPU.
DIAGRAM_SUPERSAMPLE = 1 if getattr(settings, 'TOUCH_TARGET_MIN', 0) > 0 else 2


@contextlib.contextmanager
def _supersampled_metrics(factor):
    """Temporarily scale every size source a diagram reads — the screen
    dimensions AND the fonts — by ``factor`` so the whole composition (art and
    text) grows uniformly. Restored on exit.

    Fonts matter because diagram labels are sized off fixed ``FS_*`` constants,
    not the live screen height; scaling the canvas alone would leave the text
    behind and it would shrink when the result is downscaled.
    """
    sw, sh = settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT
    base_get_font = settings.get_font
    settings.SCREEN_WIDTH = int(sw * factor)
    settings.SCREEN_HEIGHT = int(sh * factor)
    settings.get_font = lambda size, bold=False: base_get_font(
        max(1, int(round(size * factor))), bold=bool(bold))
    try:
        yield
    finally:
        settings.SCREEN_WIDTH, settings.SCREEN_HEIGHT = sw, sh
        settings.get_font = base_get_font


def render_supersampled(factory):
    """Compose ``factory()`` at ``DIAGRAM_SUPERSAMPLE`` resolution and downscale
    it once to its natural size for crisper raster art on big canvases.

    ``factory`` is a parameterless callable (the diagram functions read the
    screen size internally). On mobile this is a direct, unscaled call.
    """
    if DIAGRAM_SUPERSAMPLE <= 1:
        return factory()
    with _supersampled_metrics(DIAGRAM_SUPERSAMPLE):
        hi = factory()
    if not isinstance(hi, pygame.Surface):
        return hi
    factor = DIAGRAM_SUPERSAMPLE
    w = max(1, int(round(hi.get_width() / factor)))
    h = max(1, int(round(hi.get_height() / factor)))
    return pygame.transform.smoothscale(hi, (w, h))

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


def suit_roulette_diagram(target_h=None):
    """The four suit icons with a glowing '?' disc overlaid — the random
    starter suit, about to be drawn."""
    _SH = settings.SCREEN_HEIGHT
    size = int(target_h or 0.22 * _SH)
    key = ('suitroulette', size)
    if key in _CACHE:
        return _CACHE[key]
    surf = pygame.Surface((size, size), pygame.SRCALPHA)
    icon = int(size * 0.42)
    cx = cy = size // 2
    off = int(icon * 0.56)
    positions = {
        'Hearts': (cx - off, cy - off),
        'Diamonds': (cx + off, cy - off),
        'Clubs': (cx - off, cy + off),
        'Spades': (cx + off, cy + off),
    }
    for suit, (px, py) in positions.items():
        ic = _suit_icon(suit, icon)
        if ic:
            surf.blit(ic, ic.get_rect(center=(px, py)))
    # Central glowing '?' disc overlaying the suits.
    r = int(size * 0.21)
    disc = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
    pygame.draw.circle(disc, (255, 214, 110, 60), (r, r), r)
    pygame.draw.circle(disc, (26, 22, 14, 235), (r, r), int(r * 0.82))
    pygame.draw.circle(disc, (224, 182, 82), (r, r), int(r * 0.82), 3)
    qf = settings.get_font(int(r * 1.3), bold=True)
    q = qf.render('?', True, (240, 210, 140))
    disc.blit(q, q.get_rect(center=(r, r)))
    surf.blit(disc, disc.get_rect(center=(cx, cy)))
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
    """Two single Daggers combine into one larger Double Dagger (icons only)."""
    _SH = settings.SCREEN_HEIGHT
    target_h = int(target_h or 0.18 * _SH)
    key = ('daggers', target_h)
    if key in _CACHE:
        return _CACHE[key]
    box = int(target_h * 0.60)
    big = int(target_h * 0.92)
    d1 = _dagger_chip(box)
    d2 = _dagger_chip(box)
    combined = _dagger_chip(big)
    plus_font = settings.get_font(getattr(settings, 'FS_HEADING', 28), bold=True)
    plus = plus_font.render('+', True, (235, 222, 190))
    label_font = settings.get_font(getattr(settings, 'FS_TINY', 16), bold=True)
    label = label_font.render('Double Dagger', True, (235, 222, 190))
    gap = int(0.012 * settings.SCREEN_WIDTH)
    arrow_w = int(0.06 * settings.SCREEN_WIDTH)
    label_gap = max(3, int(0.005 * _SH))

    total_w = box + gap + plus.get_width() + gap + box + arrow_w + big
    h = big + label_gap + label.get_height()
    surf = pygame.Surface((total_w, h), pygame.SRCALPHA)
    cy = big // 2
    x = 0
    surf.blit(d1, (x, cy - box // 2)); x += box + gap
    surf.blit(plus, plus.get_rect(center=(x + plus.get_width() // 2, cy))); x += plus.get_width() + gap
    surf.blit(d2, (x, cy - box // 2)); x += box
    _draw_arrow(surf, (x + gap, cy), (x + arrow_w - gap, cy)); x += arrow_w
    surf.blit(combined, (x, cy - big // 2))
    surf.blit(label, label.get_rect(midtop=(x + big // 2, big + label_gap)))
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


def _battle_move_chip(icon_file, box, accent=(224, 182, 82)):
    """A real battle-move icon (from img/battle/icons) framed in a chip."""
    icon = _load(_asset('img', 'battle', 'icons', icon_file))
    return _chip(icon, box, accent=accent)


def _dagger_chip(box):
    return _battle_move_chip('dagger.png', box, accent=(210, 170, 120))


def _named_skill_chip(skill_key, box, accent=(224, 182, 82)):
    """A figure-skill icon framed in a chip with its name labelled below."""
    defn = {}
    try:
        from game.components.figures.family_configs.skill_config import SKILL_DEFINITIONS
        defn = SKILL_DEFINITIONS.get(skill_key) or {}
    except Exception:
        defn = {}
    rel = defn.get('icon')
    icon = _load(_asset(*rel.split('/'))) if rel else None
    chip = _chip(icon, box, accent=accent)
    name = defn.get('name', '')
    return _label_below(chip, name) if name else chip


def _result_surface(kind, ref, box):
    if kind == 'figure':
        return field_figure_icon(ref, None, label='', target_h=box)
    if kind == 'spell':
        return _spell_chip(ref, box)
    if kind == 'dagger':
        return _dagger_chip(box)
    if kind == 'block':
        # The actual Block battle-move icon.
        return _battle_move_chip('block.png', box, accent=(130, 178, 224))
    if kind == 'call':
        # ``ref`` is the battle-move icon file (castle/village/military.png).
        return _battle_move_chip(ref, box, accent=(224, 182, 82))
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
    """Welcome window 3: an offensive figure (Warriors) vs a defensive one
    (Wooden Fortress), each shown with a representative skill so the suit→skill
    split is concrete — Hearts/Diamonds lean offensive, Clubs/Spades defensive."""
    _SH = settings.SCREEN_HEIGHT
    target_h = int(target_h or 0.18 * _SH)
    key = ('off_vs_def', target_h)
    if key in _CACHE:
        return _CACHE[key]
    header_font = settings.get_font(getattr(settings, 'FS_SMALL', 18), bold=True)
    icon_h = int(target_h * 0.70)
    chip_box = int(target_h * 0.30)
    header_gap = max(4, int(0.01 * _SH))
    row_gap = max(4, int(0.012 * _SH))

    def column(field_name, header_color, fam, fb, lbl, skill_key):
        icon = field_figure_icon(fam, fb, label=lbl, target_h=icon_h)
        header = header_font.render(field_name, True, header_color)
        skill = _named_skill_chip(skill_key, chip_box, accent=header_color)
        col_w = max(icon.get_width(), header.get_width(), skill.get_width())
        col_h = (header.get_height() + header_gap + icon.get_height()
                 + row_gap + skill.get_height())
        col = pygame.Surface((col_w, col_h), pygame.SRCALPHA)
        y = 0
        col.blit(header, header.get_rect(midtop=(col_w // 2, y)))
        y += header.get_height() + header_gap
        col.blit(icon, icon.get_rect(midtop=(col_w // 2, y)))
        y += icon.get_height() + row_gap
        col.blit(skill, skill.get_rect(midtop=(col_w // 2, y)))
        return col

    left = column('OFFENSIVE', (232, 138, 120), 'Gorkha Warriors', 'army1.png',
                  'Warriors', 'distance_attack')
    right = column('DEFENSIVE', (130, 178, 224), 'Wooden Fortress', 'fortress1.png',
                   'Fortress', 'buffs_allies_defence')
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
    """Collection basics: a figure, a spell, and a tactic recipe example."""
    entries = [
        {'cards': [('J', 'Hearts'), ('10', 'Hearts')], 'kind': 'figure',
         'ref': 'Small Rice Farm', 'label': 'Rice Farm (figure)'},
        {'cards': [('3', 'Hearts'), ('3', 'Hearts')], 'kind': 'spell',
         'ref': 'Health Boost', 'label': 'Health Boost (spell)'},
        {'cards': [('Q', 'Hearts')], 'kind': 'block',
         'ref': None, 'label': 'Block (tactic)'},
    ]
    return _recipe_diagram(('recipe_examples', int(target_h or 0)), entries, target_h)


def card_rarity_code_diagram(target_h=None):
    """Collection basics: real cards with the collection rarity colour code."""
    _SH = settings.SCREEN_HEIGHT
    card_h = int(target_h or 0.14 * _SH)
    key = ('card_rarity_code', card_h)
    if key in _CACHE:
        return _CACHE[key]

    label_font = settings.get_font(getattr(settings, 'FS_SMALL', 18), bold=True)
    color_font = settings.get_font(getattr(settings, 'FS_TINY', 16))
    pad = max(5, int(0.006 * _SH))
    line_gap = max(3, int(0.004 * _SH))
    entries = [
        ('7', 1, 'Common', 'Grey'),
        ('J', 2, 'Uncommon', 'Orange'),
        ('K', 3, 'Rare', 'Gold'),
    ]

    cols = []
    for rank, tier, rarity, color_name in entries:
        card = _card_surface('Hearts', rank, card_h)
        border = settings.COLLECTION_TIER_BORDER_COLORS.get(
            tier, (180, 180, 180, 160))
        label_color = settings.COLLECTION_TIER_COLORS.get(tier, (235, 222, 190))
        framed = pygame.Surface(
            (card.get_width() + pad * 2, card.get_height() + pad * 2),
            pygame.SRCALPHA,
        )
        framed.blit(card, (pad, pad))
        pygame.draw.rect(
            framed,
            border,
            framed.get_rect(),
            3 if tier >= 2 else 2,
            border_radius=6,
        )
        rarity_label = label_font.render(rarity, True, label_color)
        color_label = color_font.render(color_name, True, (235, 222, 190))
        col_w = max(framed.get_width(), rarity_label.get_width(),
                    color_label.get_width())
        col_h = (framed.get_height() + line_gap + rarity_label.get_height()
                 + color_label.get_height())
        col = pygame.Surface((col_w, col_h), pygame.SRCALPHA)
        y = 0
        col.blit(framed, framed.get_rect(midtop=(col_w // 2, y)))
        y += framed.get_height() + line_gap
        col.blit(rarity_label, rarity_label.get_rect(midtop=(col_w // 2, y)))
        y += rarity_label.get_height()
        col.blit(color_label, color_label.get_rect(midtop=(col_w // 2, y)))
        cols.append(col)

    gap = int(0.022 * settings.SCREEN_WIDTH)
    total_w = sum(c.get_width() for c in cols) + gap * (len(cols) - 1)
    total_h = max(c.get_height() for c in cols)
    surf = pygame.Surface((total_w, total_h), pygame.SRCALPHA)
    x = 0
    for col in cols:
        surf.blit(col, (x, (total_h - col.get_height()) // 2))
        x += col.get_width() + gap
    _CACHE[key] = surf
    return surf


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


def kingdom_map_diagram(target_h=None):
    """'Read your map': a small kingdom of owned lands, the neighbour you take
    next, and a rival beyond — an arrow shows that conquering neighbours grows
    the kingdom."""
    _SH = settings.SCREEN_HEIGHT
    size = int(target_h or 0.22 * _SH)
    key = ('kingdommap', size)
    if key in _CACHE:
        return _CACHE[key]
    R = size * 0.30
    dy = R * math.sqrt(3) / 2.0
    owned = [(0.0, 0.0), (1.5 * R, -dy), (1.5 * R, dy)]
    target = (3.0 * R, 0.0)
    rival = (4.5 * R, dy)
    all_c = owned + [target, rival]
    min_x = min(c[0] for c in all_c) - R
    max_x = max(c[0] for c in all_c) + R
    min_y = min(c[1] for c in all_c) - dy
    max_y = max(c[1] for c in all_c) + dy
    pad = max(6, int(R * 0.3))
    label_font = settings.get_font(getattr(settings, 'FS_TINY', 16), bold=True)
    field_w, field_h = int(max_x - min_x), int(max_y - min_y)
    w = field_w + pad * 2
    h = field_h + pad * 2 + label_font.get_height() + 4
    surf = pygame.Surface((max(1, w), max(1, h)), pygame.SRCALPHA)

    def P(c):
        return (int(c[0] - min_x + pad), int(c[1] - min_y + pad))

    for c in owned:
        pygame.draw.polygon(surf, (74, 116, 196), _hex_points(*P(c), R))
    pygame.draw.polygon(surf, (255, 214, 110, 70), _hex_points(*P(target), R * 1.14))
    pygame.draw.polygon(surf, (70, 120, 70), _hex_points(*P(target), R))
    pygame.draw.polygon(surf, (150, 74, 70), _hex_points(*P(rival), R))
    rim_w = max(2, int(R * 0.12))
    for c in owned:
        pygame.draw.polygon(surf, (235, 220, 150), _hex_points(*P(c), R), rim_w)
    pygame.draw.polygon(surf, (255, 224, 120), _hex_points(*P(target), R), rim_w)
    pygame.draw.polygon(surf, (170, 150, 140), _hex_points(*P(rival), R), rim_w)

    crown = _scaled(_load(_asset('img', 'kingdom', 'ranking', 'kingdom_gold.png')),
                    int(R * 0.85))
    if crown:
        surf.blit(crown, crown.get_rect(center=P(owned[0])))
    gold = _scaled(_load(_asset('img', 'dialogue_box', 'icons', 'gold.png')), int(R * 0.7))
    if gold:
        surf.blit(gold, gold.get_rect(center=P(target)))
    qf = settings.get_font(max(10, int(R * 0.8)), bold=True)
    q = qf.render('?', True, (255, 244, 210))
    surf.blit(q, q.get_rect(center=P(rival)))

    # Expansion arrow: from the kingdom edge into the next land.
    _draw_arrow(surf, P((1.5 * R + R * 0.45, dy * 0.45)), P((3.0 * R - R * 0.6, 0.0)))

    ly = field_h + pad * 2 + 2
    for text, col, cx in (('Your kingdom', (235, 220, 150), 0.75 * R),
                          ('Next', (255, 224, 120), target[0]),
                          ('Rival', (210, 150, 140), rival[0])):
        s = label_font.render(text, True, col)
        surf.blit(s, s.get_rect(midtop=(int(cx - min_x + pad), ly)))
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
    top_extra = int(0.06 * _SH)  # headroom so the return loop clears the labels
    total_w = sum(c.get_width() for c in cells) + arrow_w * (len(cells) - 1)
    surf = pygame.Surface((total_w, top_extra + cell_h), pygame.SRCALPHA)
    icon_cy = top_extra + chip // 2
    xs = []
    x = 0
    for i, c in enumerate(cells):
        surf.blit(c, (x, top_extra))
        xs.append((x + c.get_width() // 2))
        x += c.get_width()
        if i < len(cells) - 1:
            _draw_arrow(surf, (x + 4, icon_cy), (x + arrow_w - 4, icon_cy))
            x += arrow_w
    # Return loop routed ABOVE the icons (last icon top -> across -> first icon
    # top), so the line never crosses the Conquer/Produce/Grow labels below.
    col = (230, 200, 120)
    ry = max(3, int(top_extra * 0.4))
    pygame.draw.line(surf, col, (xs[-1], top_extra), (xs[-1], ry), 3)
    pygame.draw.line(surf, col, (xs[-1], ry), (xs[0], ry), 3)
    _draw_arrow(surf, (xs[0], ry), (xs[0], top_extra))
    _CACHE[key] = surf
    return surf


def attack_defend_diagram(target_h=None):
    """Kingdom window: you attack rival lands; rivals attack yours, so you
    defend. Warriors -> land <- Fortress."""
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


def _card_fan(cards_spec, card_h):
    """A small overlapping hand of cards (gentle arc) that reads as a whole
    collection, not a single card."""
    fronts = []
    for (r, s) in cards_spec:
        f = _card_surface(s, r, card_h)
        if f:
            fronts.append(f)
    n = len(fronts)
    if n == 0:
        return pygame.Surface((1, 1), pygame.SRCALPHA)
    cw = fronts[0].get_width()
    step_x = int(cw * 0.52)
    arc = int(card_h * 0.10)
    mid = (n - 1) / 2.0
    total_w = step_x * (n - 1) + cw
    surf = pygame.Surface((total_w, card_h + arc), pygame.SRCALPHA)
    for i, f in enumerate(fronts):
        # Cards toward the centre sit a little higher, like a held hand.
        y = int(arc * (abs(i - mid) / (mid or 1)))
        surf.blit(f, (i * step_x, y))
    return surf


def _hex_cluster(size, icon_file='gold.png',
                 fill=(70, 104, 64), rim=(224, 182, 82)):
    """A honeycomb of adjacent lands (a capital + two neighbours) that reads as
    a small kingdom rather than one hex."""
    R = size / (2 * math.sqrt(3))
    s = R * math.sqrt(3) / 2.0              # half-height of a flat-top hex
    centers = [(0.0, 0.0), (1.5 * R, -s), (1.5 * R, s)]
    min_x, min_y, pad = -R, -2 * s, 1
    w = int(3.5 * R) + pad * 2
    h = int(4 * s) + pad * 2
    surf = pygame.Surface((max(1, w), max(1, h)), pygame.SRCALPHA)
    placed = [(cx - min_x + pad, cy - min_y + pad) for cx, cy in centers]
    for ox, oy in placed:
        pygame.draw.polygon(surf, fill, _hex_points(ox, oy, R))
    for ox, oy in placed:
        pygame.draw.polygon(surf, rim, _hex_points(ox, oy, R), max(2, int(R * 0.1)))
    if icon_file:
        ic = (_scaled(_load(_asset('img', 'resource_icons', icon_file)), int(R * 0.9))
              or _scaled(_load(_asset('img', 'dialogue_box', 'icons', icon_file)), int(R * 0.9)))
        if ic:
            surf.blit(ic, ic.get_rect(center=placed[0]))
    return surf


def kingdom_journey_diagram(target_h=None):
    """Big-picture opener: collection -> figures -> a kingdom of lands -> crown.

    Shows the whole loop ending on the crown, so a new player sees the goal
    ("become King of Nepal") and the path to it in one glance.
    """
    _SH = settings.SCREEN_HEIGHT
    cell = int(target_h or 0.12 * _SH)
    key = ('journey', cell)
    if key in _CACHE:
        return _CACHE[key]

    cards = _card_fan([('K', 'Spades'), ('A', 'Hearts'), ('9', 'Diamonds')],
                      int(cell * 0.92))
    figure = field_figure_icon('Gorkha Warriors', 'army1.png', label='',
                               target_h=cell)
    land = _hex_cluster(cell)
    crown = _scaled(_load(_asset('img', 'kingdom', 'ranking', 'kingdom_gold.png')),
                    cell)
    cells = [
        _label_below(cards, 'Your cards', bold=True),
        _label_below(figure, 'Build figures', bold=True),
        _label_below(land, 'Conquer land', bold=True),
        _label_below(crown if crown else _chip(None, cell), 'Rule Nepal', bold=True),
    ]
    arrow_w = int(0.035 * settings.SCREEN_WIDTH)
    cy = cell // 2  # arrows ride the icon band, above the labels
    total_w = sum(c.get_width() for c in cells) + arrow_w * (len(cells) - 1)
    h = max(c.get_height() for c in cells)
    surf = pygame.Surface((total_w, h), pygame.SRCALPHA)
    x = 0
    for i, c in enumerate(cells):
        surf.blit(c, (x, 0))
        x += c.get_width()
        if i < len(cells) - 1:
            _draw_arrow(surf, (x + 3, cy), (x + arrow_w - 3, cy))
            x += arrow_w
    _CACHE[key] = surf
    return surf


def duel_start_image(target_h=None):
    """Duel intro page 1: generated banner of two kings playing chess."""
    _SH = settings.SCREEN_HEIGHT
    target_h = int(target_h or 0.22 * _SH)
    key = ('duel_start_image', target_h)
    if key in _CACHE:
        return _CACHE[key]
    img = _load(_asset('img', 'tutorial', 'duel_start.png'))
    surf = _scaled(img, target_h) if img else pygame.Surface((1, 1), pygame.SRCALPHA)
    _CACHE[key] = surf
    return surf


def conquer_start_image(target_h=None):
    """Welcome intro: supplied banner for the conquer tutorial start."""
    _SH = settings.SCREEN_HEIGHT
    target_h = int(target_h or 0.22 * _SH)
    key = ('conquer_start_image', target_h)
    if key in _CACHE:
        return _CACHE[key]
    img = _load(_asset('img', 'tutorial', 'conquer_start.png'))
    surf = _scaled(img, target_h) if img else pygame.Surface((1, 1), pygame.SRCALPHA)
    _CACHE[key] = surf
    return surf


def duel_shared_card_pool_image(target_h=None):
    """Duel intro page 3: supplied bitmap of one shared card deck."""
    _SH = settings.SCREEN_HEIGHT
    target_h = int(target_h or 0.22 * _SH)
    key = ('duel_shared_card_pool_image', target_h)
    if key in _CACHE:
        return _CACHE[key]
    img = _load(_asset('img', 'tutorial', 'duel_shared_card_pool.png'))
    if img is None:
        surf = pygame.Surface((1, 1), pygame.SRCALPHA)
    elif img.get_height() > target_h:
        surf = _scaled(img, target_h)
    else:
        surf = img
    _CACHE[key] = surf
    return surf


def _score_chip(text, box, accent=(224, 182, 82)):
    surf = pygame.Surface((box, box), pygame.SRCALPHA)
    r = surf.get_rect()
    pygame.draw.circle(surf, (35, 26, 15, 235), r.center, box // 2)
    pygame.draw.circle(surf, (*accent, 60), r.center, int(box * 0.46))
    pygame.draw.circle(surf, accent, r.center, int(box * 0.43), 3)
    font = settings.get_font(max(14, int(box * 0.42)), bold=True)
    txt = font.render(str(text), True, (255, 244, 210))
    surf.blit(txt, txt.get_rect(center=r.center))
    return surf


def duel_loop_diagram(target_h=None):
    """Duel intro: the long match loop from a shared deck to battle points."""
    _SH = settings.SCREEN_HEIGHT
    cell = int(target_h or 0.12 * _SH)
    key = ('duel_loop', cell)
    if key in _CACHE:
        return _CACHE[key]

    cards = _card_fan([('K', 'Spades'), ('J', 'Hearts'), ('8', 'Diamonds')],
                      int(cell * 0.86))
    figure = field_figure_icon('Gorkha Warriors', 'army1.png', label='', target_h=cell)
    battle = _battle_move_chip('dagger.png', cell, accent=(218, 154, 106))
    points = _score_chip('7', cell)
    cells = [
        _label_below(cards, 'Draw cards', bold=True),
        _label_below(figure, 'Build board', bold=True),
        _label_below(battle, 'Battle', bold=True),
        _label_below(points, 'Points', bold=True),
    ]
    arrow_w = int(0.032 * settings.SCREEN_WIDTH)
    cy = cell // 2
    total_w = sum(c.get_width() for c in cells) + arrow_w * (len(cells) - 1)
    h = max(c.get_height() for c in cells)
    surf = pygame.Surface((total_w, h), pygame.SRCALPHA)
    x = 0
    for i, c in enumerate(cells):
        surf.blit(c, (x, 0))
        x += c.get_width()
        if i < len(cells) - 1:
            _draw_arrow(surf, (x + 3, cy), (x + arrow_w - 3, cy))
            x += arrow_w
    _CACHE[key] = surf
    return surf


def duel_build_battle_diagram(target_h=None):
    """Duel intro: simple cycle between Build and Battle."""
    _SH = settings.SCREEN_HEIGHT
    h = int(target_h or 0.18 * _SH)
    key = ('duel_build_battle', h)
    if key in _CACHE:
        return _CACHE[key]

    w = int(0.42 * settings.SCREEN_WIDTH)
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    font = settings.get_font(getattr(settings, 'FS_HEADING', 28), bold=True)
    label_color = (255, 244, 210)
    node_fill = (32, 25, 16, 238)
    node_border = (224, 182, 82)
    node_w = max(int(w * 0.25), font.size('Battle')[0] + int(0.05 * w))
    node_h = max(int(h * 0.32), font.get_height() + int(0.08 * h))
    build_rect = pygame.Rect(int(w * 0.08), (h - node_h) // 2, node_w, node_h)
    battle_rect = pygame.Rect(w - int(w * 0.08) - node_w, (h - node_h) // 2,
                              node_w, node_h)

    def draw_node(rect, label):
        pygame.draw.rect(surf, node_fill, rect, border_radius=10)
        pygame.draw.rect(surf, node_border, rect, 3, border_radius=10)
        txt = font.render(label, True, label_color)
        surf.blit(txt, txt.get_rect(center=rect.center))

    draw_node(build_rect, 'Build')
    draw_node(battle_rect, 'Battle')

    gap = int(0.018 * settings.SCREEN_WIDTH)
    top_y = h // 2 - int(h * 0.19)
    bottom_y = h // 2 + int(h * 0.19)
    _draw_arrow(
        surf,
        (build_rect.right + gap, top_y),
        (battle_rect.left - gap, top_y),
        color=(235, 202, 112),
        width=max(3, int(h * 0.025)),
        head=max(10, int(h * 0.075)),
    )
    _draw_arrow(
        surf,
        (battle_rect.left - gap, bottom_y),
        (build_rect.right + gap, bottom_y),
        color=(130, 178, 224),
        width=max(3, int(h * 0.025)),
        head=max(10, int(h * 0.075)),
    )
    _CACHE[key] = surf
    return surf


def shared_card_pool_diagram(target_h=None):
    """Duel intro: both players draw from one central card pool."""
    _SH = settings.SCREEN_HEIGHT
    cell = int(target_h or 0.13 * _SH)
    key = ('shared_card_pool', cell)
    if key in _CACHE:
        return _CACHE[key]

    you = _label_below(
        field_figure_icon('Djungle King', 'castle_red.png', label='', target_h=cell),
        'You',
        bold=True,
    )
    pool = _label_below(
        _card_fan([('Q', 'Clubs'), ('9', 'Diamonds'), ('A', 'Spades'), ('J', 'Hearts')],
                  int(cell * 0.86)),
        'Shared pool',
        bold=True,
    )
    opponent = _label_below(
        field_figure_icon('Himalaya King', 'castle_black.png', label='', target_h=cell),
        'Opponent',
        bold=True,
    )
    arrow_w = int(0.05 * settings.SCREEN_WIDTH)
    gap = int(0.006 * settings.SCREEN_WIDTH)
    total_w = you.get_width() + pool.get_width() + opponent.get_width() + arrow_w * 2 + gap * 4
    h = max(you.get_height(), pool.get_height(), opponent.get_height())
    surf = pygame.Surface((total_w, h), pygame.SRCALPHA)
    cy = cell // 2
    x = 0
    surf.blit(you, (x, (h - you.get_height()) // 2))
    x += you.get_width() + gap
    _draw_arrow(surf, (x + arrow_w - 3, cy), (x + 3, cy))
    x += arrow_w + gap
    surf.blit(pool, (x, (h - pool.get_height()) // 2))
    x += pool.get_width() + gap
    _draw_arrow(surf, (x + 3, cy), (x + arrow_w - 3, cy))
    x += arrow_w + gap
    surf.blit(opponent, (x, (h - opponent.get_height()) // 2))
    _CACHE[key] = surf
    return surf


def battle_flow_diagram(target_h=None):
    """Battle window 1: the three beats of a battle, shown as labelled icons —
    the prelude spell (Health Boost), then figures, then three tactic rounds."""
    _SH = settings.SCREEN_HEIGHT
    chip = int(target_h or 0.12 * _SH)
    key = ('battleflow', chip)
    if key in _CACHE:
        return _CACHE[key]
    spell = _spell_chip('Health Boost', chip)
    figure = field_figure_icon('Gorkha Warriors', 'army1.png', label='', target_h=chip)
    tactic = _battle_move_chip('castle.png', chip, accent=(224, 182, 82))
    cells = [
        _label_below(spell, 'Prelude', bold=True),
        _label_below(figure, 'Figures', bold=True),
        _label_below(tactic, 'Tactics ×3', bold=True),
    ]
    arrow_w = int(0.04 * settings.SCREEN_WIDTH)
    cy = chip // 2
    total_w = sum(c.get_width() for c in cells) + arrow_w * (len(cells) - 1)
    h = max(c.get_height() for c in cells)
    surf = pygame.Surface((total_w, h), pygame.SRCALPHA)
    x = 0
    for i, c in enumerate(cells):
        surf.blit(c, (x, 0))
        x += c.get_width()
        if i < len(cells) - 1:
            _draw_arrow(surf, (x + 3, cy), (x + arrow_w - 3, cy))
            x += arrow_w
    _CACHE[key] = surf
    return surf


def battle_matchup_diagram(target_h=None):
    """Battle window 2: your battle figure vs the defender, each with its power
    pill, so 'figure power decides most' reads as a head-to-head matchup."""
    _SH = settings.SCREEN_HEIGHT
    target_h = int(target_h or 0.2 * _SH)
    key = ('matchup', target_h)
    if key in _CACHE:
        return _CACHE[key]
    icon_h = int(target_h * 0.8)
    header_font = settings.get_font(getattr(settings, 'FS_SMALL', 18), bold=True)
    header_gap = max(4, int(0.01 * _SH))

    def column(title, color, fam, fb, lbl):
        icon = field_figure_icon(fam, fb, label=lbl, target_h=icon_h)
        header = header_font.render(title, True, color)
        col_w = max(icon.get_width(), header.get_width())
        col = pygame.Surface((col_w, header.get_height() + header_gap + icon.get_height()),
                             pygame.SRCALPHA)
        col.blit(header, header.get_rect(midtop=(col_w // 2, 0)))
        col.blit(icon, icon.get_rect(midtop=(col_w // 2, header.get_height() + header_gap)))
        return col

    you = column('YOU', (232, 200, 120), 'Gorkha Warriors', 'army1.png', 'Warriors')
    foe = column('DEFENDER', (130, 178, 224), 'Small Yack Farm', 'yack_farm1.png', 'Yack Farm')
    vs_font = settings.get_font(getattr(settings, 'FS_HEADING', 28), bold=True)
    vs = vs_font.render('vs', True, (235, 222, 190))
    gap = int(0.03 * settings.SCREEN_WIDTH)
    total_w = you.get_width() + gap + vs.get_width() + gap + foe.get_width()
    h = max(you.get_height(), foe.get_height())
    surf = pygame.Surface((total_w, h), pygame.SRCALPHA)
    x = 0
    surf.blit(you, (x, 0)); x += you.get_width() + gap
    surf.blit(vs, vs.get_rect(center=(x + vs.get_width() // 2, h // 2))); x += vs.get_width() + gap
    surf.blit(foe, (x, 0))
    _CACHE[key] = surf
    return surf


def starter_tactics_diagram(target_h=None):
    """Battle window 3: the player's three starter tactics as labelled icons —
    Call King, Call Villager, Block."""
    _SH = settings.SCREEN_HEIGHT
    box = int(target_h or 0.13 * _SH)
    key = ('startertactics', box)
    if key in _CACHE:
        return _CACHE[key]
    items = [
        ('castle.png', 'Call King', (224, 182, 82)),
        ('village.png', 'Call Villager', (224, 182, 82)),
        ('block.png', 'Block', (130, 178, 224)),
    ]
    cells = [_label_below(_battle_move_chip(icon, box, accent=accent), label, bold=True)
             for icon, label, accent in items]
    gap = int(0.04 * settings.SCREEN_WIDTH)
    total_w = sum(c.get_width() for c in cells) + gap * (len(cells) - 1)
    h = max(c.get_height() for c in cells)
    surf = pygame.Surface((total_w, h), pygame.SRCALPHA)
    x = 0
    for c in cells:
        surf.blit(c, (x, 0))
        x += c.get_width() + gap
    _CACHE[key] = surf
    return surf


def _breakdown_column(title, items, icon_h, _SH, cards_col=None):
    """A labelled column of ALIGNED recipe rows: cards (right-aligned to a
    shared column) → arrow (shared vertical axis) → a large result icon, with
    the label centred below the icon. ``cards_col`` may be supplied so several
    columns share one arrow axis."""
    header_font = settings.get_font(getattr(settings, 'FS_SMALL', 18), bold=True)
    label_font = settings.get_font(getattr(settings, 'FS_TINY', 16), bold=True)
    gap = max(2, int(0.003 * settings.SCREEN_WIDTH))
    arrow_w = int(0.03 * settings.SCREEN_WIDTH)
    card_h = int(icon_h * 0.62)
    label_gap = max(2, int(0.004 * _SH))
    row_gap = int(0.014 * _SH)
    hgap = max(4, int(0.012 * _SH))

    built = []
    for cards, kind, ref, label in items:
        card_surfs = [_card_surface(s, r, card_h) for (r, s) in cards]
        cards_w = sum(c.get_width() for c in card_surfs) + gap * max(0, len(card_surfs) - 1)
        result = _result_surface(kind, ref, icon_h)
        lbl = label_font.render(label, True, (235, 222, 190))
        built.append((card_surfs, cards_w, result, lbl))

    cards_col = cards_col if cards_col is not None else max(b[1] for b in built)
    result_col = max(b[2].get_width() for b in built)
    arrow_x0 = cards_col + gap
    arrow_x1 = arrow_x0 + arrow_w
    result_x = arrow_x1 + gap
    row_w = result_x + result_col
    # Labels are centred under the (right-side) result icon, so a wide label can
    # overhang the row on either side; size the column to fit that overhang.
    icon_center = result_x + result_col / 2.0
    max_lbl = max(b[3].get_width() for b in built)
    left_overhang = max(0, int(round(max_lbl / 2 - icon_center)))
    right_extent = max(row_w, int(round(icon_center + max_lbl / 2)))
    block_w = left_overhang + right_extent
    header = header_font.render(title, True, (240, 210, 140))
    col_w = max(block_w, header.get_width())
    base_x = (col_w - block_w) // 2 + left_overhang  # row origin (cards left)

    row_heights = [b[2].get_height() + label_gap + b[3].get_height() for b in built]
    total_h = (header.get_height() + hgap + sum(row_heights)
               + row_gap * max(0, len(built) - 1))
    col = pygame.Surface((col_w, total_h), pygame.SRCALPHA)
    col.blit(header, header.get_rect(midtop=(col_w // 2, 0)))
    y = header.get_height() + hgap
    for (card_surfs, cards_w, result, lbl), rh in zip(built, row_heights):
        ih = result.get_height()
        cy = y + ih // 2
        cx = base_x + cards_col - cards_w  # right-align cards to the shared column
        for c in card_surfs:
            col.blit(c, (cx, cy - c.get_height() // 2))
            cx += c.get_width() + gap
        _draw_arrow(col, (base_x + arrow_x0, cy), (base_x + arrow_x1, cy))
        col.blit(result, (base_x + result_x, y))
        col.blit(lbl, lbl.get_rect(
            midtop=(int(base_x + icon_center), y + ih + label_gap)))
        y += rh + row_gap
    return col


def starter_set_breakdown(kind, suit, target_h=None):
    """The granted cards mapped to what they build, in two columns: figures on
    the left, the spell + tactics on the right (icons large, labels below,
    arrows aligned on one axis across both columns)."""
    if kind == 'offensive':
        _SH = settings.SCREEN_HEIGHT
        cache_key = ('starter_breakdown', kind, suit, int(target_h or 0))
        if cache_key in _CACHE:
            return _CACHE[cache_key]
        icon_h = int(target_h or 0.085 * _SH)
        fig_items = [
            ([('K', suit)], 'figure', 'Djungle King', 'King'),
            ([('J', suit), ('10', suit)], 'figure', 'Small Rice Farm', 'Farm'),
            ([('A', suit), ('9', suit)], 'figure', 'Gorkha Warriors', 'Warriors'),
        ]
        tac_items = [
            ([('3', suit), ('3', suit)], 'spell', 'Health Boost', 'Health Boost'),
            ([('K', suit)], 'call', 'castle.png', 'Call King'),
            ([('J', suit)], 'call', 'village.png', 'Call Villager'),
            ([('Q', suit)], 'block', None, 'Block'),
        ]
        # Shared cards column so EVERY arrow (both columns) lands on one axis.
        gap = max(2, int(0.003 * settings.SCREEN_WIDTH))
        card_h = int(icon_h * 0.62)
        cards_col = 0
        for items in (fig_items, tac_items):
            for cards, _k, _r, _l in items:
                cws = [_card_surface(s, r, card_h) for (r, s) in cards]
                cards_col = max(cards_col, sum(c.get_width() for c in cws)
                                + gap * max(0, len(cws) - 1))
        left = _breakdown_column('Figures', fig_items, icon_h, _SH, cards_col)
        right = _breakdown_column('Spell & Tactics', tac_items, icon_h, _SH, cards_col)
        col_gap = int(0.035 * settings.SCREEN_WIDTH)
        w = left.get_width() + col_gap + right.get_width()
        h = max(left.get_height(), right.get_height())
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        surf.blit(left, (0, 0))
        surf.blit(right, (left.get_width() + col_gap, 0))
        _CACHE[cache_key] = surf
        return surf
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
