# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Focused coverage for the conquer tactics-hand model."""

import pytest

from models import (ActiveSpell, BattleMove, CollectionCard, ConquerTactic,
                    Figure, Game, MainCard, Player)

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
    defender_tactic = ConquerTactic.query.filter_by(
        game_id=game.id, player_id=defender_player.id).first()
    defender_tactic.revealed_step_index = 2
    defender_tactic.discarded_step_index = 3
    db.session.commit()

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
    assert hidden['revealed_step_index'] == 2
    assert hidden['discarded_step_index'] == 3
    assert 'family_name' not in hidden
    assert 'value' not in hidden


def test_get_battle_state_includes_active_battle_identity_fields(app, db):
    client, attacker, _defender, game, attacker_player, defender_player = (
        _start_player_owned_conquer(app, db)
    )
    _force_active_battle(db, game, attacker_player, defender_player)

    resp = client.get(
        '/games/get_battle_state',
        query_string={'game_id': game.id, 'player_id': attacker_player.id},
        headers=_auth_headers(app, attacker),
    )

    assert resp.status_code == 200, resp.get_json()
    payload = resp.get_json()
    assert payload['battle_confirmed'] is True
    assert payload['battle_round'] == 0
    assert payload['battle_turn_player_id'] == attacker_player.id
    assert payload['advancing_player_id'] == attacker_player.id
    assert payload['advancing_figure_id'] == game.advancing_figure_id
    assert payload['defending_figure_id'] == game.defending_figure_id


def test_get_battle_state_includes_timer_and_active_spells(app, db):
    from routes.games import CONQUER_ROUND_TIMEOUT_SEC, _conquer_round_deadlines

    client, attacker, _defender, game, attacker_player, defender_player = (
        _start_player_owned_conquer(app, db)
    )
    _force_active_battle(db, game, attacker_player, defender_player)
    _conquer_round_deadlines.pop(game.id, None)

    spell = ActiveSpell(
        game_id=game.id,
        player_id=defender_player.id,
        spell_name='Poison',
        spell_type='enchantment',
        spell_family_name='Poison',
        suit='Spades',
        target_figure_id=game.advancing_figure_id,
        cast_round=1,
        duration=99,
        is_active=True,
        effect_data={
            'counter_origin': True,
            'counter_status': 'executed',
            'target_figure_id': game.advancing_figure_id,
            'power_modifier': -6,
        },
    )
    db.session.add(spell)
    db.session.commit()

    resp = client.get(
        '/games/get_battle_state',
        query_string={'game_id': game.id, 'player_id': attacker_player.id},
        headers=_auth_headers(app, attacker),
    )

    assert resp.status_code == 200, resp.get_json()
    payload = resp.get_json()
    assert payload['conquer_round_deadline_ts'] is not None
    assert payload['conquer_round_timeout_sec'] == CONQUER_ROUND_TIMEOUT_SEC
    assert payload['battle_modifier'] == game.battle_modifier
    poison = next(s for s in payload['active_spells'] if s['spell_name'] == 'Poison')
    assert poison['target_figure_id'] == game.advancing_figure_id
    assert poison['effect_data']['power_modifier'] == -6


def test_get_battle_state_triggers_expired_round_timeout(app, db, monkeypatch):
    from routes.games import _conquer_round_deadlines, _conquer_timeout_last_check
    import ai.ai_worker as ai_worker

    monkeypatch.setattr(ai_worker, 'trigger_ai_if_needed', lambda *args, **kwargs: None)
    client, attacker, _defender, game, attacker_player, defender_player = (
        _start_player_owned_conquer(app, db)
    )
    _force_active_battle(db, game, attacker_player, defender_player)
    _conquer_round_deadlines[game.id] = (0, 0.0)
    _conquer_timeout_last_check.pop(game.id, None)

    resp = client.get(
        '/games/get_battle_state',
        query_string={'game_id': game.id, 'player_id': attacker_player.id},
        headers=_auth_headers(app, attacker),
    )

    assert resp.status_code == 200, resp.get_json()
    payload = resp.get_json()
    db.session.refresh(game)
    played = ConquerTactic.query.filter_by(
        game_id=game.id, status='played', played_round=0).all()
    assert {t.player_id for t in played} >= {
        attacker_player.id, defender_player.id
    }
    assert payload['battle_round'] == 1
    assert game.battle_round == 1
    assert payload['conquer_round_deadline_ts'] is not None


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


