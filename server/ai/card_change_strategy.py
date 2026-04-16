# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Shared card-change heuristics used by action enum and execution."""

from __future__ import annotations

from typing import Any


KEEP_RANKS = {'K', 'Q'}                           # Only kings and queens are always kept
MAYBE_KEEP_RANKS: set[str] = set()                  # Nothing else gets conditional keep
LOW_MAIN_RANKS = {'7', '8'}

KEEP_SIDE_RANKS = {'2'}                            # Rank 2 is key for Healers, Carpenter, Stone Mason
LOW_SIDE_RANKS: set[str] = set()                   # All side ranks (3-6) have figure/spell uses

_RANK_VALUE_FALLBACK = {
    '2': 2,
    '3': 3,
    '4': 4,
    '5': 5,
    '6': 6,
    '7': 7,
    '8': 8,
    '9': 9,
    '10': 10,
    'J': 11,
    'Q': 12,
    'K': 13,
    'A': 14,
}


def _field(card: Any, name: str, default: Any = None) -> Any:
    if isinstance(card, dict):
        return card.get(name, default)
    return getattr(card, name, default)


def normalize_rank(rank: Any) -> str:
    """Convert ORM enum/string ranks into a canonical uppercase string."""
    value = rank
    if hasattr(value, 'value'):
        value = value.value
    if value is None:
        return ''
    return str(value).upper()


def _card_numeric_value(card: Any) -> int:
    raw = _field(card, 'value', 0)
    try:
        return int(raw)
    except (TypeError, ValueError):
        pass

    rank = normalize_rank(_field(card, 'rank'))
    return int(_RANK_VALUE_FALLBACK.get(rank, 0))


def select_main_cards_to_swap(
    cards: list[Any],
    maybe_keep_limit: int = 2,
    protect_ids: set[int] | None = None,
) -> list[int]:
    """Return card IDs that should be swapped according to AI keep/swap policy.

    ``protect_ids`` — card IDs needed for a tactic target (e.g. a figure
    the AI is planning to build).  These are never swapped regardless of
    their rank.
    """
    maybe_keep_limit = max(0, int(maybe_keep_limit))
    protect_ids = protect_ids or set()
    sorted_cards = sorted(cards or [], key=_card_numeric_value)

    to_swap: list[int] = []
    kept_counts: dict[str, int] = {}

    for card in sorted_cards:
        rank = normalize_rank(_field(card, 'rank'))
        card_id = _field(card, 'id')

        kept_counts[rank] = kept_counts.get(rank, 0)

        # Tactic-protected cards are never swapped
        try:
            if int(card_id) in protect_ids:
                kept_counts[rank] += 1
                continue
        except (TypeError, ValueError):
            pass

        if rank in KEEP_RANKS:
            kept_counts[rank] += 1
            continue

        if rank in MAYBE_KEEP_RANKS and kept_counts[rank] < maybe_keep_limit:
            kept_counts[rank] += 1
            continue

        try:
            to_swap.append(int(card_id))
        except (TypeError, ValueError):
            continue

    if not to_swap and sorted_cards:
        lowest_id = _field(sorted_cards[0], 'id')
        try:
            to_swap = [int(lowest_id)]
        except (TypeError, ValueError):
            to_swap = []

    return to_swap


def summarize_main_change(
    cards: list[Any],
    maybe_keep_limit: int = 2,
    protect_ids: set[int] | None = None,
) -> dict[str, int]:
    """Return summary counters for change-card action text and telemetry."""
    free_count = len(cards or [])
    low_count = sum(1 for c in (cards or []) if normalize_rank(_field(c, 'rank')) in LOW_MAIN_RANKS)
    to_swap = select_main_cards_to_swap(
        cards or [], maybe_keep_limit=maybe_keep_limit, protect_ids=protect_ids,
    )

    return {
        'free_count': int(free_count),
        'low_rank_count': int(low_count),
        'swap_count': int(len(to_swap)),
    }


