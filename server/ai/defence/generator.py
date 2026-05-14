# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Deterministic AI defence generation for unowned kingdom lands."""

from __future__ import annotations

import copy
import hashlib
import logging
import random
from typing import Any

from ai.defence.config import (
    AI_DEFENCE_BLACK_SUITS,
    AI_DEFENCE_FIGURE_CATALOG,
    AI_DEFENCE_GENERATION_RULES,
    AI_DEFENCE_GENERATOR_VERSION,
    AI_DEFENCE_RANK_VALUES,
    AI_DEFENCE_RED_SUITS,
    AI_DEFENCE_RESOURCE_PROVIDERS,
    AI_DEFENCE_SAFE_FALLBACKS,
    AI_DEFENCE_SUITS,
    AI_DEFENCE_TIER_NAMES,
)

logger = logging.getLogger('nk.ai.defence.generator')

# Maximum re-rolls when an optional draw is rejected for resource
# infeasibility before we give up on that slot.
MAX_FEASIBILITY_RETRIES = 12

# Probability that a generator-appended castle slot becomes a Maharaja
# (else king).  Anchor castle role is left untouched.
EXTRA_CASTLE_MAHARAJA_CHANCE = 0.30

# Roles considered castle figures by the cap rule.
_CASTLE_ROLES = frozenset({'king', 'maharaja'})


def _suit_color(suit: str) -> str:
    return 'red' if suit in AI_DEFENCE_RED_SUITS else 'black'


def _suits_for_color(color: str) -> tuple[str, ...]:
    return AI_DEFENCE_RED_SUITS if color == 'red' else AI_DEFENCE_BLACK_SUITS


def _normalize_suit(suit: Any, rng: random.Random) -> str:
    if suit in AI_DEFENCE_SUITS:
        return str(suit)
    return rng.choice(AI_DEFENCE_SUITS)


def _default_suit_for_color(color: str, primary_suit: str, rng: random.Random) -> str:
    suits = _suits_for_color(color)
    if primary_suit in suits:
        return primary_suit
    return rng.choice(suits)


def _same_color_alternate(suit: str, rng: random.Random) -> str:
    suits = list(_suits_for_color(_suit_color(suit)))
    rng.shuffle(suits)
    return suits[0]


def _opposite_color_suit(suit: str, rng: random.Random) -> str:
    opposite_color = 'black' if _suit_color(suit) == 'red' else 'red'
    return rng.choice(_suits_for_color(opposite_color))


def _weighted_choice(weighted_items, rng: random.Random):
    total = sum(max(0, int(weight)) for _, weight in weighted_items)
    if total <= 0:
        return weighted_items[0][0]
    pick = rng.uniform(0, total)
    cursor = 0
    for item, weight in weighted_items:
        cursor += max(0, int(weight))
        if pick <= cursor:
            return item
    return weighted_items[-1][0]


def _number_rank_for_tier(tier: int, rng: random.Random) -> str:
    rules = AI_DEFENCE_GENERATION_RULES.get(tier) or AI_DEFENCE_GENERATION_RULES[1]
    ranks = list(rules.get('number_ranks') or ['8'])
    return rng.choice(ranks)


def _normalize_card_type(card_type: Any) -> str:
    normalized = str(card_type or 'main').strip().lower()
    return normalized if normalized in ('main', 'side') else 'main'


def _normalize_card_rank(card_type: str, rank: Any, role: str) -> str:
    raw = str(rank or '').strip()
    if card_type == 'side':
        if raw in {'2', '3', '4', '5', '6'}:
            return raw
        return '2' if role == 'key' else '6'
    if raw:
        return raw
    return 'K' if role == 'key' else '10'


def _number_rank_for_role(base: dict[str, Any], tier: int,
                          rng: random.Random) -> str:
    options = list(base.get('number_rank_options') or [])
    if not options:
        return _number_rank_for_tier(tier, rng)
    return str(rng.choice(options))


