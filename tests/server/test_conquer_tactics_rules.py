# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Characterization tests for Conquer tactics-hand domain rules."""

import importlib
import pickle
from types import SimpleNamespace


def _game_with_players(db, two_users):
    from models import Game, Player

    game = Game(
        state='active',
        mode='conquer',
        conquer_move_model='tactics_hand',
        battle_round=0,
    )
    db.session.add(game)
    db.session.flush()
    players = [
        Player(user_id=user.id, game_id=game.id)
        for user in two_users
    ]
    db.session.add_all(players)
    db.session.flush()
    game.invader_player_id = players[0].id
    return game, players


class TestConquerTacticsRulesCompatibility:
    def test_route_reexports_canonical_functions_and_constants(self):
        canonical_module = importlib.import_module(
            'game_service.conquer_tactics_rules'
        )
        legacy_module = importlib.import_module('routes.games')

        for name in (
            '_is_tactics_hand_conquer',
            '_get_tactic_card',
            '_conquer_tactic_rank',
            '_same_conquer_tactic_colour',
            '_validate_conquer_tactic_family_rank',
            '_battle_player_skipped_round',
            '_battle_player_completed_round',
            '_battle_round_complete',
            '_battle_all_rounds_complete',
            '_advance_conquer_tactic_turn',
            '_validate_conquer_tactic_call_figure',
        ):
            canonical = getattr(canonical_module, name)
            legacy = getattr(legacy_module, name)
            assert legacy is canonical
            assert canonical.__module__ == 'routes.games'
            assert pickle.loads(pickle.dumps(canonical)) is canonical

        for name in (
            '_CONQUER_BLACK_SUITS',
            '_CONQUER_CALL_FIELD_MAP',
            '_CONQUER_RED_SUITS',
            '_CONQUER_TACTIC_FAMILY_BY_RANK',
        ):
            assert (
                getattr(legacy_module, name)
                is getattr(canonical_module, name)
            )


class TestTacticsHandDetection:
    def test_requires_conquer_mode_and_tactics_hand_model(self):
        from routes.games import _is_tactics_hand_conquer

        assert _is_tactics_hand_conquer(None) is False
        assert _is_tactics_hand_conquer(SimpleNamespace(
            mode='duel',
            conquer_move_model='tactics_hand',
        )) is False
        assert _is_tactics_hand_conquer(SimpleNamespace(
            mode='conquer',
            conquer_move_model=None,
        )) is False
        assert _is_tactics_hand_conquer(SimpleNamespace(
            mode='conquer',
            conquer_move_model='battle_move',
        )) is False
        assert _is_tactics_hand_conquer(SimpleNamespace(
            mode='conquer',
            conquer_move_model='tactics_hand',
        )) is True


class TestConquerTacticRankAndColour:
    def test_normalises_enum_like_and_scalar_ranks(self):
        from routes.games import _conquer_tactic_rank

        assert _conquer_tactic_rank(None) == ''
        assert _conquer_tactic_rank(SimpleNamespace(value='A')) == 'A'
        assert _conquer_tactic_rank(7) == '7'

    def test_matches_only_suits_in_the_same_known_colour_group(self):
        from routes.games import _same_conquer_tactic_colour

        assert _same_conquer_tactic_colour('Hearts', 'Diamonds') is True
        assert _same_conquer_tactic_colour('Clubs', 'Spades') is True
        assert _same_conquer_tactic_colour('Hearts', 'Clubs') is False
        assert _same_conquer_tactic_colour('Unknown', 'Unknown') is False


class TestGetAndValidateConquerTacticCards:
    def test_loads_primary_and_secondary_cards_by_declared_type(
            self, app, db, two_users):
        from models import (
            MainCard,
            MainRank,
            SideCard,
            SideRank,
            Suit,
        )
        from routes.games import _get_tactic_card

        game, players = _game_with_players(db, two_users)
        main = MainCard(
            game_id=game.id,
            player_id=players[0].id,
            suit=Suit.HEARTS,
            rank=MainRank.SEVEN,
            value=7,
            in_deck=False,
            part_of_figure=False,
        )
        side = SideCard(
            game_id=game.id,
            player_id=players[0].id,
            suit=Suit.SPADES,
            rank=SideRank.TWO,
            value=2,
            in_deck=False,
            part_of_figure=False,
        )
        db.session.add_all([main, side])
        db.session.flush()
        tactic = SimpleNamespace(
            card_id=main.id,
            card_type='main',
            card_id_b=side.id,
            card_type_b='side',
        )

        assert _get_tactic_card(tactic) is main
        assert _get_tactic_card(tactic, secondary=True) is side
        tactic.card_id_b = None
        assert _get_tactic_card(tactic, secondary=True) is None

    def test_validates_single_and_double_dagger_card_contracts(
            self, app, db, two_users):
        from models import MainCard, MainRank, Suit
        from routes.games import _validate_conquer_tactic_family_rank

        game, players = _game_with_players(db, two_users)
        cards = [
            MainCard(
                game_id=game.id,
                player_id=players[0].id,
                suit=Suit.HEARTS,
                rank=rank,
                value=value,
                in_deck=False,
                part_of_figure=False,
            )
            for rank, value in (
                (MainRank.SEVEN, 7),
                (MainRank.EIGHT, 8),
            )
        ]
        db.session.add_all(cards)
        db.session.flush()
        tactic = SimpleNamespace(
            game_id=game.id,
            player_id=players[0].id,
            card_id=cards[0].id,
            card_type='main',
            card_id_b=None,
            card_type_b=None,
            family_name='Dagger',
            rank='7',
        )

        assert _validate_conquer_tactic_family_rank(tactic) is None
        tactic.rank = '8'
        assert _validate_conquer_tactic_family_rank(
            tactic) == 'Tactic rank does not match its card'

        tactic.family_name = 'Double Dagger'
        tactic.rank = '7+8'
        tactic.card_id_b = cards[1].id
        tactic.card_type_b = 'main'
        assert _validate_conquer_tactic_family_rank(tactic) is None

        cards[1].in_deck = True
        assert _validate_conquer_tactic_family_rank(
            tactic) == 'Tactic card is not available'


