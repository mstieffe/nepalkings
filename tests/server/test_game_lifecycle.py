# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for game lifecycle: creation, turns, end conditions."""
import pytest


# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def two_users_with_challenge(client, db, two_users, auth_headers_user1):
    """Create two users and an open challenge between them."""
    from models import Challenge, ChallengeStatus
    u1, u2 = two_users
    resp = client.post('/challenges/create_challenge', data={
        'challenger': u1.username,
        'opponent': u2.username,
        'stake': '10',
    }, headers=auth_headers_user1)
    assert resp.get_json()['success'] is True
    challenge = Challenge.query.first()
    return u1, u2, challenge


@pytest.fixture
def created_game(client, db, two_users_with_challenge, auth_headers_user1):
    """Create a game from a challenge and return (game_data, player1_data, player2_data)."""
    u1, u2, challenge = two_users_with_challenge
    resp = client.post('/games/create_game', data={
        'challenge_id': str(challenge.id),
    }, headers=auth_headers_user1)
    data = resp.get_json()
    assert data['success'] is True, data.get('message')
    return data['game']


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCreateGame:
    def test_create_game_from_challenge(self, client, created_game):
        assert created_game['id'] is not None
        assert created_game['state'] == 'open'

    def test_create_game_initializes_deck(self, app, db, created_game):
        from models import MainCard, SideCard
        game_id = created_game['id']
        main_count = MainCard.query.filter_by(game_id=game_id).count()
        side_count = SideCard.query.filter_by(game_id=game_id).count()
        assert main_count == 64
        assert side_count == 40

    def test_create_game_deals_initial_cards(self, app, db, created_game):
        """Each player should have their starting hand."""
        from models import MainCard
        import server_settings as settings
        game_id = created_game['id']
        players = created_game['players']
        for p in players:
            # The main hand size includes the maharaja card + dealt cards
            hand = MainCard.query.filter_by(
                player_id=p['id'], in_deck=False
            ).count()
            assert hand >= 1  # At least the maharaja card

    def test_create_game_sets_first_turn(self, app, db, created_game):
        """Game must have a designated invader/turn player."""
        assert created_game['invader_player_id'] is not None
        assert created_game['turn_player_id'] is not None

    def test_create_game_deducts_gold_from_both_players(self, app, db, two_users_with_challenge, client, auth_headers_user1):
        from models import User
        u1, u2, challenge = two_users_with_challenge
        gold_before_u1 = u1.gold
        gold_before_u2 = u2.gold
        client.post('/games/create_game', data={
            'challenge_id': str(challenge.id),
        }, headers=auth_headers_user1)
        db.session.refresh(u1)
        db.session.refresh(u2)
        assert u1.gold == gold_before_u1 - challenge.stake
        assert u2.gold == gold_before_u2 - challenge.stake

    def test_create_game_marks_challenge_accepted(self, app, db, two_users_with_challenge, client, auth_headers_user1):
        from models import Challenge, ChallengeStatus
        u1, u2, challenge = two_users_with_challenge
        client.post('/games/create_game', data={
            'challenge_id': str(challenge.id),
        }, headers=auth_headers_user1)
        db.session.refresh(challenge)
        assert challenge.status.value == 'accepted'

    def test_create_game_creates_maharaja_figures(self, app, db, created_game):
        """Both players start with a Maharaja castle figure."""
        from models import Figure
        game_id = created_game['id']
        maharajas = Figure.query.filter(
            Figure.game_id == game_id,
            Figure.name.in_(['Himalaya Maharaja', 'Djungle Maharaja'])
        ).all()
        assert len(maharajas) == 2

    def test_create_game_fails_with_invalid_challenge(self, client, two_users, auth_headers_user1):
        resp = client.post('/games/create_game', data={
            'challenge_id': '9999',
        }, headers=auth_headers_user1)
        data = resp.get_json()
        assert data['success'] is False


class TestGameState:
    def test_game_state_serialization(self, app, db, created_game):
        """Verify all expected fields are present in the serialized game."""
        required_fields = [
            'id', 'state', 'stake', 'current_round', 'invader_player_id',
            'turn_player_id', 'ceasefire_active', 'players',
        ]
        for field in required_fields:
            assert field in created_game, f"Missing field: {field}"

    def test_game_round_counter_starts_at_1(self, app, db, created_game):
        assert created_game['current_round'] == 1

    def test_game_ceasefire_starts_active(self, app, db, created_game):
        assert created_game['ceasefire_active'] is True


