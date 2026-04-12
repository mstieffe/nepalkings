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


@pytest.fixture
def auth_token_bs_p2(app, game_with_player):
    from routes.auth import generate_token
    _, _, p2, _, _ = game_with_player
    return generate_token(p2.user_id)


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


def _get_hand_card_by_rank(db, game_id, player_id, rank, exclude_ids=None, preferred_suits=None):
    from models import MainCard

    q = MainCard.query.filter_by(player_id=player_id, in_deck=False,
                                 part_of_figure=False, part_of_battle_move=False,
                                 rank=rank)
    if preferred_suits:
        q = q.filter(MainCard.suit.in_(preferred_suits))
    if exclude_ids:
        q = q.filter(~MainCard.id.in_(exclude_ids))
    card = q.first()
    if card:
        return card

    # Deterministic fallback: move a suitable card from anywhere in the game
    # into this player's hand so tests do not depend on shuffled deal outcome.
    q = MainCard.query.filter_by(game_id=game_id, rank=rank,
                                 part_of_figure=False, part_of_battle_move=False)
    if preferred_suits:
        q = q.filter(MainCard.suit.in_(preferred_suits))
    if exclude_ids:
        q = q.filter(~MainCard.id.in_(exclude_ids))
    card = q.first()
    if not card:
        return None

    card.player_id = player_id
    card.in_deck = False
    db.session.commit()
    return card


def _buy_three_moves(client, db, token, game, player):
    moves = []
    for rank in ('J', 'Q', 'A'):
        card = _get_hand_card_by_rank(db, game.id, player.id, rank)
        assert card is not None, f"Missing {rank} card for player {player.id}"
        resp = _buy_move(client, token, game, player, card)
        data = resp.get_json()
        assert data.get('success') is True, data
        moves.append(data['battle_move'])
    return moves


class TestBuyBattleMove:
    def test_buy_call_villager_requires_jack_card(self, client, db, app, game_with_player, auth_token_bs):
        game, p1, _, _, _ = game_with_player
        card = _get_hand_card_by_rank(db, game.id, p1.id, 'J')
        assert card is not None, "No Jack card in hand"
        resp = _buy_move(client, auth_token_bs, game, p1, card)
        data = resp.get_json()
        assert data.get('success') is True
        assert data['battle_move']['family_name'] == 'Call Villager'

    def test_buy_block_requires_queen_card(self, client, db, app, game_with_player, auth_token_bs):
        game, p1, _, _, _ = game_with_player
        card = _get_hand_card_by_rank(db, game.id, p1.id, 'Q')
        assert card is not None, "No Queen card in hand"
        resp = _buy_move(client, auth_token_bs, game, p1, card)
        data = resp.get_json()
        assert data.get('success') is True
        assert data['battle_move']['family_name'] == 'Block'

    def test_buy_call_military_requires_ace_card(self, client, db, app, game_with_player, auth_token_bs):
        game, p1, _, _, _ = game_with_player
        card = _get_hand_card_by_rank(db, game.id, p1.id, 'A')
        assert card is not None, "No Ace card in hand"
        resp = _buy_move(client, auth_token_bs, game, p1, card)
        data = resp.get_json()
        assert data.get('success') is True
        assert data['battle_move']['family_name'] == 'Call Military'

    def test_buy_dagger_requires_number_card(self, client, db, app, game_with_player, auth_token_bs):
        game, p1, _, _, _ = game_with_player
        # Any number card 7-10
        for rank in ('7', '8', '9', '10'):
            card = _get_hand_card_by_rank(db, game.id, p1.id, rank)
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
        card = _get_hand_card_by_rank(db, game.id, p1.id, 'J')
        _buy_move(client, auth_token_bs, game, p1, card)
        db.session.refresh(card)
        assert card.part_of_battle_move is True

    def test_buy_move_creates_battle_move_record(self, client, db, app, game_with_player, auth_token_bs):
        from models import BattleMove
        game, p1, _, _, _ = game_with_player
        card = _get_hand_card_by_rank(db, game.id, p1.id, 'J')
        _buy_move(client, auth_token_bs, game, p1, card)
        moves = BattleMove.query.filter_by(game_id=game.id, player_id=p1.id).all()
        assert len(moves) == 1

    def test_buy_move_fails_without_auth(self, client, db, app, game_with_player):
        game, p1, _, _, _ = game_with_player
        card = _get_hand_card_by_rank(db, game.id, p1.id, 'J')
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

        # Buy two daggers with the same colour (required for combining).
        first = None
        for rank in ('7', '8', '9', '10'):
            first = _get_hand_card_by_rank(db, game.id, p1.id, rank)
            if first:
                break
        assert first is not None

        first_suit = first.suit.value if hasattr(first.suit, 'value') else str(first.suit)
        if first_suit in {'Hearts', 'Diamonds'}:
            preferred_suits = ['Hearts', 'Diamonds']
        else:
            preferred_suits = ['Clubs', 'Spades']

        second = None
        for rank in ('7', '8', '9', '10'):
            second = _get_hand_card_by_rank(
                db,
                game.id,
                p1.id,
                rank,
                exclude_ids=[first.id],
                preferred_suits=preferred_suits,
            )
            if second:
                break
        assert second is not None

        dagger_cards = [first, second]

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
        card = _get_hand_card_by_rank(db, game.id, p1.id, 'J')
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


