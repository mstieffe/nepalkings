import requests
from config import settings
from game.components.cards.card import Card
from utils.msg_service import fetch_log_entries, add_log_entry, fetch_chat_messages, send_chat_message
from utils.figure_service import fetch_figures
from game.components.figures.figure import Figure, FigureFamily
from typing import List, Dict

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

        # Spell-related state
        self.pending_spell_id = game_dict.get('pending_spell_id')
        self.battle_modifier = game_dict.get('battle_modifier')
        self.waiting_for_counter_player_id = game_dict.get('waiting_for_counter_player_id')
        self.pending_spell = None  # Will be loaded if needed
        self.waiting_for_counter = False
        self.active_spell_effects = []  # Will be loaded separately

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
        # Initialize to False so first update() can detect if it's their turn
        self.turn = False
        self.invader = True if self.invader_player_id == self.player_id else False

        # Track previous turn to detect turn changes
        # Initialize to None so first login triggers turn detection if it's their turn
        self.previous_turn_player_id = None
        
        # Auto-fill notification (cleared after showing dialogue)
        self.pending_auto_fill = None

        # Initialize log entries and chat messages
        self.log_entries = []
        self.chat_messages = []

        # Fetch initial data for logs and chats
        self.update_logs()
        self.update_chats()

    def update(self):
        """Update game state from the server."""
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

            # Update spell-related state
            self.pending_spell_id = game_dict.get('pending_spell_id')
            self.battle_modifier = game_dict.get('battle_modifier')
            self.waiting_for_counter_player_id = game_dict.get('waiting_for_counter_player_id')
            
            # Check if we're waiting for this player to counter
            if self.pending_spell_id and self.waiting_for_counter_player_id:
                self.waiting_for_counter = (self.waiting_for_counter_player_id == self.player_id)
                # TODO: Load pending spell details if needed
                # self.pending_spell = spell_service.fetch_pending_spell(self.pending_spell_id)
            else:
                self.waiting_for_counter = False
                self.pending_spell = None

            # Reinitialize current and opponent players
            for player_dict in self.players:
                if player_dict['id'] == self.player_id:
                    self.current_player = player_dict
                else:
                    self.opponent_name = player_dict['username']
                    self.opponent_player = player_dict

            # Update turn and invader status
            previous_turn = self.turn
            self.turn = True if self.turn_player_id == self.player_id else False
            self.invader = True if self.invader_player_id == self.player_id else False

            # Check if turn changed to current player - call start_turn endpoint
            if not previous_turn and self.turn and self.previous_turn_player_id != self.turn_player_id:
                print(f"[TURN CHANGE] Detected turn change to current player. Calling start_turn...")
                self._handle_start_turn()
            
            # Update previous turn player for next check
            self.previous_turn_player_id = self.turn_player_id

            # Update logs and chats
            self.update_logs()
            self.update_chats()

        except Exception as e:
            print(f"An error occurred: {str(e)}")

    def _handle_start_turn(self):
        """Called when turn changes to current player. Checks and handles auto-fill."""
        try:
            payload = {
                'game_id': self.game_id,
                'player_id': self.player_id
            }
            print(f"[START_TURN] Sending payload: game_id={self.game_id} (type={type(self.game_id)}), player_id={self.player_id} (type={type(self.player_id)})")
            
            response = requests.post(
                f'{settings.SERVER_URL}/games/start_turn',
                json=payload
            )
            
            if response.status_code != 200:
                print(f"[START_TURN] Failed with status {response.status_code}: {response.json()}")
                return
            
            data = response.json()
            print(f"[START_TURN] Response: {data}")
            if data.get('success'):
                auto_fill = data.get('auto_fill')
                if auto_fill:
                    # Store for dialogue display
                    print(f"[START_TURN] Auto-fill needed: {auto_fill}")
                    self.pending_auto_fill = auto_fill
                else:
                    print(f"[START_TURN] No auto-fill needed")
        except Exception as e:
            print(f"Error in start_turn: {str(e)}")

    def get_player_username(self, player_id):
        """Fetch the username of a player given their player_id."""
        for player in self.players:
            if player['id'] == player_id:
                return player['username']
        return "Unknown"

    def get_hand(self, is_opponent=False):
        """
        Retrieve the main and side hand of the player or their opponent, excluding cards that are part of a figure.
        """
        player_id = self.opponent_player['id'] if is_opponent else self.player_id

        # Main hand
        main_hand = [
            Card(
                rank=c['rank'],
                suit=c['suit'],
                value=c['value'],
                id=c.get('id'),
                game_id=c.get('game_id'),
                player_id=c.get('player_id'),
                in_deck=c.get('in_deck', True),
                deck_position=c.get('deck_position'),
                part_of_figure=c.get('part_of_figure', False),
                type=c.get('type')  # Include the card type
            )
            for c in self.main_cards
            if c['player_id'] == player_id and not c.get('part_of_figure', False) and not c.get('in_deck', False)
        ]

        # Side hand
        side_hand = [
            Card(
                rank=c['rank'],
                suit=c['suit'],
                value=c['value'],
                id=c.get('id'),
                game_id=c.get('game_id'),
                player_id=c.get('player_id'),
                in_deck=c.get('in_deck', True),
                deck_position=c.get('deck_position'),
                part_of_figure=c.get('part_of_figure', False),
                type=c.get('type')  # Include the card type
            )
            for c in self.side_cards
            if c['player_id'] == player_id and not c.get('part_of_figure', False) and not c.get('in_deck', False)
        ]

        return main_hand, side_hand


    def get_figures(self, families: Dict[str, FigureFamily], is_opponent=False) -> List[Figure]:
        """
        Fetch the figures for the current player from the server.

        :param families: A dictionary mapping family names to FigureFamily instances.
        :return: A list of Figure instances.
        """
        try:
            player_id = self.opponent_player['id'] if is_opponent else self.player_id
            figures_data = fetch_figures(player_id)
            figures = []


            for figure_data in figures_data:
                family_name = figure_data['family_name']
                if family_name not in families:
                    print(f"Skipping unknown family: {family_name}")
                    continue

                family = families[family_name]

                cards = self._load_cards_from_data(figure_data['cards'])


                if not any(cards.values()):
                    print(f"Skipping figure with no valid cards: {figure_data}")
                    continue

                # Safely retrieve number_card and upgrade_card
                number_card = cards.get('number')[0] if cards.get('number') else None
                upgrade_card = cards.get('upgrade')[0] if cards.get('upgrade') else None

                # If upgrade_card is not in the saved cards, try to get it from the family definition
                # Match this figure to the correct variant in the family to get upgrade_card
                key_cards = cards.get('key', [])
                if not upgrade_card and figure_data.get('upgrade_family_name'):
                    # Find matching figure in family definitions
                    for family_figure in family.figures:
                        # Match by suit and cards
                        if (family_figure.suit == figure_data['suit'] and 
                            len(family_figure.key_cards) == len(key_cards)):
                            # Check if key cards match
                            key_cards_match = all(
                                any(kc.rank == fkc.rank and kc.suit == fkc.suit 
                                    for fkc in family_figure.key_cards)
                                for kc in key_cards
                            )
                            # Check if number cards match (if present)
                            number_cards_match = True
                            if number_card and family_figure.number_card:
                                number_cards_match = (number_card.rank == family_figure.number_card.rank and
                                                    number_card.suit == family_figure.number_card.suit)
                            elif number_card or family_figure.number_card:
                                number_cards_match = False
                            
                            if key_cards_match and number_cards_match:
                                upgrade_card = family_figure.upgrade_card
                                break

                figure = Figure(
                    name=figure_data['name'],
                    sub_name=figure_data.get('sub_name', ""),
                    suit=figure_data['suit'],
                    family=family,
                    key_cards=key_cards,
                    number_card=number_card,
                    upgrade_card=upgrade_card,
                    description=figure_data.get('description', ""),
                    upgrade_family_name=figure_data.get('upgrade_family_name'),
                    produces=figure_data.get('produces', {}),
                    requires=figure_data.get('requires', {}),
                    id=figure_data['id'],
                    player_id=figure_data.get('player_id'),
                )
                figures.append(figure)

            return figures
        except Exception as e:
            print(f"Error loading figures: {str(e)}")
            return []

    def calculate_resources(self, families: Dict[str, FigureFamily]) -> Dict[str, Dict[str, int]]:
        """
        Calculate total resources produced and required by all player figures.
        
        :param families: A dictionary mapping family names to FigureFamily instances.
        :return: A dictionary with 'produces' and 'requires' keys, each containing resource totals
        """
        figures = self.get_figures(families)
        total_produces = {}
        total_requires = {}
        
        if settings.DEBUG_ENABLED:
            with open(settings.DEBUG_LOG_PATH, 'a') as f:
                f.write(f"[CLIENT] Calculating resources for {len(figures)} figures\n")
                for figure in figures:
                    f.write(f"[CLIENT] Figure: {figure.name}, produces: {figure.produces}, requires: {figure.requires}\n")
        
        for figure in figures:
            if figure.produces:
                for resource_type, amount in figure.produces.items():
                    if resource_type in total_produces:
                        total_produces[resource_type] += amount
                    else:
                        total_produces[resource_type] = amount
            
            if figure.requires:
                for resource_type, amount in figure.requires.items():
                    if resource_type in total_requires:
                        total_requires[resource_type] += amount
                    else:
                        total_requires[resource_type] = amount
        
        if settings.DEBUG_ENABLED:
            with open(settings.DEBUG_LOG_PATH, 'a') as f:
                f.write(f"[CLIENT] Total produces: {total_produces}\n")
                f.write(f"[CLIENT] Total requires: {total_requires}\n")
        return {'produces': total_produces, 'requires': total_requires}

    @staticmethod
    def _load_cards_from_data(cards_data: List[Dict]) -> Dict[str, List[Card]]:
        """
        Convert card data from the database into Card instances grouped by role.

        :param cards_data: A list of card data dictionaries from the database.
        :return: A dictionary with card roles as keys and lists of Card instances as values.
        """
        cards = {'key': [], 'number': [], 'upgrade': []}

        for card_data in cards_data:
            try:
                card = Card(
                    rank=card_data['rank'],
                    suit=card_data['suit'],
                    value=card_data['value'],
                    id=card_data.get('card_id'),
                    game_id=card_data.get('game_id'),
                    player_id=card_data.get('player_id'),
                    in_deck=card_data.get('in_deck'),
                    deck_position=card_data.get('deck_position'),
                    part_of_figure=card_data.get('part_of_figure'),
                    type=card_data.get('card_type'),
                    role=card_data.get('role')
                )
                # Group cards by their role
                if card_data.get('role') in cards:
                    cards[card_data['role']].append(card)
            except KeyError as e:
                print(f"Skipping card with missing data: {card_data}, Error: {e}")
                continue

        return cards


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


    def change_main_cards(self, cards):
        """Change the selected main cards and return the new cards."""
        return self._change_cards(cards, card_type="main")

    def change_side_cards(self, cards):
        """Change the selected side cards and return the new cards."""
        return self._change_cards(cards, card_type="side")
    
    def discard_main_cards(self, cards):
        """Discard the selected main cards (return to deck without drawing new ones)."""
        return self._discard_cards(cards, card_type="main")
    
    def discard_side_cards(self, cards):
        """Discard the selected side cards (return to deck without drawing new ones)."""
        return self._discard_cards(cards, card_type="side")

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
    
    def _discard_cards(self, cards, card_type):
        """Helper function to discard cards on the server (return to deck without drawing)."""
        try:
            response = requests.post(f'{settings.SERVER_URL}/games/discard_cards', json={
                'game_id': self.game_id,
                'player_id': self.player_id,
                'card_type': card_type,
                'cards': [card.serialize() for card in cards]
            })

            if response.status_code != 200:
                print(f"Failed to discard {card_type} cards: {response.json().get('message', 'Unknown error')}")
                return False

            # Log the card discard action
            round_number = self.current_round
            turn_number = self.current_player.get('turns_left', 0)
            message = f"{self.current_player.get('username', 'Player')} discarded {len(cards)} {card_type} card(s)."
            self.add_log_entry(round_number, turn_number, message, self.current_player.get('username', 'Player'), 'card_discard')

            self.update()

            return True
        except Exception as e:
            print(f"An error occurred while discarding {card_type} cards: {str(e)}")
            return False
