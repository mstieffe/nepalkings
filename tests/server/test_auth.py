# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for authentication routes: register, login, token validation."""
import pytest
import sqlite3
from datetime import datetime, timedelta, timezone
from sqlalchemy.exc import OperationalError
from werkzeug.security import generate_password_hash


def _register_data(username='newuser', password='securepass', **overrides):
    data = {
        'username': username,
        'password': password,
        'age_confirmed': 'true',
        'terms_accepted': 'true',
        'privacy_accepted': 'true',
    }
    data.update(overrides)
    return data


class TestRegister:
    def test_register_new_user(self, client):
        resp = client.post('/auth/register', data=_register_data())
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['success'] is True
        assert 'token' in data
        assert data['user']['username'] == 'newuser'

    def test_starter_set_is_deferred_then_grants_buildable_deck(self, client):
        """The starter set is NOT granted at signup. It is granted (random
        offensive suit + curated set) when the Collection roulette settles, and
        is enough to build the first conquer attack independent of booster luck."""
        import server_settings as settings
        from ai.figure_recipes import find_buildable_figures
        from models import CollectionCard, User
        from onboarding_service import get_starter_suits, grant_starter_set

        resp = client.post('/auth/register', data=_register_data(username='deckuser'))
        assert resp.status_code == 200
        user = User.query.filter_by(username='deckuser').first()

        # Deferred: a fresh account has no starter cards, and the set is unflagged.
        assert CollectionCard.query.filter_by(user_id=user.id).count() == 0
        assert not (user.onboarding_state or {}).get('starter_set_granted')

        # The roulette-completion grant assigns the suit + set.
        offensive = grant_starter_set(user, commit=True)
        assert offensive in settings.OFFENSIVE_SUITS
        assert get_starter_suits(user)['offensive'] == offensive

        cards = CollectionCard.query.filter_by(user_id=user.id).all()
        assert len(cards) == len(settings.STARTER_OFFENSIVE_SET)
        assert all(c.suit == offensive for c in cards)

        # Offensive set builds the red attack figures.
        off_hand = [{'id': c.id, 'rank': c.rank, 'suit': c.suit,
                     'value': c.value, 'card_type': 'main'} for c in cards]
        off_names = {b['name'] for b in find_buildable_figures(off_hand, [], [])}
        assert {'Djungle King', 'Small Rice Farm', 'Gorkha Warriors'} <= off_names

        # Idempotent: a second grant does not duplicate the set.
        grant_starter_set(user, commit=True)
        assert CollectionCard.query.filter_by(
            user_id=user.id).count() == len(settings.STARTER_OFFENSIVE_SET)

    def test_register_duplicate_username_fails(self, client):
        client.post('/auth/register', data=_register_data('dup', 'pass1234'))
        resp = client.post('/auth/register', data=_register_data('dup', 'pass1234'))
        data = resp.get_json()
        assert resp.status_code == 409
        assert data['success'] is False

    def test_register_missing_username_fails(self, client):
        resp = client.post('/auth/register', data=_register_data(username=''))
        assert resp.status_code == 400
        assert resp.get_json()['success'] is False

    def test_register_missing_password_fails(self, client):
        resp = client.post('/auth/register', data=_register_data('someuser', ''))
        assert resp.status_code == 400
        assert resp.get_json()['success'] is False

    def test_register_requires_age_terms_and_privacy(self, client):
        resp = client.post('/auth/register', data={
            'username': 'legaluser',
            'password': 'securepass',
            'age_confirmed': 'true',
            'terms_accepted': 'false',
            'privacy_accepted': 'true',
        })
        data = resp.get_json()
        assert resp.status_code == 400
        assert data['success'] is False

    def test_register_username_too_short(self, client):
        resp = client.post('/auth/register', data=_register_data('ab', 'pass1234'))
        assert resp.status_code == 400

    def test_register_username_too_long(self, client):
        resp = client.post('/auth/register', data=_register_data('a' * 31, 'pass1234'))
        assert resp.status_code == 400

    def test_register_password_too_short(self, client):
        resp = client.post('/auth/register', data=_register_data('validuser', 'abc'))
        assert resp.status_code == 400

    def test_register_invalid_username_chars(self, client):
        resp = client.post('/auth/register', data=_register_data('bad user!', 'pass1234'))
        assert resp.status_code == 400

    def test_register_database_lock_returns_retryable_503(
            self, client, db, monkeypatch):
        def locked_commit():
            raise OperationalError(
                'COMMIT', {}, sqlite3.OperationalError('database is locked'))

        monkeypatch.setattr(db.session, 'commit', locked_commit)
        resp = client.post(
            '/auth/register', data=_register_data('busyregister', 'pass1234'))

        assert resp.status_code == 503
        assert resp.get_json()['retryable'] is True
        assert resp.headers['Retry-After'] == '2'


