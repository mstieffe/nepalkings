# Maps Feature — Implementation Plan

Adds a new tradeable item ("maps"), two new kingdom skills (`map_production`,
`atlas`), HUD/production-card integration, a conquer-cooldown bypass action,
and a reworked duel reward distribution that includes maps.

This plan is intentionally additive: every change parallels an existing
booster-pack/gold-vault pattern, so existing logic remains untouched.

---

## 1. Confirmed design (from feature Q&A)

| Topic | Decision |
|---|---|
| Atlas scope | Per-kingdom pending-cap only (wallet unlimited), mirrors booster capacity. |
| Cooldown bypassed | Only the user-level cooldown (`User.last_conquer_at`). Land-defense cooldown unaffected. |
| Map consumption UX | Explicit confirmation dialog before consuming. |
| Refuse if cooldown is 0 | Yes — server rejects, client hides the option. |
| Spam limit | None — one map per bypass, otherwise unrestricted. |
| Production-card layout | Single row, 4 equal columns. |
| Map icon source | Use `img/dialogue_box/icons/map.png` directly. |
| Starter maps | 0. |
| Map purchase via shop | No. |
| `map_production` curve | L0 disabled; L1=48h, L2=24h, L3=12h, L4=6h, L5=3h (max level 5, halving 0.5). |
| `atlas` curve | L0=1, L1=2, L2=3, L3=4, L4=5, L5=6 pending maps per kingdom (max level 5). |
| Duel rewards (rework) | Winner draws **3 items**, loser draws **1 item**, each item is randomly one of: main booster, side booster, map, or a small fixed gold portion. |

---

## 2. Server changes

### 2.1 Schema (`server/models.py`)

Add columns (with `default=0` / `nullable=True`, so existing rows backfill
safely without a manual migration):

- `User.maps` — `db.Column(db.Integer, nullable=False, default=0, server_default='0')`
- `Kingdom.pending_maps` — `db.Column(db.Integer, nullable=False, default=0, server_default='0')`
- `Kingdom.last_maps_collection_at` — `db.Column(db.DateTime, nullable=True)`

Mirror the placement of the equivalent booster fields. The local SQLite DB
auto-creates new columns on startup via the existing `db.create_all()` path;
PythonAnywhere production DB uses the same path. Document in
[server/RESET_DATABASE.sh](server/RESET_DATABASE.sh) only if the existing
booster fields required a reset (they did not — same applies here).

### 2.2 Settings (`server/server_settings.py`)

Add:

```python
STARTER_MAPS = 0

# Duel reward rework — pool-based draws including maps
DUEL_WINNER_REWARD_DRAWS = 3
DUEL_LOSER_REWARD_DRAWS = 1
DUEL_REWARD_GOLD_AMOUNT = 25  # gold awarded per "gold" draw
DUEL_REWARD_POOL_PROBABILITIES = {
    'main_booster': 0.30,
    'side_booster': 0.30,
    'map':          0.15,
    'gold':         0.25,
}
```

Keep `DUEL_WINNER_BOOSTER_PACKS` / `DUEL_LOSER_BOOSTER_PACKS` /
`DUEL_BOOSTER_REWARD_PROBABILITIES` for now, marked as **deprecated** in a
comment (the new code path no longer reads them). Tests in
[tests/server/test_server_settings_v2.py](tests/server/test_server_settings_v2.py)
that assert the old constants stay valid will continue to pass; new tests
cover the new constants.

### 2.3 Skill definitions (`server/kingdom_progression.py`)

Add two skill keys with the same data-driven shape used by
`main_booster_production`, `side_booster_production`, `gold_vault`:

- `KINGDOM_MAP_PRODUCTION_BASE_HOURS = 48` (env-overridable).
- `KINGDOM_MAP_PRODUCTION_HALVING_FACTOR = 0.5`.
- Capacity for maps **comes from the atlas skill level**, not a static
  constant. Implement a helper:

