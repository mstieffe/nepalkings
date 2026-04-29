# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Kingdom service — map seeding, gold production, config validation."""

import math
import random
from datetime import datetime, timezone

from ai.defence.generator import pick_ai_defence_seed
import server_settings as config
from models import (db, User, Land, Kingdom, KingdomCosmeticUnlock,
                    KingdomSkillAllocation, KingdomNotification,
                    CollectionCard, LandConfigFigure,
                    LandConfig, LandConfigBattleMove)


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _default_kingdom_style():
    return dict(getattr(config, 'KINGDOM_DEFAULT_STYLE', {}) or {
        'flag_key': 'flag_plain',
        'border_key': 'border_simple_gold',
        'surface_key': 'surface_plain',
    })


def _cosmetic_catalog():
    return getattr(config, 'KINGDOM_COSMETIC_CATALOG', {}) or {}


def default_unlocked_cosmetic_keys():
    return {key for key, item in _cosmetic_catalog().items()
            if int(item.get('price_gold', 0) or 0) <= 0}


def create_kingdom(owner_user_id, source_kingdom=None):
    """Create a persistent kingdom at level 1 with starter SP.

    When ``source_kingdom`` is provided (e.g. a kingdom that just split into
    two components), copy player-paid cosmetic assets (style, shield_until,
    cosmetic unlocks) so the player doesn't lose what they bought, but reset
    progression: every freshly minted kingdom starts at level 1 with 0 XP and
    ``KINGDOM_SKILL_POINTS_PER_LEVEL`` skill points granted.  Skills are NOT
    copied — splits do not duplicate progression.
    """
    defaults = _default_kingdom_style()
    if source_kingdom:
        defaults = source_kingdom.serialize_style()
    starter_sp = int(getattr(config, 'KINGDOM_SKILL_POINTS_PER_LEVEL', 3) or 0)
    kingdom = Kingdom(
        owner_user_id=owner_user_id,
        flag_key=defaults['flag_key'],
        border_key=defaults['border_key'],
        surface_key=defaults['surface_key'],
        shield_until=source_kingdom.shield_until if source_kingdom else None,
        level=1,
        experience=0,
        skill_points_granted=starter_sp,
        pending_gold=0.0,
        last_gold_collection_at=_utcnow(),
    )
    db.session.add(kingdom)
    db.session.flush()

    if source_kingdom:
        copied_unlocks = {
            key for (key,) in db.session.query(KingdomCosmeticUnlock.cosmetic_key)
            .filter_by(kingdom_id=source_kingdom.id)
            .all()
        }
        for key in copied_unlocks:
            if key not in default_unlocked_cosmetic_keys():
                db.session.add(KingdomCosmeticUnlock(
                    kingdom_id=kingdom.id, cosmetic_key=key))
    return kingdom


# ── Map Seeding ──────────────────────────────────────────────────────────────


def _pick_gold_rate(tier):
    lo, hi = config.LAND_GOLD_RATE_RANGES[tier]
    return round(random.uniform(lo, hi), 2)


def _pick_suit_bonus_value(tier):
    lo, hi = config.LAND_SUIT_BONUS_RANGES[tier]
    return random.randint(lo, hi)


def kingdom_neighbor_coords(col, row):
    """Return adjacent odd-q flat-top hex coordinates for ``(col, row)``."""
    if col % 2 == 0:
        return [
            (col + 1, row - 1), (col + 1, row),
            (col, row + 1),
            (col - 1, row), (col - 1, row - 1),
            (col, row - 1),
        ]
    return [
        (col + 1, row), (col + 1, row + 1),
        (col, row + 1),
        (col - 1, row + 1), (col - 1, row),
        (col, row - 1),
    ]


def _odd_q_to_cube(col, row):
    """Convert odd-q offset coords to cube coords for hex distance."""
    x = col
    z = row - (col - (col & 1)) // 2
    y = -x - z
    return x, y, z


def _hex_distance(c1, r1, c2, r2):
    """Hex distance between two odd-q coordinates."""
    x1, y1, z1 = _odd_q_to_cube(c1, r1)
    x2, y2, z2 = _odd_q_to_cube(c2, r2)
    return (abs(x1 - x2) + abs(y1 - y2) + abs(z1 - z2)) // 2


def _odd_q_to_world(col, row):
    """Project odd-q coordinates to 2D world space with unit neighbour step."""
    q, _, r = _odd_q_to_cube(col, row)
    return q + (r / 2.0), (math.sqrt(3.0) / 2.0) * r


def _pick_cluster_seeds(cols, rows, n_clusters):
    """Pick ``n_clusters`` seed hexes using Mitchell's best-candidate sampler.

    Each new seed is the candidate (out of several random picks) that maximises
    the minimum distance to already-chosen seeds.  This produces well-spaced
    Voronoi seeds without manual quadrant placement.
    """
    seeds = []
    all_coords = [(c, r) for r in range(rows) for c in range(cols)]
    if not all_coords:
        return seeds
    # First seed is fully random.
    seeds.append(random.choice(all_coords))
    candidate_pool = max(8, 2 * n_clusters)
    while len(seeds) < n_clusters:
        best, best_dist = None, -1
        for _ in range(candidate_pool):
            cand = random.choice(all_coords)
            if cand in seeds:
                continue
            d = min(_hex_distance(cand[0], cand[1], s[0], s[1]) for s in seeds)
            if d > best_dist:
                best, best_dist = cand, d
        if best is None:
            break
        seeds.append(best)
    return seeds


def _build_cluster_suits(clusters_per_suit):
    """Return a shuffled suit list with equal cluster count per suit."""
    count = max(1, int(clusters_per_suit))
    cluster_suits = []
    for suit in ('Hearts', 'Diamonds', 'Clubs', 'Spades'):
        cluster_suits.extend([suit] * count)
    random.shuffle(cluster_suits)
    return cluster_suits


def _cluster_radius_bounds(tier_count):
    """Return valid inclusive cluster-radius bounds after cap enforcement."""
    radius_range = getattr(config, 'KINGDOM_MAP_CLUSTER_RADIUS_RANGE', (4, 7))
    radius_min = max(1, int(radius_range[0]))
    radius_max = max(radius_min, int(radius_range[1]))

    border_cap = max(
        0,
        int(getattr(config, 'KINGDOM_MAP_TIER1_BORDER_MAX_HEXES', 3)),
    )
    max_allowed = max(1, int(tier_count) + border_cap - 2)
    radius_max = min(radius_max, max_allowed)
    radius_min = min(radius_min, radius_max)
    return radius_min, radius_max


