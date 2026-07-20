# Nepal Kings Public Launch and Production Readiness Plan

Last updated: 2026-07-20

Status: Archived exhaustive version; superseded by the lean active launch plan

Launch framing: staged public beta before a 1.0 claim

## Proportional public-beta scope

This is an indie card game, not a clinical, financial, or enterprise system.
The launch gate must be credible and safe without turning the project into an
operations platform.

Before public registration, require:

- verified backups and one successful restore/rollback path;
- PostgreSQL, multi-worker correctness, bounded load tests, and a 24-hour
  release-candidate soak;
- health/readiness checks, external probes, request IDs, useful redacted logs,
  and a human-readable incident runbook;
- password change/session revocation, account export/deletion, basic
  report/block/suspend controls, and registration/chat/game kill switches;
- representative Duel, Conquer, Defence, browser, mobile, and release-build
  smoke tests;
- truthful legal/operator/contact text and a monitored support channel;
- no known critical/high security or economy-corruption defect.

Do not block the initial beta on enterprise-grade dashboards, PITR, Redis,
WebSockets, a custom admin frontend, complete device-lab coverage, formal
property testing, service workers/offline mode, or a second hosting bake-off.
Those remain follow-up work unless testing exposes a concrete need.

## How to use this plan

- Work from top to bottom; later phases depend on the earlier hosting,
  PostgreSQL, and concurrency work.
- Check an item only after its verification line passes.
- Record hosting and architecture decisions in the decision log at the bottom.
- Keep gameplay changes out of this plan unless they block a release gate.
- Preserve a clean release candidate: committed files, reproducible build,
  green CI, immutable commit SHA, and no production-only edits.

Priority:

- **P0**: required before opening public registration.
- **P1**: required before expanding beyond the controlled beta.
- **P2**: useful after the public beta is stable.

## Current baseline

Execution checkpoint (2026-07-20):

- The exact pre-production/free-plan state is preserved and pushed as
  `backup/pythonanywhere-free-eu-2026-07-19` at commit
  `7c85e83ca31223982fdbce0d3925247f9407a847`.
- That branch passed all 2,609 tests and was deployed/smoke-tested on the EU
  one-worker SQLite app before production work began.
- Production work stays on `develop`; the fallback branch must not receive
  PostgreSQL or multi-worker changes.
- PythonAnywhere EU is selected for the staged public beta. GitHub Pages
  remains the static client host.
- Staging runs immutable release
  `3952bb4611cb9a708365e607f29a0e37e7e856a5`; maintained production remains
  on `90bfa02fa5b00b5d59998bb2b558ac19201595c1`. Both use isolated PostgreSQL
  schema 17 databases behind three managed WSGI workers.
- Production task `35394` remains on its isolated production release.
  Staging credential recovery is closed: the third password and helper-built
  URL passed login verification, the two exposed replacements are invalid,
  and the stale logs were cleared. Task `35390` is `Running` on `3952bb4`
  with exactly one staging advisory leadership lock. The production
  credential and environment were never involved.
- The current staging candidate passed 2,682 local tests with 3
  environment-specific skips. GitHub's Python 3.11, PostgreSQL compatibility,
  dependency-audit, and secret-scan jobs also passed.
- A validated pre-deployment PostgreSQL custom-format backup is stored privately
  at
  `/home/nepalkingz/backups/postgres-staging/staging-pre-3952bb4-20260720T140826Z.dump`;
  it is mode `600`, 225,070 bytes, passed `pg_restore --list`, and has
  SHA-256
  `a5f2bf07b7f22740a3b0f8bf9030e26762400749f392cc14d6280a6eb2d5e93e`.
- Production application rollback, authenticated Conquer mutation, exact
  baseline restore, and smoke-account cleanup passed. A verified production
  dump is also encrypted off-provider with CMS AES-256-GCM; the daily schedule
  and second independent storage destination remain open.

Latest live staging evidence:

- Health and readiness return release `3952bb4`, PostgreSQL, and schema 17.
  The worker is `Running` on the same release; both isolated environment
  leadership locks remain present.
- The final 100-user run completed 1,128 authenticated reads with 1,128 HTTP
  `200` responses, zero errors, 185.2 ms overall p95, and 185.3 ms
  Conquer-config p95. Its 23 full-map reads measured 735,722 decoded bytes,
  61,459 mean gzip wire bytes, and 526.0 ms p95. This closes the map-specific
  1.5-second read gate.
- A five-sample post-load external probe passed health, readiness, legal
  discovery, release consistency, schema, and latency for both staging and
  maintained production. The web and worker logs show no post-load crash,
  traceback, or restart.
- The combined Conquer/Collection bootstrap was verified live. The new screen
  path uses one config request; a 20-sample browser A/B measured 92.4 ms p50,
  171.4 ms p95, and 107.5 ms mean versus 98.7/171.1/113.2 ms for the earlier
  two-request path. The p95 was effectively unchanged, while one request and
  its preflight were removed.
- A phase-aware Conquer smoke resolved a randomly required Health Boost
  prelude, then sent two different legal advances simultaneously through the
  three-worker deployment. One returned `200` in 203.0 ms and committed
  Djungle King; the stale request returned `400` in 150.9 ms.
- A stricter cross-endpoint race sent advance and withdrawal simultaneously.
  Withdrawal won the lock, finished game `8`, and returned the canonical
  defender-win result; the queued advance re-read the finished game and
  returned `409`. PostgreSQL contains one withdrawal result/log and no advance.
- PostgreSQL game `7` contains the one winning advancing figure and exactly
  one `advance` log. The error and worker logs contain no traceback, deadlock,
  duplicate-key, or database-error line after deployment.
- Six simultaneous withdrawals with the same `client_action_id` all returned
  `200` and the same canonical response SHA-256
  `a075b59c21dbd00560e8a4fa1291cfc1f2660059c48119f68a04c0c654d2c9c6`.
  PostgreSQL recorded one receipt, one additional attack log, and one finished
  game. No new `500` or traceback appeared in the post-deployment logs.

Already present:

- Broad server and client regression coverage.
- GitHub Pages web deployment and desktop installer workflows.
- Production secret and destructive-startup guards.
- Viewer-aware gameplay serialization and ownership checks.
- Security headers, dependency auditing, and secret scanning.
- Versioned Terms and Privacy acceptance.
- SQLite backup-before-deploy tooling and a restore script.
- Secret-safe PostgreSQL backup and worker-lock verification helpers; the
  staging credential/deployment incident is closed.
- Analytics/funnel events.
- Rule-based AI opponents.

Known launch blockers:

