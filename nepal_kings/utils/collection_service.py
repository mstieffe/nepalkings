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


def open_booster():
    """POST /collection/open_booster — returns {cards, booster_packs}."""
    response = requests.post(
        f'{settings.SERVER_URL}/collection/open_booster',
        timeout=10,
    )
    response.raise_for_status()
    return response.json()


def open_booster_side():
    """POST /collection/open_booster_side — returns {cards, booster_packs_side}."""
    response = requests.post(
        f'{settings.SERVER_URL}/collection/open_booster_side',
        timeout=10,
    )
    response.raise_for_status()
    return response.json()
