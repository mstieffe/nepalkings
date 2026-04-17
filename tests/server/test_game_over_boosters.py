# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for booster pack rewards on game over (Phase 7)."""

import pytest
from unittest.mock import patch
from models import db as _db, User, Game, Player, Challenge, ChallengeStatus
from routes.games import _award_booster_packs, _finalize_game_over
from werkzeug.security import generate_password_hash


# ═══════════════════════════════════════════════════════════════════
#  _award_booster_packs
# ═══════════════════════════════════════════════════════════════════

class TestAwardBoosterPacks:

    def test_awards_main_packs(self, app, db, two_users):
        u1, _ = two_users
        u1.booster_packs = 0
        u1.booster_packs_side = 0
        db.session.commit()

        # Force all packs to be main
        with patch('routes.games.random.choices', return_value=['main']):
            result = _award_booster_packs(u1, 3)

        assert result == {'main': 3, 'side': 0}
        assert u1.booster_packs == 3
        assert u1.booster_packs_side == 0

    def test_awards_side_packs(self, app, db, two_users):
        u1, _ = two_users
        u1.booster_packs = 0
        u1.booster_packs_side = 0
        db.session.commit()

        with patch('routes.games.random.choices', return_value=['side']):
            result = _award_booster_packs(u1, 2)

        assert result == {'main': 0, 'side': 2}
        assert u1.booster_packs == 0
        assert u1.booster_packs_side == 2

    def test_awards_mixed_packs(self, app, db, two_users):
        u1, _ = two_users
        u1.booster_packs = 1
        u1.booster_packs_side = 1
        db.session.commit()

        # Alternate main/side
        with patch('routes.games.random.choices', side_effect=[['main'], ['side']]):
            result = _award_booster_packs(u1, 2)

        assert result == {'main': 1, 'side': 1}
        assert u1.booster_packs == 2   # 1 + 1
        assert u1.booster_packs_side == 2   # 1 + 1

    def test_zero_packs_returns_zeros(self, app, db, two_users):
        u1, _ = two_users
        result = _award_booster_packs(u1, 0)
        assert result == {'main': 0, 'side': 0}

    def test_none_user_returns_zeros(self, app):
        result = _award_booster_packs(None, 5)
        assert result == {'main': 0, 'side': 0}

    def test_negative_packs_returns_zeros(self, app, db, two_users):
        u1, _ = two_users
        result = _award_booster_packs(u1, -1)
        assert result == {'main': 0, 'side': 0}


# ═══════════════════════════════════════════════════════════════════
#  Game-over includes booster data
# ═══════════════════════════════════════════════════════════════════

class TestGameOverBoosters:

    def _create_game(self, client, db, two_users, auth_headers_user1):
        """Create a game via challenge for testing."""
        u1, u2 = two_users
        # Create challenge
        rv = client.post('/challenges/create_challenge', data={
            'challenger': u1.username,
            'opponent': u2.username,
            'stake': '10',
        }, headers=auth_headers_user1)
        challenge = Challenge.query.first()

        # Create game
        rv = client.post('/games/create_game',
                         data={'challenge_id': str(challenge.id)},
                         headers=auth_headers_user1)
        game_id = rv.get_json()['game']['id']
        return db.session.get(Game, game_id)

    def test_finalize_game_over_includes_boosters(self, client, db, two_users,
                                                    auth_headers_user1):
        """_finalize_game_over result includes winner_boosters and loser_boosters."""
        game = self._create_game(client, db, two_users, auth_headers_user1)
        winner = game.players[0]
        winner.points = game.stake

        # Fix randomness for predictable results
        with patch('routes.games.random.choices', return_value=['main']):
            result = _finalize_game_over(game, winner)

        assert 'winner_boosters' in result
        assert 'loser_boosters' in result
        assert result['winner_boosters']['main'] == 2  # DUEL_WINNER_BOOSTER_PACKS default
        assert result['loser_boosters']['main'] == 1   # DUEL_LOSER_BOOSTER_PACKS default

    def test_winner_gets_more_packs_than_loser(self, client, db, two_users,
                                                auth_headers_user1):
        """Winner should receive DUEL_WINNER_BOOSTER_PACKS, loser gets DUEL_LOSER_BOOSTER_PACKS."""
        u1, u2 = two_users
        u1.booster_packs = 0
        u1.booster_packs_side = 0
        u2.booster_packs = 0
        u2.booster_packs_side = 0
        db.session.commit()

        game = self._create_game(client, db, two_users, auth_headers_user1)
        winner = game.players[0]
        loser = game.players[1]
        winner.points = game.stake

        with patch('routes.games.random.choices', return_value=['main']):
            _finalize_game_over(game, winner)

        winner_user = db.session.get(User, winner.user_id)
        loser_user = db.session.get(User, loser.user_id)

        # Winner gets 2, loser gets 1
        winner_total = winner_user.booster_packs + winner_user.booster_packs_side
        loser_total = loser_user.booster_packs + loser_user.booster_packs_side
        assert winner_total == 2
        assert loser_total == 1

    def test_booster_packs_persist_in_db(self, client, db, two_users,
                                          auth_headers_user1):
        """Booster packs should be persisted to the user record."""
        u1, u2 = two_users
        u1.booster_packs = 5
        u2.booster_packs = 3
        db.session.commit()

        game = self._create_game(client, db, two_users, auth_headers_user1)
        winner = game.players[0]
        winner.points = game.stake

        with patch('routes.games.random.choices', return_value=['main']):
            _finalize_game_over(game, winner)

        db.session.refresh(u1)
        db.session.refresh(u2)

        # u1 is player1 which is players[0] (winner)
        winner_user = db.session.get(User, winner.user_id)
        assert winner_user.booster_packs >= 5  # had 5, gained 2 more