def _build_cluster_profiles(seeds, tier_count):
    """Build per-cluster shape profile (radius, anisotropy, orientation)."""
    anis_range = getattr(config, 'KINGDOM_MAP_CLUSTER_ANISOTROPY_RANGE', (1.2, 2.1))
    anis_min = max(1.0, float(anis_range[0]))
    anis_max = max(anis_min, float(anis_range[1]))
    radius_min, radius_max = _cluster_radius_bounds(tier_count)

    profiles = []
    for _ in seeds:
        profiles.append({
            'radius': random.randint(radius_min, radius_max),
            'anisotropy': random.uniform(anis_min, anis_max),
            'angle': random.uniform(0.0, math.tau),
        })
    return profiles


def _deterministic_boundary_noise(col, row, seed_col, seed_row, cluster_idx):
    """Return smooth deterministic noise in ``[-1, 1]`` for boundary variation."""
    phase = (seed_col * 0.173) + (seed_row * 0.319) + ((cluster_idx + 1) * 0.571)
    v1 = math.sin((col + phase) * 0.73 + (row - phase) * 1.17)
    v2 = math.sin((col - phase) * 1.31 - (row + phase) * 0.59)
    return (v1 + 0.5 * v2) / 1.5


def _cluster_distance(col, row, seed, profile, cluster_idx, noise_strength):
    """Return anisotropic, noise-perturbed distance from ``(col,row)`` to seed."""
    px, py = _odd_q_to_world(col, row)
    sx, sy = _odd_q_to_world(seed[0], seed[1])
    dx = px - sx
    dy = py - sy

    ca = math.cos(profile['angle'])
    sa = math.sin(profile['angle'])
    major = dx * ca + dy * sa
    minor = -dx * sa + dy * ca

    anis = max(1.0, float(profile['anisotropy']))
    base = math.sqrt((major / anis) ** 2 + (minor * anis) ** 2)
    if noise_strength <= 0.0:
        return base

    noise = _deterministic_boundary_noise(col, row, seed[0], seed[1], cluster_idx)
    return max(0.0, base + (noise_strength * noise))


def _assign_voronoi_regions(cols, rows, seeds, cluster_profiles):
    """Assign each hex to its nearest shaped cluster; ties/out-of-range are neutral.

    Returns ``{(col, row): seed_index_or_None}`` where ``None`` marks neutral
    hexes.
    """
    if len(seeds) != len(cluster_profiles):
        raise ValueError('cluster profile count must match seed count')

    noise_strength = max(
        0.0,
        float(getattr(config, 'KINGDOM_MAP_BOUNDARY_NOISE_STRENGTH', 0.0)),
    )

    assignment = {}
    tie_eps = 1e-9
    for r in range(rows):
        for c in range(cols):
            best_idx, best_d, tied = -1, 10 ** 9, False
            for idx, seed in enumerate(seeds):
                d = _cluster_distance(
                    c,
                    r,
                    seed,
                    cluster_profiles[idx],
                    idx,
                    noise_strength,
                )
                if d + tie_eps < best_d:
                    best_d, best_idx, tied = d, idx, False
                elif abs(d - best_d) <= tie_eps:
                    tied = True

            radius = cluster_profiles[best_idx]['radius'] if best_idx >= 0 else 0
            if tied or best_idx < 0 or best_d > radius:
                assignment[(c, r)] = None
            else:
                assignment[(c, r)] = best_idx
    return assignment


def _mark_border_neutrals(assignment):
    """Promote any hex that has a same-distance, different-cluster neighbour
    to neutral, ensuring at least a 1-hex visible gap between clusters."""
    neutralised = set()
    for (c, r), idx in assignment.items():
        if idx is None:
            continue
        for n in kingdom_neighbor_coords(c, r):
            n_idx = assignment.get(n)
            if n_idx is not None and n_idx != idx:
                neutralised.add((c, r))
                break
    for coord in neutralised:
        assignment[coord] = None
    return assignment


def _pick_cluster_peaks(assignment, seeds):
    """Choose 1..N apex hexes per cluster to vary the peak shape.

    The seed itself is always a peak.  Additional peaks are picked from the
    seed's same-cluster neighbours, then expanded outward by one ring per
    extra peak slot, so apex plateaux look like small irregular tops rather
    than a single hex.

    Returns a list of frozensets, one per cluster.
    """
    plateau_range = getattr(
        config, 'KINGDOM_MAP_PEAK_PLATEAU_RANGE', (1, 1))
    plateau_min = max(1, int(plateau_range[0]))
    plateau_max = max(plateau_min, int(plateau_range[1]))
    peak_sets = []
    for idx, seed in enumerate(seeds):
        target = random.randint(plateau_min, plateau_max)
        peaks = {seed}
        frontier = [seed]
        while len(peaks) < target and frontier:
            candidates = []
            for (c, r) in frontier:
                for n in kingdom_neighbor_coords(c, r):
                    if n in peaks:
                        continue
                    if assignment.get(n) == idx:
                        candidates.append(n)
            if not candidates:
                break
            random.shuffle(candidates)
            for cand in candidates:
                if len(peaks) >= target:
                    break
                peaks.add(cand)
            frontier = list(peaks)
        peak_sets.append(frozenset(peaks))
    return peak_sets


def _tier_for_cluster_hex(col, row, peaks, tier_count):
    """Elevation: tier = clamp(tier_count - distance_to_nearest_peak)."""
    d = min(_hex_distance(col, row, pc, pr) for (pc, pr) in peaks)
    return max(1, min(tier_count, tier_count - d))


def _pick_neutral_tier(tier_count):
    """Pick a tier for a neutral land (never the apex tier)."""
    neutral_probs = getattr(config, 'LAND_NEUTRAL_TIER_PROBABILITIES', None)
    if neutral_probs:
        tiers = list(neutral_probs.keys())
        weights = [neutral_probs[t] for t in tiers]
        return random.choices(tiers, weights=weights, k=1)[0]
    # Fallback: drop the apex tier from cluster weights and renormalise.
    base = {t: w for t, w in config.LAND_TIER_PROBABILITIES.items()
            if t < tier_count}
    total = sum(base.values()) or 1.0
    tiers = list(base.keys())
    weights = [base[t] / total for t in tiers]
    return random.choices(tiers, weights=weights, k=1)[0]


