# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Regression tests for end-of-conquer-battle card lock / consumption.

Covers the helpers added in the card-lock cleanup pass:
- ``_consume_config_battle_cards`` consumes battle/modifier/spell cards
- ``_destroy_land_config`` deletes every remaining card on attacker loss
- ``_rekey_config_lock_types`` re-keys conquer_* → defence_* on attacker win
- defence-compatible preludes remain committed after an attacker win
- ``_wipe_land_config`` unlocks (does not delete) every referenced card
"""
import pickle
from types import SimpleNamespace

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


class TestConfigBattleCardIds:
    def test_route_reexports_canonical_transition_helper(self):
        from game_service.conquer_config_transition import (
            _config_battle_card_ids as canonical_helper,
        )
        from routes.games import _config_battle_card_ids as legacy_helper

        assert legacy_helper is canonical_helper
        assert canonical_helper.__module__ == 'routes.games'
        assert pickle.loads(pickle.dumps(canonical_helper)) is canonical_helper

    def test_none_config_returns_empty_list(self):
        from routes.games import _config_battle_card_ids

        assert _config_battle_card_ids(None) == []

    def test_preserves_source_order_duplicates_and_skips_empty_move_ids(self):
        from routes.games import _config_battle_card_ids

        cfg = SimpleNamespace(
            battle_moves=[
                SimpleNamespace(card_id=11),
                SimpleNamespace(card_id=None),
                SimpleNamespace(card_id=12),
            ],
            modifier_card_ids=[13, 11],
            spell_card_ids=[14],
            prelude_spell_card_ids=None,
            counter_spell_card_ids=[15],
        )

        assert _config_battle_card_ids(cfg) == [
            11,
            12,
            13,
            11,
            14,
            15,
        ]


class TestConsumeConfigBattleCards:
    def test_route_reexports_canonical_transition_helper(self):
        from game_service.conquer_config_transition import (
            _consume_config_battle_cards as canonical_helper,
        )
        from routes.games import _consume_config_battle_cards as legacy_helper

        assert legacy_helper is canonical_helper
        assert canonical_helper.__module__ == 'routes.games'
        assert pickle.loads(pickle.dumps(canonical_helper)) is canonical_helper

    def test_consumes_spell_arrays(self, app, db, two_users):
        from routes.games import _consume_config_battle_cards
        from models import CollectionCard, LandConfigBattleMove
        u, _ = two_users
        cfg = _mk_config(db, u.id)

        move = _mk_card(db, u.id, rank='8', value=8,
                        lock_type='conquer_move', lock_ref_id=cfg.id)
        modifier = _mk_card(db, u.id, rank='2', value=2,
                            lock_type='conquer_modifier',
                            lock_ref_id=cfg.id)
        spell = _mk_card(db, u.id, rank='K', lock_type='conquer_spell',
                         lock_ref_id=cfg.id)
        prelude = _mk_card(db, u.id, rank='Q', lock_type='conquer_prelude',
                           lock_ref_id=cfg.id)
        counter = _mk_card(db, u.id, rank='J', lock_type='conquer_counter',
                           lock_ref_id=cfg.id)
        db.session.add(LandConfigBattleMove(
            config_id=cfg.id,
            family_name='Dagger',
            card_id=move.id,
            suit='spades',
            rank='8',
            value=8,
            round_index=0,
        ))
        cfg.battle_modifier = {'type': 'Blitzkrieg'}
        cfg.modifier_card_ids = [modifier.id]
        cfg.spell_card_ids = [spell.id]
        cfg.prelude_spell_card_ids = [prelude.id]
        cfg.counter_spell_card_ids = [counter.id]
        cfg.spell_name = 'health_boost'
        cfg.prelude_spell_name = 'spy'
        cfg.counter_spell_name = 'lightning'
        db.session.commit()
        cfg_id = cfg.id
        consumed_ids = [
            move.id,
            modifier.id,
            spell.id,
            prelude.id,
            counter.id,
        ]

        _consume_config_battle_cards(cfg)
        db.session.commit()

        for cid in consumed_ids:
            assert db.session.get(CollectionCard, cid) is None
        assert LandConfigBattleMove.query.filter_by(config_id=cfg_id).count() == 0

        # Stale references on the cfg are cleared (re-fetch after commit)
        from models import LandConfig
        cfg2 = db.session.get(LandConfig, cfg_id)
        assert (cfg2.modifier_card_ids or []) == []
        assert (cfg2.spell_card_ids or []) == []
        assert (cfg2.prelude_spell_card_ids or []) == []
        assert (cfg2.counter_spell_card_ids or []) == []
        assert cfg2.spell_name is None
        assert cfg2.prelude_spell_name is None
        assert cfg2.counter_spell_name is None
        assert cfg2.battle_modifier == {'type': 'Blitzkrieg'}


class TestDestroyLandConfig:
    def test_route_reexports_canonical_transition_helper(self):
        from game_service.conquer_config_transition import (
            _destroy_land_config as canonical_helper,
        )
        from routes.games import _destroy_land_config as legacy_helper

        assert legacy_helper is canonical_helper
        assert canonical_helper.__module__ == 'routes.games'
        assert pickle.loads(pickle.dumps(canonical_helper)) is canonical_helper

    def test_deletes_all_cards_and_cfg(self, app, db, two_users):
        from routes.games import _destroy_land_config
        from models import (
            CollectionCard,
            LandConfig,
            LandConfigBattleMove,
            LandConfigFigure,
        )
        u, _ = two_users
        cfg = _mk_config(db, u.id)

        c1 = _mk_card(db, u.id, rank='A', lock_type='conquer_figure')
        c2 = _mk_card(db, u.id, rank='K', lock_type='conquer_figure')
        c_move = _mk_card(
            db, u.id, rank='8', value=8, lock_type='conquer_move')
        c_modifier = _mk_card(
            db, u.id, rank='2', value=2, lock_type='conquer_modifier')
        c_spell = _mk_card(
            db, u.id, rank='3', value=3, lock_type='conquer_spell')
        c_prelude = _mk_card(
            db, u.id, rank='4', value=4, lock_type='conquer_prelude')
        c_counter = _mk_card(
            db, u.id, rank='5', value=5, lock_type='conquer_counter')
        fig = LandConfigFigure(
            config_id=cfg.id, family_name='F', name='F', suit='spades',
            color='spades', field='north', card_ids=[c1.id, c2.id],
            card_roles=['key', 'support'],
        )
        db.session.add(fig)
        db.session.add(LandConfigBattleMove(
            config_id=cfg.id,
            family_name='Dagger',
            card_id=c_move.id,
            suit='spades',
            rank='8',
            value=8,
            round_index=0,
        ))
        cfg.modifier_card_ids = [c_modifier.id]
        cfg.spell_card_ids = [c_spell.id]
        cfg.prelude_spell_card_ids = [c_prelude.id]
        cfg.counter_spell_card_ids = [c_counter.id]
        db.session.commit()
        cfg_id = cfg.id
        consumed_ids = [
            c1.id,
            c2.id,
            c_move.id,
            c_modifier.id,
            c_spell.id,
            c_prelude.id,
            c_counter.id,
        ]

        _destroy_land_config(cfg)
        db.session.commit()

        for cid in consumed_ids:
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

    def test_clears_foreign_key_references_before_deleting(
            self, app, db, two_users):
        from routes.games import _destroy_land_config
        from models import Game, Land, LandConfig, LandConfigFigure

        user, _ = two_users
        cfg = _mk_config(db, user.id)
        figure = LandConfigFigure(
            config_id=cfg.id,
            family_name='F',
            name='F',
            suit='spades',
            color='offensive',
            field='village',
            card_ids=[],
            card_roles=[],
        )
        db.session.add(figure)
        db.session.flush()
        cfg.battle_figure_id = figure.id

        game = Game(
            mode='conquer',
            state='finished',
            conquer_config_id=cfg.id,
            defence_config_id=cfg.id,
        )
        land = Land(
            col=999,
            row=999,
            tier=1,
            gold_rate=1.0,
            suit_bonus_suit='Hearts',
            suit_bonus_value=1,
            defence_config_id=cfg.id,
        )
        derived = LandConfig(
            user_id=user.id,
            config_type='conquer',
            base_config_id=cfg.id,
        )
        db.session.add_all([game, land, derived])
        db.session.commit()
        cfg_id = cfg.id
        game_id = game.id
        land_id = land.id
        derived_id = derived.id

        _destroy_land_config(cfg)
        db.session.commit()

        assert db.session.get(LandConfig, cfg_id) is None
        assert db.session.get(Game, game_id).conquer_config_id is None
        assert db.session.get(Game, game_id).defence_config_id is None
        assert db.session.get(Land, land_id).defence_config_id is None
        assert db.session.get(LandConfig, derived_id).base_config_id is None


class TestWipeLandConfigReturnUnlooted:
    def test_route_reexports_canonical_transition_helper(self):
        from game_service.conquer_config_transition import (
            _wipe_land_config_return_unlooted as canonical_helper,
        )
        from routes.games import (
            _wipe_land_config_return_unlooted as legacy_helper,
        )

        assert legacy_helper is canonical_helper
        assert canonical_helper.__module__ == 'routes.games'
        assert pickle.loads(pickle.dumps(canonical_helper)) is canonical_helper

    def test_deletes_looted_cards_unlocks_rest_and_removes_config(
            self, app, db, two_users):
        from routes.games import _wipe_land_config_return_unlooted
        from models import (
            CollectionCard,
            LandConfig,
            LandConfigBattleMove,
            LandConfigFigure,
        )
        u, _ = two_users
        cfg = _mk_config(db, u.id)
        looted_figure = _mk_card(
            db, u.id, rank='A', lock_type='defence_figure',
            lock_ref_id=cfg.id,
        )
        kept_figure = _mk_card(
            db, u.id, rank='K', lock_type='defence_figure',
            lock_ref_id=cfg.id,
        )
        kept_move = _mk_card(
            db, u.id, rank='8', value=8, lock_type='defence_move',
            lock_ref_id=cfg.id,
        )
        looted_modifier = _mk_card(
            db, u.id, rank='2', value=2, lock_type='defence_modifier',
            lock_ref_id=cfg.id,
        )
        kept_spell = _mk_card(
            db, u.id, rank='3', value=3, lock_type='defence_spell',
            lock_ref_id=cfg.id,
        )
        kept_prelude = _mk_card(
            db, u.id, rank='4', value=4, lock_type='defence_prelude',
            lock_ref_id=cfg.id,
        )
        kept_counter = _mk_card(
            db, u.id, rank='5', value=5, lock_type='defence_counter',
            lock_ref_id=cfg.id,
        )
        db.session.add(LandConfigFigure(
            config_id=cfg.id,
            family_name='F',
            name='F',
            suit='spades',
            color='defensive',
            field='village',
            card_ids=[looted_figure.id, kept_figure.id],
            card_roles=['key', 'number'],
        ))
        db.session.add(LandConfigBattleMove(
            config_id=cfg.id,
            family_name='Dagger',
            card_id=kept_move.id,
            suit='spades',
            rank='8',
            value=8,
            round_index=0,
        ))
        cfg.modifier_card_ids = [looted_modifier.id]
        cfg.spell_card_ids = [kept_spell.id]
        cfg.prelude_spell_card_ids = [kept_prelude.id]
        cfg.counter_spell_card_ids = [kept_counter.id]
        db.session.commit()
        cfg_id = cfg.id
        looted_ids = [looted_figure.id, looted_modifier.id]
        returned_ids = [
            kept_figure.id,
            kept_move.id,
            kept_spell.id,
            kept_prelude.id,
            kept_counter.id,
        ]

        _wipe_land_config_return_unlooted(cfg, looted_ids)
        db.session.commit()

        assert db.session.get(LandConfig, cfg_id) is None
        assert LandConfigFigure.query.filter_by(config_id=cfg_id).count() == 0
        assert LandConfigBattleMove.query.filter_by(config_id=cfg_id).count() == 0
        for card_id in looted_ids:
            assert db.session.get(CollectionCard, card_id) is None
        for card_id in returned_ids:
            returned = db.session.get(CollectionCard, card_id)
            assert returned.locked is False
            assert returned.lock_type is None
            assert returned.lock_ref_id is None


class TestWipeLandConfig:
    def test_route_reexports_canonical_transition_helper(self):
        from game_service.conquer_config_transition import (
            _wipe_land_config as canonical_helper,
        )
        from routes.games import _wipe_land_config as legacy_helper

        assert legacy_helper is canonical_helper
        assert canonical_helper.__module__ == 'routes.games'
        assert pickle.loads(pickle.dumps(canonical_helper)) is canonical_helper

    def test_unlocks_every_card_source_and_removes_config(
            self, app, db, two_users):
        from routes.games import _wipe_land_config
        from models import (
            CollectionCard,
            LandConfig,
            LandConfigBattleMove,
            LandConfigFigure,
        )
        u, _ = two_users
        cfg = _mk_config(db, u.id)
        figure_card = _mk_card(
            db, u.id, rank='A', lock_type='conquer_figure',
            lock_ref_id=cfg.id,
        )
        move_card = _mk_card(
            db, u.id, rank='8', value=8, lock_type='conquer_move',
            lock_ref_id=cfg.id,
        )
        modifier_card = _mk_card(
            db, u.id, rank='2', value=2, lock_type='conquer_modifier',
            lock_ref_id=cfg.id,
        )
        spell_card = _mk_card(
            db, u.id, rank='3', value=3, lock_type='conquer_spell',
            lock_ref_id=cfg.id,
        )
        prelude_card = _mk_card(
            db, u.id, rank='4', value=4, lock_type='conquer_prelude',
            lock_ref_id=cfg.id,
        )
        counter_card = _mk_card(
            db, u.id, rank='5', value=5, lock_type='conquer_counter',
            lock_ref_id=cfg.id,
        )
        db.session.add(LandConfigFigure(
            config_id=cfg.id,
            family_name='F',
            name='F',
            suit='spades',
            color='offensive',
            field='village',
            card_ids=[figure_card.id],
            card_roles=['key'],
        ))
        db.session.add(LandConfigBattleMove(
            config_id=cfg.id,
            family_name='Dagger',
            card_id=move_card.id,
            suit='spades',
            rank='8',
            value=8,
            round_index=0,
        ))
        cfg.modifier_card_ids = [modifier_card.id]
        cfg.spell_card_ids = [spell_card.id]
        cfg.prelude_spell_card_ids = [prelude_card.id]
        cfg.counter_spell_card_ids = [counter_card.id]
        db.session.commit()
        cfg_id = cfg.id
        returned_ids = [
            figure_card.id,
            move_card.id,
            modifier_card.id,
            spell_card.id,
            prelude_card.id,
            counter_card.id,
        ]

        _wipe_land_config(cfg)
        db.session.commit()

        assert db.session.get(LandConfig, cfg_id) is None
        assert LandConfigFigure.query.filter_by(config_id=cfg_id).count() == 0
        assert LandConfigBattleMove.query.filter_by(config_id=cfg_id).count() == 0
        for card_id in returned_ids:
            returned = db.session.get(CollectionCard, card_id)
            assert returned is not None
            assert returned.locked is False
            assert returned.lock_type is None
            assert returned.lock_ref_id is None


class TestRekeyConfigLockTypes:
    def test_route_reexports_canonical_transition_helper(self):
        from game_service.conquer_config_transition import (
            _rekey_config_lock_types as canonical_helper,
        )
        from routes.games import _rekey_config_lock_types as legacy_helper

        assert legacy_helper is canonical_helper
        assert canonical_helper.__module__ == 'routes.games'
        assert pickle.loads(pickle.dumps(canonical_helper)) is canonical_helper

    def test_rekeys_modifier_spell_and_counter_but_leaves_unknown_lock(
            self, app, db, two_users):
        from routes.games import _rekey_config_lock_types
        from models import CollectionCard
        u, _ = two_users
        cfg = _mk_config(db, u.id)
        modifier = _mk_card(
            db,
            u.id,
            rank='2',
            lock_type='conquer_modifier',
            lock_ref_id=cfg.id,
        )
        spell = _mk_card(
            db,
            u.id,
            rank='3',
            lock_type='conquer_spell',
            lock_ref_id=cfg.id,
        )
        counter = _mk_card(
            db,
            u.id,
            rank='4',
            lock_type='conquer_counter',
            lock_ref_id=cfg.id,
        )
        unknown = _mk_card(
            db,
            u.id,
            rank='5',
            lock_type='legacy_custom',
            lock_ref_id=cfg.id,
        )
        cfg.modifier_card_ids = [modifier.id, unknown.id]
        cfg.spell_card_ids = [spell.id]
        cfg.counter_spell_card_ids = [counter.id]
        db.session.commit()

        _rekey_config_lock_types(cfg, 'defence')
        db.session.commit()

        assert db.session.get(
            CollectionCard,
            modifier.id,
        ).lock_type == 'defence_modifier'
        assert db.session.get(
            CollectionCard,
            spell.id,
        ).lock_type == 'defence_spell'
        assert db.session.get(
            CollectionCard,
            counter.id,
        ).lock_type == 'defence_counter'
        unchanged = db.session.get(CollectionCard, unknown.id)
        assert unchanged.lock_type == 'legacy_custom'
        assert unchanged.lock_ref_id == cfg.id

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

    def test_rekeys_battle_move_cards(self, app, db, two_users):
        # Tactics carry over into the converted defence, so their card locks
        # must be re-keyed conquer_move -> defence_move alongside figures.
        from routes.games import _rekey_config_lock_types
        from models import CollectionCard, LandConfigBattleMove
        u, _ = two_users
        cfg = _mk_config(db, u.id)
        move_card = _mk_card(db, u.id, rank='8', value=8,
                             lock_type='conquer_move', lock_ref_id=1)
        db.session.add(LandConfigBattleMove(
            config_id=cfg.id, family_name='Dagger', card_id=move_card.id,
            suit='spades', rank='8', value=8, round_index=0))
        db.session.commit()

        _rekey_config_lock_types(cfg, 'defence')
        db.session.commit()

        assert db.session.get(CollectionCard, move_card.id).lock_type == 'defence_move'

    def test_rekeys_transferred_prelude_cards(self, app, db, two_users):
        from routes.games import _rekey_config_lock_types
        from models import CollectionCard
        u, _ = two_users
        cfg = _mk_config(db, u.id)
        prelude = _mk_card(
            db,
            u.id,
            rank='8',
            lock_type='conquer_prelude',
            lock_ref_id=cfg.id,
        )
        cfg.prelude_spell_name = 'Draw 2 MainCards'
        cfg.prelude_spell_card_ids = [prelude.id]
        db.session.commit()

        _rekey_config_lock_types(cfg, 'defence')
        db.session.commit()

        kept = db.session.get(CollectionCard, prelude.id)
        assert kept.locked is True
        assert kept.lock_type == 'defence_prelude'
        assert kept.lock_ref_id == cfg.id


class TestReturnConfigAttackOnlyCards:
    def test_route_reexports_canonical_transition_helper(self):
        from game_service.conquer_config_transition import (
            _return_config_attack_only_cards as canonical_helper,
        )
        from routes.games import (
            _return_config_attack_only_cards as legacy_helper,
        )

        assert legacy_helper is canonical_helper
        assert canonical_helper.__module__ == 'routes.games'
        assert pickle.loads(pickle.dumps(canonical_helper)) is canonical_helper

    def test_clears_and_unlocks_modifier_spell_and_counter_state(
            self, app, db, two_users):
        from routes.games import _return_config_attack_only_cards
        from models import CollectionCard
        u, _ = two_users
        cfg = _mk_config(db, u.id)
        modifier = _mk_card(
            db,
            u.id,
            rank='2',
            lock_type='conquer_modifier',
            lock_ref_id=cfg.id,
        )
        spell = _mk_card(
            db,
            u.id,
            rank='3',
            lock_type='conquer_spell',
            lock_ref_id=cfg.id,
        )
        counter = _mk_card(
            db,
            u.id,
            rank='4',
            lock_type='conquer_counter',
            lock_ref_id=cfg.id,
        )
        cfg.battle_modifier = {'type': 'Blitzkrieg'}
        cfg.modifier_card_ids = [modifier.id]
        cfg.spell_name = 'Health Boost'
        cfg.spell_target_figure_id = 73
        cfg.spell_card_ids = [spell.id]
        cfg.counter_spell_name = 'Block Spell'
        cfg.counter_spell_data = {'source': 'characterization'}
        cfg.counter_spell_card_ids = [counter.id]
        cfg.counter_spell_target_figure_id = 91
        db.session.commit()
        returned_card_ids = [modifier.id, spell.id, counter.id]

        _return_config_attack_only_cards(cfg)
        db.session.commit()

        for card_id in returned_card_ids:
            returned = db.session.get(CollectionCard, card_id)
            assert returned.locked is False
            assert returned.lock_type is None
            assert returned.lock_ref_id is None
        assert cfg.battle_modifier is None
        assert cfg.modifier_card_ids == []
        assert cfg.spell_name is None
        assert cfg.spell_target_figure_id is None
        assert cfg.spell_card_ids == []
        assert cfg.counter_spell_name is None
        assert cfg.counter_spell_data is None
        assert cfg.counter_spell_card_ids == []
        assert cfg.counter_spell_target_figure_id is None

    def test_keeps_battle_moves_and_returns_attack_only_cards(self, app, db, two_users):
        # The winning attack becomes the new defence: figures + tactics stay
        # committed; conquer-only preludes and other attack-only cards return.
        from routes.games import _return_config_attack_only_cards
        from models import CollectionCard, LandConfigBattleMove
        u, _ = two_users
        cfg = _mk_config(db, u.id)
        move_card = _mk_card(db, u.id, rank='8', value=8,
                             lock_type='conquer_move', lock_ref_id=1)
        db.session.add(LandConfigBattleMove(
            config_id=cfg.id, family_name='Dagger', card_id=move_card.id,
            suit='spades', rank='8', value=8, round_index=0))
        prelude = _mk_card(db, u.id, rank='A', lock_type='conquer_prelude',
                           lock_ref_id=cfg.id)
        cfg.prelude_spell_card_ids = [prelude.id]
        cfg.prelude_spell_name = 'Invader Swap'
        db.session.commit()
        move_card_id, prelude_id = move_card.id, prelude.id

        _return_config_attack_only_cards(cfg)
        db.session.commit()

        # Tactic survives and stays locked; the prelude card is returned.
        assert LandConfigBattleMove.query.filter_by(config_id=cfg.id).count() == 1
        kept = db.session.get(CollectionCard, move_card_id)
        assert kept is not None and kept.locked is True
        returned = db.session.get(CollectionCard, prelude_id)
        assert returned.locked is False and returned.lock_type is None
        assert (cfg.prelude_spell_card_ids or []) == []
        assert cfg.prelude_spell_name is None

    def test_keeps_defence_compatible_prelude(self, app, db, two_users):
        from routes.games import _return_config_attack_only_cards
        from models import CollectionCard
        u, _ = two_users
        cfg = _mk_config(db, u.id)
        prelude = _mk_card(
            db,
            u.id,
            rank='8',
            lock_type='conquer_prelude',
            lock_ref_id=cfg.id,
        )
        cfg.prelude_spell_name = 'Draw 2 MainCards'
        cfg.prelude_spell_data = {'note': 'keep'}
        cfg.prelude_spell_card_ids = [prelude.id]
        db.session.commit()

        _return_config_attack_only_cards(cfg)
        db.session.commit()

        kept = db.session.get(CollectionCard, prelude.id)
        assert kept.locked is True
        assert kept.lock_type == 'conquer_prelude'
        assert cfg.prelude_spell_name == 'Draw 2 MainCards'
        assert cfg.prelude_spell_data == {'note': 'keep'}
        assert cfg.prelude_spell_card_ids == [prelude.id]


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
