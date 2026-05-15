# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for v2.0 database models (CollectionCard, Land, LandConfig, etc.)."""
import pytest
from models import (
    db, User, CollectionCard, Land, LandConfig, LandConfigFigure,
    LandConfigBattleMove, LandAttackLog, Game,
)


# ── CollectionCard ───────────────────────────────────────────────────────────

class TestCollectionCard:
    def test_create_and_serialize(self, db, two_users):
        u1, _ = two_users
        card = CollectionCard(
            user_id=u1.id, suit='Hearts', rank='K', value=4,
        )
        db.session.add(card)
        db.session.commit()

        assert card.id is not None
        d = card.serialize()
        assert d['suit'] == 'Hearts'
        assert d['rank'] == 'K'
        assert d['value'] == 4
        assert d['locked'] is False
        assert d['lock_type'] is None

    def test_lock_card(self, db, two_users):
        u1, _ = two_users
        card = CollectionCard(
            user_id=u1.id, suit='Spades', rank='A', value=3,
            locked=True, lock_type='conquer_figure', lock_ref_id=42,
        )
        db.session.add(card)
        db.session.commit()

        assert card.locked is True
        assert card.lock_type == 'conquer_figure'
        assert card.lock_ref_id == 42

    def test_user_relationship(self, db, two_users):
        u1, u2 = two_users
        db.session.add(CollectionCard(user_id=u1.id, suit='Hearts', rank='7', value=7))
        db.session.add(CollectionCard(user_id=u1.id, suit='Clubs', rank='8', value=8))
        db.session.add(CollectionCard(user_id=u2.id, suit='Diamonds', rank='Q', value=2))
        db.session.commit()

        assert u1.collection_cards.count() == 2
        assert u2.collection_cards.count() == 1


# ── Land ─────────────────────────────────────────────────────────────────────

class TestLand:
    def test_create_and_serialize(self, db):
        land = Land(
            col=3, row=5, tier=2,
            gold_rate=4.5, suit_bonus_suit='Diamonds', suit_bonus_value=3,
        )
        db.session.add(land)
        db.session.commit()

        d = land.serialize()
        assert d['col'] == 3
        assert d['row'] == 5
        assert d['tier'] == 2
        assert d['gold_rate'] == 4.5
        assert d['suit_bonus_suit'] == 'Diamonds'
        assert d['suit_bonus_value'] == 3
        assert d['owner'] is None

    def test_ownership(self, db, two_users):
        u1, _ = two_users
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        land = Land(
            col=0, row=0, tier=1,
            gold_rate=2.0, suit_bonus_suit='Hearts', suit_bonus_value=1,
            owner_user_id=u1.id, owned_since=now,
        )
        db.session.add(land)
        db.session.commit()

        d = land.serialize()
        assert d['owner'] is not None
        assert d['owner']['user_id'] == u1.id
        assert d['owner']['username'] == u1.username

    def test_unique_col_row(self, db):
        db.session.add(Land(col=1, row=1, tier=1, gold_rate=1.0,
                            suit_bonus_suit='Hearts', suit_bonus_value=1))
        db.session.commit()
        db.session.add(Land(col=1, row=1, tier=2, gold_rate=2.0,
                            suit_bonus_suit='Clubs', suit_bonus_value=2))
        with pytest.raises(Exception):  # IntegrityError
            db.session.commit()
        db.session.rollback()


# ── LandConfig + Figures + Moves ─────────────────────────────────────────────

