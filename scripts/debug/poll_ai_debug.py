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

4) Show verbose per-candidate plan details:
    python poll_ai_debug.py --username alice --password secret --show-candidates --verbose
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

import requests


def _fail(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(code)


def _connection_hint(url: str) -> str:
    """Return a short actionable hint for connection failures."""
    lower = str(url or "").lower()
    if "localhost" in lower or "127.0.0.1" in lower:
        return (
            "No server is listening on localhost. Start a local server, or use "
            "--server-url https://nepalkings.pythonanywhere.com"
        )
    return "Check that the server is reachable and the URL is correct"


def _post_form(url: str, data: dict[str, Any], timeout: float) -> dict[str, Any]:
    try:
        resp = requests.post(url, data=data, timeout=timeout)
    except requests.exceptions.RequestException as exc:
        _fail(f"Connection failed for {url}: {exc}. {_connection_hint(url)}")

    try:
        payload = resp.json()
    except Exception:
        _fail(f"Non-JSON response from {url} (status={resp.status_code})")

    if resp.status_code >= 400 or not payload.get("success", False):
        msg = payload.get("message") or payload.get("error") or f"status={resp.status_code}"
        _fail(f"Request failed for {url}: {msg}")

    return payload


def _get_json(url: str, params: dict[str, Any] | None, headers: dict[str, str], timeout: float) -> dict[str, Any]:
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=timeout)
    except requests.exceptions.RequestException as exc:
        _fail(f"Connection failed for {url}: {exc}. {_connection_hint(url)}")

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


def _latest_candidate_summaries(events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str | None]:
    """Return the newest candidate summaries from planner events, if present."""
    for event in reversed(events or []):
        if not isinstance(event, dict):
            continue
        candidates = event.get("candidates")
        if isinstance(candidates, list) and candidates:
            return candidates, str(event.get("type") or "unknown")
    return [], None


def _format_candidate_verbose_lines(candidate: dict[str, Any]) -> list[str]:
    """Render full candidate details for human-friendly verbose output."""
    lines: list[str] = []

    strategy = candidate.get("strategy_name")
    if strategy:
        lines.append(f"      strategy: {strategy}")

    expected_power_diff = candidate.get("expected_power_diff")
    expected_bm_power = candidate.get("expected_battle_move_power")
    lines.append(
        "      expected: "
        f"power_diff={expected_power_diff} "
        f"battle_move_power={expected_bm_power}"
    )

    planned_figure = candidate.get("planned_battle_figure")
    if isinstance(planned_figure, dict) and planned_figure:
        lines.append(
            "      planned_figure: "
            f"{planned_figure.get('name')} ({planned_figure.get('field')}, "
            f"state={planned_figure.get('state')}, "
            f"power~{planned_figure.get('power_estimate')})"
        )
        if (
            planned_figure.get('assumed_main_draws_per_turn') is not None
            or planned_figure.get('assumed_side_draws_per_turn') is not None
        ):
            lines.append(
                "      assumed_draws_per_turn: "
                f"main={planned_figure.get('assumed_main_draws_per_turn')} "
                f"side={planned_figure.get('assumed_side_draws_per_turn')}"
            )

    likely_opp = candidate.get("likely_opponent_figure")
    if isinstance(likely_opp, dict) and likely_opp:
        lines.append(
            "      likely_opponent: "
            f"{likely_opp.get('name')} "
            f"(power~{likely_opp.get('power_estimate')}, p={likely_opp.get('probability')})"
        )

    planned_moves = candidate.get("planned_battle_moves")
    if isinstance(planned_moves, list) and planned_moves:
        move_text = ", ".join(
            f"{m.get('rank')}{str(m.get('suit') or '')[:1]}({m.get('value')})"
            for m in planned_moves
            if isinstance(m, dict)
        )
        if move_text:
            lines.append(f"      planned_moves: {move_text}")

    score_breakdown = candidate.get("score_breakdown")
    if isinstance(score_breakdown, dict) and score_breakdown:
        breakdown_text = ", ".join(
            f"{k}={v}"
            for k, v in score_breakdown.items()
        )
        lines.append(f"      score_breakdown: {breakdown_text}")

    turn_steps = candidate.get("turn_steps")
    if isinstance(turn_steps, list) and turn_steps:
        lines.append("      turn_steps:")
        for idx, step in enumerate(turn_steps, start=1):
            lines.append(f"        {idx}. {step}")

    notes = candidate.get("notes")
    if isinstance(notes, list) and notes:
        for note in notes:
            lines.append(f"      note: {note}")

    return lines


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
    parser.add_argument(
        "--server-url",
        default=os.getenv("POLL_AI_SERVER_URL", "https://nepalkings.pythonanywhere.com"),
        help="Base server URL",
    )
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
    parser.add_argument(
        "--show-candidates",
        action="store_true",
        help="Print compact planner candidate summaries when available",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="When showing candidates, print full candidate details",
    )
    args = parser.parse_args()

    if args.verbose:
        args.show_candidates = True

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
                if args.show_candidates:
                    candidates, source_event_type = _latest_candidate_summaries(events)
                    if candidates:
                        print(f"  candidates ({len(candidates)}) from {source_event_type}:")
                        for cand in candidates:
                            print(
                                "    - "
                                f"plan={cand.get('plan_id')} "
                                f"action={cand.get('seed_action_id')} "
                                f"score={cand.get('total_score')} "
                                f"feas={cand.get('feasibility_probability')} "
                                f"type={cand.get('action_type')}"
                            )
                            if cand.get("action_description"):
                                print(f"      action_desc: {cand.get('action_description')}")
                            if cand.get("step_preview"):
                                print(f"      step_preview: {cand.get('step_preview')}")
                            if args.verbose:
                                for line in _format_candidate_verbose_lines(cand):
                                    print(line)
                    else:
                        print("  candidates: none yet")
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
