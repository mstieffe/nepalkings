# Conquer Invader Swap Prelude Implementation Plan

## Goal

Reintroduce `Invader Swap` as a conquerer-only prelude spell for conquer mode.

The spell swaps the conquer battle roles before the first advance: the original land defender becomes the automated invader, and the original conquerer becomes the defender/responding player. Duel-mode `Invader Swap` must keep its existing behavior.

## Confirmed design decisions

User feedback resolved the open product decisions as follows:

1. `Invader Swap` is available only as a conquerer prelude spell.
   - Do not add it to defence prelude options.
   - Do not add it to defence counter-spell options.
   - Do not change duel-mode spell/counter behavior.
2. After the swap, use a conquer-only turn budget:
   - New automated invader: 1 required advance action.
   - Original conquerer/current defender: 1 required response action.
   - This avoids redundant duel-style extra turns in conquer mode.
3. Defence config counter spell is ignored after `Invader Swap`.
   - Server log only; no player-facing notification.
4. Defence config counter-advance figure is used by the automated defender-now-invader if it can legally advance.
   - If the configured figure cannot legally advance, fall back to the strongest legal advance figure.
5. If no counter-advance figure is configured, choose the strongest legal advance figure automatically.
   - Strength uses effective battle power: base power + support + enchantments + buffs, while respecting battle modifiers and advance blockers.
6. If the automated defender-now-invader has no legal advance figure, it loses the conquer battle automatically; the original conquerer wins the land.
7. `Invader Swap` stacks with defender prelude modifiers such as `Peasant War` and `Civil War`.
   - Those restrictions apply to automated advance selection and to the conquerer’s response.
8. Fortress solution for blockable advances:
   - After the automated defender advances, the conquerer chooses one of their own legal defending figures.
   - Fortresses can be selected this way, because this is not a counter-advance.
9. Unblockable advances solution:
   - If the automated invader advances a `cannot_be_blocked` figure, the automated invader chooses the defending target.
   - Target selection priority: random village if possible, else random military, else random castle.

## Current behavior to preserve

### Duel mode

The existing `Invader Swap` tactics spell lives in the battle spell config and is executed in `server/routes/spells.py`.

Current duel behavior:

- swaps `game.invader_player_id` to the opponent,
- sets both players to 2 turns,
- sets `game.turn_player_id` to the new invader,
- clears stale advance/defend state,
- does not affect conquer cleanup/resolution rules.

This must remain unchanged for duel mode.

### Conquer mode today

Relevant current architecture:

- Conquer prelude allowlists exist in both `server/routes/games.py` and `server/routes/kingdom.py`.
- Client conquer prelude options are listed in `nepal_kings/game/screens/conquer_screen.py`.
- Defence prelude and counter options are separately listed in `server/routes/kingdom.py` and `nepal_kings/game/screens/defence_screen.py`.
- `_create_prelude_spell()` executes non-battle-modifier preludes immediately.
- `_BATTLE_MODIFIER_SPELLS` currently contains `Peasant War`, `Civil War`, and `Blitzkrieg`; these are appended to `game.battle_modifier` without calling `_execute_spell()`.
- Conquer defender automation is handled by `server/ai/ai_worker.py` for both AI lands and player-owned offline defence configs.

Important implication: `Invader Swap` must be a conquer prelude and `spell_type='tactics'`, but it must **not** be added to `_BATTLE_MODIFIER_SPELLS`; otherwise `_create_prelude_spell()` would only append a modifier and would not perform the role swap.

## Target game flow

### Blockable automated advance

1. Original conquerer starts a conquer battle with `Invader Swap` as their prelude.
2. Defender prelude, if any, resolves first.
3. Conquerer `Invader Swap` resolves:
   - original conquerer becomes current defender,
   - original defender becomes current invader,
   - both players get conquer-only 1-action budget,
   - turn moves to the automated defender/current invader,
   - any preselected defender/counter state is cleared.
