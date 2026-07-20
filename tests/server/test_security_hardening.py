# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Security-hardening regression tests for public launch boundaries."""

from werkzeug.security import generate_password_hash


def _headers(user_id):
    from routes.auth import generate_token
    return {'Authorization': f'Bearer {generate_token(user_id)}'}


def _make_visibility_game(db):
    from models import (
        ActiveSpell,
        BattleMove,
        CardRole,
        CardToFigure,
        Figure,
        Game,
        MainCard,
        MainRank,
        Player,
        Suit,
        User,
    )

    u1 = User(username='visible_p1', password_hash=generate_password_hash('pass1234'))
    u2 = User(username='visible_p2', password_hash=generate_password_hash('pass1234'))
    outsider = User(username='visible_out', password_hash=generate_password_hash('pass1234'))
    db.session.add_all([u1, u2, outsider])
    db.session.flush()

    game = Game(stake=35, ai_seed=123456)
    db.session.add(game)
    db.session.flush()

    p1 = Player(user_id=u1.id, game_id=game.id, turns_left=6, points=0)
    p2 = Player(user_id=u2.id, game_id=game.id, turns_left=6, points=0)
    db.session.add_all([p1, p2])
    db.session.flush()
    game.turn_player_id = p1.id
    game.invader_player_id = p1.id

    own_card = MainCard(
        player_id=p1.id, game_id=game.id, suit=Suit.HEARTS,
        rank=MainRank.SEVEN, value=7, in_deck=False, deck_position=7,
    )
    opponent_card = MainCard(
        player_id=p2.id, game_id=game.id, suit=Suit.SPADES,
        rank=MainRank.KING, value=40, in_deck=False, deck_position=2,
    )
    deck_card = MainCard(
        player_id=None, game_id=game.id, suit=Suit.CLUBS,
        rank=MainRank.ACE, value=30, in_deck=True, deck_position=1,
    )
    db.session.add_all([own_card, opponent_card, deck_card])
    db.session.flush()

    figure = Figure(
        player_id=p2.id,
        game_id=game.id,
        family_name='Knight',
        field='military',
        color='black',
        name='Hidden Knight',
        suit='Spades',
    )
    db.session.add(figure)
    db.session.flush()
    db.session.add(CardToFigure(
        figure_id=figure.id,
        card_id=opponent_card.id,
        card_type='main',
        role=CardRole.NUMBER,
    ))

    db.session.add(BattleMove(
        game_id=game.id,
        player_id=p2.id,
        family_name='Dagger',
        card_id=opponent_card.id,
        card_type='main',
        suit='Spades',
        rank='K',
        value=40,
    ))
    db.session.commit()
    return game, p1, p2, u1, u2, outsider, ActiveSpell


def test_get_game_redacts_hidden_state_for_viewer(client, db):
    game, p1, p2, u1, _, _, _ = _make_visibility_game(db)

    resp = client.get(
        f'/games/get_game?game_id={game.id}',
        headers=_headers(u1.id),
    )
    data = resp.get_json()['game']

    assert data['ai_seed'] is None
    assert all(card.get('in_deck') is not True for card in data['main_cards'])

    opponent = next(player for player in data['players'] if player['id'] == p2.id)
    hidden_hand_card = opponent['main_hand'][0]
    assert hidden_hand_card['id'] is None
    assert hidden_hand_card['rank'] is None
    assert hidden_hand_card['suit'] is None
    assert hidden_hand_card['value'] == 0
    assert hidden_hand_card['deck_position'] is None

    # Field figures are PUBLIC — the opponent's army and its card composition
    # stay visible (core to attack/defense strategy). Only hands and unplayed
    # battle moves are secret.
    visible_figure_card = opponent['figures'][0]['cards'][0]
    assert visible_figure_card['card_id'] is not None
    assert visible_figure_card['rank'] == 'K'
    assert visible_figure_card['suit'] == 'Spades'

    hidden_move = next(move for move in data['battle_moves'] if move['player_id'] == p2.id)
    assert hidden_move['id'] is not None
    assert 'family_name' not in hidden_move
    assert 'card_id' not in hidden_move
    assert 'rank' not in hidden_move

    viewer = next(player for player in data['players'] if player['id'] == p1.id)
    assert viewer['main_hand'][0]['rank'] == '7'


def test_all_seeing_eye_preserves_intended_reveal(client, db):
    game, p1, p2, u1, _, _, ActiveSpell = _make_visibility_game(db)
    db.session.add(ActiveSpell(
        game_id=game.id,
        player_id=p1.id,
        spell_name='All Seeing Eye',
        spell_type='enchantment',
        spell_family_name='All Seeing Eye',
        suit='Hearts',
        cast_round=1,
        is_active=True,
    ))
    db.session.commit()

    resp = client.get(
        f'/games/get_game?game_id={game.id}',
        headers=_headers(u1.id),
    )
    data = resp.get_json()['game']
    opponent = next(player for player in data['players'] if player['id'] == p2.id)

    assert opponent['main_hand'][0]['rank'] == 'K'
    assert opponent['figures'][0]['cards'][0]['card_id'] is not None


def test_get_game_rejects_non_participant(client, db):
    game, _, _, _, _, outsider, _ = _make_visibility_game(db)

    resp = client.get(
        f'/games/get_game?game_id={game.id}',
        headers=_headers(outsider.id),
    )

    assert resp.status_code == 403


def test_get_battle_moves_redacts_opponent_unplayed_moves(client, db):
    game, _, p2, u1, _, _, _ = _make_visibility_game(db)

    resp = client.get(
        f'/battle_shop/get_battle_moves?game_id={game.id}&player_id={p2.id}',
        headers=_headers(u1.id),
    )
    data = resp.get_json()

    assert data['success'] is True
    move = data['battle_moves'][0]
    assert move['player_id'] == p2.id
    assert 'family_name' not in move
    assert 'card_id' not in move
    assert 'suit' not in move
    assert 'rank' not in move