- The production web app at
  `api-nepalkingz.eu.pythonanywhere.com` is configured on fresh PostgreSQL and
  has passed web, worker, mutation, rollback, and restore gates, but it remains
  intentionally in maintenance until the remaining launch gates pass.
- Client defaults are prepared on `develop` but are intentionally not deployed
  from `main` until the remaining public-registration gates pass.
- EU production will intentionally start with a fresh database. Legacy US
  development users, games, collections, kingdoms, and ownership will not be
  migrated.
- Atomic two-account Duel challenge acceptance and deliberately conflicting
  Conquer advances now pass locally, in PostgreSQL CI, and against the three
  live staging workers. The staging release-candidate soak clock restarted
  with candidate `3952bb4` at 2026-07-20 14:12:15 UTC; the longer
  production infrastructure soak continues on `90bfa02`.
- Job failure history/attempt limits and the remaining mutation-atomicity audit
  are incomplete.
- Map responses are now sparse and omit client-default/internal configuration
  fields. The decoded payload is 735,722 bytes and provider-gzip wire body is
  about 61 KB; the 100-active-user run measured 526.0 ms map p95. Versioned
  caching remains useful, but map construction/serialization is no longer a
  blocker for the current read gate.
- The SQL-grouped Collection snapshot in Conquer and Defence config is live.
  Updated clients use one initial config request instead of a second
  `/collection/cards` request; desktop retains an old-server fallback. The
  browser A/B and two zero-error 100-user runs verified the combined endpoint.
- A standard-library external contract/latency probe and scheduled GitHub
  workflow now exist on `develop`, and the first live cycle passed. The
  schedule becomes active from the default branch; centralized application
  metrics, exception reporting, backup-age alerts, and a status page are still
  deferred for the initial beta.
- Password change, token-version session revocation, log-out-all,
  deletion/anonymization, JSON export, reporting, blocking, audited operator
  moderation, and narrow incident switches are implemented locally with
  focused regression coverage. They remain uncredited until the candidate is
  migrated and exercised on staging.
- Legal retention and account-behavior text now matches the implementation.
  Real operator/contact details and visual-art provenance still require the
  operator's truthful input; they cannot be inferred from source code.
- The staged browser and Android archives are approximately 46 MiB. CI now
  reports their largest files and enforces a pragmatic 52 MiB compressed
  archive ceiling plus a 15 MiB external-audio ceiling.
- CI still does not run gameplay load tests. Those remain explicit,
  operator-triggered staging gates because running them on every commit would
  spend provider capacity without improving beta safety.

## Release contract

The initial planning target is:

- 300 registered users.
- 50 simultaneously active players.
- Load test at 100 active players for 2x headroom.
- EU end-to-end API latency below 800 ms p95.
- Conquer and defence configuration ready below 1.5 seconds p95 on a warm
  client.
- API 5xx responses below 0.5%.
- Public-beta uptime target of 99.5%.
- Recovery point below 26 hours for the initial beta's verified daily-dump
  policy. Revisit PITR if player activity makes that loss window unacceptable.
- Recovery time below two hours.
- Provider and GitHub Pages domains for the initial beta; polished custom
  domains can be added later without moving the database.

Revisit region choice if the first audience is primarily Nepal/South Asia. A
single write region remains the launch architecture; active-active multi-region
state is out of scope.

---

## Gate H0 — Choose the hosting platform

Decision status: **Complete — PythonAnywhere EU selected**

Current candidates:

1. Render Frankfurt with managed PostgreSQL.
2. PythonAnywhere EU with its PostgreSQL add-on.
3. Railway Amsterdam.
4. DigitalOcean App Platform Frankfurt.
5. Hetzner Germany only if self-managed operations are explicitly accepted.

Selected layout:

- Keep the static client on GitHub Pages.
- Run staging and production APIs on the upgraded PythonAnywhere EU account.
- Use the PythonAnywhere PostgreSQL add-on with separate staging and production
  databases/users.
- Use managed WSGI web workers plus a dedicated always-on task when the durable
  job queue is ready.
- Keep Render Frankfurt as the documented exit option if PostgreSQL, worker,
  backup, or support testing fails a release gate.

### H0.1 What the free PythonAnywhere EU test can prove

It can measure:

- Europe-to-EU ingress and TLS latency.
- Cold and reused-connection API latency.
- PythonAnywhere EU routing stability.
- Browser CORS/preflight cost.
- The same Flask route's external time versus access-log `response-time`.

It cannot determine:

- Three-worker paid-plan throughput; free accounts have one worker.
- PostgreSQL add-on performance.
- Always-on background-task behavior.
- Multi-worker gameplay correctness.
- Final paid-plan reliability or support.
- Real capacity under concurrent public traffic.

Therefore, use the free account to decide whether PythonAnywhere EU fixes the
regional latency problem. Make capacity and database decisions separately.

### H0.2 Deploy the server-only subset to the EU account

Do not clone the whole repository into the free account. The repository's
`.git` directory is larger than the free account quota, while the deployable
server subset is only a few MiB.

Two unrelated secrets are used during this test:

- **PythonAnywhere API token:** authorizes the local deploy script to upload
  files and reload the EU web app. Store it only on the local Mac in
  `~/.nepalkings_eu_pa_token`. Do not put it in the repository or WSGI file.
- **Flask `SECRET_KEY`:** signs Nepal Kings login tokens inside the EU test
  server. Generate a new test-only value in a PythonAnywhere console and store
  it only in the private WSGI configuration. Do not reuse the production
  `SECRET_KEY`.

On the EU PythonAnywhere Account page:

- [x] Open the **API token** tab and create/copy an API token.
- [x] Create one manual web app:
  `EU_USERNAME.eu.pythonanywhere.com`.
- [x] Select Python 3.11 to match current server CI.

On macOS, with the EU API token still copied to the clipboard, store it outside
the repository:

```bash
umask 077
pbpaste > "$HOME/.nepalkings_eu_pa_token"
chmod 600 "$HOME/.nepalkings_eu_pa_token"
test -s "$HOME/.nepalkings_eu_pa_token" \
  && echo 'EU token file created'
```

Do not use `cat` to verify the file because that would print the secret. The
deploy script strips a trailing newline automatically. Clear or replace the
clipboard contents after saving the token.

Upload only the deployable server files:

```bash
unset PA_API_TOKEN
PA_USER='EU_USERNAME' \
PA_HOST='eu.pythonanywhere.com' \
PA_DOMAIN='EU_USERNAME.eu.pythonanywhere.com' \
PA_TOKEN_FILE="$HOME/.nepalkings_eu_pa_token" \
./deploy_server.sh --no-backup
```

