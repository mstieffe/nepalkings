# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for authentication routes: register, login, token validation."""
import pytest
from werkzeug.security import generate_password_hash


class TestRegister:
    def test_register_new_user(self, client):
        resp = client.post('/auth/register', data={
            'username': 'newuser',
            'password': 'securepass',
        })
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['success'] is True
        assert 'token' in data
        assert data['user']['username'] == 'newuser'

    def test_register_duplicate_username_fails(self, client):
        client.post('/auth/register', data={'username': 'dup', 'password': 'pass123'})
        resp = client.post('/auth/register', data={'username': 'dup', 'password': 'pass123'})
        data = resp.get_json()
        assert resp.status_code == 409
        assert data['success'] is False

    def test_register_missing_username_fails(self, client):
        resp = client.post('/auth/register', data={'password': 'pass123'})
        assert resp.status_code == 400
        assert resp.get_json()['success'] is False

    def test_register_missing_password_fails(self, client):
        resp = client.post('/auth/register', data={'username': 'someuser'})
        assert resp.status_code == 400
        assert resp.get_json()['success'] is False

    def test_register_username_too_short(self, client):
        resp = client.post('/auth/register', data={'username': 'ab', 'password': 'pass123'})
        assert resp.status_code == 400

    def test_register_username_too_long(self, client):
        resp = client.post('/auth/register', data={
            'username': 'a' * 31,
            'password': 'pass123',
        })
        assert resp.status_code == 400

    def test_register_password_too_short(self, client):
        resp = client.post('/auth/register', data={'username': 'validuser', 'password': 'abc'})
        assert resp.status_code == 400

    def test_register_invalid_username_chars(self, client):
        resp = client.post('/auth/register', data={
            'username': 'bad user!',
            'password': 'pass123',
        })
        assert resp.status_code == 400


class TestLogin:
    def test_login_success_returns_token(self, client):
        client.post('/auth/register', data={'username': 'loginuser', 'password': 'pass123'})
        resp = client.post('/auth/login', data={'username': 'loginuser', 'password': 'pass123'})
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['success'] is True
        assert 'token' in data

    def test_login_wrong_password_fails(self, client):
        client.post('/auth/register', data={'username': 'loginuser2', 'password': 'pass123'})
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
        client.post('/auth/register', data={'username': 'tokenuser', 'password': 'pass123'})
        login_resp = client.post('/auth/login', data={'username': 'tokenuser', 'password': 'pass123'})
        token = login_resp.get_json()['token']
        resp = client.post('/auth/heartbeat', headers={'Authorization': f'Bearer {token}'})
        assert resp.status_code == 200
        assert resp.get_json()['success'] is True


class TestGetUsers:
    def test_get_users_returns_others(self, client, two_users):
        u1, u2 = two_users
        resp = client.get(f'/auth/get_users?username={u1.username}')
        data = resp.get_json()
        assert resp.status_code == 200
        usernames = [u['username'] for u in data['users']]
        assert u1.username not in usernames
        assert u2.username in usernames

    def test_get_user_success(self, client, two_users):
        u1, _ = two_users
        resp = client.get(f'/auth/get_user?username={u1.username}')
        data = resp.get_json()
        assert resp.status_code == 200
        assert data['success'] is True
        assert data['user']['username'] == u1.username

    def test_get_user_not_found(self, client):
        resp = client.get('/auth/get_user?username=doesnotexist')
        assert resp.status_code == 404
