# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""End-to-end test for the conquer AI defender response loop.

Exercises ``_conquer_ai_loop`` against a player-owned land that has BOTH a
counter spell and a configured battle figure (the previously-broken case).
The AI loop must either cast the counter spell or counter-advance with the
configured battle figure — never silently skip the response window.
"""
from types import SimpleNamespace

import pytest

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


@pytest.mark.parametrize('spell_name', [
    'Poison',
    'Draw 2 MainCards',
    'Draw 4 MainCards',
    'Copy Figure',
    'Landslide',
])
def test_ai_defender_casts_counter_spell_when_only_spell(
    app, db, monkeypatch, spell_name,
):
    """Defender with only a counter spell must cast it (no battle figure)."""
    with app.app_context():
        slug = spell_name.lower().replace(' ', '_')
        attacker = _make_user(db, username=f'atk_only_sp_{slug}')
        defender = _make_user(db, username=f'def_only_sp_{slug}')

        land = _make_land(db, tier=1, owner_user_id=defender.id)
        _make_conquer_config(db, attacker, land)
        def_cfg = _make_defence_config(db, defender, land)
        def_cfg.battle_figure_id = None
        def_cfg.counter_spell_name = spell_name
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
            spell_name=spell_name,
        ).first()
        assert casted is not None, "AI defender failed to cast counter spell"


def test_ai_defender_skips_civil_war_second_when_no_legal_figure(app, db, monkeypatch):
    """Regression: Civil War second pick with no legal second figure.

    The server keeps the turn on the automated defender for the optional
    second Civil War pick.  The AI worker previously bailed out with
    "no figure to advance", leaving the turn parked on the AI forever —
    the battle never started.  It must skip the second pick instead so the
    turn returns to the invader.
    """
    with app.app_context():
        attacker = _make_user(db, username='atk_cw_skip')
        defender = _make_user(db, username='def_cw_skip')

        land = _make_land(db, tier=1, owner_user_id=defender.id)
        _make_conquer_config(db, attacker, land)
        def_cfg = _make_defence_config(db, defender, land)
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
        def_fig = Figure.query.filter_by(
            game_id=game.id, player_id=def_player.id).first()

        # Freeze the game mid Civil War: the invader advanced, the automated
        # defender counter-advanced its first figure, and the server now
        # waits for the (optional) second same-color village pick.  The
        # defender has no other figure, so no legal second exists.
        game.battle_modifier = [{'type': 'Civil War'}]
        game.advancing_figure_id = atk_fig.id
        game.advancing_player_id = atk_player.id
        game.invader_player_id = atk_player.id
        game.defending_figure_id = def_fig.id
        game.turn_player_id = def_player.id
        atk_player.turns_left = 0
        def_player.turns_left = 0
        db.session.commit()

        with ai_worker._ai_player_user_ids_lock:
            ai_worker._ai_player_user_ids[def_player.id] = def_player.user_id
        _install_ai_post_via_test_client(app, monkeypatch)

        def_player_id = def_player.id
        atk_player_id = atk_player.id

    ai_worker._conquer_ai_loop(app, game_id, def_player_id)

    with app.app_context():
        from models import LogEntry
        game_after = db.session.get(Game, game_id)
        assert game_after.turn_player_id == atk_player_id, (
            "AI defender stalled on the Civil War second pick — turn never "
            "returned to the invader"
        )
        skip_log = LogEntry.query.filter_by(
            game_id=game_id, player_id=def_player_id, type='civil_war_skip',
        ).first()
        assert skip_log is not None, "skip_civil_war_second was never called"


def test_royal_decree_suppresses_ai_civil_war_second_pick_state():
    game = SimpleNamespace(
        mode='conquer',
        battle_modifier=[
            {'type': 'Civil War'},
            {'type': 'Royal Decree'},
        ],
        turn_player_id=2,
        advancing_figure_id=10,
        advancing_figure_id_2=None,
        advancing_player_id=1,
        defending_figure_id=20,
        defending_figure_id_2=None,
    )

    assert ai_worker._conquer_civil_war_second_pick_pending(game, 2) is False


def test_civil_war_counter_second_ignores_resting_figures(app, db):
    """A resting village figure must not count as an eligible Civil War second.

    The advance_figure endpoint rejects resting figures, so counting one as
    an eligible second parked the turn on the defender for a pick that could
    never be made.
    """
    with app.app_context():
        attacker = _make_user(db, username='atk_cw_rest')
        defender = _make_user(db, username='def_cw_rest')

        land = _make_land(db, tier=1, owner_user_id=defender.id)
        _make_conquer_config(db, attacker, land)
        def_cfg = _make_defence_config(db, defender, land)
        def_cfg.counter_spell_name = None
        def_cfg.counter_spell_data = None
        db.session.commit()

        client = app.test_client()
        atk_headers = _auth_headers(app, attacker)
        def_headers = _auth_headers(app, defender)

        resp = client.post('/kingdom/conquer/start_battle',
                           json={'land_id': land.id}, headers=atk_headers)
        assert resp.status_code == 200
        game_id = resp.get_json()['game_id']

        game = db.session.get(Game, game_id)
        atk_player = db.session.get(Player, game.invader_player_id)
        def_player = [p for p in game.players if p.user_id == defender.id][0]
        atk_fig = Figure.query.filter_by(
            game_id=game.id, player_id=atk_player.id).first()

        # Two same-color village figures for the defender; the second rests.
        fig_first = Figure(
            game_id=game.id, player_id=def_player.id,
            family_name='Small Rice Farm', name='Small Rice Farm',
            suit='Hearts', color='defensive', field='village',
            produces={'food_red': 8}, requires={},
        )
        fig_resting = Figure(
            game_id=game.id, player_id=def_player.id,
            family_name='Small Rice Farm', name='Small Rice Farm',
            suit='Diamonds', color='defensive', field='village',
            produces={'food_red': 8}, requires={},
        )
        db.session.add_all([fig_first, fig_resting])
        db.session.flush()

        game.battle_modifier = [{'type': 'Civil War'}]
        game.advancing_figure_id = atk_fig.id
        game.advancing_player_id = atk_player.id
        game.invader_player_id = atk_player.id
        game.turn_player_id = def_player.id
        game.resting_figure_ids = [fig_resting.id]
        atk_player.turns_left = 0
        def_player.turns_left = 1
        db.session.commit()

        counter = client.post('/games/advance_figure', json={
            'game_id': game.id,
            'player_id': def_player.id,
            'figure_id': fig_first.id,
        }, headers=def_headers)
        assert counter.status_code == 200, counter.get_json()
        payload = counter.get_json()
        assert payload['civil_war_need_second'] is False, (
            "Resting figure counted as an eligible Civil War second pick"
        )
        db.session.refresh(game)
        # No second pick pending — the turn must flip straight to the invader.
        assert game.turn_player_id == atk_player.id


def test_conquer_ai_watchdog_triggers_on_poll(app, db, monkeypatch):
    """A poll must revive the automated conquer defender when it is stuck.

    If the AI worker thread dies mid-flow (crash, restart), no POST ever
    arrives to re-trigger it — the human can only poll.  get_game runs a
    throttled watchdog that calls trigger_ai_if_needed.
    """
    import importlib
    games_module = importlib.import_module('routes.games')

    with app.app_context():
        attacker = _make_user(db, username='atk_watchdog')
        defender = _make_user(db, username='def_watchdog')

        land = _make_land(db, tier=1, owner_user_id=defender.id)
        _make_conquer_config(db, attacker, land)
        _make_defence_config(db, defender, land)
        db.session.commit()

        client = app.test_client()
        atk_headers = _auth_headers(app, attacker)

        resp = client.post('/kingdom/conquer/start_battle',
                           json={'land_id': land.id}, headers=atk_headers)
        assert resp.status_code == 200
        game_id = resp.get_json()['game_id']

        monkeypatch.setattr(games_module.settings, 'AI_ENABLED', True)
        games_module._conquer_ai_watchdog_last.clear()

        calls = []
        import ai.ai_worker as worker_module
        monkeypatch.setattr(
            worker_module, 'trigger_ai_if_needed',
            lambda gid, app=None: calls.append(gid),
        )

        poll = client.get(f'/games/get_game?game_id={game_id}',
                          headers=atk_headers)
        assert poll.status_code == 200
        assert calls == [game_id], "watchdog did not re-trigger the conquer AI"

        # Throttled: an immediate second poll must not re-trigger.
        poll = client.get(f'/games/get_game?game_id={game_id}',
                          headers=atk_headers)
        assert poll.status_code == 200
        assert calls == [game_id]


def test_conquer_ai_watchdog_triggers_on_active_battle_poll(app, db,
                                                            monkeypatch):
    """The lightweight active-battle poll must also revive the AI worker."""
    import importlib
    games_module = importlib.import_module('routes.games')

    with app.app_context():
        attacker = _make_user(db, username='atk_battle_watchdog')
        defender = _make_user(db, username='def_battle_watchdog')

        land = _make_land(db, tier=1, owner_user_id=defender.id)
        _make_conquer_config(db, attacker, land)
        _make_defence_config(db, defender, land)
        db.session.commit()

        client = app.test_client()
        atk_headers = _auth_headers(app, attacker)
        resp = client.post('/kingdom/conquer/start_battle',
                           json={'land_id': land.id}, headers=atk_headers)
        assert resp.status_code == 200
        game_id = resp.get_json()['game_id']

        game = db.session.get(Game, game_id)
        atk_player = next(p for p in game.players
                          if p.user_id == attacker.id)
        game.battle_confirmed = True
        game.battle_turn_player_id = next(
            p.id for p in game.players if p.id != atk_player.id)
        db.session.commit()

        monkeypatch.setattr(games_module.settings, 'AI_ENABLED', True)
        games_module._conquer_ai_watchdog_last.clear()
        calls = []
        import ai.ai_worker as worker_module
        monkeypatch.setattr(
            worker_module, 'trigger_ai_if_needed',
            lambda gid, app=None: calls.append(gid),
        )

        url = (f'/games/get_battle_state?game_id={game_id}'
               f'&player_id={atk_player.id}')
        poll = client.get(url, headers=atk_headers)
        assert poll.status_code == 200
        assert calls == [game_id]

        # The endpoint shares the same per-game throttle as get_game.
        poll = client.get(url, headers=atk_headers)
        assert poll.status_code == 200
        assert calls == [game_id]
