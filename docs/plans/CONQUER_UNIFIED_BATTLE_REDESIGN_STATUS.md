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

- DONE: Kept tactics-hand battle rounds centered on the field shell.
  - Tactics-hand battle objectives and auto-routing now target `field` instead of the legacy `battle` subscreen.
  - The legacy battle tab is locked for tactics-hand games, while legacy `battle_move` games still route to `battle`.
  - `FieldScreen` now treats tactics-hand battle rounds as view-only inspection: figure detail boxes still open, but stale figure-action confirmations/selection flags cannot queue advance or defender actions.

- DONE: Added first-pass tactics-hand duel lane fighter rendering.
  - `ConquerGameScreen` now draws the current player/opponent battle figures inside the layout helper's `duel_lane` while the field remains the base view.
  - The lane handles the primary and optional second Civil War fighters from the player perspective and shows a compact starting power diff.
  - This is fighter-only rendering; support badges, leader lines, receipt rows, and tactic flight/replay remain follow-up work.

- DONE: Unified tactics-hand pre-battle and battle into the same field-first canvas.
  - Tactics-hand conquer games now normalize every legacy `battle` / `battle_shop` subscreen state back to `field`.
  - The legacy field/battle tab buttons are hidden and do not capture clicks for tactics-hand games.
  - The tactics rail and round ledger are visible from pre-battle onward.
  - Ledger result review now opens the shared conquer result dialogue from the unified field canvas instead of routing to the hidden battle subscreen.
  - `FieldScreen` now uses the shared conquer layout helper for tactics-hand field columns, so figure hitboxes align with the battlefield area instead of sitting underneath the rail.
  - The rail was narrowed to reduce empty horizontal padding and give more room back to the battlefield.

- DONE: Added richer tactics-hand duel lane round readouts.
  - The lane now shows the focused round's tactic badge for each side.
  - Tactic badges have leader lines back to their fighter bands.
  - The center diff band now shows a compact receipt row: figure power + tactic power = side total.

- DONE: Added first-pass predictive ledger math for hovered tactics.
  - The tactics rail now exposes the hovered available tactic during the player's battle turn.
  - The current round card draws that tactic as a ghost chip without committing it.
  - The round diff and total circle update with a ghost projection while the hover is active.

- DONE: Added first-pass round ledger recap popovers.
  - Hovering a completed round card now opens a compact recap above the card.
  - The recap shows each side's tactic power and the color/glyph-safe round diff.

- DONE: Added first-pass played tactic flight animation.
  - Successful tactics-hand Play actions start a fixed-duration, non-blocking overlay animation.
  - The animation travels from the selected rail cell toward the active round card slot and then expires.

- DONE: Added first-pass tactics-hand battle field context overlays.
  - Battle fighters are suppressed from their home field columns while the duel lane is active.
  - Remaining field figures stay inspectable but are visually de-emphasized during battle rounds.
  - Called figures and likely support-source figures get colored rings so their field origins remain locatable.

- DONE: Added first-pass round-card reveal replay animation.
  - Newly completed ledger rounds now get a short gold sweep/pulse keyed to the revealed tactic pair.
  - The animation expires without restarting every frame once the completed round identity is already known.

- DONE: Added first-pass duel-lane predictive tactic highlighting.
  - The hovered available rail tactic now appears as a cyan ghost badge in the active duel-lane support rail when the player has not committed that round.
  - The duel-lane receipt/diff preview uses the hovered tactic power, matching the ledger hover-preview behavior.

- DONE: Added first-pass field predictive source highlighting.
  - Hovering an available tactic that calls a figure now pulses that field figure as a cyan preview source.
  - Played called figures and support-source rings remain distinct from hovered preview rings.

- DONE: Added real first-pass duel-lane support contributor rails.
  - Player/opponent badge rails now collect actual non-fighter support contributors from the field: buffs_allies, wall/defence buffs, blocks_bonus, and distance_attack.
  - Support badges show source portrait, skill marker, and contribution value; overflow collapses to a +N chip.
  - Narrow chip rails now show compact called-figure, land-bonus, and enchantment modifier cues when available.

- DONE: Added first-pass duel-lane receipt rows.
  - The center diff band now stacks compact rows for base, called figure, buffs, wall, land, enchantment, tactic, range penalty, block marker, and total when those inputs are present.
  - Receipt totals now use the same visible contributor sources as the support/chip rails instead of only showing base+tactic.

- DONE: Added first-pass support badge hover cross-links.
  - Duel-lane support badges now register hit rects and highlight on hover.
  - Hovered support badges publish their source figure id to the field overlay and draw a cyan leader line to the source figure icon when its rect is available.