```python
def map_pending_capacity_for_atlas_level(level: int) -> int:
    return max(1, 1 + int(level or 0))
```

- Extend `booster_production_interval_hours()` (or add a parallel helper) to
  understand `item_key='map'` so existing booster code paths stay unchanged.
  Preferred: introduce a small dispatcher

```python
def production_interval_hours(item_key: str, level: int) -> float:
    if item_key == 'map':
        ...
    return booster_production_interval_hours(item_key, level)
```

  and reuse it from `kingdom_service`.

- Append two `KingdomSkillDef` entries:
  - `key='map_production'`, `max_level=5`, `cost_multiplier` matching the
    booster production skills, effect values from
    `production_interval_hours('map', L)` for L=1..5.
  - `key='atlas'`, `max_level=5`, `cost_multiplier` matching `gold_vault`,
    effect values `(2, 3, 4, 5, 6)` (capacity at L1..L5).

### 2.4 Production logic (`server/kingdom_service.py`)

Add a generic helper `kingdom_map_state(kingdom)` that mirrors
`kingdom_booster_state(...)` but:

- Reads `pending_maps` / `last_maps_collection_at`.
- Production interval from `map_production` skill level.
- Capacity from `atlas` skill level via `map_pending_capacity_for_atlas_level`.
- Returns the same dict shape as booster state (`key='map'`,
  `kind='map'`, `label='Maps'`, plus `pending`, `capacity`, `enabled`,
  `progress_ratio`, `seconds_remaining`, `ready_at`, `collectable`).

Add `_accrue_pending_maps(kingdom)` paralleling `_accrue_pending_booster`,
sharing as much logic as possible (refactor the booster accrual into a
private generic helper that takes the field names + interval/capacity
callbacks; this keeps both call sites clean and avoids divergence).

Update `collect_kingdom_production(kingdom, user)`:

- Accrue maps first.
- Move `kingdom.pending_maps → user.maps`, reset `last_maps_collection_at`
  the same way the booster path does.
- Add `collected_maps` to the return dict.

Update `_production_items(kingdom)` (or whichever function currently
returns the ordered production-items list) to append the map state after
side boosters. If skill not unlocked (`map_production` level 0), still
include the entry with `enabled=False` so the UI can display the locked
slot identically to boosters.

Reset rule on first level-up (the existing booster pattern resets
`pending_*` and `last_*_collection_at`): apply the same reset for both
`map_production` and `atlas` upgrades from L0→L1 (atlas at L0 already
allows 1 pending; the cap merely grows on subsequent upgrades, no reset).

### 2.5 Routes — kingdom (`server/routes/kingdom.py`)

- Extend the kingdom-config serializer to include atlas+map_production
  skills (automatic via `KINGDOM_SKILL_DEFINITIONS`).
- `collect_gold` / `collect_gold_all`: include `collected_maps` and `maps`
  (user total) in the response payload.
- Update `_serialize_user_summary` (or whichever helper builds the
  `user_dict` returned to the client after kingdom actions) to include
  `maps`.

### 2.6 Routes — auth/me (where user state is returned)

Find every place that serializes the current user (login response, `/me`,
collection-screen refresh) and add `maps` alongside `booster_packs`. Use
grep for `'booster_packs':` to enumerate; this is exactly parallel.

### 2.7 Conquer cooldown bypass

Modify the conquer endpoint in `server/routes/kingdom.py` (around the
existing `effective_cooldown` block):

```python
use_map = bool(request.json.get('use_map'))
if user.last_conquer_at:
    elapsed = (now - user.last_conquer_at).total_seconds()
    if elapsed < effective_cooldown:
        if not use_map:
            return error(f'Conquer on cooldown. {remaining}s remaining.',
                         code='cooldown',
                         remaining=remaining,
                         maps_available=user.maps)
        if user.maps <= 0:
            return error('No maps available.', code='no_maps')
        # Atomic: decrement map, clear user cooldown, then proceed.
        user.maps -= 1
        user.last_conquer_at = None
        # Map consumption is logged in the conquer audit log entry below.
```

