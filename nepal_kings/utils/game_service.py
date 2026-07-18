# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
# game_service.py
from utils import http_compat as requests
from config import settings
from game.core.game import Game

import uuid


def _new_client_action_id():
    """Return a fresh UUID string used for server-side idempotency keys.

    Each user-initiated mutating conquer tactic action gets a unique id so
    a network retry replays the cached response instead of failing with
    "not your turn" or mutating state twice.
    """
    return uuid.uuid4().hex

def fetch_user_games(username):
    """Fetch the list of games for the user from the server."""
    response = requests.get(f'{settings.SERVER_URL}/games/get_games', params={'username': username}, timeout=10)
    if response.status_code != 200:
        raise Exception(f"Failed to get games: {response.json().get('message', 'Unknown error')}")
    
    game_dicts = response.json().get('games', [])
    games = [Game(game_dict, {'username': username}) for game_dict in game_dicts]
    return games

def fetch_users(username):
    """Fetch all users except the current one."""
    response = requests.get(f'{settings.SERVER_URL}/auth/get_users', params={'username': username}, timeout=10)
    response.raise_for_status()  # Raise an error for HTTP errors
    return response.json()['users']

def fetch_user(username):
    """Fetch the current user by username."""
    response = requests.get(f'{settings.SERVER_URL}/auth/get_user', params={'username': username}, timeout=10)
    response.raise_for_status()
    return response.json()['user']

def fetch_user_games(username):
    """Fetch the games associated with a user."""
    response = requests.get(f'{settings.SERVER_URL}/games/get_games', params={'username': username}, timeout=10)
    response.raise_for_status()
    game_dicts = response.json().get('games', [])
    return game_dicts


def fetch_game(game_id):
    """Fetch a single game by ID."""
    response = requests.get(f'{settings.SERVER_URL}/games/get_game', params={'game_id': game_id}, timeout=10)
    response.raise_for_status()
    return response.json().get('game')


def _response_message(response, fallback):
    try:
        payload = response.json()
    except Exception:
        return fallback
    return payload.get('message') or payload.get('error') or fallback


def create_game(challenge_id):
    try:
        response = requests.post(f'{settings.SERVER_URL}/games/create_game', data={'challenge_id': challenge_id}, timeout=10)
        if response.status_code >= 400:
            return {
                'success': False,
                'message': _response_message(response, 'Failed to create game'),
            }
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to create game: {str(e)}"}

def create_challenge(challenger_username, opponent_username, stake=45, game_limit=None, turn_time_limit=None):
    try:
        data = {
            'challenger': challenger_username,
            'opponent': opponent_username,
            'stake': stake,
        }
        if game_limit is not None:
            data['game_limit'] = game_limit
        if turn_time_limit is not None:
            data['turn_time_limit'] = turn_time_limit
        response = requests.post(f'{settings.SERVER_URL}/challenges/create_challenge', data=data, timeout=10)
        if response.status_code >= 400:
            return {
                'success': False,
                'message': _response_message(
                    response, 'Failed to create challenge'),
            }
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to create challenge: {str(e)}"}