class TestLandConfig:
    def test_create_conquer_config(self, db, two_users):
        u1, _ = two_users
        cfg = LandConfig(user_id=u1.id, config_type='conquer')
        db.session.add(cfg)
        db.session.commit()

        assert cfg.id is not None
        d = cfg.serialize()
        assert d['config_type'] == 'conquer'
        assert d['land_id'] is None
        assert d['figures'] == []
        assert d['battle_moves'] == []

    def test_add_figure(self, db, two_users):
        u1, _ = two_users
        cfg = LandConfig(user_id=u1.id, config_type='conquer')
        db.session.add(cfg)
        db.session.flush()

        fig = LandConfigFigure(
            config_id=cfg.id, family_name='Military', name='Warrior',
            suit='Spades', color='defensive', field='military',
            card_ids=[1, 2], card_roles=['key', 'number'],
        )
        db.session.add(fig)
        db.session.commit()

        d = cfg.serialize()
        assert len(d['figures']) == 1
        assert d['figures'][0]['family_name'] == 'Military'

    def test_add_battle_move(self, db, two_users):
        u1, _ = two_users
        cfg = LandConfig(user_id=u1.id, config_type='defence')
        db.session.add(cfg)
        db.session.flush()

        move = LandConfigBattleMove(
            config_id=cfg.id, family_name='Strike', card_id=10,
            suit='Hearts', rank='9', value=9, round_index=0,
        )
        db.session.add(move)
        db.session.commit()

        d = cfg.serialize()
        assert len(d['battle_moves']) == 1
        assert d['battle_moves'][0]['round_index'] == 0

    def test_defence_with_spell(self, db, two_users):
        u1, _ = two_users
        cfg = LandConfig(
            user_id=u1.id, config_type='defence',
            spell_name='health_boost', spell_card_ids=[5, 6],
        )
        db.session.add(cfg)
        db.session.commit()

        d = cfg.serialize()
        assert d['spell_name'] == 'health_boost'
        assert d['spell_card_ids'] == [5, 6]

    def test_defence_with_modifier(self, db, two_users):
        u1, _ = two_users
        cfg = LandConfig(
            user_id=u1.id, config_type='defence',
            battle_modifier={'type': 'Peasant War'},
            modifier_card_ids=[10, 11],
        )
        db.session.add(cfg)
        db.session.commit()

        d = cfg.serialize()
        assert d['battle_modifier']['type'] == 'Peasant War'


# ── LandAttackLog ────────────────────────────────────────────────────────────

class TestLandAttackLog:
    def test_create_attacker_won(self, db, two_users):
        u1, u2 = two_users
        land = Land(col=0, row=0, tier=1, gold_rate=1.0,
                    suit_bonus_suit='Hearts', suit_bonus_value=1)
        db.session.add(land)
        db.session.flush()

        log = LandAttackLog(
            land_id=land.id,
            attacker_user_id=u1.id,
            defender_user_id=u2.id,
            result='attacker_won',
            card_won_suit='Spades', card_won_rank='K',
        )
        db.session.add(log)
        db.session.commit()

        d = log.serialize()
        assert d['result'] == 'attacker_won'
        assert d['card_won_suit'] == 'Spades'
        assert d['seen_by_defender'] is False

    def test_ai_defender_null(self, db, two_users):
        u1, _ = two_users
        land = Land(col=1, row=0, tier=1, gold_rate=1.0,
                    suit_bonus_suit='Clubs', suit_bonus_value=1)
        db.session.add(land)
        db.session.flush()

        log = LandAttackLog(
            land_id=land.id,
            attacker_user_id=u1.id,
            defender_user_id=None,  # AI
            result='defender_won',
        )
        db.session.add(log)
        db.session.commit()

        assert log.defender_user_id is None


# ── Game mode field ──────────────────────────────────────────────────────────

class TestGameMode:
    def test_default_mode_is_duel(self, db):
        game = Game(stake=35)
        db.session.add(game)
        db.session.commit()

        d = game.serialize()
        assert d['mode'] == 'duel'
        assert d['land_id'] is None

    def test_conquer_mode(self, db):
        land = Land(col=0, row=0, tier=1, gold_rate=1.0,
                    suit_bonus_suit='Hearts', suit_bonus_value=1)
        db.session.add(land)
        db.session.flush()

        game = Game(stake=0, mode='conquer', land_id=land.id)
        db.session.add(game)
        db.session.commit()

        d = game.serialize()
        assert d['mode'] == 'conquer'
        assert d['land_id'] == land.id


# ── User v2 fields ────────────────────────────────────────────────────────────

class TestUserV2Fields:
    def test_booster_packs_default(self, db, two_users):
        u1, _ = two_users
        assert u1.booster_packs == 0

    def test_booster_packs_side_default(self, db, two_users):
        u1, _ = two_users
        assert u1.booster_packs_side == 0

    def test_booster_packs_in_serialize(self, db, two_users):
        u1, _ = two_users
        u1.booster_packs = 5
        u1.booster_packs_side = 3
        db.session.commit()

        d = u1.serialize()
        assert d['booster_packs'] == 5
        assert d['booster_packs_side'] == 3
