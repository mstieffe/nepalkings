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
    ('mode', 'land_bonus', 'expected_total', 'expected_adv', 'expected_def'),
    [
        # Duel: no land — Temple zeroes the advancing figure's King support.
        ('duel', False, 6, 10, 4),
        # Conquer: the advancing Hearts figure's King support is still blocked,
        # but the land's Hearts +3 bonus is UNBLOCKABLE and survives on it.
        # (Asymmetry disabled below so the invader gets the full land bonus.)
        ('conquer', True, 9, 13, 4),
    ],
)
def test_active_battle_temple_blocks_support_not_land(
        db, monkeypatch, mode, land_bonus,
        expected_total, expected_adv, expected_def):
    import routes.games as games_routes
    # Force symmetric land bonus so the unblockable land component is the full
    # value regardless of the deployed home-ground config.
    monkeypatch.setattr(games_routes.settings,
                        'LAND_HOME_GROUND_ASYMMETRY_ENABLED', False)

    game = _setup_temple_battle(db.session, mode=mode, land_bonus=land_bonus)

    total_diff, breakdown = _compute_server_total_diff(game, return_breakdown=True)

    assert breakdown['adv_power'] == expected_adv
    assert breakdown['def_power'] == expected_def
    assert total_diff == expected_total


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


# Suit X blocks the suit _SUIT_ADVANTAGE[X]; invert to find which Temple suit
# blocks a given defender suit.  Temple families: black (Himalaya) = Spades /
# Clubs, red (Djungle) = Hearts / Diamonds.
_ADVANTAGE = {'Spades': 'Hearts', 'Hearts': 'Clubs',
              'Clubs': 'Diamonds', 'Diamonds': 'Spades'}
_BLOCKER_SUIT = {blocked: blocker for blocker, blocked in _ADVANTAGE.items()}
_TEMPLE_FAMILY_BY_SUIT = {
    'Spades': 'Himalaya Temple', 'Clubs': 'Himalaya Temple',
    'Hearts': 'Djungle Temple', 'Diamonds': 'Djungle Temple',
}


def _setup_conquer_land_defence(db_session, *, land_suit='Spades',
                                land_value=20, defender_suit=None,
                                with_attacker_temple=True,
                                with_defender_king=True):
    """Conquer battle where the DEFENDER holds a land.  The defending figure
    (suit *defender_suit*, default the land suit) optionally has a same-suit
    King for blockable support, and the invader optionally brings a Temple
    that has suit advantage over the defending figure."""
    defender_suit = defender_suit or land_suit
    game = Game(mode='conquer', state='open')
    db_session.add(game)
    db_session.flush()

    _, attacker = _add_player(db_session, game, 'attacker_land')
    defender_user, defender = _add_player(db_session, game, 'defender_land')

    land = Land(
        col=301, row=401, tier=6, gold_rate=50.0,
        suit_bonus_suit=land_suit, suit_bonus_value=land_value,
        owner_user_id=defender_user.id,
    )
    db_session.add(land)
    db_session.flush()
    game.land_id = land.id

    # Invader's advancing figure — off-suit so it never earns the land bonus.
    attacker_figure = _add_figure(
        db_session, attacker, family_name='Gorkha Warriors', field='military',
        color='offensive', suit='Hearts', card_values=[(10, CardRole.NUMBER)])
    if with_attacker_temple:
        temple_suit = _BLOCKER_SUIT[defender_suit]
        _add_figure(
            db_session, attacker,
            family_name=_TEMPLE_FAMILY_BY_SUIT[temple_suit], field='village',
            color='offensive', suit=temple_suit,
            card_values=[(2, CardRole.KEY), (2, CardRole.KEY)])

    # Defender's defending figure earns the land bonus only when its suit
    # matches the land; the same-suit King provides blockable castle support.
    defender_figure = _add_figure(
        db_session, defender, family_name='Gorkha Warriors', field='military',
        color='offensive', suit=defender_suit,
        card_values=[(10, CardRole.NUMBER)])
    if with_defender_king:
        _add_figure(
            db_session, defender, family_name='Djungle King', field='castle',
            color='offensive', suit=defender_suit)

    game.advancing_player_id = attacker.id
    game.invader_player_id = attacker.id
    game.advancing_figure_id = attacker_figure.id
    game.defending_figure_id = defender_figure.id
    db_session.commit()
    return game