4. Server automation advances for the defender/current invader:
   - configured defence battle figure if legal,
   - otherwise strongest legal advance figure.
5. If the advanced figure is blockable:
   - turn moves to the original conquerer/current defender,
   - client shows a specialized conquer notification,
   - player selects one of their own legal defending figures,
   - fortresses are legal if they pass defender-selection rules.
6. After defender selection:
   - turn returns to the automated invader,
   - automated invader submits the conquer auto-fight decision first,
   - original conquerer auto-submits defender fight decision after the invader decision exists,
   - battle moves proceed through existing conquer battle flow.

### Unblockable automated advance

1. Steps 1-4 are the same.
2. If the automated invader advances a `cannot_be_blocked` figure:
   - the conquerer does not get the own-defender selection prompt,
   - automated invader selects the target defender using the field-priority rule:
     1. random legal village,
     2. else random legal military,
     3. else random legal castle,
   - battle proceeds through existing conquer auto-fight flow.

### No legal automated advance

If the defender/current invader cannot advance any figure after the swap, call the existing conquer auto-loss path for `cannot_advance_loss`. The original conquerer wins the land.

## Server implementation plan

### 1. Add conquer prelude configuration

Update these allowlists/cost maps:

- `server/routes/games.py`
  - Add `Invader Swap` to `_CONQUER_PRELUDE_SPELLS`.
  - Do not add it to `_TARGETED_PRELUDE_SPELLS`.
- `server/routes/kingdom.py`
  - Add `Invader Swap` to `_CONQUER_PRELUDE_SPELLS`.
  - Add `Invader Swap` to `_SPELL_CARD_COST` as `('A', 2, None)`.
    - Existing `_find_free_cards()` groups `color=None` by same-color pools, so this enforces two same-color aces.
  - Add `Invader Swap` to `_SPELL_TYPE_MAP` as `tactics`.
  - Do not add it to `_DEFENCE_PRELUDE_SPELLS`.
  - Do not add it to `_DEFENCE_COUNTER_SPELLS`.
- `nepal_kings/game/screens/conquer_screen.py`
  - Add `Invader Swap` to `_CONQUER_PRELUDE_SPELLS`.
  - Add `Invader Swap` to the client `_SPELL_CARD_COST` as `('A', 2, None)`.
- `nepal_kings/game/screens/defence_screen.py`
  - Leave defence lists unchanged.

### 2. Split duel and conquer `Invader Swap` execution

Refactor the current `Invader Swap` branch in `server/routes/spells.py` into a helper, for example:

- `_execute_invader_swap_spell(spell, game, caster, spell_effect)`
- `_execute_duel_invader_swap(...)`
- `_execute_conquer_prelude_invader_swap(...)`

Conquer-specific behavior:

- Require `game.mode == 'conquer'` and `spell.effect_data.get('prelude_origin')`.
- Validate caster is the original conquerer/attacker.
  - If not, fail safely and mark spell effect as error.
  - This is defence-list hardening; the UI/server config should already prevent defence from selecting it.
- Determine:
  - `old_invader_id = game.invader_player_id`,
  - `new_invader = opponent player`,
  - original conquerer via existing `_conquer_attacker_player()`-style logic or a local helper to avoid circular imports.
- Set:
  - `game.invader_player_id = new_invader.id`,
  - `game.turn_player_id = new_invader.id`,
  - `old_invader.turns_left = 1`,
  - `new_invader.turns_left = 1`,
  - `game.advancing_figure_id = None`,
  - `game.advancing_figure_id_2 = None`,
  - `game.advancing_player_id = None`,
  - `game.defending_figure_id = None`,
  - `game.defending_figure_id_2 = None`,
  - `game.battle_decisions = None`,
  - `game.battle_confirmed = False`.
