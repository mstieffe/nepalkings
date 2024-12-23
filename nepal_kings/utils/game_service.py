# game_service.py
import requests
from config import settings
from game.core.game import Game

def fetch_user_games(username):
    """Fetch the list of games for the user from the server."""
    response = requests.get(f'{settings.SERVER_URL}/games/get_games', params={'username': username})
    if response.status_code != 200:
        raise Exception(f"Failed to get games: {response.json().get('message', 'Unknown error')}")
    
    game_dicts = response.json().get('games', [])
    games = [Game(game_dict, {'username': username}) for game_dict in game_dicts]
    return games

def fetch_users(username):
    """Fetch all users except the current one."""
    response = requests.get(f'{settings.SERVER_URL}/auth/get_users', params={'username': username})
    response.raise_for_status()  # Raise an error for HTTP errors
    return response.json()['users']

def fetch_user(username):
    """Fetch the current user by username."""
    response = requests.get(f'{settings.SERVER_URL}/auth/get_user', params={'username': username})
    response.raise_for_status()
    return response.json()['user']

def fetch_user_games(username):
    """Fetch the games associated with a user."""
    response = requests.get(f'{settings.SERVER_URL}/games/get_games', params={'username': username})
    response.raise_for_status()
    game_dicts = response.json().get('games', [])
    return game_dicts


def create_game(challenge_id):
    try:
        response = requests.post(f'{settings.SERVER_URL}/games/create_game', data={'challenge_id': challenge_id})
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to create game: {str(e)}"}

def create_challenge(challenger_username, opponent_username):
    try:
        response = requests.post(f'{settings.SERVER_URL}/challenges/create_challenge',
                                 data={'challenger': challenger_username, 'opponent': opponent_username})
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to create challenge: {str(e)}"}

def remove_challenge(challenge_id):
    try:
        response = requests.post(f'{settings.SERVER_URL}/challenges/remove_challenge', data={'challenge_id': challenge_id})
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to remove challenge: {str(e)}"}