# EU Production Deployment Log — 2026-07-19

Status: **in progress; production is not public**

This is the durable execution record for creating the first fresh Nepal Kings
production environment on PythonAnywhere EU. It records decisions, commands,
checks, and rollback boundaries without storing passwords, API tokens, signing
keys, or complete database URLs.

The infrastructure runbook is
[`deploy/pythonanywhere/README.md`](../../deploy/pythonanywhere/README.md).
Client routing and the environment matrix are in
[`docs/environments.md`](../environments.md).

## Approved scope

- Keep the client on GitHub Pages for the initial launch.
- Create production at
  `https://api-nepalkingz.eu.pythonanywhere.com`.
- Keep `https://nepalkingz.eu.pythonanywhere.com` as isolated staging.
- Start `nepalkings_prod` fresh. Do not import legacy development data.
- Use immutable server release
  `949126c9db5fbea5f86d3b053831cb9210250bb3`.
- Preserve `backup/pythonanywhere-free-eu-2026-07-19` as the tested
  free-plan/SQLite fallback branch.
- Keep production in maintenance mode until database, web, worker, CORS,
  authentication, concurrency, isolation, and rollback checks pass.
- Do not change the published GitHub Pages client until production passes.

## Environment isolation contract

| Resource | Staging | Production |
|---|---|---|
| API host | `nepalkingz.eu.pythonanywhere.com` | `api-nepalkingz.eu.pythonanywhere.com` |
| PostgreSQL database | `nepalkings_staging` | `nepalkings_prod` |
| PostgreSQL role | `nepalkings_staging` | `nepalkings_prod` |
| Private environment | `~/.config/nepalkings/staging.env` | `~/.config/nepalkings/production.env` |
| Virtualenv | `~/.virtualenvs/nepalkings-staging` | `~/.virtualenvs/nepalkings-production` |
| Background worker | always-on task `35390` | always-on task `35394` |

Both environments may reference the same read-only immutable release
directory, but they must not share a database, role, signing key, environment
file, virtualenv, web app, or background-worker task.

## Evidence recorded before production creation

### Local release and repository

- Branch: `develop`
- Starting commit:
  `c7d0275cd5bda0fdfabfab4be2cfc24c346b6178`
- Worktree at start: clean
- Server archive:
  `/tmp/nepalkings-server-949126c9db5fbea5f86d3b053831cb9210250bb3.tar.gz`
- Archive SHA-256:
  `45345150b9656992889b7b80cec91fcb342ba667ead952ae621b3518c66dfca6`
- Matching immutable remote release directory: present

### PythonAnywhere EU API audit

The account initially contained exactly:

- one enabled staging web app at
  `nepalkingz.eu.pythonanywhere.com`;
- source directory
  `/home/nepalkingz/releases/949126c9db5fbea5f86d3b053831cb9210250bb3/server`;
- staging virtualenv
  `/home/nepalkingz/.virtualenvs/nepalkings-staging`;
- force HTTPS enabled;
- one running staging always-on task, ID `35390`, using `staging.env`,
  the staging virtualenv, and release `949126c9...`.

No production web app or production worker existed.

### Private production configuration audit

At the first audit:

- `~/.config/nepalkings/production.env`: not yet present;
- `~/.virtualenvs/nepalkings-production`: not yet present;
- `~/backups/postgres-production`: not yet present.

The absent production environment is a deliberate stop gate: no database
backup, migration, WSGI reload, or worker creation may run until the
production database password is supplied through hidden input and all
non-secret production values pass validation.

The password was subsequently supplied through hidden terminal input. The
deployment:

- validated it against database and role `nepalkings_prod`;
- confirmed a PostgreSQL `max_connections` value of `20`;
- generated a new 64-character production-only signing key;
- created `~/.config/nepalkings/production.env` with mode `600`;
- set `APP_ENVIRONMENT=production`;
- set both server URLs to
  `https://api-nepalkingz.eu.pythonanywhere.com`;
- allowed only `https://mstieffe.github.io` through CORS;
- set `DB_POOL_SIZE=1` and `DB_MAX_OVERFLOW=1`;
- set `MAINTENANCE_MODE=True`;
- verified the database host, external port `10371`, role, and database name;
- verified that no `CHANGE_ME` placeholder remained;
- removed the temporary password-only file.

No password, database URL, signing key, or API token was printed or recorded.

### Production virtualenv preparation

Created:

```text
/home/nepalkingz/.virtualenvs/nepalkings-production
```

