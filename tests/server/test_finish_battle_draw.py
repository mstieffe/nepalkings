# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for draw-resolution endpoint: /games/finish_battle_draw.

Test oracle (desired outcomes):
- Defender can choose points and becomes invader for the next round.
- Destroy choice removes invader battle figure(s) and starts a new round.
- pick_card transfers the chosen battle card to the defender and clears battle moves.
"""


def _rank_to_family(rank):
    family_map = {
        'J': 'Call Villager',
        'Q': 'Block',
        'A': 'Call Military',
        'K': 'Call King',
    }
    if rank in family_map:
        return family_map[rank]
    if rank in {'7', '8', '9', '10'}:
        return 'Dagger'
    return 'Dagger'


def _rank_value(card):
    return card.rank.value if hasattr(card.rank, 'value') else str(card.rank)


def _suit_value(card):
    return card.suit.value if hasattr(card.suit, 'value') else str(card.suit)


def _prepare_main_card_for_player(db, game_id, player_id, rank, exclude_ids=None):
    from models import MainCard

    exclude_ids = exclude_ids or []

    q = MainCard.query.filter_by(
        player_id=player_id,
        in_deck=False,
        part_of_figure=False,
        part_of_battle_move=False,
        rank=rank,
    )
    if exclude_ids:
        q = q.filter(~MainCard.id.in_(exclude_ids))
    card = q.first()
    if card:
        return card

    q = MainCard.query.filter_by(
        game_id=game_id,
        rank=rank,
        part_of_figure=False,
        part_of_battle_move=False,
    )
    if exclude_ids:
        q = q.filter(~MainCard.id.in_(exclude_ids))
    card = q.first()
    if not card:
        return None

    card.player_id = player_id
    card.in_deck = False
    db.session.commit()
    return card


def _buy_move(client, headers, game_id, player_id, card):
    resp = client.post(
        '/battle_shop/buy_battle_move',
        json={
            'game_id': game_id,
            'player_id': player_id,
            'family_name': _rank_to_family(_rank_value(card)),
            'card_id': card.id,
            'card_type': 'main',
            'suit': _suit_value(card),
            'rank': _rank_value(card),
            'value': card.value,
        },
        headers=headers,
    )
    data = resp.get_json()
    assert data.get('success') is True, data
    return data['battle_move']


def _create_battle_draw_game(client, db, two_users, auth_headers_user1, auth_headers_user2):
    from models import Challenge, Game, Player

    u1, u2 = two_users

    create_challenge = client.post(
        '/challenges/create_challenge',
        data={
            'challenger': u1.username,
            'opponent': u2.username,
            'stake': '35',
        },
        headers=auth_headers_user1,
    )
    assert create_challenge.get_json().get('success') is True

    challenge = Challenge.query.first()
    assert challenge is not None

    create_game = client.post(
        '/games/create_game',
        data={'challenge_id': str(challenge.id)},
        headers=auth_headers_user1,
    )
    create_data = create_game.get_json()
    assert create_data.get('success') is True, create_data

    game = db.session.get(Game, create_data['game']['id'])
    assert game is not None

    invader = db.session.get(Player, game.invader_player_id)
    defender = next(p for p in game.players if p.id != invader.id)
    assert invader is not None
    assert defender is not None

    header_by_user_id = {
        u1.id: auth_headers_user1,
        u2.id: auth_headers_user2,
    }
    invader_headers = header_by_user_id[invader.user_id]
    defender_headers = header_by_user_id[defender.user_id]

    game.battle_confirmed = True
    game.advancing_player_id = invader.id
    db.session.commit()

    return game, invader, defender, invader_headers, defender_headers


class TestFinishBattleDraw:
    def test_choice_points_awards_defender_and_starts_new_round(
        self,
        client,
        db,
        two_users,
        auth_headers_user1,
        auth_headers_user2,
    ):
        game, invader, defender, _, defender_headers = _create_battle_draw_game(
            client,
            db,
            two_users,
            auth_headers_user1,
            auth_headers_user2,
        )

        round_before = game.current_round
        points_before = defender.points

        resp = client.post(
            '/games/finish_battle_draw',
            json={
                'game_id': game.id,
                'player_id': defender.id,
                'choice': 'points',
            },
            headers=defender_headers,
        )
        data = resp.get_json()
        assert data.get('success') is True, data
        assert data.get('outcome') == 'draw'
        assert data.get('choice') == 'points'

        db.session.refresh(game)
        db.session.refresh(defender)
        assert defender.points == points_before + 10
        assert game.current_round == round_before + 1
        assert game.invader_player_id == defender.id
        assert game.battle_confirmed is False
        assert game.ceasefire_active is True

    def test_choice_destroy_removes_advancing_figure_and_starts_new_round(
        self,
        client,
        db,
        two_users,
        auth_headers_user1,
        auth_headers_user2,
    ):
        from models import Figure

        game, invader, defender, _, defender_headers = _create_battle_draw_game(
            client,
            db,
            two_users,
            auth_headers_user1,
            auth_headers_user2,
        )

        extra_fig = Figure(
            player_id=invader.id,
            game_id=game.id,
            family_name='Test Raider',
            field='military',
            color='grey',
            name='Test Raider',
            suit='Clubs',
            description='Temporary figure for draw-destroy test',
            produces={},
            requires={},
            checkmate=False,
        )
        db.session.add(extra_fig)
        db.session.commit()

        game.advancing_figure_id = extra_fig.id
        db.session.commit()
        round_before = game.current_round

        resp = client.post(
            '/games/finish_battle_draw',
            json={
                'game_id': game.id,
                'player_id': defender.id,
                'choice': 'destroy',
            },
            headers=defender_headers,
        )
        data = resp.get_json()
        assert data.get('success') is True, data
        assert data.get('outcome') == 'draw'
        assert data.get('choice') == 'destroy'

        db.session.refresh(game)
        assert db.session.get(Figure, extra_fig.id) is None
        assert game.current_round == round_before + 1
        assert game.invader_player_id == defender.id
        assert game.advancing_figure_id is None

    def test_choice_pick_card_assigns_card_and_clears_battle_moves(
        self,
        client,
        db,
        two_users,
        auth_headers_user1,
        auth_headers_user2,
    ):
        from models import BattleMove, MainCard

        game, invader, defender, invader_headers, defender_headers = _create_battle_draw_game(
            client,
            db,
            two_users,
            auth_headers_user1,
            auth_headers_user2,
        )

        invader_card = _prepare_main_card_for_player(db, game.id, invader.id, 'J')
        defender_card = _prepare_main_card_for_player(db, game.id, defender.id, 'Q')
        assert invader_card is not None
        assert defender_card is not None

        invader_move = _buy_move(client, invader_headers, game.id, invader.id, invader_card)
        defender_move = _buy_move(client, defender_headers, game.id, defender.id, defender_card)

        invader_bm = db.session.get(BattleMove, invader_move['id'])
        defender_bm = db.session.get(BattleMove, defender_move['id'])
        invader_bm.played_round = 0
        defender_bm.played_round = 0
        db.session.commit()

        round_before = game.current_round
        resp = client.post(
            '/games/finish_battle_draw',
            json={
                'game_id': game.id,
                'player_id': defender.id,
                'choice': 'pick_card',
                'picked_card_id': invader_card.id,
                'picked_card_type': 'main',
            },
            headers=defender_headers,
        )
        data = resp.get_json()
        assert data.get('success') is True, data
        assert data.get('outcome') == 'draw'
        assert data.get('choice') == 'pick_card'

        db.session.refresh(game)
        db.session.refresh(defender)
        db.session.refresh(invader)

        picked = db.session.get(MainCard, invader_card.id)
        assert picked is not None
        assert picked.player_id == defender.id
        assert picked.in_deck is False
        assert picked.part_of_battle_move is False

        assert BattleMove.query.filter_by(game_id=game.id).count() == 0
        assert game.current_round == round_before + 1
        assert game.invader_player_id == defender.id