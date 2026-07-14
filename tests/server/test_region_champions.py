# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Historic-region standings, Champion accrual, and API snapshots."""

from datetime import datetime, timedelta

import pytest

from models import Land, RegionChampion, User
from region_service import (
    collect_region_tributes,
    reconcile_region_champion,
)


def _lands(db, user, *, region='karnali', count=8, rate=10.0,
           col_start=0):
    rows = []
    for index in range(count):
        land = Land(
            col=col_start + index,
            row=0,
            region=region,
            tier=1,
            gold_rate=rate,
            suit_bonus_suit='Spades',
            suit_bonus_value=1,
            owner_user_id=user.id,
        )
        db.session.add(land)
        rows.append(land)
    db.session.flush()
    return rows


def test_largest_owner_is_champion_and_ties_create_co_champions(
        app, db, two_users):
    first, second = two_users
    now = datetime(2026, 7, 14, 8, 0, 0)
    _lands(db, first, count=1, col_start=0)
    _lands(db, second, count=1, col_start=20)
    db.session.commit()

    tied = reconcile_region_champion('karnali', now=now, commit=True)
    assert tied['champion_user_id'] is None
    assert tied['champion_user_ids'] == [first.id, second.id]

    _lands(db, first, count=1, col_start=40)
    db.session.commit()
    led = reconcile_region_champion(
        'karnali', now=now + timedelta(minutes=1), commit=True)
    assert led['champion_user_id'] == first.id
    assert led['champion_user_ids'] == [first.id]
    assert led['leader_count'] == 2
    assert led['runner_up_count'] == 1


def test_rate_uses_all_human_owned_region_land_and_accrues_old_rate_first(
        app, db, two_users):
    first, second = two_users
    now = datetime(2026, 7, 14, 8, 0, 0)
    _lands(db, first, count=9, rate=10.0, col_start=0)
    _lands(db, second, count=8, rate=10.0, col_start=20)
    db.session.commit()

    result = reconcile_region_champion('karnali', now=now, commit=True)
    # 17 player-owned lands * 10 raw gold/hr * 5%.
    assert result['rate_per_hour'] == pytest.approx(8.5)

    row = db.session.get(RegionChampion, 'karnali')
    row.rate_per_hour = 4.0
    row.pending_gold_by_user = {str(first.id): 0.0}
    row.last_accrued_at = now
    db.session.commit()

    # Production changes before the next reconcile.  The elapsed two hours
    # are still priced at the stored historic rate (4/hr), then rate updates.
    extra = _lands(db, first, count=1, rate=30.0, col_start=50)[0]
    db.session.commit()
    result = reconcile_region_champion(
        'karnali', now=now + timedelta(hours=2), commit=True)
    row = db.session.get(RegionChampion, 'karnali')
    assert row.pending_gold_by_user[str(first.id)] == pytest.approx(8.0)
    assert result['rate_per_hour'] == pytest.approx(10.0)
    assert extra.owner_user_id == first.id


def test_tribute_caps_at_24_hours_and_collect_drains_only_whole_gold(
        app, db, two_users):
    first, _second = two_users
    now = datetime(2026, 7, 14, 8, 0, 0)
    _lands(db, first, count=8, rate=10.0)
    db.session.commit()
    reconcile_region_champion('karnali', now=now, commit=True)

    row = db.session.get(RegionChampion, 'karnali')
    row.rate_per_hour = 2.0
    row.pending_gold = 0.0
    row.pending_gold_by_user = {str(first.id): 0.0}
    row.last_accrued_at = now - timedelta(hours=30)
    starting_gold = first.gold
    db.session.commit()

    total, breakdown = collect_region_tributes(first, now=now)
    db.session.commit()
    assert total == 48
    assert breakdown == [
        {'region': 'karnali', 'name': 'Karnali', 'collected': 48}]
    assert first.gold == starting_gold + 48
    assert row.pending_gold == pytest.approx(0.0)


def test_co_champions_split_tribute_and_collect_independently(
        app, db, two_users):
    first, second = two_users
    now = datetime(2026, 7, 14, 8, 0, 0)
    _lands(db, first, count=1, rate=10.0, col_start=0)
    _lands(db, second, count=1, rate=10.0, col_start=20)
    db.session.commit()
    result = reconcile_region_champion('karnali', now=now, commit=True)
    assert result['champion_user_ids'] == [first.id, second.id]
    assert result['rate_per_hour'] == pytest.approx(1.0)

    total, _breakdown = collect_region_tributes(
        first, now=now + timedelta(hours=2))
    db.session.commit()
    assert total == 1
    row = db.session.get(RegionChampion, 'karnali')
    # The second co-Champion's independently accrued share remains available.
    assert row.pending_gold_by_user[str(second.id)] == pytest.approx(1.0)


def test_dethroning_pays_old_champion_and_emits_activity(app, db, two_users):
    from models import KingdomNotification

    first, second = two_users
    now = datetime(2026, 7, 14, 8, 0, 0)
    first_lands = _lands(db, first, count=9, col_start=0)
    _lands(db, second, count=8, col_start=20)
    db.session.commit()
    reconcile_region_champion('karnali', now=now, commit=True)

    row = db.session.get(RegionChampion, 'karnali')
    row.pending_gold = 7.8
    row.pending_gold_by_user = {str(first.id): 7.8}
    starting_gold = first.gold
    first_lands[0].owner_user_id = second.id
    first_lands[1].owner_user_id = second.id
    db.session.commit()

    result = reconcile_region_champion(
        'karnali', now=now + timedelta(minutes=1), commit=True)
    assert result['champion_user_id'] == second.id
    assert first.gold == starting_gold + 7
    kinds = [row.kind for row in KingdomNotification.query.order_by(
        KingdomNotification.id).all()]
    assert 'region_champion_lost' in kinds
    assert kinds.count('region_champion_gained') == 2


def test_map_region_snapshot_is_read_only(client, db, two_users,
                                          auth_headers_user1, monkeypatch):
    import region_service

    first, _second = two_users
    _lands(db, first, region='kathmandu', count=3, rate=4.0)
    db.session.commit()

    def fail_reconcile(*_args, **_kwargs):
        raise AssertionError('GET /kingdom/map must not reconcile Champions')

    monkeypatch.setattr(
        region_service, 'reconcile_region_champions', fail_reconcile)
    rv = client.get('/kingdom/map', headers=auth_headers_user1)
    assert rv.status_code == 200
    data = rv.get_json()
    assert len(data['regions']) == 5
    kathmandu = next(
        region for region in data['regions']
        if region['key'] == 'kathmandu')
    assert kathmandu['name'] == 'Kathmandu Valley'
    assert kathmandu['my_land_count'] == 3
    assert kathmandu['min_lands'] == 1
    assert kathmandu['lands_to_champion'] == 0
    assert all(land['region'] == 'kathmandu' for land in data['lands'])
