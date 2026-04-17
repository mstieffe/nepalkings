# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for kingdom map seeding and gold production."""
import pytest
from unittest.mock import patch
from datetime import datetime, timezone, timedelta

from models import db, Land, User
from kingdom_service import seed_kingdom_map, collect_gold_for_user


class TestMapSeeding:
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
        with app.app_context():
            seed_kingdom_map()
            for land in Land.query.all():
                assert land.tier in (1, 2, 3)

    def test_all_lands_have_positive_gold_rate(self, app, db):
        with app.app_context():
            seed_kingdom_map()
            for land in Land.query.all():
                assert land.gold_rate > 0

    def test_all_lands_have_valid_suit_bonus(self, app, db):
        valid_suits = {'Hearts', 'Diamonds', 'Clubs', 'Spades'}
        with app.app_context():
            seed_kingdom_map()
            for land in Land.query.all():
                assert land.suit_bonus_suit in valid_suits
                assert land.suit_bonus_value > 0

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
    def _make_user(self, db):
        from werkzeug.security import generate_password_hash
        u = User(username='gold_test', password_hash=generate_password_hash('pw'), gold=100)
        db.session.add(u)
        db.session.commit()
        return u

    def test_no_lands_no_gold(self, app, db):
        with app.app_context():
            u = self._make_user(db)
            earned, total, rate = collect_gold_for_user(u)
            assert earned == 0
            assert total == 100
            assert rate == 0.0

    def test_first_call_sets_timestamp_no_earnings(self, app, db):
        with app.app_context():
            u = self._make_user(db)
            # Give user a land
            land = Land(col=0, row=0, tier=1, gold_rate=10.0,
                        suit_bonus_suit='Hearts', suit_bonus_value=1,
                        owner_user_id=u.id)
            db.session.add(land)
            db.session.commit()

            earned, total, rate = collect_gold_for_user(u)
            assert earned == 0
            assert rate == 10.0
            assert u.last_gold_collection is not None

    def test_gold_earned_after_time(self, app, db):
        with app.app_context():
            u = self._make_user(db)
            land = Land(col=0, row=0, tier=1, gold_rate=6.0,
                        suit_bonus_suit='Hearts', suit_bonus_value=1,
                        owner_user_id=u.id)
            db.session.add(land)
            db.session.commit()

            # Set last collection to 2 hours ago
            two_hours_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2)
            u.last_gold_collection = two_hours_ago
            db.session.commit()

            earned, total, rate = collect_gold_for_user(u)
            # 6.0 gold/hr × 2 hr = 12 gold
            assert earned == 12
            assert total == 112
            assert rate == 6.0

    def test_gold_capped_at_max_accumulation(self, app, db):
        import server_settings as config
        with app.app_context():
            u = self._make_user(db)
            land = Land(col=0, row=0, tier=1, gold_rate=10.0,
                        suit_bonus_suit='Hearts', suit_bonus_value=1,
                        owner_user_id=u.id)
            db.session.add(land)
            db.session.commit()

            # Set last collection to 30 days ago (way past cap)
            long_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
            u.last_gold_collection = long_ago
            db.session.commit()

            earned, total, rate = collect_gold_for_user(u)
            max_hours = config.GOLD_PRODUCTION_MAX_ACCUMULATION_HOURS
            expected_max = int(10.0 * max_hours)
            assert earned == expected_max

    def test_multiple_lands_sum_rates(self, app, db):
        with app.app_context():
            u = self._make_user(db)
            db.session.add(Land(col=0, row=0, tier=1, gold_rate=3.0,
                                suit_bonus_suit='Hearts', suit_bonus_value=1,
                                owner_user_id=u.id))
            db.session.add(Land(col=1, row=0, tier=2, gold_rate=5.0,
                                suit_bonus_suit='Clubs', suit_bonus_value=2,
                                owner_user_id=u.id))
            db.session.commit()

            one_hour_ago = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
            u.last_gold_collection = one_hour_ago
            db.session.commit()

            earned, total, rate = collect_gold_for_user(u)
            assert rate == 8.0
            assert earned == 8  # (3+5) × 1 hour
