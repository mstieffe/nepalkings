# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for Phase 13 — land conquer battle flow."""
import pytest
from unittest.mock import patch
from datetime import datetime, timezone, timedelta

from models import (db, User, Land, LandConfig, LandConfigFigure,
                    LandConfigBattleMove, CollectionCard, Game, Player,
                    Figure, BattleMove, MainCard, LandAttackLog, ActiveSpell)
from kingdom_service import seed_kingdom_map
import server_settings as config


_LAND_COORD_COUNTER = 0


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_user(db_session, username='attacker', gold=1000, is_ai=False):
    from werkzeug.security import generate_password_hash
    u = User(username=username, password_hash=generate_password_hash('pw'),
             gold=gold, is_ai=is_ai)
    db_session.session.add(u)
    db_session.session.commit()
    return u


def _make_ai_user(db_session):
    return _make_user(db_session, username=config.AI_USERNAMES[0],
                      gold=config.AI_INITIAL_GOLD, is_ai=True)


def _make_land(db_session, tier=1, owner_user_id=None, ai_template_index=0,
               col=None, row=None):
    global _LAND_COORD_COUNTER
    if col is None:
        col = 1000 + _LAND_COORD_COUNTER
    if row is None:
        row = 1000 + _LAND_COORD_COUNTER
    _LAND_COORD_COUNTER += 1

    land = Land(
        col=col, row=row, tier=tier, gold_rate=5.0,
        suit_bonus_suit='Hearts', suit_bonus_value=3,
        owner_user_id=owner_user_id,
        ai_template_index=ai_template_index,
    )
    db_session.session.add(land)
    db_session.session.commit()
    return land


def _make_conquer_config(db_session, user, land):
    """Build a minimal conquer config: 1 figure + 3 battle moves."""
    cfg = LandConfig(user_id=user.id, config_type='conquer', land_id=land.id)
    db_session.session.add(cfg)
    db_session.session.flush()

    # Create collection cards (to be locked by the config)
    cards = []
    card_data = [
        ('J', 'Diamonds', 1),
        ('8', 'Diamonds', 8),
        ('7', 'Spades', 7),
        ('9', 'Clubs', 9),
        ('10', 'Clubs', 10),
    ]
    for rank, suit, value in card_data:
        cc = CollectionCard(user_id=user.id, suit=suit, rank=rank,
                            value=value, locked=True, lock_type='conquer_figure')
        db_session.session.add(cc)
        cards.append(cc)
    db_session.session.flush()

    fig = LandConfigFigure(
        config_id=cfg.id,
        family_name='Small Rice Farm', name='Small Rice Farm',
        suit='Diamonds', color='offensive', field='village',
        card_ids=[cards[0].id, cards[1].id],
        card_roles=['key', 'number'],
        produces={'food_red': 8}, requires={},
    )
    db_session.session.add(fig)
    db_session.session.flush()

    for i, (rank, suit, value) in enumerate([('7', 'Spades', 7),
                                              ('9', 'Clubs', 9),
                                              ('10', 'Clubs', 10)]):
        move = LandConfigBattleMove(
            config_id=cfg.id,
            family_name='Dagger', card_id=cards[2 + i].id,
            suit=suit, rank=rank, value=value, round_index=i,
        )
        db_session.session.add(move)

    db_session.session.commit()
    return cfg


def _make_defence_config(db_session, user, land):
    """Build a minimal defence config for player-owned land."""
    cfg = LandConfig(user_id=user.id, config_type='defence', land_id=land.id)
    db_session.session.add(cfg)
    db_session.session.flush()

    cards = []
    card_data = [
        ('K', 'Spades', 4),
        ('8', 'Spades', 8),
        ('10', 'Hearts', 10),
        ('7', 'Hearts', 7),
    ]
    for rank, suit, value in card_data:
        cc = CollectionCard(user_id=user.id, suit=suit, rank=rank,
                            value=value, locked=True, lock_type='defence_figure')
        db_session.session.add(cc)
        cards.append(cc)
    db_session.session.flush()

    fig = LandConfigFigure(
        config_id=cfg.id,
        family_name='Himalaya King', name='Himalaya King',
        suit='Spades', color='defensive', field='castle',
        card_ids=[cards[0].id],
        card_roles=['key'],
        produces={'villager_black': 2, 'warrior_black': 1}, requires={},
    )
    db_session.session.add(fig)
    db_session.session.flush()

    cfg.battle_figure_id = fig.id

    move = LandConfigBattleMove(
        config_id=cfg.id,
        family_name='Dagger', card_id=cards[1].id,
        suit='Spades', rank='8', value=8, round_index=0,
    )
    db_session.session.add(move)

    db_session.session.commit()
    land.defence_config_id = cfg.id
    db_session.session.commit()
    return cfg


def _add_conquer_config_figure(db_session, cfg, user, *,
                               family_name='Village Guard',
                               name='Village Guard',
                               suit='Clubs',
                               color='offensive',
                               field='village',
                               checkmate=False):
    """Append one extra conquer config figure for targeted-spell tests."""
    cc = CollectionCard(
        user_id=user.id,
        suit=suit,
        rank='K',
        value=4,
        locked=True,
        lock_type='conquer_figure',
    )
    db_session.session.add(cc)
    db_session.session.flush()

    fig = LandConfigFigure(
        config_id=cfg.id,
        family_name=family_name,
        name=name,
        suit=suit,
        color=color,
        field=field,
        card_ids=[cc.id],
        card_roles=['key'],
        produces={},
        requires={},
        checkmate=checkmate,
    )
    db_session.session.add(fig)
    db_session.session.commit()
    return fig


def _auth_headers(app, user):
    from routes.auth import generate_token
    token = generate_token(user.id)
    return {'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'}


def _scripted_ai_template(*, prelude_spell_name=None, counter_spell_name=None):
    """Small deterministic AI template for spell/move interaction tests."""
    return {
        'ai_name': 'Scripted Test Defenders',
        'figures': [
            {
                'family_name': 'Small Rice Farm',
                'name': 'Small Rice Farm',
                'suit': 'Hearts',
                'color': 'defensive',
                'field': 'village',
                'card_roles': ['key', 'number'],
                'cards': [
                    {'rank': 'J', 'suit': 'Hearts', 'role': 'key', 'card_type': 'main'},
                    {'rank': '8', 'suit': 'Hearts', 'role': 'number', 'card_type': 'main'},
                ],
                'produces': {'food_red': 8},
                'requires': {},
            },
            {
                'family_name': 'Himalaya King',
                'name': 'Himalaya King',
                'suit': 'Hearts',
                'color': 'defensive',
                'field': 'castle',
                'card_roles': ['key'],
                'cards': [
                    {'rank': 'K', 'suit': 'Hearts', 'role': 'key', 'card_type': 'main'},
                ],
                'produces': {'villager_red': 2},
                'requires': {},
            },
        ],
        'battle_moves': [
            {'family_name': 'Dagger', 'rank': '7', 'suit': 'Hearts', 'value': 7, 'round_index': 0, 'card_type': 'main'},
            {'family_name': 'Dagger', 'rank': '8', 'suit': 'Hearts', 'value': 8, 'round_index': 1, 'card_type': 'main'},
            {'family_name': 'Dagger', 'rank': '9', 'suit': 'Hearts', 'value': 9, 'round_index': 2, 'card_type': 'main'},
        ],
        'battle_figure_index': 0,
        'battle_modifier': None,
        'spell': None,
        'prelude_spell_name': prelude_spell_name,
        'prelude_spell_data': {} if prelude_spell_name else None,
        'counter_spell_name': counter_spell_name,
        'counter_spell_data': {} if counter_spell_name else None,
        'auto_gamble': False,
        'auto_gamble_threshold': 10,
    }


# ═════════════════════════════════════════════════════════════════════════════
#  Tests
# ═════════════════════════════════════════════════════════════════════════════


