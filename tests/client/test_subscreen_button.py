# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Characterization coverage for sub-screen tab buttons."""

import pickle
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pygame


def _button_without_assets(*, disabled):
    from utils.utils import SubScreenButton

    button = SubScreenButton.__new__(SubScreenButton)
    button.disabled = disabled
    button.hovered = True
    button.clicked = True
    button.collide = MagicMock(return_value=True)
    return button


def test_legacy_subscreen_button_import_reexports_canonical_class():
    from game.components.buttons.subscreen_button import (
        SubScreenButton as CanonicalSubScreenButton,
    )
    from utils.utils import SubScreenButton as LegacySubScreenButton

    assert LegacySubScreenButton is CanonicalSubScreenButton
    assert CanonicalSubScreenButton.__module__ == 'utils.utils'
    assert (
        pickle.loads(pickle.dumps(CanonicalSubScreenButton))
        is CanonicalSubScreenButton
    )


def test_disabled_subscreen_button_clears_state_but_runs_feedback_hooks():
    from utils.utils import SubScreenButton

    button = _button_without_assets(disabled=True)
    haptics = SimpleNamespace(tap_edge=MagicMock())
    sound = SimpleNamespace(tap_edge=MagicMock())

    with patch.dict(SubScreenButton.update.__globals__, {
        '_get_pressed': lambda: (1, 0, 0),
        'haptics': haptics,
        'sound': sound,
    }):
        button.update()

    assert button.hovered is False
    assert button.clicked is False
    button.collide.assert_not_called()
    haptics.tap_edge.assert_called_once_with(button)
    sound.tap_edge.assert_called_once_with(button)


def test_enabled_subscreen_button_tracks_hover_and_pressed_state():
    from utils.utils import SubScreenButton

    button = _button_without_assets(disabled=False)
    haptics = SimpleNamespace(tap_edge=MagicMock())
    sound = SimpleNamespace(tap_edge=MagicMock())

    with patch.dict(SubScreenButton.update.__globals__, {
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
    from utils.utils import SubScreenButton

    button = SubScreenButton.__new__(SubScreenButton)
    button.rect = pygame.Rect(100, 100, 20, 20)
    globals_ = SubScreenButton.collide.__globals__

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
