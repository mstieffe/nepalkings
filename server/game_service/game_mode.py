# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Shared predicates for selecting game-mode implementations."""


def is_tactics_hand_conquer(game):
    """Return whether an ORM-like game uses the Conquer tactics-hand model."""
    return bool(
        game
        and game.mode == 'conquer'
        and (getattr(game, 'conquer_move_model', None) or 'battle_move') == 'tactics_hand'
    )
