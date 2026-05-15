# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for bounded strategy planner output."""

from ai.strategy_planner import (
    _action_feasibility,
    _modifier_bonus,
    _score_plan,
    format_strategy_plans_for_prompt,
    generate_strategy_plans,
    recommended_action_id,
)


def _planner_game_dict():
    return {
        'id': 120,
        'invader_player_id': 2,
        'battle_modifier': [],
        'battle_moves': [],
        'players': [
            {
                'id': 1,
                'username': '[AI] Strategos',
                'turns_left': 3,
                'main_hand': [
                    {'id': 1, 'rank': 'K', 'suit': 'Hearts', 'value': 4, 'part_of_figure': False, 'part_of_battle_move': False},
                    {'id': 2, 'rank': '10', 'suit': 'Hearts', 'value': 10, 'part_of_figure': False, 'part_of_battle_move': False},
                    {'id': 3, 'rank': '9', 'suit': 'Hearts', 'value': 9, 'part_of_figure': False, 'part_of_battle_move': False},
                ],
                'side_hand': [],
                'figures': [
                    {
                        'id': 101,
                        'name': 'Djungle King',
                        'family_name': 'Djungle King',
                        'field': 'castle',
                        'suit': 'Hearts',
                        'cards': [{'value': 15}],
                        'produces': {'villager_red': 2, 'warrior_red': 1},
                        'requires': {},
                    }
                ],
            },
            {
                'id': 2,
                'username': 'human',
                'turns_left': 3,
                'main_hand': [],
                'side_hand': [],
                'figures': [
                    {
                        'id': 201,
                        'name': 'Opp Military',
                        'family_name': 'Gorkha Warriors',
                        'field': 'military',
                        'suit': 'Hearts',
                        'cards': [{'value': 3}, {'value': 8}],
                        'produces': {},
                        'requires': {'warrior_red': 1, 'food_red': 8},
                    }
                ],
            },
        ],
        'main_cards': [
            {'rank': 'A', 'suit': 'Hearts', 'in_deck': True},
            {'rank': 'J', 'suit': 'Hearts', 'in_deck': True},
            {'rank': '7', 'suit': 'Hearts', 'in_deck': True},
        ],
        'side_cards': [
            {'rank': '2', 'suit': 'Hearts', 'in_deck': True},
            {'rank': '3', 'suit': 'Hearts', 'in_deck': True},
        ],
    }


def test_generate_strategy_plans_is_bounded_and_sorted():
    game = _planner_game_dict()
    actions = [
        {'id': 1, 'type': 'change_cards', 'description': 'change weak cards', 'params': {}},
        {'id': 2, 'type': 'advance_figure', 'description': 'advance king', 'params': {'figure_id': 101}},
        {'id': 3, 'type': 'cast_spell', 'description': 'Cast Blitzkrieg', 'params': {'spell_name': 'Blitzkrieg'}},
    ]

    plans = generate_strategy_plans(game, ai_player_id=1, phase='normal_turn', actions=actions, max_plans=2)

    assert len(plans) == 2
    assert plans[0]['total_score'] >= plans[1]['total_score']


def test_generate_strategy_plans_emits_turn_steps_for_remaining_horizon():
    game = _planner_game_dict()
    actions = [
        {'id': 2, 'type': 'advance_figure', 'description': 'advance king', 'params': {'figure_id': 101}},
    ]

    plans = generate_strategy_plans(game, ai_player_id=1, phase='normal_turn', actions=actions, max_plans=1)

    assert len(plans) == 1
    assert plans[0]['horizon_turns'] == 3
    assert len(plans[0]['turn_steps']) == 3


def test_generate_strategy_plans_uses_conquer_tactics_for_tactics_hand():
    game = _planner_game_dict()
    game['mode'] = 'conquer'
    game['conquer_move_model'] = 'tactics_hand'
    game['conquer_tactics'] = [
        {
            'id': 41,
            'player_id': 1,
            'family_name': 'Dagger',
            'rank': '7',
            'suit': 'Hearts',
            'value': 7,
            'source': 'config',
            'status': 'available',
            'sort_order': 2,
        },
        {
            'id': 42,
            'player_id': 1,
            'family_name': 'Dagger',
            'rank': '10',
            'suit': 'Spades',
            'value': 10,
            'source': 'spell',
            'status': 'available',
            'sort_order': 1,
        },
        {
            'id': 43,
            'player_id': 1,
            'family_name': 'Block',
            'rank': 'Q',
            'suit': 'Clubs',
            'value': 2,
            'source': 'config',
            'status': 'played',
            'sort_order': 3,
        },
    ]
    actions = [
        {'id': 2, 'type': 'advance_figure', 'description': 'advance king', 'params': {'figure_id': 101}},
    ]

    plans = generate_strategy_plans(game, ai_player_id=1, phase='normal_turn', actions=actions, max_plans=1)

    assert len(plans) == 1
    assert [t['id'] for t in plans[0]['planned_conquer_tactics']] == [42, 41]
    assert plans[0]['planned_battle_moves'] == plans[0]['planned_conquer_tactics']
    assert plans[0]['expected_tactic_power'] == 17.0

    prompt_text = format_strategy_plans_for_prompt(plans)
    assert 'planned_conquer_tactics:' in prompt_text
    assert 'planned_moves:' not in prompt_text


def test_format_strategy_plans_for_prompt_includes_plan_and_turn_markers():
    plans = [
        {
            'plan_id': 1,
            'seed_action_id': 2,
            'total_score': 4.25,
            'feasibility_probability': 0.9,
            'planned_battle_figure': {'name': 'Djungle King', 'field': 'castle', 'state': 'already_built', 'power_estimate': 15},
            'likely_opponent_figure': {'name': 'Opp Military', 'power_estimate': 11, 'probability': 0.6},
            'planned_battle_moves': [{'rank': '10', 'suit': 'Hearts', 'value': 10}],
            'turn_steps': ['execute now: advance king', 'select defender', 'battle decision'],
            'notes': ['opponent likely commits Opp Military'],
        }
    ]

    text = format_strategy_plans_for_prompt(plans)

    assert 'PLAN 1' in text
    assert 'seed_action=2' in text
    assert 'turn_1:' in text
    assert 'turn_3:' in text


def test_recommended_action_id_returns_seed_action_of_best_plan():
    plans = [
        {'seed_action_id': 4, 'total_score': 2.1},
        {'seed_action_id': 2, 'total_score': 2.1},
        {'seed_action_id': 3, 'total_score': 3.2},
    ]

    rec = recommended_action_id(plans)

    assert rec == 3


def test_generate_strategy_plans_forwards_draw_limits_to_target_selection(monkeypatch):
    captured = {}

    def fake_best_figure_targets(
        game_dict,
        ai_player_id,
        remaining_turns=None,
        max_results=6,
        max_main_draws_per_turn=2,
        max_side_draws_per_turn=1,
    ):
        captured['remaining_turns'] = remaining_turns
        captured['max_results'] = max_results
        captured['max_main_draws_per_turn'] = max_main_draws_per_turn
        captured['max_side_draws_per_turn'] = max_side_draws_per_turn
        return [
            {
                'family_name': 'Gorkha Warriors',
                'name': 'Gorkha Warriors',
                'field': 'military',
                'suit': 'Hearts',
                'card_state': 'build_possible_with_probability',
                'power_estimate': 11,
                'completion_probability': 0.6,
                'resource_blocked': False,
                'impossible': False,
            }
        ]

    def fake_belief_snapshot(_game_dict, _ai_player_id):
        return {
            'likely_battle_figures': [
                {'name': 'Opp Military', 'power_estimate': 9, 'probability': 0.6}
            ],
            'active_battle_modifiers': [],
        }

    monkeypatch.setattr('ai.strategy_planner.best_figure_targets', fake_best_figure_targets)
    monkeypatch.setattr('ai.strategy_planner.build_opponent_belief_snapshot', fake_belief_snapshot)

    game = _planner_game_dict()
    actions = [
        {'id': 1, 'type': 'change_cards', 'description': 'change weak cards', 'params': {}},
    ]

    plans = generate_strategy_plans(
        game,
        ai_player_id=1,
        phase='normal_turn',
        actions=actions,
        max_plans=1,
        max_main_draws_per_turn=7,
        max_side_draws_per_turn=3,
    )

    assert len(plans) == 1
    assert captured['remaining_turns'] == 3
    assert captured['max_results'] == 6
    assert captured['max_main_draws_per_turn'] == 7
    assert captured['max_side_draws_per_turn'] == 3


