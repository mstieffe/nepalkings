# Database Management

Nepal Kings uses SQLite for local development and PostgreSQL for shared hosted
environments. Schema changes ship as ordered migrations; production is never
reset to avoid implementing a migration.

## Environment boundary

| Environment | Database | Preparation policy |
|---|---|---|
| Local | SQLite `server/test.db` by default | Automatic convenience on server startup |
| Staging | `nepalkings_staging` PostgreSQL | Explicit before WSGI reload |
| Production | `nepalkings_prod` PostgreSQL | Backup, maintenance, then explicit preparation |

The free-plan fallback branch retains its historical single-worker SQLite
layout. Its database is not interchangeable with paid staging or production.

## Schema versioning

`server/migration_runner.py` contains an ordered `MIGRATIONS` list. Applied
versions are recorded in `schema_version`, making preparation idempotent.

`server/startup.py::prepare_database()` performs the bounded preparation flow:

1. optionally drops tables only when an explicit local destructive flag is enabled;
2. creates missing tables for fresh databases;
3. runs pending ordered migrations;
4. releases orphaned Collection locks;
5. seeds or reconciles required persistent game data;
6. ensures the AI service account exists when AI is enabled.

Hosted WSGI imports do not call this flow. Deployments invoke it explicitly.

## Add a migration

1. Choose the next integer schema version in `server/migration_runner.py`.
2. Implement a bounded, idempotent migration callable.
3. Append `(version, description, callable)` to `MIGRATIONS`.
4. Never renumber, remove, or silently rewrite a migration that reached a
   shared environment.
5. Add tests for a fresh database and an existing database at the previous version.
6. Add PostgreSQL coverage when SQL syntax, constraints, locking, sequences, or
   transaction behavior may differ from SQLite.
7. Run the full suite and the CI PostgreSQL job before deployment.

Use explicit SQL or SQLAlchemy operations that can safely detect already
applied structure. A failed migration rolls back and prevents later migrations
from running against an unknown intermediate schema.

## Prepare a local database

Normal local startup prepares the default SQLite database automatically:

```bash
./run_local.sh
```

To prepare explicitly through the same management entry point used by hosted
deployments:

```bash
cd server
APP_ENVIRONMENT=development \
  ../.venv/bin/python manage.py prepare-database
```

## Reset local development data

Only reset a disposable local database. Stop the local server first, verify the
active environment and database path, then run:

```bash
cd server
bash RESET_DATABASE.sh
```

The script requires confirmation. Production safety guards refuse destructive
startup behavior in a non-development environment. Never bypass those guards
to make a shared schema change easier.

## Prepare staging or production

Follow the [PythonAnywhere runbook](../deploy/pythonanywhere/README.md). The
essential command shape is:

```bash
NEPAL_KINGS_ENV_FILE="$HOME/.config/nepalkings/ENVIRONMENT.env" \
  "$HOME/.virtualenvs/nepalkings-ENVIRONMENT/bin/python" \
  "$HOME/releases/FULL_COMMIT_SHA/server/manage.py" \
  prepare-database
```

Required order:

1. stop the environment's background task and web app;
2. create and catalog-validate a secret-safe PostgreSQL backup;
3. install the release's pinned dependencies;
4. point private release metadata at the candidate;
5. run `prepare-database`;
6. verify `/readyz` reports the expected schema before reopening traffic.

Production remains in maintenance until the worker, schema, logs, and required
smokes pass.

## Backups and recovery

- Pre-deployment backups use `scripts/create_postgres_backup.py`.
- Daily provider-side production backups use scheduled task `22971` and the
  tracked wrapper under `deploy/pythonanywhere/`.
- Encrypted off-provider copies use `scripts/encrypt_postgres_backup.py`.
- Backup success requires file mode, size, SHA-256, and `pg_restore --list`
  validation—not merely the existence of a dump file.

The complete encryption and recovery procedure is in
[operations/OFFSITE_POSTGRES_BACKUPS.md](operations/OFFSITE_POSTGRES_BACKUPS.md).
Test recovery in a disposable database before replacing live data whenever
possible.

## PostgreSQL worker coordination

The hosted AI/sweeper worker holds one environment-specific PostgreSQL advisory
lock. After a worker start or deployment, verify exactly one expected lock with:

```bash
python scripts/verify_postgres_worker.py \
  --env-file /path/to/private.env \
  --environment staging
```

Use `production` only during an approved production check. The verifier does
not print `DB_URL`.

## Common SQLite lock errors

SQLite has file-level writer coordination, so local lock errors usually mean a
second server, test process, or interactive script still owns the database.

1. Stop old local server and test processes.
2. Confirm no process is using `server/test.db`.
3. Retry the operation; do not repeatedly add sleeps around a real transaction bug.
4. Reproduce concurrency-sensitive behavior on PostgreSQL before considering it fixed.

SQLite timeout and connection settings improve local diagnostics, but they do
not make SQLite a production multi-worker database.

## Data-handling rules

- Never copy production data into staging without an explicit privacy review.
- Never commit databases, dumps, manifests containing private paths, or
  plaintext recovery material.
- Never print a complete database URL or password in a shell command, log, or issue.
- Keep smoke users clearly synthetic and remove their exact rows after the test.
- Preserve production audit records unless a documented synthetic cleanup owns them.
- Record migrations, backups, restore evidence, and release metadata without secrets.
