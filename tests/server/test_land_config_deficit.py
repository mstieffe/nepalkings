# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Tests for kingdom_service resource deficit checks on LandConfigFigures."""

import pytest
from models import db as _db, User, LandConfig, LandConfigFigure
from kingdom_service import check_land_config_deficit, get_config_deficit_map
from werkzeug.security import generate_password_hash


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_user(db):
    u = User(username='deftest', password_hash=generate_password_hash('pw'), gold=0)
    db.session.add(u)
    db.session.commit()
    return u


def _make_config(db, user_id, config_type='conquer'):
    cfg = LandConfig(user_id=user_id, config_type=config_type)
    db.session.add(cfg)
    db.session.commit()
    return cfg


def _add_fig(db, config_id, family_name, field, color, suit,
             produces=None, requires=None):
    fig = LandConfigFigure(
        config_id=config_id,
        family_name=family_name,
        name=family_name,
        suit=suit,
        color=color,
        field=field,
        card_ids=[],
        card_roles=[],
        produces=produces,
        requires=requires,
    )
    db.session.add(fig)
    db.session.commit()
    return fig


# ═══════════════════════════════════════════════════════════════════
#  check_land_config_deficit
# ═══════════════════════════════════════════════════════════════════

class TestCheckLandConfigDeficit:

    def test_no_requires_never_deficit(self, db, app):
        u = _make_user(db)
        cfg = _make_config(db, u.id)
        fig = _add_fig(db, cfg.id, 'King', 'castle', 'defensive', 'Clubs',
                       produces={'villager_black': 2}, requires=None)
        assert check_land_config_deficit(fig, [fig]) is False

    def test_produces_covers_requires(self, db, app):
        u = _make_user(db)
        cfg = _make_config(db, u.id)
        king = _add_fig(db, cfg.id, 'King', 'castle', 'defensive', 'Clubs',
                        produces={'villager_black': 2, 'warrior_black': 1})
        farm = _add_fig(db, cfg.id, 'Farm', 'village', 'defensive', 'Clubs',
                        produces={'food_black': 7}, requires={'villager_black': 1})
        all_figs = [king, farm]
        assert check_land_config_deficit(farm, all_figs) is False

    def test_requires_exceeds_produces(self, db, app):
        u = _make_user(db)
        cfg = _make_config(db, u.id)
        # No producer — farm requires villager but nobody produces it
        farm = _add_fig(db, cfg.id, 'Farm', 'village', 'defensive', 'Clubs',
                        produces={'food_black': 7}, requires={'villager_black': 1})
        assert check_land_config_deficit(farm, [farm]) is True

    def test_cascading_deficit(self, db, app):
        """If a producer is itself in deficit, its production is excluded."""
        u = _make_user(db)
        cfg = _make_config(db, u.id)
        # King produces 2 villagers, 1 warrior
        king = _add_fig(db, cfg.id, 'King', 'castle', 'defensive', 'Clubs',
                        produces={'villager_black': 2, 'warrior_black': 1})
        # 3 farms each require 1 villager → total 3 > produced 2
        farm1 = _add_fig(db, cfg.id, 'Farm1', 'village', 'defensive', 'Clubs',
                         produces={'food_black': 7}, requires={'villager_black': 1})
        farm2 = _add_fig(db, cfg.id, 'Farm2', 'village', 'defensive', 'Clubs',
                         produces={'food_black': 8}, requires={'villager_black': 1})
        farm3 = _add_fig(db, cfg.id, 'Farm3', 'village', 'defensive', 'Spades',
                         produces={'food_black': 9}, requires={'villager_black': 1})
        all_figs = [king, farm1, farm2, farm3]
        # All three farms are in deficit because total requires (3) > total produces (2)
        assert check_land_config_deficit(farm1, all_figs) is True
        assert check_land_config_deficit(farm2, all_figs) is True
        assert check_land_config_deficit(farm3, all_figs) is True

    def test_king_not_in_deficit(self, db, app):
        """King has no requires, so it's never in deficit even if others are."""
        u = _make_user(db)
        cfg = _make_config(db, u.id)
        king = _add_fig(db, cfg.id, 'King', 'castle', 'defensive', 'Clubs',
                        produces={'villager_black': 2, 'warrior_black': 1})
        farm1 = _add_fig(db, cfg.id, 'Farm1', 'village', 'defensive', 'Clubs',
                         produces={'food_black': 7}, requires={'villager_black': 1})
        farm2 = _add_fig(db, cfg.id, 'Farm2', 'village', 'defensive', 'Clubs',
                         produces={'food_black': 8}, requires={'villager_black': 1})
        farm3 = _add_fig(db, cfg.id, 'Farm3', 'village', 'defensive', 'Spades',
                         produces={'food_black': 9}, requires={'villager_black': 1})
        all_figs = [king, farm1, farm2, farm3]
        assert check_land_config_deficit(king, all_figs) is False

    def test_military_figure_with_food_deficit(self, db, app):
        """Military figure is in deficit when food requires exceed food production."""
        u = _make_user(db)
        cfg = _make_config(db, u.id)
        king = _add_fig(db, cfg.id, 'King', 'castle', 'defensive', 'Clubs',
                        produces={'villager_black': 2, 'warrior_black': 1})
        # Fortress requires warrior + food, but no one produces food
        fort = _add_fig(db, cfg.id, 'Fortress', 'military', 'defensive', 'Clubs',
                        requires={'warrior_black': 1, 'food_black': 8})
        all_figs = [king, fort]
        assert check_land_config_deficit(fort, all_figs) is True


class TestGetConfigDeficitMap:

    def test_returns_map_for_all_figures(self, db, app):
        u = _make_user(db)
        cfg = _make_config(db, u.id)
        king = _add_fig(db, cfg.id, 'King', 'castle', 'defensive', 'Clubs',
                        produces={'villager_black': 2, 'warrior_black': 1})
        farm = _add_fig(db, cfg.id, 'Farm', 'village', 'defensive', 'Clubs',
                        produces={'food_black': 7}, requires={'villager_black': 1})
        result = get_config_deficit_map(cfg.id)
        assert result[king.id] is False
        assert result[farm.id] is False

    def test_deficit_map_detects_deficit(self, db, app):
        u = _make_user(db)
        cfg = _make_config(db, u.id)
        # No king (no producer), farm requires villager
        farm = _add_fig(db, cfg.id, 'Farm', 'village', 'defensive', 'Clubs',
                        produces={'food_black': 7}, requires={'villager_black': 1})
        result = get_config_deficit_map(cfg.id)
        assert result[farm.id] is True

    def test_empty_config(self, db, app):
        u = _make_user(db)
        cfg = _make_config(db, u.id)
        result = get_config_deficit_map(cfg.id)
        assert result == {}
