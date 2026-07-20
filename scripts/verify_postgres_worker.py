#!/usr/bin/env python3
"""Verify one environment's PostgreSQL worker leadership without exposing DB_URL."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Callable, Sequence

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url


WORKER_LOCK_NAMESPACE = 20044


class WorkerVerificationError(RuntimeError):
    """Raised when worker leadership does not match the deployment contract."""


def environment_lock_key(environment: str) -> int:
    digest = hashlib.sha256(environment.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") & 0x7FFFFFFF


def _private_database_url(path: Path) -> str:
    if not path.is_file():
        raise WorkerVerificationError(f"Environment file is missing: {path}")
    if path.stat().st_mode & 0o077:
        raise WorkerVerificationError("Environment file is group/world accessible")
    raw_url = dotenv_values(path).get("DB_URL")
    if not raw_url:
        raise WorkerVerificationError("Environment file has no DB_URL")
    try:
        parsed = make_url(raw_url)
    except Exception as exc:
        raise WorkerVerificationError("DB_URL could not be parsed") from exc
    if not parsed.drivername.startswith("postgresql") or not parsed.password:
        raise WorkerVerificationError("DB_URL is not a complete PostgreSQL URL")
    return raw_url


def verify_worker(
    *,
    env_file: Path,
    environment: str,
    engine_factory: Callable[..., Engine] = create_engine,
) -> dict[str, object]:
    raw_url = _private_database_url(env_file)
    lock_key = environment_lock_key(environment)
    engine = engine_factory(raw_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            database, role = connection.execute(
                text("SELECT current_database(), current_user")
            ).one()
            lock_count, role_lock_count = connection.execute(
                text(
                    "SELECT count(*), "
                    "count(*) FILTER (WHERE activity.usename = current_user) "
                    "FROM pg_locks AS locks "
                    "LEFT JOIN pg_stat_activity AS activity "
                    "ON activity.pid = locks.pid "
                    "WHERE locks.locktype = 'advisory' "
                    "AND locks.classid = :namespace "
                    "AND locks.objid = :environment_key "
                    "AND locks.granted"
                ),
                {
                    "namespace": WORKER_LOCK_NAMESPACE,
                    "environment_key": lock_key,
                },
            ).one()
    except Exception as exc:
        raise WorkerVerificationError(
            "PostgreSQL worker verification failed (details suppressed)"
        ) from exc
    finally:
        engine.dispose()

    if int(lock_count) != 1 or int(role_lock_count) != 1:
        raise WorkerVerificationError(
            "Expected exactly one worker lock owned by the environment role"
        )
    return {
        "database": database,
        "environment": environment,
        "environment_key": lock_key,
        "lock_count": int(lock_count),
        "namespace": WORKER_LOCK_NAMESPACE,
        "role": role,
        "role_lock_count": int(role_lock_count),
        "verified": True,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--environment", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = verify_worker(
            env_file=args.env_file.expanduser().resolve(),
            environment=args.environment,
        )
    except WorkerVerificationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception:
        print(
            "ERROR: unexpected worker verification failure (details suppressed)",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