Installed the exact pinned requirements from the immutable release with
Python 3.11. `pip check` reported:

```text
No broken requirements found.
```

This preparation does not connect to or modify either database.

Created `~/backups/postgres-production` with owner `nepalkingz` and mode
`700`. The verified production interpreter is Python `3.11.11`.

### Pre-initialization production backup

The production role saw zero public tables before initialization. A
custom-format backup was created and validated with `pg_restore --list`:

```text
/home/nepalkingz/backups/postgres-production/production-pre-initialization-20260719T203428Z.dump
```

- Mode: `600`
- Size: `912` bytes
- Archive entries: `0`, as expected for the empty database
- SHA-256:
  `893ba8f87e5995db5bf3e385f4622948ed2576790ed549a043f5c024f3ebdea4`

### Fresh database initialization

`manage.py prepare-database` completed against `production.env`. It created
the tables, applied migrations `0001` through `0017`, seeded the historic map,
and completed reconciliation without stale locks.

The verification inventory found 32 public tables:

- `schema_version`: one row with version `17`;
- `land`: `4800`;
- `user`, `game`, `player`, `collection_card`, `kingdom`, `land_config`,
  `figure`, and `event`: `0`;
- every other domain table: `0`.

### Production web app

Created PythonAnywhere web app ID `56868` at:

```text
https://api-nepalkingz.eu.pythonanywhere.com
```

The app was disabled immediately after creation, then configured and enabled
with:

- Python `3.11`;
- source
  `/home/nepalkingz/releases/949126c9db5fbea5f86d3b053831cb9210250bb3/server`;
- virtualenv
  `/home/nepalkingz/.virtualenvs/nepalkings-production`;
- provider WSGI
  `/var/www/api-nepalkingz_eu_pythonanywhere_com_wsgi.py`;
- WSGI project directory pinned to release `949126c9...`;
- WSGI environment file pinned to `production.env`;
- forced HTTPS;
- web-worker background services disabled.

The WSGI file passed `py_compile`. The provider API left its account-level
working directory at `/home/nepalkingz/`; this is safe because the verified
WSGI file changes to the immutable release directory before importing the
application.

The server log shows three production uWSGI workers. The error log remained
empty through startup and smoke testing.

### Maintenance-on web checks

| Check | Result |
|---|---|
| HTTP redirect | `302` to the matching HTTPS URL |
| `/healthz` | `200`; environment `production`; release `949126c9...` |
| `/readyz` | `200`; PostgreSQL; schema `17` |
| `/legal/versions` | `200`; terms/privacy version `2026-06-12` |
| Protected login while maintained | JSON `503`; `Retry-After: 300` |
| Allowed preflight | GitHub Pages origin returned the exact allow-origin |
| Untrusted preflight | no allow-origin or CORS method/header grants |

The first uncached measurements in this deployment window were approximately
`122 ms` for health, `134 ms` for readiness, and `84 ms` for legal versions.
These are observations, not a statistically meaningful latency benchmark.

### Always-on task capacity blocker

Production worker creation was attempted only after confirming there was no
existing production task. PythonAnywhere returned:

```text
403 You have reached your always on task limit.
```

The account currently exposes one running task: staging task `35390`.
Production needs a second task allocation before the worker can be created.
Do not repurpose or stop the staging worker; each environment requires its own
environment file, virtualenv, database, and leadership lock.

### Authenticated and concurrent web smoke

Maintenance was temporarily disabled and the web app reloaded. A generated
account named `prodsmoke_0719204220` was used only for this test.

- invalid login returned JSON `401`;
- allowed CORS preflight returned `200` and the exact GitHub Pages origin;
- registration, login, and onboarding state returned `200`;
- three concurrent Collection reads and three concurrent map reads all
  returned `200`;
- six concurrent heartbeat writes all returned `200`;
- Collection reads took approximately `150–503 ms`;
- heartbeat writes took approximately `109–202 ms`;
- map reads took approximately `805–1140 ms` and each transferred about
  `3,340,616` bytes.

The map result is a production-readiness performance finding: a roughly
3.34 MB response is materially expensive even when the server is healthy.
Payload reduction, conditional requests/caching, and map endpoint profiling
remain launch-plan work.

Cleanup deleted the one smoke user and its two analytics events, reset the
empty user/event sequences, and verified:

```text
users=0 events=0 games=0 collection_cards=0 kingdoms=0 lands=4800
```

Maintenance was restored, the app reloaded, and a protected login was again
verified as JSON `503` with `Retry-After: 300`.

