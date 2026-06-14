# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for authentication routes: register, login, token validation."""
import pytest
from datetime import datetime, timedelta
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

    def test_register_grants_buildable_starter_deck(self, client):
        """New accounts get a curated starter deck that can build a minimal
        conquer attack and first prelude, independent of booster luck."""
        import server_settings as settings
        from ai.figure_recipes import find_buildable_figures
        from models import CollectionCard, User

        resp = client.post('/auth/register', data=_register_data(username='deckuser'))
        assert resp.status_code == 200
        user = User.query.filter_by(username='deckuser').first()

        cards = CollectionCard.query.filter_by(user_id=user.id).all()
        assert len(cards) == len(settings.STARTER_FIGURE_CARDS)

        main_hand = [{'id': c.id, 'rank': c.rank, 'suit': c.suit,
                      'value': c.value, 'card_type': 'main'} for c in cards]
        names = {b['name'] for b in find_buildable_figures(main_hand, [], [])}
        assert {'Djungle King', 'Small Rice Farm', 'Gorkha Warriors'} <= names
        hearts_8s = [c for c in cards if c.suit == 'Hearts' and c.rank == '8']
        assert len(hearts_8s) == 2

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
