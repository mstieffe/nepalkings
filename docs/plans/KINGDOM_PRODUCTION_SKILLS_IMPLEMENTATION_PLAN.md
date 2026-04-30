# Kingdom Production Skills Implementation Plan

Date: 2026-04-30

## Confirmed decisions

- Skill timing: level 0 is disabled; level 1 starts at 96 hours; each higher level halves the interval.
- Skill balance: both new booster-production skills use max level 5 and cost multiplier 1, matching the standard 1/2/4/8/16 SP curve.
- Timing config granularity: main and side booster production have separate server config values, with the same defaults initially.
- Storage: use explicit database columns, not a generic JSON production state.
- Capacity: each booster type stores at most 1 pending pack per kingdom.
- Full-capacity behavior: no overflow and no carryover. If a kingdom is offline for longer than one interval, it still collects only 1 pack, and the next timer starts at collection time.
- Collection UX: one Collect button per kingdom collects all ready production from that kingdom: gold, main booster, and side booster.
- Map UX: the map-header Collect All button should collect all ready production across all owned kingdoms.
- Split/merge behavior: mirror existing gold behavior. Merges transfer/clamp pending production into the surviving kingdom; splits preserve progress on the surviving original kingdom and reset production on fresh daughter kingdoms.

## Current architecture summary

- Persistent kingdom progression and skill definitions are data-driven in `server/kingdom_progression.py` and re-exported through `server/server_settings.py`.
- Runtime kingdom production logic currently lives in `server/kingdom_service.py` as gold-vault helpers:
  - `kingdom_vault_state()`
  - `_accrue_pending_gold()`
  - `collect_kingdom_gold()`
  - `serialize_kingdom_config()`
- Kingdom routes expose gold collection through:
  - `POST /kingdom/<kingdom_id>/collect_gold`
  - `POST /kingdom/collect_gold_all`
- Client kingdom config UI currently has a dedicated Gold Vault card in `nepal_kings/game/screens/kingdom_config_screen.py`.
- Client map header currently aggregates `pending_gold` / `vault_cap` from serialized `my_kingdoms` in `nepal_kings/game/screens/kingdom_screen.py`.
- Skill icons are currently configured in both server skill definitions and client settings, and should move to `img/kingdom/skill_icons/`.

## New skill definitions

Add two skills to `KINGDOM_SKILL_DEFINITIONS`:

1. `main_booster_production`
   - Name: `Main Booster Production`
   - Description: produces one main-card booster pack when charged; storage capacity 1.
   - Max level: 5
   - Cost multiplier: 1
   - Effect values: production interval hours by level.
   - Defaults: `(96, 48, 24, 12, 6)`
   - Icon: `img/kingdom/skill_icons/main_booster_production.png`

2. `side_booster_production`
   - Name: `Side Booster Production`
   - Description: produces one side-card booster pack when charged; storage capacity 1.
   - Max level: 5
   - Cost multiplier: 1
   - Effect values: production interval hours by level.
   - Defaults: `(96, 48, 24, 12, 6)`
   - Icon: `img/kingdom/skill_icons/side_booster_production.png`

Also update existing skill icons:

- `gold_production` -> `img/kingdom/skill_icons/gold.png`
- `gold_vault` -> `img/kingdom/skill_icons/gold_vault.png`
- `shield_cost_reduction` -> `img/kingdom/skill_icons/shield.png`
- `core_protection` -> `img/kingdom/skill_icons/core_protection.png`

## Server configuration

Add separate configurable constants for main and side production, probably in `server/kingdom_progression.py` and re-exported through `server/server_settings.py`:

- `KINGDOM_MAIN_BOOSTER_PRODUCTION_BASE_HOURS = 96`
- `KINGDOM_MAIN_BOOSTER_PRODUCTION_HALVING_FACTOR = 0.5`
- `KINGDOM_MAIN_BOOSTER_PRODUCTION_CAPACITY = 1`
- `KINGDOM_SIDE_BOOSTER_PRODUCTION_BASE_HOURS = 96`
- `KINGDOM_SIDE_BOOSTER_PRODUCTION_HALVING_FACTOR = 0.5`
- `KINGDOM_SIDE_BOOSTER_PRODUCTION_CAPACITY = 1`

