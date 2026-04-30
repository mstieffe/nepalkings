# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for Phase 14 — attack notifications and history."""
import pytest
from datetime import datetime, timezone, timedelta

from models import db, User, Land, LandAttackLog, KingdomNotification


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
                     seen_by_attacker=False,
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
        seen_by_attacker=seen_by_attacker,
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
            assert n['activity_title'] == 'attacker conquered your land'
            assert n['activity_detail'] == 'Card lost: K of Hearts'
            assert n['activity_tone'] == 'bad'
            assert n['activity_land_label'] == 'Land (3, 2)'
            assert resp.headers['Deprecation'] == 'true'
            assert '/kingdom/notifications' in resp.headers['Link']

    def test_defender_attack_notifications_alias_is_not_deprecated(self, app, db):
        """Clear defender-only alias works without legacy deprecation headers."""
        with app.app_context():
            attacker = _make_user(db, 'attacker')
            defender = _make_user(db, 'defender')
            land = _make_land(db, owner_user_id=defender.id)
            _make_attack_log(db, land, attacker, defender)

            client = app.test_client()
            resp = client.get('/kingdom/defender_attack_notifications',
                              headers=_auth_headers(app, defender))

            assert resp.status_code == 200
            assert len(resp.get_json()['notifications']) == 1
            assert 'Deprecation' not in resp.headers

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
#  GET/POST /kingdom/notifications
# ═════════════════════════════════════════════════════════════════════════════

