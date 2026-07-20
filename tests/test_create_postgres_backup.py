from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from scripts.create_postgres_backup import main, parse_postgres_url


DATABASE_URL = (
    "postgresql+psycopg://nepalkings_staging:"
    "test-secret_123@db.example.test:10371/nepalkings_staging"
)


def _private_env(tmp_path: Path, database_url: str = DATABASE_URL) -> Path:
    path = tmp_path / "staging.env"
    path.write_text(f"APP_ENV=staging\nDB_URL={database_url}\n", encoding="utf-8")
    path.chmod(0o600)
    return path


def test_parse_sqlalchemy_postgres_url_and_options() -> None:
    connection = parse_postgres_url(
        "postgresql+psycopg://role:p%40ss@db.example:10371/app"
        "?sslmode=require&connect_timeout=20"
    )

    assert connection.host == "db.example"
    assert connection.port == 10371
    assert connection.user == "role"
    assert connection.password == "p@ss"
    assert connection.database == "app"
    assert connection.sslmode == "require"
    assert connection.connect_timeout == 20


@pytest.mark.parametrize(
    "database_url",
    [
        "sqlite:///app.db",
        "postgresql+psycopg://role@db.example/app",
        "postgresql+psycopg://role:password@db.example/",
        "postgresql+psycopg://role:password@db.example/app?unknown=value",
        "postgresql+psycopg://role:password@db.example/app?sslmode=invalid",
        "postgresql+psycopg://role:password@db.example/app?broken",
    ],
)
def test_parse_rejects_incomplete_or_unsupported_urls(database_url: str) -> None:
    with pytest.raises(Exception):
        parse_postgres_url(database_url)


def test_backup_never_places_url_or_password_in_arguments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    env_file = _private_env(tmp_path)
    output_directory = tmp_path / "private-backups"
    output = output_directory / "staging.dump"
    calls: list[tuple[list[str], dict[str, str]]] = []

    def fake_which(executable: str) -> str:
        return f"/usr/bin/{executable}"

    def fake_run(
        command: list[str],
        *,
        check: bool,
        env: dict[str, str],
        stdout: int,
        stderr: int,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        assert stdout == subprocess.PIPE
        assert stderr == subprocess.PIPE
        assert text is True
        calls.append((command, env))
        if command[0].endswith("pg_dump"):
            output_argument = next(
                argument for argument in command if argument.startswith("--file=")
            )
            Path(output_argument.removeprefix("--file=")).write_bytes(
                b"PGDMP-test-backup"
            )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("scripts.create_postgres_backup.shutil.which", fake_which)
    monkeypatch.setattr("scripts.create_postgres_backup.subprocess.run", fake_run)
    monkeypatch.setenv("DB_URL", "must-not-be-inherited")
    monkeypatch.setenv("DATABASE_URL", "must-not-be-inherited-either")

    assert (
        main(
            [
                "--env-file",
                str(env_file),
                "--output",
                str(output),
            ]
        )
        == 0
    )

    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["validated"] is True
    assert output.read_bytes() == b"PGDMP-test-backup"
    assert output.stat().st_mode & 0o777 == 0o600
    assert output_directory.stat().st_mode & 0o777 == 0o700
    assert len(calls) == 2
    for command, environment in calls:
        assert DATABASE_URL not in command
        assert "test-secret_123" not in command
        assert "DB_URL" not in environment
        assert "DATABASE_URL" not in environment
        assert environment["PGPASSWORD"] == "test-secret_123"
        assert environment["PGHOST"] == "db.example.test"
        assert environment["PGUSER"] == "nepalkings_staging"
        assert environment["PGDATABASE"] == "nepalkings_staging"


def test_subprocess_error_redacts_raw_and_encoded_secrets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    database_url = (
        "postgresql+psycopg://role:p%40ssword@db.example.test:5432/application"
    )
    env_file = _private_env(tmp_path, database_url)
    output = tmp_path / "backups" / "failed.dump"

    monkeypatch.setattr(
        "scripts.create_postgres_backup.shutil.which",
        lambda executable: f"/usr/bin/{executable}",
    )

    def fake_run(
        command: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            1,
            "",
            f"failed for p@ssword, p%40ssword, and {database_url}",
        )

    monkeypatch.setattr("scripts.create_postgres_backup.subprocess.run", fake_run)

    assert (
        main(
            [
                "--env-file",
                str(env_file),
                "--output",
                str(output),
            ]
        )
        == 1
    )

    captured = capsys.readouterr()
    assert "p@ssword" not in captured.err
    assert "p%40ssword" not in captured.err
    assert database_url not in captured.err
    assert "[REDACTED]" in captured.err
    assert not output.exists()


def test_refuses_environment_file_with_broad_permissions(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    env_file = _private_env(tmp_path)
    env_file.chmod(0o644)

    assert (
        main(
            [
                "--env-file",
                str(env_file),
                "--output",
                str(tmp_path / "backup.dump"),
            ]
        )
        == 1
    )

    assert "group/world accessible" in capsys.readouterr().err
