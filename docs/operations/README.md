# Operations Documentation

Use this directory for current production procedures and dated operational
evidence. Current runbooks tell an operator what to do now; dated logs preserve
what happened during a particular deployment or incident.

## Current runbooks

- [Public-beta operations](BETA_OPERATIONS.md) — daily checks, incident
  switches, moderation, and triage.
- [Off-provider PostgreSQL backups](OFFSITE_POSTGRES_BACKUPS.md) — encryption,
  replication expectations, restore verification, and recovery.
- [PythonAnywhere deployment](../../deploy/pythonanywhere/README.md) — provider
  layout, immutable releases, workers, and deployment order.
- [Deployment overview](../deployment.md) — promotion and rollback model.
- [Environment matrix](../environments.md) — current endpoints, releases, and
  isolation boundaries.

## Dated evidence

- [EU production deployment log — 2026-07-19](PRODUCTION_DEPLOYMENT_2026-07-19.md)
  records the initial PostgreSQL production creation, hardening, rehearsals,
  and public-beta cutover.

Dated evidence is append-only historical context. When it conflicts with a
current runbook or a live readiness response, use the current runbook and live
state, then document the discrepancy.

## Operational documentation rules

- Never store credentials, full database URLs, signing keys, API tokens, or
  private player data.
- Record timestamps in UTC and identify the environment explicitly.
- Record immutable release SHAs, schema versions, artifact and backup hashes,
  worker/task IDs, and rollback targets.
- Keep application rollback separate from data restoration.
- Update the relevant runbook whenever a deployment changes operator behavior.
- Preserve failed checks and their resolution; do not rewrite evidence to look cleaner.