### Staging isolation regression

- staging and production signing keys are distinct;
- complete database URLs are distinct;
- staging resolves to role/database `nepalkings_staging`;
- production resolves to role/database `nepalkings_prod`;
- staging remains out of maintenance;
- production remains in maintenance;
- both `/healthz`, `/readyz`, and `/legal/versions` checks return `200`;
- both report release `949126c9...`, while their health/readiness environment
  values correctly report `staging` and `production`.

### Client routing and staged artifact

The following release locations on `develop` now use the production API:

- `nepal_kings/main.py`;
- `nepal_kings/config/server_settings.py`;
- `run_remote.sh`;
- `build_installer.sh`;
- `.github/workflows/build.yml`.

The source picker labels the remote preset `Production (EU)`. A regression test
requires the production URL in all five files, rejects the legacy URL there,
and confirms that GitHub Pages still deploys only from `main`.

The complete test suite passed:

```text
2629 passed, 2 skipped in 206.99s
```

An optimized web staging build produced:

```text
build/web-staging/nepal_kings/build/web/nepal_kings.tar.gz
build/web-staging/nepal_kings/build/web/nepal_kings.apk
```

- tar.gz SHA-256:
  `c4ed81f05b22b66a39a2a41c1fcb2fe607d7d9700d1a491fe77604ece5e632eb`;
- APK SHA-256:
  `3c9450a15bd3664603bf78d3355ee4c575f66ecb6d404262eb04a46866e43271`;
- each archive is approximately `46 MB`;
- `gzip -t` and `unzip -tq` passed;
- both archives contain the exact production API in `assets/main.py` and
  `assets/config/server_settings.py`;
- neither packaged file contains the legacy API;
- the standard custom index and 98 native Web Audio assets are present;
- the final staged web directory is approximately `103 MB`.

The local `pygbag` process finished both archives but did not exit before its
template/index phase in the restricted execution environment. It was
terminated by exact PID after several output-free minutes; the normal
post-build custom index/audio steps were then applied and every artifact check
above passed. Require a clean build exit in CI before public deployment.

Nothing from `build/web-staging` was deployed. The existing Pages artifact
continues to use the legacy development server until an approved merge to
`main`.

### Desktop maintenance-message follow-up

Testing the new source default while production was intentionally maintained
revealed that the desktop auth wrapper printed a generic `503 Server Error`
and replaced the server's useful maintenance explanation with a network-error
message. The web client already preserved JSON error messages.

`utils/auth_service.py` now handles login and registration `503` responses
before `raise_for_status()`. It returns the safe server message plus
`reason`, `retryable`, and `Retry-After` metadata when supplied. Two regression
tests cover desktop login and registration. The focused auth/login suite
passed eight tests, and a live non-mutating desktop login probe returned:

```text
Nepal Kings is temporarily unavailable for maintenance.
reason=maintenance retryable=True retry_after=300
```

### Staging PostgreSQL message-polling fix

The first complete Conquer tutorial against PostgreSQL staging succeeded, but
the desktop log showed repeated `400` responses from:

```text
/msg/get_log_entries?game_id=3
/msg/get_chat_messages?game_id=3
```

The staging traceback showed that both routes passed query-string game ID
`"3"` into the shared membership query as text. SQLite had accepted the
resulting integer-to-text comparison during local development, while
PostgreSQL rejected it with `operator does not exist: integer = character
varying`.

Commit `90bfa02fa5b00b5d59998bb2b558ac19201595c1`:

- converts both message route query parameters to integers;
- normalizes and validates game IDs again at the shared authorization
  boundary;
- adds endpoint and authorization regression tests;
- logs intentional stale background-poll discards at debug instead of warning,
  because cache invalidation already guarantees redelivery of a current
  snapshot.

Verification and staging deployment evidence:

- full local suite: `2635 passed, 2 skipped`;
- pre-deploy staging PostgreSQL backup:
  `/home/nepalkingz/backups/postgres-staging/staging-pre-90bfa02-20260719T212344Z.dump`;
- backup mode/size: `600`, `211151` bytes;
- backup SHA-256:
  `33058ac97281f19fdaf662d55979264a0727e7f376513651e12833987079ee61`;
- immutable server archive SHA-256:
  `c0ff333faf517f275f1fd6f46da3b806b02807dbf19f68de6c42f1281baa660b`;
- staging WSGI, provider source directory, private `RELEASE_SHA`, and always-on
  task `35390` now point to `90bfa02...`;