class TestLogin:
    def test_login_success_returns_token(self, client):
        client.post('/auth/register', data=_register_data('loginuser', 'pass1234'))
        resp = client.post('/auth/login', data={'username': 'loginuser', 'password': 'pass1234'})
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['success'] is True
        assert 'token' in data

    def test_login_wrong_password_fails(self, client):
        client.post('/auth/register', data=_register_data('loginuser2', 'pass1234'))
        resp = client.post('/auth/login', data={'username': 'loginuser2', 'password': 'wrongpass'})
        data = resp.get_json()
        assert resp.status_code == 401
        assert data['success'] is False

    def test_login_nonexistent_user_fails(self, client):
        resp = client.post('/auth/login', data={'username': 'ghost', 'password': 'pass123'})
        assert resp.status_code == 401
        assert resp.get_json()['success'] is False

    def test_login_missing_credentials(self, client):
        resp = client.post('/auth/login', data={})
        assert resp.status_code == 400

    def test_login_ai_user_blocked(self, client, db):
        """Cannot log in as an AI player."""
        from models import User
        ai_user = User(
            username='ai_player',
            password_hash=generate_password_hash('aipass'),
            is_ai=True,
            gold=999,
        )
        db.session.add(ai_user)
        db.session.commit()
        resp = client.post('/auth/login', data={'username': 'ai_player', 'password': 'aipass'})
        assert resp.status_code == 403

    def test_login_database_lock_returns_retryable_503(
            self, client, db, monkeypatch):
        from models import User

        user = User(
            username='busylogin',
            password_hash=generate_password_hash('pass1234'),
            gold=10,
        )
        db.session.add(user)
        db.session.commit()

        def locked_commit():
            raise OperationalError(
                'COMMIT', {}, sqlite3.OperationalError('database is locked'))

        monkeypatch.setattr(db.session, 'commit', locked_commit)
        resp = client.post('/auth/login', data={
            'username': 'busylogin',
            'password': 'pass1234',
        })

        assert resp.status_code == 503
        assert resp.get_json()['retryable'] is True
        assert resp.headers['Retry-After'] == '2'