class TestConquerTacticCallValidation:
    def test_requires_owned_figure_in_the_family_field(
            self, app, db, two_users):
        from models import Figure
        from routes.games import _validate_conquer_tactic_call_figure

        game, players = _game_with_players(db, two_users)
        village = Figure(
            game_id=game.id,
            player_id=players[0].id,
            family_name='Villager',
            field='village',
            color='offensive',
            name='Villager',
            suit='Hearts',
            produces={},
            requires={},
        )
        castle = Figure(
            game_id=game.id,
            player_id=players[0].id,
            family_name='King',
            field='castle',
            color='offensive',
            name='King',
            suit='Hearts',
            produces={},
            requires={},
        )
        db.session.add_all([village, castle])
        db.session.flush()
        tactic = SimpleNamespace(family_name='Call Villager')

        assert _validate_conquer_tactic_call_figure(
            tactic, None, players[0].id, game.id) is None
        assert _validate_conquer_tactic_call_figure(
            tactic, village.id, players[0].id, game.id) is None
        assert _validate_conquer_tactic_call_figure(
            tactic,
            castle.id,
            players[0].id,
            game.id,
        ) == 'Call Villager can only call a village figure'
        tactic.family_name = 'Dagger'
        assert _validate_conquer_tactic_call_figure(
            tactic,
            village.id,
            players[0].id,
            game.id,
        ) == 'This tactic cannot call a figure'


class TestConquerTacticRoundRules:
    def test_skipped_rounds_accept_equivalent_integer_and_string_values(self):
        from routes.games import _battle_player_skipped_round

        game = SimpleNamespace(
            battle_skipped_rounds={'7': [0, '1', None]},
        )

        assert _battle_player_skipped_round(game, 7, 0) is True
        assert _battle_player_skipped_round(game, 7, '1') is True
        assert _battle_player_skipped_round(game, 7, 'invalid') is False
        assert _battle_player_skipped_round(game, 8, 0) is False

    def test_round_and_all_round_completion_use_both_players(self, app):
        from routes.games import (
            _battle_all_rounds_complete,
            _battle_round_complete,
        )

        players = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
        game = SimpleNamespace(
            id=99_001,
            mode='conquer',
            conquer_move_model='tactics_hand',
            players=players,
            battle_skipped_rounds={
                '1': [0, 1, 2],
                '2': [0, 1, 2],
            },
        )

        assert _battle_round_complete(game, 0) is True
        assert _battle_all_rounds_complete(game) is True
        game.battle_skipped_rounds['2'] = [0, 1]
        assert _battle_all_rounds_complete(game) is False
        game.players = [players[0]]
        assert _battle_round_complete(game, 0) is False

    def test_completed_round_supports_tactic_and_legacy_move_rows(
            self, app, db, two_users):
        from models import BattleMove, ConquerTactic
        from routes.games import _battle_player_completed_round

        game, players = _game_with_players(db, two_users)
        tactic = ConquerTactic(
            game_id=game.id,
            player_id=players[0].id,
            card_id=101,
            card_type='main',
            family_name='Dagger',
            suit='Hearts',
            rank='7',
            value=7,
            status='played',
            played_round=0,
        )
        db.session.add(tactic)
        db.session.flush()

        assert _battle_player_completed_round(
            game, players[0].id, 0) is True
        assert _battle_player_completed_round(
            game, players[1].id, 0) is False

        game.conquer_move_model = 'battle_move'
        legacy_move = BattleMove(
            game_id=game.id,
            player_id=players[1].id,
            family_name='Dagger',
            card_id=102,
            card_type='main',
            suit='Hearts',
            rank='7',
            value=7,
            played_round=1,
        )
        db.session.add(legacy_move)
        db.session.flush()
        assert _battle_player_completed_round(
            game, players[1].id, 1) is True

    def test_turn_advancement_rotates_or_finishes_based_on_other_player(
            self, app, db, two_users):
        from routes.games import _advance_conquer_tactic_turn

        game, players = _game_with_players(db, two_users)
        game.battle_skipped_rounds = {}

        assert _advance_conquer_tactic_turn(game, players[0].id) is True
        assert game.battle_turn_player_id == players[1].id

        game.battle_round = 0
        game.battle_skipped_rounds = {str(players[1].id): [0]}
        assert _advance_conquer_tactic_turn(game, players[0].id) is True
        assert game.battle_round == 1
        assert game.battle_turn_player_id == players[0].id

        game.battle_round = 2
        game.battle_skipped_rounds = {str(players[1].id): [2]}
        assert _advance_conquer_tactic_turn(game, players[0].id) is True
        assert game.battle_turn_player_id is None

        game.players = [players[0]]
        assert _advance_conquer_tactic_turn(game, players[0].id) is False
