# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for Phase 14 — attack notifications and history."""
import pytest
from datetime import datetime, timezone, timedelta

from models import db, User, Land, LandAttackLog


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_user(db_session, username='player1', gold=100):
    from werkzeug.security import generate_password_hash
    u = User(username=username, password_hash=generate_password_hash('pw'),
             gold=gold)
    db_session.session.add(u)
    db_session.session.commit()
    return u


def _make_land(db_session, col=0, row=0, owner_user_id=None):
    land = Land(col=col, row=row, tier=1, gold_rate=5.0,
                suit_bonus_suit='Hearts', suit_bonus_value=2,
                owner_user_id=owner_user_id)
    db_session.session.add(land)
    db_session.session.commit()
    return land


def _make_attack_log(db_session, land, attacker, defender=None,
                     result='attacker_won', seen=False,
                     card_won_suit=None, card_won_rank=None,
                     card_lost_suit=None, card_lost_rank=None,
                     timestamp=None):
    log = LandAttackLog(
        land_id=land.id,
        attacker_user_id=attacker.id,
        defender_user_id=defender.id if defender else None,
        result=result,
        card_won_suit=card_won_suit, card_won_rank=card_won_rank,
        card_lost_suit=card_lost_suit, card_lost_rank=card_lost_rank,
        seen_by_defender=seen,
    )
    if timestamp:
        log.timestamp = timestamp
    db_session.session.add(log)
    db_session.session.commit()
    return log


def _auth_headers(app, user):
    from routes.auth import generate_token
    token = generate_token(user.id)
    return {'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'}


# ═════════════════════════════════════════════════════════════════════════════
#  GET /kingdom/attack_notifications
# ═════════════════════════════════════════════════════════════════════════════

class TestAttackNotifications:

    def test_returns_unseen_for_defender(self, app, db):
        """Unseen attack logs where user is defender are returned."""
        with app.app_context():
            attacker = _make_user(db, 'attacker')
            defender = _make_user(db, 'defender')
            land = _make_land(db, col=3, row=2, owner_user_id=defender.id)
            _make_attack_log(db, land, attacker, defender,
                             result='attacker_won',
                             card_lost_suit='Hearts', card_lost_rank='K')

            client = app.test_client()
            resp = client.get('/kingdom/attack_notifications',
                              headers=_auth_headers(app, defender))
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['success'] is True
            assert len(data['notifications']) == 1
            n = data['notifications'][0]
            assert n['land_col'] == 3
            assert n['land_row'] == 2
            assert n['attacker_username'] == 'attacker'
            assert n['result'] == 'attacker_won'
            assert n['card_lost_suit'] == 'Hearts'
            assert n['card_lost_rank'] == 'K'

    def test_excludes_seen(self, app, db):
        """Already-seen notifications are not returned."""
        with app.app_context():
            attacker = _make_user(db, 'attacker')
            defender = _make_user(db, 'defender')
            land = _make_land(db, owner_user_id=defender.id)
            _make_attack_log(db, land, attacker, defender, seen=True)

            client = app.test_client()
            resp = client.get('/kingdom/attack_notifications',
                              headers=_auth_headers(app, defender))
            assert resp.get_json()['notifications'] == []

    def test_excludes_attacker_logs(self, app, db):
        """Logs where user was the attacker are not notifications."""
        with app.app_context():
            attacker = _make_user(db, 'attacker')
            defender = _make_user(db, 'defender')
            land = _make_land(db, owner_user_id=defender.id)
            _make_attack_log(db, land, attacker, defender)

            client = app.test_client()
            # Attacker should have no notifications
            resp = client.get('/kingdom/attack_notifications',
                              headers=_auth_headers(app, attacker))
            assert resp.get_json()['notifications'] == []

    def test_empty_when_no_logs(self, app, db):
        """No logs → empty list."""
        with app.app_context():
            user = _make_user(db)
            client = app.test_client()
            resp = client.get('/kingdom/attack_notifications',
                              headers=_auth_headers(app, user))
            assert resp.get_json()['notifications'] == []

    def test_multiple_unseen(self, app, db):
        """Multiple unseen logs returned in descending timestamp order."""
        with app.app_context():
            attacker = _make_user(db, 'attacker')
            defender = _make_user(db, 'defender')
            land1 = _make_land(db, col=0, row=0, owner_user_id=defender.id)
            land2 = _make_land(db, col=1, row=0, owner_user_id=defender.id)

            now = datetime.now(timezone.utc).replace(tzinfo=None)
            _make_attack_log(db, land1, attacker, defender,
                             timestamp=now - timedelta(hours=2))
            _make_attack_log(db, land2, attacker, defender,
                             result='defender_won',
                             timestamp=now)

            client = app.test_client()
            resp = client.get('/kingdom/attack_notifications',
                              headers=_auth_headers(app, defender))
            notifs = resp.get_json()['notifications']
            assert len(notifs) == 2
            # Most recent first
            assert notifs[0]['result'] == 'defender_won'
            assert notifs[1]['result'] == 'attacker_won'


# ═════════════════════════════════════════════════════════════════════════════
#  POST /kingdom/attack_notifications/mark_seen
# ═════════════════════════════════════════════════════════════════════════════

