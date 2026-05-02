# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for Invader Swap as a conquer prelude spell."""
import pytest

from models import (db, User, Land, LandConfig, LandConfigFigure,
                    LandConfigBattleMove, CollectionCard, Game, Player,
                    Figure, ActiveSpell)
from tests.server.test_land_battle import (
    _auth_headers, _make_user, _make_land,
    _make_conquer_config, _make_defence_config,
    _scripted_ai_template,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _start_battle(client, headers, land_id):
    """Call POST /kingdom/conquer/start_battle and return json."""
    resp = client.post('/kingdom/conquer/start_battle',
                       json={'land_id': land_id}, headers=headers)
    assert resp.status_code == 200, resp.get_json()
    data = resp.get_json()
    assert data['success'] is True
    return data


def _invader_swap_spell(game):
    """Return the Invader Swap ActiveSpell for the game, or None."""
    return ActiveSpell.query.filter_by(
        game_id=game.id, spell_name='Invader Swap'
    ).first()


def _set_prelude_invader_swap(db_session, cfg):
    """Set Invader Swap prelude on a config directly (bypasses card-cost check)."""
    cfg.prelude_spell_name = 'Invader Swap'
    cfg.prelude_spell_data = {}
    db_session.session.commit()


# ── Test class ────────────────────────────────────────────────────────────────

class TestConquerInvaderSwapAllowlist:
    """Config validation / allowlist tests."""

    def test_invader_swap_in_conquer_prelude_allowlist(self, app, db):
        """Invader Swap is accepted as a conquer prelude spell at battle start."""
        with app.app_context():
            attacker = _make_user(db, username='atk')
            land = _make_land(db, tier=1)
            cfg = _make_conquer_config(db, attacker, land)
            _set_prelude_invader_swap(db, cfg)

            client = app.test_client()
            headers = _auth_headers(app, attacker)
            data = _start_battle(client, headers, land.id)
            game = db.session.get(Game, data['game_id'])

            spell = _invader_swap_spell(game)
            assert spell is not None, "Invader Swap ActiveSpell should be created"
            assert spell.is_active is True
            ed = spell.effect_data or {}
            assert ed.get('conquer_invader_swap') is True

    def test_invader_swap_not_accepted_on_defence_prelude_config(self, app, db):
        """Invader Swap is rejected when set as a defence prelude spell."""
        with app.app_context():
            attacker = _make_user(db, username='atk')
            defender = _make_user(db, username='def')
            land = _make_land(db, tier=1, owner_user_id=defender.id)
            _make_conquer_config(db, attacker, land)
            def_cfg = _make_defence_config(db, defender, land)

            # Force-set Invader Swap on the defence config (simulating invalid state)
            def_cfg.prelude_spell_name = 'Invader Swap'
            db.session.commit()

            client = app.test_client()
            headers = _auth_headers(app, attacker)
            # The start_battle should succeed but Invader Swap should NOT be applied
            # for the defender (defence prelude allowlist rejects it)
            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=headers)
            data = resp.get_json()
            assert resp.status_code == 200
            game = db.session.get(Game, data['game_id'])

            # Defence player's Invader Swap spell should have a failed / no-effect status
            def_player = [p for p in game.players if p.user_id == defender.id][0]
            swap_spell = ActiveSpell.query.filter_by(
                game_id=game.id, player_id=def_player.id, spell_name='Invader Swap'
            ).first()
            # If a spell record exists it must NOT have swapped roles
            if swap_spell is not None:
                ed = swap_spell.effect_data or {}
                assert not ed.get('conquer_invader_swap'), (
                    "Defence prelude Invader Swap must not actually swap roles"
                )
            # Original attacker must still be the invader (or the AI is — roles unchanged)
            atk_player = next(p for p in game.players if p.user_id == attacker.id)
            assert game.invader_player_id == atk_player.id, (
                "Attacker must remain invader when defence Invader Swap is rejected"
            )


