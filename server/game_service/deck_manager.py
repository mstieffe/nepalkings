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
        deck = DeckManager.get_deck_for_game(card.game)
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

        game = cards[0].game  # Assume all cards belong to the same game
        deck = DeckManager.get_deck_for_game(game)
        deck.return_cards_to_deck(cards)

    @staticmethod
    def shuffle_deck(game):
        """Shuffle the deck."""
        deck = DeckManager.get_deck_for_game(game)
        deck.shuffle()