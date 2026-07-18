# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Regression tests for duel challenge clicks in the New Game screen."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pygame


class _DummyButton:
    def __init__(self, text='Opponent', collide=True):
        self.text = text
        self.rect = pygame.Rect(20, 100, 200, 40)
        self._collide = collide

    def collide(self):
        return self._collide


def _make_screen(challenge, user):
    from game.screens.new_game_screen import NewGameScreen

    state = SimpleNamespace(action={
        'task': None,
        'content': None,
        'status': None,
    })
    screen = NewGameScreen.__new__(NewGameScreen)
    screen.state = state
    screen._selected_opponent = None
    screen.send_button = _DummyButton(collide=False)
    screen.challenge_buttons = []
    screen.possible_opponents = []
    screen.open_challenge_buttons = [_DummyButton(text='Rival')]
    screen.open_challenges = [challenge]
    screen.user = user
    screen._list_top = 90
    screen._list_bottom = 180
    screen.make_dialogue_box = MagicMock()
    return screen


def test_received_open_challenge_click_opens_accept_dialogue():
    challenge = {
        'id': 7,
        'challenger_id': 2,
        'challenged_id': 1,
        'stake': 12,
        'game_limit': 21,
        'date': '2026-07-05',
    }
    user = {
        'id': 1,
        'challenges_issued': [],
        'challenges_received': [challenge],
    }
    screen = _make_screen(challenge, user)

    screen._handle_clicks()

    assert screen.state.action == {
        'task': 'accept_game_challenge',
        'content': challenge,
        'status': 'open',
    }
    screen.make_dialogue_box.assert_called_once()
    message = screen.make_dialogue_box.call_args.args[0]
    kwargs = screen.make_dialogue_box.call_args.kwargs
    assert 'Accept the duel challenge from Rival?' in message
    assert 'Stake: 12 gold' in message
    assert 'First to: 21 points' in message
    assert kwargs['actions'] == ['accept', 'reject']
    assert kwargs['title'] == 'Accept Challenge'


def test_sent_open_challenge_click_shows_pending_dialogue():
    challenge = {
        'id': 8,
        'challenger_id': 1,
        'challenged_id': 2,
        'stake': 9,
        'game_limit': 13,
        'date': '2026-07-05',
    }
    user = {
        'id': 1,
        'challenges_issued': [challenge],
        'challenges_received': [],
    }
    screen = _make_screen(challenge, user)

    screen._handle_clicks()

    assert screen.state.action == {
        'task': None,
        'content': None,
        'status': None,
    }
    screen.make_dialogue_box.assert_called_once()
    message = screen.make_dialogue_box.call_args.args[0]
    kwargs = screen.make_dialogue_box.call_args.kwargs
    assert 'You challenged Rival at 2026-07-05' in message
    assert kwargs['actions'] == ['ok']
    assert kwargs['title'] == 'Challenge Pending'


def test_opponent_sort_prioritizes_online_humans_then_offline_then_ai():
    from game.screens.new_game_screen import _opponent_sort_key

    users = [
        {'username': '[AI] Strategos', 'is_online': True, 'is_ai': True},
        {'username': 'Zed', 'is_online': False, 'is_ai': False},
        {'username': 'Amy', 'is_online': True, 'is_ai': False},
        {'username': 'Bea', 'is_online': True, 'is_ai': False},
    ]

    assert [user['username'] for user in sorted(users, key=_opponent_sort_key)] == [
        'Amy',
        'Bea',
        'Zed',
        '[AI] Strategos',
    ]


def test_rebuild_filters_username_and_keeps_button_user_mapping():
    from game.screens.new_game_screen import NewGameScreen

    screen = NewGameScreen.__new__(NewGameScreen)
    screen.window = pygame.Surface((800, 480))
    screen.state = SimpleNamespace(user_dict={})
    screen.users = [
        {'id': 2, 'username': 'HimalayaHero', 'is_online': True, 'is_ai': False},
        {'id': 3, 'username': 'RiverKing', 'is_online': True, 'is_ai': False},
        {'id': 4, 'username': '[AI] Strategos', 'is_online': True, 'is_ai': True},
    ]
    screen.open_opponents = {}
    screen.open_challenges = []
    screen.user = {'id': 1}
    screen.player_search_field = SimpleNamespace(content='HIMA')
    screen._last_search_query = ''
    screen._col1_x = 20
    screen._col2_x = 420
    screen._col_w = 340
    screen._list_top = 100
    screen._list_bottom = 400
    screen._list_button_h = 50
    screen._list_gap = 8
    screen._scroll_col1 = 0
    screen._scroll_col2 = 0
    screen._max_scroll_col1 = 0
    screen._max_scroll_col2 = 0
    screen._selected_opponent = None

    screen._rebuild_challenge_buttons()

    assert [user['username'] for user in screen.visible_opponents] == [
        'HimalayaHero',
    ]
    assert screen.challenge_buttons[0].user is screen.visible_opponents[0]


def test_on_enter_requests_roster_immediately():
    from game.screens.new_game_screen import NewGameScreen

    screen = NewGameScreen.__new__(NewGameScreen)
    screen._register_mobile_web_inputs = MagicMock()
    screen._request_matchmaking_refresh = MagicMock()

    screen.on_enter()

    screen._register_mobile_web_inputs.assert_called_once_with()
    screen._request_matchmaking_refresh.assert_called_once_with(manual=True)


def test_mobile_search_clear_syncs_native_value_and_refocuses(monkeypatch):
    from game.screens.new_game_screen import NewGameScreen
    from utils import web_keyboard

    synced = []
    monkeypatch.setattr(
        web_keyboard, 'set_input_value',
        lambda label, value: synced.append((label, value)) or True)
    field = SimpleNamespace(
        name='player_search',
        content='',
        activate=MagicMock(),
    )
    screen = NewGameScreen.__new__(NewGameScreen)
    screen._mobile_ui = True

    screen._sync_mobile_web_field(field, focus=True)

    assert synced == [('player_search', '')]
    field.activate.assert_called_once_with()
