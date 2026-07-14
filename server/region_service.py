# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Historic kingdom-map regions, standings, Champions, and tribute."""

from __future__ import annotations

import math
import random
from collections import defaultdict
from datetime import datetime, timezone
from functools import lru_cache

import server_settings as config
from models import db, KingdomNotification, Land, RegionChampion, User


SUITS = ('Hearts', 'Diamonds', 'Clubs', 'Spades')


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _odd_q_to_world(col, row):
    """Project coordinates exactly as the client renders its flat-top grid."""
    return (col * 1.5,
            row * math.sqrt(3.0) + (col & 1) * math.sqrt(3.0) / 2.0)


@lru_cache(maxsize=8)
def _world_extents(cols, rows):
    points = [_odd_q_to_world(col, row)
              for row in range(rows) for col in range(cols)]
    xs = [point[0] for point in points] or [0.0]
    ys = [point[1] for point in points] or [0.0]
    return min(xs), max(xs), min(ys), max(ys)


def _shape_noise(dx, dy, phase):
    first = math.sin(dx * 4.7 + dy * 3.1 + phase)
    second = math.sin(dx * 8.3 - dy * 5.9 - phase * 0.7)
    return (first + 0.45 * second) / 1.45


def region_for(col, row, cols=None, rows=None):
    """Return the stable historic-region key for one odd-q map coordinate."""
    cols = int(cols or config.KINGDOM_MAP_COLS)
    rows = int(rows or config.KINGDOM_MAP_ROWS)
    min_x, max_x, min_y, max_y = _world_extents(cols, rows)
    world_x, world_y = _odd_q_to_world(int(col), int(row))
    half_x = max(0.5, (max_x - min_x) / 2.0)
    half_y = max(0.5, (max_y - min_y) / 2.0)
    dx = (world_x - (min_x + max_x) / 2.0) / half_x
    dy = (world_y - (min_y + max_y) / 2.0) / half_y

    noise_strength = max(0.0, float(config.REGION_BORDER_NOISE))
    radius = max(0.1, float(config.REGION_CENTER_RADIUS))
    radius += noise_strength * _shape_noise(dx, dy, 0.73)
    if math.sqrt(dx * dx + dy * dy) <= radius:
        return 'kathmandu'

    axis_x = dx + noise_strength * 0.55 * _shape_noise(dx, dy, 2.31)
    axis_y = dy + noise_strength * 0.55 * _shape_noise(dx, dy, 4.17)
    if axis_y < 0:
        return 'karnali' if axis_x < 0 else 'kirat'
    return 'lumbini' if axis_x < 0 else 'mithila'


def region_coords(cols=None, rows=None):
    """Return every map coordinate bucketed in configured display order."""
    cols = int(cols or config.KINGDOM_MAP_COLS)
    rows = int(rows or config.KINGDOM_MAP_ROWS)
    buckets = {key: [] for key in config.MAP_REGIONS}
    for row in range(rows):
        for col in range(cols):
            buckets[region_for(col, row, cols, rows)].append((col, row))
    return buckets


def _quota_suits(count, weights, rng=None):
    """Allocate an exact suit count with largest remainders, then shuffle."""
    rng = rng or random
    count = max(0, int(count))
    raw = {suit: count * max(0.0, float(weights.get(suit, 0.0)))
           for suit in SUITS}
    allocated = {suit: int(math.floor(raw[suit])) for suit in SUITS}
    remaining = count - sum(allocated.values())
    order = sorted(SUITS, key=lambda suit: (-(raw[suit] - allocated[suit]),
                                            SUITS.index(suit)))
    for suit in order[:remaining]:
        allocated[suit] += 1
    result = []
    for suit in SUITS:
        result.extend([suit] * allocated[suit])
    rng.shuffle(result)
    return result


def region_suit_list(region_key, cluster_count, rng=None):
    """Return an exact shuffled cluster-suit list for one region."""
    region = config.MAP_REGIONS[region_key]
    dominant = region.get('dominant_suit')
    if not dominant:
        weights = {suit: 0.25 for suit in SUITS}
    else:
        dominant_weight = max(0.25, min(
            1.0, float(config.REGION_DOMINANT_SUIT_WEIGHT)))
        remainder = (1.0 - dominant_weight) / 3.0
        weights = {suit: (dominant_weight if suit == dominant else remainder)
                   for suit in SUITS}
    return _quota_suits(cluster_count, weights, rng=rng)