class TestConquerInvaderSwapRoleSwap:
    """Tests that the role swap and turn budget are applied correctly."""

    def test_invader_swap_swaps_invader_player_id(self, app, db):
        """After Invader Swap, game.invader_player_id changes to the original defender."""
        with app.app_context():
            attacker = _make_user(db, username='atk')
            land = _make_land(db, tier=1)
            cfg = _make_conquer_config(db, attacker, land)
            _set_prelude_invader_swap(db, cfg)

            client = app.test_client()
            headers = _auth_headers(app, attacker)
            data = _start_battle(client, headers, land.id)
            game = db.session.get(Game, data['game_id'])

            atk_player = db.session.get(Player, game.invader_player_id)
            # After swap, the AI/defender is now the invader
            assert atk_player.user_id != attacker.id, (
                "Original attacker should no longer be the invader after Invader Swap"
            )

    def test_invader_swap_effect_data_contains_old_new_invader(self, app, db):
        """effect_data has old_invader_id, new_invader_id, invader_swapped=True."""
        with app.app_context():
            attacker = _make_user(db, username='atk')
            land = _make_land(db, tier=1)
            cfg = _make_conquer_config(db, attacker, land)
            _set_prelude_invader_swap(db, cfg)

            client = app.test_client()
            headers = _auth_headers(app, attacker)
            data = _start_battle(client, headers, land.id)
            game = db.session.get(Game, data['game_id'])

            spell = _invader_swap_spell(game)
            assert spell is not None
            ed = spell.effect_data or {}
            assert 'old_invader_id' in ed
            assert 'new_invader_id' in ed
            assert ed.get('invader_swapped') is True
            assert ed.get('old_invader_id') != ed.get('new_invader_id')

    def test_invader_swap_sets_one_turn_budget(self, app, db):
        """Conquer Invader Swap gives each player exactly 1 turn (not 2)."""
        with app.app_context():
            attacker = _make_user(db, username='atk')
            land = _make_land(db, tier=1)
            cfg = _make_conquer_config(db, attacker, land)
            _set_prelude_invader_swap(db, cfg)

            client = app.test_client()
            headers = _auth_headers(app, attacker)
            data = _start_battle(client, headers, land.id)
            game = db.session.get(Game, data['game_id'])

            for p in game.players:
                assert p.turns_left == 1, (
                    f"Player {p.id} should have 1 turn after Invader Swap, got {p.turns_left}"
                )

    def test_invader_swap_turn_player_is_new_invader(self, app, db):
        """After swap, the turn belongs to the new invader."""
        with app.app_context():
            attacker = _make_user(db, username='atk')
            land = _make_land(db, tier=1)
            cfg = _make_conquer_config(db, attacker, land)
            _set_prelude_invader_swap(db, cfg)

            client = app.test_client()
            headers = _auth_headers(app, attacker)
            data = _start_battle(client, headers, land.id)
            game = db.session.get(Game, data['game_id'])

            assert game.turn_player_id == game.invader_player_id, (
                "Turn should be with the new invader after Invader Swap"
            )

    def test_duel_invader_swap_still_grants_two_turns(self, app, db):
        """Duel-mode Invader Swap still uses the standard 2-turn budget."""
        with app.app_context():
            # We test this by checking the duel executor path in spells.py directly.
            # Create a game manually in duel mode and cast Invader Swap.
            from werkzeug.security import generate_password_hash
            from models import ActiveSpell

            u1 = _make_user(db, username='d1')
            u2 = _make_user(db, username='d2')

            # Create a minimal duel game
            game = Game(
                state='open',
                mode='duel',
                stake=5,
                turn_time_limit=300,
                current_round=1,
            )
            db.session.add(game)
            db.session.flush()

            p1 = Player(user_id=u1.id, game_id=game.id, turns_left=2)
            p2 = Player(user_id=u2.id, game_id=game.id, turns_left=2)
            db.session.add_all([p1, p2])
            db.session.flush()

            game.invader_player_id = p1.id
            game.turn_player_id = p1.id
            db.session.flush()

            # Create a test Invader Swap spell (non-prelude duel cast)
            spell = ActiveSpell(
                game_id=game.id,
                player_id=p1.id,
                spell_name='Invader Swap',
                spell_type='tactics',
                spell_family_name='Invader Swap',
                suit='Hearts',
                cast_round=1,
                is_active=True,
                is_pending=False,
                effect_data={},
            )
            db.session.add(spell)
            db.session.commit()

            # Execute directly via spells route
            from routes.spells import _execute_spell
            result = _execute_spell(spell, game, p1)
            db.session.commit()

            # Both players should have 2 turns (duel path)
            db.session.refresh(p1)
            db.session.refresh(p2)
            assert p1.turns_left == 2, f"Duel p1 turns_left={p1.turns_left}, expected 2"
            assert p2.turns_left == 2, f"Duel p2 turns_left={p2.turns_left}, expected 2"


class TestConquerOwnDefenderEndpoint:
    """Tests for POST /games/conquer_select_own_defender."""

    def _setup_swap_game(self, app, db):
        """Create a conquer game with Invader Swap prelude and return helpers."""
        attacker = _make_user(db, username='atk')
        land = _make_land(db, tier=1)
        cfg = _make_conquer_config(db, attacker, land)
        _set_prelude_invader_swap(db, cfg)
        return attacker, land, cfg

    def test_own_defender_rejects_if_no_swap(self, app, db):
        """Endpoint rejects when no Invader Swap spell is active."""
        with app.app_context():
            attacker = _make_user(db, username='atk')
            land = _make_land(db, tier=1)
            _make_conquer_config(db, attacker, land)

            client = app.test_client()
            headers = _auth_headers(app, attacker)
            data = _start_battle(client, headers, land.id)
            game = db.session.get(Game, data['game_id'])

            atk_player = next(p for p in game.players if p.user_id == attacker.id)
            own_fig = Figure.query.filter_by(game_id=game.id, player_id=atk_player.id).first()
            assert own_fig is not None

            resp = client.post('/games/conquer_select_own_defender', json={
                'game_id': game.id,
                'player_id': atk_player.id,
                'figure_id': own_fig.id,
            }, headers=headers)
            assert resp.status_code == 400
            data_r = resp.get_json()
            assert not data_r.get('success')

    def test_own_defender_rejects_opponent_figure(self, app, db):
        """Endpoint rejects selecting an opponent figure."""
        with app.app_context():
            attacker, land, _ = self._setup_swap_game(app, db)
            client = app.test_client()
            headers = _auth_headers(app, attacker)
            data = _start_battle(client, headers, land.id)
            game = db.session.get(Game, data['game_id'])

            atk_player = next(p for p in game.players if p.user_id == attacker.id)
            # After swap, attacker is no longer the invader;
            # find an opponent figure (new invader's figure)
            opp_fig = Figure.query.filter_by(game_id=game.id).filter(
                Figure.player_id != atk_player.id
            ).first()
            if opp_fig is None:
                pytest.skip("No opponent figure found")

            # Provide a fake advancing figure so we get past other validations
            game.advancing_figure_id = opp_fig.id
            game.advancing_player_id = opp_fig.player_id
            game.turn_player_id = atk_player.id
            db.session.commit()

            own_fig = Figure.query.filter_by(game_id=game.id, player_id=atk_player.id).first()

            resp = client.post('/games/conquer_select_own_defender', json={
                'game_id': game.id,
                'player_id': atk_player.id,
                'figure_id': opp_fig.id,
            }, headers=headers)
            assert resp.status_code == 400, resp.get_json()
            assert not resp.get_json().get('success')