# ──────────────────────────────────────────────────────────────────────
#  Regression tests: verify correct action ranking in representative
#  scenarios so parameter changes don't silently break priorities.
#
#  Each test constructs a minimal but realistic board state, offers the
#  planner exactly the two (or more) actions being compared, and asserts
#  the ranking outcome.  The monkeypatch stubs bypass figure_completion
#  and opponent_model so tests are deterministic and fast.
# ──────────────────────────────────────────────────────────────────────

def _stub_planner(monkeypatch, targets, opp_figs=None):
    """Inject deterministic figure targets and opponent belief."""
    def fake_targets(_g, _pid, **_kw):
        return targets

    def fake_belief(_g, _pid):
        return {
            'likely_battle_figures': opp_figs or [],
            'active_battle_modifiers': [],
        }

    monkeypatch.setattr('ai.strategy_planner.best_figure_targets', fake_targets)
    monkeypatch.setattr('ai.strategy_planner.build_opponent_belief_snapshot', fake_belief)


def _game_with_figures(ai_figures, opp_figures, turns=3, invader_player_id=2):
    """Minimal game dict with custom figures."""
    return {
        'id': 900,
        'invader_player_id': invader_player_id,
        'battle_modifier': [],
        'battle_moves': [],
        'players': [
            {
                'id': 1, 'username': '[AI]', 'turns_left': turns,
                'main_hand': [
                    {'id': 1, 'rank': 'K', 'suit': 'Hearts', 'value': 4,
                     'part_of_figure': False, 'part_of_battle_move': False},
                    {'id': 2, 'rank': '10', 'suit': 'Clubs', 'value': 10,
                     'part_of_figure': False, 'part_of_battle_move': False},
                ],
                'side_hand': [],
                'figures': ai_figures,
            },
            {
                'id': 2, 'username': 'human', 'turns_left': turns,
                'main_hand': [], 'side_hand': [],
                'figures': opp_figures,
            },
        ],
        'main_cards': [], 'side_cards': [],
    }


# ── Scenario 1: high-probability build beats change_cards ────────────

def test_rank_build_over_change_when_high_probability(monkeypatch):
    """When the AI can build a figure right now with high probability, it
    should not waste a turn exchanging cards first.

    Setup:
    - One figure target (Sherpa Guard) with completion_probability=0.85
      and power=10.
    - One opponent figure with power=8 (establishes a positive power diff).
    - Two actions offered: build_figure vs change_cards.

    Why build should win:
    - build_figure gets feasibility=0.85 (from completion_probability)
      and an immediate power diff of +2.
    - change_cards gets feasibility=max(0.35, 0.85)=0.85 too, but its
      turn steps delay the build by one turn, so the scorer's turns_pressure
      and risk_penalty make it slightly worse.
    - More importantly build_figure is the *direct* path — the cards are
      already good enough.

    Regression purpose: prevents parameter changes from making the AI
    procrastinate (swapping cards when it could build immediately).
    """
    target = {
        'family_name': 'Sherpa Guard', 'name': 'Sherpa Guard',
        'field': 'military', 'suit': 'Hearts',
        'card_state': 'build_possible_with_probability',
        'completion_probability': 0.85, 'resource_blocked': False,
        'power_estimate': 10,
    }
    opp = [{'name': 'Opp Fig', 'power_estimate': 8, 'probability': 0.5}]
    _stub_planner(monkeypatch, [target], opp)

    game = _game_with_figures([], [
        {'id': 201, 'name': 'Opp Fig', 'field': 'military', 'suit': 'Diamonds',
         'cards': [{'value': 8}], 'produces': {}, 'requires': {}},
    ])

    actions = [
        {'id': 1, 'type': 'build_figure', 'description': 'build Sherpa Guard power=10',
         'params': {'family_name': 'Sherpa Guard', 'suit': 'Hearts'}},
        {'id': 2, 'type': 'change_cards', 'description': 'change cards', 'params': {}},
    ]

    plans = generate_strategy_plans(game, 1, 'normal_turn', actions, max_plans=2)
    assert plans[0]['seed_action_id'] == 1, (
        'build_figure with high probability should rank above change_cards'
    )


# ── Scenario 2: change_cards tops when build is blocked ──────────────

def test_rank_change_over_blocked_build(monkeypatch):
    """When the only buildable figure is resource-blocked and low probability,
    exchanging cards to improve the hand is the better move.

    Setup:
    - One figure target (Tower) with completion_probability=0.1 and
      resource_blocked=True.
    - No opponent figures (no external pressure).
    - Two actions offered: build_figure vs change_cards.

    Why change_cards should win:
    - build_figure gets feasibility=0.05 (resource_blocked path in
      _action_feasibility) → offensive_value is heavily penalised by
      the risk_penalty = (1-0.05)*4.0 = 3.8.
    - change_cards gets feasibility=max(0.35, 0.1)=0.35 → risk_penalty
      is only (1-0.35)*4.0 = 2.6.  Even though change_cards is indirect,
      its feasibility floor of 0.35 makes it clearly better here.

    Regression purpose: ensures the AI doesn't stubbornly attempt builds
    that are practically impossible.
    """
    target = {
        'family_name': 'Tower', 'name': 'Tower',
        'field': 'building', 'suit': 'Spades',
        'card_state': 'build_possible_with_probability',
        'completion_probability': 0.1, 'resource_blocked': True,
        'power_estimate': 12,
    }
    _stub_planner(monkeypatch, [target])

    game = _game_with_figures([], [])
    actions = [
        {'id': 1, 'type': 'build_figure', 'description': 'build Tower',
         'params': {'family_name': 'Tower', 'suit': 'Spades'}},
        {'id': 2, 'type': 'change_cards', 'description': 'change cards', 'params': {}},
    ]

    plans = generate_strategy_plans(game, 1, 'normal_turn', actions, max_plans=2)
    assert plans[0]['seed_action_id'] == 2, (
        'change_cards should beat a resource-blocked build with p=0.1'
    )


# ── Scenario 3: Blitzkrieg shouldn't always dominate ─────────────────

def test_blitzkrieg_does_not_dominate_strong_build(monkeypatch):
    """Blitzkrieg's +3.5 modifier bonus should not make it score 5× or more
    higher than a near-certain, high-power build.  Both should be competitive.

    Setup:
    - One figure target (Cavalry) with completion_probability=0.95 and
      power=14 — nearly guaranteed and very strong.
    - One weak opponent figure (power=6) → AI's power diff is +8 if it
      builds Cavalry.
    - Two actions: build_figure vs cast_spell (Blitzkrieg).

    Why they should be competitive:
    - build_figure: feasibility=0.95, power_diff=+8, no modifier →
      high offensive_value scaled by strong feasibility.
    - Blitzkrieg: feasibility=0.85 (flat for spells), +3.5 modifier,
      but uses the same target/diff.  The +3.5 adds strategic value
      (attacker picks the defender's figure) but shouldn't dwarf a
      near-certain +8 power advantage.

    The test does NOT assert which wins — only that the ratio stays
    below 5×, preventing one action from becoming a no-brainer.

    Regression purpose: guards against modifier inflation that would
    make the AI always cast Blitzkrieg regardless of board state.
    """
    target = {
        'family_name': 'Cavalry', 'name': 'Cavalry',
        'field': 'military', 'suit': 'Hearts',
        'card_state': 'build_possible_with_probability',
        'completion_probability': 0.95, 'resource_blocked': False,
        'power_estimate': 14,
    }
    opp = [{'name': 'Opp', 'power_estimate': 6, 'probability': 0.4}]
    _stub_planner(monkeypatch, [target], opp)

    game = _game_with_figures([], [
        {'id': 201, 'name': 'Opp', 'field': 'military', 'suit': 'Diamonds',
         'cards': [{'value': 6}], 'produces': {}, 'requires': {}},
    ])

    actions = [
        {'id': 1, 'type': 'build_figure', 'description': 'build Cavalry power=14',
         'params': {'family_name': 'Cavalry', 'suit': 'Hearts'}},
        {'id': 2, 'type': 'cast_spell', 'description': 'Cast Blitzkrieg',
         'params': {'spell_name': 'Blitzkrieg'}},
    ]

    plans = generate_strategy_plans(game, 1, 'normal_turn', actions, max_plans=2)

    scores = [p['total_score'] for p in plans]
    ratio = max(scores) / max(0.01, min(scores)) if min(scores) > 0 else 999
    assert ratio < 5.0, (
        f'Score ratio {ratio:.1f} — one action dominates unreasonably'
    )


