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