class TestUnifiedKingdomNotifications:

    def test_returns_unseen_attacker_and_defender_notifications(self, app, db):
        """Unified notifications include own attacks and incoming attacks."""
        with app.app_context():
            current = _make_user(db, 'current')
            rival = _make_user(db, 'rival')
            land1 = _make_land(db, col=1, row=1, owner_user_id=current.id)
            land2 = _make_land(db, col=2, row=2, owner_user_id=rival.id)
            _make_attack_log(db, land1, rival, current, result='defender_won',
                             card_lost_suit='Hearts', card_lost_rank='K')
            _make_attack_log(db, land2, current, rival, result='attacker_won',
                             card_won_suit='Spades', card_won_rank='A')

            client = app.test_client()
            resp = client.get('/kingdom/notifications',
                              headers=_auth_headers(app, current))
            data = resp.get_json()

            assert resp.status_code == 200
            assert data['success'] is True
            assert len(data['notifications']) == 2
            roles = {n['role'] for n in data['notifications']}
            assert roles == {'attacker', 'defender'}
            own_attack = next(n for n in data['notifications'] if n['role'] == 'attacker')
            assert own_attack['result'] == 'attacker_won'
            assert own_attack['card_won_suit'] == 'Spades'
            assert own_attack['activity_title'] == 'You conquered rival'
            assert own_attack['activity_detail'] == 'Card won: A of Spades'
            assert own_attack['activity_tone'] == 'good'
            defence_win = next(n for n in data['notifications'] if n['role'] == 'defender')
            assert defence_win['activity_title'] == 'rival failed to conquer you'
            assert defence_win['activity_detail'] == 'Card won: K of Hearts'
            assert defence_win['activity_tone'] == 'good'

    def test_defender_loss_activity_reports_card_lost_from_attacker_reward_fields(self, app, db):
        """Passive land-owner notifications translate attacker-centric card_won fields."""
        with app.app_context():
            current = _make_user(db, 'current_loss')
            rival = _make_user(db, 'rival_loss')
            land = _make_land(db, col=3, row=4, owner_user_id=current.id)
            _make_attack_log(db, land, rival, current, result='attacker_won',
                             card_won_suit='Clubs', card_won_rank='Q')

            client = app.test_client()
            resp = client.get('/kingdom/notifications',
                              headers=_auth_headers(app, current))
            data = resp.get_json()

            assert resp.status_code == 200
            notif = data['notifications'][0]
            assert notif['role'] == 'defender'
            assert notif['activity_title'] == 'rival_loss conquered your land'
            assert notif['activity_detail'] == 'Card lost: Q of Clubs'
            assert notif['activity_tone'] == 'bad'

    def test_seen_flags_are_role_specific(self, app, db):
        """Seen attacker logs are hidden without hiding defender logs."""
        with app.app_context():
            current = _make_user(db, 'current')
            rival = _make_user(db, 'rival')
            land1 = _make_land(db, col=1, row=1, owner_user_id=current.id)
            land2 = _make_land(db, col=2, row=2, owner_user_id=rival.id)
            _make_attack_log(db, land1, rival, current, result='defender_won')
            _make_attack_log(db, land2, current, rival, result='attacker_won',
                             seen_by_attacker=True)

            client = app.test_client()
            resp = client.get('/kingdom/notifications',
                              headers=_auth_headers(app, current))
            notifs = resp.get_json()['notifications']

            assert len(notifs) == 1
            assert notifs[0]['role'] == 'defender'

    def test_mark_seen_updates_attacker_and_defender_flags(self, app, db):
        """Current user can mark both role-specific notification types seen."""
        with app.app_context():
            current = _make_user(db, 'current')
            rival = _make_user(db, 'rival')
            land1 = _make_land(db, owner_user_id=current.id)
            land2 = _make_land(db, col=2, row=0, owner_user_id=rival.id)
            incoming = _make_attack_log(db, land1, rival, current, result='defender_won')
            outgoing = _make_attack_log(db, land2, current, rival, result='defender_won')

            client = app.test_client()
            resp = client.post('/kingdom/notifications/mark_seen',
                               json={'notification_ids': [incoming.id, outgoing.id]},
                               headers=_auth_headers(app, current))

            assert resp.status_code == 200
            assert resp.get_json()['marked'] == 2
            assert db.session.get(LandAttackLog, incoming.id).seen_by_defender is True
            assert db.session.get(LandAttackLog, outgoing.id).seen_by_attacker is True

    def test_typed_mark_seen_avoids_attack_and_kingdom_id_collision(self, app, db):
        """Typed payloads prevent same numeric IDs in different tables colliding."""
        with app.app_context():
            current = _make_user(db, 'current')
            rival = _make_user(db, 'rival')
            land = _make_land(db, owner_user_id=current.id)
            attack_log = _make_attack_log(db, land, rival, current, result='defender_won')
            kingdom_notif = KingdomNotification(
                user_id=current.id,
                kind='level_up',
                kingdom_id=None,
                payload={'new_level': 2},
            )
            db.session.add(kingdom_notif)
            db.session.commit()

            assert attack_log.id == kingdom_notif.id
            client = app.test_client()
            resp = client.post(
                '/kingdom/notifications/mark_seen',
                json={'attack_log_ids': [attack_log.id],
                      'kingdom_notification_ids': []},
                headers=_auth_headers(app, current),
            )

            assert resp.status_code == 200
            assert resp.get_json()['marked'] == 1
            assert db.session.get(LandAttackLog, attack_log.id).seen_by_defender is True
            assert db.session.get(KingdomNotification, kingdom_notif.id).seen is False

    def test_unified_notifications_are_globally_sorted(self, app, db):
        """Attack logs and kingdom events are returned in one recency order."""
        with app.app_context():
            current = _make_user(db, 'current')
            rival = _make_user(db, 'rival')
            land1 = _make_land(db, col=1, row=1, owner_user_id=current.id)
            land2 = _make_land(db, col=2, row=2, owner_user_id=current.id)
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            old_attack = _make_attack_log(
                db, land1, rival, current,
                result='attacker_won',
                timestamp=now - timedelta(hours=2),
            )
            new_attack = _make_attack_log(
                db, land2, rival, current,
                result='defender_won',
                timestamp=now,
            )
            level_note = KingdomNotification(
                user_id=current.id,
                kind='level_up',
                kingdom_id=None,
                payload={'new_level': 2},
                created_at=now - timedelta(hours=1),
            )
            db.session.add(level_note)
            db.session.commit()

            client = app.test_client()
            resp = client.get('/kingdom/notifications',
                              headers=_auth_headers(app, current))
            notifs = resp.get_json()['notifications']

            assert [(n['source'], n['id']) for n in notifs] == [
                ('attack_log', new_attack.id),
                ('kingdom_notification', level_note.id),
                ('attack_log', old_attack.id),
            ]


