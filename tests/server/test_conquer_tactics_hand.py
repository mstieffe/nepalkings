# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Focused coverage for the conquer tactics-hand model."""

from models import (BattleMove, CollectionCard, ConquerTactic, Figure, Game,
                    MainCard, Player)

from tests.server.test_land_battle import (
    _auth_headers,
    _make_conquer_config,
    _make_defence_config,
    _make_land,
    _make_user,
)


def _start_player_owned_conquer(app, db):
    attacker = _make_user(db, username='tactic_attacker')
    defender = _make_user(db, username='tactic_defender')
    land = _make_land(db, tier=1, owner_user_id=defender.id)
    _make_conquer_config(db, attacker, land)
    _make_defence_config(db, defender, land)

    client = app.test_client()
    resp = client.post(
        '/kingdom/conquer/start_battle',
        json={'land_id': land.id},
        headers=_auth_headers(app, attacker),
    )
    assert resp.status_code == 200, resp.get_json()
    game = db.session.get(Game, resp.get_json()['game_id'])
    attacker_player = db.session.get(Player, game.invader_player_id)
    defender_player = next(p for p in game.players if p.id != attacker_player.id)
    return client, attacker, defender, game, attacker_player, defender_player


def _force_active_battle(db, game, attacker_player, defender_player):
    attacker_fig = Figure.query.filter_by(
        game_id=game.id, player_id=attacker_player.id).first()
    defender_fig = Figure.query.filter_by(
        game_id=game.id, player_id=defender_player.id).first()
    game.advancing_player_id = attacker_player.id
    game.advancing_figure_id = attacker_fig.id
    game.defending_figure_id = defender_fig.id
    game.battle_confirmed = True
    game.battle_round = 0
    game.battle_turn_player_id = attacker_player.id
    db.session.commit()


def test_start_conquer_battle_creates_conquer_tactics_not_battle_moves(app, db):
    _client, _attacker, _defender, game, attacker_player, defender_player = (
        _start_player_owned_conquer(app, db)
    )

    assert game.conquer_move_model == 'tactics_hand'
    assert BattleMove.query.filter_by(game_id=game.id).count() == 0

    attacker_tactics = ConquerTactic.query.filter_by(
        game_id=game.id, player_id=attacker_player.id).order_by(ConquerTactic.sort_order).all()
    defender_tactics = ConquerTactic.query.filter_by(
        game_id=game.id, player_id=defender_player.id).all()

    assert len(attacker_tactics) == 3
    assert len(defender_tactics) == 1
    assert {t.source for t in attacker_tactics + defender_tactics} == {'config'}
    assert {t.status for t in attacker_tactics + defender_tactics} == {'available'}

    card = db.session.get(MainCard, attacker_tactics[0].card_id)
    assert card is not None
    assert card.part_of_battle_move is True
    assert card.player_id == attacker_player.id


def test_get_battle_state_hides_opponent_unplayed_conquer_tactics(app, db):
    client, attacker, _defender, game, attacker_player, defender_player = (
        _start_player_owned_conquer(app, db)
    )

    resp = client.get(
        '/games/get_battle_state',
        query_string={'game_id': game.id, 'player_id': attacker_player.id},
        headers=_auth_headers(app, attacker),
    )
    assert resp.status_code == 200, resp.get_json()
    payload = resp.get_json()

    assert len(payload['player_tactics']) == 3
    assert payload['player_tactics'][0]['family_name'] == 'Dagger'
    assert len(payload['opponent_tactics']) == 1
    hidden = payload['opponent_tactics'][0]
    assert hidden['player_id'] == defender_player.id
    assert hidden['status'] == 'available'
    assert 'family_name' not in hidden
    assert 'value' not in hidden


