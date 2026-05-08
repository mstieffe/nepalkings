# Conquer Unified Battle Redesign Status

Last updated: 2026-05-08
Branch: v2.0-conquer-redesign
Plan source: Copilot memory plan.md for "Conquer Unified Battle Redesign"

## Current Baseline

- DONE: Branch exists and is tracking origin/v2.0-conquer-redesign.
- DONE: Working tree was clean before this implementation pass.
- DONE: New conquer games are marked with `Game.conquer_move_model='tactics_hand'` when `CONQUER_TACTICS_HAND_ENABLED=True`.
- DONE: Legacy conquer/duel games keep the `battle_move` model marker.

## Implemented In This Pass

- DONE: Added `ConquerTactic` SQLAlchemy model in `server/models.py`.
  - Fields include game/player, primary card, optional secondary card, family/suit/rank/value, split values, source, status, played_round, call_figure_id, source tactic ids for combine/dismantle, sort_order, created_at.
  - `Game.serialize()` now includes `conquer_tactics`.

- DONE: New tactics-hand conquer games initialize `ConquerTactic` rows instead of `BattleMove` rows.
  - Attacker config moves are converted to runtime `MainCard` plus `ConquerTactic`.
  - Player-owned defender config moves are converted the same way.
  - AI template defender moves are converted the same way.
  - Legacy `battle_move` games still use `_build_battle_moves_from_config` / `_build_battle_moves_from_template`.

- DONE: Added player-safe battle-state serialization for tactics-hand games.
  - `/games/get_battle_state` now returns `player_tactics` and `opponent_tactics`.
  - It also maps those lists into existing `player_moves` / `opponent_moves` keys so current client rail/ledger code can consume them.
  - Opponent unplayed tactics hide family/suit/rank/value.

- DONE: Added conquer-specific tactic endpoints in `server/routes/games.py`.
  - `POST /games/play_conquer_tactic`
  - `POST /games/gamble_conquer_tactic`
  - `POST /games/combine_conquer_tactics`
  - `POST /games/dismantle_conquer_tactic`

- DONE: Updated battle turn/skip/math plumbing for tactics-hand games.
  - `skip_battle_turn` checks available `ConquerTactic` rows.
  - `_compute_server_total_diff` reads played `ConquerTactic` rows for tactics-hand games.
  - Battle card collection/cleanup can collect played tactic cards and return/delete unplayed tactic rows.

- DONE: Closed legacy battle-shop mutation holes for tactics-hand games.
  - Existing legacy `buy`, `return`, and `confirm` gates remain.
  - Added blocking for old `gamble`, `combine`, and `dismantle` routes so tactics-hand games use the new endpoints.

- DONE: Updated client service and conquer rail dispatch.
  - `nepal_kings/utils/game_service.py` has wrappers for play/gamble/combine/dismantle conquer tactic endpoints.
  - `ConquerGameScreen` calls those wrappers for tactics-hand games.
  - Tactics rail now ignores discarded tactics in the playable hand and recognizes combined `Double Dagger` tactics.

- DONE: Added the tactics-hand battle/result collapsed header in `ConquerGameScreen`.
  - Battle/result mode now draws the layout-helper status strip plus narration log instead of the full timeline header.
  - The strip keeps phase/turn/stake/land-bonus chips visible, clears stale hidden timeline command rects, and exposes the existing Withdraw command for attackers.
  - Clicking the collapsed header temporarily expands the full timeline as an overlay.

- DONE: Tightened tactics rail text and render coverage.
  - Long tactic names, selected details, top-strip labels, and action buttons now fit inside their rail containers.
  - The rail top strip now shows state/intent labels without instruction-style copy and does not leak hidden opponent tactic details.
  - Added client render smoke coverage for a scrollable populated rail and a filled round ledger/result click target.

- DONE: Updated automated conquer battle-round execution enough for tactics-hand rows.
  - `server/ai/ai_worker.py` reads `ConquerTactic` rows for tactics-hand games.
  - Auto-gamble, auto-combine, play, and skip fallback route through conquer tactic endpoints when appropriate.
  - `server/ai/action_enum.py` can enumerate `play_conquer_tactic` / `gamble_conquer_tactic` for tactics-hand battle rounds.

- DONE: Updated AI game-state and strategy-planner summaries for tactics-hand games.
  - `server/ai/game_state.py` now labels live rows as `conquer_tactics` for tactics-hand conquer games instead of showing stale `battle_moves` wording.
  - `server/ai/strategy_planner.py` now emits `planned_conquer_tactics` and scores tactics-hand plans from available `ConquerTactic` rows while preserving compatibility `planned_battle_moves` data.
  - Planner prompt formatting now prefers `planned_conquer_tactics` when present.

