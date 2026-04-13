# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Figure completion estimation utilities for strategy planning."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import ceil
from typing import Any

from ai.figure_recipes import FIGURE_RECIPES
from ai.game_state import compute_resource_totals
from ai.probability_engine import (
    get_deck_counts,
    probability_at_least,
    probability_meet_requirements,
)


_RANK_VALUE_MAP = {
    '2': 2,
    '3': 3,
    '4': 4,
    '5': 5,
    '6': 6,
    '7': 7,
    '8': 8,
    '9': 9,
    '10': 10,
    'J': 11,
    'Q': 12,
    'K': 13,
    'A': 14,
}


@dataclass
class FigureCompletionEstimate:
    family_name: str
    name: str
    suit: str
    field: str
    card_state: str
    completion_probability: float
    turns_needed_min: int
    build_now: bool
    impossible: bool
    resource_blocked: bool
    resource_gap: dict[str, int]
    number_card_type: str | None
    number_card_options: list[str]
    number_value_assumed: int
    missing_main: dict[str, int]
    missing_side: dict[str, int]
    assumed_main_draws_per_turn: int
    assumed_side_draws_per_turn: int

    def as_dict(self) -> dict[str, Any]:
        return {
            'family_name': self.family_name,
            'name': self.name,
            'suit': self.suit,
            'field': self.field,
            'card_state': self.card_state,
            'completion_probability': round(self.completion_probability, 4),
            'turns_needed_min': self.turns_needed_min,
            'build_now': self.build_now,
            'impossible': self.impossible,
            'resource_blocked': self.resource_blocked,
            'resource_gap': dict(self.resource_gap),
            'number_card_type': self.number_card_type,
            'number_card_options': list(self.number_card_options),
            'number_value_assumed': self.number_value_assumed,
            'missing_main': dict(self.missing_main),
            'missing_side': dict(self.missing_side),
            'assumed_main_draws_per_turn': int(self.assumed_main_draws_per_turn),
            'assumed_side_draws_per_turn': int(self.assumed_side_draws_per_turn),
        }


def _card_key(card: dict[str, Any]) -> tuple[str | None, str | None]:
    return card.get('rank'), card.get('suit')


def _find_player(game_dict: dict[str, Any], player_id: int) -> dict[str, Any] | None:
    return next((p for p in game_dict.get('players', []) if p.get('id') == player_id), None)


def _free_hand_cards(player: dict[str, Any], hand_key: str) -> list[dict[str, Any]]:
    cards = player.get(hand_key, [])
    return [
        c for c in cards
        if not c.get('part_of_figure') and not c.get('part_of_battle_move')
    ]


def _free_hand_counts(player: dict[str, Any], hand_key: str) -> Counter[tuple[str | None, str | None]]:
    return Counter(_card_key(c) for c in _free_hand_cards(player, hand_key))


def _card_numeric_value(card: dict[str, Any]) -> int:
    raw_value = card.get('value')
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        rank = str(card.get('rank') or '')
        return _RANK_VALUE_MAP.get(rank, 0)


def _is_card_relevant_for_target(
    card: dict[str, Any],
    required_keys: set[tuple[str | None, str | None]],
    target_suit: str,
    number_options: set[str],
) -> bool:
    key = _card_key(card)
    if key in required_keys:
        return True

    suit = str(card.get('suit') or '')
    rank = str(card.get('rank') or '')
    return bool(number_options and suit == str(target_suit) and rank in number_options)


