# Encrypted Off-Provider PostgreSQL Backups

Last updated: 2026-07-20

Status: the provider-side daily backup is active and the first production
archive was encrypted and round-trip verified off-provider. A second
independent destination and automated off-provider rotation remain optional
beta follow-ups.

## Recovery contract

- PythonAnywhere keeps the live database and fourteen validated daily
  custom-format dumps, plus separately named pre-deployment recovery dumps.
- Keep at least one recently verified encrypted production copy outside
  PythonAnywhere and refresh it before materially expanding the beta or making
  a high-risk data change.
- Only a PostgreSQL custom-format archive that passes `pg_restore --list` is
  eligible for encryption.
- The downloaded plaintext must match the provider-side SHA-256.
- The encrypted archive must decrypt to that same SHA-256 before the local
  plaintext is removed.
- The encrypted archive and its manifest move together.
- No database password, complete `DB_URL`, private key, or plaintext dump may
  enter Git, chat, CI artifacts, or general cloud storage.

The repository ignores `backups/`. This prevents an accidental commit; it does
not make that directory a complete backup strategy.

## Encryption identity

The dedicated recovery identity is outside the repository:

```text
~/.config/nepalkings/backup-encryption/
├── private.pem
└── recipient-cert.pem
```

Required permissions:

```text
backup-encryption/  700
private.pem         600
recipient-cert.pem  644
```

Current recipient certificate SHA-256 fingerprint:

```text
94:A2:8B:D1:DC:85:7E:B2:18:D9:C4:5F:64:74:FE:94:
9C:EC:85:8A:8C:25:A6:11:58:54:4A:81:6F:29:A9:C3
```

Confirm the fingerprint without exposing the private key:

```bash
openssl x509 \
  -in ~/.config/nepalkings/backup-encryption/recipient-cert.pem \
  -noout -fingerprint -sha256
```

The private key is intentionally readable only by the local account so
verification can be automated. Store one separate protected recovery copy in
a password manager or offline encrypted medium. Losing every copy of
`private.pem` makes every encrypted archive unrecoverable. Possession of the
recipient certificate alone cannot decrypt a backup.

## Backup procedure

### 1. Create and validate the provider-side dump

Use the repository backup helper to create a PostgreSQL custom-format archive.
It reads the private environment file, supplies individual connection fields
to libpq, validates the resulting archive, and never places the password or
complete `DB_URL` in subprocess arguments:

```bash
/home/nepalkingz/.virtualenvs/nepalkings-production/bin/python \
  /home/nepalkingz/ops/CURRENT_OPS_RELEASE/scripts/create_postgres_backup.py \
  --env-file /home/nepalkingz/.config/nepalkings/production.env \
  --output \
  /home/nepalkingz/backups/postgres-production/production-YYYYMMDDTHHMMSSZ.dump
```

The application releases under `~/releases/` are intentionally server-only
and do not contain operational scripts. Upload the helper from the same
committed candidate into a private, versioned `~/ops/FULL_COMMIT_SHA/scripts/`
directory, verify its SHA-256 against the local repository copy, and use that
immutable ops path. The currently verified ops release is
`3952bb4611cb9a708365e607f29a0e37e7e856a5`.

Production archives belong in:

```text
/home/nepalkingz/backups/postgres-production/
```

The helper refuses broadly readable environment/output paths, writes the dump
atomically with mode `600`, and runs `pg_restore --list` before publishing it.
Before download, record only its path, size, mode, and SHA-256. An operator may
repeat the catalog check on PythonAnywhere:

```bash
pg_restore --list /home/nepalkingz/backups/postgres-production/NAME.dump \
  >/dev/null
sha256sum /home/nepalkingz/backups/postgres-production/NAME.dump
stat -c '%s %a %n' \
  /home/nepalkingz/backups/postgres-production/NAME.dump
```

The archive and directory must be mode `600` and `700` respectively.

### 2. Download to a protected temporary file

Use the pinned PythonAnywhere host key and the dedicated SSH identity:

```bash
scp \
  -i ~/.ssh/nepalkings_pythonanywhere_eu \
  -o UserKnownHostsFile=/tmp/nepalkings_pa_eu_known_hosts \
  nepalkingz@ssh.eu.pythonanywhere.com:\
/home/nepalkingz/backups/postgres-production/NAME.dump \
  /private/tmp/NAME.dump
chmod 600 /private/tmp/NAME.dump
shasum -a 256 /private/tmp/NAME.dump
```

Stop if the local hash differs from the provider-side hash.

### 3. Encrypt, round-trip verify, and remove plaintext

