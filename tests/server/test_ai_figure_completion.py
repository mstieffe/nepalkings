# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for figure-completion estimation."""

from ai.figure_completion import best_figure_targets, estimate_figure_completion


AI_ID = 1
OPP_ID = 2


def _base_game_dict():
    return {
        'id': 50,
        'players': [
            {
                'id': AI_ID,
                'turns_left': 3,
                'main_hand': [],
                'side_hand': [],
                'figures': [
                    {
                        'id': 100,
                        'name': 'Djungle Maharaja',
                        'family_name': 'Djungle Maharaja',
                        'field': 'castle',
                        'suit': 'Hearts',
                        'produces': {'villager_red': 3, 'warrior_red': 2},
                        'requires': {},
                        'cards': [],
                    }
                ],
            },
            {
                'id': OPP_ID,
                'turns_left': 3,
                'main_hand': [],
                'side_hand': [],
                'figures': [],
            },
        ],
        'main_cards': [],
        'side_cards': [],
    }


def _find_estimate(estimates, name, suit):
    return next(e for e in estimates if e['name'] == name and e['suit'] == suit)


def test_estimate_figure_completion_marks_build_now_when_cards_and_resources_ready():
    game = _base_game_dict()
    game['players'][0]['main_hand'] = [
        {'id': 1, 'rank': 'J', 'suit': 'Hearts', 'value': 1, 'part_of_figure': False, 'part_of_battle_move': False},
        {'id': 2, 'rank': '10', 'suit': 'Hearts', 'value': 10, 'part_of_figure': False, 'part_of_battle_move': False},
    ]

    estimates = estimate_figure_completion(game, AI_ID)
    rice_farm = _find_estimate(estimates, 'Small Rice Farm', 'Hearts')

    assert rice_farm['build_now'] is True
    assert rice_farm['resource_blocked'] is False
    assert rice_farm['card_state'] == 'build_now'
    assert rice_farm['completion_probability'] == 1.0


def test_estimate_figure_completion_marks_impossible_when_required_cards_not_in_hand_or_deck():
    game = _base_game_dict()
    game['side_cards'] = [
        {'rank': '2', 'suit': 'Clubs', 'in_deck': True},
        {'rank': '2', 'suit': 'Spades', 'in_deck': True},
        {'rank': '3', 'suit': 'Clubs', 'in_deck': True},
    ]

    estimates = estimate_figure_completion(game, AI_ID)
    healer = _find_estimate(estimates, 'Djungle Healer', 'Hearts')

    assert healer['impossible'] is True
    assert healer['card_state'] == 'build_impossible'
    assert healer['completion_probability'] == 0.0


def test_estimate_figure_completion_flags_resource_blocked_when_build_creates_gap():
    game = _base_game_dict()
    game['players'][0]['main_hand'] = [
        {'id': 10, 'rank': 'A', 'suit': 'Hearts', 'value': 3, 'part_of_figure': False, 'part_of_battle_move': False},
        {'id': 11, 'rank': '7', 'suit': 'Hearts', 'value': 7, 'part_of_figure': False, 'part_of_battle_move': False},
    ]

    estimates = estimate_figure_completion(game, AI_ID)
    gorkha = _find_estimate(estimates, 'Gorkha Warriors', 'Hearts')

    assert gorkha['build_now'] is True
    assert gorkha['resource_blocked'] is True
    assert gorkha['resource_gap'].get('food_red', 0) > 0
    assert gorkha['card_state'] == 'build_possible_with_probability'


def test_best_figure_targets_returns_capped_non_impossible_targets():
    game = _base_game_dict()
    game['players'][0]['main_hand'] = [
        {'id': 20, 'rank': 'J', 'suit': 'Hearts', 'value': 1, 'part_of_figure': False, 'part_of_battle_move': False},
        {'id': 21, 'rank': '9', 'suit': 'Hearts', 'value': 9, 'part_of_figure': False, 'part_of_battle_move': False},
    ]
    game['main_cards'] = [
        {'rank': 'A', 'suit': 'Hearts', 'in_deck': True},
        {'rank': 'K', 'suit': 'Hearts', 'in_deck': True},
        {'rank': 'Q', 'suit': 'Hearts', 'in_deck': True},
    ]

    targets = best_figure_targets(game, AI_ID, max_results=3)

    assert len(targets) <= 3
    assert all(t['impossible'] is False for t in targets)


