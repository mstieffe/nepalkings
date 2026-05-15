# AI Strategy Upgrade Plan

## Objective
Upgrade the AI opponent from reactive action choice to probability-aware multi-turn planning that:
1. Computes card draw probabilities from remaining unknown cards.
2. Estimates probability of completing candidate figures within remaining turns.
3. Generates and scores multiple concrete turn-by-turn strategies.
4. Selects a strategy that maximizes expected battle advantage and win likelihood.

## Scope
In scope:
1. Deterministic probability and planning modules.
2. Integration into current AI decision flow.
3. Structured plan generation and selection in each AI turn.
4. Expanded tests at unit, integration, and end-to-end AI levels.

Out of scope for this phase:
1. UI changes for human-visible plan visualization.
2. Full game-tree solve across all hidden opponent hand states.
3. Heavy Monte Carlo simulations that would increase response latency significantly.

## Critical Design Constraints
1. Strategy generation must be bounded and anytime-safe to avoid combinatorial explosion.
2. Battle modifier spells are first-class tactical context, not optional side-effects.
3. Opponent belief modeling must use revealed cards, visible figures, and known card consumption.
4. Planner must prefer high expected value under uncertainty, not exhaustive search.

## Current Architecture Touchpoints
Primary integration points:
1. server/ai/ai_worker.py
2. server/ai/action_enum.py
3. server/ai/game_state.py
4. server/ai/figure_recipes.py
5. server/ai/prompts.py
6. server/server_settings.py

Current AI test surface to extend:
1. tests/server/test_ai_action_enum.py
2. tests/server/test_ai_worker.py
3. tests/server/test_ai_integration_scenarios.py
4. tests/server/test_ai_llm_client.py
5. tests/server/test_ai_route_hooks.py

## Phase Plan

### Phase 1: Probability Engine
Deliver a deterministic card probability module.

Deliverables:
1. New module server/ai/probability_engine.py.
2. Functions for hypergeometric probability and utility wrappers:
3. probability_at_least
4. probability_exact
5. probability_requirements_from_draws
6. remaining_unknown_card_pool extraction from game state

Requirements:
1. Respect known cards in both players, figure attachments, battle moves, and discard/deck state.
2. Respect revealed opponent information from visible hand effects and board figures.
2. Return stable numeric outputs for same input state.

Tests:
1. New tests/server/test_ai_probability_engine.py with closed-form checks.
2. Edge cases: zero draws, impossible requirements, exhausted pool.

### Phase 2: Figure Completion Model
Estimate whether figures are buildable now, probabilistically buildable, or impossible in horizon.

Deliverables:
1. New module server/ai/figure_completion.py.
2. Function to classify each candidate figure:
3. build_now
4. build_possible_with_probability
5. build_impossible
6. Turn-budget-aware completion probability estimate.

Requirements:
1. Include recipe constraints from figure_recipes.
2. Include color constraints and duplicate-card constraints.
3. Include resource deficit prevention and repair requirements.

Tests:
1. New tests/server/test_ai_figure_completion.py.
2. Cases with reachable and unreachable recipe paths.

### Phase 2.5: Opponent Belief and Modifier Context
Add an explicit belief-state layer consumed by planning/scoring.

Deliverables:
1. New module server/ai/opponent_model.py.
2. Opponent belief snapshot with:
3. revealed_cards
4. visible_field_figures and their resource/value implications
5. unknown_hand_distribution
6. likely_build_targets and likely_battle_figures
7. New module server/ai/modifier_context.py for battle-modifier tactical effects.

Requirements:
1. Consume only legal/visible information (no hidden-state leakage).
2. Incorporate active and castable battle modifiers into plan feasibility/scoring.
3. Expose a compact context object reusable by planner and scoring layers.

Tests:
1. New tests/server/test_ai_opponent_model.py.
2. New tests/server/test_ai_modifier_context.py.
3. Scenarios with revealed cards changing opponent likelihood distributions.

### Phase 3: Multi-Turn Strategy Planner
Generate multiple explicit strategy paths over remaining turns.

Deliverables:
1. New module server/ai/turn_planner.py.
2. Two-stage planner:
3. Stage A coarse strategy templates (build-first, spell-first, pressure-now, stabilize-deficit).
4. Stage B beam-search refinement within top templates only.
3. Structured plan object per candidate with:
4. turn_actions list
5. target_battle_figure and whether already built
6. likely_opponent_target_figure distribution
7. planned_battle_moves
8. feasibility_probability
9. expected_power_diff
10. expected_battle_score

