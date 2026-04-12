# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for bounded strategy planner output."""

from ai.strategy_planner import (
    format_strategy_plans_for_prompt,
    generate_strategy_plans,
    recommended_action_id,
)


def _planner_game_dict():
    return {
        'id': 120,
        'battle_modifier': [],
        'battle_moves': [],
        'players': [
            {
                'id': 1,
                'username': '[AI] Strategos',
                'turns_left': 3,
                'main_hand': [
                    {'id': 1, 'rank': 'K', 'suit': 'Hearts', 'value': 4, 'part_of_figure': False, 'part_of_battle_move': False},
                    {'id': 2, 'rank': '10', 'suit': 'Hearts', 'value': 10, 'part_of_figure': False, 'part_of_battle_move': False},
                    {'id': 3, 'rank': '9', 'suit': 'Hearts', 'value': 9, 'part_of_figure': False, 'part_of_battle_move': False},
                ],
                'side_hand': [],
                'figures': [
                    {
                        'id': 101,
                        'name': 'Djungle King',
                        'family_name': 'Djungle King',
                        'field': 'castle',
                        'suit': 'Hearts',
                        'cards': [{'value': 15}],
                        'produces': {'villager_red': 2, 'warrior_red': 1},
                        'requires': {},
                    }
                ],
            },
            {
                'id': 2,
                'username': 'human',
                'turns_left': 3,
                'main_hand': [],
                'side_hand': [],
                'figures': [
                    {
                        'id': 201,
                        'name': 'Opp Military',
                        'family_name': 'Gorkha Warriors',
                        'field': 'military',
                        'suit': 'Hearts',
                        'cards': [{'value': 3}, {'value': 8}],
                        'produces': {},
                        'requires': {'warrior_red': 1, 'food_red': 8},
                    }
                ],
            },
        ],
        'main_cards': [
            {'rank': 'A', 'suit': 'Hearts', 'in_deck': True},
            {'rank': 'J', 'suit': 'Hearts', 'in_deck': True},
            {'rank': '7', 'suit': 'Hearts', 'in_deck': True},
        ],
        'side_cards': [
            {'rank': '2', 'suit': 'Hearts', 'in_deck': True},
            {'rank': '3', 'suit': 'Hearts', 'in_deck': True},
        ],
    }


def test_generate_strategy_plans_is_bounded_and_sorted():
    game = _planner_game_dict()
    actions = [
        {'id': 1, 'type': 'change_cards', 'description': 'change weak cards', 'params': {}},
        {'id': 2, 'type': 'advance_figure', 'description': 'advance king', 'params': {'figure_id': 101}},
        {'id': 3, 'type': 'cast_spell', 'description': 'Cast Blitzkrieg', 'params': {'spell_name': 'Blitzkrieg'}},
    ]

    plans = generate_strategy_plans(game, ai_player_id=1, phase='normal_turn', actions=actions, max_plans=2)

    assert len(plans) == 2
    assert plans[0]['total_score'] >= plans[1]['total_score']


def test_generate_strategy_plans_emits_turn_steps_for_remaining_horizon():
    game = _planner_game_dict()
    actions = [
        {'id': 2, 'type': 'advance_figure', 'description': 'advance king', 'params': {'figure_id': 101}},
    ]

    plans = generate_strategy_plans(game, ai_player_id=1, phase='normal_turn', actions=actions, max_plans=1)

    assert len(plans) == 1
    assert plans[0]['horizon_turns'] == 3
    assert len(plans[0]['turn_steps']) == 3


def test_format_strategy_plans_for_prompt_includes_plan_and_turn_markers():
    plans = [
        {
            'plan_id': 1,
            'seed_action_id': 2,
            'total_score': 4.25,
            'feasibility_probability': 0.9,
            'planned_battle_figure': {'name': 'Djungle King', 'field': 'castle', 'state': 'already_built', 'power_estimate': 15},
            'likely_opponent_figure': {'name': 'Opp Military', 'power_estimate': 11, 'probability': 0.6},
            'planned_battle_moves': [{'rank': '10', 'suit': 'Hearts', 'value': 10}],
            'turn_steps': ['execute now: advance king', 'select defender', 'battle decision'],
            'notes': ['opponent likely commits Opp Military'],
        }
    ]

    text = format_strategy_plans_for_prompt(plans)

    assert 'PLAN 1' in text
    assert 'seed_action=2' in text
    assert 'turn_1:' in text
    assert 'turn_3:' in text


def test_recommended_action_id_returns_seed_action_of_best_plan():
    plans = [
        {'seed_action_id': 4, 'total_score': 2.1},
        {'seed_action_id': 2, 'total_score': 2.1},
        {'seed_action_id': 3, 'total_score': 3.2},
    ]

    rec = recommended_action_id(plans)

    assert rec == 3
