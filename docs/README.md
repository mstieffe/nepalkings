# Nepal Kings Documentation

This directory contains the durable documentation for players, developers,
release maintainers, and operators. Start with the guide for your task instead
of treating implementation plans or dated deployment logs as current runtime
instructions.

## Start by audience

### Players and testers

- [Gameplay guide](gameplay.md) — mode overview, duel flow, and card vocabulary.
- [Support](../SUPPORT.md) — gameplay, account, moderation, and issue-reporting help.
- [Legal documents](legal/README.md) — Terms, Privacy, Community Guidelines, and attribution.
- [itch.io release copy](launch/itch_page.md) — maintained storefront copy.

### Developers

- [Development guide](development.md) — environment setup, local execution,
  tests, configuration, and debugging.
- [Contribution guide](../CONTRIBUTING.md) — authorized change workflow and
  review checklist.
- [Architecture](architecture.md) — client/server boundaries, data flow,
  background work, and repository layout.
- [Scripts reference](../scripts/README.md) — build, asset, backup, load, and
  diagnostic utilities.
- [AI opponent](ai_opponent.md) — deterministic AI and strategy implementation.
- [Audio generation](audio_generation.md) and [PNG pipeline](png_pipeline.md) —
  asset-maintenance workflows.
- [Database management](database_management.md) — schema changes, local SQLite,
  and production PostgreSQL boundaries.

### Release maintainers

- [Distribution](distribution.md) — browser, itch.io, and desktop packaging.
- [Deployment overview](deployment.md) — release flow and authoritative runbooks.
- [Environment matrix](environments.md) — exact local, staging, production, and
  fallback routing.
- [PythonAnywhere runbook](../deploy/pythonanywhere/README.md) — production
  infrastructure and immutable deployment order.

### Operators

- [Operations index](operations/README.md) — current runbooks and historical evidence.
- [Public-beta routine](operations/BETA_OPERATIONS.md) — daily checks, incident
  switches, moderation, and triage.
- [Off-provider backups](operations/OFFSITE_POSTGRES_BACKUPS.md) — encryption,
  verification, and recovery.
- [Production cutover log](operations/PRODUCTION_DEPLOYMENT_2026-07-19.md) —
  dated evidence from the first EU production launch.

### Planning and project history

- [Plans index](plans/README.md) — status and interpretation of design records.
- [Lean launch plan](plans/PUBLIC_LAUNCH_PRODUCTION_PLAN.md) — completed launch
  checklist plus optional post-launch backlog.
- [Changelog](../CHANGELOG.md) — notable shipped and unreleased changes.

## Sources of truth

| Question | Authoritative source |
|---|---|
| What server does a client use? | [Environment matrix](environments.md) and client configuration code |
| What is live right now? | `/healthz`, `/readyz`, then [environment matrix](environments.md) |
| How is production deployed? | [PythonAnywhere runbook](../deploy/pythonanywhere/README.md) |
| How is production operated? | [Beta operations](operations/BETA_OPERATIONS.md) |
| What are the current game rules? | In-game Guide, then [gameplay guide](gameplay.md) |
| How should schema changes ship? | [Database management](database_management.md) and `server/migration_runner.py` |
| What was originally proposed? | [Plans](plans/README.md), treated as historical unless marked active |

Runtime behavior and tests take precedence over stale prose. A plan describes
intent; it does not override shipped code or a current runbook.

## Documentation structure

```text
docs/
├── README.md              Documentation home and source-of-truth map
├── gameplay.md            Player-facing game overview
├── development.md         Local developer workflow
├── architecture.md        System and repository architecture
├── distribution.md        Browser and desktop release workflow
├── deployment.md          Deployment overview and promotion rules
├── environments.md        Current endpoint and data-isolation matrix
├── legal/                 Public legal and attribution documents
├── launch/                Storefront and release-page copy
├── operations/            Current runbooks plus dated evidence
└── plans/                 Design plans, status records, and archives
```

Specialized technical guides remain directly under `docs/` so existing links
stay stable. New documents should be placed by audience and purpose, not by the
source-code module they happen to discuss.

## Writing and maintenance rules

1. Keep the root README short and public-facing. Detailed procedures belong here.
2. Give every operational procedure one authoritative runbook; link to it
   instead of copying commands into several files.
3. Put dates in evidence logs, not in evergreen guide titles.
4. Mark plans `proposed`, `active`, `complete`, or `superseded` near the top.
5. Update documentation in the same commit as behavior, configuration, or
   deployment changes.
6. Use repository-relative Markdown links and verify them before merging.
7. Never include passwords, tokens, signing keys, complete database URLs,
   private player data, or unredacted incident logs.
8. Archive obsolete material instead of silently rewriting historical evidence.

Run `.venv/bin/python scripts/check_markdown_links.py` from the repository root
to validate local links. The same check runs in CI.

## Naming conventions

- New evergreen guides: lowercase kebab-case, for example
  `database-management.md`. Existing underscore-named guides keep their stable
  paths until a coordinated rename updates every consumer.
- Operational runbooks already referenced by automation may retain their
  existing uppercase filenames.
- Dated evidence: descriptive title plus ISO date inside the document.
- Plans: descriptive uppercase filenames under `plans/`; superseded long-form
  material belongs in `plans/archive/`.
