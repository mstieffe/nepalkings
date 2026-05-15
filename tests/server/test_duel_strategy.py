# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for the deterministic duel-mode AI decision module."""

import random

import pytest

from ai import duel_strategy


def _base_game_dict(ai_id=1, opp_id=2):
    return {
        'id': 1,
        'state': 'open',
        'mode': 'duel',
        'ai_seed': 42,
        'current_round': 1,
        'stake': 45,
        'fold_winner_id': None,
        'pending_spell_id': None,
        'waiting_for_counter_player_id': None,
        'battle_modifier': [],
        'battle_confirmed': False,
        'battle_moves_confirmed': {},
        'battle_round': 0,
        'battle_turn_player_id': None,
        'battle_skipped_rounds': {},
        'battle_moves': [],
        'conquer_tactics': [],
        'battle_decisions': None,
        'advancing_figure_id': None,
        'advancing_figure_id_2': None,
        'advancing_player_id': None,
        'defending_figure_id': None,
        'defending_figure_id_2': None,
        'turn_player_id': ai_id,
        'invader_player_id': ai_id,
        'ceasefire_active': False,
        'players': [
            {
                'id': ai_id,
                'points': 0,
                'turns_left': 4,
                'main_hand': [],
                'side_hand': [],
                'figures': [],
            },
            {
                'id': opp_id,
                'points': 0,
                'turns_left': 0,
                'main_hand': [],
                'side_hand': [],
                'figures': [],
            },
        ],
    }


def _rng(seed=42):
    return random.Random(seed)


# ── choose_action dispatcher ─────────────────────────────────────────

def test_choose_action_returns_only_action_immediately():
    actions = [{'id': 1, 'type': 'noop', 'description': 'only', 'params': {}}]
    chosen = duel_strategy.choose_action(
        _base_game_dict(), 1, 'normal_turn', actions, _rng(),
    )
    assert chosen is actions[0]


def test_choose_action_raises_on_empty_actions():
    with pytest.raises(ValueError):
        duel_strategy.choose_action(_base_game_dict(), 1, 'normal_turn', [], _rng())


def test_choose_action_unknown_phase_returns_first_action():
    actions = [
        {'id': 1, 'type': 'foo', 'description': '', 'params': {}},
        {'id': 2, 'type': 'bar', 'description': '', 'params': {}},
    ]
    chosen = duel_strategy.choose_action(
        _base_game_dict(), 1, 'no_such_phase', actions, _rng(),
    )
    assert chosen is actions[0]


# ── Determinism (replay) ─────────────────────────────────────────────

def test_select_defender_is_deterministic_for_fixed_seed():
    game = _base_game_dict()
    game['players'][1]['figures'] = [
        {'id': 10, 'name': 'A', 'field': 'village', 'suit': 'Hearts',
         'cards': [{'value': 3}, {'value': 4}]},
        {'id': 11, 'name': 'B', 'field': 'military', 'suit': 'Spades',
         'cards': [{'value': 8}, {'value': 9}]},
        {'id': 12, 'name': 'C', 'field': 'castle', 'suit': 'Diamonds'},
    ]
    actions = [
        {'id': 1, 'type': 'select_defender', 'description': 'A',
         'params': {'figure_id': 10}},
        {'id': 2, 'type': 'select_defender', 'description': 'B',
         'params': {'figure_id': 11}},
        {'id': 3, 'type': 'select_defender', 'description': 'C',
         'params': {'figure_id': 12}},
    ]
    first = duel_strategy.choose_action(game, 1, 'select_defender', actions, _rng(123))
    again = duel_strategy.choose_action(game, 1, 'select_defender', actions, _rng(123))
    assert first['id'] == again['id']


