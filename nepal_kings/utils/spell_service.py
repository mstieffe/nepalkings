"""
Client-side spell service for server communication.
Handles all spell-related API calls to the server.
"""

import requests
from config import settings
from typing import Dict, List, Optional, Any


def cast_spell(
    player_id: int,
    game_id: int,
    spell_name: str,
    spell_type: str,
    spell_family_name: str,
    suit: str,
    cards: List[Dict],
    target_figure_id: Optional[int] = None,
    counterable: bool = False,
    possible_during_ceasefire: bool = True
) -> Dict[str, Any]:
    """
    Cast a spell (both counterable and non-counterable).
    
    :param player_id: ID of the player casting the spell
    :param game_id: ID of the game
    :param spell_name: Name of the spell being cast
    :param spell_type: Type of spell ('greed', 'enchantment', or 'tactics')
    :param spell_family_name: Name of the spell family
    :param suit: Suit of the spell
    :param cards: List of card dictionaries used to cast the spell
    :param target_figure_id: ID of target figure (if spell requires target)
    :param counterable: Whether this spell can be countered
    :param possible_during_ceasefire: Whether this spell can be cast during ceasefire
    :return: Response dictionary with success status and updated game state
    """
    data = {
        'player_id': player_id,
        'game_id': game_id,
        'spell_name': spell_name,
        'spell_type': spell_type,
        'spell_family_name': spell_family_name,
        'suit': suit,
        'cards': cards,
        'target_figure_id': target_figure_id,
        'counterable': counterable,
        'possible_during_ceasefire': possible_during_ceasefire
    }
    
    try:
        response = requests.post(
            f'{settings.SERVER_URL}/spells/cast_spell',
            json=data,
            timeout=10
        )
        
        if response.status_code != 200:
            error_msg = response.json().get('message', 'Unknown error')
            return {
                'success': False,
                'message': f'Failed to cast spell: {error_msg}',
                'game': None
            }
        
        return response.json()
        
    except requests.RequestException as e:
        return {
            'success': False,
            'message': f'Network error: {str(e)}',
            'game': None
        }


def counter_spell(
    player_id: int,
    game_id: int,
    pending_spell_id: int,
    counter_spell_name: str,
    counter_spell_type: str,
    counter_spell_family_name: str,
    counter_cards: List[Dict]
) -> Dict[str, Any]:
    """
    Counter an opponent's pending spell with your own spell.
    
    :param player_id: ID of the player countering
    :param game_id: ID of the game
    :param pending_spell_id: ID of the spell to counter
    :param counter_spell_name: Name of the counter spell
    :param counter_spell_type: Type of counter spell
    :param counter_spell_family_name: Family of counter spell
    :param counter_cards: Cards used for counter spell
    :return: Response dictionary
    """
    data = {
        'player_id': player_id,
        'game_id': game_id,
        'pending_spell_id': pending_spell_id,
        'counter_spell_name': counter_spell_name,
        'counter_spell_type': counter_spell_type,
        'counter_spell_family_name': counter_spell_family_name,
        'counter_cards': counter_cards
    }
    
    try:
        response = requests.post(
            f'{settings.SERVER_URL}/spells/counter_spell',
            json=data,
            timeout=10
        )
        
        if response.status_code != 200:
            error_msg = response.json().get('message', 'Unknown error')
            return {
                'success': False,
                'message': f'Failed to counter spell: {error_msg}'
            }
        
        return response.json()
        
    except requests.RequestException as e:
        return {
            'success': False,
            'message': f'Network error: {str(e)}'
        }


def allow_spell(player_id: int, game_id: int, pending_spell_id: int) -> Dict[str, Any]:
    """
    Allow an opponent's spell to execute without countering.
    
    :param player_id: ID of the player allowing the spell
    :param game_id: ID of the game
    :param pending_spell_id: ID of the pending spell to allow
    :return: Response dictionary
    """
    data = {
        'player_id': player_id,
        'game_id': game_id,
        'pending_spell_id': pending_spell_id
    }
    
    try:
        response = requests.post(
            f'{settings.SERVER_URL}/spells/allow_spell',
            json=data,
            timeout=10
        )
        
        if response.status_code != 200:
            error_msg = response.json().get('message', 'Unknown error')
            return {
                'success': False,
                'message': f'Failed to allow spell: {error_msg}'
            }
        
        return response.json()
        
    except requests.RequestException as e:
        return {
            'success': False,
            'message': f'Network error: {str(e)}'
        }


def fetch_active_spells(game_id: int, player_id: Optional[int] = None) -> List[Dict]:
    """
    Fetch all active spell effects for a game.
    
    :param game_id: ID of the game
    :param player_id: Optional player ID to filter by
    :return: List of active spell dictionaries
    """
    params = {'game_id': game_id}
    if player_id is not None:
        params['player_id'] = player_id
    
    try:
        response = requests.get(
            f'{settings.SERVER_URL}/spells/get_active_spells',
            params=params,
            timeout=10
        )
        
        if response.status_code != 200:
            print(f"Failed to fetch active spells: {response.json().get('message', 'Unknown error')}")
            return []
        
        return response.json().get('active_spells', [])
        
    except requests.RequestException as e:
        print(f"Network error fetching active spells: {str(e)}")
        return []


def fetch_pending_spell(spell_id: int) -> Optional[Dict]:
    """
    Fetch details of a pending (counterable) spell.
    
    :param spell_id: ID of the pending spell
    :return: Spell dictionary or None
    """
    try:
        response = requests.get(
            f'{settings.SERVER_URL}/spells/get_pending_spell',
            params={'spell_id': spell_id},
            timeout=10
        )
        
        if response.status_code != 200:
            print(f"Failed to fetch pending spell: {response.json().get('message', 'Unknown error')}")
            return None
        
        return response.json().get('spell')
        
    except requests.RequestException as e:
        print(f"Network error fetching pending spell: {str(e)}")
        return None


def remove_spell_effect(spell_id: int) -> Dict[str, Any]:
    """
    Remove/deactivate a spell effect.
    Used when spell duration expires or affected figure is destroyed.
    
    :param spell_id: ID of the spell effect to remove
    :return: Response dictionary
    """
    data = {'spell_id': spell_id}
    
    try:
        response = requests.post(
            f'{settings.SERVER_URL}/spells/remove_spell_effect',
            json=data,
            timeout=10
        )
        
        if response.status_code != 200:
            error_msg = response.json().get('message', 'Unknown error')
            return {
                'success': False,
                'message': f'Failed to remove spell effect: {error_msg}'
            }
        
        return response.json()
        
    except requests.RequestException as e:
        return {
            'success': False,
            'message': f'Network error: {str(e)}'
        }
