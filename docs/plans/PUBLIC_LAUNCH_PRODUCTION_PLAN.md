# Nepal Kings Public Launch and Production Readiness Plan

Last updated: 2026-07-19

Status: Execution in progress; PythonAnywhere EU selected

Launch framing: staged public beta before a 1.0 claim

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

Execution checkpoint (2026-07-19):

- The exact pre-production/free-plan state is preserved and pushed as
  `backup/pythonanywhere-free-eu-2026-07-19` at commit
  `7c85e83ca31223982fdbce0d3925247f9407a847`.
- That branch passed all 2,609 tests and was deployed/smoke-tested on the EU
  one-worker SQLite app before production work began.
- Production work stays on `develop`; the fallback branch must not receive
  PostgreSQL or multi-worker changes.
- PythonAnywhere EU is selected for the staged public beta. GitHub Pages
  remains the static client host.

Already present:

- Broad server and client regression coverage.
- GitHub Pages web deployment and desktop installer workflows.
- Production secret and destructive-startup guards.
- Viewer-aware gameplay serialization and ownership checks.
- Security headers, dependency auditing, and secret scanning.
- Versioned Terms and Privacy acceptance.
- SQLite backup-before-deploy tooling and a restore script.
- Analytics/funnel events.
- Rule-based AI opponents.

Known launch blockers:

- Production still uses SQLite.
- Multiple web workers are not gameplay-safe because important coordination is
  process-local.
- Database migration, reconciliation, map seeding, AI setup, and a sweeper run
  during WSGI startup.
- The current US PythonAnywhere route has high end-to-end latency from Europe.
- Screens and game polling fan out over multiple HTTP requests.
- There are no production health/readiness endpoints or complete application
  metrics.
- Account recovery, deletion/export, and session revocation are incomplete.
- Player reporting, blocking, suspension, and moderator tooling are missing.
- Legal operator/contact details, retention specifics, and final attribution
  are incomplete.
- The staged browser archive is approximately 45 MiB.
- CI does not exercise PostgreSQL, production container builds, migrations, or
  load tests.

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
- Recovery point below one hour when PITR is available.
- Recovery time below two hours.
- Canonical domains such as `play.nepalkings.com`,
  `api.nepalkings.com`, and `status.nepalkings.com`.

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

- [ ] Open the **API token** tab and create/copy an API token.
- [ ] Create one manual web app:
  `EU_USERNAME.eu.pythonanywhere.com`.
- [ ] Select Python 3.11 to match current server CI.

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
- [ ] Conquer config screen-ready p95 is below 1.5 seconds after request
  consolidation, or the raw regional result demonstrates that target is
  credible.
- [x] p95 is stable and is not dominated by multi-second outliers in the first
  50-sample round.
- [x] Access-log times remain low while external times improve.

Choose PythonAnywhere EU only if:

- [ ] Its paid PostgreSQL add-on price and backup behavior are acceptable.
- [ ] The app can run the required dedicated background work.
- [ ] Deployment, rollback, logs, and alerting can meet the remaining gates.
- [ ] Multi-worker state is fixed before enabling additional workers.

Choose Render Frankfurt if:

- [ ] It meets the same latency targets.
- [ ] Managed PostgreSQL, background workers, health checks, and rollback
  materially reduce launch risk.
- [ ] The measured configuration stays within the agreed monthly budget.

Do not use the free-plan benchmark to compare concurrent throughput.

Hosting decision output:

- [ ] Selected provider and region recorded below.
- [ ] Monthly launch budget recorded.
- [ ] PostgreSQL plan recorded.
- [ ] Background-worker plan recorded.
- [ ] Staging and production topology recorded.
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

Still required before making the final hosting commitment:

- [ ] Repeat the benchmark in the evening and on a second day.
- [x] Run an automated real-browser benchmark from the GitHub Pages origin.
- [x] Run Phase C with a synthetic EU test user and real Conquer/Collection
  routes.
- [ ] Measure full Pygbag Conquer screen-ready time, not just its API pair.
- [ ] Measure one representative duel polling cycle.
- [ ] Optimize or cache the 4,800-land map snapshot and set an explicit payload
  and server-time budget.
- [ ] Confirm paid PostgreSQL price, backups, background-worker support, and
  rollback expectations.
- [ ] Compare those operational requirements with a concrete Render Frankfurt
  configuration and monthly price.

---

## Phase 1 — Production deployment skeleton

Priority: **P0**

- [x] Add a production `Dockerfile` or provider-specific deployment manifest.
- [x] Use PythonAnywhere's managed WSGI workers; Gunicorn is not user-managed
  on the selected provider.
- [x] Pin one supported server Python version across local development, CI, and
  hosting.
- [x] Remove dependency installation from WSGI import.
- [ ] Create separate staging and production environments.
- [x] Store secrets in private provider-side environment files outside the
  repository; deployment templates contain placeholders only.