def test_final_tactic_response_includes_authoritative_battle_total(app, db):
    """The third-round mutation must not wait for a later poll to score."""
    from routes.games import _compute_server_total_diff

    client, attacker, _defender, game, attacker_player, defender_player = (
        _start_player_owned_conquer(app, db)
    )
    _force_active_battle(db, game, attacker_player, defender_player)

    attacker_tactics = ConquerTactic.query.filter_by(
        game_id=game.id,
        player_id=attacker_player.id,
        status='available',
    ).order_by(ConquerTactic.id).all()
    defender_tactic = ConquerTactic.query.filter_by(
        game_id=game.id,
        player_id=defender_player.id,
        status='available',
    ).first()

    # Seed rounds one and two plus the defender's final move. Duplicate
    # defender rows are sufficient here because the regression targets the
    # response timing/perspective, not tactic-card creation.
    for round_idx, tactic in enumerate(attacker_tactics[:2]):
        tactic.status = 'played'
        tactic.played_round = round_idx
    defender_tactic.status = 'played'
    defender_tactic.played_round = 0
    for round_idx in (1, 2):
        db.session.add(ConquerTactic(
            game_id=game.id,
            player_id=defender_player.id,
            card_id=defender_tactic.card_id,
            card_type=defender_tactic.card_type,
            family_name=defender_tactic.family_name,
            suit=defender_tactic.suit,
            rank=defender_tactic.rank,
            value=defender_tactic.value,
            source='config',
            status='played',
            played_round=round_idx,
            sort_order=round_idx,
        ))
    game.battle_round = 2
    game.battle_turn_player_id = attacker_player.id
    db.session.commit()

    final_tactic = attacker_tactics[2]
    response = client.post(
        '/games/play_conquer_tactic',
        json={
            'game_id': game.id,
            'player_id': attacker_player.id,
            'tactic_id': final_tactic.id,
        },
        headers=_auth_headers(app, attacker),
    )

    assert response.status_code == 200, response.get_json()
    payload = response.get_json()
    db.session.refresh(game)
    expected = _compute_server_total_diff(game)
    assert payload['battle_complete'] is True
    assert payload['battle_total_diff'] == expected
    assert payload['game']['battle_total_diff'] == expected


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


def test_final_round_skips_clear_conquer_tactics_turn(app, db):
    client, attacker, defender, game, attacker_player, defender_player = (
        _start_player_owned_conquer(app, db)
    )
    _force_active_battle(db, game, attacker_player, defender_player)

    for tactic in ConquerTactic.query.filter_by(game_id=game.id).all():
        tactic.status = 'discarded'
    game.battle_round = 2
    game.battle_turn_player_id = attacker_player.id
    game.battle_skipped_rounds = {
        str(attacker_player.id): [0, 1],
        str(defender_player.id): [0, 1],
    }
    db.session.commit()

    first = client.post(
        '/games/skip_battle_turn',
        json={'game_id': game.id, 'player_id': attacker_player.id},
        headers=_auth_headers(app, attacker),
    )
    assert first.status_code == 200, first.get_json()
    first_payload = first.get_json()
    assert first_payload['battle_round'] == 2
    assert first_payload['battle_turn_player_id'] == defender_player.id
    assert first_payload['battle_complete'] is False

    second = client.post(
        '/games/skip_battle_turn',
        json={'game_id': game.id, 'player_id': defender_player.id},
        headers=_auth_headers(app, defender),
    )
    assert second.status_code == 200, second.get_json()
    second_payload = second.get_json()
    assert second_payload['battle_round'] == 2
    assert second_payload['battle_turn_player_id'] is None
    assert second_payload['battle_complete'] is True

    db.session.refresh(game)
    assert game.battle_turn_player_id is None
    assert game.battle_skipped_rounds[str(attacker_player.id)] == [0, 1, 2]
    assert game.battle_skipped_rounds[str(defender_player.id)] == [0, 1, 2]

    repeated = client.post(
        '/games/skip_battle_turn',
        json={'game_id': game.id, 'player_id': attacker_player.id},
        headers=_auth_headers(app, attacker),
    )
    assert repeated.status_code == 200, repeated.get_json()
    repeated_payload = repeated.get_json()
    assert repeated_payload['battle_turn_player_id'] is None
    assert repeated_payload['battle_complete'] is True
    assert repeated_payload['already_skipped'] is True


