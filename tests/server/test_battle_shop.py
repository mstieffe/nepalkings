# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for the battle shop: buying, returning and combining battle moves."""
import json
import pytest


@pytest.fixture
def game_with_player(db):
    """Set up a minimal game with one active player holding a full hand."""
    from models import Game, Player, User
    from werkzeug.security import generate_password_hash
    from game_service.deck import Deck

    u1 = User(username='bs_p1', password_hash=generate_password_hash('p'), gold=200)
    u2 = User(username='bs_p2', password_hash=generate_password_hash('p'), gold=200)
    db.session.add_all([u1, u2])
    db.session.commit()

    game = Game(current_round=1, stake=35, battle_confirmed=False, battle_decisions=None)
    db.session.add(game)
    db.session.commit()

    p1 = Player(user_id=u1.id, game_id=game.id, turns_left=6, points=0)
    p2 = Player(user_id=u2.id, game_id=game.id, turns_left=6, points=0)
    db.session.add_all([p1, p2])
    db.session.commit()

    game.turn_player_id = p1.id
    game.invader_player_id = p1.id
    db.session.commit()

    deck = Deck(game)
    deck.create()
    deck.shuffle()
    deck.deal_cards([p1, p2], num_main_cards=12, num_side_cards=0)
    return game, p1, p2, u1, u2


@pytest.fixture
def auth_token_bs(app, game_with_player):
    from routes.auth import generate_token
    _, p1, _, _, _ = game_with_player
    return generate_token(p1.user_id)


def _buy_move(client, token, game, player, card):
    """Helper to call /battle_shop/buy_battle_move."""
    rank_val = card.rank.value if hasattr(card.rank, 'value') else str(card.rank)
    suit_val = card.suit.value if hasattr(card.suit, 'value') else str(card.suit)
    # Determine family from rank
    family_map = {'J': 'Call Villager', 'Q': 'Block', 'A': 'Call Military', 'K': 'Call King'}
    number_ranks = {'7', '8', '9', '10'}
    family = family_map.get(rank_val, 'Dagger' if rank_val in number_ranks else 'Unknown')
    payload = {
        'game_id': game.id,
        'player_id': player.id,
        'family_name': family,
        'card_id': card.id,
        'card_type': 'main',
        'suit': suit_val,
        'rank': rank_val,
        'value': card.value,
    }
    return client.post('/battle_shop/buy_battle_move', data=json.dumps(payload),
                       content_type='application/json',
                       headers={'Authorization': f'Bearer {token}'})


def _get_hand_card_by_rank(db, player_id, rank, exclude_ids=None):
    from models import MainCard
    q = MainCard.query.filter_by(player_id=player_id, in_deck=False,
                                 part_of_figure=False, part_of_battle_move=False,
                                 rank=rank)
    if exclude_ids:
        q = q.filter(~MainCard.id.in_(exclude_ids))
    return q.first()