def _human_user_ids(owner_ids):
    owner_ids = {int(user_id) for user_id in owner_ids if user_id is not None}
    if not owner_ids:
        return set()
    return {
        user_id for (user_id,) in db.session.query(User.id).filter(
            User.id.in_(owner_ids), User.is_ai.is_(False)).all()
    }


def region_standings(lands=None, region_key=None):
    """Return land counts and raw production for human owners by region."""
    if lands is None:
        query = Land.query
        if region_key:
            query = query.filter_by(region=region_key)
        lands = query.all()

    human_ids = _human_user_ids(land.owner_user_id for land in lands)
    counts = defaultdict(lambda: defaultdict(int))
    rates = defaultdict(float)
    for land in lands:
        user_id = land.owner_user_id
        key = land.region or region_for(
            land.col, land.row,
            config.KINGDOM_MAP_COLS, config.KINGDOM_MAP_ROWS)
        if region_key and key != region_key:
            continue
        if not key or user_id not in human_ids:
            continue
        counts[key][user_id] += 1
        rates[key] += float(land.gold_rate or 0.0)
    return {
        key: {
            'counts_by_user': dict(counts.get(key, {})),
            'player_gold_rate': float(rates.get(key, 0.0)),
        }
        for key in config.MAP_REGIONS
        if region_key is None or key == region_key
    }


def _leaders_for_counts(counts):
    """Return every human tied for the largest positive land count."""
    ranked = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    if not ranked:
        return [], 0, 0
    leader_count = int(ranked[0][1])
    if leader_count <= 0:
        return [], 0, 0
    leader_ids = sorted(
        int(user_id) for user_id, count in ranked if count == leader_count)
    lower_counts = [int(count) for _user_id, count in ranked
                    if count < leader_count]
    runner_up_count = max(lower_counts) if lower_counts else 0
    return leader_ids, leader_count, runner_up_count


def _row_champion_ids(row):
    ids = getattr(row, 'champion_user_ids', None) or []
    normalized = sorted({int(user_id) for user_id in ids if user_id is not None})
    if not normalized and row.champion_user_id:
        normalized = [int(row.champion_user_id)]
    return normalized


def _row_pending_map(row):
    pending = {
        str(int(user_id)): max(0.0, float(value or 0.0))
        for user_id, value in (getattr(row, 'pending_gold_by_user', None) or {}).items()
    }
    ids = _row_champion_ids(row)
    if not pending and len(ids) == 1 and float(row.pending_gold or 0.0) > 0:
        pending[str(ids[0])] = float(row.pending_gold or 0.0)
    return pending


def _row_since_map(row):
    since = {
        str(int(user_id)): str(value)
        for user_id, value in (getattr(row, 'since_by_user', None) or {}).items()
        if value
    }
    ids = _row_champion_ids(row)
    if not since and len(ids) == 1 and row.since:
        since[str(ids[0])] = row.since.isoformat()
    return since


def _sync_legacy_champion_fields(row, champion_ids, pending, since):
    """Keep old singular columns usable without making them authoritative."""
    row.champion_user_ids = list(champion_ids)
    row.pending_gold_by_user = dict(pending)
    row.since_by_user = dict(since)
    row.champion_user_id = champion_ids[0] if len(champion_ids) == 1 else None
    row.pending_gold = sum(float(value or 0.0) for value in pending.values())
    since_values = []
    for value in since.values():
        try:
            since_values.append(datetime.fromisoformat(value))
        except (TypeError, ValueError):
            continue
    row.since = min(since_values) if since_values else None


def _locked_champion_row(region_key, now):
    row = (RegionChampion.query.filter_by(region=region_key)
           .with_for_update().first())
    if row is None:
        row = RegionChampion(
            region=region_key,
            champion_user_id=None,
            champion_user_ids=[],
            since=None,
            pending_gold=0.0,
            pending_gold_by_user={},
            since_by_user={},
            last_accrued_at=now,
            rate_per_hour=0.0,
        )
        db.session.add(row)
        db.session.flush()
    return row


