# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Client helpers for onboarding guide endpoints."""

from config import settings
from utils import http_compat as requests


def fetch_onboarding():
    response = requests.get(f'{settings.SERVER_URL}/onboarding/state', timeout=8)
    response.raise_for_status()
    return response.json()


def claim_reward(reward_id):
    response = requests.post(
        f'{settings.SERVER_URL}/onboarding/claim_reward',
        json={'reward_id': reward_id},
        timeout=8,
    )
    response.raise_for_status()
    return response.json()


def mark_tip(tip_key):
    response = requests.post(
        f'{settings.SERVER_URL}/onboarding/mark_tip',
        json={'tip_key': tip_key},
        timeout=6,
    )
    response.raise_for_status()
    return response.json()


def prepare_starter_reveal():
    """Choose the roulette result without granting the starter cards."""
    response = requests.post(
        f'{settings.SERVER_URL}/onboarding/starter_reveal/prepare',
        timeout=6,
    )
    response.raise_for_status()
    return response.json()


def complete_starter_reveal():
    """Grant starter cards after the roulette has visibly settled."""
    response = requests.post(
        f'{settings.SERVER_URL}/onboarding/starter_reveal/complete',
        timeout=6,
    )
    response.raise_for_status()
    return response.json()


def mark_tips(tip_keys, *, event=None):
    payload = {'tip_keys': list(tip_keys or [])}
    if event:
        payload['event'] = event
    response = requests.post(
        f'{settings.SERVER_URL}/onboarding/mark_tip',
        json=payload,
        timeout=6,
    )
    response.raise_for_status()
    return response.json()


def complete_step(step_id):
    response = requests.post(
        f'{settings.SERVER_URL}/onboarding/complete_step',
        json={'step_id': step_id},
        timeout=6,
    )
    response.raise_for_status()
    return response.json()


def skip_onboarding():
    response = requests.post(f'{settings.SERVER_URL}/onboarding/skip', timeout=6)
    response.raise_for_status()
    return response.json()


def resume_onboarding():
    response = requests.post(f'{settings.SERVER_URL}/onboarding/resume', timeout=6)
    response.raise_for_status()
    return response.json()


def reset_onboarding():
    response = requests.post(f'{settings.SERVER_URL}/onboarding/reset', timeout=6)
    response.raise_for_status()
    return response.json()