On an EU PythonAnywhere Bash console:

```bash
python3.11 -m venv ~/.virtualenvs/nepalkings
~/.virtualenvs/nepalkings/bin/pip install \
  -r ~/nepalkings/server/requirements.txt
mkdir -p ~/nepalkings/server/instance
```

Configure the Web tab:

- Source code: `/home/EU_USERNAME/nepalkings/server`
- Working directory: `/home/EU_USERNAME/nepalkings`
- Virtualenv: `/home/EU_USERNAME/.virtualenvs/nepalkings`
- Force HTTPS: enabled

Use this private WSGI configuration, replacing the username and secret:

```python
import os
import sys

username = 'EU_USERNAME'
path = f'/home/{username}/nepalkings/server'
if path not in sys.path:
    sys.path.insert(0, path)

domain = f'{username}.eu.pythonanywhere.com'
os.environ['FLASK_ENV'] = 'production'
os.environ['SECRET_KEY'] = 'GENERATE_A_NEW_TEST_SECRET'
os.environ['DROP_TABLES_ON_STARTUP'] = 'False'
os.environ['DB_URL'] = f'sqlite:///{path}/instance/eu_latency_test.db'
os.environ['SERVER_URL'] = f'https://{domain}'
os.environ['SERVER_BASE_URL'] = f'https://{domain}'
os.environ['CORS_ORIGINS'] = 'https://mstieffe.github.io'
os.environ['AI_ENABLED'] = 'False'
os.environ['EMAIL_VERIFICATION_ENABLED'] = 'False'
os.environ['NOTIFY_EMAILS_ENABLED'] = 'False'
os.environ['DISABLE_BACKGROUND_SWEEPERS'] = '1'

from wsgi import application
```

Generate the test secret in the EU console:

```bash
python3.11 -c "import secrets; print(secrets.token_hex(32))"
```

Do not reuse the production secret or upload the production database.

Reload the web app and confirm:

```bash
curl -fsS \
  https://EU_USERNAME.eu.pythonanywhere.com/legal/versions
```

### H0.3 Phase A benchmark: ingress and tiny-route latency

Run from the same client and network that experienced the slowdown:

```bash
.venv/bin/python scripts/benchmark_api_latency.py \
  --target us=https://nepalkings.pythonanywhere.com/legal/versions \
  --target eu=https://EU_USERNAME.eu.pythonanywhere.com/legal/versions \
  --warmups 5 \
  --samples 50 \
  --csv /tmp/nepalkings-pa-us-vs-eu.csv
```

Protocol:

- [x] Warm both deployments before measuring.
- [x] Send requests sequentially; do not load-test the one-worker free account.
- [x] Alternate US and EU requests to reduce time-of-day/network bias.
- [x] Record both cold connection and persistent-session results.
- [ ] Run three rounds: morning, evening, and a second day.
- [ ] Avoid downloads, VPN changes, and other heavy network traffic.
- [x] Save the CSV files and the exact commit SHA.

For every round, also inspect both PythonAnywhere access logs. Search for the
`nk_bench` query parameter and record:

- client `time_total`
- client `time_starttransfer`
- access-log `response-time`
- HTTP status

Approximate transit/platform overhead:

```text
external total time - access-log response-time
```

This separates route work from network/ingress cost.

### H0.4 Phase B benchmark: real browser CORS behavior

Open the deployed GitHub Pages game, then open the browser DevTools console.
The EU WSGI `CORS_ORIGINS` must include `https://mstieffe.github.io`.

Run:

```javascript
async function nkBench(targets, count = 30, withAuthHeader = false) {
  const rows = [];
  for (let i = 0; i < count; i++) {
    const names = i % 2 ? Object.keys(targets).reverse() : Object.keys(targets);
    for (const name of names) {
      const url = `${targets[name]}?nk_browser_bench=${name}-${i}-${Date.now()}`;
      const options = {
        cache: "no-store",
        headers: withAuthHeader ? {Authorization: "Bearer benchmark-invalid"} : {}
      };
      const start = performance.now();
      const response = await fetch(url, options);
      await response.text();
      rows.push({name, ms: performance.now() - start, status: response.status});
    }
  }
  for (const name of Object.keys(targets)) {
    const values = rows.filter(r => r.name === name && r.status < 400)
      .map(r => r.ms).sort((a, b) => a - b);
    const pick = p => values[Math.max(0, Math.ceil(values.length * p) - 1)];
    console.log(name, {
      count: values.length,
      p50: pick(0.50),
      p95: pick(0.95),
      min: values[0],
      max: values[values.length - 1]
    });
  }
  return rows;
}

const nkTargets = {
  us: "https://nepalkings.pythonanywhere.com/legal/versions",
  eu: "https://EU_USERNAME.eu.pythonanywhere.com/legal/versions"
};

await nkBench(nkTargets, 30, false);
await nkBench(nkTargets, 30, true);
```

The second pass deliberately supplies an `Authorization` header. That triggers
the kind of CORS preflight used by authenticated game requests without needing
a valid production token.

### H0.5 Phase C benchmark: representative game paths

After the ingress test:

- [x] Create synthetic test users on the EU deployment.
- [x] Do not copy production users or production PII.
- [x] Complete enough onboarding to open Collection and Conquer config.
- [x] Measure `/collection/cards`.
- [x] Measure `/kingdom/conquer/config`.
- [x] Measure kingdom map loading.
- [ ] Measure one complete duel polling cycle.
- [x] Record browser requests, preflights, payload sizes, and combined
  Conquer API-pair time from the real GitHub Pages origin.
- [x] Compare route access-log response times with browser duration.
- [ ] Record full game screen-ready time including client parsing/rendering.

For an authenticated automated comparison, use synthetic databases with the
same test-only `SECRET_KEY`, equivalent test rows, and a shared bearer token.
Never share the production secret with a staging account.

### H0.6 Hosting decision criteria

PythonAnywhere EU passes the latency gate if:

- [x] Warm p95 is below 800 ms from the primary audience location.
- [x] Tiny-route EU p95 is at least 40% lower than the US result.
- [x] Conquer config screen-ready p95 is below 1.5 seconds after request
  consolidation, or the raw regional result demonstrates that target is
  credible.
- [x] p95 is stable and is not dominated by multi-second outliers in the first
  50-sample round.
- [x] Access-log times remain low while external times improve.

Choose PythonAnywhere EU only if:

- [x] Its paid PostgreSQL add-on price and backup behavior are acceptable for
  the initial beta.
- [x] The app can run the required dedicated background work.
- [ ] Deployment, rollback, logs, and alerting can meet the remaining gates.
- [x] Multi-worker state is fixed before enabling additional workers.