def _accrue_region_row(row, now):
    """Advance every co-Champion pot using the stored historic total rate."""
    last = row.last_accrued_at or now
    elapsed_hours = max(0.0, (now - last).total_seconds() / 3600.0)
    total_rate = max(0.0, float(row.rate_per_hour or 0.0))
    champion_ids = _row_champion_ids(row)
    pending = _row_pending_map(row)
    if champion_ids:
        share_rate = total_rate / len(champion_ids)
        cap = share_rate * max(0, int(config.REGION_TRIBUTE_CAP_HOURS))
        for user_id in champion_ids:
            key = str(user_id)
            current = max(0.0, float(pending.get(key, 0.0) or 0.0))
            if share_rate > 0.0 and elapsed_hours > 0.0:
                current = min(cap, current + share_rate * elapsed_hours)
            pending[key] = current
    _sync_legacy_champion_fields(
        row, champion_ids, pending, _row_since_map(row))
    row.last_accrued_at = now
    return pending


def _region_pending_snapshots(row, now):
    if row is None:
        return {}
    champion_ids = _row_champion_ids(row)
    if not champion_ids:
        return {}
    last = row.last_accrued_at or now
    elapsed_hours = max(0.0, (now - last).total_seconds() / 3600.0)
    share_rate = max(0.0, float(row.rate_per_hour or 0.0)) / len(champion_ids)
    cap = share_rate * max(0, int(config.REGION_TRIBUTE_CAP_HOURS))
    pending = _row_pending_map(row)
    return {
        user_id: min(
            cap,
            max(0.0, float(pending.get(str(user_id), 0.0) or 0.0))
            + share_rate * elapsed_hours,
        )
        for user_id in champion_ids
    }


def reconcile_region_champion(region_key, now=None, commit=False, lands=None):
    """Reconcile every tied Champion after a regional ownership change."""
    if region_key not in config.MAP_REGIONS:
        return None
    now = now or _utcnow()
    row = _locked_champion_row(region_key, now)
    _accrue_region_row(row, now)
    data = region_standings(lands=lands, region_key=region_key)[region_key]
    new_user_ids, leader_count, runner_up_count = _leaders_for_counts(
        data['counts_by_user'])
    old_user_ids = _row_champion_ids(row)
    pending = _row_pending_map(row)
    since = _row_since_map(row)
    outgoing = sorted(set(old_user_ids) - set(new_user_ids))
    incoming = sorted(set(new_user_ids) - set(old_user_ids))

    for old_user_id in outgoing:
        payout = int(float(pending.pop(str(old_user_id), 0.0) or 0.0))
        since.pop(str(old_user_id), None)
        old_user = db.session.get(User, old_user_id)
        if old_user and payout > 0:
            old_user.gold = int(old_user.gold or 0) + payout
        db.session.add(KingdomNotification(
                user_id=old_user_id,
                kingdom_id=None,
                kind='region_champion_lost',
                payload={
                    'region': region_key,
                    'region_name': config.MAP_REGIONS[region_key]['name'],
                    'tribute_paid': payout,
                },
            ))
    for new_user_id in incoming:
        pending[str(new_user_id)] = 0.0
        since[str(new_user_id)] = now.isoformat()
        db.session.add(KingdomNotification(
                user_id=new_user_id,
                kingdom_id=None,
                kind='region_champion_gained',
                payload={
                    'region': region_key,
                    'region_name': config.MAP_REGIONS[region_key]['name'],
                    'land_count': leader_count,
                    'co_champion_count': len(new_user_ids),
                },
            ))

    # Continuing co-Champions retain their accrued pot and original since.
    pending = {str(user_id): float(pending.get(str(user_id), 0.0) or 0.0)
               for user_id in new_user_ids}
    since = {str(user_id): since.get(str(user_id), now.isoformat())
             for user_id in new_user_ids}

    tribute_fraction = max(0.0, float(config.REGION_TRIBUTE_RATE))
    row.rate_per_hour = (
        float(data['player_gold_rate']) * tribute_fraction
        if new_user_ids else 0.0
    )
    _sync_legacy_champion_fields(row, new_user_ids, pending, since)
    row.last_accrued_at = now
    if commit:
        db.session.commit()
    return {
        'region': region_key,
        'champion_user_id': (new_user_ids[0]
                             if len(new_user_ids) == 1 else None),
        'champion_user_ids': new_user_ids,
        'leader_count': leader_count,
        'runner_up_count': runner_up_count,
        'rate_per_hour': float(row.rate_per_hour or 0.0),
    }


