# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for onboarding state, rewards, and counters."""

from werkzeug.security import generate_password_hash

from models import CollectionCard, Game, GameResult, Land, LandAttackLog, User


def _add_cards(db, user_id, suit='Hearts', rank='10', value=10, count=1):
    for _ in range(count):
        db.session.add(CollectionCard(
            user_id=user_id, suit=suit, rank=rank, value=value, locked=False))
    db.session.commit()


def _add_game_result(db, winner, loser):
    game = Game(state='finished', mode='duel')
    db.session.add(game)
    db.session.flush()
    db.session.add(GameResult(
        game_id=game.id,
        winner_user_id=winner.id,
        loser_user_id=loser.id,
        winner_username=winner.username,
        loser_username=loser.username,
        winner_score=45,
        loser_score=20,
        stake=45,
        gold_awarded=90,
        rounds_played=3,
    ))


def _auth_headers(app, user):
    from routes.auth import generate_token
    token = generate_token(user.id)
    return {'Authorization': f'Bearer {token}'}


def test_register_sets_welcome_present_pending(client):
    resp = client.post('/auth/register', data={
        'username': 'onboard_new',
        'password': 'pass1234',
        'age_confirmed': 'true',
        'terms_accepted': 'true',
        'privacy_accepted': 'true',
    })
    data = resp.get_json()
    assert resp.status_code == 200
    onboarding = data['user']['onboarding']
    assert onboarding['welcome_pending'] is True
    assert onboarding['welcome_seen'] is False
    assert onboarding['starter_present']['booster_packs'] >= 0


def test_existing_user_has_no_pending_welcome(client, two_users):
    u1, _ = two_users
    resp = client.get(
        f'/auth/get_user?username={u1.username}',
        headers=_auth_headers(None, u1),
    )
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


def test_duel_count_goals_use_game_results(client, db, two_users, auth_headers_user1):
    u1, u2 = two_users
    u1.gold = 0
    u1.booster_packs = 0
    u1.booster_packs_side = 0
    for _ in range(10):
        _add_game_result(db, u1, u2)
    for _ in range(10):
        _add_game_result(db, u2, u1)
    db.session.commit()

    state = client.get('/onboarding/state', headers=auth_headers_user1).get_json()['onboarding']
    goals = {g['id']: g for g in state['early_goals']}
    assert goals['finish_10_duels']['claimable'] is True
    assert goals['win_5_duels']['claimable'] is True
    assert goals['win_10_duels']['claimable'] is True
    assert goals['lose_5_duels']['claimable'] is True
    assert goals['lose_10_duels']['claimable'] is True
    assert state['facts']['duel_losses'] == 10

    claimed_win = client.post('/onboarding/claim_reward', headers=auth_headers_user1,
                              json={'reward_id': 'win_10_duels'})
    data_win = claimed_win.get_json()
    assert claimed_win.status_code == 200
    assert data_win['reward'] == {'booster_packs': 3}
    assert data_win['balances']['booster_packs'] == 3

    claimed_loss = client.post('/onboarding/claim_reward', headers=auth_headers_user1,
                               json={'reward_id': 'lose_10_duels'})
    data_loss = claimed_loss.get_json()
    assert claimed_loss.status_code == 200
    assert data_loss['reward'] == {'booster_packs_side': 2}
    assert data_loss['balances']['booster_packs_side'] == 2


def test_conquer_lands_uses_attack_log_and_grants_gold_rewards(client, db):
    user = User(username='conqueror', password_hash=generate_password_hash('pass123'), gold=0)
    db.session.add(user)
    db.session.commit()
    headers = _auth_headers(client.application, user)
    for idx in range(25):
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
    goals = {g['id']: g for g in state['early_goals']}
    assert goals['conquer_5_lands']['claimable'] is True
    assert goals['conquer_10_lands']['claimable'] is True
    assert goals['conquer_20_lands']['claimable'] is True
    assert goals['conquer_25_lands']['claimable'] is True
    assert goals['finish_10_conquer_battles']['claimable'] is True
    assert goals['conquer_10_lands']['cosmetic_unlock_hint'] == 'sigil_tower'
    assert 'cosmetic_unlock_hint' not in goals['conquer_20_lands']
    assert goals['conquer_25_lands']['cosmetic_unlock_hint'] == 'sigil_serpent'

    claimed = client.post('/onboarding/claim_reward', headers=headers,
                          json={'reward_id': 'conquer_5_lands'})
    data = claimed.get_json()
    assert claimed.status_code == 200
    assert data['reward'] == {'gold': 500}
    assert data['balances']['gold'] == 500

    claimed_20 = client.post('/onboarding/claim_reward', headers=headers,
                             json={'reward_id': 'conquer_20_lands'})
    data_20 = claimed_20.get_json()
    assert claimed_20.status_code == 200
    assert data_20['reward'] == {'gold': 2000}
    assert data_20['balances']['gold'] == 2500

    claimed_25 = client.post('/onboarding/claim_reward', headers=headers,
                             json={'reward_id': 'conquer_25_lands'})
    data_25 = claimed_25.get_json()
    assert claimed_25.status_code == 200
    assert data_25['reward'] == {'gold': 2500}
    assert data_25['balances']['gold'] == 5000


