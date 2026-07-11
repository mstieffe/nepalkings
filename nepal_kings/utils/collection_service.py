# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Client-side service functions for the collection API."""

from utils import http_compat as requests
from config import settings
import logging

logger = logging.getLogger('nk.utils.collection_service')


def fetch_collection_cards():
    """GET /collection/cards — returns {cards, booster_packs, booster_packs_side, gold}."""
    response = requests.get(f'{settings.SERVER_URL}/collection/cards', timeout=10)
    response.raise_for_status()
    return response.json()


def sell_card(suit, rank, quantity):
    """POST /collection/sell_card — returns {gold_earned, gold}."""
    response = requests.post(
        f'{settings.SERVER_URL}/collection/sell_card',
        json={'suit': suit, 'rank': rank, 'quantity': quantity},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def buy_booster(quantity=1):
    """POST /collection/buy_booster — returns {booster_packs, gold}."""
    response = requests.post(
        f'{settings.SERVER_URL}/collection/buy_booster',
        json={'quantity': quantity},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def buy_booster_side(quantity=1):
    """POST /collection/buy_booster_side — returns {booster_packs_side, gold}."""
    response = requests.post(
        f'{settings.SERVER_URL}/collection/buy_booster_side',
        json={'quantity': quantity},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def open_booster(quantity=1):
    """POST /collection/open_booster — returns {cards, booster_packs}."""
    response = requests.post(
        f'{settings.SERVER_URL}/collection/open_booster',
        json={'quantity': quantity},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def open_booster_side(quantity=1):
    """POST /collection/open_booster_side — returns {cards, booster_packs_side}."""
    response = requests.post(
        f'{settings.SERVER_URL}/collection/open_booster_side',
        json={'quantity': quantity},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def convert_card(suit, rank, target_suit, quantity):
    """POST /collection/convert_card — returns {consumed, produced, ratio, gold}."""
    response = requests.post(
        f'{settings.SERVER_URL}/collection/convert_card',
        json={'suit': suit, 'rank': rank,
              'target_suit': target_suit, 'quantity': quantity},
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def craft_maharaja(suit):
    """POST /collection/craft_maharaja — trade one free copy of every rank of
    *suit* for a Maharaja card of that suit.

    Returns the parsed body for the caller to inspect:
      success → {'success': True, 'card': {...}, 'consumed': 13}
      failure → {'success': False, 'message': '...'}
    The body carries the failure reason on 4xx too, so (unlike convert_card) we
    return the JSON instead of raising, letting the screen surface the message.
    """
    response = requests.post(
        f'{settings.SERVER_URL}/collection/craft_maharaja',
        json={'suit': suit},
        timeout=10,
    )
    return response.json()
