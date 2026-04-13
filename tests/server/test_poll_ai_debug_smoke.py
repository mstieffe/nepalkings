# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Light smoke tests for poll_ai_debug helper utilities."""

from poll_ai_debug import _format_candidate_verbose_lines, _latest_candidate_summaries, select_game_id


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


def test_latest_candidate_summaries_prefers_most_recent_event_with_candidates():
    events = [
        {'type': 'planner_generated', 'candidates': [{'plan_id': 1, 'seed_action_id': 10}]},
        {'type': 'planner_choice', 'chosen_action_id': 10},
        {'type': 'planner_generated', 'candidates': [{'plan_id': 1, 'seed_action_id': 22}]},
    ]

    candidates, event_type = _latest_candidate_summaries(events)

    assert event_type == 'planner_generated'
    assert candidates == [{'plan_id': 1, 'seed_action_id': 22}]


def test_latest_candidate_summaries_returns_empty_when_not_present():
    events = [
        {'type': 'planner_generated', 'plans': 5},
        {'type': 'planner_choice', 'chosen_action_id': 2},
    ]

    candidates, event_type = _latest_candidate_summaries(events)

    assert candidates == []
    assert event_type is None


def test_format_candidate_verbose_lines_includes_moves_and_turn_steps():
    candidate = {
        'strategy_name': 'Cast Spell Line',
        'expected_power_diff': 6.0,
        'expected_battle_move_power': 28.0,
        'planned_battle_figure': {
            'name': 'Djungle Maharaja',
            'field': 'castle',
            'state': 'already_built',
            'power_estimate': 15,
            'assumed_main_draws_per_turn': 2,
            'assumed_side_draws_per_turn': 1,
        },
        'likely_opponent_figure': {
            'name': 'Himalaya Maharaja',
            'power_estimate': 9,
            'probability': 0.7,
        },
        'planned_battle_moves': [
            {'rank': 'A', 'suit': 'Diamonds', 'value': 14},
            {'rank': '10', 'suit': 'Spades', 'value': 10},
        ],
        'score_breakdown': {'feasibility': 0.85, 'offensive_value': 12.4},
        'turn_steps': ['execute now: cast spell', 'build pressure next turn'],
        'notes': ['counter risk is acceptable'],
    }

    lines = _format_candidate_verbose_lines(candidate)

    assert any('strategy: Cast Spell Line' in line for line in lines)
    assert any('assumed_draws_per_turn: main=2 side=1' in line for line in lines)
    assert any('planned_moves: AD(14), 10S(10)' in line for line in lines)
    assert any('turn_steps:' in line for line in lines)
    assert any('1. execute now: cast spell' in line for line in lines)
    assert any('2. build pressure next turn' in line for line in lines)