def _number_card_value(cards: list[dict[str, Any]]) -> int | None:
    for card in cards:
        if card.get('role') != 'number':
            continue
        rank = str(card.get('rank') or '').strip()
        if rank.isdigit():
            return int(rank)
        return int(AI_DEFENCE_RANK_VALUES.get(rank, 0) or 0)
    return None


def _make_cards(base: dict[str, Any], suit: str, tier: int,
                rng: random.Random) -> list[dict[str, Any]]:
    roles = list(base.get('card_roles') or [])
    key_cards = list(base.get('key_cards') or [])
    fallback_key_rank = str(base.get('key_rank') or 'K')
    number_card_type = _normalize_card_type(base.get('number_card_type', 'main'))

    cards: list[dict[str, Any]] = []
    key_index = 0
    for role in roles:
        if role == 'number':
            card_type = number_card_type
            rank = _normalize_card_rank(
                card_type,
                _number_rank_for_role(base, tier, rng),
                role,
            )
        else:
            key_spec = key_cards[key_index] if key_index < len(key_cards) else {}
            card_type = _normalize_card_type(key_spec.get('card_type', 'main'))
            rank = _normalize_card_rank(
                card_type,
                key_spec.get('rank', fallback_key_rank),
                'key',
            )
            key_index += 1

        cards.append({
            'rank': rank,
            'suit': suit,
            'role': role,
            'card_type': card_type,
        })
    return cards


def _make_figure(role: str, suit: str, tier: int,
                 rng: random.Random) -> dict[str, Any]:
    color = _suit_color(suit)
    base = copy.deepcopy(AI_DEFENCE_FIGURE_CATALOG[role][color])
    cards = _make_cards(base, suit, tier, rng)
    number_value = _number_card_value(cards)

    produces = dict(base.get('produces') or {})
    requires = dict(base.get('requires') or {})
    if number_value is not None:
        for res, multiplier in (base.get('number_produces') or {}).items():
            produces[res] = produces.get(res, 0) + int(number_value * int(multiplier or 0))
        for res, multiplier in (base.get('number_requires') or {}).items():
            requires[res] = requires.get(res, 0) + int(number_value * int(multiplier or 0))

    base.pop('key_cards', None)
    base.pop('key_rank', None)
    base.pop('number_card_type', None)
    base.pop('number_rank_options', None)
    base.pop('number_produces', None)
    base.pop('number_requires', None)
    base.update({
        'suit': suit,
        'card_ids': [],
        'produces': produces,
        'requires': requires,
        'cards': cards,
    })
    return base


def _choose_optional_suit(primary_suit: str, tier: int, rng: random.Random) -> str:
    rules = AI_DEFENCE_GENERATION_RULES.get(tier) or AI_DEFENCE_GENERATION_RULES[1]
    weights = dict(rules.get('optional_suit_weights') or {})
    if not weights:
        if tier >= 3:
            weights = {'primary': 7, 'same_color': 2, 'any': 1}
        elif tier == 2:
            weights = {'primary': 5, 'same_color': 2}
        else:
            weights = {'primary': 1}

    weighted_suits = []
    for key, weight in weights.items():
        if key == 'primary':
            suit = primary_suit
        elif key == 'same_color':
            suit = _same_color_alternate(primary_suit, rng)
        elif key == 'opposite_color':
            suit = _opposite_color_suit(primary_suit, rng)
        elif key == 'any':
            suit = rng.choice(AI_DEFENCE_SUITS)
        else:
            continue
        weighted_suits.append((suit, weight))
    return _weighted_choice(weighted_suits or [(primary_suit, 1)], rng)


_FORTRESS_ROLES = frozenset({'military_basic', 'military_elite'})


def _is_black_land_fortress_free(primary_suit: str, rules: dict[str, Any],
                                 rng: random.Random) -> bool:
    if _suit_color(primary_suit) != 'black':
        return False
    chance = float(rules.get('black_land_fortress_free_chance', 0) or 0)
    if chance <= 0:
        return False
    return rng.random() < min(1.0, max(0.0, chance))