def test_temple_does_not_block_defender_land_bonus(db, monkeypatch):
    """A Temple zeroes the defender's King support but NOT the land's suit
    bonus — the core high-tier-land balance fix."""
    import routes.games as games_routes
    monkeypatch.setattr(games_routes.settings,
                        'LAND_HOME_GROUND_ASYMMETRY_ENABLED', False)

    game = _setup_conquer_land_defence(
        db.session, land_suit='Spades', land_value=20)

    total_diff, breakdown = _compute_server_total_diff(game, return_breakdown=True)

    # Defender: base 10 + King support 4 (BLOCKED → 0) + land 20 (survives) = 30
    assert breakdown['def_power'] == 30
    # Invader: off-suit base 10, no support, no land bonus
    assert breakdown['adv_power'] == 10
    assert total_diff == -20


def test_temple_still_blocks_defender_support_without_land(db, monkeypatch):
    """Sanity check: with no matching land bonus, the Temple block still
    removes the defender's King support entirely."""
    import routes.games as games_routes
    monkeypatch.setattr(games_routes.settings,
                        'LAND_HOME_GROUND_ASYMMETRY_ENABLED', False)

    # Defender figure is Spades and the invader's figure is Hearts, but the
    # land is Clubs → neither earns a land bonus, so the Temple's block on the
    # defender's King support leaves it bare.
    game = _setup_conquer_land_defence(
        db.session, land_suit='Clubs', land_value=20, defender_suit='Spades')

    total_diff, breakdown = _compute_server_total_diff(game, return_breakdown=True)

    # Defender: base 10 + King support 4 (blocked → 0) + land 0 = 10
    assert breakdown['def_power'] == 10
    assert breakdown['adv_power'] == 10
    assert total_diff == 0


def _setup_symmetric_land_battle(db_session, *, land_suit='Hearts',
                                 land_value=10):
    """Conquer battle with both battle figures matching the land suit and no
    support/temples, isolating the land bonus for asymmetry assertions."""
    game = Game(mode='conquer', state='open')
    db_session.add(game)
    db_session.flush()

    _, attacker = _add_player(db_session, game, 'attacker_sym')
    defender_user, defender = _add_player(db_session, game, 'defender_sym')

    land = Land(
        col=302, row=402, tier=5, gold_rate=45.0,
        suit_bonus_suit=land_suit, suit_bonus_value=land_value,
        owner_user_id=defender_user.id,
    )
    db_session.add(land)
    db_session.flush()
    game.land_id = land.id

    attacker_figure = _add_figure(
        db_session, attacker, family_name='Gorkha Warriors', field='military',
        color='offensive', suit=land_suit, card_values=[(10, CardRole.NUMBER)])
    defender_figure = _add_figure(
        db_session, defender, family_name='Gorkha Warriors', field='military',
        color='offensive', suit=land_suit, card_values=[(10, CardRole.NUMBER)])

    game.advancing_player_id = attacker.id
    game.invader_player_id = attacker.id
    game.advancing_figure_id = attacker_figure.id
    game.defending_figure_id = defender_figure.id
    db_session.commit()
    return game


@pytest.mark.parametrize(
    ('enabled', 'factor', 'expected_adv', 'expected_def', 'expected_total'),
    [
        (True, 0.5, 15, 20, -5),    # invader gets half the +10 land bonus
        (True, 0.0, 10, 20, -10),   # invader gets no land bonus
        (True, 1.0, 20, 20, 0),     # factor 1.0 → effectively symmetric
        (False, 0.5, 20, 20, 0),    # disabled → symmetric, factor ignored
    ],
)
def test_home_ground_asymmetry_scales_attacker_land_bonus(
        db, monkeypatch, enabled, factor,
        expected_adv, expected_def, expected_total):
    import routes.games as games_routes
    monkeypatch.setattr(games_routes.settings,
                        'LAND_HOME_GROUND_ASYMMETRY_ENABLED', enabled)
    monkeypatch.setattr(games_routes.settings,
                        'LAND_HOME_GROUND_ATTACKER_BONUS_FACTOR', factor)

    game = _setup_symmetric_land_battle(
        db.session, land_suit='Hearts', land_value=10)

    total_diff, breakdown = _compute_server_total_diff(game, return_breakdown=True)

    assert breakdown['adv_power'] == expected_adv
    assert breakdown['def_power'] == expected_def
    assert total_diff == expected_total