Choose Render Frankfurt if:

- [ ] It meets the same latency targets.
- [ ] Managed PostgreSQL, background workers, health checks, and rollback
  materially reduce launch risk.
- [ ] The measured configuration stays within the agreed monthly budget.

Do not use the free-plan benchmark to compare concurrent throughput.

Hosting decision output:

- [x] Selected provider and region recorded below.
- [ ] Monthly launch budget recorded.
- [x] PostgreSQL plan recorded.
- [x] Background-worker plan recorded.
- [x] Staging and production topology recorded.
- [ ] Canonical domains recorded.

### H0.7 Measured PythonAnywhere US versus EU result

Tested on 2026-07-19 from Berlin-area residential internet against Git commit
`41a19ef`. Each result contains 50 sequential, alternating requests after five
warmups. No concurrent load was sent to either account.

| Request pattern | US p50 | US p95 | EU p50 | EU p95 | EU p95 reduction |
|---|---:|---:|---:|---:|---:|
| New connection GET | 413.0 ms | 709.2 ms | 80.1 ms | 103.0 ms | 85.5% |
| Reused connection GET | 153.9 ms | 478.3 ms | 26.4 ms | 37.0 ms | 92.3% |
| CORS preflight plus authorized-style GET | 361.0 ms | 798.0 ms | 62.5 ms | 80.6 ms | 89.9% |

CORS pair components:

| Component | US p50 | US p95 | EU p50 | EU p95 |
|---|---:|---:|---:|---:|
| `OPTIONS` preflight | 162.7 ms | 585.1 ms | 31.1 ms | 44.4 ms |
| Following `GET` | 174.3 ms | 456.1 ms | 31.0 ms | 39.7 ms |

Both deployments returned the expected CORS origin and allowed the
`Authorization` header. The EU deployment also returned HSTS because Force
HTTPS is enabled there; the current US deployment did not return HSTS.

PythonAnywhere access-log `response-time` remained essentially identical:

| Server-side request | US p50 | US p95 | EU p50 | EU p95 |
|---|---:|---:|---:|---:|
| New connection GET route work | 2 ms | 6 ms | 2 ms | 3 ms |
| Reused connection GET route work | 2 ms | 3 ms | 2 ms | 2 ms |
| CORS `OPTIONS` route work | 2 ms | 3 ms | 2 ms | 3 ms |
| CORS following `GET` route work | 2 ms | 3 ms | 2 ms | 2 ms |

Conclusion: PythonAnywhere EU decisively fixes the measured regional
ingress/TLS problem. The Flask route itself is not meaningfully faster in EU;
the improvement is almost entirely outside the timed application work. This
passes the regional latency gate but does not yet prove paid-plan capacity,
PostgreSQL performance, background jobs, or representative authenticated
screen-ready time.

An authenticated headless-Chrome pass then ran from the real
`https://mstieffe.github.io` origin with a no-email synthetic EU test user.
Each result contains 10 measured loads after two warmups:

| Authenticated browser operation | Browser p50 | Browser p95 | Server p50 | Server p95 | Decompressed body |
|---|---:|---:|---:|---:|---:|
| Collection cards | 59.9 ms | 81.6 ms | 6 ms | 9 ms | 571 B |
| Conquer config | 87.5 ms | 165.9 ms | 32 ms | 38 ms | 3,412 B |
| Conquer config + Collection in parallel | 96.5 ms | 157.7 ms | 31–33 ms per GET | 42–45 ms per GET | 3,983 B |
| Kingdom map | 563.9 ms | 622.9 ms | 448 ms | 554 ms | 3,340,616 B |

The browser received compressed map responses of approximately 121,795 bytes,
but parsing produced about 3.34 MB of JSON. Unlike the tiny-route comparison,
the map's access-log time shows a real application hotspot: most of its roughly
0.6-second browser time is spent building/serializing the 4,800-land snapshot.
The Conquer screen's two API dependencies are already comfortably below the
1.5-second target on EU. Full Pygbag screen rendering still needs a separate
screen-ready measurement.

Evidence files:

- `/tmp/nepalkings-pa-us-vs-eu-20260719.csv`
- `/tmp/nepalkings-pa-cors-us-vs-eu-20260719.csv`
- `/tmp/nepalkings-eu-browser-game-routes-20260719.csv`
- PythonAnywhere access logs containing the matching `nk_bench` request IDs.

Useful follow-ups after the completed PythonAnywhere EU hosting decision:

- [ ] Repeat the benchmark in the evening and on a second day.
- [x] Run an automated real-browser benchmark from the GitHub Pages origin.
- [x] Run Phase C with a synthetic EU test user and real Conquer/Collection
  routes.
- [ ] Measure full Pygbag Conquer screen-ready time, not just its API pair.
- [ ] Measure one representative duel polling cycle.
- [x] Optimize the 4,800-land map snapshot and set explicit payload and
  latency budgets. Sparse serialization reduced the live decoded/wire payload
  to 735,722/61,459 bytes and passed the 1.5-second map gate at 526.0 ms p95.
- [x] Confirm paid PostgreSQL price, backups, background-worker support, and
  rollback expectations.
- [ ] Compare with Render Frankfurt only if PythonAnywhere misses a measured
  latency, capacity, recovery, or support gate.

---

## Phase 1 — Production deployment skeleton

Priority: **P0**

- [x] Add a production `Dockerfile` or provider-specific deployment manifest.
- [x] Use PythonAnywhere's managed WSGI workers; Gunicorn is not user-managed
  on the selected provider.
- [x] Pin one supported server Python version across local development, CI, and
  hosting.
- [x] Remove dependency installation from WSGI import.
- [x] Create separate staging and production environments.
- [x] Store secrets in private provider-side environment files outside the
  repository; deployment templates contain placeholders only.
- [x] Configure TLS and force HTTPS.
- [x] Configure and live-verify exact CORS origins for both environments.
- [x] Add `/healthz` without a database dependency.
- [x] Add `/readyz` with database and schema-version checks.
- [x] Add build metadata: commit SHA, API version, and minimum client version.
- [ ] Create canonical API DNS.
- [x] Document deployment and rollback commands.

Verification:

- [x] Fresh staging deployment succeeds from an empty environment.
- [x] Health and readiness fail correctly when dependencies are unavailable.
- [x] No package installation or schema mutation occurs in a web-worker import.

---

## Phase 2 — PostgreSQL setup and recovery

Priority: **P0**

