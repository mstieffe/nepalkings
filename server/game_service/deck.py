from models import MainCard, SideCard, db, MainRank, Suit
import random

class Deck:
    def __init__(self, game):
        self.game = game

    def create(self):
        """Create main and side cards and store them in the database."""
        main_ranks = ['7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        side_ranks = ['2', '3', '4', '5', '6']
        suits = ['Hearts', 'Diamonds', 'Clubs', 'Spades']
        rank_to_value = {
            '2': 2,
            '3': 3,
            '4': 4,
            '5': 5,
            '6': 6,
            '7': 7,
            '8': 8,
            '9': 9,
            '10': 10,
            'J': 1,
            'Q': 2,
            'K': 4,
            'A': 3
        }

        # Create two main cards for each rank and suit
        for suit in suits:
            for rank in main_ranks:
                for _ in range(2):  # Create two cards
                    card = MainCard(
                        rank=rank,
                        suit=suit,
                        value=rank_to_value[rank],
                        game_id=self.game.id,
                        in_deck=True
                    )
                    db.session.add(card)

        # Create two side cards for each rank and suit
        for suit in suits:
            for rank in side_ranks:
                for _ in range(2):  # Create two cards
                    card = SideCard(
                        rank=rank,
                        suit=suit,
                        value=rank_to_value[rank],
                        game_id=self.game.id,
                        in_deck=True
                    )
                    db.session.add(card)

        db.session.commit()

    def shuffle(self):
        """Shuffle the deck by randomizing the deck_position field in the database."""
        # Fetch all available cards from the database
        main_cards = MainCard.query.filter_by(game_id=self.game.id, in_deck=True).all()
        side_cards = SideCard.query.filter_by(game_id=self.game.id, in_deck=True).all()

        # Shuffle the cards in-memory
        random.shuffle(main_cards)
        random.shuffle(side_cards)

        # Assign new positions to main cards
        for index, card in enumerate(main_cards):
            card.deck_position = index + 1  # Start positions at 1
        # Assign new positions to side cards
        for index, card in enumerate(side_cards):
            card.deck_position = index + 1  # Start positions at 1

        db.session.commit()

    def deal_cards(self, players, num_main_cards, num_side_cards):
        """Deal a specified number of main and side cards to each player."""
        for player in players:
            # Deal main cards
            main_cards = MainCard.query.filter_by(game_id=self.game.id, in_deck=True).order_by(MainCard.deck_position.asc()).limit(num_main_cards).all()
            for card in main_cards:
                card.player_id = player.id
                card.in_deck = False

            # Deal side cards
            side_cards = SideCard.query.filter_by(game_id=self.game.id, in_deck=True).order_by(SideCard.deck_position.asc()).limit(num_side_cards).all()
            for card in side_cards:
                card.player_id = player.id
                card.in_deck = False

            db.session.commit()

    def draw_cards(self, player, num_cards, card_type="main"):
        """Draw a batch of cards from the deck for the player."""
        if card_type == "main":
            cards = MainCard.query.filter_by(game_id=self.game.id, in_deck=True).order_by(MainCard.deck_position.asc()).limit(num_cards).all()
        else:
            cards = SideCard.query.filter_by(game_id=self.game.id, in_deck=True).order_by(SideCard.deck_position.asc()).limit(num_cards).all()

        if not cards:
            raise ValueError("No more cards available in the deck")

        # Update the card's state
        for card in cards:
            card.player_id = player.id
            card.in_deck = False

        db.session.commit()
        return cards

    def return_card_to_deck(self, card):
        """Return a single card to the end of the appropriate deck (main or side)."""
        # Set the card back to "in deck" status
        card.player_id = None
        card.in_deck = True
        card.part_of_figure = False

        # Check whether we're dealing with a MainCard or SideCard
        if isinstance(card, MainCard):
            max_position = db.session.query(db.func.max(MainCard.deck_position)).filter_by(game_id=self.game.id, in_deck=True).scalar()
            max_position = max_position or 0  # If no cards, start with 0
        elif isinstance(card, SideCard):
            max_position = db.session.query(db.func.max(SideCard.deck_position)).filter_by(game_id=self.game.id, in_deck=True).scalar()
            max_position = max_position or 0  # If no cards, start with 0
        else:
            raise ValueError("Unknown card type")

        # Assign the next available deck position
        next_position = max_position + 1
        card.deck_position = next_position

        # Persist the changes to the database
        db.session.commit()

    def return_cards_to_deck(self, cards):
        """Return a batch of cards to the end of the deck."""
        if not cards:
            raise ValueError("No cards to return")

        # Separate cards into main and side decks
        main_cards = [card for card in cards if isinstance(card, MainCard)]
        side_cards = [card for card in cards if isinstance(card, SideCard)]

        # Find the current maximum position for each deck
        max_main_position = db.session.query(db.func.max(MainCard.deck_position)).filter_by(game_id=self.game.id, in_deck=True).scalar() or 0
        max_side_position = db.session.query(db.func.max(SideCard.deck_position)).filter_by(game_id=self.game.id, in_deck=True).scalar() or 0

        # Assign new positions to main cards
        for card in main_cards:
            max_main_position += 1
            card.player_id = None
            card.in_deck = True
            card.deck_position = max_main_position

        # Assign new positions to side cards
        for card in side_cards:
            max_side_position += 1
            card.player_id = None
            card.in_deck = True
            card.deck_position = max_side_position

        db.session.commit()

    def draw_maharaja(self, color="black", player=None):
        """Draw a random king of the specified color from the deck."""
        try:
            # Map color to suit(s)
            suit_map = {
                "black": [Suit.CLUBS.value, Suit.SPADES.value],
                "red": [Suit.HEARTS.value, Suit.DIAMONDS.value]
            }
            suits = suit_map.get(color.lower(), [color])  # Default to color if not black/red

            # Debugging: Print suits being searched
            print(f"Suits being searched: {suits}")

            print(f"Attempting to draw Maharaja for color: {color}")
            print(f"Game ID: {self.game.id}")
            print(f"Player ID: {player.id}")

            cards = MainCard.query.filter_by(game_id=self.game.id).all()
            print([card.serialize() for card in cards if card.rank == MainRank.KING])

            cards = MainCard.query.filter_by(game_id=self.game.id, in_deck=True, rank=MainRank.KING).all()
            print([card.serialize() for card in cards])


            # Query for the first king of the matching suit(s)
            king = (
                MainCard.query.filter(
                    MainCard.game_id == self.game.id,
                    MainCard.in_deck == True,
                    MainCard.rank == MainRank.KING.value,
                    MainCard.suit.in_(suits)  # Match any of the suits
                )
                .order_by(MainCard.deck_position.asc())  # Sort by position
                .first()
            )

            # Debugging: Print the result of the query
            if king:
                print(f"King found: {king.serialize()}")
            else:
                print("No matching king found.")

            if not king:
                raise ValueError(f"No {color} king available in the deck")

            # Update the card's state
            king.in_deck = False
            king.part_of_figure = True
            if player:
                king.player_id = player.id

            db.session.commit()
            return king

        except Exception as e:
            db.session.rollback()
            raise RuntimeError(f"Failed to draw Maharaja: {e}")
