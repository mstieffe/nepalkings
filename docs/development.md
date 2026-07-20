# Development Guide

This guide covers the normal local workflow. Production deployment is separate
and documented in [deployment.md](deployment.md).

## Prerequisites

- Python 3.11
- Git
- A shell capable of running the repository scripts
- SDL-compatible desktop environment for the Pygame client

Python 3.11 is declared in [`.python-version`](../.python-version) and used by
the test and desktop-build workflows. The browser build uses Python 3.12 in CI
because that is the tested pygbag build environment.

## Set up the environment

### macOS or Linux

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r server/requirements.txt
```

### Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt -r server/requirements.txt
```

The root requirements support tests and local client execution. The server
requirements add SQLAlchemy, PostgreSQL, CORS, rate limiting, and production
configuration dependencies. Production deploys install only the pinned server
requirements into the production virtual environment.

## Run locally

The normal development command is:

```bash
./run_local.sh
```

It starts the Flask API on `http://localhost:5000`, waits for it to respond,
launches the client against that address, and stops the server when the client
exits. Pass `-s` to open Settings before entering the game:

```bash
./run_local.sh -s
```

Local development defaults to `server/test.db` through SQLAlchemy's SQLite
configuration. Startup creates missing tables, applies migrations, seeds the
map, and starts the local in-process background service.

### Run client and server separately

Terminal 1:

```bash
cd server
../.venv/bin/python server.py
```

Terminal 2:

```bash
cd nepal_kings
../.venv/bin/python main.py --server-url http://localhost:5000
```

### Use a hosted environment

Use production for a normal remote-client smoke:

```bash
./run_remote.sh
```

Use staging only for intentional integration tests:

```bash
cd nepal_kings
../.venv/bin/python main.py \
  --server-url https://nepalkingz.eu.pythonanywhere.com
```

Hosted accounts and data are isolated. See [environments.md](environments.md)
before switching a client between them.

## Client options and local state

```text
--settings, -s             Open Settings before launching
--pick-resolution, -r      Alias for opening Settings
--server-url URL           Override the server for this process
```

The desktop client stores resolution, server selection, and preferences in:

```text
~/.nepalkings/resolution.json
```

Logs are written under `~/.nepalkings/`. Set `NK_DEBUG=1` for more verbose
client diagnostics. Never paste tokens or private player content into an issue.

## Run tests

Run the complete suite from the repository root:

```bash
.venv/bin/python -m pytest -q
```

Useful focused commands include:

```bash
.venv/bin/python -m pytest -q tests/client
.venv/bin/python -m pytest -q tests/server
.venv/bin/python -m pytest -q tests/server/test_ops.py
```

GitHub Actions additionally runs a PostgreSQL service matrix, dependency audit,
and secret scan. A local SQLite pass does not replace the PostgreSQL CI job for
database or concurrency changes.

## Configuration

Server configuration comes from environment variables documented in
[`.env.example`](../.env.example). Local development has safe defaults, so a
populated `.env` file is not required for the standard SQLite workflow.

Production and staging use private environment files outside the repository.
Never commit `.env`, database URLs, API tokens, signing keys, or passwords.

Important boundaries:

- `APP_ENVIRONMENT` selects development, staging, or production safety policy.
- `DB_URL` defaults to local SQLite; non-development environments require an
  explicit PostgreSQL URL unless the legacy fallback is deliberately enabled.
- `STARTUP_MAINTENANCE_ENABLED` is convenient locally but disabled in hosted
  environments, where database preparation is an explicit deploy step.
- `BACKGROUND_SERVICES_ENABLED` is local-only; hosted AI and sweep work runs in
  a dedicated always-on task.

## Database changes

Follow [database_management.md](database_management.md). In short:

1. Add an ordered, idempotent migration in `server/migration_runner.py`.
2. Add SQLite and PostgreSQL coverage where the SQL or transaction behavior can differ.
3. Run the full suite.
4. Back up and run `manage.py prepare-database` before a hosted WSGI reload.

Do not reset a shared or production database to avoid writing a migration.

## Browser and desktop builds

Release builds, bundle budgets, itch.io packaging, and installer commands live
in [distribution.md](distribution.md). Build scripts use staging directories;
do not manually optimize or overwrite source assets for a browser release.

## Code organization

```text
nepal_kings/game/screens/       Client screens and navigation
nepal_kings/game/components/    Reusable UI and gameplay presentation
nepal_kings/utils/              HTTP, authentication, polling, and preferences
server/routes/                  HTTP transport and authorization boundaries
server/game_service/            Reusable game-domain operations
server/models.py                SQLAlchemy persistence model
server/migration_runner.py      Ordered schema migrations
server/startup.py               Explicit database preparation and local services
tests/client/                   Client contracts and UI behavior
tests/server/                   API, rules, state, and persistence behavior
```

Keep route handlers thin where practical, preserve server authority over game
legality, and add regression tests at the serialization or transition boundary
where a bug occurred.

## Documentation with code changes

- Player-visible rule changes: update the in-game Guide and [gameplay.md](gameplay.md).
- New operational behavior: update the authoritative runbook in the same commit.
- Changed client routing: update [environments.md](environments.md).
- New scripts: update [scripts/README.md](../scripts/README.md).
- Design work: add or update a status-marked file under [plans/](plans/README.md).

See [docs/README.md](README.md) for documentation ownership and naming rules.
