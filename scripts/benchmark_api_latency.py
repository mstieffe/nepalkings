#!/usr/bin/env python3
"""Compare API latency across two or more deployment targets.

The cold pass starts a fresh curl process for every request, exposing DNS, TCP,
TLS, time-to-first-byte, and total time.  The warm pass keeps one requests
Session per target so connections can be reused, which is closer to normal
in-game polling after login.

Examples:

    python scripts/benchmark_api_latency.py \
      --target us=https://nepalkings.pythonanywhere.com/legal/versions \
      --target eu=https://YOURNAME.eu.pythonanywhere.com/legal/versions

    python scripts/benchmark_api_latency.py \
      --target us=https://nepalkings.pythonanywhere.com/legal/versions \
      --target eu=https://YOURNAME.eu.pythonanywhere.com/legal/versions \
      --samples 50 --warmups 5 --csv /tmp/nepalkings-latency.csv
"""

from __future__ import annotations

import argparse
import csv
import math
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


@dataclass
class Sample:
    target: str
    mode: str
    index: int
    status: int | None
    dns_ms: float | None = None
    connect_ms: float | None = None
    tls_ms: float | None = None
    ttfb_ms: float | None = None
    preflight_ms: float | None = None
    request_ms: float | None = None
    total_ms: float | None = None
    error: str = ""

    @property
    def successful(self) -> bool:
        return (
            self.error == ""
            and self.status is not None
            and 200 <= self.status < 400
            and self.total_ms is not None
        )


