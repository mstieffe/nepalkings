# PythonAnywhere EU production layout

The paid PythonAnywhere EU account is the selected launch host. Keep the
static client on GitHub Pages. Use PythonAnywhere's managed WSGI workers; this
deployment does not run Gunicorn.

The existing free-plan-compatible deployment is preserved in:

```text
backup/pythonanywhere-free-eu-2026-07-19
```

Do not point production at that branch. It exists only as a tested rollback
path to the single-worker SQLite layout.

## Environment layout

Use two isolated web apps and databases:

| Environment | Web app | Database | Secret file |
|---|---|---|---|
| staging | staging custom domain | `nepalkings_staging` | `~/.config/nepalkings/staging.env` |
| production | canonical API domain | `nepalkings_prod` | `~/.config/nepalkings/production.env` |

The current `nepalkingz.eu.pythonanywhere.com` app may remain the temporary
staging app until custom DNS is ready. A second PythonAnywhere web app needs a
custom domain.

## 1. Create PostgreSQL databases and least-privilege users

Enable the PostgreSQL add-on and set the PostgreSQL administrator password on
the PythonAnywhere **Databases** tab. Open a PostgreSQL console and create
separate owners:

```sql
CREATE USER nepalkings_staging WITH PASSWORD 'STAGING_RANDOM_PASSWORD';
CREATE DATABASE nepalkings_staging OWNER nepalkings_staging;

CREATE USER nepalkings_prod WITH PASSWORD 'PRODUCTION_RANDOM_PASSWORD';
CREATE DATABASE nepalkings_prod OWNER nepalkings_prod;
```

Use different generated passwords. Do not use the PostgreSQL superuser from
the application. Record the host and port shown on the Databases tab.

If a password contains URL-special characters, URL-encode it before placing it
in `DB_URL`:

```bash
python3.11 -c \
  "from urllib.parse import quote; print(quote(input('Password: '), safe=''))"
```

## 2. Create private environment files

In a PythonAnywhere Bash console:

```bash
mkdir -p ~/.config/nepalkings
chmod 700 ~/.config/nepalkings
cp ~/nepalkings/deploy/pythonanywhere/staging.env.example \
  ~/.config/nepalkings/staging.env
cp ~/nepalkings/deploy/pythonanywhere/production.env.example \
  ~/.config/nepalkings/production.env
chmod 600 ~/.config/nepalkings/*.env
```

Edit both copies and replace every `CHANGE_ME`. Generate each signing key
independently:

```bash
python3.11 -c "import secrets; print(secrets.token_hex(32))"
```

The private files stay outside the repository and outside the API deploy
upload set.

## 3. Prepare the Python 3.11 virtual environment

```bash
python3.11 -m venv ~/.virtualenvs/nepalkings
~/.virtualenvs/nepalkings/bin/python -m pip install --upgrade pip
~/.virtualenvs/nepalkings/bin/python -m pip install \
  -r ~/nepalkings/server/requirements.txt
```

Package installation is a deploy step. It must never happen during a web
worker import.

## 4. Prepare a database explicitly

Run this before the first WSGI reload and after every release that contains a
schema migration:

```bash
cd ~/nepalkings/server
NEPAL_KINGS_ENV_FILE="$HOME/.config/nepalkings/staging.env" \
  ~/.virtualenvs/nepalkings/bin/python manage.py prepare-database
```

Use `production.env` only inside an approved production deployment window.
The command is idempotent, but it may perform data migrations and
reconciliation. Back up production before running it.

## 5. Configure each web app

In the PythonAnywhere Web tab:

1. Select manual configuration with Python 3.11.
2. Set source code and working directory to
   `/home/nepalkingz/nepalkings/server`.
3. Set the virtualenv to the environment-specific path, for example
   `/home/nepalkingz/.virtualenvs/nepalkings-staging`.
4. Copy `wsgi.py.example` into the provider WSGI file and set the username and
   environment, release SHA, and immutable release directory.
5. Enable **Force HTTPS**.
6. Reload only after `prepare-database` succeeds.

Keep `load_dotenv(ENV_FILE, override=True)` in the provider WSGI file.
PythonAnywhere's WSGI-file touch is a soft reload and may otherwise retain
stale values such as `RELEASE_SHA` or `MAINTENANCE_MODE` from the existing
uWSGI master.

