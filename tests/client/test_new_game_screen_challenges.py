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
    assert 'Do you want to accept a game with Rival?' in message
    assert 'Stake: 12 gold' in message
    assert 'Game Limit: 21 points' in message
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
    assert 'You have challenged Rival at 2026-07-05' in message
    assert kwargs['actions'] == ['ok']
    assert kwargs['title'] == 'Challenge Pending'