- [x] Configure TLS and force HTTPS.
- [ ] Configure and live-verify exact CORS origins for both environments.
- [x] Add `/healthz` without a database dependency.
- [x] Add `/readyz` with database and schema-version checks.
- [x] Add build metadata: commit SHA, API version, and minimum client version.
- [ ] Create canonical API DNS.
- [x] Document deployment and rollback commands.

Verification:

- [ ] Fresh staging deployment succeeds from an empty environment.
- [x] Health and readiness fail correctly when dependencies are unavailable.
- [x] No package installation or schema mutation occurs in a web-worker import.

---

## Phase 2 — PostgreSQL migration

Priority: **P0**

- [x] Add `psycopg` and production connection settings.
- [ ] Add PostgreSQL to CI.
- [ ] Audit every raw DDL operation and migration for PostgreSQL.
- [ ] Decide whether to harden the custom runner or adopt Alembic.
- [ ] Test JSON, timestamps, indexes, unique constraints, and row locking.
- [ ] Build a repeatable SQLite-to-PostgreSQL importer.
- [ ] Preserve IDs and reset PostgreSQL sequences.
- [ ] Validate row counts and foreign keys.
- [ ] Validate collections, open games, configurations, kingdoms, regions, and
  land ownership.
- [ ] Rehearse twice against recent backup copies.
- [x] Add maintenance/read-only mode for the cutover.
- [ ] Enable managed backups and PITR.
- [ ] Add one encrypted daily backup outside the primary provider.
- [ ] Perform and time a complete restore drill.
- [ ] Document cutover and rollback.

Verification:

- [ ] No production SQLite dependency remains.
- [ ] Migration validation is automated and passes.
- [ ] Restore meets RPO and RTO.

---

## Phase 3 — Multi-worker and background-job correctness

Priority: **P0**

- [ ] Replace in-process Conquer idempotency with durable idempotency records
  and unique constraints.
- [ ] Replace process-local game locks with transactional row/advisory locks.
- [ ] Persist Conquer round deadlines.
- [ ] Move AI work into a durable job mechanism.
- [ ] Move sweepers and reconciliation into a dedicated worker.
- [ ] Add job leases, retries, attempt limits, and failure history.
- [ ] Replace `/tmp` leader election with database-backed leadership.
- [ ] Use shared rate-limit counters.
- [ ] Make reward, collection, ownership, and battle mutations atomic.
- [ ] Remove migration, seeding, reconciliation, and worker startup from WSGI
  import.
- [ ] Test simultaneous duplicate and conflicting actions.
- [ ] Run at least two web workers plus one job worker for a 24-hour soak.

Verification:

- [ ] No gameplay correctness relies on process-local mutable state.
- [ ] Restarts and duplicate delivery do not duplicate cards, rewards, battle
  results, or land transfer.

---

## Phase 4 — API and database performance

Priority: **P0**

- [ ] Add one viewer-safe game snapshot endpoint.
- [ ] Include game, figures, active spells, versioned logs/chat, and state
  version in the snapshot.
- [ ] Return the collection subset required by Conquer/defence config in the
  config response.
- [ ] Cache collection state by collection version.
- [ ] Cache kingdom/map state by map version.
- [ ] Add `ETag` or numeric version cursors.
- [ ] Add CORS preflight caching.
- [ ] Enable response compression.
- [ ] Pause polling when the tab is hidden.
- [ ] Add adaptive polling and exponential error backoff.
- [ ] Add jitter to polling intervals.
- [ ] Cancel obsolete navigation requests.
- [ ] Profile real PostgreSQL queries.
- [ ] Add indexes based on query plans.
- [ ] Remove N+1 query paths.
- [ ] Record response payload sizes.
- [ ] Add k6 or Locust scenarios for login, menus, map, Conquer, defence, duel,
  and simultaneous actions.

Verification:

- [ ] Target screen/API p95 and error-rate objectives pass at 2x launch load.
- [ ] Database pool and worker saturation retain operational headroom.

---

## Phase 5 — Web bundle and startup performance

Priority: **P0** for measured startup budget; further reduction is **P1**

- [ ] Add file-by-file bundle-size reporting to CI.
- [ ] Set a compressed bundle budget; initial target below 30 MiB if quality
  permits.
- [ ] Remove unused and duplicate assets.
- [ ] Verify required MP3/OGG duplication.
- [ ] Lazy-load music and non-entry assets where pygbag permits.
- [ ] Add immutable content-hashed asset caching.
- [ ] Add client/cache version invalidation.
- [ ] Evaluate a service worker for repeat visits and offline errors.
- [ ] Measure first byte, download, decompression, login-ready time, warm reload,
  and peak memory.
- [ ] Test throttled mobile LTE and older mobile devices.

Verification:

- [ ] Cold and warm startup budgets pass on the supported device matrix.
- [ ] Client/API versions cannot be mixed silently.

---

## Phase 6 — Observability and incident response

Priority: **P0**

- [ ] Add structured JSON logs.
- [ ] Add request IDs to server logs and client-visible errors.
- [ ] Record route, status, duration, safe user identifier, and commit SHA.
- [ ] Add centralized exception reporting.
- [ ] Measure p50/p95/p99 latency by route.
- [ ] Measure request/error rate, workers, DB pool, slow queries, job age,
  retries, stuck games, active games, and notification failures.
