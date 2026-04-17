# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Kingdom service — map seeding, gold production, config validation."""

import math
import random
from datetime import datetime, timezone

import server_settings as config
from models import db, Land, CollectionCard, LandConfigFigure


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── Map Seeding ──────────────────────────────────────────────────────────────

def _pick_tier():
    """Pick a land tier using weighted probabilities from config."""
    tiers = list(config.LAND_TIER_PROBABILITIES.keys())
    weights = [config.LAND_TIER_PROBABILITIES[t] for t in tiers]
    return random.choices(tiers, weights=weights, k=1)[0]


def _pick_gold_rate(tier):
    lo, hi = config.LAND_GOLD_RATE_RANGES[tier]
    return round(random.uniform(lo, hi), 2)


def _pick_suit_bonus(tier):
    suits = ['Hearts', 'Diamonds', 'Clubs', 'Spades']
    suit = random.choice(suits)
    lo, hi = config.LAND_SUIT_BONUS_RANGES[tier]
    value = random.randint(lo, hi)
    return suit, value


def _pick_ai_template_index(tier):
    templates = config.AI_DEFENCE_TEMPLATES.get(tier, [])
    if not templates:
        return 0
    return random.randint(0, len(templates) - 1)


def seed_kingdom_map():
    """Generate the kingdom hex map if it doesn't exist yet.

    Creates ``KINGDOM_MAP_COLS × KINGDOM_MAP_ROWS`` Land records with
    randomised tier, gold rate, and suit bonus.
    """
    if Land.query.first() is not None:
        return  # already seeded

    cols = config.KINGDOM_MAP_COLS
    rows = config.KINGDOM_MAP_ROWS

    for r in range(rows):
        for c in range(cols):
            tier = _pick_tier()
            suit, bonus_val = _pick_suit_bonus(tier)
            land = Land(
                col=c,
                row=r,
                tier=tier,
                gold_rate=_pick_gold_rate(tier),
                suit_bonus_suit=suit,
                suit_bonus_value=bonus_val,
                ai_template_index=_pick_ai_template_index(tier),
            )
            db.session.add(land)

    db.session.commit()


# ── Gold Production ──────────────────────────────────────────────────────────

def collect_gold_for_user(user):
    """Credit on-demand gold production from owned lands.

    Returns ``(gold_earned, total_gold, total_production_rate)``.
    All timestamps are server-authoritative.
    """
    now = _utcnow()

    # Sum gold rates of all owned lands
    total_rate = db.session.query(
        db.func.coalesce(db.func.sum(Land.gold_rate), 0.0)
    ).filter(Land.owner_user_id == user.id).scalar()

    if total_rate <= 0:
        user.last_gold_collection = now
        db.session.commit()
        return 0, user.gold, 0.0

    if user.last_gold_collection is None:
        user.last_gold_collection = now
        db.session.commit()
        return 0, user.gold, total_rate

    elapsed_seconds = (now - user.last_gold_collection).total_seconds()
    max_seconds = config.GOLD_PRODUCTION_MAX_ACCUMULATION_HOURS * 3600
    elapsed_seconds = min(elapsed_seconds, max_seconds)
    elapsed_hours = elapsed_seconds / 3600.0

    earned = int(total_rate * elapsed_hours)
    if earned > 0:
        user.gold += earned
        user.last_gold_collection = now
        db.session.commit()

    return earned, user.gold, total_rate


# ── Config Validation ────────────────────────────────────────────────────────

RANK_TO_VALUE = {
    'A': 3, 'K': 4, 'Q': 2, 'J': 1,
    '10': 10, '9': 9, '8': 8, '7': 7,
    '6': 6, '5': 5, '4': 4, '3': 3, '2': 2,
}


def get_free_collection_cards(user_id):
    """Return all unlocked collection cards for a user."""
    return CollectionCard.query.filter_by(
        user_id=user_id, locked=False
    ).all()


def validate_battle_figure_for_modifier(figure_color, figure_color_2, modifier):
    """Check if battle figure(s) are compatible with the battle modifier.

    Returns True if valid.
    """
    if modifier is None:
        return True
    mod_type = modifier.get('type', '') if isinstance(modifier, dict) else str(modifier)
    if mod_type == 'Civil War':
        # Both figures must be same color
        if figure_color_2 is None:
            return False  # civil war requires 2 figures
        return figure_color == figure_color_2
    # Peasant War / Blitzkrieg have no figure color constraint
    return True


# ── Resource Deficit ─────────────────────────────────────────────────────────

def check_land_config_deficit(figure, all_config_figures):
    """Check if a LandConfigFigure has a resource deficit within its config.

    Uses the same iterative algorithm as ``_check_figure_resource_deficit``
    in ``routes/games.py``: figures in deficit don't contribute production,
    re-evaluated until stable.

    Parameters
    ----------
    figure : LandConfigFigure
        The figure to check.
    all_config_figures : list[LandConfigFigure]
        All figures in the same LandConfig (including *figure*).

    Returns
    -------
    bool
        ``True`` if *figure* has at least one required resource in deficit.
    """
    if not figure.requires:
        return False

    # Total requires across ALL figures in this config
    total_requires = {}
    for fig in all_config_figures:
        if fig.requires:
            for res, amount in fig.requires.items():
                total_requires[res] = total_requires.get(res, 0) + amount

    # Iteratively exclude production from deficit figures until stable
    excluded = set()
    stable = False
    while not stable:
        stable = True
        total_produces = {}
        for i, fig in enumerate(all_config_figures):
            if i in excluded:
                continue
            if fig.produces:
                for res, amount in fig.produces.items():
                    total_produces[res] = total_produces.get(res, 0) + amount
        for i, fig in enumerate(all_config_figures):
            if i in excluded:
                continue
            if not fig.requires:
                continue
            for res_name in fig.requires:
                if total_requires.get(res_name, 0) > total_produces.get(res_name, 0):
                    excluded.add(i)
                    stable = False
                    break

    # Check if the target figure's required resources are in deficit
    for resource_name in figure.requires:
        total_req = total_requires.get(resource_name, 0)
        total_prod = total_produces.get(resource_name, 0)
        if total_req > total_prod:
            return True
    return False


def get_config_deficit_map(config_id):
    """Return a dict mapping LandConfigFigure.id → bool (True = deficit).

    Useful for annotating an entire config's figures at once.
    """
    figures = LandConfigFigure.query.filter_by(config_id=config_id).all()
    return {fig.id: check_land_config_deficit(fig, figures) for fig in figures}
