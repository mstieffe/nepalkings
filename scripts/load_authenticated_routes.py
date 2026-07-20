#!/usr/bin/env python3
"""Run a bounded authenticated read workload against Nepal Kings staging.

The default route mix represents active menu/config usage:

- 45% Collection reads;
- 35% Conquer configuration reads;
- 18% game-list polling;
- 2% full 4,800-land map reads.

One clearly named synthetic account is created and retained as staging test
data. Virtual users share that account but keep independent HTTP sessions,
which exercises web-worker/database concurrency without creating hundreds of
accounts. No gameplay mutation runs after setup.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import secrets
import statistics
import sys
import threading
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlencode

import requests


STAGING_URL = "https://nepalkingz.eu.pythonanywhere.com"
ROUTE_WEIGHTS = (
    ("collection", 45),
    ("conquer_config", 35),
    ("game_list", 18),
    ("kingdom_map", 2),
)


@dataclass(frozen=True)
class Sample:
    bytes: int
    elapsed_ms: float
    error: str
    route: str
    status: int
    virtual_user: int
    content_encoding: str = ""
    wire_bytes: int = 0

    @property
    def ok(self) -> bool:
        return not self.error and 200 <= self.status < 300


def _request_json(
    session: requests.Session,
    method: str,
    url: str,
    *,
    token: str | None = None,
    data: Mapping[str, str] | None = None,
    json_data: Mapping[str, Any] | None = None,
    timeout: float,
) -> tuple[requests.Response, Mapping[str, Any], float]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    started = time.perf_counter()
    response = session.request(
        method,
        url,
        data=data,
        json=json_data,
        headers=headers,
        timeout=timeout,
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"{method} {url} returned non-JSON HTTP {response.status_code}"
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{method} {url} did not return a JSON object")
    if not response.ok or payload.get("success") is False:
        safe_payload = {
            key: value
            for key, value in payload.items()
            if key.lower() not in {"password", "token"}
        }
        raise RuntimeError(
            f"{method} {url} returned HTTP {response.status_code}: "
            f"{safe_payload}"
        )
    return response, payload, elapsed_ms


def _create_synthetic_account(
    base_url: str,
    timeout: float,
) -> tuple[str, str, int, dict[str, float]]:
    session = requests.Session()
    session.headers["User-Agent"] = "NepalKings-Authenticated-Load-Setup/1.0"
    suffix = datetime.now(timezone.utc).strftime("%m%d%H%M%S")
    username = f"nkload_{suffix}_{secrets.token_hex(2)}"
    password = secrets.token_urlsafe(24)
    timings: dict[str, float] = {}

    _response, registered, timings["register_ms"] = _request_json(
        session,
        "POST",
        f"{base_url}/auth/register",
        data={
            "age_confirmed": "true",
            "password": password,
            "privacy_accepted": "true",
            "terms_accepted": "true",
            "username": username,
        },
        timeout=timeout,
    )
    token = registered.get("token")
    if not isinstance(token, str) or not token:
        raise RuntimeError("registration returned no token")

    _response, _payload, timings["welcome_ms"] = _request_json(
        session,
        "POST",
        f"{base_url}/onboarding/mark_tip",
        token=token,
        json_data={"tip_key": "welcome"},
        timeout=timeout,
    )
    _response, _payload, timings["starter_prepare_ms"] = _request_json(
        session,
        "POST",
        f"{base_url}/onboarding/starter_reveal/prepare",
        token=token,
        timeout=timeout,
    )
    _response, _payload, timings["collection_hints_ms"] = _request_json(
        session,
        "POST",
        f"{base_url}/onboarding/mark_tip",
        token=token,
        json_data={
            "tip_keys": [
                "menu:collection_basics_window",
                "menu:starter_cards_present_window",
            ]
        },
        timeout=timeout,
    )
    _response, _payload, timings["starter_complete_ms"] = _request_json(
        session,
        "POST",
        f"{base_url}/onboarding/starter_reveal/complete",
        token=token,
        timeout=timeout,
    )
    _response, kingdom_map, timings["first_map_ms"] = _request_json(
        session,
        "GET",
        f"{base_url}/kingdom/map",
        token=token,
        timeout=timeout,
    )
    land_id = kingdom_map.get("recommended_tutorial_land_id")
    if land_id is None:
        land = next(
            (
                item
                for item in kingdom_map.get("lands", [])
                if not item.get("is_mine")
            ),
            None,
        )
        land_id = land.get("id") if land else None
    if land_id is None:
        raise RuntimeError("no conquerable land found in kingdom map")

    _response, _payload, timings["first_config_ms"] = _request_json(
        session,
        "GET",
        (
            f"{base_url}/kingdom/conquer/config?"
            + urlencode({"land_id": int(land_id)})
        ),
        token=token,
        timeout=timeout,
    )
    return username, token, int(land_id), timings


def _nearest_rank(values: Sequence[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(len(ordered) * percentile))
    return ordered[rank - 1]


def _route_path(route: str, username: str, land_id: int) -> str:
    if route == "collection":
        return "/collection/cards"
    if route == "conquer_config":
        return "/kingdom/conquer/config?" + urlencode({"land_id": land_id})
    if route == "game_list":
        return "/games/get_games?" + urlencode({"username": username})
    if route == "kingdom_map":
        return "/kingdom/map"
    raise ValueError(f"unknown load route: {route}")


def _run_load(
    *,
    base_url: str,
    username: str,
    token: str,
    land_id: int,
    virtual_users: int,
    duration_seconds: float,
    think_time_seconds: float,
    ramp_seconds: float,
    timeout_seconds: float,
    seed: int,
) -> list[Sample]:
    samples: list[Sample] = []
    sample_lock = threading.Lock()
    start_at = time.monotonic()
    deadline = start_at + duration_seconds
    route_names = [name for name, _weight in ROUTE_WEIGHTS]
    route_weights = [weight for _name, weight in ROUTE_WEIGHTS]

    def virtual_user(user_index: int) -> None:
        rng = random.Random(seed + user_index)
        session = requests.Session()
        session.headers.update({
            "Authorization": f"Bearer {token}",
            "Cache-Control": "no-cache",
            "User-Agent": "NepalKings-Authenticated-Load/1.0",
        })
        initial_delay = (
            ramp_seconds * user_index / max(1, virtual_users - 1)
            if virtual_users > 1
            else 0.0
        )
        if initial_delay:
            time.sleep(initial_delay)

        while time.monotonic() < deadline:
            route = rng.choices(
                route_names,
                weights=route_weights,
                k=1,
            )[0]
            path = _route_path(route, username, land_id)
            started = time.perf_counter()
            status = 0
            byte_count = 0
            wire_byte_count = 0
            content_encoding = ""
            error = ""
            try:
                response = session.get(
                    f"{base_url}{path}",
                    timeout=timeout_seconds,
                )
                status = response.status_code
                byte_count = len(response.content)
                content_encoding = response.headers.get(
                    "Content-Encoding",
                    "",
                )
                try:
                    wire_byte_count = int(
                        response.headers.get("Content-Length", byte_count)
                    )
                except (TypeError, ValueError):
                    wire_byte_count = byte_count
                if not 200 <= response.status_code < 300:
                    error = f"HTTP {response.status_code}"
                else:
                    try:
                        payload = response.json()
                    except ValueError as exc:
                        error = f"invalid JSON: {exc}"
                    else:
                        if (
                            isinstance(payload, dict)
                            and payload.get("success") is False
                        ):
                            error = "success=false"
            except requests.RequestException as exc:
                error = f"{type(exc).__name__}: {exc}"
            elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
            with sample_lock:
                samples.append(Sample(
                    bytes=byte_count,
                    elapsed_ms=elapsed_ms,
                    error=error,
                    route=route,
                    status=status,
                    virtual_user=user_index,
                    content_encoding=content_encoding,
                    wire_bytes=wire_byte_count,
                ))

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            jittered_think = think_time_seconds * rng.uniform(0.8, 1.2)
            time.sleep(min(remaining, jittered_think))

    threads = [
        threading.Thread(target=virtual_user, args=(index,), daemon=True)
        for index in range(virtual_users)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=duration_seconds + timeout_seconds + 5)
    alive = [thread for thread in threads if thread.is_alive()]
    if alive:
        raise RuntimeError(f"{len(alive)} virtual-user threads did not stop")
    return samples


def _summarize(
    samples: Sequence[Sample],
    *,
    duration_seconds: float,
    max_p95_ms: float,
    max_map_p95_ms: float,
    max_error_rate: float,
) -> dict[str, Any]:
    route_reports: dict[str, Any] = {}
    failures = []
    for route, _weight in ROUTE_WEIGHTS:
        route_samples = [sample for sample in samples if sample.route == route]
        successful = [sample for sample in route_samples if sample.ok]
        latencies = [sample.elapsed_ms for sample in successful]
        route_p95_ms = round(_nearest_rank(latencies, 0.95), 1)
        route_ceiling_ms = (
            max_map_p95_ms if route == "kingdom_map" else max_p95_ms
        )
        if route_samples and route_p95_ms > route_ceiling_ms:
            failures.append(
                f"{route} p95 {route_p95_ms:.1f} ms exceeds "
                f"{route_ceiling_ms:.1f} ms"
            )
        route_reports[route] = {
            "bytes_mean": (
                round(statistics.mean(sample.bytes for sample in successful), 1)
                if successful
                else 0
            ),
            "gzip_responses": sum(
                sample.content_encoding == "gzip"
                for sample in successful
            ),
            "errors": len(route_samples) - len(successful),
            "p50_ms": round(_nearest_rank(latencies, 0.50), 1),
            "p95_ms": route_p95_ms,
            "p99_ms": round(_nearest_rank(latencies, 0.99), 1),
            "requests": len(route_samples),
            "wire_bytes_mean": (
                round(
                    statistics.mean(
                        sample.wire_bytes or sample.bytes
                        for sample in successful
                    ),
                    1,
                )
                if successful
                else 0
            ),
        }

    successful = [sample for sample in samples if sample.ok]
    errors = len(samples) - len(successful)
    error_rate = errors / len(samples) if samples else 1.0
    p95_ms = _nearest_rank(
        [sample.elapsed_ms for sample in successful],
        0.95,
    )
    if error_rate > max_error_rate:
        failures.append(
            f"error rate {error_rate:.3%} exceeds {max_error_rate:.3%}"
        )
    if p95_ms > max_p95_ms:
        failures.append(
            f"overall p95 {p95_ms:.1f} ms exceeds {max_p95_ms:.1f} ms"
        )
    status_counts = Counter(sample.status for sample in samples)
    error_examples = [
        sample.error
        for sample in samples
        if sample.error
    ][:10]
    return {
        "error_examples": error_examples,
        "error_rate": round(error_rate, 6),
        "errors": errors,
        "failures": failures,
        "ok": not failures,
        "overall_p50_ms": round(_nearest_rank(
            [sample.elapsed_ms for sample in successful],
            0.50,
        ), 1),
        "overall_p95_ms": round(p95_ms, 1),
        "overall_p99_ms": round(_nearest_rank(
            [sample.elapsed_ms for sample in successful],
            0.99,
        ), 1),
        "requests": len(samples),
        "requests_per_second": round(
            len(samples) / duration_seconds,
            2,
        ),
        "routes": route_reports,
        "status_counts": {
            str(status): count
            for status, count in sorted(status_counts.items())
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=STAGING_URL)
    parser.add_argument("--virtual-users", type=int, default=25)
    parser.add_argument("--duration-seconds", type=float, default=30.0)
    parser.add_argument("--think-time-seconds", type=float, default=5.0)
    parser.add_argument("--ramp-seconds", type=float, default=5.0)
    parser.add_argument("--timeout-seconds", type=float, default=15.0)
    parser.add_argument("--max-p95-ms", type=float, default=800.0)
    parser.add_argument("--max-map-p95-ms", type=float, default=1500.0)
    parser.add_argument("--max-error-rate", type=float, default=0.005)
    parser.add_argument("--seed", type=int, default=20260720)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--allow-production", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    base_url = args.base_url.rstrip("/")
    if (
        "api-nepalkingz.eu.pythonanywhere.com" in base_url
        and not args.allow_production
    ):
        print("ERROR: refusing production without --allow-production")
        return 2
    if (
        args.virtual_users < 1
        or args.duration_seconds <= 0
        or args.think_time_seconds < 0
        or args.ramp_seconds < 0
        or args.ramp_seconds >= args.duration_seconds
    ):
        print("ERROR: invalid load duration/ramp/user settings")
        return 2

    try:
        username, token, land_id, setup_timings = (
            _create_synthetic_account(
                base_url,
                args.timeout_seconds,
            )
        )
        started_at = datetime.now(timezone.utc)
        samples = _run_load(
            base_url=base_url,
            username=username,
            token=token,
            land_id=land_id,
            virtual_users=args.virtual_users,
            duration_seconds=args.duration_seconds,
            think_time_seconds=args.think_time_seconds,
            ramp_seconds=args.ramp_seconds,
            timeout_seconds=args.timeout_seconds,
            seed=args.seed,
        )
        report = {
            "base_url": base_url,
            "finished_at_utc": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "land_id": land_id,
            "profile": {
                "duration_seconds": args.duration_seconds,
                "ramp_seconds": args.ramp_seconds,
                "route_weights": dict(ROUTE_WEIGHTS),
                "think_time_seconds": args.think_time_seconds,
                "virtual_users": args.virtual_users,
            },
            "setup_timings_ms": setup_timings,
            "started_at_utc": started_at
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
            "summary": _summarize(
                samples,
                duration_seconds=args.duration_seconds,
                max_p95_ms=args.max_p95_ms,
                max_map_p95_ms=args.max_map_p95_ms,
                max_error_rate=args.max_error_rate,
            ),
            "synthetic_user_retained": username,
        }
    except Exception as exc:
        print(json.dumps({"error": str(exc), "ok": False}, sort_keys=True))
        return 1

    if args.output:
        output = args.output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(
                {
                    **report,
                    "samples": [asdict(sample) for sample in samples],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["summary"]["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