- `/healthz` and `/readyz` return `200` with release `90bfa02...`,
  environment `staging`, PostgreSQL, and schema `17`;
- non-mutating authenticated checks for game `3` return `200` from both
  formerly failing message endpoints;
- the staging worker returned to `Running` on the matching release;
- the staging error log retained its pre-deploy modification time
  `2026-07-19 21:06:36 UTC`, confirming no new web exception was written by
  the deployment or live checks.

Staging rollback is isolated from production: restore the staging environment,
WSGI, provider source directory, and task `35390` to release
`949126c9db5fbea5f86d3b053831cb9210250bb3`, then restart the task and reload
only `nepalkingz.eu.pythonanywhere.com`. The verified backup is retained; this
code-only fix did not change schema version `17`, so no automatic database
restore is part of rollback.

### Production worker, rollback, mutation, and recovery gates

After the subscription was raised from one to two always-on tasks, production
was advanced to the staging-tested server release
`90bfa02fa5b00b5d59998bb2b558ac19201595c1` while maintenance remained
enabled.

Before the release switch, the deployment created and verified:

```text
/home/nepalkingz/backups/postgres-production/production-pre-90bfa02-20260719T213221Z.dump
```

- mode/size: `600`, `197936` bytes;
- SHA-256:
  `d692d3016ce4b200a780ddecc8b28011e1ada514ecf76647ac3a59f1d4337a43`.

The remote release's auth, message-route, and requirements hashes matched the
committed source. Production dependency installation remained pinned,
`pip check` passed, and `prepare-database` completed at schema `17`.
Production WSGI, provider source, private `RELEASE_SHA`, and the new worker all
point to `90bfa02...`.

Production always-on task `35394` uses only:

```text
NEPAL_KINGS_ENV_FILE=/home/nepalkingz/.config/nepalkings/production.env
AI_ENABLED=True
/home/nepalkingz/.virtualenvs/nepalkings-production/bin/python
/home/nepalkingz/releases/90bfa02.../server/manage.py run-worker
```

Provider state reached `Running`. PostgreSQL showed exactly one production
leadership lock (`classid=20044`, environment key `730732783`) owned by role
`nepalkings_prod`, alongside the independent staging lock owned by
`nepalkings_staging`. Provider server logs confirm three WSGI workers in each
web app; the configured pool size/overflow remains bounded at `1 + 1` per
process.

#### Application rollback rehearsal

With production maintained, the deployment switched WSGI, provider source,
private release metadata, and worker task `35394` from `90bfa02...` back to
schema-compatible release `949126c9...`. The rollback release returned:

- `/healthz`: `200`, environment `production`, release `949126c9...`;
- `/readyz`: `200`, PostgreSQL, schema `17`;
- protected authentication: `503`.

The same pointers were then advanced to `90bfa02...`; health, readiness, and
maintenance enforcement passed again. Staging was not reloaded or modified.
This is one completed application-rollback rehearsal independent of database
recovery.

#### Authenticated Conquer mutation smoke

Immediately before mutation, the database contained schema `17`, `4,800`
lands, one AI user, and zero humans, games, players, collection cards,
kingdoms, or events. A second exact-baseline backup was created:

```text
/home/nepalkingz/backups/postgres-production/production-pre-conquer-smoke-20260719T214323Z.dump
```

- mode/size: `600`, `198108` bytes;
- SHA-256:
  `a6c87778def031e4c2b0d97aef45ce5c01c4ff9a0825dcad32993cfb4768e8a0`.

Maintenance was briefly disabled only for the controlled smoke. The reusable
`scripts/smoke_conquer_api.py` command verified:

- registration and starter onboarding;
- the 4,800-land kingdom map and recommended tutorial land `2733`;
- Conquer configuration;
- battle creation (`game_id=1`);
- authenticated game read;
- log and chat reads, including the PostgreSQL message-ID fix.

Observed single-request times were `208.2 ms` registration, `455.2 ms` map,
`98.1 ms` Conquer config, `422.5 ms` battle creation, `86.3 ms` game read,
`49.3 ms` log read, and `103.0 ms` chat read. These are smoke observations,
not percentile benchmarks. The worker sweep saw one candidate game and no
traceback was written.

Maintenance was restored immediately after the smoke.

#### Database restore drill

Only production worker `35394` and web app `56868` were stopped. Staging
remained online and `/readyz` returned `200` throughout. The pre-smoke custom
archive was restored with `--clean`, `--if-exists`, `--exit-on-error`, and
`--single-transaction`, followed by the idempotent preparation command.