def seed_kingdom_map():
    """Generate the kingdom hex map if it doesn't exist yet.

    The map is built as a landscape:
            * Build an equal per-suit cluster list where each suit appears exactly
                ``KINGDOM_MAP_CLUSTERS_PER_SUIT`` times, then shuffle it.
            * Pick one well-spaced seed hex per cluster; each seed becomes the
                centre of its preassigned suit cluster.
            * Give each cluster its own anisotropy/orientation/radius profile and
                assign hexes by shaped distance plus deterministic boundary noise.
      * Assign every hex to its nearest seed (Voronoi).  Hexes equidistant to
        two seeds, or whose nearest neighbour belongs to a different cluster,
        become neutral — forming visible "rivers" between kingdoms.
      * Tier acts as elevation: peak hex (the seed) is ``KINGDOM_TIER_COUNT``,
        decreasing by one per hex of distance to the seed.
      * Neutral hexes use ``LAND_NEUTRAL_TIER_PROBABILITIES`` (apex tier
        excluded) and have no suit bonus (``suit_bonus_suit='Neutral'``,
        ``suit_bonus_value=0``).
    """
    if Land.query.first() is not None:
        return  # already seeded

    cols = config.KINGDOM_MAP_COLS
    rows = config.KINGDOM_MAP_ROWS
    tier_count = getattr(config, 'KINGDOM_TIER_COUNT', 3)
    clusters_per_suit = max(
        1, int(getattr(config, 'KINGDOM_MAP_CLUSTERS_PER_SUIT', 1)))
    cluster_suits = _build_cluster_suits(clusters_per_suit)
    n_clusters = len(cluster_suits)
    neutral_suit = getattr(config, 'LAND_NEUTRAL_SUIT', 'Neutral')

    seeds = _pick_cluster_seeds(cols, rows, n_clusters)
    cluster_profiles = _build_cluster_profiles(seeds, tier_count)

    assignment = _assign_voronoi_regions(cols, rows, seeds, cluster_profiles)
    assignment = _mark_border_neutrals(assignment)
    peak_sets = _pick_cluster_peaks(assignment, seeds)

    for r in range(rows):
        for c in range(cols):
            cluster_idx = assignment.get((c, r))
            if cluster_idx is None:
                tier = _pick_neutral_tier(tier_count)
                suit = neutral_suit
                bonus_val = 0
            else:
                peaks = peak_sets[cluster_idx]
                tier = _tier_for_cluster_hex(c, r, peaks, tier_count)
                suit = cluster_suits[cluster_idx]
                bonus_val = _pick_suit_bonus_value(tier)
            land = Land(
                col=c,
                row=r,
                tier=tier,
                gold_rate=_pick_gold_rate(tier),
                suit_bonus_suit=suit,
                suit_bonus_value=bonus_val,
                ai_template_index=pick_ai_defence_seed(random),
            )
            db.session.add(land)

    db.session.commit()


# ── Connected kingdoms / skills ─────────────────────────────────────────────


def compute_owned_land_components(lands=None):
    """Compute connected owned-land components.

    Returns ``(land_info_by_id, components_by_user)``.  Each land info row is
    intentionally serializable so route payloads can include it directly.
    """
    if lands is None:
        lands = Land.query.filter(Land.owner_user_id.isnot(None)).all()
    else:
        lands = [land for land in lands if land.owner_user_id is not None]

    by_coord = {(land.col, land.row): land for land in lands}
    visited = set()
    land_info = {}
    components_by_user = {}
    owner_component_counts = {}

    for start in sorted(lands, key=lambda l: (l.owner_user_id, l.row, l.col, l.id)):
        if start.id in visited:
            continue
        owner_id = start.owner_user_id
        owner_component_counts[owner_id] = owner_component_counts.get(owner_id, 0) + 1
        component_index = owner_component_counts[owner_id]
        component_id = f'{owner_id}:{component_index}'

        stack = [start]
        visited.add(start.id)
        component_lands = []
        while stack:
            land = stack.pop()
            component_lands.append(land)
            for coord in kingdom_neighbor_coords(land.col, land.row):
                neighbour = by_coord.get(coord)
                if not neighbour or neighbour.id in visited:
                    continue
                if neighbour.owner_user_id != owner_id:
                    continue
                visited.add(neighbour.id)
                stack.append(neighbour)

        size = len(component_lands)
        raw_gold_rate = round(sum(float(land.gold_rate or 0) for land in component_lands), 3)
        component = {
            'component_id': component_id,
            'owner_user_id': owner_id,
            'land_ids': [land.id for land in component_lands],
            'size': size,
            'level': 0,
            'name': 'Outpost',
            'bonuses': {},
            'raw_gold_rate': raw_gold_rate,
            'effective_gold_rate': raw_gold_rate,
        }
        components_by_user.setdefault(owner_id, []).append(component)

        for land in component_lands:
            land_info[land.id] = {
                'kingdom_component_id': component_id,
                'kingdom_component_size': size,
                'kingdom_level': 0,
                'kingdom_tier_name': 'Outpost',
                'kingdom_bonuses': {},
                'kingdom_raw_gold_rate': raw_gold_rate,
                'kingdom_effective_gold_rate': raw_gold_rate,
            }

    for components in components_by_user.values():
        components.sort(key=lambda c: (-c['size'], c['component_id']))

    return land_info, components_by_user


def summarize_user_kingdom(user_id, lands=None):
    """Return connected-kingdom summary for a single user."""
    if lands is None:
        user_lands = Land.query.filter_by(owner_user_id=user_id).all()
    else:
        user_lands = [land for land in lands if land.owner_user_id == user_id]
    info_by_land, components_by_user = compute_owned_land_components(user_lands)
    components = components_by_user.get(user_id, [])
    raw_rate = round(sum(float(land.gold_rate or 0) for land in (user_lands or [])), 3)
    effective_rate = round(sum(c.get('effective_gold_rate', 0.0) for c in components), 3)
    strongest = components[0] if components else None
    return {
        'components': components,
        'largest_component_size': strongest['size'] if strongest else 0,
        'level': strongest['level'] if strongest else 0,
        'tier_name': strongest['name'] if strongest else 'Outpost',
        'bonuses': dict(strongest.get('bonuses') or {}) if strongest else {},
        'raw_gold_rate': raw_rate,
        'effective_gold_rate': effective_rate,
        'land_info': info_by_land,
    }


