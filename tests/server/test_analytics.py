# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for the first-party analytics event log (server/analytics.py)."""

from werkzeug.security import generate_password_hash

from analytics import track
from models import db, Event, User


def _register(client, username='analytics_user'):
    return client.post('/auth/register', data={
        'username': username,
        'password': 'pass1234',
        'age_confirmed': 'true',
        'terms_accepted': 'true',
        'privacy_accepted': 'true',
    })


def _events(name=None):
    q = Event.query
    if name:
        q = q.filter_by(name=name)
    return q.order_by(Event.id).all()


class TestTrack:
    def test_track_queues_event_on_session(self, app):
        assert track('unit_test_event', user_id=7, foo='bar', empty=None)
        db.session.commit()
        rows = _events('unit_test_event')
        assert len(rows) == 1
        assert rows[0].user_id == 7
        # None-valued props are dropped
        assert rows[0].props == {'foo': 'bar'}

    def test_track_disabled_via_settings(self, app, monkeypatch):
        import server_settings
        monkeypatch.setattr(server_settings, 'ANALYTICS_ENABLED', False)
        assert track('should_not_exist') is False
        db.session.commit()
        assert _events('should_not_exist') == []

    def test_track_never_raises(self, app, monkeypatch):
        # Force Event construction to explode; track must swallow it.
        import analytics
        monkeypatch.setattr(analytics, 'Event',
                            lambda **kw: (_ for _ in ()).throw(RuntimeError('boom')))
        assert track('explodes') is False

    def test_track_truncates_long_names(self, app):
        track('x' * 200)
        db.session.commit()
        rows = _events()
        assert rows and len(rows[-1].name) == 64


class TestRouteHooks:
    def test_register_tracks_signup(self, client, app):
        resp = _register(client, 'sig_user')
        assert resp.status_code == 200
        user = User.query.filter_by(username='sig_user').first()
        rows = _events('signup')
        assert len(rows) == 1
        assert rows[0].user_id == user.id
        assert rows[0].props == {'has_email': False}

    def test_login_tracks(self, client, app):
        _register(client, 'login_user')
        resp = client.post('/auth/login', data={
            'username': 'login_user', 'password': 'pass1234'})
        assert resp.status_code == 200
        assert len(_events('login')) == 1

    def test_challenge_created_tracks(self, client, app):
        _register(client, 'chal_a')
        _register(client, 'chal_b')
        # Gold is no longer granted at registration (deferred to the welcome
        # gift), so fund the challenger to cover the stake.
        with app.app_context():
            challenger = User.query.filter_by(username='chal_a').first()
            challenger.gold = 100
            db.session.commit()
        login = client.post('/auth/login', data={
            'username': 'chal_a', 'password': 'pass1234'}).get_json()
        headers = {'Authorization': f"Bearer {login['token']}"}
        resp = client.post('/challenges/create_challenge', data={
            'challenger': 'chal_a', 'opponent': 'chal_b',
            'stake': 10, 'game_limit': 7}, headers=headers)
        assert resp.status_code == 200, resp.get_json()
        rows = _events('challenge_created')
        assert len(rows) == 1
        assert rows[0].props['stake'] == 10
        assert rows[0].props['game_limit'] == 7
        assert rows[0].props['vs_ai'] is False

    def test_booster_open_tracks(self, client, app):
        _register(client, 'pack_user')
        # Boosters are no longer granted at registration; give the test user one.
        with app.app_context():
            user = User.query.filter_by(username='pack_user').first()
            user.booster_packs = 1
            db.session.commit()
        login = client.post('/auth/login', data={
            'username': 'pack_user', 'password': 'pass1234'}).get_json()
        headers = {'Authorization': f"Bearer {login['token']}"}
        resp = client.post('/collection/open_booster', headers=headers)
        assert resp.status_code == 200
        rows = _events('booster_opened')
        assert len(rows) == 1
        assert rows[0].props == {'kind': 'main'}