- [ ] Add external uptime monitoring.
- [ ] Alert on health, 5xx, latency, storage, backup failure, and job backlog.
- [ ] Redact tokens, passwords, emails, and hidden gameplay state.
- [ ] Define log-retention periods.
- [ ] Create incident, restore, and failed-deploy runbooks.
- [ ] Create a monitored support inbox and status page.

Verification:

- [ ] A staged failure triggers the correct alert and has enough context to
  diagnose it without server-shell archaeology.

---

## Phase 7 — Account lifecycle

Priority: **P0**

- [ ] Add forgot-password and password-reset flows.
- [ ] Add resend-verification and token expiry.
- [ ] Select a transactional email provider.
- [ ] Configure SPF, DKIM, and DMARC.
- [ ] Add password change.
- [ ] Revoke sessions after credential changes.
- [ ] Add server-side session/token records or token versioning.
- [ ] Add "log out all devices".
- [ ] Add account deletion/anonymization.
- [ ] Add personal-data export.
- [ ] Define how historic games and usernames behave after deletion.
- [ ] Add brute-force protection and CAPTCHA escalation.
- [ ] Add user-facing offline, timeout, and retry states.
- [ ] Monitor email delivery.

Verification:

- [ ] Registration, verification, reset, revocation, export, and deletion pass
  end-to-end tests.

---

## Phase 8 — Moderation and player safety

Priority: **P0**

- [ ] Add report user/message/kingdom-name flows.
- [ ] Add block user.
- [ ] Add chat mute.
- [ ] Add temporary suspension and permanent ban.
- [ ] Add a moderator/admin interface.
- [ ] Add a moderator audit log.
- [ ] Preserve report evidence while hiding removed public content.
- [ ] Add chat spam/link throttling.
- [ ] Return clear moderation reasons.
- [ ] Add appeal/contact handling.
- [ ] Add registration and chat kill switches.
- [ ] Define illegal-content notice handling.

Verification:

- [ ] A moderator can receive, investigate, action, audit, and close a report
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
- [ ] Make legal-version changes trigger re-consent.
- [ ] Align privacy text with implemented export/deletion behavior.
- [ ] Obtain review of DSA/DDG obligations for player-visible content.

Verification:

- [ ] No placeholder legal or attribution text remains.
- [ ] A data-subject request can be completed using the documented process.
- [ ] Qualified legal review has approved the launch posture.

---

## Phase 10 — CI/CD and release engineering

Priority: **P0**

- [ ] Add SQLite/PostgreSQL test coverage during migration.
- [ ] Add migration-from-previous-release tests.
- [ ] Add production image/build validation.
- [ ] Build the web client for every release candidate.
- [ ] Add a bundle-size regression gate.
- [ ] Add pragmatic lint/format checks.
- [ ] Add coverage reporting and touched-code thresholds.
- [ ] Retain dependency and secret scans.
- [ ] Auto-deploy `develop` to staging.
- [ ] Deploy production only from an approved tag or `main`.
- [ ] Tie immutable artifacts to a commit SHA.
- [ ] Add post-deploy smoke tests.
- [ ] Add schema/client compatibility checks.
- [ ] Add maintenance mode and feature flags.
- [ ] Test application rollback independently of database recovery.
- [ ] Add checksums/signing for installers.
- [ ] Publish release notes and known issues.

Verification:

- [ ] A fresh release can deploy, smoke-test, and roll back without manual file
  editing on the production server.

---

## Phase 11 — Compatibility, accessibility, and gameplay QA

Priority: **P0**

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
- [ ] Independent music and effects controls.
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

- [ ] Hosting provider and region meet the measured latency target.
- [ ] PostgreSQL migration is rehearsed and validated.
- [ ] No production SQLite remains.
- [ ] Two web workers plus the job worker pass a 24-hour soak.
- [ ] No correctness dependency remains process-local.
- [ ] Restore drill meets RPO and RTO.
- [ ] Staging/production deployment and rollback are reproducible.
- [ ] Health, readiness, metrics, alerts, and error reporting work.
- [ ] Load test passes at 2x expected concurrency.
- [ ] Conquer, defence, map, and duel polling meet screen targets.
- [ ] Account reset, deletion/export, and session revocation work.
- [ ] Reporting, blocking, and moderator tooling work.
- [ ] Legal operator/contact, privacy, and attribution are complete.
- [ ] Browser/mobile matrix passes.
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

## Indicative execution sequence

- Week 1: hosting bake-off, provider decision, production skeleton.
- Weeks 2–3: PostgreSQL migration and multi-worker correctness.
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
| 2026-07-19 | PostgreSQL plan | Separate least-privilege staging/production DB owners on PythonAnywhere; 1 GiB initial allocation | Locks backup and connection design; live credentials still need provider-side creation |
| TBD | Background job design | Multi-worker correctness prototype | Locks worker/Redis requirements |