- [x] Add `psycopg` and production connection settings.
- [x] Add PostgreSQL to CI.
- [x] Audit every raw DDL operation and migration for PostgreSQL.
- [x] Decide whether to harden the custom runner or adopt Alembic.
- [x] Test JSON, timestamps, indexes, unique constraints, and row locking.
- [x] Build a repeatable SQLite-to-PostgreSQL importer.
- [x] Preserve IDs and reset PostgreSQL sequences.
- [x] Validate row counts and foreign keys.
- [x] Validate the fresh production bootstrap: schema version, one AI user,
  4,800 lands, region/champion seeds, and zero human accounts/games/ownership.
- [x] Rehearse fresh production initialization and application rollback (one
  complete production rehearsal passed; repeating it without a changed path
  is not a beta gate).
- [x] Add maintenance/read-only mode for the cutover.
- [ ] Enable managed PITR if later usage requires a sub-day RPO (deferred for
  the initial beta).
- [ ] Add one encrypted daily backup outside the primary provider (initial
  encrypted round-trip-verified copy passed; recurrence and second-store
  replication remain).
- [x] Perform and time a complete restore drill.
- [x] Document fresh initialization, optional import, and application rollback.

Verification:

- [x] No production SQLite dependency remains.
- [x] Migration validation is automated and passes.
- [x] Restore execution meets the two-hour RTO by a wide margin (transactional
  restore under one second; restore plus preparation three seconds). The
  26-hour RPO closes when the recurring daily backup is activated.

---

## Phase 3 — Multi-worker and background-job correctness

Priority: **P0**

- [x] Replace in-process Conquer idempotency with durable idempotency records
  and unique constraints.
- [x] Replace process-local game locks with transactional row/advisory locks.
- [x] Persist Conquer round deadlines.
- [x] Move AI execution out of web workers into a dedicated always-on worker
  driven from durable game state.
- [x] Move the stuck-game sweeper into the dedicated worker.
- [x] Keep migration, seeding, and reconciliation in an explicit pre-reload
  preparation command instead of WSGI import.
- [ ] Add a general job lease/retry/failure-history subsystem if real worker
  failures require it (P1; durable game state and one advisory-locked worker
  are sufficient for the initial beta).
- [x] Replace `/tmp` leader election with database-backed leadership.
- [x] Use shared rate-limit counters for login, registration, and kingdom
  rename.
- [ ] Continue the broad mutation-atomicity audit after beta; P0 is the
  representative high-value Conquer, Duel acceptance, reward, and land
  transfer paths plus restart/duplicate regressions.
- [x] Make Duel challenge acceptance/game/deck/gold creation atomic and
  idempotent across workers.
- [x] Remove migration, seeding, reconciliation, and worker startup from WSGI
  import.
- [x] Test simultaneous duplicate Conquer actions against the live
  three-worker staging deployment.
- [x] Test simultaneous conflicting actions across Duel and Conquer (one
  canonical Duel acceptance; exactly one of two competing Conquer advances;
  and a cross-endpoint advance/withdraw race all passed on live staging).
- [ ] Run at least two web workers plus one job worker for a 24-hour soak.

Verification:

- [ ] No gameplay correctness relies on process-local mutable state.
- [ ] Restarts and duplicate delivery do not duplicate cards, rewards, battle
  results, or land transfer.

---

## Phase 4 — API and database performance

Priority: **P0**

- [ ] Add a consolidated viewer-safe game snapshot only if measured polling
  load misses its beta target (P1).
- [ ] Include figures, spells, logs/chat, and a state version in that future
  snapshot (P1).
- [x] Return the collection subset required by Conquer/defence config in the
  config response (SQL-grouped snapshot; new browser clients issue only the
  combined initial request, while desktop retains an old-server fallback).
- [ ] Cache collection state by version only if profiling shows a need (P1).
- [x] Remove map-unused/internal fields and omit client-safe default values
  from the 4,800-land response.
- [ ] Cache kingdom/map state by version only if profiling shows a need (P1).
- [ ] Add `ETag` or numeric version cursors only if measured repeat traffic
  requires them (P1).
- [x] Add browser CORS preflight caching.
- [x] Verify response compression: a live application-on/off A/B confirmed
  PythonAnywhere already gzip-compresses the 3.34 MB map JSON to about 122 KB;
  redundant application gzip was removed.
- [x] Pause new browser polling while the tab is hidden.
- [ ] Add broader adaptive polling/error backoff only if the fixed two-second
  game cadence misses load or recovery targets (P1).
- [ ] Add jitter to polling intervals if invited-beta traffic shows synchronized
  bursts (P1).
- [ ] Cancel obsolete navigation requests if they become visible in runtime
  traces (P1).
- [ ] Profile real PostgreSQL queries.
- [ ] Add indexes based on query plans.
- [ ] Remove N+1 query paths.
- [x] Record decoded and compressed wire-body sizes in the authenticated load
  harness.
- [x] Use repository-native authenticated read-load and simultaneous-action
  harnesses instead of adding k6/Locust solely for tool parity.
- [x] Add and run a reproducible authenticated read-load scenario for
  Collection, Conquer config, game polling, and the 4,800-land map.

Verification:

- [ ] Target screen/API p95 and error-rate objectives pass at 2x launch load
  (the `3952bb4` 100-active-user read mix passed with 1,128/1,128 HTTP `200`,
  zero errors, 185.2 ms overall p95, 185.3 ms Conquer-config p95, and
  526.0 ms map p95; gameplay mutations and the full screen matrix remain).
- [ ] Database pool and worker saturation retain operational headroom.

---

## Phase 5 — Web bundle and startup performance

Priority: **P0** for measured startup budget; further reduction is **P1**

- [x] Add file-by-file bundle-size reporting to CI.
- [x] Enforce a pragmatic compressed budget: 52 MiB per browser/Android
  archive and 15 MiB external audio. The current archives are about 46 MiB;
  30 MiB remains an optimization target, not a launch gate.
- [ ] Remove more unused/duplicate assets when the report identifies a safe,
  material win (P1).
- [x] Verify the MP3/OGG copies required by browser/native audio paths.
- [ ] Lazy-load music/non-entry assets where pygbag reliably permits it (P1).
- [ ] Add immutable content-hashed asset caching if GitHub Pages caching proves
  insufficient (P1).
- [ ] Add stronger client/cache invalidation if mixed versions appear in beta
  (P1).
- [ ] Evaluate a service worker after a stable beta (P2).
- [ ] Measure first byte, download, decompression, login-ready time, warm reload,
  and peak memory.
- [ ] Test throttled mobile LTE and older mobile devices.

Verification:

- [ ] Cold and warm startup budgets pass on the supported device matrix.
- [ ] Client/API versions cannot be mixed silently.

---

## Phase 6 — Observability and incident response

