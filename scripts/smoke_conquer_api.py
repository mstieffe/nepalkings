#!/usr/bin/env python3
"""Run a deliberate, authenticated Conquer mutation smoke test.

This command creates a disposable human account, completes the starter-card
onboarding flow, opens the recommended Conquer configuration, starts its first
battle, and verifies game/message reads.  It intentionally leaves data behind
so operators can either inspect it or prove database recovery by restoring the
pre-smoke backup.

The command refuses to run unless ``--confirm-mutation`` exactly matches the
normalized base URL.  It never prints the generated password or bearer token.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import secrets
import threading
import time
from typing import Any

import requests


def _safe_payload(payload: Any) -> Any:
    """Remove credentials before including a response in an exception."""
    if isinstance(payload, dict):
        return {
            key: (
                '<redacted>'
                if key.lower() in {'password', 'secret', 'token'}
                else _safe_payload(value)
            )
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        if len(payload) > 20:
            return f'<{len(payload)} items>'
        return [_safe_payload(value) for value in payload]
    return payload


def _request_json(
    session: requests.Session,
    method: str,
    url: str,
    *,
    token: str | None = None,
    timeout: float,
    **kwargs: Any,
) -> tuple[dict[str, Any], float]:
    headers = dict(kwargs.pop('headers', {}))
    if token:
        headers['Authorization'] = f'Bearer {token}'

    started = time.perf_counter()
    response = session.request(
        method,
        url,
        headers=headers,
        timeout=timeout,
        **kwargs,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f'{method} {url} returned HTTP {response.status_code} '
            'with a non-JSON body'
        ) from exc
    # Older read endpoints such as /kingdom/map return their data directly
    # without a redundant success=true field.  An explicit success=false is a
    # failure, while an absent success key is valid when HTTP itself succeeded.
    if not response.ok or payload.get('success') is False:
        raise RuntimeError(
            f'{method} {url} returned HTTP {response.status_code}: '
            f'{_safe_payload(payload)}'
        )
    return payload, elapsed_ms


def _request_json_result(
    method: str,
    url: str,
    *,
    token: str,
    timeout: float,
    json_payload: dict[str, Any],
    start: threading.Barrier,
) -> dict[str, Any]:
    """Issue one synchronized request without treating an expected 4xx as fatal."""
    session = requests.Session()
    start.wait(timeout=timeout)
    started = time.perf_counter()
    response = session.request(
        method,
        url,
        headers={'Authorization': f'Bearer {token}'},
        timeout=timeout,
        json=json_payload,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000
    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f'{method} {url} returned HTTP {response.status_code} '
            'with a non-JSON body'
        ) from exc
    safe_payload = _safe_payload(payload)
    if isinstance(safe_payload, dict):
        # Action responses can contain a complete multi-megabyte game
        # snapshot. Keep operational output concise and avoid persisting
        # unrelated gameplay state in CI/log artifacts.
        safe_payload = {
            key: safe_payload[key]
            for key in (
                'success',
                'message',
                'reason',
                'figure_name',
                'is_counter_advance',
            )
            if key in safe_payload
        }
    return {
        'status_code': response.status_code,
        'elapsed_ms': round(elapsed_ms, 1),
        'payload': safe_payload,
    }


def _assert_advance_race(results: list[dict[str, Any]]) -> None:
    """Require one committed advance and one rejection from the stale request."""
    statuses = sorted(int(result['status_code']) for result in results)
    successes = sum(
        result.get('payload', {}).get('success') is True
        for result in results
    )
    if statuses != [200, 400] or successes != 1:
        raise RuntimeError(
            'Concurrent advances did not serialize to one success and one '
            f'rejection: {_safe_payload(results)}'
        )


def _assert_advance_withdraw_race(results: list[dict[str, Any]]) -> None:
    """Require withdrawal to win canonically against a concurrent advance."""
    by_action = {
        str(result.get('action')): result
        for result in results
    }
    advance = by_action.get('advance')
    withdraw = by_action.get('withdraw')
    if advance is None or withdraw is None:
        raise RuntimeError(
            f'Cross-action race is missing a result: {_safe_payload(results)}'
        )
    withdraw_success = (
        int(withdraw['status_code']) == 200
        and withdraw.get('payload', {}).get('success') is True
    )
    advance_status = int(advance['status_code'])
    advance_consistent = (
        (
            advance_status == 200
            and advance.get('payload', {}).get('success') is True
        )
        or (
            advance_status == 409
            and advance.get('payload', {}).get('success') is False
        )
    )
    if not withdraw_success or not advance_consistent:
        raise RuntimeError(
            'Concurrent advance/withdraw did not produce a serialized '
            f'outcome: {_safe_payload(results)}'
        )


def _run_advance_race(
    base_url: str,
    *,
    token: str,
    game_id: int,
    player_id: int,
    figure_ids: list[int],
    timeout: float,
) -> list[dict[str, Any]]:
    if len(figure_ids) < 2:
        raise RuntimeError(
            'Conquer concurrency smoke requires two candidate attacker figures'
        )
    start = threading.Barrier(3)
    url = f'{base_url}/games/advance_figure'

    def _request(figure_id: int) -> dict[str, Any]:
        return _request_json_result(
            'POST',
            url,
            token=token,
            timeout=timeout,
            json_payload={
                'game_id': game_id,
                'player_id': player_id,
                'figure_id': figure_id,
            },
            start=start,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(_request, figure_id)
            for figure_id in figure_ids[:2]
        ]
        start.wait(timeout=timeout)
        results = [future.result(timeout=timeout + 5) for future in futures]
    _assert_advance_race(results)
    return results


def _run_advance_withdraw_race(
    base_url: str,
    *,
    token: str,
    game_id: int,
    player_id: int,
    figure_id: int,
    timeout: float,
) -> list[dict[str, Any]]:
    start = threading.Barrier(3)

    def _request(action: str) -> dict[str, Any]:
        if action == 'advance':
            url = f'{base_url}/games/advance_figure'
            payload = {
                'game_id': game_id,
                'player_id': player_id,
                'figure_id': figure_id,
            }
        else:
            url = f'{base_url}/games/conquer_withdraw'
            payload = {
                'game_id': game_id,
                'player_id': player_id,
                'client_action_id': f'cross-race-{secrets.token_hex(8)}',
            }
        result = _request_json_result(
            'POST',
            url,
            token=token,
            timeout=timeout,
            json_payload=payload,
            start=start,
        )
        result['action'] = action
        return result

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(_request, action)
            for action in ('advance', 'withdraw')
        ]
        start.wait(timeout=timeout)
        results = [future.result(timeout=timeout + 5) for future in futures]
    _assert_advance_withdraw_race(results)
    return results


def run_smoke(
    base_url: str,
    *,
    expected_environment: str,
    timeout: float,
    race_advances: bool = False,
    race_advance_withdraw: bool = False,
) -> dict[str, Any]:
    base_url = base_url.rstrip('/')
    session = requests.Session()
    timings: dict[str, float] = {}

    health, timings['health_ms'] = _request_json(
        session,
        'GET',
        f'{base_url}/healthz',
        timeout=timeout,
    )
    if health.get('environment') != expected_environment:
        raise RuntimeError(
            f'Expected environment {expected_environment!r}, got '
            f'{health.get("environment")!r}'
        )

    suffix = datetime.now(timezone.utc).strftime('%m%d%H%M%S')
    username = f'prodsmoke_{suffix}_{secrets.token_hex(2)}'
    password = secrets.token_urlsafe(24)

    registered, timings['register_ms'] = _request_json(
        session,
        'POST',
        f'{base_url}/auth/register',
        timeout=timeout,
        data={
            'username': username,
            'password': password,
            'age_confirmed': 'true',
            'terms_accepted': 'true',
            'privacy_accepted': 'true',
        },
    )
    token = str(registered['token'])
    user_id = int(registered['user']['id'])

    _, timings['welcome_ms'] = _request_json(
        session,
        'POST',
        f'{base_url}/onboarding/mark_tip',
        token=token,
        timeout=timeout,
        json={'tip_key': 'welcome'},
    )
    _, timings['starter_prepare_ms'] = _request_json(
        session,
        'POST',
        f'{base_url}/onboarding/starter_reveal/prepare',
        token=token,
        timeout=timeout,
    )
    _, timings['collection_hints_ms'] = _request_json(
        session,
        'POST',
        f'{base_url}/onboarding/mark_tip',
        token=token,
        timeout=timeout,
        json={
            'tip_keys': [
                'menu:collection_basics_window',
                'menu:starter_cards_present_window',
            ],
        },
    )
    _, timings['starter_complete_ms'] = _request_json(
        session,
        'POST',
        f'{base_url}/onboarding/starter_reveal/complete',
        token=token,
        timeout=timeout,
    )

    kingdom_map, timings['kingdom_map_ms'] = _request_json(
        session,
        'GET',
        f'{base_url}/kingdom/map',
        token=token,
        timeout=timeout,
    )
    land_id = kingdom_map.get('recommended_tutorial_land_id')
    if land_id is None:
        land = next(
            (
                item
                for item in kingdom_map.get('lands', [])
                if not item.get('is_mine')
            ),
            None,
        )
        land_id = land.get('id') if land else None
    if land_id is None:
        raise RuntimeError('No conquerable land found in /kingdom/map')
    land_id = int(land_id)

    _, timings['conquer_config_ms'] = _request_json(
        session,
        'GET',
        f'{base_url}/kingdom/conquer/config',
        token=token,
        timeout=timeout,
        params={'land_id': land_id},
    )
    started, timings['start_battle_ms'] = _request_json(
        session,
        'POST',
        f'{base_url}/kingdom/conquer/start_battle',
        token=token,
        timeout=timeout,
        json={'land_id': land_id},
    )
    game_id = int(started['game_id'])

    game, timings['game_read_ms'] = _request_json(
        session,
        'GET',
        f'{base_url}/games/get_game',
        token=token,
        timeout=timeout,
        params={'game_id': game_id},
    )
    if int(game['game']['id']) != game_id:
        raise RuntimeError('Game read returned the wrong game ID')

    advance_race = None
    prelude_resolution = None
    if race_advances or race_advance_withdraw:
        game_data = game['game']
        attacker = next(
            (
                player
                for player in game_data.get('players', [])
                if int(player.get('user_id', -1)) == user_id
            ),
            None,
        )
        if attacker is None:
            raise RuntimeError('Could not identify the human Conquer player')
        player_id = int(attacker['id'])

        turn_start, timings['race_start_turn_ms'] = _request_json(
            session,
            'POST',
            f'{base_url}/games/start_turn',
            token=token,
            timeout=timeout,
            json={'game_id': game_id, 'player_id': player_id},
        )
        turn_summary = turn_start.get('opponent_turn_summary') or {}
        pending_prelude = turn_summary.get('pending_prelude_target') or {}
        if pending_prelude:
            valid_target_ids = [
                int(target_id)
                for target_id in pending_prelude.get('valid_target_ids', [])
            ]
            if not valid_target_ids:
                raise RuntimeError(
                    'Pending Conquer prelude did not expose a valid target'
                )
            resolved, timings['race_resolve_prelude_ms'] = _request_json(
                session,
                'POST',
                f'{base_url}/kingdom/conquer/resolve_prelude_target',
                token=token,
                timeout=timeout,
                json={
                    'game_id': game_id,
                    'spell_id': int(pending_prelude['spell_id']),
                    'target_figure_id': valid_target_ids[0],
                },
            )
            game_data = resolved['game']
            prelude_resolution = {
                'spell_name': pending_prelude.get('spell_name'),
                'target_figure_id': valid_target_ids[0],
            }
            attacker = next(
                (
                    player
                    for player in game_data.get('players', [])
                    if int(player.get('user_id', -1)) == user_id
                ),
                None,
            )
            if attacker is None:
                raise RuntimeError(
                    'Prelude resolution lost the human Conquer player'
                )
        figure_ids = [
            int(figure['id'])
            for figure in attacker.get('figures', [])
            if int(figure['id']) not in set(
                game_data.get('resting_figure_ids') or []
            )
        ]
        if race_advances:
            advance_race = _run_advance_race(
                base_url,
                token=token,
                game_id=game_id,
                player_id=player_id,
                figure_ids=figure_ids,
                timeout=timeout,
            )
        else:
            advance_race = _run_advance_withdraw_race(
                base_url,
                token=token,
                game_id=game_id,
                player_id=player_id,
                figure_id=figure_ids[0],
                timeout=timeout,
            )
        game, timings['post_race_game_read_ms'] = _request_json(
            session,
            'GET',
            f'{base_url}/games/get_game',
            token=token,
            timeout=timeout,
            params={'game_id': game_id},
        )

    logs, timings['log_entries_ms'] = _request_json(
        session,
        'GET',
        f'{base_url}/msg/get_log_entries',
        token=token,
        timeout=timeout,
        params={'game_id': game_id},
    )
    if race_advances:
        advancing_logs = [
            entry
            for entry in logs.get('log_entries', [])
            if entry.get('type') == 'advance'
        ]
        if len(advancing_logs) != 1:
            raise RuntimeError(
                'Expected exactly one committed advance log after race, got '
                f'{len(advancing_logs)}'
            )
        advancing_figure_id = game['game'].get('advancing_figure_id')
        if advancing_figure_id not in figure_ids[:2]:
            raise RuntimeError(
                'Post-race game state does not contain the winning advance'
            )
    elif race_advance_withdraw:
        if game['game'].get('state') != 'finished':
            raise RuntimeError(
                'Concurrent advance/withdraw did not finish the Conquer game'
            )
        withdraw_logs = [
            entry
            for entry in logs.get('log_entries', [])
            if entry.get('type') == 'auto_loss'
            and 'withdrew from the conquest' in entry.get('message', '')
        ]
        if len(withdraw_logs) != 1:
            raise RuntimeError(
                'Expected exactly one committed Conquer withdrawal log, got '
                f'{len(withdraw_logs)}'
            )
    chats, timings['chat_messages_ms'] = _request_json(
        session,
        'GET',
        f'{base_url}/msg/get_chat_messages',
        token=token,
        timeout=timeout,
        params={'game_id': game_id},
    )

    return {
        'success': True,
        'environment': health['environment'],
        'release_sha': health.get('release_sha'),
        'username': username,
        'user_id': user_id,
        'land_id': land_id,
        'game_id': game_id,
        'log_entry_count': len(logs.get('log_entries', [])),
        'chat_message_count': len(chats.get('chat_messages', [])),
        'prelude_resolution': prelude_resolution,
        'advance_race': advance_race,
        'timings_ms': {
            key: round(value, 1)
            for key, value in timings.items()
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--expected-environment', required=True)
    parser.add_argument(
        '--confirm-mutation',
        required=True,
        help='Must exactly match --base-url after trailing-slash removal.',
    )
    parser.add_argument('--timeout', type=float, default=30.0)
    parser.add_argument(
        '--race-advances',
        action='store_true',
        help=(
            'Race two legal initial advances and require exactly one to commit.'
        ),
    )
    parser.add_argument(
        '--race-advance-withdraw',
        action='store_true',
        help=(
            'Race an initial advance against withdrawal and require one '
            'canonical finished result.'
        ),
    )
    args = parser.parse_args()

    base_url = args.base_url.rstrip('/')
    if args.confirm_mutation.rstrip('/') != base_url:
        parser.error(
            '--confirm-mutation must exactly match the normalized --base-url'
        )
    if args.race_advances and args.race_advance_withdraw:
        parser.error(
            '--race-advances and --race-advance-withdraw are mutually exclusive'
        )

    result = run_smoke(
        base_url,
        expected_environment=args.expected_environment,
        timeout=max(1.0, args.timeout),
        race_advances=args.race_advances,
        race_advance_withdraw=args.race_advance_withdraw,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
