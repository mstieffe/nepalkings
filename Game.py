import requests
import settings

class Game:
    def __init__(self, game_dict, user_dict):
        self.game_id = game_dict['id']
        self.state = game_dict['state']
        self.date = game_dict['date']
        self.players = []
        self.cards = []
        self.opponent_name = None
        self.player_id = None

        for player_dict in game_dict.get('players', []):
            self.players.append({
                'player_id': player_dict['id'],
                'user_id': player_dict['user_id'],
                'username': player_dict['username']
            })

        for card_dict in game_dict.get('cards', []):
            self.cards.append({
                'card_id': card_dict['id'],
                'suit': card_dict['suit'],
                'rank': card_dict['rank'],
                'player_id': card_dict['player_id']
            })

        user_id = user_dict.get('id')
        for player_dict in self.players:
            if player_dict['user_id'] == user_id:
                self.player_id = player_dict['player_id']
            else:
                self.opponent_name = player_dict['username']

    def update(self):
        try:
            response = requests.get(f'{settings.SERVER_URL}/games/get_game', params={'game_id': self.game_id})
            if response.status_code != 200:
                #print(response.json()['message'])
                print("Failed to update game")
                return

            game_data = response.json()
            game = game_data.get('game')

            if not game:
                print("Game data not found in response")
                return

            self.game_id = game['id']
            self.state = game['state']
            self.date = game['date']
            self.players = []
            self.cards = []

            for player_dict in game.get('players', []):
                self.players.append({
                    'player_id': player_dict['id'],
                    'user_id': player_dict['user_id'],
                    'username': player_dict['username']
                })

            for card_dict in game.get('cards', []):
                self.cards.append({
                    'card_id': card_dict['id'],
                    'suit': card_dict['suit'],
                    'rank': card_dict['rank'],
                    'player_id': card_dict['player_id']
                })

        except Exception as e:
            print(f"An error occurred: {str(e)}")

    def get_hand(self, is_opponent=False):
        player_id = self.player_id if not is_opponent else next((player['player_id'] for player in self.players if player['username'] == self.opponent_name), None)

        if player_id is None:
            print("Player ID not found")
            return []

        hand = [card for card in self.cards if card['player_id'] == player_id]
        return hand