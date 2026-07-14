# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for the conquer spell expansion.

Covers Royal Decree (castle-only battles + fresh hands), Copy Figure
(hidden-target battle clone), Landslide (inverted land bonus), Draw 4
MainCards, the All Seeing Eye gamble preview, and the removal of
Fill up to 10 from the conquer/defence prelude pools.
"""
import pytest

from models import (db, User, Land, LandConfig, LandConfigFigure,
                    LandConfigBattleMove, CollectionCard, Game, Player,
                    Figure, ConquerTactic, CardToFigure, ActiveSpell)

from tests.server.test_land_battle import (
    _make_user,
    _make_land,
    _make_conquer_config,
    _make_defence_config,
    _auth_headers,
)


NEW_CONQUER_SPELLS = ('Royal Decree', 'Copy Figure', 'Landslide',
                      'Draw 4 MainCards')

_SPELL_FREE_CARDS = {
    'Royal Decree':     [('K', 'Hearts'), ('K', 'Diamonds')],
    'Copy Figure':      [('10', 'Hearts'), ('10', 'Diamonds')],
    'Landslide':        [('2', 'Hearts'), ('2', 'Diamonds')],
    'Draw 4 MainCards': [('8', 'Hearts'), ('8', 'Diamonds')],
}


def _give_free_cards(user, specs):
    for rank, suit in specs:
        db.session.add(CollectionCard(
            user_id=user.id, suit=suit, rank=rank,
            value=10 if rank == '10' else 4, locked=False,
        ))
    db.session.commit()


def _add_defence_config_figure(cfg, user, *, family_name, name=None,
                               suit='Spades', color='defensive',
                               field='village', checkmate=False,
                               card_rank='9', card_value=9):
    cc = CollectionCard(user_id=user.id, suit=suit, rank=card_rank,
                        value=card_value, locked=True,
                        lock_type='defence_figure')
    db.session.add(cc)
    db.session.flush()
    fig = LandConfigFigure(
        config_id=cfg.id,
        family_name=family_name,
        name=name or family_name,
        suit=suit, color=color, field=field,
        card_ids=[cc.id], card_roles=['key'],
        produces={}, requires={},
        checkmate=checkmate,
    )
    db.session.add(fig)
    db.session.commit()
    return fig


def _add_conquer_castle_figure(cfg, user, *, suit='Diamonds'):
    cc = CollectionCard(user_id=user.id, suit=suit, rank='K', value=4,
                        locked=True, lock_type='conquer_figure')
    db.session.add(cc)
    db.session.flush()
    fig = LandConfigFigure(
        config_id=cfg.id,
        family_name='Djungle King', name='Djungle King',
        suit=suit, color='offensive', field='castle',
        card_ids=[cc.id], card_roles=['key'],
        produces={'villager_red': 2, 'warrior_red': 1}, requires={},
    )
    db.session.add(fig)
    db.session.commit()
    return fig


def _game_player(game, user):
    return next(p for p in game.players if p.user_id == user.id)


def _start_battle(app, attacker, land):
    client = app.test_client()
    headers = _auth_headers(app, attacker)
    resp = client.post('/kingdom/conquer/start_battle',
                       json={'land_id': land.id}, headers=headers)
    assert resp.status_code == 200, resp.get_json()
    game = db.session.get(Game, resp.get_json()['game_id'])
    return client, headers, game


# ── Prelude selection allowlists ─────────────────────────────────────────────

class TestPreludeAllowlists:
    @pytest.mark.parametrize('spell_name', NEW_CONQUER_SPELLS)
    def test_conquer_set_prelude_accepts_new_spells(self, app, db, spell_name):
        with app.app_context():
            user = _make_user(db)
            land = _make_land(db)
            _make_conquer_config(db, user, land)
            _give_free_cards(user, _SPELL_FREE_CARDS[spell_name])

            client = app.test_client()
            resp = client.post('/kingdom/conquer/set_prelude_spell', json={
                'land_id': land.id, 'spell_name': spell_name,
            }, headers=_auth_headers(app, user))
            assert resp.status_code == 200, resp.get_json()
            assert resp.get_json()['success'] is True

    @pytest.mark.parametrize('spell_name', NEW_CONQUER_SPELLS)
    def test_defence_set_prelude_accepts_new_spells(self, app, db, spell_name):
        with app.app_context():
            user = _make_user(db)
            land = _make_land(db, owner_user_id=None)
            land.owner_user_id = user.id
            db.session.commit()
            _give_free_cards(user, _SPELL_FREE_CARDS[spell_name])

            client = app.test_client()
            resp = client.post('/kingdom/defence/set_prelude_spell', json={
                'land_id': land.id, 'spell_name': spell_name,
            }, headers=_auth_headers(app, user))
            assert resp.status_code == 200, resp.get_json()
            assert resp.get_json()['success'] is True

    def test_fill_up_to_10_rejected_as_prelude(self, app, db):
        with app.app_context():
            user = _make_user(db)
            land = _make_land(db)
            _make_conquer_config(db, user, land)
            _give_free_cards(user, [('10', 'Hearts')])

            client = app.test_client()
            headers = _auth_headers(app, user)
            resp = client.post('/kingdom/conquer/set_prelude_spell', json={
                'land_id': land.id, 'spell_name': 'Fill up to 10',
            }, headers=headers)
            assert resp.status_code == 400

            owned = _make_land(db)
            owned.owner_user_id = user.id
            db.session.commit()
            resp = client.post('/kingdom/defence/set_prelude_spell', json={
                'land_id': owned.id, 'spell_name': 'Fill up to 10',
            }, headers=headers)
            assert resp.status_code == 400

    @pytest.mark.parametrize('spell_name', NEW_CONQUER_SPELLS)
    def test_duel_cast_route_rejects_conquer_only_spells(self, app, db, spell_name):
        with app.app_context():
            user = _make_user(db)
            opponent = _make_user(db, username='duel_opp')
            game = Game(mode='duel', state='open', stake=45, current_round=1)
            db.session.add(game)
            db.session.flush()
            player = Player(user_id=user.id, game_id=game.id,
                            turns_left=3, points=0)
            opp_player = Player(user_id=opponent.id, game_id=game.id,
                                turns_left=3, points=0)
            db.session.add_all([player, opp_player])
            db.session.flush()
            game.turn_player_id = player.id
            game.invader_player_id = player.id
            db.session.commit()

            client = app.test_client()
            resp = client.post('/spells/cast_spell', json={
                'player_id': player.id,
                'game_id': game.id,
                'spell_name': spell_name,
                'spell_type': 'tactics',
                'spell_family_name': spell_name,
                'suit': 'Hearts',
                'cards': [],
            }, headers=_auth_headers(app, user))
            assert resp.status_code == 400
            assert resp.get_json().get('reason') == 'conquer_only_spell'


# ── battle_required_field helper ─────────────────────────────────────────────

class TestBattleRequiredField:
    def test_royal_decree_requires_castle(self):
        from game_service.figure_rule_helpers import battle_required_field
        assert battle_required_field([{'type': 'Royal Decree'}]) == 'castle'

    def test_village_only_modifiers(self):
        from game_service.figure_rule_helpers import battle_required_field
        assert battle_required_field([{'type': 'Peasant War'}]) == 'village'
        assert battle_required_field([{'type': 'Civil War'}]) == 'village'

    def test_royal_decree_precedence_over_village_only(self):
        from game_service.figure_rule_helpers import battle_required_field
        assert battle_required_field([
            {'type': 'Peasant War'}, {'type': 'Royal Decree'},
        ]) == 'castle'
        assert battle_required_field([
            {'type': 'Royal Decree'}, {'type': 'Civil War'},
        ]) == 'castle'

    def test_landslide_and_blitzkrieg_do_not_restrict_field(self):
        from game_service.figure_rule_helpers import battle_required_field
        assert battle_required_field([{'type': 'Landslide'}]) is None
        assert battle_required_field([{'type': 'Blitzkrieg'}]) is None
        assert battle_required_field([]) is None


# ── Royal Decree battle flow ─────────────────────────────────────────────────

class TestRoyalDecree:
    def _setup(self, app, db):
        attacker = _make_user(db, username='rd_atk')
        defender = _make_user(db, username='rd_def')
        land = _make_land(db, tier=1, owner_user_id=defender.id)
        atk_cfg = _make_conquer_config(db, attacker, land)
        _add_conquer_castle_figure(atk_cfg, attacker)
        def_cfg = _make_defence_config(db, defender, land)
        # Give the defender a village figure next to the castle King so the
        # castle-only restriction is observable on defender selection.
        _add_defence_config_figure(def_cfg, defender,
                                   family_name='Small Yack Farm',
                                   field='village')
        atk_cfg.prelude_spell_name = 'Royal Decree'
        atk_cfg.prelude_spell_data = {}
        db.session.commit()
        return attacker, defender, land, atk_cfg, def_cfg

    def test_decree_registers_modifier_and_refreshes_hands(self, app, db):
        with app.app_context():
            attacker, defender, land, _atk_cfg, _def_cfg = self._setup(app, db)
            client, headers, game = _start_battle(app, attacker, land)

            modifiers = game.battle_modifier or []
            assert any(m.get('type') == 'Royal Decree' for m in modifiers)

            atk_player = _game_player(game, attacker)
            spell = ActiveSpell.query.filter_by(
                game_id=game.id, player_id=atk_player.id,
                spell_name='Royal Decree').first()
            assert spell is not None
            effect_data = spell.effect_data or {}
            assert effect_data.get('prelude_status') == 'executed'
            # Dump-Cards fresh-hand effect ran for both players.
            assert 'caster_dumped' in effect_data
            assert 'opponent_dumped' in effect_data

    def test_decree_without_castle_is_rejected_before_battle_creation(self, app, db):
        with app.app_context():
            attacker = _make_user(db, username='rd_no_castle_atk')
            defender = _make_user(db, username='rd_no_castle_def')
            land = _make_land(db, tier=1, owner_user_id=defender.id)
            atk_cfg = _make_conquer_config(db, attacker, land)
            _make_defence_config(db, defender, land)
            atk_cfg.prelude_spell_name = 'Royal Decree'
            atk_cfg.prelude_spell_data = {}
            db.session.commit()

            client = app.test_client()
            response = client.post(
                '/kingdom/conquer/start_battle',
                json={'land_id': land.id},
                headers=_auth_headers(app, attacker),
            )

            assert response.status_code == 400
            payload = response.get_json()
            assert payload.get('reason') == 'no_legal_battle_figure'
            assert 'castle figure' in payload.get('message', '').lower()

    def test_decree_castle_only_advance_and_defender_selection(self, app, db):
        with app.app_context():
            attacker, defender, land, _atk_cfg, _def_cfg = self._setup(app, db)
            client, headers, game = _start_battle(app, attacker, land)
            atk_player = _game_player(game, attacker)
            def_player = _game_player(game, defender)

            village_fig = Figure.query.filter_by(
                game_id=game.id, player_id=atk_player.id,
                field='village').first()
            castle_fig = Figure.query.filter_by(
                game_id=game.id, player_id=atk_player.id,
                field='castle').first()
            assert village_fig is not None and castle_fig is not None

            resp = client.post('/games/advance_figure', json={
                'game_id': game.id, 'player_id': atk_player.id,
                'figure_id': village_fig.id,
            }, headers=headers)
            assert resp.status_code == 400
            assert 'castle' in resp.get_json()['message'].lower()

            resp = client.post('/games/advance_figure', json={
                'game_id': game.id, 'player_id': atk_player.id,
                'figure_id': castle_fig.id,
            }, headers=headers)
            assert resp.status_code == 200, resp.get_json()

            # Defender selection (once it is the invader's pick) is
            # castle-only as well.
            game = db.session.get(Game, game.id)
            game.turn_player_id = atk_player.id
            game.defending_figure_id = None
            game.defending_figure_id_2 = None
            db.session.commit()

            def_village = Figure.query.filter_by(
                game_id=game.id, player_id=def_player.id,
                field='village').first()
            def_castle = Figure.query.filter_by(
                game_id=game.id, player_id=def_player.id,
                field='castle').first()
            assert def_village is not None and def_castle is not None

            resp = client.post('/games/select_defender', json={
                'game_id': game.id, 'player_id': atk_player.id,
                'figure_id': def_village.id,
            }, headers=headers)
            assert resp.status_code == 400
            assert 'castle' in resp.get_json()['message'].lower()

            resp = client.post('/games/select_defender', json={
                'game_id': game.id, 'player_id': atk_player.id,
                'figure_id': def_castle.id,
            }, headers=headers)
            assert resp.status_code == 200, resp.get_json()

    def test_decree_precedence_suppresses_civil_war_pick_flow(self, app, db):
        with app.app_context():
            attacker, defender, land, _atk_cfg, _def_cfg = self._setup(app, db)
            client, headers, game = _start_battle(app, attacker, land)
            atk_player = _game_player(game, attacker)

            game.battle_modifier = (game.battle_modifier or []) + [
                {'type': 'Civil War', 'caster_id': atk_player.id},
            ]
            db.session.commit()

            castle_fig = Figure.query.filter_by(
                game_id=game.id, player_id=atk_player.id,
                field='castle').first()
            resp = client.post('/games/advance_figure', json={
                'game_id': game.id, 'player_id': atk_player.id,
                'figure_id': castle_fig.id,
            }, headers=headers)
            assert resp.status_code == 200, resp.get_json()
            data = resp.get_json()
            # Royal Decree wins: castle figure advances and the Civil War
            # two-pick flow never opens.
            assert data.get('civil_war_need_second') is False

    def test_attacker_decree_and_defender_civil_war_reach_castle_battle(
        self, app, db, monkeypatch
    ):
        """The reported modifier combination must leave one resolvable pool."""
        with app.app_context():
            attacker, defender, land, _atk_cfg, def_cfg = self._setup(app, db)
            first_village = _add_defence_config_figure(
                def_cfg,
                defender,
                family_name='Small Rice Farm',
                suit='Hearts',
                color='defensive',
                field='village',
            )
            second_village = _add_defence_config_figure(
                def_cfg,
                defender,
                family_name='Small Yack Farm',
                suit='Diamonds',
                color='defensive',
                field='village',
            )
            def_cfg.prelude_spell_name = 'Civil War'
            def_cfg.prelude_spell_data = {}
            def_cfg.battle_figure_id = first_village.id
            def_cfg.battle_figure_id_2 = second_village.id
            def_cfg.counter_spell_name = None
            db.session.commit()

            client, headers, game = _start_battle(app, attacker, land)
            atk_player = _game_player(game, attacker)
            def_player = _game_player(game, defender)
            modifier_types = {
                modifier.get('type') for modifier in (game.battle_modifier or [])
            }
            assert {'Royal Decree', 'Civil War'} <= modifier_types

            attacker_castle = Figure.query.filter_by(
                game_id=game.id,
                player_id=atk_player.id,
                field='castle',
            ).first()
            response = client.post('/games/advance_figure', json={
                'game_id': game.id,
                'player_id': atk_player.id,
                'figure_id': attacker_castle.id,
            }, headers=headers)
            assert response.status_code == 200, response.get_json()
            assert response.get_json().get('civil_war_need_second') is False

            db.session.refresh(game)
            if game.turn_player_id == def_player.id:
                import ai.ai_worker as ai_worker
                from tests.server.test_conquer_ai_defender_response import (
                    _install_ai_post_via_test_client,
                )
                with ai_worker._ai_player_user_ids_lock:
                    ai_worker._ai_player_user_ids[def_player.id] = defender.id
                _install_ai_post_via_test_client(app, monkeypatch)
                game_id = game.id
                def_player_id = def_player.id
            else:
                game_id = game.id
                def_player_id = None

        if def_player_id is not None:
            ai_worker._conquer_ai_loop(app, game_id, def_player_id)

        with app.app_context():
            game = db.session.get(Game, game_id)
            atk_player = _game_player(game, attacker)
            def_player = _game_player(game, defender)
            if game.defending_figure_id is None:
                defender_castle = Figure.query.filter_by(
                    game_id=game.id,
                    player_id=def_player.id,
                    field='castle',
                ).first()
                response = app.test_client().post('/games/select_defender', json={
                    'game_id': game.id,
                    'player_id': atk_player.id,
                    'figure_id': defender_castle.id,
                }, headers=_auth_headers(app, attacker))
                assert response.status_code == 200, response.get_json()
                assert response.get_json().get('civil_war_need_second') is False
                db.session.refresh(game)

            defender_figure = db.session.get(Figure, game.defending_figure_id)
            assert defender_figure is not None
            assert defender_figure.field == 'castle'
            assert game.defending_figure_id_2 is None
            assert game.turn_player_id == atk_player.id

    def test_no_legal_castle_figures_resolve_via_loss_paths(self, app, db):
        with app.app_context():
            from routes.games import (_has_advanceable_figure,
                                      _has_selectable_defender)
            attacker, defender, land, _atk_cfg, _def_cfg = self._setup(app, db)
            client, headers, game = _start_battle(app, attacker, land)
            atk_player = _game_player(game, attacker)
            def_player = _game_player(game, defender)

            assert _has_advanceable_figure(game, atk_player.id) is True
            assert _has_selectable_defender(game, def_player.id) is True

            # Remove all castle figures: the legality helpers that feed
            # cannot_advance_loss / defender_no_figures_loss must report
            # no legal figure instead of stalling the phase.
            for fig in Figure.query.filter_by(game_id=game.id,
                                              field='castle').all():
                CardToFigure.query.filter_by(figure_id=fig.id).delete()
                db.session.delete(fig)
            db.session.commit()

            assert _has_advanceable_figure(game, atk_player.id) is False
            assert _has_selectable_defender(game, def_player.id) is False


# ── Copy Figure ──────────────────────────────────────────────────────────────

class TestCopyFigure:
    def _setup(self, app, db, *, attacker_prelude=True):
        attacker = _make_user(db, username='cp_atk')
        defender = _make_user(db, username='cp_def')
        land = _make_land(db, tier=1, owner_user_id=defender.id)
        atk_cfg = _make_conquer_config(db, attacker, land)
        def_cfg = _make_defence_config(db, defender, land)
        # Defender army spans all three fields incl. a checkmate Maharaja
        # and an untargetable Wall.
        _add_defence_config_figure(def_cfg, defender,
                                   family_name='Small Yack Farm',
                                   field='village')
        _add_defence_config_figure(def_cfg, defender,
                                   family_name='Gorkha Warriors',
                                   field='military')
        _add_defence_config_figure(def_cfg, defender,
                                   family_name='Himalaya Maharaja',
                                   field='castle', checkmate=True)
        _add_defence_config_figure(def_cfg, defender,
                                   family_name='Wall',
                                   field='military')
        if attacker_prelude:
            atk_cfg.prelude_spell_name = 'Copy Figure'
            atk_cfg.prelude_spell_data = {}
        db.session.commit()
        return attacker, defender, land, atk_cfg, def_cfg

    def test_hidden_target_scope_and_pending_selection(self, app, db):
        with app.app_context():
            attacker, defender, land, _a, _d = self._setup(app, db)
            client, headers, game = _start_battle(app, attacker, land)
            atk_player = _game_player(game, attacker)
            def_player = _game_player(game, defender)

            pending = ActiveSpell.query.filter_by(
                game_id=game.id, player_id=atk_player.id,
                spell_name='Copy Figure').first()
            assert pending is not None
            data = pending.effect_data or {}
            assert data.get('prelude_pending_target') is True
            assert data.get('target_scope') == 'opponent_hidden'

            valid_ids = set(data.get('valid_target_ids') or [])
            def_figs = Figure.query.filter_by(
                game_id=game.id, player_id=def_player.id).all()
            by_family = {f.family_name: f for f in def_figs}

            # Village, military, and castle figures are all copyable —
            # including the checkmate Maharaja.
            assert by_family['Small Yack Farm'].id in valid_ids
            assert by_family['Gorkha Warriors'].id in valid_ids
            assert by_family['Himalaya Maharaja'].id in valid_ids
            assert by_family['Himalaya King'].id in valid_ids
            # cannot_be_targeted (Wall) is excluded.
            assert by_family['Wall'].id not in valid_ids

    def test_copy_creates_runtime_clone_without_checkmate_or_economy(self, app, db):
        with app.app_context():
            attacker, defender, land, _a, _d = self._setup(app, db)
            client, headers, game = _start_battle(app, attacker, land)
            atk_player = _game_player(game, attacker)
            def_player = _game_player(game, defender)

            pending = ActiveSpell.query.filter_by(
                game_id=game.id, player_id=atk_player.id,
                spell_name='Copy Figure').first()
            maharaja = Figure.query.filter_by(
                game_id=game.id, player_id=def_player.id,
                family_name='Himalaya Maharaja').first()

            resp = client.post('/kingdom/conquer/resolve_prelude_target', json={
                'game_id': game.id,
                'spell_id': pending.id,
                'target_figure_id': maharaja.id,
            }, headers=headers)
            assert resp.status_code == 200, resp.get_json()

            db.session.refresh(pending)
            data = pending.effect_data or {}
            assert data.get('prelude_status') == 'executed'
            assert data.get('source_figure_id') == maharaja.id
            copied = db.session.get(Figure, data.get('copied_figure_id'))
            assert copied is not None
            assert copied.player_id == atk_player.id
            assert copied.family_name == 'Himalaya Maharaja'
            assert copied.field == 'castle'
            # Copies are never checkmate, never map to a config figure, and
            # are exempt from the resource economy.
            assert copied.checkmate is False
            assert copied.source_config_figure_id is None
            assert (copied.requires or {}) == {}
            assert (copied.produces or {}) == {}
            # Card composition is cloned so base power matches the source.
            src_cards = CardToFigure.query.filter_by(figure_id=maharaja.id).count()
            cloned_cards = CardToFigure.query.filter_by(figure_id=copied.id).count()
            assert cloned_cards == src_cards
            assert data.get('spell_icon') == 'copy.png'
            # Clone marker persists and serializes for the client aura.
            assert copied.is_clone is True
            assert copied.serialize().get('is_clone') is True
            assert maharaja.is_clone is False

    def test_defender_copy_auto_targets_random_valid_figure(
        self, app, db, monkeypatch,
    ):
        with app.app_context():
            attacker, defender, land, atk_cfg, def_cfg = self._setup(
                app, db, attacker_prelude=False)
            def_cfg.prelude_spell_name = 'Copy Figure'
            def_cfg.prelude_spell_data = {}
            db.session.commit()

            # Force the random chooser to take the last valid target. The
            # route must honor a valid random result rather than ranking by
            # hidden base power.
            import game_service.conquer_counter_spells as counter_rules
            chosen = {}

            def choose_last(candidates):
                chosen['figure_id'] = candidates[-1].id
                return candidates[-1]

            monkeypatch.setattr(
                counter_rules.secrets,
                'choice',
                choose_last,
            )

            client, headers, game = _start_battle(app, attacker, land)
            atk_player = _game_player(game, attacker)
            def_player = _game_player(game, defender)

            spell = ActiveSpell.query.filter_by(
                game_id=game.id, player_id=def_player.id,
                spell_name='Copy Figure').first()
            assert spell is not None
            data = spell.effect_data or {}
            assert data.get('prelude_status') == 'executed'

            assert data.get('source_figure_id') == chosen['figure_id']

            copied = db.session.get(Figure, data.get('copied_figure_id'))
            assert copied is not None
            assert copied.player_id == def_player.id
            assert copied.checkmate is False


# ── Landslide ────────────────────────────────────────────────────────────────

class TestLandslide:
    def test_landslide_inverts_land_bonus_once(self, app, db):
        with app.app_context():
            from routes.games import _effective_land_bonus_value
            attacker = _make_user(db, username='ls_atk')
            defender = _make_user(db, username='ls_def')
            land = _make_land(db, tier=1, owner_user_id=defender.id)
            atk_cfg = _make_conquer_config(db, attacker, land)
            _make_defence_config(db, defender, land)
            atk_cfg.prelude_spell_name = 'Landslide'
            atk_cfg.prelude_spell_data = {}
            db.session.commit()

            client, headers, game = _start_battle(app, attacker, land)
            modifiers = game.battle_modifier or []
            assert any(m.get('type') == 'Landslide' for m in modifiers)

            assert _effective_land_bonus_value(game, 3) == -3

            # Duplicate Landslide never inverts back to positive and the
            # land record itself is untouched.
            game.battle_modifier = modifiers + [{'type': 'Landslide'}]
            db.session.commit()
            assert _effective_land_bonus_value(game, 3) == -3
            assert db.session.get(Land, land.id).suit_bonus_value == 3

    def test_landslide_flips_matching_defender_battle_figure_power(self, app, db):
        """The opponent's land-suit battle figure must LOSE the bonus.

        End-to-end: attacker casts Landslide; the defender's battle figure
        matches the land suit (Hearts, +3). Its contribution to the
        authoritative total must swing by 2×bonus versus no Landslide.
        """
        with app.app_context():
            from routes.games import _compute_server_total_diff
            attacker = _make_user(db, username='ls3_atk')
            defender = _make_user(db, username='ls3_def')
            land = _make_land(db, tier=1, owner_user_id=defender.id)  # Hearts +3
            atk_cfg = _make_conquer_config(db, attacker, land)
            def_cfg = _make_defence_config(db, defender, land)
            # Defender battle figure matching the land suit.
            hearts_king = _add_defence_config_figure(
                def_cfg, defender, family_name='Djungle King',
                suit='Hearts', color='offensive', field='castle',
                card_rank='K', card_value=4)
            def_cfg.battle_figure_id = hearts_king.id
            atk_cfg.prelude_spell_name = 'Landslide'
            atk_cfg.prelude_spell_data = {}
            db.session.commit()

            client, headers, game = _start_battle(app, attacker, land)
            atk_player = _game_player(game, attacker)
            def_player = _game_player(game, defender)

            atk_fig = Figure.query.filter_by(
                game_id=game.id, player_id=atk_player.id).first()
            def_fig = Figure.query.filter_by(
                game_id=game.id, player_id=def_player.id,
                family_name='Djungle King').first()
            assert def_fig is not None and def_fig.suit == 'Hearts'

            game.advancing_figure_id = atk_fig.id
            game.advancing_player_id = atk_player.id
            game.defending_figure_id = def_fig.id
            db.session.commit()

            with_landslide, breakdown = _compute_server_total_diff(
                game, return_breakdown=True)
            assert breakdown['land_suit_bonus'] == ('Hearts', -3)

            # Remove the modifier: same battle, normal +3 land bonus.
            game.battle_modifier = [
                m for m in (game.battle_modifier or [])
                if m.get('type') != 'Landslide'
            ]
            db.session.commit()
            without_landslide, breakdown2 = _compute_server_total_diff(
                game, return_breakdown=True)
            assert breakdown2['land_suit_bonus'] == ('Hearts', 3)
            # Defender flips from +3 to -3 ⇒ the invader-positive total
            # improves by exactly 2 × bonus.
            assert with_landslide - without_landslide == 6

    def test_no_landslide_keeps_positive_bonus(self, app, db):
        with app.app_context():
            from routes.games import _effective_land_bonus_value
            attacker = _make_user(db, username='ls2_atk')
            defender = _make_user(db, username='ls2_def')
            land = _make_land(db, tier=1, owner_user_id=defender.id)
            _make_conquer_config(db, attacker, land)
            _make_defence_config(db, defender, land)

            client, headers, game = _start_battle(app, attacker, land)
            assert _effective_land_bonus_value(game, 3) == 3


# ── Draw 4 MainCards ─────────────────────────────────────────────────────────

class TestDraw4MainCards:
    def test_draw_4_draws_and_converts_four(self, app, db):
        with app.app_context():
            attacker = _make_user(db, username='d4_atk')
            defender = _make_user(db, username='d4_def')
            land = _make_land(db, tier=1, owner_user_id=defender.id)
            atk_cfg = _make_conquer_config(db, attacker, land)
            _make_defence_config(db, defender, land)
            atk_cfg.prelude_spell_name = 'Draw 4 MainCards'
            atk_cfg.prelude_spell_data = {}
            db.session.commit()

            client, headers, game = _start_battle(app, attacker, land)
            atk_player = _game_player(game, attacker)

            spell = ActiveSpell.query.filter_by(
                game_id=game.id, player_id=atk_player.id,
                spell_name='Draw 4 MainCards').first()
            assert spell is not None
            data = spell.effect_data or {}
            assert data.get('prelude_status') == 'executed'
            assert len(data.get('drawn_cards') or []) == 4

            # Conquer tactics-hand: drawn main cards auto-convert to tactics
            # (3 configured + 4 drawn).
            tactics = ConquerTactic.query.filter_by(
                game_id=game.id, player_id=atk_player.id).filter(
                ConquerTactic.status != 'spell_purged').count()
            assert tactics == 7

    def test_draw_2_unchanged(self, app, db):
        with app.app_context():
            attacker = _make_user(db, username='d2_atk')
            defender = _make_user(db, username='d2_def')
            land = _make_land(db, tier=1, owner_user_id=defender.id)
            atk_cfg = _make_conquer_config(db, attacker, land)
            _make_defence_config(db, defender, land)
            atk_cfg.prelude_spell_name = 'Draw 2 MainCards'
            atk_cfg.prelude_spell_data = {}
            db.session.commit()

            client, headers, game = _start_battle(app, attacker, land)
            atk_player = _game_player(game, attacker)
            spell = ActiveSpell.query.filter_by(
                game_id=game.id, player_id=atk_player.id,
                spell_name='Draw 2 MainCards').first()
            assert spell is not None
            assert len((spell.effect_data or {}).get('drawn_cards') or []) == 2


# ── All Seeing Eye gamble preview ────────────────────────────────────────────

class TestGamblePreview:
    def _setup_battle_round(self, app, db, *, with_eye=True):
        attacker = _make_user(db, username='gp_atk')
        defender = _make_user(db, username='gp_def')
        land = _make_land(db, tier=1, owner_user_id=defender.id)
        atk_cfg = _make_conquer_config(db, attacker, land)
        _make_defence_config(db, defender, land)
        if with_eye:
            atk_cfg.prelude_spell_name = 'All Seeing Eye'
            atk_cfg.prelude_spell_data = {}
        db.session.commit()

        client, headers, game = _start_battle(app, attacker, land)
        atk_player = _game_player(game, attacker)

        # Fast-forward into an active battle round on the attacker's turn.
        game.battle_confirmed = True
        game.battle_round = 0
        game.battle_turn_player_id = atk_player.id
        db.session.commit()

        tactics = ConquerTactic.query.filter_by(
            game_id=game.id, player_id=atk_player.id,
            status='available').order_by(ConquerTactic.id).all()
        assert len(tactics) >= 2
        return client, headers, game, atk_player, tactics

    def test_preview_requires_all_seeing_eye(self, app, db):
        with app.app_context():
            client, headers, game, atk_player, tactics = \
                self._setup_battle_round(app, db, with_eye=False)
            resp = client.post('/games/conquer_gamble_preview', json={
                'game_id': game.id, 'player_id': atk_player.id,
                'tactic_id': tactics[0].id,
            }, headers=headers)
            assert resp.status_code == 403
            assert resp.get_json().get('reason') == 'no_all_seeing_eye'

    def test_preview_is_per_round_same_for_every_tactic(self, app, db):
        with app.app_context():
            client, headers, game, atk_player, tactics = \
                self._setup_battle_round(app, db)

            # Preview one tactic.
            resp = client.post('/games/conquer_gamble_preview', json={
                'game_id': game.id, 'player_id': atk_player.id,
                'tactic_id': tactics[0].id,
            }, headers=headers)
            assert resp.status_code == 200, resp.get_json()
            specs = resp.get_json()['preview']['specs']
            assert len(specs) == 2

            # A DIFFERENT tactic returns the SAME forecast (per round, not
            # per tactic) — no 'preview_used' rejection.
            resp = client.post('/games/conquer_gamble_preview', json={
                'game_id': game.id, 'player_id': atk_player.id,
                'tactic_id': tactics[1].id,
            }, headers=headers)
            assert resp.status_code == 200, resp.get_json()
            assert resp.get_json()['preview']['specs'] == specs

            # Preview works with no tactic id at all.
            resp = client.post('/games/conquer_gamble_preview', json={
                'game_id': game.id, 'player_id': atk_player.id,
            }, headers=headers)
            assert resp.status_code == 200
            assert resp.get_json()['preview']['specs'] == specs

            # Gambling ANY tactic yields exactly those pinned cards.
            resp = client.post('/games/gamble_conquer_tactic', json={
                'game_id': game.id, 'player_id': atk_player.id,
                'tactic_id': tactics[1].id,
            }, headers=headers)
            assert resp.status_code == 200, resp.get_json()
            new_tactics = resp.get_json()['new_tactics']
            assert [(t['rank'], t['suit']) for t in new_tactics] == \
                [(s['rank'], s['suit']) for s in specs]

            # The pinned preview is consumed.
            game = db.session.get(Game, game.id)
            assert not (game.battle_gamble_previews or {})

    def test_preview_private_to_owner(self, app, db):
        with app.app_context():
            from routes.serialization import serialize_game_for_viewer
            client, headers, game, atk_player, tactics = \
                self._setup_battle_round(app, db)
            resp = client.post('/games/conquer_gamble_preview', json={
                'game_id': game.id, 'player_id': atk_player.id,
                'tactic_id': tactics[0].id,
            }, headers=headers)
            assert resp.status_code == 200

            game = db.session.get(Game, game.id)
            def_player = next(p for p in game.players if p.id != atk_player.id)
            attacker_user_id = atk_player.user_id
            defender_user_id = def_player.user_id

            own_view = serialize_game_for_viewer(game, attacker_user_id)
            assert str(atk_player.id) in own_view['battle_gamble_previews']

            opp_view = serialize_game_for_viewer(game, defender_user_id)
            assert opp_view['battle_gamble_previews'] == {}

    def test_previews_cleared_with_battle_state(self, app, db):
        with app.app_context():
            from routes.games import _clear_battle_state
            client, headers, game, atk_player, tactics = \
                self._setup_battle_round(app, db)
            resp = client.post('/games/conquer_gamble_preview', json={
                'game_id': game.id, 'player_id': atk_player.id,
                'tactic_id': tactics[0].id,
            }, headers=headers)
            assert resp.status_code == 200

            game = db.session.get(Game, game.id)
            assert game.battle_gamble_previews
            _clear_battle_state(game)
            assert game.battle_gamble_previews is None


# ── All Seeing Eye reveals opponent tactics in battle state ──────────────────

class TestAllSeeingEyeRevealsTactics:
    def _setup(self, app, db, *, with_eye):
        attacker = _make_user(db, username='ase_atk')
        defender = _make_user(db, username='ase_def')
        land = _make_land(db, tier=1, owner_user_id=defender.id)
        atk_cfg = _make_conquer_config(db, attacker, land)
        _make_defence_config(db, defender, land)
        if with_eye:
            atk_cfg.prelude_spell_name = 'All Seeing Eye'
            atk_cfg.prelude_spell_data = {}
        db.session.commit()
        client, headers, game = _start_battle(app, attacker, land)
        atk_player = _game_player(game, attacker)
        game.battle_confirmed = True
        game.battle_round = 0
        game.battle_turn_player_id = atk_player.id
        db.session.commit()
        return client, headers, game, atk_player

    def test_opponent_tactics_revealed_with_eye(self, app, db):
        with app.app_context():
            client, headers, game, atk_player = self._setup(app, db, with_eye=True)
            resp = client.get('/games/get_battle_state', query_string={
                'game_id': game.id, 'player_id': atk_player.id,
            }, headers=headers)
            assert resp.status_code == 200
            opp = resp.get_json()['opponent_tactics']
            assert opp, 'opponent should have tactics'
            # Every unplayed opponent tactic carries its real rank/suit.
            assert all(t.get('rank') and t.get('suit') for t in opp)

    def test_opponent_tactics_hidden_without_eye(self, app, db):
        with app.app_context():
            client, headers, game, atk_player = self._setup(app, db, with_eye=False)
            resp = client.get('/games/get_battle_state', query_string={
                'game_id': game.id, 'player_id': atk_player.id,
            }, headers=headers)
            assert resp.status_code == 200
            opp = resp.get_json()['opponent_tactics']
            assert opp
            # Unplayed opponent tactics are redacted (count-only stubs).
            unplayed = [t for t in opp if t.get('played_round') is None]
            assert unplayed
            assert all(t.get('rank') is None for t in unplayed)


# ── figure.is_clone migration ────────────────────────────────────────────────

class TestFigureIsCloneMigration:
    def test_migration_adds_column(self, app, db):
        with app.app_context():
            from migration_runner import _m_figure_is_clone_column
            # Idempotent: safe to run even though create_all already made it.
            _m_figure_is_clone_column()
            from sqlalchemy import inspect as sa_inspect
            cols = {c['name'] for c in sa_inspect(db.engine).get_columns('figure')}
            assert 'is_clone' in cols


# ── Fill up to 10 migration ──────────────────────────────────────────────────

class TestFillUpTo10Migration:
    def test_migration_clears_configs_and_unlocks_cards(self, app, db):
        with app.app_context():
            user = _make_user(db, username='fill_user')
            land = _make_land(db)
            cfg = _make_conquer_config(db, user, land)

            card = CollectionCard(user_id=user.id, suit='Hearts', rank='10',
                                  value=10, locked=True,
                                  lock_type='conquer_prelude',
                                  lock_ref_id=cfg.id)
            db.session.add(card)
            db.session.flush()
            cfg.prelude_spell_name = 'Fill up to 10'
            cfg.prelude_spell_data = {}
            cfg.prelude_spell_card_ids = [card.id]
            db.session.commit()

            from migration_runner import _m_clear_fill_up_to_10_preludes
            _m_clear_fill_up_to_10_preludes()

            db.session.refresh(cfg)
            db.session.refresh(card)
            assert cfg.prelude_spell_name is None
            assert cfg.prelude_spell_card_ids is None
            assert card.locked is False
            assert card.lock_type is None
