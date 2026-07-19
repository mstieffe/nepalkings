# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Characterization tests for Pygame surface effects."""

import pickle

import pygame


def test_legacy_brighten_import_reexports_canonical_function():
    from game.components.surface_effects import brighten as canonical_brighten
    from utils.utils import brighten as legacy_brighten

    assert legacy_brighten is canonical_brighten
    assert canonical_brighten.__module__ == "utils.utils"
    assert pickle.loads(pickle.dumps(canonical_brighten)) is canonical_brighten


def test_brighten_returns_unlocked_copy_and_preserves_source_and_alpha():
    from utils.utils import brighten

    source = pygame.Surface((2, 1), pygame.SRCALPHA, 32)
    source.set_at((0, 0), (10, 20, 30, 40))
    source.set_at((1, 0), (200, 130, 0, 255))

    result = brighten(source, 1.5)

    assert result is not source
    assert source.get_at((0, 0)) == pygame.Color(10, 20, 30, 40)
    assert source.get_at((1, 0)) == pygame.Color(200, 130, 0, 255)
    assert result.get_at((0, 0)) == pygame.Color(15, 30, 45, 40)
    assert result.get_at((1, 0)) == pygame.Color(255, 195, 0, 255)
    assert result.get_locked() is False


def test_brighten_truncates_fractional_channels():
    from utils.utils import brighten

    source = pygame.Surface((1, 1), pygame.SRCALPHA, 32)
    source.set_at((0, 0), (5, 7, 9, 11))

    result = brighten(source, 0.5)

    assert result.get_at((0, 0)) == pygame.Color(2, 3, 4, 11)
