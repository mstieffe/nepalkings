import requests
from config import settings
from game.components.cards.card import Card
from utils.msg_service import fetch_log_entries, add_log_entry, fetch_chat_messages, send_chat_message

class Game:
    def __init__(self, game_dict, user_dict):
        self.game_id = game_dict['id']
        self.state = game_dict['state']
        self.date = game_dict['date']
        self.players = game_dict.get('players', [])
        self.main_cards = game_dict.get('main_cards', [])
        self.side_cards = game_dict.get('side_cards', [])
        self.current_round = game_dict.get('current_round', 1)
        self.invader_player_id = game_dict.get('invader_player_id')
        self.turn_player_id = game_dict.get('turn_player_id')

        self.player_id = None
        self.opponent_name = None
        self.current_player = None
        self.opponent_player = None

        user_id = user_dict.get('id')

        # Determine current and opponent players
        for player_dict in self.players:
            if player_dict['user_id'] == user_id:
                self.player_id = player_dict['id']
                self.current_player = player_dict
            else:
                self.opponent_name = player_dict['username']
                self.opponent_player = player_dict

        # Whether it is this player's turn
        self.turn = True if self.turn_player_id == self.player_id else False
        self.invader = True if self.invader_player_id == self.player_id else False

        # Initialize log entries and chat messages
        self.log_entries = []
        self.chat_messages = []

        # Fetch initial data for logs and chats
        self.update_logs()
        self.update_chats()

    def update(self):
        try:
            response = requests.get(f'{settings.SERVER_URL}/games/get_game', params={'game_id': self.game_id})
            if response.status_code != 200:
                print("Failed to update game")
                return

            game_data = response.json()
            game_dict = game_data.get('game')

            if not game_dict:
                print("Game data not found in response")
                return

            # Update game data
            self.game_id = game_dict['id']
            self.state = game_dict['state']
            self.date = game_dict['date']
            self.players = game_dict.get('players', [])
            self.main_cards = game_dict.get('main_cards', [])
            self.side_cards = game_dict.get('side_cards', [])
            self.current_round = game_dict.get('current_round', 1)
            self.invader_player_id = game_dict.get('invader_player_id')
            self.turn_player_id = game_dict.get('turn_player_id')

            # Reinitialize current and opponent players
            for player_dict in self.players:
                if player_dict['id'] == self.player_id:
                    self.current_player = player_dict
                else:
                    self.opponent_name = player_dict['username']
                    self.opponent_player = player_dict

            # Update turn and invader status
            self.turn = True if self.turn_player_id == self.player_id else False
            self.invader = True if self.invader_player_id == self.player_id else False
            
            # Update logs and chats
            self.update_logs()
            self.update_chats()

        except Exception as e:
            print(f"An error occurred: {str(e)}")

    def get_player_username(self, player_id):
        """Fetch the username of a player given their player_id."""
        for player in self.players:
            if player['id'] == player_id:
                return player['username']
        return "Unknown"


    def get_hand(self, is_opponent=False):
        """
        Retrieve the main and side hand of the player or their opponent.
        """
        player_id = self.opponent_player['player_id'] if is_opponent else self.player_id

        # Main hand
        main_hand = [
            Card(
                rank=c['rank'],
                suit=c['suit'],
                value=c['value'],
                card_id=c.get('id'),
                game_id=c.get('game_id'),
                player_id=c.get('player_id'),
                in_deck=c.get('in_deck', True),
                deck_position=c.get('deck_position'),
                part_of_figure=c.get('part_of_figure', False)
            )
            for c in self.main_cards if c['player_id'] == player_id
        ]

        # Side hand
        side_hand = [
            Card(
                rank=c['rank'],
                suit=c['suit'],
                value=c['value'],
                card_id=c.get('id'),
                game_id=c.get('game_id'),
                player_id=c.get('player_id'),
                in_deck=c.get('in_deck', True),
                deck_position=c.get('deck_position'),
                part_of_figure=c.get('part_of_figure', False)
            )
            for c in self.side_cards if c['player_id'] == player_id
        ]

        return main_hand, side_hand


    def change_main_cards(self, cards):
        """Change the selected main cards and return the new cards."""
        return self._change_cards(cards, card_type="main")

    def change_side_cards(self, cards):
        """Change the selected side cards and return the new cards."""
        return self._change_cards(cards, card_type="side")

    def _change_cards(self, cards, card_type):
        """Helper function to change cards on the server and return the new cards."""
        try:
            response = requests.post(f'{settings.SERVER_URL}/games/change_cards', json={
                'game_id': self.game_id,
                'player_id': self.player_id,
                'card_type': card_type,
                'cards': [card.serialize() for card in cards]
            })

            if response.status_code != 200:
                print(f"Failed to change {card_type} cards: {response.json().get('message', 'Unknown error')}")
                return []

            # Update the game state after a successful response
            new_cards = response.json().get('new_cards', [])

            # Log the card change action
            round_number = self.current_round
            turn_number = self.current_player.get('turns_left', 0)  # Example: Remaining turns
            message = f"{self.current_player.get('username', 'Player')} changed {len(cards)} {card_type} card(s)."
            self.add_log_entry(round_number, turn_number, message, self.current_player.get('username', 'Player'), 'card_change')

            self.update()

            return new_cards
        except Exception as e:
            print(f"An error occurred while changing {card_type} cards: {str(e)}")
            return []

    def update_logs(self):
        """Fetch and update log entries."""
        try:
            self.log_entries = fetch_log_entries(self.game_id)
        except Exception as e:
            print(f"Failed to fetch log entries: {str(e)}")

    def add_log_entry(self, round_number, turn_number, message, author, entry_type):
        """Add a log entry and update the log list."""
        try:
            add_log_entry(self.game_id, self.player_id, round_number, turn_number, message, author, entry_type)
            self.update_logs()
        except Exception as e:
            print(f"Failed to add log entry: {str(e)}")

    def update_chats(self):
        """Fetch and update chat messages."""
        try:
            self.chat_messages = fetch_chat_messages(self.game_id)
        except Exception as e:
            print(f"Failed to fetch chat messages: {str(e)}")

    def send_chat_message(self, receiver_id, message):
        """Send a chat message and update the chat list."""
        try:
            send_chat_message(self.game_id, self.player_id, receiver_id, message)
            self.update_chats()
        except Exception as e:
            print(f"Failed to send chat message: {str(e)}")