class TestConquerStartBattle:
    """Tests for POST /kingdom/conquer/start_battle."""

    def test_start_battle_ai_land(self, app, db):
        """Start a conquer battle against an unowned (AI) land."""
        with app.app_context():
            user = _make_user(db)
            land = _make_land(db, tier=1)
            _make_conquer_config(db, user, land)

            client = app.test_client()
            headers = _auth_headers(app, user)

            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=headers)
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['success'] is True
            assert 'game_id' in data
            assert data['game']['mode'] == 'conquer'
            assert data['game']['land_id'] == land.id

            # Verify game record
            game = db.session.get(Game, data['game_id'])
            assert game.mode == 'conquer'
            assert game.state == 'open'
            assert game.ceasefire_active is False
            assert game.land_id == land.id

            # Verify players
            players = Player.query.filter_by(game_id=game.id).all()
            assert len(players) == 2

            # Verify attacker is invader
            assert game.invader_player_id is not None
            atk_player = db.session.get(Player, game.invader_player_id)
            assert atk_player.user_id == user.id

    def test_start_battle_creates_figures(self, app, db):
        """Figures from conquer config and AI template are created in the game."""
        with app.app_context():
            user = _make_user(db)
            land = _make_land(db, tier=1)
            _make_conquer_config(db, user, land)

            client = app.test_client()
            headers = _auth_headers(app, user)

            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=headers)
            data = resp.get_json()
            game_id = data['game_id']

            figures = Figure.query.filter_by(game_id=game_id).all()
            # 1 attacker figure + AI template tier 1 figures
            assert len(figures) >= 2  # at least attacker + defender

            # Check attacker figure
            atk_figs = [f for f in figures if f.family_name == 'Small Rice Farm'
                        and f.suit == 'Diamonds']
            assert len(atk_figs) == 1

    def test_start_battle_creates_battle_moves(self, app, db):
        """Battle moves from both configs are created."""
        with app.app_context():
            user = _make_user(db)
            land = _make_land(db, tier=1)
            _make_conquer_config(db, user, land)

            client = app.test_client()
            headers = _auth_headers(app, user)

            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=headers)
            data = resp.get_json()
            game_id = data['game_id']

            moves = BattleMove.query.filter_by(game_id=game_id).all()
            # 3 attacker + 3 defender (from AI template tier 1)
            assert len(moves) == 6

    @pytest.mark.parametrize('spell_name, expected_attacker_moves', [
        ('Forced Deal', 1),
        ('Dump Cards', 0),
    ])
    def test_move_mutating_ai_prelude_replenishes_defender_only(
        self, app, db, spell_name, expected_attacker_moves,
    ):
        """AI prelude disruption stays intact, but defender can rebuild moves."""
        with app.app_context():
            user = _make_user(db, username=f'atk_prelude_{spell_name.replace(" ", "_")}')
            land = _make_land(db, tier=1)
            _make_conquer_config(db, user, land)
            template = _scripted_ai_template(prelude_spell_name=spell_name)

            client = app.test_client()
            headers = _auth_headers(app, user)
            with patch('routes.kingdom.get_ai_defence_template_for_land', return_value=template), \
                    patch('routes.games.get_ai_defence_template_for_land', return_value=template):
                resp = client.post('/kingdom/conquer/start_battle',
                                   json={'land_id': land.id}, headers=headers)
            assert resp.status_code == 200
            game = db.session.get(Game, resp.get_json()['game_id'])
            atk_player = db.session.get(Player, game.invader_player_id)
            def_player = [p for p in game.players if p.id != atk_player.id][0]

            spell = ActiveSpell.query.filter_by(
                game_id=game.id,
                player_id=def_player.id,
                spell_name=spell_name,
            ).first()
            assert spell is not None
            assert (spell.effect_data or {}).get('prelude_status') == 'executed'

            defender_moves = BattleMove.query.filter_by(
                game_id=game.id,
                player_id=def_player.id,
            ).all()
            attacker_moves = BattleMove.query.filter_by(
                game_id=game.id,
                player_id=atk_player.id,
            ).all()
            assert len(defender_moves) == 3
            assert len(attacker_moves) == expected_attacker_moves

    def test_start_battle_defers_ai_defender_for_counter_spell(self, app, db):
        """AI templates use counter spells before the invader selects a defender."""
        with app.app_context():
            user = _make_user(db)
            land = _make_land(db, tier=1)
            from ai.defence.generator import get_ai_defence_template_for_land
            expected_prelude = None
            for seed in range(500):
                land.ai_template_index = seed
                template = get_ai_defence_template_for_land(land)
                if (
                    template.get('prelude_spell_name')
                    and template.get('counter_spell_name')
                ):
                    expected_prelude = template['prelude_spell_name']
                    break
            assert expected_prelude is not None
            db.session.commit()
            _make_conquer_config(db, user, land)

            client = app.test_client()
            headers = _auth_headers(app, user)

            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=headers)
            data = resp.get_json()

            game = db.session.get(Game, data['game_id'])
            assert game.defending_figure_id is None
            ai_player = [p for p in game.players if p.id != game.invader_player_id][0]
            assert ActiveSpell.query.filter_by(
                game_id=game.id,
                player_id=ai_player.id,
                spell_name=expected_prelude,
            ).first() is not None

    def test_start_battle_cooldown(self, app, db):
        """Cannot start another battle during cooldown."""
        with app.app_context():
            user = _make_user(db)
            user.last_conquer_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db.session.commit()

            land = _make_land(db, tier=1)
            _make_conquer_config(db, user, land)

            client = app.test_client()
            headers = _auth_headers(app, user)

            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=headers)
            assert resp.status_code == 400
            assert 'cooldown' in resp.get_json()['message'].lower()

    def test_start_battle_cooldown_expired(self, app, db):
        """Can start battle after cooldown expires."""
        with app.app_context():
            user = _make_user(db)
            past = (datetime.now(timezone.utc).replace(tzinfo=None)
                    - timedelta(seconds=config.CONQUER_COOLDOWN_SECONDS + 1))
            user.last_conquer_at = past
            db.session.commit()

            land = _make_land(db, tier=1)
            _make_conquer_config(db, user, land)

            client = app.test_client()
            headers = _auth_headers(app, user)

            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=headers)
            assert resp.status_code == 200
            assert resp.get_json()['success'] is True

    def test_start_battle_own_land_rejected(self, app, db):
        """Cannot conquer own land."""
        with app.app_context():
            user = _make_user(db)
            land = _make_land(db, owner_user_id=user.id)
            _make_conquer_config(db, user, land)

            client = app.test_client()
            headers = _auth_headers(app, user)

            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=headers)
            assert resp.status_code == 400
            assert 'own land' in resp.get_json()['message'].lower()

    def test_start_battle_no_config(self, app, db):
        """Rejected if no conquer config exists."""
        with app.app_context():
            user = _make_user(db)
            land = _make_land(db, tier=1)

            client = app.test_client()
            headers = _auth_headers(app, user)

            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=headers)
            assert resp.status_code == 400
            assert 'no conquer config' in resp.get_json()['message'].lower()

    def test_start_battle_no_figures(self, app, db):
        """Rejected if conquer config has no figures."""
        with app.app_context():
            user = _make_user(db)
            land = _make_land(db, tier=1)

            # Create empty config with moves but no figures
            cfg = LandConfig(user_id=user.id, config_type='conquer',
                             land_id=land.id)
            db.session.add(cfg)
            db.session.flush()

            cc = CollectionCard(user_id=user.id, suit='Spades', rank='7',
                                value=7, locked=True)
            db.session.add(cc)
            db.session.flush()

            move = LandConfigBattleMove(
                config_id=cfg.id, family_name='Dagger', card_id=cc.id,
                suit='Spades', rank='7', value=7, round_index=0)
            db.session.add(move)
            db.session.commit()

            client = app.test_client()
            headers = _auth_headers(app, user)

            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=headers)
            assert resp.status_code == 400
            assert 'no figures' in resp.get_json()['message'].lower()

    def test_start_battle_sets_cooldown(self, app, db):
        """Starting a battle sets the user's cooldown timestamp."""
        with app.app_context():
            user = _make_user(db)
            assert user.last_conquer_at is None

            land = _make_land(db, tier=1)
            _make_conquer_config(db, user, land)

            client = app.test_client()
            headers = _auth_headers(app, user)

            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=headers)
            assert resp.status_code == 200

            db.session.refresh(user)
            assert user.last_conquer_at is not None

    def test_start_battle_player_owned_land(self, app, db):
        """Start a conquer battle against a player-owned land."""
        with app.app_context():
            attacker = _make_user(db, username='attacker')
            defender = _make_user(db, username='defender')

            land = _make_land(db, tier=1, owner_user_id=defender.id)
            _make_conquer_config(db, attacker, land)
            _make_defence_config(db, defender, land)

            client = app.test_client()
            headers = _auth_headers(app, attacker)

            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=headers)
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['success'] is True

            game = db.session.get(Game, data['game_id'])
            assert game.mode == 'conquer'
            assert game.defending_figure_id is not None

            # Verify defender figures created
            def_player = [p for p in game.players
                          if p.user_id == defender.id][0]
            def_figs = Figure.query.filter_by(
                game_id=game.id, player_id=def_player.id).all()
            assert len(def_figs) >= 1
            assert any(f.family_name == 'Himalaya King' for f in def_figs)

    def test_start_battle_player_owned_land_allows_invalid_counter_strategy(self, app, db):
        """Missing counter strategy starts battle and falls back to invader defender-pick flow."""
        with app.app_context():
            attacker = _make_user(db, username='attacker')
            defender = _make_user(db, username='defender')

            land = Land(
                col=99, row=99, tier=1, gold_rate=5.0,
                suit_bonus_suit='Hearts', suit_bonus_value=3,
                owner_user_id=defender.id,
                ai_template_index=0,
            )
            db.session.add(land)
            db.session.commit()
            _make_conquer_config(db, attacker, land)
            cfg = _make_defence_config(db, defender, land)
            cfg.battle_figure_id = None
            cfg.counter_spell_name = None
            cfg.auto_gamble = True
            db.session.commit()

            client = app.test_client()
            headers = _auth_headers(app, attacker)

            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=headers)
            assert resp.status_code == 200
            data = resp.get_json()
            assert data['success'] is True

            game = db.session.get(Game, data['game_id'])
            atk_player = db.session.get(Player, game.invader_player_id)
            assert game.defending_figure_id is None

            defender_spell_count = ActiveSpell.query.filter_by(
                game_id=game.id,
                player_id=[p for p in game.players if p.id != atk_player.id][0].id,
                is_active=True,
            ).count()
            assert defender_spell_count == 0

            atk_fig = Figure.query.filter_by(
                game_id=game.id,
                player_id=atk_player.id,
            ).first()
            adv_resp = client.post('/games/advance_figure', json={
                'game_id': game.id,
                'player_id': atk_player.id,
                'figure_id': atk_fig.id,
            }, headers=headers)
            assert adv_resp.status_code == 200

            db.session.refresh(game)
            assert game.turn_player_id == atk_player.id
            assert game.defending_figure_id is None

    def test_start_battle_player_owned_land_allows_invalid_battle_figure_reference(self, app, db):
        """Stale battle_figure_id falls back instead of rejecting battle start."""
        with app.app_context():
            attacker = _make_user(db, username='attacker_ref')
            defender = _make_user(db, username='defender_ref')

            land = _make_land(db, tier=1, owner_user_id=defender.id)
            _make_conquer_config(db, attacker, land)
            cfg = _make_defence_config(db, defender, land)

            other_land = _make_land(db, tier=1, owner_user_id=defender.id)
            other_cfg = _make_defence_config(db, defender, other_land)

            cfg.battle_figure_id = other_cfg.battle_figure_id
            cfg.counter_spell_name = None
            db.session.commit()

            client = app.test_client()
            headers = _auth_headers(app, attacker)

            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=headers)
            assert resp.status_code == 200

            game = db.session.get(Game, resp.get_json()['game_id'])
            assert game.defending_figure_id is None

    def test_start_battle_normalizes_legacy_numeric_rank_cards(self, app, db):
        """Legacy numeric rank data in config cards is normalized instead of crashing."""
        with app.app_context():
            attacker = _make_user(db, username='attacker_legacy_rank')
            defender = _make_user(db, username='defender_legacy_rank')

            land = _make_land(db, tier=1, owner_user_id=defender.id)
            _make_conquer_config(db, attacker, land)
            def_cfg = _make_defence_config(db, defender, land)

            def_cfg_fig = LandConfigFigure.query.filter_by(config_id=def_cfg.id).first()
            legacy_card = db.session.get(CollectionCard, def_cfg_fig.card_ids[0])
            legacy_card.rank = '4'
            legacy_card.value = 4

            def_cfg_move = LandConfigBattleMove.query.filter_by(config_id=def_cfg.id).first()
            def_cfg_move.rank = '4'
            def_cfg_move.value = 4
            db.session.commit()

            client = app.test_client()
            headers = _auth_headers(app, attacker)

            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=headers)
            assert resp.status_code == 200
            data = resp.get_json()

            game = db.session.get(Game, data['game_id'])
            def_player = [p for p in game.players if p.user_id == defender.id][0]

            created_main_cards = MainCard.query.filter_by(
                game_id=game.id,
                player_id=def_player.id,
            ).all()
            assert created_main_cards
            assert all(c.rank.value in {'7', '8', '9', '10', 'J', 'Q', 'K', 'A'}
                       for c in created_main_cards)

            defender_moves = BattleMove.query.filter_by(
                game_id=game.id,
                player_id=def_player.id,
            ).all()
            assert any(m.rank == 'K' and m.value == 4 for m in defender_moves)

    def test_start_battle_tier2_template(self, app, db):
        """Tier 2 template includes Call King move and auto_gamble."""
        with app.app_context():
            user = _make_user(db)
            land = _make_land(db, tier=2)
            from ai.defence.generator import get_ai_defence_template_for_land

            # Keep this test focused on template move creation. Some preludes
            # (Dump Cards / Forced Deal) intentionally recycle hand cards and
            # purge their BattleMove rows, which would invalidate this assert.
            move_mutating_preludes = {'Dump Cards', 'Forced Deal'}
            template = None
            for seed in range(500):
                land.ai_template_index = seed
                candidate = get_ai_defence_template_for_land(land)
                prelude = candidate.get('prelude_spell_name')
                has_call_king = any(
                    m.get('family_name') == 'Call King'
                    for m in candidate.get('battle_moves', [])
                )
                if has_call_king and prelude not in move_mutating_preludes:
                    template = candidate
                    break
            assert template is not None
            db.session.commit()

            _make_conquer_config(db, user, land)

            client = app.test_client()
            headers = _auth_headers(app, user)

            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=headers)
            data = resp.get_json()
            assert data['success'] is True

            game_id = data['game_id']
            moves = BattleMove.query.filter_by(game_id=game_id).all()
            # Verify there's a Call King move from the AI defender
            call_king_moves = [m for m in moves
                               if m.family_name == 'Call King']
            assert len(call_king_moves) == 1

    def test_start_battle_tier3_template(self, app, db):
        """Tier 3 template includes Call Military move."""
        with app.app_context():
            user = _make_user(db)
            land = _make_land(db, tier=3)
            from ai.defence.generator import get_ai_defence_template_for_land

            move_mutating_preludes = {'Dump Cards', 'Forced Deal'}
            template = None
            for seed in range(500):
                land.ai_template_index = seed
                candidate = get_ai_defence_template_for_land(land)
                prelude = candidate.get('prelude_spell_name')
                has_call_military = any(
                    m.get('family_name') == 'Call Military'
                    for m in candidate.get('battle_moves', [])
                )
                if has_call_military and prelude not in move_mutating_preludes:
                    template = candidate
                    break
            assert template is not None
            db.session.commit()

            _make_conquer_config(db, user, land)

            client = app.test_client()
            headers = _auth_headers(app, user)

            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=headers)
            data = resp.get_json()
            assert data['success'] is True

            game_id = data['game_id']
            moves = BattleMove.query.filter_by(game_id=game_id).all()
            call_mil = [m for m in moves if m.family_name == 'Call Military']
            assert len(call_mil) == 1

    def test_ai_template_uses_spells_and_forces_fortress_selection(self, app, db):
        """AI fortress defence should cast a counter, then force invader selection."""
        with app.app_context():
            user = _make_user(db, username='atk_ai_fortress')
            land = _make_land(db, tier=3)
            land.suit_bonus_suit = 'Spades'
            from ai.defence.generator import get_ai_defence_template_for_land
            fortress_families = {'Wooden Fortress', 'Stone Fortress'}
            # Skip Explosion preludes: they destroy the lone attacker figure
            # and break the rest of this test's flow.  Skip battle-modifier
            # preludes too because they constrain advance/select rules in ways
            # this test's minimal config can't satisfy.
            _BATTLE_MOD_PRELUDES = {'Peasant War', 'Civil War', 'Blitzkrieg'}
            template = None
            for seed in range(500):
                land.ai_template_index = seed
                candidate = get_ai_defence_template_for_land(land)
                has_fortress = any(
                    f['family_name'] in fortress_families
                    for f in candidate['figures']
                )
                prelude = candidate.get('prelude_spell_name')
                if (
                    has_fortress
                    and prelude
                    and prelude != 'Explosion'
                    and prelude not in _BATTLE_MOD_PRELUDES
                    and candidate.get('counter_spell_name')
                ):
                    template = candidate
                    break
            assert template is not None
            expected_prelude = template['prelude_spell_name']
            expected_counter = template['counter_spell_name']
            db.session.commit()
            _make_conquer_config(db, user, land)

            client = app.test_client()
            atk_headers = _auth_headers(app, user)
            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=atk_headers)
            assert resp.status_code == 200
            game = db.session.get(Game, resp.get_json()['game_id'])
            atk_player = db.session.get(Player, game.invader_player_id)
            def_player = [p for p in game.players if p.id != atk_player.id][0]
            ai_user = db.session.get(User, def_player.user_id)

            # Template counter spells defer defender selection until after the response.
            assert game.defending_figure_id is None
            prelude = ActiveSpell.query.filter_by(
                game_id=game.id,
                player_id=def_player.id,
                spell_name=expected_prelude,
            ).first()
            assert prelude is not None
            assert (prelude.effect_data or {}).get('prelude_status') == 'executed'

            atk_fig = Figure.query.filter_by(
                game_id=game.id,
                player_id=atk_player.id,
            ).first()
            adv_resp = client.post('/games/advance_figure', json={
                'game_id': game.id,
                'player_id': atk_player.id,
                'figure_id': atk_fig.id,
            }, headers=atk_headers)
            assert adv_resp.status_code == 200

            db.session.refresh(game)
            assert game.turn_player_id == def_player.id

            def_headers = _auth_headers(app, ai_user)
            counter_resp = client.post('/games/conquer_defender_counter_spell', json={
                'game_id': game.id,
                'player_id': def_player.id,
            }, headers=def_headers)
            assert counter_resp.status_code == 200
            assert counter_resp.get_json()['spell_name'] == expected_counter

            db.session.refresh(game)
            assert game.turn_player_id == atk_player.id
            fortress = Figure.query.filter_by(
                game_id=game.id,
                player_id=def_player.id,
                family_name='Stone Fortress',
            ).first()
            assert fortress is not None
            non_fortress = Figure.query.filter(
                Figure.game_id == game.id,
                Figure.player_id == def_player.id,
                Figure.id != fortress.id,
                Figure.checkmate.is_(False),
            ).first()
            assert non_fortress is not None

            blocked = client.post('/games/select_defender', json={
                'game_id': game.id,
                'player_id': atk_player.id,
                'figure_id': non_fortress.id,
            }, headers=atk_headers)
            assert blocked.status_code == 400
            assert blocked.get_json().get('reason') == 'must_be_attacked'

            selected = client.post('/games/select_defender', json={
                'game_id': game.id,
                'player_id': atk_player.id,
                'figure_id': fortress.id,
            }, headers=atk_headers)
            assert selected.status_code == 200
            db.session.refresh(game)
            assert game.defending_figure_id == fortress.id

    def test_cannot_attack_figure_cannot_counter_advance(self, app, db):
        """Server rejects counter-advance attempts by cannot_attack families."""
        with app.app_context():
            attacker = _make_user(db, username='atk_no_temple_counter')
            defender = _make_user(db, username='def_no_temple_counter')
            land = _make_land(db, tier=1, owner_user_id=defender.id)
            _make_conquer_config(db, attacker, land)
            def_cfg = _make_defence_config(db, defender, land)
            temple_cfg = LandConfigFigure.query.filter_by(config_id=def_cfg.id).first()
            temple_cfg.family_name = 'Himalaya Temple'
            temple_cfg.name = 'Himalaya Temple'
            temple_cfg.field = 'village'
            db.session.commit()

            client = app.test_client()
            atk_headers = _auth_headers(app, attacker)
            def_headers = _auth_headers(app, defender)
            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=atk_headers)
            assert resp.status_code == 200
            game = db.session.get(Game, resp.get_json()['game_id'])
            atk_player = db.session.get(Player, game.invader_player_id)
            def_player = [p for p in game.players if p.user_id == defender.id][0]
            atk_fig = Figure.query.filter_by(game_id=game.id, player_id=atk_player.id).first()
            temple = Figure.query.filter_by(
                game_id=game.id,
                player_id=def_player.id,
                family_name='Himalaya Temple',
            ).first()
            assert temple is not None

            game.defending_figure_id = None
            db.session.commit()
            adv_resp = client.post('/games/advance_figure', json={
                'game_id': game.id,
                'player_id': atk_player.id,
                'figure_id': atk_fig.id,
            }, headers=atk_headers)
            assert adv_resp.status_code == 200

            db.session.refresh(game)
            game.turn_player_id = def_player.id
            db.session.commit()
            counter_resp = client.post('/games/advance_figure', json={
                'game_id': game.id,
                'player_id': def_player.id,
                'figure_id': temple.id,
            }, headers=def_headers)
            assert counter_resp.status_code == 400
            assert 'cannot advance' in counter_resp.get_json().get('message', '').lower()

    def test_civil_war_rejects_non_village_counter_advance(self, app, db):
        """Runtime counter-advance rejects non-village figures under Civil War."""
        with app.app_context():
            attacker = _make_user(db, username='atk_civil_counter')
            defender = _make_user(db, username='def_civil_counter')
            land = _make_land(db, tier=1, owner_user_id=defender.id)
            _make_conquer_config(db, attacker, land)
            _make_defence_config(db, defender, land)

            client = app.test_client()
            atk_headers = _auth_headers(app, attacker)
            def_headers = _auth_headers(app, defender)
            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=atk_headers)
            assert resp.status_code == 200
            game = db.session.get(Game, resp.get_json()['game_id'])
            atk_player = db.session.get(Player, game.invader_player_id)
            def_player = [p for p in game.players if p.user_id == defender.id][0]
            atk_fig = Figure.query.filter_by(game_id=game.id, player_id=atk_player.id).first()
            castle = Figure.query.filter_by(game_id=game.id, player_id=def_player.id).first()

            game.battle_modifier = [{'type': 'Civil War'}]
            game.defending_figure_id = None
            db.session.commit()
            adv_resp = client.post('/games/advance_figure', json={
                'game_id': game.id,
                'player_id': atk_player.id,
                'figure_id': atk_fig.id,
            }, headers=atk_headers)
            assert adv_resp.status_code == 200

            db.session.refresh(game)
            game.turn_player_id = def_player.id
            db.session.commit()
            counter_resp = client.post('/games/advance_figure', json={
                'game_id': game.id,
                'player_id': def_player.id,
                'figure_id': castle.id,
            }, headers=def_headers)
            assert counter_resp.status_code == 400
            assert 'village' in counter_resp.get_json().get('message', '').lower()

    def test_civil_war_select_defender_rejects_non_village(self, app, db):
        """Manual defender selection also honors Civil War village-only rules."""
        with app.app_context():
            attacker = _make_user(db, username='atk_civil_select')
            defender = _make_user(db, username='def_civil_select')
            land = _make_land(db, tier=1, owner_user_id=defender.id)
            _make_conquer_config(db, attacker, land)
            _make_defence_config(db, defender, land)

            client = app.test_client()
            atk_headers = _auth_headers(app, attacker)
            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=atk_headers)
            assert resp.status_code == 200
            game = db.session.get(Game, resp.get_json()['game_id'])
            atk_player = db.session.get(Player, game.invader_player_id)
            def_player = [p for p in game.players if p.user_id == defender.id][0]
            atk_fig = Figure.query.filter_by(game_id=game.id, player_id=atk_player.id).first()
            castle = Figure.query.filter_by(game_id=game.id, player_id=def_player.id).first()

            game.battle_modifier = [{'type': 'Civil War'}]
            game.defending_figure_id = None
            db.session.commit()
            adv_resp = client.post('/games/advance_figure', json={
                'game_id': game.id,
                'player_id': atk_player.id,
                'figure_id': atk_fig.id,
            }, headers=atk_headers)
            assert adv_resp.status_code == 200

            selected = client.post('/games/select_defender', json={
                'game_id': game.id,
                'player_id': atk_player.id,
                'figure_id': castle.id,
            }, headers=atk_headers)
            assert selected.status_code == 400
            assert 'village' in selected.get_json().get('message', '').lower()

    def test_civil_war_ignores_non_village_must_be_attacked(self, app, db):
        """Civil War should not force selecting a non-village taunt figure."""
        with app.app_context():
            attacker = _make_user(db, username='atk_civil_taunt')
            defender = _make_user(db, username='def_civil_taunt')
            land = _make_land(db, tier=1, owner_user_id=defender.id)
            _make_conquer_config(db, attacker, land)
            def_cfg = _make_defence_config(db, defender, land)
            fortress_cfg = LandConfigFigure.query.filter_by(config_id=def_cfg.id).first()
            fortress_cfg.family_name = 'Wooden Fortress'
            fortress_cfg.name = 'Wooden Fortress'
            fortress_cfg.field = 'military'
            _add_conquer_config_figure(
                db,
                def_cfg,
                defender,
                family_name='Small Yack Farm',
                name='Small Yack Farm',
                color='defensive',
                field='village',
            )
            db.session.commit()

            client = app.test_client()
            atk_headers = _auth_headers(app, attacker)
            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=atk_headers)
            assert resp.status_code == 200
            game = db.session.get(Game, resp.get_json()['game_id'])
            atk_player = db.session.get(Player, game.invader_player_id)
            def_player = [p for p in game.players if p.user_id == defender.id][0]
            atk_fig = Figure.query.filter_by(game_id=game.id, player_id=atk_player.id).first()
            farm = Figure.query.filter_by(
                game_id=game.id,
                player_id=def_player.id,
                family_name='Small Yack Farm',
            ).first()

            game.battle_modifier = [{'type': 'Civil War'}]
            game.defending_figure_id = None
            db.session.commit()
            adv_resp = client.post('/games/advance_figure', json={
                'game_id': game.id,
                'player_id': atk_player.id,
                'figure_id': atk_fig.id,
            }, headers=atk_headers)
            assert adv_resp.status_code == 200

            selected = client.post('/games/select_defender', json={
                'game_id': game.id,
                'player_id': atk_player.id,
                'figure_id': farm.id,
            }, headers=atk_headers)
            assert selected.status_code == 200

    def test_stale_cannot_attack_battle_figure_falls_back_to_selection(self, app, db):
        """Invalid active battle figures no longer strand conquer games."""
        with app.app_context():
            attacker = _make_user(db, username='atk_stale_temple')
            defender = _make_user(db, username='def_stale_temple')
            land = _make_land(db, tier=1, owner_user_id=defender.id)
            _make_conquer_config(db, attacker, land)
            def_cfg = _make_defence_config(db, defender, land)
            cfg_fig = LandConfigFigure.query.filter_by(config_id=def_cfg.id).first()
            cfg_fig.family_name = 'Himalaya Temple'
            cfg_fig.name = 'Himalaya Temple'
            cfg_fig.field = 'village'
            def_cfg.counter_spell_name = None
            db.session.commit()

            client = app.test_client()
            atk_headers = _auth_headers(app, attacker)
            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=atk_headers)
            assert resp.status_code == 200
            game = db.session.get(Game, resp.get_json()['game_id'])
            assert game.defending_figure_id is None

            atk_player = db.session.get(Player, game.invader_player_id)
            def_player = [p for p in game.players if p.user_id == defender.id][0]
            atk_fig = Figure.query.filter_by(game_id=game.id, player_id=atk_player.id).first()
            temple = Figure.query.filter_by(game_id=game.id, player_id=def_player.id).first()

            adv_resp = client.post('/games/advance_figure', json={
                'game_id': game.id,
                'player_id': atk_player.id,
                'figure_id': atk_fig.id,
            }, headers=atk_headers)
            assert adv_resp.status_code == 200
            db.session.refresh(game)
            assert game.turn_player_id == atk_player.id

            selected = client.post('/games/select_defender', json={
                'game_id': game.id,
                'player_id': atk_player.id,
                'figure_id': temple.id,
            }, headers=atk_headers)
            assert selected.status_code == 200

    def test_ai_counter_picker_falls_back_from_invalid_preselection(self, app, db):
        with app.app_context():
            attacker = _make_user(db, username='atk_ai_fallback')
            defender = _make_user(db, username='def_ai_fallback', is_ai=True)
            land = _make_land(db, tier=1, owner_user_id=defender.id)
            _make_conquer_config(db, attacker, land)
            def_cfg = _make_defence_config(db, defender, land)
            selected_cfg = LandConfigFigure.query.filter_by(config_id=def_cfg.id).first()
            selected_cfg.family_name = 'Himalaya Temple'
            selected_cfg.name = 'Himalaya Temple'
            selected_cfg.field = 'village'
            _add_conquer_config_figure(
                db,
                def_cfg,
                defender,
                family_name='Small Yack Farm',
                name='Small Yack Farm',
                color='defensive',
                field='village',
            )
            db.session.commit()

            client = app.test_client()
            atk_headers = _auth_headers(app, attacker)
            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=atk_headers)
            assert resp.status_code == 200
            game = db.session.get(Game, resp.get_json()['game_id'])
            atk_player = db.session.get(Player, game.invader_player_id)
            def_player = [p for p in game.players if p.user_id == defender.id][0]
            atk_fig = Figure.query.filter_by(game_id=game.id, player_id=atk_player.id).first()
            temple = Figure.query.filter_by(
                game_id=game.id,
                player_id=def_player.id,
                family_name='Himalaya Temple',
            ).first()
            farm = Figure.query.filter_by(
                game_id=game.id,
                player_id=def_player.id,
                family_name='Small Yack Farm',
            ).first()

            game.advancing_figure_id = atk_fig.id
            game.advancing_player_id = atk_player.id
            game.defending_figure_id = temple.id
            db.session.commit()

            from ai.ai_worker import _conquer_pick_counter_advance_figure
            assert _conquer_pick_counter_advance_figure(game, def_player.id) == farm.id


