# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for the Deck class: card creation, shuffle, deal, draw, return."""
import pytest


@pytest.fixture
def game_with_deck(db):
    """Create a minimal game with a fully initialized deck."""
    from models import Game
    game = Game(current_round=1, stake=35)
    db.session.add(game)
    db.session.commit()
    from game_service.deck import Deck
    deck = Deck(game)
    deck.create()
    deck.shuffle()
    return game


@pytest.fixture
def player_in_game(db, game_with_deck):
    from models import Player
    p = Player(user_id=None, game_id=game_with_deck.id, turns_left=6, points=0)
    db.session.add(p)
    db.session.commit()
    return p


class TestDeckCreate:
    def test_deck_create_generates_64_main_cards(self, app, game_with_deck, db):
        from models import MainCard
        count = MainCard.query.filter_by(game_id=game_with_deck.id).count()
        assert count == 64  # 4 suits × 8 ranks × 2 copies

    def test_deck_create_generates_40_side_cards(self, app, game_with_deck, db):
        from models import SideCard
        count = SideCard.query.filter_by(game_id=game_with_deck.id).count()
        assert count == 40  # 4 suits × 5 ranks × 2 copies

    def test_deck_all_main_cards_start_in_deck(self, app, game_with_deck, db):
        from models import MainCard
        cards = MainCard.query.filter_by(game_id=game_with_deck.id, in_deck=False).count()
        assert cards == 0

    def test_deck_all_side_cards_start_in_deck(self, app, game_with_deck, db):
        from models import SideCard
        cards = SideCard.query.filter_by(game_id=game_with_deck.id, in_deck=False).count()
        assert cards == 0


class TestDeckShuffle:
    def test_deck_shuffle_assigns_positions(self, app, game_with_deck, db):
        from models import MainCard
        cards_with_position = MainCard.query.filter(
            MainCard.game_id == game_with_deck.id,
            MainCard.deck_position.isnot(None),
        ).count()
        assert cards_with_position == 64

    def test_deck_shuffle_positions_are_unique(self, app, game_with_deck, db):
        from models import MainCard
        positions = [
            c.deck_position
            for c in MainCard.query.filter_by(game_id=game_with_deck.id).all()
        ]
        assert len(set(positions)) == len(positions)


class TestDeckDeal:
    def test_deck_deal_cards_assigns_to_players(self, app, db, game_with_deck, player_in_game):
        from game_service.deck import Deck
        from models import MainCard
        deck = Deck(game_with_deck)
        deck.deal_cards([player_in_game], num_main_cards=5, num_side_cards=0)
        dealt = MainCard.query.filter_by(
            game_id=game_with_deck.id,
            player_id=player_in_game.id,
            in_deck=False,
        ).count()
        assert dealt == 5

    def test_deck_deal_cards_marks_not_in_deck(self, app, db, game_with_deck, player_in_game):
        from game_service.deck import Deck
        from models import MainCard
        deck = Deck(game_with_deck)
        deck.deal_cards([player_in_game], num_main_cards=3, num_side_cards=0)
        still_in_deck = MainCard.query.filter_by(
            game_id=game_with_deck.id,
            player_id=player_in_game.id,
            in_deck=True,
        ).count()
        assert still_in_deck == 0


class TestDeckDrawCards:
    def test_deck_draw_cards_main_type(self, app, db, game_with_deck, player_in_game):
        from game_service.deck import Deck
        deck = Deck(game_with_deck)
        drawn = deck.draw_cards(player_in_game, 3, card_type='main')
        assert len(drawn) == 3

    def test_deck_draw_cards_side_type(self, app, db, game_with_deck, player_in_game):
        from game_service.deck import Deck
        deck = Deck(game_with_deck)
        drawn = deck.draw_cards(player_in_game, 3, card_type='side')
        assert len(drawn) == 3

    def test_deck_draw_cards_raises_when_empty(self, app, db, game_with_deck, player_in_game):
        from game_service.deck import Deck
        from models import MainCard
        # Mark all main cards as out of deck
        MainCard.query.filter_by(game_id=game_with_deck.id).update({'in_deck': False})
        db.session.commit()
        deck = Deck(game_with_deck)
        with pytest.raises(ValueError):
            deck.draw_cards(player_in_game, 1, card_type='main')


class TestReturnCardsToDeck:
    def test_return_card_to_deck_sets_in_deck_true(self, app, db, game_with_deck, player_in_game):
        from game_service.deck import Deck
        from models import MainCard
        deck = Deck(game_with_deck)
        drawn = deck.draw_cards(player_in_game, 1, card_type='main')
        card = drawn[0]
        assert card.in_deck is False
        deck.return_card_to_deck(card)
        db.session.refresh(card)
        assert card.in_deck is True

    def test_return_card_to_deck_assigns_max_position_plus_one(self, app, db, game_with_deck, player_in_game):
        from game_service.deck import Deck
        from models import MainCard
        deck = Deck(game_with_deck)
        drawn = deck.draw_cards(player_in_game, 1, card_type='main')
        card = drawn[0]
        max_pos = db.session.query(db.func.max(MainCard.deck_position)).filter_by(
            game_id=game_with_deck.id, in_deck=True
        ).scalar() or 0
        deck.return_card_to_deck(card)
        db.session.refresh(card)
        assert card.deck_position == max_pos + 1

    def test_return_cards_to_deck_batch(self, app, db, game_with_deck, player_in_game):
        from game_service.deck import Deck
        deck = Deck(game_with_deck)
        drawn = deck.draw_cards(player_in_game, 3, card_type='main')
        for c in drawn:
            assert c.in_deck is False
        deck.return_cards_to_deck(drawn)
        for c in drawn:
            db.session.refresh(c)
            assert c.in_deck is True


class TestDrawMaharaja:
    def test_draw_maharaja_black_returns_club_or_spade_king(self, app, db, game_with_deck, player_in_game):
        from game_service.deck import Deck
        deck = Deck(game_with_deck)
        king = deck.draw_maharaja('black', player_in_game)
        assert king.rank.value == 'K'
        assert king.suit.value in ('Clubs', 'Spades')

    def test_draw_maharaja_red_returns_heart_or_diamond_king(self, app, db, game_with_deck, player_in_game):
        from game_service.deck import Deck
        deck = Deck(game_with_deck)
        king = deck.draw_maharaja('red', player_in_game)
        assert king.rank.value == 'K'
        assert king.suit.value in ('Hearts', 'Diamonds')

    def test_draw_maharaja_raises_when_no_king_available(self, app, db, game_with_deck, player_in_game):
        from game_service.deck import Deck
        from models import MainCard, MainRank
        # Remove all kings from deck
        MainCard.query.filter_by(
            game_id=game_with_deck.id, rank=MainRank.KING.value, in_deck=True
        ).update({'in_deck': False})
        db.session.commit()
        deck = Deck(game_with_deck)
        with pytest.raises(RuntimeError):
            deck.draw_maharaja('black', player_in_game)
