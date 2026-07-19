# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Characterization tests for shared game-mode predicates."""

import inspect
from types import SimpleNamespace

import pytest


def test_route_orm_predicates_share_behavior_but_keep_historical_metadata():
    from game_service.game_mode import is_tactics_hand_conquer
    from routes.battle_shop import (
        _is_tactics_hand_conquer as battle_shop_predicate,
    )
    from routes.games import (
        _is_tactics_hand_conquer as games_predicate,
    )

    cases = (
        (None, False),
        (
            SimpleNamespace(
                mode='duel',
                conquer_move_model='tactics_hand',
            ),
            False,
        ),
        (
            SimpleNamespace(
                mode='conquer',
                conquer_move_model=None,
            ),
            False,
        ),
        (
            SimpleNamespace(
                mode='conquer',
                conquer_move_model='battle_move',
            ),
            False,
        ),
        (
            SimpleNamespace(
                mode='conquer',
                conquer_move_model='tactics_hand',
            ),
            True,
        ),
    )
    for game, expected in cases:
        assert is_tactics_hand_conquer(game) is expected
        assert games_predicate(game) is expected
        assert battle_shop_predicate(game) is expected

    assert str(inspect.signature(is_tactics_hand_conquer)) == '(game)'
    assert str(inspect.signature(games_predicate)) == '(game)'
    assert str(inspect.signature(battle_shop_predicate)) == '(game)'
    assert games_predicate.__module__ == 'routes.games'
    assert battle_shop_predicate.__module__ == 'routes.battle_shop'


def test_ai_state_predicates_share_behavior_and_keep_typed_signatures():
    from game_service.game_mode import is_tactics_hand_conquer_state
    from ai.game_state import (
        _is_tactics_hand_conquer as game_state_predicate,
    )
    from ai.strategy_planner import (
        _is_tactics_hand_conquer as strategy_predicate,
    )

    cases = (
        ({}, False),
        (
            {
                'mode': 'duel',
                'conquer_move_model': 'tactics_hand',
            },
            False,
        ),
        (
            {
                'mode': 'conquer',
                'conquer_move_model': None,
            },
            False,
        ),
        (
            {
                'mode': 'conquer',
                'conquer_move_model': 'battle_move',
            },
            False,
        ),
        (
            {
                'mode': 'conquer',
                'conquer_move_model': 'tactics_hand',
            },
            True,
        ),
    )
    for game_state, expected in cases:
        assert is_tactics_hand_conquer_state(game_state) is expected
        assert game_state_predicate(game_state) is expected
        assert strategy_predicate(game_state) is expected

    with pytest.raises(AttributeError):
        is_tactics_hand_conquer_state(None)
    with pytest.raises(AttributeError):
        game_state_predicate(None)
    with pytest.raises(AttributeError):
        strategy_predicate(None)

    assert str(inspect.signature(game_state_predicate)) == (
        "(game_dict: 'dict') -> 'bool'"
    )
    assert str(inspect.signature(strategy_predicate)) == (
        "(game_dict: 'dict[str, Any]') -> 'bool'"
    )
    assert str(inspect.signature(is_tactics_hand_conquer_state)) == (
        '(game_state)'
    )
    assert game_state_predicate.__module__ == 'ai.game_state'
    assert strategy_predicate.__module__ == 'ai.strategy_planner'
