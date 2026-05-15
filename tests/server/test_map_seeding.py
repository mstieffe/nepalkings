# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for kingdom map seeding and gold production."""
import pytest
from unittest.mock import patch
from datetime import datetime, timezone, timedelta

from models import db, Land, User
from kingdom_service import (
    seed_kingdom_map,
    _build_cluster_suits,
    _cluster_radius_bounds,
    _build_cluster_profiles,
)


class TestMapSeeding:
    def test_cluster_suits_equal_count_per_suit(self):
        clusters_per_suit = 3
        cluster_suits = _build_cluster_suits(clusters_per_suit)

        assert len(cluster_suits) == 4 * clusters_per_suit
        for suit in ('Hearts', 'Diamonds', 'Clubs', 'Spades'):
            assert cluster_suits.count(suit) == clusters_per_suit

    def test_cluster_radius_bounds_respect_tier1_border_cap(self):
        import server_settings as config

        lo, hi = _cluster_radius_bounds(config.KINGDOM_TIER_COUNT)
        assert 1 <= lo <= hi

        cap = max(0, int(config.KINGDOM_MAP_TIER1_BORDER_MAX_HEXES))
        max_allowed = max(1, config.KINGDOM_TIER_COUNT + cap - 2)
        assert hi <= max_allowed

    def test_cluster_profiles_within_configured_ranges(self):
        import server_settings as config

        seeds = [(0, 0), (5, 5), (10, 8)]
        profiles = _build_cluster_profiles(seeds, config.KINGDOM_TIER_COUNT)
        lo, hi = _cluster_radius_bounds(config.KINGDOM_TIER_COUNT)
        anis_lo, anis_hi = config.KINGDOM_MAP_CLUSTER_ANISOTROPY_RANGE

        assert len(profiles) == len(seeds)
        for profile in profiles:
            assert lo <= profile['radius'] <= hi
            assert max(1.0, float(anis_lo)) <= profile['anisotropy'] <= float(anis_hi)

    def test_seed_creates_correct_number_of_lands(self, app, db):
        with app.app_context():
            seed_kingdom_map()
            count = Land.query.count()
            import server_settings as config
            expected = config.KINGDOM_MAP_COLS * config.KINGDOM_MAP_ROWS
            assert count == expected

    def test_seed_idempotent(self, app, db):
        """Calling seed twice should not duplicate lands."""
        with app.app_context():
            seed_kingdom_map()
            count1 = Land.query.count()
            seed_kingdom_map()
            count2 = Land.query.count()
            assert count1 == count2

    def test_all_lands_have_valid_tiers(self, app, db):
        import server_settings as config
        with app.app_context():
            seed_kingdom_map()
            valid_tiers = set(range(1, config.KINGDOM_TIER_COUNT + 1))
            for land in Land.query.all():
                assert land.tier in valid_tiers

    def test_all_lands_have_positive_gold_rate(self, app, db):
        with app.app_context():
            seed_kingdom_map()
            for land in Land.query.all():
                assert land.gold_rate > 0

    def test_all_lands_have_valid_suit_bonus(self, app, db):
        valid_suits = {'Hearts', 'Diamonds', 'Clubs', 'Spades', 'Neutral'}
        with app.app_context():
            seed_kingdom_map()
            for land in Land.query.all():
                assert land.suit_bonus_suit in valid_suits
                if land.suit_bonus_suit == 'Neutral':
                    assert land.suit_bonus_value == 0
                else:
                    assert land.suit_bonus_value > 0

    def test_neutral_lands_never_apex_tier(self, app, db):
        import server_settings as config
        with app.app_context():
            seed_kingdom_map()
            apex = config.KINGDOM_TIER_COUNT
            for land in Land.query.filter_by(suit_bonus_suit='Neutral').all():
                assert land.tier < apex

    def test_neutral_lands_present(self, app, db):
        with app.app_context():
            seed_kingdom_map()
            neutrals = Land.query.filter_by(suit_bonus_suit='Neutral').count()
            assert neutrals > 0

    def test_apex_tier_present_in_clusters(self, app, db):
        import server_settings as config
        with app.app_context():
            seed_kingdom_map()
            apex = config.KINGDOM_TIER_COUNT
            apex_lands = [l for l in Land.query.all() if l.tier == apex]
            assert apex_lands  # at least one peak per cluster
            for land in apex_lands:
                assert land.suit_bonus_suit != 'Neutral'

    def test_unique_col_row_pairs(self, app, db):
        with app.app_context():
            seed_kingdom_map()
            lands = Land.query.all()
            coords = [(l.col, l.row) for l in lands]
            assert len(coords) == len(set(coords))

    def test_gold_rate_within_tier_range(self, app, db):
        import server_settings as config
        with app.app_context():
            seed_kingdom_map()
            for land in Land.query.all():
                lo, hi = config.LAND_GOLD_RATE_RANGES[land.tier]
                assert lo <= land.gold_rate <= hi