def test_play_conquer_tactic_validates_family_rank_consistency(app, db):
    client, attacker, _defender, game, attacker_player, defender_player = (
        _start_player_owned_conquer(app, db)
    )
    _force_active_battle(db, game, attacker_player, defender_player)

    tactic = ConquerTactic.query.filter_by(
        game_id=game.id, player_id=attacker_player.id, status='available').first()
    tactic.family_name = 'Block'
    db.session.commit()

    wrong_family = client.post(
        '/games/play_conquer_tactic',
        json={
            'game_id': game.id,
            'player_id': attacker_player.id,
            'tactic_id': tactic.id,
        },
        headers=_auth_headers(app, attacker),
    )
    assert wrong_family.status_code == 400
    assert 'family' in wrong_family.get_json()['message'].lower()
    db.session.refresh(tactic)
    assert tactic.status == 'available'

    tactic.family_name = 'Dagger'
    tactic.rank = 'J'
    db.session.commit()

    wrong_rank = client.post(
        '/games/play_conquer_tactic',
        json={
            'game_id': game.id,
            'player_id': attacker_player.id,
            'tactic_id': tactic.id,
        },
        headers=_auth_headers(app, attacker),
    )
    assert wrong_rank.status_code == 400
    assert 'rank' in wrong_rank.get_json()['message'].lower()
    db.session.refresh(tactic)
    assert tactic.status == 'available'


def test_play_conquer_tactic_validates_double_dagger_rank_consistency(app, db):
    client, attacker, _defender, game, attacker_player, defender_player = (
        _start_player_owned_conquer(app, db)
    )
    daggers = ConquerTactic.query.filter_by(
        game_id=game.id,
        player_id=attacker_player.id,
        family_name='Dagger',
        status='available',
    ).order_by(ConquerTactic.id).all()

    combined_resp = client.post(
        '/games/combine_conquer_tactics',
        json={
            'game_id': game.id,
            'player_id': attacker_player.id,
            'tactic_id_a': daggers[0].id,
            'tactic_id_b': daggers[1].id,
        },
        headers=_auth_headers(app, attacker),
    )
    assert combined_resp.status_code == 200, combined_resp.get_json()
    combined = db.session.get(
        ConquerTactic, combined_resp.get_json()['combined_tactic']['id'])
    combined.rank = '7+J'
    db.session.commit()
    _force_active_battle(db, game, attacker_player, defender_player)

    played = client.post(
        '/games/play_conquer_tactic',
        json={
            'game_id': game.id,
            'player_id': attacker_player.id,
            'tactic_id': combined.id,
        },
        headers=_auth_headers(app, attacker),
    )
    assert played.status_code == 400
    assert 'double dagger rank' in played.get_json()['message'].lower()
    db.session.refresh(combined)
    assert combined.status == 'available'


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
    card = db.session.get(MainCard, tactic.card_id)
    card.rank = 'J'
    card.value = 1
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


def test_skip_allowed_when_only_played_tactics_remain(app, db):
    """The skip filter must ignore tactics already marked as played.

    Regression for the unified-conquer skip bug: rows whose ``status`` was
    still ``available`` *but* whose ``played_round`` was set (e.g. mid-write
    state during a retry) used to wrongly block skip.  The filter now
    requires both ``status='available'`` AND ``played_round IS NULL``.
    """
    client, attacker, _defender, game, attacker_player, defender_player = (
        _start_player_owned_conquer(app, db)
    )
    _force_active_battle(db, game, attacker_player, defender_player)

    for tactic in ConquerTactic.query.filter_by(
            game_id=game.id, player_id=attacker_player.id).all():
        tactic.played_round = 0  # already-played but not yet status-flipped
    defender_tactic = ConquerTactic.query.filter_by(
        game_id=game.id, player_id=defender_player.id).first()
    defender_tactic.status = 'played'
    defender_tactic.played_round = 0
    db.session.commit()

    resp = client.post(
        '/games/skip_battle_turn',
        json={'game_id': game.id, 'player_id': attacker_player.id},
        headers=_auth_headers(app, attacker),
    )
    assert resp.status_code == 200, resp.get_json()


