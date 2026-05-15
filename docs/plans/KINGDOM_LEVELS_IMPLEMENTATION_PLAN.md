# Kingdom Levels, Permanent Skills & Gold Vault — Implementation Plan

## 1. Goal

Replace the current "skill-points = land count + resettable skills" system with a
**permanent kingdom progression** driven by experience earned from conquering
**connected** land. Slim the skill roster to four core skills, add per-kingdom
**gold vaults** that must be collected manually, and add a **Core Protection**
skill that makes a sufficiently small kingdom unkillable.

## 2. Final design (decisions baked in)

### 2.1 Kingdom progression

| Aspect | Value |
|---|---|
| `KINGDOM_LEVEL_MAX` | **50** (configurable in server settings) |
| Starting level / SP | Level 1 with 3 SP and 0 XP on kingdom creation |
| `KINGDOM_SKILL_POINTS_PER_LEVEL` | 3 (configurable) |
| Total SP at max | 150 |
| Tier XP | `KINGDOM_TIER_XP = {1: 1, 2: 2, 3: 4, 4: 8}` |
| Level XP curve | `kingdom_xp_required_for_level(L) = round(KINGDOM_LEVEL_XP_BASE * KINGDOM_LEVEL_XP_GROWTH ** (L - 1))` with `BASE=5`, `GROWTH=1.5` |
| `experience` semantics | **Cumulative total XP**; `level` is recomputed from total on every write |
| Skills on land loss | **Persistent.** Level / XP / SP allocations never decrease. |
| Skill reset | **Removed.** Endpoint deleted. |

### 2.2 Skill roster (final, all others removed)

| skill_key | Display name | Max level (cfg) | SP cost curve | Effect per level |
|---|---|---|---|---|
| `gold_production` | Gold Production | 5 | 1·{1,2,4,8,16} | +3% / +6% / +10% / +15% / +22% gold rate |
| `gold_vault` | Gold Vault | 5 | 1·{1,2,4,8,16} | cap 100 / 250 / 500 / 1000 / 2000 |
| `shield_cost_reduction` | Shield Economy | 5 | 2·{1,2,4,8,16} = {2,4,8,16,32} | -5% / -10% / -16% / -23% / -32% shield cost |
| `core_protection` | Core Protection | 5 | 3·{1,2,4,8,16} = {3,6,12,24,48} | protect 1 / 2 / 3 / 4 / 5 lands |

- Default vault cap when skill at level 0: **50 gold** (configurable).
- Vault overflow: production simply **stops accruing** when full (gold lost).
- Removed skills: `villager_power`, `military_power`, `archer_damage`, `land_suit_bonus`
  — must be deleted everywhere with no dead references.

### 2.3 Skill config schema (extensible for future skills)

In `server/server_settings.py`:

```python
@dataclass(frozen=True)
class KingdomSkillDef:
    key: str
    name: str
    description: str
    max_level: int
    cost_multiplier: int        # multiplied against KINGDOM_SKILL_BASE_COST_CURVE
    effect_values: tuple[float, ...]  # length must equal max_level
    icon_path: str

KINGDOM_SKILL_BASE_COST_CURVE = (1, 2, 4, 8, 16)   # cost to BUY level 1..5

KINGDOM_SKILL_DEFINITIONS: tuple[KingdomSkillDef, ...] = (
    KingdomSkillDef("gold_production",        ...),
    KingdomSkillDef("gold_vault",             ...),
    KingdomSkillDef("shield_cost_reduction",  ...),
    KingdomSkillDef("core_protection",        ...),
)
```

Helpers:
- `skill_cost_to_buy_level(skill_key, target_level) -> int` returns `cost_multiplier *
  BASE_CURVE[target_level - 1]`, with bounds checks.
- `skill_total_cost_for_level(skill_key, level) -> int` returns the cumulative SP
  spent to reach `level`.
- `skill_effect_at_level(skill_key, level) -> float | int`.
- All UI/server code must consume these helpers; **no skill-specific branches outside
  the definition table** (so new skills only need a new `KingdomSkillDef` row).

### 2.4 Gold vault & manual collection