class TestConquerPreludeTargeting:
    """Conquer startup prelude targeting behavior."""

    def test_defender_targeted_prelude_auto_targets_non_checkmate(self, app, db):
        with app.app_context():
            attacker = _make_user(db, username='atk')
            defender = _make_user(db, username='def')

            land = _make_land(db, tier=1, owner_user_id=defender.id)
            atk_cfg = _make_conquer_config(db, attacker, land)
            def_cfg = _make_defence_config(db, defender, land)

            # Make one attacker figure checkmate and keep one normal figure,
            # so defender Poison must auto-target the non-checkmate figure.
            first_atk_fig = LandConfigFigure.query.filter_by(config_id=atk_cfg.id).first()
            first_atk_fig.checkmate = True
            _add_conquer_config_figure(
                db,
                atk_cfg,
                attacker,
                family_name='Militia Scout',
                name='Militia Scout',
                suit='Spades',
                field='military',
                checkmate=False,
            )

            def_cfg.prelude_spell_name = 'Poison'
            def_cfg.prelude_spell_data = {}
            db.session.commit()

            client = app.test_client()
            headers = _auth_headers(app, attacker)
            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=headers)
            assert resp.status_code == 200
            game = db.session.get(Game, resp.get_json()['game_id'])

            atk_player = db.session.get(Player, game.invader_player_id)
            def_player = [p for p in game.players if p.id != atk_player.id][0]

            spell = ActiveSpell.query.filter_by(
                game_id=game.id,
                player_id=def_player.id,
                spell_name='Poison',
            ).first()
            assert spell is not None
            assert spell.is_active is True
            assert spell.target_figure_id is not None

            target = db.session.get(Figure, spell.target_figure_id)
            assert target is not None
            assert target.player_id == atk_player.id
            assert target.checkmate is False

    def test_defender_health_boost_prelude_uses_configured_target(self, app, db):
        with app.app_context():
            attacker = _make_user(db, username='atk_health_prelude')
            defender = _make_user(db, username='def_health_prelude')

            land = _make_land(db, tier=1, owner_user_id=defender.id)
            _make_conquer_config(db, attacker, land)
            def_cfg = _make_defence_config(db, defender, land)
            target_cfg_fig = LandConfigFigure.query.filter_by(config_id=def_cfg.id).first()

            def_cfg.prelude_spell_name = 'Health Boost'
            def_cfg.prelude_spell_data = {'target_figure_id': target_cfg_fig.id}
            db.session.commit()

            client = app.test_client()
            headers = _auth_headers(app, attacker)
            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=headers)
            assert resp.status_code == 200
            game = db.session.get(Game, resp.get_json()['game_id'])
            def_player = [p for p in game.players if p.user_id == defender.id][0]

            spell = ActiveSpell.query.filter_by(
                game_id=game.id,
                player_id=def_player.id,
                spell_name='Health Boost',
            ).first()
            assert spell is not None
            assert spell.is_active is True
            assert (spell.effect_data or {}).get('prelude_status') == 'executed'
            assert (spell.effect_data or {}).get('power_modifier') == 6

            target = db.session.get(Figure, spell.target_figure_id)
            assert target is not None
            assert target.player_id == def_player.id
            assert target.name == target_cfg_fig.name
            assert target.source_config_figure_id == target_cfg_fig.id

    def test_defender_prelude_uses_modifier_target_heuristic(self, app, db):
        with app.app_context():
            attacker = _make_user(db, username='atk_heuristic')
            defender = _make_user(db, username='def_heuristic')

            land = _make_land(db, tier=1, owner_user_id=defender.id)
            atk_cfg = _make_conquer_config(db, attacker, land)
            def_cfg = _make_defence_config(db, defender, land)

            _add_conquer_config_figure(
                db,
                atk_cfg,
                attacker,
                family_name='Militia Scout',
                name='Militia Scout',
                suit='Spades',
                field='military',
            )

            atk_cfg.prelude_spell_name = 'Civil War'
            def_cfg.prelude_spell_name = 'Poison'
            def_cfg.prelude_spell_data = {}
            db.session.commit()

            client = app.test_client()
            headers = _auth_headers(app, attacker)
            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=headers)
            assert resp.status_code == 200
            game = db.session.get(Game, resp.get_json()['game_id'])
            def_player = [p for p in game.players if p.user_id == defender.id][0]

            spell = ActiveSpell.query.filter_by(
                game_id=game.id,
                player_id=def_player.id,
                spell_name='Poison',
            ).first()
            assert spell is not None
            target = db.session.get(Figure, spell.target_figure_id)
            assert target is not None
            assert target.field == 'village'
            assert target.family_name == 'Small Rice Farm'

    def test_attacker_targeted_prelude_blocks_actions_until_resolved(self, app, db):
        with app.app_context():
            attacker = _make_user(db, username='atk')
            defender = _make_user(db, username='def')

            land = _make_land(db, tier=1, owner_user_id=defender.id)
            atk_cfg = _make_conquer_config(db, attacker, land)
            def_cfg = _make_defence_config(db, defender, land)

            atk_cfg.prelude_spell_name = 'Poison'
            atk_cfg.prelude_spell_data = {}
            def_cfg.prelude_spell_name = None
            db.session.commit()

            client = app.test_client()
            headers = _auth_headers(app, attacker)
            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=headers)
            assert resp.status_code == 200
            game = db.session.get(Game, resp.get_json()['game_id'])

            atk_player = db.session.get(Player, game.invader_player_id)
            def_player = [p for p in game.players if p.id != atk_player.id][0]

            pending_spell = ActiveSpell.query.filter_by(
                game_id=game.id,
                player_id=atk_player.id,
                spell_name='Poison',
            ).first()
            assert pending_spell is not None
            assert pending_spell.is_active is False
            assert (pending_spell.effect_data or {}).get('prelude_pending_target') is True

            # Invader cannot advance until prelude target is resolved.
            atk_figure = Figure.query.filter_by(game_id=game.id, player_id=atk_player.id).first()
            block_resp = client.post('/games/advance_figure', json={
                'game_id': game.id,
                'player_id': atk_player.id,
                'figure_id': atk_figure.id,
            }, headers=headers)
            assert block_resp.status_code == 400
            assert block_resp.get_json().get('reason') == 'pending_prelude_target'

            # Resolve pending prelude with a valid defender target.
            def_target = Figure.query.filter_by(game_id=game.id, player_id=def_player.id).first()
            resolve_resp = client.post('/kingdom/conquer/resolve_prelude_target', json={
                'game_id': game.id,
                'spell_id': pending_spell.id,
                'target_figure_id': def_target.id,
            }, headers=headers)
            assert resolve_resp.status_code == 200
            assert resolve_resp.get_json()['success'] is True

            db.session.refresh(pending_spell)
            assert pending_spell.target_figure_id == def_target.id
            assert (pending_spell.effect_data or {}).get('prelude_status') == 'executed'


    def test_attacker_targeted_prelude_no_target_is_reported_in_game_start(self, app, db):
        with app.app_context():
            attacker = _make_user(db, username='atk')
            defender = _make_user(db, username='def')

            land = _make_land(db, tier=1, owner_user_id=defender.id)
            atk_cfg = _make_conquer_config(db, attacker, land)
            def_cfg = _make_defence_config(db, defender, land)

            atk_cfg.prelude_spell_name = 'Poison'
            atk_cfg.prelude_spell_data = {}

            # Defender has only checkmate figures -> no valid Poison targets.
            for fig in LandConfigFigure.query.filter_by(config_id=def_cfg.id).all():
                fig.checkmate = True
            db.session.commit()

            client = app.test_client()
            headers = _auth_headers(app, attacker)
            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=headers)
            assert resp.status_code == 200
            game = db.session.get(Game, resp.get_json()['game_id'])

            atk_player = db.session.get(Player, game.invader_player_id)
            spell = ActiveSpell.query.filter_by(
                game_id=game.id,
                player_id=atk_player.id,
                spell_name='Poison',
            ).first()
            assert spell is not None
            assert spell.is_active is False
            assert (spell.effect_data or {}).get('prelude_status') == 'no_valid_target'

            start_resp = client.post('/games/start_turn', json={
                'game_id': game.id,
                'player_id': atk_player.id,
            }, headers=headers)
            assert start_resp.status_code == 200

            summary = (start_resp.get_json() or {}).get('opponent_turn_summary') or {}
            assert summary.get('action') == 'game_start'
            assert summary.get('pending_prelude_target') is None
            own_no_target = summary.get('own_prelude_no_target_spells') or []
            assert any(s.get('spell_name') == 'Poison' for s in own_no_target)

    def test_defender_explosion_prelude_does_not_preempt_game_start_summary(self, app, db):
        with app.app_context():
            attacker = _make_user(db, username='atk_intro_explosion')
            defender = _make_user(db, username='def_intro_explosion')

            land = _make_land(db, tier=1, owner_user_id=defender.id)
            _make_conquer_config(db, attacker, land)
            def_cfg = _make_defence_config(db, defender, land)
            def_cfg.prelude_spell_name = 'Explosion'
            def_cfg.prelude_spell_data = {}
            db.session.commit()

            client = app.test_client()
            headers = _auth_headers(app, attacker)
            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=headers)
            assert resp.status_code == 200
            game = db.session.get(Game, resp.get_json()['game_id'])
            atk_player = db.session.get(Player, game.invader_player_id)

            start_resp = client.post('/games/start_turn', json={
                'game_id': game.id,
                'player_id': atk_player.id,
            }, headers=headers)
            assert start_resp.status_code == 200
            summary = (start_resp.get_json() or {}).get('opponent_turn_summary') or {}
            assert summary.get('action') == 'game_start'
            opponent_spells = summary.get('opponent_prelude_spells') or []
            assert any(s.get('spell_name') == 'Explosion' for s in opponent_spells)

    def test_attacker_explosion_prelude_clears_stale_defender_reference(self, app, db):
        with app.app_context():
            attacker = _make_user(db, username='atk_stale_explosion')
            defender = _make_user(db, username='def_stale_explosion')

            land = _make_land(db, tier=1, owner_user_id=defender.id)
            atk_cfg = _make_conquer_config(db, attacker, land)
            _make_defence_config(db, defender, land)
            atk_cfg.prelude_spell_name = 'Explosion'
            atk_cfg.prelude_spell_data = {}
            db.session.commit()

            client = app.test_client()
            headers = _auth_headers(app, attacker)
            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=headers)
            assert resp.status_code == 200
            game = db.session.get(Game, resp.get_json()['game_id'])
            atk_player = db.session.get(Player, game.invader_player_id)
            target_id = game.defending_figure_id
            assert target_id is not None

            pending_spell = ActiveSpell.query.filter_by(
                game_id=game.id,
                player_id=atk_player.id,
                spell_name='Explosion',
            ).first()
            assert pending_spell is not None

            resolve_resp = client.post('/kingdom/conquer/resolve_prelude_target', json={
                'game_id': game.id,
                'spell_id': pending_spell.id,
                'target_figure_id': target_id,
            }, headers=headers)
            assert resolve_resp.status_code == 200

            db.session.refresh(game)
            assert db.session.get(Figure, target_id) is None
            assert game.defending_figure_id is None
            assert game.defending_figure_id_2 is None