# ── Scenario 4: Poison targets the strongest opponent figure ─────────

def test_poison_prefers_strong_target(monkeypatch):
    """Poison should target the opponent's strongest figure because that is
    the figure the opponent is most likely to bring into battle.  Reducing
    a strong battle figure by 6 power is strategically more important than
    weakening a figure the opponent probably won't fight with.

    Setup:
    - Two opponent figures: Strong (power=15) and Weak (power=5).
    - Two Poison actions, one targeting each.
    - A generic AI target figure (power=10) so the score formula has
      something to evaluate power diff against.

    Why Poison on Strong should win:
    - Poison bonus = min(6.0, fig_power * 0.4).
      Strong: min(6.0, 15*0.4) = 6.0.
      Weak: min(6.0, 5*0.4) = 2.0.
    - The 4.0 difference in modifier bonus pushes the Strong-targeted
      plan clearly ahead.
    - This matches real strategy: you poison the figure the opponent
      will most likely use in battle to maximise the power swing.

    Regression purpose: prevents the scorer from treating all Poison
    targets equally (the old flat-bonus approach) or inversely.
    """
    target = {
        'family_name': 'T', 'name': 'T', 'field': 'military', 'suit': 'Hearts',
        'card_state': 'ok', 'completion_probability': 0.5, 'resource_blocked': False,
        'power_estimate': 10,
    }
    _stub_planner(monkeypatch, [target])

    opp_figures = [
        {'id': 301, 'name': 'Strong Fig', 'field': 'military', 'suit': 'Clubs',
         'cards': [{'value': 15}], 'produces': {}, 'requires': {}},
        {'id': 302, 'name': 'Weak Fig', 'field': 'military', 'suit': 'Diamonds',
         'cards': [{'value': 5}], 'produces': {}, 'requires': {}},
    ]
    game = _game_with_figures([], opp_figures)

    actions = [
        {'id': 1, 'type': 'cast_spell',
         'description': 'Spell: Poison on Strong Fig (power≈15)',
         'params': {'spell_name': 'Poison', 'spell_family_name': 'Poison',
                    'target_figure_id': 301}},
        {'id': 2, 'type': 'cast_spell',
         'description': 'Spell: Poison on Weak Fig (power≈5)',
         'params': {'spell_name': 'Poison', 'spell_family_name': 'Poison',
                    'target_figure_id': 302}},
    ]

    plans = generate_strategy_plans(game, 1, 'normal_turn', actions, max_plans=2)
    assert plans[0]['seed_action_id'] == 1, (
        'Poison should prefer the stronger opponent figure'
    )


# ── Scenario 5: Health Boost on strong own figure beats weak one ─────

def test_health_boost_prefers_strong_own_figure(monkeypatch):
    """Health Boost should target the AI's strongest figure because that is
    the figure the AI most likely wants to bring into battle.  Boosting a
    strong figure by +6 increases the expected battle margin; boosting a
    weak figure the AI would fold with anyway is wasted.

    Setup:
    - Two AI figures: Strong Own (power=12) and Weak Own (power=3).
    - Two Health Boost actions, one targeting each.
    - No opponent figures → power diff is purely own-power based.

    Why Health Boost on Strong should win:
    - Health Boost bonus = min(6.0, fig_power * 0.3 + 3.0).
      Strong: min(6.0, 12*0.3 + 3.0) = min(6.0, 6.6) = 6.0.
      Weak: min(6.0, 3*0.3 + 3.0) = min(6.0, 3.9) = 3.9.
    - The 2.1 difference in bonus steers the plan toward the strong
      figure — the one the AI actually plans to fight with.

    Regression purpose: prevents the scorer from treating all Health
    Boost targets equally, which would waste spells on non-battle figures.
    """
    target = {
        'family_name': 'T', 'name': 'T', 'field': 'military', 'suit': 'Hearts',
        'card_state': 'ok', 'completion_probability': 0.5, 'resource_blocked': False,
        'power_estimate': 10,
    }
    _stub_planner(monkeypatch, [target])

    ai_figures = [
        {'id': 101, 'name': 'Strong Own', 'field': 'military', 'suit': 'Hearts',
         'cards': [{'value': 12}], 'produces': {}, 'requires': {}},
        {'id': 102, 'name': 'Weak Own', 'field': 'military', 'suit': 'Clubs',
         'cards': [{'value': 3}], 'produces': {}, 'requires': {}},
    ]
    game = _game_with_figures(ai_figures, [])

    actions = [
        {'id': 1, 'type': 'cast_spell',
         'description': 'Spell: Health Boost on Strong Own (power≈12)',
         'params': {'spell_name': 'Health Boost', 'spell_family_name': 'Health Boost',
                    'target_figure_id': 101}},
        {'id': 2, 'type': 'cast_spell',
         'description': 'Spell: Health Boost on Weak Own (power≈3)',
         'params': {'spell_name': 'Health Boost', 'spell_family_name': 'Health Boost',
                    'target_figure_id': 102}},
    ]

    plans = generate_strategy_plans(game, 1, 'normal_turn', actions, max_plans=2)
    assert plans[0]['seed_action_id'] == 1, (
        'Health Boost should prefer the stronger own figure'
    )


# ── Scenario 6: Explosion values combat power + resource chain ───────

def test_explosion_scores_proportional_to_target_power(monkeypatch):
    """Explosion on a higher-power figure should score higher than on a
    lower-power one when neither produces resources.

    Setup:
    - Two opponent figures: Castle-like (power=15, no production) and
      Weak military (power=5, no production).
    - Two Explosion actions, one targeting each.

    Why Explosion on the stronger figure should win:
    - Explosion bonus = fig_power * 0.4 + resource_value * 1.5.
      Castle-like: 15*0.4 + 0 = 6.0.
      Weak: 5*0.4 + 0 = 2.0.
    - Destroying a 15-power figure removes a much larger threat from
      the board.

    Regression purpose: ensures Explosion doesn't treat all targets
    equally (the old flat-bonus approach had no differentiation at all).
    """
    target = {
        'family_name': 'T', 'name': 'T', 'field': 'military', 'suit': 'Hearts',
        'card_state': 'ok', 'completion_probability': 0.5, 'resource_blocked': False,
        'power_estimate': 10,
    }
    _stub_planner(monkeypatch, [target])

    opp_figures = [
        {'id': 301, 'name': 'Castle', 'field': 'castle', 'suit': 'Hearts',
         'cards': [{'value': 15}], 'produces': {}, 'requires': {}},
        {'id': 302, 'name': 'Weak', 'field': 'military', 'suit': 'Diamonds',
         'cards': [{'value': 5}], 'produces': {}, 'requires': {}},
    ]
    game = _game_with_figures([], opp_figures)

    actions = [
        {'id': 1, 'type': 'cast_spell',
         'description': 'Spell: Explosion on Castle (power≈15)',
         'params': {'spell_name': 'Explosion', 'spell_family_name': 'Explosion',
                    'target_figure_id': 301}},
        {'id': 2, 'type': 'cast_spell',
         'description': 'Spell: Explosion on Weak (power≈5)',
         'params': {'spell_name': 'Explosion', 'spell_family_name': 'Explosion',
                    'target_figure_id': 302}},
    ]

    plans = generate_strategy_plans(game, 1, 'normal_turn', actions, max_plans=2)
    assert plans[0]['seed_action_id'] == 1, (
        'Explosion should strongly prefer the high-power opponent figure'
    )


# ── Scenario 6b: Explosion prefers resource producer over raw power ──

