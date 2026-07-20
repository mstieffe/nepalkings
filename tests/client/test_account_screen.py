# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.

import pygame


def _state():
    from game.core.state import State

    state = State()
    state.user_dict = {
        'id': 1,
        'username': 'PlayerOne',
        'gold': 100,
        'booster_packs': 0,
        'booster_packs_side': 0,
        'maps': 0,
    }
    state.native_screen_w = 1920
    state.native_screen_h = 1080
    state.screen = 'settings'
    return state


def test_settings_screen_renders_all_tabs_and_validates_password():
    from game.screens.settings_screen import SettingsScreen

    pygame.display.set_mode((854, 480))
    state = _state()
    screen = SettingsScreen(state)

    screen.render()
    assert set(screen._tab_rects) == {
        'resolution',
        'preferences',
        'account',
        'safety',
    }
    screen.handle_events([
        pygame.event.Event(
            pygame.MOUSEBUTTONUP,
            {'button': 1, 'pos': screen._tab_rects['account'].center},
        ),
    ])
    assert screen._tab == 'account'
    assert screen.current_password.pwd is True
    assert screen.new_password.pwd is True

    screen._activate('change_password')
    assert 'current password' in state.message_lines[-1][0].lower()

    screen._tab = 'safety'
    screen.render()
    assert screen._buttons['reason'].text.startswith('Reason:')


def test_successful_password_change_replaces_token_and_clears_fields(
        monkeypatch):
    from game.screens.settings_screen import SettingsScreen
    from utils import http_compat

    pygame.display.set_mode((854, 480))
    state = _state()
    screen = SettingsScreen(state)
    screen._tab = 'account'
    screen.current_password.content = 'old-password'
    screen.new_password.content = 'new-password'
    monkeypatch.setattr(http_compat, '_auth_token', 'old-token')

    screen._apply_result('change_password', {
        'success': True,
        'message': 'changed',
        'token': 'new-token',
    })

    assert http_compat.get_auth_token() == 'new-token'
    assert screen.current_password.content == ''
    assert screen.new_password.content == ''
