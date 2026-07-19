# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Characterization tests for finished-Conquer result serialization."""

import importlib
import inspect
from types import SimpleNamespace

import pytest


games = importlib.import_module('routes.games')

ATTACKER_PLAYER_ID = 11
DEFENDER_PLAYER_ID = 22
ATTACKER_USER_ID = 101
DEFENDER_USER_ID = 202


def _fake_finished_game(*, last_result=None, winner='attacker'):
    attacker = SimpleNamespace(id=ATTACKER_PLAYER_ID, user_id=ATTACKER_USER_ID)
    defender = SimpleNamespace(id=DEFENDER_PLAYER_ID, user_id=DEFENDER_USER_ID)
    winner_player_id = {
        'attacker': attacker.id,
        'defender': defender.id,
        'draw': None,
    }[winner]
    game = SimpleNamespace(
        mode='conquer',
        state='finished',
        land_id=None,
        invader_player_id=attacker.id,
        winner_player_id=winner_player_id,
        last_battle_result=last_result,
        players=[attacker, defender],
        victory_reviewed_at=None,
        serialize=lambda: {'source': 'game.serialize'},
    )
    return game, attacker, defender


def _patch_route_dependencies(
    monkeypatch,
    attacker,
    defender,
    *,
    serialized_game=None,
    onboarding=None,
):
    serialized_game = serialized_game or {'source': 'viewer serializer'}
    monkeypatch.setattr(games, '_conquer_attacker_player', lambda _game: attacker)
    monkeypatch.setattr(
        games,
        '_conquer_original_defender_player',
        lambda _game: defender,
    )
    monkeypatch.setattr(
        games,
        'serialize_game_for_viewer',
        lambda _game, _viewer_user_id: serialized_game,
    )
    monkeypatch.setattr(
        games,
        '_serialize_viewer_onboarding',
        lambda _viewer_user_id: onboarding,
    )


def test_finished_conquer_result_route_api_is_stable():
    helper = games._serialize_finished_conquer_result

    assert str(inspect.signature(helper)) == '(game, viewer_user_id=None)'
    assert helper.__module__ == 'routes.games'


@pytest.mark.parametrize(
    'game',
    [
        None,
        SimpleNamespace(mode='duel', state='finished'),
        SimpleNamespace(mode='conquer', state='open'),
    ],
)
def test_finished_conquer_result_rejects_ineligible_games_before_context_access(game):
    assert games._serialize_finished_conquer_result(game) is None


def test_finished_conquer_result_is_safe_outside_request_context(monkeypatch):
    game, attacker, defender = _fake_finished_game()
    _patch_route_dependencies(monkeypatch, attacker, defender)

    payload = games._serialize_finished_conquer_result(game)

    assert payload['game'] == {'source': 'game.serialize'}
    assert payload['conquer_result'] == 'attacker_won'
    assert payload['attacker_won'] is True
    assert payload['winner_player_id'] == attacker.id
    assert payload['loser_player_id'] == defender.id
    assert 'onboarding' not in payload


def test_finished_conquer_result_uses_request_viewer_and_route_hooks(
    app,
    monkeypatch,
):
    game, attacker, defender = _fake_finished_game(
        last_result={
            'battle_score_diff': '6',
            'battle_score_player_id': ATTACKER_PLAYER_ID,
        }
    )
    serialized_calls = []
    onboarding_calls = []
    monkeypatch.setattr(games, '_conquer_attacker_player', lambda _game: attacker)
    monkeypatch.setattr(
        games,
        '_conquer_original_defender_player',
        lambda _game: defender,
    )
    monkeypatch.setattr(
        games,
        'serialize_game_for_viewer',
        lambda _game, viewer_user_id: (
            serialized_calls.append(viewer_user_id)
            or {'viewer_user_id': viewer_user_id}
        ),
    )
    monkeypatch.setattr(
        games,
        '_serialize_viewer_onboarding',
        lambda viewer_user_id: (
            onboarding_calls.append(viewer_user_id)
            or {'viewer_user_id': viewer_user_id}
        ),
    )

    with app.test_request_context('/'):
        games.g.user_id = defender.user_id
        payload = games._serialize_finished_conquer_result(game)

    assert serialized_calls == [defender.user_id]
    assert onboarding_calls == [defender.user_id]
    assert payload['game'] == {'viewer_user_id': defender.user_id}
    assert payload['onboarding'] == {'viewer_user_id': defender.user_id}
    assert payload['battle_score_diff'] == 6
    assert payload['total_diff'] == -6
    assert payload['battle_total_diff'] == -6