class TestTokenDecorator:
    def test_require_token_rejects_missing_token(self, client):
        """Heartbeat endpoint requires a valid token."""
        resp = client.post('/auth/heartbeat')
        assert resp.status_code == 401

    def test_require_token_rejects_invalid_token(self, client):
        resp = client.post('/auth/heartbeat', headers={'Authorization': 'Bearer invalidtoken'})
        assert resp.status_code == 401

    def test_require_token_accepts_valid_token(self, client, app):
        client.post('/auth/register', data=_register_data('tokenuser', 'pass1234'))
        login_resp = client.post('/auth/login', data={'username': 'tokenuser', 'password': 'pass1234'})
        token = login_resp.get_json()['token']
        resp = client.post('/auth/heartbeat', headers={'Authorization': f'Bearer {token}'})
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True

    def test_legacy_version_zero_token_remains_valid(self, client, db):
        import server_settings as settings
        from itsdangerous import URLSafeTimedSerializer
        from models import User

        user = User(
            username='legacy_token_user',
            password_hash=generate_password_hash('pass1234'),
        )
        db.session.add(user)
        db.session.commit()
        token = URLSafeTimedSerializer(settings.SECRET_KEY).dumps(
            user.id,
            salt='user-auth',
        )

        response = client.post(
            '/auth/heartbeat',
            headers={'Authorization': f'Bearer {token}'},
        )

        assert response.status_code == 200, response.get_json()

    def test_revoked_token_is_rejected(self, client, db):
        from models import User
        from routes.auth import generate_token

        user = User(
            username='revoked_token_user',
            password_hash=generate_password_hash('pass1234'),
        )
        db.session.add(user)
        db.session.commit()
        token = generate_token(user.id, user.token_version)
        user.token_version = 1
        db.session.commit()

        response = client.post(
            '/auth/heartbeat',
            headers={'Authorization': f'Bearer {token}'},
        )

        assert response.status_code == 401
        assert response.get_json()['reason'] == 'session_revoked'

    def test_suspended_and_banned_accounts_are_rejected(self, client, db):
        from models import User
        from routes.auth import generate_token

        suspended = User(
            username='suspended_user',
            password_hash=generate_password_hash('pass1234'),
            account_status='suspended',
            suspended_until=datetime.now() + timedelta(hours=1),
        )
        banned = User(
            username='banned_user',
            password_hash=generate_password_hash('pass1234'),
            account_status='banned',
        )
        db.session.add_all([suspended, banned])
        db.session.commit()

        suspended_response = client.post(
            '/auth/heartbeat',
            headers={
                'Authorization': (
                    f'Bearer {generate_token(suspended.id)}'
                )
            },
        )
        banned_response = client.post(
            '/auth/heartbeat',
            headers={
                'Authorization': f'Bearer {generate_token(banned.id)}'
            },
        )

        assert suspended_response.status_code == 403
        assert suspended_response.get_json()['reason'] == 'account_suspended'
        assert banned_response.status_code == 403
        assert banned_response.get_json()['reason'] == 'account_banned'

    def test_login_reactivates_elapsed_timed_suspension(self, client, db):
        from models import User

        user = User(
            username='elapsed_suspension',
            password_hash=generate_password_hash('pass1234'),
            account_status='suspended',
            suspended_until=(
                datetime.now(timezone.utc).replace(tzinfo=None)
                - timedelta(minutes=1)
            ),
        )
        db.session.add(user)
        db.session.commit()

        response = client.post(
            '/auth/login',
            data={'username': user.username, 'password': 'pass1234'},
        )

        assert response.status_code == 200, response.get_json()
        db.session.refresh(user)
        assert user.account_status == 'active'
        assert user.suspended_until is None