- DONE: Added focused server tests in `tests/server/test_conquer_tactics_hand.py`.
  - Initialization creates `ConquerTactic` rows and no `BattleMove` rows for tactics-hand conquer games.
  - Opponent unplayed tactics are hidden in `/games/get_battle_state`.
  - Playing two tactics advances battle turn and round.
  - Gambling creates replacement tactics and does not delete persistent collection cards.
  - Gambling enforces once-per-round and three-per-battle limits.
  - Combining/dismantling restores source tactics.
  - Tactics-hand skip rejects while tactics are available and advances when no tactics remain.
  - Call-figure validation rejects wrong-field targets and accepts legal targets.
  - Family/rank consistency validation rejects corrupted tactic metadata and mismatched Double Dagger ranks.

- DONE: Added tactics-hand spell mutation service in `server/game_service/conquer_tactics_service.py`.
  - Purges `ConquerTactic` rows that reference cards moved or recycled by spells.
  - Restores surviving source tactics when a combined tactic is dismantled by card mutation.
  - Auto-converts eligible newly received runtime cards into spell-sourced tactics up to the tactics cap.
  - Replenishes automated defenders back to the standard tactics count after spell mutation.

- DONE: Updated spell and counter-spell mutation flows for tactics-hand conquer games.
  - `Forced Deal` and `Dump Cards` branch between legacy `BattleMove` purge/replenish and new `ConquerTactic` purge/replenish by `Game.conquer_move_model`.
  - `Forced Deal` purges stale move/tactic state before card ownership changes.
  - Battle-start prelude replenishment now uses `ConquerTactic` rows for tactics-hand games.
  - Counter-spell defender replenishment now uses `ConquerTactic` rows for tactics-hand games while preserving compatibility response keys.

- DONE: Updated broader land-battle tests to read the active conquer move model.
  - Tactics-hand conquer games assert against `ConquerTactic` rows.
  - Legacy rollback games still assert against `BattleMove` rows.
  - Figure creation coverage now uses a deterministic no-prelude AI template so it is not affected by generated spell preludes.

## Verified In This Pass

- DONE: Diagnostics reported no errors for edited Python/client files.
- DONE: `python -m pytest tests/server/test_conquer_tactics_hand.py` passed: 10 passed.
- DONE: Focused server/AI regression passed: 40 passed.
- DONE: Existing focused client layout/routing tests passed: 65 passed.
- DONE: Focused client header/layout regression passed: `tests/client/test_conquer_game_screen.py tests/client/test_conquer_layout.py` passed: 98 passed.
- DONE: Broader conquer client regression passed: `tests/client/test_conquer_game_screen.py tests/client/test_conquer_layout.py tests/client/test_conquer_timeline.py tests/client/test_battle_screen_conquer_flow.py` passed: 152 passed.
- DONE: Broader conquer client render regression passed: `tests/client/test_conquer_game_screen.py tests/client/test_conquer_layout.py tests/client/test_conquer_timeline.py tests/client/test_battle_screen_conquer_flow.py tests/client/test_conquer_render_smoke.py` passed: 154 passed.
- DONE: Spell mutation regression passed: `tests/server/test_spells.py::TestSpellPurgesBattleMoves tests/server/test_spells.py::TestSpellMutatesConquerTactics` passed: 6 passed.
- DONE: Focused server regression passed: `tests/server/test_schema_guards.py tests/server/test_conquer_tactics_math.py tests/server/test_conquer_tactics_hand.py tests/server/test_spells.py tests/server/test_battle_shop.py tests/server/test_conquer_ai_defender_response.py tests/server/test_ai_action_enum.py tests/server/test_land_battle.py` passed: 135 passed.
- DONE: AI summary/planner/worker regression passed: `tests/server/test_ai_game_state.py tests/server/test_ai_strategy_planner.py tests/server/test_ai_worker.py tests/server/test_ai_action_enum.py` passed: 80 passed.
- DONE: AI worker tactics-hand routing regression passed: `tests/server/test_ai_worker.py` passed: 36 passed.
- DONE: Tactics math/card-fate regression passed: `tests/server/test_conquer_tactics_math.py` passed: 6 passed.
- DONE: Production schema guard regression passed: `tests/server/test_schema_guards.py` passed: 1 passed.
- DONE: Invader Swap tactics-hand regression passed: `tests/server/test_conquer_invader_swap.py` passed: 20 passed.
- DONE: Broader Invader Swap/tactics/AI worker regression passed: `tests/server/test_conquer_invader_swap.py tests/server/test_conquer_tactics_hand.py tests/server/test_ai_worker.py` passed: 66 passed.

## Partial / Needs Follow-Up

- PARTIAL: Phase 5 tactic APIs exist, but need broader behavior coverage.
  - DONE: Basic tests exist for `gamble_conquer_tactic` replacement source behavior.
  - DONE: Basic tests exist for `combine_conquer_tactics` and `dismantle_conquer_tactic` restoration behavior.
  - DONE: Tests exist for `gamble_conquer_tactic` per-round and per-battle limits.
  - DONE: Tests exist for skip being allowed only when no available tactics remain.
  - DONE: Tests exist for legal/illegal call figure validation.
  - DONE: Tests exist for family/rank consistency validation.

