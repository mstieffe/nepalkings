# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for onboarding state, rewards, and counters."""

from datetime import datetime

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


def _add_conquer_win(db, attacker, *, col=900):
    land = Land(
        col=col, row=0, tier=1, gold_rate=1.0,
        suit_bonus_suit='Hearts', suit_bonus_value=1,
    )
    db.session.add(land)
    db.session.flush()
    db.session.add(LandAttackLog(
        land_id=land.id,
        attacker_user_id=attacker.id,
        defender_user_id=None,
        result='attacker_won',
    ))
    db.session.commit()


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
    assert onboarding['coach_version'] == 'first_session_v6'
    assert onboarding['journey_phase'] == 'reveal_starter_cards'
    assert onboarding['next_action'] == {
        'screen': 'collection',
        'label': 'Reveal Starter Cards',
        'target_id': 'starter_suit_reveal',
    }
    assert onboarding['welcome_pending'] is True
    assert onboarding['welcome_seen'] is False
    assert onboarding['starter_present']['booster_packs'] >= 0


def test_welcome_grants_no_items_and_defers_starter_cards_to_roulette(client, db):
    response = client.post('/auth/register', data={
        'username': 'starter_ready',
        'password': 'pass1234',
        'age_confirmed': 'true',
        'terms_accepted': 'true',
        'privacy_accepted': 'true',
    })
    assert response.status_code == 200
    user = User.query.filter_by(username='starter_ready').one()
    headers = _auth_headers(None, user)

    marked = client.post(
        '/onboarding/mark_tip', headers=headers,
        json={'tip_key': 'welcome'},
    )
    data = marked.get_json()

    assert marked.status_code == 200
    assert data['balances'] == {
        'gold': 0, 'booster_packs': 0,
        'booster_packs_side': 0, 'maps': 0}
    assert data['onboarding']['starter_set_granted'] is False
    assert data['onboarding']['starter_suits'] == {}
    assert CollectionCard.query.filter_by(user_id=user.id).count() == 0


def test_starter_cards_grant_only_after_roulette_completion(client, db):
    response = client.post('/auth/register', data={
        'username': 'roulette_ready',
        'password': 'pass1234',
        'age_confirmed': 'true',
        'terms_accepted': 'true',
        'privacy_accepted': 'true',
    })
    assert response.status_code == 200
    user = User.query.filter_by(username='roulette_ready').one()
    headers = _auth_headers(None, user)

    client.post('/onboarding/mark_tip', headers=headers,
                json={'tip_key': 'welcome'})
    prepared = client.post(
        '/onboarding/starter_reveal/prepare', headers=headers)
    prepared_data = prepared.get_json()

    assert prepared.status_code == 200
    assert prepared_data['suit'] in ('Hearts', 'Diamonds')
    assert prepared_data['onboarding']['starter_set_granted'] is False
    assert CollectionCard.query.filter_by(user_id=user.id).count() == 0

    blocked = client.post(
        '/onboarding/starter_reveal/complete', headers=headers)
    assert blocked.status_code == 400
    assert CollectionCard.query.filter_by(user_id=user.id).count() == 0

    client.post('/onboarding/mark_tip', headers=headers,
                json={'tip_keys': [
                    'menu:collection_basics_window',
                    'menu:starter_cards_present_window',
                ]})
    completed = client.post(
        '/onboarding/starter_reveal/complete', headers=headers)
    completed_data = completed.get_json()

    assert completed.status_code == 200
    assert completed_data['onboarding']['starter_set_granted'] is True
    assert 'starter_suit_reveal' in (
        completed_data['onboarding']['menu_hints_seen'])
    assert CollectionCard.query.filter_by(user_id=user.id).count() == 10
    assert sum(card['total'] for card in completed_data['starter_cards']) == 10
    assert (user.gold, user.booster_packs,
            user.booster_packs_side, user.maps) == (0, 0, 0, 0)

    repeated = client.post(
        '/onboarding/starter_reveal/complete', headers=headers)
    assert repeated.status_code == 200
    assert CollectionCard.query.filter_by(user_id=user.id).count() == 10


