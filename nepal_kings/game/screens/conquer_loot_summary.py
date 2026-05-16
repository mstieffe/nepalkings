# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Shared conquer/defence loot-risk copy helpers."""

from config import settings


def _plural(count, singular, plural=None):
    return singular if int(count or 0) == 1 else (plural or f'{singular}s')


def _land_tier(land):
    try:
        return max(1, int((land or {}).get('tier') or 1))
    except (TypeError, ValueError):
        return 1


def _loot_chance(land):
    bonuses = (land or {}).get('kingdom_bonuses') or {}
    try:
        return max(0.0, min(1.0, float(bonuses.get('loot_chance') or 0.0)))
    except (TypeError, ValueError):
        return 0.0


def _loot_bucket(rank):
    rank = str(rank or '').strip()
    if rank in getattr(settings, 'LOOT_KEY_RANKS', frozenset()):
        return 'key'
    return 'number'


def _loot_quota_summary(land, card_specs):
    tier = _land_tier(land)
    cards = [c for c in (card_specs or []) if c and c.get('rank')]
    key_count = sum(1 for c in cards if _loot_bucket(c.get('rank')) == 'key')
    number_count = max(0, len(cards) - key_count)
    key_loot = min(tier, key_count)
    number_loot = min(tier, number_count)
    return {
        'tier': tier,
        'total': len(cards),
        'key_loot': key_loot,
        'number_loot': number_loot,
        'base_total': key_loot + number_loot,
        'remaining_after_base': max(0, len(cards) - key_loot - number_loot),
    }


def build_loot_risk_description(land, card_specs, *, mode):
    """Return concise, land-specific copy for committed-card modals.

    ``mode`` is ``'conquer'`` for attacker cards or ``'defence'`` for saved
    defence cards.  The wording mirrors the server rule: tier N loots up to
    N key-rank cards plus N number-rank cards, then Defensive Looting can add
    extra rolls only when the defending kingdom wins.
    """
    summary = _loot_quota_summary(land, card_specs)
    tier = summary['tier']
    total = summary['total']
    base_total = summary['base_total']
    key_loot = summary['key_loot']
    number_loot = summary['number_loot']
    chance = _loot_chance(land)
    chance_pct = int(round(chance * 100))

    locked = (
        'Locked now: these cards cannot be used elsewhere while '
        f'the {"attack is active" if mode == "conquer" else "defence is saved"}.'
    )
    quota = (
        f'Tier {tier} quota: up to {tier} key-rank and {tier} number-rank '
        'cards.'
    )
    base = (
        f'{base_total} of these {total} '
        f'{_plural(total, "card")} '
        f'({key_loot} key-rank + {number_loot} number-rank)'
    )

    if mode == 'conquer':
        risk = (
            f'Loot risk: if the attack fails, the defender loots {base}. '
            f'{quota}'
        )
        if chance_pct > 0:
            skill = (
                f'Defensive Looting adds a {chance_pct}% extra roll on each '
                'remaining committed card.'
            )
        else:
            skill = 'No kingdom loot-skill bonus is active for this land.'
    else:
        risk = (
            f'Loot risk: if this land falls, the attacker loots {base}. '
            f'{quota}'
        )
        if chance_pct > 0:
            skill = (
                'Your Defensive Looting skill can loot extra attacker cards '
                'when this defence wins; it does not increase losses from '
                'these defence cards.'
            )
        else:
            skill = 'No kingdom loot-skill bonus increases losses from these defence cards.'

    return f'{locked} {risk} {skill}'
