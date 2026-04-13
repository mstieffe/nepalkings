# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for shared AI main-card change strategy."""

from ai.card_change_strategy import select_main_cards_to_swap, summarize_main_change


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

    assert set(to_swap) == {7, 8}


def test_select_main_cards_to_swap_swaps_one_card_when_everything_is_keepable():
    cards = [
        {'id': 1, 'rank': 'K', 'value': 4},
        {'id': 2, 'rank': 'A', 'value': 3},
        {'id': 3, 'rank': '10', 'value': 10},
    ]

    to_swap = select_main_cards_to_swap(cards)

    assert len(to_swap) == 1
    assert to_swap[0] == 2


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
    assert summary['swap_count'] == 2
