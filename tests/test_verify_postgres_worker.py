from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.verify_postgres_worker import (
    WorkerVerificationError,
    environment_lock_key,
    verify_worker,
)


class _Result:
    def __init__(self, row: tuple[object, ...]):
        self.row = row

    def one(self) -> tuple[object, ...]:
        return self.row


class _Connection:
    def __init__(self, lock_count: int):
        self.lock_count = lock_count
        self.calls = 0

    def __enter__(self) -> "_Connection":
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def execute(self, _statement: object, _parameters: object = None) -> _Result:
        self.calls += 1
        if self.calls == 1:
            return _Result(("nepalkings_staging", "nepalkings_staging"))
        return _Result((self.lock_count, self.lock_count))


class _Engine:
    def __init__(self, lock_count: int):
        self.connection = _Connection(lock_count)
        self.disposed = False

    def connect(self) -> _Connection:
        return self.connection

    def dispose(self) -> None:
        self.disposed = True


def _private_env(tmp_path: Path) -> Path:
    path = tmp_path / "staging.env"
    path.write_text(
        "DB_URL=postgresql+psycopg://role:password@db.example/app\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def test_environment_lock_keys_match_deployed_contract() -> None:
    assert environment_lock_key("staging") == 1763288915
    assert environment_lock_key("production") == 730732783


def test_verify_worker_requires_one_role_owned_lock(tmp_path: Path) -> None:
    env_file = _private_env(tmp_path)
    engine = _Engine(1)

    result = verify_worker(
        env_file=env_file,
        environment="staging",
        engine_factory=lambda *_args, **_kwargs: engine,
    )

    assert result == {
        "database": "nepalkings_staging",
        "environment": "staging",
        "environment_key": 1763288915,
        "lock_count": 1,
        "namespace": 20044,
        "role": "nepalkings_staging",
        "role_lock_count": 1,
        "verified": True,
    }
    assert engine.disposed is True


def test_verify_worker_rejects_duplicate_or_missing_leader(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    env_file = _private_env(tmp_path)
    url = env_file.read_text(encoding="utf-8").strip().partition("=")[2]
    engine = _Engine(2)

    with pytest.raises(WorkerVerificationError):
        verify_worker(
            env_file=env_file,
            environment="staging",
            engine_factory=lambda *_args, **_kwargs: engine,
        )

    assert url not in capsys.readouterr().err