class TestAccountLifecycle:
    def _register(self, client, username='account_user', email=None):
        data = _register_data(username, 'original-pass')
        if email:
            data['email'] = email
        response = client.post('/auth/register', data=data)
        assert response.status_code == 200
        return response.get_json()

    def test_change_password_revokes_old_token_and_returns_current_token(
            self, client):
        registered = self._register(client)
        old_token = registered['token']

        changed = client.post(
            '/auth/account/change_password',
            data={
                'current_password': 'original-pass',
                'new_password': 'replacement-pass',
            },
            headers={'Authorization': f'Bearer {old_token}'},
        )

        assert changed.status_code == 200
        new_token = changed.get_json()['token']
        assert client.post(
            '/auth/heartbeat',
            headers={'Authorization': f'Bearer {old_token}'},
        ).status_code == 401
        assert client.post(
            '/auth/heartbeat',
            headers={'Authorization': f'Bearer {new_token}'},
        ).status_code == 200
        assert client.post('/auth/login', data={
            'username': 'account_user',
            'password': 'original-pass',
        }).status_code == 401
        assert client.post('/auth/login', data={
            'username': 'account_user',
            'password': 'replacement-pass',
        }).status_code == 200

    def test_logout_all_revokes_current_token(self, client):
        registered = self._register(client, username='logout_all_user')
        token = registered['token']

        response = client.post(
            '/auth/account/logout_all',
            headers={'Authorization': f'Bearer {token}'},
        )

        assert response.status_code == 200
        assert client.post(
            '/auth/heartbeat',
            headers={'Authorization': f'Bearer {token}'},
        ).status_code == 401

    def test_export_returns_own_data_without_password_hash(self, client):
        registered = self._register(
            client,
            username='export_user',
            email='export@example.com',
        )
        self._register(client, username='export_target')
        headers = {'Authorization': f'Bearer {registered["token"]}'}
        assert client.post(
            '/safety/blocks',
            headers=headers,
            json={'username': 'export_target'},
        ).status_code == 200
        assert client.post(
            '/safety/reports',
            headers=headers,
            json={
                'username': 'export_target',
                'reason': 'spam',
                'details': 'exported own report',
            },
        ).status_code == 201

        response = client.get(
            '/auth/account/export',
            headers=headers,
        )
        data = response.get_json()

        assert response.status_code == 200
        assert data['export']['account']['username'] == 'export_user'
        assert data['export']['account']['email'] == 'export@example.com'
        assert 'password_hash' not in response.get_data(as_text=True)
        assert response.headers['Cache-Control'] == 'no-store'
        assert 'attachment;' in response.headers['Content-Disposition']
        assert data['export']['player_safety']['blocks'][0][
            'blocked_username'] == 'export_target'
        assert data['export']['player_safety']['reports_submitted'][0][
            'reason'] == 'spam'
        assert data['export']['player_safety']['reports_submitted'][0][
            'details'] == 'exported own report'
        assert 'evidence' not in data['export']['player_safety'][
            'reports_submitted'][0]

    def test_delete_anonymizes_and_revokes_account(self, client, db):
        from models import (
            Challenge,
            ChallengeStatus,
            Event,
            User,
            UserBlock,
        )

        registered = self._register(
            client,
            username='delete_user',
            email='delete@example.com',
        )
        user = User.query.filter_by(username='delete_user').first()
        other = User(
            username='delete_block_target',
            password_hash=generate_password_hash('password123'),
            gold=10,
        )
        db.session.add(other)
        db.session.flush()
        db.session.add(Event(user_id=user.id, name='signup_test'))
        db.session.add_all([
            Challenge(
                challenger_id=user.id,
                challenged_id=other.id,
                status=ChallengeStatus.OPEN,
                stake=1,
                game_limit=1,
            ),
            UserBlock(
                blocker_user_id=user.id,
                blocked_user_id=other.id,
            ),
            UserBlock(
                blocker_user_id=other.id,
                blocked_user_id=user.id,
            ),
        ])
        db.session.commit()

        response = client.post(
            '/auth/account/delete',
            data={
                'current_password': 'original-pass',
                'confirmation': 'DELETE',
            },
            headers={'Authorization': f'Bearer {registered["token"]}'},
        )

        assert response.status_code == 200
        db.session.refresh(user)
        assert user.username.startswith('DeletedPlayer-')
        assert user.email is None
        assert user.account_status == 'deleted'
        assert user.deleted_at is not None
        assert Event.query.filter_by(user_id=user.id).count() == 0
        assert UserBlock.query.filter(
            (UserBlock.blocker_user_id == user.id)
            | (UserBlock.blocked_user_id == user.id)
        ).count() == 0
        challenge = Challenge.query.filter_by(
            challenger_id=user.id,
            challenged_id=other.id,
        ).one()
        assert challenge.status == ChallengeStatus.REJECTED
        assert client.post(
            '/auth/heartbeat',
            headers={'Authorization': f'Bearer {registered["token"]}'},
        ).status_code == 401


class TestGameMembership:
    def test_accepts_numeric_string_game_id(self, app, db, two_users):
        from flask import g
        from models import Game, Player
        from routes.auth import get_game_membership

        user, _ = two_users
        game = Game(current_round=1, stake=10)
        db.session.add(game)
        db.session.commit()
        player = Player(
            user_id=user.id,
            game_id=game.id,
            turns_left=1,
            points=0,
        )
        db.session.add(player)
        db.session.commit()

        with app.test_request_context():
            g.user_id = user.id
            membership, response, status = get_game_membership(str(game.id))

        assert membership.id == player.id
        assert response is None
        assert status is None

    def test_rejects_non_integer_game_id_before_query(
        self,
        app,
        two_users,
    ):
        from flask import g
        from routes.auth import get_game_membership

        user, _ = two_users
        with app.test_request_context():
            g.user_id = user.id
            membership, response, status = get_game_membership('not-an-id')
            payload = response.get_json()

        assert membership is None
        assert status == 400
        assert payload == {'success': False, 'message': 'Invalid game ID'}


