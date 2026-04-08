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
        game = Game.query.get(created_game['id'])
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
        game = Game.query.get(created_game['id'])
        winner_player = game.players[0]
        winner_user = User.query.get(winner_player.user_id)
        gold_before = winner_user.gold
        winner_player.points = game.stake
        db.session.commit()
        _check_game_over(game)
        db.session.refresh(winner_user)
        assert winner_user.gold == gold_before + game.stake * 2

    def test_checkmate_triggers_game_over(self, app, db, created_game):
        from models import Figure, Game
        from routes.games import _check_checkmate_loss
        game = Game.query.get(created_game['id'])
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