| Aspect | Value |
|---|---|
| Storage | `Kingdom.pending_gold` (Float) + `Kingdom.last_gold_collection_at` (DateTime, nullable) |
| Production scope | Per kingdom — sums `effective_gold_rate_for_lands(kingdom.lands)` (existing helper) |
| Accrual | On read: `pending = min(prev_pending + rate * elapsed_h, vault_cap)`; **does not** mutate DB. Only collection mutates. |
| Vault cap | `gold_vault` effect at current skill level, default 50 if level 0 |
| Cap reached | Production effectively stops (clamped at cap on read) |
| Collection endpoint | `POST /kingdom/<kingdom_id>/collect_gold` — atomically clamps pending, transfers to `User.gold`, sets `pending_gold=0`, updates `last_gold_collection_at`, returns `{collected, vault_cap, pending_gold: 0, user_gold}` |
| Collect-all endpoint | `POST /kingdom/collect_gold_all` — loops user's kingdoms, returns per-kingdom + total |
| Old endpoint | `POST /kingdom/collect_gold` (global) — **removed**; `User.last_gold_collection` field removed |

### 2.5 Core Protection semantics

- Threshold-only: when `core_protection.level >= 1` and `connected_land_count(kingdom)
  <= core_protection.level`, **all** of that kingdom's lands are unconquerable.
- Coexists with normal `shield_until` (either blocks).
- Implemented inside `kingdom_shield_block_reason(land)` so all conquer-block paths
  pick it up automatically.

### 2.6 Merger of two own kingdoms

Triggered by `reconcile_user_kingdoms()` after a land transfer reconnects a previously
split set:

1. Determine **bigger** (more lands; tie-break: earlier `created_at`).
2. For every land moving from smaller → bigger: call
   `award_kingdom_xp(bigger, xp_for_land(land))`. (Connector land already awarded
   separately by the conquer flow.)
3. Refund every `KingdomCosmeticUnlock` of the **smaller** kingdom: add
   `cosmetic.price_gold` back to the user's wallet, then delete the unlock row.
4. **Pending gold:** transfer `smaller.pending_gold → bigger.pending_gold`, **clamped**
   to bigger's vault cap (overflow lost — symmetric with normal vault overflow).
5. Delete smaller's `KingdomSkillAllocation` rows, `KingdomCosmeticUnlock` rows,
   and the `Kingdom` row itself.
6. Emit `kingdom_merged` notification with refund total + XP gained.

### 2.7 Removed code (must leave **no** dead references)

- `KingdomSkillAllocation` rows for: `villager_power`, `military_power`, `archer_damage`, `land_suit_bonus`
- All combat-bonus consumers in `server/routes/games.py` for those four skills
- `kingdom_total_skill_points = land_count` logic
- `downgrade_kingdom_skills_to_fit()` and every caller
- `KingdomNotification` kind `skill_downgraded`
- `POST /kingdom/config/<id>/skills/reset` route + client invocation
- `POST /kingdom/collect_gold` (global) route
- `User.last_gold_collection` column (drop in model — local DB reset handles schema)
- Client UI: reset button + handler; old global gold-collect logic if present

## 3. Server changes

### 3.1 `server/server_settings.py` — config block

Add (group together, near existing kingdom config):

```python
# --- Kingdom progression ---------------------------------------------------
KINGDOM_LEVEL_MAX = 50
KINGDOM_SKILL_POINTS_PER_LEVEL = 3
KINGDOM_LEVEL_XP_BASE = 5
KINGDOM_LEVEL_XP_GROWTH = 1.5
KINGDOM_TIER_XP = {1: 1, 2: 2, 3: 4, 4: 8}

# --- Skills ----------------------------------------------------------------
KINGDOM_SKILL_BASE_COST_CURVE = (1, 2, 4, 8, 16)
KINGDOM_SKILL_DEFINITIONS = (...)   # see 2.3
KINGDOM_VAULT_DEFAULT_CAP = 50      # cap when gold_vault skill at level 0
```

Functions to **add** in this file (or a new `server/kingdom_config.py` if it gets
too large — judgment call during impl):

