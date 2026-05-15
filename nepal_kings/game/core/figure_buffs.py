# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Shared client-side figure buff helpers."""


def _figure_id(figure):
    return getattr(figure, 'id', None)


def _figure_field(figure):
    family = getattr(figure, 'family', None)
    return getattr(family, 'field', None) or getattr(figure, 'field', None)


def _same_suit(left, right):
    return (getattr(left, 'suit', '') or '').lower() == (getattr(right, 'suit', '') or '').lower()


def buffs_allies_sources(figures, has_deficit=None, exclude_ids=None):
    """Return active same-side healer/buffs-allies sources.

    ``has_deficit`` is an optional predicate.  Figures for which it returns
    true do not provide the buff.  ``exclude_ids`` is used by battle contexts
    where field-only support sources should ignore active fighting figures.
    """
    excluded = set(exclude_ids or ())
    sources = []
    for figure in figures or []:
        if _figure_id(figure) in excluded:
            continue
        if not getattr(figure, 'buffs_allies', False):
            continue
        if has_deficit and has_deficit(figure):
            continue
        sources.append(figure)
    return sources


def buffs_allies_bonus_for(figure, sources):
    """Return +4 per same-suit buffs-allies source for village figures."""
    if not figure:
        return 0
    if (_figure_field(figure) or '').lower() != 'village':
        return 0
    return sum(4 for source in sources or [] if _same_suit(source, figure))


def apply_buffs_allies_to_icon_map(figures, icon_map, has_deficit=None, exclude_ids=None):
    """Apply buffs-allies bonuses to already-created figure icons.

    Every icon's ``buffs_allies_bonus`` is reset first, preventing stale values
    when a healer is removed, enters battle, or falls into resource deficit.
    Returns the active buff source figures for callers that also need them.
    """
    sources = buffs_allies_sources(
        figures,
        has_deficit=has_deficit,
        exclude_ids=exclude_ids,
    )
    for figure in figures or []:
        icon = icon_map.get(_figure_id(figure)) if icon_map else None
        if not icon:
            continue
        icon.buffs_allies_bonus = buffs_allies_bonus_for(figure, sources)
    return sources
