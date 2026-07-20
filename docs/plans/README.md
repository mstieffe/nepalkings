# Plans and Design Records

Files in this directory capture design intent, implementation sequencing, and
review notes. They are not automatically current specifications. Shipped code,
tests, the in-game Guide, and evergreen documentation take precedence.

## Current project plan

- [Public-beta launch plan](PUBLIC_LAUNCH_PRODUCTION_PLAN.md) — launch is
  complete; the final section is the optional post-launch backlog.
- [Archived exhaustive launch plan](archive/PUBLIC_LAUNCH_PRODUCTION_PLAN_FULL_2026-07-20.md)
  — preserved for context, not an active checklist.

## Feature design records

### AI and Duels

- [AI strategy upgrade](AI_STRATEGY_IMPLEMENTATION_PLAN.md)
- [Spell implementation plan](SPELL_IMPLEMENTATION_PLAN.md)
- [Spell implementation summary](SPELL_IMPLEMENTATION_SUMMARY.md)

### Conquest and battle flow

- [Invader Swap prelude](CONQUER_INVADER_SWAP_PRELUDE_PLAN.md)
- [Conquer redesign polish](CONQUER_REDESIGN_POLISH_PLAN.md)
- [Unified battle redesign status](CONQUER_UNIFIED_BATTLE_REDESIGN_STATUS.md)

### Kingdom and progression

- [Cosmetics rework](COSMETICS_REWORK_IMPLEMENTATION_PLAN.md)
- [Kingdom land display redesign](KINGDOM_LAND_DISPLAY_REDESIGN_PLAN.md)
- [Kingdom levels](KINGDOM_LEVELS_IMPLEMENTATION_PLAN.md)
- [Kingdom name, badge, and cosmetics](KINGDOM_NAME_BADGE_COSMETICS_PLAN.md)
- [Kingdom production review fixes](KINGDOM_PRODUCTION_REVIEW_FIX_PLAN.md)
- [Kingdom production skills](KINGDOM_PRODUCTION_SKILLS_IMPLEMENTATION_PLAN.md)
- [Maps feature](MAPS_FEATURE_IMPLEMENTATION_PLAN.md)
- [Version 2 implementation plan](V2_IMPLEMENTATION_PLAN.md)

## How to use a plan safely

Before executing an existing plan:

1. Check its status and last-updated date.
2. Compare every named module, endpoint, model, and command with the repository.
3. Identify which items already shipped or were superseded.
4. Replace stale assumptions rather than appending contradictory instructions.
5. Add a concise status line: `proposed`, `active`, `complete`, or `superseded`.
6. Move long obsolete plans to `archive/` while keeping links from this index.

No plan is active merely because its file exists. New work should have one
primary plan, explicit acceptance criteria, and a clear transition to durable
documentation when implementation completes.