- `kingdom_xp_required_for_level(level: int) -> int`
- `kingdom_total_xp_for_level(level: int) -> int` (cumulative threshold to reach `level`)
- `kingdom_level_for_total_xp(total_xp: int) -> int` (capped at `KINGDOM_LEVEL_MAX`)
- `xp_for_land_tier(tier: int) -> int`
- `skill_definition(key: str) -> KingdomSkillDef`
- `skill_cost_to_buy_level(key: str, target_level: int) -> int`
- `skill_effect_at_level(key: str, level: int) -> Any`
- `vault_cap_for_skill_level(level: int) -> int` (returns `KINGDOM_VAULT_DEFAULT_CAP` for level 0, else effect value)

### 3.2 `server/models.py`

`Kingdom`: add columns
```python
level                    = Column(Integer, nullable=False, default=1, server_default="1")
experience               = Column(Integer, nullable=False, default=0, server_default="0")
skill_points_granted     = Column(Integer, nullable=False, default=KINGDOM_SKILL_POINTS_PER_LEVEL, server_default=str(KINGDOM_SKILL_POINTS_PER_LEVEL))
pending_gold             = Column(Float,   nullable=False, default=0.0, server_default="0")
last_gold_collection_at  = Column(DateTime, nullable=True)
```

`User`: **remove** `last_gold_collection` (no longer used). Keep `gold` (still the
single wallet players spend from).

### 3.3 `server/kingdom_service.py`

**Helpers (new):**
- `award_kingdom_xp(kingdom, amount: int) -> dict` — adds to `experience`, recomputes
  `level` via `kingdom_level_for_total_xp`, advances `skill_points_granted = level *
  KINGDOM_SKILL_POINTS_PER_LEVEL`, emits `kingdom_xp_gained` and `kingdom_level_up`
  notifications. Returns `{old_level, new_level, xp_gained, total_xp, sp_granted_total}`.
- `kingdom_total_skill_points(kingdom) -> int` → `kingdom.skill_points_granted`.
- `kingdom_spent_skill_points(kingdom_id) -> int` (already exists; ensure it sums
  using `skill_cost_to_buy_level`).
- `kingdom_available_skill_points(kingdom) -> int`.
- `kingdom_vault_cap(kingdom) -> int` → uses `gold_vault` allocation level.
- `kingdom_vault_state(kingdom, now=None) -> dict` →
  `{pending_gold, vault_cap, vault_full, rate_per_hour, last_collection_at, accrued_since_last}`.
  Pure function, **no DB writes**.
- `collect_kingdom_gold(kingdom, user, now=None) -> dict` → mutates: clamps,
  transfers to `user.gold`, sets `pending_gold=0`, updates `last_gold_collection_at`.
  Returns `{collected, user_gold, vault_cap, pending_gold: 0}`.
- `kingdom_core_protection_active(kingdom) -> bool`.

**Modified:**
- `merge_kingdoms(...)` — implement per §2.6.
- `reconcile_user_kingdoms()` — call `merge_kingdoms` for merges; for splits, just
  create new Kingdom rows at level 1 / 3 SP / 0 XP / pending 0 / cap default.
  **Remove** all calls to skill downgrade.
- `kingdom_shield_block_reason(land)` — add core-protection check before/after
  shield-until check; return distinct reason code `core_protection` so client can
  show appropriate text.

**Deleted:**
- `downgrade_kingdom_skills_to_fit` (and all its tests).
- Anywhere skill levels are reduced based on land count.

### 3.4 `server/routes/kingdom.py`

**Modified:**
- Skill upgrade endpoint: cost lookup uses `skill_cost_to_buy_level`; budget uses
  `kingdom_available_skill_points`. Allow all 4 skills incl. `core_protection`,
  `gold_vault`. Reject keys not in `KINGDOM_SKILL_DEFINITIONS`.
- `POST /kingdom/config/<id>/shield/quote` and `/purchase`: use `skill_effect_at_level`.
- Map / config response payloads include:
  - `level`, `experience`, `xp_into_level`, `xp_for_next_level`,
    `skill_points_total`, `skill_points_spent`, `skill_points_available`
  - `pending_gold`, `vault_cap`, `vault_full`, `gold_rate_per_hour` (per kingdom)
  - `core_protection_active`

**Removed:**
- `POST /kingdom/config/<id>/skills/reset`
- `POST /kingdom/collect_gold` (global)