def _core_suit_for_role(role: str, primary_suit: str, core_index: int,
                        rules: dict[str, Any], rng: random.Random,
                        fortress_free_black: bool) -> str:
    # Always keep at least one land-suit figure anchor.
    if core_index == 0:
        return primary_suit

    if fortress_free_black and role in _FORTRESS_ROLES:
        return _opposite_color_suit(primary_suit, rng)

    # If a black land is not in its fortress-free variant, keep guaranteed
    # fortress roles black so fortress-free frequency is controlled by the
    # explicit tier setting rather than incidental cross-color rolls.
    if _suit_color(primary_suit) == 'black' and role in _FORTRESS_ROLES:
        return primary_suit

    chance = float(rules.get('core_cross_color_chance', 0) or 0)
    if chance > 0 and rng.random() < min(1.0, max(0.0, chance)):
        return _opposite_color_suit(primary_suit, rng)
    return primary_suit


def _resource_totals(figures: list[dict[str, Any]]) -> tuple[dict[str, int], dict[str, int]]:
    total_requires: dict[str, int] = {}
    total_produces: dict[str, int] = {}
    for fig in figures:
        for res, amount in (fig.get('requires') or {}).items():
            total_requires[res] = total_requires.get(res, 0) + int(amount or 0)
        for res, amount in (fig.get('produces') or {}).items():
            total_produces[res] = total_produces.get(res, 0) + int(amount or 0)
    return total_requires, total_produces


def _count_castle_figures(figures: list[dict[str, Any]]) -> int:
    return sum(1 for fig in figures if (fig.get('field') or '').lower() == 'castle')


def _optional_role_is_feasible(role_key: str, suit: str,
                               current_figures: list[dict[str, Any]],
                               rng: random.Random,
                               tier: int) -> bool:
    """Return True iff appending a fresh ``role_key`` of ``suit`` keeps the
    template's static resource balance non-negative on every base channel
    (villager_*, warrior_*, etc.).  Dynamic number-based requires (food,
    material) are *not* checked here — those are handled downstream by
    ``_repair_resource_deficits`` which can append farms/material providers
    without violating the castle cap.
    """
    color = _suit_color(suit)
    base = AI_DEFENCE_FIGURE_CATALOG.get(role_key, {}).get(color)
    if not base:
        return False
    if (base.get('field') or '').lower() == 'castle':
        # Castle figures (king/maharaja) only PRODUCE; trivially feasible.
        return True
    total_req, total_prod = _resource_totals(current_figures)
    for res, amt in (base.get('requires') or {}).items():
        total_req[res] = total_req.get(res, 0) + int(amt or 0)
    for res, amt in (base.get('produces') or {}).items():
        total_prod[res] = total_prod.get(res, 0) + int(amt or 0)
    for res, req in total_req.items():
        if req > total_prod.get(res, 0):
            return False
    return True


def _resource_shortfalls(figures: list[dict[str, Any]]) -> dict[str, int]:
    total_requires, total_produces = _resource_totals(figures)
    return {
        res: req - total_produces.get(res, 0)
        for res, req in total_requires.items()
        if req > total_produces.get(res, 0)
    }


def template_resource_deficit_map(figures: list[dict[str, Any]]) -> dict[int, bool]:
    """Return ``{figure_index: has_deficit}`` for generated template figures."""
    if not figures:
        return {}

    total_requires: dict[str, int] = {}
    for fig in figures:
        for res, amount in (fig.get('requires') or {}).items():
            total_requires[res] = total_requires.get(res, 0) + int(amount or 0)

    excluded: set[int] = set()
    stable = False
    total_produces: dict[str, int] = {}
    while not stable:
        stable = True
        total_produces = {}
        for idx, fig in enumerate(figures):
            if idx in excluded:
                continue
            for res, amount in (fig.get('produces') or {}).items():
                total_produces[res] = total_produces.get(res, 0) + int(amount or 0)
        for idx, fig in enumerate(figures):
            if idx in excluded or not fig.get('requires'):
                continue
            for res_name in fig.get('requires') or {}:
                if total_requires.get(res_name, 0) > total_produces.get(res_name, 0):
                    excluded.add(idx)
                    stable = False
                    break

    result = {}
    for idx, fig in enumerate(figures):
        has_deficit = False
        for res_name in fig.get('requires') or {}:
            if total_requires.get(res_name, 0) > total_produces.get(res_name, 0):
                has_deficit = True
                break
        result[idx] = has_deficit
    return result


