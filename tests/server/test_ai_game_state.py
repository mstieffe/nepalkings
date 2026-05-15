# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for AI game-state prompt serialization."""

from ai.game_state import serialize_game_for_llm


def test_serialize_game_for_llm_uses_conquer_tactics_for_tactics_hand():
    game = {
        'id': 501,
        'mode': 'conquer',
        'conquer_move_model': 'tactics_hand',
        'current_round': 1,
        'stake': 0,
        'invader_player_id': 1,
        'ceasefire_active': False,
        'battle_confirmed': True,
        'battle_round': 0,
        'battle_moves': [
            {'id': 99, 'player_id': 1, 'name': 'Legacy Move', 'value': 99},
        ],
        'conquer_tactics': [
            {
                'id': 10,
                'player_id': 1,
                'family_name': 'Dagger',
                'rank': '7',
                'suit': 'Hearts',
                'value': 7,
                'status': 'available',
            },
            {
                'id': 11,
                'player_id': 2,
                'family_name': 'Block',
                'rank': 'Q',
                'suit': 'Clubs',
                'value': 2,
                'status': 'available',
            },
        ],
        'battle_modifier': [],
        'active_spells': [],
        'players': [
            {
                'id': 1,
                'points': 0,
                'turns_left': 1,
                'main_hand': [],
                'side_hand': [],
                'figures': [],
            },
            {
                'id': 2,
                'points': 0,
                'turns_left': 1,
                'main_hand': [],
                'side_hand': [],
                'figures': [],
            },
        ],
    }

    text = serialize_game_for_llm(game, ai_player_id=1)

    assert 'Your conquer tactics:' in text
    assert 'Dagger(7)' in text
    assert 'Your battle moves:' not in text
    assert 'Legacy Move' not in text