def test_play_conquer_tactic_marks_played_and_advances_round(app, db):
    client, attacker, defender, game, attacker_player, defender_player = (
        _start_player_owned_conquer(app, db)
    )
    _force_active_battle(db, game, attacker_player, defender_player)

    attacker_tactic = ConquerTactic.query.filter_by(
        game_id=game.id, player_id=attacker_player.id, status='available').first()
    defender_tactic = ConquerTactic.query.filter_by(
        game_id=game.id, player_id=defender_player.id, status='available').first()

    first = client.post(
        '/games/play_conquer_tactic',
        json={
            'game_id': game.id,
            'player_id': attacker_player.id,
            'tactic_id': attacker_tactic.id,
        },
        headers=_auth_headers(app, attacker),
    )
    assert first.status_code == 200, first.get_json()
    db.session.refresh(game)
    db.session.refresh(attacker_tactic)
    assert attacker_tactic.status == 'played'
    assert attacker_tactic.played_round == 0
    assert game.battle_turn_player_id == defender_player.id

    second = client.post(
        '/games/play_conquer_tactic',
        json={
            'game_id': game.id,
            'player_id': defender_player.id,
            'tactic_id': defender_tactic.id,
        },
        headers=_auth_headers(app, defender),
    )
    assert second.status_code == 200, second.get_json()
    db.session.refresh(game)
    db.session.refresh(defender_tactic)
    assert defender_tactic.status == 'played'
    assert defender_tactic.played_round == 0
    assert game.battle_round == 1
    assert game.battle_turn_player_id == game.invader_player_id


def test_gamble_conquer_tactic_creates_replacements_without_collection_deletion(app, db):
    client, attacker, _defender, game, attacker_player, defender_player = (
        _start_player_owned_conquer(app, db)
    )
    _force_active_battle(db, game, attacker_player, defender_player)

    before_collection_count = CollectionCard.query.count()
    tactic = ConquerTactic.query.filter_by(
        game_id=game.id, player_id=attacker_player.id, status='available').first()

    resp = client.post(
        '/games/gamble_conquer_tactic',
        json={
            'game_id': game.id,
            'player_id': attacker_player.id,
            'tactic_id': tactic.id,
        },
        headers=_auth_headers(app, attacker),
    )
    assert resp.status_code == 200, resp.get_json()
    payload = resp.get_json()
    db.session.refresh(tactic)
    db.session.refresh(game)

    assert tactic.status == 'discarded'
    assert len(payload['new_tactics']) == 2
    new_ids = [t['id'] for t in payload['new_tactics']]
    new_tactics = ConquerTactic.query.filter(ConquerTactic.id.in_(new_ids)).all()
    assert {t.source for t in new_tactics} == {'gamble'}
    assert {t.status for t in new_tactics} == {'available'}
    assert CollectionCard.query.count() == before_collection_count
    assert game.battle_gamble_counts[str(attacker_player.id)]['count'] == 1


def test_gamble_conquer_tactic_enforces_round_and_battle_limits(app, db):
    client, attacker, _defender, game, attacker_player, defender_player = (
        _start_player_owned_conquer(app, db)
    )
    _force_active_battle(db, game, attacker_player, defender_player)

    tactic = ConquerTactic.query.filter_by(
        game_id=game.id, player_id=attacker_player.id, status='available').first()

    first = client.post(
        '/games/gamble_conquer_tactic',
        json={
            'game_id': game.id,
            'player_id': attacker_player.id,
            'tactic_id': tactic.id,
        },
        headers=_auth_headers(app, attacker),
    )
    assert first.status_code == 200, first.get_json()

    replacement_ids = [t['id'] for t in first.get_json()['new_tactics']]
    same_round = client.post(
        '/games/gamble_conquer_tactic',
        json={
            'game_id': game.id,
            'player_id': attacker_player.id,
            'tactic_id': replacement_ids[0],
        },
        headers=_auth_headers(app, attacker),
    )
    assert same_round.status_code == 400
    assert 'once per battle round' in same_round.get_json()['message'].lower()

    db.session.refresh(game)
    game.battle_round = 2
    game.battle_gamble_counts = {
        str(attacker_player.id): {'count': 3, 'rounds': [0, 1]}
    }
    db.session.commit()

    battle_limit = client.post(
        '/games/gamble_conquer_tactic',
        json={
            'game_id': game.id,
            'player_id': attacker_player.id,
            'tactic_id': replacement_ids[1],
        },
        headers=_auth_headers(app, attacker),
    )
    assert battle_limit.status_code == 400
    assert '3 times per battle' in battle_limit.get_json()['message'].lower()


