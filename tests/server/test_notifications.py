# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for async-play email notifications (server/notification_service.py)."""

from datetime import datetime, timedelta, timezone

import pytest
from werkzeug.security import generate_password_hash

import notification_service
from models import db, Challenge, ChallengeStatus, Game, Player, User
from notification_service import (maybe_notify_turn_or_finish,
                                  notify_challenge_received,
                                  unsubscribe_sig, verify_unsubscribe_sig)


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _mk_user(name, email=None, last_active_minutes_ago=999, notify=True,
             is_ai=False):
    user = User(
        username=name,
        password_hash=generate_password_hash('pass1234'),
        email=email,
        notify_emails_enabled=notify,
        is_ai=is_ai,
        last_active=_utcnow() - timedelta(minutes=last_active_minutes_ago),
    )
    db.session.add(user)
    db.session.commit()
    return user


def _mk_duel(user_a, user_b, turn_user=None, state='open'):
    game = Game(state=state, mode='duel')
    db.session.add(game)
    db.session.flush()
    pa = Player(user_id=user_a.id, game_id=game.id, turns_left=3, points=0)
    pb = Player(user_id=user_b.id, game_id=game.id, turns_left=3, points=0)
    db.session.add_all([pa, pb])
    db.session.flush()
    if turn_user is not None:
        game.turn_player_id = pa.id if turn_user.id == user_a.id else pb.id
    db.session.commit()
    return game, pa, pb


@pytest.fixture
def sent(monkeypatch):
    """Capture outgoing notification emails instead of touching SMTP."""
    captured = []
    monkeypatch.setattr(
        notification_service, '_send_async',
        lambda to, subject, body: captured.append(
            {'to': to, 'subject': subject, 'body': body}))
    return captured


class TestUnsubscribe:
    def test_sig_roundtrip(self, app):
        sig = unsubscribe_sig(42)
        assert verify_unsubscribe_sig(42, sig)
        assert not verify_unsubscribe_sig(42, 'wrong')
        assert not verify_unsubscribe_sig(43, sig)

    def test_unsubscribe_route_disables(self, client, app):
        user = _mk_user('unsub_user', email='u@example.com')
        resp = client.get(
            f'/auth/unsubscribe?uid={user.id}&sig={unsubscribe_sig(user.id)}')
        assert resp.status_code == 200
        assert b'Unsubscribed' in resp.data
        assert User.query.get(user.id).notify_emails_enabled is False

    def test_unsubscribe_route_rejects_bad_sig(self, client, app):
        user = _mk_user('unsub_bad', email='u2@example.com')
        resp = client.get(f'/auth/unsubscribe?uid={user.id}&sig=forged')
        assert resp.status_code == 400
        assert User.query.get(user.id).notify_emails_enabled is True

    def test_set_notifications_route(self, client, app):
        from routes.auth import generate_token
        user = _mk_user('toggler', email='t@example.com')
        headers = {'Authorization': f'Bearer {generate_token(user.id)}'}
        resp = client.post('/auth/set_notifications',
                           data={'enabled': 'false'}, headers=headers)
        assert resp.get_json()['notify_emails_enabled'] is False
        resp = client.post('/auth/set_notifications',
                           data={'enabled': 'true'}, headers=headers)
        assert resp.get_json()['notify_emails_enabled'] is True


