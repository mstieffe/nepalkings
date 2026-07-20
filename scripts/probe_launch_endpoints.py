#!/usr/bin/env python3
"""Probe launch-critical endpoints from outside the hosting provider.

The command uses only the Python standard library so it can run locally or in
GitHub Actions without installing the game. Each cycle validates health,
readiness, PostgreSQL/schema state, release consistency, legal-document
discovery, and a latency ceiling.

Examples:

    python scripts/probe_launch_endpoints.py

    python scripts/probe_launch_endpoints.py \
      --cycles 1440 --interval-seconds 60 \
      --output backups/soak/launch-soak.jsonl
"""

from __future__ import annotations

import argparse
import json
import math
import socket
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_TARGETS = (
    "production=https://api-nepalkingz.eu.pythonanywhere.com",
    "staging=https://nepalkingz.eu.pythonanywhere.com",
)
ENDPOINTS = ("/healthz", "/readyz", "/legal/versions")
USER_AGENT = "NepalKings-External-Uptime-Probe/1.0"


@dataclass(frozen=True)
class RequestResult:
    endpoint: str
    latency_ms: float
    status: int
    payload: Mapping[str, Any] | None
    error: str | None


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _parse_target(value: str) -> tuple[str, str]:
    environment, separator, base_url = value.partition("=")
    environment = environment.strip()
    base_url = base_url.strip().rstrip("/")
    if not separator or not environment or not base_url.startswith("https://"):
        raise argparse.ArgumentTypeError(
            "target must have the form environment=https://hostname"
        )
    return environment, base_url


def _request_json(base_url: str, endpoint: str, timeout: float) -> RequestResult:
    request = Request(
        f"{base_url}{endpoint}",
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-cache",
            "User-Agent": USER_AGENT,
        },
    )
    started = time.perf_counter()
    try:
        with urlopen(request, timeout=timeout) as response:
            status = response.status
            raw_body = response.read()
    except HTTPError as exc:
        status = exc.code
        raw_body = exc.read()
    except (URLError, TimeoutError, socket.timeout, OSError) as exc:
        return RequestResult(
            endpoint=endpoint,
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
            status=0,
            payload=None,
            error=f"{type(exc).__name__}: {exc}",
        )

    latency_ms = round((time.perf_counter() - started) * 1000, 1)
    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return RequestResult(
            endpoint=endpoint,
            latency_ms=latency_ms,
            status=status,
            payload=None,
            error=f"invalid JSON: {exc}",
        )
    if not isinstance(payload, dict):
        return RequestResult(
            endpoint=endpoint,
            latency_ms=latency_ms,
            status=status,
            payload=None,
            error="JSON response is not an object",
        )
    return RequestResult(
        endpoint=endpoint,
        latency_ms=latency_ms,
        status=status,
        payload=payload,
        error=None,
    )