class TestConquerCounterSpells:
    """Conquer defender counter spell response behavior."""

    def test_defence_counter_explosion_rejected(self, app, db):
        with app.app_context():
            defender = _make_user(db, username='def_counter_reject')
            land = _make_land(db, tier=1, owner_user_id=defender.id)
            _make_defence_config(db, defender, land)

            client = app.test_client()
            headers = _auth_headers(app, defender)
            resp = client.post('/kingdom/defence/set_counter_spell', json={
                'land_id': land.id,
                'spell_name': 'Explosion',
            }, headers=headers)
            assert resp.status_code == 400
            assert 'not allowed' in resp.get_json().get('message', '').lower()

    def test_counter_poison_targets_advancing_figure_and_skips_counter_advance(self, app, db):
        with app.app_context():
            attacker = _make_user(db, username='atk_counter_poison')
            defender = _make_user(db, username='def_counter_poison')

            land = _make_land(db, tier=1, owner_user_id=defender.id)
            _make_conquer_config(db, attacker, land)
            def_cfg = _make_defence_config(db, defender, land)
            def_cfg.battle_figure_id = None
            def_cfg.counter_spell_name = 'Poison'
            def_cfg.counter_spell_data = {}
            db.session.commit()

            client = app.test_client()
            atk_headers = _auth_headers(app, attacker)
            def_headers = _auth_headers(app, defender)
            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=atk_headers)
            assert resp.status_code == 200
            game = db.session.get(Game, resp.get_json()['game_id'])
            atk_player = db.session.get(Player, game.invader_player_id)
            def_player = [p for p in game.players if p.user_id == defender.id][0]
            atk_fig = Figure.query.filter_by(game_id=game.id, player_id=atk_player.id).first()

            assert ActiveSpell.query.filter_by(game_id=game.id, player_id=def_player.id).count() == 0

            adv_resp = client.post('/games/advance_figure', json={
                'game_id': game.id,
                'player_id': atk_player.id,
                'figure_id': atk_fig.id,
            }, headers=atk_headers)
            assert adv_resp.status_code == 200
            db.session.refresh(game)
            assert game.turn_player_id == def_player.id

            counter_resp = client.post('/games/conquer_defender_counter_spell', json={
                'game_id': game.id,
                'player_id': def_player.id,
            }, headers=def_headers)
            assert counter_resp.status_code == 200

            spell = ActiveSpell.query.filter_by(
                game_id=game.id,
                player_id=def_player.id,
                spell_name='Poison',
            ).first()
            assert spell is not None
            assert spell.target_figure_id == atk_fig.id
            assert (spell.effect_data or {}).get('counter_status') == 'executed'

            db.session.refresh(game)
            assert game.turn_player_id == atk_player.id
            assert game.defending_figure_id is None

    def test_counter_health_boost_uses_configured_target(self, app, db):
        with app.app_context():
            attacker = _make_user(db, username='atk_counter_health')
            defender = _make_user(db, username='def_counter_health')

            land = _make_land(db, tier=1, owner_user_id=defender.id)
            _make_conquer_config(db, attacker, land)
            def_cfg = _make_defence_config(db, defender, land)
            target_cfg_fig = LandConfigFigure.query.filter_by(config_id=def_cfg.id).first()
            def_cfg.battle_figure_id = None
            def_cfg.counter_spell_name = 'Health Boost'
            def_cfg.counter_spell_data = {}
            def_cfg.counter_spell_target_figure_id = target_cfg_fig.id
            db.session.commit()

            client = app.test_client()
            atk_headers = _auth_headers(app, attacker)
            def_headers = _auth_headers(app, defender)
            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=atk_headers)
            assert resp.status_code == 200
            game = db.session.get(Game, resp.get_json()['game_id'])
            atk_player = db.session.get(Player, game.invader_player_id)
            def_player = [p for p in game.players if p.user_id == defender.id][0]
            atk_fig = Figure.query.filter_by(game_id=game.id, player_id=atk_player.id).first()

            adv_resp = client.post('/games/advance_figure', json={
                'game_id': game.id,
                'player_id': atk_player.id,
                'figure_id': atk_fig.id,
            }, headers=atk_headers)
            assert adv_resp.status_code == 200

            counter_resp = client.post('/games/conquer_defender_counter_spell', json={
                'game_id': game.id,
                'player_id': def_player.id,
            }, headers=def_headers)
            assert counter_resp.status_code == 200

            spell = ActiveSpell.query.filter_by(
                game_id=game.id,
                player_id=def_player.id,
                spell_name='Health Boost',
            ).first()
            assert spell is not None
            target = db.session.get(Figure, spell.target_figure_id)
            assert target is not None
            assert target.player_id == def_player.id
            assert target.name == target_cfg_fig.name
            assert target.source_config_figure_id == target_cfg_fig.id
            assert (spell.effect_data or {}).get('power_modifier') == 6

            db.session.refresh(game)
            assert game.turn_player_id == atk_player.id
            assert game.defending_figure_id is None

    @pytest.mark.parametrize('spell_name, expected_attacker_moves, expected_added', [
        ('Forced Deal', 1, 2),
        ('Dump Cards', 0, 3),
    ])
    def test_move_mutating_ai_counter_replenishes_defender_only(
        self, app, db, spell_name, expected_attacker_moves, expected_added,
    ):
        """AI counter spells can disrupt both sides without stranding the AI."""
        with app.app_context():
            attacker = _make_user(db, username=f'atk_counter_{spell_name.replace(" ", "_")}')
            land = _make_land(db, tier=1)
            _make_conquer_config(db, attacker, land)
            template = _scripted_ai_template(counter_spell_name=spell_name)

            client = app.test_client()
            atk_headers = _auth_headers(app, attacker)
            with patch('routes.kingdom.get_ai_defence_template_for_land', return_value=template), \
                    patch('routes.games.get_ai_defence_template_for_land', return_value=template):
                start_resp = client.post('/kingdom/conquer/start_battle',
                                         json={'land_id': land.id}, headers=atk_headers)
                assert start_resp.status_code == 200
                game = db.session.get(Game, start_resp.get_json()['game_id'])
                atk_player = db.session.get(Player, game.invader_player_id)
                def_player = [p for p in game.players if p.id != atk_player.id][0]
                ai_user = db.session.get(User, def_player.user_id)

                atk_fig = Figure.query.filter_by(
                    game_id=game.id,
                    player_id=atk_player.id,
                ).first()
                adv_resp = client.post('/games/advance_figure', json={
                    'game_id': game.id,
                    'player_id': atk_player.id,
                    'figure_id': atk_fig.id,
                }, headers=atk_headers)
                assert adv_resp.status_code == 200

                db.session.refresh(game)
                assert game.turn_player_id == def_player.id

                def_headers = _auth_headers(app, ai_user)
                counter_resp = client.post('/games/conquer_defender_counter_spell', json={
                    'game_id': game.id,
                    'player_id': def_player.id,
                }, headers=def_headers)

            assert counter_resp.status_code == 200
            payload = counter_resp.get_json()
            assert payload['spell_name'] == spell_name
            assert payload['status'] == 'executed'
            assert payload['defender_replenished_battle_moves']['added'] == expected_added

            defender_moves = BattleMove.query.filter_by(
                game_id=game.id,
                player_id=def_player.id,
            ).all()
            attacker_moves = BattleMove.query.filter_by(
                game_id=game.id,
                player_id=atk_player.id,
            ).all()
            attacker_free_main = MainCard.query.filter_by(
                game_id=game.id,
                player_id=atk_player.id,
                in_deck=False,
                part_of_figure=False,
                part_of_battle_move=False,
            ).count()

            assert len(defender_moves) == 3
            assert len(attacker_moves) == expected_attacker_moves
            assert attacker_free_main >= 2