Priority: **P0**

- [x] Add structured JSON logs.
- [x] Add request IDs to server logs, response headers, and client-visible
  errors.
- [x] Record route, status, duration, safe user identifier, environment, and
  commit SHA.
- [ ] Add centralized exception reporting when provider logs cease to be
  practical (P1).
- [x] Measure route latency percentiles in external and authenticated load
  probes; a metrics dashboard is deferred.
- [ ] Add continuous DB-pool/job/business metrics if beta volume makes the
  ten-minute operator check unreliable (P1).
- [ ] Activate external uptime monitoring from the default branch and
  stage-fail it to verify maintainer notifications.
- [x] Add an external health/readiness/legal/latency probe and scheduled
  GitHub workflow; activate and stage-fail the schedule from the default
  branch before launch.
- [ ] Keep GitHub uptime failure notifications and the daily operator check as
  the beta alert path; add storage/backup/job alerts after measured need (P1).
- [x] Redact tokens, passwords, email addresses, and database credentials from
  structured logs; hidden game state is never deliberately logged.
- [x] Define pragmatic log, backup, and report-retention targets.
- [x] Create incident, restore, failed-deploy, and moderation runbooks.
- [ ] Confirm that GitHub support/issues and workflow-failure notifications are
  actively monitored. A separate support inbox/status product is deferred.

Verification:

- [ ] A staged failure triggers the correct alert and has enough context to
  diagnose it without server-shell archaeology.

---

## Phase 7 — Account lifecycle

Priority: **P0**

- [ ] Add email password reset after a sender domain/provider exists (P1);
  disclose the beta limitation meanwhile.
- [ ] Add resend-verification after email delivery is enabled (P1). Human
  authentication tokens already expire.
- [ ] Select a transactional email provider when a sender domain exists (P1).
- [ ] Configure SPF, DKIM, and DMARC with that future provider (P1).
- [x] Add password change.
- [x] Revoke all prior sessions after credential changes.
- [x] Add token versioning for server-enforced session revocation while
  retaining version-zero legacy-token compatibility.
- [x] Add "log out all devices".
- [x] Add account deletion/anonymization.
- [x] Add a bounded personal-data JSON export on browser and desktop.
- [x] Define and test historic-game, message, kingdom, and username behavior
  after deletion.
- [x] Retain shared cross-worker brute-force rate limits; CAPTCHA escalation is
  deferred until abuse justifies it.
- [ ] Add user-facing offline, timeout, and retry states.
- [ ] Monitor delivery when player email is enabled (P1).

Verification:

- [x] Registration, password change, revocation, export, and deletion pass
  automated end-to-end route tests. Email verification/reset are explicitly
  deferred and not represented as available.

---

## Phase 8 — Moderation and player safety

Priority: **P0**

- [x] Add authorized user, Duel-message, kingdom-message, and kingdom-name
  report contexts; the compact client exposes the common player-report flow.
- [x] Add block/unblock user and prevent direct messages/challenges in either
  direction.
- [x] Add temporary chat mute.
- [x] Add temporary suspension, permanent ban, and unban.
- [x] Add an operator CLI for the beta; a custom admin frontend is deferred.
- [x] Add an append-only moderation action audit.
- [x] Preserve an authorization-checked evidence snapshot while keeping it out
  of reporter/account responses.
- [x] Add rate limits to player reports and both chat systems. Link-specific
  filtering is deferred until abuse demonstrates a need.
- [x] Return stable moderation/session reason codes and support guidance without
  exposing private evidence.
- [x] Document appeal/contact handling.
- [x] Add registration and chat kill switches plus new-game, Conquer, AI-job,
  and whole-site maintenance switches.
- [x] Route illegal/private content notices through the same evidence-preserving
  report queue and operator incident process for the beta.

Verification:

- [x] An operator can receive, investigate, action, audit, and close a report
  without direct database edits.

---

## Phase 9 — Security, privacy, legal, and attribution

Priority: **P0**

- [ ] Repeat authorization/IDOR review for every mutation route.
- [ ] Verify hidden hands, figures, spells, tactics, and previews cannot leak.
- [ ] Test replayed and concurrent mutations.
- [ ] Run an automated scan against staging.
- [ ] Complete a focused manual threat review.
- [ ] Rotate production secrets immediately before launch.
- [ ] Verify TLS, HSTS, CSP, and CORS on live domains.
- [ ] Publish a real monitored security contact.
- [ ] Complete `docs/legal/ATTRIBUTION.md`.
- [ ] Replace vague operator references with real operator/contact information.
- [ ] Add an appropriate legal notice/Impressum if required.
- [ ] List every data processor and subprocessor.
- [ ] Record purposes, lawful basis, retention, recipients, transfers, and
  deletion behavior for every personal-data category.
- [ ] Accept/sign provider DPAs.
- [ ] Obtain EU/German review of age handling.
- [x] Make legal-version changes trigger re-consent.
- [x] Align privacy text with implemented export/deletion, reports/blocks, and
  retention behavior.
- [ ] Obtain review of DSA/DDG obligations for player-visible content.

Verification:

- [ ] No placeholder legal or attribution text remains.
- [ ] A data-subject request can be completed using the documented process.
- [ ] Qualified legal review has approved the launch posture.

---

## Phase 10 — CI/CD and release engineering

Priority: **P0** for the immutable, tested release path; automation polish is
**P1**

- [x] Add SQLite/PostgreSQL test coverage during migration.
- [x] Add migration-from-previous-release tests through the ordered migration
  runner and disposable PostgreSQL CI path.
- [ ] Validate the provider-specific release artifact on every candidate; a
  container image is not used on PythonAnywhere.
- [ ] Build and inspect this release candidate's web client before staging
  promotion (the workflow/process exists; the current working tree is not yet
  a credited artifact).
- [x] Add a bundle-size regression gate.
- [ ] Add pragmatic lint/format checks.
- [ ] Add coverage reporting and touched-code thresholds.
- [x] Retain dependency and secret scans.
- [ ] Auto-deploy `develop` to staging.
- [ ] Deploy production only from an approved tag or `main`.
- [x] Tie immutable artifacts to a commit SHA.
- [x] Add post-deploy smoke tests.
- [x] Add minimum client/API/schema metadata and readiness compatibility checks.
- [x] Add maintenance mode and narrow beta feature switches.
- [x] Test application rollback independently of database recovery.
- [ ] Add checksums/signing for installers.
- [ ] Publish release notes and known issues.

Verification:

- [ ] A fresh release can deploy, smoke-test, and roll back without manual file
  editing on the production server.

---

## Phase 11 — Compatibility, accessibility, and gameplay QA