class TestGetUsers:
    def test_get_users_returns_others(self, client, two_users):
        u1, u2 = two_users
        from routes.auth import generate_token
        token = generate_token(u1.id)
        resp = client.get(
            f'/auth/get_users?username={u1.username}',
            headers={'Authorization': f'Bearer {token}'},
        )
        data = resp.get_json()
        assert resp.status_code == 200
        usernames = [u['username'] for u in data['users']]
        assert u1.username not in usernames
        assert u2.username in usernames

    def test_get_user_success(self, client, two_users):
        u1, _ = two_users
        from routes.auth import generate_token
        token = generate_token(u1.id)
        resp = client.get(
            f'/auth/get_user?username={u1.username}',
            headers={'Authorization': f'Bearer {token}'},
        )
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['success'] is True
        assert data['user']['username'] == u1.username

    def test_get_user_not_found(self, client, db):
        from models import User
        from routes.auth import generate_token
        user = User(username='lookup_user', password_hash=generate_password_hash('pass1234'))
        db.session.add(user)
        db.session.commit()
        token = generate_token(user.id)
        resp = client.get(
            '/auth/get_user?username=doesnotexist',
            headers={'Authorization': f'Bearer {token}'},
        )
        assert resp.status_code == 404


class TestEmailVerification:
    def test_verify_email_success_marks_user_verified(self, client, db):
        from models import User

        user = User(
            username='verify_user',
            password_hash=generate_password_hash('pass123'),
            email='verify@example.com',
            email_verified=False,
            email_verification_token='verify-token-123',
            email_verification_sent_at=datetime.now(),
        )
        db.session.add(user)
        db.session.commit()

        resp = client.get('/auth/verify_email?token=verify-token-123')
        data = resp.get_json()
        assert resp.status_code == 200
        assert data.get('success') is True

        db.session.refresh(user)
        assert user.email_verified is True
        assert user.email_verification_token is None

    def test_verify_email_rejects_expired_token(self, client, db):
        from models import User

        user = User(
            username='expired_verify',
            password_hash=generate_password_hash('pass123'),
            email='expired@example.com',
            email_verified=False,
            email_verification_token='expired-token-123',
            email_verification_sent_at=datetime.now() - timedelta(hours=72),
        )
        db.session.add(user)
        db.session.commit()

        resp = client.get('/auth/verify_email?token=expired-token-123')
        data = resp.get_json()
        assert resp.status_code == 400
        assert data.get('success') is False
        assert 'expired' in data.get('message', '').lower()

        db.session.refresh(user)
        assert user.email_verified is False
        assert user.email_verification_token is None


class TestRankings:
    def test_get_rankings_returns_users_with_stats(self, client, two_users):
        u1, u2 = two_users

        resp = client.get('/auth/get_rankings')
        data = resp.get_json()
        assert resp.status_code == 200
        assert data.get('success') is True

        rankings = data.get('rankings', [])
        entry_by_name = {entry['username']: entry for entry in rankings}
        assert u1.username in entry_by_name
        assert u2.username in entry_by_name

        for username in (u1.username, u2.username):
            entry = entry_by_name[username]
            assert 'gold' in entry
            assert 'total_games' in entry
            assert 'wins' in entry
            assert 'losses' in entry
            assert 'is_online' in entry

    def test_get_rankings_excludes_ai_users(self, client, db, two_users):
        from models import User

        ai_user = User(
            username='[AI] RankingBot',
            password_hash=generate_password_hash('not-a-login'),
            gold=99999,
            is_ai=True,
        )
        db.session.add(ai_user)
        db.session.commit()

        resp = client.get('/auth/get_rankings')
        usernames = {
            entry['username'] for entry in resp.get_json()['rankings']
        }

        assert resp.status_code == 200
        assert ai_user.username not in usernames