class TestConquerCounterSpellGating:
    """One-counter-per-round and validation gating for conquer counter spells."""

    def test_counter_spell_can_only_be_cast_once_per_round(self, app, db):
        with app.app_context():
            from models import LogEntry
            attacker = _make_user(db, username='atk_counter_once')
            defender = _make_user(db, username='def_counter_once')

            land = _make_land(db, tier=1, owner_user_id=defender.id)
            _make_conquer_config(db, attacker, land)
            def_cfg = _make_defence_config(db, defender, land)
            def_cfg.battle_figure_id = None
            def_cfg.counter_spell_name = 'Poison'
            def_cfg.counter_spell_data = {}
            db.session.commit()

            client = app.test_client()
            atk_headers = _auth_headers(app, attacker)
            def_headers = _auth_headers(app, defender)
            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=atk_headers)
            assert resp.status_code == 200
            game = db.session.get(Game, resp.get_json()['game_id'])
            atk_player = db.session.get(Player, game.invader_player_id)
            def_player = [p for p in game.players if p.user_id == defender.id][0]
            atk_fig = Figure.query.filter_by(game_id=game.id, player_id=atk_player.id).first()

            client.post('/games/advance_figure', json={
                'game_id': game.id,
                'player_id': atk_player.id,
                'figure_id': atk_fig.id,
            }, headers=atk_headers)

            first = client.post('/games/conquer_defender_counter_spell', json={
                'game_id': game.id,
                'player_id': def_player.id,
            }, headers=def_headers)
            assert first.status_code == 200

            # Simulate the next defender response window in the same round
            # (e.g. Civil War 2nd advance) by clearing the defender slot and
            # handing the turn back to the defender.  The counter gate must
            # block the second cast based on the existing counter_spell log.
            db.session.refresh(game)
            game.defending_figure_id = None
            game.turn_player_id = def_player.id
            db.session.commit()

            second = client.post('/games/conquer_defender_counter_spell', json={
                'game_id': game.id,
                'player_id': def_player.id,
            }, headers=def_headers)
            assert second.status_code == 400
            assert 'already' in (second.get_json() or {}).get('message', '').lower()

            counter_logs = LogEntry.query.filter_by(
                game_id=game.id, player_id=def_player.id, type='counter_spell',
            ).count()
            assert counter_logs == 1

    def test_check_defence_incomplete_requires_health_boost_target(self, app, db):
        with app.app_context():
            from kingdom_service import check_defence_incomplete
            from models import LandConfigBattleMove

            defender = _make_user(db, username='def_hb_incomplete')
            land = _make_land(db, tier=1, owner_user_id=defender.id)
            cfg = _make_defence_config(db, defender, land)

            for i, (rank, suit, value) in enumerate([
                ('9', 'Hearts', 9), ('Q', 'Hearts', 3), ('J', 'Hearts', 2),
            ]):
                cc = CollectionCard(user_id=defender.id, suit=suit, rank=rank,
                                    value=value, locked=True,
                                    lock_type='defence_move')
                db.session.add(cc)
                db.session.flush()
                db.session.add(LandConfigBattleMove(
                    config_id=cfg.id, family_name='Dagger',
                    card_id=cc.id, suit=suit, rank=rank, value=value,
                    round_index=i + 1,
                ))
            cfg.battle_figure_id = None
            cfg.counter_spell_name = 'Health Boost'
            cfg.counter_spell_target_figure_id = None
            db.session.commit()

            assert check_defence_incomplete(land.id, defender.id) is True

            target_fig = LandConfigFigure.query.filter_by(config_id=cfg.id).first()
            cfg.counter_spell_target_figure_id = target_fig.id
            db.session.commit()
            assert check_defence_incomplete(land.id, defender.id) is False