Check:

```bash
curl -fsS https://API_DOMAIN/healthz
curl -fsS https://API_DOMAIN/readyz
```

`/healthz` proves that a worker can import and answer without touching the
database. `/readyz` additionally requires a reachable database at the current
schema version.

## 6. Configure the always-on background worker

Web workers must keep `AI_ENABLED=False` and
`BACKGROUND_SERVICES_ENABLED=False`. This prevents PythonAnywhere's multiple
WSGI processes from starting duplicate AI threads. Create exactly one
always-on task per environment:

```bash
NEPAL_KINGS_ENV_FILE="$HOME/.config/nepalkings/staging.env" \
AI_ENABLED=True \
"$HOME/.virtualenvs/nepalkings-staging/bin/python" \
"$HOME/releases/RELEASE_SHA/server/manage.py" run-worker
```

Use the production environment file, production virtualenv, and approved
production release for the production task. The worker has an
environment-specific lifetime lock, polls for pending AI turns, and owns the
stuck-game sweep. A duplicate task refuses to start.

The worker holds environment-specific PostgreSQL advisory-lock leadership, so
a duplicate task refuses to start and a crashed task releases leadership with
its database connection. After every deployment, update the always-on task
command to the immutable release directory and restart it before disabling
maintenance mode.

## Deploy order

1. Confirm the target branch, clean worktree, and immutable commit SHA.
2. Take and verify a PostgreSQL backup.
3. Upload the server-only release.
4. Install the pinned requirements.
5. Set `RELEASE_SHA` in the target private environment file.
6. Run `manage.py prepare-database`.
7. Update and restart the environment's always-on worker.
8. Reload the target web app.
9. Check `/healthz`, `/readyz`, legal versions, invalid login JSON, and one
   authenticated read.
10. Watch error and access logs before promoting the client.

## SQLite-to-PostgreSQL cutover

Never import the live SQLite file in place. Work from a verified backup copy:

1. Set `MAINTENANCE_MODE=True` in the currently live environment and reload.
2. Confirm gameplay/auth calls return JSON `503` while `/healthz`, `/readyz`,
   and `/legal/versions` remain available.
3. Take a final SQLite backup and run `PRAGMA integrity_check`.
4. Copy the backup to a disposable working file.
5. Point `DB_URL` at that working copy and run
   `manage.py prepare-database`; this upgrades the copy to the current schema
   and performs the approved reconciliation.
6. Create an empty target PostgreSQL database.
7. Open an SSH tunnel if running the importer from the local Mac, then set
   `TARGET_DATABASE_URL` to the tunnel URL.
8. Run:

   ```bash
   TARGET_DATABASE_URL='postgresql+psycopg://...' \
     .venv/bin/python scripts/migrate_sqlite_to_postgres.py \
       --source /path/to/prepared-working-copy.db
   ```

The importer refuses a stale or corrupt source, a nonempty target, mismatched
tables/columns, row-count drift, or any orphaned declared foreign key. It
preserves IDs, restores nullable cyclic references, resets PostgreSQL
sequences, and reports key domain counts.

After the import:

1. Point the staging private environment at PostgreSQL.
2. Run `manage.py prepare-database` against PostgreSQL.
3. Reload and require `/readyz` to report PostgreSQL and schema readiness.
4. Validate collections, open games, configurations, kingdoms, region
   champions, 4,800 lands, and owned-land counts against the import report.
5. Keep maintenance mode enabled until authenticated smoke tests pass.
6. Rehearse this complete process twice before the production cutover.

## Application rollback

An application rollback must not automatically restore the database:

1. Select the last compatible release commit.
2. Upload that server release.
3. Install its pinned requirements.
4. Confirm that its expected schema is compatible with the current database.
5. Update `RELEASE_SHA`, reload, and smoke-test.

If a migration is not backward-compatible, enter maintenance mode and follow
the database restore runbook instead. Never run
`DROP_TABLES_ON_STARTUP=True` on staging or production.

## Emergency free-plan fallback

The backup branch retains the single-worker SQLite configuration. Switching
back requires restoring the matching SQLite database, the legacy WSGI
configuration, and the free-plan worker count together. PostgreSQL data cannot
be made compatible merely by checking out the branch; export/import or the
matching pre-cutover SQLite snapshot is required.