def effective_gold_rate_for_lands(lands):
    """Return effective gold/hour after persistent kingdom gold bonuses."""
    land_by_id = {land.id: land for land in lands}
    _, components_by_user = compute_owned_land_components(lands)
    total = 0.0
    for components in components_by_user.values():
        for component in components:
            comp_lands = [land_by_id[land_id] for land_id in component.get('land_ids', [])
                          if land_id in land_by_id]
            raw = sum(float(land.gold_rate or 0) for land in comp_lands)
            multiplier = 1.0
            kingdom_id = None
            for land in comp_lands:
                kingdom_id = land.kingdom_id
                if kingdom_id:
                    break
            if kingdom_id:
                multiplier = kingdom_gold_multiplier(db.session.get(Kingdom, kingdom_id))
            total += raw * multiplier
    if not components_by_user:
        total = sum(float(land.gold_rate or 0) for land in lands)
    return round(total, 3)


def get_user_kingdom_bonuses_for_land(user_id, land_id):
    """Return bonuses for the connected component containing ``land_id``."""
    land = db.session.get(Land, land_id)
    if not land or land.owner_user_id != user_id or not land.kingdom_id:
        return {}
    kingdom = db.session.get(Kingdom, land.kingdom_id)
    return kingdom_skill_bonuses(kingdom)


def conquer_cooldown_seconds_for_target(user_id, target_land):
    """Return base conquer cooldown for a target.

    The legacy adjacency discount has been removed; this returns the raw
    configured cooldown so callers may still consult a single source of
    truth.
    """
    return int(getattr(config, 'CONQUER_COOLDOWN_SECONDS', 0) or 0)


def kingdom_shield_block_reason(land, now=None):
    """Return ``(remaining_seconds, kingdom, reason)`` if the land is protected.

    ``reason`` is one of ``'shield'`` (timed kingdom shield active) or
    ``'core_protection'`` (last-N-lands permanent skill active).  When neither
    applies the result is ``(0, kingdom_or_None, None)``.

    For ``'core_protection'`` the returned ``remaining_seconds`` is a sentinel
    ``-1`` so callers can distinguish "permanent" from "0 seconds left".
    Centralised so every conquer entry-point applies the same rule.
    """
    if not land or not getattr(land, 'kingdom_id', None):
        return 0, None, None
    kingdom = db.session.get(Kingdom, land.kingdom_id)
    if not kingdom:
        return 0, None, None
    now = now or _utcnow()
    if kingdom.shield_until:
        remaining = int((kingdom.shield_until - now).total_seconds())
        if remaining > 0:
            return remaining, kingdom, 'shield'
    # Core protection: when the kingdom has shrunk to <= protected_count
    # lands, ALL of those lands are permanently shielded.
    if kingdom_core_protection_active(kingdom):
        return -1, kingdom, 'core_protection'
    return 0, kingdom, None


# ── Persistent kingdom configuration ────────────────────────────────────────

def _connected_land_components_for_lands(lands):
    """Return connected components for a single user's land list."""
    by_coord = {(land.col, land.row): land for land in lands}
    visited = set()
    components = []
    for start in sorted(lands, key=lambda l: (l.row, l.col, l.id)):
        if start.id in visited:
            continue
        stack = [start]
        visited.add(start.id)
        comp = []
        while stack:
            land = stack.pop()
            comp.append(land)
            for coord in kingdom_neighbor_coords(land.col, land.row):
                neighbour = by_coord.get(coord)
                if neighbour and neighbour.id not in visited:
                    visited.add(neighbour.id)
                    stack.append(neighbour)
        components.append(comp)
    return components


# ── Skills (data-driven via kingdom_progression.KINGDOM_SKILL_DEFINITIONS) ──

def _skill_keys():
    return tuple(d.key for d in (config.KINGDOM_SKILL_DEFINITIONS or ()))


def kingdom_skill_allocations(kingdom_id):
    """Return ``{skill_key: KingdomSkillAllocation}`` for ``kingdom_id``.

    Missing rows are created at level 0 so callers can read levels uniformly.
    Allocation rows for skill keys no longer in ``KINGDOM_SKILL_DEFINITIONS``
    are returned as-is (read-only) but won't be created automatically.
    """
    rows = KingdomSkillAllocation.query.filter_by(kingdom_id=kingdom_id).all()
    by_key = {row.skill_key: row for row in rows}
    for skill_key in _skill_keys():
        if skill_key not in by_key:
            row = KingdomSkillAllocation(
                kingdom_id=kingdom_id, skill_key=skill_key, level=0)
            db.session.add(row)
            by_key[skill_key] = row
    db.session.flush()
    return by_key


def kingdom_skill_level(kingdom_id, skill_key):
    """Return the current allocated level for ``skill_key`` (0 if missing)."""
    row = KingdomSkillAllocation.query.filter_by(
        kingdom_id=kingdom_id, skill_key=skill_key).first()
    return int(row.level or 0) if row else 0


def kingdom_total_skill_points(kingdom):
    """Return total SP granted to the kingdom by its current level."""
    if not kingdom:
        return 0
    return int(kingdom.skill_points_granted or 0)


def kingdom_spent_skill_points(kingdom_id):
    """Sum SP committed across all allocated skill levels."""
    total = 0
    for row in KingdomSkillAllocation.query.filter_by(kingdom_id=kingdom_id).all():
        total += int(config.skill_total_cost_for_level(row.skill_key, row.level) or 0)
    return total


def kingdom_skill_bonuses(kingdom):
    """Return effect values keyed by skill_key for the kingdom's allocations.

    The result currently feeds gold multipliers, shield discounts, and core
    protection — combat power skills were removed in the kingdom-levels
    rework.  Keys absent from the dict mean "skill not invested".
    """
    if not kingdom:
        return {}
    rows = KingdomSkillAllocation.query.filter_by(kingdom_id=kingdom.id).all()
    bonuses = {}
    for row in rows:
        sdef = config.skill_definition(row.skill_key)
        if not sdef:
            continue
        level = max(0, min(int(row.level or 0), sdef.max_level))
        if level <= 0:
            continue
        bonuses[row.skill_key] = config.skill_effect_at_level(row.skill_key, level)
    return bonuses


def describe_kingdom_bonuses(bonuses):
    """Return short player-facing description lines for active bonuses."""
    if not bonuses:
        return []
    lines = []
    gold_bonus = float(bonuses.get('gold_production', 0.0) or 0.0)
    if gold_bonus:
        lines.append(f'+{int(round(gold_bonus * 100))}% gold production')
    shield_reduction = float(bonuses.get('shield_cost_reduction', 0.0) or 0.0)
    if shield_reduction:
        lines.append(f'-{int(round(shield_reduction * 100))}% shield cost')
    vault_cap = bonuses.get('gold_vault')
    if vault_cap:
        lines.append(f'Vault capacity {int(vault_cap)} gold')
    core = int(bonuses.get('core_protection', 0) or 0)
    if core:
        lines.append(f'Last {core} land(s) cannot be conquered')
    return lines