```bash
.venv/bin/python scripts/encrypt_postgres_backup.py create \
  /private/tmp/NAME.dump \
  backups/off-provider/production/NAME.dump.cms \
  --recipient-cert \
  ~/.config/nepalkings/backup-encryption/recipient-cert.pem \
  --private-key \
  ~/.config/nepalkings/backup-encryption/private.pem \
  --expected-sha256 PROVIDER_PLAINTEXT_SHA256 \
  --source-label \
  /home/nepalkingz/backups/postgres-production/NAME.dump \
  --remove-source-after-verify
```

The tool:

1. verifies the downloaded plaintext hash;
2. encrypts it as CMS EnvelopedData with AES-256-GCM;
3. decrypts it to a hash stream without creating another plaintext file;
4. refuses to publish or delete the source if the round trip differs;
5. writes the archive and JSON manifest with mode `600`;
6. removes the downloaded plaintext only after every check passes.

Re-verify an existing archive at any time:

```bash
.venv/bin/python scripts/encrypt_postgres_backup.py verify \
  backups/off-provider/production/NAME.dump.cms \
  --recipient-cert \
  ~/.config/nepalkings/backup-encryption/recipient-cert.pem \
  --private-key \
  ~/.config/nepalkings/backup-encryption/private.pem \
  --expected-sha256 PROVIDER_PLAINTEXT_SHA256
```

### 4. Replicate the encrypted pair

Copy both files to an access-controlled store outside PythonAnywhere and
outside the development Mac:

```text
NAME.dump.cms
NAME.dump.cms.manifest.json
```

Re-download a sample from that store and run the verification command. An
upload alone is not a completed backup.

Current beta policy:

- create and validate a provider-side production dump every day;
- retain fourteen daily provider archives without rotating separately named
  pre-deployment recovery dumps;
- refresh the encrypted off-provider copy before each material beta expansion
  and high-risk data change;
- verify every copied archive and manifest;
- perform a complete restore drill before a major beta expansion and after a
  recovery-tool change.

Daily off-provider replication, seven-daily/four-weekly/six-monthly rotation,
backup-age alerts, and a second independent store are tracked as optional
hardening. Revise retention once real database growth and player activity make
the trade-off measurable.

## Recovery procedure

Do not overwrite the live database as the first recovery test. Restore into a
disposable database first whenever the provider incident allows it.

1. Put production in maintenance.
2. Stop production always-on task `35394`.
3. Disable production web app `56868`.
4. Download the encrypted archive and manifest from independent storage.
5. Verify the encrypted SHA-256 against the manifest.
6. Decrypt to a mode-`600` temporary file:

   ```bash
   umask 077
   openssl cms -decrypt -binary -inform DER \
     -in NAME.dump.cms \
     -recip \
     ~/.config/nepalkings/backup-encryption/recipient-cert.pem \
     -inkey \
     ~/.config/nepalkings/backup-encryption/private.pem \
     -out /private/tmp/NAME.dump
   ```

7. Verify the plaintext SHA-256 and `pg_restore --list`.
8. Follow the transactional PostgreSQL restore procedure in
   `PRODUCTION_DEPLOYMENT_2026-07-19.md`.
9. Run `manage.py prepare-database`, validate schema/domain counts, then start
   the worker and web app.
10. Verify health, readiness, maintenance enforcement, the correct database
    advisory lock, and staging isolation.
11. Remove the recovery plaintext.

Never restore a production archive into staging without an explicit
data-handling review; even encrypted backups may contain player personal data
after launch.

## First verified production copy

Provider source:

```text
/home/nepalkingz/backups/postgres-production/
production-pre-conquer-smoke-20260719T214323Z.dump
```

Evidence:

| Check | Result |
|---|---|
| Provider archive | custom-format catalog valid; mode `600`; 198,108 bytes |
| Plaintext SHA-256 | `a6c87778def031e4c2b0d97aef45ce5c01c4ff9a0825dcad32993cfb4768e8a0` |
| Encrypted archive | `backups/off-provider/production/production-20260719T214323Z.dump.cms` |
| Encrypted SHA-256 | `23d5ed6787756ddf9e5e3224df17ba1941348e71f37b5921efd3a05d9cd8915d` |
| Encrypted size/mode | 198,820 bytes; `600` |
| Encryption | CMS EnvelopedData with AES-256-GCM |
| Round-trip verification | passed independently twice |
| Local plaintext cleanup | passed |

The encrypted archive currently exists on the development Mac, outside
PythonAnywhere and outside source control. Replication to a second independent
store and automated off-provider rotation remain optional follow-up work; the
provider-side daily schedule is active.
