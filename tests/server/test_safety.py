# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.

from datetime import datetime, timedelta, timezone

from models import Kingdom, KingdomMessage, SafetyReport, UserBlock


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def test_user_report_queue_and_own_status(
        client, db, two_users, auth_headers_user1):
    user1, user2 = two_users
    response = client.post(
        '/safety/reports',
        headers=auth_headers_user1,
        json={
            'username': user2.username,
            'reason': 'harassment',
            'details': 'Repeated unwanted messages.',
        },
    )
    assert response.status_code == 201
    payload = response.get_json()
    assert payload['success'] is True
    assert payload['report']['reported_user_id'] == user2.id

    row = db.session.get(SafetyReport, payload['report']['id'])
    assert row.reporter_user_id == user1.id
    assert row.evidence == {'reported_username': user2.username}
    assert row.status == 'open'

    listing = client.get(
        '/safety/reports',
        headers=auth_headers_user1,
    ).get_json()
    assert [report['id'] for report in listing['reports']] == [row.id]
    assert 'details' not in listing['reports'][0]
    assert 'evidence' not in listing['reports'][0]


def test_message_report_snapshots_only_visible_evidence(
        client, db, two_users, auth_headers_user1):
    user1, user2 = two_users
    message = KingdomMessage(
        sender_user_id=user2.id,
        recipient_user_id=user1.id,
        message='reported content',
    )
    db.session.add(message)
    db.session.commit()

    response = client.post(
        '/safety/reports',
        headers=auth_headers_user1,
        json={
            'reported_user_id': user2.id,
            'reason': 'spam',
            'context_type': 'kingdom_message',
            'context_id': message.id,
        },
    )
    assert response.status_code == 201
    row = db.session.get(
        SafetyReport, response.get_json()['report']['id'])
    assert row.evidence['message'] == 'reported content'
    assert row.evidence['sender_user_id'] == user2.id

    wrong_target = client.post(
        '/safety/reports',
        headers=auth_headers_user1,
        json={
            'reported_user_id': user1.id,
            'reason': 'spam',
            'context_type': 'kingdom_message',
            'context_id': message.id,
        },
    )
    assert wrong_target.status_code == 400


def test_kingdom_name_report_validates_owner_and_snapshots_name(
        client, db, two_users, auth_headers_user1):
    user1, user2 = two_users
    kingdom = Kingdom(
        owner_user_id=user2.id,
        name='Reported Kingdom Name',
        badge_key='badge_default',
        border_key='border_default',
        surface_key='surface_default',
    )
    db.session.add(kingdom)
    db.session.commit()

    response = client.post(
        '/safety/reports',
        headers=auth_headers_user1,
        json={
            'reported_user_id': user2.id,
            'reason': 'inappropriate_name',
            'context_type': 'kingdom_name',
            'context_id': kingdom.id,
        },
    )

    assert response.status_code == 201
    row = db.session.get(
        SafetyReport, response.get_json()['report']['id'])
    assert row.evidence == {
        'kingdom_id': kingdom.id,
        'owner_user_id': user2.id,
        'kingdom_name': 'Reported Kingdom Name',
    }

    wrong_owner = client.post(
        '/safety/reports',
        headers=auth_headers_user1,
        json={
            'reported_user_id': user1.id,
            'reason': 'inappropriate_name',
            'context_type': 'kingdom_name',
            'context_id': kingdom.id,
        },
    )
    assert wrong_owner.status_code == 400


def test_block_hides_kingdom_messages_and_stops_direct_contact(
        client, db, two_users, auth_headers_user1, auth_headers_user2):
    user1, user2 = two_users
    old_message = KingdomMessage(
        sender_user_id=user2.id,
        recipient_user_id=user1.id,
        message='old contact',
    )
    db.session.add(old_message)
    db.session.commit()

    blocked = client.post(
        '/safety/blocks',
        headers=auth_headers_user1,
        json={'username': user2.username},
    )
    assert blocked.status_code == 200
    assert UserBlock.query.filter_by(
        blocker_user_id=user1.id,
        blocked_user_id=user2.id,
    ).count() == 1

    inbox = client.get(
        '/kingdom/messages',
        headers=auth_headers_user1,
    ).get_json()
    assert inbox['messages'] == []
    assert inbox['unread_count'] == 0

    send = client.post(
        '/kingdom/messages',
        headers=auth_headers_user2,
        json={
            'recipient_user_id': user1.id,
            'message': 'new contact',
        },
    )
    assert send.status_code == 403
    assert send.get_json()['reason'] == 'player_blocked'

    challenge = client.post(
        '/challenges/create_challenge',
        headers=auth_headers_user2,
        data={
            'challenger': user2.username,
            'opponent': user1.username,
            'stake': 1,
        },
    )
    assert challenge.status_code == 403
    assert challenge.get_json()['reason'] == 'player_unavailable'

    unblocked = client.post(
        '/safety/blocks/remove',
        headers=auth_headers_user1,
        json={'user_id': user2.id},
    )
    assert unblocked.status_code == 200
    inbox = client.get(
        '/kingdom/messages',
        headers=auth_headers_user1,
    ).get_json()
    assert [item['id'] for item in inbox['messages']] == [old_message.id]


def test_chat_mute_blocks_both_chat_surfaces(
        client, db, two_users, auth_headers_user1):
    user1, user2 = two_users
    user1.chat_muted_until = _now() + timedelta(hours=1)
    db.session.commit()

    response = client.post(
        '/kingdom/messages',
        headers=auth_headers_user1,
        json={
            'recipient_user_id': user2.id,
            'message': 'not sent',
        },
    )
    assert response.status_code == 403
    assert response.get_json()['reason'] == 'chat_muted'


def test_invalid_report_reason_and_self_actions_are_rejected(
        client, two_users, auth_headers_user1):
    user1, _ = two_users
    bad_reason = client.post(
        '/safety/reports',
        headers=auth_headers_user1,
        json={'username': 'player2', 'reason': 'made_up'},
    )
    assert bad_reason.status_code == 400
    assert 'valid_reasons' in bad_reason.get_json()

    self_block = client.post(
        '/safety/blocks',
        headers=auth_headers_user1,
        json={'user_id': user1.id},
    )
    assert self_block.status_code == 400