def test_explicit_finished_result_viewer_overrides_request_context(
    app,
    monkeypatch,
):
    game, attacker, defender = _fake_finished_game()
    seen_viewers = []
    _patch_route_dependencies(monkeypatch, attacker, defender)
    monkeypatch.setattr(
        games,
        'serialize_game_for_viewer',
        lambda _game, viewer_user_id: (
            seen_viewers.append(viewer_user_id)
            or {'viewer_user_id': viewer_user_id}
        ),
    )

    with app.test_request_context('/'):
        games.g.user_id = defender.user_id
        payload = games._serialize_finished_conquer_result(
            game,
            viewer_user_id=attacker.user_id,
        )

    assert seen_viewers == [attacker.user_id]
    assert payload['game'] == {'viewer_user_id': attacker.user_id}


@pytest.mark.parametrize(
    ('viewer', 'expected_total'),
    [
        (101, 6),
        ('202', -6),
    ],
)
def test_finished_result_orients_canonical_score_for_each_viewer(
    monkeypatch,
    viewer,
    expected_total,
):
    game, attacker, defender = _fake_finished_game(
        last_result={
            'fig_diff': 4,
            'round_diff': 2,
            'battle_score_diff': '6',
            'battle_score_player_id': str(ATTACKER_PLAYER_ID),
        }
    )
    _patch_route_dependencies(monkeypatch, attacker, defender)

    payload = games._serialize_finished_conquer_result(
        game,
        viewer_user_id=viewer,
    )

    assert payload['battle_score_diff'] == 6
    assert payload['battle_score_player_id'] == str(attacker.id)
    assert payload['total_diff'] == expected_total
    assert payload['battle_total_diff'] == expected_total


def test_finished_result_reconstructs_legacy_score_from_breakdown(monkeypatch):
    game, attacker, defender = _fake_finished_game(
        last_result={'fig_diff': '4', 'round_diff': '-1'}
    )
    _patch_route_dependencies(monkeypatch, attacker, defender)

    payload = games._serialize_finished_conquer_result(
        game,
        viewer_user_id=attacker.user_id,
    )

    assert payload['fig_diff'] == '4'
    assert payload['round_diff'] == '-1'
    assert payload['battle_score_player_id'] == attacker.id
    assert payload['battle_score_diff'] == 3
    assert payload['total_diff'] == 3
    assert payload['battle_total_diff'] == 3


def test_finished_result_keeps_legacy_perspective_when_score_is_malformed(
    monkeypatch,
):
    game, attacker, defender = _fake_finished_game(
        last_result={'fig_diff': 'invalid', 'round_diff': 2}
    )
    _patch_route_dependencies(monkeypatch, attacker, defender)

    payload = games._serialize_finished_conquer_result(
        game,
        viewer_user_id=attacker.user_id,
    )

    assert payload['battle_score_player_id'] == attacker.id
    assert 'battle_score_diff' not in payload
    assert 'total_diff' not in payload
    assert 'battle_total_diff' not in payload