- Add effect data fields:
  - `invader_swapped=True`,
  - `conquer_invader_swap=True`,
  - `old_invader_id`,
  - `new_invader_id`,
  - `turn_set=True`,
  - `sets_turns=True`.
- If the defence config has `counter_spell_name`, log with `logger.info(...)` that it is ignored because of conquer `Invader Swap`.
  - Do not create a player-facing `LogEntry` for this, per feedback.

Duel-specific behavior remains exactly as today:

- both players get 2 turns,
- new invader starts,
- stale advance/defend state is cleared.

### 3. Add role-swap detection helpers

Add central helpers in `server/routes/games.py` and mirror minimal equivalents in `server/ai/ai_worker.py` if importing would create cycles:

- `_conquer_invader_swap_spell(game)`
  - returns executed prelude `ActiveSpell` named `Invader Swap` with `effect_data.conquer_invader_swap`.
- `_conquer_invader_swap_active(game)`
  - true if the spell exists and current invader is not the original conquerer.
- `_conquer_original_attacker_player(game)` / reuse existing `_conquer_attacker_player(game)` where available.
- `_conquer_current_defender_player(game)` / reuse existing `_conquer_defender_player(game)`.

Use these helpers instead of scattered role comparisons.

### 4. Automated defender/current-invader advance selection

Update `server/ai/ai_worker.py`, especially `_conquer_pick_counter_advance_figure()`.

When all are true:

- game mode is `conquer`,
- `Invader Swap` is active,
- automated defender is the current invader,
- no `game.advancing_figure_id` exists,

then pick the automated advance figure as follows:

1. If `game.defence_config_id` has a configured `battle_figure_id`:
   - map it to runtime figure via `Figure.source_config_figure_id`,
   - use it if `_conquer_figure_can_advance(..., counter=False)` returns true.
2. Otherwise fallback to strongest legal advance figure.
3. If no legal advance figure exists, call `/games/cannot_advance_loss` for the automated defender/current invader.

Strongest legal advance helper:

- Legal filters:
  - belongs to automated defender/current invader,
  - not resting,
  - not `cannot_attack`,
  - no resource deficit,
  - respects `Peasant War`/`Civil War` village-only restrictions,
  - no other battle-modifier restriction blocks it.
- Effective power estimate:
  - use server battle-power helpers where possible:
    - `_compute_figure_base_power`,
    - `_compute_support_bonus`,
    - `_compute_healer_buff`,
    - `_compute_enchantment_mod`,
    - `_find_temple_blocker`,
  - wall defence is `0` because this figure is advancing as invader,
  - active enchantments count,
  - support/Temple interactions count,
  - deterministic tie-break: higher power, then higher base power, then lower figure id.

Do not broadly change normal conquer defender counter-advance policy unless needed for shared helper extraction. Existing non-swap behavior should remain stable.

### 5. Automated target selection for unblockable advances

When `Invader Swap` is active and the automated invader has advanced a `cannot_be_blocked` figure:

- keep existing route semantics that counter-advance is skipped,
- automated player should select a defender target.

Update AI `select_defender` behavior for this special case:

1. Build legal opponent target pools.
2. Apply field priority:
   - legal villages first,
   - else legal military,
   - else legal castle.
3. Select randomly within the first non-empty pool.
4. Call `/games/select_defender` as the automated invader.
5. If no target exists, trigger the existing defender-no-figures conquer auto-loss route or add a small AI executor wrapper for it.

Legal target filtering should match `select_defender()` rules:

- not `cannot_defend`,
- not `cannot_be_targeted`,
- respects `Peasant War`/`Civil War` village-only restrictions,
- checkmate cannot be selected if another legal non-checkmate target exists,
- `must_be_attacked` is ignored for `cannot_be_blocked`, matching existing `_defender_selection_ignores_must_be_attacked()` behavior.

For tests, monkeypatch `random.choice` or seed `random` to make target selection deterministic.

### 6. Add own-defender selection endpoint for blockable swap flow