- DONE: Phase 6 battle math, cleanup, card fate, and resolver idempotency are covered for tactics-hand rows.
  - DONE: Added total-diff tests for Block, Call figure, Double Dagger, land bonus, support, healer, wall, enchantment, and distance attack using `ConquerTactic` rows.
  - DONE: Added finish-battle/card-fate tests proving played tactic cards enter the returnable pool, picked card ownership, deck return, and row cleanup.
  - DONE: Verified unplayed tactic runtime cards are cleaned while played tactic cards remain collectible.
  - DONE: Verified the tactics-hand finish-battle cleanup path reuses the cached conquer resolver without duplicating attack logs.

- DONE: Phase 7 spell mutation has a first tactics-hand implementation.
  - DONE: Added `conquer_tactics_service` helper.
  - DONE: Replaced tactics-hand spell purge/replenish logic for Forced Deal and Dump Cards.
  - DONE: Added spell mutation tests proving stale tactics are purged/replenished without deleting persistent collection cards.
  - DONE: Added Forced Deal coverage for combined tactics: moving one Double Dagger source deletes the combined row, drops the moved source, restores the partner source, and recreates a spell-sourced tactic for the new owner when eligible.
  - TODO: Add more spell coverage for defender fallback edge cases and non-greed spell interactions if Phase 7 needs exhaustive coverage.

- DONE: Production startup explicitly ensures the `conquer_tactic` table and index exist for persistent deployments.

- PARTIAL: Phase 8 AI reads, summarizes, and plays tactics; remaining work is deeper scenario coverage.
  - DONE: `server/ai/game_state.py` and `server/ai/strategy_planner.py` summarize `conquer_tactics` explicitly for tactics-hand games.
  - DONE: Added AI worker tests proving tactics-hand play, auto-gamble, and auto-combine route to conquer tactic endpoints.
  - DONE: Added Invader Swap regression proving a swapped AI invader keeps tactics-hand rows and player-safe tactic serialization.
  - TODO: Add richer attacker/defender full-flow AI scenarios.
  - TODO: Check generic LLM action paths for `combine_conquer_tactics` enumeration if needed beyond deterministic conquer flow.

- PARTIAL: Phase 9 UI has a working rail/ledger shell, not the full visual spec.
  - DONE: Header collapsed status strip, narration log, transient timeline overlay, and battle-strip Withdraw command are implemented for tactics-hand battle/result modes.
  - DONE: Tactics rail text fitting and public-only top-strip intent labels are implemented.
  - TODO: Duel lane fighter-only rendering is not complete.
  - TODO: Support badge strips, source leader lines, and power receipt rows are missing.
  - TODO: Ghost predictive math and played tactic flight animation are missing.
  - TODO: Round-card replay/recap popovers are missing.
  - TODO: Field inert-but-inspectable battle behavior needs a dedicated pass.

- PARTIAL: Phase 10 routing is mostly bypassed, but old naming still leaks into code.
  - TODO: Rename/cache aliases such as `_current_conquer_battle_moves` when the UI fully switches to tactics terminology.
  - TODO: Confirm no stale battle-shop tab target appears during tactics-hand polling edge cases.

- PARTIAL: Phase 11 tests started but are not comprehensive.
  - DONE: Added server tests for tactic initialization from AI templates.
  - DONE: Added server tests for legacy `battle_move` rollback with `CONQUER_TACTICS_HAND_ENABLED=False`.
  - DONE: Added client tests for tactics-hand header mode switching, overlay expansion, hidden action rect clearing, and gamble/dismantle dispatch to conquer endpoints.
  - DONE: Added initial client render smoke tests for populated tactics rail scrolling and filled round ledger/result control behavior.
  - TODO: Add duel/battle-shop regression tests after legacy route gating changes.
  - TODO: Add broader screenshot/manual smoke checks for support badges, called figures, and long receipt rows once those visuals exist.

## Known Risks

- RISK: `Game.serialize()` currently includes full `conquer_tactics`, matching the old `battle_moves` serialization style. Player-safe hiding is implemented in `/games/get_battle_state`; any client path that consumes raw `game.conquer_tactics` should avoid displaying opponent unplayed details.
- RISK: Spell mutation now has tactics-hand coverage for Forced Deal and Dump Cards, but more edge-case spell coverage is still useful before production rollout.
- RISK: Existing UI/AI names still say battle move in several places. That is compatibility glue for now, not the final terminology.

## Suggested Next Session Start

1. Add deeper AI scenario tests for Invader Swap and richer attacker/defender full-flow behavior.
2. Add more Phase 7 spell edge coverage for combined tactics, defender fallback cases, and non-greed interactions.
3. Continue Phase 9 UI polish for the tactics rail, ledger, receipt rows, and replay details.
4. Add Phase 11 client/render smoke tests for populated tactics rail and round ledger.
