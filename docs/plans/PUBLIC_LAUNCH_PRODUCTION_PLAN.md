# Nepal Kings Lean Public-Beta Launch Plan

Last updated: 2026-07-20

Status: Public beta live on the provider hostnames

This is the completed core launch checklist and the current optional follow-up
backlog for the small public beta.
The former exhaustive plan is preserved at
[`archive/PUBLIC_LAUNCH_PRODUCTION_PLAN_FULL_2026-07-20.md`](archive/PUBLIC_LAUNCH_PRODUCTION_PLAN_FULL_2026-07-20.md).
Detailed deployment evidence remains in
[`../operations/PRODUCTION_DEPLOYMENT_2026-07-19.md`](../operations/PRODUCTION_DEPLOYMENT_2026-07-19.md).

## Launch scope

- Static web client: GitHub Pages.
- API, PostgreSQL, and background workers: PythonAnywhere EU paid account.
- Staging: `https://nepalkingz.eu.pythonanywhere.com`.
- Production: `https://api-nepalkingz.eu.pythonanywhere.com`.
- Production starts with fresh data; legacy development data is not migrated.
- Provider hostnames are acceptable for beta. A polished domain can follow.
- The free-plan fallback remains preserved on
  `backup/pythonanywhere-free-eu-2026-07-19`.

## Core launch checklist

### 1. Release candidate

- [x] Full local suite passes: 2,714 passed, 3 environment-specific skips.
- [x] Focused account, safety, observability, concurrency, and Settings tests
  pass.
- [x] Dependency audit reports no known vulnerabilities.
- [x] Final browser bundle builds and stays below the 52 MiB archive and
  15 MiB external-audio budgets.
- [x] Settings uses four peer tabs: Resolution, Preferences, Account, Safety.
- [x] Commit and push immutable release
  `70e9259200f08e309fdad60b2a7a1aff48d30254`.
- [x] Confirm GitHub CI and security jobs for that SHA.

### 2. Staging deployment

- [x] Take and validate a pre-deployment PostgreSQL backup.
- [x] Deploy the immutable release and migrate staging to schema 19.
- [x] Reload the web app and restart the staging worker on the same SHA.
- [x] Verify health, readiness, legal versions, exact CORS, request IDs, and
  clean logs.
- [x] Run registration/login, account lifecycle, report/block/moderation, and
  one representative Duel/Conquer smoke.

### 3. Production deployment

- [x] Take and validate a pre-deployment production PostgreSQL backup.
- [x] Deploy the same immutable SHA and migrate production to schema 19.
- [x] Point the production web app and worker at that same release.
- [x] Verify the production database is fresh and isolated from staging.
- [x] Verify health, readiness, legal versions, TLS/HSTS/CORS, request IDs,
  worker leadership, and clean logs.
- [x] Run one synthetic registration/login/onboarding/account-safety smoke and
  remove the synthetic account.
- [x] Turn maintenance off after the checks pass.
- [x] Keep registration independently switchable for incident containment.

### 4. Public client and operations

- [x] Publish the tested web artifact with the production API as its default.
- [x] Verify the live browser can register, log in, open Collection, open
  Conquer configuration, and load the kingdom map.
- [x] Publish the GitHub Issues support path and retain normal GitHub
  Issues/Actions repository notifications for beta operations.
- [x] Create a daily provider-side PostgreSQL dump; keep the existing encrypted
  off-provider recovery copy and perform another copy before material beta
  expansion.
- [x] Record the live SHA, schema, worker IDs, backup, smoke results, and
  rollback target in the deployment log.

## Launch go/no-go

Open the beta only when all of these are true:

- [x] The same committed SHA is green locally, in CI, on staging, and in
  production.
- [x] Both databases report PostgreSQL schema 19 and remain isolated.
- [x] Production backup, rollback, and restore procedures are documented and
  have already passed at least one rehearsal.
- [x] Core browser and gameplay smoke paths pass without a server error.
- [x] Account password/session/export/deletion and player report/block controls
  work on the deployed candidate.
- [x] Logs contain request IDs and no new traceback, credential, or repeated
  `5xx` line.
- [x] Production maintenance is off and external probes pass.
- [x] Support issues use the repository templates and the kill switches are
  documented.

If a check fails, keep production in maintenance, fix or roll back, and repeat
only the affected checks.

## First-week routine

- Check readiness, worker state, errors, open reports, and backup age daily.
- Keep the existing registration, chat, new-game, Conquer, AI-job, and
  maintenance switches available.
- Review performance after real players arrive. The latest staging load test
  already passed 100 active simulated readers with zero errors and sub-800 ms
  route p95.
- Expand from an internal/invited beta before actively promoting the public
  link.

## Optional follow-up backlog

These items were deliberately removed from the launch-critical checklist. They
are useful improvements, not prerequisites for starting the beta.

### Hosting and recovery

- Add polished `play.` and `api.` custom domains.
- Replicate encrypted backups to a second independent cloud/offline store.
- Add managed PITR and a sub-hour recovery point if player activity justifies
  the cost.
- Automate retention rotation and backup-age alerts.
- Benchmark Render Frankfurt only if PythonAnywhere misses measured goals.
- Automate staging deployments and tag-only production promotion.

### Performance and architecture

- Reduce the browser bundle toward 30 MiB and lazy-load music/art where pygbag
  supports it reliably.
- Add content-hashed caching, stronger client cache invalidation, or a service
  worker.
- Add snapshot/ETag APIs, state-version cursors, adaptive polling, and jitter
  only if measured beta traffic needs them.
- Profile PostgreSQL query plans and add indexes based on evidence.
- Add WebSockets, Redis, or a separate job lease/history system only if the
  simple deployment stops meeting its targets.
- Add centralized metrics, tracing, exception reporting, and a public status
  page after provider logs and external probes become insufficient.

### Account, moderation, and communications

- Add email password reset, resend verification, a transactional email
  provider, SPF, DKIM, and DMARC after a real domain exists.
- Add a custom moderator/admin web interface; the audited CLI is sufficient
  for beta.
- Add automated link filtering, CAPTCHA escalation, and more elaborate abuse
  tooling if real abuse appears.

### QA, accessibility, and release polish

- Expand testing to a full browser/OS/device lab, throttled LTE, long-running
  soak games, and every refresh/reconnect phase.
- Add formal property/fuzz testing and broader mutation-atomicity review.
- Add full keyboard navigation, reduced motion, canvas accessibility work, and
  an accessibility statement.
- Add coverage thresholds, format/lint enforcement, installer signing, and
  richer release-note automation.
- Run a longer invited-beta progression through 20–30, then 100–300 players
  before calling the game version 1.0.

### Legal and policy follow-up

- Replace provider hostnames and repository contacts with final branded
  operator/contact details when available.
- Complete a formal art-provenance inventory and any additional attribution.
- Obtain specialist review of the privacy, age, user-content, DSA/DDG, and
  Impressum posture before broad commercial promotion.
- Accept or archive provider DPAs and maintain a fuller processor/subprocessor
  register.