def test_journey_metadata_progresses_with_first_session_steps(db, two_users):
    from onboarding_service import mark_menu_hint, mark_step, serialize_onboarding_state
    u1, _ = two_users

    onboarding = serialize_onboarding_state(u1)
    assert onboarding['journey_phase'] == 'reveal_starter_cards'
    assert onboarding['next_action']['screen'] == 'collection'

    mark_menu_hint(u1, 'starter_suit_reveal')
    onboarding = serialize_onboarding_state(u1)
    assert onboarding['journey_phase'] == 'first_conquest'
    assert onboarding['next_action'] == {
        'screen': 'kingdom',
        'label': 'Conquer First Land',
        'target_id': 'recommended_tutorial_land',
    }

    mark_step(u1, 'finish_first_conquer_battle')
    onboarding = serialize_onboarding_state(u1)
    assert onboarding['journey_phase'] == 'finish_tutorial'
    assert onboarding['next_action']['screen'] == 'kingdom'

    mark_step(u1, 'finish_tutorial')
    onboarding = serialize_onboarding_state(u1)
    assert onboarding['journey_phase'] == 'complete'
    assert onboarding['next_action'] is None


def test_existing_user_has_no_pending_welcome(client, two_users):
    u1, _ = two_users
    resp = client.get(
        f'/auth/get_user?username={u1.username}',
        headers=_auth_headers(None, u1),
    )
    onboarding = resp.get_json()['user']['onboarding']
    assert onboarding['welcome_pending'] is False
    assert onboarding['welcome_seen'] is False


def test_open_booster_is_not_a_first_journey_reward(client, db, two_users, auth_headers_user1):
    u1, _ = two_users
    u1.booster_packs = 1
    db.session.commit()

    blocked = client.post('/onboarding/claim_reward', headers=auth_headers_user1,
                          json={'reward_id': 'open_first_main_booster'})
    assert blocked.status_code == 404

    opened = client.post('/collection/open_booster', headers=auth_headers_user1)
    assert opened.status_code == 200
    assert 'open_first_main_booster' not in (
        opened.get_json()['onboarding']['completed_steps'])

    claimed = client.post('/onboarding/claim_reward', headers=auth_headers_user1,
                          json={'reward_id': 'open_first_main_booster'})
    assert claimed.status_code == 404


def test_sell_card_marks_step_and_counts_gold_earned(client, db, two_users, auth_headers_user1):
    u1, _ = two_users
    from onboarding_service import mark_step
    mark_step(u1, 'finish_tutorial')
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
    from onboarding_service import mark_step
    mark_step(u1, 'finish_tutorial')
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
    from onboarding_service import mark_step
    mark_step(user, 'finish_tutorial')
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
    from onboarding_service import mark_step
    mark_step(u1, 'finish_tutorial')
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
    from onboarding_service import mark_step
    mark_step(u1, 'finish_first_duel', commit=True)
    client.post('/onboarding/claim_reward', headers=auth_headers_user1,
                json={'reward_id': 'finish_first_duel'})
    balances_before_pause = (
        u1.gold, u1.booster_packs, u1.booster_packs_side, u1.maps)

    skipped = client.post('/onboarding/skip', headers=auth_headers_user1).get_json()['onboarding']
    assert skipped['onboarding_skipped'] is True
    db.session.refresh(u1)
    assert (u1.gold, u1.booster_packs, u1.booster_packs_side, u1.maps) == (
        balances_before_pause)
    assert skipped['starter_set_granted'] is False

    resumed = client.post('/onboarding/resume', headers=auth_headers_user1).get_json()['onboarding']
    assert resumed['onboarding_skipped'] is False
    assert 'finish_first_duel' in resumed['claimed_rewards']

    reset = client.post('/onboarding/reset', headers=auth_headers_user1).get_json()['onboarding']
    assert reset['onboarding_skipped'] is False
    assert reset['welcome_pending'] is True
    assert 'finish_first_duel' in reset['claimed_rewards']