def compute_tactic_protected_ids(
    free_cards: list[Any],
    targets: list[dict[str, Any]],
    max_targets: int = 3,
) -> set[int]:
    """Identify hand card IDs that should be kept for figure building targets.

    For each top target, look at the recipe's *required* main cards minus
    the *missing* ones to find which ranks+suits the AI already holds.
    Match those against ``free_cards`` (by rank + suit) and protect the
    first matching card ID per requirement slot.

    Also protects number cards (7-10) of the target suit when the target
    still needs one.
    """
    if not free_cards or not targets:
        return set()

    protected: set[int] = set()
    # Track which card IDs have already been claimed so one physical card
    # isn't double-counted across targets.
    claimed: set[int] = set()

    for target in targets[:max(1, int(max_targets))]:
        missing = target.get('missing_main') or {}
        suit = target.get('suit')
        if not suit:
            continue

        # --- Protect cards already held that the recipe needs ---
        # missing_main keys look like "J_Hearts": 1
        # Recipe requirement keys we DON'T see in missing are already in hand.
        # We must infer the full recipe from figure_recipes to know what's
        # required.  Instead, use a simpler approach: protect any free card
        # whose (rank, suit) is a key-rank for *any* recipe of this family+suit
        # that isn't in the missing set.
        from ai.figure_recipes import FIGURE_RECIPES
        family = target.get('family_name', '')
        recipe = next(
            (r for r in FIGURE_RECIPES if r.get('family_name') == family),
            None,
        )
        if not recipe:
            continue

        # Collect all required (rank, suit) for main cards in this recipe
        required_main_keys: list[tuple[str, str]] = []
        for rank, card_type in recipe.get('key_ranks', []):
            if card_type == 'main':
                required_main_keys.append((str(rank).upper(), suit))

        # Determine which of those are already in hand (not in missing)
        held_keys: list[tuple[str, str]] = []
        for rank, s in required_main_keys:
            key = f"{rank}_{s}"
            if missing.get(key, 0) <= 0:
                held_keys.append((rank, s))

        # Match held recipe keys to actual card IDs in free_cards
        for req_rank, req_suit in held_keys:
            for card in free_cards:
                cid = _field(card, 'id')
                try:
                    cid = int(cid)
                except (TypeError, ValueError):
                    continue
                if cid in claimed:
                    continue
                card_rank = normalize_rank(_field(card, 'rank'))
                card_suit = str(_field(card, 'suit', ''))
                if card_rank == req_rank and card_suit == req_suit:
                    protected.add(cid)
                    claimed.add(cid)
                    break

        # --- Protect number cards needed for this target ---
        needs_number = bool(recipe.get('needs_number_card'))
        num_type = recipe.get('number_card_type', 'main')
        if needs_number and num_type == 'main':
            # If target doesn't have a number card yet (number_value_assumed=0
            # or the target still shows it needs one), protect the best
            # matching number card in hand.
            num_options = {str(r).upper() for r in recipe.get('number_card_options', [])}
            # Find the highest-value matching number card
            best_card: tuple[int, int] | None = None  # (card_id, value)
            for card in free_cards:
                cid = _field(card, 'id')
                try:
                    cid = int(cid)
                except (TypeError, ValueError):
                    continue
                if cid in claimed:
                    continue
                card_rank = normalize_rank(_field(card, 'rank'))
                card_suit = str(_field(card, 'suit', ''))
                if card_rank in num_options and card_suit == suit:
                    val = _card_numeric_value(card)
                    if best_card is None or val > best_card[1]:
                        best_card = (cid, val)
            if best_card is not None:
                protected.add(best_card[0])
                claimed.add(best_card[0])

    return protected


# ---------------------------------------------------------------------------
# Side-card swap helpers
# ---------------------------------------------------------------------------

