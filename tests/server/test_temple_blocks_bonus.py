# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Regression tests for Temple bonus-block battle resolution."""

import pytest
from werkzeug.security import generate_password_hash

from models import (
    CardRole,
    CardToFigure,
    Figure,
    Game,
    Land,
    MainCard,
    MainRank,
    Player,
    Suit,
    User,
)
from routes.games import _compute_server_total_diff


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
    return user, player


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


def _setup_temple_battle(db_session, *, mode='duel', land_bonus=False):
    game = Game(mode=mode, state='open')
    db_session.add(game)
    db_session.flush()

    _, attacker = _add_player(db_session, game, f'attacker_{mode}')
    defender_user, defender = _add_player(db_session, game, f'defender_{mode}')

    if land_bonus:
        land = Land(
            col=101 if mode == 'conquer' else 100,
            row=201 if mode == 'conquer' else 200,
            tier=1,
            gold_rate=1.0,
            suit_bonus_suit='Hearts',
            suit_bonus_value=3,
            owner_user_id=defender_user.id,
        )
        db_session.add(land)
        db_session.flush()
        game.land_id = land.id

    attacker_figure = _add_figure(
        db_session,
        attacker,
        family_name='Gorkha Warriors',
        field='military',
        color='offensive',
        suit='Hearts',
        card_values=[(10, CardRole.NUMBER)],
    )
    _add_figure(
        db_session,
        attacker,
        family_name='Djungle King',
        field='castle',
        color='offensive',
        suit='Hearts',
    )
    defending_temple = _add_figure(
        db_session,
        defender,
        family_name='Himalaya Temple',
        field='village',
        color='defensive',
        suit='Spades',
        card_values=[(2, CardRole.KEY), (2, CardRole.KEY)],
    )

    game.advancing_player_id = attacker.id
    game.invader_player_id = attacker.id
    game.advancing_figure_id = attacker_figure.id
    game.defending_figure_id = defending_temple.id
    db_session.commit()
    return game


@pytest.mark.parametrize(
    ('mode', 'land_bonus'),
    [
        ('duel', False),
        ('conquer', True),
    ],
)
def test_active_battle_temple_blocks_support_bonus(db, mode, land_bonus):
    game = _setup_temple_battle(db.session, mode=mode, land_bonus=land_bonus)

    total_diff, breakdown = _compute_server_total_diff(game, return_breakdown=True)

    assert total_diff == 6
    assert breakdown['adv_power'] == 10
    assert breakdown['def_power'] == 4


def test_upgraded_manufactory_does_not_block_support_bonus(db):
    game = Game(mode='duel', state='open')
    db.session.add(game)
    db.session.flush()

    _, attacker = _add_player(db.session, game, 'attacker_manufactory')
    _, defender = _add_player(db.session, game, 'defender_manufactory')

    attacker_figure = _add_figure(
        db.session,
        attacker,
        family_name='Gorkha Warriors',
        field='military',
        color='offensive',
        suit='Hearts',
        card_values=[(10, CardRole.NUMBER)],
    )
    _add_figure(
        db.session,
        attacker,
        family_name='Djungle King',
        field='castle',
        color='offensive',
        suit='Hearts',
    )
    defender_figure = _add_figure(
        db.session,
        defender,
        family_name='Rice Farmer',
        field='village',
        color='offensive',
        suit='Clubs',
        card_values=[(4, CardRole.KEY)],
    )
    _add_figure(
        db.session,
        defender,
        family_name='Shield Manufactory',
        field='village',
        color='defensive',
        suit='Spades',
        card_values=[(2, CardRole.KEY), (2, CardRole.KEY), (7, CardRole.NUMBER)],
    )

    game.advancing_player_id = attacker.id
    game.invader_player_id = attacker.id
    game.advancing_figure_id = attacker_figure.id
    game.defending_figure_id = defender_figure.id
    db.session.commit()

    total_diff, breakdown = _compute_server_total_diff(game, return_breakdown=True)

    assert total_diff == 10
    assert breakdown['adv_power'] == 14
    assert breakdown['def_power'] == 4
