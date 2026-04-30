# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Regression tests for conquer auto-loss resolution paths."""

from datetime import datetime, timezone

from models import Game, Figure, LandAttackLog, LogEntry, Player

from tests.server.test_land_battle import (
    _auth_headers,
    _make_conquer_config,
    _make_defence_config,
    _make_land,
    _make_user,
)


def _start_conquer(client, headers, land_id):
    resp = client.post('/kingdom/conquer/start_battle',
                       json={'land_id': land_id}, headers=headers)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()['game_id']


class TestConquerAutoLossResolution:
    def test_cannot_advance_loss_resolves_conquer_and_is_idempotent(self, app, db):
        with app.app_context():
            attacker = _make_user(db, username='att_no_advance')
            defender = _make_user(db, username='def_no_advance')
            land = _make_land(db, tier=1, owner_user_id=defender.id)
            atk_cfg = _make_conquer_config(db, attacker, land)
            _make_defence_config(db, defender, land)

            # Simulate Peasant War making the attacker's only castle figure illegal.
            cfg_fig = atk_cfg.figures[0]
            cfg_fig.family_name = 'Djungle King'
            cfg_fig.name = 'Djungle King'
            cfg_fig.field = 'castle'
            db.session.commit()

            client = app.test_client()
            atk_headers = _auth_headers(app, attacker)
            game_id = _start_conquer(client, atk_headers, land.id)
            game = db.session.get(Game, game_id)
            atk_player = db.session.get(Player, game.invader_player_id)
            game.battle_modifier = [{'type': 'Peasant War'}]
            game.turn_player_id = atk_player.id
            db.session.commit()

            resp = client.post('/games/cannot_advance_loss', json={
                'game_id': game.id,
                'player_id': atk_player.id,
            }, headers=atk_headers)
            data = resp.get_json()

            assert resp.status_code == 200, data
            assert data['success'] is True
            assert data['conquer_result'] == 'defender_won'
            assert data['attacker_won'] is False
            assert data['auto_loss_reason'] == 'no_figures_to_advance'
            db.session.refresh(game)
            assert game.state == 'finished'
            assert game.last_battle_result['auto_loss_reason'] == 'no_figures_to_advance'
            assert LandAttackLog.query.filter_by(land_id=land.id).count() == 1
            assert LogEntry.query.filter_by(game_id=game.id, type='auto_loss').count() == 1

            # Repeated/stale call returns cached conquer payload and writes no duplicates.
            again = client.post('/games/cannot_advance_loss', json={
                'game_id': game.id,
                'player_id': atk_player.id,
            }, headers=atk_headers)
            again_data = again.get_json()
            assert again.status_code == 200, again_data
            assert again_data['already_resolved'] is True
            assert again_data['conquer_result'] == 'defender_won'
            assert LandAttackLog.query.filter_by(land_id=land.id).count() == 1
            assert LogEntry.query.filter_by(game_id=game.id, type='auto_loss').count() == 1

    def test_cannot_advance_loss_rejects_when_a_figure_can_advance(self, app, db):
        with app.app_context():
            attacker = _make_user(db, username='att_can_advance')
            defender = _make_user(db, username='def_can_advance')
            land = _make_land(db, tier=1, owner_user_id=defender.id)
            _make_conquer_config(db, attacker, land)
            _make_defence_config(db, defender, land)

            client = app.test_client()
            atk_headers = _auth_headers(app, attacker)
            game_id = _start_conquer(client, atk_headers, land.id)
            game = db.session.get(Game, game_id)
            atk_player = db.session.get(Player, game.invader_player_id)
            game.turn_player_id = atk_player.id
            db.session.commit()

            resp = client.post('/games/cannot_advance_loss', json={
                'game_id': game.id,
                'player_id': atk_player.id,
            }, headers=atk_headers)
            data = resp.get_json()

            assert resp.status_code == 400
            assert data['reason'] == 'advanceable_figure_exists'
            assert LandAttackLog.query.filter_by(land_id=land.id).count() == 0

    def test_defender_no_figures_loss_resolves_conquer(self, app, db):
        with app.app_context():
            attacker = _make_user(db, username='att_no_defender')
            defender = _make_user(db, username='def_no_defender')
            land = _make_land(db, tier=1, owner_user_id=defender.id)
            _make_conquer_config(db, attacker, land)
            _make_defence_config(db, defender, land)

            client = app.test_client()
            atk_headers = _auth_headers(app, attacker)
            game_id = _start_conquer(client, atk_headers, land.id)
            game = db.session.get(Game, game_id)
            atk_player = db.session.get(Player, game.invader_player_id)
            atk_fig = Figure.query.filter_by(
                game_id=game.id,
                player_id=atk_player.id,
            ).first()
            game.battle_modifier = [{'type': 'Peasant War'}]
            game.advancing_player_id = atk_player.id
            game.advancing_figure_id = atk_fig.id
            game.turn_player_id = atk_player.id
            db.session.commit()

            resp = client.post('/games/defender_no_figures_loss', json={
                'game_id': game.id,
                'player_id': atk_player.id,
            }, headers=atk_headers)
            data = resp.get_json()

            assert resp.status_code == 200, data
            assert data['success'] is True
            assert data['conquer_result'] == 'attacker_won'
            assert data['attacker_won'] is True
            assert data['auto_loss_reason'] == 'no_defender_figures'
            db.session.refresh(land)
            assert land.owner_user_id == attacker.id

    def test_defender_no_figures_loss_rejects_selectable_defender(self, app, db):
        with app.app_context():
            attacker = _make_user(db, username='att_def_exists')
            defender = _make_user(db, username='def_def_exists')
            land = _make_land(db, tier=1, owner_user_id=defender.id)
            _make_conquer_config(db, attacker, land)
            def_cfg = _make_defence_config(db, defender, land)
            cfg_fig = def_cfg.figures[0]
            cfg_fig.family_name = 'Small Yack Farm'
            cfg_fig.name = 'Small Yack Farm'
            cfg_fig.field = 'village'
            db.session.commit()

            client = app.test_client()
            atk_headers = _auth_headers(app, attacker)
            game_id = _start_conquer(client, atk_headers, land.id)
            game = db.session.get(Game, game_id)
            atk_player = db.session.get(Player, game.invader_player_id)
            atk_fig = Figure.query.filter_by(
                game_id=game.id,
                player_id=atk_player.id,
            ).first()
            game.battle_modifier = [{'type': 'Peasant War'}]
            game.advancing_player_id = atk_player.id
            game.advancing_figure_id = atk_fig.id
            game.turn_player_id = atk_player.id
            db.session.commit()

            resp = client.post('/games/defender_no_figures_loss', json={
                'game_id': game.id,
                'player_id': atk_player.id,
            }, headers=atk_headers)
            data = resp.get_json()

            assert resp.status_code == 400
            assert data['reason'] == 'selectable_defender_exists'
            assert LandAttackLog.query.filter_by(land_id=land.id).count() == 0

    def test_select_defender_deficit_resolves_conquer(self, app, db):
        with app.app_context():
            attacker = _make_user(db, username='att_deficit_select')
            defender = _make_user(db, username='def_deficit_select')
            land = _make_land(db, tier=1, owner_user_id=defender.id)
            _make_conquer_config(db, attacker, land)
            _make_defence_config(db, defender, land)

            client = app.test_client()
            atk_headers = _auth_headers(app, attacker)
            game_id = _start_conquer(client, atk_headers, land.id)
            game = db.session.get(Game, game_id)
            atk_player = db.session.get(Player, game.invader_player_id)
            def_player = [p for p in game.players if p.id != atk_player.id][0]
            atk_fig = Figure.query.filter_by(game_id=game.id, player_id=atk_player.id).first()
            def_fig = Figure.query.filter_by(game_id=game.id, player_id=def_player.id).first()
            def_fig.requires = {'food_black': 1}
            game.advancing_player_id = atk_player.id
            game.advancing_figure_id = atk_fig.id
            game.defending_figure_id = None
            game.turn_player_id = atk_player.id
            db.session.commit()

            resp = client.post('/games/select_defender', json={
                'game_id': game.id,
                'player_id': atk_player.id,
                'figure_id': def_fig.id,
            }, headers=atk_headers)
            data = resp.get_json()

            assert resp.status_code == 200, data
            assert data['success'] is True
            assert data['conquer_result'] == 'attacker_won'
            assert data['auto_loss_reason'] == 'resource_deficit'
            assert 'deficit_loss' not in data
            db.session.refresh(land)
            assert land.owner_user_id == attacker.id

    def test_finish_battle_draw_returns_finished_conquer_draw(self, app, db):
        with app.app_context():
            attacker = _make_user(db, username='att_finished_draw')
            defender = _make_user(db, username='def_finished_draw')
            land = _make_land(db, tier=1, owner_user_id=defender.id)
            game = Game(
                mode='conquer',
                state='finished',
                land_id=land.id,
                stake=0,
                current_round=1,
                ceasefire_active=False,
                battle_confirmed=False,
                winner_player_id=None,
                finished_at=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            db.session.add(game)
            db.session.flush()
            atk_player = Player(user_id=attacker.id, game_id=game.id, turns_left=0, points=0)
            def_player = Player(user_id=defender.id, game_id=game.id, turns_left=0, points=0)
            db.session.add_all([atk_player, def_player])
            db.session.flush()
            game.invader_player_id = atk_player.id
            game.turn_player_id = atk_player.id
            db.session.commit()

            client = app.test_client()
            resp = client.post('/games/finish_battle_draw', json={
                'game_id': game.id,
                'player_id': atk_player.id,
                'choice': 'destroy',
            }, headers=_auth_headers(app, attacker))
            data = resp.get_json()

            assert resp.status_code == 200, data
            assert data['success'] is True
            assert data['already_resolved'] is True
            assert data['conquer_result'] == 'draw'
            assert data['outcome'] == 'draw'
            assert LandAttackLog.query.filter_by(land_id=land.id).count() == 0