def test_menu_hint_marks_are_persisted(client, auth_headers_user1):
    first = client.post('/onboarding/mark_tip', headers=auth_headers_user1,
                        json={'tip_key': 'menu:duel'})
    data = first.get_json()
    assert first.status_code == 200
    assert data['onboarding']['menu_hints_seen'] == ['duel']

    marked = client.post('/onboarding/mark_tip', headers=auth_headers_user1,
                         json={'tip_key': 'menu:guide_first_duel_reward'})
    data = marked.get_json()
    assert marked.status_code == 200
    assert data['onboarding']['menu_hints_seen'] == ['duel', 'guide_first_duel_reward']

    post_duel = client.post('/onboarding/mark_tip', headers=auth_headers_user1,
                            json={'tip_key': 'menu:collection_open_main_booster'})
    assert post_duel.status_code == 200
    data = post_duel.get_json()
    assert data['onboarding']['menu_hints_seen'] == [
        'duel', 'guide_first_duel_reward', 'collection_open_main_booster'
    ]

    # Hints always come back sorted by MENU_HINT_IDS order, not mark order.
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
        'duel',
        'guide_first_duel_reward',
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


def test_finish_tutorial_reward_unlocks_after_final_kingdom_step(client, db, two_users, auth_headers_user1):
    u1, u2 = two_users
    u1.booster_packs = 0
    u1.booster_packs_side = 0
    u1.maps = 0
    u1.gold = 0
    db.session.commit()

    initial = client.get('/onboarding/state', headers=auth_headers_user1).get_json()['onboarding']
    initial_steps = {step['id']: step for step in initial['core_steps']}
    assert initial_steps['finish_tutorial']['title'] == 'Finish the kingdom tour'
    assert initial_steps['finish_tutorial']['reward'] == {
        'gold': 2000, 'booster_packs': 9,
        'booster_packs_side': 4, 'maps': 4}
    assert initial_steps['finish_tutorial']['completed'] is False
    assert initial_steps['finish_tutorial']['claimable'] is False

    _add_conquer_win(db, u1)

    before_finish = client.get('/onboarding/state', headers=auth_headers_user1).get_json()['onboarding']
    assert 'finish_first_conquer_battle' in before_finish['completed_steps']
    assert 'finish_tutorial' not in before_finish['completed_steps']

    completed = client.post(
        '/onboarding/complete_step', headers=auth_headers_user1,
        json={'step_id': 'finish_tutorial'},
    )
    assert completed.status_code == 200
    finished = completed.get_json()['onboarding']
    steps = {step['id']: step for step in finished['core_steps']}
    assert 'finish_tutorial' in finished['completed_steps']
    assert steps['finish_tutorial']['completed'] is True
    assert steps['finish_tutorial']['claimable'] is True

    claimed = client.post('/onboarding/claim_reward', headers=auth_headers_user1,
                          json={'reward_id': 'finish_tutorial'})
    claim_data = claimed.get_json()
    assert claimed.status_code == 200
    assert claim_data['reward'] == {
        'gold': 2000,
        'booster_packs_side': 4,
        'maps': 4,
        'booster_packs': 9,
    }
    assert claim_data['balances']['gold'] == 2000
    assert claim_data['balances']['booster_packs'] == 9
    assert claim_data['balances']['booster_packs_side'] == 4
    assert claim_data['balances']['maps'] == 4
    assert 'finish_tutorial' in claim_data['onboarding']['claimed_rewards']


