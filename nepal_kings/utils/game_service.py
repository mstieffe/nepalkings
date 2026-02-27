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


def advance_figure(game_id, player_id, figure_id):
    """Advance a figure toward battle."""
    try:
        response = requests.post(
            f'{settings.SERVER_URL}/games/advance_figure',
            json={'game_id': game_id, 'player_id': player_id, 'figure_id': figure_id}
        )
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to advance figure: {str(e)}"}


def select_defender(game_id, player_id, figure_id):
    """Select a defending figure against the opponent's advancing figure."""
    try:
        response = requests.post(
            f'{settings.SERVER_URL}/games/select_defender',
            json={'game_id': game_id, 'player_id': player_id, 'figure_id': figure_id}
        )
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to select defender: {str(e)}"}


def skip_civil_war_second(game_id, player_id, context='advance'):
    """Skip selecting a second Civil War figure."""
    try:
        response = requests.post(
            f'{settings.SERVER_URL}/games/skip_civil_war_second',
            json={'game_id': game_id, 'player_id': player_id, 'context': context}
        )
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to skip: {str(e)}"}


def battle_decision(game_id, player_id, decision):
    """Submit a battle decision (fight or fold)."""
    try:
        response = requests.post(
            f'{settings.SERVER_URL}/games/battle_decision',
            json={'game_id': game_id, 'player_id': player_id, 'decision': decision}
        )
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to submit battle decision: {str(e)}"}


def cannot_advance_loss(game_id, player_id):
    """Report that the player cannot advance any figure and auto-loses the battle."""
    try:
        response = requests.post(
            f'{settings.SERVER_URL}/games/cannot_advance_loss',
            json={'game_id': game_id, 'player_id': player_id}
        )
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to process auto-loss: {str(e)}"}


def defender_no_figures_loss(game_id, player_id):
    """Report that the defender has no valid figures for battle — defender auto-loses."""
    try:
        response = requests.post(
            f'{settings.SERVER_URL}/games/defender_no_figures_loss',
            json={'game_id': game_id, 'player_id': player_id}
        )
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to process defender auto-loss: {str(e)}"}