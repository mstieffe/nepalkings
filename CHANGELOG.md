# Changelog

All notable changes to this project are documented in this file.

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