# Database Management

## Schema Changes: Migrations, Not Resets

Schema changes ship through `server/migration_runner.py` and apply
**automatically at server startup** (locally and on PythonAnywhere reload):

- `db.create_all()` creates tables for brand-new models.
- The ordered `MIGRATIONS` list handles everything else (added columns,
  backfills). Applied versions are recorded in the `schema_version` table,
  so each migration runs exactly once per database.

### Adding a migration

1. Append `(version, description, callable)` to `MIGRATIONS` in
   `server/migration_runner.py`, using the next integer version.
2. Make the callable idempotent (check before ALTER — see
   `_add_column_if_missing()` and the `ensure_*` helpers it wraps).
3. Never renumber, edit, or remove an entry that has shipped.
4. Deploy normally with `./deploy_server.sh` — the migration runs when the
   web app reloads.

### Production data safety

- `./deploy_server.sh` automatically downloads a timestamped snapshot of the
  live database into `backups/` before every deploy (skip with
  `--no-backup`, not recommended). The 14 most recent snapshots are kept.
- Roll back with `scripts/restore_db_backup.sh backups/<file>.db` — this
  overwrites the live DB and reloads the web app.
- **Never reset the production database.** `server/RESET_DATABASE.sh`
  refuses to run when `FLASK_ENV` looks like production and requires a
  typed `RESET` confirmation.

## Resetting a Local Development Database

For local iteration a reset is often the quickest path:

```bash
cd server
bash RESET_DATABASE.sh        # asks for confirmation, then drops + recreates
```

or simply delete the SQLite file:

```bash
cd server
killall python3   # kill any running server first
rm -f test.db
python3 server.py # tables auto-create, migrations stamp themselves
```

## Local Gameplay Test Account

For development testing, create or refresh a high-gold human account with the
maintenance helper instead of adding a public server endpoint or committing a
plaintext password.

From the repository root:
```bash
NK_TEST_ACCOUNT_PASSWORD='merkeltonien' .venv/bin/python scripts/debug/upsert_test_account.py --username KingMerk --gold 100000
```

The helper is idempotent: rerunning it updates `KingMerk` back to `100000` gold
and hashes the password through the normal `User` model path. By default it
refuses to run when `FLASK_ENV`/`ENV` is not a development-style environment;
pass `--allow-non-dev` only if you intentionally need to update a non-local
database.

## Why Do SQLite Lock Errors Occur?

SQLite database locking errors typically happen because:

1. **Concurrent Access**: SQLite uses file-level locking. When multiple processes or threads try to access the database simultaneously, you get lock errors.

2. **Incomplete Transactions**: If a process crashes or exits while holding a lock, that lock may persist until the file handle is released.

3. **Drop/Create Operations**: When you `db.drop_all()` while the database is active:
   - The old Flask process may still have the database open
   - The database file is being accessed while trying to delete it
   - SQLite needs exclusive access to drop tables

4. **Hot Reloading**: Flask's debug mode auto-restarts the server, but the old process may not release the database immediately.

### Solutions We Implemented

1. **SQLite Configuration** (in `server.py`):
   ```python
   'connect_args': {
       'timeout': 30,  # Wait up to 30 seconds for lock
       'check_same_thread': False  # Allow multi-threaded access
   }
   ```

2. **Connection Pooling**:
   - `pool_pre_ping`: Verifies connections before use
   - `pool_recycle`: Refreshes connections every 300 seconds

3. **Startup Migrations**: schema changes apply in-place at startup via
   `server/migration_runner.py`; local resets remain available for
   development convenience only.

### Best Practices

- **Development**: a local reset is fine when iterating on models; ship the
  matching migration in the same change.
- **Production**: never reset — migrations run on reload, and every deploy
  snapshots the DB into `backups/` first.
- **Kill Old Processes** before a local reset:
  ```bash
  killall python3
  # Then: bash RESET_DATABASE.sh
  ```
