# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Helpers for choosing the correct gameplay screen."""


def gameplay_screen_for(game):
    """Return the parent screen name for an active game object."""
    if getattr(game, 'mode', 'duel') == 'conquer':
        return 'conquer_game'
    return 'game'