def test_explosion_prefers_resource_producer(monkeypatch):
    """A resource-producing figure should be a more attractive Explosion
    target than a slightly stronger pure-military figure, because
    destroying the producer breaks the opponent's resource chain.

    Setup:
    - Opponent has two figures:
      * Producer (power=8, produces villager_red=2, warrior_red=1)
        → total production = 3 resource units.
      * Military (power=10, produces nothing).
    - Two Explosion actions, one targeting each.

    Why Explosion on Producer should win:
    - Producer bonus: 8*0.4 + 3*1.5 = 3.2 + 4.5 = 7.7.
    - Military bonus: 10*0.4 + 0*1.5 = 4.0.
    - The resource chain value (4.5) makes the producer a higher-priority
      target despite lower raw power.  In practice, crippling the
      opponent's economy prevents them from building future figures.

    Regression purpose: ensures the Explosion scorer accounts for
    tactical/economic disruption, not just combat power.
    """
    target = {
        'family_name': 'T', 'name': 'T', 'field': 'military', 'suit': 'Hearts',
        'card_state': 'ok', 'completion_probability': 0.5, 'resource_blocked': False,
        'power_estimate': 10,
    }
    _stub_planner(monkeypatch, [target])

    opp_figures = [
        {'id': 401, 'name': 'Producer', 'field': 'building', 'suit': 'Hearts',
         'cards': [{'value': 8}],
         'produces': {'villager_red': 2, 'warrior_red': 1}, 'requires': {}},
        {'id': 402, 'name': 'Military', 'field': 'military', 'suit': 'Diamonds',
         'cards': [{'value': 10}],
         'produces': {}, 'requires': {}},
    ]
    game = _game_with_figures([], opp_figures)

    actions = [
        {'id': 1, 'type': 'cast_spell',
         'description': 'Spell: Explosion on Producer (power≈8)',
         'params': {'spell_name': 'Explosion', 'spell_family_name': 'Explosion',
                    'target_figure_id': 401}},
        {'id': 2, 'type': 'cast_spell',
         'description': 'Spell: Explosion on Military (power≈10)',
         'params': {'spell_name': 'Explosion', 'spell_family_name': 'Explosion',
                    'target_figure_id': 402}},
    ]

    plans = generate_strategy_plans(game, 1, 'normal_turn', actions, max_plans=2)
    assert plans[0]['seed_action_id'] == 1, (
        'Explosion should prefer the resource producer over pure military'
    )


# ── Scenario 7: change_cards targets highest EV figure ───────────────

def test_change_cards_targets_highest_ev_figure(monkeypatch):
    """The change_cards action should aim for the figure with the highest
    expected value (probability × power), not just the highest-probability
    or highest-power figure.  This steers the card exchange toward the
    goal that benefits most from fresh cards.

    Setup:
    - Two figure targets:
      * Low Prob High Power: p=0.2, power=14 → EV = 2.8.
      * High Prob Med Power: p=0.7, power=10 → EV = 7.0.
    - One change_cards action.

    Why High Prob Med Power should be picked:
    - The _estimate_target_figure_for_action function for change_cards
      picks the target with max(completion_probability * power).
    - 0.7 × 10 = 7.0 > 0.2 × 14 = 2.8.
    - This is the figure that most benefits from the card exchange:
      it's already relatively close to completion AND has decent power.

    Regression purpose: prevents the target selection from falling back
    to just picking the first target in the list (which could be sorted
    by a different criterion in figure_completion).
    """
    targets = [
        {
            'family_name': 'Low', 'name': 'Low Prob High Power',
            'field': 'military', 'suit': 'Hearts',
            'card_state': 'ok', 'completion_probability': 0.2,
            'resource_blocked': False, 'power_estimate': 14,
        },
        {
            'family_name': 'High', 'name': 'High Prob Med Power',
            'field': 'military', 'suit': 'Clubs',
            'card_state': 'ok', 'completion_probability': 0.7,
            'resource_blocked': False, 'power_estimate': 10,
        },
    ]
    _stub_planner(monkeypatch, targets)

    game = _game_with_figures([], [])
    actions = [
        {'id': 1, 'type': 'change_cards', 'description': 'change cards', 'params': {}},
    ]

    plans = generate_strategy_plans(game, 1, 'normal_turn', actions, max_plans=1)
    fig = plans[0].get('planned_battle_figure', {})
    # 0.7*10 = 7.0 > 0.2*14 = 2.8 → should pick "High Prob Med Power"
    assert fig.get('name') == 'High Prob Med Power', (
        f"Expected 'High Prob Med Power' but got '{fig.get('name')}'"
    )


# ── Unit tests: _modifier_bonus state-dependent behaviour ────────────

def test_modifier_bonus_poison_scales_with_target_power():
    """Poison bonus should be larger for stronger opponent figures.

    The formula is min(6.0, fig_power * 0.4):
    - Weak figure (power=4): bonus = 4 * 0.4 = 1.6.
    - Strong figure (power=14): bonus = min(6.0, 14 * 0.4) = 5.6.

    This ensures the AI prefers to poison the opponent's strongest
    (most likely battle) figure rather than wasting Poison on a
    weak one that won't be used in battle anyway.
    """
    action = {
        'type': 'cast_spell',
        'description': 'Spell: Poison',
        'params': {'spell_family_name': 'Poison', 'target_figure_id': 10},
    }
    weak_figs = [{'id': 10, 'field': 'military', 'cards': [{'value': 4}]}]
    strong_figs = [{'id': 10, 'field': 'military', 'cards': [{'value': 14}]}]

    bonus_weak = _modifier_bonus(action, [], opp_figures=weak_figs)
    bonus_strong = _modifier_bonus(action, [], opp_figures=strong_figs)
    assert bonus_strong > bonus_weak


def test_modifier_bonus_explosion_proportional():
    """Explosion bonus should scale with target power AND resource production.

    Pure combat power:
    - Castle (power=15, no production): bonus = 15 * 0.4 + 0 = 6.0.
    - Weak fig (power=5, no production): bonus = 5 * 0.4 + 0 = 2.0.

    The castle bonus should be more than 2× the weak figure bonus,
    validating that Explosion prioritises high-threat targets.
    """
    action = {
        'type': 'cast_spell',
        'description': 'Spell: Explosion',
        'params': {'spell_family_name': 'Explosion', 'target_figure_id': 20},
    }

    castle = [{'id': 20, 'field': 'castle', 'cards': [{'value': 15}],
               'produces': {}, 'requires': {}}]
    weak = [{'id': 20, 'field': 'military', 'cards': [{'value': 5}],
             'produces': {}, 'requires': {}}]

    bonus_castle = _modifier_bonus(action, [], opp_figures=castle)
    bonus_weak = _modifier_bonus(action, [], opp_figures=weak)
    assert bonus_castle > 2 * bonus_weak


def test_modifier_bonus_explosion_values_resource_production():
    """Explosion bonus should include a resource-chain disruption component.

    A figure with power=6 but producing 3 resource units should get a
    higher bonus than a figure with power=6 and no production.

    - With production: bonus = 6*0.4 + 3*1.5 = 2.4 + 4.5 = 6.9.
    - Without production: bonus = 6*0.4 + 0 = 2.4.
    """
    action = {
        'type': 'cast_spell',
        'description': 'Spell: Explosion',
        'params': {'spell_family_name': 'Explosion', 'target_figure_id': 30},
    }

    producer = [{'id': 30, 'field': 'building', 'cards': [{'value': 6}],
                 'produces': {'villager_red': 2, 'food_red': 1}, 'requires': {}}]
    no_prod = [{'id': 30, 'field': 'military', 'cards': [{'value': 6}],
                'produces': {}, 'requires': {}}]

    bonus_prod = _modifier_bonus(action, [], opp_figures=producer)
    bonus_noprod = _modifier_bonus(action, [], opp_figures=no_prod)
    assert bonus_prod > bonus_noprod, (
        f'Producer bonus {bonus_prod} should exceed non-producer {bonus_noprod}'
    )


def test_modifier_bonus_blitzkrieg_unchanged():
    """Tactical spells should keep a fixed rule-derived bonus.

    Blitzkrieg's value is structural (attacker picks the defender's
    battle figure), not dependent on any specific target's power.
    The bonus is +2.5 — softened from the historical +3.5 so that
    context-rich spells (greed, enchantments, All-Seeing-Eye combo)
    can compete when they're the right call.
    """
    action = {
        'type': 'cast_spell',
        'description': 'Cast Blitzkrieg',
        'params': {'spell_name': 'Blitzkrieg'},
    }
    bonus = _modifier_bonus(action, [])
    assert bonus == 2.5