def kingdom_gold_multiplier(kingdom):
    """1.0 + the gold_production skill effect for the kingdom."""
    bonuses = kingdom_skill_bonuses(kingdom)
    return 1.0 + float(bonuses.get('gold_production', 0.0) or 0.0)


# ── XP / Levelling ─────────────────────────────────────────────────────────

def award_kingdom_xp(kingdom, amount, *, reason=None):
    """Add XP to a kingdom and apply any level-up consequences.

    Returns ``(levels_gained, sp_gained)`` for callers that want to surface a
    notification.  Side effects: ``kingdom.experience``,
    ``kingdom.level``, ``kingdom.skill_points_granted`` are updated in-place
    and a ``KingdomNotification`` row of kind ``xp_gained`` (and one
    ``level_up`` row per level gained) is queued.
    """
    if not kingdom or not amount:
        return 0, 0
    amount = int(amount)
    if amount <= 0:
        return 0, 0
    old_level = int(kingdom.level or 1)
    new_total_xp = int(kingdom.experience or 0) + amount
    new_level = config.kingdom_level_for_total_xp(new_total_xp)
    levels_gained = max(0, new_level - old_level)
    sp_gained = levels_gained * int(config.KINGDOM_SKILL_POINTS_PER_LEVEL)
    kingdom.experience = new_total_xp
    if levels_gained:
        kingdom.level = new_level
        kingdom.skill_points_granted = int(kingdom.skill_points_granted or 0) + sp_gained
    kingdom.updated_at = _utcnow()

    # Notifications (best-effort — never raise inside the awarding helper).
    try:
        db.session.add(KingdomNotification(
            user_id=kingdom.owner_user_id,
            kingdom_id=kingdom.id,
            kind='xp_gained',
            payload={'amount': amount, 'reason': reason or 'conquer',
                     'total_xp': new_total_xp, 'level': new_level},
        ))
        if levels_gained:
            db.session.add(KingdomNotification(
                user_id=kingdom.owner_user_id,
                kingdom_id=kingdom.id,
                kind='level_up',
                payload={'old_level': old_level, 'new_level': new_level,
                         'sp_gained': sp_gained},
            ))
    except Exception:
        pass
    return levels_gained, sp_gained


# ── Gold vault ─────────────────────────────────────────────────────────────

def kingdom_vault_cap(kingdom):
    """Vault capacity in gold for ``kingdom``."""
    if not kingdom:
        return int(config.KINGDOM_VAULT_DEFAULT_CAP)
    level = kingdom_skill_level(kingdom.id, 'gold_vault')
    return int(config.vault_cap_for_skill_level(level))


def _pending_gold_snapshot(kingdom, now=None):
    """Return accrued pending gold for ``kingdom`` without mutating it."""
    if not kingdom:
        return 0.0, int(config.KINGDOM_VAULT_DEFAULT_CAP), 0.0
    now = now or _utcnow()
    cap = int(kingdom_vault_cap(kingdom))
    pending = float(kingdom.pending_gold or 0.0)
    last = kingdom.last_gold_collection_at or kingdom.created_at or now
    elapsed_seconds = max(0.0, (now - last).total_seconds())
    rate = kingdom_gold_rate_per_hour(kingdom)
    earned = rate * (elapsed_seconds / 3600.0)
    return min(float(cap), pending + earned), cap, rate


def kingdom_vault_state(kingdom, *, now=None):
    """Return a fresh snapshot dict for the kingdom's gold vault (no side effects).

    ``{pending, cap, full, rate_per_hour}``.  Rate is the kingdom's gold
    production per hour at its current land/skill levels. Pending gold is
    accrued up to ``now`` in the returned snapshot but is not written back.
    """
    if not kingdom:
        return {'pending': 0.0, 'cap': int(config.KINGDOM_VAULT_DEFAULT_CAP),
                'full': False, 'rate_per_hour': 0.0}
    pending, cap, rate = _pending_gold_snapshot(kingdom, now=now)
    return {
        'pending': pending,
        'cap': cap,
        'full': pending >= cap - 1e-6,
        'rate_per_hour': rate,
    }


def kingdom_gold_rate_per_hour(kingdom):
    """Per-hour gold production rate across all lands owned by ``kingdom``.

    Sums each land's configured base rate and applies the kingdom's
    ``gold_production`` multiplier.  Returns 0 for empty/None kingdoms.
    """
    if not kingdom:
        return 0.0
    base_rate = 0.0
    for land in Land.query.filter_by(kingdom_id=kingdom.id).all():
        base_rate += float(getattr(land, 'gold_rate', 0.0) or 0.0)
    return base_rate * kingdom_gold_multiplier(kingdom)


def _accrue_pending_gold(kingdom, now=None):
    """Advance ``kingdom.pending_gold`` based on time since last collection.

    Capped at the vault cap.  Returns the delta added (>= 0).  No commit.
    """
    if not kingdom:
        return 0.0
    now = now or _utcnow()
    last = kingdom.last_gold_collection_at or kingdom.created_at or now
    elapsed_seconds = max(0.0, (now - last).total_seconds())
    rate_per_hour = kingdom_gold_rate_per_hour(kingdom)
    earned = rate_per_hour * (elapsed_seconds / 3600.0)
    cap = float(kingdom_vault_cap(kingdom))
    pending = float(kingdom.pending_gold or 0.0)
    new_pending = min(cap, pending + earned)
    delta = new_pending - pending
    kingdom.pending_gold = new_pending
    kingdom.last_gold_collection_at = now
    return delta


def collect_kingdom_gold(kingdom, user, *, now=None):
    """Atomically collect a kingdom's pending gold into ``user.gold``.

    Advances pending up to ``now`` first, then transfers the full pending
    balance to the user, resets ``pending_gold`` to 0, and stamps
    ``last_gold_collection_at``.  Returns ``(collected_int, vault_cap, user_gold_after)``.
    """
    if not kingdom or not user:
        return 0, int(config.KINGDOM_VAULT_DEFAULT_CAP), int(getattr(user, 'gold', 0) or 0)
    now = now or _utcnow()
    _accrue_pending_gold(kingdom, now=now)
    cap = kingdom_vault_cap(kingdom)
    pending = float(kingdom.pending_gold or 0.0)
    collected = int(pending)  # truncate fractional gold
    if collected > 0:
        user.gold = int(getattr(user, 'gold', 0) or 0) + collected
        kingdom.pending_gold = max(0.0, pending - collected)
    kingdom.last_gold_collection_at = now
    kingdom.updated_at = now
    return collected, cap, int(user.gold or 0)