def validate_ai_defence_template(template: dict[str, Any]) -> bool:
    """Return True when a generated AI template is structurally safe."""
    figures = list(template.get('figures') or [])
    moves = list(template.get('battle_moves') or [])
    if not figures or len(moves) != 3:
        return False
    if any(template_resource_deficit_map(figures).values()):
        return False
    battle_idx = int(template.get('battle_figure_index', 0) or 0)
    if battle_idx < 0 or battle_idx >= len(figures):
        return False
    fields = {fig.get('field') for fig in figures}
    required_call_fields = {
        'Call King': 'castle',
        'Call Military': 'military',
        'Call Villager': 'village',
    }
    for move in moves:
        family = move.get('family_name')
        if family in required_call_fields and required_call_fields[family] not in fields:
            return False
    return True


def _repair_resource_deficits(figures: list[dict[str, Any]], tier: int,
                              primary_suit: str, rng: random.Random) -> list[dict[str, Any]]:
    repaired = list(figures)
    castle_cap = int(tier)
    for _ in range(20):
        deficit_map = template_resource_deficit_map(repaired)
        if repaired and not any(deficit_map.values()):
            return repaired
        shortfalls = _resource_shortfalls(repaired)
        if not shortfalls:
            break
        added = False
        for resource in sorted(shortfalls):
            provider = AI_DEFENCE_RESOURCE_PROVIDERS.get(resource)
            if not provider:
                continue
            role, color = provider
            # Castle providers (king/maharaja) must not exceed the per-tier
            # castle cap.  If the cap is full, drop figures whose unmet
            # requirements bind the shortfall instead.
            if role in _CASTLE_ROLES and _count_castle_figures(repaired) >= castle_cap:
                # Remove the first figure that requires this resource (and
                # is not itself a castle figure) to bring totals back in line.
                victim_idx = None
                for idx, fig in enumerate(repaired):
                    if (fig.get('field') or '').lower() == 'castle':
                        continue
                    if int((fig.get('requires') or {}).get(resource, 0) or 0) > 0:
                        victim_idx = idx
                        break
                if victim_idx is not None:
                    repaired.pop(victim_idx)
                    added = True
                continue
            suit = _default_suit_for_color(color, primary_suit, rng)
            repaired.append(_make_figure(role, suit, tier, rng))
            added = True
        if not added:
            break
    return repaired


def _dagger(rank: str, suit: str, round_index: int) -> dict[str, Any]:
    return {
        'family_name': 'Dagger',
        'rank': rank,
        'suit': suit,
        'value': AI_DEFENCE_RANK_VALUES.get(rank, 0),
        'round_index': round_index,
        'card_type': 'main',
    }


def _call_move(family_name: str, rank: str, suit: str, value: int,
               round_index: int) -> dict[str, Any]:
    return {
        'family_name': family_name,
        'rank': rank,
        'suit': suit,
        'value': value,
        'round_index': round_index,
        'card_type': 'main',
    }


