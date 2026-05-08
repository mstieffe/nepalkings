# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Server-authoritative math and cleanup coverage for ConquerTactic rows."""

from werkzeug.security import generate_password_hash

from models import (CardRole, CardToFigure, ConquerTactic, Figure, Game,
                    Land, MainCard, MainRank, Player, Suit, User)
from routes.games import (_collect_battle_move_cards,
                          _compute_server_total_diff,
                          _delete_all_battle_moves,
                          _return_unplayed_battle_move_cards)


_SUIT_BY_NAME = {
    'Hearts': Suit.HEARTS,
    'Diamonds': Suit.DIAMONDS,
    'Clubs': Suit.CLUBS,
    'Spades': Suit.SPADES,
}

_RANK_BY_VALUE = {
    1: MainRank.JACK,
    2: MainRank.QUEEN,
    3: MainRank.ACE,
    4: MainRank.KING,
    7: MainRank.SEVEN,
    8: MainRank.EIGHT,
    9: MainRank.NINE,
    10: MainRank.TEN,
}

_RANK_VALUE = {
    'J': 1,
    'Q': 2,
    'A': 3,
    'K': 4,
    '7': 7,
    '8': 8,
    '9': 9,
    '10': 10,
}

_RANK_ENUM = {
    'J': MainRank.JACK,
    'Q': MainRank.QUEEN,
    'A': MainRank.ACE,
    'K': MainRank.KING,
    '7': MainRank.SEVEN,
    '8': MainRank.EIGHT,
    '9': MainRank.NINE,
    '10': MainRank.TEN,
}


def _add_player(db_session, game, username):
    user = User(
        username=username,
        password_hash=generate_password_hash('password'),
        gold=100,
    )
    db_session.add(user)
    db_session.flush()

    player = Player(user_id=user.id, game_id=game.id, turns_left=0)
    db_session.add(player)
    db_session.flush()
    return player


def _add_figure(db_session, player, *, family_name, name=None, field='village',
                color='offensive', suit='Hearts', card_values=()):
    fig = Figure(
        game_id=player.game_id,
        player_id=player.id,
        family_name=family_name,
        field=field,
        color=color,
        name=name or family_name,
        suit=suit,
        requires={},
        produces={},
    )
    db_session.add(fig)
    db_session.flush()

    for value, role in card_values:
        card = MainCard(
            game_id=player.game_id,
            player_id=player.id,
            suit=_SUIT_BY_NAME[suit],
            rank=_RANK_BY_VALUE[value],
            value=value,
            in_deck=False,
            part_of_figure=True,
        )
        db_session.add(card)
        db_session.flush()
        db_session.add(CardToFigure(
            figure_id=fig.id,
            card_id=card.id,
            card_type='main',
            role=role,
        ))
    db_session.flush()
    return fig


def _add_tactic(db_session, game, player, *, family_name='Dagger', rank='7',
                suit='Hearts', value=None, played_round=0, status='played',
                call_figure_id=None, secondary_rank=None, secondary_suit=None):
    value = _RANK_VALUE[rank] if value is None else value
    card = MainCard(
        game_id=game.id,
        player_id=player.id,
        suit=_SUIT_BY_NAME[suit],
        rank=_RANK_ENUM[rank],
        value=value,
        in_deck=True if status == 'played' else False,
        part_of_figure=False,
        part_of_battle_move=True,
    )
    db_session.add(card)
    db_session.flush()

    card_b = None
    if secondary_rank:
        secondary_suit = secondary_suit or suit
        card_b = MainCard(
            game_id=game.id,
            player_id=player.id,
            suit=_SUIT_BY_NAME[secondary_suit],
            rank=_RANK_ENUM[secondary_rank],
            value=_RANK_VALUE[secondary_rank],
            in_deck=True if status == 'played' else False,
            part_of_figure=False,
            part_of_battle_move=True,
        )
        db_session.add(card_b)
        db_session.flush()

    tactic = ConquerTactic(
        game_id=game.id,
        player_id=player.id,
        card_id=card.id,
        card_type='main',
        card_id_b=card_b.id if card_b else None,
        card_type_b='main' if card_b else None,
        family_name=family_name,
        suit=suit,
        suit_b=secondary_suit if card_b else None,
        rank=f'{rank}+{secondary_rank}' if secondary_rank else rank,
        value=value + (card_b.value if card_b else 0),
        value_a=value if card_b else None,
        value_b=card_b.value if card_b else None,
        source='config',
        status=status,
        played_round=played_round,
        call_figure_id=call_figure_id,
    )
    db_session.add(tactic)
    db_session.flush()
    return tactic, card, card_b