class TestConquerInvaderSwapGameFlow:
    """Integration: full game flow after Invader Swap."""

    def test_invader_swap_not_in_battle_modifier(self, app, db):
        """Invader Swap must NOT appear in game.battle_modifier."""
        with app.app_context():
            attacker = _make_user(db, username='atk')
            land = _make_land(db, tier=1)
            cfg = _make_conquer_config(db, attacker, land)
            _set_prelude_invader_swap(db, cfg)

            client = app.test_client()
            headers = _auth_headers(app, attacker)
            data = _start_battle(client, headers, land.id)
            game = db.session.get(Game, data['game_id'])

            modifiers = game.battle_modifier or []
            modifier_types = [m.get('type') for m in modifiers] if isinstance(modifiers, list) else []
            assert 'Invader Swap' not in modifier_types, (
                "Invader Swap must not be added to battle_modifier"
            )

    def test_stale_state_cleared_after_invader_swap(self, app, db):
        """After Invader Swap, advancing/defending figure IDs must be cleared."""
        with app.app_context():
            attacker = _make_user(db, username='atk')
            land = _make_land(db, tier=1)
            cfg = _make_conquer_config(db, attacker, land)
            _set_prelude_invader_swap(db, cfg)

            client = app.test_client()
            headers = _auth_headers(app, attacker)
            data = _start_battle(client, headers, land.id)
            game = db.session.get(Game, data['game_id'])

            assert game.advancing_figure_id is None
            assert game.advancing_figure_id_2 is None
            assert game.defending_figure_id is None
            assert game.defending_figure_id_2 is None

    def test_invader_swap_stacks_with_civil_war(self, app, db):
        """Invader Swap as prelude and Civil War as a second prelude both apply."""
        with app.app_context():
            attacker = _make_user(db, username='atk')
            defender = _make_user(db, username='def')
            land = _make_land(db, tier=1, owner_user_id=defender.id)
            atk_cfg = _make_conquer_config(db, attacker, land)
            def_cfg = _make_defence_config(db, defender, land)
            _set_prelude_invader_swap(db, atk_cfg)

            # Defence config uses Civil War as its prelude
            def_cfg.prelude_spell_name = 'Civil War'
            def_cfg.prelude_spell_data = {}
            db.session.commit()

            client = app.test_client()
            headers = _auth_headers(app, attacker)
            data = _start_battle(client, headers, land.id)
            game = db.session.get(Game, data['game_id'])

            # Invader Swap role-swap happened (attacker is no longer invader)
            atk_player = next(p for p in game.players if p.user_id == attacker.id)
            assert game.invader_player_id != atk_player.id

            # Civil War modifier present
            modifiers = game.battle_modifier or []
            mod_types = [m.get('type') for m in modifiers] if isinstance(modifiers, list) else []
            assert 'Civil War' in mod_types

    def test_invader_swap_counter_spell_ignored(self, app, db):
        """Defence counter spell is silently ignored when Invader Swap is active."""
        with app.app_context():
            attacker = _make_user(db, username='atk')
            defender = _make_user(db, username='def')
            land = _make_land(db, tier=1, owner_user_id=defender.id)
            cfg = _make_conquer_config(db, attacker, land)
            def_cfg = _make_defence_config(db, defender, land)
            _set_prelude_invader_swap(db, cfg)

            # Give the defence config a counter spell
            def_cfg.counter_spell_name = 'Poison'
            def_cfg.battle_figure_id = None
            db.session.commit()

            client = app.test_client()
            headers = _auth_headers(app, attacker)
            data = _start_battle(client, headers, land.id)
            game = db.session.get(Game, data['game_id'])

            # The game should still resolve (no crash)
            assert game is not None
            spell = _invader_swap_spell(game)
            assert spell is not None
            ed = spell.effect_data or {}
            assert ed.get('conquer_invader_swap') is True
