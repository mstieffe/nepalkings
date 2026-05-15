# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for AI probability utilities."""

from math import isclose

from ai.probability_engine import (
    get_deck_counts,
    probability_at_least,
    probability_exact,
    probability_meet_requirements,
)


def test_get_deck_counts_only_counts_cards_still_in_deck():
    game_dict = {
        'main_cards': [
            {'rank': 'A', 'suit': 'Hearts', 'in_deck': True},
            {'rank': 'A', 'suit': 'Hearts', 'in_deck': False},
            {'rank': 'K', 'suit': 'Spades', 'in_deck': True},
        ],
        'side_cards': [],
    }

    counts = get_deck_counts(game_dict, card_type='main')

    assert counts[('A', 'Hearts')] == 1
    assert counts[('K', 'Spades')] == 1
    assert ('A', 'Spades') not in counts


def test_probability_exact_matches_known_hypergeometric_case():
    # Draw exactly 1 success from 4 successes in population 10 with 3 draws:
    # C(4,1)*C(6,2)/C(10,3) = 60/120 = 0.5
    p = probability_exact(success_states=4, population_size=10, draws=3, successes=1)
    assert isclose(p, 0.5, rel_tol=1e-9)


def test_probability_at_least_matches_complement_form():
    # P(X >= 1) = 1 - C(6,3)/C(10,3) = 1 - 20/120 = 0.833333...
    p = probability_at_least(success_states=4, population_size=10, draws=3, at_least=1)
    assert isclose(p, 1.0 - (20.0 / 120.0), rel_tol=1e-9)


def test_probability_meet_requirements_single_key_equivalent_to_at_least():
    population = {('A', 'Hearts'): 4, ('K', 'Spades'): 6}
    req = {('A', 'Hearts'): 2}

    p_req = probability_meet_requirements(population, req, draws=3)
    p_at_least = probability_at_least(success_states=4, population_size=10, draws=3, at_least=2)

    assert isclose(p_req, p_at_least, rel_tol=1e-9)


def test_probability_meet_requirements_multi_key_detects_impossible_requests():
    population = {
        ('A', 'Hearts'): 1,
        ('K', 'Hearts'): 1,
        ('Q', 'Hearts'): 8,
    }
    req = {
        ('A', 'Hearts'): 2,  # impossible, only one in population
        ('K', 'Hearts'): 1,
    }

    p = probability_meet_requirements(population, req, draws=3)
    assert p == 0.0