class TestConquerResolution:
    """Tests for conquer post-battle resolution."""

    def test_conquer_game_finishes_after_battle(self, app, db):
        """A conquer game is marked finished after resolve."""
        with app.app_context():
            user = _make_user(db)
            land = _make_land(db, tier=1)
            _make_conquer_config(db, user, land)

            client = app.test_client()
            headers = _auth_headers(app, user)

            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=headers)
            data = resp.get_json()
            game = db.session.get(Game, data['game_id'])

            # Directly set up battle state to test resolution
            atk_player = db.session.get(Player, game.invader_player_id)
            def_player = [p for p in game.players
                          if p.id != atk_player.id][0]

            # Pick figures
            atk_fig = Figure.query.filter_by(
                game_id=game.id, player_id=atk_player.id).first()
            def_fig = Figure.query.filter_by(
                game_id=game.id, player_id=def_player.id).first()

            game.advancing_figure_id = atk_fig.id
            game.advancing_player_id = atk_player.id
            game.defending_figure_id = def_fig.id
            game.battle_confirmed = True
            db.session.commit()

            # The game state is correctly set up for a conquer battle
            assert game.mode == 'conquer'
            assert game.state == 'open'

    def test_attack_log_created(self, app, db):
        """A LandAttackLog record is created after conquer resolution."""
        with app.app_context():
            user = _make_user(db)
            land = _make_land(db, tier=1)
            _make_conquer_config(db, user, land)

            client = app.test_client()
            headers = _auth_headers(app, user)

            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=headers)
            data = resp.get_json()
            game = db.session.get(Game, data['game_id'])

            # Verify no logs exist yet
            logs_before = LandAttackLog.query.filter_by(
                land_id=land.id).count()
            assert logs_before == 0


