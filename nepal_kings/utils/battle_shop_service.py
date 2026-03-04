"""Client-side API service for battle shop operations."""

import requests
from config import settings


def buy_battle_move(game_id, player_id, family_name, card_id, card_type, suit, rank, value):
    """Buy a battle move by reserving a card.

    :return: Server response dict with 'success', 'battle_move', 'game'.
    """
    data = {
        'game_id': game_id,
        'player_id': player_id,
        'family_name': family_name,
        'card_id': card_id,
        'card_type': card_type,
        'suit': suit,
        'rank': rank,
        'value': value,
    }
    response = requests.post(f'{settings.SERVER_URL}/battle_shop/buy_battle_move', json=data)
    if response.status_code != 200:
        return {'success': False, 'message': response.json().get('message', 'Unknown error')}
    return response.json()


def return_battle_move(game_id, player_id, battle_move_id):
    """Return (cancel) a previously bought battle move.

    :return: Server response dict with 'success', 'message', 'game'.
    """
    data = {
        'game_id': game_id,
        'player_id': player_id,
        'battle_move_id': battle_move_id,
    }
    response = requests.post(f'{settings.SERVER_URL}/battle_shop/return_battle_move', json=data)
    if response.status_code != 200:
        return {'success': False, 'message': response.json().get('message', 'Unknown error')}
    return response.json()


def get_battle_moves(game_id, player_id):
    """Get all bought battle moves for a player.

    :return: Server response dict with 'success', 'battle_moves'.
    """
    response = requests.get(
        f'{settings.SERVER_URL}/battle_shop/get_battle_moves',
        params={'game_id': game_id, 'player_id': player_id}
    )
    if response.status_code != 200:
        return {'success': False, 'battle_moves': []}
    return response.json()


def confirm_battle_moves(game_id, player_id):
    """Confirm that the player's battle moves are locked in.

    :return: Server response dict with 'success', 'both_ready', 'game'.
    """
    data = {
        'game_id': game_id,
        'player_id': player_id,
    }
    response = requests.post(f'{settings.SERVER_URL}/battle_shop/confirm_battle_moves', json=data)
    if response.status_code != 200:
        return {'success': False, 'message': response.json().get('message', 'Unknown error')}
    return response.json()


def gamble_battle_move(game_id, player_id, battle_move_id):
    """Gamble: sacrifice a battle move and draw two random replacements.

    :return: Server response dict with 'success', 'sacrificed', 'new_moves', 'game'.
    """
    data = {
        'game_id': game_id,
        'player_id': player_id,
        'battle_move_id': battle_move_id,
    }
    response = requests.post(f'{settings.SERVER_URL}/battle_shop/gamble_battle_move', json=data)
    if response.status_code != 200:
        return {'success': False, 'message': response.json().get('message', 'Unknown error')}
    return response.json()


def combine_battle_moves(game_id, player_id, move_id_a, move_id_b):
    """Combine two same-colour daggers into a Double Dagger.

    :return: Server response dict with 'success', 'combined_move', 'game'.
    """
    data = {
        'game_id': game_id,
        'player_id': player_id,
        'move_id_a': move_id_a,
        'move_id_b': move_id_b,
    }
    response = requests.post(f'{settings.SERVER_URL}/battle_shop/combine_battle_moves', json=data)
    if response.status_code != 200:
        return {'success': False, 'message': response.json().get('message', 'Unknown error')}
    return response.json()


def dismantle_battle_move(game_id, player_id, battle_move_id):
    """Dismantle a Double Dagger back into two separate Daggers.

    :return: Server response dict with 'success', 'restored_moves', 'game'.
    """
    data = {
        'game_id': game_id,
        'player_id': player_id,
        'battle_move_id': battle_move_id,
    }
    response = requests.post(f'{settings.SERVER_URL}/battle_shop/dismantle_battle_move', json=data)
    if response.status_code != 200:
        return {'success': False, 'message': response.json().get('message', 'Unknown error')}
    return response.json()