class TestBattlePrepFlow:
    """Battle prep and battle-turn guard regression scenarios.

    Test oracle (desired outcomes):
    - First confirmation succeeds but keeps battle pending until both players confirm.
    - Second confirmation starts round 0 and sets battle turn to invader.
    - Confirmation flags are recorded for both players in battle_moves_confirmed.
    - play_battle_move rejects submissions from the non-active battle turn player.
    """

    def test_confirm_battle_moves_waits_for_both_players(
        self,
        client,
        db,
        app,
        game_with_player,
        auth_token_bs,
        auth_token_bs_p2,
    ):
        game, p1, p2, _, _ = game_with_player

        # In battle-prep phase, battle_confirmed is set while per-round turns
        # have not started yet (battle_turn_player_id remains None).
        game.battle_confirmed = True
        game.battle_turn_player_id = None
        db.session.commit()

        _buy_three_moves(client, db, auth_token_bs, game, p1)
        _buy_three_moves(client, db, auth_token_bs_p2, game, p2)

        first_confirm = client.post(
            '/battle_shop/confirm_battle_moves',
            data=json.dumps({'game_id': game.id, 'player_id': p1.id}),
            content_type='application/json',
            headers={'Authorization': f'Bearer {auth_token_bs}'},
        )
        first_data = first_confirm.get_json()
        assert first_data.get('success') is True
        assert first_data.get('both_ready') is False

        db.session.refresh(game)
        assert game.battle_turn_player_id is None

        second_confirm = client.post(
            '/battle_shop/confirm_battle_moves',
            data=json.dumps({'game_id': game.id, 'player_id': p2.id}),
            content_type='application/json',
            headers={'Authorization': f'Bearer {auth_token_bs_p2}'},
        )
        second_data = second_confirm.get_json()
        assert second_data.get('success') is True
        assert second_data.get('both_ready') is True

        db.session.refresh(game)
        assert game.battle_round == 0
        assert game.battle_turn_player_id == game.invader_player_id
        assert game.battle_moves_confirmed[str(p1.id)] is True
        assert game.battle_moves_confirmed[str(p2.id)] is True

    def test_play_battle_move_rejects_wrong_turn_player(
        self,
        client,
        db,
        app,
        game_with_player,
        auth_token_bs,
        auth_token_bs_p2,
    ):
        game, p1, p2, _, _ = game_with_player

        p1_move = _buy_three_moves(client, db, auth_token_bs, game, p1)[0]
        p2_move = _buy_three_moves(client, db, auth_token_bs_p2, game, p2)[0]
        assert p1_move is not None

        # Simulate an active battle where it's p1's battle turn.
        game.battle_confirmed = True
        game.battle_round = 0
        game.battle_turn_player_id = p1.id
        db.session.commit()

        resp = client.post(
            '/games/play_battle_move',
            data=json.dumps(
                {
                    'game_id': game.id,
                    'player_id': p2.id,
                    'battle_move_id': p2_move['id'],
                }
            ),
            content_type='application/json',
            headers={'Authorization': f'Bearer {auth_token_bs_p2}'},
        )
        data = resp.get_json()
        assert data.get('success') is False
        assert 'not your turn' in data.get('message', '').lower()

    def test_get_battle_state_hides_unplayed_opponent_moves(
        self,
        client,
        db,
        app,
        game_with_player,
        auth_token_bs,
        auth_token_bs_p2,
    ):
        from models import BattleMove

        game, p1, p2, _, _ = game_with_player

        p1_card = _get_hand_card_by_rank(db, game.id, p1.id, 'J')
        p2_card = _get_hand_card_by_rank(db, game.id, p2.id, 'Q')
        assert p1_card is not None
        assert p2_card is not None

        p1_move_resp = _buy_move(client, auth_token_bs, game, p1, p1_card)
        p2_move_resp = _buy_move(client, auth_token_bs_p2, game, p2, p2_card)
        p1_move_id = p1_move_resp.get_json()['battle_move']['id']
        p2_move_id = p2_move_resp.get_json()['battle_move']['id']

        p1_move = BattleMove.query.get(p1_move_id)
        p2_move = BattleMove.query.get(p2_move_id)
        p1_move.played_round = 0

        game.battle_confirmed = True
        game.battle_round = 0
        game.battle_turn_player_id = p2.id
        db.session.commit()

        state_resp = client.get(
            f'/games/get_battle_state?game_id={game.id}&player_id={p1.id}'
        )
        state_data = state_resp.get_json()

        assert state_data.get('success') is True
        assert state_data.get('battle_round') == 0
        assert state_data.get('battle_turn_player_id') == p2.id

        own_move = next(m for m in state_data['player_moves'] if m['id'] == p1_move_id)
        assert own_move.get('family_name') == 'Call Villager'
        assert own_move.get('played_round') == 0

        hidden_opp_move = next(m for m in state_data['opponent_moves'] if m['id'] == p2_move_id)
        assert hidden_opp_move.get('played_round') is None
        assert 'family_name' not in hidden_opp_move
        assert 'rank' not in hidden_opp_move
        assert 'value' not in hidden_opp_move

        # Once the opponent move is played, it should be revealed.
        p2_move.played_round = 0
        db.session.commit()

        revealed_resp = client.get(
            f'/games/get_battle_state?game_id={game.id}&player_id={p1.id}'
        )
        revealed_data = revealed_resp.get_json()
        revealed_opp_move = next(m for m in revealed_data['opponent_moves'] if m['id'] == p2_move_id)
        assert revealed_opp_move.get('family_name') == 'Block'
        assert revealed_opp_move.get('played_round') == 0

    def test_skip_battle_turn_advances_round_when_other_player_already_played(
        self,
        client,
        db,
        app,
        game_with_player,
        auth_token_bs,
        auth_token_bs_p2,
    ):
        from models import BattleMove

        game, p1, p2, _, _ = game_with_player

        p2_card = _get_hand_card_by_rank(db, game.id, p2.id, 'J')
        assert p2_card is not None
        p2_move = _buy_move(client, auth_token_bs_p2, game, p2, p2_card)
        p2_move_obj = BattleMove.query.get(p2_move.get_json()['battle_move']['id'])
        p2_move_obj.played_round = 0

        game.battle_confirmed = True
        game.battle_round = 0
        game.battle_turn_player_id = p1.id
        db.session.commit()

        resp = client.post(
            '/games/skip_battle_turn',
            data=json.dumps({'game_id': game.id, 'player_id': p1.id}),
            content_type='application/json',
            headers={'Authorization': f'Bearer {auth_token_bs}'},
        )
        data = resp.get_json()
        assert data.get('success') is True, data
        assert data.get('battle_round') == 1
        assert data.get('battle_turn_player_id') == game.invader_player_id
        assert 0 in data.get('battle_skipped_rounds', {}).get(str(p1.id), [])

    def test_skip_battle_turn_rejects_when_player_has_unplayed_moves(
        self,
        client,
        db,
        app,
        game_with_player,
        auth_token_bs,
    ):
        game, p1, _, _, _ = game_with_player

        p1_card = _get_hand_card_by_rank(db, game.id, p1.id, 'Q')
        assert p1_card is not None
        buy_resp = _buy_move(client, auth_token_bs, game, p1, p1_card)
        assert buy_resp.get_json().get('success') is True

        game.battle_confirmed = True
        game.battle_round = 0
        game.battle_turn_player_id = p1.id
        db.session.commit()

        resp = client.post(
            '/games/skip_battle_turn',
            data=json.dumps({'game_id': game.id, 'player_id': p1.id}),
            content_type='application/json',
            headers={'Authorization': f'Bearer {auth_token_bs}'},
        )
        data = resp.get_json()
        assert data.get('success') is False
        assert 'must play a battle move' in data.get('message', '').lower()
