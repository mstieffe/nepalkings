# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Light smoke tests for poll_ai_debug helper utilities."""

from poll_ai_debug import select_game_id


def test_select_game_id_prefers_latest_ai_game_when_available():
    games = [
        {'id': 10, 'players': [{'username': 'alice'}, {'username': 'bob'}]},
        {'id': 12, 'players': [{'username': 'alice'}, {'username': '[AI] Strategos'}]},
        {'id': 11, 'players': [{'username': 'alice'}, {'username': '[AI] Strategos'}]},
    ]

    assert select_game_id(games) == 12


def test_select_game_id_falls_back_to_latest_game_when_no_ai_game():
    games = [
        {'id': 4, 'players': [{'username': 'alice'}, {'username': 'bob'}]},
        {'id': 7, 'players': [{'username': 'alice'}, {'username': 'carol'}]},
    ]

    assert select_game_id(games) == 7