# ── Maharaja advance penalty ──────────────────────────────────────────

def test_maharaja_advance_penalty():
    """Advancing a checkmate figure (Maharaja) should receive a -8.0 penalty.

    Setup: Two advance_figure actions for figures of equal power — one
    with checkmate=True and one without.

    Reasoning: Losing a checkmate figure means instant game loss.  The
    scorer should strongly discourage advancing it unless no alternative exists.

    Regression: Ensures the Maharaja penalty remains active.
    """
    own_figures = [
        {'id': 1, 'field': 'military', 'cards': [{'value': 10}], 'checkmate': True},
        {'id': 2, 'field': 'military', 'cards': [{'value': 10}], 'checkmate': False},
    ]
    action_maharaja = {
        'type': 'advance_figure',
        'params': {'figure_id': 1},
    }
    action_normal = {
        'type': 'advance_figure',
        'params': {'figure_id': 2},
    }
    bonus_m = _modifier_bonus(action_maharaja, [], own_figures=own_figures)
    bonus_n = _modifier_bonus(action_normal, [], own_figures=own_figures)
    assert bonus_m == -8.0, f'Maharaja penalty should be -8.0, got {bonus_m}'
    assert bonus_n == 0.0, f'Normal figure bonus should be 0.0, got {bonus_n}'


def test_maharaja_advance_with_blitzkrieg():
    """Blitzkrieg combo still adds +1.5 but Maharaja penalty still applies.

    With Blitzkrieg active, advancing any figure gets +1.5, but a
    checkmate figure gets -8.0 + 1.5 = -6.5 net.
    """
    own = [{'id': 1, 'field': 'military', 'cards': [{'value': 8}], 'checkmate': True}]
    action = {'type': 'advance_figure', 'params': {'figure_id': 1}}
    bonus = _modifier_bonus(action, ['Blitzkrieg'], own_figures=own)
    assert bonus == -6.5, f'Expected -6.5, got {bonus}'


# ── Same-suit build promotion ────────────────────────────────────────

def test_same_suit_build_bonus():
    """Build bonus mirrors support-bonus estimate from current board state.

    Setup: AI has one Hearts castle (King, +4 support source).
    Building a Hearts military figure should add +4 support bonus on top
    of the flat +2 build-now structural preference.
    Building a Diamonds military figure should add 0 support — only the
    flat +2 structural bonus applies.

    Reasoning: planner combines a flat ``+2.0`` build-now structural bias
    (to outrank optimistic change_cards plans) with the dynamic support
    bonus derived from ``compute_support_bonus``.
    """
    own_figures = [
        {
            'id': 1,
            'field': 'castle',
            'name': 'Himalaya King',
            'suit': 'Hearts',
            'cards_to_figure': [{'value': 4, 'role': 'key'}],
            'produces': {},
            'requires': {},
        },
    ]
    action_hearts = {
        'type': 'build_figure',
        'params': {'suit': 'Hearts', 'field': 'military', 'name': 'Test Military'},
    }
    action_spades_new = {
        'type': 'build_figure',
        'params': {'suit': 'Diamonds', 'field': 'military', 'name': 'Test Military'},
    }
    bonus_h = _modifier_bonus(action_hearts, [], own_figures=own_figures)
    bonus_d = _modifier_bonus(action_spades_new, [], own_figures=own_figures)
    assert bonus_h == 6.0, f'Expected 6.0 (+2 build bias + 4 support), got {bonus_h}'
    assert bonus_d == 2.0, f'Expected 2.0 (build bias only, no support), got {bonus_d}'


# ── Invader Swap with strong defense ─────────────────────────────────

def test_invader_swap_with_strong_defense():
    """Invader Swap gets a high bonus when AI is invader and has defensive figs.

    Setup: AI is invader.  AI has a fortress (cannot_attack=True, power 15).
    The bonus should include the defensive power component (15 * 0.3 = 4.5,
    capped at 4.0).

    Reasoning: Swapping to defender forces the opponent to attack into
    our prepared defenses (fortress, walls).
    """
    own_figures = [
        {'id': 1, 'field': 'castle', 'cards': [{'value': 15}],
         'cannot_attack': True, 'must_be_attacked': True},
    ]
    game_dict = {'invader_player_id': 42}
    action = {
        'type': 'cast_spell',
        'description': 'Spell: Invader Swap',
        'params': {'spell_family_name': 'Invader Swap'},
    }
    bonus = _modifier_bonus(
        action, [], own_figures=own_figures,
        game_dict=game_dict, ai_player_id=42,
    )
    # 15 * 0.3 = 4.5 → capped at 4.0
    assert bonus == 4.0, f'Expected 4.0, got {bonus}'


def test_invader_swap_without_defense():
    """Invader Swap as invader without defensive figures yields a small bonus.

    The AI is invader but has no fortress/wall.  Swapping away the
    initiative without defenses to exploit is risky, so bonus is only 0.5.
    """
    own_figures = [
        {'id': 1, 'field': 'military', 'cards': [{'value': 10}]},
    ]
    game_dict = {'invader_player_id': 42}
    action = {
        'type': 'cast_spell',
        'description': 'Spell: Invader Swap',
        'params': {'spell_family_name': 'Invader Swap'},
    }
    bonus = _modifier_bonus(
        action, [], own_figures=own_figures,
        game_dict=game_dict, ai_player_id=42,
    )
    assert bonus == 0.5, f'Expected 0.5, got {bonus}'


def test_invader_swap_as_defender():
    """Invader Swap as defender gives a flat 1.0 baseline.

    When the AI is already the defender, swapping to become the invader
    is sometimes useful but isn't the defensive-play logic this rule targets.
    """
    game_dict = {'invader_player_id': 99}
    action = {
        'type': 'cast_spell',
        'description': 'Spell: Invader Swap',
        'params': {'spell_family_name': 'Invader Swap'},
    }
    bonus = _modifier_bonus(
        action, [], game_dict=game_dict, ai_player_id=42,
    )
    assert bonus == 1.0, f'Expected 1.0, got {bonus}'


# ── War spells when outgunned ────────────────────────────────────────

def test_peasant_war_bonus_when_outgunned():
    """Peasant War bonus increases when opponent's military is stronger.

    Setup: Opponent has military power 20, AI has military power 5.
    Difference = 15, exceeds the threshold of 5.
    Extra bonus = min(3.0, 15 * 0.3) = min(3.0, 4.5) = 3.0.
    Total = 2.5 (base) + 3.0 (outgunned) = 5.5.

    Reasoning: War spells force village-only battles, bypassing the
    opponent's military superiority.
    """
    own_figures = [
        {'id': 1, 'field': 'military', 'cards': [{'value': 5}]},
    ]
    opp_figures = [
        {'id': 10, 'field': 'military', 'cards': [{'value': 10}]},
        {'id': 11, 'field': 'military', 'cards': [{'value': 10}]},
    ]
    action = {
        'type': 'cast_spell',
        'description': 'Spell: Peasant War',
        'params': {'spell_family_name': 'Peasant War'},
    }
    bonus = _modifier_bonus(
        action, [], opp_figures=opp_figures, own_figures=own_figures,
    )
    assert bonus == 5.5, f'Expected 5.5, got {bonus}'


def test_peasant_war_no_extra_when_equal():
    """Peasant War gets only the base 2.5 when military power is roughly equal.

    Difference = 10 - 9 = 1, below the threshold of 5.
    """
    own = [{'id': 1, 'field': 'military', 'cards': [{'value': 9}]}]
    opp = [{'id': 10, 'field': 'military', 'cards': [{'value': 10}]}]
    action = {
        'type': 'cast_spell',
        'description': 'Spell: Peasant War',
        'params': {'spell_family_name': 'Peasant War'},
    }
    bonus = _modifier_bonus(action, [], opp_figures=opp, own_figures=own)
    assert bonus == 2.5, f'Expected 2.5, got {bonus}'


# ── Civil War with / without same-color village pair ─────────────────