Add a conquer-only endpoint, for example:

- `POST /games/conquer_select_own_defender`

Request:

- `game_id`,
- `player_id`,
- `figure_id`.

Validation:

- token/ownership,
- game exists and mode is `conquer`,
- `Invader Swap` is active,
- player is the original conquerer/current defender,
- it is this player’s turn,
- opponent has advanced (`game.advancing_figure_id`),
- selected figure belongs to this player,
- selected figure is not already an advancing figure,
- selected figure passes defender-selection rules,
- if the advancing figure has `cannot_be_blocked`, reject with a clear error because the automated invader must select the target.

Legal defender-selection rules:

- allow `cannot_attack` figures such as fortresses,
- reject `cannot_defend`,
- reject `cannot_be_targeted`,
- respect `Peasant War`/`Civil War` village-only rules,
- enforce `must_be_attacked` among the selecting player’s own figures,
- handle checkmate like existing `select_defender()`:
  - checkmate can only be selected if no other legal non-checkmate defender exists,
- exclude resource-deficit defenders; if no non-deficit legal defender exists, resolve auto-loss for the original conquerer/current defender.

State changes on success:

- set `game.defending_figure_id` for first pick,
- support `game.defending_figure_id_2` for Civil War second pick,
- consume the defender response turn,
- set `game.turn_player_id = game.advancing_player_id` once defender selection is complete,
- add a clear server log entry with a new type such as `own_defender_select`.

Civil War handling:

- If a second same-color village defender is available, return:
  - `civil_war_need_second=True`,
  - `civil_war_color`,
  - `game`.
- Add or extend a skip route for this context:
  - either `POST /games/conquer_skip_own_defender_second`,
  - or extend `/games/skip_civil_war_second` with `context='own_defender'`.
- On skip, set turn to the automated invader.

### 7. Keep counter spells ignored after swap

Existing guard behavior already mostly supports this:

- `_get_conquer_counter_spell_config()` returns no config if the current defender is not the original land defender.
- `_conquer_should_cast_counter_spell()` only casts during original defender response windows.

Still add regression tests and, if needed, explicit checks using `_conquer_invader_swap_active(game)` so the ignored-counter-spell rule is obvious and stable.

Do not delete or mutate the configured defence counter spell; it remains part of the land defence config for future attacks.

### 8. Battle decision sequencing fix for swapped conquer flow

Current client conquer logic auto-submits the battle decision immediately when both battle figures exist. That is safe when the human is the invader, but after `Invader Swap` the human is the defender, and the server requires the invader to decide first.

Required behavior:

- If human is the advancing player/current invader:
  - keep current conquer auto-fight behavior.
- If human is the defender:
  - wait until `battle_decisions[str(game.advancing_player_id)] == 'battle'`,
  - then auto-submit defender `battle` decision,
  - do not show duel fight/fold UI.

This avoids a race where the defender submits before the automated invader and receives `Invader has not decided yet or already resolved`.

## Client implementation plan

### 1. Conquer config UI

Update `nepal_kings/game/screens/conquer_screen.py`:

- Add `Invader Swap` to `_CONQUER_PRELUDE_SPELLS`.
- Add card cost `('A', 2, None)`.
- No defence UI change.

Confirm `PreludeSpellScreen` can already display the existing `invader_swap.png` icon from the spell manager.

### 2. Prelude/game-start notifications

Update `nepal_kings/game/screens/game_screen.py`:

- Extend `_describe_conquer_prelude_effect()` for `Invader Swap`:
  - “Invader Swap: the defender became the invader. They must advance first; you will choose a defender unless the advance cannot be blocked.”
- Do not show a counter-spell ignored notification.
- Keep `Opponent Prelude`/`Prelude Spell` sequencing unchanged.

### 3. Add own-defender-selection client state

Update `nepal_kings/game/core/game.py`:

