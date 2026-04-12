# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Deterministic probability utilities for AI planning.

This module is intentionally pure and side-effect free so its behavior is
stable in tests and easy to reason about.
"""

from __future__ import annotations

from collections import Counter
from math import comb
from typing import Any, Callable, Hashable


def _safe_comb(n: int, k: int) -> int:
    """Safe binomial coefficient with 0 for invalid ranges."""
    if n < 0 or k < 0 or k > n:
        return 0
    return comb(n, k)


def get_deck_cards(game_dict: dict[str, Any], card_type: str = "main") -> list[dict[str, Any]]:
    """Return cards currently in deck for the selected card type.

    card_type:
    1. "main" -> game_dict["main_cards"]
    2. "side" -> game_dict["side_cards"]
    """
    key = "main_cards" if card_type == "main" else "side_cards"
    cards = game_dict.get(key, [])
    return [c for c in cards if c.get("in_deck")]


def get_deck_counts(
    game_dict: dict[str, Any],
    card_type: str = "main",
    key_fn: Callable[[dict[str, Any]], Hashable] | None = None,
) -> dict[Hashable, int]:
    """Count cards remaining in deck by arbitrary key.

    Defaults to (rank, suit) grouping.
    """
    if key_fn is None:
        key_fn = lambda c: (c.get("rank"), c.get("suit"))

    counts = Counter()
    for card in get_deck_cards(game_dict, card_type=card_type):
        counts[key_fn(card)] += 1
    return dict(counts)


def probability_exact(success_states: int, population_size: int, draws: int, successes: int) -> float:
    """Hypergeometric probability for drawing exactly successes."""
    if population_size <= 0:
        return 0.0
    if draws < 0 or draws > population_size:
        return 0.0

    numerator = _safe_comb(success_states, successes) * _safe_comb(
        population_size - success_states,
        draws - successes,
    )
    denominator = _safe_comb(population_size, draws)
    if denominator == 0:
        return 0.0
    return float(numerator) / float(denominator)


def probability_at_least(success_states: int, population_size: int, draws: int, at_least: int) -> float:
    """Hypergeometric probability for drawing at least at_least successes."""
    if at_least <= 0:
        return 1.0
    if population_size <= 0 or draws <= 0 or success_states <= 0:
        return 0.0

    max_success = min(success_states, draws)
    if at_least > max_success:
        return 0.0

    total = 0.0
    for x in range(at_least, max_success + 1):
        total += probability_exact(success_states, population_size, draws, x)
    return max(0.0, min(1.0, total))


def probability_meet_requirements(
    population_by_key: dict[Hashable, int],
    requirements_by_key: dict[Hashable, int],
    draws: int,
) -> float:
    """Probability of meeting all minimum keyed card requirements in draws.

    Computes exact multivariate hypergeometric probability using recursive
    enumeration across required key dimensions.
    """
    if draws < 0:
        return 0.0

    requirements = {k: int(v) for k, v in requirements_by_key.items() if int(v) > 0}
    if not requirements:
        return 1.0

    population = {k: int(v) for k, v in population_by_key.items() if int(v) > 0}
    total_population = sum(population.values())
    if total_population <= 0:
        return 0.0
    if draws > total_population:
        draws = total_population

    required_total = sum(requirements.values())
    if required_total > draws:
        return 0.0

    for key, need in requirements.items():
        if population.get(key, 0) < need:
            return 0.0

    req_keys = list(requirements.keys())
    req_pop = [population.get(k, 0) for k in req_keys]
    req_min = [requirements[k] for k in req_keys]
    other_population = total_population - sum(req_pop)

    rem_min_suffix: list[int] = [0] * (len(req_keys) + 1)
    for i in range(len(req_keys) - 1, -1, -1):
        rem_min_suffix[i] = rem_min_suffix[i + 1] + req_min[i]

    denominator = _safe_comb(total_population, draws)
    if denominator == 0:
        return 0.0

    def recurse(idx: int, used_draws: int, numerator_prefix: int) -> int:
        if idx == len(req_keys):
            rest = draws - used_draws
            if 0 <= rest <= other_population:
                return numerator_prefix * _safe_comb(other_population, rest)
            return 0

        min_take = req_min[idx]
        max_take = min(
            req_pop[idx],
            draws - used_draws - rem_min_suffix[idx + 1],
        )
        if max_take < min_take:
            return 0

        subtotal = 0
        for take in range(min_take, max_take + 1):
            ways = _safe_comb(req_pop[idx], take)
            if ways == 0:
                continue
            subtotal += recurse(idx + 1, used_draws + take, numerator_prefix * ways)
        return subtotal

    numerator = recurse(0, 0, 1)
    return max(0.0, min(1.0, float(numerator) / float(denominator)))


def probability_meet_any_requirement_set(
    population_by_key: dict[Hashable, int],
    requirement_sets: list[dict[Hashable, int]],
    draws: int,
) -> float:
    """Probability of meeting at least one requirement set.

    Uses the max of exact probabilities as a conservative and stable estimate.
    This avoids expensive inclusion-exclusion across overlapping sets.
    """
    if not requirement_sets:
        return 0.0

    best = 0.0
    for req in requirement_sets:
        best = max(best, probability_meet_requirements(population_by_key, req, draws))
    return best


def expected_hits(success_states: int, population_size: int, draws: int) -> float:
    """Expected number of successes in a hypergeometric draw."""
    if population_size <= 0 or draws <= 0 or success_states <= 0:
        return 0.0
    draws = min(draws, population_size)
    return float(draws) * (float(success_states) / float(population_size))