def remove_challenge(challenge_id):
    try:
        response = requests.post(f'{settings.SERVER_URL}/challenges/remove_challenge', data={'challenge_id': challenge_id}, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to remove challenge: {str(e)}"}


def advance_figure(game_id, player_id, figure_id):
    """Advance a figure toward battle."""
    try:
        response = requests.post(
            f'{settings.SERVER_URL}/games/advance_figure',
            json={'game_id': game_id, 'player_id': player_id, 'figure_id': figure_id},
            timeout=10
        )
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to advance figure: {str(e)}"}


def select_defender(game_id, player_id, figure_id):
    """Select a defending figure against the opponent's advancing figure."""
    try:
        response = requests.post(
            f'{settings.SERVER_URL}/games/select_defender',
            json={'game_id': game_id, 'player_id': player_id, 'figure_id': figure_id},
            timeout=10
        )
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to select defender: {str(e)}"}


def select_conquer_own_defender(game_id, player_id, figure_id):
    """Select own figure as defender after a conquer Invader Swap advance."""
    try:
        response = requests.post(
            f'{settings.SERVER_URL}/games/conquer_select_own_defender',
            json={'game_id': game_id, 'player_id': player_id, 'figure_id': figure_id},
            timeout=10
        )
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to select own defender: {str(e)}"}


def resolve_conquer_prelude_target(game_id, spell_id, target_figure_id):
    """Resolve pending conquer prelude target selection for the invader."""
    try:
        response = requests.post(
            f'{settings.SERVER_URL}/kingdom/conquer/resolve_prelude_target',
            json={
                'game_id': game_id,
                'spell_id': spell_id,
                'target_figure_id': target_figure_id,
            },
            timeout=10
        )
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to resolve prelude target: {str(e)}"}


def skip_civil_war_second(game_id, player_id, context='advance'):
    """Skip selecting a second Civil War figure."""
    try:
        response = requests.post(
            f'{settings.SERVER_URL}/games/skip_civil_war_second',
            json={'game_id': game_id, 'player_id': player_id, 'context': context},
            timeout=10
        )
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to skip: {str(e)}"}


def battle_decision(game_id, player_id, decision):
    """Submit a battle decision (fight or fold)."""
    try:
        response = requests.post(
            f'{settings.SERVER_URL}/games/battle_decision',
            json={'game_id': game_id, 'player_id': player_id, 'decision': decision},
            timeout=10
        )
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to submit battle decision: {str(e)}"}


def cannot_advance_loss(game_id, player_id):
    """Report that the player cannot advance any figure and auto-loses the battle."""
    try:
        response = requests.post(
            f'{settings.SERVER_URL}/games/cannot_advance_loss',
            json={'game_id': game_id, 'player_id': player_id},
            timeout=10
        )
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to process auto-loss: {str(e)}"}


def defender_no_figures_loss(game_id, player_id):
    """Report that the defender has no valid figures for battle — defender auto-loses."""
    try:
        response = requests.post(
            f'{settings.SERVER_URL}/games/defender_no_figures_loss',
            json={'game_id': game_id, 'player_id': player_id},
            timeout=10
        )
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to process defender auto-loss: {str(e)}"}


def conquer_withdraw(game_id, player_id):
    """Withdraw from a conquer battle, making the original defender win."""
    try:
        response = requests.post(
            f'{settings.SERVER_URL}/games/conquer_withdraw',
            json={
                'game_id': game_id,
                'player_id': player_id,
                'client_action_id': _new_client_action_id(),
            },
            timeout=10
        )
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to withdraw: {str(e)}"}


def finish_battle(game_id, player_id, total_diff):
    """Submit the final battle result to the server for resolution."""
    try:
        response = requests.post(
            f'{settings.SERVER_URL}/games/finish_battle',
            json={'game_id': game_id, 'player_id': player_id, 'total_diff': total_diff},
            timeout=10
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
            timeout=10,
        )
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to play battle move: {str(e)}"}


def play_conquer_tactic(game_id, player_id, tactic_id, call_figure_id=None):
    """Play a conquer tactic in the current battle round."""
    try:
        payload = {
            'game_id': game_id,
            'player_id': player_id,
            'tactic_id': tactic_id,
            'client_action_id': _new_client_action_id(),
        }
        if call_figure_id is not None:
            payload['call_figure_id'] = call_figure_id
        response = requests.post(
            f'{settings.SERVER_URL}/games/play_conquer_tactic',
            json=payload,
            timeout=10,
        )
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to play conquer tactic: {str(e)}"}


def gamble_conquer_tactic(game_id, player_id, tactic_id):
    """Gamble a conquer tactic for two replacement tactics."""
    try:
        response = requests.post(
            f'{settings.SERVER_URL}/games/gamble_conquer_tactic',
            json={
                'game_id': game_id,
                'player_id': player_id,
                'tactic_id': tactic_id,
                'client_action_id': _new_client_action_id(),
            },
            timeout=10,
        )
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to gamble conquer tactic: {str(e)}"}


def conquer_gamble_preview(game_id, player_id, tactic_id):
    """Preview a gamble's replacement tactics (requires active All Seeing Eye)."""
    try:
        response = requests.post(
            f'{settings.SERVER_URL}/games/conquer_gamble_preview',
            json={
                'game_id': game_id,
                'player_id': player_id,
                'tactic_id': tactic_id,
            },
            timeout=10,
        )
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to preview gamble: {str(e)}"}


def combine_conquer_tactics(game_id, player_id, tactic_id_a, tactic_id_b):
    """Combine two same-colour Dagger conquer tactics."""
    try:
        response = requests.post(
            f'{settings.SERVER_URL}/games/combine_conquer_tactics',
            json={
                'game_id': game_id,
                'player_id': player_id,
                'tactic_id_a': tactic_id_a,
                'tactic_id_b': tactic_id_b,
                'client_action_id': _new_client_action_id(),
            },
            timeout=10,
        )
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to combine conquer tactics: {str(e)}"}


def dismantle_conquer_tactic(game_id, player_id, tactic_id):
    """Dismantle an unplayed combined conquer tactic."""
    try:
        response = requests.post(
            f'{settings.SERVER_URL}/games/dismantle_conquer_tactic',
            json={
                'game_id': game_id,
                'player_id': player_id,
                'tactic_id': tactic_id,
                'client_action_id': _new_client_action_id(),
            },
            timeout=10,
        )
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to dismantle conquer tactic: {str(e)}"}


def get_battle_state(game_id, player_id):
    """Poll the current 3-round battle state from the server."""
    try:
        response = requests.get(
            f'{settings.SERVER_URL}/games/get_battle_state',
            params={'game_id': game_id, 'player_id': player_id},
            timeout=10,
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
            timeout=10,
        )
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to skip battle turn: {str(e)}"}


def finish_battle_pick_card(game_id, player_id, picked_card_id=None, picked_card_type='main', resting_figure_ids=None):
    """Winner picks one card from the returnable pool after battle."""
    try:
        payload = {
            'game_id': game_id,
            'player_id': player_id,
            'picked_card_id': picked_card_id,
            'picked_card_type': picked_card_type,
        }
        if resting_figure_ids:
            payload['resting_figure_ids'] = resting_figure_ids
        response = requests.post(
            f'{settings.SERVER_URL}/games/finish_battle_pick_card',
            json=payload,
            timeout=10
        )
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to pick card: {str(e)}"}


def finish_battle_draw(game_id, player_id, choice, picked_card_id=None, picked_card_type='main', resting_figure_ids=None):
    """Handle the defender's choice after a draw."""
    try:
        payload = {
            'game_id': game_id,
            'player_id': player_id,
            'choice': choice,
            'picked_card_id': picked_card_id,
            'picked_card_type': picked_card_type,
        }
        if resting_figure_ids:
            payload['resting_figure_ids'] = resting_figure_ids
        response = requests.post(
            f'{settings.SERVER_URL}/games/finish_battle_draw',
            json=payload,
            timeout=10
        )
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to resolve draw: {str(e)}"}


def resolve_pending_battle_choice(game_id, player_id):
    """Apply a server-side default for an expired post-battle choice."""
    try:
        response = requests.post(
            f'{settings.SERVER_URL}/games/resolve_pending_battle_choice',
            json={'game_id': game_id, 'player_id': player_id},
            timeout=10,
        )
        return response.json()
    except requests.RequestException as e:
        return {'success': False, 'message': f"Failed to resolve pending battle choice: {str(e)}"}