- Add flags such as:
  - `pending_conquer_own_defender_selection`,
  - `conquer_own_defender_selection_shown`,
  - `civil_war_own_defender_second` if a separate flag is cleaner.
- Detect the state when:
  - `mode == 'conquer'`,
  - `Invader Swap` is active or current role state indicates original conquerer is now defender,
  - `advancing_player_id != player_id`,
  - `turn_player_id == player_id`,
  - `advancing_figure_id` exists,
  - no `defending_figure_id` exists,
  - the advancing figure is not `cannot_be_blocked`.

The existing `pending_advance_notification` can still be used for the first alert, but the message must branch for this special mode.

### 4. Specialized response prompt

Update `check_opponent_advance_notification()` and draw helpers in `game_screen.py`:

- For normal conquer without swap: keep current “battle will begin shortly” behavior.
- For swapped blockable advance:
  - title: `Invader Swap — Choose Defender`,
  - message: automated defender advanced; select one of your own figures to defend,
  - mention fortresses can defend if legal,
  - mention `Peasant War`/`Civil War` restrictions when active.
- Add persistent prompt while waiting:
  - `SELECT YOUR DEFENDER`,
  - detail text adjusted for `Peasant War`/`Civil War`/fortress constraints.

### 5. Field screen selection behavior

Update `nepal_kings/game/screens/field_screen.py`:

- When `pending_conquer_own_defender_selection` is active:
  - clicking own figures calls the new service/endpoint instead of `/games/advance_figure`,
  - opponent figures should not be selectable,
  - visually indicate eligible own defenders.
- Fortresses should be selectable if legal.
- `cannot_be_targeted`/`cannot_defend` own figures should not be selectable.
- Civil War second selection should reuse existing dialogue style where possible.

Add client service wrapper in `nepal_kings/utils/game_service.py`:

- `select_conquer_own_defender(game_id, player_id, figure_id)`.

### 6. Battle-ready handling

Update `check_battle_ready()` in `game_screen.py`:

- In conquer mode, branch on whether the local player is `game.advancing_player_id`.
- If local player is defender:
  - wait for automated invader’s `battle` decision,
  - then submit defender `battle`,
  - do not display duel fight/fold prompts.

## Tests

### Server tests

Add tests mainly to `tests/server/test_land_battle.py` or a focused new file.

1. **Conquer config accepts Invader Swap**
   - Give user two same-color aces.
   - Set conquer prelude to `Invader Swap`.
   - Assert success, lock type `conquer_prelude`, and stored card IDs.

2. **Conquer config rejects insufficient Invader Swap cards**
   - Missing two same-color aces.
   - Assert 400.

3. **Defence config rejects Invader Swap**
   - Defence prelude endpoint rejects it.
   - Defence counter endpoint rejects it.

4. **Start battle applies conquer Invader Swap**
   - Attacker has `Invader Swap` prelude.
   - Defender has normal config.
   - Assert `game.invader_player_id` is defender player.
   - Assert `game.turn_player_id` is defender player.
   - Assert both turns are 1.
   - Assert no stale `advancing_figure_id`/`defending_figure_id`.
   - Assert ActiveSpell has `effect_data.conquer_invader_swap=True`.

5. **Defence counter spell ignored after swap**
   - Defender config has `counter_spell_name`.
   - Start battle with attacker `Invader Swap`.
   - Advance automated defender.
   - Assert no counter spell is executed.
   - Use `caplog` to assert server log-only message if practical.

6. **Configured legal defence figure advances after swap**
   - Defender config has a legal `battle_figure_id`.
   - Trigger automation or call helper.
   - Assert that figure becomes `game.advancing_figure_id`.

7. **Invalid configured figure falls back to strongest legal**
   - Configured figure is illegal: resting, `cannot_attack`, resource deficit, or non-village under `Peasant War`.
   - Add at least two legal alternatives with different effective power.
   - Assert strongest legal figure advances.

