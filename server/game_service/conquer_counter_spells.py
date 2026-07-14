# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Shared rules for automated Conquer defence counter spells."""

import secrets


CONQUER_DEFENCE_COUNTER_SPELLS = frozenset({
    'Draw 2 MainCards',
    'Draw 4 MainCards',
    'Dump Cards',
    'Forced Deal',
    'Poison',
    'Health Boost',
    'Copy Figure',
    'Landslide',
})

CONQUER_COUNTER_GREED_SPELLS = frozenset({
    'Draw 2 MainCards',
    'Draw 4 MainCards',
    'Dump Cards',
    'Forced Deal',
})

CONQUER_TARGETED_COUNTER_SPELLS = frozenset({
    'Poison',
    'Health Boost',
    'Copy Figure',
})


def pick_random_copy_figure_target(figures):
    """Choose uniformly from valid automated-defence Copy Figure targets.

    Callers filter untargetable figures first. Checkmate figures remain valid
    because the resulting clone is never Checkmate. The resolved target is
    persisted on the spell, so subsequent timeline playback stays stable even
    though the initial automated choice is deliberately unpredictable.
    """
    candidates = list(figures or [])
    if not candidates:
        return None
    return secrets.choice(candidates)