def test_finished_result_projects_cached_battle_metadata(monkeypatch):
    game, attacker, defender = _fake_finished_game(
        last_result={
            'conquer_resolved': True,
            'fig_diff': 5,
            'round_diff': -2,
            'adv_power': 9,
            'def_power': 4,
            'battle_score_diff': 3,
            'battle_score_player_id': ATTACKER_PLAYER_ID,
            'card_won_suit': 'Spades',
            'card_won_rank': 'A',
            'card_lost_suit': 'Hearts',
            'card_lost_rank': 'K',
            'cards_spent': 0,
            'conquer_consumed_cards': None,
            'defence_consumed_cards': [{'suit': 'Clubs', 'rank': 'Q'}],
            'conquer_loot_lost_cards': None,
            'conquer_loot_gained_cards': [{'suit': 'Spades', 'rank': 'A'}],
            'kingdom_split_transfer': {'transferred_land_ids': [7, 8]},
            'is_ai_defender': 0,
            'conquer_attacker_player_id': ATTACKER_PLAYER_ID,
            'conquer_defender_player_id': DEFENDER_PLAYER_ID,
            'conquer_attacker_user_id': None,
            'conquer_defender_user_id': DEFENDER_USER_ID,
            'auto_loss_reason': 'withdraw',
            'auto_loss_detail': 'manual',
        }
    )
    _patch_route_dependencies(monkeypatch, attacker, defender)

    payload = games._serialize_finished_conquer_result(
        game,
        viewer_user_id=attacker.user_id,
    )

    assert payload == {
        'success': True,
        'message': 'Conquer battle already resolved: attacker_won',
        'already_resolved': True,
        'conquer_result': 'attacker_won',
        'attacker_won': True,
        'land_id': None,
        'land_gold_rate': 0,
        'land_tier': None,
        'game': {'source': 'viewer serializer'},
        'fig_diff': 5,
        'round_diff': -2,
        'adv_power': 9,
        'def_power': 4,
        'battle_score_player_id': attacker.id,
        'battle_score_diff': 3,
        'total_diff': 3,
        'battle_total_diff': 3,
        'card_won_suit': 'Spades',
        'card_won_rank': 'A',
        'card_lost_suit': 'Hearts',
        'card_lost_rank': 'K',
        'cards_spent': 0,
        'consumed_cards': [],
        'defence_consumed_cards': [{'suit': 'Clubs', 'rank': 'Q'}],
        'loot_lost_cards': [],
        'loot_gained_cards': [{'suit': 'Spades', 'rank': 'A'}],
        'kingdom_split_transfer': {'transferred_land_ids': [7, 8]},
        'is_ai_defender': False,
        'conquer_attacker_player_id': attacker.id,
        'conquer_defender_player_id': defender.id,
        'conquer_attacker_user_id': None,
        'conquer_defender_user_id': defender.user_id,
        'auto_loss_reason': 'withdraw',
        'auto_loss_detail': 'manual',
        'victory_review_available': False,
        'victory_review_config_id': None,
        'victory_review_land_id': None,
        'outcome': 'win',
        'winner_player_id': attacker.id,
        'loser_player_id': defender.id,
    }


def test_finished_result_uses_latest_attack_log_for_legacy_rows(
    db,
    two_users,
    monkeypatch,
):
    from models import Game, Land, LandAttackLog, Player

    attacker_user, defender_user = two_users
    land = Land(
        col=50,
        row=60,
        tier=3,
        gold_rate=7.5,
        suit_bonus_suit='Diamonds',
        suit_bonus_value=4,
        owner_user_id=defender_user.id,
    )
    game = Game(mode='conquer', state='finished', land=land)
    db.session.add_all([land, game])
    db.session.flush()
    attacker = Player(
        user_id=attacker_user.id,
        game_id=game.id,
        turns_left=0,
        points=0,
    )
    defender = Player(
        user_id=defender_user.id,
        game_id=game.id,
        turns_left=0,
        points=0,
    )
    db.session.add_all([attacker, defender])
    db.session.flush()
    game.invader_player_id = attacker.id
    game.winner_player_id = defender.id
    game.last_battle_result = {}
    db.session.add_all([
        LandAttackLog(
            land_id=land.id,
            attacker_user_id=attacker_user.id,
            defender_user_id=defender_user.id,
            result='defender_won',
            card_lost_suit='Clubs',
            card_lost_rank='Q',
        ),
        LandAttackLog(
            land_id=land.id,
            attacker_user_id=attacker_user.id,
            defender_user_id=defender_user.id,
            result='defender_won',
            card_lost_suit='Spades',
            card_lost_rank='A',
        ),
    ])
    db.session.commit()
    _patch_route_dependencies(monkeypatch, attacker, defender)

    payload = games._serialize_finished_conquer_result(
        game,
        viewer_user_id=attacker_user.id,
    )

    assert payload['land_gold_rate'] == 7.5
    assert payload['land_tier'] == 3
    assert payload['card_lost_suit'] == 'Spades'
    assert payload['card_lost_rank'] == 'A'
    assert payload['conquer_result'] == 'defender_won'
    assert payload['winner_player_id'] == defender.id
    assert payload['loser_player_id'] == attacker.id