def test_final_skip_response_includes_authoritative_battle_total(app, db):
    """A round-three Skip must carry the score just like a played tactic."""
    from routes.games import _compute_server_total_diff

    client, attacker, _defender, game, attacker_player, defender_player = (
        _start_player_owned_conquer(app, db)
    )
    _force_active_battle(db, game, attacker_player, defender_player)

    for tactic in ConquerTactic.query.filter_by(
            game_id=game.id, player_id=attacker_player.id).all():
        tactic.status = 'discarded'
    defender_tactic = ConquerTactic.query.filter_by(
        game_id=game.id,
        player_id=defender_player.id,
        status='available',
    ).first()
    defender_tactic.status = 'played'
    defender_tactic.played_round = 2
    game.battle_skipped_rounds = {
        str(attacker_player.id): [0, 1],
        str(defender_player.id): [0, 1],
    }
    game.battle_round = 2
    game.battle_turn_player_id = attacker_player.id
    db.session.commit()

    response = client.post(
        '/games/skip_battle_turn',
        json={'game_id': game.id, 'player_id': attacker_player.id},
        headers=_auth_headers(app, attacker),
    )

    assert response.status_code == 200, response.get_json()
    payload = response.get_json()
    db.session.refresh(game)
    expected = _compute_server_total_diff(game)
    assert payload['battle_complete'] is True
    assert payload['battle_total_diff'] == expected
    assert payload['game']['battle_total_diff'] == expected


def test_serialize_exposes_combine_lineage_always(app, db):
    """``ConquerTactic.serialize()`` always emits source ids (even None)."""
    _client, _attacker, _defender, game, attacker_player, _defender_player = (
        _start_player_owned_conquer(app, db)
    )
    tactic = ConquerTactic.query.filter_by(
        game_id=game.id, player_id=attacker_player.id).first()
    data = tactic.serialize()
    assert 'source_tactic_id_a' in data
    assert 'source_tactic_id_b' in data
    assert data['source_tactic_id_a'] is None
    assert data['source_tactic_id_b'] is None


def test_conquer_round_deadline_survives_process_cache_reset(app, db):
    """The authoritative round clock is persisted for every WSGI worker."""
    from routes.games import (
        _conquer_round_deadline_for,
        _conquer_round_deadlines,
        _ensure_conquer_round_deadline,
    )

    _client, _attacker, _defender, game, attacker_player, defender_player = (
        _start_player_owned_conquer(app, db)
    )
    _force_active_battle(db, game, attacker_player, defender_player)

    first = _ensure_conquer_round_deadline(game)
    assert first is not None
    db.session.refresh(game)
    assert game.battle_round_deadline_round == game.battle_round
    assert game.battle_round_deadline_at is not None

    # A second worker starts with an empty process-local cache.
    _conquer_round_deadlines.clear()
    db.session.expire_all()
    reloaded = db.session.get(Game, game.id)
    assert _conquer_round_deadline_for(reloaded) == pytest.approx(
        first,
        abs=0.01,
    )


def test_play_conquer_tactic_idempotent_replay(app, db):
    """Replaying play with the same client_action_id returns cached result."""
    from game_service.conquer_tactics_idempotency import reset_cache_for_tests
    reset_cache_for_tests()

    client, attacker, _defender, game, attacker_player, defender_player = (
        _start_player_owned_conquer(app, db)
    )
    _force_active_battle(db, game, attacker_player, defender_player)
    tactic = ConquerTactic.query.filter_by(
        game_id=game.id, player_id=attacker_player.id, status='available').first()

    payload = {
        'game_id': game.id,
        'player_id': attacker_player.id,
        'tactic_id': tactic.id,
        'client_action_id': 'replay-test-1',
    }
    first = client.post('/games/play_conquer_tactic', json=payload,
                       headers=_auth_headers(app, attacker))
    assert first.status_code == 200, first.get_json()
    first_body = first.get_json()

    # Simulate a retry landing on another worker by clearing the process-local
    # fast cache. The durable receipt must still return the original result.
    reset_cache_for_tests()
    second = client.post('/games/play_conquer_tactic', json=payload,
                        headers=_auth_headers(app, attacker))
    assert second.status_code == 200, second.get_json()
    assert second.get_json()['tactic']['id'] == first_body['tactic']['id']
    assert second.get_json()['battle_turn_player_id'] == first_body['battle_turn_player_id']

    # The tactic was only "played" once; played_round remains the original round.
    db.session.refresh(tactic)
    assert tactic.status == 'played'
    from models import ConquerActionReceipt
    assert ConquerActionReceipt.query.filter_by(
        game_id=game.id,
        player_id=attacker_player.id,
    ).count() == 1