def _parse_target(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("target must use NAME=https://URL")
    name, url = value.split("=", 1)
    name = name.strip()
    url = url.strip()
    if not name:
        raise argparse.ArgumentTypeError("target name cannot be empty")
    if not url.startswith("https://"):
        raise argparse.ArgumentTypeError("target URL must start with https://")
    return name, url


def _parse_header(value: str) -> tuple[str, str]:
    if ":" not in value:
        raise argparse.ArgumentTypeError("header must use 'Name: value'")
    name, header_value = value.split(":", 1)
    name = name.strip()
    if not name:
        raise argparse.ArgumentTypeError("header name cannot be empty")
    return name, header_value.strip()


def _cache_busted(url: str, target: str, index: int) -> str:
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    query.append(("nk_bench", f"{target}-{index}-{time.time_ns()}"))
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


def _rotated_targets(
    targets: list[tuple[str, str]], index: int
) -> list[tuple[str, str]]:
    offset = index % len(targets)
    return targets[offset:] + targets[:offset]


def _cold_request(
    name: str,
    url: str,
    index: int,
    timeout: float,
    headers: list[tuple[str, str]],
    cache_bust: bool,
) -> Sample:
    request_url = _cache_busted(url, name, index) if cache_bust else url
    write_out = (
        "%{http_code}|%{time_namelookup}|%{time_connect}|"
        "%{time_appconnect}|%{time_starttransfer}|%{time_total}"
    )
    command = [
        "curl",
        "--silent",
        "--show-error",
        "--output",
        "/dev/null",
        "--connect-timeout",
        str(min(timeout, 10.0)),
        "--max-time",
        str(timeout),
        "--header",
        "Cache-Control: no-cache",
    ]
    for header_name, header_value in headers:
        command.extend(["--header", f"{header_name}: {header_value}"])
    command.extend(["--write-out", write_out, "--url", request_url])

    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout + 5.0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return Sample(name, "cold", index, None, error=str(exc))

    if completed.returncode != 0:
        error = completed.stderr.strip() or f"curl exited {completed.returncode}"
        return Sample(name, "cold", index, None, error=error)

    try:
        status, dns, connect, tls, ttfb, total = completed.stdout.strip().split("|")
        dns_seconds = float(dns)
        connect_seconds = float(connect)
        tls_seconds = float(tls)
        return Sample(
            target=name,
            mode="cold",
            index=index,
            status=int(status),
            dns_ms=dns_seconds * 1000.0,
            connect_ms=max(0.0, connect_seconds - dns_seconds) * 1000.0,
            tls_ms=max(0.0, tls_seconds - connect_seconds) * 1000.0,
            ttfb_ms=float(ttfb) * 1000.0,
            total_ms=float(total) * 1000.0,
        )
    except (TypeError, ValueError) as exc:
        return Sample(
            name,
            "cold",
            index,
            None,
            error=f"could not parse curl output {completed.stdout!r}: {exc}",
        )


def _warm_request(
    session,
    name: str,
    url: str,
    index: int,
    timeout: float,
    cache_bust: bool,
) -> Sample:
    request_url = _cache_busted(url, name, index) if cache_bust else url
    started = time.perf_counter()
    try:
        response = session.get(request_url, timeout=timeout)
        response.content
    except Exception as exc:  # requests raises a family of runtime exceptions
        return Sample(name, "warm", index, None, error=str(exc))
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return Sample(
        target=name,
        mode="warm",
        index=index,
        status=response.status_code,
        total_ms=elapsed_ms,
    )


def _cors_request(
    session,
    name: str,
    url: str,
    index: int,
    timeout: float,
    cache_bust: bool,
    origin: str,
) -> Sample:
    """Measure an OPTIONS preflight followed by an authorized-style GET."""
    request_url = _cache_busted(url, name, index) if cache_bust else url
    preflight_headers = {
        "Origin": origin,
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "authorization",
    }

    started = time.perf_counter()
    try:
        preflight = session.options(
            request_url,
            headers=preflight_headers,
            timeout=timeout,
        )
        preflight.content
    except Exception as exc:
        return Sample(name, "cors", index, None, error=f"preflight: {exc}")
    preflight_ms = (time.perf_counter() - started) * 1000.0

    if not 200 <= preflight.status_code < 400:
        return Sample(
            name,
            "cors",
            index,
            preflight.status_code,
            preflight_ms=preflight_ms,
            total_ms=preflight_ms,
            error=f"preflight HTTP {preflight.status_code}",
        )

    allow_origin = preflight.headers.get("Access-Control-Allow-Origin")
    allow_headers = preflight.headers.get("Access-Control-Allow-Headers", "").lower()
    if allow_origin != origin or "authorization" not in allow_headers:
        return Sample(
            name,
            "cors",
            index,
            preflight.status_code,
            preflight_ms=preflight_ms,
            total_ms=preflight_ms,
            error=(
                "preflight policy mismatch: "
                f"origin={allow_origin!r}, headers={allow_headers!r}"
            ),
        )

    request_started = time.perf_counter()
    try:
        response = session.get(
            request_url,
            headers={
                "Origin": origin,
                "Authorization": "Bearer benchmark-invalid",
            },
            timeout=timeout,
        )
        response.content
    except Exception as exc:
        request_ms = (time.perf_counter() - request_started) * 1000.0
        return Sample(
            name,
            "cors",
            index,
            None,
            preflight_ms=preflight_ms,
            request_ms=request_ms,
            total_ms=preflight_ms + request_ms,
            error=f"GET: {exc}",
        )

    request_ms = (time.perf_counter() - request_started) * 1000.0
    return Sample(
        target=name,
        mode="cors",
        index=index,
        status=response.status_code,
        preflight_ms=preflight_ms,
        request_ms=request_ms,
        total_ms=preflight_ms + request_ms,
    )


def _percentile(values: Iterable[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return float("nan")
    rank = max(1, math.ceil((percentile / 100.0) * len(ordered)))
    return ordered[rank - 1]


def _fmt(value: float | None) -> str:
    if value is None or math.isnan(value):
        return "-"
    return f"{value:.1f}"


def _print_summary(samples: list[Sample], targets: list[tuple[str, str]]) -> None:
    print()
    print("Latency summary (milliseconds)")
    print(
        f"{'mode':<6} {'target':<14} {'ok/total':<10} "
        f"{'p50':>9} {'p95':>9} {'mean':>9} {'ttfb p50':>10} {'tls p50':>9}"
    )
    print("-" * 92)

    for mode in ("cold", "warm", "cors"):
        for name, _url in targets:
            group = [s for s in samples if s.mode == mode and s.target == name]
            if not group:
                continue
            successful = [s for s in group if s.successful]
            totals = [s.total_ms for s in successful if s.total_ms is not None]
            ttfb = [s.ttfb_ms for s in successful if s.ttfb_ms is not None]
            tls = [s.tls_ms for s in successful if s.tls_ms is not None]
            mean = sum(totals) / len(totals) if totals else float("nan")
            print(
                f"{mode:<6} {name:<14} {len(successful):>3}/{len(group):<6} "
                f"{_fmt(_percentile(totals, 50)):>9} "
                f"{_fmt(_percentile(totals, 95)):>9} "
                f"{_fmt(mean):>9} "
                f"{_fmt(_percentile(ttfb, 50)):>10} "
                f"{_fmt(_percentile(tls, 50)):>9}"
            )

    cors_samples = [sample for sample in samples if sample.mode == "cors"]
    if cors_samples:
        print()
        print("CORS pair breakdown (milliseconds)")
        print(
            f"{'target':<14} {'preflight p50':>15} {'preflight p95':>15} "
            f"{'GET p50':>10} {'GET p95':>10} {'pair p95':>10}"
        )
        print("-" * 78)
        for name, _url in targets:
            successful = [
                sample
                for sample in cors_samples
                if sample.target == name and sample.successful
            ]
            preflight = [
                sample.preflight_ms
                for sample in successful
                if sample.preflight_ms is not None
            ]
            requests = [
                sample.request_ms
                for sample in successful
                if sample.request_ms is not None
            ]
            totals = [
                sample.total_ms
                for sample in successful
                if sample.total_ms is not None
            ]
            print(
                f"{name:<14} "
                f"{_fmt(_percentile(preflight, 50)):>15} "
                f"{_fmt(_percentile(preflight, 95)):>15} "
                f"{_fmt(_percentile(requests, 50)):>10} "
                f"{_fmt(_percentile(requests, 95)):>10} "
                f"{_fmt(_percentile(totals, 95)):>10}"
            )

    failures = [sample for sample in samples if not sample.successful]
    if failures:
        print()
        print(f"Failures/non-success responses: {len(failures)}")
        for sample in failures[:10]:
            detail = sample.error or f"HTTP {sample.status}"
            print(f"  {sample.mode}/{sample.target} #{sample.index}: {detail}")
        if len(failures) > 10:
            print(f"  ... and {len(failures) - 10} more")


def _write_csv(path: Path, samples: list[Sample]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(samples[0]).keys()))
        writer.writeheader()
        writer.writerows(asdict(sample) for sample in samples)
    print(f"Raw samples: {path}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare cold and warm HTTPS latency across API deployments."
    )
    parser.add_argument(
        "--target",
        action="append",
        type=_parse_target,
        required=True,
        metavar="NAME=URL",
        help="deployment target; specify at least two",
    )
    parser.add_argument("--samples", type=int, default=30)
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument(
        "--mode",
        choices=("both", "cold", "warm", "cors", "all"),
        default="both",
    )
    parser.add_argument(
        "--cors-origin",
        default="https://mstieffe.github.io",
        help="Origin used by --mode cors/all",
    )
    parser.add_argument(
        "--header",
        action="append",
        type=_parse_header,
        default=[],
        metavar="'NAME: VALUE'",
        help="shared request header; may be repeated",
    )
    parser.add_argument(
        "--no-cache-bust",
        action="store_true",
        help="do not append a unique nk_bench query parameter",
    )
    parser.add_argument("--csv", type=Path, help="optional raw-sample CSV path")
    args = parser.parse_args()

    if len(args.target) < 2:
        parser.error("provide at least two --target values")
    if args.samples < 1 or args.warmups < 0:
        parser.error("--samples must be positive and --warmups cannot be negative")
    if len({name for name, _url in args.target}) != len(args.target):
        parser.error("target names must be unique")
    if args.mode in ("both", "cold", "all") and shutil.which("curl") is None:
        parser.error("curl is required for cold measurements")

    cache_bust = not args.no_cache_bust
    all_samples: list[Sample] = []

    print("Targets:")
    for name, url in args.target:
        print(f"  {name}: {url}")
    print(
        f"Protocol: {args.warmups} warmups, {args.samples} measured requests, "
        f"sequential/alternating, mode={args.mode}"
    )

    if args.mode in ("both", "cold", "all"):
        print("Warming cold-request endpoints...")
        for index in range(args.warmups):
            for name, url in _rotated_targets(args.target, index):
                _cold_request(
                    name,
                    url,
                    -(index + 1),
                    args.timeout,
                    args.header,
                    cache_bust,
                )
        print("Measuring cold connections...")
        for index in range(args.samples):
            for name, url in _rotated_targets(args.target, index):
                all_samples.append(
                    _cold_request(
                        name,
                        url,
                        index + 1,
                        args.timeout,
                        args.header,
                        cache_bust,
                    )
                )

    if args.mode in ("both", "warm", "cors", "all"):
        try:
            import requests
        except ImportError:
            print(
                "requests is required for warm measurements; install server "
                "requirements or use --mode cold",
                file=sys.stderr,
            )
            return 2

        sessions = {}
        for name, _url in args.target:
            session = requests.Session()
            session.headers.update({"Cache-Control": "no-cache"})
            session.headers.update(dict(args.header))
            sessions[name] = session

        if args.mode in ("both", "warm", "all"):
            print("Warming persistent sessions...")
            for index in range(args.warmups):
                for name, url in _rotated_targets(args.target, index):
                    _warm_request(
                        sessions[name],
                        name,
                        url,
                        -(index + 1),
                        args.timeout,
                        cache_bust,
                    )
            print("Measuring warm/persistent connections...")
            for index in range(args.samples):
                for name, url in _rotated_targets(args.target, index):
                    all_samples.append(
                        _warm_request(
                            sessions[name],
                            name,
                            url,
                            index + 1,
                            args.timeout,
                            cache_bust,
                        )
                    )

        if args.mode in ("cors", "all"):
            print(
                "Warming CORS OPTIONS + authorized-style GET pairs "
                f"for origin {args.cors_origin}..."
            )
            for index in range(args.warmups):
                for name, url in _rotated_targets(args.target, index):
                    _cors_request(
                        sessions[name],
                        name,
                        url,
                        -(index + 1),
                        args.timeout,
                        cache_bust,
                        args.cors_origin,
                    )
            print("Measuring CORS preflight + GET pairs...")
            for index in range(args.samples):
                for name, url in _rotated_targets(args.target, index):
                    all_samples.append(
                        _cors_request(
                            sessions[name],
                            name,
                            url,
                            index + 1,
                            args.timeout,
                            cache_bust,
                            args.cors_origin,
                        )
                    )
        for session in sessions.values():
            session.close()

    _print_summary(all_samples, args.target)
    if args.csv and all_samples:
        _write_csv(args.csv, all_samples)
    return 0 if all(sample.successful for sample in all_samples) else 1


if __name__ == "__main__":
    raise SystemExit(main())
