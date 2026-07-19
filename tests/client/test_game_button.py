# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Characterization coverage for the shared in-game navigation button."""

import pickle
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def _button_without_assets(*, locked):
    from utils.utils import GameButton

    button = GameButton.__new__(GameButton)
    button.locked = locked
    button.locked_clicked = False
    button.clicked = False
    button.subscreen_trigger = 'battle'
    button.screen_trigger = 'game'
    button.collide = lambda: True
    return button


def test_legacy_game_button_import_reexports_canonical_class():
    from game.components.buttons.game_button import GameButton as CanonicalGameButton
    from utils.utils import GameButton as LegacyGameButton

    assert LegacyGameButton is CanonicalGameButton
    assert CanonicalGameButton.__module__ == 'utils.utils'
    assert pickle.loads(pickle.dumps(CanonicalGameButton)) is CanonicalGameButton


def test_locked_game_button_reports_click_without_navigating_or_feedback():
    from utils.utils import GameButton

    button = _button_without_assets(locked=True)
    state = SimpleNamespace(
        game=SimpleNamespace(turn=True),
        subscreen='field',
        screen='duel',
    )
    haptics = SimpleNamespace(tap_edge=MagicMock())
    sound = SimpleNamespace(tap_edge=MagicMock())

    with patch.dict(GameButton.update.__globals__, {
        '_get_pressed': lambda: (1, 0, 0),
        'haptics': haptics,
        'sound': sound,
    }):
        button.update(state)

    assert button.locked_clicked is True
    assert button.clicked is False
    assert state.subscreen == 'field'
    assert state.screen == 'duel'
    haptics.tap_edge.assert_not_called()
    sound.tap_edge.assert_not_called()


def test_unlocked_game_button_routes_and_runs_feedback_hooks():
    from utils.utils import GameButton

    button = _button_without_assets(locked=False)
    state = SimpleNamespace(
        game=SimpleNamespace(turn=True),
        subscreen='field',
        screen='duel',
    )
    haptics = SimpleNamespace(tap_edge=MagicMock())
    sound = SimpleNamespace(tap_edge=MagicMock())

    with patch.dict(GameButton.update.__globals__, {
        '_get_pressed': lambda: (1, 0, 0),
        'haptics': haptics,
        'sound': sound,
    }):
        button.update(state)

    assert button.clicked is True
    assert state.subscreen == 'battle'
    assert state.screen == 'game'
    haptics.tap_edge.assert_called_once_with(button)
    sound.tap_edge.assert_called_once_with(button)