def test_dismantle_validates_source_card_state(app, db):
    """Dismantle refuses to restore tactics whose underlying cards were moved."""
    from game_service.conquer_tactics_idempotency import reset_cache_for_tests
    reset_cache_for_tests()

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

    combine_resp = client.post(
        '/games/combine_conquer_tactics',
        json={
            'game_id': game.id,
            'player_id': attacker_player.id,
            'tactic_id_a': daggers[0].id,
            'tactic_id_b': daggers[1].id,
        },
        headers=_auth_headers(app, attacker),
    )
    assert combine_resp.status_code == 200, combine_resp.get_json()
    combined_id = combine_resp.get_json()['combined_tactic']['id']

    # Simulate a spell or other mutation purging the underlying card of one source.
    purged_card = db.session.get(MainCard, daggers[0].card_id)
    purged_card.part_of_figure = True  # no longer a free hand card
    db.session.commit()

    dismantle = client.post(
        '/games/dismantle_conquer_tactic',
        json={
            'game_id': game.id,
            'player_id': attacker_player.id,
            'tactic_id': combined_id,
        },
        headers=_auth_headers(app, attacker),
    )
    assert dismantle.status_code == 400
    body = dismantle.get_json()
    assert body['success'] is False
    # The combined tactic was marked as discarded so the player is unstuck.
    db.session.refresh(db.session.get(ConquerTactic, combined_id))
    assert db.session.get(ConquerTactic, combined_id).status == 'discarded'


def test_conquer_round_timeout_auto_plays_pending_players(app, db, monkeypatch):
    """When the 60s round deadline expires, pending *human* players have a
    random available tactic auto-played and the round advances."""
    from routes.games import (
        _conquer_round_deadlines, _conquer_timeout_last_check,
        _check_conquer_round_timeout,
    )

    client, _attacker, _defender, game, attacker_player, defender_player = (
        _start_player_owned_conquer(app, db)
    )
    _force_active_battle(db, game, attacker_player, defender_player)

    # Force the deadline into the past so a subsequent get_game poll fires
    # the timeout finalisation path.
    _conquer_round_deadlines[game.id] = (0, 0.0)
    _conquer_timeout_last_check.pop(game.id, None)

    # Sanity: both players still have available tactics, none played yet.
    assert ConquerTactic.query.filter_by(
        game_id=game.id, status='played', played_round=0).count() == 0

    _check_conquer_round_timeout(db.session.get(Game, game.id))

    db.session.refresh(game)
    played = ConquerTactic.query.filter_by(
        game_id=game.id, status='played', played_round=0).all()
    assert {t.player_id for t in played} >= {
        attacker_player.id, defender_player.id
    }
    # Round advanced and a fresh deadline was registered for the new round.
    assert game.battle_round == 1
    entry = _conquer_round_deadlines.get(game.id)
    assert entry is not None
    assert entry[0] == 1
    assert entry[1] > 0