def test_select_defender_prefers_weaker_targets():
    game = _base_game_dict()
    # Three opponent figures with sharply different power.
    game['players'][1]['figures'] = [
        {'id': 10, 'name': 'Weak', 'field': 'village', 'suit': 'Hearts',
         'cards_to_figure': [{'card_value': 2}, {'card_value': 3}]},  # power 5
        {'id': 11, 'name': 'Mid', 'field': 'village', 'suit': 'Spades',
         'cards_to_figure': [{'card_value': 8}, {'card_value': 9}]},  # power 17
        {'id': 12, 'name': 'Castle', 'field': 'castle', 'suit': 'Diamonds'},  # power 15
    ]
    actions = [
        {'id': 1, 'type': 'select_defender', 'description': '',
         'params': {'figure_id': 10}},
        {'id': 2, 'type': 'select_defender', 'description': '',
         'params': {'figure_id': 11}},
        {'id': 3, 'type': 'select_defender', 'description': '',
         'params': {'figure_id': 12}},
    ]
    # Run 100 trials with different seeds; weakest should win most of the time
    weakest_wins = 0
    for s in range(100):
        chosen = duel_strategy.choose_action(
            game, 1, 'select_defender', actions, _rng(s),
        )
        if chosen['id'] == 1:
            weakest_wins += 1
    assert weakest_wins >= 70, (
        f"expected weakest to win most often, got {weakest_wins}/100"
    )


# ── battle_decision ─────────────────────────────────────────────────

def _battle_decision_actions():
    return [
        {'id': 1, 'type': 'battle_decision', 'description': '',
         'params': {'decision': 'battle'}},
        {'id': 2, 'type': 'battle_decision', 'description': '',
         'params': {'decision': 'fold'}},
    ]


def test_battle_decision_folds_when_clearly_outmatched():
    game = _base_game_dict()
    game['advancing_figure_id'] = 100
    game['defending_figure_id'] = 200
    game['advancing_player_id'] = 2  # opponent advanced, AI defends
    game['players'][0]['figures'] = [
        {'id': 200, 'field': 'village', 'suit': 'Hearts',
         'cards_to_figure': [{'card_value': 2}]},  # weak own figure
    ]
    game['players'][1]['figures'] = [
        {'id': 100, 'field': 'castle', 'suit': 'Spades'},  # castle = 15
    ]
    game['players'][0]['main_hand'] = []  # no battle cards
    game['players'][1]['num_main'] = 8     # opponent has many cards

    chosen = duel_strategy.choose_action(
        game, 1, 'battle_decision', _battle_decision_actions(), _rng(),
    )
    assert chosen['params']['decision'] == 'fold'


def test_battle_decision_fights_when_clearly_ahead():
    game = _base_game_dict()
    game['advancing_figure_id'] = 100
    game['defending_figure_id'] = 200
    game['advancing_player_id'] = 1  # AI invader
    game['players'][0]['figures'] = [
        {'id': 100, 'field': 'castle', 'suit': 'Spades'},  # castle = 15
    ]
    game['players'][1]['figures'] = [
        {'id': 200, 'field': 'village', 'suit': 'Hearts',
         'cards_to_figure': [{'card_value': 2}]},
    ]
    game['players'][0]['main_hand'] = [
        {'id': 1, 'rank': 'K', 'suit': 'Spades', 'value': 4},
        {'id': 2, 'rank': 'A', 'suit': 'Hearts', 'value': 3},
        {'id': 3, 'rank': 'Q', 'suit': 'Clubs', 'value': 2},
    ]
    game['players'][1]['num_main'] = 0

    chosen = duel_strategy.choose_action(
        game, 1, 'battle_decision', _battle_decision_actions(), _rng(),
    )
    assert chosen['params']['decision'] == 'battle'


# ── counter_spell ────────────────────────────────────────────────────

def test_counter_spell_allows_when_cards_missing():
    actions = [
        {'id': 1, 'type': 'allow_spell', 'description': '',
         'params': {'pending_spell_id': 7}},
        {'id': 2, 'type': 'counter_spell', 'description': '',
         'params': {
             'pending_spell_id': 7,
             'counter_spell_name': 'Blitzkrieg',
             'counter_cards': [],  # no cards held
         }},
    ]
    chosen = duel_strategy.choose_action(
        _base_game_dict(), 1, 'counter_spell', actions, _rng(),
    )
    assert chosen['type'] == 'allow_spell'