Priority: **P0** for the representative browser/mobile/gameplay matrix;
exhaustive platform and accessibility coverage is **P1**

Compatibility matrix:

- [ ] Chrome, Firefox, and Edge desktop.
- [ ] Safari macOS and iOS.
- [ ] Chrome Android.
- [ ] macOS, Windows, and Linux installers.
- [ ] Slow/reconnecting network.
- [ ] Tab suspension and page refresh.
- [ ] Phone, tablet, and desktop resolutions.
- [ ] Keyboard, mouse, and touch.
- [ ] Audio interruption, keyboard opening, calls, and backgrounding.
- [ ] Cold and warm client versions.

Gameplay validation:

- [ ] Two real accounts through every Duel and Conquer phase.
- [ ] AI opponents with restarts during pending jobs.
- [ ] Browser refresh during every confirmation phase.
- [ ] Simultaneous opponent actions.
- [ ] Open battles during deployment.
- [ ] Long-running soak games.
- [ ] Stuck-game recovery.
- [ ] Economy invariants for cards, boosters, gold, maps, and ownership.
- [ ] State-machine property/fuzz tests.
- [ ] Hidden-information regression tests.

Accessibility baseline:

- [ ] Minimum touch targets.
- [ ] Keyboard navigation where the canvas architecture permits it.
- [ ] No essential state communicated only by color.
- [ ] Readable contrast and scalable text.
- [ ] Reduced-motion setting.
- [x] Independent music and effects controls.
- [ ] Accessibility statement describing canvas/screen-reader limitations.

---

## Phase 12 — Staged rollout

Priority: **P0**

Stages:

1. Staging with automated and two-account smoke tests.
2. Internal beta with test accounts.
3. Invited beta with 20–30 players for at least seven days.
4. Expanded beta with 100–300 players for at least seven days.
5. Public beta with open registration and live monitoring.
6. 1.0 decision after reliability, retention, and support load are known.

At every stage:

- [ ] Review latency, errors, stuck games, and moderation reports daily.
- [ ] Confirm backups daily.
- [ ] Perform a restore drill before expanding.
- [ ] Keep kill switches for registration, chat, AI, new games, and Conquer.
- [ ] Maintain 2x tested capacity.
- [ ] Perform 24-hour, 72-hour, and seven-day reviews.

---

## Final public-registration go/no-go gate

- [x] Hosting provider and region meet the measured latency target.
- [x] Fresh PostgreSQL production initialization is rehearsed and validated.
- [x] No production SQLite remains.
- [ ] Two web workers plus the job worker pass a 24-hour soak.
- [ ] No correctness dependency remains process-local.
- [ ] Restore drill meets RPO and RTO.
- [ ] Staging/production deployment and rollback are reproducible.
- [ ] Health, readiness, external probes, request IDs, redacted logs, and
  actionable operator alerts work.
- [ ] Load test passes at 2x expected concurrency.
- [ ] Conquer, defence, map, and duel polling meet screen targets.
- [ ] Password change, deletion/export, and session revocation work. Email
  password reset is a disclosed post-domain beta follow-up.
- [ ] Reporting, blocking, and operator CLI moderation work; a custom admin
  frontend is not required.
- [ ] Legal operator/contact, privacy, and attribution are complete.
- [ ] The representative browser/mobile matrix passes; exhaustive device-lab
  coverage is not required.
- [ ] Bundle/startup performance meets the agreed budget.
- [ ] No unresolved critical/high security issue remains.
- [ ] Live two-account smoke test passes after the release candidate.
- [ ] Support and incident contacts are monitored.

## Explicitly deferred until after a stable public beta

- WebSockets, unless optimized polling fails its SLO.
- Kubernetes.
- Microservices.
- Active-active multi-region state.
- Advanced matchmaking and ratings.
- Monetization.
- Localization.
- Moving the static client away from GitHub Pages without evidence.
- Redis unless shared coordination/rate limiting requires it.
- Managed PITR and sub-hour RPO; retain verified daily dumps and off-provider
  encrypted copies for the initial beta.
- A custom moderator/admin web interface; use authenticated APIs and audited
  operator commands first.
- Centralized tracing/metrics platforms and a public status-site product;
  external probes plus provider/application logs are sufficient initially.
- Forgot-password email delivery, SPF/DKIM/DMARC, and transactional-email
  monitoring until a mail provider and real sender domain are selected.
- Full game-snapshot/ETag architecture, service-worker/offline support, and
  aggressive cache versioning while measured polling and startup budgets pass.
- Formal property/fuzz programs, full accessibility remediation, and complete
  cross-device lab coverage; retain focused regression and representative
  manual testing.
- A second Render hosting benchmark unless PythonAnywhere EU misses a measured
  launch gate.

## Indicative execution sequence

- Week 1: hosting bake-off, provider decision, production skeleton.
- Weeks 2–3: PostgreSQL setup/recovery and multi-worker correctness.
- Weeks 3–4: request consolidation, polling, database and bundle performance.
- Weeks 4–5: observability, deployment, backup, and recovery.
- Weeks 5–6: account lifecycle, moderation, legal, and attribution.
- Weeks 6–7: device QA, load/soak testing, release candidate.
- Weeks 8–9: invited and expanded beta before public registration.

Part-time expectation: approximately two to three months.

## Decision log