def test_civil_war_with_same_color_village_pair():
    """Civil War gets an extra +1.0 when AI has 2+ same-color village figures.

    Setup: AI has 2 red village figures.  Opponent's military is stronger.
    Base (2.5) + outgunned (min(3.0, 15*0.3)=3.0) + pair bonus (1.0) = 6.5.

    Reasoning: Civil War requires 2 village figures of the same color.
    When the AI has them, the spell is effective and worth promoting.
    """
    own_figures = [
        {'id': 1, 'field': 'village', 'color': 'red', 'cards': [{'value': 6}]},
        {'id': 2, 'field': 'village', 'color': 'red', 'cards': [{'value': 7}]},
        {'id': 3, 'field': 'military', 'cards': [{'value': 5}]},
    ]
    opp_figures = [
        {'id': 10, 'field': 'military', 'cards': [{'value': 10}]},
        {'id': 11, 'field': 'military', 'cards': [{'value': 10}]},
    ]
    action = {
        'type': 'cast_spell',
        'description': 'Spell: Civil War',
        'params': {'spell_family_name': 'Civil War'},
    }
    bonus = _modifier_bonus(
        action, [], opp_figures=opp_figures, own_figures=own_figures,
    )
    assert bonus == 6.5, f'Expected 6.5, got {bonus}'


def test_civil_war_without_village_pair_penalised():
    """Civil War is heavily penalised when AI lacks 2 same-color village figs.

    Setup: AI has only 1 village figure.  The spell can't be used
    effectively, so the penalty (-4.0) should outweigh the base bonus (+2.5).
    Net = 2.5 - 4.0 = -1.5 (possibly plus outgunned if applicable).

    Reasoning: Without a valid village pair, the AI wastes resources.
    """
    own_figures = [
        {'id': 1, 'field': 'village', 'color': 'red', 'cards': [{'value': 6}]},
        {'id': 2, 'field': 'military', 'cards': [{'value': 5}]},
    ]
    opp_figures = [
        {'id': 10, 'field': 'military', 'cards': [{'value': 10}]},
    ]
    action = {
        'type': 'cast_spell',
        'description': 'Spell: Civil War',
        'params': {'spell_family_name': 'Civil War'},
    }
    bonus = _modifier_bonus(
        action, [], opp_figures=opp_figures, own_figures=own_figures,
    )
    # Base 2.5, opp_mil=10, own_mil=5 → diff=5, NOT > 5 threshold → no extra
    # No pair → -4.0  →  total = 2.5 - 4.0 = -1.5
    assert bonus == -1.5, f'Expected -1.5, got {bonus}'


# ======================================================================
#  Integration regression tests for the 5 strategic improvements.
#  These call generate_strategy_plans with full game dicts and verify
#  that the new scoring logic affects actual plan ranking.
# ======================================================================

# ── Integration 1: Maharaja advance penalty lowers its rank ──────────

def test_maharaja_advance_ranks_below_normal_advance(monkeypatch):
    """Advancing a normal figure should rank above advancing the Maharaja
    when both have equal power.

    Setup:
    - AI has two military figures of equal power (10): one with
      checkmate=True (Maharaja), one without.
    - One generic opponent figure (power=8, to produce a positive diff).
    - Two advance_figure actions offered: one for each figure.

    Why normal should rank higher:
    - Both get the same feasibility (1.0) and the same power_diff (+2).
    - But the Maharaja action receives -3.0 from the checkmate penalty,
      pulling its total score substantially lower.

    Regression purpose: ensures the Maharaja penalty propagates through
    generate_strategy_plans and actually affects plan ranking.
    """
    target = {
        'family_name': 'T', 'name': 'T', 'field': 'military', 'suit': 'Hearts',
        'card_state': 'ok', 'completion_probability': 0.5, 'resource_blocked': False,
        'power_estimate': 10,
    }
    opp = [{'name': 'Opp', 'power_estimate': 8, 'probability': 0.5}]
    _stub_planner(monkeypatch, [target], opp)

    ai_figs = [
        {'id': 101, 'name': 'Maharaja', 'field': 'military', 'suit': 'Hearts',
         'cards': [{'value': 10}], 'checkmate': True, 'produces': {}, 'requires': {}},
        {'id': 102, 'name': 'Normal Fig', 'field': 'military', 'suit': 'Clubs',
         'cards': [{'value': 10}], 'checkmate': False, 'produces': {}, 'requires': {}},
    ]
    opp_figs = [
        {'id': 201, 'name': 'Opp Fig', 'field': 'military', 'suit': 'Diamonds',
         'cards': [{'value': 8}], 'produces': {}, 'requires': {}},
    ]
    game = _game_with_figures(ai_figs, opp_figs)

    actions = [
        {'id': 1, 'type': 'advance_figure', 'description': 'advance Maharaja',
         'params': {'figure_id': 101}},
        {'id': 2, 'type': 'advance_figure', 'description': 'advance Normal Fig',
         'params': {'figure_id': 102}},
    ]

    plans = generate_strategy_plans(game, 1, 'normal_turn', actions, max_plans=2)
    assert plans[0]['seed_action_id'] == 2, (
        'Normal figure should outrank Maharaja (checkmate penalty)'
    )


# ── Integration 2: Same-suit build beats off-suit build ──────────────

def test_same_suit_build_ranks_higher(monkeypatch):
    """Building a figure whose suit matches two existing figures should
    rank above building an off-suit figure of identical power/probability.

    Setup:
    - AI has two Hearts figures already on the field.
    - Two buildable targets: Hearts (same suit → +1.6) and Diamonds
      (no match → +0.0), equal power and probability.

    Why Hearts build should win:
    - Both get identical feasibility, power_diff, and battle_move_power.
    - The Hearts build gets +1.6 modifier bonus from matching 2 existing
      Hearts figures, tipping the score.

    Regression purpose: ensures same-suit promotion affects plan ranking.
    """
    targets = [
        {'family_name': 'Hearts Fig', 'name': 'Hearts Fig', 'field': 'military',
         'suit': 'Hearts', 'card_state': 'build_possible_with_probability',
         'completion_probability': 0.7, 'resource_blocked': False, 'power_estimate': 10},
        {'family_name': 'Diamonds Fig', 'name': 'Diamonds Fig', 'field': 'military',
         'suit': 'Diamonds', 'card_state': 'build_possible_with_probability',
         'completion_probability': 0.7, 'resource_blocked': False, 'power_estimate': 10},
    ]
    _stub_planner(monkeypatch, targets)

    ai_figs = [
        {'id': 101, 'name': 'Existing Hearts A', 'field': 'military', 'suit': 'Hearts',
         'cards': [{'value': 8}], 'produces': {}, 'requires': {}},
        {'id': 102, 'name': 'Existing Hearts B', 'field': 'village', 'suit': 'Hearts',
         'cards': [{'value': 5}], 'produces': {}, 'requires': {}},
    ]
    game = _game_with_figures(ai_figs, [])

    actions = [
        {'id': 1, 'type': 'build_figure', 'description': 'build Hearts Fig power=10',
         'params': {'family_name': 'Hearts Fig', 'suit': 'Hearts'}},
        {'id': 2, 'type': 'build_figure', 'description': 'build Diamonds Fig power=10',
         'params': {'family_name': 'Diamonds Fig', 'suit': 'Diamonds'}},
    ]

    plans = generate_strategy_plans(game, 1, 'normal_turn', actions, max_plans=2)
    assert plans[0]['seed_action_id'] == 1, (
        'Same-suit build should outrank off-suit build when existing figures match'
    )


# ── Integration 3: Invader Swap ranks high with strong defense ───────