Important guards:

- The map is consumed only **after** all other pre-conquest validation
  passes (target legality, gold cost, etc.) — restructure the function so
  the cooldown branch runs after those checks. This avoids consuming a map
  for a conquest that would have been rejected anyway.
- If `use_map=True` is sent while cooldown is already 0, return
  `error('Cooldown not active.', code='no_cooldown')` and do **not**
  decrement.
- Wrap the decrement+conquest in a single DB transaction (already implicit
  in Flask-SQLAlchemy request scope) so a downstream failure rolls back the
  map consumption.
- Append `'map_consumed': True` and updated `'maps'` to the success
  response so the client can update the HUD without a refetch.

### 2.8 Duel rewards rework (`server/routes/games.py`)

Replace `_award_booster_packs` with `_award_duel_rewards(user, draws)`:

```python
def _award_duel_rewards(user, draws):
    if not user or draws <= 0:
        return {'main_booster': 0, 'side_booster': 0, 'map': 0, 'gold': 0}
    probs = settings.DUEL_REWARD_POOL_PROBABILITIES
    keys = list(probs.keys())
    weights = [probs[k] for k in keys]
    awarded = {k: 0 for k in keys}
    for _ in range(draws):
        awarded[random.choices(keys, weights=weights, k=1)[0]] += 1
    user.booster_packs       += awarded['main_booster']
    user.booster_packs_side   += awarded['side_booster']
    user.maps                 += awarded['map']
    user.gold                 += awarded['gold'] * settings.DUEL_REWARD_GOLD_AMOUNT
    return awarded
```

In `_finalize_game_over`:

```python
winner_rewards = _award_duel_rewards(winner_user, settings.DUEL_WINNER_REWARD_DRAWS)
loser_rewards  = _award_duel_rewards(loser_user,  settings.DUEL_LOSER_REWARD_DRAWS)
```

Return both old and new keys for one release to keep clients compatible:

```python
'winner_boosters': {'main': winner_rewards['main_booster'],
                    'side': winner_rewards['side_booster']},  # legacy
'loser_boosters':  {'main': loser_rewards['main_booster'],
                    'side': loser_rewards['side_booster']},   # legacy
'winner_rewards':  winner_rewards,
'loser_rewards':   loser_rewards,
```

(After clients ship, the legacy keys can be dropped in a follow-up.)

### 2.9 Registration starter values

Where new users get `booster_packs = STARTER_BOOSTER_PACKS` etc., set
`maps = STARTER_MAPS` (currently 0; the assignment is still useful so
admins can change the constant later without hunting code).

---

## 3. Client changes

### 3.1 Settings & icon constants

[nepal_kings/config/kingdom_settings.py](nepal_kings/config/kingdom_settings.py):

- Add to `KINGDOM_SKILL_ICON_PATHS`:
  - `'map_production' → 'img/kingdom/skill_icons/map_production.png'`
  - `'atlas'          → 'img/kingdom/skill_icons/atlas.png'`
- Add `KINGDOM_PRODUCTION_MAP_LABEL = 'Maps'` (parallel to existing booster
  labels) if such constants exist.

[nepal_kings/config/game_menu_settings.py](nepal_kings/config/game_menu_settings.py)
(or whichever file holds the booster icon constant — verify with grep):

- Add `GAME_MENU_MAP_ICON_PATH = 'img/dialogue_box/icons/map.png'`.

### 3.2 HUD top-left ([nepal_kings/game/screens/_menu_base.py](nepal_kings/game/screens/_menu_base.py))

In `_init_menu_chrome` / `_load_chrome_cache`, load the map icon (scaled to
`GAME_MENU_GOLD_ICON_SZ`) and store it as `self._map_icon`.

In `_draw_gold`, append a 4th tuple to `items`:

