# Changelog

All notable changes to this project are documented in this file.

## Unreleased — Player-experience launch prep

Focused on the things between the game and real players: a faster front
door, a first session that pays off quickly, async-play survivability,
and the operational safety net to keep early adopters.

### Added

- **First-party analytics.** Append-only `Event` table written via
  `analytics.track()` (fail-safe, rides the caller's transaction). Hooks at
  signup, login, challenge creation, game start, all game-finish paths,
  booster opens, conquer start, and onboarding reward/skip.
  `scripts/funnel_report.py` prints the new-player funnel, early retention,
  recent activity, and median duel duration. `ANALYTICS_ENABLED` flag.
- **Versioned schema migrations.** `server/migration_runner.py` records
  applied versions in a `schema_version` table and applies ordered,
  idempotent migrations at startup (the historical `ensure_*()` helpers
  become migrations 0001–0007). Halts on first failure.
- **Production data safety.** `deploy_server.sh` now snapshots the live DB
  into `backups/` before every deploy (keeps 14, aborts on backup failure);
  `scripts/restore_db_backup.sh` is a confirmed one-command rollback;
  `RESET_DATABASE.sh` refuses a production `FLASK_ENV` and requires a typed
  confirmation. Docs rewritten to "migrations, not resets."
- **Async-play email notifications.** `notification_service.py` emails
  offline players on challenge-received, your-turn (debounced per game/6h
  via `Game.turn_email_log`), and game-finished. One-click HMAC unsubscribe,
  `/auth/set_notifications` toggle, and a Settings → Preferences row. Opt-in
  by SMTP config; logs instead of sends when unconfigured. `User.notify_emails_enabled`.
- **Sound effects.** `scripts/assets/generate_sfx.py` synthesizes a 14-sound
  set (stdlib-only, ~224 KB) into `nepal_kings/sound/`. `utils/sound.py` is a
  fail-safe engine (lazy mixer, web-gesture-safe, persisted on/off
  preference) hooked into clicks, cards, boosters, builds, coins, and
  victory/defeat stingers. Sound toggle in Settings.
- **Game-length presets** in the new-game screen: Quick (7) / Standard (21) /
  Epic (35) points; default game limit decoupled from the gold stake.
- **Web-bundle optimizer** (`scripts/assets/optimize_web_pngs.py`) and build
  pipeline (`scripts/build_web.sh`): downscales + palette-quantizes a staging
  copy of the art (source untouched), cutting the browser bundle from
  ≈79 MB to ≈35 MB. `scripts/package_itch.sh` + `docs/launch/itch_page.md`
  for an itch.io HTML5 release.

### Changed

- **Conquer-first onboarding.** The new-player journey now runs
  boosters → first conquest → first duel, so players reach a real battle
  within minutes. Main menu leads with Kingdom over Duel; beginner AI duel
  shortened from 15 to 7 points; README, web `index.html`, and welcome copy
  reframed around the single-player conquest loop. `CORE_STEPS` reordered
  (display only; completion remains a set, safe for existing accounts).
- **Action-first coaching.** The menu coach now leads with the actionable
  journey right after the welcome present instead of a generic area tour;
  light orientation (rankings/home/guide) follows. Removed dead onboarding
  hint ids left from the rework.
- `deploy-web.yml` builds via `scripts/build_web.sh` and triggers on `main`.

### Fixed

- **Opponent figures vanishing.** The security-hardening pass redacted
  opponent *figure* card data, but field figures are public in Nepal Kings.
  The nulled rank/suit made `CardImg` raise at draw time, so the AI's
  duel maharaja and AI-defended-land figures silently disappeared from the
  field. Figures are now served unredacted (hands and unplayed battle
  moves/tactics stay secret).
- **Silent conquer battles.** Added SFX to the conquer battle's tactic
  actions (play/gamble/combine/dismantle/skip) and errors; the duel sound
  hooks didn't reach the conquer screen's field/rail flow.

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