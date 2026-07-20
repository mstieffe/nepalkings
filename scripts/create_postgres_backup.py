#!/usr/bin/env python3
"""Create and validate a PostgreSQL custom-format backup without leaking DB_URL.

The database URL is read from a private environment file and parsed in-process.
Neither the complete URL nor the password is placed in subprocess arguments.
PostgreSQL connection fields are provided through libpq environment variables,
and all subprocess error output is redacted before it can reach the terminal.

Example:

    python scripts/create_postgres_backup.py \
      --env-file ~/.config/nepalkings/staging.env \
      --output ~/backups/postgres-staging/staging-pre-deploy.dump
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence
from urllib.parse import parse_qs, quote, unquote, urlsplit


BUFFER_SIZE = 1024 * 1024
ALLOWED_SCHEMES = {
    "postgres",
    "postgresql",
    "postgresql+psycopg",
    "postgresql+psycopg2",
}
ALLOWED_SSL_MODES = {
    "disable",
    "allow",
    "prefer",
    "require",
    "verify-ca",
    "verify-full",
}


class BackupCreationError(RuntimeError):
    """Raised when a database backup cannot be created safely."""


@dataclass(frozen=True)
class PostgresConnection:
    host: str
    port: int
    user: str
    password: str
    database: str
    sslmode: str | None
    connect_timeout: int

    def libpq_environment(self, base: Mapping[str, str]) -> dict[str, str]:
        environment = dict(base)
        # Do not pass an inherited application connection URL to child
        # processes. pg_dump receives only libpq's individual fields.
        environment.pop("DB_URL", None)
        environment.pop("DATABASE_URL", None)
        environment.update(
            {
                "PGHOST": self.host,
                "PGPORT": str(self.port),
                "PGUSER": self.user,
                "PGPASSWORD": self.password,
                "PGDATABASE": self.database,
                "PGCONNECT_TIMEOUT": str(self.connect_timeout),
            }
        )
        if self.sslmode:
            environment["PGSSLMODE"] = self.sslmode
        else:
            environment.pop("PGSSLMODE", None)
        return environment


def _private_file(path: Path) -> None:
    if not path.is_file():
        raise BackupCreationError(f"Environment file is missing: {path}")
    permissions = path.stat().st_mode & 0o777
    if permissions & 0o077:
        raise BackupCreationError(
            f"Environment file must not be group/world accessible: {path}"
        )


def _read_environment_value(path: Path, key: str) -> str:
    _private_file(path)
    matches: list[str] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise BackupCreationError(f"Could not read environment file: {path}") from exc

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:].lstrip()
        name, separator, value = stripped.partition("=")
        if separator and name.strip() == key:
            value = value.strip()
            if (
                len(value) >= 2
                and value[0] == value[-1]
                and value[0] in {"'", '"'}
            ):
                value = value[1:-1]
            matches.append(value)

    if len(matches) != 1 or not matches[0]:
        raise BackupCreationError(
            f"Environment file must contain exactly one non-empty {key} entry"
        )
    return matches[0]


def _safe_component(value: str | None, label: str) -> str:
    if not value:
        raise BackupCreationError(f"Database URL has no {label}")
    decoded = unquote(value)
    if any(character in decoded for character in ("\0", "\r", "\n")):
        raise BackupCreationError(f"Database URL has an invalid {label}")
    return decoded


def parse_postgres_url(url: str) -> PostgresConnection:
    try:
        parsed = urlsplit(url)
    except ValueError as exc:
        raise BackupCreationError("Database URL could not be parsed") from exc

    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise BackupCreationError("Database URL does not use a supported PostgreSQL scheme")
    if parsed.fragment:
        raise BackupCreationError("Database URL must not contain a fragment")

    try:
        parsed_user = parsed.username
        parsed_password = parsed.password
        parsed_host = parsed.hostname
    except ValueError as exc:
        raise BackupCreationError("Database URL has invalid authority fields") from exc
    user = _safe_component(parsed_user, "username")
    password = _safe_component(parsed_password, "password")
    host = _safe_component(parsed_host, "hostname")
    database = _safe_component(parsed.path.lstrip("/"), "database name")
    if "/" in database:
        raise BackupCreationError("Database URL has an invalid database name")
    try:
        port = parsed.port or 5432
    except ValueError as exc:
        raise BackupCreationError("Database URL has an invalid port") from exc
    if not 1 <= port <= 65535:
        raise BackupCreationError("Database URL has an invalid port")

    try:
        query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise BackupCreationError("Database URL has invalid connection options") from exc
    unsupported = set(query) - {"sslmode", "connect_timeout"}
    if unsupported:
        raise BackupCreationError("Database URL has unsupported connection options")
    if any(len(values) != 1 for values in query.values()):
        raise BackupCreationError("Database URL repeats a connection option")

    sslmode = query.get("sslmode", [None])[0]
    if sslmode is not None and sslmode not in ALLOWED_SSL_MODES:
        raise BackupCreationError("Database URL has an invalid sslmode")
    raw_timeout = query.get("connect_timeout", ["15"])[0]
    try:
        connect_timeout = int(raw_timeout)
    except ValueError as exc:
        raise BackupCreationError("Database URL has an invalid connect_timeout") from exc
    if not 1 <= connect_timeout <= 120:
        raise BackupCreationError("Database URL has an invalid connect_timeout")

    return PostgresConnection(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        sslmode=sslmode,
        connect_timeout=connect_timeout,
    )


def _redact(detail: str, secrets: Sequence[str]) -> str:
    redacted = detail
    variants: set[str] = set()
    for secret in secrets:
        if secret:
            variants.update({secret, quote(secret, safe=""), quote(secret, safe="-._~")})
    for value in sorted(variants, key=len, reverse=True):
        redacted = redacted.replace(value, "[REDACTED]")
    # Avoid dumping an unexpectedly large tool error into an operator log.
    if len(redacted) > 2000:
        redacted = f"{redacted[:2000]}…"
    return redacted


def _run_checked(
    command: Sequence[str],
    *,
    environment: Mapping[str, str],
    secrets: Sequence[str],
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            check=False,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as exc:
        raise BackupCreationError(
            f"{Path(command[0]).name} could not be started"
        ) from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise BackupCreationError(
            f"{Path(command[0]).name} failed: {_redact(detail, secrets)}"
        )
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(BUFFER_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _prepare_output(output: Path) -> None:
    if output.exists():
        raise BackupCreationError(f"Output already exists: {output}")
    existed = output.parent.exists()
    output.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if not existed:
        os.chmod(output.parent, 0o700)
    if output.parent.stat().st_mode & 0o077:
        raise BackupCreationError(
            f"Output directory must not be group/world accessible: {output.parent}"
        )


def create_backup(args: argparse.Namespace) -> int:
    env_file = args.env_file.expanduser().resolve()
    output = args.output.expanduser().resolve()
    database_url = _read_environment_value(env_file, args.db_url_key)
    connection = parse_postgres_url(database_url)
    _prepare_output(output)

    pg_dump = shutil.which(args.pg_dump)
    pg_restore = shutil.which(args.pg_restore)
    if not pg_dump:
        raise BackupCreationError(f"pg_dump executable not found: {args.pg_dump}")
    if not pg_restore:
        raise BackupCreationError(f"pg_restore executable not found: {args.pg_restore}")

    child_environment = connection.libpq_environment(os.environ)
    secrets = (database_url, connection.password)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output.parent,
        prefix=f".{output.name}.",
        suffix=".tmp",
    )
    os.close(descriptor)
    temporary_output = Path(temporary_name)
    try:
        os.chmod(temporary_output, 0o600)
        _run_checked(
            [
                pg_dump,
                "--format=custom",
                "--no-password",
                f"--file={temporary_output}",
            ],
            environment=child_environment,
            secrets=secrets,
        )
        if not temporary_output.is_file() or temporary_output.stat().st_size == 0:
            raise BackupCreationError("pg_dump produced an empty backup")
        _run_checked(
            [pg_restore, "--list", str(temporary_output)],
            environment=child_environment,
            secrets=secrets,
        )
        size = temporary_output.stat().st_size
        digest = _sha256(temporary_output)
        os.replace(temporary_output, output)
        os.chmod(output, 0o600)
        print(
            json.dumps(
                {
                    "backup": str(output),
                    "database": connection.database,
                    "sha256": digest,
                    "size_bytes": size,
                    "validated": True,
                },
                sort_keys=True,
            )
        )
        return 0
    finally:
        temporary_output.unlink(missing_ok=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--db-url-key", default="DB_URL")
    parser.add_argument("--pg-dump", default="pg_dump")
    parser.add_argument("--pg-restore", default="pg_restore")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return create_backup(args)
    except BackupCreationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception:
        # A defensive last boundary: an unexpected library/tool failure must
        # not serialize local variables containing the database URL.
        print("ERROR: unexpected backup failure (details suppressed)", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