def test_counter_spell_counters_high_harm_when_cards_available():
    actions = [
        {'id': 1, 'type': 'allow_spell', 'description': '',
         'params': {'pending_spell_id': 7}},
        {'id': 2, 'type': 'counter_spell', 'description': '',
         'params': {
             'pending_spell_id': 7,
             'counter_spell_name': 'Invader Swap',  # base harm 8
             'counter_cards': [
                 {'id': 100, 'rank': 'A', 'suit': 'Hearts', 'value': 3},
                 {'id': 101, 'rank': 'A', 'suit': 'Diamonds', 'value': 3},
             ],
         }},
    ]
    chosen = duel_strategy.choose_action(
        _base_game_dict(), 1, 'counter_spell', actions, _rng(),
    )
    assert chosen['type'] == 'counter_spell'


def test_counter_spell_allows_low_harm_even_with_cards():
    actions = [
        {'id': 1, 'type': 'allow_spell', 'description': '',
         'params': {'pending_spell_id': 7}},
        {'id': 2, 'type': 'counter_spell', 'description': '',
         'params': {
             'pending_spell_id': 7,
             'counter_spell_name': 'NonExistentLowHarmSpell',  # base 3 → below threshold
             'counter_cards': [{'id': 1, 'rank': 'J', 'suit': 'Hearts', 'value': 1}],
         }},
    ]
    chosen = duel_strategy.choose_action(
        _base_game_dict(), 1, 'counter_spell', actions, _rng(),
    )
    assert chosen['type'] == 'allow_spell'


# ── battle_round ────────────────────────────────────────────────────

def test_battle_round_picks_strongest_play_move():
    game = _base_game_dict()
    game['battle_round'] = 0
    game['players'][0]['figures'] = [
        {'id': 50, 'field': 'military', 'suit': 'Spades',
         'cards_to_figure': [{'card_value': 9}, {'card_value': 9}]},  # power 18
    ]
    game['battle_moves'] = [
        {'id': 1, 'player_id': 1, 'family_name': 'Dagger',
         'value': 9, 'suit': 'Hearts', 'played_round': None},
        {'id': 2, 'player_id': 1, 'family_name': 'Call Military',
         'value': 3, 'suit': 'Spades', 'call_figure_id': 50, 'played_round': None},
    ]
    actions = [
        {'id': 1, 'type': 'play_battle_move', 'description': '',
         'params': {'battle_move_id': 1}},
        {'id': 2, 'type': 'play_battle_move', 'description': '',
         'params': {'battle_move_id': 2, 'call_figure_id': 50}},
    ]
    chosen = duel_strategy.choose_action(
        game, 1, 'battle_round', actions, _rng(7),
    )
    assert chosen['params']['battle_move_id'] == 2  # call_military scores higher


def test_battle_round_block_scores_high_against_strong_opponent_move():
    game = _base_game_dict()
    game['battle_round'] = 0
    # Opponent played a strong move this round
    game['battle_moves'] = [
        {'id': 99, 'player_id': 2, 'family_name': 'Dagger',
         'value': 10, 'suit': 'Hearts', 'played_round': 0},
        {'id': 1, 'player_id': 1, 'family_name': 'Block',
         'value': 2, 'suit': 'Clubs', 'played_round': None},
        {'id': 2, 'player_id': 1, 'family_name': 'Dagger',
         'value': 7, 'suit': 'Spades', 'played_round': None},
    ]
    actions = [
        {'id': 1, 'type': 'play_battle_move', 'description': '',
         'params': {'battle_move_id': 1}},  # Block, scores opp's 10
        {'id': 2, 'type': 'play_battle_move', 'description': '',
         'params': {'battle_move_id': 2}},  # Dagger value 7
    ]
    chosen = duel_strategy.choose_action(
        game, 1, 'battle_round', actions, _rng(0),
    )
    assert chosen['params']['battle_move_id'] == 1  # Block wins over weak Dagger


