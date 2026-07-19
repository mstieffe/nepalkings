# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Characterization tests for post-battle cleanup route helpers."""

import importlib
import inspect
from types import SimpleNamespace


games = importlib.import_module('routes.games')


def _make_game_with_player(db, two_users):
    from models import Game, Player

    user, _ = two_users
    game = Game(current_round=4, stake=35, mode='duel')
    db.session.add(game)
    db.session.flush()
    player = Player(
        user_id=user.id,
        game_id=game.id,
        turns_left=2,
        points=0,
    )
    db.session.add(player)
    db.session.commit()
    return game, player


def _make_figure(db, game, player, *, name, rests):
    from models import Figure

    figure = Figure(
        player_id=player.id,
        game_id=game.id,
        family_name='Villager',
        field='village',
        color='red',
        name=name,
        suit='Hearts',
        rest_after_attack=rests,
    )
    db.session.add(figure)
    db.session.flush()
    return figure


def test_battle_cleanup_route_api_is_stable():
    expected_signatures = {
        '_destroy_figure_and_collect_cards': '(figure)',
        '_clear_battle_state': '(game)',
        '_collect_resting_figure_ids': '(game)',
        '_deactivate_all_spells': '(game)',
    }

    for name, expected_signature in expected_signatures.items():
        helper = getattr(games, name)
        assert str(inspect.signature(helper)) == expected_signature
        assert helper.__module__ == 'routes.games'


def test_clear_battle_state_resets_only_battle_fields():
    initial = {
        'advancing_figure_id': 1,
        'advancing_figure_id_2': 2,
        'advancing_player_id': 3,
        'defending_figure_id': 4,
        'defending_figure_id_2': 5,
        'battle_modifier': [{'type': 'Peasant War'}],
        'battle_confirmed': True,
        'battle_decisions': {'3': 'battle'},
        'battle_moves_confirmed': {'3': True},
        'fold_outcome': 'fold_win',
        'fold_winner_id': 3,
        'auto_loss_reason': 'resource_deficit',
        'auto_loss_detail': 'General',
        'battle_round': 2,
        'battle_turn_player_id': 4,
        'battle_skipped_rounds': {'3': [1]},
        'battle_gamble_counts': {'3': 2},
        'battle_gamble_previews': {'3': {'tactic_id': 8}},
        'current_round': 9,
        'last_battle_result': {'winner_player_id': 3},
    }
    game = SimpleNamespace(**initial)

    result = games._clear_battle_state(game)

    assert result is None
    assert vars(game) == {
        'advancing_figure_id': None,
        'advancing_figure_id_2': None,
        'advancing_player_id': None,
        'defending_figure_id': None,
        'defending_figure_id_2': None,
        'battle_modifier': [],
        'battle_confirmed': False,
        'battle_decisions': None,
        'battle_moves_confirmed': None,
        'fold_outcome': None,
        'fold_winner_id': None,
        'auto_loss_reason': None,
        'auto_loss_detail': None,
        'battle_round': 0,
        'battle_turn_player_id': None,
        'battle_skipped_rounds': None,
        'battle_gamble_counts': None,
        'battle_gamble_previews': None,
        'current_round': 9,
        'last_battle_result': {'winner_player_id': 3},
    }


def test_collect_resting_figure_ids_preserves_slot_order_and_duplicates(
    db,
    two_users,
):
    game, player = _make_game_with_player(db, two_users)
    resting = _make_figure(
        db,
        game,
        player,
        name='Resting General',
        rests=True,
    )
    active = _make_figure(
        db,
        game,
        player,
        name='Active General',
        rests=False,
    )
    db.session.commit()
    battle = SimpleNamespace(
        advancing_figure_id=resting.id,
        advancing_figure_id_2=active.id,
        defending_figure_id=resting.id,
        defending_figure_id_2=None,
    )

    assert games._collect_resting_figure_ids(battle) == [resting.id, resting.id]


def test_collect_resting_figure_ids_returns_none_without_resting_figures(
    db,
    two_users,
):
    game, player = _make_game_with_player(db, two_users)
    active = _make_figure(
        db,
        game,
        player,
        name='Active General',
        rests=False,
    )
    db.session.commit()
    battle = SimpleNamespace(
        advancing_figure_id=active.id,
        advancing_figure_id_2=None,
        defending_figure_id=None,
        defending_figure_id_2=None,
    )

    assert games._collect_resting_figure_ids(battle) is None


def test_deactivate_all_spells_only_changes_active_spells_for_game(db, two_users):
    from models import ActiveSpell, Game

    game, player = _make_game_with_player(db, two_users)
    other_game = Game(current_round=1, stake=35, mode='duel')
    db.session.add(other_game)
    db.session.flush()

    def make_spell(target_game, name, is_active):
        spell = ActiveSpell(
            game_id=target_game.id,
            player_id=player.id,
            spell_name=name,
            spell_type='tactics',
            spell_family_name=name,
            suit='Hearts',
            cast_round=1,
            duration=1,
            is_active=is_active,
        )
        db.session.add(spell)
        return spell

    active = make_spell(game, 'Active', True)
    already_inactive = make_spell(game, 'Inactive', False)
    other_active = make_spell(other_game, 'Other game', True)
    db.session.commit()

    result = games._deactivate_all_spells(game)
    db.session.flush()

    assert result is None
    assert active.is_active is False
    assert already_inactive.is_active is False
    assert other_active.is_active is True


def test_destroy_figure_detaches_and_returns_main_and_side_cards(db, two_users):
    from models import (
        CardRole,
        CardToFigure,
        MainCard,
        MainRank,
        SideCard,
        SideRank,
        Suit,
    )

    game, player = _make_game_with_player(db, two_users)
    figure = _make_figure(
        db,
        game,
        player,
        name='Doomed General',
        rests=False,
    )
    main_card = MainCard(
        game_id=game.id,
        player_id=player.id,
        suit=Suit.HEARTS,
        rank=MainRank.KING,
        value=4,
        in_deck=False,
        part_of_figure=True,
        part_of_battle_move=False,
    )
    side_card = SideCard(
        game_id=game.id,
        player_id=player.id,
        suit=Suit.CLUBS,
        rank=SideRank.TWO,
        value=2,
        in_deck=False,
        part_of_figure=True,
        part_of_battle_move=False,
    )
    db.session.add_all([main_card, side_card])
    db.session.flush()
    associations = [
        CardToFigure(
            figure_id=figure.id,
            card_id=main_card.id,
            card_type='main',
            role=CardRole.KEY,
        ),
        CardToFigure(
            figure_id=figure.id,
            card_id=side_card.id,
            card_type='side',
            role=CardRole.NUMBER,
        ),
    ]
    db.session.add_all(associations)
    db.session.commit()
    figure_id = figure.id

    cards = games._destroy_figure_and_collect_cards(figure)
    db.session.flush()

    assert [(card.id, card_type) for card, card_type in cards] == [
        (main_card.id, 'main'),
        (side_card.id, 'side'),
    ]
    assert db.session.get(type(figure), figure_id) is None
    assert CardToFigure.query.filter_by(figure_id=figure_id).count() == 0
    assert main_card.player_id is None
    assert main_card.part_of_figure is False
    assert main_card.in_deck is False
    assert side_card.player_id is None
    assert side_card.part_of_figure is False
    assert side_card.in_deck is False
