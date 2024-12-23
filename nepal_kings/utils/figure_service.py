import requests
from config import settings

def fetch_figures(player_id):
    """
    Fetch all figures associated with a specific player from the server.
    """
    response = requests.get(f'{settings.SERVER_URL}/figures/get_figures', params={'player_id': player_id})
    if response.status_code != 200:
        raise Exception(f"Failed to fetch figures: {response.json().get('message', 'Unknown error')}")
    return response.json().get('figures', [])

def fetch_figure(figure_id):
    """
    Fetch a single figure by its ID.
    """
    response = requests.get(f'{settings.SERVER_URL}/figures/get_figure', params={'figure_id': figure_id})
    if response.status_code != 200:
        raise Exception(f"Failed to fetch figure: {response.json().get('message', 'Unknown error')}")
    return response.json().get('figure', {})

def create_figure(player_id, game_id, family_name, color, name, suit, description, upgrade_family_name, cards):
    """
    Create a new figure on the server.
    :param player_id: ID of the player creating the figure.
    :param game_id: ID of the game associated with the figure.
    :param family_name: Name of the figure's family.
    :param color: Color of the figure.
    :param name: Name of the figure.
    :param suit: Suit of the figure.
    :param description: Description of the figure.
    :param upgrade_family_name: Name of the upgrade family, if any.
    :param cards: List of cards used in the figure (with their roles).
    """
    data = {
        'player_id': player_id,
        'game_id': game_id,
        'family_name': family_name,
        'color': color,
        'name': name,
        'suit': suit,
        'description': description,
        'upgrade_family_name': upgrade_family_name,
        'cards': cards
    }
    response = requests.post(f'{settings.SERVER_URL}/figures/create_figure', json=data)
    if response.status_code != 200:
        raise Exception(f"Failed to create figure: {response.json().get('message', 'Unknown error')}")
    return response.json()

def update_figure(figure_id, name=None, suit=None, description=None, upgrade_family_name=None, cards=None):
    """
    Update an existing figure on the server.
    :param figure_id: ID of the figure to update.
    :param name: Updated name of the figure.
    :param suit: Updated suit of the figure.
    :param description: Updated description of the figure.
    :param upgrade_family_name: Updated upgrade family name, if any.
    :param cards: Updated list of cards used in the figure (with their roles).
    """
    data = {
        'figure_id': figure_id,
        'name': name,
        'suit': suit,
        'description': description,
        'upgrade_family_name': upgrade_family_name,
        'cards': cards
    }
    response = requests.post(f'{settings.SERVER_URL}/figures/update_figure', json=data)
    if response.status_code != 200:
        raise Exception(f"Failed to update figure: {response.json().get('message', 'Unknown error')}")
    return response.json()

def delete_figure(figure_id):
    """
    Delete a figure by its ID.
    :param figure_id: ID of the figure to delete.
    """
    response = requests.post(f'{settings.SERVER_URL}/figures/delete_figure', json={'figure_id': figure_id})
    if response.status_code != 200:
        raise Exception(f"Failed to delete figure: {response.json().get('message', 'Unknown error')}")
    return response.json()
