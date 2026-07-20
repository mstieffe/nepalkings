#!/usr/bin/env python3
"""Exercise simultaneous two-account Duel acceptance on staging.

The script creates two synthetic accounts and one human challenge, submits the
same acceptance concurrently as both participants, and verifies that every
response resolves to one canonical game. The synthetic accounts and game are
intentionally retained as clearly named staging evidence.

Never run this against production unless the operator has created a backup,
enabled a controlled maintenance exception, and passed --allow-production.
"""

from __future__ import annotations

import argparse
import json
import re
import secrets
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import requests


STAGING_BASE_URL = "https://nepalkingz.eu.pythonanywhere.com"
SYNTHETIC_USERNAME_RE = re.compile(r"^nkduel_[ab]_[0-9]{10}_[0-9a-f]{4}$")


@dataclass(frozen=True)
class ResponseRecord:
    actor: str
    elapsed_ms: float
    payload: Mapping[str, Any]
    status: int


def _request_json(
    session: requests.Session,
    method: str,
    url: str,
    *,
    token: str | None = None,
    data: Mapping[str, str] | None = None,
    timeout: float = 30.0,
) -> tuple[requests.Response, Mapping[str, Any], float]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    started = time.perf_counter()
    response = session.request(
        method,
        url,
        data=data,
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
    return response, payload, elapsed_ms


def _require_success(
    response: requests.Response,
    payload: Mapping[str, Any],
    operation: str,
) -> None:
    if not response.ok or payload.get("success") is False:
        safe_payload = {
            key: value
            for key, value in payload.items()
            if key.lower() not in {"token", "password"}
        }
        raise RuntimeError(
            f"{operation} failed with HTTP {response.status_code}: "
            f"{safe_payload}"
        )


def _register(
    session: requests.Session,
    base_url: str,
    username: str,
    password: str,
    timeout: float,
) -> str:
    response, payload, _elapsed_ms = _request_json(
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
    _require_success(response, payload, f"register {username}")
    token = payload.get("token")
    if not isinstance(token, str) or not token:
        raise RuntimeError(f"register {username} returned no token")
    return token


def _bootstrap_staging_gold(
    usernames: Sequence[str],
    *,
    ssh_identity: Path,
    known_hosts: Path,
    gold: int = 100,
) -> None:
    if (
        len(usernames) != 2
        or any(not SYNTHETIC_USERNAME_RE.fullmatch(name) for name in usernames)
    ):
        raise RuntimeError("refusing to top up non-synthetic usernames")
    if gold < 1:
        raise RuntimeError("staging gold bootstrap must be positive")

    quoted_names = ", ".join(f"'{name}'" for name in usernames)
    remote_command = (
        "set -a; "
        ". /home/nepalkingz/.config/nepalkings/staging.env; "
        "set +a; "
        "db_url=${DB_URL/postgresql+psycopg:/postgresql:}; "
        f"psql \"$db_url\" --set ON_ERROR_STOP=1 --command="
        f"\"UPDATE \\\"user\\\" SET gold = {gold} "
        f"WHERE username IN ({quoted_names});\"; "
        "unset db_url DB_URL"
    )
    result = subprocess.run(
        [
            "ssh",
            "-i",
            str(ssh_identity.expanduser()),
            "-o",
            f"UserKnownHostsFile={known_hosts.expanduser()}",
            "nepalkingz@ssh.eu.pythonanywhere.com",
            remote_command,
        ],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )
    if result.returncode != 0 or "UPDATE 2" not in result.stdout:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(
            f"staging synthetic-gold bootstrap failed: {detail}"
        )


def run_smoke(
    base_url: str,
    timeout: float,
    *,
    bootstrap_staging_gold: bool = False,
    ssh_identity: Path = Path("~/.ssh/nepalkings_pythonanywhere_eu"),
    known_hosts: Path = Path("/tmp/nepalkings_pa_eu_known_hosts"),
) -> dict[str, Any]:
    session = requests.Session()
    session.headers["User-Agent"] = "NepalKings-Duel-Concurrency-Smoke/1.0"
    suffix = datetime.now(timezone.utc).strftime("%m%d%H%M%S")
    username1 = f"nkduel_a_{suffix}_{secrets.token_hex(2)}"
    username2 = f"nkduel_b_{suffix}_{secrets.token_hex(2)}"
    password1 = secrets.token_urlsafe(24)
    password2 = secrets.token_urlsafe(24)
    token1 = _register(session, base_url, username1, password1, timeout)
    token2 = _register(session, base_url, username2, password2, timeout)
    if bootstrap_staging_gold:
        if base_url != STAGING_BASE_URL:
            raise RuntimeError(
                "--bootstrap-staging-gold requires the exact staging URL"
            )
        _bootstrap_staging_gold(
            [username1, username2],
            ssh_identity=ssh_identity,
            known_hosts=known_hosts,
        )

    response, payload, _elapsed_ms = _request_json(
        session,
        "POST",
        f"{base_url}/challenges/create_challenge",
        token=token1,
        data={
            "challenger": username1,
            "game_limit": "10",
            "opponent": username2,
            "stake": "10",
        },
        timeout=timeout,
    )
    _require_success(response, payload, "create challenge")

    response, payload, _elapsed_ms = _request_json(
        session,
        "GET",
        f"{base_url}/challenges/open_challenges?username={username1}",
        token=token1,
        timeout=timeout,
    )
    if not response.ok:
        raise RuntimeError(
            f"open challenges failed with HTTP {response.status_code}"
        )
    challenges = payload.get("challenges")
    if not isinstance(challenges, list):
        raise RuntimeError("open challenges returned no list")
    matches = [
        challenge
        for challenge in challenges
        if challenge.get("challenger_name") == username1
        and challenge.get("challenged_name") == username2
        and challenge.get("status") == "open"
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"expected one matching open challenge, found {len(matches)}"
        )
    challenge_id = int(matches[0]["id"])

    barrier = threading.Barrier(2)

    def accept(actor: str, token: str) -> ResponseRecord:
        worker_session = requests.Session()
        worker_session.headers["User-Agent"] = session.headers["User-Agent"]
        barrier.wait(timeout=timeout)
        accept_response, accept_payload, elapsed_ms = _request_json(
            worker_session,
            "POST",
            f"{base_url}/games/create_game",
            token=token,
            data={"challenge_id": str(challenge_id)},
            timeout=timeout,
        )
        return ResponseRecord(
            actor=actor,
            elapsed_ms=elapsed_ms,
            payload=accept_payload,
            status=accept_response.status_code,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(accept, "challenger", token1),
            executor.submit(accept, "challenged", token2),
        ]
        records = [future.result(timeout=timeout + 5) for future in futures]

    for record in records:
        if record.status != 200 or record.payload.get("success") is not True:
            raise RuntimeError(
                f"{record.actor} accept failed: HTTP {record.status} "
                f"{record.payload}"
            )
    game_ids = {
        int(record.payload.get("game", {}).get("id"))
        for record in records
    }
    if len(game_ids) != 1:
        raise RuntimeError(f"concurrent accepts created different games: {game_ids}")
    game_id = game_ids.pop()

    repeated_response, repeated_payload, repeated_ms = _request_json(
        session,
        "POST",
        f"{base_url}/games/create_game",
        token=token1,
        data={"challenge_id": str(challenge_id)},
        timeout=timeout,
    )
    _require_success(repeated_response, repeated_payload, "repeat acceptance")
    if int(repeated_payload.get("game", {}).get("id")) != game_id:
        raise RuntimeError("repeat acceptance did not return the canonical game")

    viewer_checks: list[dict[str, Any]] = []
    for actor, token in (("challenger", token1), ("challenged", token2)):
        game_response, game_payload, elapsed_ms = _request_json(
            session,
            "GET",
            f"{base_url}/games/get_game?game_id={game_id}",
            token=token,
            timeout=timeout,
        )
        _require_success(game_response, game_payload, f"{actor} game read")
        returned_game = game_payload.get("game")
        if not isinstance(returned_game, dict):
            raise RuntimeError(f"{actor} game read returned no game")
        if int(returned_game.get("id")) != game_id:
            raise RuntimeError(f"{actor} game read returned the wrong game")
        viewer_checks.append({
            "actor": actor,
            "elapsed_ms": elapsed_ms,
            "status": game_response.status_code,
        })

    return {
        "base_url": base_url,
        "challenge_id": challenge_id,
        "concurrent_accepts": [
            {
                "actor": record.actor,
                "elapsed_ms": record.elapsed_ms,
                "game_id": int(record.payload["game"]["id"]),
                "message": record.payload.get("message"),
                "status": record.status,
            }
            for record in records
        ],
        "game_id": game_id,
        "ok": True,
        "repeat_accept": {
            "elapsed_ms": repeated_ms,
            "game_id": int(repeated_payload["game"]["id"]),
            "message": repeated_payload.get("message"),
            "status": repeated_response.status_code,
        },
        "synthetic_users_retained": [username1, username2],
        "viewer_checks": viewer_checks,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default="https://nepalkingz.eu.pythonanywhere.com",
    )
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument(
        "--bootstrap-staging-gold",
        action="store_true",
        help=(
            "top up only the freshly generated synthetic accounts through "
            "the private staging PostgreSQL connection"
        ),
    )
    parser.add_argument(
        "--ssh-identity",
        type=Path,
        default=Path("~/.ssh/nepalkings_pythonanywhere_eu"),
    )
    parser.add_argument(
        "--known-hosts",
        type=Path,
        default=Path("/tmp/nepalkings_pa_eu_known_hosts"),
    )
    parser.add_argument("--allow-production", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    base_url = args.base_url.rstrip("/")
    if (
        "api-nepalkingz.eu.pythonanywhere.com" in base_url
        and not args.allow_production
    ):
        print(
            "ERROR: refusing the production hostname without "
            "--allow-production",
        )
        return 2
    try:
        result = run_smoke(
            base_url,
            args.timeout_seconds,
            bootstrap_staging_gold=args.bootstrap_staging_gold,
            ssh_identity=args.ssh_identity,
            known_hosts=args.known_hosts,
        )
    except Exception as exc:
        print(json.dumps({"error": str(exc), "ok": False}, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
