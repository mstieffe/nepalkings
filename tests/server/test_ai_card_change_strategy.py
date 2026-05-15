# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for shared AI main-card change strategy."""

from ai.card_change_strategy import (
    compute_tactic_protected_ids,
    select_main_cards_to_swap,
    summarize_main_change,
)


class _EnumLike:
    def __init__(self, value):
        self.value = value


class _CardObj:
    def __init__(self, card_id, rank, value):
        self.id = card_id
        self.rank = rank
        self.value = value


def test_select_main_cards_to_swap_handles_enum_ranks_without_over_swapping():
    cards = [
        _CardObj(1, _EnumLike('K'), 4),
        _CardObj(2, _EnumLike('A'), 3),
        _CardObj(3, _EnumLike('10'), 10),
        _CardObj(4, _EnumLike('9'), 9),
        _CardObj(5, _EnumLike('Q'), 12),
        _CardObj(6, _EnumLike('J'), 11),
        _CardObj(7, _EnumLike('8'), 8),
        _CardObj(8, _EnumLike('7'), 7),
    ]

    to_swap = select_main_cards_to_swap(cards)

    # K (id=1) and Q (id=5) always kept; one A (id=2) and one J (id=6) kept
    # via MAYBE_KEEP_RANKS. Everything else is swapped.
    assert set(to_swap) == {3, 4, 7, 8}


def test_select_main_cards_to_swap_keeps_only_one_of_each_maybe_rank():
    """MAYBE_KEEP_RANKS (J, A) caps at one kept card per rank."""
    cards = [
        {'id': 1, 'rank': 'A', 'value': 14},
        {'id': 2, 'rank': 'A', 'value': 14},
        {'id': 3, 'rank': 'J', 'value': 11},
        {'id': 4, 'rank': 'J', 'value': 11},
    ]

    to_swap = select_main_cards_to_swap(cards)

    # Exactly one A and one J kept; the duplicates are swapped.
    assert len(to_swap) == 2


def test_select_main_cards_to_swap_returns_empty_when_all_keepable():
    """No forced-1-card fallback: an all-keepable hand swaps nothing."""
    cards = [
        {'id': 1, 'rank': 'K', 'value': 13},
        {'id': 2, 'rank': 'A', 'value': 14},
        {'id': 3, 'rank': 'Q', 'value': 12},
        {'id': 4, 'rank': 'J', 'value': 11},
    ]

    to_swap = select_main_cards_to_swap(cards)

    assert to_swap == []


def test_summarize_main_change_reports_swap_and_low_rank_counts():
    cards = [
        {'id': 1, 'rank': 'K', 'value': 4},
        {'id': 2, 'rank': 'A', 'value': 3},
        {'id': 3, 'rank': '10', 'value': 10},
        {'id': 4, 'rank': '9', 'value': 9},
        {'id': 5, 'rank': 'Q', 'value': 12},
        {'id': 6, 'rank': 'J', 'value': 11},
        {'id': 7, 'rank': '8', 'value': 8},
        {'id': 8, 'rank': '7', 'value': 7},
    ]

    summary = summarize_main_change(cards)

    assert summary['free_count'] == 8
    assert summary['low_rank_count'] == 2
    # K, Q always kept; one A and one J kept via MAYBE_KEEP_RANKS → 4 swapped.
    assert summary['swap_count'] == 4


def test_protect_ids_prevents_swapping():
    """Cards with IDs in protect_ids are never swapped, even if low-value."""
    cards = [
        {'id': 1, 'rank': 'K', 'value': 4},
        {'id': 2, 'rank': '9', 'value': 9, 'suit': 'Hearts'},
        {'id': 3, 'rank': '8', 'value': 8, 'suit': 'Hearts'},
        {'id': 4, 'rank': '7', 'value': 7, 'suit': 'Spades'},
    ]

    # Without protection: 9, 8, 7 are all swapped (only K kept)
    assert set(select_main_cards_to_swap(cards)) == {2, 3, 4}

    # Protect 9 (id=2) — only 8 and 7 swapped
    assert set(select_main_cards_to_swap(cards, protect_ids={2})) == {3, 4}

    # Protect 9 and 8 — only 7 swapped
    assert set(select_main_cards_to_swap(cards, protect_ids={2, 3})) == {4}


def test_compute_tactic_protected_ids_protects_held_key_cards():
    """Cards already held for a figure target's recipe are protected."""
    free_cards = [
        {'id': 10, 'rank': 'J', 'suit': 'Hearts', 'value': 11},
        {'id': 11, 'rank': '9', 'suit': 'Hearts', 'value': 9},
        {'id': 12, 'rank': '8', 'suit': 'Spades', 'value': 8},
    ]
    # Target: Small Rice Farm (Hearts) — needs J(main) + number card
    # missing_main is empty → J is already held
    targets = [{
        'family_name': 'Small Rice Farm',
        'suit': 'Hearts',
        'missing_main': {},  # J_Hearts already in hand
    }]

    protected = compute_tactic_protected_ids(free_cards, targets)

    # J of Hearts (id=10) should be protected
    assert 10 in protected
    # 9 of Hearts should also be protected (number card for farm)
    assert 11 in protected
    # 8 of Spades is NOT protected (wrong suit)
    assert 12 not in protected


def test_compute_tactic_protected_ids_skips_missing_cards():
    """Cards NOT in hand (listed in missing_main) are not protected."""
    free_cards = [
        {'id': 20, 'rank': '10', 'suit': 'Hearts', 'value': 10},
        {'id': 21, 'rank': '8', 'suit': 'Hearts', 'value': 8},
    ]
    # Target needs J_Hearts but it's missing
    targets = [{
        'family_name': 'Small Rice Farm',
        'suit': 'Hearts',
        'missing_main': {'J_Hearts': 1},
    }]

    protected = compute_tactic_protected_ids(free_cards, targets)

    # No J in hand → nothing protected from key cards
    # But 10 of Hearts should be protected as a number card for the farm
    assert 20 in protected
    assert 21 not in protected  # 8 is lower, 10 preferred


def test_compute_tactic_protected_ids_no_double_claim():
    """A single card cannot be claimed by two different targets."""
    free_cards = [
        {'id': 30, 'rank': 'J', 'suit': 'Hearts', 'value': 11},
    ]
    # Two targets both want J_Hearts
    targets = [
        {'family_name': 'Small Rice Farm', 'suit': 'Hearts', 'missing_main': {}},
        {'family_name': 'Small Rice Farm', 'suit': 'Hearts', 'missing_main': {}},
    ]

    protected = compute_tactic_protected_ids(free_cards, targets)

    # Only one card in hand, can only be claimed once
    assert protected == {30}
