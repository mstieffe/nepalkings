# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
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
        from models import Game, db
        game = db.session.get(Game, card.game_id)
        if not game:
            raise ValueError(f"Game with id {card.game_id} not found")
        deck = DeckManager.get_deck_for_game(game)
        deck.return_card_to_deck(card)

    @staticmethod
    def draw_cards_from_deck(game, player, num_cards, card_type="main", force=False):
        """Draw a batch of cards from the deck, respecting max hand size.

        If drawing *num_cards* would exceed the maximum hand size, the
        number drawn is clamped so the hand stays at the limit.
        Only cards actually in the player's hand (not part of a figure)
        count towards the hand size limit.

        If *force* is True, skip the hand-size check entirely (e.g. for
        spell draws where the client will prompt the player to discard).
        """
        from models import MainCard, SideCard
        import server_settings as settings

        if not force:
            if card_type == 'main':
                current = MainCard.query.filter_by(
                    player_id=player.id, in_deck=False, part_of_figure=False).count()
                max_size = settings.MAX_MAIN_HAND_SIZE
            else:
                current = SideCard.query.filter_by(
                    player_id=player.id, in_deck=False, part_of_figure=False).count()
                max_size = settings.MAX_SIDE_HAND_SIZE

            allowed = max(0, max_size - current)
            actual = min(num_cards, allowed)
            if actual <= 0:
                return []
        else:
            actual = num_cards

        deck = DeckManager.get_deck_for_game(game)
        return deck.draw_cards(player, actual, card_type)

    @staticmethod
    def return_cards_to_deck(cards):
        """Return a batch of cards to the deck."""
        if not cards:
            raise ValueError("No cards to return")

        # Get game_id from the first card
        game_id = cards[0].game_id
        
        # Query the game from the database
        from models import Game, db
        game = db.session.get(Game, game_id)
        
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