def test_finish_tutorial_reward_is_idempotent(
        client, db, two_users, auth_headers_user1):
    u1, _ = two_users
    u1.booster_packs = 0
    u1.booster_packs_side = 0
    u1.maps = 0
    db.session.commit()
    _add_conquer_win(db, u1, col=901)
    completed = client.post(
        '/onboarding/complete_step', headers=auth_headers_user1,
        json={'step_id': 'finish_tutorial'},
    )
    assert completed.status_code == 200

    first = client.post(
        '/onboarding/claim_reward', headers=auth_headers_user1,
        json={'reward_id': 'finish_tutorial'},
    )
    again = client.post(
        '/onboarding/claim_reward', headers=auth_headers_user1,
        json={'reward_id': 'finish_tutorial'},
    )

    assert first.status_code == 200
    assert again.status_code == 200
    data = again.get_json()
    assert data['already_claimed'] is True
    assert data['reward'] == {}
    assert data['balances']['booster_packs'] == 9
    assert data['balances']['booster_packs_side'] == 4


def test_finish_tutorial_completion_is_gated_by_real_conquest(
        client, auth_headers_user1):
    response = client.post(
        '/onboarding/complete_step', headers=auth_headers_user1,
        json={'step_id': 'finish_tutorial'},
    )
    assert response.status_code == 400
    assert 'Conquer your first land' in response.get_json()['message']


def test_mark_tip_batch_is_atomic_and_persists_missing_client_ids(
        client, auth_headers_user1):
    response = client.post(
        '/onboarding/mark_tip', headers=auth_headers_user1,
        json={'tip_keys': [
            'menu:open_starter_pack',
            'menu:collection_basics_window',
            'menu:loot_risk_intro',
            'duel:field',
            'duel:game_status',
        ]},
    )
    assert response.status_code == 200
    onboarding = response.get_json()['onboarding']
    assert {'open_starter_pack', 'collection_basics_window', 'loot_risk_intro'}.issubset(
        onboarding['menu_hints_seen'])
    assert onboarding['duel_hints_seen'] == ['field', 'game_status']

    rejected = client.post(
        '/onboarding/mark_tip', headers=auth_headers_user1,
        json={'tip_keys': ['duel:build', 'menu:not-real']},
    )
    assert rejected.status_code == 400
    state = client.get(
        '/onboarding/state', headers=auth_headers_user1).get_json()['onboarding']
    assert 'build' not in state['duel_hints_seen']


def test_starter_assignment_remains_offensive_and_defensive_only(db, two_users):
    import onboarding_service

    user, _ = two_users
    for _ in range(20):
        user.onboarding_state = onboarding_service.default_onboarding_state()
        suits = onboarding_service.assign_starter_suits(user)
        assert suits['offensive'] in {'Hearts', 'Diamonds'}
        assert suits['defensive'] in {'Clubs', 'Spades'}


def test_daily_quest_locked_before_first_conquest(client, auth_headers_user1):
    state = client.get('/onboarding/state', headers=auth_headers_user1).get_json()['onboarding']

    quest = state['daily_quest']
    assert quest['id'] == 'daily_quest'
    assert quest['locked'] is True
    assert quest['claimable'] is False

    blocked = client.post('/onboarding/claim_reward', headers=auth_headers_user1,
                          json={'reward_id': 'daily_quest'})
    assert blocked.status_code == 400


def test_early_goals_stay_locked_until_first_journey_finishes(
        client, auth_headers_user1):
    state = client.get(
        '/onboarding/state', headers=auth_headers_user1).get_json()['onboarding']
    assert state['early_goals']
    assert all(goal.get('locked') is True for goal in state['early_goals'])
    assert all(goal['claimable'] is False for goal in state['early_goals'])


