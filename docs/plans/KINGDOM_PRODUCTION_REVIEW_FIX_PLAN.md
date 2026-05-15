# Kingdom Production — Review Fix Plan

Follow-up to the Kingdom Production / Booster Skills implementation. Addresses
all ten concerns raised during the post-implementation review.

## Goals

1. Eliminate misleading "production stalled" signalling caused by ready
   booster packs.
2. Make collect labels read naturally when only boosters are ready.
3. Align action keys and class-internal names with the new "production"
   terminology.
4. Stop silently losing booster packs on auto-merge — credit them to the
   user's balance instead.
5. Tighten production-row copy and surface the capacity / no-carryover
   contract in the skill description.
6. Remove duplicated payload blocks and dead code.

## Non-goals

- Changing the production cadence, capacity defaults, or skill costs.
- Removing legacy `/collect_gold[_all]` routes or flat serializer aliases
  (kept for backward compatibility with deployed clients).

## Severity 1 — Correctness / behavior

### F1. Decouple "vault full" warning from "booster ready" state

**File:** `nepal_kings/game/screens/kingdom_screen.py` (`_draw_info_bar`)

- Track two flags:
  - `gold_vault_full` — set when a gold vault hits capacity (production
    actually stalled).
  - `boosters_ready` — set when any booster has `pending > 0` (info, not
    warning).
- Use only `gold_vault_full` to drive the red header colour and the
  `(FULL!)` badge on the Collect All button.
- Use `boosters_ready` only to enable the button and append the per-type
  counts to its label.
- Update tests in `tests/client/test_kingdom_screen.py` to assert that a
  ready booster does **not** turn the header red and does **not** add
  `(FULL!)`.

### F2. Build "Collect All" label from non-zero parts only

**File:** `nepal_kings/game/screens/kingdom_screen.py` (`_draw_info_bar`)

Replace the always-present `f'Collect All: {collectable_total}g'` prefix
with a `parts` list:

```python
parts = []
if collectable_total > 0:
    parts.append(f'{collectable_total}g')
if collectable_main_boosters:
    parts.append(f'{collectable_main_boosters} main')
if collectable_side_boosters:
    parts.append(f'{collectable_side_boosters} side')
label = 'Collect All' if not parts else 'Collect All: ' + ' + '.join(parts)
```

Update affected client tests.

### F3. Rename Collect button action to `collect_kingdom_production`

**File:** `nepal_kings/game/screens/kingdom_config_screen.py`

- Change both `_draw_button(..., 'collect_kingdom_gold', ...)` call sites
  to use `'collect_kingdom_production'`.
- Keep `'collect_kingdom_gold'` in the dispatch tuple and in
  `HANDLED_KINGDOM_CONFIG_ACTIONS` for one release as a deprecated alias.
- Add a one-line `# deprecated alias` comment.
- Update the existing button-action test to assert the new name and the
  alias still routes.

### F4. Auto-credit booster packs that would be lost on merge

**File:** `server/kingdom_service.py` (`_merge_source_kingdom_into_target`)

Sequence change inside the merge:

1. Accrue both kingdoms (already done).
2. For each booster spec in `_BOOSTER_PRODUCTION_ITEMS`:
   - Read `target_pending`, `source_pending`, `capacity`.
   - `combined = target_pending + source_pending`.
   - `kept = min(combined, capacity)`.
   - `overflow = combined - kept`.
   - If `overflow > 0`: `user.<user_attr> += overflow` (e.g.
     `user.booster_packs += overflow`) and append a structured note to a
     new `merged_overflow` dict on the merge result, e.g.
     `{'main_booster': 1, 'side_booster': 0}`.
   - Set `target.<pending_attr> = kept`; zero source.
   - Reset `target.<last_attr> = _utcnow()` only when `kept == capacity`
     (target now holds a ready pack — start a fresh cycle on next
     collection, consistent with the "no carryover" rule). Otherwise leave
     `last_attr` untouched.
3. Surface `merged_overflow` to the caller; the auto-merge path that
   composes notifications should mention transferred packs in the merge
   notification ("2 lands merged. +1 main booster credited.").

