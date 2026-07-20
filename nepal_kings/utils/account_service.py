# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Account lifecycle and lightweight safety API helpers."""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from config import settings
from utils import http_compat as requests


def _payload(response, fallback):
    try:
        data = response.json()
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    if response.status_code >= 400:
        return {
            'success': False,
            'message': data.get('message') or fallback,
            'reason': data.get('reason'),
            'request_id': data.get('request_id'),
        }
    return data


def change_password(current_password, new_password):
    try:
        response = requests.post(
            f'{settings.SERVER_URL}/auth/account/change_password',
            data={
                'current_password': current_password,
                'new_password': new_password,
            },
            timeout=10,
        )
        return _payload(response, 'Could not change password.')
    except Exception:
        return {
            'success': False,
            'message': 'Could not reach the server. Please try again.',
        }


def logout_all():
    try:
        response = requests.post(
            f'{settings.SERVER_URL}/auth/account/logout_all',
            timeout=10,
        )
        return _payload(response, 'Could not log out all devices.')
    except Exception:
        return {
            'success': False,
            'message': 'Could not reach the server. Please try again.',
        }


def export_account():
    try:
        response = requests.get(
            f'{settings.SERVER_URL}/auth/account/export',
            timeout=20,
        )
        return _payload(response, 'Could not export account data.')
    except Exception:
        return {
            'success': False,
            'message': 'Could not reach the server. Please try again.',
        }


def delete_account(current_password):
    try:
        response = requests.post(
            f'{settings.SERVER_URL}/auth/account/delete',
            data={
                'current_password': current_password,
                'confirmation': 'DELETE',
            },
            timeout=20,
        )
        return _payload(response, 'Could not delete account.')
    except Exception:
        return {
            'success': False,
            'message': 'Could not reach the server. Please try again.',
        }


def report_player(username, reason, details=''):
    try:
        response = requests.post(
            f'{settings.SERVER_URL}/safety/reports',
            json={
                'username': username,
                'reason': reason,
                'details': details,
                'context_type': 'user',
            },
            timeout=10,
        )
        return _payload(response, 'Could not submit report.')
    except Exception:
        return {
            'success': False,
            'message': 'Could not reach the server. Please try again.',
        }


def set_player_block(username, blocked):
    suffix = '' if blocked else '/remove'
    try:
        response = requests.post(
            f'{settings.SERVER_URL}/safety/blocks{suffix}',
            json={'username': username},
            timeout=10,
        )
        return _payload(
            response,
            'Could not update the player block.',
        )
    except Exception:
        return {
            'success': False,
            'message': 'Could not reach the server. Please try again.',
        }


def save_export(payload):
    """Download in the browser or securely save in the desktop user folder."""
    username = str(
        ((payload or {}).get('account') or {}).get('username')
        or 'player'
    )
    safe_username = ''.join(
        ch for ch in username if ch.isalnum() or ch in '-_')[:40] or 'player'
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    filename = f'nepal-kings-account-{safe_username}-{stamp}.json'

    if sys.platform == 'emscripten':
        if requests.download_json(filename, payload):
            return filename
        raise RuntimeError('Browser download could not be started')

    export_dir = Path.home() / '.nepalkings' / 'exports'
    export_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(export_dir, 0o700)
    except OSError:
        pass
    path = export_dir / filename
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        0o600,
    )
    with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write('\n')
    return str(path)
