# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for challenge creation, removal, and listing."""
import pytest


def _make_challenge(client, headers, challenger, opponent, stake=10, game_limit=None):
    data = {
        'challenger': challenger,
        'opponent': opponent,
        'stake': str(stake),
    }
    if game_limit is not None:
        data['game_limit'] = str(game_limit)
    return client.post('/challenges/create_challenge', data=data, headers=headers)


class TestCreateChallenge:
    def test_create_challenge_success(self, client, two_users, auth_headers_user1):
        u1, u2 = two_users
        resp = _make_challenge(client, auth_headers_user1, u1.username, u2.username)
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['success'] is True

    def test_create_challenge_sets_status_open(self, client, db, two_users, auth_headers_user1):
        from models import Challenge, ChallengeStatus
        u1, u2 = two_users
        _make_challenge(client, auth_headers_user1, u1.username, u2.username)
        challenge = Challenge.query.first()
        assert challenge is not None
        assert challenge.status.value == ChallengeStatus.OPEN.value

    def test_create_challenge_stores_stake(self, client, db, two_users, auth_headers_user1):
        from models import Challenge
        u1, u2 = two_users
        _make_challenge(client, auth_headers_user1, u1.username, u2.username, stake=25)
        challenge = Challenge.query.first()
        assert challenge.stake == 25

    def test_create_challenge_defaults_game_limit_to_stake(self, client, db, two_users, auth_headers_user1):
        from models import Challenge
        u1, u2 = two_users
        _make_challenge(client, auth_headers_user1, u1.username, u2.username, stake=25)
        challenge = Challenge.query.first()
        assert challenge.game_limit == 25

    def test_create_challenge_stores_explicit_game_limit(self, client, db, two_users, auth_headers_user1):
        from models import Challenge
        u1, u2 = two_users
        _make_challenge(client, auth_headers_user1, u1.username, u2.username, stake=10, game_limit=30)
        challenge = Challenge.query.first()
        assert challenge.stake == 10
        assert challenge.game_limit == 30

    @pytest.mark.parametrize('game_limit', ['0', '101', 'abc'])
    def test_create_challenge_fails_invalid_game_limit(
        self, client, two_users, auth_headers_user1, game_limit
    ):
        u1, u2 = two_users
        resp = client.post('/challenges/create_challenge', data={
            'challenger': u1.username,
            'opponent': u2.username,
            'stake': '10',
            'game_limit': game_limit,
        }, headers=auth_headers_user1)
        data = resp.get_json()
        assert resp.status_code == 400
        assert data['success'] is False

    def test_create_challenge_stores_turn_time_limit(self, client, db, two_users, auth_headers_user1):
        from models import Challenge
        u1, u2 = two_users
        resp = client.post('/challenges/create_challenge', data={
            'challenger': u1.username,
            'opponent': u2.username,
            'stake': '10',
            'turn_time_limit': '60',
        }, headers=auth_headers_user1)
        assert resp.get_json()['success'] is True
        challenge = Challenge.query.first()
        assert challenge.turn_time_limit == 60

    def test_create_challenge_fails_nonexistent_challenger(self, client, two_users, auth_headers_user1):
        _, u2 = two_users
        resp = _make_challenge(client, auth_headers_user1, 'ghost', u2.username)
        data = resp.get_json()
        assert resp.status_code == 400
        assert data['success'] is False

    def test_create_challenge_fails_nonexistent_opponent(self, client, two_users, auth_headers_user1):
        u1, _ = two_users
        resp = _make_challenge(client, auth_headers_user1, u1.username, 'ghost')
        data = resp.get_json()
        assert resp.status_code == 400
        assert data['success'] is False

    def test_create_challenge_fails_insufficient_gold(self, client, db, two_users, auth_headers_user1):
        u1, u2 = two_users
        u1.gold = 5
        db.session.commit()
        resp = _make_challenge(client, auth_headers_user1, u1.username, u2.username, stake=10)
        data = resp.get_json()
        assert resp.status_code == 400
        assert data['success'] is False

    def test_create_challenge_fails_stake_less_than_1(self, client, two_users, auth_headers_user1):
        u1, u2 = two_users
        resp = _make_challenge(client, auth_headers_user1, u1.username, u2.username, stake=0)
        data = resp.get_json()
        assert resp.status_code == 400
        assert data['success'] is False

    def test_create_challenge_forbidden_when_token_doesnt_match_challenger(
        self, client, two_users, auth_headers_user2
    ):
        u1, u2 = two_users
        # user2's token but claiming to be user1
        resp = _make_challenge(client, auth_headers_user2, u1.username, u2.username)
        data = resp.get_json()
        assert resp.status_code == 403
        assert data['success'] is False

    def test_create_challenge_requires_token(self, client, two_users):
        u1, u2 = two_users
        resp = _make_challenge(client, {}, u1.username, u2.username)
        assert resp.status_code == 401


