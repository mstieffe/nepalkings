# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for onboarding state, rewards, and counters."""

from werkzeug.security import generate_password_hash

from models import CollectionCard, Land, LandAttackLog, User


def _add_cards(db, user_id, suit='Hearts', rank='10', value=10, count=1):
    for _ in range(count):
        db.session.add(CollectionCard(
            user_id=user_id, suit=suit, rank=rank, value=value, locked=False))
    db.session.commit()


def _auth_headers(app, user):
    from routes.auth import generate_token
    token = generate_token(user.id)
    return {'Authorization': f'Bearer {token}'}


def test_register_sets_welcome_present_pending(client):
    resp = client.post('/auth/register', data={
        'username': 'onboard_new',
        'password': 'pass123',
    })
    data = resp.get_json()
    assert resp.status_code == 200
    onboarding = data['user']['onboarding']
    assert onboarding['welcome_pending'] is True
    assert onboarding['welcome_seen'] is False
    assert onboarding['starter_present']['booster_packs'] >= 0


def test_existing_user_has_no_pending_welcome(client, two_users):
    u1, _ = two_users
    resp = client.get(f'/auth/get_user?username={u1.username}')
    onboarding = resp.get_json()['user']['onboarding']
    assert onboarding['welcome_pending'] is False
    assert onboarding['welcome_seen'] is False


def test_open_booster_reward_is_verified_and_idempotent(client, db, two_users, auth_headers_user1):
    u1, _ = two_users
    u1.booster_packs = 1
    db.session.commit()

    blocked = client.post('/onboarding/claim_reward', headers=auth_headers_user1,
                          json={'reward_id': 'open_first_main_booster'})
    assert blocked.status_code == 400

    opened = client.post('/collection/open_booster', headers=auth_headers_user1)
    assert opened.status_code == 200

    claimed = client.post('/onboarding/claim_reward', headers=auth_headers_user1,
                          json={'reward_id': 'open_first_main_booster'})
    data = claimed.get_json()
    assert claimed.status_code == 200
    assert data['reward'] == {'booster_packs_side': 1}
    assert data['balances']['booster_packs_side'] == 1

    again = client.post('/onboarding/claim_reward', headers=auth_headers_user1,
                        json={'reward_id': 'open_first_main_booster'})
    data_again = again.get_json()
    assert again.status_code == 200
    assert data_again['already_claimed'] is True
    assert data_again['balances']['booster_packs_side'] == 1


def test_sell_card_marks_step_and_counts_gold_earned(client, db, two_users, auth_headers_user1):
    u1, _ = two_users
    u1.gold = 0
    _add_cards(db, u1.id, count=100)

    sold = client.post('/collection/sell_card', headers=auth_headers_user1,
                       json={'suit': 'Hearts', 'rank': '10', 'quantity': 100})
    assert sold.status_code == 200
    assert sold.get_json()['gold_earned'] == 1000

    state = client.get('/onboarding/state', headers=auth_headers_user1).get_json()['onboarding']
    assert 'sell_first_card' in state['completed_steps']
    assert state['counters']['gold_earned'] == 1000
    assert next(g for g in state['early_goals'] if g['id'] == 'earn_1000_gold')['claimable'] is True

    claimed = client.post('/onboarding/claim_reward', headers=auth_headers_user1,
                          json={'reward_id': 'earn_1000_gold'})
    data = claimed.get_json()
    assert claimed.status_code == 200
    assert data['reward'] == {'booster_packs': 1}
    assert data['onboarding']['counters']['gold_earned'] == 1000


def test_conquer_five_lands_uses_attack_log_and_grants_maps(client, db):
    user = User(username='conqueror', password_hash=generate_password_hash('pass123'), gold=0)
    db.session.add(user)
    db.session.commit()
    headers = _auth_headers(client.application, user)
    for idx in range(5):
        land = Land(col=idx, row=0, tier=1, gold_rate=1.0,
                    suit_bonus_suit='Hearts', suit_bonus_value=1)
        db.session.add(land)
        db.session.flush()
        db.session.add(LandAttackLog(
            land_id=land.id,
            attacker_user_id=user.id,
            defender_user_id=None,
            result='attacker_won',
        ))
    db.session.commit()

    state = client.get('/onboarding/state', headers=headers).get_json()['onboarding']
    goal = next(g for g in state['early_goals'] if g['id'] == 'conquer_5_lands')
    assert goal['claimable'] is True

    claimed = client.post('/onboarding/claim_reward', headers=headers,
                          json={'reward_id': 'conquer_5_lands'})
    data = claimed.get_json()
    assert claimed.status_code == 200
    assert data['reward'] == {'maps': 2}
    assert data['balances']['maps'] == 2


def test_skip_and_reset_do_not_clear_claimed_rewards(client, db, two_users, auth_headers_user1):
    u1, _ = two_users
    u1.booster_packs = 1
    db.session.commit()
    client.post('/collection/open_booster', headers=auth_headers_user1)
    client.post('/onboarding/claim_reward', headers=auth_headers_user1,
                json={'reward_id': 'open_first_main_booster'})

    skipped = client.post('/onboarding/skip', headers=auth_headers_user1).get_json()['onboarding']
    assert skipped['onboarding_skipped'] is True

    reset = client.post('/onboarding/reset', headers=auth_headers_user1).get_json()['onboarding']
    assert reset['onboarding_skipped'] is False
    assert reset['welcome_pending'] is True
    assert 'open_first_main_booster' in reset['claimed_rewards']


def test_menu_hint_marks_are_persisted(client, auth_headers_user1):
    first = client.post('/onboarding/mark_tip', headers=auth_headers_user1,
                        json={'tip_key': 'menu:user_items'})
    data = first.get_json()
    assert first.status_code == 200
    assert data['onboarding']['menu_hints_seen'] == ['user_items']

    marked = client.post('/onboarding/mark_tip', headers=auth_headers_user1,
                         json={'tip_key': 'menu:duel'})
    data = marked.get_json()
    assert marked.status_code == 200
    assert data['onboarding']['menu_hints_seen'] == ['user_items', 'duel']

    response = client.post('/onboarding/mark_tip', headers=auth_headers_user1,
                           json={'tip_key': 'menu:guide_first_duel_reward'})
    assert response.status_code == 200
    data = response.get_json()
    assert data['onboarding']['menu_hints_seen'] == ['user_items', 'duel', 'guide_first_duel_reward']

    post_duel = client.post('/onboarding/mark_tip', headers=auth_headers_user1,
                            json={'tip_key': 'menu:collection_open_main_booster'})
    assert post_duel.status_code == 200
    data = post_duel.get_json()
    assert data['onboarding']['menu_hints_seen'] == [
        'user_items', 'duel', 'guide_first_duel_reward', 'collection_open_main_booster'
    ]

    duel = client.post('/onboarding/mark_tip', headers=auth_headers_user1,
                       json={'tip_key': 'duel:change_cards'})
    assert duel.status_code == 200
    data = duel.get_json()
    assert data['onboarding']['duel_hints_seen'] == ['change_cards']

    unknown = client.post('/onboarding/mark_tip', headers=auth_headers_user1,
                          json={'tip_key': 'menu:unknown'})
    assert unknown.status_code == 400