def select_side_cards_to_swap(
    cards: list[Any],
    protect_ids: set[int] | None = None,
) -> list[int]:
    """Return side-card IDs that should be swapped.

    ``protect_ids`` — card IDs needed for a tactic target (figures or
    spells).  These are never swapped.
    """
    protect_ids = protect_ids or set()
    sorted_cards = sorted(cards or [], key=_card_numeric_value)

    to_swap: list[int] = []

    for card in sorted_cards:
        rank = normalize_rank(_field(card, 'rank'))
        card_id = _field(card, 'id')

        # Tactic-protected cards are never swapped
        try:
            if int(card_id) in protect_ids:
                continue
        except (TypeError, ValueError):
            pass

        if rank in KEEP_SIDE_RANKS:
            continue

        try:
            to_swap.append(int(card_id))
        except (TypeError, ValueError):
            continue

    # Always swap at least one card when called
    if not to_swap and sorted_cards:
        lowest_id = _field(sorted_cards[0], 'id')
        try:
            to_swap = [int(lowest_id)]
        except (TypeError, ValueError):
            to_swap = []

    return to_swap


def summarize_side_change(
    cards: list[Any],
    protect_ids: set[int] | None = None,
) -> dict[str, int]:
    """Return summary counters for side-card change action text."""
    free_count = len(cards or [])
    to_swap = select_side_cards_to_swap(cards or [], protect_ids=protect_ids)

    return {
        'free_count': int(free_count),
        'swap_count': int(len(to_swap)),
    }


def compute_side_tactic_protected_ids(
    free_cards: list[Any],
    targets: list[dict[str, Any]],
    max_targets: int = 3,
) -> set[int]:
    """Identify side-hand card IDs that should be kept for figure building.

    Mirrors ``compute_tactic_protected_ids`` but for side-type key ranks
    and side-type number cards.
    """
    if not free_cards or not targets:
        return set()

    protected: set[int] = set()
    claimed: set[int] = set()

    for target in targets[:max(1, int(max_targets))]:
        missing = target.get('missing_side') or {}
        suit = target.get('suit')
        if not suit:
            continue

        from ai.figure_recipes import FIGURE_RECIPES
        family = target.get('family_name', '')
        recipe = next(
            (r for r in FIGURE_RECIPES if r.get('family_name') == family),
            None,
        )
        if not recipe:
            continue

        # Collect all required (rank, suit) for side cards in this recipe
        required_side_keys: list[tuple[str, str]] = []
        for rank, card_type in recipe.get('key_ranks', []):
            if card_type == 'side':
                required_side_keys.append((str(rank).upper(), suit))

        # Determine which are already in hand (not in missing)
        held_keys: list[tuple[str, str]] = []
        for rank, s in required_side_keys:
            key = f"{rank}_{s}"
            if missing.get(key, 0) <= 0:
                held_keys.append((rank, s))

        # Match held recipe keys to actual card IDs
        for req_rank, req_suit in held_keys:
            for card in free_cards:
                cid = _field(card, 'id')
                try:
                    cid = int(cid)
                except (TypeError, ValueError):
                    continue
                if cid in claimed:
                    continue
                card_rank = normalize_rank(_field(card, 'rank'))
                card_suit = str(_field(card, 'suit', ''))
                if card_rank == req_rank and card_suit == req_suit:
                    protected.add(cid)
                    claimed.add(cid)
                    break

        # Protect side number cards needed for this target
        needs_number = bool(recipe.get('needs_number_card'))
        num_type = recipe.get('number_card_type', 'main')
        if needs_number and num_type == 'side':
            num_options = {str(r).upper() for r in recipe.get('number_card_options', [])}
            best_card: tuple[int, int] | None = None
            for card in free_cards:
                cid = _field(card, 'id')
                try:
                    cid = int(cid)
                except (TypeError, ValueError):
                    continue
                if cid in claimed:
                    continue
                card_rank = normalize_rank(_field(card, 'rank'))
                card_suit = str(_field(card, 'suit', ''))
                if card_rank in num_options and card_suit == suit:
                    val = _card_numeric_value(card)
                    if best_card is None or val > best_card[1]:
                        best_card = (cid, val)
            if best_card is not None:
                protected.add(best_card[0])
                claimed.add(best_card[0])

    return protected