class TestRemoveChallenge:
    def _create(self, client, db, two_users, auth_headers_user1):
        from models import Challenge, ChallengeStatus
        u1, u2 = two_users
        _make_challenge(client, auth_headers_user1, u1.username, u2.username)
        return Challenge.query.first()

    def test_remove_challenge_success(self, client, db, two_users, auth_headers_user1):
        from models import Challenge
        challenge = self._create(client, db, two_users, auth_headers_user1)
        resp = client.post('/challenges/remove_challenge', data={
            'challenge_id': str(challenge.id),
        }, headers=auth_headers_user1)
        assert resp.get_json()['success'] is True
        assert db.session.get(Challenge, challenge.id) is None

    def test_remove_challenge_fails_when_not_participant(self, client, db, two_users, auth_headers_user1, app):
        from models import User, Challenge
        from werkzeug.security import generate_password_hash
        from routes.auth import generate_token
        # Create third user
        u3 = User(username='third', password_hash=generate_password_hash('pass'), gold=100)
        db.session.add(u3)
        db.session.commit()
        token3 = generate_token(u3.id)
        headers3 = {'Authorization': f'Bearer {token3}'}

        challenge = self._create(client, db, two_users, auth_headers_user1)
        resp = client.post('/challenges/remove_challenge', data={
            'challenge_id': str(challenge.id),
        }, headers=headers3)
        assert resp.status_code == 403

    def test_remove_challenge_fails_when_not_found(self, client, two_users, auth_headers_user1):
        resp = client.post('/challenges/remove_challenge', data={
            'challenge_id': '9999',
        }, headers=auth_headers_user1)
        assert resp.status_code == 400


class TestOpenChallenges:
    def test_open_challenges_returns_all_for_user(self, client, db, two_users, auth_headers_user1):
        u1, u2 = two_users
        _make_challenge(client, auth_headers_user1, u1.username, u2.username)
        resp = client.get(f'/challenges/open_challenges?username={u1.username}')
        data = resp.get_json()
        assert len(data['challenges']) == 1

    def test_open_challenges_filters_by_status_open(self, client, db, two_users, auth_headers_user1):
        from models import Challenge, ChallengeStatus
        u1, u2 = two_users
        _make_challenge(client, auth_headers_user1, u1.username, u2.username)
        # Manually close the challenge
        c = Challenge.query.first()
        c.status = ChallengeStatus.ACCEPTED
        db.session.commit()
        resp = client.get(f'/challenges/open_challenges?username={u1.username}')
        data = resp.get_json()
        assert len(data['challenges']) == 0

    def test_open_challenges_fails_unknown_user(self, client):
        resp = client.get('/challenges/open_challenges?username=nobody')
        assert resp.status_code == 400
        assert resp.get_json()['success'] is False

    def test_challenge_serialization(self, client, db, two_users, auth_headers_user1):
        from models import Challenge
        u1, u2 = two_users
        _make_challenge(client, auth_headers_user1, u1.username, u2.username)
        challenge = Challenge.query.first()
        s = challenge.serialize()
        assert 'id' in s
        assert 'challenger_id' in s
        assert 'challenged_id' in s
        assert 'status' in s
        assert s['stake'] >= 1