def _build_battle_moves(figures: list[dict[str, Any]], primary_suit: str,
                        rng: random.Random,
                        battle_plan: str) -> list[dict[str, Any]]:
    fields = {fig.get('field') for fig in figures}
    alt_suit = _same_color_alternate(primary_suit, rng)

    if battle_plan == 'overlord' and {'castle', 'military'} <= fields:
        return [
            _call_move('Block', 'Q', primary_suit, 2, 0),
            _call_move('Call Military', 'A', primary_suit, 3, 1),
            _call_move('Call King', 'K', alt_suit, 4, 2),
        ]
    if battle_plan == 'apex' and {'castle', 'military'} <= fields:
        return [
            _call_move('Call King', 'K', primary_suit, 4, 0),
            _call_move('Call Military', 'A', primary_suit, 3, 1),
            _dagger('10', primary_suit, 2),
        ]
    if battle_plan == 'sentinel' and {'castle', 'village'} <= fields:
        return [
            _call_move('Call King', 'K', primary_suit, 4, 0),
            _call_move('Call Villager', 'J', alt_suit, 1, 1),
            _dagger('10', primary_suit, 2),
        ]
    if battle_plan == 'bastion' and 'military' in fields:
        return [
            _call_move('Call Military', 'A', primary_suit, 3, 0),
            _dagger('10', primary_suit, 1),
            _dagger('9', alt_suit, 2),
        ]
    if battle_plan == 'warden' and 'castle' in fields:
        return [
            _call_move('Call King', 'K', primary_suit, 4, 0),
            _dagger('10', primary_suit, 1),
            _dagger('8', alt_suit, 2),
        ]
    return [
        _dagger('7', primary_suit, 0),
        _dagger('8', alt_suit, 1),
        _dagger('7', primary_suit, 2),
    ]


def _battle_figure_index(figures: list[dict[str, Any]], tier: int,
                         primary_suit: str) -> int:
    preferred_fields = ['military', 'castle', 'village'] if tier >= 3 else ['village', 'castle']
    for field in preferred_fields:
        for idx, fig in enumerate(figures):
            if fig.get('field') == field and fig.get('suit') == primary_suit:
                return idx
    for field in preferred_fields:
        for idx, fig in enumerate(figures):
            if fig.get('field') == field:
                return idx
    return 0


def _pick_scripted_spell(rules: dict[str, Any], key: str,
                         rng: random.Random) -> str | None:
    """Pick a prelude/counter spell from a weighted pool.

    ``key`` is ``'prelude'`` or ``'counter'``.  Pool entries are
    ``(spell_name_or_None, weight)`` tuples; the literal string ``'None'`` is
    also treated as the no-spell sentinel for convenience.  Falls back to the
    legacy ``f'{key}_spell_name'`` single value when no pool is configured.
    """
    pool = rules.get(f'{key}_spell_weights')
    if pool:
        normalized = []
        for entry in pool:
            if not isinstance(entry, (list, tuple)) or len(entry) != 2:
                continue
            name, weight = entry
            if isinstance(name, str) and name.strip().lower() == 'none':
                name = None
            normalized.append((name, weight))
        if normalized:
            return _weighted_choice(normalized, rng)
    legacy = rules.get(f'{key}_spell_name')
    return legacy if legacy else None


def _template_seed(land: Any) -> int:
    parts = (
        str(AI_DEFENCE_GENERATOR_VERSION),
        str(getattr(land, 'id', 0) or 0),
        str(getattr(land, 'col', 0) or 0),
        str(getattr(land, 'row', 0) or 0),
        str(getattr(land, 'tier', 1) or 1),
        str(getattr(land, 'suit_bonus_suit', '') or ''),
        str(getattr(land, 'suit_bonus_value', 0) or 0),
        str(getattr(land, 'ai_template_index', 0) or 0),
    )
    digest = hashlib.sha256('|'.join(parts).encode('utf-8')).hexdigest()
    return int(digest[:16], 16)


def _fallback_template(tier: int) -> dict[str, Any]:
    fallback = AI_DEFENCE_SAFE_FALLBACKS.get(tier) or AI_DEFENCE_SAFE_FALLBACKS[1]
    return copy.deepcopy(fallback)


def pick_ai_defence_seed(rng_module=random) -> int:
    """Return a compact random seed stored on ``Land.ai_template_index``."""
    return int(rng_module.randint(0, 2_147_483_647))