Add helper functions so skill definitions and service code use the same config:

- `booster_production_interval_hours(item_key, level)`
- `booster_production_effect_values(item_key, max_level=5)`

The helper should return no active interval for level 0 and should clamp invalid levels defensively.

## Database model changes

Use explicit columns on `Kingdom`:

- `pending_main_boosters` integer, default 0, server default `0`
- `last_main_booster_collection_at` datetime, nullable
- `pending_side_boosters` integer, default 0, server default `0`
- `last_side_booster_collection_at` datetime, nullable

Column semantics:

- `pending_*_boosters` is persisted pending storage, clamped to capacity 1.
- `last_*_booster_collection_at` marks the start of the current production cycle when storage is empty.
- When storage is full, serialization reports ready/full without accruing overflow.
- On collect, transfer pending packs to the owning user, set pending back to 0, and set the timestamp to now.

Because this project uses `db.create_all()` but no Alembic migrations, include an idempotent schema-upgrade step or deployment SQL for existing databases. The safest implementation option is an app-start helper that checks the `kingdom` table for missing columns and issues `ALTER TABLE` only when needed, with tests against SQLite. Alternatively, document manual SQL for production deployment.

## Server production service design

Refactor the gold-only service into a small production layer while preserving existing behavior.

### Production snapshot helpers

Add typed booster helpers in `server/kingdom_service.py`:

- `kingdom_booster_production_level(kingdom, item_key)`
- `kingdom_booster_interval_hours(kingdom, item_key)`
- `kingdom_booster_state(kingdom, item_key, now=None)`
- `_accrue_pending_booster(kingdom, item_key, now=None)`

Suggested snapshot shape per booster item:

- `key`: `main_booster` or `side_booster`
- `label`: player-facing name
- `skill_key`: linked skill
- `level`
- `enabled`
- `pending`
- `capacity`
- `full`
- `interval_hours`
- `progress_ratio`
- `seconds_remaining`
- `ready_at`
- `icon_path`

For level 0:

- `enabled = False`
- `pending = 0`
- `progress_ratio = 0`
- `seconds_remaining = None`
- `ready_at = None`

For level > 0 and pending 0:

- Calculate elapsed time from `last_*_booster_collection_at` or `last_upgraded_at` or `created_at`.
- If elapsed >= interval, snapshot reports `pending = 1`, `full = True`, `progress_ratio = 1.0`.
- Do not mutate the row during serialization.

For collect:

- Accrue first.
- Transfer at most capacity 1 to `User.booster_packs` or `User.booster_packs_side`.
- Reset pending to 0 and reset the cycle timestamp to now.
- Do not carry leftover elapsed time.

### Unified collection helper

Add a new service function:

- `collect_kingdom_production(kingdom, user, now=None)`

It should:

1. Accrue gold and both booster items.
2. Transfer integer gold to `User.gold`.
3. Transfer pending main booster to `User.booster_packs`.
4. Transfer pending side booster to `User.booster_packs_side`.
5. Reset collected pending production.
6. Return a rich result payload.

Suggested result fields:

- `collected_gold`
- `collected_main_boosters`
- `collected_side_boosters`
- `collected_items`
- `gold`
- `booster_packs`
- `booster_packs_side`
- `production` snapshot after collection
- Backward-compatible aliases: `collected`, `pending_gold`, `vault_cap`, `total_gold`

Keep `collect_kingdom_gold()` as a compatibility wrapper or have it call the unified function and return legacy tuple fields where needed.

### Skill upgrade behavior

Update `kingdom_config_skill_upgrade()`:

- When upgrading `main_booster_production` from 0 to 1, initialize `last_main_booster_collection_at = now`, `pending_main_boosters = 0`.
- When upgrading `side_booster_production` from 0 to 1, initialize `last_side_booster_collection_at = now`, `pending_side_boosters = 0`.
- When upgrading from level N to N+1, keep the existing timer start. The shorter interval may make a pack ready sooner on the next snapshot.

### Split/merge handling

In `_merge_source_kingdom_into_target()`:

- Accrue source and target production before transferring pending boosters.
- Transfer pending main boosters with `min(capacity, target_pending + source_pending)`.
- Transfer pending side boosters the same way.
- Reset source pending boosters to 0.
- Keep the target kingdom's timer/progression semantics, matching gold's survivor-oriented behavior.

In split/new kingdom creation:

- New daughter kingdoms start with pending boosters 0 and timer timestamps set to now.
- The original surviving kingdom keeps its production state.

## Route changes

Add new clearer endpoints:

- `POST /kingdom/<kingdom_id>/collect_production`
- `POST /kingdom/collect_production_all`

Keep old endpoints for compatibility:

- `POST /kingdom/<kingdom_id>/collect_gold`
- `POST /kingdom/collect_gold_all`

The old endpoints should use the new unified collection logic and include old gold fields plus new booster fields. This lets existing clients keep working while the updated clients can display richer production results.

For `collect_production_all` / `collect_gold_all`:

- Iterate all owned kingdoms.
- Collect gold and boosters from each.
- Return totals:
  - `collected_gold_total`
  - `collected_main_boosters_total`
  - `collected_side_boosters_total`
  - `collected_total` as legacy gold-only alias
  - `gold`
  - `booster_packs`
  - `booster_packs_side`
  - per-kingdom breakdown with the same fields.

## Serialization changes

Extend `serialize_kingdom_config()` with:

- `production_items`: ordered list for future-friendly UI rendering.
- `production`: dict keyed by item key.
- Booster aliases for simple client use:
  - `pending_main_boosters`
  - `main_booster_capacity`
  - `main_booster_full`
  - `main_booster_interval_hours`
  - `main_booster_seconds_remaining`
  - `pending_side_boosters`
  - `side_booster_capacity`
  - `side_booster_full`
  - `side_booster_interval_hours`
  - `side_booster_seconds_remaining`

Preserve existing gold fields:

- `vault_pending`
- `vault_cap`
- `vault_full`
- `vault_rate_per_hour`
- `pending_gold`
- `gold_rate_per_hour`

Also update `_serialize_skill_definitions()` to expose the new skill definitions and new icon paths.

## Client settings changes

Update `nepal_kings/config/kingdom_settings.py`:

- Point all existing kingdom skill icons to `img/kingdom/skill_icons/`.
- Add paths for `main_booster_production` and `side_booster_production`.
- Add UI constants for production rows if needed:
  - row height
  - production progress bar colors
  - booster-ready color
  - booster-full color

## Client kingdom config UI

Refactor the current Gold Vault card into a Kingdom Production card.

Suggested changes in `kingdom_config_screen.py`:

- Rename `_draw_vault_panel()` to `_draw_production_panel()`.
- Title the panel `Kingdom Production`.
- Render three sections initially:
  1. Gold Vault
  2. Main Booster Pack
  3. Side Booster Pack
- Use a shared row renderer that consumes server `production_items`, so future items only need a new server item plus icon/config.
- Keep a single card-level `Collect` button, disabled only when no item is collectable.
- For gold row:
  - Show `pending / cap gold` and gold/hr rate.
  - Keep near-full/full colors.
- For booster rows:
  - If skill level 0: show `Unlock skill to start production`.
  - If charging: show progress bar and time remaining.
  - If ready/full: show `Ready: 1 / 1` and highlight the row.
  - Show interval text, e.g. `Every 48h at Lv 2`.

Update `_collect_kingdom_gold()` into `_collect_kingdom_production()`:

- Call the unified endpoint.
- Update `state.user_dict['gold']`, `booster_packs`, and `booster_packs_side` if present.
- Update local kingdom production snapshots from the response.
- Spawn feedback:
  - `+Ng` gold floater when gold was collected.
  - `+N main booster` / `+N side booster` message or small floater when boosters were collected.

Update `_skill_effect_text()`:

- For `main_booster_production` and `side_booster_production`, show:
  - Level 0 current: `disabled`
  - Current: `every 96h`, `every 48h`, etc.
  - Next: next interval.

## Client map header UI

Update `kingdom_screen.py`:

- Aggregate collectable gold as today.
- Aggregate ready main and side boosters from `my_kingdoms` serialized production fields.
- Rename label from `Collect All: Ng` to something like `Collect All: Ng + M main + S side`.
- Enable the button if any of gold/main/side production is collectable.
- Highlight full state if any gold vault is full or any booster slot is full.
- Update `_collect_all_gold()` into `_collect_all_production()` while keeping the old method as a wrapper if tests expect it.
- On response, sync `gold`, `booster_packs`, and `booster_packs_side` into `state.user_dict`.
- Show gold floater and a concise message for booster packs collected.

## Tests

### Server tests

Add or update tests in `tests/server/test_kingdom_config.py` and related kingdom tests:

1. Skill definitions include both booster production skills with interval effect values `(96, 48, 24, 12, 6)` and icon paths in `img/kingdom/skill_icons/`.
2. Level 0 booster production is disabled and does not accrue.
3. Level 1 main booster produces exactly 1 pack after 96h.
4. Level 2 main booster produces after 48h.
5. Side booster production mirrors main booster logic with its separate config constants.
6. Capacity is clamped to 1 after long offline periods.
7. Collecting resets timer to now and does not carry overflow.
8. Unified per-kingdom collection transfers gold + main + side production together.
9. Unified collect-all aggregates across multiple kingdoms.
10. Skill upgrade from level 0 initializes booster timer at upgrade time, not at kingdom creation time.
11. Merge transfers/clamps pending booster packs like gold.
12. Split keeps original production state and initializes fresh daughter kingdom production state.
13. Serialization does not mutate booster accrual state, matching the existing gold serialization test.
14. Backward-compatible gold endpoint still returns legacy gold fields.

### Client tests

Update/add tests in `tests/client/test_kingdom_config_screen.py`:

1. New skill icons are loaded from `img/kingdom/skill_icons/`.
2. Booster skill effect text displays intervals correctly.
3. Kingdom Production card renders gold, main booster, and side booster sections.
4. Collect button is enabled when either gold or a booster is ready.
5. Collect response updates local gold and booster counts.
6. Ready booster rows show a ready/full state.

Update/add tests in `tests/client/test_kingdom_screen.py`:

1. Header Collect All is enabled by ready boosters even when collectable gold is 0.
2. Header label includes booster counts.
3. Collect-all response syncs booster counts into state.
4. Existing gold-only collect behavior remains compatible.

## Backward compatibility and rollout

- Keep all old gold fields in serialized kingdom payloads.
- Keep old gold collection endpoint paths and response aliases.
- Add new fields rather than replacing old ones initially.
- Document or automate database column additions before deploying to a persistent database.
- Ensure clients that only understand gold ignore new production fields safely.

## Implementation order

1. Update skill icons and add new skill definitions/config constants.
2. Add database columns and schema-upgrade/deployment support.
3. Add server booster production snapshot/accrual helpers.
4. Add unified collection service and route aliases.
5. Extend kingdom serialization with production fields.
6. Update split/merge handling.
7. Refactor kingdom config UI from Gold Vault card to Kingdom Production card.
8. Update map header Collect All to collect all production.
9. Add server and client tests.
10. Run focused tests, then broader kingdom/client test suites.

## Validation commands

Run focused tests first:

- `python -m pytest tests/server/test_kingdom_config.py tests/server/test_kingdom.py`
- `python -m pytest tests/client/test_kingdom_config_screen.py tests/client/test_kingdom_screen.py`

Then run the broader suite if time allows:

- `python -m pytest tests/server tests/client`

## Risks and mitigations

- Existing databases will not receive new columns from `db.create_all()` alone. Mitigation: idempotent schema upgrade or explicit deployment SQL.
- Lazy serialization must not mutate booster timers, matching current gold behavior. Mitigation: snapshot helpers are side-effect free; collection helpers do mutation.
- Capacity 1 with no carryover can surprise users after long offline periods. Mitigation: UI clearly marks full/ready state and map header highlights collectable boosters.
- Adding skills increases skill rows and may crowd the config panel. Mitigation: keep row height adaptive and consider scroll if six skills no longer fit comfortably.
- Old tests and clients expect gold-specific method names. Mitigation: keep wrappers/aliases and only add fields.
