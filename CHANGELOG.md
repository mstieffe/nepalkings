# Changelog

All notable changes to this project are documented in this file.

## Unreleased — Land tiers 1–6, castle cap, loot rank buckets

### Added

- Land tiers expanded from 4 to **6**. New tier names: *Imperial Bulwark* (5)
  and *Eternal Citadel* (6). `KINGDOM_TIER_COUNT` and the
  `LAND_TIER_PROBABILITIES`, `LAND_NEUTRAL_TIER_PROBABILITIES`,
  `LAND_GOLD_RATE_RANGES`, `LAND_SUIT_BONUS_RANGES`, `KINGDOM_TIER_XP`,
  `HEX_TIER_FILL/BORDER` and `HEX_SUIT_TIER_FILL/BORDER` tables now cover
  tiers 5 and 6.
- **Castle figure cap per tier**: `CASTLE_FIGURE_LIMIT_BY_TIER = {1:1, …, 6:6}`.
  A land with tier *N* may host at most *N* castle figures (kings/maharajas)
  in either a conquer-attack or defence config. Enforced in
  `/kingdom/conquer/build_figure`, `/kingdom/defence/build_figure`, and the
  in-battle figure-creation path (`server/routes/figures.py`). Violations
  return `400 { error_code: 'castle_cap_reached' }`.
- AI defence generator now produces feasibility-checked templates for all
  six tiers, with rank-based optional rosters and tier-scaled
  `optional_count_range`. Extra castle slots are placed before optional
  draws so the resource graph stays solvable when castle cap > 1.
- Tests: `tests/server/test_castle_cap.py` (conquer + defence routes,
  tier 1/2/3 boundary cases); `test_hex_map_overlays` parameterised over
  tiers 1–6.

### Changed

- **Loot reward shape**: post-conquer loot cards are now classified by
  **rank** rather than by figure role:
  - `LOOT_KEY_RANKS = {'2','4','5','J','Q','K','A'}` → *key* bucket.
  - `LOOT_NUMBER_RANKS = {'3','6','7','8','9','10'}` → *number* bucket.
  The internal `support_quota` field was renamed `number_quota` (and
  `support_cards` → `number_cards`) in `_select_conquer_loot_cards`.
- AI defence: `AI_DEFENCE_GENERATOR_VERSION` bumped **5 → 6**, invalidating
  cached templates so existing AI-defended lands regenerate on next visit.
- `kingdom_service.py` fallback default tier raised 3 → 6 to match the new
  upper bound.

### Migration note

- `CASTLE_FIGURE_LIMIT_BY_TIER` is a runtime constant; no schema change is
  required for the cap itself. However, existing AI-defended templates and
  any persisted land tiers > 4 should be regenerated: **run
  `server/RESET_DATABASE.sh`** before redeploy so land tiers, AI templates,
  and loot history align with the new tier 1–6 schema.

## Unreleased — Conquer v2 spell-replay refactor

### Added

- ConquerTactic spell-timeline replay: `ConquerTactic.revealed_step_index` and
  `ConquerTactic.discarded_step_index` columns + `Game.conquer_resolution_step`
  monotonic counter. Server stamps these when spells add or purge tactics; the
  client filters tactics against `ConquerTimelinePanel.currently_resolved_step_index`
  so spell-driven changes appear in sync with the spell animation.
- Tests: `test_purge_soft_deletes_with_step_index`,
  `test_auto_convert_stamps_revealed_step`,
  `test_current_conquer_tactics_filters_by_displayed_step`,
  `test_timeline_panel_currently_resolved_step_index`.

### Changed

- `purge_conquer_tactics_referencing_card` no longer hard-deletes rows. They
  are flagged with `status='spell_purged'` and stamped with
  `discarded_step_index` so the pre-purge state can be reconstructed during
  replay. Test helpers (`_conquer_move_entries`) now exclude `spell_purged`
  from active counts.

### Migration note

- New columns on `conquer_tactic` and `game`. Repository uses `db.create_all()`
  with no Alembic; **production must reset the conquer-game tables** (or run
  manual `ALTER TABLE` against `conquer_tactic`/`game`) before deploy. See
  `server/RESET_DATABASE.sh`.

## 2026-04-16

### Added

- AI side card change capability: the AI can now swap side cards (ranks 2–6) using the same smart tactic-protection logic as main cards. Rank 2 side cards are always kept (key for Healers, Carpenter, Stone Mason). Side cards needed for figure recipes or side-type number cards are protected from swapping.
- `compute_support_bonus()` in `game_state.py` for dict-based support bonus calculation.
- Support bonus integrated into all AI power estimate functions (`_est_power`, `_est_figure_power`, `_figure_power`, `_figure_power_from_dict`) across `game_state.py`, `action_enum.py`, and `strategy_planner.py`.
- Opponent card count display on hand holders in the client UI.
- `select_side_cards_to_swap()`, `summarize_side_change()`, and `compute_side_tactic_protected_ids()` in `card_change_strategy.py`.
- `_exec_change_side_cards()` in `ai_worker.py` for side card swap execution.
- `change_side_cards` action type in action enumeration and strategy planner.

### Changed

- Opponent card count text aligned with player text using `topleft` anchor; both nudged upward (`HAND_CARD_COUNT_Y_NUDGE` doubled to `-0.016`).
- Removed artificial cap on support bonus in build promotion scoring (was `min(est_support * 0.5, 5.0)`, now uses full support value).
- Figure draw order fixed so figures render in correct z-order without overlap issues.

### Fixed

- Health Boost crash when targeting Maharaja figure.
- `_execute_spell` error handling hardened.
- `ImportError` for `enrich_figures_with_skills` imported from wrong module.
- AI King building enabled with balanced LLM prompt.

## 2026-04-12

### Added

- Deterministic full-match server regression test covering challenge creation, pending counterable spell flow, advance and counter-advance, battle prep, three-round battle resolution, and checkmate game-over finalization.
- Client dialogue-flow contract tests for FIFO notification queue ordering, opponent-turn summary payload construction, and acknowledgement-driven progression to queued notifications.
- Explicit test-oracle documentation in advanced regression test classes so expected outcomes are clear and reviewable.

### Validation

- Local pytest suite: 155 passed.