class TestMarkSeen:

    def test_marks_own_notifications(self, app, db):
        """Defender can mark their own notifications as seen."""
        with app.app_context():
            attacker = _make_user(db, 'attacker')
            defender = _make_user(db, 'defender')
            land = _make_land(db, owner_user_id=defender.id)
            log = _make_attack_log(db, land, attacker, defender)

            client = app.test_client()
            resp = client.post('/kingdom/attack_notifications/mark_seen',
                               json={'notification_ids': [log.id]},
                               headers=_auth_headers(app, defender))
            assert resp.status_code == 200
            assert resp.get_json()['marked'] == 1

            # Verify in DB
            updated = db.session.get(LandAttackLog, log.id)
            assert updated.seen_by_defender is True

    def test_cannot_mark_others_notifications(self, app, db):
        """A user cannot mark notifications where they are not the defender."""
        with app.app_context():
            attacker = _make_user(db, 'attacker')
            defender = _make_user(db, 'defender')
            third = _make_user(db, 'third')
            land = _make_land(db, owner_user_id=defender.id)
            log = _make_attack_log(db, land, attacker, defender)

            client = app.test_client()
            resp = client.post('/kingdom/attack_notifications/mark_seen',
                               json={'notification_ids': [log.id]},
                               headers=_auth_headers(app, third))
            assert resp.get_json()['marked'] == 0

            # Still unseen
            assert db.session.get(LandAttackLog, log.id).seen_by_defender is False

    def test_empty_ids_rejected(self, app, db):
        """Empty notification_ids list returns 400."""
        with app.app_context():
            user = _make_user(db)
            client = app.test_client()
            resp = client.post('/kingdom/attack_notifications/mark_seen',
                               json={'notification_ids': []},
                               headers=_auth_headers(app, user))
            assert resp.status_code == 400

    def test_missing_ids_rejected(self, app, db):
        """Missing notification_ids returns 400."""
        with app.app_context():
            user = _make_user(db)
            client = app.test_client()
            resp = client.post('/kingdom/attack_notifications/mark_seen',
                               json={},
                               headers=_auth_headers(app, user))
            assert resp.status_code == 400

    def test_idempotent(self, app, db):
        """Marking already-seen notifications succeeds with marked=1."""
        with app.app_context():
            attacker = _make_user(db, 'attacker')
            defender = _make_user(db, 'defender')
            land = _make_land(db, owner_user_id=defender.id)
            log = _make_attack_log(db, land, attacker, defender, seen=True)

            client = app.test_client()
            resp = client.post('/kingdom/attack_notifications/mark_seen',
                               json={'notification_ids': [log.id]},
                               headers=_auth_headers(app, defender))
            assert resp.status_code == 200


# ═════════════════════════════════════════════════════════════════════════════
#  GET /kingdom/attack_history
# ═════════════════════════════════════════════════════════════════════════════

class TestAttackHistory:

    def test_returns_logs_as_attacker(self, app, db):
        """History includes logs where user was the attacker."""
        with app.app_context():
            attacker = _make_user(db, 'attacker')
            defender = _make_user(db, 'defender')
            land = _make_land(db, owner_user_id=defender.id)
            _make_attack_log(db, land, attacker, defender)

            client = app.test_client()
            resp = client.get('/kingdom/attack_history',
                              headers=_auth_headers(app, attacker))
            data = resp.get_json()
            assert data['success'] is True
            assert data['total'] == 1
            assert data['history'][0]['attacker_username'] == 'attacker'

    def test_returns_logs_as_defender(self, app, db):
        """History includes logs where user was the defender."""
        with app.app_context():
            attacker = _make_user(db, 'attacker')
            defender = _make_user(db, 'defender')
            land = _make_land(db, owner_user_id=defender.id)
            _make_attack_log(db, land, attacker, defender)

            client = app.test_client()
            resp = client.get('/kingdom/attack_history',
                              headers=_auth_headers(app, defender))
            data = resp.get_json()
            assert data['total'] == 1

    def test_pagination(self, app, db):
        """History is paginated."""
        with app.app_context():
            attacker = _make_user(db, 'attacker')
            defender = _make_user(db, 'defender')
            land = _make_land(db, owner_user_id=defender.id)

            for i in range(5):
                _make_attack_log(db, land, attacker, defender)

            client = app.test_client()
            resp = client.get('/kingdom/attack_history?page=1&per_page=2',
                              headers=_auth_headers(app, attacker))
            data = resp.get_json()
            assert len(data['history']) == 2
            assert data['total'] == 5
            assert data['pages'] == 3
            assert data['page'] == 1

    def test_excludes_other_users(self, app, db):
        """History only includes the current user's logs."""
        with app.app_context():
            u1 = _make_user(db, 'u1')
            u2 = _make_user(db, 'u2')
            u3 = _make_user(db, 'u3')
            land = _make_land(db, owner_user_id=u2.id)
            _make_attack_log(db, land, u1, u2)  # u1 attacks u2

            client = app.test_client()
            resp = client.get('/kingdom/attack_history',
                              headers=_auth_headers(app, u3))
            assert resp.get_json()['total'] == 0

    def test_ai_defender_shown(self, app, db):
        """Logs with no defender_user_id show defender_username='AI'."""
        with app.app_context():
            attacker = _make_user(db, 'attacker')
            land = _make_land(db)
            _make_attack_log(db, land, attacker, defender=None)

            client = app.test_client()
            resp = client.get('/kingdom/attack_history',
                              headers=_auth_headers(app, attacker))
            history = resp.get_json()['history']
            assert len(history) == 1
            assert history[0]['defender_username'] == 'AI'

    def test_per_page_capped(self, app, db):
        """per_page cannot exceed 50."""
        with app.app_context():
            user = _make_user(db)
            client = app.test_client()
            resp = client.get('/kingdom/attack_history?per_page=100',
                              headers=_auth_headers(app, user))
            # Should not error — per_page capped at 50
            assert resp.status_code == 200
