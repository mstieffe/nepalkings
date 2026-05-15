# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""End-to-end test for the conquer AI defender response loop.

Exercises ``_conquer_ai_loop`` against a player-owned land that has BOTH a
counter spell and a configured battle figure (the previously-broken case).
The AI loop must either cast the counter spell or counter-advance with the
configured battle figure — never silently skip the response window.
"""
from types import SimpleNamespace

from models import (
    db, ActiveSpell, Figure, Game, Player,
)

import ai.ai_worker as ai_worker

from tests.server.test_land_battle import (
    _auth_headers, _make_conquer_config, _make_defence_config,
    _make_land, _make_user,
)


class _TestClientResponse:
    """Adapter so AI worker code (which expects requests.Response-like) can
    consume Flask test_client responses."""

    def __init__(self, flask_resp):
        self._resp = flask_resp
        self.status_code = flask_resp.status_code
        self.ok = 200 <= flask_resp.status_code < 300

    def json(self):
        return self._resp.get_json() or {}


def _install_ai_post_via_test_client(app, monkeypatch):
    client = app.test_client()

    def _fake_ai_post(url, ai_player_id, **kwargs):
        # Strip the SERVER_URL prefix so the test_client gets the route path.
        path = url
        for prefix in ('http://localhost:5000', 'http://localhost', 'http://127.0.0.1:5000'):
            if path.startswith(prefix):
                path = path[len(prefix):]
                break
        if not path.startswith('/'):
            # Fall back: take everything after the third '/' to find the path.
            try:
                path = '/' + url.split('/', 3)[3]
            except IndexError:
                path = '/'
        # Mint an internal token like the AI worker would, but call via test client.
        with ai_worker._ai_player_user_ids_lock:
            ai_user_id = ai_worker._ai_player_user_ids.get(ai_player_id)
        from routes.auth import generate_token
        headers = {'Authorization': f'Bearer {generate_token(ai_user_id)}',
                   'Content-Type': 'application/json'}
        json_body = kwargs.get('json') or {}
        flask_resp = client.post(path, json=json_body, headers=headers)
        return _TestClientResponse(flask_resp)

    monkeypatch.setattr(ai_worker, '_ai_post', _fake_ai_post)
    monkeypatch.setattr(ai_worker.time, 'sleep', lambda *_a, **_kw: None)


def test_ai_defender_casts_counter_spell_when_both_selected(app, db, monkeypatch):
    """Defender with both counter spell + battle figure casts the spell.

    Reproduces the user-reported bug: after the human invader advances, the
    automated defender (a player-owned land config with both a counter spell
    AND a battle figure preselected) must respond — either by casting the
    counter spell or by counter-advancing with the configured battle figure.
    """
    with app.app_context():
        attacker = _make_user(db, username='atk_ai_def')
        defender = _make_user(db, username='def_ai_def')

        land = _make_land(db, tier=1, owner_user_id=defender.id)
        _make_conquer_config(db, attacker, land)
        def_cfg = _make_defence_config(db, defender, land)
        # Both selected: keep battle_figure_id, add a counter spell.
        def_cfg.counter_spell_name = 'Poison'
        def_cfg.counter_spell_data = {}
        db.session.commit()

        client = app.test_client()
        atk_headers = _auth_headers(app, attacker)

        resp = client.post('/kingdom/conquer/start_battle',
                           json={'land_id': land.id}, headers=atk_headers)
        assert resp.status_code == 200
        game_id = resp.get_json()['game_id']

        game = db.session.get(Game, game_id)
        atk_player = db.session.get(Player, game.invader_player_id)
        def_player = [p for p in game.players if p.user_id == defender.id][0]

        # With both selected the start route now sets counter_spell mode and
        # leaves defending_figure_id unset so the response window opens.
        assert game.defending_figure_id is None

        atk_fig = Figure.query.filter_by(
            game_id=game.id, player_id=atk_player.id).first()
        adv = client.post('/games/advance_figure', json={
            'game_id': game.id,
            'player_id': atk_player.id,
            'figure_id': atk_fig.id,
        }, headers=atk_headers)
        assert adv.status_code == 200, adv.get_json()
        db.session.refresh(game)
        # Turn must flip to the AI defender so the AI loop has a phase.
        assert game.turn_player_id == def_player.id

        # Register the AI player → user mapping so _ai_headers works,
        # and route AI POSTs through the test client.
        with ai_worker._ai_player_user_ids_lock:
            ai_worker._ai_player_user_ids[def_player.id] = def_player.user_id
        _install_ai_post_via_test_client(app, monkeypatch)

    # Run the AI loop synchronously.
    ai_worker._conquer_ai_loop(app, game_id, def_player.id)

    with app.app_context():
        casted = ActiveSpell.query.filter_by(
            game_id=game_id,
            player_id=def_player.id,
            spell_name='Poison',
        ).first()
        game_after = db.session.get(Game, game_id)
        # Either: counter spell cast (preferred), or counter-advance happened.
        assert casted is not None or game_after.defending_figure_id is not None, (
            "AI defender failed to respond: no counter spell, no counter-advance"
        )


def test_ai_defender_counter_advances_when_only_battle_figure(app, db, monkeypatch):
    """Defender with only a battle figure must counter-advance (no spell)."""
    with app.app_context():
        attacker = _make_user(db, username='atk_only_bf')
        defender = _make_user(db, username='def_only_bf')

        land = _make_land(db, tier=1, owner_user_id=defender.id)
        _make_conquer_config(db, attacker, land)
        def_cfg = _make_defence_config(db, defender, land)
        # Only battle figure selected; no counter spell.
        def_cfg.counter_spell_name = None
        def_cfg.counter_spell_data = None
        db.session.commit()

        client = app.test_client()
        atk_headers = _auth_headers(app, attacker)

        resp = client.post('/kingdom/conquer/start_battle',
                           json={'land_id': land.id}, headers=atk_headers)
        assert resp.status_code == 200
        game_id = resp.get_json()['game_id']

        game = db.session.get(Game, game_id)
        atk_player = db.session.get(Player, game.invader_player_id)
        def_player = [p for p in game.players if p.user_id == defender.id][0]
        atk_fig = Figure.query.filter_by(
            game_id=game.id, player_id=atk_player.id).first()
        adv = client.post('/games/advance_figure', json={
            'game_id': game.id,
            'player_id': atk_player.id,
            'figure_id': atk_fig.id,
        }, headers=atk_headers)
        assert adv.status_code == 200, adv.get_json()
        db.session.refresh(game)
        assert game.turn_player_id == def_player.id

        with ai_worker._ai_player_user_ids_lock:
            ai_worker._ai_player_user_ids[def_player.id] = def_player.user_id
        _install_ai_post_via_test_client(app, monkeypatch)

    ai_worker._conquer_ai_loop(app, game_id, def_player.id)

    with app.app_context():
        game_after = db.session.get(Game, game_id)
        assert game_after.defending_figure_id is not None, (
            "AI defender failed to counter-advance with battle figure"
        )


def test_ai_defender_casts_counter_spell_when_only_spell(app, db, monkeypatch):
    """Defender with only a counter spell must cast it (no battle figure)."""
    with app.app_context():
        attacker = _make_user(db, username='atk_only_sp')
        defender = _make_user(db, username='def_only_sp')

        land = _make_land(db, tier=1, owner_user_id=defender.id)
        _make_conquer_config(db, attacker, land)
        def_cfg = _make_defence_config(db, defender, land)
        def_cfg.battle_figure_id = None
        def_cfg.counter_spell_name = 'Poison'
        def_cfg.counter_spell_data = {}
        db.session.commit()

        client = app.test_client()
        atk_headers = _auth_headers(app, attacker)

        resp = client.post('/kingdom/conquer/start_battle',
                           json={'land_id': land.id}, headers=atk_headers)
        assert resp.status_code == 200
        game_id = resp.get_json()['game_id']

        game = db.session.get(Game, game_id)
        atk_player = db.session.get(Player, game.invader_player_id)
        def_player = [p for p in game.players if p.user_id == defender.id][0]
        atk_fig = Figure.query.filter_by(
            game_id=game.id, player_id=atk_player.id).first()
        adv = client.post('/games/advance_figure', json={
            'game_id': game.id,
            'player_id': atk_player.id,
            'figure_id': atk_fig.id,
        }, headers=atk_headers)
        assert adv.status_code == 200, adv.get_json()
        db.session.refresh(game)
        assert game.turn_player_id == def_player.id

        with ai_worker._ai_player_user_ids_lock:
            ai_worker._ai_player_user_ids[def_player.id] = def_player.user_id
        _install_ai_post_via_test_client(app, monkeypatch)

    ai_worker._conquer_ai_loop(app, game_id, def_player.id)

    with app.app_context():
        casted = ActiveSpell.query.filter_by(
            game_id=game_id,
            player_id=def_player.id,
            spell_name='Poison',
        ).first()
        assert casted is not None, "AI defender failed to cast counter spell"
