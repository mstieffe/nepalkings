# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
#!/usr/bin/env python3
"""Print the new-player funnel from the first-party analytics event log.

Usage:
    python scripts/funnel_report.py                      # uses $DB_URL
    python scripts/funnel_report.py path/to/backup.db    # sqlite file
    DB_URL=sqlite:///server/instance/nepalkings.db python scripts/funnel_report.py

Reads only the `event` and `user` tables (see server/analytics.py).
All computation happens in Python so the report works against SQLite
and MySQL alike — event volume is expected to stay small.
"""

import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import create_engine, text


# Ordered first-session funnel: event name → label.
FUNNEL_STEPS = [
    ('signup', 'Signed up'),
    ('booster_opened', 'Opened a booster'),
    ('conquer_battle_started', 'Started a conquer battle'),
    ('game_finished:conquer', 'Finished a conquer battle'),
    ('challenge_created', 'Created a duel challenge'),
    ('game_finished:duel', 'Finished a duel'),
]

RETENTION_WINDOW_HOURS = (24, 72)  # "returned" = any event 24–72h after signup


def _resolve_db_url(argv):
    if len(argv) > 1:
        path = argv[1]
        if '://' in path:
            return path
        return f'sqlite:///{os.path.abspath(path)}'
    url = os.getenv('DB_URL')
    if url:
        return url
    default = os.path.join(os.path.dirname(__file__), '..', 'server',
                           'instance', 'nepalkings.db')
    default = os.path.abspath(default)
    if os.path.exists(default):
        return f'sqlite:///{default}'
    print('No DB_URL set and no default database found.', file=sys.stderr)
    sys.exit(1)


def _parse_dt(value):
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _load(engine):
    with engine.connect() as conn:
        human_ids = {row[0] for row in conn.execute(
            text('SELECT id FROM "user" WHERE is_ai = 0 OR is_ai IS NULL'))}
        rows = conn.execute(text(
            'SELECT user_id, name, props, created_at FROM event ORDER BY created_at'))
        events = []
        for user_id, name, props, created_at in rows:
            created = _parse_dt(created_at)
            if created is None:
                continue
            if isinstance(props, str):
                import json
                try:
                    props = json.loads(props)
                except ValueError:
                    props = {}
            events.append({'user_id': user_id, 'name': name,
                           'props': props or {}, 'created_at': created})
    return human_ids, events


def _step_key(event):
    """Map an event to its funnel key (game_finished splits by mode)."""
    if event['name'] == 'game_finished':
        return f"game_finished:{event['props'].get('mode', 'duel')}"
    return event['name']


def main(argv=None):
    argv = argv if argv is not None else sys.argv
    db_url = _resolve_db_url(argv)
    engine = create_engine(db_url)
    human_ids, events = _load(engine)

    human_events = [e for e in events if e['user_id'] in human_ids]
    users_by_step = defaultdict(set)
    signup_at = {}
    for e in human_events:
        users_by_step[_step_key(e)].add(e['user_id'])
        if e['name'] == 'signup' and e['user_id'] not in signup_at:
            signup_at[e['user_id']] = e['created_at']
    # game_finished events carry only the winner's user_id; credit the duel /
    # conquer finish to every human participant we can identify via props.
    # (Winner-only attribution is fine for a v1 funnel.)

    print(f'Funnel report — {db_url}')
    print(f'Events: {len(events)} total, {len(human_events)} from human accounts')
    print()

    # ── First-session funnel ──
    base = len(users_by_step.get('signup', set())) or None
    print('First-session funnel (distinct human users):')
    for key, label in FUNNEL_STEPS:
        n = len(users_by_step.get(key, set()))
        pct = f'  ({100 * n / base:.0f}%)' if base else ''
        print(f'  {label:<28} {n:>5}{pct}')
    print()

    # ── Early retention ──
    lo, hi = RETENTION_WINDOW_HOURS
    returned = 0
    eligible = 0
    now = datetime.utcnow()
    last_event_at = defaultdict(lambda: None)
    events_by_user = defaultdict(list)
    for e in human_events:
        events_by_user[e['user_id']].append(e['created_at'])
    for uid, t0 in signup_at.items():
        if now - t0 < timedelta(hours=hi):
            continue  # too recent to judge
        eligible += 1
        if any(timedelta(hours=lo) <= t - t0 <= timedelta(hours=hi)
               for t in events_by_user.get(uid, [])):
            returned += 1
    if eligible:
        print(f'Early retention: {returned}/{eligible} '
              f'({100 * returned / eligible:.0f}%) of signups older than {hi}h '
              f'came back {lo}–{hi}h after signing up.')
    else:
        print(f'Early retention: no signups older than {hi}h yet.')
    print()

    # ── Activity, last 14 days ──
    cutoff = now - timedelta(days=14)
    daily = defaultdict(lambda: defaultdict(int))
    for e in human_events:
        if e['created_at'] >= cutoff:
            daily[e['created_at'].date()][e['name']] += 1
    print('Last 14 days (events per day):')
    if not daily:
        print('  (no recent events)')
    for day in sorted(daily):
        counts = daily[day]
        top = ', '.join(f'{k}={v}' for k, v in sorted(counts.items()))
        print(f'  {day}  {top}')
    print()

    # ── Duel duration ──
    durations = sorted(
        e['props']['duration_s'] for e in human_events
        if e['name'] == 'game_finished' and e['props'].get('mode') == 'duel'
        and isinstance(e['props'].get('duration_s'), (int, float)))
    if durations:
        median = durations[len(durations) // 2]
        print(f'Median duel duration: {median / 60:.0f} min '
              f'({len(durations)} finished duels)')

    return 0


if __name__ == '__main__':
    sys.exit(main())