def test_battle_round_gambles_weak_move_below_threshold():
    """If any play move scores below the gamble threshold and a corresponding
    gamble action exists, the AI prefers to gamble the weakest one rather
    than play it."""
    game = _base_game_dict()
    game['battle_round'] = 0
    game['players'][0]['figures'] = []
    game['battle_moves'] = [
        {'id': 10, 'player_id': 1, 'family_name': 'Dagger',
         'value': 7, 'suit': 'Hearts', 'played_round': None},
        {'id': 11, 'player_id': 1, 'family_name': 'Dagger',
         'value': 8, 'suit': 'Spades', 'played_round': None},
    ]
    actions = [
        {'id': 1, 'type': 'play_battle_move', 'description': '',
         'params': {'battle_move_id': 10}},
        {'id': 2, 'type': 'play_battle_move', 'description': '',
         'params': {'battle_move_id': 11}},
        {'id': 3, 'type': 'gamble_battle_move', 'description': '',
         'params': {'battle_move_id': 10}},
        {'id': 4, 'type': 'gamble_battle_move', 'description': '',
         'params': {'battle_move_id': 11}},
    ]
    chosen = duel_strategy.choose_action(
        game, 1, 'battle_round', actions, _rng(),
    )
    assert chosen['type'] == 'gamble_battle_move'
    # Weakest move (Dagger 7, score 7) should be the gamble target, not the
    # stronger Dagger 8.
    assert chosen['params']['battle_move_id'] == 10


def test_battle_round_does_not_gamble_strong_moves():
    """If all play moves score at or above the threshold, the AI plays them."""
    game = _base_game_dict()
    game['battle_round'] = 0
    game['players'][0]['figures'] = []
    game['battle_moves'] = [
        # Both Daggers are at threshold (11) — should play, not gamble.
        {'id': 10, 'player_id': 1, 'family_name': 'Dagger',
         'value': 11, 'suit': 'Hearts', 'played_round': None},
        {'id': 11, 'player_id': 1, 'family_name': 'Dagger',
         'value': 12, 'suit': 'Spades', 'played_round': None},
    ]
    actions = [
        {'id': 1, 'type': 'play_battle_move', 'description': '',
         'params': {'battle_move_id': 10}},
        {'id': 2, 'type': 'play_battle_move', 'description': '',
         'params': {'battle_move_id': 11}},
        {'id': 3, 'type': 'gamble_battle_move', 'description': '',
         'params': {'battle_move_id': 10}},
        {'id': 4, 'type': 'gamble_battle_move', 'description': '',
         'params': {'battle_move_id': 11}},
    ]
    chosen = duel_strategy.choose_action(
        game, 1, 'battle_round', actions, _rng(),
    )
    assert chosen['type'] == 'play_battle_move'


def test_battle_round_gambles_call_without_eligible_figure():
    """A Call move with no matching figure has effective value = card value
    only. If that's below the threshold, gamble it (these are the cleanest
    'burn for fresh draws' targets)."""
    game = _base_game_dict()
    game['battle_round'] = 0
    game['players'][0]['figures'] = []  # no military figure to call
    game['battle_moves'] = [
        {'id': 20, 'player_id': 1, 'family_name': 'Call Military',
         'value': 3, 'suit': 'Hearts', 'played_round': None},
        # Strong play to keep
        {'id': 21, 'player_id': 1, 'family_name': 'Dagger',
         'value': 12, 'suit': 'Spades', 'played_round': None},
    ]
    actions = [
        {'id': 1, 'type': 'play_battle_move', 'description': '',
         'params': {'battle_move_id': 20}},
        {'id': 2, 'type': 'play_battle_move', 'description': '',
         'params': {'battle_move_id': 21}},
        {'id': 3, 'type': 'gamble_battle_move', 'description': '',
         'params': {'battle_move_id': 20}},
    ]
    chosen = duel_strategy.choose_action(
        game, 1, 'battle_round', actions, _rng(),
    )
    assert chosen['type'] == 'gamble_battle_move'
    assert chosen['params']['battle_move_id'] == 20