class TestTurnNotification:
    def test_offline_turn_player_gets_email(self, app, sent):
        a = _mk_user('turn_a', email='a@example.com')
        b = _mk_user('turn_b', email='b@example.com')
        game, pa, pb = _mk_duel(a, b, turn_user=b)
        assert maybe_notify_turn_or_finish(game.id, requester_user_id=a.id)
        assert len(sent) == 1
        assert sent[0]['to'] == 'b@example.com'
        assert 'your turn' in sent[0]['subject'].lower()
        assert 'unsubscribe' in sent[0]['body'].lower()

    def test_debounced_within_interval(self, app, sent):
        a = _mk_user('deb_a', email='a2@example.com')
        b = _mk_user('deb_b', email='b2@example.com')
        game, _, _ = _mk_duel(a, b, turn_user=b)
        assert maybe_notify_turn_or_finish(game.id, requester_user_id=a.id)
        assert not maybe_notify_turn_or_finish(game.id, requester_user_id=a.id)
        assert len(sent) == 1

    def test_requester_not_emailed_about_own_turn(self, app, sent):
        a = _mk_user('req_a', email='a3@example.com')
        b = _mk_user('req_b', email='b3@example.com')
        game, _, _ = _mk_duel(a, b, turn_user=b)
        assert not maybe_notify_turn_or_finish(game.id, requester_user_id=b.id)
        assert sent == []

    def test_online_player_not_emailed(self, app, sent):
        a = _mk_user('on_a', email='a4@example.com')
        b = _mk_user('on_b', email='b4@example.com', last_active_minutes_ago=0)
        game, _, _ = _mk_duel(a, b, turn_user=b)
        assert not maybe_notify_turn_or_finish(game.id, requester_user_id=a.id)
        assert sent == []

    def test_opted_out_or_missing_email_not_emailed(self, app, sent):
        a = _mk_user('opt_a', email='a5@example.com')
        b = _mk_user('opt_b', email='b5@example.com', notify=False)
        c = _mk_user('opt_c')  # no email at all
        game1, _, _ = _mk_duel(a, b, turn_user=b)
        game2, _, _ = _mk_duel(a, c, turn_user=c)
        assert not maybe_notify_turn_or_finish(game1.id)
        assert not maybe_notify_turn_or_finish(game2.id)
        assert sent == []

    def test_ai_user_never_emailed(self, app, sent):
        a = _mk_user('ai_h', email='h@example.com')
        strategos = _mk_user('[AI] T', email='ai@example.com', is_ai=True)
        game, _, _ = _mk_duel(a, strategos, turn_user=strategos)
        assert not maybe_notify_turn_or_finish(game.id, requester_user_id=a.id)
        assert sent == []

    def test_conquer_games_skipped(self, app, sent):
        a = _mk_user('cq_a', email='cq@example.com')
        b = _mk_user('cq_b', email='cq2@example.com')
        game, _, _ = _mk_duel(a, b, turn_user=b)
        game.mode = 'conquer'
        db.session.commit()
        assert not maybe_notify_turn_or_finish(game.id)
        assert sent == []


class TestFinishNotification:
    def test_finished_game_emails_offline_players_once(self, app, sent):
        a = _mk_user('fin_a', email='fa@example.com')
        b = _mk_user('fin_b', email='fb@example.com')
        game, pa, pb = _mk_duel(a, b, state='finished')
        game.winner_player_id = pa.id
        db.session.commit()
        assert maybe_notify_turn_or_finish(game.id)
        assert {m['to'] for m in sent} == {'fa@example.com', 'fb@example.com'}
        won = next(m for m in sent if m['to'] == 'fa@example.com')
        lost = next(m for m in sent if m['to'] == 'fb@example.com')
        assert 'won' in won['subject'].lower()
        assert 'lost' in lost['subject'].lower()
        # Second pass: nobody is emailed twice.
        assert not maybe_notify_turn_or_finish(game.id)
        assert len(sent) == 2


class TestChallengeNotification:
    def test_offline_challenged_player_emailed(self, app, sent):
        a = _mk_user('chn_a', email='cha@example.com')
        b = _mk_user('chn_b', email='chb@example.com')
        challenge = Challenge(challenger=a, challenged=b,
                              status=ChallengeStatus.OPEN, stake=10,
                              game_limit=7)
        db.session.add(challenge)
        db.session.commit()
        assert notify_challenge_received(challenge)
        assert len(sent) == 1
        assert sent[0]['to'] == 'chb@example.com'
        assert 'challenged you' in sent[0]['subject']

    def test_online_challenged_player_not_emailed(self, app, sent):
        a = _mk_user('chn_c', email='chc@example.com')
        b = _mk_user('chn_d', email='chd@example.com', last_active_minutes_ago=0)
        challenge = Challenge(challenger=a, challenged=b,
                              status=ChallengeStatus.OPEN, stake=10,
                              game_limit=7)
        db.session.add(challenge)
        db.session.commit()
        assert not notify_challenge_received(challenge)
        assert sent == []