def test_best_figure_targets_forwards_draw_limits_to_estimator(monkeypatch):
    captured = {}

    def fake_estimate(
        game_dict,
        ai_player_id,
        remaining_turns=None,
        max_main_draws_per_turn=2,
        max_side_draws_per_turn=1,
    ):
        captured['game_id'] = game_dict.get('id')
        captured['ai_player_id'] = ai_player_id
        captured['remaining_turns'] = remaining_turns
        captured['max_main_draws_per_turn'] = max_main_draws_per_turn
        captured['max_side_draws_per_turn'] = max_side_draws_per_turn
        return [
            {
                'impossible': False,
                'resource_blocked': False,
                'build_now': False,
                'name': 'Small Rice Farm',
                'suit': 'Hearts',
            }
        ]

    monkeypatch.setattr('ai.figure_completion.estimate_figure_completion', fake_estimate)

    game = _base_game_dict()
    targets = best_figure_targets(
        game,
        AI_ID,
        remaining_turns=4,
        max_results=3,
        max_main_draws_per_turn=7,
        max_side_draws_per_turn=3,
    )

    assert len(targets) == 1
    assert captured['game_id'] == 50
    assert captured['ai_player_id'] == AI_ID
    assert captured['remaining_turns'] == 4
    assert captured['max_main_draws_per_turn'] == 7
    assert captured['max_side_draws_per_turn'] == 3


def test_estimate_figure_completion_adapts_draw_rate_from_hand_quality():
    game_low_quality = _base_game_dict()
    game_low_quality['players'][0]['main_hand'] = [
        {'id': 31, 'rank': '2', 'suit': 'Clubs', 'value': 2, 'part_of_figure': False, 'part_of_battle_move': False},
        {'id': 32, 'rank': '3', 'suit': 'Spades', 'value': 3, 'part_of_figure': False, 'part_of_battle_move': False},
        {'id': 33, 'rank': '4', 'suit': 'Diamonds', 'value': 4, 'part_of_figure': False, 'part_of_battle_move': False},
        {'id': 34, 'rank': '5', 'suit': 'Clubs', 'value': 5, 'part_of_figure': False, 'part_of_battle_move': False},
    ]
    game_low_quality['main_cards'] = [
        {'rank': 'J', 'suit': 'Hearts', 'in_deck': True},
        {'rank': '10', 'suit': 'Hearts', 'in_deck': True},
        {'rank': '9', 'suit': 'Hearts', 'in_deck': True},
    ]

    low_estimates = estimate_figure_completion(game_low_quality, AI_ID, max_main_draws_per_turn=2)
    low_rice_farm = _find_estimate(low_estimates, 'Small Rice Farm', 'Hearts')

    game_high_quality = _base_game_dict()
    game_high_quality['players'][0]['main_hand'] = [
        {'id': 41, 'rank': 'A', 'suit': 'Hearts', 'value': 14, 'part_of_figure': False, 'part_of_battle_move': False},
        {'id': 42, 'rank': 'K', 'suit': 'Hearts', 'value': 13, 'part_of_figure': False, 'part_of_battle_move': False},
        {'id': 43, 'rank': 'Q', 'suit': 'Hearts', 'value': 12, 'part_of_figure': False, 'part_of_battle_move': False},
        {'id': 44, 'rank': 'J', 'suit': 'Clubs', 'value': 11, 'part_of_figure': False, 'part_of_battle_move': False},
    ]
    game_high_quality['main_cards'] = list(game_low_quality['main_cards'])

    high_estimates = estimate_figure_completion(game_high_quality, AI_ID, max_main_draws_per_turn=2)
    high_rice_farm = _find_estimate(high_estimates, 'Small Rice Farm', 'Hearts')

    assert low_rice_farm['assumed_main_draws_per_turn'] == 2
    assert high_rice_farm['assumed_main_draws_per_turn'] == 1


def test_estimate_figure_completion_scales_main_draw_cap_with_large_hand():
    game = _base_game_dict()
    game['players'][0]['main_hand'] = [
        {
            'id': 100 + idx,
            'rank': rank,
            'suit': suit,
            'value': value,
            'part_of_figure': False,
            'part_of_battle_move': False,
        }
        for idx, (rank, suit, value) in enumerate(
            [
                ('2', 'Clubs', 2),
                ('3', 'Spades', 3),
                ('4', 'Diamonds', 4),
                ('5', 'Clubs', 5),
                ('6', 'Spades', 6),
                ('7', 'Diamonds', 7),
                ('8', 'Clubs', 8),
                ('2', 'Spades', 2),
                ('3', 'Diamonds', 3),
                ('4', 'Clubs', 4),
                ('5', 'Spades', 5),
                ('6', 'Diamonds', 6),
            ]
        )
    ]
    game['main_cards'] = [
        {'rank': 'J', 'suit': 'Hearts', 'in_deck': True},
        {'rank': '10', 'suit': 'Hearts', 'in_deck': True},
        {'rank': '9', 'suit': 'Hearts', 'in_deck': True},
    ]

    estimates = estimate_figure_completion(game, AI_ID, max_main_draws_per_turn=2)
    rice_farm = _find_estimate(estimates, 'Small Rice Farm', 'Hearts')

    assert rice_farm['assumed_main_draws_per_turn'] > 2
