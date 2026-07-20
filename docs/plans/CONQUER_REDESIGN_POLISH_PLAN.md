# Conquer Redesign Polish & Hardening Plan

Source review: `CONQUER_UNIFIED_BATTLE_REDESIGN_STATUS.md` (post v2.0-conquer-redesign work).
Scope confirmed with user: address all selected UX, logic, and edge-case items below.
Out of scope: opponent support always-visible, Double-Dagger source rank surfacing, Block/Call help text, auto-bind changes, withdraw timing restrictions.

---

## Phase 1 — Server logic hardening (highest risk, do first)

### 1.1 Fix `skip_battle_turn` available-tactic filter
- File: [server/routes/games.py](../../server/routes/games.py)
- Locate the tactics-hand branch of `skip_battle_turn` that queries `ConquerTactic.status='available'`.
- Change the filter to also require `played_round IS NULL` so already-played-but-not-yet-resolved rows don't block a legitimate skip.
- Tests:
  - Add `tests/server/test_conquer_tactics_hand.py::test_skip_allowed_when_only_played_tactics_remain`.
  - Existing skip-rejection test (`tactics still available`) must still pass.

### 1.2 Idempotency for tactics-hand mutating endpoints
- Endpoints: `play_conquer_tactic`, `gamble_conquer_tactic`, `combine_conquer_tactics`, `dismantle_conquer_tactic`, `conquer_withdraw`.
- File: [server/routes/games.py](../../server/routes/games.py).
- Approach (minimal, no schema change):
  - Each request accepts optional `client_action_id` (uuid from client).
  - Cache the last `(game_id, player_id, client_action_id)` → serialized response in an in-process LRU (e.g. `server/game_service/conquer_tactics_idempotency.py`). On retry within TTL (e.g. 30 s) return the cached response instead of re-validating turn state.
  - For `play_conquer_tactic`: before "not your turn" rejection, check if the targeted tactic already has `played_round` set by this player in the most recent round — if so, treat as success and return current battle state.
  - For `gamble/combine/dismantle`: same `client_action_id` short-circuit.
- Client:
  - [nepal_kings/utils/game_service.py](../../nepal_kings/utils/game_service.py): generate `client_action_id` (uuid4) per user-initiated action and forward it.
- Tests:
  - `tests/server/test_conquer_tactics_idempotency.py`: covers play/gamble/combine/dismantle/withdraw replay with same `client_action_id` returns identical result and does not duplicate state changes.

### 1.3 Withdraw race-condition safety (timing unchanged)
- File: [server/routes/games.py](../../server/routes/games.py) `conquer_withdraw`.
- Per user: withdraw remains allowed any time during battle.
- Add atomic guard: re-read `Game.conquer_result` inside the same transaction; if already non-null, return the cached resolved result (idempotent). Use `with_for_update()` on `Game` row when supported, otherwise compare a monotonically increasing `Game.action_seq` column read-modify-write.
- Combine with 1.2 so a withdraw that arrives mid-opponent-play cannot double-resolve.
- Tests: `tests/server/test_conquer_withdraw_race.py` simulating concurrent withdraw + play.

### 1.4 `dismantle_conquer_tactic` validates source card state
- File: [server/routes/games.py](../../server/routes/games.py) dismantle handler.
- Before restoring a source tactic to `status='available'`, validate:
  - Source `MainCard` row still exists.
  - Card is `in_deck=False` and `part_of_figure_id IS NULL` (still part of battle hand).
  - Card `player_id` matches the dismantler.
- If any source is invalid, do not restore that source; mark the combined tactic `status='discarded'` and log a warning. Return the surviving source(s) only.
- Tests: extend `tests/server/test_conquer_tactics_hand.py` for spell-purged-source-during-combined case.

### 1.5 `ConquerTactic.serialize()` exposes combine lineage
- File: [server/models.py](../../server/models.py) `ConquerTactic.serialize`.
- Always include `source_tactic_id_a`, `source_tactic_id_b`. (No opponent leak risk: IDs already exist; values stay masked elsewhere.)
- Tests: `tests/server/test_conquer_tactics_hand.py::test_serialize_exposes_combined_sources`.