- DONE: Added first-pass support rail overflow popovers.
  - Overflow chips now register hover hit areas and open compact contributor popovers for hidden support sources.

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
- DONE: Focused field-routing regression passed: `tests/client/test_conquer_game_screen.py tests/client/test_conquer_timeline.py` passed: 83 passed.
- DONE: Broader conquer client render regression passed: `tests/client/test_conquer_game_screen.py tests/client/test_conquer_layout.py tests/client/test_conquer_timeline.py tests/client/test_battle_screen_conquer_flow.py tests/client/test_conquer_render_smoke.py` passed: 160 passed.
- DONE: Spell mutation regression passed: `tests/server/test_spells.py::TestSpellPurgesBattleMoves tests/server/test_spells.py::TestSpellMutatesConquerTactics` passed: 6 passed.
- DONE: Focused server regression passed: `tests/server/test_schema_guards.py tests/server/test_conquer_tactics_math.py tests/server/test_conquer_tactics_hand.py tests/server/test_spells.py tests/server/test_battle_shop.py tests/server/test_conquer_ai_defender_response.py tests/server/test_ai_action_enum.py tests/server/test_land_battle.py` passed: 135 passed.
- DONE: AI summary/planner/worker regression passed: `tests/server/test_ai_game_state.py tests/server/test_ai_strategy_planner.py tests/server/test_ai_worker.py tests/server/test_ai_action_enum.py` passed: 80 passed.
- DONE: AI worker tactics-hand routing regression passed: `tests/server/test_ai_worker.py` passed: 36 passed.
- DONE: Tactics math/card-fate regression passed: `tests/server/test_conquer_tactics_math.py` passed: 6 passed.
- DONE: Production schema guard regression passed: `tests/server/test_schema_guards.py` passed: 1 passed.
- DONE: Invader Swap tactics-hand regression passed: `tests/server/test_conquer_invader_swap.py` passed: 20 passed.
- DONE: Broader Invader Swap/tactics/AI worker regression passed: `tests/server/test_conquer_invader_swap.py tests/server/test_conquer_tactics_hand.py tests/server/test_ai_worker.py` passed: 66 passed.
- DONE: Unified pre-battle layout/routing regression passed: `tests/client/test_conquer_game_screen.py tests/client/test_conquer_timeline.py tests/client/test_conquer_layout.py` passed: 145 passed.
- DONE: Broader unified conquer client regression passed: `tests/client/test_conquer_game_screen.py tests/client/test_conquer_layout.py tests/client/test_conquer_timeline.py tests/client/test_battle_screen_conquer_flow.py tests/client/test_conquer_render_smoke.py` passed: 164 passed.
- DONE: Focused duel-lane readout regression passed: `tests/client/test_conquer_render_smoke.py tests/client/test_conquer_game_screen.py tests/client/test_conquer_layout.py` passed: 107 passed.
- DONE: Focused predictive ledger regression passed: `tests/client/test_conquer_render_smoke.py` passed: 4 passed.
- DONE: Broader predictive conquer client regression passed: `tests/client/test_conquer_game_screen.py tests/client/test_conquer_layout.py tests/client/test_conquer_timeline.py tests/client/test_battle_screen_conquer_flow.py tests/client/test_conquer_render_smoke.py` passed: 165 passed.
- DONE: Focused round recap ledger regression passed: `tests/client/test_conquer_render_smoke.py` passed: 5 passed.
- DONE: Broader round recap conquer client regression passed: `tests/client/test_conquer_game_screen.py tests/client/test_conquer_layout.py tests/client/test_conquer_timeline.py tests/client/test_battle_screen_conquer_flow.py tests/client/test_conquer_render_smoke.py` passed: 166 passed.
- DONE: Focused tactic flight regression passed: `tests/client/test_conquer_game_screen.py tests/client/test_conquer_render_smoke.py` passed: 53 passed.
- DONE: Broader tactic flight conquer client regression passed: `tests/client/test_conquer_game_screen.py tests/client/test_conquer_layout.py tests/client/test_conquer_timeline.py tests/client/test_battle_screen_conquer_flow.py tests/client/test_conquer_render_smoke.py` passed: 168 passed.
- DONE: Focused field context overlay regression passed: `tests/client/test_conquer_game_screen.py` passed: 49 passed.
- DONE: Focused round reveal replay regression passed: `tests/client/test_conquer_render_smoke.py` passed: 7 passed.
- DONE: Broader round reveal conquer client regression passed: `tests/client/test_conquer_game_screen.py tests/client/test_conquer_layout.py tests/client/test_conquer_timeline.py tests/client/test_battle_screen_conquer_flow.py tests/client/test_conquer_render_smoke.py` passed: 171 passed.
- DONE: Focused duel-lane predictive highlight regression passed: `tests/client/test_conquer_render_smoke.py` passed: 8 passed.
- DONE: Broader duel-lane predictive highlight conquer client regression passed: `tests/client/test_conquer_game_screen.py tests/client/test_conquer_layout.py tests/client/test_conquer_timeline.py tests/client/test_battle_screen_conquer_flow.py tests/client/test_conquer_render_smoke.py` passed: 172 passed.
- DONE: Focused field predictive source highlight regression passed: `tests/client/test_conquer_game_screen.py` passed: 50 passed.
- DONE: Broader field predictive source highlight conquer client regression passed: `tests/client/test_conquer_game_screen.py tests/client/test_conquer_layout.py tests/client/test_conquer_timeline.py tests/client/test_battle_screen_conquer_flow.py tests/client/test_conquer_render_smoke.py` passed: 173 passed.
- DONE: Focused duel-lane support contributor regression passed: `tests/client/test_conquer_render_smoke.py` passed: 9 passed.
- DONE: Broader duel-lane support contributor conquer client regression passed: `tests/client/test_conquer_game_screen.py tests/client/test_conquer_layout.py tests/client/test_conquer_timeline.py tests/client/test_battle_screen_conquer_flow.py tests/client/test_conquer_render_smoke.py` passed: 174 passed.
- DONE: Focused duel-lane receipt-row regression passed: `tests/client/test_conquer_render_smoke.py` passed: 9 passed.
- DONE: Broader duel-lane receipt-row conquer client regression passed: `tests/client/test_conquer_game_screen.py tests/client/test_conquer_layout.py tests/client/test_conquer_timeline.py tests/client/test_battle_screen_conquer_flow.py tests/client/test_conquer_render_smoke.py` passed: 174 passed.
- DONE: Focused support badge hover-link regression passed: `tests/client/test_conquer_render_smoke.py` passed: 9 passed.
- DONE: Broader support badge hover-link conquer client regression passed: `tests/client/test_conquer_game_screen.py tests/client/test_conquer_layout.py tests/client/test_conquer_timeline.py tests/client/test_battle_screen_conquer_flow.py tests/client/test_conquer_render_smoke.py` passed: 174 passed.
- DONE: Focused support overflow popover regression passed: `tests/client/test_conquer_render_smoke.py` passed: 10 passed.
- DONE: Broader support overflow popover conquer client regression passed: `tests/client/test_conquer_game_screen.py tests/client/test_conquer_layout.py tests/client/test_conquer_timeline.py tests/client/test_battle_screen_conquer_flow.py tests/client/test_conquer_render_smoke.py` passed: 175 passed.

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
  - DONE: Tactics-hand pre-battle and battle now share one field-first canvas with the rail, ledger, and field columns using the same layout helper.
  - DONE: Field inert-but-inspectable battle behavior is implemented for tactics-hand battle rounds.
  - DONE: First-pass battlefield context overlays dim non-fighters, hide fighters from home columns, and ring called/support-source figures.
  - DONE: First-pass duel lane fighter-only rendering is implemented for tactics-hand battle rounds.
  - DONE: Round tactic badge strips, leader lines, and power receipt rows are implemented in the duel lane.
  - DONE: First-pass ghost predictive math is implemented for rail-hovered tactics in the active ledger round and total circle.
  - DONE: First-pass played tactic flight animation is implemented for successful tactics-hand Play actions.
  - DONE: First-pass predictive support-badge pulsing is implemented in the duel lane for rail-hovered tactics.
  - DONE: First-pass predictive source highlighting pulses hovered tactic call-figure sources in the field.
  - DONE: Real first-pass support contributor badge rails are implemented for buffs, walls, blockers, and distance attackers.
  - DONE: First-pass receipt rows now explain the duel-lane diff from visible contributors.
  - DONE: First-pass support badge hover cross-links now highlight the badge/source and draw source leader lines.
  - DONE: First-pass support rail overflow popovers are implemented.
  - TODO: Receipt-row highlighting is still missing.
  - DONE: First-pass round-card recap popovers are implemented for completed ledger cards.
  - DONE: First-pass round-card reveal replay animation is implemented for newly completed ledger cards.

- PARTIAL: Phase 10 routing is mostly bypassed, but old naming still leaks into code.
  - TODO: Rename/cache aliases such as `_current_conquer_battle_moves` when the UI fully switches to tactics terminology.
  - DONE: Confirmed tactics-hand polling edge cases route stale move/battle targets back to `field`, not `battle_shop` or legacy `battle`.

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
3. Continue Phase 9 UI polish for duel-lane fighter rendering, support badges, receipt rows, and replay details.
4. Add Phase 11 screenshot/manual smoke checks once the remaining battle visuals exist.