class TestConquerFinishedIdempotency:
    """Finished conquer games should return stable conquer_result payloads."""

    def _make_finished_conquer_game(self, app, db, *, result='draw'):
        attacker = _make_user(db, username='attacker_finished')
        defender = _make_user(db, username='defender_finished')
        land = _make_land(db, tier=1, owner_user_id=defender.id)

        game = Game(
            mode='conquer',
            state='finished',
            land_id=land.id,
            stake=0,
            current_round=1,
            ceasefire_active=False,
            battle_confirmed=False,
        )
        db.session.add(game)
        db.session.flush()

        atk_player = Player(user_id=attacker.id, game_id=game.id, turns_left=0, points=0)
        def_player = Player(user_id=defender.id, game_id=game.id, turns_left=0, points=0)
        db.session.add_all([atk_player, def_player])
        db.session.flush()

        game.invader_player_id = atk_player.id
        game.turn_player_id = atk_player.id
        if result == 'attacker_won':
            game.winner_player_id = atk_player.id
        elif result == 'defender_won':
            game.winner_player_id = def_player.id
        else:
            game.winner_player_id = None
        game.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)

        if result != 'draw':
            log = LandAttackLog(
                land_id=land.id,
                attacker_user_id=attacker.id,
                defender_user_id=defender.id,
                result=result,
                card_won_suit='Hearts',
                card_won_rank='K',
                card_lost_suit='Spades',
                card_lost_rank='J',
            )
            db.session.add(log)

        db.session.commit()
        client = app.test_client()
        atk_headers = _auth_headers(app, attacker)
        return client, atk_headers, game, atk_player

    def test_finish_battle_returns_draw_for_finished_conquer_draw(self, app, db):
        with app.app_context():
            client, atk_headers, game, atk_player = self._make_finished_conquer_game(
                app, db, result='draw')

            resp = client.post('/games/finish_battle', json={
                'game_id': game.id,
                'player_id': atk_player.id,
                'total_diff': 0,
            }, headers=atk_headers)

            assert resp.status_code == 200
            data = resp.get_json()
            assert data.get('success') is True
            assert data.get('already_resolved') is True
            assert data.get('conquer_result') == 'draw'
            assert data.get('outcome') == 'draw'

    def test_finish_battle_pick_card_returns_conquer_result_after_cleanup(self, app, db):
        with app.app_context():
            client, atk_headers, game, atk_player = self._make_finished_conquer_game(
                app, db, result='defender_won')

            resp = client.post('/games/finish_battle_pick_card', json={
                'game_id': game.id,
                'player_id': atk_player.id,
                'picked_card_id': None,
                'picked_card_type': 'main',
            }, headers=atk_headers)

            assert resp.status_code == 200
            data = resp.get_json()
            assert data.get('success') is True
            assert data.get('already_resolved') is True
            assert data.get('conquer_result') == 'defender_won'
            assert data.get('attacker_won') is False


class TestSuitBonus:
    """Tests for suit bonus application in conquer battles."""

    def test_suit_bonus_not_applied_in_duel(self, app, db):
        """Suit bonus should not apply in duel mode."""
        with app.app_context():
            # Create a duel game
            game = Game(mode='duel', state='open', current_round=1,
                        ceasefire_active=True)
            db.session.add(game)
            db.session.commit()

            # Duel game has no land_id, so suit bonus won't apply
            assert game.mode == 'duel'
            assert game.land_id is None

    def test_conquer_game_has_land_id(self, app, db):
        """Conquer game has land_id set for suit bonus lookup."""
        with app.app_context():
            user = _make_user(db)
            land = _make_land(db, tier=1)
            _make_conquer_config(db, user, land)

            client = app.test_client()
            headers = _auth_headers(app, user)

            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=headers)
            data = resp.get_json()

            game = db.session.get(Game, data['game_id'])
            assert game.land_id == land.id
            assert game.mode == 'conquer'

            # Verify land has suit bonus
            assert land.suit_bonus_suit == 'Hearts'
            assert land.suit_bonus_value == 3


class TestConquerValidation:
    """Edge case validation tests."""

    def test_missing_land_id(self, app, db):
        with app.app_context():
            user = _make_user(db)
            client = app.test_client()
            headers = _auth_headers(app, user)

            resp = client.post('/kingdom/conquer/start_battle',
                               json={}, headers=headers)
            assert resp.status_code == 400

    def test_nonexistent_land(self, app, db):
        with app.app_context():
            user = _make_user(db)
            client = app.test_client()
            headers = _auth_headers(app, user)

            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': 9999}, headers=headers)
            assert resp.status_code == 404

    def test_no_battle_moves_rejected(self, app, db):
        """Rejected if config has figures but no battle moves."""
        with app.app_context():
            user = _make_user(db)
            land = _make_land(db, tier=1)

            cfg = LandConfig(user_id=user.id, config_type='conquer',
                             land_id=land.id)
            db.session.add(cfg)
            db.session.flush()

            cc = CollectionCard(user_id=user.id, suit='Diamonds', rank='J',
                                value=1, locked=True)
            db.session.add(cc)
            db.session.flush()

            fig = LandConfigFigure(
                config_id=cfg.id,
                family_name='Small Rice Farm', name='Small Rice Farm',
                suit='Diamonds', color='offensive', field='village',
                card_ids=[cc.id], card_roles=['key'],
                produces={'food_red': 8}, requires={},
            )
            db.session.add(fig)
            db.session.commit()

            client = app.test_client()
            headers = _auth_headers(app, user)

            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=headers)
            assert resp.status_code == 400
            assert 'no battle moves' in resp.get_json()['message'].lower()

    def test_player_owned_land_no_defence_config(self, app, db):
        """Rejected when attacking player-owned land with no defence config."""
        with app.app_context():
            attacker = _make_user(db, username='attacker')
            defender = _make_user(db, username='defender')

            land = _make_land(db, tier=1, owner_user_id=defender.id)
            _make_conquer_config(db, attacker, land)
            # No defence config for defender

            client = app.test_client()
            headers = _auth_headers(app, attacker)

            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=headers)
            assert resp.status_code == 400
            assert 'no defence config' in resp.get_json()['message'].lower()


# ═════════════════════════════════════════════════════════════════════════════
#  Conquer AI Auto-Play
# ═════════════════════════════════════════════════════════════════════════════

class TestConquerAutoPlay:
    """Tests for the rule-based conquer defender auto-play path."""

    def test_conquer_game_routes_to_conquer_ai_loop(self, app, db):
        """trigger_ai_if_needed spawns _conquer_ai_loop for conquer games."""
        with app.app_context():
            user = _make_user(db)
            ai_user = _make_ai_user(db)
            land = _make_land(db, tier=1)

            game = Game(mode='conquer', state='open', land_id=land.id, stake=0,
                        current_round=1, ceasefire_active=False,
                        battle_confirmed=False)
            db.session.add(game)
            db.session.flush()

            p1 = Player(user_id=user.id, game_id=game.id, turns_left=1, points=0)
            p2 = Player(user_id=ai_user.id, game_id=game.id, turns_left=1, points=0)
            db.session.add_all([p1, p2])
            db.session.flush()
            game.turn_player_id = p2.id
            game.invader_player_id = p1.id
            db.session.commit()

            spawned_targets = []
            original_thread = __import__('threading').Thread

            def capture_thread(*args, **kwargs):
                t = original_thread(*args, **kwargs)
                spawned_targets.append(kwargs.get('target', args[0] if args else None))
                # Don't actually start the thread
                t.start = lambda: None
                return t

            import ai.ai_worker as aw
            # Clear active games set to avoid blocking
            with aw._active_games_lock:
                aw._active_games.clear()
            with patch.object(aw.settings, 'AI_ENABLED', True), \
                 patch('threading.Thread', side_effect=capture_thread):
                aw.trigger_ai_if_needed(game.id, app=app)

            assert len(spawned_targets) == 1
            assert spawned_targets[0] is aw._conquer_ai_loop

    def test_conquer_human_defender_still_routes_to_conquer_ai_loop(self, app, db):
        """Conquer defender automation must run even for non-AI defender accounts."""
        with app.app_context():
            attacker = _make_user(db, username='conquer_attacker')
            defender = _make_user(db, username='conquer_defender')
            land = _make_land(db, tier=2, owner_user_id=defender.id)

            game = Game(mode='conquer', state='open', land_id=land.id, stake=0,
                        current_round=1, ceasefire_active=False,
                        battle_confirmed=False)
            db.session.add(game)
            db.session.flush()

            p1 = Player(user_id=attacker.id, game_id=game.id, turns_left=1, points=0)
            p2 = Player(user_id=defender.id, game_id=game.id, turns_left=1, points=0)
            db.session.add_all([p1, p2])
            db.session.flush()
            game.invader_player_id = p1.id
            game.turn_player_id = p2.id  # Defender's scripted normal_turn phase
            db.session.commit()

            spawned_targets = []
            spawned_args = []
            original_thread = __import__('threading').Thread

            def capture_thread(*args, **kwargs):
                t = original_thread(*args, **kwargs)
                spawned_targets.append(kwargs.get('target', args[0] if args else None))
                thread_args = kwargs.get('args', args[1] if len(args) > 1 else ())
                spawned_args.append(thread_args)
                # Don't actually start the thread
                t.start = lambda: None
                return t

            import ai.ai_worker as aw
            with aw._active_games_lock:
                aw._active_games.clear()
            with patch.object(aw.settings, 'AI_ENABLED', True), \
                 patch('threading.Thread', side_effect=capture_thread):
                aw.trigger_ai_if_needed(game.id, app=app)

            assert len(spawned_targets) == 1
            assert spawned_targets[0] is aw._conquer_ai_loop
            assert spawned_args[0][2] == p2.id

    def test_duel_game_routes_to_normal_ai_loop(self, app, db):
        """trigger_ai_if_needed spawns _ai_game_loop for duel games."""
        with app.app_context():
            user = _make_user(db)
            ai_user = _make_ai_user(db)

            game = Game(mode='duel', state='open', stake=10,
                        current_round=1, ceasefire_active=False,
                        battle_confirmed=False)
            db.session.add(game)
            db.session.flush()

            p1 = Player(user_id=user.id, game_id=game.id, turns_left=1, points=0)
            p2 = Player(user_id=ai_user.id, game_id=game.id, turns_left=1, points=0)
            db.session.add_all([p1, p2])
            db.session.flush()
            game.turn_player_id = p2.id
            game.invader_player_id = p1.id
            db.session.commit()

            spawned_targets = []
            original_thread = __import__('threading').Thread

            def capture_thread(*args, **kwargs):
                t = original_thread(*args, **kwargs)
                spawned_targets.append(kwargs.get('target', args[0] if args else None))
                t.start = lambda: None
                return t

            import ai.ai_worker as aw
            with aw._active_games_lock:
                aw._active_games.clear()
            with patch.object(aw.settings, 'AI_ENABLED', True), \
                 patch.object(aw.settings, 'AI_OPENAI_API_KEY', 'fake-key'), \
                 patch('threading.Thread', side_effect=capture_thread):
                aw.trigger_ai_if_needed(game.id, app=app)

            assert len(spawned_targets) == 1
            assert spawned_targets[0] is aw._ai_game_loop


# ═════════════════════════════════════════════════════════════════════════════
#  AI Template Card Rewards (Phase 15.3)
# ═════════════════════════════════════════════════════════════════════════════

