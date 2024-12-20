import requests
from config import settings

def add_log_entry(game_id, player_id, round_number, turn_number, message, author, entry_type):
    """
    Add a log entry for a game event.

    :param game_id: ID of the game.
    :param player_id: ID of the player associated with the event (optional for system messages).
    :param round_number: Round number of the event.
    :param turn_number: Turn number of the event.
    :param message: Log message.
    :param author: Author of the log entry ('system', 'player', etc.).
    :param entry_type: Type of the log entry ('draw', 'play', 'system', etc.).
    :return: Response from the server.
    """
    try:
        payload = {
            'game_id': game_id,
            'player_id': player_id,
            'round_number': round_number,
            'turn_number': turn_number,
            'message': message,
            'author': author,
            'type': entry_type
        }
        response = requests.post(f'{settings.SERVER_URL}/msg/add_log_entry', json=payload)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        raise Exception(f"Failed to add log entry: {str(e)}")


def fetch_log_entries(game_id):
    """
    Fetch log entries for a game.

    :param game_id: ID of the game.
    :return: List of log entries.
    """
    try:
        response = requests.get(f'{settings.SERVER_URL}/msg/get_log_entries', params={'game_id': game_id})
        response.raise_for_status()
        return response.json().get('log_entries', [])
    except requests.RequestException as e:
        raise Exception(f"Failed to fetch log entries: {str(e)}")


def send_chat_message(game_id, sender_id, receiver_id, message):
    """
    Send a chat message to another player in a game.

    :param game_id: ID of the game.
    :param sender_id: ID of the sender.
    :param receiver_id: ID of the receiver.
    :param message: Message content.
    :return: Response from the server.
    """
    try:
        payload = {
            'game_id': game_id,
            'sender_id': sender_id,
            'receiver_id': receiver_id,
            'message': message
        }
        response = requests.post(f'{settings.SERVER_URL}/msg/add_chat_message', json=payload)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        raise Exception(f"Failed to send chat message: {str(e)}")


def fetch_chat_messages(game_id):
    """
    Fetch chat messages for a game.

    :param game_id: ID of the game.
    :return: List of chat messages.
    """
    try:
        response = requests.get(f'{settings.SERVER_URL}/msg/get_chat_messages', params={'game_id': game_id})
        response.raise_for_status()
        return response.json().get('chat_messages', [])
    except requests.RequestException as e:
        raise Exception(f"Failed to fetch chat messages: {str(e)}")