def test_daily_quest_pool_eases_new_players_and_gates_duel_quests():
    import onboarding_service

    facts = {'completed_steps': {'finish_first_conquer_battle'}}
    new_pool = onboarding_service._eligible_daily_quests(
        facts, {'daily_quests_claimed_count': 0})
    assert new_pool
    assert {quest['tier'] for quest in new_pool} == {'easy'}
    assert all('duel' not in quest['id'] for quest in new_pool)

    facts['completed_steps'].add('finish_first_duel')
    middle_pool = onboarding_service._eligible_daily_quests(
        facts, {'daily_quests_claimed_count': 3})
    assert {quest['tier'] for quest in middle_pool} <= {'easy', 'medium'}
    assert any('duel' in quest['id'] for quest in middle_pool)

    mature_pool = onboarding_service._eligible_daily_quests(
        facts, {'daily_quests_claimed_count': 6})
    assert {quest['tier'] for quest in mature_pool} == {'easy', 'medium', 'hard'}


def test_daily_quest_is_deterministic_after_unlock(client, db, two_users, auth_headers_user1, monkeypatch):
    import onboarding_service

    u1, _ = two_users
    onboarding_service.mark_step(u1, 'finish_first_conquer_battle')
    db.session.commit()
    monkeypatch.setattr(onboarding_service, '_daily_quest_day_key',
                        lambda now=None: '2026-07-08')
    monkeypatch.setattr(onboarding_service, '_daily_quest_resets_at',
                        lambda now=None: datetime(2026, 7, 9))

    first = client.get('/onboarding/state', headers=auth_headers_user1).get_json()['onboarding']
    second = client.get('/onboarding/state', headers=auth_headers_user1).get_json()['onboarding']
    state = onboarding_service._state(u1)
    facts = onboarding_service._facts(u1, state)
    eligible = onboarding_service._eligible_daily_quests(facts, state)
    expected = onboarding_service._select_daily_quest(
        u1.id, '2026-07-08', eligible)['id']

    assert first['daily_quest'].get('locked') is not True
    assert first['daily_quest']['quest_id'] == expected
    assert second['daily_quest']['quest_id'] == expected
    db.session.refresh(u1)
    assert u1.onboarding_state['daily_quest']['day_key'] == '2026-07-08'
    assert u1.onboarding_state['daily_quest']['baseline']['duel_finishes'] == 0


def test_daily_quest_progress_claim_and_idempotency(client, db, two_users, auth_headers_user1, monkeypatch):
    import onboarding_service

    u1, u2 = two_users
    u1.gold = 100
    onboarding_service.mark_step(u1, 'finish_first_conquer_battle')
    onboarding_service.mark_step(u1, 'finish_first_duel')
    db.session.commit()
    monkeypatch.setattr(onboarding_service, '_daily_quest_day_key',
                        lambda now=None: '2026-07-08')
    monkeypatch.setattr(onboarding_service, '_daily_quest_resets_at',
                        lambda now=None: datetime(2026, 7, 9))
    monkeypatch.setattr(
        onboarding_service,
        '_select_daily_quest',
        lambda user_id, day_key, quests=None: onboarding_service.DAILY_QUEST_BY_ID['dq_finish_1_duel'],
    )

    initial = client.get('/onboarding/state', headers=auth_headers_user1).get_json()['onboarding']
    assert initial['daily_quest']['progress'] == 0
    assert initial['daily_quest']['claimable'] is False
    blocked = client.post('/onboarding/claim_reward', headers=auth_headers_user1,
                          json={'reward_id': 'daily_quest'})
    assert blocked.status_code == 400

    _add_game_result(db, u1, u2)
    db.session.commit()

    ready = client.get('/onboarding/state', headers=auth_headers_user1).get_json()['onboarding']
    assert ready['daily_quest']['progress'] == 1
    assert ready['daily_quest']['completed'] is True
    assert ready['daily_quest']['claimable'] is True
    assert ready['pending_reward_count'] >= 1

    claimed = client.post('/onboarding/claim_reward', headers=auth_headers_user1,
                          json={'reward_id': 'daily_quest'})
    data = claimed.get_json()
    assert claimed.status_code == 200
    assert data['reward_id'] == 'daily_quest'
    assert data['reward'] == {'gold': 60}
    assert data['balances']['gold'] == 160
    assert data['onboarding']['daily_quest']['claimed'] is True
    assert data['onboarding']['daily_quests_claimed_count'] == 1

    again = client.post('/onboarding/claim_reward', headers=auth_headers_user1,
                        json={'reward_id': 'daily_quest'})
    again_data = again.get_json()
    assert again.status_code == 200
    assert again_data['already_claimed'] is True
    assert again_data['balances']['gold'] == 160


