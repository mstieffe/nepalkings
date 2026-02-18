# Database Management

## Dropping Tables on Startup

By default, the server **does NOT drop tables** on startup to preserve your data.

### When to Reset the Database

You should drop and recreate tables when:
- You've added new columns to existing models
- You've changed data types in models
- You've added new tables/models
- You're experiencing database corruption

### How to Reset the Database

**Option 1: Using the helper script (Recommended)**
```bash
cd server
bash RESET_DATABASE.sh
```

**Option 2: Setting environment variable**
```bash
cd server
DROP_TABLES_ON_STARTUP=True python3 server.py
```

**Option 3: Manually editing server_settings.py**
```python
# In server_settings.py, temporarily change:
DROP_TABLES_ON_STARTUP = True  # Change this line
```
Then start the server normally. **Remember to change it back to False afterwards!**

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

3. **Optional Drop**: Only drop tables when explicitly requested via `DROP_TABLES_ON_STARTUP`

### Best Practices

- **Development**: Use `DROP_TABLES_ON_STARTUP=True` when testing schema changes
- **Production**: Always set to `False` to preserve data
- **Kill Old Processes**: Before resetting database:
  ```bash
  killall python3
  # Then start server with DROP_TABLES_ON_STARTUP=True
  ```

## Alternative: Manual Database Reset

If you want complete control, you can manually delete the database file:
```bash
cd server
killall python3  # Kill any running server
rm -f test.db    # Delete the database file
python3 server.py  # Start fresh (tables auto-create)
```

**Note**: This is cleaner than dropping tables because there's no lock contention.