def test_register_records_legal_acceptance(client, db):
    from models import User

    resp = client.post('/auth/register', data={
        'username': 'legal_accept',
        'password': 'securepass',
        'age_confirmed': 'true',
        'terms_accepted': 'true',
        'privacy_accepted': 'true',
    })

    assert resp.status_code == 200
    user = User.query.filter_by(username='legal_accept').first()
    assert user.age_confirmed is True
    assert user.age_confirmed_at is not None
    assert user.terms_version
    assert user.terms_accepted_at is not None
    assert user.privacy_version
    assert user.privacy_accepted_at is not None


def test_legal_documents_are_public(client):
    resp = client.get('/legal/versions')
    data = resp.get_json()
    assert resp.status_code == 200
    assert data['success'] is True
    assert data['documents']['terms'] == '/legal/terms'

    terms = client.get('/legal/terms')
    assert terms.status_code == 200
    assert b'Nepal Kings Terms of Service' in terms.data


def test_security_headers_are_set(client):
    resp = client.get('/legal/terms')

    assert resp.headers['X-Content-Type-Options'] == 'nosniff'
    assert resp.headers['X-Frame-Options'] == 'DENY'
    assert resp.headers['Referrer-Policy'] == 'strict-origin-when-cross-origin'
    assert "frame-ancestors 'none'" in resp.headers['Content-Security-Policy']
    assert 'geolocation=()' in resp.headers['Permissions-Policy']


def test_oversized_request_body_returns_json_413(client, app):
    oversized = 'x' * (app.config['MAX_CONTENT_LENGTH'] + 1)

    resp = client.post('/auth/register', data={'username': oversized})

    assert resp.status_code == 413
    payload = resp.get_json()
    assert payload['success'] is False
    assert payload['message'] == 'Request too large'
    assert len(payload['request_id']) == 32
    assert resp.headers['X-Request-ID'] == payload['request_id']


def test_no_route_returns_raw_exception_text():
    """Regression guard: no route may echo str(e) back to the client."""
    import os
    import re

    routes_dir = os.path.join(os.path.dirname(__file__), '..', '..', 'server', 'routes')
    offenders = []
    for filename in sorted(os.listdir(routes_dir)):
        if not filename.endswith('.py'):
            continue
        with open(os.path.join(routes_dir, filename)) as f:
            for lineno, line in enumerate(f, 1):
                if re.search(r'jsonify\(.*str\(e\)', line):
                    offenders.append(f'{filename}:{lineno}')
    assert not offenders, f'Routes leaking raw exception text: {offenders}'


def _make_log_game(db, user):
    from models import Game, Player

    game = Game(stake=35)
    db.session.add(game)
    db.session.flush()
    player = Player(user_id=user.id, game_id=game.id, turns_left=6, points=0)
    db.session.add(player)
    db.session.commit()
    return game, player


def test_add_log_entry_rejects_non_integer_round(client, db, two_users):
    u1, _ = two_users
    game, player = _make_log_game(db, u1)

    resp = client.post('/msg/add_log_entry', json={
        'game_id': game.id,
        'player_id': player.id,
        'round_number': 'not-a-number',
        'turn_number': 1,
        'message': 'hello',
        'author': 'player1',
        'type': 'info',
    }, headers=_headers(u1.id))

    assert resp.status_code == 400
    assert 'must be integers' in resp.get_json()['message']


def test_add_log_entry_rejects_out_of_range_round(client, db, two_users):
    u1, _ = two_users
    game, player = _make_log_game(db, u1)

    resp = client.post('/msg/add_log_entry', json={
        'game_id': game.id,
        'player_id': player.id,
        'round_number': -1,
        'turn_number': 999999999,
        'message': 'hello',
        'author': 'player1',
        'type': 'info',
    }, headers=_headers(u1.id))

    assert resp.status_code == 400
    assert 'out of range' in resp.get_json()['message']


def test_add_log_entry_truncates_oversized_fields(client, db, two_users):
    u1, _ = two_users
    game, player = _make_log_game(db, u1)

    resp = client.post('/msg/add_log_entry', json={
        'game_id': game.id,
        'player_id': player.id,
        'round_number': 1,
        'turn_number': 1,
        'message': 'm' * 5000,
        'author': 'a' * 500,
        'type': 't' * 500,
    }, headers=_headers(u1.id))

    assert resp.status_code == 200
    entry = resp.get_json()['log_entry']
    assert len(entry['message']) == 500
    assert len(entry['author']) == 80
    assert len(entry['type']) == 50


def test_get_rankings_aggregates_finished_games(client, db, two_users):
    from models import Game, Player

    u1, u2 = two_users
    game = Game(stake=35, state='finished')
    db.session.add(game)
    db.session.flush()
    p1 = Player(user_id=u1.id, game_id=game.id, turns_left=0, points=10)
    p2 = Player(user_id=u2.id, game_id=game.id, turns_left=0, points=5)
    db.session.add_all([p1, p2])
    db.session.flush()
    game.winner_player_id = p1.id
    db.session.commit()

    resp = client.get('/auth/get_rankings')

    assert resp.status_code == 200
    rankings = {r['username']: r for r in resp.get_json()['rankings']}
    assert rankings['player1'] == {
        'username': 'player1', 'gold': 100, 'total_games': 1,
        'wins': 1, 'losses': 0, 'is_online': False,
    }
    assert rankings['player2']['wins'] == 0
    assert rankings['player2']['losses'] == 1
    assert rankings['player2']['total_games'] == 1