def _setup_tactics_battle(db_session, *, land_bonus=False):
    game = Game(
        mode='conquer',
        state='open',
        conquer_move_model='tactics_hand',
        battle_confirmed=True,
        battle_round=0,
    )
    db_session.add(game)
    db_session.flush()

    attacker = _add_player(db_session, game, 'tactics_math_attacker')
    defender = _add_player(db_session, game, 'tactics_math_defender')

    if land_bonus:
        land = Land(
            col=300,
            row=400,
            tier=1,
            gold_rate=1.0,
            suit_bonus_suit='Hearts',
            suit_bonus_value=3,
            owner_user_id=defender.user_id,
        )
        db_session.add(land)
        db_session.flush()
        game.land_id = land.id

    attacker_fig = _add_figure(
        db_session,
        attacker,
        family_name='Attack Village',
        field='village',
        suit='Hearts',
        card_values=[(4, CardRole.KEY)],
    )
    defender_fig = _add_figure(
        db_session,
        defender,
        family_name='Defence Village',
        field='village',
        suit='Spades',
        card_values=[(4, CardRole.KEY)],
    )

    game.invader_player_id = attacker.id
    game.advancing_player_id = attacker.id
    game.advancing_figure_id = attacker_fig.id
    game.defending_figure_id = defender_fig.id
    db_session.commit()
    return game, attacker, defender, attacker_fig, defender_fig


def test_conquer_tactics_total_diff_counts_block_and_double_dagger(db):
    game, attacker, defender, _attacker_fig, _defender_fig = _setup_tactics_battle(db.session)

    _add_tactic(db.session, game, attacker, family_name='Dagger', rank='10', value=10, played_round=0)
    _add_tactic(db.session, game, defender, family_name='Block', rank='Q', value=2, played_round=0)
    _add_tactic(
        db.session,
        game,
        attacker,
        family_name='Double Dagger',
        rank='7',
        secondary_rank='8',
        value=7,
        played_round=1,
    )
    _add_tactic(db.session, game, defender, family_name='Dagger', rank='7', value=7, played_round=1)
    _add_tactic(db.session, game, attacker, family_name='Dagger', rank='9', value=9,
                played_round=2, status='discarded')
    db.session.commit()

    total, breakdown = _compute_server_total_diff(game, return_breakdown=True)

    assert total == 8
    assert breakdown['fig_diff'] == 0
    assert breakdown['round_diff'] == 8


def test_conquer_tactics_total_diff_counts_call_figure_support_and_land_bonus(db):
    game, attacker, defender, _attacker_fig, _defender_fig = _setup_tactics_battle(
        db.session,
        land_bonus=True,
    )
    call_figure = _add_figure(
        db.session,
        attacker,
        family_name='Called Farm',
        field='village',
        suit='Hearts',
        card_values=[(8, CardRole.NUMBER)],
    )
    _add_figure(
        db.session,
        attacker,
        family_name='Support King',
        field='castle',
        suit='Hearts',
    )
    _add_tactic(
        db.session,
        game,
        attacker,
        family_name='Call Villager',
        rank='J',
        suit='Hearts',
        value=1,
        played_round=0,
        call_figure_id=call_figure.id,
    )
    _add_tactic(db.session, game, defender, family_name='Dagger', rank='7', suit='Spades',
                value=7, played_round=0)
    db.session.commit()

    total, breakdown = _compute_server_total_diff(game, return_breakdown=True)

    assert breakdown['adv_power'] == 11
    assert breakdown['def_power'] == 4
    assert breakdown['fig_diff'] == 7
    assert breakdown['round_diff'] == 2
    assert total == 9


def test_conquer_tactics_cleanup_returns_only_unplayed_runtime_cards(db):
    game, attacker, _defender, _attacker_fig, _defender_fig = _setup_tactics_battle(db.session)
    played_tactic, played_card, _played_b = _add_tactic(
        db.session,
        game,
        attacker,
        family_name='Dagger',
        rank='10',
        value=10,
        played_round=0,
        status='played',
    )
    unplayed_tactic, unplayed_card, _unplayed_b = _add_tactic(
        db.session,
        game,
        attacker,
        family_name='Dagger',
        rank='7',
        value=7,
        played_round=None,
        status='available',
    )
    db.session.commit()

    _return_unplayed_battle_move_cards(game.id)
    db.session.flush()

    assert db.session.get(ConquerTactic, unplayed_tactic.id) is None
    db.session.refresh(unplayed_card)
    assert unplayed_card.part_of_battle_move is False
    assert unplayed_card.in_deck is False

    db.session.refresh(played_tactic)
    db.session.refresh(played_card)
    assert played_tactic.status == 'played'
    assert played_card.part_of_battle_move is True

    cards, tactics = _collect_battle_move_cards(game.id)
    assert [card.id for card, _card_type in cards] == [played_card.id]
    assert [tactic.id for tactic in tactics] == [played_tactic.id]

    _delete_all_battle_moves(game.id)
    db.session.flush()
    assert ConquerTactic.query.filter_by(game_id=game.id).count() == 0
