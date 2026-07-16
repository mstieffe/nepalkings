# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for the first-conquest pre-assembled starter attack.

A brand-new player's first conquer config is filled server-side with a
complete, battle-ready attack (King + Rice Farm + Gorkha Warriors + three
Daggers + Draw 2 MainCards prelude) from the curated starter deck, so they
never face the figure builder cold. See _preassemble_tutorial_conquer_attack
in routes/kingdom.py.
"""

from models import CollectionCard, LandAttackLog


def _register(client, username='preasm'):
    resp = client.post('/auth/register', data={
        'username': username, 'password': 'pass1234',
        'age_confirmed': 'true', 'terms_accepted': 'true',
        'privacy_accepted': 'true',
    })
    assert resp.status_code == 200
    # The starter set is granted when the Collection roulette settles, before
    # the player reaches a conquer config. Simulate that here so the pre-assembler
    # has the curated starter cards to work with.
    from models import User
    from onboarding_service import grant_starter_set
    grant_starter_set(User.query.filter_by(username=username).first(), commit=True)
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
    from onboarding_service import get_starter_suits
    user = User.query.filter_by(username='preasm_ready').first()
    suit = get_starter_suits(user)['offensive']
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

    # Health Boost prelude on two 3s, targeting the Warriors.
    assert cfg.get('prelude_spell_name') == 'Health Boost'
    details = cfg.get('prelude_spell_card_details')
    assert len(details) == 2 and all(
        d['rank'] == '3' and d['suit'] == suit for d in details)

    # Tactics teach the non-Dagger moves: Call King, Call Villager, Block.
    moves = cfg.get('battle_moves', cfg.get('moves', []))
    assert len(moves) == 3
    by_round = {m['round_index']: m for m in moves}
    assert by_round[0]['family_name'] == 'Call King'
    assert by_round[1]['family_name'] == 'Call Villager'
    assert by_round[2]['family_name'] == 'Block'
    # Call moves reference a field figure; Block does not.
    assert by_round[0]['call_figure_id'] is not None
    assert by_round[1]['call_figure_id'] is not None
    assert by_round[2]['call_figure_id'] is None
    assert sorted(str(m['rank']) for m in moves) == ['J', 'K', 'Q']

    # Battle-ready: every figure resolves its resource requirements (no
    # deficit), so with a battle figure + 3 moves the config can start.
    assert all(not f.get('has_deficit') for f in figures)

    # The whole offensive starter set is reserved (locked) by the attack;
    # no spare cards remain free in the offensive suit.
    free_off = CollectionCard.query.filter_by(
        user_id=user.id, suit=suit, locked=False).all()
    assert free_off == []


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


def test_preassembly_skipped_after_prior_conquest_win(client, app, db):
    # Pre-assembly opts out only once the player has actually WON a conquest.
    token = _register(client, 'preasm_winner')
    from models import User
    user = User.query.filter_by(username='preasm_winner').first()
    land = _tier1_unowned_land(db)
    db.session.add(LandAttackLog(
        land_id=land.id,
        attacker_user_id=user.id,
        result='attacker_won',
    ))
    db.session.commit()

    cfg = _open_config(client, token, land.id).get_json()['config']
    assert cfg.get('figures', []) == []


def test_preassembly_still_runs_after_only_defending(client, app, db):
    # A successful defence (or a lost first attack) does NOT opt out: the player
    # has not conquered a land yet, so the tutorial attack is still
    # pre-assembled and they can retry with no penalty.
    token = _register(client, 'preasm_defender')
    _register(client, 'preasm_attacker')
    from models import User
    user = User.query.filter_by(username='preasm_defender').first()
    other = User.query.filter_by(username='preasm_attacker').first()
    land = _tier1_unowned_land(db)
    db.session.add(LandAttackLog(
        land_id=land.id,
        attacker_user_id=other.id,
        defender_user_id=user.id,
        result='defender_won',
    ))
    db.session.commit()

    cfg = _open_config(client, token, land.id).get_json()['config']
    assert cfg.get('figures', []) != []


def test_preassembly_skipped_when_starter_cards_missing(client, app, db):
    token = _register(client, 'preasm_nocards')
    from models import User
    from onboarding_service import get_starter_suits
    user = User.query.filter_by(username='preasm_nocards').first()
    suit = get_starter_suits(user)['offensive']
    # Remove the offensive King — the deterministic plan can no longer be met.
    king = CollectionCard.query.filter_by(
        user_id=user.id, suit=suit, rank='K').first()
    db.session.delete(king)
    db.session.commit()
    land = _tier1_unowned_land(db)

    cfg = _open_config(client, token, land.id).get_json()['config']
    assert cfg.get('figures', []) == []  # no partial build


def test_kingdom_map_marks_recommended_first_conquest_land(client, app, db, monkeypatch):
    import importlib

    token = _register(client, 'preasm_map')
    land = _tier1_unowned_land(db)
    land.owner_user_id = None
    land.tier = 1
    land.conquer_cooldown_until = None
    land.suit_bonus_suit = 'Clubs'
    db.session.commit()

    def _fail_template_lookup(_land):
        raise AssertionError('first-conquest map recommendation should not generate AI templates')

    kingdom_routes = importlib.import_module('routes.kingdom')
    monkeypatch.setattr(kingdom_routes, 'get_ai_defence_template_for_land',
                        _fail_template_lookup)

    resp = client.get('/kingdom/map', headers=_headers(token))
    assert resp.status_code == 200
    data = resp.get_json()
    recommended_id = data.get('recommended_tutorial_land_id')
    assert recommended_id is not None

    lands = data.get('lands') or []
    marked = [land for land in lands if land.get('is_recommended_tutorial_land')]
    assert len(marked) == 1
    assert marked[0]['id'] == recommended_id
    assert marked[0]['tier'] == 1
    assert marked[0].get('owner') is None


def test_tutorial_land_recommendation_prefers_central_phone_safe_target(monkeypatch):
    import importlib
    from types import SimpleNamespace

    kingdom_routes = importlib.import_module('routes.kingdom')
    monkeypatch.setattr(
        kingdom_routes, '_first_conquer_complete_for_user', lambda user: False)
    monkeypatch.setattr(
        kingdom_routes, '_user_offensive_suit', lambda user: 'Hearts')

    def land(land_id, col, row, gold):
        return SimpleNamespace(
            id=land_id,
            col=col,
            row=row,
            owner_user_id=None,
            tier=1,
            conquer_cooldown_until=None,
            suit_bonus_suit='Clubs',
            gold_rate=gold,
        )

    lands = [
        land(1, 0, 0, 99),
        land(2, 95, 49, 99),
        land(3, 48, 25, 1),
    ]
    assert kingdom_routes._recommended_tutorial_land_id(
        SimpleNamespace(), lands) == 3


def test_first_tier1_ai_conquest_uses_safe_defence_template(client, app, db):
    _register(client, 'preasm_safe_ai')
    from models import User
    from routes.kingdom import (
        _should_use_tutorial_safe_ai_defence,
        _tutorial_safe_ai_defence_template,
    )
    user = User.query.filter_by(username='preasm_safe_ai').first()
    land = _tier1_unowned_land(db)

    assert _should_use_tutorial_safe_ai_defence(user, land) is True
    # The scripted defender demonstrates a prelude + a counter-advancing figure,
    # in the BLACK suit the player's red attack beats, with weak 7-Daggers.
    from onboarding_service import get_starter_suits
    from routes.kingdom import _SUIT_ADVANTAGE
    attack_suit = get_starter_suits(user)['offensive']
    template = _tutorial_safe_ai_defence_template(attack_suit)
    assert template['ai_name'] == 'Tutorial Border Watch'
    assert template['prelude_spell_name'] == 'Draw 2 MainCards'
    assert template['counter_spell_name'] is None
    assert len(template['battle_moves']) == 3
    beaten = _SUIT_ADVANTAGE[attack_suit]
    assert all(m['suit'] == beaten and int(m['value']) == 7
               for m in template['battle_moves'])
    assert all(f['suit'] == beaten and f['color'] == 'defensive'
               for f in template['figures'])
    # Counter-advancing defending figure (no counter spell / must_be_attacked).
    assert template['battle_figure_index'] == 1


# Note: new players are granted only an offensive starter set. There is no
# pre-assembled defence draft — after a won conquest the conquer config is
# converted into the land's defence config (see routes/games.py), so the first
# defence is "just the conquer config".
