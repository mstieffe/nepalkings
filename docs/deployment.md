# Deployment Overview

Nepal Kings uses a deliberately small public-beta architecture:

- GitHub Pages serves the static browser client.
- PythonAnywhere EU serves the Flask API through managed WSGI workers.
- PostgreSQL stores staging and production data in isolated databases.
- Separate always-on tasks run AI turns and stuck-game sweeps.
- A PythonAnywhere scheduled task creates daily production dumps.

This document explains the promotion workflow. The authoritative provider
commands and paths live in the
[PythonAnywhere runbook](../deploy/pythonanywhere/README.md).

## Environments

| Environment | Purpose | API |
|---|---|---|
| Local | Development with SQLite | `http://localhost:5000` |
| Staging | Integration, migration, load, and release-candidate checks | `https://nepalkingz.eu.pythonanywhere.com` |
| Production | Public-beta API with PostgreSQL | `https://api-nepalkingz.eu.pythonanywhere.com` |

Staging and production do not share a database, role, signing key, private
environment file, web app, or background worker. See
[environments.md](environments.md) for current release and routing details.

## Branch and artifact flow

- `develop` is the integration branch.
- `main` is the public release branch and GitHub Pages source.
- Server deployments use the full immutable commit SHA as their release directory.
- Production must receive the same application release that passed staging.
- Documentation-only commits after a cutover do not change the deployed
  application release metadata.

## Server promotion

The normal operator entry point is:

```bash
.venv/bin/python scripts/deploy_pythonanywhere_eu.py \
  --environment both --push --execute \
  --confirm-sha "$(git rev-parse HEAD)" \
  --allow-missing-authenticated-read
```

Omit `--execute` for a read-only plan. The authenticated-read waiver is
deliberately explicit; use private `--smoke-credentials ENV=FILE` inputs when
maintained smoke accounts are available. The automation implements the gates
below and leaves a failed staging deployment disabled or a failed production
deployment disabled/in maintenance.

### 1. Verify the candidate

- clean worktree and immutable commit;
- full local test suite;
- GitHub Python and PostgreSQL jobs;
- dependency audit and secret scan;
- relevant focused regressions and bundle budget checks.

### 2. Promote to staging

1. Stop the staging background task and disable the staging web app.
2. Create and validate a pre-deployment PostgreSQL backup.
3. Upload the immutable server release and version-matched operational helpers.
4. Install pinned server requirements and run `pip check`.
5. Update non-secret release metadata in the private staging environment.
6. Run `manage.py prepare-database` explicitly.
7. Point WSGI, the provider source directory, and the worker command at the same SHA.
8. Start the worker, enable/reload the app, and verify one advisory leadership lock.
9. Probe health, readiness, schema, legal versions, CORS, request IDs, and logs.
10. Run the account and representative gameplay smoke required by the change.

### 3. Promote to production

Repeat the same process against the production-only paths and database while
`MAINTENANCE_MODE=True`. Confirm protected routes return a retryable `503`
until startup, migration, worker, and smoke checks pass.

After verification:

1. disable maintenance;
2. enable registration if the launch window permits it;
3. reload the web app;
4. run the external contract probe;
5. recheck staging isolation;
6. remove only the known disposable smoke data;
7. record the release, schema, backups, worker state, hashes, and rollback target.

The initial production cutover evidence is retained in
[operations/PRODUCTION_DEPLOYMENT_2026-07-19.md](operations/PRODUCTION_DEPLOYMENT_2026-07-19.md).

## Browser publication

Relevant changes on `main` trigger `.github/workflows/deploy-web.yml`. The
workflow builds the optimized pygbag bundle, enforces size budgets, uploads the
Pages artifact, and deploys it.

Backend deployment does not rebuild the browser client. Pushing only to
`develop` does not update GitHub Pages. See [distribution.md](distribution.md)
for local builds, desktop artifacts, and the player-release checklist.

## Configuration and secrets

- Committed examples live under `deploy/pythonanywhere/` and `.env.example`.
- Real environment files live outside release directories with mode `600`.
- Staging and production use independent `SECRET_KEY` and `DB_URL` values.
- WSGI imports never install packages, migrate data, or start background work.
- Production refuses an implicit database URL, ephemeral signing key,
  destructive reset, or unapproved SQLite database.

Never paste credentials, complete database URLs, private player data, or
unredacted incident output into a deployment log, commit, issue, or chat.

## Verification endpoints

| Endpoint | Purpose |
|---|---|
| `/healthz` | Process, environment, API version, and release liveness |
| `/readyz` | Database connectivity and exact schema readiness |
| `/legal/versions` | Published Terms and Privacy versions and document discovery |

The production browser origin is `https://mstieffe.github.io`. CORS origins
contain a scheme and host only, never the `/nepalkings/` path.

## Rollback

Application rollback and data recovery are distinct operations.

### Application rollback

1. Enable maintenance.
2. Stop the target worker and disable the target web app.
3. Repoint WSGI, source metadata, environment release metadata, and worker to a
   known compatible immutable release.
4. Run database preparation only if required by that release's documented schema.
5. Re-enable and verify under maintenance before reopening traffic.

Do not restore a database merely because application code was rolled back.

### Data recovery

Use the validated backup and restore procedure in
[operations/OFFSITE_POSTGRES_BACKUPS.md](operations/OFFSITE_POSTGRES_BACKUPS.md).
Restore into a disposable database first when the provider incident permits it.

## Operational handoff

After every production change, hand off to
[operations/BETA_OPERATIONS.md](operations/BETA_OPERATIONS.md) with:

- live application SHA and schema;
- web app, worker, and scheduled backup state;
- pre-deployment and newest daily backup identity;
- smoke and external-probe results;
- feature-switch state;
- rollback application release and recovery archive.