class TestAITemplateCardRewards:
    """Card rewards when beating an AI-owned land."""

    def _start_battle_and_resolve(self, app, db, attacker_wins=True):
        """Helper: start a conquer battle and call _resolve_conquer_battle."""
        from routes.games import _resolve_conquer_battle

        user = _make_user(db)
        land = _make_land(db, tier=1)
        cfg = _make_conquer_config(db, user, land)

        client = app.test_client()
        headers = _auth_headers(app, user)
        resp = client.post('/kingdom/conquer/start_battle',
                           json={'land_id': land.id}, headers=headers)
        data = resp.get_json()
        game = db.session.get(Game, data['game_id'])

        atk_player = db.session.get(Player, game.invader_player_id)
        def_player = [p for p in game.players if p.id != atk_player.id][0]

        winner = atk_player if attacker_wins else def_player
        result = _resolve_conquer_battle(game, winner, atk_player)
        db.session.commit()
        return result, user, land, game, cfg

    def test_attacker_wins_ai_land_gets_card(self, app, db):
        """Attacker beating an AI land receives a card from the template."""
        with app.app_context():
            result, user, land, game, cfg = self._start_battle_and_resolve(
                app, db, attacker_wins=True)

            assert result['attacker_won'] is True
            assert result['conquer_result'] == 'attacker_won'

            # A card was won
            log = LandAttackLog.query.filter_by(land_id=land.id).first()
            assert log is not None
            assert log.card_won_suit is not None
            assert log.card_won_rank is not None

            # A CollectionCard was created for the attacker
            from models import CollectionCard
            new_cards = CollectionCard.query.filter_by(
                user_id=user.id, locked=False
            ).all()
            rewarded = [c for c in new_cards
                        if c.suit == log.card_won_suit
                        and c.rank == log.card_won_rank]
            assert len(rewarded) >= 1

    def test_attacker_wins_ai_land_rewards_only_template_key_cards(self, app, db, monkeypatch):
        """AI/template loot rewards are selected only from figure key cards."""
        with app.app_context():
            import importlib
            from routes.games import _resolve_conquer_battle
            import random as random_module

            games_routes = importlib.import_module('routes.games')

            user = _make_user(db, username='ai_key_reward')
            land = _make_land(db, tier=1)
            _make_conquer_config(db, user, land)

            client = app.test_client()
            headers = _auth_headers(app, user)
            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=headers)
            data = resp.get_json()
            game = db.session.get(Game, data['game_id'])

            atk_player = db.session.get(Player, game.invader_player_id)
            def_player = [p for p in game.players if p.id != atk_player.id][0]

            monkeypatch.setattr(
                games_routes,
                'get_ai_defence_template_for_land',
                lambda _land: _scripted_ai_template(),
            )

            seen_choices = []

            def choose_first(options):
                choices = list(options)
                seen_choices.append(choices)
                assert choices
                assert all(card.get('role') == 'key' for card in choices)
                return choices[0]

            monkeypatch.setattr(random_module, 'choice', choose_first)

            result = _resolve_conquer_battle(game, atk_player, atk_player)
            db.session.commit()

            assert result['conquer_result'] == 'attacker_won'
            assert seen_choices
            assert result['card_won_suit'] == 'Hearts'
            assert result['card_won_rank'] == 'J'
            assert CollectionCard.query.filter_by(
                user_id=user.id, suit='Hearts', rank='J', locked=False,
            ).first() is not None
            assert CollectionCard.query.filter_by(
                user_id=user.id, suit='Hearts', rank='8', locked=False,
            ).first() is None

    def test_attacker_wins_ai_land_transfers_ownership(self, app, db):
        """Attacker winning transfers land ownership."""
        with app.app_context():
            result, user, land, game, cfg = self._start_battle_and_resolve(
                app, db, attacker_wins=True)

            db.session.refresh(land)
            assert land.owner_user_id == user.id

    def test_attacker_wins_sets_land_conquer_protection(self, app, db):
        """Successful conquest sets a temporary land-level conquer protection timestamp."""
        with app.app_context():
            with patch.object(config, 'LAND_CONQUER_PROTECTION_SECONDS', 300):
                _, user, land, _, _ = self._start_battle_and_resolve(
                    app, db, attacker_wins=True)

            db.session.refresh(land)
            assert land.owner_user_id == user.id
            assert land.conquer_cooldown_until is not None
            remaining = (land.conquer_cooldown_until - datetime.now(timezone.utc).replace(tzinfo=None)).total_seconds()
            assert remaining > 0
            assert remaining <= 300

    def test_start_battle_rejected_during_land_conquer_protection(self, app, db):
        """Other attackers cannot start conquer while land protection is active."""
        with app.app_context():
            with patch.object(config, 'LAND_CONQUER_PROTECTION_SECONDS', 300):
                _, owner, land, _, _ = self._start_battle_and_resolve(
                    app, db, attacker_wins=True)

            challenger = _make_user(db, username='challenger')
            _make_conquer_config(db, challenger, land)

            client = app.test_client()
            headers = _auth_headers(app, challenger)
            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=headers)

            assert resp.status_code == 400
            assert 'conquer protection' in resp.get_json()['message'].lower()

    def test_start_battle_allows_when_land_conquer_protection_expired(self, app, db):
        """Conquer can start again once land protection timestamp has passed."""
        with app.app_context():
            with patch.object(config, 'LAND_CONQUER_PROTECTION_SECONDS', 60):
                _, owner, land, _, _ = self._start_battle_and_resolve(
                    app, db, attacker_wins=True)

            land.conquer_cooldown_until = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
            db.session.commit()

            challenger = _make_user(db, username='challenger_expired')
            _make_conquer_config(db, challenger, land)

            client = app.test_client()
            headers = _auth_headers(app, challenger)
            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=headers)

            assert resp.status_code == 200

    def test_defender_wins_attacker_loses_key_card(self, app, db):
        """When defender wins, attacker loses a key card."""
        with app.app_context():
            result, user, land, game, cfg = self._start_battle_and_resolve(
                app, db, attacker_wins=False)

            assert result['attacker_won'] is False
            log = LandAttackLog.query.filter_by(land_id=land.id).first()
            assert log is not None
            assert log.card_lost_suit is not None
            assert log.card_lost_rank is not None

            # Land ownership unchanged (still unowned)
            db.session.refresh(land)
            assert land.owner_user_id is None

    def test_player_defender_win_reports_loot_and_consumed_cards(self, app, db):
        """Defender win payload includes looted and consumed card lists."""
        with app.app_context():
            from routes.games import _resolve_conquer_battle

            attacker = _make_user(db, username='attacker_cards')
            defender = _make_user(db, username='defender_cards')
            land = _make_land(db, tier=2, owner_user_id=defender.id)

            atk_cfg = _make_conquer_config(db, attacker, land)
            prelude_card = CollectionCard(
                user_id=attacker.id,
                suit='Diamonds',
                rank='Q',
                value=2,
                locked=True,
                lock_type='conquer_prelude',
                lock_ref_id=atk_cfg.id,
            )
            db.session.add(prelude_card)
            db.session.flush()
            prelude_card_id = prelude_card.id
            atk_cfg.prelude_spell_name = 'Poison'
            atk_cfg.prelude_spell_card_ids = [prelude_card_id]
            db.session.commit()
            _make_defence_config(db, defender, land)

            client = app.test_client()
            headers = _auth_headers(app, attacker)
            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=headers)
            data = resp.get_json()
            game = db.session.get(Game, data['game_id'])

            atk_player = db.session.get(Player, game.invader_player_id)
            def_player = [p for p in game.players if p.id != atk_player.id][0]

            result = _resolve_conquer_battle(game, def_player, atk_player)
            db.session.commit()

            assert result['conquer_result'] == 'defender_won'

            loot_cards = result.get('loot_lost_cards') or []
            consumed_cards = result.get('consumed_cards') or []
            assert len(loot_cards) == 1
            assert len(consumed_cards) >= 1
            assert result.get('cards_spent') == (len(loot_cards) + len(consumed_cards))

            loot_pair = (loot_cards[0].get('suit'), loot_cards[0].get('rank'))
            consumed_pairs = {(c.get('suit'), c.get('rank')) for c in consumed_cards}
            assert loot_pair == ('Diamonds', 'J')
            assert loot_pair not in consumed_pairs
            assert ('Diamonds', 'Q') in consumed_pairs
            assert db.session.get(CollectionCard, prelude_card_id) is None

            defender_cards = CollectionCard.query.filter_by(user_id=defender.id, locked=False).all()
            assert any((c.suit, c.rank) == loot_pair for c in defender_cards)

    def test_attacker_win_consumes_old_defence_battle_and_spell_cards(self, app, db):
        """Defence battle/spell cards are consumed only when the land falls."""
        with app.app_context():
            from routes.games import _resolve_conquer_battle

            attacker = _make_user(db, username='attacker_takes_land')
            defender = _make_user(db, username='defender_loses_land')
            land = _make_land(db, tier=2, owner_user_id=defender.id)

            _make_conquer_config(db, attacker, land)
            def_cfg = _make_defence_config(db, defender, land)
            move_card_id = def_cfg.battle_moves[0].card_id
            counter_card = CollectionCard(
                user_id=defender.id,
                suit='Hearts',
                rank='3',
                value=3,
                locked=True,
                lock_type='defence_counter',
                lock_ref_id=def_cfg.id,
            )
            db.session.add(counter_card)
            db.session.flush()
            counter_card_id = counter_card.id
            def_cfg.counter_spell_name = 'Poison'
            def_cfg.counter_spell_card_ids = [counter_card_id]
            db.session.commit()

            client = app.test_client()
            headers = _auth_headers(app, attacker)
            resp = client.post('/kingdom/conquer/start_battle',
                               json={'land_id': land.id}, headers=headers)
            data = resp.get_json()
            game = db.session.get(Game, data['game_id'])

            atk_player = db.session.get(Player, game.invader_player_id)
            result = _resolve_conquer_battle(game, atk_player, atk_player)
            db.session.commit()

            assert result['conquer_result'] == 'attacker_won'
            assert (result['card_won_suit'], result['card_won_rank']) == ('Spades', 'K')
            assert db.session.get(CollectionCard, move_card_id) is None
            assert db.session.get(CollectionCard, counter_card_id) is None
            defence_consumed = result.get('defence_consumed_cards') or []
            consumed_pairs = {(c.get('suit'), c.get('rank')) for c in defence_consumed}
            assert ('Spades', '8') in consumed_pairs
            assert ('Hearts', '3') in consumed_pairs

    def test_attacker_wins_config_converted_to_defence(self, app, db):
        """Attacker's conquer config becomes the new defence config."""
        with app.app_context():
            result, user, land, game, cfg = self._start_battle_and_resolve(
                app, db, attacker_wins=True)

            db.session.refresh(cfg)
            assert cfg.config_type == 'defence'
            db.session.refresh(land)
            assert land.defence_config_id == cfg.id