def _adaptive_draws_per_turn(
    cards: list[dict[str, Any]],
    required_keys: set[tuple[str | None, str | None]],
    target_suit: str,
    number_options: set[str],
    max_draws_per_turn: int,
    needs_missing: bool,
) -> int:
    """Estimate likely card swaps per turn from card quality and relevance."""
    def _adaptive_draw_cap_per_turn(hand_size: int, base_cap: int) -> int:
        # Keep the configured value as a baseline, but scale up for large hands
        # so planner assumptions are less conservative when many cards are available.
        hand_size = max(0, int(hand_size))
        base_cap = max(0, int(base_cap))
        if hand_size <= 0 or base_cap <= 0:
            return 0

        # +1 cap slot per ~2 cards above 4 cards in hand.
        bonus = max(0, (hand_size - 3) // 2)
        scaled_cap = base_cap + bonus
        return min(hand_size, scaled_cap)

    max_draws = _adaptive_draw_cap_per_turn(len(cards), max_draws_per_turn)
    if max_draws <= 0 or not cards:
        return 0

    swap_scores: list[float] = []
    for card in cards:
        relevant = _is_card_relevant_for_target(card, required_keys, target_suit, number_options)
        value = _card_numeric_value(card)

        # Off-plan and low-value cards are more likely to be cycled away.
        score = 0.0
        if not relevant:
            score += 0.7
        if value <= 6:
            score += 1.0
        elif value <= 9:
            score += 0.4
        elif value >= 13:
            score -= 0.35
        if relevant:
            score -= 0.75

        swap_scores.append(score)

    swap_scores.sort(reverse=True)
    likely = sum(1 for s in swap_scores[:max_draws] if s >= 1.0)

    if needs_missing and likely == 0:
        likely = 1

    return max(0, min(max_draws, likely))


def _turns_needed_for_missing(missing_total: int, draws_per_turn: int) -> int:
    if int(missing_total) <= 0:
        return 0

    draws = max(0, int(draws_per_turn))
    if draws == 0:
        return 999

    return ceil(int(missing_total) / draws)


def _stringify_missing(missing: Counter[tuple[str | None, str | None]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for (rank, suit), count in missing.items():
        if count <= 0:
            continue
        out[f"{rank}_{suit}"] = int(count)
    return out


def _compute_missing(
    required: Counter[tuple[str | None, str | None]],
    available: Counter[tuple[str | None, str | None]],
) -> Counter[tuple[str | None, str | None]]:
    missing: Counter[tuple[str | None, str | None]] = Counter()
    for key, req_count in required.items():
        if req_count <= 0:
            continue
        gap = req_count - available.get(key, 0)
        if gap > 0:
            missing[key] = gap
    return missing


def _best_number_value_from_hand(
    available: Counter[tuple[str | None, str | None]],
    suit: str,
    options: list[str],
) -> int | None:
    candidates: list[int] = []
    for rank in options:
        if available.get((rank, suit), 0) > 0:
            try:
                candidates.append(int(rank))
            except (TypeError, ValueError):
                continue
    if not candidates:
        return None
    return max(candidates)


def _resource_gap_after_build(
    figures: list[dict[str, Any]],
    produces: dict[str, int],
    requires: dict[str, int],
) -> dict[str, int]:
    current_produces, current_requires = compute_resource_totals(figures)

    sim_produces = dict(current_produces)
    sim_requires = dict(current_requires)

    for res, amt in (produces or {}).items():
        if amt:
            sim_produces[res] = sim_produces.get(res, 0) + int(amt)

    for res, amt in (requires or {}).items():
        if amt:
            sim_requires[res] = sim_requires.get(res, 0) + int(amt)

    gap: dict[str, int] = {}
    for res, needed in sim_requires.items():
        short = int(needed) - int(sim_produces.get(res, 0))
        if short > 0:
            gap[res] = short
    return gap


def estimate_figure_completion(
    game_dict: dict[str, Any],
    ai_player_id: int,
    remaining_turns: int | None = None,
    max_main_draws_per_turn: int = 2,
    max_side_draws_per_turn: int = 1,
) -> list[dict[str, Any]]:
    """Estimate completion status/probability for each figure recipe variant.

    Returns deterministic estimates sorted by likely impact and feasibility.
    """
    player = _find_player(game_dict, ai_player_id)
    if not player:
        return []

    turns_left = int(player.get('turns_left') or 0)
    horizon = int(remaining_turns) if remaining_turns is not None else max(turns_left, 1)
    horizon = max(horizon, 1)

    base_main_draws_per_turn = max(0, int(max_main_draws_per_turn))
    base_side_draws_per_turn = max(0, int(max_side_draws_per_turn))

    free_main_cards = _free_hand_cards(player, 'main_hand')
    free_side_cards = _free_hand_cards(player, 'side_hand')
    hand_main = _free_hand_counts(player, 'main_hand')
    hand_side = _free_hand_counts(player, 'side_hand')
    deck_main = get_deck_counts(game_dict, card_type='main')
    deck_side = get_deck_counts(game_dict, card_type='side')

    figures = list(player.get('figures', []))
    estimates: list[FigureCompletionEstimate] = []

    for recipe in FIGURE_RECIPES:
        if recipe.get('field') == 'castle':
            continue

        for suit in recipe.get('suits', []):
            required_main: Counter[tuple[str | None, str | None]] = Counter()
            required_side: Counter[tuple[str | None, str | None]] = Counter()

            for rank, card_type in recipe.get('key_ranks', []):
                key = (rank, suit)
                if card_type == 'main':
                    required_main[key] += 1
                else:
                    required_side[key] += 1

            missing_main = _compute_missing(required_main, hand_main)
            missing_side = _compute_missing(required_side, hand_side)

            needs_number = bool(recipe.get('needs_number_card'))
            num_type = recipe.get('number_card_type', 'main') if needs_number else None
            num_options = list(recipe.get('number_card_options', [])) if needs_number else []
            num_option_set = {str(r) for r in num_options}

            best_number_in_hand = None
            if needs_number:
                pool_hand_for_number = hand_main if num_type == 'main' else hand_side
                best_number_in_hand = _best_number_value_from_hand(pool_hand_for_number, suit, num_options)

            main_missing_total_for_rate = sum(missing_main.values())
            side_missing_total_for_rate = sum(missing_side.values())
            if needs_number and best_number_in_hand is None:
                if num_type == 'main':
                    main_missing_total_for_rate += 1
                elif num_type == 'side':
                    side_missing_total_for_rate += 1

            draws_main_per_turn = _adaptive_draws_per_turn(
                cards=free_main_cards,
                required_keys=set(required_main.keys()),
                target_suit=suit,
                number_options=num_option_set if num_type == 'main' else set(),
                max_draws_per_turn=base_main_draws_per_turn,
                needs_missing=main_missing_total_for_rate > 0,
            )
            draws_side_per_turn = _adaptive_draws_per_turn(
                cards=free_side_cards,
                required_keys=set(required_side.keys()),
                target_suit=suit,
                number_options=num_option_set if num_type == 'side' else set(),
                max_draws_per_turn=base_side_draws_per_turn,
                needs_missing=side_missing_total_for_rate > 0,
            )

            draws_main = draws_main_per_turn * horizon
            draws_side = draws_side_per_turn * horizon

            # Key-card probabilities adjusted by adaptive draw-rate assumptions.
            p_main = probability_meet_requirements(deck_main, dict(missing_main), draws_main)
            p_side = probability_meet_requirements(deck_side, dict(missing_side), draws_side)

            p_number = 1.0
            number_missing = 0
            number_value_assumed = 0

            if needs_number:
                pool_hand = hand_main if num_type == 'main' else hand_side
                pool_deck = deck_main if num_type == 'main' else deck_side
                pool_draws = draws_main if num_type == 'main' else draws_side

                if best_number_in_hand is not None:
                    number_value_assumed = int(best_number_in_hand)
                else:
                    number_missing = 1
                    population_size = sum(pool_deck.values())
                    success_states = sum(pool_deck.get((r, suit), 0) for r in num_options)
                    p_number = probability_at_least(success_states, population_size, pool_draws, 1)
                    # Assume the lowest option for conservative resource requirements.
                    parsed = []
                    for r in num_options:
                        try:
                            parsed.append(int(r))
                        except (TypeError, ValueError):
                            continue
                    number_value_assumed = min(parsed) if parsed else 0

            completion_probability = max(0.0, min(1.0, p_main * p_side * p_number))

            base_main_missing = sum(missing_main.values())
            base_side_missing = sum(missing_side.values())
            main_missing_total = base_main_missing + (number_missing if num_type == 'main' else 0)
            side_missing_total = base_side_missing + (number_missing if num_type == 'side' else 0)

            turns_for_main = _turns_needed_for_missing(main_missing_total, draws_main_per_turn)
            turns_for_side = _turns_needed_for_missing(side_missing_total, draws_side_per_turn)
            turns_needed_min = max(turns_for_main, turns_for_side)

            build_now = (
                base_main_missing == 0
                and base_side_missing == 0
                and number_missing == 0
            )

            if 'requires_fn' in recipe:
                requires = dict(recipe['requires_fn'](suit, int(number_value_assumed)))
            else:
                requires = dict(recipe.get('requires', {}))

            produces = dict(recipe.get('produces_fn', lambda _s, _n: {})(suit, int(number_value_assumed)))
            gap = _resource_gap_after_build(figures, produces=produces, requires=requires)
            resource_blocked = bool(gap)
            impossible = completion_probability <= 0.0

            if build_now and not resource_blocked:
                card_state = 'build_now'
            elif impossible:
                card_state = 'build_impossible'
            else:
                card_state = 'build_possible_with_probability'

            estimates.append(
                FigureCompletionEstimate(
                    family_name=str(recipe.get('family_name', recipe.get('name', 'Unknown'))),
                    name=str(recipe.get('name', 'Unknown')),
                    suit=str(suit),
                    field=str(recipe.get('field', 'unknown')),
                    card_state=card_state,
                    completion_probability=completion_probability,
                    turns_needed_min=turns_needed_min,
                    build_now=build_now,
                    impossible=impossible,
                    resource_blocked=resource_blocked,
                    resource_gap=gap,
                    number_card_type=num_type,
                    number_card_options=list(num_options),
                    number_value_assumed=int(number_value_assumed),
                    missing_main=_stringify_missing(missing_main),
                    missing_side=_stringify_missing(missing_side),
                    assumed_main_draws_per_turn=int(draws_main_per_turn),
                    assumed_side_draws_per_turn=int(draws_side_per_turn),
                )
            )

    # Military figures usually matter most for short-term battle planning.
    field_priority = {'military': 0, 'village': 1, 'castle': 2}
    estimates.sort(
        key=lambda e: (
            field_priority.get(e.field, 9),
            -e.completion_probability,
            e.turns_needed_min,
            e.name,
            e.suit,
        )
    )

    return [e.as_dict() for e in estimates]


def best_figure_targets(
    game_dict: dict[str, Any],
    ai_player_id: int,
    remaining_turns: int | None = None,
    max_results: int = 6,
    max_main_draws_per_turn: int = 2,
    max_side_draws_per_turn: int = 1,
) -> list[dict[str, Any]]:
    """Return top feasible figure targets for plan generation."""
    estimates = estimate_figure_completion(
        game_dict,
        ai_player_id,
        remaining_turns=remaining_turns,
        max_main_draws_per_turn=max_main_draws_per_turn,
        max_side_draws_per_turn=max_side_draws_per_turn,
    )

    scored = [
        e for e in estimates
        if not e.get('impossible') and not (e.get('resource_blocked') and e.get('build_now') is False)
    ]
    return scored[: max(1, int(max_results))]
