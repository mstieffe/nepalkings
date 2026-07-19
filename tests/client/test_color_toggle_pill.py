# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Characterization coverage for the figure-colour toggle pill."""

import pickle
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pygame


def test_legacy_color_toggle_import_reexports_canonical_class():
    from game.components.buttons.color_toggle_pill import (
        ColorTogglePill as CanonicalColorTogglePill,
    )
    from utils.utils import ColorTogglePill as LegacyColorTogglePill

    assert LegacyColorTogglePill is CanonicalColorTogglePill
    assert CanonicalColorTogglePill.__module__ == 'utils.utils'
    assert (
        pickle.loads(pickle.dumps(CanonicalColorTogglePill))
        is CanonicalColorTogglePill
    )


def test_constructor_preserves_model_label_display_label_and_faction_dot():
    from utils.utils import ColorTogglePill

    button = ColorTogglePill(
        pygame.Surface((200, 100)),
        10,
        20,
        'Djungle',
        display_text='Djungle Attack',
    )
    fallback = ColorTogglePill(
        pygame.Surface((200, 100)),
        10,
        20,
        'Unknown',
    )

    assert button.text == 'Djungle'
    assert button.display_text == 'Djungle Attack'
    assert button._dot_clr == (80, 180, 80)
    assert fallback.display_text == 'Unknown'
    assert fallback._dot_clr is None


def test_update_tracks_pressed_integer_and_runs_feedback_hooks():
    from utils.utils import ColorTogglePill

    button = ColorTogglePill.__new__(ColorTogglePill)
    button.collide = MagicMock(return_value=True)
    button.hovered = False
    button.clicked = False
    haptics = SimpleNamespace(tap_edge=MagicMock())
    sound = SimpleNamespace(tap_edge=MagicMock())

    with patch.dict(ColorTogglePill.update.__globals__, {
        '_get_pressed': lambda: (1, 0, 0),
        'haptics': haptics,
        'sound': sound,
    }):
        button.update()

    assert button.hovered is True
    assert button.clicked == 1
    button.collide.assert_called_once_with()
    haptics.tap_edge.assert_called_once_with(button)
    sound.tap_edge.assert_called_once_with(button)


def test_mobile_hit_padding_expands_vertically_but_not_horizontally():
    from utils.utils import ColorTogglePill

    button = ColorTogglePill.__new__(ColorTogglePill)
    button.rect = pygame.Rect(100, 100, 20, 20)
    globals_ = ColorTogglePill.collide.__globals__

    with (
        patch.object(globals_['settings'], 'TOUCH_HIT_PAD', 8),
        patch.object(
            globals_['pygame'].mouse,
            'get_pos',
            side_effect=[(99, 110), (110, 95)],
        ),
    ):
        assert button.collide() is False
        assert button.collide() is True
