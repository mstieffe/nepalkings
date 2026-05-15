# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for opponent belief-model generation."""

from ai.opponent_model import build_opponent_belief_snapshot


AI_ID = 1
OPP_ID = 2


def _game_with_players():
    return {
        'id': 90,
        'battle_modifier': [],
        'resting_figure_ids': [],
        'players': [
            {'id': AI_ID, 'username': '[AI] Strategos', 'figures': [], 'main_hand': [], 'side_hand': []},
            {'id': OPP_ID, 'username': 'human', 'figures': [], 'main_hand': [], 'side_hand': []},
        ],
        'battle_moves': [],
    }


def test_snapshot_includes_active_modifier_names():
    game = _game_with_players()
    game['battle_modifier'] = [
        {'type': 'Peasant War', 'caster_id': OPP_ID},
        {'type': 'Blitzkrieg', 'caster_id': AI_ID},
    ]

    snapshot = build_opponent_belief_snapshot(game, AI_ID)

    assert snapshot['active_battle_modifiers'] == ['Peasant War', 'Blitzkrieg']


def test_snapshot_counts_revealed_cards_from_figures_and_played_battle_moves():
    game = _game_with_players()
    game['players'][1]['figures'] = [
        {
            'id': 200,
            'name': 'Gorkha Warriors',
            'field': 'military',
            'cards': [
                {'card_type': 'main', 'rank': 'A', 'suit': 'Hearts', 'value': 3},
                {'card_type': 'main', 'rank': '10', 'suit': 'Hearts', 'value': 10},
            ],
        }
    ]
    game['battle_moves'] = [
        {'player_id': OPP_ID, 'played_round': 0, 'card_type': 'main', 'rank': 'K', 'suit': 'Hearts', 'value': 4},
        {'player_id': OPP_ID, 'played_round': None, 'card_type': 'main', 'rank': 'Q', 'suit': 'Hearts', 'value': 2},
        {'player_id': AI_ID, 'played_round': 0, 'card_type': 'main', 'rank': 'J', 'suit': 'Clubs', 'value': 1},
    ]

    snapshot = build_opponent_belief_snapshot(game, AI_ID)
    revealed = snapshot['revealed_cards']

    assert revealed['main_rank_counts']['A'] == 1
    assert revealed['main_rank_counts']['10'] == 1
    assert revealed['main_rank_counts']['K'] == 1
    assert 'Q' not in revealed['main_rank_counts']


def test_snapshot_likely_battle_figure_respects_villager_only_modifier_bias():
    game = _game_with_players()
    game['battle_modifier'] = [{'type': 'Peasant War'}]
    game['players'][1]['figures'] = [
        {
            'id': 300,
            'name': 'Medium Military',
            'field': 'military',
            'cards': [
                {'card_type': 'main', 'rank': 'A', 'suit': 'Hearts', 'value': 3},
                {'card_type': 'main', 'rank': '9', 'suit': 'Hearts', 'value': 9},
            ],
        },
        {
            'id': 301,
            'name': 'Village Core',
            'field': 'village',
            'cards': [
                {'card_type': 'main', 'rank': 'J', 'suit': 'Hearts', 'value': 1},
                {'card_type': 'main', 'rank': '10', 'suit': 'Hearts', 'value': 10},
            ],
        },
    ]

    snapshot = build_opponent_belief_snapshot(game, AI_ID)
    likely = snapshot['likely_battle_figures'][0]

    assert likely['figure_id'] == 301
    assert likely['field'] == 'village'


def test_snapshot_handles_missing_opponent_gracefully():
    game = {
        'id': 91,
        'players': [{'id': AI_ID, 'username': '[AI] Strategos', 'figures': []}],
        'battle_modifier': [],
        'battle_moves': [],
    }

    snapshot = build_opponent_belief_snapshot(game, AI_ID)

    assert snapshot['opponent_player_id'] is None
    assert snapshot['likely_battle_figures'] == []