def test_daily_quest_rollover_starts_fresh(client, db, two_users, auth_headers_user1, monkeypatch):
    import onboarding_service

    u1, u2 = two_users
    day = {'value': '2026-07-08'}
    onboarding_service.mark_step(u1, 'finish_first_conquer_battle')
    onboarding_service.mark_step(u1, 'finish_first_duel')
    db.session.commit()
    monkeypatch.setattr(onboarding_service, '_daily_quest_day_key',
                        lambda now=None: day['value'])
    monkeypatch.setattr(onboarding_service, '_daily_quest_resets_at',
                        lambda now=None: datetime(2026, 7, 9))
    monkeypatch.setattr(
        onboarding_service,
        '_select_daily_quest',
        lambda user_id, day_key, quests=None: onboarding_service.DAILY_QUEST_BY_ID['dq_finish_1_duel'],
    )

    client.get('/onboarding/state', headers=auth_headers_user1)
    _add_game_result(db, u1, u2)
    db.session.commit()
    claimed = client.post('/onboarding/claim_reward', headers=auth_headers_user1,
                          json={'reward_id': 'daily_quest'})
    assert claimed.status_code == 200

    day['value'] = '2026-07-09'
    next_day = client.get('/onboarding/state', headers=auth_headers_user1).get_json()['onboarding']
    quest = next_day['daily_quest']
    assert quest['day_key'] == '2026-07-09'
    assert quest['progress'] == 0
    assert quest['claimed'] is False
    assert quest['claimable'] is False


def test_daily_quest_action_after_rollover_before_guide_is_counted(db, two_users, monkeypatch):
    import onboarding_service

    u1, _ = two_users
    day = {'value': '2026-07-08'}
    onboarding_service.mark_step(u1, 'finish_first_conquer_battle')
    db.session.commit()
    monkeypatch.setattr(onboarding_service, '_daily_quest_day_key',
                        lambda now=None: day['value'])
    monkeypatch.setattr(onboarding_service, '_daily_quest_resets_at',
                        lambda now=None: datetime(2026, 7, 9))
    monkeypatch.setattr(
        onboarding_service,
        '_select_daily_quest',
        lambda user_id, day_key, quests=None: onboarding_service.DAILY_QUEST_BY_ID['dq_earn_100_gold'],
    )

    onboarding_service.serialize_onboarding_state(u1)
    db.session.commit()
    day['value'] = '2026-07-09'

    onboarding_service.record_gold_earned(u1, 100)
    db.session.commit()

    state = onboarding_service.serialize_onboarding_state(u1)
    quest = state['daily_quest']
    assert quest['day_key'] == '2026-07-09'
    assert quest['progress'] == 100
    assert quest['claimable'] is True


def test_v1_state_only_preserves_tutorial_finish_after_final_card(db, two_users):
    import onboarding_service

    user, _ = two_users
    user.onboarding_state = {
        'completed_steps': ['finish_first_conquer_battle'],
        'menu_hints_seen': [],
    }
    state = onboarding_service._state(user)
    assert 'finish_tutorial' not in state['completed_steps']

    user.onboarding_state = {
        'completed_steps': ['finish_first_conquer_battle'],
        'menu_hints_seen': ['kingdom_after_conquer_map'],
    }
    state = onboarding_service._state(user)
    assert 'finish_tutorial' in state['completed_steps']
    assert state['schema_version'] == 2
