import requests
from config import settings
from game.components.cards.card import Card

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
            

        except Exception as e:
            print(f"An error occurred: {str(e)}")

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
            self.update()
            #print(f"{card_type.capitalize()} cards successfully changed and game updated.")
            return new_cards
        except Exception as e:
            print(f"An error occurred while changing {card_type} cards: {str(e)}")
            return []





