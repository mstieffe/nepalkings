# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for the first-conquest pre-assembled starter attack.

A brand-new player's first conquer config is filled server-side with a
complete, battle-ready attack (King + Rice Farm + Gorkha Warriors + three
Daggers) from the curated starter deck, so they never face the figure
builder cold. See _preassemble_tutorial_conquer_attack in routes/kingdom.py.
"""

from models import CollectionCard, LandAttackLog


def _register(client, username='preasm'):
    resp = client.post('/auth/register', data={
        'username': username, 'password': 'pass1234',
        'age_confirmed': 'true', 'terms_accepted': 'true',
        'privacy_accepted': 'true',
    })
    assert resp.status_code == 200
    return resp.get_json()['token']


def _headers(token):
    return {'Authorization': f'Bearer {token}'}


_next_land_cell = [100]


def _tier1_unowned_land(db):
    """Return an existing seeded tier-1 unowned land, or create one."""
    from models import Land
    land = (Land.query
            .filter(Land.owner_user_id.is_(None))
            .filter(Land.tier == 1)
            .first())
    if land is not None:
        return land
    _next_land_cell[0] += 1
    cell = _next_land_cell[0]
    land = Land(col=cell, row=cell, tier=1, gold_rate=1.0,
                suit_bonus_suit='Clubs', suit_bonus_value=1)
    db.session.add(land)
    db.session.commit()
    return land


def _open_config(client, token, land_id):
    return client.get(f'/kingdom/conquer/config?land_id={land_id}',
                      headers=_headers(token))


def test_first_conquer_config_is_preassembled_and_battle_ready(client, app, db):
    token = _register(client, 'preasm_ready')
    from models import User
    user = User.query.filter_by(username='preasm_ready').first()
    land = _tier1_unowned_land(db)
    assert land is not None, 'expected a seeded tier-1 unowned land'

    cfg = _open_config(client, token, land.id).get_json()['config']

    figures = cfg.get('figures', [])
    names = sorted(f['family_name'] for f in figures)
    assert names == ['Djungle King', 'Gorkha Warriors', 'Small Rice Farm']

    # Battle figure is the Warriors (the offensive attacker).
    warriors = next(f for f in figures if f['family_name'] == 'Gorkha Warriors')
    assert cfg.get('battle_figure_id') == warriors['id']
    assert cfg.get('counter_spell_name') in (None, '')

    moves = cfg.get('battle_moves', cfg.get('moves', []))
    assert len(moves) == 3
    assert all(m['family_name'] == 'Dagger' for m in moves)
    assert sorted(str(m['rank']) for m in moves) == ['10', '8', '9']

    # Battle-ready: every figure resolves its resource requirements (no
    # deficit), so with a battle figure + 3 moves the config can start.
    assert all(not f.get('has_deficit') for f in figures)

    # All starter cards are now reserved (locked) to this config.
    free_hearts = CollectionCard.query.filter_by(
        user_id=user.id, suit='Hearts', locked=False).count()
    assert free_hearts == 0


def test_preassembly_is_idempotent(client, app, db):
    token = _register(client, 'preasm_idem')
    from models import User
    user = User.query.filter_by(username='preasm_idem').first()
    land = _tier1_unowned_land(db)

    first = _open_config(client, token, land.id).get_json()['config']
    second = _open_config(client, token, land.id).get_json()['config']
    assert len(first['figures']) == 3
    assert len(second['figures']) == 3  # not doubled


def test_preassembly_skipped_after_first_conquer(client, app, db):
    token = _register(client, 'preasm_done')
    from models import User
    user = User.query.filter_by(username='preasm_done').first()
    land = _tier1_unowned_land(db)
    db.session.add(LandAttackLog(
        land_id=land.id, attacker_user_id=user.id, result='attacker_won'))
    db.session.commit()

    cfg = _open_config(client, token, land.id).get_json()['config']
    assert cfg.get('figures', []) == []


def test_preassembly_skipped_when_starter_cards_missing(client, app, db):
    token = _register(client, 'preasm_nocards')
    from models import User
    user = User.query.filter_by(username='preasm_nocards').first()
    # Remove the King — the deterministic plan can no longer be satisfied.
    king = CollectionCard.query.filter_by(
        user_id=user.id, suit='Hearts', rank='K').first()
    db.session.delete(king)
    db.session.commit()
    land = _tier1_unowned_land(db)

    cfg = _open_config(client, token, land.id).get_json()['config']
    assert cfg.get('figures', []) == []  # no partial build
