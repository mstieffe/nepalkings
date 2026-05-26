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


def skip_onboarding():
    response = requests.post(f'{settings.SERVER_URL}/onboarding/skip', timeout=6)
    response.raise_for_status()
    return response.json()


def reset_onboarding():
    response = requests.post(f'{settings.SERVER_URL}/onboarding/reset', timeout=6)
    response.raise_for_status()
    return response.json()
