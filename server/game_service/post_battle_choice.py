# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Post-battle pending-choice serialization and state transitions."""

from datetime import datetime, timedelta


def serialize_battle_card(card, card_type):
    """Create a serializable dict for a card involved in a battle."""
    data = card.serialize() if hasattr(card, 'serialize') else {}
    data['card_type'] = card_type
    return data


def post_battle_choice_timeout_seconds(settings):
    """Return the configured pending-choice timeout, clamped to zero."""
    return max(int(getattr(settings, 'POST_BATTLE_CHOICE_TIMEOUT_SECONDS', 300)), 0)


def make_post_battle_pending_choice(
    choice_type,
    player_id,
    default,
    *,
    now,
    timeout_seconds,
):
    """Build the persisted description of a pending post-battle choice."""
    created_at = now()
    timeout = timeout_seconds()
    deadline = created_at + timedelta(seconds=timeout)
    return {
        'type': choice_type,
        'player_id': player_id,
        'default': default,
        'created_at': created_at.isoformat(),
        'deadline_at': deadline.isoformat(),
        'timeout_seconds': timeout,
    }


def parse_pending_choice_deadline(pending):
    """Parse a pending-choice deadline, returning ``None`` when malformed."""
    try:
        deadline_raw = (pending or {}).get('deadline_at')
        return datetime.fromisoformat(deadline_raw) if deadline_raw else None
    except Exception:
        return None


def pending_choice_expired(
    pending,
    *,
    timeout_seconds,
    parse_deadline,
    now,
):
    """Return whether a pending choice has reached its configured deadline."""
    if not pending:
        return False
    if timeout_seconds() == 0:
        return True
    deadline = parse_deadline(pending)
    return bool(deadline and now() >= deadline)


def set_post_battle_pending_choice(
    game,
    choice_type,
    player_id,
    default,
    *,
    make_pending_choice,
    mark_modified,
):
    """Persist a pending choice without discarding existing battle results."""
    result = (
        dict(game.last_battle_result)
        if isinstance(game.last_battle_result, dict)
        else {}
    )
    result['post_battle_pending_choice'] = make_pending_choice(
        choice_type,
        player_id,
        default,
    )
    game.last_battle_result = result
    mark_modified(game, 'last_battle_result')


def clear_post_battle_pending_choice(
    game,
    *,
    defaulted=False,
    choice=None,
    mark_modified,
):
    """Clear a pending choice and optionally record how it was resolved."""
    result = (
        dict(game.last_battle_result)
        if isinstance(game.last_battle_result, dict)
        else {}
    )
    result.pop('post_battle_pending_choice', None)
    if defaulted:
        result['post_battle_choice_defaulted'] = True
    if choice:
        result['post_battle_choice'] = choice
    game.last_battle_result = result
    mark_modified(game, 'last_battle_result')
