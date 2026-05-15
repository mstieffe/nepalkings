# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Regression tests for base Screen control-button event handling."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pygame


def _screen_class():
    from game.screens.screen import Screen

    return Screen


def _make_state(screen_name='defence'):
    state = SimpleNamespace()
    state.screen = screen_name
    state.user = 'player'
    state.user_dict = {'id': 1}
    state.game = object()
    state.pending_spell_cast = {'spell': 'Poison'}
    state.pending_conquer_prelude_target = {'spell_id': 7}
    state._notified_accepted_challenges = {'abc'}
    state._pending_accepted_challenge = 'abc'
    state.action = {'task': 'x', 'content': 'y', 'status': 'z'}
    state.set_msg = MagicMock()
    return state


class _DummyButton:
    def __init__(self, collide_result):
        self._collide_result = collide_result

    def collide(self):
        return self._collide_result


class TestBaseScreenControlButtons:
    def _make_screen(self, state, logout_collide=False, home_collide=False):
        Screen = _screen_class()
        screen = Screen.__new__(Screen)
        screen.state = state
        screen.dialogue_box = None
        screen.logout_button = _DummyButton(logout_collide)
        screen.home_button = _DummyButton(home_collide)
        screen.control_buttons = [screen.logout_button, screen.home_button]
        screen.reset_action = lambda: setattr(state, 'action', {
            'task': None,
            'content': None,
            'status': None,
        })
        return Screen, screen

    def test_disabled_control_buttons_do_not_trigger_hidden_logout(self):
        state = _make_state(screen_name='defence')
        Screen, screen = self._make_screen(state, logout_collide=True)
        screen.control_buttons = []

        Screen.handle_events(screen, [SimpleNamespace(type=pygame.MOUSEBUTTONDOWN)])

        assert state.screen == 'defence'
        assert state.user == 'player'
        assert state.user_dict == {'id': 1}
        assert state.game is not None
        state.set_msg.assert_not_called()

    def test_enabled_legacy_logout_still_works(self):
        state = _make_state(screen_name='defence')
        Screen, screen = self._make_screen(state, logout_collide=True)

        Screen.handle_events(screen, [SimpleNamespace(type=pygame.MOUSEBUTTONDOWN)])

        assert state.screen == 'login'
        assert state.user is None
        assert state.user_dict is None
        assert state.game is None
        assert state.pending_spell_cast is None
        assert state.pending_conquer_prelude_target is None
        assert state._notified_accepted_challenges == set()
        assert state._pending_accepted_challenge is None
        assert state.action == {'task': None, 'content': None, 'status': None}
        state.set_msg.assert_called_once_with('Logged out')

    def test_legacy_controls_are_ignored_on_game_screen(self):
        state = _make_state(screen_name='game')
        Screen, screen = self._make_screen(state, logout_collide=True)

        Screen.handle_events(screen, [SimpleNamespace(type=pygame.MOUSEBUTTONDOWN)])

        assert state.screen == 'game'
        assert state.user == 'player'
        assert state.user_dict == {'id': 1}
        assert state.game is not None
        state.set_msg.assert_not_called()