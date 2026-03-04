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


def finish_battle(game_id, player_id, total_diff):
    """Submit the final battle result to the server for resolution."""
    try:
        response = requests.post(
            f'{settings.SERVER_URL}/games/finish_battle',
            json={'game_id': game_id, 'player_id': player_id, 'total_diff': total_diff}
        )
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to finish battle: {str(e)}"}


def play_battle_move(game_id, player_id, battle_move_id, call_figure_id=None):
    """Play a battle move in the current battle round."""
    try:
        payload = {
            'game_id': game_id,
            'player_id': player_id,
            'battle_move_id': battle_move_id,
        }
        if call_figure_id is not None:
            payload['call_figure_id'] = call_figure_id
        response = requests.post(
            f'{settings.SERVER_URL}/games/play_battle_move',
            json=payload,
        )
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to play battle move: {str(e)}"}


def get_battle_state(game_id, player_id):
    """Poll the current 3-round battle state from the server."""
    try:
        response = requests.get(
            f'{settings.SERVER_URL}/games/get_battle_state',
            params={'game_id': game_id, 'player_id': player_id},
        )
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to get battle state: {str(e)}"}


def skip_battle_turn(game_id, player_id):
    """Skip a battle turn when the player has no moves left to play."""
    try:
        response = requests.post(
            f'{settings.SERVER_URL}/games/skip_battle_turn',
            json={'game_id': game_id, 'player_id': player_id},
        )
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to skip battle turn: {str(e)}"}


def finish_battle_pick_card(game_id, player_id, picked_card_id=None, picked_card_type='main'):
    """Winner picks one card from the returnable pool after battle."""
    try:
        response = requests.post(
            f'{settings.SERVER_URL}/games/finish_battle_pick_card',
            json={
                'game_id': game_id,
                'player_id': player_id,
                'picked_card_id': picked_card_id,
                'picked_card_type': picked_card_type,
            }
        )
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to pick card: {str(e)}"}


def finish_battle_draw(game_id, player_id, choice, picked_card_id=None, picked_card_type='main'):
    """Handle the defender's choice after a draw."""
    try:
        response = requests.post(
            f'{settings.SERVER_URL}/games/finish_battle_draw',
            json={
                'game_id': game_id,
                'player_id': player_id,
                'choice': choice,
                'picked_card_id': picked_card_id,
                'picked_card_type': picked_card_type,
            }
        )
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to resolve draw: {str(e)}"}