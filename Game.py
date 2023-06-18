import requests
import settings

class Game:
    def __init__(self, game_dict, user_dict):
        self.game_id = game_dict['id']
        self.state = game_dict['state']
        self.date = game_dict['date']
        #self.players = []
        #self.cards = []
        self.opponent_name = None
        self.player_id = None

        self.players = game_dict.get('players', [])
        #for player_dict in game_dict.get('players', []):
        #    self.players.append({
        #        'player_id': player_dict['id'],
        #        'user_id': player_dict['user_id'],
        #        'username': player_dict['username']
        #    })

        self.main_cards = game_dict.get('main_cards', [])
        self.side_cards = game_dict.get('side_cards', [])

        #for card_dict in game_dict.get('cards', []):
        #    self.cards.append(card_dict)

        user_id = user_dict.get('id')
        for player_dict in self.players:
            if player_dict['user_id'] == user_id:
                self.player_id = player_dict['id']
            else:
                self.opponent_name = player_dict['username']

        self.turn = True

    def update(self):
        try:
            response = requests.get(f'{settings.SERVER_URL}/games/get_game', params={'game_id': self.game_id})
            if response.status_code != 200:
                #print(response.json()['message'])
                print("Failed to update game")
                return

            game_data = response.json()
            game_dict = game_data.get('game')

            if not game_dict:
                print("Game data not found in response")
                return

            self.game_id = game_dict['id']
            self.state = game_dict['state']
            self.date = game_dict['date']


            self.players = game_dict.get('players', [])
            #for player_dict in game.get('players', []):
            #    self.players.append({
            #        'player_id': player_dict['id'],
            #        'user_id': player_dict['user_id'],
            #        'username': player_dict['username']
            #    })

            self.main_cards = game_dict.get('main_cards', [])
            self.side_cards = game_dict.get('side_cards', [])
            #for card_dict in game.get('cards', []):
            #    self.cards.append(card_dict)
        except Exception as e:
            print(f"An error occurred: {str(e)}")

    def get_hand(self, is_opponent=False):
        player_id = self.player_id if not is_opponent else next((player['player_id'] for player in self.players if player['username'] == self.opponent_name), None)

        if player_id is None:
            print("Player ID not found")
            return []

        main_hand = [card for card in self.main_cards if card['player_id'] == player_id]
        side_hand = [card for card in self.side_cards if card['player_id'] == player_id]
        return main_hand, side_hand