- transactional restore: less than one whole second;
- restore plus preparation: `3 seconds`;
- recovered inventory: schema `17`, `4,800` lands, one AI user, zero humans,
  games, players, collection cards, kingdoms, and events.

Production was re-enabled on `90bfa02...` with maintenance still on.
Health/readiness/legal checks passed, protected registration returned JSON
`503` with `Retry-After: 300`, and staging readiness remained green.

## Execution checklist

- [x] Confirm local branch, commit, archive hash, and clean worktree.
- [x] Audit existing EU web apps and always-on tasks.
- [x] Confirm staging web/worker paths still point only to staging resources.
- [x] Confirm production release directory exists.
- [x] Create the isolated production Python 3.11 virtualenv.
- [x] Install pinned dependencies and pass `pip check`.
- [x] Create the private production backup directory with mode `700`.
- [x] Securely create and validate `production.env`.
- [x] Query and record PostgreSQL connection capacity without exposing a
      password.
- [x] Create and validate a pre-initialization custom-format PostgreSQL backup.
- [x] Initialize the fresh database and verify schema/domain counts.
- [x] Create the production web app, keep maintenance enabled, and configure
      immutable WSGI/virtualenv paths.
- [x] Confirm provider web-worker allocation: three production and three
      staging; keep per-process PostgreSQL pools bounded.
- [x] Verify `/healthz`, `/readyz`, legal endpoints, TLS, maintenance
      behavior, and exact CORS origin.
- [x] Create exactly one production always-on worker and verify its
      environment-specific leadership.
- [x] Temporarily disable maintenance for authenticated/concurrency/Conquer
      smoke, restore the exact clean baseline, and re-enable maintenance until
      client cutover.
- [x] Verify staging remains healthy, isolated, and unchanged.
- [x] Update client/build production defaults on `develop`.
- [x] Test and inspect the built artifact; do not deploy Pages from
      `develop`.
- [ ] Require the release-candidate web build to exit cleanly in CI.
- [x] Record current identifiers, hashes, counts, results, and rollback
      command; append the production task ID when capacity is available.
- [x] Commit and push the documentation and client-routing changes to
      `develop`; do not merge them to `main` before the remaining gates pass.

## Secret-handling rules

- Never paste a password, API token, signing key, or complete `DB_URL` into
  Git, chat, shell history, logs, screenshots, or this file.
- Password entry uses `read -s`; the terminal must not echo the value.
- Private directories use mode `700`; private files use mode `600`.
- Validation output may show only the database host, port, role, database
  name, key presence/length, and placeholder status.
- The production signing key is generated independently from staging.

## Rollback boundaries during this deployment

Before public cutover, rollback means:

1. leave or return production to maintenance mode;
2. disable the production always-on task;
3. disable the production web app;
4. do not change or restore staging;
5. do not restore a database automatically when rolling application code
   back;
6. do not merge the client URL change to `main`.

The existing public client therefore continues to use its previous backend
until the explicit client-release step.

### Current pre-cutover rollback

Production is already in maintenance and the public client has not been
switched. To remove the new production web tier from service without touching
either database or staging, disable only this web app in the PythonAnywhere
Web tab, or use:

```bash
PA_TOKEN="$(<~/.nepalkings_pa_token)"
curl -fsS -X POST \
  -H "Authorization: Token ${PA_TOKEN}" \
  https://eu.pythonanywhere.com/api/v0/user/nepalkingz/webapps/api-nepalkingz.eu.pythonanywhere.com/disable/
unset PA_TOKEN
```

Do not delete web app `56868`, `production.env`, the immutable release,
`nepalkings_prod`, or its backup during an application rollback. The matching
re-enable operation is the provider `enable/` endpoint followed by `reload/`,
after revalidating the WSGI and private environment paths.

## Final evidence

Complete this section as execution proceeds.