def reconcile_region_champions(now=None, commit=False, lands=None):
    """Reconcile every configured region, normally at startup/sweeper time."""
    now = now or _utcnow()
    results = []
    if lands is None:
        lands = Land.query.all()
    for region_key in config.MAP_REGIONS:
        results.append(reconcile_region_champion(
            region_key, now=now, commit=False, lands=lands))
    if commit:
        db.session.commit()
    return results


def collect_region_tributes(user, now=None):
    """Accrue and drain every regional tribute pot held by ``user``."""
    now = now or _utcnow()
    rows = RegionChampion.query.with_for_update().all()
    total = 0
    breakdown = []
    for row in rows:
        if user.id not in _row_champion_ids(row):
            continue
        _accrue_region_row(row, now)
        pending = _row_pending_map(row)
        collected = int(float(pending.get(str(user.id), 0.0) or 0.0))
        if collected <= 0:
            continue
        pending[str(user.id)] = max(
            0.0, float(pending.get(str(user.id), 0.0) or 0.0) - collected)
        _sync_legacy_champion_fields(
            row, _row_champion_ids(row), pending, _row_since_map(row))
        total += collected
        breakdown.append({
            'region': row.region,
            'name': config.MAP_REGIONS[row.region]['name'],
            'collected': collected,
        })
    if total:
        user.gold = int(user.gold or 0) + total
        db.session.add(KingdomNotification(
            user_id=user.id,
            kingdom_id=None,
            kind='region_tribute_collected',
            payload={'amount': total, 'regions': breakdown},
        ))
    return total, breakdown


def serialize_regions(user_id, lands=None, now=None):
    """Build the ordered read-only region block for ``GET /kingdom/map``."""
    now = now or _utcnow()
    lands = list(lands) if lands is not None else Land.query.all()
    standings = region_standings(lands=lands)
    rows = {row.region: row for row in RegionChampion.query.all()}
    # Names follow the live read-only standings rather than the persisted row.
    # This keeps snapshots truthful if a prior mutation failed before its
    # Champion reconciliation could commit; startup remains the repair path.
    champion_ids = {
        leader_id
        for data in standings.values()
        for leader_id in _leaders_for_counts(data['counts_by_user'])[0]
    }
    usernames = {
        user.id: user.username for user in User.query.filter(
            User.id.in_(champion_ids)).all()
    } if champion_ids else {}
    cap_hours = max(0, int(config.REGION_TRIBUTE_CAP_HOURS))
    result = []

    for key, spec in config.MAP_REGIONS.items():
        data = standings[key]
        counts = data['counts_by_user']
        row = rows.get(key)
        leader_ids, champion_count, runner_up_count = _leaders_for_counts(counts)
        my_count = int(counts.get(user_id, 0))
        highest = max(counts.values()) if counts else 0
        lands_to_champion = (0 if user_id in leader_ids else
                             max(0, max(1, highest) - my_count))
        total_rate = float(row.rate_per_hour or 0.0) if row else 0.0
        share_rate = total_rate / len(leader_ids) if leader_ids else 0.0
        pending = _region_pending_snapshots(row, now)
        champions = [{
            'user_id': champion_id,
            'username': usernames.get(champion_id),
        } for champion_id in leader_ids]
        result.append({
            'key': key,
            'name': spec['name'],
            'dominant_suit': spec.get('dominant_suit'),
            # ``champion`` keeps older clients compatible; ``champions`` is
            # authoritative and contains every tied leader.
            'champion': champions[0] if champions else None,
            'champions': champions,
            'champion_land_count': champion_count,
            'runner_up_land_count': runner_up_count,
            'my_land_count': my_count,
            'lands_to_champion': lands_to_champion,
            'min_lands': 1,
            'is_champion': user_id in leader_ids,
            'tribute_rate_per_hour': round(share_rate, 3),
            'my_pending_tribute': round(
                pending.get(user_id, 0.0), 3),
            'tribute_cap': round(share_rate * cap_hours, 3),
        })
    return result