# ── Core Protection ────────────────────────────────────────────────────────

def kingdom_core_protection_active(kingdom):
    """True iff the kingdom's land count is <= the core_protection skill effect."""
    if not kingdom:
        return False
    level = kingdom_skill_level(kingdom.id, 'core_protection')
    if level <= 0:
        return False
    protected_count = int(config.skill_effect_at_level('core_protection', level) or 0)
    if protected_count <= 0:
        return False
    land_count = Land.query.filter_by(kingdom_id=kingdom.id).count()
    return land_count <= protected_count



def _delete_kingdom_row(kingdom):
    """Delete a persistent kingdom and dependent config rows.

    Refuses to delete a kingdom that still owns Land rows, to avoid leaving
    Land.kingdom_id pointing to a deleted FK target.
    """
    if not kingdom:
        return None
    if Land.query.filter_by(kingdom_id=kingdom.id).first() is not None:
        return None
    info = {
        'id': kingdom.id,
        'name': kingdom.name or f'Kingdom #{kingdom.id}',
        'owner_user_id': kingdom.owner_user_id,
    }
    KingdomCosmeticUnlock.query.filter_by(kingdom_id=kingdom.id).delete()
    KingdomSkillAllocation.query.filter_by(kingdom_id=kingdom.id).delete()
    KingdomNotification.query.filter_by(kingdom_id=kingdom.id).delete()
    db.session.delete(kingdom)
    return info


def delete_orphan_kingdoms(owner_user_id=None, commit=False):
    """Delete kingdoms that no longer own any land.

    Returns a list of deleted kingdom descriptors so callers can attach
    user-visible notifications to the land-loss event that caused the cleanup.
    """
    query = Kingdom.query
    if owner_user_id is not None:
        query = query.filter_by(owner_user_id=owner_user_id)
    deleted = []
    for kingdom in list(query.order_by(Kingdom.id).all()):
        has_land = Land.query.filter_by(kingdom_id=kingdom.id).first() is not None
        if has_land:
            continue
        info = _delete_kingdom_row(kingdom)
        if info:
            deleted.append(info)
    if commit:
        db.session.commit()
    return deleted


def serialize_land_with_kingdom_context(land):
    """Serialize a land and include persistent kingdom skill visibility fields."""
    if not land:
        return None
    data = land.serialize()
    kingdom = db.session.get(Kingdom, land.kingdom_id) if land.kingdom_id else None
    if not kingdom:
        data.update({
            'kingdom_name': None,
            'kingdom_bonuses': {},
            'kingdom_skill_effects': [],
            'kingdom_shield_remaining': 0,
            'kingdom_is_shielded': False,
        })
        return data
    bonuses = kingdom_skill_bonuses(kingdom)
    now = _utcnow()
    shield_remaining = 0
    if kingdom.shield_until:
        shield_remaining = max(0, int((kingdom.shield_until - now).total_seconds()))
    data.update({
        'kingdom_id': kingdom.id,
        'kingdom_name': kingdom.name or f'Kingdom #{kingdom.id}',
        'kingdom_bonuses': bonuses,
        'kingdom_skill_effects': describe_kingdom_bonuses(bonuses),
        'kingdom_shield_until': kingdom.shield_until.isoformat() if kingdom.shield_until else None,
        'kingdom_shield_remaining': shield_remaining,
        'kingdom_is_shielded': shield_remaining > 0,
    })
    return data


def kingdom_unlocked_cosmetics(kingdom_id):
    keys = set(default_unlocked_cosmetic_keys())
    keys.update(
        key for (key,) in db.session.query(KingdomCosmeticUnlock.cosmetic_key)
        .filter_by(kingdom_id=kingdom_id)
        .all()
    )
    return keys


def _copy_unlocks_into_kingdom(source_kingdom, target_kingdom):
    if not source_kingdom or not target_kingdom:
        return
    existing = kingdom_unlocked_cosmetics(target_kingdom.id)
    for key in kingdom_unlocked_cosmetics(source_kingdom.id):
        if key in default_unlocked_cosmetic_keys() or key in existing:
            continue
        db.session.add(KingdomCosmeticUnlock(kingdom_id=target_kingdom.id, cosmetic_key=key))
        existing.add(key)


def _merge_source_kingdom_into_target(source_kingdom, target_kingdom):
    """Merge a smaller kingdom into a larger one when components fuse.

    Per the kingdom-levels rework the SMALLER kingdom is fully absorbed:
    cosmetic unlocks copy over, the longer shield wins, the SMALLER kingdom's
    pending gold is added to the target (clamped at the target's vault cap),
    and the smaller kingdom's progression (level, XP, skill points, skill
    allocations) is dropped — only the surviving (larger) kingdom retains its
    progression.  Additionally the surviving kingdom is awarded XP for every
    land it absorbs from the source, computed via ``xp_for_land_tier``.
    """
    if not source_kingdom or not target_kingdom or source_kingdom.id == target_kingdom.id:
        return
    _copy_unlocks_into_kingdom(source_kingdom, target_kingdom)
    source_until = source_kingdom.shield_until
    target_until = target_kingdom.shield_until
    if source_until and (not target_until or source_until > target_until):
        target_kingdom.shield_until = source_until

    # Transfer pending gold (clamped by target's vault cap).
    cap = float(kingdom_vault_cap(target_kingdom))
    target_pending = float(target_kingdom.pending_gold or 0.0)
    source_pending = float(source_kingdom.pending_gold or 0.0)
    target_kingdom.pending_gold = min(cap, target_pending + source_pending)
    source_kingdom.pending_gold = 0.0

    # Award XP for every land absorbed from the source kingdom.
    absorbed_lands = Land.query.filter_by(kingdom_id=source_kingdom.id).all()
    xp_total = sum(config.xp_for_land_tier(int(land.tier or 0)) for land in absorbed_lands)
    if xp_total > 0:
        award_kingdom_xp(target_kingdom, xp_total, reason='merger')

    # Notify owner that two of their kingdoms merged.
    try:
        db.session.add(KingdomNotification(
            user_id=target_kingdom.owner_user_id,
            kingdom_id=target_kingdom.id,
            kind='kingdoms_merged',
            payload={
                'absorbed_kingdom_id': source_kingdom.id,
                'absorbed_kingdom_name': (source_kingdom.name
                                          or f'Kingdom #{source_kingdom.id}'),
                'absorbed_lands': len(absorbed_lands),
                'xp_awarded': xp_total,
            },
        ))
    except Exception:
        pass
    target_kingdom.updated_at = _utcnow()