| Date | Decision | Evidence | Consequences |
|---|---|---|---|
| 2026-07-19 | Public beta precedes 1.0 | Operational/account gaps remain despite mature gameplay | Growth features are deferred |
| 2026-07-19 | Keep GitHub Pages during hosting test | Static delivery was not the measured API bottleneck | Compare API/database hosts only |
| 2026-07-19 | Test PythonAnywhere EU free account | Current US path showed high Europe-to-host transit | Free test decides regional latency only |
| 2026-07-19 | PythonAnywhere EU passes the regional latency gate | Warm p95 37.0 ms versus 478.3 ms US; CORS pair p95 80.6 ms versus 798.0 ms US; authenticated Conquer API pair p95 157.7 ms | EU becomes the preferred low-change candidate; paid operations still decide the provider, while the 4,800-land map becomes a separate app optimization |
| 2026-07-19 | PythonAnywhere EU paid account for staged public beta | EU latency benchmark passed and the account was upgraded | Use managed WSGI workers, PA PostgreSQL, and always-on tasks; retain Render Frankfurt as exit option |
| 2026-07-19 | Preserve the free-plan deployment before production changes | Pushed and live-tested `backup/pythonanywhere-free-eu-2026-07-19` at `7c85e83` | SQLite/single-worker fallback remains reproducible but requires its matching database snapshot |
| 2026-07-19 | Harden the existing migration runner for PostgreSQL instead of adopting Alembic before beta | Only 14 ordered migrations exist; changing frameworks during the database cutover adds avoidable migration-state risk | Add PostgreSQL CI, portability tests, and explicit pre-reload execution now; reconsider Alembic after beta |
| 2026-07-19 | PostgreSQL plan | Separate least-privilege staging/production DB owners on PythonAnywhere; 1 GiB initial allocation | Both databases/users were created and connectivity-verified; production was initialized fresh at schema 17 |
| 2026-07-19 | Dedicated PythonAnywhere always-on worker driven from durable game state | Three paid WSGI workers made in-process AI/sweeper startup unsafe; controlled staging worker test initialized AI, swept, and shut down cleanly | Web workers keep AI/background services disabled; PostgreSQL advisory leadership prevents duplicate task ownership; attempt limits and failure history remain before launch |
| 2026-07-19 | PostgreSQL-backed multi-worker coordination | Release `e52611c` passed local, Python 3.11, and disposable PostgreSQL 16 tests; staging reports schema 17 with three workers | Conquer receipts, deadlines, game transaction locks, and security rate limits are shared; live gameplay and soak gates remain |
| 2026-07-19 | Promote staging to release `949126c` after live race discovery | Validated PostgreSQL backup, green 2,627-test/CI/security gates, permanent task `35390`, six concurrent identical withdrawals with one canonical response and one durable receipt, and clean post-deploy logs | Staging is open on three workers plus one dedicated worker; next gates are restore automation, conflicting-action/two-account testing, and the 24-hour soak |
| 2026-07-19 | Start EU production with fresh data | The old US server and its accounts were development-only | Do not run a legacy data import; initialize and verify the empty `nepalkings_prod` database before switching released clients |
| 2026-07-19 | Launch first on provider domains | PythonAnywhere supports `something-username.eu.pythonanywhere.com` for additional paid-account apps, and GitHub Pages already hosts the client | Use `api-nepalkingz.eu.pythonanywhere.com` for initial production and add polished web/API domains later without moving PostgreSQL data |
| 2026-07-19 | Provision the production web tier but hold public cutover | Web app `56868` passed TLS, health/readiness, CORS, authentication, three-worker concurrent reads/writes, cleanup, and staging-isolation checks; maintenance was restored | Keep GitHub Pages on its existing artifact until a second always-on task is allocated, the production worker is verified, and remaining launch gates pass |
| 2026-07-20 | Keep production maintained while the runtime soak continues | Tasks `35390` and `35394` remained on isolated release/environment/database paths; the ten-hour checkpoint showed continuous minute sweeps, exact advisory locks, and no suspicious worker lines | Do not treat the 24-hour gate as passed before its full checkpoint |
| 2026-07-20 | Use encrypted provider-independent database copies | The first production dump passed provider catalog/hash validation, local hash equality, CMS AES-256-GCM encryption, two decryption hash checks, and plaintext cleanup | Replicate archive plus manifest to a second independent store, protect a recovery-key copy, and automate daily execution before opening registration |
| 2026-07-20 | Add an external launch-contract probe | A three-sample live cycle passed production and staging health, readiness, PostgreSQL schema, legal discovery, release consistency, and 2-second p95 ceiling | Scheduled GitHub monitoring activates from the default branch; advanced metrics and alert destinations remain separate launch work |
| 2026-07-20 | Serialize and atomically commit Duel challenge acceptance | The audit found partial commits and no accepted-status guard in `create_game`; release `636364d` passed 2,645 local tests, PostgreSQL CI, security scans, and a live two-account simultaneous accept with one game/deck and one charge per user | Staging advanced to `636364d`; Conquer conflicting-action and final-release soak gates remain |
| 2026-07-20 | Model 2x launch read load as 100 active users with five-second think time | The live staging run completed 1,126 authenticated reads at 18.77 requests/second with zero errors, 163.2 ms overall p95, 163.2 ms Conquer-config p95, and 1,264.8 ms map p95 | Read capacity has headroom; retain the map-specific 1.5-second budget and continue with mutation/polling scenarios before closing the full load gate |
| 2026-07-20 | Verify and harden Conquer battle serialization | The existing application-wide PostgreSQL lock plus release `df69ece` route-local fallback/finished-state guards passed 2,655 local tests, full CI, PostgreSQL CI, security scanning, a one-of-two advance race, and a cross-endpoint advance/withdraw race | The deliberately conflicting Conquer gate is closed; its intermediate soak began at 11:39 UTC and was later superseded by `4660f75` |
| 2026-07-20 | Rely on verified PythonAnywhere gzip instead of duplicating compression in Flask | A live A/B measured 122,140 bytes with application gzip and 122,141 bytes with it disabled for the same 3,341,221-byte map JSON; both responses were gzip encoded | Remove redundant application gzip, retain wire-size measurement, and focus map work on construction/serialization plus versioned caching |
| 2026-07-20 | Promote the provider-gzip release `4660f75` as the staging candidate | Immutable artifact and backup checks passed; all CI/security jobs were green; its final 100-user run returned 1,129/1,129 HTTP `200` with 128.7 ms overall p95 and 891.7 ms map p95; post-load probes and logs were clean | Restart the release-candidate soak at the worker's clean 12:19:34 UTC start; production stays on `90bfa02` in maintenance |
| 2026-07-20 | Combine configuration and collection bootstrap reads | Conquer and Defence setup now embed one SQL-grouped collection snapshot; browser loaders request only the combined endpoint, desktop clients retain an old-server fallback, and 2,668 local tests passed | Remove one authenticated request/preflight path from each initial setup-screen load; deploy to staging and measure before recording a live gain |
| 2026-07-20 | Close staging credential recovery with secret-safe database tooling | The third rotation passed a no-echo structural/login verifier; `create_postgres_backup.py` produced and catalog-validated a mode-600 dump without putting a URL/password in subprocess arguments; superseded credentials are invalid and stale logs were cleared | Use the secret-safe backup and worker-verification helpers for every PostgreSQL deployment; never pass SQLAlchemy URLs directly to libpq commands |
| 2026-07-20 | Promote sparse-map release `3952bb4` as the staging candidate | 2,682 local tests, GitHub Python/PostgreSQL/dependency/security jobs, immutable backup/deploy, 1,128/1,128 zero-error 100-user reads, 526.0 ms map p95, external probes, and post-load logs passed | Map decoded/wire size fell from 3,341,221/122,140 to 735,722/61,459 bytes; restart the 24-hour release-candidate soak at the clean 14:12:15 UTC worker start while production stays maintained |
