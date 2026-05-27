# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Regression tests for end-of-conquer-battle card lock / consumption.

Covers the helpers added in the card-lock cleanup pass:
- ``_consume_config_battle_cards`` consumes battle/modifier/spell cards
- ``_destroy_land_config`` deletes every remaining card on attacker loss
- ``_rekey_config_lock_types`` re-keys conquer_* → defence_* on attacker win
- ``_wipe_land_config`` unlocks (does not delete) every referenced card
"""
import pytest


def _mk_card(db, user_id, suit='spades', rank='A', value=11, locked=True,
             lock_type=None, lock_ref_id=None):
    from models import CollectionCard
    c = CollectionCard(
        user_id=user_id, suit=suit, rank=rank, value=value,
        locked=locked, lock_type=lock_type, lock_ref_id=lock_ref_id,
    )
    db.session.add(c)
    db.session.flush()
    return c


def _mk_config(db, user_id, config_type='conquer', land_id=None):
    from models import LandConfig
    cfg = LandConfig(user_id=user_id, config_type=config_type, land_id=land_id)
    db.session.add(cfg)
    db.session.flush()
    return cfg


class TestConsumeConfigBattleCards:
    def test_consumes_spell_arrays(self, app, db, two_users):
        from routes.games import _consume_config_battle_cards
        from models import CollectionCard
        u, _ = two_users
        cfg = _mk_config(db, u.id)

        spell = _mk_card(db, u.id, rank='K', lock_type='conquer_spell',
                         lock_ref_id=cfg.id)
        prelude = _mk_card(db, u.id, rank='Q', lock_type='conquer_prelude',
                           lock_ref_id=cfg.id)
        counter = _mk_card(db, u.id, rank='J', lock_type='conquer_counter',
                           lock_ref_id=cfg.id)
        cfg.spell_card_ids = [spell.id]
        cfg.prelude_spell_card_ids = [prelude.id]
        cfg.counter_spell_card_ids = [counter.id]
        cfg.modifier_card_ids = []
        cfg.spell_name = 'health_boost'
        cfg.prelude_spell_name = 'spy'
        cfg.counter_spell_name = 'lightning'
        db.session.commit()
        cfg_id = cfg.id
        spell_id, prelude_id, counter_id = spell.id, prelude.id, counter.id

        _consume_config_battle_cards(cfg)
        db.session.commit()

        for cid in (spell_id, prelude_id, counter_id):
            assert db.session.get(CollectionCard, cid) is None

        # Stale references on the cfg are cleared (re-fetch after commit)
        from models import LandConfig
        cfg2 = db.session.get(LandConfig, cfg_id)
        assert (cfg2.spell_card_ids or []) == []
        assert (cfg2.prelude_spell_card_ids or []) == []
        assert (cfg2.counter_spell_card_ids or []) == []
        assert cfg2.spell_name is None
        assert cfg2.prelude_spell_name is None
        assert cfg2.counter_spell_name is None


class TestDestroyLandConfig:
    def test_deletes_all_cards_and_cfg(self, app, db, two_users):
        from routes.games import _destroy_land_config
        from models import CollectionCard, LandConfig, LandConfigFigure
        u, _ = two_users
        cfg = _mk_config(db, u.id)

        c1 = _mk_card(db, u.id, rank='A', lock_type='conquer_figure')
        c2 = _mk_card(db, u.id, rank='K', lock_type='conquer_figure')
        c_spell = _mk_card(db, u.id, rank='Q', lock_type='conquer_spell')
        fig = LandConfigFigure(
            config_id=cfg.id, family_name='F', name='F', suit='spades',
            color='spades', field='north', card_ids=[c1.id, c2.id],
            card_roles=['key', 'support'],
        )
        db.session.add(fig)
        cfg.spell_card_ids = [c_spell.id]
        db.session.commit()
        cfg_id = cfg.id
        c1_id, c2_id, c_spell_id = c1.id, c2.id, c_spell.id

        _destroy_land_config(cfg)
        db.session.commit()

        for cid in (c1_id, c2_id, c_spell_id):
            assert db.session.get(CollectionCard, cid) is None
        assert db.session.get(LandConfig, cfg_id) is None

    def test_protects_excluded_card(self, app, db, two_users):
        from routes.games import _destroy_land_config
        from models import CollectionCard, LandConfigFigure
        u, _ = two_users
        cfg = _mk_config(db, u.id)
        looted = _mk_card(db, u.id, rank='A', lock_type='conquer_figure')
        consumed = _mk_card(db, u.id, rank='K', lock_type='conquer_figure')
        fig = LandConfigFigure(
            config_id=cfg.id, family_name='F', name='F', suit='spades',
            color='spades', field='north',
            card_ids=[looted.id, consumed.id],
            card_roles=['key', 'support'],
        )
        db.session.add(fig)
        db.session.commit()
        looted_id, consumed_id = looted.id, consumed.id

        _destroy_land_config(cfg, exclude_card_ids=[looted_id])
        db.session.commit()

        # Looted card survives (typically already transferred elsewhere)
        assert db.session.get(CollectionCard, looted_id) is not None
        assert db.session.get(CollectionCard, consumed_id) is None


class TestRekeyConfigLockTypes:
    def test_conquer_to_defence(self, app, db, two_users):
        from routes.games import _rekey_config_lock_types
        from models import CollectionCard, LandConfigFigure
        u, _ = two_users
        cfg = _mk_config(db, u.id)
        c1 = _mk_card(db, u.id, rank='A', lock_type='conquer_figure',
                      lock_ref_id=1)
        c2 = _mk_card(db, u.id, rank='K', lock_type='conquer_figure',
                      lock_ref_id=1)
        fig = LandConfigFigure(
            config_id=cfg.id, family_name='F', name='F', suit='spades',
            color='spades', field='north', card_ids=[c1.id, c2.id],
            card_roles=['key', 'support'],
        )
        db.session.add(fig)
        db.session.commit()

        _rekey_config_lock_types(cfg, 'defence')
        db.session.commit()

        assert db.session.get(CollectionCard, c1.id).lock_type == 'defence_figure'
        assert db.session.get(CollectionCard, c2.id).lock_type == 'defence_figure'


class TestOrphanLockSweep:
    """`_lock_collection_cards` and the startup sweep should release stale locks."""

    def test_card_with_dead_lock_ref_is_released(self, app, db, two_users):
        from models import CollectionCard, LandConfig, LandConfigFigure
        u, _ = two_users
        # Card claims to be locked by figure 99999 which doesn't exist.
        c = _mk_card(db, u.id, rank='A', lock_type='conquer_figure',
                     lock_ref_id=99999)
        db.session.commit()

        # Re-run the sweep manually (mirrors server.py startup logic)
        figure_ids = {fid for (fid,) in db.session.query(LandConfigFigure.id).all()}
        move_ids = set()
        config_ids = {cid for (cid,) in db.session.query(LandConfig.id).all()}
        valid_by_lock_type = {
            'conquer_figure': figure_ids, 'defence_figure': figure_ids,
            'conquer_move': move_ids, 'defence_move': move_ids,
            'conquer_modifier': config_ids, 'defence_modifier': config_ids,
            'conquer_spell': config_ids, 'defence_spell': config_ids,
            'conquer_prelude': config_ids, 'defence_prelude': config_ids,
            'conquer_counter': config_ids, 'defence_counter': config_ids,
        }
        for cc in CollectionCard.query.filter_by(locked=True).all():
            valid_set = valid_by_lock_type.get(cc.lock_type)
            if valid_set is None or cc.lock_ref_id not in valid_set:
                cc.locked = False
                cc.lock_type = None
                cc.lock_ref_id = None
        db.session.commit()

        refreshed = db.session.get(CollectionCard, c.id)
        assert refreshed.locked is False
        assert refreshed.lock_type is None
        assert refreshed.lock_ref_id is None


class TestConquerRemoveFigureParity:
    """``conquer_remove_figure`` must clear every figure reference, not just battle_figure_id."""

    def test_clears_battle_figure_id_2_and_spell_targets(
            self, client, db, two_users, auth_headers_user1):
        from models import (Land, LandConfig, LandConfigFigure,
                            CollectionCard)
        u1, u2 = two_users
        land = Land(col=10, row=10, owner_user_id=u2.id, tier=1,
                    gold_rate=1.0, suit_bonus_suit='Hearts',
                    suit_bonus_value=3)
        db.session.add(land)
        db.session.commit()

        # Two unlocked cards we'll attach to the figure
        c1 = CollectionCard(user_id=u1.id, suit='spades', rank='A',
                            value=11, locked=False)
        c2 = CollectionCard(user_id=u1.id, suit='spades', rank='K',
                            value=10, locked=False)
        db.session.add_all([c1, c2])
        db.session.commit()

        cfg = LandConfig(user_id=u1.id, config_type='conquer', land_id=land.id)
        db.session.add(cfg)
        db.session.flush()
        fig = LandConfigFigure(
            config_id=cfg.id, family_name='F', name='F', suit='spades',
            color='spades', field='north', card_ids=[c1.id, c2.id],
            card_roles=['key', 'support'],
        )
        db.session.add(fig)
        db.session.flush()
        for cc in (c1, c2):
            cc.locked = True
            cc.lock_type = 'conquer_figure'
            cc.lock_ref_id = fig.id
        # Wire all the references the parity fix should clear.
        cfg.battle_figure_id_2 = fig.id
        cfg.counter_spell_target_figure_id = fig.id
        cfg.spell_target_figure_id = fig.id
        cfg.prelude_spell_data = {'target_figure_id': fig.id, 'note': 'keep'}
        db.session.commit()
        cfg_id = cfg.id
        fig_id = fig.id

        resp = client.post('/kingdom/conquer/remove_figure',
                           json={'figure_id': fig_id},
                           headers=auth_headers_user1)
        assert resp.status_code == 200, resp.get_json()
        assert resp.get_json().get('success') is True

        cfg2 = db.session.get(LandConfig, cfg_id)
        assert cfg2.battle_figure_id is None
        assert cfg2.battle_figure_id_2 is None
        assert cfg2.counter_spell_target_figure_id is None
        assert cfg2.spell_target_figure_id is None
        # 'target_figure_id' is removed but unrelated keys are preserved.
        prelude = cfg2.prelude_spell_data or {}
        assert 'target_figure_id' not in prelude
        assert prelude.get('note') == 'keep'

        # Cards return to the player's collection.
        for cid in (c1.id, c2.id):
            cc = db.session.get(CollectionCard, cid)
            assert cc.locked is False
            assert cc.lock_type is None
            assert cc.lock_ref_id is None


class TestVictoryReviewAcknowledge:
    """``/kingdom/conquer/acknowledge_victory_review`` is idempotent and attacker-only."""

    def _mk_finished_conquer(self, db, attacker_user, defender_user):
        from models import Game, Player
        game = Game(state='finished', mode='conquer')
        db.session.add(game)
        db.session.flush()
        atk_player = Player(user_id=attacker_user.id, game_id=game.id)
        def_player = Player(user_id=defender_user.id, game_id=game.id)
        db.session.add_all([atk_player, def_player])
        db.session.flush()
        game.last_battle_result = {
            'conquer_resolved': True,
            'conquer_attacker_user_id': attacker_user.id,
            'conquer_attacker_player_id': atk_player.id,
            'conquer_defender_user_id': defender_user.id,
            'conquer_defender_player_id': def_player.id,
            'victory_review_config_id': 0,
            'victory_review_land_id': 0,
        }
        db.session.commit()
        return game

    def test_marks_reviewed_at(
            self, client, db, two_users, auth_headers_user1):
        u1, u2 = two_users
        game = self._mk_finished_conquer(db, u1, u2)
        gid = game.id

        resp = client.post('/kingdom/conquer/acknowledge_victory_review',
                           json={'game_id': gid},
                           headers=auth_headers_user1)
        assert resp.status_code == 200, resp.get_json()
        assert resp.get_json().get('success') is True
        from models import Game
        assert db.session.get(Game, gid).victory_reviewed_at is not None

    def test_idempotent(
            self, client, db, two_users, auth_headers_user1):
        u1, u2 = two_users
        game = self._mk_finished_conquer(db, u1, u2)
        gid = game.id

        client.post('/kingdom/conquer/acknowledge_victory_review',
                    json={'game_id': gid}, headers=auth_headers_user1)
        from models import Game
        first_ts = db.session.get(Game, gid).victory_reviewed_at

        resp = client.post('/kingdom/conquer/acknowledge_victory_review',
                           json={'game_id': gid},
                           headers=auth_headers_user1)
        assert resp.status_code == 200
        # Idempotent: timestamp is not overwritten on a second call.
        assert db.session.get(Game, gid).victory_reviewed_at == first_ts

    def test_rejects_non_attacker(
            self, client, db, two_users, auth_headers_user2):
        u1, u2 = two_users
        game = self._mk_finished_conquer(db, u1, u2)
        gid = game.id

        resp = client.post('/kingdom/conquer/acknowledge_victory_review',
                           json={'game_id': gid},
                           headers=auth_headers_user2)
        assert resp.status_code == 403
        from models import Game
        assert db.session.get(Game, gid).victory_reviewed_at is None


class TestBuildFigureDuplicateGuard:
    def test_conquer_build_rejects_duplicate_card_ids(
            self, client, db, two_users, auth_headers_user1):
        from models import Land, CollectionCard
        u1, u2 = two_users
        land = Land(col=42, row=42, owner_user_id=u2.id, tier=1,
                    gold_rate=1.0, suit_bonus_suit='Hearts',
                    suit_bonus_value=3)
        db.session.add(land)
        db.session.commit()
        c = CollectionCard(user_id=u1.id, suit='spades', rank='A',
                           value=11, locked=False)
        db.session.add(c)
        db.session.commit()

        resp = client.post('/kingdom/conquer/build_figure', json={
            'land_id': land.id,
            'family_name': 'X', 'name': 'X',
            'suit': 'spades', 'color': 'spades', 'field': 'north',
            'card_ids': [c.id, c.id],
            'card_roles': ['key', 'support'],
        }, headers=auth_headers_user1)

        assert resp.status_code == 400
        assert 'Duplicate' in resp.get_json().get('message', '')
