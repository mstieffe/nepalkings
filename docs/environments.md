# Nepal Kings Environments and Client Routing

Last verified: 2026-07-20

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
| EU production | `https://api-nepalkingz.eu.pythonanywhere.com` | Fresh, isolated `nepalkings_prod` PostgreSQL database | Web app and worker are healthy, but public routes remain in maintenance until launch gates pass |

Do not treat EU staging as production. Accounts, tokens, games, collections,
and ownership are isolated by database and signing key. A user created on one
environment does not automatically exist on another.

## Verified EU staging state

- **Credential recovery completed:** task `35390` was disabled on 2026-07-20 after the
  staging PostgreSQL URL appeared in a failed backup-command traceback.
  The first manual replacement URL was malformed and exposed its replacement
  password as part of the invalid hostname. A second manual replacement
  repeated the missing-separator error. Both were superseded by a third
  rotation applied with the no-echo URL setter. The database login, web
  readiness, clean worker start, first sweep, and exactly one staging
  leadership lock all passed before staging was returned to service. The old
  worker log containing the invalid credential was cleared. Production was
  not involved.
- Immutable server release:
  `3952bb4611cb9a708365e607f29a0e37e7e856a5`.
- PostgreSQL schema version: 17.
- Three PythonAnywhere WSGI workers.
- Always-on AI/sweeper task: `35390` (`Running` on the same immutable
  release).
- Private environment file:
  `/home/nepalkingz/.config/nepalkings/staging.env`.
- Maintenance mode: off after the deployment smoke test.
- GitHub Pages is the only allowed browser origin:
  `https://mstieffe.github.io`.
- Conquer and Defence setup responses now include their SQL-grouped Collection
  snapshot. The new client path avoids a second authenticated request and
  preflight. A 20-sample browser A/B measured the new Conquer setup request at
  92.4 ms p50, 171.4 ms p95, and 107.5 ms mean, versus 98.7/171.1/113.2 ms
  for the earlier two-request screen path.
- Final 100-active-user read gate on `3952bb4`: 1,128/1,128 HTTP `200`, zero
  errors, 185.2 ms overall p95, 185.3 ms Conquer-config p95, and 526.0 ms
  full-map p95. Sparse map serialization reduced the decoded map from
  3,341,221 to 735,722 bytes and its mean gzip wire body from 122,140 to
  61,459 bytes.
- The release-candidate soak restarted with the worker's clean
  2026-07-20 14:12:15 UTC start. Do not close the 24-hour gate before the full
  interval passes.

The detailed backup, concurrency, latency, and verification evidence is
recorded in the current checkpoint of the public-launch plan.

## Verified EU production state

- Web app ID: `56868`.
- Provider hostname:
  `https://api-nepalkingz.eu.pythonanywhere.com`.
- Immutable server release:
  `90bfa02fa5b00b5d59998bb2b558ac19201595c1`.
- Fresh PostgreSQL schema version: 17.
- Seed data: 4,800 lands and one isolated AI user; zero human users, games,
  players, collections, or kingdoms after the exact backup restore.
- Three WSGI workers observed in the provider server log.
- Private production environment and virtualenv are isolated from staging.
- Force HTTPS is enabled.
- Maintenance mode is on.
- Health, readiness, legal, exact CORS, registration, login, onboarding,
  concurrent reads, and concurrent heartbeats passed.
- Production always-on AI/sweeper task `35394` is running from the production
  release and private environment. PostgreSQL advisory leadership keeps it
  isolated from staging task `35390`.

Detailed hashes, timings, cleanup evidence, and rollback boundaries are in
[`docs/operations/PRODUCTION_DEPLOYMENT_2026-07-19.md`](operations/PRODUCTION_DEPLOYMENT_2026-07-19.md).

## What the published clients currently use

The public GitHub Pages artifact and released installers still default to:

```text
https://nepalkings.pythonanywhere.com
```

The old server contains development data and will not be migrated. The
following five locations on `develop` are now prepared with the production
URL, but those changes do not alter the already-published artifact:

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

1. [x] Create the second EU web app at the temporary production hostname
   `api-nepalkingz.eu.pythonanywhere.com`. PythonAnywhere supports additional
   paid-account apps in the form
   `something-username.eu.pythonanywhere.com`, so no purchased domain or DNS
   change is required for launch.
2. [x] Keep `nepalkingz.eu.pythonanywhere.com` as staging. Never point both web apps
   at the same private environment file or database.
3. [x] Complete the private `production.env` with a production-only signing key,
   the `nepalkings_prod` database URL, the production API URL, exact CORS
   origin, and maintenance mode enabled.
4. [ ] Confirm the paid web-worker allocation in the PythonAnywhere Account
   tab. Production currently starts three workers. Set staging to one worker
   if the account treats the configured four workers as a shared limit.
5. [x] Initialize `nepalkings_prod` as a fresh production database. Do not import
   users, games, collections, kingdoms, or ownership from the legacy
   development server.
6. [x] Take and verify a PostgreSQL backup before initialization and before
   every later production
   deployment that can mutate schema or data.
7. [x] Deploy an immutable release, install pinned dependencies, and run
   `manage.py prepare-database` against `production.env`.
8. [x] The production WSGI has web-worker background services off, and the
   second always-on allocation now runs isolated production task `35394`.
9. [x] TLS, `/healthz`, `/readyz`, legal endpoints, maintenance behavior,
   exact CORS origin, authenticated reads, concurrent reads/writes, and logs
   passed. The production Conquer mutation, cleanup, application rollback, and
   exact database restore drills also passed after the worker was created.
10. [ ] Disable production maintenance only after the worker and remaining
    smoke gates pass.

## Add polished domains later

Adding branded domains later does not require moving or recreating the
PostgreSQL databases. A future layout can be:

| Purpose | Temporary launch URL | Future custom URL |
|---|---|---|
| Web client | `https://mstieffe.github.io/nepalkings/` | `https://play.YOUR_DOMAIN/` |
| Production API | `https://api-nepalkingz.eu.pythonanywhere.com` | `https://api.YOUR_DOMAIN/` |
| Staging API | `https://nepalkingz.eu.pythonanywhere.com` | optional; keep private/technical |

Provider domains are suitable for staging, internal testing, and an invited
beta. Prefer adding the polished API domain before broadly distributing native
installers: unlike the web client, an installed build does not update its
baked-in default automatically. If the API domain changes after installers are
public, keep the old API hostname working through the supported client-upgrade
window.

For the later API-domain change:

1. Add the owned subdomain to the existing PythonAnywhere production web app
   and configure its CNAME and HTTPS certificate.
2. Change `SERVER_URL` and `SERVER_BASE_URL` in `production.env`.
3. Reload the production web app and restart its always-on worker.
4. Verify TLS, readiness, CORS, authenticated gameplay, and logs.
5. Rebuild the client with the custom production API URL.

For the later GitHub Pages domain change, configure and verify the custom
domain in the repository's Pages settings, add the required DNS records, and
re-test HTTPS and the exact API CORS origin. Keep the old URLs available during
the transition where possible.

## Promote the web client to EU production

The five client/build locations on `develop` now use
`https://api-nepalkingz.eu.pythonanywhere.com`. Do not merge or deploy that
change until the production worker and remaining gates pass. Then:

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