| Gate | Result |
|---|---|
| Pre-initialization backup | passed; custom-format archive validated, SHA-256 `893ba8f...dea4` |
| Production schema/counts | passed; schema 17, 4,800 lands, zero human/domain data |
| Production web app ID/host | passed; ID `56868`, `api-nepalkingz.eu.pythonanywhere.com` |
| Web-worker allocation | passed; provider logs show three production and three staging |
| Production always-on task | passed; task `35394`, production role/environment, one advisory leadership lock |
| Health/readiness/legal/TLS | passed |
| Exact CORS preflight | passed for GitHub Pages; untrusted origin not granted |
| Authenticated smoke | passed |
| Concurrency smoke | passed for six reads and six heartbeat writes |
| Production Conquer mutation | passed through battle creation and game/message reads |
| Application rollback | passed once from `90bfa02...` to `949126c9...` and forward |
| Database restore | passed; transactional restore under 1 second, restore plus prepare 3 seconds |
| Smoke-account cleanup | passed; fresh counts and sequences restored |
| Staging isolation regression | passed |
| Staging PostgreSQL message polling | passed on release `90bfa02...`; both game `3` endpoints return `200` |
| Client artifact routing | passed in both staged archives; not deployed |
| Production maintenance final state | on and verified |
| Ten-hour worker checkpoint | passed at 2026-07-20 07:55 UTC; continuous minute sweeps, exact environment locks, no suspicious worker lines |
| First encrypted off-provider backup | passed; AES-256-GCM CMS archive decrypts to production dump SHA-256 `a6c87778...8e8a0` |
| External launch probe | passed at 2026-07-20 08:05 UTC; both environments met contract and 2-second p95 ceiling |
| Atomic Duel acceptance | passed on staging release `636364d`; two simultaneous accounts returned one game, a complete deck, and one charge each |
| 100-active-user authenticated read load | passed on staging; 1,126/1,126 HTTP 200, 18.77 requests/s, 163.2 ms overall p95 |

## Post-deployment hardening checkpoint — 2026-07-20

### Runtime soak in progress

Both always-on tasks remained `Running` on release `90bfa02...`. Production
recorded 610 sweep cycles and staging 789 at the checkpoint; the most recent
entries retained one-minute continuity. Production had three nonzero-candidate
sweeps from the controlled smoke and staging had one. Neither worker log
contained a traceback, unhandled exception, lock-loss loop, database error, or
wrong-environment marker.

PostgreSQL still reported the exact production and staging advisory leadership
locks under their corresponding roles. With `max_connections=20`, production
showed one active and four idle connections and the account showed nine total,
leaving eleven connections of headroom at the observation point.

This is evidence for an in-progress soak, not completion of the required
24-hour gate. The completion checkpoint is no earlier than approximately
2026-07-20 21:50 UTC.

### Encrypted provider-independent copy

The clean production baseline dump
`production-pre-conquer-smoke-20260719T214323Z.dump` was revalidated on
PythonAnywhere with `pg_restore --list`, downloaded to a protected temporary
file, and matched against provider SHA-256
`a6c87778def031e4c2b0d97aef45ce5c01c4ff9a0825dcad32993cfb4768e8a0`.

`scripts/encrypt_postgres_backup.py` encrypted it as CMS EnvelopedData with
AES-256-GCM, decrypted it back to a hash stream twice, wrote a mode-`600`
manifest, and removed the local plaintext. The encrypted archive is 198,820
bytes with SHA-256
`23d5ed6787756ddf9e5e3224df17ba1941348e71f37b5921efd3a05d9cd8915d`.
It is stored under ignored local path `backups/off-provider/production/`.

The procedure, key fingerprint, retention target, verification command, and
recovery steps are documented in `OFFSITE_POSTGRES_BACKUPS.md`. A second
independent encrypted copy, an independently protected recovery-key copy, and
daily automation remain required before launch.

### External contract probe

`scripts/probe_launch_endpoints.py` now validates both public environments
without game dependencies. Its first three-sample live cycle completed at
2026-07-20 08:05 UTC with no errors:

| Environment | Health p95 | Readiness p95 | Legal p95 |
|---|---:|---:|---:|
| Production | 127.5 ms | 137.4 ms | 86.7 ms |
| Staging | 83.0 ms | 131.8 ms | 96.6 ms |

Both environments returned the exact release `90bfa02...`, PostgreSQL schema
17, and valid Terms/Privacy discovery. `.github/workflows/uptime.yml` schedules
the probe every 15 minutes and retains each JSONL report for 30 days after the
workflow reaches the default branch. It does not replace centralized
exceptions, route metrics, backup-age alerts, or a public status page.

### Atomic two-account Duel acceptance — staging release `636364d`

The mutation-atomicity audit found that `/games/create_game` could commit the
game, players, deck, figures, cards, and gold in separate transactions before
marking the challenge accepted. Two WSGI workers could therefore accept one
human challenge concurrently, and a mid-build exception could leave partial
state.

Release `636364d32aa570ef093dcfa596746a75484f4e6e` now:

- takes a PostgreSQL `FOR UPDATE` lock on the challenge row, with a local mutex
  fallback for SQLite development;
- rejects non-open challenges unless they already link a canonical game;
- returns that canonical game for safe acceptance retries;
- builds the game, players, deck, Maharaja figures, dealt hands, gold changes,
  analytics event, and challenge link in one transaction;
- rolls back the whole mutation when deck construction fails.

The release passed 2,645 local tests with three environment-specific skips,
the complete GitHub Python 3.11 suite, PostgreSQL concurrency/compatibility CI,
dependency audit, and security scans.

Before the staging switch, this custom-format PostgreSQL backup passed
`pg_restore --list`:

```text
/home/nepalkingz/backups/postgres-staging/
staging-pre-636364d-20260720T105217Z.dump
```

- size/mode: 211,153 bytes; `600`;
- SHA-256:
  `5a974b0d2facd44d3b14dcfdb7ab6ed7aa030666c9387917f3b79280e598d91e`.

The immutable release archive SHA-256 was
`8f73005afb9c470352943f69d2b45ce8e7ba8e4d52fa940d12fb28c798855723`.
Remote hashes for `games.py`, `challenge_coordination.py`, `deck.py`, and
`requirements.txt` matched the Git commit. Compilation, idempotent database
preparation, and `pip check` passed before the WSGI pointer moved.

Staging health/readiness then returned release `636364d`, PostgreSQL, and
schema 17. Task `35390` stopped cleanly, restarted from the same release at
10:58:40 UTC, and reached `Running`. PostgreSQL reported the exact staging
leadership lock (`classid=20044`, environment key `1763288915`) under
`nepalkings_staging`, alongside the unchanged production lock.

The reusable `scripts/smoke_duel_concurrency.py` test created two synthetic
staging users and accepted one challenge concurrently as both accounts:

| Observation | Result |
|---|---|
| Concurrent responses | both HTTP `200`; 594.7 ms and 597.8 ms |
| Returned game IDs | both `4` |
| Retry response | HTTP `200`, canonical game `4`, 67.1 ms |
| Viewer reads | both HTTP `200` |
| Challenge row | one accepted challenge linked to game `4` |
| Game/player counts | one game; two players |
| Deck counts | 64 main cards; 40 side cards |
| Gold | both users `100 → 90`; one stake deduction each |
| Error-log regression | no traceback, database error, deadlock, or duplicate-key line |

The first harness preflight created two unused, clearly named zero-gold
synthetic accounts and stopped before challenge creation. The successful
synthetic accounts and game are intentionally retained as staging evidence;
none contains an email or real player data.

Because staging changed releases, its release-candidate 24-hour soak starts at
2026-07-20 10:58 UTC. Production remains on `90bfa02...` in maintenance and
was not reloaded or mutated.

### Authenticated 2x read-load gate

`scripts/load_authenticated_routes.py` creates one clearly named synthetic
staging account, completes only the starter Collection setup, and then gives
each virtual user an independent HTTP session. Its fixed read-only mix is:

- 45% `/collection/cards`;
- 35% `/kingdom/conquer/config`;
- 18% `/games/get_games`;
- 2% `/kingdom/map`.

The first bounded baseline used 25 active users, five-second think time, a
five-second ramp, and 30 seconds total:

| Metric | Result |
|---|---:|
| Requests/errors | 145 / 0 |
| Throughput | 4.83 requests/s |
| Overall p50/p95/p99 | 61.7 / 178.7 / 681.1 ms |
| Collection p95 | 105.5 ms |
| Conquer config p95 | 178.7 ms |
| Game-list p95 | 118.4 ms |
| 3.34 MB map p95 | 956.9 ms |

The launch-capacity run used 100 active users, five-second think time, a
ten-second ramp, and 60 seconds total. This models twice the initial target of
50 simultaneously active players without pretending all 100 click at the same
millisecond:

| Metric | Result |
|---|---:|
| Requests/errors | 1,126 / 0 |
| HTTP statuses | 1,126 × `200` |
| Throughput | 18.77 requests/s |
| Overall p50/p95/p99 | 56.0 / 163.2 / 718.5 ms |
| Collection p95 | 122.7 ms |
| Conquer config p95 | 163.2 ms |
| Game-list p95 | 118.3 ms |
| 3.34 MB map p50/p95/p99 | 718.5 / 1,264.8 / 1,608.9 ms |

