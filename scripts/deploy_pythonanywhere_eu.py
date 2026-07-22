#!/usr/bin/env python3
"""Fail-closed deploys for the paid PythonAnywhere EU environments.

The command promotes one immutable Git SHA through isolated staging and
production PostgreSQL environments. Without ``--execute`` it only prints the
plan. Mutating runs require the full SHA in ``--confirm-sha``.

Typical release:

    .venv/bin/python scripts/deploy_pythonanywhere_eu.py \
        --environment both --push --execute \
        --confirm-sha "$(git rev-parse HEAD)" \
        --allow-missing-authenticated-read

The authenticated-read waiver is explicit because no reusable live token is
stored in this repository. Prefer passing private JSON credential files with
``--smoke-credentials staging=/path/to/file.json`` and the production
equivalent. Each file contains ``{"username": "...", "token": "..."}``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
REMOTE_HELPER = REPO_ROOT / "deploy/pythonanywhere/remote_release.sh"
BACKUP_HELPER = REPO_ROOT / "scripts/create_postgres_backup.py"
WORKER_HELPER = REPO_ROOT / "scripts/verify_postgres_worker.py"
PROBE_SCRIPT = REPO_ROOT / "scripts/probe_launch_endpoints.py"
CONQUER_SMOKE_SCRIPT = REPO_ROOT / "scripts/smoke_conquer_api.py"

DEFAULT_USER = "nepalkingz"
DEFAULT_API_HOST = "eu.pythonanywhere.com"
DEFAULT_TOKEN_FILE = Path.home() / ".nepalkings_eu_pa_token"
DEFAULT_BROWSER_ORIGIN = "https://mstieffe.github.io"
MINIMUM_SCHEMA_VERSION = 19
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


class DeployError(RuntimeError):
    """A release gate or provider operation failed."""


@dataclass(frozen=True)
class Environment:
    name: str
    domain: str
    task_id: int
    env_file: str
    virtualenv: str
    wsgi_file: str
    backup_directory: str

    @property
    def base_url(self) -> str:
        return f"https://{self.domain}"


ENVIRONMENTS: Mapping[str, Environment] = {
    "staging": Environment(
        name="staging",
        domain="nepalkingz.eu.pythonanywhere.com",
        task_id=35390,
        env_file="/home/nepalkingz/.config/nepalkings/staging.env",
        virtualenv="/home/nepalkingz/.virtualenvs/nepalkings-staging",
        wsgi_file="/var/www/nepalkingz_eu_pythonanywhere_com_wsgi.py",
        backup_directory="/home/nepalkingz/backups/postgres-staging",
    ),
    "production": Environment(
        name="production",
        domain="api-nepalkingz.eu.pythonanywhere.com",
        task_id=35394,
        env_file="/home/nepalkingz/.config/nepalkings/production.env",
        virtualenv="/home/nepalkingz/.virtualenvs/nepalkings-production",
        wsgi_file="/var/www/api-nepalkingz_eu_pythonanywhere_com_wsgi.py",
        backup_directory="/home/nepalkingz/backups/postgres-production",
    ),
}


def _run(
    command: Sequence[str],
    *,
    capture: bool = False,
    timeout: float | None = None,
) -> str:
    result = subprocess.run(
        list(command),
        cwd=REPO_ROOT,
        check=False,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        timeout=timeout,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "command failed").strip()
        if len(detail) > 2000:
            detail = f"{detail[:2000]}..."
        raise DeployError(f"{command[0]} failed: {detail}")
    return (result.stdout or "").strip()


def _git(*arguments: str) -> str:
    return _run(("git", *arguments), capture=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_sha(value: str) -> str:
    if not SHA_PATTERN.fullmatch(value):
        raise DeployError("Release SHA must be the full lowercase 40-character SHA")
    return value


def _candidate_state() -> tuple[str, str]:
    branch = _git("branch", "--show-current")
    sha = _validate_sha(_git("rev-parse", "HEAD"))
    if branch != "develop":
        raise DeployError(f"Deployments must start from develop, not {branch!r}")
    if _git("status", "--porcelain"):
        raise DeployError("Worktree must be clean before creating an immutable release")
    _run(("git", "diff", "--check"), capture=True)
    for path in (REMOTE_HELPER, BACKUP_HELPER, WORKER_HELPER):
        relative = path.relative_to(REPO_ROOT).as_posix()
        _run(("git", "cat-file", "-e", f"{sha}:{relative}"), capture=True)
    return branch, sha


def _ensure_remote_ref(branch: str, sha: str) -> None:
    remote_sha = _validate_sha(_git("rev-parse", f"origin/{branch}"))
    if remote_sha != sha:
        raise DeployError(
            f"origin/{branch} is {remote_sha[:7]}, expected candidate {sha[:7]}"
        )


def _wait_for_ci(sha: str, *, timeout_seconds: float) -> None:
    if not shutil.which("gh"):
        raise DeployError("GitHub CLI is required for the default CI gate")
    required = {"Tests", "Security Scans"}
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        raw = _run(
            (
                "gh",
                "run",
                "list",
                "--commit",
                sha,
                "--limit",
                "20",
                "--json",
                "databaseId,workflowName,status,conclusion,url",
            ),
            capture=True,
        )
        runs = json.loads(raw or "[]")
        latest: dict[str, Mapping[str, Any]] = {}
        for run in runs:
            name = str(run.get("workflowName") or "")
            if name not in required:
                continue
            if int(run.get("databaseId") or 0) > int(
                latest.get(name, {}).get("databaseId") or 0
            ):
                latest[name] = run
        failed = [
            name
            for name, run in latest.items()
            if run.get("status") == "completed"
            and run.get("conclusion") != "success"
        ]
        if failed:
            raise DeployError(f"Required CI failed: {', '.join(sorted(failed))}")
        if required <= latest.keys() and all(
            latest[name].get("status") == "completed"
            and latest[name].get("conclusion") == "success"
            for name in required
        ):
            print("CI_GATE_PASSED workflows=Security Scans,Tests")
            return
        statuses = ", ".join(
            f"{name}={latest.get(name, {}).get('status', 'missing')}"
            for name in sorted(required)
        )
        print(f"Waiting for CI: {statuses}")
        time.sleep(10)
    raise DeployError("Timed out waiting for required GitHub Actions workflows")


class PythonAnywhereClient:
    """Small token-authenticated client for the documented v0 API."""

    def __init__(self, *, host: str, user: str, token: str) -> None:
        self.host = host
        self.user = user
        self._token = token
        self.api_base = f"https://{host}/api/v0/user/{quote(user)}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        body: bytes | None = None,
        content_type: str | None = None,
        expected: tuple[int, ...] = (200,),
        allow_not_found: bool = False,
        timeout: float = 180,
    ) -> bytes | None:
        url = f"{self.api_base}{path}"
        headers = {
            "Authorization": f"Token {self._token}",
            "Cache-Control": "no-cache",
            "User-Agent": "NepalKings-EU-Deployer/1.0",
        }
        if content_type:
            headers["Content-Type"] = content_type
        for attempt in range(1, 6):
            request = Request(url, data=body, headers=headers, method=method)
            try:
                with urlopen(request, timeout=timeout) as response:
                    payload = response.read()
                    status = int(response.status)
            except HTTPError as exc:
                status = int(exc.code)
                payload = exc.read()
                if status == 404 and allow_not_found:
                    return None
                if status == 429 and attempt < 5:
                    delay = min(30, 2**attempt)
                    time.sleep(delay)
                    continue
            except (URLError, TimeoutError, OSError) as exc:
                if attempt < 5:
                    time.sleep(min(15, 2**attempt))
                    continue
                raise DeployError(f"PythonAnywhere request failed: {type(exc).__name__}") from exc
            if status in expected:
                return payload
            detail = payload.decode("utf-8", errors="replace").strip()
            if len(detail) > 500:
                detail = f"{detail[:500]}..."
            raise DeployError(
                f"PythonAnywhere {method} {path} returned HTTP {status}: {detail}"
            )
        raise DeployError(f"PythonAnywhere {method} {path} exhausted retries")

    def get_json(self, path: str) -> Mapping[str, Any]:
        payload = self._request("GET", path)
        result = json.loads(payload or b"{}")
        if not isinstance(result, dict):
            raise DeployError(f"PythonAnywhere {path} did not return an object")
        return result

    def patch_json(self, path: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        raw = self._request(
            "PATCH",
            path,
            body=json.dumps(payload, separators=(",", ":")).encode(),
            content_type="application/json",
        )
        result = json.loads(raw or b"{}")
        if not isinstance(result, dict):
            raise DeployError(f"PythonAnywhere {path} did not return an object")
        return result

    def post(self, path: str) -> None:
        self._request("POST", path)

    def upload(self, local_path: Path, remote_path: str) -> None:
        boundary = f"----NepalKings{secrets.token_hex(16)}"
        filename = local_path.name.replace('"', "")
        prefix = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="content"; filename="{filename}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode()
        suffix = f"\r\n--{boundary}--\r\n".encode()
        body = prefix + local_path.read_bytes() + suffix
        remote = quote(remote_path, safe="/")
        self._request(
            "POST",
            f"/files/path{remote}",
            body=body,
            content_type=f"multipart/form-data; boundary={boundary}",
            expected=(200, 201),
        )

    def get_file(self, remote_path: str) -> bytes | None:
        remote = quote(remote_path, safe="/")
        return self._request(
            "GET",
            f"/files/path{remote}",
            allow_not_found=True,
        )

    def disable_web(self, environment: Environment) -> None:
        self.post(f"/webapps/{environment.domain}/disable/")

    def enable_web(self, environment: Environment) -> None:
        self.post(f"/webapps/{environment.domain}/enable/")

    def reload_web(self, environment: Environment) -> None:
        self.post(f"/webapps/{environment.domain}/reload/")

    def point_web(self, environment: Environment, release_sha: str) -> None:
        source = f"/home/{self.user}/releases/{release_sha}/server"
        result = self.patch_json(
            f"/webapps/{environment.domain}/",
            {"source_directory": source},
        )
        if result.get("source_directory") != source:
            raise DeployError(f"Provider did not retain {environment.name} source path")

    def task(self, task_id: int) -> Mapping[str, Any]:
        return self.get_json(f"/always_on/{task_id}/")

    def set_task(
        self,
        task_id: int,
        *,
        enabled: bool,
        command: str | None = None,
    ) -> Mapping[str, Any]:
        payload: dict[str, Any] = {"enabled": enabled}
        if command is not None:
            payload["command"] = command
        return self.patch_json(f"/always_on/{task_id}/", payload)

    def wait_task_state(
        self,
        task_id: int,
        expected_state: str,
        *,
        timeout_seconds: float = 240,
    ) -> Mapping[str, Any]:
        deadline = time.monotonic() + timeout_seconds
        last: Mapping[str, Any] = {}
        while time.monotonic() < deadline:
            last = self.task(task_id)
            if last.get("state") == expected_state:
                return last
            time.sleep(5)
        raise DeployError(
            f"Task {task_id} did not reach {expected_state}; last state={last.get('state')}"
        )

    def wait_marker(
        self,
        ready_path: str,
        failed_path: str | None,
        *,
        timeout_seconds: float = 300,
    ) -> bytes:
        deadline = time.monotonic() + timeout_seconds
        attempt = 0
        while time.monotonic() < deadline:
            attempt += 1
            ready = self.get_file(ready_path)
            if ready is not None:
                return ready
            if failed_path and attempt % 3 == 0:
                failed = self.get_file(failed_path)
                if failed is not None:
                    raise DeployError(f"Remote deployment reported failure: {failed_path}")
            time.sleep(5)
        raise DeployError(f"Timed out waiting for remote marker {ready_path}")


def _read_token(path: Path) -> str:
    try:
        token = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise DeployError(f"Could not read PythonAnywhere token file: {path}") from exc
    if not token:
        raise DeployError(f"PythonAnywhere token file is empty: {path}")
    return token


def _create_archive(sha: str, destination: Path) -> str:
    _run(
        (
            "git",
            "archive",
            "--format=tar.gz",
            f"--output={destination}",
            sha,
            "server",
        ),
        capture=True,
    )
    digest = _sha256(destination)
    print(
        f"ARTIFACT_CREATED bytes={destination.stat().st_size} sha256={digest}"
    )
    return digest


def _upload_release_inputs(
    client: PythonAnywhereClient,
    *,
    sha: str,
    archive: Path,
    archive_sha256: str,
) -> None:
    remote_base = f"/home/{client.user}/ops/{sha}"
    uploads = (
        (archive, f"/home/{client.user}/uploads/nepalkings-server-{sha}.tar.gz"),
        (REMOTE_HELPER, f"{remote_base}/remote_release.sh"),
        (BACKUP_HELPER, f"{remote_base}/scripts/create_postgres_backup.py"),
        (WORKER_HELPER, f"{remote_base}/scripts/verify_postgres_worker.py"),
    )
    expected = {
        uploads[0][1]: archive_sha256,
        uploads[1][1]: _sha256(REMOTE_HELPER),
        uploads[2][1]: _sha256(BACKUP_HELPER),
        uploads[3][1]: _sha256(WORKER_HELPER),
    }
    for local_path, remote_path in uploads:
        client.upload(local_path, remote_path)
    for _local_path, remote_path in uploads:
        remote = client.get_file(remote_path)
        if remote is None or hashlib.sha256(remote).hexdigest() != expected[remote_path]:
            raise DeployError(f"Remote hash mismatch for {remote_path}")
    print(f"REMOTE_ARTIFACTS_VERIFIED release={sha}")


def _remote_helper_command(
    client: PythonAnywhereClient,
    mode: str,
    environment: Environment,
    sha: str,
    archive_sha256: str,
) -> str:
    return (
        f"bash /home/{client.user}/ops/{sha}/remote_release.sh "
        f"{mode} {environment.name} {sha} {archive_sha256}"
    )


def _canonical_worker_command(
    client: PythonAnywhereClient,
    environment: Environment,
    sha: str,
) -> str:
    return (
        f"NEPAL_KINGS_ENV_FILE={environment.env_file} "
        "AI_ENABLED=True AI_JOBS_ENABLED=True "
        f"{environment.virtualenv}/bin/python "
        f"/home/{client.user}/releases/{sha}/server/manage.py run-worker"
    )


def _task_log_path(environment: Environment) -> str:
    return f"/var/log/alwayson-log-{environment.task_id}.log"


def _worker_activity_count(log: bytes, environment: Environment, sha: str) -> int:
    return sum(
        1
        for line in log.splitlines()
        if sha.encode() in line
        and f'"environment":"{environment.name}"'.encode() in line
        and (
            b'"message":"Background worker started ' in line
            or b'"message":"Worker sweep complete ' in line
        )
    )


def _canonicalize_worker(
    client: PythonAnywhereClient,
    environment: Environment,
    sha: str,
) -> None:
    baseline = client.get_file(_task_log_path(environment)) or b""
    baseline_activity = _worker_activity_count(baseline, environment, sha)
    client.set_task(environment.task_id, enabled=False)
    client.wait_task_state(environment.task_id, "Stopped")
    command = _canonical_worker_command(client, environment, sha)
    result = client.set_task(
        environment.task_id,
        command=command,
        enabled=True,
    )
    if result.get("command") != command:
        raise DeployError(f"Provider did not retain {environment.name} worker command")
    client.wait_task_state(environment.task_id, "Running")

    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        current = client.get_file(_task_log_path(environment)) or b""
        if _worker_activity_count(current, environment, sha) > baseline_activity:
            print(
                f"CANONICAL_WORKER_VERIFIED environment={environment.name} task={environment.task_id}"
            )
            return
        time.sleep(5)
    raise DeployError(
        f"Canonical {environment.name} worker did not log fresh successful activity"
    )


def _summarize_remote_log(
    client: PythonAnywhereClient,
    environment: Environment,
    sha: str,
) -> None:
    path = f"/home/{client.user}/ops/{sha}/{environment.name}-deploy.log"
    raw = client.get_file(path)
    if raw is None:
        return
    safe_prefixes = (
        "DEPLOY_",
        "ARTIFACT_",
        "PRODUCTION_",
        "BACKUP_",
        "RELEASE_",
        "DEPENDENCIES_",
        "DATABASE_",
        "WSGI_",
        "WORKER_",
    )
    for line in raw.decode("utf-8", errors="replace").splitlines():
        if line.startswith(safe_prefixes) or line.startswith('{"backup"'):
            print(line)


def _run_probe(environment: Environment, sha: str) -> None:
    output = _run(
        (
            sys.executable,
            str(PROBE_SCRIPT),
            "--target",
            f"{environment.name}={environment.base_url}",
            "--samples",
            "3",
            "--cycles",
            "1",
            "--minimum-schema-version",
            str(MINIMUM_SCHEMA_VERSION),
            "--max-p95-ms",
            "2000",
        ),
        capture=True,
        timeout=120,
    )
    report = json.loads(output.splitlines()[-1])
    if report.get("ok") is not True:
        raise DeployError(f"External probe failed: {report.get('errors')}")
    target = report["targets"][0]
    if target.get("release_sha") != sha:
        raise DeployError(
            f"{environment.name} serves {target.get('release_sha')}, expected {sha}"
        )
    p95 = {
        item["endpoint"]: item["p95_ms"] for item in target.get("endpoints", [])
    }
    print(
        f"EXTERNAL_PROBE_PASSED environment={environment.name} "
        f"health_p95_ms={p95.get('/healthz')} ready_p95_ms={p95.get('/readyz')}"
    )


def _post_form_json(
    url: str,
    data: Mapping[str, str],
    *,
    origin: str,
    timeout: float = 30,
) -> tuple[int, Mapping[str, Any], Mapping[str, str]]:
    encoded = urlencode(data).encode()
    request = Request(
        url,
        data=encoded,
        method="POST",
        headers={
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": origin,
            "User-Agent": "NepalKings-EU-Deployer/1.0",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            status = int(response.status)
            body = response.read()
            headers = dict(response.headers.items())
    except HTTPError as exc:
        status = int(exc.code)
        body = exc.read()
        headers = dict(exc.headers.items())
    except (URLError, TimeoutError, OSError) as exc:
        raise DeployError(f"External contract request failed: {type(exc).__name__}") from exc
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise DeployError("External contract response was not JSON") from exc
    if not isinstance(payload, dict):
        raise DeployError("External contract response was not a JSON object")
    return status, payload, headers


def _check_login_contract(
    environment: Environment,
    *,
    expected_status: int,
    browser_origin: str,
) -> None:
    status, payload, headers = _post_form_json(
        f"{environment.base_url}/auth/login",
        {
            "username": "deploy-smoke-user-does-not-exist",
            "password": "invalid-deploy-password",
        },
        origin=browser_origin,
    )
    if status != expected_status or payload.get("success") is not False:
        raise DeployError(
            f"{environment.name} login contract returned HTTP {status}, expected {expected_status}"
        )
    cors = headers.get("Access-Control-Allow-Origin")
    if cors != browser_origin:
        raise DeployError(
            f"{environment.name} CORS returned {cors!r}, expected {browser_origin!r}"
        )
    print(
        f"LOGIN_CONTRACT_PASSED environment={environment.name} status={status}"
    )


def _read_smoke_credentials(path: Path) -> tuple[str, str]:
    try:
        mode = path.stat().st_mode
    except OSError as exc:
        raise DeployError(f"Could not stat smoke credential file: {path}") from exc
    if mode & 0o077:
        raise DeployError(f"Smoke credential file must be owner-only: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeployError(f"Could not read smoke credential file: {path}") from exc
    username = str(payload.get("username") or "")
    token = str(payload.get("token") or "")
    if not username or not token:
        raise DeployError(f"Smoke credential file lacks username/token: {path}")
    return username, token


def _authenticated_read(
    environment: Environment,
    credentials: Path | None,
    *,
    allow_missing: bool,
) -> None:
    if credentials is None:
        if not allow_missing:
            raise DeployError(
                f"No {environment.name} smoke credentials; pass --smoke-credentials "
                "or explicitly use --allow-missing-authenticated-read"
            )
        print(f"AUTHENTICATED_READ_SKIPPED environment={environment.name} explicit_waiver=True")
        return
    username, token = _read_smoke_credentials(credentials)
    query = urlencode({"username": username})
    request = Request(
        f"{environment.base_url}/games/get_games?{query}",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "NepalKings-EU-Deployer/1.0",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            status = int(response.status)
            payload = json.loads(response.read())
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise DeployError(f"{environment.name} authenticated read failed") from exc
    if status != 200 or payload.get("success") is not True:
        raise DeployError(f"{environment.name} authenticated read contract failed")
    print(f"AUTHENTICATED_READ_PASSED environment={environment.name}")


def _run_conquer_smoke(environment: Environment, sha: str) -> None:
    output = _run(
        (
            sys.executable,
            str(CONQUER_SMOKE_SCRIPT),
            "--base-url",
            environment.base_url,
            "--expected-environment",
            environment.name,
            "--confirm-mutation",
            environment.base_url,
        ),
        capture=True,
        timeout=180,
    )
    payload = json.loads(output)
    if payload.get("success") is not True or payload.get("release_sha") != sha:
        raise DeployError("Authenticated Conquer smoke did not verify the candidate")
    print(
        f"CONQUER_SMOKE_PASSED environment={environment.name} "
        f"game_id={payload.get('game_id')} user_id={payload.get('user_id')}"
    )


def _preflight_provider(
    client: PythonAnywhereClient,
    environments: Sequence[Environment],
) -> None:
    for environment in environments:
        task = client.task(environment.task_id)
        if int(task.get("id") or 0) != environment.task_id:
            raise DeployError(f"Unexpected always-on task for {environment.name}")
        web = client.get_json(f"/webapps/{environment.domain}/")
        if web.get("domain_name") != environment.domain:
            raise DeployError(f"Unexpected web app for {environment.name}")
    print("PROVIDER_PREFLIGHT_PASSED")


def _deploy_environment(
    client: PythonAnywhereClient,
    environment: Environment,
    *,
    sha: str,
    archive_sha256: str,
    browser_origin: str,
    smoke_credentials: Path | None,
    allow_missing_authenticated_read: bool,
    conquer_smoke: bool,
) -> None:
    print(f"DEPLOYING environment={environment.name} release={sha}")
    error_log_path = f"/var/log/{environment.domain}.error.log"
    error_log_before = client.get_file(error_log_path) or b""
    helper_task_active = False

    try:
        client.set_task(environment.task_id, enabled=False)
        client.disable_web(environment)
        client.wait_task_state(environment.task_id, "Stopped")

        deploy_command = _remote_helper_command(
            client, "deploy", environment, sha, archive_sha256
        )
        helper_task_active = True
        client.set_task(
            environment.task_id,
            command=deploy_command,
            enabled=True,
        )
        client.wait_task_state(environment.task_id, "Running")
        remote_base = f"/home/{client.user}/ops/{sha}"
        client.wait_marker(
            f"{remote_base}/{environment.name}-deploy.ready",
            f"{remote_base}/{environment.name}-deploy.failed",
        )
        _summarize_remote_log(client, environment, sha)

        client.point_web(environment, sha)
        client.enable_web(environment)
        client.reload_web(environment)
        _run_probe(environment, sha)

        if environment.name == "production":
            _check_login_contract(
                environment,
                expected_status=503,
                browser_origin=browser_origin,
            )
            client.set_task(environment.task_id, enabled=False)
            client.wait_task_state(environment.task_id, "Stopped")
            finalize_command = _remote_helper_command(
                client,
                "finalize-production",
                environment,
                sha,
                archive_sha256,
            )
            client.set_task(
                environment.task_id,
                command=finalize_command,
                enabled=True,
            )
            client.wait_task_state(environment.task_id, "Running")
            client.wait_marker(
                f"{remote_base}/production-finalize.ready",
                f"{remote_base}/production-finalize.failed",
                timeout_seconds=120,
            )

        _canonicalize_worker(client, environment, sha)
        helper_task_active = False
        if environment.name == "production":
            client.reload_web(environment)
        _run_probe(environment, sha)
        _check_login_contract(
            environment,
            expected_status=401,
            browser_origin=browser_origin,
        )
        _authenticated_read(
            environment,
            smoke_credentials,
            allow_missing=allow_missing_authenticated_read,
        )
        if conquer_smoke:
            _run_conquer_smoke(environment, sha)

        current_error_log = client.get_file(error_log_path) or b""
        if current_error_log.startswith(error_log_before):
            new_errors = current_error_log[len(error_log_before) :]
        else:
            new_errors = b""
            print(
                f"ERROR_LOG_SCAN_SKIPPED environment={environment.name} "
                "reason=rotation"
            )
        suspicious = (
            b"Traceback (most recent call last)" in new_errors
            or b"sqlalchemy.exc." in new_errors.lower()
            or b"psycopg.errors." in new_errors.lower()
            or b"deadlock detected" in new_errors.lower()
        )
        if suspicious:
            raise DeployError(f"New suspicious lines appeared in {environment.name} error log")
        print(f"ENVIRONMENT_PROMOTED environment={environment.name} release={sha}")
    except Exception:
        if helper_task_active:
            try:
                client.set_task(environment.task_id, enabled=False)
            except Exception:
                pass
            try:
                client.disable_web(environment)
            except Exception:
                pass
        _summarize_remote_log(client, environment, sha)
        if helper_task_active and environment.name == "production":
            print("Production remains disabled or in maintenance after failure.", file=sys.stderr)
        elif helper_task_active:
            print("Staging remains disabled after failure.", file=sys.stderr)
        else:
            print(
                f"{environment.name.capitalize()} canonical worker was left running after post-promotion verification failed.",
                file=sys.stderr,
            )
        raise


def _parse_smoke_credentials(values: Sequence[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        environment, separator, raw_path = value.partition("=")
        if not separator or environment not in ENVIRONMENTS or not raw_path:
            raise DeployError(
                "--smoke-credentials must be staging=/path or production=/path"
            )
        result[environment] = Path(raw_path).expanduser().resolve()
    return result


def _selected_environments(value: str) -> list[Environment]:
    if value == "both":
        return [ENVIRONMENTS["staging"], ENVIRONMENTS["production"]]
    return [ENVIRONMENTS[value]]


def _print_plan(environments: Sequence[Environment], sha: str) -> None:
    print(f"Candidate: {sha}")
    print("Safety order:")
    for environment in environments:
        print(
            f"  {environment.name}: stop worker/web -> verified PostgreSQL backup -> "
            "immutable release -> prepare database -> verify worker -> reload/probe"
        )
    if any(item.name == "production" for item in environments):
        print("  production stays in maintenance until its probe passes")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--environment",
        choices=("staging", "production", "both"),
        default="both",
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm-sha")
    parser.add_argument("--push", action="store_true")
    parser.add_argument("--skip-ci", action="store_true")
    parser.add_argument("--ci-timeout-seconds", type=float, default=1800)
    parser.add_argument("--token-file", type=Path, default=DEFAULT_TOKEN_FILE)
    parser.add_argument("--api-host", default=DEFAULT_API_HOST)
    parser.add_argument("--user", default=DEFAULT_USER)
    parser.add_argument("--browser-origin", default=DEFAULT_BROWSER_ORIGIN)
    parser.add_argument(
        "--smoke-credentials",
        action="append",
        default=[],
        metavar="ENV=/PRIVATE/FILE.json",
    )
    parser.add_argument("--allow-missing-authenticated-read", action="store_true")
    parser.add_argument("--conquer-smoke-staging", action="store_true")
    parser.add_argument("--production-without-staging", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        branch, sha = _candidate_state()
        environments = _selected_environments(args.environment)
        _print_plan(environments, sha)
        if not args.execute:
            print("Dry run only. Add --execute and --confirm-sha with the full SHA.")
            return 0
        if args.confirm_sha != sha:
            raise DeployError("--confirm-sha must exactly match the current full HEAD SHA")
        if (
            args.environment == "production"
            and not args.production_without_staging
        ):
            raise DeployError(
                "Production-only promotion requires --production-without-staging; prefer --environment both"
            )
        credentials = _parse_smoke_credentials(args.smoke_credentials)
        missing = [item.name for item in environments if item.name not in credentials]
        if missing and not args.allow_missing_authenticated_read:
            raise DeployError(
                "Missing private smoke credentials for: " + ", ".join(missing)
            )

        if args.push:
            _run(("git", "push", "origin", branch))
        _ensure_remote_ref(branch, sha)
        if not args.skip_ci:
            _wait_for_ci(sha, timeout_seconds=args.ci_timeout_seconds)

        token = os.getenv("PA_API_TOKEN") or _read_token(args.token_file)
        client = PythonAnywhereClient(host=args.api_host, user=args.user, token=token)
        _preflight_provider(client, environments)

        with tempfile.TemporaryDirectory(prefix="nepalkings-eu-release-") as temporary:
            archive = Path(temporary) / f"nepalkings-server-{sha}.tar.gz"
            archive_sha256 = _create_archive(sha, archive)
            _upload_release_inputs(
                client,
                sha=sha,
                archive=archive,
                archive_sha256=archive_sha256,
            )
            for environment in environments:
                _deploy_environment(
                    client,
                    environment,
                    sha=sha,
                    archive_sha256=archive_sha256,
                    browser_origin=args.browser_origin,
                    smoke_credentials=credentials.get(environment.name),
                    allow_missing_authenticated_read=args.allow_missing_authenticated_read,
                    conquer_smoke=(
                        environment.name == "staging"
                        and args.conquer_smoke_staging
                    ),
                )
        print(f"RELEASE_COMPLETE sha={sha} environments={args.environment}")
        return 0
    except DeployError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception:
        print("ERROR: unexpected deployment failure (details suppressed)", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
