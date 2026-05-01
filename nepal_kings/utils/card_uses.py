# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Index of game uses for each (suit, rank) card.

Used by the Collection screen's card-profile dialogue to show which
figures, spells and battle moves a particular card participates in.

The index is built lazily on first access (after pygame init, since the
underlying managers load icon surfaces).
"""

from collections import defaultdict
import logging

logger = logging.getLogger('nk.utils.card_uses')

_INDEX = None  # cached: {'figures': {(suit,rank): [(name, icon)]},
               #           'spells':  {(suit,rank): [(name, icon)]},
               #           'battle_moves': {rank:    [(name, icon)]}}


def _build_index():
    from game.components.figures.figure_manager import FigureManager
    from game.components.spells.spell_manager import SpellManager
    from game.components.battle_moves.battle_move_manager import BattleMoveManager

    index = {
        'figures': defaultdict(list),
        'spells': defaultdict(list),
        'battle_moves': defaultdict(list),
    }

    # ── Figures ─────────────────────────────────────────────────────
    fm = FigureManager()
    seen_fig = set()
    for fig in fm.figures:
        # Use only the cards required to *build* the figure (key + number).
        # ``cards_including_upgrade`` would also pull in the upgrade card,
        # which causes false positives like Q showing up under Small Rice
        # Farm — Q is the upgrade-to-Large cost, not a Small-Farm card.
        cards = list(fig.cards)
        for c in cards:
            key = (c.suit, c.rank)
            ident = (key, fig.name)
            if ident in seen_fig:
                continue
            seen_fig.add(ident)
            icon = getattr(fig, 'icon_img', None) or getattr(fig.family, 'icon_img', None)
            index['figures'][key].append((fig.name, icon))

    # ── Spells ──────────────────────────────────────────────────────
    sm = SpellManager()
    seen_sp = set()
    for sp in sm.spells:
        for c in sp.cards:
            key = (c.suit, c.rank)
            ident = (key, sp.name)
            if ident in seen_sp:
                continue
            seen_sp.add(ident)
            # Spell instances don't carry icon_img directly — only the family
            # surface is loaded in SpellManager.
            icon = getattr(getattr(sp, 'family', None), 'icon_img', None)
            index['spells'][key].append((sp.name, icon))

    # ── Battle moves (rank only) ────────────────────────────────────
    bmm = BattleMoveManager()
    for fam in bmm.families:
        rr = getattr(fam, 'required_rank', None)
        if rr is None or rr == 'none':
            continue
        ranks = ['7', '8', '9', '10'] if rr == 'number' else [rr]
        icon = getattr(fam, 'icon_img', None)
        for r in ranks:
            index['battle_moves'][r].append((fam.name, icon))

    return index


def get_card_uses(suit, rank):
    """Return a dict of game uses for the (suit, rank) card.

    Returns ``{'figures': [...], 'spells': [...], 'battle_moves': [...]}``
    where each list contains ``(name, icon_surface)`` tuples. Empty lists
    if nothing matches or the index could not be built.
    """
    global _INDEX
    if _INDEX is None:
        try:
            _INDEX = _build_index()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning('Failed to build card uses index: %s', exc)
            _INDEX = {'figures': {}, 'spells': {}, 'battle_moves': {}}
    return {
        'figures': list(_INDEX['figures'].get((suit, rank), [])),
        'spells': list(_INDEX['spells'].get((suit, rank), [])),
        'battle_moves': list(_INDEX['battle_moves'].get(rank, [])),
    }


def reset_cache():
    """Clear the cached index (used by tests)."""
    global _INDEX
    _INDEX = None
