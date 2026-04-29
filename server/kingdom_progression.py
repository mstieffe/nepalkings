# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Kingdom progression: levels, experience, skills, and gold vault config.

All values here are tunable.  The skill roster is data-driven via the
``KINGDOM_SKILL_DEFINITIONS`` tuple — adding a new skill is one row.  Per-skill
SP cost is ``cost_multiplier * KINGDOM_SKILL_BASE_COST_CURVE[level - 1]``.
"""

from dataclasses import dataclass
from typing import Tuple


# ── Kingdom progression ────────────────────────────────────────────────────
KINGDOM_LEVEL_MAX = 50
KINGDOM_SKILL_POINTS_PER_LEVEL = 3
KINGDOM_LEVEL_XP_BASE = 5         # XP needed to advance from level 1 → 2
KINGDOM_LEVEL_XP_GROWTH = 1.5     # geometric growth factor per level
KINGDOM_TIER_XP = {1: 1, 2: 2, 3: 4, 4: 8}

# ── Skills ─────────────────────────────────────────────────────────────────
# Base SP cost to BUY level N (1-indexed), multiplied per-skill by
# ``cost_multiplier``.  Length determines the maximum supported level
# across all skills.
KINGDOM_SKILL_BASE_COST_CURVE: Tuple[int, ...] = (1, 2, 4, 8, 16)

# Vault capacity when the gold_vault skill is at level 0 (i.e. not invested).
KINGDOM_VAULT_DEFAULT_CAP = 50


@dataclass(frozen=True)
class KingdomSkillDef:
    """Static definition of a kingdom skill.

    Attributes
    ----------
    key
        Stable identifier persisted in ``KingdomSkillAllocation.skill_key``.
    name, description
        Player-facing labels.
    max_level
        Maximum allocatable level (1..len(BASE_COST_CURVE)).
    cost_multiplier
        Multiplied with ``KINGDOM_SKILL_BASE_COST_CURVE`` to derive the SP cost
        to buy each level.  Higher = more expensive skill.
    effect_values
        Tuple of effect values, one per level (1-indexed).  Length must equal
        ``max_level``.  Interpretation depends on the consuming code:
        * gold_production: fractional gold-rate multiplier add (0.03 = +3%)
        * gold_vault: vault capacity in gold
        * shield_cost_reduction: fractional shield-cost discount (0.05 = -5%)
        * core_protection: number of lands shielded at threshold
    icon_path
        Client-side asset key (rendered via ``KINGDOM_SKILL_ICON_PATHS`` on
        the client).  Stored here for completeness/server payloads.
    """
    key: str
    name: str
    description: str
    max_level: int
    cost_multiplier: int
    effect_values: Tuple[float, ...]
    icon_path: str

    def __post_init__(self):
        if len(self.effect_values) != self.max_level:
            raise ValueError(
                f'KingdomSkillDef {self.key!r}: effect_values length '
                f'{len(self.effect_values)} != max_level {self.max_level}')
        if self.max_level < 1 or self.max_level > len(KINGDOM_SKILL_BASE_COST_CURVE):
            raise ValueError(
                f'KingdomSkillDef {self.key!r}: max_level {self.max_level} '
                f'out of supported range 1..{len(KINGDOM_SKILL_BASE_COST_CURVE)}')
        if self.cost_multiplier < 1:
            raise ValueError(
                f'KingdomSkillDef {self.key!r}: cost_multiplier must be >= 1')


KINGDOM_SKILL_DEFINITIONS: Tuple[KingdomSkillDef, ...] = (
    KingdomSkillDef(
        key='gold_production',
        name='Gold Production',
        description='Increases gold production for this kingdom.',
        max_level=5,
        cost_multiplier=1,
        effect_values=(0.03, 0.06, 0.10, 0.15, 0.22),
        icon_path='img/dialogue_box/icons/gold.png',
    ),
    KingdomSkillDef(
        key='gold_vault',
        name='Gold Vault',
        description='Increases the maximum amount of uncollected gold this '
                    'kingdom can hold before production stops.',
        max_level=5,
        cost_multiplier=1,
        effect_values=(100, 250, 500, 1000, 2000),
        icon_path='img/dialogue_box/icons/coin.png',
    ),
    KingdomSkillDef(
        key='shield_cost_reduction',
        name='Shield Economy',
        description='Reduces the gold cost of kingdom shields.',
        max_level=5,
        cost_multiplier=2,
        effect_values=(0.05, 0.10, 0.16, 0.23, 0.32),
        icon_path='img/resource_icons/shield.png',
    ),
    KingdomSkillDef(
        key='core_protection',
        name='Core Protection',
        description='When your kingdom shrinks to this many lands or fewer, '
                    'those lands cannot be conquered.',
        max_level=5,
        cost_multiplier=3,
        effect_values=(1, 2, 3, 4, 5),
        icon_path='img/battle/icons/block.png',
    ),
)

# Indexed once at import time for O(1) lookups.
_SKILL_DEFINITIONS_BY_KEY = {d.key: d for d in KINGDOM_SKILL_DEFINITIONS}


def skill_definition(key: str):
    """Return the ``KingdomSkillDef`` for ``key`` or ``None`` if unknown."""
    return _SKILL_DEFINITIONS_BY_KEY.get(key)


def skill_keys():
    """Return the ordered tuple of all known skill keys."""
    return tuple(d.key for d in KINGDOM_SKILL_DEFINITIONS)


def skill_cost_to_buy_level(key: str, target_level: int) -> int:
    """SP cost to upgrade from ``target_level - 1`` to ``target_level``.

    Returns 0 for out-of-range levels (level <= 0, > max_level, or unknown
    skill) so callers can treat "max level" / "unknown" uniformly.
    """
    sdef = skill_definition(key)
    if sdef is None:
        return 0
    if target_level < 1 or target_level > sdef.max_level:
        return 0
    base = KINGDOM_SKILL_BASE_COST_CURVE[target_level - 1]
    return int(base * sdef.cost_multiplier)


def skill_total_cost_for_level(key: str, level: int) -> int:
    """Cumulative SP spent to reach ``level``."""
    if level <= 0:
        return 0
    return sum(skill_cost_to_buy_level(key, lvl) for lvl in range(1, int(level) + 1))


def skill_effect_at_level(key: str, level: int):
    """Return the effect value at ``level``, or 0 if level <= 0 / unknown."""
    sdef = skill_definition(key)
    if sdef is None or level <= 0:
        return 0
    level = min(int(level), sdef.max_level)
    return sdef.effect_values[level - 1]


def vault_cap_for_skill_level(level: int) -> int:
    """Vault capacity for a given gold_vault skill level.

    Level 0 returns ``KINGDOM_VAULT_DEFAULT_CAP``; higher levels return the
    skill's effect_value.
    """
    if level <= 0:
        return int(KINGDOM_VAULT_DEFAULT_CAP)
    return int(skill_effect_at_level('gold_vault', level) or KINGDOM_VAULT_DEFAULT_CAP)


# ── XP / Levels ────────────────────────────────────────────────────────────

def kingdom_xp_required_for_level(level: int) -> int:
    """XP needed inside ``level`` to advance to ``level + 1``.

    Level 1 → 2 needs ``KINGDOM_LEVEL_XP_BASE`` XP; each subsequent level scales
    by ``KINGDOM_LEVEL_XP_GROWTH``.  At max level returns 0.
    """
    if level >= KINGDOM_LEVEL_MAX or level < 1:
        return 0
    return int(round(KINGDOM_LEVEL_XP_BASE * (KINGDOM_LEVEL_XP_GROWTH ** (level - 1))))


def kingdom_total_xp_for_level(level: int) -> int:
    """Cumulative XP needed to *reach* ``level``.

    Level 1 = 0 XP.  Level 2 = ``kingdom_xp_required_for_level(1)``.  Etc.
    """
    if level <= 1:
        return 0
    level = min(int(level), KINGDOM_LEVEL_MAX)
    return sum(kingdom_xp_required_for_level(lvl) for lvl in range(1, level))


def kingdom_level_for_total_xp(total_xp: int) -> int:
    """Highest level reachable with ``total_xp`` cumulative XP, capped at max."""
    total_xp = max(0, int(total_xp or 0))
    level = 1
    while level < KINGDOM_LEVEL_MAX:
        next_threshold = kingdom_total_xp_for_level(level + 1)
        if total_xp < next_threshold:
            break
        level += 1
    return level


def xp_for_land_tier(tier: int) -> int:
    """Return the XP awarded for connecting a land of the given tier."""
    return int(KINGDOM_TIER_XP.get(int(tier or 0), 0))