Tests:

- `tests/server/test_kingdom.py`: extend the auto-merge test to set both
  source/target pending = 1 and assert the user's `booster_packs`
  increased by 1 and target ends with `pending = 1`.
- Add a case where only one side has a ready pack — assert no overflow
  and target ends with `pending = 1`.

## Severity 2 — UX / messaging

### F5. Charging-row copy

**File:** `nepal_kings/game/screens/kingdom_config_screen.py`
(`_draw_production_item_row`)

Drop the `every {interval}` segment when a countdown is available:

```python
if not enabled:
    detail = 'Unlock skill to start production'
elif int(pending) > 0:
    detail = f'Ready: {int(pending)} / {int(capacity or 1)}'
elif remaining := self._format_seconds(item.get('seconds_remaining')):
    detail = f'Ready in {remaining}'
else:
    detail = f'Charging — every {self._format_hours(interval)}' if interval else 'Charging'
```

### F6 + F7. Surface capacity / no-carryover in skill text

**File:** `server/kingdom_progression.py`

Update the booster skill `description` strings to read e.g.:

> Produces one main-card booster pack on a timer. Capacity {cap}; pending
> packs do not carry over and the timer restarts on collection.

Where `{cap}` is interpolated from
`KINGDOM_MAIN_BOOSTER_PRODUCTION_CAPACITY` (and equivalent for side) at
module load.

No client change needed — the skill row reads `description` from the
server payload.

## Severity 3 — Code hygiene

### F8. Deduplicate `booster_production_config`

**File:** `server/routes/kingdom.py`

Lift the inline dict into a small helper inside the module:

```python
def _booster_production_config_payload():
    return {
        'main_booster': {
            'base_hours': config.KINGDOM_MAIN_BOOSTER_PRODUCTION_BASE_HOURS,
            'halving_factor': config.KINGDOM_MAIN_BOOSTER_PRODUCTION_HALVING_FACTOR,
            'capacity': config.KINGDOM_MAIN_BOOSTER_PRODUCTION_CAPACITY,
        },
        'side_booster': {
            'base_hours': config.KINGDOM_SIDE_BOOSTER_PRODUCTION_BASE_HOURS,
            'halving_factor': config.KINGDOM_SIDE_BOOSTER_PRODUCTION_HALVING_FACTOR,
            'capacity': config.KINGDOM_SIDE_BOOSTER_PRODUCTION_CAPACITY,
        },
    }
```

Use it in both `kingdom_config_route` and `kingdom_config_detail`.

### F9. Remove dead code

**File:** `nepal_kings/game/screens/kingdom_config_screen.py`

Delete `_draw_gold_vault_panel_legacy` and any private helpers it
exclusively uses. Re-run the focused client tests.

### F10. Tighten serializer payload (optional, low-risk)

**File:** `server/kingdom_service.py` (`serialize_kingdom_config`)

Keep flat aliases for one release window but mark them in code comments
as legacy. No structural change yet — flagged so a future cleanup PR can
remove them once all clients consume `production_items`.

## Test matrix

After implementing F1–F10:

```
.venv/bin/python -m pytest \
    tests/server/test_kingdom.py \
    tests/server/test_kingdom_config.py \
    tests/client/test_kingdom_config_screen.py \
    tests/client/test_kingdom_screen.py \
    tests/client/test_kingdom_settings.py
```

New tests to add:

- `test_kingdom_screen.py::test_info_bar_not_red_when_only_boosters_ready`
- `test_kingdom_screen.py::test_collect_all_label_drops_zero_gold_segment`
- `test_kingdom_config_screen.py::test_collect_button_uses_production_action`
- `test_kingdom.py::test_auto_merge_credits_overflow_booster_pack`
- `test_kingdom.py::test_auto_merge_no_overflow_when_only_source_ready`

## Rollout

1. Land F3 + F1 + F2 first (pure client polish, low risk).
2. Land F4 (server merge change) with its tests in the same PR.
3. Land F5 + F6 + F7 (copy changes).
4. Land F8 + F9 + F10 (cleanup).

No DB migration is required; behavior changes are at the application
layer only.