class TestGameOver:
    def test_game_over_on_stake(self, app, db, created_game):
        """Manually set a player to points >= stake and verify check_game_over triggers."""
        from models import Player, Game
        from routes.games import _check_game_over
        game = db.session.get(Game, created_game['id'])
        player = game.players[0]
        player.points = game.stake
        db.session.commit()
        result = _check_game_over(game)
        assert result is not None
        assert result['game_over'] is True
        assert result['winner_player_id'] == player.id

    def test_game_over_awards_gold_to_winner(self, app, db, created_game):
        from models import Player, Game, User
        from routes.games import _check_game_over
        game = db.session.get(Game, created_game['id'])
        winner_player = game.players[0]
        winner_user = db.session.get(User, winner_player.user_id)
        gold_before = winner_user.gold
        winner_player.points = game.stake
        db.session.commit()
        _check_game_over(game)
        db.session.commit()
        db.session.refresh(winner_user)
        assert winner_user.gold == gold_before + game.stake * 2

    def test_checkmate_triggers_game_over(self, app, db, created_game):
        from models import Figure, Game
        from routes.games import _check_checkmate_loss
        game = db.session.get(Game, created_game['id'])
        # Find the Himalaya Maharaja (checkmate=True)
        checkmate_fig = Figure.query.filter_by(
            game_id=game.id, checkmate=True
        ).first()
        assert checkmate_fig is not None
        result = _check_checkmate_loss(game, checkmate_fig)
        assert result is not None
        assert result['game_over'] is True
        # The owner of the destroyed figure should be the loser
        assert result['loser_player_id'] == checkmate_fig.player_id


class TestGameResultsRoute:
    def test_game_results_returns_finished_game_stats(self, client, db, created_game):
        from models import Game, User
        from routes.games import _check_game_over

        game = db.session.get(Game, created_game['id'])
        winner_player = game.players[0]
        winner_player.points = game.stake
        db.session.commit()

        result = _check_game_over(game)
        assert result is not None
        db.session.commit()

        winner_user = db.session.get(User, winner_player.user_id)
        resp = client.get(f'/games/game_results?username={winner_user.username}')
        data = resp.get_json()

        assert data.get('success') is True, data
        assert data.get('wins', 0) >= 1
        assert any(r.get('game_id') == game.id for r in data.get('results', []))

    def test_game_results_returns_404_for_unknown_user(self, client):
        resp = client.get('/games/game_results?username=unknown_player')
        data = resp.get_json()

        assert resp.status_code == 404
        assert data.get('success') is False