**Added:**
- `POST /kingdom/<kingdom_id>/collect_gold` → returns collection result.
- `POST /kingdom/collect_gold_all` → loops user's kingdoms; returns
  `{kingdoms: [{kingdom_id, collected, ...}], total_collected, user_gold}`.

### 3.5 `server/routes/games.py` — conquer resolution

In the post-battle "land transferred to attacker" path:

1. Set `land.owner_user_id = attacker_id`, `land.kingdom_id = None`.
2. Run `reconcile_after_land_transfer(old_owner, attacker)`.
3. Identify the kingdom that now owns this land:
   - If newly created kingdom (no prior adjacent kingdom): **no XP awarded** for
     the founding land.
   - Else (joined existing or merger): `award_kingdom_xp(kingdom, xp_for_land_tier(land.tier))`.
4. Note: merger XP for absorbed lands is awarded **inside** `merge_kingdoms`; the
   conquer flow only awards XP for the freshly conquered land.
5. Persist & emit notifications.

**Remove** all combat-bonus reads referencing the deleted skills (`villager_power`,
`military_power`, `archer_damage`, `land_suit_bonus`). Search the file thoroughly
and delete any captured-at-battle-start fields tied to those keys.

### 3.6 Notifications (`KingdomNotification.kind`)

Add: `kingdom_xp_gained`, `kingdom_level_up`, `kingdom_merged`.
Remove: `skill_downgraded`.

## 4. Client changes

### 4.1 Settings

`nepal_kings/config/kingdom_settings.py`
- Drop icon paths for removed skills.
- Add icon paths for `gold_vault` and `core_protection` (placeholder PNGs allowed —
  add TODO if assets missing).
- Add UI constants for: level header, XP bar (height, colours: filled / track / text),
  vault progress bar (normal / near-full / full colour), float-up animation
  (`COLLECT_FLOAT_DURATION_MS = 900`, `COLLECT_FLOAT_RISE_PX = 70`,
  `COLLECT_FLOAT_FONT_SIZE`).

### 4.2 Kingdom config screen
[nepal_kings/game/screens/kingdom_config_screen.py](nepal_kings/game/screens/kingdom_config_screen.py)

- **Header**: "Kingdom Level {N}" + XP progress bar
  `xp_into_level / xp_for_next_level`. Tooltip / sub-text: "Total XP: {experience}".
  At max level: bar full, label "MAX".
- **SP indicator**: "Skill points: {available} / {total}" (replaces "skill points = lands").
- **Skill rows**: rendered from `KINGDOM_SKILL_DEFINITIONS` order — no per-skill
  hardcoded UI. Each row shows current level / max level, current effect, next
  effect, next-level SP cost, upgrade button enabled iff affordable & not maxed.
- **Vault row** (gold_vault skill row also drives a small inline indicator): shows
  current cap.
- **Vault widget** (separate from skill row, visible at top of config screen):
  - Progress bar: `pending_gold / vault_cap`.
  - Numeric label: "Vault: 137 / 500".
  - **Collect** button (disabled when `pending_gold < 1`).
  - When `vault_full`: bar turns red AND a small "full" icon appears.
- **Core Protection row**: shows "Sanctuary active" badge when
  `core_protection_active == True`.
- **Reset button**: removed.

### 4.3 Kingdom (map) screen
[nepal_kings/game/screens/kingdom_screen.py](nepal_kings/game/screens/kingdom_screen.py)

- **Info bar** additions:
  - Aggregate per-kingdom info already exists; extend `_draw_info_bar()` with:
    - Total pending gold across all kingdoms: "Pending: 245g".
    - "Collect All" button (triggers `POST /kingdom/collect_gold_all`).
  - When **any** kingdom's vault is full: the "Gold rate" text turns **red** and
    a small full-vault icon appears next to it.
- **Hex map overlay** (optional polish, low priority): a small coin badge above
  each kingdom centroid when its vault is ≥ 80% full. Behind a feature flag /
  TODO if it complicates the first PR.

### 4.4 Gold collection animation

Add `nepal_kings/game/components/floating_text.py` (new, small, reusable):

```python
class FloatingText:
    """+amount text that rises and fades. Owns its own lifetime."""
    def __init__(self, text, start_pos, *, color, duration_ms, rise_px, font): ...
    def update(self, dt_ms) -> bool:    # returns False when finished
    def draw(self, surface): ...
```