```python
items = [
    (self._gold_icon,         str(gold)),
    (self._booster_icon,      str(bpacks)),
    (self._booster_side_icon, str(bpacks_side)),
    (self._map_icon,          str(maps)),
]
```

`maps` comes from `ud.get('maps', 0)`. The existing layout math already
loops over `items` and computes total width / spacing dynamically, so no
extra changes needed beyond verifying the box doesn't run off-screen at
the smallest supported resolution; if it does, slightly reduce
`sep` only inside this function with a comment.

### 3.3 Kingdom Production card ([nepal_kings/game/screens/kingdom_config_screen.py](nepal_kings/game/screens/kingdom_config_screen.py))

`_draw_vault_panel(rect)` currently divides width by 3. Refactor:

- Read `production_items` from server response (already returned as an
  ordered list).
- Compute `col_w = rect.width // len(items)` so it adapts to 3 or 4 items.
- Render each item via `_draw_production_item_row(item, row)` unchanged.
  The map item uses `kind='map'`; treat it the same as `kind='booster'`
  in the rendering branch (same icon-on-top, progress bar, ready/locked
  states). Use the `atlas` skill level to drive the capacity number, but
  the server already populates `capacity` so no client lookup is needed.

The "Collect" button already aggregates all collectable items — no change
needed; just include `collected_maps` in the floating-text feedback.

### 3.4 Kingdom skills list

The skills list is rendered from `KINGDOM_SKILL_DEFINITIONS` returned by
the server. Adding the two new entries server-side automatically renders
them client-side, provided their icon paths exist in
`KINGDOM_SKILL_ICON_PATHS`.

### 3.5 Conquer cooldown UI

Locate the conquer-confirmation dialog (or land-action modal) in
`nepal_kings/game/screens/kingdom_screen.py` (or `hex_map.py`). When the
target's user-level cooldown is active and `user_dict['maps'] > 0`, add
a secondary button **"Use map (1) — bypass cooldown"** that:

1. Opens a confirmation dialogue: `f"Spend 1 map to bypass the {remaining}s cooldown and attack {land_name}?"` Yes/No.
2. On Yes, sends the existing conquer request with `use_map=True`.
3. Decrements `user_dict['maps']` from the response; spawns a
   floater-style animation if desired (parallel to gold gain).

When `user.maps == 0` or cooldown is 0, the button is hidden. Errors with
codes `no_maps` / `no_cooldown` show a brief msg via the existing
`self.show_msg(...)` pipeline.

### 3.6 Duel reward summary screen

[nepal_kings/game/screens/game_screen.py](nepal_kings/game/screens/game_screen.py)
line ~3417 currently reads `winner_boosters` / `loser_boosters`. Update
to prefer the new `winner_rewards` / `loser_rewards` keys (with fallback
to legacy keys for one release). Display all four reward types: e.g.

```
You earned:
  +2 main booster
  +1 map
  +25 gold
```

Skip zero-count entries.

---

## 4. Tests

Add focused tests; do **not** modify unrelated tests.

### Server (`tests/server/`)

- `test_kingdom_map_production.py`
  - L0 produces nothing.
  - L1 produces 1 map after 48h (use frozen `now`).
  - Halving works at L2..L5.
  - Capacity respects atlas level (e.g., atlas L2 → 3 pending max).
- `test_kingdom_atlas.py`
  - Cap formula: 1 + level.
- `test_collect_production_maps.py`
  - `collect_gold` returns `collected_maps`, transfers to `user.maps`.
- `test_conquer_map_bypass.py`
  - Bypass succeeds when on cooldown with maps>0; map decremented.
  - Rejected with `no_maps` when maps=0.
  - Rejected with `no_cooldown` when cooldown already 0.
  - Map NOT consumed when conquest fails for unrelated reasons (e.g.
    target invalid).
- `test_duel_rewards_v2.py`
  - Winner draws 3 items, loser draws 1, totals match settings.
  - Probabilities sum to 1.0.
  - Maps appear in awarded set when forced via mocked `random.choices`.
  - User totals (`gold`, `booster_packs`, `booster_packs_side`, `maps`)
    update correctly.