def test_battle_round_combines_dagger_pair_before_playing():
    """Same-colour Dagger pairs should be combined during the battle round
    (frees a slot and yields a stronger move) before any play action."""
    game = _base_game_dict()
    game['battle_round'] = 0
    game['battle_moves'] = [
        {'id': 30, 'player_id': 1, 'family_name': 'Dagger',
         'value': 10, 'suit': 'Hearts', 'played_round': None},
        {'id': 31, 'player_id': 1, 'family_name': 'Dagger',
         'value': 9, 'suit': 'Diamonds', 'played_round': None},
    ]
    actions = [
        {'id': 1, 'type': 'play_battle_move', 'description': '',
         'params': {'battle_move_id': 30}},
        {'id': 2, 'type': 'play_battle_move', 'description': '',
         'params': {'battle_move_id': 31}},
        {'id': 3, 'type': 'combine_battle_moves',
         'description': 'Combine Dagger(10) + Dagger(9) → Double Dagger (power=19) — frees 1 move slot!',
         'params': {'move_id_a': 30, 'move_id_b': 31}},
    ]
    chosen = duel_strategy.choose_action(
        game, 1, 'battle_round', actions, _rng(),
    )
    assert chosen['type'] == 'combine_battle_moves'


def test_battle_round_gamble_runs_before_combine():
    """Gamble has priority over combine: matches conquer ordering."""
    game = _base_game_dict()
    game['battle_round'] = 0
    game['battle_moves'] = [
        {'id': 40, 'player_id': 1, 'family_name': 'Dagger',
         'value': 7, 'suit': 'Hearts', 'played_round': None},
        {'id': 41, 'player_id': 1, 'family_name': 'Dagger',
         'value': 8, 'suit': 'Diamonds', 'played_round': None},
    ]
    actions = [
        {'id': 1, 'type': 'play_battle_move', 'description': '',
         'params': {'battle_move_id': 40}},
        {'id': 2, 'type': 'play_battle_move', 'description': '',
         'params': {'battle_move_id': 41}},
        {'id': 3, 'type': 'gamble_battle_move', 'description': '',
         'params': {'battle_move_id': 40}},
        {'id': 4, 'type': 'gamble_battle_move', 'description': '',
         'params': {'battle_move_id': 41}},
        {'id': 5, 'type': 'combine_battle_moves',
         'description': 'Combine Dagger(7) + Dagger(8) → Double Dagger (power=15) — frees 1 move slot!',
         'params': {'move_id_a': 40, 'move_id_b': 41}},
    ]
    chosen = duel_strategy.choose_action(
        game, 1, 'battle_round', actions, _rng(),
    )
    assert chosen['type'] == 'gamble_battle_move'
    assert chosen['params']['battle_move_id'] == 40  # weakest first


def test_battle_round_plays_weakest_non_block_when_opponent_blocked():
    """When the opponent has already played Block this round, the round
    is neutralised — preserve strong cards by playing the weakest non-Block.
    """
    game = _base_game_dict()
    game['battle_round'] = 0
    game['battle_moves'] = [
        # Opponent's Block from this round (player_id=2)
        {'id': 99, 'player_id': 2, 'family_name': 'Block',
         'value': 2, 'suit': 'Clubs', 'played_round': 0},
        # Our moves
        {'id': 50, 'player_id': 1, 'family_name': 'Dagger',
         'value': 7, 'suit': 'Hearts', 'played_round': None},
        {'id': 51, 'player_id': 1, 'family_name': 'Dagger',
         'value': 10, 'suit': 'Spades', 'played_round': None},
    ]
    actions = [
        {'id': 1, 'type': 'play_battle_move', 'description': '',
         'params': {'battle_move_id': 50}},  # weakest
        {'id': 2, 'type': 'play_battle_move', 'description': '',
         'params': {'battle_move_id': 51}},  # strongest, save for later
    ]
    chosen = duel_strategy.choose_action(
        game, 1, 'battle_round', actions, _rng(),
    )
    assert chosen['type'] == 'play_battle_move'
    assert chosen['params']['battle_move_id'] == 50