Used by:
- Kingdom config screen: spawn at the **Collect** button position when collection
  succeeds; text = `+{collected}g`.
- Kingdom map screen: spawn at the **Collect All** button position; one floater
  per kingdom that contributed (small stagger, 80 ms apart) so multiple totals
  rise visibly. Final aggregate floater on top.
- Generalised: also reusable for future XP-gained / level-up toasts.

Animation spec:
- Linear rise of `COLLECT_FLOAT_RISE_PX` over `COLLECT_FLOAT_DURATION_MS`.
- Alpha eases from 255 → 0 with mild ease-out (`(1 - t) ** 1.4`).
- Slight horizontal jitter (±4 px) chosen at spawn for stagger flavour.
- Drawn on top of all other UI; managed by a small `FloatingTextLayer` registered
  in the screen's update/draw loop.

When level-up occurs server-side and the client sees `level` advanced, also spawn
a "Level Up!" floating text at the kingdom level header.

### 4.5 Client services

`nepal_kings/utils/kingdom_service.py` (or matching client service):
- Add `collect_gold(kingdom_id)` and `collect_gold_all()`.
- Remove old global collect call + reset-skills call.
- Parse new payload fields and update local kingdom snapshot.

### 4.6 Top-bar HUD
[nepal_kings/game/screens/_menu_base.py](nepal_kings/game/screens/_menu_base.py)
- After a successful collect, animate `User.gold` increment with the FloatingText
  (`+collected` near the gold display). Existing draw stays.

## 5. Tests

### 5.1 Server — new files

`tests/server/test_kingdom_levels.py`
- `test_xp_curve_and_level_lookup` — boundaries: total_xp=0 → lvl1; just below /
  at threshold for lvl 2, 3, 50; above max stays at 50.
- `test_conquer_awards_tier_xp_to_connected_kingdom` — tier 1→1, tier 4→8.
- `test_conquer_creating_disconnected_kingdom_no_xp_starts_lvl1_3sp`.
- `test_xp_accumulates_and_levels_up_grants_sp`.
- `test_skills_persist_when_losing_land`.
- `test_skill_reset_endpoint_returns_404`.
- `test_global_collect_gold_endpoint_removed`.

`tests/server/test_kingdom_vault.py`
- `test_vault_cap_default_when_skill_level_zero`.
- `test_vault_cap_advances_with_skill_level`.
- `test_pending_gold_accrues_until_cap_then_clamps`.
- `test_collect_endpoint_transfers_to_user_and_resets_pending`.
- `test_collect_all_endpoint_handles_multiple_kingdoms`.
- `test_collect_when_pending_zero_is_noop_or_400` (decide and assert).

`tests/server/test_kingdom_merger.py`
- `test_merger_awards_xp_for_each_absorbed_land_by_tier`.
- `test_merger_refunds_smaller_cosmetics_as_gold`.
- `test_merger_transfers_pending_gold_clamped_to_cap`.
- `test_merger_keeps_bigger_skills_and_drops_smaller`.
- `test_merger_tiebreak_uses_created_at_when_size_equal`.

`tests/server/test_core_protection.py`
- `test_core_protection_inactive_when_above_threshold`.
- `test_core_protection_blocks_conquer_at_threshold`.
- `test_core_protection_coexists_with_temp_shield`.
- `test_core_protection_status_in_payload`.

`tests/server/test_skill_config.py`
- `test_definitions_have_unique_keys_and_consistent_lengths`.
- `test_cost_helpers_use_multiplier`.
- `test_only_expected_skill_keys_present` — guard against accidental reintroduction.

### 5.2 Server — update existing

[tests/server/test_kingdom_config.py](tests/server/test_kingdom_config.py)
- Replace "skill points = land count" with "skill points = level × 3".
- Drop reset-related assertions.
- Rename split test: skills/level/XP **unchanged** on split.

[tests/server/test_connected_kingdom.py](tests/server/test_connected_kingdom.py)
- Add merger XP + cosmetic refund + pending-gold transfer assertions.

Combat tests: remove any references to deleted skill bonuses.

### 5.3 Client — update / new