def test_invader_swap_ranks_high_with_fortress(monkeypatch):
    """When the AI is invader and has a fortress, Invader Swap should
    rank above a generic equally-powered spell.

    Setup:
    - AI is invader (invader_player_id=1).
    - AI has a fortress figure (cannot_attack=True, power=15).
    - Two actions: Invader Swap vs a generic Infinite Hammer.

    Why Invader Swap should win:
    - Invader Swap bonus = min(4.0, 15*0.3) = 4.0 (defensive power).
    - Infinite Hammer bonus = 2.0 (fixed).
    - Both have feasibility=0.85 (spells), so the higher modifier wins.

    Regression purpose: ensures defensive-play Invader Swap logic
    propagates through the full planner scoring pipeline.
    """
    target = {
        'family_name': 'T', 'name': 'T', 'field': 'military', 'suit': 'Hearts',
        'card_state': 'ok', 'completion_probability': 0.5, 'resource_blocked': False,
        'power_estimate': 10,
    }
    _stub_planner(monkeypatch, [target])

    ai_figs = [
        {'id': 101, 'name': 'Fortress', 'field': 'castle', 'suit': 'Hearts',
         'cards': [{'value': 15}], 'cannot_attack': True, 'must_be_attacked': True,
         'produces': {}, 'requires': {}},
    ]
    game = _game_with_figures(ai_figs, [], invader_player_id=1)

    actions = [
        {'id': 1, 'type': 'cast_spell', 'description': 'Spell: Invader Swap',
         'params': {'spell_family_name': 'Invader Swap'}},
        {'id': 2, 'type': 'cast_spell', 'description': 'Spell: Infinite Hammer',
         'params': {'spell_family_name': 'Infinite Hammer'}},
    ]

    plans = generate_strategy_plans(game, 1, 'normal_turn', actions, max_plans=2)
    assert plans[0]['seed_action_id'] == 1, (
        'Invader Swap should outrank Infinite Hammer when AI is invader with fortress'
    )


# ── Integration 4: Peasant War ranks high when outgunned ─────────────

def test_peasant_war_ranks_high_when_opponent_military_stronger(monkeypatch):
    """When the opponent's military is much stronger, Peasant War should
    rank above a generic spell because it forces village-only battles.

    Setup:
    - Opponent has two military figures totalling power=24.
    - AI has one military figure with power=5.
    - Two actions: Peasant War vs Infinite Hammer.

    Why Peasant War should win:
    - Peasant War bonus = 2.5 + min(3.0, (24-5)*0.3) = 2.5 + 3.0 = 5.5.
    - Infinite Hammer bonus = 2.0.
    - The outgunned bonus makes Peasant War clearly superior.

    Regression purpose: ensures the military-power comparison logic
    correctly boosts war spells in the full pipeline.
    """
    target = {
        'family_name': 'T', 'name': 'T', 'field': 'military', 'suit': 'Hearts',
        'card_state': 'ok', 'completion_probability': 0.5, 'resource_blocked': False,
        'power_estimate': 10,
    }
    _stub_planner(monkeypatch, [target])

    ai_figs = [
        {'id': 101, 'name': 'Weak Military', 'field': 'military', 'suit': 'Hearts',
         'cards': [{'value': 5}], 'produces': {}, 'requires': {}},
    ]
    opp_figs = [
        {'id': 201, 'name': 'Strong A', 'field': 'military', 'suit': 'Clubs',
         'cards': [{'value': 12}], 'produces': {}, 'requires': {}},
        {'id': 202, 'name': 'Strong B', 'field': 'military', 'suit': 'Diamonds',
         'cards': [{'value': 12}], 'produces': {}, 'requires': {}},
    ]
    game = _game_with_figures(ai_figs, opp_figs)

    actions = [
        {'id': 1, 'type': 'cast_spell', 'description': 'Spell: Peasant War',
         'params': {'spell_family_name': 'Peasant War'}},
        {'id': 2, 'type': 'cast_spell', 'description': 'Spell: Infinite Hammer',
         'params': {'spell_family_name': 'Infinite Hammer'}},
    ]

    plans = generate_strategy_plans(game, 1, 'normal_turn', actions, max_plans=2)
    assert plans[0]['seed_action_id'] == 1, (
        'Peasant War should outrank Infinite Hammer when opponent military is stronger'
    )


# ── Integration 5: Civil War penalised without village pair ──────────

def test_civil_war_ranks_below_peasant_war_without_village_pair(monkeypatch):
    """Civil War should rank below Peasant War when the AI doesn't have
    two same-color village figures.

    Setup:
    - AI has only 1 village figure (red) and 1 military figure.
    - Opponent has stronger military (power=20 vs own=5).
    - Two actions: Civil War vs Peasant War.

    Why Peasant War should win:
    - Peasant War bonus = 2.5 + min(3.0, (20-5)*0.3) = 2.5 + 3.0 = 5.5.
    - Civil War bonus = 2.5 + 3.0 (outgunned) - 4.0 (no pair) = 1.5.
    - The village-pair penalty makes Civil War clearly worse.

    Regression purpose: ensures the AI doesn't cast Civil War when it
    can't actually field two village figures of the same color.
    """
    target = {
        'family_name': 'T', 'name': 'T', 'field': 'military', 'suit': 'Hearts',
        'card_state': 'ok', 'completion_probability': 0.5, 'resource_blocked': False,
        'power_estimate': 10,
    }
    _stub_planner(monkeypatch, [target])

    ai_figs = [
        {'id': 101, 'name': 'Village Fig', 'field': 'village', 'suit': 'Hearts',
         'color': 'red', 'cards': [{'value': 6}], 'produces': {}, 'requires': {}},
        {'id': 102, 'name': 'Military Fig', 'field': 'military', 'suit': 'Spades',
         'cards': [{'value': 5}], 'produces': {}, 'requires': {}},
    ]
    opp_figs = [
        {'id': 201, 'name': 'Strong', 'field': 'military', 'suit': 'Clubs',
         'cards': [{'value': 20}], 'produces': {}, 'requires': {}},
    ]
    game = _game_with_figures(ai_figs, opp_figs)

    actions = [
        {'id': 1, 'type': 'cast_spell', 'description': 'Spell: Civil War',
         'params': {'spell_family_name': 'Civil War'}},
        {'id': 2, 'type': 'cast_spell', 'description': 'Spell: Peasant War',
         'params': {'spell_family_name': 'Peasant War'}},
    ]

    plans = generate_strategy_plans(game, 1, 'normal_turn', actions, max_plans=2)
    assert plans[0]['seed_action_id'] == 2, (
        'Peasant War should outrank Civil War when AI lacks a same-color village pair'
    )


# ── Build-figure regression: not in top_targets, but legal ─────────────

def test_build_figure_not_in_top_targets_still_scores_well(monkeypatch):
    """A legal build_figure action whose recipe isn't in the cached
    top_targets list must still score competitively.

    Regression: previously, ``_estimate_target_figure_for_action`` would
    fall through to ``top_targets[0]`` (often an impossible/blocked
    target with completion_probability≈0), which made build_figure score
    ≈ -3 via the risk_penalty and lose to change_cards every time.

    With the synthetic-target fallback + build_now feasibility floor,
    the action should beat change_cards when the build is legal now.
    """
    # The single cached top target is a high-power but impossible build.
    impossible_target = {
        'family_name': 'Far Away Dream',
        'name': 'Far Away Dream',
        'field': 'castle',
        'suit': 'Hearts',
        'card_state': 'build_possible_with_probability',
        'completion_probability': 0.0,
        'resource_blocked': False,
        'power_estimate': 30,
    }
    _stub_planner(monkeypatch, [impossible_target])

    game = _game_with_figures([], [])

    actions = [
        # Legal build action whose family doesn't match the cached target.
        {'id': 1, 'type': 'build_figure',
         'description': 'Build Sherpa Guard [power=12]',
         'params': {'family_name': 'Sherpa Guard', 'suit': 'Spades',
                    'field': 'military', 'name': 'Sherpa Guard'}},
        {'id': 2, 'type': 'change_cards',
         'description': 'Change cards', 'params': {}},
    ]

    plans = generate_strategy_plans(game, 1, 'normal_turn', actions, max_plans=2)
    assert plans[0]['seed_action_id'] == 1, (
        'build_figure should outrank change_cards when the build is legal '
        'right now, even if the recipe is not in top_targets'
    )
    # And the build's feasibility floor should be the synthetic 1.0.
    build_plan = next(p for p in plans if p['seed_action_id'] == 1)
    assert build_plan['feasibility_probability'] == 1.0


# ── Defender advance penalty ───────────────────────────────────────────

