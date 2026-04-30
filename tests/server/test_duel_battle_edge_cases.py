# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Regression tests for duel battle edge cases and intended modifier flow."""


def _make_duel_with_figures(db, two_users):
    from models import Figure, Game, Player

    u1, u2 = two_users
    game = Game(current_round=1, stake=35, mode='duel', ceasefire_active=False)
    db.session.add(game)
    db.session.commit()

    p1 = Player(user_id=u1.id, game_id=game.id, turns_left=2, points=0)
    p2 = Player(user_id=u2.id, game_id=game.id, turns_left=2, points=0)
    db.session.add_all([p1, p2])
    db.session.commit()

    game.invader_player_id = p1.id
    game.turn_player_id = p1.id

    f1 = Figure(
        player_id=p1.id,
        game_id=game.id,
        family_name='Villager',
        field='village',
        color='red',
        name='Invader Villager',
        suit='hearts',
    )
    f2 = Figure(
        player_id=p2.id,
        game_id=game.id,
        family_name='Villager',
        field='village',
        color='red',
        name='Defender Villager',
        suit='diamonds',
    )
    db.session.add_all([f1, f2])
    db.session.commit()
    return game, p1, p2, f1, f2


def test_defender_may_advance_at_two_under_modifier_without_ceasefire(
    client,
    db,
    two_users,
    auth_headers_user2,
):
    game, _p1, p2, _f1, f2 = _make_duel_with_figures(db, two_users)
    game.battle_modifier = [{'type': 'Peasant War'}]
    game.turn_player_id = p2.id
    p2.turns_left = 2
    db.session.commit()

    resp = client.post(
        '/games/advance_figure',
        json={'game_id': game.id, 'player_id': p2.id, 'figure_id': f2.id},
        headers=auth_headers_user2,
    )
    data = resp.get_json()
    assert data.get('success') is True, data

    db.session.refresh(game)
    db.session.refresh(p2)
    assert game.advancing_player_id == p2.id
    assert game.invader_player_id == p2.id
    assert p2.turns_left == 0


def test_blitzkrieg_ceasefire_blocks_defender_advance_at_two(
    client,
    db,
    two_users,
    auth_headers_user2,
):
    game, _p1, p2, _f1, f2 = _make_duel_with_figures(db, two_users)
    game.battle_modifier = [{'type': 'Blitzkrieg'}]
    game.ceasefire_active = True
    game.turn_player_id = p2.id
    p2.turns_left = 2
    db.session.commit()

    resp = client.post(
        '/games/advance_figure',
        json={'game_id': game.id, 'player_id': p2.id, 'figure_id': f2.id},
        headers=auth_headers_user2,
    )
    data = resp.get_json()
    assert data.get('success') is False
    assert 'ceasefire' in data.get('message', '').lower()


def test_instant_charge_can_advance_on_last_turn(
    client,
    db,
    two_users,
    auth_headers_user1,
):
    from models import MainCard, MainRank, Suit

    game, p1, p2, _f1, _f2 = _make_duel_with_figures(db, two_users)
    p1.turns_left = 1
    game.turn_player_id = p1.id
    game.invader_player_id = p1.id
    game.ceasefire_active = False
    card = MainCard(
        game_id=game.id,
        player_id=p1.id,
        suit=Suit.HEARTS,
        rank=MainRank.SEVEN,
        value=7,
        in_deck=False,
    )
    db.session.add(card)
    db.session.commit()

    resp = client.post(
        '/figures/create_figure',
        json={
            'game_id': game.id,
            'player_id': p1.id,
            'family_name': 'Warrior',
            'field': 'military',
            'color': 'red',
            'name': 'Last Turn Charger',
            'suit': 'Hearts',
            'cards': [{'id': card.id, 'type': 'main', 'role': 'key'}],
            'produces': {},
            'requires': {},
            'instant_charge_advance': True,
        },
        headers=auth_headers_user1,
    )
    data = resp.get_json()
    assert data.get('success') is True, data
    assert data.get('instant_charge', {}).get('success') is True

    db.session.refresh(game)
    db.session.refresh(p1)
    assert game.advancing_player_id == p1.id
    assert p1.turns_left == 0
    assert game.turn_player_id == p2.id