### 1.6 Called-figure-destroyed at resolution
- File: server-side conquer resolver / battle math (locate via existing `_compute_server_total_diff` and call-figure handling).
- During tactic scoring, look up `call_figure_id` and verify the figure still exists and remains on the called field. If missing or moved, set the Call tactic's effective contribution to 0 (no base, no buff, no suit bonus).
- Tests: `tests/server/test_conquer_tactics_math.py::test_call_tactic_zeroed_when_called_figure_destroyed`.

### 1.7 Verify legacy battle-shop endpoints reject tactics-hand games
- File: [server/routes/battle_shop.py](../../server/routes/battle_shop.py) (or wherever `/battle_shop/*` is mounted).
- Audit `buy`, `return`, `confirm`, `gamble`, `combine`, `dismantle`. The status doc claims gamble/combine/dismantle already gate; double-check with explicit `if game.conquer_move_model == 'tactics_hand': abort 409` at the top of each route.
- Tests: extend `tests/server/test_battle_shop.py::TestTacticsHandBattleShopGating` to cover all six routes.

---

## Phase 2 — Client correctness fixes

### 2.1 Prevent clicking spell-purged tactics during replay
- File: [nepal_kings/game/screens/conquer_game_screen.py](../../nepal_kings/game/screens/conquer_game_screen.py) `_filter_conquer_tactics_by_displayed_step`.
- Currently mutates `status='available'` so the row renders. Replace with a transient render-only marker (e.g. tag the dict with `_render_ghost=True`) and keep `status` truthful.
- In [nepal_kings/game/components/conquer_tactics_rail.py](../../nepal_kings/game/components/conquer_tactics_rail.py):
  - Cells with `_render_ghost` are visually shown but mark them non-selectable / non-clickable (greyed cursor, click is a no-op with brief "Resolving spell…" hint).
- Tests: `tests/client/test_conquer_render_smoke.py::test_spell_replay_ghost_tactic_not_clickable`.

### 2.2 Reload mid-battle-round ledger sync
- Files: `conquer_game_screen.py`, `conquer_round_ledger.py`.
- On entering battle mode with cold caches, seed `_conquer_tactic_cache*` from the freshly-fetched `get_battle_state` payload before the ledger first renders.
- Verify ledger `_opp_played_per_round()` prefers `_current_conquer_opponent_tactics()` over `battle.opp_played` (status-doc claim — confirm with code, fix if stale).
- Tests: `tests/client/test_conquer_game_screen.py::test_reload_mid_round_renders_filled_ledger`.

### 2.3 Disconnect/timeout reconnection shows result dialogue
- Files: `conquer_game_screen.py`, `conquer_flow.py`.
- When `get_battle_state` returns a game whose `conquer_result` is already set but the client is in pre-result state, route directly to the shared result dialogue using the same idempotent payload from Phase 1.6.
- Tests: `tests/client/test_conquer_game_screen.py::test_reconnect_after_auto_loss_opens_result_dialog`.

### 2.4 Action buttons disabled during flight animation
- File: [nepal_kings/game/components/conquer_tactics_rail.py](../../nepal_kings/game/components/conquer_tactics_rail.py) (and the play dispatch in `conquer_game_screen.py`).
- Expose `is_tactic_flight_active()` on the screen; rail action buttons (Play, Gamble, Combine, Dismantle, Skip) become non-interactive while flight is running.
- The flight remains visually non-blocking elsewhere; only the action surface freezes.
- Tests: `tests/client/test_conquer_render_smoke.py::test_action_buttons_disabled_during_flight`.

---

## Phase 3 — Client UX polish

### 3.1 Surface gamble-block reason
- File: `conquer_tactics_rail.py`.
- When Gamble is rendered disabled, attach hover tooltip displaying `_gamble_block_reason()` string (e.g. "Already gambled this round", "3/3 gambles used", "No available tactics").
- Also surface as a small inline hint under the action button row when the disabled state is "sticky" (per-battle limit reached).
- Tests: `test_gamble_disabled_tooltip_shows_reason`.

### 3.2 Combine flow "1 of 2" indicator
- File: `conquer_tactics_rail.py`.
- When player has clicked Combine on a single Dagger and is awaiting the second pick:
  - Decorate the first Dagger cell with a lock/badge "1/2".
  - Combine action button label switches to "Pick 2nd Dagger" with a Cancel affordance.
  - Cells not eligible for second pick (non-Dagger, mismatched rank constraint) get dimmed.
