# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Deterministic end-to-end game-flow regression test.

This test intentionally drives a long real-server flow:
1. Challenge + game creation
2. Counterable spell pending/allow cycle
3. Advance + counter-advance
4. Battle prep handshake
5. 3-round battle move sequence
6. Battle resolution + winner card pick + game over

Test oracle (desired outcomes):
- Counterable spell creation enters pending state and returns a pending spell id.
- While a spell is pending, casting another spell is blocked.
- Allowing the pending spell clears pending-spell state fields on the game.
- Advance + counter-advance establish advancing/defending figures and expected turn state.
- Dual battle decisions transition into battle prep state with reset prep fields.
- Both players must confirm battle moves before battle rounds start.
- Scripted 3-round move playback succeeds for all six move submissions.
- Battle finish returns invader win and marks game_over_pending for winner card pick.
- Winner card pick finalizes game over and transfers picked card ownership to winner.
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


class TestFullGameFlow:
    def test_full_match_from_pending_spell_to_game_over(
        self,
        client,
        db,
        two_users,
        auth_headers_user1,
        auth_headers_user2,
    ):
        from models import Challenge, Figure, Game, MainCard, Player, SideCard

        u1, u2 = two_users

        # Create challenge + game.
        create_challenge = client.post(
            '/challenges/create_challenge',
            data={
                'challenger': u1.username,
                'opponent': u2.username,
                'stake': '10',
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

        game_id = create_data['game']['id']
        game = db.session.get(Game, game_id)
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

        # 1) Counterable spell lifecycle: cast -> pending lock -> allow.
        cast_pending = client.post(
            '/spells/cast_spell',
            json={
                'player_id': invader.id,
                'game_id': game_id,
                'spell_name': 'Poison',
                'spell_type': 'enchantment',
                'spell_family_name': 'Poison',
                'suit': 'Clubs',
                'cards': [],
                'counterable': True,
                'possible_during_ceasefire': True,
            },
            headers=invader_headers,
        )
        cast_pending_data = cast_pending.get_json()
        assert cast_pending_data.get('success') is True, cast_pending_data
        pending_spell_id = cast_pending_data.get('spell_id')
        assert pending_spell_id is not None

        blocked_while_pending = client.post(
            '/spells/cast_spell',
            json={
                'player_id': invader.id,
                'game_id': game_id,
                'spell_name': 'Draw 2 MainCards',
                'spell_type': 'greed',
                'spell_family_name': 'Draw 2 MainCards',
                'suit': 'Hearts',
                'cards': [],
                'counterable': False,
                'possible_during_ceasefire': True,
            },
            headers=invader_headers,
        )
        blocked_data = blocked_while_pending.get_json()
        assert blocked_data.get('success') is False
        assert 'pending' in blocked_data.get('message', '').lower()

        allow_pending = client.post(
            '/spells/allow_spell',
            json={
                'player_id': defender.id,
                'game_id': game_id,
                'pending_spell_id': pending_spell_id,
            },
            headers=defender_headers,
        )
        allow_data = allow_pending.get_json()
        assert allow_data.get('success') is True, allow_data

        db.session.refresh(game)
        assert game.pending_spell_id is None
        assert game.waiting_for_counter_player_id is None

        # Force deterministic battle setup preconditions.
        game.ceasefire_active = False
        game.ceasefire_start_turn = None
        game.turn_player_id = invader.id
        invader.turns_left = 6
        defender.turns_left = 6
        db.session.commit()

        invader_figure = Figure.query.filter_by(
            game_id=game_id,
            player_id=invader.id,
            checkmate=True,
        ).first()
        defender_figure = Figure.query.filter_by(
            game_id=game_id,
            player_id=defender.id,
            checkmate=True,
        ).first()
        assert invader_figure is not None
        assert defender_figure is not None

        # 2) Advance + counter-advance.
        advance = client.post(
            '/games/advance_figure',
            json={
                'game_id': game_id,
                'player_id': invader.id,
                'figure_id': invader_figure.id,
            },
            headers=invader_headers,
        )
        advance_data = advance.get_json()
        assert advance_data.get('success') is True, advance_data
        assert advance_data.get('is_counter_advance') is False

        counter_advance = client.post(
            '/games/advance_figure',
            json={
                'game_id': game_id,
                'player_id': defender.id,
                'figure_id': defender_figure.id,
            },
            headers=defender_headers,
        )
        counter_data = counter_advance.get_json()
        assert counter_data.get('success') is True, counter_data
        assert counter_data.get('is_counter_advance') is True

        db.session.refresh(game)
        assert game.advancing_figure_id == invader_figure.id
        assert game.defending_figure_id == defender_figure.id
        assert game.turn_player_id == invader.id

        # 3) Battle decision handshake.
        invader_decision = client.post(
            '/games/battle_decision',
            json={
                'game_id': game_id,
                'player_id': invader.id,
                'decision': 'battle',
            },
            headers=invader_headers,
        )
        invader_decision_data = invader_decision.get_json()
        assert invader_decision_data.get('success') is True
        assert invader_decision_data.get('waiting') is True

        defender_decision = client.post(
            '/games/battle_decision',
            json={
                'game_id': game_id,
                'player_id': defender.id,
                'decision': 'battle',
            },
            headers=defender_headers,
        )
        defender_decision_data = defender_decision.get_json()
        assert defender_decision_data.get('success') is True
        assert defender_decision_data.get('resolved') is True
        assert defender_decision_data.get('outcome') == 'battle'

        db.session.refresh(game)
        assert game.battle_confirmed is True
        assert game.battle_turn_player_id is None
        assert game.battle_moves_confirmed is None

        # 4) Deterministic battle move purchases.
        invader_ranks = ['10', '10', '9']
        defender_ranks = ['7', '7', '8']

        invader_move_ids = []
        used_ids = []
        for rank in invader_ranks:
            card = _prepare_main_card_for_player(
                db,
                game_id,
                invader.id,
                rank,
                exclude_ids=used_ids,
            )
            assert card is not None, f'Missing invader card rank {rank}'
            used_ids.append(card.id)

            buy = client.post(
                '/battle_shop/buy_battle_move',
                json={
                    'game_id': game_id,
                    'player_id': invader.id,
                    'family_name': _rank_to_family(_rank_value(card)),
                    'card_id': card.id,
                    'card_type': 'main',
                    'suit': _suit_value(card),
                    'rank': _rank_value(card),
                    'value': card.value,
                },
                headers=invader_headers,
            )
            buy_data = buy.get_json()
            assert buy_data.get('success') is True, buy_data
            invader_move_ids.append(buy_data['battle_move']['id'])

        defender_move_ids = []
        used_ids = []
        for rank in defender_ranks:
            card = _prepare_main_card_for_player(
                db,
                game_id,
                defender.id,
                rank,
                exclude_ids=used_ids,
            )
            assert card is not None, f'Missing defender card rank {rank}'
            used_ids.append(card.id)

            buy = client.post(
                '/battle_shop/buy_battle_move',
                json={
                    'game_id': game_id,
                    'player_id': defender.id,
                    'family_name': _rank_to_family(_rank_value(card)),
                    'card_id': card.id,
                    'card_type': 'main',
                    'suit': _suit_value(card),
                    'rank': _rank_value(card),
                    'value': card.value,
                },
                headers=defender_headers,
            )
            buy_data = buy.get_json()
            assert buy_data.get('success') is True, buy_data
            defender_move_ids.append(buy_data['battle_move']['id'])

        confirm_invader = client.post(
            '/battle_shop/confirm_battle_moves',
            json={'game_id': game_id, 'player_id': invader.id},
            headers=invader_headers,
        )
        confirm_invader_data = confirm_invader.get_json()
        assert confirm_invader_data.get('success') is True
        assert confirm_invader_data.get('both_ready') is False

        confirm_defender = client.post(
            '/battle_shop/confirm_battle_moves',
            json={'game_id': game_id, 'player_id': defender.id},
            headers=defender_headers,
        )
        confirm_defender_data = confirm_defender.get_json()
        assert confirm_defender_data.get('success') is True
        assert confirm_defender_data.get('both_ready') is True

        db.session.refresh(game)
        assert game.battle_turn_player_id == invader.id
        assert game.battle_round == 0

        # 5) Play all 3 rounds (invader starts each round).
        play_sequence = [
            (invader.id, invader_headers, invader_move_ids[0]),
            (defender.id, defender_headers, defender_move_ids[0]),
            (invader.id, invader_headers, invader_move_ids[1]),
            (defender.id, defender_headers, defender_move_ids[1]),
            (invader.id, invader_headers, invader_move_ids[2]),
            (defender.id, defender_headers, defender_move_ids[2]),
        ]

        for player_id, headers, move_id in play_sequence:
            play = client.post(
                '/games/play_battle_move',
                json={
                    'game_id': game_id,
                    'player_id': player_id,
                    'battle_move_id': move_id,
                },
                headers=headers,
            )
            play_data = play.get_json()
            assert play_data.get('success') is True, play_data

        # 6) Finish battle and pick loot card.
        finish_battle = client.post(
            '/games/finish_battle',
            json={
                'game_id': game_id,
                'player_id': invader.id,
                'total_diff': 0,
            },
            headers=invader_headers,
        )
        finish_data = finish_battle.get_json()
        assert finish_data.get('success') is True, finish_data
        assert finish_data.get('outcome') == 'win', finish_data
        assert finish_data.get('winner_player_id') == invader.id
        assert finish_data.get('game_over_pending') is True

        returnable_cards = finish_data.get('returnable_cards', [])
        assert returnable_cards, 'Expected returnable cards after battle win'
        picked_card = returnable_cards[0]

        pick_card = client.post(
            '/games/finish_battle_pick_card',
            json={
                'game_id': game_id,
                'player_id': invader.id,
                'picked_card_id': picked_card['id'],
                'picked_card_type': picked_card['card_type'],
            },
            headers=invader_headers,
        )
        pick_data = pick_card.get_json()
        assert pick_data.get('success') is True, pick_data
        assert pick_data.get('game_over'), pick_data
        assert pick_data['game_over'].get('winner_player_id') == invader.id
        assert pick_data['game_over'].get('reason') == 'checkmate'

        # Rewards from the (checkmate-triggered) _finalize_game_over call
        # made earlier in finish_battle must survive into the pick_card
        # response — otherwise the client's spoils-of-war dialogue shows no
        # loot. winner_rewards is a dict with keys main_booster, side_booster,
        # map, gold (counts/amounts depend on the random draws). The
        # Winner gets at least one scaled reward draw, so at least one entry
        # must be non-zero.
        winner_rewards = pick_data['game_over'].get('winner_rewards')
        assert isinstance(winner_rewards, dict), pick_data['game_over']
        assert sum(int(v or 0) for v in winner_rewards.values()) > 0, winner_rewards

        db.session.refresh(game)
        assert game.state == 'finished'
        assert game.winner_player_id == invader.id

        # Winner should own the picked loot card.
        if picked_card['card_type'] == 'side':
            owned_card = db.session.get(SideCard, picked_card['id'])
        else:
            owned_card = db.session.get(MainCard, picked_card['id'])
        assert owned_card is not None
        assert owned_card.player_id == invader.id
        assert owned_card.in_deck is False