class TestGameRouteCoverage:
    def test_get_games_lists_games_for_username(self, client, created_game, two_users):
        u1, _ = two_users

        resp = client.get(f'/games/get_games?username={u1.username}')
        data = resp.get_json()

        assert resp.status_code == 200
        assert any(g.get('id') == created_game['id'] for g in data.get('games', []))

    def test_get_game_returns_serialized_game(self, client, created_game):
        resp = client.get(f"/games/get_game?game_id={created_game['id']}")
        data = resp.get_json()

        assert resp.status_code == 200
        assert data.get('game', {}).get('id') == created_game['id']

    def test_get_hand_returns_players_main_and_side_cards(self, client, db, created_game, two_users):
        from models import Player

        u1, _ = two_users
        player = Player.query.filter_by(game_id=created_game['id'], user_id=u1.id).first()
        assert player is not None

        resp = client.get(f'/games/get_hand?player_id={player.id}')
        data = resp.get_json()

        assert resp.status_code == 200
        assert data.get('success') is True
        assert isinstance(data.get('main_hand', []), list)
        assert isinstance(data.get('side_hand', []), list)

    def test_update_points_route_increments_points(self, client, db, created_game, two_users, auth_headers_user1):
        from models import Player

        u1, _ = two_users
        player = Player.query.filter_by(game_id=created_game['id'], user_id=u1.id).first()
        assert player is not None
        points_before = player.points

        resp = client.post(
            '/games/update_points',
            json={'player_id': player.id, 'points': 5},
            headers=auth_headers_user1,
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data.get('success') is True
        assert data.get('points') == points_before + 5

    def test_draw_and_return_cards_routes(self, client, db, created_game, two_users, auth_headers_user1):
        from models import Player, SideCard

        u1, _ = two_users
        player = Player.query.filter_by(game_id=created_game['id'], user_id=u1.id).first()
        assert player is not None

        draw_resp = client.post(
            '/games/draw_cards',
            data={
                'game_id': str(created_game['id']),
                'player_id': str(player.id),
                'card_type': 'side',
                'num_cards': '1',
            },
            headers=auth_headers_user1,
        )
        draw_data = draw_resp.get_json()
        assert draw_data.get('success') is True, draw_data
        assert len(draw_data.get('cards', [])) == 1

        drawn_id = draw_data['cards'][0]['id']
        return_resp = client.post(
            '/games/return_cards',
            data={
                'card_ids': [str(drawn_id)],
                'card_type': 'side',
            },
            headers=auth_headers_user1,
        )
        return_data = return_resp.get_json()
        assert return_data.get('success') is True, return_data

        card = db.session.get(SideCard, drawn_id)
        assert card is not None
        assert card.in_deck is True

    def test_change_cards_route_draws_replacements_and_decrements_turns(
        self,
        client,
        db,
        created_game,
        two_users,
        auth_headers_user1,
    ):
        from models import Game, MainCard, Player

        u1, _ = two_users
        player = Player.query.filter_by(game_id=created_game['id'], user_id=u1.id).first()
        game = db.session.get(Game, created_game['id'])
        assert player is not None
        assert game is not None

        card = MainCard.query.filter_by(
            game_id=game.id,
            player_id=player.id,
            in_deck=False,
            part_of_figure=False,
            part_of_battle_move=False,
        ).first()
        assert card is not None

        game.turn_player_id = player.id
        player.turns_left = 3
        db.session.commit()

        resp = client.post(
            '/games/change_cards',
            json={
                'game_id': game.id,
                'player_id': player.id,
                'cards': [{'id': card.id}],
                'card_type': 'main',
            },
            headers=auth_headers_user1,
        )
        data = resp.get_json()

        assert data.get('success') is True, data
        assert len(data.get('new_cards', [])) == 1
        assert data.get('turns_left') == 2

    def test_discard_cards_route_returns_selected_cards_to_deck(
        self,
        client,
        db,
        created_game,
        two_users,
        auth_headers_user1,
    ):
        from models import MainCard, Player

        u1, _ = two_users
        player = Player.query.filter_by(game_id=created_game['id'], user_id=u1.id).first()
        assert player is not None

        card = MainCard.query.filter_by(
            game_id=created_game['id'],
            player_id=player.id,
            in_deck=False,
            part_of_figure=False,
            part_of_battle_move=False,
        ).first()
        assert card is not None

        rank_val = card.rank.value if hasattr(card.rank, 'value') else str(card.rank)

        resp = client.post(
            '/games/discard_cards',
            json={
                'game_id': created_game['id'],
                'player_id': player.id,
                'cards': [{'id': card.id, 'rank': rank_val}],
                'card_type': 'main',
            },
            headers=auth_headers_user1,
        )
        data = resp.get_json()

        assert data.get('success') is True, data
        db.session.refresh(card)
        assert card.in_deck is True

    def test_delete_game_route_removes_game(self, client, db, created_game, auth_headers_user1):
        from models import Game

        resp = client.post(
            '/games/delete_game',
            data={'game_id': str(created_game['id'])},
            headers=auth_headers_user1,
        )
        data = resp.get_json()

        assert data.get('success') is True, data
        assert db.session.get(Game, created_game['id']) is None

    def test_start_turn_route_returns_turn_payload(
        self,
        client,
        db,
        created_game,
        two_users,
        auth_headers_user1,
    ):
        from models import Game, Player

        u1, _ = two_users
        game = db.session.get(Game, created_game['id'])
        player = Player.query.filter_by(game_id=game.id, user_id=u1.id).first()
        assert game is not None
        assert player is not None

        game.turn_player_id = player.id
        db.session.commit()

        resp = client.post(
            '/games/start_turn',
            json={'game_id': game.id, 'player_id': player.id},
            headers=auth_headers_user1,
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data.get('success') is True, data

    def test_select_defender_sets_defending_figure(
        self,
        client,
        db,
        created_game,
        two_users,
        auth_headers_user1,
    ):
        from models import Figure, Game, Player

        u1, u2 = two_users
        game = db.session.get(Game, created_game['id'])
        p1 = Player.query.filter_by(game_id=game.id, user_id=u1.id).first()
        p2 = Player.query.filter_by(game_id=game.id, user_id=u2.id).first()
        assert game is not None
        assert p1 is not None
        assert p2 is not None

        attacker_figure = Figure.query.filter_by(game_id=game.id, player_id=p1.id).first()
        defender_figure = Figure.query.filter_by(game_id=game.id, player_id=p2.id).first()
        assert attacker_figure is not None
        assert defender_figure is not None

        game.advancing_figure_id = attacker_figure.id
        game.advancing_player_id = p1.id
        game.turn_player_id = p1.id
        db.session.commit()

        resp = client.post(
            '/games/select_defender',
            json={'game_id': game.id, 'player_id': p1.id, 'figure_id': defender_figure.id},
            headers=auth_headers_user1,
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data.get('success') is True, data
        assert data.get('game', {}).get('defending_figure_id') == defender_figure.id

    def test_select_defender_requires_must_be_attacked_without_blitzkrieg(
        self,
        client,
        db,
        created_game,
        two_users,
        auth_headers_user1,
    ):
        from models import Figure, Game, Player

        u1, u2 = two_users
        game = db.session.get(Game, created_game['id'])
        p1 = Player.query.filter_by(game_id=game.id, user_id=u1.id).first()
        p2 = Player.query.filter_by(game_id=game.id, user_id=u2.id).first()
        attacker_figure = Figure.query.filter_by(game_id=game.id, player_id=p1.id).first()
        fortress = Figure(
            game_id=game.id,
            player_id=p2.id,
            family_name='Wooden Fortress',
            field='military',
            color='defensive',
            name='Wooden Fortress',
            suit='Spades',
        )
        normal_defender = Figure(
            game_id=game.id,
            player_id=p2.id,
            family_name='Rice Farmer',
            field='village',
            color='offensive',
            name='Rice Farmer',
            suit='Hearts',
        )
        db.session.add_all([fortress, normal_defender])
        db.session.flush()
        game.mode = 'conquer'
        game.advancing_figure_id = attacker_figure.id
        game.advancing_player_id = p1.id
        game.turn_player_id = p1.id
        db.session.commit()

        resp = client.post(
            '/games/select_defender',
            json={'game_id': game.id, 'player_id': p1.id, 'figure_id': normal_defender.id},
            headers=auth_headers_user1,
        )
        data = resp.get_json()

        assert resp.status_code == 400
        assert data.get('reason') == 'must_be_attacked'

    def test_select_defender_blitzkrieg_can_ignore_must_be_attacked_fortress(
        self,
        client,
        db,
        created_game,
        two_users,
        auth_headers_user1,
    ):
        from models import Figure, Game, Player

        u1, u2 = two_users
        game = db.session.get(Game, created_game['id'])
        p1 = Player.query.filter_by(game_id=game.id, user_id=u1.id).first()
        p2 = Player.query.filter_by(game_id=game.id, user_id=u2.id).first()
        attacker_figure = Figure.query.filter_by(game_id=game.id, player_id=p1.id).first()
        fortress = Figure(
            game_id=game.id,
            player_id=p2.id,
            family_name='Wooden Fortress',
            field='military',
            color='defensive',
            name='Wooden Fortress',
            suit='Spades',
        )
        normal_defender = Figure(
            game_id=game.id,
            player_id=p2.id,
            family_name='Rice Farmer',
            field='village',
            color='offensive',
            name='Rice Farmer',
            suit='Hearts',
        )
        db.session.add_all([fortress, normal_defender])
        db.session.flush()
        game.mode = 'conquer'
        game.advancing_figure_id = attacker_figure.id
        game.advancing_player_id = p1.id
        game.turn_player_id = p1.id
        game.battle_modifier = [{'type': 'Blitzkrieg', 'caster_id': p1.id}]
        db.session.commit()

        resp = client.post(
            '/games/select_defender',
            json={'game_id': game.id, 'player_id': p1.id, 'figure_id': normal_defender.id},
            headers=auth_headers_user1,
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data.get('success') is True, data
        assert data.get('game', {}).get('defending_figure_id') == normal_defender.id

    def test_select_defender_blitzkrieg_still_rejects_cannot_be_targeted(
        self,
        client,
        db,
        created_game,
        two_users,
        auth_headers_user1,
    ):
        from models import Figure, Game, Player

        u1, u2 = two_users
        game = db.session.get(Game, created_game['id'])
        p1 = Player.query.filter_by(game_id=game.id, user_id=u1.id).first()
        p2 = Player.query.filter_by(game_id=game.id, user_id=u2.id).first()
        attacker_figure = Figure.query.filter_by(game_id=game.id, player_id=p1.id).first()
        wall = Figure(
            game_id=game.id,
            player_id=p2.id,
            family_name='Wall',
            field='military',
            color='defensive',
            name='Wall',
            suit='Clubs',
        )
        db.session.add(wall)
        db.session.flush()
        game.mode = 'conquer'
        game.advancing_figure_id = attacker_figure.id
        game.advancing_player_id = p1.id
        game.turn_player_id = p1.id
        game.battle_modifier = [{'type': 'Blitzkrieg', 'caster_id': p1.id}]
        db.session.commit()

        resp = client.post(
            '/games/select_defender',
            json={'game_id': game.id, 'player_id': p1.id, 'figure_id': wall.id},
            headers=auth_headers_user1,
        )
        data = resp.get_json()

        assert resp.status_code == 400
        assert 'cannot be selected' in data.get('message', '')

    def test_select_defender_cannot_be_blocked_can_ignore_must_be_attacked_fortress(
        self,
        client,
        db,
        created_game,
        two_users,
        auth_headers_user1,
    ):
        """Cavalry (cannot_be_blocked) advance bypasses must_be_attacked, like Blitzkrieg."""
        from models import Figure, Game, Player

        u1, u2 = two_users
        game = db.session.get(Game, created_game['id'])
        p1 = Player.query.filter_by(game_id=game.id, user_id=u1.id).first()
        p2 = Player.query.filter_by(game_id=game.id, user_id=u2.id).first()
        cavalry = Figure(
            game_id=game.id,
            player_id=p1.id,
            family_name='Cavalry',
            field='military',
            color='offensive',
            name='Cavalry',
            suit='Hearts',
            cannot_be_blocked=True,
        )
        fortress = Figure(
            game_id=game.id,
            player_id=p2.id,
            family_name='Wooden Fortress',
            field='military',
            color='defensive',
            name='Wooden Fortress',
            suit='Spades',
        )
        normal_defender = Figure(
            game_id=game.id,
            player_id=p2.id,
            family_name='Rice Farmer',
            field='village',
            color='offensive',
            name='Rice Farmer',
            suit='Hearts',
        )
        db.session.add_all([cavalry, fortress, normal_defender])
        db.session.flush()
        game.mode = 'conquer'
        game.advancing_figure_id = cavalry.id
        game.advancing_player_id = p1.id
        game.turn_player_id = p1.id
        db.session.commit()

        resp = client.post(
            '/games/select_defender',
            json={'game_id': game.id, 'player_id': p1.id, 'figure_id': normal_defender.id},
            headers=auth_headers_user1,
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data.get('success') is True, data
        assert data.get('game', {}).get('defending_figure_id') == normal_defender.id

    def test_advance_figure_cannot_be_blocked_clears_preselected_defender_in_conquer(
        self,
        client,
        db,
        created_game,
        two_users,
        auth_headers_user1,
    ):
        """Cavalry advance in conquer mode clears the preselected defender and
        keeps turn on invader so they can pick freely (mirrors Blitzkrieg)."""
        from models import Figure, Game, Player

        u1, u2 = two_users
        game = db.session.get(Game, created_game['id'])
        p1 = Player.query.filter_by(game_id=game.id, user_id=u1.id).first()
        p2 = Player.query.filter_by(game_id=game.id, user_id=u2.id).first()
        cavalry = Figure(
            game_id=game.id,
            player_id=p1.id,
            family_name='Cavalry',
            field='military',
            color='offensive',
            name='Cavalry',
            suit='Hearts',
            cannot_be_blocked=True,
        )
        preselected_defender = Figure(
            game_id=game.id,
            player_id=p2.id,
            family_name='Rice Farmer',
            field='village',
            color='offensive',
            name='Rice Farmer',
            suit='Hearts',
        )
        db.session.add_all([cavalry, preselected_defender])
        db.session.flush()
        game.mode = 'conquer'
        game.invader_player_id = p1.id
        game.turn_player_id = p1.id
        game.defending_figure_id = preselected_defender.id
        game.ceasefire_active = False
        p1.turns_left = 1
        p2.turns_left = 0
        db.session.commit()

        resp = client.post(
            '/games/advance_figure',
            json={'game_id': game.id, 'player_id': p1.id, 'figure_id': cavalry.id},
            headers=auth_headers_user1,
        )
        data = resp.get_json()

        assert resp.status_code == 200, data
        assert data.get('success') is True, data
        db.session.refresh(game)
        assert game.advancing_figure_id == cavalry.id
        assert game.defending_figure_id is None
        assert game.defending_figure_id_2 is None
        assert game.turn_player_id == p1.id

    def test_skip_civil_war_second_flips_turn_for_advance_context(
        self,
        client,
        db,
        created_game,
        two_users,
        auth_headers_user1,
    ):
        from models import Game, Player

        u1, u2 = two_users
        game = db.session.get(Game, created_game['id'])
        p1 = Player.query.filter_by(game_id=game.id, user_id=u1.id).first()
        p2 = Player.query.filter_by(game_id=game.id, user_id=u2.id).first()
        assert game is not None
        assert p1 is not None
        assert p2 is not None

        game.turn_player_id = p1.id
        db.session.commit()

        resp = client.post(
            '/games/skip_civil_war_second',
            json={'game_id': game.id, 'player_id': p1.id, 'context': 'advance'},
            headers=auth_headers_user1,
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data.get('success') is True, data
        assert data.get('game', {}).get('turn_player_id') == p2.id

    def test_cannot_advance_loss_awards_points_to_opponent(
        self,
        client,
        db,
        created_game,
        two_users,
        auth_headers_user1,
    ):
        from models import Game, Player

        u1, u2 = two_users
        game = db.session.get(Game, created_game['id'])
        p1 = Player.query.filter_by(game_id=game.id, user_id=u1.id).first()
        p2 = Player.query.filter_by(game_id=game.id, user_id=u2.id).first()
        assert game is not None
        assert p1 is not None
        assert p2 is not None

        game.turn_player_id = p1.id
        game.stake = 99
        points_before = p2.points
        db.session.commit()

        resp = client.post(
            '/games/cannot_advance_loss',
            json={'game_id': game.id, 'player_id': p1.id},
            headers=auth_headers_user1,
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data.get('success') is True, data
        db.session.refresh(p2)
        assert p2.points == points_before + 10

    def test_defender_no_figures_loss_awards_points_to_invader(
        self,
        client,
        db,
        created_game,
        two_users,
        auth_headers_user1,
    ):
        from models import Game, Player

        u1, u2 = two_users
        game = db.session.get(Game, created_game['id'])
        p1 = Player.query.filter_by(game_id=game.id, user_id=u1.id).first()
        p2 = Player.query.filter_by(game_id=game.id, user_id=u2.id).first()
        assert game is not None
        assert p1 is not None
        assert p2 is not None

        game.turn_player_id = p1.id
        game.advancing_player_id = p1.id
        game.stake = 99
        points_before = p1.points
        db.session.commit()

        resp = client.post(
            '/games/defender_no_figures_loss',
            json={'game_id': game.id, 'player_id': p1.id},
            headers=auth_headers_user1,
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data.get('success') is True, data
        db.session.refresh(p1)
        assert p1.points == points_before + 10