- Tests: `test_combine_mode_marks_first_dagger`.

### 3.3 Tactics-remaining and gambles-left counters
- File: `conquer_tactics_rail.py` top strip.
- Render two compact badges:
  - "Tactics N" — count of `status='available' AND played_round IS NULL` for the player.
  - "Gambles K/3" — derived from existing gamble-limit data already accessible.
- Hide both during opponent's turn if they would leak info; player-side only.
- Tests: extend existing rail render smoke tests.

### 3.4 Expanded result dialogue aftermath
- Server: extend the finish-battle / result response payload (re-used by reconnection path 2.3) with:
  - `card_lost` (suit/rank) when the loser hands a card over.
  - `card_won` for the winner if any picked.
  - `land_name` and `land_kept_or_taken` summary.
  - `gold_awarded` / `points_awarded` (already partially present — consolidate).
  - `destroyed_figure_name` (already present).
- Client: result dialogue component renders these as discrete rows. Missing fields collapse cleanly.
- Files: server resolver / `_serialize_finished_conquer_result`, plus result dialogue in `conquer_flow.py` or its dedicated component.
- Tests:
  - Server: `tests/server/test_conquer_finish_battle.py::test_result_payload_includes_aftermath`.
  - Client: smoke render covers each populated field.

---

## Phase 4 — Coverage & regression

After each phase, run scoped suites:
- Phase 1: `tests/server/test_conquer_tactics_hand.py tests/server/test_conquer_tactics_math.py tests/server/test_conquer_tactics_idempotency.py tests/server/test_conquer_withdraw_race.py tests/server/test_battle_shop.py`.
- Phase 2/3: `tests/client/test_conquer_game_screen.py tests/client/test_conquer_layout.py tests/client/test_conquer_timeline.py tests/client/test_conquer_render_smoke.py tests/client/test_battle_screen_conquer_flow.py`.

Final pass before merge:
- Full server suite under `tests/server/`.
- Full client suite under `tests/client/`.
- Manual smoke: prelude → battle round 1 play → gamble → combine → dismantle → round 2 → resolve → result dialogue, plus a reload mid-round and a withdraw mid-battle.

---

## Implementation order

1. Phase 1.1 (skip filter) — small, isolated, blocker for legitimate skip.
2. Phase 1.5 (serialize lineage) — unblocks any client work that needs it.
3. Phase 1.2 (idempotency framework) — foundation for 1.3.
4. Phase 1.3 (withdraw race) — depends on 1.2.
5. Phase 1.4 (dismantle validation) — small, isolated.
6. Phase 1.6 (called-figure destroyed) — small, isolated.
7. Phase 1.7 (legacy shop audit) — small audit; mostly verification.
8. Phase 2.1 (purged tactic non-clickable).
9. Phase 2.2 (reload sync).
10. Phase 2.3 (reconnect result dialog) — depends on Phase 3.4 server payload shape.
11. Phase 2.4 (flight disables buttons).
12. Phase 3.4 (result aftermath payload + UI) — server first, then client.
13. Phase 3.1 (gamble tooltip).
14. Phase 3.2 (combine indicator).
15. Phase 3.3 (counters).

Each step is independently testable and shippable.

---

## Known risks

- Idempotency LRU is in-process; a server restart drops the cache. Acceptable because actions are short-lived (turn-scoped) and the alternative (DB-backed) is heavier than needed.
- Combine "Pick 2nd Dagger" introduces a transient client state; ensure spell timeline replays or opponent-turn arrivals cancel it cleanly to avoid stale selection.
- Aftermath payload changes are additive; legacy `battle_move` games should retain or gracefully omit new fields.

---

## Acceptance criteria

- All listed tests pass.
- Manual smoke flow completes without console warnings or UI artifacts.
- Reloading mid-round, withdrawing mid-battle, and replaying a played-tactic request (simulated retry) all produce coherent client state.
- Status doc `CONQUER_UNIFIED_BATTLE_REDESIGN_STATUS.md` is updated with a new "Polish & Hardening" section listing the completed phases.
