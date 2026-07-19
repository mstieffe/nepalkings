# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Characterization tests for shared game-mode predicates."""

import inspect
from types import SimpleNamespace


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