def _choose_component_kingdom(component_lands, used_kingdom_ids):
    counts = {}
    for land in component_lands:
        if land.kingdom_id:
            counts[land.kingdom_id] = counts.get(land.kingdom_id, 0) + 1
    candidates = []
    for kingdom_id, count in counts.items():
        kingdom = db.session.get(Kingdom, kingdom_id)
        if not kingdom:
            continue
        if kingdom_id in used_kingdom_ids:
            continue
        total_lands = Land.query.filter_by(kingdom_id=kingdom_id).count()
        created = kingdom.created_at or datetime.min
        candidates.append((count, total_lands, created, kingdom.id, kingdom))
    if not candidates:
        source = None
        for land in component_lands:
            if land.kingdom_id:
                source = db.session.get(Kingdom, land.kingdom_id)
                if source:
                    break
        owner_id = component_lands[0].owner_user_id
        return create_kingdom(owner_id, source_kingdom=source)
    candidates.sort(key=lambda item: (-item[0], -item[1], item[2], item[3]))
    return candidates[0][-1]


def reconcile_user_kingdoms(user_id, commit=False):
    """Ensure each connected land component has one persistent kingdom."""
    lands = Land.query.filter_by(owner_user_id=user_id).all()
    if not lands:
        delete_orphan_kingdoms(user_id, commit=False)
        if commit:
            db.session.commit()
        return []

    components = _connected_land_components_for_lands(lands)
    result = []
    used_kingdom_ids = set()
    # First pass: pick the canonical kingdom per component so we know which
    # kingdom IDs survive; the merge pass below then knows whether a referenced
    # source kingdom is being kept (split inheritance) or absorbed (merger).
    component_kingdoms = []
    for comp in components:
        kingdom = _choose_component_kingdom(comp, used_kingdom_ids)
        used_kingdom_ids.add(kingdom.id)
        component_kingdoms.append((comp, kingdom))

    for comp, kingdom in component_kingdoms:
        source_ids = {land.kingdom_id for land in comp if land.kingdom_id and land.kingdom_id != kingdom.id}
        for source_id in source_ids:
            # Skip the merge path for split inheritance: if the source kingdom
            # is being kept as the canonical kingdom for *another* component,
            # we must NOT absorb it (that would award XP, transfer pending
            # gold, and trample its progression).
            if source_id in used_kingdom_ids:
                continue
            source = db.session.get(Kingdom, source_id)
            _merge_source_kingdom_into_target(source, kingdom)
        for land in comp:
            land.kingdom_id = kingdom.id
        kingdom.owner_user_id = user_id
        kingdom.updated_at = _utcnow()
        result.append(kingdom)

    for land in Land.query.filter(Land.owner_user_id.is_(None), Land.kingdom_id.isnot(None)).all():
        land.kingdom_id = None

    delete_orphan_kingdoms(user_id, commit=False)

    if commit:
        db.session.commit()
    return result


def reconcile_all_kingdoms(commit=False):
    user_ids = [uid for (uid,) in db.session.query(Land.owner_user_id)
                .filter(Land.owner_user_id.isnot(None)).distinct().all()]
    existing_owner_ids = {uid for (uid,) in db.session.query(Kingdom.owner_user_id).distinct().all()}
    for user_id in sorted(existing_owner_ids - set(user_ids)):
        delete_orphan_kingdoms(user_id, commit=False)
    kingdoms = []
    for user_id in user_ids:
        kingdoms.extend(reconcile_user_kingdoms(user_id, commit=False))
    delete_orphan_kingdoms(commit=False)
    if commit:
        db.session.commit()
    return kingdoms


def reconcile_after_land_transfer(old_owner_id=None, new_owner_id=None, commit=False):
    touched = []
    for user_id in {old_owner_id, new_owner_id}:
        if user_id:
            touched.extend(reconcile_user_kingdoms(user_id, commit=False))
    if commit:
        db.session.commit()
    return touched


def kingdom_by_land_for_user(user_id, land_id=None, kingdom_id=None):
    if kingdom_id:
        kingdom = db.session.get(Kingdom, kingdom_id)
        if kingdom and kingdom.owner_user_id == user_id:
            return kingdom
        return None
    if land_id:
        land = db.session.get(Land, land_id)
        if not land or land.owner_user_id != user_id:
            return None
        if not land.kingdom_id:
            reconcile_user_kingdoms(user_id, commit=False)
            db.session.flush()
        return db.session.get(Kingdom, land.kingdom_id) if land.kingdom_id else None
    return None


