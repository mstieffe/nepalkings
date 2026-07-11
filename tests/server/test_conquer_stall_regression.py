# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Regression tests: the conquer flow must never strand the turn.

Companions to the client-side poller stall fix (production game 140).
Server-side there were two ways the automated defender could hold the turn
forever after the invader advanced:

1. ``_figure_can_counter_advance`` ignored resting figures while the AI
   worker's own legality check excluded them — the server opened a defender
   response window the AI then refused to answer.
2. When the AI defender found no legal counter-advance in an open response
   window (rule drift / races), the worker logged a warning and exited,
   leaving ``turn_player_id`` on the defender with nothing to re-trigger a
   state change.
"""
from models import db, Figure, Game, LogEntry, Player

import ai.ai_worker as ai_worker

from tests.server.test_conquer_ai_defender_response import (
    _install_ai_post_via_test_client,
)
from tests.server.test_land_battle import (
    _auth_headers, _make_conquer_config, _make_defence_config,
    _make_land, _make_user,
)


def _start_conquer_and_advance(app, db, *, attacker_name, defender_name):
    """Create a conquer game vs a player land and advance the attacker."""
    attacker = _make_user(db, username=attacker_name)
    defender = _make_user(db, username=defender_name)
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
    assert resp.status_code == 200, resp.get_json()
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
    return game, atk_player, def_player


def test_resting_figure_cannot_counter_advance(app, db):
    """Server legality must match the AI worker: resting figures are out."""
    with app.app_context():
        from routes.games import _figure_can_counter_advance

        game, atk_player, def_player = _start_conquer_and_advance(
            app, db, attacker_name='rest_atk', defender_name='rest_def')

        def_fig = Figure.query.filter_by(
            game_id=game.id, player_id=def_player.id).first()
        assert _figure_can_counter_advance(def_fig, def_player.id, game.id)

        game.resting_figure_ids = [def_fig.id]
        db.session.commit()
        assert not _figure_can_counter_advance(def_fig, def_player.id, game.id)


def test_ai_defender_with_no_legal_response_returns_turn(app, db, monkeypatch):
    """An unanswerable response window must be spent, not stalled on.

    Simulates the drift case: the response window opened for the automated
    defender, but by the time the worker acts a castle-only Royal Decree
    modifier makes every defender figure illegal for counter-advance.
    The worker must hand the turn back to the invader.
    """
    with app.app_context():
        game, atk_player, def_player = _start_conquer_and_advance(
            app, db, attacker_name='stall_atk', defender_name='stall_def')
        game_id = game.id
        atk_player_id = atk_player.id
        def_player_id = def_player.id

        # The advance opened the defender response window.
        assert game.turn_player_id == def_player_id
        assert game.defending_figure_id is None

        # Drift: castle-only restriction arrives while every defender figure
        # is a village figure — no legal counter-advance remains.
        game.battle_modifier = [{'type': 'Royal Decree',
                                 'caster_id': atk_player_id}]
        for fig in Figure.query.filter_by(game_id=game.id,
                                          player_id=def_player_id).all():
            fig.field = 'village'
        db.session.commit()

        with ai_worker._ai_player_user_ids_lock:
            ai_worker._ai_player_user_ids[def_player_id] = def_player.user_id
        _install_ai_post_via_test_client(app, monkeypatch)

    ai_worker._conquer_ai_loop(app, game_id, def_player_id)

    with app.app_context():
        game_after = db.session.get(Game, game_id)
        # The turn is back with the invader; no counter-advance happened.
        assert game_after.turn_player_id == atk_player_id, (
            'AI defender stalled the game instead of spending its response'
        )
        assert game_after.defending_figure_id is None
        spent_log = LogEntry.query.filter_by(
            game_id=game_id, player_id=def_player_id, type='battle_skip',
        ).first()
        assert spent_log is not None