- Update `test_game_over_boosters.py` to also assert the new keys exist
  alongside legacy keys (don't break the legacy assertions until the
  legacy keys are removed in a later release).

### Client (`tests/client/`)

- Smoke test that `_draw_gold` accepts a `user_dict` containing `maps`
  without exception (offscreen surface).
- Smoke test that the production card renders 4 items when the server
  payload includes `kind='map'`.

---

## 5. Order of implementation

1. **DB + settings**: schema columns, settings constants, kingdom-progression
   helpers, skill defs (server compiles cleanly).
2. **Production logic**: `kingdom_service` map state + accrual + collection;
   route updates; user serialization.
3. **Server tests** for production, atlas, collection.
4. **Conquer bypass** route logic + tests.
5. **Duel rewards rework** + tests; keep legacy response keys.
6. **Client config**: icon paths, settings constants.
7. **Client HUD**: `_menu_base._draw_gold` 4th item.
8. **Client production card**: dynamic column width + map render.
9. **Client conquer dialog**: bypass button + confirmation.
10. **Client game-over screen**: prefer `winner_rewards`/`loser_rewards`.
11. **Client smoke tests**.
12. Run full test suite (`pytest`) + manual smoke (run_local.sh) covering:
    a. Register fresh user → maps=0 in HUD.
    b. Upgrade `map_production` to L1 → wait (with reduced env interval) →
       collect → maps=1 in HUD.
    c. Upgrade `atlas` → capacity number grows on production card.
    d. Conquer once → on cooldown → "Use map" button → confirm → succeeds,
       maps decremented.
    e. Win duel → reward summary shows mixed booster/map/gold drops.

---

## 6. Risks / coupling notes

- **Booster accrual refactor**: extracting a generic `_accrue_pending_item`
  helper is ideal but risks regressing booster behavior. Mitigation: keep
  the existing booster function intact and add a parallel
  `_accrue_pending_maps` for v1; refactor to a shared helper only after
  both are working and unit-tested.
- **Existing tests for old duel rewards**: `test_game_over_boosters.py`
  and `test_server_settings_v2.py` reference the legacy constants. Keep
  the legacy constants and legacy response keys; the new code path is
  additive, so old tests continue to pass.
- **Schema additions**: SQLite auto-migrates via `create_all()`; PostgreSQL
  on PythonAnywhere does not. If the deployment uses PostgreSQL, an Alembic
  migration is required. Verify with `server/database_settings.py` /
  `setup_pythonanywhere.sh` before merge; the existing booster fields'
  introduction should have set the precedent.
- **Conquer endpoint complexity**: re-ordering the validation flow to
  consume the map only after all other checks pass requires careful
  reading of the current function. Keep the diff minimal and add a
  regression test that conquering an invalid target with `use_map=True`
  does NOT decrement `user.maps`.
- **Race conditions on `User.maps`**: SQLAlchemy's session-level updates
  are safe for single-request flows; no `SELECT ... FOR UPDATE` needed
  beyond what the rest of the codebase already does.
- **Pygbag / web build**: confirm `img/dialogue_box/icons/map.png` and
  the two skill icon PNGs exist and are bundled. If they need to be
  baked into the web build, run `build_installer.sh` / `pygbag.ini`
  pipelines.
- **Memory note (`/memories/repo/conquer_*`)**: review existing notes
  about conquer flow before editing — particularly any tiny-font /
  cooldown UI quirks — to avoid reintroducing fixed bugs.

---

## 7. Out of scope (explicit non-goals)

- No shop entry for maps.
- No achievement / quest reward integration beyond duel pool.
- No leaderboard or stats panel for maps.
- No AI awareness of maps (AI never bypasses cooldown via maps).
- No retroactive grant of maps to existing users (starter=0 applies only
  to new registrations).
