# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for the duel reward pool (main / side / map / gold draws)."""

from unittest.mock import patch

from models import db as _db, User, Game, Challenge
import server_settings as settings
from routes.games import _award_duel_rewards, _finalize_game_over


class TestAwardDuelRewards:

    def test_zero_draws(self, app, two_users):
        u1, _ = two_users
        result = _award_duel_rewards(u1, 0)
        assert result == {'main_booster': 0, 'side_booster': 0, 'map': 0, 'gold': 0}

    def test_none_user(self, app):
        assert _award_duel_rewards(None, 5) == {
            'main_booster': 0, 'side_booster': 0, 'map': 0, 'gold': 0,
        }

    def test_main_only(self, app, db, two_users):
        u1, _ = two_users
        u1.booster_packs = 0
        u1.booster_packs_side = 0
        u1.maps = 0
        u1.gold = 0
        db.session.commit()
        with patch('routes.games.random.choices', return_value=['main_booster']):
            result = _award_duel_rewards(u1, 3)
        assert result == {'main_booster': 3, 'side_booster': 0, 'map': 0, 'gold': 0}
        assert u1.booster_packs == 3
        assert u1.maps == 0
        assert u1.gold == 0

    def test_map_draws_increment_user_maps(self, app, db, two_users):
        u1, _ = two_users
        u1.maps = 1
        db.session.commit()
        with patch('routes.games.random.choices', return_value=['map']):
            _award_duel_rewards(u1, 2)
        assert u1.maps == 3

    def test_gold_draws_apply_fixed_amount(self, app, db, two_users):
        u1, _ = two_users
        u1.gold = 100
        db.session.commit()
        with patch('routes.games.random.choices', return_value=['gold']):
            _award_duel_rewards(u1, 2)
        assert u1.gold == 100 + 2 * settings.DUEL_REWARD_GOLD_AMOUNT


class TestFinalizeGameOverRewards:

    def _create_game(self, client, db, two_users, auth_headers_user1):
        u1, u2 = two_users
        client.post('/challenges/create_challenge', data={
            'challenger': u1.username, 'opponent': u2.username, 'stake': '10',
        }, headers=auth_headers_user1)
        challenge = Challenge.query.first()
        rv = client.post('/games/create_game',
                         data={'challenge_id': str(challenge.id)},
                         headers=auth_headers_user1)
        game_id = rv.get_json()['game']['id']
        return db.session.get(Game, game_id)

    def test_includes_new_and_legacy_reward_keys(self, client, db, two_users,
                                                   auth_headers_user1):
        game = self._create_game(client, db, two_users, auth_headers_user1)
        winner = game.players[0]
        winner.points = game.stake
        with patch('routes.games.random.choices', return_value=['main_booster']):
            result = _finalize_game_over(game, winner)
        assert 'winner_rewards' in result
        assert 'loser_rewards' in result
        assert result['winner_rewards']['main_booster'] == settings.DUEL_WINNER_REWARD_DRAWS
        assert result['loser_rewards']['main_booster'] == settings.DUEL_LOSER_REWARD_DRAWS
        # Legacy keys preserved for older clients.
        assert 'winner_boosters' in result
        assert 'loser_boosters' in result
        assert result['winner_boosters']['main'] == settings.DUEL_WINNER_REWARD_DRAWS
