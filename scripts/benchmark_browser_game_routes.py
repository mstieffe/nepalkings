#!/usr/bin/env python3
"""Measure authenticated Nepal Kings routes from a real browser origin.

The script creates one clearly named synthetic user on the selected test
deployment, completes the starter-card reveal, finds the recommended first
conquest land, and measures Collection, Conquer config, kingdom map, and the
combined Conquer-screen request pair from headless Chrome.

Run this only against a staging/test database. The synthetic account is
intentionally retained as test data unless the test database is reset.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import secrets
import shutil
import statistics
import tempfile
import time
from typing import Any

import requests

from mobile_ui_review.capture_web import Cdp, launch_chrome, wait_for_target


def _nearest_rank(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * percentile) - 1)]


def _request_json(
    session: requests.Session,
    method: str,
    url: str,
    *,
    token: str | None = None,
    data: dict[str, str] | None = None,
    json_data: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], float]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    started = time.perf_counter()
    response = session.request(
        method,
        url,
        headers=headers,
        data=data,
        json=json_data,
        timeout=30,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"{method} {url} returned HTTP {response.status_code} "
            "with a non-JSON body"
        ) from exc
    if not response.ok:
        raise RuntimeError(
            f"{method} {url} returned HTTP {response.status_code}: {payload}"
        )
    return payload, elapsed_ms


def _create_synthetic_user(
    session: requests.Session,
    base_url: str,
) -> tuple[str, str, int, dict[str, float]]:
    suffix = datetime.now(timezone.utc).strftime("%m%d%H%M%S")
    username = f"nkperf_{suffix}_{secrets.token_hex(2)}"
    password = secrets.token_urlsafe(24)

    registered, register_ms = _request_json(
        session,
        "POST",
        f"{base_url}/auth/register",
        data={
            "username": username,
            "password": password,
            "age_confirmed": "true",
            "terms_accepted": "true",
            "privacy_accepted": "true",
        },
    )
    if not registered.get("success") or not registered.get("token"):
        raise RuntimeError(f"Registration failed: {registered}")
    token = str(registered["token"])

    welcome, welcome_ms = _request_json(
        session,
        "POST",
        f"{base_url}/onboarding/mark_tip",
        token=token,
        json_data={"tip_key": "welcome"},
    )
    if not welcome.get("success"):
        raise RuntimeError(f"Welcome acknowledgement failed: {welcome}")

    prepared, prepare_ms = _request_json(
        session,
        "POST",
        f"{base_url}/onboarding/starter_reveal/prepare",
        token=token,
    )
    if not prepared.get("success"):
        raise RuntimeError(f"Starter reveal prepare failed: {prepared}")

    collection_hints, collection_hints_ms = _request_json(
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
    )
    if not collection_hints.get("success"):
        raise RuntimeError(
            f"Collection hint acknowledgement failed: {collection_hints}"
        )

    completed, complete_ms = _request_json(
        session,
        "POST",
        f"{base_url}/onboarding/starter_reveal/complete",
        token=token,
    )
    if not completed.get("success"):
        raise RuntimeError(f"Starter reveal complete failed: {completed}")

    kingdom_map, map_ms = _request_json(
        session,
        "GET",
        f"{base_url}/kingdom/map",
        token=token,
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
        raise RuntimeError("No conquerable land found in /kingdom/map")

    _config, first_config_ms = _request_json(
        session,
        "GET",
        f"{base_url}/kingdom/conquer/config?land_id={int(land_id)}",
        token=token,
    )

    return username, token, int(land_id), {
        "register": register_ms,
        "welcome": welcome_ms,
        "starter_prepare": prepare_ms,
        "collection_hints": collection_hints_ms,
        "starter_complete": complete_ms,
        "first_map": map_ms,
        "first_conquer_config": first_config_ms,
    }


def _browser_expression(
    *,
    base_url: str,
    token: str,
    land_id: int,
    warmups: int,
    samples: int,
) -> str:
    config = json.dumps(
        {
            "baseUrl": base_url,
            "token": token,
            "landId": land_id,
            "warmups": warmups,
            "samples": samples,
        }
    )
    return f"""