class TestGoldProduction:
    """Per-kingdom gold vault accrual + atomic collect (vault skill rework)."""

    def _make_user(self, db):
        from werkzeug.security import generate_password_hash
        u = User(username='gold_test', password_hash=generate_password_hash('pw'), gold=100)
        db.session.add(u)
        db.session.commit()
        return u

    def _kingdom_for(self, user):
        from kingdom_service import reconcile_user_kingdoms
        from models import Kingdom
        reconcile_user_kingdoms(user.id, commit=True)
        return Kingdom.query.filter_by(owner_user_id=user.id).first()

    def test_no_lands_no_kingdom(self, app, db):
        with app.app_context():
            u = self._make_user(db)
            from kingdom_service import collect_kingdom_gold
            # Even with no kingdom, calling collect on None is safe.
            collected, cap, gold = collect_kingdom_gold(None, u)
            assert collected == 0
            assert gold == 100

    def test_pending_accrues_per_kingdom(self, app, db):
        from kingdom_service import collect_kingdom_gold
        with app.app_context():
            u = self._make_user(db)
            land = Land(col=0, row=0, tier=1, gold_rate=6.0,
                        suit_bonus_suit='Hearts', suit_bonus_value=1,
                        owner_user_id=u.id)
            db.session.add(land)
            db.session.commit()
            k = self._kingdom_for(u)
            two_hours_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2)
            k.last_gold_collection_at = two_hours_ago
            db.session.commit()
            collected, cap, gold = collect_kingdom_gold(k, u)
            assert collected == 12          # 6 gold/hr × 2 hr
            assert gold == 112
            assert k.pending_gold < 1

    def test_vault_caps_pending(self, app, db):
        """Pending gold is clamped at the vault cap (default cap with no skill)."""
        from kingdom_service import collect_kingdom_gold, kingdom_vault_cap
        import server_settings as config
        with app.app_context():
            u = self._make_user(db)
            land = Land(col=0, row=0, tier=1, gold_rate=10.0,
                        suit_bonus_suit='Hearts', suit_bonus_value=1,
                        owner_user_id=u.id)
            db.session.add(land)
            db.session.commit()
            k = self._kingdom_for(u)
            long_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
            k.last_gold_collection_at = long_ago
            db.session.commit()
            collected, cap, gold = collect_kingdom_gold(k, u)
            assert cap == int(config.KINGDOM_VAULT_DEFAULT_CAP)
            assert collected == cap

    def test_multiple_lands_sum_rates(self, app, db):
        from kingdom_service import collect_kingdom_gold
        with app.app_context():
            u = self._make_user(db)
            db.session.add(Land(col=0, row=0, tier=1, gold_rate=3.0,
                                suit_bonus_suit='Hearts', suit_bonus_value=1,
                                owner_user_id=u.id))
            db.session.add(Land(col=1, row=0, tier=2, gold_rate=5.0,
                                suit_bonus_suit='Clubs', suit_bonus_value=2,
                                owner_user_id=u.id))
            db.session.commit()
            k = self._kingdom_for(u)
            one_hour_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
            k.last_gold_collection_at = one_hour_ago
            db.session.commit()
            collected, cap, gold = collect_kingdom_gold(k, u)
            assert collected == 8           # (3 + 5) × 1 hour