def _nearest_rank_percentile(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def _validate_sample(
    environment: str,
    result: RequestResult,
    minimum_schema_version: int,
) -> list[str]:
    errors: list[str] = []
    payload = result.payload or {}
    if result.error:
        errors.append(result.error)
    if result.status != 200:
        errors.append(f"expected HTTP 200, got {result.status}")
    if payload.get("success") is not True:
        errors.append("success is not true")

    if result.endpoint in {"/healthz", "/readyz"}:
        if payload.get("environment") != environment:
            errors.append(
                f"expected environment {environment!r}, "
                f"got {payload.get('environment')!r}"
            )
        release_sha = payload.get("release_sha")
        if (
            not isinstance(release_sha, str)
            or len(release_sha) != 40
            or any(character not in "0123456789abcdef" for character in release_sha)
        ):
            errors.append("release_sha is not a lowercase 40-character Git SHA")

    if result.endpoint == "/healthz" and payload.get("status") != "ok":
        errors.append("health status is not ok")
    elif result.endpoint == "/readyz":
        if payload.get("status") != "ready":
            errors.append("readiness status is not ready")
        if payload.get("database") != "postgresql":
            errors.append("readiness database is not postgresql")
        schema_version = payload.get("schema_version")
        if (
            not isinstance(schema_version, int)
            or schema_version < minimum_schema_version
        ):
            errors.append(
                f"schema version is below {minimum_schema_version}: "
                f"{schema_version!r}"
            )
    elif result.endpoint == "/legal/versions":
        documents = payload.get("documents")
        if not isinstance(documents, dict):
            errors.append("legal document map is missing")
        else:
            for name in ("terms", "privacy"):
                if not documents.get(name):
                    errors.append(f"legal document {name!r} is missing")
        for name in ("terms_version", "privacy_version"):
            if not payload.get(name):
                errors.append(f"{name} is missing")
    return errors


def probe_cycle(
    targets: Sequence[tuple[str, str]],
    *,
    samples: int,
    timeout: float,
    max_p95_ms: float,
    minimum_schema_version: int,
) -> dict[str, Any]:
    started_at = _utc_now()
    target_reports: list[dict[str, Any]] = []
    cycle_errors: list[str] = []

    for environment, base_url in targets:
        endpoint_reports: list[dict[str, Any]] = []
        releases: dict[str, set[str]] = {"/healthz": set(), "/readyz": set()}
        for endpoint in ENDPOINTS:
            results = [
                _request_json(base_url, endpoint, timeout) for _ in range(samples)
            ]
            errors: list[str] = []
            for index, result in enumerate(results, start=1):
                for error in _validate_sample(
                    environment, result, minimum_schema_version
                ):
                    errors.append(f"sample {index}: {error}")
                release_sha = (result.payload or {}).get("release_sha")
                if endpoint in releases and isinstance(release_sha, str):
                    releases[endpoint].add(release_sha)

            p95_ms = round(
                _nearest_rank_percentile(
                    [result.latency_ms for result in results],
                    0.95,
                ),
                1,
            )
            if p95_ms > max_p95_ms:
                errors.append(
                    f"p95 {p95_ms:.1f} ms exceeds {max_p95_ms:.1f} ms"
                )
            if errors:
                cycle_errors.extend(
                    f"{environment}{endpoint}: {error}" for error in errors
                )
            endpoint_reports.append(
                {
                    "endpoint": endpoint,
                    "errors": errors,
                    "p95_ms": p95_ms,
                    "samples": [asdict(result) for result in results],
                }
            )

        health_releases = releases["/healthz"]
        ready_releases = releases["/readyz"]
        if (
            len(health_releases) != 1
            or len(ready_releases) != 1
            or health_releases != ready_releases
        ):
            error = (
                "health/readiness release mismatch: "
                f"health={sorted(health_releases)}, "
                f"ready={sorted(ready_releases)}"
            )
            cycle_errors.append(f"{environment}: {error}")

        target_reports.append(
            {
                "base_url": base_url,
                "endpoints": endpoint_reports,
                "environment": environment,
                "release_sha": (
                    next(iter(health_releases))
                    if health_releases == ready_releases
                    and len(health_releases) == 1
                    else None
                ),
            }
        )

    return {
        "errors": cycle_errors,
        "finished_at_utc": _utc_now(),
        "ok": not cycle_errors,
        "started_at_utc": started_at,
        "targets": target_reports,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        action="append",
        type=_parse_target,
        dest="targets",
        help=(
            "environment=https://hostname; repeat for multiple targets "
            "(defaults to production and staging)"
        ),
    )
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--cycles", type=int, default=1)
    parser.add_argument("--interval-seconds", type=float, default=60.0)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--max-p95-ms", type=float, default=2000.0)
    parser.add_argument("--minimum-schema-version", type=int, default=17)
    parser.add_argument(
        "--output",
        type=Path,
        help="append one complete JSON report per cycle to this JSONL file",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.samples < 1 or args.cycles < 1:
        print("ERROR: --samples and --cycles must be positive", file=sys.stderr)
        return 2
    if args.interval_seconds < 0 or args.timeout_seconds <= 0:
        print(
            "ERROR: interval must be non-negative and timeout must be positive",
            file=sys.stderr,
        )
        return 2

    targets = args.targets or [_parse_target(value) for value in DEFAULT_TARGETS]
    output_handle = None
    if args.output:
        output_path = args.output.expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_handle = output_path.open("a", encoding="utf-8")
        try:
            os_mode = output_path.stat().st_mode & 0o777
            if os_mode & 0o077:
                output_path.chmod(0o600)
        except OSError:
            pass

    all_ok = True
    try:
        for cycle_index in range(args.cycles):
            report = probe_cycle(
                targets,
                samples=args.samples,
                timeout=args.timeout_seconds,
                max_p95_ms=args.max_p95_ms,
                minimum_schema_version=args.minimum_schema_version,
            )
            report["cycle"] = cycle_index + 1
            serialized = json.dumps(report, sort_keys=True)
            print(serialized, flush=True)
            if output_handle:
                output_handle.write(serialized)
                output_handle.write("\n")
                output_handle.flush()
            all_ok = all_ok and bool(report["ok"])
            if cycle_index + 1 < args.cycles:
                time.sleep(args.interval_seconds)
    finally:
        if output_handle:
            output_handle.close()
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