8. **No legal automated advance resolves attacker win**
   - All defender figures illegal to advance.
   - Trigger automation.
   - Assert conquer result is attacker win.

9. **Own defender selection allows fortress**
   - After swapped blockable advance, original conquerer selects a `Wooden Fortress`/`Stone Fortress` as own defender.
   - Assert endpoint succeeds and sets `game.defending_figure_id`.

10. **Own defender selection rejects illegal own defenders**
    - `cannot_defend`, `cannot_be_targeted`, resource deficit, wrong field under `Peasant War`/`Civil War`.

11. **Must-be-attacked enforced in own defender selection**
    - If conquerer owns a fortress and another selectable figure, selecting the non-fortress first is rejected.

12. **Unblockable automated advance target priority**
    - Automated invader advances `Cavalry`/`cannot_be_blocked`.
    - Opponent has village, military, castle targets.
    - Monkeypatch randomness.
    - Assert selected defender is from village pool first.
    - Remove village, assert military; remove military, assert castle.

13. **Battle decision sequencing after own defender selection**
    - Human defender does not submit before automated invader decision.
    - Automated invader decision is recorded first.
    - Human defender battle decision confirms battle.

14. **Duel regression**
    - Existing duel `Invader Swap` tests still pass.
    - Explicitly assert duel still grants 2 turns after `Invader Swap`.

### Client/manual validation

1. Conquer screen shows `Invader Swap` prelude and correct card cost.
2. Defence screen does not show `Invader Swap` in prelude or counter spell selectors.
3. Starting a battle with `Invader Swap` shows:
   - conquer intro,
   - own prelude spell result,
   - role as defender after swap.
4. Blockable automated advance shows “choose your defender” prompt.
5. Fortress click successfully selects fortress as defender.
6. Unblockable automated advance does not show own-defender prompt; automated target selection happens.
7. Battle proceeds without duel fight/fold UI.
8. Existing normal conquer flow without `Invader Swap` remains unchanged.

## Risk controls

1. Keep duel logic isolated.
   - Mode-specific branch in `Invader Swap` executor.
   - Do not alter duel tests or client duel prompts.
2. Keep normal conquer flow stable.
   - New own-defender endpoint is reachable only when conquer `Invader Swap` is active.
   - Automated strongest-advance fallback is used only for defender-as-invader after swap.
3. Avoid hidden player-facing counter-spell noise.
   - Ignored defence counter spell is server logger-only.
4. Avoid battle-decision race.
   - Client defender waits for automated invader’s `battle` decision.
5. Avoid target-selection dead ends.
   - No legal automated advance: auto-loss for automated defender/current invader.
   - No legal defending target after unblockable advance: defender-no-figures auto-loss.
   - No legal own defender after blockable advance: original conquerer/current defender auto-loses the battle.
6. Keep card fate unchanged.
   - `Invader Swap` prelude cards are conquer consumables.
   - Defence config cards remain locked/unchanged.
   - Ignored counter spell stays in defence config for future attacks.

## Suggested implementation order

1. Server allowlists/cost maps/type map and client conquer list.
2. Mode-specific `Invader Swap` executor with conquer turn budget and effect data.
3. Server role-swap helper functions and regression tests for startup state.
4. AI strongest legal advance selection after swap.
5. AI unblockable target-selection priority.
6. New own-defender selection endpoint and Civil War skip support.
7. Client own-defender selection state, notification, and field click handling.
8. Conquer battle-decision sequencing fix for human-as-defender.
9. Full server regression tests.
10. Manual client validation pass.

## Open technical details

No open product decisions remain after feedback. The remaining implementation-level details are:

- exact helper placement to avoid circular imports between `routes.games`, `routes.spells`, and `ai.ai_worker`,
- deterministic tie-breakers for strongest figure selection,
- deterministic test handling for random unblockable target selection,
- whether to add a new log entry type (`own_defender_select`) to client icon maps or reuse an existing neutral icon.
