# Copyright (c) 2026 Marc Stieffenhofer. All rights reserved.
# See LICENSE file in the project root for full license information.
"""Helpers for conquer prelude targets that only exist in timeline replay.

Conquer preludes are executed on the server before the client has replayed the
pre-battle timeline.  Explosion can therefore delete a figure that the player
still sees during the land overview and earlier prelude bubbles.  These helpers
make that deleted figure selectable only for non-destructive prelude spell
replay, without relaxing normal duel/battle target validation.
"""

from types import SimpleNamespace

from models import ActiveSpell, Figure


_REPLAY_SELECTABLE_PRELUDE_SPELLS = frozenset({'Poison', 'Health Boost'})


def conquer_spell_allows_destroyed_replay_target(spell_name):
    """Return True for prelude spells that can harmlessly replay on a ghost."""
    return spell_name in _REPLAY_SELECTABLE_PRELUDE_SPELLS


def _coerce_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _explosion_replay_payload(spell):
    """Return the destroyed target snapshot for an executed Explosion prelude."""
    if not spell or spell.spell_name != 'Explosion':
        return None

    effect_data = spell.effect_data if isinstance(spell.effect_data, dict) else {}
    if not effect_data.get('prelude_origin'):
        return None
    if effect_data.get('prelude_status') != 'executed':
        return None

    snapshot = (
        effect_data.get('destroyed_figure_snapshot')
        or effect_data.get('target_figure_snapshot')
    )
    if not isinstance(snapshot, dict):
        return None

    target_id = _coerce_int(
        effect_data.get('destroyed_figure_id')
        or effect_data.get('target_figure_id')
        or spell.target_figure_id
        or snapshot.get('id')
    )
    if target_id is None:
        return None

    snapshot = dict(snapshot)
    snapshot.setdefault('id', target_id)
    return {
        'id': target_id,
        'source_spell_id': spell.id,
        'snapshot': snapshot,
    }


def conquer_explosion_replay_target_for_id(game, target_figure_id):
    """Find an executed conquer prelude Explosion snapshot by target id."""
    target_id = _coerce_int(target_figure_id)
    if not game or getattr(game, 'mode', None) != 'conquer' or target_id is None:
        return None

    spells = ActiveSpell.query.filter_by(
        game_id=game.id,
        spell_name='Explosion',
    ).all()
    for spell in spells:
        payload = _explosion_replay_payload(spell)
        if payload and payload['id'] == target_id:
            return payload
    return None


def conquer_destroyed_replay_targets_for_prelude(
    game,
    candidate_player_ids,
    spell_name,
):
    """Return selectable deleted Explosion victims for a pending prelude spell."""
    if not game or getattr(game, 'mode', None) != 'conquer':
        return []
    if not conquer_spell_allows_destroyed_replay_target(spell_name):
        return []

    candidate_ids = {
        coerced for coerced in (_coerce_int(pid) for pid in candidate_player_ids)
        if coerced is not None
    }
    if not candidate_ids:
        return []

    targets = []
    seen_target_ids = set()
    spells = ActiveSpell.query.filter_by(
        game_id=game.id,
        spell_name='Explosion',
    ).all()
    for spell in spells:
        payload = _explosion_replay_payload(spell)
        if not payload:
            continue

        target_id = payload['id']
        if target_id in seen_target_ids:
            continue

        snapshot = payload['snapshot']
        player_id = _coerce_int(snapshot.get('player_id'))
        if player_id not in candidate_ids:
            continue
        if bool(snapshot.get('checkmate')):
            continue
        if db_live_target_exists(game.id, target_id):
            continue

        seen_target_ids.add(target_id)
        targets.append(_snapshot_target_proxy(game.id, player_id, snapshot, payload))

    return targets


def db_live_target_exists(game_id, target_id):
    return Figure.query.filter_by(game_id=game_id, id=target_id).first() is not None


def _snapshot_target_proxy(game_id, player_id, snapshot, payload):
    target_id = payload['id']
    return SimpleNamespace(
        id=target_id,
        game_id=game_id,
        player_id=player_id,
        family_name=snapshot.get('family_name') or snapshot.get('name') or 'Figure',
        name=snapshot.get('name') or snapshot.get('family_name') or f'Figure {target_id}',
        suit=snapshot.get('suit') or '',
        color=snapshot.get('color') or '',
        field=snapshot.get('field') or '',
        produces=snapshot.get('produces') or {},
        requires=snapshot.get('requires') or {},
        checkmate=bool(snapshot.get('checkmate')),
        cards=snapshot.get('cards') or [],
        is_conquer_replay_target=True,
        conquer_replay_source_spell_id=payload.get('source_spell_id'),
        conquer_replay_snapshot=snapshot,
    )
