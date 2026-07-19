# Nepal Kings Environments and Client Routing

Last verified: 2026-07-19

This is the authoritative guide for deciding which backend a Nepal Kings
client uses. The PythonAnywhere infrastructure runbook is
[`deploy/pythonanywhere/README.md`](../deploy/pythonanywhere/README.md), and the
full launch gate is
[`docs/plans/PUBLIC_LAUNCH_PRODUCTION_PLAN.md`](plans/PUBLIC_LAUNCH_PRODUCTION_PLAN.md).

## Current environment matrix

| Environment | API URL | Data | Current role |
|---|---|---|---|
| Local development | `http://localhost:5000` | Local development database | Developer-only |
| Legacy development server | `https://nepalkings.pythonanywhere.com` | Disposable development data | Current default for the published web client and installers; not production data |
| EU staging | `https://nepalkingz.eu.pythonanywhere.com` | Isolated `nepalkings_staging` PostgreSQL database | Integration, performance, schema/restore, and soak testing |
| EU production | Final custom API domain not selected | Fresh, isolated `nepalkings_prod` PostgreSQL database | Database exists; web app and worker are not configured yet |

Do not treat EU staging as production. Accounts, tokens, games, collections,
and ownership are isolated by database and signing key. A user created on one
environment does not automatically exist on another.

## Verified EU staging state

- Immutable server release:
  `949126c9db5fbea5f86d3b053831cb9210250bb3`.
- PostgreSQL schema version: 17.
- Three PythonAnywhere WSGI workers.
- Always-on AI/sweeper task: `35390`.
- Private environment file:
  `/home/nepalkingz/.config/nepalkings/staging.env`.
- Maintenance mode: off after the deployment smoke test.
- GitHub Pages is the only allowed browser origin:
  `https://mstieffe.github.io`.

The detailed backup, concurrency, latency, and verification evidence is
recorded in the current checkpoint of the public-launch plan.

## What the published clients currently use

The public GitHub Pages artifact and released installers still default to:

```text
https://nepalkings.pythonanywhere.com
```

This remains unchanged only until EU production exists. The old server contains
development data and will not be migrated. The default is currently baked into:

- `nepal_kings/main.py`;
- `nepal_kings/config/server_settings.py`;
- `run_remote.sh`;
- `build_installer.sh`;
- `.github/workflows/build.yml`.

The GitHub Pages workflow builds from `main`. Pushing server work to `develop`
does not update the browser client, and deploying a backend does not rebuild
GitHub Pages.

## Use EU staging now

### Browser

Use the existing query-string override:

```text
https://mstieffe.github.io/nepalkings/?server_url=https%3A%2F%2Fnepalkingz.eu.pythonanywhere.com
```

The override applies before the game imports its API settings. Log in with a
staging account; legacy development accounts are intentionally not present.

The published default remains unchanged, so opening the normal URL without the
query string still uses the legacy development server.

### Source checkout or desktop client

```bash
cd nepal_kings
python main.py \
  --server-url https://nepalkingz.eu.pythonanywhere.com
```

The desktop client saves that choice in
`~/.nepalkings/resolution.json`. To switch back to the current legacy
development server:

```bash
python main.py \
  --server-url https://nepalkings.pythonanywhere.com
```

The desktop URL precedence is:

1. `--server-url`;
2. `SERVER_URL`;
3. `~/.nepalkings/resolution.json`;
4. the baked-in default.

### Local development

Use `./run_local.sh`. It starts the local Flask server and explicitly sends the
client to `http://localhost:5000`.

## Server deployment boundaries

The paid EU PostgreSQL deployment uses immutable release directories,
pre-deployment PostgreSQL backups, explicit `manage.py prepare-database`,
provider WSGI configuration, and one always-on worker per environment.

Do not use `deploy_server.sh` for the paid EU staging or production layout. It
is the legacy mutable-directory/SQLite deploy helper and defaults to the old US
account. The matching legacy state remains available on
`backup/pythonanywhere-free-eu-2026-07-19`.

Until the paid deployment is automated, follow the deploy order in
`deploy/pythonanywhere/README.md` and record the immutable release SHA,
validated backup, web app, worker task, health/readiness result, and live smoke
result in the launch plan.

## EU production creation and cutover

Do not update the public client's default server until every item below passes.

1. Select the canonical production API domain, for example
   `api.nepalkings.com`.
2. Point its DNS at PythonAnywhere and create the second EU web app.
3. Complete the private `production.env` with a production-only signing key,
   the `nepalkings_prod` database URL, the production API URL, exact CORS
   origin, and maintenance mode enabled.
4. Allocate the four paid web workers deliberately. The launch target is three
   production workers and one staging worker; staging temporarily uses three
   only for concurrency testing.
5. Initialize `nepalkings_prod` as a fresh production database. Do not import
   users, games, collections, kingdoms, or ownership from the legacy
   development server.
6. Take and verify a PostgreSQL backup before every later production
   deployment that can mutate schema or data.
7. Deploy an immutable release, install pinned dependencies, and run
   `manage.py prepare-database` against `production.env`.
8. Configure the production WSGI file and the second always-on task. Keep web
   workers' `AI_ENABLED` and `BACKGROUND_SERVICES_ENABLED` values false.
9. Verify the custom domain, TLS, `/healthz`, `/readyz`, legal endpoints,
   maintenance behavior, exact CORS origin, authenticated reads, concurrent
   gameplay, logs, and rollback.
10. Disable production maintenance only after the smoke gates pass.

## Promote the web client to EU production

After the production cutover passes, replace the legacy development URL with
the canonical production API URL in the five client/build locations listed
above.
Then:

1. Run client tests and build the optimized web archive.
2. Inspect `assets/main.py` inside the built archive and confirm the exact
   production API URL.
3. Merge the approved client release to `main`.
4. Wait for the `Deploy Web Client` workflow to deploy GitHub Pages.
5. Download the deployed `nepal_kings.apk` and verify its baked-in URL.
6. Test login, Collection, Conquer config, map, one Duel, and one Conquer from
   the normal Pages URL without a query override.
7. Watch production access/error logs and the external health monitor.

Changing only the backend does not redirect clients. Changing only
`production.env` also does not redirect clients. The public cutover happens
when the released client artifact is rebuilt with the production API URL.

## Rollback boundaries

- Client rollback: redeploy the last known-good GitHub Pages artifact or revert
  the client URL commit.
- Application rollback: point WSGI and the environment worker at the last
  schema-compatible immutable release.
- Database recovery: follow the restore runbook; never combine it
  automatically with an application rollback.
- Emergency free-plan fallback: use the preserved branch and its matching
  SQLite snapshot. PostgreSQL data is not directly interchangeable with it.