Requirements:
1. Enumerate each remaining turn with one planned action.
2. Generate multiple strategies and rank them.
3. Keep runtime bounded with beam width and depth limits.
4. Apply strict pruning:
5. progressive widening (limit children at each depth)
6. legality/feasibility gating before expansion
7. transposition table and state hashing for duplicate collapse
8. dominance pruning (drop plans dominated on score upper-bound and feasibility)
9. optimistic upper-bound cutoff for early branch termination
10. hard runtime budget with anytime best-plan return.

Tests:
1. New tests/server/test_ai_turn_planner.py.
2. Deterministic scenario tests with expected top strategy ordering.

### Phase 4: Battle Outcome Scoring
Score candidate plans by expected value, not only raw figure power.

Deliverables:
1. New module server/ai/plan_scoring.py.
2. Composite score function combining:
3. feasibility_probability
4. expected_power_diff
5. estimated battle move effectiveness
6. risk penalty for low-certainty paths
7. opponent likelihood weighting from belief model
8. battle-modifier tactical value contributions

Requirements:
1. Strategy ranking must be stable and explainable.
2. Provide score breakdown fields for diagnostics.
3. Score must include both mean-case and guarded worst-case opponent responses.

Tests:
1. New tests/server/test_ai_plan_scoring.py.
2. Regression tests for ranking consistency.

### Phase 5: AI Worker Integration
Use planner output in each AI turn and keep LLM as chooser or explainer.

Deliverables:
1. Integrate planner call path into ai_worker decision step.
2. Add optional LLM selection over top ranked plans.
3. Add deterministic fallback to highest score plan when LLM fails.
4. Add per-turn strategy memory entries that reference selected plan id and rationale.

Requirements:
1. Maintain existing safeguards for retries, fallback actions, and hooks.
2. Do not block thread longer than configured budget.
3. Preserve behavior when planner is disabled.

Tests:
1. Extend tests/server/test_ai_worker.py and tests/server/test_ai_integration_scenarios.py.
2. Add planner-failure fallback tests.

### Phase 6: Config, Telemetry, and Rollout
Add feature flags and observability for safe rollout.

Deliverables:
1. New settings flags in server/server_settings.py:
2. AI_PLANNER_ENABLED
3. AI_PLANNER_BEAM_WIDTH
4. AI_PLANNER_MAX_DEPTH
5. AI_PLANNER_MAX_RUNTIME_MS
6. AI_PLANNER_MAX_TEMPLATE_COUNT
7. AI_PLANNER_MAX_CHILDREN_PER_NODE
8. AI_PLANNER_OPPONENT_MODEL_ENABLED
9. AI_PLANNER_MODIFIER_MODEL_ENABLED
6. Structured logs for:
7. selected plan
8. plan score breakdown
9. fallback reasons
10. pruned_branch_counts and planner_runtime_ms

Requirements:
1. Shadow mode support: compute plans but keep old policy for comparison.
2. Safe rollback path via config only.

Tests:
1. Config flag behavior tests.
2. Runtime budget tests for planner cutoffs.

## Data Contracts
Plan object schema (logical contract):
1. plan_id
2. horizon_turns
3. turn_steps list with explicit action and target ids
4. target_figure_id and target_figure_state
5. predicted_opponent_figure_id_distribution
6. revealed_opponent_cards_used
7. active_battle_modifier_assumptions
6. planned_battle_move_sequence
7. feasibility_probability
8. expected_power_diff
9. expected_battle_win_probability
10. total_score
11. score_breakdown

## Acceptance Criteria
1. AI emits at least three candidate plans when branching allows.
2. Selected plan contains explicit per-turn actions for remaining turns.
3. Plan includes own target figure and likely opponent figure.
4. Planner marks impossible figure pathways correctly in deterministic tests.
5. AI behavior remains stable under missing or malformed LLM responses.
6. Full test suite remains green.
7. Planner remains under runtime budget while spells/modifiers are enabled.
8. Plan ranking changes appropriately when opponent revealed cards change.
9. Battle modifier spells are reflected in plan feasibility and score breakdown.

## Performance Constraints
1. Planner runtime target: under 120 ms median and under 300 ms p95 per decision call.
2. Memory overhead constrained by beam width and capped state copies.
3. Fallback policy: if budget exceeded, return best partial plan with explicit confidence penalty.

## Execution Order
Suggested implementation sequence:
1. Phase 1 probability engine.
2. Phase 2 figure completion model.
3. Phase 4 scoring function skeleton.
4. Phase 3 turn planner using phases 1, 2, and 4.
5. Phase 5 ai_worker integration.
6. Phase 6 rollout flags and telemetry.

## First Build Slice
First mergeable slice should include:
1. probability_engine module + tests.
2. figure_completion module + tests.
3. non-invasive worker logging hook that computes but does not enforce plan choice yet.
4. opponent_model scaffold that only uses currently revealed cards and visible figures.

This yields immediate value and low rollout risk before replacing decision policy.