def test_defender_advance_gets_penalty():
    """Advancing during one's own turn while the opponent is the invader
    is poor strategy — the invader is forced to advance themselves.

    The penalty is soft (~-3) and scales by +1.5 when opponent still
    holds ≥2 turns. Capped at -5 so an overwhelming advantage can
    still pursue an offensive line in the planner.
    """
    own_fig = {'id': 1, 'field': 'military', 'cards': [{'value': 10}]}
    action = {'type': 'advance_figure', 'params': {'figure_id': 1}}

    # AI is defender (invader is player 2); opponent has 3 turns left.
    game = {
        'invader_player_id': 2,
        'players': [
            {'id': 1, 'turns_left': 3, 'figures': [own_fig]},
            {'id': 2, 'turns_left': 3, 'figures': []},
        ],
    }
    bonus = _modifier_bonus(action, [], own_figures=[own_fig],
                            game_dict=game, ai_player_id=1)
    # -3 base + -1.5 (opponent turns_left >= 2) = -4.5, capped at -5.
    assert -5.0 <= bonus <= -3.0, f'Expected defender penalty in [-5, -3], got {bonus}'

    # As invader, no defender penalty applies.
    game_invader = {
        'invader_player_id': 1,
        'players': [
            {'id': 1, 'turns_left': 3, 'figures': [own_fig]},
            {'id': 2, 'turns_left': 3, 'figures': []},
        ],
    }
    bonus_inv = _modifier_bonus(action, [], own_figures=[own_fig],
                                game_dict=game_invader, ai_player_id=1)
    assert bonus_inv == 0.0, f'Invader advance should be unpenalized, got {bonus_inv}'


def test_defender_advance_lighter_penalty_when_opp_low_turns():
    """When the opponent has only 1 turn left, the bonus +1.5 doesn't
    apply — the defender penalty stays at -3."""
    own_fig = {'id': 1, 'field': 'military', 'cards': [{'value': 10}]}
    action = {'type': 'advance_figure', 'params': {'figure_id': 1}}
    game = {
        'invader_player_id': 2,
        'players': [
            {'id': 1, 'turns_left': 2, 'figures': [own_fig]},
            {'id': 2, 'turns_left': 1, 'figures': []},
        ],
    }
    bonus = _modifier_bonus(action, [], own_figures=[own_fig],
                            game_dict=game, ai_player_id=1)
    assert bonus == -3.0, f'Expected -3.0 when opp turns_left=1, got {bonus}'


# ── New spell bonus regressions ────────────────────────────────────────

def _game_with_hands(main_hand, side_hand=None):
    """Game dict with a configurable AI hand for spell-bonus tests."""
    return {
        'invader_player_id': 2,
        'players': [
            {'id': 1, 'turns_left': 3, 'figures': [],
             'main_hand': main_hand,
             'side_hand': side_hand or []},
            {'id': 2, 'turns_left': 3, 'figures': [],
             'main_hand': [], 'side_hand': []},
        ],
    }


def test_fill_up_to_10_prefers_low_hand():
    """Fill up to 10 should score higher when the AI has few free
    main cards."""
    action = {
        'type': 'cast_spell',
        'description': 'Spell: Fill up to 10',
        'params': {'spell_name': 'Fill up to 10'},
    }

    low_hand = _game_with_hands(
        [{'id': i, 'rank': '10', 'suit': 'Hearts',
          'part_of_figure': False, 'part_of_battle_move': False}
         for i in range(3)]  # 3 free main cards
    )
    full_hand = _game_with_hands(
        [{'id': i, 'rank': '10', 'suit': 'Hearts',
          'part_of_figure': False, 'part_of_battle_move': False}
         for i in range(10)]  # already at 10
    )

    bonus_low = _modifier_bonus(action, [], game_dict=low_hand, ai_player_id=1)
    bonus_full = _modifier_bonus(action, [], game_dict=full_hand, ai_player_id=1)
    assert bonus_low > bonus_full, (
        f'Fill up to 10 should score higher with a low hand: '
        f'low={bonus_low} vs full={bonus_full}'
    )


def test_all_seeing_eye_high_when_blitzkrieg_cavalry_combo_available():
    """All Seeing Eye + Blitzkrieg + Cavalry is the premium combo: scout
    the opponent's hand, become invader unblockably, charge with a
    Cavalry that can't be blocked. The scorer should reflect that."""
    action = {
        'type': 'cast_spell',
        'description': 'Spell: All Seeing Eye',
        'params': {'spell_name': 'All Seeing Eye'},
    }

    cavalry = {'id': 1, 'family_name': 'Cavalry', 'field': 'military',
               'suit': 'Hearts', 'cards': [{'value': 8}]}
    game_combo = _game_with_hands(
        [{'id': 10, 'rank': 'Q', 'suit': 'Hearts',
          'part_of_figure': False, 'part_of_battle_move': False},
         {'id': 11, 'rank': 'Q', 'suit': 'Diamonds',
          'part_of_figure': False, 'part_of_battle_move': False}]
    )
    game_combo['players'][0]['figures'] = [cavalry]

    game_no_combo = _game_with_hands([])

    bonus_combo = _modifier_bonus(action, [], own_figures=[cavalry],
                                  game_dict=game_combo, ai_player_id=1)
    bonus_no = _modifier_bonus(action, [], own_figures=[],
                               game_dict=game_no_combo, ai_player_id=1)
    assert bonus_combo > bonus_no + 1.5, (
        f'Cavalry+Blitzkrieg combo should boost All Seeing Eye well above '
        f'baseline: combo={bonus_combo} vs baseline={bonus_no}'
    )


def test_all_seeing_eye_reduced_when_battle_imminent():
    """Once advancing_figure_id is set, the matchup is locked. All
    Seeing Eye becomes wasted information — its bonus should drop
    well below the combo case."""
    action = {
        'type': 'cast_spell',
        'description': 'Spell: All Seeing Eye',
        'params': {'spell_name': 'All Seeing Eye'},
    }

    game = _game_with_hands([])
    game['advancing_figure_id'] = 99  # battle is being set up

    bonus_imminent = _modifier_bonus(action, [], game_dict=game, ai_player_id=1)

    game_clear = _game_with_hands([])
    bonus_clear = _modifier_bonus(action, [], game_dict=game_clear, ai_player_id=1)

    assert bonus_imminent < bonus_clear, (
        f'All Seeing Eye should score lower when battle is imminent: '
        f'imminent={bonus_imminent} vs clear={bonus_clear}'
    )


def test_blitzkrieg_softened_to_2_5():
    """Blitzkrieg's base bonus is +2.5 (down from a previous +3.5),
    leaving room for contextual spells to compete."""
    action = {
        'type': 'cast_spell',
        'description': 'Cast Blitzkrieg',
        'params': {'spell_name': 'Blitzkrieg'},
    }
    assert _modifier_bonus(action, []) == 2.5


def test_change_cards_power_is_expected_value(monkeypatch):
    """change_cards target power must be discounted by completion_probability.

    Regression: previously change_cards inherited the raw recipe rank-sum
    power of a half-built dream target (e.g. 30+) and used the full value
    in offensive_value. That dominated real builds. The planner should now
    convert it to expected value: recipe_power * completion_probability.
    """
    half_built_dream = {
        'family_name': 'Dream Knight',
        'name': 'Dream Knight',
        'field': 'military',
        'suit': 'Hearts',
        'card_state': 'build_possible_with_probability',
        'completion_probability': 0.4,
        'resource_blocked': False,
        # Two missing main cards K(13), A(14) — recipe power = 27.
        'missing_main': {'K_Hearts': 1, 'A_Hearts': 1},
        'missing_side': {},
        'number_value_assumed': 0,
    }
    _stub_planner(monkeypatch, [half_built_dream])

    game = _game_with_figures([], [])

    actions = [
        # An actually buildable Castle (power=13 from the description).
        {'id': 1, 'type': 'build_figure',
         'description': 'Build Himalaya King [power=13]',
         'params': {'family_name': 'Himalaya King', 'suit': 'Spades',
                    'field': 'castle', 'name': 'Himalaya King'}},
        # change_cards targeting the dream knight.
        {'id': 2, 'type': 'change_cards',
         'description': 'Change cards', 'params': {}},
    ]

    plans = generate_strategy_plans(game, 1, 'normal_turn', actions, max_plans=2)

    # Build must outrank change_cards: power 13 + 2 (build bias) beats
    # change_cards expected value 27 * 0.4 ≈ 10.8 (no build bias, lower feasibility).
    assert plans[0]['seed_action_id'] == 1, (
        f'build_figure should win over change_cards with discounted expected '
        f"power; plans={plans}"
    )
