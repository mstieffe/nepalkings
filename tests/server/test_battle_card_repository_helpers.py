# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Characterization tests for battle-card repository route helpers."""

import importlib
import inspect
from types import SimpleNamespace


games = importlib.import_module('routes.games')


def _make_duel_game(db, two_users):
    from models import Game, Player

    user, _ = two_users
    game = Game(
        current_round=1,
        stake=35,
        mode='duel',
        conquer_move_model='battle_move',
    )
    db.session.add(game)
    db.session.flush()
    player = Player(
        user_id=user.id,
        game_id=game.id,
        turns_left=3,
        points=0,
    )
    db.session.add(player)
    db.session.commit()
    return game, player


def _make_main_card(db, game, player=None, *, rank=None, reserved=True):
    from models import MainCard, MainRank, Suit

    card = MainCard(
        game_id=game.id,
        player_id=player.id if player else None,
        suit=Suit.HEARTS,
        rank=rank or MainRank.SEVEN,
        value=7,
        in_deck=False,
        part_of_figure=False,
        part_of_battle_move=reserved,
    )
    db.session.add(card)
    db.session.flush()
    return card


def _make_side_card(db, game, player=None, *, reserved=True):
    from models import SideCard, SideRank, Suit

    card = SideCard(
        game_id=game.id,
        player_id=player.id if player else None,
        suit=Suit.SPADES,
        rank=SideRank.TWO,
        value=2,
        in_deck=False,
        part_of_figure=False,
        part_of_battle_move=reserved,
    )
    db.session.add(card)
    db.session.flush()
    return card


def _make_battle_move(
    db,
    game,
    player,
    card,
    *,
    card_type='main',
    secondary=None,
    played_round=None,
):
    from models import BattleMove

    move = BattleMove(
        game_id=game.id,
        player_id=player.id,
        family_name='Double Dagger' if secondary else 'Dagger',
        card_id=card.id,
        card_type=card_type,
        card_id_b=secondary.id if secondary else None,
        card_type_b='side' if secondary else None,
        suit='Hearts',
        suit_b='Spades' if secondary else None,
        rank='7+2' if secondary else '7',
        value=9 if secondary else 7,
        value_a=7 if secondary else None,
        value_b=2 if secondary else None,
        played_round=played_round,
    )
    db.session.add(move)
    db.session.flush()
    return move


def test_battle_card_repository_route_api_is_stable():
    expected_signatures = {
        '_collect_battle_move_cards': '(game_id)',
        '_return_unplayed_battle_move_cards': '(game_id)',
        '_delete_all_battle_moves': '(game_id)',
        '_first_deterministic_returnable_card': '(game_id)',
    }

    for name, expected_signature in expected_signatures.items():
        helper = getattr(games, name)
        assert str(inspect.signature(helper)) == expected_signature
        assert helper.__module__ == 'routes.games'


def test_collect_battle_move_cards_preserves_primary_secondary_and_move_order(
    db,
    two_users,
):
    game, player = _make_duel_game(db, two_users)
    main_card = _make_main_card(db, game, player)
    side_card = _make_side_card(db, game, player)
    move = _make_battle_move(
        db,
        game,
        player,
        main_card,
        secondary=side_card,
        played_round=0,
    )
    db.session.commit()

    cards, moves = games._collect_battle_move_cards(game.id)

    assert [(card.id, card_type) for card, card_type in cards] == [
        (main_card.id, 'main'),
        (side_card.id, 'side'),
    ]
    assert [row.id for row in moves] == [move.id]


def test_return_unplayed_battle_move_cards_restores_cards_and_keeps_played_move(
    db,
    two_users,
):
    from models import BattleMove

    game, player = _make_duel_game(db, two_users)
    unplayed_main = _make_main_card(db, game, player)
    unplayed_side = _make_side_card(db, game, player)
    unplayed_move = _make_battle_move(
        db,
        game,
        player,
        unplayed_main,
        secondary=unplayed_side,
    )
    played_card = _make_main_card(db, game, player)
    played_move = _make_battle_move(
        db,
        game,
        player,
        played_card,
        played_round=0,
    )
    db.session.commit()
    unplayed_move_id = unplayed_move.id

    result = games._return_unplayed_battle_move_cards(game.id)
    db.session.flush()

    assert result is None
    assert db.session.get(BattleMove, unplayed_move_id) is None
    assert db.session.get(BattleMove, played_move.id) is played_move
    assert unplayed_main.part_of_battle_move is False
    assert unplayed_main.in_deck is False
    assert unplayed_side.part_of_battle_move is False
    assert unplayed_side.in_deck is False
    assert played_card.part_of_battle_move is True
    assert played_card.in_deck is False


def test_delete_all_battle_moves_removes_legacy_moves_and_conquer_tactics(
    db,
    two_users,
):
    from models import BattleMove, ConquerTactic

    game, player = _make_duel_game(db, two_users)
    main_card = _make_main_card(db, game, player)
    _make_battle_move(db, game, player, main_card, played_round=0)
    tactic = ConquerTactic(
        game_id=game.id,
        player_id=player.id,
        card_id=main_card.id,
        card_type='main',
        family_name='Dagger',
        suit='Hearts',
        rank='7',
        value=7,
        status='played',
        played_round=0,
    )
    db.session.add(tactic)
    db.session.commit()

    result = games._delete_all_battle_moves(game.id)
    db.session.flush()

    assert result is None
    assert BattleMove.query.filter_by(game_id=game.id).count() == 0
    assert ConquerTactic.query.filter_by(game_id=game.id).count() == 0


def test_first_deterministic_returnable_card_prefers_main_before_side(
    db,
    two_users,
):
    game, player = _make_duel_game(db, two_users)
    side_card = _make_side_card(db, game, player)
    _make_battle_move(
        db,
        game,
        player,
        side_card,
        card_type='side',
        played_round=0,
    )
    orphaned_main = _make_main_card(db, game, reserved=False)
    db.session.commit()

    card, card_type = games._first_deterministic_returnable_card(game.id)

    assert card is orphaned_main
    assert card_type == 'main'


def test_first_deterministic_returnable_card_uses_route_collection_hook(
    db,
    two_users,
    monkeypatch,
):
    game, _player = _make_duel_game(db, two_users)
    sentinel = SimpleNamespace(id=99)
    monkeypatch.setattr(
        games,
        '_collect_battle_move_cards',
        lambda game_id: ([(sentinel, 'side')], ['sentinel-move']),
    )

    assert games._first_deterministic_returnable_card(game.id) == (sentinel, 'side')


def test_first_deterministic_returnable_card_returns_empty_pair_without_cards(
    db,
    two_users,
):
    game, _player = _make_duel_game(db, two_users)

    assert games._first_deterministic_returnable_card(game.id) == (None, None)