def test_conquer_round_timeout_auto_play_counts_call_tactic_power(
        app, db, monkeypatch):
    """A timeout-played Call tactic must bind its figure before scoring.

    The normal one-tap Play path chooses the best eligible Call figure.  The
    timeout path used to mark the tactic as played without that binding, so
    the live ledger previewed the called figure's power while the server only
    counted the tactic card's raw value in the authoritative battle total.
    """
    from routes.games import (
        _check_conquer_round_timeout,
        _compute_server_total_diff,
        _conquer_round_deadlines,
        _conquer_timeout_last_check,
    )

    _client, _attacker, _defender, game, attacker_player, defender_player = (
        _start_player_owned_conquer(app, db)
    )
    _force_active_battle(db, game, attacker_player, defender_player)

    # Leave the attacker's original village free to be called by moving the
    # active battle slot to a separate military figure.
    callable_village = Figure.query.filter_by(
        game_id=game.id,
        player_id=attacker_player.id,
        field='village',
    ).first()
    battle_figure = Figure(
        game_id=game.id,
        player_id=attacker_player.id,
        family_name='Timeout Test Military',
        field='military',
        color='offensive',
        name='Timeout Test Military',
        suit='Clubs',
        produces={},
        requires={},
    )
    db.session.add(battle_figure)
    db.session.flush()
    game.advancing_figure_id = battle_figure.id

    attacker_tactics = ConquerTactic.query.filter_by(
        game_id=game.id,
        player_id=attacker_player.id,
        status='available',
    ).order_by(ConquerTactic.id).all()
    call_tactic = attacker_tactics[0]
    call_tactic.family_name = 'Call Villager'
    call_tactic.rank = 'J'
    call_tactic.suit = 'Diamonds'
    call_tactic.value = 1
    call_card = db.session.get(MainCard, call_tactic.card_id)
    call_card.rank = 'J'
    call_card.suit = 'Diamonds'
    call_card.value = 1
    for tactic in attacker_tactics[1:]:
        tactic.status = 'discarded'

    # The defender has already submitted the opposing round move, leaving
    # only the attacker for the timeout fallback to finalize.
    defender_tactic = ConquerTactic.query.filter_by(
        game_id=game.id,
        player_id=defender_player.id,
        status='available',
    ).first()
    defender_tactic.status = 'played'
    defender_tactic.played_round = 0
    db.session.commit()

    _conquer_round_deadlines[game.id] = (0, 0.0)
    _conquer_timeout_last_check.pop(game.id, None)
    import ai.ai_worker as ai_worker
    monkeypatch.setattr(
        ai_worker,
        'trigger_ai_if_needed',
        lambda *args, **kwargs: None,
    )

    _check_conquer_round_timeout(db.session.get(Game, game.id))

    db.session.refresh(call_tactic)
    db.session.refresh(call_card)
    assert call_tactic.status == 'played'
    assert call_tactic.played_round == 0
    assert call_tactic.call_figure_id == callable_village.id
    assert call_card.in_deck is True

    _total, breakdown = _compute_server_total_diff(
        db.session.get(Game, game.id),
        return_breakdown=True,
    )
    # Callable village power is 9; matching-suit Jack adds 1, opposed by the
    # defender's 8-power Dagger: (9 + 1) - 8 = +2.
    assert breakdown['round_diff'] == 2


def test_conquer_round_timeout_does_not_auto_play_ai_uses_worker(app, db, monkeypatch):
    """AI players must NOT have a random tactic auto-played on timeout.

    Instead the AI worker is re-triggered so the real AI policy (gamble,
    combine, optimal selection) runs. Otherwise letting the timer hit 0
    would let the human bypass the AI's defender strategy.
    """
    from routes.games import (
        _conquer_round_deadlines, _conquer_timeout_last_check,
        _check_conquer_round_timeout,
    )

    client, _attacker, _defender, game, attacker_player, defender_player = (
        _start_player_owned_conquer(app, db)
    )
    _force_active_battle(db, game, attacker_player, defender_player)

    # Mark the defender's underlying user as AI.
    defender_user = db.session.get(__import__('models').User, defender_player.user_id)
    defender_user.is_ai = True
    db.session.commit()

    _conquer_round_deadlines[game.id] = (0, 0.0)
    _conquer_timeout_last_check.pop(game.id, None)

    triggered = []
    import ai.ai_worker as ai_worker
    monkeypatch.setattr(
        ai_worker, 'trigger_ai_if_needed',
        lambda gid, app=None: triggered.append(gid))

    _check_conquer_round_timeout(db.session.get(Game, game.id))

    db.session.refresh(game)
    played = ConquerTactic.query.filter_by(
        game_id=game.id, status='played', played_round=0).all()
    # Human attacker was auto-played; AI defender was NOT auto-played.
    assert {t.player_id for t in played} == {attacker_player.id}
    # AI worker was re-triggered so its real policy can run.
    assert triggered == [game.id]