def test_battle_round_block_tiebreak_when_strongest_cannot_beat_opp():
    """If we hold Block AND the strongest non-Block can't beat the
    opponent's known value, play Block to neutralise."""
    game = _base_game_dict()
    game['battle_round'] = 0
    game['battle_moves'] = [
        # Opponent played a Dagger 10
        {'id': 99, 'player_id': 2, 'family_name': 'Dagger',
         'value': 10, 'suit': 'Hearts', 'played_round': 0},
        # Our: Block (Q) and Dagger 7 (can't beat 10)
        {'id': 60, 'player_id': 1, 'family_name': 'Block',
         'value': 2, 'suit': 'Spades', 'played_round': None},
        {'id': 61, 'player_id': 1, 'family_name': 'Dagger',
         'value': 7, 'suit': 'Clubs', 'played_round': None},
    ]
    actions = [
        {'id': 1, 'type': 'play_battle_move', 'description': '',
         'params': {'battle_move_id': 60}},
        {'id': 2, 'type': 'play_battle_move', 'description': '',
         'params': {'battle_move_id': 61}},
    ]
    chosen = duel_strategy.choose_action(
        game, 1, 'battle_round', actions, _rng(),
    )
    assert chosen['type'] == 'play_battle_move'
    assert chosen['params']['battle_move_id'] == 60  # Block


def test_battle_round_skip_when_only_skip_offered():
    """When the only action is skip_battle_turn (no plays, no gambles), take it.

    In real play, action_enum only emits skip when there are no remaining
    moves at all — so gamble and skip are mutually exclusive. This test
    just confirms skip wins in its own when offered alone.
    """
    actions = [
        {'id': 1, 'type': 'skip_battle_turn', 'description': '', 'params': {}},
    ]
    chosen = duel_strategy.choose_action(
        _base_game_dict(), 1, 'battle_round', actions, _rng(),
    )
    assert chosen['type'] == 'skip_battle_turn'


# ── battle_shop ──────────────────────────────────────────────────────

def test_battle_shop_prefers_confirm_over_buy():
    actions = [
        {'id': 1, 'type': 'buy_battle_move', 'description': '',
         'params': {'card_id': 1, 'family_name': 'Dagger', 'rank': '9',
                    'suit': 'Hearts', 'value': 9}},
        {'id': 2, 'type': 'confirm_battle_moves', 'description': '', 'params': {}},
    ]
    chosen = duel_strategy.choose_action(
        _base_game_dict(), 1, 'battle_shop', actions, _rng(),
    )
    assert chosen['type'] == 'confirm_battle_moves'


def test_battle_shop_prefers_high_value_buy():
    """When only buys offered, higher-ranked card wins most of the time."""
    actions = [
        {'id': 1, 'type': 'buy_battle_move', 'description': '',
         'params': {'card_id': 1, 'family_name': 'Dagger', 'rank': '7',
                    'suit': 'Hearts', 'value': 7}},
        {'id': 2, 'type': 'buy_battle_move', 'description': '',
         'params': {'card_id': 2, 'family_name': 'Dagger', 'rank': '10',
                    'suit': 'Hearts', 'value': 10}},
    ]
    wins_high = 0
    for s in range(50):
        chosen = duel_strategy.choose_action(
            _base_game_dict(), 1, 'battle_shop', actions, _rng(s),
        )
        if chosen['params']['rank'] == '10':
            wins_high += 1
    assert wins_high >= 40, f"expected high-rank wins most often, got {wins_high}/50"


def test_battle_shop_prefers_combine_over_buy():
    actions = [
        {'id': 1, 'type': 'buy_battle_move', 'description': '',
         'params': {'card_id': 1, 'family_name': 'Dagger', 'rank': '8',
                    'suit': 'Hearts', 'value': 8}},
        {'id': 2, 'type': 'combine_battle_moves',
         'description': 'Combine Dagger(9) + Dagger(7) → Double Dagger (power=16) — frees 1 move slot!',
         'params': {'move_id_a': 10, 'move_id_b': 11}},
    ]
    chosen = duel_strategy.choose_action(
        _base_game_dict(), 1, 'battle_shop', actions, _rng(),
    )
    assert chosen['type'] == 'combine_battle_moves'


# ── Tuning constants ────────────────────────────────────────────────

def test_normal_turn_decisiveness_constants():
    """The normal_turn handler is the most strategic decision point;
    its softmax must be biased toward the top-scoring plan so the AI
    doesn't sample weak alternatives like change_cards over a clear
    build line. Sanity check the tuned constants."""
    assert duel_strategy.NORMAL_TURN_TEMPERATURE <= 0.2
    assert duel_strategy.NORMAL_TURN_TOP_K <= 3