[tests/client/test_kingdom_config_screen.py](tests/client/test_kingdom_config_screen.py)
- Drop reset-button tests.
- Add level header + XP bar render test.
- Add vault widget render test (empty / partial / full states).
- Add core_protection row + Sanctuary badge test.
- Add collect-button click → posts to correct endpoint.

`tests/client/test_floating_text.py` (new)
- Constructor sets initial alpha; `update(dt)` advances rise; returns False at end;
  alpha reaches 0 exactly at duration end.

`tests/client/test_kingdom_screen.py` (extend or new)
- Info bar shows total pending gold and "Collect All" button.
- Vault-full indicator (red rate text + icon) when any kingdom is full.

## 6. Migration

Local dev only — wipe DB via `server/RESET_DATABASE.sh`. No data migration code.

## 7. Implementation order (PR-sized chunks)

1. **Settings + helpers** — `KingdomSkillDef` dataclass, definitions tuple, cost /
   effect helpers, XP curve helpers. Pure-Python, fully tested via §5.1
   `test_skill_config.py` + `test_kingdom_levels.py::xp_curve_and_level_lookup`.
2. **Schema** — add Kingdom columns, drop `User.last_gold_collection`. DB reset.
3. **XP awarding on conquer** — modify `routes/games.py` post-battle path; add
   `award_kingdom_xp`. Tests: `test_kingdom_levels` (conquer & accumulation).
4. **Permanent skills + delete dead skills** — remove reset endpoint, delete
   `downgrade_kingdom_skills_to_fit` and callers, delete combat bonus consumers
   for the four removed skills, drop the four skills from definitions. Tests
   green; assert no dead references via `grep`.
5. **Vault & collection** — `pending_gold` accrual / collect endpoints. Tests:
   `test_kingdom_vault`.
6. **Merger overhaul** — rework `merge_kingdoms` per §2.6. Tests:
   `test_kingdom_merger`.
7. **Core Protection** — implement skill, hook into shield block path. Tests:
   `test_core_protection`.
8. **Client UI: config screen** — level header, XP bar, vault widget, remove reset
   button, core_protection row, sanctuary indicator. Tests updated.
9. **Client UI: map screen** — pending-gold total, "Collect All" button,
   vault-full indicator on rate text. Tests added.
10. **Floating text animation** — `FloatingText` component + integration in
    config & map screens & top-bar gold update. Tests for component logic.
11. **Notifications** — `kingdom_xp_gained`, `kingdom_level_up`, `kingdom_merged`
    surfaces (toast/floater).

Each chunk leaves the test suite green before moving on.

## 8. Pitfalls & how we handle them

| Pitfall | Mitigation |
|---|---|
| `experience` ↔ `level` drift | Always set `level = kingdom_level_for_total_xp(experience)` inside `award_kingdom_xp`; assert in tests |
| `skill_points_granted` drift | Always `= level * KINGDOM_SKILL_POINTS_PER_LEVEL` after level update |
| Pending gold double-accrual (read-then-write race) | Server collect endpoint recomputes accrual atomically inside the request; client never sends pending value |
| Vault cap shrinks (won't happen since skills are permanent, but defensive): | If ever cap < pending, clamp on read; document invariant |
| Merger pending gold transfer overflow | Clamp to bigger's cap; loss is symmetric with normal overflow |
| Refund of merged kingdom cosmetics double-counted | Delete unlock rows in same transaction as gold credit |
| Floating-text leak (animations not freed) | Store in a layer list, drop when `update()` returns False |
| New skills introduced later requiring per-skill code | Avoid by routing all skill logic through `KINGDOM_SKILL_DEFINITIONS` + helpers; tests assert no per-key branching outside definitions |
| Core Protection on disconnected mini-kingdom (1 land + level ≥ 1) makes a player unkillable forever | Intended; cost is lack of growth and SP allocation. Document in skill description. |
| Removed skill rows lingering in DB after settings change | Local dev: DB reset. Add a startup sanity log: warn if any allocation has unknown `skill_key`. |

## 9. Out of scope

- Cross-kingdom skill sharing.
- Prestige / rebirth at level 50.
- Cosmetic rewards tied to level milestones.
- Background gold accrual jobs (we stay on-demand).
- Production migration (handled by reset for now).
