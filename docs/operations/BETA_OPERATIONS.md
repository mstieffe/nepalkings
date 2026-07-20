# Nepal Kings Public-Beta Operations

Last updated: 2026-07-20

This is the small, practical operator runbook for the initial public beta. It
supplements the detailed
[PythonAnywhere deployment runbook](../../deploy/pythonanywhere/README.md) and
[backup runbook](OFFSITE_POSTGRES_BACKUPS.md).

## Daily check (about 10 minutes)

1. Confirm the scheduled **External uptime probe** GitHub Actions run is green.
2. Open PythonAnywhere and confirm the production web app and always-on worker
   are running.
3. Check `/readyz`; record the release SHA and schema version if anything is
   unexpected.
4. Scan the provider error/server logs for JSON entries at `ERROR` and for
   repeated `5xx`, slow requests, or a growing stuck-game count.
5. Review open player reports:

   ```bash
   NEPAL_KINGS_ENV_FILE="$HOME/.config/nepalkings/production.env" \
     "$HOME/.virtualenvs/nepalkings-production/bin/python" \
     "$HOME/releases/CURRENT_SHA/server/manage.py" \
     moderation-list --status open
   ```

6. Confirm scheduled task `22971` ran at 03:15 UTC, its log has no failure,
   and the newest production dump passed `pg_restore --list`. Make another
   encrypted off-provider copy before materially expanding the beta.
7. Check new GitHub support issues without copying private game data into a
   public comment.

## Incident switches

The private environment file supports these reversible switches:

| Variable | Effect when `False` |
|---|---|
| `REGISTRATION_ENABLED` | Stops new accounts; login and existing games continue |
| `CHAT_ENABLED` | Stops Duel chat and kingdom direct messages |
| `NEW_GAMES_ENABLED` | Stops new Duel challenges/games |
| `CONQUER_ENABLED` | Stops new Conquer battles |
| `AI_JOBS_ENABLED` | Pauses AI turns while the sweeper and worker remain alive |

`MAINTENANCE_MODE=True` is the broad emergency switch. It leaves health,
readiness, and legal routes available and returns retryable JSON `503` for
gameplay/auth.

After editing the relevant private environment:

- reload the web app for web-route switches;
- restart the always-on task for `AI_JOBS_ENABLED`;
- verify the intended route returns the documented reason and unrelated reads
  remain healthy.

Prefer the narrowest switch that contains the incident.

## Player report handling

List reports with `moderation-list`. Each report includes a preserved snapshot
of message evidence only when the reporter was authorized to see that message.

Apply one audited action:

```bash
NEPAL_KINGS_ENV_FILE="$HOME/.config/nepalkings/production.env" \
  "$HOME/.virtualenvs/nepalkings-production/bin/python" \
  "$HOME/releases/CURRENT_SHA/server/manage.py" \
  moderation-action REPORT_ID ACTION \
  --hours 24 \
  --reason "Concise operator reason" \
  --actor "operator-name"
```

Actions are `close`, `dismiss`, `mute`, `unmute`, `suspend`, `ban`, and
`unban`. `--hours` applies to `mute` and `suspend`. Suspension and ban revoke
all issued human sessions. Every command appends a `moderation_action` row and
closes the report.

Before acting:

1. confirm the evidence belongs to the reported account;
2. consider context and prior actions;
3. use a mute or temporary suspension when sufficient;
4. write a reason another operator could understand;
5. never paste private evidence into GitHub.

Appeals arrive through the support channel in [SUPPORT.md](../../SUPPORT.md).

## Triage

- **Critical:** data exposure, credential leak, destructive corruption, or
  account takeover. Enable maintenance or the relevant narrow switch, rotate
  affected secrets, preserve redacted evidence, and keep production closed
  until verified.
- **High:** widespread inability to play, repeated 5xx, worker failure, or
  incorrect economy/game mutations. Stop the affected writes, take a backup,
  then roll back the application if schema-compatible.
- **Normal:** one stuck match, visual defect, moderation report, or isolated
  client failure. Preserve the request ID and reproduce on staging.

## Failed deployment

1. Keep or enable maintenance mode.
2. Do not restore the database merely because application code failed.
3. Point the WSGI app and worker to the previous schema-compatible immutable
   release.
4. Reload/restart, then run health, readiness, legal, invalid-login, and one
   authenticated smoke check.
5. Restore the database only for confirmed incompatible/destructive data
   change, using the backup runbook.
6. Record the release SHA, request IDs, decision, and recovery result in the
   dated deployment log.

## Retention targets

- application/security logs: normally up to 30 days;
- PythonAnywhere PostgreSQL dumps: 30 days;
- encrypted off-provider production backups: 90 days;
- closed player-report evidence and moderation audit: up to 12 months, unless
  an active legal, safety, or abuse matter requires longer;
- public GitHub support issues: close when resolved and remove accidentally
  posted personal data when repository controls permit.

Review these manually during the beta. A separate logging/retention platform
is not required unless player volume makes this process unreliable.