def generate_ai_defence_template_for_land(land: Any) -> dict[str, Any]:
    """Generate one concrete, validated AI defence template for ``land``."""
    tier = max(1, int(getattr(land, 'tier', 1) or 1))
    rules = AI_DEFENCE_GENERATION_RULES.get(tier) or AI_DEFENCE_GENERATION_RULES[1]
    rng = random.Random(_template_seed(land))
    primary_suit = _normalize_suit(getattr(land, 'suit_bonus_suit', None), rng)
    fortress_free_black = _is_black_land_fortress_free(primary_suit, rules, rng)

    figures = [
        _make_figure(
            role,
            _core_suit_for_role(
                role,
                primary_suit,
                idx,
                rules,
                rng,
                fortress_free_black,
            ),
            tier,
            rng,
        )
        for idx, role in enumerate(rules.get('core_roles', []))
    ]

    lo, hi = rules.get('optional_count_range', (0, 0))
    optional_target = rng.randint(int(lo), int(hi))
    optional_weights = rules.get('optional_role_weights') or [('farm_small', 1)]

    # Castle exact-N enforcement BEFORE optional draws.  Appending the extra
    # king/maharaja figures up front (mixing suits/colors) gives optional
    # feasibility checks access to the full anchor production base —
    # otherwise cross-color optional roles would always fail feasibility on
    # tiers whose core has a single primary-color king.
    castle_have = _count_castle_figures(figures)
    castle_need = max(0, int(tier) - castle_have)
    for _ in range(castle_need):
        role = 'maharaja' if rng.random() < EXTRA_CASTLE_MAHARAJA_CHANCE else 'king'
        cross_chance = float(rules.get('core_cross_color_chance', 0) or 0)
        if cross_chance > 0 and rng.random() < min(1.0, max(0.0, cross_chance)):
            suit = _opposite_color_suit(primary_suit, rng)
        else:
            suit = _same_color_alternate(primary_suit, rng)
        figures.append(_make_figure(role, suit, tier, rng))

    for _ in range(optional_target):
        chosen = None
        for _attempt in range(MAX_FEASIBILITY_RETRIES):
            role = _weighted_choice(optional_weights, rng)
            if fortress_free_black and role in _FORTRESS_ROLES:
                suit = _opposite_color_suit(primary_suit, rng)
            else:
                suit = _choose_optional_suit(primary_suit, tier, rng)
            if _optional_role_is_feasible(role, suit, figures, rng, tier):
                chosen = _make_figure(role, suit, tier, rng)
                break
        if chosen is not None:
            figures.append(chosen)

    figures = _repair_resource_deficits(figures, tier, primary_suit, rng)

    final_castle = _count_castle_figures(figures)
    if final_castle != int(tier):
        logger.warning(
            'AI defence castle invariant: tier=%s expected %s castle figures, got %s (land=%s)',
            tier, tier, final_castle, getattr(land, 'id', None),
        )
    moves = _build_battle_moves(
        figures,
        primary_suit,
        rng,
        str(rules.get('battle_plan') or 'border'),
    )
    prelude_spell = _pick_scripted_spell(rules, 'prelude', rng)
    counter_spell = _pick_scripted_spell(rules, 'counter', rng)
    template = {
        'ai_name': f'{primary_suit} {AI_DEFENCE_TIER_NAMES.get(tier, "Defenders")}',
        'figures': figures,
        'battle_moves': moves,
        'battle_figure_index': _battle_figure_index(figures, tier, primary_suit),
        'battle_modifier': None,
        'spell': None,
        'prelude_spell_name': prelude_spell,
        'prelude_spell_data': copy.deepcopy(rules.get('prelude_spell_data')) if prelude_spell else None,
        'counter_spell_name': counter_spell,
        'counter_spell_data': copy.deepcopy(rules.get('counter_spell_data')) if counter_spell else None,
        'auto_gamble': bool(rules.get('auto_gamble', False)),
        'auto_gamble_threshold': int(rules.get('auto_gamble_threshold', 10)),
    }

    if validate_ai_defence_template(template):
        return template

    logger.warning(
        'Generated invalid AI defence template for land=%s tier=%s suit=%s; using fallback',
        getattr(land, 'id', None),
        tier,
        primary_suit,
    )
    return _fallback_template(tier)


def get_ai_defence_template_for_land(land: Any) -> dict[str, Any]:
    """Public accessor for AI land defence templates.

    All runtime paths must call this instead of reading static template lists so
    battle setup, rewards, and map serialization stay consistent.
    """
    return generate_ai_defence_template_for_land(land)