def serialize_kingdom_config(kingdom):
    if not kingdom:
        return None
    lands = Land.query.filter_by(kingdom_id=kingdom.id).order_by(Land.row, Land.col).all()
    raw_gold_rate = round(sum(float(land.gold_rate or 0) for land in lands), 3)
    effective_gold_rate = effective_gold_rate_for_lands(lands) if lands else 0.0
    gold_bonus_rate = round(float(effective_gold_rate or 0) - raw_gold_rate, 3)
    allocations = kingdom_skill_allocations(kingdom.id)
    skills = {}
    for sdef in (config.KINGDOM_SKILL_DEFINITIONS or ()):
        row = allocations.get(sdef.key)
        level = int(row.level or 0) if row else 0
        next_level = level + 1 if level < sdef.max_level else level
        skills[sdef.key] = {
            'key': sdef.key,
            'name': sdef.name,
            'description': sdef.description,
            'icon_path': sdef.icon_path,
            'level': level,
            'max_level': sdef.max_level,
            'cost_multiplier': sdef.cost_multiplier,
            'effect_values': list(sdef.effect_values),
            'current_effect': config.skill_effect_at_level(sdef.key, level) if level > 0 else 0,
            'next_effect': (config.skill_effect_at_level(sdef.key, next_level)
                            if next_level > level else None),
            'next_cost': (config.skill_cost_to_buy_level(sdef.key, next_level)
                          if next_level > level else None),
        }
    spent = kingdom_spent_skill_points(kingdom.id)
    granted = int(kingdom.skill_points_granted or 0)
    now = _utcnow()
    shield_remaining = 0
    if kingdom.shield_until:
        shield_remaining = max(0, int((kingdom.shield_until - now).total_seconds()))
    bonuses = kingdom_skill_bonuses(kingdom)

    # Vault snapshot accrued up to "now" without mutating the DB row.
    vault_state = kingdom_vault_state(kingdom, now=now)

    # Level / XP progression.
    level = int(kingdom.level or 1)
    total_xp = int(kingdom.experience or 0)
    xp_into_level = total_xp - config.kingdom_total_xp_for_level(level)
    xp_for_next = config.kingdom_xp_required_for_level(level)

    return {
        'id': kingdom.id,
        'name': kingdom.name or f'Kingdom #{kingdom.id}',
        'owner_user_id': kingdom.owner_user_id,
        'style': kingdom.serialize_style(),
        'shield_until': kingdom.shield_until.isoformat() if kingdom.shield_until else None,
        'shield_remaining': shield_remaining,
        'is_shielded': shield_remaining > 0,
        'land_ids': [land.id for land in lands],
        'lands_count': len(lands),
        'lands': [land.serialize() for land in lands],
        'raw_gold_rate': raw_gold_rate,
        'effective_gold_rate': effective_gold_rate,
        'gold_bonus_rate': gold_bonus_rate,
        'unlocked_cosmetics': sorted(kingdom_unlocked_cosmetics(kingdom.id)),
        # Level / XP
        'level': level,
        'level_max': int(config.KINGDOM_LEVEL_MAX),
        'experience': total_xp,
        'xp_into_level': max(0, xp_into_level),
        'xp_for_next_level': xp_for_next,
        # Skill points
        'skill_points_total': granted,
        'skill_points_spent': spent,
        'skill_points_available': max(0, granted - spent),
        'skills': skills,
        'bonuses': bonuses,
        'skill_effects': describe_kingdom_bonuses(bonuses),
        # Gold vault
        'vault_pending': vault_state['pending'],
        'vault_cap': vault_state['cap'],
        'vault_full': vault_state['full'],
        'vault_rate_per_hour': vault_state['rate_per_hour'],
        # Aliases consumed by the persistent kingdom-config UI: ``pending_gold``
        # is the live snapshot accrued up to "now" (lazy: only computed when
        # the row is serialized; no background ticker), and ``gold_rate_per_hour``
        # is the kingdom's effective production rate.
        'pending_gold': vault_state['pending'],
        'gold_rate_per_hour': vault_state['rate_per_hour'],
        # Core protection
        'core_protection_active': kingdom_core_protection_active(kingdom),
    }


def shield_quote_for_kingdom(kingdom, hours):
    try:
        hours = int(hours or 0)
    except (TypeError, ValueError):
        raise ValueError('Shield duration must be a whole number of hours.')
    allowed = list(getattr(config, 'KINGDOM_SHIELD_DURATION_OPTIONS_HOURS', [6, 12, 24]) or [])
    max_hours = int(getattr(config, 'KINGDOM_SHIELD_MAX_HOURS', max(allowed or [24])) or 24)
    if hours <= 0:
        raise ValueError('Shield duration must be greater than zero hours.')
    if hours > max_hours:
        raise ValueError(f'Shield duration cannot exceed {max_hours} hours.')
    if allowed and hours not in allowed:
        opts = ', '.join(str(h) for h in sorted(allowed))
        raise ValueError(f'Shield duration must be one of: {opts} hour(s).')
    land_count = Land.query.filter_by(kingdom_id=kingdom.id).count() if kingdom else 0
    base = land_count * int(getattr(config, 'KINGDOM_SHIELD_PRICE_PER_HOUR_PER_LAND', 0) or 0) * hours
    reduction = float(kingdom_skill_bonuses(kingdom).get('shield_cost_reduction', 0.0) or 0.0)
    reduction = max(0.0, min(0.95, reduction))
    price = math.ceil(base * (1.0 - reduction))
    return {
        'kingdom_id': kingdom.id,
        'hours': hours,
        'lands_count': land_count,
        'price_per_hour_per_land': int(getattr(config, 'KINGDOM_SHIELD_PRICE_PER_HOUR_PER_LAND', 0) or 0),
        'reduction': reduction,
        'price_gold': price,
    }


# ── Gold Production ──────────────────────────────────────────────────────────

def accrue_pending_gold_for_user(user_id, *, now=None):
    """Advance pending gold for every kingdom owned by ``user_id``.

    Called from the kingdom map view so the shown vault values are fresh.
    Returns the list of touched kingdoms.
    """
    now = now or _utcnow()
    kingdoms = Kingdom.query.filter_by(owner_user_id=user_id).all()
    for kingdom in kingdoms:
        _accrue_pending_gold(kingdom, now=now)
    return kingdoms


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


def check_defence_incomplete(land_id, user_id):
    """Check if a player's defence config for a land is incomplete.

    A defence is incomplete when:
    - No defence config exists at all, OR
    - No figure exists that is not in resource deficit, OR
    - Fewer than 3 battle moves are configured.
    - Counter strategy is not set to exactly one of:
      battle figure XOR counter spell.

    Returns
    -------
    bool
        ``True`` if the defence is incomplete or missing.
    """
    cfg = LandConfig.query.filter(
        LandConfig.user_id == user_id,
        LandConfig.config_type == 'defence',
        LandConfig.land_id == land_id,
        db.or_(LandConfig.status == 'active', LandConfig.status.is_(None)),
    ).first()
    if not cfg:
        return True

    figures = LandConfigFigure.query.filter_by(config_id=cfg.id).all()
    if not figures:
        return True

    # Check if at least one figure is not in deficit
    has_valid_figure = any(
        not check_land_config_deficit(fig, figures) for fig in figures
    )
    if not has_valid_figure:
        return True

    # Check battle moves count
    move_count = LandConfigBattleMove.query.filter_by(config_id=cfg.id).count()
    if move_count < 3:
        return True

    has_battle_fig = (cfg.battle_figure_id is not None)
    has_counter_spell = (cfg.counter_spell_name is not None)

    # Strict strategy requirement: exactly one of battle figure or counter spell.
    if has_battle_fig == has_counter_spell:
        return True

    # Defensive check against stale battle_figure_id references.
    if has_battle_fig and not any(fig.id == cfg.battle_figure_id for fig in figures):
        return True

    # Health Boost prelude/counter spells require an own-figure target.
    figure_ids = {fig.id for fig in figures}
    prelude_data = cfg.prelude_spell_data if isinstance(cfg.prelude_spell_data, dict) else {}
    if cfg.prelude_spell_name == 'Health Boost':
        target_id = prelude_data.get('target_figure_id')
        if not target_id or target_id not in figure_ids:
            return True
    if cfg.counter_spell_name == 'Health Boost':
        target_id = cfg.counter_spell_target_figure_id
        if not target_id or target_id not in figure_ids:
            return True

    return False