The post-load error log contained no traceback, SQLAlchemy/psycopg error,
deadlock, duplicate-key, or pool error. PostgreSQL settled to one active and
five idle staging connections, both environment leadership locks remained
exact, and the worker continued its sweeps. A post-load external probe passed
both environments; staging health/readiness p95 was 106.2/106.1 ms.

This closes the 100-active-user authenticated read-capacity gate only. It does
not close the full launch load gate: Defence, Duel turns, chat/log polling,
long-running games, and mutation-heavy mixes remain. The full kingdom map also
remains an optimization target; its payload is approximately 3.34 MB even when
server queueing is healthy.

### Serialized Conquer battle mutations — staging release `df69ece`

The mutation audit found that early Conquer actions such as
`/games/advance_figure` and `/games/select_defender` read and wrote mutable
game state without acquiring the PostgreSQL per-game advisory lock used by the
newer tactic endpoints. Two WSGI workers could therefore validate against the
same turn snapshot. Release
`df69ece7bf5916d335185752afc2c33656bb2a7e` now:

- acquires the cross-worker game lock before every Conquer battle mutation
  reads game state;
- covers counter spells, advances, defender selection, Civil War selection,
  fight/fold, legacy battle moves, battle finish, and post-battle choices;
- rejects stale advance and defender-selection requests after a game is
  finished;
- includes a concurrent endpoint regression that requires exactly one of two
  different advances to commit;
- extends the authenticated Conquer smoke with an optional live advance race
  and phase-aware prelude resolution.

Verification before deployment:

- local suite: 2,655 passed, 3 environment-specific skips;
- GitHub Python 3.11 suite and dependency audit: passed;
- disposable PostgreSQL 16 compatibility/concurrency job: passed;
- security/secret scan: passed;
- immutable server artifact: 367,894 bytes, SHA-256
  `98fc28e4bd3bf87f75bfcc6986c1ef0b7709b3da880049ebc0174ee044aea226`;
- remote source hashes matched the committed `games.py`, `manage.py`, and
  `requirements.txt`;
- compilation, `prepare-database`, and `pip check` passed.

The pre-deploy custom-format backup is:

```text
/home/nepalkingz/backups/postgres-staging/
staging-pre-df69ece-20260720T113345Z.dump
```

- size/mode: 215,064 bytes; `600`;
- SHA-256:
  `39330f4461f7de4cb26e5180a9b6456beab584557c238bd73a2054af62ddc7b3`;
- `pg_restore --list`: passed.

Task `35390` stopped cleanly, then the staging WSGI, provider source
directory, private `RELEASE_SHA`, and task command moved to the same immutable
release. Health/readiness returned `df69ece`, PostgreSQL, and schema 17.
Production remained on `90bfa02...` in maintenance and was not reloaded.
The task returned to `Running`; the worker log records a clean signal-15 stop
and a clean 11:39:12 UTC start.

The first concurrency-smoke setup produced a valid battle whose Health Boost
prelude still required a target. Both attempted advances correctly returned
`400 pending_prelude_target` and no advance was committed. The harness was
then made phase-aware and the repeated live smoke:

- created synthetic user `prodsmoke_0720114043_cd5b`, game `7`, land `2337`;
- resolved Health Boost on figure `28`;
- raced two different attacker figures;
- received one `200` in 203.0 ms and one stale-turn `400` in 150.9 ms;
- persisted advancing figure `28`, advancing player `13`, and turn player
  `14`;
- persisted exactly one `advance` log and one expected `game_start` log;
- left the game open and internally consistent.

The last 300 error-log and worker-log lines contain zero traceback, deadlock,
duplicate-key, or database-error matches. Both staging and production
environment leadership locks remain present. Because the runtime release
changed, the final staging candidate's 24-hour soak begins at 2026-07-20
11:39 UTC.

A second, stricter live test raced two different endpoints on fresh game `8`:
initial advance versus `/games/conquer_withdraw`. Withdrawal acquired the
shared lock first and returned `200` with the canonical defender-win result in
400.0 ms. The queued advance then re-read the finished game and returned
`409 Game is already finished` in 342.0 ms. PostgreSQL confirms:

- state `finished`, winner player `16`, and `auto_loss_reason=withdraw`;
- cleared advancing-player and advancing-figure fields;
- exactly one withdrawal `auto_loss` log and no advance log;
- exactly one `land_attack_log` result, `defender_won`, for the synthetic
  attacker and land;
- exact leadership-lock owners:
  `nepalkings_staging/1763288915` and
  `nepalkings_prod/730732783`;
- zero suspicious matches in the post-race error and worker log windows.
