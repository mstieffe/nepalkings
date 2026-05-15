# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for the kingdom config castle-cap indicator."""

from types import SimpleNamespace

import pygame


def test_castle_cap_state_counts_dict_and_object_figures():
    from game.components.castle_cap_indicator import castle_cap_reached

    figures = [
        {'field': 'castle'},
        SimpleNamespace(family=SimpleNamespace(field='castle')),
        {'field': 'village'},
    ]

    reached, count, cap = castle_cap_reached({'tier': 2}, figures)

    assert reached is True
    assert count == 2
    assert cap == 2


def test_castle_cap_indicator_draws_only_when_full():
    from game.components.castle_cap_indicator import draw_castle_cap_indicator

    surface = pygame.Surface((180, 120), pygame.SRCALPHA)
    rect = pygame.Rect(10, 10, 150, 90)

    assert draw_castle_cap_indicator(surface, rect, 1, 2) is None

    badge = draw_castle_cap_indicator(surface, rect, 2, 2)

    assert badge is not None
    assert rect.contains(badge)
    assert surface.get_bounding_rect().width > 0


def test_castle_cap_indicator_uses_checkmate_skill_icon(monkeypatch):
    from game.components import castle_cap_indicator as module

    loaded_paths = []

    def fake_load(path):
        loaded_paths.append(path)
        icon = pygame.Surface((8, 8), pygame.SRCALPHA)
        icon.fill((80, 200, 240, 255))
        return icon

    module._CHECKMATE_ICON_CACHE.clear()
    monkeypatch.setattr(module.pygame.image, 'load', fake_load)
    monkeypatch.setattr(module.pygame.display, 'get_surface', lambda: None)

    surface = pygame.Surface((180, 120), pygame.SRCALPHA)
    badge = module.draw_castle_cap_indicator(
        surface, pygame.Rect(10, 10, 150, 90), 2, 2)

    assert badge is not None
    assert loaded_paths == [module._CHECKMATE_ICON_PATH]
    assert loaded_paths[0].endswith('img/figures/state_icons/checkmate.png')