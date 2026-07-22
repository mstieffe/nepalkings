# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Field figure info-badge layout: full info stays visible on mobile."""

import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pygame


APP_DIR = Path(__file__).resolve().parents[2] / 'nepal_kings'


def _make_field_icon(skills, max_info_width, *, compact=False,
                     battle_bonus=0, buffs_bonus=0, defence_bonus=0,
                     distance_penalty=0, enchantment_modifier=0,
                     visible=True, card_count=0, field='military',
                     game_mode='duel'):
    """Build a minimal FieldFigureIcon wired for draw_figure_info()."""
    from config import settings
    from game.components.figures.figure_icon import FieldFigureIcon

    icon = FieldFigureIcon.__new__(FieldFigureIcon)
    icon.window = pygame.Surface((600, 400), pygame.SRCALPHA)
    icon.game = SimpleNamespace(mode=game_mode)
    enchantments = ([{
        'spell_name': 'Health Boost',
        'spell_icon': 'health_portion.png',
        'power_modifier': enchantment_modifier,
    }] if enchantment_modifier else [])
    icon.figure = SimpleNamespace(
        name='Guard',
        get_value=lambda: 8,
        get_active_skill_keys=lambda: list(skills),
        active_enchantments=enchantments,
        get_total_enchantment_modifier=lambda: enchantment_modifier,
        family=SimpleNamespace(field=field),
        cards=[SimpleNamespace(id=i) for i in range(card_count)],
    )
    icon.is_visible = visible
    icon.hovered = False
    icon.clicked = False
    icon.icon_scale_factor = 1.3
    font = settings.get_font(settings.FS_SMALL)
    icon.font = font
    icon.font_big = font
    icon.max_info_width = max_info_width
    icon.compact_info_badge = compact

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
    card_back = _sq(16, (55, 90, 150))
    icon._card_back_normal = card_back
    icon._card_back_big = card_back
    icon.buffs_allies_bonus = buffs_bonus
    icon.buffs_allies_defence_bonus = defence_bonus
    icon.battle_bonus_blocked = False
    icon.distance_attack_penalty = distance_penalty
    icon.x = 300
    icon.y = 150
    icon._current_battle_bonus_received = lambda: battle_bonus
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


def test_modifier_format_is_compact_only_when_requested():
    from game.components.figures.figure_icon import FieldFigureIcon

    assert FieldFigureIcon._format_info_modifier(6, compact=True) == '+6'
    assert FieldFigureIcon._format_info_modifier(-3, compact=True) == '-3'
    assert FieldFigureIcon._format_info_modifier(6, compact=False) == '(+6)'


def test_compact_card_back_row_shrinks_to_inner_width():
    from game.components.figures.figure_icon import FieldFigureIcon

    size, spacing, width = FieldFigureIcon._fit_compact_card_back_row(
        4, max_width=52, preferred_size=16, preferred_spacing=2)
    assert (size, spacing, width) == (11, 2, 50)
    assert width <= 52


def test_noncompact_capped_badge_keeps_name_and_legacy_punctuation():
    icon = _make_field_icon(
        ['k1'], max_info_width=120, compact=False,
        battle_bonus=2, enchantment_modifier=6)
    icon.draw_figure_info()

    metrics = icon._last_info_metrics
    assert metrics['compact'] is False
    assert metrics['name_visible'] is True
    assert metrics['support_text'] == '(+2)'
    assert metrics['enchantment_text'] == '(+6)'


def test_field_badge_hides_instant_charge_only_in_conquer_mode():
    skills = ['instant_charge', 'distance_attack']
    conquer_icon = _make_field_icon(
        skills, max_info_width=140, game_mode='conquer')
    duel_icon = _make_field_icon(
        skills, max_info_width=140, game_mode='duel')

    conquer_icon.draw_figure_info()
    duel_icon.draw_figure_info()

    assert conquer_icon._last_info_metrics['skills'] == ('distance_attack',)
    assert duel_icon._last_info_metrics['skills'] == (
        'instant_charge', 'distance_attack')


def test_mobile_conquer_badge_stress_case_is_at_most_two_rows():
    code = r'''
import pygame
from tests.client.test_figure_info_badge import _make_field_icon

pygame.init()
pygame.display.set_mode((854, 480))
icon = _make_field_icon(
    ['k1', 'k2'], max_info_width=62, compact=True,
    battle_bonus=2, buffs_bonus=4, enchantment_modifier=6)
icon.draw_figure_info()
metrics = icon._last_info_metrics
assert metrics['rows'] == 2, metrics
assert metrics['name_visible'] is False, metrics
assert metrics['suit_in_metadata'] is True, metrics
assert metrics['power_text'] == '12', metrics
assert metrics['support_text'] == '+2', metrics
assert metrics['enchantment_text'] == '+6', metrics
assert metrics['widest_row_w'] <= metrics['inner_w'], metrics
assert metrics['vertical_nudge'] == 0, metrics

simple = _make_field_icon([], max_info_width=62, compact=True)
simple.draw_figure_info()
simple_metrics = simple._last_info_metrics
assert simple_metrics['rows'] == 1, simple_metrics
assert simple_metrics['vertical_nudge'] >= 4, simple_metrics
assert simple_metrics['info_rect'].top > metrics['info_rect'].top, (
    simple_metrics, metrics)

hidden = _make_field_icon(
    ['k1', 'k2'], max_info_width=62, compact=True,
    visible=False, card_count=4, enchantment_modifier=6)
hidden.draw_figure_info()
hidden_metrics = hidden._last_info_metrics
assert hidden_metrics['rows'] == 1, hidden_metrics
assert hidden_metrics['name_visible'] is False, hidden_metrics
assert hidden_metrics['hidden_card_back_only'] is True, hidden_metrics
assert hidden_metrics['card_back_count'] == 4, hidden_metrics
assert hidden_metrics['widest_row_w'] <= hidden_metrics['inner_w'], hidden_metrics
assert hidden_metrics['vertical_nudge'] >= 4, hidden_metrics
assert hidden_metrics['card_back_vertical_padding'] >= 2, hidden_metrics
assert hidden_metrics['info_rect'].height >= (
    hidden_metrics['card_back_size'] + 4), hidden_metrics

# Hidden figures can enlarge during defender selection.  The backs must be
# recomputed for the narrower big-state inner width rather than overflowing.
hidden.hovered = True
hidden.draw_figure_info()
hover_metrics = hidden._last_info_metrics
assert hover_metrics['card_back_size'] < hidden_metrics['card_back_size'], (
    hover_metrics, hidden_metrics)
assert hover_metrics['widest_row_w'] <= hover_metrics['inner_w'], hover_metrics
assert hover_metrics['info_rect'].height >= (
    hover_metrics['card_back_size'] + 4), hover_metrics
'''
    env = os.environ.copy()
    env.update({
        'SDL_VIDEODRIVER': 'dummy',
        'SDL_AUDIODRIVER': 'dummy',
        'NK_SCREEN_WIDTH': '854',
        'NK_SCREEN_HEIGHT': '480',
        'NK_IS_MOBILE': '1',
        'NK_UI_SCALE': '1.6',
        'PYTHONPATH': os.pathsep.join((str(APP_DIR.parent), str(APP_DIR))),
    })
    result = subprocess.run(
        [sys.executable, '-c', code],
        cwd=APP_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