def test_earn_10000_gold_goal_is_claimable(client, db, two_users, auth_headers_user1):
    u1, _ = two_users
    u1.gold = 0
    _add_cards(db, u1.id, count=1000)

    sold = client.post('/collection/sell_card', headers=auth_headers_user1,
                       json={'suit': 'Hearts', 'rank': '10', 'quantity': 1000})
    assert sold.status_code == 200
    assert sold.get_json()['gold_earned'] == 10000

    state = client.get('/onboarding/state', headers=auth_headers_user1).get_json()['onboarding']
    goals = {g['id']: g for g in state['early_goals']}
    assert goals['earn_1000_gold']['claimable'] is True
    assert goals['earn_10000_gold']['claimable'] is True

    claimed = client.post('/onboarding/claim_reward', headers=auth_headers_user1,
                          json={'reward_id': 'earn_10000_gold'})
    data = claimed.get_json()
    assert claimed.status_code == 200
    assert data['reward'] == {'booster_packs': 10}
    assert data['balances']['booster_packs'] == 10


def test_skip_and_reset_do_not_clear_claimed_rewards(client, db, two_users, auth_headers_user1):
    u1, _ = two_users
    u1.booster_packs = 1
    db.session.commit()
    client.post('/collection/open_booster', headers=auth_headers_user1)
    client.post('/onboarding/claim_reward', headers=auth_headers_user1,
                json={'reward_id': 'open_first_main_booster'})

    skipped = client.post('/onboarding/skip', headers=auth_headers_user1).get_json()['onboarding']
    assert skipped['onboarding_skipped'] is True

    resumed = client.post('/onboarding/resume', headers=auth_headers_user1).get_json()['onboarding']
    assert resumed['onboarding_skipped'] is False
    assert 'open_first_main_booster' in resumed['claimed_rewards']

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

    collection_intro = client.post('/onboarding/mark_tip', headers=auth_headers_user1,
                                   json={'tip_key': 'menu:collection_starter_cards'})
    assert collection_intro.status_code == 200
    data = collection_intro.get_json()
    assert data['onboarding']['menu_hints_seen'] == [
        'user_items', 'duel', 'guide_first_duel_reward', 'collection_starter_cards'
    ]

    post_duel = client.post('/onboarding/mark_tip', headers=auth_headers_user1,
                            json={'tip_key': 'menu:collection_open_main_booster'})
    assert post_duel.status_code == 200
    data = post_duel.get_json()
    assert data['onboarding']['menu_hints_seen'] == [
        'user_items', 'duel', 'guide_first_duel_reward',
        'collection_starter_cards', 'collection_open_main_booster'
    ]

    newest = client.post('/onboarding/mark_tip', headers=auth_headers_user1,
                         json={'tip_key': 'menu:kingdom_config_shields_style'})
    assert newest.status_code == 200

    earlier_new = client.post('/onboarding/mark_tip', headers=auth_headers_user1,
                              json={'tip_key': 'menu:conquer_battle_timeline_intro'})
    assert earlier_new.status_code == 200

    middle_new = client.post('/onboarding/mark_tip', headers=auth_headers_user1,
                             json={'tip_key': 'menu:kingdom_after_conquer_map'})
    assert middle_new.status_code == 200
    data = middle_new.get_json()
    assert data['onboarding']['menu_hints_seen'] == [
        'user_items',
        'duel',
        'guide_first_duel_reward',
        'collection_starter_cards',
        'collection_open_main_booster',
        'conquer_battle_timeline_intro',
        'kingdom_after_conquer_map',
        'kingdom_config_shields_style',
    ]

    duel = client.post('/onboarding/mark_tip', headers=auth_headers_user1,
                       json={'tip_key': 'duel:change_cards'})
    assert duel.status_code == 200
    data = duel.get_json()
    assert data['onboarding']['duel_hints_seen'] == ['change_cards']

    unknown = client.post('/onboarding/mark_tip', headers=auth_headers_user1,
                          json={'tip_key': 'menu:unknown'})
    assert unknown.status_code == 400


def test_finish_tutorial_reward_unlocks_on_last_menu_hint(client, db, two_users, auth_headers_user1):
    u1, u2 = two_users
    u1.booster_packs = 0
    db.session.commit()

    initial = client.get('/onboarding/state', headers=auth_headers_user1).get_json()['onboarding']
    initial_steps = {step['id']: step for step in initial['core_steps']}
    assert initial_steps['finish_tutorial']['title'] == 'Finish first-session tutorial'
    assert initial_steps['finish_tutorial']['reward'] == {'booster_packs': 6}
    assert initial_steps['finish_tutorial']['completed'] is False
    assert initial_steps['finish_tutorial']['claimable'] is False

    marked = client.post('/onboarding/mark_tip', headers=auth_headers_user1,
                         json={'tip_key': 'menu:kingdom_config_shields_style'})
    data = marked.get_json()
    assert marked.status_code == 200
    steps = {step['id']: step for step in data['onboarding']['core_steps']}
    assert 'finish_tutorial' not in data['onboarding']['completed_steps']
    assert steps['finish_tutorial']['completed'] is False
    assert steps['finish_tutorial']['claimable'] is False

    from onboarding_service import mark_step
    mark_step(u1, 'finish_first_conquer_battle')
    _add_game_result(db, u1, u2)
    db.session.commit()

    finished = client.get('/onboarding/state', headers=auth_headers_user1).get_json()['onboarding']
    steps = {step['id']: step for step in finished['core_steps']}
    assert 'finish_tutorial' in finished['completed_steps']
    assert steps['finish_tutorial']['completed'] is True
    assert steps['finish_tutorial']['claimable'] is True

    claimed = client.post('/onboarding/claim_reward', headers=auth_headers_user1,
                          json={'reward_id': 'finish_tutorial'})
    claim_data = claimed.get_json()
    assert claimed.status_code == 200
    assert claim_data['reward'] == {'booster_packs': 6}
    assert claim_data['balances']['booster_packs'] == 6
    assert 'finish_tutorial' in claim_data['onboarding']['claimed_rewards']
