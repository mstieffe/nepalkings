# AI Opponent README

This document explains how the Nepal Kings AI opponent works end to end: startup, turn triggering, planning, LLM decision making, action execution, tactical explain chat controls, observability, configuration, and test coverage.

## Table of Contents

1. [Scope and Goals](#scope-and-goals)
2. [Architecture Overview](#architecture-overview)
3. [Core Files and Responsibilities](#core-files-and-responsibilities)
4. [AI Lifecycle and Trigger Flow](#ai-lifecycle-and-trigger-flow)
5. [Decision Pipeline](#decision-pipeline)
6. [Strategy Planner Internals](#strategy-planner-internals)
7. [Chat, Banter, and Explain Controls](#chat-banter-and-explain-controls)
8. [Observability and Debugging](#observability-and-debugging)
9. [Configuration Reference](#configuration-reference)
10. [Reliability and Safety Guardrails](#reliability-and-safety-guardrails)
11. [Testing Map](#testing-map)
12. [Troubleshooting Guide](#troubleshooting-guide)
13. [Extension Points](#extension-points)

## Scope and Goals

The AI system is designed to be:

- Event driven: no central polling loop for all games.
- Rules compliant: all moves go through the same HTTP routes as human moves.
- Bounded: planning and action loops are capped and failure-safe.
- Observable: planner decisions and strategy notes can be inspected at runtime.
- Configurable: behavior can be tuned via environment variables.

The AI is currently represented by the service user `[AI] Strategos`.

## Architecture Overview

High-level flow:

1. Server startup initializes AI users and service tokens.
2. Human challenges AI.
3. AI auto-accepts challenge after a short delay.
4. Game actions (POST routes) trigger `trigger_ai_if_needed(game_id)`.
5. Worker thread runs a bounded per-game loop.
6. Loop detects current phase, enumerates legal actions, asks planner + LLM, executes chosen action.
7. Worker may emit chat banter or tactical explain messages.
8. Planner telemetry and strategy notes are stored in memory for debug access.

ASCII sequence:

```text
Human POST -> Route after_request hook -> trigger_ai_if_needed
          -> (if AI must act) spawn ai-game-<game_id> thread
          -> detect_phase -> enumerate_actions -> planner -> LLM -> execute route POST
          -> optional AI chat/explain
          -> continue until no action needed or loop cap reached
```

## Core Files and Responsibilities

- `server/ai/__init__.py`
  - AI account bootstrap (`init_ai_users`).
  - In-memory AI service token store.
  - Helpers for AI auth headers and AI-player detection.

- `server/ai/ai_worker.py`
  - Trigger entrypoint, worker loop, retries, watchdog, chat, explain controls.
  - Planner telemetry and strategy memory buffers.
  - Action execution router to server endpoints.

- `server/ai/action_enum.py`
  - Phase detection (`detect_phase`).
  - Legal action enumeration by phase.
  - LLM-facing action formatting.

- `server/ai/game_state.py`
  - Builds the textual game summary used in LLM prompts.
  - Includes own hand detail, visible board state, and threat analysis.

- `server/ai/strategy_planner.py`
  - Bounded candidate plan generation and scoring.
  - Recommended action extraction and prompt formatting.

- `server/ai/figure_completion.py`
  - Figure completion probabilities using adaptive draw assumptions.
  - Build feasibility and resource-gap analysis.

- `server/ai/opponent_model.py`
  - Belief snapshot from revealed information only.
  - Likely opponent battle figure ranking.

- `server/ai/probability_engine.py`
  - Deterministic hypergeometric utilities.
  - Exact and requirement-based draw probabilities.

- `server/ai/llm_client.py`
  - Provider abstraction and OpenAI integration.
  - Retries, backoff, timeout, and response parsing helpers.

- `server/ai/prompts.py`
  - Global strategy system prompt.
  - Phase-specific decision prompts.

- `server/routes/games.py`
  - AI trigger hook on POST requests.
  - AI debug endpoint: `GET /games/get_ai_debug`.

- `server/routes/figures.py`
- `server/routes/spells.py`
- `server/routes/battle_shop.py`
  - Same AI trigger hook pattern on POST requests.

- `server/routes/msg.py`
  - Human-to-AI explain/help command interception and AI auto-replies.

- `poll_ai_debug.py`
  - CLI poller for AI debug telemetry and planner candidates.

## AI Lifecycle and Trigger Flow

### 1) Startup and AI identity

On server startup, if `AI_ENABLED` is true:

- `init_ai_users()` ensures each configured AI username exists and has `is_ai=True`.
- AI gets high initial gold (`AI_INITIAL_GOLD`).
- Service token is generated and cached in memory.

Important behavior:

- AI service tokens are regenerated on each server start (in-memory map).
- Human login as AI is blocked (`/auth/login` returns 403 for `is_ai=True`).

### 2) Challenge auto-accept

When a human creates a challenge against an AI user:

- `routes/challenges.py` schedules a short delayed auto-accept thread (~2s).
- The AI context creates the game via the regular route path.
- If AI is enabled, `trigger_ai_if_needed` is invoked for the new game.

### 3) Route hooks that wake AI

These blueprints trigger AI after POST requests:

- `/games/*`
- `/figures/*`
- `/spells/*`
- `/battle_shop/*`

All hooks skip internal AI self-calls if header is set:

- `X-NepalKings-AI-Internal: 1`

This recursion guard is critical because AI actions are executed through HTTP calls back into the same server.

### 4) `trigger_ai_if_needed(game_id)` gates

Trigger checks include:

- AI enabled.
- API key present (`OPENAI_API_KEY` via `AI_OPENAI_API_KEY`).
- Game exists and is not finished.
- Game has an AI player.
- AI currently has an actionable phase.

Concurrency controls:

- `_active_games` lock prevents duplicate worker threads per game.
- `_pending_retrigger` marks races where new state arrived while worker was running.

### 5) Worker loop behavior

`_ai_game_loop` is a bounded loop with safeguards:

- Initial think delay (`AI_THINK_DELAY`).
- Max iterations per run (20).
- Re-fetches DB state each iteration inside app context.
- Exits cleanly when no phase remains.

Special flow handling:

- Calls `/games/start_turn` once at beginning of AI normal turn.
- Handles `finish_battle` and `post_battle_pick` directly.
- Enumerates phase actions and executes chosen action.
- Attempts fallbacks on failed execution.
- Optionally emits chat (banter or tactical explain).

Cleanup behavior:

- Clears per-game memory for finished games.
- Processes pending retrigger after thread exit.
- Schedules watchdog retry if loop failed while AI still owns actionable turn.

## Decision Pipeline

For each actionable phase:

1. Detect phase (`detect_phase`).
2. Enumerate legal actions (`enumerate_actions`).
3. If one action, auto-pick without LLM.
4. Else ask planner + LLM to choose action.
5. Execute via corresponding HTTP route.
6. Save strategy note and planner telemetry.

### Phase detection

Current phases include:

- `normal_turn`
- `select_defender`
- `battle_decision`
- `battle_shop`
- `battle_round`
- `finish_battle`
- `counter_spell`
- `post_battle_pick` (handled in worker)

### Legal action enumeration

Actions are explicit dicts with:

- `id`
- `type`
- `description`
- `params`

Enumerator includes tactical constraints such as:

- Defender-side counter-advance policy.
- Resource-deficit restrictions.
- Battle-modifier restrictions (Peasant War, Civil War, Blitzkrieg).
- Infinite Hammer action restrictions.

### LLM prompt assembly

The worker builds a prompt from:

- Serialized game state (`serialize_game_for_llm`).
- Recent game log digest.
- Strategy notes from previous AI decisions.
- Optional strategy plan candidate section.
- Numbered legal actions.
- Phase-specific instruction text.

Prompt hardening:

- `chat_messages` are removed before prompt generation.
- AI chat generation also uses sanitized context to prevent chat injection.

### LLM response parsing and fallback

`parse_action_response` accepts:

- Pure JSON.
- JSON inside code fences.
- JSON object embedded in reasoning text.
- Number-only fallback patterns.

If selected action is invalid:

- Default fallback is first legal action.
- Optional planner recommendation fallback may override this when enabled and not in shadow mode.

### Action execution map

Worker executes through server endpoints, for example:

- `build_figure` -> `/figures/create_figure`
- `change_cards` -> `/games/change_cards`
- `advance_figure` -> `/games/advance_figure`
- `select_defender` -> `/games/select_defender`
- `battle_decision` -> `/games/battle_decision`
- `buy_battle_move` -> `/battle_shop/buy_battle_move`
- `confirm_battle_moves` -> `/battle_shop/confirm_battle_moves`
- `gamble_battle_move` -> `/battle_shop/gamble_battle_move`
- `combine_battle_moves` -> `/battle_shop/combine_battle_moves`
- `play_battle_move` -> `/games/play_battle_move`
- `skip_battle_turn` -> `/games/skip_battle_turn`
- `cast_spell` -> `/spells/cast_spell`
- `counter_spell` -> `/spells/counter_spell`
- `allow_spell` -> `/spells/allow_spell`
- `end_infinite_hammer` -> `/spells/end_infinite_hammer`

Execution fallback rules (selected examples):

- Try alternative actions of same type on failure.
- If `build_figure` fails, may fallback to `change_cards`.
- If `confirm_battle_moves` fails, may fallback to `buy_battle_move`.

## Strategy Planner Internals

Planner is bounded and action-seeded: each legal action is treated as a plan seed and scored.

### Inputs

- Current game dict.
- AI player id.
- Current phase.
- Current legal actions.
- Planner caps (`max_plans`, draw assumptions).

### Supporting models

- Figure completion estimator (`best_figure_targets`).
- Opponent belief snapshot (`build_opponent_belief_snapshot`).
- Planned battle move preview from current free main cards.

### Output plan shape

Each candidate includes:

- `plan_id`
- `seed_action_id`
- `strategy_name`
- `horizon_turns`
- `turn_steps`
- `planned_battle_figure`
- `likely_opponent_figure`
- `planned_battle_moves`
- `feasibility_probability`
- `expected_power_diff`
- `expected_battle_move_power`
- `total_score`
- `score_breakdown`
- `notes`

### Scoring model

Planner score uses a compact expected-value heuristic:

```text
offensive_value = expected_power_diff + 0.35 * expected_battle_move_power + modifier_bonus
risk_penalty   = (1 - feasibility_probability) * 4.0
total_score    = feasibility_probability * offensive_value + turns_pressure - risk_penalty
```

Where:

- `turns_pressure` increases when few turns remain.
- Modifier bonus rewards tactical spell/modifier synergy (see below).
- Lower feasibility is penalized.

### Modifier bonus breakdown

The `modifier_bonus` component of the scoring formula is computed by
`_modifier_bonus()` and adapts to the current board state.  It combines
several independent sub-bonuses:

#### Maharaja advance penalty (-3.0)

Advancing a figure with `checkmate=True` risks instant game loss if the
battle is lost.  The scorer applies a flat -3.0 penalty to discourage
reckless Maharaja advances.

#### Same-suit build promotion (+0.8 per match)

Building a figure whose suit matches existing friendly figures earns
+0.8 per matching figure already on the field.  This promotes suit
concentration and maximizes support-bonus synergy in battle.

#### Tactical spells (fixed bonuses)

| Spell | Bonus | Rationale |
|---|---|---|
| Blitzkrieg | +3.5 | Attacker picks the defender's battle figure |
| Infinite Hammer | +2.0 | Extra action economy |
| Blitzkrieg + advance combo | +1.5 | Advancing while Blitzkrieg is active |

#### War spells (state-dependent)

Peasant War and Civil War share a base bonus of +2.5.  When the
opponent's total military power exceeds our own by more than 5, an
additional bonus kicks in:

```text
extra = min(3.0, (opp_military_power - own_military_power) * 0.3)
```

This rewards war spells when the opponent has a clear military advantage,
because they force village-only battles that bypass hostile military
superiority.

**Civil War village-pair check:**  Civil War additionally checks whether
the AI has at least two village figures of the same color.  If yes, a
+1.0 bonus is added.  If no valid pair exists, a -4.0 penalty is applied
(net negative), heavily discouraging the AI from wasting the spell.

#### Invader Swap (role-dependent)

| Condition | Bonus | Rationale |
|---|---|---|
| AI is invader, has defensive figures | min(4.0, defensive_power × 0.3) | Forces opponent into our prepared defenses |
| AI is invader, no defensive figures | +0.5 | Swapping away initiative without defenses is risky |
| AI is defender | +1.0 | Flat baseline; not the defensive-play case |

Defensive power sums the power of figures with `cannot_attack=True` or
`must_be_attacked=True` (fortresses, walls).

#### Targeted enchantment spells (power-proportional)

| Spell | Formula | Target |
|---|---|---|
| Poison | min(6.0, target_power × 0.4) | Strongest opponent figure |
| Health Boost | min(6.0, target_power × 0.3 + 3.0) | Strongest own figure |
| Explosion | target_power × 0.4 + resource_value × 1.5 | Highest-impact opponent figure |

Poison scales linearly with the target's power (capped at the actual
6-point damage dealt).  Health Boost has a +3.0 floor to keep weak-figure
boosts viable.  Explosion combines raw combat removal with resource-chain
disruption — destroying a resource-producing figure is worth more than a
pure military target of equal power.

### Figure completion probabilities

`figure_completion.py` estimates build probability per recipe variant by combining:

- Missing key-card requirements.
- Deck counts from known cards still in deck.
- Adaptive draw-rate assumptions based on hand quality/relevance.
- Resource-gap simulation after hypothetical build.

Probability engine is deterministic and hypergeometric.

### Planner runtime telemetry

Worker records planner events such as:

- `planner_generated`
- `planner_choice`
- `planner_runtime_warning`
- `planner_failure`
- `invalid_action_fallback`
- `planner_shadow_comparison`

These events are exposed through the AI debug endpoint and poll script.

### Shadow mode

When `AI_STRATEGY_PLANNER_SHADOW_MODE=True`:

- Planner still runs and emits telemetry.
- Plan text is not injected into LLM prompt.
- Recommendation fallback is not used to override invalid LLM picks.

This enables safe rollout comparisons before hard enforcement.

## Chat, Banter, and Explain Controls

There are two chat systems:

1. Flavor banter (random, occasional).
2. Tactical explain responses (manual or cadence-driven).

### Flavor banter

Controlled by:

- `AI_CHAT_ENABLED`
- `AI_CHAT_CHANCE`
- `AI_CHAT_MIN_SECONDS_BETWEEN`
- `AI_CHAT_MAX_PER_GAME`

Rules:

- Sent only in selected phases.
- Cooldown and per-marker dedupe prevent spam.
- LLM-generated one-liners with template fallback.

### Explain control model

Per-game explain state:

- `mode`: `off`, `manual`, `turn`, `battle`
- `depth`: `brief`, `standard`, `detailed`, `extensive`
- `last_marker`: dedupe marker for auto explains

Human-to-AI chat messages can change explain state.

### Supported command patterns

The parser recognizes phrases containing `explain` or `analysis mode`, plus plain help requests.

Common examples:

- `explain yourself`
- `explain mode off`
- `explain mode manual`
- `explain mode turn`
- `explain mode battle`
- `explain depth brief`
- `explain depth standard`
- `explain depth detailed`
- `explain depth extensive`
- `help`
- `commands`
- `ai help`
- `?`
- `/help`

Behavior:

- Help requests return a short command manual in chat.
- Manual explain requests return tactical explanation immediately.
- Auto explain emits once per phase/turn marker depending on mode.

### Explain output depth

- `brief`: top line only.
- `standard`: summary plus key detail bits.
- `detailed`: includes alternates.
- `extensive`: multi-candidate sequence summaries.

## Observability and Debugging

### Debug endpoint

Route:

- `GET /games/get_ai_debug`

Auth and access:

- Requires bearer token.
- Caller must be a participant in the target game.

Query params:

- `game_id` (required)
- `max_notes` (optional, default 20, clamped)
- `max_events` (optional, default 40, clamped)

Response includes:

- `ai_player_id`
- `ai_username`
- `ai_debug.strategy_notes`
- `ai_debug.planner_events`

Notes:

- Data is ephemeral and in-memory.
- Cleared when game finishes or server restarts.

### Poll script (`poll_ai_debug.py`)

The script supports:

- Auto login to get token.
- Auto selecting latest AI game.
- Continuous polling with diff output.
- Candidate summary display (`--show-candidates`).
- Verbose candidate detail display (`--verbose`).

Quick examples:

```bash
python poll_ai_debug.py --username alice --password secret --once
python poll_ai_debug.py --username alice --password secret --show-candidates
python poll_ai_debug.py --username alice --password secret --show-candidates --verbose --interval 2
```

## Configuration Reference

AI settings live in `server/server_settings.py`.

### Identity and core runtime

| Variable | Default | Purpose |
|---|---|---|
| `AI_USERNAMES` | `['[AI] Strategos']` | AI service usernames created at startup |
| `AI_INITIAL_GOLD` | `999999` | AI economic bootstrap |
| `AI_ENABLED` | `True` | Master switch |
| `AI_THINK_DELAY` | `2` | Delay between AI actions |

### LLM provider and reliability

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` -> `AI_OPENAI_API_KEY` | empty | Required to activate LLM decisions |
| `AI_PROVIDER` | `openai` | LLM provider id |
| `AI_MODEL` | `gpt-4.1-mini` | Model name |
| `AI_LLM_TIMEOUT_SECONDS` | `12` | Per-call timeout |
| `AI_LLM_MAX_RETRIES` | `2` | Retry count after initial attempt |
| `AI_LLM_RETRY_BACKOFF_SECONDS` | `1.0` | Exponential backoff base |

### Planner controls

| Variable | Default | Purpose |
|---|---|---|
| `AI_STRATEGY_PLANNER_ENABLED` | `True` | Enable planner generation |
| `AI_STRATEGY_PLANNER_MAX_PLANS` | `5` | Candidate cap |
| `AI_STRATEGY_PLANNER_MAX_MAIN_DRAWS_PER_TURN` | `2` | Base main-card draw assumption |
| `AI_STRATEGY_PLANNER_MAX_SIDE_DRAWS_PER_TURN` | `1` | Base side-card draw assumption |
| `AI_STRATEGY_PLANNER_USE_RECOMMENDATION_FALLBACK` | `True` | Use planner suggestion on invalid LLM choice |
| `AI_STRATEGY_PLANNER_SHADOW_MODE` | `False` | Observe planner without enforcing it |
| `AI_STRATEGY_PLANNER_RUNTIME_WARNING_MS` | `120.0` | Slow-planner warning threshold |

### AI chat and explain chatter

| Variable | Default | Purpose |
|---|---|---|
| `AI_CHAT_ENABLED` | `True` | Enable AI chat lines |
| `AI_CHAT_CHANCE` | `0.22` | Random send probability |
| `AI_CHAT_MIN_SECONDS_BETWEEN` | `35` | Anti-spam cooldown |
| `AI_CHAT_MAX_PER_GAME` | `12` | Per-game cap |
| `AI_CHAT_LLM_TEMPERATURE` | `0.75` | Banter generation temperature |
| `AI_CHAT_LLM_MAX_TOKENS` | `90` | Banter generation token cap |

### Worker watchdog

| Variable | Default | Purpose |
|---|---|---|
| `AI_WATCHDOG_RETRY_DELAY` | `4.0` | Delay before retry thread |
| `AI_WATCHDOG_MAX_RETRIES` | `3` | Max retries for stuck actionable state |

## Reliability and Safety Guardrails

The current implementation includes multiple guardrails:

- Recursion guard header (`X-NepalKings-AI-Internal`) to avoid hook-trigger loops.
- Single active worker thread per game (`_active_games` lock).
- Pending retrigger queue for race-safe continuation.
- Worker loop iteration cap (`max_iterations = 20`).
- Watchdog retry budget for unsuccessful exits.
- Fallbacks for invalid LLM action ids.
- Alternate action retry on execution failure.
- Optional planner shadow mode for safe rollout.
- Sanitization: chat messages removed from LLM state prompt.
- AI users cannot be logged into via normal human login endpoint.

## Testing Map

Core AI test files:

- `tests/server/test_ai.py`
  - AI identity and auth basics.

- `tests/server/test_ai_llm_client.py`
  - Response parsing robustness and fallback behavior.

- `tests/server/test_ai_action_enum.py`
  - Phase detection and legal action generation.

- `tests/server/test_ai_probability_engine.py`
  - Deterministic hypergeometric utilities.

- `tests/server/test_ai_figure_completion.py`
  - Figure completion probability, impossible/build-now/resource-blocked states, adaptive draw assumptions.

- `tests/server/test_ai_opponent_model.py`
  - Modifier-aware opponent belief snapshot and revealed card accounting.

- `tests/server/test_ai_strategy_planner.py`
  - Bounded plan generation, ranking, prompt formatting, recommendation behavior.

- `tests/server/test_ai_worker.py`
  - Trigger/headers, planner integration (active + shadow), fallbacks, explain control behavior, auto explain cadence.

- `tests/server/test_ai_observability.py`
  - `get_ai_debug` auth and data semantics.

- `tests/server/test_ai_route_hooks.py`
  - Route hook trigger behavior and recursion-guard bypass header.

- `tests/server/test_msg.py`
  - Human-to-AI explain/help chat auto-replies.

- `tests/server/test_poll_ai_debug_smoke.py`
  - Poll helper selection and candidate formatting.

Suggested quick regression commands:

```bash
pytest -q tests/server/test_ai*.py
pytest -q tests/server/test_msg.py tests/server/test_poll_ai_debug_smoke.py
```

## Troubleshooting Guide

### AI does not move

Check in order:

1. `AI_ENABLED` is true.
2. `OPENAI_API_KEY` is set (worker skips if missing).
3. Game actually has an AI player (`is_ai=True` user in game).
4. `detect_phase` returns actionable phase for AI.

### AI appears stuck in actionable state

1. Query `GET /games/get_ai_debug` and inspect latest planner events.
2. Watch for repeated `invalid_action_fallback` or action failures.
3. Confirm watchdog settings allow retries (`AI_WATCHDOG_MAX_RETRIES > 0`).
4. Check server logs for route-level validation failures from self-calls.

### Planner too slow

1. Reduce `AI_STRATEGY_PLANNER_MAX_PLANS`.
2. Lower draw assumption caps if needed.
3. Use `AI_STRATEGY_PLANNER_SHADOW_MODE=True` during tuning.
4. Track runtime warnings (`planner_runtime_warning`) in debug events.

### Explain commands not responding

1. Ensure human is messaging an AI receiver (`/msg/add_chat_message`).
2. Verify message includes explain/help trigger phrase.
3. Confirm AI auto-messages are included in response payload.
4. Validate no downstream DB commit failure in `msg` route.

### Debug endpoint returns forbidden

- Caller token user must be one of the two game participants.

## Extension Points

### Add another LLM provider

1. Extend `LLMClient` in `server/ai/llm_client.py`.
2. Add provider branch in `choose_action` and `generate_text`.
3. Wire provider settings via `AI_PROVIDER` and provider-specific credentials.

### Add a new planner feature

1. Add data model fields to candidate dict in `strategy_planner.py`.
2. Include new signal in scoring breakdown.
3. Record field in planner telemetry events.
4. Cover with deterministic tests before enabling in production.

### Add new explain command alias

1. Extend mode/depth alias maps in `ai_worker.py`.
2. Add parser tests in `tests/server/test_ai_worker.py`.
3. Add route-level reply coverage in `tests/server/test_msg.py`.

### Build richer observability

1. Add event type in `_record_planner_event` call sites.
2. Include compact and verbose fields for both in-app endpoint and poll script.
3. Keep per-game buffers bounded to avoid memory growth.

---

For historical rollout context and implementation sequencing notes, see `AI_STRATEGY_IMPLEMENTATION_PLAN.md`.