class TestBuyBattleMove:
    def test_buy_call_villager_requires_jack_card(self, client, db, app, game_with_player, auth_token_bs):
        game, p1, _, _, _ = game_with_player
        card = _get_hand_card_by_rank(db, p1.id, 'J')
        assert card is not None, "No Jack card in hand"
        resp = _buy_move(client, auth_token_bs, game, p1, card)
        data = resp.get_json()
        assert data.get('success') is True
        assert data['battle_move']['family_name'] == 'Call Villager'

    def test_buy_block_requires_queen_card(self, client, db, app, game_with_player, auth_token_bs):
        game, p1, _, _, _ = game_with_player
        card = _get_hand_card_by_rank(db, p1.id, 'Q')
        assert card is not None, "No Queen card in hand"
        resp = _buy_move(client, auth_token_bs, game, p1, card)
        data = resp.get_json()
        assert data.get('success') is True
        assert data['battle_move']['family_name'] == 'Block'

    def test_buy_call_military_requires_ace_card(self, client, db, app, game_with_player, auth_token_bs):
        game, p1, _, _, _ = game_with_player
        card = _get_hand_card_by_rank(db, p1.id, 'A')
        assert card is not None, "No Ace card in hand"
        resp = _buy_move(client, auth_token_bs, game, p1, card)
        data = resp.get_json()
        assert data.get('success') is True
        assert data['battle_move']['family_name'] == 'Call Military'

    def test_buy_dagger_requires_number_card(self, client, db, app, game_with_player, auth_token_bs):
        game, p1, _, _, _ = game_with_player
        # Any number card 7-10
        for rank in ('7', '8', '9', '10'):
            card = _get_hand_card_by_rank(db, p1.id, rank)
            if card:
                break
        assert card is not None, "No number card in hand"
        resp = _buy_move(client, auth_token_bs, game, p1, card)
        data = resp.get_json()
        assert data.get('success') is True
        assert data['battle_move']['family_name'] == 'Dagger'

    def test_buy_move_removes_card_from_free_hand(self, client, db, app, game_with_player, auth_token_bs):
        from models import MainCard
        game, p1, _, _, _ = game_with_player
        card = _get_hand_card_by_rank(db, p1.id, 'J')
        _buy_move(client, auth_token_bs, game, p1, card)
        db.session.refresh(card)
        assert card.part_of_battle_move is True

    def test_buy_move_creates_battle_move_record(self, client, db, app, game_with_player, auth_token_bs):
        from models import BattleMove
        game, p1, _, _, _ = game_with_player
        card = _get_hand_card_by_rank(db, p1.id, 'J')
        _buy_move(client, auth_token_bs, game, p1, card)
        moves = BattleMove.query.filter_by(game_id=game.id, player_id=p1.id).all()
        assert len(moves) == 1

    def test_buy_move_fails_without_auth(self, client, db, app, game_with_player):
        game, p1, _, _, _ = game_with_player
        card = _get_hand_card_by_rank(db, p1.id, 'J')
        rank_val = card.rank.value if hasattr(card.rank, 'value') else str(card.rank)
        suit_val = card.suit.value if hasattr(card.suit, 'value') else str(card.suit)
        payload = {
            'game_id': game.id,
            'player_id': p1.id,
            'family_name': 'Call Villager',
            'card_id': card.id,
            'card_type': 'main',
            'suit': suit_val,
            'rank': rank_val,
            'value': card.value,
        }
        resp = client.post('/battle_shop/buy_battle_move', data=json.dumps(payload),
                           content_type='application/json')
        assert resp.status_code == 401

    def test_double_dagger_created_by_combining_two_daggers(self, client, db, app, game_with_player, auth_token_bs):
        from models import BattleMove
        game, p1, _, _, _ = game_with_player
        # Buy two daggers
        dagger_cards = []
        for rank in ('7', '8', '9', '10'):
            card = _get_hand_card_by_rank(db, p1.id, rank, exclude_ids=[c.id for c in dagger_cards])
            if card and len(dagger_cards) < 2:
                dagger_cards.append(card)
            if len(dagger_cards) == 2:
                break
        assert len(dagger_cards) == 2

        move_ids = []
        for card in dagger_cards:
            resp = _buy_move(client, auth_token_bs, game, p1, card)
            data = resp.get_json()
            assert data.get('success') is True
            move_ids.append(data['battle_move']['id'])

        # Combine them into a Double Dagger
        combine_payload = {
            'game_id': game.id,
            'player_id': p1.id,
            'move_id_a': move_ids[0],
            'move_id_b': move_ids[1],
        }
        resp = client.post('/battle_shop/combine_battle_moves',
                           data=json.dumps(combine_payload),
                           content_type='application/json',
                           headers={'Authorization': f'Bearer {auth_token_bs}'})
        data = resp.get_json()
        assert data.get('success') is True
        assert data['combined_move']['family_name'] == 'Double Dagger'


class TestReturnBattleMove:
    def test_return_battle_move_success(self, client, db, app, game_with_player, auth_token_bs):
        from models import BattleMove, MainCard
        game, p1, _, _, _ = game_with_player
        card = _get_hand_card_by_rank(db, p1.id, 'J')
        buy_resp = _buy_move(client, auth_token_bs, game, p1, card)
        move_id = buy_resp.get_json()['battle_move']['id']

        payload = {'game_id': game.id, 'player_id': p1.id, 'battle_move_id': move_id}
        resp = client.post('/battle_shop/return_battle_move',
                           data=json.dumps(payload),
                           content_type='application/json',
                           headers={'Authorization': f'Bearer {auth_token_bs}'})
        data = resp.get_json()
        assert data.get('success') is True
        assert BattleMove.query.get(move_id) is None
        db.session.refresh(card)
        assert card.part_of_battle_move is False
