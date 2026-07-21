from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts import deploy_pythonanywhere_eu as deploy


SHA = "a" * 40
ARCHIVE_SHA = "b" * 64


class FakeClient:
    user = "nepalkingz"

    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.files: dict[str, bytes] = {}

    def get_file(self, path: str) -> bytes | None:
        self.calls.append(("get_file", path))
        return self.files.get(path, b"")

    def set_task(
        self,
        task_id: int,
        *,
        enabled: bool,
        command: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append(("set_task", task_id, enabled, command))
        return {"id": task_id, "enabled": enabled, "command": command}

    def disable_web(self, environment: deploy.Environment) -> None:
        self.calls.append(("disable_web", environment.name))

    def enable_web(self, environment: deploy.Environment) -> None:
        self.calls.append(("enable_web", environment.name))

    def reload_web(self, environment: deploy.Environment) -> None:
        self.calls.append(("reload_web", environment.name))

    def wait_task_state(self, task_id: int, state: str) -> dict[str, Any]:
        self.calls.append(("wait_task_state", task_id, state))
        return {"id": task_id, "state": state}

    def wait_marker(
        self,
        ready_path: str,
        failed_path: str | None,
        *,
        timeout_seconds: float = 300,
    ) -> bytes:
        self.calls.append(
            ("wait_marker", ready_path, failed_path, timeout_seconds)
        )
        return b""

    def point_web(self, environment: deploy.Environment, sha: str) -> None:
        self.calls.append(("point_web", environment.name, sha))


def _patch_verifiers(monkeypatch: pytest.MonkeyPatch, events: list[Any]) -> None:
    monkeypatch.setattr(deploy, "_summarize_remote_log", lambda *_args: None)
    monkeypatch.setattr(
        deploy,
        "_run_probe",
        lambda environment, sha: events.append(("probe", environment.name, sha)),
    )
    monkeypatch.setattr(
        deploy,
        "_check_login_contract",
        lambda environment, expected_status, browser_origin: events.append(
            ("login", environment.name, expected_status, browser_origin)
        ),
    )
    monkeypatch.setattr(
        deploy,
        "_authenticated_read",
        lambda environment, credentials, allow_missing: events.append(
            ("auth_read", environment.name, credentials, allow_missing)
        ),
    )
    monkeypatch.setattr(
        deploy,
        "_canonicalize_worker",
        lambda client, environment, sha: events.append(
            ("canonical", environment.name, sha)
        ),
    )


def test_production_deploy_stays_in_maintenance_until_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient()
    events: list[Any] = []
    _patch_verifiers(monkeypatch, events)

    deploy._deploy_environment(
        client,
        deploy.ENVIRONMENTS["production"],
        sha=SHA,
        archive_sha256=ARCHIVE_SHA,
        browser_origin=deploy.DEFAULT_BROWSER_ORIGIN,
        smoke_credentials=None,
        allow_missing_authenticated_read=True,
        conquer_smoke=False,
    )

    login_events = [event for event in events if event[0] == "login"]
    assert [event[2] for event in login_events] == [503, 401]
    assert [event[0] for event in events].count("probe") == 2
    assert ("canonical", "production", SHA) in events

    finalizer = [
        call
        for call in client.calls
        if call[0] == "set_task"
        and call[3]
        and "finalize-production" in call[3]
    ]
    assert len(finalizer) == 1
    assert any(
        call[0] == "wait_marker"
        and call[1].endswith("production-finalize.ready")
        and call[2].endswith("production-finalize.failed")
        for call in client.calls
    )
    assert client.calls.count(("reload_web", "production")) == 2


def test_staging_failure_disables_temporary_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeClient()
    monkeypatch.setattr(deploy, "_summarize_remote_log", lambda *_args: None)

    def fail_marker(*_args, **_kwargs):
        raise deploy.DeployError("remote helper failed")

    client.wait_marker = fail_marker  # type: ignore[method-assign]

    with pytest.raises(deploy.DeployError, match="remote helper failed"):
        deploy._deploy_environment(
            client,
            deploy.ENVIRONMENTS["staging"],
            sha=SHA,
            archive_sha256=ARCHIVE_SHA,
            browser_origin=deploy.DEFAULT_BROWSER_ORIGIN,
            smoke_credentials=None,
            allow_missing_authenticated_read=True,
            conquer_smoke=False,
        )

    disable_calls = [
        call
        for call in client.calls
        if call[0] == "set_task" and call[2] is False
    ]
    assert len(disable_calls) == 2
    assert ("enable_web", "staging") not in client.calls


def test_worker_start_count_requires_environment_and_release() -> None:
    environment = deploy.ENVIRONMENTS["staging"]
    log = b"\n".join(
        (
            (
                b'{"message":"Background worker started environment=staging",'
                + f'"release_sha":"{SHA}"'.encode()
                + b"}"
            ),
            b'{"message":"Background worker started environment=production"}',
            b'{"message":"Worker sweep complete","release_sha":"'
            + SHA.encode()
            + b'"}',
        )
    )

    assert deploy._worker_start_count(log, environment, SHA) == 1


def test_smoke_credentials_must_be_private(tmp_path: Path) -> None:
    credentials = tmp_path / "smoke.json"
    credentials.write_text(
        json.dumps({"username": "smoke", "token": "private-token"}),
        encoding="utf-8",
    )
    credentials.chmod(0o644)
    with pytest.raises(deploy.DeployError, match="owner-only"):
        deploy._read_smoke_credentials(credentials)

    credentials.chmod(0o600)
    assert deploy._read_smoke_credentials(credentials) == (
        "smoke",
        "private-token",
    )


def test_api_task_boolean_is_encoded_as_json(monkeypatch: pytest.MonkeyPatch) -> None:
    client = deploy.PythonAnywhereClient(
        host="example.invalid",
        user="tester",
        token="secret-token",
    )
    observed: dict[str, Any] = {}

    def fake_request(method, path, **kwargs):
        observed.update(method=method, path=path, **kwargs)
        return b'{"id":123,"enabled":false}'

    monkeypatch.setattr(client, "_request", fake_request)
    result = client.set_task(123, enabled=False)

    assert result["enabled"] is False
    assert observed["method"] == "PATCH"
    assert observed["content_type"] == "application/json"
    assert json.loads(observed["body"]) == {"enabled": False}


def test_remote_helper_keeps_production_fail_closed() -> None:
    helper = deploy.REMOTE_HELPER.read_text(encoding="utf-8")

    maintenance_on = helper.index("MAINTENANCE_MODE=True")
    backup = helper.index("create_postgres_backup.py", maintenance_on)
    prepare = helper.index("prepare-database", backup)
    maintenance_off = helper.index("MAINTENANCE_MODE=False")
    assert maintenance_on < backup < prepare
    assert "finalize-production" in helper[:maintenance_off]
    assert "DB_URL" not in helper