def test_instant_charge_can_counter_advance_on_last_turn(
    client,
    db,
    two_users,
    auth_headers_user2,
):
    from models import MainCard, MainRank, Suit

    game, p1, p2, f1, _f2 = _make_duel_with_figures(db, two_users)
    game.advancing_player_id = p1.id
    game.advancing_figure_id = f1.id
    game.turn_player_id = p2.id
    game.invader_player_id = p1.id
    game.ceasefire_active = False
    p2.turns_left = 1
    card = MainCard(
        game_id=game.id,
        player_id=p2.id,
        suit=Suit.SPADES,
        rank=MainRank.SEVEN,
        value=7,
        in_deck=False,
    )
    db.session.add(card)
    db.session.commit()

    resp = client.post(
        '/figures/create_figure',
        json={
            'game_id': game.id,
            'player_id': p2.id,
            'family_name': 'Warrior',
            'field': 'military',
            'color': 'black',
            'name': 'Counter Charger',
            'suit': 'Spades',
            'cards': [{'id': card.id, 'type': 'main', 'role': 'key'}],
            'produces': {},
            'requires': {},
            'instant_charge_advance': True,
        },
        headers=auth_headers_user2,
    )
    data = resp.get_json()
    assert data.get('success') is True, data
    assert data.get('instant_charge', {}).get('success') is True
    assert data.get('instant_charge', {}).get('is_counter_advance') is True

    db.session.refresh(game)
    db.session.refresh(p2)
    assert game.defending_figure_id == data['figure']['id']
    assert p2.turns_left == 0
    assert game.turn_player_id == p1.id


def test_battle_decision_rejects_missing_battle_figures(
    client,
    db,
    two_users,
    auth_headers_user1,
):
    game, p1, _p2, _f1, _f2 = _make_duel_with_figures(db, two_users)
    game.advancing_figure_id = None
    game.defending_figure_id = None
    game.advancing_player_id = None
    db.session.commit()

    resp = client.post(
        '/games/battle_decision',
        json={'game_id': game.id, 'player_id': p1.id, 'decision': 'battle'},
        headers=auth_headers_user1,
    )
    data = resp.get_json()
    assert data.get('success') is False
    assert data.get('reason') == 'battle_not_ready'


def test_conquer_battle_decision_rejects_fold(
    client,
    db,
    two_users,
    auth_headers_user1,
):
    game, p1, p2, f1, f2 = _make_duel_with_figures(db, two_users)
    game.mode = 'conquer'
    game.advancing_player_id = p1.id
    game.advancing_figure_id = f1.id
    game.defending_figure_id = f2.id
    game.turn_player_id = p1.id
    db.session.commit()

    resp = client.post(
        '/games/battle_decision',
        json={'game_id': game.id, 'player_id': p1.id, 'decision': 'fold'},
        headers=auth_headers_user1,
    )
    data = resp.get_json()
    assert data.get('success') is False
    assert data.get('reason') == 'conquer_no_fold'


def test_expired_draw_choice_defaults_to_defender_points(
    client,
    db,
    two_users,
    auth_headers_user1,
):
    game, p1, p2, f1, f2 = _make_duel_with_figures(db, two_users)
    game.battle_confirmed = True
    game.advancing_player_id = p1.id
    game.advancing_figure_id = f1.id
    game.defending_figure_id = f2.id
    game.last_battle_result = {
        'post_battle_pending_choice': {
            'type': 'draw_choice',
            'player_id': p2.id,
            'default': 'points',
            'deadline_at': '2000-01-01T00:00:00',
        }
    }
    before_points = p2.points
    before_round = game.current_round
    db.session.commit()

    resp = client.post(
        '/games/resolve_pending_battle_choice',
        json={'game_id': game.id, 'player_id': p1.id},
        headers=auth_headers_user1,
    )
    data = resp.get_json()
    assert data.get('success') is True, data
    assert data.get('defaulted') is True
    assert data.get('choice') == 'points'

    db.session.refresh(game)
    db.session.refresh(p2)
    assert p2.points == before_points + 10
    assert game.current_round == before_round + 1
    assert game.invader_player_id == p2.id
    assert game.battle_confirmed is False
    assert 'post_battle_pending_choice' not in (game.last_battle_result or {})


def test_expired_winner_pick_defaults_and_starts_next_round(
    client,
    db,
    two_users,
    auth_headers_user2,
):
    game, p1, p2, f1, f2 = _make_duel_with_figures(db, two_users)
    game.battle_confirmed = True
    game.advancing_player_id = p1.id
    game.advancing_figure_id = f1.id
    game.defending_figure_id = f2.id
    game.fold_winner_id = p2.id
    game.last_battle_result = {
        'winner_player_id': p2.id,
        'post_battle_pending_choice': {
            'type': 'winner_pick',
            'player_id': p2.id,
            'default': 'first_available_card',
            'deadline_at': '2000-01-01T00:00:00',
        }
    }
    before_round = game.current_round
    db.session.commit()

    resp = client.post(
        '/games/resolve_pending_battle_choice',
        json={'game_id': game.id, 'player_id': p2.id},
        headers=auth_headers_user2,
    )
    data = resp.get_json()
    assert data.get('success') is True, data
    assert data.get('defaulted') is True

    db.session.refresh(game)
    assert game.current_round == before_round + 1
    assert game.invader_player_id == p2.id
    assert game.battle_confirmed is False
    assert game.fold_winner_id is None
    assert 'post_battle_pending_choice' not in (game.last_battle_result or {})