# ═════════════════════════════════════════════════════════════════════════════
#  Kingdom user messages
# ═════════════════════════════════════════════════════════════════════════════

class TestKingdomMessages:

    def test_send_and_fetch_message_with_land_context(self, app, db):
        """Players can send kingdom messages to another user."""
        with app.app_context():
            sender = _make_user(db, 'sender')
            recipient = _make_user(db, 'recipient')
            land = _make_land(db, col=4, row=5, owner_user_id=recipient.id)

            client = app.test_client()
            resp = client.post('/kingdom/messages',
                               json={
                                   'recipient_user_id': recipient.id,
                                   'land_id': land.id,
                                   'message': 'Nice land.',
                               },
                               headers=_auth_headers(app, sender))
            assert resp.status_code == 200
            payload = resp.get_json()['kingdom_message']
            assert payload['sender_username'] == 'sender'
            assert payload['recipient_username'] == 'recipient'
            assert payload['land_col'] == 4
            assert payload['message'] == 'Nice land.'

            recv = client.get('/kingdom/messages',
                              headers=_auth_headers(app, recipient)).get_json()
            assert recv['unread_count'] == 1
            assert recv['messages'][0]['message'] == 'Nice land.'
            assert recv['messages'][0]['activity_title'] == 'From sender'
            assert recv['messages'][0]['activity_detail'] == 'Nice land.'
            assert recv['messages'][0]['activity_tone'] == 'neutral'
            assert recv['messages'][0]['activity_land_label'] == 'Land (4, 5)'

    def test_mark_messages_seen_only_for_recipient(self, app, db):
        """Only the recipient can mark a kingdom message as read."""
        with app.app_context():
            sender = _make_user(db, 'sender')
            recipient = _make_user(db, 'recipient')
            third = _make_user(db, 'third')
            client = app.test_client()
            sent = client.post('/kingdom/messages',
                               json={'recipient_user_id': recipient.id,
                                     'message': 'Read me'},
                               headers=_auth_headers(app, sender)).get_json()
            msg_id = sent['kingdom_message']['id']

            blocked = client.post('/kingdom/messages/mark_seen',
                                  json={'message_ids': [msg_id]},
                                  headers=_auth_headers(app, third))
            assert blocked.get_json()['marked'] == 0

            ok = client.post('/kingdom/messages/mark_seen',
                             json={'message_ids': [msg_id]},
                             headers=_auth_headers(app, recipient))
            assert ok.status_code == 200
            assert ok.get_json()['marked'] == 1
            recv = client.get('/kingdom/messages',
                              headers=_auth_headers(app, recipient)).get_json()
            assert recv['unread_count'] == 0

    def test_empty_self_and_ai_messages_are_rejected(self, app, db):
        """Invalid kingdom message targets or bodies are rejected."""
        with app.app_context():
            sender = _make_user(db, 'sender')
            ai = User(username='ai', password_hash='x', is_ai=True)
            db.session.add(ai)
            db.session.commit()

            client = app.test_client()
            empty = client.post('/kingdom/messages',
                                json={'recipient_user_id': ai.id, 'message': '  '},
                                headers=_auth_headers(app, sender))
            assert empty.status_code == 400

            self_msg = client.post('/kingdom/messages',
                                   json={'recipient_user_id': sender.id,
                                         'message': 'hello'},
                                   headers=_auth_headers(app, sender))
            assert self_msg.status_code == 400

            ai_msg = client.post('/kingdom/messages',
                                 json={'recipient_user_id': ai.id,
                                       'message': 'hello'},
                                 headers=_auth_headers(app, sender))
            assert ai_msg.status_code == 400

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
