#from server.game_service.deck import Deck
#from server.models import Game, Player, MainCard, SideCard, db

class DeckManager:
    @staticmethod
    def get_deck_for_game(game):
        from game_service.deck import Deck  # Import moved here to avoid circular dependency
        """Return a Deck instance for the specified game."""
        return Deck(game)

    @staticmethod
    def create_and_shuffle_deck(game):
        """Create a new deck, shuffle it, and store the cards in the database."""
        deck = DeckManager.get_deck_for_game(game)
        deck.create()  # Create the deck in the database
        deck.shuffle()  # Shuffle the cards

    @staticmethod
    def deal_cards_to_players(game, players, num_main_cards, num_side_cards):
        """Deal the specified number of cards to the players."""
        deck = DeckManager.get_deck_for_game(game)
        deck.deal_cards(players, num_main_cards, num_side_cards)

    @staticmethod
    def return_card_to_deck(card):
        """Return a single card to the deck by updating its state in the database."""
        from models import Game
        game = Game.query.get(card.game_id)
        if not game:
            raise ValueError(f"Game with id {card.game_id} not found")
        deck = DeckManager.get_deck_for_game(game)
        deck.return_card_to_deck(card)

    @staticmethod
    def draw_cards_from_deck(game, player, num_cards, card_type="main"):
        """Draw a batch of cards from the deck."""
        deck = DeckManager.get_deck_for_game(game)
        return deck.draw_cards(player, num_cards, card_type)

    @staticmethod
    def return_cards_to_deck(cards):
        """Return a batch of cards to the deck."""
        if not cards:
            raise ValueError("No cards to return")

        # Get game_id from the first card
        game_id = cards[0].game_id
        
        # Query the game from the database
        from models import Game
        game = Game.query.get(game_id)
        
        if not game:
            raise ValueError(f"Game with id {game_id} not found")
        
        deck = DeckManager.get_deck_for_game(game)
        deck.return_cards_to_deck(cards)

    @staticmethod
    def shuffle_deck(game):
        """Shuffle the deck."""
        deck = DeckManager.get_deck_for_game(game)
        deck.shuffle()

    @staticmethod
    def delete_deck(game):
        """Delete all cards associated with the game."""
        deck = DeckManager.get_deck_for_game(game)
        deck.delete()

    @staticmethod
    def draw_maharaja(game, color, player):
        """Draw the Maharaja card from the deck."""
        deck = DeckManager.get_deck_for_game(game)
        return deck.draw_maharaja(color, player)