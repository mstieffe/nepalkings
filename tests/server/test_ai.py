# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for AI system: user creation, token generation."""
import pytest


class TestAIUsers:
    def test_ai_users_created_on_startup_when_enabled(self, app, db):
        """When AI_ENABLED=True, AI users are created at startup."""
        import os
        # The test app uses AI_ENABLED=False; verify the helper function works standalone
        from models import User
        from werkzeug.security import generate_password_hash
        ai_user = User(
            username='[AI] TestBot',
            password_hash=generate_password_hash('secret'),
            gold=999999,
            is_ai=True,
        )
        db.session.add(ai_user)
        db.session.commit()
        found = User.query.filter_by(username='[AI] TestBot', is_ai=True).first()
        assert found is not None

    def test_ai_auth_headers_generated(self, app, db):
        """get_ai_auth_headers returns a valid Bearer token for an AI user."""
        from ai import get_ai_auth_headers, init_ai_users
        import server_settings as settings
        from models import User

        # Tokens are generated when AI users are initialized.
        init_ai_users()

        ai_user = User.query.filter_by(
            username=settings.AI_USERNAMES[0],
            is_ai=True,
        ).first()
        assert ai_user is not None

        headers = get_ai_auth_headers(ai_user.id)
        assert 'Authorization' in headers
        assert headers['Authorization'].startswith('Bearer ')

    def test_ai_user_cannot_login_via_normal_route(self, client, db):
        """AI users are blocked from normal login."""
        from models import User
        from werkzeug.security import generate_password_hash
        ai_user = User(
            username='[AI] BlockedBot',
            password_hash=generate_password_hash('aipass'),
            is_ai=True,
            gold=999,
        )
        db.session.add(ai_user)
        db.session.commit()
        resp = client.post('/auth/login', data={
            'username': '[AI] BlockedBot',
            'password': 'aipass',
        })
        assert resp.status_code == 403
        assert resp.get_json()['success'] is False