(async () => {{
  const cfg = {config};
  const definitions = [
    {{name: "collection", paths: ["/collection/cards"]}},
    {{name: "conquer_config", paths: [
      `/kingdom/conquer/config?land_id=${{cfg.landId}}`
    ]}},
    {{name: "kingdom_map", paths: ["/kingdom/map"]}},
    {{name: "conquer_screen_pair", paths: [
      `/kingdom/conquer/config?land_id=${{cfg.landId}}`,
      "/collection/cards"
    ]}}
  ];
  const rows = [];

  async function measure(definition, sample, warmup) {{
    const nonce = `${{definition.name}}-${{sample}}-${{Date.now()}}`;
    const urls = definition.paths.map(path => {{
      const joiner = path.includes("?") ? "&" : "?";
      return `${{cfg.baseUrl}}${{path}}${{joiner}}nk_browser_bench=${{nonce}}`;
    }});
    const started = performance.now();
    try {{
      const responses = await Promise.all(urls.map(url => fetch(url, {{
        cache: "no-store",
        headers: {{Authorization: `Bearer ${{cfg.token}}`}}
      }})));
      const bodies = await Promise.all(responses.map(response => response.arrayBuffer()));
      rows.push({{
        route: definition.name,
        sample,
        warmup,
        ok: responses.every(response => response.ok),
        statuses: responses.map(response => response.status),
        bytes: bodies.reduce((total, body) => total + body.byteLength, 0),
        ms: performance.now() - started
      }});
    }} catch (error) {{
      rows.push({{
        route: definition.name,
        sample,
        warmup,
        ok: false,
        statuses: [],
        bytes: 0,
        ms: performance.now() - started,
        error: String(error)
      }});
    }}
  }}

  for (let i = 0; i < cfg.warmups; i++) {{
    const order = i % 2 ? [...definitions].reverse() : definitions;
    for (const definition of order) await measure(definition, i + 1, true);
  }}
  for (let i = 0; i < cfg.samples; i++) {{
    const order = i % 2 ? [...definitions].reverse() : definitions;
    for (const definition of order) await measure(definition, i + 1, false);
  }}
  return {{origin: location.origin, userAgent: navigator.userAgent, rows}};
}})()
"""


def _run_browser(
    *,
    origin_url: str,
    base_url: str,
    token: str,
    land_id: int,
    warmups: int,
    samples: int,
    chrome_path: str,
    debug_port: int,
) -> dict[str, Any]:
    profile = Path(tempfile.mkdtemp(prefix="nk-api-bench-cdp-"))
    chrome = launch_chrome(chrome_path, debug_port, profile)
    cdp: Cdp | None = None
    try:
        cdp = Cdp(wait_for_target(debug_port))
        cdp.command("Page.enable")
        cdp.command("Runtime.enable")
        cdp.command("Page.navigate", {"url": origin_url})

        deadline = time.time() + 20
        while time.time() < deadline:
            result = cdp.command(
                "Runtime.evaluate",
                {
                    "expression": "document.readyState",
                    "returnByValue": True,
                },
            )
            if result.get("result", {}).get("value") in {"interactive", "complete"}:
                break
            time.sleep(0.2)
        else:
            raise TimeoutError(f"Browser origin did not load: {origin_url}")

        evaluated = cdp.command(
            "Runtime.evaluate",
            {
                "expression": _browser_expression(
                    base_url=base_url,
                    token=token,
                    land_id=land_id,
                    warmups=warmups,
                    samples=samples,
                ),
                "awaitPromise": True,
                "returnByValue": True,
            },
            timeout=max(120, samples * 20),
        )
        if evaluated.get("exceptionDetails"):
            raise RuntimeError(evaluated["exceptionDetails"])
        value = evaluated.get("result", {}).get("value")
        if not isinstance(value, dict):
            raise RuntimeError(f"Unexpected browser result: {evaluated}")
        return value
    finally:
        if cdp:
            try:
                cdp.command("Browser.close", timeout=2)
            except Exception:
                pass
            cdp.close()
        chrome.terminate()
        try:
            chrome.wait(timeout=5)
        except Exception:
            chrome.kill()
        shutil.rmtree(profile, ignore_errors=True)


def _print_summary(rows: list[dict[str, Any]]) -> None:
    measured = [row for row in rows if not row.get("warmup")]
    print("\nAuthenticated browser latency (milliseconds)")
    print(
        f"{'route':<22} {'ok/total':>10} {'p50':>9} {'p95':>9} "
        f"{'mean':>9} {'bytes':>11}"
    )
    print("-" * 76)
    for route in (
        "collection",
        "conquer_config",
        "conquer_screen_pair",
        "kingdom_map",
    ):
        route_rows = [row for row in measured if row.get("route") == route]
        ok_rows = [row for row in route_rows if row.get("ok")]
        if not ok_rows:
            print(f"{route:<22} {f'0/{len(route_rows)}':>10}")
            continue
        values = [float(row["ms"]) for row in ok_rows]
        mean_bytes = statistics.mean(int(row["bytes"]) for row in ok_rows)
        print(
            f"{route:<22} {f'{len(ok_rows)}/{len(route_rows)}':>10} "
            f"{_nearest_rank(values, 0.50):>9.1f} "
            f"{_nearest_rank(values, 0.95):>9.1f} "
            f"{statistics.mean(values):>9.1f} "
            f"{mean_bytes:>11.0f}"
        )


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "route",
        "sample",
        "warmup",
        "ok",
        "statuses",
        "bytes",
        "ms",
        "error",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            output = {field: row.get(field, "") for field in fields}
            output["statuses"] = json.dumps(output["statuses"])
            writer.writerow(output)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url",
        default="https://nepalkingz.eu.pythonanywhere.com",
    )
    parser.add_argument(
        "--origin-url",
        default="https://mstieffe.github.io/nepalkings/favicon.png",
        help="Small page on the same origin as the production GitHub Pages game",
    )
    parser.add_argument("--warmups", type=int, default=2)
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument(
        "--chrome",
        default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    )
    parser.add_argument("--debug-port", type=int, default=9224)
    parser.add_argument("--csv", type=Path)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    session = requests.Session()
    session.headers["User-Agent"] = "NepalKingsBrowserBenchmark/1.0"

    print(f"Creating synthetic test user on {base_url}...")
    username, token, land_id, setup_timings = _create_synthetic_user(
        session,
        base_url,
    )
    print(f"Synthetic user: {username} (test data; no email or PII)")
    print(f"Recommended conquer land: {land_id}")
    print(
        "One-time setup ms: "
        + ", ".join(
            f"{name}={elapsed:.1f}"
            for name, elapsed in setup_timings.items()
        )
    )
    print(
        f"Running {args.samples} real-browser samples per route "
        f"after {args.warmups} warmups..."
    )

    result = _run_browser(
        origin_url=args.origin_url,
        base_url=base_url,
        token=token,
        land_id=land_id,
        warmups=args.warmups,
        samples=args.samples,
        chrome_path=args.chrome,
        debug_port=args.debug_port,
    )
    print(f"Browser origin: {result.get('origin')}")
    rows = result.get("rows") or []
    _print_summary(rows)

    failed = [row for row in rows if not row.get("ok")]
    if failed:
        print(f"\nFailed browser requests: {len(failed)}")
        for row in failed[:5]:
            print(
                f"  {row.get('route')}: statuses={row.get('statuses')} "
                f"error={row.get('error', '')}"
            )

    if args.csv:
        _write_csv(args.csv, rows)
        print(f"Raw samples: {args.csv}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
