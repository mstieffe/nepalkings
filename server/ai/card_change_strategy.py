# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Shared card-change heuristics used by action enum and execution."""

from __future__ import annotations

from typing import Any


KEEP_RANKS = {'K', 'A', '10', '9'}
MAYBE_KEEP_RANKS = {'Q', 'J'}
LOW_MAIN_RANKS = {'7', '8'}

_RANK_VALUE_FALLBACK = {
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


def _field(card: Any, name: str, default: Any = None) -> Any:
    if isinstance(card, dict):
        return card.get(name, default)
    return getattr(card, name, default)


def normalize_rank(rank: Any) -> str:
    """Convert ORM enum/string ranks into a canonical uppercase string."""
    value = rank
    if hasattr(value, 'value'):
        value = value.value
    if value is None:
        return ''
    return str(value).upper()


def _card_numeric_value(card: Any) -> int:
    raw = _field(card, 'value', 0)
    try:
        return int(raw)
    except (TypeError, ValueError):
        pass

    rank = normalize_rank(_field(card, 'rank'))
    return int(_RANK_VALUE_FALLBACK.get(rank, 0))


def select_main_cards_to_swap(cards: list[Any], maybe_keep_limit: int = 2) -> list[int]:
    """Return card IDs that should be swapped according to AI keep/swap policy."""
    maybe_keep_limit = max(0, int(maybe_keep_limit))
    sorted_cards = sorted(cards or [], key=_card_numeric_value)

    to_swap: list[int] = []
    kept_counts: dict[str, int] = {}

    for card in sorted_cards:
        rank = normalize_rank(_field(card, 'rank'))
        card_id = _field(card, 'id')

        kept_counts[rank] = kept_counts.get(rank, 0)

        if rank in KEEP_RANKS:
            kept_counts[rank] += 1
            continue

        if rank in MAYBE_KEEP_RANKS and kept_counts[rank] < maybe_keep_limit:
            kept_counts[rank] += 1
            continue

        try:
            to_swap.append(int(card_id))
        except (TypeError, ValueError):
            continue

    if not to_swap and sorted_cards:
        lowest_id = _field(sorted_cards[0], 'id')
        try:
            to_swap = [int(lowest_id)]
        except (TypeError, ValueError):
            to_swap = []

    return to_swap


def summarize_main_change(cards: list[Any], maybe_keep_limit: int = 2) -> dict[str, int]:
    """Return summary counters for change-card action text and telemetry."""
    free_count = len(cards or [])
    low_count = sum(1 for c in (cards or []) if normalize_rank(_field(c, 'rank')) in LOW_MAIN_RANKS)
    to_swap = select_main_cards_to_swap(cards or [], maybe_keep_limit=maybe_keep_limit)

    return {
        'free_count': int(free_count),
        'low_rank_count': int(low_count),
        'swap_count': int(len(to_swap)),
    }
