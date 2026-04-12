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