def test_combine_and_dismantle_conquer_tactics_restore_sources(app, db):
    client, attacker, _defender, game, attacker_player, _defender_player = (
        _start_player_owned_conquer(app, db)
    )
    daggers = ConquerTactic.query.filter_by(
        game_id=game.id,
        player_id=attacker_player.id,
        family_name='Dagger',
        status='available',
    ).order_by(ConquerTactic.id).all()
    assert len(daggers) >= 2

    resp = client.post(
        '/games/combine_conquer_tactics',
        json={
            'game_id': game.id,
            'player_id': attacker_player.id,
            'tactic_id_a': daggers[0].id,
            'tactic_id_b': daggers[1].id,
        },
        headers=_auth_headers(app, attacker),
    )
    assert resp.status_code == 200, resp.get_json()
    combined_id = resp.get_json()['combined_tactic']['id']
    combined = db.session.get(ConquerTactic, combined_id)
    db.session.refresh(daggers[0])
    db.session.refresh(daggers[1])

    assert combined.family_name == 'Double Dagger'
    assert combined.source == 'combine'
    assert combined.status == 'available'
    assert daggers[0].status == 'discarded'
    assert daggers[1].status == 'discarded'

    dismantle = client.post(
        '/games/dismantle_conquer_tactic',
        json={
            'game_id': game.id,
            'player_id': attacker_player.id,
            'tactic_id': combined_id,
        },
        headers=_auth_headers(app, attacker),
    )
    assert dismantle.status_code == 200, dismantle.get_json()
    db.session.refresh(daggers[0])
    db.session.refresh(daggers[1])

    assert db.session.get(ConquerTactic, combined_id) is None
    assert daggers[0].status == 'available'
    assert daggers[1].status == 'available'


def test_skip_battle_turn_uses_available_conquer_tactics(app, db):
    client, attacker, _defender, game, attacker_player, defender_player = (
        _start_player_owned_conquer(app, db)
    )
    _force_active_battle(db, game, attacker_player, defender_player)

    rejected = client.post(
        '/games/skip_battle_turn',
        json={'game_id': game.id, 'player_id': attacker_player.id},
        headers=_auth_headers(app, attacker),
    )
    assert rejected.status_code == 400
    assert 'tactic' in rejected.get_json()['message'].lower()

    attacker_tactics = ConquerTactic.query.filter_by(
        game_id=game.id, player_id=attacker_player.id).all()
    for tactic in attacker_tactics:
        tactic.status = 'discarded'

    defender_tactic = ConquerTactic.query.filter_by(
        game_id=game.id, player_id=defender_player.id).first()
    defender_tactic.status = 'played'
    defender_tactic.played_round = 0
    db.session.commit()

    skipped = client.post(
        '/games/skip_battle_turn',
        json={'game_id': game.id, 'player_id': attacker_player.id},
        headers=_auth_headers(app, attacker),
    )
    assert skipped.status_code == 200, skipped.get_json()
    payload = skipped.get_json()
    assert payload['success'] is True
    assert payload['battle_round'] == 1
    assert payload['battle_turn_player_id'] == game.invader_player_id
    assert 0 in payload['battle_skipped_rounds'][str(attacker_player.id)]


def test_play_conquer_tactic_validates_call_figure_field(app, db):
    client, attacker, _defender, game, attacker_player, defender_player = (
        _start_player_owned_conquer(app, db)
    )
    _force_active_battle(db, game, attacker_player, defender_player)

    tactic = ConquerTactic.query.filter_by(
        game_id=game.id, player_id=attacker_player.id, status='available').first()
    tactic.family_name = 'Call Villager'
    tactic.rank = 'J'
    tactic.value = 1
    village = Figure.query.filter_by(
        game_id=game.id, player_id=attacker_player.id, field='village').first()
    castle = Figure(
        game_id=game.id,
        player_id=attacker_player.id,
        family_name='Test Castle',
        field='castle',
        color='offensive',
        name='Test Castle',
        suit='Hearts',
        produces={},
        requires={},
    )
    db.session.add(castle)
    db.session.commit()

    wrong_field = client.post(
        '/games/play_conquer_tactic',
        json={
            'game_id': game.id,
            'player_id': attacker_player.id,
            'tactic_id': tactic.id,
            'call_figure_id': castle.id,
        },
        headers=_auth_headers(app, attacker),
    )
    assert wrong_field.status_code == 400
    assert 'village' in wrong_field.get_json()['message'].lower()
    db.session.refresh(tactic)
    assert tactic.status == 'available'

    legal = client.post(
        '/games/play_conquer_tactic',
        json={
            'game_id': game.id,
            'player_id': attacker_player.id,
            'tactic_id': tactic.id,
            'call_figure_id': village.id,
        },
        headers=_auth_headers(app, attacker),
    )
    assert legal.status_code == 200, legal.get_json()
    db.session.refresh(tactic)
    assert tactic.status == 'played'
    assert tactic.call_figure_id == village.id
