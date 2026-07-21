# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Field figure info-badge layout: full info stays visible on mobile."""

from types import SimpleNamespace

import pygame


def _make_field_icon(skills, max_info_width):
    """Build a minimal FieldFigureIcon wired for draw_figure_info()."""
    from config import settings
    from game.components.figures.figure_icon import FieldFigureIcon

    icon = FieldFigureIcon.__new__(FieldFigureIcon)
    icon.window = pygame.Surface((600, 400), pygame.SRCALPHA)
    icon.figure = SimpleNamespace(
        name='Guard',
        get_value=lambda: 8,
        get_active_skill_keys=lambda: list(skills),
        active_enchantments=[],
        family=SimpleNamespace(field='military'),
        cards=[],
    )
    icon.is_visible = True
    icon.hovered = False
    icon.clicked = False
    icon.icon_scale_factor = 1.3
    font = settings.get_font(settings.FS_SMALL)
    icon.font = font
    icon.font_big = font
    icon.max_info_width = max_info_width

    def _sq(size, colour=(100, 180, 220)):
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        surf.fill(colour)
        return surf

    icon.skill_icons = {key: _sq(18) for key in skills}
    icon.skill_icons_big = dict(icon.skill_icons)
    glow = _sq(22, (255, 255, 255))
    icon.skill_glow = glow
    icon.skill_glow_big = glow
    icon.advantage_suit_icon = None
    icon.advantage_suit_icon_big = None
    icon.own_suit_icon = None
    icon.own_suit_icon_big = None
    suit = _sq(18, (200, 60, 60))
    icon.suit_icon = suit
    icon.suit_icon_big = suit
    icon.buffs_allies_bonus = 0
    icon.buffs_allies_defence_bonus = 0
    icon.battle_bonus_blocked = False
    icon.distance_attack_penalty = 0
    icon.x = 300
    icon.y = 150
    icon._current_battle_bonus_received = lambda: 0
    return icon


def test_info_badge_single_row_without_width_cap():
    icon = _make_field_icon(['k1', 'k2', 'k3'], max_info_width=None)
    icon.draw_figure_info()
    metrics = icon._last_info_metrics
    assert metrics['rows'] == 1
    assert metrics['widest_row_w'] <= metrics['inner_w']


def test_info_badge_wraps_so_nothing_is_truncated_under_mobile_cap():
    icon = _make_field_icon(['k1', 'k2', 'k3'], max_info_width=70)
    icon.draw_figure_info()
    metrics = icon._last_info_metrics
    # The single row would have overflowed the cap ...
    assert metrics['single_row_w'] > metrics['inner_w']
    # ... so it wrapped, and every wrapped row now fits inside the badge.
    assert metrics['rows'] >= 2
    assert metrics['widest_row_w'] <= metrics['inner_w']


def test_info_badge_wraps_many_skills_across_multiple_rows():
    icon = _make_field_icon(['k1', 'k2', 'k3', 'k4', 'k5'], max_info_width=55)
    icon.draw_figure_info()
    metrics = icon._last_info_metrics
    assert metrics['rows'] >= 3
    # Full info remains visible: no row exceeds the badge inner width.
    assert metrics['widest_row_w'] <= metrics['inner_w']


def test_info_row_width_and_wrap_helpers():
    from game.components.figures.figure_icon import FieldFigureIcon

    noop = lambda x, cy: None
    elements = [(10, 8, noop), (10, 8, noop), (10, 8, noop)]
    # 3 * 10 + 2 * spacing(4) = 38
    assert FieldFigureIcon._info_row_width(elements, 4) == 38
    assert FieldFigureIcon._info_row_width([], 4) == 0

    # Cap of 24 -> two per row (10 + 4 + 10 = 24 fits; adding a third overflows).
    rows = FieldFigureIcon._wrap_info_rows(elements, 24, 4)
    assert [len(r) for r in rows] == [2, 1]
    # An oversized element still gets its own row rather than being dropped.
    big = FieldFigureIcon._wrap_info_rows([(50, 8, noop)], 24, 4)
    assert len(big) == 1


def test_info_badge_draw_row_lays_elements_left_to_right_centered():
    from game.components.figures.figure_icon import FieldFigureIcon

    icon = FieldFigureIcon.__new__(FieldFigureIcon)
    icon.x = 100
    drawn = []
    elements = [
        (10, 8, lambda x, cy: drawn.append(('a', x, cy))),
        (20, 8, lambda x, cy: drawn.append(('b', x, cy))),
    ]
    icon._draw_info_row(elements, center_y=50, spacing=4)
    # Row width = 10 + 4 + 20 = 34, centred on x=100 -> starts at 83.
    assert drawn == [('a', 83, 50), ('b', 97, 50)]
