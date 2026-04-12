#!/usr/bin/env python3
# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Poll AI reasoning/debug telemetry from the Nepal Kings server.

Usage examples:
1) Login and auto-discover latest AI game:
   python poll_ai_debug.py --username alice --password secret

2) Use an existing token and explicit game id:
   python poll_ai_debug.py --token <TOKEN> --username alice --game-id 42 --once

3) Poll every 2 seconds and print full snapshots:
   python poll_ai_debug.py --username alice --password secret --interval 2 --show-all
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

import requests


def _fail(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(code)


def _post_form(url: str, data: dict[str, Any], timeout: float) -> dict[str, Any]:
    resp = requests.post(url, data=data, timeout=timeout)
    try:
        payload = resp.json()
    except Exception:
        _fail(f"Non-JSON response from {url} (status={resp.status_code})")

    if resp.status_code >= 400 or not payload.get("success", False):
        msg = payload.get("message") or payload.get("error") or f"status={resp.status_code}"
        _fail(f"Request failed for {url}: {msg}")

    return payload


def _get_json(url: str, params: dict[str, Any] | None, headers: dict[str, str], timeout: float) -> dict[str, Any]:
    resp = requests.get(url, params=params, headers=headers, timeout=timeout)
    try:
        payload = resp.json()
    except Exception:
        _fail(f"Non-JSON response from {url} (status={resp.status_code})")

    if resp.status_code == 404:
        msg = payload.get("message") or "not found"
        _fail(
            f"{url} returned 404 ({msg}). "
            "Make sure server is running the feature/ai-strategy-upgrade-v1 code and restarted."
        )

    if resp.status_code >= 400:
        msg = payload.get("message") or payload.get("error") or f"status={resp.status_code}"
        _fail(f"Request failed for {url}: {msg}")

    return payload


def login_for_token(server_url: str, username: str, password: str, timeout: float) -> str:
    url = f"{server_url}/auth/login"
    payload = _post_form(url, {"username": username, "password": password}, timeout=timeout)
    token = payload.get("token")
    if not token:
        _fail("Login succeeded but token missing in response")
    return str(token)


def fetch_games(server_url: str, username: str, timeout: float) -> list[dict[str, Any]]:
    url = f"{server_url}/games/get_games"
    payload = _get_json(url, params={"username": username}, headers={}, timeout=timeout)
    games = payload.get("games", [])
    if not isinstance(games, list):
        _fail("Unexpected get_games response: 'games' is not a list")
    return games


def select_game_id(games: list[dict[str, Any]]) -> int:
    if not games:
        _fail("No games found for this user")

    def has_ai(game: dict[str, Any]) -> bool:
        players = game.get("players", [])
        if not isinstance(players, list):
            return False
        return any(str(p.get("username", "")).startswith("[AI]") for p in players)

    games_sorted = sorted(games, key=lambda g: int(g.get("id", 0)), reverse=True)
    ai_games = [g for g in games_sorted if has_ai(g)]
    chosen = ai_games[0] if ai_games else games_sorted[0]

    try:
        return int(chosen.get("id"))
    except (TypeError, ValueError):
        _fail("Could not determine game id from get_games response")


def fetch_ai_debug(
    server_url: str,
    token: str,
    game_id: int,
    max_notes: int,
    max_events: int,
    timeout: float,
) -> dict[str, Any]:
    url = f"{server_url}/games/get_ai_debug"
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "game_id": int(game_id),
        "max_notes": int(max_notes),
        "max_events": int(max_events),
    }
    payload = _get_json(url, params=params, headers=headers, timeout=timeout)
    if not payload.get("success", False):
        msg = payload.get("message") or "unknown error"
        _fail(f"get_ai_debug failed: {msg}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Poll AI reasoning and planner rollout telemetry")
    parser.add_argument("--server-url", default="http://localhost:5000", help="Base server URL")
    parser.add_argument("--username", required=True, help="Human username")
    parser.add_argument("--password", help="Human password (required if --token not provided)")
    parser.add_argument("--token", help="Existing bearer token (skips login)")
    parser.add_argument("--game-id", type=int, help="Game id to inspect (auto-discovered if omitted)")
    parser.add_argument("--interval", type=float, default=3.0, help="Polling interval in seconds")
    parser.add_argument("--max-notes", type=int, default=20, help="Max strategy notes returned")
    parser.add_argument("--max-events", type=int, default=40, help="Max planner events returned")
    parser.add_argument("--timeout", type=float, default=8.0, help="HTTP timeout in seconds")
    parser.add_argument("--once", action="store_true", help="Fetch one snapshot and exit")
    parser.add_argument("--show-all", action="store_true", help="Print full JSON each poll")
    args = parser.parse_args()

    server_url = args.server_url.rstrip("/")
    token = args.token
    if not token:
        if not args.password:
            _fail("--password is required when --token is not provided")
        token = login_for_token(server_url, args.username, args.password, timeout=args.timeout)

    game_id = args.game_id
    if game_id is None:
        games = fetch_games(server_url, args.username, timeout=args.timeout)
        game_id = select_game_id(games)

    print(f"Connected to {server_url}")
    print(f"Using game_id={game_id}")

    last_note = None
    last_event_repr = None

    while True:
        payload = fetch_ai_debug(
            server_url,
            token,
            game_id,
            max_notes=args.max_notes,
            max_events=args.max_events,
            timeout=args.timeout,
        )

        if args.show_all:
            print(json.dumps(payload, indent=2, ensure_ascii=True))
        else:
            ai_debug = payload.get("ai_debug", {})
            notes = ai_debug.get("strategy_notes", [])
            events = ai_debug.get("planner_events", [])

            note = notes[-1] if notes else None
            event = events[-1] if events else None
            event_repr = json.dumps(event, sort_keys=True) if event is not None else None

            stamp = time.strftime("%Y-%m-%d %H:%M:%S")
            changed = (note != last_note) or (event_repr != last_event_repr)

            if changed:
                print(f"[{stamp}] notes={len(notes)} events={len(events)}")
                if note is not None:
                    print(f"  latest_note: {note}")
                if event is not None:
                    print(f"  latest_event: {json.dumps(event, ensure_ascii=True)}")
            else:
                print(f"[{stamp}] no change (notes={len(notes)}, events={len(events)})")

            last_note = note
            last_event_repr = event_repr

        if args.once:
            break

        time.sleep(max(0.2, float(args.interval)))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
